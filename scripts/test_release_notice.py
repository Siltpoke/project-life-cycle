"""p37:AC12 — an upgrading adopter is told, not surprised.

A SEPARATE MODULE on purpose. scripts/test_changelog_headings.py refuses to read this repo's own
CHANGELOG, and says why in its docstring: a suite whose verdict depends on a tracked document goes
red for reasons that have nothing to do with the mechanism it tests. That reasoning is right for
that module, whose subject is an invariant script. It does not apply here, because THIS module's
subject IS the tracked document -- the notice is the deliverable, so the document is the mechanism.

WHAT THIS CANNOT DO, stated rather than left to be assumed: it checks that the notice is present and
carries the parts a surprised adopter would need. It cannot check that the notice is TRUE, or that
anyone read it. A `[Unreleased]` entry is a claim about a release that has not happened.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "CHANGELOG.md"
KEY = "validator_input_paths_rationale"


def _unreleased() -> str:
    text = CHANGELOG.read_text(encoding="utf-8")
    start = text.index("\n## [Unreleased]")
    nxt = text.find("\n## ", start + 1)
    return text[start : nxt if nxt != -1 else len(text)]


def test_the_unreleased_section_names_the_key() -> None:
    assert KEY in _unreleased(), (
        f"CHANGELOG.md's [Unreleased] section does not name {KEY}. An adopter whose gate starts "
        f"failing on a key they never wrote learns about it here or not at all."
    )


def test_the_notice_carries_a_fix_that_can_be_pasted() -> None:
    """Naming the key without showing a value that satisfies it is a notice that creates work
    rather than removing it.

    p30 MIGRATED THIS, and what it used to assert is worth keeping in view: it required a
    SINGLE LINE containing the key and the word `tracked` and at least two digits -- the old
    array shape's one-liner. Both halves of that are gone. The value is an object now, which
    cannot be one readable line, and `tracked` is no longer a requirement on anything: it is one
    of four enum values for `basis`, and an adopter may pick a different one.

    The property is unchanged: the notice must show a value the gate would ACCEPT. What that
    means now is the object's required members present and the derived member absent.
    """
    section = _unreleased()
    assert re.search(rf'"{KEY}":\s*\{{', section), (
        "the notice names the key but shows no object to paste"
    )
    assert re.search(r'"surface_total":\s*\d+', section), (
        "the pasteable example has no numeric surface_total, so it is an example of a value the "
        "gate would REFUSE"
    )
    assert re.search(r'"basis":\s*"(tracked-files|all-files|glob-set|explicit-path-list)"', section), (
        "the pasteable example's basis is not one of the four values the gate accepts"
    )
    assert "surface_kept" in section, (
        "the notice never mentions surface_kept -- an adopter is not told the gate derives it, "
        "which is the one member they must NOT write"
    )
    assert not re.search(r'"surface_kept":', section), (
        "the pasteable example DECLARES surface_kept, which the gate refuses -- the notice would "
        "be teaching the exact mistake it exists to prevent"
    )


def test_the_notice_states_who_is_unaffected() -> None:
    """A migration notice that only says what broke leaves every reader unsure whether it is about
    them. The coupling is the reassuring half and it belongs in the notice, not only in the code."""
    section = _unreleased()
    assert "test_evidence_inputs" in section, "the notice does not name what the key is coupled to"
    assert re.search(r"absent|do not narrow|does not fire", section), (
        "the notice does not say that a manifest which narrows nothing is unaffected"
    )


def test_the_pasteable_literal_is_actually_pasteable() -> None:
    """FOUND BY A BLIND CROSS-FAMILY REVIEW, and it was a real defect in the notice rather than a
    style point: the example was wrapped across two source lines for margin width, and a JSON string
    cannot contain a literal newline. An adopter who read the upgrade notice and copied the span got
    `Invalid control character` before ever reaching the rationale check -- the failure landed on
    exactly the person who did the right thing.

    Reproduced before fixing: json.loads on the copied span raised
    `Invalid control character at: line 1 column 91`.

    The assertion is the property, not the layout: extract the member as it appears and require that
    it PARSE. A pin on "no line break here" would go green the day someone reflowed the paragraph a
    different wrong way.

    p30 MIGRATED THE EXTRACTION, NOT THE PROPERTY. The old version additionally required the member
    to sit on ONE physical line and to parse to a non-empty ARRAY. The object shape cannot be one
    readable line, so that half was dropped -- deliberately, and it is the only requirement removed
    here. What replaces it is stricter about what actually matters: the block must parse AND carry
    the members the gate reads by name.
    """
    import json

    section = _unreleased()
    block = re.search(rf'("{KEY}":\s*\{{.*?\n  \}})', section, re.S)
    assert block, f"no {KEY} object found in the notice to paste"
    obj = json.loads("{" + block.group(1) + "}")  # raises if the notice cannot be pasted
    value = obj[KEY]
    assert isinstance(value, dict), "the pasted member is not an object"
    assert isinstance(value.get("surface_total"), (int, float)), (
        "the pasted surface_total is not a JSON number -- a numeric string is refused by the gate"
    )
    assert value.get("basis") in ("tracked-files", "all-files", "glob-set", "explicit-path-list")
    assert isinstance(value.get("why"), list) and value["why"], "why is not a non-empty array"
    assert "surface_kept" not in value, "the pasted object declares the derived member"


def test_the_notice_says_the_phrasing_constraint_is_GONE() -> None:
    """THIS TEST WAS WRITTEN TO EXPIRE, AND p30 IS WHAT EXPIRED IT.

    Its previous docstring ended: *"Filed; until it is resolved, the notice has to SAY so."*
    It required the notice to state that the counts must be written as digits and that the rationale
    must contain the English word `tracked` -- a constraint that refused honest arguments written in
    another language, and one the gate no longer has.

    So the assertion is INVERTED rather than deleted. Deleting it would leave the notice free to
    drift back into demanding a language with nothing watching; and an adopter who read the old
    notice needs to be told the demand is lifted, not merely to find it absent. Both halves are
    asserted for that reason: the demand must be gone, AND the notice must say it is gone.
    """
    section = _unreleased()
    assert not re.search(r'say "tracked"|must contain the tracked-surface word', section), (
        "the notice still demands the English word `tracked` -- p30 removed that requirement"
    )
    assert not re.search(r"[Ww]rite the counts as digits", section), (
        "the notice still demands Arabic numerals -- p30 removed that requirement"
    )
    # `\s+` and not a literal space, and that is this file's own lesson applied to itself: the
    # phrase is wrapped across two source lines for margin width, exactly as the pasteable example
    # once was. The first draft of this assertion pinned a literal "any language" and went red on a
    # notice that says precisely that. Pin the property, never the layout.
    assert re.search(r"any\s+language", section), (
        "the notice does not tell the reader the prose may be written in any language, which is "
        "the whole of what that change did for them"
    )
    assert re.search(r"never shipped|reshaped by", section), (
        "the notice does not say the intermediate shape existed and never shipped -- a reader who "
        "finds no trace of it cannot tell a deliberate lift from an oversight"
    )
