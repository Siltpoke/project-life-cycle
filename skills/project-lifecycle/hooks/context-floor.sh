#!/usr/bin/env bash
# project-lifecycle — context-saturation hard floor (enforce-only, self-arming).
# Wired as PreToolUse:Edit|Write (machine-local global). When the session's context
# occupancy crosses an absolute-token floor, blocks Edit/Write (exit 2) until RESUME.md
# is refreshed. Deliberately does NOT warn: soft %-based warnings are left to whatever
# statusline indicator or prompt-time hooks the user already runs.
# The floor's only job is the hard block those soft layers cannot do.
#
# Occupancy = newest assistant turn's input_tokens + cache_read + cache_creation
# (read from the transcript JSONL). Floor: env PLC_CONTEXT_FLOOR (default 150000;
# 0 = disabled). Re-arm step after a checkpoint: PLC_CONTEXT_FLOOR_STEP (default 30000).
#
# Window-% mode (opt-in): set PLC_CONTEXT_FLOOR_PCT (e.g. 70) to trigger at a
# FRACTION of the running model's window instead of an absolute token count.
# When >0 it OVERRIDES PLC_CONTEXT_FLOOR — effective floor = window * pct/100,
# where window = PLC_CONTEXT_WINDOW (default 1000000). This lets a 1M-window
# user set one %-threshold that holds across models, instead of re-deriving an
# absolute floor per window size (a 150K floor is 75% of a 200K window but only
# 15% of a 1M window). Absolute mode stays the default — rot tracks absolute
# context size, not window fraction (references/harness-primitives.md §9) — but
# the %-knob is there for users whose mental model is window-occupancy.
# Disable entirely: PLC_CONTEXT_FLOOR=0 AND PLC_CONTEXT_FLOOR_PCT=0 (or unset).
# Self-arms: the first over-floor Edit/Write creates a session-keyed marker; a RESUME.md
# newer than that marker clears it and allows work. Fails OPEN (exit 0) on any
# read/parse/write error — a broken floor must never block work. NOT a frontmatter hook
# (would miss non-workflow sessions).
#
# Escape hatches, and where they may be MENTIONED:
#   - PLC_CONTEXT_FLOOR=0 (or _PCT=0) — a deliberate config decision. Named in the block
#     message; fine.
#   - deleting the marker — a human who reads this source can do it. NOT named in the
#     block message, and the marker path is not printed there either. The block message
#     used to say "or `rm <marker>` to override once", and an agent blocked mid-task did
#     exactly that: it deleted the guard's state to get past the guard, because the guard
#     told it how. A guard that ships its own bypass in its error message is a guard that
#     will be bypassed — and the agent taking it is not even disobeying, it is following
#     instructions. Keep the hatch; stop advertising it at the moment of maximum incentive
#     to take it.
#
# ── bash + jq, no python3 ────────────────────────────────────────────────
# This hook used to be a ~170-line python3 heredoc. The project's dependency envelope
# for gate scripts and hooks is jq-only; widening it hurts
# portability as a drop-in forcing function, and python3 no longer ships with macOS.
#
# The divergence ledger. `scripts/invariants/ledger-contract-sync.sh` extracts the span between
# the two bare marker lines below, matched as WHOLE LINES. That anchoring is not fussiness:
# with a substring match, this very comment -- which has to
# name the markers to explain them -- closes the range on itself: the span
# comes back a few lines long, the extracted id set is EMPTY, and an empty set compares equal
# to an empty set, so the invariant would pass while checking nothing.
#
# Line numbers are deliberately not used either: `file:line` references go stale silently.
#LEDGER-BEGIN
# Behaviour was deliberately UNCHANGED BY THE PORT. Four known defects were preserved on
# purpose and asserted as XFAIL rows in hooks/test-context-floor-contract.sh — red before
# the port and red after it, which is what "faithfully preserved" is supposed to mean.
#
# Four of the four have since been fixed in their own phases, each with the whole apparatus
# pointed at one behaviour change at a time — which is the discipline this list protects,
# not a prohibition on ever fixing them:
#   B9011 FIXED — the checkpoint is now resolved against the file being written,
#        not the session cwd. Row graduated to live.
#   B9012 FIXED — the first call of an arm cycle is decided at the arm site
#        instead of against a marker created microseconds earlier. Row graduated to live.
#   B9013 FIXED — the CLEAR path now requires a checkpoint FILE too, closing the
#        half the first-call fix left open. Rows are live. This one is a CHOSEN divergence, not a preserved
#        defect — see the divergence note below.
#   B9014 FIXED -- a truthy non-numeric usage field now skips that RECORD instead
#        of abandoning the whole scan. Row graduated to live. This is a CHOSEN divergence
#        from the pinned python reference.
#   B9015 FIXED -- only an ABSENT session_id keys "nosession"; each present-but-
#        falsy value gets its own key. Row graduated to live. Also a CHOSEN divergence.
#   B9016 FIXED -- the session key is percent-encoded before it becomes a filename.
#        Both halves were measured on the pinned reference and are INHERITED, not port damage:
#        a `/` implied a subdirectory nothing creates, so the write failed and the hook FAILED
#        OPEN (exit 0, floor silently off for the session); a `..` resolved OUT of the marker
#        directory and wrote into its parent. A CHOSEN divergence.
#   B9016 CLOSED -- the sentinel half of the same key, and a storage-layer half.
#        The sentinels moved OUT of `@uri`'s image (`%~<token>`) instead of prefixing every real id.
#        Separately, the key is a FILENAME and a case-folding volume merged two
#        ids that `@uri` kept apart, so the string branch now escapes uppercase as well --
#        byte-identical output for ids with no uppercase and no `~`, so existing keys did not
#        move. No erroneous allow or block was ever demonstrated from the folding; the
#        sentinel half DID demonstrate one (a session spending a window it never earned).
#   B9017 FIXED -- the grace record carries the RESOLVED CHECKPOINT PATH as a second
#        field, so "which checkpoint does the floor measure" and "whose grace window is this"
#        are answered by one resolution and cannot drift apart. Row graduated to live.
#        An old single-field record grants no grace: fail-closed.
#   B9018 FIXED -- a DIRECTORY (or FIFO / socket) at the MARKER path used to skip the
#        arm block entirely, freezing its mtime so every later call cleared and re-issued a
#        grace window: a permanent, silent, per-session disable. The arm entry now widens to
#        "no REGULAR marker" and a non-regular node is RENAMED ASIDE, never deleted; an
#        unrepairable one moves the guard's own state to a sidecar so the block stays clearable.
#        The row that used to carry it was DELETED, not graduated -- measured decorative (XPASS
#        under two designs it was supposed to reject) -- and replaced by independently
#        falsifiable rows.
#
# THE LIST IS NOW EMPTY OF PRESERVED DEFECTS, and `scripts/invariants/ledger-contract-sync.sh`
# reads that as the finished state rather than as a broken extractor.
#LEDGER-END
# Do not "just fix" one of these while touching this file for another reason. Changing
# behaviour and substrate together destroys the ability to tell a porting bug from an
# intended change; fixing one deliberately, in its own phase, is how each of them went.
#
# CHOSEN divergences from the python — deliberate leads, not porting bugs. They are
# named HERE and asserted in hooks/test-context-floor-contract.sh:
#   the checkpoint resolution and the first-call decision — see above.
#   the clear path: a DIRECTORY, a FIFO, or a symlink to /dev/null named RESUME.md no longer clears the
#        block on the second call. The pinned python's os.path.getmtime() returns an mtime for
#        all three and clears; this blocks. Measured before the change: 00/clearedat=YES on
#        both implementations, i.e. ~30K of free over-floor edits per arm cycle.
#
# Three OTHER divergences from the python are unavoidable rather than chosen, and all three are
# named here rather than left silent:
#   - an overflowing PLC_CONTEXT_FLOOR_PCT (`inf`, `1e309`) exits 1 in both, but the
#     python also printed a traceback and this cannot reproduce that text
#   - likewise for a TRUTHY NON-STRING session_id or cwd, which raised TypeError from
#     os.path.join: exit 1 and an untouched filesystem are reproduced, the traceback is not
#   - the rounding of the display-only "~NK" figures is half-up here and half-to-even
#     in python; they differ only at an exact odd multiple of 500
#
# THE PORT'S OWN BUG CLASS. Every
# defect that survived both oracles lived in a value ENCODER, and every one failed in the
# same direction — the port allowed where the python blocked:
#   @tsv escaped tab/newline/CR/backslash out of path data · jq's `//` is falsy only for
#   null and false where python's `or` is also falsy for 0, "", [] and {} · a hand-written
#   normpath collapsed the leading "//" that POSIX and python preserve · one base was used
#   where python resolves the tool target and a relative PLC_RESUME_PATH against two.
# Both suites were green throughout, because every fixture path was a plain `mktemp` path
# and every fixture field was a JSON string. The fixtures were the blind spot, not the
# assertions. Anything added here that hands a value between jq and bash, or normalises a
# path, needs a fixture carrying a hostile byte and one carrying a non-string.
set -uo pipefail

INPUT="$(cat 2>/dev/null || true)"

# jq missing -> fail OPEN. A machine without jq has an inert floor, which is the same
# bargain every other failure path here makes: a broken floor must never block work.
#
# (What now exists, and exactly what it is worth. Both close gates, the canonical one
# in references/close-gate.md and this repo's scripts/close-gate.sh, carry a warn-only arming
# row that reports `wired but inert: jq missing` as a state of its OWN, distinct from `wired`.
# So the state this line creates is named in the gate rather than only in this comment, which is
# what the old parenthetical here claimed and did not have.
#  What it is NOT: a warning you should expect to SEE. Measured in both directions. On a machine
# where jq is genuinely unresolvable, the gate reads its own manifest through jq and dies at its
# first read with rc 127, printing nothing — so the inert row never gets reached. And where only
# THIS hook's spawner has a stripped PATH — a GUI/launchd client with jq outside /usr/bin — the
# gate runs from a login shell, resolves jq, and prints the ✓ WIRED row while this very line
# exits 0. The row is therefore a CONTRACT that the state has a name and a place to be reported,
# not evidence that any user is told about it. The thing that would tell them is a warning
# emitted HERE, which this hook deliberately does not do -- it would change the hook's behaviour.)
# PLC-ANCHOR:jq-early-return -- the dependency envelope closes here, above every counter and helper
command -v jq >/dev/null || exit 0

# ── event parse ───────────────────────────────────────────────────────────────
# Empty stdin is NOT a parse failure: the python did `json.loads(x) if x else {}`, so an
# empty event carries on with all-default fields. Only malformed-or-not-an-object exits.
if [ -z "$INPUT" ]; then
  EV='{}'
else
  EV="$(printf '%s' "$INPUT" | jq -c 'if type == "object" then . else empty end' 2>/dev/null)" || EV=""
  [ -n "$EV" ] || exit 0          # unparseable or non-object -> fail-open
fi

# ── shared floor math ──────────────────────────────────────────────────
# `trim` / `intenv` / `floatenv` live in ONE file shared with close-gate-nudge.sh. They used to
# be byte-identical copies in both hooks, and the copies had already drifted once in a way that
# silenced a hook: the nudge lost the `* 1` this file carried. The
# reasoning for each definition lives in the library, next to the definition.
#
# The library path is NOT anchored on $CLAUDE_PLUGIN_ROOT. Verified: neither hook references any
# plugin-root variable, the hook may be wired by absolute path in a settings.json,
# and the suites invoke it as `/bin/bash "$IMPL"` with no such variable set -- a
# plugin-root anchor breaks every suite.
# `${var%/*}` returns $var UNCHANGED when there is no slash in it, so a slash-less invocation
# (`cd hooks && bash context-floor.sh`) would compose `context-floor.sh/lib/floor-env.sh`.
# Absolute and `./name` invocations are unaffected.
_lib_dir="${BASH_SOURCE[0]%/*}"
[ "$_lib_dir" = "${BASH_SOURCE[0]}" ] && _lib_dir="."
LIB="${PLC_FLOOR_LIB:-$_lib_dir/lib/floor-env.sh}"
# Sourced in a SUBSHELL, and only the variable is carried back out. `[ -r ]` would separate none
# of the shapes a failed or partial plugin update actually produces:
#   - the file is absent            -> `.` fails, nothing is printed
#   - the file has a syntax error   -> `.` fails partway, nothing usable is printed
#   - the file CONTAINS `exit`      -> the subshell dies, not this hook
#   - the file sources CLEANLY but sets the variable to text that is not a usable program
# The subshell is what handles the third: sourcing a file that calls `exit` exits the SOURCING
# shell, so a broken library could otherwise terminate the hook mid-event -- on a PreToolUse hook
# that is a failure with no message at all.
# shellcheck source=lib/floor-env.sh
PLC_FLOOR_JQ_DEFS="$( . "$LIB" >/dev/null 2>&1; printf '%s' "${PLC_FLOOR_JQ_DEFS:-}" )" || PLC_FLOOR_JQ_DEFS=""

