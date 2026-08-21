#!/usr/bin/env bash
# The closure log: parser and state derivation.
#
# Backlog `state` used to be a word guessed out of a heading: `backlog-toc.sh` ran a substring
# `case` over the title text and called an entry closed if it happened to contain ✅ / DONE /
# CLOSED / MERGED. The truth of the whole column therefore depended on which word whoever wrote
# the heading happened to reach for, and many entries rendered as `—`, which meant "nothing
# matched" and was read by both a human and an AI as "not done".
#
# State is now DERIVED from this file: an append-only list of events, one per line. The file
# records what happened on a day (a moment); the state is computed from it. That is the shape
# the doctrine "Documents record moments, never states" asks for.
#
# The declaration deliberately does NOT live in a git trailer. That was the original design and
# it does not survive a squash merge: GitHub rewrites the commit message and appends
# its own `Co-authored-by:` paragraph, and git reads only the LAST paragraph as the trailer
# block — so an authored trailer is pushed out of it.
#
# Format: 5 tab-separated columns, `#` starts a comment, the file must end with a newline.
#
#   id  event  reason  date  ref
#
# event  : closed | partial | reopen | ref-amend
# reason : completed | moved | not_planned | duplicate | superseded | -
#          (`-` only for reopen and ref-amend, which carry no reason)
# ref    : free text; `-` means none. `ref-amend` is the one event that REQUIRES a real one.
#
# Derivation takes an id's LAST STATE-BEARING event — `ref-amend` is skipped:
#
#   (no events) -> open
#   closed      -> closed (<reason>)
#   partial     -> open      (a half-closed item is still open; the event keeps the detail)
#   reopen      -> open
#   ref-amend   -> (no state; see below)
#
# `ref-amend` exists because a closure and its PR number are known at DIFFERENT MOMENTS. A phase
# closes locally, and its PR is opened and merged afterwards, so the closure event has to be
# written with a ref that does not exist yet. Without this event there is no legal way to record
# the number later: appending a second `closed` trips the gate's duplicate-closure criterion,
# editing the old line trips its append-only criterion, and the `reopen` the error message
# suggests would be a false event.
#
# It records a MOMENT — "the reference became known" — and deliberately carries no state, so
# amending a ref can never change whether an entry reads open or closed. `last_event` skips it
# and the gate's duplicate-closure check skips it too; if it did not, one amend between two
# closures would hide the second from the criterion that exists to catch it.
#
# jq-only envelope: no python3 anywhere in this file or anything it calls.

set -uo pipefail

LOG="${PLC_CLOSURE_LOG:-.claude/backlog-closures.tsv}"

EVENTS="closed partial reopen ref-amend"
REASONS="completed moved not_planned duplicate superseded -"

die() { printf 'backlog-closures: %s\n' "$1" >&2; exit "${2:-2}"; }

# ---------------------------------------------------------------------------------------------
# line-level validation
# ---------------------------------------------------------------------------------------------

# check_line <line> — prints nothing on success; prints the reason and returns 1 on failure.
# Out-of-domain values are ERRORS, never silently-accepted values: a reason nobody recognises
# would otherwise render into the index as authoritative text.
check_line() {
  local line="$1" ncol id ev rs rf
  case "$line" in ''|'#'*) return 0 ;; esac

  ncol="$(printf '%s' "$line" | awk -F'\t' '{print NF}')"
  if [ "$ncol" != 5 ]; then
    printf 'not 5 tab-separated columns (%s): %s\n' "$ncol" "$line"; return 1
  fi

  id="$(printf '%s' "$line" | cut -f1)"
  ev="$(printf '%s' "$line" | cut -f2)"
  rs="$(printf '%s' "$line" | cut -f3)"
  rf="$(printf '%s' "$line" | cut -f5)"

  printf '%s' "$id" | grep -qE '^B[0-9]+(\.[0-9]+)?$' \
    || { printf 'bad id shape "%s": %s\n' "$id" "$line"; return 1; }
  case " $EVENTS " in *" $ev "*) ;; *) printf 'bad event "%s": %s\n' "$ev" "$line"; return 1 ;; esac
  case " $REASONS " in *" $rs "*) ;; *) printf 'bad reason "%s": %s\n' "$rs" "$line"; return 1 ;; esac

  # `-` is the reopen placeholder and means "no reason applies". Allowing it on a `closed` line
  # would let a closure be declared with no stated cause, which is the hand-written state the log
  # exists to remove.
  if [ "$ev" = closed ] && [ "$rs" = "-" ]; then
    printf 'a closed event needs a real reason, not "-": %s\n' "$line"; return 1
  fi
  if [ "$ev" = reopen ] && [ "$rs" != "-" ]; then
    printf 'a reopen event takes reason "-", got "%s": %s\n' "$rs" "$line"; return 1
  fi
  if [ "$ev" = ref-amend ] && [ "$rs" != "-" ]; then
    printf 'a ref-amend event takes reason "-", got "%s": %s\n' "$rs" "$line"; return 1
  fi
  # The whole point of this event is the ref, so `-` (which means "none") makes it a no-op line
  # that still reads, to anyone scanning the log, as though a reference had been supplied.
  if [ "$ev" = ref-amend ] && [ "$rf" = "-" ]; then
    printf 'a ref-amend event exists to carry a ref, so "-" is not one: %s\n' "$line"; return 1
  fi
  return 0
}

