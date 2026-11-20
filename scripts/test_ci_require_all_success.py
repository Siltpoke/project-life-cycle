"""The aggregate CI gate's body (scripts/ci-require-all-success.sh).

The gate is the single required status check for branch protection. Its whole reason to exist is
that a GitHub required check which was SKIPPED counts as passing, so the gate must treat anything
other than `success` as a non-pass. These tests pin both directions — a real all-success pass AND
each non-pass it must catch — because a gate that only catches `failure` would let a silently
skipped suite merge green, which is the hole this phase closes.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
GATE = REPO / "scripts" / "ci-require-all-success.sh"


def _run(*results):
    return subprocess.run(
        ["/bin/bash", str(GATE), *results],
        capture_output=True, text=True,
    )


def test_all_success_passes():
    proc = _run("success", "success", "success")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "all required jobs succeeded" in proc.stdout


def test_a_skipped_dependency_is_not_a_pass():
    """The load-bearing case: `skipped` reads as green to GitHub required checks, so the gate
    must fail on it. A gate that only caught `failure` would let a path-skipped suite merge."""
    proc = _run("success", "skipped", "success")
    assert proc.returncode != 0
    assert "skipped" in (proc.stdout + proc.stderr)


def test_a_failed_dependency_fails():
    proc = _run("success", "failure", "success")
    assert proc.returncode != 0
    assert "failure" in (proc.stdout + proc.stderr)


def test_a_cancelled_dependency_fails():
    proc = _run("cancelled", "success", "success")
    assert proc.returncode != 0
    assert "cancelled" in (proc.stdout + proc.stderr)


def test_empty_result_fails():
    """An empty result string (a job that produced no result) must not pass."""
    proc = _run("success", "", "success")
    assert proc.returncode != 0


def test_no_arguments_is_an_error_not_a_pass():
    """Zero results is a wiring mistake, not 'everything passed'. Distinct exit code (2) so a
    broken caller is not read as a clean gate — empty-set-is-not-evidence."""
    proc = _run()
    assert proc.returncode == 2
    assert "no job results" in (proc.stdout + proc.stderr)


def test_the_error_names_every_bad_result_not_just_the_first():
    proc = _run("skipped", "failure", "success")
    out = proc.stdout + proc.stderr
    assert proc.returncode != 0
    assert "skipped" in out and "failure" in out, "each non-success must be named, not just the first"
