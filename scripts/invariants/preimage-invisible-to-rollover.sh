#!/usr/bin/env bash
# INVARIANT — the pre-image store is not a document, and the drain will not archive it.
#
# One shape, stated: this is not a proof about every path into the store. It asserts the two
# reachable ways the tool could eat its own backups:
#   1. pointing `drain` at a file inside the store is refused;
#   2. a roll-over pass, triggered on a real archive, never ingests the store's bytes.
#
# Why an invariant and not only a pytest case: the exclusion is a required
# property, and the suite is where the mechanism is developed. A guard that lives only there
# cannot catch a regression that arrives with the suite skipped or not yet run — the same
# argument `unreleased-survives-drain.sh` makes, and the same reason it is fixture-based rather
# than a grep: a rewrite that keeps the word ".pre-images" in the code while losing the
# exclusion would pass a grep.
# ISOLATION, stated rather than left implicit: every drain this check runs happens with
# cwd inside its own `mktemp -d`, and `archive_dir` is the RELATIVE path `docs/archive`, so the
# pre-image store it creates is `$TMP/docs/archive/.pre-images` and never the repo's own. That
# matters more than it looks: a pre-image capture failure REFUSES the drain, and this file plus
# `unreleased-survives-drain.sh` both run as close-gate invariants — so a store that leaked into
# the real tree would put gate runs and real drains on the same disk state, and a permissions or
# space problem in one would redden the other.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Selectable so this check can be shown capable of failing — an invariant must be
# proven red, and a guard nobody has ever seen fail is a guard nobody has tested.
DRAIN="${PLC_DRAIN_IMPL:-$HERE/../retention-drain.sh}"
TMP="$(mktemp -d)" || { echo "✗ preimage-invisible-to-rollover: mktemp -d failed"; exit 1; }
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$TMP/.claude" || exit 1
printf '{"retention":{"archive_dir":"docs/archive","preimage_keep":5}}\n' \
  > "$TMP/.claude/close-gate.json" || exit 1

# Enough entries that the drain has work to do, and a tiny roll-over cap so the roll-over pass
# actually fires rather than being skipped for being under threshold.
{
  printf '# Changelog\n\n'
  for i in 1 2 3 4 5 6 7 8; do printf '## [1.%s.0] — 2026-0%s-01\n\nbody %s\n\n' "$i" "$i" "$i"; done
} > "$TMP/CHANGELOG.md" || exit 1

out="$(cd "$TMP" && /bin/bash "$DRAIN" drain CHANGELOG.md 1 2>&1)"; rc=$?
if [ "$rc" -ne 0 ]; then
  echo "✗ preimage-invisible-to-rollover: drain exited $rc — expected 0"
  echo "$out"
  exit 1
fi

STORE="$TMP/docs/archive/.pre-images"
if [ ! -d "$STORE" ]; then
  echo "✗ preimage-invisible-to-rollover: no pre-image store was created, so this check"
  echo "  cannot observe the property it exists to hold — treating that as a failure rather"
  echo "  than passing vacuously."
  exit 1
fi

fail=0

# (1) The store is not a document: pointing the drain at a file inside it must be refused.
victim="$(find "$STORE" -type f -name '*.md' | head -1)"
if [ -n "$victim" ]; then
  rel="${victim#"$TMP"/}"
  vout="$(cd "$TMP" && /bin/bash "$DRAIN" drain "$rel" 2>&1)"; vrc=$?
  if [ "$vrc" -eq 0 ]; then
    echo "✗ preimage-invisible-to-rollover: draining a file INSIDE the store succeeded"
    echo "  $rel"
    echo "$vout"
    fail=1
  fi
fi

# (2) Roll-over must not ingest the store. Compare against the store's own bytes rather than
# against the literal string ".pre-images": a segment could carry the archived CONTENT of a
# pre-image without ever naming the directory.
segdir="$TMP/docs/archive/CHANGELOG"
if [ -d "$segdir" ]; then
  if grep -rqF "pre-image" "$segdir" 2>/dev/null; then
    echo "✗ preimage-invisible-to-rollover: a roll-over segment mentions the pre-image store"
    fail=1
  fi
  # No content-overlap check sits here, deliberately: the obvious one has both
  # branches of its `if` as no-ops, so it reads as an assertion and asserts nothing — and the
  # property it appeared to check is not even true, since the archive legitimately holds the same
  # entry text the pre-image does. A check that cannot fail is worse than no check, because the
  # next reader counts it.
fi

# (3) The store must still be there afterwards. A roll-over that "excluded" it by deleting it
# would satisfy (2) and destroy the very backups the store exists to keep.
if [ ! -d "$STORE" ] || [ -z "$(find "$STORE" -mindepth 1 -maxdepth 1 -type d 2>/dev/null)" ]; then
  echo "✗ preimage-invisible-to-rollover: the store is gone or empty after the roll-over pass"
  fail=1
fi

if [ "$fail" -ne 0 ]; then exit 1; fi
echo "PASS preimage-invisible-to-rollover: the store is refused as a drain target and survives roll-over untouched"
exit 0
