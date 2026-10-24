"""archive-working must MOVE, never delete — deletion is deferred until distill
quality is proven over 2-3 tracks.

Second surface: `drain_monolith`. Every fixture
below builds a throwaway repo under `tmp_path` and runs the real script against it —
nothing here touches the real repository's documents.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path

import pytest

from close_gate_lib import extract_retention_drain_script, make_fixture_repo

# Overridable so the suite can be mutation-tested without editing the tracked script — the gate
# invariant already had this selector and the suite did not, which is a large part of why an
# insensitive fixture in that invariant stayed invisible.
DRAIN = Path(
    os.environ.get("PLC_DRAIN_IMPL", Path(__file__).resolve().parent / "retention-drain.sh")
)
RETENTION_MD = (
    Path(__file__).resolve().parents[1]
    / "skills/project-lifecycle/references/retention.md"
)


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(DRAIN), *args], cwd=repo, capture_output=True, text=True, check=False
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_fixture_repo(
        tmp_path,
        manifest={"retention": {"archive_dir": "docs/archive"}},
        files={"docs/superpowers/specs/2026-07-13-foo-design.md": "body\n"},
    )


def test_archive_working_moves_the_file(repo: Path) -> None:
    result = _run(repo, "archive-working", "docs/superpowers/specs/2026-07-13-foo-design.md")
    assert result.returncode == 0, result.stdout + result.stderr
    src = repo / "docs/superpowers/specs/2026-07-13-foo-design.md"
    dst = repo / "docs/archive/working/superpowers/specs/2026-07-13-foo-design.md"
    assert not src.exists(), "source must be gone from the hot path"
    assert dst.read_text() == "body\n", "content must survive byte-for-byte"


def test_archive_working_is_idempotent(repo: Path) -> None:
    p = "docs/superpowers/specs/2026-07-13-foo-design.md"
    assert _run(repo, "archive-working", p).returncode == 0
    second = _run(repo, "archive-working", p)
    assert second.returncode == 0, "re-running on an already-archived path must not fail"
    assert (repo / "docs/archive/working/superpowers/specs/2026-07-13-foo-design.md").exists()


def test_archive_working_refuses_screenshots(repo: Path) -> None:
    shot = repo / "docs/pr-drafts/screenshots/01.png"
    shot.parent.mkdir(parents=True)
    shot.write_bytes(b"png")
    result = _run(repo, "archive-working", "docs/pr-drafts/screenshots/01.png")
    assert result.returncode != 0
    assert shot.exists(), "load-bearing PR screenshots must never be moved"


def test_archive_working_missing_file_is_a_real_failure(repo: Path) -> None:
    result = _run(repo, "archive-working", "docs/superpowers/specs/never-existed.md")
    assert result.returncode != 0, "a file that was never archived and doesn't exist must fail"


def test_archive_working_refuses_to_clobber_a_differing_archived_original(repo: Path) -> None:
    """A re-opened/re-created track whose spec/plan filename collides with an
    already-archived original must NOT be silently overwritten by a plain `mv` — that archived
    original is the sole evidence the deferred-deletion decision rests on. RED against
    the pre-fix script: this assertion fails because `mv -- "$src" "$dst"` has no `-n` and
    clobbers `$dst` unconditionally."""
    p = "docs/superpowers/specs/2026-07-13-foo-design.md"
    assert _run(repo, "archive-working", p).returncode == 0
    dst = repo / "docs/archive/working/superpowers/specs/2026-07-13-foo-design.md"
    original_content = dst.read_text()
    assert original_content == "body\n"

    # simulate a re-opened track: the same path is recreated with DIFFERENT content
    src = repo / p
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("a second round of work, not the original body\n")

    result = _run(repo, "archive-working", p)
    assert result.returncode != 0, "must refuse rather than overwrite a differing archived original"
    assert dst.read_text() == original_content, "the archived original must survive byte-for-byte"
    assert src.exists(), "the recreated source must be left in place, not consumed by a failed move"


def test_archive_working_byte_identical_dst_is_a_harmless_no_op(repo: Path) -> None:
    """Companion case: if `$dst` already exists and is byte-identical to `$src` (e.g. the
    cadence retried archive-working before deleting/using the recreated source), that is not
    the dangerous case — nothing would be lost — so it must succeed as a no-op, not refuse."""
    p = "docs/superpowers/specs/2026-07-13-foo-design.md"
    assert _run(repo, "archive-working", p).returncode == 0
    dst = repo / "docs/archive/working/superpowers/specs/2026-07-13-foo-design.md"

    # recreate the source with the EXACT same bytes as what was already archived
    src = repo / p
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(dst.read_text())

    result = _run(repo, "archive-working", p)
    assert result.returncode == 0, result.stdout + result.stderr
    assert dst.read_text() == "body\n"


def test_archive_working_handles_untracked_file(repo: Path) -> None:
    # Where docs/ is gitignored, PLC-minted spec/plan files are frequently untracked.
    # `git mv` fails outright on an untracked path — archive-working must not blow up here.
    untracked = repo / "docs/superpowers/specs/2026-07-13-untracked-bar.md"
    untracked.parent.mkdir(parents=True, exist_ok=True)
    untracked.write_text("untracked body\n")
    # Confirm the fixture is actually untracked before trusting the assertion below.
    status = subprocess.run(
        ["git", "status", "--porcelain", str(untracked)],
        cwd=repo, capture_output=True, text=True, check=True,
    )
    assert status.stdout.startswith("??"), "fixture setup must produce an untracked file"

    result = _run(repo, "archive-working", "docs/superpowers/specs/2026-07-13-untracked-bar.md")
    assert result.returncode == 0, result.stdout + result.stderr
    dst = repo / "docs/archive/working/superpowers/specs/2026-07-13-untracked-bar.md"
    assert not untracked.exists()
    assert dst.read_text() == "untracked body\n"


# --------------------------------------------------------------------------------------
# drain_monolith surface
# --------------------------------------------------------------------------------------

MONOLITH = "CHANGELOG.md"
ARCHIVE = "docs/archive/CHANGELOG-archive.md"

#: Oldest-first — the ordering `drain_monolith` was written for and the one AC2 pins.
CHRON_HEADINGS: tuple[str, ...] = (
    "[1.0.0] — 2026-01-01",
    "[1.1.0] — 2026-02-01",
    "[1.2.0] — 2026-03-01",
    "[1.3.0] — 2026-04-01",
    "[1.4.0] — 2026-05-01",
    "[1.5.0] — 2026-06-01",
)
#: Newest-first — the shape a Keep-a-Changelog CHANGELOG.md actually has.
REVERSE_CHRON_HEADINGS: tuple[str, ...] = tuple(reversed(CHRON_HEADINGS))


def monolith_body(headings: tuple[str, ...], header: str = "# Changelog\n\n") -> str:
    return header + "".join(f"## {h}\n\nbody of {h}\n\n" for h in headings)


def make_monolith_repo(
    tmp_path: Path,
    headings: tuple[str, ...],
    *,
    retention: dict | None = None,
    name: str = MONOLITH,
    header: str = "# Changelog\n\n",
) -> Path:
    """A fixture repo holding one monolith with N `## ` entries.

    `retention` is merged into the manifest's `retention` block, so a test declares only
    the keys it is about; `archive_dir` is always present because the script's own default
    would otherwise be the thing under test rather than the thing being held fixed.
    """
    manifest = {"retention": {"archive_dir": "docs/archive", **(retention or {})}}
    return make_fixture_repo(
        tmp_path, manifest=manifest, files={name: monolith_body(headings, header)}
    )


def entry_headings(text: str) -> list[str]:
    """Entry headings in file order, applying the script's own `## …Index` exclusion."""
    return [
        line[3:]
        for line in text.splitlines()
        if line.startswith("## ") and not line.rstrip().endswith("Index")
    ]


# AC2 golden. Captured from the PRE-CHANGE `retention-drain.sh` by running it on
# `CHRON_HEADINGS`. It is committed as a literal, not recomputed at test
# time, because a golden captured from the post-change script would make AC2's regression
# guard vacuous: it would only ever assert that the new code agrees with itself.
AC2_GOLDEN_STDOUT = (
    "  drained 3 entries from CHANGELOG.md → docs/archive/CHANGELOG-archive.md"
    " (verbatim, newest-first, pointer stub + TOC entries left)\n"
)
AC2_GOLDEN_SOURCE = (
    "# Changelog\n"
    "\n"
    "> Earlier entries archived verbatim (newest-first): → docs/archive/CHANGELOG-archive.md\n"
    "\n"
    "## [1.3.0] — 2026-04-01\n"
    "\n"
    "body of [1.3.0] — 2026-04-01\n"
    "\n"
    "## [1.4.0] — 2026-05-01\n"
    "\n"
    "body of [1.4.0] — 2026-05-01\n"
    "\n"
    "## [1.5.0] — 2026-06-01\n"
    "\n"
    "body of [1.5.0] — 2026-06-01\n"
    "\n"
)
AC2_GOLDEN_ARCHIVE = (
    "# CHANGELOG — archive (verbatim, newest-first)\n"
    "\n"
    "## 📑 Index\n"
    "\n"
    "- [1.2.0] — 2026-03-01\n"
    "- [1.1.0] — 2026-02-01\n"
    "- [1.0.0] — 2026-01-01\n"
    "---\n"
    "## [1.2.0] — 2026-03-01\n"
    "\n"
    "body of [1.2.0] — 2026-03-01\n"
    "\n"
    "## [1.1.0] — 2026-02-01\n"
    "\n"
    "body of [1.1.0] — 2026-02-01\n"
    "\n"
    "## [1.0.0] — 2026-01-01\n"
    "\n"
    "body of [1.0.0] — 2026-01-01\n"
    "\n"
)


def test_chron_output_is_byte_identical_to_pre_change(tmp_path: Path) -> None:
    """AC2 (⟲ regression guard, green by construction).

    An oldest-first document with no pinned entries must come out of the rewrite exactly as
    it does today: same hot file, same archive, same stdout. If the walk-based rewrite
    breaks this, it changed behaviour on documents that already work — a finding, not a
    fixture to relax.
    """
    repo = make_monolith_repo(tmp_path, CHRON_HEADINGS)
    result = _run(repo, "drain", MONOLITH)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == AC2_GOLDEN_STDOUT
    assert (repo / MONOLITH).read_text() == AC2_GOLDEN_SOURCE
    assert (repo / ARCHIVE).read_text() == AC2_GOLDEN_ARCHIVE


def test_reverse_chron_keeps_newest_three(tmp_path: Path) -> None:
    """AC1. On a newest-first document the drain must keep the newest three entries.

    RED against the pre-change script: `drain_monolith` hard-codes "newest entry is the
    LAST heading", so it keeps the last three in file order — which on this
    document are the three OLDEST — the defect that archives a newest-first changelog's
    `[Unreleased]` section.
    """
    repo = make_monolith_repo(
        tmp_path, REVERSE_CHRON_HEADINGS, retention={"order": {MONOLITH: "newest-first"}}
    )
    result = _run(repo, "drain", MONOLITH)
    assert result.returncode == 0, result.stdout + result.stderr
    kept = entry_headings((repo / MONOLITH).read_text())
    assert kept == list(REVERSE_CHRON_HEADINGS[:3]), (
        "a newest-first document must keep its newest three entries; "
        f"kept {kept} instead"
    )


PREAMBLE_HEADINGS: tuple[str, ...] = (
    "How to read this file",
    "How to contribute an entry",
)


def test_declared_preamble_headings_survive(tmp_path: Path) -> None:
    """AC4. Undated preamble headings declared under `retention.non_entry_headings` are not
    entries and must never be evicted, however many real entries sit below them.

    RED against the pre-change script: the only heading it refuses to treat as an entry is
    `## …Index`, so both preamble headings enter the candidate set, land in the head of the
    file, and are archived as the two oldest entries.
    """
    repo = make_monolith_repo(
        tmp_path,
        PREAMBLE_HEADINGS + CHRON_HEADINGS,
        retention={"non_entry_headings": {MONOLITH: list(PREAMBLE_HEADINGS)}},
    )
    result = _run(repo, "drain", MONOLITH)
    assert result.returncode == 0, result.stdout + result.stderr

    kept = entry_headings((repo / MONOLITH).read_text())
    assert kept == list(PREAMBLE_HEADINGS) + list(CHRON_HEADINGS[3:]), (
        "declared preamble headings must survive alongside the newest three entries; "
        f"kept {kept} instead"
    )
    archived = entry_headings((repo / ARCHIVE).read_text())
    assert archived == list(reversed(CHRON_HEADINGS[:3])), (
        f"only the three oldest real entries may be archived; archived {archived} instead"
    )


def test_unreleased_survives_no_declaration(tmp_path: Path) -> None:
    """AC3 (⟲ regression guard, green by construction).

    `[Unreleased]` is pinned unconditionally, with no declaration needed. Here it also sits
    inside the keep window, so today's script already keeps it; the row exists so that the
    pinning machinery cannot quietly change the answer on this shape.
    """
    repo = make_monolith_repo(tmp_path, CHRON_HEADINGS + ("[Unreleased]",))
    result = _run(repo, "drain", MONOLITH)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "## [Unreleased]" in (repo / MONOLITH).read_text()


def _assert_usage_error_moved_nothing(
    repo: Path, result: subprocess.CompletedProcess[str], before: str
) -> None:
    """A usage error must be non-zero AND inert: hot file untouched, archive never created.

    Asserting the archive is *absent* (rather than hashing it) is only valid because these
    fixtures start without one.
    """
    assert result.returncode != 0, result.stdout + result.stderr
    assert (repo / MONOLITH).read_text() == before, "a usage error must move zero bytes"
    assert not (repo / ARCHIVE).exists(), "a usage error must not create an archive"


def test_invalid_order_value_is_a_usage_error(tmp_path: Path) -> None:
    """`order` takes `newest-first` or `oldest-first` and nothing else.

    RED against the pre-change script: it never reads `order`, so a typo'd value drains
    silently under the default ordering and the operator's declaration is a no-op.
    """
    repo = make_monolith_repo(
        tmp_path, CHRON_HEADINGS, retention={"order": {MONOLITH: "newest_first"}}
    )
    before = (repo / MONOLITH).read_text()
    _assert_usage_error_moved_nothing(repo, _run(repo, "drain", MONOLITH), before)


@pytest.mark.parametrize(
    ("declared", "shape"),
    [
        ("not-an-array", "a string where an array of strings belongs"),
        (["## How to read this file"], "a heading declared with its '## ' prefix"),
    ],
)
def test_malformed_non_entry_headings_is_a_usage_error(
    tmp_path: Path, declared: object, shape: str
) -> None:
    """Malformed *protection* must fail closed.

    Failing open here is the expensive direction: it produces a silent, successful drain that
    archives the very heading the declaration was written to protect. RED against the
    pre-change script for both shapes — it reads neither key.
    """
    repo = make_monolith_repo(
        tmp_path,
        PREAMBLE_HEADINGS + CHRON_HEADINGS,
        retention={"non_entry_headings": {MONOLITH: declared}},
    )
    before = (repo / MONOLITH).read_text()
    _assert_usage_error_moved_nothing(repo, _run(repo, "drain", MONOLITH), before)


STUB_PREFIX = "> Earlier entries archived verbatim"


def stub_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith(STUB_PREFIX)]


def test_reverse_chron_evicts_final_entry_without_unbound_error(tmp_path: Path) -> None:
    """AC1. The newest-first path always evicts the file's LAST entry, whose
    `starts[i+1]` does not exist. The script runs `set -uo pipefail`, so an unguarded read
    aborts the shell before the loop body executes.

    This row could not exist before newest-first eviction: with KEEP=3 the oldest-first path never reaches
    `i == n-1`, so the branch was dead and no red for it was observable. It goes
    red the moment eviction learns to run newest-first, and green when the terminus is fixed.
    """
    repo = make_monolith_repo(
        tmp_path, REVERSE_CHRON_HEADINGS, retention={"order": {MONOLITH: "newest-first"}}
    )
    result = _run(repo, "drain", MONOLITH)
    assert "unbound variable" not in result.stderr, result.stderr
    assert result.returncode == 0, result.stdout + result.stderr
    archived = entry_headings((repo / ARCHIVE).read_text())
    assert REVERSE_CHRON_HEADINGS[-1] in archived, (
        "the file's last entry is the oldest on a newest-first document and must be archived"
    )


#: Descending versions, no dates anywhere — the alarm has nothing to say about this document,
#: so the declaration is the only signal in play.
UNDATED_DESCENDING: tuple[str, ...] = tuple(f"[1.{i}.0]" for i in range(5, -1, -1))


def test_declaration_is_authoritative(tmp_path: Path) -> None:
    """AC5. The declaration decides the direction on its own — no dates are involved here, so
    nothing but `order` could have produced this answer.

    The fixture is deliberately undated. A dated fixture cannot express this AC now that the alarm
    exists: dates that *agree* with the declaration make the row unable to tell the two signals
    apart, and dates that *disagree* refuse rather than obey. "Authoritative" means the
    dates never silently override the declaration — the drain either follows it or refuses.

    Provenance of its red, stated exactly: this row was first written on a DATED fixture and
    was red there because `order` was validated but never acted on. It moved to this undated fixture
    once the alarm made the dated shape unsatisfiable — so the red above was observed on the
    earlier fixture, not on this one. Derivable, not measured, and said so rather than implied.
    """
    repo = make_monolith_repo(
        tmp_path, UNDATED_DESCENDING, retention={"order": {MONOLITH: "newest-first"}}
    )
    result = _run(repo, "drain", MONOLITH)
    assert result.returncode == 0, result.stdout + result.stderr
    kept = entry_headings((repo / MONOLITH).read_text())
    assert kept == list(UNDATED_DESCENDING[:3]), (
        f"a newest-first declaration must keep the file's FIRST three entries; kept {kept}"
    )


def test_absent_declaration_keeps_todays_behaviour(tmp_path: Path) -> None:
    """AC6 (⟲ regression guard, green by construction).

    No declaration, no manifest change on upgrade day: the document drains exactly as it did
    before `order` existed.
    """
    repo = make_monolith_repo(tmp_path, CHRON_HEADINGS)
    result = _run(repo, "drain", MONOLITH)
    assert result.returncode == 0, result.stdout + result.stderr
    assert entry_headings((repo / MONOLITH).read_text()) == list(CHRON_HEADINGS[3:])


def test_unreleased_survives_correct_declaration(tmp_path: Path) -> None:
    """AC3. Newest-first document, declared newest-first, `[Unreleased]` at the top."""
    repo = make_monolith_repo(
        tmp_path,
        ("[Unreleased]",) + REVERSE_CHRON_HEADINGS,
        retention={"order": {MONOLITH: "newest-first"}},
    )
    result = _run(repo, "drain", MONOLITH)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "## [Unreleased]" in (repo / MONOLITH).read_text()
    assert "## [Unreleased]" not in (repo / ARCHIVE).read_text()


def test_unreleased_survives_wrong_declaration(tmp_path: Path) -> None:
    """AC3. A newest-first document declared `oldest-first` drains the wrong end — that is the
    operator's error and the drain obeys it — but `[Unreleased]` is pinned unconditionally and
    must survive being declared about incorrectly.

    Undated on purpose. With dates, "declared oldest-first on a reverse-chron
    fixture" as a combination
    is a contradiction and refuses, so the row would prove only that a refusal moves nothing —
    already covered by `contradiction_refuses_and_moves_zero_bytes`. Undated, the declaration is
    genuinely wrong, the drain genuinely proceeds, and the pin is what saves the entry.
    """
    repo = make_monolith_repo(
        tmp_path,
        ("[Unreleased]",) + UNDATED_DESCENDING,
        retention={"order": {MONOLITH: "oldest-first"}},
    )
    result = _run(repo, "drain", MONOLITH)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "## [Unreleased]" in (repo / MONOLITH).read_text()
    assert "## [Unreleased]" not in (repo / ARCHIVE).read_text()


def test_unreleased_survives_below_a_real_entry(tmp_path: Path) -> None:
    """AC3 — the non-contiguous guard. A pinned entry sitting BELOW an evicted one makes the
    kept set non-contiguous, which the two-`sed`-range rewrite cannot express. It must be kept,
    and there must be **no refusal**: a positional rule would refuse here, and
    on an oldest-first changelog with a trailing `[Unreleased]` it would refuse forever.
    """
    headings = (CHRON_HEADINGS[0], "[Unreleased]") + CHRON_HEADINGS[1:]
    repo = make_monolith_repo(tmp_path, headings)
    result = _run(repo, "drain", MONOLITH)
    assert result.returncode == 0, result.stdout + result.stderr
    kept = entry_headings((repo / MONOLITH).read_text())
    assert kept == ["[Unreleased]"] + list(CHRON_HEADINGS[3:]), (
        f"the pinned entry must survive from below an evicted one; kept {kept}"
    )
    assert "## [Unreleased]" not in (repo / ARCHIVE).read_text()


def test_oldest_first_doc_with_trailing_unreleased_still_drains(tmp_path: Path) -> None:
    """AC3 — the permanent-un-drainability guard. An oldest-first document whose
    `[Unreleased]` is its LAST heading must still drain. Under a head-contiguity rule this
    document refuses on every run and grows past its cap forever — the exact failure the
    retention discipline exists to prevent.
    """
    repo = make_monolith_repo(tmp_path, CHRON_HEADINGS + ("[Unreleased]",))
    result = _run(repo, "drain", MONOLITH)
    assert result.returncode == 0, result.stdout + result.stderr
    kept = entry_headings((repo / MONOLITH).read_text())
    assert kept == list(CHRON_HEADINGS[3:]) + ["[Unreleased]"], (
        f"the document must drain its three oldest entries and keep the rest; kept {kept}"
    )
    assert entry_headings((repo / ARCHIVE).read_text()) == list(
        reversed(CHRON_HEADINGS[:3])
    )


