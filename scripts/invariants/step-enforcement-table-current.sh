#!/usr/bin/env bash
# step-enforcement-table-current.sh -- p31.
#
# WHAT THIS ASSERTS: the step -> enforcement table has not gone stale relative to the
# requirement text it maps, and the table still says out loud what it does not cover.
#
# WHAT THIS DOES NOT ASSERT, stated here because the table's whole subject is claims wider
# than their mechanism:
#   * It never checks whether a row is TRUE. A row can name an enforcer that was deleted
#     yesterday and this script stays green. Re-deriving rows from the enforcing code is a
#     different job that nothing currently does.
#   * It only fingerprints the bracketed regions of the files in
#     .claude/step-enforcement-fingerprinted.txt. Text outside a bracket -- INCLUDING a brand-new
#     requirement written one line past a closing marker -- is invisible by construction.
#   * The files in .claude/step-enforcement-listed.txt are NOT fingerprinted. 23 of the table's
#     36 rows live there. They are listed so a reader can find them, not because they are guarded.
#   * "The table was touched" is not "a row was updated". A trailing blank line satisfies the
#     same-diff requirement. Closing that would mean judging content, which is the thing this
#     design deliberately does not do.
#
# EXIT: 0 pass | 1 the repository is wrong | 3 could not run.
# Exit 3 never folds into 0. A check that could not run must not report as though it did.
#
# ENVELOPE: bash 3.2 + git + awk/grep/sed. No python3, no jq, no bash-4 constructs.
#
# OUTPUT: every failure prints a stable FAIL[<slug>] code as its first token. The close gate runs
# invariants as ( eval "$CMD" ) >/dev/null 2>&1 and prints only "run it directly to see why", so
# this text exists for the person who runs it directly -- and the codes exist so a mutation test
# can assert WHICH check fired. Exit 1 is shared by seven assertions; without the codes a mutant
# proves only that something failed.
set -u

CANNOT_RUN_RC=3

cannot_run() { printf 'CANNOT-RUN[%s] %s\n' "$1" "$2" >&2; exit "$CANNOT_RUN_RC"; }
fail()       { printf 'FAIL[%s] %s\n' "$1" "$2" >&2; exit 1; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)" || cannot_run "no-root" "cannot resolve repo root"
cd "$ROOT" || cannot_run "no-root" "cannot cd to $ROOT"

FP_LIST=".claude/step-enforcement-fingerprinted.txt"
LS_LIST=".claude/step-enforcement-listed.txt"
PIN=".claude/step-enforcement.sha"
TABLE="skills/project-lifecycle/references/step-enforcement.md"
SKILL="skills/project-lifecycle/SKILL.md"

for f in "$FP_LIST" "$LS_LIST" "$PIN" "$TABLE" "$SKILL"; do
  [ -f "$f" ] || cannot_run "missing-input" "$f does not exist"
  [ -r "$f" ] || cannot_run "unreadable-input" "$f is not readable"
done
command -v git >/dev/null 2>&1 || cannot_run "no-git" "git is not on PATH"

# ---------------------------------------------------------------- sentinel balance (AC7)
# begin/end must be equal in number, strictly alternating, never nested. The one-pair rule this
# replaced could not express SKILL.md's shape: its requirements sit in two non-contiguous regions.
while IFS= read -r f; do
  [ -n "$f" ] || continue
  [ -f "$f" ] || cannot_run "missing-fingerprinted" "$f is listed as fingerprinted but does not exist"
  # awk's `exit` STILL RUNS THE END BLOCK. A first version printed the verdict and exited inside the
  # rule, so END printed a second verdict and $state arrived as two lines -- every structural mutant
  # then fell through to the catch-all and reported CANNOT-RUN instead of the balance failure it had
  # actually triggered. Caught by mutants M11/M12, not by reading. The verdict is now recorded in a
  # variable and printed exactly once, from END.
  state="$(/usr/bin/awk '
    /^<!-- plc-p31:begin -->$/ { if (open) { v="nested"; exit } open=1; pairs++; next }
    /^<!-- plc-p31:end -->$/   { if (!open) { v="unopened"; exit } open=0; next }
    END {
      if (v != "") { print v }
      else if (open) { print "unclosed" }
      else if (!pairs) { print "none" }
      else { print "ok" }
    }
  ' "$f")"
  case "$state" in
    ok) ;;
    nested)   fail "sentinel-balance" "$f: a begin marker appears inside an open block" ;;
    unopened) fail "sentinel-balance" "$f: an end marker appears with no open block" ;;
    unclosed) fail "sentinel-balance" "$f: a block is opened and never closed" ;;
    none)     fail "sentinel-balance" "$f: no plc-p31 block at all" ;;
    *)        cannot_run "awk-failed" "$f: could not evaluate sentinel balance" ;;
  esac
