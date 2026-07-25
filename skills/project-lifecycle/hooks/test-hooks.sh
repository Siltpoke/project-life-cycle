#!/usr/bin/env bash
# Deterministic tests for the project-lifecycle frontmatter hook scripts.
# Run before committing hook changes. No fresh session needed — these exercise the scripts directly.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# The result ledger is a FILE, not a shell variable. Four of the sections below run inside
# ( … ) subshells, and a variable incremented in a subshell is discarded when it exits — so
# a counter kept in $PASS/$FAIL structurally cannot see most of this suite's own results.
# Created before the first subshell, and FORCED ABSOLUTE: the sections that `cd` into a
# temp repo and then `rm -rf` it must not be able to reach it. A relative TMPDIR would put
# the ledger inside one of those repos, and its results would be deleted with it.
RESULTS="$(mktemp "${TMPDIR:-/tmp}/plc-test-hooks.XXXXXX")" \
  || { echo "FATAL: cannot create the result ledger under '${TMPDIR:-/tmp}'" >&2; exit 1; }
case "$RESULTS" in /*) ;; *) RESULTS="$PWD/$RESULTS" ;; esac
trap 'rm -f "$RESULTS"' EXIT

# `return 0` is load-bearing: almost every assertion is an `A && ok … || no …` chain, and a
# non-zero return from ok would run the no branch as well.
#
# A failed append is announced on stderr, but be precise about what that buys: most of these
# calls happen inside ( … ) subshells, so `led` CANNOT abort the run or reach the tally. The
# notice is a breadcrumb for a human reading the log, not a control. `verdict` is where the
# ledger's health is actually judged, and its coverage is stated there — do not read this
# stderr line as "a lost result cannot slip through".
led(){ printf '%s\n' "$1" >> "$RESULTS" || echo "FATAL: result ledger unwritable ($RESULTS)" >&2; }
ok(){ printf '  PASS: %s\n' "$1"; led P; return 0; }
no(){ printf '  FAIL: %s\n' "$1"; led F; return 0; }

# Print the tally and exit with it. Every path out of this script goes through here.
verdict(){
  local p f
  # An absent or empty ledger is NOT a pass. "Nothing was recorded" and "nothing failed"
  # are different states, and treating the first as the second is exactly how this suite
  # used to report green over its own failures.
  [ -s "$RESULTS" ] || {
    echo
    echo "RESULT: no results recorded — the ledger is missing or empty, so this run proves nothing"
    exit 1
  }
  # …and a ledger that STOPPED being writable part-way is the same defect with a later
  # trigger: the entries recorded before it broke are all passes, the failures after it are
  # gone, and the tally reads clean. Checked, not assumed.
  # KNOWN RESIDUAL: this catches the permission case, not a mid-run ENOSPC (the file stays
  # writable, the append just fails). Closing that needs an expected-assertion-count floor,
  # which is a different trade — written down here rather than papered over.
  [ -w "$RESULTS" ] || {
    echo
    echo "RESULT: the ledger stopped being writable — results were lost, so this run proves nothing"
    exit 1
  }
  p="$(grep -c '^P$' "$RESULTS" 2>/dev/null)" || true
  f="$(grep -c '^F$' "$RESULTS" 2>/dev/null)" || true
  case "$p" in ''|*[!0-9]*) p=0 ;; esac
  case "$f" in ''|*[!0-9]*) f=0 ;; esac
  echo
  echo "RESULT: $p passed, $f failed"
  [ "$f" -eq 0 ] || exit 1
  exit 0
}

# Self-verification mode. Re-entered by the "=== self-verification ===" section at
# the bottom, which asserts that this script's EXIT CODE reflects its assertions. Skips
# every test body and takes only the verdict path.
#   --selftest-fail  -> one deliberate FAILURE raised from inside a ( … ) subshell — the
#                       exact case a shell-variable counter cannot see. Must exit non-zero.
#   --selftest-clean -> one deliberate PASS, also from inside a subshell. Must exit zero.
# Both sides raise a real result: a mode that recorded nothing would only prove "an empty
# ledger exits zero", which is the very state verdict() now refuses to call a pass.
# Driven by $1, never by an inherited environment variable — an exported PLC_SELFTEST would
# silently reduce a full run to a two-line no-op that still exits 0.
case "${1:-}" in
  --selftest-fail)  ( no "deliberate failure raised inside a subshell (self-test)" ); verdict ;;
  --selftest-clean) ( ok "deliberate pass raised inside a subshell (self-test)" );   verdict ;;
  "") ;;
  *)  echo "usage: ${BASH_SOURCE[0]##*/} [--selftest-fail|--selftest-clean]" >&2; exit 2 ;;
esac

# Build the hook event JSON via json.dumps so commands containing quotes
# (e.g. a -m "message") are escaped correctly.
ev(){ python3 -c 'import json,sys; print(json.dumps({"tool_name":"Bash","tool_input":{"command":sys.argv[1]}}))' "$1"; }

