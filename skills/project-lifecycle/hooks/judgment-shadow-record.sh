#!/bin/sh
# project-lifecycle -- PreToolUse:Bash|Edit|Write SHADOW-MODE recorder.
# Phase-1 shadow: this hook RECORDS what the judgment routing WOULD do for each declared decision
# and does NOTHING else. It NEVER blocks a tool (it always exits 0), never hides a batch line,
# never releases a human check. The only real block in phase 1 is judgment-action-gate.sh.
#
# Input: the standard PreToolUse JSON. Declared decisions ride in `.tool_input.judgment`, either
# one object or an array, each {id, what, authorization_tier, decision_type}. A declaration that is
# missing a field, or whose decision_type is outside the set below, is skipped (never guessed).
#
# Output (LOAD-BEARING INTERFACE, consumed by the Task 4 evaluator): one JSONL line per decision,
# appended to ${TMPDIR:-/tmp}/plc-judgment-shadow.$SID.jsonl with exactly these fields:
#   {id, what, authorization_tier, decision_type, would_action, would_time}
#   would_action in {shadow-record, confirm-before-build, hard-stop, do-and-report}
#   would_time   in {before-build, at-finish, none}
# Nothing acts on these lines in phase 1.
#
# Decision-type -> routing map (the product owner's call; decision_type is exactly the four-value
# set in scripts/judgment_corpus_schema.py DECISION_TYPES, and the test imports it from there):
#   taste            -> shadow-record        at-finish
#   product-boundary -> confirm-before-build before-build
#   side-effect      -> hard-stop            none   (immediate; cross-checked against the factual
#                                                    trigger in judgment-action-gate.sh by test)
#   mechanical       -> do-and-report        none
#
# When it cannot run (no jq / malformed input / no session_id) it says so with an honest `defer`
# (did NOT run, not a pass) and records nothing. jq + POSIX sh only; no network, ever.
# Global blast radius: additive, fail-open.

INPUT="$(cat 2>/dev/null || true)"

if ! command -v jq >/dev/null 2>&1; then
  printf '%s' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"defer","additionalContext":"UNVERIFIED (project-lifecycle judgment-shadow-record.sh) -- jq is not on PATH, so this hook parsed nothing and did NOT record any shadow decision. Shadow recording is not running while jq is missing. This is not a pass. The normal permission flow is untouched. To restore this layer, install jq."}}'
  exit 0
fi

TOOL="$(printf '%s' "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)"
case "$TOOL" in
  Bash|Edit|Write) ;;
  "")
    printf '%s' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"defer","additionalContext":"UNVERIFIED (project-lifecycle judgment-shadow-record.sh) -- could not parse tool input (malformed JSON or no tool_name), so this hook did NOT record any shadow decision for this call. This is not a pass. The normal permission flow is untouched."}}'
    exit 0 ;;
  *) exit 0 ;;
esac

SID="$(printf '%s' "$INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)"
if [ -z "$SID" ]; then
  printf '%s' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"defer","additionalContext":"UNVERIFIED (project-lifecycle judgment-shadow-record.sh) -- the hook input had no session_id, so it cannot key a per-session shadow log and did NOT record. This is not a pass. The normal permission flow is untouched."}}'
  exit 0
fi
SID="$(printf '%s' "$SID" | tr -c 'A-Za-z0-9_-' '_')"

# Valid decisions -> one compact line each, with the routing fields derived from decision_type.
LINES="$(printf '%s' "$INPUT" | jq -c '
  def ok: type == "string" and length > 0;
  def route:
    if   . == "taste"            then {would_action: "shadow-record",        would_time: "at-finish"}
    elif . == "product-boundary" then {would_action: "confirm-before-build", would_time: "before-build"}
    elif . == "side-effect"      then {would_action: "hard-stop",            would_time: "none"}
    elif . == "mechanical"       then {would_action: "do-and-report",        would_time: "none"}
    else empty end;
  (.tool_input.judgment // empty)
  | (if type == "array" then .[] else . end)
  | select(type == "object")
  | select((.id | ok) and (.what | ok) and (.authorization_tier | ok) and (.decision_type | ok))
  | {id, what, authorization_tier, decision_type} + (.decision_type | route)
' 2>/dev/null || true)"

[ -n "$LINES" ] || exit 0

# Append-only. A write failure (unwritable TMPDIR) must never break the call: subshell + || true.
( printf '%s\n' "$LINES" >>"${TMPDIR:-/tmp}/plc-judgment-shadow.$SID.jsonl" ) 2>/dev/null || true
exit 0