def test_second_drain_does_not_archive_the_pointer_stub(tmp_path: Path) -> None:
    """On a newest-first document the stub lands at the FOOT of the file, so on the
    next drain it sits inside the evicted region's text and would be copied into the archive as
    body content. The walk emits nothing for an evicted entry, so on THIS path exactly one stub
    survives and none reaches the archive.

    Scope is the newest-first path only. On the oldest-first path the previous stub sits above the
    first entry, inside the prefix the walk emits verbatim; that path is handled by the prefix
    rewrite and covered by the stub-collapse rows further down.
    """
    repo = make_monolith_repo(
        tmp_path, REVERSE_CHRON_HEADINGS, retention={"order": {MONOLITH: "newest-first"}}
    )
    assert _run(repo, "drain", MONOLITH).returncode == 0

    # a newest-first document grows at the TOP: three newer entries land under the H1
    hot = repo / MONOLITH
    text = hot.read_text()
    newer = "".join(
        f"## [2.{i}.0] — 2026-0{7 + i}-01\n\nbody of [2.{i}.0]\n\n" for i in range(3)
    )
    hot.write_text(text.replace("# Changelog\n\n", "# Changelog\n\n" + newer, 1))

    result = _run(repo, "drain", MONOLITH)
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(stub_lines(hot.read_text())) == 1, "exactly one stub may survive per file"
    assert stub_lines((repo / ARCHIVE).read_text()) == [], (
        "a stub written by a previous run must never be archived as entry text"
    )


REFUSAL_EXIT = 3

#: Descending with same-day ties — the shape a real CHANGELOG.md routinely has (several
#: releases on one day). Under a *strictly* monotone criterion this sequence is
#: inconclusive and the alarm could not fire on it, which is why the criterion is
#: one-directional monotone.
TIED_DESCENDING: tuple[str, ...] = (
    "[1.5.0] — 2026-06-01",
    "[1.4.0] — 2026-05-01",
    "[1.3.1] — 2026-05-01",
    "[1.3.0] — 2026-04-01",
    "[1.2.0] — 2026-03-01",
    "[1.1.0] — 2026-02-01",
)


def test_contradiction_refuses_and_moves_zero_bytes(tmp_path: Path) -> None:
    """AC7. Dates say newest-first, the effective ordering is oldest-first (undeclared) — the
    drain refuses with exit 3 and touches nothing.

    The archive is asserted **absent** rather than hashed, which is only valid because this
    fixture starts without one.
    """
    repo = make_monolith_repo(tmp_path, REVERSE_CHRON_HEADINGS)
    before = (repo / MONOLITH).read_text()
    result = _run(repo, "drain", MONOLITH)
    assert result.returncode == REFUSAL_EXIT, result.stdout + result.stderr
    assert (repo / MONOLITH).read_text() == before, "a refusal must move zero bytes"
    assert not (repo / ARCHIVE).exists(), "a refusal must not create an archive"


def test_ties_do_not_disarm_the_alarm(tmp_path: Path) -> None:
    """AC7 — the one-directional criterion's guard, and the most important row here.

    A descending sequence containing same-day ties has zero strictly-ascending pairs and at
    least one strictly-descending pair, so it is detected `newest-first`. Under the strict
    criterion the ties would make it inconclusive and the drain would proceed — which is
    precisely the failure the alarm exists to catch.
    """
    repo = make_monolith_repo(tmp_path, TIED_DESCENDING)
    result = _run(repo, "drain", MONOLITH)
    assert result.returncode == REFUSAL_EXIT, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("headings", "shape"),
    [
        (("Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta"), "no dates at all"),
        (("Alpha", "Beta", "Gamma", "Delta", "Epsilon", "[1.0.0] — 2026-01-01"), "one date"),
        (tuple(f"[1.{i}.0] — 2026-01-01" for i in range(6)), "all-equal dates"),
        (
            (
                "[1.0.0] — 2026-01-01",
                "[1.1.0] — 2026-03-01",
                "[1.2.0] — 2026-02-01",
                "[1.3.0] — 2026-04-01",
                "[1.4.0] — 2026-01-15",
                "[1.5.0] — 2026-05-01",
            ),
            "mixed directions",
        ),
    ],
)
def test_inconclusive_detection_does_not_block(
    tmp_path: Path, headings: tuple[str, ...], shape: str
) -> None:
    """AC8. The alarm speaks only when the evidence is one-directional. Every other shape
    proceeds silently under the effective ordering — an alarm that fires on ambiguity would
    make undated documents un-drainable.
    """
    repo = make_monolith_repo(tmp_path, headings)
    result = _run(repo, "drain", MONOLITH)
    assert result.returncode == 0, result.stdout + result.stderr
    assert entry_headings((repo / MONOLITH).read_text()) == list(headings[3:])


def test_refusal_message_names_file_ordering_source_and_evidence(tmp_path: Path) -> None:
    """AC9. Each element is asserted present, not merely that something was printed."""
    repo = make_monolith_repo(tmp_path, REVERSE_CHRON_HEADINGS)
    out = _run(repo, "drain", MONOLITH).stdout + _run(repo, "drain", MONOLITH).stderr
    assert MONOLITH in out, "the message must name the file"
    assert "oldest-first" in out, "the message must name the effective ordering"
    assert "default" in out, "the message must say where the ordering came from"
    assert "2026-06-01" in out, "the message must show the observed dates as evidence"
    assert "newest-first" in out, "the message must say what the sequence says instead"
    assert "Nothing was moved" in out, "the message must state that nothing was moved"
    assert "Fix:" in out, "the message must carry a one-line fix"


def test_printed_fix_actually_fixes(tmp_path: Path) -> None:
    """AC9. Apply the message's own `Fix:` line to the fixture, re-run, assert it drains.

    A printed fix that still refuses is worse than none — a fix line that does not
    fix trains the reader to route around the gate rather than to act on it.
    """
    repo = make_monolith_repo(tmp_path, REVERSE_CHRON_HEADINGS)
    first = _run(repo, "drain", MONOLITH)
    assert first.returncode == REFUSAL_EXIT

    out = first.stdout + first.stderr
    assert "confirm which end" in out, "the fix must ask for a confirmation, not assert the verdict"
    fix = next(line for line in out.splitlines() if '"order"' in line)
    assert f'"{MONOLITH}"' in fix, (
        "the printed fix must name the file being drained — a fix naming some other document "
        f"would still let this test pass if it wrote the manifest itself: {fix}"
    )

    manifest = repo / ".claude/close-gate.json"
    manifest.write_text(
        json.dumps(
            {
                "retention": {
                    "archive_dir": "docs/archive",
                    "order": {MONOLITH: "newest-first"},
                }
            }
        ),
        encoding="utf-8",
    )
    second = _run(repo, "drain", MONOLITH)
    assert second.returncode == 0, second.stdout + second.stderr
    assert entry_headings((repo / MONOLITH).read_text()) == list(
        REVERSE_CHRON_HEADINGS[:3]
    )


def test_qa_log_preflight_refuses_before_fragments_are_deleted(tmp_path: Path) -> None:
    """AC7. `drain_qa_log` compiles fragments into the hot monolith, deletes
    every fragment, and only then drains it. A refusal raised at that point would land after
    the fragments are gone, making "nothing was moved" a lie and leaving the qa-log
    un-drainable with its sources deleted. The pre-flight therefore runs at the TOP.
    """
    mono = "docs/brainstorming-qa-log.md"
    repo = make_fixture_repo(
        tmp_path,
        manifest={"retention": {"archive_dir": "docs/archive"}},
        files={
            mono: monolith_body(REVERSE_CHRON_HEADINGS, header="# Brainstorming QA log\n\n"),
            "docs/qa-log.d/2026-07-01-a.md": "## fragment a\n\nbody\n",
            "docs/qa-log.d/2026-07-02-b.md": "## fragment b\n\nbody\n",
        },
    )
    before = (repo / mono).read_text()
    result = _run(repo, "drain", "qa-log")
    assert result.returncode == REFUSAL_EXIT, result.stdout + result.stderr
    assert sorted(p.name for p in (repo / "docs/qa-log.d").iterdir()) == [
        "2026-07-01-a.md",
        "2026-07-02-b.md",
    ], "fragments must still be on disk after a refusal"
    assert (repo / mono).read_text() == before, "the hot monolith must be untouched"


def test_qa_log_malformed_protection_refuses_before_fragments_are_deleted(tmp_path: Path) -> None:
    """The sibling half. `order` was hoisted into the pre-flight; the
    `non_entry_headings` validation was left inside `drain_monolith`, which `drain_qa_log` calls
    LAST. A malformed declaration therefore exited 1 after the compile had appended to the
    monolith and every fragment had been deleted — the exact failure the pre-flight exists to
    prevent, applied to the other key.
    """
    mono = "docs/brainstorming-qa-log.md"
    repo = make_fixture_repo(
        tmp_path,
        manifest={
            "retention": {
                "archive_dir": "docs/archive",
                "non_entry_headings": {"brainstorming-qa-log.md": "not-an-array"},
            }
        },
        files={
            mono: monolith_body(UNDATED_DESCENDING, header="# Brainstorming QA log\n\n"),
            "docs/qa-log.d/2026-07-01-a.md": "## fragment a\n\nbody\n",
        },
    )
    before = (repo / mono).read_text()
    result = _run(repo, "drain", "qa-log")
    assert result.returncode == 1, result.stdout + result.stderr
    assert (repo / "docs/qa-log.d/2026-07-01-a.md").exists(), (
        "a usage error must not consume the fragments"
    )
    assert (repo / mono).read_text() == before, "a usage error must move zero bytes"


def test_qa_log_refuses_on_a_contradiction_the_compile_introduces(tmp_path: Path) -> None:
    """The pre-flight at the top of `drain_qa_log` sees only the PRE-compile monolith. The
    fragments carry their own dated headings, so the compile itself can create the contradiction —
    and that refusal used to surface from the `drain_monolith` call at the foot of the function,
    after the fragments were gone, while printing "nothing was moved".
    """
    mono = "docs/brainstorming-qa-log.md"
    repo = make_fixture_repo(
        tmp_path,
        manifest={"retention": {"archive_dir": "docs/archive"}},
        files={
            # one date pre-compile → inconclusive, so the top pre-flight passes
            mono: "# Brainstorming QA log\n\n## [seed] — 2026-08-01\n\nbody\n\n",
            "docs/qa-log.d/2026-07-01-a.md": "## Q5 — 2026-07-05\n\nbody\n",
            "docs/qa-log.d/2026-07-02-b.md": "## Q4 — 2026-07-04\n\nbody\n",
            "docs/qa-log.d/2026-07-03-c.md": "## Q3 — 2026-07-03\n\nbody\n",
            "docs/qa-log.d/2026-07-04-d.md": "## Q2 — 2026-07-02\n\nbody\n",
        },
    )
    before = (repo / mono).read_text()
    result = _run(repo, "drain", "qa-log")
    assert result.returncode == REFUSAL_EXIT, result.stdout + result.stderr
    assert len(list((repo / "docs/qa-log.d").iterdir())) == 4, (
        "every fragment must still be on disk after a refusal"
    )
    assert (repo / mono).read_text() == before, "the hot monolith must be untouched"
    out = result.stdout + result.stderr
    assert mono in out, "the message must name the real monolith, not the staged temp copy"
    assert "no retention.order entry for brainstorming-qa-log.md" in out, (
        "the MANIFEST KEY must come from the display name too, not from the staged temp file — "
        "otherwise a declared qa-log ordering is silently ignored and the operator is told to "
        f"declare a temp path: {out}"
    )


def test_a_body_line_quoting_the_stub_is_archived_verbatim(tmp_path: Path) -> None:
    """The archive-side stub filter must not delete a body line that merely quotes a pointer stub
    pointing somewhere else.

    A prefix match deletes a body line that merely quotes the drain's own output — from the
    archive AND, because the walk emits nothing for an evicted entry, from the source too. It then
    exists nowhere, and the byte-conservation check cannot see it: `added` is measured on the
    already-filtered block, so the arithmetic still balances. Likely wherever a project's
    changelog or qa-log discusses this tool.
    """
    quoted = "> Earlier entries archived verbatim (newest-first): → docs/archive/EXAMPLE.md"
    body = (
        "# Changelog\n\n"
        f"## [1.0.0] — 2026-01-01\n\nthe drain writes a line like this:\n\n{quoted}\n\n"
        + "".join(f"## [1.{i}.0] — 2026-0{i}-01\n\nbody {i}\n\n" for i in (1, 2, 3, 4, 5))
    )
    repo = make_fixture_repo(
        tmp_path,
        manifest={"retention": {"archive_dir": "docs/archive"}},
        files={MONOLITH: body},
    )
    result = _run(repo, "drain", MONOLITH)
    assert result.returncode == 0, result.stdout + result.stderr
    everywhere = (repo / MONOLITH).read_text() + (repo / ARCHIVE).read_text()
    assert quoted in everywhere, (
        "a body line quoting the stub must survive the drain somewhere — it was deleted from both"
    )


def test_unparseable_manifest_is_a_usage_error(tmp_path: Path) -> None:
    """The direction the suite could not see. Every reader swallows jq's stderr and returns
    empty on error, so a manifest with a syntax error read as a manifest that is ABSENT: a declared
    `newest-first` silently reverted to the default and every declared heading lost its protection,
    at exit 0. That is malformed protection failing OPEN — the expensive direction — reached by
    a stray comma rather than by a wrong value.
    """
    repo = make_monolith_repo(
        tmp_path,
        PREAMBLE_HEADINGS + CHRON_HEADINGS,
        retention={"non_entry_headings": {MONOLITH: list(PREAMBLE_HEADINGS)}},
    )
    manifest = repo / ".claude/close-gate.json"
    manifest.write_text(manifest.read_text().replace("}}", "},}"), encoding="utf-8")
    before = (repo / MONOLITH).read_text()
    _assert_usage_error_moved_nothing(repo, _run(repo, "drain", MONOLITH), before)


def test_one_out_of_order_date_does_not_silence_the_alarm(tmp_path: Path) -> None:
    """Tightened after review. A single contrary pair is a backport or a typo, not a mixed
    document — and treating it as ambiguity made the protection one character wide.

    Measured on a copy of a real `CHANGELOG.md`: changing ONE date by two days,
    with no declaration, flipped the verdict from exit 3 to a full drain — the newest releases
    archived, on the default path, with both oracles green.
    """
    headings = (
        "[1.9.0] — 2026-09-01",
        "[1.8.0] — 2026-08-01",
        "[1.7.0] — 2026-10-01",  # the typo: one ascending pair in an otherwise descending file
        "[1.6.0] — 2026-06-01",
        "[1.5.0] — 2026-05-01",
        "[1.4.0] — 2026-04-01",
        "[1.3.0] — 2026-03-01",
    )
    repo = make_monolith_repo(tmp_path, headings)
    before = (repo / MONOLITH).read_text()
    result = _run(repo, "drain", MONOLITH)
    assert result.returncode == REFUSAL_EXIT, result.stdout + result.stderr
    assert (repo / MONOLITH).read_text() == before
    # …and a genuinely mixed document is still inconclusive: this is the line between the two.
    (tmp_path / "mixed").mkdir()
    mixed = make_monolith_repo(
        tmp_path / "mixed",
        (
            "[2.0.0] — 2026-01-01",
            "[2.1.0] — 2026-03-01",
            "[2.2.0] — 2026-02-01",
            "[2.3.0] — 2026-04-01",
            "[2.4.0] — 2026-01-15",
            "[2.5.0] — 2026-05-01",
        ),
    )
    assert _run(mixed, "drain", MONOLITH).returncode == 0


def test_a_dated_pinned_heading_alone_does_not_cause_a_refusal(tmp_path: Path) -> None:
    """Resolved after review. A structural heading carrying its own revision date,
    sitting above same-day entries, made the sequence one-directional by itself and refused a
    correctly ordered document — and the printed `Fix:` then inverted it, archiving the newest
    entries.

    A heading that is not an entry is not evidence about entry ordering, so the verdict is decided
    on the non-pinned sequence. The actual concern — that declaring a heading must not silently
    disarm an alarm the ENTRIES raise — is unaffected and is guarded by
    `test_a_dated_pinned_heading_does_not_disarm_a_real_contradiction`.
    """
    headings = ("Conventions — last revised 2026-07-30",) + tuple(
        f"Q{i} — 2026-07-01" for i in range(1, 6)
    )
    repo = make_monolith_repo(
        tmp_path,
        headings,
        retention={"non_entry_headings": {MONOLITH: ["Conventions — last revised 2026-07-30"]}},
    )
    result = _run(repo, "drain", MONOLITH)
    assert result.returncode == 0, result.stdout + result.stderr
    kept = entry_headings((repo / MONOLITH).read_text())
    assert kept == [headings[0]] + list(headings[3:]), (
        f"an all-same-day document must drain its oldest entries, not refuse; kept {kept}"
    )


def test_a_dated_pinned_heading_does_not_disarm_a_real_contradiction(tmp_path: Path) -> None:
    """The guard for that concern, kept. Declaring a heading must not silence an alarm the ENTRIES themselves
    raise — here the entries are descending on their own, and the declared heading's date agrees
    with the default. The refusal must still fire.

    It is red against the pre-change script too, but **for a different reason than its name
    suggests**, and saying so is the point: before the fix the pinned heading's own date sat in the
    sequence as one ascending pair, which made the whole thing inconclusive and let the document
    drain. So the old code failed this row by *under*-refusing on a real contradiction — the same
    pollution that made the sibling row *over*-refuse on a clean one.
    """
    repo = make_monolith_repo(
        tmp_path,
        ("Conventions — last revised 2026-01-01",) + REVERSE_CHRON_HEADINGS,
        retention={"non_entry_headings": {MONOLITH: ["Conventions — last revised 2026-01-01"]}},
    )
    assert _run(repo, "drain", MONOLITH).returncode == REFUSAL_EXIT


@pytest.mark.parametrize(
    "declared",
    ["**Conventions** — last revised 2026-07-30", "Conventions a{2 — last revised 2026-07-30"],
)
def test_a_declared_heading_with_regex_metacharacters_does_not_disarm_the_alarm(
    tmp_path: Path, declared: str
) -> None:
    """The pinned-heading exclusion must compare TEXT, not compile a regex.

    `awk -v` runs escape processing over its value before the regex engine sees it, so shell-side
    escaping is consumed rather than applied. A declared `**Conventions**` reached the engine
    unescaped, awk aborted, the date list came back empty, and an empty list reads as "no dates —
    proceed silently": the alarm disarmed at exit 0 by a bold heading, and the newest releases
    archived. Fail-OPEN, and the stderr line is invisible to any caller using `|| true`.
    """
    repo = make_monolith_repo(
        tmp_path,
        (declared,) + REVERSE_CHRON_HEADINGS,
        retention={"non_entry_headings": {MONOLITH: [declared]}},
    )
    before = (repo / MONOLITH).read_text()
    result = _run(repo, "drain", MONOLITH)
    assert result.returncode == REFUSAL_EXIT, result.stdout + result.stderr
    assert (repo / MONOLITH).read_text() == before


def test_a_stub_below_a_pinned_heading_reaches_the_archive_as_one_line(tmp_path: Path) -> None:
    """The KNOWN LIMIT of the stub rule, asserted rather than left undocumented.

    The walk writes the stub at the position of the first evicted entry, which is the foot of the
    file only when nothing is pinned below it. The filter drops a trailing stub at the END OF THE
    FILE, so on this shape the stub is copied into the archive as one line of pointer prose.

    That is the accepted cost of the only rule that provably cannot lose data — the two variants
    that covered this shape each deleted an ordinary body line from the archive AND the source at
    once. Nothing is lost here; a cold file gains a stray line. The fully correct
    rule needs a sentinel, which changes the stub's bytes and so AC2's golden.

    This row exists so that a future change to the rule has to confront this case deliberately: if
    it starts passing, the limit was closed and this docstring is what says so.
    """
    repo = make_monolith_repo(
        tmp_path,
        REVERSE_CHRON_HEADINGS[:5] + ("[Unreleased]",) + REVERSE_CHRON_HEADINGS[5:],
        retention={"order": {MONOLITH: "newest-first"}},
    )
    assert _run(repo, "drain", MONOLITH).returncode == 0
    hot = repo / MONOLITH
    newer = "".join(f"## [2.{i}.0]\n\nbody of [2.{i}.0]\n\n" for i in range(3))
    hot.write_text(hot.read_text().replace("# Changelog\n\n", "# Changelog\n\n" + newer, 1))
    result = _run(repo, "drain", MONOLITH)
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(stub_lines((repo / ARCHIVE).read_text())) == 1, (
        "known limit: with a pinned heading below the stub's position the stub is not the "
        "file's last line, so it is archived as prose. If this is now 0 the limit was closed — "
        "update the docstring rather than the number."
    )
    assert len(stub_lines(hot.read_text())) == 1, "the hot file still carries exactly one stub"


@pytest.mark.parametrize(
    "retention",
    [
        {"archive_dir": "docs/archive", "order": "newest-first"},
        {"archive_dir": "docs/archive", "non_entry_headings": ["How to read this file"]},
        # `.retention` itself the wrong shape: jq exits 5 with EMPTY stdout, and a `case` whose only
        # arm was `bad)` fell through to the safe path — an unreadable probe reading as "shape is
        # fine". Every declaration dropped, exit 0, the declared heading archived.
        [{"archive_dir": "docs/archive"}, {"non_entry_headings": {"CHANGELOG.md": ["x"]}}],
    ],
)
def test_a_container_of_the_wrong_shape_is_a_usage_error(tmp_path: Path, retention: dict) -> None:
    """One level up from the value checks. Forgetting the per-file map is valid JSON, passes
    the parse probe, reads as absent for every basename, and silently reverts the declaration to
    the default — malformed protection failing OPEN again, one container higher.
    """
    repo = make_fixture_repo(
        tmp_path,
        manifest={"retention": retention},
        files={MONOLITH: monolith_body(UNDATED_DESCENDING)},
    )
    before = (repo / MONOLITH).read_text()
    _assert_usage_error_moved_nothing(repo, _run(repo, "drain", MONOLITH), before)


def test_retention_md_fence_is_byte_identical_to_the_real_script() -> None:
    """retention.md embeds a full copy of retention-drain.sh as the canonical
    source /init-harness materializes into a project. That copy is a cache —
    prose derived from a live source — and caches rot silently unless something
    mechanically checks them. This is that check: if retention-drain.sh changes
    and the doc's fence isn't updated to match, this test goes red."""
    embedded = extract_retention_drain_script(RETENTION_MD)
    # The TRACKED path, deliberately not the overridable `DRAIN`: under `PLC_DRAIN_IMPL` this row
    # would redden for every mutant, for a documentation reason, inflating any "N rows red" count
    # taken from a whole-file run by exactly one.
    real = (Path(__file__).resolve().parent / "retention-drain.sh").read_text(encoding="utf-8")
    assert embedded == real, (
        "skills/project-lifecycle/references/retention.md's ```bash fence has "
        "drifted from scripts/retention-drain.sh — resync the fence verbatim"
    )


