"""The stale-exemption check in roadmap-station-blocks-placement.sh is scoped
to declarations THIS branch added.

THE BUG. `.claude/roadmap-row-edits.txt` exempts a deliberately-edited mainline
row from the byte-identical comparison, and a declaration whose row did NOT change is
flagged "stale". That is correct WHILE the declaration is this branch's own. But once a
phase that flipped a row merges, the base catches up: on the next branch the merged row
now equals the base, and the surviving (inherited) declaration is flagged stale even
though this branch never touched it. The catch-22: a
phase cannot both keep the declaration (so the row-change passes the byte comparison) and
delete it (so it is not stale after merge), because deletion is only clean once the row
equals the base — which is after the merge, on a branch that cannot have made the edit.

THE FIX. The stale error fires only for a declaration THIS branch added — one present in
the working `.claude/roadmap-row-edits.txt` but NOT in the file at the phase base. An
inherited declaration (already at the base, having done its job in a prior merged phase)
is tolerated: skipping it is not a weakening, because it was never coverage for THIS
branch's diff.

THE HARNESS. The stale check only runs when a real phase base exists in git, so these
tests build a throwaway git repo per case and drive the guard with PHASE_BASE_SHA. The
fixture-driven p36 tests never exercise this path — their ROADMAP_PATH is an absolute
tmp file that does not exist at the base, so the whole table-bytes block SKIPs.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
GUARD = REPO / "scripts" / "invariants" / "roadmap-station-blocks-placement.sh"

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

# A two-row mainline table. The prefix `CI line` names row one on each side, is ASCII,
# and carries no status glyph (per the declaration file's own rules).
_ROADMAP_ROW_DONE = "| **done CI line** | a docs-only change should not wait | heavy | done |"
_ROADMAP_ROW_OPEN = "| **todo CI line** | a docs-only change should not wait | heavy | some |"
_OTHER_ROW = "| **todo Backlog item** | something unrelated | light | later |"


def _roadmap(ci_row):
    return (
        "# Roadmap\n\n"
        "## \U0001f6e3 Mainline\n\n"
        "| name | what | weight | eta |\n"
        "|---|---|---|---|\n"
        f"{ci_row}\n"
        f"{_OTHER_ROW}\n"
    )


_DECL_PLACEHOLDER = "# declarations go here, one per line\n"
_DECL_WITH_CI = _DECL_PLACEHOLDER + "-\tCI line\tflip ci-line to done\n"


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, text=True)


def _make_repo(tmp_path, base_roadmap, base_decl, work_roadmap, work_decl):
    """Commit (base_roadmap, base_decl) as the phase base, then lay (work_roadmap,
    work_decl) in the working tree. Returns (repo_path, base_sha)."""
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / ".claude").mkdir(parents=True)
    _git(repo.parent, "init", repo.name)
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    (repo / "docs" / "ROADMAP.md").write_text(base_roadmap, encoding="utf-8")
    (repo / ".claude" / "roadmap-row-edits.txt").write_text(base_decl, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "base")
    base_sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                              check=True, capture_output=True, text=True).stdout.strip()
    (repo / "docs" / "ROADMAP.md").write_text(work_roadmap, encoding="utf-8")
    (repo / ".claude" / "roadmap-row-edits.txt").write_text(work_decl, encoding="utf-8")
    return repo, base_sha


def _run(repo, base_sha):
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
           "PHASE_BASE_SHA": base_sha}
    return subprocess.run(["/bin/bash", str(GUARD)],
                          cwd=repo, env=env, capture_output=True, text=True)


def test_inherited_declaration_for_an_unchanged_row_is_not_stale(tmp_path):
    """RED→GREEN. The merged-phase case: the base already carries the flipped row AND
    its declaration, and this branch changed neither. The declaration is inherited, so it
    must not red — this is the false-red that reddened main."""
    base_roadmap = _roadmap(_ROADMAP_ROW_DONE)
    repo, base = _make_repo(
        tmp_path,
        base_roadmap=base_roadmap, base_decl=_DECL_WITH_CI,
        work_roadmap=base_roadmap, work_decl=_DECL_WITH_CI)
    proc = _run(repo, base)
    assert proc.returncode == 0, (
        "inherited declaration for an unchanged row was flagged, but it is not this "
        "branch's:\nstdout:\n%s\nstderr:\n%s" % (proc.stdout, proc.stderr))


def test_branch_added_declaration_for_an_unchanged_row_is_still_stale(tmp_path):
    """PRESERVE. The genuine error the check exists for: THIS branch added a declaration
    for a row it did not change. Must still red."""
    roadmap = _roadmap(_ROADMAP_ROW_DONE)
    repo, base = _make_repo(
        tmp_path,
        base_roadmap=roadmap, base_decl=_DECL_PLACEHOLDER,
        work_roadmap=roadmap, work_decl=_DECL_WITH_CI)
    proc = _run(repo, base)
    assert proc.returncode != 0, (
        "a branch-added declaration about an unchanged row must be flagged stale:\n"
        "stdout:\n%s\nstderr:\n%s" % (proc.stdout, proc.stderr))
    assert "stale" in proc.stderr, (
        "expected a stale-exemption failure, got:\n%s" % proc.stderr)


def test_inherited_declaration_does_not_exempt_a_later_edit_to_its_row(tmp_path):
    """RED→GREEN (2nd-agent review finding). An inherited declaration must NOT grant its row a standing
    exemption from the byte comparison. A later branch that edits the row WITHOUT its own
    declaration must red — otherwise the exemption outlives its phase and the row becomes
    silently editable forever (the forcing function the earlier stale red used to provide)."""
    base_roadmap = _roadmap(_ROADMAP_ROW_DONE)
    edited = _roadmap(
        _ROADMAP_ROW_DONE.replace("a docs-only change should not wait",
                                  "a docs-only change should not wait AT ALL"))
    repo, base = _make_repo(
        tmp_path,
        base_roadmap=base_roadmap, base_decl=_DECL_WITH_CI,
        work_roadmap=edited, work_decl=_DECL_WITH_CI)
    proc = _run(repo, base)
    assert proc.returncode != 0, (
        "an inherited declaration silently exempted a later edit to its row — the exemption "
        "must not outlive its phase:\nstdout:\n%s\nstderr:\n%s" % (proc.stdout, proc.stderr))


def test_branch_added_declaration_for_a_changed_row_passes(tmp_path):
    """PRESERVE. The normal within-phase flip: this branch changed the row AND declared
    it. Must pass — the fix must not reject a legitimate edit."""
    repo, base = _make_repo(
        tmp_path,
        base_roadmap=_roadmap(_ROADMAP_ROW_OPEN), base_decl=_DECL_PLACEHOLDER,
        work_roadmap=_roadmap(_ROADMAP_ROW_DONE), work_decl=_DECL_WITH_CI)
    proc = _run(repo, base)
    assert proc.returncode == 0, (
        "a declared row that genuinely changed on this branch must pass:\n"
        "stdout:\n%s\nstderr:\n%s" % (proc.stdout, proc.stderr))
