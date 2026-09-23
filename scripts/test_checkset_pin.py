"""SKILL.md's check-set table lists exactly the ids close-gate.sh announces.

The invariant's red against this repo's real files is unrepeatable: it existed only while the
table said eight and the gate announced twelve. These rows are what outlives that measurement.

Every fixture is a throwaway pair under `tmp_path`. Nothing here reads the repo's own SKILL.md or
close-gate.sh — a suite whose verdict depends on two tracked documents goes red for reasons that
have nothing to do with the mechanism, and this invariant would then red on every legitimate check
addition, which is the opposite of what it is for. The one row that DOES read them is last, and
says why it is a different claim.

**The indentation row is the load-bearing one.** A column-0 `^cs ` anchor passes every other row
in this file, because every call in the real gate happens to be flush-left. It is the only row
separating "sees the calls that exist today" from "sees the call a conditional check adds".
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

INVARIANT = Path(
    os.environ.get(
        "PLC_CHECKSET_PIN_IMPL",
        Path(__file__).resolve().parent / "invariants/skill-checkset-matches-gate.sh",
    )
)

# A minimal gate: the function definition (which must NOT be counted) plus three calls.
GATE_BASE = """#!/usr/bin/env bash
cs() { if [ "$1" = 1 ]; then RAN="$RAN $2"; else SKIPPED="$SKIPPED $2"; fi; }
cs "$RUN_A" "1(product-tree)"
cs 1        "8(invariants:$N)"
cs "$RUN_B" "9b(divergence-records)"
"""

SKILL_BASE = """# Some skill

   | # | Check | Mode |
   |---|---|---|
   | 1 | the phase diff touched the product tree | task + phase |
   | 8 | declared repo-integrity invariants | every branch |
   | 9b | divergence records | phase + CI |

Prose after the table.

