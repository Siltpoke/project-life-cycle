"""AC suite the protected-behavior-change invariant
(scripts/invariants/protected-behavior-change.sh).

Closes: (a touched PRESERVE carrier with no recorded baseline is RED, with a waiver escape),
AC4 (scoped + fail-safe), and AC5 (self-coverage + registration). The touched-no-baseline case
asserts exit 1, so a vacuous always-green invariant is caught.

**No CJK here** (leak gate). The touched-file set is driven by the PLC_PROTCHG_TOUCHED seam so the
suite does not depend on git state.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
INV = REPO / "scripts" / "invariants" / "protected-behavior-change.sh"

PRESERVE_ROW = "BL-9\tPRESERVE\tsome behavior\tfoo.py::test_x\tbecause"
FIX_ROW = "BL-8\tFIX\tsome fix\tbar.py::test_y\tbecause"


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


def write(tmp_path: Path, name: str, *lines: str) -> Path:
    p = tmp_path / name
    p.write_text("".join(ln + "\n" for ln in lines))
    return p


def base_env(tmp_path, *, rows=(PRESERVE_ROW,), baseline=False, skip=False, touched="foo.py"):
    lock = write(tmp_path, "lock.tsv", *rows)
    if baseline:
        bl = write(tmp_path, "base.tsv",
                   "# id\tstate\texit\tcmd\tenv\tdate",
                   "BL-9\tbefore\t0\tc\te\td",
                   "BL-9\tafter\t0\tc\te\td")
    else:
        bl = write(tmp_path, "base.tsv", "# id\tstate\texit\tcmd\tenv\tdate")
    jr = write(tmp_path, "journal.md",
               "SKIP: protected-change -- re-proven below" if skip else "ordinary journal")
    return {
        "PLC_PROTCHG_LOCK": str(lock),
        "PLC_PROTCHG_BASELINE": str(bl),
        "PLC_PROTCHG_JOURNAL": str(jr),
        "PLC_PROTCHG_TOUCHED": touched,
    }


# --- touched PRESERVE carrier with no baseline is RED (self-coverage) --------------------------

def test_touched_preserve_carrier_no_baseline_is_red(tmp_path):
    cp = run(base_env(tmp_path, baseline=False, touched="foo.py"))
    assert cp.returncode == 1, cp.stdout + cp.stderr
    assert "BL-9" in cp.stderr


# --- touched PRESERVE carrier WITH a recorded baseline is green --------------------------------

def test_touched_preserve_carrier_with_baseline_is_green(tmp_path):
    cp = run(base_env(tmp_path, baseline=True, touched="foo.py"))
    assert cp.returncode == 0, cp.stdout + cp.stderr


# --- waiver escape -----------------------------------------------------------------------------

def test_touched_no_baseline_but_waived_is_green(tmp_path):
    cp = run(base_env(tmp_path, baseline=False, skip=True, touched="foo.py"))
    assert cp.returncode == 0, cp.stdout + cp.stderr
    assert "waiver" in cp.stdout


# --- untouched carrier is green (the anti-starvation guarantee) --------------------------------

def test_untouched_carrier_is_green(tmp_path):
    cp = run(base_env(tmp_path, baseline=False, touched="something_else.py"))
    assert cp.returncode == 0, cp.stdout + cp.stderr
    assert "no PRESERVE carrier changed" in cp.stdout


# --- a touched NON-PRESERVE (FIX/NEW) carrier does not trigger ---------------------------------

def test_touched_non_preserve_carrier_is_green(tmp_path):
    cp = run(base_env(tmp_path, rows=(FIX_ROW,), baseline=False, touched="bar.py"))
    assert cp.returncode == 0, cp.stdout + cp.stderr


# --- the carrier file is the part before '::' --------------------------------------------------

def test_carrier_file_is_before_the_colons(tmp_path):
    # touching foo.py matches a carrier foo.py::test_x; touching foo.py::test_x literally does not.
    cp = run(base_env(tmp_path, baseline=False, touched="foo.py::test_x"))
    assert cp.returncode == 0, cp.stdout + cp.stderr


# --- self-coverage: registered in the gate + the envelope --------------------------------------

def test_registered_in_close_gate_invariants():
    cg = json.loads((REPO / ".claude" / "close-gate.json").read_text())
    names = [i["name"] for i in cg["invariants"]]
    assert "protected-behavior-change" in names, names


def test_in_declared_jq_envelope_set():
    env_sh = (REPO / "scripts" / "invariants" / "gate-jq-only-envelope.sh").read_text()
    assert "protected-behavior-change.sh" in env_sh
