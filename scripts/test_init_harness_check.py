"""`/init-harness` ends with a deterministic count, not the model's own account.

The measured failure: on Qoder, init skipped `scripts/close-gate.sh` and the pre-push hook and
still reported "Bootstrap complete". These tests build a fully bootstrapped fixture repo, prove
the check passes on it (the positive control), then take each of the nine items away one at a
time and require the check to go red AND to name that item. A check that only goes red without
naming what is missing would let the report still open with "complete".
"""
import os
import stat
import subprocess
from pathlib import Path

import pytest

from close_gate_lib import extract_gate_script

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "scripts" / "init-harness-check.sh"
GATE_MD = ROOT / "skills/project-lifecycle/references/close-gate.md"

HOOK = "#!/bin/sh\nbash scripts/close-gate.sh diff\n"


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _write(path: Path, text: str, mode=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if mode is not None:
        path.chmod(mode)


def _bootstrapped(repo: Path, hooks_path: bool = True) -> Path:
    _git(repo, "init", "-q")
    _write(repo / "CLAUDE.md", "# rules\n")
    _write(repo / "CONTEXT.md", "# terms\n")
    _write(repo / "docs/RESUME.md", "# resume\n")
    _write(repo / "docs/iteration-journal.md", "# journal\n")
    _write(repo / "CHANGELOG.md", "# Changelog\n\n## [Unreleased]\n")
    _write(repo / ".gitignore", "/.claude/tasklist.md\n")
    _write(repo / "scripts/close-gate.sh", extract_gate_script(GATE_MD), 0o755)
    _write(repo / ".claude/close-gate.json", '{"test_command": "pytest -q"}\n')
    if hooks_path:
        _write(repo / ".githooks/pre-push", HOOK, 0o755)
        _git(repo, "config", "core.hooksPath", ".githooks")
    else:
        _write(repo / ".git/hooks/pre-push", HOOK, 0o755)
    return repo


def _run(repo: Path):
    p = subprocess.run(["bash", str(CHECK)], cwd=repo, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


@pytest.mark.parametrize("hooks_path", [True, False], ids=["core.hooksPath", "default-hooks-dir"])
def test_positive_control_complete(tmp_path, hooks_path):
    rc, out = _run(_bootstrapped(tmp_path, hooks_path))
    assert rc == 0, out
    assert out.startswith("COMPLETE -- all 9 required items present"), out


def _rm(rel):
    def f(repo):
        target = repo / rel
        target.unlink()
    return f


def _set(rel, text):
    def f(repo):
        _write(repo / rel, text)
    return f


def _chmod_hook(repo):
    (repo / ".githooks/pre-push").chmod(0o644)


def _unwire_hooks_path(repo):
    _git(repo, "config", "--unset", "core.hooksPath")


# (case id, mutation, the words the report must contain to name the missing item)
CASES = [
    ("claude-md", _rm("CLAUDE.md"), "✗ CLAUDE.md"),
    ("context-md", _rm("CONTEXT.md"), "✗ CONTEXT.md"),
    ("resume", _rm("docs/RESUME.md"), "✗ docs/RESUME.md"),
    ("journal", _rm("docs/iteration-journal.md"), "✗ journal home"),
    ("changelog", _rm("CHANGELOG.md"), "✗ CHANGELOG.md"),
    ("changelog-no-unreleased", _set("CHANGELOG.md", "# Changelog\n"), "no '## [Unreleased]'"),
    ("gitignore", _set(".gitignore", "node_modules/\n"), "/.claude/tasklist.md"),
    ("gate-missing", _rm("scripts/close-gate.sh"), "✗ scripts/close-gate.sh"),
    ("gate-not-template", _set("scripts/close-gate.sh", "#!/usr/bin/env bash\nexit 0\n"),
     "is not the shipped template"),
    ("manifest-missing", _rm(".claude/close-gate.json"), "✗ .claude/close-gate.json"),
    ("manifest-bad-json", _set(".claude/close-gate.json", "{nope"), "not valid JSON"),
    ("manifest-no-test-command", _set(".claude/close-gate.json", "{}"), "no test_command"),
    ("hook-not-executable", _chmod_hook, "pre-push hook"),
    ("hook-not-calling-gate", _set(".githooks/pre-push", "#!/bin/sh\nexit 0\n"), "pre-push hook"),
    ("hooks-path-unset", _unwire_hooks_path, "pre-push hook"),
]


@pytest.mark.parametrize("case_id,mutate,named", CASES, ids=[c[0] for c in CASES])
def test_each_missing_item_is_named(tmp_path, case_id, mutate, named):
    repo = _bootstrapped(tmp_path)
    mutate(repo)
    rc, out = _run(repo)
    assert rc == 1, out
    # The report must OPEN with the shortfall: a model copying the first line can no longer say
    # "complete" when something is missing.
    assert out.startswith("INCOMPLETE -- 1 of 9 required items missing"), out
    missing_block = out.split("present:")[0]
    assert named in missing_block, out


def test_skill_repo_own_gate_is_not_accepted(tmp_path):
    """The measured case: the model copied the skill repo's OWN gate, whose default product tree
    is that repo's directories. It must be named, not counted as 'a gate is present'."""
    repo = _bootstrapped(tmp_path)
    _write(repo / "scripts/close-gate.sh", (ROOT / "scripts/close-gate.sh").read_text(encoding="utf-8"), 0o755)
    rc, out = _run(repo)
    assert rc == 1, out
    assert "is not the shipped template" in out, out


def test_cannot_run_outside_a_repo_is_exit_3(tmp_path):
    rc, out = _run(tmp_path)
    assert rc == 3, out
    assert "COULD NOT RUN" in out, out


def test_check_never_writes(tmp_path):
    repo = _bootstrapped(tmp_path)
    _git(repo, "add", "-A")
    before = subprocess.run(["git", "status", "--porcelain", "--ignored"], cwd=repo,
                            capture_output=True, text=True).stdout
    _run(repo)
    after = subprocess.run(["git", "status", "--porcelain", "--ignored"], cwd=repo,
                           capture_output=True, text=True).stdout
    assert before == after


def test_init_harness_command_runs_the_check_and_leads_with_it():
    """The script only helps if /init-harness calls it and the report is bound to its output."""
    text = (ROOT / "commands/init-harness.md").read_text(encoding="utf-8")
    assert 'scripts/init-harness-check.sh"' in text
    assert "INCOMPLETE" in text
