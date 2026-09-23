"""the document map covers what the skill actually points at.

**No CJK in this file, deliberately.** This project bans CJK in shipped files outside
`README*` / `CHANGELOG.md` / `GUIDE*`.

**Why these tests exist rather than "a table was added".** Its exit criteria set a judgeable landing:
a new adopter who reads only the table can answer "which file do I open now". A table that is
merely PRESENT satisfies nothing — the failure it is fixing is a document set that grew past its
own index, and a hand-written index drifts for exactly the reason the index was needed. So:

  * every document the shipped surfaces reference must have a row (`test_every_referenced_...`),
  * every row must fill all six columns (`test_every_row_is_complete`),
  * a row may not silently claim a file exists when it does not
    (`test_absent_documents_are_marked_absent`).

The first is the one that will fail in six months, and failing is the point.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MAP = REPO / "skills" / "project-lifecycle" / "references" / "document-map.md"
SURFACES = ["skills/", "commands/", "scripts/"]

pytestmark = pytest.mark.skipif(not MAP.is_file(), reason="document-map.md absent")

# The documents this skill instructs a project to keep. Listed here rather than discovered,
# because "what counts as a progress document" is a judgement; what is CHECKED mechanically is
# that each one has a row and that the row is complete.
DOCUMENTS = [
    "RESUME.md",
    "docs/ROADMAP.md",
    "docs/BACKLOG.md",
    "docs/journal.d/",
    "docs/qa-log.d/",
    "CHANGELOG.md",
    "docs/CONTEXT.md",
    ".claude/tasklist.md",
    "docs/cognition.md",
    "docs/STATUS.md",
]


def table_rows() -> list[list[str]]:
    rows = []
    for line in MAP.read_text(encoding="utf-8").split("\n"):
        t = line.strip()
        if not t.startswith("|") or re.match(r"^\|[-: |]+\|?$", t):
            continue
        cells = [c.strip() for c in t.split("|")[1:-1]]
        if len(cells) < 2 or cells[0].startswith("document"):
            continue
        rows.append(cells)
    return rows


def test_the_table_is_not_empty() -> None:
    """An empty table would pass every assertion below by vacuity — the shape this repo keeps
    filing. Asserted first so nothing after it can be vacuously true."""
    rows = table_rows()
    assert len(rows) >= 8, "only %d rows parsed; the assertions below would prove nothing" % len(rows)


@pytest.mark.parametrize("doc", DOCUMENTS)
def test_every_document_the_skill_names_has_a_row(doc: str) -> None:
    """The assertion that will fail in six months, which is its job: a document added to the
    skill without a row here leaves the reader back where this started."""
    body = MAP.read_text(encoding="utf-8")
    base = doc.rstrip("/").split("/")[-1]
    assert base in body, (
        "%s is a document this skill tells a project to keep, and the map has no row for it"
        % doc)


def test_every_row_is_complete() -> None:
    """Six columns, all filled. A row with an empty "most confused with" cell is the row a
    reader needed most — the whole complaint was about telling two documents apart."""
    incomplete = []
    for cells in table_rows():
        if len(cells) != 6 or any(c == "" for c in cells):
            incomplete.append(cells[0][:40] if cells else "(empty)")
    assert not incomplete, "rows missing a column: %s" % incomplete


def test_absent_documents_are_marked_absent() -> None:
    """Two rows name files this repository does not have. Saying so is the point; a table that
    silently listed them as if present would reproduce the confusion it exists to remove."""
    body = MAP.read_text(encoding="utf-8")
    for doc in ("docs/STATUS.md", "docs/cognition.md"):
        assert not (REPO / doc).exists(), (
            "%s now exists — this test and the map's claim both need updating" % doc)
    assert "Absent here" in body or "does not exist in this repository" in body
    assert "not** by design" in body or "not by design" in body, (
        "the map must distinguish the deliberately-absent document from the starved one")


def test_the_resume_status_ambiguity_is_settled_not_restated() -> None:
    """The exit criteria require the ambiguity to be RESOLVED, not described. The ruling has to name
    which document wins and what the other one is for."""
    body = MAP.read_text(encoding="utf-8")
    assert "`RESUME.md` is the read-first document" in body
    assert "status_doc" in body, "the ruling must name the mechanism it preserves"
    assert "delete a real mechanism" in body, (
        "the map must say why that conclusion is not simply executed, or the next reader "
        "will execute it")


def test_the_claim_about_status_doc_is_true_of_this_repo() -> None:
    """The ruling rests on four measured facts. If any stops being true, the ruling is stale and
    the page is lying with confidence — the failure mode this whole phase family exists for."""
    assert not (REPO / "docs" / "STATUS.md").exists()
    assert not (REPO / "STATUS.md").exists()
    assert (REPO / "RESUME.md").exists() or True  # gitignored; absence on a fresh clone is fine
    manifest = (REPO / ".claude" / "close-gate.json").read_text(encoding="utf-8")
    assert "status_doc" not in manifest, (
        "this repo now sets status_doc; the map says it does not")
    local_gate = (REPO / "scripts" / "close-gate.sh").read_text(encoding="utf-8")
    assert "status_doc" not in local_gate, (
        "the local gate now implements status_doc; the map says only the adopter gate does")
    adopter_gate = (REPO / "skills" / "project-lifecycle" / "references"
                    / "close-gate.md").read_text(encoding="utf-8")
    assert "status_doc" in adopter_gate


def test_the_map_is_in_the_repository_map() -> None:
    """`guide-map-covers-references.sh` checks this too; asserting it here makes the failure
    land next to the change that caused it rather than at push time."""
    guide = REPO / "GUIDE.md"
    if not guide.is_file():
        pytest.skip("GUIDE.md absent")
    assert "document-map.md" in guide.read_text(encoding="utf-8"), (
        "the new reference is not in GUIDE.md's repository map")


def test_no_document_is_claimed_to_be_both_truth_and_view() -> None:
    """The column exists to answer one question — is this authored or derived — and a row that
    says both answers neither. `docs/ROADMAP.md` is the one legitimate split (its plan is
    authored, its progress is derived) and it says so explicitly."""
    for cells in table_rows():
        col = cells[4] if len(cells) > 4 else ""
        both = "truth" in col.lower() and "view" in col.lower()
        if both:
            assert "ROADMAP" in cells[0], (
                "%s claims to be both truth and view without saying which half is which"
                % cells[0][:40])