# ---------------------------------------------------------------------------------------------
# derivation
# ---------------------------------------------------------------------------------------------

# last_event <id> [file] — the id's most recent STATE-BEARING event, empty if it has none.
# `ref-amend` is filtered out here rather than handled in `derive`: it is not a transition, so an
# id whose newest line is an amend must still derive from the closure underneath it.
last_event() {
  local id="$1" f="${2:-$LOG}"
  [ -f "$f" ] || return 0
  grep -v '^#' "$f" \
    | awk -F'\t' -v id="$id" '$1==id && $2!="ref-amend"{e=$2; r=$3} END{if (e != "") print e "\t" r}'
}

# derive <id> [file] — the rendered state.
derive() {
  local id="$1" f="${2:-$LOG}" ev rs pair
  pair="$(last_event "$id" "$f")"
  [ -n "$pair" ] || { printf 'open\n'; return 0; }
  ev="$(printf '%s' "$pair" | cut -f1)"
  rs="$(printf '%s' "$pair" | cut -f2)"
  case "$ev" in
    closed)  printf 'closed (%s)\n' "$rs" ;;
    # `partial` and `reopen` both render open. By design, a half-closed (`partial`) entry counts as
    # open so it keeps showing up in planning; the event itself stays in the log as the detail.
    partial) printf 'open\n' ;;
    reopen)  printf 'open\n' ;;
    *)       die "underivable event '$ev' for $id" 3 ;;
  esac
}

# ---------------------------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------------------------

usage() {
  cat >&2 <<'USAGE'
usage: backlog-closures.sh <mode>
  --check-line          read one line on stdin, validate it (exit 1 on a bad line)
  --check-file [FILE]   validate every line of the log
  --list-ids [FILE]     every id that has at least one event
  --derive ID [FILE]    the derived state for one id
  --derive-event EVENT  the state an event of this kind derives to (domain probe)
  --states [FILE]       every id and its derived state, tab-separated
USAGE
  exit 64
}

[ $# -ge 1 ] || usage

case "$1" in
  --check-line)
    IFS= read -r line || line=""
    if ! msg="$(check_line "$line")"; then printf 'backlog-closures: %s\n' "$msg" >&2; exit 1; fi
    ;;

  --check-file)
    f="${2:-$LOG}"
    [ -f "$f" ] || die "no such log: $f" 2
    rc=0; n=0
    while IFS= read -r line; do
      case "$line" in ''|'#'*) continue ;; esac
      n=$((n + 1))
      if ! msg="$(check_line "$line")"; then printf 'backlog-closures: %s\n' "$msg" >&2; rc=1; fi
    done < "$f"
    printf 'checked %s event line(s)\n' "$n"
    exit $rc
    ;;

  --list-ids)
    f="${2:-$LOG}"
    # ONLY the pinned file. A same-shaped TSV sitting anywhere else must never be picked up —
    # the log's authority comes from its path, not from its shape.
    [ -f "$f" ] || exit 0
    grep -v '^#' "$f" | cut -f1 | grep -v '^$' | sort -u
    ;;

  --derive)
    [ $# -ge 2 ] || usage
    derive "$2" "${3:-$LOG}"
    ;;

  --derive-event)
    [ $# -ge 2 ] || usage
    case "$2" in
      closed)  printf 'closed (<reason>)\n' ;;
      partial) printf 'open\n' ;;
      reopen)  printf 'open\n' ;;
      # NOT `open`. This probe answers "what state does an event of this kind derive to", and
      # printing a state here would assert that amending a ref can move an entry — the exact
      # thing the event is built not to do. It has no answer, and says so.
      ref-amend) printf 'no state (records a reference, not a transition)\n' ;;
      *)       die "not an event: $2" 3 ;;
    esac
    ;;

  --states)
    f="${2:-$LOG}"
    [ -f "$f" ] || exit 0
    for id in $(grep -v '^#' "$f" | cut -f1 | grep -v '^$' | sort -u); do
      printf '%s\t%s\n' "$id" "$(derive "$id" "$f")"
    done
    ;;

  *) usage ;;
esac
