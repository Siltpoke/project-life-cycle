#!/usr/bin/env bash
# risk-tier.sh: parse and validate a phase's declared risk tier.
#
# A phase declares its tier in one machine-readable line in its qa-log fragment -- the same
# fragment `mode-provenance-recorded` reads -- in this shape:
#
#   risk: LOW | reason: <why>
#   risk: MEDIUM | reason: <why>
#   risk: HIGH | reason: <why>
#
# This script is the PARSER ONLY. It never decides the effective tier (that is the invariant's
# job, which also folds in the objective careful-paths floor). One job per component.
#
# Fail-safe, never silent. A line that is PRESENT but malformed, or MORE THAN ONE
# risk line, resolves to HIGH, with a note on stderr saying why -- never a silent fall to LOW.
# ZERO risk lines resolves to EMPTY (absent): a branch with no danger signal and no declaration
# is LOW by default elsewhere, so forcing a declaration on every branch is not this script's call.
#
# jq-free envelope: pure bash + grep (CLAUDE.md gate rule).

set -uo pipefail

LEGAL="LOW MEDIUM HIGH"

usage() {
  cat >&2 <<'EOF'
usage: risk-tier.sh <mode>

  --check-line "<line>"   exit 0 iff <line> is a well-formed `risk: <TIER> | reason: <non-empty>`
  --resolve <fragment>    print the DECLARED tier read from <fragment>:
                            exactly one valid line  -> that tier
                            zero risk lines          -> (empty: no declaration)
                            >1 lines, or malformed   -> HIGH   (fail-safe; reason on stderr)
  --levels                print the legal tiers, one per line
EOF
  exit 2
}

# A well-formed line: `risk: <LEGAL TIER> | reason: <at least one printable, non-space char>`.
# Kept as one ERE so --check-line and --resolve agree by construction.
is_valid_line() {
  printf '%s\n' "$1" | grep -qE '^risk: (LOW|MEDIUM|HIGH) \| reason: .*[[:graph:]].*$'
}

[ $# -ge 1 ] || usage

case "$1" in
  --levels)
    for t in $LEGAL; do printf '%s\n' "$t"; done
    ;;

  --check-line)
    [ $# -ge 2 ] || usage
    if is_valid_line "$2"; then exit 0; else
      printf 'risk-tier: not a well-formed risk line: %s\n' "$2" >&2
      exit 1
    fi
    ;;

  --resolve)
    [ $# -ge 2 ] || usage
    frag="$2"
    if [ ! -f "$frag" ]; then
      printf 'risk-tier: fragment not found: %s\n' "$frag" >&2
      # A missing fragment is not a malformed declaration; it is an absent one.
      exit 0
    fi
    # All lines that CLAIM to be a risk declaration (start with `risk:`), valid or not.
    all_count="$(grep -cE '^risk:' "$frag" 2>/dev/null || true)"
    all_count="${all_count:-0}"
    if [ "$all_count" -eq 0 ]; then
      # Absent: no declaration. Empty stdout, exit 0.
      exit 0
    fi
    valid_count="$(grep -cE '^risk: (LOW|MEDIUM|HIGH) \| reason: .*[[:graph:]].*$' "$frag" 2>/dev/null || true)"
    valid_count="${valid_count:-0}"
    if [ "$all_count" -eq 1 ] && [ "$valid_count" -eq 1 ]; then
      # Exactly one, and it is well-formed: honour it.
      line="$(grep -E '^risk: (LOW|MEDIUM|HIGH) \| reason: .*[[:graph:]].*$' "$frag" | head -1)"
      printf '%s\n' "$line" | sed -E 's/^risk: (LOW|MEDIUM|HIGH) \|.*/\1/'
      exit 0
    fi
    # Present but ambiguous (>1) or malformed: fail-safe to HIGH, and say why.
    if [ "$all_count" -gt 1 ]; then
      printf 'risk-tier: %s risk lines in %s -- ambiguous, resolving to HIGH (fail-safe)\n' \
        "$all_count" "$frag" >&2
    else
      printf 'risk-tier: the risk line in %s is malformed, resolving to HIGH (fail-safe)\n' \
        "$frag" >&2
    fi
    printf 'HIGH\n'
    ;;

  *) usage ;;
esac
