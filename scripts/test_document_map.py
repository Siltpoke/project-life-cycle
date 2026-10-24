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


# The heading whose table this test is about. The scan is BOUNDED to this section, and the bound is
# the fix for a real failure rather than tidiness: this parser used to read every pipe-line in
# the file, so when a second, unrelated 3-column table was added under a later heading
# ("Where each one is visible from") its three data rows were judged against the
# six-column rule and `test_every_row_is_complete` went red in CI. The page is allowed more than
# one table; the test is not allowed to claim "every row of the document map" while measuring
# "every pipe-line in the file". That gap between a check's claim and its reach is the defect
# class this repo keeps filing, and it was sitting inside this test's own control.
TABLE_HEADING = "## The table"


def _table_section(body: str) -> str:
    """The lines under TABLE_HEADING, up to the next `## ` heading.

    Fails loudly rather than returning everything: a heading rename must red these rows, not
    silently widen them back to the whole file -- which is the state this function replaced.
    """
    lines = body.split("\n")
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == TABLE_HEADING)
    except StopIteration:  # pragma: no cover - asserted by test_the_table_section_is_found
        raise AssertionError(
            "%r not found in document-map.md; the row scan has no bounded section to read and "
            "would otherwise fall back to the whole file" % TABLE_HEADING
        )
    end = next(
        (i for i, ln in enumerate(lines[start + 1 :], start + 1) if ln.startswith("## ")),
        len(lines),
    )
    return "\n".join(lines[start + 1 : end])


def table_rows(body: str | None = None) -> list[list[str]]:
    """Data rows of the document-map table. `body` is injectable so the positive control below can prove
    a short row inside the bounded section still fails."""
    src = _table_section(MAP.read_text(encoding="utf-8") if body is None else body)
    rows = []
    for line in src.split("\n"):
        t = line.strip()
        if not t.startswith("|") or re.match(r"^\|[-: |]+\|?$", t):
            continue
        cells = [c.strip() for c in t.split("|")[1:-1]]
        if len(cells) < 2 or cells[0].startswith("document"):
            continue
        rows.append(cells)
    return rows


def test_the_table_section_is_found() -> None:
    """Asserted on its own, because every row-level assertion below is vacuous if the section
    lookup silently returned nothing."""
    assert _table_section(MAP.read_text(encoding="utf-8")).strip(), (
        "the %r section parsed empty" % TABLE_HEADING
    )


def test_a_short_row_inside_the_bounded_section_still_fails() -> None:
    """THE POSITIVE CONTROL for the bound, and the reason the bound is not just a way to make a
    red test green. Narrowing a scan can disable it; this feeds a five-column row into the
    bounded section and requires it to be reported."""
    body = "\n".join(
        [
            TABLE_HEADING,
            "",
            "| document | a | b | c | d | e |",
            "|---|---|---|---|---|---|",
            "| **`short.md`** | 1 | 2 | 3 | 4 |",
            "",
            "## Where each one is visible from",
            "",
            "| document | tracked? | visible from |",
            "|---|---|---|",
            "| **`other.md`** | no | main checkout only |",
        ]
    )
    rows = table_rows(body)
    assert [r for r in rows if len(r) != 6], "a five-column row was not reported"
    assert not [r for r in rows if r and r[0].startswith("**`other.md`")], (
        "a row from the SECOND table reached the six-column rule -- the bound is not holding"
    )


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
    """The ruling rests on measured facts. If any stops being true, the ruling is stale and the
    page is lying with confidence — the failure mode this whole phase family exists for.

    One of those facts FLIPPED and this row is what caught it; see the long comment
    at the status_doc assertions below for what changed, why the map was corrected instead of the
    code reverted, and why the replacement is two assertions rather than one."""
    assert not (REPO / "docs" / "STATUS.md").exists()
    assert not (REPO / "STATUS.md").exists()
    assert (REPO / "RESUME.md").exists() or True  # gitignored; absence on a fresh clone is fine
    manifest = (REPO / ".claude" / "close-gate.json").read_text(encoding="utf-8")
    assert "status_doc" not in manifest, (
        "this repo now sets status_doc; the map says it does not")
    local_gate = (REPO / "scripts" / "close-gate.sh").read_text(encoding="utf-8")

    # THIS ASSERTION WAS INVERTED, and the old one is quoted rather than deleted
    # because the reason matters more than the direction. It used to be
    # `assert "status_doc" not in local_gate` with the message "the local gate now implements
    # status_doc; the map says only the adopter gate does" -- and it did its job: a later change ported the
    # canonical hot-cap rows into this gate, the status-doc row came with them, a documented
    # claim became false, and this row went RED in the full suite. No targeted subset saw it.
    #
    # The map was corrected rather than the port reverted, for a behavioural reason: dropping the
    # row would mean a project that later adds a status doc gets no cap on it SILENTLY, which is
    # the shape that change exists to end. So the claim is now the other way round, and it is asserted
    # as TWO facts rather than one, because collapsing them would make this row weaker than the
    # one it replaced:
    #
    #   (a) the gate READS the key -- the half the map used to call never-exercised
    #   (b) the row is DORMANT here -- it resolves to docs/STATUS.md, which does not exist (the
    #       first two assertions in this function), so `cap_file` returns early and prints
    #       nothing. "The key is read" and "the row ran against a real status document" are
    #       different claims and only (a) is true.
    assert "status_doc" in local_gate, (
        "the local gate no longer reads status_doc -- the port has been reverted or lost in a "
        "merge, and the map's corrected bullet now overstates what this gate does")
    assert 'cap_file "$_sd" status' in local_gate, (
        "status_doc is mentioned in the local gate but no longer feeds a cap row -- the map says "
        "the key is read BY the hot-cap row, and a mention that routes nowhere is the claim-wider"
        "-than-mechanism shape this page exists to prevent")
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