# --------------------------------------------------------------------------------------
# drain_journal surface
#
# This function once had ZERO tests — nothing in this file ran `drain journal` at all.
# Both the wall-clock-month and the never-written-archive-index defects lived here, which is
# not a coincidence: an untested function is where a defect survives many real drains.
# --------------------------------------------------------------------------------------

JOURNAL_DIR = "docs/journal.d"
JOURNAL_ARCHIVE_DIR = "docs/archive/journal"


def journal_fragment(stem: str) -> str:
    """One fragment, shaped like a real one: an H1 title then one `## ` entry."""
    return f"# Journal fragment — {stem}\n\n## {stem} entry\n\nbody of {stem}\n"


def make_journal_repo(
    tmp_path: Path, stems: tuple[str, ...], *, retention: dict | None = None
) -> Path:
    manifest = {"retention": {"archive_dir": "docs/archive", **(retention or {})}}
    files = {f"{JOURNAL_DIR}/{s}.md": journal_fragment(s) for s in stems}
    return make_fixture_repo(tmp_path, manifest=manifest, files=files)


def archive_month_files(repo: Path) -> list[str]:
    d = repo / JOURNAL_ARCHIVE_DIR
    return sorted(p.name for p in d.iterdir()) if d.is_dir() else []


def wall_clock_month() -> str:
    """The month `date +%Y-%m` would produce, for the fallback assertions only."""
    return datetime.now().strftime("%Y-%m")


def test_fragments_land_in_the_month_their_own_name_carries(tmp_path: Path) -> None:
    """AC1. Red before the fix ON ANY DATE — that is why the fixture spans two months.

    A single-month fixture would pass by accident whenever the run happens inside that
    month, which is exactly how such a defect survives: every drain run in the month its
    fragments were written passes.
    """
    repo = make_journal_repo(tmp_path, ("2026-07-30-phase-x-a", "2026-08-01-phase-x-b"))
    result = _run(repo, "drain", "journal")
    assert result.returncode == 0, result.stdout + result.stderr

    assert archive_month_files(repo) == ["2026-07.md", "2026-08.md"], (
        "two fragments carrying two months must produce two archives, "
        f"got {archive_month_files(repo)}"
    )
    july = (repo / JOURNAL_ARCHIVE_DIR / "2026-07.md").read_text(encoding="utf-8")
    august = (repo / JOURNAL_ARCHIVE_DIR / "2026-08.md").read_text(encoding="utf-8")

    assert "2026-07-30-phase-x-a.md" in july and "2026-08-01-phase-x-b.md" not in july
    assert "2026-08-01-phase-x-b.md" in august and "2026-07-30-phase-x-a.md" not in august
    # The header is half the defect: a wall-clock month puts one month's header over another month's content.
    assert july.splitlines()[0] == "# Journal archive — 2026-07"
    assert august.splitlines()[0] == "# Journal archive — 2026-08"


def test_an_undated_fragment_falls_back_to_the_wall_clock_and_names_itself(
    tmp_path: Path,
) -> None:
    """AC2. The placement half of this assertion is green before the fix (the wall clock
    IS today's behaviour); the half that is red is the warning. Recorded here so the row
    is not read as stronger evidence than it is."""
    repo = make_journal_repo(tmp_path, ("notes",))
    result = _run(repo, "drain", "journal")
    assert result.returncode == 0, result.stdout + result.stderr
    assert archive_month_files(repo) == [f"{wall_clock_month()}.md"]
    assert "notes.md" in result.stdout, (
        "an undated fragment must be named in the output — a silent wall-clock fallback "
        "is indistinguishable from a correctly-dated one"
    )


@pytest.mark.parametrize("stem", ["notadate-x", "2026-13-99-x"])
def test_a_malformed_date_prefix_takes_the_fallback_not_a_garbage_month(
    tmp_path: Path, stem: str
) -> None:
    """AC2b. The case a substring cut cannot pass.

    `${f:0:7}` always "succeeds": it returns seven characters whether or not they are a
    date. `2026-13-99-x.md` would then be filed under a `2026-13.md` that no calendar has,
    and — because extraction "worked" — would never enter the branch AC2 requires to warn.
    """
    repo = make_journal_repo(tmp_path, (stem,))
    result = _run(repo, "drain", "journal")
    assert result.returncode == 0, result.stdout + result.stderr
    assert archive_month_files(repo) == [f"{wall_clock_month()}.md"], (
        f"{stem}.md has no valid date prefix and must take the fallback, "
        f"got {archive_month_files(repo)}"
    )
    assert f"{stem}.md" in result.stdout


#: Captured from the PRE-CHANGE `retention-drain.sh` by running
#: `drain journal` on three same-month fragments. Committed as a literal, never recomputed:
#: a golden taken from the post-change script would only assert that the new code agrees
#: with itself. Scoped to the region AFTER the `---` separator on purpose — the filename and
#: the `# Journal archive — YYYY-MM` header legitimately changed with the per-fragment month, the compiled body's
#: ordering and separators must not. (Index bullets live ABOVE the separator; this golden
#: is deliberately blind to that region so this control does not move with the index.)
JOURNAL_BODY_GOLDEN = (
    "\n"
    "<!-- fragment: docs/journal.d/2026-07-30-phase-x-c.md -->\n"
    "# Journal fragment — 2026-07-30-phase-x-c\n"
    "\n"
    "## 2026-07-30-phase-x-c entry\n"
    "\n"
    "body of 2026-07-30-phase-x-c\n"
    "\n"
    "\n"
    "<!-- fragment: docs/journal.d/2026-07-20-phase-x-b.md -->\n"
    "# Journal fragment — 2026-07-20-phase-x-b\n"
    "\n"
    "## 2026-07-20-phase-x-b entry\n"
    "\n"
    "body of 2026-07-20-phase-x-b\n"
    "\n"
    "\n"
    "<!-- fragment: docs/journal.d/2026-07-10-phase-x-a.md -->\n"
    "# Journal fragment — 2026-07-10-phase-x-a\n"
    "\n"
    "## 2026-07-10-phase-x-a entry\n"
    "\n"
    "body of 2026-07-10-phase-x-a\n"
    "\n"
)


def test_a_same_month_drain_keeps_its_newest_first_body_byte_for_byte(
    tmp_path: Path,
) -> None:
    """Regression control (⟲ green by construction, both before and after).

    Proves the per-fragment month derivation did not disturb the compile itself:
    descending sort still means newest-first WITHIN a month file, and the blank-line
    separators between fragments are unchanged. It runs the drain ONCE and therefore says
    nothing about re-running — that is AC4's job, not this one.
    """
    repo = make_journal_repo(
        tmp_path,
        ("2026-07-10-phase-x-a", "2026-07-20-phase-x-b", "2026-07-30-phase-x-c"),
    )
    assert _run(repo, "drain", "journal").returncode == 0
    written = archive_month_files(repo)
    assert len(written) == 1, f"one month in, one archive out, got {written}"
    text = (repo / JOURNAL_ARCHIVE_DIR / written[0]).read_text(encoding="utf-8")
    body = text.split("---\n", 1)[1]
    assert body == JOURNAL_BODY_GOLDEN


def test_a_second_drain_of_the_same_fragment_appends_nothing(tmp_path: Path) -> None:
    """AC4, body half. NOT a red-before-green row — the idempotence sentinel in `drain_journal`
    already works. This is coverage added to a mechanism that shipped untested, which is
    a different claim than "a defect was fixed".
    The crash-between-append-and-delete state it guards is reproduced by writing
    the fragment back after a completed drain.
    """
    stem = "2026-07-30-phase-x-a"
    repo = make_journal_repo(tmp_path, (stem,))
    assert _run(repo, "drain", "journal").returncode == 0
    written = archive_month_files(repo)
    assert len(written) == 1
    archive = repo / JOURNAL_ARCHIVE_DIR / written[0]
    after_first = archive.read_text(encoding="utf-8")

    (repo / JOURNAL_DIR / f"{stem}.md").write_text(journal_fragment(stem), encoding="utf-8")
    second = _run(repo, "drain", "journal")
    assert second.returncode == 0, second.stdout + second.stderr

    assert archive.read_text(encoding="utf-8") == after_first, (
        "an already-compiled fragment must not be appended twice"
    )
    assert "already compiled" in second.stdout
    assert not (repo / JOURNAL_DIR / f"{stem}.md").exists(), (
        "the skipped fragment must still be deleted — a skip is not a failure"
    )


# --------------------------------------------------------------------------------------
# Index maintenance + stub collapse
#
# --------------------------------------------------------------------------------------

INDEXED_HEADER = "# Changelog\n\n## 📑 Index\n\n- stale one\n- stale two\n\n"


def test_journal_archive_index_gets_one_bullet_per_appended_heading(tmp_path: Path) -> None:
    """AC3. The archive's `## 📑 Index` must not stay empty after a drain,
    since `references/retention.md` says fragments carry no TOC *because the obligation lives on
    the compiled archive*."""
    repo = make_journal_repo(tmp_path, ("2026-07-10-phase-x-a", "2026-07-20-phase-x-b"))
    assert _run(repo, "drain", "journal").returncode == 0
    text = (repo / JOURNAL_ARCHIVE_DIR / "2026-07.md").read_text(encoding="utf-8")
    head = text.split("---\n", 1)[0]
    assert "- 2026-07-20-phase-x-b entry" in head
    assert "- 2026-07-10-phase-x-a entry" in head
    # Plain text, never a hand-computed anchor link — document-indexing.md's anti-pattern.
    assert "](#" not in head, "TOC bullets are plain text; anchor guesses are the banned shape"


def test_a_skipped_reappend_adds_no_duplicate_bullet(tmp_path: Path) -> None:
    """AC4, index half. The sentinel skips the append; the index must skip with it, or a
    crash-retry silently doubles every bullet."""
    stem = "2026-07-30-phase-x-a"
    repo = make_journal_repo(tmp_path, (stem,))
    assert _run(repo, "drain", "journal").returncode == 0
    archive = repo / JOURNAL_ARCHIVE_DIR / "2026-07.md"
    first = archive.read_text(encoding="utf-8")
    (repo / JOURNAL_DIR / f"{stem}.md").write_text(journal_fragment(stem), encoding="utf-8")
    assert _run(repo, "drain", "journal").returncode == 0
    assert archive.read_text(encoding="utf-8") == first


def test_the_source_index_is_regenerated_from_what_survives(tmp_path: Path) -> None:
    """AC5. Left alone, a source index is not merely stale after a drain but INVERTED —
    its anchors point at the evicted sections, and none of the
    surviving sections appear at all. Regenerated, never patched: a patched index can drift,
    a regenerated one is the file describing itself."""
    repo = make_monolith_repo(tmp_path, CHRON_HEADINGS, header=INDEXED_HEADER)
    assert _run(repo, "drain", MONOLITH).returncode == 0
    text = (repo / MONOLITH).read_text()
    head = text.split("## [", 1)[0]
    survivors = entry_headings(text)
    assert survivors == list(CHRON_HEADINGS[-3:]), survivors
    for h in survivors:
        assert f"- {h}" in head, f"surviving section {h!r} must be listed"
    for h in CHRON_HEADINGS[:3]:
        assert f"- {h}" not in head, f"evicted section {h!r} must not be listed"
    assert "- stale one" not in head and "- stale two" not in head


def test_a_document_without_an_index_is_left_byte_identical(tmp_path: Path) -> None:
    """The other half of AC5, and the reason index regeneration cannot be unconditional: the
    AC2 golden above pins a no-Index document's output byte-for-byte. Regeneration must be
    keyed on the source ACTUALLY having an `## …Index` heading, not on the drain running."""
    repo = make_monolith_repo(tmp_path, CHRON_HEADINGS)
    result = _run(repo, "drain", MONOLITH)
    assert result.returncode == 0
    assert (repo / MONOLITH).read_text() == AC2_GOLDEN_SOURCE


def test_stubs_never_accumulate_across_runs(tmp_path: Path) -> None:
    """AC6. Six identical stubs in one hot file = six drains, not six
    evicted entries: `stub_done` already emits exactly one per run, and a previous run's stub
    then survives inside the prefix range the walk emits verbatim. The fixture seeds the stubs
    directly so the assertion does not depend on running the drain six times."""
    stub = "> Earlier entries archived verbatim (newest-first): → docs/archive/CHANGELOG-archive.md"
    header = "# Changelog\n\n" + "".join(f"{stub}\n\n" for _ in range(6))
    repo = make_monolith_repo(tmp_path, CHRON_HEADINGS, header=header)
    assert _run(repo, "drain", MONOLITH).returncode == 0
    assert len(stub_lines((repo / MONOLITH).read_text())) == 1, (
        "one stub per file, however many drains preceded it"
    )


def test_collapse_and_index_regeneration_do_not_offset_each_other(tmp_path: Path) -> None:
    """The composition risk: both passes rewrite the SAME prefix
    region, and the index insertion locates its anchor by line number. Two stubs make N > 1, so
    an off-by-N lands visibly rather than coincidentally correct."""
    stub = "> Earlier entries archived verbatim (newest-first): → docs/archive/CHANGELOG-archive.md"
    header = "# Changelog\n\n## 📑 Index\n\n- stale one\n\n" + f"{stub}\n\n{stub}\n\n"
    repo = make_monolith_repo(tmp_path, CHRON_HEADINGS, header=header)
    assert _run(repo, "drain", MONOLITH).returncode == 0
    text = (repo / MONOLITH).read_text()
    head = text.split("## [", 1)[0]
    assert len(stub_lines(text)) == 1
    assert head.count("## 📑 Index") == 1, "the index heading must not be duplicated or displaced"
    for h in CHRON_HEADINGS[-3:]:
        assert f"- {h}" in head
    assert "- stale one" not in head


def test_a_preamble_line_below_the_index_is_not_eaten_by_the_collapse(tmp_path: Path) -> None:
    """AC7, source side. The collapse matches a prefix, and `drain_monolith`'s comments record that a previous
    variant of exactly this idea deleted an ordinary quoted line. Only lines that ARE stubs may
    go; ordinary preamble prose in the same region must survive untouched."""
    keep = "This file used to say: earlier entries archived verbatim, and that note moved."
    header = f"# Changelog\n\n## 📑 Index\n\n- stale one\n\n{keep}\n\n"
    repo = make_monolith_repo(tmp_path, CHRON_HEADINGS, header=header)
    assert _run(repo, "drain", MONOLITH).returncode == 0
    assert keep in (repo / MONOLITH).read_text()


# ------------------------------------------------------------------------------------------
# Two shapes no fixture combined before
# ------------------------------------------------------------------------------------------


def test_pinned_headings_are_not_listed_as_entries_in_the_regenerated_index(
    tmp_path: Path,
) -> None:
    """The combination that had no witness in either direction: a document that BOTH declares
    `non_entry_headings` AND carries an `## …Index` block. The regeneration listed everything
    that survived the eviction, and a pin survives by definition — so `- How to read this file`
    and `- [Unreleased]` landed in the index beside dated release entries. Pins are the
    document's scaffolding, which is why they are unevictable; they are not contents.

    A typical `CHANGELOG.md` declares exactly this shape, so it is the first real
    document a naive regeneration gets wrong."""
    header = "# Changelog\n\n## 📑 Index\n\n- stale one\n\n"
    repo = make_monolith_repo(
        tmp_path,
        PREAMBLE_HEADINGS + ("[Unreleased]",) + CHRON_HEADINGS,
        retention={"non_entry_headings": {MONOLITH: list(PREAMBLE_HEADINGS)}},
        header=header,
    )
    assert _run(repo, "drain", MONOLITH).returncode == 0
    text = (repo / MONOLITH).read_text()
    head = text.split("## How to read", 1)[0]
    for pin in (*PREAMBLE_HEADINGS, "[Unreleased]"):
        assert f"- {pin}" not in head, f"pinned heading {pin!r} is scaffolding, not an index entry"
        assert f"## {pin}" in text, f"pinned heading {pin!r} must still survive the eviction"
    # The positive control in the same fixture: real surviving entries ARE still listed, so a
    # regeneration that simply emitted nothing would not pass this test.
    for h in CHRON_HEADINGS[-3:]:
        assert f"- {h}" in head, f"surviving entry {h!r} must still be listed"


def test_a_crash_between_the_append_and_the_index_write_is_repaired_by_the_retry(
    tmp_path: Path,
) -> None:
    """The bullet that no rerun could recover. Collecting bullets per appended fragment put the
    collection inside the "not yet compiled" branch: a run interrupted after the body append and
    before the index write correctly skipped the RE-append on retry — and never re-collected the
    heading, so the body sat in the archive permanently absent from that archive's own index.

    `test_a_skipped_reappend_adds_no_duplicate_bullet` cannot see this: it reruns a fully
    SUCCESSFUL drain. The interrupted state has to be constructed, and it is constructed here as
    the script itself would leave it — sentinel and body present, index untouched."""
    stem = "2026-07-30-phase-x-a"
    repo = make_journal_repo(tmp_path, (stem,))
    archive = repo / JOURNAL_ARCHIVE_DIR / "2026-07.md"
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_text(
        "# Journal archive — 2026-07\n\n## 📑 Index\n\n---\n"
        f"\n<!-- fragment: {JOURNAL_DIR}/{stem}.md -->\n{journal_fragment(stem)}\n",
        encoding="utf-8",
    )
    result = _run(repo, "drain", "journal")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "skipping append (idempotent retry)" in result.stdout, (
        "the fixture must exercise the skip branch, or it is not the crash-retry case"
    )
    text = archive.read_text(encoding="utf-8")
    head = text.split("---\n", 1)[0]
    assert f"- {stem} entry" in head, "a retry must repair the index it never got to write"
    assert text.count(f"<!-- fragment: {JOURNAL_DIR}/{stem}.md -->") == 1, (
        "and must still not duplicate the body"
    )


# ------------------------------------------------------------------------------------------
# What the index regeneration written above could still get wrong
# ------------------------------------------------------------------------------------------


def test_a_note_under_the_archive_index_is_not_eaten_by_the_regeneration(
    tmp_path: Path,
) -> None:
    """Byte deletion, in a tool whose entire contract is that it moves bytes verbatim. The first
    version deleted EVERYTHING between the Index heading and the first `---`, reasoning that the
    region "is" the index; an archive carrying a one-line human note there lost it to a plain
    `drain journal` — exit 0, no warning.

    The monolith side of this same file already had the right rule and a test named for it
    (`test_a_preamble_line_below_the_index_is_not_eaten_by_the_collapse`). Two regenerators in
    one file, disagreeing on the same input."""
    keep = "NOTE: entries are newest-first; fragments were deleted after compilation."
    stem = "2026-07-30-phase-x-a"
    repo = make_journal_repo(tmp_path, (stem,))
    archive = repo / JOURNAL_ARCHIVE_DIR / "2026-07.md"
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_text(
        f"# Journal archive — 2026-07\n\n## 📑 Index\n\n{keep}\n\n---\n", encoding="utf-8"
    )
    archive.chmod(0o644)
    assert _run(repo, "drain", "journal").returncode == 0
    text = archive.read_text(encoding="utf-8")
    assert keep in text, "a human note below the index heading is body, not index"
    assert f"- {stem} entry" in text, "and the index is still regenerated around it"
    # Same run, second observation: `mktemp` files are 0600 and `mv` carries that mode onto the
    # destination. git does not track the mode, so no diff review can see a drain quietly
    # tightening an archive's permissions — only a run can.
    assert archive.stat().st_mode & 0o777 == 0o644, "the drain must not change the archive's mode"


def test_an_archive_with_no_pending_fragments_still_gets_its_index_repaired(
    tmp_path: Path,
) -> None:
    """The gap between the promise and the mechanism. Regenerating only the months this run wrote
    made "run the drain again and the index is repaired" unreachable for the one archive that
    motivated the fix: since fragments are filed by their own filename month, an archive for a
    month with nothing left in the hot directory can never be written again."""
    repo = make_journal_repo(tmp_path, ("2026-08-01-phase-x-b",))
    stale = repo / JOURNAL_ARCHIVE_DIR / "2026-05.md"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text(
        "# Journal archive — 2026-05\n\n## 📑 Index\n\n---\n"
        "\n<!-- fragment: docs/journal.d/2026-05-01-phase-old-x.md -->\n"
        "# old\n\n## an entry no drain will ever touch again\n\nbody\n",
        encoding="utf-8",
    )
    assert _run(repo, "drain", "journal").returncode == 0
    head = stale.read_text(encoding="utf-8").split("---\n", 1)[0]
    assert "- an entry no drain will ever touch again" in head, (
        "a month with no pending fragments is exactly the month that needs the repair"
    )


# ------------------------------------------------------------------------------------------
# The same deletion, through a different anchor; and the mode nobody could diff
# ------------------------------------------------------------------------------------------


def test_a_body_heading_ending_in_index_is_not_taken_as_the_index_anchor(
    tmp_path: Path,
) -> None:
    """The byte deletion above, again, one door along. The anchor was "the first `## …Index`
    heading anywhere in the file", so an archive whose HEADER has no index and whose BODY has a
    fragment titled `## how we rebuilt the Index` had the `- ` lines under that body heading
    treated as a stale index and dropped — silent, exit 0.

    The sibling this function was modelled on is structurally confined to the prefix region and
    could never have the problem; the rule was copied and the bound was not. The bound is now an
    interval that must exist — above the header separator — rather than a terminator the file
    might not contain, which is what the first attempt at this fix got wrong."""
    repo = make_journal_repo(tmp_path, ("2026-07-30-phase-x-a",))
    archive = repo / JOURNAL_ARCHIVE_DIR / "2026-07.md"
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_text(
        "# Journal archive — 2026-07\n\n<!-- fragment: docs/journal.d/x.md -->\n"
        "## how we rebuilt the Index\n\n- step one\n- step two\n\nprose after\n",
        encoding="utf-8",
    )
    result = _run(repo, "drain", "journal")
    assert result.returncode == 0, result.stdout + result.stderr
    text = archive.read_text(encoding="utf-8")
    assert "- step one" in text and "- step two" in text, "body bullets are body, not an index"
    assert "no --- separator" in result.stdout, (
        "and the skip must be said out loud, not inferred from the file being unchanged"
    )


