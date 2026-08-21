#!/usr/bin/env bash
# Invariant: every closure-log line THIS BRANCH ADDS is legal, and no older line was touched.
#
# Scope is the whole design, not an implementation detail. The gate reads only tracked files and
# judges only what the branch added. It says nothing about whether the backlog entry an id refers
# to is "really" closed — that could only be decided by reading the heading word, which is the
# heuristic the closure log replaces, so a gate resting on it would be certifying the
# heuristic against itself rather than checking anything.
#
# Six criteria, all against the lines this branch appended to .claude/backlog-closures.tsv:
#
#   0. the file ends with a newline
#   1. 5 tab-separated columns, event/reason in domain      (delegated to backlog-closures.sh)
#   2. id shape B<n>[.<n>]                                  (delegated to backlog-closures.sh)
#   3. no added line re-closes an id whose last prior STATE-BEARING event is already `closed`
#   4. append-only, as a BYTE PREFIX of the base version
#   5. an added `ref-amend` names an id that already has at least one event
#
# Criterion 3 reads past `ref-amend` lines deliberately — see the comment at the join. An amend
# is not a transition, so letting one sit between two closures would hide the second from the
# very criterion built to catch it.
#
# Criterion 3 is deliberately narrow. "The same id must not be closed twice" is history-
# dependent, so implemented literally the gate must scan the whole file — and then a base that
# already contains one historical duplicate turns the gate red on a branch that added nothing at
# all. That is a gate that blocks every push in the repo.
# The cost: duplicates already sitting in history
# are never found by this gate.
#
# Criterion 4 is a byte prefix rather than `git diff` line semantics, for a measured reason too:
# when the base file lacks a trailing newline, an ordinary append makes git render the last old
# line as `-`/`+`, and a diff-based check rejects a legal append. Criterion 0 stops that state
# from being committed in the first place, and the prefix comparison normalises it once so an
# already-committed one cannot deadlock.
#
# The base is `git merge-base HEAD main`, NOT main's tip. With parallel sessions on one repo,
# an advancing tip would fail a perfectly legal older branch.

set -uo pipefail

NAME="backlog-closure-log"
LOG=".claude/backlog-closures.tsv"
PARSER="$(dirname "$0")/../backlog-closures.sh"

pass() { printf 'PASS %s: %s\n' "$NAME" "$1"; exit 0; }
fail() { printf 'FAIL %s: %s\n' "$NAME" "$1"; exit 1; }

# No log at all is not a violation — the file only exists once a phase starts declaring closures.
[ -f "$LOG" ] || pass "no closure log in this tree — nothing to check"
[ -f "$PARSER" ] || fail "parser missing at $PARSER (the gate cannot validate lines without it)"

# --- criterion 0 -------------------------------------------------------------------------
# Runs on $LOG BEFORE the split, because it is a property of the working file alone and does
# not depend on the base.
if [ -s "$LOG" ] && [ "$(tail -c1 "$LOG" | od -An -c | tr -d ' ')" != '\n' ]; then
  fail "$LOG does not end with a newline — the next append would rewrite its last line"
fi

# The base/added split lives in scripts/lib/closure-log-added.sh, because
# `closure-declaration.sh reconcile` needs the SAME added set and a second computation of it
# would be a copy. Criterion 4 stays HERE: the helper deliberately does not verify
# append-only-ness, only who added what.
# A MISSING OR BROKEN HELPER IS A HARD FAILURE, and this is not defensive ceremony -- it is a
# measured defect. The first extraction sourced the helper without checking, and in the suite
# throwaway-repo fixture (where scripts/lib/ did not exist) the source failed,
# closure_log_split was undefined, BASE and ADDED stayed empty, and the gate RETURNED 0:
# criterion 4 silently switched itself off. A guard whose dependency can go missing without a
# sound is worse than no guard, because the transcript then carries a green nobody re-checks.
# shellcheck source=../lib/closure-log-added.sh
_CLS_LIB="$(dirname "$0")/../lib/closure-log-added.sh"
[ -r "$_CLS_LIB" ] || fail "helper missing at $_CLS_LIB — this gate cannot compute its added set without it"
# shellcheck disable=SC1090
. "$_CLS_LIB" || fail "helper at $_CLS_LIB could not be sourced"
command -v closure_log_split >/dev/null 2>&1 \
  || fail "helper at $_CLS_LIB sourced but did not define closure_log_split"

