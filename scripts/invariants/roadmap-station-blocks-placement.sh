#!/usr/bin/env bash
# Invariant (AC-2a + AC-2b): adding the station-plan blocks to `docs/ROADMAP.md`
# leaves the mainline table byte-identical, and the new `## ` sections sit where they cut no
# existing section's body open.
#
# WHY THESE TWO AND NOT THE THIRD. AC-2 was split into three separately-falsifiable criteria
# -- [a] the mainline table's bytes are unchanged, [b] the new blocks are placed
# so no existing section is cut open, [c] PLC's own two parsers produce byte-identical output
# across the change. **[c] is not here, and its absence is a placement decision, not an omission.**
# [c] has to run `scripts/session_card.py` -- that is `python3` -- and every script in
# `scripts/invariants/` is watched by `gate-jq-only-envelope.sh`, which the jq-only envelope widened from three
# named files to this whole directory. The gate is a drop-in for other people's repos: one more
# interpreter is one more thing an adopter must already have (`CLAUDE.md` "Don't do"). So [c] lives
# in `scripts/test_roadmap_parsers_unchanged.py` and runs under the manifest's declared
# `test_command`. **Do not move it back here because it looks like the same job.**
#
# WHY [b] EXISTS AT ALL -- it is not a style rule. Both consumers define a section's body as
# "everything after this `## ` heading up to the NEXT `## `" (a downstream consumer's
# parser; PLC's own parser walks headings the same way). The new
# blocks are themselves `## ` sections, so dropping one into the middle of an existing section
# TRUNCATES that section's body -- while the mainline table's bytes never move. That is why [a] is
# necessary but NOT sufficient, and why the review's suggested shortcut ("just compare the table
# bytes") was rejected: measured, a `## ` heading inserted mid-table changes the parsed output
# while every byte of every table ROW is still there.
#
# MEASURED, not reasoned (docs/research/<the measurement run>/): the two blocks were
# inserted at each of the nine candidate points -- immediately before each of the eight existing
# `## ` headings, and at EOF -- and PLC's parser output was byte-identical at all nine. Three
# negative controls all went red: one character changed in a mainline row, a `## ` heading inserted
# mid-table, and a fifth column added to one row. The nine greens are quotable only because those
# three reds are.
#
# WHAT THIS DOES NOT CHECK, named rather than implied:
#   * that any consumer actually parses the file -- that is [c], see above.
#   * the CONTENT of the blocks (ids, binds-to, steps, cycles). Those are a separate check's other validators;
#     this one is only about where the blocks sit and whether the table moved.
#   * a `## ` heading inside a fenced code block. The scan is line-oriented and fence-blind. A
#     roadmap that puts a fenced `## ` between the table and the next heading would read as a
#     section boundary here and would NOT read as one in a fence-aware parser. No such block exists
#     in this repo's roadmap today; if one appears, this check gets it wrong in the loud direction
#     (it reports a placement violation that is not one), which is the survivable direction.
#
# Envelope: bash + git + awk + coreutils. No python3, no jq needed (this one does not read JSON).
set -euo pipefail

ROADMAP="${ROADMAP_PATH:-docs/ROADMAP.md}"
MAINLINE_HEADING="${MAINLINE_HEADING:-## 🛣}"
# The two block headings this phase introduces. Kept as a declared list rather than "any heading
# the file did not have before": a diff-derived set would treat a heading somebody legitimately
# adds later as a station block and hold it to rules that do not apply to it.
BLOCK_HEADINGS="${BLOCK_HEADINGS:-## 🧭|## 🚦}"

fail=0
note() { printf '%s\n' "$*" >&2; }
bad() { note "✗ $*"; fail=1; }
ok() { printf '  ok  %s\n' "$*"; }

[ -r "$ROADMAP" ] || { note "✗ cannot read $ROADMAP"; exit 1; }
# `[ -r ]` is true for a directory too -- filed here before (p38). Say so out loud.
[ -f "$ROADMAP" ] || { note "✗ $ROADMAP is not a regular file"; exit 1; }

