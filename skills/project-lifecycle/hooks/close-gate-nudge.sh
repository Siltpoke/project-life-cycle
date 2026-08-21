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
#   The task boundary is the cheapest moment to checkpoint + /clear; sessions
#   that skip it tend to end at several times the per-turn input of their early turns.
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

# Values go in as jq --arg, never interpolated into the filter: additionalContext carries
# arbitrary prose (quotes, newlines, backslashes) and jq must do the escaping.
# Byte-note: the output is NOT byte-identical to the python3 `json.dumps` this replaced, on
# every input -- two independent reasons, verified by differential test over 10 cases
# (plain / quotes / backslash / newline / tab / CJK / emoji / empty / json-looking):
#   1. separators. json.dumps defaults to ", " and ": "; jq -c is compact. Affects EVERY line.
#   2. ensure_ascii. json.dumps escaped non-ASCII to \uXXXX; jq emits UTF-8. Affects CJK/emoji.
# Both forms are valid JSON and parse to the same structure, which is all the harness needs.
# Recorded because "equivalent" here means semantically, not bytewise -- a future consumer that
# byte-compares would break, and it should find this note rather than rediscover it.
# (jq-only envelope -- these hooks install on the adopter's machine.)
emit() {
  jq -nc --arg e "$EVENT" --arg c "$1" \
    '{hookSpecificOutput:{hookEventName:$e,additionalContext:$c}}'
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
# dirty-tree trigger.)
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
#
# ── shared floor math ───────────────────────────────────────────────────
# `trim` / `intenv` / `floatenv` come from ONE file shared with context-floor.sh. "Keep the two
# in sync" used to be a comment, and a comment was not enough -- this hook sat without the
# `* 1` that context-floor.sh already carried, and a subnormal percentage floor SILENCED
# the nudge where python would have warned. The counter-example was one file away.
#
# Sourced in a SUBSHELL, carrying only the variable back out -- the same guard context-floor.sh
# uses, for the same reason: absent, syntactically broken, "contains `exit`", and
# "sources cleanly but the text is not a usable program" must all degrade identically. The `exit`
# shape matters more on this side, not less: this hook runs `set -euo pipefail`, so a sourced
# failure is doubly able to take the whole hook down mid-Stop instead of degrading. `[ -r ]`
# distinguishes none of the four, and a bare `-z` check misses the fourth.
# `${var%/*}` returns $var UNCHANGED when it holds no slash, so a slash-less invocation would
# compose `close-gate-nudge.sh/lib/floor-env.sh`.
_lib_dir="${BASH_SOURCE[0]%/*}"
[ "$_lib_dir" = "${BASH_SOURCE[0]}" ] && _lib_dir="."
LIB="${PLC_FLOOR_LIB:-$_lib_dir/lib/floor-env.sh}"
# shellcheck source=lib/floor-env.sh
PLC_FLOOR_JQ_DEFS="$( . "$LIB" >/dev/null 2>&1; printf '%s' "${PLC_FLOOR_JQ_DEFS:-}" )" || PLC_FLOOR_JQ_DEFS=""
# Non-empty is not the same as usable. A library that sources cleanly and sets the variable to
# garbage, or to text defining nothing, arrives non-empty and then dies inside the `2>/dev/null
# || echo 0` on the floor program below -- which maps to `FLOOR=0` and exits silently, i.e. "no
# nudge was due". So the text is PROBED: it must parse and all three definitions must answer
# correctly on known inputs.
#
# THE PROBE INPUTS COVER ALL THREE BRANCHES. An earlier revision probed only an ABSENT
# variable, so every definition it exercised took the `$unset` branch -- and a library reading
# `def intenv($n; $unset; $empty): $unset;`, which ignores the environment entirely, answered the
# probe correctly and passed. Measured on the floor side: that library made the hook ignore an
# explicit `PLC_CONTEXT_FLOOR=0` and block at the default floor. A probe that only ever asks for
# an absent variable cannot tell "reads the environment" from "never reads anything".
#
# The `1e-400` case is the subnormal-floor incident above: without the library's `* 1`, jq keeps the literal
# at arbitrary precision and the value stays greater than zero, where python's C double underflows
# to 0.0. So library text without the `* 1` is now REJECTED by this probe rather than declared out of scope --
# an earlier revision declared exactly that shape acceptable, and it is the one shape this probe exists to
# catch. What remains genuinely out of scope is version drift that changes no probed answer.
_lib_ok=""
if [ -n "$PLC_FLOOR_JQ_DEFS" ]; then
  _lib_ok="$(PLC_FLOOR_LIB_PROBE_INT=42 PLC_FLOOR_LIB_PROBE_EMPTY= PLC_FLOOR_LIB_PROBE_TINY=1e-400 \
    jq -nr "$PLC_FLOOR_JQ_DEFS"'
    ((("  x " | trim) == "x")
     and (intenv("PLC_FLOOR_LIB_PROBE_ABSENT"; 7; 8) == 7)
     and (intenv("PLC_FLOOR_LIB_PROBE_EMPTY"; 7; 8) == 8)
     and (intenv("PLC_FLOOR_LIB_PROBE_INT"; 7; 8) == 42)
     and (floatenv("PLC_FLOOR_LIB_PROBE_ABSENT"; 9; 10) == 9)
     and (floatenv("PLC_FLOOR_LIB_PROBE_EMPTY"; 9; 10) == 10)
     and (floatenv("PLC_FLOOR_LIB_PROBE_INT"; 9; 10) == 42)
     and (floatenv("PLC_FLOOR_LIB_PROBE_TINY"; 9; 10) == 0))
  ' 2>/dev/null || true)"
fi
if [ "$_lib_ok" != "true" ]; then
  # Fail OPEN, and say so -- per event, which for a Stop hook is already at most once per stop,
  # so no throttle is needed on this side. Silence here would read as "no nudge was due".
  printf 'project-lifecycle: close-gate nudge OFF -- shared library not usable (%s)\n' "$LIB" >&2
  exit 0
fi

# Env handling mirrors the python this replaced EXACTLY, including two quirks that look like
# bugs but are the original's semantics: an UNSET var takes the default, while an EMPTY var
# means 0 for the two floor vars (i.e. disabled) but still 1000000 for WINDOW -- that asymmetry
# is the original's `or "0"` vs `or "1000000"`, not an invention here. Likewise python's int()
# REJECTS a decimal string ("0.5" raised, falling back to the default), so intenv() requires an
# integer pattern rather than accepting whatever tonumber would swallow.
FLOOR="$(jq -nr "$PLC_FLOOR_JQ_DEFS"'
  intenv("PLC_CONTEXT_FLOOR";      150000; 0)        as $abs
  | floatenv("PLC_CONTEXT_FLOOR_PCT";    0; 0)       as $pct
  | intenv("PLC_CONTEXT_WINDOW";  1000000; 1000000)  as $win
  | (if $pct > 0 and $win > 0 then ($win * $pct / 100) else $abs end)
  # A non-finite floor is exactly where python raised OverflowError inside int(),
  # uncaught, so the old scan emitted nothing. 0 reproduces that silence. `nan > 0`
  # and `-inf > 0` are both False in python, so those never reach here -- they fall
  # through to the absolute floor and DO nudge, which an earlier version of this fix
  # wrongly silenced.
  #
  # FORMER KNOWN DIVERGENCE -- CLOSED. The retired reasoning is kept
  # verbatim below, because being wrong in this particular way is the point.
  #
  # It used to say: reproducing python`s `1e-400` underflow "would mean hard-coding a magic
  # 5e-324 threshold, which is more fragile than the divergence it papers over", and that both
  # behaviours mean "no usable percentage floor" so only the phrasing differs.
  #
  # Every clause of that was wrong:
  #   - The fix is `* 1`, not a threshold. Measured: `jq -n ("1e-400"|tonumber) > 0` is true,
  #     the same expression `* 1` is false, and python agrees with the second.
  #   - `context-floor.sh` had ALREADY implemented it, in this exact form -- its own
  #     comment says the `* 1` closes a divergence once documented as unfixable. The
  #     counter-example sat one file away and nothing connected the two.
  #   - The two behaviours are NOT equivalent. python falls through to the absolute floor and
  #     NUDGES; the unfixed jq took the %-branch, computed a floor of 0, and went SILENT. One
  #     warns the user and the other does not, which is the whole job of this hook.
  #
  # Executable form: `test-hooks.sh`, row "a subnormal PLC_CONTEXT_FLOOR_PCT falls through to
  # the absolute floor" -- measured RED, with empty output, before the fix.
  | if (isinfinite or isnan) then 0 else floor end
' 2>/dev/null || echo 0)"
case "$FLOOR" in ''|*[!0-9]*) exit 0 ;; esac    # negative or junk -> treat as disabled
[ "$FLOOR" -le 0 ] && exit 0                    # floor disabled -> no nudge

