"""The writers that already existed, wired fail-open.

The criterion is not "the ledger gets written". It is that **a lost write never becomes a green**:
if a writer fails, the stage reads as claimed-but-unobserved and the gate still exits 0. So the
assertion that matters is about the GATE's exit code, and the mutant is a writer whose failure
propagates.

Everything here drives the real `close-gate.sh`. A stub would test a story about the gate.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
GATE = SCRIPTS / "close-gate.sh"
READER = SCRIPTS / "plc-status.sh"
CROSS = SCRIPTS / "cross-family-review.sh"
LEDGER_DIR = ROOT / ".claude/.gate-runs/ledger"

# The two guards that make a bookkeeping failure invisible to the gate. Both are needed: removing
# either one alone leaves the gate green (see the mutant).
INNER_GUARD = '      --observer close-gate.sh --started-at "$now" --completed-at "$now" >/dev/null 2>&1 || true'
OUTER_GUARD = "ledger_flush || true"


def _run_gate(gate: Path, run_id: str, env: dict[str, str] | None = None):
    return subprocess.run(
        ["/bin/bash", str(gate), "task", "p1"],
        capture_output=True, text=True, check=False, cwd=str(ROOT),
        env={**os.environ, "PLC_RUN_ID": run_id, **(env or {})},
    )


def _ledger(run_id: str) -> Path:
    return LEDGER_DIR / f"{run_id}.jsonl"


def _clean(run_id: str) -> None:
    path = _ledger(run_id)
    if path.exists():
        path.unlink()


def _records(run_id: str) -> list[dict]:
    path = _ledger(run_id)
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l]


def _rendered(run_id: str) -> dict[str, str]:
    result = subprocess.run(
        ["/bin/bash", str(READER), "--run", run_id],
        capture_output=True, text=True, check=False, cwd=str(ROOT),
    )
    assert result.returncode == 0, result.stderr
    rows: dict[str, str] = {}
    for line in result.stdout.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and parts[0] in {"+", "?", "-", "~", "."}:
            stage, rest = parts[1].split(None, 1)
            rows[stage] = rest.strip()
    return rows


# ---------------------------------------------------------------------------
# The gate observes its own checks
# ---------------------------------------------------------------------------
def test_the_gate_records_the_checks_it_ran() -> None:
    run_id = "run-happy"
    _clean(run_id)
    try:
        result = _run_gate(GATE, run_id)
        # NOT `returncode == 0`. Whether the gate passes is a property of the working tree, not of
        # the wiring — and the wiring is what this asserts. What must hold either way is that the
        # gate RECORDED what it ran, and that close_gate_task agrees with the verdict it reached.
        records = _records(run_id)
        stages = {r["stage_id"]: r["status"] for r in records}
        for stage in ("product_diff", "journal", "invariants", "close_gate_task"):
            assert stage in stages, f"{stage} not recorded: {stages}"
        assert stages["close_gate_task"] == ("done" if result.returncode == 0 else "failed")
        # ONE record per stage. Check 8 reports per declared invariant, and twenty-two records would
        # read as twenty-two retries of a stage that ran once.
        assert len({r["stage_id"] for r in records}) == len(records), [r["stage_id"] for r in records]
        assert all(r["observed"] is True for r in records)
        assert all(r["observer"] == "close-gate.sh" for r in records)
        # No agent-authored claims in this phase: everything written here is an observation the
        # gate actually made.
        assert all(r["type"] == "stage_observation" for r in records)
    finally:
        _clean(run_id)


def test_a_stage_the_gate_never_reached_renders_missing_not_done() -> None:
    run_id = "run-render"
    _clean(run_id)
    try:
        _run_gate(GATE, run_id)
        rows = _rendered(run_id)
        assert rows["journal"].startswith("observed"), rows["journal"]
        for stage in ("qa_log", "smoke", "independent_review", "crosscheck_a"):
            assert rows[stage].startswith("missing"), f"{stage}: {rows[stage]}"
    finally:
        _clean(run_id)


# ---------------------------------------------------------------------------
# A lost write never becomes a green
# ---------------------------------------------------------------------------
def _assert_the_writer_cannot_change_the_gates_verdict(gate: Path, run_id: str) -> None:
    """A DIFFERENTIAL, not an absolute.

    An absolute (the gate exits 0) would make every row here depend on whether
    the working tree happens to satisfy the gate — and editing CHANGELOG.md, for one,
    legitimately restales the test-evidence fingerprint. Rows would then fail for
    a reason that had nothing to do with what they test, and the suite could not tell "the gate is
    red" from "the ledger broke the gate". Those are the only two things it exists to distinguish.

    So: run the gate with the writer working, run it with the writer failing, and require the SAME
    verdict. That is what the rule actually says — a lost write never CHANGES the outcome — and it
    is true whatever the tree's gate status happens to be."""
    baseline_id, broken_id = f"{run_id}-base", f"{run_id}-broken"
    _clean(baseline_id)
    _clean(broken_id)
    try:
        baseline = _run_gate(gate, baseline_id)
        broken = _run_gate(gate, broken_id, env={"PLC_LEDGER_BREAK": "1"})

        # THE VERDICT LINE, not the exit code alone. Why: while the gate happened
        # to be RED for an unrelated reason, a propagated ledger failure and a legitimately failing
        # check BOTH produced exit 1, the differential matched, and this mutant survived. The two
        # are still distinguishable, and this is how: `ledger_flush` runs after the verdict is
        # decided and before it is PRINTED, so a propagated failure kills the script with no
        # verdict line at all. A gate that reached its verdict said so; one that died in the
        # bookkeeping never gets to.
        def verdict(result):
            for line in result.stdout.splitlines():
                if line.startswith("✓ close-gate ") or line.startswith("✗ close-gate "):
                    return line
            return None

        assert verdict(baseline) is not None, (
            "the baseline run printed no verdict at all — this fixture cannot say anything\n"
            + baseline.stdout[-1200:]
        )
        assert verdict(broken) is not None, (
            "a lost write became a red: the gate died in its own bookkeeping and never reached a "
            "verdict\n" + broken.stdout[-1200:] + broken.stderr[-1200:]
        )
        assert verdict(broken) == verdict(baseline), (
            f"a lost write became a red: verdict changed from {verdict(baseline)!r} to "
            f"{verdict(broken)!r}"
        )
        assert broken.returncode == baseline.returncode, (
            f"a lost write became a red: the gate exits {baseline.returncode} when the ledger "
            f"writer works and {broken.returncode} when it fails"
        )
        assert not _ledger(broken_id).exists(), "a failing writer left a file behind"
    finally:
        _clean(baseline_id)
        _clean(broken_id)


