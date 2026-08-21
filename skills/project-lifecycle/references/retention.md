# Document retention — the hot/cold model

A long-running project's `docs/` tree can reach tens of megabytes across hundreds of files, with individual hot docs and single journal months each hundreds of kilobytes — while every ring/slicing/archive mechanism is already running. The failure is not absence of mechanism; it is **coverage + regrowth**: new append-only docs escape the net, and docs that are being maintained still creep back up between maintenance passes. This reference is the fix — a small set of dual-limit caps, a coverage-discovery net, and a deterministic drain that runs at the one moment nothing else is competing for attention: milestone close. Every transition below is **event-triggered off the existing lifecycle** (phase-done, milestone-done), never a calendar chore a human has to remember.

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

**Measured whole-file, deliberately.** For the status doc, "the active section" is the natural reading, but mechanically parsing section semantics to isolate it is the wrong layer here — the drain algorithm below already guarantees active + 2 closed entries ≈ the whole file, so measuring the whole file against the cap is deterministic and, once the drain is running, equivalent in practice. Deterministic beats precise.

**Escalation.** The gate persists an over-cap list to `.claude/retention-state.json` (`over_cap_at_last_close`) at every close. If the *same* doc is over-cap at two consecutive closes, the warn row's wording gains an explicit flag: `"SECOND consecutive over-cap close — this doc is not draining"`. Still warn-only — escalation is louder wording, never a failing gate, in v1.

**Override.** Project `CLAUDE.md` sets `retention.hot-caps` to raise or lower any doc's cap. `<doc>: none` is the **only** exemption mechanism — there is deliberately no exempt list. An exempt list recreates exactly the coverage gap this reference exists to close: the moment a doc is exempted by name instead of by an explicit `none`, someone forgets to add the next one.

## Coverage discovery

The known set = files referenced by `.claude/close-gate.json` manifest keys, plus everything under `docs/journal.d/**`, plus everything under `docs/qa-log.d/**`, plus everything under `changelog.d/**`, plus everything under `retention.archive-dir/**`. Any other file matching `docs/**/*.md` that exceeds the coverage floor (default 50K) and is outside that known set gets a warn row at `phase-done`:

```
⚠ coverage: docs/some-new-doc.md (62K) not in retention net — add to manifest known set or archive it
```

This is the row that answers the failure mode that matters: a brand-new append-only doc (a second qa-log, a per-feature notes file, anything) can grow to tens of megabytes unnoticed because no existing check was ever wired to watch it. Coverage discovery watches the filesystem, not a fixed list — a new doc can't opt out just by not being named anywhere.

## The drain algorithm

Runs at milestone close (cadence step 10), deterministic, no LLM involved anywhere in this step:

