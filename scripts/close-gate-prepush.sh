#!/usr/bin/env bash
# close-gate-prepush.sh — the pre-push wrap-up check, called by the LOCAL .git/hooks/pre-push
# (wired by scripts/install-close-gate-hook.sh, which appends a one-line call to this file so
# the existing local pre-push hook above it stays untouched).
#
# On a feat/phase-* branch: run the phase's close-gate; a failing gate exits non-zero and the
# calling hook blocks the push. Any other branch pushes freely (WIP-branch granularity — the
# gate is a phase-close gate, not a per-commit gate).
#
# This message names no bypass on purpose — a guard must not ship its own escape hatch (see the
# local hook's header). If a check is wrong, edit scripts/close-gate.sh; reading it is the
# decision, a one-liner in an error message is a trap for a blocked agent.
set -u

branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
case "$branch" in
  feat/phase-*)
    phase="$(printf '%s' "$branch" | sed -E 's#^feat/phase-([0-9]+(\.[0-9]+)*).*#\1#')"
    if [ -x scripts/close-gate.sh ]; then
      echo "pre-push: running close-gate phase $phase …" >&2
      if ! bash scripts/close-gate.sh phase "$phase" >&2; then
        echo "pre-push: close-gate FAILED — push blocked. Fix the ✗ rows above." >&2
        exit 1
      fi
    else
      echo "pre-push: scripts/close-gate.sh missing/not executable — skipping wrap-up gate" >&2
    fi
    ;;
esac
exit 0
