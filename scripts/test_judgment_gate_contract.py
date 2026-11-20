"""Structural test for references/judgment-gate.md.

The hook's deny reason points at this contract, so its four named sections and
fixed vocabulary must not silently disappear.
"""

import pathlib
import re

DOC = (pathlib.Path(__file__).parent.parent
       / "skills/project-lifecycle/references/judgment-gate.md")


def _text():
    assert DOC.is_file(), f"missing contract: {DOC}"
    return DOC.read_text(encoding="utf-8")


def _section(marker):
    t = _text()
    parts = re.split(r"(?m)^## ", t)
    hits = [p for p in parts if marker in p.split("\n", 1)[0]]
    assert hits, f"section heading containing {marker!r} not found"
    return hits[0]


def test_contract_has_four_required_sections():
    for m in ("A-1", "A-2", "A-3", "A-4"):
        _section(m)


def test_surfacing_has_three_openings():
    s = _section("A-1")
    for phrase in ("None of these, I'll tell you", "I'm not sure, suggest more", "You decide"):
        assert phrase in s
    assert "escape option" in s and "options" in s


def test_a2_is_shadow_recording_protocol():
    s = _section("A-2")
    assert "shadow" in s.lower()
    for phrase in ("record what you would do", "do not block", "do not hide", "do not release"):
        assert phrase in s
    assert "judgment-shadow-record.sh" in s


def test_a2_drops_the_three_question_self_check():
    s = _section("A-2")
    for q in ("touch something the user can see", "copy, the data model, or an API"):
        assert q not in s


def test_a2_has_authorization_stack():
    s = _section("A-2")
    for phrase in ("authorization", "who", "scope", "authorization_tier"):
        assert phrase in s


def test_a2_timing_map_pins_each_type_to_its_time():
    s = _section("A-2")
    rows = {}
    for line in s.splitlines():
        m = re.match(r"\|\s*`?([a-z-]+)`?\s*\|\s*`?([a-z-]+)`?\s*\|\s*`?([a-z-]+)`?\s*\|", line)
        if m:
            rows[m.group(1)] = (m.group(2), m.group(3))
    assert rows.get("taste") == ("shadow-record", "at-finish")
    assert rows.get("product-boundary") == ("confirm-before-build", "before-build")
    assert rows.get("side-effect") == ("hard-stop", "none")
    assert rows.get("mechanical") == ("do-and-report", "none")


def test_a2_states_log_line_shape():
    s = _section("A-2")
    for f in ("id", "what", "authorization_tier", "decision_type", "would_action", "would_time"):
        assert f in s
    assert "plc-judgment-shadow" in s


def test_report_template_three_lines():
    s = _section("A-3")
    for line in ("Before", "What changed", "new tests", "Why"):
        assert line in s


def test_contract_degrades_gracefully():
    s = _section("A-4")
    assert "mock" in s
    assert "None" in s and ("in chat" in s)
