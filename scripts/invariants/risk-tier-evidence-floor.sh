#!/usr/bin/env bash
# Invariant `risk-tier-evidence-floor` (close-gate check #8 family): the evidence on this
# branch matches the EFFECTIVE risk tier -- never that the declared tier is "correct".
#
# effective tier = max(objective careful-paths floor, declared tier):
#   - objective floor: a careful-paths hit forces MEDIUM; no hit -> LOW. Computed by invoking the
#     canonical detector plc-careful-check.sh, never a second copy of its logic.
#   - declared tier:  scripts/risk-tier.sh --resolve <fragment> (fail-safe-to-HIGH on malformed,
#     empty on absent). A declaration cannot drop the tier below the objective floor -- declaring
#     LOW under a hit does not escape MEDIUM; the floor wins and the message says so.
#
# Evidence floor enforced per effective tier:
#   LOW     -> nothing.
#   MEDIUM  -> >=1 behavior-lock row this branch added/changed (merge-base scoped, like
#              behavior-lock-carriers-resolve). Carrier resolution is that other invariant's job.
#   HIGH    -> MEDIUM's requirement AND >=1 of those rows has a RECORDED BASELINE -- both a
#              `before` and an `after` row in .claude/behavior-baseline.tsv. The HIGH
#              delta that is machine-checkable is that the characterization run actually happened,
#              not merely that behaviors were listed.
#
# Waiver escape: a `SKIP: risk-floor` line in this branch's journal satisfies the floor
# and is recorded in git (attributable by commit) -- the controlled-waiver pattern. Block-everything
# gates get bypassed; a gate with a written, attributable exception does not have to.
#
# Never warn-only: an unmet, unwaived floor is RED (exit 1).
#
# Test seams (drive it without git or jq):
#   PLC_RISK_FRAGMENT   qa-log fragment holding the `risk:` line   (default: this branch's qa-log.d)
#   PLC_RISK_FLOOR      override objective floor: LOW|MEDIUM        (default: computed via plc-careful-check)
#   PLC_RISK_LOCK       behavior-lock.tsv path                     (default .claude/behavior-lock.tsv)
#   PLC_RISK_LOCK_BASE  file with base registry content            (default: git merge-base)
#   PLC_RISK_JOURNAL    file to scan for the SKIP waiver           (default: this branch's journal.d)
#   PLC_RISK_BASELINE   behavior-baseline.tsv path                 (default .claude/behavior-baseline.tsv)
#
# jq envelope: this script is bash/grep/awk; it may invoke plc-careful-check.sh (bash+jq). No python3.

set -uo pipefail

NAME="risk-tier-evidence-floor"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
RISK_TIER="$HERE/../risk-tier.sh"

LOCK="${PLC_RISK_LOCK:-.claude/behavior-lock.tsv}"
BASELINE="${PLC_RISK_BASELINE:-.claude/behavior-baseline.tsv}"

pass() { printf 'PASS %s: %s\n' "$NAME" "$1"; exit 0; }
fail() { printf 'FAIL %s: %s\n' "$NAME" "$1"; exit 1; }

rank() { case "$1" in LOW) echo 0 ;; MEDIUM) echo 1 ;; HIGH) echo 2 ;; *) echo -1 ;; esac; }

[ -f "$RISK_TIER" ] || fail "parser missing at $RISK_TIER -- cannot resolve the declared tier"

