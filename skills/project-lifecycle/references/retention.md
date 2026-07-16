# Document retention — the hot/cold model

A long-running project's `docs/` tree reached tens of megabytes across hundreds of files, with individual hot docs and single journal months each hundreds of kilobytes — while every existing ring/slicing/archive mechanism was already running. The failure was never absence of mechanism; it was **coverage + regrowth**: new append-only docs escaped the net, and docs that were being maintained still crept back up between maintenance passes. This reference is the fix — a small set of dual-limit caps, a coverage-discovery net, and a deterministic drain that runs at the one moment nothing else is competing for attention: milestone close. Every transition below is **event-triggered off the existing lifecycle** (phase-done, milestone-done), never a calendar chore a human has to remember.

## The three tiers

| Tier | What lives here | Size discipline | Transition out |
|---|---|---|---|
| **Hot** (always-read) | RESUME/status active section, journal fragments (`docs/journal.d/`), qa-log hot zone (`docs/qa-log.d/` + hot monolith), changelog fragments (`changelog.d/`) | Dual caps (lines AND KB), warn-only rows at `phase-done` | Milestone-close drain |
| **Cold** (discoverable archive) | `docs/archive/<name>-archive.md`, rolled segments `docs/archive/<name>/YYYY-MM.md` | 4× cap roll-over, never read by default | Never deleted if decision-bearing |
| **Deep-cold** | git history | — | Mechanical artifacts are deleted at drain; git is their storage. **Working docs (spec/plan) are the exception: they are MOVED to `<archive_dir>/working/` by `archive-working`, never deleted — deletion is deferred pending distill-quality evidence (2–3 tracks).** |

Plus one upward flow: **distill**, at milestone close, promotes surviving knowledge (locked decisions → `CONTEXT.md` glossary entries / ADR offers / principle lines) with a human one-tap approval per item — see §"Distill protocol" below.

## Hot-doc caps

Every hot doc gets a dual limit — **lines AND KB, whichever hits first** — checked as a warn-only row at `phase-done`. These defaults follow the same precedent that shaped `close-gate.md`'s context-floor row: the MEMORY.md-25K convention and the general context-rot evidence for always-read files 🟢.

| Doc | Lines | KB |
|---|---|---|
| `RESUME.md` | 200 | 25K |
| status doc (read-first) | 300 | 30K |
| journal hot zone (`docs/journal.d/` total) | — | 100K |
| qa-log hot monolith (`docs/brainstorming-qa-log.md`) | — | 50K |
| qa-log fragment dir (`docs/qa-log.d/` total) | — | 50K |
| changelog hot zone (`changelog.d/` total) | — | 50K |

**qa-log's two caps are independent, not summed.** The monolith and the fragment dir are each checked against their own 50K ceiling separately — the gate never adds them together into a combined budget. This mirrors `close-gate.sh`'s own comment on the fragment-dir check: its cap is *additional to* the monolith file cap, not a replacement for it. A project can be well under 50K on the monolith and still trip the fragment-dir row (or the reverse). The two checks share one exemption key (`qa-log`) and one override value in `retention.hot-caps` — setting `qa-log: 100K` raises both ceilings to 100K independently, it does not create a single 100K combined pool.

**Measured whole-file, deliberately.** For the status doc, "the active section" is the literal AC wording, but mechanically parsing section semantics to isolate it is the wrong layer here — the drain algorithm below already guarantees active + 2 closed entries ≈ the whole file, so measuring the whole file against the cap is deterministic and, once the drain is running, equivalent in practice. Deterministic beats precise.

**Escalation.** The gate persists an over-cap list to `.claude/retention-state.json` (`over_cap_at_last_close`) at every close. If the *same* doc is over-cap at two consecutive closes, the warn row's wording gains an explicit flag: `"SECOND consecutive over-cap close — this doc is not draining"`. Still warn-only — escalation is louder wording, never a failing gate, in v1.

