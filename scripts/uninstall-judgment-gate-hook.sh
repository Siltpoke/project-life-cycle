#!/usr/bin/env bash
# uninstall-judgment-gate-hook.sh — remove exactly what install-judgment-gate-hook.sh wired:
# PreToolUse entries whose command ends in `/plc-judgment-gate.sh` (only that inner hook; siblings kept), plus the copied hook file and its copied contract.
# Every other hook in settings is left untouched. Safe to run when nothing is installed.
set -euo pipefail

SETTINGS="${CLAUDE_SETTINGS:-$HOME/.claude/settings.json}"
HOOKS_DIR="${CLAUDE_HOOKS_DIR:-$HOME/.claude/hooks}"

command -v jq >/dev/null 2>&1 || { echo "✗ jq is required to edit $SETTINGS" >&2; exit 1; }

if [ -f "$SETTINGS" ]; then
  jq -e 'type == "object"' "$SETTINGS" >/dev/null 2>&1 \
    || { echo "✗ $SETTINGS is not a valid JSON object — refusing to touch it" >&2; exit 1; }
  tmp="$(mktemp "${SETTINGS}.XXXXXX")"
  trap 'rm -f "$tmp"' EXIT
  jq 'def strip: [ .[] | ((.hooks // []) | any((.command // "") | endswith("/plc-judgment-gate.sh"))) as $m
      | (if $m then .hooks |= map(select(((.command // "") | endswith("/plc-judgment-gate.sh")) | not)) else . end)
      | select(($m | not) or ((.hooks | length) > 0)) ];
      if (.hooks.PreToolUse // null) == null then . else .hooks.PreToolUse |= strip end' "$SETTINGS" > "$tmp"
  if cmp -s "$tmp" "$SETTINGS"; then
    echo "✓ no judgment-gate entry in $SETTINGS — nothing to remove"
  else
    mv "$tmp" "$SETTINGS"
    echo "✓ removed judgment-gate entry from $SETTINGS"
  fi
fi
rm -f "$HOOKS_DIR/plc-judgment-gate.sh" "$HOOKS_DIR/plc-judgment-gate.contract.md"
