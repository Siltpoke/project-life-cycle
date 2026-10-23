"""The gate reads `retention.hot_caps` and REFUSES when a hot document exceeds one.

**No CJK in this file, deliberately.** This project bans CJK in shipped files outside `README*` / `CHANGELOG.md`
/ `GUIDE*`, and `scripts/` ships.

WHY THESE ROWS EXIST, and the measurement that put them here rather than a judgement.
`retention.hot_caps` is documented in `references/retention.md` and
declared in `.claude/close-gate.json`. Measured at the start:

    /usr/bin/grep -c 'hot_caps' scripts/close-gate.sh   ->  0

Every one of those entries is inert in the variant this repo actually runs. The consequence is
not hypothetical: when the journal/qa-log drain stopped running, the hot documents grew far past
their caps and **every close-gate run printed green**. The drain script was fine; what was missing
is the only mechanism that could notice nobody ran it.

WHAT IS AND IS NOT THE ORACLE. `grep -c hot_caps > 0` is a PRECONDITION, not evidence -- it tests
that a string exists, which is the "tested the parser, not the guarantee" failure
this guards against. The oracle is the failure path: push a document over its cap and require the gate to
exit NON-ZERO. A check downgraded to warn-only never reds, so a `warn` row here would satisfy nothing.

WHY THE SUBJECT IS `docs/journal.d` AND NOT `CHANGELOG.md`. A fresh checkout's journal.d and qa-log.d are
**empty** while `CHANGELOG.md` is **already over its cap**.
A red produced with CHANGELOG as the subject would be indistinguishable from the
pre-existing state, so it would prove nothing about this change. CHANGELOG's over-cap state is
AC5's subject (a declared exemption with a written reason), not AC2's.

FOUR STATES, not one. "It fails" and "it fails on THIS" are different claims, and so are "no row
appears" and "the document is absent". Each row below is one state, asserted separately, so a red
can never be attributed to the fixture's shape.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from close_gate_lib import make_fixture_repo, run_gate

REPO_ROOT = Path(__file__).resolve().parents[1]
GATE = REPO_ROOT / "scripts" / "close-gate.sh"

pytestmark = pytest.mark.skipif(not GATE.is_file(), reason="scripts/close-gate.sh absent")

# A manifest with ONLY what these rows need. `hot_caps.journal_hot` is [lines, KB]; 0 means that
# dimension is unlimited, matching the canonical gate's grammar
# (`references/close-gate.md`, cap_val/cap_none).
MANIFEST: dict = {
    "product_paths": ["skills/", "commands/", "scripts/", ".claude-plugin/"],
    "retention": {
        "journal_dir": "docs/journal.d",
        # 8 KB, NOT 1 KB, and the reason is measured rather than stylistic: a directory cap is
        # `du -sk`, which reports ALLOCATED BLOCKS, not content bytes. On this filesystem a
        # directory holding one 100-byte file already reports 4 K, so a
        # 1 KB cap is breached by any non-empty directory and the under-cap row below could
        # never be satisfied. 8 KB leaves one 4 K block of headroom for the under-cap fixture
        # while a 40 KB fragment (44 K allocated) still breaches it decisively.
        "hot_caps": {"journal_hot": [0, 8]},
    },
    "invariants": [],
}

OVER_CAP = "x" * 40000     # ~44 K allocated against an 8 KB cap -- breaches on any block size
UNDER_CAP = "x" * 100      # one 4 K block against an 8 KB cap -- fits, with a block to spare


def _repo(tmp_path: Path, fragment: str | None, caps_override: dict | None = None) -> Path:
    # mkdir the parent: `make_fixture_repo` creates `<tmp_path>/repo` and does not create
    # `<tmp_path>` itself, so a per-state subdirectory (`tmp_path / "under"`) must exist first.
    # Measured, not guessed: the two paired rows below pass separate subdirectories and failed
    # with FileNotFoundError until this line existed.
    tmp_path.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(json.dumps(MANIFEST))
    if caps_override is not None:
        manifest["retention"]["hot_caps"] = caps_override
    files = {"CHANGELOG.md": "# Changelog\n\n## [Unreleased]\n"}
    if fragment is not None:
        files["docs/journal.d/2026-01-06-fragment.md"] = fragment
    return make_fixture_repo(tmp_path, manifest=manifest, files=files)


def _run(repo: Path):
    return run_gate(repo, GATE.read_text(encoding="utf-8"), "diff")


# --------------------------------------------------------------------- AC2, the failure path


def test_an_over_cap_hot_document_makes_the_gate_refuse(tmp_path: Path) -> None:
    """The oracle. Not 'a row is printed' -- a non-zero exit."""
    r = _run(_repo(tmp_path, OVER_CAP))
    assert r.returncode != 0, (
        "an over-cap hot document did not fail the gate; a cap nothing refuses is not a cap\n"
        f"{r.stdout}{r.stderr}"
    )
    out = r.stdout + r.stderr
    assert "journal" in out.lower(), "the failing row does not name the document"
    assert "cap" in out.lower(), "the failing row does not mention a cap"


def test_removing_the_fragment_clears_the_refusal(tmp_path: Path) -> None:
    """THE LOAD-BEARING HALF. Without it the row above is satisfied by a gate that always fails.

    Asserted as its own state rather than folded into the row above, because 'the gate refuses'
    and 'the gate refuses BECAUSE of this document' are different claims and only the second one
    is what AC2 means.
    """
    over = _run(_repo(tmp_path / "a", OVER_CAP))
    clean = _run(_repo(tmp_path / "b", None))
    assert over.returncode != 0, f"the over-cap state did not fail:\n{over.stdout}{over.stderr}"
    assert clean.returncode == 0 or "over hot cap" not in (clean.stdout + clean.stderr), (
        "with no hot fragment at all the gate still reported a cap row -- the refusal above "
        f"cannot be attributed to the document\n{clean.stdout}{clean.stderr}"
    )


# --------------------------------------------------------------------- AC3, no false positive


def test_an_under_cap_document_produces_no_row(tmp_path: Path) -> None:
    """Distinct from 'absent'. A present-but-small document is the state an adopter is in most of
    the time, and a cap that fires there is worse than no cap.

    PAIRED: the under-cap silence is only meaningful if the SAME gate emits a row when the
    document is over. Both halves run here; the second is what makes the first evidence.
    """
    quiet = _run(_repo(tmp_path / "under", UNDER_CAP))
    loud = _run(_repo(tmp_path / "over", OVER_CAP))

    assert "over hot cap" in (loud.stdout + loud.stderr), (
        "this gate build emits no cap row even for an over-cap document, so the under-cap "
        "silence below would be vacuous -- it is the gate doing nothing, not the gate being "
        f"correct\n{loud.stdout}{loud.stderr}"
    )
    out = quiet.stdout + quiet.stderr
    assert "over hot cap" not in out, f"false positive on an under-cap document\n{out}"


# --------------------------------------------------------------------- AC4, the exemption


def test_none_exempts_the_document_and_says_so(tmp_path: Path) -> None:
    """`hot_caps.<doc>: "none"` is the ONLY exemption mechanism, and it must PRINT that it
    exempted the document. A check a filter removed silently is indistinguishable from one that
    passed -- the rule this repo already applies to `experiment-gate: off`."""
    r = _run(_repo(tmp_path, OVER_CAP, caps_override={"journal_hot": "none"}))
    out = r.stdout + r.stderr
    assert "exempt" in out.lower(), f"an exempted document was skipped silently\n{out}"
    assert "over hot cap" not in out, f"an exempted document still produced a cap row\n{out}"


# --------------------------------------------------------------------- the precondition, stated


def test_the_string_check_is_a_precondition_not_the_oracle() -> None:
    """The precondition, kept as a row so the distinction stays executable.

    Originally `hot_caps` appeared ZERO times in the gate; then the rows landed and this
    assertion FLIPPED, together with the four xfail markers, in one commit. It is deliberately
    still NOT the oracle: a string count cannot tell a cap that refuses from a cap that prints.
    The rows above are the oracle, and this one exists so that "the port was reverted" fails
    HERE with a sentence, instead of showing up as four confusing xfails elsewhere.
    """
    n = GATE.read_text(encoding="utf-8").count("hot_caps")
    assert n > 0, (
        "scripts/close-gate.sh no longer mentions hot_caps at all -- the hot_caps port has been "
        "reverted or lost in a merge. This is the precondition, not the guarantee; the rows "
        "above are what prove the cap refuses."
    )


# ------------------------------------------------- AC6/AC7, the written record, made executable


RETENTION_MD = REPO_ROOT / "skills" / "project-lifecycle" / "references" / "retention.md"

pytestmark_retention = pytest.mark.skipif(
    not RETENTION_MD.is_file(), reason="references/retention.md absent"
)


@pytestmark_retention
def test_policy_keys_states_which_variant_reads_hot_caps_and_at_what_severity() -> None:
    """AC6. One acceptable resolution is to mark every key with the gate variant that reads it; there are
    two, and this phase does BOTH halves -- so the written half needs a guard too,
    or it is prose that can rot while the code stays right.

    Asserted as CONTENT, not as a heading: a section that exists with the answer missing is the
    failure mode, not a section that is missing. Three things must be findable -- that the two
    variants are named, that one warns and one fails, and that the difference has a stated reason.
    """
    body = RETENTION_MD.read_text(encoding="utf-8")

    assert "Which gate variant reads each key" in body, (
        "references/retention.md has no per-key variant/severity section. Marking every key "
        "with the variant that reads it is required -- without this, a reader finds out "
        "by measurement, which is the state the phase closes"
    )
    assert "warn-only" in body and "FAILS the gate" in body, (
        "the section does not say that the two variants differ in SEVERITY. Naming which variant "
        "reads a key while leaving its behaviour unstated answers half the question"
    )
    assert "Why the severities differ" in body, (
        "the severity difference is stated but not justified. An undocumented divergence and a "
        "documented one are different objects; only the second is acceptable"
    )


@pytestmark_retention
def test_the_unread_state_file_is_recorded_as_a_decision_not_left_as_a_gap() -> None:
    """AC7, and its verdict is the measured one rather than the convenient one.

    `.claude/retention-state.json` is tracked and `grep -rl retention-state scripts` returns
    NOTHING -- nothing reads it. AC7 allowed either outcome: give it a
    reader, or record it as deliberately unread with the reason. The reason that settled it is
    structural: canonical writes that file to escalate the wording when the SAME document is
    still over cap at the NEXT close, and where the rows FAIL there is no next close -- the first
    one blocks the push. Porting the escalation would have produced a file written by a path
    nothing can traverse.

    This row asserts BOTH halves, because either alone is satisfiable by accident: the state file
    still has no reader in `scripts/` (so the record is not stale), AND the record exists and
    gives the structural reason (so the absence is a decision).
    """
    # THE SCAN EXCLUDES TEST FILES AND BYTECODE, and that is forced rather than convenient: THIS
    # FILE lives under scripts/ and necessarily spells `retention-state` while asserting that
    # nothing reads it. An unscoped scan therefore counts this row as a reader and the assertion
    # inverts -- measured on the first run, before the exclusion existed. It is the same shape
    # this repo already records about a sibling test's marker and about
    # gate-jq-only-envelope.sh exempting itself: a checker that scans for a token cannot have a
    # sibling that spells it.
    #
    # WHY THIS IS NOT A LOOPHOLE: "reader" means production code that consults the file at gate
    # time. A test that documents the absence is not a consumer of the state, and if a test ever
    # DID consume it, that test would be the reader and the record would need updating -- which
    # is what the `if readers:` branch below is for. The exclusion is by path shape (`test_` /
    # `__pycache__`), so a new non-test script under scripts/ is still caught.
    readers = [
        q
        for q in (REPO_ROOT / "scripts").rglob("*")
        if q.is_file()
        and not q.name.startswith("test_")
        and "__pycache__" not in q.parts
        and "retention-state" in q.read_text(encoding="utf-8", errors="ignore")
    ]
    body = RETENTION_MD.read_text(encoding="utf-8")

    if readers:
        # The other acceptable outcome. Not a failure -- but the written record must then stop
        # claiming there is no reader, so this says exactly that instead of passing quietly.
        assert "no reader" not in body, (
            "something under scripts/ now reads retention-state, so the claim in retention.md "
            f"that it has no reader is stale: {[str(q.relative_to(REPO_ROOT)) for q in readers]}"
        )
        return

    assert "retention-state.json` has no reader" in body, (
        "the state file has no reader in scripts/ and nothing says so. An unread tracked file "
        "with no record is indistinguishable from an inert config"
    )
    assert "there is no second consecutive close" in body, (
        "the record says the file is unread but not WHY the escalation was not ported. 'We did "
        "not do it' and 'it cannot be reached where the rows fail' are different claims, and "
        "only the second one justifies leaving a tracked file unread"
    )