def test_a_body_heading_ending_in_index_does_not_shadow_a_real_header_index(
    tmp_path: Path,
) -> None:
    """The positive control for the bound: the same body heading, in an archive that DOES have a
    header index. The header index must still be the one regenerated, and the body bullets must
    still survive — otherwise the fix above would pass by disabling the feature."""
    repo = make_journal_repo(tmp_path, ("2026-07-30-phase-x-a",))
    archive = repo / JOURNAL_ARCHIVE_DIR / "2026-07.md"
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_text(
        "# Journal archive — 2026-07\n\n## 📑 Index\n\n---\n"
        "\n<!-- fragment: docs/journal.d/x.md -->\n## how we rebuilt the Index\n\n- step one\n",
        encoding="utf-8",
    )
    assert _run(repo, "drain", "journal").returncode == 0
    text = archive.read_text(encoding="utf-8")
    head = text.split("---\n", 1)[0]
    assert "- 2026-07-30-phase-x-a entry" in head, "the header index is still regenerated"
    assert "- step one" in text, "and the body bullets still survive"


def test_a_stale_bullet_is_replaced_not_appended_to(tmp_path: Path) -> None:
    """The existing index block has to be IDENTIFIED to be replaced. Without the block scan the
    regeneration inserts beside the old bullets instead of over them, and a document's index
    grows a stale line per drain — the same accumulate-forever shape the stub collapse closed. No
    fixture reached this: every other archive fixture starts with an EMPTY index."""
    repo = make_journal_repo(tmp_path, ("2026-07-30-phase-x-a",))
    archive = repo / JOURNAL_ARCHIVE_DIR / "2026-07.md"
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_text(
        "# Journal archive — 2026-07\n\n## 📑 Index\n\n- a bullet from a previous run\n\n---\n",
        encoding="utf-8",
    )
    assert _run(repo, "drain", "journal").returncode == 0
    text = archive.read_text(encoding="utf-8")
    assert "- a bullet from a previous run" not in text, "regenerated means replaced, not added to"
    assert "- 2026-07-30-phase-x-a entry" in text


@pytest.mark.parametrize("mode", [0o644, 0o600])
def test_the_drain_preserves_each_archives_own_mode(tmp_path: Path, mode: int) -> None:
    """Not "the mode ends up 0644" — that assertion passes only where the umask is
    022. The temp was built with a shell redirect, so the archive's mode was replaced by
    `0666 & ~umask`: measured tightening 0644 → 0600 under `umask 077` and loosening 0600 →
    0644 under the default. Since every drain now rewrites every archive, that is churn on every
    file every time, and git does not track the mode, so no diff review could ever see it."""
    repo = make_journal_repo(tmp_path, ("2026-07-30-phase-x-a",))
    archive = repo / JOURNAL_ARCHIVE_DIR / "2026-07.md"
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_text("# Journal archive — 2026-07\n\n## 📑 Index\n\n---\n", encoding="utf-8")
    archive.chmod(mode)
    assert _run(repo, "drain", "journal").returncode == 0
    assert archive.stat().st_mode & 0o777 == mode, "the archive keeps its OWN mode, not the umask's"


def test_an_archive_the_drain_does_not_own_is_left_alone_and_silent(tmp_path: Path) -> None:
    """The widened regeneration loop is scoped to `YYYY-MM.md`, the only shape `drain_journal`
    creates. A bare `*.md` swept in pre-convention files and printed a ⚠
    about a file no drain will ever index, on every future drain. A permanent warning about
    something that will not change is the noise that costs the warnings that matter."""
    repo = make_journal_repo(tmp_path, ("2026-07-30-phase-x-a",))
    legacy = repo / JOURNAL_ARCHIVE_DIR / "legacy-2026-07-08.md"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text("# legacy\n\nno index here\n", encoding="utf-8")
    before = legacy.read_text(encoding="utf-8")
    result = _run(repo, "drain", "journal")
    assert result.returncode == 0, result.stdout + result.stderr
    assert legacy.read_text(encoding="utf-8") == before
    assert "legacy-2026-07-08.md" not in result.stdout, "not ours to index, and not ours to nag about"


# ------------------------------------------------------------------------------------------
# The adopter's lens: what the prose promises vs what the code does
# ------------------------------------------------------------------------------------------

NESTED_INDEX_HEADER = (
    "# QA log\n\n## Index\n\n"
    "- [2026-01-01 — topic A](#a)\n"
    "  - [Q1 — first](#q1)\n"
    "  - [Q2 — second](#q2)\n"
    "- [2026-02-01 — topic B](#b)\n\n"
)


def test_a_nested_index_bullet_does_not_strand_the_rest_of_the_old_index(
    tmp_path: Path,
) -> None:
    """The index fix, defeated by a nested index. The index-block scan was
    anchored `^- `, which does not match `  - [Q1 — …]`, so the run ended at the first sub-bullet:
    the regenerated list was flushed there and the WHOLE REMAINDER of the old index was emitted
    below it as body prose — anchors to the entries the drain had just evicted included.

    A qa-log whose index nests sub-bullets under its top-level ones is exactly that
    shape. Every fixture missed
    it because every fixture had a FLAT index. The hole was in the fixture shape, not the
    assertion."""
    repo = make_monolith_repo(tmp_path, CHRON_HEADINGS, header=NESTED_INDEX_HEADER)
    assert _run(repo, "drain", MONOLITH).returncode == 0
    text = (repo / MONOLITH).read_text()
    head = text.split("## [", 1)[0]
    assert "topic A" not in head and "topic B" not in head, (
        f"an evicted entry is still named in the regenerated head:\n{head}"
    )
    assert "(#q1)" not in head and "(#q2)" not in head, "the nested bullets are index, and go too"
    for h in CHRON_HEADINGS[-3:]:
        assert f"- {h}" in head, "and the survivors are still listed"


def test_a_drain_with_no_manifest_at_all_still_drains(tmp_path: Path) -> None:
    """`references/retention.md` promises the whole retention block is optional. The probe read
    `[ -f "$M" ] && jq …`, so an absent manifest short-circuited, the substitution exited non-zero,
    and the refusal arm fired — a greenfield adopter's very first drain rejected, naming a file
    they had just been told they do not need. The `""` arm written for this case was unreachable,
    so its comment documented an intention rather than a behaviour.

    Invisible to this suite because every other fixture passes a manifest: `make_fixture_repo`
    accepts `manifest=None` and nothing used it."""
    repo = make_fixture_repo(
        tmp_path, manifest=None, files={MONOLITH: monolith_body(CHRON_HEADINGS)}
    )
    result = _run(repo, "drain", MONOLITH)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "drained" in result.stdout, result.stdout


@pytest.mark.parametrize(
    ("label", "manifest"),
    [("a retention block of the wrong shape", {"retention": "not-an-object"})],
)
def test_a_malformed_manifest_still_refuses(
    tmp_path: Path, label: str, manifest: dict
) -> None:
    """The control for the test above, and the reason it cannot be satisfied by simply removing
    the refusal: "absent" and "present but unreadable" must keep landing on opposite answers."""
    repo = make_fixture_repo(tmp_path, manifest=manifest, files={MONOLITH: monolith_body(CHRON_HEADINGS)})
    result = _run(repo, "drain", MONOLITH)
    assert result.returncode != 0, result.stdout
    assert (repo / MONOLITH).read_text() == monolith_body(CHRON_HEADINGS), "and moves zero bytes"


def test_repeated_drains_do_not_accumulate_the_blank_under_the_stub(tmp_path: Path) -> None:
    """The stub collapse traded one accumulating line for another. The emitter writes stub-then-blank; the
    rewrite dropped the stub and not the blank, so the file still grew exactly one line per drain
    in exactly the same position — and the motivating evidence had been a line count.
    The state six drains leave is SEEDED, exactly as `test_stubs_never_accumulate_across_runs`
    seeds its six stubs — because looping the drain six times does not produce six drains: after
    the first one the source is down to the keep-window and every later call correctly reports
    "nothing to drain". A loop-based fixture here is green by construction, which is how the
    first version of this test passed against the unfixed script.

    The header carries NO index heading, and that is load-bearing rather than incidental: with an
    index present the `in_index` run swallows the blanks on its way past, so the accumulation is
    invisible. Measured — indexed header: 1 blank before the stub on both the fixed and unfixed
    script; indexless header: 7 blanks unfixed, 1 fixed. The first version of this test used an
    indexed header and was therefore green against the defect it is named for."""
    stub = "> Earlier entries archived verbatim (newest-first): → docs/archive/CHANGELOG-archive.md"
    header = "# Changelog\n\n" + f"{stub}\n\n" * 6
    repo = make_monolith_repo(tmp_path, CHRON_HEADINGS, header=header)
    assert _run(repo, "drain", MONOLITH).returncode == 0
    text = (repo / MONOLITH).read_text()
    head = text[: text.index("> Earlier entries")]
    assert len(stub_lines(text)) == 1, "one stub per file"
    assert "\n\n\n" not in head, (
        f"the blanks the collapsed stubs left behind accumulate in their place:\n{head!r}"
    )


# ══════════════════════════════════════════════════════════════════════════════════════
# The drain's pre-image and its restore.
#
# This whole block was written with ZERO production change, so every row below was RED on
# arrival. That
# ordering is deliberate, not a style choice: a
# fixture written after the mechanism encodes what the mechanism does rather than what the
# requirement demands.
#
# ══════════════════════════════════════════════════════════════════════════════════════

PREIMAGE_DIR = "docs/archive/.pre-images"
#: BESIDE the store, not inside it. F19 makes the store unwritable to force a refusal, and a
#: receipt living inside it could not record the very refusal it exists to make observable.
#: The fixture forced this before the mechanism was written, which is the argument for writing fixtures first.
PREIMAGE_INDEX = "docs/archive/.pre-images.log"

#: How many generations the store keeps. Small on purpose: a keep-N fixture has to run N+1
#: drains, and every one of them is a subprocess.
KEEP_N = 3


def _slots(repo: Path) -> list[str]:
    """Numbered slot directories, sorted. The store's whole state in one call."""
    store = repo / PREIMAGE_DIR
    if not store.is_dir():
        return []
    return sorted(p.name for p in store.iterdir() if p.is_dir())


def _index(repo: Path) -> list[str]:
    p = repo / PREIMAGE_INDEX
    return p.read_text(encoding="utf-8").splitlines() if p.is_file() else []


def _grow(repo: Path, tag: str, name: str = MONOLITH) -> None:
    """Append one fresh entry to a monolith.

    Needed between successive drains because a drain leaves exactly `KEEP` (3) entries, so a
    second drain on an untouched file returns "nothing to drain" BEFORE reaching the capture
    step — several fixtures were red for that reason and not for the one they name. Growing
    between drains is also what actually happens: documents accrue entries, then get drained.
    """
    p = repo / name
    p.write_text(p.read_text(encoding="utf-8") + f"## [{tag}] — 2026-12-01\n\nbody {tag}\n\n",
                 encoding="utf-8")


def _tree(repo: Path, *rel: str) -> dict[str, bytes]:
    """Byte snapshot of the named paths, for before/after comparison in the fixtures
    themselves. The fixtures must be able to say 'nothing moved' independently of the
    mechanism under test — otherwise a refusal test is only checking an exit code."""
    out: dict[str, bytes] = {}
    for r in rel:
        f = repo / r
        out[r] = f.read_bytes() if f.is_file() else b""
    return out


# ── Capture ───────────────────────────────────────────────────────────────────────────

def test_f1_a_monolith_drain_captures_both_files_before_mutating(tmp_path: Path) -> None:
    """F1 · AC1

    The drain mutates TWO files and the archive is appended first, so a store holding only
    the source restores half a lie.
    """
    repo = make_monolith_repo(tmp_path, CHRON_HEADINGS)
    before = _tree(repo, MONOLITH, ARCHIVE)
    assert _run(repo, "drain", MONOLITH).returncode == 0
    slots = _slots(repo)
    assert len(slots) == 1, f"expected exactly one pre-image slot, got {slots}"
    slot = repo / PREIMAGE_DIR / slots[0]
    manifest = (slot / "manifest").read_text(encoding="utf-8")
    recorded = {ln.split("\t", 1)[1]: ln.split("\t", 1)[0] for ln in manifest.splitlines() if ln}
    assert MONOLITH in recorded, f"the source is not in the manifest: {recorded}"
    assert ARCHIVE in recorded, f"the archive is not in the manifest: {recorded}"
    assert recorded[MONOLITH] == "present"
    # On a FIRST drain the archive does not exist yet, and 'absent' is state a restore has to
    # act on — otherwise restoring leaves behind a file the pre-drain tree never had.
    assert recorded[ARCHIVE] == "absent", "a not-yet-created archive must be recorded, not skipped"
    assert (slot / "files" / MONOLITH).is_file(), "the source's bytes were not stored"
    assert before  # the snapshot helper is load-bearing for F8; keep it exercised here


def test_f1b_captured_bytes_are_identical_not_merely_equivalent(tmp_path: Path) -> None:
    """F1 · AC2

    `cmp -s`, not "the entries are back": an undo that re-derives content is a second
    drain running backwards.
    """
    repo = make_monolith_repo(tmp_path, CHRON_HEADINGS)
    src_before = (repo / MONOLITH).read_bytes()
    assert _run(repo, "drain", MONOLITH).returncode == 0
    slot = repo / PREIMAGE_DIR / _slots(repo)[0]
    captured_src = next(p for p in slot.rglob("*") if p.name == "CHANGELOG.md")
    assert captured_src.read_bytes() == src_before


def test_f2_two_drains_in_the_same_second_get_distinct_keys(tmp_path: Path) -> None:
    """F2 · AC3

    A timestamp key collides on a coarse-resolution filesystem and the second
    capture silently overwrites the first. Back-to-back with no sleep is the point — a
    fixture that sleeps proves nothing about the property.
    """
    repo = make_monolith_repo(tmp_path, CHRON_HEADINGS)
    assert _run(repo, "drain", MONOLITH).returncode == 0
    first = _slots(repo)
    for i in range(4):
        _grow(repo, f"2.{i}.0")
    assert _run(repo, "drain", MONOLITH).returncode == 0
    second = _slots(repo)
    assert len(second) == len(first) + 1, f"second drain did not mint a new key: {second}"
    assert first[0] in second, "the first pre-image was overwritten by the second drain"


def test_f3_keep_n_prunes_the_oldest_and_the_drain_does_it(tmp_path: Path) -> None:
    """F3 · AC5

    Who prunes matters as much as that pruning happens: the retention discipline has no scheduler and
    names calendar-triggered maintenance an anti-pattern, so a separate `prune` command
    would rot unrun.
    """
    repo = make_monolith_repo(
        tmp_path,
        tuple(f"[1.{i}.0] — 2026-0{i}-01" for i in range(1, 9)),
        retention={"preimage_keep": KEEP_N},
    )
    for r in range(KEEP_N + 1):
        for i in range(4):
            _grow(repo, f"{r}.{i}.0")
        assert _run(repo, "drain", MONOLITH).returncode == 0
    slots = _slots(repo)
    assert len(slots) == KEEP_N, f"expected {KEEP_N} generations, got {slots}"
    assert slots == sorted(slots)[-KEEP_N:], "the pruned generation was not the oldest"


def test_f4_rollover_never_ingests_the_pre_image_store(tmp_path: Path) -> None:
    """F4 · AC6 — the assertion below first requires the store to be non-empty, so it cannot
    pass vacuously when no pre-image was taken.
    `scripts/invariants/preimage-invisible-to-rollover.sh` is the standing guard.

    Without an explicit exclusion the store is an archive-shaped tree under `$AD` and the
    roll-over pass eventually archives the tool's own backups — a self-eating archive.
    """
    repo = make_monolith_repo(tmp_path, CHRON_HEADINGS, retention={"preimage_keep": KEEP_N})
    assert _run(repo, "drain", MONOLITH, "1").returncode == 0
    assert _slots(repo), "no pre-image was taken, so this fixture cannot test the exclusion"
    segdir = repo / "docs/archive/CHANGELOG"
    if segdir.is_dir():
        blob = "".join(
            p.read_text(encoding="utf-8") for p in segdir.rglob("*.md") if p.is_file()
        )
        assert ".pre-images" not in blob, "roll-over ingested the pre-image store"


def test_f18_one_index_line_per_drain_naming_the_slot(tmp_path: Path) -> None:
    """F18 · AC4

    The receipt is how a drain is audited afterwards: one line per drain, naming its slot.
    """
    repo = make_monolith_repo(tmp_path, CHRON_HEADINGS)
    assert _run(repo, "drain", MONOLITH).returncode == 0
    assert len(_index(repo)) == 1, f"expected one receipt line, got {_index(repo)}"
    for i in range(4):
        _grow(repo, f"2.{i}.0")
    assert _run(repo, "drain", MONOLITH).returncode == 0
    lines = _index(repo)
    assert len(lines) == 2, f"expected two receipt lines, got {lines}"
    for line, slot in zip(lines, _slots(repo)):
        assert slot in line, f"receipt line does not name its slot: {line}"
        assert MONOLITH in line, f"receipt line does not name the source: {line}"


def test_f21_a_refused_drain_does_not_prune(tmp_path: Path) -> None:
    """F21 · AC5, second clause

    Pruning before capture destroys the oldest pre-image on behalf of a drain that never
    happened.
    """
    repo = make_monolith_repo(
        tmp_path,
        tuple(f"[1.{i}.0] — 2026-0{i}-01" for i in range(1, 9)),
        retention={"preimage_keep": KEEP_N},
    )
    for r in range(KEEP_N):
        for i in range(4):
            _grow(repo, f"{r}.{i}.0")
        assert _run(repo, "drain", MONOLITH).returncode == 0
    before = _slots(repo)
    assert len(before) == KEEP_N
    for i in range(4):
        _grow(repo, f"9.{i}.0")
    (repo / PREIMAGE_DIR).chmod(0o500)          # capture will fail; the drain must refuse
    try:
        assert _run(repo, "drain", MONOLITH).returncode != 0
        assert _slots(repo) == before, "a refused drain pruned the oldest generation"
    finally:
        (repo / PREIMAGE_DIR).chmod(0o700)


# ── Failure semantics ─────────────────────────────────────────────────────────────────

def test_f8_capture_failure_refuses_and_leaves_both_files_untouched(tmp_path: Path) -> None:
    """F8 · AC11 — a capture failure must refuse the drain.

    Asserts the FILES, not just `$?`. An exit-code-only assertion is how a refusal test
    passes while the refusal does not hold.

    ⚠️ The first draft of this fixture made `docs/archive` unwritable and PASSED on arrival —
    the drain refused, but because its own pre-existing archive write failed, which is a
    behaviour that predates the pre-image and has nothing to do with it. A
    fixture that is green before the mechanism exists is testing something else. Only the
    STORE is made unwritable here, so the sole reachable failure is the capture.
    """
    repo = make_monolith_repo(tmp_path, CHRON_HEADINGS)
    before = _tree(repo, MONOLITH, ARCHIVE)
    store = repo / PREIMAGE_DIR
    store.mkdir(parents=True, exist_ok=True)
    store.chmod(0o500)
    try:
        assert _run(repo, "drain", MONOLITH).returncode != 0, (
            "the drain completed even though its pre-image could not be written"
        )
        assert _tree(repo, MONOLITH, ARCHIVE) == before, "a refused drain mutated a file"
    finally:
        store.chmod(0o700)


def test_f10_a_failed_capture_leaves_no_half_written_slot(tmp_path: Path) -> None:
    """F10 · AC14

    Verify-then-`mv`, the INVERSE of the monolith drain's archive write (which is mv-first,
    verify-after). Copying that idiom would publish a slot before knowing it is good.
    """
    repo = make_monolith_repo(tmp_path, CHRON_HEADINGS)
    (repo / PREIMAGE_DIR).mkdir(parents=True, exist_ok=True)
    (repo / PREIMAGE_DIR).chmod(0o500)
    try:
        assert _run(repo, "drain", MONOLITH).returncode != 0
        assert _slots(repo) == [], "a failed capture left a slot behind"
    finally:
        (repo / PREIMAGE_DIR).chmod(0o700)


def test_f19_a_refusal_appends_its_own_index_line(tmp_path: Path) -> None:
    """F19 · AC20

    The design's recorded flip condition is 'capture failures turn out not to be rare'. A refusal
    that leaves no trace makes that condition unobservable — a rule asserting something its
    own trigger never checks.
    """
    repo = make_monolith_repo(tmp_path, CHRON_HEADINGS)
    assert _run(repo, "drain", MONOLITH).returncode == 0
    ok_lines = len(_index(repo))
    for i in range(4):
        _grow(repo, f"2.{i}.0")
    (repo / PREIMAGE_DIR).chmod(0o500)
    try:
        assert _run(repo, "drain", MONOLITH).returncode != 0
    finally:
        (repo / PREIMAGE_DIR).chmod(0o700)
    lines = _index(repo)
    assert len(lines) == ok_lines + 1, "the refusal left no trace in the index"
    assert "REFUSED" in lines[-1], f"the refusal line is not marked as one: {lines[-1]}"


def test_f17_no_argument_causes_the_pre_image_to_be_skipped(tmp_path: Path) -> None:
    """F17 · AC12 — no flag may bypass the pre-image.

    Phrased as the absence of a bypass, not as an error string: inventing a `--force` later
    must red this, and asserting today's generic 'no such file' message would not catch it.
    """
    repo = make_monolith_repo(tmp_path, CHRON_HEADINGS)
    for bypass in ("--force", "--no-preimage", "-f"):
        r = _run(repo, "drain", bypass)
        assert r.returncode != 0, f"{bypass} was accepted as a subcommand"
    # The bare-flag loop above was NOT enough, measured by mutation: a real bypass takes a file
    # argument, and a flag with no file exits non-zero for free under any implementation. The
    # mutant that adds a working `--no-preimage <file>` survived the whole suite on that gap.
    for bypass in ("--force", "--no-preimage", "--skip-preimage", "-f"):
        r = _run(repo, "drain", bypass, MONOLITH)
        if r.returncode == 0:
            assert _slots(repo), f"{bypass} {MONOLITH} succeeded AND skipped the pre-image"
    assert _run(repo, "drain", MONOLITH).returncode == 0
    assert _slots(repo), "the ordinary drain took no pre-image"


# ── Restore ───────────────────────────────────────────────────────────────────────────

