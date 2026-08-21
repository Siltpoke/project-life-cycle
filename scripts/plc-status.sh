#!/usr/bin/env bash
# The reader. Renders the ledger; never writes it.
#
# Modes:
#   (default)       the current run, one row per registry stage
#   --run <id>      one run's timeline: stage, state, derived duration, artifacts
#   --all           the conformance matrix over every run the index knows
#
# THE ROW COUNT IS THE REGISTRY'S, NOT THE RECORDS'. Every mode walks the registry and
# asks what the records say about each stage -- never the other way round. A stage nobody mentioned
# still produces a row, and that row says `missing`. Enumerating records would make the one stage
# nobody touched the one stage that does not appear, which is the exact failure the ledger exists
# to close.
#
# STATES ARE COMPUTED HERE, NEVER STORED. Five of them:
#
#   observed                    a record says observed:true
#   claimed                     records exist but none of them observed anything
#   missing                     the stage is in the registry and nothing mentions it
#   not-applicable (unverified) an applicability record with a reason says it does not apply
#   unknown (retro)             a pre-ledger run, for a stage whose evidence cannot exist
#
# RESOLUTION RULES, each of which is a decision rather than an implementation detail:
#
#   * a MISSING `observed` field is `observed:false`. A record without it renders claimed, never
#     observed. That is the fail-safe direction and it is what makes the mutant testable.
#   * a record whose `specversion` this reader does not know renders CLAIMED and is REPORTED. It is
#     never dropped -- dropping would silently become `missing` -- and never trusted as observed.
#     Dispatch is PER RECORD, never per file: a ledger can span a schema upgrade mid-run.
#   * `claimed` then `observed` for one attempt renders OBSERVED, and both records stay in the
#     timeline. Evidence upgrades; it does not overwrite.
#   * an applicability record with no non-empty `reason` NEVER renders as a suppression. Until the ledger
#     models owner/scope/expiry, a stated reason is the only thing between an authorized suppression
#     and a forged one, so one without it is just another record -- which makes the stage claimed.
#   * evidence BEATS declaration. A stage that was both observed and declared not-applicable
#     renders observed, and the conflict is reported rather than resolved silently.
#
# WHY available_from IS NOT CONSULTED FOR RETRO RUNS, said plainly because it was introduced for
# exactly them. A retro record's timestamps are when the SCAN ran, not when the stage did (see ledger-scan.sh), so
# comparing them against a stage's availability date would ask a question about the scanner's clock.
# The honest signal for "this evidence could never have survived" is the registry's own
# `retro_evidence: null`, and that is what produces `unknown (retro)`. The intended effect is
# delivered -- `cross_family_review` on an old phase renders `unknown (retro)`, not `missing` -- by
# a mechanism that does not depend on a timestamp nobody can supply. `available_from` therefore
# means something only for live runs today, and that is a limitation, not a feature.
#
# jq IS THE ONE BINARY DEPENDENCY. Absent, this exits non-zero with a named error and
# prints NO matrix. A wrong conformance matrix is worse than no matrix -- that is the whole thesis
# of the ledger -- so there is no degraded fallback.
#
# Envelope: bash + jq + coreutils. No python3.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# The schema versions this reader understands. A record outside this set is reported, not guessed.
KNOWN_SPECVERSIONS='["1"]'

die() { printf 'plc-status: %s\n' "$1" >&2; exit "${2:-2}"; }

usage() {
  cat >&2 <<'EOF'
usage:
  plc-status.sh [--run <run_id>] [--all]
                [--registry <file>] [--ledger-dir <dir>] [--index-dir <dir>] [--repo-root <dir>]
EOF
}

