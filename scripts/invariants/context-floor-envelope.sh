#!/usr/bin/env bash
# Invariant: the context hooks stay inside the hook dependency envelope, and every git
# invocation in them is stderr-guarded.
#
# Two separate failures over a DECLARED SET of files, because they share a cause: target-based checkpoint resolution brought
# `git` into these hooks, and `git` is chatty. python3 is banned
# from the gate's envelope; `scripts/close-gate.sh` spells the envelope out as "bash + git +
# jq + coreutils only". So git is allowed -- but these are hooks whose stderr reaches the user,
# and `git rev-parse` prints `fatal: not a git repository` on every miss, which is the COMMON
# case for anything edited outside a repo. An unguarded call turns a silent fallback into
# per-keystroke noise, and the redirection-order lesson (`: > f 2>/dev/null` leaks,
# because redirections apply left to right) says the guard has to be on the command itself.
#
# WHY A DECLARED LIST AND NOT A DERIVED ONE. The set is written out by hand, one entry per
# file, rather than derived by following `source` lines. The derived side has filed, real
# failures -- Ruff #10147 (inconsistent glob dialects) and semgrep #11144 (include can only
# narrow) -- and CMake's own documentation argues against globbing source lists for exactly the
# silent-under-coverage reason. The cost is real and is named here rather than hidden: a file
# added to the hook tree and NOT added to this list is scanned by nothing, silently. The
# mitigation is the self-coverage assertion below plus the rule that a file enters this
# list in the SAME change that creates it.
#
# THE SELF-COVERAGE ASSERTION IS LOCAL INVENTION. Research across ESLint, ast-grep, semgrep, Go
# `analysistest`, Rust tidy, ShellCheck and golangci-lint found every one of them proving "this
# rule fires on this content" (framework-mandated known-bad fixtures) and NONE proving "this
# checker opened every file it claims to cover". Do not describe the assertion below as an
# industry practice; it was designed here because the stale-list risk above needed an answer.
#
# WHAT THIS IS NOT. Both checks are LEXICAL greps, and a review demonstrated real bypasses:
# `PY="py"thon"3"` never puts the token in the source bytes contiguously, and `GITBIN=git`
# followed by `"$GITBIN" -C ...` contains no literal `git ` on the invoking line. Those bypasses
# are all DELIBERATE obfuscation, and that is not the threat here -- the threat is a future edit
# reaching for an interpreter or forgetting a redirect, which is drift, and drift is exactly what
# a grep catches.
#
# REMAINING BLIND SPOTS, stated rather than implied:
#   - The stale-list risk above. The self-coverage assertion proves every DECLARED file is read;
#     nothing here can prove the declaration is complete.
#   - INV-2 has NO self-coverage equivalent. The assertion plants a python invocation, so it
#     exercises INV-1 only. An INV-2 that silently stopped reading a file would still pass.
#   - INV-3's count is per LINE, not per occurrence: `grep -cE '^[[:space:]]*def x'` counts each
#     matching line once and is anchored at line start, so three definitions re-pasted onto ONE
#     line read as one hit and every row stays green (measured, with a positive control). A second
#     copy therefore hides by being written on the same line as the first. Occurrence-counting is
#     the fix and is deliberately NOT applied here: `grep -o` over multi-line jq text changes what
#     "a definition" means for the whole check, which is a bigger change than this check makes.
#
# THERE IS NO ENVIRONMENT OVERRIDE. An earlier version let
# `PLC_CFE_ROOT` relocate the scanned set, with a header claiming the override "announces itself
# on stdout, and the close gate's output is where that shows up" -- measured false, because
# `close-gate.sh` runs invariants with `>/dev/null 2>&1`. A later version gated the relocation behind
# an internal token, and that was measured false too: the token was the plain environment
# variable `PLC_CFE_SELFTEST=1`, spelled in this file's own source, so any caller or ambient CI
# environment supplying both variables relocated the set, skipped the self-coverage assertion, and
# exited 0 -- the same silent off-switch, one layer down. An environment variable is not a
# capability. The self-coverage assertion now calls `scan_set` IN-PROCESS with the fixture root as
# an argument, so there is no second invocation to authenticate and nothing to forge.
#
# The SEMANTIC proof already exists and lives elsewhere, which is why this file is not trying to
# be it: `hooks/test-context-floor-contract.sh` §"dependency envelope" RUNS the hook on a PATH
# where python3 is provably unreachable and asserts it still blocks, ordered so that a hook which
# had silently become fail-open cannot pass by "still behaving". Read this file as a fast
# drift-catcher wired into every close, and that suite as the thing that actually proves the
# envelope is closed.
set -euo pipefail

