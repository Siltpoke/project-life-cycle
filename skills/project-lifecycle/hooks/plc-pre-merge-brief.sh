#!/usr/bin/env bash
# skills/project-lifecycle/hooks/plc-pre-merge-brief.sh
#
# Validate one pre-merge brief against references/pre-merge-brief.md.
#
# COUNTING HEADINGS IS NOT ENOUGH, and that is the whole design of this checker. A brief can carry
# four headings where the fourth is a pointer to something else -- which is neither the fourth item
# nor four items. So each item is identified by its own
# marker and checked for CONTENT, not for presence of a title.
#
# EVERY RULE FAILS WITH ITS OWN MESSAGE. "Malformed brief" tells the author nothing.
#
# Envelope: bash only.
#
# Exit codes: 0 valid, 1 a rule failed (each named), 2 bad invocation.
set -euo pipefail

die() { printf '%s\n' "$*" >&2; exit 2; }

[ $# -eq 1 ] || die "usage: plc-pre-merge-brief.sh <brief.md>"
body="$1"
[ -r "$body" ] || die "cannot read $body"

fail=0
say() { printf 'FAIL %s\n' "$*" >&2; fail=1; }

text="$(/bin/cat "$body")"
flat="$(printf '%s' "$text" | tr '\n' ' ')"

# --- the disclaimer, byte for byte ---------------------------------------------------------------
# Matched exactly so a paraphrase reds. A softened version of this sentence is worse than none: it
# still reads as reassurance while no longer saying the thing.
DISCLAIMER='It is NOT someone having read the code.'
case "$flat" in
  *"$DISCLAIMER"*) ;;
  *) say "the disclaimer is missing or paraphrased -- it must read exactly: $DISCLAIMER" ;;
esac

# --- exactly four items, identified by marker ----------------------------------------------------
ITEMS="what-i-did unchecked-criteria skipped-steps long-term"
n_found=0
for id in $ITEMS; do
  if ! /usr/bin/grep -q "<!-- plc-brief-item: $id -->" "$body"; then
    say "item '$id' is absent -- the brief carries exactly four items and this is not one of them"
  else
    n_found=$((n_found + 1))
  fi
done
n_markers=$(/usr/bin/grep -c '<!-- plc-brief-item: ' "$body" || true)
if [ "$n_markers" -gt 4 ]; then
  say "the brief carries $n_markers items; it carries exactly four"
fi

# --- EVERY item has a body, not just item 2 ------------------------------------------------------
# Checking emptiness for `unchecked-criteria`
# alone would let a brief whose "what I did", "what was skipped" and "what would stick around" sections
# were all bare titles pass shape validation. Item 2 keeps its own message because its empty case
# has a REQUIRED WORD -- "none", not blank -- and that distinction is the most-quoted line in the
# reference document.
#
# THE HEADING IS NOT CONTENT, and skipping it is the whole assertion. Kept, it would let
# an item stripped down to its own title read as non-empty: a
# fixture with the body deleted would be reported as a valid brief.
for id in $ITEMS; do
  /usr/bin/grep -q "<!-- plc-brief-item: $id -->" "$body" || continue
  section="$(awk -v want="$id" '
    index($0, "<!-- plc-brief-item: " want " -->") > 0 { inblk = 1; next }
    inblk && /<!-- plc-brief-item: /                    { inblk = 0 }
    inblk && /^#/                                        { next }
    inblk                                                { print }
  ' "$body")"
  if [ -z "$(printf '%s' "$section" | tr -d '[:space:]')" ]; then
    if [ "$id" = "unchecked-criteria" ]; then
      say "item 2 (unchecked criteria) has no body -- an empty set is written as 'none', never left blank"
    else
      say "item '$id' has a heading and no body -- a title is not an item"
    fi
  fi
done

# --- the two counts, separately -------------------------------------------------------------------
# The phase-level count is not just present, it is TWO. Matching
# any integer would let a brief claiming nine phase-level stops satisfy the check
# that exists to carry `fast`'s central claim. Two is the design (the start-of-work screen, and the
# merge), so two is what the check says.
pl="$(sed -n 's/^[[:space:]]*-[[:space:]]*phase-level:[[:space:]]*\([0-9][0-9]*\).*/\1/p' "$body" | head -1)"
if [ -z "$pl" ]; then
  say "the phase-level stop count is missing"
elif [ "$pl" != 2 ]; then
  say "the phase-level stop count is $pl -- fast stops exactly twice (the start-of-work screen, and you clicking merge)"
fi
if ! /usr/bin/grep -qE '^[[:space:]]*-[[:space:]]*intent gate, one tap per request:[[:space:]]*[0-9]+' "$body"; then
  say "the intent-gate tap count is missing -- folding it away makes 'only two stops' true by accounting"
fi

