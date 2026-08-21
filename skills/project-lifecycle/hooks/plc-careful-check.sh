#!/usr/bin/env bash
# skills/project-lifecycle/hooks/plc-careful-check.sh
#
# Decide whether the current uncommitted changes touch anywhere this project asked to be handled
# carefully. Prints one tab-separated row per hit: <class>\t<rule>\t<path>, sorted. Prints `no-hit`
# and exits 0 when nothing matched -- silence would be indistinguishable from a crash.
#
# THE PATH LISTS AND THE WORD LIST ARE NOT IN THIS FILE. They live in the single data block in
# references/careful-paths.md, and scripts/test_careful_check.py greps this file for every shipped
# path literal and requires zero occurrences. A literal here is how the next editor learns it is
# acceptable to keep two copies.
#
# Envelope: bash + jq + git only. No python3.
#
# Exit codes, and the distinctions are deliberate:
#   0  ran; hits printed, or `no-hit`
#   1  bad invocation (unknown option, unreadable CLAUDE.md)
#   3  the data block is missing, malformed, or not exactly one: nothing can be concluded
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DEFAULT="$HERE/../references/careful-paths.md"

die() { printf '%s\n' "$*" >&2; exit "${2:-1}"; }

claude_md="" data="$DATA_DEFAULT" repo="." files_from=""
while [ $# -gt 0 ]; do
  case "$1" in
    --claude-md) [ $# -ge 2 ] || die "--claude-md needs a path"; claude_md="$2"; shift 2 ;;
    --data)      [ $# -ge 2 ] || die "--data needs a path";      data="$2";      shift 2 ;;
    --repo)      [ $# -ge 2 ] || die "--repo needs a path";      repo="$2";      shift 2 ;;
    --files)     [ $# -ge 2 ] || die "--files needs - or a path"; files_from="$2"; shift 2 ;;
    -h|--help)
      printf 'usage: plc-careful-check.sh --claude-md PATH [--data PATH] [--repo PATH] [--files -|PATH]\n'
      exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done
[ -n "$claude_md" ] || die "usage: plc-careful-check.sh --claude-md PATH [--data PATH] [--repo PATH] [--files -|PATH]"
[ -r "$claude_md" ] || die "cannot read $claude_md"
[ -r "$data" ] || die "cannot read the careful-paths data: $data" 3

# Exactly one fenced json block between the sentinels. Two is a hard failure, never a best-effort
# pick -- "the data I read" and "the data that is there" have to be the same object.
if ! block="$(awk '
  /<!-- plc-careful-data:begin -->/ { inblk = 1; next }
  /<!-- plc-careful-data:end -->/   { inblk = 0; next }
  inblk && /^```json$/              { infence = 1; fences++; next }
  inblk && /^```$/                  { infence = 0; next }
  inblk && infence                  { print }
  END                               { if (fences != 1) exit 9 }
' "$data")"; then
  die "the careful-paths data must hold exactly one fenced json block: $data" 3
fi
jq -e . >/dev/null 2>&1 <<<"$block" || die "the careful-paths data block is not valid json: $block" 3

# --- the changed-file list -------------------------------------------------------------------
#
# THE IMPLEMENTER'S WORK IS NOT COMMITTED YET when this runs, so a commit range would produce a
# permanently empty list -- a guard that never fires, which this project holds to be worth exactly
# as much as one that always fires. `git status --porcelain` covers staged, unstaged AND untracked
# in one call, and the untracked half is not optional: a BRAND NEW src/auth/new-login.ts is the
# single shape most deserving of an upgrade, and it is untracked by definition.
changed_files() {
  if [ -n "$files_from" ]; then
    if [ "$files_from" = "-" ]; then cat; else cat "$files_from"; fi
    return
  fi
  git -C "$repo" status --porcelain=1 -z --untracked-files=all |
    while IFS= read -r -d '' entry; do
      # XY<space>path ; a rename carries a second NUL-separated old path, which we drop.
      case "$entry" in
        R*|C*) IFS= read -r -d '' _old || true ;;
      esac
      printf '%s\n' "${entry:3}"
    done
}

# NO `mapfile` ANYWHERE IN THIS FILE. macOS still ships bash 3.2 as /bin/bash and has no mapfile;
# a shipped hook that only runs on machines with bash 4+ is not portable, it is portable-looking.
# Measured: the first version of this script died with `mapfile: command not found` on every row.
#
# ONE STATED LIMIT: a filename containing a NEWLINE is not handled. `git status -z` reports such a
# name correctly and this newline-joined list then splits it in two, so the file is missed. It is
# named rather than silently tolerated -- and it is a miss in the safe direction only by accident,
# so it belongs in the record. Fixing it means carrying NUL through the whole intersection, which
# is a restructure rather than an edit.
FILES="$(changed_files | LC_ALL=C sort -u | sed '/^$/d')"
[ -n "$FILES" ] || { printf 'no-hit\n'; exit 0; }

# --- matching --------------------------------------------------------------------------------
#
# git is asked to decide, so that pathspec semantics are git's and not a hand-rolled matcher's.
# The untracked half of the flags below is load-bearing: `git ls-files` on its own lists TRACKED
# files only, so a newly created file inside a careful directory would be in FILES above and absent
# from the match set here -- the user marks src/auth/, the mechanism works exactly as designed, and
# writing a brand-new login file is invisible to it. scripts/test_careful_check.py mutates that
# flag away and requires red, which is why the flags appear exactly once in this file: a mutation
# that lands in a comment leaves the code intact and its survivor reads like a real one.
matches_pathspec() {
  git -C "$repo" ls-files --cached --others --exclude-standard -z -- "$1" 2>/dev/null |
    tr '\0' '\n' | sed '/^$/d'
}

# A top-level `key: value` from CLAUDE.md. A commented line sets nothing -- otherwise documenting a
# value would enact it.
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

in_changed() {
  case $'\n'"$FILES"$'\n' in
    *$'\n'"$1"$'\n'*) return 0 ;;
  esac
  return 1
}

hits=""

# 1. the project's own declaration
declared="$(read_key careful-paths)"
if [ -n "$declared" ]; then
  IFS=',' read -r -a specs <<<"$declared"
  for spec in "${specs[@]}"; do
    spec="${spec#"${spec%%[![:space:]]*}"}"
    spec="${spec%"${spec##*[![:space:]]}"}"
    [ -n "$spec" ] || continue
    while IFS= read -r f; do
      [ -n "$f" ] || continue
      in_changed "$f" && hits+="careful-path"$'\t'"$spec"$'\t'"$f"$'\n'
    done < <(matches_pathspec "$spec")
  done
fi

# 2. the three signals that need no declaration
while IFS= read -r class; do
  [ -n "$class" ] || continue
  while IFS= read -r spec; do
    [ -n "$spec" ] || continue
    while IFS= read -r f; do
      [ -n "$f" ] || continue
      in_changed "$f" && hits+="$class"$'\t'"$spec"$'\t'"$f"$'\n'
    done < <(matches_pathspec "$spec")
  done < <(jq -r --arg c "$class" '.signals[$c].paths[]' <<<"$block")
done < <(jq -r '.signals | keys[]' <<<"$block")

if [ -z "$hits" ]; then
  printf 'no-hit\n'
  exit 0
fi
printf '%s' "$hits" | LC_ALL=C sort -u
