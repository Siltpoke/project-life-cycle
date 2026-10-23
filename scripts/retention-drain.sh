#!/usr/bin/env bash
# scripts/retention-drain.sh — deterministic, no-LLM archival drain for the hot/cold model.
# Two manifest keys under `retention` in .claude/close-gate.json steer a monolith drain, both
# keyed by the file's basename WITH its extension:
#   "order": { "CHANGELOG.md": "newest-first" }   which end is old; absent = oldest-first, the same
#                                                 end today's drain evicts from. NOT "nothing
#                                                 changes on upgrade": an undeclared document whose
#                                                 heading dates contradict that default now refuses
#                                                 (exit 3) instead of draining, until it is declared.
#   "non_entry_headings": { "CHANGELOG.md": [ "How to read this file" ] }
#                                                 heading TEXTS (no '## ' prefix) that are structure,
#                                                 not entries, and are never evicted wherever they
#                                                 sit. '[Unreleased]' is pinned without declaring it.
# Both fail closed: a non-literal order, a non-array-of-strings list, or a heading declared with its
# '## ' prefix is a usage error that moves zero bytes. Heading DATES never decide the ordering —
# they only raise a contradiction alarm against the declaration (exit 3).
# Usage: retention-drain.sh drain <monolith.md> [rollover_cap_kb]   (keep the LAST 3 '## ' entries
#   NOTE: pass the DOC'S OWN KB cap as rollover_cap_kb (status=30, qa-log=50, RESUME=25) so the 4×
#   roll-over threshold matches the caps table; omitting it defaults to 25 (RESUME) for every doc —
#   the milestone-done drain step invokes once per doc WITH that doc's cap. Benign if wrong (early
#   segment split, never data loss) but the caller contract is: cap arg == this doc's hot cap.
#                                                                     = active+2; older head entries
#                                                                     move byte-verbatim to the
#                                                                     archive, written newest-first)
#        retention-drain.sh drain journal                           (compile docs/journal.d/*.md
#                                                                     newest-first, then delete them;
#                                                                     idempotent on retry)
#        retention-drain.sh drain qa-log                             (compile docs/qa-log.d/*.md
#                                                                     oldest-first (newest = last
#                                                                     heading) INTO THE HOT monolith
#                                                                     docs/brainstorming-qa-log.md —
#                                                                     byte-verified before fragments
#                                                                     are deleted — then drain_monolith
#                                                                     evicts old entries to archive;
#                                                                     idempotent)
#        retention-drain.sh drain legacy <file>                     (move a whole pre-convention
#                                                                     tail, script-chunked, verbatim
#                                                                     — never LLM-rewritten)
#        retention-drain.sh archive-working <path> [archive_dir]    (move a single closed-track
#                                                                     working doc — spec/plan — to
#                                                                     <archive_dir>/working/<rel>,
#                                                                     byte-verbatim, via `git mv`
#                                                                     when tracked else plain `mv`;
#                                                                     NEVER deletes; idempotent on
#                                                                     retry; refuses screenshots/)
# Deliberately does NOT `set -e`. The old invariant — "content/keep-window decisions must never
# abort a drain" — is no longer true and is replaced by this one:
#   exits non-zero on I/O errors, on usage errors (1), and on an ordering it cannot safely
#   resolve (3) — never on "nothing to drain".
# Exit 3 is distinct from 1 so a caller can tell "I refused to guess" from "I failed". A drain
# that guesses the wrong end archives the entries the operator most needs, which is worse than
# not draining; a drain that refuses says so, names the evidence, and moves zero bytes.
set -uo pipefail

M=".claude/close-gate.json"
# A manifest that exists but cannot be PARSED must not read as a manifest that is absent. Every
# reader below swallows jq's stderr and returns empty on error, so one stray comma would silently
# revert a declared ordering to the default and drop every protected heading — malformed
# protection failing OPEN, which is the direction that archives the thing the operator declared.
if [ -f "$M" ]; then
  command -v jq >/dev/null 2>&1 || { echo "✗ jq is not installed — this script's whole dependency envelope is bash + jq"; exit 1; }
  jq empty "$M" 2>/dev/null || { echo "✗ $M is not valid JSON — refusing to run rather than treating a broken manifest as an absent one"; exit 1; }
fi
g() { [ -f "$M" ] && jq -r ".retention.$1 // empty" "$M" 2>/dev/null; }
# Per-document readers. Two, because one cannot serve both shapes: `gk` reads a scalar
# (retention.order), `gka` streams an array one element per line (retention.non_entry_headings)
# — `jq -r` on an array key returns a pretty-printed multi-line JSON blob, not its elements.
# `--arg` in both so a basename holding jq-significant characters cannot alter the query.
# The key is the source file's basename WITH its extension; see drain_monolith's `base`.
gk()  { [ -f "$M" ] && jq -r --arg k "$2" ".retention.$1[\$k] // empty" "$M" 2>/dev/null; }
gka() { [ -f "$M" ] && jq -r --arg k "$2" ".retention.$1[\$k][]? // empty" "$M" 2>/dev/null; }

AD="$(g archive_dir)"; AD="${AD:-docs/archive}"
# TRAILING SLASHES ARE STRIPPED, and it is not cosmetic. `$PID` is built by appending to `$AD`, so
# `archive_dir: "docs/archive/"` yields `docs/archive//.pre-images` -- a string that no path
# produced by `find` is ever equal to or prefixed by. Every place that EXCLUDES the ring by
# comparing against `$PID` then excludes nothing, and the last-copy check's durable set silently
# starts containing the ring: it finds every fragment in some older slot and refuses nothing. That
# is the fails-open mutant the second negative control exists for, reachable through configuration instead of a
# source edit. Normalise once, here, rather than at each comparison -- a rule applied at N sites is
# a rule that will be applied at N-1.
while :; do case "$AD" in */) AD="${AD%/}" ;; *) break ;; esac; done
case "$AD" in
  docs/*) : ;;
  *) echo "⚠ retention.archive-dir '$AD' outside docs/ — config error, falling back to docs/archive"; AD="docs/archive" ;;
esac
JD="$(g journal_dir)"; JD="${JD:-docs/journal.d}"
QD="$(g qa_log_dir)"; QD="${QD:-docs/qa-log.d}"
KEEP=3   # active + 2 most recent closed '## ' entries — the LAST 3 headings of the source

# NOT FOR `config`. This runs at load, BEFORE the command is parsed, so
# `retention-drain.sh config preimage_keep` used to CREATE `docs/archive` on a tree that has none --
# while the accessor's own header calls itself read-only and `preimage-keep-faces-agree.sh` runs it
# inside the close gate. "It moves no bytes" was true; "read-only" was not, and a gate with an
# undeclared filesystem side effect is something this repo would otherwise find out about later.
case "${1:-}" in
  config) : ;;
  *) mkdir -p "$AD" || { echo "✗ cannot create archive dir $AD"; exit 1; } ;;
esac

# newline-guard: never let an append land glued to the previous line
ensure_trailing_nl() {
  [ -s "$1" ] || return 0
  [ "$(tail -c1 "$1" | wc -l)" -eq 0 ] && printf '\n' >> "$1"
  return 0
}

pointer_stub() { # $1 = archive path   $2 = ordering note for the archived content
  printf '> Earlier entries archived verbatim (%s): → %s\n' "$2" "$1"
}

# ── pre-image ────────────────────────────────────────────────────────────────────
# A drain that FAILS is safe: the archive append is byte-verified before the source is
# touched. The dangerous run is the one that succeeds at the wrong thing — every check
# passes and the wrong bytes move. git is the cold-storage path for that case, and the SCOPE
# of that sentence is the whole point: git recovers a mutated file only where the drain's
# corpus is TRACKED, and only as of its last commit. This repo has tracked docs/ since p39,
# so here git is a real second copy for anything already committed — but not for an
# uncommitted edit, and not at all for an adopter who keeps its docs out of git.
# The reason that used to sit here read:
# > the wrong bytes move, and docs/ is gitignored so git recovers neither file
# True when written, retired by p39, and quoted rather than deleted: an unrecorded deletion is
# how the next reader rebuilds the wrong story out of the gap.
# The pre-image is the byte-for-byte state of every file a drain is about to mutate, captured
# before it mutates them, so `restore` can put the tree back exactly — which is what keeps this
# store load-bearing even where git IS a second copy.
PID="$AD/.pre-images"          # the store: numbered slots, never timestamped (a timestamp can collide)
PIX="$AD/.pre-images.log"      # the receipt — OUTSIDE the store on purpose, see below
PIKEEP="$(g preimage_keep)"; case "$PIKEEP" in ''|*[!0-9]*) PIKEEP=5 ;; esac
# FLOORED AT 1, BY REFUSING RATHER THAN BY CORRECTING. `preimage_keep: 0` means "keep no undo at
# all": the prune would evict every slot including the one this run just captured, so the drain
# would run with no way back -- the single state this script refuses everywhere else. Silently
# reading 0 as 5 would be the other kind of wrong: a declaration that does not do what it says,
# which is what the faces-agree invariant exists to stop. So it is an exit, and it names the key.
# `config` is exempt from the refusal below, and that exemption is load-bearing rather than tidy:
# the accessor's job is to REPORT the effective value, including a value that is out of range, so
# the declaration-time check can say "the effective value is 0" instead of "the accessor failed".
# Refusing here for every invocation would make that check's own floor branch unreachable, and an
# unreachable branch is an unguarded one. The drain paths still refuse.
if [ "$PIKEEP" -lt 1 ] && [ "${1:-}" != "config" ]; then
  echo "✗ retention.preimage_keep is $PIKEEP — a ring that keeps nothing is a drain with no undo"
  echo "  Declare at least 1 in .claude/close-gate.json (and in CLAUDE.md's retention: block)."
  exit 1
fi
PI_CAPTURED=0                  # one slot per invocation, not per internal call
PI_KEY=""                      # the slot this invocation captured, for failure messages to name
PI_PROTECT=""                  # a key the prune may never evict (the one being restored)

# The receipt lives beside the store, not inside it. If it lived inside, an unwritable store
# would make the refusal it is supposed to record unwritable too — and the design's recorded flip
# condition ("capture failures turn out not to be rare") would stay unobservable in exactly
# the situation that would trigger it. Found by the fixture, before the code existed.
preimage_log() { # $1 = key ('-' when none)  $2 = mode  $3 = status  $4 = detail
  printf '%s\t%s\t%s\t%s\t%s\n' "$1" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$2" "$3" "$4" \
    >> "$PIX" 2>/dev/null || return 0   # a missing receipt must never be why a drain dies
}

# $1 = key. Puts every path the slot names back the way it was, and verifies it did.
drain_restore() {
  local key="$1" slot stage st rel d n=0 bad=0
  local -a paths=()
  case "$key" in ''|*[!0-9]*) echo "✗ restore: key must be a slot number, got '$key'"; return 1 ;; esac
  slot="$PID/$key"
  [ -d "$slot" ] && [ -f "$slot/manifest" ] || {
    echo "✗ restore: no pre-image $key under $PID"; return 1; }
  # Validate BEFORE touching anything: a slot missing the bytes it claims is not a slot to
  # restore from, and finding that out halfway would leave a tree that is neither state.
  while IFS="$(printf '\t')" read -r st rel; do
    [ -n "$rel" ] || continue
    case "$st" in
      present) [ -f "$slot/files/$rel" ] || { echo "✗ restore: $key is incomplete — no bytes for $rel"; return 1; } ;;
      absent)  : ;;
      *)       echo "✗ restore: $key has a malformed manifest line ($st)"; return 1 ;;
    esac
    paths+=("$rel")
  done < "$slot/manifest"
  [ "${#paths[@]}" -gt 0 ] || { echo "✗ restore: $key names no paths"; return 1; }

  # Stage first: the capture below mints a slot and prunes, and the prune must not be able to
  # remove the slot being read. PI_PROTECT is the second belt on the same braces.
  stage="$(mktemp -d)" || { echo "✗ restore: mktemp -d failed"; return 1; }
  cp -R "$slot/." "$stage/" 2>/dev/null || { echo "✗ restore: cannot stage $key"; rm -rf "$stage"; return 1; }

  # Undo-the-undo. The gap between a bad drain and its discovery routinely contains
  # legitimate later writes; overwriting them blind would trade one silent data-loss class for
  # another. Same routine as the drain's, deliberately — a second implementation is the thing
  # this escape route exists to prevent.
  PI_PROTECT="$key"
  # Array, not word-splitting: a restored path containing a space would otherwise split into
  # nonexistent fragments, all recorded `absent`, and the pre-restore capture would report
  # success while protecting nothing — the same Critical the two drain call sites carried.
  capture_preimage "restore $key" "${paths[@]}" || { rm -rf "$stage"; return 1; }

  while IFS="$(printf '\t')" read -r st rel; do
    [ -n "$rel" ] || continue
    case "$st" in
      present)
        mkdir -p "$(dirname "$rel")" 2>/dev/null
        cp -p "$stage/files/$rel" "$rel" 2>/dev/null || { echo "✗ restore: cannot write $rel"; bad=1; continue; }
        cmp -s "$stage/files/$rel" "$rel" || { echo "✗ restore: $rel differs after restore"; bad=1; continue; }
        ;;
      absent)
        # ABSENCE IS STATE. A first drain creates its archive, so that path was recorded absent —
        # leaving it in place would pass a per-file check and still leave a tree the pre-drain
        # tree never had. Exposed by a fixture before this path existed to get it wrong.
        rm -f "$rel" 2>/dev/null
        # A directory that only existed to hold files the pre-drain tree did not have must go
        # too, or the tree still differs. Only if EMPTY, and never above the archive dir.
        d="$(dirname "$rel")"
        while [ "$d" != "." ] && [ "$d" != "/" ] && [ "$d" != "$AD" ]; do
          rmdir "$d" 2>/dev/null || break
          d="$(dirname "$d")"
        done
        [ ! -e "$rel" ] || { echo "✗ restore: $rel should be absent and still exists"; bad=1; }
        ;;
    esac
    n=$((n + 1))
  done < "$stage/manifest"
  rm -rf "$stage"
  [ "$bad" -eq 0 ] || { echo "✗ restore $key: the tree does not match the pre-image"; return 1; }
  echo "  restored $n path(s) from pre-image $key (byte-verified)"
  return 0
}

# max(highest slot on disk, highest key EVER issued per the receipt) + 1. `mkdir` remains the
# collision check; this only decides which number to try.
#
# Consulting the receipt as well as the disk is deliberate. With `max on disk + 1` alone,
# deleting slot 0002 — an operator tidying up, or a prune interrupted mid-run — made the next
# capture mint `0002` again; the receipt is append-only, so it then carried two `0002` lines for
# two unrelated captures, and `restore 0002` silently returned whichever one happened to occupy
# the directory. A key that can mean two things is not an audit trail.
# Files created AFTER the capture, by a step running inside the same invocation, belong in the
# current slot's manifest as `absent` — otherwise `restore` puts the captured files back and
# leaves the new ones behind, and the tree is neither state. `check_rollover` is the case that
# forced this: it runs right after drain_monolith (so PI_CAPTURED is already 1, and a second
# capture would be wrong), writes a segment directory plus an index, and rewrites the archive to
# a stub. Without it, restore would report byte-verified with an orphaned directory left
# on disk.
preimage_note_absent() {
  [ -n "$PI_KEY" ] && [ -f "$PID/$PI_KEY/manifest" ] || return 0
  local p
  for p in "$@"; do
    [ -n "$p" ] || continue
    printf 'absent\t%s\n' "${p#./}" >> "$PID/$PI_KEY/manifest" 2>/dev/null || return 0
  done
  return 0
}

preimage_next_key() {
  local max=0 d n
  for d in "$PID"/[0-9]*; do
    [ -d "$d" ] || continue
    n="$(basename "$d")"
    case "$n" in ''|*[!0-9]*) continue ;; esac
    n=$((10#$n)); [ "$n" -gt "$max" ] && max="$n"
  done
  if [ -f "$PIX" ]; then
    while IFS="$(printf '\t')" read -r n _; do
      case "$n" in ''|*[!0-9]*) continue ;; esac
      n=$((10#$n)); [ "$n" -gt "$max" ] && max="$n"
    done < "$PIX"
  fi
  printf '%04d\n' $((max + 1))
}

# ── last-copy refusal ────────────────────────────────────────────────────────────
# The ring is an undo buffer, and an undo buffer holding the ONLY copy of something is not an undo
# buffer any more -- it is unacknowledged primary storage with a delete queue `preimage_keep` deep.
# So before an eviction destroys a slot, every fragment-source file in that slot is checked for a
# copy OUTSIDE the ring, and a slot holding a last copy is refused rather than evicted.
#
# CONTENT, NOT A MARKER. The drain writes `<!-- fragment: <path> -->` above each block it appends,
# and that marker is keyed by PATH: this repo's live state holds fragments whose marker is present
# while the archived bytes differ. A marker-only test would report a copy that is not there, which
# is the fail-OPEN direction -- it would delete the thing it was asked to protect.
#
# WHAT COUNTS AS A COPY, MEASURED AND NOT ASSUMED -- the first version of this check got this wrong
# in the direction that bricks the drain. A fragment does NOT survive archival as one contiguous
# run of lines inside one file, for two independent reasons:
#   [1] `drain_monolith` slices the monolith entry-by-entry and reassembles NEWEST-FIRST, so a
#       fragment's own entries come back in a different order with other phases' entries between
#       them. Every byte is present; the fragment-shaped run is not.
#   [2] `check_rollover` segments an archive with `split -l 2000`, which cuts at a LINE COUNT and
#       therefore cuts THROUGH entries -- one segment can end mid-entry and the next carry
#       the rest. No single file holds that entry contiguously; the series does.
# Whole-file contiguity scored most ring fragments as last copies while every one
# of them was in the archive.
# The refusal would have blocked the next drain and every `restore`.
# So: the needle is split at `## ` boundaries and EVERY block must appear contiguously in some
# durable STREAM, where a `part-??.md` series counts as ONE stream because `split -l` is exactly
# what cut it into files.
#
# WHERE THE DURABLE SET COMES FROM, and the one exclusion that keeps the check from being vacuous:
# the drain's own config -- the hot qa-log monolith, the live fragment directories, and every `.md`
# under `$AD` -- MINUS `$PID`, which lives INSIDE `$AD`. A set built recursively over `$AD` would
# find every fragment in some older slot, never refuse once, and look exactly like a check that
# works. That mutant is a required control, not a hypothetical.
#
# The live fragment directories are in the set deliberately: a pre-drain snapshot of a document
# still sitting in `$QD`/`$JD` is not a last copy and must not block.
#
# $1 = a scratch directory the caller owns. Prints one path per stream; a segment series is
# materialised there as a single concatenation in `LC_ALL=C` suffix order, which is the order
# `split -l` assigned and therefore the order that reconstructs what it cut.
durable_streams() {
  local out="$1" f d series p i=0
  [ -f docs/brainstorming-qa-log.md ] && printf '%s\n' docs/brainstorming-qa-log.md
  for f in "$QD"/*.md "$JD"/*.md; do [ -f "$f" ] && printf '%s\n' "$f"; done
  [ -d "$AD" ] || return 0
  while IFS= read -r d; do
    [ -n "$d" ] || continue
    case "$d" in "$PID"|"$PID"/*) continue ;; esac
    series="$(find "$d" -maxdepth 1 -type f -name 'part-??.md' 2>/dev/null | LC_ALL=C sort)"
    if [ -n "$series" ]; then
      i=$((i + 1))
      : > "$out/series$i"
      while IFS= read -r p; do [ -n "$p" ] && cat "$p" >> "$out/series$i"; done <<EOF
$series
EOF
      printf '%s\n' "$out/series$i"
    fi
    while IFS= read -r p; do
      [ -n "$p" ] || continue
      case "${p##*/}" in part-??.md) continue ;; esac
      printf '%s\n' "$p"
    done <<EOF