echo "=== guard.sh ==="
ev 'git commit --no-verify -m x' | bash "$HERE/guard.sh" >/dev/null 2>&1; [ $? -eq 2 ] && ok "blocks --no-verify flag" || no "blocks --no-verify flag"
ev 'git push origin main'        | bash "$HERE/guard.sh" >/dev/null 2>&1; [ $? -eq 2 ] && ok "blocks push origin main" || no "blocks push origin main"
ev 'git push origin HEAD:main'   | bash "$HERE/guard.sh" >/dev/null 2>&1; [ $? -eq 2 ] && ok "blocks push HEAD:main" || no "blocks push HEAD:main"
ev 'git push origin feat/phase-1.2-x' | bash "$HERE/guard.sh" >/dev/null 2>&1; [ $? -eq 0 ] && ok "allows push to feat branch" || no "allows push to feat branch"
ev 'git push origin main-experiment'  | bash "$HERE/guard.sh" >/dev/null 2>&1; [ $? -eq 0 ] && ok "allows push to main-experiment (no false positive)" || no "allows main-experiment"
ev 'echo hello'                  | bash "$HERE/guard.sh" >/dev/null 2>&1; [ $? -eq 0 ] && ok "allows ordinary command" || no "allows ordinary command"
ev 'npm run verify'              | bash "$HERE/guard.sh" >/dev/null 2>&1; [ $? -eq 0 ] && ok "allows 'verify' substring" || no "allows verify substring"
# Regression: the flag/word appearing inside a commit MESSAGE must NOT false-block.
# These two passed under the old python3 shlex implementation because shlex kept a quoted span as
# ONE token. The POSIX rewrite has no lexer, so it passes them by a DIFFERENT mechanism:
# quoted spans are deleted outright before anything is tokenized. Spelled out because the two
# routes are not interchangeable — a future "simplification" that tokenizes first and strips
# later silently reopens both of these, and they would then be the guard's most common false
# positive (every commit message that says "main" or "--no-verify").
ev 'git commit -m "docs: guard blocks the --no-verify bypass"' | bash "$HERE/guard.sh" >/dev/null 2>&1; [ $? -eq 0 ] && ok "allows --no-verify inside a commit message (quoted span dropped)" || no "false-positive: --no-verify in message"
ev 'git commit -m "note: push to main later"' | bash "$HERE/guard.sh" >/dev/null 2>&1; [ $? -eq 0 ] && ok "allows 'main' inside a commit message (quoted span dropped)" || no "false-positive: main in message"
ev "git commit -m 'single quotes: push to main'" | bash "$HERE/guard.sh" >/dev/null 2>&1; [ $? -eq 0 ] && ok "allows 'main' inside a single-quoted message" || no "false-positive: main in single-quoted message"

# --- the guard reported the event it inferred, not the one it checked ---------------------
# Every case below is a PROBED observation from this defect's brainstorm, not a hypothetical. The
# expectations are what a correct guard must do; the ones marked (RED) fail against the
# prior implementation and are the reason this section exists. Pinning them here first is
# deliberate: a correctness fix for an inference bug that is not itself pinned to evidence is the
# same defect class recurring inside its own fix.
#
# Two independent bugs are covered:
#   (1) FALSE POSITIVES — the whole command line is scanned as one flat token list, so `push` from
#       one sub-command and `main` from another combine into a verdict about neither.
#   (2) FALSE NEGATIVES — the target is matched as `t == "main" or t.endswith(":main")`, which is
#       not how git names a push target. `+main` (FORCE) and `refs/heads/main` both miss.

# (1) Compound commands: the `push` and the `main` come from DIFFERENT sub-commands.
ev 'git push -u origin feat/x && gh pr create --base main --title x' | bash "$HERE/guard.sh" >/dev/null 2>&1; [ $? -eq 0 ] && ok "allows push-to-feat && gh pr create --base main (RED-1)" || no "false-positive: compound push + gh pr create --base main"
ev 'git checkout main && git push origin --delete feat/x' | bash "$HERE/guard.sh" >/dev/null 2>&1; [ $? -eq 0 ] && ok "allows checkout main && push --delete feat (RED-2)" || no "false-positive: compound checkout main + branch-delete push"
# Unspaced operator — naive word-splitting fuses `x&&gh` into one token and segmentation silently
# does nothing. Kept as its own case precisely because it is the way the fix is most likely to fail.
ev 'git push origin x&&gh pr create --base main' | bash "$HERE/guard.sh" >/dev/null 2>&1; [ $? -eq 0 ] && ok "allows unspaced compound: push origin x&&gh pr create --base main (RED-3)" || no "false-positive: unspaced compound operator"

# (2) Real pushes to main that the token match does not recognise.
ev 'git push origin refs/heads/main' | bash "$HERE/guard.sh" >/dev/null 2>&1; [ $? -eq 2 ] && ok "blocks push to refs/heads/main (RED-4)" || no "FALSE NEGATIVE: refs/heads/main allowed"
ev 'git push origin +main' | bash "$HERE/guard.sh" >/dev/null 2>&1; [ $? -eq 2 ] && ok "blocks FORCE push to main (+main) (RED-5)" || no "FALSE NEGATIVE: +main force-push allowed"
ev 'git push origin +HEAD:main' | bash "$HERE/guard.sh" >/dev/null 2>&1; [ $? -eq 2 ] && ok "blocks force push +HEAD:main" || no "FALSE NEGATIVE: +HEAD:main allowed"

# Deletion forms of the same target — these already pass; pinned so a rewrite cannot lose them.
ev 'git push origin :main' | bash "$HERE/guard.sh" >/dev/null 2>&1; [ $? -eq 2 ] && ok "blocks delete-by-refspec :main" || no "regression: :main allowed"
ev 'git push origin --delete main' | bash "$HERE/guard.sh" >/dev/null 2>&1; [ $? -eq 2 ] && ok "blocks --delete main" || no "regression: --delete main allowed"
# Independent-review finding: --delete/-d BEFORE the remote. The flag binds to the whole segment,
# not to the single next token — else the token after --delete is eaten as the delete target
# (a non-main), the remote consumes the next slot, and `main` lands in the refspec position unchecked.
ev 'git push --delete origin main' | bash "$HERE/guard.sh" >/dev/null 2>&1; [ $? -eq 2 ] && ok "blocks --delete BEFORE remote (delete origin main)" || no "FALSE NEGATIVE: --delete origin main allowed"
ev 'git push -d origin main' | bash "$HERE/guard.sh" >/dev/null 2>&1; [ $? -eq 2 ] && ok "blocks -d BEFORE remote (-d origin main)" || no "FALSE NEGATIVE: -d origin main allowed"

# Correct-today cases, pinned as regressions. `main:release` and `target=main` were each WRONGLY
# predicted to be false positives during the brainstorm and were corrected by probing — they are
# handled right today, and a rewrite must not "fix" them into blocks.
ev 'git push origin main:release' | bash "$HERE/guard.sh" >/dev/null 2>&1; [ $? -eq 0 ] && ok "allows main:release (main is the SOURCE, target is release)" || no "false-positive: main as refspec source"
ev 'git push -o "target=main" origin feat/x' | bash "$HERE/guard.sh" >/dev/null 2>&1; [ $? -eq 0 ] && ok "allows --push-option value containing main" || no "false-positive: -o target=main"
ev 'git push origin --delete feat/x' | bash "$HERE/guard.sh" >/dev/null 2>&1; [ $? -eq 0 ] && ok "allows branch-delete push (standalone)" || no "false-positive: standalone --delete feat"
ev 'gh pr create --base main --title x' | bash "$HERE/guard.sh" >/dev/null 2>&1; [ $? -eq 0 ] && ok "allows standalone gh pr create --base main" || no "false-positive: standalone gh pr create"

