"""The reader.

Three things this file is really about.

`rows == len(registry)`, for a run whose ledger mentions two stages out of twenty. That is only
true if the reader walks the REGISTRY and asks what the records say, rather than walking the
records — and walking the records is the natural way to write it, which is why it has a mutant.

The five states stay five. A stage nothing observed is never rendered as done, an applicability
record with no reason never renders as a suppression, and a record carrying a schema version this
reader does not know is reported and rendered claimed rather than dropped — because dropping it
would silently become `missing`.

And `jq` absent is a named failure with NO matrix. A wrong conformance matrix is worse than no
matrix; that is the ledger's whole thesis, so there is no degraded print to fall back to.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
READER = Path(os.environ.get("PLC_STATUS_IMPL", SCRIPTS / "plc-status.sh"))
APPEND = SCRIPTS / "ledger-append.sh"
REGISTRY = ROOT / ".claude/stage-registry.json"

BASE = {
    "specversion": "1", "run_id": "live-1", "repo_id": "repo-xyz", "phase": "p1",
    "attempt_id": 1, "type": "stage_observation", "status": "done", "observed": True,
    "observer": "close-gate.sh", "started_at": "2026-08-13T10:00:00Z",
    "completed_at": "2026-08-13T10:00:05Z", "artifacts": [],
}

STAGE_COUNT = len(json.loads(REGISTRY.read_text())["stages"])


def _run(*args: str, impl: Path = READER, env: dict[str, str] | None = None):
    return subprocess.run(
        ["/bin/bash", str(impl), *args], capture_output=True, text=True, check=False,
        env={**os.environ, **(env or {})},
    )


def _ledger(tmp_path: Path, records: list[dict], run_id: str = "live-1") -> Path:
    """Records are PLANTED as JSON here rather than written through the emitter, and deliberately:
    several of them are shapes the emitter refuses to write (an unknown specversion, an
    applicability record with no reason). The reader has to cope with what is on disk, not with
    what a well-behaved writer would have produced."""
    ledger_dir = tmp_path / "ledger"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    path = ledger_dir / f"{run_id}.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    return ledger_dir


def _rows(ledger_dir: Path, run_id: str = "live-1", impl: Path = READER) -> dict[str, str]:
    result = _run("--run", run_id, "--ledger-dir", str(ledger_dir),
                  "--registry", str(REGISTRY), "--repo-root", str(ROOT), impl=impl)
    assert result.returncode == 0, result.stdout + result.stderr
    rows: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if not line.startswith("  ") or line.startswith("  20"):
            continue
        parts = line.strip().split(None, 1)
        if len(parts) != 2 or parts[0] not in {"+", "?", "-", "~", "."}:
            continue
        stage, rest = parts[1].split(None, 1)
        rows[stage] = rest.strip()
    return rows


def _state(ledger_dir: Path, stage: str, **kw) -> str:
    row = _rows(ledger_dir, **kw)[stage]
    for state in ("not-applicable (unverified)", "unknown (retro)", "observed", "claimed", "missing"):
        if row.startswith(state):
            return state
    raise AssertionError(f"unparseable row for {stage}: {row!r}")


def _sub(tmp_path: Path, name: str = "run") -> Path:
    """A fresh directory for a mutant run, so its ledger never lands beside the real one."""
    target = tmp_path / name
    target.mkdir(parents=True, exist_ok=True)
    return target


def _mutant(tmp_path: Path, old: str, new: str, name: str = "mutant.sh") -> Path:
    text = READER.read_text()
    assert text.count(old) == 1, f"mutation target occurs {text.count(old)} times: {old!r}"
    target = tmp_path / name
    target.write_text(text.replace(old, new))
    return target


# ---------------------------------------------------------------------------
# The row-count rule, live half — every registry stage produces exactly one row
# ---------------------------------------------------------------------------
def _assert_every_stage_gets_a_row(ledger_dir: Path, impl: Path = READER) -> None:
    rows = _rows(ledger_dir, impl=impl)
    registry = [s["stage_id"] for s in json.loads(REGISTRY.read_text())["stages"]]
    assert len(rows) == STAGE_COUNT, f"expected {STAGE_COUNT} rows, got {len(rows)}: {sorted(rows)}"
    assert sorted(rows) == sorted(registry), f"missing {set(registry) - set(rows)}"


def test_a_live_run_mentioning_two_stages_still_renders_every_row(tmp_path: Path) -> None:
    """The criterion, stated at its hardest: a ledger naming 2 of 20 stages must still produce 20
    rows, and the 18 nobody mentioned must say `missing`."""
    ledger_dir = _ledger(tmp_path, [
        {**BASE, "stage_id": "journal"},
        {**BASE, "stage_id": "test_evidence"},
    ])
    _assert_every_stage_gets_a_row(ledger_dir)
    rows = _rows(ledger_dir)
    assert _state(ledger_dir, "journal") == "observed"
    assert _state(ledger_dir, "test_evidence") == "observed"
    missing = [s for s in rows if rows[s].startswith("missing")]
    assert len(missing) == STAGE_COUNT - 2, missing


def test_mutant_enumerating_records_instead_of_the_registry_loses_rows(tmp_path: Path) -> None:
    """The natural wrong implementation. Walk the records and the one stage nobody touched becomes
    the one stage that does not appear — which is the failure the reader exists to close."""
    mutant = _mutant(
        tmp_path,
        "$registry.stages\n| map(. as $s",
        "($records | map(select(type == \"object\")) | group_by(.stage_id)\n"
        "  | map({stage_id: .[0].stage_id, retro_evidence: null}))\n| map(. as $s",
    )
    ledger_dir = _ledger(tmp_path, [
        {**BASE, "stage_id": "journal"},
        {**BASE, "stage_id": "test_evidence"},
    ])
    with pytest.raises(AssertionError, match="expected"):
        _assert_every_stage_gets_a_row(ledger_dir, impl=mutant)


def test_the_all_matrix_totals_the_registry_on_every_line(tmp_path: Path) -> None:
    for run_id, stages in (("live-1", ["journal"]), ("live-2", []), ("live-3", ["spec", "plan"])):
        _ledger(tmp_path, [{**BASE, "run_id": run_id, "stage_id": s} for s in stages], run_id=run_id)
    result = _run("--all", "--ledger-dir", str(tmp_path / "ledger"),
                  "--registry", str(REGISTRY), "--repo-root", str(ROOT))
    assert result.returncode == 0, result.stderr
    lines = [l for l in result.stdout.splitlines() if l.strip()]
    assert len(lines) == 3, result.stdout
    for line in lines:
        assert f"total={STAGE_COUNT}" in line, line


# ---------------------------------------------------------------------------
# The five states stay distinct and none collapses into "done"
# ---------------------------------------------------------------------------
def test_one_record_of_each_provenance_renders_five_distinct_states(tmp_path: Path) -> None:
    ledger_dir = _ledger(tmp_path, [
        {**BASE, "stage_id": "journal"},                                        # observed
        {**BASE, "stage_id": "spec", "observed": False, "type": "stage_claim"},  # claimed
        {**BASE, "stage_id": "smoke", "observed": False, "type": "applicability",
         "reason": "no user-visible surface"},                                   # not-applicable
        {**BASE, "stage_id": "plan", "retro": True},                             # (marks run retro)
    ])
    assert _state(ledger_dir, "journal") == "observed"
    assert _state(ledger_dir, "spec") == "claimed"
    assert _state(ledger_dir, "smoke") == "not-applicable (unverified)"
    # `retro: true` on any record marks the run; a stage the registry says leaves no recoverable
    # trace is then `unknown (retro)`, and one that does leave a trace is `missing`.
    assert _state(ledger_dir, "intent_gate") == "unknown (retro)"
    assert _state(ledger_dir, "qa_log") == "missing"
    assert len({_state(ledger_dir, s) for s in
                ("journal", "spec", "smoke", "intent_gate", "qa_log")}) == 5


def _assert_absent_observed_is_not_done(ledger_dir: Path, impl: Path = READER) -> None:
    state = _state(ledger_dir, "journal", impl=impl)
    assert state == "claimed", f"a record with no `observed` field rendered {state!r}"


def test_a_record_with_no_observed_field_renders_claimed_not_done(tmp_path: Path) -> None:
    """The fail-safe direction, and its named mutant."""
    record = {k: v for k, v in BASE.items() if k != "observed"}
    _assert_absent_observed_is_not_done(_ledger(tmp_path, [{**record, "stage_id": "journal"}]))


def test_mutant_defaulting_observed_to_true_reds_that(tmp_path: Path) -> None:
    mutant = _mutant(tmp_path, "def observed_flag: (.observed // false) == true;",
                     "def observed_flag: (.observed // true) == true;")
    record = {k: v for k, v in BASE.items() if k != "observed"}
    ledger_dir = _ledger(tmp_path, [{**record, "stage_id": "journal"}])
    with pytest.raises(AssertionError, match="rendered 'observed'"):
        _assert_absent_observed_is_not_done(ledger_dir, impl=mutant)


def test_a_claim_upgraded_by_an_observation_renders_observed_and_keeps_the_claim(tmp_path: Path) -> None:
    ledger_dir = _ledger(tmp_path, [
        {**BASE, "stage_id": "journal", "observed": False, "type": "stage_claim",
         "status": "running", "completed_at": None},
        {**BASE, "stage_id": "journal"},
    ])
    assert _state(ledger_dir, "journal") == "observed"
    assert "upgraded from a claim" in _rows(ledger_dir)["journal"]
    # And the claim is still in the timeline — evidence upgrades, it does not overwrite.
    result = _run("--run", "live-1", "--ledger-dir", str(ledger_dir),
                  "--registry", str(REGISTRY), "--repo-root", str(ROOT))
    assert result.stdout.count("journal  attempt 1") == 2, result.stdout


def test_an_applicability_record_with_no_reason_is_not_a_suppression(tmp_path: Path) -> None:
    """The interim authorization guard, on the READER's side. The emitter refuses to write one of these,
    but a reader that trusted whatever reached disk would still be forgeable — and a suppression
    that looks exactly like an authorized one is the failure the ledger exists to stop."""
    for reason in (None, "", "   "):
        record = {**BASE, "stage_id": "smoke", "observed": False, "type": "applicability"}
        if reason is not None:
            record["reason"] = reason
        ledger_dir = _ledger(tmp_path / str(reason), [record])
        state = _state(ledger_dir, "smoke")
        assert state == "claimed", f"reason={reason!r} rendered {state!r}"
        assert "carry no reason" in _rows(ledger_dir)["smoke"]


def test_evidence_beats_a_declaration_and_the_conflict_is_reported(tmp_path: Path) -> None:
    ledger_dir = _ledger(tmp_path, [
        {**BASE, "stage_id": "smoke", "observed": False, "type": "applicability",
         "reason": "declared not to apply"},
        {**BASE, "stage_id": "smoke"},
    ])
    assert _state(ledger_dir, "smoke") == "observed"
    assert "conflict" in _rows(ledger_dir)["smoke"]


# ---------------------------------------------------------------------------
# specversion dispatch — per record, never per file
# ---------------------------------------------------------------------------
def _assert_mixed_versions_render_per_record(ledger_dir: Path, impl: Path = READER) -> None:
    rows = _rows(ledger_dir, impl=impl)
    assert rows["journal"].startswith("observed"), rows["journal"]
    assert rows["spec"].startswith("claimed"), rows["spec"]
    assert "specversion this reader does not know" in rows["spec"], rows["spec"]


def test_a_file_spanning_two_schema_versions_is_read_record_by_record(tmp_path: Path) -> None:
    """A ledger can span a schema upgrade mid-run. The unknown-version record
    is REPORTED and rendered claimed — never dropped, because dropping it would silently become
    `missing`, and never trusted, because nothing here knows what it means."""
    ledger_dir = _ledger(tmp_path, [
        {**BASE, "stage_id": "journal"},
        {**BASE, "stage_id": "spec", "specversion": "2"},
    ])
    _assert_mixed_versions_render_per_record(ledger_dir)


def test_mutant_deciding_the_version_once_per_file_reds_that(tmp_path: Path) -> None:
    """Take the version from the FIRST record and apply it to the file. The v1 record is first, so
    the v2 record is silently accepted as v1 — the file reads as clean and the upgrade is
    invisible."""
    mutant = _mutant(
        tmp_path,
        'def usable: parseable and ((.specversion // "") | known);',
        'def usable: parseable and ((($records | map(select(parseable)) '
        '| first | .specversion) // "") | known);',
    )
    ledger_dir = _ledger(tmp_path, [
        {**BASE, "stage_id": "journal"},
        {**BASE, "stage_id": "spec", "specversion": "2"},
    ])
    with pytest.raises(AssertionError):
        _assert_mixed_versions_render_per_record(ledger_dir, impl=mutant)


# ---------------------------------------------------------------------------
# One dependency, and its absence is loud
# ---------------------------------------------------------------------------
def _assert_jq_absent_is_loud_and_prints_nothing(impl: Path, tmp_path: Path) -> None:
    empty_bin = tmp_path / "bin"
    empty_bin.mkdir(exist_ok=True)
    ledger_dir = _ledger(tmp_path, [{**BASE, "stage_id": "journal"}])
    result = subprocess.run(
        ["/bin/bash", str(impl), "--run", "live-1", "--ledger-dir", str(ledger_dir),
         "--registry", str(REGISTRY), "--repo-root", str(ROOT)],
        capture_output=True, text=True, check=False,
        env={**os.environ, "PATH": str(empty_bin)},
    )
    assert result.returncode != 0, "the reader ran without jq"
    assert "jq not found" in result.stderr, result.stderr
    assert result.stdout == "", f"a matrix reached the terminal anyway: {result.stdout!r}"


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq is the dependency under test")
def test_without_jq_it_exits_non_zero_and_prints_no_matrix(tmp_path: Path) -> None:
    _assert_jq_absent_is_loud_and_prints_nothing(READER, tmp_path)


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq is the dependency under test")
def test_mutant_degraded_fallback_reds_the_jq_assertion(tmp_path: Path) -> None:
    """A reader that limped on without jq would print a matrix built from nothing. The assertion
    that must red is the one about stdout being EMPTY — not the exit code, because a fallback could
    still exit non-zero after printing."""
    mutant = _mutant(
        tmp_path,
        '  command -v jq >/dev/null 2>&1 ||\n'
        '    die "jq not found -- it is this reader\'s one binary dependency, and a wrong '
        'conformance matrix is worse than no matrix, so nothing is printed" 3\n',
        '  if ! command -v jq >/dev/null 2>&1; then\n'
        '    printf "run <degraded>\\n  ? journal                claimed\\n"\n'
        '    printf "plc-status: jq not found\\n" >&2\n'
        '    exit 3\n'
        '  fi\n',
    )
    with pytest.raises(AssertionError, match="matrix reached the terminal"):
        _assert_jq_absent_is_loud_and_prints_nothing(mutant, tmp_path)


# ---------------------------------------------------------------------------
# It reads, and only reads
# ---------------------------------------------------------------------------
def test_the_reader_never_writes(tmp_path: Path) -> None:
    ledger_dir = _ledger(tmp_path, [{**BASE, "stage_id": "journal"}])
    before = {p: p.read_bytes() for p in ledger_dir.rglob("*")}
    _run("--run", "live-1", "--ledger-dir", str(ledger_dir),
         "--registry", str(REGISTRY), "--repo-root", str(ROOT))
    _run("--all", "--ledger-dir", str(ledger_dir),
         "--registry", str(REGISTRY), "--repo-root", str(ROOT))
    after = {p: p.read_bytes() for p in ledger_dir.rglob("*")}
    assert after == before


def test_no_run_at_all_is_an_error_that_says_so(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    result = _run("--ledger-dir", str(empty), "--registry", str(REGISTRY),
                  "--repo-root", str(ROOT), env={"PLC_RUN_ID": ""})
    assert result.returncode != 0
    assert "no run to show" in result.stderr


def test_the_command_is_registered() -> None:
    """A command file nobody lists is a command that does not ship — validate.py checks the
    manifest both ways, and this asserts the entry exists rather than trusting it was added."""
    manifest = (SCRIPTS / "commands-manifest.txt").read_text().splitlines()
    assert "plc-status.md" in manifest
    assert (ROOT / "commands/plc-status.md").exists()


# ---------------------------------------------------------------------------
# Provenance — defects that keep the SHAPE of the output.
#
# Every row below is a defect that shape-level tests do not see. They
# share one shape: they preserve the SHAPE of
# the output while changing what it says is true.
# ---------------------------------------------------------------------------
def _torn(record: dict) -> str:
    """A record truncated before its closing brace — what a killed append actually leaves."""
    return json.dumps(record)[:-1]


def _assert_one_bad_line_costs_only_itself(impl: Path, tmp_path: Path) -> None:
    ledger_dir = tmp_path / "ledger"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    good = {**BASE, "stage_id": "journal"}
    (ledger_dir / "live-1.jsonl").write_text(
        json.dumps(good) + "\n" + _torn({**BASE, "stage_id": "spec"}) + "\n"
    )
    result = _run("--run", "live-1", "--ledger-dir", str(ledger_dir),
                  "--registry", str(REGISTRY), "--repo-root", str(ROOT), impl=impl)
    assert result.returncode == 0, result.stderr
    rows = _rows(ledger_dir, impl=impl)
    assert _state(ledger_dir, "journal", impl=impl) == "observed", (
        "one unparseable line discarded a good record — `jq -s` fails on the WHOLE file, and the "
        "`|| printf '[]'` fallback then rendered every stage `missing`"
    )
    assert "do not parse" in result.stdout, result.stdout


def test_one_unparseable_line_does_not_discard_the_good_records(tmp_path: Path) -> None:
    """The record contract in its own words: a record that fails validation "is never dropped, because dropping
    would silently become `missing`". The reader did exactly that, for the whole file, on one torn
    append — announcing that a run did none of the process on the strength of a truncated write."""
    _assert_one_bad_line_costs_only_itself(READER, tmp_path)


def test_mutant_slurp_or_empty_reds_the_torn_ledger_row(tmp_path: Path) -> None:
    mutant = _mutant(
        tmp_path,
        '''  jq -R -s 'sub("\\n$"; "") | if . == "" then [] else split("\\n") end
            | map(try fromjson catch {"__unparseable__": true})' "$ledger" 2>/dev/null ||
    die "cannot read $ledger -- refusing to render a matrix built from nothing" 4''',
        '''  jq -s '.' "$ledger" 2>/dev/null || printf '[]\'''',
        name="slurp.sh",
    )
    with pytest.raises(AssertionError, match="discarded a good record"):
        _assert_one_bad_line_costs_only_itself(mutant, _sub(tmp_path, "slurp"))


def _assert_a_foreign_record_is_not_this_runs_evidence(impl: Path, tmp_path: Path) -> None:
    ledger_dir = _ledger(tmp_path, [{**BASE, "run_id": "someone-else", "stage_id": "journal"}])
    state = _state(ledger_dir, "journal", impl=impl)
    assert state == "missing", f"a record belonging to another run rendered {state!r}"
    assert "another run" in _rows(ledger_dir, impl=impl)["journal"]


def test_a_record_naming_another_run_is_reported_not_used(tmp_path: Path) -> None:
    """The reader picks the file by run id and used to trust everything inside it. One writer per
    file makes a foreign record unlikely; it does not make it false, and "unlikely" is not what a
    conformance matrix is for. Reported, never silently used and never silently dropped."""
    _assert_a_foreign_record_is_not_this_runs_evidence(READER, tmp_path)


def test_mutant_dropping_the_run_filter_reds_that(tmp_path: Path) -> None:
    mutant = _mutant(
        tmp_path,
        "def mine: (.run_id // null) == $run;",
        "def mine: true;",
        name="norun.sh",
    )
    with pytest.raises(AssertionError, match="rendered 'observed'"):
        _assert_a_foreign_record_is_not_this_runs_evidence(mutant, _sub(tmp_path, "norun"))


def _assert_a_declaration_is_not_evidence(impl: Path, tmp_path: Path) -> None:
    """Planted, because the emitter now refuses to write this — which is the doubled guard. The
    reader must hold on its own against a file that reached disk some other way."""
    ledger_dir = _ledger(tmp_path, [
        {**BASE, "stage_id": "smoke", "type": "applicability", "observed": True,
         "reason": "forged"},
    ])
    state = _state(ledger_dir, "smoke", impl=impl)
    assert state == "not-applicable (unverified)", (
        f"an applicability record with observed:true rendered {state!r} — a declaration was "
        f"treated as evidence, which is a forged suppression wearing the one word this tool "
        f"exists to make trustworthy"
    )
    assert "non-observation type" in _rows(ledger_dir, impl=impl)["smoke"]


def test_an_applicability_record_cannot_forge_an_observation(tmp_path: Path) -> None:
    _assert_a_declaration_is_not_evidence(READER, tmp_path)


def test_mutant_dropping_the_type_filter_reds_that(tmp_path: Path) -> None:
    mutant = _mutant(
        tmp_path,
        'def evidence: usable and (.type == "stage_observation") and observed_flag;',
        "def evidence: usable and observed_flag;",
        name="notype.sh",
    )
    with pytest.raises(AssertionError, match="rendered 'observed'"):
        _assert_a_declaration_is_not_evidence(mutant, _sub(tmp_path, "notype"))


def test_the_emitter_refuses_to_write_a_declaration_that_claims_to_be_evidence(tmp_path: Path) -> None:
    """The write-time half of the same guard, doubled the way the duration ban is."""
    ledger = tmp_path / "e.jsonl"
    argv = [
        "append", "--file", str(ledger), "--run-id", "r", "--repo-id", "x", "--phase", "p1",
        "--stage-id", "smoke", "--attempt-id", "1", "--status", "done", "--observer", "agent",
        "--started-at", "2026-08-13T10:00:00Z", "--completed-at", "2026-08-13T10:00:01Z",
        "--reason", "declared",
    ]
    refused = subprocess.run(
        ["/bin/bash", str(SCRIPTS / "ledger-append.sh"), *argv,
         "--type", "applicability", "--observed", "true"],
        capture_output=True, text=True, check=False,
    )
    assert refused.returncode == 1, refused.stdout
    assert "only legal on a stage_observation" in refused.stderr
    assert not ledger.exists()

    allowed = subprocess.run(
        ["/bin/bash", str(SCRIPTS / "ledger-append.sh"), *argv,
         "--type", "applicability", "--observed", "false"],
        capture_output=True, text=True, check=False,
    )
    assert allowed.returncode == 0, allowed.stderr


# ---------------------------------------------------------------------------
# One rule, several consumers.
#
# Teaching the resolver that a record belongs to a run does not teach the
# two OTHER things in this file that read the same ledger, so the same render simultaneously
# reported a record as foreign and used it. One renderer contradicting another is worse than either
# being wrong alone, because it makes the output unusable as evidence in both directions.
# ---------------------------------------------------------------------------
FOREIGN = {
    **BASE, "run_id": "someone-else", "stage_id": "smoke", "retro": True,
}


def _assert_a_foreign_record_cannot_make_this_run_retro(impl: Path, tmp_path: Path) -> None:
    ledger_dir = _ledger(tmp_path, [FOREIGN])
    state = _state(ledger_dir, "intent_gate", impl=impl)
    assert state == "missing", (
        f"a record belonging to another run made this run retro: intent_gate rendered {state!r}. "
        f"`unknown (retro)` is the forgiving state, so this is a run being excused on the strength "
        f"of somebody else's record"
    )


def test_a_foreign_record_cannot_make_this_run_retro(tmp_path: Path) -> None:
    _assert_a_foreign_record_cannot_make_this_run_retro(READER, tmp_path)


def test_mutant_unfiltered_retro_probe_reds_that(tmp_path: Path) -> None:
    # If the target moves, the mutation
    # helper's "occurs exactly once" assertion says so — a stale mutant that silently
    # matched nothing would have been a mutant that could not kill anything.
    mutant = _mutant(
        tmp_path,
        "if (for_run | any(.[]; usable and (.retro == true)))",
        "if (any(.[]; usable and (.retro == true)))",
        name="anyretro.sh",
    )
    with pytest.raises(AssertionError, match="made this run retro"):
        _assert_a_foreign_record_cannot_make_this_run_retro(mutant, _sub(tmp_path, "anyretro"))


def _timeline(ledger_dir: Path, run_id: str, impl: Path = READER) -> str:
    result = _run("--run", run_id, "--ledger-dir", str(ledger_dir),
                  "--registry", str(REGISTRY), "--repo-root", str(ROOT), impl=impl)
    assert result.returncode == 0, result.stderr
    return result.stdout.split("timeline ", 1)[1] if "timeline " in result.stdout else ""


def _assert_the_timeline_shows_only_this_runs_events(impl: Path, tmp_path: Path) -> None:
    ledger_dir = _ledger(tmp_path, [FOREIGN, {**BASE, "stage_id": "journal"}])
    timeline = _timeline(ledger_dir, "live-1", impl=impl)
    assert "journal" in timeline, f"this run's own event vanished from the timeline: {timeline!r}"
    assert "smoke" not in timeline, (
        f"the timeline printed another run's event as this run's, while the matrix above it "
        f"reported that same record as foreign: {timeline!r}"
    )


def test_the_timeline_shows_only_this_runs_events(tmp_path: Path) -> None:
    _assert_the_timeline_shows_only_this_runs_events(READER, tmp_path)


def test_mutant_unfiltered_timeline_reds_that(tmp_path: Path) -> None:
    mutant = _mutant(
        tmp_path,
        "      elif (mine | not)\n      then empty\n",
        "      elif false\n      then empty\n",
        name="anytimeline.sh",
    )
    with pytest.raises(AssertionError, match="another run's event as this run's"):
        _assert_the_timeline_shows_only_this_runs_events(mutant, _sub(tmp_path, "anytl"))


def _assert_the_unparseable_marker_is_reachable(impl: Path, tmp_path: Path) -> None:
    """A guard that cannot fire, found in the code written to fix guards that cannot fire.

    The marker was built as a string and then dropped by a `select(type == "object")` on the very
    next line, so the comment promising "the one place a reader can see WHERE the file broke" had
    no mechanism at all behind it."""
    ledger_dir = tmp_path / "ledger"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    (ledger_dir / "live-1.jsonl").write_text(
        json.dumps({**BASE, "stage_id": "journal"}) + "\n" + _torn({**BASE, "stage_id": "spec"}) + "\n"
    )
    timeline = _timeline(ledger_dir, "live-1", impl=impl)
    assert "unparseable line" in timeline, (
        f"the promised marker never printed — the timeline shows no sign the file broke: {timeline!r}"
    )
    assert "journal" in timeline, "the good event vanished with the bad one"


def test_the_unparseable_marker_actually_prints(tmp_path: Path) -> None:
    _assert_the_unparseable_marker_is_reachable(READER, tmp_path)


def test_mutant_dropping_the_marker_reds_that(tmp_path: Path) -> None:
    mutant = _mutant(
        tmp_path,
        '      then "  <unparseable line -- run: /bin/bash scripts/ledger-append.sh validate>"',
        "      then empty",
        name="nomarker.sh",
    )
    with pytest.raises(AssertionError, match="marker never printed"):
        _assert_the_unparseable_marker_is_reachable(mutant, _sub(tmp_path, "nomarker"))


# ---------------------------------------------------------------------------
# One rule, three consumers.
#
# The defect class here is not "a bug", it is "a rule applied unevenly across consumers of the same
# data". The instance below is the known-specversion rule, once applied in
# the resolver and nowhere else. As a shape rather than an instance: this file has
# three consumers of the ledger, and every rule has to reach all three.
# ---------------------------------------------------------------------------
UNKNOWN_VERSION_RETRO = {
    **BASE, "specversion": "999", "stage_id": "journal", "retro": True, "observer": "probe",
}


def _assert_an_unreadable_record_cannot_decide_what_kind_of_run_this_is(
    impl: Path, tmp_path: Path
) -> None:
    ledger_dir = _ledger(tmp_path, [UNKNOWN_VERSION_RETRO])
    state = _state(ledger_dir, "intent_gate", impl=impl)
    assert state == "missing", (
        f"intent_gate rendered {state!r}: the run was marked retro on the authority of a record "
        f"whose own row says this reader cannot interpret it. `unknown (retro)` is the forgiving "
        f"state, so this excuses a run on evidence the reader just disclaimed"
    )
    # The record itself is still reported — never dropped, which would make it `missing` silently.
    assert "does not know" in _rows(ledger_dir, impl=impl)["journal"]


def test_an_unreadable_record_cannot_decide_what_kind_of_run_this_is(tmp_path: Path) -> None:
    _assert_an_unreadable_record_cannot_decide_what_kind_of_run_this_is(READER, tmp_path)


def test_a_known_version_retro_record_still_marks_the_run_retro(tmp_path: Path) -> None:
    """The control the fix above could break. Tightening a rule until nothing satisfies it is a
    way of passing the test while destroying the feature."""
    ledger_dir = _ledger(tmp_path, [{**BASE, "stage_id": "journal", "retro": True}])
    assert _state(ledger_dir, "intent_gate") == "unknown (retro)"


def test_mutant_retro_probe_ignoring_specversion_reds_that(tmp_path: Path) -> None:
    mutant = _mutant(
        tmp_path,
        "if (for_run | any(.[]; usable and (.retro == true)))",
        "if (for_run | any(.[]; (.retro == true)))",
        name="anyversion.sh",
    )
    with pytest.raises(AssertionError, match="cannot interpret it"):
        _assert_an_unreadable_record_cannot_decide_what_kind_of_run_this_is(
            mutant, _sub(tmp_path, "anyversion")
        )


def test_the_timeline_marks_an_unreadable_record_rather_than_rendering_it(tmp_path: Path) -> None:
    """The THIRD consumer, the timeline.
    It would otherwise print `observed=true` for a record the matrix beside it calls
    uninterpretable — the two views contradicting each other."""
    ledger_dir = _ledger(tmp_path, [UNKNOWN_VERSION_RETRO])
    timeline = _timeline(ledger_dir, "live-1")
    assert "unknown specversion" in timeline, timeline
    assert "observed=true" not in timeline, (
        f"the timeline rendered an uninterpretable record as a normal event: {timeline!r}"
    )


# ---------------------------------------------------------------------------
# The structural change that ends the class.
#
# The reason is written into the script: a
# rule lived in as many copies as there were consumers, so fixing instances could never finish.
# There is one prelude (`JQ_RULES`) and every consumer starts from it. These rows guard the four
# known instances plus one more.
# ---------------------------------------------------------------------------
def test_a_blank_line_is_an_invalid_jsonl_line_not_nothing(tmp_path: Path) -> None:
    """`ledger-append.sh validate` reported a blank line and the reader dropped it, so the two
    programs disagreed about the same file — the uneven-rule class between two binaries rather than
    two functions."""
    ledger_dir = tmp_path / "ledger"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    (ledger_dir / "live-1.jsonl").write_text(json.dumps({**BASE, "stage_id": "journal"}) + "\n\n")
    result = _run("--run", "live-1", "--ledger-dir", str(ledger_dir),
                  "--registry", str(REGISTRY), "--repo-root", str(ROOT))
    assert "do not parse" in result.stdout, result.stdout
    # The good record is untouched, and the trailing newline every correct file ends with is NOT
    # counted — the control that keeps this from flagging every well-formed ledger.
    assert _state(ledger_dir, "journal") == "observed"
    (ledger_dir / "clean.jsonl").write_text(
        json.dumps({**BASE, "run_id": "clean", "stage_id": "journal"}) + "\n"
    )
    clean = _run("--run", "clean", "--ledger-dir", str(ledger_dir),
                 "--registry", str(REGISTRY), "--repo-root", str(ROOT))
    assert "do not parse" not in clean.stdout, clean.stdout


def test_the_timeline_shows_the_type_so_a_declaration_cannot_look_like_evidence(tmp_path: Path) -> None:
    """The per-stage row said "a declaration is not evidence"; the timeline rendered that same
    record in exactly the shape of a real observation. Two views of one record that could not both
    be read as true."""
    ledger_dir = _ledger(tmp_path, [
        {**BASE, "stage_id": "journal", "type": "stage_claim", "observed": True},
    ])
    timeline = _timeline(ledger_dir, "live-1")
    assert "stage_claim" in timeline, timeline
    assert "(NOT evidence)" in timeline, timeline
    assert _state(ledger_dir, "journal") == "claimed"


def test_the_all_summary_does_not_hide_a_report_the_run_view_shows(tmp_path: Path) -> None:
    """`--all` is the fourth consumer of the same resolved rows, and the one most likely to be read
    on its own. It discarded the notes column entirely."""
    _ledger(tmp_path, [{**BASE, "stage_id": "journal", "specversion": "99"}])
    result = _run("--all", "--ledger-dir", str(tmp_path / "ledger"),
                  "--registry", str(REGISTRY), "--repo-root", str(ROOT))
    assert result.returncode == 0, result.stderr
    assert "carry a report" in result.stdout, result.stdout


def test_a_record_naming_an_unknown_stage_is_reported_not_invisible(tmp_path: Path) -> None:
    """The registry is the denominator, so a
    record for a stage it does not declare produces no row — and "produces no row" was
    indistinguishable from "is not on disk"."""
    ledger_dir = _ledger(tmp_path, [{**BASE, "stage_id": "not_a_registry_stage"}])
    rows = _rows(ledger_dir)
    assert len(rows) == STAGE_COUNT
    assert any("does not declare" in note for note in rows.values()), rows


def test_the_rules_are_defined_once(tmp_path: Path) -> None:
    """The structural assertion, and the reason the class stopped recurring. Each rule has exactly
    one definition; a consumer that wants it says its name. Instance-fixing could
    not finish this, because a rule in four copies can be forgotten in four places."""
    text = (SCRIPTS / "plc-status.sh").read_text()
    for rule in ("def known:", "def parseable:", "def usable:", "def mine:",
                 "def evidence:", "def for_run:"):
        assert text.count(rule) == 1, f"{rule} is defined {text.count(rule)} times"
    assert text.count("JQ_RULES='") == 1
    # And every consumer starts from the prelude rather than re-deriving.
    assert text.count('"$JQ_RULES"') >= 3, "a consumer is not using the shared rules"


# ---------------------------------------------------------------------------
# Every suppressed error answers one question: does it cost a RECORD or a GUARANTEE?
# ---------------------------------------------------------------------------
def test_an_unreadable_ledger_refuses_rather_than_reporting_a_run_did_nothing(tmp_path: Path) -> None:
    """The reader is the one component here that is never fail-open, and this was fail-open.

    `|| printf '[]'` turned a READ FAILURE into an empty record set, so a ledger that exists and
    cannot be read rendered every stage `missing` — a run reported as having done none of the
    process because of a permission bit. Absent and unreadable are different facts and only one of
    them is empty.

    The refusal is checked BEFORE any output and OUTSIDE a command substitution, both of which
    matter: `die` inside `$( )` exits only the subshell, and the first version let the run header
    reach the terminal before the refusal landed. "Prints no matrix" has to mean prints nothing."""
    ledger_dir = _ledger(tmp_path, [{**BASE, "stage_id": "journal"}])
    ledger = ledger_dir / "live-1.jsonl"
    assert _state(ledger_dir, "journal") == "observed"

    ledger.chmod(0o000)
    try:
        for args in (["--run", "live-1"], ["--all"]):
            result = _run(*args, "--ledger-dir", str(ledger_dir),
                          "--registry", str(REGISTRY), "--repo-root", str(ROOT))
            assert result.returncode != 0, f"{args}: rendered anyway"
            assert result.stdout == "", f"{args}: {result.stdout!r} reached the terminal"
            assert "cannot be read" in result.stderr, result.stderr
    finally:
        ledger.chmod(0o644)

    # An ABSENT ledger is still empty rather than an error — the control that keeps this refusal
    # from swallowing the ordinary "this run has no records yet" case.
    absent = _run("--run", "no-such-run", "--ledger-dir", str(ledger_dir),
                  "--registry", str(REGISTRY), "--repo-root", str(ROOT))
    assert absent.returncode == 0, absent.stderr


# ---------------------------------------------------------------------------
# Read the output as the person who has to ACT on it.
#
# Code-defect lenses never ask whether the output MISLEADS, which is the one
# thing this tool exists not to do. Every value in the four cases below was already technically
# correct.
# ---------------------------------------------------------------------------
def test_a_missing_row_says_whether_the_stage_was_even_required(tmp_path: Path) -> None:
    """The most misleading thing in the tool before this. A task run printed `missing` for
    `spec_doc`, `changelog`, `independent_review` and the rest, and a competent reader concluded
    the process had been violated — when the registry only says those are conditionally mandated
    and NOTHING evaluates the condition yet. `missing` here
    means NOT SEEN, not necessarily SKIPPED, and the row now says so."""
    ledger_dir = _ledger(tmp_path, [{**BASE, "stage_id": "journal"}])
    rows = _rows(ledger_dir)
    missing = {k: v for k, v in rows.items() if v.startswith("missing")}
    assert missing, rows
    for stage, note in missing.items():
        assert "mandated" in note, f"{stage} renders bare `missing` with no condition: {note!r}"
        assert "NOT SEEN" in note, stage


def test_the_two_kinds_of_unknown_retro_are_told_apart(tmp_path: Path) -> None:
    """`unknown (retro)` meant two things that call for opposite actions: evidence that could never
    have survived (nothing to do) and evidence this scanner declines to recover (a person can still
    check by hand). They rendered identically."""
    ledger_dir = _ledger(tmp_path, [{**BASE, "stage_id": "journal", "retro": True}])
    rows = _rows(ledger_dir)
    assert rows["intent_gate"].startswith("unknown (retro)")
    assert "NOT IMPLEMENTED" not in rows["intent_gate"], rows["intent_gate"]
    assert "NOT IMPLEMENTED" in rows["changelog"], rows["changelog"]
    assert "by hand" in rows["cross_family_review"], rows["cross_family_review"]


def test_an_unsupported_flag_is_refused_not_ignored(tmp_path: Path) -> None:
    """`--index-dir` was parsed and never read, so asking for one run population silently rendered
    another. Accepted-and-ignored is worse than refused: the reader gets an answer to a question
    they did not ask, with no sign of the substitution."""
    result = _run("--all", "--ledger-dir", str(tmp_path), "--index-dir", str(tmp_path))
    assert result.returncode == 2, result.stdout
    assert "not supported here" in result.stderr
    assert "ledger-index.sh list" in result.stderr, "the refusal must say where to go instead"


def test_the_default_run_discloses_that_it_guessed(tmp_path: Path) -> None:
    """With no run declared, the tool picks the newest ledger by mtime — and rendered that exactly
    like a run somebody had chosen. The disclosure is on STDOUT, because stdout is what a reader is
    shown verbatim; putting it only in the command's documentation is putting it where the person
    reading the output is not looking."""
    ledger_dir = _ledger(tmp_path, [{**BASE, "stage_id": "journal"}], run_id="only-one")
    result = _run("--ledger-dir", str(ledger_dir), "--registry", str(REGISTRY),
                  "--repo-root", str(ROOT), env={"PLC_RUN_ID": ""})
    assert result.returncode == 0, result.stderr
    assert "NEWEST ledger by mtime" in result.stdout, result.stdout
    assert "--run" in result.stdout, "the disclosure should say how to be sure"

    # And an explicitly named run does NOT carry the disclosure — a warning on every render is a
    # warning nobody reads.
    named = _run("--run", "only-one", "--ledger-dir", str(ledger_dir),
                 "--registry", str(REGISTRY), "--repo-root", str(ROOT))
    assert "NEWEST ledger by mtime" not in named.stdout
