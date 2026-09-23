"""p30:AC17 -- the retired constraint has an obituary in each place p37 put it.

No CJK in this file, deliberately: the CJK rule exempts `docs/` outright and nothing else.

WHY AN OBITUARY AND NOT A DELETION. p37 did not merely enforce "write the counts as DIGITS and use
the word tracked" -- it deliberately WROTE that sentence into three surfaces, each with an
assertion, because the constraint was real and unstated and an adopter kept hitting it. Removing the
requirement while deleting every trace of it leaves the next reader unable to tell a deliberate lift
from an oversight: they find nothing, and nothing is what an unfinished job also looks like. So each
surface must both (a) no longer carry the instruction and (b) say that it is gone.

THE TWO HALVES ARE ASSERTED SEPARATELY ON PURPOSE. An assertion that only checked (a) would pass
against a silent deletion, which is the failure this test exists to prevent.
"""

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent

RETIRED = re.compile(r"write the counts as DIGITS", re.I)
# The lift, matched loosely enough to survive rewording but tightly enough to mean something: the
# surface must say the requirement is gone AND name what it was about.
LIFTED = re.compile(r"no longer requires? Arabic numerals|never shipped|was removed in p30|"
                    r"reshaped by the filing|What it removed", re.I)

SURFACES = {
    "CHANGELOG.md": "the entry an upgrader reads",
    "skills/project-lifecycle/references/close-gate.md": (
        "carries BOTH the per-key documentation an adopter looks up AND the canonical gate's "
        "failing rows"
    ),
    "scripts/close-gate.sh": "the gate this repository itself runs",
}


@pytest.mark.parametrize("rel,why", sorted(SURFACES.items()))
def test_the_retired_instruction_is_gone(rel: str, why: str) -> None:
    text = (ROOT / rel).read_text(encoding="utf-8")
    hits = RETIRED.findall(text)
    assert not hits, f"{rel} still carries the retired instruction ({why}): {hits}"


@pytest.mark.parametrize("rel,why", sorted(SURFACES.items()))
def test_each_surface_says_the_constraint_was_lifted(rel: str, why: str) -> None:
    text = (ROOT / rel).read_text(encoding="utf-8")
    assert LIFTED.search(text), (
        f"{rel} no longer carries the instruction, but never says it was lifted ({why}). "
        f"A reader who finds nothing cannot tell a deliberate removal from an unfinished job."
    )


def test_the_object_shape_is_what_the_docs_now_show() -> None:
    """The pasteable example in the docs must be the shape the gate now accepts.

    Pinned because a doc that still shows the deprecated array would send every new adopter down the
    path that prints a deprecation warning on their first run.
    """
    for rel in ("CHANGELOG.md", "skills/project-lifecycle/references/close-gate.md",
                "skills/project-lifecycle/references/init-harness.md",
                "commands/init-harness.md"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "surface_total" in text, f"{rel} does not show the object shape's members"
        assert "surface_kept" in text, (
            f"{rel} never mentions surface_kept -- an adopter is not told the gate derives it, "
            f"which is the one member they must NOT write"
        )


@pytest.mark.parametrize("rel", ["scripts/close-gate.sh",
                                 "skills/project-lifecycle/references/close-gate.md"])
def test_check_nines_refusal_rows_share_one_tail(rel: str) -> None:
    """The help/note tail is built once per gate home and referenced, not written out per branch.

    ADDED BY A REVIEW FINDING, not by design. The tail was originally spelled out in full in each of
    check 9's three refusal rows, in both homes -- six copies of the same ~500 characters -- and it
    had ALREADY DRIFTED inside this phase's own diff: two copies carried the "(here: N files)"
    parenthetical and the third did not. Cross-home agreement is held by the conformance suite;
    nothing held cross-BRANCH agreement inside one home, so a reviewer found the drift rather than a
    test.

    This pins the shape rather than the wording: exactly one assignment, and every refusal row
    referencing it. A future editor who inlines one branch's tail again has to do it deliberately,
    and this goes red when they do.
    """
    text = (ROOT / rel).read_text(encoding="utf-8")
    assigns = re.findall(r"^\s*RAT_TAIL=", text, re.M)
    assert len(assigns) == 1, f"{rel}: expected exactly one RAT_TAIL assignment, found {len(assigns)}"

    refusals = re.findall(r'^\s*bad "validator_input_paths_rationale \[check9-[a-z]+\].*$', text, re.M)
    assert len(refusals) == 3, f"{rel}: expected 3 check-9 refusal rows, found {len(refusals)}"
    for row in refusals:
        assert row.rstrip().endswith('| $RAT_TAIL"'), (
            f"{rel}: a refusal row spells its own tail instead of sharing the one built above -- "
            f"that is how the three drifted apart the first time:\n{row[:160]}"
        )
