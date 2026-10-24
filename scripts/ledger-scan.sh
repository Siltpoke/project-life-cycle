#!/usr/bin/env bash
# The retroactive scanner. Disk evidence for phases that predate the ledger.
#
# Modes:
#   runs --roadmap <path>                          print the enumerated run slugs, one per line
#   scan --roadmap R --out-dir O [options]         write one retro ledger file per run
#
# THE RUN POPULATION IS ROADMAP-DRIVEN, AND THAT IS LOAD-BEARING.
# Runs are enumerated from the phase rows in docs/ROADMAP.md, and only then is each registry stage
# looked for. The tempting alternative -- walk the qa-log/spec/plan filenames and call each one a
# run -- can only ever find phases that PRODUCED ARTIFACTS. A phase that produced none would
# silently not exist, which is precisely the blindness the ledger exists to fix: the
# question is "did phase X run the process", and a phase that ran none of it must still be a row.
#
# MATCHING IS ANCHORED, NEVER A BARE SUBSTRING. The false positive it prevents: when a phase's
# only occurrence anywhere in the qa-log corpus is a CROSS-REFERENCE inside
# another phase's fragment, a content search scores it as having a qa-log it never had. Two anchors,
# and they point in opposite directions on purpose:
#
#   * a FILENAME carries the slug plus an optional suffix, so `YYYY-MM-DD-...-phase-<slug>-design.md`
#     matches when the extracted name IS the slug or begins with `<slug>-`;
#   * an ARCHIVE HEADING carries the slug or a shorter prefix of it (`# Journal — phase `p7``
#     against the ROADMAP's `p7-retry-backoff`), so it matches when the SLUG is the
#     extracted name or begins with `<name>-`.
#
# Getting these two backwards is the whole defect class, which is why they are separate functions
# with separate tests rather than one clever comparison.
#
# WHAT A RETRO RECORD'S TIMESTAMPS MEAN, said plainly because they are easy to misread: they are
# when the SCAN observed the evidence, not when the stage ran. The scanner cannot know the latter --
# a filename's date is the artifact's date, not the stage's -- and inventing one would put a lie
# under a field the reader derives duration from. `retro: true` is what tells the reader not to read
# a duration out of these.
#
# EVERY RECORD GOES THROUGH ledger-append.sh. No JSON is written here.
#
# Envelope: bash + jq + git + coreutils. No python3.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# The emitter is an ARGUMENT (`--emitter`), never an environment variable. This was
# `${PLC_LEDGER_APPEND:-...}` until it became clear what that buys a caller:
# `PLC_LEDGER_APPEND=/dev/null` made the scan print "wrote 1 records" while writing zero bytes.
# The rule is "an environment variable is not a capability".
# Tests pass the path explicitly; nothing ambient can relocate the writer.
APPEND_DEFAULT="$HERE/ledger-append.sh"

# The ONE reader for the drain's fragment sentinel, shared with the wrap-up gate: a file here, an
# embedded copy there, held to the same bytes by
# scripts/invariants/one-fragment-sentinel-reader.sh. The gate is a single drop-in script and
# cannot reach a sibling file; this scanner runs in place and can. Writing a second matcher for
# the same sentinel is exactly the drift that guard refuses.
#
# It is an ARGUMENT (`--sentinel`) with this as the default, for the reason written above the
# emitter and then promptly re-earned: a mutant copy of this script lives under a temp directory,
# so a reader resolved beside the script is NOT THERE, and a mutant of the matchers dies of a
# missing file and is scored dead for a reason unrelated to what it mutated. Measured --
# mutant rows failed exactly that way before this line existed. Not an environment variable, for
# the same reason as the emitter: an environment variable is not a capability.
SENTINEL_DEFAULT="$HERE/lib/fragment-sentinel.awk"

die() { printf 'ledger-scan: %s\n' "$1" >&2; exit "${2:-2}"; }

