#!/usr/bin/env bash
# The lifecycle ledger's SOLE JSON emitter, and the one definition of a valid record.
#
# Two modes:
#   append   --file F --run-id … --stage-id … …    emit exactly ONE line onto F
#   validate F [F…]                                 read records back and judge them
#
# WHY ONE EMITTER. Every writer goes through this script and hands it SCALARS. No caller
# ever hand-rolls JSON, because a path containing a quote, a backslash, a tab or a newline is
# exactly the encoder-divergence class that hides silent defects in value encoders (`@tsv` escaping
# backslashes, jq `//` not being python's `or`, `normpath` flattening a leading `//`).
# The encoding here is `jq`'s, not
# ours: nothing in this file writes a `"` into JSON by hand.
#
# WHY THE VALIDATOR IS THE SAME FILTER THE WRITER RUNS. `append` validates the record it just built
# with the identical `jq` program `validate` runs over records read back off disk. A separate
# validator is a second implementation, and two implementations of one contract drift.
# The concrete consequence: it is not possible for this script to write a record its own validator
# rejects, which is what makes the oracle ("schema validation over every record the test suite
# produces") mean something rather than describe two moods of the same optimism.
#
# EXIT CODES, and the one thing this script deliberately does NOT do:
#   0  the record was written / every record validated
#   1  a record is invalid — in `append` NOTHING was written, the file is untouched
#   2  usage error (unknown flag, missing required arg, no jq)
# This script does NOT fail open. "A failed write is never a green" is the CALLER's
# posture (`… || true` at every call site), and it has to be, because the interim authorization guard —
# an `applicability` record must carry a non-empty `reason` — is only a guard if a bad
# record is REFUSED here. A helper that swallowed its own refusal would be the forged-suppression
# hole the ledger exists to close.
#
# Envelope: bash + jq + coreutils. No python3 — this is on the path close-gate.sh calls,
# so it lives inside the gate's dependency envelope by policy.

set -euo pipefail

SPEC_VERSION_DEFAULT="1"

usage() {
  cat >&2 <<'EOF'
usage:
  ledger-append.sh append --file <ledger.jsonl> \
      --run-id <id> --repo-id <id> --phase <token> --stage-id <id> \
      --attempt-id <n> --type <stage_observation|stage_claim|applicability> \
      --status <running|done|failed> --observed <true|false> --observer <name> \
      --started-at <RFC3339-UTC> [--completed-at <RFC3339-UTC>] \
      [--specversion <v>] [--task-id <id>] [--reason <text>] [--retro] \
      [--artifact <path>]… [--attribute <key>=<value>]…

  ledger-append.sh validate <ledger.jsonl> [<ledger.jsonl>…]

Duration is NOT an argument. It is derived by the reader from the two timestamps and is never
stored; `validate` rejects any record carrying a duration key.
EOF
}

die() { printf 'ledger-append: %s\n' "$1" >&2; exit "${2:-2}"; }

need_jq() {
  command -v jq >/dev/null 2>&1 || die "jq not found (this script's only binary dependency)"
}

