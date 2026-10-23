#!/usr/bin/env bash
# Regenerate the BACKLOG table of contents in place. Deliberately emits NO line numbers:
# a hand- or tool-maintained line index goes stale on the next edit. Ctrl-F on the id instead.
set -uo pipefail
F="docs/BACKLOG.md"

# Arguments are parsed FIRST, before any temp file exists and before any other check can
# fail. Parsed after the temp files, body
# extraction, id validation and state derivation, a typo'd flag would leak three temp files, and
# any earlier failure would report itself instead of the real problem, which is the typo. Nothing here
# can leak, because nothing has been created yet.
RELABEL=0
CHECK=0
for _a in "$@"; do
  case "$_a" in
    --relabel) RELABEL=1 ;;
    # `--check` writes NOTHING. It builds exactly what a real run would write and
    # compares it against the file on disk, so `generator-edges-declared.sh` can ask "is this
    # index what the generator produces today" at gate time. Before this flag existed the only
    # way to find out was to run the generator for real and read the diff afterwards, which is
    # how entries sat `open` in the committed index while the closure ledger
    # said otherwise.
    --check) CHECK=1 ;;
    *) printf 'backlog-toc: unknown argument: %s\n' "$_a" >&2
       printf 'backlog-toc: nothing was written; %s is unchanged.\n' "$F" >&2
       exit 2 ;;
  esac
done

TOC="$(mktemp)"; BODY="$(mktemp)"

# Titles are truncated by CHARACTER. `cut -c` cannot do that portably — it is byte-based in
# GNU coreutils regardless of locale — and slicing a CJK title mid-character rewrites this
# ledger as invalid UTF-8. See the sourced helper for the measurement.
. "$(dirname "${BASH_SOURCE[0]}")/utf8-text.sh"

# The exemption table. Headings whose id is NOT of the form B<n>[.<n>] cannot be
# indexed by id, and an existing id must not be renamed (merged PRs and handoffs cite it).
# So they are exempted BY NAME, and
# the list is deliberately a written-down literal rather than a pattern: a pattern is a table
# that can quietly grow until the count check balances, which is the back door the count
# assertion in test_backlog_ledger.py::test_ac1... exists to slam shut.
#
#   The two entries below are placeholder EXAMPLES of the two shapes (a non-numeric id, and a
#   duplicate kept as "(original)"); replace them with your own legacy headings, if any.
#
# Cost: exempt headings are findable by Ctrl-F and
# NOT by the index. The header below says so out loud, because an index that silently omits
# entries is worse than one that admits it.
EXEMPT_IDS=("B-example-legacy" "B9001 (original)")

is_exempt() {  # $1 = heading text with the leading "## " already stripped
  local raw="$1" e
  for e in "${EXEMPT_IDS[@]}"; do
    case "$raw" in "$e"|"$e "*|"$e"—*) return 0 ;; esac
  done
  return 1
}

# THE SOURCE MUST BE READABLE BEFORE ANYTHING IS WRITTEN OVER IT.
#
# Without this check: with `docs/BACKLOG.md`
# present but unreadable (a permission bit, a lock, an I/O error), `awk` reads nothing, $BODY comes
# out empty, and this script REPLACES a backlog holding real entries with a zero-entry file --
# printing `TOC regenerated: 0 entries` and exiting 0. That is not a bad artifact, it is DATA LOSS
# behind a success message, and `awk`'s own complaint (`source line number 1`) goes to stderr
# unnoticed.
#
# The empty case is legal and stays legal: a repository with no backlog yet gets one created. What
# is not legal is REPLACING a file that exists and has bytes in it with a file that has none --
# the one situation where "nothing was read" and "there is nothing to read" cannot be told apart
# by looking at the output, only by looking at the input first.
if [ -e "$F" ] && [ ! -r "$F" ]; then
  printf 'backlog-toc: %s exists but cannot be read -- refusing to overwrite it with a\n' "$F" >&2
  printf 'backlog-toc: freshly generated empty backlog. Nothing was written.\n' >&2
  rm -f "$TOC" "$BODY"
  exit 8
fi

# body = everything from the first "## B" heading onward
awk '/^## B/{f=1} f' "$F" 2>/dev/null > "$BODY"

# A readable file that yielded no body is the same danger by a different route: a truncated read,
# a file that is not the backlog, a cwd that merely happens to contain a `docs/`. Refuse when the
# source has bytes but produced no entries; allow it when the source is genuinely absent or empty.
if [ -s "$F" ] && [ ! -s "$BODY" ]; then
  printf 'backlog-toc: %s has %s bytes but no `## B` entry could be read from it -- refusing to\n' \
         "$F" "$(/usr/bin/wc -c < "$F" | tr -d ' ')" >&2
  printf 'backlog-toc: replace it with an empty backlog. Nothing was written.\n' >&2
  printf 'backlog-toc: if this file really is not a backlog, you are in the wrong directory.\n' >&2
  rm -f "$TOC" "$BODY"
  exit 8
