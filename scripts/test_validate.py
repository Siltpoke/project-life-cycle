"""Tests for scripts/validate.py's input surface.

Check 9 ("all .md are valid UTF-8") used to walk the filesystem with
``REPO.rglob("*.md")``. On this repo that reached orders of magnitude more files than are
tracked — the remainder being a co-located tool's cache directory,
the gitignored ``docs/`` tree, and other dot-directories. Two consequences:

1. The validator's verdict depended on unrelated local state it never intended
   to own.
2. ``close-gate.sh``'s test-evidence freshness row cannot be honest. Freshness is
   answerable from git (did a relevant path change since the recorded SHA?), and
   git can only ever see the tracked subset — so a validator with
   nearly all of its inputs invisible to git has no checkable freshness at all.

Narrowing the surface to tracked files is what makes the gate's freshness claim
exactly true rather than approximately true. These tests pin that surface.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from validate import md_files_to_check


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _git(r, "config", "user.email", "t@t.t")
    _git(r, "config", "user.name", "t")
    (r / "shipped.md").write_text("tracked\n", encoding="utf-8")
    (r / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "init")
    return r


def test_tracked_md_is_checked(repo: Path) -> None:
    files, how = md_files_to_check(repo)
    assert how == "tracked"
    assert Path("shipped.md") in {p.relative_to(repo) for p in files}


def test_gitignored_md_is_not_checked(repo: Path) -> None:
    """The live case: docs/ is kept out of version control here, and another
    tool's cache lands a large number of .md files in a co-located dot-directory. Neither is a deliverable."""
    (repo / "ignored").mkdir()
    (repo / "ignored/cache.md").write_text("someone else's file\n", encoding="utf-8")

    files, _ = md_files_to_check(repo)

    rel = {p.relative_to(repo) for p in files}
    assert Path("ignored/cache.md") not in rel
    assert Path("shipped.md") in rel


def test_untracked_but_not_ignored_md_is_not_checked(repo: Path) -> None:
    """A brand-new, never-added .md is not a deliverable either. It is also the
    case that would silently re-break the gate: git diff cannot see it, so if the
    validator read it the evidence could go stale invisibly."""
    (repo / "scratch.md").write_text("draft\n", encoding="utf-8")

    files, _ = md_files_to_check(repo)

    assert Path("scratch.md") not in {p.relative_to(repo) for p in files}


def test_non_git_tree_falls_back_to_a_walk_and_says_so(tmp_path: Path) -> None:
    """Running from a tarball must still validate something — but the mode is
    reported, never silently swapped. A silent fallback is the same defect class
    this check exists to remove."""
    plain = tmp_path / "plain"
    (plain / "sub").mkdir(parents=True)
    (plain / "a.md").write_text("x\n", encoding="utf-8")
    (plain / "sub/b.md").write_text("y\n", encoding="utf-8")

    files, how = md_files_to_check(plain)

    assert how == "walk"
    assert {p.relative_to(plain) for p in files} == {Path("a.md"), Path("sub/b.md")}


def test_dot_git_is_never_walked(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    (plain / ".git").mkdir(parents=True)
    (plain / ".git/hook.md").write_text("internal\n", encoding="utf-8")
    (plain / "real.md").write_text("x\n", encoding="utf-8")

    files, how = md_files_to_check(plain)

    assert how == "walk"
    assert {p.relative_to(plain) for p in files} == {Path("real.md")}


def test_tracked_but_deleted_md_does_not_crash(repo: Path) -> None:
    """Regression (independent review, MEDIUM): `git ls-files` lists a tracked file
    even after it's deleted in the working tree but not staged. The UTF-8 check must
    not raise FileNotFoundError on it — mid-refactor `rm` of a tracked .md would
    otherwise crash the validator (and dump a traceback into the evidence file)."""
    (repo / "gone.md").write_text("bye\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add gone.md")
    (repo / "gone.md").unlink()  # deleted in the working tree, NOT staged

    files, how = md_files_to_check(repo)

    assert how == "tracked"
    # the surface must not include a path that isn't on disk
    assert all(p.exists() for p in files), [str(p) for p in files if not p.exists()]
    assert Path("gone.md") not in {p.relative_to(repo) for p in files}
    assert Path("shipped.md") in {p.relative_to(repo) for p in files}