def test_f5_restore_puts_both_files_back_byte_identically(tmp_path: Path) -> None:
    """F5 · AC7, AC9 — restore is byte-identical and re-runnable."""
    repo = make_monolith_repo(tmp_path, CHRON_HEADINGS)
    before = _tree(repo, MONOLITH, ARCHIVE)
    assert _run(repo, "drain", MONOLITH).returncode == 0
    key = _slots(repo)[0]
    assert _run(repo, "restore", key).returncode == 0
    assert _tree(repo, MONOLITH, ARCHIVE) == before, "restore was not byte-identical"
    after_first = _tree(repo, MONOLITH, ARCHIVE)
    assert _run(repo, "restore", key).returncode == 0, "restore is not re-runnable"
    assert _tree(repo, MONOLITH, ARCHIVE) == after_first, "the second restore differed"


def test_f6_restore_captures_what_it_is_about_to_overwrite(tmp_path: Path) -> None:
    """F6 · AC8

    The window between a bad drain and its discovery routinely contains legitimate later
    writes; a blind-overwriting restore destroys them silently, trading one silent
    data-loss class for another.
    """
    repo = make_monolith_repo(tmp_path, CHRON_HEADINGS)
    assert _run(repo, "drain", MONOLITH).returncode == 0
    key = _slots(repo)[0]
    (repo / MONOLITH).write_text("# Changelog\n\n## edited after the drain\n\nnew\n")
    intervening = (repo / MONOLITH).read_bytes()
    assert _run(repo, "restore", key).returncode == 0
    slots = _slots(repo)
    assert len(slots) >= 2, "restore minted no pre-image of the state it overwrote"
    newest = repo / PREIMAGE_DIR / slots[-1]
    saved = next(p for p in newest.rglob("*") if p.name == "CHANGELOG.md")
    assert saved.read_bytes() == intervening, "restore did not preserve the intervening write"


def test_f7_restore_of_an_unknown_key_refuses_and_moves_nothing(tmp_path: Path) -> None:
    """F7 · AC10 — an unknown key is refused while a known one is accepted.

    ⚠️ The first draft asserted only that `restore 9999` exits non-zero, and PASSED on
    arrival — an unknown subcommand exits non-zero for free, so the fixture was green while
    `restore` did not exist and said nothing whatsoever about key validation. The fix is to
    make the fixture distinguish the two: an unknown key must be refused AND a known key
    must be accepted. Only a real `restore` satisfies both halves.
    """
    repo = make_monolith_repo(tmp_path, CHRON_HEADINGS)
    assert _run(repo, "drain", MONOLITH).returncode == 0
    before = _tree(repo, MONOLITH, ARCHIVE)
    slots_before = _slots(repo)
    assert _run(repo, "restore", "9999").returncode != 0, "an unknown key was accepted"
    assert _tree(repo, MONOLITH, ARCHIVE) == before, "a refused restore mutated a file"
    assert _slots(repo) == slots_before, "a refused restore touched the store"
    assert _run(repo, "restore", slots_before[0]).returncode == 0, (
        "a KNOWN key was refused too — the fixture cannot tell refusal from absence"
    )


def test_f9_restore_refuses_when_its_own_capture_cannot_be_taken(tmp_path: Path) -> None:
    """F9 · AC13

    The refusal is one refusal reached from both call sites. Do not assume the AC11 mutant
    reaches this one — that assumption is what 'one routine' makes tempting, and it has
    been measured going wrong.
    """
    repo = make_monolith_repo(tmp_path, CHRON_HEADINGS)
    assert _run(repo, "drain", MONOLITH).returncode == 0
    key = _slots(repo)[0]
    before = _tree(repo, MONOLITH, ARCHIVE)
    (repo / PREIMAGE_DIR).chmod(0o500)
    try:
        assert _run(repo, "restore", key).returncode != 0
        assert _tree(repo, MONOLITH, ARCHIVE) == before, "a refused restore mutated a file"
    finally:
        (repo / PREIMAGE_DIR).chmod(0o700)


def test_f20_keep_n_holds_under_restore_with_no_drain_between(tmp_path: Path) -> None:
    """F20 · AC5, first clause

    Restore mints a slot through the same routine and is re-runnable by design, so pruning
    from `drain` alone leaves an unbounded growth path — the exact family keep-N exists
    to foreclose.
    """
    repo = make_monolith_repo(
        tmp_path,
        tuple(f"[1.{i}.0] — 2026-0{i}-01" for i in range(1, 9)),
        retention={"preimage_keep": KEEP_N},
    )
    assert _run(repo, "drain", MONOLITH).returncode == 0
    key = _slots(repo)[0]
    for _ in range(KEEP_N + 1):
        assert _run(repo, "restore", key).returncode == 0
    assert len(_slots(repo)) == KEEP_N, f"restore grew the store past keep-N: {_slots(repo)}"


# ── The other three modes ─────────────────────────────────────────────────────────────

def test_f11_qa_log_captures_the_fragments_it_deletes(tmp_path: Path) -> None:
    """F11 · AC18

    `drain qa-log` DELETES its fragments. A pre-image that
    covers only rewritten files does not cover this mode at all.
    """
    repo = make_fixture_repo(
        tmp_path,
        manifest={"retention": {"archive_dir": "docs/archive", "preimage_keep": KEEP_N}},
        files={"docs/qa-log.d/2026-08-04-x.md": "# frag\n\n## x entry\n\nbody\n"},
    )
    assert _run(repo, "drain", "qa-log").returncode == 0
    assert _slots(repo), "qa-log drain took no pre-image"
    slot = repo / PREIMAGE_DIR / _slots(repo)[0]
    names = [p.name for p in slot.rglob("*") if p.is_file()]
    assert "2026-08-04-x.md" in names, f"the deleted fragment was not captured: {names}"


def test_f12_journal_captures_the_fragments_it_deletes(tmp_path: Path) -> None:
    """F12 · AC18 (the delete loop in `drain_journal`.)"""
    repo = make_journal_repo(tmp_path, ("2026-08-04-a",), retention={"preimage_keep": KEEP_N})
    assert _run(repo, "drain", "journal").returncode == 0
    assert _slots(repo), "journal drain took no pre-image"
    slot = repo / PREIMAGE_DIR / _slots(repo)[0]
    names = [p.name for p in slot.rglob("*") if p.is_file()]
    assert "2026-08-04-a.md" in names, f"the deleted fragment was not captured: {names}"


def test_f13_legacy_captures_the_file_it_overwrites_with_a_stub(tmp_path: Path) -> None:
    """F13 · AC18 (the stub write is `pointer_stub` in `drain_legacy`.)"""
    repo = make_fixture_repo(
        tmp_path,
        manifest={"retention": {"archive_dir": "docs/archive", "preimage_keep": KEEP_N}},
        files={"OLD.md": "# old\n\n## entry\n\nbody\n"},
    )
    original = (repo / "OLD.md").read_bytes()
    assert _run(repo, "drain", "legacy", "OLD.md").returncode == 0
    assert _slots(repo), "legacy drain took no pre-image"
    slot = repo / PREIMAGE_DIR / _slots(repo)[0]
    saved = next(p for p in slot.rglob("*") if p.name == "OLD.md")
    assert saved.read_bytes() == original


def test_f14_f15_f16_restore_recreates_deleted_fragments(tmp_path: Path) -> None:
    """F14–F16 · AC19

    Putting back the archive and the hot doc while the fragments stay deleted is NOT a
    restore: AC2's bar is the tree, not the files someone happened to think of.
    """
    repo = make_journal_repo(
        tmp_path, ("2026-08-04-a", "2026-08-04-b"), retention={"preimage_keep": KEEP_N}
    )
    frags = sorted((repo / JOURNAL_DIR).glob("*.md"))
    before = {f.name: f.read_bytes() for f in frags}
    assert _run(repo, "drain", "journal").returncode == 0
    assert not list((repo / JOURNAL_DIR).glob("*.md")), "the drain did not delete the fragments"
    assert _run(repo, "restore", _slots(repo)[0]).returncode == 0
    after = {f.name: f.read_bytes() for f in (repo / JOURNAL_DIR).glob("*.md")}
    assert after == before, "restore did not re-create the deleted fragments byte-identically"


def test_f22_the_rewrite_failure_no_longer_says_safe_to_re_run(tmp_path: Path) -> None:
    """F22 · the rewrite-failure message.

    The source-rewrite failure branch printed "archive already updated — safe to re-run". That
    is false: `drain_monolith` has no idempotence sentinel (unlike `drain_journal` /
    `drain_qa_log`), so a re-run appends the same entries to the archive a second time and
    the byte-count + first-line check passes both times.

    This fixture does NOT add the missing sentinel — it pins the message. Before it, the branch had no
    test at all (grep for 'safe to re-run' / 'rewrite.*fail' / 'chmod.*000' over this file found
    nothing), which is how a printed instruction stayed wrong long enough to be filed.

    The rewrite is forced to fail by making the repo ROOT unwritable: the archive lives under
    `docs/archive/` and is unaffected, so the drain gets all the way to `mv … "$src"` and only
    that step fails — the exact branch under test, reached for the right reason.
    """
    repo = make_monolith_repo(tmp_path, CHRON_HEADINGS)
    # The archive dir must exist BEFORE the root is locked: the script's unconditional
    # `mkdir -p "$AD"` at :82 runs before any drain logic, so without this the run dies there
    # and the fixture would be green for a reason three hundred lines away from the branch it
    # claims to test — the F8 mistake, again.
    (repo / "docs/archive").mkdir(parents=True, exist_ok=True)
    repo.chmod(0o500)
    try:
        r = _run(repo, "drain", MONOLITH)
        assert r.returncode != 0, "the rewrite did not fail; this fixture tested nothing"
        out = r.stdout + r.stderr
        assert "safe to re-run" not in out, f"the false instruction is back: {out}"
        assert "do NOT re-run" in out, f"the branch no longer warns against re-running: {out}"
        assert "restore" in out, f"the message names no way back: {out}"
    finally:
        repo.chmod(0o700)


def test_f23_the_store_is_not_a_drain_target(tmp_path: Path) -> None:
    """F23 · AC6 — added because a mutant survived the suite.

    Removing the store-is-not-a-document guard was KILLED by `preimage-invisible-to-rollover.sh` and SURVIVED the pytest
    suite: F4 only checks that roll-over segments do not mention the store, and never points
    the drain AT it. The property was genuinely guarded and genuinely untested *here*, and the
    matrix runs the suite — so a future refactor that kept the invariant passing (or ran with
    invariants skipped) had no suite-level guard at all.
    """
    repo = make_monolith_repo(tmp_path, CHRON_HEADINGS)
    assert _run(repo, "drain", MONOLITH).returncode == 0
    victim = next(p for p in (repo / PREIMAGE_DIR).rglob("*.md") if p.is_file())
    rel = str(victim.relative_to(repo))
    before = _tree(repo, MONOLITH, ARCHIVE)
    slots_before = _slots(repo)
    r = _run(repo, "drain", rel)
    assert r.returncode != 0, f"draining a file inside the store succeeded: {r.stdout}"
    assert _tree(repo, MONOLITH, ARCHIVE) == before, "the refused drain still mutated a file"
    assert _slots(repo) == slots_before, "the refused drain still touched the store"


# ── Two critical defects, pinned before the fix ──

def test_f24_restore_removes_a_month_archive_the_drain_created(tmp_path: Path) -> None:
    """F24 · AC2's tree bar, AC19 — RED before the fix.

    `drain journal` captures `$frags` plus the month archives that ALREADY exist. A fragment
    whose target month has no archive yet makes the drain CREATE one — a path that was never in
    the capture's argument list, so it is not in the manifest at all, not even as `absent`.
    `restore` therefore leaves it behind, holding a duplicate of the drained content, and still
    reports "byte-verified".

    The comment justifying the glob says the touched set "is not knowable here without
    re-deriving the fragment-to-month mapping" — but `fragment_month()` IS that mapping, it is a standalone
    function, and it is called on each fragment a few lines later. The set is derivable.
    """
    repo = make_journal_repo(tmp_path, ("2026-08-04-a",), retention={"preimage_keep": KEEP_N})
    before = sorted(p.name for p in (repo / JOURNAL_ARCHIVE_DIR).glob("*.md")) \
        if (repo / JOURNAL_ARCHIVE_DIR).is_dir() else []
    assert before == [], "this fixture needs a repo with no month archive yet"
    assert _run(repo, "drain", "journal").returncode == 0
    created = sorted(p.name for p in (repo / JOURNAL_ARCHIVE_DIR).glob("*.md"))
    assert created, "the drain did not create a month archive, so this fixture tests nothing"
    assert _run(repo, "restore", _slots(repo)[0]).returncode == 0
    after = sorted(p.name for p in (repo / JOURNAL_ARCHIVE_DIR).glob("*.md")) \
        if (repo / JOURNAL_ARCHIVE_DIR).is_dir() else []
    assert after == before, (
        f"restore left behind an archive the pre-drain tree never had: {after} (was {before})"
    )


def test_f25_a_fragment_name_with_a_space_is_really_captured(tmp_path: Path) -> None:
    """F25 · AC1, AC11 — RED before the fix.

    `capture_preimage "drain journal" $frags …` is unquoted (a deliberate SC2086 site). A
    fragment named with a space word-splits into three nonexistent partial paths, each recorded
    `absent`, and the capture returns SUCCESS. The drain then deletes the real fragment, and the
    receipt says OK.

    Measured, not reasoned: the manifest reads
        absent  docs/journal.d/2026-08-04
        absent  a
        absent  fragment.md
    and the store holds zero files while the fragment is gone.

    This is a live counter-example to the pre-image's central claim — "if the pre-image cannot be
    taken, the drain refuses and moves nothing". Here it silently was not taken, and the drain
    proceeded, indistinguishable from a protected run.
    """
    repo = make_fixture_repo(
        tmp_path,
        manifest={"retention": {"archive_dir": "docs/archive", "preimage_keep": KEEP_N}},
        files={"docs/journal.d/2026-08-04 a fragment.md": "# frag\n\n## entry a\n\nbody a\n"},
    )
    original = (repo / "docs/journal.d/2026-08-04 a fragment.md").read_bytes()
    r = _run(repo, "drain", "journal")
    if r.returncode == 0:
        # Either the drain captured the real file, or it must not have proceeded at all.
        slot = repo / PREIMAGE_DIR / _slots(repo)[0]
        stored = [p for p in slot.rglob("*") if p.is_file() and p.name == "2026-08-04 a fragment.md"]
        assert stored, (
            "the drain succeeded and deleted the fragment, but no pre-image of it exists — "
            f"manifest was: {(slot / 'manifest').read_text(encoding='utf-8')!r}"
        )
        assert stored[0].read_bytes() == original
    else:
        # Refusing is an acceptable answer; silently proceeding unprotected is not.
        assert (repo / "docs/journal.d/2026-08-04 a fragment.md").is_file(), (
            "the drain refused but had already deleted the fragment"
        )


def test_f26_restore_removes_what_rollover_created(tmp_path: Path) -> None:
    """F26 · AC2's tree bar — RED before the fix.

    `check_rollover` runs inside the same invocation as the drain, after the capture, and creates
    a segment directory plus an index while rewriting the archive to a stub. None of that was in
    any manifest, so `restore` put the archive back and left an orphaned directory of files the
    pre-drain tree never had — while reporting byte-verified.
    """
    # Entries must be big enough that the archive passes 4x the cap, or roll-over never fires and
    # the fixture is vacuous. The assertion below catches that rather than passing quietly — the
    # first draft of this fixture did exactly that and said so.
    headings = tuple(f"[1.{i}.0] — 2026-0{i}-01" for i in range(1, 9))
    body = "\n".join("padding line for the roll-over threshold" for _ in range(30))
    repo = make_fixture_repo(
        tmp_path,
        manifest={"retention": {"archive_dir": "docs/archive", "preimage_keep": KEEP_N}},
        files={MONOLITH: "# Changelog\n\n" + "".join(f"## {h}\n\n{body}\n\n" for h in headings)},
    )
    segdir = repo / "docs/archive/CHANGELOG"
    assert not segdir.exists(), "this fixture needs a repo with no segment dir yet"
    assert _run(repo, "drain", MONOLITH, "1").returncode == 0
    assert segdir.is_dir() and list(segdir.glob("*.md")), "roll-over did not fire; fixture is vacuous"
    assert _run(repo, "restore", _slots(repo)[0]).returncode == 0
    left = sorted(p.name for p in segdir.glob("*")) if segdir.exists() else []
    assert left == [], f"restore left roll-over output behind: {left}"


# ══════════════════════════════════════════════════════════════════════════════════════
# The restore double — S1..S6.
#
# Two byte-verification guards in `retention-drain.sh` had NO fixture that could reach them:
# `drain_restore`'s `cmp -s` and `capture_preimage`'s `cmp -s`. In both, the adjacent `cp`
# already owns every failure it can have, so the only state that fires the `cmp` is
# "cp exited 0 and the bytes differ" — and tampering with the source tampers with the
# comparison target too. A mutation matrix measured the consequence: deleting the
# restore-side line left every fixture entirely green, the only
# survivor of twenty mutants.
#
# The double is a PATH-shimmed `cp`. The shipped script is NOT modified for testability:
# two properties (every `cp`/`cmp` in the script is a bare invocation, never `/bin/cp`; and
# the script never references `PATH`) are what make that possible.
#
# DECLARED LIMIT: the shim proves the line can FIRE. It says nothing about
# whether a real `cp` ever exits 0 while writing different bytes — no portable mechanism
# for that exists, and four were checked. Reachability, not realism.
# ══════════════════════════════════════════════════════════════════════════════════════

#: A regex that matches no path. The shim always has a rule; "no corruption" is expressed as
#: a rule that cannot match, never as an unset variable — an unset variable in an ERE match
#: is an empty pattern, and an empty ERE matches EVERYTHING.
#: `/dev/null` is a character device, so no path the shim will ever test (it only corrupts
#: something `-f` already accepted) can live below it.
SHIM_MATCHES_NOTHING = "^/dev/null/matches-nothing$"

_SHIM_SOURCE = r"""#!/bin/bash
# Test double for `cp`. Obligations:
#   1. lie selectively — corrupt ONLY a destination the fixture named, delegate the rest;
#   2. record WHICH call and WHICH outcome, not merely that it ran;
#   3. be the only file in this directory (asserted by S6 / AC13).
set -u
real=/bin/cp
log="${PLC_SHIM_LOG:?shim invoked without a log}"
re="${PLC_SHIM_CORRUPT_RE:?shim invoked without a rule}"

dest="${@: -1}"
case "$dest" in
  /*) abs="$dest" ;;
  *)  abs="$PWD/$dest" ;;
esac
# Resolve the DIRECTORY part physically. On macOS `mktemp -d` hands back /var/folders/...,
# a symlink to /private/var/folders/... — a matcher that normalises differently from the
# script's own path construction misses silently, the shim delegates, `cmp` passes because
# the bytes really are identical, and a fixture built to prove a failure branch proves
# nothing.
_d="$(cd "$(dirname "$abs")" 2>/dev/null && pwd -P)" || _d="$(dirname "$abs")"
abs="${_d%/}/$(basename "$abs")"

"$real" "$@"; rc=$?

if [ "$rc" -eq 0 ] && [ -f "$abs" ] && [[ $abs =~ $re ]]; then
  printf 'x' >> "$abs"
  printf 'corrupt\t%s\n' "$abs" >> "$log"
else
  printf 'delegate\t%s\n' "$abs" >> "$log"
fi
exit "$rc"
"""


def _shim(tmp_path: Path, name: str = "shim") -> tuple[Path, Path]:
    """A directory holding exactly one executable, `cp`, plus the log it writes to.

    The log lives OUTSIDE the shim directory on purpose: AC13 asserts the directory holds
    exactly one entry, and a receipt sitting inside the thing it describes would break the
    very rule it was written to record.
    """
    d = tmp_path / name
    d.mkdir()
    cp = d / "cp"
    cp.write_text(_SHIM_SOURCE, encoding="utf-8")
    cp.chmod(0o755)
    log = tmp_path / f"{name}.log"
    log.write_text("", encoding="utf-8")

    # On a hardened runner `chmod +x` succeeds and execution still fails (noexec
    # temp mount). The resulting "command not found" reads as the PRODUCTION script's `cp`
    # being broken, i.e. a false Critical against retention-drain.sh itself. Prove the shim
    # runs before any scenario depends on it.
    src = tmp_path / f"{name}-probe-src"
    src.write_text("probe\n", encoding="utf-8")
    dst = tmp_path / f"{name}-probe-dst"
    probe = subprocess.run(
        [str(cp), str(src), str(dst)],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PLC_SHIM_LOG": str(log), "PLC_SHIM_CORRUPT_RE": SHIM_MATCHES_NOTHING},
    )
    assert probe.returncode == 0, f"the shim is not executable here: {probe.stderr}"
    assert dst.read_text(encoding="utf-8") == "probe\n", "the shim did not delegate the probe copy"
    log.write_text("", encoding="utf-8")  # the probe is setup, not evidence
    return d, log


def _run_shimmed(
    repo: Path, *args: str, shim: Path, log: Path, corrupt_re: str = SHIM_MATCHES_NOTHING
) -> subprocess.CompletedProcess[str]:
    """Run the drain with the shim first on PATH — for the SUBPROCESS ONLY.

    `env=` is passed explicitly and `os.environ` is never mutated: an assertion
    raising before teardown would otherwise leave the shim on PATH for the rest of the
    session, and a later unrelated test whose destination collides with the corruption
    target would fail with this double's error message, attributed to the wrong test, with
    the shim gone by the time anyone looked.
    """
    env = {
        **os.environ,
        "PATH": f"{shim}:{os.environ.get('PATH', '')}",
        "PLC_SHIM_LOG": str(log),
        "PLC_SHIM_CORRUPT_RE": corrupt_re,
    }
    return subprocess.run(
        ["bash", str(DRAIN), *args], cwd=repo, capture_output=True, text=True, check=False, env=env
    )


def _shim_log(log: Path) -> list[tuple[str, str]]:
    return [
        (ln.split("\t", 1)[0], ln.split("\t", 1)[1])
        for ln in log.read_text(encoding="utf-8").splitlines()
        if "\t" in ln
    ]


def _re_exact(path: Path) -> str:
    """An ERE matching exactly one resolved absolute path."""
    return "^" + re.escape(str(path.resolve())) + "$"


