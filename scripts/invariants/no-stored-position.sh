#!/usr/bin/env bash
# Invariant (AC-7, AC-9, AC-5): docs/ROADMAP.md stores no position.
#
# Contract: skills/project-lifecycle/references/roadmap-format.md
# "Derivable => must not be written down." Position and `done` are derivable from closure
# records, so a copy written into the roadmap is a cache that rots.
#
# TWO SCAN FACES, BECAUSE ONE REGEX OVER THE WHOLE FILE IS WRONG IN BOTH DIRECTIONS. The first
# draft of this check scanned the file for the words done / position / progress. Measured, both
# failures are real:
#
#   * FALSE RED. This project's own plan contains a step whose text translates as "remove
#     the inclusive `done` test" -- a sentence ABOUT the word. (The source line is Chinese;
#     it is paraphrased here rather than quoted because this file is shipped bytes and the
#     CJK rule refuses CJK outside docs/.) A free-text scan goes red on prose on day one, catching a
#     description rather than a defect. Fix: face 1 anchors on KEY POSITION inside plan blocks,
#     never on free text.
#
#   * FALSE GREEN. Somebody hand-writes a position into a mainline row's `what` cell in a
#     language this checker was never taught -- the golden fixture uses Cyrillic,
#     "выполнено 2/3 шага". Three English words match none of it, the check passes, and a position is very much
#     stored. Fix: face 2 scans the mainline table's `what` cells for the SHAPE of a progress
#     literal, in any language, rather than for a word list.
#
# A word list is wrong by construction here: it can only ever know the languages somebody
# thought of. A shape -- "a number over a number", "N of M", "N%" -- survives translation.
#
# AND THEN THE SHAPE WAS TOO WIDE, WHICH IS THE SAME DEFECT ONE LEVEL DOWN. Face 2's first
# version scanned EVERY mainline row. Against this repo's real roadmap it produced 16 findings
# and all 16 were wrong: `23/24`, `40/55`, `57/105`, `6 of 24` are how this project routinely
# writes TEST RESULTS ("23 of 24 mutants killed", "40 red of 55"). A fraction in prose is not a
# stored position -- this is R2-5's false red, reproduced by the author who was fixing R2-5.
#
# The narrowing is principled, not a threshold nudged until the noise stopped. POSITION IS A
# PROPERTY OF A STATION, and a station is a row that HAS A PLAN BLOCK. A row no block binds to
# has no position to store, so a numeral in its `what` cell cannot be a stored one. Face 2 now
# scans only rows named by some block's `binds-to:`. Today that is one row; the covered set
# grows exactly as the format is adopted, which is the right coupling.
#
# THE COST, STATED: a hand-written position on a row with no plan block goes unnoticed. That is
# acceptable because AC-9 is about a written value CONTRADICTING the derived one, and where
# nothing is derived there is no contradiction to catch.
#
# WHAT THIS DOES NOT CATCH, stated rather than implied:
#   * "nearly there", in any language -- natural language with no numeral. That is not a stored
#     position; it commits to nothing a renderer could read back. Out of scope on purpose.
#   * a position written into a step's own text. The closed line set stops NEW KEYS, not
#     content inside an allowed value; this is filed as an open gap in the contract, not fixed
#     here.
#   * anything outside docs/ROADMAP.md.
#
# Envelope: bash + coreutils. No python3, no jq (CLAUDE.md).
set -euo pipefail

ROADMAP="${ROADMAP_PATH:-docs/ROADMAP.md}"
fail=0
bad() { printf '✗ %s\n' "$*" >&2; fail=1; }

[ -f "$ROADMAP" ] || { printf '✗ %s is not a regular file\n' "$ROADMAP" >&2; exit 1; }

# --- face 1: key-position scan inside plan blocks ---------------------------------------------
# Only a line whose KEY is one of the banned names counts. `- done` with no colon is caught too,
# because the closed line set (station-id-integrity.sh) rejects any unrecognised line -- this
# face deliberately overlaps there rather than relying on it, since the two guards can be run
# separately.
face1=$(
  awk '
    index($0, "## 🧭") == 1 { inplan = 1; next }
    inplan && substr($0, 1, 3) == "## " { inplan = 0 }
    !inplan { next }
    /^[ \t]*-[ \t]*(done|position|progress)[ \t]*:/ { printf "%d: %s\n", NR, $0 }
    /^[ \t]*-[ \t]*(done|position|progress)[ \t]*$/ { printf "%d: %s\n", NR, $0 }
  ' "$ROADMAP"
)
if [ -n "$face1" ]; then
  while IFS= read -r l; do
    [ -n "$l" ] && bad "$ROADMAP:$l — a declared position/done key inside a plan block"
  done <<EOF