# ---------------------------------------------------------------------------
# The record contract, as one jq program. Input: one record. Output: an array of
# human-readable violations, empty when the record is valid.
#
# NOT rejected here, on purpose: unknown top-level keys. `specversion` exists precisely so a later
# schema may add fields, and a strict-keys validator would red every old reader against a new
# writer. The one exception is the duration ban below, which is a rule about a field that must
# never exist rather than a rule about fields we happen not to know yet.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# The FILE-level contract. Input: the file's records, slurped. Output: violations.
#
# `attempt_id` must be unique per (run_id, stage_id) and minted as a monotonic
# counter. "Unique" is a rule about ATTEMPTS, not about records — a `running` record and the `done`
# record that finishes the same attempt legitimately share an id: both
# records are kept, and the reader renders that attempt observed. So what is checkable here is the sequence: the
# distinct attempt ids of one (run_id, stage_id), in the order they first appear, must be 1..N with
# no gaps, and the ids must never go backwards.
#
# Both halves are needed and neither implies the other: a gap (1, 3) means an attempt was minted and
# its record lost, and a backwards step (1, 2, 1) means an id was REUSED — the collision that rules out
# last-write-wins, arriving through the back door.
# ---------------------------------------------------------------------------
JQ_FILE_ERRORS='
def firsts: reduce .[] as $a ([]; if any(.[]; . == $a) then . else . + [$a] end);
def file_errors:
  [ .[] | select(type == "object")
        | select((.run_id | type) == "string"
                 and (.stage_id | type) == "string"
                 and (.attempt_id | type) == "number") ]
  | group_by([.run_id, .stage_id])
  | map(
      . as $g
      | ([ $g[].attempt_id ]) as $seq
      | ($seq | firsts) as $f
      | [ (if $f != [range(1; ($f | length) + 1)]
           then "attempt_id sequence for (" + $g[0].run_id + ", " + $g[0].stage_id + ") is "
                + ($f | tostring) + ", expected 1.." + (($f | length) | tostring)
                + " contiguous and in order"
           else empty end),
          (if (all(range(0; ($seq | length) - 1); $seq[.] <= $seq[.+1]) | not)
           then "attempt_id goes backwards for (" + $g[0].run_id + ", " + $g[0].stage_id + "): "
                + ($seq | tostring) + " -- an id was reused, which is the collision that got"
                + " last-write-wins rejected"
           else empty end) ])
  | add // [];
'

JQ_RECORD_ERRORS='
def rfc3339utc: test("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}([.][0-9]+)?Z$");
def nonempty_string: (type == "string") and (. != "");
def blank_string: (type == "string") and (test("^[[:space:]]*$"));