def _whole_tree(repo: Path) -> dict[str, bytes]:
    """Every file under `repo`, by relative path, as bytes.

    AC4 compares the WHOLE tree rather than an exit code: a shim that delegated but wrote
    one stray byte somewhere would pass any exit-code assertion. The one normalisation is
    the pre-image receipt, whose every line carries a UTC timestamp (`preimage_log`,
    retention-drain.sh:112-115) — two runs a second apart differ there for a reason that has
    nothing to do with the shim, so that column is masked rather than the file skipped.
    """
    out: dict[str, bytes] = {}
    for p in sorted(repo.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(repo))
        # `.git/` is excluded, and the exclusion is load-bearing rather than tidy: the fixture
        # repo is created by `git init` + one commit, and two commits made a second apart carry
        # different SHAs for identical content. Comparing them would red this fixture for a
        # reason with nothing to do with the shim — and, worse, would train the next reader to
        # loosen the comparison instead of narrowing it.
        if rel == ".git" or rel.startswith(".git" + os.sep):
            continue
        data = p.read_bytes()
        if rel == PREIMAGE_INDEX:
            data = b"\n".join(
                b"\t".join(c if i != 1 else b"<ts>" for i, c in enumerate(ln.split(b"\t")))
                for ln in data.splitlines()
            )
        out[rel] = data
    return out


def test_s1_the_restore_byte_check_can_actually_fire(tmp_path: Path) -> None:
    """S1 · AC1 — the headline. Deleting retention-drain.sh's restore-side `cmp -s` used to
    leave the whole suite green (the only survivor of twenty mutants).

    RED before the shim existed only in the sense that no fixture reached the line at all;
    what this asserts is that the line, when reached, refuses.
    """
    repo = make_monolith_repo(tmp_path, CHRON_HEADINGS)
    assert _run(repo, "drain", MONOLITH).returncode == 0
    key = _slots(repo)[0]
    shim, log = _shim(tmp_path)

    result = _run_shimmed(
        repo, "restore", key, shim=shim, log=log, corrupt_re=_re_exact(repo / MONOLITH)
    )

    out = result.stdout + result.stderr
    assert result.returncode != 0, f"a restore that wrote different bytes reported success:\n{out}"
    assert "differs after restore" in out, f"the byte check did not name itself:\n{out}"
    assert MONOLITH in out, f"the failure does not say WHICH path differed:\n{out}"


def test_s2_the_preimage_byte_check_can_actually_fire(tmp_path: Path) -> None:
    """S2 · AC2 — the twin at capture_preimage.

    Same shape as S1 one function away, and it carries a second obligation the restore side
    does not: a refused capture must leave NO slot behind, or the store accrues half-written
    generations that a later restore would trust.
    """
    repo = make_monolith_repo(tmp_path, CHRON_HEADINGS)
    shim, log = _shim(tmp_path)

    # The staged copy, not the repo file: capture_preimage copies INTO $stage/files/<rel>
    # and compares the two. Anchoring on /files/ is what keeps this from also matching the
    # restore-side write, which is S1's target.
    result = _run_shimmed(
        repo, "drain", MONOLITH, shim=shim, log=log, corrupt_re=r"/files/" + re.escape(MONOLITH) + "$"
    )

    out = result.stdout + result.stderr
    assert result.returncode != 0, f"a pre-image that stored different bytes was accepted:\n{out}"
    assert "failed verification" in out, f"the capture-side byte check did not name itself:\n{out}"
    assert "refusing to drain" in out, f"the refusal did not stop the drain:\n{out}"
    assert _slots(repo) == [], "a refused capture left a slot behind"


def test_s3_the_fixture_asserts_the_corrupting_call_specifically(tmp_path: Path) -> None:
    """S3 · AC3 — 'the shim fired' is too weak an assertion.

    One `drain_restore` run makes several legitimate `cp` calls: `cp -R` stages the slot
    once, `cp -p` writes once per manifest line. A log recording only THAT the shim ran lets
    this pass on the staging call while the intended corruption never happened — which is
    exactly how a silent miss ends up looking like a green.
    """
    repo = make_monolith_repo(tmp_path, CHRON_HEADINGS)
    assert _run(repo, "drain", MONOLITH).returncode == 0
    key = _slots(repo)[0]
    shim, log = _shim(tmp_path)

    target = repo / MONOLITH
    assert _run_shimmed(
        repo, "restore", key, shim=shim, log=log, corrupt_re=_re_exact(target)
    ).returncode != 0

    entries = _shim_log(log)
    assert entries, "the shim never ran at all — the scenario proved nothing"
    corrupted = [p for outcome, p in entries if outcome == "corrupt"]
    delegated = [p for outcome, p in entries if outcome == "delegate"]
    assert corrupted == [str(target.resolve())], (
        f"the corrupting call is not the one the fixture named: corrupted={corrupted}"
    )
    assert delegated, (
        "every call was corrupted — the shim is not selective, so the fixture's own setup "
        "is running through a lying cp (the shim's obligation 1)"
    )


def test_s3b_an_absolute_cp_defeats_the_shim_and_the_log_is_what_says_so(tmp_path: Path) -> None:
    """S3b · AC3's demonstration — if anyone later writes `/bin/cp` in the script,
    the bare-invocation property breaks and the shim silently stops intercepting.

    Measured, not reasoned: a throwaway copy of the script with the restore-side `cp` made
    absolute is run through S1's exact scenario. The claim under test is that the LOG is the
    thing that names the failure — it records zero corruption events.

    "Zero corruption events" is ALSO what a run that never reached a `cp` produces, so the log
    alone does not make this un-foolable and the earlier version of this docstring said it did.
    The two liveness assertions below are what close that: without them this test passes against
    a script that exits before doing anything (measured: rc=9, zero log entries, assertion green).
    """
    repo = make_monolith_repo(tmp_path, CHRON_HEADINGS)
    assert _run(repo, "drain", MONOLITH).returncode == 0
    key = _slots(repo)[0]
    shim, log = _shim(tmp_path)

    stale = tmp_path / "retention-drain-absolute-cp.sh"
    source = DRAIN.read_text(encoding="utf-8")
    hardened = source.replace(
        '        cp -p "$stage/files/$rel" "$rel" 2>/dev/null',
        '        /bin/cp -p "$stage/files/$rel" "$rel" 2>/dev/null',
    )
    assert hardened != source, "the restore-side cp line moved; this demonstration is stale"
    stale.write_text(hardened, encoding="utf-8")

    env = {
        **os.environ,
        "PATH": f"{shim}:{os.environ.get('PATH', '')}",
        "PLC_SHIM_LOG": str(log),
        "PLC_SHIM_CORRUPT_RE": _re_exact(repo / MONOLITH),
    }
    result = subprocess.run(
        ["bash", str(stale), "restore", key],
        cwd=repo, capture_output=True, text=True, check=False, env=env,
    )

    assert result.returncode == 0, (
        "the hardened copy did not complete the restore, so its empty corruption list says "
        f"nothing about the shim:\n{result.stdout}{result.stderr}"
    )
    entries = _shim_log(log)
    assert entries, "the shim recorded nothing at all — this run never reached a `cp`"
    corrupted = [p for outcome, p in entries if outcome == "corrupt"]
    assert corrupted == [], (
        "the shim still intercepted an absolute /bin/cp — this demonstration no longer "
        f"demonstrates anything: {corrupted}"
    )


def test_s4_a_shim_with_no_target_is_byte_identical_to_no_shim(tmp_path: Path) -> None:
    """S4 · AC4 — the shim delegates faithfully.

    Compared on the WHOLE tree rather than on an exit code: a double that delegated but wrote
    one stray byte anywhere would satisfy any returncode assertion and quietly poison every
    fixture built on top of it.
    """
    (tmp_path / "plain").mkdir()
    (tmp_path / "shimmed").mkdir()
    plain = make_monolith_repo(tmp_path / "plain", CHRON_HEADINGS)
    shimmed = make_monolith_repo(tmp_path / "shimmed", CHRON_HEADINGS)
    shim, log = _shim(tmp_path)

    assert _run(plain, "drain", MONOLITH).returncode == 0
    assert _run_shimmed(shimmed, "drain", MONOLITH, shim=shim, log=log).returncode == 0

    assert _whole_tree(plain) == _whole_tree(shimmed), "a delegating shim changed the outcome"
    outcomes = {outcome for outcome, _ in _shim_log(log)}
    assert outcomes == {"delegate"}, f"a run with no target corrupted something: {outcomes}"


def test_s5_the_staging_and_capture_copies_are_untouched_in_s1(tmp_path: Path) -> None:
    """S5 · AC5 — the corruption is confined to the one destination the fixture names.

    `cp -R` at retention-drain.sh:141 stages the slot and `cp -p` at :280 captures. A shim
    that corrupted either would break the fixture's own setup and S1 would then be red for a
    reason that has nothing to do with the guard it exists to reach.
    """
    repo = make_monolith_repo(tmp_path, CHRON_HEADINGS)
    assert _run(repo, "drain", MONOLITH).returncode == 0
    key = _slots(repo)[0]
    slot_bytes = (repo / PREIMAGE_DIR / key / "files" / MONOLITH).read_bytes()
    pre_restore = (repo / MONOLITH).read_bytes()
    shim, log = _shim(tmp_path)

    assert _run_shimmed(
        repo, "restore", key, shim=shim, log=log, corrupt_re=_re_exact(repo / MONOLITH)
    ).returncode != 0

    assert (repo / PREIMAGE_DIR / key / "files" / MONOLITH).read_bytes() == slot_bytes, (
        "the shim corrupted the stored pre-image the restore was reading from"
    )
    # The restore's own pre-image of what it was about to overwrite is a `cp -p` into a fresh
    # slot; it must have gone through untouched, or the escape route out of a bad restore is
    # itself corrupt.
    #
    # Asserted by BYTE IDENTITY against the state that capture was taken of. The assertion this
    # replaces was `b"padding" not in newest.read_bytes() or newest.read_bytes()[-1:] != b"x"` —
    # and `monolith_body` emits `body of <heading>`, never the string `padding`, so the left
    # disjunct was unconditionally true and the right one was never evaluated. It passed in
    # exactly the case it names.
    newest = repo / PREIMAGE_DIR / _slots(repo)[-1] / "files" / MONOLITH
    assert newest.is_file(), "the restore took no pre-image of the state it was overwriting"
    assert newest.read_bytes() == pre_restore, (
        "the restore's own capture does not match the state it was capturing — the shim "
        "corrupted the escape route out of a bad restore"
    )


def test_s6_the_shim_directory_holds_exactly_one_entry(tmp_path: Path) -> None:
    """S6 · AC13 — the shim's obligation 3: its directory holds exactly one entry.

    Later fixtures will want their own doubles. Absent this, a contributor reuses
    this directory and adds a fake `mv`; nothing fails at test time, and a later unrelated
    test's real `mv` is silently intercepted, masking a genuine data-loss bug elsewhere.
    """
    shim, _ = _shim(tmp_path)
    assert sorted(p.name for p in shim.iterdir()) == ["cp"], (
        f"the shim directory grew: {sorted(p.name for p in shim.iterdir())}"
    )


# ── check_rollover's return code, and the retry it invites (S7..S12) ─────────────
#
# `[ "$rc" -eq 0 ] && check_rollover …` leaves check_rollover's status in a `$?` nobody
# reads, so a failed roll-over exited 0 from both call sites. Propagating that alone
# would have been a NET REGRESSION: the month split writes in append mode, so the operator's
# correct response to a newly visible failure — retry — appended the same entries again.
# The two ship together, and S10 is what makes "together"
# a property of the tree rather than a reviewer's promise.

def _rollover_repo(
    tmp_path: Path, months: tuple[str, ...] = ("01", "02", "03", "04", "05", "06", "07", "08")
) -> Path:
    """A repo whose archive will cross 4x the cap on `drain <monolith> 1`.

    Bodies are padded because roll-over is size-gated: a fixture whose archive never crosses
    the threshold exercises nothing and passes quietly, which F26 recorded happening once.
    """
    body = "\n".join("padding line for the roll-over threshold" for _ in range(30))
    headings = tuple(f"[1.{i}.0] — 2026-{m}-01" for i, m in enumerate(months, start=1))
    return make_fixture_repo(
        tmp_path,
        manifest={"retention": {"archive_dir": "docs/archive", "preimage_keep": KEEP_N}},
        files={MONOLITH: "# Changelog\n\n" + "".join(f"## {h}\n\n{body}\n\n" for h in headings)},
    )



def _extend(repo: Path, month: str, tags: tuple[str, ...]) -> None:
    """Append dated entries landing in one named `YYYY-MM` month.

    `_grow` hardcodes a single date, so every entry it adds lands in the same segment. The
    retry-safety fixtures need to choose which month an entry belongs to — one the segment
    tree already holds, and one it does not — because that ordering is what decides whether a
    blocked split leaves a half-written file behind or dies on its first write.
    """
    body = "\n".join("padding line for the roll-over threshold" for _ in range(30))
    p = repo / MONOLITH
    p.write_text(
        p.read_text(encoding="utf-8")
        + "".join(f"## [{t}] — {month}-0{i}\n\n{body}\n\n" for i, t in enumerate(tags, 1)),
        encoding="utf-8",
    )


def _entry_counts(segdir: Path) -> dict[str, int]:
    """How many times each entry heading appears across every segment file."""
    counts: dict[str, int] = {}
    for f in sorted(segdir.glob("*.md")):
        if f.name == "index.md":
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.startswith("## "):
                counts[line] = counts.get(line, 0) + 1
    return counts


def _undated_rollover_repo(tmp_path: Path, tags: tuple[str, ...]) -> Path:
    """A repo whose archive crosses 4x the cap and whose entry headings carry NO date.

    The date is what chooses the branch: `check_rollover` splits by month only when every entry
    heading is dated, and falls back to a line-count `split` otherwise. This repo's own qa-log
    archive takes the second branch, so it is the branch the close drain actually runs.
    """
    body = "\n".join("padding line for the roll-over threshold" for _ in range(30))
    return make_fixture_repo(
        tmp_path,
        manifest={"retention": {"archive_dir": "docs/archive", "preimage_keep": KEEP_N}},
        files={MONOLITH: "# Changelog\n\n" + "".join(f"## [{t}]\n\n{body}\n\n" for t in tags)},
    )


def test_s21_a_second_undated_rollover_keeps_the_first_rollovers_segments(tmp_path: Path) -> None:
    """A roll-over must not DESTROY what an earlier roll-over wrote. RED before the fix.

    MEASURED, which is how this was found: the close drain of a phase rolled
    the qa-log archive over a second time and **entry headings stopped existing anywhere in
    the working tree** -- one archive segment lost most of its lines, others
    were rewritten, and the only surviving copy of that content was inside the
    pre-image ring. In a phase whose entire subject is "the ring is an undo buffer, not evidence",
    the closing step itself made the ring the last copy. git had the content, so nothing was lost
    for good -- which is exactly the cold-storage path this phase rewrote the drain's comment to
    name.

    THE TWO BRANCHES OF ONE VERBATIM-MOVE CONTRACT DISAGREE, and the script's own comment says
    that is a defect rather than a layout choice -- about a different disagreement. The staged
    directory is seeded with a copy of the existing segments, and the month branch APPENDS into
    that copy (`>> out`). The undated branch runs `split -l 2000 "$archive" "$stage/part-"` and
    then renames each piece to `part-XX.md`, which OVERWRITES the seeded copy of the same name.
    So the seeding comment ("seeding it wrong would trade duplicated content for lost content,
    which is the worse of the two") describes a protection the second branch does not get.
    """
    first = _undated_rollover_repo(tmp_path, tuple(f"1.{i}.0" for i in range(1, 9)))
    assert _run(first, "drain", MONOLITH, "1").returncode == 0
    segdir = first / "docs/archive/CHANGELOG"
    before = _entry_counts(segdir)
    assert before, "roll-over did not fire; fixture is vacuous"
    assert sorted(p.name for p in segdir.glob("part-*.md")), (
        "this fixture must take the line-count branch; a month-split segment set means the "
        "headings were dated after all and the test measures the wrong branch"
    )

    body = "\n".join("padding line for the roll-over threshold" for _ in range(30))
    mono = first / MONOLITH
    mono.write_text(
        mono.read_text(encoding="utf-8")
        + "".join(f"## [2.{i}.0]\n\n{body}\n\n" for i in range(1, 9)),
        encoding="utf-8",
    )
    assert _run(first, "drain", MONOLITH, "1").returncode == 0

    after = _entry_counts(segdir)
    lost = [h for h in before if h not in after]
    assert not lost, (
        f"{len(lost)} entry heading(s) written by the FIRST roll-over are gone after the second: "
        + ", ".join(lost[:6])
    )


def test_s12_a_successful_rollover_still_exits_zero(tmp_path: Path) -> None:
    """S12 · AC7 — the success path is unchanged, and it is asserted BEFORE S7 leans on it.

    S7's claim is "the non-zero came from the roll-over". That claim is worth nothing unless
    the same command with the same fixture exits 0 when the roll-over is left alone — without
    this control, S7 would pass just as well against a script that failed for any other reason.
    """
    repo = _rollover_repo(tmp_path)
    result = _run(repo, "drain", MONOLITH, "1")
    assert result.returncode == 0, result.stdout + result.stderr
    segdir = repo / "docs/archive/CHANGELOG"
    assert segdir.is_dir() and list(segdir.glob("*.md")), (
        "roll-over never fired; this fixture and S7's control are both vacuous"
    )


def test_s7_a_failed_rollover_makes_the_dispatch_arm_exit_non_zero(tmp_path: Path) -> None:
    """S7 · AC6 — the top-level dispatch arm (the `drain <monolith>` case in the dispatcher).

    Cited by NAME, not by line. The line numbers this docstring and S8's used to carry were both
    stale by the time anyone read them: later changes inserted lines above them, and the fix for the Critical
    below inserted more, so `:1246-1248` had drifted into `archive_working`'s refusal branch and
    `:1101-1102` onto the `drain_monolith` call. Same shape as the mutation harness's rule that a
    mutant is named by the TEXT it removes and never by a line number.

    Also the regression guard for a data-loss defect an intermediate version introduced:
    the old code reached `$segdir` through `mkdir -p`, which failed loudly when a
    non-directory sat there; the staged swap reaches it through `rm -rf`, which would have
    DELETED it. The blocking file must still be on disk afterwards.
    """
    repo = _rollover_repo(tmp_path)
    blocker = repo / "docs/archive/CHANGELOG"
    blocker.parent.mkdir(parents=True, exist_ok=True)
    blocker.write_text("not a directory\n", encoding="utf-8")

    result = _run(repo, "drain", MONOLITH, "1")

    out = result.stdout + result.stderr
    assert result.returncode != 0, f"a failed roll-over still reported success:\n{out}"
    assert "refusing to roll over" in out, f"the failure does not name itself:\n{out}"
    assert blocker.is_file() and blocker.read_text(encoding="utf-8") == "not a directory\n", (
        "the roll-over deleted a non-directory it should have refused"
    )


def test_s8_a_failed_rollover_makes_drain_qa_log_exit_non_zero(tmp_path: Path) -> None:
    """S8 · AC6 — the other call site, the `check_rollover` at drain_qa_log's tail.

    One defect, two call sites; fixing one and assuming the other is fixed by similarity is the move
    to refuse. drain_qa_log passes cap 50, so the archive has to cross
    200K before check_rollover does anything at all — the assertion below checks that it did,
    because a fixture that never reaches the code under test passes for free.
    """
    mono = "docs/brainstorming-qa-log.md"
    body = "\n".join(f"padding line {i} for the qa-log roll-over threshold" for i in range(700))
    headings = tuple(f"Q{i} — 2026-0{(i % 9) + 1}-01" for i in range(1, 11))
    repo = make_fixture_repo(
        tmp_path,
        manifest={"retention": {"archive_dir": "docs/archive"}},
        files={
            mono: "# Brainstorming QA log\n\n"
            + "".join(f"## {h}\n\n{body}\n\n" for h in headings),
            "docs/qa-log.d/2026-07-01-a.md": "## Q99 — 2026-07-01\n\nbody\n",
        },
    )
    blocker = repo / "docs/archive/brainstorming-qa-log"
    blocker.parent.mkdir(parents=True, exist_ok=True)
    blocker.write_text("not a directory\n", encoding="utf-8")

    result = _run(repo, "drain", "qa-log")

    out = result.stdout + result.stderr
    assert "refusing to roll over" in out, (
        f"the qa-log archive never crossed 4x50K, so this fixture never reached "
        f"check_rollover and proves nothing:\n{out}"
    )
    assert result.returncode != 0, f"drain_qa_log swallowed the roll-over failure:\n{out}"
    assert blocker.read_text(encoding="utf-8") == "not a directory\n"


def test_s9_a_failed_rollover_leaves_the_segment_dir_exactly_as_it_found_it(
    tmp_path: Path,
) -> None:
    """S9 · AC8 — retry safety, stated as the property that actually closes the defect.

    The month split appends (`out != "" { print >> out }`), so a run that died partway used to
    leave half-written segments, and the retry the new non-zero exit INVITES appended the same
    entries again. The fix does not make a retry-over-partial-state clean — it makes the
    partial state unreachable, by building the new segment tree beside the old one and moving
    it into place only after every step succeeded.

    The injection is a read-only `$segdir`, and it fails the swap: `rm -rf "$segdir"` needs
    write permission on that directory. `$segdir` must be byte-identical afterwards, and the
    retry that follows must produce exactly one copy of every entry.
    """
    repo = _rollover_repo(tmp_path)
    segdir = repo / "docs/archive/CHANGELOG"

    # First roll-over succeeds, so there is a real prior state for a failure to preserve.
    assert _run(repo, "drain", MONOLITH, "1").returncode == 0
    assert _entry_counts(segdir), "roll-over never fired; the fixture is vacuous"
    before = _whole_tree(segdir)

    # Grow the monolith so a SECOND roll-over has new entries to contribute, in a deliberate
    # ORDER: a hostile `$segdir` lets an entry APPEND to a month the tree already has (write
    # permission lives on the existing FILE) and blocks one that needs a NEW month (creating a
    # file needs the DIRECTORY). Only that sequence — append, then block — leaves the
    # half-written state a retry could double; blocked-first dies before touching anything.
    #
    # The order below looks backwards and is not. MEASURED, after the first draft assumed the
    # archive was oldest-first and this fixture stayed green against a genuinely no-staging
    # implementation: the drain writes the archive in reverse MONOLITH POSITION ("newest-first"
    # in its own message — position, not date), and it keeps the last few entries by that same
    # position. So the SECOND `_extend` here supplies the archive's FIRST entries. The new month
    # therefore has to be extended FIRST to end up split LAST.
    _extend(repo, "2027-11", ("5.1.0", "5.2.0", "5.3.0", "5.4.0"))
    _extend(repo, "2026-03", tuple(f"6.{i}.0" for i in range(1, 9)))

    # Injected on `$segdir`, NOT on the archive directory. Measured, after the first draft got
    # this wrong and the mutation matrix caught it: a read-only archive dir fails the ARCHIVE
    # WRITE inside `drain_monolith` ("✗ archive write failed … Permission denied"), which runs
    # BEFORE check_rollover is ever called — so every run this fixture called "a failed
    # roll-over" was really a failed drain, upstream of the code it names.
    segdir.chmod(0o500)
    try:
        blocked = _run(repo, "drain", MONOLITH, "1")
    finally:
        segdir.chmod(0o700)
    out = blocked.stdout + blocked.stderr
    assert "drained" in out, (
        f"the drain itself failed, so this fixture is measuring the wrong component:\n{out}"
    )
    # LIVENESS — the roll-over has to have been REACHED, or everything below is about a run that
    # never touched the mechanism this fixture names.
    assert "rolled over" in out or "✗" in out, (
        f"the roll-over was never reached, so nothing below measures it:\n{out}"
    )
    # THE PROPERTY, not the injection. This used to assert `returncode != 0` — that a read-only
    # `$segdir` makes the roll-over fail. It no longer does, and that is the fix working: the
    # swap became two renames inside `$AD`, and renaming a directory within its own parent needs
    # write permission on the PARENT, not on the directory being moved. MEASURED — this run now
    # exits 0 and rolls over successfully. What retry safety actually claims survives that change:
    # either the run completed, or it left the tree exactly as it found it.
    assert blocked.returncode == 0 or _whole_tree(segdir) == before, (
        f"a roll-over reported failure with the segment tree already mutated:\n{out}"
    )

    # And the retry: every entry exactly once, nothing doubled.
    assert _run(repo, "drain", MONOLITH, "1").returncode == 0
    doubled = {h: n for h, n in _entry_counts(segdir).items() if n != 1}
    assert doubled == {}, f"the retry duplicated entries into the segments: {doubled}"