done < "$FP_LIST"

# ---------------------------------------------------------------- digest (AC10/AC11)
# Regions are concatenated in the order the fingerprinted list names them, each preceded by its
# path so that moving text between two bracketed files is not a no-op.
extract_regions() {
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    printf '%s\n' "$f"
    /usr/bin/awk '
      /^<!-- plc-p31:begin -->$/ { inblk=1; next }
      /^<!-- plc-p31:end -->$/   { inblk=0; next }
      inblk { print }
    ' "$f"
  done < "$FP_LIST"
}

NOW="$(extract_regions | git hash-object --stdin 2>/dev/null)" \
  || cannot_run "hash-failed" "git hash-object failed"
[ -n "$NOW" ] || cannot_run "hash-empty" "digest computed as empty"
PINNED="$(/usr/bin/sed -n '1p' "$PIN" | /usr/bin/tr -d ' \n')"
[ -n "$PINNED" ] || cannot_run "pin-empty" "$PIN is empty"

if [ "$NOW" != "$PINNED" ]; then
  # A MISMATCH IS ALWAYS RED. There is no path from "the digest disagrees with the pin" to exit 0,
  # and that is the point: the only way to green is to make them agree.
  #
  # An earlier version of this block branched on "is the pin in the diff?" and RETURNED 0 when it
  # was. That was a false-green -- the digest still disagreed, and any diff that happened to touch
  # the pin file (with a stale value, a wrong value, a whitespace edit) bought a pass. It survived
  # because the obvious positive control does not reach here: correctly updating the pin makes the
  # digests match, so M2 exits above and never exercises this branch at all. The bug was found by
  # asking what M2 had actually proven, not by M2 passing. Recorded because a false-green inside
  # the tool built to count false-greens is the phase's own subject reproducing itself.
  #
  # The diff lookup that remains is used ONLY to choose the message, never the verdict.
  BASE="$(git merge-base origin/HEAD HEAD 2>/dev/null || git merge-base origin/main HEAD 2>/dev/null || true)"
  CHANGED=""
  if [ -n "$BASE" ]; then
    CHANGED="$(git diff --name-only "$BASE"...HEAD 2>/dev/null
               git diff --name-only 2>/dev/null
               git diff --name-only --cached 2>/dev/null
               git ls-files --others --exclude-standard 2>/dev/null)"
  fi
  if printf '%s\n' "$CHANGED" | /usr/bin/grep -qxF "$TABLE"; then
    fail "digest-mismatch" "a bracketed region changed and $TABLE was updated, but $PIN still reads $PINNED -- write $NOW into $PIN in this same commit"
  fi
  fail "digest-mismatch" "a bracketed region changed and $TABLE was not touched -- if a requirement was added or removed, add or remove its row; if not, say so in the commit message and write $NOW into $PIN"
fi

