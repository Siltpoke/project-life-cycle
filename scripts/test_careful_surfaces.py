"""The surfaces that talk about careful-paths, and the claims they are allowed to make.

Every assertion here is about SHIPPED text. Nothing mutates the real working tree.
"""
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SKILL = REPO / "skills/project-lifecycle"
DATA = SKILL / "references/careful-paths.md"
MODE = SKILL / "references/mode.md"
SKILL_MD = SKILL / "SKILL.md"
OUTPUT_FORMAT = SKILL / "references/output-format.md"
GUIDE = REPO / "GUIDE.md"

SENTINEL = re.compile(r"<!-- plc-careful-data:begin -->\s*```json\n(.*?)\n```", re.S)

# The inference words the tick-box screen may not use. A reason has to be something the reader can
# check and overrule -- "this folder has files whose names contain password" -- never something they
# are asked to take on trust. THIS GUARD PROVES THE ABSENCE OF THESE WORDS AND NOTHING MORE: a
# reason phrased around them is still an inference and still passes. It is a floor, not a promise,
# and the file name says so.
INFERENCE_WORDS = [
    "sensitive", "risky", "dangerous", "looks like", "probably", "seems to",
    "appears to", "likely handles", "critical",
]


def block() -> dict:
    m = SENTINEL.search(DATA.read_text(encoding="utf-8"))
    assert m, "no fenced json block between the careful-data sentinels"
    return json.loads(m.group(1))


# --- the data block is the only copy ----------------------------------------------------------


def test_exactly_one_data_block_in_the_shipped_reference():
    text = DATA.read_text(encoding="utf-8")
    assert text.count("<!-- plc-careful-data:begin -->") == 1
    assert text.count("<!-- plc-careful-data:end -->") == 1
    inner = text.split("<!-- plc-careful-data:begin -->")[1].split(
        "<!-- plc-careful-data:end -->"
    )[0]
    assert inner.count("```json") == 1, "a reader that has to choose between two copies is the drift"


@pytest.mark.parametrize("other", [MODE, SKILL_MD, OUTPUT_FORMAT, GUIDE])
def test_no_other_surface_carries_a_second_copy_of_the_signal_lists(other):
    """Routing to the file is fine. Restating the lists is a second copy, and second copies drift.

    SCOPED TO THE LINES THAT TALK ABOUT THIS FEATURE, and that narrowing was measured rather than
    reasoned: the first version scanned whole files and reddened on GUIDE.md for `go.mod`,
    `migrations/` and `.github/workflows/` -- every one of them a pre-existing row of the
    repository map, none of them anything to do with this feature. A net that fires on the product
    it is stretched over is a broken net.
    """
    paths = [p for s in block()["signals"].values() for p in s["paths"]]
    lines = other.read_text(encoding="utf-8").splitlines()
    region = "\n".join(ln for ln in lines if "careful" in ln.lower())
    # Naming one entry in an example line (`careful-paths: src/auth/, db/`) is routing, not a copy.
    leaked = [p for p in paths if p in region]
    assert len(leaked) < 3, f"{other.name} restates the signal lists near its careful rows: {leaked}"


# --- the claims the shipped text is allowed to make --------------------------------------------


def test_the_dependency_signal_says_what_it_saw_not_what_it_means():
    """Path-level match cannot tell 'a dependency was added' from 'the scripts block was edited'.
    Telling those apart needs a parser per ecosystem, which is the frozen stack knowledge the design
    refuses. So the wording is narrowed instead of the mechanism widened."""
    says = block()["signals"]["dependency"]["says"]
    assert "add" not in says.lower(), says
    assert "touched" in says.lower(), says


def test_every_signal_has_a_says_string():
    for name, sig in block()["signals"].items():
        assert sig.get("says", "").strip(), f"{name} fires with nothing to say"


def test_the_four_misses_are_all_stated_in_the_shipped_reference():
    """The boundary has to be in user-visible text. The fourth statement -- that
    the decision is by path and never by what the change did -- is as much a miss as the
    other three."""
    text = DATA.read_text(encoding="utf-8").lower()
    for needle, why in [
        ("marked by you", "the user's own marking is incomplete"),
        ("do not name is a miss", "an uncovered ecosystem is a miss"),
        ("word list is english", "the vocabulary is English"),
        ("deleted", "danger in what a change removed is invisible"),
        ("moved", "danger in what a change relocated is invisible"),
    ]:
        assert needle in text, f"missing boundary statement: {why}"


def test_no_surface_claims_it_finds_every_risky_change():
    """The claim this feature is forbidden to make, checked on every surface that mentions it."""
    banned = ["all high-risk", "every risky change automatically", "detects all"]
    for f in (DATA, MODE, SKILL_MD, OUTPUT_FORMAT):
        low = f.read_text(encoding="utf-8").lower()
        for phrase in banned:
            # "does not claim to detect all" is the sentence we WANT; only an unqualified claim
            # is a breach, so require a negation nearby.
            idx = low.find(phrase)
            while idx != -1:
                window = low[max(0, idx - 60):idx]
                assert any(n in window for n in ("not ", "never ", "cannot", "no ")), (
                    f"{f.name} claims {phrase!r} without a negation in front of it"
                )
                idx = low.find(phrase, idx + 1)


def test_the_fixup_boundary_is_stated_as_a_gap_and_not_as_covered():
    """The first draft said a fixup was 'covered by the review coverage window'. That was
    a claim wider than its mechanism -- a final-pass review is not
    an upgrade of three stages to cadence: full."""
    text = DATA.read_text(encoding="utf-8").lower()
    assert "does not trigger a careful upgrade" in text
    assert "not the same thing" in text


def test_the_upgrade_is_scoped_to_cadence_on_every_surface():
    for f in (DATA, MODE, SKILL_MD, OUTPUT_FORMAT):
        low = f.read_text(encoding="utf-8").lower()
        if "careful" not in low:
            continue
        assert "cadence" in low, f"{f.name} mentions the feature without naming what it moves"


# --- the vocabulary --------------------------------------------------------------------------


def test_the_shipped_reason_wording_uses_no_inference_words():
    """The no-inference constraint, mechanised as far as a mechanism reaches."""
    text = DATA.read_text(encoding="utf-8").lower()
    reason_lines = [
        ln for ln in text.splitlines()
        if "names contain" in ln or "whose names" in ln
    ]
    assert reason_lines, "no reason template in the shipped reference to check"
    for ln in reason_lines:
        for w in INFERENCE_WORDS:
            assert w not in ln, f"a reason template uses the inference word {w!r}: {ln.strip()}"


def test_the_word_list_is_declared_unbounded_rather_than_left_to_be_noticed():
    """'No upper bound, and no mechanism for one' is an accepted risk. A risk whose
    treatment nothing implements is not a treatment, so the sentence has a home."""
    text = DATA.read_text(encoding="utf-8").lower()
    assert "no upper bound" in text
    assert "ships no mechanism" in text


def test_the_project_extension_key_is_named_in_the_block_not_only_in_prose():
    assert block().get("extra_words_key") == "careful-words"


# --- registry coverage -------------------------------------------------------------------------


@pytest.mark.parametrize("registry", [SKILL_MD, OUTPUT_FORMAT, GUIDE])
def test_every_registry_names_the_new_reference(registry):
    assert "careful-paths.md" in registry.read_text(encoding="utf-8"), (
        f"{registry.name} does not name the new reference, so nobody discovers it"
    )
