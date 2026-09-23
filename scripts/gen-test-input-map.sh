#!/usr/bin/env bash
# gen-test-input-map.sh — record which repo files each test file reads, by running it.
#
# Writes .claude/test-input-map.tsv: a header line, then one row per (test file, input path, via):
#     test-file <TAB> input-path <TAB> via <TAB> tracked
#   via      direct     -- the test process opened the path in a way that can read it
#            subprocess -- the path was named in the argv of a subprocess the test started
#            (generator -- added by the declared-edge rule; never written by this script yet)
#   tracked  yes | no   -- whether the path is in the git index at generation time
#
# RUN IT ON A FULLY STAGED TREE, with the map itself already present. MEASURED, both:
#   - `tracked` reads the INDEX. The first real run happened before `git add`, so the generator
#     and its own test were marked `no` -- a map that would have been wrong from the commit that
#     pinned it.
#   - Several tests walk the working tree (one of them reads over a thousand paths), so
#     the map is an input to them once it exists. The first run is the one where it did not, so
#     only a SECOND run on the same tree is a fixed point.
# A DIRECTORY row always reads `tracked=no`: git indexes files, not directories. Directories reach
# the map only as subprocess argv (`docs`, `.claude/.gate-runs/ledger`). What such a row means for
# selection -- prefix match? untracked if anything under it is? -- is the selector's decision,
# and it is not settled by this column.
#
# WHY RUN IT AND NOT PARSE IT. The test this whole phase is built around,
# scripts/test_roadmap_lead_length.py, never contains the string docs/ROADMAP.md: it reaches it
# through a subprocess'd generator. A parser cannot see that edge; a traced run can (a traced run is the whole reason this exists).
#
# WHY ONE PYTEST PROCESS PER TEST FILE. A module is opened only by the first file in a process
# that imports it, so a shared process hides every later importer's dependency on it. MEASURED:
# An earlier multi-file run had no scripts/session_card.py row for two test files that import it at top
# level. It also bounds memory -- a single-process run was OOM-killed twice.
#
# WHY THE LIST OF TEST FILES COMES FROM PYTEST. It is whatever `pytest scripts --collect-only`
# collects, not a glob re-implemented here. That matches CI's `python -m pytest scripts/` only while
# `python3` here and `python` there are the same interpreter with the same plugins -- true today
# (both 3.13; CI pins it via setup-python), assumed rather than checked by this script.
# A file with zero collected tests is not a test file for this purpose.
#
# REFUSES rather than writes a partial map. If any test file fails, errors, or records nothing --
# not even its own module, which every traced test file reads -- the script exits 1 and the
# existing map is left byte-for-byte as it was. A failing test may stop before its reads, and a
# map built from it would under-select silently. The output goes to a temp file in .claude/ and is
# renamed over the real one only on success: never a bare `> file` or `tee`, which truncate the
# good file before the step that can fail.
#
# --check: trace, write nothing, fail on every read the pinned map does not name (completeness).
# Writes .claude/test-input-map.fingerprint beside the map (see FINGERPRINT below).
#
# Cost: about as long as the full suite plus one interpreter start per test file.
# Progress goes to stderr, one line per file; per-file pytest output goes to a log kept on failure.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
OUT="$ROOT/.claude/test-input-map.tsv"
FP="$ROOT/.claude/test-input-map.fingerprint"
# What counts as CODE -- a file whose content can change which files a test opens. Must equal
# scripts/blind_spots.py SCRIPT_SUFFIXES (a test pins the two together): the first version kept
# its own shorter list, missed .mjs, and 5 real map rows fell out of the fingerprint.
CODE_SUFFIXES='sh py awk jq sed pl rb js mjs bash'
cd "$ROOT"
MODE=write
case "${1:-}" in
  --check) MODE=check ;;
  "") ;;
  *) printf 'gen-test-input-map: unknown argument %s (only --check)\n' "$1" >&2; exit 2 ;;
esac

WORK="$(mktemp -d "${TMPDIR:-/tmp}/gen-test-input-map.XXXXXX")"
LOG="$WORK/pytest.log"
keep_work=0
cleanup() { [ "$keep_work" = 1 ] || rm -rf "$WORK"; }
trap cleanup EXIT

# The tracer arms on PLC_TRACE_OUT; an inherited one must not reach the collection pass.
unset PLC_TRACE_OUT

if ! python3 -m pytest scripts --collect-only -q >"$WORK/collect.txt" 2>&1; then
  keep_work=1
  printf 'gen-test-input-map: collection failed; output kept at %s\n' "$WORK/collect.txt" >&2
  exit 1
fi
awk -F'::' 'NF > 1 { print $1 }' "$WORK/collect.txt" | LC_ALL=C sort -u >"$WORK/files.txt"
total=$(wc -l <"$WORK/files.txt" | tr -d ' ')
[ "$total" -gt 0 ] || { keep_work=1; printf 'gen-test-input-map: pytest collected no test files\n' >&2; exit 1; }

: >"$WORK/rows.tsv"
failed=""
i=0
while IFS= read -r f; do
  i=$((i + 1))
  printf '[%d/%d] %s\n' "$i" "$total" "$f" >&2
  raw="$WORK/raw-$i.tsv"
  rc=0
  PYTHONPATH="$HERE/lib${PYTHONPATH:+:$PYTHONPATH}" PLC_TRACE_OUT="$raw" \
    python3 -m pytest "$f" -q -p test_input_tracer </dev/null >>"$LOG" 2>&1 || rc=$?
  if [ "$rc" -ne 0 ]; then
    failed="$failed$f (pytest exit $rc)"$'\n'
    continue
  fi
  # Every traced test file reads its own module. No such row = the tracer never armed.
  if ! awk -F'\t' -v f="$f" '$1 == f && $2 == "r" { found = 1 } END { exit !found }' "$raw"; then
    failed="$failed$f (the tracer recorded no read of the file itself)"$'\n'
    continue
  fi
  awk -F'\t' -v OFS='\t' -v f="$f" '{ print f, $1, $2 }' "$raw" >>"$WORK/rows.tsv"
