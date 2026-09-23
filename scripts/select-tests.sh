#!/usr/bin/env bash
# select-tests.sh — which test files could change result, given what changed.
#
#   select-tests.sh              changed paths on stdin
#   select-tests.sh --base REF   changed paths = git diff from merge-base(REF, HEAD) to HEAD
#
# --base sees COMMITTED changes only; the working tree is not consulted. It is the mode for CI:
# the selector computes the diff itself, and any git failure is FULL. STDIN is for a person or a
# test, and an empty stdin is taken at its word -- no changed paths, so only the permanent
# members. A caller that pipes a failed diff into stdin gets that; use --base instead.
#
# Prints either one line `FULL` (run everything; the reason goes to stderr) or the test files to
# run, one per line, sorted. Exit 0 either way: FULL is an answer, not an error.
# A test file DELETED in the change can appear in the set (the map's self-row names it): a caller
# that runs the set must drop names that no longer exist (ci-line.s2's concern, noted here).
#
# THE SET is the union of:
#   - LOOKUP: every test file with a map row (.claude/test-input-map.tsv) whose input-path is in the
#     changed set after EXPANSION over .claude/generator-edges.tsv (script · reads · writes): a
#     changed path a declared script reads makes what it writes count as changed, and the script
#     itself (so tests that run it are in scope) -- to a fixed point, since one generator's output
#     can be another's input.
#   - PERMANENT MEMBERS (a standing rule): every test file scripts/blind_spots.py flags, and every
#     test file with a `tracked=no` row (an untracked path, or a directory -- git indexes neither).
#     Their inputs are not fully known, so they run every time. MEASURED: 74 of 93 today.
#
# FULL when any of these holds (the design; its fallback 2 became the permanent-member rule above):
#   1  a changed path is in neither the map nor the edges table -- nothing knows who reads it;
#   3  the selection machinery changed: a declared script, scripts/lib/**, the tracer, the map
#      generator, this script, the detector, or either table;
#   4  the map or the edges table is missing, unreadable, headerless or malformed, or the map and
#      the table are one file, or the detector fails, or the map is STALE: its fingerprint
#      (.claude/test-input-map.fingerprint) names a code or test file that has changed since;
#   5  with --base: the checkout is shallow, or the merge-base cannot be resolved.
# Every bad input found in a review produced an empty set, exit 0, nothing on stderr. Now each
# one is FULL with a reason. Input lines lose a trailing CR. Files are told apart by FILENAME
# against ARGV, never against `awk -v` copies (-v processes escapes; FILENAME does not).
#
# Env overrides, for tests: TEST_INPUT_MAP, GENERATOR_EDGES, TEST_INPUT_FINGERPRINT (`none` skips
# the staleness check, and says so on stderr); SELECT_ROOT (the tree the detector
# reads and git runs in); BLIND_SPOT_FLAGS (a precomputed detector output, instead of running it).
# Envelope: bash + awk + sort + git, and python3 for the detector.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="${SELECT_ROOT:-$(cd "$HERE/.." && pwd)}"
MAP="${TEST_INPUT_MAP:-$ROOT/.claude/test-input-map.tsv}"
EDGES="${GENERATOR_EDGES:-$ROOT/.claude/generator-edges.tsv}"

full() { printf 'select-tests: FULL -- %s\n' "$*" >&2; printf 'FULL\n'; exit 0; }

base=""
case "${1:-}" in
  --base) [ -n "${2:-}" ] || full "--base needs a ref"; base="$2" ;;
  "") ;;
  *) full "unknown argument: $1" ;;
esac

for f in "$MAP" "$EDGES"; do
  [ -r "$f" ] && [ -f "$f" ] || full "cannot read $f"
done
[ "$MAP" -ef "$EDGES" ] && full "the map and the edges table are the same file: $MAP"
IFS= read -r header <"$MAP" || true
[ "$header" = "$(printf 'test-file\tinput-path\tvia\ttracked')" ] ||
  full "$MAP: first line is not the header 'test-file<TAB>input-path<TAB>via<TAB>tracked'"

