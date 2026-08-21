#!/usr/bin/env bash
# Deterministic tests for the project-lifecycle frontmatter hook scripts.
# Run before committing hook changes. No fresh session needed — these exercise the scripts directly.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# this suite tests FOUR hooks, each invoked through a selector (the *_IMPL variables below) so a mutation run can reach every one of them.
#
# Absolutised for the same reason CF_IMPL is: a mutation run hands in a RELATIVE path, and
# several sections below `cd` into a temp repo before invoking the hook.
#
# MEASURED when the selectors were introduced (numbers from real runs, not predictions).
#
# (a) Wiring, proven by a stub that only counts its own invocations — this is the check that
#     answers "does EVERY call site honour the selector?", independent of any assertion:
#            guard 25   nudge 12   tasklist 64      (before this change: 0, 0, 0)
#     tasklist is 64 rather than 40 because `arm3()` invokes the hook three times and is
#     itself called from several rows; 40 is the count of static sites, not of invocations.
#
# (b) Sensitivity, per hook, under three stub classes — no-op(exit 0) / always-block(exit 2) /
#     noisy(emits JSON, exit 0) — with row-level union taken by ORDINAL, not by name. Matching
#     by name is wrong here and quietly produced nonsense the first time: many rows word their
#     `ok` and `no` strings differently ("allows push to main-experiment (no false positive)"
#     vs "allows main-experiment"), so a name-keyed union counts one row as two.
#         hook                rows  no-op  block  noisy  union
#         guard.sh              25     11     14     11     25
#         close-gate-nudge.sh   12      5      6     12     12
#         tasklist-first.sh     37     23     30     24     35
#         context-floor.sh      15      6     13      6     15
#
# (c) RESIDUAL, stated rather than papered over: two tasklist rows are never red under any of
#     the three classes — "TodoWrite len 1 does not set seen" and "a fresh session consumes
#     the marker once". Both assert that a state file is NOT written. (a) proves their call
#     sites are wired; no stub that only controls stdout and exit code can move them. Reaching
#     them needs a stub that writes the hook's own state layout, i.e. an UNFAITHFUL stub of the
#     kind that lets a test pass over a probe that could never work. Not built on purpose.
#
# The unresolvable-directory case is FATAL, not a fallback. Measured: with a bare
# `$(cd … && pwd)`, `PLC_GUARD_NEW=nosuchdir/guard-mutant.sh` resolves to `/guard-mutant.sh`
# and the suite prints `guard.sh 0 passed, 25 failed` — every row red because nothing ran.
# That is the most convincing wrong answer available: it reads as "the suite is extremely
# sensitive to this mutant" when it is actually a typo in the mutant's path. A mutation run
# whose result is misattributed is worse than one that does not happen.
impl_path(){   # $1 = override (may be empty), $2 = default; echoes an absolute path
  local p="${1:-$2}" d
  case "$p" in
    /*) printf '%s\n' "$p" ;;
    *)  d="$(cd "$(dirname "$p")" 2>/dev/null && pwd)"
        [ -n "$d" ] || { echo "FATAL: cannot resolve '$p' — its directory does not exist (a mis-typed mutant path would otherwise redden every row and read as sensitivity)" >&2; exit 2; }
        printf '%s/%s\n' "$d" "$(basename "$p")" ;;
  esac
}
# `|| exit 2` is load-bearing and was missing on the first attempt: `impl_path` runs inside a
# command substitution, so its `exit 2` leaves the SUBSHELL and the script carries on with an
# empty selector. Measured before this line existed: a mis-typed mutant path still produced
# `70 passed, 26 failed` instead of aborting. Command substitution propagates the status, so
# the abort has to be re-raised here.
GUARD_IMPL="$(impl_path "${PLC_GUARD_NEW:-}" "$HERE/guard.sh")" || exit 2
NUDGE_IMPL="$(impl_path "${PLC_NUDGE_NEW:-}" "$HERE/close-gate-nudge.sh")" || exit 2
TASKLIST_IMPL="$(impl_path "${PLC_TASKLIST_NEW:-}" "$HERE/tasklist-first.sh")" || exit 2
# the shared floor library, selected and guarded exactly like the hook selectors above --
# PLC_FLOOR_LIB_NEW picks a mutant library, `impl_path` gives the FATAL unresolvable-directory
# answer, and `|| exit 2` re-raises it out of the command substitution. Readability is checked on
# top, because `impl_path` proves a path RESOLVES and cannot prove it is loadable: a hook that
# cannot load the library degrades to "OFF", which on the floor side is rc=0 (indistinguishable
# from "under the floor") and on the nudge side is empty stdout (indistinguishable from "no nudge
# was due"). Either way an unreadable library turns rows green for the wrong reason.
#
# Defined HERE, beside the other selectors, rather than next to its first use: both the nudge
# section and the context-floor section need it, and the nudge section runs first.
FLOOR_LIB_IMPL="$(impl_path "${PLC_FLOOR_LIB_NEW:-}" "$HERE/lib/floor-env.sh")" || exit 2
[ -r "$FLOOR_LIB_IMPL" ] || { echo "FATAL: shared floor library not readable: $FLOOR_LIB_IMPL" >&2; exit 2; }
printf 'floor library in use: %s\n' "$FLOOR_LIB_IMPL"
# The result ledger is a FILE, not a shell variable. Four of the sections below run inside
# ( … ) subshells, and a variable incremented in a subshell is discarded when it exits — so
# a counter kept in $PASS/$FAIL structurally cannot see most of this suite's own results.
# Created before the first subshell, and FORCED ABSOLUTE: the sections that `cd` into a
# temp repo and then `rm -rf` it must not be able to reach it. A relative TMPDIR would put
# the ledger inside one of those repos, and its results would be deleted with it.
RESULTS="$(mktemp "${TMPDIR:-/tmp}/plc-test-hooks.XXXXXX")" \
  || { echo "FATAL: cannot create the result ledger under '${TMPDIR:-/tmp}'" >&2; exit 1; }
case "$RESULTS" in /*) ;; *) RESULTS="$PWD/$RESULTS" ;; esac
trap 'rm -f "$RESULTS"' EXIT

# `return 0` is load-bearing: almost every assertion is an `A && ok … || no …` chain, and a
# non-zero return from ok would run the no branch as well.
#
# A failed append is announced on stderr, but be precise about what that buys: most of these
# calls happen inside ( … ) subshells, so `led` CANNOT abort the run or reach the tally. The
# notice is a breadcrumb for a human reading the log, not a control. `verdict` is where the
# ledger's health is actually judged, and its coverage is stated there — do not read this
# stderr line as "a lost result cannot slip through".
#
# each entry now carries the SECTION it was recorded under, so the tally can be broken
# down per hook. A single aggregate number is what let three mutation-blind quarters hide
# behind one green headline; a per-hook breakdown makes "which hook did those passes come
# from?" answerable without reading the log. SECTION is set outside the ( … ) subshells and
# inherited by them, so it survives the four sections that run in one.
led(){ printf '%s\t%s\n' "$1" "${SECTION:-other}" >> "$RESULTS" || echo "FATAL: result ledger unwritable ($RESULTS)" >&2; }
ok(){ printf '  PASS: %s\n' "$1"; led P; return 0; }
no(){ printf '  FAIL: %s\n' "$1"; led F; return 0; }
SECTION="startup"

# Print the tally and exit with it. Every path out of this script goes through here.
verdict(){
  local p f
  # An absent or empty ledger is NOT a pass. "Nothing was recorded" and "nothing failed"
  # are different states, and treating the first as the second is exactly how this suite
  # used to report green over its own failures.
  [ -s "$RESULTS" ] || {
    echo
    echo "RESULT: no results recorded — the ledger is missing or empty, so this run proves nothing"
    exit 1
  }
  # …and a ledger that STOPPED being writable part-way is the same defect with a later
  # trigger: the entries recorded before it broke are all passes, the failures after it are
  # gone, and the tally reads clean. Checked, not assumed.
  # KNOWN RESIDUAL: this catches the permission case, not a mid-run ENOSPC (the file stays
  # writable, the append just fails). Closing that needs an expected-assertion-count floor,
  # which is a different trade — written down here rather than papered over.
  [ -w "$RESULTS" ] || {
    echo
    echo "RESULT: the ledger stopped being writable — results were lost, so this run proves nothing"
    exit 1
  }
  p="$(grep -c "^P$(printf '\t')" "$RESULTS" 2>/dev/null)" || true
  f="$(grep -c "^F$(printf '\t')" "$RESULTS" 2>/dev/null)" || true
  case "$p" in ''|*[!0-9]*) p=0 ;; esac
  case "$f" in ''|*[!0-9]*) f=0 ;; esac
  # per-section breakdown, in first-appearance order. The aggregate below is kept
  # byte-identical on purpose — it is the line that gets quoted — but it is no
  # longer the only thing this suite says about itself.
  # `${SECTION:-other}` keeps `set -u` happy, and in doing so it makes
  # a section that forgot to set SECTION indistinguishable from one that set it — the rows
  # are silently attributed to whichever section ran last, and "each mutant reddened only its
  # own section" then reads true or false for the wrong reason. The section list is therefore
  # PINNED. A new section must be added here as well, which is the point: the cost of adding
  # one is a line, the cost of forgetting SECTION is a lie about which hook was covered.
  # SELFTEST modes raise exactly one assertion by design, so the pin cannot apply to them —
  # measured: adding the pin without this guard turned `--selftest-clean` into a non-zero exit
  # and reddened the self-verification row on a clean tree (95/1). The self-test asserts
  # that the EXIT CODE tracks assertions; a ledger-shape check firing there would make it
  # assert something else.
  [ -n "${SELFTEST:-}" ] || {
  _seen="$(awk -F'\t' '{print $2}' "$RESULTS" | sort -u | tr '\n' ' ')"
  _want="close-gate-nudge.sh context-floor.sh frontmatter guard.sh self-verification tasklist-first.sh "
  [ "$_seen" = "$_want" ] || {
    echo
    echo "RESULT: section ledger mismatch — a section is missing, renamed, or never set SECTION"
    echo "  expected: $_want"
    echo "  recorded: $_seen"
    exit 1
  }
  }
  echo
  echo "PER-SECTION:"
  awk -F'\t' '
    { key=$2; if (!(key in seen)) { seen[key]=1; order[++n]=key }
      if ($1=="P") pass[key]++; else if ($1=="F") fail[key]++ }
    END { for (i=1;i<=n;i++) { k=order[i]
            printf "  %-34s %3d passed, %3d failed\n", k, pass[k]+0, fail[k]+0 } }
  ' "$RESULTS"
  echo
  echo "RESULT: $p passed, $f failed"
  [ "$f" -eq 0 ] || exit 1
  exit 0
}

# Self-verification mode. Re-entered by the "=== self-verification ===" section at
# the bottom, which asserts that this script's EXIT CODE reflects its assertions. Skips
# every test body and takes only the verdict path.
#   --selftest-fail  -> one deliberate FAILURE raised from inside a ( … ) subshell — the
#                       exact case a shell-variable counter cannot see. Must exit non-zero.
#   --selftest-clean -> one deliberate PASS, also from inside a subshell. Must exit zero.
# Both sides raise a real result: a mode that recorded nothing would only prove "an empty
# ledger exits zero", which is the very state verdict() now refuses to call a pass.
# Driven by $1, never by an inherited environment variable — an exported PLC_SELFTEST would
# silently reduce a full run to a two-line no-op that still exits 0.
case "${1:-}" in
  --selftest-fail)  SELFTEST=1; ( no "deliberate failure raised inside a subshell (self-test)" ); verdict ;;
  --selftest-clean) SELFTEST=1; ( ok "deliberate pass raised inside a subshell (self-test)" );   verdict ;;
  "") ;;
  *)  echo "usage: ${BASH_SOURCE[0]##*/} [--selftest-fail|--selftest-clean]" >&2; exit 2 ;;
