#!/usr/bin/env bash
# Invariant (p36): the station-plan blocks in docs/ROADMAP.md are structurally sound --
# ids well-formed and unique, every `binds-to:` resolving to exactly one mainline row, no row
# bound twice, the line set inside a block closed, step numbering 1..N consecutive within
# bounds, each step within the column budget, and the active list naming only known stations.
#
# Contract: skills/project-lifecycle/references/roadmap-format.md
# Fixtures: skills/project-lifecycle/references/roadmap-format/fixtures/
#
# THE LINE SET IS CLOSED, NOT THE KEY SET. A checker anchored on `:` cannot see a line that
# has no colon -- `- done` is not a key to it, so a closed-KEY-set rule lets exactly the thing
# it exists to stop walk straight in. Every line inside a block is therefore matched against a
# whitelist of SHAPES; anything unmatched is red whether or not it contains a colon.
#
# STEP COUNT HAS A LOWER BOUND AND THAT IS NOT PEDANTRY. An empty `steps:` satisfies "no more
# than 7" and "no gaps" -- both upper-bound-shaped rules -- and leaves a divide-by-zero in the
# position derivation downstream. Zero steps is red.
#
# WIDTH is measured over the RENDERED line including the `sN ` prefix and excluding the
# markdown `  - ` marker, per the contract: the budget exists so a step does not wrap in an
# 80-column terminal, and what wraps is what a renderer prints. Widths come from
# scripts/lib/eaw-ranges.jq, exported from the Unicode database -- see that file's header for
# the declared treatment of Ambiguous-width characters.
#
# WHAT THIS DOES NOT CHECK, named rather than implied:
#   * dependency edges -- station-deps-acyclic.sh.
#   * stored positions -- no-stored-position.sh.
#   * step references from closure declarations -- closed-step-refs-resolve.sh, which scans
#     the whole corpus including docs/archive/ and is therefore a different input set.
#   * whether a station derived done is also declared in flight -- station-state-consistency.sh.
#   * whether the blocks are placed where they cut no section open --
#     roadmap-station-blocks-placement.sh.
#   * a `### ` heading inside a fenced code block: the scan is line-oriented and fence-blind.
#
# Envelope: bash + jq + coreutils. No python3 (CLAUDE.md).
set -euo pipefail

ROADMAP="${ROADMAP_PATH:-docs/ROADMAP.md}"
HERE="$(cd "$(dirname "$0")" && pwd)"
LIBDIR="${EAW_LIB_DIR:-$HERE/../lib}"
MAX_STEPS="${MAX_STEPS:-7}"
MAX_COLS="${MAX_COLS:-60}"

fail=0
bad() { printf '✗ %s\n' "$*" >&2; fail=1; }

[ -f "$ROADMAP" ] || { printf '✗ %s is not a regular file\n' "$ROADMAP" >&2; exit 1; }
[ -f "$LIBDIR/eaw-ranges.jq" ] || {
  printf '✗ %s/eaw-ranges.jq missing — regenerate with scripts/gen-eaw-ranges.py\n' "$LIBDIR" >&2
  exit 1
}
# The block grammar lives in ONE file, shared with the two corpus validators (the station-plan work).
# Checked for presence rather than assumed: a missing program makes awk read the roadmap as
# an empty stream, which prints as "no blocks — nothing to check" and exits 0.
STATION_AWK="${STATION_BLOCKS_AWK:-$HERE/../lib/station-blocks.awk}"
[ -f "$STATION_AWK" ] || {
  printf '✗ %s missing — the station-block parser is shared, not inlined\n' "$STATION_AWK" >&2
  exit 1
}

# --- collect the mainline row names -----------------------------------------------------
# `name` is cells[0] with surrounding whitespace trimmed, matching how every consumer reads it.
mainline_names=$(
  awk '
    index($0, "## 🛣") == 1 { inmain = 1; next }
    inmain && substr($0, 1, 3) == "## " { inmain = 0 }
    inmain {
      t = $0; sub(/^[ \t]+/, "", t)
      if (substr(t, 1, 1) != "|") next
      if (t ~ /^\|[-: |]+\|?$/) { seensep = 1; next }   # separator row
      # THE HEADER IS THE ROW BEFORE THE SEPARATOR, not a row whose first cell holds a
      # particular word. It used to compare against the header cell of THIS repo
      # roadmap, hard-coded and CJK. Two things were wrong and only one is about language:
      # an adopter whose header cell reads `station` had that header row collected as a
      # station name, and a CJK literal in a shipped file is what the CJK rule refuses.
      # Position is structural and survives translation; a word does not.
      if (!seensep) next
      n = split(t, c, "|")
      if (n < 3) next
      name = c[2]
      gsub(/^[ \t]+|[ \t]+$/, "", name)
      if (name == "") next
      print name
    }
  ' "$ROADMAP"
)

