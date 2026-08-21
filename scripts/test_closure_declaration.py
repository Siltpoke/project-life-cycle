"""Tests for scripts/closure-declaration.sh — the closure-declaration extractor.

Every test here is a numbered case over the `plc-closes` declaration format and its
validation rules.

**Case 8 (`plc-closes-example` beside a real block) guards the fence-nesting trap.**
`awk` has no concept of fence-nesting depth, so an illustrative block wrapped in a wider
four-backtick fence is still a line in the file.

**One instrument note, recorded because it once produced a false green.** `close` is
an awk BUILT-IN function name and cannot be used as a variable. Renaming the shell locals
without renaming the matching `-v` flags left the line-range unset, so the parser skipped
every line, printed ZERO records, and exited 0 — which is byte-identical to the legitimate
"this file has no block" outcome.
`test_case1_wellformed_two_entries` asserts a POSITIVE record count for exactly that
reason: a suite that only checked exit codes would have stayed green.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "closure-declaration.sh"
FENCE = "`" * 3


def run(*files: Path | str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["/bin/bash", str(SCRIPT), "extract", *[str(f) for f in files]],
        capture_output=True,
        text=True,
        cwd=REPO,
    )


def doc(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


def block(*lines: str) -> str:
    return "\n".join([f"{FENCE}plc-closes", *lines, FENCE, ""])


def records(proc: subprocess.CompletedProcess) -> list[list[str]]:
    return [ln.split("\t") for ln in proc.stdout.splitlines() if ln.strip()]


# --------------------------------------------------------------------------- case 1
def test_case1_wellformed_two_entries(tmp_path: Path) -> None:
    """Both records come back, and the reason survives verbatim including the em dash."""
    f = doc(
        tmp_path,
        "spec.md",
        "# a doc\n\n"
        + block("closed: B1030", "left-open: B1020 — the fix is outside this fence"),
    )
    p = run(f)
    assert p.returncode == 0, p.stderr
    recs = records(p)
    # Positive count, not just a clean exit: zero records with exit 0 is a legitimate
    # outcome for a different input, so an exit-code-only assertion proves nothing here.
    assert len(recs) == 2, p.stdout
    assert recs[0] == ["closed", "B1030", "-"]
    assert recs[1][0] == "left-open"
    assert recs[1][1] == "B1020"
    assert recs[1][2] == "the fix is outside this fence"


def test_case1b_double_hyphen_separator_also_works(tmp_path: Path) -> None:
    """A keyboard-typed `--` is accepted, not punished. Rejecting the reason for its
    punctuation would teach authors to omit the reason."""
    f = doc(tmp_path, "spec.md", block("left-open: B1021 -- not in scope this time"))
    p = run(f)
    assert p.returncode == 0, p.stderr
    assert records(p) == [["left-open", "B1021", "not in scope this time"]]


# --------------------------------------------------------------------------- case 2
def test_case2_closes_none_alone(tmp_path: Path) -> None:
    f = doc(tmp_path, "spec.md", block("closes: none"))
    p = run(f)
    assert p.returncode == 0, p.stderr
    assert records(p) == [["none", "-", "-"]]


# --------------------------------------------------------------------------- case 3
def test_case3_no_block_is_not_this_scripts_error(tmp_path: Path) -> None:
    """Absent is silent here. The verdict for a missing declaration belongs to the gate,
    not to the extractor."""
    f = doc(tmp_path, "spec.md", "# a doc with prose only\n\nnothing to declare here.\n")
    p = run(f)
    assert p.returncode == 0, p.stderr
    assert p.stdout.strip() == ""


# --------------------------------------------------------------------------- case 4
def test_case4_unparseable_line_names_itself(tmp_path: Path) -> None:
    """A named failure, never a silent zero — the shape ac-evidence.sh already closed."""
    f = doc(tmp_path, "spec.md", "x\n" + block("closed: B1030", "wat is this line"))
    p = run(f)
    assert p.returncode != 0
    assert "wat is this line" in p.stderr
    assert "spec.md:4" in p.stderr, p.stderr


# --------------------------------------------------------------------------- case 5
def test_case5_two_blocks_in_one_file(tmp_path: Path) -> None:
    f = doc(tmp_path, "spec.md", block("closed: B1001") + "\nprose\n\n" + block("closed: B1002"))
    p = run(f)
    assert p.returncode != 0
    assert "exactly one" in p.stderr
    # Every location is named so the author does not have to hunt for the second one.
    assert p.stderr.count("spec.md:") == 2, p.stderr


# --------------------------------------------------------------------------- case 6
def test_case6_blocks_in_two_files(tmp_path: Path) -> None:
    a = doc(tmp_path, "spec.md", block("closed: B1001"))
    b = doc(tmp_path, "plan.md", block("closed: B1002"))
    p = run(a, b)
    assert p.returncode != 0
    assert "spec.md:" in p.stderr and "plan.md:" in p.stderr, p.stderr


# --------------------------------------------------------------------------- case 7
def test_case7_example_block_alone_is_ignored(tmp_path: Path) -> None:
    body = "\n".join(["````markdown", f"{FENCE}plc-closes-example", "closed: B1099", FENCE, "````", ""])
    f = doc(tmp_path, "spec.md", body)
    p = run(f)
    assert p.returncode == 0, p.stderr
    assert p.stdout.strip() == "", "an -example block must not be read as a declaration"


# --------------------------------------------------------------------------- case 8
def test_case8_example_beside_real_block_is_not_a_conflict(tmp_path: Path) -> None:
    """The regression guard for the fence-nesting trap. One real block plus any
    number of documentation examples is EXACTLY ONE block, not a rule-3 violation."""
    body = (
        "\n".join(["````markdown", f"{FENCE}plc-closes-example", "closed: B1099", FENCE, "````", "", ""])
        + block("closed: B1030")
    )
    f = doc(tmp_path, "spec.md", body)
    p = run(f)
    assert p.returncode == 0, p.stderr
    assert records(p) == [["closed", "B1030", "-"]]


# --------------------------------------------------------------------------- case 9
def test_case9_same_id_both_kinds_is_a_contradiction(tmp_path: Path) -> None:
    f = doc(tmp_path, "spec.md", block("closed: B1030", "left-open: B1030 — no"))
    p = run(f)
    assert p.returncode != 0
    assert "B1030" in p.stderr and "already declared" in p.stderr, p.stderr


# --------------------------------------------------------------------------- case 10
def test_case10_left_open_without_reason(tmp_path: Path) -> None:
    """A deliberate non-closure with no stated reason is indistinguishable from having
    forgotten, which is the defect the declaration exists to prevent."""
    f = doc(tmp_path, "spec.md", block("left-open: B1020"))
    p = run(f)
    assert p.returncode != 0
    assert "no reason" in p.stderr, p.stderr


def test_case10b_closed_without_reason_is_fine(tmp_path: Path) -> None:
    """The reason is required only where its absence would be ambiguous. `closed:` is not
    ambiguous, and demanding prose there would be ceremony."""
    f = doc(tmp_path, "spec.md", block("closed: B1030"))
    p = run(f)
    assert p.returncode == 0, p.stderr
    assert records(p) == [["closed", "B1030", "-"]]


# --------------------------------------------------------- refinements this script adds
def test_none_may_not_be_mixed_with_named_ids(tmp_path: Path) -> None:
    """A refinement this script adds to the declaration grammar.
    Taking the union would let a typo silently delete the `none` claim."""
    f = doc(tmp_path, "spec.md", block("closes: none", "closed: B1030"))
    p = run(f)
    assert p.returncode != 0
    assert "stand alone" in p.stderr, p.stderr


def test_unclosed_fence_is_named_not_swallowed(tmp_path: Path) -> None:
    """Running to end-of-file would absorb unrelated prose and then blame the wrong line
    for being malformed."""
    f = doc(tmp_path, "spec.md", f"{FENCE}plc-closes\nclosed: B1030\n\nprose that never closes\n")
    p = run(f)
    assert p.returncode != 0
    assert "never closed" in p.stderr, p.stderr


def test_unreadable_file_is_named(tmp_path: Path) -> None:
    p = run(tmp_path / "does-not-exist.md")
    assert p.returncode != 0
    assert "cannot read" in p.stderr, p.stderr


# ===========================================================================
# Every test below closes a mutant that SURVIVED a mutation matrix, or reproduces a
# known failure. A survived mutant is a map of what was never tested, and this
# block is that map turned into assertions.
# ===========================================================================


def test_tilde_wrapper_is_not_a_declaration(tmp_path: Path) -> None:
    """The reserved `-example` suffix addressed fence-nesting, but
    only for the four-backtick shape it happened to hit. Tildes are the more idiomatic
    CommonMark wrapper, and a REAL `plc-closes` block inside `~~~markdown` was being read
    as a genuine declaration."""
    body = "\n".join(["~~~markdown", f"{FENCE}plc-closes", "closed: B1099", FENCE, "~~~", ""])
    f = doc(tmp_path, "spec.md", body)
    p = run(f)
    assert p.returncode == 0, p.stderr
    assert p.stdout.strip() == "", "a block inside a tilde wrapper is documentation, not a declaration"


def test_long_backtick_wrapper_is_not_a_declaration(tmp_path: Path) -> None:
    """The other half of the same trap: a four-backtick wrapper around a REAL block."""
    body = "\n".join(["````markdown", f"{FENCE}plc-closes", "closed: B1099", FENCE, "````", ""])
    f = doc(tmp_path, "spec.md", body)
    p = run(f)
    assert p.returncode == 0, p.stderr
    assert p.stdout.strip() == ""


def test_directory_argument_is_named_not_silent(tmp_path: Path) -> None:
    """`[ -r ]` is true for a readable DIRECTORY, and BWK awk reads a
    directory as an empty stream rather than erroring — so this produced exit 0, no output
    and no message: exactly the silent zero this script's header forbids."""
    d = tmp_path / "adir"
    d.mkdir()
    p = run(d)
    assert p.returncode != 0
    assert "not a regular file" in p.stderr, p.stderr


