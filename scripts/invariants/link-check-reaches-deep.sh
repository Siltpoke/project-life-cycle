#!/usr/bin/env bash
# Invariant: the link check reaches a file four path segments deep -- and the pre-fix
# invocation does NOT.
#
# WHY TWO ARMS. The requirement is only that the fixed form goes red on a deep broken link.
# An assertion that only checks that would pass for the wrong reason the moment something
# unrelated makes every run red, and would then be silently measuring nothing. The shallow
# arm is the negative control that keeps the positive one meaningful.
#
# A RUN THAT COULD NOT EXECUTE IS A FAILURE, NEVER A SKIP.
# No lychee, no temp dir, no pin file -> exit non-zero. Degrading to a quiet pass here would
# reproduce, inside the guard, the exact defect the guard exists to catch.
set -euo pipefail

NAME=link-check-reaches-deep
# Pure-bash parameter expansion, not the external `dirname` binary (measured):
# under a PATH that has no coreutils at all, `dirname` itself is unresolvable and this script
# died on the `cd`/source below -- before ever reaching the ensure-lychee.sh guard three lines
# down -- exiting nonzero but printing "No such file or directory", never "FAIL". That is the
# same defect one layer up: a "fail loudly" control silently dying upstream of its own designed
# guard because of an unexamined external-tool dependency. `${BASH_SOURCE[0]%/*}` needs nothing
# on PATH.
# NOT a drop-in equal of `dirname`, and the difference is the same defect class again: when
# BASH_SOURCE[0] contains NO slash (`cd scripts/invariants && bash link-check-reaches-deep.sh`)
# `dirname` yields `.` while `%/*` leaves the string untouched, so the cd becomes
# `<filename>/../..` -> "Not a directory", nonzero exit, NO "FAIL" text. Unreachable from every
# caller that exists today (close-gate passes a path with a slash, and so does its test), which
# is exactly why it would have gone unnoticed until someone wrote a caller that does not.
_self="${BASH_SOURCE[0]}"
case "$_self" in */*) _dir="${_self%/*}" ;; *) _dir="." ;; esac
HERE="$(cd "$_dir/../.." && pwd)"
. "$HERE/scripts/lib/lychee-pin.env"
LYCHEE="$(/bin/bash "$HERE/scripts/lib/ensure-lychee.sh")" || {
  echo "FAIL $NAME: no verified lychee binary; this check cannot run and does not pass"; exit 1; }

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/one/two/three"
printf '# deep\n\n[broken](./definitely-not-here.md)\n' > "$TMP/one/two/three/deep.md"
printf '# shallow-decoy\n\n[fine](./deep-decoy.md)\n' > "$TMP/deep-decoy.md"
printf '# target\n' > "$TMP/deep-decoy.md.tmp" && mv "$TMP/deep-decoy.md.tmp" "$TMP/deep-decoy.md"

# MEASURED ADDITION: a decoy exactly one directory deep.
# On macOS /bin/bash is 3.2.57, which predates the `globstar` shopt entirely (it is a
# 4.0+ option). Without it, an UNMATCHED glob is left as a literal string when nullglob is off
# -- and a literal "**/*.md" then reaches lychee's OWN recursive glob engine unchanged, same as
# the quoted arm. Measured directly: with only a depth-0 and a depth-3 file present, the eval'd
# unquoted `**/*.md` matched nothing, fell through literal, and BOTH arms detected the deep link
# -- reproducing the exact "quoting alone reproduces nothing" failure this file already warns
# about, one layer down. A file at exactly one directory level gives bash's non-recursive
# `*/*.md` collapse something to actually match, so the pattern expands (to this file alone)
# instead of falling through -- and that is what actually excludes the deep file.
mkdir -p "$TMP/shallow"
printf '# shallow-ok\n' > "$TMP/shallow/present.md"

