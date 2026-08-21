#!/usr/bin/env bash
# cross-family-code-review.sh — run a CODE review on a foreign CLI family (codex).
#
# WHY THIS EXISTS. "Different lens rather than more reviewers" is a core review rule,
# and the cross-family reviewer is the
# mechanism it names. Without this script it has hardened tooling for only one of its two paths:
# `cross-family-review.sh` runs the brainstorm's blind 2nd agent, with a timeout, sandbox flags and
# an output contract. With no equivalent for code review, a cross-family CODE review would be
# an ad-hoc `codex exec` composed on the spot.
#
# THREE WAYS that ad-hoc form fails:
#   hang     -> runs until the caller's own tool timeout kills it. Zero findings.
#   refusal  -> "Not inside a trusted directory and --skip-git-repo-check was
#              not specified". Zero findings.
#   roaming  -> spends its entire budget printing the files under review with `nl -ba`, then
#              stops. Zero findings.
# `cross-family-review.sh` already prevents all three (`timeout`, `--skip-git-repo-check`, and a
# packet on stdin instead of a roam-the-repo prompt). This script is the missing
# runner for the code-review path.
#
# The four gates are NOT copied. `cross-family-review.sh` takes three defaulted flags
# (--schema / --require / --payload-key) so this script can reuse it; with them left at their
# defaults, its own path is unchanged.
#
# Usage:
#   cross-family-code-review.sh --diff <file> --brief <file> --out <file> [--timeout 300]
#     --diff   the change under review (e.g. `git diff main...HEAD > /tmp/d.patch`)
#     --brief  the review lens: the questions this round is asking. One round, one lens --
#              asking the same three questions again is how you get the same three findings.
#
# Emits <out>, key-disjoint by arm — the ABSENT key is the discriminator:
#   succeeded: {"engine","status":"succeeded","review": <review>}
#   fallback:  {"engine","status":"fallback","fallback_reason":"<reason>"}
# A `status:fallback` means NO REVIEW HAPPENED. It is not a clean bill of health, and the caller
# must not read it as one -- that conflation makes empty rounds look survivable.
# Since this script `exec`s the runner, THE RUNNER'S EXIT STATUS IS THIS SCRIPT'S: 0 a review is in
# --out, 3 no review happened, 2 the call was wrong, 1 the answer could not be written.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="${SCRIPT_DIR}/cross-family-review.sh"
SCHEMA="${SCRIPT_DIR}/cross-family-code-review.schema.json"

DIFF="" BRIEF="" OUT="" TIMEOUT="300"
while [ $# -gt 0 ]; do
  case "$1" in
    --diff)    DIFF="$2";    shift 2;;
    --brief)   BRIEF="$2";   shift 2;;
    --out)     OUT="$2";     shift 2;;
    --timeout) TIMEOUT="$2"; shift 2;;
    *) shift;;
  esac
done

for v in DIFF BRIEF OUT; do
  eval "val=\${$v}"
  [ -n "$val" ] || { echo "FATAL: --${v,,} is required" >&2; exit 2; }
done
for f in "$DIFF" "$BRIEF"; do
  [ -r "$f" ] || { echo "FATAL: '$f' is missing or unreadable" >&2; exit 2; }
done
[ -x "$RUNNER" ] || { echo "FATAL: runner '$RUNNER' is missing or not executable" >&2; exit 2; }

# An EMPTY diff is fatal rather than a clean review. A reviewer handed nothing finds nothing, and
# the result is indistinguishable from a careful review that found nothing -- which is precisely
# the distinction this runner exists to make available.
[ -s "$DIFF" ] || { echo "FATAL: --diff '$DIFF' is empty; a review of nothing is not a clean review" >&2; exit 2; }

PACKET="$(mktemp)"
trap 'rm -f "$PACKET"' EXIT

# The packet carries the diff INLINE. That is the whole difference between this and the ad-hoc
# calls: the reviewer is never asked to go and find the code, so it cannot spend its budget
# discovering the repository instead of reading the change.
{
  cat "$BRIEF"
  printf '\n\n--- BEFORE ANY FINDING ---\n'
  printf 'For every check you run to reach a finding (a grep, a probe, a mutation), you must record\n'
  printf 'it in `checks_performed` with a known-good input that confirmed the CHECK ITSELF works\n'
  printf 'before you believed its result. A grep that finds nothing and a broken grep print the\n'
  printf 'same thing. A finding backed by an unverified check is worth less than no finding.\n'
  printf '\nIn `refutation_attempted`, say what you did to try to prove each finding WRONG. Report it\n'
  printf 'only if it survived. Your verdict goes LAST, after the findings, not before them.\n'
  printf '\n--- DIFF UNDER REVIEW ---\n'
  cat "$DIFF"
} > "$PACKET"

exec /bin/bash "$RUNNER" \
  --family codex \
  --packet "$PACKET" \
  --out "$OUT" \
  --timeout "$TIMEOUT" \
  --schema "$SCHEMA" \
  --require verdict \
  --payload-key review
