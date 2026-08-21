"""The recorded start-of-work screen.

WHY FIXTURES AND NOT ONE HAND-BUILT STRING PER TEST. Each fixture differs from ok.md in EXACTLY ONE
field, so a red names one rule. A fixture broken two ways proves neither -- a coarse mutant that
kills two assertions establishes nothing about either.

The positive control (ok.md passing) is not decoration either: without it, a checker that reds on
everything looks perfect.
"""

import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHECK = ROOT / "skills/project-lifecycle/hooks/plc-kickoff-check.sh"
FIXTURES = ROOT / "scripts/testdata/kickoff"
STORY = ROOT / "docs/superpowers/specs/mode-fast-detailed-user-story.md"
KICKOFF_DOC = ROOT / "skills/project-lifecycle/references/kickoff-confirmation.md"

BANNED = ("cadence", "archetype", "oracle", "AC", "close-gate", "subagent", "validator")


def run(fixture):
    return subprocess.run(
        [
            "bash", str(CHECK), str(FIXTURES / fixture),
            "--story", str(STORY), "--phase", "1.2",
        ],
        capture_output=True, text=True, cwd=ROOT,
    )


story_missing = pytest.mark.skipif(
    not STORY.exists(), reason="the phase story is working material and is not shipped"
)


@story_missing
def test_the_good_fixture_passes():
    """The positive control. A checker that reds on everything would look perfect without it."""
    p = run("ok.md")
    assert p.returncode == 0, p.stdout + p.stderr


@story_missing
@pytest.mark.parametrize(
    "fixture,rule,needle",
    [
        ("banned-word.md", 1, "banned term 'validator'"),
        ("no-work-kind-reason.md", 2, "no 'because:'"),
        ("partial-criteria.md", 3, "all of them, not a summary"),
        ("criteria-reordered.md", 3, "different order"),
        ("outstanding-question.md", 4, "Start is unavailable"),
        ("no-not-for-fast.md", 5, "public-to-strangers"),
    ],
)
def test_each_fixture_reds_for_its_own_reason(fixture, rule, needle):
    p = run(fixture)
    assert p.returncode == 1, f"expected exit 1, got {p.returncode}: {p.stdout}{p.stderr}"
    combined = p.stdout + p.stderr
    assert needle in combined, combined
    assert f"rule {rule} " in combined, f"the failure did not name rule {rule}: {combined}"


@story_missing
def test_only_the_intended_rule_reds():
    """Each fixture is broken ONE way, so exactly one rule number may appear in its output.

    Without this, a fixture that happens to trip two rules would still pass the test above, and
    neither rule would have been established.
    """
    for fixture, rule in [
        ("banned-word.md", 1),
        ("no-work-kind-reason.md", 2),
        ("partial-criteria.md", 3),
        ("criteria-reordered.md", 3),
        ("outstanding-question.md", 4),
    ]:
        combined = run(fixture).stdout + run(fixture).stderr
        seen = {r for r in (1, 2, 3, 4, 5) if f"rule {r} " in combined}
        assert seen == {rule}, f"{fixture} tripped rules {sorted(seen)}, expected only {rule}"


def test_the_banned_list_is_the_documented_one():
    """The checker's list and the reference document's list are one list, or the rule is a rumour."""
    doc = KICKOFF_DOC.read_text(encoding="utf-8")
    src = CHECK.read_text(encoding="utf-8")
    for word in BANNED:
        assert word in doc, f"{word!r} is enforced but not documented"
        assert word in src, f"{word!r} is documented but not enforced"


def test_the_document_states_what_a_new_interruption_is():
    """The mechanical wording. Without it 'pause' is a judgement call and unenforceable."""
    doc = " ".join(KICKOFF_DOC.read_text(encoding="utf-8").split())
    assert "a turn *outside this screen* that waits for user input" in doc


def test_the_document_says_the_warning_does_not_block():
    """The kickoff check is a warning, not a barrier -- and a reader who assumes otherwise is worse off."""
    doc = " ".join(KICKOFF_DOC.read_text(encoding="utf-8").split())
    assert "This is a warning, not a barrier" in doc
