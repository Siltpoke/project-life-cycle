"""Run identity, the on-disk layout, and appends that do not lose records.

The centre of this file is one differential and one mutant. The oracle has two clauses:

  (a) zero interleaved or torn records, and
  (b) records read back == writes attempted.

Clause (b) is the one that exists because of a defect the first draft shipped: appending to a
multi-record file with temp-then-rename is read-modify-write, and under two writers it silently
LOSES a record — which is neither interleaved nor torn, so clause (a) cannot see it. The mutant
below reintroduces exactly that, and the assertion this suite makes is not "the mutant dies" but
**"(b) dies while (a) stays green"**. A mutant that reds both would leave the actual claim
unproven.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent
APPEND = Path(os.environ.get("PLC_LEDGER_APPEND_IMPL", SCRIPTS / "ledger-append.sh"))
RUN = Path(os.environ.get("PLC_LEDGER_RUN_IMPL", SCRIPTS / "ledger-run.sh"))

WRITERS = 6
PER_WRITER = 15


def _run(script: Path, *args: str, env: dict[str, str] | None = None):
    return subprocess.run(
        ["/bin/bash", str(script), *args],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, **(env or {})},
    )


def _mutant(tmp_path: Path, old: str, new: str, source: Path = APPEND, name: str = "mutant.sh") -> Path:
    text = source.read_text()
    assert text.count(old) == 1, f"mutation target occurs {text.count(old)} times, want 1: {old!r}"
    target = tmp_path / name
    target.write_text(text.replace(old, new))
    assert target.read_text() != text, "mutant did not change the file"
    return target


# The line the design turns on: one physical append by the file's sole owner.
PLAIN_APPEND = """  printf '%s\\n' "$record" >> "$file"\n"""

# And the shape the single-writer rule rejects. Read the file, add in memory, write a temp, rename over the top.
# It never tears a record and it never interleaves one — it just drops whichever concurrent append
# landed between the read and the rename.
READ_MODIFY_WRITE = """  __tmp="$file.tmp.$$"
  { if [ -f "$file" ]; then cat "$file"; fi; printf '%s\\n' "$record"; } > "$__tmp"
  mv -f "$__tmp" "$file"
