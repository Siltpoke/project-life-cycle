#!/usr/bin/env bash
# Invariant: no iCloud " 2" conflict copies anywhere in this working copy.
#
# In a checkout that lives in an iCloud-synced folder, iCloud syncs `.git/` internals and working
# files alike and spawns ` 2` / ` 3` duplicates. They can corrupt refs (a `refs/heads/main 2` can
# wedge `git fetch` and make a merged PR read as unmerged), and a stale duplicate of a document
# silently shadows the real one when someone opens the wrong file.
#
# **Scanning `git ls-files` -- TRACKED FILES ONLY -- is not enough.** Conflict copies inside gitignored
# directories -- a copy of an append-only ledger, a journal archive -- would be invisible to it:
# `git ls-files` reports nothing about ignored or untracked paths, and neither does
# grepping `git status --porcelain`, for the same reason.
#
# So the scan is over the WORKING COPY, `.git/` included, tracked or not:
#
#   - tracked copies are a FAIL (they get committed and shared);
#   - untracked and ignored ones are a FAIL too, because they are the ones that shadow real
#     documents, and nothing else looks at them.
#
# Cost, stated rather than discovered later: a push can be blocked by junk that is not in git.
# That is deliberate — the remedy is one `rm` and the message prints the paths.
# A filename that legitimately ends in a space plus a digit must
# be added to EXEMPT below with a written reason; the list is a literal, never a pattern, for the
# same reason the backlog's exemption table is.
#
# jq-only envelope: no python3 here or in anything it calls.

set -uo pipefail

NAME="no-icloud-conflict-copies"

# One line per exempt path, relative to the repo root. A written-down literal, never a pattern —
# a pattern is a list that can quietly grow until nothing is left to check.
#
# Empty today. Nothing in this repo legitimately carries the ` <digit>` shape.
EXEMPT=""

# The ONE directory pruned rather than exempted by name, with its reason: `__pycache__` is
# regenerated build output that carries no information, and iCloud re-spawns copies there on every
# test run. Left in, this guard would be permanently red for zero risk — a gate that blocks every
# push teaches people to ignore the guard, which
# costs more than the copies do. A `.pyc` duplicate cannot shadow a document or corrupt a ref.
#
# **Singular, deliberately.** It interpolates into ONE
# `-name`, so the obvious way to add a second directory — `"__pycache__ node_modules"` — yields
# `-name '__pycache__ node_modules'`, which matches nothing: pruning would silently stop entirely
# and the guard would go permanently red on every `.pyc` copy, i.e. exactly the failure the
# paragraph above exists to prevent. A plural name invited that edit.
PRUNE_DIR="__pycache__"

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || printf '.')"
cd "$ROOT" || { printf 'FAIL %s: cannot enter the repo root\n' "$NAME"; exit 1; }

