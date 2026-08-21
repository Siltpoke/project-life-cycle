#!/usr/bin/env bash
# skills/project-lifecycle/hooks/plc-kickoff-check.sh
#
# Validate one recorded start-of-work screen against the five rules in references/kickoff-confirmation.md, plus the conditional careful-round rule (rule 6).
#
# WHAT THIS CHECKS AND WHAT IT DOES NOT. It checks the RECORD -- the block written into the phase's
# Q&A log when the user tapped Start. Nothing here proves the screen was shown, or read. The record
# is what a later reader has, including the person deciding whether to merge, so it is the thing
# worth checking; saying so is better than letting a green line imply more.
#
# EVERY RULE FAILS WITH ITS OWN MESSAGE. A single "the screen is malformed" would tell the author
# nothing, and this file's whole value is that it names which rule broke.
#
# Envelope: bash + jq (jq only to read the declared mode set out of the mode document).
#
# Exit codes: 0 valid, 1 a rule failed (each named), 2 bad invocation, 3 could not run.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE_DOC="${PLC_MODE_DOC:-$HERE/../references/mode.md}"

die() { printf '%s\n' "$*" >&2; exit "${2:-2}"; }

# The banned words. Short, mechanical, and NOT a claim that the rest of the screen reads plainly --
# that judgement is not automatable and the reference document says so.
BANNED="cadence archetype oracle AC close-gate subagent validator"
NOT_FOR_FAST="logins-and-passwords taking-payments other-peoples-personal-details public-to-strangers"

fragment=""; story=""; phase=""
[ $# -ge 1 ] || die "usage: plc-kickoff-check.sh <fragment> --story <user-story.md> [--phase <token>]"
fragment="$1"; shift
while [ $# -gt 0 ]; do
  case "$1" in
    --story) [ $# -ge 2 ] || die "--story needs a path"; story="$2"; shift 2 ;;
    --phase) [ $# -ge 2 ] || die "--phase needs a token"; phase="$2"; shift 2 ;;
    *) die "unknown option: $1" ;;
  esac
done
[ -r "$fragment" ] || die "cannot read the recorded screen: $fragment"
[ -n "$story" ] && [ -r "$story" ] || die "cannot read the story: ${story:-<missing --story>}"
[ -r "$MODE_DOC" ] || die "cannot read the mode document: $MODE_DOC" 3

block="$(awk '
  /<!-- plc-kickoff:begin -->/ { inblk = 1; found++; next }
  /<!-- plc-kickoff:end -->/   { inblk = 0; next }
  inblk                        { print }
  END                          { if (found != 1) exit 9 }
' "$fragment")" || die "expected exactly one plc-kickoff block in $fragment" 1
[ -n "$block" ] || die "the plc-kickoff block is empty -- an empty block is not a recorded screen" 1

field() { printf '%s\n' "$block" | sed -n "s/^$1:[[:space:]]*//p" | head -1; }

fail=0
say() { printf 'FAIL %s\n' "$*" >&2; fail=1; }

# --- rule 1: no jargon, over the WHOLE recorded screen, header and prose alike -------------------
# Word-bounded: `AC` must not swallow `ACCESS`, and `oracle` must not be found inside `oracles`
# only by accident -- both directions were wrong in the first draft of this matcher.
screen="$(awk '/<!-- plc-kickoff:begin -->/,0' "$fragment")"
for w in $BANNED; do
  if printf '%s' "$screen" | /usr/bin/grep -qE "(^|[^A-Za-z0-9_-])$w([^A-Za-z0-9_-]|$)"; then
    say "rule 1 (no jargon): the recorded screen contains the banned term '$w'"
  fi
done

# --- rule 5: exactly the four declared not-for-fast items ---------------------------------------
nff="$(field not-for-fast)"
if [ -z "$nff" ]; then
  say "rule 5 (not-for-fast): the field is absent -- the four warnings are not optional"
else
  for item in $NOT_FOR_FAST; do
    case "$nff" in *"$item"*) ;; *) say "rule 5 (not-for-fast): missing '$item'" ;; esac
  done
  n=$(printf '%s' "$nff" | tr '|' '\n' | /usr/bin/grep -c '[^[:space:]]' || true)
  [ "$n" = 4 ] || say "rule 5 (not-for-fast): expected 4 items, found $n"
fi

# --- rule 2: the work-kind line carries a reason -------------------------------------------------
wk="$(field work-kind)"
if [ -z "$wk" ]; then
  say "rule 2 (work-kind): the field is absent -- the inference has no receiver without it"
else
  case "$wk" in
    *"because:"*)
      reason="${wk#*because:}"
      reason="${reason#"${reason%%[![:space:]]*}"}"
      [ -n "$reason" ] || say "rule 2 (work-kind): 'because:' is present but empty" ;;
    *) say "rule 2 (work-kind): no 'because:' -- an inference with no reason is an announcement" ;;
  esac
fi

# --- rule 4: nothing left unanswered -------------------------------------------------------------
ma="$(field must-answer)"
case "$ma" in
  "0 outstanding") ;;
  "") say "rule 4 (must-answer): the field is absent -- absence is not the same as zero" ;;
  *)  say "rule 4 (must-answer): '$ma' -- Start is unavailable while anything is outstanding" ;;