usage() {
  cat >&2 <<'EOF'
usage:
  ledger-scan.sh runs --roadmap <docs/ROADMAP.md>
  ledger-scan.sh scan --roadmap <docs/ROADMAP.md> --out-dir <dir>
                      [--registry <.claude/stage-registry.json>] [--repo-root <dir>]
                      [--repo-id <id>] [--now <RFC3339-UTC>]
                      [--emitter <scripts/ledger-append.sh>]
                      [--sentinel <scripts/lib/fragment-sentinel.awk>]
EOF
}

# --- run enumeration --------------------------------------------------------------------------
#
# The annotation this reads is `phase `<slug>`` -- ASCII, and deliberately so. A ROADMAP
# may state the close-gate PHASE token in any language's prose; matching on that
# would encode
# one repo's dialect into a script other repos are meant to run.
#
# COLLAPSING: the ROADMAP names some phases twice at different granularity (`p16` in one row and
# `p16-cache-namespace` in another). A slug that is a strict `-`-delimited prefix of another is
# folded into the longer one, so those are one run rather than two. The `-` is required: `p4` does
# NOT collapse into `p46`, and `p9-p8` does not collapse into `p9-p21-atomic-acquire`.
enumerate_runs() {
  local roadmap="$1" all short long keep
  [ -r "$roadmap" ] || die "roadmap is unreadable: $roadmap"
  # `|| true` is load-bearing, and it was measured. `grep` exits 1 when it matches nothing; under
  # `set -o pipefail` that becomes the substitution's status, and under `set -e` the script dies
  # RIGHT HERE -- one line before the guard below, which therefore never ran and never printed.
  # The guard against a vacuous population was itself unreachable:
  # a check that cannot fire looks exactly like a check that passed.
  all="$(grep -oE 'phase `[a-z0-9][a-z0-9._-]*`' "$roadmap" | sed 's/^phase `//; s/`$//' | sort -u || true)"
  [ -n "$all" ] || die "no phase annotations found in $roadmap -- the enumeration source produced an EMPTY population, which would make every downstream assertion vacuously true"
  keep=""
  while IFS= read -r short; do
    [ -n "$short" ] || continue
    local folded=0
    while IFS= read -r long; do
      [ -n "$long" ] || continue
      [ "$long" = "$short" ] && continue
      case "$long" in "$short"-*) folded=1; break ;; esac
    done <<EOF
$all
EOF
    [ "$folded" -eq 1 ] || keep="$keep$short"$'\n'
  done <<EOF
$all
EOF
  printf '%s' "$keep"
}

# --- the two anchored matchers ------------------------------------------------------------------
# A name extracted from a FILENAME may carry a suffix the slug does not.
file_name_matches() {
  case "$1" in "$2"|"$2"-*) return 0 ;; esac
  return 1
}
# A name extracted from a HEADING may be a prefix of the slug.
heading_name_matches() {
  case "$2" in "$1"|"$1"-*) return 0 ;; esac
  return 1
}

