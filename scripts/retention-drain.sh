#!/usr/bin/env bash
# scripts/retention-drain.sh — deterministic, no-LLM archival drain for the hot/cold model.
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
# Deliberately does NOT `set -e`: content/keep-window decisions must never abort a drain.
# Exits non-zero only on I/O or usage errors — never on "nothing to drain".
set -uo pipefail

M=".claude/close-gate.json"
g() { [ -f "$M" ] && jq -r ".retention.$1 // empty" "$M" 2>/dev/null; }

AD="$(g archive_dir)"; AD="${AD:-docs/archive}"
case "$AD" in
  docs/*) : ;;
  *) echo "⚠ retention.archive-dir '$AD' outside docs/ — config error, falling back to docs/archive"; AD="docs/archive" ;;
esac
JD="$(g journal_dir)"; JD="${JD:-docs/journal.d}"
QD="$(g qa_log_dir)"; QD="${QD:-docs/qa-log.d}"
KEEP=3   # active + 2 most recent closed '## ' entries — the LAST 3 headings of the source

mkdir -p "$AD" || { echo "✗ cannot create archive dir $AD"; exit 1; }

# newline-guard: never let an append land glued to the previous line
ensure_trailing_nl() {
  [ -s "$1" ] || return 0
  [ "$(tail -c1 "$1" | wc -l)" -eq 0 ] && printf '\n' >> "$1"
  return 0
}

pointer_stub() { # $1 = archive path   $2 = ordering note for the archived content
  printf '> Earlier entries archived verbatim (%s): → %s\n' "$2" "$1"
}

drain_monolith() {
  local src="$1" name archive tmpdir starts_s n m keepstart first_start
  local idx_line sep_line old_bytes new_bytes added i s e
  [ -f "$src" ] || { echo "✗ retention-drain: no such file: $src"; return 1; }
  name="$(basename "$src" .md)"
  archive="$AD/${name}-archive.md"

  # Entry boundaries. Source monoliths are chronological-append (document-indexing.md:
  # new sections land at the BOTTOM, so the newest entry is the LAST '## ' heading).
  # The doc's own TOC heading ('## 📑 Index') is not an entry — exclude any '## …Index' heading.
  starts_s="$(awk '/^## / && $0 !~ /Index[[:space:]]*$/ { print NR }' "$src")"
  [ -z "$starts_s" ] && { echo "  $src: no '## ' entries — nothing to drain"; return 0; }
  local starts=($starts_s)
  n=${#starts[@]}
  [ "$n" -le "$KEEP" ] && { echo "  $src: $n entries <= keep-window $KEEP — nothing to drain"; return 0; }

  m=$((n - KEEP))            # evicted = the m OLDEST entries (the head of the file)
  keepstart=${starts[m]}     # first kept entry — the last KEEP entries are active + 2
  first_start=${starts[0]}

  tmpdir="$(mktemp -d)" || { echo "✗ mktemp -d failed"; return 1; }
  # Assemble the evicted block NEWEST-FIRST: reverse the ENTRY order (ring convention),
  # each entry extracted as a byte-verbatim line range. TOC bullets are plain text —
  # no hand-computed anchor links (document-indexing.md's anti-pattern: anchor guesses).
  for ((i = m - 1; i >= 0; i--)); do
    s=${starts[i]}; e=$(( ${starts[i+1]} - 1 ))
    sed -n "${s},${e}p" "$src" >> "$tmpdir/block" \
      || { echo "✗ read failure extracting entries from $src"; rm -rf "$tmpdir"; return 1; }
    sed -n "${s}p" "$src" | sed 's/^## /- /' >> "$tmpdir/toc"
  done

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

  # rewrite source: doc header (H1 + its own TOC) stays, a pointer stub replaces the
  # evicted entries, the last KEEP entries (active + 2) stay
  {
    [ "$first_start" -gt 1 ] && sed -n "1,$((first_start - 1))p" "$src"
    pointer_stub "$archive" "newest-first"
    echo
    sed -n "${keepstart},\$p" "$src"
  } > "$tmpdir/src.new" && mv "$tmpdir/src.new" "$src" \
    || { echo "✗ rewrite of $src failed (archive already updated — safe to re-run)"; rm -rf "$tmpdir"; return 1; }

  rm -rf "$tmpdir"
  echo "  drained $m entries from $src → $archive (verbatim, newest-first, pointer stub + TOC entries left)"
  return 0
}

drain_journal() {
  [ -d "$JD" ] || { echo "  $JD: no such directory — nothing to drain"; return 0; }
  local frags month archive f
  frags="$(find "$JD" -maxdepth 1 -type f -name '*.md' | sort)"
  [ -z "$frags" ] && { echo "  $JD: no fragments — nothing to drain"; return 0; }
  month="$(date +%Y-%m)"
  archive="$AD/journal/$month.md"
  mkdir -p "$(dirname "$archive")" || { echo "✗ cannot create $(dirname "$archive")"; return 1; }
  [ -f "$archive" ] || printf '# Journal archive — %s\n\n## 📑 Index\n\n---\n' "$month" > "$archive" \
    || { echo "✗ cannot create $archive"; return 1; }
  ensure_trailing_nl "$archive"
  # Compile newest-first: fragment filenames are date-prefixed, so descending sort = newest
  # first. The per-fragment sentinel makes a retried drain IDEMPOTENT: a fragment that was
  # already compiled (crash between append and delete) is skipped, never duplicated.
  while IFS= read -r f; do
    if grep -qF "<!-- fragment: $f -->" "$archive"; then
      echo "  $f already compiled into $archive — skipping append (idempotent retry)"
    else
      { printf '\n<!-- fragment: %s -->\n' "$f"; cat "$f"; echo; } >> "$archive" \
        || { echo "✗ append of $f to $archive failed"; return 1; }
    fi
  done <<<"$(sort -r <<<"$frags")"
  # delete-vs-archive: fragments are mechanical once compiled — delete, git is cold storage
  while IFS= read -r f; do rm -f -- "$f" || { echo "✗ failed to delete drained fragment $f"; return 1; }; done <<<"$frags"
  echo "  drained journal fragments → $archive, $JD emptied"
  # no roll-over pass: journal archives are already month-segmented by filename (YYYY-MM.md)
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
  local mono="docs/brainstorming-qa-log.md" frags f old_bytes new_bytes added tmpblock appended rc
  [ -d "$QD" ] || { echo "  $QD: no such directory — nothing to drain"; return 0; }
  frags="$(find "$QD" -maxdepth 1 -type f -name '*.md' | sort)"
  [ -z "$frags" ] && { echo "  $QD: no fragments — nothing to drain"; return 0; }
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
  [ "$rc" -eq 0 ] && check_rollover "$AD/$(basename "$mono" .md)-archive.md" 50
  return "$rc"
}

drain_legacy() {
  # chunk_lines=2000: bounds each read/append to well under a single tool-buffer/Read,
  # so a large legacy month moves in bounded, resumable pieces instead of one giant I/O op
  local src="$1" chunk_lines=2000 archive tmpdir c
  [ -f "$src" ] || { echo "✗ retention-drain legacy: no such file: $src"; return 1; }
  archive="$AD/journal/legacy-$(date +%Y-%m-%d).md"
  mkdir -p "$(dirname "$archive")" || { echo "✗ cannot create $(dirname "$archive")"; return 1; }
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
  local archive="$1" cap_kb="${2:-25}" name segdir kb threshold entries dated s
  [ -f "$archive" ] || return 0
  kb=$(( $(wc -c < "$archive") / 1024 )); threshold=$((cap_kb * 4))
  [ "$kb" -le "$threshold" ] && return 0
  name="$(basename "$archive" | sed 's/-archive\.md$//; s/\.md$//')"
  segdir="$AD/$name"
  mkdir -p "$segdir" || { echo "✗ cannot create $segdir"; return 1; }
  entries=$(awk '/^## / && $0 !~ /Index[[:space:]]*$/ { c++ } END { print c+0 }' "$archive")
  dated=$(awk '/^## / && $0 !~ /Index[[:space:]]*$/ && /[0-9][0-9][0-9][0-9]-[0-9][0-9]/ { c++ } END { print c+0 }' "$archive")
  if [ "$entries" -gt 0 ] && [ "$entries" -eq "$dated" ]; then
    # every entry heading carries a date → split by month into YYYY-MM.md segments
    awk -v segdir="$segdir" '
      /^## / && $0 !~ /Index[[:space:]]*$/ {
        m = $0
        if (match(m, /[0-9][0-9][0-9][0-9]-[0-9][0-9]/)) mo = substr(m, RSTART, 7)
        out = segdir "/" mo ".md"
      }
      out != "" { print >> out }
    ' "$archive" || { echo "✗ roll-over month split failed for $archive"; return 1; }
  else
    # undated (or mixed) headings → deterministic LINE-COUNT chunk split, same mechanic
    # as drain_legacy — never an "undated.md" catch-all segment
    split -l 2000 "$archive" "$segdir/part-" || { echo "✗ roll-over chunk split failed for $archive"; return 1; }
    for s in "$segdir"/part-*; do
      case "$s" in *.md) : ;; *) mv "$s" "$s.md" || { echo "✗ rename failed for $s"; return 1; } ;; esac
    done
  fi
  { echo "# Segment index — $name"; echo
    for s in "$segdir"/*.md; do
      [ "$(basename "$s")" = index.md ] && continue
      echo "- $(basename "$s")"
    done
  } > "$segdir/index.md" || { echo "✗ cannot write $segdir/index.md"; return 1; }
  { printf '# %s — archive, rolled over into segments\n\n' "$name"
    pointer_stub "$segdir/index.md" "see segment index"; } > "$archive" \
    || { echo "✗ cannot rewrite $archive"; return 1; }
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
if [ "$CMD" = "archive-working" ]; then
  [ -n "${2:-}" ] || { echo "✗ usage: retention-drain.sh archive-working <path> [archive_dir]"; exit 1; }
  archive_working "${2:-}" "${3:-}"
  exit $?
fi
if [ "$CMD" != "drain" ]; then
  echo "✗ usage: retention-drain.sh drain <monolith.md>|journal|qa-log|legacy <file> [rollover_cap_kb]|archive-working <path> [archive_dir]"; exit 1
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
    [ "$rc" -eq 0 ] && check_rollover "$AD/$(basename "$SUB" .md)-archive.md" "${3:-25}"
    exit "$rc" ;;
esac