1. **Per known append-only monolith** (RESUME, status doc, qa-log, or any other doc tracked by the manifest): these docs append chronologically by default — per `document-indexing.md`, a new entry lands at the **bottom**, so the newest entry is the **last** `## ` heading, and the doc's own `## 📑 Index` heading is not an entry. **A document that grows the other way says so** with `retention.order` (see §"Policy keys"), and headings that are structure rather than entries — plus `[Unreleased]`, always — are protected with `retention.non_entry_headings` and never evicted from any position. **If the heading dates contradict the ordering in force, the drain refuses with exit 3 and moves nothing** rather than guessing which end is old; ambiguous or undated documents proceed silently. The drain keeps the **last active + 2 most recent closed `## ` entries** (the *first* KEEP under `newest-first`) and evicts the older entries into `<archive-dir>/<name>-archive.md`, where they are written **newest-first** (entry *order* is reversed at write time; each entry itself stays byte-verbatim). The archive append is **byte-verified before the source is rewritten** — if the archive did not demonstrably receive every byte, the source is left untouched and the drain exits non-zero. A one-line pointer stub replaces the evicted entries in the source, and each evicted entry gets a TOC line in the archive file (per `document-indexing.md`).
1b. **Index maintenance is part of the drain, on both sides.** The eviction and the index are one operation, not an eviction plus a chore someone remembers: (a) the SOURCE's `## …Index` block, when it has one, is **regenerated from the entries that survive, minus the pinned ones** — regenerated, never patched, so it is the file describing itself and cannot drift. Pins are excluded because a pin survives by definition: `[Unreleased]` and your declared `non_entry_headings` are the document's scaffolding, not its contents, and an index listing `How to read this file` beside your releases is not an index. A source with no index heading gets no index written — but it is **not** left byte-identical, and an implementer who reads it that way will skip the prefix rewrite for indexless documents and reintroduce (c) for them: the prefix rewrite runs whenever there is a prefix at all, because stub collapse is not conditional on an index. Index bullets are matched as `^[[:space:]]*- `, **nested ones included** — an anchored `^- ` ends the block at the first sub-bullet and strands the rest of the old index below the new one as body prose, pointing at the entries the drain just evicted, which is the exact failure (a) exists to prevent and the exact shape a hand-maintained index has. **Migration warning, and it only matters once:** the first drain replaces a hand-authored index — anchor links, nesting, whatever `document-indexing.md` produced — with plain-text top-level bullets. That is the design (anchor guesses are the named anti-pattern), but it is not reversible, so an adopter with a curated index should look at the first run's diff before committing it; (b) on the JOURNAL path, the archive's `## 📑 Index` is **regenerated from the archive itself** — deliberately not accumulated from whatever the current run appended, because a run interrupted between the body append and the index write would then skip the re-append on retry and never re-collect that heading, leaving a body in the archive permanently absent from its own index and unrepairable by any rerun. Regeneration covers **every** journal archive a run touches or does not, not only the months it wrote: fragments are filed by their own month, so an archive with nothing left pending would otherwise never be reachable again — though a drain with **no** fragments at all still exits early, so the repair rides on a drain that has work to do. It is scoped to the `YYYY-MM.md` files the journal drain itself creates; a hand-made or pre-convention archive is not the drain's to index, and is neither rewritten nor warned about. **Only the existing bullet block is replaced** — the run of blank and `- ` lines directly under the heading — so ordinary prose below an index survives untouched, and each archive keeps its own file permissions. The index heading is looked for **above the header's `---` separator only**; a body heading that happens to end in `Index` is a body heading. (b2) the MONOLITH archive path still *accumulates* one plain-text bullet per heading moved into it, which is safe there because its insert and its rename are one step — it has no crash gap to close, and is deliberately left alone rather than converted for symmetry. Bullets are plain text on both sides — a hand-computed anchor link is `document-indexing.md`'s named anti-pattern. And (c) **exactly one pointer stub survives per file, however many drains preceded it**: a stub written by an earlier run sits above the first entry on the oldest-first path, inside the region the rewrite emits verbatim, so it used to survive and accumulate — six identical stub lines meant six drains, not six evicted entries.

2. **Journal fragments**: compile the phase's fragments (newest-first) into `<archive-dir>/journal/YYYY-MM.md`, then **delete** the fragments — the hot directory drains to zero, towncrier-style. Pure file operations. **`YYYY-MM` is each fragment's OWN month**, read from its filename's `YYYY-MM-DD` prefix — never the month the drain happens to run in. One run therefore writes as many archive files as the fragment set spans. A fragment whose name carries no valid date falls back to the wall-clock month **and says so on stdout**; it is never silently mis-filed.
3. **Roll-over**: any archive file that exceeds **4× its source doc's cap** splits into `<archive-dir>/<name>/YYYY-MM.md` segments plus a `<archive-dir>/<name>/index.md` segment index. The date-split applies to archives whose entry headings carry dates (qa-log style); an archive whose headings carry no usable dates falls back to a deterministic **line-count chunk split** (`part-NN.md` segments, same mechanic as the legacy mover) — never an `undated.md` catch-all. Journal archives never roll: they are already month-segmented by their `YYYY-MM.md` filenames.
4. **Delete-vs-archive**: decision-bearing content (journal entries, qa-log, ADRs, specs) is archived, never deleted. Mechanical artifacts (drained journal fragments once compiled, scratch files, regenerable HTML companions) are deleted at drain time — git is their cold storage, not `docs/archive/`.