$(find "$d" -maxdepth 1 -type f -name '*.md' 2>/dev/null | LC_ALL=C sort)
EOF
  done <<EOF
$(find "$AD" -type d 2>/dev/null | LC_ALL=C sort)
EOF
  return 0
}

# Does every `## `-delimited block of this file appear CONTIGUOUSLY in some one of the given
# streams? Per BLOCK, not per file, because an entry is the unit the archive moves: see the
# measurement above. Blocks may land in different streams; what may not happen is a block that is
# nowhere.
#
# ERROR DIRECTION, stated because it is a choice and not an accident: the scan backtracks naively,
# so a pattern whose own prefix recurs inside itself can be MISSED. A miss reads as "no copy
# outside the ring", which REFUSES the eviction. THE COST OF A REFUSAL IS THE WHOLE DRAIN, not one
# kept slot: `preimage_prune` returning 1 makes `capture_preimage` return 1, which makes the drain
# exit non-zero having moved zero bytes. The earlier version of this sentence said the cost was
# "a kept slot, never a deleted one" -- narrower than the consequence, in the comment whose only
# job is to state the consequence. The direction is still the right one, because the other
# direction deletes; it is not the cheap one.
#
# An empty file reports as copied, because evicting it loses nothing.
content_copied_outside_ring() { # $1 = needle file, rest = streams to search
  local needle="$1"; shift
  [ -s "$needle" ] || return 0
  [ "$#" -gt 0 ] || return 1
  awk '
    FNR == NR {
      if ($0 ~ /^## /) nb++
      if (nb == 0) nb = 1
      len[nb]++; blk[nb SUBSEP len[nb]] = $0
      next
    }
    FNR == 1 { for (b = 1; b <= nb; b++) if (!done[b]) m[b] = 0 }
    {
      for (b = 1; b <= nb; b++) {
        if (done[b]) continue
        if ($0 == blk[b SUBSEP (m[b] + 1)]) { if (++m[b] == len[b]) done[b] = 1 }
        else m[b] = ($0 == blk[b SUBSEP 1]) ? 1 : 0
      }
    }
    END {
      for (b = 1; b <= nb; b++) if (!done[b]) exit 1
      exit 0
    }
  ' "$needle" "$@"
}

# $1 = slot key, $2.. = the durable streams. Prints the first fragment-source path in that slot
# whose content exists nowhere outside the ring, and exits 0. Exits 1 when the slot is safe to
# evict. The streams are built ONCE per prune by the caller: materialising them per victim would
# re-concatenate the whole archive for every file in every slot.
slot_holds_last_copy() {
  local dir="$PID/$1/files" f rel
  shift
  [ -d "$dir" ] || return 1
  local hay=("$@")
  # No durable file at all means nothing is copied anywhere, so every fragment in the slot is a
  # last copy. Reported as the first one found rather than treated as "nothing to check".
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    rel="${f#"$dir"/}"
    case "$rel" in "$QD"/*|"$JD"/*) ;; *) continue ;; esac
    if [ "${#hay[@]}" -gt 0 ]; then
      content_copied_outside_ring "$f" "${hay[@]}" && continue
    fi
    printf '%s\n' "$rel"
    return 0
  done <<EOF
$(find "$dir" -type f -name '*.md' 2>/dev/null | sort)
EOF
  return 1
}

# Runs AFTER a successful capture, never before. Pruning first and then refusing would
# destroy the oldest pre-image on behalf of a drain that never happened.
preimage_prune() {
  local slots n excess d
  slots="$(for d in "$PID"/[0-9]*; do [ -d "$d" ] && basename "$d"; done | sort -n)"
  n="$(printf '%s\n' "$slots" | grep -c '[0-9]')"
  excess=$((n - PIKEEP))
  [ "$excess" -gt 0 ] || return 0
  # `PI_PROTECT` is the key currently being restored FROM. Evicting it mid-restore would delete
  # the thing being read, and across repeated restores from one key the store would eventually
  # eat its own source — F20 restores KEEP_N+1 times from a single key and would fail on the
  # fourth without this. Skipping it can leave one extra generation on disk; that is the correct
  # trade, because the alternative is losing the generation someone is actively using.
  # THE VICTIM LIST IS DECIDED ONCE, IN THIS SHELL, and both the check and the eviction read it.
  # The old loop ran inside `printf | while`, a subshell -- a refusal raised there could not reach
  # the caller, and this function ended `return 0` regardless. Deciding the list first takes the
  # subshell off the refusal's path instead of trying to carry a status out of one.
  local victims=() left="$excess" blocked
  while IFS= read -r d; do
    [ "$left" -gt 0 ] || break
    [ -n "$d" ] || continue
    [ "$d" = "$PI_PROTECT" ] && continue
    victims+=("$d")
    left=$((left - 1))
  done <<EOF
$slots
EOF
  [ "${#victims[@]}" -gt 0 ] || return 0
  # THE STREAMS ARE BUILT ONCE for the whole prune, in a scratch directory this function owns and
  # removes on every path out from here down. A segment series is concatenated there, so a block
  # `split -l` cut across two files is contiguous again -- see the measurement on `durable_streams`.
  local sdir hay=()
  sdir="$(mktemp -d "${TMPDIR:-/tmp}/plc-durable-XXXXXX")" || {
    echo "✗ cannot create a scratch directory for the last-copy check — refusing to prune"
    return 1
  }
  while IFS= read -r d; do [ -n "$d" ] && hay+=("$d"); done <<EOF
$(durable_streams "$sdir")
EOF
  # EVERY victim is checked before ANY is evicted. Checking and deleting in one pass would leave a
  # partial eviction behind the refusal, so the refusal would have already destroyed something.
  for d in "${victims[@]}"; do
    blocked="$(slot_holds_last_copy "$d" "${hay[@]+${hay[@]}}")" || continue
    echo "✗ pre-image slot $d holds the only copy of $blocked — refusing to evict it"
    echo "  The ring is an undo buffer, not storage. Get that content into a durable file (a"
    echo "  qa-log drain compiles a fragment into the hot monolith) and run again, or raise"
    echo "  retention.preimage_keep. Nothing was evicted and nothing was drained."
    preimage_log "$d" "prune" "REFUSED" "last copy: $blocked"
    rm -rf "${sdir:?}"
    return 1
  done
  rm -rf "${sdir:?}"
  # ONE RECEIPT LINE PER EVICTED SLOT, and it is counted and sized BEFORE the slot is gone --
  # afterwards there is nothing left to measure, which is the whole reason an eviction needs its
  # own line rather than an inference from a missing directory.
  #
  # THE STATUS IS NOT `OK`. `OK` means a capture happened today, and reusing it for an eviction
  # makes every reader that counts captures wrong -- a count of OK lines that no longer matches
  # the slots on disk.
  #
  # KNOWN LIMIT, documented rather than fixed: `preimage_log` swallows a write failure by design,
  # so a drain never dies for want of a receipt line. An eviction can therefore happen without its
  # line. That is the declared trade (a missing receipt must never be why a drain dies), and it is
  # why the line is written where the eviction is, not somewhere a reader could mistake for proof.
  local paths bytes
  for d in "${victims[@]}"; do
    paths="$(find "${PID:?}/$d" -type f 2>/dev/null | grep -c . || true)"
    bytes="$(find "${PID:?}/$d" -type f -exec cat {} + 2>/dev/null | wc -c | tr -d ' ')"
    preimage_log "$d" "prune" "EVICTED" "${paths:-0} paths, ${bytes:-0} bytes destroyed"
    rm -rf "${PID:?}/$d"
  done
  return 0
}

# $1 = mode label, $2.. = every file this mode is about to mutate or delete.
# Verify, THEN publish. This is the INVERSE of the archive write in drain_monolith below, which
# is mv-first/verify-after: that order is defensible where it sits, but copying it here
# would publish a slot before knowing it is good, which is the one thing a pre-image may
# never do. A failed capture leaves no slot.
capture_preimage() {
  local mode="$1"; shift
  local key slot stage f rel n=0
  [ "$PI_CAPTURED" -eq 0 ] || return 0
  mkdir -p "$PID" 2>/dev/null || {
    echo "✗ cannot create pre-image store $PID — refusing to drain without an undo"
    preimage_log "-" "$mode" "REFUSED" "cannot create store"; return 1; }
  stage="$(mktemp -d)" || {
    echo "✗ cannot stage a pre-image"; preimage_log "-" "$mode" "REFUSED" "mktemp failed"; return 1; }
  # Created unconditionally: an ALL-ABSENT capture is legal and normal — `restore` captures the
  # state it is about to overwrite, and after a journal drain every fragment it names is already
  # deleted. Without this the publish `mv` below has no source and a correct capture reports
  # failure. Found by F14–F16, which restore a journal drain.
  mkdir -p "$stage/files" || {
    echo "✗ cannot stage a pre-image"; rm -rf "$stage"
    preimage_log "-" "$mode" "REFUSED" "stage mkdir failed"; return 1; }
  # ABSENCE IS STATE. A first drain creates its archive, so that file does not exist at
  # capture time — and a restore that only writes back the files it holds would leave behind
  # a file the pre-drain tree did not have. The bar is the TREE being byte-identical, not
  # the files someone happened to have copied. So every requested path is recorded with a
  # status, and `absent` is an instruction to `restore`, not a skip. Found by F1 before the
  # restore path existed to get it wrong.
  for f in "$@"; do
    rel="${f#./}"
    if [ -f "$f" ]; then
      mkdir -p "$stage/files/$(dirname "$rel")" 2>/dev/null \
        && cp -p "$f" "$stage/files/$rel" 2>/dev/null \
        && cmp -s "$f" "$stage/files/$rel" || {
          echo "✗ pre-image of $f failed verification — refusing to drain"
          rm -rf "$stage"; preimage_log "-" "$mode" "REFUSED" "verify failed: $rel"; return 1; }
      printf 'present\t%s\n' "$rel" >> "$stage/manifest"
    else
      printf 'absent\t%s\n' "$rel" >> "$stage/manifest"
    fi
    n=$((n + 1))
  done
  [ "$n" -gt 0 ] || { rm -rf "$stage"; return 0; }   # nothing to mutate is not a failure
  key="$(preimage_next_key)"
  mkdir "$PID/$key" 2>/dev/null || {
    echo "✗ pre-image key $key already taken — refusing rather than overwriting one"
    rm -rf "$stage"; preimage_log "$key" "$mode" "REFUSED" "key collision"; return 1; }
  slot="$PID/$key"
  mv "$stage/files" "$slot/files" 2>/dev/null && mv "$stage/manifest" "$slot/manifest" 2>/dev/null || {
    echo "✗ could not publish pre-image $key — refusing to drain"
    rm -rf "$slot" "$stage"; preimage_log "$key" "$mode" "REFUSED" "publish failed"; return 1; }
  rm -rf "$stage"
  PI_CAPTURED=1
  PI_KEY="$key"
  # Cap the path list: a journal drain captures dozens of fragments and a receipt naming
  # every one defeats the readability that is the receipt's entire reason for existing.
  if [ "$n" -le 4 ]; then
    preimage_log "$key" "$mode" "OK" "$(cut -f2 "$slot/manifest" | tr '\n' ' ')"
  else
    preimage_log "$key" "$mode" "OK" "$n paths → $slot"
  fi
  if ! preimage_prune; then
    # The slot just published is the undo for a drain that will NOT happen, so it goes away rather
    # than growing the ring by one on every refused attempt -- the refusal has to be repeatable
    # without changing the thing it is protecting. Same reason the prune runs after the capture
    # and never before: nothing in the store should belong to a drain that did not run.
    rm -rf "${PID:?}/$key"
    PI_CAPTURED=0; PI_KEY=""
    preimage_log "$key" "$mode" "REFUSED" "slot removed: the prune refused, so this capture belongs to a drain that will not happen"
    return 1
  fi
  return 0
}

PREFLIGHT_ORD=""        # set by preflight_ordering: the effective ordering for the file it was given
PREFLIGHT_DECLARED=""   # …and that file's validated non-entry heading declarations, one per line
preflight_ordering() { # $1 = file to inspect   $2 = name to report it as (default: $1)
  # Validate EVERY manifest key this file's drain depends on, then run the contradiction alarm.
  # Returns 1 on a usage error, 3 on a contradiction, 0 otherwise — and in every non-zero case
  # NOTHING has been written, which is why it must run before the first byte moves on EVERY drain
  # path. drain_qa_log calls it at its top AND on a staged copy of the post-compile monolith:
  # a refusal raised by the drain_monolith it calls last lands after every fragment has been
  # deleted, making "nothing was moved" a lie and leaving the qa-log un-drainable with its sources
  # gone. $2 exists for that staged copy — the message must name the real file, not the temp one.
  local src="$1" base ord osrc dates dcount i asc=0 desc=0 ties=0 detected seq dir d neh_verdict pinned_list
  base="$(basename "${2:-$1}")"
  ord="$(gk order "$base")"   # read ONCE — re-reading to print the bad value would report a
  case "$ord" in              # different read than the one that was judged
    "") ord="oldest-first"; osrc="default — no retention.order entry for $base" ;;
    newest-first|oldest-first) osrc="declared — retention.order[\"$base\"]" ;;
    *) echo "✗ retention.order[\"$base\"] = '$ord' — expected 'newest-first' or 'oldest-first'"; return 1 ;;
  esac
  PREFLIGHT_ORD="$ord"

  # Malformed protection failing OPEN is the expensive direction: it yields a silent, successful
  # drain that archives the very heading the declaration was written to protect. This lives in the
  # pre-flight rather than in drain_monolith so the qa-log path validates it BEFORE the compile —
  # in drain_monolith it fires after the fragments are already deleted.
  # Valid JSON of the wrong SHAPE one level up used to fail open too: `"order": "newest-first"`
  # (the per-file map forgotten) parses, reads as absent for every basename, and silently reverts a
  # declaration to the default. Both containers are checked before either key is read.
  # ONE verdict over all three containers, and an EXPLICIT arm for empty. A `case` with only a
  # `bad)` arm falls through on empty — and jq exits 5 with empty stdout whenever `.retention`
  # itself is not indexable, so a wrong shape one level up read as "fine, proceed" and dropped every
  # declaration at exit 0. That is the same "an empty result reads as a benign state" this function
  # guards against three lines below, reintroduced by the guard for it.
  # `[ -f "$M" ] || printf absent` FIRST, and not `[ -f "$M" ] &&` alone: with the bare `&&`, an
  # absent manifest short-circuits, the command substitution exits non-zero, `|| echo probe-failed`
  # fires, and the `*)` arm refuses to drain — naming a file the operator was told they do not
  # need. The `""` arm below was written for this case and was unreachable, so the comment on it
  # documented an intention rather than a behaviour. `references/retention.md` promises the
  # opposite ("the whole block is optional … fall back to these shipped defaults when it is
  # absent"), which makes a greenfield adopter's very first drain a hard refusal. Invisible to the
  # suite because every one of its fixtures passes a manifest — `make_fixture_repo` accepts
  # `manifest=None` and nothing used it.
  if [ -f "$M" ]; then
    _mprobe="$(jq -r '
      def shape($v; $want): if $v == null then "absent" elif ($v|type) == $want then "ok" else "bad" end;
      if (.retention == null) then "ok"
      elif ((.retention|type) != "object") then "bad-retention"
      elif shape(.retention.order; "object") == "bad" then "bad-order"
      elif shape(.retention.non_entry_headings; "object") == "bad" then "bad-neh"
      else "ok" end' "$M" 2>/dev/null || echo probe-failed)"
  else
    _mprobe=absent
  fi
  case "$_mprobe" in
    ok|absent) : ;;   # `absent` == no manifest at all, which is legal and is the greenfield case
    bad-retention) echo "✗ retention must be an object — the whole retention block is the wrong shape"; return 1 ;;
    bad-order) echo "✗ retention.order must be an object keyed by file basename, e.g. { \"CHANGELOG.md\": \"newest-first\" }"; return 1 ;;
    bad-neh) echo "✗ retention.non_entry_headings must be an object keyed by file basename"; return 1 ;;
    *) echo "✗ could not read the retention block in $M — refusing rather than treating an unreadable manifest as an absent one"; return 1 ;;
  esac
  neh_verdict="$(jq -r --arg k "$base" '
      (.retention.non_entry_headings[$k]) as $v
      | if   $v == null then "absent"
        elif ($v | type) != "array" then "bad"
        elif ([$v[] | type] | any(. != "string")) then "bad"
        else "ok" end' "$M" 2>/dev/null)"
  [ "$neh_verdict" = bad ] && { echo "✗ retention.non_entry_headings[\"$base\"] is not an array of strings"; return 1; }
  PREFLIGHT_DECLARED="$(gka non_entry_headings "$base")"
  while IFS= read -r d; do
    case "$d" in
      '## '*) echo "✗ retention.non_entry_headings[\"$base\"] contains '$d' — declare the heading TEXT only, without its '## ' prefix"; return 1 ;;
    esac
  done <<<"$PREFLIGHT_DECLARED"

  # Dates come from EVERY entry heading, pinned ones included — otherwise declaring a heading
  # would silently disarm the alarm. Only the FIRST date in a heading is read, so
  # '## [1.2.0] — 2026-07-30 (backport of 2025-01-02)' contributes one date, not two.
  # …but a REFUSAL is decided on the non-pinned sequence only. A structural heading carrying a
  # revision date ("## Conventions — last revised …") sitting above same-day entries otherwise makes
  # the sequence one-directional on its own and refuses a perfectly ordered document — measured, and
  # the printed Fix then inverts it. The concern was that declaring a heading must not silently
  # disarm the alarm; what actually follows from it is that a heading which is not an entry is not
  # evidence about entry ordering. So pinned headings are still read (the sequence is still shown as
  # the operator sees the file), and the verdict ignores them.
  # Pinned headings are passed to awk as DATA and compared with `==`, exactly as drain_monolith
  # compares them. NOT as a regex: `awk -v` runs escape processing over its value before the regex
  # engine ever sees it, so shell-side escaping is consumed rather than applied. Measured: a
  # declared `**Conventions**` reached the engine unescaped, awk aborted with "illegal primary in
  # regular expression", the command substitution came back empty, and an empty date list reads as
  # "no dates — proceed silently" — the alarm disarmed at exit 0 by a bold heading. The built-in
  # `[Unreleased]` degraded the same way — `\[Unreleased\]` became a bracket expression — but that
  # half was INERT and is recorded as such rather than as a second defect: the pattern is anchored
  # whole-line, so it could only ever match a heading ONE character long, and a one-character heading
  # cannot contain a date. Neither the pin nor any dated heading changed hands. A regression
  # row has to be shown red against the pre-fix script, not only green against the fix.
  # ENVIRON, not -v, because -v would mangle a backslash.
  pinned_list="[Unreleased]"
  while IFS= read -r d; do
    [ -n "$d" ] && pinned_list="$pinned_list
$d"
  done <<<"$PREFLIGHT_DECLARED"
  dates="$(PLC_PINNED="$pinned_list" awk '
    BEGIN { np = split(ENVIRON["PLC_PINNED"], pin, "\n") }
    /^## / && $0 !~ /Index[[:space:]]*$/ {
      h = $0; sub(/^## /, "", h); sub(/^[[:space:]]+/, "", h); sub(/[[:space:]]+$/, "", h)
      for (i = 1; i <= np; i++) if (h == pin[i]) next
      if (match($0, /[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]/)) print substr($0, RSTART, 10)
    }' "$src")" \
    || { echo "✗ retention-drain: heading scan failed on ${2:-$src}"; return 1; }
  [ -z "$dates" ] && return 0
  local darr=($dates)   # ISO dates are fixed-shape and space-free; word-splitting is safe here
  dcount=${#darr[@]}
  [ "$dcount" -lt 2 ] && return 0   # fewer than two dates proves nothing — proceed silently

  # ONE-DIRECTIONAL monotone, not strictly monotone. A real changelog routinely ships several
  # releases on one day, i.e. tied ADJACENT PAIRS in same-day
  # groups (the counter below counts pairs, which is the number the refusal
  # message prints): under the strict form the sequence reads inconclusive and the alarm could not
  # fire on exactly the documents it exists for.
  # ISO dates compare lexicographically, which for this format is chronologically.
  for ((i = 1; i < dcount; i++)); do
    if   [[ "${darr[i]}" < "${darr[i-1]}" ]]; then desc=$((desc + 1))
    elif [[ "${darr[i]}" > "${darr[i-1]}" ]]; then asc=$((asc + 1))
    else ties=$((ties + 1)); fi
  done
  # NEARLY one-directional counts. A single contrary pair is a backport or a typo, not a mixed
  # document — measured: changing ONE date in a changelog by two days flipped the
  # verdict from refuse to a full drain, archiving the newest releases. Requiring 4 dominant
  # pairs before overruling one contrary pair is what keeps a genuinely mixed document inconclusive
  # (its minority count is >1), so undated and disordered documents still drain silently.
  if   [ "$desc" -ge 1 ] && [ "$asc" -eq 0 ]; then detected="newest-first"; dir="descending"
  elif [ "$asc" -ge 1 ] && [ "$desc" -eq 0 ]; then detected="oldest-first"; dir="ascending"
  elif [ "$asc" -eq 1 ] && [ "$desc" -ge 4 ]; then detected="newest-first"; dir="descending apart from one pair"
  elif [ "$desc" -eq 1 ] && [ "$asc" -ge 4 ]; then detected="oldest-first"; dir="ascending apart from one pair"
  else return 0; fi                       # genuinely mixed, or all equal → inconclusive
  [ "$detected" = "$ord" ] && return 0    # detection agrees with the declaration → nothing to say

  seq="$(printf '%s, ' "${darr[@]:0:6}")"; seq="${seq%, }"
  [ "$dcount" -gt 6 ] && seq="$seq, …"
  # Every element below is load-bearing: the file, the effective ordering AND where it came from,
  # the evidence, the explicit "nothing was moved", and a Fix line that actually fixes — a printed
  # fix that still refuses trains the reader to route around the check instead of acting on it.
  echo "✗ retention-drain: refusing to drain ${2:-$src} — cannot safely tell which end is old."
  echo "    effective ordering: $ord  (source: $osrc)"
  echo "    observed heading dates, in file order: $seq  ($dir, $ties ties)"
  echo "    that sequence says $detected. Nothing was moved; both files are untouched."
  # The fix line does NOT assert the detected value. Detection can be wrong — a structural heading
  # with its own date, a backport, a fence quoting a heading — and a declaration applied on trust
  # archives the newest entries. Ask for a confirmation, then give the exact line to write.
  echo "    Fix: confirm which end of $base is genuinely OLD, then declare it — if it is $detected,"
  echo "         add  \"order\": { \"$base\": \"$detected\" }  under retention in $M"
  return 3
}

drain_monolith() {
  local src="$1" name base archive tmpdir starts_s heads_s n m c
  local declared ord d h p last_line
  local idx_line sep_line old_bytes new_bytes added i j s e
  [ -f "$src" ] || { echo "✗ retention-drain: no such file: $src"; return 1; }
  # The store is not a document. Without this the tool can be pointed at its own backups and
  # archive them — a self-eating archive, which makes this a required exclusion.
  case "$src" in
    "$PID"/*|"$PIX") echo "✗ $src is inside the pre-image store — the store is not a document"; return 1 ;;
  esac
  name="$(basename "$src" .md)"
  archive="$AD/${name}-archive.md"
  # The manifest key is the basename WITH its extension. `$name` above is `.md`-stripped and
  # exists for the archive filename only — reusing it here would look up the wrong key.
  base="$(basename "$src")"

  # --- ordering + alarm + manifest validation, fail-closed, BEFORE any byte moves ------
  preflight_ordering "$src" || return $?
  ord="$PREFLIGHT_ORD"
  declared="$PREFLIGHT_DECLARED"

  # Entry boundaries. Source monoliths are chronological-append (document-indexing.md:
  # new sections land at the BOTTOM, so the newest entry is the LAST '## ' heading).
  # The doc's own TOC heading ('## 📑 Index') is not an entry — exclude any '## …Index' heading.
  starts_s="$(awk '/^## / && $0 !~ /Index[[:space:]]*$/ { print NR }' "$src")"
  [ -z "$starts_s" ] && { echo "  $src: no '## ' entries — nothing to drain"; return 0; }
  local starts=($starts_s)
  n=${#starts[@]}
  [ "$n" -le "$KEEP" ] && { echo "  $src: $n entries <= keep-window $KEEP — nothing to drain"; return 0; }

  # Pinned entries keep their place in `starts` and are excluded from the eviction candidate
  # set ONLY — no positional requirement, no positional refusal. A positional rule would make
  # an oldest-first document whose '[Unreleased]' is the last heading permanently un-drainable.
  # Pinned = the built-in '[Unreleased]' (unconditional; it must survive a wrong
  # declaration and no declaration) plus the headings declared for this basename. Nothing else
  # is inferred — Keep a Changelog provides no machine marker.
  # Entry i ends the line before entry i+1 starts — or, for the LAST entry, at the end of the
  # file. Without that second branch the newest-first path (which always evicts the final entry)
  # reads an unset `starts[n]` under `set -u` and the shell aborts before the loop body runs.
  # `awk END{NR}` rather than `wc -l`: a file with no trailing newline undercounts by one there.
  last_line="$(awk 'END { print NR }' "$src")"
  entry_end() { if [ $(( $1 + 1 )) -lt "$n" ]; then echo $(( ${starts[$1 + 1]} - 1 )); else echo "$last_line"; fi; }

  heads_s="$(awk '/^## / && $0 !~ /Index[[:space:]]*$/ { sub(/^## /, ""); sub(/^[[:space:]]+/, ""); sub(/[[:space:]]+$/, ""); print }' "$src")"
  # `is_pin` is the per-entry mirror of the pin decision, kept because the decision has a SECOND
  # reader downstream (the regenerated source index) and re-deriving it there would be the same
  # rule written twice. `cand` alone cannot serve: it is a list of indices in eviction terms and
  # says nothing about an index that was pinned rather than merely surviving.
  local heads=() cand=() is_pin=()
  while IFS= read -r h; do heads+=("$h"); done <<<"$heads_s"
  for ((i = 0; i < n; i++)); do
    h="${heads[i]}"; p=0
    [ "$h" = "[Unreleased]" ] && p=1
    if [ "$p" -eq 0 ]; then
      while IFS= read -r d; do
        [ -n "$d" ] && [ "$d" = "$h" ] && { p=1; break; }
      done <<<"$declared"
    fi
    is_pin+=("$p")
    [ "$p" -eq 0 ] && cand+=("$i")
  done
  c=${#cand[@]}
  [ "$c" -le "$KEEP" ] && { echo "  $src: $c evictable entries <= keep-window $KEEP — nothing to drain"; return 0; }

  m=$((c - KEEP))
  # Which candidates are evicted follows from the EFFECTIVE ordering, never from the dates:
  #   oldest-first (default, today) → keep the last KEEP in file order, evict all earlier
  #   newest-first                  → keep the first KEEP in file order, evict all later
  local ev=()
  if [ "$ord" = newest-first ]; then
    for ((j = KEEP; j < c; j++)); do ev+=("${cand[j]}"); done
  else
    for ((j = 0; j < m; j++)); do ev+=("${cand[j]}"); done
  fi

  tmpdir="$(mktemp -d)" || { echo "✗ mktemp -d failed"; return 1; }
  # Assemble the evicted block NEWEST-FIRST: reverse the ENTRY order (ring convention),
  # each entry extracted as a byte-verbatim line range. TOC bullets are plain text —
  # no hand-computed anchor links (document-indexing.md's anti-pattern: anchor guesses).
  # Archive block order is unchanged: always newest-first. Only the SOURCE side differs — the
  # oldest-first path reverses the evicted list, the newest-first path is already newest-first.
  local ev_order=()
  if [ "$ord" = newest-first ]; then
    for ((j = 0; j < m; j++)); do ev_order+=("${ev[j]}"); done
  else
    for ((j = m - 1; j >= 0; j--)); do ev_order+=("${ev[j]}"); done
  fi
  for i in "${ev_order[@]}"; do
    s=${starts[i]}; e=$(entry_end "$i")
    # A stub written by a PREVIOUS drain is not entry content: on the newest-first path it lands
    # in the source and the next drain would copy it into the archive as body text.
    #
    # SIMPLEST RULE THAT CANNOT LOSE DATA, chosen deliberately after three variants each traded one
    # leak for another. Only a trailing blanks-then-stub run at the very END OF THE FILE is dropped,
    # matched by PREFIX:
    #   - end-of-file, not per-range: a body line is essentially never the document's last line,
    #     whereas the stub is exactly that on that shape. Per-range scanning is what
    #     let an ordinary quoted line be deleted from the archive AND the source at once.
    #   - prefix, not byte-identity: identity keyed the reader to the rendered archive path, so a
    #     stub written before `retention.archive_dir` changed stopped being recognised, and the
    #     value had to travel through `awk -v`, which mangles a backslash in a path.
    # KNOWN LIMIT, accepted and filed rather than papered over: when a pinned heading sits below the
    # stub's position the stub is not the file's last line, so it reaches the archive as one line of
    # pointer prose. That costs a stray line in a cold file and loses nothing. The fully correct
    # rule needs a sentinel the drain writes and matches, which changes the stub's bytes and so
    # the pinned golden output — a declared behaviour change, not a patch.
    awk -v s="$s" -v e="$e" -v tail="$([ "$e" -eq "$last_line" ] && echo 1 || echo 0)" '
      NR >= s && NR <= e { buf[++k] = $0 }
      END {
        last = k
        if (tail) {
          j = last
          while (j > 0 && buf[j] == "") j--
          if (j > 0 && buf[j] ~ /^> Earlier entries archived verbatim/) last = j - 1
        }
        for (i = 1; i <= last; i++) print buf[i]
      }' "$src" >> "$tmpdir/block" \
      || { echo "✗ read failure extracting entries from $src"; rm -rf "$tmpdir"; return 1; }
    sed -n "${s}p" "$src" | sed 's/^## /- /' >> "$tmpdir/toc"
  done

  # Last point at which nothing has been mutated: the archive template below is the first
  # write, and the source rewrite follows it. Both files, because an undo that restores only
  # the source leaves the archive holding content the source no longer references.
  capture_preimage "drain $src" "$src" "$archive" || { rm -rf "$tmpdir"; return 1; }

  [ -f "$archive" ] || printf '# %s — archive (verbatim, newest-first)\n\n## 📑 Index\n\n---\n' "$name" > "$archive" \
    || { echo "✗ cannot create $archive"; rm -rf "$tmpdir"; return 1; }

  idx_line="$(awk '/^## / && /Index[[:space:]]*$/ { print NR; exit }' "$archive")"
  sep_line="$(awk -v s="${idx_line:-0}" 'NR > s && /^---$/ { print NR; exit }' "$archive")"

  old_bytes=$(wc -c < "$archive"); added=$(wc -c < "$tmpdir/block")
  if [ -n "$idx_line" ] && [ -n "$sep_line" ]; then
    # multi-line insertion via `sed <line>r <file>` (portable BSD/GNU) — body first (the
    # later line), then TOC bullets (the earlier line, unaffected by the body insert).
    # Inserting right after '---' keeps the archive newest-first across successive drains.
    sed "${sep_line}r $tmpdir/block" "$archive" > "$tmpdir/a1" \
      && sed "$((idx_line + 1))r $tmpdir/toc" "$tmpdir/a1" > "$tmpdir/a2" \
      && mv "$tmpdir/a2" "$archive" \
      || { echo "✗ archive write failed for $archive"; rm -rf "$tmpdir"; return 1; }
    added=$((added + $(wc -c < "$tmpdir/toc")))
  else
    echo "⚠ $archive lacks the Index/--- template header — inserting after line 1, TOC bullets skipped"
    sed "1r $tmpdir/block" "$archive" > "$tmpdir/a1" && mv "$tmpdir/a1" "$archive" \
      || { echo "✗ archive write failed for $archive"; rm -rf "$tmpdir"; return 1; }
  fi

  # VERIFY the archive actually received every byte BEFORE touching the source — a
  # silently no-op'd insert followed by a source rewrite would be silent data loss,
  # the exact thing the drain exists to prevent. Byte count AND sentinel grep.
  new_bytes=$(wc -c < "$archive")
  if [ "$new_bytes" -ne $((old_bytes + added)) ] || ! grep -qF "$(head -1 "$tmpdir/block")" "$archive"; then
    echo "✗ archive verification failed (${new_bytes}B, expected $((old_bytes + added))B) — $src left untouched"
    rm -rf "$tmpdir"; return 1
  fi

  # Rewrite source as a WALK, not as two `sed` ranges: pinning can leave the kept set
  # non-contiguous (a pinned entry may sit between evicted ones), which no pair of ranges can
  # express. Emit everything above the first entry, then each KEPT entry's range in file order,
  # emitting exactly one pointer stub at the position of the first evicted entry and nothing at
  # all for any other evicted entry. That last part is also what stops a stub written by a
  # PREVIOUS drain from being copied into the archive as body text on the next one.
  # On a document with nothing pinned this reproduces the old two-range output byte-for-byte,
  # which the golden test pins — and is why the prefix is keyed on starts[0] rather than on the first evicted.
  local is_ev=() stub_done=0
  for ((i = 0; i < n; i++)); do is_ev+=(0); done
  for i in "${ev[@]}"; do is_ev[i]=1; done

  # The SOURCE's own index, which the eviction alone would leave behind. Left unmaintained it is
  # not merely stale but INVERTED — its anchors name
  # the evicted sections and none of the survivors appear at all. The drain
  # must perform the index maintenance the same convention demands of a human, not only the eviction.
  #
  # REGENERATED, never patched: the list is derived from the entries that survive, so it is the
  # file describing itself and cannot drift. Bullets are plain text — a hand-computed anchor is
  # `document-indexing.md`'s named anti-pattern, already rejected archive-side at the TOC build.
  #
  # SURVIVING IS NOT THE SAME AS BEING AN ENTRY. A pinned heading also survives the eviction, so
  # a "not evicted" test alone put `- How to read this file` and `- [Unreleased]` in the index
  # beside dated release entries. Pins are structure — the document's own scaffolding, which is
  # exactly why they are unevictable — and a typical `CHANGELOG.md` carries two of them, so it
  # is the first document a naive regeneration gets wrong. Skip both classes, from the one decision
  # already made above rather than by re-testing the heading text here.
  local kept_toc="$tmpdir/src.toc"
  : > "$kept_toc"
  for ((i = 0; i < n; i++)); do
    [ "${is_ev[i]}" -eq 1 ] && continue
    [ "${is_pin[i]}" -eq 1 ] && continue
    sed -n "${starts[i]}p" "$src" | sed 's/^## /- /' >> "$kept_toc"
  done

  # One stub per FILE, not one per drain. On the oldest-first path a previous run's stub
  # sits above `starts[0]`, inside the prefix this walk emits verbatim, so it would survive and a new
  # one would be added below it: six identical lines would mean six drains, not six
  # evicted entries. It is handled here.
  #
  # Both rewrites act on the SAME prefix region, and index insertion is position-sensitive, so
  # they run as ONE awk pass over that region rather than two composed ones — two passes with
  # independently-computed anchors land off by the number of stubs removed.
  #
  # KNOWN LIMIT, declared rather than papered over: a preamble line byte-identical to a stub is
  # indistinguishable from one and would be dropped. The match is anchored at line start on the
  # whole stub prefix, so ordinary prose that merely mentions the wording survives — that is the
  # case a previous variant got wrong (see the extraction comment above), and it has a test.
  rewrite_prefix() {
    [ "${starts[0]}" -gt 1 ] || return 0
    sed -n "1,$(( ${starts[0]} - 1 ))p" "$src" | awk -v toc="$kept_toc" '
      BEGIN { k = 0; while ((getline line < toc) > 0) bullets[++k] = line }
      function flush_index() { print ""; for (i = 1; i <= k; i++) print bullets[i]; print "" }
      # The stub AND the blank line the emitter writes under it. Dropping only the stub traded
      # one accumulating line for another: the emitter writes stub-then-blank, the blank was not
      # dropped on the next pass, and the file still grew exactly one line per drain in exactly
      # the same position — six drains, six blanks. "One line per file, however many drains came
      # before" was true of the stub and false of the file, and the motivating evidence had been
      # a line count. `swallow` is cleared by the first non-blank so only the emitter`s own blank
      # goes, never a run of prose spacing further down.
      /^> Earlier entries archived verbatim/ { swallow = 1; next }
      swallow == 1 { swallow = 0; if ($0 == "") next }
      in_index == 1 {
        # `^[[:space:]]*- `, not `^- `: a NESTED index bullet is still index. With the anchored
        # form the run ended at the first sub-bullet, the regenerated list was flushed there, and
        # the WHOLE REMAINDER of the old index was emitted below it as body prose — anchors to the
        # entries the drain had just evicted included. A qa-log whose index nests
        # sub-bullets under its top-level ones is exactly that shape, and a fixture with a flat
        # index misses it — the hole is in the fixture SHAPE, not in the assertion.
        if ($0 ~ /^[[:space:]]*- / || $0 == "") next
        in_index = 0; flush_index()
      }
      /^## / && /Index[[:space:]]*$/ { print; in_index = 1; next }
      { print }
      END { if (in_index == 1) flush_index() }
    '
  }

  {
    rewrite_prefix
    for ((i = 0; i < n; i++)); do
      if [ "${is_ev[i]}" -eq 1 ]; then
        [ "$stub_done" -eq 1 ] && continue
        pointer_stub "$archive" "newest-first"
        echo
        stub_done=1
      else
        sed -n "${starts[i]},$(entry_end "$i")p" "$src"
      fi
    done
  } > "$tmpdir/src.new" && mv "$tmpdir/src.new" "$src" \
    || { echo "✗ rewrite of $src failed — the archive was ALREADY updated, so the two files now disagree"
         # The old wording here was "safe to re-run", and it was false: `drain_monolith` has no
         # idempotence sentinel (unlike drain_journal / drain_qa_log), so a literal re-run
         # appends the same entries to the archive a SECOND time and the byte-count + first-line
         # verification passes both times. Not fixed: an idempotence sentinel would change
         # the archive's bytes and needs its own fixture.
         # What changed is that the line no longer instructs the operator to trigger it, and — now
         # that a pre-image exists — it can name the way back instead of inventing one.
         if [ -n "$PI_KEY" ]; then
           echo "  do NOT re-run: the archive has no idempotence sentinel, so a second run appends the same entries again"
           echo "  put both files back instead:  retention-drain.sh restore $PI_KEY"
         else
           echo "  no pre-image was taken for this run, so there is no clean way back — inspect $archive and $src by hand before re-running"
         fi
         rm -rf "$tmpdir"; return 1; }

  rm -rf "$tmpdir"
  echo "  drained $m entries from $src → $archive (verbatim, newest-first, pointer stub + TOC entries left)"
  return 0
}

# The archive month a fragment belongs to, read from its OWN filename — echoes `YYYY-MM`, or
# NOTHING when the name does not start with a real date. Two things are deliberate here:
#
#   1. VALIDATED, not cut. `${base:0:7}` always "succeeds" — it returns seven characters whether
#      or not they are a date — so `2026-13-99-x.md` would be filed under a `2026-13.md` no
#      calendar has, and would never reach the wall-clock fallback that is supposed to warn about
#      exactly that fragment. The month and day ranges below are what make the fallback reachable.
#   2. It echoes ONLY the month, never a warning. The caller runs this in a command substitution,
#      so anything printed here would be captured as the month instead of shown to the operator.
#      The warning belongs at the call site, outside the substitution.
#
# `[-.]` after the date accepts both the slugged convention (`2026-07-30-feat-x.md`) and a
# slugless `2026-07-30.md` — the rule: be strict about inputs the script PARSES, permissive
# about artifacts it is merely LOOKING FOR, and a fragment is the latter.
# Pure shell pattern-matching, deliberately NOT sed: BSD sed (macOS) has no `\|`
# alternation — that is a GNU extension — so the obvious one-line BRE
# matched NOTHING here and sent every fragment to the fallback while looking correct. Caught only
# because the two-month fixture stayed red after the fix. `case` is POSIX, needs no subprocess,
# and keeps the dependency envelope narrower than the sed version it replaces.
fragment_month() {
  local base="${1##*/}" y m d
  # Shape first: exactly YYYY-MM-DD, then a separator. `[-.]` accepts the slugged convention
  # (`2026-07-30-feat-x.md`) and a slugless `2026-07-30.md` alike — the rule: strict
  # about inputs the script PARSES, permissive about artifacts it is merely LOOKING FOR.
  case "$base" in
    [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][-.]*) ;;
    *) return 0 ;;
  esac
  y="${base:0:4}"; m="${base:5:2}"; d="${base:8:2}"
  # Then RANGES, which is what makes the fallback reachable at all. A shape-only check would
  # accept `2026-13-99-x.md` and file it under a `2026-13.md` no calendar has, and — because the
  # extraction "succeeded" — it would never reach the warning that exists for exactly that case.
  case "$m" in 0[1-9]|1[0-2]) ;; *) return 0 ;; esac
  case "$d" in 0[1-9]|[12][0-9]|3[01]) ;; *) return 0 ;; esac
  printf '%s-%s' "$y" "$m"
}

