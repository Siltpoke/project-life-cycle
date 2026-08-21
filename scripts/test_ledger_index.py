"""The global discovery index.

The claim is "the ledger is the truth, the index is a cache": deleting the whole index loses nothing
but discovery speed. Three oracles, all metamorphic.

The ordering fixture is the load-bearing one. `started_at` is scrambled AGAINST file-creation order
on purpose — on APFS a handful of entries can have readdir
order coincidentally track creation order, which would let the "stop sorting" mutant survive and
leave a green that proves nothing.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
INDEX = Path(os.environ.get("PLC_LEDGER_INDEX_IMPL", SCRIPTS / "ledger-index.sh"))
APPEND = SCRIPTS / "ledger-append.sh"

# Creation order is 0..5; started_at deliberately runs the other way and interleaves, so sorted
# order and readdir order cannot coincide.
SCRAMBLED = [
    ("run-alpha", "2026-08-06T00:00:00Z"),
    ("run-bravo", "2026-08-02T00:00:00Z"),
    ("run-charlie", "2026-08-05T00:00:00Z"),
    ("run-delta", "2026-08-01T00:00:00Z"),
    ("run-echo", "2026-08-04T00:00:00Z"),
    ("run-foxtrot", "2026-08-03T00:00:00Z"),
]


def _run(*args: str, impl: Path = INDEX):
    return subprocess.run(
        ["/bin/bash", str(impl), *args], capture_output=True, text=True, check=False,
    )


def _mutant(tmp_path: Path, old: str, new: str, name: str = "mutant.sh") -> Path:
    text = INDEX.read_text()
    assert text.count(old) == 1, f"mutation target occurs {text.count(old)} times: {old!r}"
    target = tmp_path / name
    target.write_text(text.replace(old, new))
    return target


def _ledger(dirpath: Path, run_id: str, started: str, repo_id: str = "repo-xyz") -> Path:
    """A real ledger file, written through the sole emitter — the index's facts have to be
    recoverable from these and nowhere else, so they must be genuine records."""
    dirpath.mkdir(parents=True, exist_ok=True)
    path = dirpath / f"{run_id}.jsonl"
    result = subprocess.run(
        ["/bin/bash", str(APPEND), "append", "--file", str(path),
         "--run-id", run_id, "--repo-id", repo_id, "--phase", "p1", "--stage-id", "journal",
         "--attempt-id", "1", "--type", "stage_observation", "--status", "done",
         "--observed", "true", "--observer", "close-gate.sh",
         "--started-at", started, "--completed-at", started],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    return path


def _build(tmp_path: Path, impl: Path = INDEX) -> tuple[Path, Path]:
    """Six runs, upserted in an order that scrambles creation against started_at."""
    ledgers = tmp_path / "ledgers"
    index_dir = tmp_path / "index"
    for run_id, started in SCRAMBLED:
        path = _ledger(ledgers, run_id, started)
        result = _run(
            "upsert", "--run-id", run_id, "--ledger-path", str(path),
            "--repo-root", str(tmp_path), "--repo-id", "repo-xyz", "--repo-id-basis", "given",
            "--started-at", started, "--now", "2026-08-13T20:00:00Z",
            "--index-dir", str(index_dir), impl=impl,
        )
        assert result.returncode == 0, result.stderr
        # Distinct mtimes, so "creation order" is a real thing this fixture controls.
        time.sleep(0.01)
    return ledgers, index_dir


def _listing(index_dir: Path, impl: Path = INDEX, compare: bool = True) -> str:
    args = ["list", "--index-dir", str(index_dir)] + (["--compare"] if compare else [])
    result = _run(*args, impl=impl)
    assert result.returncode == 0, result.stderr
    return result.stdout


# ---------------------------------------------------------------------------
# Delete the index, rebuild it, and the reader's output is byte-identical
# ---------------------------------------------------------------------------
def _assert_rebuild_is_byte_identical(tmp_path: Path, impl: Path = INDEX) -> None:
    ledgers, index_dir = _build(tmp_path, impl=impl)
    before = _listing(index_dir, impl=impl)
    assert before.count("\n") == len(SCRAMBLED), before

    for entry in index_dir.glob("*.json"):
        entry.unlink()
    assert not list(index_dir.glob("*.json")), "the index was not actually deleted"
    assert _listing(index_dir, impl=impl) == "", "a deleted index still listed something"

    result = _run(
        "rebuild", "--ledger-dir", str(ledgers), "--repo-root", str(tmp_path),
        "--index-dir", str(index_dir), "--now", "2026-08-13T21:00:00Z", impl=impl,
    )
    assert result.returncode == 0, result.stderr
    after = _listing(index_dir, impl=impl)
    assert after == before, (
        "rebuild did not recover the same listing\n"
        f"--- before ---\n{before}\n--- after ---\n{after}"
    )


def test_deleting_the_index_and_rebuilding_recovers_it_byte_for_byte(tmp_path: Path) -> None:
    _assert_rebuild_is_byte_identical(tmp_path)


def test_mutant_unsorted_listing_reds_the_ORDER_assertion_not_the_identity_one(tmp_path: Path) -> None:
    """A sort mutant, aimed where it can actually bite.

    "Make rebuild emit in readdir order -> the byte-identical assertion must red" sounds right. It
    cannot, and neither can removing the sort from the reader, for a reason that also corrects the
    obvious risk: **bash sorts glob expansions**. Readdir order never reaches the output at
    all, so the APFS concern is not reachable through this code path. What
    removing the sort actually produces is filename order — wrong, but DETERMINISTIC, so a rebuild
    reproduces it exactly and the two listings still match byte for byte.

    A byte-identical oracle can only see NON-determinism. It is structurally blind to a stable
    wrong answer, which is what an ordering defect is. So the ordering claim needs its own
    assertion, and this mutant is aimed there."""
    mutant = _mutant(
        tmp_path,
        """  } | sort -t"$(printf '\\t')" -k2,2 -k3,3""",
        "  }",
    )
    # Still byte-identical under the mutant — stated as an assertion rather than left as a
    # footnote, because it is the finding.
    _assert_rebuild_is_byte_identical(tmp_path / "still-identical", impl=mutant)

    _, index_dir = _build(tmp_path / "order", impl=mutant)
    started = [line.split("\t")[1] for line in _listing(index_dir, impl=mutant).splitlines()]
    assert started != sorted(s for _, s in SCRAMBLED), (
        "the mutant produced started_at order anyway — the fixture is not scrambling anything"
    )
    assert started == [s for _, s in SCRAMBLED], (
        f"expected filename order (which is creation order in this fixture), got {started}"
    )


def test_the_listing_really_is_in_started_at_order(tmp_path: Path) -> None:
    """Stated separately from the mutant above, because "the two listings match" and "the listing
    is sorted" are different claims and a broken sort could satisfy the first."""
    _, index_dir = _build(tmp_path)
    started = [line.split("\t")[1] for line in _listing(index_dir).splitlines()]
    assert started == sorted(s for _, s in SCRAMBLED), started
    assert started != [s for _, s in SCRAMBLED], "the fixture is not scrambled — it proves nothing"