# ---------------------------------------------------------------------------
# [b] Placement: every declared block heading must be immediately followed, at its own section's
# end, by another `## ` heading or EOF -- i.e. it must not have been dropped INTO another section.
#
# Stated positively so the rule is checkable rather than vibe-based: a block heading is well placed
# when the line immediately preceding its section (skipping blank lines and its own leading `---`
# rule) is either the last line of a COMPLETE section or the file start. The operational form that
# does not require modelling "complete": the block heading must not appear between a `## ` heading
# and that heading's own table/list body. We approximate that with the one shape that actually
# breaks a consumer and that the measurement exercised: a block heading sitting between two lines
# that both start with `|` (inside a table), or between a `## ` heading and the first `|` of its
# table.
# ---------------------------------------------------------------------------
#
# THE RULE IS TWO-SIDED, AND THE FIRST VERSION ONLY IMPLEMENTED ONE SIDE. Its comment said
# "the previous non-blank line was a table row AND the next non-blank line is also a table
# row"; the code tested only the previous one. Measured consequence, not a hypothetical: it
# rejected `## 🧭` placed immediately before `## 🗂` -- one of the positions an early run proved
# safe by running both parsers over every candidate -- because the mainline table happens to
# be the last thing in the section above. A guard whose comment describes a two-sided test and
# whose code performs a one-sided one is a known defect shape, and this one was
# written inside the phase that exists to fix it.
#
# Two passes: collect lines, then decide with real lookahead. A single streaming pass cannot
# see the NEXT non-blank line, which is exactly the half that went missing.
placement_violations=$(
  awk -v blocks="$BLOCK_HEADINGS" '
    BEGIN { n = split(blocks, B, "|") }
    function is_block(line,   i) {
      for (i = 1; i <= n; i++) if (index(line, B[i]) == 1) return 1
      return 0
    }
    function is_table(line,   t) {
      t = line; sub(/^[ \t]+/, "", t)
      return (substr(t, 1, 1) == "|")
    }
    function is_blank(line) { return (line ~ /^[ \t]*$/) }
    { L[NR] = $0 }
    END {
      for (i = 1; i <= NR; i++) {
        if (!is_block(L[i])) continue

        prev = ""
        for (j = i - 1; j >= 1; j--) if (!is_blank(L[j])) { prev = L[j]; break }
        nxt = ""
        for (j = i + 1; j <= NR; j++) if (!is_blank(L[j])) { nxt = L[j]; break }

        # A block heading splits a table only when table rows continue AFTER it. A table that
        # simply ends above the heading is a section that ended -- which is the safe case, and
        # is where a block is supposed to go.
        if (is_table(prev) && is_table(nxt)) {
          printf "%d: block heading splits a table (rows continue below it): %s\n", i, L[i]
        }
      }
    }
  ' "$ROADMAP"
)

if [ -n "$placement_violations" ]; then
  while IFS= read -r v; do
    [ -n "$v" ] && bad "$ROADMAP:$v"
  done <<EOF
$placement_violations
EOF
else
  ok "block headings cut no section open"
fi

# ---------------------------------------------------------------------------
# [a] The mainline table's bytes are unchanged against the phase base, EXCEPT for rows a human
#     declared they were editing.
#
# The base is resolved as the merge-base with origin/main, NOT as HEAD~N: a fixed ancestor is what
# makes this comparison mean "since this phase started" no matter how many commits land on top.
# When there is no base to compare against (a fresh clone with no origin, an adopter running this
# on a tree that has no such history), the check says so and SKIPS rather than passing -- an empty
# comparison that prints a pass is indistinguishable from a real one, filed here before.
#
# THE DECLARED-ROWS EXCEPTION, and why it is not a loosening. The criterion this check names is
# "ADDING THE BLOCKS leaves the table byte-identical". Comparing the whole table against the base
# also refuses a row a human edited deliberately -- which is a different claim, and a wider one
# than the criterion. At this phase's own close the checklist required promoting one mainline row
# and demoting another, and this check refused it. Widening a guard past its responsibility is a
# shape filed here repeatedly, so the answer is not a looser comparison: it is a WRITTEN exception.
#
# `.claude/roadmap-row-edits.txt` names each deliberately-edited row. Declared rows are dropped
# from BOTH sides before the comparison and are PRINTED, so the exception is never silent. And a
# declaration whose row did not actually change is an ERROR -- a stale exemption reads exactly
# like coverage while providing none.
# ---------------------------------------------------------------------------
extract_mainline_table() {
  # stdin: a roadmap. stdout: the mainline section's table rows, verbatim.
  awk -v heading="$MAINLINE_HEADING" '
    index($0, heading) == 1 { inmain = 1; next }
    inmain && substr($0, 1, 3) == "## " { inmain = 0 }
    inmain {
      trimmed = $0; sub(/^[ \t]+/, "", trimmed)
      if (substr(trimmed, 1, 1) == "|") print $0
    }
  '
}

BASE="${PHASE_BASE_SHA:-}"
if [ -z "$BASE" ]; then
  BASE=$(git merge-base origin/main HEAD 2>/dev/null || true)
fi

if [ -z "$BASE" ]; then
  note "⊘ no phase base resolvable (no origin/main?) — table-bytes check SKIPPED, not passed"
