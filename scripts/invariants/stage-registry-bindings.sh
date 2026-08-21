#!/usr/bin/env bash
# Invariant: the stage registry's gate-check bindings still point at something.
#
# WHY. `.claude/stage-registry.json` binds stage ids to close-gate checks so that the reader's
# denominator is computable. It binds to the gate's check IDENTIFIERS -- the shell variables the
# gate branches on -- and never to their ordinal positions, because the numbers move: check 9 was
# added after the table that numbered 1..8, and 9b was inserted after 9. Renumbering is then free.
# Renaming is what this makes loud.
#
# The class it belongs to: a declaration wider than its
# mechanism. A registry that names `RUN_JOURNAL` after someone renames that variable is a table
# claiming a binding that does not exist, and nothing else in the tree would notice -- the gate
# still runs, the registry still parses, and the scanner still emits a row.
#
# WHAT IT DOES NOT DO, stated rather than discovered later:
#   * it does not check that the named variable GATES the check the registry says it does. It
#     checks the token is present. A rename is caught; a rewiring is not.
#   * it is lexical. A variable spelled `RUN_${WHICH}` would be invisible to it. Deliberate evasion
#     is not the threat -- drift is, and drift arrives spelled out.
#   * a row with `gate_check: null` is out of scope by construction. Those are the stages with no
#     deterministic writer, and they are the entire point of the registry.
#     Their absence from this check is not a gap in it.
#
# THE INPUTS ARE ARGUMENTS, NEVER ENVIRONMENT VARIABLES. A
# checker whose scan root can be relocated from outside can be
# pointed at the wrong file, producing a green over a file nobody meant to
# check. The self-coverage assertion at the bottom calls the same function with a different pair of
# paths, in-process.
#
# Envelope: bash + jq only. No python3.

set -uo pipefail

