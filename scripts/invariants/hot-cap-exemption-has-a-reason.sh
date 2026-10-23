#!/usr/bin/env bash
# Invariant: every `retention.hot_caps.<key>: "none"` carries a written reason.
#
# WHY THIS EXISTS. The cap rows FAIL the gate when a hot document exceeds its cap, and `"none"`
# is the only way to stand a subject down. That makes `"none"` the escape hatch for the exact
# mechanism the phase was built to install -- and an escape hatch with no stated reason is
# indistinguishable from the inert config this check exists to prevent: a check downgraded to
# warn-only never reds. The original trigger was declared cap entries that no code read.
#
# THE SHAPE IS THE REPO'S EXISTING ONE, not a new convention: `commands-no-bare-python.sh`
# already requires every exemption to cost a written reason and FAILS when an exemption's line
# stops matching, rather than passing quietly. The reason lives in a sibling
# `_note_hot_caps_<key>_none` key, matching the manifest's own `_note_*` convention.
#
# WHAT IT DOES NOT ASSERT, stated rather than implied: it judges that a reason EXISTS and is
# substantial, never whether the reason is a good one. No mechanical check can do the second, and
# claiming it would be a claim wider than the mechanism. The length floor is what stops `"x"`
# from satisfying it; the content is for a human at review.
#
# Verdicts: 0 pass, 1 an exemption has no reason, 3 could not run.
# Envelope: jq only. No python3 (CLAUDE.md).
set -uo pipefail
cd "${HOTCAP_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

NAME="hot-cap-exemption-has-a-reason"
M="${HOTCAP_MANIFEST:-.claude/close-gate.json}"
MIN_LEN="${HOTCAP_MIN_REASON:-80}"

command -v jq >/dev/null 2>&1 || {
  printf 'COULD NOT RUN %s: jq is required and is not on PATH\n' "$NAME" >&2
  exit 3
}

if [ ! -r "$M" ]; then
  # An adopter without a manifest has nothing to guard, and it says so rather than passing
  # silently -- a check that cannot tell "nothing to guard" from "guarded and clean" is the
  # vacuous pass this repo keeps re-filing.
  printf 'ok  %s: no %s in this repo; nothing to guard\n' "$NAME" "$M"
  exit 0
fi

if ! jq -e . "$M" >/dev/null 2>&1; then
  printf 'COULD NOT RUN %s: %s is not valid JSON\n' "$NAME" "$M" >&2
  exit 3
fi

# Keys whose value is the string "none". `// {}` so a manifest with no retention block is a
# clean empty set rather than a jq error.
exempt="$(jq -r '((.retention.hot_caps // {}) | to_entries | map(select(.value == "none")) | .[].key)' "$M" 2>/dev/null || true)"

if [ -z "$exempt" ]; then
  printf 'ok  %s: no hot-cap exemption declared, so no reason is owed\n' "$NAME"
  exit 0
fi

fail=0
n=0
while IFS= read -r key; do
  [ -n "$key" ] || continue
  n=$((n + 1))
  note="$(jq -r --arg k "_note_hot_caps_${key}_none" '(.retention[$k] // empty)' "$M" 2>/dev/null || true)"
  if [ -z "$note" ]; then
    printf '✗ %s: retention.hot_caps.%s is "none" with no reason\n' "$NAME" "$key" >&2
    printf '  -> add retention._note_hot_caps_%s_none. "none" stands a FAILING cap row down; an\n' "$key" >&2
    printf '     exemption with no stated reason is indistinguishable from the inert config this check\n' >&2
    printf '     prevents. Say what is deferred, why it is not simply fixed now, and what\n' >&2
    printf '     removes the exemption again.\n' >&2
    fail=1
    continue
  fi
  len=${#note}
  if [ "$len" -lt "$MIN_LEN" ]; then
    printf '✗ %s: retention.hot_caps.%s has a reason of only %d chars (floor %d)\n' "$NAME" "$key" "$len" "$MIN_LEN" >&2
    printf '  -> the floor exists so a placeholder cannot satisfy this check. It does NOT judge\n' >&2
    printf '     whether the reason is a good one -- no mechanical check can, and claiming it\n' >&2
    printf '     would be a claim wider than the mechanism.\n' >&2
    fail=1
    continue
  fi
  printf 'ok  %s: hot_caps.%s exempt, reason recorded (%d chars)\n' "$NAME" "$key" "$len"
done <<EOF2
$exempt
EOF2

if [ "$n" -eq 0 ]; then
  printf '✗ %s: read zero exemption keys from a non-empty list -- refusing to certify (fail closed)\n' "$NAME" >&2
  exit 1
fi

exit "$fail"
