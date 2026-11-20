"""AC suite the characterization baseline.

scripts/behavior-baseline.sh records a behavior's before/after exit (a SEPARATE artifact from
the test-evidence fingerprint) and checks the observed before->after transition against the
behavior's class.

**No CJK in this file, deliberately.** This project bans CJK in shipped files outside
README* / CHANGELOG.md / GUIDE*.

Each class has a holds-case AND a contradicts-case: a transition checker that could not go red
on a wrong transition would be silently green, which is the failure AC5 names.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "behavior-baseline.sh"

REG_HEADER = "# id\tclass\tbehavior\tcarrier\twhy\n"


def run(*args: str, baseline: Path, registry: Path | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "PLC_BEHAVIOR_BASELINE": str(baseline)}
    if registry is not None:
        env["PLC_BEHAVIOR_LOCK"] = str(registry)
    return subprocess.run(
        ["/bin/bash", str(SCRIPT), *args],
        capture_output=True, text=True, cwd=REPO, env=env,
    )


def registry(tmp_path: Path, id_="BL-1", cls="PRESERVE") -> Path:
    p = tmp_path / "behavior-lock.tsv"
    p.write_text(REG_HEADER + "\t".join([id_, cls, "a behavior", "t.py::test_x", "why"]) + "\n",
                 encoding="utf-8")
    return p


def record(b: Path, id_: str, state: str, exit_: str):
    r = run("--record", id_, state, exit_, "pytest t.py", "py-darwin", baseline=b)
    assert r.returncode == 0, r.stderr


# --- record / get --------------------------------------------------------------------------

def test_record_then_get(tmp_path):
    b = tmp_path / "baseline.tsv"
    record(b, "BL-1", "before", "0")
    record(b, "BL-1", "after", "1")
    assert run("--get", "BL-1", "before", baseline=b).stdout.strip() == "0"
    assert run("--get", "BL-1", "after", baseline=b).stdout.strip() == "1"


def test_record_rejects_bad_id(tmp_path):
    b = tmp_path / "baseline.tsv"
    r = run("--record", "X407", "before", "0", "c", "e", baseline=b)
    assert r.returncode == 1
    assert "bad id shape" in r.stderr


def test_record_rejects_bad_exit(tmp_path):
    b = tmp_path / "baseline.tsv"
    r = run("--record", "BL-1", "before", "oops", "c", "e", baseline=b)
    assert r.returncode == 1
    assert "bad exit" in r.stderr


# --- transitions: holds + contradicts for each class ---------------------------------------

def test_preserve_holds(tmp_path):
    b = tmp_path / "baseline.tsv"
    record(b, "BL-1", "before", "0")
    record(b, "BL-1", "after", "0")
    r = run("--check-transition", "BL-1", "PRESERVE", baseline=b)
    assert r.returncode == 0
    assert "holds" in r.stdout


def test_preserve_contradicts_when_before_failed(tmp_path):
    b = tmp_path / "baseline.tsv"
    record(b, "BL-1", "before", "1")  # PRESERVE wants pass before
    record(b, "BL-1", "after", "0")
    r = run("--check-transition", "BL-1", "PRESERVE", baseline=b)
    assert r.returncode == 1
    assert "CONTRADICTS" in r.stdout


def test_fix_holds(tmp_path):
    b = tmp_path / "baseline.tsv"
    record(b, "BL-1", "before", "1")
    record(b, "BL-1", "after", "0")
    r = run("--check-transition", "BL-1", "FIX", baseline=b)
    assert r.returncode == 0


def test_fix_contradicts_when_before_passed(tmp_path):
    b = tmp_path / "baseline.tsv"
    record(b, "BL-1", "before", "0")  # FIX wants fail before
    record(b, "BL-1", "after", "0")
    r = run("--check-transition", "BL-1", "FIX", baseline=b)
    assert r.returncode == 1
    assert "CONTRADICTS" in r.stdout


def test_new_holds(tmp_path):
    b = tmp_path / "baseline.tsv"
    record(b, "BL-1", "before", "na")
    record(b, "BL-1", "after", "0")
    r = run("--check-transition", "BL-1", "NEW", baseline=b)
    assert r.returncode == 0


def test_new_contradicts_when_before_existed(tmp_path):
    b = tmp_path / "baseline.tsv"
    record(b, "BL-1", "before", "1")  # NEW wants na before
    record(b, "BL-1", "after", "0")
    r = run("--check-transition", "BL-1", "NEW", baseline=b)
    assert r.returncode == 1
    assert "CONTRADICTS" in r.stdout


def test_class_read_from_registry(tmp_path):
    b = tmp_path / "baseline.tsv"
    reg = registry(tmp_path, cls="FIX")
    record(b, "BL-1", "before", "1")
    record(b, "BL-1", "after", "0")
    r = run("--check-transition", "BL-1", baseline=b, registry=reg)  # no class arg
    assert r.returncode == 0
    assert "FIX" in r.stdout


def test_incomplete_transition_is_blocked(tmp_path):
    b = tmp_path / "baseline.tsv"
    record(b, "BL-1", "before", "0")  # no after
    r = run("--check-transition", "BL-1", "PRESERVE", baseline=b)
    assert r.returncode == 2
    assert "no after-result" in r.stderr


# --- check-file ----------------------------------------------------------------------------

def test_check_file_counts_rows(tmp_path):
    b = tmp_path / "baseline.tsv"
    record(b, "BL-1", "before", "0")
    record(b, "BL-2", "before", "na")
    r = run("--check-file", str(b), baseline=b)
    assert r.returncode == 0
    assert "checked 2 baseline row(s)" in r.stdout