fi
MAXID="$(grep -oE '^## B[0-9]+' "$BODY" | sed 's/^## B//' | sort -n | tail -1)"
COUNT="$(grep -cE '^## B' "$BODY")"

# Count the exemptions that are ACTUALLY PRESENT, not the size of the table.
#
# Subtracting `${#EXEMPT_IDS[@]}` unconditionally would be wrong: on any corpus that does
# not happen to contain both exempt headings the header would under-report the index — claiming 2
# indexed rows on a 4-heading fixture that exempts nothing. The table is a list of headings that
# WOULD be skipped if present, not an assertion that they are.
EXEMPT_PRESENT=0
while IFS= read -r h; do
  is_exempt "${h#\#\# }" && EXEMPT_PRESENT=$((EXEMPT_PRESENT + 1))
done < <(grep -E '^## B' "$BODY")
INDEXED=$((COUNT - EXEMPT_PRESENT))

# Validate the key set BEFORE generating anything.
#
# Two reasons this is a separate pass and not a check inside the generation loop. (1) That loop
# runs on the right-hand side of a pipe, so it is a SUBSHELL: an `exit` there kills the subshell
# and the script sails on to write a truncated index — a silent degrade.
# (2) A key-set error should leave the file untouched, not
# half-rewritten. Read from a file, never a pipe, so this loop stays in the current shell.
HEADS="$(mktemp)"; grep -E '^## B' "$BODY" > "$HEADS"
while IFS= read -r h; do
  raw="${h#\#\# }"
  is_exempt "$raw" && continue
  # Deliberately the LOOSER extraction: `B[0-9.]+`, not `B[0-9]+(\.[0-9]+)?`.
  #
  # "Tightening" it would be a strictness
  # REGRESSION. A strict pattern only matches the well-formed prefix and sed leaves the rest
  # behind, so `## B12. — x` extracts as `B12` and `## B1.2.3 — x` as `B1.2`: two malformed ids
  # laundered into valid-looking ones, which walks straight past the shape check below. The loose
  # pattern extracts `B12.` and `B1.2.3` verbatim, the check rejects them, and the operator is
  # told. Extraction must be permissive precisely so that validation can be strict.
  probe="$(printf '%s' "$h" | sed -E 's/^## (B[0-9.]+(\(original\))?).*/\1/;s/ .*//')"
  if ! printf '%s' "$probe" | grep -qE '^B[0-9]+(\.[0-9]+)?$'; then
    printf 'backlog-toc: unindexable id "%s" in heading:\n  %s\n' "$probe" "$h" >&2
    printf 'backlog-toc: give it a B<n> id, or add it to EXEMPT_IDS with a written reason.\n' >&2
    printf 'backlog-toc: nothing was written; %s is unchanged.\n' "$F" >&2
    rm -f "$TOC" "$BODY" "$HEADS"
    exit 4
  fi
done < "$HEADS"
rm -f "$HEADS"

# Derive every state ONCE, before the generation block.
#
# A missing parser is a hard failure, not an empty states file. With no parser every id would
# derive `open` and the index would render a confident, uniformly wrong column -- a
# silent degrade, and it would look like a successful run.
PARSER="$(dirname "$0")/backlog-closures.sh"
if [ ! -f "$PARSER" ]; then
  printf 'backlog-toc: no closure-log parser at %s — refusing to render a state column with\n' "$PARSER" >&2
  printf 'backlog-toc: nothing behind it; every id would silently read `open`.\n' >&2
  printf 'backlog-toc: nothing was written; %s is unchanged.\n' "$F" >&2
  rm -f "$TOC" "$BODY"
  exit 5
fi
STATES="$(mktemp)"
if ! /bin/bash "$PARSER" --states > "$STATES" 2>/dev/null; then
  printf 'backlog-toc: %s --states exited non-zero — refusing to render a state column from\n' "$PARSER" >&2
  printf 'backlog-toc: a derivation that failed; every id would silently read `open`.\n' >&2
  printf 'backlog-toc: nothing was written; %s is unchanged.\n' "$F" >&2
  rm -f "$TOC" "$BODY" "$STATES"
  exit 6
fi