NAME="stage-registry-bindings"
pass() { printf 'PASS %s: %s\n' "$NAME" "$1"; exit 0; }
fail() { printf 'FAIL %s: %s\n' "$NAME" "$1"; exit 1; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGISTRY="${1:-$HERE/../../.claude/stage-registry.json}"
GATE="${2:-$HERE/../close-gate.sh}"

command -v jq >/dev/null 2>&1 || fail "jq not found"

# Returns the problems with one (registry, gate) pair, one per line. Empty output = clean.
# A function, so the self-coverage assertion below can call it on a planted pair.
check_pair() {
  local registry="$1" gate="$2" rows ids id n
  [ -r "$registry" ] || { printf 'registry is unreadable: %s\n' "$registry"; return 0; }
  [ -r "$gate" ]     || { printf 'gate script is unreadable: %s\n' "$gate"; return 0; }
  jq -e . "$registry" >/dev/null 2>&1 || { printf 'registry is not valid JSON: %s\n' "$registry"; return 0; }

  # Shape first. A malformed registry that produced zero bindings would satisfy every binding
  # assertion below -- the empty-set pass ledger-contract-sync.sh also guards against.
  n="$(jq '[.stages[]? | select(type == "object")] | length' "$registry" 2>/dev/null || echo 0)"
  if [ "${n:-0}" -eq 0 ]; then
    printf 'registry declares no stages -- an empty registry makes the row count vacuous, not satisfied\n'
    return 0
  fi

  # jq emits the finished sentences, one per line — NOT positional columns for the shell to
  # reassemble. `@tsv` plus `IFS=$'\t' read` cannot carry an empty field: tab is IFS WHITESPACE, so
  # a run of tabs delimits as one no matter what IFS is set to, and every empty column silently
  # shifts the rest left. A fixture whose only defect is a
  # LATER column reports the FIRST column's message instead, naming the wrong field on a
  # correct stage_id. One message per line has no columns to shift.
  rows="$(jq -r '
      .stages[]
      | (.stage_id // "<a stage with no stage_id>") as $sid
      | [ (if ($sid | type) != "string" or ($sid == "")
           then "stage_id must be a non-empty string: " + ($sid | tostring) else empty end),
          (if has("mandated_when") | not
           then $sid + ": no mandated_when (the field may be prose, but it must exist)" else empty end),
          (if has("writer") | not
           then $sid + ": no writer field (use null for \"no deterministic writer\")" else empty end),
          (if has("gate_check") | not
           then $sid + ": no gate_check field (use null for \"no gate check\")" else empty end),
          (if ((.available_from // "") | test("^[0-9]{4}-[0-9]{2}-[0-9]{2}$")) | not
           then $sid + ": available_from must be YYYY-MM-DD" else empty end),
          (if ((.available_from_basis // "") | length) == 0
           then $sid + ": available_from_basis is empty -- a date whose provenance is unstated cannot be judged"
           else empty end)
        ] | .[]' "$registry")"
  [ -z "$rows" ] || printf '%s\n' "$rows"

  # Duplicate stage ids. The registry IS the denominator, so a duplicate inflates it silently.
  jq -r '[.stages[].stage_id] | group_by(.) | map(select(length > 1)) | .[] | .[0]' "$registry" 2>/dev/null |
    while IFS= read -r id; do
      [ -n "$id" ] && printf 'duplicate stage_id: %s\n' "$id"
    done

  # The binding itself.
  ids="$(jq -r '.stages[] | select(.gate_check != null) | .gate_check' "$registry" 2>/dev/null)"
  if [ -z "$ids" ]; then
    printf 'no stage binds a gate_check -- either every binding was dropped, or this check is reading the wrong file\n'
    return 0
  fi
  while IFS= read -r id; do
    [ -n "$id" ] || continue
    # The identifier must be a shell variable name. Checked rather than assumed, because the value
    # goes straight into a regex below and a `.` in it would match anything.
    case "$id" in
      [!A-Za-z_]*|*[!A-Za-z0-9_]*)
        printf 'gate_check %s is not a shell identifier -- bindings name variables, not patterns\n' "$id"
        continue ;;
    esac
    # TOKEN boundary, not a substring. `grep -F RUN_JOURNAL` matches `RUN_JOURNAL_RENAMED`, so a
    # rename to a longer name would slip past -- which is not a hypothetical: this check's OWN
    # self-coverage probe below renamed exactly that way and the first version of this line
    # reported nothing. A rename is the whole failure mode being guarded, and half of all renames
    # are extensions of the old name.
    grep -qE "(^|[^A-Za-z0-9_])${id}([^A-Za-z0-9_]|\$)" "$gate" ||
      printf 'gate_check %s is bound by the registry but does not appear in %s\n' "$id" "$gate"
  done <<EOF
$ids
EOF
}

PROBLEMS="$(check_pair "$REGISTRY" "$GATE")"

# Report the real finding FIRST. Self-coverage exists to guard a GREEN — it is the answer to "did
# this check read anything" — so running it ahead of a real problem replaces an accurate message
# with a note about a planted fixture, and the reader is sent to debug the probe instead of the
# registry. Run the other way round, a fixture reports "self-coverage could not
# run" while the actual defect (a missing field, an empty stage list) goes unmentioned.
if [ -n "$PROBLEMS" ]; then
  printf 'FAIL %s:\n' "$NAME"
  printf '  %s\n' "$PROBLEMS"
  exit 1
fi

# --- self-coverage: prove this can fail, on a pair it constructs itself ---------
# Without this, "no problems" and "read nothing" print the same PASS. The planted pair renames one
# bound identifier in a COPY of the gate; the check must report exactly that identifier.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
FIRST_BOUND="$(jq -r 'first(.stages[] | select(.gate_check != null) | .gate_check) // ""' "$REGISTRY" 2>/dev/null || true)"
if [ -n "$FIRST_BOUND" ] && [ -r "$GATE" ]; then
  # TWO planted renames, because they fail differently. The first replaces the identifier outright
  # (no trace of the old name); the second EXTENDS it, which is what a real rename usually looks
  # like and what the substring matcher this check started with could not see.
  sed "s/${FIRST_BOUND}/PLANTED_GONE/g" "$GATE" > "$TMP/gate.sh"
  sed "s/${FIRST_BOUND}/${FIRST_BOUND}_RENAMED/g" "$GATE" > "$TMP/gate-extended.sh"
  for planted in "$TMP/gate.sh" "$TMP/gate-extended.sh"; do
    SELF="$(check_pair "$REGISTRY" "$planted")"
    case "$SELF" in
      *"gate_check $FIRST_BOUND is bound by the registry"*) ;;
      *) fail "self-coverage FAILED on $(basename "$planted"): renaming $FIRST_BOUND in a copy of the gate did not produce a finding, so a green here proves nothing. Got: ${SELF:-<no output>}" ;;
    esac
  done
else
  fail "self-coverage could not run: no bound gate_check in $REGISTRY, or $GATE unreadable"
fi

BOUND="$(jq -r '[.stages[] | select(.gate_check != null)] | length' "$REGISTRY")"
TOTAL="$(jq -r '.stages | length' "$REGISTRY")"
pass "$TOTAL stages declared, $BOUND bound to a close-gate identifier and every one of them still present in $(basename "$GATE"); self-coverage confirmed by renaming $FIRST_BOUND in a copy"