work="$(mktemp -d "${TMPDIR:-/tmp}/select-tests.XXXXXX")"
trap 'rm -rf "$work"' EXIT

# STALENESS (fallback 4). The generator's fingerprint names the map's blob and the blob of every
# file whose change could change which files a test opens. Any mismatch means the map describes a
# tree that is gone, so nothing it says can be trusted: FULL, naming the first stale file. A data
# file's content is not in the fingerprint -- changing it does not change what is opened -- which
# is what lets a docs-only change be selected while a code change runs everything until the map is
# regenerated. TEST_INPUT_FINGERPRINT=none skips this, loudly, for fixtures that have no fingerprint.
FP="${TEST_INPUT_FINGERPRINT:-$ROOT/.claude/test-input-map.fingerprint}"
if [ "$FP" = none ]; then
  printf 'select-tests: staleness NOT checked (TEST_INPUT_FINGERPRINT=none)\n' >&2
else
  [ -r "$FP" ] && [ -f "$FP" ] || full "no fingerprint for the map ($FP) -- regenerate it"
  IFS= read -r fp_first <"$FP" || true
  [ "$fp_first" = "map $(git hash-object "$MAP")" ] ||
    full "$MAP does not match its fingerprint (hand-edited, or written without one)"
  # The path is everything after `input <blob> ` -- it may contain spaces (a review: `$3` cut
  # `some file.py` to `some`, and every run then called the map stale).
  tail -n +2 "$FP" | sed 's/^input [^ ]* //' >"$work/fp.paths"
  tail -n +2 "$FP" | awk '{ print $2 }' >"$work/fp.want"
  while IFS= read -r f; do
    [ -f "$ROOT/$f" ] || full "map is stale: $f no longer exists"
  done <"$work/fp.paths"
  (cd "$ROOT" && git hash-object --stdin-paths) <"$work/fp.paths" >"$work/fp.have" ||
    full "could not hash the fingerprint's inputs"
  # paste to a FILE, then awk the file. The pipeline this replaces was
  #   stale="$(paste ... | awk '$1 != $2 { ...; exit }')"
  # and under `set -euo pipefail` awk's early `exit` closed the pipe while paste was still writing:
  # paste died of SIGPIPE, pipefail made the substitution 141, and `set -e` killed the script BEFORE
  # `full` could print anything. MEASURED 2026-09-12 on the real repo: 1 of 3 runs exited 141 with an
  # EMPTY stdout -- which a caller reads as "run no tests", the one failure direction the design forbids. It
  # fired on the staleness path, i.e. on every change to a code input, and it grows more likely the
  # more inputs the fingerprint has (6 of 6 at 20k lines).
  paste -d' ' "$work/fp.want" "$work/fp.have" "$work/fp.paths" >"$work/fp.triples"
  stale="$(awk '$1 != $2 { sub(/^[^ ]* [^ ]* /, ""); print; exit }' "$work/fp.triples")"
  [ -z "$stale" ] || full "map is stale: $stale changed since the map was generated -- regenerate it"
fi

if [ -n "$base" ]; then
  [ "$(git -C "$ROOT" rev-parse --is-shallow-repository 2>/dev/null)" = "false" ] ||
    full "shallow checkout (or not a git tree): history before the fetch depth is unknown"
  mb="$(git -C "$ROOT" merge-base "$base" HEAD 2>/dev/null)" || full "no merge-base for $base"
  # --no-renames: git detects renames by default and --name-only then prints only the NEW path,
  # so a test that read the old one was silently dropped (a review, reproduced).
  # core.quotePath=false: otherwise a non-ASCII name comes out quoted and matches no map row.
  git -C "$ROOT" -c core.quotePath=false diff --no-renames --name-only "$mb" HEAD \
    >"$work/changed" || full "git diff failed"
else
  cat >"$work/changed"
fi

if [ -n "${BLIND_SPOT_FLAGS:-}" ]; then
  [ -r "$BLIND_SPOT_FLAGS" ] || full "cannot read BLIND_SPOT_FLAGS=$BLIND_SPOT_FLAGS"
  cp "$BLIND_SPOT_FLAGS" "$work/flags"
