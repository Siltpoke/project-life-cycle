#!/usr/bin/env bash
# init-harness-check -- does the repo /init-harness just bootstrapped actually hold what it must?
# Run from the adopter's repo root (or pass it as $1):
#   bash "${CLAUDE_PLUGIN_ROOT}/scripts/init-harness-check.sh" [repo]
#
# WHY THIS IS A SCRIPT. /init-harness is prose that a model follows, and its last step was a report
# the same model wrote. On a measured run (Qoder, 2026-10-23) it skipped the close gate AND the
# pre-push hook -- the two pieces init-harness.md says MUST be activated -- and then reported
# "Bootstrap complete. 18 files created", with neither one in its list. Nothing between the writing
# and the report counted what was there. This script is that count: it reads the disk, not the
# model's account of what it wrote.
#
# EXIT CODES:
#   0  every required item is present        -> the report may say the bootstrap is complete
#   1  one or more items missing             -> the report MUST open with the list this prints
#   3  the check could not run               -> the report says the check could not run
# 3 is separate from 1 because a check that could not run must never read as a check that ran.
#
# THIS SCRIPT NEVER WRITES. It only reads the repo and prints.
set -u

REPO="${1:-.}"
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE_MD="$SELF_DIR/../skills/project-lifecycle/references/close-gate.md"

cant_run() { printf 'init-harness-check: COULD NOT RUN -- %s\n' "$1"; exit 3; }

cd "$REPO" 2>/dev/null || cant_run "no such directory: $REPO"
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || cant_run "not inside a git work tree: $(pwd)"
cd "$(git rev-parse --show-toplevel)" || cant_run "cannot reach the repo root"
[ -f "$TEMPLATE_MD" ] || cant_run "the gate template is not where this script expects it: $TEMPLATE_MD"

MISSING=""
PRESENT=""
miss() { MISSING="${MISSING}  ✗ $1"$'\n'; }
have() { PRESENT="${PRESENT}  ✓ $1"$'\n'; }

# 1-3. The three anchor docs. CONTEXT-MAP.md is the documented multi-context form of CONTEXT.md;
# RESUME is accepted at either conventional location, the same rule entry detection uses.
[ -f CLAUDE.md ] && have "CLAUDE.md" || miss "CLAUDE.md"
{ [ -f CONTEXT.md ] || [ -f CONTEXT-MAP.md ]; } && have "CONTEXT.md" || miss "CONTEXT.md (or CONTEXT-MAP.md)"
{ [ -f docs/RESUME.md ] || [ -f RESUME.md ]; } && have "RESUME.md" || miss "docs/RESUME.md"

# 4. The journal home: the monolith or the fragment directory.
{ [ -f docs/iteration-journal.md ] || [ -d docs/journal.d ]; } && have "journal home" \
  || miss "journal home (docs/iteration-journal.md or docs/journal.d/)"

# 5. CHANGELOG.md with an [Unreleased] section -- the gate's phase mode reads that section.
if [ ! -f CHANGELOG.md ]; then miss "CHANGELOG.md"
elif grep -q '^## \[Unreleased\]' CHANGELOG.md; then have "CHANGELOG.md [Unreleased]"
else miss "CHANGELOG.md has no '## [Unreleased]' section"; fi

# 6. .gitignore keeps the tasklist out of history (it carries a per-phase session nonce).
if [ -f .gitignore ] && grep -qxF '/.claude/tasklist.md' .gitignore; then have ".gitignore ignores /.claude/tasklist.md"
else miss ".gitignore line '/.claude/tasklist.md'"; fi

# 7. The gate itself -- AND that it is the template the skill ships. On the measured run the model
# later copied the skill repo's OWN gate in instead, whose default product tree is that repo's
# directories; with no product_paths declared, the copied gate counted its own new file as "the
# product changed" and passed an empty task. Comparing against the shipped template is what tells
# "a gate" from "the right gate". The template is extracted the same way the test suite extracts
# it: the ```bash fence after the "## Portable gate script" heading.
if [ ! -f scripts/close-gate.sh ]; then
  miss "scripts/close-gate.sh"
else
  TEMPLATE="$(awk '
    /^## Portable gate script/ { h=1; next }
    h && !f && $0 == "```bash" { f=1; next }
    f && $0 == "```" { exit }
    f { print }' "$TEMPLATE_MD")"
  [ -n "$TEMPLATE" ] || cant_run "found no gate script under '## Portable gate script' in $TEMPLATE_MD"
  if [ "$TEMPLATE" = "$(cat scripts/close-gate.sh)" ]; then have "scripts/close-gate.sh (matches the shipped template)"
  else miss "scripts/close-gate.sh is not the shipped template -- copy it from references/close-gate.md §Portable gate script"; fi
fi

# 8. The manifest: valid JSON carrying a test_command. jq is checked first because the gate cannot
# run without it either, so its absence is a finding about the bootstrap, not a reason to skip.
if [ ! -f .claude/close-gate.json ]; then
  miss ".claude/close-gate.json"
elif ! command -v jq >/dev/null 2>&1; then
  miss "jq is not installed -- the gate needs it, and the manifest cannot be checked without it"
elif ! jq -e . .claude/close-gate.json >/dev/null 2>&1; then
  miss ".claude/close-gate.json is not valid JSON"
elif ! jq -e '(.test_command | type) == "string" and (.test_command | length) > 0' .claude/close-gate.json >/dev/null 2>&1; then
  miss ".claude/close-gate.json has no test_command"
else
  have ".claude/close-gate.json (valid JSON, test_command set)"
fi

# 9. An ACTIVE pre-push wiring that calls the gate. Two documented wirings, and either counts:
# core.hooksPath pointing at a directory whose pre-push calls it, or the default .git/hooks/pre-push.
# A hook file that is not executable is not active -- git skips it without a word.
hook_calls_gate() { [ -f "$1" ] && [ -x "$1" ] && grep -q 'close-gate' "$1"; }
HP="$(git config --get core.hooksPath 2>/dev/null || true)"
DEFAULT_HOOK="$(git rev-parse --git-common-dir)/hooks/pre-push"
if [ -n "$HP" ]; then
  # When core.hooksPath is set, git reads ONLY that directory; .git/hooks is not consulted.
  if hook_calls_gate "$HP/pre-push"; then have "pre-push hook active (core.hooksPath=$HP)"
  else miss "pre-push hook: core.hooksPath=$HP but $HP/pre-push is missing, not executable, or does not call close-gate"; fi
elif hook_calls_gate "$DEFAULT_HOOK"; then
  have "pre-push hook active (.git/hooks/pre-push)"
else
  miss "pre-push hook: neither core.hooksPath nor .git/hooks/pre-push runs close-gate (missing, not executable, or not wired)"
fi

N_MISS="$(printf '%s' "$MISSING" | grep -c '✗' || true)"
if [ "$N_MISS" -gt 0 ]; then
  printf 'INCOMPLETE -- %s of 9 required items missing:\n%s' "$N_MISS" "$MISSING"
  [ -n "$PRESENT" ] && printf 'present:\n%s' "$PRESENT"
  exit 1
fi
printf 'COMPLETE -- all 9 required items present:\n%s' "$PRESENT"
exit 0
