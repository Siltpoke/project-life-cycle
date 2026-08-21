#!/usr/bin/env bash
# Run identity, the on-disk layout, and attempt numbering.
#
# Modes:
#   run-id --phase <token>                  print this writer's run id (see IDENTITY below)
#   ledger-path <run_id> [--repo-root R]    print the ledger file for that run
#   next-attempt <file> <stage_id>          the next attempt number for that stage in that file
#
# IDENTITY.
# Run identity is per SESSION rather than per-branch, because two concurrent sessions on one
# branch would otherwise derive the same id, target the same file, and break the rule "every ledger file
# has exactly one writer process for its whole life".
#
# Per-session alone does not deliver that property either. One session can host two concurrent
# writer processes — a project's gate can be running in a background shell while another
# invocation starts — and they would collide in exactly the way per-branch did, one level down. So
# the id minted here is
#
#     <phase>-<session-token>-<pid>-<epoch>
#
# which keeps the session grouping AND makes the single-writer property literally true,
# because no two live processes share a pid. The reader never needed the file to be per-session:
# `phase` is a field on every record, so a phase's timeline is a merge across ids either way.
# The session token is a short digest of the host's session id when one is
# exported, and `nosess` when none is — which is a fact about the host, not a failure.
#
# MINT ONCE PER PROCESS, THEN EXPORT. `run-id` honours `PLC_RUN_ID` when it is already set and mints
# only otherwise. A caller that needs a stable id across several invocations must capture it once
# and export it — calling this twice can straddle a second boundary and produce two ids, which is
# two files, which is a split run rather than a lost one, but still wrong. close-gate.sh mints
# once per run, inside its ledger flush, and passes that one id to every append.
#
# Envelope: bash + jq + coreutils + git. No python3.

set -euo pipefail

die() { printf 'ledger-run: %s\n' "$1" >&2; exit "${2:-2}"; }

usage() {
  cat >&2 <<'EOF'
usage:
  ledger-run.sh run-id --phase <token>
  ledger-run.sh ledger-path <run_id> [--repo-root <dir>]
  ledger-run.sh next-attempt <ledger.jsonl> <stage_id>
EOF
}

# A short, filename-safe digest of the host session id. Hashed rather than embedded: a session id is
# an opaque host string that may contain a path separator or be long enough to be unwieldy in a
# filename, and nothing downstream needs to read it back — it exists to keep two sessions apart.
session_token() {
  local raw="${PLC_SESSION_ID:-${CLAUDE_SESSION_ID:-}}"
  if [ -z "$raw" ]; then
    printf 'nosess'
    return 0
  fi
  # `git hash-object` rather than `shasum`: shasum is a perl script on macOS, which the gate scripts
  # already avoid (scripts/potency-runner.sh, scripts/close-gate.sh).
  # `cut -c` on a git object id is safe on any machine: the input is ASCII hex, so
  # byte and character counting agree. Named in test_utf8_text_helpers.py's exemption
  # list with that reason rather than silently skipped.
  printf '%s' "$raw" | git hash-object --stdin | cut -c1-12
}

cmd_run_id() {
  local phase=""
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --phase) [ "$#" -ge 2 ] || die "--phase needs a value"; phase="$2"; shift 2 ;;
      *) die "unknown argument: $1" ;;
    esac
  done
  if [ -n "${PLC_RUN_ID:-}" ]; then
    printf '%s\n' "$PLC_RUN_ID"
    return 0
  fi
  [ -n "$phase" ] || die "--phase is required when PLC_RUN_ID is unset"
  case "$phase" in
    *[!a-zA-Z0-9._-]*) die "phase token must be filename-safe (a-z A-Z 0-9 . _ -): $phase" ;;
  esac
  printf '%s-%s-%s-%s\n' "$phase" "$(session_token)" "$$" "$(date -u +%s)"
}