def test_tab_inside_reason_is_rejected(tmp_path: Path) -> None:
    """The output contract is TAB-separated; a TAB in free text makes a
    downstream `cut -f3` see four fields where three were promised."""
    f = doc(tmp_path, "spec.md", block("left-open: B1020 — a reason with\ta tab"))
    p = run(f)
    assert p.returncode != 0
    assert "TAB" in p.stderr, p.stderr


def test_second_open_fence_before_close_is_named(tmp_path: Path) -> None:
    """SURVIVED MUTANT. Deleting the reopen detector in locate_blocks left all 18 green:
    the behaviour was correct and completely untested."""
    body = f"{FENCE}plc-closes\nclosed: B1001\n{FENCE}plc-closes\nclosed: B1002\n{FENCE}\n"
    f = doc(tmp_path, "spec.md", body)
    p = run(f)
    assert p.returncode != 0
    assert "never closed" in p.stderr, p.stderr


def test_id_may_carry_dot_underscore_and_hyphen(tmp_path: Path) -> None:
    """SURVIVED MUTANT. Narrowing the id class to [A-Za-z0-9]* left all 18 green — no test
    used any of the three extra characters the format's own grammar allows. The permissiveness
    is deliberate (an adopter's id dialect may differ), so it needs an assertion."""
    f = doc(tmp_path, "spec.md", block("closed: B1001.2_x-y"))
    p = run(f)
    assert p.returncode == 0, p.stderr
    assert records(p) == [["closed", "B1001.2_x-y", "-"]]