# Regenerate a journal archive's `## 📑 Index` FROM THE ARCHIVE ITSELF, never from what this
# run happened to append. Same principle the source side already uses (`kept_toc`): the file
# describes itself, so the index cannot drift from the bodies and cannot be made wrong by the order
# or the survival of any single run.
#
# It is also the only shape that survives a crash-retry. Collecting bullets per appended fragment
# put the collection inside the "not yet compiled" branch, so a run interrupted between the append
# and the index write correctly skipped the re-append on retry — and never re-collected the heading.
# The body sat in the archive, permanently absent from that archive's own index, and no rerun could
# repair it. Regeneration is idempotent by construction: it does not care which run wrote what.
#
# ONLY THE OLD BULLETS ARE REPLACED — nothing else in the file is even eligible to be dropped.
# The first version of this deleted every line between the Index heading and the first `---`,
# reasoning that the region "is" the index. It is not: an archive carrying a one-line human note
# under its index lost that line to a plain `drain journal`, exit 0, no warning — byte deletion in
# a tool whose entire contract is that it moves bytes verbatim. Worse, the `---` it stopped at was
# only ever asserted to EXIST, not to be the header separator, so an archive without one had the
# rewrite stop at an ordinary horizontal rule inside a fragment body and take the whole fragment
# with it. The sibling regenerator forty lines up (`rewrite_prefix`) already had the right rule and
# a test named for it (`test_a_preamble_line_below_the_index_is_not_eaten_by_the_collapse`); two
# regenerators in one file disagreeing on the same input is how that happened.
#
# So the old index block is defined by what it IS — the run of blank and `- ` lines immediately
# below the heading — and ends at the first line that is neither. Everything from there down is
# emitted verbatim. A wrong `---` can now only mis-scope which headings get collected, never
# delete anything.
#
# KNOWN LIMITS, declared rather than left to be found: `^## ` is matched line-wise, so a `## ` line
# inside a fenced code block in a body is listed as an entry; and a genuine entry whose heading
# ENDS in `Index` is excluded, because the `## …Index` exclusion is file-wide and cannot tell that
# heading from a document's own TOC heading. Both are the same rule and the same limits the
# monolith side has always had.
regen_archive_index() {
  local archive="$1" idx_line blk_end sep_line tmpdir
  # THE ANCHOR IS BOUNDED TO THE HEADER, and it has to be: an unbounded "first `## …Index` heading"
  # search selects a heading in a BODY when the header has none — say a fragment titled
  # `## how we rebuilt the Index` — and the rewrite below then treats the `- ` lines under that
  # body heading as a stale index and drops them. Silent, exit 0, byte deletion again, through a
  # different door than the one described above. The sibling this function's design was taken from
  # (`rewrite_prefix`) never had the problem because it is structurally confined to the prefix
  # region; the rule was copied and the bound was not. Here the bound is the header separator: a
  # heading below the first `---` is a body heading and can never be the index.
  # NO SEPARATOR MEANS NO HEADER, hence no index — checked first and separately. Bounding the
  # search with "stop at the first `---`" is not enough on its own: a file with no `---` anywhere
  # never hits the stop and the scan runs to EOF, which is exactly the archive shape that
  # reproduced the deletion. The bound has to be an interval that exists, not a terminator that
  # might not.
  local first_sep
  first_sep="$(awk '/^---[[:space:]]*$/ { print NR; exit }' "$archive")"
  if [ -z "$first_sep" ]; then
    echo "  ⚠ $archive has no --- separator, so it has no header block to hold an index — index regeneration skipped"
    return 0
  fi
  idx_line="$(awk -v s="$first_sep" 'NR >= s { exit } /^## / && /Index[[:space:]]*$/ { print NR; exit }' "$archive")"
  if [ -z "$idx_line" ]; then
    echo "  ⚠ $archive lacks an Index heading above its --- separator — index regeneration skipped"
    return 0
  fi
  # The end of the EXISTING index block: the last of the contiguous blank/bullet lines below the
  # heading. `blk_end == idx_line` (nothing replaceable at all) is a perfectly ordinary state.
  # A nested bullet is index too — same rule and the same reason as the source side above, written
  # the same way on purpose: these two scans disagreeing about what an index bullet is, is the
  # shape that produced this whole class.
  blk_end="$(awk -v s="$idx_line" '
    NR <= s { next }
    ($0 ~ /^[[:space:]]*$/ || $0 ~ /^[[:space:]]*- /) { last = NR; next }
    { exit }
    END { print (last ? last : s) }
  ' "$archive")"
  [ -n "$blk_end" ] || blk_end="$idx_line"
  # Where the BODIES start, for heading collection only. Absent `---` is not an error any more —
  # it costs a slightly wider collection window, not a deletion.
  sep_line="$(awk -v s="$blk_end" 'NR > s && /^---[[:space:]]*$/ { print NR; exit }' "$archive")"
  [ -n "$sep_line" ] || sep_line="$blk_end"
  # THE ARCHIVE'S OWN MODE IS PRESERVED, not re-derived. A bare `mktemp` file is 0600 and `mv`
  # carries that onto the archive; building the temp with a shell redirect instead only replaces
  # 0600 with `0666 & ~umask`, which is a different wrong answer — measured, it tightened 0644 to
  # 0600 under `umask 077` and loosened 0600 to 0644 under the default. Since the widened loop
  # below rewrites EVERY archive on EVERY drain, a mode derived from whoever happened to run it is
  # churn on every file, every time; and git does not track the mode, so no diff review can see
  # it. `cp -p` first, then redirect into that copy: the redirect keeps the file it truncates, so
  # the temp carries the archive's real mode and `mv` puts it back unchanged.
  tmpdir="$(mktemp -d)" || { echo "✗ mktemp -d failed"; return 1; }
  cp -p "$archive" "$tmpdir/a.new" || { echo "✗ cannot stage $archive"; rm -rf "$tmpdir"; return 1; }
  # Two passes over the SAME file: pass 1 reads the bodies into the bullet list, pass 2 emits
  # everything up to the heading, the freshly built index, then the rest of the file verbatim.
  # Write-temp-then-`mv` so an interrupted run leaves the archive as it was rather than half-indexed.
  awk -v sep="$sep_line" -v idx="$idx_line" -v blk="$blk_end" '
    NR == FNR {
      if (FNR > sep && $0 ~ /^## / && $0 !~ /Index[[:space:]]*$/) { h = $0; sub(/^## /, "- ", h); b[++k] = h }
      next
    }
    FNR <= idx { print; next }
    FNR <= blk { next }
    FNR == blk + 1 {
      print ""
      for (i = 1; i <= k; i++) print b[i]
      print ""
      print
      next
    }
    { print }
    # (No END clause. One was written here "in case the index block runs to EOF" — on that shape
    # `sep` falls back to EOF too, so pass 1 collects nothing and it could never emit a bullet:
    # error handling for a case it could not handle, with a comment asserting otherwise. Removed
    # rather than repaired; the shape is an archive whose index is its last section, which the
    # writer never produces.)
  ' "$archive" "$archive" > "$tmpdir/a.new" \
    && mv "$tmpdir/a.new" "$archive" \
    || { echo "✗ index regeneration failed for $archive"; rm -rf "$tmpdir"; return 1; }
  rm -rf "$tmpdir"
}

drain_journal() {
  [ -d "$JD" ] || { echo "  $JD: no such directory — nothing to drain"; return 0; }
  local frags wall month archive f written=""
  frags="$(find "$JD" -maxdepth 1 -type f -name '*.md' | sort)"
  [ -z "$frags" ] && { echo "  $JD: no fragments — nothing to drain"; return 0; }
  # The target month comes from EACH FRAGMENT, never from the clock this run happens to
  # tick on. The old single `month="$(date +%Y-%m)"` filed every fragment under the run's month,
  # which is invisible while a project drains inside the month it wrote — and wrong the moment it
  # does not.
  # The wall clock survives only as the fallback for a fragment whose name carries no date.
  wall="$(date +%Y-%m)"
  mkdir -p "$AD/journal" || { echo "✗ cannot create $AD/journal"; return 1; }
  # This mode DELETES its fragments (`rm -f` below) rather than rewriting them, which is the
  # harder loss: a restore that puts back only the monthly archive leaves the fragments gone.
  #
  # Two properties are enforced here, both measured:
  #
  # (1) The path list is built as an ARRAY, never by word-splitting `$frags`. Unquoted, a
  #     fragment named `2026-08-04 a fragment.md` split into three nonexistent partial paths,
  #     each recorded `absent`, and the capture returned SUCCESS — the drain then deleted the
  #     real file with no pre-image and the receipt said OK — the exact inverse of what the
  #     pre-image exists to guarantee.
  #
  # (2) The touched archives are DERIVED, not globbed. The old comment here claimed the set was
  #     "not knowable without re-deriving the fragment-to-month mapping" — but `fragment_month()` IS that
  #     mapping, it is a standalone function, and it is called on each fragment a few lines
  #     below. Globbing only what already exists missed the archive a drain CREATES for a new
  #     month, so that file was in no manifest at all and `restore` left it behind while
  #     reporting byte-verified.
  local -a pi_paths=()
  local pi_f pi_m
  while IFS= read -r pi_f; do
    [ -n "$pi_f" ] || continue
    [ -f "$pi_f" ] || { echo "✗ fragment vanished between listing and capture: $pi_f"; return 1; }
    pi_paths+=("$pi_f")
    pi_m="$(fragment_month "$pi_f")"; pi_m="${pi_m:-$wall}"
    case " ${pi_paths[*]} " in *" $AD/journal/$pi_m.md "*) ;; *) pi_paths+=("$AD/journal/$pi_m.md") ;; esac
  done <<EOF