esac

# Build the hook event JSON via json.dumps so commands containing quotes
# (e.g. a -m "message") are escaped correctly.
ev(){ python3 -c 'import json,sys; print(json.dumps({"tool_name":"Bash","tool_input":{"command":sys.argv[1]}}))' "$1"; }

SECTION="guard.sh"
echo "=== guard.sh ==="
ev 'git commit --no-verify -m x' | /bin/bash "$GUARD_IMPL" >/dev/null 2>&1; [ $? -eq 2 ] && ok "blocks --no-verify flag" || no "blocks --no-verify flag"
ev 'git push origin main'        | /bin/bash "$GUARD_IMPL" >/dev/null 2>&1; [ $? -eq 2 ] && ok "blocks push origin main" || no "blocks push origin main"
ev 'git push origin HEAD:main'   | /bin/bash "$GUARD_IMPL" >/dev/null 2>&1; [ $? -eq 2 ] && ok "blocks push HEAD:main" || no "blocks push HEAD:main"
ev 'git push origin feat/phase-1.2-x' | /bin/bash "$GUARD_IMPL" >/dev/null 2>&1; [ $? -eq 0 ] && ok "allows push to feat branch" || no "allows push to feat branch"
ev 'git push origin main-experiment'  | /bin/bash "$GUARD_IMPL" >/dev/null 2>&1; [ $? -eq 0 ] && ok "allows push to main-experiment (no false positive)" || no "allows main-experiment"
ev 'echo hello'                  | /bin/bash "$GUARD_IMPL" >/dev/null 2>&1; [ $? -eq 0 ] && ok "allows ordinary command" || no "allows ordinary command"
ev 'npm run verify'              | /bin/bash "$GUARD_IMPL" >/dev/null 2>&1; [ $? -eq 0 ] && ok "allows 'verify' substring" || no "allows verify substring"
# Regression: the flag/word appearing inside a commit MESSAGE must NOT false-block.
# These two passed under the old python3 shlex implementation because shlex kept a quoted span as
# ONE token. The POSIX rewrite has no lexer, so it passes them by a DIFFERENT mechanism:
# quoted spans are deleted outright before anything is tokenized. Spelled out because the two
# routes are not interchangeable — a future "simplification" that tokenizes first and strips
# later silently reopens both of these, and they would then be the guard's most common false
# positive (every commit message that says "main" or "--no-verify").
ev 'git commit -m "docs: guard blocks the --no-verify bypass"' | /bin/bash "$GUARD_IMPL" >/dev/null 2>&1; [ $? -eq 0 ] && ok "allows --no-verify inside a commit message (quoted span dropped)" || no "false-positive: --no-verify in message"
ev 'git commit -m "note: push to main later"' | /bin/bash "$GUARD_IMPL" >/dev/null 2>&1; [ $? -eq 0 ] && ok "allows 'main' inside a commit message (quoted span dropped)" || no "false-positive: main in message"
ev "git commit -m 'single quotes: push to main'" | /bin/bash "$GUARD_IMPL" >/dev/null 2>&1; [ $? -eq 0 ] && ok "allows 'main' inside a single-quoted message" || no "false-positive: main in single-quoted message"

# --- the guard reported the event it inferred, not the one it checked ---------------------
# Every case below is a PROBED observation, not a hypothetical. The
# expectations are what a correct guard must do; the ones marked (was RED) fail against the
# earlier implementation and are the reason this section exists. Pinning them here first is
# deliberate: a correctness fix for an inference bug that is not itself pinned to evidence is the
# same defect class recurring inside its own fix.
#
# Two independent bugs are covered:
#   (1) FALSE POSITIVES — the whole command line is scanned as one flat token list, so `push` from
#       one sub-command and `main` from another combine into a verdict about neither.
#   (2) FALSE NEGATIVES — the target is matched as `t == "main" or t.endswith(":main")`, which is
#       not how git names a push target. `+main` (FORCE) and `refs/heads/main` both miss.

# (1) Compound commands: the `push` and the `main` come from DIFFERENT sub-commands.
ev 'git push -u origin feat/x && gh pr create --base main --title x' | /bin/bash "$GUARD_IMPL" >/dev/null 2>&1; [ $? -eq 0 ] && ok "allows push-to-feat && gh pr create --base main (was RED)" || no "false-positive: compound push + gh pr create --base main"
ev 'git checkout main && git push origin --delete feat/x' | /bin/bash "$GUARD_IMPL" >/dev/null 2>&1; [ $? -eq 0 ] && ok "allows checkout main && push --delete feat (was RED)" || no "false-positive: compound checkout main + branch-delete push"
# Unspaced operator — naive word-splitting fuses `x&&gh` into one token and segmentation silently
# does nothing. Kept as its own case precisely because it is the way the fix is most likely to fail.
ev 'git push origin x&&gh pr create --base main' | /bin/bash "$GUARD_IMPL" >/dev/null 2>&1; [ $? -eq 0 ] && ok "allows unspaced compound: push origin x&&gh pr create --base main (was RED)" || no "false-positive: unspaced compound operator"

# (2) Real pushes to main that the token match does not recognise.
ev 'git push origin refs/heads/main' | /bin/bash "$GUARD_IMPL" >/dev/null 2>&1; [ $? -eq 2 ] && ok "blocks push to refs/heads/main (was RED)" || no "FALSE NEGATIVE: refs/heads/main allowed"
ev 'git push origin +main' | /bin/bash "$GUARD_IMPL" >/dev/null 2>&1; [ $? -eq 2 ] && ok "blocks FORCE push to main (+main) (was RED)" || no "FALSE NEGATIVE: +main force-push allowed"
ev 'git push origin +HEAD:main' | /bin/bash "$GUARD_IMPL" >/dev/null 2>&1; [ $? -eq 2 ] && ok "blocks force push +HEAD:main" || no "FALSE NEGATIVE: +HEAD:main allowed"

# Deletion forms of the same target — these already pass; pinned so a rewrite cannot lose them.
ev 'git push origin :main' | /bin/bash "$GUARD_IMPL" >/dev/null 2>&1; [ $? -eq 2 ] && ok "blocks delete-by-refspec :main" || no "regression: :main allowed"
ev 'git push origin --delete main' | /bin/bash "$GUARD_IMPL" >/dev/null 2>&1; [ $? -eq 2 ] && ok "blocks --delete main" || no "regression: --delete main allowed"
# --delete/-d BEFORE the remote. The flag binds to the whole segment,
# not to the single next token — else the token after --delete is eaten as the delete target
# (a non-main), the remote consumes the next slot, and `main` lands in the refspec position unchecked.
ev 'git push --delete origin main' | /bin/bash "$GUARD_IMPL" >/dev/null 2>&1; [ $? -eq 2 ] && ok "blocks --delete BEFORE remote (delete origin main)" || no "FALSE NEGATIVE: --delete origin main allowed"
ev 'git push -d origin main' | /bin/bash "$GUARD_IMPL" >/dev/null 2>&1; [ $? -eq 2 ] && ok "blocks -d BEFORE remote (-d origin main)" || no "FALSE NEGATIVE: -d origin main allowed"

# Correct-today cases, pinned as regressions. `main:release` and `target=main` both LOOK like
# false positives, and probing shows they are not — they are
# handled right today, and a rewrite must not "fix" them into blocks.
ev 'git push origin main:release' | /bin/bash "$GUARD_IMPL" >/dev/null 2>&1; [ $? -eq 0 ] && ok "allows main:release (main is the SOURCE, target is release)" || no "false-positive: main as refspec source"
ev 'git push -o "target=main" origin feat/x' | /bin/bash "$GUARD_IMPL" >/dev/null 2>&1; [ $? -eq 0 ] && ok "allows --push-option value containing main" || no "false-positive: -o target=main"
ev 'git push origin --delete feat/x' | /bin/bash "$GUARD_IMPL" >/dev/null 2>&1; [ $? -eq 0 ] && ok "allows branch-delete push (standalone)" || no "false-positive: standalone --delete feat"
ev 'gh pr create --base main --title x' | /bin/bash "$GUARD_IMPL" >/dev/null 2>&1; [ $? -eq 0 ] && ok "allows standalone gh pr create --base main" || no "false-positive: standalone gh pr create"

# DOCUMENTED FALSE POSITIVE, asserted as current behaviour rather than as desired behaviour.
# A heredoc BODY is not command structure, but the hook receives the whole command string and
# cannot tell, so a commit message mentioning such a push is blocked too. Left unfixed on
# purpose (over-block is the safe direction here; `-F <file>` is the existing convention; and
# modelling heredocs means matching delimiters / `<<-` / quoted forms). Pinned so that a future
# change to this behaviour is a DECISION with a failing test, not a silent drift.
ev 'git commit -F - <<EOF
docs: explain that git push origin +main is forbidden
EOF' | /bin/bash "$GUARD_IMPL" >/dev/null 2>&1; [ $? -eq 2 ] && ok "KNOWN over-block: heredoc body describing a push to main (documented, not fixed)" || no "heredoc behaviour changed — update guard.sh's KNOWN FALSE POSITIVE note"

SECTION="close-gate-nudge.sh"
echo "=== close-gate-nudge.sh ==="
# Off a phase branch → must be silent. Exercised in a temp repo, NOT in $PWD: reading the
# real repo's branch and dirty state as the premise made this assertion fail whenever the
# suite was run from the `feat/phase-*` branch this project mandates for all work — and
# the suite's exit code turns that from a cosmetic red line into a non-zero exit for the whole suite. It also
# kept the hook's throttle file out of whichever repo the suite happened to run from.
SILTMP="$(mktemp -d)" || { echo "FATAL: mktemp -d failed (\$SILTMP)" >&2; exit 1; }
(
  # the nudge's throttle state now lives OUTSIDE the worktree. Pin it into the fixture so
  # the suite neither pollutes the developer's real ~/.claude/plc-state/ nor inherits a throttle
  # from a previous run — the latter would silence the nudge and turn a real failure green.
  export PLC_STATE_DIR="$SILTMP-state"
  cd "$SILTMP"
  git init -q && git config user.email t@t && git config user.name t
  git checkout -q -b not-a-phase-branch 2>/dev/null || true
  echo a > a.txt && git add a.txt && git commit -qm init      # clean tree, non-phase branch
  OUT="$(echo '{}' | /bin/bash "$NUDGE_IMPL" Stop 2>/dev/null)"
  [ -z "$OUT" ] && ok "silent off a phase branch" || no "silent off a phase branch (got: $OUT)"
)
rm -rf "$SILTMP" "$SILTMP-state"

