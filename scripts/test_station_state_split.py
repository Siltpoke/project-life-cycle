"""a bound row takes its state from the derivation; every other row does not.

**No CJK in this file, deliberately.** This project bans CJK in shipped files outside
`README*` / `CHANGELOG.md` / `GUIDE*`.

**THIS IS A SPLIT AND NOT A DELETE, and the difference is the whole test file.** The first
plan said "remove the inclusive done check". Measured on this repository at the time of
writing, that removes every finished row from `mainline_done` — the done glyph sits INSIDE the name
cell on all 47 and leads it on none — and **no test would have gone red**, because the new
mechanism is only reachable by rows that have a plan block and those 47 never will (a
station id exists only where a block does). The plan's cross-check caught it and required
the assertion `test_legacy_rows_are_byte_identical` makes.

**AC-7, the glyph-never-enters case, needs a station WITH a plan block and NO closure
declaration** (plan R2-13). A fixture that supplies both a declaration and a glyph is
passed by a bad implementation that falls back to the glyph whenever the declaration is
missing — the branch never gets reached. So the fixture below has a plan block, zero closed
steps, and a done glyph sitting in the name cell: the honest answer is `0/N` and not done,
and the fallback implementation says done.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "scripts" / "session_card.py"
ROADMAP = REPO / "docs" / "ROADMAP.md"

_spec = importlib.util.spec_from_file_location("session_card_split_under_test", SRC)
sc = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(sc)

NO_FACTS = {"blocks": {}, "active": [], "closed": {}, "available": False, "why": "test"}


def facts(*, nsteps=3, closed=(), active=(), binds_to="**Row A**", sid="ci-line",
          depends_on="none"):
    return {
        "blocks": {sid: {"binds_to": binds_to, "nsteps": nsteps,
                         "steps": [str(i) for i in range(1, nsteps + 1)],
                         "depends_on": depends_on}},
        "active": list(active),
        "closed": {sid: {str(c) for c in closed}} if closed else {},
        "available": True,
        "why": "",
    }


def roadmap(*rows: str) -> str:
    head = ("# R\n\n## \U0001f6e3 Mainline\n\n| station | what | weight | eta |\n"
            "|---|---|---|---|\n")
    return head + "".join("| %s | what | w | e |\n" % r for r in rows) + "\n"


# ============================================================ the plan's own assertion


@pytest.mark.skipif(not ROADMAP.exists(), reason="gitignored docs/ absent (fresh clone)")
def test_legacy_rows_are_byte_identical_with_and_without_the_derivation() -> None:
    """The assertion the cross-check demanded. Unbound rows must be untouched by T7b, and
    "untouched" is asserted byte for byte rather than by count: a swap of two entries keeps
    the count and changes what the card prints."""
    md = ROADMAP.read_text(encoding="utf-8")
    plain = sc.parse_roadmap(md)
    derived = sc.parse_roadmap(md, sc._station_facts(REPO))
    assert plain["mainline_done"], "no finished rows parsed — the comparison would be vacuous"
    assert json.dumps(plain["mainline_done"], ensure_ascii=False) == \
           json.dumps(derived["mainline_done"], ensure_ascii=False)


@pytest.mark.skipif(not ROADMAP.exists(), reason="gitignored docs/ absent (fresh clone)")
def test_a_call_without_facts_is_the_pre_split_parser() -> None:
    """An adopter who calls `parse_roadmap(md)` — the signature before this task — must get
    exactly what they got before, including on a roadmap that HAS plan blocks."""
    md = ROADMAP.read_text(encoding="utf-8")
    a = sc.parse_roadmap(md)
    b = sc.parse_roadmap(md, None)
    for k in ("mainline_done", "doing", "mainline", "unreadable_rows"):
        assert json.dumps(a[k], ensure_ascii=False, sort_keys=True) == \
               json.dumps(b[k], ensure_ascii=False, sort_keys=True), k


# ============================================================ AC-7: the glyph is out


def test_a_bound_row_with_a_done_glyph_and_no_closed_steps_is_not_done() -> None:
    """The case a fallback implementation gets wrong. Plan block present, declarations
    absent, done glyph sitting in the name cell where this repo actually writes it."""
    md = roadmap("Row A shipped ✅", "Row B legacy ✅")
    out = sc.parse_roadmap(md, facts(binds_to="Row A shipped ✅"))
    assert out["mainline_done"] == ["Row B legacy ✅"], out["mainline_done"]
    assert out["stations"]["ci-line"]["position"] == "0/3"
    assert out["stations"]["ci-line"]["state"] == "future"


def test_changing_only_the_glyph_on_a_bound_row_changes_nothing() -> None:
    """State never comes from a glyph on a bound row — asserted by mutating ONLY the glyph
    and comparing the derived state, which is what AC-7 asks for."""
    f = facts(binds_to="Row A", closed=(1, 2, 3))
    with_glyph = sc.parse_roadmap(roadmap("Row A"), f)
    assert with_glyph["stations"]["ci-line"]["state"] == "done"
    # The row text is what binds, so the glyph goes in a way that keeps the binding: a
    # second block bound to the glyphed spelling, same steps closed.
    f2 = facts(binds_to="Row A ✅", closed=(1, 2, 3))
    with_glyph2 = sc.parse_roadmap(roadmap("Row A ✅"), f2)
    assert with_glyph2["stations"]["ci-line"]["state"] == "done"
    assert with_glyph["stations"]["ci-line"]["position"] == \
           with_glyph2["stations"]["ci-line"]["position"]


def test_all_steps_closed_makes_a_bound_row_done_even_with_no_glyph() -> None:
    md = roadmap("Row A")
    out = sc.parse_roadmap(md, facts(binds_to="Row A", closed=(1, 2, 3)))
    assert out["mainline_done"] == ["Row A"]
    assert out["stations"]["ci-line"]["position"] == "3/3"


def test_the_active_list_is_what_makes_a_bound_row_doing() -> None:
    md = roadmap("Row A")
    out = sc.parse_roadmap(md, facts(binds_to="Row A", closed=(1,), active=("ci-line",)))
    assert out["doing"] == ["Row A"]
    assert out["stations"]["ci-line"]["position"] == "1/3"


def test_a_partly_closed_row_not_in_the_active_list_is_future() -> None:
    md = roadmap("Row A")
    out = sc.parse_roadmap(md, facts(binds_to="Row A", closed=(1,)))
    assert out["mainline_done"] == []
    assert out["doing"] == []
    assert [r["name"] for r in out["mainline"]] == ["Row A"]


# ============================================================ honest degradation


def test_an_unavailable_deriver_is_undecidable_not_zero() -> None:
    """`0/N` is a claim about history; it must not be what a broken deriver prints. A row
    whose state could not be derived joins the honest count instead."""
    f = facts(binds_to="Row A")
    f["available"] = False
    f["why"] = "reader missing: closure-declaration.sh"
    out = sc.parse_roadmap(roadmap("Row A"), f)
    assert out["mainline_done"] == []
    assert out["doing"] == []
    assert [r["name"] for r in out["mainline"]] == []
    assert out["unreadable_rows"] == 1
    assert out["stations"]["ci-line"]["position"] is None


def test_station_facts_degrades_rather_than_raising(tmp_path: Path) -> None:
    """A directory with no readers at all. The card must still render."""
    out = sc._station_facts(tmp_path)
    assert out["available"] is False
    assert out["why"], "an unavailable deriver must say why"
    assert out["blocks"] == {}


def test_a_zero_step_station_is_never_trivially_done() -> None:
    """0 of 0 reads as complete to the obvious comparison. station-id-integrity.sh makes a
    zero-step block impossible, but this reader must not depend on that being true."""
    f = facts(nsteps=0)
    st = sc.station_state(f, "ci-line")
    assert st["state"] != "done", st


def test_the_binding_is_binds_to_and_not_the_glyph_or_the_position() -> None:
    """The boundary between the two paths, asserted directly. A row that merely LOOKS like
    a station — same shape, same glyph — is legacy until a block names it."""
    md = roadmap("Row A", "Row B")
    out = sc.parse_roadmap(md, facts(binds_to="Row B", closed=(1, 2, 3)))
    assert out["mainline_done"] == ["Row B"], out["mainline_done"]
    assert [r["name"] for r in out["mainline"]] == ["Row A"]


def test_binding_survives_bold_on_either_side() -> None:
    """Both sides are compared after the same normalisation, so whether the author bolded
    the row, the binds-to, both or neither cannot decide whether a station exists."""
    for row, bind in (("**Row A**", "Row A"), ("Row A", "**Row A**"),
                      ("**Row A**", "**Row A**")):
        out = sc.parse_roadmap(roadmap(row), facts(binds_to=bind, closed=(1, 2, 3)))
        assert out["mainline_done"] == ["Row A"], (row, bind, out["mainline_done"])


def test_a_dangling_closed_step_does_not_inflate_the_position() -> None:
    """Added because a mutant survived. Dropping the "was this step ever declared" filter
    left every case above green — no fixture had a closure declaration naming a step the
    block does not declare, so the numerator was never asked to reject one.

    It matters beyond tidiness: a station with three steps and a declaration naming `s9`
    would read 1/3, or with three such tokens 3/3 and DONE, from work that resolves to
    nothing. `closed-step-refs-resolve.sh` reddens a dangling token at gate time, but the
    card must not print a number that depends on the gate having been run.
    """
    f = facts(nsteps=3, closed=(9,))
    st = sc.station_state(f, "ci-line")
    assert st["position"] == "0/3", st
    assert st["state"] != "done"

    f2 = facts(nsteps=3, closed=(1, 7, 8, 9))
    st2 = sc.station_state(f2, "ci-line")
    assert st2["position"] == "1/3", st2
    assert st2["state"] != "done"


# ============================================================ T7c: what the card prints


def test_a_station_line_separates_blocked_by_from_the_position() -> None:
    """`blocked-by:` and `next:` must never be one field. A reader who sees them merged
    takes a dependency for a priority — and this format declares dependencies, never order,
    which is B9022's whole subject. `next:` is therefore ABSENT rather than invented: no
    source in this format declares what comes next, and deriving it from dependency order
    would be exactly the sequence B9022 says this document does not carry.

    Asserted against the source because the claim is about what the renderer CAN emit, not
    about one sample of its output."""
    src = SRC.read_text(encoding="utf-8")
    assert "blocked-by: %s" in src, "the station line stopped naming blocked-by"
    assert '"  next:' not in src and "'  next:" not in src, (
        "something emits a `next:` field; no source in this format declares one")


def test_the_position_prints_a_dash_when_the_deriver_could_not_run() -> None:
    """`0/3` is a claim about history and must not be what a broken deriver prints."""
    f = facts(binds_to="Row A")
    f["available"] = False
    f["why"] = "reader missing"
    rm = sc.parse_roadmap(roadmap("Row A"), f)
    assert rm["stations"]["ci-line"]["position"] is None
    assert rm["station_facts_available"] is False
    assert rm["station_facts_why"] == "reader missing"


def test_a_station_with_a_plan_and_no_work_reports_zero_over_n() -> None:
    """B9021's Exit falsifier, as a test: a station that has a plan and has done nothing
    renders `0/N` — not blank, and not done."""
    rm = sc.parse_roadmap(roadmap("Row A"), facts(binds_to="Row A"))
    assert rm["stations"]["ci-line"]["position"] == "0/3"
    assert rm["stations"]["ci-line"]["state"] != "done"


def test_the_stations_key_is_emitted_even_when_there_are_none() -> None:
    """An absent key and an empty one read differently to a renderer, and `no stations yet`
    is a real answer rather than a missing one."""
    rm = sc.parse_roadmap(roadmap("Row A"))
    assert "stations" in rm and rm["stations"] == {}
    assert rm["station_facts_available"] is False
