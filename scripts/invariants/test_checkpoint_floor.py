"""AC suite the checkpoint-floor invariant
(scripts/invariants/checkpoint-floor.sh).

Closes: (the gate reds a MEDIUM/HIGH phase with no recorded mid-phase checkpoint, with a
waiver escape), AC3 (the floor is the M2 effective tier), and AC6 (self-coverage + registration).

**No CJK here** (leak gate). Each case asserts the EXIT CODE and that the message names the
effective tier, so a vacuous invariant (always-green, or green because it parsed nothing) is
caught -- the red paths below must really exit 1. The LOW-no-checkpoint-green case is the
anti-starvation guarantee (a quiet LOW branch owes nothing).
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
INV = REPO / "scripts" / "invariants" / "checkpoint-floor.sh"

CHECKPOINT = "checkpoint: mid-phase | risk: MEDIUM"


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


def base_env(tmp_path, *, floor="LOW", frag_lines=(), skip=False):
    frag = fragment(tmp_path, *frag_lines)
    jr = tmp_path / "journal.md"
    jr.write_text(
        "SKIP: checkpoint-floor -- nothing mid-phase to report here\n" if skip
        else "ordinary journal\n"
    )
    return {
        "PLC_CHECKPOINT_FLOOR": floor,
        "PLC_CHECKPOINT_FRAGMENT": str(frag),
        "PLC_CHECKPOINT_JOURNAL": str(jr),
    }


# --- LOW owes nothing: the anti-starvation guarantee (AC3) -------------------------------------

def test_low_floor_no_checkpoint_is_green(tmp_path):
    cp = run(base_env(tmp_path, floor="LOW"))
    assert cp.returncode == 0, cp.stdout + cp.stderr
    assert "LOW" in cp.stdout


# --- MEDIUM needs a recorded mid-phase checkpoint (AC5) ----------------------------------------

def test_medium_floor_without_a_checkpoint_is_red(tmp_path):
    cp = run(base_env(tmp_path, floor="MEDIUM"))
    assert cp.returncode == 1, cp.stdout + cp.stderr
    assert "MEDIUM" in cp.stdout


def test_medium_floor_with_a_checkpoint_is_green(tmp_path):
    cp = run(base_env(tmp_path, floor="MEDIUM", frag_lines=(CHECKPOINT,)))
    assert cp.returncode == 0, cp.stdout + cp.stderr
    assert "MEDIUM" in cp.stdout


def test_marker_must_be_at_line_start(tmp_path):
    # A checkpoint mentioned mid-sentence (not a marker line) does not satisfy the floor.
    cp = run(base_env(tmp_path, floor="MEDIUM",
                       frag_lines=("see the checkpoint: mid-phase note below",)))
    assert cp.returncode == 1, cp.stdout + cp.stderr


# --- waiver escape (AC5) -----------------------------------------------------------------------

def test_medium_floor_unmet_but_waived_is_green(tmp_path):
    cp = run(base_env(tmp_path, floor="MEDIUM", skip=True))
    assert cp.returncode == 0, cp.stdout + cp.stderr
    assert "waived" in cp.stdout


# --- HIGH has the same requirement at this layer (AC5) -----------------------------------------

def test_high_floor_without_a_checkpoint_is_red(tmp_path):
    cp = run(base_env(tmp_path, floor="HIGH"))
    assert cp.returncode == 1, cp.stdout + cp.stderr
    assert "HIGH" in cp.stdout


def test_high_floor_with_a_checkpoint_is_green(tmp_path):
    cp = run(base_env(tmp_path, floor="HIGH", frag_lines=(CHECKPOINT,)))
    assert cp.returncode == 0, cp.stdout + cp.stderr
    assert "HIGH" in cp.stdout


# --- the tier is the M2 effective tier (AC3) ---------------------------------------------------

def test_declared_high_raises_above_low_floor_and_needs_a_checkpoint(tmp_path):
    # A declared HIGH on a no-hit (LOW floor) branch raises the effective tier to HIGH, so a
    # checkpoint is now owed; without one it is red.
    cp = run(base_env(tmp_path, floor="LOW",
                      frag_lines=("risk: HIGH | reason: touches auth and money",)))
    assert cp.returncode == 1, cp.stdout + cp.stderr
    assert "HIGH" in cp.stdout


def test_declared_low_under_medium_floor_still_needs_a_checkpoint(tmp_path):
    # Declaring LOW under a careful-paths hit does not escape MEDIUM; a checkpoint is still owed.
    cp = run(base_env(tmp_path, floor="MEDIUM",
                      frag_lines=("risk: LOW | reason: i think this is fine",)))
    assert cp.returncode == 1, cp.stdout + cp.stderr
    assert "below the objective floor" in cp.stdout


def test_declared_medium_with_checkpoint_on_low_floor_is_green(tmp_path):
    cp = run(base_env(tmp_path, floor="LOW",
                      frag_lines=("risk: MEDIUM | reason: shared gate change", CHECKPOINT)))
    assert cp.returncode == 0, cp.stdout + cp.stderr
    assert "MEDIUM" in cp.stdout


# --- self-coverage: registered in the gate + the envelope --------------------------------------

def test_registered_in_close_gate_invariants():
    cg = json.loads((REPO / ".claude" / "close-gate.json").read_text())
    names = [i["name"] for i in cg["invariants"]]
    assert "checkpoint-floor" in names, names


def test_in_declared_jq_envelope_set():
    env_sh = (REPO / "scripts" / "invariants" / "gate-jq-only-envelope.sh").read_text()
    assert "checkpoint-floor.sh" in env_sh
