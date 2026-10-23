#!/usr/bin/env bash
# growth-declares-a-deletion.sh.
#
# WHAT THIS ASSERTS: when a branch grows one of three counted surfaces relative to its merge
# base, the branch carries a line saying what was removed to pay for it, or why nothing could be.
# Per surface, the sum of declared growth must be at least the measured growth.
#
#   GROWTH: <surface> +<N> deleted: <what was removed>
#   GROWTH: <surface> +<N> cannot-delete: <why nothing could be removed>
#
# <surface> is exactly one of: references | commands | steps
#
# WHY IT EXISTS. Every other gate in this repository fires when something is MISSING -- no journal
# fragment, no spec, no ROADMAP row, no test evidence. Nothing fired when a phase ADDED a census
# row, a reference or a command, so monotonic growth was the mechanism's guaranteed output rather
# than an accident: one-off slimming passes do not hold without a standing mechanism.
#
# SCOPE OF THE WORD `steps`. This counter reads the census in references/step-enforcement.md, so
# `steps` means CENSUS ROWS, not "steps a human performs". A new SKILL.md requirement that never
# gets a row adds no growth here (step-enforcement-table-current.sh is what reds for that), and
# backfilling a row for an old requirement shows up as growth. Stated because the shorter phrasing
# "a phase that adds a step" overreaches by one level.
#
# WHAT THIS DOES NOT ASSERT, stated here because this phase's own subject is a claim wider than
# its mechanism:
#   * It never checks a declaration is TRUE. `GROWTH: references +1 deleted: nothing, actually`
#     passes. Judging the content is a different job and nothing currently does it.
#   * It never counts lines. A phase can add three thousand lines to existing files and stay green.
#     That exclusion is deliberate, not an oversight -- see the LINES ARE NOT COUNTED note below.
#   * Blocking points -- the weight the user actually reports -- are invisible to it. They have only ever been counted in prose;
#     no artifact holds that number, so no script can read it.
#     Making it readable is a separate job, not this one's.
#   * It does not confirm the named deletion ever existed. The declaration names what was removed;
#     nothing here looks for it.
#   * Surfaces are ENUMERATED below, not discovered. A future skills/project-lifecycle/playbooks/
#     directory grows uncounted until somebody adds a fourth counter here by hand.
#   * Both sides are read from git, so an UNTRACKED new reference is invisible. That is deliberate
#     -- an unadded file does not ship in the PR -- but it means `find`-based counts and this
#     check's counts can legitimately disagree on a dirty tree.
#   * A GROWTH-shaped line pasted into a journal fragment as an example is indistinguishable from
#     a real declaration, including one inside a fenced code block. The scan is narrowed to this
#     branch's docs/journal.d fragments and the commit range for exactly that reason, but inside
#     those two sources it cannot tell prose from a claim.
#   * An UNTRACKED journal fragment is accepted, so a declaration that never ships can green a
#     LOCAL run. The push path is unaffected, because by then it is committed. This is the one
#     deliberate asymmetry with the counted surfaces, which read the index; the reason is at
#     `branch_journal_fragments`.
#   * NET ZERO RECORDS NOTHING. A phase that adds five references and removes five others has a
#     delta of zero on that surface and owes no declaration, so nothing is written down about
#     either half. "Records what it cost" is true of net growth only. Making every churn declare
#     itself is a different and much noisier rule than the one this gate was asked for.
#
# EXIT: 0 pass | 1 the repository is wrong | 3 could not run.
# Exit 3 never folds into 0. A check that could not run must not report as though it did.
#
# ENVELOPE: bash 3.2 + git + awk/grep/sed/sort. No python3, no jq (the gate's dependency envelope
# is held by scripts/invariants/gate-jq-only-envelope.sh). No bash-4 constructs: no associative
# arrays, which is why the three surfaces are walked as a space-separated list rather than a map.
#
# OUTPUT: every failure prints a stable FAIL[<slug>] code as its first token. The close gate runs
# invariants as ( eval "$CMD" ) >/dev/null 2>&1 and prints only "run it directly to see why", so
# this text exists for the person who runs it directly -- and the codes exist so a test can assert
# WHICH check fired rather than merely that something did.
set -u

CANNOT_RUN_RC=3

cannot_run() { printf 'CANNOT-RUN[%s] %s\n' "$1" "$2" >&2; exit "$CANNOT_RUN_RC"; }
fail()       { printf 'FAIL[%s] %s\n' "$1" "$2" >&2; exit 1; }

