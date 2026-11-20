#!/usr/bin/env bash
# uninstall-judgment-phase1-hooks.sh -- remove exactly what install-judgment-phase1-hooks.sh wired:
# PreToolUse hook commands ending in `/plc-judgment-action-gate.sh` or `/plc-judgment-shadow-record.sh`
# (only those inner hooks; siblings kept), plus the copied hooks and contract.
# Safe to run when nothing is installed.
set -euo pipefail

SETTINGS="${CLAUDE_SETTINGS:-$HOME/.claude/settings.json}"
HOOKS_DIR="${CLAUDE_HOOKS_DIR:-$HOME/.claude/hooks}"

command -v jq >/dev/null 2>&1 || { echo "x jq is required to edit $SETTINGS" >&2; exit 1; }

if [ -f "$SETTINGS" ]; then
  jq -e 'type == "object"' "$SETTINGS" >/dev/null 2>&1 \
    || { echo "x $SETTINGS is not a valid JSON object -- refusing to touch it" >&2; exit 1; }
  tmp="$(mktemp "${SETTINGS}.XXXXXX")"
  trap 'rm -f "$tmp"' EXIT
  jq 'def mark: ((.command // "") | endswith("/plc-judgment-action-gate.sh") or endswith("/plc-judgment-shadow-record.sh"));
      def strip: [ .[] | ((.hooks // []) | any(mark)) as $m
        | (if $m then .hooks |= map(select(mark | not)) else . end)
        | select(($m | not) or ((.hooks | length) > 0)) ];
      if (.hooks.PreToolUse // null) == null then . else .hooks.PreToolUse |= strip end' "$SETTINGS" > "$tmp"
  if cmp -s "$tmp" "$SETTINGS"; then
    echo "ok no phase-1 judgment entries in $SETTINGS -- nothing to remove"
  else
    mv "$tmp" "$SETTINGS"
    echo "ok removed phase-1 judgment entries from $SETTINGS"
  fi
fi
rm -f "$HOOKS_DIR/plc-judgment-action-gate.sh" "$HOOKS_DIR/plc-judgment-shadow-record.sh" "$HOOKS_DIR/plc-judgment-phase1.contract.md"
