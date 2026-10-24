#!/usr/bin/env bash
# Invariant: the fragment sentinel has ONE source text, and every copy of it is byte-identical.
#
# WHY. The drain writes `<!-- fragment: <path> -->` above every block it appends to an archive, and
# two mechanisms must agree on when such a line is a real fragment boundary: the wrap-up gate, which
# slices one phase's entry out of an archive, and the lifecycle ledger, which asks whether a phase's
# fragment reached a durable file at all. The reader that answers that has been repaired
# before, and it carries a written error-direction policy -- every ambiguity costs a FAIL, never a
# PASS. A second reader re-deriving those rules does not announce itself: it agrees on today's
# corpus and diverges on the first shape nobody thought of.
#
# It was already happening. Before this guard the adopter-facing gate reference carried a
# hand-maintained paraphrase of the parser: 946 bytes against the script's 1697, identical in logic
# but reformatted, with nothing comparing them. That file's own prose said so -- "nothing was
# watching it".
#
# WHAT IS CHECKED, AND WHAT THE CLAIM IS NOT. The ledger reads $LIB directly at run time
# (`awk -f`). The gate cannot: it is a single drop-in script -- its own harness runs it by writing
# the script text alone into a fixture repository, and the reference ships it as one copyable file
# -- so a sibling file would not travel with it. The gate and the reference therefore EMBED the
# program, and this guard holds the source and both embeddings to the same bytes. So the claim is
# exactly: one source text, two pinned embeddings, two direct run-time readers -- the ledger, and
# mode-provenance-recorded.sh, which slices a phase's record out of the archive after a drain has
# moved it there. A direct reader holds no copy of the pattern, so it is not a fourth matcher
# and needs no exemption -- which is what check 2's own refusal message recommends. It is NOT "one
# physical implementation",
# and saying so would be the claim-wider-than-mechanism defect this guard exists to stop.
#
# SCOPE, stated rather than implied. Three things are checked:
#   1. Each declared embedding's awk region is byte-identical to $LIB's pinned program.
#   2. No FOURTH anchored matcher exists under the scanned roots. The discriminator is the ANCHORED
#      form of the sentinel's opener -- a caret immediately followed by the marker's comment prefix
#      -- which only matcher CODE contains. The drain's own writes and its idempotence lookups are
#      unanchored (`printf`, `grep -qF`) and are therefore out of scope by construction, with no
#      exemption list to go stale. This file assembles that pattern from two halves at run time so
#      that it holds no contiguous copy of it either: a checker that matches itself needs an
#      exemption for its own name, and an exemption list is one more thing that goes stale.
#   3. The pinned region is non-empty, so an emptied $LIB cannot pass by comparing nothing to
#      nothing.
#   4. The pinned region contains neither a single quote nor a run of three or more backticks or
#      tildes. Both are CONSTRUCTION constraints, not style: the embeddings live inside a
#      single-quoted shell string inside a markdown fence, so a single quote closes the shell
#      string and breaks the gate, and a triple run ends the fence so the adopter-facing gate
#      silently loses its tail. Both were measured by doing it -- an apostrophe in a comment gave
#      `syntax error near unexpected token`, and one backtick run cut the extracted gate from
#      79,554 bytes to 9,504 -- and in the first case checks 1-3 stayed GREEN throughout, which is
#      exactly why this one exists: identical bytes is a different claim from usable bytes.
# NOT checked: that the program is CORRECT, or that the two embeddings are reached at run time.
# Behaviour is proven by the gate's and the ledger's own suites; `docs/` is outside the scanned
# roots because the prose there discusses this rule and quoting it is not implementing it.
#
# Verdicts: 0 pass, 1 a copy drifted or an undeclared matcher appeared, 3 could not run.

set -uo pipefail

NAME="one-fragment-sentinel-reader"
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT" || { printf 'COULD-NOT-RUN %s: cannot cd to %s\n' "$NAME" "$ROOT" >&2; exit 3; }

LIB="scripts/lib/fragment-sentinel.awk"
PIN="# --- PINNED PROGRAM BELOW"
EMBEDDINGS="scripts/close-gate.sh skills/project-lifecycle/references/close-gate.md"
SCAN_ROOTS="scripts hooks skills"

