#!/usr/bin/env bash
# Invariant: BACKLOG.md's title may not claim a git fact the tree contradicts.
#
# WHY THIS EXISTS, and why it is not simply "delete the parenthetical".
#
# The title read `# Backlog (local-only — docs/ is gitignored)` for months after
# p39 made docs/ tracked. Both halves were false. It survived hand-corrections
# because it is not hand-written: `scripts/backlog-toc.sh` PRINTS it, so the next
# regeneration restores it. A correction therefore produces a diff that reads as
# a fix, reviews as a fix, merges -- and is silently undone. Someone can "fix" it
# repeatedly and every attempt looks successful.
#
# That is a different defect from the one p33 spent the day on. There the claim
# had merely outlived its mechanism: inert, wrong, waiting. Here a mechanism is
# ACTIVELY RESTORING the claim, which makes the usual remedy indistinguishable
# from success.
#
# So this guard does not ban the sentence. It requires it to be TRUE. A title that
# says docs/ is gitignored is checked against whether docs/ is actually gitignored;
# if the tree ever genuinely goes back to ignoring docs/, the sentence becomes
# legal again on its own, with nothing to remember.
#
# BOTH SOURCES ARE CHECKED, and that is the point rather than belt-and-braces:
# the file is the artifact a reader sees, the generator is what restores it. A
# guard reading only the file goes green on a tree whose generator would red it
# on the very next run -- which is precisely how this defect hid.
#
# SCOPE, stated rather than implied. This checks the TITLE only: line 1 of
# docs/BACKLOG.md, and the title printf in the generator. It says nothing about
# the rest of the header block, whose counts and next-free-id are DERIVED from
# the tree and so cannot go stale this way. It also does not police prose about
# the PAST -- "the tool used to be local-only" (on the generator's own
# line 450) is a true historical statement and stays legal.

set -uo pipefail

NAME="backlog-title-claims-only-what-is-true"
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
BACKLOG="$ROOT/docs/BACKLOG.md"
GENERATOR="$ROOT/scripts/backlog-toc.sh"

fail() { printf 'FAIL %s: %s\n' "$NAME" "$1" >&2; exit 1; }

[ -f "$BACKLOG" ] || fail "docs/BACKLOG.md not found at $BACKLOG"
[ -f "$GENERATOR" ] || fail "scripts/backlog-toc.sh not found at $GENERATOR"

# The claim, wherever it is asserted about the CURRENT state.
CLAIM_RE='gitignored|local-only'

title_from_file="$(head -1 "$BACKLOG")"
# The generator's title is the printf that emits a line starting with '# Backlog'.
title_from_generator="$(grep -m1 -E "printf '# Backlog" "$GENERATOR" || true)"

# Is docs/ actually ignored? Tracked files are the discriminator: git's ignore
# rules do not apply to tracked paths, so counting them answers the real question
# and does not depend on .gitignore's wording.
tracked_docs="$(git -C "$ROOT" ls-files docs/ 2>/dev/null | wc -l | tr -d ' ')"

# Every offending source is reported in ONE run. Reporting only the first would
# hand back a partial fix that looks complete: correct the file, re-run, and only
# then learn the generator still restores it -- which is the same trap in miniature.
offenders=()
for src in "file:$title_from_file" "generator:$title_from_generator"; do
  where="${src%%:*}"
  text="${src#*:}"
  if printf '%s' "$text" | grep -qE "$CLAIM_RE"; then
    [ "$tracked_docs" -gt 0 ] && offenders+=("$where")
  fi
done

if [ "${#offenders[@]}" -gt 0 ]; then
  fail "the BACKLOG title claims docs/ is gitignored or local-only in: ${offenders[*]} -- but git tracks $tracked_docs file(s) under docs/. Both must be fixed together: scripts/backlog-toc.sh reprints the title on every run, so editing docs/BACKLOG.md alone is undone by the next regeneration."
fi

printf 'PASS %s: the BACKLOG title asserts no git fact the tree contradicts (checked in docs/BACKLOG.md line 1 AND the generator printf; git tracks %s file(s) under docs/). Scope: title only — the header block below it is derived, and prose about the past is not policed.\n' "$NAME" "$tracked_docs"