# ---------------------------------------------------------------- watched lists (AC4)
# Set equality between what the table SAYS it covers and what the list files declare. Substring
# containment would pass on mismatched counts, so both directions are compared.
table_paths_in_section() {
  /usr/bin/awk -v want="$1" '
    $0 ~ "^## " want "$" { inblk=1; next }
    /^## / { inblk=0 }
    inblk && /^- `/ { line=$0; sub(/^- `/,"",line); sub(/`.*$/,"",line); print line }
  ' "$TABLE"
}

cmp_sets() {
  a="$(printf '%s\n' "$1" | /usr/bin/grep -v '^$' | /usr/bin/sort -u)"
  b="$(printf '%s\n' "$2" | /usr/bin/grep -v '^$' | /usr/bin/sort -u)"
  [ "$a" = "$b" ]
}

cmp_sets "$(table_paths_in_section 'Fingerprinted files')" "$(cat "$FP_LIST")" \
  || fail "watched-set-drift" "the table's 'Fingerprinted files' section does not match $FP_LIST"
cmp_sets "$(table_paths_in_section 'Listed but NOT fingerprinted')" "$(cat "$LS_LIST")" \
  || fail "watched-set-drift" "the table's 'Listed but NOT fingerprinted' section does not match $LS_LIST"

# ---------------------------------------------------------------- band structure (AC1)
for band in A B C; do
  /usr/bin/grep -qE "^## Band $band " "$TABLE" || fail "band-missing" "the table has no '## Band $band' section"
done

band_rows() {
  /usr/bin/awk -v b="$1" '
    $0 ~ "^## Band " b " " { inblk=1; next }
    /^## / { if (inblk) exit }
    # The separator row is |---|---|..., i.e. a pipe followed by a dash, so it never matches
    # "^| " and is never counted. Only the header row is, which is why the skip is 1 and not 2.
    inblk && /^\| / { n++; if (n>1) print }
  ' "$TABLE"
}

declared_count() {
  /usr/bin/awk -v b="$1" '$0 ~ "^- Band " b " rows: " { gsub(/[^0-9]/,""); print; exit }' "$TABLE"
}

SUM=0
for band in A B C; do
  d="$(declared_count "$band")"
  case "$d" in ''|*[!0-9]*) fail "band-count-missing" "the header does not declare a row count for band $band" ;; esac
  a="$(band_rows "$band" | /usr/bin/grep -c '^| ')"
  [ "$a" -eq 0 ] && fail "band-empty" "band $band declares $d rows but the table has none -- an empty scope must never pass"
  [ "$a" -eq "$d" ] || fail "band-count-drift" "band $band declares $d rows but carries $a"
  SUM=$((SUM + d))
done

# ---------------------------------------------------------------- no combined total (AC2)
# Bans any bare integer equal to the sum, not merely the word "total": "36 gaps" in prose walks
# straight through a word-based ban.
HDR="$(/usr/bin/awk '/^## Band A /{exit} {print}' "$TABLE")"
printf '%s\n' "$HDR" | /usr/bin/grep -qE "(^|[^0-9])$SUM([^0-9]|$)" \
  && fail "bare-total" "the header region contains $SUM, the sum of the band counts -- report the three counts, never their total"

# ---------------------------------------------------------------- seven columns (AC3)
for band in A B C; do
  bad="$(band_rows "$band" | /usr/bin/awk -F'|' 'NF != 9 { print NR": "NF-2" columns" }' | /usr/bin/head -3)"
  [ -z "$bad" ] || fail "columns" "band $band has rows without exactly 7 columns: $bad"
done

# ---------------------------------------------------------------- risk receiver is band-shaped (AC3b)
receivers() { band_rows "$1" | /usr/bin/awk -F'|' '{ v=$7; gsub(/^ +| +$/,"",v); print v }'; }

nonnobody="$(receivers A | /usr/bin/grep -vc '^nobody$')"
[ "$nonnobody" -eq 0 ] || fail "receiver-not-band-shaped" "band A has $nonnobody risk-receiver cells that are not exactly 'nobody' -- band A means there is no receiver"
for band in B C; do
  n="$(receivers "$band" | /usr/bin/grep -c '^nobody$')"
  [ "$n" -eq 0 ] || fail "receiver-not-band-shaped" "band $band has $n cells reading 'nobody' -- an enforcer exists, so somebody is relying on it"
  rep="$(receivers "$band" | /usr/bin/sort | /usr/bin/uniq -c | /usr/bin/sort -rn | /usr/bin/awk 'NR==1{print $1}')"
  case "$rep" in ''|*[!0-9]*) rep=0 ;; esac
  [ "$rep" -le 2 ] || fail "receiver-not-band-shaped" "band $band repeats one risk-receiver value $rep times -- a column of boilerplate says nothing"
done

# ---------------------------------------------------------------- boundary sentences (AC5, AC5b)
# Two DISTINCT strings, not one combined pattern: a single pattern would let one sentence's removal
# pass while the other still matched.
/usr/bin/grep -qF 'does not verify that a row' "$TABLE" \
  || fail "boundary-sentence-missing" "the table no longer says it does not verify a row's claim -- that sentence is the boundary, not decoration"
/usr/bin/grep -qF 'is not on either list below is not watched' "$TABLE" \
  || fail "boundary-sentence-missing" "the table no longer states its residual blind spot -- a gap outside both lists is unwatched, and the table must say so"

# ---------------------------------------------------------------- pointer is prose (AC6)
# MUST fail when the only mention is a References-list bullet. A "filename appears anywhere" grep
# passes on exactly the input this check exists to reject -- that is a guard reporting enforcement
# it is not performing, which this repo has shipped once already.
PROSE="$(/usr/bin/grep -n 'step-enforcement\.md' "$SKILL" | /usr/bin/awk -F: '{ line=$0; sub(/^[0-9]+:/,"",line); if (line !~ /^[[:space:]]*[-*]/) print }' | /usr/bin/wc -l | /usr/bin/tr -d ' ')"
case "$PROSE" in ''|*[!0-9]*) PROSE=0 ;; esac
[ "$PROSE" -ge 1 ] \
  || fail "pointer-not-prose" "$SKILL mentions the table only on bullet lines -- a References entry is not a pointer a reader will follow"

printf 'PASS step-enforcement table is current (bands %s/%s/%s, digest %s)\n' \
  "$(declared_count A)" "$(declared_count B)" "$(declared_count C)" "$NOW"
exit 0