$face1
EOF
else
  printf '  ok  no position/done key declared in any plan block\n'
fi

# --- face 2: progress-literal SHAPE in BOUND mainline rows' `what` cells ------------------------
# Only rows some block's `binds-to:` names. See the header for why this is narrower than "every
# mainline row" and why that narrowing is principled rather than noise-driven.
bound_names=$(
  awk '
    index($0, "## 🧭") == 1 { inplan = 1; next }
    inplan && substr($0, 1, 3) == "## " { inplan = 0 }
    !inplan { next }
    /^- binds-to:[ \t]*/ { b = $0; sub(/^- binds-to:[ \t]*/, "", b); gsub(/[ \t]+$/, "", b); print b }
  ' "$ROADMAP"
)
if [ -z "$bound_names" ]; then
  printf '  ok  no plan blocks yet — no row has a position to store\n'
  bound_names="$(printf '\001nothing\001')"
fi

# Shapes, not words:
#   N/M  N / M      a fraction of steps
#   N of M          English long form
#   <CJK-or-any> N/M  covered by the first shape regardless of surrounding language
# A bare year range or a version number would false-positive on `N/M`, so the fraction shape
# additionally requires the numerator to be no greater than the denominator, which "2026/09"
# fails and "2/3" passes. That rule is the reason this is awk and not one grep.
face2=$(
  printf '%s\n' "$bound_names" | awk '
    NR == FNR { bound[$0] = 1; next }
    index($0, "## 🛣") == 1 { inmain = 1; next }
    inmain && substr($0, 1, 3) == "## " { inmain = 0 }
    !inmain { next }
    {
      t = $0; sub(/^[ \t]+/, "", t)
      if (substr(t, 1, 1) != "|") next
      if (t ~ /^\|[-: |]+\|?$/) next
      n = split(t, c, "|")
      if (n < 4) next
      name = c[2]; gsub(/^[ \t]+|[ \t]+$/, "", name)
      if (!(name in bound)) next
      what = c[3]
      if (match(what, /[0-9]+[ \t]*\/[ \t]*[0-9]+/)) {
        frac = substr(what, RSTART, RLENGTH)
        split(frac, p, "/")
        a = p[1] + 0; b = p[2] + 0
        if (b > 0 && a <= b) { printf "%d: fraction %s in a `what` cell\n", NR, frac; next }
      }
      if (match(what, /[0-9]+[ \t]*(of|OF)[ \t]*[0-9]+/)) {
        printf "%d: \"N of M\" in a `what` cell\n", NR; next
      }
      # THE PERCENTAGE ARM IS GONE, and this is the measurement that removed it rather
      # than a judgement that it felt noisy. The moment a second row got a plan block --
      # the readability line, at this phase close -- the arm produced FOUR findings on
      # that one row and none of them was a position: two acceptance thresholds
      # (`>= 20%`, `>= 30%`), one measured rate (`1.72%`), one ratio (`43x`). That is
      # R2-5 recurring a third time: first as an English word scan, then as a fraction
      # shape over every row, now as a bare percentage.
      #
      # AND THE NARROWING IS PRINCIPLED, not a threshold nudged until the noise stopped.
      # `N/M` carries STRUCTURE a checker can reason about -- a denominator, which must
      # not exceed the numerator and which the declared step count of a station can be
      # compared against. A bare percentage carries none: nothing in `20%` distinguishes
      # a position from a target from a measurement, so any rule over it is guessing.
      # The two arms above keep the claim; this one only ever had a shape.
      #
      # THE COST, STATED: a position written ONLY as a bare percentage now goes
      # unnoticed. That is accepted for the same reason AC-9 gives -- the criterion
      # is about a written value CONTRADICTING the derived one, and the derived value is
      # a fraction of steps, so a percentage was never the form the contradiction takes.
    }
  ' - "$ROADMAP"
)
if [ -n "$face2" ]; then
  while IFS= read -r l; do
    [ -n "$l" ] && bad "$ROADMAP:$l — a hand-written position; position is derived, never stored"
  done <<EOF
$face2
EOF
else
  printf '  ok  no progress literal in any mainline `what` cell\n'
fi

if [ "$fail" -ne 0 ]; then
  printf '✗ no-stored-position: FAILED\n' >&2
  exit 1
fi
printf '✓ no-stored-position\n'