| unrelated | table |
|---|---|
| 99 | must not be read as a check id |
"""


def _run(gate: Path, skill: Path) -> subprocess.CompletedProcess[str]:
    """Subjects are ARGUMENTS. Selecting them through the environment would hide the fixture
    choice from the call site, a shape this repo has already rejected once."""
    return subprocess.run(
        ["/bin/bash", str(INVARIANT), str(gate), str(skill)],
        capture_output=True,
        text=True,
        check=False,
    )


def _pair(tmp_path: Path, gate_body: str = GATE_BASE, skill_body: str = SKILL_BASE):
    gate = tmp_path / "close-gate.sh"
    skill = tmp_path / "SKILL.md"
    gate.write_text(gate_body)
    skill.write_text(skill_body)
    return gate, skill


def test_matching_sets_pass(tmp_path: Path) -> None:
    """The control. It can go red: every mutation row below is this fixture plus one edit."""
    r = _run(*_pair(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "exactly the 3 ids" in r.stdout


def test_unrelated_table_is_not_read_as_check_ids(tmp_path: Path) -> None:
    """`99` sits in a second markdown table below the prose. An unbounded row scan pulls it in and
    then fails for a reason unrelated to the gate — so this row is what stops the check widening
    every time someone adds a table to SKILL.md."""
    r = _run(*_pair(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "99" not in r.stdout


def test_gate_call_the_table_omits_is_red(tmp_path: Path) -> None:
    """The actual defect: the gate enforces something the declaration never mentions."""
    gate, skill = _pair(tmp_path, gate_body=GATE_BASE + 'cs 1 "12(experiment-gate)"\n')
    r = _run(gate, skill)
    assert r.returncode == 1
    assert "the gate RUNS but the table omits: 12" in r.stdout


def test_indented_conditional_call_is_still_seen(tmp_path: Path) -> None:
    """THE row this invariant exists in its current form for.

    A `^cs ` anchor at column 0 passes every other test here. It fails only on this input — a
    policy state that skips its own `cs()` call has to wrap it in an `if`, which indents it, and a
    column-0 anchor would then be SILENTLY blind to the newest check rather than loudly broken.
    Predicted by a cross-check agent before any such call existed; kept as a row because the
    prediction is cheap to lose and expensive to re-derive.
    """
    conditional = GATE_BASE + 'if [ "$POLICY" != off ]; then\n  cs 1 "12(experiment-gate)"\nfi\n'
    gate, skill = _pair(tmp_path, gate_body=conditional)
    r = _run(gate, skill)
    assert r.returncode == 1, "an indented cs() call was not seen — the parse is anchored too tightly"
    assert "the gate RUNS but the table omits: 12" in r.stdout


def test_cs_shaped_text_that_is_not_a_call_is_not_counted(tmp_path: Path) -> None:
    """The anchor's SECOND job, which had no row until an independent reviewer removed the anchor
    and watched all ten of these stay green.

    `^[[:space:]]*` does two things. It tolerates indentation — `test_indented_conditional_call_is_
    still_seen` covers that. It also refuses `cs "<id>(...)"`-shaped text that is not a call: inside
    a comment, inside prose, or as the tail of a longer word. **Deleting the anchor leaves the
    indentation row green** (an indented call still matches an unanchored pattern), so that row
    alone does not defend the line its own file calls load-bearing.

    The decoy below is the shape that actually occurs: a comment recording what the code used to
    say. Counted, it invents a check id nobody wired and reds the invariant for a reason no edit
    to either real file could fix.
    """
    decoy = GATE_BASE + '# old code used to say: xcs 1 "13(decoy-check)"\n'
    gate, skill = _pair(tmp_path, gate_body=decoy)
    r = _run(gate, skill)
    assert r.returncode == 0, f"a cs-shaped comment was counted as a real call: {r.stdout}"
    assert "13" not in r.stdout
    assert "exactly the 3 ids" in r.stdout


def test_table_row_with_no_gate_call_is_red(tmp_path: Path) -> None:
    """The other direction, worse in one way: the declaration claims enforcement that is not
    happening, which is what a `verified 3 of 3` line does."""
    extra = SKILL_BASE.replace(
        "   | 9b | divergence records | phase + CI |",
        "   | 9b | divergence records | phase + CI |\n   | 12 | a check nobody wired | phase only |",
    )
    gate, skill = _pair(tmp_path, skill_body=extra)
    r = _run(gate, skill)
    assert r.returncode == 1
    assert "the table LISTS but the gate does not run: 12" in r.stdout


def test_function_definition_is_not_counted_as_a_call(tmp_path: Path) -> None:
    """`cs() {` has no space before its paren. Counted, it would put a phantom id on the left side
    and the invariant would be permanently red for a reason no edit could fix."""
    r = _run(*_pair(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "cs()" not in r.stdout


def test_empty_left_side_fails_rather_than_passing_vacuously(tmp_path: Path) -> None:
    """An empty scope reporting PASS is this repo's most-repeated green-that-means-nothing. If the
    `cs` call shape ever changes, this must say so loudly rather than compare two empty sets."""
    gate, skill = _pair(tmp_path, gate_body="#!/usr/bin/env bash\necho no calls here\n")
    r = _run(gate, skill)
    assert r.returncode == 1
    assert "parsed ZERO check ids" in r.stdout


def test_empty_right_side_fails_rather_than_passing_vacuously(tmp_path: Path) -> None:
    """Same the other way: a table whose header shape changed must not read as 'no rows declared,
    so nothing to disagree with'."""
    gate, skill = _pair(tmp_path, skill_body="# Some skill\n\nno table at all\n")
    r = _run(gate, skill)
    assert r.returncode == 1
    assert "parsed ZERO rows" in r.stdout


def test_unreadable_subject_is_named(tmp_path: Path) -> None:
    """A missing file must not be indistinguishable from a file with nothing in it."""
    gate, skill = _pair(tmp_path)
    r = _run(gate, tmp_path / "does-not-exist.md")
    assert r.returncode == 1
    assert "cannot read" in r.stdout


def test_the_real_repo_is_consistent() -> None:
    """The one row that reads tracked files, deliberately last.

    Every row above proves the mechanism on fixtures. This proves the mechanism currently HOLDS
    here — a different claim, and the only one that catches a real drift landing on main. It goes
    red when someone adds a check without its table row, which is the entire point; that red is a
    correct failure, not a flaky one.
    """
    repo = Path(__file__).resolve().parent.parent
    r = subprocess.run(
        ["/bin/bash", str(INVARIANT)],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stdout + r.stderr
