"""Test support for the close-gate bash embedded in references/close-gate.md.

The gate is markdown-resident by design (projects copy it in via init-harness),
so the only honest way to test it is to extract the fenced block and run it.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

# close-gate.md contains multiple ```bash fences (portable gate, self-test,
# pre-push hook, wiring examples). Anchor on the "## Portable gate script"
# heading and take the first ```bash fence that follows it, so a fence added
# elsewhere in the doc can never be picked up silently.
_HEADING = "## Portable gate script"
_FENCE = re.compile(r"```bash\n(#!/usr/bin/env bash\n.*?)```", re.DOTALL)

# retention.md currently has exactly one ```bash fence, but we anchor on its
# heading anyway (same contract as extract_gate_script) so a second bash
# example added anywhere else in the doc can never be picked up silently.
_RETENTION_HEADING = "## Embedded portable script — `scripts/retention-drain.sh`"
_RETENTION_FENCE = re.compile(r"```bash\n(#!/usr/bin/env bash\n.*?)```", re.DOTALL)


def extract_gate_script(md_path: Path) -> str:
    """Return the gate's bash source from the ```bash fence under §Portable gate script."""
    text = md_path.read_text(encoding="utf-8")
    heading_idx = text.find(_HEADING)
    if heading_idx == -1:
        raise AssertionError(f"heading '{_HEADING}' not found in {md_path}")
    match = _FENCE.search(text, heading_idx)
    if match is None:
        raise AssertionError(
            f"no ```bash fence found after '{_HEADING}' in {md_path}"
        )
    return match.group(1)


# The FULL heading, matching extract_gate_script's anchor beside it rather than a prefix of it.
# `"## Self-test"` also matches a future `## Self-test — something else` added EARLIER in the doc,
# and `find` returns the first hit, so the looser anchor would silently start reading a different
# fence while every assertion about "the harness" kept passing.
_SELF_TEST_HEADING = "## Self-test — `scripts/test-close-gate.sh`"


def extract_self_test_script(md_path: Path) -> str:
    """Return the embedded self-test harness's bash source from the ```bash fence under
    §Self-test. Same anchoring contract as extract_gate_script — close-gate.md holds several
    bash fences, so a fence added elsewhere can never be read as the harness."""
    text = md_path.read_text(encoding="utf-8")
    heading_idx = text.find(_SELF_TEST_HEADING)
    if heading_idx == -1:
        raise AssertionError(f"heading '{_SELF_TEST_HEADING}' not found in {md_path}")
    match = _FENCE.search(text, heading_idx)
    if match is None:
        raise AssertionError(f"no ```bash fence found after '{_SELF_TEST_HEADING}' in {md_path}")
    return match.group(1)


def extract_retention_drain_script(md_path: Path) -> str:
    """Return retention-drain.sh's bash source from the ```bash fence under
    §Embedded portable script in references/retention.md."""
    text = md_path.read_text(encoding="utf-8")
    heading_idx = text.find(_RETENTION_HEADING)
    if heading_idx == -1:
        raise AssertionError(f"heading '{_RETENTION_HEADING}' not found in {md_path}")
    match = _RETENTION_FENCE.search(text, heading_idx)
    if match is None:
        raise AssertionError(
            f"no ```bash fence found after '{_RETENTION_HEADING}' in {md_path}"
        )
    return match.group(1)


# `/init-harness` is prose — nothing executes it, so the only thing that CAN be executed is the
# artifact it hands the adopter. That artifact is machine-readable: the reference doc carries
# the close-gate manifest it generates as a real ```json fence, and the tests run THAT through the
# real gate. Same full-heading anchoring contract as _SELF_TEST_HEADING, and for the same reason —
# a prefix anchor would silently start reading a different fence while the assertions kept passing.
_INIT_MANIFEST_HEADING = "## Generated close-gate manifest"
_JSON_FENCE = re.compile(r"```json\n(.*?)```", re.DOTALL)


def extract_init_harness_manifest(md_path: Path) -> dict:
    """Return the `.claude/close-gate.json` template `/init-harness` generates, parsed.

    Raises AssertionError when the heading or its fence is absent — an adopter-facing doc that
    does not carry the manifest cannot be checked, and a test that quietly passed on a missing
    fixture would report a green about a template that does not exist.
    """
    text = md_path.read_text(encoding="utf-8")
    heading_idx = text.find(_INIT_MANIFEST_HEADING)
    if heading_idx == -1:
        raise AssertionError(f"heading '{_INIT_MANIFEST_HEADING}' not found in {md_path}")
    match = _JSON_FENCE.search(text, heading_idx)
    if match is None:
        raise AssertionError(
            f"no ```json fence found after '{_INIT_MANIFEST_HEADING}' in {md_path}"
        )
    return json.loads(match.group(1))


_RUNNER_HEADING = "## Evidence runner — `scripts/gen-test-evidence.sh`"


def extract_evidence_runner_script(md_path: Path) -> str:
    """Return the evidence runner's bash source from the ```bash fence under §Evidence runner.

    Same full-heading anchoring contract as the other extractors: close-gate.md holds several
    bash fences, so a prefix anchor could silently start returning the gate itself while every
    assertion phrased as "the runner does X" kept passing.
    """
    text = md_path.read_text(encoding="utf-8")
    heading_idx = text.find(_RUNNER_HEADING)
    if heading_idx == -1:
        raise AssertionError(f"heading '{_RUNNER_HEADING}' not found in {md_path}")
    match = _FENCE.search(text, heading_idx)
    if match is None:
        raise AssertionError(f"no ```bash fence found after '{_RUNNER_HEADING}' in {md_path}")
    return match.group(1)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def make_fixture_repo(tmp_path: Path, manifest: dict | None, files: dict[str, str]) -> Path:
    """A git repo with one commit on main and an origin/main ref the gate can diff against."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@t.t")
    _git(repo, "config", "user.name", "t")
    if manifest is not None:
        (repo / ".claude").mkdir(exist_ok=True)
        (repo / ".claude/close-gate.json").write_text(json.dumps(manifest), encoding="utf-8")
    for rel, body in files.items():
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    # origin/main == HEAD, so `origin/main..HEAD` is empty unless a test adds commits
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    return repo


def run_gate(repo: Path, script: str, *args: str) -> subprocess.CompletedProcess[str]:
    gate = repo / ".gate.sh"
    gate.write_text(script, encoding="utf-8")
    gate.chmod(0o755)
    return subprocess.run(
        ["bash", str(gate), *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