TPATH="$(printf '%s' "$INPUT" \
  | jq -r 'if type == "object" then (.transcript_path // "") else "" end' 2>/dev/null || true)"
[ -n "$TPATH" ] && [ -f "$TPATH" ] || exit 0    # fail-open: no transcript -> no nudge

# Last non-zero usage total wins: the python reassigned `occ` on every hit and kept the final
# one, so `tail -1` is the faithful translation, not `max`.
# `fromjson?` is the direct equivalent of the per-line try/except -- a malformed line is skipped
# and the scan continues.
# `n()` reproduces python's `(u.get(k) or 0)`, which coerced every FALSY value -- None, false, 0,
# "", [], {} -- to 0. jq's `// 0` only replaces null and false, so an empty-string token field
# stayed a string, made the sum raise, and dropped the whole LINE. With `tail -1` that is not a
# harmless skip: it reports an OLDER, LOWER occupancy and can suppress the nudge entirely.
# The differential fixtures cannot see this -- none carries a
# falsy-but-not-null usage field, so the gap is in the fixture set, not the assertions.
#
# DELIBERATE DIFFERENCE (the one that remains, now narrower): a TRUTHY non-numeric field ("abc",
# [1]) raised in python and abandoned the entire scan; here it raises and skips only that line.
# One bad record silently disabling an advisory nudge is the worse failure. This no longer
# swallows the falsy cases python handled cleanly.
OCC="$(jq -Rr '
  def n($v): if   ($v | type) == "number" then $v
             elif $v == null or $v == false or $v == "" or $v == [] or $v == {} then 0
             else error("non-numeric usage field") end;
  fromjson?
  | select(type == "object")
  | ((if (.message | type) == "object" then .message.usage else null end) // .usage) as $u
  | select(($u | type) == "object")
  | (try ( n($u.input_tokens)
         + n($u.cache_read_input_tokens)
         + n($u.cache_creation_input_tokens) ) catch empty)
  | select(type == "number" and . > 0)
' "$TPATH" 2>/dev/null | tail -1)"
case "$OCC" in ''|*[!0-9]*) exit 0 ;; esac
[ "$OCC" -lt "$FLOOR" ] && exit 0

# Rounding note: python's round() is banker's rounding (half-to-even); this is half-up. They
# differ only when the value is an exact odd multiple of 500, and the number is display-only
# ("~123K"), so a 1K divergence in that rare case carries no behavioural weight.
OVER="$(( (OCC + 500) / 1000 )) $(( (FLOOR + 500) / 1000 ))"
[ -z "$OVER" ] && exit 0

OCC_K="${OVER%% *}"; FLOOR_K="${OVER##* }"
throttle clear-nudge-last || exit 0
emit "[project-lifecycle] Task close just passed on ${BRANCH} and context ~${OCC_K}K is over the ~${FLOOR_K}K floor — this task boundary is the cheapest moment to checkpoint: write/refresh RESUME.md + handoff notes, commit, then /clear before the next task. Late-session turns cost 2-3x early turns (SKILL.md cost-aware behaviors)."
exit 0
