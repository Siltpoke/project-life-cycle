#!/usr/bin/env bash
# Invariant (the station-plan work): no CJK text in a tracked file that ships.
#
# WHY THIS EXISTS, and it is a measured gap rather than a precaution. The only thing enforcing
# this rule was `.git/hooks/pre-push` check #3 — which is NOT git-tracked and runs at
# PUSH. A phase that has not pushed yet is therefore green at every close-gate run while
# holding un-shippable bytes. That is not hypothetical: p36 wrote its format contract and all
# fifteen fixtures under `skills/` in Chinese across four tasks, passed the gate every time,
# and found out on the first push of the branch. Sixteen files.
#
# WHAT IT IS NOT. It is not a general leak check. It answers one question only, and it
# reads the tree rather than a push range, so it fires when the work is done rather
# than when it leaves the machine. Identifier and secret scanning is a separate concern
# and is not done here.
# This row answers one question — is there CJK in a tracked file that is not exempt — at the
# time the work is done rather than at the time it leaves the machine.
#
# THE EXEMPTIONS MIRROR THE HOOK, deliberately and not by coincidence:
#   README* / CHANGELOG.md / GUIDE*  the intentional Chinese docs and the language switcher.
#   private/                            a private working directory, if you keep one.
#   docs/                               the project's working record; it does not ship.
#   CLAUDE.md                           the root agent-instruction file; it does not ship either.
#
# The paths are anchored, so `docs-something/` and `skills/x/docs/` are still scanned.
# CLAUDE.md is anchored too, so `skills/x/CLAUDE.md` is still scanned -- only the root file is
# exempt.
#
# Envelope: bash + git + grep + perl. No python3 (CLAUDE.md). `grep -P` is not portable (BSD
# grep lacks it), so the codepoint test is perl, which ships with macOS and with every runner
# image used here.
set -euo pipefail

fail=0

command -v perl >/dev/null 2>&1 || {
  printf '✗ no-cjk-in-shipped-files: perl is required for the codepoint test and is not on PATH\n' >&2
  exit 1
}

# Tracked files only. An untracked file cannot reach the snapshot, and scanning the working
# tree would red on scratch files nobody is shipping.
files="$(git ls-files -- ':(exclude)docs/**' ':(exclude)private/**' \
                         ':(exclude)README*' ':(exclude)CHANGELOG.md' ':(exclude)GUIDE*' \
                         ':(exclude,top)CLAUDE.md')"

n_scanned=0
hits=""
while IFS= read -r f; do
  [ -n "$f" ] || continue
  [ -f "$f" ] || continue          # a path staged for deletion is not on disk
  n_scanned=$((n_scanned + 1))
  # EVERY matching line, not the first. Reporting one hit per file turns fixing this into
  # whack-a-mole: the first version of this guard did exactly that, and three further sites
  # surfaced one at a time as each earlier one was fixed. Capped at 20 lines per file so a
  # badly-scoped run cannot bury the summary.
  line="$(perl -CSD -ne 'if (/[\x{4e00}-\x{9fff}\x{3040}-\x{30ff}\x{ac00}-\x{d7af}]/) { print "$.: $_"; exit if ++$n >= 20 }' "$f" 2>/dev/null || true)"
  [ -n "$line" ] || continue
  while IFS= read -r one; do
    [ -n "$one" ] && hits="$hits$f:$one
"
  done <<INNER
$line
INNER
done <<EOF
$files
EOF

# An empty scan is reported, never passed silently: zero files scanned and zero hits are two
# different states, and this repo has seen the collapse of that distinction.
if [ "$n_scanned" -eq 0 ]; then
  printf '⊘ no-cjk-in-shipped-files: 0 tracked files in scope — nothing was checked, and that is stated rather than passed\n'
  exit 0
fi

if [ -n "$hits" ]; then
  printf '%s' "$hits" | while IFS= read -r h; do
    [ -n "$h" ] && printf '✗ CJK in a shipped tracked file: %s\n' "$h" >&2
  done
  fail=1
fi

if [ "$fail" -ne 0 ]; then
  printf '✗ no-cjk-in-shipped-files: FAILED — CJK is not allowed in shipped files outside the listed localized docs\n' >&2
  exit 1
fi
printf '✓ no-cjk-in-shipped-files (%s tracked file(s) scanned; docs/, private/, README*, CHANGELOG.md, GUIDE*, and the root CLAUDE.md are exempt by name)\n' "$n_scanned"
