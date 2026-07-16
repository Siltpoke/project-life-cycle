#!/usr/bin/env bash
# close-gate.sh — deterministic wrap-up gate for THIS repo (project-life-cycle).
#
# Usage: close-gate.sh phase X.Y
#
# WHY THIS IS NOT the canonical gate from references/close-gate.md:
# This repo gitignores all of docs/ (a local .git/hooks/pre-push check BLOCKS any
# tracked docs/ file). The
# canonical gate proves the journal / spec / plan / ROADMAP ceremony via git commit-range
# checks (git diff origin/main..HEAD), which structurally CANNOT see gitignored files. So the
# two designs are mutually exclusive here. This gate proves the same ceremony via LOCAL FILE
# signals (existence + FACT content + freshness-vs-branch-point) instead — the only observable
# evidence for docs that never enter git. Tracked artifacts (CHANGELOG.md, the feat/fix
# commit, the test-evidence file) are still checked via git / file as normal.
#
# Envelope: bash + git + jq + coreutils only. NO python3 (a hard rule for this gate — the
# gate must stay a drop-in with a minimal dependency footprint).
set -euo pipefail

MODE="${1:?usage: close-gate.sh phase X.Y}"
PHASE="${2:-}"
[ "$MODE" = phase ] || { echo "✗ only 'phase' mode is supported"; exit 1; }
[ -n "$PHASE" ] || { echo "✗ phase mode needs a PHASE arg (e.g. close-gate.sh phase 1.2)"; exit 1; }

M=".claude/close-gate.json"
[ -f "$M" ] || { echo "✗ missing manifest $M"; exit 1; }
g() { jq -r ".$1 // empty" "$M" | sed "s/{PHASE}/$PHASE/g"; }

fail=0
ok()   { echo "✓ $1"; }
bad()  { echo "✗ $1"; fail=1; }
warn() { echo "⚠ $1"; }   # never touches $fail
glob_exists() { compgen -G "$1" >/dev/null 2>&1; }

# freshness: `find X -newer Y` reads full sub-second mtime (bash 3.2's `[ a -nt b ]` truncates
# to whole seconds and mis-orders files placed <1s apart). Fails
# CLOSED on an exact tie (equal mtime = NOT fresh).
fresh() { [ -e "$1" ] && [ -e "$2" ] && [ -n "$(find "$1" -newer "$2" -print 2>/dev/null)" ]; }

# Stamp a temp file's mtime to a commit's committer-date. --date=format-LOCAL renders the digits
# in THIS machine's timezone — exactly how `touch -t` interprets them. (Plain --date=format:
# renders in the commit's OWN offset, which touch -t then misreads as local time — a cross-tz
# freshness bug that can false-PASS stale docs or false-FAIL fresh ones. format-local sidesteps
# it and stays BSD-touch-safe, unlike a GNU-only `touch -d @epoch`.)
stamp_ref() { touch -t "$(git show -s --format=%cd --date=format-local:%Y%m%d%H%M.%S "$1")" "$2"; }

# Branch-point ref: a docs artifact written DURING this phase is newer than the commit the branch
# forked from. Fail CLOSED if origin/main can't be resolved — the old genesis-commit fallback made
# every freshness check trivially pass (anything postdates the repo's first commit → false PASS).
BP="$(git merge-base origin/main HEAD 2>/dev/null || true)"
[ -n "$BP" ] || { echo "✗ cannot resolve 'git merge-base origin/main HEAD' — fetch origin/main before running the gate"; exit 1; }
# register the cleanup trap BEFORE the second mktemp so a failure there can't leak the first.
BPREF="$(mktemp)"; HEADREF=""; trap 'rm -f "$BPREF" "$HEADREF"' EXIT; HEADREF="$(mktemp)"
stamp_ref "$BP" "$BPREF"
# HEAD-commit ref for the test-evidence check: evidence must be newer than the LAST COMMIT, not
# newer than .git/HEAD's file mtime (that mtime tracks checkout, not commit — evidence written at
# checkout then N commits later would false-PASS as "fresh"). Materialize HEAD's committer-date.
stamp_ref HEAD "$HEADREF"

RANGE="origin/main..HEAD"

