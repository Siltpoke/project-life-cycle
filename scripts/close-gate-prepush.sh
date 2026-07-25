#!/usr/bin/env bash
# close-gate-prepush.sh — the pre-push wrap-up check, called by the LOCAL .git/hooks/pre-push
# (wired by scripts/install-close-gate-hook.sh, which appends a one-line call to this file so
# the existing local pre-push hook above it stays untouched).
#
# On a feat/phase-* branch: run the TASK-level close-gate; a failing gate exits non-zero
# and the calling hook blocks the push. `task` gates the per-commit subset (product-tree change +
# this task's journal FACT + fresh test-evidence + invariants), so a phase's first completed task
# is pushable the moment it exists — push-immediate, reconciled with the un-bypassable gate that
# used to demand phase-close artifacts (CHANGELOG / spec / plan / ROADMAP) on commit one. The
# heavier `phase` gate is the PRE-MERGE gate: run `bash scripts/close-gate.sh phase <id>` (or
# `make phase-done`) before opening/merging the PR — SKILL.md's Definition of Done requires its
# output pasted, and the merge itself is human-gated. Any other branch pushes freely.
#
# This message names no bypass on purpose — a guard must not ship its own escape hatch (see the
# local hook's header). If a check is wrong, edit scripts/close-gate.sh; reading it is the
# decision, a one-liner in an error message is a trap for a blocked agent.
set -u

branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
case "$branch" in
  feat/phase-*)
    # Phase token = the segment right after 'feat/phase-' up to the next '-'.
    # `[^-]+` captures any shape (1.2, X.Y, X.Ya, SS) — an earlier numeric-only
    # or dotted-numeric regex truncated letter-suffixed labels (X.Ya → X.Y).
    phase="$(printf '%s' "$branch" | sed -E 's#^feat/phase-([^-]+)-.*#\1#')"
    if [ -x scripts/close-gate.sh ]; then
      echo "pre-push: running close-gate task $phase …" >&2
      if ! bash scripts/close-gate.sh task "$phase" >&2; then
        echo "pre-push: close-gate (task) FAILED — push blocked. Fix the ✗ rows above." >&2
        echo "pre-push: this is the per-commit gate; phase-close artifacts are checked by 'phase' at merge." >&2
        exit 1
      fi
    else
      echo "pre-push: scripts/close-gate.sh missing/not executable — skipping wrap-up gate" >&2
    fi
    ;;
esac
exit 0
