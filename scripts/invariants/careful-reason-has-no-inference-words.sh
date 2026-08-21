#!/usr/bin/env bash
# Invariant `careful-reason-has-no-inference-words`.
#
# ITS NAME IS THE POINT. It proves the ABSENCE OF A FEW WORDS in what the suggester emits. It does
# NOT prove that a reason is factual -- an inference phrased around these words passes it. The
# constraint it partially mechanises: a reason may state what was observed and may
# not state what it means. This is the FLOOR of that constraint, not the constraint.
#
# An earlier name for this file was `careful-reason-states-fact-only.sh`. That name was
# a claim wider than its mechanism, so it was renamed.
#
# IT RUNS THE SHIPPED SUGGESTER over a purpose-built tree rather than grepping the script's source.
# Grepping the source would pass on a script that assembles a banned word at runtime, and would
# fail on one that merely documents the ban in a comment. Both are wrong in the expensive direction.
#
# Verdicts: 0 pass, 1 the repository is wrong, 3 the check could not run.
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

SUGGEST=skills/project-lifecycle/hooks/plc-careful-suggest.sh
DATA=skills/project-lifecycle/references/careful-paths.md

[ -r "$SUGGEST" ] || { printf 'COULD NOT RUN: %s is not readable\n' "$SUGGEST" >&2; exit 3; }
[ -r "$DATA" ]    || { printf 'COULD NOT RUN: %s is not readable\n' "$DATA" >&2; exit 3; }
command -v git >/dev/null 2>&1 || { printf 'COULD NOT RUN: git is not on PATH\n' >&2; exit 3; }

# Deliberately including the ones an author reaches for first when trying to be helpful.
BANNED="sensitive risky dangerous insecure unsafe critical suspicious probably likely"

# A GIT HOOK RUNS WITH GIT_DIR SET, AND GIT_DIR OVERRIDES `-C` (proved, not
# guessed). This script only READS from its fixture, but a read against the wrong repository is
# just a quieter version of the same defect: it would answer about the real tree and call that a
# pass. Cleared here for the same reason it is cleared where a commit happens.
# Clear the WHOLE GIT_* family, not a list of six names. An enumerated list is a claim that git
# will never add another variable able to redirect a read or a write, and nothing announces the
# day that stops being true -- a claim wider than its mechanism. The python
# fixtures already filter by prefix (`not k.startswith("GIT_")`); this is parity with them.
#
# Measured, with a probe first proven able to detect a real bypass (removing the protection moves
# a decoy repository's HEAD): with GIT_DIR, GIT_CONFIG_COUNT/core.worktree and GIT_NAMESPACE all
# poisoned at once, this leaves zero GIT_* set and the decoy's HEAD does not move.
#
# The six-name form this replaces was NOT found exploitable -- five injection vectors were tried
# and none reached the decoy. It is replaced because its correctness depends on a future git
# release, not because a bypass was demonstrated.
for _gv in $(env | sed -n 's/^\(GIT_[A-Za-z0-9_]*\)=.*/\1/p'); do unset "$_gv"; done
unset _gv

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
git init -q "$tmp/p"
printf '# p\n' > "$tmp/p/CLAUDE.md"
# A tree chosen to make the suggester talk as much as possible: several matches, several shapes.
mkdir -p "$tmp/p/src/auth" "$tmp/p/src/billing" "$tmp/p/config" "$tmp/p/tests/fixtures"
printf 'x\n' > "$tmp/p/src/auth/session.ts"
printf 'x\n' > "$tmp/p/src/billing/stripe.ts"
printf 'x\n' > "$tmp/p/config/secret.env"
printf 'x\n' > "$tmp/p/tests/fixtures/password_generator.py"
printf 'x\n' > "$tmp/p/login.ts"

if ! out="$(/bin/bash "$SUGGEST" --repo "$tmp/p" --claude-md "$tmp/p/CLAUDE.md" --data "$DATA" 2>"$tmp/err")"; then
  printf 'FAIL the shipped suggester failed to run:\n' >&2
  sed 's/^/  /' "$tmp/err" >&2
  exit 1
fi

# An empty scope is not a pass. If this tree produced nothing, the check verified nothing, and a
# green here would be the vacuous kind.
case "$out" in
  no-candidates*|"")
    printf 'FAIL the probe tree produced no reasons, so nothing was checked -- an empty scope is not a pass\n' >&2
    exit 1 ;;
esac

fail=0
n=0
while IFS= read -r line; do
  [ -n "$line" ] || continue
  n=$((n + 1))
  reason="${line#*	}"
  low="$(printf '%s' "$reason" | tr '[:upper:]' '[:lower:]')"
  for w in $BANNED; do
    case " $low " in
      *" $w "*|*" $w."*|*" $w,"*)
        printf 'FAIL a reason infers rather than states: %s\n' "$reason" >&2
        fail=1 ;;
    esac
  done
done <<EOF
$out
EOF

[ "$fail" = 0 ] || exit 1
printf 'ok  %s reason(s) carry none of the %s inference words -- this is the floor of the fact-only rule, not the rule\n' \
  "$n" "$(printf '%s' "$BANNED" | wc -w | tr -d ' ')"