**Override.** Project `CLAUDE.md` sets `retention.hot-caps` to raise or lower any doc's cap. `<doc>: none` is the **only** exemption mechanism — there is deliberately no exempt list. An exempt list recreates exactly the coverage gap this reference exists to close: the moment a doc is exempted by name instead of by an explicit `none`, someone forgets to add the next one.

## Coverage discovery

The known set = files referenced by `.claude/close-gate.json` manifest keys, plus everything under `docs/journal.d/**`, plus everything under `docs/qa-log.d/**`, plus everything under `changelog.d/**`, plus everything under `retention.archive-dir/**`. Any other file matching `docs/**/*.md` that exceeds the coverage floor (default 50K) and is outside that known set gets a warn row at `phase-done`:

```
⚠ coverage: docs/some-new-doc.md (62K) not in retention net — add to manifest known set or archive it
```

This is the row that answers the actual observed failure mode: a brand-new append-only doc (a second qa-log, a per-feature notes file, anything) can grow to that territory unnoticed because no existing check was ever wired to watch it. Coverage discovery watches the filesystem, not a fixed list — a new doc can't opt out just by not being named anywhere.

## The drain algorithm

Runs at milestone close (cadence step 10), deterministic, no LLM involved anywhere in this step:

1. **Per known append-only monolith** (RESUME, status doc, qa-log, or any other doc tracked by the manifest): these docs append chronologically — per `document-indexing.md`, a new entry lands at the **bottom**, so the newest entry is the **last** `## ` heading, and the doc's own `## 📑 Index` heading is not an entry. The drain keeps the **last active + 2 most recent closed `## ` entries** and evicts the older head entries into `<archive-dir>/<name>-archive.md`, where they are written **newest-first** (entry *order* is reversed at write time; each entry itself stays byte-verbatim). The archive append is **byte-verified before the source is rewritten** — if the archive did not demonstrably receive every byte, the source is left untouched and the drain exits non-zero. A one-line pointer stub replaces the evicted entries in the source, and each evicted entry gets a TOC line in the archive file (per `document-indexing.md`).
2. **Journal fragments**: compile the phase's fragments (newest-first) into `<archive-dir>/journal/YYYY-MM.md`, then **delete** the fragments — the hot directory drains to zero, towncrier-style. Pure file operations.
3. **Roll-over**: any archive file that exceeds **4× its source doc's cap** splits into `<archive-dir>/<name>/YYYY-MM.md` segments plus a `<archive-dir>/<name>/index.md` segment index. The date-split applies to archives whose entry headings carry dates (qa-log style); an archive whose headings carry no usable dates falls back to a deterministic **line-count chunk split** (`part-NN.md` segments, same mechanic as the legacy mover) — never an `undated.md` catch-all. Journal archives never roll: they are already month-segmented by their `YYYY-MM.md` filenames.
4. **Delete-vs-archive**: decision-bearing content (journal entries, qa-log, ADRs, specs) is archived, never deleted. Mechanical artifacts (drained journal fragments once compiled, scratch files, regenerable HTML companions) are deleted at drain time — git is their cold storage, not `docs/archive/`.

Like the status-file ring it generalizes (`roadmap.md` §"Close protocol — the status-file ring"), this drain is **deliberately ungated** in v1: no hard gate row blocks a close that skips it. The hot-doc-cap warn rows above are what make a skipped drain visible — the next close simply shows the same doc over-cap, and after two closes the wording escalates.

## Embedded portable script — `scripts/retention-drain.sh`

Same ship-pattern as `close-gate.sh`: this repo carries the spec below as the canonical, reviewable source; a project materializes its own copy under `scripts/retention-drain.sh` via `/init-harness`. Pure bash + standard POSIX-ish text tools (`awk`, `sed`, `split`, `jq` for the manifest read), no stack assumptions. Portability notes baked in: no multi-line `awk -v` values (BSD awk rejects newlines in `-v` strings — multi-line content moves through temp files and `sed <line>r <file>` insertion instead), and no `\x` hex escapes inside awk regex literals (BSD awk does not interpret them; matching silently no-ops).

This block is checked byte-for-byte against `scripts/retention-drain.sh` by `scripts/test_retention_drain.py`, so a drifted mirror fails the test suite instead of going unnoticed.

