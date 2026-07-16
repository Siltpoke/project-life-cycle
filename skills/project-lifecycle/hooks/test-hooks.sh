#!/usr/bin/env bash
# Deterministic tests for the project-lifecycle frontmatter hook scripts.
# Run before committing hook changes. No fresh session needed — these exercise the scripts directly.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASS=0; FAIL=0
ok(){ echo "  PASS: $1"; PASS=$((PASS+1)); }
no(){ echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

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
# Regression: the flag/word appearing inside a commit MESSAGE must NOT false-block (shlex fix).
ev 'git commit -m "docs: guard blocks the --no-verify bypass"' | bash "$HERE/guard.sh" >/dev/null 2>&1; [ $? -eq 0 ] && ok "allows --no-verify inside a commit message (shlex)" || no "false-positive: --no-verify in message"
ev 'git commit -m "note: push to main later"' | bash "$HERE/guard.sh" >/dev/null 2>&1; [ $? -eq 0 ] && ok "allows 'main' inside a commit message (shlex)" || no "false-positive: main in message"

echo "=== close-gate-nudge.sh ==="
# On this repo (branch main, not feat/phase-*) → must be silent.
OUT="$(echo '{}' | bash "$HERE/close-gate-nudge.sh" Stop 2>/dev/null)"
[ -z "$OUT" ] && ok "silent off a phase branch" || no "silent off a phase branch (got: $OUT)"

# Integration: temp git repo on a feat/phase-* branch + dirty → must emit JSON.
TMP="$(mktemp -d)"
(
  cd "$TMP"
  git init -q && git config user.email t@t && git config user.name t
  echo a > a.txt && git add a.txt && git commit -qm init
  git checkout -q -b feat/phase-1.0-test
  echo b > b.txt   # uncommitted → dirty
  rm -rf .claude
  OUT="$(echo '{}' | bash "$HERE/close-gate-nudge.sh" Stop 2>/dev/null)"
  echo "$OUT" | python3 -c 'import json,sys
d=json.load(sys.stdin)
a=d["hookSpecificOutput"]["additionalContext"]
assert d["hookSpecificOutput"]["hookEventName"]=="Stop"
assert "Definition of Done" in a and "feat/phase-1.0-test" in a
print("  PASS: emits nudge JSON on dirty phase branch")' || echo "  FAIL: emits nudge JSON on dirty phase branch (got: $OUT)"
  # Throttle: second call within 10 min → silent.
  OUT2="$(echo '{}' | bash "$HERE/close-gate-nudge.sh" Stop 2>/dev/null)"
  [ -z "$OUT2" ] && echo "  PASS: throttled (silent within 10 min)" || echo "  FAIL: throttle (got: $OUT2)"
)
rm -rf "$TMP"

# D2 /clear nudge: clean tree + test-evidence (task close just passed) + occupancy vs floor.
CNTMP="$(mktemp -d)"
(
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
  [ -z "$OUT" ] && echo "  PASS: clear-nudge silent under floor" || echo "  FAIL: clear-nudge silent under floor (got: $OUT)"

  # floor disabled → silent even far over
  mktrans t-dis.jsonl 500000
  OUT="$(evn "$CNTMP/t-dis.jsonl" | PLC_CONTEXT_FLOOR=0 bash "$HERE/close-gate-nudge.sh" Stop 2>/dev/null)"
  [ -z "$OUT" ] && echo "  PASS: clear-nudge silent when floor disabled" || echo "  FAIL: clear-nudge floor=0 (got: $OUT)"

  # no transcript_path in event → silent (fail-open)
  OUT="$(echo '{}' | bash "$HERE/close-gate-nudge.sh" Stop 2>/dev/null)"
  [ -z "$OUT" ] && echo "  PASS: clear-nudge fail-open without transcript" || echo "  FAIL: clear-nudge fail-open (got: $OUT)"

  # malformed (non-JSON) event on stdin → silent + exit 0 (fail-open)
  OUT="$(printf '{ not json' | bash "$HERE/close-gate-nudge.sh" Stop 2>/dev/null)"; RC=$?
  { [ -z "$OUT" ] && [ "$RC" -eq 0 ]; } && echo "  PASS: clear-nudge fail-open on malformed event JSON" || echo "  FAIL: clear-nudge malformed event (rc=$RC, got: $OUT)"

  # over floor (200K ≥ 150K) → emits /clear nudge JSON with occupancy
  mktrans t-hi.jsonl 200000
  OUT="$(evn "$CNTMP/t-hi.jsonl" | bash "$HERE/close-gate-nudge.sh" Stop 2>/dev/null)"
  echo "$OUT" | python3 -c 'import json,sys
d=json.load(sys.stdin)
a=d["hookSpecificOutput"]["additionalContext"]
assert d["hookSpecificOutput"]["hookEventName"]=="Stop"
assert "/clear" in a and "200K" in a and "150K" in a
print("  PASS: clear-nudge emits over floor (clean+tested)")' 2>/dev/null || echo "  FAIL: clear-nudge emits over floor (got: $OUT)"

  # throttled second call → silent
  OUT="$(evn "$CNTMP/t-hi.jsonl" | bash "$HERE/close-gate-nudge.sh" Stop 2>/dev/null)"
  [ -z "$OUT" ] && echo "  PASS: clear-nudge throttled (silent within 10 min)" || echo "  FAIL: clear-nudge throttle (got: $OUT)"

  # window-% mode: 70% of 1M = 700K floor → 720K emits (after clearing throttle)
  rm -f .claude/.clear-nudge-last
  mktrans t-pct.jsonl 720000
  OUT="$(evn "$CNTMP/t-pct.jsonl" | PLC_CONTEXT_FLOOR_PCT=70 PLC_CONTEXT_WINDOW=1000000 bash "$HERE/close-gate-nudge.sh" Stop 2>/dev/null)"
  echo "$OUT" | grep -q '/clear' && echo "  PASS: clear-nudge honors window-% floor" || echo "  FAIL: clear-nudge window-% (got: $OUT)"

  # custom absolute floor honored: 90K over an 80K floor emits (default 150K would stay silent)
  rm -f .claude/.clear-nudge-last
  mktrans t-cust.jsonl 90000
  OUT="$(evn "$CNTMP/t-cust.jsonl" | PLC_CONTEXT_FLOOR=80000 bash "$HERE/close-gate-nudge.sh" Stop 2>/dev/null)"
  echo "$OUT" | grep -q '/clear' && echo "  PASS: clear-nudge honors custom PLC_CONTEXT_FLOOR" || echo "  FAIL: clear-nudge custom floor (got: $OUT)"

  # dirty tree still gets the ORIGINAL close-gate nudge, not the /clear one
  echo b > b.txt
  OUT="$(evn "$CNTMP/t-hi.jsonl" | bash "$HERE/close-gate-nudge.sh" Stop 2>/dev/null)"
  { echo "$OUT" | grep -q 'Definition of Done' && ! echo "$OUT" | grep -q '/clear before the next task'; } && echo "  PASS: dirty tree keeps original close-gate nudge" || echo "  FAIL: dirty tree nudge precedence (got: $OUT)"
)
rm -rf "$CNTMP"

echo
echo "=== tasklist-first.sh (enumerated-list guard, jq) ==="
TLTMP="$(mktemp -d)"
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
  evEdit c1 /tmp/x.md | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1; [ $? -eq 2 ] && echo "  PASS: single TaskCreate does not satisfy guard (1<3)" || echo "  FAIL: single TaskCreate should not satisfy"

  # --- counter: three TaskCreate calls -> enumerated list exists -> edit passes ---
  evTC c3 | bash "$HERE/tasklist-first.sh" mark >/dev/null 2>&1
  evTC c3 | bash "$HERE/tasklist-first.sh" mark >/dev/null 2>&1
  evTC c3 | bash "$HERE/tasklist-first.sh" mark >/dev/null 2>&1
  { [ -e "$MDIR/c3.seen" ]; } && echo "  PASS: 3 TaskCreate calls set the seen marker" || echo "  FAIL: 3 TaskCreate should set seen"
  evEdit c3 /tmp/x.md | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1; [ $? -eq 0 ] && echo "  PASS: allows edit after 3-task list" || echo "  FAIL: allows after 3-task list"

  # --- TodoWrite shape: length >= 3 satisfies in one call; length 1 does not ---
  evTodo t3 3 | bash "$HERE/tasklist-first.sh" mark >/dev/null 2>&1
  { [ -e "$MDIR/t3.seen" ]; } && echo "  PASS: TodoWrite len>=3 sets seen in one call" || echo "  FAIL: TodoWrite len>=3 sets seen"
  evTodo t1 1 | bash "$HERE/tasklist-first.sh" mark >/dev/null 2>&1
  { [ ! -e "$MDIR/t1.seen" ]; } && echo "  PASS: TodoWrite len 1 does not set seen" || echo "  FAIL: TodoWrite len 1 should not set seen"

  # --- block-once on file edit with no list ---
  evEdit e1 /tmp/x.md | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 2 ] && [ -f "$MDIR/e1.nudged" ]; } && echo "  PASS: blocks first edit without list" || echo "  FAIL: blocks first edit without list"
  evEdit e1 /tmp/x.md | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1; [ $? -eq 0 ] && echo "  PASS: block-once (second edit passes)" || echo "  FAIL: block-once"

  # --- Bash: git commit/push is gated; read-only Bash is not ---
  evBash b1 'git commit -m "feat: x"' | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1; [ $? -eq 2 ] && echo "  PASS: blocks git commit without list" || echo "  FAIL: blocks git commit without list"
  evBash b2 'git push origin feat/x'  | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1; [ $? -eq 2 ] && echo "  PASS: blocks git push without list" || echo "  FAIL: blocks git push without list"
  evBash b3 'git status'              | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 0 ] && [ ! -f "$MDIR/b3.nudged" ]; } && echo "  PASS: read-only Bash (git status) not gated" || echo "  FAIL: read-only Bash should pass"
  evBash b4 'ls -la'                  | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1; [ $? -eq 0 ] && echo "  PASS: non-git Bash not gated" || echo "  FAIL: non-git Bash should pass"

  # --- per-phase re-arm: a close-gate run wipes markers so the next phase re-blocks ---
  # helper: give a session a satisfied 3-task list (seen marker set).
  arm3(){ evTC "$1" | bash "$HERE/tasklist-first.sh" mark >/dev/null 2>&1
          evTC "$1" | bash "$HERE/tasklist-first.sh" mark >/dev/null 2>&1
          evTC "$1" | bash "$HERE/tasklist-first.sh" mark >/dev/null 2>&1; }

  arm3 rg1
  evBash rg1 'make task-done' | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 0 ] && [ ! -e "$MDIR/rg1.seen" ] && [ ! -e "$MDIR/rg1.count" ] && [ ! -e "$MDIR/rg1.nudged" ]; } \
    && echo "  PASS: 'make task-done' re-arms (wipes seen/count/nudged)" || echo "  FAIL: task-done should re-arm"
  evEdit rg1 /tmp/x.md | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1; [ $? -eq 2 ] && echo "  PASS: next edit re-blocks after re-arm" || echo "  FAIL: next edit should re-block"

  arm3 rg2
  evBash rg2 'make phase-done PHASE=1.2' | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1
  { [ ! -e "$MDIR/rg2.seen" ]; } && echo "  PASS: 'make phase-done' re-arms" || echo "  FAIL: phase-done should re-arm"

  arm3 rg3
  evBash rg3 'bash scripts/close-gate.sh task-done' | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1
  { [ ! -e "$MDIR/rg3.seen" ]; } && echo "  PASS: 'close-gate.sh' path re-arms" || echo "  FAIL: close-gate.sh should re-arm"

  # false-positive guard: the token inside a commit MESSAGE keeps its quote after word-split -> no re-arm.
  arm3 rg4
  evBash rg4 'git commit -m "task-done: ship it"' | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1
  { [ -e "$MDIR/rg4.seen" ]; } && echo "  PASS: 'task-done' inside a commit message does NOT re-arm" || echo "  FAIL: false re-arm from commit message"

  # escape hatch: PLC_TASKLIST_REARM=0 -> close-gate run does not reset.
  arm3 rg5
  evBash rg5 'make task-done' | PLC_TASKLIST_REARM=0 bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1
  { [ -e "$MDIR/rg5.seen" ]; } && echo "  PASS: PLC_TASKLIST_REARM=0 disables re-arm" || echo "  FAIL: REARM=0 should keep seen"

  # --- Task (subagent dispatch): off by default, gated when PLC_TASKLIST_GATE_TASK=1 ---
  evTask k1 | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 0 ] && [ ! -f "$MDIR/k1.nudged" ]; } && echo "  PASS: Task dispatch not gated by default (intent-gate Explore safe)" || echo "  FAIL: Task should pass by default"
  evTask k2 | PLC_TASKLIST_GATE_TASK=1 bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1; [ $? -eq 2 ] && echo "  PASS: Task gated when PLC_TASKLIST_GATE_TASK=1" || echo "  FAIL: Task gated when flag on"

  # --- RESUME.md exempt even with no list (deadlock guard) ---
  evEdit r1 /some/proj/RESUME.md | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 0 ] && [ ! -f "$MDIR/r1.nudged" ]; } && echo "  PASS: RESUME.md write exempt" || echo "  FAIL: RESUME.md exempt"

  # --- escape hatch ---
  evEdit h1 /tmp/x.md | PLC_TASKLIST_GUARD=0 bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1; [ $? -eq 0 ] && echo "  PASS: PLC_TASKLIST_GUARD=0 disables" || echo "  FAIL: escape hatch"

  # --- fail-open: malformed JSON / missing session_id ---
  echo '{ not json' | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1; [ $? -eq 0 ] && echo "  PASS: fail-open on malformed input" || echo "  FAIL: fail-open malformed"
  echo '{}' | bash "$HERE/tasklist-first.sh" check >/dev/null 2>&1; [ $? -eq 0 ] && echo "  PASS: fail-open on missing session_id" || echo "  FAIL: fail-open missing sid"
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
CFTMP="$(mktemp -d)"
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
  { [ "$RC" -eq 0 ] && [ ! -f "$M/b.marker" ]; } && echo "  PASS: allows under floor" || echo "  FAIL: allows under floor"

  # over floor, no RESUME -> self-arm + block (exit 2)
  T="$CFTMP/over.jsonl"; mktrans "$T" 160000
  evc "$T" a "$CFTMP" | cf >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 2 ] && [ -f "$M/a.marker" ]; } && echo "  PASS: self-arms + blocks over floor (no RESUME)" || echo "  FAIL: self-arms + blocks over floor"

  # still blocked while RESUME stale (older than marker)
  echo stale > "$CFTMP/RESUME.md"; sleep 1; touch "$M/a.marker"   # bump marker newer than RESUME
  evc "$T" a "$CFTMP" | cf >/dev/null 2>&1; [ $? -eq 2 ] && echo "  PASS: stays blocked while RESUME stale" || echo "  FAIL: stays blocked while RESUME stale"

  # fresh RESUME -> clear marker + write clearedat + allow
  sleep 1; echo fresh > "$CFTMP/RESUME.md"
  evc "$T" a "$CFTMP" | cf >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 0 ] && [ ! -f "$M/a.marker" ] && [ -f "$M/a.clearedat" ]; } && echo "  PASS: clears on fresh RESUME" || echo "  FAIL: clears on fresh RESUME"

  # post-clear grace: occ < clearedat+step -> allow, no re-arm
  CA="$(cat "$M/a.clearedat")"
  T="$CFTMP/grace.jsonl"; mktrans "$T" $((CA + 10000))
  evc "$T" a "$CFTMP" | cf >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 0 ] && [ ! -f "$M/a.marker" ]; } && echo "  PASS: post-clear grace allows (<clearedat+step)" || echo "  FAIL: post-clear grace allows"

  # past grace: occ >= clearedat+step -> re-arm + block
  T="$CFTMP/regrow.jsonl"; mktrans "$T" $((CA + 35000))
  evc "$T" a "$CFTMP" | cf >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 2 ] && [ -f "$M/a.marker" ]; } && echo "  PASS: re-arms + blocks past grace step" || echo "  FAIL: re-arms past grace step"

  # escape hatch: PLC_CONTEXT_FLOOR=0 -> allow even far over floor
  T="$CFTMP/dis.jsonl"; mktrans "$T" 500000
  evc "$T" dis "$CFTMP" | PLC_CONTEXT_FLOOR=0 bash "$HERE/context-floor.sh" >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 0 ] && [ ! -f "$M/dis.marker" ]; } && echo "  PASS: PLC_CONTEXT_FLOOR=0 disables" || echo "  FAIL: PLC_CONTEXT_FLOOR=0 disables"

  # custom floor 80k -> blocks at 90k
  T="$CFTMP/c.jsonl"; mktrans "$T" 90000
  evc "$T" c "$CFTMP" | PLC_CONTEXT_FLOOR=80000 bash "$HERE/context-floor.sh" >/dev/null 2>&1; [ $? -eq 2 ] && echo "  PASS: custom PLC_CONTEXT_FLOOR honored" || echo "  FAIL: custom PLC_CONTEXT_FLOOR honored"

  # window-% mode: 70% of 1M = 700K floor -> 650K allows (under), 720K blocks (over)
  T="$CFTMP/pctlo.jsonl"; mktrans "$T" 650000
  evc "$T" pctlo "$CFTMP" | PLC_CONTEXT_FLOOR_PCT=70 PLC_CONTEXT_WINDOW=1000000 bash "$HERE/context-floor.sh" >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 0 ] && [ ! -f "$M/pctlo.marker" ]; } && echo "  PASS: window-% mode allows under %-floor" || echo "  FAIL: window-% mode allows under %-floor"
  T="$CFTMP/pcthi.jsonl"; mktrans "$T" 720000
  evc "$T" pcthi "$CFTMP" | PLC_CONTEXT_FLOOR_PCT=70 PLC_CONTEXT_WINDOW=1000000 bash "$HERE/context-floor.sh" >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 2 ] && [ -f "$M/pcthi.marker" ]; } && echo "  PASS: window-% mode blocks over %-floor" || echo "  FAIL: window-% mode blocks over %-floor"

  # window-% overrides absolute: 720K under 70% of 1M allows even though >150K abs default
  T="$CFTMP/pctov.jsonl"; mktrans "$T" 680000
  evc "$T" pctov "$CFTMP" | PLC_CONTEXT_FLOOR_PCT=70 PLC_CONTEXT_WINDOW=1000000 PLC_CONTEXT_FLOOR=150000 bash "$HERE/context-floor.sh" >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 0 ] && [ ! -f "$M/pctov.marker" ]; } && echo "  PASS: window-% overrides absolute floor" || echo "  FAIL: window-% overrides absolute floor"

  # disable: PLC_CONTEXT_FLOOR=0 AND PLC_CONTEXT_FLOOR_PCT=0 -> allow far over
  T="$CFTMP/pctdis.jsonl"; mktrans "$T" 800000
  evc "$T" pctdis "$CFTMP" | PLC_CONTEXT_FLOOR=0 PLC_CONTEXT_FLOOR_PCT=0 bash "$HERE/context-floor.sh" >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 0 ] && [ ! -f "$M/pctdis.marker" ]; } && echo "  PASS: both-zero disables" || echo "  FAIL: both-zero disables"

  # fail-open: malformed transcript -> allow
  echo "{ not json" > "$CFTMP/bad.jsonl"
  evc "$CFTMP/bad.jsonl" badc "$CFTMP" | cf >/dev/null 2>&1; [ $? -eq 0 ] && echo "  PASS: fail-open on malformed transcript" || echo "  FAIL: fail-open on malformed transcript"

  # fail-open: missing usage field -> allow
  python3 -c 'open("'"$CFTMP"'/nousage.jsonl","w").write("{\"type\":\"assistant\",\"message\":{}}\n")'
  evc "$CFTMP/nousage.jsonl" nu "$CFTMP" | cf >/dev/null 2>&1; [ $? -eq 0 ] && echo "  PASS: fail-open on missing usage" || echo "  FAIL: fail-open on missing usage"

  # RESUME exemption: editing the checkpoint file itself is never blocked (no deadlock)
  evf(){ python3 -c 'import json,sys; print(json.dumps({"session_id":sys.argv[2],"transcript_path":sys.argv[1],"cwd":sys.argv[3],"tool_input":{"file_path":sys.argv[4]}}))' "$1" "$2" "$3" "$4"; }
  T="$CFTMP/exempt.jsonl"; mktrans "$T" 300000   # far over floor
  evf "$T" ex "$CFTMP" "$CFTMP/RESUME.md" | cf >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 0 ] && [ ! -f "$M/ex.marker" ]; } && echo "  PASS: RESUME.md write exempt from block (no deadlock)" || echo "  FAIL: RESUME.md write exempt"
)
rm -rf "$CFTMP"

echo
echo "RESULT: $PASS passed, $FAIL failed (note: temp-repo sub-results print inline above)"
[ "$FAIL" -eq 0 ] || exit 1