else
  python3 "$HERE/blind_spots.py" --root "$ROOT" --map "$MAP" --edges "$EDGES" \
    >"$work/flags" 2>"$work/flags.err" || full "blind-spot detector failed: $(head -1 "$work/flags.err")"
fi

# awk exit codes: 3 malformed edges row · 4 machinery changed · 5 unknown path. Reason on stderr.
rc=0
awk -F'\t' '
  BEGIN {
    split("scripts/gen-test-input-map.sh scripts/select-tests.sh scripts/blind_spots.py " \
          ".claude/generator-edges.tsv .claude/test-input-map.tsv " \
          ".claude/test-input-map.fingerprint", m, " ")
    for (i in m) machinery[m[i]] = 1
  }
  FILENAME == ARGV[1] {
    sub(/\r$/, "")
    if ($0 ~ /^#/ || $0 == "" || ($1 == "generator" && $2 == "reads" && $3 == "writes")) next
    if (NF != 3 || $1 == "" || $2 == "" || $3 == "") {
      printf "select-tests: %s:%d: an edges row needs exactly 3 non-empty tab-separated fields: %s\n",
        FILENAME, FNR, $0 > "/dev/stderr"
      code = 3; exit
    }
    n++; gen[n] = $1; rd[n] = $2; wr[n] = $3
    # A write-target is NOT known on its own: one no map row reads was "known" and selected
    # nothing, silently (a review). The map says who reads it, or nothing does.
    known[$1] = 1; known[$2] = 1
    machinery[$1] = 1
    next
  }
  FILENAME == ARGV[2] {
    if (FNR == 1) next
    rows++; t[rows] = $1; p[rows] = $2
    known[$2] = 1
    if ($4 == "no") permanent[$1] = 1
    next
  }
  FILENAME == ARGV[3] {
    sub(/\r$/, "")
    if ($0 == "") next
    if (($0 in machinery) || $0 ~ /^scripts\/lib\//) {
      printf "select-tests: the selection machinery changed: %s\n", $0 > "/dev/stderr"
      code = 4; exit
    }
    if (!($0 in known)) {
      printf "select-tests: nothing in the map or the edges table reads %s\n", $0 > "/dev/stderr"
      code = 5; exit
    }
    set[$0] = 1
    next
  }
  FILENAME == ARGV[4] {
    # No CR strip here, unlike ARGV[1] and ARGV[3], and that asymmetry is deliberate: MEASURED
    # 2026-09-12 against a CRLF flags file, `-F'\t'` puts the CR on the LAST field, never on $1, so
    # a flagged test file is still named correctly; a single-field line carries it on $1 but is
    # already malformed (NF < 2) and goes to FULL either way. The phase review proposed adding the
    # strip for symmetry; it was written, could not be made to fail, and was removed -- a line no
    # test can pin is how this repository grows guards nobody has proven.
    if ($0 == "") next
    if (NF < 2 || $1 !~ /\.py$/) {
      printf "select-tests: flags line %d is not <test-file.py><TAB><category>...: %s\n", FNR, $0 > "/dev/stderr"
      code = 6; exit
    }
    permanent[$1] = 1; next
  }
  END {
    if (code) exit code
    do {
      grew = 0
      for (i = 1; i <= n; i++) if (rd[i] in set) {
        if (!(gen[i] in set)) { set[gen[i]] = 1; grew = 1 }
        if (wr[i] != "-" && !(wr[i] in set)) { set[wr[i]] = 1; grew = 1 }
      }
    } while (grew)
    for (i = 1; i <= rows; i++) if (p[i] in set) print t[i]
    for (x in permanent) print x
  }
' "$EDGES" "$MAP" "$work/changed" "$work/flags" >"$work/out" || rc=$?
case "$rc" in
  0) LC_ALL=C sort -u "$work/out" ;;
  3) full "malformed edges table" ;;
  4) full "the selection machinery changed" ;;
  5) full "a changed path nothing knows about" ;;
  6) full "malformed blind-spot flags" ;;
  *) full "awk failed ($rc)" ;;
esac