# The fourth shape needs its OWN check.
# A library that sources cleanly and sets the variable to garbage, or to
# text defining nothing, arrives NON-EMPTY, sails past a bare `-z`, and dies inside the swallowing
# `2>/dev/null` on the floor program below -- silently, which is the exact class this branch
# exists to reject. So the text is PROBED: it must parse AND all three definitions must exist and
# answer correctly on a known input.
#
# THE PROBE INPUTS COVER ALL THREE BRANCHES -- absent, empty, and a real value.
# A probe of only an ABSENT variable exercises every definition through
# the `$unset` branch. A library reading `def intenv($n; $unset; $empty): $unset;` -- valid,
# complete, and ignoring the environment entirely -- answers that probe correctly and passes.
# MEASURED: with such a library the hook ignored an explicit `PLC_CONTEXT_FLOOR=0` and blocked at
# the 150K default, rc 2. A probe that only ever asks for an absent variable cannot distinguish
# "reads the environment" from "never reads anything".
#
# The `1e-400` case is the drift the shared library exists to prevent. Without the library's `* 1`, jq holds the literal
# at arbitrary precision and the value stays above zero, where python's C double underflows to
# 0.0 and falls through to the absolute floor. A library missing the `* 1` is therefore REJECTED here.
#
# WHAT REMAINS OUT OF SCOPE, stated rather than implied: version drift that changes none of the
# probed answers. This probe checks behaviour on eight known inputs; it is not a proof that two
# trees hold the same library, and nothing on this side of the boundary can be.
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
  # Fail OPEN -- a broken floor must never block work -- but never SILENTLY. An empty FLOORINFO
  # is indistinguishable from a legitimately disabled floor, and silent degrade is this hook's
  # entire failure history.
  #
  # At most ONE line per session, FOR A SESSION ID WHOSE KEY FITS IN A FILENAME. The key
  # exists here: `$INPUT` was captured at the top of the hook, long before the floor math, so the
  # session id is derivable at the point of failure, even though the hook
  # does not PARSE it until much later.
  #
  # THE QUALIFIER IS NOT HEDGING, IT IS THE MEASURED LIMIT. The key becomes a filename, so a
  # long enough one exceeds NAME_MAX, the `set -C` create fails, and `2>/dev/null || true` swallows
  # ENAMETOOLONG exactly as it swallows every other write failure -- no marker, no throttle, and the
  # line is printed on EVERY event for that session. Measured on APFS: the base name fails at 251
  # bytes and succeeds at 245, and a 200-element numeric array id (401 raw bytes) encodes to 815.
  # A sufficiently long STRING id hits this ceiling, and the
  # `%~nonstring-` construction narrows the margin for the shapes it serves, because `@uri`
  # spends three bytes on each of JSON`s punctuation characters. Bounding it needs a digest to stay
  # injective, and this gate`s dependency envelope is deliberately jq-only, so it is not done here.
  # An unqualified "at most ONE
  # line per session" is a claim wider than the mechanism.
  #
  # The id is derived the same way the hook derives it further down FOR EVERY SHAPE THE MARKER
  # DERIVATION KEYS -- the six falsy sentinels and the `k`-encoded string -- and deliberately
  # differently for the ONE shape it does not key at all. Deriving it a second, different way is
  # how an earlier version of this branch went wrong: a bespoke
  # `tr -c` encoding that is NOT injective (`a/b` and `a b` both key `a_b`, so one session's
  # warning swallows another's) plus an "absent id" hole that emitted an unthrottled line on every
  # single event.
  #
  # An earlier version of this branch ran `tostring` over every non-string id and
  # let a present-but-empty id fall into the absent sentinel, so `1`/`"1"`, `true`/`"true"` and
  # absent/`""` each shared ONE throttle file and one session's warning swallowed another's -- the
  # same collision the marker derivation once had. Measured before the fix: eight distinct ids, five
  # files. This site now uses the same tokens and the same encoder as the marker
  # derivation.
  #
  # THE TRUTHY NON-STRING IS WHERE THE TWO SITES DIVERGE, AND THE DIVERGENCE IS THE POINT. The
  # marker derivation gives `1` and `true` no key: an earlier field of that same program answers
  # TYPEERR and the hook exits 1, reproducing the pinned python`s uncaught TypeError. This branch
  # runs on the FAIL-OPEN path -- a floor that cannot load its library must never block work -- so
  # it cannot adopt an answer that is "exit 1", and it still needs those sessions throttled apart.
  # Hence `%~nonstring-<stringified>`: same sentinel namespace, which is unreachable by
  # the string encoder (`k` doubles `~` before `@uri`, and `@uri` renders a literal `%` as `%25`, so
  # a session id spelled `%~nonstring-1` encodes to `%25~~nonstring-1`). The stringified value goes
  # through `k` rather than landing raw because this key becomes a FILENAME and `[1,2] | tostring`
  # is not one.
  #
  # Mirroring the marker derivation exactly -- everything not falsy and not a string keying "" --
  # was measured and rejected: it separates the three colliding pairs above
  # while making `1` and `true` collide on a file literally named `.libwarn`. Trading a named
  # collision for an unnamed one is no fix.
  #
  # jq is available here: `command -v jq >/dev/null || exit 0` runs at the top of this hook, well
  # before this block.
  _lw_sid="$(printf '%s' "$INPUT" | jq -r 'def k: gsub("~";"~~") | gsub("(?<c>[A-Z])"; "~\(.c)") | @uri; if type != "object" or (has("session_id") | not) then "%~nosession" else (.session_id | if   . == null  then "%~nosession" elif . == false then "%~falsy-boolean-false" elif . == 0     then "%~falsy-number-0" elif . == ""    then "%~falsy-string-empty" elif . == []    then "%~falsy-array-empty" elif . == {}    then "%~falsy-object-empty" elif type == "string" then k else ("%~nonstring-" + (tostring | k)) end) end' 2>/dev/null || true)"
  [ -n "$_lw_sid" ] || _lw_sid="%~nosession"
  _lw_dir="${TMPDIR:-/tmp}/plc-context-floor"
  if mkdir -p "$_lw_dir" 2>/dev/null; then
    _lw_marker="$_lw_dir/$_lw_sid.libwarn"
    # THE THROTTLE MUST NOT BE REACHABLE THROUGH A NODE WE DID NOT WRITE. `$_lw_dir` lives under a
    # shared `${TMPDIR:-/tmp}` and the session id is derivable, so the path is plantable, and this
    # is the one branch whose entire job is not being silent.
    #
    # `-f` plus not-a-symlink alone closes the DIRECTORY shape, and leaves two more open:
    #   - a chmod-000 regular file passes `-f`, so a squat we could never have written silenced
    #     the whole session;
    #   - a FIFO at this path made `: > "$_lw_marker"` BLOCK -- open-for-write on a FIFO waits for
    #     a reader -- so the hook HUNG rather than degrading. Measured: killed at 12s, rc 124.
    #     `2>/dev/null || true` cannot save a redirect that never returns. In a PreToolUse hook
    #     that is a frozen edit, which is worse than the silence this branch exists to prevent.
    #
    # So: throttle only on a marker that is a regular file, not a symlink, and WRITABLE BY US --
    # the three properties true of a marker this hook wrote. Anything else at the path is a squat:
    # never written to (the write is what hangs) and never trusted (staying noisy is recoverable,
    # going silent is not). The create is guarded by `set -C` in a subshell so it fails rather than
    # follows if something appears between the test and the write.
    if [ -e "$_lw_marker" ] || [ -L "$_lw_marker" ]; then
      if [ -f "$_lw_marker" ] && [ ! -L "$_lw_marker" ] && [ -w "$_lw_marker" ]; then exit 0; fi
    else
      ( set -C; : > "$_lw_marker" ) 2>/dev/null || true
    fi
  fi
  printf 'project-lifecycle: context floor OFF -- shared library not usable (%s)\n' "$LIB" >&2
  exit 0
fi

# ── floor / step / window (env), and the pct-mode branch ──────────────────────
# The env READS stay here rather than in the library: they bind to a different downstream shape
# than the nudge's (this one also carries $step, and its non-finite branch signals OVERFLOW where
# the nudge maps to 0). Env quirks that look like bugs but are the original's semantics: an UNSET
# var takes the default, while an EMPTY var means 0 for PLC_CONTEXT_FLOOR (i.e. disabled) but
# still 1000000 for WINDOW and 30000 for STEP -- that asymmetry is python's `or "0"` vs
# `or "1000000"`, not an invention.
FLOORINFO="$(jq -nr "$PLC_FLOOR_JQ_DEFS"'
  intenv("PLC_CONTEXT_FLOOR";      150000; 0)        as $abs
  | floatenv("PLC_CONTEXT_FLOOR_PCT";    0; 0)       as $pct
  | intenv("PLC_CONTEXT_WINDOW";  1000000; 1000000)  as $win
  | intenv("PLC_CONTEXT_FLOOR_STEP"; 30000; 30000)   as $step
  # `nan > 0` and `-inf > 0` are both false in python too, so those fall through to the
  # absolute floor rather than entering pct mode.
  | if ($pct > 0 and $win > 0) then
      ( ($win * $pct / 100) as $f
        # python computed int(window * pct / 100) OUTSIDE any try, and the interpreter
        # call was not wrapped in `|| true`, so an infinite product raised OverflowError
        # and the hook exited 1 -- neither a clean allow (0) nor a block (2). Signal it.
        | if ($f | isinfinite) or ($f | isnan) then "OVERFLOW"
          else "\($f | floor)\t1\t\($step)\t\($win)\t\($pct)" end )
    else "\($abs)\t0\t\($step)\t\($win)\t\($pct)" end
' 2>/dev/null)" || FLOORINFO=""

[ -n "$FLOORINFO" ] || exit 0                  # jq itself broke -> fail-open
[ "$FLOORINFO" = "OVERFLOW" ] && exit 1        # reproduce python's uncaught OverflowError

FLOOR="${FLOORINFO%%$'\t'*}"; REST="${FLOORINFO#*$'\t'}"
PCT_MODE="${REST%%$'\t'*}";   REST="${REST#*$'\t'}"
STEP="${REST%%$'\t'*}";       REST="${REST#*$'\t'}"
WINDOW="${REST%%$'\t'*}"
FLOOR_PCT="${REST#*$'\t'}"

case "$FLOOR" in ''|*[!0-9-]*) exit 0 ;; esac
[ "$FLOOR" -le 0 ] && exit 0                   # disabled (escape hatch: PLC_CONTEXT_FLOOR=0)

# ── session identity and paths ────────────────────────────────────────────────
# NUL-separated, never @tsv. @tsv escapes tab, newline, carriage return AND backslash, so a
# transcript under `~/dir\name` reached the existence check as the six characters `a\tb`, failed
# it, and the hook exited 0 with nothing armed -- the floor silently disappeared for anyone with a
# backslash or a tab in a path. A session_id carrying one keyed a DIFFERENT session's marker for
# the same reason. NUL is the one byte a path cannot contain, so it is the only safe delimiter;
# it cannot survive `$(...)` (bash drops NULs from command substitution), hence the read loop.
# Reading exactly five records is the success condition -- a jq that died mid-stream yields fewer.
#
# The five records also carry python's `or` semantics, which jq's `//` does not have: `//` falls
# through for null and false only, while python's `or` also treats 0, "", [] and {} as absent.
# `{"session_id": 0}` therefore used to key state under "0" instead of "nosession" -- in the
# measured case reading another key's grace window and allowing an edit the floor had blocked.
# The same chain governs cwd, transcript_path and the file_path -> path fallback: a
# `{"file_path": "", "path": "RESUME.md"}` event lost its exemption and blocked the very write
# that clears the block.
#
# A TRUTHY NON-STRING sid or cwd made python raise TypeError from os.path.join, uncaught, exiting
# 1 with a traceback. That is signalled here rather than papered over; the traceback text itself
# is unreproducible, a known stderr-only divergence.
STATUS=""; SID=""; CWD=""; TPATH=""; TARGET=""; NF=0
while IFS= read -r -d '' FLD; do
  case "$NF" in
    0) STATUS="$FLD" ;; 1) SID="$FLD" ;; 2) CWD="$FLD" ;; 3) TPATH="$FLD" ;; 4) TARGET="$FLD" ;;
  esac
  NF=$((NF+1))
