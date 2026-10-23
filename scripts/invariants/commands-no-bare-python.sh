#!/bin/bash
# commands-no-bare-python -- every Python INVOCATION in a command doc goes through the
# resolver, or carries a written exemption.
#
# WHY. On a default Windows install `python3` is an App Execution Alias: a stub that is not
# an interpreter, and one of its two reported shapes exits 0 printing nothing. A command doc
# that tells the model to run `python3 something.py` therefore has a silent-failure path on
# the single platform this repo has never run on. Every such site goes through
# `scripts/plc-python.sh`; this check is what stops a new one appearing, and what stops one
# of them being reverted.
#
# SHAPE CANNOT DO THIS JOB, AND THAT WAS MEASURED, NOT ASSUMED. `commands/release.md` once
# carried `python3 -c "..."` (a real instruction) and `commands/cognition-distill.md`
# carries `python3 scripts/cognition_log.py` (prose naming a module) -- the SAME shape, a
# numbered-list line with inline-backtick code. A fence test classifies both as prose. So the
# rule below is not "looks like prose"; it is the repo's existing explicit-exemption pattern,
# the one `gate-jq-only-envelope.sh` already uses, where every exemption costs a written
# reason.
#
# THE ONE DISCRIMINATOR THIS CHECK DOES USE, stated so it is not mistaken for the above: a
# bare mention -- `python3` immediately closed by a backtick, with no argument after it -- is
# not an invocation and is not flagged. That distinction is real and mechanical, and it is
# what lets a doc explain the hazard in prose. It does NOT separate the two cases in the
# paragraph above, which is exactly why the exemption list still exists and still has an
# entry in it.
#
# THE ANCHOR IS THE LINE'S TEXT, NOT ITS LINE NUMBER (this was chosen
# over narrowing the rule). The first version keyed each exemption on
# `path:line`, and the hole that opens is this repo's worst shape: insert a line above an exempted
# one, and the exempted text moves to the next number while whatever ARRIVES at the old
# number inherits a written reason addressed to something else. The expiry check below could
# not see it -- it only asks whether the keyed line still invokes something, never whether it
# is still the SAME line. A content anchor cannot drift, because there is nothing to drift.
#
# THAT IS NOT A HYPOTHETICAL, AND THE EVIDENCE WAS ALREADY SITTING IN THE FILE. The first
# version's own exemption reason ended "...no shape distinguishes it from release.md:41,
# which IS one". Measured: `commands/release.md` now contains ZERO bare Python
# invocations -- every call in it goes through the resolver, and line 41 is prose about the
# wrapper. A line-number citation inside the exemption's justification had already gone
# stale, silently, in the same phase that wrote it. The reason below now cites the file and
# the shape instead of a number.
#
# EXPIRY IS ENFORCED, AND SO IS OVER-BREADTH. If an exempted fragment matches NO invocation,
# this check FAILS rather than passing quietly -- an exemption that no longer applies is a
# hole with a reason attached, and the reason is what makes it invisible. If one fragment
# matches MORE THAN ONE invocation it also FAILS: one written reason silently covering two
# call sites is the same hole in the other direction. Same discipline as
# `gate-jq-only-envelope.sh`'s expired-exemption row.
set -u

cd "${COMMANDS_PY_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}" || exit 1

# SCOPE. `commands/*.md` plus one file outside it: the tenth edited site lives in
# `references/init-harness.md`, and a `commands/`-only scope would let that one be reverted
# unnoticed. That widening came from the plan-vs-spec cross-check, not from this file.
SCOPE_GLOB="commands/*.md"
SCOPE_EXTRA="skills/project-lifecycle/references/init-harness.md"

RESOLVER_MARK="plc-python.sh"

# `path|line-fragment|reason`. Three fields, and all three are load-bearing: the fragment is
# the anchor (see the header), and the reason is what makes adding an entry a decision
# someone has to write down. These two were. The plan said "exactly one exemption"; the
# second appeared when the check was first run, and widening the net was chosen over
# narrowing the rule -- see the second reason.
EXEMPT="
commands/cognition-distill.md|python3 scripts/cognition_log.py|prose naming a module, not an invocation; no shape distinguishes it from a real inline instruction of the same form
skills/project-lifecycle/references/init-harness.md|python manage.py migrate|adopter-facing Django guidance -- the ADOPTER's own 'python manage.py migrate', not a PLC invocation of a PLC script, and routing someone else's project commands through PLC's resolver would be wrong
"

fail=0
bad() { echo "FAIL commands-no-bare-python: $*"; fail=1; }

FILES=""
for f in $SCOPE_GLOB; do
  [ -f "$f" ] && FILES="$FILES $f"
done
[ -f "$SCOPE_EXTRA" ] && FILES="$FILES $SCOPE_EXTRA"

# An empty corpus is a hard FAIL, never a vacuous pass. Two empty sets compare equal and the
# run looks exactly like a clean one -- this repo has paid for that shape before.
if [ -z "${FILES// /}" ]; then
  bad "scope is EMPTY -- '$SCOPE_GLOB' and '$SCOPE_EXTRA' matched nothing"
  exit 1
