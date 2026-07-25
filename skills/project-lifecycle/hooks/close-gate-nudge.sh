#!/usr/bin/env bash
# project-lifecycle — Stop / SubagentStop close-gate nudge.
# Injects a one-line reminder via hookSpecificOutput.additionalContext,
# but ONLY when it is actually relevant and not too often:
#   Close-gate nudge (original):
#   - on a feat/phase-* branch (we are mid-phase), AND
#   - there are uncommitted changes OR no fresh test-evidence, AND
#   - we have not already nudged in the last 10 minutes (throttle).
#   /clear nudge (attacks late-session context tax):
#   - on a feat/phase-* branch, AND
#   - clean tree + test-evidence present (a task close just passed), AND
#   - context occupancy >= the context-floor (same env semantics as
#     context-floor.sh: PLC_CONTEXT_FLOOR, PLC_CONTEXT_FLOOR_PCT,
#     PLC_CONTEXT_WINDOW; floor 0 = disabled = no nudge), AND
#   - not already /clear-nudged in the last 10 minutes (separate throttle).
#   The task boundary is the cheapest moment to checkpoint + /clear; measured
#   sessions that skipped it ended at 370-420K input/turn (2-3x early turns).
# Silent in every other case. Always exits 0 — never blocks turn/subagent end.
# Fails OPEN: any parse/read error on the transcript just skips the /clear nudge.
# Realizes the skill's "Definition of Done" forcing function as a platform nudge.
set -euo pipefail

EVENT="${1:-Stop}"
INPUT="$(cat 2>/dev/null || true)"   # hook event JSON (transcript_path lives here)

BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '')"
case "$BRANCH" in
  feat/phase-*) ;;
  *) exit 0 ;;            # not mid-phase → nothing to nudge about
esac

emit() {
  python3 - "$EVENT" "$1" <<'PY'
import json, sys
print(json.dumps({"hookSpecificOutput": {"hookEventName": sys.argv[1], "additionalContext": sys.argv[2]}}))
PY
}

# --- machine-local state --------------------------------------------------------------
# WHERE THIS HOOK'S STATE LIVES: $PLC_STATE_DIR, else ~/.claude/plc-state/<repo-key>/.
# Named here on purpose — moving state out of the worktree hides it from the reviewer who would
# otherwise notice it misbehaving, so the path has to be discoverable from the code.
#
# It used to live at .claude/.close-gate-nudge-last, GIT-TRACKED. That is a closed loop: this
# hook rewrites the stamp on every Stop, which makes the tree dirty, and "the tree is dirty" is
# one of this same hook's trigger conditions — so it re-armed on its own throttle file, and every
# phase's history carried a commit whose entire content was a timestamp. A throttle is neither
# shared team state nor evidence of anything; it is per-machine UX state and belongs out of the
# tree entirely, next to the session digests PLC already keeps in ~/.claude/plc-session-data/.
# (The /clear throttle at .claude/.clear-nudge-last had the same problem in a quieter form: it was
# neither tracked NOR ignored, so it showed up as an untracked `??` entry and fed the same
# dirty-tree trigger. The original write-up named only the first of the two.)
plc_state_dir() {
  local root key
  root="${PLC_STATE_DIR:-$HOME/.claude/plc-state}"
  key="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
  # One flat directory name per worktree. Slashes and spaces become dashes; the result is a
  # stable key for this checkout without needing a hash or a lookup table.
  key="$(printf '%s' "$key" | tr '/ ' '--')"
  printf '%s/%s' "$root" "$key"
}

# throttle <name>: returns 0 (proceed) at most once per 10 min per name.
# Takes a NAME, not a path — callers must not be able to place state back in the worktree.
throttle() {
  local name="$1" dir f now last
  dir="$(plc_state_dir)"
  mkdir -p "$dir" 2>/dev/null || true
  f="$dir/$name"
  now="$(date +%s)"
  last=0
  [ -f "$f" ] && last="$(cat "$f" 2>/dev/null || echo 0)"
  [ $((now - last)) -lt 600 ] && return 1
  echo "$now" > "$f" 2>/dev/null || true
  return 0
}

REASON=""
[ -n "$(git status --porcelain 2>/dev/null || true)" ] && REASON="uncommitted changes"
if [ ! -f .claude/.last-test-run ]; then
  REASON="${REASON:+$REASON; }no fresh test-evidence (.claude/.last-test-run missing)"
fi

if [ -n "$REASON" ]; then
  throttle close-gate-nudge-last || exit 0
  emit "[project-lifecycle] On ${BRANCH} with ${REASON}. Before claiming done: run make task-done / phase-done and paste its output; confirm every wrap-up todo (journal / tests-3x / handoff / CHANGELOG / smoke / PR-comment) is checked or logged as SKIP. (SKILL.md \"Definition of Done\")"
  exit 0
fi

# Clean + tested = a task close just passed → check context occupancy vs floor.
# Prints "OCC_K FLOOR_K" (rounded thousands) when over floor; nothing otherwise.
# Floor semantics deliberately mirror context-floor.sh (keep the two in sync).
OVER="$(python3 - "$INPUT" 2>/dev/null <<'PY' || true
import json, os, sys

try:
    ev = json.loads(sys.argv[1]) if sys.argv[1] else {}
except Exception:
    sys.exit(0)
if not isinstance(ev, dict):
    sys.exit(0)

try:
    floor_abs = int(os.environ.get("PLC_CONTEXT_FLOOR", "150000") or "0")
except Exception:
    floor_abs = 150000
try:
    floor_pct = float(os.environ.get("PLC_CONTEXT_FLOOR_PCT", "0") or "0")
except Exception:
    floor_pct = 0.0
try:
    window = int(os.environ.get("PLC_CONTEXT_WINDOW", "1000000") or "1000000")
except Exception:
    window = 1000000
if floor_pct > 0 and window > 0:
    floor = int(window * floor_pct / 100)
else:
    floor = floor_abs
if floor <= 0:
    sys.exit(0)  # floor disabled → no nudge

tpath = ev.get("transcript_path") or ""
if not tpath or not os.path.exists(tpath):
    sys.exit(0)  # fail-open: no transcript → no nudge
occ = None
try:
    with open(tpath, "r", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            u = None
            if isinstance(o, dict):
                m = o.get("message")
                if isinstance(m, dict):
                    u = m.get("usage")
                if u is None:
                    u = o.get("usage")
            if isinstance(u, dict):
                tot = ((u.get("input_tokens") or 0)
                       + (u.get("cache_read_input_tokens") or 0)
                       + (u.get("cache_creation_input_tokens") or 0))
                if tot > 0:
                    occ = tot
except Exception:
    sys.exit(0)
if occ is None or occ < floor:
    sys.exit(0)
print("%d %d" % (round(occ / 1000), round(floor / 1000)))
PY
)"
[ -z "$OVER" ] && exit 0

OCC_K="${OVER%% *}"; FLOOR_K="${OVER##* }"
throttle clear-nudge-last || exit 0
emit "[project-lifecycle] Task close just passed on ${BRANCH} and context ~${OCC_K}K is over the ~${FLOOR_K}K floor — this task boundary is the cheapest moment to checkpoint: write/refresh RESUME.md + handoff notes, commit, then /clear before the next task. Late-session turns cost 2-3x early turns (SKILL.md cost-aware behaviors)."
exit 0