done < <(printf '%s' "$EV" | jq -j '
  def pyfalsy: . == null or . == false or . == 0 or . == "" or . == [] or . == {};
  def NUL: [0] | implode;
  .session_id as $s
  | .cwd as $c
  | .transcript_path as $t
  | (if (.tool_input | type) == "object" then .tool_input else {} end) as $ti
  # file_path -> path -> "", through python`s `or`, not jq`s `//`.
  | (if ($ti.file_path | pyfalsy | not) then $ti.file_path
     elif ($ti.path | pyfalsy | not) then $ti.path
     else "" end) as $tg
  | [ (if ((($s | pyfalsy | not) and ($s | type) != "string")
        or (($c | pyfalsy | not) and ($c | type) != "string")) then "TYPEERR" else "OK" end)
    # SENTINEL COLLISION, formerly: a session whose
    # id is the literal STRING "falsy-number-0" keys the same marker as session_id 0, exactly as
    # a session whose id is the literal string "nosession" has always keyed the same marker as an
    # event with NO id -- that pair is inherited from the python reference.
    # CLOSED by moving the SENTINELS out of the encoder image rather than prefixing the
    # ids. The paragraph above reasoned that closing this needs an escaping scheme over ALL keys,
    # reddening every fixture at once; that is true of the id-prefix design and of nothing else.
    # Only an ABSENT session_id keys "nosession". A present-but-falsy
    # one gets its own key, and a key per falsy VALUE rather than one shared "falsy" bucket --
    # collapsing 0, false, "", [] and {} together would fix the row the contract suite tests
    # (0 vs absent) while leaving four other pairs sharing a block and a grace window, i.e. a
    # claim wider than its mechanism. Tokens are literal and path-safe: they become marker
    # filenames.
    , (if   $s == null  then "%~nosession"
       elif $s == false then "%~falsy-boolean-false"
       elif $s == 0     then "%~falsy-number-0"
       elif $s == ""    then "%~falsy-string-empty"
       elif $s == []    then "%~falsy-array-empty"
       elif $s == {}    then "%~falsy-object-empty"
       # `@uri` because the key is INTERPOLATED INTO A PATH one line
       # later (`MARKER="$MDIR/$SID.marker"`), and an unencoded session_id therefore decides
       # where the hook writes. Measured on the PINNED PYTHON REFERENCE, so both of these are
       # inherited rather than port damage:
       #   session_id "a/b"        -> exit 0, NOTHING written anywhere. `mkdir -p` creates the
       #                              marker dir but not `$MDIR/a`, the write fails, and the
       #                              hook fails open -- the floor is SILENTLY OFF for that
       #                              whole session. The control (a normal id) exits 2.
       #   session_id "../escape"  -> exit 2, but the marker lands as `escape.marker` in the
       #                              PARENT of the marker directory. The hook writes outside
       #                              its own state directory.
       # `@uri` closes both: `/` becomes `%2F` so no subdirectory is implied and no traversal
       # is possible. It also encodes `%` itself, so the mapping stays INJECTIVE over string
       # ids -- closing a hole with an encoding that collides is not closing it.
       #
       # CLOSED from the SENTINEL side rather than by prefixing every real id. The
       # collisions that used to live here were a literal "nosession" keying the same marker as an
       # absent id, and a literal "falsy-number-0" keying the same marker as `0`.
       #
       # THE STRING BRANCH ALSO SURVIVES A CASE-FOLDING FILESYSTEM. `@uri` leaves A-Z raw, and this
       # key becomes a FILENAME, so on a folding volume two ids differing only by case landed on one
       # file. Encoder-injective is not storage-injective.
       # `~` is doubled FIRST and uppercase prefixed SECOND -- that order is the
       # correctness of the escape, since prefixing first lets a literal `~A` and a bare `A` produce
       # the same text. Ids with no uppercase and no `~` encode byte-for-byte as before.
       #
       # NO APOSTROPHES ANYWHERE IN THIS PROGRAM. It lives inside a single-quoted shell string; one
       # contraction inside a comment here closed that string early, swallowed the `then`, and made
       # the hook exit 2 on EVERY input, under-floor calls included.
       elif ($s | type) == "string" then ($s | gsub("~";"~~") | gsub("(?<c>[A-Z])"; "~\(.c)") | @uri)
       else "" end)
    , (if ($c | pyfalsy) then "" elif ($c | type) == "string" then $c else "" end)
    # A truthy non-string transcript_path went to os.path.exists(), which took an int as a FILE
    # DESCRIPTOR and answered False for anything not open. Empty reproduces that for every value
    # that is not a live fd; a live-fd transcript_path is out of scope in both implementations.
    , (if ($t | pyfalsy) then "" elif ($t | type) == "string" then $t else "" end)
    # A truthy non-string target raised inside python`s try and simply skipped the exemption,
    # which is what an empty target does here.
    , (if ($tg | type) == "string" then $tg else "" end)
    ] | .[] | (., NUL)' 2>/dev/null)
[ "$NF" -eq 5 ] || exit 0                      # jq died mid-stream -> fail-open
[ "$STATUS" = "TYPEERR" ] && exit 1            # reproduce python`s uncaught TypeError

# python fell back to os.getcwd(), which is the PHYSICAL directory. $PWD is bash`s LOGICAL one and
# keeps symlinks, so on a machine where /tmp is a symlink the two spell the same directory
# differently -- and the exemption below compares paths as strings.
PWD_PHYS="$(pwd -P 2>/dev/null)" || PWD_PHYS=""
[ -n "$PWD_PHYS" ] || PWD_PHYS="$PWD"
[ -n "$CWD" ] || CWD="$PWD_PHYS"
# A RELATIVE event cwd is resolved against the hook process's own directory, once, here. Claude
# Code is documented to send an absolute `.cwd`, so this is defence rather than a fix -- but the
# alternative is that `git -C`, `stat` and the string-comparing exemption each resolve it
# separately, which is the multiple-bases defect this file has paid for before. One base,
# decided before anything reads it.
case "$CWD" in /*) ;; *) CWD="$PWD_PHYS/$CWD" ;; esac

MDIR="${TMPDIR:-/tmp}/plc-context-floor"
MARKER="$MDIR/$SID.marker"
CLEAREDAT="$MDIR/$SID.clearedat"
# ── which checkpoint? ───────────────────────────────────────────────────
# The checkpoint is anchored on THE FILE BEING WRITTEN, not on the session cwd.
#
# `.cwd` is the session's working directory and it follows the agent's `cd`. In a workspace of
# sibling repos that made the demanded file change identity as the session moved: the floor
# blocked, the agent refreshed the RESUME.md of the repo it was working in -- the obviously
# correct action -- and the block did not clear, and could not by any correct behaviour.
# An unsatisfiable guard is a guard that
# gets disabled, and the env knob below is right there.
#
# An Edit/Write always carries a file_path. That is the one field in the event which says which
# project is being touched RIGHT NOW, so it is what the checkpoint is resolved from.
#
# Order: explicit env > the target's git root > the session cwd (unchanged from before).
#
#   * Explicit wins outright. A pinned path cannot need discovery, and it is also the documented
#     escape for layouts git cannot describe.
#   * The git boundary is the stop rule. Walking upward for a RESUME.md by NAME was rejected: a
#     stale leftover in a parent scratch directory would satisfy the walk and mask that the repo
#     being edited has never been checkpointed -- a silent pass, which is worse than a bleed with
#     a reason. Unbounded walks are the documented ESLint `~/.eslintrc` hazard.
#   * EVERY git failure falls through to the cwd default and none of them reaches the exit code:
#     not a repo, bare repo, a `safe.directory` refusal on a foreign-owned tree, or a target
#     directory that does not exist yet. Resolution that cannot run is not the same thing as a
#     checkpoint that is stale, and only the second one is the user's to act on.
#
# There is deliberately NO "target is under cwd, so use cwd and skip git" shortcut. It looks
# free and it is wrong exactly where this defect lives: a common layout is
# <workspace>/{repoA,repoB} with cwd at the workspace ROOT and a RESUME.md sitting there (put
# there as a workaround), so the repo IS under cwd and cwd DOES have a checkpoint.
# The shortcut would answer with the workspace file and reproduce the defect while passing any test
# whose cwd is a SIBLING of the repo. The contract suite has a row for exactly that case.
#
# The target is made absolute against the EVENT cwd, never the process cwd. Resolving it against
# the process cwd would introduce a third base into a file that already has two (see the
# exemption below), which is a divergence class the port has already hit.
# `git -C` is likewise mandatory: without it git resolves against the hook process's own
# directory, which in a test run is this checkout -- a real repo that may hold a real RESUME.md.
RESUME="${PLC_RESUME_PATH:-}"
RESUME_HINT=""            # set only when the hook CHOSE the path -- see the block message
if [ -z "$RESUME" ]; then
  RESUME="$CWD/RESUME.md"
  if [ -n "$TARGET" ]; then
    case "$TARGET" in
      /*) ABS_TARGET="$TARGET" ;;
      *)  ABS_TARGET="$CWD/$TARGET" ;;
    esac
    # `%/*` strips one component, which assumes the target is a leaf FILE. A real Edit/Write
    # always names a file, but nothing here enforced that, and a target naming a directory --
    # a repo root, say -- had its own root stripped off and resolved against the PARENT, which
    # is usually not a repo at all. One stat closes it.
    if [ -d "$ABS_TARGET" ]; then TDIR="$ABS_TARGET"
    else TDIR="${ABS_TARGET%/*}"; [ -n "$TDIR" ] || TDIR="/"; fi
    # A Write that creates a file in a directory that does not exist yet is ordinary, and
    # `git -C <missing>` simply fails -- which would drop the whole resolution back to cwd for
    # precisely the new-file case and leave target-based resolution half done. Climb to the nearest EXISTING
    # ancestor first; the repo membership of a path is not changed by walking to a parent that
    # is still inside the same repo.
    #
    # The real terminator is `$TDIR` reaching "/", which every path reaches in finitely many
    # steps. The counter is a pure backstop against a loop body that stops shortening the string,
    # and it is deliberately set far above any reachable component count (PATH_MAX is 1024 bytes
    # here, so at least two bytes per component caps a real path near 512). A cap of 64 would be
    # a SEMANTIC cutoff rather than a
    # backstop: a target with more than 64 nonexistent components would stop the walk early, git
    # would fail, and resolution would drop back to `$CWD` -- reintroducing this very defect on a
    # deep path. A backstop that changes the answer is not a backstop.
    TDEPTH=0
    while [ ! -d "$TDIR" ] && [ "$TDIR" != "/" ] && [ "$TDEPTH" -lt 1024 ]; do
      TDIR="${TDIR%/*}"; [ -n "$TDIR" ] || TDIR="/"
      TDEPTH=$((TDEPTH+1))
    done
    # stderr is redirected on the command itself, so bash's own "command not found" for a
    # missing git is suppressed too -- the redirection is in place before the exec is attempted.
    # A PreToolUse hook's stderr reaches the user, and `fatal: not a git repository` is printed
    # on every miss, which is the common case for anything outside a repo.
    TOP="$(git -C "$TDIR" rev-parse --show-toplevel 2>/dev/null)" || TOP=""
    # Only an absolute answer is trusted; empty output or anything else leaves the cwd default
    # in place. `--show-toplevel` returns the PHYSICALLY resolved path, so a repo reached through
    # a symlink comes back as its real root -- same file, so the mtime comparison below is
    # unaffected, and the exemption's basename branch still covers the checkpoint write.
    case "$TOP" in
      /*) RESUME="$TOP/RESUME.md"; RESUME_HINT=" ($RESUME)" ;;
    esac
  fi
fi

# ── RESUME exemption (deadlock guard) ─────────────────────────────────────────
# Never gate the checkpoint file itself -- writing/refreshing RESUME.md is the action
# that CLEARS the block, so gating it would deadlock. Exempt by absolute-path match OR a
# RESUME.md basename anywhere. Runs BEFORE the transcript read, exactly as the python did.
#
# The normalisation is LEXICAL (python used os.path.abspath, which strips ".." without
# resolving symlinks). Doing this in jq rather than bash 3.2 string loops keeps it
# readable and keeps `realpath` -- which WOULD resolve symlinks and therefore diverge --
# out of the picture.
# Two more details the first port flattened, both of which made it exempt a path python gated:
#
#   * TWO leading slashes. POSIX leaves exactly two implementation-defined, and python`s abspath
#     preserves them while collapsing three or more -- so `//x` and `/x` are different paths there.
#     A normpath that collapses two made them equal, and the exemption fired where python blocked.
#   * TWO different bases. The tool target is resolved against the EVENT`s cwd, but a RELATIVE
#     PLC_RESUME_PATH is resolved by abspath against the PROCESS cwd. Using one base for both made
#     a relative checkpoint path match a target it does not name.
if [ -n "$TARGET" ]; then
  EXEMPT="$(jq -nr --arg t "$TARGET" --arg c "$CWD" --arg r "$RESUME" --arg p "$PWD_PHYS" '
    def normpath:
      . as $p
      | (if   ($p | startswith("///")) then "/"
         elif ($p | startswith("//"))  then "//"
         elif ($p | startswith("/"))   then "/"
         else "" end) as $root
      | ($p | split("/") | map(select(. != "" and . != "."))) as $raw
      | (reduce $raw[] as $seg ([];
           if $seg == ".." then
             (if $root != "" then (if length > 0 then .[0:-1] else . end)
              else (if (length > 0 and (.[-1] != "..")) then .[0:-1] else . + [".."] end) end)
           else . + [$seg] end)) as $comps
      | if $root != "" then $root + ($comps | join("/"))
        else (if ($comps | length) == 0 then "." else ($comps | join("/")) end) end;
    def join_under($base): if startswith("/") then . else ($base + "/" + .) end;
    # python: join(cwd, target) first, then abspath() -- which joins against the process cwd only
    # if the result is STILL relative, then normalises once.
    ($t | join_under($c) | join_under($p) | normpath) as $ta
    | ($r | join_under($p) | normpath) as $ra
    | if $ta == $ra or ($ta | split("/") | last) == "RESUME.md" then "yes" else "no" end
  ' 2>/dev/null)" || EXEMPT="no"
  [ "$EXEMPT" = "yes" ] && exit 0
fi

# ── occupancy ─────────────────────────────────────────────────────────────────
[ -n "$TPATH" ] && [ -e "$TPATH" ] || exit 0   # python: os.path.exists gate, then fail-open
# `fromjson?` is the direct equivalent of the per-line try/except: a malformed JSON line
# is skipped and the scan continues.
#
# n() reproduces python's `(u.get(k) or 0)`, which coerced every FALSY value -- None,
# false, 0, "", [], {} -- to 0.
#
# A TRUTHY non-numeric field (e.g. "abc") raises. Unlike close-gate-nudge.sh, that error
# is NOT caught per line: python's arithmetic exception escaped the inner loop to the
# outer try wrapping the whole file read, returned None, and abandoned the entire scan.
# That was a defect -- one bad record anywhere silently disabled a blocking gate -- and
# it is NOT reproduced here: the program below skips such a record instead.
#
OCC_RAW="$(jq -Rr '
  def falsy: . == null or . == false or . == "" or . == [] or . == {};
  fromjson?
  | select(type == "object")
  | ((if (.message | type) == "object" then .message.usage else null end) // .usage) as $u
  | select(($u | type) == "object")
  | [ $u.input_tokens, $u.cache_read_input_tokens, $u.cache_creation_input_tokens ]
  # python evaluated `(u.get(k) or 0)`, coercing every FALSY value -- None, false, 0, "",
  # [], {} -- to 0. A TRUTHY non-numeric ("abc", [1]) instead raised, and that exception
  # escaped to the try wrapping the entire file read: occupancy became None and the gate
  # silently vanished. This program skips that record instead.
  | if   any(.[]; (type != "number") and (falsy | not)) then empty
    else (map(if type == "number" then . else 0 end) | add) end
  | select(type == "number" and . > 0)
' "$TPATH" 2>/dev/null)" || exit 0             # jq itself broke / unreadable -> fail-open
# Last non-zero wins: the python reassigned `occ` on every hit and kept the final one.
OCC="$(printf '%s\n' "$OCC_RAW" | tail -1)"
# Occupancy may legitimately be FRACTIONAL: python summed whatever JSON numbers it found,
# so a float token count stays a float and is compared as one. An integer-only guard here
# silently dropped such a transcript to fail-open. Validate and compare in jq, not in
# bash arithmetic, which cannot represent it.
[ -n "$OCC" ] || exit 0
jq -ne --arg o "$OCC" '($o | tonumber?) // empty | . > 0' >/dev/null 2>&1 || exit 0
jq -ne --arg o "$OCC" --argjson f "$FLOOR" '($o | tonumber) < $f' >/dev/null 2>&1 && exit 0

# ── which checkpoint earned the grace? ──────────────────────────────────
# The grace window used to be keyed by session id ALONE, so a window earned by refreshing repo A's
# checkpoint went on suppressing arming while the floor was measuring repo B's. Target-based
# resolution fixed WHICH FILE is measured; it did not touch WHOSE grace is honoured, and those are two different questions that
# were being answered by one key.
#
# Keyed on the very path the floor already resolved above, so "which file we measure" and "whose
# grace we honour" cannot drift apart -- every alternative (the git root, the target directory, an
# inode pair) adds a SECOND resolution rule, and two rules are how they diverge. It answers the
# N>=2 alternating case for free: distinct checkpoints, distinct records.
#
# ENCODED, NOT HASHED. Hashing is the obvious choice when identity lives in a FILENAME,
# because an encoded absolute path can exceed the
# FILENAME limit -- but here identity lives in the record's CONTENT, not in the state
# FILENAMES.
# In CONTENT there is no length limit to defend,
# and keying the grace on the resolved checkpoint path is served
# STRICTLY BETTER by an injective encoding: `@uri` is injective over strings because it also encodes
# `%`, so two distinct checkpoints cannot share a key BY CONSTRUCTION. A digest could only ever make
# that an empirical hope, and the digests available inside this hook's envelope are cksum-grade.
# Closing a collision-shaped hole with something that can collide is not closing it -- the same
# argument that picked `@uri` for the session id.
CKEY="$(jq -nr --arg r "$RESUME" '$r | @uri' 2>/dev/null)" || CKEY=""

# ── post-checkpoint grace ─────────────────────────────────────────────────────
# TWO fields, one per line, and the second one is REQUIRED. A record written before this change has
# no second line and therefore grants no grace -- fail-CLOSED, which costs at most one extra block
# and never grants an unearned window. That direction is the whole bias of this file.
if [ -f "$CLEAREDAT" ]; then
  # Line-oriented, not `tr -d ' \t\n'`. The old reader stripped ALL whitespace from the whole file,
  # which cannot tell two fields apart. Reading exactly two lines keeps the framing independent of
  # the path's bytes; `@uri` above then guarantees the second line contains none of them anyway.
  # The port's own defects all lived in value encoders, so the framing is not left to
  # chance twice.
  # EVERY READER OF THIS FILE WAS AUDITED BEFORE THE FORMAT CHANGED. The command is recorded
  # so the next person re-runs it instead of trusting this sentence; an audit nobody can re-run is
  # not evidence:
  #
  #   grep -rn --include='*.sh' --include='*.py' --include='*.md' \
  #        -e 'clearedat' -e 'CLEAREDAT' . | grep -v '^\./\.git/'
  #
  # A reader that feeds the content into arithmetic must take `head -n 1` -- a second line aborts it.
  CA=""; CK=""
  { IFS= read -r CA; IFS= read -r CK; } < "$CLEAREDAT" 2>/dev/null || true
  CA="$(printf '%s' "$CA" | tr -d ' \t')"
  CK="$(printf '%s' "$CK" | tr -d ' \t')"
  case "$CA" in
    # python's read_int() used int(), which REJECTS a decimal string -- so a fractional
    # clearedat reads back as absent, not as a number. Keep the integer-only pattern here
    # even though OCC itself may be fractional; they are different functions.
    ''|*[!0-9-]*) : ;;
    # A missing, empty or non-matching second field is "no grace" -- never a crash, never a
    # fail-open. The opposite shape -- a single dirty record
    # voiding the whole gate, silently, for a session -- is exactly what this avoids.
    *) if [ -n "$CK" ] && [ -n "$CKEY" ] && [ "$CK" = "$CKEY" ]; then
         jq -ne --arg o "$OCC" --argjson c "$CA" --argjson s "$STEP" \
           '($o | tonumber) < ($c + $s)' >/dev/null 2>&1 && exit 0
       fi ;;
  esac
fi

# ── arm ───────────────────────────────────────────────────────────────────────
# Guarded, never an unconditional `: >`. Truncating on every over-floor call would make
# the marker newer than any RESUME.md that could possibly follow, and the hook would
# block forever.
FIRST_ARM=0
# PLC-ANCHOR:statedir-failopen -- cannot manage the marker directory -> fail OPEN, leaving no aside node
mkdir -p "$MDIR" 2>/dev/null || exit 0         # cannot manage marker -> fail-open
# `[ ! -f ] || [ -L ]` -- "no REGULAR, non-symlink marker is here" -- not `[ ! -e ]`.
#
# `-e` was true of a DIRECTORY, a FIFO or a socket sitting at the marker path, so the whole arm block
# was SKIPPED for them: no marker was created, the symlink repair below was never reached, and the
# node arrived intact at the clear path with a FROZEN mtime. Any RESUME.md is then newer than a frozen
# mtime forever, so every over-floor call cleared the block and collected a STEP-sized grace window.
# Measured: `0000` over four calls -- the floor silently OFF for the entire session.
#
# `-f` FOLLOWS symlinks, which is why the `-L` disjunct is not redundant: a symlink pointing at a real
# file satisfies `-f` and would otherwise skip the block, taking the "a symlink at the marker path is
# corrupt guard state" repair with it.
# PLC-ANCHOR:arm-block-entry -- the arm block is entered only from here
if [ ! -f "$MARKER" ] || [ -L "$MARKER" ]; then
  # `[ ! -f ]` above is a CHECK; this is the CREATE; and the first-call branch hands the winner of that pair a
  # free call. Plain `>` truncates a file that appeared in between, so every process in a
  # concurrent Edit/Write batch would set FIRST_ARM=1 and every one of them would be allowed --
  # measured at 20/20 allows at batch width 2 and 30/30 at width 3, i.e. the granted unit
  # silently becomes "one batch of arbitrary width" instead of "one call". `set -C` makes the
  # redirect O_EXCL, so exactly one process can win.
  #
  # A failed O_EXCL create has THREE causes and they must not be merged:
  #   - the marker now exists   -> someone else won the race. We are NOT the first call; fall
  #                                through to the mtime comparison like any later call.
  #   - the path is a SYMLINK   -> CORRUPT GUARD STATE. Not a marker, and not a write failure.
  #                                Repair it: `rm` unlinks the symlink ITSELF and never follows it,
  #                                so whatever it pointed at is untouched, and the retry then
  #                                creates a real marker. Both simpler answers were measured and
  #                                both are wrong:
  #                                  * fail open (what `[ -e ]` alone does, since `-e` is FALSE for
  #                                    a dangling link) -> nothing is ever created, so every later
  #                                    call fails open too: 00000 over five calls, a permanent
  #                                    silent allow surviving every clear. Strictly worse than the
  #                                    `rm <marker>` bypass the block message deliberately
  #                                    withholds, which buys one call.
  #                                  * just block -> 22222, but the marker still never exists, so
  #                                    mtime_of returns nothing forever and the clear branch below
  #                                    can never run. Refreshing RESUME.md -- the ONE action the
  #                                    block message names -- does not clear it. An unclearable
  #                                    block is the cardinal sin this file's header describes: it
  #                                    trains the operator to set PLC_CONTEXT_FLOOR=0 and leave it.
  #                                Repairing is the only outcome that is both un-bypassable and
  #                                recoverable, and it beats the pre-fix code, which got there by
  #                                WRITING THROUGH a link someone else controls.
  #   - it still does not exist -> a genuine write failure (permissions, full disk). Fail OPEN,
  #                                exactly as this line did before.
  #
  # Redirections are applied left to right, so `: > "$MARKER" 2>/dev/null` prints bash's
  # own "Permission denied" -- and, under `set -C`, "cannot overwrite existing file" -- to the
  # STILL-UNREDIRECTED stderr before the 2>/dev/null takes effect. The python failed silently
  # here; a leaked diagnostic is a behaviour change, and on a PreToolUse hook it surfaces to
  # the user. Redirect stderr first. (The outer redirect is belt-and-braces: measured, the inner
  # one alone already suppresses the noclobber diagnostic.)
  # REPAIR A NON-REGULAR NODE **BEFORE** ANY ATTEMPT TO OPEN THE PATH.
  #
  # The position is the whole of this fix, and it was measured the hard way. Placed AFTER the create
  # (the obvious spot, next to the symlink repair) the hook HANGS on a FIFO: opening a FIFO for
  # write blocks until a reader appears, and `set -C` does not help because noclobber governs regular
  # files. The probe never returned. That is strictly worse than the defect being fixed -- a non-regular marker turns
  # the floor off, an indefinite hang stalls the agent's tool call forever -- and it is invisible to
  # any assertion that only reads exit codes, because there is no exit code.
  #
  # So the type test comes first and the path is never opened until it is known to be openable.
  #
  # REPAIR BY RENAMING ASIDE, never by deleting. A survey of comparable tools is unanimous in one direction:
  # every tool that removes a foreign node gates it behind an explicit operator action
  # (`npm --force`, `docker -f`, `terraform force-unlock <ID>`), and none of those exist inside an
  # unattended PreToolUse hook. Recursive deletion is the one documented data-loss shape in that
  # survey. Rename is also the only repair that works on a NON-EMPTY directory -- measured, `rm -f`
  # removes FIFOs and sockets and an empty directory needs `rmdir`, but a non-empty one resists both.
  # What actually put all three shapes on the clear path is that EXISTENCE skipped arming, not that
  # removal failed.
  #
  # Symlinks are NOT handled here. They are handled one branch down, and unlinking a link is not the
  # same act as moving the thing it names.
  #
  # The destination carries the PID **and** a counter. PID alone is not enough: two repairs inside ONE
  # session would land on the same name and the second would overwrite the first, which is exactly
  # the "fixed string a second corrupt node overwrites" shape this repair must avoid.
  #
  # THE REPAIR RUNS UNDER A MUTEX, and the paragraph that used to sit here was WRONG. It said the
  # move/create pair is not atomic, named the gap between them, and then argued the gap was harmless
  # because a process landing in it "wins the ordinary O_EXCL create and receives the ordinary
  # one-call grant". MEASURED, and it does not: 18 of 100 concurrent iterations under load granted
  # TWO allows, one granted three. Idle, the same fixture is green.
  #
  # The mechanism, pinned by instrumenting the aside nodes: `[ ! -f ]` and `mv` are not one act.
  # A stats the corrupt directory, moves it aside, and creates a REGULAR marker. B stat'd the same
  # directory a moment earlier, and only now runs its `mv` -- which SUCCEEDS, on A's freshly created
  # regular marker. Both aside nodes are then present with different types (`drwx` and `-rw-`), the
  # marker path is empty again, B's O_EXCL create succeeds, and B holds a first-arm grant too. The
  # previous fix guarded the case where `mv` FAILS; this is the case where it succeeds on the wrong
  # node.
  #
  # `mkdir` is the mutex because it is the atomic primitive POSIX actually gives a shell: it either
  # creates the directory or fails, with no window. That is true of `mkdir` and it is NOT true of the
  # critical section it opens: this comment used to continue "and no second repairer exists", and that
  # clause is false -- MEASURED, on this code. See "WHAT THIS LOCK ACTUALLY GUARANTEES"
  # below, which names the three windows and the measurement that opened each one. The re-stat inside
  # is a real precondition only against repairers that arrive after the acquire's own type test.
  #
  # A LOCK-LOSER DOES NOT REPAIR AND MUST NOT FALL THROUGH TO THE COMPARISON: the corrupt node is
  # still there for it, and `stat -L` on a directory yields a frozen mtime that any checkpoint beats
  # forever -- the frozen-marker defect again, as an extra allow. It blocks instead (see the guard below the create),
  # which self-heals on the very next call once the holder has finished.
  #
  # A STALE LOCK IS RECLAIMED BY OWNERSHIP, NOT BY A CLOCK. A process
  # SIGKILLed while holding the lock does not merely "stop this session repairing";
  # the real consequence is the cardinal sin at the top of
  # this file: with the corrupt node still in place, every later call fails to take the lock, fails to
  # create, and blocks -- and refreshing RESUME.md cannot clear it, because no marker mtime exists to
  # compare against. A PERMANENT, UNCLEARABLE block, escapable only by disabling the floor.
  #
  # So the holder records its PID inside the lock and a loser asks the kernel whether that process is
  # still alive (`kill -0`). Gone means the lock is an artefact of a death, and the loser removes it
  # and competes for it again -- ONCE, so a pathological loop cannot form. This is a liveness test,
  # not a timeout: no clock, no threshold, nothing to tune.
  # PID reuse could in principle keep a stale lock alive one extra call;
  # that is bounded and self-correcting, unlike the wedge it replaces.
  #
  # ── WHAT THIS LOCK ACTUALLY GUARANTEES ──
  #
  # IT DOES NOT GUARANTEE THAT REPAIR IS MUTUALLY EXCLUSIVE. It guarantees something strictly
  # narrower, and the gap between the two is what intermittent concurrency failures report:
  #
  #     a caller that arrives AFTER the holder has stamped its pid does not re-enter repair.
  #
  # Everything before that stamp is unprotected, and two more windows sit downstream of it.
  #
  # THE THREE ARE NOT EQUALLY EVIDENCED, and the difference is stated here rather than levelled out.
  # W1 and W2 were each opened by widening them with a `sleep` -- no logic removed -- and each was
  # measured against a control that adds the same assertion WITHOUT the widening. **W3 was NOT
  # separately widened or measured.** It is a code-inspection consequence of W1: once a second
  # repairer exists, an unconditional `rm -rf` of the lock necessarily removes somebody else's. The
  # premise of that consequence IS observed -- the release-time assertion fires, so the lock genuinely
  # is not ours by then -- but the removal of another repairer's lock was never watched happening.
  # Read W3 as "follows from W1 plus one unguarded line", not as a third measurement.
  #
  # W1 -- CLOSED BY THE ATOMIC ACQUIRE BELOW. Kept in full, because this stanza is the
  #   only written record of what the defect WAS, and a fix whose motivation has been deleted is one
  #   refactor away from being undone by someone who reads the new code as arbitrary.
  #   WHAT IT WAS: the lock was taken by `mkdir` and stamped with its owner pid a few lines later. In
  #   between it was a directory with no `pid` file in it. A second caller reaching the reclaim
  #   stanza read an empty owner, classified the LIVE lock as ownerless, `rm -rf`d it, and then took
  #   the lock itself. Two repairers then held what is nominally one lock.
  #   EVIDENCE TIER -- MEASURED, both directions. Widen the take->stamp gap and
  #   assert at release that the lock still carries our own pid: a steal is reported
  #   (`STOLEN self=<pid> found=<another pid>`).
  #   The identical assertion with no widening -> ZERO. Not an inference: the widened and
  #   unwidened arms are the same code path, run side by side.
  #   W1 ALONE DOES NOT PRODUCE A SECOND ALLOW:
  #   the widened run still left the suite green with every batch granting
  #   exactly one. A broken invariant is not yet a broken outcome, and only the outcome is asserted.
  #   HOW IT IS CLOSED: the acquire publishes the CONTENT (the pid, into a per-pid staging name) and
  #   only then publishes the NAME (`ln`, whose EEXIST failure IS the exclusion). There is no instant
  #   in which the lock's name is visible and its owner is not, so the state the reclaim stanza used
  #   to misread cannot occur. The reclaim's empty-owner arm is KEPT as a fail-safe and is no longer
  #   window-reachable -- reaching it now requires the filesystem to have lost the content.
  #
  # W2 -- THE RE-STAT IS AT [[skills/project-lifecycle/hooks/context-floor.sh#restat-under-lock]], THE RENAME AT [[skills/project-lifecycle/hooks/context-floor.sh#repair-rename]], AND THE SCAN AT [[skills/project-lifecycle/hooks/context-floor.sh#candidate-scan]] RUNS
  #   BETWEEN THEM. The re-stat establishes "the node is still corrupt"; the `mv` is what acts on it;
  #   nothing rechecks in between, and `mv` does not care that its target stopped being corrupt. A
  #   second repairer still inside the scan when the first completes BOTH its rename and its create
  #   emerges to find a REGULAR marker at the path and moves it aside anyway. That is precisely the
  #   scenario set out at the head of this stanza ("A stats the corrupt directory..."), which this
  #   mutex was introduced to close -- it closed the single-repairer half of it.
  #   MEASURED: widen W1 and W2 together -> the concurrent-repair row fails every batch, `worst=2`.
  #   The debris has a telling shape: one aside
  #   node is a DIRECTORY (the genuine corrupt node) and one is a REGULAR FILE (a legitimate marker
  #   that a later repairer moved). NODE TYPE IS THE DISCRIMINATOR, and it is what tells this apart
  #   from a resource fail-open, which leaves no aside node at all.
  #
  # W3 -- CLOSED: THE RELEASE AT [[skills/project-lifecycle/hooks/context-floor.sh#lock-release]] NOW CHECKS OWNERSHIP. An unconditional removal of `$_cflock`
  #   meant that once W1 had admitted a second repairer the FIRST one deleted the SECOND one's lock on its way
  #   out, and a third caller could enter behind it. That is why the aside nodes in a bad round were not
  #   bounded at two, and it is the mechanism behind the three-asides-on-three-pids shape seen
  #   in bad rounds.
  #
  # WHY A QUIET HOST SAYS ZERO AND A SMALL SHARED RUNNER DOES NOT. The control -- real code, ownership
  # assertion, no widening -- can report ZERO steals on an idle many-core developer machine. These
  # windows are a few instructions wide; being preempted inside one is a function of RUNNABLE THREADS
  # PER CORE, not of load average, which is why merely loading a many-core host
  # reproduces nothing, while a 2-4 vCPU shared runner driving a dozen concurrent processes preempts there
  # routinely. So "a flaky test, not a live defect" and "the guard handed out a second
  # allow" are not both casually true: the second reading is the correct one. A host whose runs are
  # all green may simply never have REACHED the window.
  # "Did not reach", not
  # "cannot reach": a zero observation on one host bounds the rate, it does not establish an
  # impossibility, and rare preemption on many cores is not excluded by any measurement taken.
  #
  # WHAT IS PROVEN AND WHAT IS ONLY CONSISTENT -- said here because the difference is exactly the
  # kind of over-claim this file keeps catching in itself. PROVEN: this code can hand out a second
  # allow, by a named mechanism, reproducibly. NOT PROVEN: that a given intermittent red came from
  # THIS mechanism, unless it was captured with its state directory attached -- that is
  # what the forensic collector was added for.
  # The evidence
  # tying the two together is that the debris shapes match (one directory aside, one regular-file
  # aside, `worst=2`) and that a resource fail-open, the only other mechanism known to produce the
  # same signature, leaves no aside node at all. That is a strong consistency argument and it is
  # not an identity proof. Anyone reading a future red should still check the listing rather than
  # assume this entry already answered it.
  #
  # ALL THREE ARE CLOSED BELOW. The fix changes the
  # ownership model of the repair (acquire and stamp atomically; recheck the node type immediately
  # before the `mv`; verify ownership before releasing), and each of those is applied below, at the
  # acquire, at the repair rename and at the release.
  _cfl="$MDIR/$SID.repair"           # the lock: a REGULAR FILE whose content IS the owner pid
  _cft="$MDIR/$SID.repair.tmp.$$"    # staging name, per-pid, never contended, never the lock
  # RECLAIM, CURRENT SHAPE -- a regular file whose content is the pid.
  if [ -e "$MARKER" ] && [ ! -L "$MARKER" ] && [ ! -f "$MARKER" ] && [ -f "$_cfl" ]; then
    _cfowner="$(cat "$_cfl" 2>/dev/null || true)"
    case "$_cfowner" in
      # FAIL-SAFE, AND NO LONGER A WINDOW -- kept AND kept explained, because a reader who does not
      # know its history will read it as dead code and delete it. Before the atomic publish below,
      # this arm destroyed LIVE locks: the owner was legitimately absent for the three lines between
      # `mkdir` and the stamp, so a rival arriving in that gap read an empty owner, classified a live
      # lock as ownerless and removed it. That was W1. The publish now carries the content, so
      # reaching this arm requires the FILESYSTEM to have lost it -- a genuinely broken lock, which
      # is exactly what should be reclaimed.
      ''|*[!0-9]*) rm -f "$_cfl" 2>/dev/null || true ;;
      *) kill -0 "$_cfowner" 2>/dev/null || rm -f "$_cfl" 2>/dev/null || true ;;
    esac
  fi
  # RECLAIM, LEGACY SHAPE -- a DIRECTORY here is a pre-fix holder or its corpse. `$MDIR` outlives a
  # single invocation, so the FIRST RUN OF THIS CODE can find one left by the previous version.
  # Without this branch an abandoned pre-fix lock is unreclaimable, which is the cardinal sin this
  # file's header describes -- introduced BY the upgrade. Retire it one release later, deliberately.
  if [ -d "$_cfl" ]; then
    _cfowner="$(cat "$_cfl/pid" 2>/dev/null || true)"
    case "$_cfowner" in
      ''|*[!0-9]*) rm -rf "$_cfl" 2>/dev/null || true ;;
      *) kill -0 "$_cfowner" 2>/dev/null || rm -rf "$_cfl" 2>/dev/null || true ;;
    esac
  fi
  # RECLAIM, ANY OTHER SHAPE. A symlink, FIFO or socket at the lock path can NEVER be a lock this
  # code created -- the only two shapes it makes are the regular file below and, historically, the
  # directory above -- so anything else is debris and is removed. It is not an edge case:
  # with it missing, such a node was reclaimed by
  # nothing, `ln` failed against it forever, `_cflock` stayed empty on every call, and every later
  # call fell to the lock-loser branch and exited 2 -- a PERMANENT, UNCLEARABLE block, which this
  # file's own header names as the cardinal sin. `-L` is tested FIRST because a symlink to a regular
  # file passes `-f`.
  if [ -L "$_cfl" ] || { [ -e "$_cfl" ] && [ ! -f "$_cfl" ] && [ ! -d "$_cfl" ]; }; then
    rm -f "$_cfl" 2>/dev/null || true
  fi
  # ACQUIRE -- CONTENT FIRST, NAME SECOND. `ln` is the publish and its EEXIST failure IS the
  # exclusion, so there is no instant in which the lock's NAME is visible and its OWNER is not.
  #
  # `ln`'s EEXIST IS NOT THE WHOLE EXCLUSION, AND BELIEVING IT WAS SHIPPED A CRITICAL DEFECT.
  # MEASURED, with a
  # positive control: `ln <file> <existing-regular-file>` fails `File exists`, rc=1 -- but
  # `ln <file> <existing-DIRECTORY>` returns rc=0 and links the file INSIDE the directory. That is
  # ordinary POSIX `ln` (the "link into target_dir" form), not a platform quirk.
  #
  # Why that mattered exactly here: the legacy lock shape is a DIRECTORY, kept on purpose for the
  # upgrade path, and the branch above deliberately leaves it alone when its owner is still ALIVE.
  # So a live pre-fix holder plus a new-code acquirer gave `ln` rc=0, the acquirer believed it held
  # the lock, and BOTH repaired -- W1 reproduced, in the one window this stanza's own comments say
  # will occur. The release then `rm -f`d a directory, which is a silent no-op, so nothing even
  # cleaned up after it.
  #
  # TWO GUARDS, AND THE SECOND IS THE LOAD-BEARING ONE. The `[ ! -d ]` test is cheap and closes the
  # common case; on its own it is a time-of-check race. The POST-CONDITION below is what actually
  # decides: after a successful `ln` we must find a REGULAR file at the lock path whose content is
  # OUR pid. If we do not, the `ln` landed somewhere else and we hold nothing.
  # Plain `>` on the staging file on purpose, NOT `set -C`: a temp left behind by our own SIGKILLed
  # prior incarnation carries this same pid, and no live process can ever hold this name.
  #
  # THE STAGING STEP IS ITS OWN TEST. Written first
  # as one `&&` chain -- marker-type tests, staging write and `ln` together -- with the diagnostic
  # below in the single `else`, the diagnostic then printed on
  # an ORDINARY blocked call with a perfectly good regular marker, which never went
  # near the repair path at all: the chain's `else` catches "no repair was needed" as readily as
  # "the acquire failed". So the comment below claiming it "cannot be noisy in practice" was FALSE
  # AS WRITTEN, and it was false on the most common call there is. `_cfstaged` is what separates
  # "we tried and could not" from "we never tried", and only the first is worth a word on stderr.
  #
  # THE STAGING PATH IS HARDENED TOO. Every node
  # type this file worries about was checked at `$MARKER` and at the lock -- and NOT here, at the one
  # path the atomic acquire INTRODUCED. The staging name is predictable (`<sid>.repair.tmp.<pid>`) and the
  # write below is a plain redirection, so:
  #   * a FIFO planted here makes `>` BLOCK, with no reader, FOREVER. Measured: still blocked after
  #     2s and killed. That is worse than anything else in this file -- the hook does not fail open,
  #     it HANGS, and every Edit/Write in the session hangs behind it. Nothing in this file's
  #     fail-open discipline covers a hang, because until now nothing could hang.
  #   * a symlink planted here is FOLLOWED by the write. Measured: a victim file's contents were
  #     replaced by the staged pid through the link. The guard would be the thing doing the writing.
  # `rm -f` clears a symlink, FIFO, socket or stale regular file. A DIRECTORY is left alone and the
  # staging write then fails (measured rc=1), which takes the not-acquired path rather than reaching
  # for `rm -r` inside `$TMPDIR` -- a recursive delete here is a bigger decision than the defect.
  rm -f "$_cft" 2>/dev/null || true
  _cfstaged=0
  if [ -e "$MARKER" ] && [ ! -L "$MARKER" ] && [ ! -f "$MARKER" ] \
     && printf '%s\n' "$$" > "$_cft" 2>/dev/null; then
    _cfstaged=1
  fi
  if [ "$_cfstaged" = 1 ] && [ ! -d "$_cfl" ] \
     && ln "$_cft" "$_cfl" 2>/dev/null; then          # bare `ln` -- NEVER `ln -f`, which clobbers
    # THE POST-CONDITION. A regular file, not a symlink, carrying OUR pid -- anything else means the
    # link landed somewhere that is not the lock, and we hold nothing.
    if [ -f "$_cfl" ] && [ ! -L "$_cfl" ] && [ "$(cat "$_cfl" 2>/dev/null || true)" = "$$" ]; then
    _cflock="$_cfl"
    trap 'rm -f "$_cflock" "$_cft" 2>/dev/null || true' EXIT
    rm -f "$_cft" 2>/dev/null || true                 # link count back to 1; the lock survives
    # RE-STAT UNDER THE LOCK. Between the outer test and here, another process may have completed
    # the whole repair; without this line we would move ITS marker aside, which is the defect.
# PLC-ANCHOR:restat-under-lock -- establishes "the node is still corrupt" once the lock is held
    if [ ! -e "$MARKER" ] || [ -L "$MARKER" ] || [ -f "$MARKER" ]; then
      rm -f "$_cflock" 2>/dev/null || true; trap - EXIT; _cflock=""
    fi
    else
      # `ln` SAID YES AND WE STILL DO NOT HOLD IT. The one shape that produces this is a directory at
      # the lock path, where `ln` nests the staging file inside instead of failing -- so remove the
      # link it created in there rather than leaving debris in another holder's lock, and take the
      # not-acquired path. Deliberately NOT the classification message below: this is contention with
      # a legacy holder, which is ordinary, not a host on which repair can never engage.
      rm -f "$_cfl/${_cft##*/}" 2>/dev/null || true
      rm -f "$_cft" 2>/dev/null || true
      _cflock=""
    fi
  else
    # CLASSIFY THE FAILURE, do not absorb it. `ln` failing EEXIST is ordinary contention and is the
    # whole design. `ln` failing for ANY OTHER REASON -- `EXDEV`/`ENOTSUP` on an exotic `$TMPDIR`, a
    # permissions problem, a filesystem with no hard links at all -- took the identical branch, so
    # repair would silently never engage on such a host FOREVER while looking exactly like a healthy,
    # busy lock. The lock path answers which: present means contention, absent means something else.
    #
    # UNCONDITIONAL stderr, deliberately NOT behind a debug knob. Gating this on a knob would make
    # the signal invisible in production, which is the silent-degrade class the line exists to close,
    # reintroduced by the line closing it. It is NOT a block message -- it names no path and demands
    # no action, because an agent once read a suggested `rm` out of an error message and deleted the
    # guard's state to get past the guard.
    #
    # THE NOISE BOUND IS NOW A MEASUREMENT RATHER THAN A CLAIM: both guards are required, and the
    # `_cfstaged` half was added because without it this printed on an ordinary blocked
    # call. It fires only when this process reached the publish and `ln` failed with the lock path
    # ABSENT -- i.e. not contention and not "no repair needed", which is the whole classification.
    #
    # `-L` IS TESTED TOO, AND ITS ABSENCE WAS A MISDIAGNOSIS RATHER THAN A GAP. `-e` FOLLOWS a
    # symlink, so a DANGLING one at the lock path made this read "the path is free" -- while `ln`
    # had correctly failed `File exists` against it, because `link()` answers by directory entry and
    # does not follow. Both halves measured. The
    # node is reclaimed above now, so this should not be reachable by that shape any more; the test
    # stays because a message that says the opposite of the truth is worse than no message.
    if [ "$_cfstaged" = 1 ] && [ ! -e "$_cfl" ] && [ ! -L "$_cfl" ]; then
      printf '[context-floor] repair lock could not be created and the path is free\n' >&2
    fi
    rm -f "$_cft" 2>/dev/null || true
    _cflock=""
  fi
  if [ -n "${_cflock:-}" ]; then
    _cfn=0; _cfaside=""
    while [ "$_cfn" -lt 100 ]; do