def test_a_failing_writer_cannot_change_the_gates_verdict() -> None:
    """The criterion's own oracle. `PLC_LEDGER_BREAK` points the ledger path somewhere that cannot
    be created, so the REAL emitter runs and really fails — which is the same shape as it being
    killed mid-run. An absent emitter would not do: that path returns early and would exercise the
    graceful skip instead of the criterion."""
    _assert_the_writer_cannot_change_the_gates_verdict(GATE, "run-broken")


def test_mutant_a_propagating_writer_failure_reds_the_gate(tmp_path: Path) -> None:
    """The propagating-failure mutant, and it needs BOTH guards removed — which is the finding.

    One at a time: taking `|| true` off `ledger_flush` alone leaves the gate green,
    because the function swallows its own errors and returns 0. Taking `|| true` off the emitter
    call alone ALSO leaves it green, because `ledger_flush` is invoked as the left side of `||`,
    and `set -e` is suspended for the whole body of a function called in a condition context. The
    guard is doubled, the same way the emitter's duration ban is, and a mutant that removed
    only one would have been scored dead while the mechanism it targeted was still alive.

    With both gone the gate exits 1 — and it does so AFTER `GATE_VERDICT_REACHED`, so a
    bookkeeping failure would be indistinguishable from a legitimate gate FAIL rather than being
    reported as an abort. That is exactly the outcome the rule forbids."""
    text = GATE.read_text()
    assert text.count(INNER_GUARD) == 1, "the inner guard moved — this mutant is stale"
    assert text.count(OUTER_GUARD) == 1, "the outer guard moved — this mutant is stale"
    mutant = tmp_path / "gate-mutant.sh"
    mutant.write_text(
        text.replace(INNER_GUARD, INNER_GUARD[: -len(" || true")]).replace(OUTER_GUARD, "ledger_flush")
    )
    with pytest.raises(AssertionError, match="lost write became a red"):
        _assert_the_writer_cannot_change_the_gates_verdict(mutant, "run-mutant")


@pytest.mark.parametrize("guard", ["inner", "outer"])
def test_removing_only_one_guard_is_not_enough(tmp_path: Path, guard: str) -> None:
    """The measurement behind the mutant above, kept as its own rows so the claim "the guard is
    doubled" is asserted rather than described in a comment."""
    text = GATE.read_text()
    if guard == "inner":
        text = text.replace(INNER_GUARD, INNER_GUARD[: -len(" || true")])
    else:
        text = text.replace(OUTER_GUARD, "ledger_flush")
    half = tmp_path / f"gate-half-{guard}.sh"
    half.write_text(text)
    _assert_the_writer_cannot_change_the_gates_verdict(half, f"run-half-{guard}")


def test_nothing_renders_observed_without_a_record_saying_so() -> None:
    """The reader's half of the rule: whatever a missing write does, it must not read as evidence."""
    run_id = "run-absent"
    _clean(run_id)
    try:
        _run_gate(GATE, run_id, env={"PLC_LEDGER": "0"})
        assert not _ledger(run_id).exists()
        _ledger(run_id).write_text("")
        rows = _rendered(run_id)
        assert rows, "the reader produced nothing for an empty ledger"
        assert not any(r.startswith("observed") for r in rows.values()), rows
    finally:
        _clean(run_id)


