"""Resolve the installed pre-push hook the way git itself resolves it.

WHY THIS IS ITS OWN MODULE. Two test files needed this answer and carried two
implementations. They were not duplicates -- one was simply wrong. One asked git
(`--git-common-dir`); the other built
`REPO / ".git" / "hooks" / "pre-push"` literally, which resolves in an ordinary checkout and
NEVER in a linked worktree, because there `.git` is a pointer FILE. Measured in a
linked worktree: the rest passed and the tests that skipped were exactly the ones
reading the literal path -- on a machine where the hook was present the whole time. A skip that
looks exactly like the honest "no hook here" skip, on a machine that has one.

So this is a shared helper rather than a copied one on purpose. This repo has filed the
copied-guard-drifts shape repeatedly; two copies of a path resolver, one of them broken for the
layout the repo actually uses, is that shape with the drift already arrived.

WHAT IT RESOLVES, AND WHY EACH QUESTION IS THE RIGHT ONE.
`--git-common-dir` rather than `--git-dir`: hooks live in the COMMON directory and are shared by
every worktree, so a per-worktree git dir points at a `hooks/` that never contains anything.
`core.hooksPath` overrides the location entirely and is honoured here for the same reason -- the
caller must look at the hook git would actually run, not at a conventional location.

It returns a path that MAY NOT EXIST (a fresh clone, CI). That is the caller's business: an
absent hook is a real state and the caller must say so rather than treat it as a pass.

ONE WORD IS DELIBERATELY ABSENT FROM THIS FILE. The name of the decorator that suppresses a test
row is not written anywhere here, and must not be added. `scripts/invariants/skip-baseline-matches.sh`
greps `scripts/*.py` for that literal token and then scans forward for an enclosing `def`; the
token appearing in PROSE makes the invariant refuse to classify rather than guess a window, and
it refuses by failing the push. Measured, in the file this helper came from: it blocked
a push saying it could not find the enclosing def within 30 lines. The first repair re-spelled the
token while explaining why it must not be spelled -- the defect reproduced inside its own fix.
That is why this paragraph describes the word instead of using it.
"""

import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


class HookPathUnresolved(RuntimeError):
    """git could not be run, so the hook's location is unknown rather than conventional."""


def _git() -> str:
    """git's path, preferring the absolute one, then PATH.

    `/usr/bin/git` first because this repo requires it wherever a git result is EVIDENCE: a
    shell wrapper on PATH can rewrite git's output.
    PATH second because the absolute path is a fact about one machine, not about
    git -- a slim container or a Homebrew-only host has it elsewhere, and the old code treated
    that as a reason to fall back to a path it knew to be wrong.
    """
    if Path("/usr/bin/git").exists():
        return "/usr/bin/git"
    found = shutil.which("git")
    if found:
        return found
    raise HookPathUnresolved(
        "git is neither at /usr/bin/git nor on PATH, so the hook's location cannot be resolved. "
        "Install git, or run these rows somewhere git exists."
    )


def hook_path() -> Path:
    """The pre-push hook git would run from this repo, which may not exist.

    IT RAISES RATHER THAN GUESSING, and that is the point of the module.

    The first version fell back to `REPO / ".git" / "hooks" / "pre-push"` when git could not be
    run -- which is VERBATIM the implementation this module exists to delete, the one the docstring
    above calls wrong and "NEVER in a linked worktree". So the fallback reintroduced the defect at
    the one moment nobody would look, and in an ordinary checkout it would resolve by accident and
    pass. Found by an independent review: reverting `hook_path()` to that literal left
    the whole suite green, because CI is an ordinary checkout.

    An unresolvable location is a real state and it gets said out loud, exactly as an absent hook
    does. A helper that answers "probably here" is worse than one that answers "I cannot tell".
    """
    git = _git()
    common = subprocess.run(
        [git, "rev-parse", "--git-common-dir"],
        cwd=str(REPO), capture_output=True, text=True, check=True,
    ).stdout.strip()
    base = Path(common)
    if not base.is_absolute():
        base = REPO / base
    hooks_path = subprocess.run(
        [git, "config", "--get", "core.hooksPath"],
        cwd=str(REPO), capture_output=True, text=True,
    ).stdout.strip()
    if hooks_path:
        hp = Path(hooks_path)
        return (hp if hp.is_absolute() else REPO / hp) / "pre-push"
    return base / "hooks" / "pre-push"
