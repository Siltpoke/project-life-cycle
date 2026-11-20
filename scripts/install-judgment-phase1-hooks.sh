#!/usr/bin/env bash
# install-judgment-phase1-hooks.sh -- wire the phase-1 hooks into GLOBAL settings:
#   judgment-action-gate.sh     -> PreToolUse matcher "Bash"  (action-level hard-stop; every trigger is
#                                  command-level, so Edit|Write would only pay a spawn per edit)
#   judgment-shadow-record.sh   -> PreToolUse matcher "Bash|Edit|Write" (shadow recorder, never blocks)
#
# Same shape as install-judgment-gate-hook.sh: hook code stays tracked in the repo, only the wiring
# lands on the machine. Hooks are COPIED to ~/.claude/hooks/plc-<name>.sh and settings points there;
# the A-2 contract is copied beside them. Both hooks are standalone (no libs).
#
# MARK: the command basenames `/plc-judgment-action-gate.sh` and `/plc-judgment-shadow-record.sh`
# (anchored; lookalikes do not match). Install dedupes on them; uninstall removes exactly them.
#
# Env: CLAUDE_SETTINGS / CLAUDE_HOOKS_DIR override the real ~/.claude (tests use temp paths).
# Run once per machine, only with the owner's consent:  bash scripts/install-judgment-phase1-hooks.sh
set -euo pipefail

SETTINGS="${CLAUDE_SETTINGS:-$HOME/.claude/settings.json}"
HOOKS_DIR="${CLAUDE_HOOKS_DIR:-$HOME/.claude/hooks}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
SRC_DIR="$REPO/skills/project-lifecycle/hooks"
CONTRACT_SRC="$REPO/skills/project-lifecycle/references/judgment-gate.md"
CONTRACT_DEST="$HOOKS_DIR/plc-judgment-phase1.contract.md"

command -v jq >/dev/null 2>&1 || { echo "x jq is required to edit $SETTINGS" >&2; exit 1; }
for f in "$SRC_DIR/judgment-action-gate.sh" "$SRC_DIR/judgment-shadow-record.sh" "$CONTRACT_SRC"; do
  [ -f "$f" ] || { echo "x source missing: $f" >&2; exit 1; }
done
if [ -f "$SETTINGS" ]; then
  jq -e 'type == "object"' "$SETTINGS" >/dev/null 2>&1 \
    || { echo "x $SETTINGS is not a valid JSON object -- refusing to touch it" >&2; exit 1; }
else
  mkdir -p "$(dirname "$SETTINGS")"
  printf '{}\n' > "$SETTINGS"
fi

mkdir -p "$HOOKS_DIR"
cp "$SRC_DIR/judgment-action-gate.sh" "$HOOKS_DIR/plc-judgment-action-gate.sh"
cp "$SRC_DIR/judgment-shadow-record.sh" "$HOOKS_DIR/plc-judgment-shadow-record.sh"
chmod +x "$HOOKS_DIR/plc-judgment-action-gate.sh" "$HOOKS_DIR/plc-judgment-shadow-record.sh"
cp "$CONTRACT_SRC" "$CONTRACT_DEST"

tmp="$(mktemp "${SETTINGS}.XXXXXX")"
trap 'rm -f "$tmp"' EXIT
jq --arg gate "$HOOKS_DIR/plc-judgment-action-gate.sh" --arg rec "$HOOKS_DIR/plc-judgment-shadow-record.sh" '
  def mark: ((.command // "") | endswith("/plc-judgment-action-gate.sh") or endswith("/plc-judgment-shadow-record.sh"));
  def strip: [ .[] | ((.hooks // []) | any(mark)) as $m
      | (if $m then .hooks |= map(select(mark | not)) else . end)
      | select(($m | not) or ((.hooks | length) > 0)) ];
  .hooks.PreToolUse = (
    ((.hooks.PreToolUse // []) | strip)
    + [{matcher: "Bash", hooks: [{type: "command", command: $gate}]},
       {matcher: "Bash|Edit|Write", hooks: [{type: "command", command: $rec}]}]
  )' "$SETTINGS" > "$tmp"
if cmp -s "$tmp" "$SETTINGS"; then
  echo "ok phase-1 judgment hooks already wired in $SETTINGS (copies refreshed in $HOOKS_DIR)"
else
  mv "$tmp" "$SETTINGS"
  echo "ok wired action-gate (Bash) + shadow-recorder (Bash|Edit|Write) in $SETTINGS"
fi