Like the status-file ring it generalizes (`roadmap.md` §"Close protocol — the status-file ring"), this drain is **deliberately ungated** in v1: no hard gate row blocks a close that skips it. The hot-doc-cap warn rows above are what make a skipped drain visible — the next close simply shows the same doc over-cap, and after two closes the wording escalates.

## Embedded portable script — `scripts/retention-drain.sh`

Same ship-pattern as `close-gate.sh`: this repo carries the spec below as the canonical, reviewable source; a project materializes its own copy under `scripts/retention-drain.sh` via `/init-harness`. Pure bash + standard POSIX-ish text tools (`awk`, `sed`, `split`, `jq` for the manifest read), no stack assumptions. Portability notes baked in: no multi-line `awk -v` values (BSD awk rejects newlines in `-v` strings — multi-line content moves through temp files and `sed <line>r <file>` insertion instead), and no `\x` hex escapes inside awk regex literals (BSD awk does not interpret them; matching silently no-ops).

This block is checked byte-for-byte against `scripts/retention-drain.sh` by `scripts/test_retention_drain.py`, so a drifted mirror fails the test suite instead of going unnoticed.

```bash
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

# ── pre-image ────────────────────────────────────────────────────────────────────
# A drain that FAILS is safe: the archive append is byte-verified before the source is
# touched. The dangerous run is the one that succeeds at the wrong thing — every check
# passes, the wrong bytes move, and where docs/ is gitignored git recovers neither file. The
# pre-image is the byte-for-byte state of every file a drain is about to mutate, captured
# before it mutates them, so `restore` can put the tree back exactly.
PID="$AD/.pre-images"          # the store: numbered slots, never timestamped (a timestamp can collide)
PIX="$AD/.pre-images.log"      # the receipt — OUTSIDE the store on purpose, see below
PIKEEP="$(g preimage_keep)"; case "$PIKEEP" in ''|*[!0-9]*) PIKEEP=5 ;; esac
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
  printf '%s\n' "$slots" | while IFS= read -r d; do
    [ "$excess" -gt 0 ] || break
    [ -n "$d" ] || continue
    [ "$d" = "$PI_PROTECT" ] && continue
    rm -rf "${PID:?}/$d"
    excess=$((excess - 1))
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
  preimage_prune
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
    awk -v segdir="$stage" '
      /^## / && $0 !~ /Index[[:space:]]*$/ {
        m = $0
        if (match(m, /[0-9][0-9][0-9][0-9]-[0-9][0-9]/)) mo = substr(m, RSTART, 7)
        out = segdir "/" mo ".md"
      }
      out != "" { print >> out }
    ' "$archive" \
      || { echo "✗ roll-over month split failed for $archive"; rm -rf "$stage"; return 1; }
  else
    # undated (or mixed) headings → deterministic LINE-COUNT chunk split, same mechanic
    # as drain_legacy — never an "undated.md" catch-all segment
    split -l 2000 "$archive" "$stage/part-" \
      || { echo "✗ roll-over chunk split failed for $archive"; rm -rf "$stage"; return 1; }
    for s in "$stage"/part-*; do
      case "$s" in *.md) : ;; *) mv "$s" "$s.md" \
        || { echo "✗ rename failed for $s"; rm -rf "$stage"; return 1; } ;; esac
    done
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
    # Same propagation as drain_qa_log's tail — one defect, two call sites.
    if [ "$rc" -eq 0 ]; then
      check_rollover "$AD/$(basename "$SUB" .md)-archive.md" "${3:-25}" || rc=$?
    fi
    exit "$rc" ;;
esac
```

