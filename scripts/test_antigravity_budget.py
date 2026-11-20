"""Antigravity loads only the first 24,000 bytes of the main skill file's body.

`agy plugin validate` (1.4.8) reports: `skills/project-lifecycle/SKILL.md: the body is 116018 bytes;
only the first 24000 are loaded`. The README tells Antigravity users that the part they do get holds
the Definition of Done and the close-gate rules. That sentence is only true while the section sits
inside the cut, and nothing else notices if an edit above it pushes it out. This test is what
keeps the README's claim true.

What it measures is byte position, not what the agent read; HOST-VERIFICATION.md says so.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/project-lifecycle/SKILL.md"
AGY_BODY_BUDGET = 24000  # agy 1.4.8, `agy plugin validate`


def _body() -> bytes:
    raw = SKILL.read_bytes()
    assert raw.startswith(b"---\n"), "SKILL.md no longer opens with frontmatter"
    end = raw.index(b"\n---\n", 4) + len(b"\n---\n")
    return raw[end:]


def _section_span(body: bytes, heading: bytes):
    at = body.find(b"\n" + heading)
    assert at != -1, (
        f"SKILL.md has no '{heading.decode()}' heading any more. This test and the README's Antigravity "
        "note refer to that section by name -- update both if it was renamed."
    )
    start = at + 1
    nxt = body.find(b"\n## ", start + len(heading))
    return start, (nxt + 1 if nxt != -1 else len(body))


def test_definition_of_done_is_inside_what_antigravity_loads():
    body = _body()
    start, end = _section_span(body, b"## Definition of Done")
    assert end <= AGY_BODY_BUDGET, (
        f"the Definition of Done section ends at body byte {end}, past Antigravity's {AGY_BODY_BUDGET}-byte "
        "load limit. README.md / README.zh-CN.md tell Antigravity users this section is loaded -- move it "
        "up, shorten what is above it, or change the README."
    )


def test_the_close_gate_rule_is_inside_that_section():
    body = _body()
    start, end = _section_span(body, b"## Definition of Done")
    gate = body.find(b"Run the close gate", start)
    assert start <= gate < end, "the close-gate rule is no longer inside the Definition of Done section"
