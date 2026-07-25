#!/usr/bin/env bash
# close-gate.sh — deterministic wrap-up gate for THIS repo (project-life-cycle).
#
# Usage: close-gate.sh task X.Y     (per-commit subset — run by the pre-push hook)
#        close-gate.sh phase X.Y    (phase close — adds CHANGELOG / spec / plan / ROADMAP; pre-merge)
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

# --- test-evidence content fingerprint (shared by the runner and row 7) --------------------
#
# GATE-RELEVANT PATHS — exactly scripts/validate.py's inputs, the validator itself, and the
# test-evidence contract. Written down here on purpose: a permissive list
# silently re-breaks the check, and a list that drifts from validate.py makes the ✓ a lie.
# validate.py reads the plugin manifests, skills/*/SKILL.md frontmatter + referenced files,
# the commands manifest + commands/*.md, and every TRACKED *.md (check 9). It reads no .sh,
# no test file, nothing untracked — so none of those appear here.
#
# The tracked-only surface is load-bearing. Check 9 used to WALK the filesystem: orders of magnitude more .md on
# this repo than are tracked (another tool's cache, the gitignored docs/ tree). No content
# check over inputs nearly all invisible to git can be honest; validate.py was narrowed to tracked
# files (md_files_to_check) so this fingerprint means exactly what it says.
GATE_RELEVANT_PATHS='*.md
plugin.json
.claude-plugin/*.json
.qoder-plugin/*.json
.codebuddy-plugin/*.json
.codex-plugin/*.json
scripts/commands-manifest.txt
scripts/validate.py'

# evidence_digest: a stable fingerprint of validate.py's tracked inputs, from WORKING-TREE
# content (so an uncommitted edit is caught). `git hash-object` is content-addressed — same
# bytes, same hash, on any machine — and keeps the envelope inside git (no sha256sum dep). The
# per-file hashes are sorted so ordering never perturbs the digest, then hashed as one blob.
# This is why the SHA-anchor design was abandoned: a fingerprint cannot be fooled by commit
# order, has no same-commit off-by-one (commits don't change content), and needs no anchor.
evidence_digest() {
  # Disable globbing while splitting the pattern list: '*.md' must reach `git ls-files` as a
  # (recursive) PATHSPEC, not be expanded by the shell against the cwd first — in a directory
  # that happens to contain a top-level .md, an unquoted '*.md' globs to that one file and the
  # recursive match silently collapses. `set -- $LIST` under `set -f` passes them verbatim.
  set -f
  # shellcheck disable=SC2086
  set -- $GATE_RELEVANT_PATHS
  set +f
  # Zero matches must NOT fall through to `git hash-object --stdin` on empty input: that
  # returns the FIXED empty-blob SHA e69de29b…, a constant that passes the header regex, so
  # row 7 would compare constant-to-constant and PASS vacuously — an adopter whose layout does
  # not fit GATE_RELEVANT_PATHS would silently green, the exact silent-degrade this check
  # removes. Emit a non-hex sentinel instead; the gate rejects it loudly (row 7).
  if [ -z "$(git ls-files -z -- "$@" 2>/dev/null | tr -d '\0')" ]; then
    printf 'EMPTY-no-gate-relevant-paths-matched\n'
    return 0
  fi
  git ls-files -z -- "$@" 2>/dev/null \
    | while IFS= read -r -d '' _f; do
        printf '%s %s\n' "$(git hash-object "$_f" 2>/dev/null || echo MISSING)" "$_f"
      done \
    | LC_ALL=C sort \
    | git hash-object --stdin
}

# The header the runner must write as the evidence file's first line. ONE definition, emitted
# by the `evidence-header` subcommand below and re-derived by row 7 — the runner and the gate
# can never drift because they call the same function.
evidence_header() { printf '# plc-gate-evidence inputs=%s\n' "$(evidence_digest)"; }

# Subcommand: print just the header, so the runner can prepend it. Runs BEFORE the phase/
# manifest requirements — producing evidence must not itself need a configured manifest.
if [ "${1:-}" = evidence-header ]; then evidence_header; exit 0; fi

MODE="${1:?usage: close-gate.sh <task|phase> X.Y}"
PHASE="${2:-}"
# two modes. `task` (per-commit, run by the pre-push hook on every push) gates the
# per-task subset — product-tree change + this task's journal FACT + fresh test-evidence +
# declared invariants — so a phase's first completed task is pushable the moment it exists,
# reconciling SKILL.md's push-immediate rule with the gate that used to demand phase-close
# artifacts on commit one. `phase` (run before PR-merge) additionally requires the phase-close
# artifacts: CHANGELOG [Unreleased], spec + plan docs, and the ROADMAP row. The un-bypassable
# pre-push layer is not weakened — it still runs on every push; only its scope now matches the
# push moment (a task) instead of demanding a whole phase up front.
case "$MODE" in
  task|phase) ;;
  *) echo "✗ mode must be 'task' (per-commit, pre-push) or 'phase' (phase close) — got '$MODE'"; exit 1 ;;
esac
[ -n "$PHASE" ] || { echo "✗ $MODE mode needs a PHASE arg (e.g. close-gate.sh $MODE X.Y-X.Z)"; exit 1; }

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
#
# ⚠ mtime IS NOT EVIDENCE OF CONTENT, and under a sync daemon it is barely evidence
# of anything at all: such a daemon rewrites and re-touches
# files it did not change. A freshness-only row
# here false-PASSES *by construction*, not by accident: a gate can print
# `✓ ROADMAP.md updated this phase` while a grep for the phase identifier returns 0.
# So: where the artifact's CONTENT can be checked, check the content — `fresh()` is only
# for rows where nothing but recency is being claimed, and those rows must SAY so in their
# ✓ text. Do not reintroduce `fresh`-only as proof that a ceremony was performed.
fresh() { [ -e "$1" ] && [ -e "$2" ] && [ -n "$(find "$1" -newer "$2" -print 2>/dev/null)" ]; }

# Stamp a temp file's mtime to a commit's committer-date. --date=format-LOCAL renders the digits
# in THIS machine's timezone — exactly how `touch -t` interprets them. (Plain --date=format:
# renders in the commit's OWN offset, which touch -t then misreads as local time — a cross-tz
# freshness bug that can false-PASS stale docs or false-FAIL fresh ones. format-local sidesteps
# it and stays BSD-touch-safe, unlike a GNU-only `touch -d @epoch`.)
#
# ⚠ `touch -t` accepts whole seconds only, so the stamped mtime is the committer-date TRUNCATED
# down to its second. A file written earlier in that same second carries a larger sub-second mtime
# and so reads `fresh` — a ≤1s fail-OPEN window. Benign for the ONLY remaining consumer, BPREF
# (the branch-point commit): a phase artifact is written after `git checkout -b`, never within the
# same second as the merge-base commit it is compared against, so the tie cannot occur in a real
# run. The row where the window WAS reachable (test-evidence, once compared to a HEAD-second ref)
# no longer uses mtime at all — it fingerprints content (row 7). If a future `fresh()` consumer
# ever compares against a reference that CAN fall within 1s of the artifact, give it sub-second
# resolution instead of `touch -t` (e.g. a feature-detected GNU `touch -d @<epoch.frac>`); do not
# assume this truncation stays harmless.
stamp_ref() { touch -t "$(git show -s --format=%cd --date=format-local:%Y%m%d%H%M.%S "$1")" "$2"; }

# Branch-point ref: a docs artifact written DURING this phase is newer than the commit the branch
# forked from. Fail CLOSED if origin/main can't be resolved — the old genesis-commit fallback made
# every freshness check trivially pass (anything postdates the repo's first commit → false PASS).
BP="$(git merge-base origin/main HEAD 2>/dev/null || true)"
[ -n "$BP" ] || { echo "✗ cannot resolve 'git merge-base origin/main HEAD' — fetch origin/main before running the gate"; exit 1; }
# --- The gate publishes its own completion signal ------------------------------------
# hooks/tasklist-first.sh used to detect "a close gate ran" by word-matching a bare gate-script
# token in ANY Bash command, so `wc -l` on this file and `git add` of this file each counted as
# a phase close — observed live, repeatedly, including while this very check was being
# written. Reading a file about the gate is not the gate running, and nothing about a token scan
# can tell the two apart. The gate is a script this project owns, so it states the fact rather
# than being guessed at.
#
# Deliberately NOT an mtime, and not "the file exists": a checked-out tree may live under a file-syncing
# directory whose daemon re-touches files (the same reasoning drove the
# nonce in hooks/tasklist-first.sh). Identity comes from a per-RUN id the reader compares against
# what it last saw, so a marker left by an earlier run cannot be mistaken for a new one.
#
# Both outcomes are recorded, with the exit code. A gate that RAN AND FAILED is a different fact
# from a gate that never ran, and flattening the two is the defect this check exists to remove —
# the consumer decides what to do with each. (Today: hooks/tasklist-first.sh re-arms only on
# exit=0.)
GATE_RUN_DIR=".claude/.gate-runs"
GATE_MARKER="$GATE_RUN_DIR/last-run"
GATE_RUN_ID="$$-$(date +%s 2>/dev/null || echo 0)"
write_gate_marker() {
  _ec="${1:-1}"
  mkdir -p "$GATE_RUN_DIR" 2>/dev/null || return 0
  # The directory ships its OWN ignore entry — the pytest / mypy / husky pattern — so an adopter
  # never commits machine-local run state without having to edit anything first.
  [ -s "$GATE_RUN_DIR/.gitignore" ] || printf '*\n' > "$GATE_RUN_DIR/.gitignore" 2>/dev/null || true
  _tmp="$GATE_MARKER.$$.tmp"
  {
    printf 'run=%s\n'   "$GATE_RUN_ID"
    printf 'exit=%s\n'  "$_ec"
    printf 'phase=%s\n' "$PHASE"
    printf 'head=%s\n'  "$(git rev-parse HEAD 2>/dev/null || echo unknown)"
    printf 'at=%s\n'    "$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)"
  } > "$_tmp" 2>/dev/null || { rm -f "$_tmp" 2>/dev/null || true; return 0; }
  # write-temp-then-rename: POSIX rename() is atomic and keeps the destination name visible
  # throughout, so a reader sees either the previous marker or the new one, never a partial file.
  mv -f "$_tmp" "$GATE_MARKER" 2>/dev/null || rm -f "$_tmp" 2>/dev/null || true
}

# register the cleanup trap right after the mktemp so a later abort can't leak the temp file.
# `_gec=$?` MUST be the trap's first statement — anything before it clobbers the status being
# recorded. The trap (rather than a line at each exit point) is what makes the marker survive an
# early `set -e` abort or a signal: those paths are exactly the ones a final-line write misses.
BPREF="$(mktemp)"; trap '_gec=$?; write_gate_marker "$_gec"; rm -f "$BPREF"' EXIT
stamp_ref "$BP" "$BPREF"
# (A HEAD-committer-date ref used to be stamped here for the test-evidence row's mtime freshness
# check. That row now compares a content fingerprint instead (row 7), so the HEAD ref had
# no remaining reader and was removed: a stamped reference that nothing consumes reads as a check
# that still runs when it does not — the exact honest-guards defect this design removes.)

RANGE="origin/main..HEAD"

# skip-escape-hatch: an exempt_* flag is only legit if a 'SKIP: <reason>' line is in the newest journal.
JD="$(g retention.journal_dir)"; JD="${JD:-docs/journal.d}"
# `|| true` on BOTH the pipeline and the assignment: with no *.md fragment (brand-new phase, or
# the dir absent), the glob doesn't expand, `ls` exits non-zero, and under `pipefail` the pipeline
# reports that — an unguarded `J="$(...)"` under `set -e` would then kill the script silently,
# before any ✗ row prints, on the exact "journal not written yet" case the gate must report.
newest_journal() { ls -t "$JD"/*.md 2>/dev/null | head -1 || true; }
# Prefer the fragment that NAMES this phase over the merely-newest one. `ls -t` is an mtime
# proxy for "the fragment this phase wrote", and it is wrong whenever a fragment from another
# phase is newer — a leftover, a parallel branch, or a sync-daemon re-touch. When that happens the
# FACT-field and Plan-deviations rows below are judged against the WRONG file, which can both
# false-FAIL a correct phase and false-PASS an incomplete one. Fragments are named
# `<date>-phase-<PHASE>-<slug>.md`, so identity is available; use it, and keep `ls -t` only as
# the fallback for projects whose fragments predate that convention.
# Within ONE phase's fragments, take the LAST BY NAME — not `head -1` (which took the
# earliest, so a phase that wrote a stub early and its real FACT entry later was judged on
# the stub) and deliberately not `ls -t`. Fragments are `<date>-phase-<id>-<slug>.md`, so the
# name already carries the ordering, and a name is something a background sync daemon cannot
# rewrite. Using mtime to order a phase's own fragments would reintroduce exactly the
# dependence this gate is being cured of.
phase_journal() { ls "$JD"/*phase-"$PHASE"-*.md 2>/dev/null | tail -1 || true; }
J="$(phase_journal || true)"
# FALLBACK IS NOT A SUBSTITUTE. If the phase has no fragment of its own, `ls -t` picks the
# newest fragment belonging to some OTHER phase, and every row below then judges that file —
# printing ✓ FACT / ✓ Plan-deviations for a phase that wrote no journal at all. The fallback
# exists only for repos whose fragments predate the `-phase-<id>-` naming convention, so it
# is allowed ONLY when no fragment in the directory carries that convention at all. Anything
# else is a missing journal, and must be reported as one.
JFALLBACK=0
# `*phase-*` (no trailing `-*`): a slugless `<date>-phase-<id>.md` still USES the
# convention, and requiring a slug sent it to the fallback the narrowing exists to stop.
if [ -z "$J" ] && ! ls "$JD"/*phase-*.md >/dev/null 2>&1; then
  J="$(newest_journal || true)"
  [ -n "$J" ] && JFALLBACK=1
fi
skip_logged() { [ -n "$J" ] && grep -qE '^[[:space:]]*SKIP:' "$J" 2>/dev/null; }

echo "── close-gate $MODE $PHASE (gitignored-docs mode) ──"

# 1. the phase's diff touched the product tree (content check, not commit verb).
#    The old `feat|fix` commit-verb test was a proxy: the deliverable here IS markdown under
#    skills/**, so a legit refactor-only phase (e.g. a skill-content-only phase) had to be mislabeled
#    `feat` to pass. Path-based asks the real question — did this phase change the product — so a
#    meta-only README typo correctly fails while an honest `refactor(skill):` passes. Paths are
#    manifest-driven (.product_paths[]) so an adopter with a different tree sets their own; an
#    absent key falls back to this repo's default, a malformed key fails closed. Same
#    `grep -c … -gt 0` (not `grep -q`) idiom check #2 uses, for the pipefail/SIGPIPE reason below.
# Gate on the JSON *type* first: `.product_paths[]?` also iterates an OBJECT's values, so a
# `{"a":"skills/"}` typo would silently run on those instead of failing closed. Only a non-empty
# ARRAY takes the read branch; absent key (type "null") → default; anything else → fail-closed.
PP_TYPE="$(jq -r '.product_paths | type' "$M" 2>/dev/null || echo null)"
if [ "$PP_TYPE" = array ] && PP_LIST="$(jq -r '.product_paths[]' "$M" 2>/dev/null)" && [ -n "$PP_LIST" ]; then
  # dir prefixes → strip trailing slash, escape EVERY ERE metachar (not just `.`, so an adopter
  # path like `c++/` or `app(v2)/` can't reach grep -E raw and false-FAIL), join with `|`.
  PP_ALT="$(printf '%s\n' "$PP_LIST" | sed -e 's#/*$##' -e 's#[][(){}.^$*+?|\\]#\\&#g' | paste -sd'|' -)"
elif [ "$PP_TYPE" = null ]; then
  PP_ALT='skills|commands|scripts|\.claude-plugin'   # absent key → this repo's default tree
else
  PP_ALT=""   # present but not a non-empty array (object / string / empty array) → fail-closed
fi
if [ -z "$PP_ALT" ]; then
  bad "product_paths present in manifest but empty or not a JSON array — fix the manifest"
elif [ "$(git diff --name-only "$RANGE" 2>/dev/null | grep -cE "^(${PP_ALT})/" || true)" -gt 0 ]; then
  ok "phase diff touches the product tree ($RANGE)"
else bad "no product-tree change in $RANGE — a phase must ship a product change (paths: ${PP_ALT})"; fi

# 2 + 3 + 4 are PHASE-CLOSE artifacts: a CHANGELOG [Unreleased] entry, and the spec + plan
# docs. A single cadence task does not produce them, so `task` mode (per-commit, pre-push) skips
# this block; only `phase` mode (pre-merge) requires them.
if [ "$MODE" = phase ]; then
# 2. CHANGELOG.md [Unreleased] touched in range (tracked → git check).
if [ "$(g exempt_changelog)" = true ]; then
  skip_logged && ok "changelog exempt (SKIP: logged)" || bad "exempt_changelog=true but no 'SKIP:' line in newest journal"
elif [ "$(git diff --name-only "$RANGE" 2>/dev/null | grep -cE '^CHANGELOG\.md$' || true)" -gt 0 ]; then
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
fi  # end phase-only (checks 2-4)

# 5. newest journal.d fragment: exists + fresh-vs-branch-point + FACT fields + Plan-deviations.
if [ -z "$J" ]; then
  bad "no journal fragment matching '*phase-$PHASE-*.md' under $JD/ — write this phase's FACT entry"
else
  [ "$JFALLBACK" = 1 ] && warn "no '-phase-<id>-' fragment names exist in $JD/ — falling back to the newest file ($(basename "$J")); its rows below are judged by mtime, not by phase identity"
  fresh "$J" "$BPREF" && ok "journal fragment newer than the branch point, by mtime ($(basename "$J"))" \
    || bad "journal fragment $(basename "$J") is older than the branch point — write this phase's FACT entry"
  MISS=""
  for f in Decision Why Backing; do
    grep -qE "^[[:space:]]*[-*][[:space:]]+\*\*${f}:?\*\*" "$J" || MISS="$MISS $f"
  done
  [ -z "$MISS" ] && ok "journal FACT fields present (Decision/Why/Backing)" || bad "journal FACT entry missing field(s):$MISS"
  grep -qE '\*\*Plan deviations:?\*\*|^#{1,4}[[:space:]]*Plan deviations' "$J" \
    && ok "journal 'Plan deviations' header present" || bad "journal missing 'Plan deviations' header"
fi

# 6. ROADMAP.md exists + NAMES THIS PHASE (LOCAL file — gitignored).
# TWO independent facts, both required — content AND recency.
#
#   content: the ceremony this row claims ("the roadmap reflects this phase") is only
#     observable in the file's text, so grep for the phase id.
#   recency: content alone is pre-satisfied by any row written in an EARLIER phase. Every
#     `planned` row in a real roadmap already names a phase that has not started, so a
#     content-only check greens before the work exists. (Regression: the first version of
#     this row REPLACED the freshness check instead of AND-ing with it, and its own failure
#     message still pointed at a fresh() call that no longer ran.)
#
# The match is ANCHORED, not a bare substring: `grep -F` disables regex, it does NOT make a
# match whole-token, so `N9` matched a roadmap containing only `N99`. Real collisions in a
# namespace like this: N3 in N33/N34, N4 in N44..N49, N5 in N50. Require a non-identifier
# character (or a line edge) on both sides. `[^0-9A-Za-z._-]` keeps `N48-N50` matchable as a
# whole while rejecting `N4` against `N48`. TWO DELIBERATE CONSEQUENCES, both verified:
# (a) an id ending a sentence (`... see N57.`) does NOT match, because `.` is excluded on
#     purpose — that exclusion is what keeps `1.2` out of `1.2.1`;
# (b) a GROUPED row (`| N51–N56 |`) does not satisfy its members — closing a bundled
#     phase means naming the bundle in the roadmap, which is the honest record anyway. grep -E is ERE, so the escape class must cover the ERE metacharacters
# (`+ ? ( ) { } |`) as well as the BRE ones — an id like `B|C` would otherwise be read as an
# alternation and match an unrelated row. No GNU-only `\b` (BSD grep).
# PHASE-CLOSE artifact: flipping the ROADMAP row is a phase-boundary act, not a per-task one,
# so `task` mode skips it; only `phase` mode requires it.
if [ "$MODE" = phase ]; then
if [ -f docs/ROADMAP.md ]; then
  if ! grep -qE "(^|[^0-9A-Za-z._-])$(printf '%s' "$PHASE" | sed 's/[][\.*^$/&+?(){}|]/\\&/g')([^0-9A-Za-z._-]|$)" docs/ROADMAP.md; then
    bad "docs/ROADMAP.md never mentions phase $PHASE — add its row and flip ✅/▶"
  elif ! fresh docs/ROADMAP.md "$BPREF"; then
    bad "docs/ROADMAP.md names phase $PHASE but has not been touched since the branch point — the row predates this phase, so it proves nothing about it"
  else
    ok "ROADMAP.md names phase $PHASE and was updated this phase"
  fi
else bad "docs/ROADMAP.md missing"; fi
fi  # end phase-only (check 6)

# 7. non-empty test-evidence that DEMONSTRABLY describes the current tree.
#    The gate does NOT run validate.py itself (jq-only envelope); the runner writes evidence,
#    the gate checks it. Skipped only when the manifest configures no test_evidence.
#
#    ⚠ This row used to be `fresh "$EV" "$HEADREF"` — evidence mtime vs HEAD's committer-date.
#    mtime is not evidence of content, and in THIS tree it is barely evidence of anything: git
#    does not preserve mtime across checkout, and a cloud-sync daemon re-touches files in place.
#    The row's own ✓ text conceded it proved "recency only". It now checks CONTENT: the runner
#    stamps a fingerprint of validate.py's inputs into the evidence header (evidence_header,
#    top of file); the gate recomputes it and compares. Do not reintroduce an mtime compare.
EV="$(g test_evidence)"
# The one command that produces a valid evidence file. Quoted in every failure message so a
# reader never reconstructs the header by hand — the header is this row's contract, and a
# contract nobody is told how to satisfy is a trap, not a gate. It calls the SAME subcommand
# the gate uses, so the two can never disagree about how the fingerprint is computed.
EVIDENCE_CMD="{ bash scripts/close-gate.sh evidence-header; python3 scripts/validate.py 2>&1; } | tee ${EV:-<evidence-file>}"
if [ -z "$EV" ]; then
  warn "no test_evidence configured in manifest — skipping the test-ran check"
elif [ ! -s "$EV" ]; then
  bad "empty/missing test-evidence $EV — run: $EVIDENCE_CMD"
else
  # First line must be the fingerprint header. A missing/garbled header is a HARD fail, never a
  # fallback to a weaker check: silently degrading is the defect class this check removes.
  EVDIG="$(sed -n '1s/^# plc-gate-evidence inputs=\([0-9a-f]\{40,64\}\)[[:space:]]*$/\1/p' "$EV" 2>/dev/null)"
  NOWDIG="$(evidence_digest)"
  if [ "${NOWDIG#EMPTY-}" != "$NOWDIG" ]; then
    # evidence_digest signalled that ZERO gate-relevant paths matched. Never a pass — a gate
    # that fingerprints nothing checks nothing. Loud, so a mis-scoped GATE_RELEVANT_PATHS (or a
    # repo restructure that renamed the manifests) surfaces instead of greening vacuously.
    bad "no gate-relevant paths matched in this repo — the gate's GATE_RELEVANT_PATHS list does not fit this layout, so the test-evidence fingerprint checks nothing. Fix the list before trusting this row."
  elif [ -z "$EVDIG" ]; then
    bad "test-evidence $EV has no '# plc-gate-evidence inputs=<digest>' first line — regenerate it: $EVIDENCE_CMD"
  elif [ "$EVDIG" = "$NOWDIG" ]; then
    ok "test-evidence non-empty and its input fingerprint matches the current tree ($EV)"
  else
    bad "test-evidence $EV is stale — a path validate.py reads has changed since it was generated (fingerprint $(printf '%.12s' "$EVDIG")… ≠ $(printf '%.12s' "$NOWDIG")…) — re-run: $EVIDENCE_CMD"
  fi
fi

# 8. declared repo-integrity invariants: the gate does not just check that artifacts
#    exist — it RUNS every invariant the manifest declares. jq reads invariants[]; each
#    .command is executed and a non-zero exit is a FAIL. This is what closes the loop the
#    seeded invariants opened: a mechanism that is declared but never run is a
#    claim, not a gate (ROADMAP load-bearing invariant).
#    Fail-CLOSED at every seam: an unreadable/malformed manifest, a non-array invariants
#    value, or an entry that isn't an object / is missing its name/command, is a ✗ — never
#    a silent skip that would let a broken invariant slip by. Every jq read is guarded with
#    a sentinel fallback so a bad SHAPE produces a graceful ✗ row, not a raw jq trace + a
#    `set -e` abort that truncates the remaining invariants (the crash-under-set-e lesson
#    already learned in scripts/invariants/manifest-version-sync.sh, earlier commits).
#    Envelope stays jq-only: the invariant COMMANDS may use git/grep/etc., but the gate's
#    own iteration is pure jq + bash (no python3).
#    TRUST BOUNDARY: `eval "$CMD"` runs a string straight from the git-tracked manifest, so a
#    manifest edit is arbitrary-code-execution-equivalent — review `.command` changes with the
#    same care as a script change. Deliberate: the manifest is PR-reviewed repo config, same
#    trust tier as scripts/*.sh, and this gate is local dev-time only (never fed untrusted input).
if ! INV_JSON="$(jq -c '.invariants // []' "$M" 2>/dev/null)"; then
  bad "invariants[]: manifest unreadable or malformed JSON — cannot run declared invariants"
else
  # `.invariants` present-but-not-an-array (e.g. a `"invariants": true` typo) would make a bare
  # `jq length` error out under set -e; map any non-array to -1 and report it, don't crash.
  INV_COUNT="$(printf '%s' "$INV_JSON" | jq 'if type=="array" then length else -1 end' 2>/dev/null)" || INV_COUNT=-1
  if [ "${INV_COUNT:--1}" -lt 0 ]; then
    bad "invariants[] is present but not a JSON array — fix the manifest"
  elif [ "$INV_COUNT" -eq 0 ]; then
    warn "no invariants declared in manifest — skipping the invariants run"
  else
    i=0
    while [ "$i" -lt "$INV_COUNT" ]; do
      # an array element that isn't an object (a stray string/number) makes `.[$i].name` error
      # under set -e; the `if (.[i]|type)=="object"` wrapper + `|| __ERR__` fallback turns that
      # into the malformed-entry ✗ row instead of a script abort that skips later invariants.
      NAME="$(printf '%s' "$INV_JSON" | jq -r "if (.[$i]|type)==\"object\" then (.[$i].name // \"\") else \"__ERR__\" end" 2>/dev/null)" || NAME="__ERR__"
      CMD="$(printf  '%s' "$INV_JSON" | jq -r "if (.[$i]|type)==\"object\" then (.[$i].command // \"\") else \"__ERR__\" end" 2>/dev/null)" || CMD="__ERR__"
      if [ "$NAME" = "__ERR__" ] || [ "$CMD" = "__ERR__" ] || [ -z "$NAME" ] || [ -z "$CMD" ]; then
        bad "invariant #$i is malformed (not an object, or missing name/command) — fix the manifest"
      # run the declared command in a subshell so its own `set -e`/cwd can't leak into the
      # gate; suppress its chatter (the ✗ row names the command to re-run for detail).
      elif ( eval "$CMD" ) >/dev/null 2>&1; then
        ok "invariant '$NAME' holds"
      else
        bad "invariant '$NAME' FAILED — \`$CMD\` exited non-zero (run it directly to see why)"
      fi
      i=$((i+1))
    done
  fi
fi

echo "──"
[ $fail -eq 0 ] && { echo "✓ close-gate PASS ($MODE $PHASE)"; exit 0; } \
                || { echo "✗ close-gate FAIL ($MODE $PHASE) — fix the ✗ rows above, then re-run"; exit 1; }
