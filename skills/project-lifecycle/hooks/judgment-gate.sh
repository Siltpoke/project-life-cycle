#!/bin/sh
# project-lifecycle -- PreToolUse:Edit|Write first-edit judgment gate.
# On a session's FIRST Edit/Write, block once (exit 2) with a reason that points the AI at
# references/judgment-gate.md; a per-session marker lets every later edit through. A new
# session_id (e.g. after /clear) means a new marker path, so the gate re-fires by design.
# Mirrors guard.sh mechanics: jq + POSIX sh, exit 2 = block with stderr reason.
# Contract text (A-1..A-4) lives in the reference, not here.

INPUT="$(cat 2>/dev/null || true)"

# jq absent: say so, honestly. NOT a pass and NOT a block (same shape as guard.sh).
# Payload is a fixed literal; nothing from $INPUT is interpolated.
if ! command -v jq >/dev/null 2>&1; then
  printf '%s' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"defer","additionalContext":"UNVERIFIED (project-lifecycle judgment-gate.sh) -- jq is not on PATH, so this hook parsed nothing and did NOT check whether this is the first edit of the session. The first-edit judgment gate (skills/project-lifecycle/references/judgment-gate.md) is not enforcing while jq is missing. This is not a pass. The normal permission flow is untouched. To restore this layer, install jq."}}'
  exit 0
fi

TOOL="$(printf '%s' "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)"
case "$TOOL" in
  Edit|Write) ;;
  "")
    # Malformed JSON / no tool_name: parsed nothing, so say so (defer, not a pass, not a block).
    printf '%s' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"defer","additionalContext":"UNVERIFIED (project-lifecycle judgment-gate.sh) -- could not parse tool input (malformed JSON or no tool_name), so this hook did NOT check whether this is the first edit of the session. The first-edit judgment gate is not enforcing for this call. This is not a pass. The normal permission flow is untouched."}}'
    exit 0 ;;
  *) exit 0 ;;
esac

SID="$(printf '%s' "$INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)"
# No session_id => cannot key a per-session marker. A shared marker would silently suppress every
# later id-less session, so say so honestly (defer, not a pass, not a block).
if [ -z "$SID" ]; then
  printf '%s' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"defer","additionalContext":"UNVERIFIED (project-lifecycle judgment-gate.sh) -- the hook input had no session_id, so it cannot track whether this is the first edit of the session and did NOT check. The first-edit judgment gate (skills/project-lifecycle/references/judgment-gate.md) is not enforcing for this call. This is not a pass. The normal permission flow is untouched."}}'
  exit 0
fi
SID="$(printf '%s' "$SID" | tr -c 'A-Za-z0-9_-' '_')"

MARKER="${TMPDIR:-/tmp}/plc-judgment-gate.$SID"
[ -e "$MARKER" ] && exit 0

# Set the marker BEFORE blocking: the retry after this deny must pass.
# NB: wrap in a subshell. `:` is a POSIX *special* built-in, and a redirection
# failure on a special built-in is FATAL in a POSIX shell (dash = Ubuntu /bin/sh):
# it exits the shell (status 2) before `|| true` can run, so an unwritable TMPDIR
# would hard-block forever instead of failing open. bash-as-/bin/sh (macOS) does not,
# which is why this only surfaced in CI. The subshell contains the fatal exit.
( : >"$MARKER" ) 2>/dev/null || true
# Marker not writable (read-only/full TMPDIR): fail OPEN, else every edit would be denied forever.
if [ ! -e "$MARKER" ]; then
  printf '%s' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"defer","additionalContext":"UNVERIFIED (project-lifecycle judgment-gate.sh) -- could not write the once-per-session marker (TMPDIR not writable), so the first-edit judgment gate did NOT run and is not enforcing. This is not a pass. The normal permission flow is untouched."}}'
  exit 0
fi

# Resolve the contract as an ABSOLUTE path from the hook's OWN location (never cwd): the installed
# layout keeps a copy beside the hook; the in-repo layout has it at ../references/.
HOOK_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd -P)"
CONTRACT=""
for c in "$HOOK_DIR/plc-judgment-gate.contract.md" "$HOOK_DIR/../references/judgment-gate.md"; do
  if [ -n "$HOOK_DIR" ] && [ -f "$c" ]; then
    CONTRACT="$(cd "$(dirname "$c")" && pwd -P)/$(basename "$c")"
    break
  fi
done
[ -n "$CONTRACT" ] || CONTRACT="skills/project-lifecycle/references/judgment-gate.md (not found beside the hook; the gist below is self-sufficient)"

{
  printf '[project-lifecycle] First edit of this session -- paused once for a judgment check.\n'
  printf 'Read %s now. Run the A-2 self-check\n' "$CONTRACT"
  printf '(does this edit hide a judgment call the human has not decided?) and do the A-1 surfacing.\n'
  printf '\n'
  printf 'Attended (a human is present): put the options + tradeoffs in plain words in chat and wait for the human to pick.\n'
  printf 'Unattended / subagent: write the judgment to a file, skip that one product-facing decision, do everything else, never hang.\n'
  printf 'No signal tells this hook which case you are in; pick the branch that matches.\n'
  printf 'This gate fires once per session; your retry of the edit will go through.\n'
} >&2
exit 2
