#!/usr/bin/env bash
# the characterization baseline: a SEPARATE record of what a behavior's test did,
# before and after a change, so a transition can be checked against the behavior's class.
#
# This is deliberately NOT the test-evidence fingerprint. That fingerprint (close-gate.sh
# evidence_digest) hashes the BYTES of the validator's input files and says nothing about
# whether a command ran or what it returned -- it recomputes identically no matter what any
# process did. The baseline records the orthogonal fact: the command, its exit code, and the
# environment it ran in, captured by the coding agent's own run.
#
# Record (.claude/behavior-baseline.tsv): 6 tab-separated columns, `#` is a comment, ends NL.
#   id  state  exit  cmd  env  date
#
# id    : ^BL-[0-9]+$          (a behavior in the registry)
# state : before | after
# exit  : an integer, or `na` for "the test did not exist yet" (a NEW behavior, before)
# cmd   : the command run
# env   : a label identifying the environment (interpreter/os/sha -- enough to reproduce)
# date  : YYYY-MM-DD
#
# Transition contract, checked against the registry class:
#   PRESERVE  pass(0)   before -> pass(0)  after
#   FIX       fail(!=0) before -> pass(0)  after
#   NEW       na        before -> pass(0)  after
# A row whose observed before->after contradicts its class is red, not silently green.
#
# jq-only envelope: no jq, no python3 (CLAUDE.md).

set -uo pipefail

LOG="${PLC_BEHAVIOR_BASELINE:-.claude/behavior-baseline.tsv}"
REGISTRY="${PLC_BEHAVIOR_LOCK:-.claude/behavior-lock.tsv}"

STATES="before after"

die() { printf 'behavior-baseline: %s\n' "$1" >&2; exit "${2:-2}"; }

valid_exit() { case "$1" in na) return 0 ;; ''|*[!0-9]*) return 1 ;; *) return 0 ;; esac; }

# last_exit <id> <state> [file] -- the most recent recorded exit for id in that state; empty none.
last_exit() {
  local id="$1" st="$2" f="${3:-$LOG}"
  [ -f "$f" ] || return 0
  grep -v '^#' "$f" \
    | awk -F'\t' -v id="$id" -v st="$st" '$1==id && $2==st{e=$3} END{if (e!="") print e}'
}

# class_of <id> [registry] -- the behavior's class from the registry, empty if not present.
class_of() {
  local id="$1" f="${2:-$REGISTRY}"
  [ -f "$f" ] || return 0
  grep -v '^#' "$f" | awk -F'\t' -v id="$id" '$1==id{print $2; exit}'
}

case "${1:-}" in
  --record)
    # --record <id> <state> <exit> <cmd> <env>
    [ $# -ge 6 ] || die "usage: --record <id> <state> <exit> <cmd> <env>" 64
    id="$2"; st="$3"; ex="$4"; cmd="$5"; env="$6"
    printf '%s' "$id" | grep -qE '^BL-[0-9]+$' || die "bad id shape \"$id\" (want BL-<n>)" 1
    case " $STATES " in *" $st "*) ;; *) die "bad state \"$st\" (want before|after)" 1 ;; esac
    valid_exit "$ex" || die "bad exit \"$ex\" (want an integer or na)" 1
    [ -n "$cmd" ] || die "empty cmd" 1
    [ -n "$env" ] || die "empty env" 1
    [ -f "$LOG" ] || printf '# id\tstate\texit\tcmd\tenv\tdate\n' > "$LOG"
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$id" "$st" "$ex" "$cmd" "$env" "$(date +%F)" >> "$LOG"
    ;;

  --get)
    # --get <id> <state> -- print the most recent exit for id in that state
    [ $# -ge 3 ] || die "usage: --get <id> <state>" 64
    last_exit "$2" "$3"
    ;;

  --check-transition)
    # --check-transition <id> [class] -- class defaults to the registry's class for id
    [ $# -ge 2 ] || die "usage: --check-transition <id> [class]" 64
    id="$2"
    cls="${3:-$(class_of "$id")}"
    [ -n "$cls" ] || die "no class for $id (not in the registry, and none given)" 2
    before="$(last_exit "$id" before)"
    after="$(last_exit "$id" after)"
    [ -n "$before" ] || die "no before-baseline recorded for $id" 2
    [ -n "$after" ] || die "no after-result recorded for $id" 2
    ok=0
    case "$cls" in
      PRESERVE) [ "$before" = 0 ] && [ "$after" = 0 ] && ok=1 ;;
      FIX)      [ "$before" != 0 ] && [ "$before" != na ] && [ "$after" = 0 ] && ok=1 ;;
      NEW)      [ "$before" = na ] && [ "$after" = 0 ] && ok=1 ;;
      *)        die "unknown class \"$cls\" for $id" 2 ;;
    esac
    if [ "$ok" = 1 ]; then
      printf 'OK %s: %s transition before=%s after=%s holds\n' "$id" "$cls" "$before" "$after"
    else
      printf 'CONTRADICTS %s: class %s expects ' "$id" "$cls"
      case "$cls" in
        PRESERVE) printf 'pass->pass' ;;
        FIX)      printf 'fail->pass' ;;
        NEW)      printf 'na->pass' ;;
      esac
      printf ', observed before=%s after=%s\n' "$before" "$after"
      exit 1
    fi
    ;;

  --check-file)
    f="${2:-$LOG}"
    [ -f "$f" ] || die "no such baseline: $f" 2
    rc=0; n=0
    while IFS= read -r line; do
      case "$line" in ''|'#'*) continue ;; esac
      n=$((n + 1))
      ncol="$(printf '%s' "$line" | awk -F'\t' '{print NF}')"
      [ "$ncol" = 6 ] || { printf 'behavior-baseline: not 6 columns (%s): %s\n' "$ncol" "$line" >&2; rc=1; continue; }
      bid="$(printf '%s' "$line" | cut -f1)"; bst="$(printf '%s' "$line" | cut -f2)"; bex="$(printf '%s' "$line" | cut -f3)"
      printf '%s' "$bid" | grep -qE '^BL-[0-9]+$' || { printf 'behavior-baseline: bad id "%s": %s\n' "$bid" "$line" >&2; rc=1; }
      case " $STATES " in *" $bst "*) ;; *) printf 'behavior-baseline: bad state "%s": %s\n' "$bst" "$line" >&2; rc=1 ;; esac
      valid_exit "$bex" || { printf 'behavior-baseline: bad exit "%s": %s\n' "$bex" "$line" >&2; rc=1; }
    done < "$f"
    printf 'checked %s baseline row(s)\n' "$n"
    exit $rc
    ;;

  *)
    cat >&2 <<'USAGE'
usage: behavior-baseline.sh <mode>
  --record <id> <state> <exit> <cmd> <env>   append a baseline/after record
  --get <id> <state>                         most recent exit for id in that state
  --check-transition <id> [class]            verify before->after matches the class (exit 1 if not)
  --check-file [FILE]                         validate every row
USAGE
    exit 64
    ;;
esac