# Root resolution uses bash parameter expansion, NOT `dirname`, and that is a measured choice.
# `dirname` is an external command: with a stripped PATH the sibling idiom prints
# "dirname: command not found", resolves ROOT to `/`, and only then reaches the no-git check --
# so the script reported the right exit code by accident, after silently running against the
# wrong directory. Caught by this check's own test, not by reading.
SELF_DIR="${BASH_SOURCE[0]%/*}"
[ "$SELF_DIR" = "${BASH_SOURCE[0]}" ] && SELF_DIR="."
ROOT="$(cd "$SELF_DIR/../.." && pwd)" || cannot_run "no-root" "cannot resolve repo root"
cd "$ROOT" || cannot_run "no-root" "cannot cd to $ROOT"

command -v git >/dev/null 2>&1 || cannot_run "no-git" "git is not on PATH"
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || cannot_run "not-a-worktree" "$ROOT is not inside a work tree"

TABLE="skills/project-lifecycle/references/step-enforcement.md"
JOURNAL_DIR="docs/journal.d"

# The three counted surfaces. Walked as a list because bash 3.2 has no associative arrays.
SURFACES="references commands steps"

# ---------------------------------------------------------------- merge base
# Same fallback chain as scripts/invariants/step-enforcement-table-current.sh. Neither resolving
# is CANNOT-RUN: a check that cannot find its baseline has not passed, it has not run. On main,
# the merge base IS head, every delta is 0, and this exits 0 without reading a declaration.
BASE="$(git merge-base origin/HEAD HEAD 2>/dev/null || git merge-base origin/main HEAD 2>/dev/null || true)"
[ -n "$BASE" ] || cannot_run "no-merge-base" "cannot resolve a merge base against origin/HEAD or origin/main"
git cat-file -e "$BASE^{commit}" 2>/dev/null || cannot_run "bad-merge-base" "$BASE is not a commit"

# ---------------------------------------------------------------- counters
#
# LINES ARE NOT COUNTED, AND THIS IS THE LINE WHERE A FUTURE READER WOULD ADD THEM.
# Do not. A decidable predicate for "is this resident prose available on demand elsewhere?"
# was swept over SKILL.md: almost none of the prose qualified, and the largest candidate (the
# References section) qualified nowhere. The prose face has been measured and there is almost no water in
# it. A line counter aims this gate at the one direction the repository already falsified, and
# reds on a pure rewording, which is noise rather than growth. The weight lives in the number
# of surfaces and the number of human blocking points, not in the width of the sentences.

# ONE path listing and ONE filter per surface, applied to BOTH sides.
#
# This shape is not stylistic. The first version of this check listed the HEAD side with
# `git ls-files -- 'skills/*/references/*.md'` and the base side with `git ls-tree` plus a
# regex. Its FIRST RUN reported `references` growing on a branch that had not touched a
# single reference: a git pathspec glob is not path-aware, so `*/` matched across directory
# separators and swallowed test-fixture `input.md` files nested under
# references/roadmap-format/fixtures/. Two implementations of "is this a reference file"
# disagreed -- the exact defect the `steps` counter's note below says it avoided by reading
# declared numbers. It reproduced here, in the same file.
#
# So: list paths with git (tree-side by sha, HEAD-side from the index), then filter both with the
# SAME extended regex, which IS path-aware.
# `core.quotePath=off` is REQUIRED, not hygiene. With git's default, a path holding any byte
# outside ASCII is printed wrapped in double quotes with octal escapes --
# "skills/project-lifecycle/references/\303\251t\303\251.md" -- so a `^skills` anchor never
# matches it, on either side. A probe showed: adding and staging a reference
# with a non-ASCII name produced `references 4 -> 4` and exit 0, while the ASCII control produced
# exit 1. A counter blind to a whole class of filename is a counter that greens on real growth.
list_paths() {  # $1 = "HEAD" | <base-sha>
  if [ "$1" = "HEAD" ]; then
    git -c core.quotePath=off ls-files
  else
    git -c core.quotePath=off ls-tree -r --name-only "$1"
  fi
}

