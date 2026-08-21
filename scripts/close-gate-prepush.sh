#!/usr/bin/env bash
# close-gate-prepush.sh — the pre-push wrap-up check, called by the LOCAL .git/hooks/pre-push
# (wired by scripts/install-close-gate-hook.sh, which INSERTS a call to this file immediately
# after the hook's shebang, so this gate runs before the rest of that hook rather than after
# it. It used to append below the hook's last `exit 0`, which a hook ending in `exec` never
# reaches.)
#
# On a feat/phase-* branch: run the TASK-level close-gate; a failing gate exits non-zero
# and the calling hook blocks the push. `task` gates the per-commit subset (product-tree change +
# this task's journal FACT + test-evidence unchanged since generated + invariants), so a phase's first completed task
# is pushable the moment it exists — push-immediate, reconciled with the un-bypassable gate that
# used to demand phase-close artifacts (CHANGELOG / spec / plan / ROADMAP) on commit one. The
# heavier `phase` gate is the PRE-MERGE gate: run `bash scripts/close-gate.sh phase <id>`
# before opening/merging the PR — SKILL.md's Definition of Done requires its
# output pasted, and the merge itself is human-gated.
#
# On ANY OTHER branch: the gate is triggered by the DIFF, not by the branch name.
# Exiting 0 here without printing anything would let a `chore/…` branch ship
# user-visible skill changes with no CHANGELOG entry while nothing
# objects. Such a branch runs `close-gate.sh diff` — the diff-triggered subset (CHANGELOG
# [Unreleased] + test-evidence fingerprint when the diff touches the manifest's declared
# product_paths, and the declared invariants always) — and the gate REPORTS what it ran and why
# anything was skipped. A branch whose diff touches no product path still exits 0, but never
# silently: a required check that is skipped by a filter is indistinguishable from one that
# passed, which is the failure mode this arm exists to remove.
#
# The three-way classification (well-formed phase branch · malformed phase branch · everything
# else) lives HERE and only here. It is deliberately NOT the shared branch/journal classifier
# approach: close-gate.sh takes its mode and phase as explicit CLI arguments and still parses
# no branch name at all.
#
# This message names no bypass on purpose — a guard must not ship its own escape hatch in its
# block message. If a check is wrong, edit scripts/close-gate.sh; reading it is the
# decision, a one-liner in an error message is a trap for a blocked agent.
set -u

# Invoke the gate in an ALREADY-DECIDED mode. This helper does not look at the branch name and
# does not classify anything — the classification is the `case` below, and keeping the two apart
# is what stops this growing into the shared classifier this design declines. Returns the gate's status;
# each caller prints its own mode-specific block message, because the fix differs per mode.
run_close_gate() {
  if [ ! -x scripts/close-gate.sh ]; then
    echo "pre-push: scripts/close-gate.sh missing/not executable — skipping wrap-up gate ($1)" >&2
    return 0
  fi
  echo "pre-push: running close-gate $* …" >&2
  /bin/bash scripts/close-gate.sh "$@" >&2
}

branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
# A malformed phase branch is rejected BY NAME, before any sed runs. A branch name is an
# INPUT this gate parses to decide what to check, not an artifact it is looking for — so an
# ambiguous one makes the sed substitution below not match at all, which passes the branch
# through UNCHANGED: 'phase' silently becomes the WHOLE branch name, and the gate goes on to
# look for a journal fragment named after that string, failing later with an unrelated message.
# Reject it here instead: it costs the pusher one `git branch -m` and is caught before any work
# runs.
#
# The accept pattern is `feat/phase-[!-]*-?*`, and each half of it is load-bearing:
#   `[!-]*` — the id must start with a NON-dash, because the sed below captures `([^-]+)`. A
#             plain "has a second dash" test (`feat/phase-*-*`) accepts `feat/phase--slug`,
#             whose sed does not match either — reproducing the exact pass-through this arm
#             exists to remove. The guard's domain must equal the parser's domain.
#   `?*`    — the slug must be non-empty. This is deliberately ONE NOTCH STRICTER than the
#             parser (`feat/phase-x1-` does parse to `x1`), because the shape printed below
#             promises `<slug>`: an advertised contract that is not the enforced one is a
#             defect in its own right.
#
# Strictness is cheap on the input side and expensive on the artifact side — contrast
# close-gate.sh's phase_journal(), which deliberately keeps the opposite (loose) strictness
# for journal FILENAMES, because those are artifacts the gate is looking for, not input it
# parses.
case "$branch" in
  feat/phase-*)
    case "$branch" in
      feat/phase-[!-]*-?*) ;;  # non-empty id AND non-empty slug — derive the phase token
      *)
        echo "pre-push: branch '$branch' does not match the required shape feat/phase-<id>-<slug>." >&2
        echo "pre-push: both segments must be non-empty — the id is what this gate parses to find the phase's artifacts, and the slug keeps it apart from the rest of the name." >&2
        case "$branch" in
          # A non-empty id with a missing/empty slug can be repaired by appending one; an empty
          # id cannot, so that case gets the shape rather than a rename that would still fail.
          feat/phase-[!-]*) echo "pre-push: fix with: git branch -m ${branch%-}-<slug>" >&2 ;;
          *)                echo "pre-push: fix with: git branch -m feat/phase-<id>-<slug>" >&2 ;;
        esac
        exit 1
        ;;
    esac
    # Phase token = the segment right after 'feat/phase-' up to the next '-'.
    # `[^-]+` captures any shape (1.2, X.Y, X.Ya, SS) — an earlier numeric-only
    # or dotted-numeric regex truncated letter-suffixed labels (X.Ya → X.Y).
    phase="$(printf '%s' "$branch" | sed -E 's#^feat/phase-([^-]+)-.*#\1#')"
    if ! run_close_gate task "$phase"; then
      echo "pre-push: close-gate (task) FAILED — push blocked. Fix the ✗ rows above." >&2
      echo "pre-push: this is the per-commit gate; phase-close artifacts are checked by 'phase' at merge." >&2
      exit 1
    fi
    ;;
  *)
    # Not a phase branch — no phase exists, so the spec / plan / journal / ROADMAP
    # rows have nothing to judge and the product-tree row has no phase to require it of. What
    # DOES apply is whatever the diff touches, plus the tree-level invariants. `diff` mode is
    # that subset; it takes no phase argument, which is the point — this arm hands the gate a
    # MODE, never a parsed branch name.
    if ! run_close_gate diff; then
      echo "pre-push: close-gate (diff) FAILED — push blocked. Fix the ✗ rows above." >&2
      # Deliberately does NOT name a cause. A diff-mode failure can come from the CHANGELOG or
      # test-evidence rows (which fire only when the diff touches the product tree) OR from a
      # declared invariant (which runs on every branch). Asserting the first would be a message
      # wider than its mechanism — so it points at the check-set
      # line, which reports what actually ran on THIS run.
      #
      # "The check-set line above lists …" was itself wider than its mechanism. close-gate.sh
      # can exit BEFORE printing any check-set line — the unresolvable-`origin/main` arm fails
      # closed on the very first thing it does, so the only output is that one ✗ row. Telling a
      # blocked pusher to read a line that is not on their screen sends them looking for a
      # missing gate instead of at the message they were given, so the sentence now covers both
      # paths that can reach it.
      echo "pre-push: this branch is gated by what its DIFF touches, not by its name. If a 'check-set' line was printed above, it lists exactly which checks ran and why anything was skipped; if the gate exited before reaching it (e.g. it could not resolve origin/main), the ✗ row above is the whole report." >&2
      exit 1
    fi
    ;;
esac
exit 0
