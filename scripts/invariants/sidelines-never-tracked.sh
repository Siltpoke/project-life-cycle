#!/usr/bin/env bash
# Invariant: the side-discovery queue is never git-tracked -- at the path actually CONFIGURED,
# not only at the one hard-coded in .gitignore.
#
# WHY. The queue is PER-PHASE working state (it used to say "per-branch", and
# nothing read a branch name -- the file belonged to the directory, so the previous phase's drained
# queue satisfied the next phase's close): lines move from `untriaged` to a landing while a phase
# runs, and the phase's OUTCOME -- not the queue -- is what becomes permanent, written into the
# journal at close. This repository's own rule is that documents record moments and never states, so
# a mutable queue has no business in history. Committing one would also put a half-drained list into
# every adopter's clone, where it means nothing.
#
# SHAPED FROM scripts/invariants/tasklist-never-tracked.sh, deliberately, including three of its
# measured lessons rather than a fresh take on the same problem:
#
#   [1] TRACKED IS TESTED BEFORE IGNORED. An ignore rule has no effect on a path already in the
#       index, so if the ignore test ran first a committed queue would produce a red whose stated
#       reason was "the path is not ignored" and whose remedy was "edit .gitignore" -- a TRUE
#       FAILURE WITH A FALSE REASON. `git check-ignore` will even report such a path as "not
#       ignored" while the rule sits right there.
#   [2] A CONFIGURED VALUE THAT IS NOT A PATH IS REFUSED FAIL-CLOSED. `PLC_SIDELINES_FILE='*'`
#       would make `git ls-files --error-unmatch -- '*'` match the whole index and report "a
#       sidelines artifact is git-tracked: [*]" -- non-zero, so safe, and again a true failure with
#       a false reason. The work-tree root `.` has the same shape.
#   [3] THE ASSERTION IS `git ls-files`, NOT FILE EXISTENCE. A gitignored file simply does not exist
#       in another checkout -- this repository has measured a gitignored path being invisible from
#       inside a worktree while the same command exited 0 in both places. Existence answers a
#       different question than tracking, and only tracking is what this check is about.
#
# WHAT IT DOES NOT DO. It says nothing about the queue's CONTENTS -- whether the grammar is
# respected, whether anything is still `untriaged`, whether the drain happened. Those are the close
# gate's `sidelines` row, and conflating them here would give one red two meanings.
#
# Envelope: bash + git only. No python3, no jq (CLAUDE.md).

set -uo pipefail

NAME="sidelines-never-tracked"

pass() { printf 'PASS %s: %s\n' "$NAME" "$1"; exit 0; }
fail() { printf 'FAIL %s: %s\n' "$NAME" "$1"; exit 1; }
# Third verdict: the CHECK could not run, not the repo is wrong. close-gate reads exit STATUS only,
# so 1 and 3 both block -- the fail-closed behaviour a check that could not run must have. What 3
# buys is that a direct caller, CI, or a test can tell the two apart.
CANNOT_RUN_RC=3
cannot_run() { printf 'FAIL %s: COULD NOT RUN -- %s\n' "$NAME" "$1"; exit "$CANNOT_RUN_RC"; }

REPO_ROOT="${1:-$(git rev-parse --show-toplevel 2>/dev/null || true)}"
[ -n "$REPO_ROOT" ] || cannot_run "not inside a git work tree (git rev-parse --show-toplevel failed)"
REPO_ROOT="${REPO_ROOT%/}"
cd "$REPO_ROOT" 2>/dev/null || cannot_run "cannot enter repo root: $REPO_ROOT"

DEFAULT_REL=".claude/sidelines.md"
ART_REL="${PLC_SIDELINES_FILE:-$DEFAULT_REL}"