# Existence of the parser was never the property that mattered — OUTPUT was.
#
# Checking only that the file is there does not make the degrade impossible.
# With the parser present but broken, this script would print
# "TOC regenerated", exit 0, and rewrite the ledger in place so that every
# row read `open`, closed ones included. The exit-status check above catches
# that one. This second check catches the quieter shape: a parser that succeeds while pointed at
# the wrong log (a stale `PLC_CLOSURE_LOG`, or a cwd where `.claude/` does not exist) exits 0
# with no output, which is indistinguishable from "no closures yet" unless we look at the log.
#
# An adopter with no log at all is the legitimate empty case and stays legal: the check only
# fires when a log with real event lines produced no states.
#
# The DEFAULT path is checked as well as the resolved one, because the resolved one alone
# is not enough: with `PLC_CLOSURE_LOG` pointing somewhere that does not exist, the resolved log is
# absent, the check does not fire, and the real ledger is rewritten to rows of `open`
# — the precise silent degrade, reached through the override rather than through a broken
# parser. A tree with no `.claude/` at all (an adopter, or a scratch fixture) still renders.
has_events() { [ -f "$1" ] && grep -qvE '^(#|$)' "$1"; }
LOGPATH="${PLC_CLOSURE_LOG:-.claude/backlog-closures.tsv}"
DEFAULT_LOG=".claude/backlog-closures.tsv"
if [ ! -s "$STATES" ] && { has_events "$LOGPATH" || has_events "$DEFAULT_LOG"; }; then
  printf 'backlog-toc: a closure log with event lines is present but the derivation produced none\n' >&2
  printf 'backlog-toc: (resolved log: %s) — refusing to render\n' "$LOGPATH" >&2
  printf 'backlog-toc: a column in which every id would read `open`.\n' >&2
  printf 'backlog-toc: nothing was written; %s is unchanged.\n' "$F" >&2
  rm -f "$TOC" "$BODY" "$STATES"
  exit 6
fi

# The two provenance labels for the column header.
#
# They are READ, not written here: an optional, gitignored marker file can supply a vocabulary
# for them at run time (for example, labels in the language the backlog is written in).
# With no marker file the labels fall back to plain English.
MARKERS="${PLC_ROADMAP_MARKERS:-.claude/roadmap-progress-markers.txt}"
PROV_DERIVED=derived
PROV_HAND=hand-written
MARKERS_PRESENT=0
VOCAB_RESOLVED=0
if [ -f "$MARKERS" ]; then
  MARKERS_PRESENT=1
  # Looked up BY KEY, never by line number. The positional form (line 1 = derived, line 2 =
  # hand-written) meant a reorder of two lines in an author-local file silently published a
  # header claiming `state` is hand-written and `priority` derived -- a lie about the exact
  # property the header exists to state -- and no test could see it, because the test read its
  # expectation from the same two lines.
  # `^[ \t]*#`, not `^#`: the test-side reader strips before testing for a comment, and two
  # readers of one format that disagree on an indented comment is how a header ends up carrying
  # a comment as its label. Same format, same predicate.
  prov="$(awk '/^\[provenance\]/{f=1;next} /^\[/{f=0} f' "$MARKERS" | awk 'NF && $0 !~ /^[ \t]*#/')"
  d="$(printf '%s\n' "$prov" | awk -F'\t' '$1=="derived"{print $2; exit}')"
  h="$(printf '%s\n' "$prov" | awk -F'\t' '$1=="hand-written"{print $2; exit}')"
  [ -n "$d" ] && PROV_DERIVED="$d"
  [ -n "$h" ] && PROV_HAND="$h"
  # PRESENCE OF THE FILE IS THE WRONG PREDICATE: what matters is whether the file actually
  # YIELDS labels. Measured, with a header already carrying SEEDED-D / SEEDED-H:
  #
  #   vocabulary file, empty ................ exit 0  -> state (derived) | priority (hand-written)
  #   vocabulary file, section header only .. exit 0  -> state (derived) | priority (hand-written)
  #   vocabulary file, comments only ........ exit 0  -> state (derived) | priority (hand-written)
  #   vocabulary file, `derived` only ....... exit 0  -> state (ONLY-D)  | priority (hand-written)
  #
  # Three of those ARE the defect, and the fourth is half of it. A file that exists and resolves
  # nothing is indistinguishable, for every decision below, from no file at all -- so it is
  # treated as no file at all. PARTIAL counts as unresolved on purpose: relabelling one column
  # from a vocabulary and the other from the fallback is the half-defect above, and the format
  # documents both keys.
  [ -n "$d" ] && [ -n "$h" ] && VOCAB_RESOLVED=1
  if [ "$VOCAB_RESOLVED" -eq 0 ]; then
    printf 'backlog-toc: %s exists but resolves no usable provenance vocabulary' "$MARKERS" >&2
    if [ -n "$d$h" ]; then
      printf ' (derived=%s, hand-written=%s -- both keys are required)' "${d:-<missing>}" "${h:-<missing>}" >&2
    fi
    printf ' -- treating it as absent.\n' >&2
  fi
