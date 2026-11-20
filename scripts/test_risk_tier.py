"""AC suite the risk-tier parser (scripts/risk-tier.sh).

Closes: (a declared `risk: <TIER> | reason: <text>` line is parsed and validated) and
(fail-safe, never silent: malformed or ambiguous resolves to HIGH, absent to empty).

**No CJK in this file, deliberately.** This project bans CJK in shipped files outside
README* / CHANGELOG.md / GUIDE*.

Tests assert the resolved VALUE, not only exit codes: a resolver that printed nothing would
exit 0 on every input, which is byte-identical for "absent" and for "bug that drops the tier".
Each case therefore checks the exact stdout.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "risk-tier.sh"


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["/bin/bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
    )


def frag(tmp_path: Path, *lines: str) -> Path:
    p = tmp_path / "qa-log-fragment.md"
    p.write_text("".join(line + "\n" for line in lines))
    return p


# --- --check-line ------------------------------------------------------------------------------

def test_check_line_accepts_each_legal_tier():
    for tier in ("LOW", "MEDIUM", "HIGH"):
        cp = run("--check-line", f"risk: {tier} | reason: blast radius is one caller")
        assert cp.returncode == 0, f"{tier} should be well-formed: {cp.stderr}"


def test_check_line_rejects_bad_token():
    cp = run("--check-line", "risk: SEVERE | reason: whatever")
    assert cp.returncode == 1


def test_check_line_rejects_empty_reason():
    cp = run("--check-line", "risk: HIGH | reason: ")
    assert cp.returncode == 1


def test_check_line_rejects_missing_pipe():
    cp = run("--check-line", "risk: HIGH reason: no pipe here")
    assert cp.returncode == 1


def test_check_line_rejects_not_a_risk_line():
    cp = run("--check-line", "mode: detailed | source: x | confirmed-at: y")
    assert cp.returncode == 1


# --- --resolve ---------------------------------------------------------------------------------

def test_resolve_single_valid_returns_that_tier(tmp_path):
    for tier in ("LOW", "MEDIUM", "HIGH"):
        f = frag(tmp_path, f"risk: {tier} | reason: touches shared auth state")
        cp = run("--resolve", str(f))
        assert cp.returncode == 0
        assert cp.stdout.strip() == tier


def test_resolve_absent_is_empty(tmp_path):
    f = frag(tmp_path, "mode: detailed | source: project-default | confirmed-at: kickoff")
    cp = run("--resolve", str(f))
    assert cp.returncode == 0
    assert cp.stdout.strip() == ""


def test_resolve_missing_fragment_is_empty(tmp_path):
    cp = run("--resolve", str(tmp_path / "does-not-exist.md"))
    assert cp.returncode == 0
    assert cp.stdout.strip() == ""


def test_resolve_ambiguous_is_high(tmp_path):
    f = frag(
        tmp_path,
        "risk: LOW | reason: first call",
        "risk: HIGH | reason: second call contradicts",
    )
    cp = run("--resolve", str(f))
    assert cp.returncode == 0
    assert cp.stdout.strip() == "HIGH"
    assert "ambiguous" in cp.stderr


def test_resolve_malformed_single_is_high(tmp_path):
    f = frag(tmp_path, "risk: SEVERE | reason: bad token")
    cp = run("--resolve", str(f))
    assert cp.returncode == 0
    assert cp.stdout.strip() == "HIGH"
    assert "malformed" in cp.stderr


# --- --levels ----------------------------------------------------------------------------------

def test_levels_lists_three(tmp_path):
    cp = run("--levels")
    assert cp.returncode == 0
    levels = [ln for ln in cp.stdout.splitlines() if ln.strip()]
    assert levels == ["LOW", "MEDIUM", "HIGH"]
