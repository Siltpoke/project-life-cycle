#!/usr/bin/env bash
# Invariant `test-input-map-fresh` (the freshness guard): the pinned map is what the generator wrote.
#
# The generator writes `.claude/test-input-map.fingerprint` beside the map; its first line is the
# map's git blob. A hand edit changes the blob, so it is red here; regenerating writes both files
# together, so it is green again.
#
# WHAT THIS DOES NOT CHECK, and who does. Whether the map is stale against the TREE -- a test file
# or a code file it reads changed since generation -- is `scripts/select-tests.sh`'s check: it reads
# the fingerprint's `input` lines and prints FULL while any is stale. That is deliberately not a gate
# condition: regenerating takes 90+ minutes, and a gate that demanded it on every commit touching
# code would be switched off. A stale map costs a full run, never a missed test.
#
# NOT APPLICABLE (exit 0, says so) where neither file exists: a repo that never generated a map has
# nothing to protect (a check must not fire where the feature was never configured).
#
# Envelope: bash + git + awk. No python3, no jq needed (CLAUDE.md).
# Verdicts: 0 pass or not applicable, 1 the pin is wrong.
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MAP=.claude/test-input-map.tsv
FP=.claude/test-input-map.fingerprint
fail() { printf 'FAIL test-input-map-fresh: %s\n' "$*" >&2; exit 1; }

if [ ! -e "$MAP" ] && [ ! -e "$FP" ]; then
  printf 'ok  test-input-map-fresh: not applicable -- no %s in this repo\n' "$MAP"
  exit 0
fi
[ -f "$MAP" ] || fail "$FP exists but $MAP does not"
[ -f "$FP" ] || fail "$MAP has no $FP -- regenerate: /bin/bash scripts/gen-test-input-map.sh"

first="$(head -n 1 "$FP")"
case "$first" in
  "map "*) ;;
  *) fail "$FP: first line is not 'map <blob>': $first" ;;
esac
want="${first#map }"
have="$(git hash-object "$MAP")"
[ "$want" = "$have" ] ||
  fail "$MAP was edited by hand, or written without its fingerprint (blob $have; fingerprint says $want) -- regenerate: /bin/bash scripts/gen-test-input-map.sh"

awk 'NR > 1 && $0 !~ /^input [0-9a-f][0-9a-f]* [^ ]/ { bad = NR } END { exit bad ? 1 : 0 }' "$FP" ||
  fail "$FP: a line after the first is not 'input <blob> <path>'"

printf 'ok  test-input-map-fresh: %s matches its fingerprint (%d inputs recorded; staleness against the tree is the selector'"'"'s check)\n' \
  "$MAP" "$(($(wc -l <"$FP") - 1))"
