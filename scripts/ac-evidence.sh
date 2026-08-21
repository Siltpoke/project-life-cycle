#!/bin/bash
# scripts/ac-evidence.sh — every acceptance criterion owns an oracle, or a written-down exclusion.
#
# This proves each criterion HAS an oracle. It never proves the oracle is correct, and an exclusion
# self-destructs only when its condition fails, never when its reasoning was wrong.
#
# Envelope: bash + jq + git ONLY. No python3, and no `shasum` either -- it is a perl
# script on macOS and would widen that envelope.
# Hashing, where this file needs it, goes through `git hash-object`.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST="${AC_MANIFEST:-$HERE/../.claude/close-gate.json}"

die() { printf '%s\n' "$*" >&2; exit 1; }

# The heading set is declared in the manifest so an adopter can extend it without editing the gate.
# Real user stories differ in this heading: `## Acceptance criteria`
# (lowercase c), a CJK heading (U+9A8C U+6536 U+6807 U+51C6), and
# `## Acceptance Criteria` all occur. A single literal would be blind to most of them.
heading_set() {
  if [ -r "$MANIFEST" ] && jq -e '.ac_heading_set' "$MANIFEST" >/dev/null 2>&1; then
    jq -r '.ac_heading_set[]' "$MANIFEST"
  else
    # The CJK heading is emitted as octal UTF-8, not as a literal, so this file carries no CJK bytes.
    # Verified byte-identical to the literal. `$'\uXXXX'` is NOT an option --
    # macOS /bin/bash is 3.2 and that syntax needs 4.2+.
    printf '%s\n' 'acceptance criteria' "$(printf '\351\252\214\346\224\266\346\240\207\345\207\206')"
  fi
}

# Print "<start-line> <end-line>" for the acceptance-criteria section, or die naming the heading set.
section_range() {
  local file="$1" h start level end
  start=""
  while IFS= read -r h; do
    # DO NOT use awk's `==` here. On macOS awk (version 20200816) string equality returns TRUE for
    # ANY two non-ASCII strings: comparing a story heading (U+6545 U+4E8B) with the
    # acceptance heading (U+9A8C U+6536 U+6807 U+51C6) prints EQUAL, while "foo" == "bar" prints
    # notequal. Under `==` this matcher locks onto the FIRST CJK heading in a file
    # instead of the real acceptance section.
    # `length()` plus `index()` compares bytes and is portable.
    start="$(awk -v want="$(printf '%s' "$h" | tr '[:upper:]' '[:lower:]')" '
      function same(a, b) { return (length(a) == length(b)) && (index(a, b) == 1) }
      /^#+[[:space:]]/ {
        line = tolower($0)
        sub(/^#+[[:space:]]*/, "", line)
        gsub(/[[:punct:]]+$/, "", line)
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", line)
        if (same(line, want)) { print NR; exit }
      }' "$file")"
    [ -n "$start" ] && break
  done < <(heading_set)

  # Section ABSENT is its own failure, distinct from section-empty. A missing section must never
  # read as "this phase has no criteria".
  [ -n "$start" ] || die "no acceptance-criteria section found in $file -- the heading set is: $(heading_set | tr '\n' '/')"

  level="$(awk -v n="$start" 'NR==n { match($0, /^#+/); print RLENGTH }' "$file")"
  end="$(awk -v n="$start" -v L="$level" '
    NR > n && /^#+[[:space:]]/ { match($0, /^#+/); if (RLENGTH <= L) { print NR; exit } }' "$file")"
  [ -n "$end" ] || end="$(( $(wc -l < "$file") + 1 ))"
  printf '%s %s\n' "$start" "$end"
}