$frags
EOF
  capture_preimage "drain journal" "${pi_paths[@]}" || return 1
  # The archive's own index. `references/retention.md` says fragments deliberately carry no
  # TOC *because the obligation lives on the compiled archive*; the archive is created with an
  # `## 📑 Index` heading, and without this step nothing would write a bullet under it.
  #
  # The index is REGENERATED from every journal archive after the compile loop
  # (`regen_archive_index` above), not accumulated per appended fragment. A crash-retry therefore
  # cannot lose a bullet: nothing about the index depends on which run appended which body. Bullet
  # order is the archive's own body order — newest-first WITHIN each run's block, and blocks stack
  # oldest-run-first, because appends land at the bottom across runs. The index is faithful to the
  # file, which is the whole contract; it is not globally date-sorted, and does not claim to be.
  # Compile newest-first: fragment filenames are date-prefixed, so descending sort = newest
  # first — now WITHIN each month file rather than across the whole run. The per-fragment
  # sentinel makes a retried drain IDEMPOTENT: a fragment that was already compiled (crash
  # between append and delete) is skipped, never duplicated.
  while IFS= read -r f; do
    month="$(fragment_month "$f")"
    if [ -z "$month" ]; then
      month="$wall"
      echo "  ⚠ $(basename "$f"): no YYYY-MM-DD prefix in the filename — filing under the wall-clock month $wall"
    fi
    archive="$AD/journal/$month.md"
    [ -f "$archive" ] || printf '# Journal archive — %s\n\n## 📑 Index\n\n---\n' "$month" > "$archive" \
      || { echo "✗ cannot create $archive"; return 1; }
    ensure_trailing_nl "$archive"
    if grep -qF "<!-- fragment: $f -->" "$archive"; then
      echo "  $f already compiled into $archive — skipping append (idempotent retry)"
    else
      { printf '\n<!-- fragment: %s -->\n' "$f"; cat "$f"; echo; } >> "$archive" \
        || { echo "✗ append of $f to $archive failed"; return 1; }
    fi
    case " $written " in *" $month "*) ;; *) written="${written:+$written }$month" ;; esac
  done <<<"$(sort -r <<<"$frags")"

  # EVERY journal archive, not only the months this run happened to write. Two reasons.
  # (1) A touched archive whose every fragment was skipped as already-
  # compiled is precisely the crash-retry case whose index needs repairing, so it must not be
  # filtered out — that alone argues for `$written` rather than "months that got an append". (2)
  # `$written` is still too narrow to make the promise stick: since fragments are filed by their
  # own filename month, an archive for a month with no pending fragments can never be in `$written`
  # again, so "run the drain again and the index is repaired" would be unreachable for exactly a
  # past month's archive,
  # with nothing left in the hot directory that could ever name that month. Regeneration is idempotent and
  # byte-verified on that same archive, so widening the loop costs a re-read and nothing else.
  # STILL NOT UNCONDITIONAL, and the difference matters: `drain_journal` returns at the top when the
  # hot directory is empty, so the repair rides on a drain that has fragments to compile. In the
  # post-drain steady state — the state the hot directory is supposed to be in — re-running the
  # drain does nothing at all. Said here because the sentence one screen up reads as a promise.
  #
  # Scoped to the archives THIS FUNCTION NAMES — `YYYY-MM.md`, the only shape `drain_journal`
  # creates. A bare `*.md` swept in hand-made and pre-convention files the drain does not own:
  # `drain legacy` writes one (`legacy-<date>.md`, no Index heading), which would mean a `⚠` on every
  # future drain about a file no drain will ever index. A permanent warning about something that
  # is not going to change is the class of noise operators learn to scroll past, which costs the
  # warnings that matter.
  for _arch in "$AD"/journal/[0-9][0-9][0-9][0-9]-[0-9][0-9].md; do
    [ -f "$_arch" ] || continue
    regen_archive_index "$_arch" || return 1
  done
  # delete-vs-archive: fragments are mechanical once compiled — delete, git is cold storage.
  # STRICTLY after every append, never interleaved: a per-fragment append-then-delete would, on a
  # run that fails partway through a second month, leave some fragments deleted and their bytes
  # nowhere. One loop, then the other, is what makes a partial failure safe to re-run.
  while IFS= read -r f; do rm -f -- "$f" || { echo "✗ failed to delete drained fragment $f"; return 1; }; done <<<"$frags"
  echo "  drained journal fragments → $AD/journal/ [$written], $JD emptied"
  # no roll-over pass: journal archives are already month-segmented by filename (YYYY-MM.md).
  return 0
}

