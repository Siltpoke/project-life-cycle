#!/usr/bin/env bash
# project-lifecycle — TaskCreate-first guard (Definition of Done, forcing function 1).
# The skill mandates "materialize the steps as a task list — FIRST action on every
# invocation, before any work", but prose alone is model self-discipline — observed
# skipping. This hook moves the rule to platform enforcement.
#
# jq-only: no python3 (repo CLAUDE.md "hooks jq-only" envelope). Uses jq to read
# session_id / tool_name / payload fields from the PreToolUse stdin JSON; the
# per-session task counter is bash arithmetic on a marker file.
#
# Two entry modes (arg 1):
#   mark  — PreToolUse:TaskCreate|TodoWrite. Counts tasks created this session
#           (TaskCreate = one task per call → increment a counter; TodoWrite =
#           array in one call → take its length). Records "an ENUMERATED task list
#           exists" (marker keyed by session_id) only once the count reaches
#           PLC_TASKLIST_MIN. A single one-task list no longer satisfies the guard.
#           Always exits 0.
#   check — PreToolUse for gated tools. If no enumerated task list exists yet,
#           blocks ONCE (exit 2) with an actionable message; after that single
#           block it stays silent (block-once, never a wall — loop-guard rule).
#           Gated tools: Edit|Write|MultiEdit|NotebookEdit always; Bash only when
#           the command is a `git commit`/`git push` (state-change boundary — the
#           intent-gate's read-only Bash + entry detection pass freely); subagent
#           dispatch (Task|Agent) only when PLC_TASKLIST_GATE_TASK=1 (default off,
#           so the intent-gate's Explore dispatch is not false-blocked).
#
# Per-phase re-arm (PLC_TASKLIST_REARM=1, default on): the block is once per
# PHASE, not once per session. A close-gate run (`make task-done` /
# `make phase-done` / `close-gate.sh`) is the canonical PLC phase-close boundary
# — when check sees one, it wipes this session's markers (seen/count/nudged), so
# the NEXT gated edit re-forces a fresh ≥PLC_TASKLIST_MIN task list for the next
# phase. Maps PLC's own "one task = one list = one gate" model. Loop-safe: re-arm
# fires only AFTER a real close-out, never mid-phase. Set PLC_TASKLIST_REARM=0 to
# revert to once-per-session. Bare-token match (git commit -m "task-done…" keeps
# its quote char after word-split → no false re-arm).
#
# Threshold PLC_TASKLIST_MIN=3: TaskCreate's own guidance is "3+ distinct steps";
# the most-compressed legit cadence still has ≥3 real steps; <3-step work is meant
# to skip the skill entirely.
#
# Fail-open on any parse error / missing session_id. Escape hatch:
# PLC_TASKLIST_GUARD=0 disables. RESUME.md writes are exempt (no deadlock with the
# context-floor hook, which demands a RESUME checkpoint write when it fires).
set -euo pipefail

MODE="${1:-check}"
INPUT="$(cat 2>/dev/null || true)"

[ "${PLC_TASKLIST_GUARD:-1}" = "0" ] && exit 0

N="${PLC_TASKLIST_MIN:-3}"
DIR="${TMPDIR:-/tmp}/plc-tasklist-guard"
mkdir -p "$DIR" 2>/dev/null || true

# jq field extraction — fail open on unparseable input or missing session_id.
jqget() { printf '%s' "$INPUT" | jq -r "$1" 2>/dev/null || true; }
SID="$(jqget '.session_id // empty')"
[ -z "$SID" ] && exit 0
TOOL="$(jqget '.tool_name // empty')"

COUNT="$DIR/$SID.count"
SEEN="$DIR/$SID.seen"
NUDGED="$DIR/$SID.nudged"

if [ "$MODE" = "mark" ]; then
  if [ "$TOOL" = "TodoWrite" ]; then
    # Other hosts: a TodoWrite carries the whole list in one call.
    len="$(jqget '.tool_input.todos | length // 0')"
    case "$len" in ''|*[!0-9]*) len=0 ;; esac
    [ "$len" -ge "$N" ] && : > "$SEEN"
  else
    # TaskCreate: one task per call — accumulate a per-session counter.
    c="$(cat "$COUNT" 2>/dev/null || echo 0)"
    case "$c" in ''|*[!0-9]*) c=0 ;; esac
    c=$((c + 1))
    printf '%s' "$c" > "$COUNT"
    [ "$c" -ge "$N" ] && : > "$SEEN"
  fi
  exit 0
fi

# mode == check

# Per-phase re-arm: a close-gate run is PLC's phase-close boundary. Detect it
# BEFORE the seen-early-return (else a session that already passed the gate would
# never reset). Wipe markers -> the next gated edit re-forces a fresh list.
# Must run even when SEEN exists — that's the whole point.
if [ "${PLC_TASKLIST_REARM:-1}" != "0" ] && [ "$TOOL" = "Bash" ]; then
  cmd="$(jqget '.tool_input.command // empty')"
  set -f
  # shellcheck disable=SC2086
  set -- $cmd
  set +f
  for t in "$@"; do
    case "$t" in
      task-done|phase-done|close-gate.sh|*/close-gate.sh)
        rm -f "$SEEN" "$COUNT" "$NUDGED" 2>/dev/null || true
        exit 0
        ;;
    esac
  done
fi

[ -e "$SEEN" ] && exit 0                 # enumerated task list exists -> allow

# RESUME.md exemption: checkpoint writes are never blocked (context-floor deadlock guard).
fp="$(jqget '.tool_input.file_path // empty')"
[ "$(basename "$fp" 2>/dev/null)" = "RESUME.md" ] && exit 0

# Decide whether THIS tool call is gated.
gated=0
case "$TOOL" in
  Edit|Write|MultiEdit|NotebookEdit)
    gated=1
    ;;
  Bash)
    # Gate only a git commit / git push (state-change boundary). Bash word-split
    # (no shlex in the jq envelope): match `git` + a bare `commit`/`push` token.
    cmd="$(jqget '.tool_input.command // empty')"
    set -f
    # shellcheck disable=SC2086
    set -- $cmd
    set +f
    has_git=0 has_verb=0
    for t in "$@"; do
      [ "$t" = "git" ] && has_git=1
      { [ "$t" = "commit" ] || [ "$t" = "push" ]; } && has_verb=1
    done
    [ "$has_git" = 1 ] && [ "$has_verb" = 1 ] && gated=1
    ;;
  Task|Agent)
    [ "${PLC_TASKLIST_GATE_TASK:-0}" = "1" ] && gated=1
    ;;
esac
[ "$gated" = 0 ] && exit 0                # not a gated call -> allow

[ -e "$NUDGED" ] && exit 0               # already blocked once this session -> stay silent

: > "$NUDGED"
printf '%s' "[project-lifecycle] Blocked (once): no enumerated task list exists this session. \
The skill's Definition of Done requires materializing the step list as your FIRST action \
(TaskCreate — one call per cadence/phase step, ${N}+ steps, wrap-up steps included; \
announcing a count is not enough) BEFORE committing/editing work. \
Create the task list, then retry. (SKILL.md \"Definition of Done\"; \
escape hatch for genuinely trivial inline work: PLC_TASKLIST_GUARD=0)
" >&2
exit 2