# DOCUMENTED FALSE POSITIVE, asserted as current behaviour rather than as desired behaviour.
# A heredoc BODY is not command structure, but the hook receives the whole command string and
# cannot tell. This blocked the commit message for this rewrite itself. Left unfixed on
# purpose (over-block is the safe direction here; `-F <file>` is the existing convention; and
# modelling heredocs means matching delimiters / `<<-` / quoted forms). Pinned so that a future
# change to this behaviour is a DECISION with a failing test, not a silent drift.
ev 'git commit -F - <<EOF
docs: explain that git push origin +main is forbidden
EOF' | bash "$HERE/guard.sh" >/dev/null 2>&1; [ $? -eq 2 ] && ok "KNOWN over-block: heredoc body describing a push to main (documented, not fixed)" || no "heredoc behaviour changed — update guard.sh's KNOWN FALSE POSITIVE note"

echo "=== close-gate-nudge.sh ==="
# Off a phase branch → must be silent. Exercised in a temp repo, NOT in $PWD: reading the
# real repo's branch and dirty state as the premise made this assertion fail whenever the
# suite was run from the `feat/phase-*` branch this project mandates for all work — and
# This turns that from a cosmetic red line into a non-zero exit for the whole suite. It also
# kept the hook's throttle file out of whichever repo the suite happened to run from.
SILTMP="$(mktemp -d)" || { echo "FATAL: mktemp -d failed (\$SILTMP)" >&2; exit 1; }
(
  # the nudge's throttle state now lives OUTSIDE the worktree. Pin it into the fixture so
  # the suite neither pollutes the developer's real ~/.claude/plc-state/ nor inherits a throttle
  # from a previous run — the latter would silence the nudge and turn a real failure green.
  export PLC_STATE_DIR="$SILTMP-state"
  cd "$SILTMP"
  git init -q && git config user.email t@t && git config user.name t
  git checkout -q -b not-a-phase-branch 2>/dev/null || true
  echo a > a.txt && git add a.txt && git commit -qm init      # clean tree, non-phase branch
  OUT="$(echo '{}' | bash "$HERE/close-gate-nudge.sh" Stop 2>/dev/null)"
  [ -z "$OUT" ] && ok "silent off a phase branch" || no "silent off a phase branch (got: $OUT)"
)
rm -rf "$SILTMP" "$SILTMP-state"

# Integration: temp git repo on a feat/phase-* branch + dirty → must emit JSON.
TMP="$(mktemp -d)" || { echo "FATAL: mktemp -d failed (\$TMP)" >&2; exit 1; }
(
  export PLC_STATE_DIR="$TMP-state"      # throttle state outside the worktree
  cd "$TMP"
  git init -q && git config user.email t@t && git config user.name t
  echo a > a.txt && git add a.txt && git commit -qm init
  git checkout -q -b feat/phase-1.0-test
  echo b > b.txt   # uncommitted → dirty
  rm -rf .claude
  OUT="$(echo '{}' | bash "$HERE/close-gate-nudge.sh" Stop 2>/dev/null)"
  # python asserts and exits; the SHELL decides — otherwise the pass never reaches the ledger.
  echo "$OUT" | python3 -c 'import json,sys
d=json.load(sys.stdin)
a=d["hookSpecificOutput"]["additionalContext"]
assert d["hookSpecificOutput"]["hookEventName"]=="Stop"
assert "Definition of Done" in a and "feat/phase-1.0-test" in a' 2>/dev/null \
    && ok "emits nudge JSON on dirty phase branch" \
    || no "emits nudge JSON on dirty phase branch (got: $OUT)"
  # Throttle: second call within 10 min → silent.
  OUT2="$(echo '{}' | bash "$HERE/close-gate-nudge.sh" Stop 2>/dev/null)"
  [ -z "$OUT2" ] && ok "throttled (silent within 10 min)" || no "throttle (got: $OUT2)"
)
rm -rf "$TMP" "$TMP-state"

