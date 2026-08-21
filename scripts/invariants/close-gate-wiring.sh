#!/usr/bin/env bash
# Invariant: the close gate is actually wired into the pre-push hook git will run.
#
# The installer runs ONCE PER CLONE, but reachability is a property of a file it does not own and
# cannot hold still. A later reinstall of the local hook, an added `exec` shim, or a `core.hooksPath`
# setting un-wires the chain — and the symptom of every one of those is identical and invisible:
# PUSHES KEEP SUCCEEDING. A once-per-clone action cannot guarantee a standing property, so the
# property gets its own standing assertion.
#
# WHAT IT DOES NOT DO, stated here rather than discovered later: it cannot run when the wiring is
# broken in the one way that matters most to it — if the hook does not fire, this check does not run
# from the hook either. It is the PAIR to the installer's insertion order, not a replacement
# for it: check 8 also reaches it on a `close-gate.sh task|phase|diff` a human types, and that is the
# path on which it earns its keep.
#
# Reach, stated accurately: not "every push". It runs where check 8 runs — every `feat/phase-*` push,
# every non-phase push (the `diff` mode runs tree-level invariants too), and any hand-typed
# `close-gate.sh`.
#
# jq-only envelope: bash + git only. No jq is needed here and no python3 appears anywhere in it.

set -uo pipefail

NAME="close-gate-wiring"

pass() { printf 'PASS %s: %s\n' "$NAME" "$1"; exit 0; }
fail() { printf 'FAIL %s: %s\n' "$NAME" "$1"; exit 1; }

# The repo root is an OPTIONAL EXPLICIT ARGUMENT, never an environment variable, and never derived
# from BASH_SOURCE. Deriving it from the script's own location would make the `core.hooksPath`
# questions below read THIS repository's configuration no matter which tree was handed to the
# check — the same trap `gate-jq-only-envelope.sh` documents for its own root.
ROOT="${1:-.}"
cd "$ROOT" 2>/dev/null || fail "cannot enter '$ROOT'"

git rev-parse --git-dir >/dev/null 2>&1 || fail "not a git repository (from '$ROOT')"

# The sentinel the chain-shaped install writes. Pinned as a literal here and asserted equal to
# `install-close-gate-hook.sh`'s copy by a test — two files, one string, checked rather than hoped.
MARK="# >>> close-gate wrap-up chain (scripts/install-close-gate-hook.sh) >>>"

# Resolve, never string-compare. `--git-path hooks` may answer absolute where `--git-common-dir`
# answers relative, and comparing those as text calls one directory two names.
abspath() { ( cd "$(dirname "$1")" 2>/dev/null && printf '%s/%s\n' "$(pwd -P)" "$(basename "$1")" ) || printf '%s\n' "$1"; }

# --- clause 1: an ORPHANED hook, evaluated BEFORE the hook is located ---------------
#
# The order is load-bearing. `git rev-parse --git-path hooks/pre-push` HONOURS core.hooksPath by
# itself, so clause 3 asks a question whose answer this clause changes; locating first means
# inspecting a different file than the one being reported on, and any red is unattributable.
#
# The danger is never the config key — it is a hook git has stopped running while everyone still
# believes it runs. Setting core.hooksPath is not a failure. An adopter who followed /init-harness
# has no hook at the default path, so nothing is orphaned and this passes.
RESOLVED_DIR="$(abspath "$(git rev-parse --git-path hooks)")"
DEFAULT_DIR="$(abspath "$(git rev-parse --git-common-dir)")/hooks"
if [ "$RESOLVED_DIR" != "$DEFAULT_DIR" ] && [ -e "$DEFAULT_DIR/pre-push" ]; then
  fail "an existing pre-push hook at '$DEFAULT_DIR/pre-push' has been ORPHANED — git now reads hooks from '$RESOLVED_DIR', so that file no longer runs on any push. Either clear core.hooksPath, or move its contents into '$RESOLVED_DIR/pre-push'."
fi

# --- clause 3 (applied here): locate the hook, unqualified -------------------------
#
# `--git-path hooks/pre-push` and nothing else. Its output is cwd-relative, which is exactly what
# makes it correct from a subdirectory, and in a linked worktree it resolves into the shared git dir
# where the hooks actually live. `--absolute-git-dir` is the trap: in a worktree it returns the
# per-worktree directory, under which `hooks/pre-push` does not exist, so an invariant built on it is
# permanently red there — reintroducing the very defect this clause exists to close.
HOOK="$(git rev-parse --git-path hooks/pre-push)"