# THE NEGATIVE ARM MUST GO THROUGH `eval` WITH AN UNQUOTED GLOB, AND THIS IS THE WHOLE POINT.
#
# The first draft of this script ran both arms as `"$LYCHEE" $ARGS "$target"` and BOTH ARMS
# DETECTED THE LINK -- measured, not predicted, against lychee 0.24.2. The reason is that the
# shallow behaviour was never a property of the glob STRING. It was a property of
# lychee-action's `eval lychee ... ${ARGS}`, which handed the pattern to BASH first, where
# globstar is off by default and `**` collapses to `*`. A quoted argument never reaches bash's
# pathname expansion at all, so quoting the "shallow" string reproduces nothing.
#
# The consequence is worth stating plainly, because it nearly shipped: the defect mechanism
# lives in lychee-action, which CI no longer uses. Once the action is gone there is no natural way to
# re-enter the buggy path, so the negative arm has to RECONSTRUCT it -- deliberately using the
# same `eval` + unquoted expansion the action used. That reconstruction is the control.
#
# MEASURED, SECOND PROBLEM (not a quoting-for-safety cleanup of the eval itself): the shared
# LYCHEE_ARGS_COMMON now carries `--exclude-path (^|/)docs/archive/` -- absent
# from the action's original `args:` string entirely (the pre-fix config
# was `--no-progress --offline --include-fragments **/*.md`, no exclude-path at all). Handed to
# `eval` UNCHANGED, the unquoted `(`, `)` and `|` are real shell operators to eval's re-parse, not
# literal regex characters, and it dies with "syntax error near unexpected token `('" before
# lychee ever runs -- a crash, not a detection, landing on the SAME nonzero branch as a genuine
# find and reading identically in this script's output. That is a different bug from the glob
# collapse this arm exists to reproduce, and fixing it here does not touch the glob mechanism:
# only the flags are escaped for eval's benefit; $LYCHEE_TARGET_SHALLOW is still handed to eval
# completely unquoted and unescaped, which is the actual thing under test.
esc_args_common="${LYCHEE_ARGS_COMMON//(/\\(}"
esc_args_common="${esc_args_common//)/\\)}"
esc_args_common="${esc_args_common//|/\\|}"

run_deep()    { ( cd "$TMP" && "$LYCHEE" $LYCHEE_ARGS_COMMON "$LYCHEE_TARGET" ) >/dev/null 2>&1; }
run_shallow() { ( cd "$TMP" && eval "\"\$LYCHEE\" $esc_args_common $LYCHEE_TARGET_SHALLOW" ) >/dev/null 2>&1; }

# Negative arm: bash collapses the unquoted ** to *, so one/two/three/deep.md is never read.
if run_shallow; then shallow_detected=0; else shallow_detected=1; fi

# Positive arm: the quoted, ./-prefixed target reaches lychee's own recursive glob engine.
if run_deep;    then deep_detected=0;    else deep_detected=1;    fi

fail=0
if [ "$shallow_detected" -ne 0 ]; then
  echo "FAIL $NAME: the SHALLOW arm detected the four-segment broken link."
  echo "  The negative control is no longer negative, so a green positive arm proves nothing."
  fail=1
fi
if [ "$deep_detected" -ne 1 ]; then
  echo "FAIL $NAME: the DEEP arm did NOT detect a broken link four segments down."
  echo "  target was: $LYCHEE_TARGET"
  fail=1
fi
[ "$fail" -eq 0 ] || exit 1
echo "ok $NAME: shallow arm blind at depth 4, deep arm detects -- the widened scan reaches"

