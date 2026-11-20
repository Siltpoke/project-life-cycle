#!/usr/bin/env bash
# Invariant: the SKILL.md diet is a byte-conserving MOVE, not a deletion.
#
# WHAT THIS ASSERTS: the pre-move SKILL.md can be rebuilt, BYTE-FOR-BYTE, from the current slim
# SKILL.md plus every moved block pulled from its destination reference and spliced back at its
# pointer line. If that reconstruction equals the pinned pre-move git blob, every byte of the
# original is accounted for and its ordering preserved -- the move lost nothing. It also checks
# that each pointer left behind is a real "when to open X" signpost (short + names its dest), not a
# summary that makes the agent never open the reference (cross-check A failure mode).
#
# WHY IT EXISTS: the diet relocates ~half of the always-injected SKILL.md (116,385 B) into
# load-on-demand references/*.md to shrink the per-turn injection, preserving all information. No
# existing invariant guards SKILL.md PROSE (detailed-bytes-frozen covers a frozen byte set, not the
# whole file; the weld guard covers bullet structure). This is net-new and is the keystone of the
# phase: without it, a move that silently drops or garbles a block looks identical to a clean one.
#
# THE PRE-MOVE IMAGE IS A PINNED GIT BLOB, NEVER A FILE COPY (cross-check A): the manifest header
# carries `# preimage-blob: <40-hex>` and reconstruction is judged against `git cat-file blob
# <sha>`. A copy on disk could be post-edit, or from the stale core.bare main checkout, or a
# self-certifying manifest's own digest. The blob is immutable and external to the manifest.
#
# HONEST BOUNDARY (stated, not left to be discovered):
#   * This guard owns reconstruction byte-equality + pointer shape + manifest/dest grammar + a
#     marker-leak check. It deliberately does NOT re-implement the structural asserts that EXISTING
#     DECLARED invariants already enforce in the same close-gate check-8 run:
#       - frozen byte set unmoved ...... scripts/invariants/detailed-bytes-frozen.sh
#       - step-enforcement pin+table ... scripts/invariants/step-enforcement-table-current.sh
#       - no welded bold bullet ........ scripts/invariants/no-welded-bold-bullets.sh
#       - single adoption sentinel ..... scripts/invariants/adoption-rule-single-source.sh
#       - plc-p34 blocks in place ..... scripts/invariants/no-stored-position.sh +
#                                        scripts/invariants/acquire-shape-and-steal-oracle.sh
#     Duplicating an oracle is a repo anti-pattern (aim the review at the oracle, not a copy).
#   * The pointer SHAPE check proves a pointer is SHORT and NAMES its dest. It does NOT prove the
#     prose is semantically non-summarizing -- a terse-but-misleading pointer under the length cap
#     still passes. Length + dest-naming is a mechanical proxy for "a when-to-open signpost".
#   * Reconstruction is line-based: it assumes every moved block and the pre-move file are composed
#     of newline-terminated lines (true for this markdown). A block that did not end on a line
#     boundary would surface as a byte mismatch, not a silent pass.
#   * It judges the WORKING-TREE files, not any commit. "Same-commit" coupling (e.g. step-
#     enforcement) is the other invariants' job.
#
# ENVELOPE: bash 3.2 + grep/awk/sed/cmp + git cat-file only (jq-only gate envelope; no jq, no
# python3, no bash-4 constructs such as `declare -A`).
# Exit 0 = clean, 1 = a move/pointer/grammar violation, 3 = CANNOT-RUN (missing/unreadable file,
# unresolvable pinned blob) -- never a silent pass on a broken read.
set -uo pipefail

GREP=/usr/bin/grep
[ -x "$GREP" ] || GREP=grep

SKILL="skills/project-lifecycle/SKILL.md"
MANIFEST=".claude/skill-move-manifest.tsv"

