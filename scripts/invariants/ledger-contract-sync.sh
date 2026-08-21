#!/usr/bin/env bash
# Invariant: the divergence ledger in context-floor.sh and the contract suite's known-defect
# rows describe the same set of ids, and agree about which of them are still preserved.
#
# WHY THIS EXISTS. The ledger is the strongest naming site for a preserved or chosen
# divergence. Nothing
# checked it. An id could be named in the ledger with no executable row behind it, or have a row
# and quietly drop out of the ledger, and both drift in silence. "Named" was a custom; this makes
# it a property.
#
# WHAT IS CHECKED, precisely, because the obvious rule is slightly different.
# The obvious rule is "every id in the ledger appears in the contract suite as a live or XFAIL row".
# The XFAIL half is machine-readable -- the id is an argument to `xfail`/`xpass`. The LIVE half
# is not: a graduated id appears only in prose ("<id> -- FIXED, graduated to live rows"), and no
# grep can tell a live row from a paragraph about one. Rather than claim a check this cannot
# perform, the ledger's own FIXED marker is used as the pivot, which turns out to be STRONGER
# than that rule and fully checkable in both directions:
#
#   INV-1  a ledger id NOT marked FIXED must have an `xfail`/`xpass` row  (preserved => executable)
#   INV-2  a ledger id marked FIXED must NOT have one                     (graduated => not XFAIL)
#   INV-3  every `xfail`/`xpass` id must be named in the ledger           (row => named)
#
# INV-2 inverts the naive form, where writing the check as
# "appears as XFAIL" would turn a graduation into a gate failure. Inverting it makes graduation
# the thing being verified instead -- a phase that flips a row to live and forgets to update the
# ledger now fails here.
#
# WHAT THIS IS NOT. It does not verify that a graduated id has a live row; nothing greppable
# distinguishes one. It verifies that it is no longer an XFAIL one. Closing that gap needs a
# declared per-row marker in the suite, which is a convention change, not an invariant.
#
# The ledger span is delimited by two BARE marker lines, matched as whole lines. That anchoring
# is load-bearing: under substring matching, the ledger's own explanatory
# comment -- which must name the markers to explain them -- closes the range on itself, yielding
# an EMPTY id set. An empty set compares equal to an empty set, so the invariant passed while
# checking nothing.
#
# Envelope: bash + grep + sed + sort + comm. No python3.
set -uo pipefail

HOOK="skills/project-lifecycle/hooks/context-floor.sh"
SUITE="skills/project-lifecycle/hooks/test-context-floor-contract.sh"
rc=0

for f in "$HOOK" "$SUITE"; do
  [ -r "$f" ] || { echo "FAIL ledger-contract-sync: $f missing or unreadable"; exit 1; }
done

LEDGER="$(awk '/^#LEDGER-BEGIN$/{f=1;next} /^#LEDGER-END$/{f=0} f' "$HOOK")"

# An empty span is a FAILURE, not a vacuous pass. This is the exact state the marker anchoring
# above was introduced to prevent, and it must be impossible to reach it silently.
if [ -z "$(printf '%s' "$LEDGER" | tr -d '[:space:]')" ]; then
  echo "FAIL ledger-contract-sync: the ledger span is empty -- are the #LEDGER-BEGIN / #LEDGER-END"
  echo "     marker lines present in $HOOK, each alone on its own line?"
  exit 1
fi

# Ledger ids, split by whether their line carries FIXED.
LED_ALL="$(printf '%s\n' "$LEDGER" | grep -oE 'B[0-9]+' | sort -u)"
LED_FIXED="$(printf '%s\n' "$LEDGER" | grep -E 'FIXED' | grep -oE 'B[0-9]+' | sort -u)"
LED_OPEN="$(comm -23 <(printf '%s\n' "$LED_ALL") <(printf '%s\n' "$LED_FIXED"))"