fi

EXEMPT_LINES=$(printf '%s\n' "$EXEMPT" | /usr/bin/grep -v '^[[:space:]]*$' || true)

# PASS 1 -- validate the exemption list ITSELF, before it is used to excuse anything. A
# malformed entry must never reach the scan: a two-field entry would hand the fragment back
# as its own reason, and an empty fragment would match every line in its file -- a blanket
# exemption wearing the costume of a targeted one.
while IFS= read -r e; do
  [ -n "$e" ] || continue
  e_path="${e%%|*}"
  e_rest="${e#*|}"
  e_frag="${e_rest%%|*}"
  e_reason="${e_rest#*|}"
  if [ "$e_rest" = "$e" ]; then
    bad "EXEMPT entry '$e' has no '|' -- the format is path|line-fragment|reason"
    continue
  fi
  if [ -z "$e_frag" ]; then
    bad "EXEMPT entry for '$e_path' has an EMPTY fragment -- an empty anchor matches every line in the file"
    continue
  fi
  if [ "$e_reason" = "$e_frag" ] || [ -z "$e_reason" ]; then
    bad "'$e_path|$e_frag' is EXEMPT but carries no written reason -- an exemption without one is just a hole"
    continue
  fi
  case " $FILES " in
    *" $e_path "*) ;;
    *) bad "'$e_path' is EXEMPT but is not in this check's scope -- the entry excuses nothing and will never expire" ;;
  esac
done <<PASS1
$EXEMPT_LINES
PASS1

# An invocation is `python` or `python3` followed by whitespace and then something that is
# not a backtick -- i.e. it has an argument. A bare mention closed by a backtick is not one.
INVOCATION='(^|[^[:alnum:]_./-])python[0-9]*[[:space:]]+[^`[:space:]]'

# PASS 2 -- the scan.
seen_exempt=""
for f in $FILES; do
  while IFS= read -r hit; do
    [ -n "$hit" ] || continue
    n="${hit%%:*}"
    text="${hit#*:}"
    # Allowed: the invocation IS the resolver, or runs through it on the same line.
    case "$text" in
      *"$RESOLVER_MARK"*) continue ;;
    esac
    key="$f:$n"

    matched_id=""
    matched_reason=""
    while IFS= read -r e; do
      [ -n "$e" ] || continue
      e_path="${e%%|*}"
      [ "$e_path" = "$f" ] || continue
      e_rest="${e#*|}"
      [ "$e_rest" != "$e" ] || continue
      e_frag="${e_rest%%|*}"
      e_reason="${e_rest#*|}"
      [ -n "$e_frag" ] || continue
      [ "$e_reason" != "$e_frag" ] || continue
      case "$text" in
        *"$e_frag"*)
          matched_id="$e_path|$e_frag"
          matched_reason="$e_reason"
          break
          ;;
      esac
    done <<PASS2
$EXEMPT_LINES
PASS2

    if [ -n "$matched_id" ]; then
      seen_exempt="$seen_exempt
$matched_id"
      echo "ok  commands-no-bare-python: $key exempt -- $matched_reason"
      continue
    fi
    bad "$key invokes a Python interpreter directly -- route it through $RESOLVER_MARK, or add an EXEMPT line with a written reason"
    echo "       $text"
  done <<EOF
$(/usr/bin/grep -nE "$INVOCATION" "$f" 2>/dev/null || true)
EOF
done

# PASS 3 -- expired and over-broad exemptions. An entry whose fragment matches nothing is
# stale, and a stale exemption is invisible by construction. An entry whose fragment matched
# more than once is one written reason covering two call sites, which is the same hole.
while IFS= read -r e; do
  [ -n "$e" ] || continue
  e_path="${e%%|*}"
  e_rest="${e#*|}"
  [ "$e_rest" != "$e" ] || continue
  e_frag="${e_rest%%|*}"
  [ -n "$e_frag" ] || continue
  id="$e_path|$e_frag"
  hits=$(printf '%s\n' "$seen_exempt" | /usr/bin/grep -c -F -x -- "$id" || true)
  if [ "$hits" -eq 0 ]; then
    bad "'$id' is EXEMPT but matched no invocation -- the exemption has expired; delete its line from EXEMPT"
  elif [ "$hits" -gt 1 ]; then
    bad "'$id' is EXEMPT and matched $hits invocations -- one written reason cannot cover several call sites; narrow the fragment"
  fi
done <<PASS3
$EXEMPT_LINES
PASS3

if [ "$fail" = 0 ]; then
  # Both numbers are DERIVED. The exemption count was briefly a literal `1` while the list
  # held two, which is this repo's own claim-wider-than-mechanism shape appearing in the
  # summary line of a check built to prevent it.
  n_files=$(printf '%s\n' $FILES | /usr/bin/grep -c . || true)
  n_exempt=$(printf '%s\n' "$EXEMPT_LINES" | /usr/bin/grep -c . || true)
  echo "ok  commands-no-bare-python: $n_files files in scope, every Python invocation goes through $RESOLVER_MARK ($n_exempt written exemptions)"
fi
exit "$fail"
