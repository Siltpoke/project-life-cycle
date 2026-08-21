"""Tests for scripts/backlog-toc.sh — the backlog index generator.

The generator exists because backlog ids collide in practice: an entry filed under an id that
was already taken is caught, if at all, only by a hand-run check afterwards.
So the property that matters most here is **next-free-id is correct**, and it is tested against
a gap-containing, out-of-order fixture rather than a tidy one.

The other load-bearing property is a *negative* one: the index must contain **no line numbers**.
A generated line index is correct for exactly one edit.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "backlog-toc.sh"

FIXTURE = """# Backlog

Deferred decisions, each with explicit Trigger + Exit criteria per the skill's backlog discipline.

## B1 — first thing — ✅ DONE 2026-01-01

Body of B1.

## B7 — a gap above me, on purpose — 🟡 MEDIUM

Body of B7. Mentions a line like `foo.sh:123` which must NOT make the index emit line numbers.

## B3 — out of numeric order in the file — 🟠 HIGH

Body of B3.

## B12 — the highest id — 🟢 LOW

Body of B12.
"""


def _run(tmp_path: Path, body: str) -> str:
    """Run the generator against a throwaway repo and return the rewritten BACKLOG."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "BACKLOG.md").write_text(body, encoding="utf-8")
    res = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"generator failed: {res.stderr}"
    return (docs / "BACKLOG.md").read_text(encoding="utf-8")


def test_next_free_id_is_max_plus_one_not_count_plus_one(tmp_path: Path) -> None:
    """The fixture has 4 entries with a gap and out-of-order ids; max is B12, so next is B13.

    A count-based implementation would say B5 here — that is the bug this asserts against.
    """
    out = _run(tmp_path, FIXTURE)
    assert "Next free id: B13." in out
    assert "Next free id: B5." not in out


def _index_of(out: str) -> str:
    """The index block, split on a prefix rather than the whole header row.

    The columns are a derived `state` plus a hand-written
    `priority`, and the header can carry provenance labels from a local vocabulary file.
    Splitting on `| id |` keeps the
    tests shape-agnostic: a further column change does not break them, and they
    still fail loudly if the index disappears.
    """
    head, sep, rest = out.partition("| id |")
    assert sep, "index table header not found in the generated backlog"
    return rest.split("\n---\n")[0]


def test_entry_count_is_reported(tmp_path: Path) -> None:
    """The header reports headings AND how many are indexed.

    The two numbers stopped being the same the moment an exemption table existed, and a single
    "N entries" line would quietly claim the index covers every heading when it does not. This
    fixture exempts nothing, so the two agree here — both are asserted anyway, because a
    generator that printed the heading count into the indexed slot would otherwise pass on
    exactly the corpus where the distinction cannot show.
    """
    out = _run(tmp_path, FIXTURE)
    assert "4 headings" in out
    assert "**4 indexed**" in out


def test_every_id_appears_in_the_index_table(tmp_path: Path) -> None:
    out = _run(tmp_path, FIXTURE)
    index = _index_of(out)
    for bid in ("B1", "B7", "B3", "B12"):
        assert f"**{bid}**" in index, f"{bid} missing from the index table"


def test_index_carries_no_line_numbers(tmp_path: Path) -> None:
    """The deliberate negative property. A `foo.sh:123` in an entry body must not leak in."""
    out = _run(tmp_path, FIXTURE)
    index = _index_of(out)
    assert ":123" not in index
    assert "foo.sh:" not in index


def test_bodies_survive_verbatim(tmp_path: Path) -> None:
    """The generator rewrites only the header; every entry body must come through untouched."""
    out = _run(tmp_path, FIXTURE)
    for marker in ("Body of B1.", "Body of B7.", "Body of B3.", "Body of B12."):
        assert marker in out


def test_regenerating_twice_is_idempotent(tmp_path: Path) -> None:
    """Running it again must not stack a second index on top of the first."""
    first = _run(tmp_path, FIXTURE)
    docs = tmp_path / "docs"
    subprocess.run(["bash", str(SCRIPT)], cwd=tmp_path, capture_output=True, check=True)
    second = (docs / "BACKLOG.md").read_text(encoding="utf-8")
    assert first == second
    assert second.count("## Index") == 1


