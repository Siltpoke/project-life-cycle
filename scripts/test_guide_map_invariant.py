"""Controls for scripts/invariants/guide-map-covers-references.sh.

Every passing row here is paired with a mutation that turns it red. A fixture that
cannot fail is not a control -- and this guard exists precisely because the thing
it watches can drift for a long time while every check around it stays green.

A looser check is not enough, and the failure is specific: it can call complete a
map this guard reds. The looser check extracted every
``*.md`` token anywhere in the map block, so ``commands/reconcile.md`` made
``references/reconcile.md`` look listed, and two more names were matched inside prose
rather than on a tree leaf. Hence ``test_same_name_in_another_subtree_does_not_count``:
that exact confusion is now a control, not a memory.
"""

import subprocess
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GUARD = REPO / "scripts" / "invariants" / "guide-map-covers-references.sh"


def run(guide: Path, refdir: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["/bin/bash", str(GUARD), str(guide), str(refdir)],
        capture_output=True, text=True, cwd=REPO,
    )


def build(tmp_path: Path, listed: list[str], ondisk: list[str],
          commands: list[str] | None = None, map_header: str = "## Repository map") -> tuple[Path, Path]:
    """A minimal GUIDE + references/ tree.

    ``commands`` populates a SECOND subtree after references/, so a test can assert the
    parser stops at the subtree boundary instead of swallowing the whole map.
    """
    refdir = tmp_path / "references"
    refdir.mkdir(exist_ok=True)
    for name in ondisk:
        (refdir / name).write_text("# stub\n")

    lines = [map_header, "", "```", "skills/project-lifecycle/", "└── references/", "    │"]
    for name in listed:
        lines.append(f"    ├── {name}                     one-line note")
    if commands is not None:
        lines += ["", "commands/"]
        for name in commands:
            lines.append(f"├── {name}                     a command, not a reference")
    lines += ["```", ""]
    guide = tmp_path / "GUIDE.md"
    guide.write_text("\n".join(lines))
    return guide, refdir


def test_complete_map_passes(tmp_path):
    guide, refdir = build(tmp_path, ["a.md", "b.md"], ["a.md", "b.md"])
    r = run(guide, refdir)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "PASS" in r.stdout
    assert "2 reference(s)" in r.stdout


def test_missing_reference_fails(tmp_path):
    """The drift that actually happened: a file lands on disk, the map never learns."""
    guide, refdir = build(tmp_path, ["a.md"], ["a.md", "b.md"])
    r = run(guide, refdir)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "never names" in r.stdout
    assert "b.md" in r.stdout
    # The count is reported, not just the fact -- a guard that says "something is wrong"
    # without saying how much sends the reader back to doing the diff by hand.
    assert "1 reference(s) on disk" in r.stdout


def test_phantom_entry_fails(tmp_path):
    """What a rename leaves behind; reads to a user exactly like a broken link."""
    guide, refdir = build(tmp_path, ["a.md", "gone.md"], ["a.md"])
    r = run(guide, refdir)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "no file behind them" in r.stdout
    assert "gone.md" in r.stdout


def test_both_directions_reported_together(tmp_path):
    """Not first-failure-wins: fixing the missing one must not reveal the phantom later."""
    guide, refdir = build(tmp_path, ["a.md", "gone.md"], ["a.md", "b.md"])
    r = run(guide, refdir)
    assert r.returncode == 1
    assert "b.md" in r.stdout and "gone.md" in r.stdout
    assert "never names" in r.stdout and "no file behind them" in r.stdout


def test_same_name_in_another_subtree_does_not_count(tmp_path):
    """`commands/x.md` must not make `references/x.md` look listed.

    This is the exact false-green the looser check produced, and it is
    why the parser is bounded by the subtree rather than by the whole map block.
    """
    guide, refdir = build(tmp_path, ["a.md"], ["a.md", "dup.md"], commands=["dup.md"])
    r = run(guide, refdir)
    assert r.returncode == 1, "a same-named command entry must not satisfy the references check"
    assert "dup.md" in r.stdout


def test_unrecognised_layout_fails_rather_than_passing_vacuously(tmp_path):
    """Zero extracted names means the parser lost the map, not that the map is clean."""
    guide = tmp_path / "GUIDE.md"
    guide.write_text("## Repository map\n\nthe layout was rewritten and has no tree at all\n")
    refdir = tmp_path / "references"
    refdir.mkdir()
    (refdir / "a.md").write_text("# stub\n")
    r = run(guide, refdir)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "vacuous" in r.stdout


def test_absent_subjects_fail(tmp_path):
    r = run(tmp_path / "nope.md", tmp_path)
    assert r.returncode == 1
    assert "not found" in r.stdout


def test_empty_reference_dir_fails(tmp_path):
    guide, refdir = build(tmp_path, ["a.md"], [])
    r = run(guide, refdir)
    assert r.returncode == 1
    assert "ZERO .md files" in r.stdout


def test_guard_reads_its_argument_not_stdin(tmp_path):
    """git hands the pre-push hook a ref line on stdin; the guard must ignore it.

    A stdin-reading guard scanned that ref line, found no map, and passed -- measured
    once already in this directory (backlog-no-title-markers.sh's header records it).
    """
    guide, refdir = build(tmp_path, ["a.md"], ["a.md", "b.md"])
    r = subprocess.run(
        ["/bin/bash", str(GUARD), str(guide), str(refdir)],
        input="refs/heads/x sha refs/heads/x sha\n",
        capture_output=True, text=True, cwd=REPO,
    )
    assert r.returncode == 1, "a ref line on stdin must not turn the real subject green"
    assert "b.md" in r.stdout


def test_live_repo_is_clean():
    """The guard passes on the tree that ships."""
    r = subprocess.run(["/bin/bash", str(GUARD)], capture_output=True, text=True, cwd=REPO)
    assert r.returncode == 0, r.stdout + r.stderr
