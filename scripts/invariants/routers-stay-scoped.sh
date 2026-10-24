#!/usr/bin/env bash
# Invariant: widening did not swallow the narrower routers.
#
# WHY. Before this phase there were three routers, each correct inside its own input scope and none
# of them covering a mid-flow item that is neither a user request nor a review finding:
#
#   references/defer-vs-fix.md    reviewer findings. Its first sentence names the four severities.
#   references/findings-tier.md   smoke findings / review concerns / known limitations.
#   references/intent-gate.md     a fresh user request (and its three sizes).
#
# The existing rules are not to be rewritten: the new router widens the range and adds a tier,
# it does not replace them. The failure this guards is the quiet kind -- a new
# router that is cheaper to reach becomes the one everybody uses, the older ones stop being
# maintained, and nothing fails. So two properties are asserted:
#
#   [1] each existing router still declares its own input scope, and
#   [2] the new router points at all three by name, so a reader lands in the right one rather than
#       in the newest one.
#
# PROPERTY, NOT BYTES. [1] does NOT pin a whole sentence. It asserts the shortest fragment that
# carries "this file is about reviewer findings" / "about smoke and review findings" / "about a
# user request". A reworded but equally scoped sentence must stay green, because the thing being
# protected is the scope, not the prose. Pinning the sentence was the first draft of this check and
# it was wrong for a practical reason: a single added quote mark around a path can turn
# fixed-string assertions red against correct documents.
#
# WHAT IT CANNOT DO. It cannot tell you the new router's pointer DESCRIBES each old router
# correctly. A pointer that names defer-vs-fix.md and then mis-states what it covers passes this
# check -- a review named exactly that hole, and it is left open rather than papered
# over, because detecting it needs a reader, not a grep.
#
# Envelope: bash + git only. No python3, no jq (CLAUDE.md).

set -uo pipefail

NAME="routers-stay-scoped"

pass() { printf 'PASS %s: %s\n' "$NAME" "$1"; exit 0; }
fail() { printf 'FAIL %s: %s\n' "$NAME" "$1"; exit 1; }
CANNOT_RUN_RC=3
cannot_run() { printf 'FAIL %s: COULD NOT RUN -- %s\n' "$NAME" "$1"; exit "$CANNOT_RUN_RC"; }

REPO_ROOT="${1:-$(git rev-parse --show-toplevel 2>/dev/null || true)}"
[ -n "$REPO_ROOT" ] || cannot_run "not inside a git work tree (git rev-parse --show-toplevel failed)"
REPO_ROOT="${REPO_ROOT%/}"
cd "$REPO_ROOT" 2>/dev/null || cannot_run "cannot enter repo root: $REPO_ROOT"

REF_DIR="${ROUTERS_REF_DIR:-skills/project-lifecycle/references}"
NEW_DOC="${ROUTERS_NEW_DOC:-$REF_DIR/where-does-this-go.md}"

errs=""
add() { errs="${errs}
  - $1"; }

# ---------------------------------------------------------------------------
# [1] Each pre-existing router still declares its own input scope.
#
# The scope fragment for each file is the shortest text that could not survive a scope change.
# "Reviewers" leaving defer-vs-fix.md means it stopped being about reviewer findings.
# ---------------------------------------------------------------------------
check_scope() {
  _f="$REF_DIR/$1"
  _re="$2"
  _why="$3"
  if [ ! -f "$_f" ]; then
    add "$_f is gone. Widening must not delete a narrower router ($_why)."
    return
  fi
  if ! grep -qE "$_re" -- "$_f"; then
    add "$_f no longer declares its input scope: nothing matches /$_re/. $_why"
  fi
}

check_scope defer-vs-fix.md    'Reviewers'                  "Its scope is reviewer findings, and it is still called from the cadence's fixup step."
check_scope findings-tier.md   '[Ss]moke finding'           "Its scope is smoke findings, review concerns and known limitations of a delivered phase."
check_scope intent-gate.md     '[Uu]ser request|[Rr]equest' "Its scope is a fresh user request, and its size axis is the machinery triage."

# ---------------------------------------------------------------------------
# [2] The new router names all three, so the gap between them is navigable.
#
# Checked only when the new router exists, so this invariant is meaningful on a tree where the
# phase that introduces it has not landed yet -- rather than failing for a file nothing has
# promised to create. [1] is the half that protects the status quo.
# ---------------------------------------------------------------------------
if [ -f "$NEW_DOC" ]; then
  for peer in defer-vs-fix.md findings-tier.md intent-gate.md; do
    grep -qF -- "$peer" "$NEW_DOC" \
      || add "$NEW_DOC does not name $peer. A reader with an item in hand then has no way to tell
    which of the four routers takes it, and will use the newest one."
  done
fi

if [ -n "$errs" ]; then
  fail "a router lost its scope, or the new one does not point at its peers:${errs}"
fi

if [ -f "$NEW_DOC" ]; then
  pass "all three pre-existing routers still declare their own input scope, and $NEW_DOC names each of them -- scope PRESENCE only, not that the pointers describe them correctly"
fi
pass "all three pre-existing routers still declare their own input scope ($NEW_DOC not present, so the pointer half is not applicable)"
