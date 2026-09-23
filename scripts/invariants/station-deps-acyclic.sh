#!/usr/bin/env bash
# Invariant (p36): the station dependency graph in docs/ROADMAP.md resolves and has no cycle.
#
# Contract: skills/project-lifecycle/references/roadmap-format.md
#
# THREE RULES, and each one exists because a plausible implementation misses it:
#   * `depends-on:` must be present and non-empty. An absent value cannot be told apart from
#     "nobody filled this in", which is why the format requires a literal `none`.
#   * every named id must resolve to a declared block.
#   * the graph must be acyclic TRANSITIVELY, self-loops included. A checker that compares
#     adjacent pairs reports `a -> a` correctly and lets `a -> b -> c -> a` straight through;
#     the fixture set carries both cases separately for exactly that reason.
#
# WHY A REACHABILITY WALK AND NOT A PAIRWISE TEST. Cycle detection is done by walking each
# node's transitive successors and asking whether the node reappears. That is O(n^2) on a graph
# this size, which is free, and it cannot degrade into a pairwise check the way a "compare
# neighbours" implementation can.
#
# WHAT THIS DOES NOT CHECK: block shape, ids, binds-to, steps, the active list -- all
# station-id-integrity.sh. Rendering `blocked-by:` is one hop by contract; that is a RENDERER
# rule and this file says nothing about it. The two reaches differ on purpose.
#
# Envelope: bash + jq + coreutils. No python3 (CLAUDE.md).
set -euo pipefail

ROADMAP="${ROADMAP_PATH:-docs/ROADMAP.md}"
fail=0
bad() { printf '✗ %s\n' "$*" >&2; fail=1; }

[ -f "$ROADMAP" ] || { printf '✗ %s is not a regular file\n' "$ROADMAP" >&2; exit 1; }

# id<TAB>space-separated-deps  (deps empty means the key was absent entirely)
edges=$(
  awk '
    function flush() {
      if (id != "") printf "%s\t%s\t%d\n", id, deps, seen
      id = ""; deps = ""; seen = 0
    }
    index($0, "## 🧭") == 1 { inplan = 1; next }
    inplan && substr($0, 1, 3) == "## " { flush(); inplan = 0 }
    !inplan { next }
    /^### / { flush(); id = $0; sub(/^### [ \t]*/, "", id); gsub(/[ \t]+$/, "", id); next }
    id == "" { next }
    /^- depends-on:[ \t]*/ {
      seen = 1
      d = $0; sub(/^- depends-on:[ \t]*/, "", d); gsub(/[ \t]+$/, "", d)
      deps = d
      next
    }
    END { flush() }
  ' "$ROADMAP"
)

if [ -z "$edges" ]; then
  printf '⊘ no station-plan blocks in %s — no dependency graph to check\n' "$ROADMAP"
  exit 0
fi

all_ids=$(printf '%s\n' "$edges" | cut -f1)

# --- presence and resolution ---------------------------------------------------------------
while IFS=$'\t' read -r id deps seen; do
  [ -n "$id" ] || continue
  if [ "$seen" -ne 1 ]; then
    bad "block '$id': no depends-on line — an absent value cannot be told apart from an unfilled one; write 'none'"
    continue
  fi
  if [ -z "$deps" ]; then
    bad "block '$id': depends-on is empty — write the literal 'none'"
    continue
  fi
  [ "$deps" = "none" ] && continue
  for d in $deps; do
    if ! printf '%s\n' "$all_ids" | grep -Fxq -- "$d"; then
      bad "block '$id': depends-on names '$d', which no block declares"
    fi
  done
done <<EOF
$edges
EOF

# --- transitive cycle detection --------------------------------------------------------------
deps_of() {
  printf '%s\n' "$edges" | awk -F'\t' -v k="$1" '$1==k{print $2}'
}

for start in $all_ids; do
  frontier="$(deps_of "$start")"
  [ "$frontier" = "none" ] && continue
  seen_nodes=""
  depth=0
  while [ -n "$frontier" ]; do
    depth=$((depth + 1))
    if [ "$depth" -gt 64 ]; then
      bad "dependency walk from '$start' exceeded 64 hops — refusing to loop forever"
      break
    fi
    next=""
    for n in $frontier; do
      [ "$n" = "none" ] && continue
      if [ "$n" = "$start" ]; then
        bad "dependency cycle reaches '$start' from itself"
        frontier=""; next=""
        break 2
      fi
      case " $seen_nodes " in *" $n "*) continue ;; esac
      seen_nodes="$seen_nodes $n"
      d=$(deps_of "$n")
      [ "$d" = "none" ] && continue
      next="$next $d"
    done
    frontier="$next"
  done
done

n=$(printf '%s\n' "$all_ids" | grep -c '^..*$' || true)
if [ "$fail" -ne 0 ]; then
  printf '✗ station-deps-acyclic: FAILED\n' >&2
  exit 1
fi
printf '✓ station-deps-acyclic (%s node(s), no cycle, all edges resolve)\n' "$n"