fi

# WHERE THE LABELS COME FROM, and why the tracked file outranks the vocabulary.
#
# $MARKERS is gitignored, so a git
# worktree never receives it and the fallback above resolves to the English defaults. The same
# command therefore produced two different tracked artifacts depending on which checkout it ran
# in, and said nothing either time:
#
#   main checkout, file present ...... | id | state (<author-vocab>) | ...  exit 0
#   worktree, file absent ............ | id | state (derived) | ...      exit 0
#
# That is how a worktree run can commit an English header over a labelled one, silently.
#
# THE FIX IS NOT TO GO FIND THE FILE. Resolving $MARKERS across worktrees
# (`git rev-parse --git-common-dir` + dirname) was rejected for three reasons:
# it derives the worktree root from the git dir, an assumption that breaks when
# core.bare=true is set; it adds a git dependency to a
# generator that has zero; and it makes a worktree reach into the main checkout for config,
# defeating the isolation the worktree exists to give.
#
# SO: THE TRACKED FILE IS THE AUTHORITY FOR ITS OWN LABELS. $MARKERS only ever seeds a header
# that does not exist yet. This also collapses a two-sources-for-one-fact problem
# -- there is now one source, and it is the artifact.
#
# ABSENCE PRESERVES, IT DOES NOT OVERWRITE, AND IT DOES NOT REFUSE. Refusing outright whenever
# the labels disagree would be wrong: callers legitimately drive this generator over a COPY of
# the backlog inside a
# scratch directory that has no vocabulary, and refusing would make every scratch-
# directory caller carry a flag it has no opinion about. Preserving removes the failure mode
# instead of reporting it -- a worktree run is now a no-op on the labels rather than an error.
#
# A PRESENT vocabulary that DISAGREES is a different situation and still stops: two live sources
# are in conflict and only a human knows which one moved. That is what --relabel is for.
#
# Read BY COLUMN, not by position: a header with the two labels swapped is the exact lie
# a column-blind comparison misses, so comparing an unordered pair would pass it through.
# Extract the labels ALREADY in the file. Each choice below is kept as a comment
# because each one is a way this guard could have gone
# on protecting nothing while exiting 0.
#
#   ^ *\| , not ^\|            -- a markdown table may be indented up to three spaces. An
#                                indented header used to match nothing, which fell through to
#                                "no prior header" and OVERWROTE. The empty-extract path is the
#                                back door into the exact defect this guard exists to close.
#   [^()]* inside the capture  -- `.*(\(.*\)).*` is greedy on both ends, so a nested label like
#                                `state (source (derived))` captured `derived` and rewrote the
#                                header as `state (derived))`. Bounded to non-parens.
#   BOTH or NEITHER            -- see the malformed-header branch below.
_extract_label() {  # $1 = the header line, $2 = the 1-based cell number
  printf '%s\n' "$1" | awk -F'|' -v c="$2" '{print $c}' | sed -n 's/.*(\([^()]*\)).*/\1/p'
}
_cell_text() {      # $1 = the header line, $2 = the 1-based cell number, trimmed
  printf '%s\n' "$1" | awk -F'|' -v c="$2" '{gsub(/^[ \t]+|[ \t]+$/, "", $c); print $c}'
}

# ROUND-TRIP, because enumerating the shapes that break extraction is a losing game.
#
# A fix per known shape would still be a list. This asks the only
# question that matters instead: if the label I read back does not rebuild the cell that is
# actually in the file, then I did not read that cell -- whatever the reason. A nested label
# (`state (source (X))`) survived the per-shape fix and was still being silently rewritten to
# `state (X)`; this catches it, and catches the next shape nobody has thought of.
_reads_back() {     # $1 = header line, $2 = cell number, $3 = column word, $4 = extracted label
  [ -n "$4" ] && [ "$(_cell_text "$1" "$2")" = "$3 ($4)" ]
}