## Fragment convention

### Journal

**Write path:** per-branch journal entries append to the current branch's fragment file, `docs/journal.d/<date>-<branch-slug>.md`, instead of the monthly monolith. **One fragment per branch, not per task** — if the branch's fragment already exists, append to it. Under WIP=1, branch and phase are effectively the same unit of work, so this reads as "one fragment per phase" in practice — the file is named for the branch specifically so two branches active at once (or a branch that outlives one phase) never collide on a shared filename. The entry still follows the same 6-section schema unchanged.

**No per-fragment TOC.** Fragments are short-lived hot files — they exist only until the next milestone close drains them — so they carry no TOC obligation. The compiled archive month file (`docs/archive/journal/YYYY-MM.md`) carries the TOC instead, per `document-indexing.md`.

**Compile + drain.** At milestone close (`retention-drain.sh drain journal`), each fragment compiles into the archive for **the month its own filename carries** — `docs/archive/journal/YYYY-MM.md` — newest-first within each file; then the fragments are deleted, so the hot directory drains to zero, towncrier-style, purely mechanically. No LLM step anywhere in this path. The compile is idempotent on retry: each fragment is recorded in the archive under a `<!-- fragment: … -->` sentinel, so a drain interrupted between append and delete skips already-compiled fragments instead of duplicating them. **Every append completes before any fragment is deleted** — never interleaved per fragment: on a run that fails partway through a second month, an interleaved order would leave some fragments deleted and their bytes nowhere.

> **This used to say the run's month, and the code used to mean it.** The target was a single `date +%Y-%m`, so a drain executed in August filed July's fragments under August, beneath a header claiming July — invisible for as long as a project drains inside the month it writes in, and wrong on the first day it does not. Archives written by an older version may still hold such mis-filed fragments; leave them in place, because archived bytes are never hand-edited.

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
  order: { CHANGELOG.md: newest-first }   # newest-first | oldest-first; absent key = oldest-first
  non-entry-headings: { CHANGELOG.md: [How to read this file, How to contribute an entry] }
```

**`.claude/close-gate.json` — the machine source (snake_case), mirrored by `/init-harness`:**

```json
"retention": {
  "hot_caps": { "resume": [200, 25], "status": [300, 30], "journal_hot": [0, 100], "qa_log_hot": [0, 50], "changelog_hot": [0, 50] },
  "archive_dir": "docs/archive",
  "coverage_floor_kb": 50,
  "journal_dir": "docs/journal.d",
  "qa_log_dir": "docs/qa-log.d",
  "changelog_dir": "changelog.d",
  "count_caps": { "specs": 10, "plans": 10, "docs_total": 150 },
  "order": { "CHANGELOG.md": "newest-first" },
  "non_entry_headings": { "CHANGELOG.md": ["How to read this file", "How to contribute an entry"] }
}
```

`count_caps` is in this block because it is a key the gate reads and this block is what adopters copy; it was named only in prose further down, so a copied config silently took the built-in defaults without their owner knowing the key existed. **Every key the gate or the drain reads appears here, and nothing here is unread** — that is the property this block is supposed to have, and it is worth re-checking whenever a key is added, because a documented-but-dead key and an undocumented-but-live one fail in opposite directions and both look like a working config. (`hot_caps` accepts one entry per hot doc; a key naming a doc your gate does not measure is inert, so add caps for docs, not for hopes.)

**`order` and `non_entry_headings` are keyed by the source file's basename *including* its
extension** (`CHANGELOG.md`, not `CHANGELOG`) — the drain receives a path, and keying on the path as
passed would make the declaration depend on the caller's cwd.

- `order` — `newest-first` or `oldest-first`. An absent key, an absent object, or an absent manifest
  all mean `oldest-first` — the same end the drain evicted from before the key existed. **That is not
  the same as "nothing changes when you upgrade":** an undeclared document whose heading dates
  contradict the default now refuses (exit 3) instead of draining, until you declare it. Declaring it is how a reverse-chronological document (a
  Keep-a-Changelog `CHANGELOG.md`, for instance) tells the drain that its newest entries are at the
  **top**; without the declaration the drain would archive them and keep the oldest.
- `non_entry_headings` — the exact heading **texts**, without their `## ` prefix, that are structural
  parts of the document rather than entries: a "How to read this file" preamble, a contributing note.
  They are never evicted, wherever they sit in the file. `[Unreleased]` is pinned automatically and
  needs no declaration.