# Integration: temp git repo on a feat/phase-* branch + dirty → must emit JSON.
TMP="$(mktemp -d)" || { echo "FATAL: mktemp -d failed (\$TMP)" >&2; exit 1; }
(
  export PLC_STATE_DIR="$TMP-state"      # throttle state outside the worktree
  cd "$TMP"
  git init -q && git config user.email t@t && git config user.name t
  echo a > a.txt && git add a.txt && git commit -qm init
  git checkout -q -b feat/phase-1.0-test
  echo b > b.txt   # uncommitted → dirty
  rm -rf .claude
  OUT="$(echo '{}' | /bin/bash "$NUDGE_IMPL" Stop 2>/dev/null)"
  # python asserts and exits; the SHELL decides — otherwise the pass never reaches the ledger.
  echo "$OUT" | python3 -c 'import json,sys
d=json.load(sys.stdin)
a=d["hookSpecificOutput"]["additionalContext"]
assert d["hookSpecificOutput"]["hookEventName"]=="Stop"
assert "Definition of Done" in a and "feat/phase-1.0-test" in a' 2>/dev/null \
    && ok "emits nudge JSON on dirty phase branch" \
    || no "emits nudge JSON on dirty phase branch (got: $OUT)"
  # Throttle: second call within 10 min → silent.
  OUT2="$(echo '{}' | /bin/bash "$NUDGE_IMPL" Stop 2>/dev/null)"
  [ -z "$OUT2" ] && ok "throttled (silent within 10 min)" || no "throttle (got: $OUT2)"
)
rm -rf "$TMP" "$TMP-state"

