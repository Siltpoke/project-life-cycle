#!/usr/bin/env bash
# Invariant (the station-plan work): every `<station-id>.s<N>` token written in a closure declaration
# ANYWHERE IN THE CORPUS resolves to a step that a station plan actually declares.
#
# Contract: skills/project-lifecycle/references/roadmap-format.md
#
# WHY THIS IS ITS OWN SCRIPT AND NOT PART OF station-id-integrity.sh (the station-id design).
# That script does LOCAL integrity of docs/ROADMAP.md. This one reads a different input set
# entirely — every closure declaration in the repository, including `docs/archive/**`. Bolted
# together, one of the two scopes would hide behind the other's name, and "a guard whose scope
# is wider or narrower than its name" is a shape this repo has filed repeatedly.
#
# A DANGLING REFERENCE IS A SILENT POSITION ERROR, which is why it is red rather than a
# warning. Position is the count of DISTINCT steps named across all declarations over the
# station's declared step count. A token naming a step that does not exist inflates nothing —
# it is simply dropped by the deriver — so the station reads as less far along than its own
# history says, and nothing anywhere says why.
#
# EMPTY SCOPE IS REPORTED, NEVER PASSED SILENTLY. Zero documents, zero tokens and "every
# token resolved" are three different states, and a bare ✓ makes them one. Filed here as
# p38 and p32: a guard that reports PASS over an empty scope has verified nothing while
# printing exactly like a guard that verified everything.
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

# --- what the roadmap declares ------------------------------------------------------------
blocks="$(awk -f "$STATION_AWK" "$ROADMAP")"
station_steps="$(printf '%s\n' "$blocks" | awk -F'\t' '$1 == "STEP" { print $2 "." $3 }' | sort -u)"
station_ids="$(printf '%s\n' "$blocks" | awk -F'\t' '$1 == "BLOCK" { print $2 }' | sort -u)"
nblocks="$(printf '%s\n' "$station_ids" | grep -c '^..*$' || true)"

# --- what the corpus claims ---------------------------------------------------------------
docs="$(closure_corpus_files "$CORPUS_ROOT")"
ndocs="$(printf '%s\n' "$docs" | grep -c '^..*$' || true)"

if [ "$ndocs" -eq 0 ]; then
  printf '⊘ closed-step-refs-resolve: no closure declarations under %s — 0 tokens checked, and that is stated rather than passed\n' "$CORPUS_ROOT"
  exit 0
fi

tokens=""
if ! tokens="$(closure_step_records "$EXTRACTOR" $docs)"; then
  printf '✗ closed-step-refs-resolve: the corpus could not be read; a declaration this check cannot parse is a red, not an under-count\n' >&2
  exit 1
fi
ntok="$(printf '%s\n' "$tokens" | grep -c '^..*$' || true)"

if [ "$ntok" -eq 0 ]; then
  printf '⊘ closed-step-refs-resolve: %s declaration document(s), 0 `closed-step:` tokens naming a step — nothing to resolve yet\n' "$ndocs"
  exit 0
fi

# --- resolve ------------------------------------------------------------------------------
# The station id is everything before the FINAL `.s<N>`. Split from the right, because a
# station id may legally contain neither `.` nor uppercase but the shape check in the
# extractor only guarantees the suffix — splitting from the left would mis-read any id that
# ever grows a dot.
while IFS="$(printf '\t')" read -r tok src; do
  [ -n "${tok:-}" ] || continue
  sid="${tok%.s*}"
  num="${tok##*.s}"
  if ! printf '%s\n' "$station_ids" | grep -Fxq -- "$sid"; then
    bad "$src names \`$tok\`, but no station plan declares a station '$sid'"
    continue
  fi
  if ! printf '%s\n' "$station_steps" | grep -Fxq -- "$sid.$num"; then
    bad "$src names \`$tok\`, but station '$sid' declares no step s$num"
  fi
done <<EOF
$tokens
EOF

if [ "$fail" -ne 0 ]; then
  printf '✗ closed-step-refs-resolve: FAILED\n' >&2
  exit 1
fi
printf '✓ closed-step-refs-resolve (%s token(s) across %s document(s) resolved against %s station(s) in %s)\n' \
  "$ntok" "$ndocs" "$nblocks" "$ROADMAP"
