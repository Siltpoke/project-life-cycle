#!/usr/bin/env bash
# Invariant: the set of author-local-gated skips matches the committed baseline exactly.
set -euo pipefail
NAME=skip-baseline-matches
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BASE="$HERE/tests/adopter/skip-baseline.txt"
[ -r "$BASE" ] || { echo "FAIL $NAME: baseline missing at $BASE"; exit 1; }
now="$(/bin/bash "$HERE/scripts/skip-baseline.sh")"
if ! diff -u "$BASE" <(printf '%s\n' "$now") > /tmp/skip-baseline.diff 2>&1; then
  echo "FAIL $NAME: the set of author-local-gated skips changed."
  cat /tmp/skip-baseline.diff
  echo "  If this change is intended, regenerate: /bin/bash scripts/skip-baseline.sh > $BASE"
  exit 1
fi
n="$(printf '%s\n' "$now" | /usr/bin/grep -c .)"
echo "ok $NAME: $n rows NOT COVERED -- each gated on an artifact that is not tracked"