FILE_D=""; FILE_H=""; HDR_PRESENT=0; LABELS_SEEN=0
if [ -f "$F" ] && [ -r "$F" ]; then
  # The matcher is WIDER than the generator's own output on purpose.
  #
  # Two header shapes used to be missed, and missing a header is not a
  # harmless no-op: HDR_PRESENT stays 0, the guards read that as "there is nothing here", and the
  # fallback is written straight over labels that were sitting in the file. Both measured, both
  # exit 0 before this change:
  #
  #   a TAB-indented header line      -> `^ *` matches spaces only
  #   `| ID |` instead of `| id |`    -> the extractor was case-sensitive
  #
  # This tool only ever WRITES `| id |` at column zero, so a wider matcher costs nothing and the
  # narrow one was quietly load-bearing for a decision it should never have influenced.
  _hdr="$(awk '/^[ \t]*\|[ \t]*[Ii][Dd][ \t]*\|/{print; exit}' "$F")"
  if [ -n "$_hdr" ]; then
    HDR_PRESENT=1
    # $2 is `id`, $3 the state cell, $4 the priority cell (a leading `|` makes $1 empty).
    FILE_D="$(_extract_label "$_hdr" 3)"
    FILE_H="$(_extract_label "$_hdr" 4)"
    # Recorded BEFORE the malformed-header branch below can zero HDR_PRESENT, because the exit-9
    # guard needs a different question than that branch answers. `HDR_PRESENT` means "I can parse
    # this header"; `LABELS_SEEN` means "there is something here I would be discarding". The
    # second is the one that decides whether the fallback may be written, and conflating them is
    # how `--relabel` on a HALF-readable header (one good label, one malformed) discarded the good
    # one and wrote English -- the same half-defect the vocabulary side has, on the header side.
    [ -n "$FILE_D$FILE_H" ] && LABELS_SEEN=1
  fi
fi

# A HEADER THAT IS PRESENT BUT ONLY HALF-READABLE IS AN ERROR, NOT A LICENCE TO WRITE.
#
# `[ -n "$FILE_D$FILE_H" ]` was true when only ONE label extracted, and the preserve branch then
# assigned the empty one straight through -- writing `priority ()` into the tracked file and
# exiting 0. Corrupting the artifact is a worse outcome than a wrong label,
# and it was reachable from a single missing bracket in the header. A label containing a literal
# `|` reaches this same branch, because `awk -F'|'` splits the cell in half and the capture then
# finds no closing paren; refusing is correct there too -- the header is not parseable by the
# tool that has to rewrite it, and guessing is how the original defect happened.
if [ "$HDR_PRESENT" -eq 1 ] && { ! _reads_back "$_hdr" 3 state "$FILE_D" \
                                 || ! _reads_back "$_hdr" 4 priority "$FILE_H"; }; then
  printf 'backlog-toc: the index header of %s is present but its provenance labels are not\n' "$F" >&2
  printf 'backlog-toc: readable as written -- got state (%s) | priority (%s) from %s | %s.\n' \\
         "$FILE_D" "$FILE_H" "$(_cell_text "$_hdr" 3)" "$(_cell_text "$_hdr" 4)" >&2
  printf 'backlog-toc: refusing to rewrite a header this tool cannot read; nothing was written.\n' >&2
  # Only advertise --relabel where it will actually work. With a label still
  # readable and no vocabulary resolved, --relabel now refuses (exit 9) rather than discarding it,
  # so telling the operator to reach for it would send them into a second refusal. A message that
  # names an unavailable way out is worse than one that names none.
  if [ "$LABELS_SEEN" -eq 1 ] && [ "$VOCAB_RESOLVED" -eq 0 ]; then
    printf 'backlog-toc: fix the header by hand. (--relabel will NOT help here: one label is still\n' >&2
    printf 'backlog-toc: readable and there is no vocabulary to relabel from, so it refuses too.)\n' >&2
  else
    printf 'backlog-toc: fix the header by hand, or pass --relabel to write it fresh.\n' >&2
  fi
  if [ "$RELABEL" -eq 0 ]; then
    rm -f "$TOC" "$BODY" "$STATES"
    exit 7
  fi
  printf 'backlog-toc: --relabel given -- writing a fresh header anyway.\n' >&2
  FILE_D=""; FILE_H=""; HDR_PRESENT=0
fi

# THE ESCAPE HATCH MUST NOT LEAD BACK INTO THE DEFECT.
#
# `--relabel` is "the one way past the refusal", and with no condition on it
# it would lead straight back into the defect: in a
# checkout with no vocabulary -- a worktree, typically --
# `--relabel` would rewrite a labelled tracked header straight back to the English fallback.
# And that route is WORSE than a silent overwrite, because it would be
# reached by a person who hit a refusal and followed the documented way out.
#
# The question `--relabel` has to be able to answer is "relabel to WHAT". It has a real answer in
# exactly two situations, and both stay legal:
#
#   * a vocabulary IS present     -- you are re-applying a vocabulary that actually changed
#   * the header is unreadable    -- the recovery path above; there is nothing to lose
#
# It has no answer when the vocabulary is absent and a readable header already carries labels: the
# only thing to relabel to is the fallback, and the fallback IS the bug. So that one case refuses,
# and the message names the two ways forward rather than leaving the operator to guess.
if [ "$RELABEL" -eq 1 ] && [ "$LABELS_SEEN" -eq 1 ] && [ "$VOCAB_RESOLVED" -eq 0 ]; then
  printf 'backlog-toc: --relabel with no vocabulary would rewrite the header of %s to the\n' "$F" >&2
  printf '  English fallback -- state (%s) | priority (%s) -- discarding the labels that are\n' \
         "$PROV_DERIVED" "$PROV_HAND" >&2
  printf '  in the file now: state (%s) | priority (%s).\n' "$FILE_D" "$FILE_H" >&2
  printf '\n' >&2
  printf '  That is the defect this guard exists to prevent, reached through its own escape hatch. A\n' >&2
  printf '  worktree does not receive the gitignored vocabulary, so this is what --relabel does\n' >&2
  printf '  there. Nothing was written.\n' >&2
  printf '\n' >&2
  printf '  Run where %s is readable, or set PLC_ROADMAP_MARKERS to point at it.\n' "$MARKERS" >&2
  rm -f "$TOC" "$BODY" "$STATES"
  exit 9
