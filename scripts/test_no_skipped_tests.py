"""p35 — `scripts/assert_no_skipped_tests.py` actually refuses the thing it names.

A guard that has never been shown red is worth what one that always returns 0 is worth.
The cases below are the four verdicts it can reach, one mutant at a time: a clean report
passes, a report carrying a skip fails, an EMPTY report fails (that is the vacuous-pass
shape this repository keeps filing), and an unreadable path fails rather than being
treated as "nothing skipped here".

The last test is the one that matters most and is not a fixture: it runs the real width
suite under a real interpreter whose Unicode version does not match the table, produces a
real JUnit report, and requires the guard to reject it. Without that, every case here is
a statement about hand-written XML.
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
GUARD = REPO / "scripts" / "assert_no_skipped_tests.py"
WIDTH_SUITE = REPO / "scripts" / "test_eaw_width.py"

CLEAN = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="2">
<testcase classname="t" name="a"/>
<testcase classname="t" name="b"/>
</testsuite></testsuites>
"""

WITH_SKIP = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="2">
<testcase classname="t" name="a"/>
<testcase classname="t" name="b"><skipped message="Unicode version skew"/></testcase>
</testsuite></testsuites>
"""

EMPTY = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="0"></testsuite></testsuites>
"""


def _run(*args):
    return subprocess.run([sys.executable, str(GUARD), *args],
                          capture_output=True, text=True)


def _write(tmp_path, name, body):
    p = tmp_path / name
    p.write_text(body)
    return str(p)


def test_a_clean_report_passes(tmp_path):
    proc = _run(_write(tmp_path, "clean.xml", CLEAN))
    assert proc.returncode == 0, proc.stderr
    assert "none skipped" in proc.stdout


def test_a_skipped_case_fails_and_names_it(tmp_path):
    proc = _run(_write(tmp_path, "skip.xml", WITH_SKIP))
    assert proc.returncode == 1, "a report carrying a skip must not exit 0"
    assert "t::b" in proc.stderr, "the guard must name which case skipped: %s" % proc.stderr
    assert "Unicode version skew" in proc.stderr, "the skip reason must survive to the log"


def test_an_empty_report_fails(tmp_path):
    """Zero collected cases prints the same green as zero skips. It is not the same thing."""
    proc = _run(_write(tmp_path, "empty.xml", EMPTY))
    assert proc.returncode == 1, "an empty report is a vacuous pass and must be refused"
    assert "zero test cases" in proc.stderr


def test_an_unreadable_path_fails(tmp_path):
    proc = _run(str(tmp_path / "does-not-exist.xml"))
    assert proc.returncode == 1, "a missing report must fail, not read as 'nothing skipped'"


def test_no_arguments_is_a_usage_error():
    proc = _run()
    assert proc.returncode == 2


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq not installed")
def test_against_a_real_skewed_run_of_the_width_suite(tmp_path):
    """END TO END, on the actual failure p35 is about.

    Runs the width suite under an interpreter whose `unicodedata` version differs from
    the table's header, so the remaining version-gated test really skips, and requires
    the guard to reject that report. Every other case in this file is hand-written XML;
    this one is the suite itself.

    IT IS BEST-EFFORT, AND A SKIP OF IT IS NOT CAUGHT ANYWHERE. This docstring used to say
    the opposite -- "that skip is itself caught in CI by the guard under test" -- and that
    was false: the CI step feeds the guard exactly one report, the WIDTH suite's
    (`validate.yml`, `--junit-xml=width-junit.xml`). Nothing points it at this file, so
    every skip below lands in the unguarded `pytest scripts/ -q` step, which prints one
    green tick either way. On a GitHub runner the second-interpreter hunt most likely finds
    a system python without pytest and skips, so the test this file calls the one that
    matters most is also the one most likely never to run.

    Filed rather than papered over: the same green CI run reported
    `2104 passed, 23 skipped` in that unguarded step, so widening the guard to the whole
    suite is a real decision with 23 pre-existing skips behind it, not a one-line change.
    """
    other = None
    for cand in ("/Library/Frameworks/Python.framework/Versions/3.10/bin/python3",
                 "python3.10", "python3.11", "python3.12"):
        path = shutil.which(cand) if not cand.startswith("/") else (
            cand if Path(cand).exists() else None)
        if not path:
            continue
        probe = subprocess.run(
            [path, "-c", "import unicodedata;print(unicodedata.unidata_version)"],
            capture_output=True, text=True)
        if probe.returncode == 0 and probe.stdout.strip() != _table_unicode_version():
            other = path
            break
    if other is None:
        pytest.skip("no second interpreter here whose Unicode version differs from the table")

    have_pytest = subprocess.run([other, "-c", "import pytest"], capture_output=True)
    if have_pytest.returncode != 0:
        pytest.skip("%s has no pytest installed" % other)

    report = tmp_path / "skewed.xml"
    subprocess.run([other, "-m", "pytest", str(WIDTH_SUITE), "-q",
                    "--junit-xml", str(report)],
                   capture_output=True, text=True, cwd=REPO)
    assert report.exists(), "the skewed run produced no report, so this proves nothing"

    proc = _run(str(report))
    assert proc.returncode == 1, (
        "the width suite skipped under a skewed interpreter and the guard let it pass; "
        "stdout=%s stderr=%s" % (proc.stdout, proc.stderr))