cmd_ledger_path() {
  [ "$#" -ge 1 ] || { usage; exit 2; }
  local run_id="$1"; shift
  local root="" owner_pid=""
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --repo-root) [ "$#" -ge 2 ] || die "--repo-root needs a value"; root="$2"; shift 2 ;;
      --owner-pid) [ "$#" -ge 2 ] || die "--owner-pid needs a value"; owner_pid="$2"; shift 2 ;;
      *) die "unknown argument: $1" ;;
    esac
  done
  [ -n "$run_id" ] || die "run id must not be empty"
  # A run id reaches the filesystem as a filename. Anything that could climb out of the directory is
  # refused here rather than sanitised — silently rewriting an identifier makes two runs collide.
  case "$run_id" in
    *[!a-zA-Z0-9._-]*) die "run id must be filename-safe (a-z A-Z 0-9 . _ -): $run_id" ;;
    .|..) die "run id must not be a directory entry: $run_id" ;;
  esac
  if [ -z "$root" ]; then
    root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
    [ -n "$root" ] || root="$PWD"
  fi
  # TWO statements, not one. `local a="x" b="$a"` expands ALL of its arguments before `local`
  # runs, so `$a` is still unset at that moment -- under `set -u` that is a fatal "unbound
  # variable", which is exactly what it produces.
  local dir="$root/.claude/.gate-runs/ledger"
  local target="$dir/$run_id.jsonl"

  # OWNERSHIP IS CLAIMED HERE, because `PLC_RUN_ID` made it claimable by two processes at once.
  #
  # `run-id` honours an exported `PLC_RUN_ID` and has to: a caller that exports it makes
  # every invocation in one session belong to one run. But look at what
  # that buys -- export it in two shells and both processes derive the SAME id, the same path, and
  # append to one file. The central claim ("exactly one writer process for its whole life")
  # was defeated by an environment variable.
  #
  # The fix is a claim, not a lock: the first caller to ask for this path stamps its pid beside the
  # ledger, and a later caller with a DIFFERENT LIVE pid is refused. What it does and does not buy:
  #   * a dead owner's stamp is taken over -- a crashed run must not wedge its own run id forever;
  #   * the window between reading the stamp and writing it is real and unclosed. This narrows the
  #     hole from "any two exported shells, always" to "two processes inside one file-write" --
  #     honest narrowing, not elimination, and said here rather than discovered later;
  #   * a refusal is exit 2 and NOTHING is printed, so a caller wrapping this fail-open (which every
  #     writer does) loses a record and never a verdict. That is the designed direction.
  # THE OWNER IS THE CALLER, NOT THIS SCRIPT. The first version stamped `$$` -- this script's own
  # pid -- and that is always dead a millisecond later, because `ledger-path` is a one-shot. Every
  # later caller then found a dead owner and reclaimed the id, so the guard passed its own probe by
  # never refusing anything. Measured: the second concurrent caller got the path handed to it.
  #
  # The writer is whoever holds the run id across appends, and only that process knows its pid, so
  # it declares it: `--owner-pid $$`. `$PPID` is the default because it is right for the common case
  # (a writer invoking this directly) and wrong quietly enough to be worth naming: a caller that
  # shells out through an extra layer must pass the flag or it will claim ownership for a wrapper
  # that exits first.
  mkdir -p "$dir" 2>/dev/null || true
  [ -n "$owner_pid" ] || owner_pid="$PPID"
  case "$owner_pid" in ''|*[!0-9]*) die "--owner-pid must be a pid: $owner_pid" ;; esac
  local owner_file="$dir/.$run_id.owner" owner=""
  # An owner stamp that EXISTS and cannot be READ is not "no owner" -- it is an unanswered
  # question, and treating it as absence overwrote a live owner's claim and handed out the path.
  # Same trade as the claim-persistence check below: fail-open must cost the record, never
  # the guarantee.
  if [ -e "$owner_file" ] && [ ! -r "$owner_file" ]; then
    die "ownership stamp $owner_file exists but cannot be read -- refusing to hand out a ledger path whose current owner is unknown" 1
  fi
  [ -r "$owner_file" ] && owner="$(head -1 "$owner_file" 2>/dev/null | tr -d "[:space:]")" || true
  if [ -n "$owner" ] && [ "$owner" != "$owner_pid" ]; then
    if kill -0 "$owner" 2>/dev/null; then
      die "run id $run_id is already owned by live pid $owner -- two processes must not share one ledger file. If that pid is not a writer for this run, remove $owner_file." 2
    fi
  fi
  # IF THE CLAIM CANNOT BE PERSISTED, THERE IS NO CLAIM. This was `|| true`, so `ledger-path`
  # returned a path with exit 0 while the stamp had failed to land -- and both callers honour only
  # "non-zero or empty stdout", so they proceeded to write a ledger nobody owned. Fail-open applied
  # one step too broadly: the point of fail-open is that a bookkeeping failure costs a RECORD, and
  # here it was costing the guarantee instead while still writing the record. Refusing gives the
  # callers exactly what they already handle, and the record they skip renders claimed/missing.
  if ! printf '%s\n' "$owner_pid" > "$owner_file" 2>/dev/null; then
    die "cannot record ownership of $run_id at $owner_file -- refusing to hand out a ledger path whose single-writer claim did not persist" 1
  fi
  printf '%s\n' "$target"
}

