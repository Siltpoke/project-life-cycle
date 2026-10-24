#!/usr/bin/env bash
# Invariant: the lifecycle ledger does not look for evidence inside a store that is designed to
# delete.
#
# WHY. `docs/archive/.pre-images/` is an undo ring: `preimage_prune` removes the oldest slots with
# `rm -rf`, by design, every time a drain runs. For most of its life the stage registry named two
# roots inside it -- `.../files/docs/qa-log.d` and `.../files/docs/journal.d` -- so a stage could be
# scored `observed` on bytes the next drain was entitled to destroy. The phase that removed them
# measured the consequence first: ledger records cited the ring, some claimed no path outside it,
# and a prune destroyed the bytes those records cited.
#
# A record that points into the ring is not merely fragile. It reads exactly like a record pointing
# at an archive, so "this phase's Q&A survived" and "this phase's Q&A is one drain from gone" print
# the same word.
#
# WHAT IS CHECKED. Every `roots` entry of every `retro_evidence` source in the registry, against
# the ring's path. A root is refused if it names the pre-image store at all -- not only the two that
# were there, because the defect is the LOCATION, and a third root added later would be the same
# defect under a different name.
#
# NOT CHECKED: whether the remaining roots are the right ones, or whether a stage resolves at all.
# That is the ledger's own suite. This holds one boundary: evidence is read from files something
# else is not allowed to delete.
#
# Verdicts: 0 pass, 1 a root names the ring, 3 could not run (a check that could not run
# must never report as though it had).

set -uo pipefail

NAME="no-ledger-evidence-under-preimages"
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT" || { printf 'COULD-NOT-RUN %s: cannot cd to %s\n' "$NAME" "$ROOT" >&2; exit 3; }

REGISTRY="${PLC_STAGE_REGISTRY:-.claude/stage-registry.json}"
REGISTRY_MANIFEST="${PLC_CLOSE_GATE_MANIFEST:-.claude/close-gate.json}"

command -v jq >/dev/null 2>&1 || { printf 'COULD-NOT-RUN %s: jq is not installed\n' "$NAME" >&2; exit 3; }
[ -f "$REGISTRY" ] || { printf 'COULD-NOT-RUN %s: %s is missing\n' "$NAME" "$REGISTRY" >&2; exit 3; }
[ -f "$REGISTRY_MANIFEST" ] || { printf 'COULD-NOT-RUN %s: %s is missing, so the ring'"'"'s location is unknown\n' "$NAME" "$REGISTRY_MANIFEST" >&2; exit 3; }

# The store's path is assembled rather than spelled, for the same reason the sentinel guard
# assembles its pattern: this file would otherwise be a text match for the thing it refuses, and a
# checker that matches itself needs an exemption for its own name -- one more thing to go stale.
#
# THE ARCHIVE DIR IS READ, NOT SPELLED. The header claims a root is refused "if it names the
# pre-image store at all", and a hardcoded `docs/archive` is narrower than that sentence in two
# ways that both fail OPEN: a repo whose `retention.archive_dir` is something else has its ring
# unscanned, and this phase shipped `retention-drain.sh config archive_dir`, so there is no longer
# any reason to guess. Unreadable config is exit 3, never a pass -- the one thing a location check
# must not do is pass because it was looking in the wrong place.
AD="$(jq -r '.retention.archive_dir // "docs/archive"' "$REGISTRY_MANIFEST" 2>/dev/null)" || AD=""
case "$AD" in
  ''|null) printf 'COULD-NOT-RUN %s: cannot read retention.archive_dir out of %s\n' "$NAME" "$REGISTRY_MANIFEST" >&2; exit 3 ;;
esac
while :; do case "$AD" in */) AD="${AD%/}" ;; *) break ;; esac; done
case "$AD" in
  docs/*) : ;;
  *) printf 'COULD-NOT-RUN %s: retention.archive_dir is %s, which is outside docs/ -- the drain itself falls back in that case, and this check will not guess which path is live\n' "$NAME" "$AD" >&2; exit 3 ;;
esac
RING="$AD/.pre""-images"

# Non-vacuity first. A registry with no roots at all passes this check for the wrong reason, and
# "nothing to look at" and "nothing wrong" must not print the same thing.
TOTAL="$(jq -r '[.stages[]? | .retro_evidence[]? | .roots[]?] | length' "$REGISTRY" 2>/dev/null)" || TOTAL=""
case "$TOTAL" in ''|*[!0-9]*)
  printf 'COULD-NOT-RUN %s: cannot read roots out of %s\n' "$NAME" "$REGISTRY" >&2; exit 3 ;;
esac
if [ "$TOTAL" -eq 0 ]; then
  printf 'COULD-NOT-RUN %s: %s declares 0 evidence roots, so this check would pass by having nothing to read\n' "$NAME" "$REGISTRY" >&2
  exit 3
fi

OFFENDERS="$(jq -r --arg ring "$RING" '
  .stages[]? as $s
  | $s.retro_evidence[]? as $e
  | $e.roots[]?
  | sub("^\\./"; "")
  | select(startswith($ring))
  | "\($s.stage_id // "<no stage_id>")|\($e.kind // "<no kind>")|\(.)"
' "$REGISTRY" 2>/dev/null)" || {
  printf 'COULD-NOT-RUN %s: the roots query failed against %s\n' "$NAME" "$REGISTRY" >&2; exit 3; }

if [ -n "$OFFENDERS" ]; then
  printf 'FAIL %s: %s names the pre-image ring as an evidence root:\n' "$NAME" "$REGISTRY" >&2
  printf '%s\n' "$OFFENDERS" | while IFS='|' read -r stage kind root; do
    printf '    stage %s, kind %s: %s\n' "$stage" "$kind" "$root" >&2
  done
  printf '  -> That store is an undo ring; a prune deletes its oldest slots by design. A stage\n' >&2
  printf '     scored from it reads identically to one scored from an archive, so "survived" and\n' >&2
  printf '     "one drain from gone" print the same word. Point the root at a durable file, or\n' >&2
  printf '     declare the stage not-recoverable and say so.\n' >&2
  exit 1
fi

printf 'PASS %s: none of the %s declared evidence roots in %s names the pre-image ring. Scope: location only -- this says nothing about whether the remaining roots resolve.\n' \
  "$NAME" "$TOTAL" "$REGISTRY"