fi

if [ "$HDR_PRESENT" -eq 1 ] && [ "$RELABEL" -eq 0 ] \
   && { [ "$FILE_D" != "$PROV_DERIVED" ] || [ "$FILE_H" != "$PROV_HAND" ]; }; then
  if [ "$VOCAB_RESOLVED" -eq 0 ]; then
    # No usable vocabulary here. Keep what the artifact already says and narrate it, so a worktree run
    # is visibly a no-op on the labels rather than an invisible rewrite.
    printf 'backlog-toc: keeping the header labels already in %s -- state (%s) | priority (%s).\n' \
           "$F" "$FILE_D" "$FILE_H" >&2
    PROV_DERIVED="$FILE_D"; PROV_HAND="$FILE_H"
  else
    printf 'backlog-toc: REFUSING to relabel the index header of %s.\n' "$F" >&2
    printf '  already in the file : state (%s) | priority (%s)\n' "$FILE_D" "$FILE_H" >&2
    printf '  resolved from %s : state (%s) | priority (%s)\n' "$MARKERS" "$PROV_DERIVED" "$PROV_HAND" >&2
    printf '\n' >&2
    printf '  Two live sources disagree and only you know which one moved. Nothing was\n' >&2
    printf '  written. Pass --relabel if the change is deliberate.\n' >&2
    rm -f "$TOC" "$BODY" "$STATES" "$HEADS"
    exit 3
  fi
fi