# --- the mode line ---------------------------------------------------------------------------------
/usr/bin/grep -qE '^[[:space:]]*mode:[[:space:]]*[A-Za-z0-9._-]+' "$body" \
  || say "the brief does not state which mode this phase ran in"

# --- the guidance line -------------------------------------------------------------------------------
if ! /usr/bin/grep -q '<!-- plc-brief-guidance -->' "$body"; then
  say "the guidance line is absent -- when there is nothing to flag it says so, it is never omitted"
else
  guide="$(awk '
    /<!-- plc-brief-guidance -->/  { inblk = 1; next }
    inblk && /<!-- plc-brief-item: / { inblk = 0 }
    inblk                            { print }
  ' "$body")"
  # Three parts per flagged thing: a file:line-range, a "before:" excerpt, a reason. Checked only
  # for entries that exist -- an empty guidance line is legitimate and says "nothing in particular".
  n_entries=$(printf '%s\n' "$guide" | /usr/bin/grep -cE '^[[:space:]]*-[[:space:]]' || true)
  if [ "$n_entries" -gt 3 ]; then
    say "the guidance line flags $n_entries things; it flags at most three"
  fi
  if [ "$n_entries" = 0 ]; then
    printf '%s' "$guide" | /usr/bin/grep -q 'nothing in particular' \
      || say "the guidance line flags nothing and does not say so"
  fi

  # EACH FLAGGED THING CARRIES THREE PARTS, each checked -- otherwise
  # `- look here` would pass as a merge-risk receiver. The three parts are the ones
  # the criterion spells out, and the second is the one a non-technical reader actually uses: they
  # cannot tell whether new code is right, but they can tell whether old and new are the same KIND
  # of thing.
  #
  # SCOPE, stated: this checks each part is PRESENT and shaped like itself. It cannot check the line
  # range points at a real change, that the excerpt is the real prior text, or that the reason is a
  # good one. It raises `- look here` from acceptable to rejected; it does not make a flag correct.
  entry_no=0
  while IFS= read -r line; do
    case "$line" in
      [[:space:]]*-[[:space:]]*|-[[:space:]]*) ;;
      *) continue ;;
    esac
    entry_no=$((entry_no + 1))
    # The entry plus everything up to the next bullet.
    chunk="$(awk -v n="$entry_no" '
      /<!-- plc-brief-guidance -->/  { inblk = 1; next }
      inblk && /<!-- plc-brief-item: / { exit }
      inblk && /^[[:space:]]*-[[:space:]]/ { seen++ }
      inblk && seen == n              { print }
    ' "$body")"
    printf '%s' "$chunk" | /usr/bin/grep -qE '[A-Za-z0-9_./-]+\.[A-Za-z0-9]+:[0-9]+(-[0-9]+)?' \
      || say "guidance entry $entry_no has no file:line-range -- there is nowhere to click"
    printf '%s' "$chunk" | /usr/bin/grep -qiE '^[[:space:]]*before:' \
      || say "guidance entry $entry_no does not show the lines as they were before"
    # A reason is a sentence, not the locator: at least one line that is neither the bullet's own
    # first line nor part of the `before:` excerpt.
    printf '%s' "$chunk" | awk '
      /^[[:space:]]*-[[:space:]]/ { next }
      /^[[:space:]]*before:/      { inpre = 1; next }
      inpre && /^[[:space:]]{6,}/ { next }
      /^[[:space:]]*$/            { next }
      { found = 1 }
      END { exit found ? 0 : 1 }
    ' || say "guidance entry $entry_no gives no reason it is worth a look"
  done <<<"$guide"
fi

# --- the smoke checklist is PRESENT, below the items, and does not block ---------------------------
# ABSENCE IS A FAILURE. Running these checks only inside `if grep -q` would let a brief
# that omits the checklist entirely pass -- "a fast PR can omit the
# required Track A checklist". The checklist exists because automated smoke cannot see what a real
# browser shows a real person, so leaving it out is exactly the gap it was added to cover.
if ! /usr/bin/grep -q 'Manual smoke checklist' "$body"; then
  say "the manual smoke checklist is absent -- automated smoke cannot see what a browser shows a person"
else
  last_item=$(/usr/bin/grep -n '<!-- plc-brief-item: ' "$body" | /usr/bin/tail -1 | cut -d: -f1)
  smoke=$(/usr/bin/grep -n 'Manual smoke checklist' "$body" | /usr/bin/head -1 | cut -d: -f1)
  [ "$smoke" -gt "$last_item" ] \
    || say "the smoke checklist appears above the four items -- it belongs below them"
  /usr/bin/grep -q 'does not block' "$body" \
    || say "the smoke checklist does not say it is non-blocking"
fi

[ "$fail" = 0 ] || exit 1
printf 'ok  pre-merge brief: guidance line, %d items, both counts, mode line, disclaimer verbatim\n' "$n_found"