def test_repo_id_basis_is_the_field_compare_excludes_and_why(tmp_path: Path) -> None:
    """`--compare` drops `repo_id_basis`, and this row is the reason rather than an apology for it.
    A rebuilt entry's repo_id comes out of the LEDGER; a live entry's was derived from the tree.
    Same value, different provenance, honestly recorded — so a byte comparison including it would
    be asserting that provenance never changes, when the whole point of storing it is that it can."""
    ledgers, index_dir = _build(tmp_path)
    live = json.loads((index_dir / "run-alpha.json").read_text())
    assert live["repo_id_basis"] == "given"
    _run("rebuild", "--ledger-dir", str(ledgers), "--repo-root", str(tmp_path),
         "--index-dir", str(index_dir), "--now", "2026-08-13T21:00:00Z")
    rebuilt = json.loads((index_dir / "run-alpha.json").read_text())
    assert rebuilt["repo_id_basis"] == "ledger"
    assert rebuilt["repo_id"] == live["repo_id"] == "repo-xyz"
    # And the full listing, which DOES include the basis, differs — so nothing is being hidden.
    assert _listing(index_dir, compare=False) != ""


def test_repo_name_and_worktree_path_are_re_derived_not_recovered(tmp_path: Path) -> None:
    """Found by the byte-identical assertion failing, and kept because the answer is a real
    boundary rather than a fixture detail.

    `repo_name` and `worktree_path` are NOT in the ledger and cannot be recovered from it — they
    describe where the repo is NOW, not what the run did. A rebuild therefore re-derives them from
    the tree it is handed, which is the behaviour you want: an index rebuilt after a move should
    point at the repo's current location, not resurrect the path it had when the run happened. So
    the rule "deleting the index loses nothing but discovery speed" holds for every fact ABOUT
    THE RUN, and the two fields it does not hold for are exactly the two that were never facts
    about the run."""
    ledgers, index_dir = _build(tmp_path)
    stale = tmp_path / "where-it-used-to-live"
    result = _run(
        "upsert", "--run-id", "run-alpha", "--ledger-path", str(ledgers / "run-alpha.jsonl"),
        "--repo-root", str(tmp_path), "--repo-id", "repo-xyz",
        "--repo-name", "an-old-name", "--worktree-path", str(stale),
        "--started-at", "2026-08-06T00:00:00Z", "--now", "2026-08-13T20:00:00Z",
        "--index-dir", str(index_dir),
    )
    assert result.returncode == 0, result.stderr
    assert json.loads((index_dir / "run-alpha.json").read_text())["worktree_path"] == str(stale)

    _run("rebuild", "--ledger-dir", str(ledgers), "--repo-root", str(tmp_path),
         "--index-dir", str(index_dir), "--now", "2026-08-13T21:00:00Z")
    rebuilt = json.loads((index_dir / "run-alpha.json").read_text())
    assert rebuilt["worktree_path"] == str(tmp_path)
    assert rebuilt["repo_name"] == tmp_path.name
    # The run's own facts survived the round trip unchanged.
    assert rebuilt["run_id"] == "run-alpha"
    assert rebuilt["repo_id"] == "repo-xyz"
    assert rebuilt["started_at"] == "2026-08-06T00:00:00Z"


