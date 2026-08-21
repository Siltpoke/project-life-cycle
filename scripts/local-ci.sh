#!/usr/bin/env bash
# Run this repository's REAL GitHub Actions workflow locally, in Docker, via `act`.
#
#   bash scripts/local-ci.sh [<branch>] [<output-file>]
#
# Requires: `act` (brew install act / https://nektosact.com) and a running Docker daemon.
# Optional: `lychee` on the host — see the link-check block below for why it is not run in the
# container.
#
# WHY THIS EXISTS. When CI is unavailable — billing exhausted, offline, a fork without Actions —
# the reflex is "just run the tests locally". That reflex misses what CI was for.
# The value CI provides is not "it runs the tests" but "it runs them on a machine that is not
# yours". Each difference below can turn a green local suite into a red CI run, and none of them
# is reproducible by re-running the suite in your own shell:
#
#   Linux + GNU coreutils  ->  `cut -c` counts BYTES, so a generator can silently rewrite
#                              CJK-bearing text as invalid UTF-8, in place
#   C locale               ->  the same defect reached by a second path
#   clean checkout         ->  untracked local artifacts absent, so a premise that only held
#                              because of them fails
#   lychee installed       ->  broken links, unreachable by any local check
#
# So this script does not run the suite. It reconstructs the DIFFERENCES.
#
# ------------------------------------------------------------------------------------------------
# THREE SETTINGS THIS SCRIPT NEEDS. Without each one, the local run reports failures that real CI
# does not.
#
#   1. act runs the container as ROOT; GitHub's runner does not. Several tests here simulate an
#      unwritable path with `chmod 0555` and assert the operation refuses — and root ignores
#      permission bits entirely. Inside the image:
#          as root      : writing into a 0555 directory SUCCEEDED
#          as non-root  : refused
#      Hence `--user 1000` (`ubuntu` exists in catthehacker's image and is in the sudo
#      group).
#
#   2. A `--single-branch` clone has no `origin/main`, and the close-gate resolves
#      `git merge-base origin/main HEAD`. Hence the fetch below.
#
#   3. The link-check targets. scripts/lib/lychee-pin.env defines both, and says why there are two.
#
# ------------------------------------------------------------------------------------------------
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="${1:-$(git -C "$REPO" rev-parse --abbrev-ref HEAD)}"
SLUG="$(printf '%s' "$BRANCH" | tr '/' '-')"
OUT="${2:-${TMPDIR:-/tmp}/local-ci-$SLUG.txt}"
WORK="$(dirname "$OUT")/local-ci-clone-$SLUG"

command -v act >/dev/null 2>&1 || { echo "act is not installed (brew install act)" >&2; exit 2; }
docker info >/dev/null 2>&1    || { echo "the docker daemon is not running" >&2; exit 2; }

# A CLEAN CLONE, not the working tree. This is the point of the whole exercise: `act` would
# happily mount the working directory, and the working directory carries every untracked artifact
# the local machine has accumulated — which is precisely the difference a CI checkout does not
# have.
echo "=== clean clone of $BRANCH (tracked files only, like a CI checkout) ==="
rm -rf "$WORK"
git clone -q --branch "$BRANCH" "$REPO" "$WORK" || exit 1
git -C "$WORK" fetch -q "$REPO" main:refs/remotes/origin/main 2>/dev/null
git -C "$WORK" rev-parse --verify -q refs/remotes/origin/main >/dev/null \
  || { echo "could not make origin/main resolvable in the clone" >&2; exit 1; }

echo "  tracked files: $(git -C "$WORK" ls-files | grep -c '')"
echo "  artifacts that must be ABSENT here (their absence IS the test):"
for f in .claude/roadmap-progress-markers.txt .git/hooks/pre-push; do
  if [ -e "$WORK/$f" ]; then
    echo "    !! $f is present — the clone is not clean, and this run proves less than it appears to"
  else
    echo "    ok  $f absent"
  fi
done

# --------------------------------------------------------------------------------------------
# The link check runs on the HOST rather than inside the act container, and it runs the
# SAME pinned binary CI runs -- so this is a cost decision (no container round-trip), not a
# capability workaround.
run_lychee() {
  . "$REPO/scripts/lib/lychee-pin.env"
  local lychee; lychee="$(/bin/bash "$REPO/scripts/lib/ensure-lychee.sh")"
  ( cd "$WORK" && "$lychee" $LYCHEE_ARGS_COMMON "$LYCHEE_TARGET" "$LYCHEE_TARGET_HIDDEN" ) 2>&1 | tail -3
}

echo "=== act: the real workflow, as uid 1000 rather than root ==="
( cd "$WORK" && act pull_request -j validate \
    -P ubuntu-latest=catthehacker/ubuntu:act-latest \
    --container-options "--user 1000" ) > "$OUT" 2>&1
rc=$?

echo "=== result (act exit=$rc) ==="
grep -E '(✅|❌)[[:space:]]+(Success|Failure)' "$OUT" | tail -12
echo "  --- test tallies ---"
grep -oE '[0-9]+ (failed|passed|skipped)' "$OUT" | tail -4 | sed 's/^/  /'
echo "  --- link check (host-native; skips a container round-trip for a pinned binary act would run anyway) ---"
run_lychee | sed 's/^/  /'
echo "  full log: $OUT"

# `Lint markdown` carries `continue-on-error: true` in the workflow, so it fails on real CI too
# and does not fail the job. act reports it as a step failure regardless. Said here so a reader
# does not chase it.
echo "  note: a 'Lint markdown' failure is expected — that step is continue-on-error upstream."
exit "$rc"
