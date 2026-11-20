#!/usr/bin/env bash
# Invariant `test-weakening-guard` (close-gate check #8 family): the branch did not quietly
# WEAKEN the test suite. It is the mirror of `growth-declares-a-deletion` -- that one makes a GROWTH
# declare a deletion; this one makes a SHRINK of the test surface declare a reason.
#
# WHAT IS COUNTED, and why it is NOT assert lines. The count is the number of TEST FUNCTIONS
# (`^\s*def test_`) across all test files at HEAD vs the merge-base. `growth-declares-a-deletion`
# carries a measured warning against counting lines -- "a line counter ... reds on a pure rewording,
# which is noise rather than growth". Counting `assert` statements has exactly that failure:
# parametrizing a test, moving an assert to a helper, or merging two asserts all legitimately change
# the assert-line count. A test FUNCTION is a discrete unit (like the file-paths that invariant
# counts): renaming or refactoring within a test does not change the count; DELETING a test does.
# The honest boundary: an assertion gutted inside a SURVIVING test is not caught here -- that stays
# the human UNVERIFIED-vs-VERIFIED call (references/prove.md).
#
# RED when the net count DROPS below the merge-base, UNLESS this branch's journal carries a
# `SKIP: test-weakening -- <reason>` line (in git, attributable by commit). No drop, or growth,
# passes with no declaration. Never warn-only. A read that cannot run (no merge base, a listing that
# failed) is CANNOT-RUN (exit 3), not a silent pass -- the growth guard's exact contract.
#
# Test seams (drive it without git): PLC_TESTWEAKEN_HEAD_COUNT / PLC_TESTWEAKEN_BASE_COUNT override
# the two counts; PLC_TESTWEAKEN_JOURNAL is the file scanned for the waiver.
#
# ENVELOPE: bash + git + grep/awk. No python3, no jq.

set -u

CANNOT_RUN_RC=3
cannot_run() { printf 'CANNOT-RUN[%s] %s\n' "$1" "$2" >&2; exit "$CANNOT_RUN_RC"; }
fail()       { printf 'FAIL[%s] %s\n' "$1" "$2" >&2; exit 1; }
pass()       { printf 'PASS test-weakening-guard: %s\n' "$1"; exit 0; }

# Root via parameter expansion, not `dirname` (a stripped PATH makes `dirname` resolve ROOT to `/`).
SELF_DIR="${BASH_SOURCE[0]%/*}"
[ "$SELF_DIR" = "${BASH_SOURCE[0]}" ] && SELF_DIR="."
ROOT="$(cd "$SELF_DIR/../.." && pwd)" || cannot_run "no-root" "cannot resolve repo root"
cd "$ROOT" || cannot_run "no-root" "cannot cd to $ROOT"

JOURNAL_DIR="docs/journal.d"

# --- the waiver: a SKIP: test-weakening line in this branch's journal fragments or commit range ----
waived() {
  local src=""
  if [ -n "${PLC_TESTWEAKEN_JOURNAL:-}" ]; then
    [ -f "$PLC_TESTWEAKEN_JOURNAL" ] && src="$(/bin/cat "$PLC_TESTWEAKEN_JOURNAL")"
  else
    command -v git >/dev/null 2>&1 || return 1
    local base="${BASE:-}"
    src="$(
      { git diff --name-only --diff-filter=AM "$base"...HEAD -- "$JOURNAL_DIR" 2>/dev/null
        git diff --name-only --diff-filter=AM -- "$JOURNAL_DIR" 2>/dev/null
        git ls-files --others --exclude-standard -- "$JOURNAL_DIR" 2>/dev/null
      } | /usr/bin/sort -u | while IFS= read -r _f; do
            [ -n "$_f" ] && [ -f "$_f" ] && /bin/cat "$_f"
          done
      git log --format=%B "$base"..HEAD 2>/dev/null || true
    )"
  fi
  printf '%s\n' "$src" \
    | /usr/bin/sed -e 's/^[[:space:]]*//' \
    | /usr/bin/grep -qE '^SKIP: test-weakening([[:space:]]|$|:|--)'
}