# --- locate this branch's qa-log fragment (the declaration) + journal (the waiver) -------------
find_fragment() {
  [ -n "${PLC_RISK_FRAGMENT:-}" ] && { printf '%s' "$PLC_RISK_FRAGMENT"; return; }
  ls -1 docs/qa-log.d/*.md 2>/dev/null | sort | tail -1
}
find_journal() {
  [ -n "${PLC_RISK_JOURNAL:-}" ] && { printf '%s' "$PLC_RISK_JOURNAL"; return; }
  ls -1 docs/journal.d/*.md 2>/dev/null | sort | tail -1
}

FRAGMENT="$(find_fragment)"
JOURNAL="$(find_journal)"

# --- declared tier -----------------------------------------------------------------------------
declared=""
if [ -n "$FRAGMENT" ] && [ -f "$FRAGMENT" ]; then
  declared="$(/bin/bash "$RISK_TIER" --resolve "$FRAGMENT" 2>/dev/null || true)"
fi

# --- objective careful-paths floor -------------------------------------------------------------
floor="LOW"
if [ -n "${PLC_RISK_FLOOR:-}" ]; then
  floor="$PLC_RISK_FLOOR"
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
    # The detector could not run. Do NOT jam: fall back to LOW and say so. The
    # careful-check-reads-worktree invariant separately guards that the detector works.
    printf 'note %s: careful-paths detector unavailable; objective floor assumed LOW\n' "$NAME" >&2
    floor="LOW"
  fi
fi

# --- effective tier = max(floor, declared) -----------------------------------------------------
effective="$floor"
note=""
if [ -n "$declared" ]; then
  if [ "$(rank "$declared")" -ge "$(rank "$floor")" ]; then
    effective="$declared"
  else
    effective="$floor"
    note=" (declared $declared is below the objective floor $floor -- the floor wins; a careful-paths hit cannot be declared away)"
  fi
fi

# --- waiver (checked only when a floor would otherwise be unmet) --------------------------------
waived() {
  [ -n "$JOURNAL" ] && [ -f "$JOURNAL" ] || return 1
  grep -qE '^SKIP: risk-floor' "$JOURNAL"
}

# --- behavior-lock rows this branch added/changed (merge-base scoped): print their ids ---------
touched_ids() {
  [ -f "$LOCK" ] || return 0
  local base; base="$(mktemp)"
  if [ -n "${PLC_RISK_LOCK_BASE:-}" ]; then
    [ -f "$PLC_RISK_LOCK_BASE" ] && cat "$PLC_RISK_LOCK_BASE" > "$base"
  else
    local mb; mb="$(git merge-base HEAD main 2>/dev/null || true)"
    [ -n "$mb" ] && { git show "$mb:$LOCK" 2>/dev/null > "$base" || : > "$base"; }
  fi
  local line
  while IFS= read -r line; do
    case "$line" in ''|'#'*) continue ;; esac
    grep -qxF -- "$line" "$base" && continue
    printf '%s\n' "$line" | cut -f1
  done < "$LOCK"
  rm -f "$base"
}

# --- does any of the given ids (stdin, one per line) have BOTH a before and an after baseline? --
any_recorded_baseline() {
  [ -f "$BASELINE" ] || return 1
  local id
  while IFS= read -r id; do
    [ -n "$id" ] || continue
    if awk -F'\t' -v id="$id" \
        '$1==id && $2=="before"{b=1} $1==id && $2=="after"{a=1} END{exit !(a && b)}' "$BASELINE"; then
      return 0
    fi
  done
  return 1
}

# --- enforce the effective floor ---------------------------------------------------------------
IDS="$(touched_ids)"
nrows=0
[ -n "$IDS" ] && nrows="$(printf '%s\n' "$IDS" | grep -c .)"

case "$effective" in
  LOW)
    pass "effective tier LOW -- no behavior lock required${note}"
    ;;
  MEDIUM)
    if [ "$nrows" -ge 1 ]; then
      pass "effective tier MEDIUM -- $nrows behavior-lock row(s) added/changed on this branch${note}"
    fi
    if waived; then
      pass "effective tier MEDIUM -- floor waived by a SKIP: risk-floor line in $JOURNAL${note}"
    fi
    fail "effective tier MEDIUM requires at least one behavior-lock row on this branch, and none was added/changed; lock the at-risk behavior, or write a 'SKIP: risk-floor -- <reason>' line in the journal${note}"
    ;;
  HIGH)
    if [ "$nrows" -ge 1 ] && printf '%s\n' "$IDS" | any_recorded_baseline; then
      pass "effective tier HIGH -- $nrows behavior-lock row(s) on this branch, at least one with a recorded before+after baseline${note}"
    fi
    if waived; then
      pass "effective tier HIGH -- floor waived by a SKIP: risk-floor line in $JOURNAL${note}"
    fi
    if [ "$nrows" -lt 1 ]; then
      fail "effective tier HIGH requires at least one behavior-lock row on this branch (and a recorded baseline), and none was added/changed; lock the at-risk behavior, or write a 'SKIP: risk-floor -- <reason>' line in the journal${note}"
    fi
    fail "effective tier HIGH requires a RECORDED BASELINE (a before+after in $BASELINE) for at least one of this branch's behavior-lock rows, and none has one; run scripts/behavior-baseline.sh --record for a locked row, or write a 'SKIP: risk-floor -- <reason>' line in the journal${note}"
    ;;
  *)
    fail "could not determine an effective tier (declared='$declared', floor='$floor')"
    ;;
esac
