#!/usr/bin/env bash
# Invariant: the tasklist artifact is ignored, and no tasklist is tracked -- at the path actually
# CONFIGURED, not only at the one hard-coded in .gitignore.
#
# WHY. `.gitignore` ignores `/.claude/tasklist.md` at exactly one path, while the writer resolves
# `${PLC_TASKLIST_FILE:-.claude/tasklist.md}` and `tasklist-first.sh:104` records that the override
# "can already be absolute". So the file can legitimately live anywhere, and without this script NO invariant
# mentioned `tasklist` at all. A committed tasklist -- session nonce plus per-phase working state,
# meaningless outside its session -- passed every declared check.
#
# The nonce is the part that makes this more than tidiness. It is minted at block time and must be
# transcribed into the artifact so that last phase's checklist cannot satisfy this phase. Committing
# one publishes a satisfier and, worse, invites the next session to edit a tracked file whose whole
# purpose is to be per-session.
#
# WHAT THIS DELIBERATELY DOES NOT DO, each a binding design constraint rather than an
# omission:
#
#   * It does NOT widen `no-hook-state-tracked.sh`. That script's header scopes it to state the
#     HOOKS THEMSELVES write; the tasklist is written by the agent. Its mechanism is three exact
#     basenames and could not follow an arbitrary override anyway, and widening it would deepen its
#     already-generous "asks by SHAPE" self-description. One invariant, one named constraint.
#
#   * It does NOT sweep `git ls-files` for `*tasklist*`. A blind reviewer's false-positive objection
#     was accepted as binding: this repo tracks `scripts/tasklist-view.sh`, its test, and a command
#     doc, and a broad sweep would red on all of them. The tracked-anywhere check is pinned to the
#     RESOLVED configured path plus the known default location. There is one default:
#     `.claude/tasklist.md`.
#
#   * It does NOT ask for `.gitignore` to be "un-anchored". That would be wrong:
#     per git's own documentation a pattern containing a slash anywhere but the trailing position is
#     ALREADY anchored, so the leading `/` is redundant and `**/` would be strictly LOOSER. The rule
#     is correct; what it cannot do is follow an override, which is what this script is for.
#
# EXIT 128 IS NOT EXIT 1. `git check-ignore` exits 0 when a path IS ignored, 1 when it is not,
# and 128 on a fatal error -- wrong cwd, unset GIT_DIR, not a work tree. Treating "any nonzero" as
# "not ignored" would turn an environment bug into a confident, false finding about the repository.
# A check that could not run must never report as though it did.
#
# Envelope: bash + git only. No python3, no jq.

set -uo pipefail

NAME="tasklist-never-tracked"

pass() { printf 'PASS %s: %s\n' "$NAME" "$1"; exit 0; }
fail() { printf 'FAIL %s: %s\n' "$NAME" "$1"; exit 1; }
# A third verdict: the CHECK failed, not the repo.
#
# EXIT 3, and the comment used to say "Not exit 1" while the next token was `exit 1`.
# The manifest repeated the distinction as a contract, and the only test on this path
# asserted `returncode != 0` -- so deleting the third verdict entirely would have gone unnoticed.
#
# WHAT EXIT 3 DOES AND DOES NOT BUY, stated rather than implied. `close-gate.sh`'s invariant runner
# reads exit STATUS only (`elif ( eval "$CMD" ) >/dev/null 2>&1`), so 1 and 3 are still the same
# thing to the gate -- both block, which is the fail-closed behaviour a check that could not run
# must have. What 3 buys is that the distinction is now legible to a direct caller, to CI, and to
# a test that can assert it, instead of existing only in prose that the code contradicted.
CANNOT_RUN_RC=3
cannot_run() { printf 'FAIL %s: COULD NOT RUN -- %s\n' "$NAME" "$1"; exit "$CANNOT_RUN_RC"; }

REPO_ROOT="${1:-$(git rev-parse --show-toplevel 2>/dev/null || true)}"
[ -n "$REPO_ROOT" ] || cannot_run "not inside a git work tree (git rev-parse --show-toplevel failed)"
cd "$REPO_ROOT" 2>/dev/null || cannot_run "cannot enter repo root: $REPO_ROOT"