{
  # The title asserts nothing about how git treats docs/. It said
  # "(local-only — docs/ is gitignored)" until p39 made docs/ tracked and for
  # months after, and because this printf restores it, every hand-correction was
  # silently undone by the next run. A claim a mechanism keeps reasserting cannot
  # be fixed in the artifact. Guarded by
  # scripts/invariants/backlog-title-claims-only-what-is-true.sh, which checks
  # this line AND docs/BACKLOG.md against the tree rather than against wording.
  printf '# Backlog\n\n'
  printf 'Deferred decisions, each with explicit Trigger + Exit criteria per the skill'"'"'s backlog discipline.\n\n'
  printf '## Index\n\n'
  printf '> **Next free id: B%s.** Check this before filing — ids collide otherwise.\n' "$((MAXID + 1))"
  printf '> %s headings, **%s indexed**. Regenerate with `/bin/bash scripts/backlog-toc.sh` — do NOT hand-edit this block,\n' "$COUNT" "$INDEXED"
  printf '> the generator rewrites it wholesale.\n'
  printf '> It carries **no line numbers on purpose** — a line index goes stale on the next edit. Ctrl-F the id.\n'
  if [ "$EXEMPT_PRESENT" -gt 0 ]; then
    printf '> **%s heading(s) are exempt and appear below only via Ctrl-F, not in this table**: ' "$EXEMPT_PRESENT"
    sep=""
    for e in "${EXEMPT_IDS[@]}"; do
      grep -qF "## $e" "$BODY" && { printf '%s`%s`' "$sep" "$e"; sep=" · "; }
    done
    printf '\n> — ids this generator cannot index (see EXEMPT_IDS in scripts/backlog-toc.sh).\n'
  fi
  printf '> **The two columns do not have the same provenance.** `state` is DERIVED from\n'
  printf '> `.claude/backlog-closures.tsv` via `backlog-closures.sh --derive` — to change it, append\n'
  printf '> an event to that log; editing this table does nothing. `priority` is still read\n'
  printf '> from the heading glyph and is hand-written: it is a human ordering, and there is no\n'
  printf '> source to derive it from.\n'
  printf '\n'
  printf '| id | state (%s) | priority (%s) | what |\n|---|---|---|---|\n' "$PROV_DERIVED" "$PROV_HAND"
  grep -E '^## B' "$BODY" | while IFS= read -r h; do
    rest="${h#\#\# }"
    if is_exempt "$rest"; then continue; fi
    id="$(printf '%s' "$h" | sed -E 's/^## (B[0-9.]+(\(original\))?).*/\1/;s/ .*//')"
    rest="${rest#* — }"

    # A heading whose first segment is only a closure date must not donate that date
    # to the `what` column. A row reading `✅ DONE YYYY-MM-DD` would otherwise show that as its description;
    # stripping the marker words alone would only leave it reading
    # `YYYY-MM-DD` -- a tidier version of the same uselessness. The date stays in the heading,
    # where it is the historical record; it is just not what the entry is ABOUT.
    rest="$(printf '%s' "$rest" | sed -E 's/^[0-9]{4}-[0-9]{2}-[0-9]{2}( \([^)]*\))? — //')"

    # State is DERIVED, and derived by the parser rather than re-implemented here.
    #
    # It used to be a substring `case` over this same heading text: whichever of ✅ / DONE /
    # CLOSED / MERGED the author happened to reach for decided the whole column, and many entries
    # rendered `—`, which meant "no word matched" and was read by everyone as "not done". The
    # lookup below is a plain grep of a states file computed ONCE before this loop, because the
    # loop runs on the right-hand side of a pipe and is therefore a subshell -- no state it
    # builds would survive, and a per-id call to the parser would fork three processes per row.
    state="$(awk -F'\t' -v id="$id" '$1==id{print $2; f=1} END{if(!f) print "open"}' "$STATES")"

    # priority stays hand-written, and the header says so. There is nothing to derive it from:
    # it is a human ordering, not a fact about the repo.
    #
    # TWO DEFECTS, ONE LINE OF CODE. The table above mapped three glyphs and tested them
    # as a substring of the WHOLE heading.
    #
    #   1. `🔴` reached no branch, so `prio` stayed empty and the cell rendered BLANK -- the
    #      heaviest entries in the file read exactly like entries nobody had prioritised. Exit 0, nothing printed.
    #   2. A glyph that is not in the table at all was the same silence. A state word such as `🔵 DEFERRED` sitting in
    #      a heading's priority slot is a real inconsistency and was unreportable.
    #
    # AND THE OBVIOUS FIX IS WRONG, measured rather than feared: a substring test lets a glyph
    # MENTIONED IN PROSE win. Take a heading whose trailing segment opens with 🟠 and then names 🔴 inside its
    # own parenthetical, and another whose title contains 🔴 while its priority segment is 🟢. Both
    # are right today only because 🟠 and 🟢 are tested first; adding a `*"🔴"*` branch
    # promotes both, invisibly, since a wrong priority looks exactly like a right one.
    #
    # So the oracle is a glyph that OPENS one of the heading's ` -- ` segments -- the one
    # position a prose mention cannot reach. Prefix patterns, not `${seg:0:1}`: bash substring
    # arithmetic is byte-based under a C locale, and this repo has already paid for a
    # byte-vs-character slip in a CJK-bearing generator.
    #
    # IT IS "SOME SEGMENT", NOT "THE LAST SEGMENT", and that correction was bought by reading
    # the regenerated diff rather than by a test. The first attempt here took the last segment
    # (`${h##* -- }`) and it dropped priorities that the defective substring `case` had
    # been getting right:
    #       one   -- `🟡 (note: ... **step 2 -- the first part ...`   more ` -- ` AFTER the glyph
    #       two   -- `... -- 🟡 SOON (small; ...) -- added later`   glyph is second-to-last
    #       three -- `## B9001 -- 🟠 ESCALATED -- some later title ...`    glyph is FIRST
    # A fix for a silent downgrade that silently downgrades other rows is the defect, not
    # a fix for it, and the fixture missed it because every heading in it put the glyph last --
    # a hole in the SHAPE of the scenario, not in the axis being varied (a lesson learned before).
    # The walk below therefore scans segments left to right and stops at the first one that
    # OPENS with a glyph. Pure parameter expansion: this loop body runs once per heading and
    # the surrounding code already refuses to fork per row.
    #
    # The WORD beside the glyph is not a usable key. Severity words come in several spellings, some
    # of them non-English, and the same word can label 🟠 in one document and 🔴 in another.
    # The glyph ranks; the word is decoration. Normalising the words is NOT done here -- it needs
    # every heading rewritten, which is a different change -- but the two documents now agree
    # on the thing that carries meaning: 🔴 is the top tier in both.
    prio=""
    prio_seg="${h#\#\# }"
    while :; do
      case "$prio_seg" in
        "🔴"*) prio="🔴 crit" ;;
        "🟠"*) prio="🟠 high" ;;
        "🟡"*) prio="🟡 med" ;;
        "🟢"*) prio="🟢 low" ;;
        # Recognised as a priority-slot glyph, deliberately NOT ranked. `?` is the honest
        # cell: it says "a glyph is here and it is not one of the four", which a blank cannot
        # say, and it stays distinguishable from an entry that simply set no priority (which
        # keeps its blank cell and earns no warning -- otherwise the fix just swaps one
        # indiscriminate cell for one indiscriminate complaint). Warn-only on purpose: the
        # generator rewrites the file in place, and aborting mid-write over a heading typo is
        # the worse failure.
        "🔵"*|"🟣"*|"🟤"*|"⚫"*|"⚪"*)
          prio="?"
          printf 'backlog-toc: %s carries a priority glyph this table does not rank (%s) -- cell rendered `?`.\n' \
            "$id" "${prio_seg%% *}" >&2
          ;;
      esac
      if [ -n "$prio" ]; then break; fi
      # Not this segment: advance past the next ` -- `, or stop when there is none left. Each
      # pass strictly shortens the string, so the walk terminates on every input.
      case "$prio_seg" in
        *" — "*) prio_seg="${prio_seg#*" — "}" ;;
        *) break ;;
      esac
    done
    title="$(plc_utf8_head "$(printf '%s' "$rest" | sed -E 's/ \(surfaced[^)]*\)//; s/ —.*//')" 105)"
    printf '| **%s** | %s | %s | %s |\n' "$id" "$state" "$prio" "$title"
  done
  printf '\n---\n\n'
} > "$TOC"

