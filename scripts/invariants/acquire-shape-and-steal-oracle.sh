#!/usr/bin/env bash
# Invariant: the repair lock's acquire cannot walk back to its two-step shape, and the one string
# that has ever caught the defect it produced cannot silently leave the test suite again.
#
# WHY THESE TWO AND NOT A THIRD. Every other assertion about the lock watches BEHAVIOUR, and
# behaviour-watching rows all share one weakness: they pass on a hook that has been refactored back
# to the broken shape as long as the host never reaches the window. A concurrency row can report zero
# double-allows on a fast machine while the invariant behind it is already broken. So the
# regression guard for this lock cannot itself be a race.
#
#   I1  the acquire is not a bare directory-create followed by a separate owner stamp.
#   I3  the release-time steal report appears in at least one committed test file.
#
# I3 LOOKS LIKE BOOKKEEPING AND IS NOT. The steal report is the one observable the defect produces;
# if no committed test names it, nothing watches that phenomenon and failures go unexplained.
# This is what stops it leaving the suite.
#
# jq-only envelope: bash + grep, no python3, no jq.

set -uo pipefail

NAME="acquire-shape-and-steal-oracle"
HOOK="${PLC_I1_HOOK:-skills/project-lifecycle/hooks/context-floor.sh}"
TESTDIR="${PLC_I3_TESTDIR:-skills/project-lifecycle/hooks}"
GREP=/usr/bin/grep
[ -x "$GREP" ] || GREP=grep

fail() { printf 'FAIL %s: %s\n' "$NAME" "$1"; exit 1; }

[ -r "$HOOK" ] || fail "$HOOK is unreadable -- a guard that cannot read its subject must never report a pass"

# --- I1: the acquire publishes content before name --------------------------------------------
# BOTH DIRECTIONS, because either alone is satisfiable by an accident. Requiring the `ln` publish
# alone passes a hook that ALSO kept the old create; banning the old create alone passes a hook whose
# acquire was deleted outright.
# THE BAN IS A PATTERN, NOT A LITERAL. Banning only the exact string `mkdir "$_cfl"` would let
# `mkdir -p "$_cfl"` -- still the two-step
# acquire, just with a flag inserted -- through, and a hook that kept the publish line as
# camouflage and added a reachable `mkdir -p` fallback would clear both halves.
I1_BAD='mkdir( +-[^ ]+)* +"\$_cfl"'
I1_GOOD='ln "$_cft" "$_cfl"'
n_bad="$("$GREP" -cE -- "$I1_BAD" "$HOOK" 2>/dev/null || true)"
n_good="$("$GREP" -cF -- "$I1_GOOD" "$HOOK" 2>/dev/null || true)"
if [ "${n_bad:-0}" != 0 ]; then
  fail "I1 the acquire has walked back to a bare directory-create ($n_bad occurrence(s) of the old form in $HOOK). That form takes the lock and stamps its owner separately, so a rival arriving in between reads an empty owner, classifies a LIVE lock as ownerless and removes it."
fi
if [ "${n_good:-0}" != 1 ]; then
  fail "I1 the atomic publish is not in $HOOK exactly once (found ${n_good:-0}). Zero means the acquire was replaced or deleted; more than one means there are two publish sites and only one of them is reasoned about."
fi
printf 'ok %s I1: the acquire publishes its content before its name, and the two-step form is absent\n' "$NAME"

# --- I3: the steal report is watched by a committed test ---------------------------------------
# THE NEEDLE IS ASSEMBLED. Written out, it would occur in this file, and this file would satisfy its
# own search -- the guard would report the oracle as present forever, including on the day somebody
# deletes it -- the use-versus-mention collision, easy to hit inside guards written to enforce
# something about text.
I3_TOK="STO$(printf 'LEN')"
[ -d "$TESTDIR" ] || fail "I3 $TESTDIR is not a directory -- the search has nowhere to look and a vacuous pass is the failure this guard exists to prevent"
hits=0
while IFS= read -r f; do
  [ -n "$f" ] || continue
  case "$f" in *"$(basename "$0")") continue ;; esac   # never count this guard's own source
  # A USE, NOT A MENTION: a file containing only a COMMENT saying
  # "that assertion was deleted, this comment is the only thing left that mentions it" would satisfy a
  # plain substring count.
  # The answer is to match the SHAPE, not the substring. A comment
  # line cannot be a live assertion, so comment lines do not count.
  n="$("$GREP" -c -E "^[[:space:]]*[^#[:space:]].*${I3_TOK}" "$f" 2>/dev/null || true)"
  hits=$((hits + ${n:-0}))
done <<EOF
$("$GREP" -rl --include='test-*.sh' -- "$I3_TOK" "$TESTDIR" 2>/dev/null || true)
EOF
if [ "$hits" -lt 1 ]; then
  fail "I3 the release-time steal report has no committed test watching it. It is the one observable the defect produces; without a test naming it, nothing watches that phenomenon."
fi
printf 'ok %s I3: the release-time steal report is named by %s committed test occurrence(s)\n' "$NAME" "$hits"
printf 'PASS %s: the acquire cannot walk back to its two-step shape, and its oracle cannot silently leave\n' "$NAME"