drain_qa_log() {
  # Two-step, unlike drain_journal: compile fragments INTO THE HOT MONOLITH (not the
  # archive) first, byte-verify the monolith received them, delete fragments — THEN call
  # drain_monolith to evict old entries out of that same monolith to archive. qa-log keeps
  # a hot tier (a deliberate choice, unlike journal's drain-to-zero), so the compile target is hot, not cold.
  # The pre-delete verify below is INTENTIONALLY STRICTER than drain_journal's bare append —
  # a batch byte-count delta AND a per-fragment sentinel grep gate every fragment delete —
  # because the compile target (the hot monolith) is a live-read doc, not a write-only archive.
  local mono="docs/brainstorming-qa-log.md" frags f old_bytes new_bytes added tmpblock appended staged rc
  [ -d "$QD" ] || { echo "  $QD: no such directory — nothing to drain"; return 0; }
  frags="$(find "$QD" -maxdepth 1 -type f -name '*.md' | sort)"
  [ -z "$frags" ] && { echo "  $QD: no fragments — nothing to drain"; return 0; }
  # PRE-FLIGHT AT THE TOP, before the compile — not inside the drain_monolith call at the foot.
  # By then every fragment has been deleted (the delete loop below) and the monolith rewritten, so a refusal
  # raised there would leave the qa-log un-drainable with its sources gone while claiming
  # nothing was moved. Skipped when the monolith does not exist yet: there is no ordering to
  # contradict in a file this run is about to create.
  [ ! -f "$mono" ] || preflight_ordering "$mono" || return $?
  # Three tiers in one call: the fragments this run DELETES, the hot monolith it rewrites, and
  # the archive drain_monolith will append to at the foot. Captured here, at the top, because
  # `PI_CAPTURED` makes the nested drain_monolith call reuse this slot rather than mint a
  # second one — one drain, one slot, one receipt line.
  # Array, never word-splitting — same Critical as drain_journal's: a fragment name containing a
  # space split into nonexistent partial paths, every one recorded `absent`, and the capture
  # returned success while the real file went on to be deleted unprotected.
  local -a pi_paths=()
  local pi_f
  while IFS= read -r pi_f; do
    [ -n "$pi_f" ] || continue
    [ -f "$pi_f" ] || { echo "✗ fragment vanished between listing and capture: $pi_f"; return 1; }
    pi_paths+=("$pi_f")
  done <<EOF
$frags
EOF
  pi_paths+=("$mono" "$AD/$(basename "$mono" .md)-archive.md")
  capture_preimage "drain qa-log" "${pi_paths[@]}" || return 1
  [ -f "$mono" ] || printf '# Brainstorming QA log\n\n## 📑 Index\n\n---\n' > "$mono" \
    || { echo "✗ cannot create $mono"; return 1; }
  ensure_trailing_nl "$mono"

  tmpblock="$(mktemp)" || { echo "✗ mktemp failed"; return 1; }
  appended="$(mktemp)" || { echo "✗ mktemp failed"; rm -f "$tmpblock"; return 1; }
  old_bytes=$(wc -c < "$mono")
  # Stage OLDEST-FIRST (ascending sort) — the OPPOSITE of drain_journal's newest-first.
  # drain_journal writes to an ARCHIVE (convention: newest-first at top). This compile target
  # is the HOT MONOLITH, whose convention is chronological-append: oldest-first, newest entry
  # is the LAST '## ' heading (§"The drain algorithm"). drain_monolith (called right after)
  # RELIES on that — it keeps the LAST KEEP entries as newest and evicts the FIRST m as oldest.
  # Appending an ascending block to the tail keeps the newest fragment as the last heading, so
  # the eviction partitions correctly. Idempotent-sentinel convention is shared with drain_journal.
  while IFS= read -r f; do
    if grep -qF "<!-- fragment: $f -->" "$mono"; then
      echo "  $f already compiled into $mono — skipping append (idempotent retry)"
    else
      { printf '\n<!-- fragment: %s -->\n' "$f"; cat "$f"; echo; } >> "$tmpblock" \
        || { echo "✗ read failure staging $f"; rm -f "$tmpblock" "$appended"; return 1; }
      echo "$f" >> "$appended"
    fi
  done <<<"$(sort <<<"$frags")"

  if [ -s "$tmpblock" ]; then
    # SECOND pre-flight, on the POST-COMPILE shape, still before anything is written. The one at
    # the top of this function saw only the pre-compile monolith; the compile itself can introduce
    # the contradiction (the fragments carry their own dated headings). Without this, that refusal
    # surfaces from the drain_monolith call at the foot of this function — after every fragment has
    # been deleted — while printing "nothing was moved". Run against a staged copy, reported under
    # the real monolith's name so the message and the Fix line name the file the operator has.
    staged="$(mktemp)" || { echo "✗ mktemp failed"; rm -f "$tmpblock" "$appended"; return 1; }
    cat "$mono" "$tmpblock" > "$staged" \
      || { echo "✗ staging the post-compile check copy failed"; rm -f "$tmpblock" "$appended" "$staged"; return 1; }
    preflight_ordering "$staged" "$mono" || { rc=$?; rm -f "$tmpblock" "$appended" "$staged"; return "$rc"; }
    rm -f "$staged"

    added=$(wc -c < "$tmpblock")
    cat "$tmpblock" >> "$mono" || { echo "✗ append to $mono failed"; rm -f "$tmpblock" "$appended"; return 1; }
    # VERIFY the monolith actually received every byte BEFORE deleting any fragment —
    # same discipline as drain_monolith's archive check: byte-count delta AND a sentinel
    # grep for every fragment just staged. A truncated/no-op append must never be followed
    # by a fragment delete — that would be silent data loss.
    new_bytes=$(wc -c < "$mono")
    rc=0
    while IFS= read -r f; do
      grep -qF "<!-- fragment: $f -->" "$mono" || rc=1
    done <"$appended"
    if [ "$new_bytes" -ne $((old_bytes + added)) ] || [ "$rc" -ne 0 ]; then
      echo "✗ monolith verification failed (${new_bytes}B, expected $((old_bytes + added))B) — fragments left untouched"
      rm -f "$tmpblock" "$appended"; return 1
    fi
  fi
  rm -f "$tmpblock" "$appended"

  # delete-vs-archive: fragments are mechanical once compiled into the hot monolith —
  # delete, git is cold storage. The qa-log CONTENT is decision-bearing and stays
  # preserved: it now lives in $mono, and drain_monolith below evicts old entries to
  # archive rather than deleting them.
  while IFS= read -r f; do rm -f -- "$f" || { echo "✗ failed to delete drained fragment $f"; return 1; }; done <<<"$frags"
  echo "  compiled qa-log fragments → $mono, $QD emptied"

  # Step two: evict old entries out of the now-larger hot monolith to archive (never
  # deleted — decision-bearing), same keep-window + verify-then-delete drain_monolith uses.
  drain_monolith "$mono"; rc=$?
  # `A && B` leaves B's status in a `$?` nobody reads, so a failed roll-over used to return 0
  # from here. Combined, not replaced: a drain failure must not be masked by a roll-over
  # that then succeeds. `set -e` would not have caught this because this script does not use it
  # (`set -uo pipefail`, deliberately — a drain aborting mid-tree is worse than one reporting).
  # It is NOT exempt under the AND-OR rule: that rule exempts every command of the list except
  # the LAST, and `check_rollover` was the last one. Measured, because the comment this replaces
  # claimed the opposite: under `set -e`, `[ "$rc" -eq 0 ] && roll` with a failing `roll` aborts.
  if [ "$rc" -eq 0 ]; then
    check_rollover "$AD/$(basename "$mono" .md)-archive.md" 50 || rc=$?
  fi
  return "$rc"
}

