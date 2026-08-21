#!/usr/bin/env bash
# Regenerate the batch-map status GLYPH in docs/ROADMAP.md from `gh pr list`.
#
# Why a generator at all: `grep -rl ROADMAP scripts/` finds readers and no writers, so "the table
# is correct today" is luck. Not adding
# a generator only moves the rot somewhere else.
#
# Why only the glyph: the batch map has no clean status cell. Column 1 carries the PR number, the
# glyph, AND free-form hand-written notes about the row.
# Rewriting the cell would destroy
# those notes. So the generator replaces ONE TOKEN: the glyph
# immediately following `**N**`. Everything else on the line is left byte-for-byte alone.
#
# The cost of that choice, stated rather than discovered later: the prose beside the glyph stays
# hand-written and can therefore contradict it. `--check` exists for that and is the half that
# makes this honest — it reads the same marker vocabulary the /catchup detectors use.
#
# Rules:
#   - MERGED only. Not `!= OPEN`: a CLOSED-unmerged PR must never render as shipped.
#   - A row whose PR number cannot be resolved renders an explicit `?`, never a blank and never a
#     stale glyph. The numbers in those rows are hand-typed, and a typo would otherwise be handed
#     the generator's authority.
#   - No `gh`, or no network, is a NON-ZERO EXIT. "Printed a warning and left the table looking
#     normal" is the failure mode this replaces.

set -uo pipefail

# The status glyph is multibyte, so taking or dropping it must be done by CHARACTER. `cut -c`
# cannot do that portably — it is byte-based in GNU coreutils regardless of locale.
. "$(dirname "${BASH_SOURCE[0]}")/utf8-text.sh"

F="${1:-docs/ROADMAP.md}"
MODE=write
case "${1:-}" in --check) MODE=check; F="${2:-docs/ROADMAP.md}" ;; esac

MARKERS="${PLC_ROADMAP_MARKERS:-.claude/roadmap-progress-markers.txt}"

die() { printf 'roadmap-batchmap-status: %s\n' "$1" >&2; exit "${2:-2}"; }

[ -f "$F" ] || die "no such file: $F"
command -v gh >/dev/null 2>&1 || die "gh is not installed — cannot derive PR state" 3
command -v jq >/dev/null 2>&1 || die "jq is not installed" 3

# One query, not one per row. A per-row query would make the generator's cost scale with the
# table and its behaviour depend on rate limits.
STATES="$(mktemp)"; trap 'rm -f "$STATES"' EXIT
if ! gh pr list --state all --limit 300 --json number,state \
     --jq '.[] | [(.number|tostring), .state] | @tsv' > "$STATES" 2>/dev/null; then
  die "gh pr list failed (no network, or not authenticated) — refusing to rewrite the table with stale or missing state" 3
fi
[ -s "$STATES" ] || die "gh pr list returned nothing — refusing to rewrite the table" 3

state_of() { awk -F'\t' -v n="$1" '$1==n{print $2; found=1} END{if(!found) print "UNKNOWN"}' "$STATES"; }

OUT="$(mktemp)"; trap 'rm -f "$STATES" "$OUT"' EXIT
changed=0
conflicts=0

while IFS= read -r line; do
  # Only batch-map rows: `| **<digits>** <glyph> ...`
  if ! printf '%s' "$line" | grep -qE '^\| \*\*[0-9]+\*\* '; then
    printf '%s\n' "$line" >> "$OUT"; continue
  fi

  # The PR number this row refers to: the first `#<digits>` anywhere on the line.
  pr="$(printf '%s' "$line" | grep -oE '#[0-9]+' | head -1 | tr -d '#')"
  if [ -z "$pr" ]; then
    want='?'
  else
    case "$(state_of "$pr")" in
      MERGED) want='✅' ;;
      OPEN)   want='○' ;;
      CLOSED) want='✖' ;;   # closed unmerged — deliberately NOT ✅
      *)      want='?' ;;   # a number gh has never heard of: a typo, shown as unresolved
    esac
  fi

  head="$(printf '%s' "$line" | sed -E 's/^(\| \*\*[0-9]+\*\* ).*/\1/')"
  rest="$(printf '%s' "$line" | sed -E 's/^\| \*\*[0-9]+\*\* //')"
  cur="$(plc_utf8_head "$rest" 1)"
  # Only a known glyph is replaced. If the first character is prose, the row is left alone and
  # reported — silently inserting a glyph into someone's sentence is worse than not helping.
  case "$cur" in
    '✅'|'○'|'✖'|'?') tail_txt="$(plc_utf8_tail "$rest" 1)" ;;
    *) printf '%s\n' "$line" >> "$OUT"
       printf 'roadmap-batchmap-status: row does not start with a glyph, left untouched: %.60s\n' "$line" >&2
       continue ;;
  esac

  [ "$cur" = "$want" ] || changed=$((changed + 1))
  printf '%s%s%s\n' "$head" "$want" "$tail_txt" >> "$OUT"

  # The stated cost of glyph-only rewriting: the prose can disagree with the glyph.
  if [ -f "$MARKERS" ] && [ "$want" != '✅' ]; then
    while IFS= read -r tok; do
      case "$tok" in ''|'#'*|'['*) continue ;; esac
      if printf '%s' "$tail_txt" | grep -qF "$tok"; then
        printf 'roadmap-batchmap-status: PR #%s is %s but the row prose still claims completion ("%s")\n' \
               "${pr:-?}" "$(state_of "${pr:-0}")" "$tok" >&2
        conflicts=$((conflicts + 1))
        break
      fi
    done < <(awk '/^\[completion\]/{f=1;next} /^\[/{f=0} f' "$MARKERS")
  fi
done < "$F"

if [ "$MODE" = check ]; then
  if [ "$changed" -ne 0 ] || [ "$conflicts" -ne 0 ]; then
    die "$changed glyph(s) out of date, $conflicts prose/glyph conflict(s)" 1
  fi
  printf 'roadmap-batchmap-status: table agrees with gh (%s conflicts)\n' "$conflicts"
  exit 0
fi

cp "$OUT" "$F"
printf 'roadmap-batchmap-status: %s glyph(s) updated, %s prose/glyph conflict(s) reported\n' \
       "$changed" "$conflicts"
[ "$conflicts" -eq 0 ] || exit 1
