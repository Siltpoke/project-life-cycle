#!/usr/bin/env bash
# project-lifecycle — enumerated-task-list guard (Definition of Done, forcing function 1).
# Satisfied by the CONTENT of a portable checklist artifact (see ART_REL below); a host task
# tool (TaskCreate / TodoWrite) is an optional additional satisfier, never the contract.
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
#           blocks ONCE (exit 2) with an actionable message carrying a nonce; after
#           that single block it does NOT go silent — it returns permissionDecision
#           `defer` plus an `additionalContext` UNVERIFIED notice on EVERY later gated
#           call, so "could not verify" stays distinct from "verified" in the model's
#           context. Still block-once, never a wall (loop-guard rule), and `defer`
#           leaves the user's normal permission flow untouched.
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

# The PORTABLE satisfier. The guard used to be satisfied only by a host tool call
# (TaskCreate / TodoWrite). That is unsatisfiable wherever the host has no such tool — and a
# hook cannot ask: its stdin carries only THIS call's {session_id, tool_name, tool_input},
# with no way to enumerate the session's tools. Worse, no two agent CLIs agree on the name
# or the granularity (TaskCreate one-per-call, Codex `update_plan` whole-list, Gemini
# `write_todos`, Cursor `updateTodos`, Amp `todo_write`), so a name-keyed guard cannot
# generalize even in principle.
#
# So key on CONTENT, not tool identity: a plain checklist file. Write/Edit is provably
# available on every host where this guard can fire — it is what the guard gates — so the
# requirement is now satisfiable exactly where it is enforced. Same move as EditorConfig
# (drop each editor's settings API for one plain file) and Kubernetes preferring httpGet
# over exec probes (drop the in-container binary for a universal contract). The tool-call
# `mark` path below is kept as an OPTIONAL additional satisfier, not the contract.
ART_REL="${PLC_TASKLIST_FILE:-.claude/tasklist.md}"

# jq field extraction — fail open on unparseable input or missing session_id.
jqget() { printf '%s' "$INPUT" | jq -r "$1" 2>/dev/null || true; }
SID="$(jqget '.session_id // empty')"
[ -z "$SID" ] && exit 0
TOOL="$(jqget '.tool_name // empty')"

COUNT="$DIR/$SID.count"
SEEN="$DIR/$SID.seen"
NUDGED="$DIR/$SID.nudged"
NONCE="$DIR/$SID.nonce"

CWD="$(jqget '.cwd // empty')"
ART="${CWD:+$CWD/}$ART_REL"

# Anti-stale defense is a NONCE CARRIED IN THE FILE'S TEXT, deliberately not an mtime.
# An mtime check would be the very defect its sibling gate had to be fixed for. A
# checked-out tree may live under a file-syncing directory whose daemon re-touches
# files, so "recently modified" is not evidence of anything. A nonce is minted at block time,
# printed in the block message, and must be transcribed into the artifact — so last phase's
# checklist cannot satisfy this phase, and no background process can forge it.
artifact_ok() {
  [ -f "$ART" ] || return 1
  _n="$(cat "$NONCE" 2>/dev/null || true)"
  [ -n "$_n" ] || return 1
  grep -qF -- "$_n" "$ART" 2>/dev/null || return 1
  _c="$(grep -cE '^[[:space:]]*- \[[ xX]\]' "$ART" 2>/dev/null || echo 0)"
  case "$_c" in ''|*[!0-9]*) _c=0 ;; esac
  [ "$_c" -ge "$N" ]
}

mint_nonce() {
  _v="$(head -c 6 /dev/urandom 2>/dev/null | od -An -tx1 2>/dev/null | tr -d ' \n' || true)"
  [ -n "$_v" ] || _v="$$${RANDOM:-0}"   # fallback: never leave the nonce empty
  printf '%s' "$_v" > "$NONCE" 2>/dev/null || true
  printf '%s' "$_v"
}

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
#
# this used to word-split the Bash command and re-arm on a bare `close-gate.sh` /
# `task-done` / `phase-done` TOKEN. That is a syntactic fact standing in for a semantic event,
# and it fired on commands that only READ or STAGED the gate file — `wc -l scripts/…`,
# `git add scripts/…` — four times during this phase alone, including while this very block was
# being rewritten. The token scan is DELETED, not narrowed: no narrowing of "the name appears in
# a string" ever becomes "the thing ran".
#
# The gate now writes its own marker on exit (see scripts/close-gate.sh §"the gate publishes its
# own completion signal"), carrying a per-run id and the exit code. Two consequences worth
# stating rather than discovering:
#
#   * A FAILING gate no longer re-arms. The old check fired in PreToolUse — i.e. when the gate
#     command was ABOUT TO run — so a gate that then failed re-armed exactly as a passing one
#     did. It declared the event before it happened. Re-arm is now conditional on `exit=0`.
#   * The scope changed from per-session to per-repo-per-run. The gate is a separate process and
#     never sees a session_id, so the marker cannot be session-scoped. Re-arm now means "this
#     repo closed a phase since I last looked", not "this session did". The per-run id is what
#     keeps one gate run from re-arming more than once, and what stops last phase's marker from
#     counting — the same anti-stale reasoning as the nonce above, and equally not an mtime.
if [ "${PLC_TASKLIST_REARM:-1}" != "0" ]; then
  GMARK="${CWD:+$CWD/}.claude/.gate-runs/last-run"
  GSEEN="$DIR/$SID.gateseen"
  if [ -f "$GMARK" ]; then
    _grun="$(sed -n 's/^run=//p' "$GMARK" 2>/dev/null | head -1)"
    _gexit="$(sed -n 's/^exit=//p' "$GMARK" 2>/dev/null | head -1)"
    _gprev="$(cat "$GSEEN" 2>/dev/null || true)"
    if [ -n "$_grun" ] && [ "$_grun" != "$_gprev" ]; then
      # Record it either way, so one gate run is considered exactly once.
      printf '%s' "$_grun" > "$GSEEN" 2>/dev/null || true
      if [ "$_gexit" = "0" ]; then
        rm -f "$SEEN" "$COUNT" "$NUDGED" "$NONCE" 2>/dev/null || true
        exit 0
      fi
    fi
  fi
