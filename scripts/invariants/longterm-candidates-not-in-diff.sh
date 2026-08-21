#!/usr/bin/env bash
# Invariant `longterm-candidates-not-in-diff`: under `mode: fast`, no commit writes a long-term record without authorisation.
#
# THE CLOSED LOOP, and it takes both halves. The pre-merge brief lists what WOULD be written to the
# files an assistant reads first in every future conversation, every box unticked. That default is
# meaningless if the change is already in the diff -- merging writes it regardless. So the
# candidates must not be in the diff at all, and writing must happen afterwards as its own act,
# carrying a `Longterm-write:` trailer naming what the user ticked.
#
# ARMED BY THE MODE, AND IT SAYS WHICH. Under any mode other than `fast` this check does not apply
# and PRINTS THAT rather than passing silently -- one failure shape is a check firing on
# projects that never configured the feature, and its mirror is a check that quietly applies to
# nobody. A reader must be able to tell "checked and clean" from "did not apply".
#
# NARROW, AND SAID RATHER THAN LEFT TO BE DISCOVERED: this asserts the DIFF, not the selection.
# Nothing here can tell a trailer the user really authorised from one the assistant wrote. Same
# residual every trailer carries. What it closes is the SILENT path.
#
# Verdicts: 0 pass or not-applicable, 1 an unauthorised write, 3 could not run.
set -euo pipefail
# LONGTERM_ROOT exists so the guard can be run against a throwaway repository. This repository runs with
# no `mode` key, so on this tree the check reports "not applicable" and would do so forever -- a
# guard proven only where it cannot arm is a guard nobody has run. The default is the repo this
# script lives in, so a plain invocation behaves exactly as if the variable did not exist.
cd "${LONGTERM_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

LIST="${LONGTERM_PATHS:-.claude/longterm-record-paths.txt}"
CLAUDE_MD="${LONGTERM_CLAUDE_MD:-CLAUDE.md}"
BASE="${LONGTERM_BASE:-}"

[ -r "$LIST" ] || { printf 'COULD NOT RUN: %s is not readable\n' "$LIST" >&2; exit 3; }

paths="$(/usr/bin/grep -v '^[[:space:]]*#' "$LIST" | /usr/bin/grep -v '^[[:space:]]*$' || true)"
[ -n "$paths" ] || { printf 'FAIL the long-term path list is empty -- an empty list protects nothing\n' >&2; exit 1; }

# `mode` is read DIRECTLY, and the reason is worth a sentence because the obvious objection is
# right in general: elsewhere in this design the effective configuration must come from the
# resolver, since an explicitly set low-level key beats the preset and only the resolver knows that
# rule. It does not apply here. `mode` is the key being expanded, not one of the keys it expands
# into, so the resolver never emits a row for it and there is nothing for it to arbitrate.
#
# An earlier version of this file CLAIMED to use the resolver while doing exactly what is below,
# and also made the resolver's presence a silent precondition -- so on any tree where the relative
# path did not resolve, the mode read as unset and the whole check reported "not applicable".
# Measured: every fixture repo took that path.
mode=""
if [ -r "$CLAUDE_MD" ]; then
  mode="$(awk '
    /^[[:space:]]*#/ { next }
    index($0, "mode:") == 1 {
      sub("^mode:[[:space:]]*", ""); sub("[[:space:]]*#.*$", ""); gsub(/[[:space:]]+$/, "")
      print; exit
    }' "$CLAUDE_MD")"
fi

if [ "$mode" != "fast" ]; then
  printf 'ok  not applicable: this project runs mode=%s, and this rule is armed only by fast\n' \
    "${mode:-<unset>}"
  exit 0
fi

if [ -z "$BASE" ]; then
  BASE="$(/usr/bin/git symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null || true)"
  [ -n "$BASE" ] || { printf 'COULD NOT RUN: cannot determine the default branch; set LONGTERM_BASE\n' >&2; exit 3; }
fi
mb="$(/usr/bin/git merge-base "$BASE" HEAD 2>/dev/null)" || {
  printf 'COULD NOT RUN: no merge-base between %s and HEAD\n' "$BASE" >&2; exit 3; }

fail=0
checked=0
while IFS= read -r sha; do
  [ -n "$sha" ] || continue
  touched="$(/usr/bin/git show --pretty=format: --name-only "$sha" | /usr/bin/grep -v '^$' || true)"
  hit=""
  while IFS= read -r p; do
    [ -n "$p" ] || continue
    while IFS= read -r t; do
      [ -n "$t" ] || continue
      case "$t" in $p) hit="$hit $t" ;; esac
    done <<<"$touched"
  done <<<"$paths"
  [ -n "$hit" ] || continue
  checked=$((checked + 1))
  # NO TRAILER EXEMPTS A COMMIT ON THIS BRANCH.
  # An earlier version accepted any commit carrying a `Longterm-write:` trailer -- which
  # reduces the criterion from "the candidates are not in this PR's diff" to "the commit that puts
  # them there says it meant to". A trailer-bearing commit on the feature branch is STILL IN THE
  # DIFF, so merging still writes it, which is exactly the loop the criterion closes.
  #
  # The trailer's place is on the DEFAULT branch, after the person has ticked boxes while reading
  # the PR. That is where hooks/plc-longterm-write.sh is meant to run.
  trailer="$(/usr/bin/git log -1 --format='%(trailers:key=Longterm-write,valueonly)' "$sha" | tr -d '[:space:]')"
  if [ -n "$trailer" ]; then
    printf 'FAIL %s carries a `Longterm-write:` trailer on a FEATURE branch:%s\n' \
      "$(/usr/bin/git log -1 --format='%h %s' "$sha")" "$hit" >&2
    printf '    the trailer authorises a write AFTER the selection, on the default branch. Here it\n' >&2
    printf '    is still in the PR diff, so merging writes it whether or not anybody ticked a box.\n' >&2
  else
    printf 'FAIL %s writes a long-term record on a feature branch:%s\n' \
      "$(/usr/bin/git log -1 --format='%h %s' "$sha")" "$hit" >&2
    printf '    candidates belong in the pre-merge brief, unticked, and out of the diff entirely.\n' >&2
  fi
  fail=1
done < <(/usr/bin/git rev-list "$mb..HEAD")

[ "$fail" = 0 ] || exit 1
printf 'ok  mode=fast: no commit on this branch touches a long-term record -- the candidates are in the brief, not the diff\n'
