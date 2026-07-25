#!/usr/bin/env bash
# diff-guards.sh — out-of-envelope producer of diff-guards.json (verify-gate AC3 / R5).
# Two-pass so multi-line comments / strings are handled with real cross-line state (a unified=0
# diff can't see a construct's opener when only an interior line is added):
#   pass 1 — from the diff, collect the ADDED line numbers per source file;
#   pass 2 — for each such file, scan its FULL content at HEAD (`git show`) with diff-guards.awk,
#            which tracks block-comment / template-literal / triple-quote state and emits a guard
#            only for lines that are both ADDED and real code (never over-routing into a comment).
# Emits { base, head, guards:[{guardId,file,line,kind}] }. The jq gate READS this; the gate stays
# jq-only. This producer is out-of-envelope (bash + awk + git + jq).
#
# Usage: diff-guards.sh --base <sha> --head <sha> --diff <path> --out <path> [--repo <dir>]
#   --diff : a `git diff --unified=0 BASE HEAD` capture (a file, or '-' for empty/no-diff).
set -euo pipefail

die() { echo "diff-guards: $*" >&2; exit 1; }

BASE="" HEAD="" DIFF="" OUT="" REPO=""
while [ $# -gt 0 ]; do
  case "$1" in
    --base|--head|--diff|--out|--repo)
      [ $# -ge 2 ] || die "flag $1 needs a value"
      case "$1" in
        --base) BASE="$2" ;; --head) HEAD="$2" ;;
        --diff) DIFF="$2" ;; --out) OUT="$2" ;; --repo) REPO="$2" ;;
      esac
      shift 2 ;;
    *) die "unknown flag: $1" ;;
  esac
done
[ -n "$BASE" ] || die "missing --base"
[ -n "$HEAD" ] || die "missing --head"
[ -n "$OUT" ]  || die "missing --out"
[ -n "$DIFF" ] || die "missing --diff"
[ -n "$REPO" ] || REPO="$(git rev-parse --show-toplevel 2>/dev/null)" || die "not in a git repo (pass --repo)"

is_source() {  # $1 = filename → 0 if a scanned source extension
  case "$1" in
    *.js|*.jsx|*.ts|*.tsx|*.mjs|*.cjs|*.py|*.sh|*.bash|*.rb|*.go|*.rs|*.java|*.c|*.cc|*.cpp|*.h|*.hpp|*.pl|*.php) return 0 ;;
    *) return 1 ;;
  esac
}

# '-' or a missing/empty diff → a clean empty guard set (no guards this PR, not an error).
DIFF_TEXT=""
if [ "$DIFF" != "-" ] && [ -s "$DIFF" ]; then DIFF_TEXT="$(cat "$DIFF")"; fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AWK_PROG="$SCRIPT_DIR/diff-guards.awk"
[ -f "$AWK_PROG" ] || die "awk program not found: $AWK_PROG"

# pass 1: `file<TAB>addedline` for every added line (source-ext filtering happens in pass 2).
ADDED_TSV="$(printf '%s\n' "$DIFF_TEXT" | awk '
  /^\+\+\+ / { f=$2; sub(/^b\//,"",f); curfile=(f=="/dev/null")?"":f; next }
  /^--- / { next }
  /^@@ / { m=$0; sub(/^@@ [^+]*\+/,"",m); sub(/[, ].*/,"",m); addln=m+0; next }
  /^\+/ { if (curfile!="") printf "%s\t%d\n", curfile, addln; addln++; next }
  /^-/  { next }
  /^ /  { addln++; next }
')"

# pass 2: per source file, scan its HEAD content over just the added line numbers.
GUARDS_TSV=""
if [ -n "$ADDED_TSV" ]; then
  FILES="$(printf '%s\n' "$ADDED_TSV" | cut -f1 | sort -u)"
  while IFS= read -r F; do
    [ -n "$F" ] || continue
    is_source "$F" || continue
    LINES="$(printf '%s\n' "$ADDED_TSV" | awk -F'\t' -v f="$F" '$1==f{print $2}' | paste -sd, -)"
    EXT="${F##*.}"; [ "$EXT" = "$F" ] && EXT=""
    CONTENT="$(git -C "$REPO" show "$HEAD:$F" 2>/dev/null)" || continue  # file gone at HEAD → skip
    HITS="$(printf '%s\n' "$CONTENT" | awk -v file="$F" -v ext="$EXT" -v addlines="$LINES" -f "$AWK_PROG")"
    [ -n "$HITS" ] && GUARDS_TSV="${GUARDS_TSV}${HITS}"$'\n'
  done <<EOF
$FILES
EOF
fi

GUARDS_JSON="$(printf '%s' "$GUARDS_TSV" | jq -R -s '
  split("\n") | map(select(length>0) | split("\t"))
  | map({ guardId: (.[0] + ":" + .[1]), file: .[0], line: (.[1]|tonumber), kind: .[2] })
')"

TMP="$(mktemp)"; trap 'rm -f "$TMP"' EXIT
jq -n --arg base "$BASE" --arg head "$HEAD" --argjson guards "$GUARDS_JSON" \
  '{base:$base, head:$head, guards:$guards}' > "$TMP"
mkdir -p "$(dirname "$OUT")"
mv "$TMP" "$OUT"
echo "diff-guards: wrote $(jq '.guards|length' "$OUT") guard(s) to $OUT"
