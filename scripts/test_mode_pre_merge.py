"""The pre-merge brief.

Each fixture is broken in exactly ONE way, so a red names one rule. The positive control (ok.md
passing) is load-bearing: without it a checker that reds on everything looks perfect.
"""

import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHECK = ROOT / "skills/project-lifecycle/hooks/plc-pre-merge-brief.sh"
FIXTURES = ROOT / "scripts/testdata/pre-merge"
DOC = ROOT / "skills/project-lifecycle/references/pre-merge-brief.md"

DISCLAIMER = "It is NOT someone having read the code."


def run(fixture):
    return subprocess.run(
        ["bash", str(CHECK), str(FIXTURES / fixture)],
        capture_output=True, text=True, cwd=ROOT,
    )


def test_the_good_fixture_passes():
    p = run("ok.md")
    assert p.returncode == 0, p.stdout + p.stderr


@pytest.mark.parametrize(
    "fixture,needle",
    [
        # the block's fixed structure
        ("no-disclaimer.md", "missing or paraphrased"),
        ("softened-disclaimer.md", "missing or paraphrased"),
        ("five-items.md", "carries exactly four"),
        ("missing-item-2.md", "'unchecked-criteria' is absent"),
        ("empty-item-2.md", "written as 'none'"),
        ("empty-guidance-silent.md", "flags nothing and does not say so"),
        # two counts, separately
        ("merged-counts.md", "intent-gate tap count is missing"),
        ("no-intent-gate-count.md", "intent-gate tap count is missing"),
        # which mode this phase ran in
        ("no-mode-line.md", "does not state which mode"),
        # the smoke checklist sits below and does not block
        ("smoke-above-items.md", "belongs below them"),
    ],
)
def test_each_fixture_reds_for_its_own_reason(fixture, needle):
    p = run(fixture)
    assert p.returncode == 1, f"expected exit 1, got {p.returncode}: {p.stdout}{p.stderr}"
    assert needle in p.stdout + p.stderr, p.stdout + p.stderr


def test_a_softened_disclaimer_is_not_good_enough():
    """The reassurance survives a paraphrase; the warning does not. So the match is byte-exact."""
    combined = run("softened-disclaimer.md").stdout + run("softened-disclaimer.md").stderr
    assert DISCLAIMER in combined, "the failure should quote the required sentence"


def test_the_document_and_the_checker_agree_on_the_disclaimer():
    """One sentence, two files. A checker enforcing a sentence the document does not carry is a
    rule nobody can look up."""
    assert DISCLAIMER in DOC.read_text(encoding="utf-8")
    assert DISCLAIMER in CHECK.read_text(encoding="utf-8")


def test_the_document_states_the_empty_set_rule():
    """An absent section and an empty one mean opposite things."""
    doc = " ".join(DOC.read_text(encoding="utf-8").split())
    assert 'When the set is empty, write "none" explicitly' in doc
    assert "Omitting the section is not allowed" in doc


def test_the_document_states_the_guidance_line_is_not_a_fifth_item():
    doc = " ".join(DOC.read_text(encoding="utf-8").split())
    assert "above** the four items and is not one of them" in doc


def test_the_document_states_the_three_parts_each_flag_carries():
    """Each flag carries three parts: file:line, the lines as they were, and one reason."""
    doc = " ".join(DOC.read_text(encoding="utf-8").split())
    assert "`file:line-range`" in doc
    assert "the lines as they were before" in doc
    assert "one sentence on why it is worth a look" in doc
