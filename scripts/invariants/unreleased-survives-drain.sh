#!/usr/bin/env bash
# INVARIANT — a drain never archives '## [Unreleased]', on a declared newest-first document.
# One shape, stated: this is not a proof about every ordering or every position.
#
# This has to be checkable OUTSIDE the pytest suite: the suite is where the
# mechanism is developed, and a guard that lives only there cannot catch a regression that
# arrives with the suite disabled, skipped, or not yet run. This runs the REAL script against a
# throwaway fixture and asserts the heading is still in the hot file and absent from the archive.
#
# Deliberately fixture-based, not a grep over the source: the property is behavioural. A future
# rewrite that keeps the word "[Unreleased]" in the code while losing the pin would pass a grep.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# The implementation is selectable so this check can be shown capable of failing — an
# invariant must be proven red, and a guard nobody has ever seen fail is a guard nobody has tested.
DRAIN="${PLC_DRAIN_IMPL:-$HERE/../retention-drain.sh}"
TMP="$(mktemp -d)" || { echo "✗ unreleased-survives-drain: mktemp -d failed"; exit 1; }
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$TMP/.claude" || exit 1
printf '{"retention":{"archive_dir":"docs/archive","order":{"CHANGELOG.md":"newest-first"}}}\n' \
  > "$TMP/.claude/close-gate.json" || exit 1

# '[Unreleased]' sits INSIDE THE EVICTED REGION, not at the top. A fixture with it first is
# green with the pin deleted and green with the eviction direction inverted — it survives on
# position alone, so such a check tests "the first heading of a newest-first file is kept" and
# says nothing about pinning. Here it is the second-to-last heading: on a newest-first document
# with 7 entries the last 4 are evicted, so only the pin can save it.
{
  printf '# Changelog\n\n'
  for i in 6 5 4 3 2; do printf '## [1.%s.0] — 2026-0%s-01\n\nbody %s\n\n' "$i" "$i" "$i"; done
  printf '## [Unreleased]\n\npending\n\n'
  printf '## [1.1.0] — 2026-01-01\n\nbody 1\n\n'
} > "$TMP/CHANGELOG.md" || exit 1

out="$(cd "$TMP" && /bin/bash "$DRAIN" drain CHANGELOG.md 2>&1)"; rc=$?   # named interpreter
if [ "$rc" -ne 0 ]; then
  echo "✗ unreleased-survives-drain: drain exited $rc — expected 0"
  echo "$out"
  exit 1
fi
if ! grep -qF '## [Unreleased]' "$TMP/CHANGELOG.md"; then
  echo "✗ unreleased-survives-drain: '## [Unreleased]' was evicted from the hot file"
  exit 1
fi
if grep -qF '## [Unreleased]' "$TMP/docs/archive/CHANGELOG-archive.md" 2>/dev/null; then
  echo "✗ unreleased-survives-drain: '## [Unreleased]' reached the archive"
  exit 1
fi
# Assert the WHOLE surviving set, not just the one heading. A check that only asks "is
# [Unreleased] still there" is green under an inverted eviction direction,
# because the pin happens to rescue that one heading either way.
kept="$(awk '/^## / && $0 !~ /Index[[:space:]]*$/ { sub(/^## /, ""); print }' "$TMP/CHANGELOG.md" | tr '\n' '|')"
want='[1.6.0] — 2026-06-01|[1.5.0] — 2026-05-01|[1.4.0] — 2026-04-01|[Unreleased]|'
if [ "$kept" != "$want" ]; then
  echo "✗ unreleased-survives-drain: wrong entries survived"
  echo "    want: $want"
  echo "    got:  $kept"
  exit 1
fi
echo "ok unreleased-survives-drain: '[Unreleased]' stays in the hot file and never reaches the archive"
exit 0