# ---- arg parse ---------------------------------------------------------------------------------
while [ $# -gt 0 ]; do
  case "$1" in
    --check) shift ;;
    --skill) SKILL="$2"; shift 2 ;;
    --manifest) MANIFEST="$2"; shift 2 ;;
    *) echo "usage: skill-reconstruction.sh --check [--skill PATH] [--manifest PATH]" >&2; exit 64 ;;
  esac
done

cannot_run() { echo "CANNOT-RUN skill-reconstruction: $1"; exit 3; }
fail()       { echo "FAIL skill-reconstruction: $1"; exit 1; }

[ -f "$SKILL" ]    || cannot_run "$SKILL not found"
[ -r "$SKILL" ]    || cannot_run "$SKILL not readable"
[ -f "$MANIFEST" ] || cannot_run "manifest $MANIFEST not found"
[ -r "$MANIFEST" ] || cannot_run "manifest $MANIFEST not readable"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# dest_file paths in the manifest are relative to the SKILL file's own directory, so SKILL.md can
# keep its `references/X` pointer convention and the pointer-shape check can match that same string
# -- NOT relative to the process cwd (the gate runs from the repo root, the skill lives three dirs
# down). Opens are prefixed with this base; the manifest string and the pointer stay unprefixed.
DESTBASE="$(dirname "$SKILL")"

# ---- pinned pre-move blob ----------------------------------------------------------------------
SHA="$($GREP -m1 '^# preimage-blob:' "$MANIFEST" | sed 's/^# preimage-blob:[[:space:]]*//' | tr -d '[:space:]')"
printf '%s' "$SHA" | $GREP -qE '^[0-9a-f]{40}$' \
  || cannot_run "manifest has no valid '# preimage-blob: <40-hex>' header (got '${SHA}')"
git cat-file blob "$SHA" > "$WORK/preimage" 2>/dev/null \
  || cannot_run "pinned pre-move blob $SHA is not resolvable (git cat-file failed)"

# ---- read + validate manifest rows -------------------------------------------------------------
# Parallel indexed arrays (bash-3.2: no associative arrays). One entry per data row.
IDS=(); DESTS=(); ORDERS=(); PTRS=()
rownum=0
while IFS= read -r raw || [ -n "$raw" ]; do
  case "$raw" in ''|'#'*) continue ;; esac
  rownum=$((rownum + 1))
  ncol="$(printf '%s' "$raw" | awk -F'\t' '{print NF}')"
  [ "$ncol" = 4 ] || fail "manifest row $rownum is not 4 tab-separated columns (got $ncol): $raw"
  bid="$(printf '%s' "$raw" | cut -f1)"
  dest="$(printf '%s' "$raw" | cut -f2)"
  order="$(printf '%s' "$raw" | cut -f3)"
  ptr="$(printf '%s' "$raw" | cut -f4)"
  [ -n "$bid" ]  || fail "manifest row $rownum has empty block_id: $raw"
  [ -n "$dest" ] || fail "manifest row $rownum has empty dest_file: $raw"
  printf '%s' "$order" | $GREP -qE '^[0-9]+$' \
    || fail "manifest row $rownum insert_order must be a non-negative integer (got '$order')"
  [ -n "$ptr" ]  || fail "manifest row $rownum has empty pointer_line: $raw"
  IDS+=("$bid"); DESTS+=("$dest"); ORDERS+=("$order"); PTRS+=("$ptr")
done < "$MANIFEST"

# unique block_id
if [ "${#IDS[@]}" -gt 0 ]; then
  dup="$(printf '%s\n' "${IDS[@]}" | sort | uniq -d | head -1)"
  [ -z "$dup" ] || fail "duplicate block_id '$dup' in manifest (ids must be unique)"
fi

