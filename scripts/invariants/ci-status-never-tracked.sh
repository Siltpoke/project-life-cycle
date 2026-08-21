#!/usr/bin/env bash
# Invariant: `.claude/ci-status.json` is never git-tracked, and the path is ignored.
#
# WHY. The artifact is MACHINE-LOCAL by design: it records what one machine observed about one
# commit at one moment. Committing it publishes a fact about somebody else's clone, and — worse —
# a checkout of an older branch would then hand the card a green recorded against a commit nobody
# is standing on.
#
# Modelled on `scripts/invariants/tasklist-never-tracked.sh`, including its measured order.
#
# THE ORDER IS LOAD-BEARING, and it is copied because it was MEASURED there rather than reasoned:
# git's ignore rules DO NOT APPLY to tracked files, so `git check-ignore` answers 1 -- "not
# ignored" -- for a file that is both tracked and matched by a rule. Testing ignore-ness first
# therefore produces a TRUE FAILURE WITH A FALSE REASON: it sends the reader to `.gitignore` when
# the real problem is an index entry no ignore rule can override.
#
# WHAT THIS DELIBERATELY DOES NOT DO:
#
#   * It does NOT follow an environment override. Unlike the tasklist, this artifact has no
#     configurable path: `read_ci_status` resolves `<root>/.claude/ci-status.json` and nothing else
#     (scripts/session_card.py). Inventing an override here would be a guard for a configuration
#     that does not exist, and would then have to guess at its resolution rules.
#
#   * It does NOT sweep for `*ci-status*`. Other tracked files include the tests, the docs and this
#     script, all of which name the artifact; a broad sweep would red on every one of them. The
#     check is pinned to the one path the reader actually opens.
#
# EXIT 128 IS NOT EXIT 1. `git check-ignore` exits 0 when a path IS ignored, 1 when it is
# not, and 128 on a fatal error. Treating "any nonzero" as "not ignored" turns an environment bug
# into a confident, false finding about the repository. A check that could not run must never
# report as though it did.
#
# Envelope: bash + git only. No python3, no jq.

set -uo pipefail

NAME="ci-status-never-tracked"
ART=".claude/ci-status.json"

pass() { printf 'PASS %s: %s\n' "$NAME" "$1"; exit 0; }
fail() { printf 'FAIL %s: %s\n' "$NAME" "$1"; exit 1; }
# A third verdict: the CHECK failed, not the repo. The gate reads exit status only, so 1 and 3 both
# block -- the fail-closed behaviour a check that could not run must have. What 3 buys is that the
# distinction is legible to a direct caller, to CI, and to a test that can assert it.
cannot_run() { printf 'FAIL %s: COULD NOT RUN -- %s\n' "$NAME" "$1"; exit 3; }

REPO_ROOT="${1:-$(git rev-parse --show-toplevel 2>/dev/null || true)}"
[ -n "$REPO_ROOT" ] || cannot_run "not inside a git work tree (git rev-parse --show-toplevel failed)"
# Strip trailing slashes before anything compares against the root. Measured in the sibling script:
# a root passed as `/path/` produced a glob that matched nothing and a green that meant "I looked
# away". The root is a documented argument, so a trailing slash is a spelling callers do use.
while [ "$REPO_ROOT" != "/" ] && [ "$REPO_ROOT" != "${REPO_ROOT%/}" ]; do
  REPO_ROOT="${REPO_ROOT%/}"
done
cd "$REPO_ROOT" 2>/dev/null || cannot_run "cannot enter repo root: $REPO_ROOT"
git rev-parse --git-dir >/dev/null 2>&1 || cannot_run "$REPO_ROOT is not a git work tree"

# --- 1. TRACKED first, because tracking beats ignoring ----------------------------------------
if git ls-files --error-unmatch -- "$ART" >/dev/null 2>&1; then
  fail "the CI-status artifact is git-tracked: $ART
  -> TRACKING BEATS IGNORING. An ignore rule has no effect on a file already in the index, so this
     is not fixed by editing .gitignore -- \`git check-ignore\` will even report the path as
     'not ignored' while the rule sits right there.
  -> Remove it with \`git rm --cached $ART\` and commit that removal. The file records what ONE
     machine observed about ONE commit at ONE moment; committing it publishes a fact about someone
     else's clone, and a checkout of an older branch would then hand the card a green recorded
     against a commit nobody is standing on."
fi

# --- 2. and only then, is the path ignored ----------------------------------------------------
git check-ignore -q -- "$ART"
rc=$?
case "$rc" in
  0) : ;;
  1) fail "$ART is NOT ignored
  -> Add \`/$ART\` to .gitignore. A pattern containing a slash anywhere but the trailing position
     is ALREADY anchored to the .gitignore's directory, so the leading slash is the correct
     spelling and \`**/\` would be strictly looser." ;;
  128) cannot_run "git check-ignore exited 128 on '$ART' (fatal: bad cwd, unset GIT_DIR, or not a work tree). This is the CHECK failing, not a finding about the repo." ;;
  *) cannot_run "git check-ignore exited $rc on '$ART', which is outside its documented 0/1/128 contract" ;;
esac

pass "$ART is ignored and not tracked. Scope: this checks the ONE path the reader opens -- it does not sweep for other spellings, and it says nothing about copies outside this work tree"
