"""the two glyph readers in session_card.py normalise a cell the same way.

**No CJK in this file, deliberately.** This project bans CJK in shipped files outside
`README*` / `CHANGELOG.md` / `GUIDE*`.

**The defect, measured before the fix rather than argued from the code.** `session_card.py`
recognises status glyphs in two places: the emoji-fisheye main loop, which cleaned the cell
first (`**bold**` and backticks stripped) and then looked for the glyph, and
`_milestone_table_rows`, the fallback for the Milestones-table layout, which only did
`.lstrip()`. So a status cell written `**✅ done**` — a whole-cell bold, which is how a
migrating author writes it and how the retired convention in this repo was written — was a
finished milestone to one reader and invisible to the other.

The asymmetry mattered most where it was least visible: the fallback runs only when the
fisheye parse yields nothing, so on exactly the documents where it is the ONLY reader,
a bold status cell dropped the row silently.

This file is a separate commit from the format work by the plan's instruction, so that a
regression here can be bisected without a format change in the same diff.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "scripts" / "session_card.py"

_spec = importlib.util.spec_from_file_location("session_card_under_test", SRC)
sc = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(sc)


ROW = "| 1 | Name | what | {} |"
WRAPPINGS = [
    pytest.param("✅ done", id="plain"),
    pytest.param("**✅ done**", id="whole-cell-bold"),
    pytest.param("`✅ done`", id="code-span"),
    pytest.param("   ✅ done", id="leading-space"),
    pytest.param("**✅** done", id="bold-glyph-only"),
]


@pytest.mark.parametrize("cell", WRAPPINGS)
def test_the_fallback_reads_the_glyph_through_markup(cell: str) -> None:
    rows = sc._milestone_table_rows(ROW.format(cell))
    assert rows, f"the fallback did not see a status glyph in {cell!r}"
    assert rows[0][0] == sc._G_DONE
    assert rows[0][1] == "1 Name"


@pytest.mark.parametrize("cell", WRAPPINGS)
def test_both_readers_normalise_a_cell_identically(cell: str) -> None:
    """The parity itself, stated as one assertion rather than two lists that happen to
    match: whatever the fallback accepts as a leading glyph, `_clean_cell` — the function
    the fisheye loop uses — must also expose as leading."""
    assert sc._clean_cell(cell).startswith(sc._G_DONE)
    assert sc._milestone_table_rows(ROW.format(cell))[0][0] == sc._G_DONE


@pytest.mark.parametrize("raw,want", [
    pytest.param("| 1 | **Name** | what | ✅ done |", "1 Name", id="bold-name"),
    pytest.param("| 1 | `Name` | what | ✅ done |", "1 Name", id="code-name"),
    pytest.param("| 1 | **`m4`** — a name | what | ✅ done |", "1 m4 — a name",
                 id="interior-markup"),
])
def test_the_fallback_normalises_the_NAME_the_same_way_too(raw: str, want: str) -> None:
    """Added because a mutant survived. Replacing the name-side `_clean_cell` with a bare
    `.strip()` left every case above green — every fixture in this file had written the name
    as plain `1 Name`, so the assertion covered the glyph side of the merge and nothing else.
    A surviving mutant is a map of what was never tested, and this is that map turned into
    cases: the interior-markup one is B9004's original defect, on the path that had no test
    for it at all."""
    rows = sc._milestone_table_rows(raw)
    assert rows, raw
    assert rows[0][1] == want, rows


def test_a_glyph_that_does_not_lead_is_still_not_a_milestone_row() -> None:
    """The widening must not become "a glyph appears somewhere". The leading anchor is the
    structure that separates a Status cell from a table that merely mentions a glyph, and
    stripping markup was never meant to relax it."""
    assert sc._milestone_table_rows("| 1 | Name | what | shipped, see ✅ above |") == []
    assert sc._milestone_table_rows("| 1 | Name | ✅ what | notes |") == []


def test_a_row_with_fewer_than_four_cells_is_still_not_a_milestone_row() -> None:
    assert sc._milestone_table_rows("| Name | ✅ done |") == []


def test_clean_cell_still_strips_interior_markup() -> None:
    """B9004's original reason for the function, kept under the rename: the old
    `.strip().strip('`')` only touched the ends of the span."""
    assert sc._clean_cell("**`m4`** — a name") == "m4 — a name"


def test_there_is_exactly_one_cell_normaliser_left() -> None:
    """A source-level assertion, and it is here because the merge is the deliverable. Two
    normalisers agreeing today is not the same as one normaliser: the previous state was
    two functions that agreed on most inputs, which is how the disagreement survived."""
    src = SRC.read_text(encoding="utf-8")
    # The bold-stripping regex is the signature of a normaliser. One definition, plus no
    # second inline copy anywhere.
    assert src.count(r'r"\*\*(.+?)\*\*"') == 1, (
        "a second inline markup-stripping regex reappeared; route it through _clean_cell"
    )
    assert "def _clean_name(" not in src, "the pre-merge nested normaliser came back"
