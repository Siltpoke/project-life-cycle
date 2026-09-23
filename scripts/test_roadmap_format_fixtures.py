"""the published golden fixtures are well-formed and say what
rule each of them exercises.

WHAT THIS IS AND IS NOT. This checks the FIXTURE SET, not a validator. The
the validators and the renderer each read these same
files. Until then a fixture set with no reader would be a directory of hopeful
text — this repo has filed that shape before, so the fixtures get a consumer on
the day they land rather than a promise of one.

WHY EACH INVALID CASE NAMES ITS RULE. A negative fixture that is rejected for the
wrong reason proves nothing about the rule it claims to cover, and reads as
coverage while providing none. So every `invalid/*/expected.json` carries a
`rule` field, and a downstream validator is expected to confirm the rejection
includes THAT rule, not merely that something was rejected.

WHY THE RULE NAMES ARE PINNED HERE. The list below is written down rather than
derived from the directory, so adding a fixture with a typo'd or invented rule
name fails instead of silently widening the vocabulary.
"""
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CONTRACT = REPO / "skills" / "project-lifecycle" / "references" / "roadmap-format.md"
FIXTURES = CONTRACT.parent / "roadmap-format" / "fixtures"

# The closed vocabulary of rule names an invalid fixture may claim.
RULES = {
    "steps-lower-bound",
    "steps-upper-bound",
    "steps-consecutive",
    "station-id-unique",
    "binds-to-resolves",
    "row-bound-at-most-once",
    "deps-acyclic",
    "deps-resolve",
    "closed-line-set",
    "active-names-known-station",
    "no-stored-position",
    "block-placement",
}


def _cases(kind):
    root = FIXTURES / kind
    return sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []


def test_fixture_root_exists():
    assert FIXTURES.is_dir(), "no fixtures directory — AC-10 has nothing to publish"


@pytest.mark.parametrize("kind, minimum", [("valid", 1), ("invalid", 8)])
def test_enough_cases(kind, minimum):
    """A scope assertion. An empty fixture directory would make every
    parametrised test below collect zero cases and the suite would report green
    over nothing — the empty-scope pass this repo keeps re-filing."""
    cases = _cases(kind)
    assert len(cases) >= minimum, "%s/ has %d cases, expected at least %d" % (
        kind, len(cases), minimum)


@pytest.mark.parametrize("case", _cases("valid") + _cases("invalid"), ids=lambda p: p.name)
def test_case_is_well_formed(case):
    inp = case / "input.md"
    exp = case / "expected.json"
    assert inp.is_file(), "%s has no input.md" % case.name
    assert exp.is_file(), "%s has no expected.json" % case.name
    assert inp.read_text().strip(), "%s/input.md is empty" % case.name
    meta = json.loads(exp.read_text())
    assert isinstance(meta.get("valid"), bool), "%s: 'valid' must be a boolean" % case.name


@pytest.mark.parametrize("case", _cases("invalid"), ids=lambda p: p.name)
def test_invalid_case_names_a_known_rule(case):
    meta = json.loads((case / "expected.json").read_text())
    assert meta["valid"] is False, "%s is under invalid/ but claims valid:true" % case.name
    rule = meta.get("rule")
    assert rule in RULES, (
        "%s claims rule %r, which is not in the contract's vocabulary. Either fix "
        "the name or add it to RULES here (deliberately manual — a derived list "
        "would absorb a typo silently)." % (case.name, rule))
    assert meta.get("why", "").strip(), (
        "%s gives no reason. A negative fixture without a stated reason cannot be "
        "told apart from one that fails by accident." % case.name)


@pytest.mark.parametrize("case", _cases("valid"), ids=lambda p: p.name)
def test_valid_case_claims_valid(case):
    meta = json.loads((case / "expected.json").read_text())
    assert meta["valid"] is True
    assert meta.get("note", "").strip(), "%s: say what this case is for" % case.name


def test_every_rule_has_at_least_one_fixture():
    """Coverage in the direction that actually goes wrong.

    The other tests check each fixture names a legal rule. This one checks the
    reverse — that no rule in the contract's vocabulary is left with nothing
    pointing at it. Counting fixtures would not have caught that; only mapping
    the two sets against each other does.
    """
    claimed = {json.loads((c / "expected.json").read_text())["rule"] for c in _cases("invalid")}
    missing = sorted(RULES - claimed)
    assert not missing, "rules with no fixture exercising them: %s" % missing


def test_contract_document_publishes_the_fixture_path():
    """The contract is published so third parties can self-check; a document that
    does not say where the fixtures are cannot be used that way."""
    text = CONTRACT.read_text()
    assert "roadmap-format/fixtures" in text
    assert "PULL" in text, (
        "the contract must state that fixtures are pulled, not that consumers are "
        "required to run our checks — the coupling this format refuses")