done <"$WORK/files.txt"

if [ -n "$failed" ]; then
  keep_work=1
  printf 'gen-test-input-map: refusing to write %s -- these test files did not trace cleanly:\n%s' \
    "$OUT" "$failed" >&2
  printf 'pytest output: %s\n' "$LOG" >&2
  exit 1
fi

git ls-files -z | tr '\0' '\n' >"$WORK/tracked.txt"
mkdir -p "$(dirname "$OUT")"
# Written next to the real map (same filesystem, so `mv` is atomic) -- or into the work dir in
# --check mode, which never touches the pinned map.
if [ "$MODE" = check ]; then tmp="$WORK/map.tsv"; else
  tmp="$(mktemp "$(dirname "$OUT")/.test-input-map.tsv.XXXXXX")"; fi
if ! {
  printf 'test-file\tinput-path\tvia\ttracked\n'
  awk -F'\t' -v OFS='\t' '
    NR == FNR { tracked[$0] = 1; next }
    $3 == "r" { via = "direct" }
    $3 == "x" { via = "subprocess" }
    $3 != "r" && $3 != "x" { printf "unknown tracer mode %s on %s\n", $3, $0 > "/dev/stderr"; bad = 1; next }
    { print $1, $2, via, (($2 in tracked) ? "yes" : "no") }
    END { exit bad }
  ' "$WORK/tracked.txt" "$WORK/rows.tsv" | LC_ALL=C sort -u
} >"$tmp"; then
  rm -f "$tmp"
  printf 'gen-test-input-map: failed while assembling the map; %s untouched\n' "$OUT" >&2
  exit 1
fi
if [ "$MODE" = check ]; then
  # COMPLETENESS (the completeness criterion): every (test file, path) this run saw must be named by the pinned map.
  # Only that direction fails: a row the pinned map has and this run did not see is stale but safe
  # (it can only over-select), so it is counted, not failed on.
  [ -r "$OUT" ] || { printf 'gen-test-input-map --check: no pinned map at %s\n' "$OUT" >&2; exit 1; }
  export LC_ALL=C
  tail -n +2 "$OUT" | cut -f1,2 | sort -u >"$WORK/pinned.pairs"
  tail -n +2 "$tmp" | cut -f1,2 | sort -u >"$WORK/seen.pairs"
  comm -13 "$WORK/pinned.pairs" "$WORK/seen.pairs" >"$WORK/missing.pairs"
  extra=$(comm -23 "$WORK/pinned.pairs" "$WORK/seen.pairs" | wc -l | tr -d ' ')
  if [ -s "$WORK/missing.pairs" ]; then
    printf 'gen-test-input-map --check: INCOMPLETE -- %d read(s) the pinned map does not name:\n' \
      "$(wc -l <"$WORK/missing.pairs" | tr -d ' ')" >&2
    cat "$WORK/missing.pairs" >&2
    printf 'regenerate: /bin/bash scripts/gen-test-input-map.sh\n' >&2
    exit 1
  fi
  printf 'gen-test-input-map --check: complete -- every read of %d test files is in the map' "$total" >&2
  printf ' (%s pinned row(s) not seen this run: stale, never a miss)\n' "$extra" >&2
  exit 0
fi

mv "$tmp" "$OUT"
# FINGERPRINT (the freshness criterion). Line 1: the map's own git blob -- a hand edit changes it, and the
# close-gate invariant compares only this line. Then one `input <blob> <path>` per file whose
# change could change which files a test opens: the tracer, this script, the conftest, every test
# file, and every CODE file the map lists as an input. A data file's content does not change what
# is opened, so it is not listed. The selector compares every input line and prints FULL while
# any is stale. git hash-object, not shasum: it is portable, and git is already required.
{
  printf '%s\n' scripts/lib/test_input_tracer.py scripts/gen-test-input-map.sh scripts/conftest.py
  cat "$WORK/files.txt"
  tail -n +2 "$OUT" | cut -f2 | grep -E "\\.($(printf '%s' "$CODE_SUFFIXES" | tr ' ' '|'))\$" || true
} | LC_ALL=C sort -u | while IFS= read -r f; do [ -f "$f" ] && printf '%s\n' "$f"; done \
  >"$WORK/fp.paths"
fptmp="$(mktemp "$(dirname "$FP")/.test-input-map.fingerprint.XXXXXX")"
if ! {
  printf 'map %s\n' "$(git hash-object "$OUT")"
  git hash-object --stdin-paths <"$WORK/fp.paths" | paste -d' ' - "$WORK/fp.paths" | sed 's/^/input /'
} >"$fptmp"; then
  rm -f "$fptmp"
  printf 'gen-test-input-map: wrote %s but could not write its fingerprint; the gate will say so\n' \
    "$OUT" >&2
  exit 1
fi
mv "$fptmp" "$FP"
printf 'gen-test-input-map: %s -- %d test files, %d rows; fingerprint %d inputs\n' \
  "${OUT#"$ROOT"/}" "$total" "$(($(wc -l <"$OUT") - 1))" "$(($(wc -l <"$FP") - 1))" >&2
