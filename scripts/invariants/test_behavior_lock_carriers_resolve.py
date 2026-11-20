"""AC suite the carrier-resolves invariant.

scripts/invariants/behavior-lock-carriers-resolve.sh is the hard-fail gate: every behavior-lock
row this branch touched must name a carrier that resolves to a real test.

**No CJK in this file, deliberately.** This project bans CJK in shipped files outside
README* / CHANGELOG.md / GUIDE*.

The self-coverage case (test_bogus_carrier_is_red) plants a dangling carrier and REQUIRES the
invariant go red -- a guard that cannot fail on its own target is vacuous.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
INV = REPO / "scripts" / "invariants" / "behavior-lock-carriers-resolve.sh"

HEADER = "# id\tclass\tbehavior\tcarrier\twhy\n"


def row(id_="BL-1", cls="PRESERVE", beh="a behavior", car="t.py::test_x", why="matters") -> str:
    return "\t".join([id_, cls, beh, car, why])


def run(registry: Path, root: Path, base: Path | None = None) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "PLC_BEHAVIOR_LOCK": str(registry),
        "PLC_BEHAVIOR_LOCK_ROOT": str(root),
    }
    if base is not None:
        env["PLC_BEHAVIOR_LOCK_BASE"] = str(base)
    return subprocess.run(
        ["/bin/bash", str(INV)],
        capture_output=True,
        text=True,
        cwd=REPO,
        env=env,
    )


def reg(tmp_path: Path, *rows: str) -> Path:
    p = tmp_path / "behavior-lock.tsv"
    p.write_text(HEADER + "".join(r + "\n" for r in rows), encoding="utf-8")
    return p


def carrier_file(tmp_path: Path, name="t.py", body="def test_x(): pass\n") -> None:
    (tmp_path / name).write_text(body, encoding="utf-8")


def test_all_carriers_resolve_is_green(tmp_path):
    carrier_file(tmp_path)
    registry = reg(tmp_path, row())
    r = run(registry, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "resolved every carrier for 1 behavior row(s)" in r.stdout


def test_bogus_carrier_is_red(tmp_path):
    # Self-coverage: the carrier names a test that does not exist -> must be red.
    registry = reg(tmp_path, row(car="does/not/exist.py::test_ghost"))
    r = run(registry, tmp_path)
    assert r.returncode == 1
    assert "carrier does not resolve to a real test" in r.stdout
    assert "BL-1" in r.stdout


def test_one_bad_among_good_is_red(tmp_path):
    carrier_file(tmp_path)
    registry = reg(tmp_path, row(id_="BL-1"), row(id_="BL-2", car="missing.py"))
    r = run(registry, tmp_path)
    assert r.returncode == 1
    assert "BL-2" in r.stdout


def test_absent_registry_is_explicit_pass(tmp_path):
    missing = tmp_path / "behavior-lock.tsv"  # never created
    r = run(missing, tmp_path)
    assert r.returncode == 0
    assert "no behavior-lock registry in this tree" in r.stdout


def test_row_unchanged_from_base_is_skipped(tmp_path):
    # The carrier is bogus, but the row is identical to base (not touched this branch) -> skip.
    bad = row(car="missing.py::test_ghost")
    registry = reg(tmp_path, bad)
    base = tmp_path / "base.tsv"
    base.write_text(HEADER + bad + "\n", encoding="utf-8")
    r = run(registry, tmp_path, base=base)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "no behavior rows added or changed on this branch" in r.stdout


def test_changed_row_against_base_is_checked(tmp_path):
    # Base has BL-1 with a good carrier; branch changed it to a bogus one -> checked and red.
    carrier_file(tmp_path)
    base = tmp_path / "base.tsv"
    base.write_text(HEADER + row() + "\n", encoding="utf-8")
    registry = reg(tmp_path, row(car="now/missing.py::test_ghost"))
    r = run(registry, tmp_path, base=base)
    assert r.returncode == 1
    assert "BL-1" in r.stdout