# Print every file under the given roots whose extracted phase name matches the slug.
find_phase_files() {
  local slug="$1" suffix="$2" repo_root="$3"; shift 3
  local root f base cand
  for root in "$@"; do
    # The root itself may be a glob (docs/archive/.pre-images/*/files/docs/qa-log.d). Unmatched
    # globs stay literal under bash, so the -d test below is what filters them out.
    for expanded in $repo_root/$root; do
      [ -d "$expanded" ] || continue
      for f in "$expanded"/*.md; do
        [ -f "$f" ] || continue
        base="$(basename "$f")"
        case "$base" in *phase-*) cand="${base##*phase-}" ;; *) continue ;; esac
        if [ -n "$suffix" ]; then
          case "$cand" in *"$suffix") cand="${cand%"$suffix"}" ;; *) continue ;; esac
        else
          cand="${cand%.md}"
        fi
        file_name_matches "$cand" "$slug" && printf '%s\n' "${f#"$repo_root"/}"
      done
    done
  done
  # A finder that found nothing is not an error, and under `set -e` it would be: the last
  # `file_name_matches` returns 1, that becomes the function's status, and `found="$(...)"` then
  # kills the script. It did — silently, after one run — which is why this line is here and not a
  # `|| true` at the call site: the fact "nothing matched" belongs to the finder, not the caller.
  return 0
}

# Print every archive file carrying a heading that names this phase.
#
# Both heading forms are accepted:
# `# Journal — phase `p7`` (backticked) and `# Journal fragment — phase p8-full-rebaseline`
# (bare, name ends at the first character outside [a-z0-9._-]).
find_archive_headings() {
  local slug="$1" repo_root="$2"; shift 2
  local root f name
  for root in "$@"; do
    for expanded in $repo_root/$root; do
      [ -d "$expanded" ] || continue
      for f in "$expanded"/*.md; do
        [ -f "$f" ] || continue
        while IFS= read -r name; do
          [ -n "$name" ] || continue
          if heading_name_matches "$name" "$slug"; then
            printf '%s\n' "${f#"$repo_root"/}"
            break
          fi
        done < <(grep -oE '^#+ .*phase [`]?[a-z0-9][a-z0-9._-]*' "$f" 2>/dev/null |
                 sed 's/.*phase [`]*//')
      done
    done
  done
  return 0
}

# --- fragment markers: one read of each archive for the WHOLE scan ------------------------------
#
# ROOTS ARE FILES for this kind, not directories, because that is what the drain writes into: one
# compiled monolith, one cold archive file, and a directory of roll-over segments reached by a
# glob. The two finders above walk `<dir>/*.md`; this pair expands each root and takes what is a
# regular file.
#
# WHY AN INDEX AND NOT A READ PER RUN, AND THE REASON IS NOT SPEED. The per-run shape was written
# first, and the arithmetic looked damning -- one awk pass per declared file per run, over
# archives that do not change during a scan, in a file that already carries that lesson one layer
# up (its first draft spawned one jq per file per run and was slow). Then it was measured, and no
# cost was there to find: a full scan ran no slower with this kind declared than without it,
# so any difference is run-to-run noise. The index stays, and the honest
# reason is the next paragraph, not this one.
#
# IT PUTS THE REFUSAL IN THE RIGHT PLACE. A malformed marker is a property of the ARCHIVE, not
# of a run: it is the same defect whichever phase is being scored. Reading once means the refusal
# fires once, before any run is scored, from the top level where `die` ends the scan -- instead of
# once per run, from inside a command substitution, where `die` ends only a subshell and the scan would
# have to notice through `set -e`. The loudest rule in this grammar should not depend on a shell
# option staying switched on.
#
# The reader itself supplies whole-line-only and fence-awareness, so neither is re-derived here: a
# document that QUOTES a marker inside a fenced block is not a marker, and this phase's own spec
# does exactly that.
FM_INDEX=""
fm_build_index() {
  local sentinel="$1" repo_root="$2" specs="$3"
  local spec roots root f rel payloads payload base cand rc seen=""
  while IFS= read -r spec; do
    [ -n "$spec" ] || continue
    case "$spec" in *"|fragment-marker|"*) ;; *) continue ;; esac
    # `<stage>|<kind>|<suffix>|<roots>` -- drop the first three fields. `suffix` has no meaning for
    # this kind: a marker names a source PATH, and the phase name comes from its basename.
    roots="${spec#*|}"; roots="${roots#*|}"; roots="${roots#*|}"
    for root in $roots; do
      for f in $repo_root/$root; do
        [ -f "$f" ] || continue
        rel="${f#"$repo_root"/}"
        # A file declared under two stages is read once, not twice.
        case "$seen" in *"|$rel|"*) continue ;; esac
        seen="$seen|$rel|"
        [ -r "$f" ] || die "declared root $rel is not readable, so this scan cannot say whether it holds markers" 3
        payloads="$(awk -v emit=payload -f "$sentinel" "$f")" && rc=0 || rc=$?
        [ "$rc" -eq 3 ] && die "malformed fragment marker in $rel -- a sentinel-shaped line whose payload is empty, or whose comment never closes. The grammar fails loud here on purpose: a marker nobody can read must not be scored as a marker nobody wrote." 3
        # 2 IS NOT A VERDICT IN PAYLOAD MODE. The reader's contract uses 2 for "a sentinel naming
        # this phase was rejected as FENCED", which only the slice mode returns; in payload mode a
        # 2 is `awk` itself failing -- a syntax error in the program, or an input it could not read.
        # Measured: both exit 2. Falling through to `continue` scored that as "this file holds no
        # markers", which is the fail-OPEN reading of "I could not look".
        [ "$rc" -eq 2 ] && die "the fragment-sentinel reader could not run against $rel (awk exited 2: a program that does not parse, or an input it cannot read). A reader that could not look must not be scored as a file holding nothing." 3
        [ "$rc" -eq 0 ] || continue
        while IFS= read -r payload; do
          [ -n "$payload" ] || continue
          # The phase name comes from the payload's BASENAME with a trailing `.md` optional, so
          # both observed forms parse. The match itself happens at lookup time through
          # `file_name_matches` -- the same anchored rule the filename finder uses, so "this name
          # is that phase" has one definition and not two.
          base="${payload##*/}"
          case "$base" in *phase-*) cand="${base##*phase-}" ;; *) continue ;; esac
          FM_INDEX="$FM_INDEX$rel|${cand%.md}"$'\n'
        done <<EOF2