def test_status_glyphs_are_carried_into_the_index(tmp_path: Path) -> None:
    """The old `status` column is split in two, and the halves have different provenances.

    The priority glyph is still read from the heading, so it must still arrive. `✅ done` must
    NOT: state is now derived from the closure log, and this fixture ships no log, so every id
    has to read `open` no matter what its heading says. Asserting the absence is the half that
    matters — without it this test passes on a generator that quietly kept guessing from titles.
    """
    out = _run(tmp_path, FIXTURE)
    index = _index_of(out)
    assert "🟠 high" in index, "the hand-written priority glyph was dropped"
    assert "✅ done" not in index, "the retired title-guessing vocabulary is still being emitted"
    assert "open" in index, "no state was rendered at all"


def test_envelope_stays_bash_only(tmp_path: Path) -> None:
    """Gate-adjacent scripts stay jq/bash-only — no python3 dependency."""
    src = SCRIPT.read_text(encoding="utf-8")
    assert "python3" not in src
    assert "python " not in src


@pytest.mark.parametrize("missing", ["docs/BACKLOG.md"])
def test_absent_backlog_does_not_crash(tmp_path: Path, missing: str) -> None:
    """No backlog is 'nothing to do', not an error — same posture as retention-drain.sh."""
    (tmp_path / "docs").mkdir()
    res = subprocess.run(
        ["bash", str(SCRIPT)], cwd=tmp_path, capture_output=True, text=True, check=False
    )
    assert res.returncode != 0 or "0 entries" in res.stdout


# --- the provenance labels of a tracked file are that file's own property ------------------
#
# The defect these pin: the vocabulary file the generator reads its labels
# from is gitignored, so a git WORKTREE never receives it and the generator silently fell back
# to English -- rewriting the header of a tracked file differently depending on which checkout
# it ran in, exit 0, with nothing on stderr but the usual success line.
#
# Labels here are deliberately ASCII sentinels, not real vocabulary.
# The property
# under test is "whatever is in the file survives", which no specific alphabet is load-bearing
# for -- and using sentinels means a test cannot accidentally pass by matching a real default.

SEEDED = FIXTURE.replace(
    "# Backlog\n",
    "| id | state (SEEDED-D) | priority (SEEDED-H) | what |\n\n# Backlog\n",
)


def _run_raw(
    tmp_path: Path, body: str, *args: str, markers: str | None = None
) -> subprocess.CompletedProcess[str]:
    """Run the generator without asserting success, so exit codes are testable."""
    docs = tmp_path / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "BACKLOG.md").write_text(body, encoding="utf-8")
    env = None
    if markers is not None:
        mfile = tmp_path / "vocab.txt"
        mfile.write_text(markers, encoding="utf-8")
        import os

        env = {**os.environ, "PLC_ROADMAP_MARKERS": str(mfile)}
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_absent_vocabulary_preserves_the_labels_already_in_the_file(tmp_path: Path) -> None:
    """The worktree case, one-to-one. No vocabulary reachable, header already labelled.

    This is the ONE that reproduces the shipped defect. Before the fix the same inputs produced
    `state (derived) | priority (hand-written)` and exit 0. The assertion is two-sided on
    purpose: keeping the seeded labels is not enough if the English defaults also appear
    somewhere in the header, which a partial fix (one column, not both) would produce.
    """
    res = _run_raw(tmp_path, SEEDED)
    assert res.returncode == 0, f"a missing vocabulary must not be fatal: {res.stderr}"
    header = _index_of((tmp_path / "docs" / "BACKLOG.md").read_text(encoding="utf-8")).split("\n")[0]
    assert "SEEDED-D" in header and "SEEDED-H" in header, f"labels were not preserved: {header!r}"
    assert "(derived)" not in header and "(hand-written)" not in header, (
        f"the English fallback overwrote a label that was already in the file: {header!r}"
    )
    assert "keeping the header labels" in res.stderr, (
        "preserving must be narrated -- a silent no-op is indistinguishable from a silent "
        f"rewrite to a reader, which is the whole defect. stderr was: {res.stderr!r}"
    )