# /clear nudge: clean tree + test-evidence (task close just passed) + occupancy vs floor.
CNTMP="$(mktemp -d)" || { echo "FATAL: mktemp -d failed (\$CNTMP)" >&2; exit 1; }
(
  export PLC_STATE_DIR="$CNTMP-state"    # throttle state outside the worktree
  # Pinned, never inherited. This hook sources the shared library too, so a
  # mutant nudge placed outside the hooks directory would otherwise find no sibling and degrade
  # to "OFF" -- which prints nothing on stdout and reads exactly like "no nudge was due".
  export PLC_FLOOR_LIB="$FLOOR_LIB_IMPL"
  cd "$CNTMP"
  unset PLC_CONTEXT_FLOOR PLC_CONTEXT_FLOOR_PCT PLC_CONTEXT_FLOOR_STEP PLC_CONTEXT_WINDOW
  git init -q && git config user.email t@t && git config user.name t
  printf '.claude/\n*.jsonl\n' > .gitignore
  echo a > a.txt && git add .gitignore a.txt && git commit -qm init
  git checkout -q -b feat/phase-2.0-test
  mkdir -p .claude && echo evidence > .claude/.last-test-run   # clean + tested = task close passed
  mktrans(){ python3 -c 'import json,sys; open(sys.argv[1],"w").write(json.dumps({"type":"assistant","message":{"usage":{"input_tokens":int(sys.argv[2]),"cache_read_input_tokens":0,"cache_creation_input_tokens":0}}})+"\n")' "$1" "$2"; }
  evn(){ python3 -c 'import json,sys; print(json.dumps({"session_id":"s","transcript_path":sys.argv[1]}))' "$1"; }

  # under floor (120K < default 150K) → silent
  mktrans t-low.jsonl 120000
  OUT="$(evn "$CNTMP/t-low.jsonl" | /bin/bash "$NUDGE_IMPL" Stop 2>/dev/null)"
  [ -z "$OUT" ] && ok "clear-nudge silent under floor" || no "clear-nudge silent under floor (got: $OUT)"

  # ── library failure shapes (nudge side): a library that is absent, syntactically broken, or calls
  # `exit` must all degrade the SAME way -- fail open, one stderr line, empty stdout. `[ -r ]`
  # distinguishes none of the three, and an adopter's failed or partial plugin update produces
  # the broken shapes far more often than a clean removal.
  #
  # Placed HERE, inside the section that has already built a clean repo on a `feat/phase-*`
  # branch with test evidence. Measured the hard way: driving this by hand never reached the
  # library block at all, because the hook's dirty-tree branch exits 0 long before it -- so the
  # three "results" collected that way were the dirty-tree nudge and two throttled silences.
  mktrans t-lib.jsonl 500000
  # The fixture libraries live OUTSIDE the repo. Measured: writing them into $CNTMP made the
  # worktree DIRTY, the hook's dirty-tree branch then took precedence over the clear-nudge path,
  # and FIVE later rows in this section went red for a reason that had nothing to do with them.
  LIBDIR="$CNTMP-libs"; mkdir -p "$LIBDIR"
  printf 'PLC_FLOOR_JQ_DEFS="$(cat <<EOF\nunterminated\n' > "$LIBDIR/lib-syntaxerr.sh"
  printf '#!/usr/bin/env bash\nexit 1\n' > "$LIBDIR/lib-exits.sh"
  # The two shapes a bare emptiness check is blind to: they source CLEANLY and leave the
  # variable NON-EMPTY, so a bare `-z` check waves them through into the swallowing fallback.
  printf 'PLC_FLOOR_JQ_DEFS="this is not jq at all ((("\n' > "$LIBDIR/lib-garbage.sh"
  printf 'PLC_FLOOR_JQ_DEFS="def unrelated: 1;"\n' > "$LIBDIR/lib-nothing.sh"
  # The two shapes an absent-only probe is blind to -- see the floor section for the
  # measurements. Kept on BOTH sides because the probe is duplicated per hook, and a probe that
  # is only regression-tested on one side is exactly the drift that goes unnoticed.
cat > "$LIBDIR/lib-envblind.sh" <<'FXEOF'
PLC_FLOOR_JQ_DEFS='
  def trim: sub("^\\s+"; "") | sub("\\s+$"; "");
  def intenv($n; $unset; $empty): $unset;
  def floatenv($n; $unset; $empty): $unset;
'
FXEOF
cat > "$LIBDIR/lib-without-times-one.sh" <<'FXEOF'
PLC_FLOOR_JQ_DEFS='
  def trim: sub("^\\s+"; "") | sub("\\s+$"; "");
  def intenv($n; $unset; $empty):
    env[$n] as $v
    | if   $v == null then $unset
      elif $v == ""   then $empty
      elif ($v | test("^\\s*[+-]?[0-9]+\\s*$")) then ($v | trim | tonumber)
      else $unset end;
  def floatenv($n; $unset; $empty):
    env[$n] as $v
    | if   $v == null then $unset
      elif $v == ""   then $empty
      else (($v | trim | tonumber?) // $unset) end;
'
FXEOF
  for LIBCASE in absent:"$LIBDIR/no-such-lib.sh" broken:"$LIBDIR/lib-syntaxerr.sh" exiting:"$LIBDIR/lib-exits.sh" garbage:"$LIBDIR/lib-garbage.sh" defining-nothing:"$LIBDIR/lib-nothing.sh" env-blind:"$LIBDIR/lib-envblind.sh" without-times-one:"$LIBDIR/lib-without-times-one.sh"; do
    LIBNAME="${LIBCASE%%:*}"; LIBPATH="${LIBCASE#*:}"
    OUT="$(evn "$CNTMP/t-lib.jsonl" | PLC_FLOOR_LIB="$LIBPATH" /bin/bash "$NUDGE_IMPL" Stop 2>"$LIBDIR/$LIBNAME.err")"; RC=$?
    # Counted, not grepped -- see the floor side's note. This side already asserted
    # empty stdout; what it could not see was a SECOND stderr line.
    ERRN="$(grep -c 'close-gate nudge OFF' "$LIBDIR/$LIBNAME.err" 2>/dev/null || true)"
    ERRTOT="$(wc -l < "$LIBDIR/$LIBNAME.err" | tr -d ' ')"
    { [ "$RC" -eq 0 ] && [ -z "$OUT" ] && [ "${ERRN:-0}" -eq 1 ] && [ "${ERRTOT:-0}" -eq 1 ]; } \
      && ok "nudge degrades identically on a $LIBNAME library (fail open + exactly one line, empty stdout)" \
      || no "nudge on a $LIBNAME library (rc=$RC matching-lines=$ERRN total-stderr-lines=$ERRTOT out=[$OUT] err=[$(tr -d '\n' < "$LIBDIR/$LIBNAME.err")])"
  done

  # floor disabled → silent even far over
  mktrans t-dis.jsonl 500000
  OUT="$(evn "$CNTMP/t-dis.jsonl" | PLC_CONTEXT_FLOOR=0 /bin/bash "$NUDGE_IMPL" Stop 2>/dev/null)"
  [ -z "$OUT" ] && ok "clear-nudge silent when floor disabled" || no "clear-nudge floor=0 (got: $OUT)"

  # no transcript_path in event → silent (fail-open)
  OUT="$(echo '{}' | /bin/bash "$NUDGE_IMPL" Stop 2>/dev/null)"
  [ -z "$OUT" ] && ok "clear-nudge fail-open without transcript" || no "clear-nudge fail-open (got: $OUT)"

  # malformed (non-JSON) event on stdin → silent + exit 0 (fail-open)
  OUT="$(printf '{ not json' | /bin/bash "$NUDGE_IMPL" Stop 2>/dev/null)"; RC=$?
  { [ -z "$OUT" ] && [ "$RC" -eq 0 ]; } && ok "clear-nudge fail-open on malformed event JSON" || no "clear-nudge malformed event (rc=$RC, got: $OUT)"

  # over floor (200K ≥ 150K) → emits /clear nudge JSON with occupancy
  mktrans t-hi.jsonl 200000
  OUT="$(evn "$CNTMP/t-hi.jsonl" | /bin/bash "$NUDGE_IMPL" Stop 2>/dev/null)"
  echo "$OUT" | python3 -c 'import json,sys
d=json.load(sys.stdin)
a=d["hookSpecificOutput"]["additionalContext"]
assert d["hookSpecificOutput"]["hookEventName"]=="Stop"
assert "/clear" in a and "200K" in a and "150K" in a' 2>/dev/null \
    && ok "clear-nudge emits over floor (clean+tested)" \
    || no "clear-nudge emits over floor (got: $OUT)"

  # throttled second call → silent
  OUT="$(evn "$CNTMP/t-hi.jsonl" | /bin/bash "$NUDGE_IMPL" Stop 2>/dev/null)"
  [ -z "$OUT" ] && ok "clear-nudge throttled (silent within 10 min)" || no "clear-nudge throttle (got: $OUT)"

  # window-% mode: 70% of 1M = 700K floor → 720K emits (after clearing throttle)
  rm -rf "$PLC_STATE_DIR"
  mktrans t-pct.jsonl 720000
  OUT="$(evn "$CNTMP/t-pct.jsonl" | PLC_CONTEXT_FLOOR_PCT=70 PLC_CONTEXT_WINDOW=1000000 /bin/bash "$NUDGE_IMPL" Stop 2>/dev/null)"
  echo "$OUT" | grep -q '/clear' && ok "clear-nudge honors window-% floor" || no "clear-nudge window-% (got: $OUT)"

  # a SUBNORMAL percentage. python's float() UNDERFLOWS 1e-400 to 0.0, so `pct > 0` is
  # False there and the hook falls through to the ABSOLUTE floor -- 160K over 150K, so it nudges.
  # jq keeps the literal at arbitrary precision, so `1E-400 > 0` was True, the %-branch was taken,
  # the resulting floor rounded to 0, and the hook went SILENT: a user who set a subnormal
  # percentage silently lost the nudge entirely. This row is the executable form of that.
  rm -rf "$PLC_STATE_DIR"
  mktrans t-subnormal.jsonl 160000
  OUT="$(evn "$CNTMP/t-subnormal.jsonl" | PLC_CONTEXT_FLOOR_PCT=1e-400 PLC_CONTEXT_WINDOW=1000000 /bin/bash "$NUDGE_IMPL" Stop 2>/dev/null)"
  echo "$OUT" | grep -q '/clear' \
    && ok "a subnormal PLC_CONTEXT_FLOOR_PCT falls through to the absolute floor" \
    || no "subnormal pct must not silence the nudge (got: '$OUT')"

  # custom absolute floor honored: 90K over an 80K floor emits (default 150K would stay silent)
  rm -rf "$PLC_STATE_DIR"
  mktrans t-cust.jsonl 90000
  OUT="$(evn "$CNTMP/t-cust.jsonl" | PLC_CONTEXT_FLOOR=80000 /bin/bash "$NUDGE_IMPL" Stop 2>/dev/null)"
  echo "$OUT" | grep -q '/clear' && ok "clear-nudge honors custom PLC_CONTEXT_FLOOR" || no "clear-nudge custom floor (got: $OUT)"

  # dirty tree still gets the ORIGINAL close-gate nudge, not the /clear one
  echo b > b.txt
  OUT="$(evn "$CNTMP/t-hi.jsonl" | /bin/bash "$NUDGE_IMPL" Stop 2>/dev/null)"
  { echo "$OUT" | grep -q 'Definition of Done' && ! echo "$OUT" | grep -q '/clear before the next task'; } && ok "dirty tree keeps original close-gate nudge" || no "dirty tree nudge precedence (got: $OUT)"
)
rm -rf "$CNTMP" "$CNTMP-state"

echo
SECTION="tasklist-first.sh"
echo "=== tasklist-first.sh (enumerated-list guard, jq) ==="
TLTMP="$(mktemp -d)" || { echo "FATAL: mktemp -d failed (\$TLTMP)" >&2; exit 1; }
(
  export TMPDIR="$TLTMP"
  unset PLC_TASKLIST_GUARD PLC_TASKLIST_GATE_TASK PLC_TASKLIST_MIN
  MDIR="$TLTMP/plc-tasklist-guard"
  # Every builder carries a cwd inside the fixture. Without it the hook's marker path
  #   GMARK="${CWD:+$CWD/}.claude/.gate-runs/last-run"   (tasklist-first.sh)
  # degrades to a RELATIVE path and resolves against whatever directory the suite was launched
  # from — i.e. this checkout, whose real .claude/.gate-runs/last-run then leaks into the test.
  # Symptom: 7 failures when run from the repo root, 0 from anywhere else. The re-arm group
  # below already had its own cwd-carrying builder (evBashCwd) for exactly this reason; the fix
  # was applied there and not to the five basic builders, so the leak survived in the group that
  # runs first.
  ISOCWD="$TLTMP/isolated-cwd"; mkdir -p "$ISOCWD"
  # Event builders (test harness only — python3 here is dev/CI, not the runtime hook).
  evEdit(){ python3 -c 'import json,sys; print(json.dumps({"session_id":sys.argv[1],"cwd":sys.argv[3],"tool_name":"Edit","tool_input":{"file_path":sys.argv[2]}}))' "$1" "$2" "$ISOCWD"; }
  evBash(){ python3 -c 'import json,sys; print(json.dumps({"session_id":sys.argv[1],"cwd":sys.argv[3],"tool_name":"Bash","tool_input":{"command":sys.argv[2]}}))' "$1" "$2" "$ISOCWD"; }
  evTask(){ python3 -c 'import json,sys; print(json.dumps({"session_id":sys.argv[1],"cwd":sys.argv[2],"tool_name":"Task","tool_input":{}}))' "$1" "$ISOCWD"; }
  evTC(){   python3 -c 'import json,sys; print(json.dumps({"session_id":sys.argv[1],"cwd":sys.argv[2],"tool_name":"TaskCreate","tool_input":{}}))' "$1" "$ISOCWD"; }
  evTodo(){ python3 -c 'import json,sys; print(json.dumps({"session_id":sys.argv[1],"cwd":sys.argv[3],"tool_name":"TodoWrite","tool_input":{"todos":[{"content":"x"}]*int(sys.argv[2])}}))' "$1" "$2" "$ISOCWD"; }

  # --- counter: one TaskCreate is NOT enough (count 1 < 3) -> edit still blocks ---
  evTC c1 | /bin/bash "$TASKLIST_IMPL" mark >/dev/null 2>&1
  evEdit c1 /tmp/x.md | /bin/bash "$TASKLIST_IMPL" check >/dev/null 2>&1; [ $? -eq 2 ] && ok "single TaskCreate does not satisfy guard (1<3)" || no "single TaskCreate should not satisfy"

  # --- counter: three TaskCreate calls -> enumerated list exists -> edit passes ---
  evTC c3 | /bin/bash "$TASKLIST_IMPL" mark >/dev/null 2>&1
  evTC c3 | /bin/bash "$TASKLIST_IMPL" mark >/dev/null 2>&1
  evTC c3 | /bin/bash "$TASKLIST_IMPL" mark >/dev/null 2>&1
  { [ -e "$MDIR/c3.seen" ]; } && ok "3 TaskCreate calls set the seen marker" || no "3 TaskCreate should set seen"
  evEdit c3 /tmp/x.md | /bin/bash "$TASKLIST_IMPL" check >/dev/null 2>&1; [ $? -eq 0 ] && ok "allows edit after 3-task list" || no "allows after 3-task list"

  # --- TodoWrite shape: length >= 3 satisfies in one call; length 1 does not ---
  evTodo t3 3 | /bin/bash "$TASKLIST_IMPL" mark >/dev/null 2>&1
  { [ -e "$MDIR/t3.seen" ]; } && ok "TodoWrite len>=3 sets seen in one call" || no "TodoWrite len>=3 sets seen"
  evTodo t1 1 | /bin/bash "$TASKLIST_IMPL" mark >/dev/null 2>&1
  { [ ! -e "$MDIR/t1.seen" ]; } && ok "TodoWrite len 1 does not set seen" || no "TodoWrite len 1 should not set seen"

  # --- the no-primitive host. No mark ever fires, because the host has no task tool.
  # This is the case the guard used to handle by blocking once and then permitting
  # everything in silence — enforcement in the transcript, nothing in reality.
  PROJ="$TLTMP/proj"; mkdir -p "$PROJ/.claude"
  ART="$PROJ/.claude/tasklist.md"
  evEditC(){ python3 -c 'import json,sys; print(json.dumps({"session_id":sys.argv[1],"cwd":sys.argv[2],"tool_name":"Edit","tool_input":{"file_path":sys.argv[3]}}))' "$1" "$PROJ" "$2"; }

  # 1. first gated call blocks once AND hands over a nonce to transcribe
  ERR="$TLTMP/np.err"
  evEditC np /tmp/x.md | /bin/bash "$TASKLIST_IMPL" check >/dev/null 2>"$ERR"; RC=$?
  NV="$(grep -o 'plc-tasklist: [0-9a-f]*' "$ERR" 2>/dev/null | cut -d' ' -f2 || true)"
  { [ "$RC" -eq 2 ] && [ -n "$NV" ]; } \
    && ok "no-primitive host blocks once and mints a nonce" \
    || no "expected exit 2 carrying a nonce (rc=$RC nonce='$NV')"
  grep -q "\.claude/tasklist\.md" "$ERR" \
    && ok "block message names the artifact path" \
    || no "block message must name .claude/tasklist.md"

  # 2. THE FIX: after that block the guard must not go silent. Every later gated call
  #    reports UNVERIFIED — allowed, but never indistinguishable from a verified pass.
  # No `|| true` inside the substitution: it would be what $? reports, pinning RC to 0 and
  # killing the failing half of this assertion. The script runs without -e.
  OUT="$(evEditC np /tmp/y.md | /bin/bash "$TASKLIST_IMPL" check 2>/dev/null)"; RC=$?
  { [ "$RC" -eq 0 ] && printf '%s' "$OUT" | grep -q 'UNVERIFIED'; } \
    && ok "post-block calls report UNVERIFIED instead of silence" \
    || no "expected an UNVERIFIED payload (rc=$RC out='$OUT')"
  # The FIELDS are the assertion, not just "some JSON came out". `allow` proceeds WITHOUT
  # the user's permission prompt (an auto-approval the guard has no business granting), and
  # `permissionDecisionReason` is only documented to reach Claude on deny/ask — so the first
  # version of this payload silently auto-approved every gated call and told no one.
  printf '%s' "$OUT" | jq -e '.hookSpecificOutput.permissionDecision=="defer"' >/dev/null 2>&1 \
    && ok "UNVERIFIED payload defers (does not auto-approve past the permission prompt)" \
    || no "permissionDecision must be 'defer' — 'allow' bypasses the user's prompt"
  printf '%s' "$OUT" | jq -e '(.hookSpecificOutput.additionalContext//"")|test("UNVERIFIED")' >/dev/null 2>&1 \
    && ok "notice rides additionalContext (the field that reaches the model)" \
    || no "UNVERIFIED must be in additionalContext, not permissionDecisionReason"
  printf '%s' "$OUT" | jq -e 'has("hookSpecificOutput") and (.hookSpecificOutput|has("permissionDecisionReason")|not)' >/dev/null 2>&1 \
    && ok "no permissionDecisionReason under defer (undocumented delivery)" \
    || no "permissionDecisionReason is not delivered under defer — do not rely on it"

  # 3. the portable artifact satisfies the guard with no task tool anywhere in sight
  printf '<!-- plc-tasklist: %s -->\n- [ ] a\n- [ ] b\n- [x] c\n' "$NV" > "$ART"
  OUT="$(evEditC np /tmp/z.md | /bin/bash "$TASKLIST_IMPL" check 2>&1)"; RC=$?
  { [ "$RC" -eq 0 ] && [ -z "$OUT" ]; } \
    && ok "valid artifact satisfies the guard silently" \
    || no "valid artifact should allow with no output (rc=$RC out='$OUT')"

  # 4. too few steps is not a list
  printf '<!-- plc-tasklist: %s -->\n- [ ] only one\n' "$NV" > "$ART"
  evEditC np /tmp/z.md | /bin/bash "$TASKLIST_IMPL" check 2>/dev/null | grep -q 'UNVERIFIED' \
    && ok "fewer than 3 checkbox lines does not satisfy" \
    || no "1 checkbox line should not satisfy"

  # 4b. `- [/]` is the in-progress state SKILL.md:102 defines, and it counts. Shaped as the
  #     list a user following the convention actually has -- exactly N items, one of them in
  #     progress. Before the fix this counted 2 of 3 and printed UNVERIFIED, i.e. the guard
  #     punished the convention it documents.
  printf '<!-- plc-tasklist: %s -->\n- [x] a\n- [/] b\n- [ ] c\n' "$NV" > "$ART"
  OUT="$(evEditC np /tmp/z.md | /bin/bash "$TASKLIST_IMPL" check 2>&1)"; RC=$?
  { [ "$RC" -eq 0 ] && [ -z "$OUT" ]; } \
    && ok "an in-progress '- [/]' item counts toward the guard (SKILL.md:102 contract)" \
    || no "'- [/]' must count (rc=$RC out='$OUT')"

  # 4c. ...and the count stays a THRESHOLD, not a rubber stamp. Without this row, 4b also passes
  #     under an implementation that counts every line in the file, which would satisfy the guard
  #     with any three lines of prose.
  printf '<!-- plc-tasklist: %s -->\n- [/] a\n- [/] b\n' "$NV" > "$ART"
  evEditC np /tmp/z.md | /bin/bash "$TASKLIST_IMPL" check 2>/dev/null | grep -q 'UNVERIFIED' \
    && ok "two '- [/]' lines still do not reach N=3" \
    || no "counting must stay a threshold, not accept any list containing '- [/]'"

  # 5. LAST PHASE'S list must not satisfy THIS phase. The nonce is why this is checked
  #    without consulting an mtime — a checked-out tree may sync through a file-syncing daemon that re-touches
  #    files, so a timestamp is not evidence that anything was rewritten.
  printf '<!-- plc-tasklist: deadbeefcafe -->\n- [ ] a\n- [ ] b\n- [ ] c\n' > "$ART"
  evEditC np /tmp/z.md | /bin/bash "$TASKLIST_IMPL" check 2>/dev/null | grep -q 'UNVERIFIED' \
    && ok "a stale nonce from a previous phase does not satisfy" \
    || no "stale nonce must not satisfy"

  # 6. writing the artifact is never gated, or the guard deadlocks: the only way to satisfy
  #    it is a Write, and Write is what it gates.
  evEditC np2 "$ART" | /bin/bash "$TASKLIST_IMPL" check >/dev/null 2>&1; RC=$?
  [ "$RC" -eq 0 ] && ok "writing the artifact itself is exempt" \
                  || no "artifact write must never block (rc=$RC)"

  # 6b/6c. The absolute-override case, and the property that CAN be observed. `ART_REL` is
  # `${PLC_TASKLIST_FILE:-.claude/tasklist.md}` -- user-configurable, NOT a fixed literal -- and the
  # site concatenated it unconditionally onto the event cwd, so an ABSOLUTE override became
  # `$CWD//abs/path` and never resolved. Measured: with the override set and a valid
  # artifact at it, the guard printed UNVERIFIED. The documented escape hatch was inert in the only
  # configuration real Claude Code produces (it always sends a cwd).
  #
  # These two rows are a PAIR and each catches a different mistake. 6b is the defect. 6c is the
  # regression control for the obvious fix: backfilling `CWD` from the process cwd and dropping the
  # `${CWD:+...}` guard resolves 6b
  # and breaks 6c, because it prefixes the absolute path again. Neither row alone distinguishes the
  # two, and the hook's own process-cwd dependence is NOT what either of them tests: that one is
  # reproduced and still open (see the CWD note in tasklist-first.sh), because the fix and the defect both resolve against
  # the process cwd, so no row can separate them.
  ABSART="$TLTMP/pinned-tasklist.md"
  evEditNoCwd(){ python3 -c 'import json,sys; print(json.dumps({"session_id":sys.argv[1],"tool_name":"Edit","tool_input":{"file_path":sys.argv[2]}}))' "$1" "$2"; }
  # First call blocks and mints this session's nonce; the artifact then transcribes it. An EMPTY
  # nonce would make the artifact satisfy any check (`grep -qF -- ""` matches every line), so its
  # presence is part of the assertion rather than an assumption.
  evEditC ab1 /tmp/z.md | PLC_TASKLIST_FILE="$ABSART" /bin/bash "$TASKLIST_IMPL" check >/dev/null 2>&1
  NVA="$(cat "$MDIR/ab1.nonce" 2>/dev/null || true)"
  printf '<!-- plc-tasklist: %s -->\n- [ ] a\n- [ ] b\n- [x] c\n' "$NVA" > "$ABSART"
  OUT="$(evEditC ab1 /tmp/z.md | PLC_TASKLIST_FILE="$ABSART" /bin/bash "$TASKLIST_IMPL" check 2>&1)"; RC=$?
  { [ -n "$NVA" ] && [ "$RC" -eq 0 ] && [ -z "$OUT" ]; } \
    && ok "an absolute PLC_TASKLIST_FILE resolves when the event carries a cwd" \
    || no "absolute override must not be prefixed with the event cwd (nonce='$NVA' rc=$RC out='$OUT')"

  # 6c runs from a directory with no `.claude/` in it AND with re-arm disabled, both deliberately:
  # with no event cwd the re-arm marker path degrades the same way, so a gate marker in the process
  # cwd would wipe this session's markers and `exit 0` SILENTLY -- which this row would have scored
  # as a pass for entirely the wrong reason. With re-arm off, rc 0 plus no output can only mean the
  # artifact predicate resolved.
  OUT="$(cd "$ISOCWD" && evEditNoCwd ab1 /tmp/z.md | PLC_TASKLIST_FILE="$ABSART" PLC_TASKLIST_REARM=0 /bin/bash "$TASKLIST_IMPL" check 2>&1)"; RC=$?
  { [ -n "$NVA" ] && [ "$RC" -eq 0 ] && [ -z "$OUT" ]; } \
    && ok "...and still resolves when the event carries no cwd at all (regression control)" \
    || no "absolute override must survive a missing event cwd (nonce='$NVA' rc=$RC out='$OUT')"

  # --- block-once on file edit with no list ---
  evEdit e1 /tmp/x.md | /bin/bash "$TASKLIST_IMPL" check >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 2 ] && [ -f "$MDIR/e1.nudged" ]; } && ok "blocks first edit without list" || no "blocks first edit without list"
  evEdit e1 /tmp/x.md | /bin/bash "$TASKLIST_IMPL" check >/dev/null 2>&1; [ $? -eq 0 ] && ok "block-once (second edit passes)" || no "block-once"

  # --- Bash: git commit/push is gated; read-only Bash is not ---
  evBash b1 'git commit -m "feat: x"' | /bin/bash "$TASKLIST_IMPL" check >/dev/null 2>&1; [ $? -eq 2 ] && ok "blocks git commit without list" || no "blocks git commit without list"
  evBash b2 'git push origin feat/x'  | /bin/bash "$TASKLIST_IMPL" check >/dev/null 2>&1; [ $? -eq 2 ] && ok "blocks git push without list" || no "blocks git push without list"
  evBash b3 'git status'              | /bin/bash "$TASKLIST_IMPL" check >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 0 ] && [ ! -f "$MDIR/b3.nudged" ]; } && ok "read-only Bash (git status) not gated" || no "read-only Bash should pass"
  evBash b4 'ls -la'                  | /bin/bash "$TASKLIST_IMPL" check >/dev/null 2>&1; [ $? -eq 0 ] && ok "non-git Bash not gated" || no "non-git Bash should pass"

  # --- per-phase re-arm: a close-gate run wipes markers so the next phase re-blocks ---
  # helper: give a session a satisfied 3-task list (seen marker set).
  arm3(){ evTC "$1" | /bin/bash "$TASKLIST_IMPL" mark >/dev/null 2>&1
          evTC "$1" | /bin/bash "$TASKLIST_IMPL" mark >/dev/null 2>&1
          evTC "$1" | /bin/bash "$TASKLIST_IMPL" mark >/dev/null 2>&1; }

  # re-arm keys on a MARKER THE GATE WRITES, never on a token in the command string.
  # The whole point is that the two are different facts. `wc -l` on the gate file and `git add`
  # of the gate file each used to count as a phase close,
  # and no amount of narrowing "the name appears in a string" ever
  # turns it into "the thing ran".
  RREPO="$TLTMP/rearm-repo"; mkdir -p "$RREPO/.claude/.gate-runs"
  GM="$RREPO/.claude/.gate-runs/last-run"
  # Event carrying a cwd, so the hook resolves the marker inside the fixture and never touches
  # the checkout this suite is running from.
  evBashCwd(){ python3 -c 'import json,sys; print(json.dumps({"session_id":sys.argv[1],"cwd":sys.argv[3],"tool_name":"Bash","tool_input":{"command":sys.argv[2]}}))' "$1" "$2" "$3"; }
  mkmark(){ printf 'run=%s\nexit=%s\nphase=T1\nhead=deadbeef\nat=1970-01-01T00:00:00Z\n' "$1" "$2" > "$GM"; }

  # --- the two commands that used to false-re-arm: reading and staging the gate file ---
  arm3 rg1; rm -f "$GM"
  evBashCwd rg1 'wc -l scripts/close-gate.sh' "$RREPO" | /bin/bash "$TASKLIST_IMPL" check >/dev/null 2>&1
  { [ -e "$MDIR/rg1.seen" ]; } && ok "reading the gate file does NOT re-arm" || no "false re-arm: wc -l on the gate file"

  arm3 rg2; rm -f "$GM"
  evBashCwd rg2 'git add scripts/close-gate.sh' "$RREPO" | /bin/bash "$TASKLIST_IMPL" check >/dev/null 2>&1
  { [ -e "$MDIR/rg2.seen" ]; } && ok "staging the gate file does NOT re-arm" || no "false re-arm: git add of the gate file"

  # --- the command NAME alone is no longer a signal at all ---
  arm3 rg3; rm -f "$GM"
  evBashCwd rg3 'make task-done' "$RREPO" | /bin/bash "$TASKLIST_IMPL" check >/dev/null 2>&1
  { [ -e "$MDIR/rg3.seen" ]; } && ok "'make task-done' with no gate marker does NOT re-arm" || no "token scan still live"

  # --- a real, passing gate run DOES re-arm ---
  arm3 rg4; mkmark run-aaa 0
  evBashCwd rg4 'echo unrelated' "$RREPO" | /bin/bash "$TASKLIST_IMPL" check >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 0 ] && [ ! -e "$MDIR/rg4.seen" ] && [ ! -e "$MDIR/rg4.count" ] && [ ! -e "$MDIR/rg4.nudged" ]; } \
    && ok "a passing gate marker re-arms (wipes seen/count/nudged)" || no "passing gate marker should re-arm"
  evEdit rg4 /tmp/x.md | /bin/bash "$TASKLIST_IMPL" check >/dev/null 2>&1; [ $? -eq 2 ] && ok "next edit re-blocks after re-arm" || no "next edit should re-block"

  # --- the SAME run re-arms exactly once (the per-run id is what makes a stale marker inert) ---
  arm3 rg5   # marker still says run-aaa, already consumed by rg4's session? no — per session.
  evBashCwd rg5 'echo unrelated' "$RREPO" | /bin/bash "$TASKLIST_IMPL" check >/dev/null 2>&1
  { [ ! -e "$MDIR/rg5.seen" ]; } && ok "a fresh session consumes the marker once" || no "fresh session should re-arm once"
  arm3 rg5   # re-satisfy; same marker, same run id -> must NOT re-arm again
  evBashCwd rg5 'echo unrelated' "$RREPO" | /bin/bash "$TASKLIST_IMPL" check >/dev/null 2>&1
  { [ -e "$MDIR/rg5.seen" ]; } && ok "the same gate run does NOT re-arm twice" || no "stale marker re-armed again"

  # --- a FAILING gate run must not re-arm. The old PreToolUse token scan fired when the gate
  #     command was ABOUT to run, so a gate that then failed re-armed exactly like a passing one.
  arm3 rg6; mkmark run-bbb 1
  evBashCwd rg6 'echo unrelated' "$RREPO" | /bin/bash "$TASKLIST_IMPL" check >/dev/null 2>&1
  { [ -e "$MDIR/rg6.seen" ]; } && ok "a FAILING gate run does NOT re-arm (timing defect)" || no "failing gate re-armed"
  # ...and it is still consumed, so the next call does not reconsider it.
  arm3 rg7; mkmark run-ccc 1
  evBashCwd rg7 'echo unrelated' "$RREPO" | /bin/bash "$TASKLIST_IMPL" check >/dev/null 2>&1
  evBashCwd rg7 'echo unrelated' "$RREPO" | /bin/bash "$TASKLIST_IMPL" check >/dev/null 2>&1
  { [ -e "$MDIR/rg7.seen" ]; } && ok "a failing gate run stays non-re-arming on re-read" || no "failing marker re-armed on second look"

  # escape hatch: PLC_TASKLIST_REARM=0 -> even a fresh passing marker does not reset.
  arm3 rg8; mkmark run-ddd 0
  evBashCwd rg8 'echo unrelated' "$RREPO" | PLC_TASKLIST_REARM=0 /bin/bash "$TASKLIST_IMPL" check >/dev/null 2>&1
  { [ -e "$MDIR/rg8.seen" ]; } && ok "PLC_TASKLIST_REARM=0 disables re-arm" || no "REARM=0 should keep seen"

  # --- Task (subagent dispatch): off by default, gated when PLC_TASKLIST_GATE_TASK=1 ---
  evTask k1 | /bin/bash "$TASKLIST_IMPL" check >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 0 ] && [ ! -f "$MDIR/k1.nudged" ]; } && ok "Task dispatch not gated by default (intent-gate Explore safe)" || no "Task should pass by default"
  evTask k2 | PLC_TASKLIST_GATE_TASK=1 /bin/bash "$TASKLIST_IMPL" check >/dev/null 2>&1; [ $? -eq 2 ] && ok "Task gated when PLC_TASKLIST_GATE_TASK=1" || no "Task gated when flag on"

  # --- RESUME.md exempt even with no list (deadlock guard) ---
  evEdit r1 /some/proj/RESUME.md | /bin/bash "$TASKLIST_IMPL" check >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 0 ] && [ ! -f "$MDIR/r1.nudged" ]; } && ok "RESUME.md write exempt" || no "RESUME.md exempt"

  # --- escape hatch ---
  evEdit h1 /tmp/x.md | PLC_TASKLIST_GUARD=0 /bin/bash "$TASKLIST_IMPL" check >/dev/null 2>&1; [ $? -eq 0 ] && ok "PLC_TASKLIST_GUARD=0 disables" || no "escape hatch"

  # --- fail-open: malformed JSON / missing session_id ---
  echo '{ not json' | /bin/bash "$TASKLIST_IMPL" check >/dev/null 2>&1; [ $? -eq 0 ] && ok "fail-open on malformed input" || no "fail-open malformed"
  echo '{}' | /bin/bash "$TASKLIST_IMPL" check >/dev/null 2>&1; [ $? -eq 0 ] && ok "fail-open on missing session_id" || no "fail-open missing sid"
)
rm -rf "$TLTMP"