$payloads
EOF2
      done
    done
  done <<EOF
$specs
EOF
}

# Print every declared file under these roots that carries a marker naming this phase.
find_fragment_markers() {
  local slug="$1" repo_root="$2"; shift 2
  local root f paths="" rel cand hit=""
  for root in "$@"; do
    for f in $repo_root/$root; do
      [ -f "$f" ] || continue
      paths="$paths|${f#"$repo_root"/}|"
    done
  done
  [ -n "$paths" ] || return 0
  # `|` is the field separator for the same reason the registry specs use it: a path can hold `/`,
  # `*`, `.` and `-`, but not a pipe. A TAB would be worse than useless here -- it is IFS
  # whitespace, so a run of them collapses and an empty field shifts the next one left.
  while IFS='|' read -r rel cand; do
    [ -n "$rel" ] || continue
    case "$paths" in *"|$rel|"*) ;; *) continue ;; esac
    case "$hit" in *"|$rel|"*) continue ;; esac
    file_name_matches "$cand" "$slug" || continue
    hit="$hit|$rel|"
    printf '%s\n' "$rel"
  done <<EOF
$FM_INDEX
EOF
  # Same reason as the finders above: under `set -e` a trailing non-zero from the last match test
  # would become this function's status and kill the scan on the common case.
  return 0
}

