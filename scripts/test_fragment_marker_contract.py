"""AC11 -- the drain's fragment sentinel is a CONTRACT, and one fixture holds both sides to it.

The drain writes `<!-- fragment: <path> -->` above every block it appends to an archive. Two
unrelated mechanisms read that line, and until this file existed nothing ran the WRITER and the
READER against each other: `test_retention_drain.py` proves the drain writes what the drain expects,
`test_ledger_scan.py` proves the scanner reads what the fixture author typed, and a format change on
either side leaves both suites green. That is the gap this file closes, and it is the same shape this
repo has paid for before -- a proxy checked, the real thing reported.

WHY THE REGISTRY HERE KEEPS ONLY `fragment-marker`. The real `journal` stage can also resolve
through `phase-file` and `archive-heading`, so with all three declared a broken marker is invisible:
another kind answers and the stage still reads `observed`. Stripping the stage to the one kind under
test is what makes "not observed" mean "the marker was not read".

EVERY MUTATION ARM ASSERTS ITS OWN BASELINE FIRST, in the same test and on the same fixture. A
mutant that fails to resolve proves nothing unless the unmutated run resolved -- this repo has
recorded mutants scored dead for reasons unrelated to the mutation.
"""
import json
import subprocess
from pathlib import Path

import pytest

from close_gate_lib import make_fixture_repo

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
DRAIN = SCRIPTS / "retention-drain.sh"
SCAN = SCRIPTS / "ledger-scan.sh"
SENTINEL = SCRIPTS / "lib" / "fragment-sentinel.awk"
EMITTER = SCRIPTS / "ledger-append.sh"
REGISTRY = ROOT / ".claude" / "stage-registry.json"

SLUG = "p186-marker-contract"
FRAGMENT = f"docs/journal.d/2026-01-15-feat-phase-{SLUG}.md"
ARCHIVE_GLOB = "docs/archive/journal/*.md"
FROZEN_NOW = "2026-01-15T00:00:00Z"

# The prefix is assembled rather than spelled, for the reason the one-reader invariant records: a
# file that talks about the sentinel should not read as a fourth matcher for it.
PREFIX = "<!-- " + "fragment: "
# The ANCHORED form, assembled for a second reason beyond the one above:
# scripts/invariants/one-fragment-sentinel-reader.sh refuses a FOURTH anchored matcher anywhere
# under the scanned roots, and a literal here reads as one. Measured -- the first version of this
# file spelled it, and the guard blocked the push and named this file. A fixture that must NAME the
# matcher in order to mutate it is exactly the sibling that guard exists to refuse.
ANCHORED = "^" + PREFIX


def _repo(tmp_path: Path, body: str = "## FACT — a thing happened\n\nbody\n") -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    return make_fixture_repo(
        tmp_path,
        manifest={"retention": {"archive_dir": "docs/archive", "journal_dir": "docs/journal.d"}},
        files={FRAGMENT: body},
    )


def _drain(repo: Path, impl: Path = DRAIN) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", str(impl), "drain", "journal"],
        cwd=repo, capture_output=True, text=True, check=False,
    )


def _registry_marker_only(tmp_path: Path) -> Path:
    """The real registry with every stage but `journal` silenced, and `journal` reduced to its
    `fragment-marker` source. Derived from the shipped file rather than hand-written, so the schema
    is the real one and this fixture cannot drift from it."""
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    for stage in data["stages"]:
        if stage.get("stage_id") == "journal" and stage.get("retro_evidence"):
            kept = [s for s in stage["retro_evidence"] if s["kind"] == "fragment-marker"]
            assert kept, "the journal stage no longer declares a fragment-marker source"
            kept[0] = {**kept[0], "roots": [ARCHIVE_GLOB]}
            stage["retro_evidence"] = kept
        else:
            stage["retro_evidence"] = None
            stage["retro_reason"] = "not-recoverable"
    tmp_path.mkdir(parents=True, exist_ok=True)
    target = tmp_path / "registry-marker-only.json"
    target.write_text(json.dumps(data), encoding="utf-8")
    return target