OPENER='awk -v pat="phase-$2" '"'"
CLOSER="  ' \"\$1\""

# Assembled from two halves on purpose -- see SCOPE item 2. Keep it split.
ANCHORED='^<!-- '"fragment: "

[ -f "$LIB" ] || { printf 'COULD-NOT-RUN %s: %s missing -- the declared source text is gone\n' "$NAME" "$LIB" >&2; exit 3; }

pin_line="$(grep -n -F -- "$PIN" "$LIB" | head -1 | cut -d: -f1)"
[ -n "$pin_line" ] || { printf 'COULD-NOT-RUN %s: no `%s` marker in %s -- the pinned region is undefined\n' "$NAME" "$PIN" "$LIB" >&2; exit 3; }

prog="$(mktemp)" || { printf 'COULD-NOT-RUN %s: mktemp failed\n' "$NAME" >&2; exit 3; }
emb="$(mktemp)" || { rm -f "$prog"; printf 'COULD-NOT-RUN %s: mktemp failed\n' "$NAME" >&2; exit 3; }
trap 'rm -f "$prog" "$emb"' EXIT

tail -n +$((pin_line + 1)) "$LIB" > "$prog"

# Check 3 first: an empty pinned region would make check 1 vacuous -- two empty files compare equal.
prog_lines="$(wc -l < "$prog" | tr -d ' ')"
if [ "${prog_lines:-0}" -lt 10 ]; then
  printf 'FAIL %s: %s has only %s line(s) after the `%s` marker. A near-empty pinned region makes\n' "$NAME" "$LIB" "${prog_lines:-0}" "$PIN" >&2
  printf '  every byte-comparison below vacuous -- two empty extracts are equal. Restore the program.\n' >&2
  exit 1
fi

# Check 4, before the comparisons: a region that cannot be embedded makes a byte-match worthless.
# The quote is built with printf rather than written as a literal only so the pattern stays
# readable in a file that is itself full of quoted printf formats -- unlike the anchored matcher
# above, this guard is embedded nowhere, so the constraint it enforces does not apply to it.
SQ="$(printf '\047')"
if grep -qF -- "$SQ" "$prog"; then
  printf 'FAIL %s: the pinned program in %s contains a single quote, at:\n' "$NAME" "$LIB" >&2
  grep -nF -- "$SQ" "$prog" | head -5 | sed "s/^/     /" >&2
  printf '  -> Both embeddings sit inside a single-quoted shell string, so this closes it and the\n' >&2
  printf '     gate stops parsing (measured: `syntax error near unexpected token`). Checks 1-3 stay\n' >&2
  printf '     green through that, because identical bytes is not the same claim as usable bytes.\n' >&2
  printf '     Reword it -- an apostrophe in a comment is enough to do this.\n' >&2
  exit 1
fi
if grep -qE -- '(`{3,}|~{3,})' "$prog"; then
  printf 'FAIL %s: the pinned program in %s contains a run of three or more backticks or tildes, at:\n' "$NAME" "$LIB" >&2
  grep -nE -- '(`{3,}|~{3,})' "$prog" | head -5 | sed "s/^/     /" >&2
  printf '  -> The adopter-facing reference embeds this program inside a markdown fence and its\n' >&2
  printf '     extractor is non-greedy, so a run here ends the fence early and the published gate\n' >&2
  printf '     silently loses everything after it (measured: 79,554 bytes down to 9,504).\n' >&2
  printf '     Describe the delimiter instead of spelling it.\n' >&2
  exit 1
fi