# --- scan -------------------------------------------------------------------------------------
cmd_scan() {
  local roadmap="" out_dir="" registry="" repo_root="" repo_id="" now="" emitter="" sentinel=""
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --roadmap)   [ "$#" -ge 2 ] || die "--roadmap needs a value";   roadmap="$2";   shift 2 ;;
      --out-dir)   [ "$#" -ge 2 ] || die "--out-dir needs a value";   out_dir="$2";   shift 2 ;;
      --registry)  [ "$#" -ge 2 ] || die "--registry needs a value";  registry="$2";  shift 2 ;;
      --repo-root) [ "$#" -ge 2 ] || die "--repo-root needs a value"; repo_root="$2"; shift 2 ;;
      --repo-id)   [ "$#" -ge 2 ] || die "--repo-id needs a value";   repo_id="$2";   shift 2 ;;
      --now)       [ "$#" -ge 2 ] || die "--now needs a value";       now="$2";       shift 2 ;;
      --emitter)   [ "$#" -ge 2 ] || die "--emitter needs a value";   emitter="$2";   shift 2 ;;
      --sentinel)  [ "$#" -ge 2 ] || die "--sentinel needs a value";  sentinel="$2";  shift 2 ;;
      *) die "unknown argument: $1" ;;
    esac
  done
  [ -n "$roadmap" ] || die "--roadmap is required"
  [ -n "$out_dir" ] || die "--out-dir is required"
  command -v jq >/dev/null 2>&1 || die "jq not found"

  if [ -z "$repo_root" ]; then
    repo_root="$(git -C "$HERE" rev-parse --show-toplevel 2>/dev/null || true)"
    [ -n "$repo_root" ] || repo_root="$PWD"
  fi
  [ -n "$registry" ] || registry="$repo_root/.claude/stage-registry.json"
  [ -r "$registry" ] || die "registry is unreadable: $registry"
  if [ -z "$repo_id" ]; then
    # ledger-index.sh owns repo identity and pins the full fallback order. This is that order's FIRST entry,
    # used here so `scan` is runnable on its own.
    repo_id="$(git -C "$repo_root" rev-list --max-parents=0 HEAD 2>/dev/null | head -1)"
    [ -n "$repo_id" ] || die "--repo-id is required (no first commit to derive one from)"
  fi
  [ -n "$now" ] || now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  [ -n "$emitter" ] || emitter="$APPEND_DEFAULT"
  # An emitter that is not there, or not a file, is a hard failure rather than a silent skip: a
  # scan that cannot write is not a scan that found nothing.
  [ -f "$emitter" ] || die "emitter is not a file: $emitter"
  [ -n "$sentinel" ] || sentinel="$SENTINEL_DEFAULT"
  # Checked unconditionally, not only when the registry happens to declare a marker source: the
  # reader ships with this scanner, so its absence means a broken installation, and a scanner that
  # cannot read markers is not a scanner that found none.
  [ -f "$sentinel" ] || die "the fragment-sentinel reader is not a file: $sentinel"

  mkdir -p "$out_dir"

  # The registry is read ONCE, into one line per (stage, evidence source):
  #     <stage_id>|<kind>|<suffix>|<space-separated roots>
  # Reading it with two `jq` calls inside the per-run per-stage loop would spawn an interpreter
  # twice per (run, stage) pair; reading it once is far cheaper, and
  # the shape of the data is identical. `|` is the separator because a path can contain `/`, `*`,
  # `.` and `-` but not a pipe, and because a TAB would be worse than useless -- tab is IFS
  # whitespace, so `IFS=$'\t' read` collapses runs of them and an empty suffix field would shift
  # every root one column left.
  local specs stage_ids
  specs="$(jq -r '
      .stages[]
      | .stage_id as $sid
      | (.retro_evidence // [])[]
      | [$sid, .kind, (.suffix // ""), (.roots | join(" "))] | join("|")' "$registry")"
  stage_ids="$(jq -r '.stages[].stage_id' "$registry")"
  [ -n "$stage_ids" ] || die "the registry declares no stages -- every run would then be trivially complete"

  # Fragment markers are read here, once for the whole scan, and a malformed one refuses from this
  # level rather than from inside a per-run command substitution. See fm_build_index.
  fm_build_index "$sentinel" "$repo_root" "$specs"

  local slug run_id phase stage kind roots suffix artifacts found file spec
  local n_runs=0 n_records=0

  while IFS= read -r slug; do
    [ -n "$slug" ] || continue
    n_runs=$((n_runs + 1))
    run_id="retro-$slug"
    phase="${slug%%-*}"
    local ledger="$out_dir/$run_id.jsonl"
    : > "$ledger"

    while IFS= read -r stage; do
      [ -n "$stage" ] || continue

      artifacts=""
      while IFS= read -r spec; do
        [ -n "$spec" ] || continue
        case "$spec" in "$stage|"*) ;; *) continue ;; esac
        spec="${spec#*|}"; kind="${spec%%|*}"
        spec="${spec#*|}"; suffix="${spec%%|*}"
        roots="${spec#*|}"
        case "$kind" in
          phase-file)
            found="$(find_phase_files "$slug" "$suffix" "$repo_root" $roots)" ;;
          archive-heading)
            found="$(find_archive_headings "$slug" "$repo_root" $roots)" ;;
          fragment-marker)
            # A pure lookup in the index built before the run loop. The malformed-marker refusal
            # already fired there if it was going to, at the top level where `die` ends the scan.
            found="$(find_fragment_markers "$slug" "$repo_root" $roots)" ;;
          prose-token)
            # The run population IS this file, so this is true by construction for a retro run.
            # Emitted anyway and labelled in the registry, rather than silently dropped.
            found=""
            for expanded in $roots; do
              if [ -f "$repo_root/$expanded" ]; then found="$expanded"; fi
            done ;;
          *) die "unknown retro_evidence kind for $stage: $kind" ;;
        esac
        [ -z "$found" ] || artifacts="$artifacts$found"$'\n'
      done <<EOF