# PLC-ANCHOR:candidate-scan -- the aside-slot scan; it is what takes time between the re-stat and the rename
      _cfcand="$MDIR/$SID.corrupt.$$.$_cfn"
      if [ ! -e "$_cfcand" ] && [ ! -L "$_cfcand" ]; then _cfaside="$_cfcand"; break; fi
      _cfn=$((_cfn+1))
    done
    # RE-TEST THE NODE TYPE HERE, BETWEEN THE SCAN AND THE RENAME -- not before the scan. The scan is
    # what takes time (up to a hundred `[ -e ]` probes), so a check placed before it re-opens exactly
    # the gap it is meant to close. `mv` does not care that its target stopped being corrupt: without
    # this line a repairer emerging from the scan will rename aside a perfectly good REGULAR marker
    # that somebody else finished creating while it was looking for a slot.
    #
    # THIS SHRINKS W2. IT DOES NOT ELIMINATE IT, and the difference is stated here rather than left
    # for a reader to assume, because assuming the stronger one is how a partial fix gets quoted as a
    # total one. `mv` is still not atomic with its own test -- the node can change between this line
    # and the next. What ELIMINATES the second repairer is the atomic acquire above, which makes it
    # impossible for two processes to be inside this stanza at once. TWO INDEPENDENT MECHANISMS,
    # neither of them claimed total on its own: this one narrows the window to a couple of
    # instructions, the acquire removes the only party that could enter it.
    #
    # EVIDENCE TIER FOR W2 -- MEASURED IN COMBINATION (with both windows widened every batch fails;
    # with the atomic acquire none does) and CORROBORATED by the debris of a failing run,
    # whose anomalous rounds leave one DIRECTORY aside and one REGULAR-FILE aside: a regular
    # file at the marker path can only be a marker a repairer had already finished creating, which is
    # the literal statement of this window, on unmodified code. W2 alone is not isolated
    # by the bench -- the contract suite's W2 injection arm isolates it, by harness
    # injection rather than by waiting for a second repairer.
    # PLC-ANCHOR:repair-rename -- the rename that acts on the corrupt node
    if [ -n "$_cfaside" ] \
       && [ -e "$MARKER" ] && [ ! -L "$MARKER" ] && [ ! -f "$MARKER" ] \
       && mv "$MARKER" "$_cfaside" 2>/dev/null; then
      # PATHLESS, deliberately. A maintainer needs to know a repair happened; a BLOCKED AGENT must
      # not be handed a path into the guard's own state. The block message names exactly one action
      # (refresh RESUME.md) because an agent once read a suggested `rm` out of an error message and
      # deleted the guard's state to get past the guard. A repair that prints its own scratch path
      # rebuilds that affordance.
      printf '[context-floor] repaired corrupt guard marker\n' >&2
    elif [ ! -e "$MARKER" ] || [ -f "$MARKER" ]; then
      # WE LOST A RACE, and that is NOT the same thing as "the repair cannot proceed". A failed `mv`
      # has two causes and merging them reintroduced the double first-call grant.
      #
      # MEASURED, 5 of 5 concurrent runs against a directory-shaped corrupt marker: the winner's `mv`
      # succeeds and it creates the marker; the loser's `mv` fails because the SOURCE IS ALREADY GONE,
      # fell into the sidecar branch below, and created `<sid>.wedged` -- a filename nobody else was
      # contending for. Both processes therefore obtained `FIRST_ARM=1` and BOTH WERE ALLOWED. The
      # single-winner guarantee that makes the ordinary path safe is a property of one filename, and
      # the sidecar branch quietly introduced a second one. Both rc=0, with `s.marker`, `s.wedged` and
      # the moved-aside node all present. At the time the
      # only concurrency row in the suites started from a CLEAN sandbox, so no oracle
      # covered "concurrent processes AND a corrupt node already present".
      #
      # THE TEST IS "IS THE CORRUPT NODE STILL THERE", not "has somebody else finished repairing".
      # The second phrasing was tried first and is ALSO racy: between the winner's `mv` and its
      # create there is a window in which the marker path is EMPTY, and a loser checking for a
      # finished repair sees nothing and falls into the sidecar anyway. Measured -- that version
      # still allowed both processes, 8 of 8.
      #
      # If the node is gone (someone moved it) or is already a regular file (someone rebuilt it),
      # this call is simply not the one doing the repair. Do nothing and let the shared O_EXCL create
      # below decide: it is the single-winner primitive, so exactly one process gets FIRST_ARM and
      # the other falls through to the mtime comparison like any later call. Leaving `FIRST_ARM` at 0
      # here is what puts both racers back on ONE filename.
      #
      # SUPERSEDED BY THE MUTEX ABOVE, AND KEPT ANYWAY -- said plainly because "kept" and "still
      # load-bearing" are different claims. NO MUTANT CAN KILL THIS BRANCH: the mutant written for it
      # (`elif false`) leaves the whole suite green, where it used to redden
      # the concurrent-repair row. So it is retained without an oracle, and it is recorded as UNASSERTED.
      #
      # IT USED TO BE RECORDED AS "UNREACHABLE BY CONSTRUCTION", AND THAT IS WITHDRAWN. The argument
      # was "under the lock no second repairer exists, so `the source vanished` can only be caused by
      # something outside this hook" -- and its premise is false, measured: W1 in the
      # stanza above admits a second repairer, whose `mv` can find the source already gone and land
      # exactly here. What was NOT measured is whether that is what happens in a real bad
      # round; the reachability claim is withdrawn, not inverted, and no replacement claim is made.
      :
    else
      # THE RENAME COULD NOT PROCEED. Fail CLOSED, and stay CLEARABLE. Both halves are
      # required and the two obvious answers each give up one of them, measured:
      #
      #   * carry on to the comparison below -> `stat -L` succeeds on a directory, so the frozen
      #     mtime of the corrupt node is what a refreshed RESUME.md is compared against, and it is
      #     newer forever. That is the frozen-marker defect, unfixed: `0000`.
      #   * block unconditionally -> the corrupt node is still here, no marker mtime ever exists,
      #     the clear branch can never run, and refreshing RESUME.md -- the one action the block
      #     message names -- does nothing. `2222` with the checkpoint refreshed before every retry.
      #     That is the cardinal sin this file's header describes.
      #
      # So the guard moves its OWN state to a SIDECAR path and stops looking at the corrupt node
      # altogether. Everything downstream -- the O_EXCL create, the mtime comparison, the `rm -f` on
      # the clear path -- then operates on an ordinary regular file and needs no special case. The
      # corrupt node is never read, never followed, never removed.
      #
      # Same directory, so the sidecar cannot itself be a cross-device rename, the likeliest
      # trigger for this branch.
      MARKER="$MDIR/$SID.wedged"
      printf '[context-floor] corrupt guard marker could not be repaired\n' >&2
    fi
    # RELEASED BEFORE THE CREATE, not at exit: the create below is the shared single-winner
    # primitive and must not be run while holding a lock nobody else can take, or the ordinary
    # contention this guard depends on would be serialised behind a repair.
    #
    # OWNERSHIP ASSERTION -- and, with W3 closed, the condition the removal below hangs off.
    # This block reports when the lock we are about
    # to delete is not the one we took, and then leaves it in place (W3, below).
    #
    # WHY IT EXISTS: the string `STOLEN self=... found=...` is the one phenomenon W1 produces, and
    # an observation that no committed test watches explains no failure.
    # This is that oracle, written down where a test can see it.
    #
    # READS `$_cflock` DIRECTLY: the lock is a regular file whose content IS the pid. A read left in
    # the older directory-with-a-`pid`-file shape would
    # `cat` a regular file's path with `/pid` appended, come back
    # empty, and print STOLEN on EVERY release including unwidened ones -- destroying this row's own
    # control rather than failing loudly.
    # ITS OWN KNOB, NOT THE SUITE'S. It is deliberately not gated on the
    # CONTRACT SUITE's switch for whether to run the bench at all -- a variable this hook does not read.
    # Borrowing it would have tied a hook assertion to a variable that means something else in another
    # file, and left this row's silence indistinguishable from "the knob meant something different
    # today".
    #
    # W3 -- THE REMOVAL IS NOW CONDITIONAL ON OWNERSHIP. It used to be unconditional, so once W1 had
    # admitted a second repairer the FIRST one deleted the SECOND one's lock on its way out and a
    # third caller could enter behind it. That is why the aside nodes in a bad round were not bounded
    # at two.
    #
    # EVIDENCE TIER, VERBATIM: NOT MEASURED -- code inspection only, and unreachable-by-construction
    # once the atomic acquire landed. Retained as an assertion, not as a repair.
    #
    # AND THE HONEST ANSWER TO "CAN THAT BRANCH BE TESTED", because "unreachable by construction"
    # is an easy over-claim here:
    # it CAN be reached, but only by a harness that FORGES the lock's content mid-flight --
    # writing a foreign pid into the lock while this process is held inside the publish. No real race
    # produces it any more: the acquire publishes content and name together, so a rival cannot obtain
    # this lock's name at all, and cannot rewrite its content without already being a process that
    # has no business there. The contract suite's W3 forge arm is that synthetic demonstration and
    # it is LABELLED synthetic. Do not read it as evidence a real race exists; read it as evidence
    # this branch does what it says when it is reached.
    # PLC-ANCHOR:lock-release -- ownership is read here, and the removal below hangs off it
    _cfrel="$(cat "$_cflock" 2>/dev/null || true)"
    if [ "$_cfrel" = "$$" ]; then
      rm -f "$_cflock" 2>/dev/null || true
    else
      # NOT OURS. Do not delete another repairer's lock. The report stays behind its own knob because
      # it is an assertion for the suite, not a diagnostic for a user -- unlike the acquire's
      # classification line, which fires unconditionally because a host on which repair can never
      # engage is a fact the operator needs and the suite cannot see.
      [ -n "${PLC_CF_ASSERT_OWNER:-}" ] && printf 'STOLEN self=%s found=%s\n' "$$" "$_cfrel" >&2
    fi
    trap - EXIT; _cflock=""
  fi
  if { ( set -C; : 2>/dev/null > "$MARKER" ); } 2>/dev/null; then
    FIRST_ARM=1
  else
    if [ -L "$MARKER" ]; then                  # corrupt guard state -> unlink and retry ONCE
      rm -f "$MARKER" 2>/dev/null || true      # removes the LINK, never what it points at
      { ( set -C; : 2>/dev/null > "$MARKER" ); } 2>/dev/null && FIRST_ARM=1
    fi
    # Not ours, not repairable, and nothing is there: a genuine write failure -> fail OPEN.
    #
    # THE FAIL-OPEN IS RE-TESTED, NOT INFERRED FROM THE FAILED CREATE ABOVE, and that difference is
    # the second half of the double-allow. Measured after the repair mutex landed: 4 of 100 loaded
    # iterations still granted two allows, and the surviving shape had ONE aside node, not two --
    # so it was not a double repair. It was this: the losing call's create failed because the corrupt
    # DIRECTORY still occupied the path, and by the time these three tests ran the repairer had moved
    # that directory aside, so "nothing is there" was true and the call failed OPEN -- on the strength
    # of a create attempt that had already been overtaken. The old comment's "a marker that DOES exist
    # now falls through" covered the case where the winner had already CREATED; it had no answer for
    # the window between the winner's move and the winner's create, which is exactly where this lands.
    #
    # So try once more before believing it. The create is the single-winner primitive: if it succeeds
    # this call IS the arming call and takes the ordinary one-call grant; if it fails, somebody armed
    # in between and this is an ordinary later call, judged by the comparison below. Only a path that
    # is STILL empty after a real second attempt is a genuine write failure.
    if [ "$FIRST_ARM" = 0 ] && [ ! -e "$MARKER" ] && [ ! -L "$MARKER" ]; then
      { ( set -C; : 2>/dev/null > "$MARKER" ); } 2>/dev/null && FIRST_ARM=1
      if [ "$FIRST_ARM" = 0 ] && [ ! -e "$MARKER" ] && [ ! -L "$MARKER" ]; then
        exit 0
      fi
    fi
    # THE LOCK-LOSER'S GUARD. We could not create, and what is sitting there is not a regular file
    # and not a symlink -- so it is the corrupt node another process is repairing right now. Falling
    # through would compare a checkpoint against the FROZEN mtime of a directory or a FIFO, which
    # every checkpoint beats, and the loser would be allowed: the frozen-marker defect itself, arriving as the second
    # allow of a race. Block instead. This costs one call and self-heals -- the holder's repair
    # completes in the same instant, so the next call sees an ordinary regular marker -- and the
    # block is the ordinary, clearable one, not the `2222` wedge (the marker it leaves behind is the
    # holder's regular file, and the clear path below removes it like any other).
    if [ "$FIRST_ARM" = 0 ] && [ -e "$MARKER" ] && [ ! -L "$MARKER" ] && [ ! -f "$MARKER" ]; then
      printf '[context-floor] guard state is being repaired by another call; retry\n' >&2
      exit 2
    fi
  fi