def test_closes_nonetheless_is_not_closes_none(tmp_path: Path) -> None:
    """SURVIVED MUTANT. Removing the trailing anchor on the `closes: none` regex left all 18
    green, so `closes: nonetheless` would have been silently accepted as a `none` record —
    a claim about the phase's whole scope, invented from a typo."""
    f = doc(tmp_path, "spec.md", block("closes: nonetheless"))
    p = run(f)
    assert p.returncode != 0
    assert "not a declaration entry" in p.stderr, p.stderr


def test_closing_fence_with_trailing_content_does_not_close(tmp_path: Path) -> None:
    """SURVIVED MUTANT. Loosening FENCE_CLOSE to `^```` left all 18 green."""
    body = f"{FENCE}plc-closes\nclosed: B1001\n{FENCE}notafence\n\nprose\n"
    f = doc(tmp_path, "spec.md", body)
    p = run(f)
    assert p.returncode != 0
    assert "never closed" in p.stderr, p.stderr


def test_no_block_path_is_reached_deliberately_not_by_accident(tmp_path: Path) -> None:
    """SURVIVED MUTANT. Breaking the `n -eq 0` early return still passed, because the
    fallback happened to yield the same empty output. Pin the DISTINCTION instead: a file
    with no block is silent, while a file with a malformed block is not — if the early
    return is broken so that a real block stops being parsed, this pair separates."""
    empty = doc(tmp_path, "empty.md", "# prose only\n")
    real = doc(tmp_path, "real.md", block("closed: B1003"))
    pe, pr = run(empty), run(real)
    assert pe.returncode == 0 and pe.stdout.strip() == ""
    assert pr.returncode == 0 and records(pr) == [["closed", "B1003", "-"]]