def test_a_present_vocabulary_that_disagrees_refuses_and_writes_nothing(
    tmp_path: Path,
) -> None:
    """Two live sources in conflict is a different situation from one source missing.

    Asserts the FILE, not just the exit code: a guard that reports and writes anyway is the
    failure shape a guard must not have.
    """
    res = _run_raw(
        tmp_path,
        SEEDED,
        markers="[provenance]\nderived\tOTHER-D\nhand-written\tOTHER-H\n",
    )
    assert res.returncode == 3, f"expected a refusal, got {res.returncode}: {res.stderr}"
    assert (tmp_path / "docs" / "BACKLOG.md").read_text(encoding="utf-8") == SEEDED, (
        "the refusal did not leave the file untouched"
    )
    # All FOUR labels, not one per source. The first version of this assertion checked only the
    # `-D` side of each while its own message said "both labels" -- a message wider than the
    # mechanism under it.
    for label in ("SEEDED-D", "SEEDED-H", "OTHER-D", "OTHER-H"):
        assert label in res.stderr, (
            f"the refusal must name every label on both sides; {label!r} is missing "
            f"from: {res.stderr!r}"
        )


def test_relabel_is_the_only_way_past_the_refusal(tmp_path: Path) -> None:
    """Positive control for the escape hatch: without it the previous test's setup fails.

    Without this the refusal could be a blanket refusal and both tests would still pass.
    """
    res = _run_raw(
        tmp_path,
        SEEDED,
        "--relabel",
        markers="[provenance]\nderived\tOTHER-D\nhand-written\tOTHER-H\n",
    )
    assert res.returncode == 0, f"--relabel must be honoured: {res.stderr}"
    header = _index_of((tmp_path / "docs" / "BACKLOG.md").read_text(encoding="utf-8")).split("\n")[0]
    # PER CELL, not containment. The first version asserted both labels appeared somewhere in the
    # header, which passes a header with the two columns SWAPPED -- precisely the lie
    # test_ac4_header_names_which_column_comes_from_where... was rewritten to stop.
    cells = [c.strip() for c in header.strip().strip("|").split("|")]
    state_cell = next((c for c in cells if c.startswith("state")), "")
    prio_cell = next((c for c in cells if c.startswith("priority")), "")
    assert "OTHER-D" in state_cell and "OTHER-H" not in state_cell, (
        f"the derived label is not on the state column: {state_cell!r}"
    )
    assert "OTHER-H" in prio_cell and "OTHER-D" not in prio_cell, (
        f"the hand-written label is not on the priority column: {prio_cell!r}"
    )


def test_a_file_with_no_header_yet_still_gets_the_fallback_labels(tmp_path: Path) -> None:
    """Every adopter's first run: no vocabulary, and no prior header to preserve.

    Preserving must not become "refuse to ever write a label". The fallback still applies when
    there is nothing to preserve, which is what keeps this usable outside this repository.
    """
    res = _run_raw(tmp_path, FIXTURE)
    assert res.returncode == 0, f"an adopter's first run must succeed: {res.stderr}"
    header = _index_of((tmp_path / "docs" / "BACKLOG.md").read_text(encoding="utf-8")).split("\n")[0]
    assert "(derived)" in header and "(hand-written)" in header, (
        f"the fallback did not apply to a fresh header: {header!r}"
    )


def test_an_unknown_argument_is_not_swallowed(tmp_path: Path) -> None:
    """A typo'd flag must not read as "no flags given" -- that would silently arm the guard."""
    res = _run_raw(tmp_path, SEEDED, "--relable")
    assert res.returncode == 2, f"expected an argument error, got {res.returncode}"
    assert (tmp_path / "docs" / "BACKLOG.md").read_text(encoding="utf-8") == SEEDED


# --- header-extraction back doors ------------------------------------------------------------
#
# Every row below is the SAME back door: make the header extraction
# return empty, and the guard reads that as "no prior header yet" and OVERWRITES -- reaching the
# exact defect the guard exists to close, through the guard. They are separate tests because they
# are separate ways in, and a single fixture would let one fix look like four.


def _header_of(tmp_path: Path) -> str:
    return _index_of((tmp_path / "docs" / "BACKLOG.md").read_text(encoding="utf-8")).split("\n")[0]