# D2 /clear nudge: clean tree + test-evidence (task close just passed) + occupancy vs floor.
CNTMP="$(mktemp -d)" || { echo "FATAL: mktemp -d failed (\$CNTMP)" >&2; exit 1; }
(
  export PLC_STATE_DIR="$CNTMP-state"    # throttle state outside the worktree
  cd "$CNTMP"
  unset PLC_CONTEXT_FLOOR PLC_CONTEXT_FLOOR_PCT PLC_CONTEXT_FLOOR_STEP PLC_CONTEXT_WINDOW
  git init -q && git config user.email t@t && git config user.name t
  printf '.claude/\n*.jsonl\n' > .gitignore
  echo a > a.txt && git add .gitignore a.txt && git commit -qm init
  git checkout -q -b feat/phase-2.0-test
  mkdir -p .claude && echo evidence > .claude/.last-test-run   # clean + tested = task close passed
  mktrans(){ python3 -c 'import json,sys; open(sys.argv[1],"w").write(json.dumps({"type":"assistant","message":{"usage":{"input_tokens":int(sys.argv[2]),"cache_read_input_tokens":0,"cache_creation_input_tokens":0}}})+"\n")' "$1" "$2"; }
  evn(){ python3 -c 'import json,sys; print(json.dumps({"session_id":"s","transcript_path":sys.argv[1]}))' "$1"; }

  # under floor (120K < default 150K) → silent
  mktrans t-low.jsonl 120000
  OUT="$(evn "$CNTMP/t-low.jsonl" | bash "$HERE/close-gate-nudge.sh" Stop 2>/dev/null)"
  [ -z "$OUT" ] && ok "clear-nudge silent under floor" || no "clear-nudge silent under floor (got: $OUT)"

  # floor disabled → silent even far over
  mktrans t-dis.jsonl 500000
  OUT="$(evn "$CNTMP/t-dis.jsonl" | PLC_CONTEXT_FLOOR=0 bash "$HERE/close-gate-nudge.sh" Stop 2>/dev/null)"
  [ -z "$OUT" ] && ok "clear-nudge silent when floor disabled" || no "clear-nudge floor=0 (got: $OUT)"

  # no transcript_path in event → silent (fail-open)
  OUT="$(echo '{}' | bash "$HERE/close-gate-nudge.sh" Stop 2>/dev/null)"
  [ -z "$OUT" ] && ok "clear-nudge fail-open without transcript" || no "clear-nudge fail-open (got: $OUT)"

  # malformed (non-JSON) event on stdin → silent + exit 0 (fail-open)
  OUT="$(printf '{ not json' | bash "$HERE/close-gate-nudge.sh" Stop 2>/dev/null)"; RC=$?
  { [ -z "$OUT" ] && [ "$RC" -eq 0 ]; } && ok "clear-nudge fail-open on malformed event JSON" || no "clear-nudge malformed event (rc=$RC, got: $OUT)"

  # over floor (200K ≥ 150K) → emits /clear nudge JSON with occupancy
  mktrans t-hi.jsonl 200000
  OUT="$(evn "$CNTMP/t-hi.jsonl" | bash "$HERE/close-gate-nudge.sh" Stop 2>/dev/null)"
  echo "$OUT" | python3 -c 'import json,sys
d=json.load(sys.stdin)
a=d["hookSpecificOutput"]["additionalContext"]
assert d["hookSpecificOutput"]["hookEventName"]=="Stop"
assert "/clear" in a and "200K" in a and "150K" in a' 2>/dev/null \
    && ok "clear-nudge emits over floor (clean+tested)" \
    || no "clear-nudge emits over floor (got: $OUT)"

  # throttled second call → silent
  OUT="$(evn "$CNTMP/t-hi.jsonl" | bash "$HERE/close-gate-nudge.sh" Stop 2>/dev/null)"
  [ -z "$OUT" ] && ok "clear-nudge throttled (silent within 10 min)" || no "clear-nudge throttle (got: $OUT)"

  # window-% mode: 70% of 1M = 700K floor → 720K emits (after clearing throttle)
  rm -rf "$PLC_STATE_DIR"
  mktrans t-pct.jsonl 720000
  OUT="$(evn "$CNTMP/t-pct.jsonl" | PLC_CONTEXT_FLOOR_PCT=70 PLC_CONTEXT_WINDOW=1000000 bash "$HERE/close-gate-nudge.sh" Stop 2>/dev/null)"
  echo "$OUT" | grep -q '/clear' && ok "clear-nudge honors window-% floor" || no "clear-nudge window-% (got: $OUT)"

  # custom absolute floor honored: 90K over an 80K floor emits (default 150K would stay silent)
  rm -rf "$PLC_STATE_DIR"
  mktrans t-cust.jsonl 90000
  OUT="$(evn "$CNTMP/t-cust.jsonl" | PLC_CONTEXT_FLOOR=80000 bash "$HERE/close-gate-nudge.sh" Stop 2>/dev/null)"
  echo "$OUT" | grep -q '/clear' && ok "clear-nudge honors custom PLC_CONTEXT_FLOOR" || no "clear-nudge custom floor (got: $OUT)"

  # dirty tree still gets the ORIGINAL close-gate nudge, not the /clear one
  echo b > b.txt
  OUT="$(evn "$CNTMP/t-hi.jsonl" | bash "$HERE/close-gate-nudge.sh" Stop 2>/dev/null)"
  { echo "$OUT" | grep -q 'Definition of Done' && ! echo "$OUT" | grep -q '/clear before the next task'; } && ok "dirty tree keeps original close-gate nudge" || no "dirty tree nudge precedence (got: $OUT)"
)
rm -rf "$CNTMP" "$CNTMP-state"

