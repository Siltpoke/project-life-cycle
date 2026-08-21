#!/usr/bin/env bash
# skills/project-lifecycle/hooks/mode-expand.sh
#
# Resolve a project's effective policy keys from its CLAUDE.md and the declarative expansion map in
# references/mode.md. Prints one tab-separated row per effective key: <key>\t<value>\t<source>,
# sorted, where source is `explicit` or `preset:<mode>`.
#
# THIS FILE NAMES NO KEY, NOT EVEN IN A COMMENT. Every key, every preset value and every
# never-touched entry comes out of the map; adding one is an edit to that one file. A literal here
# would silently make that false, and scripts/test_mode_expand.py greps this file for every declared
# name and requires zero occurrences -- prose included, because a name in a comment is how the next
# editor learns it is acceptable to branch on one.
#
# Envelope: bash + jq only. No python3 -- the dependency envelope is a portability forcing function.
#
# Exit codes, and the distinctions are deliberate:
#   0  resolved
#   1  bad invocation (unknown option, unreadable CLAUDE.md)
#   2  the project declares a mode the map does not define -- named, never defaulted
#   3  the map itself is missing, malformed, or not exactly one block: nothing can be concluded
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAP_DEFAULT="$HERE/../references/mode.md"

die() { printf '%s\n' "$*" >&2; exit "${2:-1}"; }

claude_md=""
map="$MAP_DEFAULT"
while [ $# -gt 0 ]; do
  case "$1" in
    --claude-md) [ $# -ge 2 ] || die "--claude-md needs a path"; claude_md="$2"; shift 2 ;;
    --map)       [ $# -ge 2 ] || die "--map needs a path";       map="$2";       shift 2 ;;
    -h|--help)   printf 'usage: mode-expand.sh --claude-md PATH [--map PATH]\n'; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done
[ -n "$claude_md" ] || die "usage: mode-expand.sh --claude-md PATH [--map PATH]"
[ -r "$claude_md" ] || die "cannot read $claude_md"
[ -r "$map" ] || die "cannot read the expansion map: $map" 3

# Exactly one fenced json block between the sentinels. Zero or two is a hard failure and never a
# best-effort pick: "the map I read" and "the map that is there" have to be the same object, and a
# reader that silently picks one of two copies is the drift this whole design exists to avoid.
if ! block="$(awk '
  /<!-- plc-mode-map:begin -->/ { inblk = 1; next }
  /<!-- plc-mode-map:end -->/   { inblk = 0; next }
  inblk && /^```json$/          { infence = 1; fences++; next }
  inblk && /^```$/              { infence = 0; next }
  inblk && infence              { print }
  END                           { if (fences != 1) exit 9 }
' "$map")"; then
  die "the expansion map must hold exactly one fenced json block: $map" 3
fi
jq -e . >/dev/null 2>&1 <<<"$block" || die "the expansion map block is not valid json: $map" 3

declared="$(jq -r '.keys[]?' <<<"$block")"
[ -n "$declared" ] || die "the expansion map declares no keys: $map" 3
legal="$(jq -r '.modes | join(", ")' <<<"$block")"

# Read a top-level `key: value` out of CLAUDE.md. First occurrence wins. A line beginning with `#`
# is a comment and sets nothing -- otherwise documenting a value would enact it. A trailing `#`
# comment is stripped from the value.
read_key() {
  awk -v k="$1" '
    /^[[:space:]]*#/ { next }
    index($0, k ":") == 1 {
      sub("^" k ":[[:space:]]*", "")
      sub("[[:space:]]*#.*$", "")
      gsub(/[[:space:]]+$/, "")
      print
      exit
    }
  ' "$claude_md"
}

selected="$(read_key mode)"
preset='{}'
if [ -n "$selected" ]; then
  if ! preset="$(jq -e --arg m "$selected" '.presets[$m]' <<<"$block" 2>/dev/null)"; then
    die "unrecognised mode: $selected (legal values: $legal)" 2
  fi
fi

# The never-touched list is enforced HERE rather than left to the preset happening to omit the key.
# A preset edited later to set one would otherwise start moving it with nothing noticing.
untouched="$(jq -r '.never_set_by_mode[]?' <<<"$block")"

while IFS= read -r key; do
  [ -n "$key" ] || continue
  explicit="$(read_key "$key")"
  if [ -n "$explicit" ]; then
    printf '%s\t%s\texplicit\n' "$key" "$explicit"
    continue
  fi
  case $'\n'"$untouched"$'\n' in
    *$'\n'"$key"$'\n'*) continue ;;
  esac
  value="$(jq -r --arg k "$key" '.[$k] // empty' <<<"$preset")"
  [ -n "$value" ] || continue
  printf '%s\t%s\tpreset:%s\n' "$key" "$value" "$selected"
done <<<"$declared" | LC_ALL=C sort