# Count one filtered surface, FAILING rather than returning zero when the listing itself failed.
#
# The first version was `list_paths "$1" | grep -cE '<re>' || true`. In a pipeline the status
# belongs to grep, so a broken `git ls-files` became "0 matches", and 0 at HEAD against a real
# count at base reads as a clean SHRINK -- which needs no declaration and exits 0. A probe showed:
# with `.git/index` corrupted after staging an add, the check printed
# `references 4 -> 0 | commands 2 -> 0` and PASSED. That is the could-not-run-folds-into-pass
# class this script's own EXIT contract says it does not have. The listing is now captured first,
# its status checked, and emptiness treated as a failure -- a git work tree with no files at all is
# not a state this repository can be in, so an empty listing means the read broke.
count_filtered() {  # $1 = ERE, $2 = "HEAD" | <base-sha>
  _paths="$(list_paths "$2")" || return 1
  [ -n "$_paths" ] || return 1
  printf '%s\n' "$_paths" | /usr/bin/grep -cE "$1" || true
}

# *.md DIRECTLY under any skills/*/references/ directory. Anything deeper is a fixture or a
# sub-asset, not a reference a reader has to find.
count_references() {  # $1 = "HEAD" | <base-sha>
  count_filtered '^skills/[^/]+/references/[^/]+\.md$' "$1"
}

# *.md DIRECTLY under commands/.
count_commands() {  # $1 = "HEAD" | <base-sha>
  count_filtered '^commands/[^/]+\.md$' "$1"
}

# steps: the sum of the THREE DECLARED band counts in the step -> enforcement table.
#
# It reads the DECLARED numbers rather than counting the rows itself, and that is a deliberate
# dependency rather than laziness. scripts/invariants/step-enforcement-table-current.sh already
# asserts declared == actual for every band and reds otherwise, so the declared numbers are the
# single source and re-counting here would be a SECOND implementation of one predicate -- which a
# tracked invariant in this repository forbids. It is also the mistake that was actually made while
# designing this check: an ad-hoc row count disagreed with the declared counts,
# because it counted each band's header row. The duplicate implementation was wrong on its first run.
# BOTH SIDES COME FROM GIT, and the HEAD side is the INDEX (`git show :path`), not the working
# tree. That was a review finding, not a preference: reading the file with `cat` while references
# and commands read the index meant "both sides are read from git" was false for this one counter,
# and an unstaged table edit counted as growth while an unstaged reference did not. One source per
# side, same source for all three surfaces.
#
# The number is extracted from a STRICT `**N**` match rather than by stripping non-digits from the
# line. Stripping is what the sibling invariant does, and the review measured where it breaks: on
# `- Band C rows: **11** (was 10)` it yields 1110, a 1,099 phantom growth -- and the same mis-parse
# on the BASE side would hide real growth as a shrink. A format this parser cannot read is exit 3,
# which is visible, rather than a number that is wrong, which is not.
#
# The band letters are checked for being exactly one each of A, B and C. `/^- Band [ABC]/` with a
# bare `n==3` accepted `A, B, A` (double-counting one band) and ignored a future `- Band D` entirely
# (silently undercounting while staying green). Both were review findings.
declared_steps() {  # $1 = "HEAD" | <base-sha>
  if [ "$1" = "HEAD" ]; then
    git show ":$TABLE"
  else
    git show "$1:$TABLE"
  fi 2>/dev/null | /usr/bin/awk '
    /^- Band [A-Z] rows:/ {
      n++
      letter = $3
      if (letter !~ /^[ABC]$/)  { bad = 1 }
      else if (seen[letter]++)  { bad = 1 }
      else if (match($0, /\*\*[0-9]+\*\*/)) { sum += substr($0, RSTART + 2, RLENGTH - 4) }
      else                      { bad = 1 }
    }
    END { if (bad || n != 3) exit 1; print sum + 0 }
  '
}

count_surface() {  # $1 = surface, $2 = "HEAD" | <base-sha>
  case "$1" in
    references) count_references "$2" ;;
    commands)   count_commands   "$2" ;;
    steps)      declared_steps   "$2" ;;
    *)          return 1 ;;
  esac
}