- **Both keys fail closed.** An `order` value that is neither literal, a `non_entry_headings` value
  that is not an array of strings, or a heading declared with its `## ` prefix attached, is a usage
  error: the drain exits non-zero and moves zero bytes. Malformed *protection* failing open is the
  expensive direction — it would produce a silent, successful drain that archives exactly the
  heading the declaration was written to protect.

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
| `order: { CHANGELOG.md: newest-first }` | `order: { "CHANGELOG.md": "newest-first" }` |
| `non-entry-headings: { CHANGELOG.md: [How to read this file] }` | `non_entry_headings: { "CHANGELOG.md": ["How to read this file"] }` |
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

Committed to the repo — it must survive across sessions to do its job. `over_cap_at_last_close` is written by the gate at every close and powers the consecutive-close escalation above. `declined_distill` is written by the distill step and powers the no-nagging guarantee in §"Distill protocol": an anchor once declined is never proposed again.

## Anti-patterns

- **LLM-rewriting or summarizing legacy content during a drain** — banned outright. Legacy tails move whole, verbatim, script-chunked. If the content needs interpretation, that is a distill proposal on the *new* fragment convention going forward, never a rewrite of what already happened.
- **Deleting decision-bearing content** — journal entries, qa-log, ADRs, and specs are archived, never deleted. Only mechanical, regenerable, or already-compiled artifacts are deleted at drain time.
- **Rewriting the source before the archive write is verified** — the drain byte-verifies the archive append (size delta + sentinel grep) before touching the source; a truncation that isn't provably mirrored in the archive is silent data loss, not a drain.
- **Exempt lists instead of `<doc>: none`** — an exempt list is exactly the coverage gap this reference exists to close. The only legitimate exemption is naming the doc explicitly with `none`.
- **Calendar-triggered maintenance** — there is no scheduled/periodic drain job. Every transition rides an existing lifecycle event (phase-done's warn rows, milestone-done's drain step).
- **Hard-failing the gate on a retention row** — every row in this reference is warn-only in v1. Escalating wording is as far as v1 goes; a hard-fail row is deliberately out of scope.
- **Per-fragment TOCs** — fragments are short-lived hot files; adding TOC maintenance to something that drains to zero every milestone close is pure overhead. The TOC obligation lives on the compiled archive file instead.

## The count axis

The caps above measure **size**, and size-only is structurally blind to a directory of many small files.

A directory that gains one small file per track (one PR draft each, say) sits entirely below every size threshold. To the coverage net, the directory does not exist. It can grow forever.

**A per-file size cap cannot see a per-track file-count leak.** The count caps (`retention.count_caps`, checked by `close-gate.sh`) are the missing axis: warn-only at `task`/`phase`, **blocking at `milestone`** (see `close-gate.md` §"Milestone mode").

**Working documents are archived, not deleted** — `retention-drain.sh archive-working <path>` moves a closed track's spec/plan to `<archive_dir>/working/…`. They leave the hot read/grep path and stop counting against caps — **specs, plans, AND `docs_total`**: `close-gate.sh`'s `count_md` excludes `retention.archive_dir` from every count row it computes, the same way the coverage-discovery row (§"Coverage discovery") already excludes it, so archiving is a reachable escape from an over-cap close, not a no-op. They remain on disk, searchable, and are the natural content of a project wiki. Deletion stays deferred until distill quality is proven over 2–3 tracks.