"""


def _writer_driver(tmp_path: Path, impl: Path) -> Path:
    """One process, PER_WRITER appends. A loop inside one bash process rather than N python
    subprocesses — the concurrency being tested is between WRITERS, not between appends."""
    driver = tmp_path / "writer.sh"
    driver.write_text(
        "#!/bin/bash\n"
        "set -eu\n"
        'file="$1"; who="$2"; n="$3"\n'
        "for i in $(seq 1 \"$n\"); do\n"
        f'  /bin/bash "{impl}" append --file "$file" \\\n'
        '    --run-id shared-run --repo-id repo-abc --phase p1 \\\n'
        '    --stage-id "$who" --attempt-id "$i" --type stage_observation --status done \\\n'
        '    --observed true --observer close-gate.sh \\\n'
        '    --started-at 2026-08-13T10:00:00Z --completed-at 2026-08-13T10:00:01Z\n'
        "done\n"
    )
    return driver


def _race(tmp_path: Path, impl: Path) -> tuple[Path, int, list[str]]:
    """Run WRITERS concurrent writers against ONE file. Returns (file, attempted, raw lines)."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    ledger = tmp_path / "shared.jsonl"
    driver = _writer_driver(tmp_path, impl)
    procs = [
        subprocess.Popen(
            ["/bin/bash", str(driver), str(ledger), f"w{i}", str(PER_WRITER)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for i in range(WRITERS)
    ]
    for p in procs:
        out, err = p.communicate()
        assert p.returncode == 0, f"a writer failed: {err or out}"
    lines = ledger.read_text().splitlines() if ledger.exists() else []
    return ledger, WRITERS * PER_WRITER, lines


def _clause_a_no_torn_or_interleaved(lines: list[str]) -> None:
    """Every physical line is exactly one whole record. A torn or interleaved write shows up as a
    line that does not parse, or one that parses but is not a record."""
    for index, line in enumerate(lines, 1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:  # pragma: no cover - only under a torn write
            raise AssertionError(f"line {index} is torn or interleaved: {line!r} ({exc})") from exc
        assert isinstance(record, dict), f"line {index} is not a record: {line!r}"
        assert record.get("run_id") == "shared-run", f"line {index} is malformed: {record}"


def _clause_b_nothing_lost(lines: list[str], attempted: int) -> None:
    written = {(json.loads(l)["stage_id"], json.loads(l)["attempt_id"]) for l in lines}
    expected = {(f"w{i}", j) for i in range(WRITERS) for j in range(1, PER_WRITER + 1)}
    missing = sorted(expected - written)
    assert len(lines) == attempted, (
        f"records read back ({len(lines)}) != writes attempted ({attempted}); "
        f"{len(missing)} lost, e.g. {missing[:3]}"
    )
    assert not missing, f"lost records: {missing[:5]}"


def test_concurrent_appends_lose_nothing_and_tear_nothing(tmp_path: Path) -> None:
    """Both clauses, against the real script.

    Note what this does and does not establish. The design's guarantee is OWNERSHIP — one writer per
    file for life — so this scenario is one the design says never happens. Exercising it anyway
    is the point: it is the only way to show the append primitive itself is sound, which is what
    makes single-owner a second line of defence rather than the only one. The residual, stated: a
    single `write()` of a line larger than the platform's atomic bound could still tear, and POSIX
    guarantees nothing here for regular files. These records are ~350 bytes."""
    ledger, attempted, lines = _race(tmp_path, APPEND)
    _clause_a_no_torn_or_interleaved(lines)
    _clause_b_nothing_lost(lines, attempted)
    assert _run(APPEND, "validate", str(ledger)).returncode == 0


def test_mutant_read_modify_write_reds_clause_b_while_clause_a_stays_green(tmp_path: Path) -> None:
    """The whole reason clause (b) was added. If reintroducing read-modify-write reds nothing, or
    reds clause (a) too, then clause (b) is not the thing catching it."""
    mutant = _mutant(tmp_path, PLAIN_APPEND, READ_MODIFY_WRITE)
    ledger, attempted, lines = _race(tmp_path / "race", mutant)

    # (a) still green: temp-then-rename never tears and never interleaves. This assertion is the
    # load-bearing half of the mutant — it is what shows the ORIGINAL oracle was blind.
    _clause_a_no_torn_or_interleaved(lines)

    # (b) red: records were silently lost.
    with pytest.raises(AssertionError, match="records read back"):
        _clause_b_nothing_lost(lines, attempted)


# ---------------------------------------------------------------------------
# Identity — the property that makes the scenario above one the design never reaches.
# ---------------------------------------------------------------------------
def test_concurrent_processes_mint_distinct_run_ids_and_distinct_files(tmp_path: Path) -> None:
    """Identity is minted per session to stop two SESSIONS sharing a file. Per-session alone does
    not stop two PROCESSES in one session sharing one, which is why the id carries the pid. Run
    them under one session id to prove exactly that case."""
    procs = [
        subprocess.Popen(
            ["/bin/bash", str(RUN), "run-id", "--phase", "p1"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env={**os.environ, "PLC_SESSION_ID": "one-and-the-same-session", "PLC_RUN_ID": ""},
        )
        for _ in range(WRITERS)
    ]
    ids = []
    for p in procs:
        out, err = p.communicate()
        assert p.returncode == 0, err
        ids.append(out.strip())
    assert len(set(ids)) == len(ids), f"two processes in one session minted the same id: {ids}"

    paths = {
        _run(RUN, "ledger-path", i, "--repo-root", str(tmp_path)).stdout.strip() for i in ids
    }
    assert len(paths) == len(ids), f"distinct ids collapsed onto the same file: {sorted(paths)}"
    # Same session token on every id, so the session grouping survives the pid suffix.
    tokens = {i.split("-")[1] for i in ids}
    assert len(tokens) == 1 and tokens != {"nosess"}, ids


def test_run_id_honours_an_exported_id_and_refuses_to_guess(tmp_path: Path) -> None:
    assert _run(RUN, "run-id", "--phase", "p1", env={"PLC_RUN_ID": "fixed-1"}).stdout.strip() == "fixed-1"
    bare = _run(RUN, "run-id", env={"PLC_RUN_ID": ""})
    assert bare.returncode == 2 and "--phase is required" in bare.stderr
    unsafe = _run(RUN, "run-id", "--phase", "../p1", env={"PLC_RUN_ID": ""})
    assert unsafe.returncode == 2 and "filename-safe" in unsafe.stderr


def test_ledger_path_refuses_a_run_id_that_could_leave_its_directory(tmp_path: Path) -> None:
    """Refused, never sanitised: silently rewriting an identifier makes two runs collide, which is
    a worse outcome than the error."""
    for bad in ("../evil", "a/b", "..", "with space"):
        result = _run(RUN, "ledger-path", bad, "--repo-root", str(tmp_path))
        assert result.returncode == 2, f"{bad!r} was accepted: {result.stdout}"
    good = _run(RUN, "ledger-path", "p1-nosess-1-2", "--repo-root", str(tmp_path))
    assert good.returncode == 0
    assert good.stdout.strip() == str(tmp_path / ".claude/.gate-runs/ledger/p1-nosess-1-2.jsonl")


# ---------------------------------------------------------------------------
# attempt_id — minted by the sole owner, and checked as a SEQUENCE rather than as uniqueness.
# ---------------------------------------------------------------------------
def _append(impl: Path, ledger: Path, stage: str, attempt: str, **over: str):
    argv = [
        "append", "--file", str(ledger), "--run-id", "r1", "--repo-id", "x", "--phase", "p1",
        "--stage-id", stage, "--attempt-id", attempt, "--type", "stage_observation",
        "--status", "done", "--observed", "true", "--observer", "scan",
        "--started-at", "2026-08-13T10:00:00Z", "--completed-at", "2026-08-13T10:00:01Z",
    ]
    for key, value in over.items():
        argv += ["--" + key.replace("_", "-"), value]
    return _run(impl, *argv)


def test_next_attempt_counts_per_stage_and_starts_at_one(tmp_path: Path) -> None:
    ledger = tmp_path / "l.jsonl"
    assert _run(RUN, "next-attempt", str(ledger), "qa_log").stdout.strip() == "1"
    for expected in ("1", "2", "3"):
        got = _run(RUN, "next-attempt", str(ledger), "qa_log").stdout.strip()
        assert got == expected, f"wanted {expected}, got {got}"
        assert _append(APPEND, ledger, "qa_log", got).returncode == 0
    # A different stage has its own counter — a shared one would make every stage's second attempt
    # look like a retry of whichever stage went first.
    assert _run(RUN, "next-attempt", str(ledger), "journal").stdout.strip() == "1"


def _assert_gap_is_rejected(impl: Path, tmp_path: Path) -> None:
    ledger = tmp_path / "gap.jsonl"
    for attempt in ("1", "2", "5"):
        assert _append(APPEND, ledger, "qa_log", attempt).returncode == 0
    result = _run(impl, "validate", str(ledger))
    assert result.returncode != 0, "a gap in the attempt sequence was accepted"
    assert "expected 1..3 contiguous" in result.stderr, result.stderr


def _assert_reuse_is_rejected(impl: Path, tmp_path: Path) -> None:
    ledger = tmp_path / "reuse.jsonl"
    for attempt in ("1", "2", "1"):
        assert _append(APPEND, ledger, "qa_log", attempt).returncode == 0
    result = _run(impl, "validate", str(ledger))
    assert result.returncode != 0, "a reused attempt_id was accepted"
    assert "goes backwards" in result.stderr, result.stderr


def test_a_gap_in_the_attempt_sequence_is_rejected(tmp_path: Path) -> None:
    _assert_gap_is_rejected(APPEND, tmp_path)


def test_a_reused_attempt_id_is_rejected(tmp_path: Path) -> None:
    _assert_reuse_is_rejected(APPEND, tmp_path)


def test_two_records_about_the_same_attempt_are_legal(tmp_path: Path) -> None:
    """The record contract's explicit case: a `running` record and the `done` record that finishes the SAME attempt
    share an id, and both are kept. A naive "unique per (run_id, stage_id)" check reads that as a
    collision and reds on correct data — which is why the file-level rule is about the SEQUENCE."""
    ledger = tmp_path / "l.jsonl"
    assert _append(APPEND, ledger, "qa_log", "1", status="running", type="stage_claim",
                   observed="false", completed_at="").returncode == 0
    assert _append(APPEND, ledger, "qa_log", "1").returncode == 0
    result = _run(APPEND, "validate", str(ledger))
    assert result.returncode == 0, result.stderr


def test_mutant_dropped_contiguity_clause_reds_the_gap_assertion(tmp_path: Path) -> None:
    mutant = _mutant(
        tmp_path,
        '      | [ (if $f != [range(1; ($f | length) + 1)]\n',
        "      | [ (if false\n",
    )
    with pytest.raises(AssertionError):
        _assert_gap_is_rejected(mutant, tmp_path / "m1")


def test_mutant_dropped_monotonic_clause_reds_the_reuse_assertion(tmp_path: Path) -> None:
    """Aimed at the OTHER clause, because a gap and a reuse are different defects: (1, 3) means a
    record was lost, (1, 2, 1) means an id was handed out twice. Neither check implies the other."""
    mutant = _mutant(
        tmp_path,
        "          (if (all(range(0; ($seq | length) - 1); $seq[.] <= $seq[.+1]) | not)\n",
        "          (if false\n",
        name="mutant2.sh",
    )
    with pytest.raises(AssertionError):
        _assert_reuse_is_rejected(mutant, tmp_path / "m2")


def test_attempt_check_is_skipped_loudly_when_a_line_does_not_parse(tmp_path: Path) -> None:
    """Silence here would report the parse failure a second time under a heading about attempt
    numbering, naming the wrong defect."""
    ledger = tmp_path / "broken.jsonl"
    assert _append(APPEND, ledger, "qa_log", "1").returncode == 0
    with ledger.open("a") as handle:
        handle.write("not json\n")
    result = _run(APPEND, "validate", str(ledger))
    assert result.returncode != 0
    assert "not valid JSON" in result.stderr
    assert "attempt-sequence check skipped" in result.stderr


def test_a_ledger_path_is_not_handed_out_when_its_ownership_claim_cannot_persist(tmp_path: Path) -> None:
    """A `|| true` one step too far.

    `ledger-path` refuses a second live owner — that is the single-writer guarantee. But the stamp
    that makes the claim was written with `|| true`, so when it could not land the function still
    returned exit 0 and a path. Both callers honour only "non-zero or empty stdout", so they wrote
    a ledger nobody owned while believing otherwise.

    Fail-open is deliberate in this system, and this is where it was applied one step too broadly:
    the point of fail-open is that a bookkeeping failure costs a RECORD, and here it was costing
    the guarantee while still writing the record."""
    root = tmp_path / "repo"
    ledger_dir = root / ".claude/.gate-runs/ledger"
    ledger_dir.mkdir(parents=True)
    # A directory where the owner stamp wants to be: the stamp cannot be written, and nothing else
    # about the tree is unusual — the ledger directory itself stays writable, which is what made
    # the old behaviour write a real record.
    (ledger_dir / ".blocked.owner").mkdir()

    blocked = _run(RUN, "ledger-path", "blocked", "--repo-root", str(root),
                   "--owner-pid", str(os.getpid()))
    assert blocked.returncode != 0, (
        f"handed out {blocked.stdout.strip()!r} while the ownership claim had not persisted"
    )
    assert blocked.stdout.strip() == "", (
        "a caller that checks stdout would still have taken this path"
    )
    assert "did not persist" in blocked.stderr, blocked.stderr

    # Control: the same call one name over still works, so this is a refusal about the claim and
    # not a tree that is simply unusable.
    fine = _run(RUN, "ledger-path", "fine", "--repo-root", str(root),
                "--owner-pid", str(os.getpid()))
    assert fine.returncode == 0, fine.stderr
    assert fine.stdout.strip().endswith("/fine.jsonl")


def test_an_unreadable_owner_stamp_is_not_the_same_as_no_owner(tmp_path: Path) -> None:
    """An ownership stamp that EXISTS and cannot be READ is an unanswered question,
    not an absence — and treating it as absence overwrote a live owner's claim and handed out the
    path. Same trade as the claim-persistence test above: fail-open must cost the record, never the
    guarantee."""
    root = tmp_path / "repo"
    ledger_dir = root / ".claude/.gate-runs/ledger"
    ledger_dir.mkdir(parents=True)
    stamp = ledger_dir / ".probe.owner"
    stamp.write_text("999999\n")
    stamp.chmod(0o200)          # write-only: it exists, and it cannot be read
    try:
        result = _run(RUN, "ledger-path", "probe", "--repo-root", str(root),
                      "--owner-pid", str(os.getpid()))
        assert result.returncode != 0, (
            f"handed out {result.stdout.strip()!r} without knowing who owns it"
        )
        assert result.stdout.strip() == ""
        assert "cannot be read" in result.stderr, result.stderr
    finally:
        stamp.chmod(0o644)

    # Control: readable stamp, dead owner -> reclaimable, as before.
    stamp.write_text("999999\n")
    ok = _run(RUN, "ledger-path", "probe", "--repo-root", str(root),
              "--owner-pid", str(os.getpid()))
    assert ok.returncode == 0, ok.stderr