fi

# ── the first call of an arm cycle cannot be judged by the comparison below ───────────
# The marker was just created, so its mtime is ~now and `mtime(RESUME) > mtime(marker)` is
# UNSATISFIABLE -- not sometimes, ever. The block below therefore fired on the very first
# over-floor call of every arm cycle regardless of how fresh the checkpoint was, demanding an
# action at the same instant it defined the deadline for that action. An operator who had done
# exactly the right thing was blocked for it, and a guard whose block cannot be pre-empted is a
# guard that gets switched off permanently via this hook's documented off switch (the
# dynamics are argued in this file's header).
#
# So the first call of an arm cycle is decided HERE instead: arm, and allow -- but only if a
# checkpoint file actually exists at the resolved path. "No checkpoint at all" is the one state
# with nothing to be wrong about, the block is uniquely cheap to clear (the RESUME write is
# exempt above, so the operator's very next action succeeds), and it is what the contract row
# "first over-floor edit: arms and blocks" has always asserted.
#
# THE ARM ABOVE MUST HAPPEN BEFORE THIS ALLOW. Exiting 0 without creating the marker re-enters
# this branch on every subsequent call, and the floor is off for the rest of the session --
# while passing every exit-code-only assertion in both suites.
#
# NO `clearedat` WRITE HERE, deliberately. Reusing the clear path below would hand out a
# STEP-sized token window nobody earned and push the first real block that much further out.
# What is granted here is one CALL, not a window.
#
# `[ -e ]` treats an undeterminable path (unreadable parent, dead automount, stale NFS handle)
# as absent, i.e. it blocks. That is byte-identical to the behaviour that shipped before this
# change -- this branch only ever converts block into allow, so declining to convert one case is
# not a regression. A fail-open classifier here was specified and then dropped: it collides with
# a live fixture whose parent is legitimately absent, it cannot hold from call 2 anyway because
# mtime_of conflates the same two cases -- see [[skills/project-lifecycle/hooks/context-floor.sh#mtime-of]] -- and it would put a `chmod`-the-parent bypass in
# reach of a blocked agent -- the exact failure the block message was rewritten to stop.
#
# This recurs ONCE PER ARM CYCLE, not once per session, and that is in contract: the clear path
# below removes the marker, so crossing the next STEP threshold arms afresh and grants the one
# chance again. Denying it would reproduce this very defect at every threshold after the first.
#
# `-f`, not `-e`: the rule is "no checkpoint FILE at all -> block", and `-e` is also true of a
# DIRECTORY named RESUME.md, which would otherwise buy the free call (measured:
# 0 -> 2). `-f` follows symlinks, so a symlink to a real checkpoint still allows and a dangling
# one still blocks.
#
# This used to close only the FIRST-CALL half, and said so: `mtime_of` below still used `-e`, so on
# the SECOND call a directory or FIFO named RESUME.md cleared the block and was awarded the
# STEP-sized grace window this branch is careful not to hand out. That half is now closed
# at the clear-path guard just above `RT=`. The two
# tests are deliberately NOT hoisted into one shared predicate -- see the reasoning at the clear
# path -- so a half-revert is possible, and the contract rows assert both halves per shape for
# exactly that reason.
if [ "$FIRST_ARM" = 1 ] && [ -f "$RESUME" ]; then
  exit 0