fi

artifact_ok && exit 0                    # portable checklist artifact is valid -> allow
[ -e "$SEEN" ] && exit 0                 # host task tool satisfied it instead -> allow

# RESUME.md exemption: checkpoint writes are never blocked (context-floor deadlock guard).
fp="$(jqget '.tool_input.file_path // empty')"
[ "$(basename "$fp" 2>/dev/null)" = "RESUME.md" ] && exit 0
# The artifact itself is exempt, or the guard is a deadlock: the only way to satisfy it is
# a Write, and Write is gated. Match on basename so an absolute, relative, or symlinked
# path all resolve the same way.
[ "$(basename "$fp" 2>/dev/null)" = "$(basename "$ART_REL")" ] && exit 0

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

# THE THIRD STATE. Previously this line was a bare `exit 0`: after one block the guard
# went silent and permitted everything, so every later gated call was indistinguishable in the
# transcript from a genuine pass. That is the defect — not weak enforcement, but DISHONEST
# REPORTING. Every mature checker keeps "not verified" as its own state: TAP `# SKIP`, pytest
# `skip` vs `xfail`, JUnit `skipped` vs a passing testcase, SARIF `result.kind: notApplicable`
# with `level` forced to `none`. None of them fold it into pass. Neither do we: the call is
# still allowed (block-once, never a wall — a hard wall on a possibly-unsatisfiable demand is
# a deadlock, not rigor), but it is allowed OUT LOUD, on every call, until the list exists.
#
# FIELD CHOICE IS LOAD-BEARING — verified against the documented PreToolUse contract, after
# a first version of this block shipped the wrong two and had to be hotfixed:
#   permissionDecision "allow"  -> "Tool call proceeds WITHOUT permission prompt". That is an
#       auto-approval: it removes the human's confirmation for every gated Edit/Write/commit/
#       push for the rest of the phase. A guard must never buy its own visibility by spending
#       the user's consent. NOT "allow".
#   permissionDecision "defer"  -> "Skips this hook's decision; normal permission flow
#       applies". Exactly the semantics wanted: non-blocking, and the guard abstains rather
#       than deciding.
#   permissionDecisionReason    -> documented as shown to Claude, and explicitly NOT shown anywhere under `allow`;
#       under `defer` the docs are silent, i.e. unspecified.
#       Under defer/allow it is unspecified — i.e. the message reaches nobody. NOT this field.
#   additionalContext           -> "Information added to Claude's context for this turn".
#       This is the field that actually carries the notice to the model.
if [ -e "$NUDGED" ]; then
  jq -cn --arg p "$ART_REL" --arg n "$N" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "defer",
      additionalContext: ("UNVERIFIED — project-lifecycle could not verify an enumerated task list for this phase, and is NOT enforcing one. This is not a pass; do not treat it as one at close time. The normal permission flow is untouched. To restore enforcement, write " + $p + " with " + $n + "+ `- [ ]` steps including the wrap-up steps (journal / tests / CHANGELOG / PR comment), carrying the nonce from the earlier block message. Closing a phase under UNVERIFIED requires a `SKIP:` line in the journal.")
    }
  }' 2>/dev/null || true
  exit 0
fi

: > "$NUDGED"
NV="$(mint_nonce)"
printf '%s' "[project-lifecycle] Blocked (once): no enumerated task list exists for this phase. \
The skill's Definition of Done requires materializing the step list as your FIRST action \
(${N}+ steps, wrap-up steps included; announcing a count is not enough) BEFORE committing/editing work.

Write ${ART_REL} with the first line:

    <!-- plc-tasklist: ${NV} -->

then ${N}+ checklist lines, one per cadence/phase step, e.g. \`- [ ] journal entry\`. \
Writing that file is never blocked. A host task tool (TaskCreate / TodoWrite) also satisfies \
this where one exists, but the file is the portable contract and does not depend on the host. \
After this one block the guard does NOT enforce — it reports UNVERIFIED on every subsequent \
call until the list exists. (SKILL.md \"Definition of Done\"; escape hatch for genuinely \
trivial inline work: PLC_TASKLIST_GUARD=0)
" >&2
exit 2