BASE="$(mktemp)"; ADDED="$(mktemp)"
trap 'rm -f "$BASE" "$ADDED"' EXIT
_split="$(closure_log_split "$LOG" "$BASE" "$ADDED")"
BASE_REF="$(printf '%s' "$_split" | cut -f1)"

# --- criterion 4: byte prefix ---------------------------------------------------------------
BLEN="$(printf '%s' "$_split" | cut -f2)"
# BLEN=0 is guarded explicitly: BSD `head -c 0` is an ERROR, not an empty read. Unguarded it
# printed `head: illegal byte count -- 0` to stderr and produced no output, whose checksum
# happens to equal the empty base's — so the check passed **because it failed**, and the wrong
# answer was invisible because it coincided with the right one.
if [ "$BLEN" -gt 0 ] && [ "$(head -c "$BLEN" "$LOG" | cksum)" != "$(cksum < "$BASE")" ]; then
  fail "$LOG is not a byte-prefix extension of its base ($BASE_REF) — an existing line was changed, deleted, reordered, or something was inserted above the end. The log is append-only."
fi
# ADDED was already produced by closure_log_split above, from the same BLEN this criterion
# just verified. It is deliberately NOT recomputed here: two computations of the same set is
# a copy, and a copied guard drifts.

# --- criteria 1, 2, 3 over the added lines ---------------------------------------------------
# `seen` counts added event lines so criterion 3 can look at "the added lines strictly before
# this one". It is counted with awk, never `head -n $((seen-1))`: BSD `head -n 0` is an error,
# and a probe that relied on it produced the right answer only because the failure happened to
# return an empty string.
n=0
rc=0
while IFS= read -r line; do
  case "$line" in ''|'#'*) continue ;; esac
  n=$((n + 1))

  if ! msg="$(printf '%s\n' "$line" | /bin/bash "$PARSER" --check-line 2>&1)"; then
    printf 'FAIL %s: %s\n' "$NAME" "${msg#backlog-closures: }"
    rc=1
    continue
  fi

  ev="$(printf '%s' "$line" | cut -f2)"
  case "$ev" in closed|ref-amend) ;; *) continue ;; esac
  id="$(printf '%s' "$line" | cut -f1)"

  # --- criterion 5 ---------------------------------------------------------------------------
  # An amend names an existing event's reference, so there has to BE one. Amending an id with no
  # history is not a smaller mistake than a duplicate closure — it writes a reference into the
  # log for a closure that was never declared, and every reader downstream treats the log as the
  # authority. Counted over the same filtered stream as `prior` below, for the same reason.
  if [ "$ev" = ref-amend ]; then
    nprior="$( { grep -v '^#' "$BASE"; grep -v '^#' "$ADDED" | grep -v '^$' | awk -v k="$n" 'NR<k'; } \
               | awk -F'\t' -v id="$id" '$1==id{c++} END{print c+0}' )"
    if [ "$nprior" -eq 0 ]; then
      printf 'FAIL %s: the added ref-amend for %s has no prior event to amend — a reference cannot be recorded for a closure that was never declared\n' "$NAME" "$id"
      rc=1
    fi
    continue
  fi

  # BOTH sides of this join must be filtered by the SAME predicate as the counter `n`, which
  # skips comments AND blank lines. The first version stripped only comments from the stream
  # while the counter also skipped blanks, so every blank line at or before position k shortened
  # the "strictly before this one" window by one from its tail -- and a duplicate closure sitting
  # in that shortened tail was accepted. Reproduced against this very gate: two adjacent
  # duplicate closures FAIL, and the byte-identical pair with one blank line above them PASS.
  # `ref-amend` is excluded from this join for the same reason `last_event` excludes it: it is
  # not a transition. Included, a single amend between two closures would make the second one's
  # `prior` read `ref-amend`, and the duplicate this criterion exists to catch would walk through.
  prior="$( { grep -v '^#' "$BASE"; grep -v '^#' "$ADDED" | grep -v '^$' | awk -v k="$n" 'NR<k'; } \
            | awk -F'\t' -v id="$id" '$1==id && $2!="ref-amend"{e=$2} END{print e}' )"
  if [ "$prior" = closed ]; then
    printf 'FAIL %s: the added line closing %s duplicates a closure that is already the last event for that id — append a `reopen` first if it really was reopened\n' "$NAME" "$id"
    rc=1
  fi
done < "$ADDED"

[ "$rc" -eq 0 ] || exit 1
pass "examined $n added line(s); all legal and the log is append-only"