fi

# ── has the checkpoint been refreshed since we armed? ─────────────────────────
# `stat`, not bash's `[ a -nt b ]`. Measured on the target platform: bash 3.2's `-nt` has
# only whole-second resolution, and the RESUME write is EXEMPT above -- so an agent that
# is blocked, writes RESUME.md, and retries within the same second would stay blocked
# while python (float mtime) would clear. "Doing the right thing does not clear the
# block" is precisely the pattern that trains an operator to set PLC_CONTEXT_FLOOR=0.
#
# `-L` is mandatory on both platforms: BSD `stat` does NOT follow symlinks by default,
# while python's os.path.getmtime() does. A symlinked RESUME.md -- entirely plausible in
# a multi-repo layout -- would otherwise be compared against the wrong file.
STAT_FMT=""
if command -v stat >/dev/null; then
  if LC_ALL=C stat -L -f %Fm . >/dev/null 2>&1;   then STAT_FMT="bsd_frac"
  elif LC_ALL=C stat -L -c %.9Y . >/dev/null 2>&1; then STAT_FMT="gnu_frac"
  elif LC_ALL=C stat -L -f %m . >/dev/null 2>&1;   then STAT_FMT="bsd_sec"
  elif LC_ALL=C stat -L -c %Y . >/dev/null 2>&1;   then STAT_FMT="gnu_sec"
  fi