def test_s10_propagation_and_retry_safety_are_the_same_assertion(tmp_path: Path) -> None:
    """S10 · AC14 — the bundling rule, enforced rather than stated.

    The rule is "the two ship together or neither ships", but AC6 and AC8 are
    independently satisfiable as written, so a tree carrying only the propagation would have
    gone green and a reviewer would have had to remember the rule. Both halves live in ONE
    test: a tree with a visible failure and a dirty retry fails here, and so does a tree with
    a clean retry and a silent failure.

    That ordering matters more than it looks. A visible failure with a dirty retry is WORSE
    than the silence it replaced, because the silence never invited anyone to retry.

    An earlier version of this test discriminated nothing S9 did not: every mutant
    killing it also killed S9, and S9 additionally did the `_whole_tree` comparison this one
    omitted. Both halves of that are now addressed — the injection makes the roll-over actually
    fail (so removing the propagation kills this and not S9, which no longer asserts a non-zero
    exit), and the tree comparison is here too.
    """
    repo = _rollover_repo(tmp_path)
    segdir = repo / "docs/archive/CHANGELOG"
    assert _run(repo, "drain", MONOLITH, "1").returncode == 0
    for i in range(5, 9):
        _grow(repo, f"3.{i}.0")

    # Ordered growth — see S9 for why the order is load-bearing, and for why the NEW month is
    # extended first rather than second.
    _extend(repo, "2027-11", ("5.1.0", "5.2.0", "5.3.0", "5.4.0"))
    _extend(repo, "2026-03", tuple(f"6.{i}.0" for i in range(1, 9)))
    before = _whole_tree(segdir)

    # The injection has to make the ROLL-OVER genuinely fail, or there is no return code for the
    # propagation half to carry and this test silently becomes a retry-safety test with an extra
    # docstring. That is not hypothetical: this fixture used a read-only `$segdir`, and when the
    # swap became two renames inside `$AD` that stopped failing at all — MEASURED, the mutant
    # removing the propagation stopped killing this test while it still went green. A directory
    # where the staged archive stub must be written fails the roll-over and nothing else.
    #
    # The `drained` assertion is not decoration either: a read-only ARCHIVE DIR fails
    # `drain_monolith` instead, and this fixture spent one round asserting against that.
    blocker = segdir.parent / f"{segdir.name}.rollover-archive"
    blocker.mkdir()

    # HALF ONE — the failure is visible, and it is the ROLL-OVER that failed.
    blocked = _run(repo, "drain", MONOLITH, "1")
    out = blocked.stdout + blocked.stderr
    assert "drained" in out, f"the drain failed, not the roll-over:\n{out}"
    assert blocked.returncode != 0, f"AC6 half: the roll-over failure was swallowed:\n{out}"

    # HALF TWO — and the retry that failure invites is clean. Same run, same injection: an
    # implementation that reports the failure but leaves half-written segments behind fails
    # HERE, in the same test, which is what makes "the two ship together" a property of the
    # tree rather than a rule a reviewer has to remember.
    assert _whole_tree(segdir) == before, f"AC8 half: the failed roll-over mutated the tree:\n{out}"
    blocker.rmdir()
    assert _run(repo, "drain", MONOLITH, "1").returncode == 0
    doubled = {h: n for h, n in _entry_counts(segdir).items() if n != 1}
    assert doubled == {}, f"AC8 half: the retry duplicated {doubled}"


def test_s11_the_undated_branch_is_measured_not_assumed_safe(tmp_path: Path) -> None:
    """S11 · AC15 — check_rollover has two branches with different retry semantics.

    The dated path appends (`print >> out`); the undated path runs `split -l 2000`, which
    OVERWRITES `part-aa…`. Their failure residues are therefore different — stale segments
    from a longer first run rather than duplicated entries — so similarity may not
    stand in for measurement.

    What is asserted here is the same property S9 asserts for the dated branch: a failed
    roll-over leaves the segment tree untouched.
    """
    body = "\n".join(f"undated padding line {i}" for i in range(120))
    repo = make_fixture_repo(
        tmp_path,
        manifest={"retention": {"archive_dir": "docs/archive", "preimage_keep": KEEP_N}},
        files={
            MONOLITH: "# Changelog\n\n"
            + "".join(
                f"## release {n}\n\n{body}\n\n"
                for n in ("alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta")
            )
        },
    )
    segdir = repo / "docs/archive/CHANGELOG"

    assert _run(repo, "drain", MONOLITH, "1").returncode == 0
    assert segdir.is_dir(), (
        "roll-over never fired at all — the archive stayed under 4x the cap, so this fixture "
        "says nothing about either branch"
    )
    parts = sorted(p.name for p in segdir.glob("part-*"))
    assert parts, (
        f"roll-over fired but took the DATED branch; this fixture is measuring the wrong one: "
        f"{sorted(x.name for x in segdir.iterdir())}"
    )
    # CONSTRUCTED, not observed — and the fixture is worth nothing without it. `split` writes
    # `part-aa`, and the rename loop immediately moves it to `part-aa.md`, so on a second run
    # every split target is a NEW name; in a read-only `$segdir` the split then dies on its
    # FIRST output and no partial write is ever reachable. MEASURED: without these two files a
    # no-staging implementation leaves the tree untouched too, and the assertion at the bottom
    # of this test passes against the very shape it exists to reject.
    #
    # Seeding the bare (`.md`-less) names is the state a pre-staging run genuinely leaves if it
    # dies between `split` and the rename — so the blocked split's first outputs land on
    # existing writable files and only the rename is refused.
    for stale in ("part-aa", "part-ab"):
        (segdir / stale).write_text(f"stale {stale}\n", encoding="utf-8")
    before = _whole_tree(segdir)

    # Grow the monolith so a second roll-over is genuinely due, then block it. Without this the
    # blocked run could exit 0 for the mundane reason that the archive is back under the cap,
    # and the assertion below would pass while measuring nothing.
    for n in ("iota", "kappa", "lambda", "mu", "nu", "xi"):
        p = repo / MONOLITH
        p.write_text(p.read_text(encoding="utf-8") + f"## release {n}\n\n{body}\n\n",
                     encoding="utf-8")
    segdir.chmod(0o500)
    try:
        blocked = _run(repo, "drain", MONOLITH, "1")
    finally:
        segdir.chmod(0o700)

    out = blocked.stdout + blocked.stderr
    assert "drained" in out, (
        "the drain failed rather than the roll-over — same mis-injection S9 was repaired for"
    )
    assert "rolled over" in out or "✗" in out, (
        f"the undated branch's roll-over was never reached, so this fixture never measured the "
        f"residue it exists to measure:\n{out}"
    )
    # Same reframing as S9: a read-only `$segdir` stopped being able to fail the swap once the
    # swap became two renames within `$AD`. The residue property is what this asserts.
    assert blocked.returncode == 0 or _whole_tree(segdir) == before, (
        f"a roll-over reported failure with the undated branch's tree already mutated:\n{out}"
    )


def test_s13_a_failure_below_the_swap_cannot_leave_a_doubling_retry(tmp_path: Path) -> None:
    """S13 · AC8 — the same property S9 asserts, reached where S9 structurally cannot go.

    S9, S10 and S11 all inject on `$segdir`. That injection fails AT the swap, so none of them
    ever reaches the steps that run BELOW it — and the archive rewrite used to be one of them.

    MEASURED on the tracked implementation, no mutant, one injection (a read-only archive FILE
    with `$AD` and `$segdir` both left writable): `check_rollover` returned 1 from
    `✗ cannot rewrite …` with `$segdir` ALREADY replaced and `$archive` still holding all eight
    entries, and the retry that non-zero exit invites split them into the new tree a second time
    and exited 0. EIGHT headings at x2, out of the thirteen the tree then held — the first draft
    of this line said twelve, which is neither number and was corrected by re-running it. That is
    the "visible failure with a dirty retry" the docstring above calls WORSE than the silence it
    replaced.

    The property is asserted rather than the mechanism: whatever the exit code, either the run
    completed or it left the tree alone, and the retry doubles nothing. A future rewrite that
    reorders these steps differently still has to satisfy it.
    """
    repo = _rollover_repo(tmp_path)
    segdir = repo / "docs/archive/CHANGELOG"
    archive = repo / "docs/archive/CHANGELOG-archive.md"

    assert _run(repo, "drain", MONOLITH, "1").returncode == 0
    assert _entry_counts(segdir), "roll-over never fired; the fixture is vacuous"
    before = _whole_tree(segdir)

    # Written directly, because a SUCCESSFUL roll-over always leaves the archive as a small
    # pointer stub — an archive that is both large and unrolled is exactly the state a previous
    # run left behind. Entries land in a month the tree already has and in months it does not.
    body = "\n".join("padding line for the roll-over threshold" for _ in range(30))
    archive.write_text(
        "# CHANGELOG — archive\n\n"
        + "".join(
            f"## [{t}] — {m}\n\n{body}\n\n"
            for t, m in (
                ("7.1.0", "2026-03-09"), ("7.2.0", "2026-03-10"),
                ("7.3.0", "2027-11-01"), ("7.4.0", "2027-11-02"),
                ("7.5.0", "2027-11-03"), ("7.6.0", "2027-11-04"),
                ("7.7.0", "2027-11-05"), ("7.8.0", "2027-11-06"),
            )
        ),
        encoding="utf-8",
    )
    # Liveness, computed rather than inferred from the output: below 4x the cap `check_rollover`
    # returns at its size gate and this fixture measures nothing at all.
    kb = archive.stat().st_size // 1024
    assert kb > 4, f"the archive is {kb}K, under 4x the cap of 1K — the roll-over never fires"

    # The injection has to SURVIVE the drain. A run with entries to move rewrites the archive
    # through a temp file and `mv`, which replaces the inode and resets the mode — measured, the
    # first attempt at this fixture lost its own injection that way and reported a clean pass.
    # The monolith here is inside its keep-window, so `drain_monolith` leaves the archive alone.
    archive.chmod(0o444)
    assert not os.access(archive, os.W_OK), "the injection did not take; this fixture is vacuous"
    try:
        blocked = _run(repo, "drain", MONOLITH, "1")
    finally:
        archive.chmod(0o644)
    out = blocked.stdout + blocked.stderr

    # LIVENESS. The assertion below is satisfied by a clean run, so an injection that was silently
    # undone before `check_rollover` saw it would pass here for the wrong reason — which is exactly
    # what happened to this fixture's first draft, and exactly the gap a review found in S3b one
    # commit earlier. Measured: without this line, deleting the `chmod` above leaves the test green
    # against the mutant it exists to kill. `nothing to drain` is the drain declining to rewrite
    # the archive, which is what carries the read-only mode into the roll-over.
    assert "nothing to drain" in out, (
        f"the drain rewrote the archive and replaced its inode, so the read-only injection never "
        f"reached check_rollover and this run measured nothing:\n{out}"
    )

    assert blocked.returncode == 0 or _whole_tree(segdir) == before, (
        "a roll-over failed below the swap: it reported the failure with the segment tree "
        f"already replaced, so the retry it invites will double every entry:\n{out}"
    )
    assert _run(repo, "drain", MONOLITH, "1").returncode == 0
    doubled = {h: n for h, n in _entry_counts(segdir).items() if n != 1}
    assert doubled == {}, f"the retry duplicated entries into the segments: {doubled}"


def test_s14_a_second_rollover_keeps_what_the_first_one_archived(tmp_path: Path) -> None:
    """S14 · AC8's other half — the stage begins as a COPY of the existing segments.

    `check_rollover` seeds `$stage` from `$segdir` before splitting, and the source says seeding
    it wrong "would trade duplicated content for lost content, which is the worse of the two".
    Nothing measured that. Removing the seeding block leaves every other case in this file green:
    `_entry_counts` reports headings whose count `!= 1`, and a heading that vanished entirely has
    count 0, so it is simply absent from the dict and invisible to S9 and S10 alike.

    MEASURED: against a copy with the seeding removed, the second roll-over drops the five
    entries the first one archived (2026-01 through 2026-05) while every assertion in this file
    stays green.
    """
    repo = _rollover_repo(tmp_path)
    segdir = repo / "docs/archive/CHANGELOG"

    assert _run(repo, "drain", MONOLITH, "1").returncode == 0
    first = set(_entry_counts(segdir))
    assert first, "roll-over never fired; the fixture is vacuous"

    _extend(repo, "2027-11", ("5.1.0", "5.2.0", "5.3.0", "5.4.0"))
    _extend(repo, "2026-03", tuple(f"6.{i}.0" for i in range(1, 9)))
    assert _run(repo, "drain", MONOLITH, "1").returncode == 0

    lost = first - set(_entry_counts(segdir))
    assert lost == set(), (
        f"the second roll-over dropped entries the first one had already archived: {sorted(lost)}"
    )


def test_s15_the_archive_stub_is_staged_before_the_swap_not_after(tmp_path: Path) -> None:
    """S15 · AC8 — the ORDER of the two halves of the retry-safety fix, not just its outcome.

    The fix did two things: it moved the archive rewrite above the swap, and it changed the write
    into a rename. S13 only discriminates the second — measured: putting the staging
    back below the swap while keeping `mv -f` leaves the entire suite green, because S13's
    injection (a read-only archive file) is one `mv -f` sails through.

    So this fixture makes the STAGING itself fail. `$newarchive` is derived from `$segdir` rather
    than from the random staging directory precisely so a fixture can reach it: a directory
    sitting at that path cannot be written to as a file. If the staging runs before the swap the
    tree is untouched; if it runs after, the tree has already been replaced when the failure is
    reported, which is the shape S13's docstring describes.
    """
    repo = _rollover_repo(tmp_path)
    segdir = repo / "docs/archive/CHANGELOG"

    assert _run(repo, "drain", MONOLITH, "1").returncode == 0
    assert _entry_counts(segdir), "roll-over never fired; the fixture is vacuous"
    before = _whole_tree(segdir)

    _extend(repo, "2027-11", ("5.1.0", "5.2.0", "5.3.0", "5.4.0"))
    _extend(repo, "2026-03", tuple(f"6.{i}.0" for i in range(1, 9)))

    # A directory where the staged archive stub has to be written.
    blocker = segdir.parent / f"{segdir.name}.rollover-archive"
    blocker.mkdir()
    (blocker / "occupied").write_text("not a regular file\n", encoding="utf-8")

    blocked = _run(repo, "drain", MONOLITH, "1")
    out = blocked.stdout + blocked.stderr

    assert "drained" in out, f"the drain failed, so the roll-over is not what this measured:\n{out}"
    assert blocked.returncode != 0, (
        f"the staged archive write could not be made to fail, so this fixture never reached the "
        f"step it exists to order:\n{out}"
    )
    assert _whole_tree(segdir) == before, (
        "the roll-over reported a failure with the segment tree already replaced — the archive "
        "stub is being staged BELOW the swap"
    )
    assert blocker.is_dir() and (blocker / "occupied").is_file(), (
        "the roll-over wrote over a directory it should have refused"
    )


def test_s16_a_failed_swap_never_destroys_the_previous_segments(tmp_path: Path) -> None:
    """S16 · AC8 — `rm -rf` is not a swap.

    The swap was `rm -rf "$segdir" && mv "$stage" "$segdir"`. `rm -rf` is not all-or-nothing: it
    deletes what it can and reports failure afterwards. MEASURED on the tracked implementation —
    one entry inside `$segdir` that cannot be unlinked left the other FIVE segment files already
    deleted, the archive still a pointer stub from the earlier run, and the entries recorded
    `absent` in the pre-image slot, so `restore` would have removed them rather than brought them
    back. The retry then exited 0. Permanent, silent loss of previously archived content.

    The fix moves `$segdir` aside with a rename and only removes it after the new tree is in
    place. This asserts the property that makes that fix worth having: whatever happens to the
    roll-over, nothing the previous one archived may disappear.
    """
    repo = _rollover_repo(tmp_path)
    segdir = repo / "docs/archive/CHANGELOG"

    assert _run(repo, "drain", MONOLITH, "1").returncode == 0
    first = set(_entry_counts(segdir))
    assert first, "roll-over never fired; the fixture is vacuous"

    _extend(repo, "2027-11", ("5.1.0", "5.2.0", "5.3.0", "5.4.0"))
    _extend(repo, "2026-03", tuple(f"6.{i}.0" for i in range(1, 9)))

    # A subdirectory that `rm -rf` cannot empty: the file inside it cannot be unlinked because the
    # directory holding it is not writable. `rm -rf "$segdir"` therefore removes the plain segment
    # files FIRST and only then fails, which is what makes the loss partial and silent.
    stubborn = segdir / "stubborn"
    stubborn.mkdir()
    (stubborn / "keep.txt").write_text("x\n", encoding="utf-8")
    stubborn.chmod(0o500)
    try:
        blocked = _run(repo, "drain", MONOLITH, "1")
        after = set(_entry_counts(segdir)) if segdir.is_dir() else set()
        lost = first - after
        assert lost == set(), (
            f"a roll-over destroyed {len(lost)} previously archived entries on its way to "
            f"reporting a failure: {sorted(lost)}\n{blocked.stdout}{blocked.stderr}"
        )

        # And the retry cannot bring them back, which is why the loss above is permanent rather
        # than merely alarming — asserted here so the guard is about durability, not one run.
        retry = _run(repo, "drain", MONOLITH, "1")
        final = set(_entry_counts(segdir)) if segdir.is_dir() else set()
        assert first - final == set(), (
            f"the retry left {sorted(first - final)} permanently gone:\n{retry.stdout}{retry.stderr}"
        )
    finally:
        stubborn.chmod(0o700)


def _rolled(segdir: Path) -> list[str]:
    """Every line of every segment file, index.md excluded (it is generated, not moved)."""
    lines: list[str] = []
    for f in sorted(segdir.glob("*.md")):
        if f.name == "index.md":
            continue
        lines.extend(f.read_text(encoding="utf-8").splitlines())
    return lines


def test_s18_the_month_split_moves_every_line_including_what_precedes_the_first_entry(
    tmp_path: Path,
) -> None:
    """The roll-over is a verbatim MOVE, so no line of the archive may vanish in it.

    The month split assigns each line to the segment named by the nearest PRECEDING `## ` heading,
    and it writes nothing while no heading has been seen yet. Everything above the first entry is
    therefore dropped: in a real archive that is its title, its `## 📑 Index` heading, every TOC
    bullet the drain just regenerated, and the `---` separator — and a fragment marker, if one sits
    there, which is how a roll-over can turn an observed stage into a missing one.

    MEASURED against the pre-fix script with this fixture (8 monolith entries, 5 of them
    archived): 10 lines reached no segment -- the archive's title, its `## 📑 Index` heading, all
    five TOC bullets, the `---` separator, and the two blank lines between them.

    The control is the other branch of the same function: an archive whose headings are undated
    goes through `split -l`, which moves every byte. Two branches of one verbatim-move contract
    disagreeing is what makes this a defect rather than a layout choice — so the comparison is
    asserted in S19 rather than left as an argument.
    """
    (tmp_path / "control").mkdir()
    (tmp_path / "rolled").mkdir()
    control = _rollover_repo(tmp_path / "control")
    rolled = _rollover_repo(tmp_path / "rolled")

    # Same fixture, same eviction, roll-over threshold out of reach: this is what the archive
    # holds at the moment the split would run.
    assert _run(control, "drain", MONOLITH, "100000").returncode == 0
    archive = control / ARCHIVE
    assert archive.is_file(), "the control never produced an archive; the fixture is vacuous"
    assert not (control / "docs/archive/CHANGELOG").exists(), (
        "the control rolled over after all, so it is not a picture of the pre-split archive"
    )
    before = archive.read_text(encoding="utf-8").splitlines()

    assert _run(rolled, "drain", MONOLITH, "1").returncode == 0
    segdir = rolled / "docs/archive/CHANGELOG"
    assert segdir.is_dir() and _entry_counts(segdir), "roll-over never fired; this is vacuous"

    after = Counter(_rolled(segdir))
    missing = [ln for ln, k in (Counter(before) - after).items() for _ in range(k)]
    assert missing == [], (
        f"{len(missing)} line(s) of the archive reached no segment — the split dropped them:\n"
        + "\n".join(f"  {ln!r}" for ln in missing[:15])
    )
    # The multiset difference above is ONE-DIRECTIONAL, and a review named what that lets through:
    # a duplicated line can mask the loss of an identical one, and this fixture has 240 identical
    # padding lines. The totals close that gap for a first roll-over, where the segments are built
    # from this archive and nothing else. S20 is where a LATER roll-over's additions are bounded.
    assert sum(after.values()) == sum(Counter(before).values()), (
        f"the segment tree holds {sum(after.values())} lines against the archive's "
        f"{len(before)} — equal multiset differences can still hide a swap"
    )