def test_an_indented_header_is_still_found(tmp_path: Path) -> None:
    """A markdown table may be indented up to three spaces; `^\\|` matched none of them.

    Before the fix this fell through to "no prior header" and the absent-vocabulary path rewrote
    the labels to the English defaults with exit 0 -- the shipped defect, reached through the
    guard meant to prevent it.
    """
    res = _run_raw(tmp_path, SEEDED.replace("| id | state (SEEDED-D)", "  | id | state (SEEDED-D)"))
    assert res.returncode == 0, f"an indented header must not be fatal: {res.stderr}"
    header = _header_of(tmp_path)
    assert "SEEDED-D" in header and "(derived)" not in header, (
        f"an indented header was treated as absent and overwritten: {header!r}"
    )


def test_a_half_readable_header_refuses_instead_of_writing_an_empty_label(
    tmp_path: Path,
) -> None:
    """One label parses, the other does not -- the old test was `-n "$FILE_D$FILE_H"`, true here.

    The preserve branch then assigned the empty one straight through and wrote `priority ()` into
    the tracked file, exit 0. **Corrupting the artifact is worse than a wrong label**, and one
    missing bracket in the header reached it.
    """
    res = _run_raw(tmp_path, SEEDED.replace("state (SEEDED-D)", "state SEEDED-D").replace("priority (SEEDED-H)", "priority SEEDED-H"))
    assert res.returncode == 7, f"expected the malformed-header refusal, got {res.returncode}"
    body = (tmp_path / "docs" / "BACKLOG.md").read_text(encoding="utf-8")
    assert "priority ()" not in body, "an empty label was written into the tracked file"
    assert "priority SEEDED-H" in body, "the file was modified despite the refusal"


def test_relabel_overrides_the_malformed_header_refusal(tmp_path: Path) -> None:
    """Positive control for the row above: without it, a malformed header is unrecoverable.

    A refusal with no way out turns one bad bracket into a file only a hand-edit can fix.
    """
    res = _run_raw(
        tmp_path,
        SEEDED.replace("state (SEEDED-D)", "state SEEDED-D").replace("priority (SEEDED-H)", "priority SEEDED-H"),
        "--relabel",
    )
    assert res.returncode == 0, f"--relabel must recover a malformed header: {res.stderr}"
    header = _header_of(tmp_path)
    assert "(derived)" in header and "(hand-written)" in header, (
        f"a fresh header was not written: {header!r}"
    )


def test_a_label_containing_parentheses_is_not_truncated(tmp_path: Path) -> None:
    """`.*(\\(.*\\)).*` is greedy at both ends, so `state (source (derived))` captured `derived`.

    Preserving then rewrote the header as `state (derived))` -- a silent corruption of a label the
    run was supposed to be leaving alone. Bounded to `[^()]*`, which makes a nested label
    unreadable rather than misread, and unreadable is handled by the refusal above.
    """
    res = _run_raw(tmp_path, SEEDED.replace("state (SEEDED-D)", "state (source (SEEDED-D))"))
    body = (tmp_path / "docs" / "BACKLOG.md").read_text(encoding="utf-8")
    assert "(SEEDED-D))" not in body or res.returncode != 0, (
        "a nested label was silently rewritten into a corrupted one"
    )
    assert res.returncode in (0, 7), f"unexpected exit {res.returncode}: {res.stderr}"
    if res.returncode == 0:
        assert "state (source (SEEDED-D))" in body, "the nested label was not preserved verbatim"


def test_a_label_containing_a_pipe_does_not_reach_the_write_path(tmp_path: Path) -> None:
    """`awk -F'|'` splits such a cell in half, so the capture finds no closing paren.

    Refusing is correct: the header is not parseable by the tool that has to rewrite it, and
    guessing at it is how the original defect happened.
    """
    res = _run_raw(tmp_path, SEEDED.replace("state (SEEDED-D)", "state (SEEDED|D)"))
    assert res.returncode == 7, f"expected the malformed-header refusal, got {res.returncode}"
    assert "state (SEEDED|D)" in (tmp_path / "docs" / "BACKLOG.md").read_text(encoding="utf-8")