echo
SECTION="frontmatter"
echo "=== frontmatter YAML parses ==="
if python3 - "$HERE/.." <<'PY'
import yaml, sys
raw=open(sys.argv[1] + "/SKILL.md").read()
d=yaml.safe_load(raw.split("---",2)[1])
h=d.get("hooks",{})
assert "PreToolUse" in h and "Stop" in h and "SubagentStop" in h, "missing hook events: %s"%list(h)
root="${QODER_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}/skills/project-lifecycle/hooks/"
cmds={
  "PreToolUse": h["PreToolUse"][0]["hooks"][0]["command"],
  "Stop": h["Stop"][0]["hooks"][0]["command"],
  "SubagentStop": h["SubagentStop"][0]["hooks"][0]["command"],
}
assert cmds["PreToolUse"]==root+"guard.sh", cmds["PreToolUse"]
assert cmds["Stop"]==root+"close-gate-nudge.sh Stop", cmds["Stop"]
assert cmds["SubagentStop"]==root+"close-gate-nudge.sh SubagentStop", cmds["SubagentStop"]
pre={m.get("matcher",""): m["hooks"][0]["command"] for m in h["PreToolUse"]}
assert pre.get("TaskCreate|TodoWrite")==root+"tasklist-first.sh mark", pre
# the check hook fires on a single combined matcher (distinct from guard's "Bash" key);
# assert it exists and its matcher covers commit/edit/subagent surfaces.
checks=[mm for mm,c in pre.items() if c==root+"tasklist-first.sh check"]
assert len(checks)==1, ("expected exactly one check matcher", pre)
cm=checks[0]
for tok in ("Bash","Task","Edit","Write","MultiEdit","NotebookEdit"):
    assert tok in cm, ("check matcher missing "+tok, cm)