# --- count test functions at a revision --------------------------------------------------------
# List all paths at the rev (index for HEAD, tree for a sha), filter test files with the SAME
# path-aware ERE on both sides, then count `def test_` lines read from git objects.
count_at() {  # $1 = HEAD | <sha>   -> prints integer, returns 1 if the listing failed
  local rev="$1" paths f total n
  if [ "$rev" = "HEAD" ]; then
    paths="$(git -c core.quotePath=off ls-files)" || return 1
  else
    paths="$(git -c core.quotePath=off ls-tree -r --name-only "$rev")" || return 1
  fi
  [ -n "$paths" ] || return 1
  paths="$(printf '%s\n' "$paths" | /usr/bin/grep -E '(^|/)(test_[^/]*|[^/]*_test)\.py$' || true)"
  total=0
  if [ -n "$paths" ]; then
    while IFS= read -r f; do
      [ -n "$f" ] || continue
      if [ "$rev" = "HEAD" ]; then
        n="$(git show ":$f" 2>/dev/null | /usr/bin/grep -cE '^[[:space:]]*def test_' || true)"
      else
        n="$(git show "$rev:$f" 2>/dev/null | /usr/bin/grep -cE '^[[:space:]]*def test_' || true)"
      fi
      total=$((total + n))
    done <<EOF
$paths
EOF
  fi
  printf '%s' "$total"
}

# --- resolve the two counts (seams win) --------------------------------------------------------
if [ -n "${PLC_TESTWEAKEN_HEAD_COUNT:-}" ] && [ -n "${PLC_TESTWEAKEN_BASE_COUNT:-}" ]; then
  NOW="$PLC_TESTWEAKEN_HEAD_COUNT"
  WAS="$PLC_TESTWEAKEN_BASE_COUNT"
  BASE="seam"
else
  command -v git >/dev/null 2>&1 || cannot_run "no-git" "git is not on PATH"
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || cannot_run "not-a-worktree" "$ROOT is not inside a work tree"
  BASE="$(git merge-base origin/HEAD HEAD 2>/dev/null || git merge-base origin/main HEAD 2>/dev/null || true)"
  [ -n "$BASE" ] || cannot_run "no-merge-base" "cannot resolve a merge base against origin/HEAD or origin/main"
  git cat-file -e "$BASE^{commit}" 2>/dev/null || cannot_run "bad-merge-base" "$BASE is not a commit"
  NOW="$(count_at HEAD)" || cannot_run "head-listing-failed" "could not list files at HEAD"
  WAS="$(count_at "$BASE")" || cannot_run "base-listing-failed" "could not list files at $BASE"
  # This repo always has test functions; both sides zero means the read matched nothing -> broken.
  if [ "$NOW" = "0" ] && [ "$WAS" = "0" ]; then
    cannot_run "no-test-files" "counted zero test functions on both sides -- the path filter matched nothing"
  fi
fi

case "$NOW" in ''|*[!0-9]*) cannot_run "unreadable-head" "head count is not a number: '$NOW'" ;; esac
case "$WAS" in ''|*[!0-9]*) cannot_run "unreadable-base" "base count is not a number: '$WAS'" ;; esac

# --- compare -----------------------------------------------------------------------------------
if [ "$NOW" -ge "$WAS" ]; then
  pass "test-function count did not drop ($WAS -> $NOW; base ${BASE})"
fi

if waived; then
  pass "test-function count dropped ($WAS -> $NOW) but a 'SKIP: test-weakening' waiver is recorded"
fi

fail "weakened" "test-function count dropped from $WAS to $NOW across all test files (base ${BASE}); a test was deleted or skipped-by-removal. Restore it, or write a 'SKIP: test-weakening -- <reason>' line in this branch's journal if the drop is intended (e.g. a merged/obsolete test)."