# --- the scan reaches every tracked .md except the excluded archive -------------------
# SET COMPARISON, NOT COUNTS. The count form (`[ "$actual" -ne "$expected" ]`)
# was GREEN while proving nothing: LYCHEE_TARGET's glob silently skips dot-prefixed directory
# components (lychee's own engine, not bash's -- quoting doesn't help; `.claude/` is one, and it can
# hold tracked .md files), while the SAME invocation also matches untracked, gitignored
# top-level .md files present on a dev machine (AGENTS.md, RESUME.md, RESUME-archive.md,
# .claude/tasklist.md -- none dot-prefixed, so the dot-directory skip never touches them). The two
# errors can cancel: 3 files missing and 3 extra still read as equal totals, by coincidence of
# cardinality. A count can never catch an equal-size drop/gain pair; that is structural, not a
# bug in this particular count. See LYCHEE_TARGET_HIDDEN in lychee-pin.env for the fix to the
# scan itself (a second, explicit, non-`--hidden` target) -- this assertion is what catches it
# if that ever regresses, or if some OTHER dot-directory gains a tracked .md file later.
cd "$HERE"
git ls-files '*.md' | sort > "$TMP/ac1-tracked.txt"
git ls-files 'docs/archive/*.md' 'docs/archive/**/*.md' | sort > "$TMP/ac1-archive.txt"
comm -23 "$TMP/ac1-tracked.txt" "$TMP/ac1-archive.txt" > "$TMP/ac1-expected.txt"
"$LYCHEE" $LYCHEE_ARGS_COMMON --dump-inputs "$LYCHEE_TARGET" "$LYCHEE_TARGET_HIDDEN" 2>/dev/null \
  | /usr/bin/grep '\.md$' | sort -u > "$TMP/ac1-matched-raw.txt"

