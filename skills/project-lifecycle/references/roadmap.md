# ROADMAP — the project's whole-plan map

The single document that answers "what is the entire plan, and where am I in it?" at a glance. Its job is to survive long projects: by milestone 9 the human (and the AI) has forgotten the shape of the whole thing — ROADMAP is the cure.

`RESUME.md` answers *"what do I do next?"* (narrow, current-phase). ROADMAP answers *"what is the whole journey?"* (wide, all milestones). They are complementary; do not merge them.

## When it is created

- **At project kickoff**, by `/init-harness` (seeded stub) OR at the end of the first milestone's brainstorm once the milestone breakdown is known.
- If a project predates this convention, create it the next time the milestone list is discussed.

## When it is updated

ROADMAP is **append-and-amend**, updated at three moments:

1. **Milestone boundary** (in the same commit as the handoff + RESUME update): flip the just-finished milestone's status to ✅, set the next one to ▶ (current). If the project's read-first status doc carries closing paragraphs, rotate the ring in the same edit (§"Close protocol — the status-file ring").
2. **Scope change**: when milestones are added, split, merged, reordered, or dropped — amend the table and add a dated one-line note under "Plan changes" explaining why (this is the drift signal; never silently rewrite history).
3. **Milestone-done gate**: the gate checks that ROADMAP reflects reality before closing.

## Canonical location

`docs/ROADMAP.md` (MD is the source of truth). An optional `docs/ROADMAP.html` companion may be generated under the normal `html-policy` opt-in (it is one of the HTML-companion-eligible artifacts — same ask-once rule as the spec/design and milestone-summary nodes).

## Required structure

```markdown
# Roadmap — <project>

## Index
- [The one-sentence goal](#...)
- [The shape of the work](#...)
- [Milestones](#...)
- [How a milestone runs](#...)
- [What "done" looks like](#...)
- [Plan changes](#...)

## The one-sentence goal
<what this project is, in one sentence — the thing you'd forget by milestone 9>

## The shape of the work
<2-4 "blocks" that group the milestones into phases of intent, in order.
e.g. "build the substrate → plug tools in → synthesize". State the load-bearing
invariant the whole plan rests on, if there is one.>

## Milestones
| # | Milestone | What gets built | Depends on | Status |
|---|---|---|---|---|
| M1 | ... | ... | — | ✅ done |
| M2 | ... | ... | M1 | ▶ current |
| M3 | ... | ... | M2 | ☐ planned |
<status legend: ✅ done · ▶ current · ☐ planned · ⏸ paused · ✗ dropped>

## How a milestone runs (the repeating loop)
<the per-phase cadence, so a reader knows the rhythm — usually a fixed block,
copy the project-lifecycle loop: brainstorm → user-story → spec → plan →
build → smoke → handoff → PR → /clear>

## What "done" looks like
<the end-state acceptance: what exists + what's true when the whole project ships>

## Plan changes
<dated, append-only log of scope changes. "2026-06-10 — split M5 into M5a/M5b
because the deep-dive was too big for one phase." Drift is signal; record it.>
```

## Status legend (use exactly these)

| Glyph | Meaning |
|---|---|
| ✅ | done (merged) |
| ▶ | current (in progress) |
| ☐ | planned (not started) |
| ⏸ | paused (blocked / deferred, with reason in Plan changes) |
| ✗ | dropped (with reason in Plan changes) |

## Relationship to other docs

| Doc | Scope | Question it answers |
|---|---|---|
| **ROADMAP.md** | whole project | "What is the entire plan + where am I?" |
| **RESUME.md** | current phase | "What is the very next action?" |
| **decisions.md** (if used) | cross-cutting | "What did we lock and why?" |
| **iteration-journal.md** | per-task history | "What happened, in order?" |

ROADMAP links into RESUME ("current milestone detail → see RESUME") and RESUME links back up ("full plan → see ROADMAP").

## Close protocol — the status-file ring

Applies to the project's **read-first status doc** (RESUME.md in this skill's default layout; STATUS.md in some projects) — NOT to the ROADMAP milestone table, which stays one line per milestone forever.

> The ring is the SPECIAL CASE (for the read-first status doc) of the generalized milestone-close archival drain in `references/retention.md` §"The drain algorithm" — same window (active + 2 closed), same verbatim-move + pointer-stub rules, applied there to every known append-only doc.

The structural bug this fixes: an append-forever close protocol grows the read-first file until a single Read can't load it (observed on a real project: 634 lines / 76k+ tokens — "read first every session" physically degraded). Closing paragraphs are write-once-read-rarely; the active section is read every session. Separate them.

**The ring (capacity 2).** The status file's active section ("Now" / current phase) holds the active entry + the **2 most recent closed entries** only. At every milestone/track close, in ONE edit:

1. Write the new closed paragraph into the active section.
2. Move the oldest closed paragraph **verbatim** to a dedicated archive file (e.g. `docs/archive/status-closed.md`), newest-first — append at the top of its section.
3. Keep a one-line pointer at the bottom of the active section ("all earlier closed entries: → archive, verbatim, newest-first").

O(1) per close, rides the existing close step — no new gate, no periodic chore.

**Rules that came out of the first live run:**

- **Destination is a dedicated archive file — never RESUME-as-verbose-history or any other living doc with its own job.** Stuffing closed paragraphs into a doc that has a different responsibility is the same disease in a different organ. (And this protocol never merges the ROADMAP map anywhere — the milestone TABLE stays; see the anti-pattern below.)
- **Verbatim means verbatim.** Zero edits at move time — every archived segment is byte-identical to its original (git history is the second copy; a byte-count balance check proves nothing was dropped).
- **Retroactive amendments (strikethrough, corrections) happen in the archive file, never back in the status file.** One direction; no pointer-chasing.
- **Sidecar / doc-only entries don't occupy ring slots** (see `parallel-work.md`) — only code-track closes rotate the ring.
- **Deliberately ungated.** No close-gate check, no tripwire: forgetting just makes the status file fat again, which is loud and self-healing. Re-evaluate after 2-3 closes.

**Honest boundary:** the ring fixes the close protocol's append path only. Other append-forever sections (icebox / decisions-log style) keep growing on their own — that is a capture-discipline problem (entries must stay capped at a few lines, not grow into diagnoses), not something the ring solves. In practice: ring landed the structural goal (zero written-once-stays-forever in the active section) but the file still missed its single-Read token target because of exactly those sections.

## Anti-patterns

- **Merging ROADMAP into RESUME** — RESUME churns every phase and gets `/clear`-truncated; the whole-plan map must be stable and separate.
- **Letting ROADMAP go stale** — a roadmap that still says "M2 current" at milestone 9 is worse than none; the milestone-done gate exists to catch this. Update it in the same commit as the handoff.
- **Silently rewriting the milestone list on scope change** — amend the table AND log the change under "Plan changes" with a date + reason. The drift is the most valuable signal.
- **Over-detailing future milestones** — far-out milestones get one line; detail accrues as they approach. ROADMAP is a map, not a spec.
- **Per-task entries** — that's the journal's job. ROADMAP is milestone-granularity only.
- **Two sessions writing ROADMAP (or the project's status file) concurrently** — exactly one session holds the pen (single-writer rule, `parallel-work.md`); sidecar findings enter through the pen-holding session.
- **Closing paragraphs appended to the status file forever** — the append-forever close protocol is the structural bug that degrades "read first every session"; rotate the ring instead (§"Close protocol — the status-file ring"). Equally wrong in the other direction: editing or summarizing paragraphs while archiving them — the move is verbatim or it didn't happen.