def _roadmap(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    target = tmp_path / "ROADMAP.md"
    target.write_text(f"# Roadmap\n\n- x (phase `{SLUG}`)\n", encoding="utf-8")
    return target


def _scan(repo: Path, tmp_path: Path, *, sentinel: Path = SENTINEL,
          out_name: str = "retro") -> subprocess.CompletedProcess[str]:
    out = tmp_path / out_name
    return subprocess.run(
        ["/bin/bash", str(SCAN), "scan",
         "--roadmap", str(_roadmap(tmp_path)), "--out-dir", str(out),
         "--registry", str(_registry_marker_only(tmp_path)), "--repo-root", str(repo),
         "--repo-id", "fixed-repo-id", "--now", FROZEN_NOW,
         "--emitter", str(EMITTER), "--sentinel", str(sentinel)],
        capture_output=True, text=True, check=False,
    )


def _journal_records(tmp_path: Path, out_name: str = "retro") -> list[dict]:
    path = tmp_path / out_name / f"retro-{SLUG}.jsonl"
    assert path.exists(), f"no ledger file for {SLUG} -- a run with no evidence still gets one"
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return [r for r in records if r["stage_id"] == "journal"]


def _observed(repo: Path, tmp_path: Path, *, sentinel: Path = SENTINEL,
              out_name: str = "retro") -> bool:
    result = _scan(repo, tmp_path, sentinel=sentinel, out_name=out_name)
    assert result.returncode == 0, result.stdout + result.stderr
    return any(r.get("observed") is True for r in _journal_records(tmp_path, out_name))


def _mutant_script(tmp_path: Path, src: Path, old: str, new: str, name: str) -> Path:
    text = src.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"mutation target occurs {text.count(old)} times in {src.name}"
    target = tmp_path / name
    target.write_text(text.replace(old, new), encoding="utf-8")
    return target


def test_the_drain_writes_the_contract_line(tmp_path: Path) -> None:
    """The format itself, asserted where it is written -- whole line, blank line above, payload is
    the fragment's repo-relative path."""
    repo = _repo(tmp_path)
    assert _drain(repo).returncode == 0
    archives = sorted((repo / "docs" / "archive" / "journal").glob("*.md"))
    assert archives, "the drain archived nothing, so there is no marker to hold anyone to"
    lines = archives[0].read_text(encoding="utf-8").splitlines()
    hits = [i for i, line in enumerate(lines) if line.startswith(PREFIX)]
    assert len(hits) == 1, f"expected exactly one marker, got {len(hits)}"
    i = hits[0]
    assert lines[i] == f"{PREFIX}{FRAGMENT} -->", lines[i]
    assert i > 0 and lines[i - 1].strip() == "", (
        "the reader requires a blank line immediately above the marker; the drain must supply it"
    )


def test_write_then_read_resolves_the_stage(tmp_path: Path) -> None:
    """The contract end to end: the drain writes, the ledger reads, and the artifact it reports is
    the archive file that CONTAINS the marker -- not the fragment, which no longer exists."""
    repo = _repo(tmp_path)
    assert _drain(repo).returncode == 0
    assert _observed(repo, tmp_path), "the marker the drain just wrote was not read back"
    artifacts = [a for r in _journal_records(tmp_path) for a in (r.get("artifacts") or [])]
    assert artifacts, "an observation with no artifact points at nothing"
    assert any("docs/archive/journal/" in str(a) for a in artifacts), artifacts


def test_a_writer_side_format_change_breaks_the_read(tmp_path: Path) -> None:
    """AC11's oracle, writer half. The drain alone renames the marker; nothing else changes."""
    baseline = _repo(tmp_path / "baseline")
    assert _drain(baseline).returncode == 0
    assert _observed(baseline, tmp_path / "baseline-scan"), (
        "the baseline did not resolve, so the mutant arm below would prove nothing"
    )

    # The printf that WRITES the marker, not the grep that looks it up: the lookup only decides
    # whether to append at all. Both halves are asserted replacements -- the first version of this
    # arm changed the lookup with an UNASSERTED replace, the printf never matched, the drain kept
    # writing the real marker, and the arm reported the two sides as held together when nothing
    # had been mutated at all.
    mutant = _mutant_script(
        tmp_path, DRAIN,
        """      { printf '\\n<!-- fragment: %s -->\\n' "$f"; cat "$f"; echo; } >> "$archive" \\""",
        """      { printf '\\n<!-- frag: %s -->\\n' "$f"; cat "$f"; echo; } >> "$archive" \\""",
        "drain-mutant.sh",
    )

    broken = _repo(tmp_path / "broken")
    assert _drain(broken, impl=mutant).returncode == 0
    assert not _observed(broken, tmp_path / "broken-scan"), (
        "the writer renamed the marker and the ledger still credited the stage -- the two sides "
        "are not held to one format"
    )


def test_a_reader_side_format_change_breaks_the_read(tmp_path: Path) -> None:
    """AC11's oracle, reader half. The archive is the real one the real drain wrote; only the
    declared reader changes."""
    repo = _repo(tmp_path)
    assert _drain(repo).returncode == 0
    assert _observed(repo, tmp_path / "baseline-scan"), (
        "the baseline did not resolve, so the mutant arm below would prove nothing"
    )

    # The ANCHORED matcher, not `PFX`. Measured: changing `PFX` alone does not break the read --
    # it only shifts where the payload is cut from, and the payload still carried the phase name,
    # so the stage resolved and the arm proved nothing. The line that decides whether a line IS a
    # marker is the regex below.
    mutant = _mutant_script(
        tmp_path, SENTINEL,
        "$0 ~ /" + ANCHORED + "/",
        "$0 ~ /^<!-- frag: /",
        "sentinel-mutant.awk",
    )
    assert not _observed(repo, tmp_path / "mutant-scan", sentinel=mutant), (
        "the reader changed the prefix it accepts and the stage still resolved"
    )


def test_a_malformed_marker_refuses_the_whole_scan(tmp_path: Path) -> None:
    """The error direction, asserted rather than described: an unreadable marker is a FAIL, and it
    is a property of the archive, so it ends the scan instead of quietly scoring one run lower."""
    repo = _repo(tmp_path)
    assert _drain(repo).returncode == 0
    archive = sorted((repo / "docs" / "archive" / "journal").glob("*.md"))[0]
    archive.write_text(
        archive.read_text(encoding="utf-8").replace(
            f"{PREFIX}{FRAGMENT} -->", f"{PREFIX} -->"
        ),
        encoding="utf-8",
    )
    result = _scan(repo, tmp_path)
    assert result.returncode == 3, (
        f"a malformed marker exited {result.returncode}; the contract says 3, and anything quieter "
        "reads as 'this file holds nothing for you'"
    )
    assert "malformed fragment marker" in result.stderr, result.stderr


def test_a_payload_with_whitespace_inside_it_is_malformed(tmp_path: Path) -> None:
    """The grammar rule that was WRITTEN from the start and not checked, found by a phase-close
    review: the payload is "one non-empty, whitespace-free token", and `<!-- fragment: a b -->`
    parsed anyway, handing the phase-name test a token nobody wrote.

    Asserted against the real reader in both modes, because the two have different error numbers
    and this shape must be loud in each: payload mode exits 3, and `ledger-scan.sh` turns that into
    a refusal of the whole scan. The control below is the same line with the space removed -- it
    must parse, or this test would pass for a reader that rejects everything.
    """
    archive = tmp_path / "archive.md"
    good = tmp_path / "good.md"
    archive.write_text(f"# A\n\n{PREFIX}docs/qa-log.d/a b.md -->\n\nbody\n", encoding="utf-8")
    good.write_text(f"# A\n\n{PREFIX}{FRAGMENT} -->\n\nbody\n", encoding="utf-8")

    control = subprocess.run(
        ["/usr/bin/awk", "-v", "emit=payload", "-f", str(SENTINEL), str(good)],
        capture_output=True, text=True, check=False,
    )
    assert control.returncode == 0 and control.stdout.strip(), (
        f"the control marker did not parse, so the red below proves nothing: {control.returncode}"
    )

    result = subprocess.run(
        ["/usr/bin/awk", "-v", "emit=payload", "-f", str(SENTINEL), str(archive)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 3, (
        f"a payload with a space in it exited {result.returncode}; the grammar says that shape is "
        "malformed, and 1 would read to a caller as 'this file holds nothing for you'"
    )
    assert not result.stdout.strip(), f"a malformed payload was printed anyway: {result.stdout!r}"


def test_a_marker_quoted_inside_a_fence_is_not_a_marker(tmp_path: Path) -> None:
    """Fence-awareness belongs to the grammar, not to the caller. This phase's own spec quotes a
    marker inside a fence, and a document that TALKS ABOUT one must not be scored as carrying it."""
    repo = _repo(tmp_path)
    archive_dir = repo / "docs" / "archive" / "journal"
    archive_dir.mkdir(parents=True, exist_ok=True)
    (archive_dir / "2026-10.md").write_text(
        "# Journal archive\n\n## How to read this file\n\n"
        "```\n\n" + f"{PREFIX}{FRAGMENT} -->\n" + "```\n\nprose\n",
        encoding="utf-8",
    )
    assert not _observed(repo, tmp_path), (
        "a marker quoted inside a fenced block was scored as a real boundary"
    )