# Normalise an absolute override down to a repo-relative path. An override pointing OUTSIDE the
# repository cannot be tracked by this repository at all, so it is reported as out of scope rather
# than silently passing as if it had been checked -- "nothing to check" and "checked and clean" must
# not print the same line.
CHECK_REL="$ART_REL"
OUT_OF_SCOPE=""
case "$ART_REL" in
  /*)
    case "$ART_REL" in
      "$REPO_ROOT"/*) CHECK_REL="${ART_REL#"$REPO_ROOT"/}" ;;
      # This used to `pass` and EXIT here, which made the claim "the family sweep runs in
      # addition, always" false -- an override pointing outside the repository skipped every check
      # below, including the per-phase family that has nothing to do with the override. Found by an
      # independent reviewer. The override is still out of scope (no path here can track it), but
      # the default path and the family are still this repository's business, so the run continues
      # and the out-of-scope fact is reported in the verdict instead of replacing it.
      *) OUT_OF_SCOPE="$ART_REL"; CHECK_REL="$DEFAULT_REL" ;;
    esac
    ;;
esac

# Lesson [2]: a configured value that is not a path is refused before it reaches any scan.
case "$CHECK_REL" in
  '.' )
    fail "PLC_SIDELINES_FILE ('$ART_REL') resolves to the work-tree root itself, not to a queue file
  -> this is a configuration error, not a tracked artifact. Point it at a file."
    ;;
  *[*?\[\]]* | :* )
    fail "PLC_SIDELINES_FILE ('$ART_REL') contains a glob or magic-pathspec character, so it is not a path this check can resolve
  -> refusing to certify it (fail closed). A pattern here means the queue is not where anyone thinks
     it is, and \`git ls-files -- '*'\` would match the whole index."
    ;;
esac

# Both the configured path and the default: an override does not stop the default location from
# being a place a queue can accidentally land.
CANDIDATES="$CHECK_REL
$DEFAULT_REL"

# The queue became ONE FILE PER PHASE, under a directory, so a two-path candidate list can no
# longer see it. Measured before this sweep existed: with `.claude/sidelines/zzfake.md` in the index,
# this script printed `PASS ... no side-discovery queue is tracked` and exited 0.
#
# NO PATTERN IS EVER HANDED TO GIT. The index is queried under a LITERAL directory and the returned
# literal names are filtered here in the shell; `git check-ignore` is then handed each exact path.
# That keeps the fail-closed refusal above (a glob in a configured value would match the whole
# index) intact rather than widening it for convenience.
FAMILY_DIR=".claude/sidelines"

# A path that exists but is not a directory would make `find` yield nothing, i.e. a sweep that
# examines zero files and prints the same line as a clean one.
# `-L` is tested FIRST and on its own: a symlink to a directory satisfies `-d`, so the original
# `[ -e ] && [ ! -d ]` let a symlinked family directory through and the sweep then examined nothing
# (measured by an independent reviewer with a tracked symlink). A symlink here is refused whatever
# it points at -- the queue family must be a real directory in this work tree.
if [ -L "$FAMILY_DIR" ] || { [ -e "$FAMILY_DIR" ] && [ ! -d "$FAMILY_DIR" ]; }; then
  fail "$FAMILY_DIR is a symlink or is not a directory, so the per-phase queue family cannot live there
  -> every queue path derived from the manifest's {PHASE} template resolves under it. A file or a
     symlink here means no queue can be written and this sweep would examine nothing while printing
     the same line as a clean run."
fi

# --- 1. TRACKED (lesson [1]: this test comes first) -----------------------------------------
tracked=""
while IFS= read -r p; do
  [ -n "$p" ] || continue
  case "$tracked" in *"[$p]"*) continue ;; esac   # de-duplicate: the configured path is often the default
  if git ls-files --error-unmatch -- "$p" >/dev/null 2>&1; then
    tracked="$tracked[$p]"
  fi
done <<EOF
$CANDIDATES
EOF

# The family sweep, DEPTH-BLIND on purpose. A basename grammar would miss a tracked
# `.claude/sidelines/x/y.md`, and a tracked file anywhere under the queue directory is exactly what
# this invariant exists to refuse -- the directory holds nothing but gitignored working state.
# FAIL CLOSED WHEN THE INDEX CANNOT BE READ. The first version read this through a process
# substitution (`done < <(git ls-files … 2>/dev/null)`), which discards git's exit status -- so a
# broken index looked exactly like "nothing tracked". An independent reviewer measured that: with a
# family file tracked and `.git/index` truncated to 40 bytes, this script printed
# `PASS … no side-discovery queue is tracked` and exited 0.
#
# THE REVIEWER'S SUGGESTED FIX DOES NOT WORK, and that was measured rather than assumed. Checking
# the exit status catches nothing here: with the index truncated to 40 bytes,
# `git ls-files -- .claude/` exits **0** with **zero** lines and an EMPTY stderr. So the detector
# cannot be the exit code. Two changes instead:
#   [1] no pathspec at all -- the whole index is read and the family is filtered in shell, which
#       also makes "no pattern ever reaches git" literal rather than nearly true;
#   [2] a corrupt-index SANITY CHECK -- an index reporting zero entries while HEAD's tree holds
#       files is not an empty repository, it is an unreadable index, and this check refuses to
#       certify that rather than passing it. A corrupt index is a known failure on synced folders.
_lstmp="$(mktemp 2>/dev/null)" || cannot_run "cannot create a temp file to read the index"
if ! git ls-files -z > "$_lstmp" 2>/dev/null; then
  rm -f "$_lstmp"
  cannot_run "\`git ls-files\` failed, so whether a queue is tracked is UNKNOWN -- refusing to certify it clean (a broken or locked index must not read as an empty one)"
fi
_idx_n="$(tr '\0' '\n' < "$_lstmp" | grep -c . || true)"
case "$_idx_n" in ''|*[!0-9]*) _idx_n=0 ;; esac
if [ "$_idx_n" -eq 0 ]; then
  _head_n="$(git ls-tree -r --name-only HEAD 2>/dev/null | grep -c . || true)"
  case "$_head_n" in ''|*[!0-9]*) _head_n=0 ;; esac
  if [ "$_head_n" -gt 0 ]; then
    rm -f "$_lstmp"
    cannot_run "the index reports ZERO tracked files while HEAD's tree holds $_head_n -- the index is unreadable or truncated, not empty. Whether a queue is tracked is UNKNOWN, so this check refuses to certify it (measured: a 40-byte index makes \`git ls-files\` exit 0 with no output and no error)"
  fi
fi
while IFS= read -r -d '' p; do
  [ -n "$p" ] || continue
  # THE ACTUAL SIGNAL OF A CORRUPT INDEX, measured rather than guessed. With `.git/index` truncated
  # to 40 bytes, `git ls-files -z` exits 0, writes nothing to stderr, and emits entries whose names
  # are `./` -- so neither the exit code nor the entry COUNT can tell the difference (the count was
  # 2, the same as HEAD's tree). What gives it away is that the names are not paths: git's index
  # holds files, so no legitimate entry is `.`, `./`, `..`, or ends in `/`. Refuse rather than
  # certify, because "the index is unreadable" and "nothing is tracked" must not print the same line.
  case "$p" in
    .|./|..|*/)
      rm -f "$_lstmp"
      cannot_run "the index yielded an entry that is not a file path ([$p]), so it is unreadable or truncated rather than empty -- whether a queue is tracked is UNKNOWN and this check refuses to certify it. Measured: a 40-byte .git/index makes \`git ls-files -z\` exit 0, print no error, and emit \`./\` entries"
      ;;
  esac
  case "$p" in
    # The exact path is included, not just paths under it: a tracked SYMLINK named
    # `.claude/sidelines` is itself the violation and the `/*` pattern never matched it.
    "$FAMILY_DIR"|"$FAMILY_DIR"/*) ;;
    *) continue ;;
  esac
  case "$tracked" in *"[$p]"*) continue ;; esac
  tracked="$tracked[$p]"
done < "$_lstmp"
rm -f "$_lstmp"

if [ -n "$tracked" ]; then
  fail "a side-discovery queue is git-tracked: $tracked
  -> TRACKING BEATS IGNORING. An ignore rule has no effect on a path already in the index, so this
     is NOT fixed by editing .gitignore and NOT fixed by adding a marker.
  -> Remove it with \`git rm --cached <path>\` and commit that removal. The queue is per-PHASE
     working state; what becomes permanent is the phase's OUTCOME, written into the journal at close
     (references/where-does-this-go.md)."
fi

# --- 2. IGNORED (only reachable once nothing is tracked) ------------------------------------
not_ignored=""
while IFS= read -r p; do
  [ -n "$p" ] || continue
  case "$not_ignored" in *"[$p]"*) continue ;; esac
  git check-ignore -q -- "$p" 2>/dev/null || not_ignored="$not_ignored[$p]"
done <<EOF
$CANDIDATES
EOF

# Every queue that EXISTS in the family must be ignored. Enumerated from the FILESYSTEM and
# not from the index, which is a stated departure from the shape first sketched for this check: an
# ignored untracked file is by definition absent from the index, so an index-only enumeration would
# examine nothing. Each exact path is handed to git; no pattern is.
family_n=0
if [ -d "$FAMILY_DIR" ]; then
  while IFS= read -r -d '' p; do
    [ -n "$p" ] || continue
    family_n=$((family_n + 1))
    case "$not_ignored" in *"[$p]"*) continue ;; esac
    git check-ignore -q -- "$p" 2>/dev/null || not_ignored="$not_ignored[$p]"
    # `-type l` as well as `-type f`: the close-gate row reads its queue with `[ -f ]`, which
    # FOLLOWS a symlink, so a symlinked queue is readable there while `find -type f` alone never
    # handed it to `check-ignore`. Measured by an independent reviewer: an unignored symlink inside
    # the family passed.
  done < <(find "$FAMILY_DIR" \( -type f -o -type l \) -print0 2>/dev/null)
fi

if [ -n "$not_ignored" ]; then
  fail "a side-discovery queue path is not ignored: $not_ignored
  -> Nothing is tracked, so this is the cheap half: add the path to .gitignore WITH THE REASON
     written beside it, the way the tasklist entry is documented there. Without the rule the queue
     shows up as an untracked file at every status and gets committed by the next \`git add -A\`."
fi

# De-duplicate for the message too. The scan loops skip repeats, but the pass line was printing
# `.claude/sidelines.md .claude/sidelines.md` whenever the configured path WAS the default -- the
# common case. A check whose output looks like it examined two things when it examined one is a
# small lie in exactly the place a reader goes for reassurance.
CHECKED="$(printf '%s\n' "$CANDIDATES" | grep -v '^$' | LC_ALL=C sort -u | tr '\n' ' ')"
pass "no side-discovery queue is tracked -- neither candidate path (${CHECKED% }) nor anything at any depth under $FAMILY_DIR/, where the index was read under a literal directory (and a git failure there is a refusal, not a pass) and $family_n existing queue file(s) or symlink(s) were each handed to git check-ignore by exact path -- and every one of them is ignored. Tracking is tested BEFORE ignoring, so a red here can never send the reader to .gitignore for an index entry${OUT_OF_SCOPE:+. NOTE: PLC_SIDELINES_FILE (\'$OUT_OF_SCOPE\') points OUTSIDE this repository, so that path itself was not verified -- no path here can track it -- while the default path and the whole family were}"