# --- the declared set. Repo-root-relative, matching how the single-file predecessor spelled its
# `HOOK` variable. INV-1 covers every file here; INV-2 covers the subset below it.
INV1_FILES="
skills/project-lifecycle/hooks/context-floor.sh
skills/project-lifecycle/hooks/close-gate-nudge.sh
skills/project-lifecycle/hooks/lib/floor-env.sh
"

# INV-2 is deliberately NARROWER than INV-1, and the exclusion is an argument, not an oversight:
# a file with zero git calls passes INV-2 vacuously, and a vacuous pass is indistinguishable from
# a check that never ran. Both files below invoke git for real -- `context-floor.sh` via its
# repo-root resolution, `close-gate-nudge.sh` in several places -- so INV-2 over them is a
# real, currently-passing check.
INV2_FILES="
skills/project-lifecycle/hooks/context-floor.sh
skills/project-lifecycle/hooks/close-gate-nudge.sh
"

# The declared set must be NON-EMPTY. A check whose file list is empty passes every loop below
# vacuously and prints nothing but the self-coverage lines -- which is indistinguishable from a
# clean repository, and is what an editing accident on the two strings above produces. Asserted
# rather than left to the accidental protection of INV-3 and the control fixture.
for _set in INV1_FILES INV2_FILES; do
  eval "_val=\${$_set}"
  case "$_val" in
    *[![:space:]]*) : ;;
    *) echo "FAIL context-floor-envelope: the declared set $_set is empty; every check below would"
       echo "     pass vacuously. Refusing to run."
       exit 1 ;;
  esac
done

rc=0

# --- INV-1: no python interpreter, including absolute paths. Comment lines are excluded: these
# files discuss the python implementation they replaced at length, and that prose is the record
# of why the port exists.
#
# Captured into a variable rather than tested with `grep -q` inside the pipeline. Under
# `set -o pipefail` a `-q` tail exits as soon as it matches, which can SIGPIPE the upstream greps
# and hand the pipeline a non-zero status even though the match SUCCEEDED -- so the `if` reads a
# real violation as "clean". This form has no `-q` and cannot reach it.
inv1_hits() {
  grep -nE '(^|[^#[:alnum:]_])(python3?|/usr/(local/)?bin/python3?)' "$1" \
    | grep -vE ':[[:space:]]*#' \
    | grep -vE '#.*python' \
    || true
}

# --- INV-2: every executable `git` call carries a stderr guard. Comment lines are skipped so the
# prose explaining the rule does not trip the rule.
inv2_hits() {
  grep -nE '(^|[^#[:alnum:]_])git ' "$1" \
    | grep -vE '^[0-9]+:[[:space:]]*#' \
    | grep -vE '2>[[:space:]]*/dev/null' \
    || true
}

# --- the declared set must be internally consistent: INV-2 is a SUBSET of INV-1, so a file can
# never be git-checked while escaping the python ban.
for f in $INV2_FILES; do
  case " $(echo $INV1_FILES) " in
    *" $f "*) : ;;
    *) echo "FAIL context-floor-envelope: $f is in the INV-2 set but not the INV-1 set"; rc=1 ;;
  esac
done

