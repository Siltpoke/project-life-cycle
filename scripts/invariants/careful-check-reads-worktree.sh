#!/usr/bin/env bash
# Invariant `careful-check-reads-worktree`: the danger check sees UNCOMMITTED work,
# and it sees UNTRACKED files.
#
# BOTH HALVES ARE BEHAVIOURAL, not textual. Asserting on the shape of the command inside the script
# would pass on a script that computes the right command and then ignores it, and would fail on a
# refactor that reaches the same behaviour another way. So this builds two trees and asks what the
# shipped check actually reports.
#
#   half 1  the implementer's diff is NOT COMMITTED when the check runs. Reading a commit range
#           gives a permanently empty list -- a guard that never fires, which is worth
#           exactly as much as one that always fires.
#   half 2  `git ls-files` lists TRACKED files only. Without the untracked half, a brand-new
#           src/auth/new-login.ts sits in the changed-file list and misses the pathspec set: the
#           user marks src/auth/, the mechanism works as designed, and writing a new login file --
#           the shape most deserving of the upgrade -- is invisible.
#
# Verdicts: 0 pass, 1 the repository is wrong, 3 the check could not run.
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

CHECK=skills/project-lifecycle/hooks/plc-careful-check.sh
DATA=skills/project-lifecycle/references/careful-paths.md

[ -r "$CHECK" ] || { printf 'COULD NOT RUN: %s is not readable\n' "$CHECK" >&2; exit 3; }
[ -r "$DATA" ]  || { printf 'COULD NOT RUN: %s is not readable\n' "$DATA" >&2; exit 3; }
command -v git >/dev/null 2>&1 || { printf 'COULD NOT RUN: git is not on PATH\n' >&2; exit 3; }
command -v jq  >/dev/null 2>&1 || { printf 'COULD NOT RUN: jq is not on PATH\n' >&2; exit 3; }

# A GIT HOOK RUNS WITH GIT_DIR SET, AND GIT_DIR OVERRIDES `-C`.
#
# This is proved rather than guessed. With GIT_DIR exported -- exactly what
# git does for every hook process, including the pre-push hook that runs this gate -- a fixture
# doing `git init <tmp>` followed by `git -C <tmp> commit` writes the commit into THE REPOSITORY
# THE HOOK IS RUNNING FOR: the fixture's tree lands on that repository's checked-out branch, and
# every file already on that branch comes out as a deletion.
#
# It also defeats the obvious guard. `git -C <tmp> rev-parse --show-toplevel` still answers <tmp>,
# because the worktree follows the cwd while the commit follows GIT_DIR, so an assertion on the top
# level PASSES while the commit still goes to the wrong place -- a claim wider than its mechanism,
# inside the fix written for that class.
#
# Both halves are therefore needed: clear the environment, and assert on the GIT DIR, which is the
# thing that actually decides where a commit lands.
# Clear the WHOLE GIT_* family, not a list of six names. An enumerated list is a claim that git
# will never add another variable able to redirect a read or a write, and nothing announces the
# day that stops being true -- a claim wider than its mechanism. The python
# fixtures already filter by prefix (`not k.startswith("GIT_")`); this is parity with them.
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

setup() {
  local root="$1"
  git init -q "$root"

  # THE ASSERTION IS ON THE GIT DIR, not on the top level. See the GIT_DIR note above: a top-level
  # assertion passes while the commit still lands in the wrong repository, which is what the first
  # version of this guard did. The git dir is what decides where a commit goes, so it is what gets
  # checked. The `unset` above should already make this unreachable; it stays because a guard whose
  # only protection is another line's correctness is not a guard.
  local gd want
  gd="$(git -C "$root" rev-parse --absolute-git-dir 2>/dev/null || true)"
  want="$(cd "$root" && pwd -P)/.git"
  if [ "$gd" != "$want" ]; then
    printf 'COULD NOT RUN: fixture at %s resolves to git dir %s, not %s -- refusing to commit\n' \
      "$root" "${gd:-<none>}" "$want" >&2
    exit 3
  fi

  git -C "$root" config user.email t@example.invalid
  git -C "$root" config user.name t
  printf '# p\ncareful-paths: src/auth/\n' > "$root/CLAUDE.md"
  mkdir -p "$root/src/auth"
  printf 'old\n' > "$root/src/auth/session.ts"
  git -C "$root" add -A
  git -C "$root" commit -qm base
}

probe() { /bin/bash "$CHECK" --claude-md "$1/CLAUDE.md" --repo "$1" --data "$DATA"; }

# --- half 1: uncommitted modification -----------------------------------------------------------
setup "$tmp/a"
printf 'changed\n' > "$tmp/a/src/auth/session.ts"
[ -n "$(git -C "$tmp/a" status --porcelain)" ] || {
  printf 'COULD NOT RUN: the probe tree is not dirty, so half 1 would pass vacuously\n' >&2; exit 3; }
out_a="$(probe "$tmp/a")"
case "$out_a" in
  no-hit*) printf 'FAIL an UNCOMMITTED modification under a declared careful path was not seen -- the check is reading a commit range, and a commit range is empty at the moment this runs\n' >&2; exit 1 ;;
esac

# --- half 2: brand-new untracked file -----------------------------------------------------------
setup "$tmp/b"
printf 'brand new\n' > "$tmp/b/src/auth/new-login.ts"
out_b="$(probe "$tmp/b")"
case "$out_b" in
  *new-login.ts*) ;;
  *) printf 'FAIL a BRAND-NEW untracked file under a declared careful path was not seen -- writing a new login file is the shape most deserving of the upgrade\n' >&2; exit 1 ;;
esac

printf 'ok  the check sees uncommitted work and untracked files (%s / %s hit row(s))\n' \
  "$(printf '%s\n' "$out_a" | wc -l | tr -d ' ')" "$(printf '%s\n' "$out_b" | wc -l | tr -d ' ')"