# --- the resolver, as one jq program ------------------------------------------------------------
#
# Input: the ledger's records. Arguments: the registry, the run being rendered, and whether the
# run is retro. Output: one line per REGISTRY stage -- `stage_id \t state \t note`.
#
# THREE PROVENANCE RULES. A reader can break
# each of them in a way shape-level tests cannot see: every one of them
# PRESERVES THE SHAPE of the output while changing what it says is true.
#
#  1. A RECORD BELONGS TO A RUN. Records are filtered on `run_id`, not on `stage_id` alone. The
#     reader picks the file by run id and used to trust everything inside it, so a record carrying
#     another run`s id rendered as this run`s evidence. One writer per file makes that unlikely; it
#     does not make it FALSE, and "unlikely" is not what a conformance matrix is for. A foreign
#     record is REPORTED, never silently used and never silently dropped.
#
#  2. ONLY AN OBSERVATION IS EVIDENCE. `observed` requires `type == "stage_observation"`. A
#     `stage_claim` or an `applicability` record carrying `observed: true` is a DECLARATION with a
#     flag set, and it used to render `observed` -- which is a forged suppression wearing the one
#     word this whole tool exists to make trustworthy. Reported, and rendered as what it is.
#
#  3. A LINE THAT DOES NOT PARSE IS STILL A LINE. See `resolve_run` below.
# THE RULES, WRITTEN ONCE. The failure class here is a rule about the
# ledger applied by one consumer of it and not another.
# It recurs because there are FOUR consumers of these records in this file (the state
# resolver, the retro probe, the timeline, the summary counter) and each had its own copy of the
# filters. Fixing instances could never finish that; a rule that exists in one place can only be
# forgotten in one place.
#
# Every consumer below now starts from this prelude and, where it needs run-scoped records, from
# `for_run`. Adding a rule means editing one definition.
JQ_RULES='
def known: IN($known[]);
def parseable: (type == "object") and ((.__unparseable__ // false) | not);
def usable: parseable and ((.specversion // "") | known);
def observed_flag: (.observed // false) == true;
def mine: (.run_id // null) == $run;
def evidence: usable and (.type == "stage_observation") and observed_flag;
def for_run: map(select(parseable) | select(mine));
'

JQ_RESOLVE="$JQ_RULES"'

# A record naming a stage the registry does not have is REPORTED at the run level. The registry is
# the denominator by design, so such a record produces no row -- and "produces no row"
# was indistinguishable from "is not on disk", which is a silent drop.
($registry.stages | map(.stage_id)) as $declared
| ($records | map(select(parseable) | select(mine))
            | map(select((.stage_id // "") | IN($declared[]) | not))) as $unknown_stage
| $registry.stages
| map(. as $s
  | ($records | map(select(parseable)) | map(select(.stage_id == $s.stage_id))) as $named
  | ($named | map(select(mine | not))) as $foreign
  | ($named | map(select(mine))) as $rs
  | ($rs | map(select(usable | not))) as $unknown_version
  | ($rs | map(select(usable))) as $ok
  | ($rs | map(select(evidence))) as $seen
  | ($ok | map(select(.type != "stage_observation") | select(observed_flag))) as $mislabelled
  | ($ok | map(select(.type == "applicability")
                | select(((.reason // "") | test("^[[:space:]]*$")) | not))) as $suppressed
  | ($ok | map(select(.type == "applicability")
                | select(((.reason // "") | test("^[[:space:]]*$"))))) as $unreasoned
  | (if ($seen | length) > 0 then "observed"
     elif ($suppressed | length) > 0 then "not-applicable (unverified)"
     elif ($rs | length) > 0 then "claimed"
     elif $retro and ($s.retro_evidence == null) then "unknown (retro)"
     else "missing" end) as $state
  | [ (if ($unknown_version | length) > 0
       then "REPORTED: " + (($unknown_version | length) | tostring)
            + " record(s) carry a specversion this reader does not know ("
            + (($unknown_version | map(.specversion // "<absent>") | unique | join(", ")))
            + ") -- rendered claimed, never dropped"
       else empty end),
      (if ($seen | length) > 0 and ($suppressed | length) > 0
       then "REPORTED: declared not-applicable AND observed -- evidence wins, the conflict does not"
       else empty end),
      (if ($unreasoned | length) > 0
       then "REPORTED: " + (($unreasoned | length) | tostring)
            + " applicability record(s) carry no reason -- not treated as a suppression"
       else empty end),
      (if $state == "observed" and (($ok | map(select(observed_flag | not)) | length) > 0)
       then "upgraded from a claim, which is still in the timeline"
       else empty end),
      (if ($mislabelled | length) > 0
       then "REPORTED: " + (($mislabelled | length) | tostring)
            + " record(s) set observed:true on a non-observation type ("
            + (($mislabelled | map(.type // "<absent>") | unique | join(", ")))
            + ") -- a declaration is not evidence, so it is NOT treated as observed"
       else empty end),
      (if ($s.stage_id == ($declared | first)) and (($unknown_stage | length) > 0)
       then "REPORTED (run-level): " + (($unknown_stage | length) | tostring)
            + " record(s) name a stage this registry does not declare ("
            + (($unknown_stage | map(.stage_id // "<absent>") | unique | join(", ")))
            + ") -- they produce no row, which is why this says so"
       else empty end),
      (if $state == "missing" and (($s.mandated_when // "") != "")
       then "registry says this stage is mandated " + $s.mandated_when
            + " -- nothing evaluates that condition yet, so `missing` here means NOT SEEN, not"
            + " necessarily SKIPPED"
       else empty end),
      (if $state == "unknown (retro)" and (($s.retro_reason // "") == "not-implemented")
       then "recovery for this stage is possible in principle and NOT IMPLEMENTED -- unlike the"
            + " other unknown (retro) rows, a person can still check this one by hand"
       else empty end),
      (if ($foreign | length) > 0
       then "REPORTED: " + (($foreign | length) | tostring)
            + " record(s) in this file name another run ("
            + (($foreign | map(.run_id // "<absent>") | unique | join(", ")))
            + ") -- not counted here, and not discarded"
       else empty end)
    ] as $notes
  | [$s.stage_id, $state, ($notes | join(" · "))] | @tsv)
| .[]
'

# PROVENANCE RULE 3: A LINE THAT DOES NOT PARSE IS STILL A LINE.
#
# The obvious form is `jq -s '.' "$ledger" || printf '[]'`, and that fallback is the worst defect
# a reader can have. `jq -s` fails on the WHOLE FILE if any single line is malformed, so one torn append
# discards every good record with it and the reader renders every stage `missing` -- announcing
# that a run did none of the process, on the strength of a truncated write. Measured: the same
# record renders `observed` intact and `missing` with its last brace removed.
#
# The reader's own rule forbids exactly this: a record that fails validation renders claimed
# and is reported; it is never dropped, because dropping would silently become `missing`.
# Parsing per LINE means a bad line costs only itself.
#
# WHAT A BAD LINE CANNOT DO, said plainly rather than papered over: it cannot be attributed to a
# stage, because the thing that would name the stage is the part that did not parse. So it is
# reported at the RUN level and counted, and it is deliberately NOT allowed to flip any stage's
# state -- inventing a stage for it would be a second lie told to cover the first.
parse_records() {
  local ledger="$1"
  # ABSENT and UNREADABLE are different facts, and only one of them is empty. A run with no ledger
  # legitimately has no records; a ledger that EXISTS and cannot be read is a question this reader
  # cannot answer, and answering it anyway rendered every stage `missing` -- a run reported as
  # having done none of the process because of a permission bit. The reader is the one component
  # in this system that is never fail-open: a wrong matrix is worse than no matrix.
  if [ ! -e "$ledger" ]; then
    printf '[]'
    return 0
  fi
  if [ ! -r "$ledger" ]; then
    die "ledger exists but cannot be read: $ledger -- refusing to render a matrix that would report this run as having done nothing" 4
  fi
  if [ ! -s "$ledger" ]; then
    printf '[]'
    return 0
  fi
  # A BLANK LINE IS AN INVALID JSONL LINE, not nothing. `ledger-append.sh validate` already
  # reported it as one; the reader dropped it, so the two disagreed about the same file -- the same
  # uneven-rule class, between two programs instead of two functions. The final newline every
  # correct file ends with is the one exception, and it is stripped before the split rather than
  # filtered after, so a genuinely empty line in the middle survives to be counted.
  jq -R -s 'sub("\n$"; "") | if . == "" then [] else split("\n") end
            | map(try fromjson catch {"__unparseable__": true})' "$ledger" 2>/dev/null ||
    die "cannot read $ledger -- refusing to render a matrix built from nothing" 4
}

unparseable_count() {
  parse_records "$1" | jq '[.[] | select(type == "object") | select(.__unparseable__ == true)] | length'
}

# Called BEFORE any output, and outside a command substitution. Both matter: `die` inside `$( )`
# exits only the subshell, so the first version of this check let the run header (7 bytes) reach
# the terminal before the refusal landed. "Prints no matrix" has to mean prints nothing.
require_readable_ledger() {
  local ledger="$1"
  [ -e "$ledger" ] || return 0
  [ -r "$ledger" ] || die "ledger exists but cannot be read: $ledger -- refusing to render a matrix that would report this run as having done nothing" 4
  return 0
}

resolve_run() {
  local registry="$1" ledger="$2" retro="$3" run="$4"
  jq -r -n \
    --argjson registry "$(cat "$registry")" \
    --argjson records "$(parse_records "$ledger")" \
    --argjson known "$KNOWN_SPECVERSIONS" \
    --argjson retro "$retro" \
    --arg run "$run" \
    "$JQ_RESOLVE"
}

is_retro() {
  # Goes through parse_records for the same reason the resolver does: `jq -s` on the raw file dies
  # on one bad line, and a retro run whose ledger has a torn append would have silently stopped
  # being retro -- turning every unrecoverable stage from `unknown (retro)` into `missing`, which
  # is the accusing direction.
  #
  # AND IT FILTERS ON THE RUN. Without that,
  # the resolver would know that a record belongs to
  # a run while THIS function kept asking "does any object in the file say retro", so a single
  # foreign record would flip the whole run to retro and every unrecoverable stage would render
  # `unknown (retro)` instead of `missing` -- invisibly,
  # because the matrix would REPORT the record as foreign and use it.
  # AND IT APPLIES THE KNOWN-SPECVERSION RULE.
  # The row for such a record says "carries a specversion this reader
  # does not know -- rendered claimed", and without this rule the run header would accept `retro` from
  # that same record, putting every unrecoverable stage into `unknown (retro)` on the authority of
  # something the reader had just declared uninterpretable. A record this reader cannot read cannot
  # be the record that establishes what kind of run this is.
  local ledger="$1" run="$2"
  parse_records "$ledger" |
    jq --arg run "$run" --argjson known "$KNOWN_SPECVERSIONS" \
      "$JQ_RULES"'
       if (for_run | any(.[]; usable and (.retro == true))) then true else false end' 2>/dev/null ||
    printf 'false'
}

# --- rendering ----------------------------------------------------------------------------------
glyph_for() {
  case "$1" in
    observed)                      printf '+' ;;
    claimed)                       printf '?' ;;
    missing)                       printf '-' ;;
    'not-applicable (unverified)') printf '~' ;;
    'unknown (retro)')             printf '.' ;;
    *)                             printf ' ' ;;
  esac
}

render_run() {
  local registry="$1" ledger="$2" run_id="$3" retro
  require_readable_ledger "$ledger"
  retro="$(is_retro "$ledger" "$run_id")"
  printf 'run %s%s\n' "$run_id" "$( [ "$retro" = true ] && printf '  (retro: reconstructed from disk, not observed live)' || true)"
  local torn; torn="$(unparseable_count "$ledger")"
  if [ "${torn:-0}" -gt 0 ]; then
    # Loud, at the run level, and NOT attributed to a stage -- the part that would have named the
    # stage is the part that did not parse.
    printf '  !! %s line(s) in this ledger do not parse. They are counted here and cannot be\n' "$torn"
    printf '     attributed to a stage, so no row below reflects them. Run:\n'
    printf '       /bin/bash scripts/ledger-append.sh validate %s\n' "$ledger"
  fi
  # The separator is US (0x1f), written OCTAL because BSD `tr` does not understand `\x1f` -- it
  # reads that as a literal `x` and every rendered row came out as `stagexstatex`. And it is US
  # rather than a tab because tab is IFS whitespace: `IFS=$'\t' read` collapses runs of tabs, so an
  # empty note column would shift the row apart.
  local stage state note
  while IFS=$'\037' read -r stage state note; do
    [ -n "$stage" ] || continue
    printf '  %s %-22s %-28s %s\n' "$(glyph_for "$state")" "$stage" "$state" "$note"
  done <<EOF
$(resolve_run "$registry" "$ledger" "$retro" "$run_id" | tr '\t' '\037')
EOF
}

# One line per run: the five counts and the total. The total is the row-count rule on every line -- it must
# equal the number of stages in the registry, for every run, always.
render_summary() {
  local registry="$1" ledger="$2" run_id="$3" retro
  require_readable_ledger "$ledger"
  retro="$(is_retro "$ledger" "$run_id")"
  local torn; torn="$(unparseable_count "$ledger")"
  resolve_run "$registry" "$ledger" "$retro" "$run_id" |
    awk -F'\t' -v run="$run_id" -v torn="${torn:-0}" '
      # The notes column is the third field. `--all` used to discard it, so a record the `--run`
      # view REPORTS was invisible in the summary -- the summary being the fourth consumer of the
      # same resolved rows, and the one most likely to be read on its own.
      { n[$2]++; total++; if ($3 != "") reported++ }
      END {
        printf "%-52s observed=%d claimed=%d missing=%d n/a=%d unknown=%d total=%d%s\n",
          run, n["observed"], n["claimed"], n["missing"],
          n["not-applicable (unverified)"], n["unknown (retro)"], total,
          (torn > 0 ? "  !! " torn " unparseable line(s)" : "")   \
            (reported > 0 ? "  !! " reported " row(s) carry a report -- see --run " run : "")
      }'
}

render_timeline() {
  local ledger="$1" run_id="$2"
  require_readable_ledger "$ledger"
  printf 'timeline %s\n' "$run_id"
  [ -f "$ledger" ] || { printf '  (no ledger file)\n'; return 0; }
  # Duration is DERIVED here and stored nowhere. A running record has no end time, so it
  # has no duration -- rendered as `-`, never as zero, which would read as "it took no time".
  # Through parse_records, like everything else that reads this file: a plain `jq -r` over the raw
  # ledger dies on one malformed line, which is how the torn-ledger fixture first failed here after
  # the resolver had already been fixed. The timeline shows the bad line as a row of its own rather
  # than hiding it -- it is the one place a reader can actually see WHERE the file broke.
  # TWO more rules, both about the timeline:
  #
  #  * it filters on the run. The matrix was taught that a record belongs to a run; the timeline was
  #    not, so the same render said "N record(s) name another run -- not counted here" in the matrix
  #    and then printed that record as this run's event three lines later. One renderer contradicting
  #    the other is worse than either being wrong alone.
  #  * the unparseable marker is REACHABLE. It was converted to a string and then dropped by a
  #    `select(type == "object")` on the very next line -- a guard that could not fire, in the code
  #    written to fix guards that could not fire. Its comment claimed this was "the one place a
  #    reader can actually see WHERE the file broke", which was a claim with no mechanism at all.
  parse_records "$ledger" | jq -r --arg run "$run_id" --argjson known "$KNOWN_SPECVERSIONS" \
    "$JQ_RULES"'
    .[]
    | select(type == "object")
    | if ((.__unparseable__ // false))
      then "  <unparseable line -- run: /bin/bash scripts/ledger-append.sh validate>"
      elif (mine | not)
      then empty
      elif (usable | not)
      then "  <record with an unknown specversion (" + ((.specversion // "<absent>") | tostring)
           + ") -- shown, not interpreted>"
      else
        . as $r
    | (if (.completed_at // null) == null then "-"
       else ((.completed_at | fromdateiso8601) - (.started_at | fromdateiso8601) | tostring) + "s"
       end) as $dur
    | "  " + (.started_at) + "  " + (.stage_id) + "  attempt " + (.attempt_id | tostring)
      + "  " + (.status) + "  " + (.type // "<no type>")
      + "  observed=" + ((.observed // false) | tostring)
      + (if evidence then "" else "  (NOT evidence)" end)
      + "  by " + (.observer // "?") + "  " + $dur
      + (if ((.artifacts // []) | length) > 0
         then "  [" + ((.artifacts | map(.path) | join(", "))) + "]" else "" end)
      end
  ' | sort
}

main() {
  local mode=run_current run_id="" registry="" ledger_dir="" repo_root=""
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --run)        [ "$#" -ge 2 ] || die "--run needs a value"; run_id="$2"; mode=run_named; shift 2 ;;
      --all)        mode=all; shift ;;
      --registry)   [ "$#" -ge 2 ] || die "--registry needs a value";   registry="$2";   shift 2 ;;
      --ledger-dir) [ "$#" -ge 2 ] || die "--ledger-dir needs a value"; ledger_dir="$2"; shift 2 ;;
      # ACCEPTED AND IGNORED IS WORSE THAN REFUSED. This flag was parsed and never read, so
      # `--all --index-dir <somewhere>` silently rendered the LOCAL ledger directory instead --
      # a reader could ask for one population and be shown another with no sign of it. The global
      # index has its own reader; say so rather than pretend to honour the flag.
      --index-dir)  die "--index-dir is not supported here: --all reads the per-repo ledger directory (--ledger-dir). The global discovery index has its own reader: /bin/bash scripts/ledger-index.sh list" ;;
      --repo-root)  [ "$#" -ge 2 ] || die "--repo-root needs a value";  repo_root="$2";  shift 2 ;;
      -h|--help)    usage; exit 0 ;;
      *) die "unknown argument: $1" ;;
    esac
  done

  # jq is required. Checked before ANY output, so there is no path on which a partial matrix reaches the
  # terminal and then a failure message follows it.
  command -v jq >/dev/null 2>&1 ||
    die "jq not found -- it is this reader's one binary dependency, and a wrong conformance matrix is worse than no matrix, so nothing is printed" 3

  [ -n "$repo_root" ] || repo_root="$(git -C "$HERE" rev-parse --show-toplevel 2>/dev/null || printf '%s' "$PWD")"
  [ -n "$registry" ] || registry="$repo_root/.claude/stage-registry.json"
  [ -n "$ledger_dir" ] || ledger_dir="$repo_root/.claude/.gate-runs/ledger"
  [ -r "$registry" ] || die "registry is unreadable: $registry"

  case "$mode" in
    run_named)
      render_run "$registry" "$ledger_dir/$run_id.jsonl" "$run_id"
      printf '\n'
      render_timeline "$ledger_dir/$run_id.jsonl" "$run_id"
      ;;
    run_current)
      local current="${PLC_RUN_ID:-}"
      if [ -z "$current" ]; then
        # Newest by mtime. Stated rather than silent: there is no "current run" marker on disk, and
        # inventing one here would be a second source of truth about identity (that is ledger-run.sh's).
        current="$(ls -t "$ledger_dir"/*.jsonl 2>/dev/null | head -1 || true)"
        [ -n "$current" ] || die "no run to show: PLC_RUN_ID is unset and $ledger_dir holds no ledger" 1
        current="$(basename "$current" .jsonl)"
        # Disclosed on STDOUT, not only in the command's documentation. The rendered output is what
        # a reader is shown verbatim, and "newest by mtime" looked exactly like "the current run".
        printf 'note: PLC_RUN_ID is unset, so this is the NEWEST ledger by mtime, not a run anyone\n'
        printf '      declared current. Pass --run <id> to be sure which run you are reading.\n'
      fi
      render_run "$registry" "$ledger_dir/$current.jsonl" "$current"
      ;;
    all)
      local f n=0
      for f in "$ledger_dir"/*.jsonl; do
        [ -f "$f" ] || continue
        render_summary "$registry" "$f" "$(basename "$f" .jsonl)"
        n=$((n + 1))
      done
      [ "$n" -gt 0 ] || printf 'no runs found in %s\n' "$ledger_dir"
      ;;
  esac
}

main "$@"
