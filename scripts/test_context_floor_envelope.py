"""Regression rows for `scripts/invariants/context-floor-envelope.sh`.

WHY THIS FILE EXISTS. The invariant carries a self-coverage assertion, and
that assertion once had an off-switch, and then another. An earlier version let `PLC_CFE_ROOT` relocate the scanned
set outright; a later one gated the relocation behind `PLC_CFE_SELFTEST=1`, which a caller could set
from OUTSIDE for the same silent pass -- an environment variable spelled in the script's own
source is not a capability. Both times the close gate showed a bare check mark, because
`close-gate.sh` runs invariants with `>/dev/null 2>&1`.

The fix deleted the relocation path. What was missing after the fix was any UNATTENDED oracle for
"deleted": the controls that proved it were run by hand, once.
These rows are that oracle.

They deliberately assert on the invariant's OUTPUT and exit code rather than on its source text --
a grep for the variable name would pass the moment somebody re-added the feature under a different
name, and would fail on a comment mentioning the history.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INVARIANT = REPO / "scripts" / "invariants" / "context-floor-envelope.sh"


def run(env_extra=None, script=None, cwd=None):
    env = None
    if env_extra:
        import os

        env = os.environ.copy()
        env.update(env_extra)
    return subprocess.run(
        ["/bin/bash", str(script or INVARIANT)],
        cwd=str(cwd or REPO),
        env=env,
        capture_output=True,
        text=True,
    )


def test_clean_tree_passes():
    """The control. Every row below is only meaningful against a green baseline."""
    r = run()
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SELF-COVERAGE" in r.stdout
    assert "FAIL" not in r.stdout


def test_self_coverage_actually_runs_and_names_every_declared_file():
    """A green run must PROVE it read each declared file, not merely not complain."""
    r = run()
    ok_lines = [l for l in r.stdout.splitlines() if l.startswith("ok") and "SELF-COVERAGE" in l]
    assert len(ok_lines) == 3, r.stdout
    for name in ("context-floor.sh", "close-gate-nudge.sh", "lib/floor-env.sh"):
        assert any(name in l for l in ok_lines), (name, r.stdout)


def test_no_environment_variable_relocates_the_scanned_set(tmp_path):
    """The environment off-switch, as a row.

    A fixture tree is built holding copies of the declared set with a banned interpreter planted in
    one of them. Pointing the historical variables at it -- BOTH of them, which is what defeated
    the gated version -- must change nothing: same verdict, same output, and the real files still named.
    """
    hooks = tmp_path / "skills" / "project-lifecycle" / "hooks"
    (hooks / "lib").mkdir(parents=True)
    for rel in ("context-floor.sh", "close-gate-nudge.sh"):
        (hooks / rel).write_text((REPO / "skills/project-lifecycle/hooks" / rel).read_text())
    (hooks / "lib" / "floor-env.sh").write_text(
        (REPO / "skills/project-lifecycle/hooks/lib/floor-env.sh").read_text()
    )
    # A violation the invariant WOULD report, if the relocation were honoured.
    with (hooks / "context-floor.sh").open("a") as fh:
        fh.write('\npython3 -c "pass"\n')

    baseline = run()
    attacked = run({"PLC_CFE_ROOT": str(tmp_path), "PLC_CFE_SELFTEST": "1"})

    assert attacked.returncode == baseline.returncode == 0, attacked.stdout + attacked.stderr
    assert attacked.stdout == baseline.stdout, "an ambient environment changed what was scanned"
    assert "SELF-COVERAGE" in attacked.stdout, "self-coverage was skipped"


def test_a_blinded_checker_makes_self_coverage_fail(tmp_path):
    """Positive control for the assertion itself: it must be able to go RED.

    Without this row the three above would all pass against a checker that reports nothing at all.
    """
    src = INVARIANT.read_text()
    needle = "inv1_hits() {\n  grep -nE"
    assert src.count(needle) == 1
    blinded = tmp_path / "blinded.sh"
    blinded.write_text(src.replace(needle, "inv1_hits() {\n  return 0\n  grep -nE"))

    r = run(script=blinded)
    assert r.returncode == 1, r.stdout
    fails = [l for l in r.stdout.splitlines() if "FAIL" in l and "SELF-COVERAGE" in l]
    assert len(fails) == 3, r.stdout


def test_an_empty_declared_set_refuses_to_run(tmp_path):
    """An empty list passes every loop vacuously and reads exactly like a clean repository."""
    src = INVARIANT.read_text()
    start = src.index('INV1_FILES="')
    end = src.index('"', start + len('INV1_FILES="'))
    emptied = tmp_path / "emptied.sh"
    emptied.write_text(src[:start] + 'INV1_FILES=""' + src[end + 1 :])

    r = run(script=emptied)
    assert r.returncode == 1, r.stdout
    assert "is empty" in r.stdout, r.stdout
    assert "Refusing to run" in r.stdout, r.stdout


def test_a_planted_violation_in_the_real_tree_is_reported(tmp_path):
    """The invariant's ordinary job, pinned so the rows above cannot all pass on a no-op script."""
    src = INVARIANT.read_text()
    # Point the declared set at a fixture tree by editing the DECLARATION, which is the only
    # supported way to change what is scanned now that the environment path is gone.
    fixture = tmp_path / "hooks"
    fixture.mkdir()
    (fixture / "planted.sh").write_text('#!/usr/bin/env bash\npython3 -c "pass"\n')
    start = src.index('INV1_FILES="')
    end = src.index('"', start + len('INV1_FILES="'))
    repointed = tmp_path / "repointed.sh"
    repointed.write_text(src[:start] + 'INV1_FILES="\nhooks/planted.sh\n"' + src[end + 1 :])
    # INV-2's set must stay a subset, or the consistency check fires first.
    text = repointed.read_text()
    s2 = text.index('INV2_FILES="')
    e2 = text.index('"', s2 + len('INV2_FILES="'))
    repointed.write_text(text[:s2] + 'INV2_FILES="\nhooks/planted.sh\n"' + text[e2 + 1 :])

    r = run(script=repointed, cwd=tmp_path)
    assert r.returncode == 1, r.stdout
    assert "INV-1: a python interpreter is invoked in hooks/planted.sh" in r.stdout, r.stdout