$specs
EOF

      # No evidence source at all -> not recoverable -> no record, and the reader renders
      # `unknown (retro)`. A source that found nothing -> recoverable but absent -> also no record,
      # and the reader renders `missing`. The two look identical HERE and are told apart by the
      # registry, which is the only place that knows which stages can leave a trace.
      [ -n "$artifacts" ] || continue

      set -- append --file "$ledger" \
        --run-id "$run_id" --repo-id "$repo_id" --phase "$phase" --stage-id "$stage" \
        --attempt-id 1 --type stage_observation --status done --observed true \
        --observer scan --started-at "$now" --completed-at "$now" --retro
      while IFS= read -r file; do
        [ -n "$file" ] || continue
        set -- "$@" --artifact "$file"
      done <<EOF
$(printf '%s' "$artifacts" | sort -u)
EOF
      # Count what LANDED, never what was invoked. The old counter incremented once per call, so
      # an emitter that wrote nothing still produced "wrote N records" -- a number measuring the
      # loop rather than the ledger, which is "claim wider than mechanism" in one line.
      local before after
      before="$(wc -l < "$ledger" 2>/dev/null || printf 0)"
      /bin/bash "$emitter" "$@" || true
      after="$(wc -l < "$ledger" 2>/dev/null || printf 0)"
      n_records=$((n_records + after - before))
    done <<EOF
$stage_ids
EOF

    # A run with no recoverable evidence at all still gets a file, and the file is EMPTY rather
    # than absent. An absent file and a run that produced nothing are different facts, and the
    # second one is the entire question the ledger exists to answer.
    [ -f "$ledger" ] || : > "$ledger"
  done <<EOF
$(enumerate_runs "$roadmap")
EOF

  printf 'scanned %s runs, wrote %s records into %s\n' "$n_runs" "$n_records" "$out_dir"
}

main() {
  [ "$#" -ge 1 ] || { usage; exit 2; }
  local mode="$1"; shift
  case "$mode" in
    runs)
      local roadmap=""
      while [ "$#" -gt 0 ]; do
        case "$1" in
          --roadmap) [ "$#" -ge 2 ] || die "--roadmap needs a value"; roadmap="$2"; shift 2 ;;
          *) die "unknown argument: $1" ;;
        esac
      done
      [ -n "$roadmap" ] || die "--roadmap is required"
      enumerate_runs "$roadmap" ;;
    scan)      cmd_scan "$@" ;;
    -h|--help) usage; exit 0 ;;
    *)         usage; exit 2 ;;
  esac
}

main "$@"