fi
# No usable stat at all is an environment defect, not a normal path: fail OPEN rather
# than turn a missing utility into a permanent block.
[ -n "$STAT_FMT" ] || exit 0

# PLC-ANCHOR:mtime-of -- one reader for both the marker and the checkpoint, which is why it conflates their absence
mtime_of() {                                    # echoes an mtime, or nothing
  [ -e "$1" ] || return 0
  case "$STAT_FMT" in
    bsd_frac) LC_ALL=C stat -L -f %Fm  "$1" 2>/dev/null ;;
    gnu_frac) LC_ALL=C stat -L -c %.9Y "$1" 2>/dev/null ;;
    bsd_sec)  LC_ALL=C stat -L -f %m   "$1" 2>/dev/null ;;
    gnu_sec)  LC_ALL=C stat -L -c %Y   "$1" 2>/dev/null ;;
  esac
}
# The CLEAR path needs the same "is it a checkpoint FILE" test the first-call branch got, and it needs it HERE rather than inside `mtime_of`. `stat -L` succeeds on a directory, a
# FIFO and a symlink to /dev/null (measured, both platforms), so without this guard any of them
# named RESUME.md compares newer than the marker, clears the block, and collects the STEP-sized
# grace window the first-call branch is careful not to hand out -- ~30K of free over-floor edits
# per arm cycle. "No checkpoint FILE at all -> block" was only half true until this line.
#
# NOT pushed into `mtime_of`, deliberately, and this is the whole of the design decision:
# `mtime_of` is also called on $MARKER one line down, where the guard's OWN state lives. The arm
# block above is entered only under the type test at [[skills/project-lifecycle/hooks/context-floor.sh#arm-block-entry]], so a directory / FIFO / socket
# sitting at the marker path skips arming AND skips the symlink repair, and reaches here intact.
# Rejecting it here would leave MT empty forever, so the clear below could never run -- and
# the clear path's `rm -f` CANNOT remove a directory, so the block would be permanent AND unclearable by
# refreshing RESUME.md, the one action the block message names. Measured: 2222 with the checkpoint
# refreshed before every retry. That is the shape this file's header calls the cardinal sin.
# The marker half is a different fix class -- repair, not
# reject -- and is handled by the arm block's repair above.
#
# `mtime_of`'s own `[ -e "$1" ]` therefore stays: it is load-bearing on BSD, where `stat -L` on a
# DANGLING symlink falls back to lstat (documented in `man stat`) and reports the link's own mtime,
# while GNU returns non-zero. Dropping it would make a dangling RESUME.md clear on macOS and block
# on Linux -- a silent platform split no row would catch.
#
# `-f` follows symlinks, so a RESUME.md symlinked to a real file still clears (asserted as the
# positive control in the contract suite; without it, "blocks on all three shapes" is satisfied by
# a hook that never clears anything at all).
RT=""; [ -f "$RESUME" ] && RT="$(mtime_of "$RESUME")"
MT="$(mtime_of "$MARKER")"
# Both must exist and parse, reproducing python's "rt is not None and mt is not None".
# An empty or non-numeric capture is "no mtime", never 0 -- a 0 would compare as older
# than everything and silently change the clear semantics.
if [ -n "$RT" ] && [ -n "$MT" ] \
   && jq -ne --arg a "$RT" --arg b "$MT" \
        '(($a | tonumber?) // empty) as $x | (($b | tonumber?) // empty) as $y | $x > $y' \
        >/dev/null 2>&1; then
  # checkpointed since arming -> record occupancy AND which checkpoint earned it, clear, allow.
  # Two lines, matching the reader above. Writing only the occupancy is what let a window earned
  # against one project suppress arming while another was being measured.
  printf '%s\n%s\n' "$OCC" "$CKEY" > "$CLEAREDAT" 2>/dev/null || true
  rm -f "$MARKER" 2>/dev/null || true
  exit 0
