#!/usr/bin/env bash
# Emit the IDENTITY of every test row skipped because an author-local artifact is untracked.
#
# IDENTITY, NOT A COUNT. A total stays the same while one row is added and another removed, and
# "the number matched" is the exact shape of wrong-green this script exists to close. A rename
# turning this red is correct behaviour: the set really did change.
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

/usr/bin/grep -rn 'skipif' scripts/*.py | while IFS= read -r hit; do
  file="${hit%%:*}"; rest="${hit#*:}"; line="${rest%%:*}"

  # DYNAMIC WINDOW, NOT A FIXED LOOKAHEAD. A fixed form would read a
  # constant `${line},$((line+3))` -- every CURRENT skipif site fits that, but nothing pins it
  # to the decorator's actual extent, so a future multi-line skipif whose artifact marker
  # (e.g. `HOOK.exists()`) sits on line+4 or later would fall through to `continue` below and
  # be SILENTLY reclassified as not-author-local -- shrinking the emitted set with no error.
  # That is the same wrong-green shape (a check whose scope quietly narrows) one layer
  # down inside the tool that measures it.
  #
  # The fix widens the window to the decorator's REAL boundary: scan forward from the hit to
  # the next `def` (any indent -- module-level marker objects like `requires_artifact =
  # pytest.mark.skipif(...)` used via `@requires_artifact` on a later function are still
  # bounded by SOME upcoming `def`, since this repo has no skipif outside a test module).
  # Capped at 30 lines so a malformed file can't make this scan silently unbounded, and an
  # unclosed/unfindable decorator is a HARD FAIL naming file:line -- never a silent continue --
  # because "couldn't determine this hit's extent" is exactly the situation where guessing a
  # boundary is how a real hit goes missing.
  end_line="$(/usr/bin/awk -v start="$((line+1))" -v cap="$((line+30))" \
    'NR>=start && NR<=cap && /^[[:space:]]*def / { print NR; exit }' "$file")"
  if [ -z "$end_line" ]; then
    echo "FAIL skip-baseline: could not find the enclosing def for skipif at $file:$line" \
      "within 30 lines -- refusing to guess a window, classify by hand" >&2
    exit 1
  fi
  ctx="$(sed -n "${line},$((end_line-1))p" "$file")"

  artifact=""
  case "$ctx" in
    *HOOK.exists*)     artifact=".git/hooks/pre-push" ;;
    *BASELINE.exists*) artifact=".claude/.ac5-baseline.txt" ;;
    *) continue ;;   # jq/euid/docs gates are environment, not author-local artifacts
  esac
  printf '%s::%s -> %s\n' "$file" "$line" "$artifact"
done | LC_ALL=C sort
