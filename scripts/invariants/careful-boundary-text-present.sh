#!/usr/bin/env bash
# Invariant `careful-boundary-text-present`: the four "what this will miss" statements
# and the fixup gap are in the shipped text, and nothing claims more than the mechanism does.
#
# WHY THIS IS A GUARD AND NOT A REVIEW NOTE. Every one of these sentences exists because a review
# found the document promising more than the code delivers. Left as prose, each is one careless
# edit from disappearing, and its disappearance is invisible -- nothing else fails.
#
# WHAT IT DOES NOT DO. It checks that the sentences are PRESENT. It cannot check that they are
# true, or that a reader believes them. Saying so here is cheaper than letting a green imply it.
#
# Verdicts: 0 pass, 1 the repository is wrong, 3 the check could not run.
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

DATA=skills/project-lifecycle/references/careful-paths.md
SCREEN=skills/project-lifecycle/references/kickoff-confirmation.md

for f in "$DATA" "$SCREEN"; do
  [ -r "$f" ] || { printf 'COULD NOT RUN: %s is not readable\n' "$f" >&2; exit 3; }
done

fail=0
need() { # need <file> <label> <fixed string>
  if ! /usr/bin/grep -qi -- "$3" "$1"; then
    printf 'FAIL %s: the %s statement is gone -- it is not decoration, it is the boundary a review put there\n' "$1" "$2" >&2
    fail=1
  fi
}

# The four misses, in the contract. Each is a DIFFERENT way this feature misses something, so each
# is checked on its own: one "the misses are present" probe would pass with three of four.
need "$DATA" "user-marking-is-incomplete"   "marked by you"
need "$DATA" "unnamed-ecosystem-is-a-miss"  "do not name is a miss"
need "$DATA" "vocabulary-is-english"        "word list is english"
need "$DATA" "by-path-not-by-intent"        "deleted"
need "$DATA" "by-path-not-by-intent"        "moved"

# The same four on the screen a person actually reads. The contract is for the adopter; the screen
# is for the user, and a boundary stated only in the contract is a boundary the user never sees.
need "$SCREEN" "user-marking-is-incomplete" "do not mark"
need "$SCREEN" "unnamed-ecosystem-is-a-miss" "do not name is a miss"
need "$SCREEN" "vocabulary-is-english"       "english words"
need "$SCREEN" "by-path-not-by-intent"       "removed"

# The fixup gap. Claiming the coverage window COVERS it would be
# a claim wider than its mechanism -- a final-pass review is not an upgrade of three
# verification stages -- so the text states a gap instead. This pins that wording.
need "$DATA" "fixup-is-a-stated-gap" "does not trigger a careful upgrade"
need "$DATA" "fixup-is-not-covered"  "not the same thing"

# The unbounded word list. "Ships no mechanism for it" and "does not even say so" are different
# things, and only the first is acceptable.
need "$DATA" "word-list-has-no-bound" "no upper bound"

# And the claim the whole feature is forbidden to make, checked as a NEGATIVE: the phrase may
# appear, but only with a negation in front of it.
if /usr/bin/grep -qi 'detect all high-risk' "$DATA"; then
  if ! /usr/bin/grep -qiE '(not|never|cannot|does not) claim to (detect|find) (every|all)' "$DATA"; then
    printf 'FAIL %s: claims it detects all high-risk changes with no negation -- it cannot, and saying it can is the lie this file exists to prevent\n' "$DATA" >&2
    fail=1
  fi
fi

[ "$fail" = 0 ] || exit 1
printf 'ok  four misses stated in both the contract and the screen, the fixup gap is stated as a gap, and the word list is declared unbounded\n'
