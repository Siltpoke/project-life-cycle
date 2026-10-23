#!/usr/bin/env bash
# install-close-gate-hook.sh — chain the wrap-up close-gate into the LOCAL pre-push hook.
#
# Why a local chain and not core.hooksPath=.githooks:
# git honours exactly ONE hooks dir, so pointing core.hooksPath elsewhere silently disables
# whatever pre-push hook a clone already has. Instead we insert a three-line call to
# scripts/close-gate-prepush.sh into the existing local hook. Both gate scripts
# (close-gate.sh + close-gate-prepush.sh) are tracked + reviewable; only the WIRING is local.
# This installer is the tracked, idempotent, reviewable record of that wiring.
#
# ORDER: the chain goes immediately after the shebang, so it runs FIRST — before the rest of
# whatever hook was already there. It used to be inserted before the hook's final `exit 0`,
# which was wrong in a way that printed success: a hook whose body ends in `exec …` never
# reaches its own last line, so the chain became dead code while this script reported
# "✓ chained" and exited 0. Running first is also the only position from which the gate can
# actually block a push it disagrees with.
#
# WHAT THIS SCRIPT CAN AND CANNOT SAY: it never reads the body it inserts above. It therefore
# reports only what it observed — where the chain was placed — and makes no claim about what
# the rest of the hook is or whether that part still runs on a given push. For an adopter
# whose pre-push is a linter, a test runner or commitlint, any such claim would be false.
#
# Run once per clone:  bash scripts/install-close-gate-hook.sh
set -euo pipefail

MARK="# >>> close-gate wrap-up chain (scripts/install-close-gate-hook.sh) >>>"

# Ask git for the hooks directory instead of spelling `.git/hooks`. `--git-path hooks`
# honours core.hooksPath by itself, and a literal path is wrong in both directions: absent in
# a linked worktree (where it would fail open), and a false positive when core.hooksPath
# merely aliases the default dir.
git rev-parse --git-dir >/dev/null 2>&1 || { echo "✗ not a git repo"; exit 1; }

# Both paths are RESOLVED before comparison, never compared as strings. `--git-path hooks`
# may answer with an absolute path while `--git-common-dir` answers with a relative one, so
# a string compare calls the same directory two different things and refuses a repo that is
# perfectly fine. That false positive was first found in the sibling predicate
# (scripts/invariants/close-gate-wiring.sh) and reappeared here the moment this check was written the
# obvious way — caught by the fixture that sets core.hooksPath TO the default directory.
abspath() { ( cd "$(dirname "$1")" 2>/dev/null && printf '%s/%s\n' "$(pwd -P)" "$(basename "$1")" ) || printf '%s\n' "$1"; }
HOOKS_DIR="$(abspath "$(git rev-parse --git-path hooks)")"
DEFAULT_HOOKS_DIR="$(abspath "$(git rev-parse --git-common-dir)/hooks")"
HOOK="$HOOKS_DIR/pre-push"
DEFAULT_HOOK="$DEFAULT_HOOKS_DIR/pre-push"

if [ -f "$HOOK" ] && grep -qF "$MARK" "$HOOK"; then
  echo "✓ close-gate chain already installed in $HOOK — nothing to do"
  exit 0
fi

# EVERYTHING BELOW THIS POINT RUNS ONLY ON A HOOK THAT IS NOT YET WIRED. The two refusals
# are deliberately placed AFTER the idempotent early return above: an already
# wired install must never be re-judged, or re-running this script on a clone that was set up
# before those checks existed would flip from exit 0 to a non-zero refusal — an idempotence
# regression that the "the normal path is unchanged" wording would not have covered.

# Refuse when git will not run the hook we are about to write. `core.hooksPath`
# pointing elsewhere means the file below is written, reported with a check-mark, and never
# executed by git. Setting the key is not itself an error; writing into a directory git does
# not consult is.
if [ "$HOOKS_DIR" != "$DEFAULT_HOOKS_DIR" ]; then
  # If a chain was previously installed into the default directory, say THAT — it is the
  # more useful sentence and it is the state close-gate-wiring.sh's clause 1 exists to detect. Reaching this
  # branch means the earlier install is orphaned: git no longer runs that file.
  if [ -f "$DEFAULT_HOOK" ] && grep -qF "$MARK" "$DEFAULT_HOOK"; then
    cat >&2 <<EOF
