#!/usr/bin/env bash
# skills/project-lifecycle/hooks/plc-branch-protection.sh
#
# The single human act `fast` cannot do without: someone clicking merge.
#
# WHY THIS CHECK EXISTS AT ALL. Under `fast` the per-task human approval moves to the merge
# boundary, and the merge button is chosen precisely because it is the one action an assistant
# physically cannot perform. That argument collapses the moment the assistant can push the default
# branch directly -- the button stops being a boundary and becomes a formality. So the protection
# has to be ON, and the criterion asks for BOTH halves rather than just the outcome: read the
# configuration, and confirm a push is actually refused.
#
# THREE VERDICTS, and the third is the point:
#   0  protection is configured, and a push to the default branch is refused
#   1  the repository is wrong -- protection is off, or a push would be accepted
#   3  COULD NOT RUN -- no `gh`, not authenticated, no network, insufficient permission
#
# 3 IS NEVER A PASS. The rule: a check that could not run must not report as though it had. Most
# adopters will see 3 in CI, where the token cannot read protection settings, and reporting that as
# green would make this the most reassuring useless check in the suite.
#
# ARMED BY THE MODE. Under any mode other than `fast` this prints that it does not apply and exits
# 0. The argument above is specific to `fast`: it is `fast` that moves the human approval onto the
# merge button. A project running `detailed` still stops a human at every task, so an unprotected
# default branch there is a different (real, but different) concern, and firing on it would be the
# familiar defect of a check going off at projects that never configured the feature.
#
set -euo pipefail

remote="${1:-origin}"
CLAUDE_MD="${PROTECTION_CLAUDE_MD:-CLAUDE.md}"

mode=""
if [ -r "$CLAUDE_MD" ]; then
  mode="$(awk '
    /^[[:space:]]*#/ { next }
    index($0, "mode:") == 1 {
      sub("^mode:[[:space:]]*", ""); sub("[[:space:]]*#.*$", ""); gsub(/[[:space:]]+$/, "")
      print; exit
    }' "$CLAUDE_MD")"
fi
if [ "${PROTECTION_FORCE:-0}" != "1" ] && [ "$mode" != "fast" ]; then
  printf 'ok  not applicable: this project runs mode=%s, and this rule is armed only by fast\n' \
    "${mode:-<unset>}"
  exit 0
fi

# THE WRITTEN ADMISSION, and it exists because the requirement is UNSATISFIABLE for a large share of
# this skill's users. Measured, not assumed: on GitHub, a PRIVATE repository on the Free plan cannot
# have branch protection at all -- neither classic protected branches nor rulesets; both are
# public-repository-only on Free. A private project on a free account is exactly the shape most of
# the people this mode is for are in, and without an escape they would set `mode: fast`, hit this
# check, and be blocked forever with no action available to them but paying or going public.
#
# The admission buys no safety -- anyone can write the line. That is not what it is for. What it
# removes is somebody believing they have a boundary they do not have.
ack="$(awk '
  /^[[:space:]]*#/ { next }
  index($0, "merge-boundary:") == 1 {
    sub("^merge-boundary:[[:space:]]*", ""); sub("[[:space:]]*#.*$", ""); gsub(/[[:space:]]+$/, "")
    print; exit
  }' "$CLAUDE_MD" 2>/dev/null || true)"

case "$ack" in
  ""|"protected") ;;
  "unprotected-acknowledged")
    printf 'ok  ACKNOWLEDGED, NOT PROTECTED: this project has stated in writing that its merge button is not a hard boundary.\n'
    printf '    Nothing stops an assistant pushing the default branch directly here, so "nobody merged it" is not\n'
    printf '    something you can conclude on this repository. Under `fast` that button is the only human act left.\n'
    exit 0 ;;
  *)
    printf 'unrecognised merge-boundary: %s (legal values: protected, unprotected-acknowledged)\n' "$ack" >&2
    exit 2 ;;
esac