drain_legacy() {
  # chunk_lines=2000: bounds each read/append to well under a single tool-buffer/Read,
  # so a large legacy month moves in bounded, resumable pieces instead of one giant I/O op
  local src="$1" chunk_lines=2000 archive tmpdir c
  [ -f "$src" ] || { echo "✗ retention-drain legacy: no such file: $src"; return 1; }
  archive="$AD/journal/legacy-$(date +%Y-%m-%d).md"
  mkdir -p "$(dirname "$archive")" || { echo "✗ cannot create $(dirname "$archive")"; return 1; }
  # This mode overwrites the whole source with a two-line stub (at the end of this function) — the largest
  # single-file loss of the four, and the only one where the original survives nowhere else.
  capture_preimage "drain legacy $src" "$src" "$archive" || return 1
  ensure_trailing_nl "$archive"
  # whole-tail verbatim move, chunked by LINE COUNT only (never by content/meaning) —
  # legacy pre-convention content is never LLM-rewritten, never re-summarized
  tmpdir="$(mktemp -d)" || { echo "✗ mktemp -d failed"; return 1; }
  split -l "$chunk_lines" "$src" "$tmpdir/chunk-" || { echo "✗ split failed for $src"; rm -rf "$tmpdir"; return 1; }
  for c in "$tmpdir"/chunk-*; do
    cat "$c" >> "$archive" || { echo "✗ append failed writing $archive"; rm -rf "$tmpdir"; return 1; }
  done
  rm -rf "$tmpdir"
  { printf '# %s (legacy, pre-retention-convention)\n' "$(basename "$src")"
    pointer_stub "$archive" "chronological order preserved"; } > "$src" \
    || { echo "✗ rewrite of $src failed"; return 1; }
  echo "  legacy tail of $src moved verbatim (script-chunked, $chunk_lines lines/chunk) → $archive"
  return 0
}