# skip-escape-hatch: an exempt_* flag is only legit if a 'SKIP: <reason>' line is in the newest journal.
JD="$(g retention.journal_dir)"; JD="${JD:-docs/journal.d}"
# `|| true` on BOTH the pipeline and the assignment: with no *.md fragment (brand-new phase, or
# the dir absent), the glob doesn't expand, `ls` exits non-zero, and under `pipefail` the pipeline
# reports that — an unguarded `J="$(...)"` under `set -e` would then kill the script silently,
# before any ✗ row prints, on the exact "journal not written yet" case the gate must report.
newest_journal() { ls -t "$JD"/*.md 2>/dev/null | head -1 || true; }
J="$(newest_journal || true)"
skip_logged() { [ -n "$J" ] && grep -qE '^[[:space:]]*SKIP:' "$J" 2>/dev/null; }

echo "── close-gate phase $PHASE (gitignored-docs mode) ──"

# 1. a feat/fix commit exists in the branch range (the phase produced code).
if git log "$RANGE" --format=%s 2>/dev/null | grep -qE '^(feat|fix)(\(|!|:)'; then
  ok "feat/fix commit in branch range"
else bad "no feat/fix commit in $RANGE — a phase must ship code"; fi

# 2. CHANGELOG.md [Unreleased] touched in range (tracked → git check).
if [ "$(g exempt_changelog)" = true ]; then
  skip_logged && ok "changelog exempt (SKIP: logged)" || bad "exempt_changelog=true but no 'SKIP:' line in newest journal"
elif git diff --name-only "$RANGE" 2>/dev/null | grep -qE '^CHANGELOG\.md$'; then
  ok "CHANGELOG.md touched in range"
else bad "CHANGELOG.md not touched in $RANGE (add an [Unreleased] entry, or set exempt_changelog + SKIP:)"; fi

# 3 + 4. spec + plan docs exist for the phase (LOCAL files — docs/ is gitignored).
if [ "$(g exempt_docs)" = true ]; then
  skip_logged && ok "spec/plan exempt (SKIP: logged)" || bad "exempt_docs=true but no 'SKIP:' line in newest journal"
else
  SPEC="$(g phase_docs_glob)"; PLAN="$(g plan_glob)"
  { [ -n "$SPEC" ] && glob_exists "$SPEC"; } && ok "spec doc exists ($SPEC)" || bad "no spec doc matching '$SPEC'"
  { [ -n "$PLAN" ] && glob_exists "$PLAN"; } && ok "plan doc exists ($PLAN)" || bad "no plan doc matching '$PLAN'"
fi

# 5. newest journal.d fragment: exists + fresh-vs-branch-point + FACT fields + Plan-deviations.
if [ -z "$J" ]; then
  bad "no journal fragment under $JD/"
else
  fresh "$J" "$BPREF" && ok "journal fragment fresh this phase ($(basename "$J"))" \
    || bad "newest journal fragment $(basename "$J") is older than the branch point — write this phase's FACT entry"
  MISS=""
  for f in Decision Why Backing; do
    grep -qE "^[[:space:]]*[-*][[:space:]]+\*\*${f}:?\*\*" "$J" || MISS="$MISS $f"
  done
  [ -z "$MISS" ] && ok "journal FACT fields present (Decision/Why/Backing)" || bad "journal FACT entry missing field(s):$MISS"
  grep -qE '\*\*Plan deviations:?\*\*|^#{1,4}[[:space:]]*Plan deviations' "$J" \
    && ok "journal 'Plan deviations' header present" || bad "journal missing 'Plan deviations' header"
fi

# 6. ROADMAP.md exists + fresh (LOCAL file — gitignored).
if [ -f docs/ROADMAP.md ]; then
  fresh docs/ROADMAP.md "$BPREF" && ok "ROADMAP.md updated this phase" \
    || bad "docs/ROADMAP.md not updated since the branch point (flip ✅/▶ for this phase)"
else bad "docs/ROADMAP.md missing"; fi

# 7. fresh, non-empty test-evidence (validate.py output captured to the evidence file).
#    The gate does NOT run validate.py itself (jq-only envelope); the runner writes evidence,
#    the gate checks it. Skipped only when the manifest configures no test_evidence.
EV="$(g test_evidence)"
if [ -z "$EV" ]; then
  warn "no test_evidence configured in manifest — skipping the test-ran check"
elif [ -s "$EV" ] && fresh "$EV" "$HEADREF"; then
  ok "fresh non-empty test-evidence ($EV)"
else bad "stale/empty/missing test-evidence $EV — run 'python3 scripts/validate.py 2>&1 | tee $EV' after your last commit"; fi

echo "──"
[ $fail -eq 0 ] && { echo "✓ close-gate PASS (phase $PHASE)"; exit 0; } \
                || { echo "✗ close-gate FAIL (phase $PHASE) — fix the ✗ rows above, then re-run"; exit 1; }
