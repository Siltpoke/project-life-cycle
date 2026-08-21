#!/usr/bin/env bash
# test-context-floor-contract.sh — contract suite for context-floor.sh.
#
# WHY THIS EXISTS
#
#   This suite asks one question: "is this RIGHT?" -- assertions against the contract the
#   hook is supposed to honour, never against the previous implementation. That is what lets it see
#   a preserved defect.
#
#   IT IS ALSO THE ONLY ORACLE FOR THE FIRST-CALL PATH.
#   Every future property of that code (atomicity, `-f` vs `-e`, a successor's session anchor)
#   has exactly one place it can be asserted: here, with nothing behind it.
#
# THE XFAIL ROWS -- **ONE TODAY**, and this header moves with the count.
#   `CF-W2-INJECT` -- the residual rename window registered in the NONPORT block below. The
#   repair re-tests the marker's type before renaming it aside, but `mv` is not atomic with that
#   re-test, so a legitimate marker swapped in between is still moved aside -- red today BY DESIGN.
#   It runs on every invocation. When a later change closes the residual this row XPASSes, and an XPASS fails this suite -- which is
#   exactly what forces whoever fixes it to come back and flip the row live.
#
#   THE BENCH IS NOT AN XFAIL. `RL-BENCH`, the widened-window repair-lock bench, is a LIVE row.
#   The bench costs ~27s and runs in CI, or locally when your hooks differ from the merge-base;
#   otherwise it prints a SKIP naming every criterion it covers. Under CI a bench that fails to arm
#   is itself a hard failure
#   (`RL-bench-arming`) -- otherwise a broken detection would silently disarm all of it.
#
#   THE MECHANISM IS STILL LIVE AND STILL BINDING, for the next row that needs it. An XFAIL is
#   marked and PRINTED -- never commented out, never silently skipped, because an expected-failure
#   nobody sees is an expected-failure that quietly becomes a regression. An XFAIL that unexpectedly
#   PASSES fails this suite: either behaviour changed where it should not have, or the defect was
#   fixed elsewhere and the row is stale. Both need a human, so neither may be silent.
#
# WHERE A KNOWN-DEFECT ROW IS REGISTERED, and why there are now two places rather than one.
#   `scripts/invariants/ledger-contract-sync.sh` requires every `xfail`/`xpass` id to be
#   NAMED somewhere, so that a row cannot exist with nothing declaring why. Its only naming site
#   used to be the divergence ledger inside `context-floor.sh`.
#
#   That ledger is a PORT ledger and says so in its own first line: "Behaviour was deliberately
#   UNCHANGED BY THE PORT. Four known defects were preserved on purpose." Every id in it is a
#   defect the bash port inherited from the pinned python and chose not to fix.
#
#   The defect registered below is not one of those. It is a live defect in code written after the
#   port, and this suite treats `context-floor.sh` as frozen -- that byte-identity is the entire
#   reason the widening is a PATH shim instead of a patched copy, and any edit to that file,
#   comments included, would break it. So the two requirements collided: the invariant
#   wanted the id written into a file this suite does not touch.
#
#   Resolved by splitting the naming site rather than by dropping either: the ledger keeps the
#   port divergences, and NON-PORT known defects are declared HERE, beside the rows that assert
#   them. The invariant checks both directions on this block too -- a declared id with no row, or
#   a row with no declaration, fails -- so this is a second register, not an escape hatch. An id
#   may live in exactly one of the two, never both.
#
#NONPORT-BEGIN
#   B9002 Two windows in the repair path, and they are in DIFFERENT states. Say so
#         separately: one registration covering "some of this is fixed" is how a half-closed defect
#         gets quoted as closed.
#         W1 -- CLOSED. `mkdir "$_cfl"` took the lock and the owner pid was stamped a line later, so
#         a rival arriving in between read an empty owner, classified a LIVE lock as ownerless,
#         `rm -rf`d it and took it. The acquire now publishes the CONTENT first and the NAME with a
#         bare `ln` whose EEXIST failure IS the exclusion, so that state cannot exist. `RL-BENCH` is
#         LIVE, not xfail: with both windows still deliberately held open it measured 6 of 6 batches
#         double-allowing before the change and 0 of 6 after.
#         W2 -- HALF CLOSED, AND THE OPEN HALF IS WHY THIS ID STAYS REGISTERED. The scan half is
#         closed: the node type is re-tested BETWEEN the candidate scan and the rename, so a marker
#         that arrives while the scan is running is no longer renamed aside (`CF-RETEST`, presence
#         and order). The RESIDUAL is not: `mv` is still not atomic with its own test, so a marker
#         arriving between that re-test and the rename is still moved aside. `CF-W2-INJECT` is the
#         xfail this registration now covers and it measures the RESIDUAL specifically -- its
#         rendezvous is the `mv` wrapper's log line, which fires after the re-test has passed.
#         SAID PLAINLY BECAUSE IT IS EASY TO MISREAD AS A FAILED FIX: nothing here closes
#         the residual, and nothing was expected to. What removes the party that could exploit it is
#         the atomic acquire, which makes a second repairer impossible; the residual remains
#         reachable in principle by a process outside this hook writing to the marker path.
#NONPORT-END
#
# Usage: /bin/bash skills/project-lifecycle/hooks/test-context-floor-contract.sh
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMPL="${PLC_CF_NEW:-$HERE/context-floor.sh}"
# Absolutise: `run_hook` can now run the hook from a different working directory (see its comment),
# and a relative PLC_CF_NEW -- exactly what a mutation run hands in -- would stop resolving there.
case "$IMPL" in
  /*) ;;
  *)  IMPL="$(cd "$(dirname "$IMPL")" 2>/dev/null && pwd)/$(basename "$IMPL")" ;;
esac

# the shared floor library. Selected by PLC_FLOOR_LIB_NEW (a mutant library, the same way
# PLC_CF_NEW selects a mutant hook) and then PINNED onto every hook call below -- the hook's own
# PLC_FLOOR_LIB is always written by this suite and never inherited from the caller. That is
# deliberate: a stale export reaching a mutation run produces a HYBRID (mutated hook, wrong
# library) that reports confidently instead of aborting, which is the misattribution class
# `impl_path`'s FATAL guard already exists for in test-hooks.sh.
#
# Readability is checked FATALLY here rather than left to the hook's fail-open. A hook that
# cannot load the library exits 0, and rc=0 is a legitimate "under the floor" answer -- so an
# unreadable library would turn this whole suite green for the wrong reason.
FLOOR_LIB="${PLC_FLOOR_LIB_NEW:-$HERE/lib/floor-env.sh}"
case "$FLOOR_LIB" in
  /*) ;;
  *)  FLOOR_LIB="$(cd "$(dirname "$FLOOR_LIB")" 2>/dev/null && pwd)/$(basename "$FLOOR_LIB")" ;;
esac
[ -r "$FLOOR_LIB" ] || {
  echo "FATAL: shared floor library not readable: $FLOOR_LIB" >&2
  echo "       (a missing library makes the hook exit 0, which this suite cannot tell from 'under the floor')" >&2
  exit 2
}
printf 'floor library in use: %s\n' "$FLOOR_LIB"

# PLC-ANCHOR:suite-counters -- the tallies every helper below mutates
PASS=0; FAIL=0; XFAIL=0; XPASS=0
# THE GATE IS A FUNCTION, called both by the last line of this file and by the row that claims to
# evaluate it. It used to be a literal retyped in three places, and that was MEASURED to drift:
# deleting `&& [ "$XPASS" -eq 0 ]` from the real gate left `RL-AC8` printing "an XPASS CLOSES
# this suite's gate" while the suite exited 0. A guard and its proof reading two copies of one
# expression is the same defect this file names further down about `hits == 0`.
plc_gate() { [ "$FAIL" -eq 0 ] && [ "$XPASS" -eq 0 ]; }
# PLC-ANCHOR:suite-verdict-helpers -- the only two functions allowed to record a verdict
ok()    { PASS=$((PASS+1));  printf '  ok     %s\n' "$1"; }
no()    { FAIL=$((FAIL+1));  printf '  FAIL   %s\n' "$1"; }
xfail() { XFAIL=$((XFAIL+1)); printf '  XFAIL  %s\n            (known defect %s -- expected red until it is fixed)\n' "$1" "$2"; }
xpass() { XPASS=$((XPASS+1)); printf '  XPASS  %s\n            (known defect %s did NOT reproduce -- investigate before proceeding)\n' "$1" "$2"; }

command -v jq >/dev/null || { echo "FATAL: jq not found" >&2; exit 1; }

# PLC-ANCHOR:suite-workdir -- created and trapped before any row runs
WORK="$(mktemp -d)" || { echo "FATAL: mktemp -d failed" >&2; exit 1; }
trap 'rm -rf "$WORK"' EXIT

usage_line() {
  printf '{"type":"assistant","message":{"usage":{"input_tokens":%s,"cache_read_input_tokens":0,"cache_creation_input_tokens":0}}}\n' "$1"
}

# --- owned-tree recursive content digest --------------------------
# `mode`/`type` are recorded as TWO INDEPENDENT fields, because
# merged into one field, a symlink-vs-regular
# swap stops being visible.
CT_TIMEOUT=""
command -v timeout >/dev/null 2>&1 && CT_TIMEOUT=1
MODETYPE_STAT=""
if command -v stat >/dev/null 2>&1; then
  if   LC_ALL=C stat -f '%Lp %HT' . >/dev/null 2>&1; then MODETYPE_STAT=bsd
  elif LC_ALL=C stat -c '%a %F'   . >/dev/null 2>&1; then MODETYPE_STAT=gnu
  fi
fi
ct_modetype() {
  local out
  case "$MODETYPE_STAT" in
    bsd) out="$(LC_ALL=C stat -f '%Lp %HT' "$1" 2>&1)" ;;
    gnu) out="$(LC_ALL=C stat -c '%a %F'   "$1" 2>&1)" ;;
    *)   printf 'mode=? type=?'; return 0 ;;
  esac
  case "$out" in
    [0-7]*' '[A-Za-z]*) : ;;
    *) printf 'mode=<unread> type=<unread>'; return 0 ;;
  esac
  printf 'mode=%s type=%s' "${out%% *}" \
    "$(printf '%s' "${out#* }" | cut -d' ' -f1 | LC_ALL=C tr 'A-Z' 'a-z')"
}
# `cksum`, not `shasum`/`md5`: POSIX-mandated and present on both platforms, and this needs
# change-detection, not collision resistance. A content CHANGE with an unchanged name is the entire
# class this digest exists to catch, and a CRC sees it.
ct_walk() {                       # $1 = absolute dir, $2 = relative prefix ("" at the root)
  local root="$1" pfx="$2" f rel
  for f in "$root/$pfx"* "$root/$pfx".[!.]* "$root/$pfx"..?*; do
    [ -e "$f" ] || [ -L "$f" ] || continue
    rel="${f#"$root"/}"
    if   [ -L "$f" ]; then printf '%s %s -> %s\n' "$rel" "$(ct_modetype "$f")" "$(readlink "$f" 2>/dev/null)"
    elif [ -f "$f" ]; then printf '%s %s %s\n'    "$rel" "$(ct_modetype "$f")" "$(cksum < "$f" 2>/dev/null || echo '<unreadable>')"
    else                   printf '%s %s\n'       "$rel" "$(ct_modetype "$f")"
    fi
    # A symlinked directory is NEVER descended (`-d` is checked only after `-L` has been ruled out
    # above, and the recursion below repeats the test). That is what makes a symlink LOOP inside an
    # owned tree terminate BY CONSTRUCTION rather than by a depth counter that would be a semantic
    # cutoff.
    # Row `CF-AC11b` asserts this rather than assuming it.
    if [ -d "$f" ] && [ ! -L "$f" ]; then ct_walk "$root" "$rel/"; fi
  done
}
# Globs, never `find | read`: a filename containing a NEWLINE survives a glob and does not survive a
# line-oriented stream. The hostile-name fixtures in this suite are exactly the reason.
tree_digest() {
  [ -d "$1" ] || { printf '<absent>\n'; return 0; }
  ct_walk "$1" "" | LC_ALL=C sort
}

# Run the hook in a sandbox. $1 sandbox, $2 event JSON. Echoes the exit code.
#
# EVERY call runs from a FRESH HARNESS-OWNED RUN DIRECTORY. This replaces the former optional
# third argument, and the replacement is the point: the old default was `.`, the harness's own
# checkout, so almost every call ran the hook from inside the repository. Two of the hook's
# fallbacks are defined against the PROCESS working directory rather than the event's `cwd` -- the
# `cwd`-absent backfill from `pwd -P`, and a RELATIVE PLC_RESUME_PATH -- so those rows were reading
# the developer's checkout, which can have a real `RESUME.md` at its root.
#
# The old design managed that hazard with a per-row opt-in; this one REMOVES it. A directory the
# harness just created cannot contain a `RESUME.md`, cannot contain a `.git/`, and cannot be written
# by a concurrent session -- so the exclusion is STRUCTURAL rather than a denylist somebody has to
# keep current: isolation by construction, not by exclusion list.
#
# Both OWNED TREES (the sandbox and the run directory) are compared by
# RECURSIVE CONTENT DIGEST, before and after. The previous check diffed NAME SETS at one level, so it
# detected CREATION only: appending to a file that already existed, and writing anywhere inside a
# directory that already existed, both left the name set unchanged. The relative-path audit-log
# mutant was therefore caught on call 1 and invisible for the remaining 65.
#
# A SNAPSHOT, not a declared allow-list. A hand-written "files this row creates" list goes stale in
# silence; a before/after diff cannot. Anything a row created BEFORE the call is in `before` by
# construction, so the hostile-named fixtures further down need no exemption.
# `RH_IMPL` is an EXPLICIT per-call implementation override, set by the caller around the call. It
# exists because `IMPL=<double> run_hook ...` -- the obvious spelling -- silently did NOT take: the
# call runs inside command substitution and the hook is exec'd from a further subshell, and the row
# that used it measured the UNMODIFIED hook while reading as though it had driven a test double.
# Measured, not theorised: the row reported `entries=[s.clearedat s.marker]`, which is the defect
# under test, from a tree where it is fixed.
run_hook() {
  local d="$1" ev="$2" rundir rc before after stray rd_before rd_after rd_stray impl
  impl="${RH_IMPL:-$IMPL}"
  rundir="$(mktemp -d "$WORK/rd.XXXXXX")" || { printf '127'; return 0; }
  # The state directory is the ONE thing the hook may create in the sandbox, so it is excluded from
  # the sandbox digest by PREFIX -- its CONTENTS are the hook's own business and are asserted by other
  # rows, not here. Nothing is excluded from the run-directory digest: `TMPDIR` is
  # `$d`, so a `plc-context-floor` appearing in the run directory is itself the finding.
  before="$(tree_digest "$d" | grep -v '^plc-context-floor\(/\| \)' || true)"
  rd_before="$(tree_digest "$rundir")"
  # WATCHDOG. Not defensive decoration: the hook opens the marker path, and opening a FIFO for write
  # BLOCKS until a reader appears. MEASURED with a mutant that repairs only directories -- the whole
  # suite hung and had to be killed at 400s, producing NO output at all. A hang is the one failure
  # mode an exit-code assertion cannot see, and it kills every row after it as well, including the
  # row written to catch exactly this. So it is caught HERE, once, for all 66 calls, rather than in
  # a row that a hang would prevent from ever running. `timeout` reports 124, which is a perfectly
  # ordinary exit code to an assertion.
  #
  # Where `timeout` is absent the call runs bare and a hang still kills the suite -- stated rather
  # than silently assumed away.
  printf '%s' "$ev" | ( cd "$rundir" || exit 127
    env -u PLC_CONTEXT_FLOOR -u PLC_CONTEXT_FLOOR_PCT -u PLC_CONTEXT_FLOOR_STEP \
        -u PLC_CONTEXT_WINDOW -u PLC_RESUME_PATH TMPDIR="$d" LC_ALL=C \
        PLC_FLOOR_LIB="$FLOOR_LIB" \
        ${CT_TIMEOUT:+timeout 20} /bin/bash "$impl" >/dev/null 2>&1 )
  rc=$?
  after="$(tree_digest "$d" | grep -v '^plc-context-floor\(/\| \)' || true)"
  rd_after="$(tree_digest "$rundir")"
  if [ "$rd_before" != "$rd_after" ]; then
    rd_stray="$(diff <(printf '%s\n' "$rd_before") <(printf '%s\n' "$rd_after") | grep '^[<>]' || true)"
    printf 'called from line %s (run dir): %s\n' "${BASH_LINENO[0]}" \
      "$(printf '%s' "$rd_stray" | tr '\n' ' ')" >> "$STRAYLOG"
  fi
  stray=""
  [ "$before" != "$after" ] && \
    stray="$(diff <(printf '%s\n' "$before") <(printf '%s\n' "$after") | grep '^[<>]' || true)"
  # RECORDED TO A FILE, not reported here, and that is not a style choice. Every caller captures this
  # function's stdout (`rc="$(run_hook ...)"`), so the whole body runs in a COMMAND-SUBSTITUTION
  # SUBSHELL: a `no` called here increments a counter that dies with the subshell, and its message
  # would be captured INTO `$rc` instead of printed. Measured -- the first cut of this check did
  # exactly that and the mutant it was written for stayed green in all 67 rows. File writes DO
  # survive the subshell, so the finding is appended here and asserted once, below.
  [ -n "$stray" ] && printf 'called from line %s: %s\n' "${BASH_LINENO[0]}" \
    "$(printf '%s' "$stray" | tr '\n' ' ')" >> "$STRAYLOG"
  printf '%s' "$rc"
}
# Created up front so the final assertion can distinguish "nothing was written" from "the log was
# never created because run_hook never ran".
STRAYLOG="$WORK/.stray-log"; : > "$STRAYLOG"

sandbox() { local d; d="$(mktemp -d "$WORK/sb.XXXXXX")"; printf '%s' "$d"; }
ev_for()  { printf '{"session_id":"s","transcript_path":"%s/t.jsonl","cwd":"%s"}' "$1" "$1"; }
# Arm a marker that is definitively OLDER than any RESUME.md written after it. Done by hand rather
# than by a first hook call, so rows using it do not depend on the first-call path being broken or fixed. Defined
# HERE with the other helpers, not next to its first heavy user: bash resolves functions at call
# time, so a definition further down the file is invisible to every row above it -- which is why
# this body was previously inlined by hand at the clear-path rows, hard-coding the marker path convention
# in a suite whose contract already folds that convention in. Three of those inlines are now calls.
# ONE hand-rolled arm survives on purpose, at the "RESUME older than the marker" row: it sleeps
# BEFORE writing the marker, so the marker ends up newer than the checkpoint -- the opposite of what
# arm_old is for. Do not "finish the refactor" by converting it; that row would stop testing its case.
arm_old() { mkdir -p "$1/plc-context-floor"; : > "$1/plc-context-floor/s.marker"; sleep 1; }

echo "=== context-floor contract suite ==="
echo "    impl: $IMPL"
echo

# =============================================================================
# Live contract rows -- these must be GREEN
# =============================================================================
echo "-- lifecycle --"

d="$(sandbox)"; usage_line 120000 > "$d/t.jsonl"
rc="$(run_hook "$d" "$(ev_for "$d")")"
{ [ "$rc" = 0 ] && [ ! -e "$d/plc-context-floor/s.marker" ]; } \
  && ok "under the floor: allows, and arms nothing" \
  || no "under the floor: allows, and arms nothing (rc=$rc)"

d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
rc="$(run_hook "$d" "$(ev_for "$d")")"
{ [ "$rc" = 2 ] && [ -e "$d/plc-context-floor/s.marker" ]; } \
  && ok "first over-floor edit: arms and blocks" \
  || no "first over-floor edit: arms and blocks (rc=$rc)"

# Same call as the row above, one difference: a checkpoint
# exists. The marker used to be created and compared against in the same pass, making
# `mtime(RESUME) > mtime(marker)` unsatisfiable and the first call of every arm cycle a block --
# however fresh the checkpoint was.
#
# THE SECOND AND THIRD CLAUSES ARE THE POINT. Asserting `rc` alone is not enough:
# an implementation that exits 0 BEFORE arming satisfies that: it then re-enters the first-call
# branch on every subsequent call and the floor is off for the rest of the session, while every
# exit-code-only row in this suite stays green. `s.marker` present proves the arm happened;
# `s.clearedat` absent proves what was granted is one CALL, not a STEP-sized token window taken by
# reusing the clear path.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"; echo current > "$d/RESUME.md"
rc="$(run_hook "$d" "$(ev_for "$d")")"
{ [ "$rc" = 0 ] && [ -e "$d/plc-context-floor/s.marker" ] \
                && [ ! -e "$d/plc-context-floor/s.clearedat" ]; } \
  && ok "first over-floor edit with a checkpoint present: arms, allows, and grants no window" \
  || no "first over-floor edit with a checkpoint present: arms, allows, and grants no window (rc=$rc)"

d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"; echo stale > "$d/RESUME.md"
mkdir -p "$d/plc-context-floor"; sleep 1; : > "$d/plc-context-floor/s.marker"
rc="$(run_hook "$d" "$(ev_for "$d")")"
[ "$rc" = 2 ] && ok "RESUME older than the marker: stays blocked" \
              || no "RESUME older than the marker: stays blocked (rc=$rc)"

d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
arm_old "$d"; echo fresh > "$d/RESUME.md"
rc="$(run_hook "$d" "$(ev_for "$d")")"
{ [ "$rc" = 0 ] && [ ! -e "$d/plc-context-floor/s.marker" ] && [ -f "$d/plc-context-floor/s.clearedat" ]; } \
  && ok "RESUME refreshed: clears the marker and records clearedat" \
  || no "RESUME refreshed: clears the marker and records clearedat (rc=$rc)"

# A grace record is TWO lines: the occupancy, then the checkpoint the window was earned
# against. Seeding it by hand needs the second line, and the helper computes it the same way the
# hook does rather than restating the encoding -- a fixture that spells the format itself is a
# second implementation of it, and the two drift.
seed_grace() {          # $1 sandbox, $2 occupancy, $3 checkpoint path (default: the sandbox's own)
  local p="${3:-$1/RESUME.md}"
  mkdir -p "$1/plc-context-floor"
  printf '%s\n%s\n' "$2" "$(jq -nr --arg r "$p" '$r | @uri')" > "$1/plc-context-floor/s.clearedat"
}

d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
seed_grace "$d" 155000
rc="$(run_hook "$d" "$(ev_for "$d")")"
[ "$rc" = 0 ] && ok "within the post-clear grace: allows" \
              || no "within the post-clear grace: allows (rc=$rc)"

# CF-AC10 -- a record with NO second field grants NO grace. This is the shape every record written
# by an older version of the hook has, so it is the upgrade path, and the direction is fail-CLOSED: one extra block, never
# an unearned window. Asserted rather than left implicit because the fixture above USED to look
# exactly like this, and "the old fixture now blocks" is a fact worth pinning instead of quietly
# rewriting.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
mkdir -p "$d/plc-context-floor"; echo 155000 > "$d/plc-context-floor/s.clearedat"
rc="$(run_hook "$d" "$(ev_for "$d")")"
[ "$rc" = 2 ] && ok "CF-AC10 a legacy single-field grace record grants no grace" \
              || no "CF-AC10 a legacy single-field grace record grants no grace (rc=$rc)"

d="$(sandbox)"; usage_line 200000 > "$d/t.jsonl"
seed_grace "$d" 155000
rc="$(run_hook "$d" "$(ev_for "$d")")"
[ "$rc" = 2 ] && ok "past the grace step: re-arms and blocks" \
              || no "past the grace step: re-arms and blocks (rc=$rc)"

# The first call's one chance recurs ONCE PER ARM CYCLE, not once per session. The clear path removes the
# marker, so crossing the next STEP threshold arms afresh -- and with a checkpoint present that
# fresh arm allows again, exactly as the session's first one did. Locked as in-contract: denying
# it would reproduce the first-call defect itself at every threshold after the first, demanding a checkpoint at the
# same instant the new threshold is defined. Identical to the row above except that a checkpoint
# exists, which is the whole difference the decision turns on -- keep them adjacent.
d="$(sandbox)"; usage_line 200000 > "$d/t.jsonl"; echo current > "$d/RESUME.md"
seed_grace "$d" 155000
rc="$(run_hook "$d" "$(ev_for "$d")")"
{ [ "$rc" = 0 ] && [ -e "$d/plc-context-floor/s.marker" ]; } \
  && ok "past the grace step with a checkpoint present: re-arms and allows once more" \
  || no "past the grace step with a checkpoint present: re-arms and allows once more (rc=$rc)"

# The arm is a CHECK (`[ ! -e ]`) followed by a CREATE, and the winner of that pair gets the arm
# cycle's one free call. A plain `>` truncates a marker that appeared in between, so every process
# in a concurrent batch believes it is the first -- measured at 20/20 allows at width 2 and 30/30
# at width 3 before the fix, i.e. the granted unit was "one batch of arbitrary width", not one
# call. Concurrent Edit/Write hooks are not hypothetical: parallel subagents are a common
# dispatch mode.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"; echo current > "$d/RESUME.md"
ev="$(ev_for "$d")"; W=6
for i in $(seq "$W"); do
  ( printf '%s' "$ev" | env -u PLC_CONTEXT_FLOOR -u PLC_CONTEXT_FLOOR_PCT -u PLC_CONTEXT_FLOOR_STEP \
      -u PLC_CONTEXT_WINDOW -u PLC_RESUME_PATH TMPDIR="$d" LC_ALL=C /bin/bash "$IMPL" >/dev/null 2>&1
    printf '%s' "$?" > "$d/rc.$i" ) &
done
wait
# Count allows AND blocks AND rc files. Counting allows alone cannot tell "1 allow, W-1 blocks"
# from "1 allow, W-1 processes that crashed or never ran" -- `cat` on a missing rc file yields
# empty, which simply is not counted, so a batch where five of six died reads as a pass. That is
# the passes-because-nothing-executed class, and it matters more here
# than usual: this row is the only oracle for the first-call path, with nothing behind it.
allows=0; blocks=0; seen=0
for i in $(seq "$W"); do
  [ -f "$d/rc.$i" ] || continue
  seen=$((seen+1))
  case "$(cat "$d/rc.$i")" in 0) allows=$((allows+1)) ;; 2) blocks=$((blocks+1)) ;; esac
done
{ [ "$seen" = "$W" ] && [ "$allows" = 1 ] && [ "$blocks" = $((W-1)) ]; } \
  && ok "a concurrent batch of $W first calls yields exactly one allow and $((W-1)) blocks" \
  || no "a concurrent batch of $W first calls yields exactly one allow and $((W-1)) blocks (ran=$seen/$W allows=$allows blocks=$blocks)"

# CF-AC5b -- THE SAME BATCH, BUT WITH A CORRUPT NODE ALREADY AT THE MARKER PATH.
# The row above starts from a CLEAN sandbox. This one does not, because the combination is not
# hypothetical: the marker repair
# reproduced the first-call defect through a second filename. MEASURED, 5 of 5 concurrent runs before the fix
# and 0 of 10 after -- the winner's `mv` succeeded and it armed `<sid>.marker`; the loser's `mv`
# failed BECAUSE THE SOURCE WAS ALREADY GONE, fell into the unrepairable branch, and armed
# `<sid>.wedged` -- a name nobody was contending for. Both got the one-call grant. The single-winner
# guarantee is a property of ONE filename, and a second one silently repealed it.
#
# The fix is a distinction, not a lock: a failed rename because the node is GONE means we lost a
# race, which is the ordinary O_EXCL-loser case; only a node still sitting there is unrepairable.
# The first attempt tested "has somebody finished repairing" instead and was itself racy -- between
# the winner's rename and its create the path is EMPTY -- and still allowed both, 8 of 8.
#
# THE ROW ASSERTS "AT MOST ONE ALLOW", NOT "EXACTLY ONE", and the weakening is deliberate, measured,
# and argued here rather than quietly convenient. What a guard must never do is hand out a second
# allow; handing out none for one call is the fail-CLOSED direction and self-heals on the next call,
# because by then the repair has completed and the marker is an ordinary regular file. Measured after
# the mutex landed: 0 double-allows in 660 loaded iterations, and 5 all-blocked batches in roughly a
# thousand (~0.5%).
#
# THAT ZERO IS A PROPERTY OF THE HOST, NOT A BOUND ON THE GUARD. The guard CAN hand out a second
# allow, by a named mechanism, reproducibly, and that mechanism is written out in the hook under
# "WHAT THIS LOCK ACTUALLY GUARANTEES".
#
# Three windows in
# the repair path are reachable on unmodified code; widening two of them makes this row fail 8 of 8
# batches with `worst=2`, and the SAME assertion with no widening reports zero on an idle many-core
# machine -- which is exactly what `0/660` measured. Reaching the window is a function of runnable
# threads per core, so a 2-4 vCPU runner reaches it and an idle many-core machine does not. Do not quote the `0/660`
# as evidence the guard holds; quote it as evidence such a host cannot test the guard.
#
# The all-blocked shape is only HALF characterised -- one process repaired, all four
# finished with `FIRST_ARM=0`, and the marker existed, yet no process reported creating it -- and the
# probe that would answer "who created it" made the phenomenon stop reproducing entirely (660
# iterations, zero occurrences). Instrument-changes-the-outcome is itself the finding; it is documented
# with the rate and the partial mechanism rather than papered over with a retry loop.
#
# LIVENESS IS NOT LOST BY THIS. "A repair leads to an allow" is asserted deterministically, in a
# single process, by the four CF-AC1 shape rows (`rcs=022`); it does not need a concurrent batch.
#
# START BARRIER. Without one, the children are staggered by however long each `mktemp -d` and fork
# took, and the interleaving this row exists to catch became load-dependent: the double-allow it
# eventually did catch appeared once, in a mutant row, during a sixteen-suite matrix run, and not at
# all on an idle machine. Spinning on a release file puts all CW processes into the repair window
# together.
#
# WIDTH AND REPETITION ARE CALIBRATED AGAINST THE MUTANTS, not chosen for looking thorough. At the
# width this row shipped with -- four processes, one batch -- BOTH mutants that reintroduce the
# double-allow (the repair mutex removed; the fail-open trusting a stale create) ran GREEN through
# the whole suite -- the row would have been decorative.
# Measured on an idle machine, per batch: width 4 reproduced 0 of 20, width 8 reproduced 4 of 20,
# width 12 reproduced 9 of 20.
#
# THE TWO HALVES ARE NOT DETECTED EQUALLY WELL, and the weaker number is written here rather than
# averaged away. Measured at this width and repetition:
#   * mutex removed          -- dies in 7 of 8 batches; a suite run misses it with probability ~0
#   * fail-open not retried  -- reproduces in ~15% of batches (3 of 20 standalone, 1 of 8 here), so a
#                               suite run misses it about a quarter of the time
# The second window is intrinsically narrower: it is only the gap between one process's rename and
# its create. Closing that detection gap needs either ~20 batches (measured cost: the suite goes from
# 67s to roughly 100s, against 44s before this row was widened) or a test double that widens the
# window deliberately, and neither is done here -- stated, with these
# numbers, rather than left as an unstated "covered".
#
# The hook is invoked DIRECTLY rather than through `run_hook`, like the batch row above it: the
# per-call owned-tree digests are what make `run_hook` expensive, and repeating them 96 times would
# roughly double the suite to re-prove a property the row above already covers on every other call.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
echo current > "$d/RESUME.md"
cev="$(ev_for "$d")"; CW=12; CR=8
cmax=0; cbad=0; cside_seen=0; cshort=0; cgood=0
# FORENSICS FOR THE ROUND THAT MISBEHAVES -- without them a red on this row arrives with
# no explanation. Every anomalous round used to erase its own evidence twice over: the tally
# keeps counts and nothing else, `tree_digest` above deliberately filters the guard's state
# directory out (that check is about STRAY writes, so excluding the state dir is correct there and
# useless here), and the next round's `rm -rf` at the top of the loop wipes the directory before
# any human sees it. So a red arrives as two integers -- `1 batches did not; worst=2` -- which is
# exactly enough to know something happened and not nearly enough to know what.
#
# WHAT THE LISTING DISCRIMINATES, and why it is worth capturing rather than reasoning about. Two
# mechanisms produce the identical `worst=2` signature and they leave different debris:
#   * a SECOND REPAIRER (under the OLD acquire the lock was taken by
#     `mkdir` and stamped with its owner's pid a few lines later, and the reclaim stanza deleted a
#     lock it read as ownerless -- see W1 in the hook's own header; that acquire is gone) leaves TWO aside
#     nodes carrying TWO DIFFERENT pids, because each repairer names its aside after its own `$$`.
#     THIS IS NO LONGER A HYPOTHESIS. It was measured by widening that window and
#     asserting lock ownership at release; see the hook's "WHAT THIS LOCK ACTUALLY GUARANTEES".
#   * a RESOURCE FAIL-OPEN leaves NO aside at all: the hook exits 0 at [[skills/project-lifecycle/hooks/context-floor.sh#statedir-failopen]]
#     when it cannot manage the state directory, and again when no `stat` format could be probed -- and that probe forks
#     four subprocesses, so a runner low on process slots can fail it. Same signature, unrelated
#     cause, opposite fix.
# Nothing in this suite can currently tell those apart. The listing can, and it costs one `ls`.
#
# IT RUNS AFTER `wait`, DELIBERATELY. What makes this hard was measured: probes placed
# inside the racing code path made the phenomenon stop reproducing entirely (660 iterations, zero
# occurrences, including 420 at load average 21). So this adds NOTHING to the hook and nothing to
# the window -- not a write, not a stat, not a fork. It reads wreckage after every process has
# exited, which is the one place an instrument cannot change the outcome it is measuring.
#
# CAPTURED FOR ANY `callows != 1` ROUND, not just the double-allow. Zero-allow rounds are the other
# open shape -- ~0.5%, half-characterised, and the missing half is "who created the marker that
# no process reported creating". That question is answered by a listing, and this row is where
# the shape occurs. Capturing only the failures would keep the cheaper half of the mystery dark.
cforensic=""
# SPLIT INTO TWO FUNCTIONS SO THEY CAN BE ASSERTED ON DIRECTLY. Inline, the collector could only be
# exercised by winning a race, and a row that must win a race to assert anything reports nothing
# most of the time. Separated, `CF-AC5b-meta` below feeds both a synthetic state directory and
# checks what they say -- which is what lets this instrument carry an oracle of its own rather than
# being the one piece of the suite nobody checks.
ac5b_anomalous() {   # $1 allows  $2 seen  $3 width  $4 statedir
  [ "$1" != 1 ] || [ "$2" != "$3" ] || [ -e "$4/s.wedged" ]
}
ac5b_forensic() {    # $1 round  $2 allows  $3 seen  $4 width  $5 statedir  $6 rcdir
  _crcs=""; _i=1
  while [ "$_i" -le "$4" ]; do
    _crcs="$_crcs$(cat "$6/rc.$_i" 2>/dev/null || printf '?')  "
    _i=$((_i+1))
  done
  # THE LEGEND IS PRINTED WITH THE DEBRIS, NOT LEFT IN A COMMENT SOMEWHERE. The whole value of this
  # listing is that node TYPE discriminates between mechanisms, and a reader meeting it in CI output
  # has no way to know that. It is also why the staging file gets its own bucket below: the atomic
  # acquire introduced `<sid>.repair.tmp.<pid>` as a NEW class of node in this directory, and the
  # debris shape is the only attribution discriminator -- an unexplained new filename in a
  # forensic dump is exactly how the next red gets misread.
  printf '\n    round %s: allows=%s seen=%s of %s   exit codes: %s\n' "$1" "$2" "$3" "$4" "$_crcs"
  printf '      legend: %s\n' \
    "*.corrupt.* aside node -- DIRECTORY = the genuine corrupt marker, REGULAR FILE = a legitimate marker a repair moved aside (W2); *.repair = the lock, a regular file whose content is the owner pid; *.repair.tmp.* = acquire staging, normally unlinked immediately, one left behind means a process died between writing it and publishing it; *.wedged = the guard's own sidecar state; NO aside node at all = a resource fail-open, an unrelated cause with the same allow-count signature"
  printf '      -- staging files (%s):\n%s\n' \
    "$(ls -A "$5" 2>/dev/null | grep -c '\.repair\.tmp\.' || printf 0)" \
    "$(ls -la "$5" 2>/dev/null | grep '\.repair\.tmp\.' | sed 's/^/        /' || true)"
  printf '      -- everything else:\n%s' \
    "$(ls -la "$5" 2>/dev/null | grep -v '\.repair\.tmp\.' | sed 's/^/        /' || true)"
}
# The owned-tree check `run_hook` performs per call is done ONCE around the whole loop instead:
# invoking the hook directly would otherwise drop the stray-write oracle on
# the one path no other row reaches -- repair UNDER CONTENTION.
# Two digests cover 96 calls: any file appearing
# or changing outside the guard's own state directory is a finding, wherever in the loop it happened.
cbefore="$(tree_digest "$d" | grep -v '^plc-context-floor\(/\| \)' || true)"
# The batch's own bookkeeping lives OUTSIDE the sandbox. It used to be written into `$d`, and the
# check just added then reported the row's own `crc.*` files as stray writes -- the oracle was right
# and the fixture was dirty.
crcd="$(mktemp -d "$WORK/crc.XXXXXX")"
for r in $(seq "$CR"); do
  rm -rf "$d/plc-context-floor"; rm -f "$crcd"/rc.* "$crcd/.go"
  mkdir -p "$d/plc-context-floor/s.marker"; echo x > "$d/plc-context-floor/s.marker/inner"
  for i in $(seq "$CW"); do
    ( while [ ! -e "$crcd/.go" ]; do :; done
      printf '%s' "$cev" | env -u PLC_CONTEXT_FLOOR -u PLC_CONTEXT_FLOOR_PCT -u PLC_CONTEXT_FLOOR_STEP \
        -u PLC_CONTEXT_WINDOW -u PLC_RESUME_PATH TMPDIR="$d" LC_ALL=C \
        ${CT_TIMEOUT:+timeout 20} /bin/bash "$IMPL" >/dev/null 2>&1
      printf '%s' "$?" > "$crcd/rc.$i" ) &
  done
  sleep 0.05; : > "$crcd/.go"
  wait
  callows=0; cseen=0
  for i in $(seq "$CW"); do
    [ -f "$crcd/rc.$i" ] || continue
    cseen=$((cseen+1))
    [ "$(cat "$crcd/rc.$i")" = 0 ] && callows=$((callows+1))
  done
  [ "$cseen" = "$CW" ] || cshort=$((cshort+1))
  [ "$callows" -gt "$cmax" ] && cmax="$callows"
  [ "$callows" -gt 1 ] && cbad=$((cbad+1))
  [ "$callows" = 1 ] && cgood=$((cgood+1))
  [ -e "$d/plc-context-floor/s.wedged" ] && cside_seen=$((cside_seen+1))
  # Capture BEFORE the next iteration's `rm -rf` at the top of the loop. `|| true` on every
  # collector: a missing rc file or an unreadable directory is itself information, and a forensic
  # step must never be the thing that turns a diagnosable round into a dead suite.
  if ac5b_anomalous "$callows" "$cseen" "$CW" "$d/plc-context-floor"; then
    cforensic="$cforensic$(ac5b_forensic "$r" "$callows" "$cseen" "$CW" "$d/plc-context-floor" "$crcd")"
  fi
done
rm -f "$crcd/.go"
cafter="$(tree_digest "$d" | grep -v '^plc-context-floor\(/\| \)' || true)"
if [ "$cshort" != 0 ]; then
  no "CF-AC5b concurrent batches over a corrupt marker: $cshort of $CR batches did not run every call"
elif [ "$cbad" != 0 ]; then
  no "CF-AC5b $CR concurrent batches over a corrupt marker grant AT MOST ONE allow ($cbad batches did not; worst=$cmax)"
elif [ "$cside_seen" != 0 ]; then
  no "CF-AC5b losing the repair race must not arm a second marker name (a sidecar appeared in $cside_seen batches)"
elif [ "$cgood" = 0 ]; then
  # THE LIVENESS HALF, restored after the safety half was weakened to "at most one". It closes
  # the hole the weakening opened: with only an upper bound, a hook that lost the first-arm grant
  # entirely -- creating the marker and then blocking anyway -- would pass every batch at zero allows.
  # Requiring at least ONE batch to grant exactly one keeps that regression fatal while still
  # tolerating the ~0.5% all-blocked batch that was measured and could not be fully characterised:
  # eight independent batches make "every one of them was the rare shape" a non-event.
  no "CF-AC5b no batch granted an allow at all ($CR batches, all blocked) -- the first-arm grant is gone"
elif [ "$cbefore" != "$cafter" ]; then
  no "CF-AC5b concurrent repair wrote outside the guard's own state directory: $(diff <(printf '%s\n' "$cbefore") <(printf '%s\n' "$cafter") | grep '^[<>]' | tr '\n' ' ')"
else
  ok "CF-AC5b $CR concurrent batches of $CW over a corrupt marker grant at most one allow ($cgood granted one), on one marker name, writing nothing outside the state directory"
fi
# PRINTED ON BOTH PATHS, and the `ok` half is the deliberate one. A zero-allow round does not fail
# this row -- the bound is "at most one", and `cgood` only has to be non-zero -- so the all-blocked
# shape occurs inside PASSING runs and has never left a trace. Emitting only on failure would keep
# it that way. The verdict semantics are untouched: this prints after the ok/no line and changes
# neither, so a green run stays green and the tally is unmoved.
if [ -n "$cforensic" ]; then
  printf '  CF-AC5b forensics -- rounds that did not grant exactly one allow:%s\n' "$cforensic"
fi

# CF-AC5b-meta -- THE COLLECTOR ABOVE IS ITSELF AN INSTRUMENT, SO IT GETS AN ORACLE.
# A red that arrives with no state attached is the whole reason the collector exists; adding
# a collector that nothing checks would reproduce that defect one layer up. The row above cannot
# assert its own output -- it only emits when a race misbehaves, which is rare by construction and
# never on demand -- so the two functions are driven directly against a SYNTHETIC state directory.
# That is the same "use a double, do not wait to win a race" reasoning `MVFAIL` and `CWDPROBE` use
# further down this file.
#
# WHAT IT DOES NOT CLAIM: this proves the collector FORMATS and TRIGGERS correctly. It does not
# prove the wiring -- that the row calls it on the right rounds -- which is asserted only by the
# fact that both call sites are one line apart and reviewed. Saying so here rather than letting a
# green row imply more than it checked.
d="$(sandbox)"; msd="$d/statedir"; mrd="$d/rcdir"
mkdir -p "$msd" "$mrd"
# The debris a SECOND REPAIRER leaves: two asides on two pids, and the node types that tell them
# apart -- a directory is the genuine corrupt node, a regular file is a legitimate marker that a
# later repairer moved aside. A resource fail-open leaves neither.
mkdir -p "$msd/s.corrupt.111.0"; : > "$msd/s.corrupt.222.0"; : > "$msd/s.marker"
# A STAGING FILE LEFT BEHIND BY AN INTERRUPTED ACQUIRE. This is a NEW class of node in the state
# directory, introduced when the acquire became atomic, and the state directory's debris shape is
# the ONLY attribution discriminator. An unexplained new filename in a forensic dump is how
# the next red gets misread, so the collector must bucket it separately and the legend must name it.
: > "$msd/s.repair.tmp.333"
mi=1; while [ "$mi" -le 12 ]; do
  case "$mi" in 4|6|10) printf '0' > "$mrd/rc.$mi" ;; *) printf '2' > "$mrd/rc.$mi" ;; esac
  mi=$((mi+1))
done
mout="$(ac5b_forensic 7 3 12 12 "$msd" "$mrd")"
mmiss=""
for want in 'round 7' 'allows=3' 'seen=12 of 12' 's.corrupt.111.0' 's.corrupt.222.0' \
            'staging files (1)' 's.repair.tmp.333' 'legend:' '*.repair.tmp.*'; do
  case "$mout" in *"$want"*) ;; *) mmiss="$mmiss $want" ;; esac
done
# The exit codes must survive as a row, not as a count: "three processes were allowed" is the
# claim a tally already makes, and WHICH three is what a tally cannot say.
case "$mout" in *'2  2  2  0  2  0  2  2  2  0  2  2'*) ;; *) mmiss="$mmiss <exit-code-row>" ;; esac
# SEPARATELY BUCKETED, NOT MERELY PRESENT. A collector that dumped one flat listing would satisfy
# every membership test above while destroying the discriminator: the staging file would sit in the
# same block as the aside nodes and read as repair debris. So the aside nodes must NOT appear in the
# staging block -- checked by taking the staging block alone and requiring it to name neither.
mstage="${mout#*-- staging files}"; mstage="${mstage%%-- everything else*}"
case "$mstage" in
  *s.corrupt.*) mmiss="$mmiss <staging-bucket-contains-repair-debris>" ;;
esac
if [ -n "$mmiss" ]; then
  no "CF-AC5b-meta forensic block omits:$mmiss"
else
  ok "CF-AC5b-meta forensic block names the round, its allow count, every exit code in order, both aside nodes, and buckets acquire staging files separately under a legend that explains every node class"
fi

# The predicate, both directions. The FALSE case is the load-bearing one: a collector that cannot
# stay quiet on a healthy round would print on all eight every run, and would have been deleted
# within a week.
mclean="$d/clean"; mkdir -p "$mclean"
mwedge="$d/wedged"; mkdir -p "$mwedge"; : > "$mwedge/s.wedged"
mbad=""
ac5b_anomalous 1 12 12 "$mclean" && mbad="$mbad healthy-round-fired"
ac5b_anomalous 3 12 12 "$mclean" || mbad="$mbad double-allow-silent"
ac5b_anomalous 0 12 12 "$mclean" || mbad="$mbad all-blocked-silent"
ac5b_anomalous 1 11 12 "$mclean" || mbad="$mbad lost-call-silent"
ac5b_anomalous 1 12 12 "$mwedge" || mbad="$mbad sidecar-silent"
if [ -n "$mbad" ]; then
  no "CF-AC5b-meta anomaly predicate wrong on:$mbad"
else
  ok "CF-AC5b-meta anomaly predicate fires on double-allow, all-blocked (the rare shape, which does NOT fail the row), a lost call and a sidecar -- and stays silent on a healthy round"
fi

# CF-AC5b-meta POSITION -- the collector must stay OUTSIDE the window it measures, and that is a
# property of WHERE the call sits, so the check reads this file's own source rather than trusting a
# comment. Probes placed inside the racing path have been measured to make the phenomenon
# stop reproducing (660 iterations, zero occurrences, 420 of them at load average 21). A future edit
# that hoists a collector call up into the spawn loop -- to "catch it closer to the moment" -- would
# be the single most tempting and most destructive change anyone could make here, it would look
# correct in review, and nothing else in this suite would notice.
# THE RUNNING FILE, NOT A HARD-CODED PATH. It was `$HERE/<this file name>`,
# which reads the file ON DISK AT THAT PATH no matter which copy is executing -- so every row that
# checks this suite's own source was UNFALSIFIABLE: a mutated copy run directly still read the
# pristine original and reported green. Measured, on an attempt to prove the header row below could
# fail. `${BASH_SOURCE[0]}` is the file actually running, which is what "its own source" meant all
# along.
msrc="${BASH_SOURCE[0]}"
if [ ! -r "$msrc" ]; then
  no "CF-AC5b-meta position: cannot read own source at $msrc"
else
  mcall="$(grep -n 'ac5b_anomalous "\$callows"' "$msrc" | cut -d: -f1 | head -1)"
  mloop="$(grep -n 'for r in \$(seq "\$CR")' "$msrc" | cut -d: -f1 | head -1)"
  # The `wait` that closes the batch, i.e. the last one before the call site.
  mwait="$(awk -v c="${mcall:-0}" 'NR<c && /^[[:space:]]*wait$/ {n=NR} END{print n+0}' "$msrc")"
  # Anything calling a collector between the loop head and that `wait` is inside the window.
  minside="$(awk -v a="${mloop:-0}" -v b="$mwait" \
    'a>0 && b>a && NR>a && NR<b && /ac5b_(forensic|anomalous)/ {n++} END{print n+0}' "$msrc")"
  if [ -z "$mcall" ] || [ -z "$mloop" ] || [ "$mwait" = 0 ]; then
    # A zero-extraction is a FAIL, never a vacuous pass: it means the layout moved under the parser
    # and the check silently stopped covering anything.
    no "CF-AC5b-meta position: could not locate loop/wait/call (loop=${mloop:-<none>} wait=$mwait call=${mcall:-<none>}) -- the parser lost the row, it did not pass"
  elif [ "$minside" != 0 ]; then
    no "CF-AC5b-meta position: $minside collector call(s) sit between the spawn loop and \`wait\` -- that is inside the window under test"
  elif [ "$mcall" -lt "$mwait" ]; then
    no "CF-AC5b-meta position: the collector is called at line $mcall, before \`wait\` at line $mwait"
  else
    ok "CF-AC5b-meta collector is called after the batch's \`wait\` (line $mcall > $mwait) and no collector runs inside the spawn window"
  fi
fi

# CF-AC12 -- THE RELEASE-TIME OWNERSHIP ASSERTION, AND THE FIRST THING THAT HAS EVER WATCHED W1.
#
# THE GAP THIS CLOSES IS A MEASURED ABSENCE, NOT A DESIGN PREFERENCE. The string
# `STOLEN self=... found=...` has existed in `context-floor.sh`'s own prose as the
# record of a real measurement -- and it once existed in ZERO committed test files. CI reds of
# `CF-AC5b` arrived with nothing whatsoever watching the one phenomenon W1 produces. A measurement
# somebody wrote down in a comment is not an oracle; this row is that measurement moved to where a
# test can see it.
#
# THE ROW ASSERTS SILENCE, AND THAT IS THE SHAPE THAT SURVIVES THE FIX. The proof step
# ("widen W1 -> STOLEN fires") is what demonstrates the instrument works -- but it CANNOT be
# a permanent row, because the atomic acquire
# makes the widened arm silent too. A row asserting "the steal reproduces" would go red
# BECAUSE THE DEFECT WAS FIXED, which is the exact failure `CF-AC14` exists to make loud one layer
# up. So the permanent assertion is the negative one: under ordinary contention, on unmodified code,
# no process may release a lock it does not own.
#
# SILENCE HAS TWO CAUSES AND THE ROW MUST SEPARATE THEM. A run in which the release stanza was never
# reached is silent for a reason that says nothing about ownership, and accepting it would make this
# row satisfiable by a hook that never repairs anything. So the batch must also PROVE IT RAN: every
# round places a corrupt node at the marker path, and the process that wins the repair prints
# `repaired corrupt guard marker`. Holding the lock is what makes the release stanza run, so at least
# one repair per round is the evidence that the assertion was evaluated at all. This is the same
# discipline `RL-AC5-meta` applies to the bench's hit counter -- a zero-hit run fails as "it did not
# run", never as "the guard holds".
#
# WHY A REAL BATCH RATHER THAN ONE PROCESS. One process cannot steal its own lock, so a single-call
# fixture would assert nothing and pass forever. Contention is the only condition under which W1 or
# W3 can fire. On this class of host the expected count is ZERO -- reaching those windows is a
# function of runnable threads per core, and 0/660 was measured on an idle many-core machine -- so
# LOCALLY THIS ROW IS NOT EXPECTED TO CATCH ANYTHING. It is written for the 2-4 vCPU shared runner
# where `CF-AC5b` has gone red. Do not read a local green as evidence the guard holds;
# read it as this host declining to test it, which is the correction already written into `CF-AC5b`'s
# header.
#
# TWO ROUNDS, NOT EIGHT, AND ITS OWN FIXTURE RATHER THAN `CF-AC5b`'s. Piggy-backing the assertion on
# the batch above would have cost zero extra runtime and was rejected: `PLC_CF_ASSERT_OWNER` makes the
# hook fork a `cat` inside the release path, which is INSIDE the racing window `CF-AC5b` measures,
# and adding a probe to that path has been measured to stop the phenomenon reproducing entirely
# (660 iterations, zero occurrences). The row that goes red in CI does not get its
# fixture perturbed to save a few seconds.
ac12_stole() {   # $1 = file of collected stderr ; true when a release reported a foreign owner
  # ANCHORED, AND THE PID MUST BE DIGITS. The literal sentence `STOLEN self=... found=...` appears in
  # prose in several places, including the hook's own comment; a predicate loose enough to
  # match the prose form would report a steal from any run that merely quoted the string. The meta row
  # below demonstrates that rejection rather than asserting it in a comment.
  grep -q '^STOLEN self=[0-9][0-9]* found=' "$1"
}
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
echo current > "$d/RESUME.md"
oev="$(ev_for "$d")"; OW=12; OR=2
ordir="$(mktemp -d "$WORK/own.XXXXXX")"
for r in $(seq "$OR"); do
  # Only `.go` is cleared between rounds. The stderr files are keyed by round AND call and kept, so
  # the verdict below reads EVERY call of the whole fixture -- a per-round wipe would have made the
  # row report only the last round while looking like it covered all of them.
  rm -rf "$d/plc-context-floor"; rm -f "$ordir/.go"
  mkdir -p "$d/plc-context-floor/s.marker"; echo x > "$d/plc-context-floor/s.marker/inner"
  for i in $(seq "$OW"); do
    ( while [ ! -e "$ordir/.go" ]; do :; done
      printf '%s' "$oev" | env -u PLC_CONTEXT_FLOOR -u PLC_CONTEXT_FLOOR_PCT -u PLC_CONTEXT_FLOOR_STEP \
        -u PLC_CONTEXT_WINDOW -u PLC_RESUME_PATH PLC_CF_ASSERT_OWNER=1 TMPDIR="$d" LC_ALL=C \
        ${CT_TIMEOUT:+timeout 20} /bin/bash "$IMPL" >/dev/null 2>"$ordir/err.$r.$i" ) &
  done
  sleep 0.05; : > "$ordir/.go"
  wait
done
rm -f "$ordir/.go"
oerr="$ordir/all.err"
cat "$ordir"/err.*.* > "$oerr" 2>/dev/null || : > "$oerr"
orepairs="$(grep -c 'repaired corrupt guard marker' "$oerr" 2>/dev/null || true)"
osteals="$(grep -c '^STOLEN self=[0-9][0-9]* found=' "$oerr" 2>/dev/null || true)"
if [ "${orepairs:-0}" -lt "$OR" ]; then
  no "CF-AC12 the ownership assertion never ran: $OR rounds over a corrupt marker reported ${orepairs:-0} repair(s), so no process held the lock through a release -- silence here is not evidence about ownership"
elif ac12_stole "$oerr"; then
  no "CF-AC12 a release removed a lock this process does not own ($osteals report(s)): $(grep '^STOLEN self=' "$oerr" | sort | uniq -c | tr '\n' ' ')"
else
  ok "CF-AC12 $OR concurrent batches of $OW over a corrupt marker release only locks they own (${orepairs} repair(s) reached a release, 0 steals) -- on this host tier that is a declined test, not a proof"
fi

# CF-AC12-meta -- THE PREDICATE ABOVE DECIDES WHAT SILENCE MEANS, SO IT GETS ITS OWN ORACLE.
# The live row can only be exercised by winning a race that this host is measured never to win, so
# without this the entire criterion would rest on a `grep` nobody has ever seen match. Three cases,
# and the third is the one that matters: a broken-open predicate and a broken-shut one both look
# identical from a green run.
omfail=""
: > "$WORK/ac12.hit";  printf 'STOLEN self=4211 found=4298\n'                 >> "$WORK/ac12.hit"
: > "$WORK/ac12.miss"; printf '[context-floor] repaired corrupt guard marker\n' >> "$WORK/ac12.miss"
: > "$WORK/ac12.prose"; printf 'reported as `STOLEN self=... found=...` in one AC5b run\n' >> "$WORK/ac12.prose"
ac12_stole "$WORK/ac12.hit"    || omfail="$omfail a real report was not recognised;"
ac12_stole "$WORK/ac12.miss"   && omfail="$omfail an ordinary repair was read as a steal;"
ac12_stole "$WORK/ac12.prose"  && omfail="$omfail the PROSE form of the string was read as a steal;"
if [ -n "$omfail" ]; then
  no "CF-AC12-meta the steal predicate is wrong on:$omfail"
else
  ok "CF-AC12-meta the steal predicate accepts a real report, rejects an ordinary repair, and rejects the prose form of the same string -- so a silent run means no steal, never a broken grep"
fi

# =============================================================================
# A WIDENED-WINDOW BENCH FOR THE REPAIR-MUTEX DOUBLE-ALLOW.
#
# CF-AC5b above asserts an OUTCOME ("at most one allow") and on an idle many-core machine it measured
# 0 of 660. That zero is a property of the host, not a bound on the guard: the same row goes red
# on shared runners. The mechanism is known and written out in the hook under "WHAT THIS
# LOCK ACTUALLY GUARANTEES" -- two windows the repair path had before its acquire was made atomic:
#
#   W1  between taking the lock (then `mkdir "$_cfl"`) and stamping it with an owner pid. A caller
#       arriving inside it reads an EMPTY owner, classifies a LIVE lock as ownerless, `rm -rf`s it
#       and takes it.
#   W2  between the re-stat that establishes "still corrupt" and the `mv` that acts on it. `mv` does
#       not care that its target stopped being corrupt, so a second repairer moves aside the REGULAR
#       marker the first one just created.
#
# W1 ALONE IS NOT ENOUGH, and that control is the load-bearing fact of this whole design -- but read
# to the end of this paragraph before quoting its number. An earlier measurement put W1-widened at
# 102 passed / 0 failed, all 8 batches granting exactly one. THAT IS A SAMPLE, NOT A BOUND, and
# a later run falsified its absolute form: W1 alone CAN hand out a second allow (6 of 24 batches at
# width 12, one run taking 4 of 8 under heavy load). It is rare, load-sensitive, and never enough on
# its own -- the direction holds, the absolute does not. The full measurement is in the
# solo-configuration note further down; the correction is repeated HERE because this is where the
# claim gets made, and a reader who stops at this paragraph would carry away the wrong one. The
# original reading stands for what it showed: the invariant
# was already broken and the suite could not see it, because a suite that only asserts outcomes is
# blind to a broken invariant that has not yet produced a bad outcome. That is exactly how "the lock
# works" survived repeated CI reds. Both windows widened together is what produces the failure.
#
# THE SHIPPED HOOK IS NOT EDITED, NOT COPIED, NOT PATCHED. The widening comes from wrapper
# scripts placed ahead of the real binaries on `PATH`. Verified before choosing this rather than
# assumed: `ln "$_cft" "$_cfl"` is the ONLY bare `ln` in the hook (the RL-P2 anchor count below
# pins it), and `mv "$MARKER" "$_cfaside"` is the only `mv` anywhere in it. So
# THE DISCRIMINATOR IS THE ARGUMENT SHAPE, NOT THE CALL SITE.
#
# WHAT THIS BENCH MAY AND MAY NOT CLAIM.
#
# The block below is delimited by sentinels so its PRESENCE is mechanically checkable -- a future
# edit that drops the boundary language goes red. Its PHRASING is deliberately NOT pinned: a
# golden-string assertion turns every wording improvement into a test edit, which trains people to
# change the test without reading it. So the split is
# presence checked and truthfulness reviewed by a human, with the
# second half written down as an EXCLUSION rather than pretending an oracle covers it. The gate
# proves a criterion HAS an oracle; an oracle claiming to check truthfulness would be the
# fabrication that gate exists to prevent.
#
#RL-BOUNDARY-BEGIN
# MAY CLAIM: that the two-step `mkdir`-then-stamp-owner pattern is not atomic, and that under a
#   deliberately widened window it is exploitable -- a rival reads the empty owner, classifies a
#   live lock as ownerless, and both processes end up granted.
#
# MAY NOT CLAIM, and these are the three that matter:
#   1. That the REAL, narrow window has the same shape. This bench blew the window open by two
#      orders of magnitude; what happens at 150ms is not evidence about what happens at nanoseconds.
#   2. That a fix validated HERE closes the real window. A fix that merely SHRINKS the window
#      satisfies this bench while leaving the narrow race intact -- and now invisible, because this
#      would be the only oracle watching. A fix needs an independent argument: an acquire
#      that is atomic BY CONSTRUCTION (a single-syscall `flock`, or the owner pid carried in the
#      lock's own name so the lock cannot exist without its owner), or an explicit written
#      admission that the bench cannot see what would need to be seen.
#   3. That this bench is mechanistically connected to CI's roughly-every-other-run red. The link
#      to `CF-AC5b`'s CI reds is a CONSISTENCY argument -- matching debris shapes, and the only
#      other mechanism known to produce the same `worst=2` signature leaves no aside node at all --
#      not an identity proof. No CI red has ever been captured with its state directory attached.
#RL-BOUNDARY-END
#
# --- the shim pair, and the knobs that arm it ----------------------------
# UNSET/0 = UNWIDENED, and that is what makes the control honest: the control run is THE SAME CODE
# PATH with the knobs off, not a second code path that can drift away from the widened one.
RL_SHIMDIR="$(mktemp -d "$WORK/rlshim.XXXXXX")"
# Resolved HERE, from the un-widened PATH, and baked in absolute. A shim that re-resolves its own
# name at run time finds ITSELF -- the wrapper recurses until the process dies.
# THE W1 WRAPPER IS `ln`, NOT `mkdir` -- RE-POINTED, NOT RELAXED. The acquire used
# to take the lock with `mkdir` and stamp the owner a few lines later, and the shim widened that gap.
# The atomic acquire publishes the content first and the NAME with `ln`, so `mkdir` is no longer in
# the repair path at all and a wrapper around it would widen nothing while still reporting a number.
# The arm therefore moves to the new publish point and keeps asserting the same property -- that no
# rival can observe a lock whose owner is not yet recorded -- which post-fix must report ZERO, and
# that zero is now a real measurement rather than an artefact of an unhooked wrapper. Deleting the
# arm was the other honest option (`CF-GAP` offers it in so many words); it was not taken, because
# an arm still inserted at the publish point is what would catch a refactor walking the acquire back.
RL_REAL_LN="$(command -v ln 2>/dev/null || true)"
RL_REAL_MV="$(command -v mv 2>/dev/null || true)"
# ONE PATH VARIABLE, CONSTRUCTED ONCE. P1 verifies this same string, and the batch runs
# with this same string. If verification assembled its own, P1 could pass while the batch ran
# unwidened -- an unwidened run reports green, and that green reads as "the guard holds". That is
# the precise false-green this bench exists to close, so the two must not be able to drift.
RL_PATH="$RL_SHIMDIR:$PATH"

if [ -z "$RL_REAL_LN" ] || [ -z "$RL_REAL_MV" ]; then
  no "RL-SHIM the real ln/mv resolve from the un-widened PATH (ln=${RL_REAL_LN:-<none>} mv=${RL_REAL_MV:-<none>})"
else
  ok "RL-SHIM the real ln/mv resolve from the un-widened PATH and are baked into the shims absolute"

  { printf '#!/usr/bin/env bash\n_real=%s\n' "$(printf '%q' "$RL_REAL_LN")"
    cat <<'RL_LN_BODY'
# Widen the publish by delaying AFTER success. WHAT THAT NOW HOLDS OPEN IS THE SAFE STATE, and that
# is the point: the lock exists AND already carries its owner pid, because the content was written to
# the staging name before this link published it. Under the old `mkdir` acquire the same delay held
# open the state a rival misread as ownerless. Same probe, same place in the algorithm, opposite
# answer -- which is what makes the zero it now reports a measurement rather than an artefact.
# Defensive; the hook has exactly one two-argument call site and never passes an option.
[ "$#" -ne 2 ] && exec "$_real" "$@"
"$_real" "$@"; _rc=$?
if [ "$_rc" = 0 ] && [ "${PLC_RL_W1_MS:-0}" != 0 ]; then
  [ -n "${PLC_RL_HITLOG:-}" ] && printf '%s W1\n' "$$" >> "$PLC_RL_HITLOG"
  _s=$(( ${PLC_RL_W1_MS:-0} / 1000 )); _f=$(( ${PLC_RL_W1_MS:-0} % 1000 ))
  sleep "$_s.$(printf '%03d' "$_f")"
fi
# The real command's exit status is propagated UNCHANGED. A failed `ln` is how the hook learns it
# lost the lock race -- EEXIST IS the exclusion -- so swallowing it would rewrite the behaviour under
# test into one where every caller believes it holds the lock.
exit $_rc
RL_LN_BODY
  } > "$RL_SHIMDIR/ln"

  { printf '#!/usr/bin/env bash\n_real=%s\n' "$(printf '%q' "$RL_REAL_MV")"
    cat <<'RL_MV_BODY'
# Widen W2 by delaying BEFORE the rename: that is what holds a second repairer's `mv` open across
# the first one's rename-plus-create.
# Defensive; the hook has exactly one two-argument call site.
[ "$#" -ne 2 ] && exec "$_real" "$@"
if [ "${PLC_RL_W2_MS:-0}" != 0 ]; then
  [ -n "${PLC_RL_HITLOG:-}" ] && printf '%s W2\n' "$$" >> "$PLC_RL_HITLOG"
  _s=$(( ${PLC_RL_W2_MS:-0} / 1000 )); _f=$(( ${PLC_RL_W2_MS:-0} % 1000 ))
  sleep "$_s.$(printf '%03d' "$_f")"
fi
exec "$_real" "$@"
RL_MV_BODY
  } > "$RL_SHIMDIR/mv"
  chmod +x "$RL_SHIMDIR/ln" "$RL_SHIMDIR/mv"

  # --- the shims' oracle: the wrappers are driven DIRECTLY, outside any race --------
  # Same reasoning as `MVFAIL` and `CWDPROBE` further down: use a double, do not wait to win a race.
  # A row that must win a race before it can assert anything reports nothing most of the time.
  #
  # The two "it delayed" rows do NOT assert on a wall clock. They probe the wrapper MID-FLIGHT and
  # ask what the filesystem looks like while it is sleeping -- which is the property that actually
  # matters (ln delays AFTER the link exists, mv delays BEFORE the rename), and which a
  # coarse elapsed-seconds reading cannot distinguish at all.
  RL_W_MS=800          # long enough to probe inside; short enough not to dominate the suite
  u="$(sandbox)"; hl="$u/hits.log"
  rl_unit() {   # $1 = W1_MS  $2 = W2_MS  ; rest = the command line to run under the shims
    local w1="$1" w2="$2"; shift 2
    env PATH="$RL_PATH" PLC_RL_W1_MS="$w1" PLC_RL_W2_MS="$w2" PLC_RL_HITLOG="$hl" "$@"
  }
  # `grep -c` prints 0 AND exits 1 on no match, so the obvious `grep -c ... || printf 0` emits "00".
  # Measured, not reasoned: it made the first draft of RL-SHIM-a compare "00" against 0 and go red.
  rl_hits() { local n; n="$(grep -c "$1" "$hl" 2>/dev/null || true)"; printf '%s' "${n:-0}"; }
  # SPIN, NEVER `sleep`-then-sample. The mid-flight probes below have to land INSIDE the wrapper's
  # delay, and a fixed `sleep 0.3` assumes the child has already forked, exec'd and reached the
  # sleep -- an assumption a loaded machine falsifies, turning a correct shim red. The hit line is
  # written immediately adjacent to the sleep, so its appearance is the signal that the delay has
  # begun. Bounded at ~5s so a broken shim fails the row instead of hanging the suite.
  rl_await_hit() {   # $1 = tag
    local i=0
    while [ "$(rl_hits "$1")" -lt 1 ] && [ "$i" -lt 500 ]; do i=$((i+1)); sleep 0.01; done
  }

  # RL-SHIM-a -- `-p` is the fast path even when W1 is armed.
  #
  # THE HIT COUNT IS THE PRIMARY ORACLE AND THE CLOCK IS THE BACKSTOP, in that order deliberately.
  # `no log, no sleep` is one branch, so an armed `-p` that took the slow path logs -- deterministic,
  # load-independent, and it is what kills the mutant. The elapsed check is kept because a future
  # split of the log from the sleep would slip past the hit count alone, but it is coarse: measured
  # on an idle machine the four fast calls already read 1s across a second boundary, so the ceiling
  # is 2s and the delayed shape it must exclude is ~3.2s (measured 3s).
  : > "$hl"; SECONDS=0; echo x > "$u/psrc"
  rl_unit "$RL_W_MS" 0 ln -s "$u/psrc" "$u/p1"; rc_p=$?
  rl_unit "$RL_W_MS" 0 ln -s "$u/psrc" "$u/p2"
  rl_unit "$RL_W_MS" 0 ln -s "$u/psrc" "$u/p3"
  rl_unit "$RL_W_MS" 0 ln -s "$u/psrc" "$u/p4"
  e_p=$SECONDS; h_p="$(rl_hits W1)"
  if [ "$rc_p" != 0 ]; then
    no "RL-SHIM-a an option-bearing \`ln\` under an armed shim still succeeds (rc=$rc_p)"
  elif [ "$h_p" != 0 ]; then
    no "RL-SHIM-a an option-bearing \`ln\` logs no hit ($h_p logged -- the arity short-circuit is gone, so any unrelated \`ln\` in the environment now pays the delay and pollutes the hit count)"
  elif [ "$e_p" -gt 2 ]; then
    no "RL-SHIM-a an option-bearing \`ln\` takes the no-delay path (4 calls took ${e_p}s with W1=${RL_W_MS}ms armed)"
  else
    ok "RL-SHIM-a an option-bearing \`ln\` execs the real binary immediately under an armed shim: 4 calls in ${e_p}s, 0 hits"
  fi

  # RL-SHIM-b -- a bare two-argument `ln` that SUCCEEDS delays, and delays AFTER the link exists. The
  # mid-flight assertion is the one that changed meaning with the fix and it is the reason this row
  # is worth keeping: what is held open now is the lock PRESENT AND ALREADY CARRYING ITS OWNER.
  : > "$hl"; printf '%s\n' 4242 > "$u/lsrc"
  rl_unit "$RL_W_MS" 0 ln "$u/lsrc" "$u/bare" & rl_mkpid=$!
  rl_await_hit W1
  rl_hit_seen="$(rl_hits W1)"
  rl_mid_dir=0; [ -f "$u/bare" ] && [ "$(cat "$u/bare" 2>/dev/null)" = 4242 ] && rl_mid_dir=1
  # Sampled a beat after the delay began, not at the instant it began: if the shim slept BEFORE
  # linking, it is finished and gone by now; if it slept after, ~500ms remain.
  sleep 0.2
  rl_mid_alive=0; kill -0 "$rl_mkpid" 2>/dev/null && rl_mid_alive=1
  wait "$rl_mkpid"; rc_b=$?
  h_b="$(rl_hits W1)"
  if [ "$rc_b" != 0 ]; then
    no "RL-SHIM-b a bare \`ln\` under an armed shim still succeeds (rc=$rc_b)"
  elif [ "$rl_hit_seen" -lt 1 ]; then
    no "RL-SHIM-b a bare \`ln\` reached the widening at all (no W1 hit within the 5s spin -- the shim is not armed, or logs nothing)"
  elif [ "$rl_mid_alive" != 1 ]; then
    no "RL-SHIM-b a bare \`ln\` is still delaying 200ms after it logged its hit -- it did not sleep (W1=${RL_W_MS}ms)"
  elif [ "$rl_mid_dir" != 1 ]; then
    no "RL-SHIM-b the delay lands AFTER the link exists WITH ITS CONTENT (mid-flight the link was absent or empty -- the shim sleeps too early, so the state it holds open is not the published lock)"
  elif [ "$h_b" != 1 ]; then
    no "RL-SHIM-b a bare \`ln\` logs exactly one W1 hit (logged $h_b)"
  else
    ok "RL-SHIM-b a bare \`ln\` delays AFTER success -- mid-flight the lock already exists AND already carries its owner pid, which is the state the old \`mkdir\` acquire could not produce -- and logs one W1 hit"
  fi

  # RL-SHIM-c -- a bare `ln` that FAILS delays not at all and propagates its non-zero rc. EEXIST IS the
  # exclusion, so this is the loser of the lock race, and taxing it would slow the very process whose
  # speed the window needs. Swallowing the failure would be worse than slow: every caller would
  # believe it holds the lock.
  : > "$hl"; SECONDS=0; echo x > "$u/csrc"; echo y > "$u/ctaken"
  rl_unit "$RL_W_MS" 0 ln "$u/csrc" "$u/ctaken" 2>/dev/null; rc_f=$?
  rl_unit "$RL_W_MS" 0 ln "$u/csrc" "$u/ctaken" 2>/dev/null
  rl_unit "$RL_W_MS" 0 ln "$u/csrc" "$u/ctaken" 2>/dev/null
  rl_unit "$RL_W_MS" 0 ln "$u/csrc" "$u/ctaken" 2>/dev/null
  e_f=$SECONDS; h_f="$(rl_hits W1)"
  if [ "$rc_f" = 0 ]; then
    no "RL-SHIM-c an \`ln\` onto an existing name propagates its non-zero rc (got 0 -- the shim swallowed EEXIST, which is the exclusion itself)"
  elif [ "$h_f" != 0 ]; then
    no "RL-SHIM-c a failing bare \`ln\` logs no hit ($h_f logged -- the widening fired on a call that published nothing)"
  elif [ "$e_f" -gt 2 ]; then
    no "RL-SHIM-c a failing bare \`ln\` does not delay (4 calls took ${e_f}s)"
  elif [ "$(cat "$u/ctaken" 2>/dev/null)" != y ]; then
    no "RL-SHIM-c a failing bare \`ln\` left the existing name UNCHANGED (it was clobbered -- the shim is behaving like \`ln -f\`, which the acquire must never do)"
  else
    ok "RL-SHIM-c a failing bare \`ln\` propagates rc=$rc_f, does not delay (4 calls in ${e_f}s), logs nothing, and leaves the taken name unclobbered"
  fi

  # RL-SHIM-d -- `mv` delays BEFORE the rename. Mid-flight the source must still be there and the
  # destination must not: that is the whole point of widening W2, and asserting only that the rename
  # eventually happened would be satisfied by a shim that slept afterwards.
  : > "$hl"; echo x > "$u/src"
  rl_unit 0 "$RL_W_MS" mv "$u/src" "$u/dst" & rl_mvpid=$!
  rl_await_hit W2
  rl_hit_seen_m="$(rl_hits W2)"
  rl_mid_src=0; [ -e "$u/src" ] && rl_mid_src=1
  rl_mid_dst=0; [ -e "$u/dst" ] && rl_mid_dst=1
  wait "$rl_mvpid"; rc_m=$?
  h_m="$(rl_hits W2)"
  if [ "$rc_m" != 0 ]; then
    no "RL-SHIM-d \`mv\` under an armed shim still renames (rc=$rc_m)"
  elif [ "$rl_hit_seen_m" -lt 1 ]; then
    no "RL-SHIM-d \`mv\` reached the widening at all (no W2 hit within the 5s spin -- the shim is not armed, or logs nothing)"
  elif [ "$rl_mid_src" != 1 ] || [ "$rl_mid_dst" != 0 ]; then
    no "RL-SHIM-d the delay lands BEFORE the rename (mid-flight src=$rl_mid_src dst=$rl_mid_dst -- the shim slept after renaming, which widens nothing)"
  elif [ ! -e "$u/dst" ] || [ -e "$u/src" ]; then
    no "RL-SHIM-d the rename completes after the delay (src present=$([ -e "$u/src" ] && echo 1 || echo 0) dst present=$([ -e "$u/dst" ] && echo 1 || echo 0))"
  elif [ "$h_m" != 1 ]; then
    no "RL-SHIM-d \`mv\` logs exactly one W2 hit (logged $h_m)"
  else
    ok "RL-SHIM-d \`mv\` delays BEFORE renaming -- mid-flight the source is still in place and the destination does not exist -- then completes the rename and logs one W2 hit"
  fi

  # RL-SHIM-e -- THE CONTROL IS THE SAME CODE PATH WITH THE KNOBS OFF. Not a second implementation, so it
  # cannot drift from the widened run. Unset is tested alongside 0: a future refactor that treated
  # "unset" as "armed with an empty value" would widen every unrelated call in the suite.
  : > "$hl"; echo x > "$u/src2"; echo z > "$u/osrc"; SECONDS=0
  rl_unit 0 0 ln "$u/osrc" "$u/off1"; rc_o=$?
  rl_unit 0 0 mv "$u/src2" "$u/dst2"
  # `-u` BEFORE the assignments. `env` stops parsing options at the first `name=value`, so
  # `env PATH=... -u FOO ln a b` runs a command literally named `-u` -- measured here, as a red.
  env -u PLC_RL_W1_MS -u PLC_RL_W2_MS PATH="$RL_PATH" PLC_RL_HITLOG="$hl" ln "$u/osrc" "$u/off2"
  env -u PLC_RL_W1_MS -u PLC_RL_W2_MS PATH="$RL_PATH" PLC_RL_HITLOG="$hl" ln "$u/osrc" "$u/off3"
  # THE `mv` SHIM GETS THE GENUINELY-UNSET ARM TOO. Both wrappers default an absent knob to 0, and
  # only the W1 wrapper was ever driven with the variable actually unset -- so the stated hazard (a
  # refactor treating unset as armed-with-an-empty-value would widen every unrelated call in the
  # suite) was covered for one of the two.
  echo x > "$u/src3"
  env -u PLC_RL_W1_MS -u PLC_RL_W2_MS PATH="$RL_PATH" PLC_RL_HITLOG="$hl" mv "$u/src3" "$u/dst3"
  e_o=$SECONDS; h_o="$(rl_hits '.')"
  if [ "$rc_o" != 0 ] || [ ! -f "$u/off1" ] || [ ! -f "$u/off2" ] || [ ! -f "$u/off3" ] || [ ! -e "$u/dst2" ] || [ ! -e "$u/dst3" ]; then
    no "RL-SHIM-e with the knobs off the shims still do the real work (rc=$rc_o off1=$([ -f "$u/off1" ] && echo 1 || echo 0) off2=$([ -f "$u/off2" ] && echo 1 || echo 0) off3=$([ -f "$u/off3" ] && echo 1 || echo 0) renamed=$([ -e "$u/dst2" ] && echo 1 || echo 0) renamed-unset=$([ -e "$u/dst3" ] && echo 1 || echo 0))"
  elif [ "$h_o" != 0 ]; then
    no "RL-SHIM-e knobs off logs nothing ($h_o hits logged -- an unset knob is being read as armed, so the control is not the same code path unwidened)"
  elif [ "$e_o" -gt 2 ]; then
    no "RL-SHIM-e knobs off = unwidened (4 calls took ${e_o}s -- something is still sleeping)"
  else
    ok "RL-SHIM-e knobs unset or 0 is the same code path unwidened, for BOTH wrappers: ${e_o}s, 0 hits, and the real ln/mv work still done under an explicit 0 and under a genuinely unset knob"
  fi
fi

# --- the preconditions, and why neither may ever be a skip ---------------
# BOTH ARE HARD FAILURES OF THE ROW. Never a skip, and -- stated rather than left as an inference --
# NEVER a fall back to running the batch unwidened "so the suite stays green". An unwidened run
# reports green and that green reads as "the guard holds", which is the single outcome this whole
# bench exists to prevent. The W1-alone control is the proof it is not hypothetical: 102 passed /
# 0 failed with the invariant already broken.
#
# P1 -- THE SHIMS ARE ACTUALLY REACHABLE, and it verifies the SAME `RL_PATH` string the batch
# runs under. If this check assembled its own path, it could pass while the batch ran unwidened.
rl_resolves() { PATH="$1" /bin/bash -c "command -v $2" 2>/dev/null || true; }
rl_r_ln="$(rl_resolves "$RL_PATH" ln)"
rl_r_mv="$(rl_resolves "$RL_PATH" mv)"
RL_P1_OK=1
if [ "$rl_r_ln" != "$RL_SHIMDIR/ln" ] || [ "$rl_r_mv" != "$RL_SHIMDIR/mv" ]; then
  RL_P1_OK=0
  no "RL-P1 under the widened PATH, bare \`ln\` and \`mv\` resolve to the shims (ln->${rl_r_ln:-<unresolved>} mv->${rl_r_mv:-<unresolved>}, wanted $RL_SHIMDIR/) -- the batch would run UNWIDENED and report green"
else
  ok "RL-P1 under the widened PATH both bare command names resolve to the shim files, and it is the same PATH string the batch runs under"
fi

# P2 -- THE HOOK STILL INVOKES BARE COMMAND NAMES. This is what closes the shim's one named
# weakness: a future hardening pass changing `ln` to `command ln`, or to an absolute path,
# would otherwise disarm the widening WITH NO TEST FAILURE MARKING THE MOMENT. With P2 it reds at
# the commit that introduces it.
#
# A COUNT, NOT A PRESENCE TEST. `grep -q` cannot tell one match from two, and a DUPLICATED anchor
# must fail as loudly as a vanished one -- a second copy of the line means the widening now fires
# somewhere nobody reasoned about. `grep -q` is simply the wrong tool for a count.
RL_W1_ANCHOR='&& ln "$_cft" "$_cfl" 2>/dev/null; then'
RL_W2_ANCHOR='&& mv "$MARKER" "$_cfaside" 2>/dev/null; then'
rl_anchors() {   # $1 = file ; prints "<w1count> <w2count>"
  local a b
  a="$(grep -c -F "$RL_W1_ANCHOR" "$1" 2>/dev/null || true)"
  b="$(grep -c -F "$RL_W2_ANCHOR" "$1" 2>/dev/null || true)"
  printf '%s %s' "${a:-0}" "${b:-0}"
}
# THE VERDICT LIVES IN ONE PREDICATE, and the meta row below asserts THE PREDICATE rather than the
# raw counts. The first draft asserted the counts, and it left a hole a mutant walks straight
# through: relax this row's comparison to `grep -q` semantics -- red only on zero -- and the counting
# function still returns the right numbers, so a counts-only meta row stays green while the
# duplicate-anchor half of P2 has silently stopped existing.
rl_p2_ok() { [ "$(rl_anchors "$1")" = "1 1" ]; }
rl_p2="$(rl_anchors "$IMPL")"
if ! rl_p2_ok "$IMPL"; then
  # THE FAILURE MESSAGE NAMES THE TRIPWIRE, because an edit to this hook's COMMENTS is the most
  # likely way to trip it: the natural way to document a window
  # is to quote its anchor verbatim -- which takes a count from 1 to 2 and hard-fails P2 on
  # legitimate documentation. Whoever trips it should be told the cause, not left hunting a
  # disarmed shim that is not disarmed.
  no "RL-P2 the shipped hook still invokes bare \`ln\`/\`mv\` (anchor counts W1 W2 = $rl_p2, wanted 1 1). A count of 0 means the call was hardened to \`command ln\` or an absolute path and the widening is silently disarmed. A count above 1 usually means a COMMENT now quotes the anchor verbatim -- that is this tripwire, not a disarmed shim."
else
  ok "RL-P2 each widening anchor occurs exactly once in the shipped hook, so neither window can be disarmed without this row going red"
fi

# RL-P2-meta -- P2 IS A GUARD, SO IT GETS PROOF THAT IT CAN FAIL.
# Driven against throwaway copies rather than argued for in prose: a declaration wider than the
# mechanism behind it is a recurring defect, and "a future hardening pass reds here" is
# exactly such a declaration until something demonstrates it.
rl_p2meta="$(mktemp -d "$WORK/rlp2.XXXXXX")"
# (a) DISARMED: the hardening this precondition exists to catch.
sed 's/&& ln "\$_cft" "\$_cfl" 2>\/dev\/null; then/\&\& command ln "$_cft" "$_cfl" 2>\/dev\/null; then/' \
  "$IMPL" > "$rl_p2meta/disarmed.sh"
# (b) DUPLICATED: a comment quoting the W2 anchor verbatim -- the likely shape of a comment edit.
{ printf '# %s\n' "$RL_W2_ANCHOR"; cat "$IMPL"; } > "$rl_p2meta/duplicated.sh"
rl_p2_dis="$(rl_anchors "$rl_p2meta/disarmed.sh")"
rl_p2_dup="$(rl_anchors "$rl_p2meta/duplicated.sh")"
# A POSITIVE CONTROL FIRST. Without it, a predicate that answered "no" to everything would satisfy
# both negative halves below and look like a thorough guard.
if ! rl_p2_ok "$IMPL"; then
  no "RL-P2-meta the predicate rejects the UNMODIFIED hook ($rl_p2) -- the two negative cases below prove nothing"
elif rl_p2_ok "$rl_p2meta/disarmed.sh"; then
  no "RL-P2-meta a hook whose \`ln\` was hardened to \`command ln\` still passes P2 (counts $rl_p2_dis) -- P2 cannot see the disarming it exists to catch"
elif rl_p2_ok "$rl_p2meta/duplicated.sh"; then
  no "RL-P2-meta a hook carrying a second copy of the W2 anchor still passes P2 (counts $rl_p2_dup) -- the row has been relaxed to \`grep -q\` semantics and its duplicate half no longer exists"
else
  ok "RL-P2-meta P2's own predicate is demonstrated to accept the shipped hook ($rl_p2) and reject both directions: hardened to \`command ln\` counts $rl_p2_dis, a comment quoting the anchor counts $rl_p2_dup"
fi

# --- the widened batch, measured per configuration -----------------------
# Same batch machinery and the same START BARRIER as CF-AC5b above: children spin on a `.go`
# release file rather than being staggered by however long each fork took. Never a `sleep`-then-go,
# which is banned for fixtures here because a same-second race turned out to be a coin flip.
#
# THE KNOBS RIDE THE LITERAL `env` LINE, never an export. A widened PATH exported process-wide
# reaches every other hook call in this suite, inflating its runtime and perturbing unrelated rows.
RL_CW=24        # See the calibration note below: WIDTH is the first lever and the window is the
RL_MS=150       # second, and they are not interchangeable. Declared ceiling: width 24, 300ms.
                  # Past that the suite cost stops being worth a rate, and the row takes the
                  # pre-declared >=1/N fallback -- with the measured rate written into its
                  # own message, which is what the fallback branch below does.
RL_CR_BOTH=6
RL_CR_SOLO=4
rl_batch() {    # $1 = W1_MS  $2 = W2_MS  $3 = rounds  [$4 = on|off hit log] ; prints "bad good short side worst hits"
  local w1="$1" w2="$2" rounds="$3" logging="${4:-on}"
  # `rlist`, NOT `rounds`. The accumulator was first written as `rounds`, which is this function's
  # own third PARAMETER (the batch count) -- the second `local` re-declared it empty, so the loop
  # bound was destroyed and the batch silently ran a different number of rounds than its own
  # denominator claimed. Caught only because the per-round listing printed two entries beside a
  # denominator of six: the listing disagreed with the summary, which is the entire argument for
  # printing a listing instead of two integers.
  local bd rd ev bad=0 good=0 short=0 side=0 worst=0 hits=0 r i allows seen hl="" hlarg="" rlist=""
  bd="$(sandbox)"; usage_line 160000 > "$bd/t.jsonl"; echo current > "$bd/RESUME.md"
  ev="$(ev_for "$bd")"; rd="$(mktemp -d "$WORK/rlrc.XXXXXX")"
  # THE `off` ARM STILL CREATES THE FILE AND STILL DOES NOT EXPORT THE VARIABLE, deliberately: the
  # calibration below compares an arm that logs against an arm that does not, and nothing used to
  # assert the second one actually differed. Measured as a surviving mutant: making the `off` arm
  # log exactly like the `on` arm left the calibration row GREEN at "delta 0", because it read the
  # rates and never its own independent variable. The file exists so its emptiness is checkable.
  hl="$bd/hits.log"; : > "$hl"
  if [ "$logging" = on ]; then hlarg="PLC_RL_HITLOG=$hl"; fi
  for r in $(seq "$rounds"); do
    rm -rf "$bd/plc-context-floor"; rm -f "$rd"/rc.* "$rd/.go"
    mkdir -p "$bd/plc-context-floor/s.marker"; echo x > "$bd/plc-context-floor/s.marker/inner"
    for i in $(seq "$RL_CW"); do
      ( while [ ! -e "$rd/.go" ]; do :; done
        printf '%s' "$ev" | env -u PLC_CONTEXT_FLOOR -u PLC_CONTEXT_FLOOR_PCT -u PLC_CONTEXT_FLOOR_STEP \
          -u PLC_CONTEXT_WINDOW -u PLC_RESUME_PATH TMPDIR="$bd" LC_ALL=C \
          PATH="$RL_PATH" PLC_RL_W1_MS="$w1" PLC_RL_W2_MS="$w2" ${hlarg:+"$hlarg"} \
          ${CT_TIMEOUT:+timeout 40} /bin/bash "$IMPL" >/dev/null 2>&1
        printf '%s' "$?" > "$rd/rc.$i" ) &
    done
    sleep 0.05; : > "$rd/.go"
    wait
    allows=0; seen=0
    for i in $(seq "$RL_CW"); do
      [ -f "$rd/rc.$i" ] || continue
      seen=$((seen+1)); [ "$(cat "$rd/rc.$i")" = 0 ] && allows=$((allows+1))
    done
    [ "$seen" = "$RL_CW" ] || short=$((short+1))
    [ "$allows" -gt "$worst" ] && worst="$allows"
    [ "$allows" -gt 1 ] && bad=$((bad+1))
    [ "$allows" = 1 ] && good=$((good+1))
    [ -e "$bd/plc-context-floor/s.wedged" ] && side=$((side+1))
    rlist="$rlist$allows,"
  done
  rm -f "$rd/.go"
  hits="$(grep -c . "$hl" 2>/dev/null || true)"; hits="${hits:-0}"
  # FIELD 7 IS THE PER-ROUND LISTING. Two integers were exactly enough to know something happened
  # and nowhere near enough to know what -- the lesson this file already paid for with the AC5b
  # forensic collector. A short run should arrive as `1,3,3,2,4,2` and not as `5 of 6`.
  printf '%s %s %s %s %s %s %s' "$bad" "$good" "$short" "$side" "$worst" "$hits" "${rlist%,}"
  rm -rf "$rd"
}
rl_f() { printf '%s' "$1" | cut -d' ' -f"$2"; }   # field of a rl_batch result

# --- WHERE THIS BENCH RUNS, decided by a measurement rather than by taste ----------------
#
# MEASURED, three runs each side on a loaded many-core development machine: the suite goes from
# 74/75/75s to 102/102/99s. **+27s against a +15s budget**, so the row does not stay in the
# default local suite.
#
# BOTH FALLBACKS FIRE AND THEY COMPOSE, in the order the design fixed in advance: correctness
# outranks cost. The 100% reproduction rate is KEPT (width 24, 150ms, 6 of 6) and the row moves to
# a conditional shape instead. A deterministic row that runs only where it is affordable
# beats a probabilistic row that runs everywhere, and the +15s budget was the weaker preference.
#
# THE SKIP IS PRINTED, NEVER SILENT. A guard that is invisible when it does not run is a guard
# nobody notices has stopped running, which is the silent-degrade class.
# Every row the skip covers says so by name, and says how to run it.
#
# `PLC_RL_BENCH` = on | off | auto (default). `auto` runs it in CI, and locally whenever the
# working tree's own hooks have changed against the merge-base -- which is exactly when a bench
# over those hooks is worth 27 seconds.

# CF-GAP -- AN ARM THAT HAS STOPPED MEASURING MUST SAY SO, NOT REPORT ZERO.
#
# `RL-P2` above asserts that each widening ANCHOR still exists. That is only half of what makes an
# arm meaningful. The shim widens a WINDOW, and a window is a gap BETWEEN TWO POINTS -- for W1,
# between taking the lock and stamping it with an owner; for W2, between the re-stat that establishes
# "still corrupt" and the rename that acts on it. Delete the second point and the anchor is still
# there, the shim still sleeps, the arm still runs, and it reports ZERO. Which reads as "the guard
# holds".
#
# THIS IS THE FAILURE MODE AN ATOMIC ACQUIRE HITS. The atomic acquire
# merges "take the lock" and "record the owner" into one act -- which is precisely the deletion of
# W1's second point. Without this row, the W1 arm would silently become a sleep that measures
# nothing, and the number it prints would still be read as evidence. A reproducer that stops
# reproducing BECAUSE YOU FIXED HALF OF WHAT IT WATCHED is the thing that must be loud.
#
# WHAT IT DOES NOT CLAIM, said plainly. This checks that the two points bounding each window still
# exist and are still in order with something between them. It does NOT check that the gap is still
# WIDE, still RACY, or still reachable -- those are not properties any grep can see. A shrinking gap
# (which the W2 re-test deliberately produces) stays green here on purpose, and the row says so.
CF_GAP_W1_OPEN='> "$_cft" 2>/dev/null'
CF_GAP_W1_CLOSE="$RL_W1_ANCHOR"
CF_GAP_W2_OPEN='if [ ! -e "$MARKER" ] || [ -L "$MARKER" ] || [ -f "$MARKER" ]; then'
CF_GAP_W2_CLOSE="$RL_W2_ANCHOR"
# ONE PREDICATE, AND THE META HALF ASSERTS THE PREDICATE. Re-deriving "is there still a gap" at the
# call site is how a guard and its proof drift apart, which `RL-P2` already paid for once.
cf_gap_span() {   # $1 = file  $2 = opening literal  $3 = closing literal ; prints lines strictly between, or -1
  local o c oh ch
  # SAME CORRECTION AS THE ROW BELOW, AND THE SAME DEFECT APPLIED HERE TOO: with first-match
  # resolution, reverting the acquire to its pre-fix two-step form and adding one comment quoting the
  # removed publish anchor left this reporting a healthy span on a structurally regressed hook.
  oh="$(grep -cF -- "$2" "$1" 2>/dev/null || true)"; ch="$(grep -cF -- "$3" "$1" 2>/dev/null || true)"
  if [ "${oh:-0}" != 1 ] || [ "${ch:-0}" != 1 ]; then printf '%s' -1; return; fi
  o="$(grep -nF -- "$2" "$1" 2>/dev/null | cut -d: -f1)"
  c="$(grep -nF -- "$3" "$1" 2>/dev/null | cut -d: -f1)"
  # A MISSING POINT IS -1, NEVER 0. Zero means "they are adjacent", which is a real and different
  # state; collapsing the two would let a deleted anchor read as a merely-narrow gap.
  if [ -z "$o" ] || [ -z "$c" ]; then printf '%s' -1; return; fi
  if [ "$c" -le "$o" ]; then printf '%s' -1; return; fi
  printf '%s' "$(( c - o - 1 ))"
}
cf_gap_ok() { [ "$(cf_gap_span "$1" "$2" "$3")" -ge 0 ]; }
cf_g_w1="$(cf_gap_span "$IMPL" "$CF_GAP_W1_OPEN" "$CF_GAP_W1_CLOSE")"
cf_g_w2="$(cf_gap_span "$IMPL" "$CF_GAP_W2_OPEN" "$CF_GAP_W2_CLOSE")"
# THE POSITIVE CONTROL RUNS FIRST, against throwaway copies with each window's closing point
# deleted. Without it a predicate that answered "gap present" to everything would satisfy both arms
# below while covering nothing -- the same hole `RL-P2-meta` was written to close one row up.
cf_gapdir="$(mktemp -d "$WORK/cfgap.XXXXXX")"
grep -vF -- "$CF_GAP_W1_CLOSE" "$IMPL" > "$cf_gapdir/no-w1.sh"
grep -vF -- "$CF_GAP_W2_CLOSE" "$IMPL" > "$cf_gapdir/no-w2.sh"
cf_gap_c1="$(cf_gap_span "$cf_gapdir/no-w1.sh" "$CF_GAP_W1_OPEN" "$CF_GAP_W1_CLOSE")"
cf_gap_c2="$(cf_gap_span "$cf_gapdir/no-w2.sh" "$CF_GAP_W2_OPEN" "$CF_GAP_W2_CLOSE")"
if cf_gap_ok "$cf_gapdir/no-w1.sh" "$CF_GAP_W1_OPEN" "$CF_GAP_W1_CLOSE" \
  || cf_gap_ok "$cf_gapdir/no-w2.sh" "$CF_GAP_W2_OPEN" "$CF_GAP_W2_CLOSE"; then
  no "CF-GAP the gap predicate still reports a gap after the window's closing point was deleted (W1 copy $cf_gap_c1, W2 copy $cf_gap_c2) -- it cannot see the disappearance it exists to catch, so the two arms below prove nothing"
elif [ "$cf_g_w1" -lt 0 ]; then
  no "CF-GAP the W1 arm no longer measures anything -- the lock is taken but the owner stamp it was widening against is gone from the shipped hook. RE-POINT THIS ARM OR DELETE IT DELIBERATELY. Do not let it keep sleeping and reporting zero: a zero from an arm that is no longer inserted into a gap is indistinguishable from a zero that means the guard holds, and that is the whole reason this row exists."
elif [ "$cf_g_w2" -lt 0 ]; then
  no "CF-GAP the W2 arm no longer measures anything -- the re-stat and the rename it was widening between are no longer both present and in order in the shipped hook. RE-POINT THIS ARM OR DELETE IT DELIBERATELY, rather than leaving a sleep that reports zero."
else
  ok "CF-GAP both widened windows still have a gap to insert into (W1 spans $cf_g_w1 line(s), W2 spans $cf_g_w2), and the predicate is demonstrated to report -1 on copies with each closing point deleted ($cf_gap_c1 / $cf_gap_c2) -- presence and order only, never that the gap is still wide or still racy"
fi


# CF-W3-FORGE -- THE OWNERSHIP-CHECKED RELEASE, AND AN HONEST
# ANSWER TO WHETHER ITS NOT-OURS BRANCH CAN BE REACHED AT ALL.
#
# THE ANSWER IS: ONLY SYNTHETICALLY, AND THIS ROW IS LABELLED SYNTHETIC FOR THAT REASON. The question
# is asked because this file RETRACTED the phrase "unreachable by
# construction" once already, about this same stanza, when its premise turned out to be false. So the
# claim is not repeated on trust. What is measured here is that the branch DOES WHAT IT SAYS WHEN IT
# IS REACHED. What is NOT claimed is that any real race reaches it: the acquire publishes content and
# name together, so a rival cannot obtain this lock's name, and cannot rewrite its content without
# already being a process that has no business in the state directory.
#
# THE FORGE: hold the hook inside the RENAME with the W2 widening, then overwrite the lock's content
# with a foreign pid from outside. At release the hook reads a pid that is not its own.
#
# IT USED TO FORGE INSIDE THE PUBLISH, AND THE FIX FOR THE `ln`-ONTO-A-DIRECTORY DEFECT MADE THAT
# UNREACHABLE -- a strengthening, recorded rather than worked around. The acquire now carries a
# POST-CONDITION: after a successful `ln` it requires a regular file at the lock path whose content is
# its own pid. A forge landing inside the publish window is therefore caught at ACQUIRE time, the
# caller correctly concludes it holds nothing, and the release never runs -- so the row went red for
# a reason that is better behaviour, not worse. The forge moved one window later, past the
# post-condition, which is the only place a foreign owner can still be observed at release. Two things
# must then be true, and the SECOND is the criterion -- the first is only the tripwire proving the
# forge landed:
#   1. it reports the steal (`STOLEN self=... found=...`), and
#   2. IT LEAVES THE LOCK ALONE. Under the old unconditional removal the first
#      repairer deleted the second one's lock on its way out, which is why the aside nodes in a bad
#      round were never bounded at two.
#
# A MANUFACTURED PASS MUST NOT READ AS COVERAGE, so the row says "synthetic" in its own message rather
# than leaving a green row to imply
# the branch is exercised by ordinary running.
w3d="$(sandbox)"; usage_line 160000 > "$w3d/t.jsonl"
echo current > "$w3d/RESUME.md"
w3ev="$(ev_for "$w3d")"
mkdir -p "$w3d/plc-context-floor/s.marker"; echo x > "$w3d/plc-context-floor/s.marker/inner"
w3log="$WORK/w3.hits"; : > "$w3log"; w3err="$WORK/w3.err"; : > "$w3err"
( printf '%s' "$w3ev" | env -u PLC_CONTEXT_FLOOR -u PLC_CONTEXT_FLOOR_PCT -u PLC_CONTEXT_FLOOR_STEP \
    -u PLC_CONTEXT_WINDOW -u PLC_RESUME_PATH \
    PATH="$RL_PATH" PLC_RL_W1_MS=0 PLC_RL_W2_MS=600 PLC_RL_HITLOG="$w3log" \
    PLC_CF_ASSERT_OWNER=1 TMPDIR="$w3d" LC_ALL=C \
    ${CT_TIMEOUT:+timeout 20} /bin/bash "$IMPL" >/dev/null 2>"$w3err" ) &
w3pid=$!
w3forged=0; w3i=0
while [ "$w3i" -lt 150 ]; do
  if grep -q ' W2$' "$w3log" 2>/dev/null; then
    printf '999999\n' > "$w3d/plc-context-floor/s.repair" 2>/dev/null || true
    w3forged=1; break
  fi
  w3i=$((w3i+1)); sleep 0.01
done
wait "$w3pid" 2>/dev/null || true
w3left=0; [ -f "$w3d/plc-context-floor/s.repair" ] && w3left=1
w3content="$(cat "$w3d/plc-context-floor/s.repair" 2>/dev/null || true)"
if [ "$w3forged" != 1 ]; then
  no "CF-W3-FORGE the forge never landed -- no \`W2\` line appeared in the shim's hit log within 1.5s, so the hook never reached the rename and this row measured NOTHING (it must not report green for that)"
elif ! ac12_stole "$w3err"; then
  no "CF-W3-FORGE the release did not report a foreign owner after the lock's content was forged mid-flight -- either the release stopped reading the owner, or it reads it from the wrong place (the lock is a regular file; reading \`\$_cflock/pid\` on one returns empty and would silently compare against nothing)"
elif [ "$w3left" != 1 ] || [ "$w3content" != 999999 ]; then
  no "CF-W3-FORGE the release REMOVED a lock this process does not own (present=$w3left content=${w3content:-<gone>}, expected the forged 999999 untouched) -- that is W3, and under the old unconditional removal it is what let a third caller in behind the second"
else
  ok "CF-W3-FORGE with the lock's content forged mid-flight, the release reports the steal and LEAVES THE LOCK ALONE (content still $w3content). SYNTHETIC BY CONSTRUCTION -- no real race reaches this branch once the acquire is atomic, and this row is evidence the branch behaves, never evidence that it is exercised"
fi

# CF-RETEST -- THE NODE TYPE IS RE-TESTED BETWEEN THE SCAN AND THE RENAME.
#
# A STATIC ORDER ASSERTION, AND THE REASON IT IS STATIC IS THE FINDING, NOT AN EXCUSE. The window
# this re-test closes runs from the re-stat under the lock to the rename, and the only thing inside
# it is the candidate-slot scan -- pure shell builtins, no external command, therefore no place any
# PATH shim can insert a delay. `CF-W2-INJECT` below CANNOT reach it: that arm's rendezvous is the
# `mv` wrapper's log line, which fires AFTER this re-test has already run. So there is no
# behavioural falsifier for this line, and rather than let a green behavioural row imply one exists,
# the coverage is what it is -- presence and ORDER -- and the gap is written down here.
#
# ORDER IS THE WHOLE ASSERTION. The re-test placed BEFORE the scan re-opens exactly the gap it is
# meant to close, and a reviewer moving it "somewhere tidier" would produce a hook that still
# contains every one of these three lines. Presence alone would stay green through that edit.
CF_RT_SCAN='_cfcand="$MDIR/$SID.corrupt.$$.$_cfn"'
CF_RT_TEST='       && [ -e "$MARKER" ] && [ ! -L "$MARKER" ] && [ ! -f "$MARKER" ] \'
CF_RT_MV="$RL_W2_ANCHOR"
# EXACTLY ONE OCCURRENCE, NOT THE FIRST ONE. `head -1` was a CRITICAL defect, and the mechanism
# is this: a decoy comment quoting the scan literal near the top of the file resolves the "scan" line
# to the decoy, so the order test compares against a line that is not the scan, and a hook whose
# re-test had been hoisted out of the window entirely reported order-OK -- through the whole suite,
# byte-identical to a clean run. `RL-P2` one screen away counts occurrences for precisely
# this reason; the pattern was not carried to its two newer siblings. An empty answer here means
# absent OR ambiguous, and both must fail.
cf_rt_line() {
  local hits
  hits="$(grep -cF -- "$2" "$1" 2>/dev/null || true)"
  [ "${hits:-0}" = 1 ] || { printf ''; return; }
  grep -nF -- "$2" "$1" 2>/dev/null | cut -d: -f1
}
cf_rt_ok() {   # $1 = file ; true when scan < re-test < mv, all present
  local s t m
  s="$(cf_rt_line "$1" "$CF_RT_SCAN")"; t="$(cf_rt_line "$1" "$CF_RT_TEST")"; m="$(cf_rt_line "$1" "$CF_RT_MV")"
  [ -n "$s" ] && [ -n "$t" ] && [ -n "$m" ] && [ "$t" -gt "$s" ] && [ "$m" -gt "$t" ]
}
cf_rtdir="$(mktemp -d "$WORK/cfrt.XXXXXX")"
# TWO MUTANTS, AND THE SECOND IS THE ONE PRESENCE-ONLY WOULD MISS: deleted, and merely MOVED to
# before the scan. Both must be rejected or this row is not asserting order at all.
grep -vF -- "$CF_RT_TEST" "$IMPL" > "$cf_rtdir/deleted.sh"
awk -v t="$CF_RT_TEST" -v s="$CF_RT_SCAN" '
  index($0,t){next}
  index($0,s) && !done{print t; done=1}
  {print}' "$IMPL" > "$cf_rtdir/moved.sh"
if cf_rt_ok "$cf_rtdir/deleted.sh" || cf_rt_ok "$cf_rtdir/moved.sh"; then
  no "CF-RETEST the order predicate accepts a hook with the re-test deleted or hoisted above the scan -- it is asserting presence, not order, so the row below proves nothing"
elif ! cf_rt_ok "$IMPL"; then
  no "CF-RETEST the shipped hook does not re-test the node type BETWEEN the candidate scan and the rename (scan=$(cf_rt_line "$IMPL" "$CF_RT_SCAN") re-test=$(cf_rt_line "$IMPL" "$CF_RT_TEST") mv=$(cf_rt_line "$IMPL" "$CF_RT_MV")). Placed before the scan it re-opens the gap it exists to close; absent, the rename acts on whatever the path became while the scan was running."
else
  ok "CF-RETEST the node type is re-tested between the candidate scan and the rename (lines $(cf_rt_line "$IMPL" "$CF_RT_SCAN") < $(cf_rt_line "$IMPL" "$CF_RT_TEST") < $(cf_rt_line "$IMPL" "$CF_RT_MV")), and the predicate rejects both a deleted re-test and one hoisted above the scan -- presence and ORDER only, because the window it closes contains no external command and no shim can reach it"
fi

# CF-RETEST-CLAIM -- THE COMMENT MUST NOT OVERSTATE WHAT THE RE-TEST BOUGHT.
#
# The row above asserts the re-test is THERE and in the right place. This asserts the hook does not
# claim more for it than it does. The failure being guarded is specific:
# a partial fix whose comment reads like a total one gets quoted as total by the next reader,
# and then by a PR body, and then by a backlog entry marking the defect closed.
#
# STRUCTURE, NOT A GOLDEN STRING. Three things must be present near the re-test -- that it SHRINKS
# the window, that it does NOT eliminate it, and a pointer to the mechanism that does the
# eliminating. Phrasing stays free, because pinning the sentence makes every improvement a test edit,
# which trains people to edit tests unread. What this cannot check is whether the prose is TRUE; that is the
# reviewer's, and it is stated as an exclusion rather than dressed up
# as coverage here.
cf_rtc_missing=""
cf_rtc_zone="$(awk -v s='RE-TEST THE NODE TYPE HERE' -v e='&& mv "$MARKER" "$_cfaside"' \
  'index($0,s){on=1} on{print} index($0,e){if(on) exit}' "$IMPL")"
# CASE-FOLDED, and that was measured rather than reasoned: the first pattern was `[Ss]hrink`, the
# hook's comment says `SHRINKS` in capitals, and the row went red against a comment that says exactly
# what it demands. A predicate that only accepts one casing of a free-phrasing claim is a golden
# string wearing a structure check's clothes.
cf_rtc_fold="$(printf '%s' "$cf_rtc_zone" | tr '[:upper:]' '[:lower:]')"
case "$cf_rtc_fold" in *shrink*) ;; *) cf_rtc_missing="$cf_rtc_missing <shrinks>" ;; esac
case "$cf_rtc_fold" in *"not eliminate"*) ;; *) cf_rtc_missing="$cf_rtc_missing <does-not-eliminate>" ;; esac
case "$cf_rtc_fold" in *"atomic acquire"*) ;; *) cf_rtc_missing="$cf_rtc_missing <names-the-eliminating-mechanism>" ;; esac
if [ -z "$cf_rtc_zone" ]; then
  no "CF-RETEST-CLAIM the re-test's comment zone could not be located in the shipped hook -- the check silently stopped covering anything, which is a failure and never a pass"
elif [ -n "$cf_rtc_missing" ]; then
  no "CF-RETEST-CLAIM the re-test's comment does not bound its own claim; missing:$cf_rtc_missing. A partial fix described as a total one is how a still-open window gets recorded as closed."
else
  ok "CF-RETEST-CLAIM the re-test's comment says it SHRINKS the window, says it does NOT eliminate it, and names the atomic acquire as what does -- structure checked, phrasing deliberately free, truthfulness excluded in words rather than faked"
fi

# CF-W2-INJECT -- A W2 FALSIFIER THAT DOES NOT DEPEND ON W1 BEING BROKEN.
#
# WHY THIS ROW HAS TO EXIST BEFORE THE FIX. Today the only thing that reproduces W2 is the
# both-windows-widened arm of the bench, and it reproduces W2 by going THROUGH W1: it needs a second
# repairer, and W1 is what admits one. An atomic acquire therefore DESTROYS THE ONLY W2 REPRODUCER
# IN THE SUITE. The bench's W2-only arm measures 0 of 4 for exactly that reason -- it is waiting for
# W1 to let a second process through. So between the commit that fixes W1 and the commit that fixes
# W2, W2 would be the only defect left and NOTHING would be watching it. This row is what closes
# that window, and it must be built now, while the defect is still reachable.
#
# THE INJECTION MECHANISM IS THE WHOLE TASK, AND TWO READINGS DIVERGE HARD. The
# obvious reading is self-defeating:
#
#   (a) TWO OS PROCESSES racing to the `mv`. This is exploiting W1 under another name. An atomic
#       acquire destroys the injection itself, so the arm could never red after the fix -- and the
#       fix's own required proof ("this arm still reds") would be unsatisfiable by construction.
#       REJECTED.
#   (b) HARNESS-DRIVEN, ONE REPAIRER. Widen only the scan->`mv` gap and have THE TEST replace the
#       marker from outside while the hook is held inside it -- simulating "a legitimate marker
#       arrived mid-flight", which is precisely what a second repairer does to the first. It never
#       touches the acquire, so it survives the fix unchanged. THIS IS WHAT RUNS BELOW.
#
# THE RENDEZVOUS IS THE SHIM'S OWN HIT LOG, not a sleep. The `mv` wrapper logs its line BEFORE it
# sleeps, so a `W2` line in the log is a positive signal that the hook is inside the window right
# now. Timing a swap with `sleep` instead would be the coin-flip fixture banned here after a
# same-second race turned out to be exactly that.
#
# IF THE INJECTION DOES NOT HAPPEN, THE ROW FAILS -- it never falls back to reporting green. An arm
# that quietly reports "no defect" when it never managed to inject anything is the vacuous pass this
# whole suite is built to refuse.
#
# REGISTERED IN THE NONPORT BLOCK ABOVE, whose entry names both windows in so
# many words. `scripts/invariants/ledger-contract-sync.sh` requires every xfail id to be registered,
# and this row stays RED until the residual is closed, so it must be an xfail or CI is red.
# When a fix lands this row XPASSes, an XPASS closes this suite's gate, and
# whoever fixed it is forced to flip the row live. That is the mechanism working, not a surprise.
w2d="$(sandbox)"; usage_line 160000 > "$w2d/t.jsonl"
echo current > "$w2d/RESUME.md"
w2ev="$(ev_for "$w2d")"
mkdir -p "$w2d/plc-context-floor/s.marker"; echo x > "$w2d/plc-context-floor/s.marker/inner"
w2log="$WORK/w2.hits"; : > "$w2log"
# 400ms, not the bench's 150: this window is crossed by ONE process and a shell poll loop, where the
# bench's is crossed by 24 forked children already in flight. The number buys the harness room to
# notice and act; it is not a claim about how wide the real window is.
( printf '%s' "$w2ev" | env -u PLC_CONTEXT_FLOOR -u PLC_CONTEXT_FLOOR_PCT -u PLC_CONTEXT_FLOOR_STEP \
    -u PLC_CONTEXT_WINDOW -u PLC_RESUME_PATH \
    PATH="$RL_PATH" PLC_RL_W1_MS=0 PLC_RL_W2_MS=400 PLC_RL_HITLOG="$w2log" \
    TMPDIR="$w2d" LC_ALL=C ${CT_TIMEOUT:+timeout 20} /bin/bash "$IMPL" >/dev/null 2>&1 ) &
w2pid=$!
w2swapped=0; w2i=0
while [ "$w2i" -lt 150 ]; do
  if grep -q ' W2$' "$w2log" 2>/dev/null; then
    # THE SWAP: the corrupt node this repair was entitled to move goes away, and an ordinary
    # regular marker -- the thing a finished repairer leaves behind -- takes its place. The hook is
    # asleep between its re-stat and its `mv`, and nothing rechecks in between.
    rm -rf "$w2d/plc-context-floor/s.marker" 2>/dev/null || true
    : > "$w2d/plc-context-floor/s.marker" 2>/dev/null || true
    w2swapped=1; break
  fi
  w2i=$((w2i+1)); sleep 0.01
done
wait "$w2pid" 2>/dev/null || true
# The aside nodes this call left, and their TYPE -- which is the discriminator the hook's own header
# publishes: a directory aside is the genuine corrupt node, a REGULAR-FILE aside is a legitimate
# marker that a repair moved out from under somebody.
w2reg=0; w2dir=0
for w2n in "$w2d/plc-context-floor/"*.corrupt.*; do
  [ -e "$w2n" ] || continue
  if [ -f "$w2n" ] && [ ! -L "$w2n" ]; then w2reg=$((w2reg+1)); elif [ -d "$w2n" ]; then w2dir=$((w2dir+1)); fi
done
if [ "$w2swapped" != 1 ]; then
  no "CF-W2-INJECT the injection never fired -- no \`W2\` line appeared in the shim's hit log within 1.5s, so the hook never reached the widened rename and this arm measured NOTHING (it must not report green for that)"
elif [ "$w2reg" != 0 ]; then
  xfail "CF-W2-INJECT the RESIDUAL rename window: with a legitimate regular marker swapped in after the hook's own re-test has passed and before the rename lands, the repair still renames it aside ($w2reg regular-file aside(s), $w2dir directory aside(s)) -- \`mv\` is not atomic with its own test, which the hook's comment states and this arm is the measurement of" "B9002"
else
  ok "CF-W2-INJECT the residual rename window did not fire: a legitimate marker swapped in between the re-test and the rename was NOT renamed aside ($w2reg regular-file aside(s), $w2dir directory aside(s)). READ THIS BEFORE CELEBRATING -- the residual is not closed by anything in this phase, so a green here most likely means the swap missed its window, not that \`mv\` became atomic with its own test"
fi

RL_BENCH_WHY=""
# P1 GATES THE BATCH, and this is the "fail the row hard AND STOP" half that was previously only
# half-built. The precondition recorded its `no` and then the batch ran anyway -- under a `PATH`
# P1 had just proved was not widened. The end state was still red, so no green was ever handed
# out, but "never a fall back to running unwidened" is a claim about control flow and the control
# flow contradicted it, and the reader got two reds where one would have diagnosed it.
if [ "${RL_P1_OK:-0}" != 1 ]; then
  printf '  SKIP   repair-lock bench (widened-window reproduction, control, and hit-count rows) -- P1 FAILED above: the shims are not on the widened PATH. The batch is NOT run, because running it here would run it UNWIDENED, and an unwidened green reads as "the guard holds".\n'
  RL_BENCH_RUN=0
  RL_BENCH_WHY="P1 failed"
else
case "${PLC_RL_BENCH:-auto}" in
  on)  RL_BENCH_RUN=1; RL_BENCH_WHY="PLC_RL_BENCH=on" ;;
  off) RL_BENCH_RUN=0; RL_BENCH_WHY="PLC_RL_BENCH=off" ;;
  *)
    RL_BENCH_RUN=0; RL_BENCH_WHY="not CI, and no hook change against the merge-base"
    if [ -n "${CI:-}" ]; then
      RL_BENCH_RUN=1; RL_BENCH_WHY="CI"
    elif command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
      # NO `rev:path` ARGUMENT ANYWHERE HERE. Measured: `"$SHA:$PATH"` expands with
      # everything from the colon onward dropped, and `git` then answers about the COMMIT -- a
      # baseline extraction came back as a commit object and a tree object before the truncation
      # was spotted. `--` with a separate pathspec has no such ambiguity.
      rl_mb2="$(git merge-base origin/main HEAD 2>/dev/null || true)"
      if [ -n "$rl_mb2" ] && [ -n "$(git diff --name-only "$rl_mb2" -- "$HERE" 2>/dev/null)" ]; then
        RL_BENCH_RUN=1; RL_BENCH_WHY="hooks changed against merge-base ${rl_mb2}"
      fi
    fi
    ;;
esac
fi

# CI => THE BENCH RAN. Without this the arming condition is the one piece of this bench with no
# oracle: if the `CI` detection ever breaks, every bench row silently stops running and nothing
# reds -- the same silent-disarm class P2 was built to close for the shims.
if [ -n "${CI:-}" ] && [ "$RL_BENCH_RUN" != 1 ] && [ "${PLC_RL_BENCH:-auto}" != off ]; then
  no "RL-bench-arming under CI the bench runs (it did not: $RL_BENCH_WHY) -- the arming condition has silently disarmed every criterion the bench carries"
fi

if [ "$RL_BENCH_RUN" != 1 ]; then
  printf '  SKIP   repair-lock bench (widened-window reproduction, control, and hit-count rows) -- %s. It costs ~27s; run it with PLC_RL_BENCH=on, and CI runs it on every push.\n' "$RL_BENCH_WHY"
else
printf '  repair-lock bench running -- %s\n' "$RL_BENCH_WHY"
# THE GUARDED BLOCK IS DELIBERATELY NOT RE-INDENTED. Re-indenting a hundred lines to add one
# conditional buries the actual change in whitespace, and this file's rows are read in diffs.

# REPORTED PER CONFIGURATION, NEVER AGGREGATED (AC7). One aggregate number would hide the single
# most important fact this bench establishes: which window matters.
rl_ctl="$(rl_batch 0 0 "$RL_CR_SOLO")"
rl_o1="$(rl_batch  "$RL_MS" 0 "$RL_CR_SOLO")"
rl_o2="$(rl_batch  0 "$RL_MS" "$RL_CR_SOLO")"
rl_bo="$(rl_batch  "$RL_MS" "$RL_MS" "$RL_CR_BOTH")"

# THE NUMBERS ARE HOISTED INTO PLAIN VARIABLES BEFORE ANY MESSAGE IS BUILT, and that is a
# requirement rather than a style choice. `ledger-contract-sync.sh` extracts a row's id with
# `(xfail|xpass) "[^"]*" "B[0-9]+"` -- a message carrying an embedded double quote, which every
# inline `$(rl_f "$rl_bo" 1)` does, terminates `[^"]*` early and the id is never seen. Measured
# here: three call sites, zero ids extracted. The guard CAUGHT it rather than passing vacuously,
# which is the one thing its own header promised and the reason it exists.
RL_CTL_BAD="$(rl_f "$rl_ctl" 1)"; RL_CTL_SHORT="$(rl_f "$rl_ctl" 3)"
RL_CTL_WORST="$(rl_f "$rl_ctl" 5)"; RL_CTL_HITS="$(rl_f "$rl_ctl" 6)"
RL_O1_BAD="$(rl_f "$rl_o1" 1)"; RL_O1_WORST="$(rl_f "$rl_o1" 5)"; RL_O1_HITS="$(rl_f "$rl_o1" 6)"
RL_O2_BAD="$(rl_f "$rl_o2" 1)"; RL_O2_WORST="$(rl_f "$rl_o2" 5)"; RL_O2_HITS="$(rl_f "$rl_o2" 6)"
RL_BO_BAD="$(rl_f "$rl_bo" 1)"; RL_BO_SHORT="$(rl_f "$rl_bo" 3)"
RL_BO_WORST="$(rl_f "$rl_bo" 5)"; RL_BO_HITS="$(rl_f "$rl_bo" 6)"
RL_BO_ROUNDS="$(rl_f "$rl_bo" 7)"; RL_CTL_ROUNDS="$(rl_f "$rl_ctl" 7)"

# AC5's verdict, as ONE predicate the meta row below asserts directly. Re-deriving "hits == 0" in
# two places is how a guard and its proof drift apart -- `RL-P2` already paid for that lesson once.
rl_ac5_ok() { [ "${1:-0}" != 0 ]; }

# AC2's bar, in numbers rather than in prose. See the row below for why it is not simply zero.
RL_CTL_TOL=1     # batches, out of RL_CR_SOLO
RL_SEP_MIN=50    # percentage points the widened arm must lead the control by
# THERE IS NO SEPARATE NUMERIC FLOOR. Two earlier positions were each falsified by a measurement:
#   1. "N of N -- every batch." Shipped, and it was an overclaim on arrival: the chain underneath
#      it accepted anything above zero, and an XFAIL is not a failure, so a run reproducing 1 of 6
#      printed a reassuring line and exited 0. The bench could decay to a 17%-reliable
#      probabilistic row by drift, with nothing red.
#   2. "A measured floor of 5 of 6." Replaced (1) after per-round measurement showed round 1 is
#      systematically cold: three consecutive trials, round 1 reproduced 0 of 3, rounds 2-6
#      reproduced 15 of 15. The first batch after process start has unread shim scripts and
#      unwarmed fork paths. A warm-up round excluded from the count would buy the sixth back and
#      was deliberately NOT added -- changing the fixture to improve a number is the one thing a
#      bench about self-flattery may not do.
#   3. NO FIXED FLOOR.
#      The rate IS host- and load-dependent
#      (standalone held 5 of 6 at every window from 150ms to the 300ms ceiling under load 7-17,
#      against 6 of 6 on a quieter box), so any fixed floor has to be re-tuned per host, and a
#      threshold that needs re-tuning is a threshold nobody will trust when it fires.
#
# WHAT CARRIES THE BAR INSTEAD IS THE SEPARATION FROM THE CONTROL -- not a magic number but a
# consequence. With the control at 0%, `RL_SEP_MIN=50` requires the widened arm to reproduce in
# at least half its batches. A 2-of-6 run fails it (33 - 0 = 33 < 50) for the right reason and by
# the right mechanism, and a "fix" that quietly weakened the bench to 1 of 6 fails it too. So
# "reproduces at all" is never accepted on its own -- the objection that killed position (1) -- and
# nothing here needs re-tuning per host. The rate and the per-round listing are printed either way,
# because a rate you can read beats a threshold you have to trust.
RL_CTL_PCT=$(( 100 * RL_CTL_BAD / RL_CR_SOLO ))
RL_BO_PCT=$((  100 * RL_BO_BAD  / RL_CR_BOTH ))
RL_SEP=$(( RL_BO_PCT - RL_CTL_PCT ))
RL_REPORT="$(printf '  RL-BENCH reproduction by configuration (width %s, %sms, host tier: %s cores) --\n' \
  "$RL_CW" "$RL_MS" "$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo '?')"
printf '      %-18s %s of %s batches granted more than one allow   worst=%s  hits=%s\n' \
  "unwidened control" "$RL_CTL_BAD" "$RL_CR_SOLO" "$RL_CTL_WORST" "$RL_CTL_HITS" \
  "W1 only"           "$RL_O1_BAD"  "$RL_CR_SOLO" "$RL_O1_WORST"  "$RL_O1_HITS" \
  "W2 only"           "$RL_O2_BAD"  "$RL_CR_SOLO" "$RL_O2_WORST"  "$RL_O2_HITS" \
  "W1+W2"             "$RL_BO_BAD"  "$RL_CR_BOTH" "$RL_BO_WORST"  "$RL_BO_HITS")"
printf '%s\n' "$RL_REPORT"
# AC7 IS AN ASSERTION, NOT A `printf`. A report with no predicate would let a later edit
# collapse the four lines into one summary rate, which
# is exactly what AC7 forbids, and redden nothing.
RL_CFG_LINES="$(printf '%s\n' "$RL_REPORT" | grep -cE '^      (unwidened control|W1 only|W2 only|W1\+W2) ' || true)"
if [ "${RL_CFG_LINES:-0}" != 4 ]; then
  no "RL-AC7 each widening configuration is reported on its own line (found ${RL_CFG_LINES:-0} of 4: unwidened control, W1 only, W2 only, W1+W2) -- one aggregate number would hide which window matters, which is the finding this bench most needed to establish"
else
  ok "RL-AC7 all 4 configurations report on their own lines, never aggregated, each with its own batch count, worst allow and hit count, and the host tier beside them"
fi

# THE HOST TIER IS PRINTED WITH THE RATE, DELIBERATELY. This race is hardware-tier sensitive --
# 0 of 660 on an idle many-core machine against roughly every other run on a 2-4 vCPU runner -- so a rate with
# no tier beside it is a number nobody can diagnose after a runner change.
if [ "$RL_BO_SHORT" != 0 ] || [ "$RL_CTL_SHORT" != 0 ]; then
  no "RL-BENCH every spawned call ran (widened short=$RL_BO_SHORT, control short=$RL_CTL_SHORT of their batches lost a call) -- the rates below are not measuring what they claim"
elif ! rl_ac5_ok "$RL_BO_HITS"; then
  # AC5 LIVES HERE, BESIDE THE XPASS BRANCH. Its whole point is that a
  # zero-hit run must fail as "THE BENCH DID NOT RUN", never as "the guard holds" -- and the branch
  # it has to beat is the XPASS below.
  no "RL-BENCH the widened batch reached the widening at all -- ZERO hits logged across $RL_CR_BOTH batches. The bench did not run; this is NOT evidence the guard holds."
elif [ "$RL_BO_BAD" = 0 ]; then
  # XPASS COMES FIRST, AND ITS PLACE IN THIS CHAIN IS THE WHOLE FORCING FUNCTION.
  #
  # It used to sit last, after the AC2 separation branch -- and that made it DEAD CODE, proven by
  # mutation rather than by reading: applying a one-line fix to the hook that closes W1
  # (an unstamped lock read as live), the widened arm went 6 of 6 -> 0 of 6, and the row printed
  # "the unwidened control stays well below the widened arm". The arithmetic is unconditional --
  # zero reproductions means the widened arm is at 0%, so its lead over any control is <= 0, always
  # under the 50-point minimum, so the separation branch always fires first.
  #
  # The consequence was exact: on the day someone
  # fixes the lock, the row this suite is built around could NEVER XPASS, and the person who fixed
  # it would be sent to investigate host attribution instead of being told to flip the row live.
  # `RL-AC8` was a proof about a consumer that did not exist.
  #
  # The separation check is now conditional on the widened arm having reproduced at all, because
  # attribution is only a question when there is a result to attribute.
  # FLIPPED LIVE BY THE COMMIT THAT MADE THE ACQUIRE ATOMIC, and the flip was FORCED
  # rather than remembered: this row XPASSed, an XPASS closes the suite's gate, and the commit could
  # not push until somebody came here and decided what the row means now. That is the mechanism
  # `RL-AC8` was built for, working on its first real occasion.
  #
  # WHAT IT ASSERTS NOW IS THE INVERSE OF WHAT IT ASSERTED BEFORE THE FIX. It used to be "the defect
  # reproduces, expect red". It is now "with both windows deliberately held open, the repair still
  # grants at most one allow" -- a live regression guard on the fix, and a strictly stronger claim
  # than the unwidened batch above can make, because it holds the windows open on purpose.
  #
  # MEASURED ACROSS THE FIX, same host, same run shape: 6 of 6 batches double-allowed before, 0 of 6
  # after. The other three configurations went to 0 too, and the hit counts fell from 56 to 12 for a
  # reason worth writing down rather than treating as noise -- the W1 wrapper logs only a SUCCESSFUL
  # publish, and under the atomic acquire exactly one caller per batch succeeds, where the old bare
  # `mkdir` was attempted (and logged) by every caller that reached it.
  ok "RL-BENCH under both windows deliberately widened, the repair grants at most one allow in every one of $RL_CR_BOTH batches ($RL_BO_HITS hits logged, so the bench DID run) -- measured 6 of 6 before the atomic acquire and 0 of $RL_CR_BOTH after it"
elif [ "$RL_CTL_BAD" -gt "$RL_CTL_TOL" ]; then
  # THE CONTROL IS NOT QUIET ON THIS HOST, so ATTRIBUTION DEGRADES TO A NAMED OBSERVATION rather
  # than to a red. This is not a threshold being relaxed under pressure; it is the first run on the
  # hardware tier the defect actually lives on saying something a many-core machine structurally
  # could not.
  #
  # MEASURED, GitHub runner, 2 cores: the UNWIDENED control granted more than one
  # allow in 2 of 4 batches, worst=4, with ZERO hits logged -- nothing was widened. W2 alone
  # reproduced 2 of 4 (worst=6) while W1 alone reproduced 0 of 4. The widened arm was 6 of 6,
  # worst=8, per round 5,7,8,6,7,5. On an idle many-core machine the same control is 0 of 4 almost
  # always, and 1 of 4 once under load.
  #
  # WHY THIS IS NOT A RED. The control exists to argue "the widening, not the assertion's own
  # triviality, did the work". On a host whose baseline reproduces half the time, that argument is
  # unavailable BY CONSTRUCTION -- and failing here reports nothing a reader did not already learn
  # from the printed rates, while leaving the row permanently red on the ONLY hardware where this
  # defect matters. `CF-AC5b` has gone red on that same tier with no explanation, and
  # the reflex it trains is "re-run", which is where skipping the gate starts. Adding a
  # second permanently-red row would reproduce that disease, not diagnose it.
  #
  # WHAT STILL HARD-FAILS, so this is a narrowed claim and not a hole: the widened arm must still
  # reproduce (the separation branch below), the bench must still prove it ran (AC5's hit count
  # above), every spawned call must still have run, and a widened arm that stops reproducing
  # entirely still XPASSes at the top of this chain. Only the attribution half degrades, and it
  # degrades LOUDLY -- named, with its numbers.
  printf '  OBSERVE RL-BENCH attribution is UNAVAILABLE on this host: the UNWIDENED control granted more than one allow in %s of %s batches (worst=%s, hits=%s -- with the knobs off that is 0 by construction, so a non-zero here means the control arm is not a control), per round: %s. The widened arm reproduced %s of %s (%s%%). On this hardware tier the defect reproduces without any widening, so the control cannot carry the "the widening did the work" argument here. The reproduction claim is unaffected; the attribution claim is not made.\n' \
    "$RL_CTL_BAD" "$RL_CR_SOLO" "$RL_CTL_WORST" "$RL_CTL_HITS" "$RL_CTL_ROUNDS" "$RL_BO_BAD" "$RL_CR_BOTH" "$RL_BO_PCT"
  # HARD FAIL, NOT XFAIL -- a leftover `xfail` here would be a CRITICAL defect.
  # Flipping only the ENTRY of this chain live when the acquire
  # landed would leave both EXITS saying "known defect, expected red", which is what they meant while the
  # defect was open. `plc_gate` checks FAIL and XPASS and never inspects XFAIL, so a build that
  # genuinely reintroduced the double-allow -- measured at 5 of 6 batches, worst=4,
  # against a 0% control -- printed its reproduction and then exited CLEAN. The row's own comments
  # called it "a live regression guard on the fix" while it could not fail.
  no "RL-BENCH under both windows widened, the repair granted MORE THAN ONE allow in $RL_BO_BAD of $RL_CR_BOTH batches (worst=$RL_BO_WORST, allows per round: $RL_BO_ROUNDS) -- attribution is NOT claimed on this host (see the OBSERVE line above), but the repair handing out a second allow AT ALL is a regression of the atomic acquire and this row does not wait for attribution to say so"
elif [ "$RL_SEP" -lt "$RL_SEP_MIN" ]; then
  # AC2, AND ITS BAR MOVED ON A MEASUREMENT -- said here rather than quietly rewritten.
  #
  # It was originally "the control reproduces NOTHING". That was measured and it is false: on a
  # many-core machine under load the UNWIDENED control granted THREE allows in one of four batches, with
  # zero hits logged, so nothing was widened. It is intermittent -- 1 of 4 once, 0 of 4 on the two
  # runs either side, under moderate load -- but a hard zero is therefore a FLAKY assertion,
  # and shipping a probabilistic row is the disease this suite refuses.
  #
  # THE TOLERANCE WAS CHOSEN AFTER SEEING 1-of-4, and that is stated plainly instead of dressed up
  # as a prior. The honest justification is not preference: zero is falsified by measurement, and
  # the control's job was never "this can never happen" -- it is "the widening, not the assertion's
  # own triviality, did the work". A 25% control against a 100% widened arm carries that just as
  # well as 0% does. A control ABOVE this tolerance is left red on purpose: it would mean the host
  # reached the window so often that attribution really has collapsed.
  #
  # A double-allow with NO widening is evidence about the REAL defect rather
  # than about this bench -- and it falsifies a sentence in the hook's own header, which says
  # reaching the window is a function of runnable threads per core so "a 2-4 vCPU runner reaches it
  # and this host does not". A many-core host does, when it is busy enough.
  # REACHED ONLY WITH A QUIET CONTROL, so there is exactly one reading left: the widened arm itself
  # reproduced too weakly to be an oracle. The dirty-control case degrades above instead of landing
  # here, which is why this message no longer has to describe two opposite situations at once.
  no "RL-BENCH the widened arm reproduces strongly enough to be an oracle (widened $RL_BO_BAD of $RL_CR_BOTH = ${RL_BO_PCT}%, per round: $RL_BO_ROUNDS, against a quiet control at ${RL_CTL_PCT}%; separation $RL_SEP points, minimum $RL_SEP_MIN). The control is clean, so this is not an attribution problem -- the bench is too unreliable HERE. Raise the window toward the 300ms ceiling or run it on a quieter machine; do not lower the separation."
else
  # IT REPRODUCED, AND BY A MARGIN. A hard FAIL: the acquire is atomic now, so a bench that genuinely
  # reproduces is a regression of that fix. Before the fix this branch was an expected red, and the
  # XPASS at the top of this chain -- which fails this suite -- is what forced whoever fixed it
  # to come back and flip the row live.
  no "RL-BENCH under both windows widened, the repair granted MORE THAN ONE allow in $RL_BO_BAD of $RL_CR_BOTH batches (${RL_BO_PCT}% against a ${RL_CTL_PCT}% control, separation $RL_SEP >= $RL_SEP_MIN, worst=$RL_BO_WORST, allows per round: $RL_BO_ROUNDS); the unwidened control in the same run reproduced $RL_CTL_BAD of $RL_CR_SOLO (per round: $RL_CTL_ROUNDS). Cleanly attributed to the widening and therefore a REGRESSION of the atomic acquire, not host noise."
fi

# --- AC5's negative control, and the perturbation calibration ------------
#
# RL-AC5-meta -- THE ZERO-HIT RULE IS NOT VACUOUS, and the negative control is a REAL measured
# run rather than a synthetic zero: the unwidened control batch above genuinely logs nothing,
# because with the knobs off the wrappers never reach their log line. So the predicate is asserted
# against a number the bench actually produced. Without this, "zero hits is a hard failure" is a
# sentence, and a predicate that returned true for everything would satisfy the widened row alone.
if ! rl_ac5_ok "$RL_BO_HITS"; then
  no "RL-AC5-meta the widened batch's hit count ($RL_BO_HITS) satisfies AC5 -- the positive half of the control is broken, so the negative half below proves nothing"
elif rl_ac5_ok "$RL_CTL_HITS"; then
  no "RL-AC5-meta a disarmed batch logged $RL_CTL_HITS hits and AC5 accepted it -- a bench that never ran would report as 'the guard holds'"
else
  ok "RL-AC5-meta AC5's own predicate accepts the widened batch ($RL_BO_HITS hits) and rejects the disarmed one ($RL_CTL_HITS) -- a zero-hit run fails as 'the bench did not run', never as 'the guard holds'"
fi

# RL-AC6 -- DOES THE HIT LOG ITSELF CHANGE THE RATE?
#
# THE THRESHOLD WAS WRITTEN DOWN BEFORE THE CALIBRATION WAS RUN, and it is stated here rather than
# in a commit message so it cannot be quietly re-chosen later. At N=6 one flipped batch is 16.7%,
# and run-to-run noise at this N is already known to be that big -- the same configuration at 100ms
# measured 6 of 6 standalone and 5 of 6 in-suite. So: **a difference of MORE THAN ONE batch is
# material; a difference of one or zero is not.** Choosing this after seeing the numbers would be
# choosing the answer.
RL_AC6_TOL=1
#
# WHICH PERTURBATION THIS ARM ACTUALLY TESTS, said plainly instead of letting one number look like
# it covered both. The two arms differ ONLY by the log write -- an open/write/close per hit, i.e.
# the I/O-CONTENTION vector, and it is the worse one precisely on the 2-4 vCPU class where the
# defect really reproduces. The TIMING vector is NOT tested here and cannot be: the sleeps are the
# intervention itself, and removing them removes the bench. The question is asked because
# probes placed inside the racing path stopped the phenomenon reproducing entirely,
# 660 iterations, zero occurrences, 420 of them at load average 21.
rl_nolog="$(rl_batch "$RL_MS" "$RL_MS" "$RL_CR_BOTH" off)"
RL_NL_BAD="$(rl_f "$rl_nolog" 1)"; RL_NL_SHORT="$(rl_f "$rl_nolog" 3)"
RL_AC6_DELTA=$(( RL_BO_BAD > RL_NL_BAD ? RL_BO_BAD - RL_NL_BAD : RL_NL_BAD - RL_BO_BAD ))
RL_NL_HITS="$(rl_f "$rl_nolog" 6)"
if [ "$RL_NL_HITS" != 0 ]; then
  no "RL-AC6 the no-log calibration arm actually ran WITHOUT the log ($RL_NL_HITS hits appeared in it) -- the two arms are not different, so a delta of 0 says nothing"
elif [ "$RL_NL_SHORT" != 0 ]; then
  no "RL-AC6 the no-log calibration arm ran every spawned call ($RL_NL_SHORT of $RL_CR_BOTH batches lost one) -- the comparison is not measuring what it claims"
elif [ "$RL_AC6_DELTA" -gt "$RL_AC6_TOL" ]; then
  # PRE-DECLARED RESPONSE: drop the hit log and fall back to debris-shape inference -- two aside
  # nodes carrying two distinct pids can only occur if W1 was actually reached -- and record that
  # W2 then has NO direct run-time hit evidence. Written here so the response is not invented under
  # pressure at the moment the number arrives.
  no "RL-AC6 the hit log does not materially change the reproduction rate (with-log $RL_BO_BAD of $RL_CR_BOTH vs without-log $RL_NL_BAD of $RL_CR_BOTH, delta $RL_AC6_DELTA > tolerance $RL_AC6_TOL). The log perturbs: drop it, fall back to debris-shape inference, and record that W2 loses its direct run-time evidence."
else
  ok "RL-AC6 the hit log does not materially change the reproduction rate (with-log $RL_BO_BAD of $RL_CR_BOTH, without-log $RL_NL_BAD of $RL_CR_BOTH, delta $RL_AC6_DELTA <= tolerance $RL_AC6_TOL declared before the run) -- this measures the I/O-contention vector only, never the timing one"
fi

fi

# --- the XPASS polarity, DEMONSTRATED rather than asserted in prose ------
#
# The row above was XFAIL while the lock was unfixed; the fix made it XPASS, and this suite's
# gate treats an XPASS as a failure -- which is the forcing function: whoever fixes a lock cannot
# leave the bench behind, the suite goes red until they come back and flip the row live.
#
# "AN XPASS FAILS THIS SUITE" IS A CLAIM ABOUT A MECHANISM, so it is run, not written. A prose
# sentence here would be a declaration wider than the mechanism behind it
# -- and a claim about a path that can go unexercised: this file can have zero `xfail`
# calls for long stretches, so if the accounting were mis-wired, nothing would say so.
#
# IT RUNS IN AN ISOLATED SUBSHELL WITH ITS OWN COUNTERS, and that is not tidiness. `PASS`, `FAIL`,
# `XFAIL` and `XPASS` are file-global and the gate is this file's last line, so a demonstration that
# called `xpass()` in the normal flow would increment the shared counter and RED EVERY RUN OF THIS
# SUITE FOREVER. Getting it wrong has exactly two outcomes and both are bad: a permanently red
# suite, or a quiet retreat of this demonstration back into prose.
RL_X_BEFORE="$XFAIL/$XPASS"
rl_gate_probe="$(
  PASS=0; FAIL=0; XFAIL=0; XPASS=0
  xpass "isolated demonstration -- never counted by this file" "demo-not-an-id" >/dev/null
  if plc_gate; then printf 'OPEN'; else printf 'CLOSED'; fi
)"
rl_gate_xfail="$(
  PASS=0; FAIL=0; XFAIL=0; XPASS=0
  xfail "isolated demonstration -- never counted by this file" "demo-not-an-id" >/dev/null
  if plc_gate; then printf 'OPEN'; else printf 'CLOSED'; fi
)"
RL_X_AFTER="$XFAIL/$XPASS"
if [ "$rl_gate_probe" != CLOSED ]; then
  no "RL-AC8 an XPASS closes this suite's gate (the isolated gate expression came back $rl_gate_probe) -- a fixed lock would leave the bench silently stale instead of forcing it live"
elif [ "$rl_gate_xfail" != OPEN ]; then
  # THE OTHER HALF, and without it the row above is satisfied by a gate that fails on everything.
  no "RL-AC8 an XFAIL alone leaves the gate open (it came back $rl_gate_xfail) -- the XPASS half proves nothing if every outcome closes the gate"
elif [ "$RL_X_BEFORE" != "$RL_X_AFTER" ]; then
  no "RL-AC8 the demonstration leaked into this file's own totals (xfail/xpass went $RL_X_BEFORE -> $RL_X_AFTER) -- it would red every future run of this suite"
else
  ok "RL-AC8 demonstrated in an isolated subshell: an XPASS CLOSES this suite's gate while an XFAIL alone leaves it OPEN, and the demonstration leaks nothing into the file's totals (still $RL_X_AFTER)"
fi

# --- RETIRED: the byte-identity fence ----------------------------------------
#
# `RL-AC9` -- "the shipped hook is byte-identical to its merge-base" -- LIVED HERE AND IS GONE.
# It was a fence with no natural exit: every legitimate edit to `context-floor.sh` tripped it.
#
# DELETED RATHER THAN RE-POINTED AT THE NEW MERGE-BASE, and that is the whole decision. Re-pointing
# would recreate the fence one commit later and hand the next edit the identical red.
# A fence that must be re-pointed
# on every edit is not a fence, it is a chore that trains
# people to edit tests without reading them.
#
# CF-AC26 -- AND THE RETIREMENT ITSELF GETS AN ORACLE, because "I deleted it" is not evidence.
# A deletion with nothing watching it is one careless revert away from coming back, and it would come
# back GREEN on the commit that reintroduced it (the hook is unedited at the moment of a revert) and
# then red every commit afterwards, which is the worst possible time to learn about it. This asserts
# the fence stays retired.
#
# IT MUST TELL A LIVE ROW FROM A MENTION, and that is the whole difficulty. The paragraphs directly
# above name `RL-AC9` on purpose -- a retirement that does not say what it retired is
# useless to the next reader. So a bare substring search would report the retirement notice AS the
# thing it forbids. The discriminator is the SHAPE OF A VERDICT, not the presence of the id: a live
# row reaches `ok "`/`no "` or prints its own `SKIP` line. This is the use-versus-mention class
# (a checker that cannot tell a use from a mention), and the fix is the same: match the shape.
ac26_live_rows() {   # $1 = file ; prints how many LIVE RL-AC9 verdict rows it contains
  grep -cE '^[[:space:]]*(ok|no) "RL-AC9|printf .[[:space:]]*SKIP[[:space:]]+RL-AC9' "$1" 2>/dev/null || true
}
ac26_here="$(ac26_live_rows "$msrc")"
# THE POSITIVE CONTROL COMES FIRST. A predicate that answers zero to everything would satisfy the
# assertion below while covering nothing, which is precisely how a deleted row stays "guarded".
ac26_fake="$WORK/ac26-fake.sh"
{ cat "$msrc"; printf '  no "RL-AC9 the shipped hook is byte-identical to its merge-base"\n'; } > "$ac26_fake"
ac26_ctrl="$(ac26_live_rows "$ac26_fake")"
if [ "${ac26_ctrl:-0}" -eq 0 ]; then
  no "CF-AC26 the retirement predicate does not recognise a reintroduced RL-AC9 row even when one is planted (control counted $ac26_ctrl) -- the assertion below would pass over anything"
elif [ "${ac26_here:-0}" -ne 0 ]; then
  no "CF-AC26 RL-AC9 is live again in this suite ($ac26_here verdict row(s)) -- the byte-identity fence was retired because every legitimate edit to context-floor.sh tripped it; reintroducing it reds every such edit"
else
  ok "CF-AC26 the retired RL-AC9 byte-identity fence has not come back as a live row (0 verdict rows here, $ac26_ctrl in a copy with one planted) -- the prose above may name it freely, only a verdict counts"
fi

# --- the row says what it may not claim, and the SAYING is checked ------
#
# PRESENCE IS MECHANICAL, TRUTHFULNESS IS NOT, and the split is stated rather than blurred. This
# catches one failure: a header that drops the boundary language
# entirely. It does NOT check that the prose is correct -- that is the independent reviewer's job.
# An oracle claiming to
# check truthfulness would be a fabricated oracle, which is the thing the AC-binding gate exists
# to stop.
#
# THE WORDING IS DELIBERATELY NOT PINNED. A golden-string assertion makes every wording
# improvement a test edit, and that trains people to change the test without reading it.
rl_bsrc="$HERE/test-context-floor-contract.sh"
if [ ! -r "$rl_bsrc" ]; then
  no "RL-AC10 the boundary block is present: cannot read own source at $rl_bsrc"
else
  # COUNTED SEPARATELY, because a TOTAL of two cannot tell one-of-each from two-of-one. Measured as
  # a surviving mutant: renaming END to BEGIN (a copy-paste slip while moving the block) and
  # deleting the entire body gave markers=2 and a "body" of 746 lines -- the `awk` never resets its
  # flag, so an unterminated block swallows the rest of the file -- and the row went GREEN with no
  # boundary statement present at all. Each of the two mutants recorded earlier was killed on its
  # own; their COMBINATION was the blind spot.
  rl_bbeg="$(grep -cE '^#RL-BOUNDARY-BEGIN$' "$rl_bsrc" || true)"
  rl_bend="$(grep -cE '^#RL-BOUNDARY-END$'   "$rl_bsrc" || true)"
  rl_bspan="$(awk '/^#RL-BOUNDARY-BEGIN$/{f=1;next} /^#RL-BOUNDARY-END$/{f=0} f' "$rl_bsrc")"
  rl_bbody="$(printf '%s\n' "$rl_bspan" | grep -cE '^#[[:space:]]*[^[:space:]]' || true)"
  # STRUCTURE, NOT PHRASING. The wording stays free -- pinning a golden string makes every
  # improvement a test edit -- but the SHAPE is required: a may-not-claim heading and three
  # numbered claims. Measured as a surviving mutant: ten lines of prose that explicitly PERMITTED
  # all three forbidden claims passed a bare line-count floor. That is deletion of required
  # content, which this row does claim to cover.
  rl_bnot="$(printf '%s\n' "$rl_bspan" | grep -cE 'MAY NOT CLAIM' || true)"
  rl_bnum="$(printf '%s\n' "$rl_bspan" | grep -cE '^#[[:space:]]+[0-9]+\.' || true)"
  if [ "${rl_bbeg:-0}" != 1 ] || [ "${rl_bend:-0}" != 1 ]; then
    no "RL-AC10 exactly one BEGIN and one END sentinel (found begin=${rl_bbeg:-0} end=${rl_bend:-0}) -- a total of two is not the same check, and an unterminated block makes the body count swallow the rest of the file"
  elif [ "${rl_bbody:-0}" -lt 5 ]; then
    no "RL-AC10 the boundary block has a body (${rl_bbody:-0} non-empty comment lines between the sentinels) -- the sentinels survived an edit that gutted what they delimit"
  elif [ "${rl_bnot:-0}" -lt 1 ] || [ "${rl_bnum:-0}" -lt 3 ]; then
    no "RL-AC10 the block still states what may NOT be claimed, as three numbered items (may-not headings=${rl_bnot:-0}, numbered claims=${rl_bnum:-0}, wanted >=1 and >=3) -- prose that deletes the prohibitions satisfies a bare line count"
  else
    ok "RL-AC10 the row carries a sentinel-delimited statement of what this bench may and may not claim (${rl_bbody:-0} lines, ${rl_bnum:-0} numbered prohibitions) -- structure is checked here, phrasing is deliberately free, and truthfulness is the reviewer's and recorded as an exclusion"
  fi
fi

# WHAT THE SOLO CONFIGURATIONS ESTABLISHED, and the correction the measurement forced.
#
# The design's premise was that W1 alone reproduces NOTHING, resting on an earlier measurement's
# "102 passed / 0 failed, all 8 batches granting exactly one". THAT IS A SAMPLE, NOT A BOUND, and
# re-measuring it before relying on it falsified the absolute form.
# Measured on a many-core host, 100ms, `mkdir`-only widening (before the acquire moved to `ln`):
#     width 12 -- 6 of 24 batches reproduced (one run took 4 of 8 under heavy load)
#     width 24 -- 1 of 35
#     width 32 -- 0 of 16
# So W1 alone CAN hand out a second allow; it is rare, load-sensitive, and it never reaches N-of-N.
# The design's direction survives and its absolute claim does not, which is the same correction
# this file already carries one screen up about `0/660`: a zero is a property of the host and the
# width it was measured at, never a bound on the guard.
#
# WIDTH IS THE FIRST LEVER AND THE WINDOW IS THE SECOND, and the order matters -- the first version
# of this note said "the lever is concurrency, NOT sleep length" and the fuller measurement below
# falsified the second half of that sentence within the hour. Both halves are kept here because the
# wrong one is the more instructive.
#
# At WIDTH 12 the rate is genuinely non-monotonic in the window -- 2/4 at 50ms, 1/4 at 100ms, 0/4 at
# 150ms, 2/4 at 200ms, 1/4 at 300ms. A coin flip, and the mechanism says why: reproducing needs a
# rival's jitter to land inside the first repairer's rename-plus-create gap, and a longer sleep
# delays BOTH racers equally, so it buys nothing when there is no third party to supply jitter.
# Chasing sleep length at width 12 would have burned an afternoon for noise.
#
# ONCE THE WIDTH SUPPLIES RIVALS, the window does start to pay: at width 24, 100ms reproduced 6 of 6
# standalone but only 5 of 6 in-suite (measured -- the suite is a busier machine than the bare
# harness, and that difference alone moved the row onto its fallback branch), while 150ms reproduced
# 6 of 6 on three consecutive standalone trials AND in-suite. Width 32 at 100ms was consistently
# 5 of 6 with a higher worst (6, 7, 7), so more rivals is not monotonically better either.
# Shipped: width 24, 150ms, control 0 of 4 in every trial.

# CF-AC5c -- A REPAIR LOCK LEFT BEHIND BY A DEAD HOLDER MUST NOT WEDGE THE SESSION.
# The mutex above buys the single-winner property with a lock, and a lock introduces the failure mode
# locks always introduce. The first version's own comment
# understated it: with the corrupt node still in place and a lock nobody owns, every later call fails
# to take the lock, fails to create, and blocks -- and refreshing RESUME.md CANNOT clear it, because
# there is no marker mtime to compare against. That is the unclearable block this file's header calls
# the cardinal sin, reachable by one `kill -9`.
#
# Reproduced against the previous commit before the fix was written: rc 2, 2, and 2 again after the
# checkpoint was refreshed, with `s.marker` and `s.repair` both still sitting there.
#
# The reclaim is by OWNERSHIP, not by age: the holder writes its PID into the lock and a later call
# asks the kernel whether that process still exists. No clock, no threshold.
#
# RUN TWICE, ONCE PER LOCK SHAPE, AND THE SECOND ARM IS THE ONE THE UPGRADE NEEDS.
# The lock became a REGULAR FILE whose content is the owner pid. But `$MDIR` outlives an invocation,
# so the FIRST RUN of the new code on a real machine can find a DIRECTORY-shaped lock left by the
# previous version -- and if the reclaim only understands the new shape, that abandoned lock is
# unreclaimable forever. That is the cardinal sin, introduced BY the fix, on exactly the upgrade path
# nobody exercises locally. Both arms are therefore driven, and the legacy one is not optional.
cf_ac5c() {   # $1 = label  $2 = shape (file|dir)
  local d rc1 rc2 aside dead
  d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
  mkdir -p "$d/plc-context-floor/s.marker"; echo x > "$d/plc-context-floor/s.marker/inner"
  echo current > "$d/RESUME.md"
  ( : ) & dead=$!; wait "$dead" 2>/dev/null || true               # a PID that is definitively gone
  if [ "$2" = dir ]; then
    mkdir -p "$d/plc-context-floor/s.repair"; printf '%s\n' "$dead" > "$d/plc-context-floor/s.repair/pid"
  else
    printf '%s\n' "$dead" > "$d/plc-context-floor/s.repair"
  fi
  rc1="$(run_hook "$d" "$(ev_for "$d")")"
  sleep 1; echo refreshed > "$d/RESUME.md"
  rc2="$(run_hook "$d" "$(ev_for "$d")")"
  aside="$(ls -A "$d/plc-context-floor" 2>/dev/null | grep -c '^s\.corrupt\.' || true)"
  if [ "${aside:-0}" = 0 ]; then
    no "CF-AC5c ($1) a lock left by a dead holder is reclaimed and the corrupt node repaired (nothing was moved aside; rcs=$rc1$rc2)"
  elif [ "$rc2" != 0 ]; then
    no "CF-AC5c ($1) refreshing the checkpoint still clears the block after a stale lock (rc=$rc2) -- an unclearable block"
  else
    ok "CF-AC5c ($1) a repair lock left by a dead holder is reclaimed, and the block stays clearable"
  fi
}
if [ "$(uname -s 2>/dev/null)" != "" ]; then
  cf_ac5c "current shape, a regular file whose content is the pid" file
  cf_ac5c "LEGACY shape, a pre-fix directory holding pid -- the upgrade path" dir
fi

# CF-LNDIR -- A LIVE LEGACY DIRECTORY LOCK MUST STILL EXCLUDE A NEW-CODE ACQUIRER.
#
# MEASURED HERE RATHER THAN TAKEN ON REPORT, WITH A CONTROL:
# `ln <file> <existing-regular-file>` fails `File exists` rc=1 -- but `ln <file> <existing-DIRECTORY>`
# returns rc=0 and links the file INSIDE the directory. Ordinary POSIX `ln`, not a platform quirk.
#
# WHY THAT WAS A CRITICAL DEFECT AND NOT A CURIOSITY. The legacy lock shape IS a directory, kept on
# purpose for the upgrade path, and the reclaim leaves it alone while its owner is ALIVE. So a live
# pre-fix holder plus a new-code acquirer gave `ln` rc=0, the acquirer believed it held the lock, and
# both repaired -- W1 reproduced, on the one code path the atomic acquire added, in the exact window the
# stanza's own comments say will occur. The whole exclusion argument rested on `ln`'s EEXIST, and
# EEXIST is not what `ln` does against a directory.
#
# THE HOLDER IS THIS TEST PROCESS, so `kill -0` on it necessarily succeeds and the reclaim MUST leave
# the lock in place -- which is what makes this a live-holder fixture rather than a stale-lock one.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
echo current > "$d/RESUME.md"
mkdir -p "$d/plc-context-floor/s.marker"; echo x > "$d/plc-context-floor/s.marker/inner"
mkdir -p "$d/plc-context-floor/s.repair"; printf '%s\n' "$$" > "$d/plc-context-floor/s.repair/pid"
lnd_rc="$(run_hook "$d" "$(ev_for "$d")")"
lnd_aside="$(ls -A "$d/plc-context-floor" 2>/dev/null | grep -c '^s\.corrupt\.' || true)"
lnd_stray="$(ls -A "$d/plc-context-floor/s.repair" 2>/dev/null | grep -c 'repair\.tmp' || true)"
lnd_dir=0; [ -d "$d/plc-context-floor/s.repair" ] && lnd_dir=1
if [ "${lnd_aside:-0}" != 0 ]; then
  no "CF-LNDIR a new-code caller REPAIRED while a live legacy directory lock was held ($lnd_aside aside node(s), rc=$lnd_rc) -- \`ln\` returned success against the directory instead of failing EEXIST, so two processes hold what is nominally one lock. That is W1, on the upgrade path."
elif [ "$lnd_dir" != 1 ]; then
  no "CF-LNDIR the live legacy directory lock was destroyed by a new-code caller (rc=$lnd_rc) -- its owner is alive, so it must be left exactly where it is"
elif [ "${lnd_stray:-0}" != 0 ]; then
  no "CF-LNDIR a new-code caller left $lnd_stray staging file(s) INSIDE another holder's lock directory -- the \`ln\` nested rather than failing, and nothing cleaned up after it"
else
  ok "CF-LNDIR a live legacy directory lock excludes a new-code acquirer: no repair happened, the lock is untouched, and no staging file was nested inside it (rc=$lnd_rc)"
fi

# CF-STAGE -- THE STAGING PATH IS AN ADVERSARIAL INPUT TOO.
#
# THE CLASS READS BETTER AS A SHAPE THAN AS A BUG:
# HOSTILE PRE-EXISTING NODES AT AN
# AUXILIARY PATH, one the assertions treat as the guard's own scratch space rather than as input.
# The staging name is predictable, it sits in a shared state directory, and the write to it is a
# plain redirection.
#
# THE FIFO CASE IS WORSE THAN ANYTHING ELSE IN THIS FILE. A `>` onto a FIFO with no reader BLOCKS --
# measured, still blocked after 2s and killed -- so the hook does not fail open, it HANGS, and every
# edit in the session hangs behind it. This file's whole safety argument is "fails OPEN, never
# closed, on its own breakage", and a hang is neither: it is a third outcome the discipline never had
# to name, because until the staging path existed nothing here could hang.
#
# The symlink case is quieter and not smaller: `>` FOLLOWS the link, so the guard becomes the thing
# writing a pid through it into a file somebody else chose. Measured against a victim file.
cf_stage() {   # $1 = label  $2 = fifo|link
  local d ev rc aside wrap
  d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
  echo current > "$d/RESUME.md"
  echo UNTOUCHED > "$d/victim"
  mkdir -p "$d/plc-context-floor/s.marker"; echo x > "$d/plc-context-floor/s.marker/inner"
  # PLANT-THEN-`exec`, WHICH IS THE ONLY DETERMINISTIC WAY TO HIT THIS PATH. The staging name carries
  # the HOOK's own pid, and two guesses at it failed before this one: planting a range around the
  # suite's `$$` missed by thousands (the suite has spawned that many by the time this row runs), and
  # planting around a freshly probed pid still missed, because `run_hook` spawns several processes of
  # its own in between. Both misses were caught only because this row asserts its fixture landed --
  # with the hardening REMOVED from the hook, both arms reported green.
  #
  # `exec` REPLACES the wrapper with the hook, keeping the SAME pid. So the wrapper plants the node at
  # exactly the name the hook is about to use, with no guessing and no race.
  wrap="$d/wrap.sh"
  { printf '#!/usr/bin/env bash\n'
    printf 'MDIR="$1"; KIND="$2"; VICTIM="$3"; IMPL="$4"; shift 4\n'
    printf 'if [ "$KIND" = fifo ]; then mkfifo "$MDIR/s.repair.tmp.$$" 2>/dev/null || true\n'
    printf 'else ln -s "$VICTIM" "$MDIR/s.repair.tmp.$$" 2>/dev/null || true; fi\n'
    printf 'printf "%%s" "$$" > "$MDIR/../planted-at-pid"\n'
    printf 'exec /bin/bash "$IMPL"\n'
  } > "$wrap"
  chmod +x "$wrap"
  ev="$(ev_for "$d")"
  # A HARD TIMEOUT, because the failure under test is a HANG. Without one this row would not fail --
  # it would take the whole suite down with it, which is exactly how a hang differs from every other
  # outcome this file asserts.
  printf '%s' "$ev" | env -u PLC_CONTEXT_FLOOR -u PLC_CONTEXT_FLOOR_PCT -u PLC_CONTEXT_FLOOR_STEP \
    -u PLC_CONTEXT_WINDOW -u PLC_RESUME_PATH TMPDIR="$d" LC_ALL=C \
    ${CT_TIMEOUT:+timeout 15} /bin/bash "$wrap" \
      "$d/plc-context-floor" "$2" "$d/victim" "$IMPL" >/dev/null 2>&1
  rc=$?
  aside="$(ls -A "$d/plc-context-floor" 2>/dev/null | grep -c '^s\.corrupt\.' || true)"
  if [ ! -s "$d/planted-at-pid" ]; then
    no "CF-STAGE ($1) the wrapper never ran, so nothing was planted and this row exercised NOTHING -- it must not report green"
  elif [ "$rc" = 124 ]; then
    no "CF-STAGE ($1) THE HOOK HUNG (timed out at 15s). A plain redirection onto a FIFO with no reader blocks forever; the hook did not fail open, it stopped -- and every edit in a real session would stop behind it"
  elif [ "$(cat "$d/victim" 2>/dev/null || true)" != UNTOUCHED ]; then
    no "CF-STAGE ($1) the guard wrote THROUGH a planted symlink into a file it does not own (victim now: $(cat "$d/victim" 2>/dev/null)) -- a plain redirection follows a link, and the staging path was never type-checked"
  elif [ "${aside:-0}" = 0 ]; then
    no "CF-STAGE ($1) the repair never happened with a hostile node at the staging path (rc=$rc, no aside node) -- the staged write was blocked or diverted, so the guard cannot repair and the block cannot clear"
  else
    ok "CF-STAGE ($1) a hostile node planted at the hook's exact staging name is cleared, the repair still happens, nothing outside the guard's own state is written, and it does not hang (rc=$rc)"
  fi
}
if command -v mkfifo >/dev/null 2>&1; then
  cf_stage "FIFO -- a plain redirection onto one blocks forever" fifo
  cf_stage "symlink -- a plain redirection follows it" link
else
  printf '  SKIP   CF-STAGE mkfifo is unavailable here, so the hostile-staging-node rows cannot be built (printed rather than silently omitted)\n'
fi

# CF-LNODE -- A SYMLINK AT THE LOCK PATH MUST NOT WEDGE THE SESSION FOREVER.
#
# It is the cardinal sin in its purest form. A symlink, FIFO or
# socket at the lock path matched NEITHER reclaim branch, so nothing removed it; `ln` failed against
# it on every call (`link()` answers by directory entry and does not follow), `_cflock` stayed empty
# forever, and every later call fell to the lock-loser branch and exited 2 -- a permanent block that
# refreshing the checkpoint cannot clear, which is the one outcome this file's header forbids.
#
# THE DANGLING CASE ALSO MADE THE DIAGNOSTIC LIE: `-e` FOLLOWS a symlink, so the classifier read "the
# path is free" about a path that was permanently occupied. Both halves are asserted here.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
echo current > "$d/RESUME.md"
mkdir -p "$d/plc-context-floor/s.marker"; echo x > "$d/plc-context-floor/s.marker/inner"
ln -s "$d/definitely-not-here" "$d/plc-context-floor/s.repair"
lno_err="$WORK/lno.err"
lno_rc="$(run_hook "$d" "$(ev_for "$d")" 2>"$lno_err")"
lno_aside="$(ls -A "$d/plc-context-floor" 2>/dev/null | grep -c '^s\.corrupt\.' || true)"
sleep 1; echo refreshed > "$d/RESUME.md"
lno_rc2="$(run_hook "$d" "$(ev_for "$d")")"
if [ "${lno_aside:-0}" = 0 ]; then
  no "CF-LNODE a dangling symlink at the lock path stopped the repair entirely (rcs=$lno_rc$lno_rc2, no aside node) -- nothing reclaims that node, so the guard can never repair and the block never clears"
elif [ "$lno_rc2" != 0 ]; then
  no "CF-LNODE refreshing the checkpoint does not clear the block after a symlink at the lock path (rc=$lno_rc2) -- that is the permanent, unclearable block this file's header calls the cardinal sin"
elif grep -q 'the path is free' "$lno_err" 2>/dev/null; then
  no "CF-LNODE the classifier reported 'the path is free' about a path occupied by a symlink -- \`-e\` follows the link, so the message says the opposite of the truth"
else
  ok "CF-LNODE a symlink at the lock path is reclaimed, the repair proceeds, the block stays clearable, and the classifier does not report a squatted path as free"
fi

# `-e` is true of a DIRECTORY named RESUME.md, which is not a checkpoint and must not buy the free
# call. This row covers that half at the first-call branch; the clear-path block below covers the
# OTHER half.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"; mkdir -p "$d/RESUME.md"
rc="$(run_hook "$d" "$(ev_for "$d")")"
[ "$rc" = 2 ] \
  && ok "a DIRECTORY named RESUME.md does not buy the first call's free pass" \
  || no "a DIRECTORY named RESUME.md does not buy the first call's free pass (rc=$rc)"

# The other two shapes at the FIRST-CALL branch. These exist because the clear-path block below CANNOT
# cover this half and a review measured it: those rows pre-arm the marker, so `FIRST_ARM` is 0 and
# the first-call branch is never entered. Reverting the first-call predicate alone (`-f` -> `-e` at
# context-floor.sh) reddened exactly ONE row -- the directory row above -- while all three clear-path rows
# stayed green. FIFO and symlink->/dev/null had zero first-call coverage, and the comment at the
# clear-path block claimed the two-site design was guarded "per shape" on the strength of rows that only
# ever exercise one site. Assert the second site directly instead of inferring it.
#
# ONE OF THESE THREE IS NOT SITE-ISOLATED, and that is a property of the hook, not a defect here.
# Measured on both single-site mutants: `dir` and `fifo` redden ONLY under the first-call revert,
# but `devnull` reddens under EITHER. Rejection at the first-call branch is not a terminal block --
# control falls through to the clear path -- so a devnull checkpoint that `-f` correctly refuses the
# free pass then meets the clear-path guard, and if THAT one is reverted `stat -L` reads devfs's
# live mtime and clears anyway. Expect devnull in both mutant runs; a run where it is the ONLY red
# is a first-call revert that also disabled something else.
for shape in fifo devnull; do
  d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
  case "$shape" in
    fifo)    mkfifo "$d/RESUME.md" ;;
    devnull) ln -s /dev/null "$d/RESUME.md" ;;
  esac
  rc="$(run_hook "$d" "$(ev_for "$d")")"
  [ "$rc" = 2 ] \
    && ok "a $shape named RESUME.md does not buy the first call's free pass" \
    || no "a $shape named RESUME.md does not buy the first call's free pass (rc=$rc)"
done

# The first-call positive control. It differs from the plain-file control further up in exactly one
# way that matters here: the checkpoint is a SYMLINK to a real file, so it proves `-f` follows
# symlinks at THIS site rather than only at the clear path. It asserts all three signals (allow,
# marker armed, no window) because a rc-only assertion would be strictly weaker than the plain-file
# row and would earn its place only by accident.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
echo fresh > "$d/real-checkpoint.md"; ln -s "$d/real-checkpoint.md" "$d/RESUME.md"
rc="$(run_hook "$d" "$(ev_for "$d")")"
{ [ "$rc" = 0 ] && [ -e "$d/plc-context-floor/s.marker" ] \
                && [ ! -e "$d/plc-context-floor/s.clearedat" ]; } \
  && ok "a RESUME.md symlinked to a real file DOES buy the first call's free pass (clear-path control)" \
  || no "a RESUME.md symlinked to a real file DOES buy the first call's free pass (clear-path control) (rc=$rc clearedat=$([ -e "$d/plc-context-floor/s.clearedat" ] && echo YES || echo NO) marker=$([ -e "$d/plc-context-floor/s.marker" ] && echo PRESENT || echo GONE))"

# --- the CLEAR path also requires a checkpoint FILE ------------------------------------
# Three shapes that `stat -L` reports an mtime for while being no kind of checkpoint. Without the
# FILE requirement each of them cleared the block on the second call AND collected a STEP-sized grace window --
# measured 00 / clearedat=YES on an older version of the hook, i.e. ~30K of free
# over-floor edits per arm cycle.
#
# BOTH HALVES ARE ASSERTED SEPARATELY, per shape. What that buys is narrower than this comment
# used to claim, and the difference was measured rather than reasoned:
#
#   * A clearedat-only assertion DOES pass on a hook that stopped blocking -- that half stands.
#   * "An `rcs=22` assertion alone passes on a hook that still writes clearedat" was WRONG, and no
#     such hook can be built against this fixture. `clearedat` is not an output, it is an INPUT to
#     the re-arm decision in context-floor.sh's grace-window check: writing it grants the STEP-sized grace
#     window, so call 2 is allowed and `rcs` becomes 20, not 22. Measured on a mutant that writes
#     `clearedat` unconditionally at the clear path: all three rows print `rcs=20 clearedat=YES`.
#     Both assertions move together; neither is redundant, but they are not independent either.
#
# Making them genuinely independent needs a fixture whose occupancy climbs by more than STEP between
# calls, so the grace window cannot absorb call 2. That fixture does not exist here. Do not restore
# the old claim -- it described a mutant that cannot PASS an rcs-only assertion against this fixture.
# (The mutant itself is perfectly writable. What cannot happen is the
# outcome the old claim predicted. An earlier wording here said "cannot be written", which is the
# same over-reach one notch smaller -- it dropped the qualifier the sentence nine lines up carries.)
#
# WHAT THESE ROWS DO NOT COVER, stated because the comment here used to imply otherwise. The fix
# leaves the "is it a checkpoint FILE" rule expressed in TWO places -- the first-call branch and the
# clear-path guard -- rather than hoisting one shared predicate (hoisting would move the test above
# the arm block, and RESUME writes are EXEMPT and therefore concurrent, so a checkpoint written in
# that window would be judged absent and blocked). A revert of ONE of those two sites is therefore
# possible, and THESE ROWS CANNOT SEE IT: the setup below pre-arms the marker, so `FIRST_ARM` is 0
# and the first-call branch is never entered. Measured -- reverting the first-call predicate alone
# leaves all three rows below green. The first-call site is covered by its own rows further up
# (the directory row plus the fifo/devnull rows beside it); the two-site design is
# guarded by BOTH row groups together, not by this one.
#
# marker=PRESENT is asserted for a narrower reason than "blocking by not arming" -- that outcome is
# not expressible here, since the setup pre-creates the marker and the arm block is skipped. What it
# catches is a clear that RAN: the clear path removes the marker, so a hook that cleared and then
# failed to record `clearedat` shows up as marker=GONE rather than passing on the clearedat check.
for shape in dir fifo devnull; do
  d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
  arm_old "$d"
  case "$shape" in
    dir)     mkdir -p "$d/RESUME.md" ;;
    fifo)    mkfifo "$d/RESUME.md" ;;
    devnull) ln -s /dev/null "$d/RESUME.md" ;;
  esac
  rcs=""
  for i in 1 2; do rcs="$rcs$(run_hook "$d" "$(ev_for "$d")")"; done
  { [ "$rcs" = 22 ] \
    && [ ! -e "$d/plc-context-floor/s.clearedat" ] \
    && [ -e "$d/plc-context-floor/s.marker" ]; } \
    && ok "a $shape named RESUME.md blocks on BOTH calls and earns no grace window" \
    || no "a $shape named RESUME.md blocks on BOTH calls and earns no grace window (rcs=$rcs clearedat=$([ -e "$d/plc-context-floor/s.clearedat" ] && echo YES || echo NO) marker=$([ -e "$d/plc-context-floor/s.marker" ] && echo PRESENT || echo GONE))"
done

# The positive control for the three rows above, and it is NOT optional: `[ -f ]` follows symlinks,
# so a RESUME.md symlinked to a real checkpoint must still clear. Without this row, "blocks on all
# three shapes" is satisfied by a hook that has stopped clearing anything at all -- the same
# never-clears trap the dangling-symlink row spells out below, arriving from the other direction.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
arm_old "$d"
echo fresh > "$d/real-checkpoint.md"; ln -s "$d/real-checkpoint.md" "$d/RESUME.md"
rcs=""
for i in 1 2; do rcs="$rcs$(run_hook "$d" "$(ev_for "$d")")"; done
{ [ "$rcs" = 00 ] && [ -e "$d/plc-context-floor/s.clearedat" ]; } \
  && ok "a RESUME.md symlinked to a real file still clears -- the -f guard follows symlinks" \
  || no "a RESUME.md symlinked to a real file still clears -- the -f guard follows symlinks (rcs=$rcs)"

# --- a POSITIVE CONTROL and a RECOVERY row, independently falsifiable ---------
# THE ROW THAT USED TO SIT HERE WAS DECORATIVE, and it is deleted rather than flipped. It asserted
# `rcs=222` plus no `clearedat`. Measured, twice over:
#
#   * the design its own comment REJECTED -- rejecting a non-regular marker inside `mtime_of` --
#     makes it report XPASS while wedging the guard at `2222`, with every other row green. It
#     reported success for the outcome the file's header calls the cardinal sin.
#   * a pure state-file rename that fixes nothing also makes it XPASS.
#   * and the design that IS correct makes it XFAIL: under repair the first call takes the ordinary
#     one-call first-arm grant, so the reading is `022`, not `222`. The row was red against a
#     working fix and green against two broken ones.
#
# `222` is the signature of BLOCKING, not of REPAIRING, and one assertion cannot separate "it
# blocked" from "it blocked for the right reason and can still be cleared". So it becomes two rows
# that fail for different reasons: `0000` must fail the control, `2222` must fail the recovery.
# Three independently-surveyed ecosystems converge on exactly this pairing (TLA+ safety plus
# liveness, Gomega `Consistently` plus `Eventually`, and the mutation-testing definition of a weak
# assertion).
#
# The deleted row also carried a `sleep 1`, which this harness bans: it makes the fixture
# slower without making it deterministic. Both rows below CONSTRUCT their mtimes and verify the
# construction fatally.

# CF-AC2 -- POSITIVE CONTROL: the block was entered FOR THE FLOOR'S REASON.
# The discriminator is the second half, and without it this row is the weak assertion it replaces:
# a hook that blocks unconditionally satisfies "it blocked". The SAME fixture UNDER the floor must
# ALLOW, so only a hook that is actually consulting the occupancy can pass both halves.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
mkdir -p "$d/plc-context-floor/s.marker"; echo x > "$d/plc-context-floor/s.marker/inner"
echo stale > "$d/RESUME.md"
python3 - "$d/RESUME.md" <<'PY' || { echo "FATAL: could not construct the stale checkpoint" >&2; exit 1; }
import os,sys
# Older than anything the hook will create in this run, by construction rather than by racing a clock.
os.utime(sys.argv[1], ns=(1_000_000_000_000_000_000, 1_000_000_000_000_000_000))
PY
rc_over=""
for i in 1 2; do rc_over="$rc_over$(run_hook "$d" "$(ev_for "$d")")"; done
d2="$(sandbox)"; usage_line 100000 > "$d2/t.jsonl"     # same shape, UNDER the floor
mkdir -p "$d2/plc-context-floor/s.marker"; echo x > "$d2/plc-context-floor/s.marker/inner"
echo stale > "$d2/RESUME.md"
python3 - "$d2/RESUME.md" <<'PY' || { echo "FATAL: could not construct the stale checkpoint" >&2; exit 1; }
import os,sys
os.utime(sys.argv[1], ns=(1_000_000_000_000_000_000, 1_000_000_000_000_000_000))
PY
rc_under=""
for i in 1 2; do rc_under="$rc_under$(run_hook "$d2" "$(ev_for "$d2")")"; done
# "NOT `00`" IS NOT "BLOCKED", and this row once asserted the weaker of the
# two. The first version accepted any over-floor reading except `00`, so an implementation returning
# `1` on both calls -- an ERROR, not a block -- reached the `ok` branch while the row's own name said
# "blocks". Probed: `rc_over=11 rc_under=00` reported ok. The row now names the exact
# shape it means. `02` is that shape and it is contract, not incidental: the checkpoint FILE exists
# (it is merely stale), so the first call takes the once-per-arm-cycle grant and the second blocks --
# the same reading `022` that AC1 measures for all four corrupt shapes.
if [ "$rc_over" != 02 ]; then
  no "CF-AC2 a corrupt marker over the floor is repaired then blocks (want 02, got over=$rc_over under=$rc_under)"
elif [ "$rc_under" != 00 ]; then
  no "CF-AC2 the block is the FLOOR's, not unconditional (the same fixture under the floor blocked: under=$rc_under)"
elif [ ! -f "$d/plc-context-floor/s.marker" ] || [ -L "$d/plc-context-floor/s.marker" ]; then
  no "CF-AC2 the block followed a REPAIR (no fresh regular marker was left behind)"
else
  ok "CF-AC2 a repaired marker blocks over the floor and allows under it (over=$rc_over under=$rc_under)"
fi

# CF-AC3 -- RECOVERY, starting from an ESTABLISHED blocked state.
# "Established" is load-bearing: a recovery row that starts from an unproven block degenerates into
# the same weak assertion it replaces, because a hook that never blocks passes it trivially. The
# block is asserted first, and only then is the one named action performed.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
mkdir -p "$d/plc-context-floor/s.marker"; echo x > "$d/plc-context-floor/s.marker/inner"
echo stale > "$d/RESUME.md"
python3 - "$d/RESUME.md" <<'PY' || { echo "FATAL: could not construct the stale checkpoint" >&2; exit 1; }
import os,sys
os.utime(sys.argv[1], ns=(1_000_000_000_000_000_000, 1_000_000_000_000_000_000))
PY
run_hook "$d" "$(ev_for "$d")" >/dev/null            # arms (and repairs)
rc_blocked="$(run_hook "$d" "$(ev_for "$d")")"       # the state the recovery starts from
MARK="$d/plc-context-floor/s.marker"
if [ "$rc_blocked" != 2 ]; then
  no "CF-AC3 the blocked state could not be established (rc=$rc_blocked) -- recovery is untested"
elif [ ! -f "$MARK" ]; then
  no "CF-AC3 no regular marker to recover from (the repair did not happen)"
else
  echo refreshed > "$d/RESUME.md"                    # the ONE action the block message names
  python3 - "$d/RESUME.md" "$MARK" <<'PY' || { echo "FATAL: mtime construction failed" >&2; exit 1; }
import os,sys
m=os.stat(sys.argv[2]).st_mtime_ns
os.utime(sys.argv[1], ns=(m+2_000_000_000, m+2_000_000_000))
assert os.stat(sys.argv[1]).st_mtime_ns > os.stat(sys.argv[2]).st_mtime_ns, "checkpoint is not newer"
PY
  rc_after="$(run_hook "$d" "$(ev_for "$d")")"
  [ "$rc_after" = 0 ] \
    && ok "CF-AC3 refreshing the checkpoint clears a block that followed a repair" \
    || no "CF-AC3 refreshing the checkpoint clears a block that followed a repair (rc=$rc_after -- the 2222 wedge)"
fi

# The marker path being OCCUPIED BY A SYMLINK is a third failure cause for the O_EXCL create, and
# it is corrupt guard state rather than a marker or a write failure. Both simpler answers were
# measured and both are wrong, so BOTH HALVES ARE ASSERTED HERE -- an implementation can satisfy
# either one alone while being unusable:
#   * fail open (`[ -e ]` alone; `-e` is FALSE for a dangling link) -> nothing is ever created, so
#     every later call fails open: 00000 over five calls, a permanent silent allow.
#   * block without repairing -> 22222, but the marker never exists, so mtime_of returns nothing
#     forever and REFRESHING RESUME.md DOES NOT CLEAR IT. The block is unclearable by the only
#     action its own message names, which is what trains an operator to disable the floor for good.
# So: it must block, it must never write through the link, AND the named recovery must work.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
mkdir -p "$d/plc-context-floor"; ln -s "$d/no-such-target" "$d/plc-context-floor/s.marker"
rcs=""
for i in 1 2; do rcs="$rcs$(run_hook "$d" "$(ev_for "$d")")"; done
sleep 1; echo refreshed > "$d/RESUME.md"          # the ONE action the block message names
rc_after="$(run_hook "$d" "$(ev_for "$d")")"
{ [ "$rcs" = 22 ] && [ ! -e "$d/no-such-target" ] && [ "$rc_after" = 0 ]; } \
  && ok "a dangling symlink at the marker path blocks, is never written through, and STILL clears on a refresh" \
  || no "a dangling symlink at the marker path blocks, is never written through, and STILL clears on a refresh (rcs=$rcs after=$rc_after)"

# ...and when the repair itself CANNOT run -- a dangling symlink inside an unwritable marker
# directory, so the `rm` fails too -- the final fail-open test must still refuse to fail open,
# because `-e` alone is false for a dangling link. Without that last `[ ! -L ]` the permanent
# silent allow returns: measured 000 across three calls, against 222 here and 222 on an older
# hook. This row exists because the mutation that removes the guard reddens NOTHING otherwise --
# the repair branch hides it on every path where the repair can succeed, so the guard would read
# as dead code and get "cleaned up".
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
mkdir -p "$d/plc-context-floor"; ln -s "$d/no-such-target-2" "$d/plc-context-floor/s.marker"
chmod 500 "$d/plc-context-floor"
rcs=""
for i in 1 2 3; do rcs="$rcs$(run_hook "$d" "$(ev_for "$d")")"; done
chmod 700 "$d/plc-context-floor"
{ [ "$rcs" = 222 ] && [ ! -e "$d/no-such-target-2" ]; } \
  && ok "an UNREPAIRABLE symlinked marker does not fail open" \
  || no "an UNREPAIRABLE symlinked marker does not fail open (rcs=$rcs)"

# A symlink to a real checkpoint IS a checkpoint -- `-f` follows symlinks, and the multi-repo
# layout the checkpoint-resolution rows below describe makes a symlinked RESUME.md entirely plausible.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
echo current > "$d/real-resume.md"; ln -s "$d/real-resume.md" "$d/RESUME.md"
rc="$(run_hook "$d" "$(ev_for "$d")")"
[ "$rc" = 0 ] \
  && ok "a symlink to a real checkpoint counts as one: allows once" \
  || no "a symlink to a real checkpoint counts as one: allows once (rc=$rc)"

# A row was deleted here on the reasoning that `marker directory unwritable: fails open` (above)
# "already covers that path". THAT REASONING WAS WRONG, and that is why the
# dangling-symlink row above exists: the unwritable-dir row covers the BRANCH, not the CAUSE SET.
# Its cause (EACCES) agrees with an older hook; the symlink cause does not, and diverges into a
# permanent silent allow. Branch coverage is not cause coverage -- one row per branch will happily
# leave a discriminating case with nothing asserting it.

echo "-- the deadlock guard --"
# If the hook ever gates the checkpoint file, the action that clears the block cannot be performed.
# Every accepted spelling must be exempt; the existing suite only ever covered the absolute one.
for spelling in 'file_path abs' 'file_path rel' 'file_path dotrel' 'path rel'; do
  key="${spelling%% *}"; form="${spelling##* }"
  d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
  case "$form" in
    abs)    val="$d/RESUME.md" ;;
    rel)    val="RESUME.md" ;;
    dotrel) val="./RESUME.md" ;;
  esac
  ev="$(printf '{"session_id":"s","transcript_path":"%s/t.jsonl","cwd":"%s","tool_input":{"%s":"%s"}}' "$d" "$d" "$key" "$val")"
  rc="$(run_hook "$d" "$ev")"
  [ "$rc" = 0 ] && ok "writing the checkpoint is exempt: tool_input.$key = $form" \
                || no "writing the checkpoint is exempt: tool_input.$key = $form (rc=$rc)"
done

d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
ev="$(printf '{"session_id":"s","transcript_path":"%s/t.jsonl","cwd":"%s","tool_input":{"file_path":"%s/src/main.ts"}}' "$d" "$d" "$d")"
rc="$(run_hook "$d" "$ev")"
[ "$rc" = 2 ] && ok "a normal source file is NOT exempt" \
              || no "a normal source file is NOT exempt (rc=$rc)"

# The fallback chain is file_path -> path -> none, and "present but empty" must fall through. An
# implementation that stops at an empty file_path gates the checkpoint write: the deadlock again,
# reached by a different door.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
ev="$(jq -nc --arg d "$d" '{session_id:"s",transcript_path:($d+"/t.jsonl"),cwd:$d,
                            tool_input:{file_path:"",path:"RESUME.md"}}')"
rc="$(run_hook "$d" "$ev")"
[ "$rc" = 0 ] && ok "writing the checkpoint is exempt: file_path empty, path carries it" \
              || no "writing the checkpoint is exempt: file_path empty, path carries it (rc=$rc)"

echo "-- paths are bytes, not an encoding --"
# A transcript under a directory whose name contains a tab or a backslash is an ORDINARY path.
# If the hook hands it from jq to bash through an escaping encoder, the existence check fails and
# the floor quietly stops existing for that user -- no error, no block, nothing to notice.
TAB="$(printf '\t')"
for hostile in "dir${TAB}name" 'dir\name'; do
  d="$(sandbox)"; sub="$d/$hostile"; mkdir -p "$sub"; usage_line 160000 > "$sub/t.jsonl"
  ev="$(jq -nc --arg t "$sub/t.jsonl" --arg c "$d" '{session_id:"s",transcript_path:$t,cwd:$c}')"
  rc="$(run_hook "$d" "$ev")"
  [ "$rc" = 2 ] && ok "a transcript path containing [$hostile] still gates" \
                || no "a transcript path containing [$hostile] still gates (rc=$rc)"
done

# The session key becomes a filename. Under an escaping encoder a literal tab and the two
# characters backslash-t both render as `\t`, so two unrelated sessions share one marker: one
# session's checkpoint clears the other's block.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
ev="$(jq -nc --arg d "$d" '{session_id:"a\tb",transcript_path:($d+"/t.jsonl"),cwd:$d}')"
rc="$(run_hook "$d" "$ev")"
ev2="$(jq -nc --arg d "$d" '{session_id:"a\\tb",transcript_path:($d+"/t.jsonl"),cwd:$d}')"
rc2="$(run_hook "$d" "$ev2")"
n="$(ls "$d/plc-context-floor" 2>/dev/null | grep -c marker || true)"
{ [ "$rc" = 2 ] && [ "$rc2" = 2 ] && [ "$n" = 2 ]; } \
  && ok "two session ids that differ only by escaping keep separate markers" \
  || no "two session ids that differ only by escaping keep separate markers (rc=$rc rc2=$rc2 markers=$n)"

echo "-- fails open, never closed, on its own breakage --"
d="$(sandbox)"; printf '{ not json\n' > "$d/t.jsonl"
rc="$(run_hook "$d" "$(ev_for "$d")")"
[ "$rc" = 0 ] && ok "unreadable transcript: fails open" || no "unreadable transcript: fails open (rc=$rc)"

d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"; mkdir -p "$d/plc-context-floor"; chmod 500 "$d/plc-context-floor"
rc="$(run_hook "$d" "$(ev_for "$d")")"
chmod 700 "$d/plc-context-floor"
[ "$rc" = 0 ] && ok "marker directory unwritable: fails open" || no "marker directory unwritable: fails open (rc=$rc)"

d="$(sandbox)"; usage_line 900000 > "$d/t.jsonl"
printf '%s' "$(ev_for "$d")" | env -u PLC_CONTEXT_FLOOR_PCT TMPDIR="$d" PLC_CONTEXT_FLOOR=0 \
  /bin/bash "$IMPL" >/dev/null 2>&1
[ $? = 0 ] && ok "PLC_CONTEXT_FLOOR=0 disables the floor" || no "PLC_CONTEXT_FLOOR=0 disables the floor"

# A jq that dies PARTWAY through the field stream is the one failure this suite could not stage:
# every other jq breakage yields nothing at all. A truncated stream is worse than an empty one,
# because the fields that DID arrive look valid -- losing only the tool target silently deletes the
# RESUME exemption and blocks the write that clears the block. Staged with a jq stub that returns
# four of the five records and exits non-zero; everything else still reaches the real jq.
REALJQ="$(command -v jq)"
STUBDIR="$(mktemp -d "$WORK/stub.XXXXXX")"
{ printf '#!/bin/bash\ncase "$*" in\n  *pyfalsy*)\n'
  printf '    cat | "%s" -j %s\n' "$REALJQ" \
    "'[\"OK\", (.session_id // \"s\"), (.cwd // \"\"), (.transcript_path // \"\")] | .[] | (., ([0]|implode))'"
  printf '    exit 1 ;;\nesac\nexec "%s" "$@"\n' "$REALJQ"
} > "$STUBDIR/jq"
chmod +x "$STUBDIR/jq"
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
printf '%s' "$(ev_for "$d")" | env -u PLC_CONTEXT_FLOOR -u PLC_CONTEXT_FLOOR_PCT \
  -u PLC_CONTEXT_FLOOR_STEP -u PLC_CONTEXT_WINDOW -u PLC_RESUME_PATH \
  TMPDIR="$d" LC_ALL=C PATH="$STUBDIR:$PATH" /bin/bash "$IMPL" >/dev/null 2>&1
rc=$?
{ [ "$rc" = 0 ] && [ ! -e "$d/plc-context-floor/s.marker" ]; } \
  && ok "a truncated field stream fails open, it does not act on the half it got" \
  || no "a truncated field stream fails open, it does not act on the half it got (rc=$rc)"

echo "-- the block message must not ship its own bypass --"
# A guard that prints `rm <marker>` gets bypassed, and the agent taking the hint is not even
# disobeying -- it is following instructions. This regression-guards that decision.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
msg="$(printf '%s' "$(ev_for "$d")" | env -u PLC_CONTEXT_FLOOR -u PLC_CONTEXT_FLOOR_PCT TMPDIR="$d" \
        /bin/bash "$IMPL" 2>&1 >/dev/null)"
case "$msg" in
  *"rm "*|*plc-context-floor*|*marker*) no "the block message names no marker path and no rm command" ;;
  *) ok "the block message names no marker path and no rm command" ;;
esac

echo "-- dependency envelope --"
# The hook must not need python3. `grep -c python3` is the weak form of that claim; these are the
# real ones. Ordering matters: prove the fixture BLOCKS with everything present first, or a hook
# that had silently become fail-open would pass "still behaves" trivially.
mkbin() { local b t p; b="$(mktemp -d "$WORK/bin.XXXXXX")"; for t in "$@"; do
            p="$(command -v "$t" 2>/dev/null)" && ln -sf "$p" "$b/$t"; done; printf '%s' "$b"; }
reachable() { PATH="$1" /bin/bash -c "command -v $2 >/dev/null 2>&1"; }
blocks_with_path() {
  local p="$1" d; d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
  printf '%s' "$(ev_for "$d")" | env -u PLC_CONTEXT_FLOOR -u PLC_CONTEXT_FLOOR_PCT \
    -u PLC_CONTEXT_FLOOR_STEP -u PLC_CONTEXT_WINDOW -u PLC_RESUME_PATH \
    TMPDIR="$d" LC_ALL=C PATH="$p" /bin/bash "$IMPL" >/dev/null 2>&1
  printf '%s' $?
}

if grep -nE '(^|[^#[:alnum:]_])(python3?|/usr/bin/python3?|/usr/local/bin/python3?)' "$IMPL" \
     | grep -vE ':[[:space:]]*#' | grep -qvE '#.*python'; then
  no "no python interpreter is invoked (static, incl. absolute paths)"
else
  ok "no python interpreter is invoked (static, incl. absolute paths)"
fi

BIN_FULL="$(mkbin jq stat cat mkdir rm tr tail)"
BIN_NOJQ="$(mkbin    stat cat mkdir rm tr tail)"
if reachable "$BIN_FULL" python3; then
  no "envelope probe is valid (python3 really is unreachable on the probe PATH)"
else
  ok "envelope probe is valid (python3 really is unreachable on the probe PATH)"

  [ "$(blocks_with_path "$BIN_FULL")" = 2 ] \
    && ok "blocks with python3 unreachable (the envelope is genuinely closed)" \
    || no "blocks with python3 unreachable (the envelope is genuinely closed)"

  if reachable "$BIN_NOJQ" jq; then
    no "jq-absent probe is valid (jq really is unreachable)"
  else
    ok "jq-absent probe is valid (jq really is unreachable)"
    # Fails open by design -- but that means a machine without jq has an inert floor, which is
    # why the arming path warns separately. Paired with the row above, which proves the same
    # fixture blocks when jq IS present, so this is not a fail-open impersonating a pass.
    [ "$(blocks_with_path "$BIN_NOJQ")" = 0 ] \
      && ok "jq unreachable: fails open rather than blocking forever" \
      || no "jq unreachable: fails open rather than blocking forever"
  fi
fi

# =============================================================================
# CHECKPOINT RESOLUTION anchors on the FILE BEING WRITTEN, not the session cwd.
#
# The event's `.cwd` follows the agent's `cd`, so a cwd-resolved checkpoint changes identity as
# the session moves between sibling repos and "refresh the RESUME.md you just wrote" stops
# clearing the block. Edit/Write always carries a file_path; that is the one field in the event
# that says which project is being touched RIGHT NOW.
#
# Resolution order under test: PLC_RESUME_PATH -> git toplevel of the target's dir -> $CWD.
#
# NOTE ON PATHS -- do not assert literal absolute strings here. Measured on macOS:
# `git rev-parse --show-toplevel` returns the PHYSICALLY resolved path, so a sandbox that
# mktemp spells `/var/folders/...` comes back as `/private/var/folders/...`, and a symlinked
# repo alias resolves to its real root. Both spell the same file, so `stat` is unaffected and
# the mtime comparison is unaffected -- but a fixture comparing strings would be asserting the
# platform, not the contract. Every row below asserts on BEHAVIOUR (did it clear?) or on a
# repo-relative substring.
# =============================================================================
echo
echo "-- checkpoint resolution anchors on the target --"

if ! command -v git >/dev/null 2>&1; then
  no "checkpoint-resolution rows require git on PATH (envelope is bash + git + jq + coreutils)"
else

# Build a git repo at $1 with a src/ subdir. Templates and global config are neutralised so an
# adopter's own git setup cannot leak into the fixture.
mkrepo() {
  mkdir -p "$1/src"
  GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null \
    git -C "$1" init -q --template= 2>/dev/null
}

# Event carrying an explicit cwd AND a tool target. $1 sandbox (for the transcript), $2 cwd,
# $3 target file_path (absolute or relative -- relative is the point of the AC7 row).
ev_t() {
  jq -nc --arg t "$1/t.jsonl" --arg c "$2" --arg f "$3" \
    '{session_id:"s",transcript_path:$t,cwd:$c,tool_input:{file_path:$f}}'
}

# Like run_hook, but returns the STDERR text instead of the exit code.
msg_hook() {
  printf '%s' "$2" | env -u PLC_CONTEXT_FLOOR -u PLC_CONTEXT_FLOOR_PCT -u PLC_CONTEXT_FLOOR_STEP \
      -u PLC_CONTEXT_WINDOW -u PLC_RESUME_PATH TMPDIR="$1" LC_ALL=C \
      /bin/bash "$IMPL" 2>&1 >/dev/null
}

# --- AC2: a target inside a repo resolves to that repo's root, whatever cwd says -------------
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
mkrepo "$d/repoA"; mkdir -p "$d/neutral"
arm_old "$d"
echo fresh > "$d/repoA/RESUME.md"          # the ONLY RESUME.md in the sandbox
rc="$(run_hook "$d" "$(ev_t "$d" "$d/neutral" "$d/repoA/src/f.txt")")"
[ "$rc" = 0 ] \
  && ok "AC2 target inside a repo resolves to that repo's RESUME.md, not cwd's" \
  || no "AC2 target inside a repo resolves to that repo's RESUME.md, not cwd's (rc=$rc)"

# --- AC2b: cwd is an ANCESTOR of the repo, and the ancestor has its own checkpoint -----------
# This is a realistic scenario, and the one every other row here misses: the rows
# above put cwd in a SIBLING directory, where almost any resolution strategy looks right. The
# multi-repo workspace layout `<workspace>/{repoA,repoB,...}` can put the session cwd at the workspace
# ROOT -- and a RESUME.md placed there as a workaround means the ancestor's
# checkpoint exists and is fresh. A resolver that shortcuts on "the target is somewhere under
# cwd, and cwd has a RESUME.md" therefore answers with the workspace file and reproduces the defect
# exactly, while passing every sibling-cwd row. That shortcut is the reason this row exists.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
mkdir -p "$d/ws"; mkrepo "$d/ws/repoA"
: > "$d/ws/repoA/RESUME.md"                # the repo's own checkpoint, written BEFORE the
arm_old "$d"                               # marker, so it is genuinely stale
echo fresh > "$d/ws/RESUME.md"             # the workspace-root workaround, fresh
rc="$(run_hook "$d" "$(ev_t "$d" "$d/ws" "$d/ws/repoA/src/f.txt")")"
[ "$rc" = 2 ] \
  && ok "AC2b an ancestor cwd's checkpoint does not stand in for the edited repo's" \
  || no "AC2b an ancestor cwd's checkpoint does not stand in for the edited repo's (rc=$rc)"

# --- AC3a: target in no repo at all -> falls back to \$CWD, byte-identical to today ----------
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
mkdir -p "$d/plain"
arm_old "$d"
echo fresh > "$d/RESUME.md"                # cwd's checkpoint; no repo anywhere
rc="$(run_hook "$d" "$(ev_t "$d" "$d" "$d/plain/f.txt")")"
[ "$rc" = 0 ] \
  && ok "AC3a target outside any repo falls back to \$CWD/RESUME.md" \
  || no "AC3a target outside any repo falls back to \$CWD/RESUME.md (rc=$rc)"

# The same call must not leak git's own diagnostics. `git rev-parse` prints `fatal: not a git
# repository` on every miss, and this is a PreToolUse hook -- its stderr reaches the user.
# (Redirections apply left to right, so a misplaced 2>/dev/null lets the first
# diagnostic escape before it takes effect.)
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
mkdir -p "$d/plain"; arm_old "$d"; echo fresh > "$d/RESUME.md"
m="$(msg_hook "$d" "$(ev_t "$d" "$d" "$d/plain/f.txt")")"
case "$m" in
  *fatal:*|*"not a git repository"*) no "AC3a no git diagnostic leaks to the user's stderr" ;;
  *) ok "AC3a no git diagnostic leaks to the user's stderr" ;;
esac

# --- AC3b: the target's directory does not exist yet (Write creating a new tree) -------------
# Measured: `git -C <missing>` exits non-zero with `fatal: cannot change to ...`.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
arm_old "$d"; echo fresh > "$d/RESUME.md"
rc="$(run_hook "$d" "$(ev_t "$d" "$d" "$d/nodir/deep/f.txt")")"
[ "$rc" = 0 ] \
  && ok "AC3b a target whose directory does not exist falls back, it does not wedge" \
  || no "AC3b a target whose directory does not exist falls back, it does not wedge (rc=$rc)"

# --- AC3c: git itself unreachable -> same fallback, never a hard failure ---------------------
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
mkrepo "$d/repoA"; arm_old "$d"; echo fresh > "$d/RESUME.md"
NOGIT="$(mkbin jq stat cat mkdir rm tr tail)"        # deliberately no git
rc="$(printf '%s' "$(ev_t "$d" "$d" "$d/repoA/src/f.txt")" \
      | env -u PLC_CONTEXT_FLOOR -u PLC_CONTEXT_FLOOR_PCT -u PLC_CONTEXT_FLOOR_STEP \
            -u PLC_CONTEXT_WINDOW -u PLC_RESUME_PATH TMPDIR="$d" LC_ALL=C PATH="$NOGIT" \
            /bin/bash "$IMPL" >/dev/null 2>&1; printf '%s' $?)"
[ "$rc" = 0 ] \
  && ok "AC3c git unreachable falls back to \$CWD rather than failing the call" \
  || no "AC3c git unreachable falls back to \$CWD rather than failing the call (rc=$rc)"

# --- AC7: a RELATIVE target is made absolute against the EVENT cwd, not the process cwd ------
# This is a known divergence class recurring: the hook already resolves the tool target
# against the event cwd but a relative PLC_RESUME_PATH against the PROCESS cwd, and a naive
# `git -C "$(dirname "$TARGET")"` on a relative path silently introduces a THIRD base.
#
# The fixture discriminates because the process cwd is never repoA (every call runs from a fresh
# harness-owned run directory). Resolving
# against the process cwd therefore finds no fresh checkpoint and blocks; resolving
# against the event cwd lands on repoA's fresh one and clears.
#
# The event cwd is the repo's SUBDIRECTORY, not its root, and only the root carries a
# RESUME.md. That is deliberate: with cwd at the root, today's cwd-resolution would clear this
# too and the row would pass without testing anything -- an inert fixture that looks like
# coverage. Pointing cwd one level down makes today's behaviour block and only correct
# target-anchored resolution clear.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
mkrepo "$d/repoA"; arm_old "$d"
echo fresh > "$d/repoA/RESUME.md"          # at the ROOT; repoA/src has none
rc="$(run_hook "$d" "$(ev_t "$d" "$d/repoA/src" "f.txt")")"
[ "$rc" = 0 ] \
  && ok "AC7 a relative target is resolved against the EVENT cwd, not the process cwd" \
  || no "AC7 a relative target is resolved against the EVENT cwd, not the process cwd (rc=$rc)"

# --- AC8: a repo reached through a symlinked root still finds the same checkpoint ------------
# Pins the canonicalisation rather than inheriting whatever the test machine happens to do.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
mkrepo "$d/repoA"; mkdir -p "$d/neutral"; ln -s "$d/repoA" "$d/aliasA"
arm_old "$d"
echo fresh > "$d/repoA/RESUME.md"
rc="$(run_hook "$d" "$(ev_t "$d" "$d/neutral" "$d/aliasA/src/f.txt")")"
[ "$rc" = 0 ] \
  && ok "AC8 a symlinked repo root resolves to the same checkpoint (no deadlock)" \
  || no "AC8 a symlinked repo root resolves to the same checkpoint (no deadlock) (rc=$rc)"

# --- AC6: the block message names the resolved checkpoint, and still ships no bypass ---------
# After AC2 the checkpoint can no longer be guessed as `./RESUME.md`, so withholding it would
# recreate the original failure mode from a new cause: the agent does not know where to write.
# This is the OPPOSITE disclosure from the marker path -- that one is the guard's own state and
# naming it once led an agent to `rm` it. The second case below regression-guards that.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
mkrepo "$d/repoA"; mkdir -p "$d/neutral"      # repoA deliberately has NO RESUME.md
m="$(msg_hook "$d" "$(ev_t "$d" "$d/neutral" "$d/repoA/src/f.txt")")"
case "$m" in
  *repoA/RESUME.md*) ok "AC6 the block message names the resolved checkpoint path" ;;
  *) no "AC6 the block message names the resolved checkpoint path" ;;
esac
case "$m" in
  *"rm "*|*plc-context-floor*|*.marker*) no "AC6 the block message still names no marker path and no rm" ;;
  *) ok "AC6 the block message still names no marker path and no rm" ;;
esac

# --- AC9: spawn discipline -------------------------------------------------------------------
# Resolution happens BEFORE the occupancy gate, so it runs on every Edit/Write, not just
# over-floor ones. Measured: ~17 ms per rev-parse. Per-turn spawn growth has caused real
# resource exhaustion (EAGAIN, OOM kills) on a busy machine, so "how often does
# this fork" is a contract, not an optimisation.
#
# AC9 was originally written as a "fast path" contract: skip git when the target is under cwd and
# cwd has a RESUME.md. That heuristic was DROPPED -- see AC2b. In a multi-repo workspace
# layout the repo IS under cwd and cwd DOES have a RESUME.md, so the fast path would have fired
# on precisely the case checkpoint resolution is about and answered with the workspace file. A shortcut that is
# wrong exactly where the bug lives is worse than the fork it saves.
#
# What is asserted instead is the sound half of the same concern: git is invoked AT MOST ONCE per
# call, and not at all on the two paths that cannot need it -- an explicit PLC_RESUME_PATH, and
# an event with no tool target.
SHIM="$(mktemp -d "$WORK/gitshim.XXXXXX")"
{ printf '#!/bin/sh\n'
  printf 'printf "%%s\\n" "$*" >> "$GIT_SHIM_LOG"\n'
  printf 'exit 1\n'; } > "$SHIM/git"
chmod +x "$SHIM/git"

run_shimmed() {   # $1 sandbox, $2 log path, $3 event, $4.. extra env assignments
  local d="$1" log="$2" ev="$3"; shift 3
  printf '%s' "$ev" | env -u PLC_CONTEXT_FLOOR -u PLC_CONTEXT_FLOOR_PCT -u PLC_CONTEXT_FLOOR_STEP \
        -u PLC_CONTEXT_WINDOW -u PLC_RESUME_PATH TMPDIR="$d" LC_ALL=C \
        GIT_SHIM_LOG="$log" PATH="$SHIM:$PATH" "$@" /bin/bash "$IMPL" >/dev/null 2>&1
}

# Control first: with a target that needs resolving, git IS reached exactly once. Ordering
# matters -- prove the probe is live before reading anything into an empty log below.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
mkdir -p "$d/elsewhere" "$d/neutral"; arm_old "$d"; echo fresh > "$d/RESUME.md"
LOG="$d/gitcalls.log"; : > "$LOG"
run_shimmed "$d" "$LOG" "$(ev_t "$d" "$d/neutral" "$d/elsewhere/f.txt")"
n="$(wc -l < "$LOG" | tr -d ' ')"
[ "$n" = 1 ] \
  && ok "AC9 a target that needs resolving reaches git exactly once (the probe is live)" \
  || no "AC9 a target that needs resolving reaches git exactly once (got $n call(s))"

# An explicit checkpoint path cannot need resolution.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
mkdir -p "$d/elsewhere"; arm_old "$d"; echo fresh > "$d/pinned.md"
LOG="$d/gitcalls.log"; : > "$LOG"
run_shimmed "$d" "$LOG" "$(ev_t "$d" "$d" "$d/elsewhere/f.txt")" PLC_RESUME_PATH="$d/pinned.md"
[ ! -s "$LOG" ] \
  && ok "AC9 an explicit PLC_RESUME_PATH spawns no git at all" \
  || no "AC9 an explicit PLC_RESUME_PATH spawns no git at all ($(wc -l < "$LOG") call(s))"

# No tool target means nothing to anchor on; the cwd fallback needs no subprocess.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
arm_old "$d"; echo fresh > "$d/RESUME.md"
LOG="$d/gitcalls.log"; : > "$LOG"
run_shimmed "$d" "$LOG" "$(ev_for "$d")"
[ ! -s "$LOG" ] \
  && ok "AC9 an event with no tool target spawns no git at all" \
  || no "AC9 an event with no tool target spawns no git at all ($(wc -l < "$LOG") call(s))"

# --- AC4 / AC5: the two assertions that replace the old single row -----------------------
# The row these supersede created repoA and repoB with no .git dirs, no nesting, a transcript
# outside both, and an event with no tool_input -- supplying NO signal connecting the event to
# repoA. Anything satisfying it had to treat "refresh any RESUME.md anywhere" as clearing "any
# blocked repo anywhere", i.e. one `touch` defeats the floor machine-wide. That is a strictly
# WEAKER guarantee than the hook already gives, so the row was rewritten rather than satisfied.
# Both halves are needed: the positive alone is satisfied by a hook that never blocks.

# AC4 positive -- cwd wanders out of the repo, the target does not.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
mkrepo "$d/repoA"; mkdir -p "$d/neutral"     # cwd is neither repoA nor repoB: see AC5
ev="$(ev_t "$d" "$d/neutral" "$d/repoA/src/deep/file.py")"
rc1="$(run_hook "$d" "$ev")"                 # call 1: arms and blocks (no checkpoint yet)
sleep 1; echo fresh > "$d/repoA/RESUME.md"   # the human does the obviously-correct thing
rc2="$(run_hook "$d" "$ev")"                 # call 2: must clear
{ [ "$rc1" = 2 ] && [ "$rc2" = 0 ]; } \
  && ok "AC4 refreshing the EDITED repo's checkpoint clears the block (cwd elsewhere)" \
  || no "AC4 refreshing the EDITED repo's checkpoint clears the block (rc1=$rc1 rc2=$rc2)"

# AC5 negative -- the half the old row never covered. Once the target has genuinely moved to an
# unrelated repo, neither repoA's checkpoint nor cwd's may speak for repoB.
#
# cwd gets its OWN fresh RESUME.md, refreshed AFTER the marker is armed. Without that this row
# passes today for the wrong reason (it blocks because `neutral/` simply has no checkpoint), and
# a fixture that is green before the fix is a fixture that is not testing the fix. With it,
# today's cwd-resolution finds a fresh checkpoint and CLEARS -- so the row is red until
# resolution is anchored on the target, which is the whole point.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
mkrepo "$d/repoA"; mkrepo "$d/repoB"; mkdir -p "$d/neutral"
echo fresh > "$d/repoA/RESUME.md"            # A is checkpointed; B never has been
evB="$(ev_t "$d" "$d/neutral" "$d/repoB/src/x.py")"
rc1="$(run_hook "$d" "$evB")"                # arms against repoB
sleep 1
touch "$d/repoA/RESUME.md"                   # refresh the WRONG repo ...
echo fresh > "$d/neutral/RESUME.md"          # ... and the session's cwd, also wrong
rc2="$(run_hook "$d" "$evB")"
{ [ "$rc1" = 2 ] && [ "$rc2" = 2 ]; } \
  && ok "AC5 refreshing another repo's or cwd's checkpoint does NOT clear a block armed for repo B" \
  || no "AC5 refreshing another repo's or cwd's checkpoint does NOT clear a block armed for repo B (rc1=$rc1 rc2=$rc2)"

# --- AC8b: the symlinked-checkout exemption (refuted-but-pinned) --------
# git returns the PHYSICALLY resolved root, the
# RESUME-write exemption compares paths as STRINGS, so with cwd and the target both spelled
# through a symlink the absolute-match branch misses and "refreshing the checkpoint gets gated"
# -- a deadlock.
#
# Measured: it does not happen, and not by luck. The absolute branch does miss. The BASENAME
# branch then catches it unconditionally, because a git-resolved checkpoint is `$TOP/RESUME.md`
# by construction and therefore always ends in `RESUME.md`. The hedge ("unless the
# basename escape happens to catch it") resolves to "it always does".
#
# The row exists anyway. A refuted finding that is not pinned is a finding that comes back, and
# anyone who later tightens the basename branch -- which is generous on purpose -- needs this to
# turn red rather than to rediscover the argument.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
mkdir -p "$d/real"; mkrepo "$d/real/repo"; ln -s "$d/real/repo" "$d/link"
rc="$(run_hook "$d" "$(ev_t "$d" "$d/link" "$d/link/RESUME.md")")"
[ "$rc" = 0 ] \
  && ok "AC8b writing the checkpoint through a symlinked checkout is still exempt" \
  || no "AC8b writing the checkpoint through a symlinked checkout is still exempt (rc=$rc)"

# --- AC3d: a slashless relative target (refuted-but-pinned) --------------
# `${ABS_TARGET%/*}` computes no parent for a path with no slash, so the
# walk spins to its bound and git then runs against the hook PROCESS's directory.
#
# Measured: unreachable. A relative target is prefixed with `$CWD/`, so ABS_TARGET always carries
# a slash; and `$CWD` cannot be empty by the time this runs, because it is backfilled from
# `pwd -P` above. Even forcing `cwd` to "" in the event, the hook blocks normally and does not
# hang. Pinned because both of those are load-bearing invariants that live far from this code.
#
# THIS ROW USED TO PASS A THIRD ARGUMENT to `run_hook`, and the parameter was deleted. Recorded so
# nobody "restores" it: `cwd:""` is precisely the input that sends the hook to its `pwd -P` backfill,
# so the row is only meaningful when the process cwd has NO `RESUME.md`. It used to buy that by
# running from `$d`; it now gets it from the shared default, because every call runs from a
# freshly-created harness-owned run directory. That is STRICTLY stronger -- `$d` is a sandbox this
# row has already written fixtures into, while the run directory is empty by construction.
#
# MEASURED at the branch point, by runtime instrumentation rather than by reading: 66 invocations per
# contract run, 65 on the shared default, and this was the ONLY explicit one. The relative-path
# escape it used to be the sole witness for is now caught on all 66 calls, and the "do not run the
# suite from the repository root" half is asserted directly by its own row instead of as a side
# effect of this one.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
rc="$(run_hook "$d" "$(jq -nc --arg t "$d/t.jsonl" \
        '{session_id:"s",transcript_path:$t,cwd:"",tool_input:{file_path:"foo"}}')")"
[ "$rc" = 2 ] \
  && ok "AC3d a slashless relative target with an empty cwd blocks normally, it does not wedge" \
  || no "AC3d a slashless relative target with an empty cwd blocks normally, it does not wedge (rc=$rc)"

# --- AC3e: a deep nonexistent path still reaches its repo (CONFIRMED) ----
# The walk's iteration counter was 64, which made it a
# SEMANTIC cutoff rather than a backstop. A target more than 64 nonexistent components deep
# stopped the walk early, git failed, and resolution dropped back to `$CWD` -- reintroducing this
# resolution defect on a deep path. The bound is now far above any reachable component count.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
mkrepo "$d/repoA"; mkdir -p "$d/neutral"
arm_old "$d"
echo fresh > "$d/repoA/RESUME.md"          # only the repo has a checkpoint
deep="$d/repoA"; i=0
while [ "$i" -lt 70 ]; do deep="$deep/d$i"; i=$((i+1)); done
rc="$(run_hook "$d" "$(ev_t "$d" "$d/neutral" "$deep/f.txt")")"
[ "$rc" = 0 ] \
  && ok "AC3e a target 70 nonexistent levels deep still resolves to its repo" \
  || no "AC3e a target 70 nonexistent levels deep still resolves to its repo (rc=$rc)"

# --- AC2c: git-root resolution, NOT "walk up to the first RESUME.md you find" ----------------
# The header rejects name-walking on the grounds that a stale leftover checkpoint in an
# intermediate directory would satisfy the search and mask that the repo has never been
# checkpointed. Nothing asserted the difference: every other row places the only RESUME.md at the
# repo root, where git-root resolution and a name-walk agree, so a regression to name-walking
# would have passed all of them.
#
# Here they disagree. A STALE checkpoint sits in an intermediate directory between the target and
# the repo root, and the FRESH one is at the root. Name-walking finds the stale one first and
# blocks; git-root resolution reaches the fresh one and clears.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
mkrepo "$d/repoA"; mkdir -p "$d/repoA/sub/deeper" "$d/neutral"
: > "$d/repoA/sub/RESUME.md"               # the decoy, written BEFORE the marker
arm_old "$d"
echo fresh > "$d/repoA/RESUME.md"          # the real one, at the git root
rc="$(run_hook "$d" "$(ev_t "$d" "$d/neutral" "$d/repoA/sub/deeper/f.txt")")"
[ "$rc" = 0 ] \
  && ok "AC2c resolution uses the git root, not the nearest RESUME.md by name" \
  || no "AC2c resolution uses the git root, not the nearest RESUME.md by name (rc=$rc)"

# --- AC2d: a target that names a DIRECTORY keeps its own root -------------------------------
# `%/*` strips one component unconditionally, which assumes a leaf file. A target naming a repo
# root had that root stripped and resolved against the parent -- usually not a repo at all, so
# resolution fell back to cwd while the correct checkpoint sat one level below where the walk
# started. Real Edit/Write never names a directory; nothing here relied on that.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
mkrepo "$d/repoD"; mkdir -p "$d/neutral"
arm_old "$d"
echo fresh > "$d/repoD/RESUME.md"
rc="$(run_hook "$d" "$(ev_t "$d" "$d/neutral" "$d/repoD")")"
[ "$rc" = 0 ] \
  && ok "AC2d a target naming a directory resolves from that directory, not its parent" \
  || no "AC2d a target naming a directory resolves from that directory, not its parent (rc=$rc)"

# --- AC3f: a RELATIVE event cwd is resolved once, against the hook process -------------------
# Claude Code sends an absolute `.cwd`, so this is defence, not a fix. Without it `git -C`,
# `stat` and the string-comparing exemption each resolve a relative cwd separately -- the
# multiple-bases class this file has already paid for twice. Asserting the guard exists.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
arm_old "$d"; echo fresh > "$d/RESUME.md"
rc="$(printf '%s' "$(jq -nc --arg t "$d/t.jsonl" --arg f "$d/x/f.txt" \
        '{session_id:"s",transcript_path:$t,cwd:"some/relative/dir",tool_input:{file_path:$f}}')" \
      | env -u PLC_CONTEXT_FLOOR -u PLC_CONTEXT_FLOOR_PCT -u PLC_CONTEXT_FLOOR_STEP \
            -u PLC_CONTEXT_WINDOW -u PLC_RESUME_PATH TMPDIR="$d" LC_ALL=C \
            /bin/bash "$IMPL" >/dev/null 2>&1; printf '%s' $?)"
[ "$rc" = 2 ] \
  && ok "AC3f a relative event cwd blocks deterministically, it does not wedge or vary" \
  || no "AC3f a relative event cwd blocks deterministically, it does not wedge or vary (rc=$rc)"

# --- AC1: an explicit PLC_RESUME_PATH still wins over everything above -----------------------
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
mkrepo "$d/repoA"; mkdir -p "$d/neutral"
arm_old "$d"
echo fresh > "$d/pinned.md"                  # only the pinned file is fresh
: > "$d/repoA/RESUME.md"                     # repo checkpoint exists but is OLDER than the marker
rc="$(printf '%s' "$(ev_t "$d" "$d/neutral" "$d/repoA/src/f.txt")" \
      | env -u PLC_CONTEXT_FLOOR -u PLC_CONTEXT_FLOOR_PCT -u PLC_CONTEXT_FLOOR_STEP \
            -u PLC_CONTEXT_WINDOW TMPDIR="$d" LC_ALL=C PLC_RESUME_PATH="$d/pinned.md" \
            /bin/bash "$IMPL" >/dev/null 2>&1; printf '%s' $?)"
[ "$rc" = 0 ] \
  && ok "AC1 an explicit PLC_RESUME_PATH still outranks git resolution" \
  || no "AC1 an explicit PLC_RESUME_PATH still outranks git resolution (rc=$rc)"

fi   # git available

# =============================================================================
# KNOWN-DEFECT rows -- each began as the executable form of a defect this gate did not honour.
# The ones marked FIXED have graduated to live rows.
# =============================================================================
# --- FIXED: a malformed usage record must not erase a later valid occupancy -----------------
# Deliberately keeps the ORDER that matters: the bad record comes FIRST, so
# an implementation that merely checks jq's exit status still passes -- jq reports only its LAST
# input. The second row puts it after, which is the ordering that also survives a streamed stdout.
d="$(sandbox)"; { usage_line '"abc"'; usage_line 160000; } > "$d/t.jsonl"
rc="$(run_hook "$d" "$(ev_for "$d")")"
[ "$rc" = 2 ] && ok "a malformed usage record does not erase a later valid over-floor occupancy" \
              || no "a malformed usage record does not erase a later valid over-floor occupancy (rc=$rc)"
d="$(sandbox)"; { usage_line 160000; usage_line '"abc"'; } > "$d/t.jsonl"
rc="$(run_hook "$d" "$(ev_for "$d")")"
[ "$rc" = 2 ] && ok "a malformed usage record AFTER a valid one does not erase it either" \
              || no "a malformed usage record AFTER a valid one does not erase it either (rc=$rc)"

# --- FIXED: a present-but-falsy session_id keeps its own state ------------------------------
# Two clauses, both load-bearing: both calls must block, AND there must be
# TWO markers. An implementation that blocked both while still sharing one key passes an rc-only
# assertion and leaves the collision in place.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
rc="$(run_hook "$d" "$(jq -nc --arg d "$d" '{transcript_path:($d+"/t.jsonl"),cwd:$d}')")"
rc2="$(run_hook "$d" "$(jq -nc --arg d "$d" '{session_id:0,transcript_path:($d+"/t.jsonl"),cwd:$d}')")"
n="$(ls "$d/plc-context-floor" 2>/dev/null | grep -c marker || true)"
{ [ "$rc" = 2 ] && [ "$rc2" = 2 ] && [ "$n" = 2 ]; } \
  && ok "a falsy session_id keeps its own state, separate from a session with no id" \
  || no "a falsy session_id keeps its own state, separate from a session with no id (rc=$rc rc2=$rc2 markers=$n)"
# ...and the CONSEQUENCE: the grace window an id-less session earns must not be spendable by a
# falsy-id one. Measured on the pre-port python implementation: it exits 0 there, i.e. walks through the floor.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
mkdir -p "$d/plc-context-floor"; echo 155000 > "$d/plc-context-floor/nosession.clearedat"
: > "$d/plc-context-floor/nosession.marker"
rc="$(run_hook "$d" "$(jq -nc --arg d "$d" '{session_id:0,transcript_path:($d+"/t.jsonl"),cwd:$d}')")"
[ "$rc" = 2 ] && ok "a falsy session_id cannot spend a grace window earned by an id-less session" \
              || no "a falsy session_id cannot spend a grace window earned by an id-less session (rc=$rc)"

# --- FIXED: the session key is interpolated into a PATH, so it must be path-safe -------
# Both of these were measured on the PINNED PYTHON REFERENCE too -- inherited, not port damage.
# A slash implied a subdirectory that `mkdir -p` never created, so the marker write failed and
# the hook FAILED OPEN: exit 0, nothing written, the floor silently off for that whole session,
# while a normal id on identical input exits 2.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
rc="$(run_hook "$d" "$(jq -nc --arg d "$d" '{session_id:"a/b",transcript_path:($d+"/t.jsonl"),cwd:$d}')")"
n="$(ls "$d/plc-context-floor" 2>/dev/null | grep -c marker || true)"
{ [ "$rc" = 2 ] && [ "$n" = 1 ]; } \
  && ok "a session_id containing '/' still blocks and arms a marker (no silent fail-open)" \
  || no "a session_id containing '/' must not disable the floor (rc=$rc markers=$n)"

# ...and `..` resolved OUT of the marker directory: the hook wrote `escape.marker` into the
# PARENT. Both halves are asserted, because an implementation that blocks while still writing
# outside its own state directory passes an rc-only check.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
rc="$(run_hook "$d" "$(jq -nc --arg d "$d" '{session_id:"../escape",transcript_path:($d+"/t.jsonl"),cwd:$d}')")"
outside="$(ls "$d" 2>/dev/null | grep -c '\.marker$' || true)"
# ls -A, not ls: the encoded name is `..%2Fescape.marker`, which begins with a dot and is
# therefore INVISIBLE to a bare `ls`. The first version of this row asserted inside=1 and read
# 0 -- the assertion was wrong, not the hook.
inside="$(ls -A "$d/plc-context-floor" 2>/dev/null | grep -c marker || true)"
{ [ "$rc" = 2 ] && [ "$outside" = 0 ] && [ "$inside" = 1 ]; } \
  && ok "a session_id containing '..' cannot write outside the marker directory" \
  || no "'..' in a session_id escaped the marker dir (rc=$rc outside=$outside inside=$inside)"

# --- sentinel half: a real id must never land on a sentinel's key --------------------------
# The remaining half of the path-safety fix. The six sentinel tokens and the encoded ids shared ONE flat namespace,
# so a session whose id is the literal string "nosession" keyed the same marker as a session with no
# id at all, and "falsy-number-0" the same as `0`. Two sessions on one marker means either one's
# checkpoint clears the other's block.
#
# EVERY ROW HERE ASSERTS THE FILESYSTEM, NOT JUST `rc`. Both members of a colliding pair block, so an
# rc-only row is satisfied by the defect itself -- the same trap the falsy-session_id row above names, and the same
# one CF-AC9 records after `rc=0` alone passed a hook with the grace window disabled outright.
marker_names() {        # $1 sandbox -> sorted marker basenames, one per line
  ls -A "$1/plc-context-floor" 2>/dev/null | grep 'marker$' | sort || true
}

d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
rc1="$(run_hook "$d" "$(jq -nc --arg d "$d" '{session_id:0,transcript_path:($d+"/t.jsonl"),cwd:$d}')")"
rc2="$(run_hook "$d" "$(jq -nc --arg d "$d" '{session_id:"falsy-number-0",transcript_path:($d+"/t.jsonl"),cwd:$d}')")"
n="$(marker_names "$d" | wc -l | tr -d ' ')"
{ [ "$rc1" = 2 ] && [ "$rc2" = 2 ] && [ "$n" = 2 ]; } \
  && ok "session_id 0 and the literal string \"falsy-number-0\" keep separate state" \
  || no "session_id 0 and the literal string \"falsy-number-0\" share a key (rc=$rc1/$rc2 markers=$n: $(marker_names "$d" | tr '\n' ' '))"

d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
rc1="$(run_hook "$d" "$(jq -nc --arg d "$d" '{transcript_path:($d+"/t.jsonl"),cwd:$d}')")"
rc2="$(run_hook "$d" "$(jq -nc --arg d "$d" '{session_id:"nosession",transcript_path:($d+"/t.jsonl"),cwd:$d}')")"
n="$(marker_names "$d" | wc -l | tr -d ' ')"
{ [ "$rc1" = 2 ] && [ "$rc2" = 2 ] && [ "$n" = 2 ]; } \
  && ok "an absent session_id and the literal string \"nosession\" keep separate state" \
  || no "an absent session_id and the literal string \"nosession\" share a key (rc=$rc1/$rc2 markers=$n: $(marker_names "$d" | tr '\n' ' '))"

# ...and the CONSEQUENCE, which is the half that costs a user something: the grace window one member
# of the pair earns must not be spendable by the other.
#
# THE SEQUENCE IS NOT ARBITRARY, and the obvious shorter one is WRONG. "Let A clear by refreshing the
# checkpoint, then check B still blocks" cannot work: the checkpoint is one file shared by the whole
# repo, so refreshing it legitimately clears B as well, and the resulting `rc=0` says nothing about
# keys. That confound once produced a false "reproduced" and is written down here so the
# row is not "simplified" back into it. B's marker is therefore armed AFTER the refresh, which leaves
# spending A's grace as the ONLY path to an allow.
#
# Nor is the grace record seeded by hand: seeding needs the key's spelling, i.e. a second copy of the
# derivation under test, and post-change a hand-seeded file would simply go unread and the row would
# pass for the wrong reason.
grace_leak_case() {     # $1 label, $2 jq event program for A, $3 jq event program for B
  local d rcb1 rcb2
  d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
  run_hook "$d" "$(jq -nc --arg d "$d" "$2")" >/dev/null      # A: arms, blocks
  echo fresh > "$d/RESUME.md"
  run_hook "$d" "$(jq -nc --arg d "$d" "$2")" >/dev/null      # A: clears, EARNS the grace window
  rcb1="$(run_hook "$d" "$(jq -nc --arg d "$d" "$3")")"       # B: first call, arms (allows once)
  rcb2="$(run_hook "$d" "$(jq -nc --arg d "$d" "$3")")"       # B: marker now newer than checkpoint
  [ "$rcb2" = 2 ] \
    && ok "$1" \
    || no "$1 (B's second call exited $rcb2, first=$rcb1 -- it spent a window it did not earn)"
}
grace_leak_case "the literal string \"falsy-number-0\" cannot spend a window earned by session_id 0" \
  '{session_id:0,transcript_path:($d+"/t.jsonl"),cwd:$d}' \
  '{session_id:"falsy-number-0",transcript_path:($d+"/t.jsonl"),cwd:$d}'
grace_leak_case "the literal string \"nosession\" cannot spend a window earned by an id-less session" \
  '{transcript_path:($d+"/t.jsonl"),cwd:$d}' \
  '{session_id:"nosession",transcript_path:($d+"/t.jsonl"),cwd:$d}'

# --- the six sentinel spellings, pinned as literal text ---------------------------------
# A harness that blesses whatever the hook actually produced CANNOT supply this:
# a typo in a token is absorbed as the new ground truth and every count stays green.
# Counting markers cannot see a misspelling either -- the falsy-session_id row above counts, deliberately, because
# it is asking a different question. This row asks: are the six keys the six strings we chose?
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
for prog in '{transcript_path:($d+"/t.jsonl"),cwd:$d}' \
            '{session_id:false,transcript_path:($d+"/t.jsonl"),cwd:$d}' \
            '{session_id:0,transcript_path:($d+"/t.jsonl"),cwd:$d}' \
            '{session_id:"",transcript_path:($d+"/t.jsonl"),cwd:$d}' \
            '{session_id:[],transcript_path:($d+"/t.jsonl"),cwd:$d}' \
            '{session_id:{},transcript_path:($d+"/t.jsonl"),cwd:$d}'; do
  run_hook "$d" "$(jq -nc --arg d "$d" "$prog")" >/dev/null
done
got="$(marker_names "$d" | tr '\n' ' ')"
want="$(printf '%s\n' '%~falsy-array-empty.marker' '%~falsy-boolean-false.marker' \
                      '%~falsy-number-0.marker' '%~falsy-object-empty.marker' \
                      '%~falsy-string-empty.marker' '%~nosession.marker' | sort | tr '\n' ' ')"
[ "$got" = "$want" ] \
  && ok "the six sentinel keys are spelled exactly as the design fixed them" \
  || no "sentinel spellings drifted -- want [$want] got [$got]"

# --- storage layer: distinct ids must stay distinct as FILENAMES --------------------------
# Encoder-injective is not storage-injective. The key is interpolated into a path, and a
# case-folding volume merges two encoded keys that `@uri` kept apart. No erroneous ALLOW or BLOCK
# was ever demonstrated from it,
# only the shared state, so this is hardening with a measured mechanism and an unobserved
# consequence -- written at that width on purpose.
#
# The first clause is the COST CONTROL, not a behaviour check: ids with no uppercase and no `~` must
# encode byte-for-byte as they do today. It is what keeps existing state filenames from moving, and
# it is why closing this cost zero extra rows. It is expected green before AND after the change.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
for sid in 's' 'a/b' '../escape'; do
  run_hook "$d" "$(jq -nc --arg d "$d" --arg s "$sid" '{session_id:$s,transcript_path:($d+"/t.jsonl"),cwd:$d}')" >/dev/null
done
got="$(marker_names "$d" | tr '\n' ' ')"
want="$(printf '%s\n' 's.marker' 'a%2Fb.marker' '..%2Fescape.marker' | sort | tr '\n' ' ')"
[ "$got" = "$want" ] \
  && ok "ids with no uppercase and no tilde encode exactly as they do today" \
  || no "the encoding moved for ordinary ids -- want [$want] got [$got]"

# The second clause is the actual defect. It is only MEANINGFUL on a case-folding volume, so the row
# probes the volume it is running on and SAYS WHICH -- a bare pass on a case-sensitive filesystem
# would read as evidence when it is nothing but the environment.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
: > "$d/foldprobe"; : > "$d/FOLDPROBE"
if [ "$(ls -A "$d" | grep -ci '^foldprobe$')" = 1 ]; then vol="case-folding"; else vol="case-sensitive"; fi
rm -f "$d/foldprobe" "$d/FOLDPROBE"
rc1="$(run_hook "$d" "$(jq -nc --arg d "$d" '{session_id:"a",transcript_path:($d+"/t.jsonl"),cwd:$d}')")"
rc2="$(run_hook "$d" "$(jq -nc --arg d "$d" '{session_id:"A",transcript_path:($d+"/t.jsonl"),cwd:$d}')")"
# EXACT NAMES, NOT A COUNT -- and that is what makes this row portable. A count separates the pair
# only on a FOLDING volume. On the case-SENSITIVE filesystem this repo's CI actually runs
# (`.github/workflows/validate.yml`, ubuntu-latest), an implementation with the uppercase escape
# removed writes `a.marker` and `A.marker`, the count reads 2, and the row passes WITH THE DEFECT
# PRESENT -- green on the one machine that gates a merge. The encoded names differ as STRINGS
# (`a` vs `~A`), so comparing names catches it on any filesystem. The volume is still reported,
# because which one you are on changes what a failure MEANS, not whether it can be detected.
got="$(marker_names "$d" | tr '\n' ' ')"
want="$(printf '%s\n' 'a.marker' '~A.marker' | sort | tr '\n' ' ')"
{ [ "$rc1" = 2 ] && [ "$rc2" = 2 ] && [ "$got" = "$want" ]; } \
  && ok "ids differing only by case keep separate state files (volume here: $vol)" \
  || no "ids differing only by case are not separated (volume here: $vol rc=$rc1/$rc2 want [$want] got [$got])"

# ...and the ESCAPE CHARACTER itself, which the row above does not reach. FOUND BY A SURVIVING
# MUTANT: deleting the tilde-doubling step left the whole suite green, so nothing
# was testing why the escape needs escaping.
#
# `A` encodes to `~A`, which a folding volume reads as `~a` -- exactly what the literal id `~a`
# encodes to when `~` is not doubled. Doubling makes the second one `~~a` and the pair distinct.
# The same row also catches the two steps being applied in the wrong ORDER, which produces `~~a`
# for both.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
rc1="$(run_hook "$d" "$(jq -nc --arg d "$d" '{session_id:"A",transcript_path:($d+"/t.jsonl"),cwd:$d}')")"
rc2="$(run_hook "$d" "$(jq -nc --arg d "$d" '{session_id:"~a",transcript_path:($d+"/t.jsonl"),cwd:$d}')")"
# Exact names for the same reason as the row above, and here the count form was WORSE than useless:
# with the doubling step deleted the two keys are `~A` and `~a`, which are two distinct files on a
# case-sensitive volume -- so on CI the count reads 2 and the mutant this row exists to kill walks
# straight through. Correct output is `~A` and `~~a`, which differ as strings anywhere.
got="$(marker_names "$d" | tr '\n' ' ')"
want="$(printf '%s\n' '~A.marker' '~~a.marker' | sort | tr '\n' ' ')"
{ [ "$rc1" = 2 ] && [ "$rc2" = 2 ] && [ "$got" = "$want" ]; } \
  && ok "an uppercase id and a tilde-prefixed one keep separate state files" \
  || no "the escape character is not escaped -- want [$want] got [$got]"

# --- the encoder property the sentinel design rests on ----------------------------------
# `%~<token>` is unreachable by any string id BECAUSE a `%` in `@uri` output always begins a
# well-formed escape whose two following characters are UPPERCASE hex, and `~` is not a hex digit.
# That was a comment, and a comment cannot fail.
#
# THE OBVIOUS TEST DOES NOT EXIST. jq refuses to let a program shadow a built-in format --
# `jq -n 'def @uri: ...'` is a syntax error -- and this hook calls jq as an external binary, so the
# real `@uri` can never be driven to emit `%~`. A "stub encoder" mutant is not a thing. The row is
# therefore split: a PREDICATE over already-encoded text, an ACCEPTANCE run feeding it real `@uri`
# output, and a FALSIFICATION run feeding it hand-written literals. The third part is what proves
# the first two can go red at all.
uri_wellformed() {      # 0 when every `%` in $1 begins a well-formed UPPERCASE-hex escape
  case "$(printf '%s' "$1" | sed 's/%[0-9A-F][0-9A-F]//g')" in *%*) return 1 ;; esac
  return 0
}

bad=""
for raw in 's' 'a/b' '../escape' '%' '%25' '~' '%~nosession' 'ünï' 'A' 'aA~/%'; do
  enc="$(jq -rn --arg s "$raw" '$s | gsub("~";"~~") | gsub("(?<c>[A-Z])"; "~\(.c)") | @uri')"
  uri_wellformed "$enc" || bad="$bad [$raw -> $enc: malformed escape]"
  case "$enc" in *'%~'*) bad="$bad [$raw -> $enc: produced a sentinel prefix]" ;; esac
done
[ -z "$bad" ] \
  && ok "the key encoder emits only uppercase-hex escapes and never a sentinel prefix" \
  || no "the key encoder broke its own image guarantee:$bad"

# FALSIFICATION. Without this the row above is satisfied by a predicate that accepts everything --
# the self-proving assertion.
bad=""
for lit in '%~x' '%fa' '%2' '%' '%2f'; do
  uri_wellformed "$lit" && bad="$bad [$lit accepted]"
done
for lit in '%2F' '%25' 'abc' 'a%C3%BFb' ''; do
  uri_wellformed "$lit" || bad="$bad [$lit rejected]"
done
[ -z "$bad" ] \
  && ok "the escape predicate rejects %~, lowercase hex and truncated escapes, and accepts valid ones" \
  || no "the escape predicate is not discriminating:$bad"

# --- the SECOND derivation site, where the hook warns that its library is unusable --------
# `context-floor.sh` says the libwarn id is "derived the SAME way the hook derives it further down".
# Nothing asserted that, and `libwarn` had ZERO occurrences in any suite -- so a token typo at
# that site would have passed every row, repeated suite runs and the close gate. It writes into the
# SAME state directory as the marker, which is what makes its key shape this suite's business.
#
# This row invokes the hook directly instead of through run_hook: run_hook always exports a WORKING
# PLC_FLOOR_LIB, and an unusable one is the entire precondition here.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
printf 'this file is not the floor library\n' > "$d/brokenlib.sh"
lw_run() {              # $1 jq event program
  printf '%s' "$(jq -nc --arg d "$d" "$1")" | \
    env -u PLC_CONTEXT_FLOOR -u PLC_CONTEXT_FLOOR_PCT -u PLC_CONTEXT_FLOOR_STEP \
        -u PLC_CONTEXT_WINDOW -u PLC_RESUME_PATH TMPDIR="$d" LC_ALL=C \
        PLC_FLOOR_LIB="$d/brokenlib.sh" /bin/bash "$IMPL" >/dev/null 2>&1
}
lw_run '{transcript_path:($d+"/t.jsonl"),cwd:$d}'
lw_run '{session_id:"a",transcript_path:($d+"/t.jsonl"),cwd:$d}'
lw_run '{session_id:"A",transcript_path:($d+"/t.jsonl"),cwd:$d}'
got="$(ls -A "$d/plc-context-floor" 2>/dev/null | grep 'libwarn$' | sort | tr '\n' ' ')"
want="$(printf '%s\n' '%~nosession.libwarn' 'a.libwarn' '~A.libwarn' | sort | tr '\n' ' ')"
[ "$got" = "$want" ] \
  && ok "the libwarn throttle keys the absent id and string ids exactly as the marker does" \
  || no "the two derivation sites disagree -- want [$want] got [$got]"

# --- the same site, for the shapes the row above never feeds it -------------------------
# The row above feeds only `absent`, `"a"` and `"A"`. Every one of those keyed correctly while the
# branch was ALSO collapsing `1` with `"1"`, `true` with `"true"` and absent with `""` onto one
# throttle file each -- so one session's "context floor OFF" line silenced another's, which is the
# silent degrade this whole branch exists to prevent. Measured before the fix: fourteen distinct
# ids, ELEVEN files.
#
# This asserts the SET of filenames, never a count. "N distinct files" is satisfiable by N wrong
# files, and a count is weaker than it reads.
#
# `%~nosession` appearing for BOTH the absent id and an explicit `null` is deliberate and is not a
# collision being tolerated: jq reads a missing key and an explicit null identically, the marker
# derivation keys both `%~nosession`.
# Before this change an explicit null keyed `null` -- a shape the marker
# derivation has never produced. Aligning it is part of the fix, not a side effect of it.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
printf 'this file is not the floor library\n' > "$d/brokenlib.sh"
for _ev in '{session_id:1}' '{session_id:"1"}' '{session_id:true}' '{session_id:"true"}' \
           '{}' '{session_id:""}' '{session_id:null}' '{session_id:0}' '{session_id:false}' \
           '{session_id:[]}' '{session_id:{}}' '{session_id:[1,2]}'; do
  lw_run "$_ev"' + {transcript_path:($d+"/t.jsonl"),cwd:$d}'
done
got="$(ls -A "$d/plc-context-floor" 2>/dev/null | grep 'libwarn$' | sort | tr '\n' ' ')"
want="$(printf '%s\n' \
  '%~nonstring-1.libwarn'          '1.libwarn' \
  '%~nonstring-true.libwarn'       'true.libwarn' \
  '%~nosession.libwarn'            '%~falsy-string-empty.libwarn' \
  '%~falsy-number-0.libwarn'       '%~falsy-boolean-false.libwarn' \
  '%~falsy-array-empty.libwarn'    '%~falsy-object-empty.libwarn' \
  '%~nonstring-%5B1%2C2%5D.libwarn' | sort | tr '\n' ' ')"
[ "$got" = "$want" ] \
  && ok "the libwarn throttle splits ids the marker splits, and keys the one shape it refuses" \
  || no "the libwarn throttle collapses distinct session ids -- want [$want] got [$got]"

# The truthy-non-string sentinel has to be UNREACHABLE by a real string id, or it is not a sentinel
# -- a session could then be handed an id that steals another shape`s throttle file. `k` doubles
# `~` before `@uri` runs and `@uri` renders a literal `%` as `%25`, so the string that SPELLS the
# sentinel must encode to something else. Asserted rather than reasoned, because "the encoding is
# injective" was the claim that needed a case-folding filesystem to falsify it once already.
lw_run '{session_id:"%~nonstring-1"} + {transcript_path:($d+"/t.jsonl"),cwd:$d}'
[ -f "$d/plc-context-floor/%25~~nonstring-1.libwarn" ] \
  && [ -f "$d/plc-context-floor/%~nonstring-1.libwarn" ] \
  && ok "a string id spelling the truthy-non-string sentinel cannot reach it" \
  || no "the truthy-non-string sentinel is inside the string encoder image -- a string id collided with it"

echo
echo "-- known-defect rows, graduated to live --"


# --- the grace window is scoped to the resolved checkpoint -------------------
# `clearedat` was keyed by session_id ALONE, so the re-arm grace window earned by checkpointing one
# project suppressed arming in a different one. Checkpoint resolution decides WHICH FILE the floor measures; it does
# not touch WHOSE grace window it honours, and those are two questions that one key was answering.
# An under-block -- the opposite failure from a mis-resolved checkpoint's over-block.
#
# The record now carries the resolved checkpoint path as a second field, so the two questions are
# answered by the same resolution and cannot drift apart.
if command -v git >/dev/null 2>&1; then
  # CF-AC7 -- the original trace: clear in repoA, then arrive over the floor in repoB, whose
  # checkpoint has never been written. Must block.
  d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
  mkrepo "$d/repoA"; mkrepo "$d/repoB"; mkdir -p "$d/neutral"
  arm_old "$d"
  echo fresh > "$d/repoA/RESUME.md"
  run_hook "$d" "$(ev_t "$d" "$d/neutral" "$d/repoA/src/f.txt")" >/dev/null
  rc="$(run_hook "$d" "$(ev_t "$d" "$d/neutral" "$d/repoB/src/x.py")")"
  [ "$rc" = 2 ] \
    && ok "CF-AC7 a grace window earned in one repo does not suppress arming in another" \
    || no "CF-AC7 a grace window earned in one repo does not suppress arming in another (rc=$rc)"

  # CF-AC9 -- THE NEGATIVE CONTROL, and without it AC7 is satisfied by a hook that never grants a
  # grace window at all. Same session, same resolved checkpoint, edits arriving from two different
  # directories inside ONE project: the window IS shared, because it was earned against that
  # project's checkpoint and nothing has changed about which checkpoint is being measured.
  d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
  mkrepo "$d/repoA"; mkdir -p "$d/neutral" "$d/repoA/other"
  arm_old "$d"
  echo fresh > "$d/repoA/RESUME.md"
  run_hook "$d" "$(ev_t "$d" "$d/neutral" "$d/repoA/src/f.txt")" >/dev/null
  rc="$(run_hook "$d" "$(ev_t "$d" "$d/repoA" "$d/repoA/other/g.txt")")"
  # `rc=0` ALONE IS NOT ENOUGH, and this row shipped that way for one measurement before a mutant
  # caught it: with the grace window disabled outright the row still passed, because the allow was
  # coming from the once-per-arm-cycle first-arm grant, not from the grace. The discriminator is the
  # MARKER -- the grace path exits ABOVE the arm block, so a genuine grace allow leaves no marker,
  # while a first-arm allow necessarily creates one.
  if [ "$rc" != 0 ]; then
    no "CF-AC9 within one project the grace window IS shared across directories (rc=$rc)"
  elif [ -e "$d/plc-context-floor/s.marker" ]; then
    no "CF-AC9 the allow came from a re-arm, not from the shared grace window (a marker was created)"
  else
    ok "CF-AC9 within one project the grace window IS shared across directories"
  fi

  # CF-AC8 -- the N>=2 ALTERNATING case:
  # blocked in A, move to B before refreshing A, blocked in B, refresh B, return to A --
  # A must STILL block, because the window B just earned is B's.
  d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
  mkrepo "$d/repoA"; mkrepo "$d/repoB"; mkdir -p "$d/neutral"
  arm_old "$d"
  rc_a1="$(run_hook "$d" "$(ev_t "$d" "$d/neutral" "$d/repoA/src/f.txt")")"   # A: no checkpoint -> block
  rc_b1="$(run_hook "$d" "$(ev_t "$d" "$d/neutral" "$d/repoB/src/x.py")")"   # B: no checkpoint -> block
  echo fresh > "$d/repoB/RESUME.md"
  rc_b2="$(run_hook "$d" "$(ev_t "$d" "$d/neutral" "$d/repoB/src/x.py")")"   # B: refreshed -> clears
  rc_a2="$(run_hook "$d" "$(ev_t "$d" "$d/neutral" "$d/repoA/src/f.txt")")"  # A: must NOT inherit B's
  if [ "$rc_a1$rc_b1" != 22 ]; then
    no "CF-AC8 the alternating case could not be set up (A=$rc_a1 B=$rc_b1) -- the assertion is untested"
  elif [ "$rc_b2" != 0 ]; then
    no "CF-AC8 refreshing repoB's checkpoint clears repoB (rc=$rc_b2)"
  elif [ "$rc_a2" != 2 ]; then
    no "CF-AC8 returning to repoA does not inherit repoB's grace window (rc=$rc_a2)"
  else
    ok "CF-AC8 alternating repos: each grace window stays with the checkpoint that earned it"
  fi
fi

# CF-AC10c -- two distinct checkpoints never share a grace key, asserted with a DELIBERATELY
# ADVERSARIAL pair rather than two arbitrary paths. `a%2Fb/RESUME.md` and `a/b/RESUME.md` are the
# pair that collides under any encoder that does not also encode its own escape character; `@uri`
# does, so the mapping stays injective and the two cannot be confused. Collision resistance is a
# requirement here, not an assumption -- which is the whole reason this is an encoding and not a
# digest.
#
# IT USED TO ASSERT THAT AGAINST ITSELF. The row computed both keys with the same `jq @uri`
# expression the hook uses and compared those two strings, so a hook that stopped encoding, or
# encoded with a scheme that collides, left it green -- it tested `jq`, not the hook. That is the
# identical self-confirming shape CF-AC10 once had.
# It was found here by MUTATION
# COVERAGE and by nothing else: a mutant weakening the encoder to `gsub("/";"%2F")` -- the textbook
# non-injective escape -- reddened AC10's round-trip row and left this one green.
#
# It now drives the HOOK, and the two repositories ARE the adversarial pair: under a colliding
# encoder the window `a/b` earns clears the block held by `a%2Fb`.
if command -v git >/dev/null 2>&1; then
  d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
  mkdir -p "$d/a" "$d/neutral"; mkrepo "$d/a%2Fb"; mkrepo "$d/a/b"
  arm_old "$d"
  rc_p1="$(run_hook "$d" "$(ev_t "$d" "$d/neutral" "$d/a%2Fb/src/f.txt")")"
  rc_p2="$(run_hook "$d" "$(ev_t "$d" "$d/neutral" "$d/a/b/src/f.txt")")"
  echo fresh > "$d/a/b/RESUME.md"
  rc_p3="$(run_hook "$d" "$(ev_t "$d" "$d/neutral" "$d/a/b/src/f.txt")")"
  rc_p4="$(run_hook "$d" "$(ev_t "$d" "$d/neutral" "$d/a%2Fb/src/f.txt")")"
  if [ "$rc_p1$rc_p2" != 22 ]; then
    no "CF-AC10c the adversarial pair could not both be blocked (=$rc_p1$rc_p2) -- the assertion is untested"
  elif [ "$rc_p3" != 0 ]; then
    no "CF-AC10c refreshing a/b's own checkpoint clears a/b (rc=$rc_p3)"
  elif [ "$rc_p4" != 2 ]; then
    no "CF-AC10c the window a/b earned cleared a%2Fb too -- the grace key is not injective (rc=$rc_p4)"
  else
    ok "CF-AC10c an adversarially-chosen checkpoint pair does not share a grace key"
  fi
fi

# CF-AC10 (encoders) -- a checkpoint path containing a NEWLINE, a TAB or a BACKSLASH must not
# corrupt the record's framing. Value encoders are where this hook's defects have clustered, so
# this is the axis this file has actually been burned on. The record is line-framed, so a raw
# newline in field 2 would silently truncate it; `@uri` percent-encodes all three.
# ONE check, not two. A second `case` testing for a literal newline via `*"$(printf '\n')"*` was
# written first and was always true: command substitution strips trailing newlines, so the pattern
# was `**` and matched everything -- a check that fires on every input reports the same red as a
# real finding. The character-class test below already covers newline and tab, because it accepts
# ONLY the unreserved set. MEASURED, not assumed: jq's `@uri` leaves exactly `A-Za-z0-9-_.~` and
# percent-encodes the rest, so `a<newline>b/R.md` becomes `a%0Ab%2FR.md`, tab becomes `%09`, and a
# backslash `%5C`. Even `!*'()` are encoded.
# DRIVEN THROUGH THE HOOK, and the first version was not. It computed the encoding with the SAME
# `jq @uri` expression the hook uses and then checked that value's character set -- so the check and
# the thing it checks moved together, and a hook that stopped encoding entirely would leave this row
# green. That is a self-confirming shape.
#
# The hostile bytes now reach the hook the only way they can without `PLC_RESUME_PATH` (which
# `run_hook` deliberately unsets): a repository directory whose NAME contains them, so the checkpoint
# resolves through it. The assertion is end-to-end -- the record must still be two lines (framing
# survived) AND the grace window it records must still be honoured on the next call (the reader got
# its own value back).
if command -v git >/dev/null 2>&1; then
  AC10_BAD=""
  for weird in "$(printf 'we\nird')" "$(printf 'we\tird')" 'we\ird'; do
    d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
    mkrepo "$d/$weird" 2>/dev/null || { AC10_BAD="mkrepo failed"; break; }
    mkdir -p "$d/neutral"
    arm_old "$d"
    echo fresh > "$d/$weird/RESUME.md"
    rc_clear="$(run_hook "$d" "$(ev_t "$d" "$d/neutral" "$d/$weird/src/f.txt")")"
    CF="$d/plc-context-floor/s.clearedat"
    if [ "$rc_clear" != 0 ]; then AC10_BAD="the clearing call did not clear (rc=$rc_clear)"; break; fi
    if [ ! -f "$CF" ]; then AC10_BAD="no grace record was written"; break; fi
    # Exactly two lines: a raw newline in the second field would make it three or more.
    NL="$(wc -l < "$CF" | tr -d ' ')"
    if [ "$NL" != 2 ]; then AC10_BAD="grace record has $NL lines, not 2 -- framing broken"; break; fi
    # And the reader must accept its own record back.
    rc_grace="$(run_hook "$d" "$(ev_t "$d" "$d/neutral" "$d/$weird/src/g.txt")")"
    if [ "$rc_grace" != 0 ]; then AC10_BAD="the window it just recorded was not honoured (rc=$rc_grace)"; break; fi
  done
  [ -z "$AC10_BAD" ] \
    && ok "CF-AC10 a checkpoint path containing a newline / tab / backslash survives the record round-trip" \
    || no "CF-AC10 a checkpoint path containing a newline / tab / backslash survives the record round-trip ($AC10_BAD)"
fi

# CF-AC10d -- the cwd-FALLBACK case, the one place two genuinely different
# projects can still collapse onto one key: no git root anywhere, both edits made from one cwd. The
# checkpoint resolves to `$CWD/RESUME.md` for BOTH, so they SHARE a key -- and that is the honest
# reading of this row. It pins the residual, it does not claim it away.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
mkdir -p "$d/projX" "$d/projY"                        # no git repos anywhere
arm_old "$d"; echo fresh > "$d/RESUME.md"
run_hook "$d" "$(ev_t "$d" "$d" "$d/projX/f.txt")" >/dev/null
rc="$(run_hook "$d" "$(ev_t "$d" "$d" "$d/projY/g.txt")")"
[ "$rc" = 0 ] \
  && ok "CF-AC10d cwd fallback: two projects under one cwd DO share a window (residual, pinned)" \
  || no "CF-AC10d cwd fallback: two projects under one cwd DO share a window (residual, pinned) (rc=$rc)"


# --- AC1: every non-regular node at the MARKER path is repaired, not stepped over ------------
# The defect these four rows close is not "a directory is mishandled", it is that `[ ! -e ]` made
# EXISTENCE skip the arm block, so the node reached the clear path with a FROZEN mtime and every
# later call cleared the block and collected a STEP-sized grace window. Measured at the branch point,
# all four shapes: `000` over three calls with `s.clearedat` written -- the floor silently OFF.
#
# Four shapes, not three. It was assumed FIFOs and sockets "need a stronger removal path"; measured,
# `rm -f` removes both. They arrive here for the same reason the directory does, so they are asserted
# the same way rather than assumed equivalent.
#
# THREE things per shape, because any one of them alone is satisfiable by a wrong implementation:
# a hook that blocks unconditionally leaves no fresh marker; a hook that DELETES the node leaves no
# aside; and a hook that repairs but still writes `clearedat` hands out the very window this defect leaks.
mk_corrupt_marker() {                      # $1 sandbox, $2 shape
  mkdir -p "$1/plc-context-floor"
  case "$2" in
    emptydir) mkdir "$1/plc-context-floor/s.marker" ;;
    fulldir)  mkdir "$1/plc-context-floor/s.marker"; echo x > "$1/plc-context-floor/s.marker/inner" ;;
    fifo)     mkfifo "$1/plc-context-floor/s.marker" ;;
    socket)   python3 -c 'import socket,sys
s=socket.socket(socket.AF_UNIX); s.bind(sys.argv[1])' "$1/plc-context-floor/s.marker" ;;
  esac
}
for shape in emptydir fulldir fifo socket; do
  d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
  mk_corrupt_marker "$d" "$shape"
  echo fresh > "$d/RESUME.md"
  rcs=""
  for i in 1 2 3; do rcs="$rcs$(run_hook "$d" "$(ev_for "$d")")"; done
  M="$d/plc-context-floor/s.marker"
  ASIDE_N="$(ls -A "$d/plc-context-floor" 2>/dev/null | grep -c '^s\.corrupt\.')"
  case "$rcs" in
    *124*) no "CF-AC1 $shape at the marker path does not hang the hook (rcs=$rcs)"; continue ;;
  esac
  if [ "$rcs" = 000 ]; then
    no "CF-AC1 $shape at the marker path is repaired (the floor stayed OFF for the session: rcs=$rcs)"
  elif [ ! -f "$M" ] || [ -L "$M" ]; then
    no "CF-AC1 $shape at the marker path is replaced by a fresh REGULAR marker (rcs=$rcs)"
  elif [ "$ASIDE_N" != 1 ]; then
    no "CF-AC1 $shape is renamed ASIDE, never deleted (aside nodes=$ASIDE_N)"
  elif [ -e "$d/plc-context-floor/s.clearedat" ]; then
    no "CF-AC1 $shape repair hands out no grace window (clearedat was written)"
  else
    ok "CF-AC1 $shape at the marker path: renamed aside, fresh regular marker, no unearned grace (rcs=$rcs)"
  fi
done

# --- AC1b: a FIFO must not make the hook HANG --------------------------------
# Its own row because the failure mode has no exit code. Placing the repair AFTER the O_EXCL create --
# the obvious spot, beside the symlink repair -- opens the FIFO for write, which BLOCKS until a
# reader appears. MEASURED: the probe never returned. That is strictly worse than the defect being
# fixed (that defect turns the floor off; this stalls the agent's tool call indefinitely) and no assertion
# above can see it, because a hung process produces no exit code to compare.
#
# HONEST BOUNDARY: on a host without `timeout` this row degrades to "the suite never finishes", the
# same shape as AC11b's watchdog. Recorded rather than papered over.
if [ -n "$CT_TIMEOUT" ]; then
  d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
  mk_corrupt_marker "$d" fifo
  echo fresh > "$d/RESUME.md"
  rc="$(run_hook "$d" "$(ev_for "$d")")"
  [ "$rc" = 124 ] \
    && no "CF-AC1b a FIFO at the marker path does not hang the hook (it timed out)" \
    || ok "CF-AC1b a FIFO at the marker path does not hang the hook"
else
  ok "CF-AC1b skipped -- no timeout(1) on this host; a hang shows up as a suite that never finishes"
fi

# --- AC5: the aside destination is collision-safe ----------------------------
# Two successive repairs in one session must not overwrite each other's aside node.
#
# WHAT THIS ROW DOES NOT REACH, stated so nobody reads it as fuller coverage than it is: each
# invocation is a fresh process, so the two repairs get different PIDs and the names differ on the
# PID alone. The `.$_cfn` counter is a backstop against PID REUSE, and no fixture here reaches it --
# a guard with zero coverage, stated here rather than
# asserted with a fixture that cannot exist.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
echo fresh > "$d/RESUME.md"
mk_corrupt_marker "$d" emptydir
run_hook "$d" "$(ev_for "$d")" >/dev/null
rm -f "$d/plc-context-floor/s.marker"
mk_corrupt_marker "$d" fifo
run_hook "$d" "$(ev_for "$d")" >/dev/null
ASIDE_N="$(ls -A "$d/plc-context-floor" 2>/dev/null | grep -c '^s\.corrupt\.')"
[ "$ASIDE_N" = 2 ] \
  && ok "CF-AC5 two repairs in one session leave two distinct aside nodes" \
  || no "CF-AC5 two repairs in one session leave two distinct aside nodes (found $ASIDE_N)"

# --- AC6: a rename that CANNOT proceed fails closed AND stays clearable ------
# Driven by a TEST DOUBLE, deliberately, and the reason is written here rather than left as an
# apology. A same-directory rename fails only if the marker path is itself a mount point, or if the
# state directory is unwritable -- and the second case fails the sidecar create too, so it reaches
# the pre-existing "cannot manage marker -> fail open" exit that has always been there. Neither is
# constructible in this harness without root. The rule for a guard no fixture can
# reach: build a test double, do not write a comment claiming it works.
#
# The double is the shipped hook with `mv` forced to fail. Nothing else changes, so what this row
# exercises is the real branch, not a re-implementation of it.
#
# THREE readings, and the row must be able to fail on each independently:
#   0000 -> failed closed? no, it fails OPEN: this is the original defect surviving in a new location
#   2222 -> clearable? no: the cardinal sin, an operator doing the one named action gets nowhere
#   0 2 then 0 after a refresh -> blocks, and the named action works
#
# COVERAGE, measured rather than assumed, and this note has already been revised once by measurement.
# Two mutants built FOR this row -- the sidecar removed, and the sidecar branch blocking
# unconditionally -- both stop at the SAME assertion ("no sidecar was created") and print an identical
# message, so between them they reach one branch, not two. A third mutant built for a different row
# (the clear branch records and removes but no longer allows) reaches the FOURTH branch here as well,
# reporting `sidecar_made=yes` with the refresh not clearing -- the wedge. So two of the four branches
# have a mutant; a mutant written for one row proving another row is the argument for running the
# WHOLE matrix after every change rather than the mutants a row "owns".
#
# The `0000` branch remains unreached, and by construction: this fixture starts the checkpoint OLDER
# than the guard's state, so the fail-open shape cannot arise here at all. That one is a guard with no
# coverage -- written down instead of left to look covered.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
MVFAIL="$WORK/mv-always-fails.sh"
sed 's|mv "\$MARKER" "\$_cfaside" 2>/dev/null|false|' "$IMPL" > "$MVFAIL"
if ! grep -q 'could not be repaired' "$MVFAIL" || grep -q 'mv "\$MARKER"' "$MVFAIL"; then
  no "CF-AC6 the test double could not be built (the sed no longer matches the hook)"
else
  mkdir -p "$d/plc-context-floor/s.marker"; echo x > "$d/plc-context-floor/s.marker/inner"
  echo stale > "$d/RESUME.md"
  # Constructed, never slept for. RESUME starts OLDER than anything the hook will create.
  python3 - "$d/RESUME.md" <<'PY' || { echo "FATAL: could not construct mtimes" >&2; exit 1; }
import os,sys
os.utime(sys.argv[1], ns=(1_000_000_000_000_000_000, 1_000_000_000_000_000_000))
PY
  rc1="$(RH_IMPL="$MVFAIL" run_hook "$d" "$(ev_for "$d")")"
  rc2="$(RH_IMPL="$MVFAIL" run_hook "$d" "$(ev_for "$d")")"
  WEDGED="$d/plc-context-floor/s.wedged"
  # SAMPLED BEFORE THE CLEARING CALL, deliberately. A successful clear runs `rm -f` on the guard's
  # own marker, which is now the sidecar -- so checking after rc3 asks whether a file the hook is
  # SUPPOSED to remove was removed, and answers "no sidecar was ever created". Measured: the first
  # version of this row did exactly that and accused a working hook.
  WEDGED_MADE=no; [ -f "$WEDGED" ] && [ ! -L "$WEDGED" ] && WEDGED_MADE=yes
  echo refreshed > "$d/RESUME.md"          # the ONE action the block message names
  # Fatally verified rather than assumed: the refresh must really be newer than the guard's state,
  # otherwise the row would pass or fail for a reason that has nothing to do with the branch.
  # Gated on the sidecar existing, and NOT fatal when it does not. "No sidecar was created" is one of
  # the outcomes this row exists to REPORT; a fatal exit here made the two mutants that produce it
  # kill the suite instead, so both printed no output at all and no summary line -- a mutant that
  # destroys the harness looks nothing like a mutant the harness catches. Measured, both of them.
  rc3=""
  if [ "$WEDGED_MADE" = yes ]; then
    python3 - "$d/RESUME.md" "$WEDGED" <<'PY' || { echo "FATAL: mtime construction failed" >&2; exit 1; }
import os,sys
w=os.stat(sys.argv[2]).st_mtime_ns
os.utime(sys.argv[1], ns=(w+2_000_000_000, w+2_000_000_000))
assert os.stat(sys.argv[1]).st_mtime_ns > os.stat(sys.argv[2]).st_mtime_ns
PY
    rc3="$(RH_IMPL="$MVFAIL" run_hook "$d" "$(ev_for "$d")")"
  fi
  SEEN="rc=$rc1$rc2$rc3 sidecar_made=$WEDGED_MADE entries=[$(ls -A "$d/plc-context-floor" 2>/dev/null | tr '\n' ' ')]"
  if [ "$WEDGED_MADE" != yes ]; then
    no "CF-AC6 an unrepairable marker moves the guard's state to a sidecar ($SEEN)"
  elif [ "$rc1$rc2" = 00 ]; then
    no "CF-AC6 an unrepairable marker fails CLOSED (the floor stayed off: $SEEN)"
  elif [ "$rc2" != 2 ]; then
    no "CF-AC6 an unrepairable marker blocks the over-floor call ($SEEN)"
  elif [ "$rc3" != 0 ]; then
    no "CF-AC6 refreshing the checkpoint still clears an unrepairable marker ($SEEN -- the 2222 wedge)"
  else
    ok "CF-AC6 an unrepairable marker blocks, and refreshing the checkpoint still clears it"
  fi
fi

# --- AC11b: the digest walks hostile node types and TERMINATES ---------------
# AC1 covers a directory / FIFO / socket / symlink at the MARKER path. Nothing covered those shapes
# INSIDE the trees the digest walks, and the digest is new code, so its own blind spots are nobody's
# regression yet.
#
# The symlink LOOP is the one that matters. `ct_walk` recurses only when `[ -d ] && [ ! -L ]`, so a
# loop terminates BY CONSTRUCTION rather than by a depth counter (a bound that changes the answer
# is not a backstop).
#
# HONEST BOUNDARY, stated rather than discovered later: a mutant that DOES descend symlinked
# directories does not redden this row, it HANGS. `timeout` converts that into a red where it exists,
# and it is used when present -- but it is not on a bare macOS, so on such a host this row asserts
# COMPLETENESS (every shape reported, exactly once) and a non-terminating walk shows up as a suite
# that never finishes. Completeness is still falsifiable on every host: a walk that skipped or
# double-counted an entry reddens here.
d="$(sandbox)"
mkdir -p "$d/tree/sub"
: > "$d/tree/plain"
mkfifo "$d/tree/afifo" 2>/dev/null
ln -s /dev/null "$d/tree/todev"
# A REAL cycle, and getting it wrong is easy: `ln -s ../tree` resolves against the LINK'S directory
# (`tree/sub`), i.e. `tree/tree`, which does not exist -- a DANGLING link that terminates for the
# wrong reason. Measured: with that target the row passed while a mutant that descends symlinked
# directories also passed, because there was nothing to descend into. `..` is `tree` itself.
ln -s .. "$d/tree/sub/loop"
DIG=""
if command -v timeout >/dev/null 2>&1; then
  # `export -f` is what makes this branch real. A first cut ran `timeout ... bash -c 'tree_digest'`
  # WITHOUT exporting, so the fresh shell had no such function, the branch produced empty output on
  # every host, and the in-process fallback did all the work -- a watchdog that could never fire,
  # printing the same green as one that did.
  export -f tree_digest ct_walk ct_modetype
  export MODETYPE_STAT
  DIG="$(timeout 20 /bin/bash -c 'tree_digest "$1"' _ "$d/tree" 2>/dev/null)"; DIGRC=$?
else
  DIG="$(tree_digest "$d/tree")"; DIGRC=$?
fi
_count() { printf '%s\n' "$DIG" | grep -c "$1"; }
if [ "$DIGRC" = 124 ]; then
  no "CF-AC11b the recursive digest terminates on a symlink loop (it timed out)"
elif [ "$(_count '^tree_')" != 0 ]; then
  no "CF-AC11b the digest reports relative paths, not \$root-prefixed ones"
elif [ "$(_count '^sub/loop ')" != 1 ]; then
  no "CF-AC11b the symlink loop is reported exactly once, as a link (got $(_count '^sub/loop '))"
elif [ "$(_count 'type=fifo')" != 1 ] || [ "$(_count '^todev ')" != 1 ] \
     || [ "$(_count '^plain ')" != 1 ] || [ "$(_count '^sub ')" != 1 ]; then
  no "CF-AC11b every node type is reported exactly once (fifo/devlink/plain/dir)"
elif printf '%s\n' "$DIG" | grep -q 'loop/'; then
  no "CF-AC11b the digest descended THROUGH the symlink loop"
else
  ok "CF-AC11b the recursive digest walks fifo/symlink/dir/loop, terminates, and descends no symlink"
fi

# --- AC13: the hook never executes in the suite's own working directory ------
# The run directory's guarantee is that nothing the hook writes with a RELATIVE path can land in this checkout. The
# old design bought that per row with an optional argument; this asserts the property itself, once.
#
# Written as "where did the hook actually run", not "was the suite launched from the repo root",
# because the second is a property of how someone typed the command and the first is the property
# that makes it not matter. Falsifiable: revert `run_hook`'s `mktemp`/`cd` to the old default of `.`
# and this row reddens immediately.
d="$(sandbox)"; usage_line 160000 > "$d/t.jsonl"
CWDPROBE="$WORK/cwd-probe.sh"
# Writes into the state directory, the one place the hook is allowed to write, so this row does not
# trip the stray oracle asserted below.
printf '#!/usr/bin/env bash\nmkdir -p "$TMPDIR/plc-context-floor"\npwd -P > "$TMPDIR/plc-context-floor/.probe-cwd"\nexit 0\n' \
  > "$CWDPROBE"
RH_IMPL="$CWDPROBE" run_hook "$d" "$(ev_for "$d")" >/dev/null
RANIN="$(cat "$d/plc-context-floor/.probe-cwd" 2>/dev/null || true)"
SUITECWD="$(pwd -P)"
WORKP="$(cd "$WORK" && pwd -P)"
if [ -z "$RANIN" ]; then
  no "CF-AC13 the hook's working directory could not be probed"
elif [ "$RANIN" = "$SUITECWD" ]; then
  no "CF-AC13 the hook ran in the SUITE's own cwd ($RANIN) -- a relative write would land in the checkout"
elif case "$RANIN" in "$WORKP"/*) false ;; *) true ;; esac; then
  no "CF-AC13 the hook ran outside the harness's own work tree ($RANIN)"
else
  ok "CF-AC13 the hook executes in a harness-owned run directory, never the suite's cwd"
fi

# --- nothing outside the state directory ------------------
# One row, asserted at the END rather than inside `run_hook`, because `run_hook`'s body runs in a
# command-substitution subshell (see the note there) and no counter it touches survives.
#
# A POSITIVE row, not a silent check that only speaks up when it fails. A guard that is invisible on
# a green run is a guard nobody notices has stopped running -- the silent-degrade class.
# It costs one line of output.
if [ -s "$STRAYLOG" ]; then
  no "the hook writes nothing outside its own state directory -- it wrote: $(tr '\n' '; ' < "$STRAYLOG")"
else
  ok "the hook writes nothing outside its own state directory (every call snapshot-checked)"
fi

echo
printf 'contract: %d passed, %d failed, %d xfail (expected), %d xpass (UNEXPECTED)\n' \
  "$PASS" "$FAIL" "$XFAIL" "$XPASS"
# An XPASS is a failure of this suite: a preserved defect stopped reproducing and nobody decided that.
# The SAME function `RL-AC8` evaluates -- never a second copy of the expression.
plc_gate