elif ! git cat-file -e "$BASE:$ROADMAP" 2>/dev/null; then
  note "⊘ $ROADMAP does not exist at $BASE — table-bytes check SKIPPED, not passed"
else
  # Declared rows, matched by the prefix each declaration gives. Read before either side is
  # extracted so the same list is subtracted from both.
  DECL_FILE="${ROADMAP_ROW_EDITS:-.claude/roadmap-row-edits.txt}"
  decl_prefixes=""
  if [ -r "$DECL_FILE" ]; then
    decl_prefixes=$(awk -F'\t' '/^#/ { next } NF >= 2 { print $2 }' "$DECL_FILE")
  fi
  # The prefix list reaches awk as a FILE, never through `-v`: a `-v` value cannot carry a
  # newline (awk rejects it outright with "newline in string"), which is how the first version
  # of this helper died. Same NR==FNR two-input shape no-stored-position.sh already uses.
  DECL_TMP=$(mktemp)
  trap 'rm -f "$DECL_TMP"' EXIT
  printf '%s\n' "$decl_prefixes" > "$DECL_TMP"
  drop_declared() {
    if [ -z "$decl_prefixes" ]; then cat; return; fi
    awk 'NR == FNR { if ($0 != "") p[++n] = $0; next }
         { for (i = 1; i <= n; i++) if (index($0, p[i]) > 0) next; print }' "$DECL_TMP" -
  }
  before=$(git show "$BASE:$ROADMAP" | extract_mainline_table | drop_declared)
  after=$(extract_mainline_table < "$ROADMAP" | drop_declared)

  # A declaration whose row did not change is an ERROR, checked here rather than trusted.
  # A stale exemption reads like coverage and provides none, and it silently widens the
  # hole every time somebody forgets to delete one.
  if [ -n "$decl_prefixes" ]; then
    while IFS= read -r pfx; do
      [ -n "$pfx" ] || continue
      b_row=$(git show "$BASE:$ROADMAP" | extract_mainline_table | grep -F -- "$pfx" || true)
      a_row=$(extract_mainline_table < "$ROADMAP" | grep -F -- "$pfx" || true)
      b_n=$(printf '%s' "$b_row" | grep -c '.' || true)
      a_n=$(printf '%s' "$a_row" | grep -c '.' || true)
      # EXACTLY ONE ROW ON EACH SIDE. A pattern matching two rows silently exempts the second
      # one as well, which is how a written exception becomes a wider hole than the guard it
      # was carved out of; a pattern matching none is a declaration about nothing.
      if [ "$b_n" -ne 1 ] || [ "$a_n" -ne 1 ]; then
        bad "declared row edit \`$pfx\` matches $b_n row(s) at the base and $a_n now — it must name exactly one row on each side"
      elif [ "$b_row" = "$a_row" ]; then
        bad "declared row edit is stale: nothing changed for \`$pfx\` — delete the line in $DECL_FILE"
      else
        note "  declared row edit: $pfx"
      fi
    done <<DECLEOF
$decl_prefixes
DECLEOF
  fi

  # ORDER MATTERS: the non-empty assertion runs BEFORE the comparison, not after.
  #
  # This ordering was not planned -- the first version compared first and asserted afterwards, and
  # the empty-scope mutant (MAINLINE_HEADING pointed at a heading that does not exist) printed
  # `ok  mainline table byte-identical against deadbeef (1 rows)` and only THEN the failure. Two
  # empty extractions compare equal, so the reassuring line is emitted for a comparison that read
  # nothing -- exactly the "empty-set comparison prints like a verified match" shape filed here
  # before. The row count made it worse rather than catching it: `grep -c '^'` over an empty string
  # returns 1, because `printf '%s\n' ""` emits one empty line. A count that reports 1 for zero
  # rows is a broken instrument reporting a healthy number.
  if [ -z "$after" ]; then
    bad "mainline table extraction is EMPTY (heading '$MAINLINE_HEADING' matched nothing) — refusing to compare"
  elif [ "$before" = "$after" ]; then
    rows=$(printf '%s' "$after" | grep -c '' || true)
    ok "mainline table byte-identical against ${BASE:0:8} ($rows rows)"
  else
    bad "mainline table changed against ${BASE:0:8} — AC-2a"
    diff <(printf '%s\n' "$before") <(printf '%s\n' "$after") >&2 || true
  fi
fi

if [ "$fail" -ne 0 ]; then
  note "✗ roadmap-station-blocks-placement: FAILED"
  exit 1
fi
printf '✓ roadmap-station-blocks-placement\n'