echo
echo "=== tasklist-first.sh (enumerated-list guard, jq) ==="
TLTMP="$(mktemp -d)" || { echo "FATAL: mktemp -d failed (\$TLTMP)" >&2; exit 1; }
(
  export TMPDIR="$TLTMP"
  unset PLC_TASKLIST_GUARD PLC_TASKLIST_GATE_TASK PLC_TASKLIST_MIN
  MDIR="$TLTMP/plc-tasklist-guard"
  # Event builders (test harness only — python3 here is dev/CI, not the runtime hook).
  evEdit(){ python3 -c 'import json,sys; print(json.dumps({"session_id":sys.argv[1],"tool_name":"Edit","tool_input":{"file_path":sys.argv[2]}}))' "$1" "$2"; }
  evBash(){ python3 -c 'import json,sys; print(json.dumps({"session_id":sys.argv[1],"tool_name":"Bash","tool_input":{"command":sys.argv[2]}}))' "$1" "$2"; }
  evTask(){ python3 -c 'import json,sys; print(json.dumps({"session_id":sys.argv[1],"tool_name":"Task","tool_input":{}}))' "$1"; }
  evTC(){   python3 -c 'import json,sys; print(json.dumps({"session_id":sys.argv[1],"tool_name":"TaskCreate","tool_input":{}}))' "$1"; }
  evTodo(){ python3 -c 'import json,sys; print(json.dumps({"session_id":sys.argv[1],"tool_name":"TodoWrite","tool_input":{"todos":[{"content":"x"}]*int(sys.argv[2])}}))' "$1" "$2"; }

  # --- counter: one TaskCreate is NOT enough (count 1 < 3) -> edit still blocks ---
  evTC c1 | bash "$HERE/tasklist-first.sh" mark >/dev/null 2>&1
  evEdit c1 /tmp/x.md | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1; [ $? -eq 2 ] && ok "single TaskCreate does not satisfy guard (1<3)" || no "single TaskCreate should not satisfy"

  # --- counter: three TaskCreate calls -> enumerated list exists -> edit passes ---
  evTC c3 | bash "$HERE/tasklist-first.sh" mark >/dev/null 2>&1
  evTC c3 | bash "$HERE/tasklist-first.sh" mark >/dev/null 2>&1
  evTC c3 | bash "$HERE/tasklist-first.sh" mark >/dev/null 2>&1
  { [ -e "$MDIR/c3.seen" ]; } && ok "3 TaskCreate calls set the seen marker" || no "3 TaskCreate should set seen"
  evEdit c3 /tmp/x.md | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1; [ $? -eq 0 ] && ok "allows edit after 3-task list" || no "allows after 3-task list"

  # --- TodoWrite shape: length >= 3 satisfies in one call; length 1 does not ---
  evTodo t3 3 | bash "$HERE/tasklist-first.sh" mark >/dev/null 2>&1
  { [ -e "$MDIR/t3.seen" ]; } && ok "TodoWrite len>=3 sets seen in one call" || no "TodoWrite len>=3 sets seen"
  evTodo t1 1 | bash "$HERE/tasklist-first.sh" mark >/dev/null 2>&1
  { [ ! -e "$MDIR/t1.seen" ]; } && ok "TodoWrite len 1 does not set seen" || no "TodoWrite len 1 should not set seen"

  # --- the no-primitive host. No mark ever fires, because the host has no task tool.
  # This is the case the guard used to handle by blocking once and then permitting
  # everything in silence — enforcement in the transcript, nothing in reality.
  PROJ="$TLTMP/proj"; mkdir -p "$PROJ/.claude"
  ART="$PROJ/.claude/tasklist.md"
  evEditC(){ python3 -c 'import json,sys; print(json.dumps({"session_id":sys.argv[1],"cwd":sys.argv[2],"tool_name":"Edit","tool_input":{"file_path":sys.argv[3]}}))' "$1" "$PROJ" "$2"; }

  # 1. first gated call blocks once AND hands over a nonce to transcribe
  ERR="$TLTMP/np.err"
  evEditC np /tmp/x.md | bash "$HERE/tasklist-first.sh" check >/dev/null 2>"$ERR"; RC=$?
  NV="$(grep -o 'plc-tasklist: [0-9a-f]*' "$ERR" 2>/dev/null | cut -d' ' -f2 || true)"
  { [ "$RC" -eq 2 ] && [ -n "$NV" ]; } \
    && ok "no-primitive host blocks once and mints a nonce" \
    || no "expected exit 2 carrying a nonce (rc=$RC nonce='$NV')"
  grep -q "\.claude/tasklist\.md" "$ERR" \
    && ok "block message names the artifact path" \
    || no "block message must name .claude/tasklist.md"

  # 2. THE FIX: after that block the guard must not go silent. Every later gated call
  #    reports UNVERIFIED — allowed, but never indistinguishable from a verified pass.
  # No `|| true` inside the substitution: it would be what $? reports, pinning RC to 0 and
  # killing the failing half of this assertion. The script runs without -e.
  OUT="$(evEditC np /tmp/y.md | bash "$HERE/tasklist-first.sh" check 2>/dev/null)"; RC=$?
  { [ "$RC" -eq 0 ] && printf '%s' "$OUT" | grep -q 'UNVERIFIED'; } \
    && ok "post-block calls report UNVERIFIED instead of silence" \
    || no "expected an UNVERIFIED payload (rc=$RC out='$OUT')"
  # The FIELDS are the assertion, not just "some JSON came out". `allow` proceeds WITHOUT
  # the user's permission prompt (an auto-approval the guard has no business granting), and
  # `permissionDecisionReason` is only documented to reach Claude on deny/ask — so the first
  # version of this payload silently auto-approved every gated call and told no one.
  printf '%s' "$OUT" | jq -e '.hookSpecificOutput.permissionDecision=="defer"' >/dev/null 2>&1 \
    && ok "UNVERIFIED payload defers (does not auto-approve past the permission prompt)" \
    || no "permissionDecision must be 'defer' — 'allow' bypasses the user's prompt"
  printf '%s' "$OUT" | jq -e '(.hookSpecificOutput.additionalContext//"")|test("UNVERIFIED")' >/dev/null 2>&1 \
    && ok "notice rides additionalContext (the field that reaches the model)" \
    || no "UNVERIFIED must be in additionalContext, not permissionDecisionReason"
  printf '%s' "$OUT" | jq -e 'has("hookSpecificOutput") and (.hookSpecificOutput|has("permissionDecisionReason")|not)' >/dev/null 2>&1 \
    && ok "no permissionDecisionReason under defer (undocumented delivery)" \
    || no "permissionDecisionReason is not delivered under defer — do not rely on it"

  # 3. the portable artifact satisfies the guard with no task tool anywhere in sight
  printf '<!-- plc-tasklist: %s -->\n- [ ] a\n- [ ] b\n- [x] c\n' "$NV" > "$ART"
  OUT="$(evEditC np /tmp/z.md | bash "$HERE/tasklist-first.sh" check 2>&1)"; RC=$?
  { [ "$RC" -eq 0 ] && [ -z "$OUT" ]; } \
    && ok "valid artifact satisfies the guard silently" \
    || no "valid artifact should allow with no output (rc=$RC out='$OUT')"

  # 4. too few steps is not a list
  printf '<!-- plc-tasklist: %s -->\n- [ ] only one\n' "$NV" > "$ART"
  evEditC np /tmp/z.md | bash "$HERE/tasklist-first.sh" check 2>/dev/null | grep -q 'UNVERIFIED' \
    && ok "fewer than 3 checkbox lines does not satisfy" \
    || no "1 checkbox line should not satisfy"

  # 5. LAST PHASE'S list must not satisfy THIS phase. The nonce is why this is checked
  #    without consulting an mtime — a checked-out tree may sync through a file-syncing daemon that re-touches
  #    files, so a timestamp is not evidence that anything was rewritten.
  printf '<!-- plc-tasklist: deadbeefcafe -->\n- [ ] a\n- [ ] b\n- [ ] c\n' > "$ART"
  evEditC np /tmp/z.md | bash "$HERE/tasklist-first.sh" check 2>/dev/null | grep -q 'UNVERIFIED' \
    && ok "a stale nonce from a previous phase does not satisfy" \
    || no "stale nonce must not satisfy"

  # 6. writing the artifact is never gated, or the guard deadlocks: the only way to satisfy
  #    it is a Write, and Write is what it gates.
  evEditC np2 "$ART" | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1; RC=$?
  [ "$RC" -eq 0 ] && ok "writing the artifact itself is exempt" \
                  || no "artifact write must never block (rc=$RC)"

  # --- block-once on file edit with no list ---
  evEdit e1 /tmp/x.md | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 2 ] && [ -f "$MDIR/e1.nudged" ]; } && ok "blocks first edit without list" || no "blocks first edit without list"
  evEdit e1 /tmp/x.md | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1; [ $? -eq 0 ] && ok "block-once (second edit passes)" || no "block-once"

  # --- Bash: git commit/push is gated; read-only Bash is not ---
  evBash b1 'git commit -m "feat: x"' | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1; [ $? -eq 2 ] && ok "blocks git commit without list" || no "blocks git commit without list"
  evBash b2 'git push origin feat/x'  | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1; [ $? -eq 2 ] && ok "blocks git push without list" || no "blocks git push without list"
  evBash b3 'git status'              | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 0 ] && [ ! -f "$MDIR/b3.nudged" ]; } && ok "read-only Bash (git status) not gated" || no "read-only Bash should pass"
  evBash b4 'ls -la'                  | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1; [ $? -eq 0 ] && ok "non-git Bash not gated" || no "non-git Bash should pass"

  # --- per-phase re-arm: a close-gate run wipes markers so the next phase re-blocks ---
  # helper: give a session a satisfied 3-task list (seen marker set).
  arm3(){ evTC "$1" | bash "$HERE/tasklist-first.sh" mark >/dev/null 2>&1
          evTC "$1" | bash "$HERE/tasklist-first.sh" mark >/dev/null 2>&1
          evTC "$1" | bash "$HERE/tasklist-first.sh" mark >/dev/null 2>&1; }

  # re-arm keys on a MARKER THE GATE WRITES, never on a token in the command string.
  # The whole point is that the two are different facts. `wc -l` on the gate file and `git add`
  # of the gate file each used to count as a phase close — observed live four times while this
  # rewrite was being written — and no amount of narrowing "the name appears in a string" ever
  # turns it into "the thing ran".
  RREPO="$TLTMP/rearm-repo"; mkdir -p "$RREPO/.claude/.gate-runs"
  GM="$RREPO/.claude/.gate-runs/last-run"
  # Event carrying a cwd, so the hook resolves the marker inside the fixture and never touches
  # the checkout this suite is running from.
  evBashCwd(){ python3 -c 'import json,sys; print(json.dumps({"session_id":sys.argv[1],"cwd":sys.argv[3],"tool_name":"Bash","tool_input":{"command":sys.argv[2]}}))' "$1" "$2" "$3"; }
  mkmark(){ printf 'run=%s\nexit=%s\nphase=T1\nhead=deadbeef\nat=1970-01-01T00:00:00Z\n' "$1" "$2" > "$GM"; }

  # --- the two commands that used to false-re-arm: reading and staging the gate file ---
  arm3 rg1; rm -f "$GM"
  evBashCwd rg1 'wc -l scripts/close-gate.sh' "$RREPO" | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1
  { [ -e "$MDIR/rg1.seen" ]; } && ok "reading the gate file does NOT re-arm (regression)" || no "false re-arm: wc -l on the gate file"

  arm3 rg2; rm -f "$GM"
  evBashCwd rg2 'git add scripts/close-gate.sh' "$RREPO" | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1
  { [ -e "$MDIR/rg2.seen" ]; } && ok "staging the gate file does NOT re-arm (regression)" || no "false re-arm: git add of the gate file"

  # --- the command NAME alone is no longer a signal at all ---
  arm3 rg3; rm -f "$GM"
  evBashCwd rg3 'make task-done' "$RREPO" | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1
  { [ -e "$MDIR/rg3.seen" ]; } && ok "'make task-done' with no gate marker does NOT re-arm" || no "token scan still live"

  # --- a real, passing gate run DOES re-arm ---
  arm3 rg4; mkmark run-aaa 0
  evBashCwd rg4 'echo unrelated' "$RREPO" | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 0 ] && [ ! -e "$MDIR/rg4.seen" ] && [ ! -e "$MDIR/rg4.count" ] && [ ! -e "$MDIR/rg4.nudged" ]; } \
    && ok "a passing gate marker re-arms (wipes seen/count/nudged)" || no "passing gate marker should re-arm"
  evEdit rg4 /tmp/x.md | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1; [ $? -eq 2 ] && ok "next edit re-blocks after re-arm" || no "next edit should re-block"

  # --- the SAME run re-arms exactly once (the per-run id is what makes a stale marker inert) ---
  arm3 rg5   # marker still says run-aaa, already consumed by rg4's session? no — per session.
  evBashCwd rg5 'echo unrelated' "$RREPO" | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1
  { [ ! -e "$MDIR/rg5.seen" ]; } && ok "a fresh session consumes the marker once" || no "fresh session should re-arm once"
  arm3 rg5   # re-satisfy; same marker, same run id -> must NOT re-arm again
  evBashCwd rg5 'echo unrelated' "$RREPO" | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1
  { [ -e "$MDIR/rg5.seen" ]; } && ok "the same gate run does NOT re-arm twice" || no "stale marker re-armed again"

  # --- a FAILING gate run must not re-arm. The old PreToolUse token scan fired when the gate
  #     command was ABOUT to run, so a gate that then failed re-armed exactly like a passing one.
  arm3 rg6; mkmark run-bbb 1
  evBashCwd rg6 'echo unrelated' "$RREPO" | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1
  { [ -e "$MDIR/rg6.seen" ]; } && ok "a FAILING gate run does NOT re-arm (timing defect)" || no "failing gate re-armed"
  # ...and it is still consumed, so the next call does not reconsider it.
  arm3 rg7; mkmark run-ccc 1
  evBashCwd rg7 'echo unrelated' "$RREPO" | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1
  evBashCwd rg7 'echo unrelated' "$RREPO" | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1
  { [ -e "$MDIR/rg7.seen" ]; } && ok "a failing gate run stays non-re-arming on re-read" || no "failing marker re-armed on second look"

  # escape hatch: PLC_TASKLIST_REARM=0 -> even a fresh passing marker does not reset.
  arm3 rg8; mkmark run-ddd 0
  evBashCwd rg8 'echo unrelated' "$RREPO" | PLC_TASKLIST_REARM=0 bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1
  { [ -e "$MDIR/rg8.seen" ]; } && ok "PLC_TASKLIST_REARM=0 disables re-arm" || no "REARM=0 should keep seen"

  # --- Task (subagent dispatch): off by default, gated when PLC_TASKLIST_GATE_TASK=1 ---
  evTask k1 | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 0 ] && [ ! -f "$MDIR/k1.nudged" ]; } && ok "Task dispatch not gated by default (intent-gate Explore safe)" || no "Task should pass by default"
  evTask k2 | PLC_TASKLIST_GATE_TASK=1 bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1; [ $? -eq 2 ] && ok "Task gated when PLC_TASKLIST_GATE_TASK=1" || no "Task gated when flag on"

  # --- RESUME.md exempt even with no list (deadlock guard) ---
  evEdit r1 /some/proj/RESUME.md | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 0 ] && [ ! -f "$MDIR/r1.nudged" ]; } && ok "RESUME.md write exempt" || no "RESUME.md exempt"

  # --- escape hatch ---
  evEdit h1 /tmp/x.md | PLC_TASKLIST_GUARD=0 bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1; [ $? -eq 0 ] && ok "PLC_TASKLIST_GUARD=0 disables" || no "escape hatch"

  # --- fail-open: malformed JSON / missing session_id ---
  echo '{ not json' | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1; [ $? -eq 0 ] && ok "fail-open on malformed input" || no "fail-open malformed"
  echo '{}' | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1; [ $? -eq 0 ] && ok "fail-open on missing session_id" || no "fail-open missing sid"
)
rm -rf "$TLTMP"

