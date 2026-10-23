"""Direct rows for `scripts/hook_path.py`.

WHY THIS FILE EXISTS, and it is a measurement rather than a tidiness argument. Until an
independent review the module had **zero** rows of its own. Its consumer is
an assertion that runs in whatever layout the
suite happens to be invoked from. CI is an ordinary checkout, so **reverting `hook_path()` to the
broken two-line literal it was created to delete left the entire suite green** — the AC it closes
existed only when a human happened to run the suite inside a worktree.

That is the phase's own opening defect wearing different clothes: a check whose coverage depends
on the environment it is run in, and whose absence is indistinguishable from a pass. These rows
build the layouts instead of hoping to be run in one.

Every row builds its own throwaway repo. Nothing here touches this repository.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent
MODULE = SCRIPTS / "hook_path.py"


def _run(*args: str, cwd: Path) -> str:
    res = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if res.returncode != 0:
        raise AssertionError(f"{args} failed in {cwd}:\n{res.stdout}\n{res.stderr}")
    return res.stdout


def _load_for(repo: Path):
    """Import a fresh copy of the module whose REPO is `repo`.

    The module computes REPO from its own location at import time, so a copy is placed inside the
    target repo rather than monkeypatching the constant — the same mechanism the real callers use.
    """
    dest = repo / "scripts" / "hook_path.py"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(MODULE.read_text())
    name = f"hook_path_probe_{abs(hash(str(repo)))}"
    spec = importlib.util.spec_from_file_location(name, dest)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _repo(tmp_path: Path, name: str = "repo") -> Path:
    repo = tmp_path / name
    repo.mkdir(parents=True)
    _run("git", "init", "-q", ".", cwd=repo)
    _run("git", "config", "user.email", "p@p", cwd=repo)
    _run("git", "config", "user.name", "p", cwd=repo)
    (repo / "README.md").write_text("hi\n")
    _run("git", "add", "-A", cwd=repo)
    _run("git", "commit", "-qm", "base", cwd=repo)
    return repo


# --------------------------------------------------------------------------------------------
# 1. the ordinary case — where the broken literal also happens to be right
# --------------------------------------------------------------------------------------------

def test_an_ordinary_checkout_resolves_to_the_git_dir_hook(tmp_path):
    """The case the old literal got right by accident, asserted so the next row has a contrast."""
    repo = _repo(tmp_path)
    mod = _load_for(repo)
    assert mod.hook_path() == repo / ".git" / "hooks" / "pre-push"


# --------------------------------------------------------------------------------------------
# 2. the case the literal gets WRONG — and the whole reason the module exists
# --------------------------------------------------------------------------------------------

def test_a_linked_worktree_resolves_to_the_COMMON_dir_hook(tmp_path):
    """In a linked worktree `.git` is a FILE, so the literal path names something that is not
    a directory and the hook is never found. This is the row that fails if anyone reverts the
    resolver, and it fails in an ordinary CI checkout too, because it builds the worktree itself.
    """
    repo = _repo(tmp_path)
    wt = tmp_path / "linked"
    _run("git", "worktree", "add", "-q", str(wt), "-b", "side", cwd=repo)

    assert (wt / ".git").is_file(), "not a linked worktree; this row would prove nothing"

    mod = _load_for(wt)
    resolved = mod.hook_path()

    assert resolved == repo / ".git" / "hooks" / "pre-push", resolved
    # and the literal the module exists to delete points somewhere else entirely
    literal = wt / ".git" / "hooks" / "pre-push"
    assert resolved != literal
    assert not literal.exists()

    # the resolved path is the one git actually uses: put a hook there and git runs it
    hooks = repo / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    hook = hooks / "pre-push"
    hook.write_text("#!/bin/bash\necho RESOLVED-HOOK-RAN >&2\nexit 1\n")
    hook.chmod(0o755)
    remote = tmp_path / "remote.git"
    _run("git", "init", "-q", "--bare", str(remote), cwd=tmp_path)
    res = subprocess.run(["git", "push", str(remote), "HEAD:refs/heads/x"],
                         cwd=wt, capture_output=True, text=True)
    assert res.returncode != 0, res.stdout + res.stderr
    assert "RESOLVED-HOOK-RAN" in res.stderr, res.stderr


# --------------------------------------------------------------------------------------------
# 3. core.hooksPath overrides the location entirely
# --------------------------------------------------------------------------------------------

def test_core_hooks_path_absolute_is_honoured(tmp_path):
    repo = _repo(tmp_path)
    elsewhere = tmp_path / "myhooks"
    elsewhere.mkdir()
    _run("git", "config", "core.hooksPath", str(elsewhere), cwd=repo)
    mod = _load_for(repo)
    assert mod.hook_path() == elsewhere / "pre-push"


def test_core_hooks_path_relative_resolves_against_the_repo(tmp_path):
    """A relative setting is relative to the worktree, not to whatever cwd the caller had."""
    repo = _repo(tmp_path)
    (repo / "myhooks").mkdir()
    _run("git", "config", "core.hooksPath", "myhooks", cwd=repo)
    mod = _load_for(repo)
    assert mod.hook_path() == repo / "myhooks" / "pre-push"


# --------------------------------------------------------------------------------------------
# 4. a path that does not exist is a real answer, not an error
# --------------------------------------------------------------------------------------------

def test_a_missing_hook_is_returned_rather_than_hidden(tmp_path):
    """A fresh clone has no hook. The module's contract is to name where it WOULD be, and leave
    "it is not there" to the caller — because a resolver that refused here would make an absent
    hook indistinguishable from an unresolvable one.
    """
    repo = _repo(tmp_path)
    mod = _load_for(repo)
    resolved = mod.hook_path()
    assert not resolved.exists()
    assert resolved.name == "pre-push"


# --------------------------------------------------------------------------------------------
# 5. git missing: it says so instead of guessing
# --------------------------------------------------------------------------------------------

def test_without_git_it_raises_instead_of_returning_the_broken_literal(tmp_path, monkeypatch):
    """The regression that an independent review found, pinned.

    The first version fell back to `REPO/".git"/"hooks"/"pre-push"` — verbatim the implementation
    this module replaces — whenever git could not be run. In an ordinary checkout that resolves by
    accident and passes; in a worktree it names a path inside a gitfile. Either way the caller is
    told "here" when the honest answer is "I cannot tell".
    """
    repo = _repo(tmp_path)
    mod = _load_for(repo)

    monkeypatch.setattr(mod.Path, "exists", lambda self: False, raising=False)
    monkeypatch.setattr(mod.shutil, "which", lambda _name: None)

    with pytest.raises(mod.HookPathUnresolved) as got:
        mod.hook_path()
    msg = str(got.value)
    assert "PATH" in msg
    assert "cannot be resolved" in msg


def test_it_prefers_the_absolute_git_but_accepts_one_from_PATH(tmp_path, monkeypatch):
    """`/usr/bin/git` first is a repo rule about evidence, not a claim that git lives there.

    A shell wrapper on PATH can rewrite git's output, so
    anything load-bearing calls the absolute path. But the absolute path is a fact about THIS
    machine: a slim container or a Homebrew-only host has git elsewhere, and treating that as a
    reason to return a known-wrong path was the defect. PATH is the documented second choice.
    """
    repo = _repo(tmp_path)
    mod = _load_for(repo)

    real = mod.shutil.which("git")
    assert real, "no git on PATH; this row cannot measure anything"

    monkeypatch.setattr(mod.Path, "exists", lambda self: False, raising=False)
    monkeypatch.setattr(mod.shutil, "which", lambda _name: real)
    assert mod._git() == real

    monkeypatch.undo()
    if Path("/usr/bin/git").exists():
        assert mod._git() == "/usr/bin/git"


# --------------------------------------------------------------------------------------------
# 6. the token that must never appear in this directory's .py files
# --------------------------------------------------------------------------------------------

def test_the_resolver_never_spells_the_suppression_decorator(tmp_path):
    """`scripts/invariants/skip-baseline-matches.sh` greps `scripts/*.py` for that literal token
    and then scans forward for an enclosing `def`. The word in PROSE makes it refuse to classify
    and refuse the push — seen in the file this resolver came from, and the first
    repair re-spelled the token while explaining that it must not be spelled.

    This row holds the rule for the resolver and for itself.
    """
    banned = "skip" + "if"
    for f in (MODULE, Path(__file__)):
        assert banned not in f.read_text(), f"{f.name} spells the token the baseline invariant greps"