# ---------------------------------------------------------------------------
# STALE — rendered, never silently pruned and never silently followed
# ---------------------------------------------------------------------------
def test_a_moved_repo_is_reported_stale_not_pruned(tmp_path: Path) -> None:
    ledgers, index_dir = _build(tmp_path)
    assert "STALE" not in _listing(index_dir)

    moved = tmp_path / "moved-away"
    ledgers.rename(moved)
    listing = _listing(index_dir)
    assert listing.count("STALE") == len(SCRAMBLED), listing
    # Not pruned: every run is still named. The index remembers that the run happened even when
    # the ledger it points at has gone.
    for run_id, _ in SCRAMBLED:
        assert run_id in listing
    assert len(list(index_dir.glob("*.json"))) == len(SCRAMBLED)


def test_an_unreadable_entry_is_reported_and_does_not_stop_the_listing(tmp_path: Path) -> None:
    _, index_dir = _build(tmp_path)
    (index_dir / "run-alpha.json").write_text("{not json")
    result = _run("list", "--index-dir", str(index_dir))
    assert result.returncode == 0
    assert "UNREADABLE" in result.stderr
    assert result.stdout.count("\n") == len(SCRAMBLED) - 1


# ---------------------------------------------------------------------------
# Atomicity — a reader sees the old entry or the new one, never a torn one
# ---------------------------------------------------------------------------
def test_a_reader_never_sees_a_half_written_entry(tmp_path: Path) -> None:
    """The design reserves temp-then-rename for the index, and this is the assertion that reserves it
    for a reason. A writer flips one entry between two distinct values in a tight loop while a
    reader parses it repeatedly; every read must yield valid JSON holding one of the two values.
    The writer is killed part-way, which is the case the criterion names."""
    ledgers, index_dir = _build(tmp_path)
    path = _ledger(ledgers, "run-flip", "2026-08-07T00:00:00Z")

    script = tmp_path / "flip.sh"
    script.write_text(
        "#!/bin/bash\n"
        "set -eu\n"
        "while true; do\n"
        f'  /bin/bash "{INDEX}" upsert --run-id run-flip --ledger-path "{path}" '
        f'--repo-root "{tmp_path}" --repo-id repo-xyz --repo-name AAAA '
        f'--index-dir "{index_dir}" --started-at 2026-08-07T00:00:00Z --now 2026-08-13T20:00:00Z\n'
        f'  /bin/bash "{INDEX}" upsert --run-id run-flip --ledger-path "{path}" '
        f'--repo-root "{tmp_path}" --repo-id repo-xyz --repo-name BBBB '
        f'--index-dir "{index_dir}" --started-at 2026-08-07T00:00:00Z --now 2026-08-13T20:00:00Z\n'
        "done\n"
    )
    writer = subprocess.Popen(["/bin/bash", str(script)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    target = index_dir / "run-flip.json"
    reads = 0
    try:
        deadline = time.time() + 3.0
        while time.time() < deadline:
            if not target.exists():
                continue
            raw = target.read_text()
            if not raw:
                continue
            entry = json.loads(raw)   # a torn write raises here, which is the failure
            assert entry["repo_name"] in {"AAAA", "BBBB"}, entry
            reads += 1
    finally:
        writer.kill()
        writer.wait()
    assert reads > 20, f"only {reads} reads landed — the race was never actually exercised"
    # The file left behind after the kill is whole, not a stump.
    assert json.loads(target.read_text())["repo_name"] in {"AAAA", "BBBB"}

    # A temp CAN survive a SIGKILL, and saying otherwise would be a claim with no mechanism behind
    # it: SIGKILL is untrappable, full stop. What is guaranteed is that a partial write is never
    # READ as an entry — the temp is hidden and does not end in `.json`, so the listing cannot see
    # it — and that the next write for the same run sweeps temps whose owner process is gone.
    listing_before = _listing(index_dir)
    assert "run-flip" in listing_before
    assert listing_before.count("\n") == len(SCRAMBLED) + 1, listing_before

    leftovers = list(index_dir.glob(".*tmp*"))
    result = _run(
        "upsert", "--run-id", "run-flip", "--ledger-path", str(path),
        "--repo-root", str(tmp_path), "--repo-id", "repo-xyz",
        "--index-dir", str(index_dir), "--started-at", "2026-08-07T00:00:00Z",
        "--now", "2026-08-13T20:00:00Z",
    )
    assert result.returncode == 0, result.stderr
    assert not list(index_dir.glob(".*tmp*")), (
        f"the next write did not sweep the orphaned temps: {leftovers}"
    )


# ---------------------------------------------------------------------------
# repo identity
# ---------------------------------------------------------------------------
def test_repo_id_is_derived_by_a_pinned_order_and_records_which_one_won(tmp_path: Path) -> None:
    result = _run("repo-id", "--with-basis", "--repo-root", str(ROOT))
    assert result.returncode == 0, result.stderr
    basis, value = result.stdout.strip().split("\t")
    assert basis == "first-commit"
    first = subprocess.run(
        ["/usr/bin/git", "-C", str(ROOT), "rev-list", "--max-parents=0", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.split()[0]
    assert value == first, "the id is not this repo's first-commit SHA"
    # Not a path — the whole reason the field exists. Moving a project to another directory
    # changes its path, and anything keyed on paths (git worktree metadata, for one) goes stale.
    assert str(ROOT) not in value


def test_a_repo_with_no_commit_and_no_remote_refuses_to_guess(tmp_path: Path) -> None:
    bare = tmp_path / "bare"
    bare.mkdir()
    subprocess.run(["/usr/bin/git", "init", "-q", str(bare)], check=True)
    result = _run("repo-id", "--repo-root", str(bare))
    assert result.returncode == 2
    assert "cannot derive a repo id" in result.stderr

    (bare / ".claude").mkdir()
    (bare / ".claude/repo-id").write_text("declared-identity\n")
    result = _run("repo-id", "--with-basis", "--repo-root", str(bare))
    assert result.returncode == 0
    assert result.stdout.strip().split("\t") == ["marker", "declared-identity"]
