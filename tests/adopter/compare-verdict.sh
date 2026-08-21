#!/usr/bin/env bash
# Assert the adopter run's VERDICT: the exit codes it declared and the exact SET of ✗ rows the
# gate printed. This is the counterpart to compare-reached.sh and its oracle is deliberately the
# opposite shape -- reached is "expected ⊆ observed" (unrelated extra output must not fail it),
# verdict is SET EQUALITY (an unexpected ✗ is a new product finding nobody looked at, and a
# missing ✗ means the product changed under a fixture that still claims to catch it). A subset
# oracle here would let the fixture go on asserting a finding that had silently disappeared.
#
# The ✗ set is compared DEDUPLICATED. A row printed twice is a cosmetic property of the gate's
# output, not a verdict change, and reddening on it would make this file a layout test.
#
# Zero is never vacuous: an unreadable expected file, one that parses to nothing, or one that
# lists no ✗ rows without saying NO-FAIL-ROWS out loud, is a FAIL. An empty scope that prints PASS
# is a known failure shape.
set -euo pipefail
CAPTURE="${1:?usage: compare-verdict.sh <capture> <expected-verdict.txt>}"
EXPECTED="${2:?usage: compare-verdict.sh <capture> <expected-verdict.txt>}"
[ -r "$CAPTURE" ]  || { echo "FAIL: capture unreadable: $CAPTURE"; exit 2; }
[ -r "$EXPECTED" ] || { echo "FAIL: expected-verdict unreadable: $EXPECTED"; exit 2; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

rc=0
pins=0
rows=0
no_fail_rows=0
: > "$TMP/expected-rows"

# --- parse the expected file -------------------------------------------------------------
while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in
    ""|"#"*)          continue ;;
    "✗ "*)            printf '%s\n' "$line" >> "$TMP/expected-rows"; rows=$(( rows + 1 )) ;;
    "NO-FAIL-ROWS")   no_fail_rows=1 ;;
    ADOPTER-*=*)
      key="${line%%=*}"
      want="${line#*=}"
      pins=$(( pins + 1 ))
      # Byte-exact AND exactly once. A key appearing twice means the capture concatenated two
      # runs, and "the value I wanted is in there somewhere" is not the same claim as "this run
      # produced it".
      n="$(LC_ALL=C /usr/bin/grep -c "^${key}=" "$CAPTURE" || true)"
      if [ "$n" -ne 1 ]; then
        echo "FAIL: $key appears $n times in the capture (expected exactly 1)"
        rc=1
        continue
      fi
      got="$(LC_ALL=C /usr/bin/grep "^${key}=" "$CAPTURE")"
      if [ "$got" = "$line" ]; then
        echo "  pinned: $line"
      else
        echo "FAIL: expected \`$line\` but the capture says \`$got\`"
        rc=1
      fi
      ;;
    *)
      # An unrecognized line is not skipped. A typo in a pin key, or a ✗ row that lost its glyph
      # to an editor, would otherwise silently shrink what this file asserts.
      echo "FAIL: unrecognized line in $EXPECTED (not a comment, an ADOPTER-*= pin, a ✗ row, or NO-FAIL-ROWS):"
      echo "  $line"
      rc=1
      ;;
  esac
done < "$EXPECTED"

if [ "$pins" -eq 0 ] && [ "$rows" -eq 0 ] && [ "$no_fail_rows" -eq 0 ]; then
  echo "FAIL: $EXPECTED asserts nothing (no pins, no ✗ rows, no NO-FAIL-ROWS)"
  exit 1
fi
if [ "$rows" -eq 0 ] && [ "$no_fail_rows" -eq 0 ]; then
  echo "FAIL: $EXPECTED lists no ✗ rows and does not say NO-FAIL-ROWS"
  echo "  \"I expect none\" and \"I forgot to write them\" must not look the same"
  exit 1
fi
if [ "$rows" -ne 0 ] && [ "$no_fail_rows" -ne 0 ]; then
  echo "FAIL: $EXPECTED says NO-FAIL-ROWS and also lists $rows ✗ row(s)"
  exit 1
fi

# --- compare the ✗ set -------------------------------------------------------------------
LC_ALL=C /usr/bin/grep '^✗' "$CAPTURE" > "$TMP/actual-raw" || true
LC_ALL=C sort -u "$TMP/actual-raw"      > "$TMP/actual"
LC_ALL=C sort -u "$TMP/expected-rows"   > "$TMP/expected"

missing="$(LC_ALL=C comm -23 "$TMP/expected" "$TMP/actual")"
unexpected="$(LC_ALL=C comm -13 "$TMP/expected" "$TMP/actual")"

if [ -n "$missing" ]; then
  echo "FAIL: expected ✗ row(s) the run did NOT produce -- the product changed under a fixture that still claims to catch this:"
  printf '%s\n' "$missing" | while IFS= read -r m; do echo "  $m"; done
  rc=1
fi
if [ -n "$unexpected" ]; then
  echo "FAIL: ✗ row(s) the run produced that nobody has looked at -- triage each, then either fix it or add it here:"
  printf '%s\n' "$unexpected" | while IFS= read -r u; do echo "  $u"; done
  rc=1
fi

n_actual="$(LC_ALL=C /usr/bin/grep -c . "$TMP/actual" || true)"
if [ "$rc" -eq 0 ]; then
  echo "ok: verdict matches -- $pins exit pin(s), $n_actual ✗ row(s), set-equal to $EXPECTED"
fi
exit "$rc"
