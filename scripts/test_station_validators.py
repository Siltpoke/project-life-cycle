"""the station validators accept the valid fixtures and reject the invalid
ones, each for the rule it claims.

WHY "REJECTED" IS NOT ENOUGH. A negative fixture that is rejected for an unintended
reason reads as coverage while providing none — the shape this repo keeps re-filing.
So each invalid fixture declares a `rule` in its expected.json, RULE_OWNER maps that
rule to the validator responsible for it, and the test requires THAT validator to be
the one that goes red. A fixture rejected only by some other guard fails this test.

WHY THE VALID FIXTURES MATTER AS MUCH. Without them these guards are only proven able
to go red — never proven able to decide. `test_valid_fixture_is_accepted` is the
positive control, and a guard that fails it is useless no matter how many mutants it
kills.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "skills" / "project-lifecycle" / "references" / "roadmap-format" / "fixtures"
INV = REPO / "scripts" / "invariants"

ID_INTEGRITY = INV / "station-id-integrity.sh"
DEPS = INV / "station-deps-acyclic.sh"
NO_POS = INV / "no-stored-position.sh"
PLACEMENT = INV / "roadmap-station-blocks-placement.sh"

RULE_OWNER = {
    "steps-lower-bound": ID_INTEGRITY,
    "steps-upper-bound": ID_INTEGRITY,
    "steps-consecutive": ID_INTEGRITY,
    "station-id-unique": ID_INTEGRITY,
    "binds-to-resolves": ID_INTEGRITY,
    "row-bound-at-most-once": ID_INTEGRITY,
    "closed-line-set": ID_INTEGRITY,
    "active-names-known-station": ID_INTEGRITY,
    "deps-acyclic": DEPS,
    "deps-resolve": DEPS,
    "no-stored-position": NO_POS,
    "block-placement": PLACEMENT,
}

ALL_VALIDATORS = [ID_INTEGRITY, DEPS, NO_POS]

pytestmark = pytest.mark.skipif(shutil.which("jq") is None, reason="jq not installed")


def _cases(kind):
    root = FIXTURES / kind
    return sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []


def _run(validator, roadmap):
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
           "ROADMAP_PATH": str(roadmap)}
    return subprocess.run(["/bin/bash", str(validator)],
                          cwd=REPO, env=env, capture_output=True, text=True)


def _meta(case):
    return json.loads((case / "expected.json").read_text())


def test_scope_is_not_empty():
    """Without this, a missing fixture directory collects zero parametrised cases
    and the file reports green having checked nothing."""
    assert len(_cases("valid")) >= 1
    assert len(_cases("invalid")) >= 8


@pytest.mark.parametrize("case", _cases("valid"), ids=lambda p: p.name)
@pytest.mark.parametrize("validator", ALL_VALIDATORS, ids=lambda p: p.stem)
def test_valid_fixture_is_accepted(case, validator):
    """Positive control. A guard that cannot accept a correct file is not a guard."""
    proc = _run(validator, case / "input.md")
    assert proc.returncode == 0, (
        "%s rejected valid fixture %s:\n%s" % (validator.stem, case.name, proc.stderr))


@pytest.mark.parametrize("case", _cases("invalid"), ids=lambda p: p.name)
def test_invalid_fixture_is_rejected_by_its_owner(case):
    meta = _meta(case)
    rule = meta["rule"]
    owner = RULE_OWNER.get(rule)
    assert owner is not None, "no validator is mapped to rule %r" % rule
    if not owner.is_file():
        pytest.skip("%s not built yet" % owner.name)
    proc = _run(owner, case / "input.md")
    assert proc.returncode != 0, (
        "%s accepted %s, which must be rejected for rule %r.\nwhy: %s\nstdout:\n%s"
        % (owner.stem, case.name, rule, meta["why"], proc.stdout))


@pytest.mark.parametrize("case", _cases("invalid"), ids=lambda p: p.name)
def test_invalid_fixture_is_not_rejected_by_everything(case):
    """A fixture that every validator rejects is usually malformed rather than
    precise, and it would keep passing the test above even if its owner stopped
    working. Requires at least one validator OTHER than the owner to accept it —
    skipped for the cases where a second violation is inherent and documented.
    """
    meta = _meta(case)
    owner = RULE_OWNER[meta["rule"]]
    if "also trips" in meta.get("why", ""):
        pytest.skip("this fixture documents a second, inherent violation")
    others = [v for v in ALL_VALIDATORS + [PLACEMENT] if v != owner and v.is_file()]
    accepted = [v.stem for v in others if _run(v, case / "input.md").returncode == 0]
    assert accepted, (
        "%s is rejected by every validator, so it cannot show that %s specifically "
        "works" % (case.name, owner.stem))


# ---------------------------------------------------------------- header row
# Not fixture-driven: it is about a row the fixtures deliberately do not contain, and the
# behaviour it pins only became observable once the fixtures were translated out of Chinese.


def _roadmap_with_header(tmp_path, header_cell, binds_to):
    md = (
        "# Roadmap\n\n## \U0001f6e3 Mainline\n\n"
        f"| {header_cell} | what | weight | eta |\n|---|---|---|---|\n"
        "| **○ CI line** | a docs-only change should not wait 31 minutes | heavy | some |\n\n"
        "## \U0001f9ed Station plans\n\n<!-- plc-station-plan v1 -->\n\n"
        "### ci-line\n"
        f"- binds-to: {binds_to}\n"
        "- depends-on: none\n- steps:\n  - s1 measure the oracle\n\n"
        "## \U0001f6a6 In flight\n\n<!-- plc-station-active v1 -->\n- ci-line\n"
    )
    p = tmp_path / "ROADMAP.md"
    p.write_text(md, encoding="utf-8")
    return p


def test_the_header_row_is_not_a_station(tmp_path):
    """The header row must never be collectable as a mainline name.

    The rule used to be `the first cell equals <the CJK word this repo's own header uses>`,
    so it knew exactly one document. An adopter whose header cell reads `station` had that
    header row collected as a station name, and a block could then bind to it and resolve —
    a plan block bound to the table's own header, reported green. The rule is now positional:
    everything above the `|---|` separator is header.

    This case is the one that goes red if that changes back. It binds to the header text, so
    under the old rule it RESOLVES and the validator passes; under the current rule it is an
    orphan and the validator fails.
    """
    # `station`, NOT `**station**`. The binds-to text must be EXACTLY the header cell as the
    # parser trims it, or the block is an orphan for the wrong reason — text that does not
    # match — and the case goes red under the mutant too, proving nothing. Measured: with
    # `**station**` the mutant that disables the positional skip SURVIVED.
    rm = _roadmap_with_header(tmp_path, "station", "station")
    proc = _run(ID_INTEGRITY, rm)
    assert proc.returncode != 0, (
        "a plan block bound to the table's own header row was accepted:\n" + proc.stdout)
    assert "orphan" in proc.stdout + proc.stderr


def test_a_real_row_still_resolves_under_the_positional_rule(tmp_path):
    """The positive control for the same change. Narrowing what counts as a station must not
    stop a genuine row from resolving — a guard that rejects everything passes the test above
    while being useless."""
    rm = _roadmap_with_header(tmp_path, "station", "**○ CI line**")
    proc = _run(ID_INTEGRITY, rm)
    assert proc.returncode == 0, proc.stdout + proc.stderr