esac

# --- the mode line names a declared mode ---------------------------------------------------------
legal="$(awk '
  /<!-- plc-mode-map:begin -->/ { inblk = 1; next }
  /<!-- plc-mode-map:end -->/   { inblk = 0; next }
  inblk && /^```json$/          { infence = 1; next }
  inblk && /^```$/              { infence = 0; next }
  inblk && infence              { print }
' "$MODE_DOC" | jq -r '.modes[]?')"
[ -n "$legal" ] || die "no modes declared in $MODE_DOC" 3
m="$(field mode)"; m="${m%% *}"; m="${m%%|*}"
mode_line="$(field mode)"
if [ -z "$m" ]; then
  say "the mode line is absent -- it is the first line of the screen for a reason"
else
  # THE MODE LINE IS THE PROVENANCE LINE. If the two carried different
  # fields, "this tap confirmed the mode" would split from the record meant to prove it -- and the
  # kickoff check could pass while the phase record said nothing about a confirmation.
  case "$mode_line" in
    *"confirmed-at: kickoff"*) ;;
    *"confirmed-at:"*) say "the mode line records a confirmation that did not happen on this screen: $mode_line" ;;
    *) say "the mode line has no \`confirmed-at:\` -- this tap IS the mode confirmation and the record has to say so" ;;
  esac
  case "$mode_line" in
    *"source: project-default"*|*"source: override"*) ;;
    *) say "the mode line has no legal \`source:\` (project-default | override): $mode_line" ;;
  esac
  case $'\n'"$legal"$'\n' in
    *$'\n'"$m"$'\n'*) ;;
    *) say "mode '$m' is not a declared mode ($(printf '%s' "$legal" | tr '\n' ' '))" ;;
  esac
fi

# --- rule 3: every criterion, in the story's order -----------------------------------------------
[ -n "$phase" ] || phase="$(printf '%s\n' "$block" | sed -n 's/^criteria:[[:space:]]*\([A-Za-z0-9_.-]*\):AC.*/\1/p' | head -1)"
[ -n "$phase" ] || say "rule 3 (criteria): cannot determine the phase token; pass --phase"

if [ -n "$phase" ]; then
  # The story's declared set comes from the gate's own parser. Writing a second parser for the same
  # file is how two readings of one document start to disagree.
  if ! declared="$("$HERE/../../../scripts/ac-evidence.sh" parse-criteria "$story" "$phase" 2>/dev/null)"; then
    declared="$(/usr/bin/grep -oE "^- \*\*AC[0-9]+\*\* \{#$phase:AC[0-9]+\}" "$story" \
      | sed -E "s/.*\{#($phase:AC[0-9]+)\}/\1/")"
  fi
  [ -n "$declared" ] || die "could not read any criterion from $story" 3
  listed="$(field criteria | tr ' ' '\n' | /usr/bin/grep -E "^$phase:AC[0-9]+$" || true)"
  if [ -z "$listed" ]; then
    say "rule 3 (criteria): the field lists none -- a receiver that shows nothing is not a receiver"
  elif [ "$listed" != "$declared" ]; then
    n_d=$(printf '%s\n' "$declared" | wc -l | tr -d ' ')
    n_l=$(printf '%s\n' "$listed" | wc -l | tr -d ' ')
    if [ "$n_d" != "$n_l" ]; then
      say "rule 3 (criteria): the story declares $n_d, the screen lists $n_l -- all of them, not a summary"
    else
      say "rule 3 (criteria): same count, different order -- the screen must follow the story's order"
    fi
  fi
fi

# --- rule 6: the careful round, when it ran, states all four of its misses -------------
# CONDITIONAL BY DESIGN. The round only happens on a first `fast` run with nothing marked, so a
# screen without a `careful:` field is not in breach -- it is a screen where the round did not
# apply. Checking the four MARKERS rather than the prose is the same split the header already uses:
# the sentences are written in whatever language the user reads, the markers are the checkable part.
CAREFUL_MISSES="your-marking incomplete-ecosystems english-words path-not-intent"
careful_line="$(field careful)"
if [ -n "$careful_line" ]; then
  for m in $CAREFUL_MISSES; do
    case " $careful_line " in
      *" $m "*) ;;
      *) say "rule 6 (careful): the round ran but does not state the '$m' miss -- all four are required, because each is a different way this will miss something" ;;
    esac
  done
  case "$careful_line" in
    *proposed=*) ;;
    *) say "rule 6 (careful): no proposed= count -- 'it suggested nothing' and 'it was never run' must not read alike" ;;
  esac
  case "$careful_line" in
    *chosen=*) ;;
    *) say "rule 6 (careful): no chosen= count" ;;
  esac
fi

[ "$fail" = 0 ] || exit 1
printf 'ok  recorded start-of-work screen satisfies all five rules (%s criteria listed)%s\n' \
  "$(field criteria | tr ' ' '\n' | /usr/bin/grep -cE "^$phase:AC[0-9]+$" || true)" \
  "$([ -n "$careful_line" ] && printf ', plus the careful round and its four stated misses' || printf '; no careful round on this screen')"
