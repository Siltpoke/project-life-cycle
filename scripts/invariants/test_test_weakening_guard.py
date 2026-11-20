"""AC suite the test-weakening guard
(scripts/invariants/test-weakening-guard.sh).

Closes: (a net drop in test-function count across all test files is RED, with a waiver
escape) and AC6 (self-coverage + registration). The drop-no-waiver case asserts exit 1, so a
vacuous always-green guard is caught.

**No CJK here** (leak gate). Counts are driven by the PLC_TESTWEAKEN_*_COUNT seams so the suite
does not depend on the repo's real test count.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
INV = REPO / "scripts" / "invariants" / "test-weakening-guard.sh"


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


def seam(head: int, base: int, journal: Path | None = None) -> dict[str, str]:
    env = {
        "PLC_TESTWEAKEN_HEAD_COUNT": str(head),
        "PLC_TESTWEAKEN_BASE_COUNT": str(base),
        "PLC_TESTWEAKEN_JOURNAL": str(journal) if journal is not None else "/dev/null",
    }
    return env


# --- no drop / growth is green -----------------------------------------------------------------

def test_no_drop_is_green(tmp_path):
    cp = run(seam(10, 10))
    assert cp.returncode == 0, cp.stdout + cp.stderr
    assert "did not drop" in cp.stdout


def test_growth_is_green(tmp_path):
    cp = run(seam(12, 10))
    assert cp.returncode == 0, cp.stdout + cp.stderr
    assert "did not drop" in cp.stdout


# --- a drop with no waiver is RED (self-coverage) ----------------------------------------------

def test_drop_without_waiver_is_red(tmp_path):
    cp = run(seam(5, 10))
    assert cp.returncode == 1, cp.stdout + cp.stderr
    assert "dropped from 10 to 5" in cp.stderr


def test_single_deletion_is_red(tmp_path):
    cp = run(seam(99, 100))
    assert cp.returncode == 1, cp.stdout + cp.stderr


# --- a drop with a waiver is green -------------------------------------------------------------

def test_drop_with_waiver_is_green(tmp_path):
    jr = tmp_path / "journal.md"
    jr.write_text("ordinary journal\nSKIP: test-weakening -- merged two redundant tests\n")
    cp = run(seam(5, 10, jr))
    assert cp.returncode == 0, cp.stdout + cp.stderr
    assert "waiver is recorded" in cp.stdout


def test_waiver_must_be_at_line_start(tmp_path):
    # A mention mid-sentence is not a waiver marker.
    jr = tmp_path / "journal.md"
    jr.write_text("we did not write a SKIP: test-weakening line here\n")
    cp = run(seam(5, 10, jr))
    assert cp.returncode == 1, cp.stdout + cp.stderr


# --- self-coverage: registered in the gate + the envelope --------------------------------------

def test_registered_in_close_gate_invariants():
    cg = json.loads((REPO / ".claude" / "close-gate.json").read_text())
    names = [i["name"] for i in cg["invariants"]]
    assert "test-weakening-guard" in names, names


def test_in_declared_jq_envelope_set():
    env_sh = (REPO / "scripts" / "invariants" / "gate-jq-only-envelope.sh").read_text()
    assert "test-weakening-guard.sh" in env_sh
