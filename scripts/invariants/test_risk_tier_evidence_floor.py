"""AC suite the risk-tier evidence-floor invariant
(scripts/invariants/risk-tier-evidence-floor.sh).

Closes: (gate enforces the evidence floor per effective tier, with a waiver escape),
AC3 (the careful-paths hit is an objective floor a declaration cannot drop below), and AC4
(LOW adds nothing). HIGH's recorded-baseline sub-check is added in a sibling file.

**No CJK here** (leak gate). Each case asserts the EXIT CODE and that the message names the
effective tier, so a vacuous invariant (always-green, or green because it parsed nothing) is
caught -- that is the self-coverage requirement: the red paths below must really exit 1.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
INV = REPO / "scripts" / "invariants" / "risk-tier-evidence-floor.sh"


def run(env_extra: dict[str, str]) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update(env_extra)
    return subprocess.run(
        ["/bin/bash", str(INV)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env=env,
    )


def fragment(tmp_path: Path, *lines: str) -> Path:
    p = tmp_path / "frag.md"
    p.write_text("".join(ln + "\n" for ln in lines))
    return p


def lock(tmp_path: Path, name: str, *rows: str) -> Path:
    p = tmp_path / name
    p.write_text("".join(r + "\n" for r in rows))
    return p


ROW = "BL-9\tPRESERVE\tsome behavior\tscripts/test_x.py::test_y\tbecause"


def base_env(tmp_path, *, floor="LOW", frag_lines=(), rows=(), base_rows=(), skip=False,
             baseline=False):
    frag = fragment(tmp_path, *frag_lines)
    lk = lock(tmp_path, "lock.tsv", *rows)
    bs = lock(tmp_path, "base.tsv", *base_rows)
    jr = tmp_path / "journal.md"
    jr.write_text("SKIP: risk-floor -- nothing to lock here\n" if skip else "ordinary journal\n")
    bl = tmp_path / "baseline.tsv"
    if baseline:
        # a recorded before+after for BL-9 (the id ROW carries)
        bl.write_text(
            "# id\tstate\texit\tcmd\tenv\tdate\n"
            "BL-9\tbefore\t0\tpytest x\tpy\t2026-11-02\n"
            "BL-9\tafter\t0\tpytest x\tpy\t2026-11-02\n"
        )
    else:
        bl.write_text("# id\tstate\texit\tcmd\tenv\tdate\n")
    return {
        "PLC_RISK_FLOOR": floor,
        "PLC_RISK_FRAGMENT": str(frag),
        "PLC_RISK_LOCK": str(lk),
        "PLC_RISK_LOCK_BASE": str(bs),
        "PLC_RISK_JOURNAL": str(jr),
        "PLC_RISK_BASELINE": str(bl),
    }


# --- LOW adds nothing (AC4) --------------------------------------------------------------------

def test_low_floor_no_declaration_is_green(tmp_path):
    cp = run(base_env(tmp_path, floor="LOW"))
    assert cp.returncode == 0, cp.stdout + cp.stderr
    assert "LOW" in cp.stdout


# --- MEDIUM floor needs a locked row (AC2) -----------------------------------------------------

def test_medium_floor_with_a_touched_row_is_green(tmp_path):
    cp = run(base_env(tmp_path, floor="MEDIUM", rows=(ROW,)))
    assert cp.returncode == 0, cp.stdout + cp.stderr
    assert "MEDIUM" in cp.stdout


def test_medium_floor_without_a_row_is_red(tmp_path):
    cp = run(base_env(tmp_path, floor="MEDIUM", rows=(), base_rows=()))
    assert cp.returncode == 1, cp.stdout + cp.stderr
    assert "MEDIUM" in cp.stdout


def test_medium_floor_row_present_in_base_is_red(tmp_path):
    # A row byte-identical in base was not added this branch -> does not count.
    cp = run(base_env(tmp_path, floor="MEDIUM", rows=(ROW,), base_rows=(ROW,)))
    assert cp.returncode == 1, cp.stdout + cp.stderr


# --- waiver escape (AC2) -----------------------------------------------------------------------

def test_medium_floor_unmet_but_waived_is_green(tmp_path):
    cp = run(base_env(tmp_path, floor="MEDIUM", rows=(), skip=True))
    assert cp.returncode == 0, cp.stdout + cp.stderr
    assert "waived" in cp.stdout


# --- objective floor cannot be declared away (AC3) ---------------------------------------------

def test_declared_low_under_medium_floor_still_requires_the_row(tmp_path):
    env = base_env(
        tmp_path, floor="MEDIUM",
        frag_lines=("risk: LOW | reason: i think this is fine",),
        rows=(),
    )
    cp = run(env)
    assert cp.returncode == 1, cp.stdout + cp.stderr
    assert "below the objective floor" in cp.stdout


def test_declared_high_raises_above_low_floor(tmp_path):
    # HIGH needs a row AND a recorded baseline.
    env = base_env(
        tmp_path, floor="LOW",
        frag_lines=("risk: HIGH | reason: touches auth and money",),
        rows=(ROW,), baseline=True,
    )
    cp = run(env)
    assert cp.returncode == 0, cp.stdout + cp.stderr
    assert "HIGH" in cp.stdout


def test_declared_high_with_no_row_is_red(tmp_path):
    env = base_env(
        tmp_path, floor="LOW",
        frag_lines=("risk: HIGH | reason: touches auth and money",),
        rows=(),
    )
    cp = run(env)
    assert cp.returncode == 1, cp.stdout + cp.stderr
    assert "HIGH" in cp.stdout


# --- HIGH additionally needs a recorded baseline ------------------------------------------

def test_high_with_row_but_no_baseline_is_red(tmp_path):
    env = base_env(
        tmp_path, floor="LOW",
        frag_lines=("risk: HIGH | reason: touches auth and money",),
        rows=(ROW,), baseline=False,
    )
    cp = run(env)
    assert cp.returncode == 1, cp.stdout + cp.stderr
    assert "RECORDED BASELINE" in cp.stdout


def test_high_unmet_but_waived_is_green(tmp_path):
    env = base_env(
        tmp_path, floor="LOW",
        frag_lines=("risk: HIGH | reason: touches auth and money",),
        rows=(ROW,), baseline=False, skip=True,
    )
    cp = run(env)
    assert cp.returncode == 0, cp.stdout + cp.stderr
    assert "waived" in cp.stdout


# --- self-coverage: registered in the gate + the envelope --------------------------------------

def test_registered_in_close_gate_invariants():
    cg = json.loads((REPO / ".claude" / "close-gate.json").read_text())
    names = [i["name"] for i in cg["invariants"]]
    assert "risk-tier-evidence-floor" in names, names


def test_in_declared_jq_envelope_set():
    env_sh = (REPO / "scripts" / "invariants" / "gate-jq-only-envelope.sh").read_text()
    assert "risk-tier-evidence-floor.sh" in env_sh
    assert "risk-tier.sh" in env_sh