# WHERE THE STAGING FILE LIVES, and why --check does not put it in docs/.
# The first version of --check staged to "$F.new" like a real run does. That is a large file
# written INTO docs/, untracked and not gitignored, from a mode three shipped surfaces described as
# "writes nothing" -- and `link-check-reaches-deep` fails on untracked files under docs/ that are
# not on its declared-safe list, so an interrupted --check could redden an unrelated invariant.
# In check mode the staging file goes to TMPDIR instead. In write mode it stays beside the target,
# because `mv` within one filesystem is what makes the install atomic.
if [ "$CHECK" -eq 1 ]; then
  NEW="$(mktemp "${TMPDIR:-/tmp}/backlog-toc.XXXXXX")" || {
    rm -f "$TOC" "$BODY" "$STATES"
    printf 'backlog-toc: mktemp failed; nothing was written and %s is unchanged.\n' "$F" >&2
    exit 10
  }
else
  NEW="$F.new"
fi

# THE `&&` HERE IS LOAD-BEARING AND SPLITTING IT COST A LEDGER.
# This was `cat ... > "$F.new" && mv "$F.new" "$F"` on one line. Adding --check split it, and
# because this script runs `set -uo pipefail` with NO `-e`, a failed `cat` stopped guarding the
# `mv`: the truncated staging file was installed over docs/BACKLOG.md and the script still printed
# `TOC regenerated` and exited 0. MEASURED, not reasoned: with $BODY made unreadable just before
# this line, the file was truncated while origin/main's one-liner left it untouched.
# docs/BACKLOG.md is its own source -- $BODY is extracted FROM it at :84 -- so a clobber destroys
# content that exists nowhere else in the working tree. Fail closed, and name the file that was NOT
# written.
# `if ! cmd; then rc=$?` reads the status of the NEGATION, which is always 0 -- the first version of
# this fix printed "cat exited 0" while reporting a failure. Capture before testing.
cat_rc=0
cat "$TOC" "$BODY" > "$NEW" || cat_rc=$?
if [ "$cat_rc" -ne 0 ]; then
  rc="$cat_rc"
  rm -f "$TOC" "$BODY" "$STATES" "$NEW"
  printf 'backlog-toc: could not assemble the new %s (cat exited %s).\n' "$F" "$rc" >&2
  printf '  Nothing was written; %s is unchanged.\n' "$F" >&2
  exit 10
fi
if [ "$CHECK" -eq 1 ]; then
  if cmp -s "$NEW" "$F"; then
    rm -f "$TOC" "$BODY" "$STATES" "$NEW"
    printf 'backlog-toc --check: %s is what the generator produces today (%s entries)\n' "$F" "$COUNT"
    exit 0
  fi
  rm -f "$TOC" "$BODY" "$STATES" "$NEW"
  printf 'backlog-toc --check: %s DIFFERS from what the generator produces today.\n' "$F" >&2
  printf '  Nothing was written. Regenerate with: /bin/bash scripts/backlog-toc.sh\n' >&2
  exit 1
fi
mv "$NEW" "$F"
rm -f "$TOC" "$BODY" "$STATES"
printf 'TOC regenerated: %s entries, next free id B%s\n' "$COUNT" "$((MAXID + 1))"
