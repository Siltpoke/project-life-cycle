#!/usr/bin/env bash
# Invariant: a mainline row opens with something a person can read, and the wall can
# only get smaller.
#
# Contract: skills/project-lifecycle/references/roadmap-format.md
#
# THE COMPLAINT THIS ANSWERS is not a rendering bug. Twice, on first opening the progress page,
# the reaction was the same two words: too long, unreadable. Both times the text was produced by
# THIS repo's format. A consumer is forbidden to summarise it (a view derived from a
# hand-maintained copy drifts -- measured here, the Quest Log track died of it), so a renderer's
# only honest options were to show the wall or hide it behind a click. Both were tried; the
# reader still bounced.
#
# WHAT IS MEASURED, and it is why this is a LEAD rule rather than a length cap. A `what` cell on
# this repo has median 953 characters, so a cap deletes reasoning that entries exist to preserve
# -- the format rules reject that explicitly. But the cell is not formless: it already OPENS with a
# sentence, median 78 characters, p75 136. The lead exists. Nothing marked where it ended, so
# nothing downstream could show it alone. This rule bounds the lead and leaves the detail
# untouched and unbounded.
#
# A RATCHET, NOT AN EXEMPTION LIST. In display columns, 49 of 52 name cells and 45 of 52 leads
# exceed the bound TODAY. A rule that reds on 45 rows the day it lands gets switched off. So
# every row is pinned at its current width in `.claude/roadmap-lead-baseline.tsv`, and:
#
#   * a PINNED row may stay exactly as long as it is -- and may not grow;
#   * a row that is NOT pinned -- new, or renamed, which is the same as having been edited --
#     must meet the bound outright.
#
# The debt is therefore counted rather than hidden, and it can only go down. That count IS the
# deliverable: before this, nothing in the repository could say how bad the wall was.
#
# WHAT THIS DOES NOT DO, named rather than implied:
#   * It does not make any existing row readable. It stops the wall growing and makes it
#     countable. Shortening the 45 is human work this check cannot do.
#   * It says nothing about `docs/BACKLOG.md`, whose entries are long ON PURPOSE -- they are
#     where the detail is supposed to live.
#   * The bound is a CHOICE (see the contract). It is the same 60 columns p36 uses for a step
#     line, for the same reason: an 80-column terminal.
#
# Envelope: bash + jq + awk + cksum. No python3 (CLAUDE.md).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROADMAP="${ROADMAP_PATH:-docs/ROADMAP.md}"
LIBDIR="${EAW_LIB_DIR:-$HERE/../lib}"
BASELINE="${ROADMAP_LEAD_BASELINE:-.claude/roadmap-lead-baseline.tsv}"
MAX_COLS="${MAX_LEAD_COLS:-60}"

fail=0
bad() { printf '✗ %s\n' "$*" >&2; fail=1; }

[ -f "$ROADMAP" ] || { printf '✗ %s is not a regular file\n' "$ROADMAP" >&2; exit 1; }
[ -f "$LIBDIR/eaw-ranges.jq" ] || { printf '✗ %s/eaw-ranges.jq missing\n' "$LIBDIR" >&2; exit 1; }
[ -r "$LIBDIR/roadmap-lead.sh" ] || { printf '✗ %s/roadmap-lead.sh missing — the guard and the baseline generator must measure with ONE ruler\n' "$LIBDIR" >&2; exit 1; }
# shellcheck disable=SC1090
. "$LIBDIR/roadmap-lead.sh"
command -v roadmap_lead_rows >/dev/null 2>&1 \
  || { printf '✗ roadmap-lead.sh did not define roadmap_lead_rows\n' >&2; exit 1; }

now="$(roadmap_lead_rows "$ROADMAP" "$LIBDIR")"
nrows="$(printf '%s\n' "$now" | grep -c '^..*$' || true)"

# An empty scan is stated, never passed: zero rows and "every row is fine" are different
# answers, and this repo has filed the collapse of that distinction twice.
if [ "$nrows" -eq 0 ]; then
  printf '⊘ roadmap-lead-length: no mainline rows parsed in %s — 0 rows checked, and that is stated rather than passed\n' "$ROADMAP"
  exit 0
fi

pinned_file="$(mktemp)"
trap 'rm -f "$pinned_file"' EXIT
if [ -r "$BASELINE" ]; then
  grep -v '^#' "$BASELINE" > "$pinned_file" || true
else
  : > "$pinned_file"
fi
npinned="$(grep -c '^..*$' "$pinned_file" || true)"

over_bound=0
unpinned=0
while IFS="$(printf '\t')" read -r key ncols lcols pref; do
  [ -n "${key:-}" ] || continue
  [ "$ncols" -gt "$MAX_COLS" ] && over_bound=$((over_bound + 1))
  [ "$lcols" -gt "$MAX_COLS" ] && over_bound=$((over_bound + 1))

  pin="$(awk -F'\t' -v k="$key" '$1 == k { print $2 "\t" $3; exit }' "$pinned_file")"
  if [ -z "$pin" ]; then
    unpinned=$((unpinned + 1))
    if [ "$ncols" -gt "$MAX_COLS" ]; then
      bad "$pref… — name cell is $ncols display columns, the bound is $MAX_COLS. This row is new or was renamed, so the bound applies: open with a short line and let the detail follow it"
    fi
    if [ "$lcols" -gt "$MAX_COLS" ]; then
      bad "$pref… — the lead of its \`what\` cell is $lcols display columns, the bound is $MAX_COLS. This row is new or was renamed, so the bound applies. End the lead with 。 or <br> and put the rest after it; the detail is not capped"
    fi
    continue
  fi

  # ONLY THE LEAD IS RATCHETED HERE, and the missing half is missing on purpose. A name
  # ratchet was written first and a mutant that disabled it SURVIVED -- because it is
  # unreachable by construction: the pin is keyed on the name cell, so any change to the name
  # produces a different key, the row stops being pinned, and it meets the bound outright on
  # the branch above. Dead code that looks like a guard is worse than no code; the property it
  # was reaching for is asserted in test_a_pinned_rows_name_cannot_change_while_pinned.
  pl="$(printf '%s' "$pin" | cut -f2)"
  if [ "$lcols" -gt "$pl" ]; then
    bad "$pref… — the lead of its \`what\` cell grew from $pl to $lcols display columns. A pinned row may stay as long as it is; it may not get longer"
  fi
done <<EOF
$now
EOF

if [ "$fail" -ne 0 ]; then
  printf '✗ roadmap-lead-length: FAILED\n' >&2
  exit 1
fi
printf '✓ roadmap-lead-length (%s row(s); %s pinned, %s unpinned and within the %s-column bound; %s measurement(s) still over the bound and pinned, which can only go down)\n' \
  "$nrows" "$npinned" "$unpinned" "$MAX_COLS" "$over_bound"