# Closed section grammar: inside the acceptance-criteria section every line must be a recognised
# declaration, an indented continuation, a blank line, a fenced block or a blockquote. Anything else
# is a hard failure naming the line -- which turns `### AC3` and a table row from a SILENT
# under-count into a red, without the checker ever deciding what they mean.
parse_criteria() {
  local file="$1" phase="$2" range start end
  [ -r "$file" ] || die "story file is unreadable: $file"
  range="$(section_range "$file")"
  read -r start end <<<"$range"

  awk -v start="$start" -v end="$end" -v phase="$phase" '
    function emit(id, ln,   tok) {
      tok = id; sub(/:.*$/, "", tok)
      if (tok != phase) {
        printf "declaration at line %d carries phase token %s, expected %s\n", ln, tok, phase > "/dev/stderr"
        bad = 1; return
      }
      if (id in seen) {
        printf "duplicate id %s at lines %d and %d\n", id, seen[id], ln > "/dev/stderr"
        bad = 1; return
      }
      seen[id] = ln
      order[++n] = id
    }
    NR <= start || NR >= end { next }
    /^```/            { fence = !fence; next }
    fence             { next }
    /^[[:space:]]*>/  { next }   # blockquote
    /^[[:space:]]*$/  { next }   # blank
    /^[[:space:]]+/   { next }   # indented continuation of a declaration
    {
      line = $0
      # long form:  - **<phase>:AC3**:   or   - **<phase>:AC3** —
      if (match(line, /^- \*\*[A-Za-z0-9_.-]+:AC[0-9]+(\.[0-9]+)?[a-z]?\*\*[[:space:]]*([:—–])/)) {
        id = line; sub(/^- \*\*/, "", id); sub(/\*\*.*$/, "", id)
        emit(id, NR); next
      }
      # short form: - **AC3** {#<phase>:AC3}:   -- the human label, plus the
      # machine-visible scoped anchor.
      if (match(line, /^- \*\*AC[0-9]+(\.[0-9]+)?[a-z]?\*\*[[:space:]]*\{#[A-Za-z0-9_.-]+:AC[0-9]+(\.[0-9]+)?[a-z]?\}[[:space:]]*([:—–])/)) {
        label = line; sub(/^- \*\*/, "", label); sub(/\*\*.*$/, "", label)
        anchor = line; sub(/^[^{]*\{#/, "", anchor); sub(/\}.*$/, "", anchor)
        bare = anchor; sub(/^[^:]*:/, "", bare)
        if (bare != label) {
          printf "label/anchor mismatch at line %d: **%s** vs {#%s}\n", NR, label, anchor > "/dev/stderr"
          bad = 1; next
        }
        emit(anchor, NR); next
      }
      printf "unrecognised construct in the acceptance-criteria section, line %d: %s\n", NR, line > "/dev/stderr"
      bad = 1
    }
    END {
      if (bad) exit 1
      if (n == 0) { print "no declarations parsed from the acceptance-criteria section" > "/dev/stderr"; exit 1 }
      for (i = 1; i <= n; i++) print order[i]
    }
  ' "$file"
}

# The declaration line for one id plus every following indented continuation, whitespace-normalised.
# This is the digest preimage for the baseline (scripts/ac-baseline.sh). Full declaration, not the
# first line: criteria in real stories wrap across three and four lines, and hashing only
# the `- **id**:` line would let a one-word semantic inversion inside a continuation pass while a
# pure rewrap reds.
declaration_text() {
  local file="$1" id="$2" range start end
  [ -r "$file" ] || die "story file is unreadable: $file"
  range="$(section_range "$file")"
  read -r start end <<<"$range"
  awk -v start="$start" -v end="$end" -v id="$id" '
    NR <= start || NR >= end { next }
    /^- \*\*/ {
      want = (index($0, id) > 0)
      if (want) { inside = 1; buf = $0; next }
      if (inside) { exit }
      inside = 0; next
    }
    inside && /^[[:space:]]+/ { buf = buf " " $0; next }
    inside && /^[[:space:]]*$/ { next }
    inside { exit }
    END { if (buf != "") { gsub(/[[:space:]]+/, " ", buf); sub(/^ /, "", buf); sub(/ $/, "", buf); print buf } }
  ' "$file"
}

# Walk a covered_by_oracle chain. Returns 0 only when it terminates on a row whose status is
# `oracle` -- a chain that merely leaves the exclusion graph proves nothing. `seen` carries the path
# so a cycle is reported with its members instead of recursing forever.
#
# What this CANNOT see, stated because the neighbouring comment would otherwise over-claim: whether
# the terminal carrier actually asserts anything. That is a stated bound, not a hole to patch.
chain_terminates() {
  local id="$1" ev="$2" seen="${3:-}" row status next
  case " $seen " in *" $id "*) printf '%s -> %s\n' "${seen# }" "$id"; return 1 ;; esac
  row="$(jq -c --arg id "$id" '.criteria[]? | select(.id == $id)' "$ev")"
  [ -n "$row" ] || return 1
  status="$(jq -r '.status // ""' <<<"$row")"
  [ "$status" = "oracle" ] && return 0
  [ "$status" = "excluded" ] || return 1
  [ "$(jq -r '.exclusion.type // ""' <<<"$row")" = "covered_by_oracle" ] || return 1
  while IFS= read -r next; do
    [ -n "$next" ] || continue
    chain_terminates "$next" "$ev" "$seen $id" || return 1
  done < <(jq -r '.exclusion.condition.criteria_still_naming[]?' <<<"$row")
  return 0
}

# Validate one `status: excluded` row. Two types are BUILT; `certified_once` is specified in the
# format and deliberately not implemented (no criterion has needed that shape yet), and a row
# declaring it is routed to UNMAPPED rather than silently accepted or mis-reported as unknown.
# Everything malformed fails CLOSED -- explicitly against Snyk's precedent of honouring a malformed
# expiry forever.
exclusion_row() {
  local id="$1" row="$2" ev="$3" type names n path cyc
  type="$(jq -r '.exclusion.type // ""' <<<"$row")"
  case "$type" in
    covered_by_oracle)
      names="$(jq -r '.exclusion.condition.criteria_still_naming[]?' <<<"$row")"
      if [ -z "$names" ]; then
        printf '  %-12s UNMAPPED  malformed: covered_by_oracle with an empty criteria_still_naming\n' "$id"
        return 1
      fi
      while IFS= read -r n; do
        [ -n "$n" ] || continue
        if ! cyc="$(chain_terminates "$n" "$ev" "$id")"; then
          if [ -n "$cyc" ]; then
            printf '  %-12s UNMAPPED  cycle in covered_by_oracle: %s\n' "$id" "$cyc"
          else
            printf '  %-12s UNMAPPED  condition no longer holds: %s is not (or no longer reaches) an oracle\n' "$id" "$n"
          fi
          return 1
        fi
      done <<<"$names"
      printf '  %-12s excluded  %-14s condition holds\n' "$id" "$type"
      ;;
    ci_unreachable_carrier)
      path="$(jq -r '.exclusion.condition.path // ""' <<<"$row")"
      if [ -z "$path" ]; then
        printf '  %-12s UNMAPPED  malformed: ci_unreachable_carrier with no path\n' "$id"; return 1
      fi
      if [ ! -e "${AC_CARRIER_ROOT:-$HERE/..}/$path" ]; then
        # Environment-determined, and said so rather than blamed on the author: in CI a gitignored
        # path usually does not exist at all, so this condition can only be evaluated where the
        # tree is complete. Fail closed, but name the environment.
        printf '  %-12s UNMAPPED  condition unevaluable here (path absent): %s\n' "$id" "$path"; return 1
      fi
      if ! git -C "${AC_CARRIER_ROOT:-$HERE/..}" check-ignore -q "$path"; then
        printf '  %-12s UNMAPPED  condition no longer holds: %s is no longer gitignored, so a real carrier is possible\n' "$id" "$path"
        return 1
      fi
      printf '  %-12s excluded  %-14s condition holds\n' "$id" "$type"
      ;;
    certified_once)
      printf "  %-12s UNMAPPED  exclusion type 'certified_once' is specified but not implemented; this criterion is unmapped\n" "$id"
      return 1
      ;;
    *)
      printf '  %-12s UNMAPPED  malformed: unknown exclusion type %s\n' "$id" "${type:-<absent>}"
      return 1
      ;;
  esac
  return 0
}

# Reference discipline over the artifacts THIS PHASE creates.
#
# STAGED, and saying so is the point: four kinds of artifact carry criterion links -- test name, journal,
# review finding, evidence row. This checks ONE of them, and leaves two questions open:
# where the authority to grandfather REFERENCES comes from (the baseline grandfathers
# criteria, not references), and how a checker tells a claim from a quotation in an
# append-only record. A green row here does NOT mean a repo's test files are clean: they can
# still carry bare AC ids.
#
# A qualifier is `<token>:` only. `<token>-` would make ordinary prose qualify -- "the pre-AC10
# behaviour" reads as phase `pre`, and every hyphenated word becomes a namespace.
scan_refs() {
  local phase="$1" declared="$2" fail=0 file label val stripped tok
  shift 2
  while [ $# -gt 0 ]; do
    file="$1"; label="$2"; shift 2
    [ -n "$file" ] && [ -r "$file" ] || continue
    while IFS= read -r val; do
      [ -n "$val" ] || continue
      # Delete every QUALIFIED id first; anything of the shape AC<n> still standing is bare.
      stripped="$(printf '%s' "$val" | sed -E 's/[A-Za-z0-9_.-]+:AC[0-9]+(\.[0-9]+)?[a-z]?//g')"
      if printf '%s' "$stripped" | grep -qE '(^|[^A-Za-z0-9_])AC[0-9]'; then
        printf '  REFERENCE  bare AC id in %s (%s): %s\n' "$label" "$file" "$val"
        fail=1
      fi
      # A this-phase id the story does not declare is an ORPHAN, distinct from "unmapped".
      for tok in $(printf '%s' "$val" | grep -oE "$phase:AC[0-9]+(\.[0-9]+)?[a-z]?" || true); do
        if ! printf '%s\n' "$declared" | grep -qFx "$tok"; then
          printf '  %-12s ORPHAN    referenced in %s, but the current story declares no such criterion\n' "$tok" "$label"
          fail=1
        fi
      done
    done < <(jq -r '.criteria[]? | .id, (.why // empty), (.exclusion.why // empty)' "$file" 2>/dev/null || true)
  done
  return "$fail"
}

# Task-mode scope: the union of `Closes:` trailers on this branch. Branch-cumulative, because the
# gate is handed a PHASE and never a task id.
# Nothing unclaimed ever enters scope, which is the guarantee this scope gives.
#
# Two properties this carrier does NOT have, stated so nobody relies on them: trailers do not
# survive squash-merge, and the scope moves when the merge-base moves. The second is mitigated by
# disclosure only -- the computed merge-base is printed on every run.
scope_from_trailers() {
  local phase="$1" base="" mb raw tok out=""
  shift
  while [ $# -gt 0 ]; do
    case "$1" in
      --base) base="$2"; shift 2 ;;
      *) die "scope-from-trailers: unknown option $1" ;;
    esac
  done
  if [ -z "$base" ]; then
    base="$(git symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null || true)"
    [ -n "$base" ] || die "cannot determine the default branch: origin/HEAD is unset (a --single-branch clone or a fork remote does this). Pass --base <ref>, or run: git remote set-head origin -a"
  fi
  mb="$(git merge-base "$base" HEAD 2>/dev/null)" || die "no merge-base between $base and HEAD"
  printf 'scope computed from merge-base %s\n' "$mb" >&2

  raw="$(git log --format='%(trailers:key=Closes,valueonly)' "$mb..HEAD" | tr ' ' '\n' | sed '/^$/d')"
  [ -n "$raw" ] || return 0
  while IFS= read -r tok; do
    [ -n "$tok" ] || continue
    case "$tok" in
      *:AC*) out="$out$tok"$'\n' ;;
      '#'*)  die "a \`Closes:\` trailer names an issue ($tok), not an acceptance criterion. Use \`Refs:\` for issues." ;;
      *)     die "unparseable \`Closes:\` value: $tok" ;;
    esac
  done <<<"$raw"
  printf '%s' "$out" | sort -u
}

DISCLAIMER_1="this proves each criterion HAS an oracle. It never proves the oracle is correct,"
DISCLAIMER_2="and an exclusion self-destructs only when its condition fails, never when its reasoning was wrong."

# Validate one `status: oracle` row. Prints its line; returns non-zero when the row is unmapped.
oracle_row() {
  local id="$1" row="$2" klass carrier path sym root
  klass="$(jq -r '.class // ""' <<<"$row")"
  case "$klass" in
    mutant-killed|tracked-suite|local-only|pin) ;;
    *) printf '  %-12s UNMAPPED  malformed: class %s\n' "$id" "${klass:-<absent>}"; return 1 ;;
  esac
  carrier="$(jq -r '.carrier // ""' <<<"$row")"
  path="${carrier%%::*}"
  sym=""
  case "$carrier" in *::*) sym="${carrier#*::}" ;; esac
  root="${AC_CARRIER_ROOT:-$HERE/..}"
  if [ -z "$path" ] || [ ! -e "$root/$path" ]; then
    printf '  %-12s UNMAPPED  carrier path does not exist: %s\n' "$id" "${path:-<absent>}"; return 1
  fi
  # Dangling-pointer check, NOT a quality judgement: a carrier naming a symbol that is no longer in
  # the file points at nothing. Without it, removing a guard cannot change any verdict and
  # a guard-removal test can never go red. Known false green: a mention in a comment satisfies
  # a plain string match. Still strictly stronger than path-existence.
  if [ -n "$sym" ] && ! grep -qF -- "$sym" "$root/$path"; then
    printf '  %-12s UNMAPPED  carrier names %s, which is not in %s\n' "$id" "$sym" "$path"; return 1
  fi
  printf '  %-12s oracle    %-14s %s\n' "$id" "$klass" "$carrier"
  return 0
}

# One row per criterion in scope. Exit 0 only when every one of them is mapped.
report() {
  local story="" phase="" ev="" ids_file="" baseline="" fail=0 declared scope id row status why
  story="${1:?report: <story> <phase>}"; phase="${2:?report: <story> <phase>}"; shift 2
  while [ $# -gt 0 ]; do
    case "$1" in
      --evidence) ev="$2"; shift 2 ;;
      --ids)      ids_file="$2"; shift 2 ;;
      --baseline) baseline="$2"; shift 2 ;;
      *) die "report: unknown option $1" ;;
    esac
  done
  [ -n "$ev" ] || ev="$(jq -r '.ac_evidence // ".claude/ac-evidence.json"' "$MANIFEST")"

  # A top-level parse failure is reported ONCE as a broken file. Reporting it as "every criterion is
  # unmapped" reads as catastrophe and sends the reader to write evidence instead of fix a comma.
  jq -e . "$ev" >/dev/null 2>&1 || die "evidence file is unreadable or not valid JSON: $ev -- nothing about individual criteria can be concluded from this"

  declared="$(parse_criteria "$story" "$phase")"

  printf 'ac-oracle-binding  phase %s\n' "$phase"
  # The scope line names WHERE the scope came from, never how big it is, and it differs
  # per mode: saying "the declared set" while checking a trailer-derived set would be misleading,
  # and printing nothing for an empty task scope is the empty-set-guard shape.
  if [ -n "$ids_file" ]; then
    if [ -s "$ids_file" ]; then
      printf '  scope: the criteria this branch declares it closes (merge-base %s)\n' "${AC_MERGE_BASE:-unknown}"
    else
      printf '  scope: no criteria claimed by any commit on this branch\n'
    fi
    # An id a commit CLAIMS that the story does not declare must be reported. The intersection
    # below would silently drop it, and an unclaimed id must be reported distinctly.
    while IFS= read -r id; do
      [ -n "$id" ] || continue
      case "$id" in "$phase":AC*) ;; *) continue ;; esac
      if ! grep -qFx "$id" <<<"$declared"; then
        printf '  %-12s ORPHAN    claimed by a `Closes:` trailer, but the current story declares no such criterion\n' "$id"
        fail=1
      fi
    done < "$ids_file"
    scope="$(grep -Fxf "$ids_file" <<<"$declared" || true)"
  else
    printf '  scope: the declared set of %s\n' "$story"
    scope="$declared"
  fi

  # Reference discipline across the artifacts this phase creates: bare ids fail, this-phase ids the
  # story does not declare are ORPHANS (distinct from "unmapped" -- two mistakes, two messages).
  scan_refs "$phase" "$declared" "$ev" "evidence row" ${baseline:+"$baseline" "baseline entry"} || fail=1

  while IFS= read -r id; do
    [ -n "$id" ] || continue
    row="$(jq -c --arg id "$id" '.criteria[]? | select(.id == $id)' "$ev")"
    if [ -z "$row" ]; then
      baselined_row "$id" "$baseline" "$story" || fail=1
      continue
    fi
    why="$(jq -r '.why // .exclusion.why // ""' <<<"$row")"
    if [ -z "$why" ]; then
      printf '  %-12s UNMAPPED  malformed: row has no `why`\n' "$id"; fail=1; continue
    fi
    status="$(jq -r '.status // ""' <<<"$row")"
    case "$status" in
      oracle)   oracle_row "$id" "$row" || fail=1 ;;
      excluded) exclusion_row "$id" "$row" "$ev" || fail=1 ;;
      *)        printf '  %-12s UNMAPPED  malformed: status %s\n' "$id" "${status:-<absent>}"; fail=1 ;;
    esac
  done <<<"$scope"

  baseline_rows "$baseline" || true
  printf '  %s\n  %s\n' "$DISCLAIMER_1" "$DISCLAIMER_2"
  return "$fail"
}

# The dispatcher lists every arm, so a new arm adds a FUNCTION above it and never
# has to touch this block. An un-implemented arm dies with a clear message.
not_yet() { die "$1: not implemented until its task lands"; }
# A criterion with no evidence row is UNMAPPED unless the baseline grandfathers it -- and a
# grandfathered entry loses its protection the moment its declaration TEXT changes, which is what
# makes the scoping "new-or-CHANGED" rather than merely "new". Cross-phase entries carry a null
# digest (their story is unreadable here), so change detection is current-phase-only; that hole is
# real and is stated here.
baselined_row() {
  local id="$1" baseline="$2" story="$3" entry want have
  if [ -z "$baseline" ] || [ ! -r "$baseline" ]; then
    printf '  %-12s UNMAPPED  no evidence row\n' "$id"; return 1
  fi
  entry="$(jq -c --arg id "$id" '.criteria[]? | select(.id == $id)' "$baseline")"
  if [ -z "$entry" ]; then
    printf '  %-12s UNMAPPED  no evidence row\n' "$id"; return 1
  fi
  want="$(jq -r '.digest // ""' <<<"$entry")"
  if [ -n "$want" ]; then
    # Byte-for-byte the same preimage as scripts/ac-baseline.sh's declaration_digest: `printf %s`,
    # no trailing newline. Measured: the pipeline form appends one and the two digests then never
    # match, so a freshly-added entry reads as CHANGED on the very next run. Two code paths
    # computing "the same" digest differently is the encoder-divergence class.
    have="$(printf '%s' "$(declaration_text "$story" "$id" 2>/dev/null)" | git hash-object --stdin)"
    if [ "$want" != "$have" ]; then
      printf '  %-12s UNMAPPED  baselined, but its declaration has CHANGED since it was grandfathered -- it needs an oracle now\n' "$id"
      return 1
    fi
  fi
  printf '  %-12s baselined grandfathered   %s\n' "$id" "$(jq -r '.why' <<<"$entry")"
  return 0
}

# Nothing forces the baseline to shrink. Printing what remains on every run is the whole mitigation.
baseline_rows() {
  local baseline="$1" id
  [ -n "$baseline" ] && [ -r "$baseline" ] || return 0
  while IFS= read -r id; do
    [ -n "$id" ] || continue
    printf '  baseline: %s (explicit action required to add; removals automatic at phase close)\n' "$id"
  done < <(jq -r '.criteria[]?.id // empty' "$baseline")
  return 0
}

case "${1:-}" in
  parse-criteria)      shift; parse_criteria "$@" ;;
  declaration-text)    shift; declaration_text "$@" ;;
  report)              shift; report "$@" ;;
  scope-from-trailers) shift; scope_from_trailers "$@" ;;
  scan-refs)           shift; scan_refs "$@" ;;
  *) die "usage: ac-evidence.sh <parse-criteria|declaration-text|report|scope-from-trailers|scan-refs> ..." ;;
esac
