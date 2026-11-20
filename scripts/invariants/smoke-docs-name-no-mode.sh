#!/usr/bin/env bash
# Invariant: references/smoke-tracks.md and references/handoff-template.md stay silent about
# `detailed` / the mode mechanism.
#
# WHY THIS EXISTS. A byte-freezing guard's first arm froze the whole references/ subtree, so these
# two files could not be edited at all -- and they document smoke testing and the PR body, nothing
# about `mode`. They were removed from .claude/mode-frozen-set.txt, and that removal RESTS ON A
# PREMISE: that neither file has anything to do with `detailed`. This guard asserts the premise
# instead of leaving it as a sentence in a comment. Same shape as ci-cd-gates-names-no-mode.sh.
#
# WHAT IT MATCHES, and why not the bare English word "mode". smoke-tracks.md says "Failure mode" in
# a table header; banning the word would red an honest file. It matches the tokens specific to PLC's
# mode MECHANISM: the preset name `detailed`, the frozen-set file, references/mode.md, `presets.`.
#
# Verdicts: 0 pass, 1 the premise no longer holds, 3 could not run.

set -uo pipefail

NAME="smoke-docs-name-no-mode"
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
FROZEN="$ROOT/.claude/mode-frozen-set.txt"
TARGETS="skills/project-lifecycle/references/smoke-tracks.md skills/project-lifecycle/references/handoff-template.md"
MECHANISM_RE='\bdetailed\b|mode-frozen-set|references/mode\.md|presets\.'

[ -f "$FROZEN" ] || { printf 'COULD-NOT-RUN %s: %s missing\n' "$NAME" "$FROZEN" >&2; exit 3; }

rc=0
checked=0
for rel in $TARGETS; do
  f="$ROOT/$rel"
  [ -f "$f" ] || { printf 'COULD-NOT-RUN %s: %s missing\n' "$NAME" "$f" >&2; exit 3; }
  # While a file is back inside the frozen set, arm 1 governs it and this check is redundant there.
  if grep -qx "$rel" "$FROZEN"; then
    printf 'PASS %s: %s is back inside the frozen set, so arm 1 governs it.\n' "$NAME" "$rel"
    continue
  fi
  checked=$((checked + 1))
  hits="$(grep -cE "$MECHANISM_RE" "$f" || true)"
  if [ "${hits:-0}" -gt 0 ]; then
    printf 'FAIL %s: %s now names PLC'"'"'s mode mechanism on %s line(s):\n' "$NAME" "$rel" "$hits" >&2
    grep -nE "$MECHANISM_RE" "$f" | head -5 >&2
    printf '  -> this file was removed from .claude/mode-frozen-set.txt on the premise that it says\n' >&2
    printf '     nothing about `detailed`. Either take the mode-relevant prose back out, or put the\n' >&2
    printf '     file back in the frozen set.\n' >&2
    rc=1
  fi
done

[ "$rc" -eq 0 ] && printf 'PASS %s: %s file(s) checked, 0 hits for %s, so their exclusion from the frozen set still holds. Scope: this asserts the exclusion'"'"'s premise only.\n' "$NAME" "$checked" "$MECHANISM_RE"
exit "$rc"
