#!/usr/bin/env python3
"""Refuse a test run that reported a skip. Reads a pytest JUnit XML report (p35).

WHY THIS EXISTS. A skipped test and a passing test produce the same coloured tick on
a CI summary, and the difference is the whole question. `scripts/lib/eaw-ranges.jq`
went unverified on every CI run from the day it landed because three tests skipped on
an interpreter whose Unicode version did not match the table's header, and the job
stayed green. Nothing was broken and nothing was checked.

WHY IT READS A REPORT INSTEAD OF KNOWING THE SKIP CONDITIONS. The obvious version of
this guard re-states the conditions -- "fail if the Unicode versions differ", "fail if
jq is missing" -- and then drifts from the suite the first time somebody adds a fourth
reason to skip. This one never learns why a test skipped, only that one did, so a skip
reason invented next year is covered by construction rather than by remembering.

NOT IN THE CLOSE GATE'S DEPENDENCY ENVELOPE. This is a CI-only script. `CLAUDE.md`
keeps the close gate jq-only so it stays a drop-in for other people's repositories;
this needs a report that only pytest produces, so it stays on the CI side of that line.

Usage:
    python3 scripts/assert_no_skipped_tests.py <junit.xml> [<junit.xml> ...]

Exit 0 only when every named report contains at least one test case and none of them
is skipped. An empty report is a FAILURE, not a vacuous pass: a run that collected
nothing has the same shape as a run where nothing was skipped.
"""
import sys
import xml.etree.ElementTree as ET


def check(path):
    """Return (n_cases, [(classname, name, reason), ...]) -- a 2-tuple -- or raise."""
    root = ET.parse(path).getroot()
    # pytest emits <testsuites><testsuite>...; older shapes emit <testsuite> at the root.
    suites = root.iter("testsuite")
    cases = [c for s in suites for c in s.iter("testcase")]
    skipped = []
    for c in cases:
        for s in c.iter("skipped"):
            skipped.append((c.get("classname", ""), c.get("name", ""),
                            (s.get("message") or s.text or "").strip()))
    return len(cases), skipped


def main(argv):
    if not argv:
        print("usage: assert_no_skipped_tests.py <junit.xml> [...]", file=sys.stderr)
        return 2

    failed = False
    for path in argv:
        try:
            total, skipped = check(path)
        except (OSError, ET.ParseError) as exc:
            print("%s: cannot read a JUnit report here (%s). A guard that cannot read its "
                  "input has not checked anything." % (path, exc), file=sys.stderr)
            failed = True
            continue

        if total == 0:
            print("%s: the report contains zero test cases. That is indistinguishable from "
                  "a run where nothing was skipped, so it is a failure." % path,
                  file=sys.stderr)
            failed = True
            continue

        if skipped:
            print("%s: %d of %d test cases were SKIPPED, and a skip here is not a pass:"
                  % (path, len(skipped), total), file=sys.stderr)
            for classname, name, reason in skipped:
                print("  - %s::%s\n      %s" % (classname, name, reason or "(no reason given)"),
                      file=sys.stderr)
            failed = True
            continue

        print("%s: %d test cases, none skipped." % (path, total))

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