```bash
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
```

## Fragment convention

### Journal

**Write path:** per-branch journal entries append to the current branch's fragment file, `docs/journal.d/<date>-<branch-slug>.md`, instead of the monthly monolith. **One fragment per branch, not per task** — if the branch's fragment already exists, append to it. Under WIP=1, branch and phase are effectively the same unit of work, so this reads as "one fragment per phase" in practice — the file is named for the branch specifically so two branches active at once (or a branch that outlives one phase) never collide on a shared filename. The entry still follows the same 6-section schema unchanged.

**No per-fragment TOC.** Fragments are short-lived hot files — they exist only until the next milestone close drains them — so they carry no TOC obligation. The compiled archive month file (`docs/archive/journal/YYYY-MM.md`) carries the TOC instead, per `document-indexing.md`.

**Compile + drain.** At milestone close (`retention-drain.sh drain journal`), the fragments compile newest-first into `docs/archive/journal/YYYY-MM.md`, then the fragments are deleted — the hot directory drains to zero, towncrier-style, purely mechanically. No LLM step anywhere in this path. The compile is idempotent on retry: each fragment is recorded in the archive under a `<!-- fragment: … -->` sentinel, so a drain interrupted between append and delete skips already-compiled fragments instead of duplicating them.

**Legacy monolith contingency.** A pre-convention monolith (`docs/iteration-journal.md`) that already exists when the fragment convention is adopted is handled by `retention-drain.sh drain legacy <file>`: the whole tail moves in one verbatim, script-chunked move (chunked by line count only) to `docs/archive/journal/legacy-<date>.md`, with a pointer stub left behind. It is **never LLM-rewritten or summarized** — legacy content is moved, not reinterpreted.

### qa-log

**Write path:** per-branch Q&A entries append to the current branch's fragment file, `docs/qa-log.d/<date>-<branch-slug>.md`, instead of the hot monolith directly. Same one-fragment-per-branch rule and no-per-fragment-TOC rule as journal above.

