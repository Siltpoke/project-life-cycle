#!/usr/bin/env bash
# Invariant: SKILL.md's close-gate check-set table lists exactly the checks the gate actually
# runs -- no more, no fewer.
#
# WHY THIS EXISTS. `SKILL.md` told readers the gate "checks exactly these eight things, and
# nothing else" and printed eight rows, while `close-gate.sh` had twelve `cs()` call sites. The
# "and nothing else" clause is what makes that sentence a falsifiable claim rather than an
# incomplete list, and it was false. This is not a documentation nicety: an agent in another
# session read that sentence, planned an entire wiring scheme against it, and every coordinate in
# the plan was wrong -- including "add a ninth check", when nine, ten and eleven already existed.
#
# NEITHER SIDE IS A LITERAL. Both lists are parsed at run time from the files that own them. A
# check-set frozen into this script as an array would be a third copy of the same fact, which is
# the defect class filed earlier: a derived value written down as a literal rots and then lies. So a
# drift on either side reds this, and no edit here is needed when a check is legitimately added.
#
# THE PARSE MUST SURVIVE INDENTATION, and that is not hypothetical. `^cs ` (column-0 anchor) would
# match all twelve calls that exist today only because all twelve happen to be flush-left. The
# experiment-gate check being added in this same phase has an `off` state that must skip its
# `cs()` call entirely -- which means wrapping it in an `if` and indenting it. A column-0 anchor
# would then go SILENTLY BLIND to the newest check, which is the one a fresh pin most needs to
# see. Found by cross-check agent B before the code existed.
#
# WHAT IT DOES NOT DO, stated here rather than discovered later: it says nothing about whether a
# row's DESCRIPTION or its MODE column is accurate. Only the id sets are compared. A row claiming
# "task + phase" for a phase-only check passes this invariant. That is a real gap and it is left
# open deliberately -- the mode is derived from flag assignments spread across a `case` statement,
# and a parser for that would be a second implementation of the gate's own control flow, which is
# a worse thing to maintain than the gap. Filed rather than approximated.
#
# jq-only envelope: no python3 here or in anything it calls (CLAUDE.md).

set -uo pipefail

NAME="skill-checkset-matches-gate"

# Subjects are ARGUMENTS with repo-relative defaults, never environment variables. The suite runs
# the real script against throwaway fixtures, and a test whose verdict depends on this repo's own
# tracked SKILL.md would go red for reasons that have nothing to do with the mechanism. The
# argument form is also what lets the mutants below be repeatable instead of a one-off hand run.
GATE="${1:-scripts/close-gate.sh}"
SKILL="${2:-skills/project-lifecycle/SKILL.md}"

pass() { printf 'PASS %s: %s\n' "$NAME" "$1"; exit 0; }
fail() { printf 'FAIL %s: %s\n' "$NAME" "$1"; exit 1; }

[ -r "$GATE" ]  || fail "cannot read $GATE"
[ -r "$SKILL" ] || fail "cannot read $SKILL"

# --- left side: the ids the gate actually announces -------------------------------------------
#
# `cs <flag> "<id>(<label>)"` is the gate's own check-set printer. Take the id, which is whatever
# precedes the first `(`. `[[:space:]]*` so an indented (conditional) call is still seen; the
# `cs "` shape excludes the function DEFINITION `cs() {`, which has no space before the paren.
GATE_IDS="$(
  /usr/bin/grep -oE '^[[:space:]]*cs[[:space:]]+[^[:space:]]+[[:space:]]+"[^("]+\(' "$GATE" 2>/dev/null |
  /usr/bin/sed -E 's/.*"([^("]+)\(.*/\1/' |
  /usr/bin/sort -u
)"

# --- right side: the ids SKILL.md declares -----------------------------------------------------
#
# Bounded to the ONE table that follows the check-set header, so an unrelated markdown table
# elsewhere in a 500-line file can never contribute a row. Without the bound this check would
# quietly widen every time someone adds a table.
SKILL_IDS="$(
  /usr/bin/awk '
    /\| # \| Check \| Mode \|/ { intable=1; next }
    intable && /^[[:space:]]*\|[-| ]+\|[[:space:]]*$/ { next }
    intable && !/^[[:space:]]*\|/ { exit }
    intable { print }
  ' "$SKILL" |
  /usr/bin/sed -E 's/^[[:space:]]*\|[[:space:]]*([^ |]+)[[:space:]]*\|.*/\1/' |
  /usr/bin/sort -u
)"

[ -n "$GATE_IDS" ]  || fail "parsed ZERO check ids out of $GATE -- the \`cs\` call shape changed, and an empty left side would make this invariant pass against an empty table while proving nothing"
[ -n "$SKILL_IDS" ] || fail "parsed ZERO rows out of $SKILL's check-set table -- the table header or its shape changed"

ONLY_GATE="$(/usr/bin/comm -23 <(printf '%s\n' "$GATE_IDS") <(printf '%s\n' "$SKILL_IDS") | /usr/bin/tr '\n' ' ')"
ONLY_SKILL="$(/usr/bin/comm -13 <(printf '%s\n' "$GATE_IDS") <(printf '%s\n' "$SKILL_IDS") | /usr/bin/tr '\n' ' ')"

# Both directions are findings, and for different reasons. A check the gate runs but the table
# omits is the defect itself -- a reader plans against a list that understates enforcement.
# A row the table lists but the gate does not run is the opposite and is worse in one way: it
# claims enforcement that is not happening, which is what a `verified 3 of 3` line does.
if [ -n "${ONLY_GATE// }" ] || [ -n "${ONLY_SKILL// }" ]; then
  MSG="$SKILL's check-set table and $GATE's \`cs()\` calls disagree."
  [ -n "${ONLY_GATE// }" ]  && MSG="$MSG
      the gate RUNS but the table omits: ${ONLY_GATE% } -- the table understates what is enforced (a defect this repo measured)"
  [ -n "${ONLY_SKILL// }" ] && MSG="$MSG
      the table LISTS but the gate does not run: ${ONLY_SKILL% } -- the table claims enforcement that is not happening"
  fail "$MSG"
fi

N="$(printf '%s\n' "$GATE_IDS" | /usr/bin/grep -c .)"
pass "the check-set table lists exactly the $N ids the gate announces ($(printf '%s' "$GATE_IDS" | /usr/bin/tr '\n' ' ' | /usr/bin/sed 's/ $//')) -- ids only; this says NOTHING about whether each row's description or Mode column is right"
