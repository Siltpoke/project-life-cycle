#!/usr/bin/env bash
# Invariant `mode-skip-marker-template`: every skip marker in the tree is the emitter's output, byte for byte.
#
# THE CHECK RE-RUNS THE EMITTER with each marker's own parsed parameters and compares. It does NOT
# re-implement the format. A second copy of the format here would be the exact drift the template exists
# to stop -- and it would be a copy sitting in the guard meant to prevent copies.
#
# A TREE WITH NO MARKERS IS A PASS THAT SAYS SO. "Nothing was checked" and "everything checked out"
# must not print the same line; an empty-scope PASS verifies nothing and would
# read like a clean bill of health.
#
# SCOPE, stated rather than left to be discovered: docs/ and the tracked skill tree. The marker's
# consumer is the pre-merge brief, which counts markers inside a phase's artifacts, and those live
# under docs/. A marker written into some other directory escapes this and would go uncounted.
#
# Verdicts: 0 pass, 1 a marker does not match the template, 3 the check could not run.
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

EMIT=skills/project-lifecycle/hooks/plc-skip-marker.sh
MODE_DOC=skills/project-lifecycle/references/mode.md
[ -r "$EMIT" ] || { printf 'COULD NOT RUN: %s is not readable\n' "$EMIT" >&2; exit 3; }
[ -r "$MODE_DOC" ] || { printf 'COULD NOT RUN: %s is not readable\n' "$MODE_DOC" >&2; exit 3; }

# THE MODE MUST COME FROM THE DECLARED SET, and this line is the whole reason the check is not
# self-satisfying. The first version fed each marker's OWN parsed parameters back into the emitter
# and compared -- so any internally consistent marker passed, including `mode=Fast`. It proved line
# 2 agrees with line 1 and nothing else. Measured, not reasoned: a planted `mode=Fast` marker was
# reported as one of "3 skip markers match the emitter byte for byte".
legal_modes="$(awk '
  /<!-- plc-mode-map:begin -->/ { inblk = 1; next }
  /<!-- plc-mode-map:end -->/   { inblk = 0; next }
  inblk && /^```json$/          { infence = 1; next }
  inblk && /^```$/              { infence = 0; next }
  inblk && infence              { print }
' "$MODE_DOC" | jq -r '.modes[]?')"
[ -n "$legal_modes" ] || { printf 'COULD NOT RUN: no modes declared in %s\n' "$MODE_DOC" >&2; exit 3; }

hits="$(/usr/bin/grep -rn 'plc-mode-skip:' docs skills --include='*.md' 2>/dev/null || true)"

# The emitter's own doc-comment and the mode document both SPELL the marker while explaining it.
# Those are quotations, not markers, and a checker that cannot tell a use from a mention is a
# recurring defect. The discriminator: a real marker is the whole line.
hits="$(printf '%s\n' "$hits" | /usr/bin/grep -E ':[0-9]+:[[:space:]]*<!-- plc-mode-skip: ' || true)"

if [ -z "$hits" ]; then
  printf 'ok  no skip markers in docs/ or skills/ -- nothing was checked, and this line says so\n'
  exit 0
fi

fail=0
count=0
while IFS= read -r hit; do
  [ -n "$hit" ] || continue
  file="${hit%%:*}"
  rest="${hit#*:}"
  lineno="${rest%%:*}"
  marker="${rest#*:}"
  marker="${marker#"${marker%%[![:space:]]*}"}"

  # `<!-- plc-mode-skip: STEP | mode=M | phase=P -->`
  if ! printf '%s' "$marker" | /usr/bin/grep -qE '^<!-- plc-mode-skip: [A-Za-z0-9._-]+ \| mode=[A-Za-z0-9._-]+ \| phase=[A-Za-z0-9._-]+ -->$'; then
    printf 'FAIL %s:%s: marker does not match the fixed shape\n    %s\n' "$file" "$lineno" "$marker" >&2
    fail=1
    continue
  fi
  step="$(printf '%s' "$marker" | sed -E 's/^<!-- plc-mode-skip: ([^ ]+) .*/\1/')"
  mode="$(printf '%s' "$marker" | sed -E 's/.*\| mode=([^ ]+) .*/\1/')"
  phase="$(printf '%s' "$marker" | sed -E 's/.*\| phase=([^ ]+) -->$/\1/')"

  case $'\n'"$legal_modes"$'\n' in
    *$'\n'"$mode"$'\n'*) ;;
    *) printf 'FAIL %s:%s: mode=%s is not a declared mode (%s)\n' \
         "$file" "$lineno" "$mode" "$(printf '%s' "$legal_modes" | tr '\n' ' ')" >&2
       fail=1; continue ;;
  esac

  expected="$(/bin/bash "$EMIT" "$step" "$mode" "$phase")"
  want_1="$(printf '%s\n' "$expected" | sed -n '1p')"
  want_2="$(printf '%s\n' "$expected" | sed -n '2p')"

  got_2="$(sed -n "$((lineno + 1))p" "$file")"
  got_2="${got_2#"${got_2%%[![:space:]]*}"}"

  if [ "$marker" != "$want_1" ]; then
    printf 'FAIL %s:%s: line 1 is not the emitter output\n    got:  %s\n    want: %s\n' \
      "$file" "$lineno" "$marker" "$want_1" >&2
    fail=1
  fi
  if [ "$got_2" != "$want_2" ]; then
    printf 'FAIL %s:%s: line 2 is not the emitter output\n    got:  %s\n    want: %s\n' \
      "$file" "$((lineno + 1))" "$got_2" "$want_2" >&2
    fail=1
  fi
  count=$((count + 1))
done <<<"$hits"

[ "$fail" = 0 ] || exit 1
printf 'ok  %d skip marker(s) match the emitter byte for byte\n' "$count"
