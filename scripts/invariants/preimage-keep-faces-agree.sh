#!/usr/bin/env bash
# Invariant: the pre-image ring's depth is ONE number, readable on both policy faces and from the
# script that acts on it.
#
# WHY. `preimage_keep` governs how many pre-image generations survive a prune, and for its whole
# life it was a literal `5` sitting in the drain's source as a fallback. The number was real and
# load-bearing, and the only way to read it was to open the script -- so a repo could not state its
# own retention depth, and a reader could not check one. A number nobody can read without reading
# the code is not a policy.
#
# WHAT IS CHECKED, AND WHY THE THIRD CHECK IS NOT REDUNDANT. The two faces are `CLAUDE.md`'s
# `retention:` block (kebab-case, the human face) and `.claude/close-gate.json`'s
# `retention.preimage_keep` (snake_case, the machine face). Holding those two to each other is not
# enough: both could agree on a value the drain never acts on, because the drain applies its own
# fallback to anything it cannot parse. So the EFFECTIVE value is read from the drain itself
# (`retention-drain.sh config preimage_keep`) and compared as well. That closes the one gap a
# two-face check leaves open -- a malformed declaration passing because the fallback happens to be
# the number the faces agree on.
#
# AND THE FLOOR IS CHECKED HERE TOO, at 1. A ring that keeps nothing is a drain with no undo. The
# script refuses 0 at run time; this refuses it at declaration time, which is where it is cheaper
# to notice.
#
# NOT CHECKED: that 5 is the right depth, or that the ring is large enough for any particular
# workload. This holds a number consistent; it does not have an opinion about its size.
#
# Verdicts: 0 pass, 1 a face drifted or the value is out of range, 3 could not run.

set -uo pipefail

NAME="preimage-keep-faces-agree"
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT" || { printf 'COULD-NOT-RUN %s: cannot cd to %s\n' "$NAME" "$ROOT" >&2; exit 3; }

HUMAN="CLAUDE.md"
MACHINE=".claude/close-gate.json"
DRAIN="scripts/retention-drain.sh"

command -v jq >/dev/null 2>&1 || { printf 'COULD-NOT-RUN %s: jq is not installed\n' "$NAME" >&2; exit 3; }
for f in "$HUMAN" "$MACHINE" "$DRAIN"; do
  [ -f "$f" ] || { printf 'COULD-NOT-RUN %s: %s is missing\n' "$NAME" "$f" >&2; exit 3; }
done

# The human face. Anchored at the start of an INDENTED line so a mention of the key in prose --
# this file's header does it, and so does the reference doc -- is not read as a declaration.
human_lines="$(grep -cE '^[[:space:]]+preimage-keep:[[:space:]]*[^[:space:]]' "$HUMAN")" || human_lines=0
if [ "$human_lines" -ne 1 ]; then
  printf 'FAIL %s: %s carries %s `preimage-keep:` declaration(s) in its retention: block; expected exactly 1.\n' "$NAME" "$HUMAN" "$human_lines" >&2
  printf '  -> Zero means the human face does not state the depth at all, which is the state this\n' >&2
  printf '     invariant was written to end. More than one means two answers with nothing choosing.\n' >&2
  exit 1
fi
human="$(grep -E '^[[:space:]]+preimage-keep:[[:space:]]*[^[:space:]]' "$HUMAN" | head -1 | sed -E 's/^[[:space:]]*preimage-keep:[[:space:]]*//; s/[[:space:]].*$//; s/#.*$//')"

# The machine face. `// empty` BEFORE `tostring`, and that order was measured rather than
# reasoned: `.retention.preimage_keep | tostring` turns a missing key into the four-character
# string `null`, which sails past `jq -re` and lands in the integer check below -- so the branch
# written for a missing key never ran, and the message a reader got named a type error instead of
# an absent declaration. A planted removal is what showed it.
machine="$(jq -re '.retention.preimage_keep // empty | tostring' "$MACHINE" 2>/dev/null)" || {
  printf 'FAIL %s: %s declares no `retention.preimage_keep`.\n' "$NAME" "$MACHINE" >&2
  printf '  -> The machine face is what the drain reads. Without it the drain falls back to its\n' >&2
  printf '     built-in 5, and the human face above would be describing a number nothing uses.\n' >&2
  exit 1
}

# The effective value, from the script that acts on it.
effective="$(/bin/bash "$DRAIN" config preimage_keep 2>/dev/null)" || {
  printf 'FAIL %s: `%s config preimage_keep` did not succeed, so the effective value cannot be read.\n' "$NAME" "$DRAIN" >&2
  printf '  -> That accessor is the only thing that reports the number the drain ACTS on. A check\n' >&2
  printf '     of the two declarations alone cannot see a malformed one hiding behind a fallback.\n' >&2
  exit 1
}

case "$human" in ''|*[!0-9]*)
  printf 'FAIL %s: the %s declaration is `%s`, which is not a non-negative integer.\n' "$NAME" "$HUMAN" "$human" >&2
  exit 1 ;;
esac
case "$machine" in ''|*[!0-9]*)
  printf 'FAIL %s: the %s declaration is `%s`, which is not a non-negative integer.\n' "$NAME" "$MACHINE" "$machine" >&2
  printf '  -> The drain cannot parse it either, so it falls back to 5 and runs with a depth nobody\n' >&2
  printf '     declared. That is the silent-fallback case this invariant exists for.\n' >&2
  exit 1 ;;
esac

if [ "$human" != "$machine" ]; then
  printf 'FAIL %s: the two policy faces disagree -- %s says %s, %s says %s.\n' "$NAME" "$HUMAN" "$human" "$MACHINE" "$machine" >&2
  printf '  -> Change both in one commit. A reader checks whichever one they happen to open.\n' >&2
  exit 1
fi
if [ "$machine" != "$effective" ]; then
  printf 'FAIL %s: both faces declare %s, but the drain acts on %s.\n' "$NAME" "$machine" "$effective" >&2
  printf '  -> The declaration is not reaching the script: it is malformed in a way the drain\n' >&2
  printf '     swallows, or the accessor and the drain no longer read the same variable. Either way\n' >&2
  printf '     the declared number is decoration.\n' >&2
  exit 1
fi
if [ "$effective" -lt 1 ]; then
  printf 'FAIL %s: the effective preimage_keep is %s. A ring that keeps nothing is a drain with no undo.\n' "$NAME" "$effective" >&2
  printf '  -> Declare at least 1 on both faces.\n' >&2
  exit 1
fi

printf 'PASS %s: preimage_keep = %s on both faces (%s, %s) and as the effective value the drain acts on (`%s config preimage_keep`), floor 1 respected. Scope: consistency and range only -- this says nothing about whether %s is the right depth.\n' \
  "$NAME" "$effective" "$HUMAN" "$MACHINE" "$DRAIN" "$effective"