echo
echo "=== frontmatter YAML parses ==="
if python3 - "$HERE/.." <<'PY'
import yaml, sys
raw=open(sys.argv[1] + "/SKILL.md").read()
d=yaml.safe_load(raw.split("---",2)[1])
h=d.get("hooks",{})
assert "PreToolUse" in h and "Stop" in h and "SubagentStop" in h, "missing hook events: %s"%list(h)
root="${QODER_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}/skills/project-lifecycle/hooks/"
cmds={
  "PreToolUse": h["PreToolUse"][0]["hooks"][0]["command"],
  "Stop": h["Stop"][0]["hooks"][0]["command"],
  "SubagentStop": h["SubagentStop"][0]["hooks"][0]["command"],
}
assert cmds["PreToolUse"]==root+"guard.sh", cmds["PreToolUse"]
assert cmds["Stop"]==root+"close-gate-nudge.sh Stop", cmds["Stop"]
assert cmds["SubagentStop"]==root+"close-gate-nudge.sh SubagentStop", cmds["SubagentStop"]
pre={m.get("matcher",""): m["hooks"][0]["command"] for m in h["PreToolUse"]}
assert pre.get("TaskCreate|TodoWrite")==root+"tasklist-first.sh mark", pre
# the check hook fires on a single combined matcher (distinct from guard's "Bash" key);
# assert it exists and its matcher covers commit/edit/subagent surfaces.
checks=[mm for mm,c in pre.items() if c==root+"tasklist-first.sh check"]
assert len(checks)==1, ("expected exactly one check matcher", pre)
cm=checks[0]
for tok in ("Bash","Task","Edit","Write","MultiEdit","NotebookEdit"):
    assert tok in cm, ("check matcher missing "+tok, cm)
