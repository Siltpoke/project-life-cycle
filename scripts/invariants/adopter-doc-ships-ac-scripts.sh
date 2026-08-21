#!/usr/bin/env bash
# Invariant: the copies of ac-evidence.sh and ac-baseline.sh embedded in the adopter contract are
# BYTE-IDENTICAL to the scripts this repo actually runs.
#
# Why a copy exists at all: an adopter materializing their gate from
# `references/close-gate.md` gets the check -- not a checklist row promising one. Every other row in
# that document has its implementation in the document; these two would have been the only prose-only
# rows -- a declaration wider than its mechanism.
#
# Why byte-equality is possible HERE and not for the gate itself: the document's embedded
# `close-gate.sh` is deliberately a DIFFERENT implementation from this repo's (this repo runs the
# gitignored-docs variant; the document ships the canonical git-range one), so no equality can hold
# between them. `ac-evidence.sh` and `ac-baseline.sh` take no gate dialect -- they are standalone and
# identical on both sides, so the copy can be held exactly rather than by discipline.
#
# The comparison is over BYTES, not a summary: a digest of a digest tells a reader nothing about
# WHERE it diverged, and this check has to be actionable at 3am. It prints the first differing line.
#
# Fences are FOUR backticks. `ac-evidence.sh` contains a line matching /^```/ (an awk pattern for
# markdown fences), which would close a three-backtick block early and silently truncate the copy --
# measured while writing this, not reasoned about.
#
# jq-only envelope: no python3 here or in anything it calls.

set -uo pipefail

NAME="adopter-doc-ships-ac-scripts"

# Subject is an ARGUMENT, never fd 0 (git feeds the pre-push hook ref lines on stdin).
ROOT="${1:-.}"
DOC="$ROOT/skills/project-lifecycle/references/close-gate.md"

pass() { printf 'PASS %s: %s\n' "$NAME" "$1"; exit 0; }
fail() { printf 'FAIL %s: %s\n' "$NAME" "$1"; exit 1; }

[ -f "$DOC" ] || fail "$DOC not found (subject must exist; an absent contract is not a pass)"

# Extract the fenced block that follows a given heading. Bounded by the HEADING and the fence, never
# by a line count -- a count goes stale on the next edit, the defect class of stale
# line-number citations.
extract() { # $1 = heading text to anchor on
  awk -v want="$1" '
    index($0, want) == 1 { seen = 1; next }
    seen && !inblock && /^````/ { inblock = 1; next }
    inblock && /^````/ { exit }
    inblock { print }
  ' "$DOC"
}

rc=0
checked=0

check_one() { # $1 = heading anchor, $2 = real script path
  local anchor="$1" real="$ROOT/$2" embedded tmp nheads
  if [ ! -f "$real" ]; then
    printf 'FAIL %s: %s not found -- refusing to compare the shipped copy against nothing\n' "$NAME" "$2"
    rc=1; return
  fi
  # A DUPLICATE heading is a hard failure, not a thing to resolve by precedence. `extract` reads the
  # first match and exits, so an earlier section carrying a correct copy hides drift in the later
  # real one -- measured: inserted an earlier duplicate, corrupted the intended section, invariant
  # stayed green. There is no right answer to "which copy is the real one", so refuse to guess.
  nheads="$(grep -cF -- "$anchor" "$DOC")"
  if [ "$nheads" -eq 0 ]; then
    # ZERO and TWO are different facts and get different sentences: the section is gone, versus the
    # section is ambiguous. Collapsing them sends the reader to the wrong repair.
    printf 'FAIL %s: extracted ZERO lines for `%s` -- the section is MISSING from the contract (its heading `%s` appears nowhere), so an adopter materializing their gate would not get the script at all\n' "$NAME" "$2" "$anchor"
    rc=1; return
  fi
  if [ "$nheads" -ne 1 ]; then
    printf 'FAIL %s: the heading `%s` appears %s times in the contract -- exactly one is required, because the extractor reads the first and a duplicate hides drift in the other\n' "$NAME" "$anchor" "$nheads"
    rc=1; return
  fi
  embedded="$(mktemp)"
  extract "$anchor" > "$embedded"
  if [ ! -s "$embedded" ]; then
    # An empty extraction means the document's layout changed under this parser, not that the copy
    # is clean. Passing here would be the vacuous-pass class.
    printf 'FAIL %s: extracted ZERO lines for `%s` -- the section is missing, or its fence/heading changed and this parser no longer finds it (a vacuous pass is not a pass)\n' "$NAME" "$2"
    rm -f "$embedded"; rc=1; return
  fi
  checked=$((checked + 1))
  if diff -q "$real" "$embedded" >/dev/null 2>&1; then
    :
  else
    printf 'FAIL %s: the copy of %s in the adopter contract has drifted from the real script.\n' "$NAME" "$2"
    printf '  first difference (< shipped script, > copy in the document):\n'
    diff "$real" "$embedded" | head -12 | sed 's/^/    /'
    printf '  Fix by regenerating the copy from the script, never the other way round.\n'
    rc=1
  fi
  rm -f "$embedded"
}

check_one '## AC-oracle binding — `scripts/ac-evidence.sh`' scripts/ac-evidence.sh
check_one '## AC baseline — `scripts/ac-baseline.sh`'      scripts/ac-baseline.sh

[ "$checked" -eq 2 ] || { printf 'FAIL %s: compared %s of 2 expected copies -- refusing to report on a partial set\n' "$NAME" "$checked"; rc=1; }
[ "$rc" -eq 0 ] || exit 1

pass "both companion scripts are shipped in the adopter contract, byte-identical to the real ones"