PY
then ok "SKILL.md frontmatter hooks block valid (all 3 commands)"; else no "SKILL.md frontmatter hooks block valid (all 3 commands)"; fi

echo
SECTION="context-floor.sh"
echo "=== context-floor.sh (enforce-only, self-arming) ==="

#
# All seven call sites in this section (the `cf()` wrapper plus six inline invocations) route through CF_IMPL. Six would not have been enough: `cf()` is the wrapper the
# checkpoint and clear-path rows use, i.e. exactly the rows a context-floor mutant moves, while the
# six inline ones are floor-CONFIGURATION rows a behaviour mutant leaves alone. Converting only the
# inline six would have produced a green check and a suite still ignoring the mutant where it counts.
#
# Absolutised through `impl_path`: a relative PLC_CF_NEW is exactly what a
# mutation run hands in, and rows that run the hook from another directory would otherwise lose it.
CF_IMPL="$(impl_path "${PLC_CF_NEW:-}" "$HERE/context-floor.sh")" || exit 2
CFTMP="$(mktemp -d)" || { echo "FATAL: mktemp -d failed (\$CFTMP)" >&2; exit 1; }
(
  export TMPDIR="$CFTMP"
  # PINNED, never inherited: a stale PLC_CONTEXT_* or PLC_FLOOR_LIB in the caller's
  # environment must not be able to reach a mutation run and make it a hybrid.
  export PLC_FLOOR_LIB="$FLOOR_LIB_IMPL"
  # hermetic: don't inherit a caller's floor config (e.g. settings.json env block)
  unset PLC_CONTEXT_FLOOR PLC_CONTEXT_FLOOR_PCT PLC_CONTEXT_FLOOR_STEP PLC_CONTEXT_WINDOW
  mktrans(){ python3 -c 'import json,sys; open(sys.argv[1],"w").write(json.dumps({"type":"assistant","message":{"usage":{"input_tokens":int(sys.argv[2]),"cache_read_input_tokens":0,"cache_creation_input_tokens":0}}})+"\n")' "$1" "$2"; }
  evc(){ python3 -c 'import json,sys; print(json.dumps({"session_id":sys.argv[2],"transcript_path":sys.argv[1],"cwd":sys.argv[3]}))' "$1" "$2" "$3"; }
  cf(){ /bin/bash "$CF_IMPL"; }   # reads stdin; PreToolUse:Edit|Write
  M="$CFTMP/plc-context-floor"

  # under floor -> allow, no marker
  T="$CFTMP/below.jsonl"; mktrans "$T" 120000
  evc "$T" b "$CFTMP" | cf >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 0 ] && [ ! -f "$M/b.marker" ]; } && ok "allows under floor" || no "allows under floor"

  # over floor, no RESUME -> self-arm + block (exit 2)
  T="$CFTMP/over.jsonl"; mktrans "$T" 160000
  evc "$T" a "$CFTMP" | cf >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 2 ] && [ -f "$M/a.marker" ]; } && ok "self-arms + blocks over floor (no RESUME)" || no "self-arms + blocks over floor"

  # still blocked while RESUME stale (older than marker)
  echo stale > "$CFTMP/RESUME.md"; sleep 1; touch "$M/a.marker"   # bump marker newer than RESUME
  evc "$T" a "$CFTMP" | cf >/dev/null 2>&1; [ $? -eq 2 ] && ok "stays blocked while RESUME stale" || no "stays blocked while RESUME stale"

  # fresh RESUME -> clear marker + write clearedat + allow
  sleep 1; echo fresh > "$CFTMP/RESUME.md"
  evc "$T" a "$CFTMP" | cf >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 0 ] && [ ! -f "$M/a.marker" ] && [ -f "$M/a.clearedat" ]; } && ok "clears on fresh RESUME" || no "clears on fresh RESUME"

  # post-clear grace: occ < clearedat+step -> allow, no re-arm
  #
  # FIRST LINE ONLY. The grace record carries a SECOND line -- the encoded checkpoint the
  # window was earned against -- and `$(cat)` fed both lines into `$(( ))`, which aborted the whole
  # section with "value too great for base" and took eleven later rows with it (measured: this
  # section fell from 15 rows to 4, at `0 failed`, so the RESULT line still read green).
  CA="$(head -n 1 "$M/a.clearedat")"
  T="$CFTMP/grace.jsonl"; mktrans "$T" $((CA + 10000))
  evc "$T" a "$CFTMP" | cf >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 0 ] && [ ! -f "$M/a.marker" ]; } && ok "post-clear grace allows (<clearedat+step)" || no "post-clear grace allows"

  # past grace: occ >= clearedat+step -> re-arm. REWRITTEN, not merely satisfied.
  # It asserted rc=2 here, i.e. that a re-arm with a checkpoint PRESENT blocks -- which is the
  # defect written down as expected behaviour: the marker is minted in the same pass that then
  # compares against it, so the block could not be pre-empted by any action, however fresh the
  # checkpoint. A checkpoint was written at the "clears on fresh RESUME" row above and is still
  # here, so this row is squarely the once-per-arm-cycle case the contract locks in.
  # What the row actually cares about is that crossing clearedat+step RE-ARMS; the rc=2 was
  # incidental to that. Marker presence is the assertion that carries the intent.
  T="$CFTMP/regrow.jsonl"; mktrans "$T" $((CA + 35000))
  evc "$T" a "$CFTMP" | cf >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 0 ] && [ -f "$M/a.marker" ]; } \
    && ok "re-arms past grace step, and spends the arm cycle's one chance" \
    || no "re-arms past grace step (rc=$RC)"

  # escape hatch: PLC_CONTEXT_FLOOR=0 -> allow even far over floor
  T="$CFTMP/dis.jsonl"; mktrans "$T" 500000
  evc "$T" dis "$CFTMP" | PLC_CONTEXT_FLOOR=0 /bin/bash "$CF_IMPL" >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 0 ] && [ ! -f "$M/dis.marker" ]; } && ok "PLC_CONTEXT_FLOOR=0 disables" || no "PLC_CONTEXT_FLOOR=0 disables"

  # These rows are about FLOOR CONFIGURATION -- is a custom floor honoured, does %-mode compute the
  # right threshold -- and have nothing to do with checkpoints. They ran with cwd=$CFTMP, which by
  # this point holds the RESUME.md written by the "clears on fresh RESUME" row above, so under the one-chance-per-arm-cycle rule
  # each one's first over-floor call spends that session's one chance and returns 0. That is a
  # SHARED-FIXTURE leak, the same family as the two fixtures below that get directories of their own: a row inheriting
  # state from an earlier row's setup and asserting on it by accident. Give them a cwd with no
  # checkpoint and their original rc=2 assertions stand unchanged, meaning exactly what they meant.
  NOCK="$CFTMP/nockpt"; mkdir -p "$NOCK"

  # custom floor 80k -> blocks at 90k
  T="$CFTMP/c.jsonl"; mktrans "$T" 90000
  evc "$T" c "$NOCK" | PLC_CONTEXT_FLOOR=80000 /bin/bash "$CF_IMPL" >/dev/null 2>&1; [ $? -eq 2 ] && ok "custom PLC_CONTEXT_FLOOR honored" || no "custom PLC_CONTEXT_FLOOR honored"

  # window-% mode: 70% of 1M = 700K floor -> 650K allows (under), 720K blocks (over)
  T="$CFTMP/pctlo.jsonl"; mktrans "$T" 650000
  evc "$T" pctlo "$NOCK" | PLC_CONTEXT_FLOOR_PCT=70 PLC_CONTEXT_WINDOW=1000000 /bin/bash "$CF_IMPL" >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 0 ] && [ ! -f "$M/pctlo.marker" ]; } && ok "window-% mode allows under %-floor" || no "window-% mode allows under %-floor"
  T="$CFTMP/pcthi.jsonl"; mktrans "$T" 720000
  evc "$T" pcthi "$NOCK" | PLC_CONTEXT_FLOOR_PCT=70 PLC_CONTEXT_WINDOW=1000000 /bin/bash "$CF_IMPL" >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 2 ] && [ -f "$M/pcthi.marker" ]; } && ok "window-% mode blocks over %-floor" || no "window-% mode blocks over %-floor"

  # window-% overrides absolute: 720K under 70% of 1M allows even though >150K abs default
  T="$CFTMP/pctov.jsonl"; mktrans "$T" 680000
  evc "$T" pctov "$CFTMP" | PLC_CONTEXT_FLOOR_PCT=70 PLC_CONTEXT_WINDOW=1000000 PLC_CONTEXT_FLOOR=150000 /bin/bash "$CF_IMPL" >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 0 ] && [ ! -f "$M/pctov.marker" ]; } && ok "window-% overrides absolute floor" || no "window-% overrides absolute floor"

  # disable: PLC_CONTEXT_FLOOR=0 AND PLC_CONTEXT_FLOOR_PCT=0 -> allow far over
  T="$CFTMP/pctdis.jsonl"; mktrans "$T" 800000
  evc "$T" pctdis "$CFTMP" | PLC_CONTEXT_FLOOR=0 PLC_CONTEXT_FLOOR_PCT=0 /bin/bash "$CF_IMPL" >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 0 ] && [ ! -f "$M/pctdis.marker" ]; } && ok "both-zero disables" || no "both-zero disables"

  # fail-open: malformed transcript -> allow
  echo "{ not json" > "$CFTMP/bad.jsonl"
  evc "$CFTMP/bad.jsonl" badc "$CFTMP" | cf >/dev/null 2>&1; [ $? -eq 0 ] && ok "fail-open on malformed transcript" || no "fail-open on malformed transcript"

  # fail-open: missing usage field -> allow
  python3 -c 'open("'"$CFTMP"'/nousage.jsonl","w").write("{\"type\":\"assistant\",\"message\":{}}\n")'
  evc "$CFTMP/nousage.jsonl" nu "$CFTMP" | cf >/dev/null 2>&1; [ $? -eq 0 ] && ok "fail-open on missing usage" || no "fail-open on missing usage"

  # RESUME exemption: editing the checkpoint file itself is never blocked (no deadlock)
  evf(){ python3 -c 'import json,sys; print(json.dumps({"session_id":sys.argv[2],"transcript_path":sys.argv[1],"cwd":sys.argv[3],"tool_input":{"file_path":sys.argv[4]}}))' "$1" "$2" "$3" "$4"; }
  T="$CFTMP/exempt.jsonl"; mktrans "$T" 300000   # far over floor
  evf "$T" ex "$CFTMP" "$CFTMP/RESUME.md" | cf >/dev/null 2>&1; RC=$?
  { [ "$RC" -eq 0 ] && [ ! -f "$M/ex.marker" ]; } && ok "RESUME.md write exempt from block (no deadlock)" || no "RESUME.md write exempt"

  # ── where a mutant SITS decides which library it loads ──────────────
  # The hook resolves its library relative to its own BASH_SOURCE. So a mutant placed BESIDE the
  # real hook picks up the REAL library, and a mutant placed anywhere else picks up nothing. Both
  # halves are asserted, because only the pair distinguishes "resolution works" from "the mutant
  # happened to sit in the right place".
  #
  # This is a PRECONDITION, not a behaviour: it pins the assumption every future mutation run
  # rests on, so a change that relocates mutants fails HERE and loudly instead of producing a
  # misattributed run somewhere else. The rows below deliberately run with PLC_FLOOR_LIB UNSET --
  # this suite pins it everywhere else, and pinning it here would test the pin, not the fallback.
  # A fixture directory of its own, with NO checkpoint in it. Reusing $CFTMP would inherit the
  # fresh RESUME.md earlier rows wrote, and a fresh checkpoint makes the hook ALLOW -- the row
  # would then read rc=0 as "the library did not load" when it actually means "the checkpoint
  # cleared it". Measured: that is exactly what the first version of this row did.
  #
  # Copied from $CF_IMPL, not from a literal path: under a mutation run the thing that belongs
  # beside the real hook is the MUTANT, and the suite's own self-verification row rejects literal
  # references to the hook outside its selector definition. It caught this one.
  AC5DIR="$CFTMP/ac5"; mkdir -p "$AC5DIR"
  T="$AC5DIR/ac5.jsonl"; mktrans "$T" 160000
  # The mutant HAS to sit in the tracked hook directory -- that is the whole claim being pinned --
  # so the cleanup is a trap in a subshell of its own, not a trailing `rm -f`. A trailing `rm`
  # does not run when the suite is interrupted, and what it leaves behind is a copy of the hook
  # inside the tree the close gate reads. The name is also gitignored, so
  # an interrupt that outruns even the trap cannot turn into a committed file.
  BESIDE="$HERE/context-floor.AC5-mutant.sh"
  (
    trap 'rm -f "$BESIDE"' EXIT INT TERM
    cp "$CF_IMPL" "$BESIDE"
    evc "$T" ac5a "$AC5DIR" | ( unset PLC_FLOOR_LIB; /bin/bash "$BESIDE" ) >/dev/null 2>&1; RC=$?
    [ "$RC" -eq 2 ] \
      && ok "a mutant beside the real hook resolves the REAL library (blocks over floor)" \
      || no "a mutant beside the real hook resolves the REAL library (rc=$RC, expected 2)"
  )

  # The other half: the same copy, one directory away, has no sibling library. It must fail OPEN
  # (rc=0, never a block) AND say so on stderr -- a SILENT rc=0 here is indistinguishable from
  # "under the floor", which is exactly how a relocated hook would disable the floor unnoticed.
  ELSEWHERE="$CFTMP/context-floor.AC5-elsewhere.sh"
  cp "$CF_IMPL" "$ELSEWHERE"
  AC5ERR="$CFTMP/ac5.err"
  evc "$T" ac5b "$AC5DIR" | ( unset PLC_FLOOR_LIB; /bin/bash "$ELSEWHERE" ) >/dev/null 2>"$AC5ERR"; RC=$?
  { [ "$RC" -eq 0 ] && grep -q "context floor OFF" "$AC5ERR"; } \
    && ok "the same copy one directory away finds no library, fails OPEN, and says so" \
    || no "relocated copy (rc=$RC, stderr=[$(tr -d '\n' < "$AC5ERR")])"

  # ── a stale-but-existing PLC_FLOOR_LIB must not reach a run ────────
  # `impl_path`'s FATAL guard proves a path RESOLVES; it cannot prove the path is the library this
  # run intends. A stale export left in a shell or CI environment passes that guard and turns a
  # later mutation run into a HYBRID -- mutated hook, wrong library -- reported confidently. The
  # defence is the PIN, not the guard: every hook call in this file writes PLC_FLOOR_LIB, so an
  # ambient value is overwritten rather than detected.
  #
  # The FIRST version of this row compared two shell variables set by `env`. It invoked no hook,
  # touched no pin, and it passed against two empty temp files -- a tautology
  # about POSIX `env` closing an AC. It is now a real run through the hook, with a stale library
  # chosen to be BEHAVIOURALLY distinguishable: its `intenv` returns a floor far above the
  # fixture's occupancy, so the stale library ALLOWS where the real one BLOCKS. Anything less than
  # a behavioural difference cannot tell a hybrid run from a clean one, which is the whole reason
  # a hybrid is invisible.
  STALE="$CFTMP/stale-but-existing-floor-env.sh"
  printf 'PLC_FLOOR_JQ_DEFS="%s"\n' \
    'def trim: sub("^\\\\s+"; "") | sub("\\\\s+$"; ""); def intenv($n; $unset; $empty): 10000000; def floatenv($n; $unset; $empty): 0;' \
    > "$STALE"
  # Its own fixture directory, with NO checkpoint in it. Reusing $CFTMP inherits the fresh
  # RESUME.md earlier rows wrote, which CLEARS the block -- both halves then return 0 for a reason
  # that has nothing to do with the library, and the row silently loses its power to distinguish.
  # Measured: that is exactly what the first version of this row did.
  AC3BDIR="$CFTMP/ac3b"; mkdir -p "$AC3BDIR"
  T="$AC3BDIR/ac3b.jsonl"; mktrans "$T" 500000
  # (a) the stale library really is distinguishable: with NO pin it wins, and the hook ALLOWS.
  evc "$T" ac3bstale "$AC3BDIR" | ( export PLC_FLOOR_LIB="$STALE"; /bin/bash "$CF_IMPL" ) >/dev/null 2>&1; STALERC=$?
  # (b) the same ambient export, plus this suite's pin: the REAL library must win and BLOCK.
  evc "$T" ac3bpin "$AC3BDIR" \
    | ( export PLC_FLOOR_LIB="$STALE"; env PLC_FLOOR_LIB="$FLOOR_LIB_IMPL" /bin/bash "$CF_IMPL" ) >/dev/null 2>&1; PINRC=$?
  { [ "$STALERC" -eq 0 ] && [ "$PINRC" -eq 2 ]; } \
    && ok "an ambient stale PLC_FLOOR_LIB changes the hook's answer, and the pin overrides it" \
    || no "pin/stale (stale-alone rc=$STALERC expected 0; pinned rc=$PINRC expected 2 -- equal values mean the row cannot tell them apart)"

  # ── library failure shapes (floor side): absent / broken / exiting library all degrade the same ────────────
  # `[ -r ]` separates none of these three, and a partial plugin update produces the broken shapes
  # more often than a clean removal. The "exiting" case is why the hook sources in a SUBSHELL: a
  # sourced `exit` exits the SOURCING shell, so a broken library could otherwise terminate the
  # hook mid-event -- which on a PreToolUse hook is a failure mode with no message at all.
  LIBFX="$CFTMP/libfx"; mkdir -p "$LIBFX"
  printf 'PLC_FLOOR_JQ_DEFS="$(cat <<EOF\nunterminated\n' > "$LIBFX/syntaxerr.sh"
  printf '#!/usr/bin/env bash\nexit 1\n' > "$LIBFX/exits.sh"
  printf 'PLC_FLOOR_JQ_DEFS="this is not jq at all ((("\n' > "$LIBFX/garbage.sh"
  printf 'PLC_FLOOR_JQ_DEFS="def unrelated: 1;"\n' > "$LIBFX/nothing.sh"
  # The two shapes an absent-only probe is blind to. Both source cleanly, define all
  # three names, and answer an ABSENT variable correctly -- which was the only input the first
  # probe ever asked about. `envblind` ignores the environment entirely (measured: it made the
  # hook block at the default floor while the caller had set PLC_CONTEXT_FLOOR=0); `without-times-one` is
  # the subnormal-floor shape, the real definitions with the load-bearing `* 1` stripped off floatenv.
