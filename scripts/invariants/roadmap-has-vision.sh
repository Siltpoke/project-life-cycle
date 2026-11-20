#!/usr/bin/env bash
# Invariant `roadmap-has-vision`: docs/ROADMAP.md must carry a NON-EMPTY vision (north-star) sentence.
#
# WHY: references/roadmap.md documents two layouts and session_card.py reads both, but nothing
# forced either to be filled in, so a project could ship a ROADMAP with no stated goal and every
# consumer (the /catchup card, any downstream progress board) fell back to "undeclared".
#
# TWO ACCEPTED SHAPES (either one is enough):
#   A. milestone-table layout: a `## The one-sentence goal` heading whose body has real text.
#   B. emoji/fisheye layout:   a column-0 `**vision**` or `**<CJK vision label>**` line, before the
#      first `## ` header, with a value on the SAME line (the parser reads it inline).
#
# NON-EMPTY IS THE POINT. An empty heading, an empty bold line, or a heading whose body is only the
# unfilled `<placeholder>` the init-harness stub ships all FAIL: a field that is present but blank is
# exactly the thing this check exists to refuse.
#
# DECLARED LIMIT: it checks that a vision is PRESENT and non-blank, never that it is a good one.
#
# The CJK label is built from its UTF-8 bytes so this file stays ASCII (the leak gate refuses CJK
# in tracked files outside README*/CHANGELOG). Pure awk/grep: the gate envelope is jq-only, no python3.
#
# Usage: roadmap-has-vision.sh [path-to-ROADMAP.md]   (default docs/ROADMAP.md, relative to repo root)
# Verdicts: 0 pass, 1 no usable vision, 3 could not run (a check that could not run must
# never report as though it had).
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

RM="${1:-docs/ROADMAP.md}"
[ -r "$RM" ] || { printf 'COULD NOT RUN: %s is not readable\n' "$RM" >&2; exit 3; }

LABEL_CJK="$(printf '\346\204\277\346\231\257')"   # the two-character CJK word for "vision"
IDEO_SP="$(printf '\343\200\200')"                  # U+3000, the separator the live ROADMAP uses

shape="$(LC_ALL=C awk -v cjk="$LABEL_CJK" -v isp="$IDEO_SP" '
  function blank(s) { gsub(isp, "", s); gsub(/[ \t\r]/, "", s); return s == "" }
  function lc(s)    { return tolower(s) }
  BEGIN { head = 1; ingoal = 0; found_b = 0; found_a = 0 }
  {
    line = $0
    if (substr(line, 1, 3) == "## ") {
      head = 0
      ingoal = (lc(substr(line, 4)) ~ /^the one-sentence goal[ \t\r]*$/) ? 1 : 0
      next
    }
    if (head && substr(line, 1, 2) == "**") {
      for (i = 1; i <= 2; i++) {
        lab = (i == 1) ? "vision" : cjk
        pre = "**" lab "**"
        if (lc(substr(line, 1, length(pre))) == lc(pre)) {
          rest = substr(line, length(pre) + 1)
          if (!blank(rest)) found_b = 1
        }
      }
    }
    if (ingoal && !blank(line)) {
      t = line; gsub(/^[ \t]+|[ \t\r]+$/, "", t)
      # an unfilled `<placeholder>` line is not a goal
      if (!(t ~ /^<.*>$/) && !(t ~ /^<!--.*-->$/)) found_a = 1
    }
  }
  END { if (found_a) print "A"; else if (found_b) print "B"; else print "NONE" }
' "$RM")"

case "$shape" in
  A) printf 'ok  %s carries a vision (## The one-sentence goal, non-empty)\n' "$RM" ;;
  B) printf 'ok  %s carries a vision (column-0 bold vision line, non-empty)\n' "$RM" ;;
  *)
    printf 'FAIL %s has no non-empty vision. Add EITHER a `## The one-sentence goal` section with a real sentence under it, OR a column-0 `**vision** <sentence>` line (value on the same line) before the first `## ` header. An empty heading, an empty bold line, or the unfilled `<...>` placeholder does not count. See references/roadmap.md.\n' "$RM" >&2
    exit 1 ;;
esac
