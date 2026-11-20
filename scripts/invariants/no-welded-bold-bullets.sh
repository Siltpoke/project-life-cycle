#!/usr/bin/env bash
# Invariant: no welded bold bullet in SKILL.md.
#
# WHAT THIS ASSERTS: no line of skills/project-lifecycle/SKILL.md contains a `- **` bold-bullet
# opener glued onto the end of preceding text with no newline between them (the pattern
# `<non-space>- **`). A bullet written mid-line like `...prev sentence.- **Next bullet**` renders
# in markdown as part of the previous item, so the "Next bullet" stops being its own list entry --
# a stop-sign (Red Flag) silently dies as a standalone bullet while its text is still present.
#
# WHY IT EXISTS: the SKILL.md diet removes duplicate Red Flags by deleting bullet lines. Twice
# (phases skill-diet-cut3 + its fix) an edit dropped the newline before the surviving bullet after
# a removed block and welded two Red Flags onto a neighbour. The diet's measurement harness CANNOT
# see this: it grades a fixed golden set of behaviours, and the welded behaviours (TDD-horizontal-
# slicing, user-story-before-spec) are not in it. Both times the weld was caught only by a
# secondary, different-lineage reviewer. This check turns "hope a reviewer looks" into a free,
# deterministic gate guard that runs on every push and close.
#
# HONEST BOUNDARY (stated, not left to be discovered):
#   * It matches a welded BOLD bullet (`- **`) only. A welded PLAIN bullet (`...text.- next`) is
#     NOT caught -- the broad `<non-space>- ` pattern has 15 false positives on the real file
#     (`- [ ]` / `- [/]` / `- [none]` checkbox examples, hyphenated prose), so it is unusable as a
#     gate. `- **` has zero false positives on the current file and is the exact weld signature the
#     two incidents produced.
#   * Scope is SKILL.md, the always-loaded file where the diet operates and the stakes are highest.
#     It does not scan references/*.md.
#   * It proves a bullet is STRUCTURALLY standalone, never that the bullet's text is correct.
#
# ENVELOPE: bash + grep only (jq-only gate envelope; no python3, no jq, no bash-4 constructs).
# Exit 0 = clean, 1 = weld(s) found, 3 = CANNOT-RUN (file missing / unreadable) -- never a silent
# pass on a broken read.
set -euo pipefail

# Default target is the always-loaded skill file; an explicit path arg exists ONLY so the test
# suite can point the same logic at a fixture. The manifest/gate call passes no arg.
SKILL="${1:-skills/project-lifecycle/SKILL.md}"

[ -f "$SKILL" ] || { echo "CANNOT-RUN no-welded-bold-bullets: $SKILL not found"; exit 3; }
[ -r "$SKILL" ] || { echo "CANNOT-RUN no-welded-bold-bullets: $SKILL not readable"; exit 3; }

# `|| true` is load-bearing under `set -e`: grep exits 1 when it finds nothing (the clean case).
HITS="$(/usr/bin/grep -nE '[^[:space:]]- \*\*' "$SKILL" 2>/dev/null || true)"

if [ -n "$HITS" ]; then
  echo "FAIL no-welded-bold-bullets: welded bold bullet(s) in $SKILL -- a '- **' bullet is glued to the end of the"
  echo "previous line (no newline between), so markdown swallows it into that line. Insert a"
  echo "newline before each '- **':"
  echo "$HITS"
  exit 1
fi

echo "PASS no-welded-bold-bullets: no welded bold bullets in $SKILL"
exit 0