# ---- per-row: pointer shape, pointer uniqueness, dest block extraction, marker leak ------------
i=0
while [ "$i" -lt "${#IDS[@]}" ]; do
  bid="${IDS[$i]}"; dest="${DESTS[$i]}"; ptr="${PTRS[$i]}"

  # pointer SHAPE: names its destination, and is short (a signpost, not a reproduced body)
  case "$ptr" in
    *"$dest"*) : ;;
    *) fail "pointer for block '$bid' does not name its destination '$dest' (points nowhere): $ptr" ;;
  esac
  [ "${#ptr}" -le 200 ] \
    || fail "pointer for block '$bid' is ${#ptr} bytes (> 200) -- a pointer must be a short 'when to open X' signpost, not a summary of the moved body: $ptr"

  # pointer UNIQUENESS in the slim SKILL (exactly one splice point)
  n="$($GREP -cxF -- "$ptr" "$SKILL" 2>/dev/null || true)"
  [ "$n" = 1 ] \
    || fail "pointer for block '$bid' matches $n line(s) in $SKILL (need exactly 1 unambiguous splice point): $ptr"

  # dest exists + exactly one delimited block for this id (path resolved relative to the skill dir)
  destpath="$DESTBASE/$dest"
  [ -f "$destpath" ] || cannot_run "dest_file '$dest' for block '$bid' is not on disk at '$destpath' (broken read)"
  [ -r "$destpath" ] || cannot_run "dest_file '$dest' for block '$bid' is not readable at '$destpath'"
  nopen="$($GREP -cxF -- "<!-- plc-move:$bid -->" "$destpath" 2>/dev/null || true)"
  nclose="$($GREP -cxF -- "<!-- /plc-move:$bid -->" "$destpath" 2>/dev/null || true)"
  { [ "$nopen" = 1 ] && [ "$nclose" = 1 ]; } \
    || fail "dest '$dest' must contain exactly one delimited block for '$bid' (found $nopen open / $nclose close markers)"

  # extract the block body (strictly between the markers) to a temp file, byte-faithful line-wise
  awk -v id="$bid" '
    $0=="<!-- plc-move:" id " -->"{inblk=1; next}
    $0=="<!-- /plc-move:" id " -->"{inblk=0; next}
    inblk{print}
  ' "$destpath" > "$WORK/block.$i"

  # marker leak: a bracket marker that belongs in SKILL.md must not ride out inside a moved block
  if $GREP -qE 'plc-review-digest' "$WORK/block.$i" 2>/dev/null; then
    fail "moved block '$bid' carries a plc-p31/plc-p34 bracket marker into '$dest' -- such markers must stay in $SKILL"
  fi

  i=$((i + 1))
done

# ---- whole-file reconstruction -----------------------------------------------------------------
# Stream the slim SKILL line by line; when a line is a pointer, emit its block instead, else the
# line verbatim. Linear pointer search (few rows). Block content is emitted directly and never
# re-matched, so a block line that happens to equal a pointer cannot trigger a nested splice.
: > "$WORK/recon"
while IFS= read -r line || [ -n "$line" ]; do
  j=0; matched=-1
  while [ "$j" -lt "${#PTRS[@]}" ]; do
    if [ "$line" = "${PTRS[$j]}" ]; then matched="$j"; break; fi
    j=$((j + 1))
  done
  if [ "$matched" -ge 0 ]; then
    cat "$WORK/block.$matched" >> "$WORK/recon"
  else
    printf '%s\n' "$line" >> "$WORK/recon"
  fi
done < "$SKILL"

if cmp -s "$WORK/preimage" "$WORK/recon"; then
  echo "PASS skill-reconstruction: ${#IDS[@]} moved block(s) reconstruct $SKILL byte-for-byte to pinned blob ${SHA:0:12}"
  exit 0
fi

echo "FAIL skill-reconstruction: reconstruction does NOT match the pinned pre-move blob ${SHA:0:12}"
echo "  (slim $SKILL + ${#IDS[@]} moved block(s) spliced at their pointers != git blob $SHA)"
echo "  first byte difference:"
cmp "$WORK/preimage" "$WORK/recon" 2>&1 | sed 's/^/    /'
exit 1
