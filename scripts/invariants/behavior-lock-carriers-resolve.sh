#!/usr/bin/env bash
# Invariant (close-gate check #8): every behavior-lock row THIS BRANCH added or
# changed names a carrier that resolves to a real test.
#
# This is the hard-fail heart of the Behavior Lock. A row can claim a test proves
# a behavior while nothing does -- a dangling carrier. The gate rejects that, and it is never
# warn-only: a carrier that resolves to nothing is red, not a warning.
#
# Scope = rows this branch touched, not the whole live registry. A row byte-identical to the
# merge-base version is skipped. Checking every live row instead would turn the gate red on a
# branch that merely renamed a test an UNRELATED row happens to carry -- the "blocks every push"
# failure the closure invariant's criterion 3 was narrowed to avoid. The base is
# `git merge-base HEAD main`, not main's tip: this workspace runs two sessions and an advancing
# tip would fail a perfectly legal older branch.
#
# jq-only envelope: no jq, no python3 (CLAUDE.md).
#
# Test seams (so the suite can drive it without git):
#   PLC_BEHAVIOR_LOCK       -- registry path            (default .claude/behavior-lock.tsv)
#   PLC_BEHAVIOR_LOCK_BASE  -- a file holding base content; when set, used instead of git
#   PLC_BEHAVIOR_LOCK_ROOT  -- root to resolve carriers against (default .)

set -uo pipefail

NAME="behavior-lock-carriers-resolve"
LOG="${PLC_BEHAVIOR_LOCK:-.claude/behavior-lock.tsv}"
ROOT="${PLC_BEHAVIOR_LOCK_ROOT:-.}"
PARSER="$(dirname "$0")/../behavior-lock.sh"

pass() { printf 'PASS %s: %s\n' "$NAME" "$1"; exit 0; }
fail() { printf 'FAIL %s: %s\n' "$NAME" "$1"; exit 1; }

# No registry at all is not a violation -- the file only exists once a phase starts locking
# behaviors. Stated explicitly, never a silent no-op.
[ -f "$LOG" ] || pass "no behavior-lock registry in this tree -- nothing to check"
# A missing parser is a HARD failure, not a skip: a guard whose dependency can vanish without a
# sound is worse than no guard (the closure invariant paid for this lesson at p38).
[ -f "$PARSER" ] || fail "parser missing at $PARSER -- cannot resolve carriers without it"

BASE_CONTENT="$(mktemp)"; trap 'rm -f "$BASE_CONTENT"' EXIT
if [ -n "${PLC_BEHAVIOR_LOCK_BASE:-}" ]; then
  [ -f "$PLC_BEHAVIOR_LOCK_BASE" ] && cat "$PLC_BEHAVIOR_LOCK_BASE" > "$BASE_CONTENT"
else
  base="$(git merge-base HEAD main 2>/dev/null || true)"
  [ -n "$base" ] && { git show "$base:$LOG" 2>/dev/null > "$BASE_CONTENT" || : > "$BASE_CONTENT"; }
fi

n=0; checked=0; rc=0
while IFS= read -r line; do
  case "$line" in ''|'#'*) continue ;; esac
  n=$((n + 1))
  # A row present verbatim in the base was not touched by this branch -- out of scope.
  if grep -qxF -- "$line" "$BASE_CONTENT"; then continue; fi
  checked=$((checked + 1))
  id="$(printf '%s' "$line" | cut -f1)"
  carrier="$(printf '%s' "$line" | cut -f4)"
  if ! /bin/bash "$PARSER" --resolve "$carrier" "$ROOT" >/dev/null 2>&1; then
    printf 'FAIL %s: %s carrier does not resolve to a real test: %s\n' "$NAME" "$id" "$carrier"
    rc=1
  fi
done < "$LOG"

[ "$rc" -eq 0 ] || exit 1
[ "$checked" -gt 0 ] \
  || pass "no behavior rows added or changed on this branch ($n live row(s), all unchanged from base)"
pass "resolved every carrier for $checked behavior row(s) this branch touched (of $n live)"