# The working copy is not the only tree to scan, and in a LINKED WORKTREE it contains no
# git internals at all: `.git` there is a ~108-byte file pointing elsewhere, so `find .` walks past
# it. Without a second root, the same planted bad ref FAILs from the main checkout and PASSes
# from a linked worktree -- a common setup for running parallel sessions.
#
# `--git-common-dir` is the shared directory (the main repo's `.git`) rather than the per-worktree
# one, so refs, objects and the index are covered from anywhere. It is scanned as a SECOND root and
# only when it is not already inside `ROOT`, so the ordinary case walks it exactly once.
GITDIR="$(git rev-parse --git-common-dir 2>/dev/null || printf '')"
case "$GITDIR" in
  "") ;;                                   # not a git repo — ROOT alone is the whole story
  /*) ;;                                   # absolute: a linked worktree, outside ROOT
  *)  GITDIR="$ROOT/$GITDIR" ;;            # relative (`.git`): already under ROOT
esac
EXTRA_ROOT=""
case "$GITDIR" in
  "") ;;
  "$ROOT"/*) ;;                            # already covered by the ROOT walk
  *) [ -d "$GITDIR" ] && EXTRA_ROOT="$GITDIR" ;;
esac

HITS="$(mktemp)"; KEEP="$(mktemp)"
trap 'rm -f "$HITS" "$KEEP"' EXIT

# ` 2` … ` 9` immediately before an extension, or at the end of the name. The digit range starts at
# 2 because iCloud numbers copies from 2; a name ending in " 1" is not the shape. `find` rather than
# a shell glob: the copies hide several levels down (`.claude/.gate-runs/`, `docs/archive/journal/`)
# and glob expansion would miss them.
# The traversal's exit status is READ. `set -uo pipefail` deliberately omits `-e`, and
# the first version also threw stderr away, so a `find` that could not enter a directory produced a
# PARTIAL scan and the guard printed PASS. Measured: with a mode-000 directory holding `note 2.md`,
# bare `find` exits 1 and the guard exited 0 with a clean bill. Reachable without contriving
# anything here — a checkout inside a cloud-synced home directory can be denied to a hook process, and
# `.git/objects` entries disappear under a concurrent repack. A scan that did not finish must never
# be reported as a scan that found nothing.
ERRS="$(mktemp)"; trap 'rm -f "$HITS" "$KEEP" "$ERRS"' EXIT
find "$ROOT" ${EXTRA_ROOT:+"$EXTRA_ROOT"} -type d -name "$PRUNE_DIR" -prune -o \
     \( -name '* [2-9]' -o -name '* [2-9].*' \) -print 2>"$ERRS" \
  | sed "s|^$ROOT/||" | LC_ALL=C sort > "$HITS"
find_rc=${PIPESTATUS[0]}
if [ "${find_rc:-0}" -ne 0 ]; then
  printf 'FAIL %s: the scan did not complete (find exited %s) — a partial walk must not be\n' \
         "$NAME" "$find_rc"
  printf '%s: reported as "nothing found". What it could not read:\n' "$NAME"
  sed "s|^|  |" "$ERRS" | LC_ALL=C sort -u
  exit 1
fi

if [ -n "$EXEMPT" ]; then
  printf '%s\n' "$EXEMPT" | LC_ALL=C sort > "$KEEP"
  LC_ALL=C comm -23 "$HITS" "$KEEP" > "$HITS.tmp" && mv "$HITS.tmp" "$HITS"
fi

n="$(grep -c '' "$HITS")"
if [ "$n" -ne 0 ]; then
  printf 'FAIL %s: %s iCloud conflict copy/copies in the working copy:\n' "$NAME" "$n"
  # Say which ones are tracked. A tracked copy is the worse case (it gets shared); an untracked one
  # is the commoner case (it shadows a real file locally and nothing else looks for it) — and
  # before this guard was widened, only the first kind was ever reported.
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    # `:(literal)` — `$f` used to be passed as a pathspec, so glob metacharacters in a
    # filename were interpreted: with a tracked `ab 2.md` present, an untracked `a[b] 2.md` was
    # labelled `tracked`, because the character class matched the other file. Only the label lied,
    # never the hit count — but a label nobody can trust is worse than no label.
    if git ls-files --error-unmatch -- ":(literal)$f" >/dev/null 2>&1; then
      printf '  tracked    %s\n' "$f"
    else
      printf '  untracked  %s\n' "$f"
    fi
  done < "$HITS"
  printf '%s: verify each is a stale duplicate (compare it against the real file — an iCloud copy\n' "$NAME"
  printf '%s: normally has NO unique content), then delete it. Do not assume: check first.\n' "$NAME"
  exit 1
fi

# The PASS line names what was walked and stops there. The previous one said ".git included"
# unconditionally, which was false in a worktree, and it also says nothing about symlinked
# directories, which `find -P` does not follow (deliberate: a link can leave the repo entirely).
if [ -n "$EXTRA_ROOT" ]; then
  printf 'PASS %s: no iCloud conflict copies under %s or %s (tracked, untracked and ignored alike; symlinked directories are not followed)\n' \
         "$NAME" "$ROOT" "$EXTRA_ROOT"
else
  printf 'PASS %s: no iCloud conflict copies under %s, .git included (tracked, untracked and ignored alike; symlinked directories are not followed)\n' \
         "$NAME" "$ROOT"
fi