need() { command -v "$1" >/dev/null 2>&1; }

# A FAILURE THAT NAMES NO ACTION IS A WALL. Printed on every not-protected verdict, because for a
# private repository on a free plan there is no setting to change -- the feature is not sold at that
# tier -- and a check that just says "not protected" leaves that reader with nothing to do.
no_way_out() {
  printf '\n    Two ways forward, and the second is legitimate:\n'
  printf '      1. Turn protection on. NOTE: on GitHub this is unavailable for a PRIVATE repository\n'
  printf '         on the Free plan -- protected branches and rulesets are both public-only there.\n'
  printf '      2. If you cannot, say so in writing. Put this in CLAUDE.md:\n\n'
  printf '             merge-boundary: unprotected-acknowledged\n\n'
  printf '         It buys no safety -- anyone can write it. What it means is that you know the merge\n'
  printf '         button here is not a hard boundary, and that under `fast` it is the only human act\n'
  printf '         left. See references/mode.md, "When the merge button is not a boundary".\n'
}

if ! need gh; then
  printf 'COULD NOT RUN: `gh` is not installed, so branch protection cannot be read\n' >&2
  exit 3
fi
if ! gh auth status >/dev/null 2>&1; then
  printf 'COULD NOT RUN: `gh` is not authenticated\n' >&2
  exit 3
fi

slug="$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || true)"
[ -n "$slug" ] && [ "$slug" != "null" ] || {
  printf 'COULD NOT RUN: cannot resolve the repository from remote %s\n' "$remote" >&2; exit 3; }

default="$(gh repo view --json defaultBranchRef -q .defaultBranchRef.name 2>/dev/null || true)"
[ -n "$default" ] && [ "$default" != "null" ] || {
  printf 'COULD NOT RUN: cannot resolve the default branch of %s\n' "$slug" >&2; exit 3; }

# --- half 1: the configuration ---------------------------------------------------------------
# A 404 here is ambiguous by design on GitHub's side: it is returned both for "no protection" and
# for "your token may not read protection". Those are a FAIL and a COULD-NOT-RUN respectively, and
# conflating them is how this check would quietly become decorative. The token's own permission is
# probed first so the two can be told apart.
if ! api="$(gh api "repos/$slug/branches/$default/protection" 2>&1)"; then
  case "$api" in
    *"Branch not protected"*)
      printf 'FAIL %s: the default branch `%s` is NOT protected -- an assistant can push straight to it, and the merge button stops being a boundary\n' \
        "$slug" "$default" >&2
      no_way_out >&2
      exit 1 ;;
    *"Not Found"*|*"404"*)
      if perm="$(gh api "repos/$slug" -q .permissions.admin 2>/dev/null)" && [ "$perm" = "true" ]; then
        printf 'FAIL %s: the default branch `%s` has no protection configured\n' "$slug" "$default" >&2
        no_way_out >&2
        exit 1
      fi
      printf 'COULD NOT RUN: cannot read protection on %s (404, and this token is not an admin, so absent and unreadable are indistinguishable here)\n' \
        "$slug" >&2
      exit 3 ;;
    *)
      printf 'COULD NOT RUN: reading protection failed: %s\n' "$api" >&2
      exit 3 ;;
  esac
fi

# --- half 2: a push is actually refused --------------------------------------------------------
# A DRY RUN, deliberately: this must never be the thing that pushes to the default branch. A dry-run
# push is refused by the same server-side rule as a real one, and the criterion's wording -- "an
# attempt to push the default branch is refused" -- is satisfied by the refusal, not by damage.
if git push --dry-run "$remote" "HEAD:$default" >/dev/null 2>&1; then
  printf 'FAIL %s: protection is configured but a push to `%s` was accepted (dry run) -- the rule does not cover this actor\n' \
    "$slug" "$default" >&2
  exit 1
fi

printf 'ok  %s: `%s` is protected and a push to it is refused (both halves checked)\n' "$slug" "$default"
