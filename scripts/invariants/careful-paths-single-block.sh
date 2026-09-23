#!/usr/bin/env bash
# Invariant `careful-paths-single-block`: the careful-paths data is ONE block, and the
# two shipped readers can both read it.
#
# TWO DIRECTIONS, and the second is the one that bites. Zero blocks is a broken file anybody notices
# on the next run. TWO blocks is a file that reads fine to a human and where a reader silently picks
# one -- the same fact written twice with the reader landing on the stale copy.
#
# BOTH READERS ARE RUN, not one. The check reads `signals`; the suggester reads `words`. A block
# that lost one of the two would still satisfy a single-reader probe, which is how a green comes to
# mean less than it looks.
#
# Verdicts: 0 pass, 1 the repository is wrong, 3 the check could not run.
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

DATA=skills/project-lifecycle/references/careful-paths.md
CHECK=skills/project-lifecycle/hooks/plc-careful-check.sh
SUGGEST=skills/project-lifecycle/hooks/plc-careful-suggest.sh

for f in "$DATA" "$CHECK" "$SUGGEST"; do
  [ -r "$f" ] || { printf 'COULD NOT RUN: %s is not readable\n' "$f" >&2; exit 3; }
done
command -v jq  >/dev/null 2>&1 || { printf 'COULD NOT RUN: jq is not on PATH\n' >&2; exit 3; }
command -v git >/dev/null 2>&1 || { printf 'COULD NOT RUN: git is not on PATH\n' >&2; exit 3; }

begins=$(/usr/bin/grep -c '<!-- plc-careful-data:begin -->' "$DATA" || true)
ends=$(/usr/bin/grep -c '<!-- plc-careful-data:end -->' "$DATA" || true)
if [ "$begins" != 1 ] || [ "$ends" != 1 ]; then
  printf 'FAIL %s: expected exactly one sentinel pair, found %s begin / %s end\n' \
    "$DATA" "$begins" "$ends" >&2
  exit 1
fi

# GIT_DIR OVERRIDES `-C`, AND THE ENVIRONMENT IS THEREFORE CLEARED BEFORE ANY FIXTURE IS BUILT.
#
# p33 CORRECTION -- what this comment used to say, and why the sentence changed. It read:
# "A GIT HOOK RUNS WITH GIT_DIR SET, AND GIT_DIR OVERRIDES `-C` (root cause of a measured incident, proved not
# guessed)." The second clause is true and reproducible. The FIRST IS FALSE, and it is corrected
# here rather than deleted, because deleting it would leave the surviving conclusion unsupported.
#
# Measured on a recent git, across pre-commit, prepare-commit-msg,
# commit-msg, post-commit, pre-push and post-checkout: NO hook type exports GIT_DIR or
# GIT_WORK_TREE. Commit-family hooks export GIT_INDEX_FILE (relative); pre-push exports only
# GIT_EDITOR, GIT_EXEC_PATH, GIT_PREFIX. Nothing in this repository exports it either -- the chain
# is pre-push -> close-gate-prepush.sh -> close-gate.sh -> invariants, and the only variable
# close-gate.sh exports is AC_MERGE_BASE. The proof the old wording cited,
# `scratchpad/prove_gitdir.sh`, no longer exists; what it most likely established is the
# conditional half, with the antecedent assumed. A claim wider than its mechanism, inside a fix
# written for that class.
#
# WHAT REMAINS TRUE, AND IS WHY THIS SCRIPT STILL CLEARS THE ENVIRONMENT. With GIT_DIR set --
# by whatever means -- `git -C <tmp> commit` writes into the repository GIT_DIR names, and an
# assertion on `--show-toplevel` still PASSES because the worktree follows the cwd while the
# commit follows GIT_DIR. Reproduced end to end: the decoy's HEAD moved and every real file came
# out as a deletion. the incident is real history; only its stated mechanism is unproven, and
# the actual cause of the 2026-08-19 commits is recorded as UNKNOWN rather than guessed at.
#
# So this stays, as insurance against an injection vector not yet identified -- stated as
# insurance, not sold as a fix for a measured failure path.
# Clear the WHOLE GIT_* family, not a list of six names. An enumerated list is a claim that git
# will never add another variable able to redirect a read or a write, and nothing announces the
# day that stops being true -- a claim wider than its mechanism. The python
# fixtures already filter by prefix (`not k.startswith("GIT_")`); this is parity with them.
#
# This script only READS from its fixture, but a read against the wrong repository is
# just a quieter version of the same defect: it would answer about the real tree and call that a
# pass. Cleared here for the same reason it is cleared where a commit happens.
#
# Measured, with a probe first proven able to detect a real bypass (removing the protection moves
# a decoy repository's HEAD): with GIT_DIR, GIT_CONFIG_COUNT/core.worktree and GIT_NAMESPACE all
# poisoned at once, this leaves zero GIT_* set and the decoy's HEAD does not move.
#
# The six-name form this replaces was NOT found exploitable -- five injection vectors were tried
# and none reached the decoy. It is replaced because its correctness depends on a future git
# release, not because a bypass was demonstrated.
for _gv in $(env | sed -n 's/^\(GIT_[A-Za-z0-9_]*\)=.*/\1/p'); do unset "$_gv"; done
unset _gv

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
git init -q "$tmp/p"
printf '# p\ncareful-paths: src/auth/\n' > "$tmp/p/CLAUDE.md"
mkdir -p "$tmp/p/src/auth"
printf 'x\n' > "$tmp/p/src/auth/session.ts"

# Reader 1 reads `signals` and the declared key. A hit is REQUIRED: a reader that returns no-hit on
# a tree built to hit is indistinguishable from one that read nothing at all.
if ! out1="$(/bin/bash "$CHECK" --claude-md "$tmp/p/CLAUDE.md" --repo "$tmp/p" --data "$DATA" 2>"$tmp/e1")"; then
  printf 'FAIL the shipped check cannot read the data block:\n' >&2
  sed 's/^/  /' "$tmp/e1" >&2
  exit 1
fi
case "$out1" in
  no-hit*) printf 'FAIL the check returned no-hit on a tree built to hit -- it read nothing useful\n' >&2; exit 1 ;;
esac
if ! printf '%s\n' "$out1" | awk -F'\t' 'NF != 3 { exit 1 }'; then
  printf 'FAIL the check emitted a row that is not <class>\\t<rule>\\t<path>\n' >&2
  exit 1
fi

# Reader 2 reads `words`. Same argument: a suggester returning no-candidates on a tree containing a
# directory named `auth` has not read the vocabulary.
if ! out2="$(/bin/bash "$SUGGEST" --repo "$tmp/p" --claude-md "$tmp/p/CLAUDE.md" --data "$DATA" 2>"$tmp/e2")"; then
  printf 'FAIL the shipped suggester cannot read the data block:\n' >&2
  sed 's/^/  /' "$tmp/e2" >&2
  exit 1
fi
case "$out2" in
  no-candidates*) printf 'FAIL the suggester found nothing in a tree containing src/auth/ -- it read no vocabulary\n' >&2; exit 1 ;;
esac

printf 'ok  careful-paths data is a single block both shipped readers can read (%s hit row(s), %s candidate row(s))\n' \
  "$(printf '%s\n' "$out1" | wc -l | tr -d ' ')" "$(printf '%s\n' "$out2" | wc -l | tr -d ' ')"
