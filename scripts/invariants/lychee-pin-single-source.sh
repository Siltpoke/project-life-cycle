#!/usr/bin/env bash
# Invariant: the lychee pin is stated exactly once, and no reference to the retired
# lycheeverse/lychee-action survives.
#
# I3 IS NOT COSMETIC. The whole reason the action was dropped was that it carried TWO
# independent version axes that could drift apart. Re-introducing a second copy of the
# version literal anywhere would restore that defect in a new place, silently.
set -euo pipefail
NAME=lychee-pin-single-source
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$HERE"
PIN_FILE=scripts/lib/lychee-pin.env
. "$PIN_FILE"

fail=0

# SELF-EXCLUSION IS LOAD-BEARING, NOT COSMETIC. This checker's own source text has to NAME
# both the retired action and the version literal in order to check for them (this comment
# block itself says "lycheeverse/lychee-action" and "the version literal" above). Without
# excluding this file's own basename, I2 finds itself on line 3 of this very file and fails
# on every run, permanently -- measured: it did, on the first run of this script. A checker
# that matches its own family is the self-referential-oracle defect; excluding THIS SCRIPT
# BY NAME (not by directory, so a future sibling invariant is still covered) is the fix.
SELF="$(basename "${BASH_SOURCE[0]}")"

# I2 -- the retired action must not be referenced anywhere (outside this checker's own source).
hits="$(/usr/bin/grep -rn --exclude="$SELF" 'lycheeverse/lychee-action' .github scripts 2>/dev/null || true)"
if [ -n "$hits" ]; then
  echo "FAIL $NAME: the retired lychee-action is still referenced:"
  printf '%s\n' "$hits"
  fail=1
fi

# I3 -- the version literal appears exactly once, and that once is the pin file.
n="$(/usr/bin/grep -rn --exclude="$SELF" -- "$LYCHEE_VERSION" .github scripts 2>/dev/null | /usr/bin/grep -c . || true)"
if [ "$n" -ne 1 ]; then
  echo "FAIL $NAME: the version literal $LYCHEE_VERSION appears $n time(s); expected exactly 1"
  /usr/bin/grep -rn --exclude="$SELF" -- "$LYCHEE_VERSION" .github scripts 2>/dev/null || true
  echo "  Two copies of a version string drifting apart is the defect the pin file removed."
  fail=1
fi

[ "$fail" -eq 0 ] || exit 1
echo "ok $NAME: action retired, version literal stated once (in $PIN_FILE)"