def _table_unicode_version():
    head = (REPO / "scripts" / "lib" / "eaw-ranges.jq").read_text()[:600]
    m = re.search(r"unicodedata ([0-9]+\.[0-9]+\.[0-9]+)", head)
    return m.group(1) if m else ""


# ----------------------------------------------------------------------------------------
# The workflow STEP, not just the guard it calls.
#
# The guard above answers one question: did anything skip. The CI step answers two -- did
# anything skip, AND did the suite pass -- and for a while it printed the same sentence for
# both. Measured, with one digit wrong in the table: every case RAN, three FAILED, the
# report showed zero skips, and the step still said "did not all run", sending the reader
# to look for a skip that was not there.
#
# These tests EXECUTE the step's body, lifted verbatim out of validate.yml, against a stub
# `python` whose exit codes and JUnit output are chosen per case. Asserting on the YAML text
# instead would pass for a step that never runs, which is this repo's most-filed shape.
# ----------------------------------------------------------------------------------------

WORKFLOW = REPO / ".github" / "workflows" / "validate.yml"
STEP_NAME = "The width table's checks may not skip (p35)"


def _step_body():
    """Lift the step's `run:` block out of the workflow, de-indented, byte for byte.

    Parsed rather than duplicated: a copy in this file would drift from the workflow and
    then these tests would be checking a step that no longer exists.
    """
    y = WORKFLOW.read_text(encoding="utf-8")
    m = re.search(
        r"- name: %s\n        run: \|\n((?:          .*\n|\n)+)" % re.escape(STEP_NAME), y)
    assert m, "the step %r is gone from validate.yml, or its shape changed" % STEP_NAME
    return "".join(l[10:] if l.startswith("          ") else l
                   for l in m.group(1).splitlines(True))


# NOT a %-format string: the stub's own body contains `printf '%s'`, and formatting it
# once meant the interpreter path collided with the shell's format specifier.
#
# THE STUB READS ITS OWN ARGV, and that is the whole point of this version. The first one
# matched on `"$1 $2"` alone and wrote to a hard-coded `width-junit.xml`. MEASURED: with
# that stub, pointing the step at `scripts/NO_SUCH_SUITE.py` still gave `4 passed`, and so
# did deleting `--junit-xml=` from the step entirely. A green step that verified nothing
# about the width table is precisely the defect p35 was filed for -- reintroduced inside
# the tests written to pin the fix for it. Asserting on the YAML text passes for a step
# that never runs; executing it against a stub that ignores argv passes for a step that
# runs the WRONG THING.
#
# So: the report goes to the path the step actually asks for, an absent `--junit-xml` is a
# hard error rather than a silently-correct default, and the suite path is recorded so a
# test can assert WHICH suite was run.
STUB = """#!/bin/bash
# Stand-in for `python`. Records what it was asked to do, then behaves as configured.
if [ "$1" = "-m" ] && [ "$2" = "pytest" ]; then
  shift 2
  junit=""
  suites=""
  for a in "$@"; do
    case "$a" in
      --junit-xml=*) junit="${a#--junit-xml=}" ;;
      -*) ;;
      *) suites="$suites $a" ;;
    esac
  done
  printf '%s\n' "$suites" > "$STUB_RECORD"
  if [ -z "$junit" ]; then
    echo "stub: the step asked for no --junit-xml, so nothing downstream can see skips" >&2
    exit 90
  fi
  printf '%s' "$JUNIT_BODY" > "$junit"
  exit "$PYTEST_RC"
fi
exec __REAL_PYTHON__ "$@"
""".replace("__REAL_PYTHON__", sys.executable)