def record_errors:
  if type != "object" then ["record is not a JSON object"]
  else
    . as $r
    # The field name is bound to $f explicitly: inside `has(.)` the `.` would be the OBJECT being
    # tested, not the name being iterated — jq reads the argument in the context of its input.
    | ( ["specversion","run_id","repo_id","phase","stage_id","attempt_id","type","status",
         "observed","observer","started_at","completed_at","artifacts"]
        | map(. as $f | select($r | has($f) | not) | "missing required field: " + $f) )
    + [ (["specversion","run_id","repo_id","phase","stage_id","observer"][] as $f
         | select($r | has($f))
         | select(($r[$f] | nonempty_string) | not)
         | $f + " must be a non-empty string") ]
    + [ if ($r | has("attempt_id")) and (($r.attempt_id | type) != "number"
                                         or ($r.attempt_id | floor) != $r.attempt_id
                                         or $r.attempt_id < 1)
        then "attempt_id must be an integer >= 1" else empty end ]
    + [ if ($r | has("type")) and (["stage_observation","stage_claim","applicability"]
                                   | index($r.type) | not)
        then "type must be one of stage_observation|stage_claim|applicability" else empty end ]
    + [ if ($r | has("status")) and (["running","done","failed"] | index($r.status) | not)
        then "status must be one of running|done|failed" else empty end ]
    + [ if ($r | has("observed")) and (($r.observed | type) != "boolean")
        then "observed must be a boolean" else empty end ]
    + [ if ($r | has("started_at")) and ((($r.started_at | type) == "string" and ($r.started_at | rfc3339utc)) | not)
        then "started_at must be RFC3339 UTC (…Z)" else empty end ]
    + [ if ($r | has("completed_at")) and ($r.completed_at != null)
           and ((($r.completed_at | type) == "string" and ($r.completed_at | rfc3339utc)) | not)
        then "completed_at must be RFC3339 UTC (…Z) or null" else empty end ]

    # status and completed_at are one fact stated twice; a `running` record with an end time is a
    # lie, and a finished record without one loses the timestamp the reader derives duration from.
    + [ if ($r | has("status")) and ($r | has("completed_at"))
           and $r.status == "running" and $r.completed_at != null
        then "a running record must have completed_at: null" else empty end ]
    + [ if ($r | has("status")) and ($r | has("completed_at"))
           and $r.status != "running" and $r.completed_at == null
        then "completed_at is required once status is " + ($r.status // "" | tostring) else empty end ]

    + [ if ($r | has("artifacts")) and (($r.artifacts | type) != "array")
        then "artifacts must be an array" else empty end ]
    + [ if ($r | has("artifacts")) and (($r.artifacts | type) == "array")
        then ($r.artifacts[]
              | select((type != "object") or (keys != ["path"]) or ((.path | nonempty_string) | not))
              | "artifacts[] entries must be exactly {path: <non-empty string>}")
        else empty end ]

    # A DECLARATION IS NOT AN OBSERVATION, and this is the write-time half of a doubled guard --
    # the reader carries the other half. Without it, an `applicability` record
    # with `observed: true` would be accepted here and rendered `observed` by the reader, which is a
    # forged suppression wearing the one word this whole tool exists to make trustworthy. Only a
    # `stage_observation` may set the flag; a `stage_claim` is by definition a self-report, and an
    # `applicability` record is a statement that the stage did not apply, so neither can be the
    # evidence that it happened.
    + [ if ($r | has("type")) and ($r | has("observed"))
           and $r.type != "stage_observation" and $r.observed == true
        then "observed:true is only legal on a stage_observation -- a " + ($r.type | tostring)
             + " record is a declaration, not evidence"
        else empty end ]

    # The interim authorization guard: until the ledger models owner/scope/expiry, a stated reason
    # is the ONLY thing between an authorized suppression and a forged one.
    + [ if ($r | has("type")) and $r.type == "applicability"
           and ((($r.reason? | nonempty_string) and (($r.reason | blank_string) | not)) | not)
        then "an applicability record requires a non-empty reason" else empty end ]

    + [ if ($r | has("attributes")) and (($r.attributes | type) != "object")
        then "attributes must be an object" else empty end ]
    + [ if ($r | has("task_id")) and (($r.task_id | nonempty_string) | not)
        then "task_id must be a non-empty string" else empty end ]
    + [ if ($r | has("retro")) and (($r.retro | type) != "boolean")
        then "retro must be a boolean" else empty end ]

    # Duration is derived, never stored. Banned at the top level AND inside the
    # free bag, because `attributes` is where a stored duration would actually be smuggled in.
    + [ ($r | keys[] | select(test("^duration")) | "duration must never be stored: " + .) ]
    + [ if ($r | has("attributes")) and (($r.attributes | type) == "object")
        then ($r.attributes | keys[] | select(test("^duration"))
              | "duration must never be stored: attributes." + .)
        else empty end ]
  end;
'

# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------
cmd_validate() {
  [ "$#" -ge 1 ] || { usage; exit 2; }
  need_jq
  local failures=0 file line lineno errs msg unparseable
  for file in "$@"; do
    [ -f "$file" ] || { printf '%s: not a file\n' "$file" >&2; failures=$((failures + 1)); continue; }

    # A JSONL file whose last line has no newline is a torn append, not a stylistic choice. Reported
    # rather than silently tolerated — and the read loop below keeps that last line instead of
    # dropping it, so the record itself is judged too.
    # Command substitution strips trailing newlines, so this is empty exactly when the last byte IS
    # a newline. No `wc` involved — a counting tool is one more thing that can be wrong about a
    # one-byte question.
    if [ -s "$file" ] && [ -n "$(tail -c 1 "$file")" ]; then
      printf '%s: file does not end with a newline (torn append?)\n' "$file" >&2
      failures=$((failures + 1))
    fi

    lineno=0
    unparseable=0
    while IFS= read -r line || [ -n "$line" ]; do
      lineno=$((lineno + 1))
      if [ -z "$line" ]; then
        printf '%s:%s: empty line\n' "$file" "$lineno" >&2
        failures=$((failures + 1))
        unparseable=1
        continue
      fi
      # `jq .`, not `jq -e .`: with -e a line holding the literal `false` or `null` exits non-zero
      # and would be reported as unparseable, which is the wrong finding. Those parse fine and are
      # caught below by "record is not a JSON object", which is what is actually wrong with them.
      if ! printf '%s' "$line" | jq . >/dev/null 2>&1; then
        printf '%s:%s: not valid JSON\n' "$file" "$lineno" >&2
        failures=$((failures + 1))
        unparseable=1
        continue
      fi
      errs=$(printf '%s' "$line" | jq -r "$JQ_RECORD_ERRORS"' record_errors | .[]')
      if [ -n "$errs" ]; then
        while IFS= read -r msg; do
          printf '%s:%s: %s\n' "$file" "$lineno" "$msg" >&2
          failures=$((failures + 1))
        done <<EOF
$errs
EOF
      fi
    done < "$file"

    # Pass 2 — the file-level contract. Skipped when a line failed to parse, and SAID so rather
    # than silently omitted: slurping a file with a broken line reports the parse error a second
    # time under a heading about attempt numbering, which names the wrong defect.
    if [ "$unparseable" -ne 0 ]; then
      printf '%s: attempt-sequence check skipped (a line above did not parse)\n' "$file" >&2
    else
      errs=$(jq -s "$JQ_FILE_ERRORS"' file_errors | .[]' -r "$file")
      if [ -n "$errs" ]; then
        while IFS= read -r msg; do
          printf '%s: %s\n' "$file" "$msg" >&2
          failures=$((failures + 1))
        done <<EOF
$errs
EOF
      fi
    fi
  done
  [ "$failures" -eq 0 ] || exit 1
}

# ---------------------------------------------------------------------------
# append
# ---------------------------------------------------------------------------
cmd_append() {
  need_jq

  local file="" run_id="" repo_id="" phase="" stage_id="" attempt_id="" rtype="" status=""
  local observed="" observer="" started_at="" completed_at="" specversion="$SPEC_VERSION_DEFAULT"
  local task_id="" reason="" retro="false"
  local artifacts_json='[]' attributes_json='{}'
  local key value pair

  while [ "$#" -gt 0 ]; do
    case "$1" in
      --file)         [ "$#" -ge 2 ] || die "--file needs a value"; file="$2"; shift 2 ;;
      --run-id)       [ "$#" -ge 2 ] || die "--run-id needs a value"; run_id="$2"; shift 2 ;;
      --repo-id)      [ "$#" -ge 2 ] || die "--repo-id needs a value"; repo_id="$2"; shift 2 ;;
      --phase)        [ "$#" -ge 2 ] || die "--phase needs a value"; phase="$2"; shift 2 ;;
      --stage-id)     [ "$#" -ge 2 ] || die "--stage-id needs a value"; stage_id="$2"; shift 2 ;;
      --attempt-id)   [ "$#" -ge 2 ] || die "--attempt-id needs a value"; attempt_id="$2"; shift 2 ;;
      --type)         [ "$#" -ge 2 ] || die "--type needs a value"; rtype="$2"; shift 2 ;;
      --status)       [ "$#" -ge 2 ] || die "--status needs a value"; status="$2"; shift 2 ;;
      --observed)     [ "$#" -ge 2 ] || die "--observed needs a value"; observed="$2"; shift 2 ;;
      --observer)     [ "$#" -ge 2 ] || die "--observer needs a value"; observer="$2"; shift 2 ;;
      --started-at)   [ "$#" -ge 2 ] || die "--started-at needs a value"; started_at="$2"; shift 2 ;;
      --completed-at) [ "$#" -ge 2 ] || die "--completed-at needs a value"; completed_at="$2"; shift 2 ;;
      --specversion)  [ "$#" -ge 2 ] || die "--specversion needs a value"; specversion="$2"; shift 2 ;;
      --task-id)      [ "$#" -ge 2 ] || die "--task-id needs a value"; task_id="$2"; shift 2 ;;
      --reason)       [ "$#" -ge 2 ] || die "--reason needs a value"; reason="$2"; shift 2 ;;
      --retro)        retro="true"; shift ;;
      --artifact)
        [ "$#" -ge 2 ] || die "--artifact needs a value"
        # One jq call per path, the value carried as an OPTION value rather than a positional
        # argument: a path that begins with `-` is then never a candidate flag for anything.
        artifacts_json=$(printf '%s' "$artifacts_json" | jq -c --arg p "$2" '. + [{path: $p}]')
        shift 2 ;;
      --attribute)
        [ "$#" -ge 2 ] || die "--attribute needs a value"
        case "$2" in
          *=*) ;;
          *) die "--attribute expects <key>=<value>, got: $2" ;;
        esac
        key="${2%%=*}"; value="${2#*=}"
        [ -n "$key" ] || die "--attribute key must not be empty"
        attributes_json=$(printf '%s' "$attributes_json" |
          jq -c --arg k "$key" --arg v "$value" '. + {($k): $v}')
        shift 2 ;;
      -h|--help) usage; exit 0 ;;
      *) die "unknown argument: $1" ;;
    esac
  done

  [ -n "$file" ] || die "--file is required"
  for pair in "run-id:$run_id" "repo-id:$repo_id" "phase:$phase" "stage-id:$stage_id" \
              "attempt-id:$attempt_id" "type:$rtype" "status:$status" "observed:$observed" \
              "observer:$observer" "started-at:$started_at"; do
    [ -n "${pair#*:}" ] || die "--${pair%%:*} is required"
  done

  # `--argjson` dies with jq's own message on a non-literal; these two checks exist so the caller
  # is told which FLAG was wrong instead of reading a jq parse error.
  case "$observed" in true|false) ;; *) die "--observed must be true or false" ;; esac
  case "$attempt_id" in ''|*[!0-9]*) die "--attempt-id must be a positive integer" ;; esac

  local record
  record=$(jq -cn \
    --arg specversion "$specversion" \
    --arg run_id "$run_id" \
    --arg repo_id "$repo_id" \
    --arg phase "$phase" \
    --arg stage_id "$stage_id" \
    --argjson attempt_id "$attempt_id" \
    --arg type "$rtype" \
    --arg status "$status" \
    --argjson observed "$observed" \
    --arg observer "$observer" \
    --arg started_at "$started_at" \
    --arg completed_at "$completed_at" \
    --argjson artifacts "$artifacts_json" \
    --arg task_id "$task_id" \
    --arg reason "$reason" \
    --argjson retro "$retro" \
    --argjson attributes "$attributes_json" \
    '{
       specversion: $specversion,
       run_id: $run_id,
       repo_id: $repo_id,
       phase: $phase,
       stage_id: $stage_id,
       attempt_id: $attempt_id,
       type: $type,
       status: $status,
       observed: $observed,
       observer: $observer,
       started_at: $started_at,
       completed_at: (if $completed_at == "" then null else $completed_at end),
       artifacts: $artifacts
     }
     + (if $task_id    == ""    then {} else {task_id: $task_id}       end)
     + (if $reason     == ""    then {} else {reason: $reason}         end)
     + (if $retro      == false then {} else {retro: $retro}           end)
     + (if ($attributes | length) == 0 then {} else {attributes: $attributes} end)')

  local errs
  errs=$(printf '%s' "$record" | jq -r "$JQ_RECORD_ERRORS"' record_errors | .[]')
  if [ -n "$errs" ]; then
    printf 'ledger-append: refusing to write an invalid record; nothing was appended to %s\n' "$file" >&2
    printf '%s\n' "$errs" | while IFS= read -r msg; do printf '  %s\n' "$msg" >&2; done
    exit 1
  fi

  mkdir -p "$(dirname "$file")"
  # A single-line `>>` append by the file's sole owner. No read-modify-write, no
  # temp-then-rename: appending to a multi-record file that way silently LOSES a record under two
  # writers, which is worse than the torn record it defends against.
  printf '%s\n' "$record" >> "$file"
}

main() {
  [ "$#" -ge 1 ] || { usage; exit 2; }
  local mode="$1"; shift
  case "$mode" in
    append)   cmd_append "$@" ;;
    validate) cmd_validate "$@" ;;
    -h|--help) usage; exit 0 ;;
    *) usage; exit 2 ;;
  esac
}

main "$@"