def test_a_bad_argument_leaves_no_temp_files_and_is_reported_first(tmp_path: Path) -> None:
    """Argument parsing moved ahead of every temp file and every other check.

    Late parsing leaked three temp files on the exit-2 path, and any earlier failure reported
    itself instead of the real problem, which is the typo.
    """
    import os

    before = set(os.listdir("/tmp")) if os.path.isdir("/tmp") else set()
    res = _run_raw(tmp_path, SEEDED, "--relable")
    assert res.returncode == 2, f"expected an argument error, got {res.returncode}"
    assert "unknown argument" in res.stderr
    assert "is unchanged" in res.stderr, "the message must say nothing was written"
    if before:
        leaked = {f for f in set(os.listdir("/tmp")) - before if f.startswith("tmp")}
        assert not leaked, f"temp files leaked on the argument-error path: {leaked}"


# --- the source must be readable before anything is written over it -------------------------
#
# MEASURED on an earlier version:
# an unreadable `docs/BACKLOG.md` holding real entries was REPLACED by a zero-entry file, printing
# `TOC regenerated: 0 entries` and exiting 0. Data loss behind a success message. These rows exist
# because "nothing was read" and "there is nothing to read" produce identical output, and only the
# input can tell them apart.


def test_an_unreadable_backlog_is_not_replaced_by_an_empty_one(tmp_path: Path) -> None:
    """The destructive case. Asserts the BYTES survive, not merely that the exit code moved."""
    import os
    import stat

    docs = tmp_path / "docs"
    docs.mkdir()
    target = docs / "BACKLOG.md"
    target.write_text(FIXTURE, encoding="utf-8")
    before = target.read_bytes()
    os.chmod(target, 0)
    try:
        if os.access(target, os.R_OK):  # running as root: the premise does not hold
            pytest.skip("cannot make a file unreadable for this user")
        res = subprocess.run(
            ["bash", str(SCRIPT)], cwd=tmp_path, capture_output=True, text=True, check=False
        )
        assert res.returncode == 8, f"expected the unreadable-source refusal, got {res.returncode}"
        assert "cannot be read" in res.stderr
    finally:
        os.chmod(target, stat.S_IRUSR | stat.S_IWUSR)
    assert target.read_bytes() == before, "an unreadable backlog was overwritten"


def test_a_non_backlog_file_is_not_replaced_by_an_empty_backlog(tmp_path: Path) -> None:
    """The wrong-directory case, which the same guard covers and which nobody was looking for.

    A `docs/BACKLOG.md` that is readable but yields no `## B` entry is either not a backlog or was
    read only partially. Both mean: do not write. Before this, running the generator from a
    directory that merely happened to contain a `docs/` overwrote whatever was there.
    """
    docs = tmp_path / "docs"
    docs.mkdir()
    target = docs / "BACKLOG.md"
    target.write_text("# Some other file\n\nnot a backlog at all\n", encoding="utf-8")
    before = target.read_bytes()
    res = subprocess.run(
        ["bash", str(SCRIPT)], cwd=tmp_path, capture_output=True, text=True, check=False
    )
    assert res.returncode == 8, f"expected the unreadable-source refusal, got {res.returncode}"
    assert "wrong directory" in res.stderr, f"the message must name the likely cause: {res.stderr!r}"
    assert target.read_bytes() == before, "a non-backlog file was overwritten"


def test_a_genuinely_absent_backlog_is_still_created(tmp_path: Path) -> None:
    """POSITIVE CONTROL, and the reason the guard keys on bytes rather than on entry count.

    Without this row the guard above is satisfiable by a generator that refuses to bootstrap
    anything, which would break every adopter's very first run.
    """
    (tmp_path / "docs").mkdir()
    res = subprocess.run(
        ["bash", str(SCRIPT)], cwd=tmp_path, capture_output=True, text=True, check=False
    )
    assert res.returncode == 0, f"an absent backlog must still be created: {res.stderr}"
    assert (tmp_path / "docs" / "BACKLOG.md").exists()
    assert "0 entries" in res.stdout