# --- clause 4: a clone with no hook fails, and the failure names the cure -----------
#
# Not a false red: that clone genuinely is not wired, and the pre-merge gate is exactly where that
# should surface. The cure is spelled `/bin/bash …` and never `run: bash …` — `named-interpreter.sh`
# reds any non-comment line matching `bash` preceded by a non-word character, so the obvious spelling
# would make a DIFFERENT invariant fail on every check-8 run, with the red attributed to that one.
if [ ! -e "$HOOK" ]; then
  fail "no pre-push hook at '$HOOK' — this clone is not wired. From the repository root, run: /bin/bash scripts/install-close-gate-hook.sh"
fi
[ -x "$HOOK" ] || fail "'$HOOK' exists but is not executable — git will not run it. chmod +x it, or re-run the installer from the repository root."

# --- clause 2: the gate is REACHABLE in it — a claim about POSITION ----------------
#
# Presence alone is fail-open, and measurably so: a hook with `exec /usr/bin/true "$@"` on line 2 and
# the full sentinel-bracketed chain below it does not run the chain, and a presence-only check
# passes. Two shapes are accepted, because there are two legitimate wirings:
#
#   chain shape        — the sentinel is the FIRST NON-BLANK LINE AFTER THE SHEBANG, which is what
#                        the installer produces by construction, so it is free for every future
#                        install.
#   /init-harness shape — the hook IS the gate rather than a chain spliced into a foreign hook, so
#                        nothing foreign precedes it and position is not the question. It qualifies
#                        by invoking close-gate.sh or close-gate-prepush.sh anywhere in its body.
#                        Without this shape the clause would be UNSATISFIABLE for the wiring this
#                        skill's own /init-harness mandates: the sentinel exists in exactly one file
#                        in the whole product, and the shipped .githooks/pre-push carries none.
FIRST_BODY_LINE="$(sed -n '2,$p' "$HOOK" | sed -n '/[^[:space:]]/{p;q;}')"

if [ "$FIRST_BODY_LINE" = "$MARK" ]; then
  pass "chain shape: the close-gate sentinel is the first line after the shebang in '$HOOK'"
fi

# ORDER IS LOAD-BEARING, and getting it wrong here re-opened the exact hole this clause
# closes. A sentinel that is PRESENT but MISPLACED must fail right here; it must not fall
# through to the second shape below. Measured while writing this: with the second shape
# checked first, the `exec`-shim fixture PASSED — the chain sitting dead below the `exec`
# still contains a call to the gate, so a name search finds it and reports success. The
# repair for one accepted shape had swallowed the other clause whole.
if grep -qF "$MARK" "$HOOK"; then
  fail "'$HOOK' contains the close-gate chain, but NOT as the first line after the shebang — the first body line is: ${FIRST_BODY_LINE:-<empty>}. Anything above it (an \`exec\` line in particular) can stop the chain from ever running while pushes keep succeeding. Re-run the installer from the repository root: /bin/bash scripts/install-close-gate-hook.sh"
fi

# Only a hook with NO sentinel is eligible for the second shape — the /init-harness wiring,
# where the hook IS the gate and nothing foreign precedes it.
#
# Comments are stripped BEFORE looking, so a hook that merely mentions the gate in prose does
# not qualify — use, not mention.
# The name is matched without a preceding-character class: a path-qualified call
# (`scripts/close-gate-prepush.sh`, which is how every real hook writes it) is the normal
# case, and a class excluding `/` rejected exactly that. Measured — it reddened every
# /init-harness-shaped fixture, i.e. the wiring this clause exists to accept.
if sed 's/[[:space:]]*#.*$//' "$HOOK" | grep -qE 'close-gate(-prepush)?\.sh'; then
  pass "gate shape: '$HOOK' invokes the close gate directly (the /init-harness wiring)"
fi

fail "'$HOOK' does not reach the close gate: no chain sentinel and no direct call to close-gate.sh or close-gate-prepush.sh. From the repository root, run: /bin/bash scripts/install-close-gate-hook.sh"