# ---------------------------------------------------------------- declarations
#
# One predicate, two text sources -- not two implementations of one predicate. The journal
# fragment is where this repository already keeps SKIP: lines, so the convention is familiar. The
# commit range exists because declared invariants run on EVERY branch, always,
# so a docs branch with no journal fragment would otherwise be structurally unable to
# satisfy a check that still runs on it, and an unsatisfiable guard is one people route around
# with --no-verify.
# FRAGMENTS ARE SCOPED TO THIS BRANCH, not to the directory. `find docs/journal.d -name '*.md'`
# reads every fragment sitting in the tree, and fragments from already-merged phases stay there
# until the next retention drain, so that directory can grow large.
# The review probed it: a base commit carrying `GROWTH: references +5` from an
# older phase let a new branch add a reference with no declaration at all and exit 0. Worse, the
# line THIS phase writes becomes that payer for the next phase the moment it merges. So the pool is
# the fragments this branch added or modified, plus untracked ones.
#
# Untracked fragments ARE included, deliberately and asymmetrically: the counted surfaces read the
# index, so an unadded reference does not count, while an unadded journal fragment does. The reason
# is the local workflow -- the fragment is usually written before it is committed, and a check that
# reds on your own freshly written declaration is a check you learn to skip. The consequence is
# stated in the non-guarantee list at the top: a declaration that never ships can green a local run.
# The push path is unaffected, because by then it is committed.
branch_journal_fragments() {
  git diff --name-only --diff-filter=AM "$BASE"...HEAD -- "$JOURNAL_DIR"
  git diff --name-only --diff-filter=AM -- "$JOURNAL_DIR"
  git diff --name-only --cached --diff-filter=AM -- "$JOURNAL_DIR"
  git ls-files --others --exclude-standard -- "$JOURNAL_DIR"
}

declaration_text() {
  branch_journal_fragments 2>/dev/null | /usr/bin/sort -u | while IFS= read -r _f; do
    [ -n "$_f" ] && [ -f "$_f" ] && /bin/cat "$_f"
  done
  git log --format=%B "$BASE"..HEAD 2>/dev/null || true
}

DECL="$(declaration_text)"

# Sum of declared growth for one surface. Two properties, both from review findings:
#
#   * The surface name is part of the match, so a declaration naming `commands` can never pay for
#     growth in `references`, and `references` never matches `references-extra`.
#   * IDENTICAL LINES ARE DEDUPLICATED. Summing every matching line meant the same declaration
#     written in both places the design invites -- the journal fragment AND a commit message --
#     counted twice, so `+1` written twice paid for a delta of 2 and the under-declaration check
#     was bypassed by copy-paste. Measured by the review. Two genuinely separate declarations need
#     two different reasons, or one line with the right number; identical text is one claim.
declared_for() {  # $1 = surface
  printf '%s\n' "$DECL" \
    | /usr/bin/tr -d '\r' \
    | /usr/bin/sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' \
    | /usr/bin/grep -E "^GROWTH:[[:space:]]+$1[[:space:]]+\+[0-9]+[[:space:]]+(deleted|cannot-delete):[[:space:]]*[^[:space:]]" \
    | /usr/bin/sort -u \
    | /usr/bin/awk '
        { line=$0; sub(/^[^+]*\+/,"",line); sub(/[^0-9].*$/,"",line); if (line != "") total += line }
        END { print total+0 }
      '
}

# ---------------------------------------------------------------- compare
VERDICT_LINES=""
GREW=0

for s in $SURFACES; do
  NOW="$(count_surface "$s" HEAD)"
  WAS="$(count_surface "$s" "$BASE")"

  case "$NOW" in ''|*[!0-9]*) cannot_run "unreadable-head-$s" "cannot count surface '$s' at HEAD" ;; esac
  case "$WAS" in ''|*[!0-9]*) cannot_run "unreadable-base-$s" "cannot count surface '$s' at $BASE" ;; esac

  DELTA=$((NOW - WAS))
  VERDICT_LINES="$VERDICT_LINES$s $WAS -> $NOW
"
  [ "$DELTA" -le 0 ] && continue
  GREW=1

  DECLARED="$(declared_for "$s")"
  case "$DECLARED" in ''|*[!0-9]*) DECLARED=0 ;; esac

  if [ "$DECLARED" -eq 0 ]; then
    fail "undeclared-growth" "surface '$s' grew by $DELTA ($WAS -> $NOW) and nothing declares it. Add a line to this branch's $JOURNAL_DIR fragment or to a commit message: 'GROWTH: $s +$DELTA deleted: <what was removed>' or 'GROWTH: $s +$DELTA cannot-delete: <why nothing could be removed>'"
  fi

  if [ "$DECLARED" -lt "$DELTA" ]; then
    fail "under-declared-growth" "surface '$s' grew by $DELTA ($WAS -> $NOW) but the declarations only account for $DECLARED. Raise the declared number to at least $DELTA, or add another GROWTH: $s line"
  fi
done

if [ "$GREW" -eq 0 ]; then
  printf 'PASS no counted surface grew against %s\n' "$(git rev-parse --short "$BASE" 2>/dev/null || echo "$BASE")"
else
  printf 'PASS every grown surface is declared (base %s)\n' "$(git rev-parse --short "$BASE" 2>/dev/null || echo "$BASE")"
fi
printf '%s' "$VERDICT_LINES"
exit 0