# --- NESTED WORK TREES ARE NOT PART OF THIS TREE'S LINK SURFACE ------------------------------
#
# THE FAILURE. When a second session (Claude Code's `EnterWorktree`, say) checks a
# different branch out under `.claude/worktrees/<name>/`, every `.md` in that checkout -- the whole
# skill tree -- is reported as "an untracked file not on the declared-safe list",
# and an UNRELATED branch cannot be pushed.
#
# It is a real defect and not merely bad luck: `.claude/worktrees/` is typically gitignored (e.g. via
# `.git/info/exclude`), lychee's glob has no git-awareness at all -- this file's own comment two
# paragraphs up says so -- and the declared-safe list is a list of individual FILES, which cannot
# express "an entire second checkout". Worse, a worktree per session is a common fix for concurrent
# sessions, so without this the guard would break on an ordinary workflow.
# Any adopter who uses `git worktree` inside their repo hits it.
#
# THE EXCLUSION IS DERIVED, NEVER A LITERAL. `git worktree list --porcelain` is asked at run time
# for the paths git itself considers separate work trees, and this tree's own root is excluded from
# that list. A hardcoded `.claude/worktrees/` would be wrong twice over: it would miss a worktree
# placed anywhere else (`git worktree add ../elsewhere` is the common spelling), and it would
# happily swallow a real `.claude/worktrees/` directory that was NOT a work tree.
#
# This cannot mask a genuine miss. The EXPECTED set comes from `git ls-files` on THIS index, and a
# path inside another work tree is by construction not in it -- so removing these from the MATCHED
# set can only ever remove rows from `extra`, never add rows to `missing`.
#
# UNVERIFIED LIMIT, named rather than implied: `git worktree list`
# reports CANONICAL paths. If a work tree were reached through a symlink inside this repo, the
# derived prefix and the path lychee reports could differ and the exclusion would simply not fire --
# which fails in the SAFE direction (a noisy red, not a silent drop). It is recorded as unverified
# because no fixture was built for it: it needs lychee to follow a symlink into a foreign checkout,
# and whether it does was not measured. Saying "handled" here would be the kind of claim this file
# spends fifty lines warning about.
git worktree list --porcelain \
  | /usr/bin/awk '/^worktree /{print substr($0, 10)}' \
  | while IFS= read -r wt; do
      [ -n "$wt" ] || continue
      [ "$wt" = "$HERE" ] && continue
      case "$wt" in "$HERE"/*) printf '%s\n' "${wt#"$HERE"/}" ;; esac
    done | sort -u > "$TMP/ac1-nested-worktrees.txt"

nested_n="$(/usr/bin/grep -c . "$TMP/ac1-nested-worktrees.txt" || true)"
cp "$TMP/ac1-matched-raw.txt" "$TMP/ac1-matched.txt"
if [ "$nested_n" -gt 0 ]; then
  while IFS= read -r wt_rel; do
    [ -n "$wt_rel" ] || continue
    # LITERAL prefix, never a regex.
    # `grep -v "^$wt_rel/"` would treat the worktree path as a PATTERN, so a metacharacter in a real
    # directory name would silently widen the exclusion: a work tree at
    # `.claude/worktrees/a.b/` produces `^.claude/worktrees/a.b/`, whose `.` matches any character,
    # and an unrelated untracked `.claude/worktrees/axb/leak.md` would be dropped with it -- a file that
    # should be REPORTED, disappearing silently, which is exactly the failure this exclusion
    # exists to avoid.
    # `grep -F` is not the answer: it has no anchors, so a fixed string would match mid-path.
    # `awk index()` compares bytes and is anchored by the `!= 1`.
    /usr/bin/awk -v p="$wt_rel/" 'index($0, p) != 1' "$TMP/ac1-matched.txt" > "$TMP/ac1-matched.next"
    mv "$TMP/ac1-matched.next" "$TMP/ac1-matched.txt"
  done < "$TMP/ac1-nested-worktrees.txt"
  # Announced, never silent. A filter that removes rows without saying so is indistinguishable
  # from a scan that never reached them -- the exact shape this whole invariant exists to catch.
  dropped=$(( $(/usr/bin/grep -c . "$TMP/ac1-matched-raw.txt" || true) - $(/usr/bin/grep -c . "$TMP/ac1-matched.txt" || true) ))
  echo "note $NAME: $nested_n nested work tree(s) excluded from the scan, $dropped .md path(s) dropped:"
  sed 's/^/  /' "$TMP/ac1-nested-worktrees.txt"
fi

expected_n="$(/usr/bin/grep -c . "$TMP/ac1-expected.txt" || true)"
if [ "$expected_n" -le 0 ]; then
  echo "FAIL $NAME: derived expected set is empty -- the derivation itself is broken."
  echo "  Refusing to fall back to a constant; that is the defect this assertion prevents."
  exit 1
fi

comm -23 "$TMP/ac1-expected.txt" "$TMP/ac1-matched.txt" > "$TMP/ac1-missing.txt"
comm -13 "$TMP/ac1-expected.txt" "$TMP/ac1-matched.txt" > "$TMP/ac1-extra.txt"

# DECLARED, NOT DISCOVERED: everything this scan is known to ALSO pick up despite being
# untracked. lychee's glob has no git-awareness at all (it matches RESUME.md, gitignored, the
# same as it matches CLAUDE.md, tracked) -- these four are common, gitignored-on-purpose local
# artifacts, not accidents: AGENTS.md (another agent's instruction file), RESUME.md / RESUME-archive.md
# (session continuity docs), .claude/tasklist.md (guarded by its own tasklist-never-tracked
# invariant). Checking their links is harmless. This is a SUBSET check, not exact-match on
# purpose: none of the four exist in a fresh checkout (real CI never sees RESUME.md), so an
# ALLOWED entry being ABSENT from a given run is fine -- only an extra match NOT on this list is
# a genuine FAIL, because that is an unreviewed file silently joining what CI link-checks.
ALLOWED_EXTRA=(
  "AGENTS.md"
  "RESUME.md"
  "RESUME-archive.md"
  ".claude/tasklist.md"
)
unexplained_extra=0
while IFS= read -r f; do
  [ -n "$f" ] || continue
  known=0
  for a in "${ALLOWED_EXTRA[@]}"; do
    if [ "$f" = "$a" ]; then known=1; break; fi
  done
  if [ "$known" -eq 0 ]; then
    echo "FAIL $NAME: scan matched an untracked file not on the declared-safe list: $f"
    unexplained_extra=1
  fi
done < "$TMP/ac1-extra.txt"

missing_n="$(/usr/bin/grep -c . "$TMP/ac1-missing.txt" || true)"
if [ "$missing_n" -gt 0 ]; then
  echo "FAIL $NAME: scan is missing $missing_n tracked markdown file(s) it must reach:"
  sed 's/^/  /' "$TMP/ac1-missing.txt"
  exit 1
fi
[ "$unexplained_extra" -eq 0 ] || exit 1
echo "ok $NAME: scan reaches all $expected_n tracked markdown files outside docs/archive/ (set-exact on missing, extras checked against a declared allowlist)"

# --- the exclusion excludes the archive, and did not silence everything ---------------
# The SECOND condition is the one that matters. Zero findings everywhere is indistinguishable
# from a correct exclusion if you only check the first.
#
# THE KEY IS `error_map`, NOT `fail_map`. Verified against lychee 0.24.2's real --format json
# output: the emitted keys are error_map / success_map / excluded_map / timeout_map /
# redirect_map / suggestion_map. The first draft read `.fail_map`, which does not exist -- and
# because the assignment was unguarded under `set -euo pipefail`, jq's "null has no keys"
# aborted the script and made the success line below UNREACHABLE. A check that always dies
# before its verdict is a check that never ran.
#
# No `trap ... RETURN` here: this script is EXECUTED, not sourced, so a RETURN trap never
# fires and the temp file leaks. The EXIT trap set at the top of the script owns cleanup, and
# the report lives inside $TMP so that one trap already covers it.
report="$TMP/lychee-report.json"
"$LYCHEE" $LYCHEE_ARGS_COMMON --format json "$LYCHEE_TARGET" "$LYCHEE_TARGET_HIDDEN" > "$report" 2>/dev/null || true
jq -e 'has("error_map")' "$report" >/dev/null || {
  echo "FAIL $NAME: lychee's JSON has no error_map key -- the schema changed."
  echo "  Refusing to report a verdict computed from a shape this version does not emit."
  exit 1; }
arch_findings="$(jq '[.error_map | to_entries[] | select(.key | test("docs/archive/"))] | length' "$report")"
other_findings="$(jq '[.error_map | to_entries[] | select(.key | test("docs/archive/") | not)] | length' "$report")"
if [ "$arch_findings" -ne 0 ]; then
  echo "FAIL $NAME: $arch_findings finding(s) under docs/archive/ -- the exclusion is not excluding"
  exit 1
fi
# LIVENESS IS PROVEN ON A PLANTED CONTROL, NEVER ON THE REPOSITORY STAYING BROKEN.
#
# The first version of this block asserted `other_findings > 0` against the REAL tree, and its own
# failure message told the reader to "plant a control". That was a trap with no exit. In a repo with
# exactly one genuine broken anchor, fixing it -- the obviously correct act, and the only way to
# make CI green -- would have blocked every push until somebody deliberately broke a document
# again. A guard whose green depends on the codebase staying defective is not a guard, it is a
# hostage.
#
# The control lives in $TMP, which the archive exclusion cannot reach, so this asserts the scan is
# LIVE -- it still reports a finding when one exists -- while holding no opinion about whether the
# real tree currently has one. `arch_findings` above is unchanged and still reads the real tree.
ctl="$TMP/liveness"
mkdir -p "$ctl"
printf '# liveness control\n\n[deliberately broken](./no-such-target-9f3a.md)\n' > "$ctl/probe.md"
ctl_report="$TMP/lychee-liveness.json"
( cd "$ctl" && "$LYCHEE" $LYCHEE_ARGS_COMMON --format json './**/*.md' ) > "$ctl_report" 2>/dev/null || true
if ! jq -e 'has("error_map")' "$ctl_report" >/dev/null; then
  echo "FAIL $NAME: the liveness control produced no error_map -- the probe could not run"
  exit 1
fi
ctl_findings="$(jq '[.error_map | to_entries[]] | length' "$ctl_report")"
if [ "$ctl_findings" -eq 0 ]; then
  echo "FAIL $NAME: the scan reported ZERO findings against a deliberately broken link."
  echo "  Either link checking is disabled or the exclusion is over-broad; a run that cannot"
  echo "  report a finding it was handed cannot be trusted to report a real one."
  exit 1
fi
echo "ok $NAME: archive excluded (0 findings in the real tree), and the scan is live -- a planted broken link IS reported ($ctl_findings on the control)"
echo "   real-tree non-archive findings: $other_findings (REPORTED, not asserted -- this guard must never require the repository to stay broken)"
