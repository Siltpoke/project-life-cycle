#!/usr/bin/env bash
# Print the untracked-artifact skips as a counted ABSENCE OF COVERAGE, naming the artifact
# responsible for each, in this shape:
#   `N rows NOT COVERED — <artifact> is not tracked`
#
# It lives in its own file rather than inline in run.sh so the wording can be ASSERTED;
# scripts/test_not_covered_line.py is the guard.
#
# WHY THE WORDS ARE BANNED: "skipped" is precisely the word a reader's eye slides past, and
# rows of missing coverage then read as passes.
set -euo pipefail
BASE="${1:?usage: print-not-covered.sh <skip-baseline.txt>}"
[ -r "$BASE" ] || { echo "FAIL print-not-covered: baseline unreadable: $BASE" >&2; exit 1; }

# An empty baseline is a FAIL, never a silent "0 rows NOT COVERED" -- zero rows and a baseline
# that failed to generate look identical in a count.
total="$(LC_ALL=C /usr/bin/grep -c . "$BASE" || true)"
if [ "${total:-0}" -eq 0 ]; then
  echo "FAIL print-not-covered: $BASE lists no rows -- an empty baseline is not evidence of full coverage" >&2
  exit 1
fi

# Group by artifact, so the reader sees WHICH artifact costs them WHICH coverage rather than one
# opaque total. Every row of the baseline carries its artifact after ` -> ` (scripts/skip-baseline.sh).
LC_ALL=C /usr/bin/sed -n 's/^.* -> //p' "$BASE" | LC_ALL=C sort | /usr/bin/uniq -c \
  | while read -r n artifact; do
      printf '%s rows NOT COVERED \xe2\x80\x94 %s is not tracked\n' "$n" "$artifact"
    done

printf '%s rows NOT COVERED in total \xe2\x80\x94 run these against the named artifacts before trusting them\n' "$total"
