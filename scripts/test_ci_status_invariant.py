"""The standing oracle for `ci-status-never-tracked.sh`.

Every case runs against a THROWAWAY git repo in `tmp_path`, never against this
one. A manual demonstration can use `git add -f` on the real index and undo it
with `git rm --cached`; that is fine once, at the keyboard, with the output
pasted — but as a permanent test it would mutate the working index on every run,
and a mutation matrix whose cleanup step can erase an
uncommitted fix and then report a clean sweep is what that looks like.
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO = Path(__file__).resolve().parent.parent
GUARD = REPO / "scripts" / "invariants" / "ci-status-never-tracked.sh"
ART = ".claude/ci-status.json"


def _git(root: Path, *args):
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True,
    )


def _repo(tmp_path: Path, ignore: bool = True) -> Path:
    root = tmp_path / "r"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    (root / ".gitignore").write_text(f"/{ART}\n" if ignore else "", encoding="utf-8")
    (root / ".claude").mkdir()
    _git(root, "add", ".gitignore")
    _git(root, "commit", "-qm", "init")
    return root


def _write_artifact(root: Path):
    (root / ART).write_text('{"schema":"plc.ci-status/1"}', encoding="utf-8")


def _run(root: Path):
    return subprocess.run(
        ["/bin/bash", str(GUARD), str(root)], capture_output=True, text=True,
    )


def test_absent_and_ignored_passes(tmp_path):
    r = _run(_repo(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "PASS ci-status-never-tracked" in r.stdout


def test_present_but_untracked_passes(tmp_path):
    """The normal state of an adopting repo. A guard that red-flagged the file's
    mere existence would make the feature unusable."""
    root = _repo(tmp_path)
    _write_artifact(root)
    r = _run(root)
    assert r.returncode == 0, r.stdout + r.stderr


def test_tracked_goes_red_and_blames_TRACKING_not_the_ignore_rule(tmp_path):
    """THE ordering assertion, and the reason this guard checks tracked FIRST.

    Git's ignore rules do not apply to tracked files, so with the ignore-test
    first a committed artifact produces a red whose stated reason is "the path is
    not ignored" and whose remedy is "edit .gitignore" — a TRUE FAILURE WITH A
    FALSE REASON, pointing the reader at a rule that is sitting right there and
    working. This asserts the message names tracking and `git rm --cached`, so
    reversing the order inside the script fails HERE rather than being noticed by
    whoever is unlucky enough to hit it."""
    root = _repo(tmp_path)
    _write_artifact(root)
    _git(root, "add", "-f", ART)
    r = _run(root)
    assert r.returncode == 1, r.stdout
    assert "is git-tracked" in r.stdout
    assert "git rm --cached" in r.stdout
    assert "TRACKING BEATS IGNORING" in r.stdout
    assert "Add `/" not in r.stdout          # never the .gitignore remedy


def test_git_agrees_that_a_tracked_path_reads_as_not_ignored(tmp_path):
    """The premise the ordering rests on, asserted against git itself rather than
    quoted from a comment. If a future git changed this behaviour, the ordering
    rationale would be stale and nothing else here would say so."""
    root = _repo(tmp_path)
    _write_artifact(root)
    assert _git(root, "check-ignore", "-q", "--", ART).returncode == 0   # ignored
    _git(root, "add", "-f", ART)
    assert _git(root, "check-ignore", "-q", "--", ART).returncode == 1   # "not ignored"


def test_untracked_but_not_ignored_goes_red_with_the_gitignore_remedy(tmp_path):
    root = _repo(tmp_path, ignore=False)
    _write_artifact(root)
    r = _run(root)
    assert r.returncode == 1, r.stdout
    assert "is NOT ignored" in r.stdout
    assert "TRACKING BEATS IGNORING" not in r.stdout


def test_a_trailing_slash_on_the_root_does_not_silently_pass(tmp_path):
    """An unstripped trailing slash produces a
    path comparison that matches nothing and a green meaning "I looked away".
    The root is a documented argument, so this is a spelling callers use."""
    root = _repo(tmp_path)
    _write_artifact(root)
    _git(root, "add", "-f", ART)
    r = subprocess.run(
        ["/bin/bash", str(GUARD), str(root) + "/"], capture_output=True, text=True,
    )
    assert r.returncode == 1, r.stdout
    assert "is git-tracked" in r.stdout


def test_not_a_work_tree_cannot_run_rather_than_passing(tmp_path):
    """A check that could not run must never report as though it did, and
    it must BLOCK — the gate reads exit status only, so 3 and 1 both stop the
    push, which is the fail-closed behaviour required."""
    plain = tmp_path / "plain"
    plain.mkdir()
    r = _run(plain)
    assert r.returncode == 3
    assert "COULD NOT RUN" in r.stdout
    assert "PASS" not in r.stdout


def test_the_guard_is_declared_in_the_close_gate_manifest():
    """A guard nothing runs is a guard that does not exist."""
    import json
    m = json.loads((REPO / ".claude" / "close-gate.json").read_text(encoding="utf-8"))
    row = next(i for i in m["invariants"] if i["name"] == "ci-status-never-tracked")
    assert "ci-status-never-tracked.sh" in row["command"]


def test_this_repo_ignores_the_artifact_path():
    """The rule itself, in THIS repo, read from git rather than from .gitignore's
    text — a pattern can be present and still be overridden by a later negation."""
    r = subprocess.run(
        ["git", "check-ignore", "-q", "--", ART], cwd=REPO, capture_output=True, text=True,
    )
    assert r.returncode == 0
