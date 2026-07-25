#!/usr/bin/env bash
# tasklist-view.test.sh — pure-bash fixture tests for tasklist-view.sh. jq-free.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/tasklist-view.sh"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
fails=0
run() { PLC_TASKLIST_FILE="$1" bash "$SCRIPT" "${2:-}"; }         # stdout
rc()  { PLC_TASKLIST_FILE="$1" bash "$SCRIPT" "${2:-}" >/dev/null 2>&1; echo $?; }
has() { # name  file  needle  (case-match, no pipe: grep -q + pipefail = SIGPIPE false-negatives)
  local o; o="$(run "$2" "${4:-}")"
  case "$o" in *"$3"*) echo "ok   $1";; *) echo "FAIL $1 — expected to contain: $3"; fails=1;; esac; }
hasnt() { # name file needle [mode]
  local o; o="$(run "$2" "${4:-}")"
  case "$o" in *"$3"*) echo "FAIL $1 — should NOT contain: $3"; fails=1;; *) echo "ok   $1";; esac; }
eq() { # name got want
  if [ "$2" = "$3" ]; then echo "ok   $1"
  else echo "FAIL $1 — got:$2 want:$3"; fails=1; fi; }

# --- fixture: mixed states, one current ---
FX="$TMP/mixed.md"
cat > "$FX" <<'EOF'
# Phase feat/phase-demo
## Task 1 — Alpha
- [x] a1
- [x] a2
## Task 2 — Beta
- [x] b1
- [/] b2
- [ ] b3
- [ ] b4
EOF

# --- brief mode (default): header + current one-liner, NO full tree ---
has  "brief phase+count"  "$FX" "Phase feat/phase-demo"
has  "brief global 3/6"   "$FX" "3/6"
has  "brief now line"     "$FX" "▶ now:"
has  "brief current group" "$FX" "Task 2 — Beta"
has  "brief current text"  "$FX" "b2"
has  "brief expand hint"   "$FX" "--tree to expand"
hasnt "brief hides todos"  "$FX" "○ b3"
eq   "exit 0 brief"       "$(rc "$FX")" "0"

# --- tree mode: full expanded overview ---
has  "tree global 3/6"    "$FX" "3/6"          "--tree"
has  "tree group1 2/2"    "$FX" "2/2"          "--tree"
has  "tree group2 1/4"    "$FX" "1/4"          "--tree"
has  "tree done glyph"    "$FX" "✓ a1"         "--tree"
has  "tree inprogress"    "$FX" "▶ b2"         "--tree"
has  "tree todo glyph"    "$FX" "○ b3"         "--tree"
has  "tree current marker" "$FX" "← here"      "--tree"
eq   "exit 0 tree"        "$(rc "$FX" "--tree")" "0"

# --- missing file ---
eq   "exit 0 missing"     "$(rc "$TMP/nope.md")" "0"
has  "missing msg"        "$TMP/nope.md" "no tasklist yet"

# --- empty (no checkboxes) ---
printf '# Phase x\n## Task 1\n' > "$TMP/empty.md"
has  "empty msg"          "$TMP/empty.md" "no tasks"
eq   "exit 0 empty"       "$(rc "$TMP/empty.md")" "0"

# --- no current ([/] absent): brief says so, tree has no ← here ---
printf '# P\n## T\n- [x] one\n- [ ] two\n' > "$TMP/nocur.md"
has  "brief no-progress"  "$TMP/nocur.md" "no step in progress"
hasnt "tree no here"      "$TMP/nocur.md" "← here" "--tree"
eq   "exit 0 nocur"       "$(rc "$TMP/nocur.md")" "0"

# --- malformed line ignored, unknown char → todo (tree mode) ---
printf '# P\n## T\n- [x] ok\ngarbage not a task\n- [?] weird\n' > "$TMP/mal.md"
eq   "exit 0 malformed"   "$(rc "$TMP/mal.md")" "0"
has  "unknown→todo glyph" "$TMP/mal.md" "○ weird" "--tree"
has  "count ignores junk" "$TMP/mal.md" "1/2"     "--tree"

# --- AC5 label independence: rename text, counts/current unchanged ---
printf '# P\n## T\n- [x] RENAMED_LABEL_ZZZ\n- [/] xx\n' > "$TMP/lbl.md"
has  "label-indep count"  "$TMP/lbl.md" "1/2"
has  "label-indep now"    "$TMP/lbl.md" "▶ now:"

echo "----"
[ "$fails" = 0 ] && echo "ALL PASS" || { echo "FAILURES"; exit 1; }
