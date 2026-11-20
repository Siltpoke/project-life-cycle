#!/usr/bin/env bash
# Invariant `protected-behavior-change` (close-gate check #8 family): if this branch CHANGED
# the proof of a PRESERVE-locked behavior, it showed the behavior still holds.
#
# M1's `behavior-lock-carriers-resolve` checks a carrier still RESOLVES (the file exists, the named
# test is present). It does NOT notice when the carrier's CONTENT changed -- and editing the test that
# PROVES a locked behavior is exactly how a protected behavior gets altered silently. This invariant
# closes that gap: for each PRESERVE row whose carrier FILE this branch's diff touched, it requires a
# recorded baseline transition (a `before` AND an `after` in .claude/behavior-baseline.tsv) for that
# row -- i.e. you changed the proof, so a re-run on record shows the behavior still holds.
#
# A touched PRESERVE carrier with no recorded baseline is RED, UNLESS this branch's journal carries a
# `SKIP: protected-change -- <reason>` waiver (in git, attributable by commit). Never warn-only.
#
# Scope: merge-base `HEAD main`, like behavior-lock-carriers-resolve. CANNOT-RUN (exit 3) on a broken
# read, never a silent pass.
#
# HONEST BOUNDARY: this keys on the carrier FILE changing, not on semantic behavior diffing. A behavior
# changed while its carrier file stays byte-identical is NOT caught -- the same shape as M1's "does not
# find every risky change".
#
# Test seams: PLC_PROTCHG_LOCK / PLC_PROTCHG_BASELINE / PLC_PROTCHG_JOURNAL override the files;
# PLC_PROTCHG_TOUCHED (newline-separated paths) overrides the branch-touched file list so tests drive
# it without git.
#
# ENVELOPE: bash + git + grep/awk. No python3, no jq.

set -uo pipefail

NAME="protected-behavior-change"
LOCK="${PLC_PROTCHG_LOCK:-.claude/behavior-lock.tsv}"
BASELINE="${PLC_PROTCHG_BASELINE:-.claude/behavior-baseline.tsv}"

CANNOT_RUN_RC=3
cannot_run() { printf 'CANNOT-RUN[%s] %s\n' "$1" "$2" >&2; exit "$CANNOT_RUN_RC"; }
pass()       { printf 'PASS %s: %s\n' "$NAME" "$1"; exit 0; }
fail()       { printf 'FAIL %s: %s\n' "$NAME" "$1" >&2; exit 1; }

# No registry, or an empty one, is a PASS that says so (an adopter with no locks owes nothing).
if [ ! -f "$LOCK" ]; then
  pass "no behavior-lock registry at $LOCK -- nothing to protect"
fi

# --- this branch's touched files -----------------------------------------------------------------
touched_files() {
  if [ -n "${PLC_PROTCHG_TOUCHED:-}" ]; then
    printf '%s\n' "$PLC_PROTCHG_TOUCHED"
    return 0
  fi
  command -v git >/dev/null 2>&1 || return 1
  # Base against the ORIGIN ref, never the local `main` -- in a bare-repo worktree the local main ref
  # lags origin/main (core.bare; memory core-bare-true-read-origin-main), and here the over-count is
  # RESTRICTIVE (an already-merged file would look touched and demand a baseline it never needed), a
  # FALSE RED, not the permissive over-count the risk-tier floor tolerates. Same fallback chain as
  # growth-declares-a-deletion.
  local mb
  mb="$(git merge-base origin/HEAD HEAD 2>/dev/null || git merge-base origin/main HEAD 2>/dev/null || true)"
  [ -n "$mb" ] || return 1
  # --diff-filter=M: MODIFIED carriers only -- a carrier that EXISTED at the base and changed is a
  # changed PROTECTION; a newly-ADDED carrier is a NEW behavior (na->pass), not a changed protection,
  # so it owes no before-baseline here. A DELETED carrier is M1's behavior-lock-carriers-resolve's job.
  git diff --name-only --diff-filter=M "$mb"..HEAD 2>/dev/null
}

TOUCHED="$(touched_files)" || cannot_run "no-diff" "cannot compute the branch-touched file set (no merge base / no git)"

is_touched() {  # $1 = file path
  printf '%s\n' "$TOUCHED" | /usr/bin/grep -qxF -- "$1"
}

# --- does row id have BOTH a before and an after baseline? ----------------------------------------
has_baseline() {  # $1 = id
  [ -f "$BASELINE" ] || return 1
  awk -F'\t' -v id="$1" \
    '$1==id && $2=="before"{b=1} $1==id && $2=="after"{a=1} END{exit !(a && b)}' "$BASELINE"
}

# --- waiver --------------------------------------------------------------------------------------
waived() {
  local jr="${PLC_PROTCHG_JOURNAL:-}"
  if [ -z "$jr" ]; then
    jr="$(ls -1 docs/journal.d/*.md 2>/dev/null | sort | tail -1)"
  fi
  [ -n "$jr" ] && [ -f "$jr" ] || return 1
  /usr/bin/grep -qE '^SKIP: protected-change' "$jr"
}

# --- walk the PRESERVE rows ----------------------------------------------------------------------
unmet=""
while IFS=$'\t' read -r id class behavior carrier why; do
  case "$id" in ''|'#'*) continue ;; esac
  [ "$class" = "PRESERVE" ] || continue
  [ -n "$carrier" ] || continue
  file="${carrier%%::*}"
  [ -n "$file" ] || continue
  is_touched "$file" || continue
  # the proof of a PRESERVE behavior changed on this branch -> require a recorded baseline
  if ! has_baseline "$id"; then
    unmet="$unmet $id($file)"
  fi
done < "$LOCK"

if [ -z "$unmet" ]; then
  pass "no PRESERVE carrier changed on this branch without a recorded baseline"
fi

if waived; then
  pass "a PRESERVE carrier changed without a recorded baseline ($unmet) but a SKIP: protected-change waiver is recorded"
fi

fail "this branch changed the carrier of a PRESERVE-locked behavior without a recorded baseline transition:${unmet}. Re-run the characterization baseline (scripts/behavior-baseline.sh --record <id> before|after ...) to show the protected behavior still holds, or write a 'SKIP: protected-change -- <reason>' line in the journal."