cat > "$LIBFX/envblind.sh" <<'FXEOF'
PLC_FLOOR_JQ_DEFS='
  def trim: sub("^\\s+"; "") | sub("\\s+$"; "");
  def intenv($n; $unset; $empty): $unset;
  def floatenv($n; $unset; $empty): $unset;
'
FXEOF
cat > "$LIBFX/without-times-one.sh" <<'FXEOF'
PLC_FLOOR_JQ_DEFS='
  def trim: sub("^\\s+"; "") | sub("\\s+$"; "");
  def intenv($n; $unset; $empty):
    env[$n] as $v
    | if   $v == null then $unset
      elif $v == ""   then $empty
      elif ($v | test("^\\s*[+-]?[0-9]+\\s*$")) then ($v | trim | tonumber)
      else $unset end;
  def floatenv($n; $unset; $empty):
    env[$n] as $v
    | if   $v == null then $unset
      elif $v == ""   then $empty
      else (($v | trim | tonumber?) // $unset) end;
'
FXEOF
  T="$CFTMP/lib.jsonl"; mktrans "$T" 500000     # far over the floor: a working hook would BLOCK
  for LIBCASE in absent:"$LIBFX/nope.sh" broken:"$LIBFX/syntaxerr.sh" exiting:"$LIBFX/exits.sh" garbage:"$LIBFX/garbage.sh" defining-nothing:"$LIBFX/nothing.sh" env-blind:"$LIBFX/envblind.sh" without-times-one:"$LIBFX/without-times-one.sh"; do
    LIBNAME="${LIBCASE%%:*}"; LIBPATH="${LIBCASE#*:}"
    evc "$T" "lib$LIBNAME" "$CFTMP" \
      | ( export PLC_FLOOR_LIB="$LIBPATH"; /bin/bash "$CF_IMPL" ) >"$LIBFX/$LIBNAME.out" 2>"$LIBFX/$LIBNAME.err"; RC=$?
    # "exactly one line, and nothing on stdout" was CLAIMED in prose
    # while the row only `grep -q`'d for a substring and discarded stdout -- so two lines, or a
    # line plus stray stdout, both read as a pass. Counted and asserted now.
    ERRN="$(grep -c 'context floor OFF' "$LIBFX/$LIBNAME.err" 2>/dev/null || true)"
    ERRTOT="$(wc -l < "$LIBFX/$LIBNAME.err" | tr -d ' ')"
    { [ "$RC" -eq 0 ] && [ "${ERRN:-0}" -eq 1 ] && [ "${ERRTOT:-0}" -eq 1 ] && [ ! -s "$LIBFX/$LIBNAME.out" ]; } \
      && ok "floor degrades identically on a $LIBNAME library (fail open + exactly one line, empty stdout)" \
      || no "floor on a $LIBNAME library (rc=$RC matching-lines=$ERRN total-stderr-lines=$ERRTOT stdout=[$(tr -d '\n' < "$LIBFX/$LIBNAME.out")] err=[$(tr -d '\n' < "$LIBFX/$LIBNAME.err")])"
  done

  # ── throttle (floor side): at most ONE line per session ───────────────────────────────────
  # A PreToolUse hook fires on every Edit/Write, so an unthrottled line would repeat per keystroke
  # -- per-keystroke stderr noise, arriving through a different door.
  # Keyed by session and NOT globally: a second session must still be told once.
  THRDIR="$CFTMP/thr"; mkdir -p "$THRDIR"
  thrun(){ evc "$T" "$1" "$CFTMP" \
    | ( export TMPDIR="$THRDIR" PLC_FLOOR_LIB="$LIBFX/nope.sh"; /bin/bash "$CF_IMPL" ) >/dev/null 2>>"$THRDIR/$1.err"; }
  thrun thrA; thrun thrA; thrun thrA
  thrun thrB
  A="$(grep -c 'context floor OFF' "$THRDIR/thrA.err" 2>/dev/null || true)"
  B="$(grep -c 'context floor OFF' "$THRDIR/thrB.err" 2>/dev/null || true)"
  { [ "$A" -eq 1 ] && [ "$B" -eq 1 ]; } \
    && ok "the missing-library line is emitted once per SESSION, not once per event" \
    || no "throttle (3 calls in session A emitted $A lines, expected 1; session B emitted $B, expected 1)"

  # ── the throttle must not be reachable through a node this hook did not write ──────────
  #
  # WHY THESE ROWS EXIST. The once-per-session row above pre-squats NOTHING: it lets the hook create its own
  # marker and counts lines. Measured, that is not enough -- reverting the guard to a bare
  # `[ -e ]`, the exact regression the guard was written to prevent, left the
  # whole suite green. A row that never plants the hostile shape cannot see it.
  # Each shape below is planted BEFORE the first call, and each is a real defect that shipped:
  # a directory, a chmod-000 file and a FIFO.
  #
  # The FIFO row is run in the BACKGROUND with a bounded wait rather than under `timeout`, which
  # is not a dependency this suite has. A regressed hook blocks forever in `: > "$marker"`, so a
  # foreground row would hang the suite instead of failing it -- a red that never arrives.
  SQDIR="$CFTMP/squat"; mkdir -p "$SQDIR"
  # $1 = shape label, $2 = expected line count. Returns the observed count, or `HUNG`.
  squat_run(){
    local shape="$1" d="$SQDIR/$1" m out n i p
    mkdir -p "$d/plc-context-floor"
    m="$d/plc-context-floor/sq.libwarn"
    case "$shape" in
      dir)      mkdir "$m" ;;
      fifo)     mkfifo "$m" ;;
      unwrit)   : > "$m"; chmod 000 "$m" ;;
      symlink)  ln -s "$d/elsewhere" "$m"; : > "$d/elsewhere" ;;
    esac
    out="$d/err"
    ( evc "$T" sq "$CFTMP" \
      | ( export TMPDIR="$d" PLC_FLOOR_LIB="$LIBFX/nope.sh"; /bin/bash "$CF_IMPL" ) >/dev/null 2>"$out" ) &
    p=$!
    i=0
    while kill -0 "$p" 2>/dev/null && [ "$i" -lt 100 ]; do sleep 0.1; i=$((i + 1)); done
    if kill -0 "$p" 2>/dev/null; then kill -9 "$p" 2>/dev/null || true; printf 'HUNG'; return 0; fi
    n="$(grep -c 'context floor OFF' "$out" 2>/dev/null || true)"
    printf '%s' "${n:-0}"
  }
  for SHAPE in dir fifo unwrit symlink; do
    N="$(squat_run "$SHAPE")"
    [ "$N" = "1" ] \
      && ok "a $SHAPE squatting the throttle marker leaves the hook NOISY" \
      || no "a $SHAPE squatting the throttle marker (got [$N] lines, expected 1 -- HUNG means the write blocked)"
  done
)
rm -rf "$CFTMP"