# The next attempt number for one stage inside one file. Safe because the file has exactly one
# writer — there is no allocator race to lose. Returns 1 when the stage has no record yet.
#
# Reading the file to mint is NOT the read-modify-write that the single-writer rule bans: that ban is about rewriting
# the file, and this only ever reads it and then appends a new line.
cmd_next_attempt() {
  [ "$#" -eq 2 ] || { usage; exit 2; }
  local file="$1" stage="$2" max
  command -v jq >/dev/null 2>&1 || die "jq not found"
  if [ ! -f "$file" ]; then
    printf '1\n'
    return 0
  fi
  # THE SAME PARSE RULE THE READER APPLIES. `jq -s` fails on the WHOLE file if one line is
  # malformed, and the old `|| printf 0` then answered "1" for a stage that already had attempt 1 --
  # handing out an id that exists, which is the collision the file-level attempt-sequence contract
  # is there to make impossible. The reader parses per line, so the writer must too.
  #
  # A file with an unparseable line REFUSES rather than guesses. Every caller wraps this fail-open
  # so a refusal costs one unwritten record and never a verdict -- and an unwritten
  # record renders `claimed`/`missing`, never `observed`. Guessing costs a duplicate attempt id,
  # which is silent and permanent.
  local parsed
  parsed="$(jq -R -s 'sub("\n$"; "") | if . == "" then [] else split("\n") end
                      | map(try fromjson catch {"__unparseable__": true})' "$file" 2>/dev/null)" ||
    die "cannot read $file" 1
  if printf '%s' "$parsed" | jq -e 'any(.[]?; (type == "object") and (.__unparseable__ == true))' >/dev/null 2>&1; then
    die "$file has at least one unparseable line -- refusing to mint an attempt id from a file this cannot read (run: /bin/bash scripts/ledger-append.sh validate $file)" 1
  fi
  max="$(printf '%s' "$parsed" | jq -r --arg s "$stage" '
      [ .[] | select(type == "object") | select(.stage_id == $s) | .attempt_id
        | select(type == "number") ] | max // 0
    ' 2>/dev/null || printf '0')"
  [ -n "$max" ] && [ "$max" != "null" ] || max=0
  printf '%s\n' "$((max + 1))"
}

main() {
  [ "$#" -ge 1 ] || { usage; exit 2; }
  local mode="$1"; shift
  case "$mode" in
    run-id)       cmd_run_id "$@" ;;
    ledger-path)  cmd_ledger_path "$@" ;;
    next-attempt) cmd_next_attempt "$@" ;;
    -h|--help)    usage; exit 0 ;;
    *)            usage; exit 2 ;;
  esac
}

main "$@"