check_rollover() {
  local archive="$1" cap_kb="${2:-25}" name segdir stage newarchive old kb threshold entries dated s
  [ -f "$archive" ] || return 0
  kb=$(( $(wc -c < "$archive") / 1024 )); threshold=$((cap_kb * 4))
  [ "$kb" -le "$threshold" ] && return 0
  name="$(basename "$archive" | sed 's/-archive\.md$//; s/\.md$//')"
  segdir="$AD/$name"
  mkdir -p "$AD" || { echo "✗ cannot create $AD"; return 1; }
  # The old shape reached `$segdir` through `mkdir -p`, which failed loudly when something that
  # was not a directory already sat there. The swap below stopped inheriting that check: it moves
  # `$segdir` aside only `if [ -d ]`, so a regular file sitting there would be left in place for
  # the second rename to trip over, with a message about a staged roll-over rather than about the
  # file. Refuse here, explicitly, rather than inherit the check by accident — the shape that
  # first made this necessary was an `rm -rf` that would simply have deleted it.
  if [ -e "$segdir" ] && [ ! -d "$segdir" ]; then
    echo "✗ $segdir exists and is not a directory — refusing to roll over $archive"; return 1
  fi
  # STAGE, THEN SWAP. The month split below writes in APPEND mode, so a run that dies partway
  # through leaves half-written segments — and the operator's correct response to the failure
  # being made visible is to retry, which appends the same entries a second time.
  # Making the failure loud without making the retry clean would be a net regression, and it
  # would be a WORSE one than the silence it replaced, because the silence never invited the
  # retry. Building the new state beside the old one and moving it into place means a failed
  # run leaves `$segdir` exactly as it found it, so a retry starts where the first attempt did.
  #
  # Staged inside `$AD` deliberately: `mktemp -d` under `$TMPDIR` is usually a different
  # filesystem, where the `mv` below degrades from a rename into a recursive copy and stops
  # being the cheap all-or-nothing step this depends on.
  stage="$(mktemp -d "$AD/.rollover-XXXXXX")" \
    || { echo "✗ cannot stage a roll-over for $archive"; return 1; }
  if [ -d "$segdir" ]; then
    # A second roll-over legitimately ADDS entries to a month an earlier one created, so the
    # stage begins as a copy of what is already there — never empty. Seeding it wrong would
    # trade duplicated content for lost content, which is the worse of the two.
    cp -R "$segdir/." "$stage/" 2>/dev/null \
      || { echo "✗ cannot stage the existing segments of $segdir"; rm -rf "$stage"; return 1; }
  fi
  entries=$(awk '/^## / && $0 !~ /Index[[:space:]]*$/ { c++ } END { print c+0 }' "$archive")
  dated=$(awk '/^## / && $0 !~ /Index[[:space:]]*$/ && /[0-9][0-9][0-9][0-9]-[0-9][0-9]/ { c++ } END { print c+0 }' "$archive")
  if [ "$entries" -gt 0 ] && [ "$entries" -eq "$dated" ]; then
    # every entry heading carries a date → split by month into YYYY-MM.md segments
    # EVERY line reaches a segment, including the ones ABOVE the first entry heading. The rule is
    # "a line belongs to the segment named by the nearest PRECEDING heading", and the shape this
    # replaces wrote nothing at all while no heading had been seen yet -- so the archive's own
    # title, its `## 📑 Index` heading (excluded from the match on purpose), every TOC bullet the
    # drain had just regenerated, and the `---` separator were dropped by a step whose whole
    # contract is a verbatim move. MEASURED on the tracked script with an 8-entry fixture whose
    # archive holds 5: 10 lines reached no segment. A fragment marker sitting in that region goes
    # with them, and that is the one way a roll-over can turn an observed stage into a missing one.
    #
    # WHAT THAT COSTS, measured rather than left for the next reader to discover: the held region
    # is mostly the archive's own GENERATED header, so it now travels into a segment instead of
    # being dropped. First roll-over: 8 such lines (the title, `## 📑 Index`, the five then-current
    # TOC bullets, `---`) land in the segment named by the archive's first dated heading. Each
    # LATER roll-over adds exactly ONE more line that this change is responsible for: the previous
    # run's stub TITLE. Its pointer-stub line was already travelling before this change -- it sits
    # after the last heading, so the old rule printed it too, measured on a reverted copy as 0
    # titles and 1 pointer after a second roll-over. The title lands in the segment of the first
    # dated heading, which can be the same file twice across two roll-overs. Bounded, and the
    # second-roll-over fixture in the drain suite is what keeps that from being a stale comment.
    #
    # THE NARROWER RULE WAS REJECTED ON ERROR DIRECTION, not on effort. Recognising the drain's own
    # generated shapes and holding only the rest needs five matchers, one of them the TOC bullet
    # `- ...`, which is a shape ordinary content uses. That would trade two generated lines per
    # roll-over for a chance of deleting a content line, in a function whose every other ambiguity
    # is resolved the other way. An independent review raised the accumulation; this is the answer
    # to it, and the fixture is the part that cannot go stale.
    #
    # The other branch of this same function (`split -l`, below) has always moved those lines.
    # Two branches of one verbatim-move contract disagreeing is what makes this a defect rather
    # than a layout choice -- so the comparison is a test, not this paragraph.
    #
    # HELD, not written to a default segment: the first heading decides where they go, so nothing
    # has to invent a name for a segment that has not been named yet. The END refusal below is
    # unreachable while this branch is entered only with at least one DATED heading present; it is
    # there so a silent drop cannot come back if that condition changes.
    #
    # WHAT THIS DELIBERATELY DOES NOT DO: move a marker back next to the block it names. In an
    # archive a marker is already not above its own block -- `drain_monolith` slices entries from
    # heading to heading, so a marker sits at the tail of the PREVIOUS entry, and the newest-first
    # reassembly then reorders those entries. Measured on this fixture: the marker naming the
    # 2026-02 fragment ends up at the tail of `2026-01.md`. Any "keep it with the heading below"
    # rule here would move such a line to a second wrong file while reading as if it had fixed
    # something. The adjacency is lost upstream, at eviction, which is filed rather than widened
    # into this task.
    awk -v segdir="$stage" '
      function flush(dest,   i) { for (i = 1; i <= nheld; i++) print held[i] >> dest; nheld = 0 }
      /^## / && $0 !~ /Index[[:space:]]*$/ {
        m = $0
        if (match(m, /[0-9][0-9][0-9][0-9]-[0-9][0-9]/)) mo = substr(m, RSTART, 7)
        out = segdir "/" mo ".md"
        flush(out)
      }
      out == "" { held[++nheld] = $0; next }
      { print >> out }
      END { if (nheld > 0) exit 1 }
    ' "$archive" \
      || { echo "✗ roll-over month split failed for $archive"; rm -rf "$stage"; return 1; }
  else
    # undated (or mixed) headings → deterministic LINE-COUNT chunk split, same mechanic
    # as drain_legacy — never an "undated.md" catch-all segment.
    #
    # THE PIECES CONTINUE THE SEQUENCE; THEY DO NOT REUSE ITS NAMES. `split -l … "$stage/part-"`
    # restarts at `part-aa` every time, and the rename to `part-aa.md` then OVERWRITES the seeded
    # copy of the segment an earlier roll-over wrote. So this branch DESTROYED history while the
    # month branch above, which appends into the same seeded copy, preserved it -- two branches of
    # one verbatim-move contract disagreeing, which the comment above already calls a defect
    # rather than a layout choice. It was measured, not reasoned: a close drain
    # rolled the qa-log archive over a second time and entry headings stopped
    # existing anywhere in the working tree (archive segments were
    # rewritten), leaving the pre-image ring as the only copy -- in the phase whose whole subject
    # is that the ring is an undo buffer and not evidence. git held the content, which is the
    # cold-storage path this phase rewrote this file's own comment to name.
    #
    # So: split into a scratch directory, then move each piece to the suffix that CONTINUES the
    # ones already staged -- `n_existing + k`, a count, not a search for the lowest unused name.
    # Said precisely because the difference is observable: against a non-contiguous set
    # (`part-aa`, `part-ac`) the computed target is `part-ac`, which exists, and this refuses
    # instead of filling the free `part-ab`. That is the fail-CLOSED direction and it is the one
    # to be on in this branch, where silently reusing a name is exactly what went wrong -- but
    # "the next free suffix", which this comment used to say, describes a search the code does
    # not do. The no-overwrite property is an assertion below, not an assumption.
    local newdir="$stage/.split" n_existing=0 k=0 target hi lo
    # The suffix alphabet is a plain string sliced with parameter expansion, not `cut -c`: that
    # utility counts CHARACTERS per the ambient locale, and this repo already paid for one
    # locale-dependent truncation (`plc_utf8_head`/`plc_utf8_tail` exist because of it). The
    # input here is ASCII, so `cut -c` would in fact be correct -- the rule it would violate is
    # attached to the SHAPE, and an exemption for the whole drain would hide the next real one.
    local alpha="abcdefghijklmnopqrstuvwxyz"
    mkdir -p "$newdir" \
      || { echo "✗ cannot stage the chunk split for $archive"; rm -rf "$stage"; return 1; }
    split -l 2000 "$archive" "$newdir/part-" \
      || { echo "✗ roll-over chunk split failed for $archive"; rm -rf "$stage"; return 1; }
    for s in "$stage"/part-*.md; do [ -f "$s" ] && n_existing=$((n_existing + 1)); done
    for s in "$newdir"/part-*; do
      [ -f "$s" ] || continue
      # Two-letter suffixes in `split`'s own order, continued: aa, ab, … zz. 676 segments is a
      # refusal rather than a wrap, because a wrapped name is an overwrite wearing a new label.
      if [ $((n_existing + k)) -ge 676 ]; then
        echo "✗ $segdir already holds 676 segments — refusing to roll over $archive"
        rm -rf "$stage"; return 1
      fi
      hi=$(( (n_existing + k) / 26 )); lo=$(( (n_existing + k) % 26 ))
      target="$stage/part-${alpha:hi:1}${alpha:lo:1}.md"
      if [ -e "$target" ]; then
        echo "✗ roll-over would overwrite $target — refusing, nothing has been swapped in"
        rm -rf "$stage"; return 1
      fi
      mv "$s" "$target" \
        || { echo "✗ rename failed for $s"; rm -rf "$stage"; return 1; }
      k=$((k + 1))
    done
    rmdir "$newdir" 2>/dev/null || true
  fi
  { echo "# Segment index — $name"; echo
    for s in "$stage"/*.md; do
      [ "$(basename "$s")" = index.md ] && continue
      echo "- $(basename "$s")"
    done
  } > "$stage/index.md" \
    || { echo "✗ cannot write $segdir/index.md"; rm -rf "$stage"; return 1; }
  # STAGE THE REWRITTEN ARCHIVE TOO, and stage it BEFORE the swap. This used to be written
  # after, and a failure there returned 1 with `$segdir` ALREADY replaced while `$archive` still
  # held every entry — so the retry that non-zero exit invites split the same entries into the
  # new tree a second time and exited 0. That is precisely the "visible failure with a dirty
  # retry" this function exists to prevent, reached by a path the fixtures below could not see:
  # they inject on `$segdir`, which fails at the swap and never reaches the region where the
  # property broke. MEASURED on the tracked implementation with a read-only archive FILE — the
  # blocked run mutated the tree and the retry doubled all eight entries.
  #
  # `pointer_stub` is pure text, so nothing here needs `$segdir` to be in place yet.
  #
  # The name is DERIVED from `$segdir`, not from the random `$stage`, so a fixture can reach it.
  # With an unpredictable name nothing outside this function can make THIS write fail, and a
  # measured consequence: moving the staging back below the swap left the whole suite
  # green. An unreachable failure path is an unguarded one.
  newarchive="$segdir.rollover-archive"
  if [ -e "$newarchive" ] && [ ! -f "$newarchive" ]; then
    echo "✗ $newarchive exists and is not a regular file — refusing to roll over $archive"
    rm -rf "$stage"; return 1
  fi
  { printf '# %s — archive, rolled over into segments\n\n' "$name"
    pointer_stub "$segdir/index.md" "see segment index"; } > "$newarchive" \
    || { echo "✗ cannot stage the rewritten $archive"; rm -rf "$stage"; rm -f "$newarchive"; return 1; }
  # MOVE ASIDE, never delete-then-move. `rm -rf "$segdir" && mv …` was NOT all-or-nothing:
  # `rm -rf` deletes what it can and only then reports failure, so a single stubborn entry inside
  # `$segdir` left the other segments already deleted, the archive still a pointer stub from an
  # earlier run, and the entries recorded `absent` in the pre-image slot — meaning `restore` would
  # REMOVE them rather than bring them back. MEASURED: five previously archived entries gone, and
  # the retry exited 0. The reflex that catches this class:
  # `rm -rf` is not a swap.
  #
  # Two renames instead. Each is all-or-nothing, and the old tree survives under `$old` until the
  # new one is in place, so a failure between them is recoverable — and the handler puts it back
  # rather than leaving the operator to.
  #
  # POSIX still has no atomic directory EXCHANGE (`renameat2(RENAME_EXCHANGE)` is Linux-only), so
  # a crash — not a failure, a crash — between the two renames leaves `$segdir` absent with the
  # old tree at `$old` and the new one at `$stage`. That window is far smaller than the one it
  # replaces and both copies are on disk, but it is NOT closed; stated rather than implied away.
  old=""
  if [ -d "$segdir" ]; then
    old="$stage.old"
    mv "$segdir" "$old" \
      || { echo "✗ cannot move $segdir aside for the roll-over"; rm -rf "$stage"; rm -f "$newarchive"; return 1; }
  fi
  if ! mv "$stage" "$segdir"; then
    echo "✗ cannot move the staged roll-over into $segdir"
    [ -n "$old" ] && mv "$old" "$segdir"
    rm -rf "$stage"; rm -f "$newarchive"; return 1
  fi
  # Everything roll-over just created is new to the tree. Record it in the drain's own slot as
  # `absent` so a restore of that key removes it; the archive itself is already captured, so it
  # comes back from the slot rather than from here.
  preimage_note_absent "$segdir/index.md" "$segdir"/*.md
  # A rename, not a rewrite: it replaces the directory entry, so it does not need `$archive`
  # itself to be writable, and it cannot leave the archive half-written. `-f` because a
  # non-writable destination makes POSIX `mv` prompt when stdin is a terminal — which pytest
  # never provides, so the suite CANNOT distinguish `mv` from `mv -f` here. Kept and named
  # deliberately: a green suite is not evidence for this flag.
  mv -f "$newarchive" "$archive" \
    || { echo "✗ cannot rewrite $archive"; rm -f "$newarchive"; return 1; }
  # Only now is the old tree unreachable by anything that could still have needed it. A failure
  # here is not a roll-over failure — the new tree is in place and correct — but it must not print
  # raw `rm:` lines and call that reporting. Name it, and say what to do.
  if [ -n "$old" ]; then
    rm -rf "$old" 2>/dev/null \
      || echo "  ⚠ rolled over, but the previous segments are still at $old — remove them by hand"
  fi
  echo "  rolled over $archive (${kb}K > ${threshold}K = 4x ${cap_kb}K) → $segdir/*.md + index.md"
  return 0
}

archive_working() {  # $1 = path under docs/, $2 = archive dir (default: $AD, i.e. config archive_dir)
  local src="$1" adir="${2:-$AD}"
  case "$src" in
    */screenshots/*) echo "✗ refusing: $src is a load-bearing PR asset, not a document" >&2; return 1 ;;
    docs/*) ;;
    *) echo "✗ refusing: $src is not under docs/" >&2; return 1 ;;
  esac
  local rel="${src#docs/}" dst
  dst="$adir/working/$rel"
  if [ ! -e "$src" ]; then
    # idempotent: already archived (a prior run moved it and the cadence retried) is
    # success — a path that was never archived and doesn't exist is a real miss.
    [ -e "$dst" ] && { echo "= already archived: $dst"; return 0; }
    echo "✗ not found: $src" >&2; return 1
  fi
  if [ -e "$dst" ]; then
    # $src exists AND $dst already exists: NOT the idempotent-retry case above (that requires
    # $src gone). This is a re-opened/re-created track whose spec/plan filename collides with an
    # already-archived original — a plain `mv` here would silently overwrite that original, which
    # is the SOLE evidence the deferred-deletion decision rests on (retention.md §"The three
    # tiers", Deep-cold row: "prove the distill lossless against the archived original over 2-3
    # tracks"). Byte-identical is a harmless no-op (already archived, nothing to lose); anything
    # else refuses rather than clobbers.
    if cmp -s "$src" "$dst"; then
      echo "= already archived, byte-identical: $dst"; return 0
    fi
    echo "✗ refusing: $dst already exists and differs from $src — not overwriting the archived original (it is the sole evidence for the distill-vs-original comparison)" >&2
    return 1
  fi
  mkdir -p "$(dirname "$dst")" || { echo "✗ cannot create $(dirname "$dst")" >&2; return 1; }
  # `git mv` fails outright on an untracked path (common when docs/ is gitignored,
  # so PLC-minted spec/plan files are frequently untracked) — probe tracked state first and
  # fall back to plain `mv` rather than letting the whole archive attempt fail on that alone.
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1 \
     && git ls-files --error-unmatch -- "$src" >/dev/null 2>&1; then
    git mv -- "$src" "$dst" || { echo "✗ git mv failed: $src → $dst" >&2; return 1; }
  else
    mv -- "$src" "$dst" || { echo "✗ mv failed: $src → $dst" >&2; return 1; }
  fi
  echo "→ archived: $src → $dst"
  return 0
}

CMD="${1:-}"; SUB="${2:-}"
# `config <key>` exists because a policy key with no readable EFFECTIVE value cannot be checked:
# the declaration and the number the drain acts on are two different things, and the gap between
# them is where a malformed declaration hides behind a silent fallback. These are the same
# variables every drain path uses -- computed once at load, above, with the same fallbacks -- so
# the accessor cannot drift from the behaviour it reports. Read-only; it moves no bytes.
if [ "$CMD" = "config" ]; then
  case "$SUB" in
    preimage_keep) printf '%s\n' "$PIKEEP" ;;
    archive_dir)   printf '%s\n' "$AD" ;;
    journal_dir)   printf '%s\n' "$JD" ;;
    qa_log_dir)    printf '%s\n' "$QD" ;;
    *) echo "✗ usage: retention-drain.sh config <preimage_keep|archive_dir|journal_dir|qa_log_dir>"; exit 1 ;;
  esac
  exit 0
fi
if [ "$CMD" = "restore" ]; then
  [ -n "$SUB" ] || { echo "✗ usage: retention-drain.sh restore <key>   (keys: $PID)"; exit 1; }
  drain_restore "$SUB"
  exit $?
fi
if [ "$CMD" = "archive-working" ]; then
  [ -n "${2:-}" ] || { echo "✗ usage: retention-drain.sh archive-working <path> [archive_dir]"; exit 1; }
  archive_working "${2:-}" "${3:-}"
  exit $?
fi
if [ "$CMD" != "drain" ]; then
  echo "✗ usage: retention-drain.sh drain <monolith.md>|journal|qa-log|legacy <file> [rollover_cap_kb]|archive-working <path> [archive_dir]|config <key>"; exit 1
fi
case "$SUB" in
  "")
    echo "✗ usage: retention-drain.sh drain <monolith.md>|journal|qa-log|legacy <file> [rollover_cap_kb]"; exit 1 ;;
  journal)
    drain_journal; exit $? ;;
  qa-log)
    drain_qa_log; exit $? ;;
  legacy)
    LEGACY_FILE="${3:-}"
    [ -n "$LEGACY_FILE" ] || { echo "✗ usage: retention-drain.sh drain legacy <file>"; exit 1; }
    drain_legacy "$LEGACY_FILE"; exit $? ;;
  *)
    drain_monolith "$SUB"; rc=$?
    # Same propagation as drain_qa_log's tail — one defect, two call sites.
    if [ "$rc" -eq 0 ]; then
      check_rollover "$AD/$(basename "$SUB" .md)-archive.md" "${3:-25}" || rc=$?
    fi
    exit "$rc" ;;
esac