echo
SECTION="self-verification"
echo "=== self-verification: the verdict is real ==="
# The suite guards every hook in this plugin, so its own exit code has to mean something.
# Re-invoke this script in each self-test mode and assert on the CODE, not on the output.
SELF="${BASH_SOURCE[0]}"
/bin/bash "$SELF" --selftest-fail >/dev/null 2>&1 \
  && no "a failed assertion inside a subshell must make the suite exit non-zero" \
  || ok "a failed assertion inside a subshell makes the suite exit non-zero"
/bin/bash "$SELF" --selftest-clean >/dev/null 2>&1 \
  && ok "a passed assertion inside a subshell exits zero (the failing case is not just always-red)" \
  || no "a passed assertion inside a subshell must exit zero"

# Nothing above would notice a NEW call site that hardcodes the hook path again. The
# mutation runs measure the sites that exist; a site added tomorrow is simply absent from
# them and the suite stays green — the same "the row exists, is named, and is green" blind
# spot. This is the cheap static half: no call site may bypass its selector.
# It is a source-text check, so it costs nothing and fails the moment the bypass is written.
#
# Deliberately NOT matched: the frontmatter block near the top asserts that SKILL.md wires
# the real hook paths (`root+"guard.sh"`). Those are manifest assertions, not invocations —
# routing them through a selector would make the suite stop checking what it ships.
# The pattern matches `$HERE/x.sh`, `${HERE}/x.sh`, quoted or bare, with or without a leading
# `bash `. Matching only the one spelling that happened to exist would have made this guard's
# claim ("no call site bypasses the selector") wider than its mechanism ("no call site uses the
# exact idiom I already removed") — exactly the gap this check is meant to close, reproduced
# inside its own fix. No row below plants each spelling; the pattern is what covers them.
#
# STILL NOT CAUGHT, stated rather than implied: an invocation that reaches the hook through
# another variable (`P=$HERE/guard.sh; bash "$P"`) or through `source`. That needs parsing, not
# grep. The guard's claim is scoped to a literal `HERE`-rooted path, which is what every call
# site in this file has ever used.
# The rule enforced is: a literal `HERE`-rooted path to one of these hooks may appear ONLY on
# the line that defines that hook's selector (`*_IMPL=`), which is the one place it must appear.
# Comments are excluded so prose can name a path without tripping the guard — including the
# paragraph directly above.
#
# Widening the pattern beyond the single spelling that happened to exist is not cosmetic: the
# first version matched only `bash "$HERE/x.sh"`, so its claim ("no call site bypasses the
# selector") was wider than its mechanism ("no call site uses the exact idiom I already
# removed"), which is exactly the gap this check is meant to close, reproduced inside its own
# fix. Widening it then false-positived on the selector definitions themselves — 4 rows red on
# a clean tree — which is why the exclusions below are derived from a listing of the actual
# matches rather than guessed.
for _h in guard close-gate-nudge tasklist-first context-floor; do
  _n="$(grep -E "[\"']?\\\$\{?HERE\}?/$_h\.sh" "$SELF" 2>/dev/null \
        | grep -vE '^[[:space:]]*#' \
        | grep -vE '_IMPL=' \
        | grep -c . )"
  case "$_n" in ''|*[!0-9]*) _n=0 ;; esac
  [ "$_n" -eq 0 ] \
    && ok "no call site bypasses the selector for $_h.sh" \
    || no "$_n call site(s) reference $_h.sh by literal path outside its selector definition"
done

verdict
