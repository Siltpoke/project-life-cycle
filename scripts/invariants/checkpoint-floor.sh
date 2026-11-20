#!/usr/bin/env bash
# Invariant `checkpoint-floor` (close-gate check #8 family): a MEDIUM/HIGH phase recorded
# its mid-phase PROGRESS checkpoint. It checks that the checkpoint was RECORDED -- never that the
# phase PAUSED for it. This fires once, at phase close; it is not a runtime block. A progress
# checkpoint is posted and work continues (references/checkpoint-modes.md); enforcement lives here,
# at close, so "inform, not gate" and "the gate enforces it" are both true.
#
# effective tier = max(objective careful-paths floor, declared tier) -- computed exactly as
# risk-tier-evidence-floor.sh does, reusing the same seams and the canonical plc-careful-check.sh
# detector (never a second copy of its logic). There is no second risk notion.
#
# Floor enforced per effective tier:
#   LOW     -> nothing (LOW is never jammed into mid-phase reporting).
#   MEDIUM  -> the phase qa-log fragment carries a `^checkpoint: mid-phase` marker line.
#   HIGH    -> same requirement as MEDIUM at this layer.
#
# Waiver escape: a `SKIP: checkpoint-floor` line in this branch's journal satisfies the
# floor and is recorded in git (attributable by commit) -- the same controlled-waiver shape as M2's
# `SKIP: risk-floor`.
#
# The gate keys only on the marker line; it does NOT grade the checkpoint's prose (grading prose is
# the hard AI problem PLC does not claim). Never warn-only: an unmet, unwaived floor is RED (exit 1).
#
# Test seams (drive it without git or jq):
#   PLC_CHECKPOINT_FRAGMENT  qa-log fragment holding `risk:` + the checkpoint marker (default: this branch's qa-log.d)
#   PLC_CHECKPOINT_FLOOR     override objective floor: LOW|MEDIUM                      (default: computed via plc-careful-check)
#   PLC_CHECKPOINT_JOURNAL   file to scan for the SKIP waiver                          (default: this branch's journal.d)
#
# jq envelope: this script is bash/grep/awk; it may invoke plc-careful-check.sh (bash+jq). No python3.

set -uo pipefail

NAME="checkpoint-floor"
HERE="$(cd "$(dirname "$0")" && pwd)"
RISK_TIER="$HERE/../risk-tier.sh"

pass() { printf 'PASS %s: %s\n' "$NAME" "$1"; exit 0; }
fail() { printf 'FAIL %s: %s\n' "$NAME" "$1"; exit 1; }

rank() { case "$1" in LOW) echo 0 ;; MEDIUM) echo 1 ;; HIGH) echo 2 ;; *) echo -1 ;; esac; }

[ -f "$RISK_TIER" ] || fail "parser missing at $RISK_TIER -- cannot resolve the declared tier"

# --- locate this branch's qa-log fragment (declaration + checkpoint marker) + journal (waiver) ----
find_fragment() {
  [ -n "${PLC_CHECKPOINT_FRAGMENT:-}" ] && { printf '%s' "$PLC_CHECKPOINT_FRAGMENT"; return; }
  ls -1 docs/qa-log.d/*.md 2>/dev/null | sort | tail -1
}
find_journal() {
  [ -n "${PLC_CHECKPOINT_JOURNAL:-}" ] && { printf '%s' "$PLC_CHECKPOINT_JOURNAL"; return; }
  ls -1 docs/journal.d/*.md 2>/dev/null | sort | tail -1
}

FRAGMENT="$(find_fragment)"
JOURNAL="$(find_journal)"

# --- declared tier --------------------------------------------------------------------------------
declared=""
if [ -n "$FRAGMENT" ] && [ -f "$FRAGMENT" ]; then
  declared="$(/bin/bash "$RISK_TIER" --resolve "$FRAGMENT" 2>/dev/null || true)"
fi

# --- objective careful-paths floor ----------------------------------------------------------------
floor="LOW"
if [ -n "${PLC_CHECKPOINT_FLOOR:-}" ]; then
  floor="$PLC_CHECKPOINT_FLOOR"
else
  CHECK="skills/project-lifecycle/hooks/plc-careful-check.sh"
  DATA="skills/project-lifecycle/references/careful-paths.md"
  if [ -r "$CHECK" ] && [ -r "$DATA" ] && [ -r CLAUDE.md ] && command -v jq >/dev/null 2>&1; then
    hit="$(/bin/bash "$CHECK" --claude-md CLAUDE.md --repo . --data "$DATA" 2>/dev/null || true)"
    case "$hit" in
      no-hit*|"") floor="LOW" ;;
      *)          floor="MEDIUM" ;;
    esac
  else
    printf 'note %s: careful-paths detector unavailable; objective floor assumed LOW\n' "$NAME" >&2
    floor="LOW"
  fi
fi

# --- effective tier = max(floor, declared) --------------------------------------------------------
effective="$floor"
note=""
if [ -n "$declared" ]; then
  if [ "$(rank "$declared")" -ge "$(rank "$floor")" ]; then
    effective="$declared"
  else
    effective="$floor"
    note=" (declared $declared is below the objective floor $floor -- the floor wins)"
  fi
fi

# --- is a mid-phase checkpoint recorded in the fragment? ------------------------------------------
has_checkpoint() {
  [ -n "$FRAGMENT" ] && [ -f "$FRAGMENT" ] || return 1
  grep -qE '^checkpoint: mid-phase' "$FRAGMENT"
}

# --- waiver (checked only when the floor would otherwise be unmet) --------------------------------
waived() {
  [ -n "$JOURNAL" ] && [ -f "$JOURNAL" ] || return 1
  grep -qE '^SKIP: checkpoint-floor' "$JOURNAL"
}

# --- enforce the effective floor ------------------------------------------------------------------
case "$effective" in
  LOW)
    pass "effective tier LOW -- no mid-phase progress checkpoint required${note}"
    ;;
  MEDIUM|HIGH)
    if has_checkpoint; then
      pass "effective tier $effective -- a mid-phase checkpoint is recorded in $FRAGMENT${note}"
    fi
    if waived; then
      pass "effective tier $effective -- checkpoint floor waived by a SKIP: checkpoint-floor line in $JOURNAL${note}"
    fi
    fail "effective tier $effective requires a mid-phase progress checkpoint recorded in the qa-log fragment (a 'checkpoint: mid-phase | risk: <tier>' marker line), and none is present; post the checkpoint and record it (references/checkpoint-modes.md), or write a 'SKIP: checkpoint-floor -- <reason>' line in the journal${note}"
    ;;
  *)
    fail "could not determine an effective tier (declared='$declared', floor='$floor')"
    ;;
esac