# --- parse the plan blocks --------------------------------------------------------------
# Emits one TSV record per finding so the shell stays out of the parsing.
blocks=$(awk -f "$STATION_AWK" "$ROADMAP")

if [ -z "$blocks" ]; then
  printf '⊘ no station-plan blocks in %s — nothing to check (this is legal today; it stops being legal once a block exists)\n' "$ROADMAP"
  exit 0
fi

# --- parser-reported errors --------------------------------------------------------------
while IFS=$'\t' read -r kind a b c; do
  [ "$kind" = "ERR" ] || continue
  bad "$ROADMAP:$b block '$a': $c"
done <<EOF
$blocks
EOF

# --- ids: shape and uniqueness -------------------------------------------------------------
ids=$(printf '%s\n' "$blocks" | awk -F'\t' '$1=="BLOCK"{print $2}')
while IFS= read -r id; do
  [ -n "$id" ] || continue
  case "$id" in
    [a-z0-9]*) ;;
    *) bad "station id '$id' must start with [a-z0-9]" ; continue ;;
  esac
  if ! printf '%s' "$id" | grep -Eq '^[a-z0-9][a-z0-9-]{1,31}$'; then
    bad "station id '$id' does not match ^[a-z0-9][a-z0-9-]{1,31}\$"
  fi
done <<EOF
$ids
EOF

dupes=$(printf '%s\n' "$ids" | sort | uniq -d)
[ -z "$dupes" ] || while IFS= read -r d; do
  [ -n "$d" ] && bad "station id '$d' is declared by more than one block"
done <<EOF
$dupes
EOF

# --- binds-to: resolves to exactly one row, and no row is bound twice ------------------------
bound_rows=""
while IFS=$'\t' read -r kind id target nsteps _line; do
  [ "$kind" = "BLOCK" ] || continue
  [ -n "$target" ] || continue
  matches=$(printf '%s\n' "$mainline_names" | grep -Fxc -- "$target" || true)
  if [ "$matches" -eq 0 ]; then
    bad "block '$id': binds-to matches no mainline row (orphan): $target"
  elif [ "$matches" -gt 1 ]; then
    bad "block '$id': binds-to matches $matches mainline rows, must be exactly one"
  fi
  bound_rows="$bound_rows$target
"
  if [ "$nsteps" -lt 1 ]; then
    bad "block '$id': zero steps — the lower bound is 1 (an empty list satisfies every upper-bound rule and divides by zero downstream)"
  elif [ "$nsteps" -gt "$MAX_STEPS" ]; then
    bad "block '$id': $nsteps steps, the bound is $MAX_STEPS"
  fi
done <<EOF
$blocks
EOF

dupe_rows=$(printf '%s' "$bound_rows" | grep -v '^$' | sort | uniq -d || true)
[ -z "$dupe_rows" ] || while IFS= read -r r; do
  [ -n "$r" ] && bad "mainline row bound by more than one block: $r"
done <<EOF
$dupe_rows
EOF

# --- steps: consecutive from 1, and within the column budget --------------------------------
for id in $(printf '%s\n' "$ids" | sort -u); do
  expected=1
  while IFS=$'\t' read -r kind bid num text; do
    [ "$kind" = "STEP" ] && [ "$bid" = "$id" ] || continue
    if [ "$num" -ne "$expected" ]; then
      bad "block '$id': step numbering is not consecutive — expected s$expected, found s$num"
    fi
    expected=$((expected + 1))
    width=$(printf '%s' "$text" | jq -Rr "include \"eaw-ranges\" {search:\"$LIBDIR\"}; dispwidth")
    if [ "$width" -gt "$MAX_COLS" ]; then
      bad "block '$id': step s$num is $width display columns, the bound is $MAX_COLS"
    fi
  done <<EOF
$blocks
EOF
done

# --- the active list names only known stations ---------------------------------------------
active_block_present=0
if grep -q '^## 🚦' "$ROADMAP"; then
  active_block_present=1
  active=$(printf '%s\n' "$blocks" | awk -F'\t' '$1=="ACTIVE"{print $2}')
  while IFS= read -r a; do
    [ -n "$a" ] || continue
    if ! printf '%s\n' "$ids" | grep -Fxq -- "$a"; then
      bad "the active list names '$a', which no plan block declares"
    fi
  done <<EOF
$active
EOF
else
  bad "no '## 🚦' active block — an absent block cannot be told apart from an unfilled one"
fi

nblocks=$(printf '%s\n' "$ids" | grep -c '^..*$' || true)
if [ "$fail" -ne 0 ]; then
  printf '✗ station-id-integrity: FAILED\n' >&2
  exit 1
fi
printf '✓ station-id-integrity (%s block(s), active block present=%s)\n' "$nblocks" "$active_block_present"