def test_the_ledger_can_be_turned_off_entirely() -> None:
    """`PLC_LEDGER=0` is an off switch, not a degraded mode. An adopter who wants none of this gets
    the gate they had before, which is what "the ledger blocks nothing new" has to mean in code."""
    run_id = "run-off"
    _clean(run_id)
    try:
        _run_gate(GATE, run_id, env={"PLC_LEDGER": "0"})
        assert not _ledger(run_id).exists()
    finally:
        _clean(run_id)


# ---------------------------------------------------------------------------
# The second writer — mapped, never re-derived
# ---------------------------------------------------------------------------
def test_the_cross_family_writer_maps_the_envelope_it_already_produces() -> None:
    """`cross-family-review.sh` already decides whether the foreign reviewer ran and writes that
    into an envelope. The mirror MAPS that decision; computing a second opinion would be two
    mechanisms for one fact and they would drift. Asserted on the source, because running the real
    foreign CLI here would make this row depend on a paid third-party service and on a network."""
    text = CROSS.read_text()
    assert "ledger_mirror" in text
    assert "--status done" in text
    assert '--status failed --attribute "fallback_reason=${reason:-unstated}"' in text
    # Fail-open: the mirror can never change this script's exit code, which belongs to the REVIEW.
    assert 'ledger_mirror "$status" "$reason" || true' in text
    # Called AFTER the envelope has landed, so a mirror failure cannot cost the envelope.
    assert text.index('mv -f "$tmp" "$OUT"') < text.index('ledger_mirror "$status"')


def test_the_emitter_is_inside_the_gates_declared_dependency_envelope() -> None:
    """close-gate.sh CALLS these now, so they are inside its envelope in every sense that matters —
    and that invariant covers a helper only by it being declared."""
    declared = (SCRIPTS / "invariants/gate-jq-only-envelope.sh").read_text()
    assert "scripts/ledger-append.sh" in declared
    assert "scripts/ledger-run.sh" in declared


# ---------------------------------------------------------------------------
# The sixth consumer: the CALLER must honour a refusal the callee already makes.
# ---------------------------------------------------------------------------
def test_a_refusal_to_mint_an_attempt_id_skips_the_stage_rather_than_guessing() -> None:
    """`next-attempt` refuses when the ledger has a line it cannot parse, precisely so nobody
    mints an id that may already exist. Both writers caught that refusal with `|| attempt=1` and
    proceeded — guessing exactly the value the callee had just refused to give, and producing a
    duplicate attempt 1. A refusal is not a default.

    Asserted at the source in both writers, because reaching this through a real gate run needs a
    ledger that is torn at the moment the gate reads it, and a fixture that arranges that would be
    testing the fixture. What is asserted is the SHAPE: neither writer may fall back to a literal
    attempt id when the mint fails."""
    def code_only(text: str) -> str:
        """Comments stripped before matching. Reading the whole
        file would flag the COMMENT that explains the defect — a lexical false positive.
        A checker that cannot tell code from prose about code will eventually flag its own
        explanation."""
        out = []
        for line in text.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            out.append(line.split("  #", 1)[0])
        return "\n".join(out)

    for path in (GATE, CROSS):
        text = code_only(path.read_text())
        assert "next-attempt" in text, path
        assert "|| attempt=1" not in text, (
            f"{path.name} still defaults the attempt id when the mint REFUSES — that turns a "
            f"deliberate refusal into a guess of the exact value it refused to give"
        )
        # And the refusal has to lead somewhere that writes nothing.
        assert ("continue" in text) or ("return 0" in text), path.name


def test_the_mint_refuses_on_a_torn_ledger_and_says_so(tmp_path: Path) -> None:
    """The callee's half, asserted here because the caller's contract depends on it: `next-attempt`
    must FAIL rather than answer, or the skip above can never trigger."""
    ledger = tmp_path / "torn.jsonl"
    good = {
        "specversion": "1", "run_id": "r", "repo_id": "x", "phase": "p1", "stage_id": "spec",
        "attempt_id": 1, "type": "stage_observation", "status": "done", "observed": True,
        "observer": "x", "started_at": "2026-08-14T00:00:00Z",
        "completed_at": "2026-08-14T00:00:01Z", "artifacts": [],
    }
    ledger.write_text(json.dumps(good) + "\n" + '{"torn"' + "\n")
    result = subprocess.run(
        ["/bin/bash", str(SCRIPTS / "ledger-run.sh"), "next-attempt", str(ledger), "spec"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0, f"it answered {result.stdout.strip()!r} on an unreadable file"
    assert "unparseable" in result.stderr, result.stderr

    clean = tmp_path / "clean.jsonl"
    clean.write_text(json.dumps(good) + "\n")
    ok = subprocess.run(
        ["/bin/bash", str(SCRIPTS / "ledger-run.sh"), "next-attempt", str(clean), "spec"],
        capture_output=True, text=True, check=False,
    )
    assert ok.returncode == 0 and ok.stdout.strip() == "2", ok.stdout
