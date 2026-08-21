#!/usr/bin/env bash
# Invariant: no machine-local hook state file is git-tracked, at ANY depth.
#
# The hooks keep throttle/re-arm stamps so they fire at most once per interval. Current builds
# write them under ~/.claude/plc-state/<repo-key>/ and never touch the worktree. An OLDER cached
# plugin build writes them to `<cwd>/.claude/...` instead -- and `cwd` is wherever the shell was
# standing, not the repo root.
#
# How that goes wrong: a stamp lands in `skills/project-lifecycle/hooks/.claude/` because a shell
# sat in that directory when a Stop hook fired. A `.gitignore` rule for exactly that filename,
# anchored to the repo root, does not match at that depth, so a `git add -A` tracks it into
# the product tree, where it ships to every adopter and rewrites itself on every run.
#
# `.gitignore` is unanchored (`**/`) for the three known names, which covers the known case. This is the
# backstop for the ones nobody has thought of: it asks the question by SHAPE -- is anything that
# looks like hook state tracked, anywhere -- rather than by an enumerated path list that can
# be wrong.
set -euo pipefail

# Names the hooks are known to write, matched at any depth.
PATTERNS='(^|/)\.claude/(\.close-gate-nudge-last|\.clear-nudge-last|\.gate-runs/)'

hits="$(git ls-files | grep -nE "$PATTERNS" || true)"

if [ -n "$hits" ]; then
  echo "FAIL no-hook-state-tracked: machine-local hook state is git-tracked"
  printf '%s\n' "$hits"
  echo "  -> these are per-machine throttle stamps, not deliverables. Untrack with"
  echo "     'git rm --cached <path>' and confirm .gitignore covers that DEPTH, not just the root."
  exit 1
fi

echo "ok no-hook-state-tracked: no hook state file is tracked at any depth"
