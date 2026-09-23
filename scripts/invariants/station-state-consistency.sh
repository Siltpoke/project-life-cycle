#!/usr/bin/env bash
# Invariant (AC-8 / AC-10): a station that the corpus DERIVES as done
# must not also be DECLARED in the "now in flight" list.
#
# Contract: skills/project-lifecycle/references/roadmap-format.md.
#
# THE THREE STATES HAVE THREE SEPARATE SOURCES AND THAT IS THE DESIGN, not an accident of
# implementation: `done` is derived from the closure declarations, `doing` is declared in the
# active list, and `future` is the difference — it has no source of its own. Nothing merges
# them, nothing guesses one from a trace of another. This script is the only place the two
# real sources meet, and it meets them to check they disagree with nothing.
#
# WHY BOTH-AT-ONCE IS RED RATHER THAN A PREFERENCE. If a station is derived done and also
# listed as in flight, one of the two is stale, and there is no rule that says which — that
# is exactly why it cannot be resolved silently. Picking a winner would let the card print a
# confident number that no human ever agreed with.
#
# `done` IS FRACTION-EQUALS-ONE AND NOTHING ELSE (the closure design): distinct steps named across
# ALL declarations equals the declared step count, with the count at least 1. A zero-step
# station is impossible by station-id-integrity.sh's lower bound; if one arrives anyway it is
# refused here rather than being counted as trivially complete, because 0 of 0 reads as done
# to any comparison written the obvious way.
#
# WHAT THIS DOES NOT CHECK, named rather than implied:
#   * that the active list names a station that exists — station-id-integrity.sh.
#   * that a step token resolves — closed-step-refs-resolve.sh.
#   * that no position is stored in the file — no-stored-position.sh.
#   Re-reporting any of them here would make two guards go red for one defect and put this
#   script's scope wider than its name.
#
# Envelope: bash + awk + coreutils. No python3 (CLAUDE.md).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROADMAP="${ROADMAP_PATH:-docs/ROADMAP.md}"
CORPUS_ROOT="${CLOSURE_CORPUS_ROOT:-docs}"
LIBDIR="${STATION_LIB_DIR:-$HERE/../lib}"
EXTRACTOR="${CLOSURE_EXTRACTOR:-$HERE/../closure-declaration.sh}"
STATION_AWK="${STATION_BLOCKS_AWK:-$LIBDIR/station-blocks.awk}"

fail=0
bad() { printf '✗ %s\n' "$*" >&2; fail=1; }

[ -f "$ROADMAP" ]     || { printf '✗ %s is not a regular file\n' "$ROADMAP" >&2; exit 1; }
[ -f "$STATION_AWK" ] || { printf '✗ %s missing — the station-block parser is shared, not inlined\n' "$STATION_AWK" >&2; exit 1; }
[ -f "$EXTRACTOR" ]   || { printf '✗ %s missing — the closure grammar has one reader\n' "$EXTRACTOR" >&2; exit 1; }
[ -r "$LIBDIR/closure-corpus.sh" ] || { printf '✗ %s/closure-corpus.sh missing\n' "$LIBDIR" >&2; exit 1; }
# shellcheck disable=SC1091
. "$LIBDIR/closure-corpus.sh"
command -v closure_corpus_files >/dev/null 2>&1 \
  || { printf '✗ closure-corpus.sh did not define closure_corpus_files\n' >&2; exit 1; }

blocks="$(awk -f "$STATION_AWK" "$ROADMAP")"
counts="$(printf '%s\n' "$blocks" | awk -F'\t' '$1 == "BLOCK" { print $2 "\t" $4 }')"
nblocks="$(printf '%s\n' "$counts" | grep -c '^..*$' || true)"

if [ "$nblocks" -eq 0 ]; then
  printf '⊘ station-state-consistency: no station-plan blocks in %s — 0 stations compared, and that is stated rather than passed\n' "$ROADMAP"
  exit 0
fi

active="$(printf '%s\n' "$blocks" | awk -F'\t' '$1 == "ACTIVE" { print $2 }' | sort -u)"

docs="$(closure_corpus_files "$CORPUS_ROOT")"
ndocs="$(printf '%s\n' "$docs" | grep -c '^..*$' || true)"

tokens=""
if [ "$ndocs" -gt 0 ]; then
  if ! tokens="$(closure_step_records "$EXTRACTOR" $docs)"; then
    printf '✗ station-state-consistency: the corpus could not be read; a declaration this check cannot parse is a red, not an under-count\n' >&2
    exit 1
  fi
fi

# Distinct steps per station, across the WHOLE corpus. Distinct, because a step touched by
# two phases is one step done, not two (the closure design) — counting rows here would let a station
# derive as done with half its steps never named.
closed_counts="$(
  printf '%s\n' "$tokens" \
    | awk -F'\t' 'NF && $1 != "" { print $1 }' \
    | sort -u \
    | awk '{ sid = $0; sub(/\.s[0-9]+$/, "", sid); n[sid]++ } END { for (k in n) printf "%s\t%d\n", k, n[k] }'
)"

ndone=0
while IFS="$(printf '\t')" read -r sid total; do
  [ -n "${sid:-}" ] || continue
  if [ "$total" -lt 1 ]; then
    bad "station '$sid' declares $total steps; a zero-step station cannot be compared (0 of 0 reads as complete to the obvious comparison)"
    continue
  fi
  got="$(printf '%s\n' "$closed_counts" | awk -F'\t' -v k="$sid" '$1 == k { print $2; exit }')"
  [ -n "$got" ] || got=0
  [ "$got" -eq "$total" ] || continue
  ndone=$((ndone + 1))
  if printf '%s\n' "$active" | grep -Fxq -- "$sid"; then
    bad "station '$sid' is derived done ($got/$total steps closed across the corpus) but the active list still declares it in flight — one of the two is stale and this check will not pick a winner"
  fi
done <<EOF
$counts
EOF

if [ "$fail" -ne 0 ]; then
  printf '✗ station-state-consistency: FAILED\n' >&2
  exit 1
fi
nactive="$(printf '%s\n' "$active" | grep -c '^..*$' || true)"
printf '✓ station-state-consistency (%s station(s): %s derived done, %s declared in flight, no station in both)\n' \
  "$nblocks" "$ndone" "$nactive"
