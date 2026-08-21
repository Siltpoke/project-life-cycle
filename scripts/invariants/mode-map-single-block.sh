#!/usr/bin/env bash
# Invariant `mode-map-single-block`: the mode expansion map is ONE data block, and the shipped reader can read it.
#
# TWO DIRECTIONS, and the second is the one that bites. Zero blocks is a broken file anybody would
# notice on the next run. TWO blocks is a file that reads fine to a human and where the reader
# silently picks one -- the same fact written twice with the reader landing on the stale copy.
#
# THE CHECK RUNS THE SHIPPED READER rather than re-implementing its parser. A second parser here
# could be green while the product is broken -- the proxy-versus-real-thing defect.
# The cost is that a reader bug shows up as an invariant failure rather
# than as a parser disagreement; that is the right direction to be wrong in.
#
# Verdicts: 0 pass, 1 the repository is wrong, 3 the check could not run (a check that
# could not run must never report as though it had).
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

MAP=skills/project-lifecycle/references/mode.md
READER=skills/project-lifecycle/hooks/mode-expand.sh

[ -r "$MAP" ]    || { printf 'COULD NOT RUN: %s is not readable\n' "$MAP" >&2; exit 3; }
[ -r "$READER" ] || { printf 'COULD NOT RUN: %s is not readable\n' "$READER" >&2; exit 3; }

begins=$(/usr/bin/grep -c '<!-- plc-mode-map:begin -->' "$MAP" || true)
ends=$(/usr/bin/grep -c '<!-- plc-mode-map:end -->' "$MAP" || true)
if [ "$begins" != 1 ] || [ "$ends" != 1 ]; then
  printf 'FAIL %s: expected exactly one sentinel pair, found %s begin / %s end\n' \
    "$MAP" "$begins" "$ends" >&2
  exit 1
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
printf 'mode: fast\n' > "$tmp/CLAUDE.md"

if ! out="$(/bin/bash "$READER" --claude-md "$tmp/CLAUDE.md" 2>"$tmp/err")"; then
  printf 'FAIL the shipped reader cannot resolve the map:\n' >&2
  sed 's/^/  /' "$tmp/err" >&2
  exit 1
fi
if [ -z "$out" ]; then
  printf 'FAIL the map resolved to an empty configuration -- an empty result is not a pass\n' >&2
  exit 1
fi

# The three columns are the contract every consumer reads. A row that lost its source column would
# still be non-empty, so "non-empty" alone is not enough.
if ! printf '%s\n' "$out" | awk -F'\t' 'NF != 3 { exit 1 }'; then
  printf 'FAIL the reader emitted a row that is not <key>\\t<value>\\t<source>\n' >&2
  exit 1
fi

printf 'ok  mode map is a single readable block (%s keys resolved for the fast preset)\n' \
  "$(printf '%s\n' "$out" | wc -l | tr -d ' ')"