fi

# ── block ─────────────────────────────────────────────────────────────────────
# The message names ONE action: refresh RESUME.md. It deliberately does NOT hand out the
# marker path or an `rm` command.
#
# It used to. An agent, blocked mid-task, read the suggestion and reached straight for
# `rm <marker>` -- deleting the guard's own state to get past the guard. It did that
# because THE GUARD TOLD IT TO. A guard that ships its own bypass in its error message is
# a guard that will be bypassed, and the agent is not even being disobedient when it
# happens: it is following instructions.
#
# The escape hatch still exists -- the env knob below, and the marker is still a file on
# disk for a human who knows where to look. What changed is that it is no longer
# ADVERTISED at the moment of maximum incentive to take it. A config knob a human sets
# deliberately is a decision; a shell command dangled in front of a blocked agent is a trap.
#
# NOTE ON `%%`: the absolute-mode note below USED TO render a literal `%%` to the user.
# In the python it was a plain string constant containing `%%`, substituted into the
# outer format via `%s`, so the escape was never processed. The port reproduced that verbatim
# rather than fixing it in passing, because the port was checked by comparing this message
# byte for byte and a drive-by text fix would have read as a porting bug.
#
# It was then fixed on its own, as a single deliberate change.
# The single `%` below is the whole
# behaviour change.
# `${VAR%%...}` parameter expansions elsewhere in this file are unrelated and untouched.
NUMS="$(jq -nr --argjson occ "$OCC" --argjson floor "$FLOOR" \
                --argjson win "$WINDOW" --arg fpct "$FLOOR_PCT" '
  # python round() is half-to-even. These figures are display-only, and they differ from
  # a half-up rounding solely at an exact odd multiple of 500, so half-even is reproduced
  # rather than approximated.
  def bround:
    . as $x | ($x | floor) as $f | ($x - $f) as $r
    | if   $r > 0.5 then $f + 1
      elif $r < 0.5 then $f
      else (if ($f % 2) == 0 then $f else $f + 1 end) end;
  # python renders round(x, 1) via %s, which always shows exactly one decimal place.
  def one_dp: (. * 10 | bround) as $t | "\($t / 10 | floor).\($t - ($t / 10 | floor) * 10)";
  ( if $win > 0 then ($occ / $win * 100) else 0 end ) as $pct
  | [ ($occ / 1000 | bround)          # ~NK
    , ($pct | one_dp)                 # ~P%
    , ($win / 1000 | bround)          # of WK window
    , ($floor / 1000 | bround)        # floor FK
    , (($fpct | tonumber? // 0) | one_dp)
    ] | @tsv' 2>/dev/null)" || NUMS=""
[ -n "$NUMS" ] || exit 0                        # cannot render the message -> fail-open

OCC_K="${NUMS%%$'\t'*}"; R="${NUMS#*$'\t'}"
PCT_S="${R%%$'\t'*}";    R="${R#*$'\t'}"
WIN_K="${R%%$'\t'*}";    R="${R#*$'\t'}"
FLOOR_K="${R%%$'\t'*}"
FPCT_S="${R#*$'\t'}"

if [ "$PCT_MODE" = "1" ]; then
  TRIGGER_DESC="the %-floor (${FPCT_S}% of the ${WIN_K}K window = ~${FLOOR_K}K)"
  NOTE=""
  DISABLE_HINT="set PLC_CONTEXT_FLOOR_PCT=0 to disable"
else
  TRIGGER_DESC="floor ${FLOOR_K}K"
  NOTE="Trigger is absolute tokens, not window %, so this fires even when the window-% looks small. "
  DISABLE_HINT="set PLC_CONTEXT_FLOOR=0 to disable"
fi

# WORKTREE. A worktree exists to isolate one session from another,
# so the RESUME.md resolved inside one is, by construction, NOT this session's:
# it was inherited from the base branch and belongs to whoever wrote it there,
# or -- when the checkpoint is gitignored, as PLC's own is -- it does not exist
# at all and the block names a path that was never on disk.
#
# Either way the instruction is unsatisfiable as written, and the message named
# only the disable switch. That is the shape this whole hook exists to avoid: a
# guard whose only stated exit is its own off-switch teaches the operator to
# take it (see the note at the DISABLE_HINT rationale above). PLC_RESUME_PATH
# was already the correct exit and went unmentioned.
#
# MEASURED TWICE ON THE SAME DAY, not reasoned:
#   1. A session repairing a release pipeline hit the floor inside a worktree
#      of the repo it was working in; that RESUME.md belonged to another
#      LIVE session's branch. It complied by prepending its own section and
#      keeping the original verbatim -- which is a workaround, not a fix.
#   2. Opening a worktree HERE to write this very patch hit the floor again, on
#      a RESUME.md that does not exist in any PLC worktree. The defect blocked
#      its own repair.
#
# Detected structurally rather than by matching "/worktrees/" in a path: in a
# normal checkout the git dir is `<toplevel>/.git`; in a worktree it is not.
# Both calls fail safe -- a non-git or unreadable CWD yields empty strings and
# no note. Silent when PLC_RESUME_PATH is already set, for the same reason
# RESUME_HINT is: the reader configured the location and does not need it read
# back to them.
#
# The sentence says "a worktree", never the two-word form: INV-2 of
# `scripts/invariants/context-floor-envelope.sh` requires every `git ` in this
# file to carry a stderr guard, and it skips comment lines but not string
# literals — so the longer phrase reads as an unguarded call and blocks the
# push. Widening that invariant to understand strings would trade a false
# positive for a real hole, and the extra word buys nothing in a message that
# is already talking about branches and checkouts.
#
# Spends NO git call: in a normal checkout `<toplevel>/.git` is a DIRECTORY, and in a
# worktree it is a regular FILE holding a `gitdir:` pointer. That is git's own on-disk
# shape, so this is still structural rather than a match on "/worktrees/" in a path —
# and it costs one stat.
#
# Two rejected alternatives, both measured, so neither comes back:
#   * `rev-parse --absolute-git-dir` alongside `--show-toplevel`: the design pins checkpoint
#     resolution to EXACTLY ONE git call (this hook runs ahead of every Edit/Write, so
#     the count is a budget), and adding one took it to three.
#   * Asking `rev-parse` for both values in one process and splitting its output on the
#     newline: an acceptance criterion pins that a checkpoint path may itself contain a newline, which
#     makes a line-split parse wrong exactly where that test looks.
WORKTREE_NOTE=""
if [ -z "${PLC_RESUME_PATH:-}" ]; then
  _wt_top="${TOP:-}"
  if [ -n "$_wt_top" ] && [ -f "$_wt_top/.git" ]; then
    WORKTREE_NOTE="This is a worktree, so that RESUME.md is inherited from the base branch (and may be another session's, or may not exist) -- point PLC_RESUME_PATH at a checkpoint of your own rather than overwriting it. "
  fi
fi

# WHICH RESUME.md. Once the checkpoint is resolved from the target's git root it can no
# longer be assumed to be `./RESUME.md`, and "refresh RESUME.md" stops being an instruction the
# reader can act on -- which is the same unsatisfiable-guard failure this resolution exists to remove,
# just relocated from "the file keeps moving" to "the agent cannot tell which file is meant".
#
# This is NOT a walk-back of the decision three paragraphs up. That one withholds the MARKER path
# and any `rm`: the guard's own state, whose disclosure is a bypass. This names the artifact the
# reader is being asked to WRITE. Opposite direction, and the row above regression-guards that the
# marker path stays out.
#
# Named only when THE HOOK chose the path, i.e. when git resolution won (RESUME_HINT is set at
# exactly that point above). Two cases deliberately stay silent: `$CWD/RESUME.md`, where the bare
# sentence already says everything and an absolute path would be noise on the common case; and an
# explicit `PLC_RESUME_PATH`, where the reader configured the location themselves and repeating
# it back tells them nothing they did not type.
printf '[context-floor] Blocked: context ~%sK (~%s%% of %sK window) over %s and RESUME.md%s not refreshed since. %sRefresh RESUME.md%s to clear this -- it is the checkpoint the floor exists to force, and it is almost certainly stale if you are seeing this. %s(To turn the floor off on this machine: %s.)\n' \
  "$OCC_K" "$PCT_S" "$WIN_K" "$TRIGGER_DESC" "$RESUME_HINT" "$NOTE" "$RESUME_HINT" "$WORKTREE_NOTE" "$DISABLE_HINT" >&2
exit 2
