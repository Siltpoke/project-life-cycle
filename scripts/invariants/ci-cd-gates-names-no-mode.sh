#!/usr/bin/env bash
# Invariant: references/ci-cd-gates.md stays silent about `detailed` / the mode mechanism.
#
# WHY THIS EXISTS. a byte-freezing guard's first arm froze the whole references/ subtree, which meant
# this file could not be edited at all -- and the file documents CI and billing fallbacks, nothing
# about `mode`. It was removed from .claude/mode-frozen-set.txt on 2026-08-31 on the precedent
# close-gate.md set, and that removal REST ON A PREMISE: that the file has nothing to do with
# `detailed`. This guard asserts the premise instead of leaving it as a sentence in a comment.
#
# That is the narrow form of what the frozen-set file itself calls the general fix -- "pin the
# registration instead of the bytes" -- applied to one file. If someone later documents
# mode-relevant behaviour here, the exclusion stops being true, and this reds rather than the edit
# passing silently because arm 1 no longer looks.
#
# WHAT IT MATCHES, and why not the bare English word "mode". `mode` appears innocently in prose
# ("dormant mode", "manual mode") and banning it would red an honest edit -- a guard that cries wolf
# gets disabled, which is worse than no guard. It matches the tokens that are specific to PLC's mode
# MECHANISM: the preset name `detailed`, the frozen-set file, references/mode.md, and `presets.`.
#
# Verdicts: 0 pass, 1 the premise no longer holds, 3 could not run.

set -uo pipefail

NAME="ci-cd-gates-names-no-mode"
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
TARGET="$ROOT/skills/project-lifecycle/references/ci-cd-gates.md"
FROZEN="$ROOT/.claude/mode-frozen-set.txt"

[ -f "$TARGET" ] || { printf 'COULD-NOT-RUN %s: %s missing\n' "$NAME" "$TARGET" >&2; exit 3; }
[ -f "$FROZEN" ] || { printf 'COULD-NOT-RUN %s: %s missing\n' "$NAME" "$FROZEN" >&2; exit 3; }

# The guard only applies while the file is OUT of the frozen set. If someone puts it back, arm 1
# governs again and this check would be redundant rather than wrong -- say so instead of pretending.
if grep -qx 'skills/project-lifecycle/references/ci-cd-gates.md' "$FROZEN"; then
  printf 'PASS %s: ci-cd-gates.md is back inside the frozen set, so arm 1 governs it and this narrower check is not needed.\n' "$NAME"
  exit 0
fi

MECHANISM_RE='\bdetailed\b|mode-frozen-set|references/mode\.md|presets\.'

hits="$(grep -nEc "$MECHANISM_RE" "$TARGET" || true)"
if [ "${hits:-0}" -gt 0 ]; then
  printf 'FAIL %s: ci-cd-gates.md now names PLC'"'"'s mode mechanism on %s line(s):\n' "$NAME" "$hits" >&2
  grep -nE "$MECHANISM_RE" "$TARGET" | head -5 >&2
  printf '  -> this file was removed from .claude/mode-frozen-set.txt on the premise that it says\n' >&2
  printf '     nothing about `detailed`. That premise no longer holds. Either take the mode-relevant\n' >&2
  printf '     prose back out, or put the file back in the frozen set and delete this guard.\n' >&2
  exit 1
fi

printf 'PASS %s: ci-cd-gates.md names nothing from PLC'"'"'s mode mechanism (0 hits for %s), so its exclusion from the frozen set still holds. Scope: this asserts the EXCLUSION'"'"'s premise — it says nothing about the rest of the file'"'"'s correctness.\n' "$NAME" "$MECHANISM_RE"