def test_s19_the_chunk_split_already_moved_that_region_which_is_how_we_know(
    tmp_path: Path,
) -> None:
    """S18's control, and the reason it is a test: the two branches must not disagree.

    `check_rollover` splits by month when every entry heading carries a date and by line count
    when they do not. The line-count branch runs `split -l`, which cannot drop anything, so the
    same archive region survives there. Without this assertion S18 rests on reading the source;
    with it, the claim "a verbatim move loses nothing" is measured on the branch that already
    honours it.
    """
    (tmp_path / "undated").mkdir()
    body = "\n".join("padding line for the roll-over threshold" for _ in range(30))
    repo = make_fixture_repo(
        tmp_path / "undated",
        manifest={"retention": {"archive_dir": "docs/archive", "preimage_keep": KEEP_N}},
        files={MONOLITH: "# Changelog\n\n" + "".join(
            f"## [{i}.0.0] release {i}\n\n{body}\n\n" for i in range(1, 9)
        )},
    )
    assert _run(repo, "drain", MONOLITH, "1").returncode == 0
    segdir = repo / "docs/archive/CHANGELOG"
    assert segdir.is_dir(), "roll-over never fired; this control is vacuous"
    assert sorted(p.name for p in segdir.glob("part-*.md")), (
        "no `part-*.md` segment: this fixture took the month branch, not the line-count one"
    )
    joined = "\n".join(_rolled(segdir))
    assert "## 📑 Index" in joined, "the line-count branch dropped the archive's own index heading"
    assert "# CHANGELOG — archive" in joined, "the line-count branch dropped the archive's title"


def test_s20_a_later_rollover_adds_two_generated_lines_and_no_more(tmp_path: Path) -> None:
    """S18's cost, bounded — raised by an independent review, which is why it is a fixture.

    S18 makes the split move every line, and most of what it had been dropping is the archive's
    own GENERATED header. So the header now travels into a segment, and on every roll-over AFTER
    the first the previous run's stub TITLE travels too. The review's word for that was unbounded
    accumulation. It is bounded, at one copy per roll-over, and a number in a comment goes stale
    while a fixture does not.

    MEASURED across three roll-overs: 0 stub titles and 0 pointer lines in the segment tree after
    the first, 1 of each after the second, 2 of each after the third. They land in whichever
    segments hold the first dated heading and the last entry, which is why this counts over the
    whole tree rather than naming a file.

    ONE OF THE TWO SHAPES IS NOT THIS CHANGE'S DOING, and the mutant says so rather than the
    author: against a copy with the split reverted, the second roll-over gives 0 titles and ONE
    pointer. The pointer line sits after the last heading, so the old rule already carried it. The
    assertion still counts both, because what matters is the bound, not which rule produced it.

    The other half of the assertion is the one that would matter if it broke: a later roll-over
    appends into a stage seeded from the existing segments, and nothing archived by the first
    roll-over may be lost in that path.
    """
    (tmp_path / "later").mkdir()
    repo = _rollover_repo(tmp_path / "later")
    segdir = repo / "docs/archive/CHANGELOG"

    STUB_TITLE = "# CHANGELOG — archive, rolled over into segments"
    POINTER = "> Earlier entries archived verbatim"

    def generated() -> tuple[int, int]:
        lines = _rolled(segdir)
        return (
            sum(1 for ln in lines if ln == STUB_TITLE),
            sum(1 for ln in lines if ln.startswith(POINTER)),
        )

    assert _run(repo, "drain", MONOLITH, "1").returncode == 0
    assert _entry_counts(segdir), "roll-over never fired; this fixture is vacuous"
    first = Counter(_rolled(segdir))
    assert generated() == (0, 0), (
        f"the first roll-over already carried a stub into a segment: {generated()}"
    )

    _extend(repo, "2027-11", ("5.1.0", "5.2.0", "5.3.0", "5.4.0"))
    _extend(repo, "2026-03", tuple(f"6.{i}.0" for i in range(1, 9)))
    assert _run(repo, "drain", MONOLITH, "1").returncode == 0
    second = Counter(_rolled(segdir))
    assert generated() == (1, 1), f"the second roll-over added more than one of each: {generated()}"
    lost = [ln for ln, k in (first - second).items() for _ in range(k)]
    assert lost == [], (
        f"the second roll-over lost {len(lost)} line(s) the first one had archived:\n"
        + "\n".join(f"  {ln!r}" for ln in lost[:15])
    )

    _extend(repo, "2027-12", ("7.1.0", "7.2.0", "7.3.0", "7.4.0"))
    _extend(repo, "2026-04", tuple(f"8.{i}.0" for i in range(1, 9)))
    assert _run(repo, "drain", MONOLITH, "1").returncode == 0
    assert generated() == (2, 2), (
        f"growth is not one copy of each per roll-over: {generated()} after the third"
    )
    third = Counter(_rolled(segdir))
    lost = [ln for ln, k in (second - third).items() for _ in range(k)]
    assert lost == [], f"the third roll-over lost {len(lost)} line(s): {lost[:15]}"


# ── Last-copy refusal ─────────────────────────────────────────────────────

LAST_COPY_FRAGMENT = "docs/qa-log.d/2026-01-01-phase-zzlast.md"
LAST_COPY_BODY = (
    "## 2026-01-01 · zzlast\n\nthe only sentence that exists nowhere else in this fixture\n"
)
QA_MONOLITH = "docs/brainstorming-qa-log.md"


def _ring_holding_a_last_copy(tmp_path: Path) -> Path:
    """A repo whose oldest slot holds the only copy of a fragment, built the way it happened.

    No slot is hand-assembled: the first drain compiles the fragment into the hot monolith and
    deletes it, so the slot legitimately holds its bytes. The monolith is then REPLACED, which is
    what a later roll-over plus an eviction amount to, and at that point the ring is the only
    holder. `preimage_keep` is 1 so the second drain's capture makes the oldest slot a candidate.
    """
    repo = make_fixture_repo(
        tmp_path,
        manifest={"retention": {"archive_dir": "docs/archive", "preimage_keep": 1}},
        files={LAST_COPY_FRAGMENT: LAST_COPY_BODY},
    )
    assert _run(repo, "drain", "qa-log").returncode == 0
    assert _slots(repo) == ["0001"], _slots(repo)
    assert LAST_COPY_BODY.splitlines()[2] in (repo / QA_MONOLITH).read_text(encoding="utf-8")

    # The monolith loses the block. Now the ring is the only holder of those bytes.
    (repo / QA_MONOLITH).write_text(
        "# Brainstorming QA log\n\n## 📑 Index\n\n---\n\n## 2026-02-01 · unrelated\n\nother\n",
        encoding="utf-8",
    )
    (repo / "docs/qa-log.d/2026-03-01-phase-zznext.md").write_text(
        "## 2026-03-01 · zznext\n\nsomething new to drain\n", encoding="utf-8"
    )
    return repo


def test_f27_a_prune_refuses_to_evict_the_last_copy_and_the_drain_exits_non_zero(
    tmp_path: Path,
) -> None:
    """AC7 — the refusal, its exit code, and the path it names.

    RED against the earlier script (measured through `PLC_DRAIN_IMPL`): the drain exits 0 and slot
    0001 is gone, taking the only copy of that fragment with it. The ring is an undo buffer, and an
    undo buffer that holds a last copy is unacknowledged primary storage with a delete queue.

    The exit code is asserted, not the message alone: the eviction loop used to run inside a
    `printf | while` subshell, where a refusal cannot reach the caller, and `preimage_prune` ended
    `return 0` whatever happened inside it.
    """
    repo = _ring_holding_a_last_copy(tmp_path)
    before = _slots(repo)

    result = _run(repo, "drain", "qa-log")

    assert result.returncode != 0, (
        f"the drain exited 0 while evicting a last copy:\n{result.stdout}{result.stderr}"
    )
    out = result.stdout + result.stderr
    assert LAST_COPY_FRAGMENT in out, f"the refusal does not name the path that stopped it:\n{out}"
    assert "0001" in _slots(repo), (
        f"the refused slot was evicted anyway: {before} -> {_slots(repo)}"
    )
    # The fragment's bytes still exist somewhere, which is the whole point of refusing.
    held = repo / PREIMAGE_DIR / "0001/files" / LAST_COPY_FRAGMENT
    assert held.is_file() and held.read_text(encoding="utf-8") == LAST_COPY_BODY

    # And the refusal is REPEATABLE without changing what it protects: the capture belonging to
    # the drain that did not happen is rolled back, so the ring does not grow by one per attempt.
    again = _run(repo, "drain", "qa-log")
    assert again.returncode != 0, again.stdout + again.stderr
    assert _slots(repo) == before, (
        f"a refused attempt changed the store: {before} -> {_slots(repo)}"
    )
    statuses = [ln.split("\t")[3] for ln in _index(repo) if ln.count("\t") >= 4]
    assert "REFUSED" in statuses, f"the receipt does not record the refusal: {_index(repo)}"


def test_f28_a_snapshot_of_a_still_live_fragment_never_blocks(tmp_path: Path) -> None:
    """AC7's negative control — the refusal must not fire on the ordinary case.

    Without this, the refusal test passes just as well against a prune that refuses EVERYTHING, which would
    stop every drain on this repo the moment the ring filled. Here the fragment is still sitting in
    `docs/qa-log.d/`, so the slot's copy is a snapshot and not a last copy, and the eviction runs.
    """
    repo = make_fixture_repo(
        tmp_path,
        manifest={"retention": {"archive_dir": "docs/archive", "preimage_keep": 1}},
        files={
            "docs/qa-log.d/2026-01-01-phase-zzalive.md": "## 2026-01-01 · zzalive\n\nstill here\n",
        },
    )
    # A restore-free way to get a slot whose files still exist: capture, then put the fragment back.
    assert _run(repo, "drain", "qa-log").returncode == 0
    assert _slots(repo) == ["0001"], _slots(repo)
    (repo / "docs/qa-log.d/2026-01-01-phase-zzalive.md").write_text(
        "## 2026-01-01 · zzalive\n\nstill here\n", encoding="utf-8"
    )

    result = _run(repo, "drain", "qa-log")
    assert result.returncode == 0, (
        f"the prune refused a snapshot of a document that is still live:\n"
        f"{result.stdout}{result.stderr}"
    )
    assert "0001" not in _slots(repo), (
        f"the oldest slot was not evicted, so this control proves nothing: {_slots(repo)}"
    )


def test_f29_mutant_a_durable_set_that_includes_the_ring_never_refuses(tmp_path: Path) -> None:
    """AC7's second negative control, and it is a different thing from the first.

    The check's durable set excludes `$PID`, which lives INSIDE `$AD`. A set built recursively over
    `$AD` finds every fragment in some older slot, so nothing is ever a last copy: the check passes
    vacuously while looking exactly like a check that works. That is the fails-open mutant, and it
    must be killed by the refusal test's fixture rather than argued about.

    The seam is `PLC_DRAIN_IMPL`, the same selector the invariant script already uses.

    RE-AIMED, not relaxed. The exclusion used to be a `-path "$PID" -prune` inside one `find`; it is
    now the `case` that skips the ring's directories while `durable_streams` walks `$AD` looking for
    segment series. The needle moved because the code moved -- the same thing this phase had to do
    more than once -- and the mutant still describes the one shape that matters: a durable set that
    contains the ring.
    """
    impl = Path(os.environ.get("PLC_DRAIN_IMPL", DRAIN))
    text = impl.read_text(encoding="utf-8")
    pruned = '''    case "$d" in "$PID"|"$PID"/*) continue ;; esac'''
    assert text.count(pruned) == 1, "the durable set's exclusion is not where this mutant expects"
    mutant = tmp_path / "drain-fails-open.sh"
    mutant.write_text(
        text.replace(pruned, '''    case "$d" in "$PID"|"$PID"/*) : ;; esac'''),
        encoding="utf-8",
    )

    (tmp_path / "ring").mkdir()
    repo = _ring_holding_a_last_copy(tmp_path / "ring")
    result = subprocess.run(
        ["bash", str(mutant), "drain", "qa-log"], cwd=repo, capture_output=True, text=True,
        check=False,
    )
    assert result.returncode == 0 and "0001" not in _slots(repo), (
        "the recursive-over-$AD mutant did NOT fail open, so the refusal test's green says less than it looks "
        f"like it does:\nrc={result.returncode}\n{result.stdout}{result.stderr}"
    )


TWO_ENTRY_FRAGMENT = "docs/qa-log.d/2026-01-01-phase-zzsplit.md"
ENTRY_A = "## 2026-01-01 · zzsplit A\n\nthe first of two sentences that exist only in this phase\n"
ENTRY_B = "## 2026-01-02 · zzsplit B\n\nthe second of two sentences that exist only in this phase\n"
OTHER_ENTRY = "## 2026-06-01 · unrelated\n\nsome other phase wrote this\n"


def test_f31_an_archived_fragment_whose_entries_were_REORDERED_is_not_a_last_copy(
    tmp_path: Path,
) -> None:
    """AC7 — the ordinary case the first version of this check called a last copy.

    RED against the shipped script (measured through `PLC_DRAIN_IMPL`): it refuses, the drain exits
    non-zero and moves nothing, because it asked whether the fragment's WHOLE line sequence appears
    contiguously in one file. `drain_monolith` slices entry-by-entry and reassembles NEWEST-FIRST,
    so a multi-entry fragment comes back with other phases' entries between its own. Every byte is
    durable; the fragment-shaped run is not.

    This is why this fixture exists: whole-file
    contiguity scored ring fragments as last copies while they were in the archive, and the
    next drain and every `restore` would have been refused.

    The monolith is REWRITTEN to model the reassembly, the way the refusal test rewrites it to model an
    eviction. What it must model is only this: both entries present, not adjacent.
    """
    repo = make_fixture_repo(
        tmp_path,
        manifest={"retention": {"archive_dir": "docs/archive", "preimage_keep": 1}},
        files={TWO_ENTRY_FRAGMENT: ENTRY_A + "\n" + ENTRY_B},
    )
    assert _run(repo, "drain", "qa-log").returncode == 0
    assert _slots(repo) == ["0001"], _slots(repo)

    (repo / QA_MONOLITH).write_text(
        "# Brainstorming QA log\n\n## 📑 Index\n\n---\n\n"
        + ENTRY_A + "\n" + OTHER_ENTRY + "\n" + ENTRY_B,
        encoding="utf-8",
    )
    mono = (repo / QA_MONOLITH).read_text(encoding="utf-8")
    assert ENTRY_A in mono and ENTRY_B in mono, "the fixture must keep both entries durable"
    assert ENTRY_A + "\n" + ENTRY_B not in mono, (
        "the two entries are still adjacent, so this fixture would pass under whole-file "
        "contiguity and prove nothing"
    )
    (repo / "docs/qa-log.d/2026-03-01-phase-zznext.md").write_text(
        "## 2026-03-01 · zznext\n\nsomething new to drain\n", encoding="utf-8"
    )

    result = _run(repo, "drain", "qa-log")

    assert result.returncode == 0, (
        "the prune refused a slot whose every entry is durable -- only their ORDER changed:\n"
        f"{result.stdout}{result.stderr}"
    )
    assert "0001" not in _slots(repo), (
        f"the oldest slot was not evicted, so this test proves nothing: {_slots(repo)}"
    )


def test_f32_an_entry_split_across_two_segments_is_not_a_last_copy(tmp_path: Path) -> None:
    """AC7 — the second half of the same defect, and a different mechanism.

    RED against the shipped script: `check_rollover` segments an archive with `split -l`, which
    cuts at a LINE COUNT and therefore cuts THROUGH an entry: one segment can end mid-entry
    and the next carry the
    rest. No single file holds that entry contiguously, so a per-file test refuses even for a
    fragment with ONE entry -- per-entry splitting alone does not fix it, which is why this
    fixture is separate from the per-entry one above.

    The segments are cut by the real `split -l`, not written by hand, and the fixture asserts both
    halves of the property it depends on: the concatenation is byte-identical to the source, and
    neither file alone holds the entry.
    """
    long_entry = "## 2026-01-01 · zzstraddle\n\n" + "".join(
        f"line {i} of an entry long enough to be cut in half by a line-count split\n"
        for i in range(1, 41)
    )
    repo = make_fixture_repo(
        tmp_path,
        manifest={
            "retention": {
                "archive_dir": "docs/archive",
                "preimage_keep": 1,
                # Declared because this fixture creates a SEGMENTED archive, and the drain exits 3
                # rather than guess a segment order -- the refusal this repo would rather have than
                # a guessed reassembly. Measured here: without it the second drain exits 3 and the
                # test would have been reporting that refusal as the last-copy refusal.
                "order": {"brainstorming-qa-log.md": "newest-first"},
            }
        },
        files={"docs/qa-log.d/2026-01-01-phase-zzstraddle.md": long_entry},
    )
    assert _run(repo, "drain", "qa-log").returncode == 0
    assert _slots(repo) == ["0001"], _slots(repo)

    # The durable copy moves OUT of the monolith and into a real `split -l` series.
    source = tmp_path / "pre-split.md"
    source.write_text(
        "# Brainstorming QA log archive\n\n" + OTHER_ENTRY + "\n" + long_entry,
        encoding="utf-8",
    )
    segdir = repo / "docs/archive/brainstorming-qa-log"
    segdir.mkdir(parents=True, exist_ok=True)
    assert subprocess.run(
        ["split", "-l", "20", str(source), "part-"], cwd=segdir, check=False
    ).returncode == 0
    pieces = sorted(segdir.glob("part-*"))
    assert len(pieces) >= 2, f"the split produced {len(pieces)} piece(s), so nothing straddles"
    for piece in pieces:
        piece.rename(piece.with_suffix(".md"))
    pieces = sorted(segdir.glob("part-??.md"))
    rejoined = "".join(piece.read_text(encoding="utf-8") for piece in pieces)
    assert rejoined == source.read_text(encoding="utf-8"), (
        "the concatenation is not the source, so these segments are not what `split -l` cut"
    )
    assert not any(long_entry in piece.read_text(encoding="utf-8") for piece in pieces), (
        "one segment holds the whole entry, so this fixture would pass under per-file contiguity "
        "and prove nothing about the series"
    )

    (repo / QA_MONOLITH).write_text(
        "# Brainstorming QA log\n\n## 📑 Index\n\n---\n\n" + OTHER_ENTRY, encoding="utf-8"
    )
    (repo / "docs/qa-log.d/2026-03-01-phase-zznext.md").write_text(
        "## 2026-03-01 · zznext\n\nsomething new to drain\n", encoding="utf-8"
    )

    result = _run(repo, "drain", "qa-log")

    assert result.returncode == 0, (
        "the prune refused a slot whose entry is durable in a segment SERIES -- the only reason no "
        f"single file holds it is the line-count split:\n{result.stdout}{result.stderr}"
    )
    assert "0001" not in _slots(repo), (
        f"the oldest slot was not evicted, so this test proves nothing: {_slots(repo)}"
    )


def _receipt_rows(repo: Path) -> list[list[str]]:
    """The receipt parsed with ONE reader, so a new status word cannot get a reader of its own."""
    rows = []
    for line in _index(repo):
        if not line:
            continue
        parts = line.split("\t")
        assert len(parts) == 5, f"receipt line is not five columns: {line!r}"
        rows.append(parts)
    return rows


def test_f30_each_evicted_slot_gets_one_receipt_line_under_its_own_status(
    tmp_path: Path,
) -> None:
    """AC8 — an eviction is recorded, once per slot, and not as a capture.

    RED against the earlier script: the prune deletes slots silently, so the receipt shows four
    captures and no evictions, and the only trace of three destroyed generations is that their
    directories are not there any more.

    The status word matters as much as the line. `OK` means a capture happened, and reusing it for
    an eviction makes every reader that counts captures wrong -- this store has already produced
    the shape of an OK-line count that no longer matches the slots on disk.

    The fixture evicts THREE slots in one prune, because "one line per evicted slot" and "a line
    when a prune runs" are different claims and a single-eviction fixture cannot tell them apart.
    """
    repo = make_monolith_repo(
        tmp_path,
        tuple(f"[1.{i}.0] — 2026-0{i}-01" for i in range(1, 9)),
        retention={"preimage_keep": 5},
    )
    for r in range(3):
        for i in range(4):
            _grow(repo, f"{r}.{i}.0")
        assert _run(repo, "drain", MONOLITH).returncode == 0
    assert len(_slots(repo)) == 3, f"the fixture needs three slots before the prune: {_slots(repo)}"
    doomed = _slots(repo)
    before = len(_receipt_rows(repo))

    # The ring narrows under them: nothing else about the drain changes.
    manifest = repo / ".claude/close-gate.json"
    manifest.write_text(
        json.dumps({"retention": {"archive_dir": "docs/archive", "preimage_keep": 1}}),
        encoding="utf-8",
    )
    for i in range(4):
        _grow(repo, f"final.{i}.0")
    assert _run(repo, "drain", MONOLITH).returncode == 0

    rows = _receipt_rows(repo)
    added = rows[before:]
    evicted = [r for r in added if r[3] == "EVICTED"]
    captures = [r for r in added if r[3] == "OK"]

    assert len(captures) == 1, f"expected one capture line for this drain: {added}"
    assert sorted(r[0] for r in evicted) == sorted(doomed), (
        f"the evicted keys in the receipt do not match the slots that disappeared: "
        f"{[r[0] for r in evicted]} vs {doomed}"
    )
    assert _slots(repo) == sorted(_slots(repo))[-1:], (
        f"the prune did not actually evict three slots: {_slots(repo)}"
    )
    for r in evicted:
        assert r[2] == "prune", f"the mode column does not say where the line came from: {r}"
        assert re.fullmatch(r"\d+ paths, \d+ bytes destroyed", r[4]), (
            f"the detail does not name the paths and bytes: {r}"
        )
        assert int(r[4].split()[0]) > 0 and int(r[4].split()[2]) > 0, (
            f"an eviction reported as destroying nothing: {r}"
        )

    # The counting reader: capture and eviction are separable, which is the point of the status.
    statuses = [r[3] for r in rows]
    assert statuses.count("OK") == 4, f"capture count is wrong: {statuses}"
    assert statuses.count("EVICTED") == 3, f"eviction count is wrong: {statuses}"
