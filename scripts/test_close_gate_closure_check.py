"""Acceptance suite for check 11 (closure declaration) wired into the close gate.

Covers AC3 (three distinct verdicts) and AC5 (phase mode only).

**AC5 is asserted against a baseline that cannot be re-taken.**
The baseline file (`BASELINE` below) was captured with zero tracked changes, before check 11
was wired in. If that file is missing these tests SKIP rather than silently passing
against nothing.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
GATE = REPO / "scripts" / "close-gate.sh"
MANIFEST = REPO / ".claude" / "close-gate.json"
BASELINE = REPO / ".claude" / ".ac5-baseline.txt"


def gate(mode: str, phase: str = "p1") -> subprocess.CompletedProcess:
    return subprocess.run(
        ["/bin/bash", str(GATE), mode, phase],
        cwd=REPO,
        capture_output=True,
        text=True,
    )


def check_set(out: str, kind: str, mode: str) -> str:
    prefix = f"check-set ({mode}): {kind}"
    for line in out.splitlines():
        if line.startswith(prefix):
            return line
    return ""


# ------------------------------------------------------------------ AC5
def _numbered_checks(line: str) -> list[str]:
    """The numbered checks a `check-set` line names, e.g. ['1', '5', '7', '8', '9', '10'].

    Deliberately drops the parenthetical labels and anything inside them: `8(invariants:22)` and
    `8(invariants:23)` are the SAME CHECK running, and the number after the colon is how many
    invariants the manifest declares -- which is not what this criterion is about.
    """
    return re.findall(r"(?:^|\s)(\d+b?)\(", line)


@pytest.mark.skipif(not BASELINE.exists(), reason="baseline absent (fresh clone); it cannot be re-taken")
def test_ac5_nothing_new_runs_on_the_push_path() -> None:
    """Clause 1, the load-bearing half: no NEW numbered check appears on the push path.

    What a phase closes is only knowable when it is closing, so a check for it must never reach
    the pre-push path.

    NARROWED, and the reason is written HERE rather than left in a commit
    message, because silently loosening a guard is worse than the red it produced.

    **This assertion used to compare the whole `running` line byte-for-byte.** That mechanism is
    wider than the claim the docstring makes: the line embeds `8(invariants:N)`, so it also forbade
    N from ever changing -- and N changes whenever any phase adds or retires a declared invariant,
    which is routine. When N moved, this row went RED while
    the behaviour it names was completely intact.

    **A mechanism wider than its stated claim is a defect of its own.** The
    narrowing deliberately goes the other way from "update the number and move on": the check SET is
    still pinned exactly, check `11` is still asserted absent BY NAME, and the only thing now allowed
    to vary is a count that was never the subject.

    **What this can no longer catch, stated rather than hidden:** a phase adding a declared invariant
    that is itself expensive or unsafe on the push path. That gap was already outside AC5's
    wording -- `no-icloud-conflict-copies` walks the entire working copy on every push, and
    this row never had an opinion about it.
    """
    before_line = check_set(BASELINE.read_text(encoding="utf-8"), "running", "task")
    after_line = check_set(gate("task").stdout, "running", "task")
    assert before_line, "the baseline carries no task-mode running line"

    before, after = _numbered_checks(before_line), _numbered_checks(after_line)
    assert before, f"no numbered checks parsed out of the baseline line: {before_line!r}"
    assert after == before, (
        f"the set of checks running on the push path changed\n"
        f"baseline: {before}  ({before_line})\n"
        f"now:      {after}  ({after_line})"
    )
    assert "11" not in after, (
        "check 11 (closure-declaration) reached the push path -- what a phase closes is only "
        "knowable at close, and this is the criterion that forbids it"
    )


def test_ac5_the_narrowed_row_still_reds_when_a_new_check_appears() -> None:
    """The mutant for the row above, and the reason the narrowing is not just a loosening.

    A guard that stops firing on everything also passes every green test, so the narrowed
    comparison is exercised directly against three shapes: a count-only change must be ACCEPTED
    (that is the whole point), while a new check id and check 11 specifically must both be
    REJECTED. Run on strings rather than on the gate, because making the real gate emit check 11
    in task mode is the defect, not a fixture.
    """
    base = "check-set (task): running 1(product-tree) 5(journal) 7(test-evidence) 8(invariants:22) 9(rationale) 10(ac-oracle-binding)"
    count_changed = base.replace("invariants:22", "invariants:23")
    new_check = base + " 12(something-new)"
    closure_leaked = base.replace("10(ac-oracle-binding)", "10(ac-oracle-binding) 11(closure-declaration)")

    assert _numbered_checks(count_changed) == _numbered_checks(base), (
        "a change to the invariant COUNT must not read as a new check -- that is what was narrowed"
    )
    assert _numbered_checks(new_check) != _numbered_checks(base), (
        "a genuinely new numbered check slipped past the narrowed comparison"
    )
    assert "11" in _numbered_checks(closure_leaked), (
        "check 11 on the push path is undetectable by the narrowed comparison"
    )


@pytest.mark.skipif(not BASELINE.exists(), reason="baseline absent (fresh clone); it cannot be re-taken")
def test_ac5_skipped_line_gains_exactly_one_token() -> None:
    """Clause 2. Pinning WHAT changed rather than forbidding all change — the alternative was
    to hide the row from `cs()` in task mode, which would make the oracle pass by making the
    gate less honest about what it is not running."""

    def tokens(line: str) -> set:
        body = line.split(" skipped ", 1)[1].split(" — ", 1)[0]
        return set(body.split())

    before = tokens(check_set(BASELINE.read_text(encoding="utf-8"), "skipped", "task"))
    after = tokens(check_set(gate("task").stdout, "skipped", "task"))
    assert after - before == {"11(closure-declaration)"}, f"unexpected delta: {after - before}"
    assert before - after == set(), f"a check stopped being reported: {before - after}"


def test_ac5_check_11_is_present_in_phase_mode() -> None:
    """The other half of `phase mode only`: it has to actually run somewhere. A check that is
    off everywhere satisfies clause 1 trivially."""
    assert "11(closure-declaration)" in check_set(gate("phase").stdout, "running", "phase")


# ------------------------------------------------------------------ AC3
def test_ac3_unarmed_repo_is_not_failed() -> None:
    """Closed by construction: with no `closure_declaration` key the
    row does not run and does not fail. An adopter who never configured this feature is not
    red because of it."""
    armed = "closure_declaration" in json.loads(MANIFEST.read_text(encoding="utf-8"))
    if armed:
        pytest.skip("this repo is armed; the unarmed path is pinned by the source test below")
    assert "closure-declaration NOT ARMED" in gate("phase").stdout


def test_ac3_unarmed_branch_exists_in_the_source() -> None:
    """The armed repo cannot exercise the unarmed path, so the branch is pinned here. Without
    this, arming the repo would silently delete the coverage the test above provided — a skip
    that quietly becomes permanent is how a criterion stops being checked."""
    src = GATE.read_text(encoding="utf-8")
    assert "closure-declaration NOT ARMED" in src
    idx = src.index("closure-declaration NOT ARMED")
    assert "ok " in src[max(0, idx - 120):idx], "an unarmed repo must PASS, not fail"


def test_ac3_three_verdicts_are_distinct_strings() -> None:
    """The three verdicts must not share a message. Asserted on the SOURCE rather than by
    running three gates, because two of the three need a repo state this repo is not in — and
    a test that can only run in one state would report on one third of the criterion while
    reading like it covered all of it."""
    src = GATE.read_text(encoding="utf-8")
    absent = "Declare what this phase closed, or declare"
    disagree = "the declaration and $CD_LEDGER disagree"
    agree = "every id this phase declares closed has a ledger event"
    assert absent in src, "the absent-block verdict is missing"
    assert disagree in src, "the disagreement verdict is missing"
    assert agree in src, "the agreement verdict is missing"
    assert len({absent, disagree, agree}) == 3
    # And the absent case must be a FAILURE, not a pass: if it passed it would be
    # indistinguishable from `closes: none`, and the criterion asks for three outcomes.
    idx = src.index(absent)
    assert "bad " in src[max(0, idx - 200):idx], "the absent-block verdict must be raised by `bad`, not `ok`"


def test_no_phase_documents_is_a_failure_not_a_pass() -> None:
    """SURVIVED MUTANT. Flipping `bad` -> `ok` on the no-phase-documents branch
    left all three suites green: the branch needs an armed manifest AND zero matching docs,
    a state this repo cannot be driven into without unarming itself. Pinned in the source for
    the same reason `test_ac3_unarmed_branch_exists_in_the_source` is — a branch no fixture can
    reach still has to be pinned somewhere, or it is protected by nothing at all.

    Armed with no phase documents means the declaration has nowhere to live, which is a
    configuration error and not a phase that closed nothing. Passing it would hand a green to
    a repo whose globs are wrong."""
    src = GATE.read_text(encoding="utf-8")
    msg = "closure-declaration: no phase documents matched"
    assert msg in src, "the no-phase-documents branch is gone"
    idx = src.index(msg)
    assert "bad " in src[max(0, idx - 40):idx], "this branch must FAIL, not pass"