def _run_step(tmp_path, pytest_rc, junit_body):
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    stub = stub_dir / "python"
    stub.write_text(STUB)
    stub.chmod(0o755)
    # The step calls `python scripts/assert_no_skipped_tests.py` by RELATIVE path, so the
    # sandbox needs the real guard at that path. Copied, not stubbed: the guard is the part
    # under test on the skip arm, and a stub of it would make that arm prove nothing.
    (tmp_path / "scripts").mkdir()
    shutil.copy(GUARD, tmp_path / "scripts" / GUARD.name)
    script = tmp_path / "step.sh"
    script.write_text(_step_body())
    record = tmp_path / "stub-record"
    env = {
        "PATH": "%s:%s" % (stub_dir, os.environ["PATH"]),
        "PYTEST_RC": str(pytest_rc),
        "JUNIT_BODY": junit_body,
        "STUB_RECORD": str(record),
        "HOME": str(tmp_path),
    }
    res = subprocess.run(["/bin/bash", "-e", str(script)],
                         capture_output=True, text=True, cwd=str(tmp_path), env=env)
    res.suites_run = record.read_text().split() if record.exists() else []
    return res


def test_step_passes_when_the_suite_passed_and_nothing_skipped(tmp_path):
    res = _run_step(tmp_path, 0, CLEAN)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "::error" not in (res.stdout + res.stderr)


def test_step_names_a_FAILING_suite_as_failing_not_as_skipping(tmp_path):
    """The regression this splits the verdicts for: a red suite must not be reported as a skip."""
    res = _run_step(tmp_path, 1, CLEAN)
    out = res.stdout + res.stderr
    assert res.returncode == 1, out
    assert "RAN and FAILED" in out, out
    assert "did not all RUN" not in out, (
        "a failing suite was reported as a skip -- the exact wording bug this test pins")


def test_step_names_a_SKIPPED_case_as_skipping_not_as_failing(tmp_path):
    res = _run_step(tmp_path, 0, WITH_SKIP)
    out = res.stdout + res.stderr
    assert res.returncode == 1, out
    assert "did not all RUN" in out, out
    assert "RAN and FAILED" not in out, out


def test_step_reports_BOTH_when_the_suite_failed_and_something_skipped(tmp_path):
    """Neither verdict may swallow the other -- one `rc` for both is how they got confused."""
    res = _run_step(tmp_path, 1, WITH_SKIP)
    out = res.stdout + res.stderr
    assert res.returncode == 1, out
    assert "RAN and FAILED" in out, out
    assert "did not all RUN" in out, out


def test_the_step_runs_the_width_suite_and_asks_for_a_report(tmp_path):
    """WHICH suite, and that it asks for a machine-readable report at all.

    Both were unasserted until a reviewer measured it: with the previous argv-blind stub,
    pointing the step at `scripts/NO_SUCH_SUITE.py` gave `4 passed`, and deleting
    `--junit-xml=` gave `4 passed`. Either edit produces a green CI step that checks
    nothing about the width table -- p35's own defect, inside p35's own guard tests.

    The stub now exits 90 with no report when `--junit-xml` is absent, so that edit fails
    every arm; this test covers the other half, the suite path.
    """
    res = _run_step(tmp_path, 0, CLEAN)
    assert res.returncode == 0, res.stdout + res.stderr
    assert res.suites_run == ["scripts/test_eaw_width.py"], (
        "the step ran %r; the width suite is the only thing this guard is pointed at, and "
        "a step aimed elsewhere is green while verifying nothing" % (res.suites_run,))
