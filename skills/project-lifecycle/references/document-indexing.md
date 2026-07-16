# Document Indexing

Long-lived project documents grow. By milestone 1.x the iteration journal might be 2,000 lines; the brainstorm Q&A log might span 6 phases. Scrolling is slow. Search works but only if you know the term.

The fix: **every long-lived document carries a TOC index at the top with anchor links to each section**. Both AI and human readers can jump in 1-2 clicks instead of paging through thousands of lines.

## Rule

A document needs an index when ANY of these holds:

- It is append-only across phases (journal, qa-log, RESUME progress sections, smoke-findings, mid-phase-questions).
- It currently exceeds 300 lines.
- It is projected to grow past 300 lines (a single phase's qa-log can pass 150 lines).

Short specs, handoff docs, and design docs for a single phase do NOT need an index. The 300-line / append-only test catches the right files.

## The 5 mandatory files (default set; a project may add more)

1. `docs/brainstorming-qa-log.md` — append-only across all phases. When the project uses qa-log fragments (`docs/qa-log.d/`, per `references/retention.md` §"Fragment convention"), the TOC obligation moves to the compiled hot monolith `docs/brainstorming-qa-log.md` (qa-log compiles into the hot monolith at milestone close, unlike journal's drain-to-zero); fragments themselves carry no TOC (short-lived hot files)
2. `docs/iteration-journal.md` — append-only per-task. When the project uses journal fragments (`docs/journal.d/`, per `references/retention.md` §"Fragment convention"), the TOC obligation moves to the compiled archive file `docs/archive/journal/YYYY-MM.md`; fragments themselves carry no TOC (short-lived hot files)
3. `docs/RESUME.md` — append-only per-milestone progress log
4. `docs/research/YYYY-MM-DD-mx.y-smoke-findings.md` per phase — short, but findings list grows
5. `docs/research/YYYY-MM-DD-mx.y-mid-phase-questions.md` per phase — Q's accumulate during execution

Any other long-lived file (>300 lines, append-only) gets the same treatment.

## Index format

The index lives at the very top of the file, immediately after the H1 title and any short intro paragraph. Format:

```markdown
# <Document title>

<optional 1-2 sentence intro>

## 📑 Index

- [M1.1 — <phase name>](#m11--phase-name--YYYY-MM-DD)
- [M1.2 — <phase name>](#m12--phase-name--YYYY-MM-DD)
  - [Q1: <sub-decision label>](#q1-sub-decision-label--YYYY-MM-DD)
  - [Q2: <sub-decision label>](#q2-sub-decision-label--YYYY-MM-DD)
- [M1.3 — <phase name>](#m13--phase-name--YYYY-MM-DD)
  ...

---

## M1.1 — <phase name> — YYYY-MM-DD
...

## M1.2 — <phase name> — YYYY-MM-DD
...
```

**Rules:**

- Use H2 (`##`) for top-level sections (phases, milestones, dates).
- Use H3 (`###`) for sub-sections (per-question entries inside a phase).
- Anchor links use GitHub's auto-anchor convention: lowercase, spaces → hyphens, punctuation stripped, non-ASCII characters kept verbatim (CJK, accented letters, etc.).
- One indent level under each H2 entry for H3 sub-sections (the per-Q items).
- Section dates `(YYYY-MM-DD)` in the heading are part of the anchor — keep them so anchors stay unique even if the title repeats.

## Maintenance

**When adding a new section:**
1. Add the H2 (or H3) heading at the bottom of the file (chronological append).
2. Add a matching line in the index, in chronological order (top to bottom of file = top to bottom of index).
3. Confirm the anchor link resolves (the H2 text → anchor convention is deterministic; verify by clicking once after commit).

**When renaming a section:**
1. Update the H2 text.
2. Update the matching index entry (the anchor will change — GitHub re-derives it from the new heading text).
3. Search the rest of the codebase + docs for incoming links to the old anchor and update them.

**When the index itself grows past 50 lines:**
1. Add a "Latest entries" mini-section at the top of the index showing the last 3-5 entries.
2. Keep the full index below as the source of truth.
3. Consider archiving entries older than 3 milestones into a separate `docs/<file>-archive.md` with its own index. Cross-link from the live file. The generalized mechanic for ALL append-only docs (drain window, roll-over, pointer stubs) is `references/retention.md` §"The drain algorithm".

## When to use H3 sub-anchors

H3 sub-anchors are valuable when a single section grows long enough that scrolling within it is also slow. Typical triggers:

- A phase has ≥5 brainstorm Q&A entries — link each Q in the index.
- A milestone in RESUME has ≥10 tasks/sub-progress entries — link the major ones.
- A smoke-findings file has ≥5 distinct findings — link by finding ID.

Otherwise, H2 anchors alone are enough.

## Why this matters

- **Context window economy** — agent reading `iteration-journal.md` doesn't need to scan thousands of lines to find a specific phase entry — jump via anchor.
- **Human review speed** — when reviewing a long-running PR, the reviewer needs to find the brainstorm Q where Decision X was locked. Index says: line N.
- **Resume safety** — after `/clear`, the next session reads RESUME.md and needs to jump to the current phase's progress. Index makes this 1 jump instead of a Cmd+F.

## Anti-patterns

- **Index appended at the bottom** — readers won't see it; defeats the purpose. Always top.
- **Index drifts from sections** — adding a section without updating the index. Set a per-task check: "did I touch a long-lived doc? Did I update its index?"
- **Anchor-link guesses** — write the link, click it once locally before commit. GitHub's anchor algorithm is deterministic but easy to mis-predict (e.g. forgot to strip parentheses).
- **Indexing short specs** — a 50-line design doc with a TOC is overhead with no benefit. Apply the 300-line / append-only test.

## Migration: adding an index to an existing long file

1. Open the file. Skim the H2 headings.
2. Build the index block at the top: copy each H2's text, derive its anchor (lowercase / hyphens / non-ASCII kept).
3. Add H3 sub-links where the section is long (per the H3 trigger above).
4. Commit with message: `docs: add TOC index to <file>.md for fast section nav`.
5. From this point forward, treat the index as mandatory — every append also updates the index.
