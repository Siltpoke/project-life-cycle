#!/usr/bin/env bash
# install-judgment-gate-hook.sh — wire the first-edit judgment-gate into GLOBAL settings.
#
# Same philosophy as install-close-gate-hook.sh: the hook CODE stays tracked in the repo
# (skills/project-lifecycle/hooks/judgment-gate.sh); only the WIRING lands on the machine, and
# this installer is the tracked, idempotent, reviewable record of it.
#
# Path reference: the hook is COPIED to ~/.claude/hooks/plc-judgment-gate.sh and settings points
# there. That path pins neither a plugin-cache versioned dir (dies on upgrade) nor a repo
# checkout (dies on move/delete), matching how other global hooks reference ~/.claude/hooks/.
# Re-run this script after the hook changes to refresh the copy.
#
# MARK: JSON has no comments, so the marker is the command basename `/plc-judgment-gate.sh` (anchored; lookalikes do not match);
# install dedupes on it and uninstall removes exactly the entries carrying it.
#
# Run once per machine:  bash scripts/install-judgment-gate-hook.sh
set -euo pipefail

SETTINGS="${CLAUDE_SETTINGS:-$HOME/.claude/settings.json}"
HOOKS_DIR="${CLAUDE_HOOKS_DIR:-$HOME/.claude/hooks}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)/skills/project-lifecycle/hooks/judgment-gate.sh"
DEST="$HOOKS_DIR/plc-judgment-gate.sh"
CONTRACT_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)/skills/project-lifecycle/references/judgment-gate.md"
CONTRACT_DEST="$HOOKS_DIR/plc-judgment-gate.contract.md"

command -v jq >/dev/null 2>&1 || { echo "✗ jq is required to edit $SETTINGS" >&2; exit 1; }
[ -f "$SRC" ] || { echo "✗ hook source missing: $SRC" >&2; exit 1; }
[ -f "$CONTRACT_SRC" ] || { echo "✗ contract source missing: $CONTRACT_SRC" >&2; exit 1; }
if [ -f "$SETTINGS" ]; then
  jq -e 'type == "object"' "$SETTINGS" >/dev/null 2>&1 \
    || { echo "✗ $SETTINGS is not a valid JSON object — refusing to touch it" >&2; exit 1; }
else
  mkdir -p "$(dirname "$SETTINGS")"
  printf '{}\n' > "$SETTINGS"
fi

mkdir -p "$HOOKS_DIR"
cp "$SRC" "$DEST"
chmod +x "$DEST"
# The contract sits BESIDE the hook: the hook resolves it from its own location, so the deny
# reason's path is valid in non-PLC repos where cwd has no skills/ tree.
cp "$CONTRACT_SRC" "$CONTRACT_DEST"

tmp="$(mktemp "${SETTINGS}.XXXXXX")"
trap 'rm -f "$tmp"' EXIT
jq --arg cmd "$DEST" '
  def strip: [ .[] | ((.hooks // []) | any((.command // "") | endswith("/plc-judgment-gate.sh"))) as $m
      | (if $m then .hooks |= map(select(((.command // "") | endswith("/plc-judgment-gate.sh")) | not)) else . end)
      | select(($m | not) or ((.hooks | length) > 0)) ];
  .hooks.PreToolUse = (
    ((.hooks.PreToolUse // []) | strip)
    + [{matcher: "Edit|Write", hooks: [{type: "command", command: $cmd}]}]
  )' "$SETTINGS" > "$tmp"
if cmp -s "$tmp" "$SETTINGS"; then
  echo "✓ judgment-gate already wired in $SETTINGS (hook copy refreshed at $DEST)"
else
  mv "$tmp" "$SETTINGS"
  echo "✓ wired judgment-gate (PreToolUse Edit|Write -> $DEST) in $SETTINGS"
fi