✗ refusing: a close-gate chain is installed in '$DEFAULT_HOOK', but core.hooksPath points
  at '$HOOKS_DIR', so git does not run that file any more. The existing chain is orphaned.
  Either clear core.hooksPath, or wire the call to scripts/close-gate-prepush.sh into
  whatever manages '$HOOKS_DIR'.
EOF
  else
    cat >&2 <<EOF
✗ refusing: core.hooksPath points at '$HOOKS_DIR', not the repository's default hooks
  directory ('$DEFAULT_HOOKS_DIR'). Writing a hook there and reporting success would give
  you a file git never runs. Wire the chain through whatever manages that directory, or run
  \`/init-harness --refresh\`.
EOF
  fi
  exit 1
fi

# The three lines to inject. Kept trivial on purpose — all real logic lives in the tracked
# scripts/close-gate-prepush.sh, so there is no bash-in-a-string to escape here.
#
# `</dev/null`: git feeds the pre-push hook one `<local ref> <local sha> <remote ref>
# <remote sha>` line per ref on fd 0. Now that the chain runs FIRST, a gate that reads stdin
# would consume those lines and everything below it in the adopter's hook would silently see
# an empty stdin. The redirect costs nothing and removes the whole class.
#
# The failure notice says only what this script can observe. It must not name what the rest of
# the hook does — a linter, a test runner, a secret scanner, anything: this script never reads
# the body it inserts above, so any such claim would be false for someone.
L1="$MARK"
L2='if [ -x scripts/close-gate-prepush.sh ]; then scripts/close-gate-prepush.sh </dev/null || { echo "close-gate failed: the rest of this pre-push hook did not run on this attempt" >&2; exit 1; }; fi'
L3="# <<< close-gate wrap-up chain <<<"

# A FRESH CLONE HAS NO "REST OF THE HOOK", so the notice above would be false by
# construction there — the very thing the notice exists to avoid. Same line, no notice.
L2_FRESH='if [ -x scripts/close-gate-prepush.sh ]; then scripts/close-gate-prepush.sh </dev/null || exit 1; fi'

if [ ! -f "$HOOK" ]; then
  # No pre-existing hook (fresh clone) — create a minimal one that just runs the chain.
  mkdir -p "$HOOKS_DIR"
  printf '#!/bin/bash\nset -u\n\n%s\n%s\n%s\n\nexit 0\n' "$L1" "$L2_FRESH" "$L3" > "$HOOK"
  chmod +x "$HOOK"
  echo "✓ created $HOOK with the close-gate chain (no pre-existing pre-push hook found)"
  exit 0
fi

# Refuse a hook this script cannot safely insert into. The insertion below puts the
# chain on line 2, which is only correct if line 1 is a shebang naming a POSIX shell. A
# python or ruby hook would get three lines of shell spliced into its source.
FIRSTLINE="$(sed -n '1p' "$HOOK")"
case "$FIRSTLINE" in
  '#!'*/sh|'#!'*/bash|'#!'*/dash|'#!'*/zsh|\
  '#!'*/env\ sh|'#!'*/env\ bash|'#!'*/env\ dash|'#!'*/env\ zsh) ;;
  *)
    cat >&2 <<EOF
✗ refusing: $HOOK does not start with a POSIX-shell shebang.
  Its first line is: $FIRSTLINE
  The chain is inserted as shell immediately after line 1, which would splice shell into a
  hook written in another language. Wire the call to scripts/close-gate-prepush.sh into that
  hook yourself, or move it aside and re-run this script.
EOF
    exit 1
    ;;
esac

# Insert immediately after the shebang. The old search-for-the-last-`exit 0` approach is
# gone entirely, along with the `awk` that carried it: `awk -v` applies its own escape
# processing to the injected bytes, which made it the single escaping hazard in a script that
# otherwise injects three literal lines. `sed -n '1p'` + `printf` + `sed -n '2,$p'` has no such
# hazard and behaves the same on a hook with no trailing newline or with CRLF line endings.
tmp="$(mktemp)"
{
  sed -n '1p' "$HOOK"
  printf '\n%s\n%s\n%s\n\n' "$L1" "$L2" "$L3"
  sed -n '2,$p' "$HOOK"
} > "$tmp"
mv "$tmp" "$HOOK"
chmod +x "$HOOK"
echo "✓ chained close-gate into $HOOK — the chain is inserted immediately after the shebang, and the rest of the hook follows it"