# Suite ids that carry an executable known-defect row: the second argument of xfail/xpass.
# Both verbs, because one row prints as XFAIL and the same row prints as XPASS once it passes --
# reading only `xfail` would make the check blind at exactly the moment a defect gets fixed.
# The id is the SECOND argument, and only the second: pulling every `B[0-9]+` out of the matched
# text also harvested ids out of the row's NAME, which reads like a row that carries an id it does
# not carry: a row named `<a>-extra` whose id argument is `<b>` yielded both, so
# INV-2 accused <a> of a row that does not exist. Anchored capture
# instead of a second grep.
ROWS="$(grep -oE '(xfail|xpass) "[^"]*" "B[0-9]+"' "$SUITE" | sed -E 's/.*"(B[0-9]+)"$/\1/' | sort -u)"

# NO ROWS IS ONLY A FAILURE IF THE LEDGER STILL EXPECTS SOME. The guard used to fail on an empty
# row set unconditionally, to stop a broken extractor from passing vacuously -- and then the suite
# legitimately reached zero: every ledger entry graduated to FIXED and
# the last decorative row was deleted. From that commit on this invariant failed on a CORRECT state,
# which would have blocked the close gate for doing exactly what the ledger asks.
#
# The distinction the original guard was reaching for is available directly: a broken extractor shows
# up as "the ledger names ids that are still preserved, yet no row asserts any of them" -- which is
# INV-1, and INV-1 keeps its teeth here. Only when EVERY ledger id is marked FIXED is an empty row
# set the correct answer, and then saying so is not vacuous, it is the finished state.
# THE EXTRACTOR IS CROSS-CHECKED BY A SECOND, DIFFERENT READER, because "no rows" now has a legitimate
# meaning and a broken extractor produces the same string. The gap:
# with every ledger id marked FIXED, a suite that HAS an `xfail` row for a FIXED id is exactly what
# INV-2 exists to catch -- and a broken extractor returning empty makes INV-2 compare an empty set and
# pass. So the presence of rows is established independently of the regex that parses them: count the
# call SITES, and disagree loudly if one reader sees rows and the other sees none.
# THE SECOND NAMING SITE. The ledger above is a PORT ledger -- its own opening line
# is "Behaviour was deliberately UNCHANGED BY THE PORT" -- and every id in it is a defect the bash
# port inherited from the pinned python and chose not to fix. A later defect is not one of those: it can be a
# live defect in code written well after the port, and editing
# `context-floor.sh` to name it is off-limits, because that byte-identity is the whole reason its widening is a PATH
# shim rather than a patched copy, and any edit there -- comments included -- restales every
# divergence record. So "every row must be NAMED" collides head-on with "this file
# does not change".
#
# Resolved by splitting the register, not by dropping either requirement. Non-port known defects
# are declared in the SUITE, between bare `#NONPORT-BEGIN` / `#NONPORT-END` marker lines, beside
# the rows that assert them. The same whole-line anchoring as the ledger, and for the same measured
# reason: a substring match lets the explanatory comment that must name the markers close the range
# on itself, yielding an empty set that compares equal to an empty set.
#
# THIS IS A SECOND REGISTER, NOT AN ESCAPE HATCH, and that is enforced rather than promised:
# INV-4 fails a declared id with no row (the mirror of INV-1), and INV-5 fails an id declared in
# both, so the FIXED pivot that governs INV-1/INV-2 can never be ambiguous about which list owns
# an id. A missing block is simply an empty set -- adopters with no non-port rows declare nothing.
# THE ID MUST HEAD ITS OWN ENTRY LINE, not merely appear somewhere in the block. Pulling every
# `B[0-9]+` out of the span makes a PROSE MENTION count as a declaration -- for an entry that says
# "asserted by `<id>-case`", a mutant that renamed the entry head still left the id "declared" and
# INV-3 stayed green. This is the same defect the
# ROWS extractor above was already hardened against (ids harvested out of a row's NAME), reappearing
# in the new register because the new register copied the ledger's loose form instead of the fixed one.
NONPORT="$(awk '/^#NONPORT-BEGIN$/{f=1;next} /^#NONPORT-END$/{f=0} f' "$SUITE" \
            | grep -oE '^#[[:space:]]+B[0-9]+[[:space:]]' | grep -oE 'B[0-9]+' | sort -u)"
NAMED="$(printf '%s\n%s\n' "$LED_ALL" "$NONPORT" | grep -E '^B[0-9]+$' | sort -u)"

SITES="$(grep -cE '^[[:space:]]*(xfail|xpass)[[:space:]]+"' "$SUITE" || true)"
if [ "$SITES" -gt 0 ] && [ -z "$ROWS" ]; then
  echo "FAIL ledger-contract-sync: $SITES xfail/xpass call site(s) exist in $SUITE, but the id"
  echo "     extractor matched none of them -- the extractor is broken, and every check below would"
  echo "     be comparing an empty set"
  exit 1
fi

if [ -z "$ROWS" ] && [ -n "$LED_OPEN" ]; then
  echo "FAIL ledger-contract-sync: no xfail/xpass rows found in $SUITE, while the ledger still names"
  echo "     ids that are NOT marked FIXED -- the extractor matched nothing, which would make every"
  echo "     check below vacuously true"
  printf '     still-preserved: %s\n' $LED_OPEN
  exit 1
fi
if [ -z "$ROWS" ]; then
  echo "ok ledger-contract-sync: no xfail/xpass rows, and every ledger id is marked FIXED"
fi

report() { # $1 label, $2 offending ids, $3 explanation
  if [ -n "$2" ]; then
    echo "FAIL ledger-contract-sync $1: $3"
    printf '     %s\n' $2
    rc=1
  else
    echo "ok ledger-contract-sync $1"
  fi
}

miss1="$(comm -23 <(printf '%s\n' "$LED_OPEN") <(printf '%s\n' "$ROWS"))"
report "INV-1" "$miss1" "named in the ledger as still-preserved, but no xfail/xpass row asserts it"

bad2="$(comm -12 <(printf '%s\n' "$LED_FIXED") <(printf '%s\n' "$ROWS"))"
report "INV-2" "$bad2" "marked FIXED in the ledger, yet still carried by an xfail/xpass row"

miss3="$(comm -13 <(printf '%s\n' "$NAMED") <(printf '%s\n' "$ROWS"))"
report "INV-3" "$miss3" "carried by an xfail/xpass row, but named in neither the ledger nor the suite's non-port register"

miss4="$(comm -23 <(printf '%s\n' "$NONPORT") <(printf '%s\n' "$ROWS"))"
report "INV-4" "$miss4" "declared in the suite's non-port register, but no xfail/xpass row asserts it"

bad5="$(comm -12 <(printf '%s\n' "$LED_ALL") <(printf '%s\n' "$NONPORT"))"
report "INV-5" "$bad5" "declared in BOTH the port ledger and the non-port register -- one home each, or the FIXED pivot governing it is ambiguous"

exit "$rc"