def test_a_zero_byte_backlog_is_a_legal_empty_state(tmp_path: Path) -> None:
    """Second positive control: empty is not the same as unreadable, and only one of them blocks."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "BACKLOG.md").write_text("", encoding="utf-8")
    res = subprocess.run(
        ["bash", str(SCRIPT)], cwd=tmp_path, capture_output=True, text=True, check=False
    )
    assert res.returncode == 0, f"a zero-byte backlog is a legal empty state: {res.stderr}"


# --- the escape hatch must not lead back into the defect -----------------------------------
#
# `--relabel` once shipped with no condition on it, described as a deliberate boundary.
# MEASURED, the description was wrong: with no vocabulary reachable -- a worktree, which is where
# the original defect happened -- `--relabel` rewrote a labelled tracked header straight back to
# the English fallback, reached by a person following the
# documented way out of a refusal. These rows exist because "no guard on the escape hatch" and
# "the escape hatch IS the defect" read the same in a changelog and are not the same thing.


def test_relabel_without_a_vocabulary_refuses_instead_of_reopening_the_defect(
    tmp_path: Path,
) -> None:
    """The hole. Asserts the file, because the whole failure is that it gets written."""
    res = _run_raw(tmp_path, SEEDED, "--relabel")
    assert res.returncode == 9, f"expected the escape-hatch refusal, got {res.returncode}"
    header = _header_of(tmp_path)
    assert "SEEDED-D" in header and "(derived)" not in header, (
        f"--relabel rewrote the header to the fallback -- the silent-relabel defect: {header!r}"
    )
    # Asserted as a CHECKLIST, not a keyword. A single
    # `"escape hatch" in stderr` was a message test wearing a behaviour test's description: the
    # message could have read "escape hatch is broken" and passed. What an operator who arrived
    # here by following a printed instruction actually needs is four things, so four things are
    # asserted -- both label pairs so they can see the trade, and the way out.
    for needed, why in (
        ("SEEDED-D", "the labels already in the file"),
        ("derived", "the labels it would have written instead"),
        ("worktree", "the situation that puts them here"),
        ("PLC_ROADMAP_MARKERS", "the way forward"),
    ):
        assert needed in res.stderr, (
            f"the refusal must name {why} ({needed!r} missing): {res.stderr!r}"
        )


def test_relabel_with_a_vocabulary_is_still_honoured(tmp_path: Path) -> None:
    """POSITIVE CONTROL. Without this the guard above is satisfiable by disabling --relabel."""
    res = _run_raw(
        tmp_path,
        SEEDED,
        "--relabel",
        markers="[provenance]\nderived\tNEW-D\nhand-written\tNEW-H\n",
    )
    assert res.returncode == 0, f"--relabel must work where a vocabulary exists: {res.stderr}"
    header = _header_of(tmp_path)
    assert "NEW-D" in header and "NEW-H" in header, f"labels were not applied: {header!r}"


def test_relabel_still_recovers_an_unreadable_header_without_a_vocabulary(
    tmp_path: Path,
) -> None:
    """SECOND POSITIVE CONTROL, and the one that keeps the two refusals from deadlocking.

    A malformed header refuses with exit 7 and names `--relabel` as the way out. If the new exit-9
    guard also caught that case, the documented recovery would be unreachable and a single missing
    bracket would need a hand-edit. Nothing else in the suite would notice.
    """
    res = _run_raw(tmp_path, SEEDED.replace("state (SEEDED-D)", "state SEEDED-D").replace("priority (SEEDED-H)", "priority SEEDED-H"), "--relabel")
    assert res.returncode == 0, f"the recovery path must stay open: {res.stderr}"
    header = _header_of(tmp_path)
    # EXCLUSIVE, not merely present. Checking only that the fallback labels appear would pass a
    # header that kept the malformed cell and gained the new labels somewhere else -- presence is
    # not replacement, and the criterion is that the unreadable header was replaced.
    assert "(derived)" in header and "(hand-written)" in header, (
        f"a fresh header was not written: {header!r}"
    )
    assert "SEEDED-D" not in header and "SEEDED-H" not in header, (
        f"the malformed header survived alongside the new one: {header!r}"
    )


def test_a_vocabulary_that_resolves_nothing_is_treated_as_absent(tmp_path: Path) -> None:
    """Found by reviewing the CLAIMS, without running anything.

    The guard keyed on whether the vocabulary FILE EXISTS, while the comment above it promised
    `--relabel` is honoured when "a vocabulary IS present". What would have to be
    true for that promise to hold? The file must actually yield labels. Measured
    against a header already carrying SEEDED-D / SEEDED-H, every one of these rewrote it to the
    English fallback at exit 0 -- three of them the whole defect, the fourth half of it.

    PARTIAL is unresolved on purpose: relabelling one column from a vocabulary and the other from
    the fallback is the half-defect, and the format documents both keys.
    """
    for label, vocab in (
        ("empty file", ""),
        ("section header only", "[provenance]\n"),
        ("comments only", "[provenance]\n# nothing here\n"),
        ("derived only", "[provenance]\nderived\tONLY-D\n"),
        ("hand-written only", "[provenance]\nhand-written\tONLY-H\n"),
    ):
        d = tmp_path / label.replace(" ", "_")
        d.mkdir()
        res = _run_raw(d, SEEDED, "--relabel", markers=vocab)
        assert res.returncode == 9, f"{label}: expected the refusal, got {res.returncode}"
        header = _index_of((d / "docs" / "BACKLOG.md").read_text(encoding="utf-8")).split("\n")[0]
        assert "SEEDED-D" in header and "SEEDED-H" in header, (
            f"{label}: a vocabulary that resolves nothing overwrote the header: {header!r}"
        )


def test_a_fully_resolved_vocabulary_is_still_honoured(tmp_path: Path) -> None:
    """POSITIVE CONTROL for the row above: without it, the fix is satisfiable by refusing always."""
    res = _run_raw(
        tmp_path, SEEDED, "--relabel",
        markers="[provenance]\nderived\tOK-D\nhand-written\tOK-H\n",
    )
    assert res.returncode == 0, f"a complete vocabulary must be honoured: {res.stderr}"
    header = _header_of(tmp_path)
    assert "OK-D" in header and "OK-H" in header, f"labels were not applied: {header!r}"


def test_a_header_that_is_merely_unrecognised_is_not_treated_as_absent(tmp_path: Path) -> None:
    """Three ways to make the extractor miss a header that IS there.

    Missing it is not a harmless no-op: `HDR_PRESENT` stays 0, the guards read that as "there is
    nothing here", and the fallback is written straight over labels sitting in the file. All three
    exited 0 before the fix. The first is the sharpest, because it is the half-defect on the header
    side: one label parses, one does not, and `--relabel` discarded the good one.

    The tab and uppercase rows are about the MATCHER being narrower than markdown, while this tool
    only ever writes `| id |` at column zero — so the narrow form was quietly load-bearing for a
    decision it should never have influenced.
    """
    body = "\n\n# Backlog\n\n## B1 — x — MED\n\nbody\n"
    for label, header, must_survive in (
        ("half-readable", "| id | state (SEEDED-D) | priority SEEDED-H | what |", "SEEDED-D"),
        ("tab-indented", "\t| id | state (SEEDED-D) | priority (SEEDED-H) | what |", "SEEDED-H"),
        ("uppercase ID", "| ID | state (SEEDED-D) | priority (SEEDED-H) | what |", "SEEDED-H"),
    ):
        d = tmp_path / label.replace(" ", "_").replace("-", "_")
        d.mkdir()
        res = _run_raw(d, header + body, "--relabel")
        assert res.returncode == 9, f"{label}: expected the refusal, got {res.returncode}"
        text = (d / "docs" / "BACKLOG.md").read_text(encoding="utf-8")
        assert must_survive in text, f"{label}: a readable label was discarded"
        assert "(derived)" not in text, f"{label}: the fallback was written over it"


def test_a_header_with_no_readable_label_still_recovers(tmp_path: Path) -> None:
    """POSITIVE CONTROL for the row above, and the line the fix has to draw.

    `HDR_PRESENT` means "I can parse this header". `LABELS_SEEN` means "there is something here I
    would be discarding". Only the second may block the fallback: when NOTHING readable is present
    there is nothing to lose, and blocking would strand the operator with a header only a hand-edit
    could fix. Conflating the two is what made `--relabel` discard a good label.
    """
    body = "\n\n# Backlog\n\n## B1 — x — MED\n\nbody\n"
    res = _run_raw(tmp_path, "| id | state SEEDED-D | priority SEEDED-H | what |" + body, "--relabel")
    assert res.returncode == 0, f"the recovery path must stay open: {res.stderr}"
    header = _header_of(tmp_path)
    assert "(derived)" in header and "(hand-written)" in header
