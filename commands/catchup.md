---
description: Render a warm "welcome back" card on return to a repo (post-/clear) — where you are, what shipped, what you were doing, and whether your save is fresh — synthesized from live git + RESUME.md + PLC's session digest (+ STATUS.md if present). AI-rendered normal reply, read-only, omits rows it has no data for. Complements /recall (mechanical digest) and /handoff (writes the anchor).
---

# /catchup — unified welcome-back card

Gather the raw facts (deterministic, read-only), then render a card:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/session_card.py"
```

(When running from a checkout of this repository rather than the installed plugin, the script is `scripts/session_card.py`.) The script prints a
raw-facts blob ending in a `SOURCES:` map. Render a compact card as your NORMAL
reply — never a hook/additionalContext payload. **Omit any row whose source is
absent** (that is the whole behavior — a bare repo renders ~2 lines, not an empty
table). Render in the user's language; default English.

Card shape — render each row as a **plain labeled markdown line** (a bold
label, then its content after a `·`), NOT a table. Small two-column tables
render as heavy bordered boxes that read worse than plain text for one-line
values. One line per row, in this order; omit any whose source is absent:

> Welcome back 👋 <one sentence: last thing done + overall posture>

- **Where** — branch + WIP (WIP only if STATUS present)
- **CI** — the CI state on record for `origin/main`, only if the facts blob
  carries a `CI:` block; see "CI state on record" below. Its own line, directly
  after **Where**, because "is the branch I am about to build on broken?" is a
  where-am-I question, not a what-shipped one.
- **Recently shipped** — recent merges, rephrased
- **Last doing** — digest tasks/files (only if a digest exists)
- **🗺 Roadmap** — the fisheye block, only if the `roadmap` source is present;
  see "Roadmap fisheye" below. This is the ONE part that is NOT a plain line:
  it renders as the fenced breadcrumb / done / doing block, the drift line,
  then the Future and Backlog **tables** described there.
- **Don't forget** — gotchas from RESUME checkpoint
- **Save-state** — see below

The `Could pick up` pool is folded into the Roadmap block's Backlog table when
the `roadmap` source is present — do not also render a separate `Could pick up`
line. Fall back to a `Could pick up` line drawn from STATUS locked-next only
when there is no ROADMAP.md.

## CI state on record

PLC **reads a file and nothing else**: `.claude/ci-status.json`, written by
whatever the adopter already has. The card never queries a forge, never runs an
adopter-supplied command, and never fetches the `url` it may print. So every
sentence below is about A RECORD SOMEBODY LEFT, never about a live system —
phrase them that way, and the card cannot claim more than it knows.

Five situations, and they are five because collapsing any two of them is how
this row would grow the defect it exists to remove. Each is marked with its
machine key; the set is checked against `session_card.py`'s `CI_ROW_STATES` in
both directions, so neither this file nor the code can add a sixth alone.

- `ci-state=absent` — no `CI:` block in the blob. **Omit the row entirely**, the
  same contract every other row follows. If you ever have cause to mention the
  absence at all — the human asks, or the welcome sentence would otherwise imply
  something — the only permitted phrasing is **"no CI state on record"**. Never
  "no CI here", never "CI is fine". One absent file is not evidence that a repo
  has no CI; it is evidence that nothing wrote the file. Over-warning is
  self-correcting, a reassuring falsehood is not, and the reassuring direction is
  the one this row was built after.
- `ci-state=unreadable` — the blob's `CI:` line says the file exists but could
  not be read. Render ONE honest line saying exactly that, and do not silently
  omit it as if absent. This is the same rule the card already follows for an
  unparseable `ROADMAP.md` and for an unreadable roadmap row; a silently-dropped
  unreadable file would be its third instance on this surface.
- `ci-state=unknown` — the record says `unknown`. **Render it.** The producer
  looked and could not tell — which is a different thing from nobody having
  looked, and an omitted row already means the latter.
- `ci-state=stale` — the blob says `freshness: stale`. Report **the mismatch**,
  not the recorded state as an answer. Name what was compared: the record
  describes `recorded-sha`, you are standing on `reference-sha`. A green recorded
  against a superseded commit must never read like a green about the commit in
  front of the reader — that IS the defect this row closes, and rendering it
  loosely relocates the defect rather than fixing it. When `reference-sha` is
  `(unobtainable)`, say the reference could not be read rather than implying a
  superseded commit exists.
- `ci-state=fresh` — state, how long ago it was observed, and the producer's
  `detail` **verbatim** when present. Quote `detail`; never paraphrase it and
  never interpret it. PLC has no vocabulary for what a forge means and is not
  pretending to: if the producer wrote "the run was cancelled because a newer
  run superseded it", print that sentence. If the forge rewords it
  tomorrow, print the new one and still be correct.
  **One thing is done to that text and it is structural, not editorial:** line
  breaks and control characters arrive escaped (`\n`), because the blob is
  line-oriented and a producer whose `detail` contained a newline could otherwise
  emit what looks like a top-level blob fact — a forged `SAVE-STATE:` or a second
  `CI:` row, which is this row's own defect
  class pointed at the row. **So: `detail` is producer text, not a PLC fact.**
  Attribute it — "the producer recorded: …" — and never restate something from
  inside `detail` as if the card had established it.

Two limits to keep out of the wording, both accepted rather than fixed:
`origin/main` is a LOCAL ref that may itself be behind, so `fresh` means "matches
the local reference", never "matches the forge". And this row is not an alert —
the card renders when a human comes back after a `/clear`, so it shortens no
outage. It exists to stop the card implying everything is fine.

Voice rules:
1. PR subjects → "what changed for you" — drop `feat:`/`fix:` prefix, filenames,
   SHAs. Collapse a run of sibling PRs into ONE line.
2. Doc/ledger PRs do NOT go in "Recently shipped" — they explain why save-state
   looks behind, so mention them only in Save-state.
3. Save-state leads with the action, then evidence:
   - `SAVE-STATE: fresh` → "save is current".
   - `doc-behind` → "basically current — glance at git".
   - `code-behind` → "⚠️ N code PRs merged since your last checkpoint — run
     `/reconcile` to land them in STATUS/ROADMAP before starting; then /handoff
     to refresh the anchor".
   - `unknown` → "no checkpoint yet — clean start".
4. "Last doing" is mechanical (from the digest); for the curated next-step +
   what-NOT-to-retry, point at RESUME.md / `/recall <date>` for a specific recall.
5. Gotchas: "don't re-hit" + consequence, no mechanism. Human-relevant only —
   never surface AI-facing memos (process reminders, mechanism notes); those
   stay in RESUME.md for the next session, not on this card.
6. Never print jargon (`WIP=0`, `sources_present`) — say "nothing in flight".
7. Drift (see "Roadmap fisheye" below) is silent only when recent work
   aligns on BOTH the phase-deviation and vision-level-plumbing-drift
   tracks — an absent `⚠` line is still the expected common case, not a gap
   to apologize for; and a fired line is not an error either, just a
   flagged pattern worth a glance.

## Roadmap fisheye

Only applies when the facts blob's `SOURCES:` map has `roadmap: True` (a
`ROADMAP:` block is present). **If `roadmap` is absent, omit the whole 🗺
Roadmap row AND the drift line below — render the rest of the card exactly as
if this section didn't exist**, the same per-source degrade every other row
already follows.

**Present-but-unparseable is NOT absent.** When `SOURCES:` shows
`roadmap: False` but `roadmap_unparseable: True` (the facts blob then also
carries a `ROADMAP: (present but unrecognized layout …)` line), a
`docs/ROADMAP.md` exists that the parser could not read — do NOT silently omit
as if the file were missing. Render a single honest line instead of the
fisheye block: **🗺 Roadmap — a `ROADMAP.md` exists but its layout wasn't
recognized (glance at the file).** This keeps "no map" and "map I couldn't
read" distinct — the failure this guards against.

**A row the parser could not read is reported, never dropped in silence.** When
the facts blob carries an `unreadable-rows: N` line, render it — one short line
under the Roadmap block, e.g. **⚠ N row(s) in `ROADMAP.md` could not be read —
check for an unescaped `|` in a cell.** The blob prints the line only when `N`
is non-zero, so its absence means zero and nothing is rendered; do NOT invent a
"0 unreadable" line. This is the row-level twin of the file-level rule above:
a card that is quietly short is worse than one that says what it missed, and the
count is what makes the shortfall visible at all.

When present, render it as a **fisheye**: the whole arc stays visible, but
only the item nearest the reader's current position gets expanded. Distance
from focus decides how much detail survives — the further an item is from
"where we are now," the less it says.

1. **Breadcrumb** — two lines. First, pin the `vision` alone on its own
   line — always rendered, never folded into the breadcrumb chain below it.
   Second, a breadcrumb line led by a short "you are here" wayfinding label
   (rendered in the user's language), followed by the `current` phase and
   the focal name from `doing`: `<you-are-here label> ▸ current-phase ▸
   focal-item`. If `doing` is empty or absent, drop the focal-item segment
   entirely — the breadcrumb becomes `<you-are-here label> ▸ current`; the
   label plus `current` still anchor "where we are," so do not invent a
   focal item to fill the slot.
2. **Done** — collapse every completed phase to ONE line: name them and give
   a count (the facts blob's `done: N items`). Do not enumerate each one.
   The blob carries **two** finished-work sources and they are at **different
   granularities — never add them together**. `done: N items` is
   theme/batch-level: one entry can swallow a dozen stations. `mainline-done
   (N):` is station-level, one line per finished row of the mainline table. A
   station named in `mainline-done` is very often *inside* one of the `done`
   themes, so `done + mainline-done` would be a number describing nothing. Report the
   station-level count, and reach for the theme-level one only when naming the
   arcs. (They never render in "Future"; a finished station is not work
   ahead.)
3. **Doing** — the focal item, expanded: its name, a one-line "what," and the
   single next step. Mark it with exactly ONE asymmetric focus glyph (`▶`)
   in the left column — the glyph alone signals "you are here"; do not
   append a "you are here" text tag to the focal row (that wording lives at
   the breadcrumb head per rule 1, never as a row suffix). Never more than
   one focus glyph in the whole block, and never on any other line. `doing`
   is a list and can hold 0, 1, or 2+ items: if it holds more than one,
   treat only the first as the focal item (expanded, carrying the single
   focus glyph) and name any remaining items on ONE collapsed line — no
   focus glyph on that line, though each item may still carry its own
   left-column status glyph (see the glyph rules below; the "exactly one"
   invariant is about the focus glyph only, not status glyphs) — the same
   treatment "Future" gives `mainline` items: a collapsed remaining `doing`
   item takes the `○` status glyph, never `▶` (which is reserved for the
   single focal row) — which is what keeps the focus-glyph count at exactly
   one across the whole block. If `doing` is empty or absent, there is no
   focal item: skip this expanded line altogether (the breadcrumb already
   dropped its segment per rule 1, and the `current` line from "Where"
   still anchors the reader) — do not invent one.
4. **Future** — render the `mainline` rows as a compact table (or a tightly
   aligned list if a table would run wide): one row per station, each showing
   its name, "what," weight, and eta — the same four columns the source
   `ROADMAP.md` mainline table carries, read from the facts blob's per-row
   `mainline (N):` lines. **`N` can be 0, and that is a state to report, not a
   band to drop.** Say so in one line — *no station is queued ahead of you; the
   next thing comes from the backlog below* — the same treatment rules 1 and 3
   give an empty `doing`. Do not render an empty table, and do not omit the band
   in silence: the Future band can be empty for
   a good reason (finished stations never appear in it), so a reader who sees
   nothing cannot otherwise tell "nothing is queued" from "the card failed to
   read your roadmap." The count is printed even at 0 for exactly that reason.
   An empty Future band with a non-empty `current` is also the strongest cue
   that the current-phase prose is the thing that needs updating — pair it with
   the out-of-step line if that fired. **Calibrated override of the pure-fisheye distance rule**
   (a plain fisheye would collapse "Future" to name-only, the way "Done" and
   "Backlog" collapse) — this is a deliberate exception, not a contradiction
   left unresolved: "the card looks busy" is deliberately NOT solved
   with minimalism — the Future band keeps
   a table with what/weight/eta instead of stripping to bare names. Only the
   Future band gets this override; the rest of the fisheye rules (breadcrumb,
   collapsed-done, single-focus-glyph doing) are unaffected.
5. **Backlog** — render as a table using the SAME header as the Future table
   (name / what / weight / eta) so the two read as one consistent shape. Each
   backlog item carries a name + its description and, when the source
   `ROADMAP.md` backlog is itself a table, a real weight and eta — read all
   four columns straight from the facts blob's per-row `backlog:` lines, the
   same way Future reads its `mainline (N):` lines. This backlog table is also
   what "Could pick up" draws from now. If an adopter's backlog is a bare
   `·` list instead of a table, the fact-gatherer falls back to name-only
   rows — in that case the weight/eta cells are simply blank for those rows.

6. **Out-of-step line** (conditional, one line, only when the blob carries
   `current-conflicts:`) — the `current` prose names a station the mainline
   table already marks finished. Render it as an **observation, not a
   verdict**: "`current` still names X, and X is already finished — worth a
   look." Never "these two contradict each other." The check cannot know *why*
   a name appears in the prose, so a deliberate backward reference ("the way we
   did the auth rewrite") trips it legitimately; a false alarm is affordable only
   while what is reported is something to glance at.

7. **Skipped-rows note** (only when the blob's `crossread-skipped:` is
   non-zero) — say that N finished rows did not take part in the check above
   because of the shape of their names. The blob prints this line **always**,
   0 included, and 0 is the common case; a non-zero value means the check is
   quietly doing less than it appears to, which is the reader's to know. Do not
   render a "0 skipped" line on the card — surface it only when it is not 0,
   but never treat its absence from the card as the number being unavailable.

Glyph rules: a status glyph sits in a fixed left column so the eye can scan
it as one line per entry — e.g. `✓` done · `▶` doing (the focal row only)
· `○` future, with `◐` and `⚠` available for partial/blocked if the data
supports it. These left-column status glyphs are distinct from the single
focus glyph in rule 3: every line (done, doing, future alike) may carry its
own status glyph, and doing so is unaffected by the "exactly one focus
marker" invariant — that invariant is about `▶`-as-focus-marker only; per
rule 3, a collapsed non-focal `doing` row takes the `○` status glyph, not
`▶`, so `▶` never appears more than once in the block. Keep the glyph set
monochrome-safe (no meaning carried by color alone). A progress fraction
(e.g. a `done/total` stations count) may lead the collapsed-done line at
the phase/arc level — never a per-leaf bar, and never a block/ASCII
progress bar at any level: calibration against a real terminal render
found a bar reads as clutter and misaligns in-terminal, so the bare
fraction is the chosen form. The exact glyph vocabulary, column widths, and
line budget beyond this are intentionally left uncalibrated here; verify
them against a real terminal render before treating any specific ASCII
layout as final.

**Drift line** (conditional): run two independent checks against `RECENT
MERGES` and the digest's tasks. Emit exactly ONE `⚠` line if EITHER check
fires (if both fire at once, still emit only one line — pick whichever
pattern is more evident from the recent merges rather than stacking both).

- **Track A — phase deviation**: compare recent work against `current`. If
  it pulls in a different kind of work than the current phase describes — a
  different direction, not just a different file — surface it as: recent
  work is off the current phase — intentional, or time to refocus?
- **Track B — vision-level plumbing drift**: look at whether a RUN of the
  most recent merges are all tooling / DX / plumbing / wrap-up work that
  does not touch the `vision`'s core — even when each one individually
  still fits the current phase. This is the "last N were all X, not the
  core Y" pattern. Surface it as: the recent run has all been
  <tooling/DX/plumbing>, none of it the core <vision> — intentional
  groundwork, or time to get back to the main line?

Stay silent only when recent work is aligned with BOTH the current phase AND
is making progress toward (or at least is not a sustained detour from) the
vision. Compute both checks fresh on every render; never store the result
anywhere.

Read-only: do NOT start work or edit files. Wait for the user to pick something up.