# Check 1: each declared embedding matches the source text, byte for byte.
for f in $EMBEDDINGS; do
  if [ ! -f "$f" ]; then
    printf 'FAIL %s: declared embedding %s is missing. If it was removed on purpose, remove it from\n' "$NAME" "$f" >&2
    printf '  this guard'"'"'s EMBEDDINGS list in the same change, so the list cannot describe a file that\n' >&2
    printf '  is not there.\n' >&2
    exit 1
  fi
  s="$(grep -n -F -- "$OPENER" "$f" | head -1 | cut -d: -f1)"
  if [ -z "$s" ]; then
    printf 'FAIL %s: %s no longer opens the reader with `%s`. The embedding is gone or was renamed,\n' "$NAME" "$f" "$OPENER" >&2
    printf '  so nothing is holding it to %s any more.\n' "$LIB" >&2
    exit 1
  fi
  e="$(grep -n -F -- "$CLOSER" "$f" | awk -F: -v s="$s" '$1 > s { print $1; exit }')"
  if [ -z "$e" ] || [ "$e" -le $((s + 1)) ]; then
    printf 'FAIL %s: %s opens the reader at line %s but no closing `%s` line follows it.\n' "$NAME" "$f" "$s" "$CLOSER" >&2
    exit 1
  fi
  sed -n "$((s + 1)),$((e - 1))p" "$f" > "$emb"
  if ! cmp -s "$prog" "$emb"; then
    printf 'FAIL %s: the reader embedded in %s (lines %s-%s) is NOT byte-identical to the pinned\n' "$NAME" "$f" "$((s + 1))" "$((e - 1))" >&2
    printf '  program in %s (line %s onward).\n' "$LIB" "$((pin_line + 1))" >&2
    printf '  -> %s is the source text. Copy it into the embedding rather than editing the embedding:\n' "$LIB" >&2
    printf '     the two readers must not be able to disagree about what a fragment boundary is.\n' >&2
    printf '  First difference:\n' >&2
    diff "$prog" "$emb" 2>&1 | head -12 | sed 's/^/     /' >&2
    exit 1
  fi
done

# Check 2: no fourth anchored matcher anywhere under the scanned roots.
#
# NON-VACUITY FIRST, and it is not symmetry with the other checks -- it is a measured hole. Checks
# 1, 3 and 4 each assert they had something to read; check 2 did not, so its probe could stop
# matching and the PASS line would still say "no fourth anchored matcher". Measured:
# changing ONE character of `$ANCHORED` left this invariant printing PASS, and no test in the repo
# reddened. The probe must find the three files it is allowed to find; if it cannot, it has stopped
# being a probe and the verdict is COULD-NOT-RUN rather than a pass.
allowed=" $LIB $EMBEDDINGS "
stray=""
found=""
while IFS= read -r f; do
  [ -n "$f" ] || continue
  found="${found:+$found }$f"
  case "$allowed" in *" $f "*) continue ;; esac
  stray="${stray:+$stray }$f"
done <<EOF
$(grep -r -l -F -- "$ANCHORED" $SCAN_ROOTS 2>/dev/null | sort)
EOF

for f in $LIB $EMBEDDINGS; do
  case " $found " in
    *" $f "*) ;;
    *)
      printf 'COULD-NOT-RUN %s: the anchored probe did not find %s, which is one of the three
' "$NAME" "$f" >&2
      printf '  files it is DECLARED to match. A probe that matches none of its own allow-list cannot
' >&2
      printf '  report "no fourth matcher" -- it would print that from having matched nothing. Check
' >&2
      printf '  the pattern assembled into $ANCHORED, and whether %s still lives under: %s
' "$f" "$SCAN_ROOTS" >&2
      exit 3 ;;
  esac
done

if [ -n "$stray" ]; then
  printf 'FAIL %s: an anchored "%s" matcher appears outside the declared source and its\n' "$NAME" "$ANCHORED" >&2
  printf '  two pinned embeddings:\n' >&2
  for f in $stray; do printf '     %s\n' "$f" >&2; done
  printf '  -> That is a reader nothing holds to %s, which is how two mechanisms come to disagree\n' "$LIB" >&2
  printf '     about what a fragment boundary is. Call the source text instead (`awk -f %s`), or --\n' "$LIB" >&2
  printf '     if the new site genuinely cannot read a sibling file -- add it to this guard'"'"'s\n' >&2
  printf '     EMBEDDINGS list so its bytes are pinned too.\n' >&2
  exit 1
fi

printf 'PASS %s: one source text (%s, %s pinned lines), %s embeddings byte-identical to it, no fourth anchored matcher under %s. Scope: bytes only -- see this file'"'"'s header for what it deliberately does not prove.\n' \
  "$NAME" "$LIB" "$prog_lines" "$(printf '%s\n' $EMBEDDINGS | wc -l | tr -d ' ')" "$(printf '%s' "$SCAN_ROOTS" | tr ' ' '/')"
