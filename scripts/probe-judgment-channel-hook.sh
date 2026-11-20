#!/bin/sh
# probe-judgment-channel-hook.sh -- live probe for the PROVISIONAL declaration channel.
# QUESTION: does Claude Code pass an unknown `tool_input.judgment` key through to a PreToolUse
# hook (for Bash / Edit / Write), or strip it / reject the call?
# STATUS: NOT RUN. It needs a REAL Claude Code session with this hook wired, which means editing
# real settings; that was out of bounds for the build task. Until a human runs it, the recorder
# stays PROVISIONAL and inert (see references/judgment-gate.md).
#
# This hook only OBSERVES: it appends one line per call to ${PLC_PROBE_OUT:-/tmp/plc-judgment-probe.jsonl}
# with the tool name, the sorted tool_input keys, and whether `judgment` was present. Always exit 0.
#
# PROCEDURE (manual, in a throwaway session, with owner consent):
#   1. Add a PreToolUse hook (matcher "Bash|Edit|Write") whose command is this file's absolute path.
#      Prefer a project-local .claude/settings.local.json over the global settings; remove it after.
#   2. In that session, ask Claude to run a harmless Bash command and, in the SAME tool call, include
#      an extra input field  "judgment": {"id":"p1","what":"probe","authorization_tier":"asked","decision_type":"other"}
#      (Claude can only do this if the tool schema permits extra keys; note whether the call was
#      rejected or the key silently dropped -- both are findings.)
#   3. Read the output file. judgment_present=true  => channel passes through (record for that tool).
#      judgment_present=false with the call having succeeded => key stripped => channel DEAD.
#      Call rejected before the hook ran => no line at all => channel DEAD.
#   4. Repeat for Edit and Write; update the contract's PROVISIONAL note with the measured result.
INPUT="$(cat 2>/dev/null || true)"
OUT="${PLC_PROBE_OUT:-/tmp/plc-judgment-probe.jsonl}"
command -v jq >/dev/null 2>&1 || exit 0
printf '%s' "$INPUT" | jq -c '{tool: (.tool_name // null),
  tool_input_keys: ((.tool_input // {}) | keys),
  judgment_present: ((.tool_input // {}) | has("judgment"))}' >> "$OUT" 2>/dev/null || true
exit 0