# Strip trailing slashes from the root before ANYTHING compares against it.
#
# MEASURED, and this one was silent: the in-repo test is `"$REPO_ROOT"/*`, so a root
# passed as `/path/to/repo/` produces `/path/to/repo//*`, which matches nothing. The DEFAULT
# `.claude/tasklist.md` was then reported as resolving OUTSIDE the repo and the invariant exited 0
# having checked nothing at all -- a green that means "I looked away". The root is a documented
# argument (see the row that passes it explicitly), so a trailing slash is a spelling a caller will
# actually use. `/` itself is preserved rather than emptied.
while [ "$REPO_ROOT" != "/" ] && [ "$REPO_ROOT" != "${REPO_ROOT%/}" ]; do
  REPO_ROOT="${REPO_ROOT%/}"
done

# The configured path, resolved the same way the writer resolves it
# (skills/project-lifecycle/hooks/tasklist-first.sh:75).
ART_REL="${PLC_TASKLIST_FILE:-.claude/tasklist.md}"

# The pinned set: the resolved path plus the known default location. Named individually rather than
# globbed, which is the whole point of the no-broad-sweep constraint. There is ONE default; this
# list carried it twice while calling itself "the two known default locations".
DEFAULTS=".claude/tasklist.md"

# Resolve the override to an absolute path FIRST, lexically, so that every spelling of the same
# situation gets the same verdict.
#
# WHY LEXICALLY AND WHY AT ALL. This used to branch on a
# leading `/` only. A RELATIVE escape -- `PLC_TASKLIST_FILE=../tasklist.md`, the ordinary way to
# say "the tasklist lives beside this repo" -- fell through to the `*)` arm as a literal
# `../tasklist.md`, `git check-ignore` refused it with exit 128, and the script reported
# "COULD NOT RUN ... bad cwd, unset GIT_DIR, or not a work tree". None of those was true, and the
# ABSOLUTE spelling of the identical situation was a documented PASS. Same state, two verdicts.
#
# The path need not exist, so this cannot use `realpath`/`cd`; segments are collapsed by text. A
# subshell keeps the `IFS` change local. Symlinks are not resolved, and that is a real limit: a
# symlinked repo root could make an in-repo path look out-of-repo. It is left alone rather than
# papered over, because resolving it needs a filesystem the path may not have.
abspath() (
  # `set -f` is load-bearing, not hygiene. The splitting loop below is an UNQUOTED `$p`, so
  # without noglob the shell pathname-expands every segment: MEASURED, a
  # configured `*` became a listing of the repo root joined by slashes, and the check then ran
  # against that invented path and reported PASS. A nonsense configured value must stay nonsense
  # and be judged as itself, never be quietly replaced by a directory listing.
  set -f
  case "$1" in
    /*) p="$1" ;;
    *)  p="$REPO_ROOT/$1" ;;
  esac
  out=""
  IFS=/
  for seg in $p; do
    case "$seg" in
      '' | .) continue ;;
      ..)     out="${out%/*}" ;;
      *)      out="$out/$seg" ;;
    esac
  done
  printf '%s' "${out:-/}"
)

ART_ABS="$(abspath "$ART_REL")"

case "$ART_ABS" in
  # The root ITSELF, not only paths under it. `"$REPO_ROOT"/*` does not match `$REPO_ROOT`, so
  # a configured path that resolves exactly to the work-tree root was answered "outside this
  # repo". It is inside by definition; `git check-ignore` on `.` is the honest
  # question to ask about it.
  "$REPO_ROOT")
    CHECK_REL="."
    ;;
  "$REPO_ROOT"/*)
    CHECK_REL="${ART_ABS#"$REPO_ROOT"/}"
    ;;
  *)
    # OUT OF SCOPE, UNVERIFIED -- and it says the weaker of the two things it could say.
    #
    # This used to end "...and the directory marker is what protects it", which asserted a
    # protection it never checked. For the likeliest shape -- a sibling
    # repo's `<repo>/.claude/tasklist.md` -- `scripts/tasklist-guard-dir.sh:61-65` REFUSES to
    # write a marker at all, because `.claude/` already exists and a marker belongs only in a
    # directory that script created. Correctly so, and pinned by its own test. So the old wording
    # named as the protection the exact thing that is absent in the common case.
    #
    # Exit 0 is still right: no `.gitignore` in this repo governs that path, and reporting a
    # failure the repo cannot fix would be a confident finding about someone else's tree. What
    # changes is the claim -- this is an absence of coverage, not a clean bill of health.
    pass "PLC_TASKLIST_FILE resolves outside this repo ($ART_REL -> $ART_ABS) -- OUT OF SCOPE, UNVERIFIED. No .gitignore here governs it, and this check does NOT assert anything protects it: tasklist-guard-dir.sh writes a marker only into a directory it created itself, so a pre-existing .claude/ beside another repo has none"
    ;;
esac

# --- 1. TRACKED is checked FIRST, and the order is load-bearing -------------------------------
#
# MEASURED, and this script had the order the other way round until it was: git's ignore
# rules DO NOT APPLY to tracked files, so `git check-ignore` answers 1 -- "not ignored" -- for a
# file that is both tracked and matched by a rule. Same repo, same rule, one `git add -f` apart:
#
#     untracked, rule present  ->  check-ignore exit 0   (ignored)
#     TRACKED,   rule present  ->  check-ignore exit 1   ("not ignored")
#     TRACKED,   --no-index    ->  check-ignore exit 0   (the rule is still there)
#
# With the ignore test first, a committed tasklist produced a red whose stated reason was "the
# configured tasklist path is NOT ignored" and whose remedy was "place a marker" -- a TRUE FAILURE
# WITH A FALSE REASON, pointing the reader at .gitignore when the actual problem is an index entry
# that no ignore rule can override. It was caught by a fixture rather than by reading.
# --- 0. the configured value must be a PATH, refused fail-closed if it is not ---------------
#
# MEASURED. Without this, `PLC_TASKLIST_FILE='*'` reached the scan below and
# `git ls-files --error-unmatch -- '*'` matched the whole index, producing
# `FAIL: a tasklist artifact is git-tracked: [*]`. Non-zero, so safe -- and a TRUE FAILURE WITH A
# FALSE REASON, the exact shape this script's own header documents about check order. The reader
# is sent to `git rm --cached` when the actual problem is that the configuration is not a path.
# The work-tree root has the same shape: `.` matches everything tracked.
case "$CHECK_REL" in
  '.' )
    fail "PLC_TASKLIST_FILE ('$ART_REL') resolves to the work-tree root itself, not to a tasklist file
  -> this is a configuration error, not a tracked artifact. Point it at a file."
    ;;
  *[*?\[\]]* | :* )
    fail "PLC_TASKLIST_FILE ('$ART_REL') contains a glob or magic-pathspec character, so it is not a path this check can resolve
  -> refusing to certify it (fail closed). The writer resolves it as a literal filename; a pattern
     here means the tasklist is not where anyone thinks it is."
    ;;
esac

CANDIDATES="$CHECK_REL
$DEFAULTS"

tracked=""
while IFS= read -r p; do
  [ -n "$p" ] || continue
  case "$tracked" in *"[$p]"*) continue ;; esac   # de-duplicate; the resolved path is often a default
  if git ls-files --error-unmatch -- "$p" >/dev/null 2>&1; then
    tracked="$tracked[$p]"
  fi
done <<EOF
$CANDIDATES
EOF

if [ -n "$tracked" ]; then
  fail "a tasklist artifact is git-tracked: $tracked
  -> TRACKING BEATS IGNORING. An ignore rule has no effect on a file already in the index, so this
     is not fixed by editing .gitignore and not fixed by adding a marker -- \`git check-ignore\`
     will even report the path as 'not ignored' while the rule sits right there.
  -> Remove it with \`git rm --cached <path>\` and commit that removal. The artifact carries a
     per-session nonce and per-phase working state; committing one publishes a satisfier for the
     tasklist-first guard and invites the next session to edit a file whose whole purpose is to be
     per-session."
fi

# --- 2. and only then, is the configured path IGNORED -----------------------------------------
git check-ignore -q -- "$CHECK_REL"
rc=$?
case "$rc" in
  0) : ;;
  1) fail "the configured tasklist path is NOT ignored: $CHECK_REL
  -> it carries a per-session nonce and per-phase working state; committing one publishes a
     satisfier for the tasklist-first guard and invites the next session to edit a tracked file
     whose whole purpose is to be per-session.
  -> if PLC_TASKLIST_FILE points somewhere .gitignore does not cover, run
     scripts/tasklist-guard-dir.sh to place a self-ignoring marker in the directory the tool
     created for it -- do NOT loosen the .gitignore rule, which is already correctly anchored." ;;
  128) cannot_run "git check-ignore exited 128 on '$CHECK_REL' (fatal: bad cwd, unset GIT_DIR, or not a work tree). This is the CHECK failing, not a finding about the repo." ;;
  *) cannot_run "git check-ignore exited $rc on '$CHECK_REL', which is outside its documented 0/1/128 contract" ;;
esac

pass "configured path '$CHECK_REL' is ignored, and no tasklist is tracked at it or at the known defaults"
