"""AC suite for the no-welded-bold-bullets invariant
(scripts/invariants/no-welded-bold-bullets.sh).

The guard exists because the SKILL.md diet twice welded a `- **` Red Flag onto a neighbour by
dropping a newline, and the measurement harness could not see it (the welded behaviours are not in
its golden set). Each case asserts the EXIT CODE and, on the red path, that the offending line is
NAMED -- so a vacuous always-green invariant is caught.

**No CJK here** (leak gate). Pure subprocess over a fixture path (the script takes an optional path
arg for exactly this).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
INV = REPO / "scripts" / "invariants" / "no-welded-bold-bullets.sh"


def run(target: str | None) -> subprocess.CompletedProcess:
    cmd = ["/bin/bash", str(INV)]
    if target is not None:
        cmd.append(target)
    return subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True, env=dict(os.environ))


def write(tmp_path: Path, body: str) -> str:
    p = tmp_path / "SKILL.md"
    p.write_text(body)
    return str(p)


def test_clean_file_passes(tmp_path):
    """A file whose bold bullets all start at column 0 is clean -> exit 0."""
    target = write(tmp_path, "intro line\n- **First bullet** text\n- **Second bullet** text\n")
    r = run(target)
    assert r.returncode == 0, r.stderr + r.stdout
    assert "PASS" in r.stdout


def test_welded_bold_bullet_fails_and_is_named(tmp_path):
    """A `- **` glued onto the end of the previous line -> exit 1, offending line reported."""
    target = write(tmp_path, "prev sentence.- **Welded bullet** text\nclean line\n")
    r = run(target)
    assert r.returncode == 1, r.stderr + r.stdout
    assert "FAIL" in r.stdout
    assert "Welded bullet" in r.stdout  # the real line is quoted, not just a count


def test_standalone_bullet_not_flagged(tmp_path):
    """A legitimate column-0 bold bullet next to the welded one is NOT a false positive."""
    target = write(tmp_path, "x.- **Bad** a\n- **Good standalone** b\n")
    r = run(target)
    assert r.returncode == 1
    assert "Bad" in r.stdout
    assert "Good standalone" not in r.stdout


def test_checkbox_examples_are_not_false_positives(tmp_path):
    """The real SKILL.md carries `- [ ]` / `- [/]` / `- [none]` examples; the bold-only pattern
    must leave them alone (the reason the broad pattern was rejected)."""
    target = write(
        tmp_path,
        "write `- [ ]` per step\nthe `- [/]` in-progress marker\n`- [none]` is valid\n",
    )
    r = run(target)
    assert r.returncode == 0, r.stderr + r.stdout


def test_missing_file_is_cannot_run_not_pass(tmp_path):
    """A missing target is CANNOT-RUN (exit 3), never a silent pass."""
    r = run(str(tmp_path / "does-not-exist.md"))
    assert r.returncode == 3
    assert "CANNOT-RUN" in r.stdout


def test_real_skill_file_is_clean():
    """The shipped SKILL.md must be weld-free (regression lock on the two fixed incidents)."""
    r = run(None)  # no arg -> the real skills/project-lifecycle/SKILL.md
    assert r.returncode == 0, r.stdout