# --- scan_set <root>: run INV-1, INV-2 and INV-3 over the declared set rooted at <root>.
#
# A FUNCTION, not a re-invocation of this script. The self-coverage assertion below needs to run
# the same scan over a fixture tree, and an earlier version did that by re-`exec`ing this file with the
# root in an environment variable -- which is what created a relocation switch that an ambient
# environment could flip (see the header). With the root as an argument there is no second
# process, no environment channel, and nothing for a caller to set.
#
# Emits its own ok/FAIL lines and returns 1 if anything failed. It does NOT touch the outer `rc`:
# the self-coverage runs depend on distinguishing THEIR result from the real scan's.
scan_set() {
  local root="$1" f path hits n total srodef srrc=0
  for f in $INV1_FILES; do
    path="$root/$f"
  if [ ! -r "$path" ]; then
    echo "FAIL context-floor-envelope: $f missing or unreadable under $root"
    srrc=1
    continue
  fi
  hits="$(inv1_hits "$path")"
    if [ -n "$hits" ]; then
      echo "FAIL context-floor-envelope INV-1: a python interpreter is invoked in $f"
      printf '%s\n' "$hits"
      srrc=1
    else
      echo "ok context-floor-envelope INV-1: no python interpreter invoked in $f"
    fi
  done

  for f in $INV2_FILES; do
    path="$root/$f"
    [ -r "$path" ] || continue   # already reported by the INV-1 loop
    hits="$(inv2_hits "$path")"
    if [ -n "$hits" ]; then
      echo "FAIL context-floor-envelope INV-2: a git invocation is not stderr-guarded in $f"
      printf '%s\n' "$hits"
      srrc=1
    else
      echo "ok context-floor-envelope INV-2: every git invocation is stderr-guarded in $f"
    fi
  done

  # --- INV-3: each shared definition exists EXACTLY ONCE across the declared set.
  #
  # This is the invariant the extraction is FOR. Sharing a definition does not stop a future edit
  # from pasting a private copy back into a hook -- that is precisely how the two copies came to
  # exist, and the drift then silenced a hook. A GLOBAL count is the only shape that catches it:
  # a per-file check cannot tell "the one true definition" from "a second copy", because both are
  # one occurrence in their own file.
  #
  # Counted over the declared set, so a copy pasted into a file NOT on the list is invisible here.
  # That is the same stale-list blind spot named at the top, and the same mitigation applies.
  # The per-LINE counting blind spot is named in the header, with the reason it is not fixed here.
  for srodef in trim intenv floatenv; do
    total=0
    for f in $INV1_FILES; do
      path="$root/$f"
      [ -r "$path" ] || continue
      n="$(grep -cE "^[[:space:]]*def $srodef:?[[:space:]]*\(?" "$path" || true)"
      total=$((total + n))
    done
    if [ "$total" -eq 1 ]; then
      echo "ok context-floor-envelope INV-3: 'def $srodef' is defined exactly once across the declared set"
    else
      echo "FAIL context-floor-envelope INV-3: 'def $srodef' is defined $total times across the declared set (expected exactly 1)"
      srrc=1
    fi
  done

  return "$srrc"
}

scan_set "." || rc=1

# --- self-coverage assertion. Proves this script actually OPENED each declared file,
# rather than proving only that its greps work on whatever it happened to read.
#
# Shape: per-file planted violation. For each declared file, build a fixture tree holding clean
# copies of the WHOLE declared set, plant a python invocation in exactly ONE of them, point the
# scan at that tree, and require red. Copying the whole set is what makes the red ATTRIBUTABLE:
# planting into one file while the others resolved to the real ones would let an unrelated real
# defect produce the same red. The all-clean CONTROL run below is the other half of that -- if
# the control is already red, every planted red proves nothing.
#
# Rejected alternative: a declared-count assertion (print and count the set scanned). Cheap, but
# it proves the checker's claim about itself using the checker's own bookkeeping -- the
# self-certification shape the close gate exists to reject.
mk_fixture() {
  # $1 = fixture root, $2 = repo-relative file to plant into ("" for the clean control)
  local dir="$1" plant="${2:-}" f
  for f in $INV1_FILES; do
    mkdir -p "$dir/$(dirname "$f")"
    cp "$f" "$dir/$f"
    if [ -n "$plant" ] && [ "$f" = "$plant" ]; then
      printf 'python3 -c "pass"\n' >> "$dir/$f"
    fi
  done
}

# In-process, in a SUBSHELL. The subshell is what keeps `scan_set`'s loop variables and any
# `set -e` behaviour from leaking into the real scan's state; the discarded output is what keeps
# the fixture runs from being mistaken for findings about the repository.
run_scan() {
  ( scan_set "$1" ) >/dev/null 2>&1
}

TMPROOT="$(mktemp -d)"
trap 'rm -rf "$TMPROOT"' EXIT

mk_fixture "$TMPROOT/control" ""
if run_scan "$TMPROOT/control"; then
  for f in $INV1_FILES; do
    slug="$(printf '%s' "$f" | tr '/.' '__')"
    mk_fixture "$TMPROOT/$slug" "$f"
    if run_scan "$TMPROOT/$slug"; then
      echo "FAIL context-floor-envelope SELF-COVERAGE: a python invocation planted in $f did"
      echo "     not redden the check, so this script never read that file"
      rc=1
    else
      echo "ok context-floor-envelope SELF-COVERAGE: $f is really scanned"
    fi
  done
else
  echo "FAIL context-floor-envelope SELF-COVERAGE: the all-clean control fixture is already"
  echo "     RED, so no planted red below would be attributable to the plant"
  rc=1
fi

exit "$rc"