**Compile + evict, two steps (unlike journal's drain-to-zero).** qa-log keeps a hot tier by design — old Q&A is still worth a quick skim during onboarding — so the compile target is the **hot monolith**, not the archive directly. At milestone close, `retention-drain.sh drain qa-log`:

1. Compiles `docs/qa-log.d/*.md` fragments **into the hot monolith** `docs/brainstorming-qa-log.md`, appended chronologically — **oldest-first, newest becomes the last `## ` heading**. This is the *opposite* of journal's newest-first order, and deliberately so: journal compiles into an *archive* (newest-first-at-top convention), whereas the hot monolith is a chronological-append doc (§"The drain algorithm": new entries land at the bottom, newest is the last heading) that step 3's `drain_monolith` reads that way. The same idempotent `<!-- fragment: … -->` sentinel as journal makes the compile retry-safe.
2. **Byte-verifies the monolith actually received every appended byte before deleting any fragment** — the same verify-then-delete discipline `drain_monolith` uses for its archive writes (§"The drain algorithm"). A truncated or no-op append leaves the fragments untouched and the drain exits non-zero.
3. Only then calls `drain_monolith "docs/brainstorming-qa-log.md" 50` on the now-larger monolith, which evicts entries beyond the keep-window to `docs/archive/brainstorming-qa-log-archive.md` — **decision-bearing content, archived, never deleted.** Only the transient fragments (mechanical, already compiled) are ever deleted at drain time.

### Naming (both)

`<date>-<branch-slug>.md` — date for chronological sort, branch-slug for cross-branch uniqueness. A sequential or task-based name re-creates the exact shared-tail conflict fragments exist to avoid; the branch is what's actually unique across parallel work.

### Post-merge single-writer boundary

Compile/drain (journal, qa-log, and — see `references/changelog.md` — CHANGELOG) runs **at milestone close, post-merge**: on a branch that has already merged, or as part of `/release`. It is a single-writer operation by construction — one branch, already the sole HEAD, doing the compile.

**Multiple undrained fragments coexisting across branches is the expected steady state, not a bug.** Two feature branches each writing their own `docs/journal.d/<date>-<branch-slug>.md` (or `qa-log.d`, or `changelog.d`) fragment never touch the same file, so they never conflict — that is the entire point of the fragment layout. They simply both sit undrained until each is merged and compiled at its own milestone close.

**Running compile pre-merge on a feature branch is banned.** Compiling on a feature branch writes into the shared compiled/archive file (the hot monolith, the archive, or `CHANGELOG.md`) *before* merge — which relocates the exact conflict the fragment convention exists to eliminate onto that compiled file instead. The fragment layer is conflict-free only as long as the compile step stays a post-merge, single-writer event.

### Scope

The same convention converts `qa-log` (→ hot monolith, per above) and `CHANGELOG.md` (→ `/release`, see `references/changelog.md` + `references/release-process.md`) to the fragment convention, alongside journal. All three append-doc layers are now fragment-based; no monolith in this net is still taking direct concurrent writes.

## Distill protocol

At milestone close, **after** the drain (so archive anchors exist to cite), the AI produces a distill proposal — skipped silently when `retention.distill: off`.

1. The AI scans the phase's locked decisions and just-drained content and proposes:
   - **Promotions** — candidate `CONTEXT.md` glossary entries, ADR offers, or principle lines, each citing its source archive anchor (e.g. `docs/archive/journal/2026-07.md#...`).
   - **Demotions** — hot content that is now superseded and belongs in the archive.
2. The human approves **per item** (a one-tap, multi-select list). Nothing writes without approval — there is no "approve all" default and no silent write.
3. **Supersede chain.** A promoted entry that replaces an earlier promoted entry carries `supersedes: <anchor>`; the entry it replaces gets `superseded-by: <anchor>` and moves to archive. This is what keeps the distilled tier from accumulating contradictions as knowledge is re-promoted over the project's life.
4. **Decline is legitimate.** Declining the entire proposal is a normal outcome, not a failure — it is recorded as one line in the journal fragment, and the declined anchors are written to `.claude/retention-state.json` (`declined_distill`) so the same content is never re-proposed at the next milestone close.

## Policy keys

**CLAUDE.md — the user-facing source (kebab-case):**

```yaml
retention:
  hot-caps: { RESUME.md: 200/25K, status: 300/30K, journal: 100K, qa-log: 50K, changelog: 50K }   # <doc>: none = exempt
  archive-dir: docs/archive
  distill: on          # on | off — off skips the distill step silently
```

**`.claude/close-gate.json` — the machine source (snake_case), mirrored by `/init-harness`:**

```json
"retention": {
  "hot_caps": { "resume": [200, 25], "status": [300, 30], "journal_hot": [0, 100], "qa_log_hot": [0, 50], "changelog_hot": [0, 50] },
  "archive_dir": "docs/archive",
  "coverage_floor_kb": 50,
  "journal_dir": "docs/journal.d",
  "qa_log_dir": "docs/qa-log.d",
  "changelog_dir": "changelog.d"
}
```

Manifest cap values are `[lines, KB]`; `0` means that dimension is unlimited. The whole block is optional — the gate script and `retention-drain.sh` fall back to these shipped defaults when it (or any key inside it) is absent. `hot_caps.<doc>: "none"` exempts that doc, mirroring the CLAUDE.md rule.

**The kebab↔snake mapping** (`/init-harness` and `--refresh` perform it; CLAUDE.md is authoritative, the manifest is derived):

| CLAUDE.md (kebab, human) | Manifest (snake, machine) |
|---|---|
| `hot-caps: { RESUME.md: 200/25K }` | `hot_caps: { "resume": [200, 25] }` |
| `hot-caps: { status: 300/30K }` | `hot_caps: { "status": [300, 30] }` |
| `hot-caps: { journal: 100K }` | `hot_caps: { "journal_hot": [0, 100] }` |
| `hot-caps: { qa-log: 50K }` | `hot_caps: { "qa_log_hot": [0, 50] }` |
| `hot-caps: { changelog: 50K }` | `hot_caps: { "changelog_hot": [0, 50] }` |
| `archive-dir: docs/archive` | `archive_dir: "docs/archive"` |
| `distill: on \| off` | *(no manifest mirror — consumed by the model at the milestone-done distill step, not by scripts)* |
| *(no CLAUDE.md key — infra defaults)* | `coverage_floor_kb: 50`, `journal_dir: "docs/journal.d"`, `qa_log_dir: "docs/qa-log.d"`, `changelog_dir: "changelog.d"` |

Defaults apply whenever a key is absent at either layer; nothing here is required to be set explicitly.

**Contingency — archive-dir outside `docs/`.** If `retention.archive-dir` resolves to a path outside `docs/`, that is treated as a config error: the gate and the drain script both emit a warn row and fall back to `docs/archive/` rather than writing archives somewhere unexpected.

## State file — `.claude/retention-state.json`

```json
{
  "over_cap_at_last_close": ["docs/RESUME.md"],
  "declined_distill": [{ "anchor": "<archive-anchor>", "declined": "YYYY-MM-DD" }]
}
```

Committed to the repo — it must survive across sessions to do its job. `over_cap_at_last_close` is written by the gate at every close and powers the AC3 consecutive-close escalation above. `declined_distill` is written by the distill step and powers the no-nagging guarantee in §"Distill protocol": an anchor once declined is never proposed again.

## Anti-patterns

- **LLM-rewriting or summarizing legacy content during a drain** — banned outright. Legacy tails move whole, verbatim, script-chunked. If the content needs interpretation, that is a distill proposal on the *new* fragment convention going forward, never a rewrite of what already happened.
- **Deleting decision-bearing content** — journal entries, qa-log, ADRs, and specs are archived, never deleted. Only mechanical, regenerable, or already-compiled artifacts are deleted at drain time.
- **Rewriting the source before the archive write is verified** — the drain byte-verifies the archive append (size delta + sentinel grep) before touching the source; a truncation that isn't provably mirrored in the archive is silent data loss, not a drain.
- **Exempt lists instead of `<doc>: none`** — an exempt list is exactly the coverage gap this reference exists to close. The only legitimate exemption is naming the doc explicitly with `none`.
- **Calendar-triggered maintenance** — there is no scheduled/periodic drain job. Every transition rides an existing lifecycle event (phase-done's warn rows, milestone-done's drain step).
- **Hard-failing the gate on a retention row** — every row in this reference is warn-only in v1. Escalating wording is as far as v1 goes; a hard-fail row is deliberately out of scope: escalating wording is the strongest response here.
- **Per-fragment TOCs** — fragments are short-lived hot files; adding TOC maintenance to something that drains to zero every milestone close is pure overhead. The TOC obligation lives on the compiled archive file instead.

## The count axis

The caps above measure **size**. Measured on a long-running project that adopted this skill, size-only was structurally blind:

| | |
|---|---|
| `docs/**/*.md` | **610** |
| Files above the 50K coverage floor (i.e. visible to any gate) | **14** |
| **Invisible to every gate** | **596** |

`docs/pr-drafts/` — **143 files, 1.1 MB** — sat entirely below every threshold. To the coverage net, the directory did not exist. It could grow forever.

**A per-file size cap cannot see a per-track file-count leak.** The count caps (`retention.count_caps`, checked by `close-gate.sh`) are the missing axis: warn-only at `task`/`phase`, **blocking at `milestone`** (see `close-gate.md` §"Milestone mode").

**Working documents are archived, not deleted** — `retention-drain.sh archive-working <path>` moves a closed track's spec/plan to `<archive_dir>/working/…`. They leave the hot read/grep path and stop counting against caps — **specs, plans, AND `docs_total`**: `close-gate.sh`'s `count_md` excludes `retention.archive_dir` from every count row it computes, the same way the coverage-discovery row four lines above already excludes it, so archiving is a reachable escape from an over-cap close, not a no-op. They remain on disk, searchable, and are the natural content of a project wiki. Deletion stays deferred until distill quality is proven over 2–3 tracks.