PY
then ok "SKILL.md frontmatter hooks block valid (all 3 commands)"; else no "SKILL.md frontmatter hooks block valid (all 3 commands)"; fi

echo
echo "=== context-floor.sh (enforce-only, self-arming) ==="
CFTMP="$(mktemp -d)" || { echo "FATAL: mktemp -d failed (\$CFTMP)" >&2; exit 1; }
(
  export TMPDIR="$CFTMP"
  # hermetic: don't inherit a caller's floor config (e.g. settings.json env block)
  unset PLC_CONTEXT_FLOOR PLC_CONTEXT_FLOOR_PCT PLC_CONTEXT_FLOOR_STEP PLC_CONTEXT_WINDOW
  mktrans(){ python3 -c 'import json,sys; open(sys.argv[1],"w").write(json.dumps({"type":"assistant","message":{"usage":{"input_tokens":int(sys.argv[2]),"cache_read_input_tokens":0,"cache_creation_input_tokens":0}}})+"\n")' "$1" "$2"; }
  evc(){ python3 -c 'import json,sys; print(json.dumps({"session_id":sys.argv[2],"transcript_path":sys.argv[1],"cwd":sys.argv[3]}))' "$1" "$2" "$3"; }
  cf(){ bash "$HERE/context-floor.sh"; }   # reads stdin; PreToolUse:Edit|Write
  M="$CFTMP/plc-context-floor"

  # under floor -> allow, no marker
  T="$CFTMP/below.jsonl"; mktrans "$T" 120000
  evc "$T" b "$CFTMP" | cf >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 0 ] && [ ! -f "$M/b.marker" ]; } && ok "allows under floor" || no "allows under floor"

  # over floor, no RESUME -> self-arm + block (exit 2)
  T="$CFTMP/over.jsonl"; mktrans "$T" 160000
  evc "$T" a "$CFTMP" | cf >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 2 ] && [ -f "$M/a.marker" ]; } && ok "self-arms + blocks over floor (no RESUME)" || no "self-arms + blocks over floor"

  # still blocked while RESUME stale (older than marker)
  echo stale > "$CFTMP/RESUME.md"; sleep 1; touch "$M/a.marker"   # bump marker newer than RESUME
  evc "$T" a "$CFTMP" | cf >/dev/null 2>&1; [ $? -eq 2 ] && ok "stays blocked while RESUME stale" || no "stays blocked while RESUME stale"

  # fresh RESUME -> clear marker + write clearedat + allow
  sleep 1; echo fresh > "$CFTMP/RESUME.md"
  evc "$T" a "$CFTMP" | cf >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 0 ] && [ ! -f "$M/a.marker" ] && [ -f "$M/a.clearedat" ]; } && ok "clears on fresh RESUME" || no "clears on fresh RESUME"

  # post-clear grace: occ < clearedat+step -> allow, no re-arm
  CA="$(cat "$M/a.clearedat")"
  T="$CFTMP/grace.jsonl"; mktrans "$T" $((CA + 10000))
  evc "$T" a "$CFTMP" | cf >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 0 ] && [ ! -f "$M/a.marker" ]; } && ok "post-clear grace allows (<clearedat+step)" || no "post-clear grace allows"

  # past grace: occ >= clearedat+step -> re-arm + block
  T="$CFTMP/regrow.jsonl"; mktrans "$T" $((CA + 35000))
  evc "$T" a "$CFTMP" | cf >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 2 ] && [ -f "$M/a.marker" ]; } && ok "re-arms + blocks past grace step" || no "re-arms past grace step"

  # escape hatch: PLC_CONTEXT_FLOOR=0 -> allow even far over floor
  T="$CFTMP/dis.jsonl"; mktrans "$T" 500000
  evc "$T" dis "$CFTMP" | PLC_CONTEXT_FLOOR=0 bash "$HERE/context-floor.sh" >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 0 ] && [ ! -f "$M/dis.marker" ]; } && ok "PLC_CONTEXT_FLOOR=0 disables" || no "PLC_CONTEXT_FLOOR=0 disables"

  # custom floor 80k -> blocks at 90k
  T="$CFTMP/c.jsonl"; mktrans "$T" 90000
  evc "$T" c "$CFTMP" | PLC_CONTEXT_FLOOR=80000 bash "$HERE/context-floor.sh" >/dev/null 2>&1; [ $? -eq 2 ] && ok "custom PLC_CONTEXT_FLOOR honored" || no "custom PLC_CONTEXT_FLOOR honored"

  # window-% mode: 70% of 1M = 700K floor -> 650K allows (under), 720K blocks (over)
  T="$CFTMP/pctlo.jsonl"; mktrans "$T" 650000
  evc "$T" pctlo "$CFTMP" | PLC_CONTEXT_FLOOR_PCT=70 PLC_CONTEXT_WINDOW=1000000 bash "$HERE/context-floor.sh" >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 0 ] && [ ! -f "$M/pctlo.marker" ]; } && ok "window-% mode allows under %-floor" || no "window-% mode allows under %-floor"
  T="$CFTMP/pcthi.jsonl"; mktrans "$T" 720000
  evc "$T" pcthi "$CFTMP" | PLC_CONTEXT_FLOOR_PCT=70 PLC_CONTEXT_WINDOW=1000000 bash "$HERE/context-floor.sh" >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 2 ] && [ -f "$M/pcthi.marker" ]; } && ok "window-% mode blocks over %-floor" || no "window-% mode blocks over %-floor"

  # window-% overrides absolute: 720K under 70% of 1M allows even though >150K abs default
  T="$CFTMP/pctov.jsonl"; mktrans "$T" 680000
  evc "$T" pctov "$CFTMP" | PLC_CONTEXT_FLOOR_PCT=70 PLC_CONTEXT_WINDOW=1000000 PLC_CONTEXT_FLOOR=150000 bash "$HERE/context-floor.sh" >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 0 ] && [ ! -f "$M/pctov.marker" ]; } && ok "window-% overrides absolute floor" || no "window-% overrides absolute floor"

  # disable: PLC_CONTEXT_FLOOR=0 AND PLC_CONTEXT_FLOOR_PCT=0 -> allow far over
  T="$CFTMP/pctdis.jsonl"; mktrans "$T" 800000
  evc "$T" pctdis "$CFTMP" | PLC_CONTEXT_FLOOR=0 PLC_CONTEXT_FLOOR_PCT=0 bash "$HERE/context-floor.sh" >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 0 ] && [ ! -f "$M/pctdis.marker" ]; } && ok "both-zero disables" || no "both-zero disables"

  # fail-open: malformed transcript -> allow
  echo "{ not json" > "$CFTMP/bad.jsonl"
  evc "$CFTMP/bad.jsonl" badc "$CFTMP" | cf >/dev/null 2>&1; [ $? -eq 0 ] && ok "fail-open on malformed transcript" || no "fail-open on malformed transcript"

  # fail-open: missing usage field -> allow
  python3 -c 'open("'"$CFTMP"'/nousage.jsonl","w").write("{\"type\":\"assistant\",\"message\":{}}\n")'
  evc "$CFTMP/nousage.jsonl" nu "$CFTMP" | cf >/dev/null 2>&1; [ $? -eq 0 ] && ok "fail-open on missing usage" || no "fail-open on missing usage"

  # RESUME exemption: editing the checkpoint file itself is never blocked (no deadlock)
  evf(){ python3 -c 'import json,sys; print(json.dumps({"session_id":sys.argv[2],"transcript_path":sys.argv[1],"cwd":sys.argv[3],"tool_input":{"file_path":sys.argv[4]}}))' "$1" "$2" "$3" "$4"; }
  T="$CFTMP/exempt.jsonl"; mktrans "$T" 300000   # far over floor
  evf "$T" ex "$CFTMP" "$CFTMP/RESUME.md" | cf >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 0 ] && [ ! -f "$M/ex.marker" ]; } && ok "RESUME.md write exempt from block (no deadlock)" || no "RESUME.md write exempt"
)
rm -rf "$CFTMP"

echo
echo "=== self-verification: the verdict is real ==="
# The suite guards every hook in this plugin, so its own exit code has to mean something.
# Re-invoke this script in each self-test mode and assert on the CODE, not on the output.
SELF="${BASH_SOURCE[0]}"
bash "$SELF" --selftest-fail >/dev/null 2>&1 \
  && no "a failed assertion inside a subshell must make the suite exit non-zero" \
  || ok "a failed assertion inside a subshell makes the suite exit non-zero"
bash "$SELF" --selftest-clean >/dev/null 2>&1 \
  && ok "a passed assertion inside a subshell exits zero (the failing case is not just always-red)" \
  || no "a passed assertion inside a subshell must exit zero"

verdict
