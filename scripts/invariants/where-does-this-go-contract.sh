#!/usr/bin/env bash
# Invariant: the routing criterion carries the three things that make it falsifiable --
# a declared refusal class, a priced escape hatch, and the calibration cases it must reproduce.
#
# WHY THESE THREE AND NOT "THE DOC EXISTS". A doc that exists is not a criterion. Each of the three
# is the written form of an acceptance criterion that would otherwise be unfalsifiable prose:
#
#   refusal class: a criterion that names no refused input class is claiming it can decide everything, which
#        is the claim-wider-than-the-mechanism shape this repository files most often.
#   priced hatch: an escape hatch with no stated expectation cannot be observed to have become the default
#        path. Medical triage does not forbid over-triage; it publishes a rate and watches it.
#   calibration cases: the three landings a human already decided are the specified oracle. If they
#        are not IN the doc, an edit that breaks one of them is invisible in the diff -- and the
#        whole point of recording them is that the criterion is adjusted to the landings and never
#        the landings to the criterion.
#
# WHAT THIS CHECKS AND WHAT IT CANNOT. It checks that each of the three is PRESENT and non-empty.
# It cannot tell you the refusal classes are the right ones, that the hatch's expectation is
# well-chosen, or that the criterion actually reproduces the landings -- the last of those is a
# judgement a human or a test makes, not a grep. Stated here because a presence check reported as
# "the criterion is sound" is a different and worse failure than no check at all, and this
# repository has measured exactly that: evidence validation that confirmed only EXISTENCE and
# reported it as "verified".
#
# NOT A BYTE PIN. Every assertion below matches the shortest stable fragment that carries the
# property, never a whole sentence. The reason is practical: a single added quote mark around a path
# can turn fixed-string assertions red against CORRECT documents.
#
# Envelope: bash + git only. No python3, no jq (CLAUDE.md).

set -uo pipefail

NAME="where-does-this-go-contract"

pass() { printf 'PASS %s: %s\n' "$NAME" "$1"; exit 0; }
fail() { printf 'FAIL %s: %s\n' "$NAME" "$1"; exit 1; }
# Third verdict: the CHECK could not run, not the repo is wrong. close-gate reads exit STATUS only,
# so 1 and 3 both block -- which is the fail-closed behaviour a check that could not run must have.
# What 3 buys is that a direct caller, CI, or a test can tell the two apart.
CANNOT_RUN_RC=3
cannot_run() { printf 'FAIL %s: COULD NOT RUN -- %s\n' "$NAME" "$1"; exit "$CANNOT_RUN_RC"; }

REPO_ROOT="${1:-$(git rev-parse --show-toplevel 2>/dev/null || true)}"
[ -n "$REPO_ROOT" ] || cannot_run "not inside a git work tree (git rev-parse --show-toplevel failed)"
REPO_ROOT="${REPO_ROOT%/}"
cd "$REPO_ROOT" 2>/dev/null || cannot_run "cannot enter repo root: $REPO_ROOT"

DOC="${WDTG_DOC:-skills/project-lifecycle/references/where-does-this-go.md}"

[ -f "$DOC" ] || fail "$DOC does not exist
  -> This invariant is the contract for the routing criterion. Without the document there is
     nothing routing a mid-flow item, which is the gap this document was written to close."

# Read the file ONCE. Every assertion below works off this copy, so a file changing under the check
# cannot make two assertions disagree about what they read.
BODY="$(cat -- "$DOC" 2>/dev/null)" || cannot_run "cannot read $DOC"
[ -n "$BODY" ] || fail "$DOC is empty"

errs=""
add() { errs="${errs}
  - $1"; }

# ---------------------------------------------------------------------------
# [1] Refusal class -- a declared refusal class, with at least one class actually named.
#
# Two assertions, not one. A heading with nothing under it is the failure mode worth guarding:
# "Refuses to decide" as an empty section reads, in a diff and to a reader, exactly like a
# criterion that declared its blind spot.
# ---------------------------------------------------------------------------
REFUSE_RE='^#+ .*[Rr]efus'
if ! printf '%s\n' "$BODY" | grep -qE "$REFUSE_RE"; then
  add "no refusal section: no heading matches /$REFUSE_RE/ (refusal class). A criterion that names no input
    class it hands to a human is claiming it can decide every case."
else
  # Count numbered classes anywhere in the file. Deliberately NOT scoped to the section's line
  # range: an interval counter whose end condition does not match the real document counts to the
  # end of the file.
  n_classes="$(printf '%s\n' "$BODY" | grep -cE '^[0-9]+\. ' || true)"
  [ -n "$n_classes" ] || n_classes=0
  if [ "$n_classes" -lt 1 ]; then
    add "the refusal section names no class: zero lines match /^[0-9]+\\. / in $DOC (refusal class)."
  fi
fi

# ---------------------------------------------------------------------------
# [2] Priced hatch -- the hatch is priced: an expectation AND the threshold at which it is a defect.
#
# Both halves are required. An expectation with no threshold cannot fire; a threshold with no
# expectation is a number with nothing behind it.
# ---------------------------------------------------------------------------
printf '%s\n' "$BODY" | grep -qiE 'refusal rate' \
  || add "no refusal-rate expectation in $DOC (priced hatch): nothing matches /refusal rate/i. An escape
    hatch with no stated expectation cannot be observed to have become the default path."
printf '%s\n' "$BODY" | grep -qiE 'is a defect|file it as a defect|not a safe default' \
  || add "the refusal rate has no defect threshold in $DOC (priced hatch): nothing says at what point a
    high refusal rate stops being prudence and becomes a defect to file."

# ---------------------------------------------------------------------------
# [3] Calibration cases -- the three calibration cases are present, each with its landing.
#
# Identified by backlog id, not by title: a title may not be ASCII, and
# scripts/invariants/no-cjk-in-shipped-files.sh forbids CJK under skills/ -- so an id is the
# only stable handle for a calibration case.
# ---------------------------------------------------------------------------
for id in B7272 B7270 B7271; do
  printf '%s\n' "$BODY" | grep -qE "\\b${id}\\b" \
    || add "calibration case $id is absent from $DOC (calibration cases). The three landings a human decided on
    are the specified oracle; if they are not in the document, an edit that breaks one
    of them does not show up in the diff."
done

# The landing words must both appear, or the cases are named without their answers.
printf '%s\n' "$BODY" | grep -qiE 'mainline|main-line|main line' \
  || add "no main-line landing named in $DOC (calibration cases): the main-line calibration case has no recorded
    answer."
printf '%s\n' "$BODY" | grep -qiE 'backlog' \
  || add "no backlog landing named in $DOC (calibration cases): the two deferred calibration cases have no
    recorded answer."

# ---------------------------------------------------------------------------
# [4] Drain owner -- the doc says who executes which outcome.
#
# Folded in here rather than given its own script: it is the same job as [1]-[3], asserting that a
# required part of this one document's contract is present. A second script would be a second
# spelling of the same assertion, and a copied guard drifts.
# ---------------------------------------------------------------------------
printf '%s\n' "$BODY" | grep -qiE 'who (drains|executes|decides)|owner' \
  || add "the document does not say who drains the queue or who executes which outcome (drain owner).
    Every capture-plus-inbox system surveyed fails the same way: the inbox is only as good as its
    drain, and all of them assume a named owner."

if [ -n "$errs" ]; then
  fail "the routing criterion is missing part of its contract:${errs}"
fi

pass "$DOC declares a refusal class, prices its hatch, carries all three calibration cases with their landings, and names the drain's owner -- PRESENCE only, which is not evidence that any of the four is any good"
