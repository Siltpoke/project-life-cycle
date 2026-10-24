# Which file do I open?

**One row per document this skill tells you to keep.** Read this table and nothing else, and you
should be able to answer *"which file do I open right now"* without opening any of them.

That is the acceptance bar for this page, and it is why the page exists: the person who wrote
this format could not tell the documents apart —

> the progress markdown is confusing, there are several — STATUS, ROADMAP, RESUME and so on —
> and what the relationship between them is, that is unclear

**Two rows below name a file that does not exist in this repository.** That is written into the
table rather than hidden, because "the skill points at it and it is not there" is precisely the
confusion this page is for.

---

## The table

| document | who writes it | who reads it first | when | truth or view | most confused with — and the difference |
|---|---|---|---|---|---|
| **`RESUME.md`** | `/handoff` — never by hand mid-phase | the next session, **first thing** | resuming after a break or a `/clear` | **truth** — the only record of state git cannot recover | **`docs/STATUS.md`** · see the ruling below. Also `docs/journal.d/` — RESUME is the CURRENT moment, the journal is what already happened |
| **`docs/ROADMAP.md`** | a human; `/reconcile` proposes edits | anyone asking *where is this going* | starting a milestone, or `/catchup` | **truth for the plan, VIEW for progress** — a station's position is derived and never written | **`docs/BACKLOG.md`** · the roadmap is the mainline being walked, the backlog is everything filed and not scheduled. The roadmap's 🗂 table is a stale copy of the backlog and only ever gains rows |
| **`docs/BACKLOG.md`** | a human; the id comes from `scripts/backlog-toc.sh`, **never from eyeballing the maximum** | anyone choosing what to do next | picking up work | **truth** — closure STATE is derived from `.claude/backlog-closures.tsv`, not from the heading | **`docs/ROADMAP.md`** · see above |
| **`docs/journal.d/<date>-phase-*.md`** | the phase, one FACT per task | a reader asking *why is it like this* | before repeating a decision | **truth** — append-only | **`docs/qa-log.d/`** · the journal records what was LEARNED; the Q&A log records what was DECIDED and by whom |
| **`docs/qa-log.d/<date>-*.md`** | the phase, once, at brainstorm | a reader auditing a decision | when a choice needs its provenance | **truth** | **`docs/journal.d/`** · see above |
| **`CHANGELOG.md`** | every PR that changes user-visible behaviour | an adopter upgrading | before upgrading, and at release | **truth** for the release story | **`docs/journal.d/`** · the CHANGELOG is what changed FOR YOU; the journal is what it cost us |
| **`docs/CONTEXT.md`** | a human, rarely | a newcomer, or anyone hitting an unfamiliar word | when a term does not parse | **truth** for vocabulary | nothing — it defines words, it holds no state |
| **`.claude/tasklist.md`** | the cadence, per phase | the author mid-phase, plus `hooks/tasklist-first.sh` (which checks that it exists, never renders it) — the `/tasklist` reader was removed | to see which step is live | **truth for the current phase only** | **`RESUME.md`** · the tasklist is THIS PHASE's steps, RESUME is the session's moment. **Gitignored** — it carries a session nonce and never leaves the machine |
| **`docs/cognition.md`** | `/cognition-distill`, regenerated from `docs/cognition-log.d/` | anyone asking *why did we want this* | before re-litigating an old intent | **VIEW** — regenerated from the cold log, never edited | **`docs/journal.d/`** · cognition is INTENT, the journal is OUTCOME. **Absent here** — see below |
| **`docs/STATUS.md`** | a human, in projects that keep one | that project's next session | the same slot as `RESUME.md` | **truth**, where it exists | **`RESUME.md`** — and this is the confusing one. See the ruling |

---

## Where each one is visible from

The table above says who writes and who reads each file. It does **not** say where the file
*exists*, and two of these are `gitignored` — so they live in the main checkout only and are
**absent from every worktree**, while every other row is tracked and visible from any checkout:

| document | tracked? | visible from |
|---|---|---|
| **`RESUME.md`** (and `RESUME-archive.md`) | no — `.gitignore` anchors `/RESUME.md` | main checkout only |
| **`.claude/tasklist.md`** | no | main checkout only |
| everything else in the table | yes | any checkout or worktree |

**Why this is a correctness surface, not a detail.** A read taken
inside a worktree can report `RESUME.md` absent, and that false absence could retire the artifact
of `/handoff` — a file that is in fact present, inside its
hot cap, with `/catchup` as its consumer. Likewise a main checkout that is one commit behind can
report backlog entries absent. **"I did not find it" is not "it does
not exist"** — resolve a gitignored project-state artifact from the canonical location rather than
assuming the current worktree, and re-read HEAD before trusting a tracked file's contents.

**Distinct from "Two rows point at files that are not here" below.** That section is about a file
this repo genuinely does not keep (`docs/STATUS.md`, absent by design; `docs/cognition.md`, absent
because its upstream is starved). This section is about a file that **does** exist and is simply
invisible from where you are standing. Collapsing the two is what produced both cases above:
*artifact existence* and *artifact visibility from the current execution environment* are not the
same question, and only the first one is answered by looking.

## `RESUME.md` vs `docs/STATUS.md` — the ambiguity, settled

**They occupy the same slot: the read-first status document. Both cannot be it.**

**Measured, rather than recalled:**

- This repository has **no** `STATUS.md` and no `docs/STATUS.md`. It reads `RESUME.md`.
- Its manifest does **not** set `status_doc`, so it runs on the shipped default —
  **`docs/STATUS.md`. The default names a file the reference implementation does not have.**
- `scripts/close-gate.sh`, this repo's own gate, **reads `status_doc`**
  — and this bullet is a correction, kept in place rather than rewritten away, because the
  sentence it replaces was true when it was measured and the ruling below still rests on it.
  **It used to read:** *"does not implement `status_doc` at all. Only the adopter-facing gate in
  `references/close-gate.md` does, which means the half that reads the key has never been
  exercised here."* The canonical hot-cap rows have since been ported into this gate, and the status-doc
  row came with them.
  **The distinction that survives, and it is not a quibble:** the gate now READS the key, and
  the row is **dormant here** — it resolves to `docs/STATUS.md`, which this repo does not have,
  so `cap_file` returns early and prints nothing. *"The key is read"* and *"the row has been
  exercised against a real status document"* are different claims, and only the first became
  true. The row is kept rather than dropped for a reason that is about behaviour, not parity:
  deleting it would mean a project that later adds a status doc gets **no cap on it silently**,
  which is the shape the port exists to end.
  **What this does NOT change:** the manifest still does not set `status_doc`, so the default
  still names a file this repo does not have — see "Left open on purpose" below, which is
  unaffected.
- Thirteen references to `STATUS.md` remain across `skills/`, `commands/` and `scripts/`.

**The ruling.** `RESUME.md` is the read-first document. `docs/STATUS.md` is what an adopter who
already keeps a status file points `status_doc` at: a **configuration**, not an alternative this
skill recommends.

**Why the earlier conclusion is not simply executed.** An earlier decision concluded *"STATUS is not a portable
variant; drop the endorsement"* and was closed without action. Taken literally today it would
**delete a real mechanism** — most of those thirteen mentions ARE the `status_doc` key, not a
recommendation. The endorsement goes; the key stays, documented as a key.

**Left open on purpose, named so it is not mistaken for an oversight:** the default should
probably become `RESUME.md`, since it is wrong for the only project running the reference
implementation. Changing a manifest default changes behaviour for every adopter who never set
the key, so that is a phase with a story rather than a line edited here.

---

## One occurrence of the old wording survives, and it is not an oversight

The sentence that created this ambiguity —

> the read-first status doc (RESUME.md by default; STATUS.md where present)

— presented `docs/STATUS.md` as a second CONVENTION rather than as a configured value. It
appeared four times and three were rewritten to point here.

**The fourth is in `references/reconcile.md`, which is byte-frozen.** Every reference file that
existed at p34's baseline defines what `detailed` mode DOES, and the byte-freeze guard
refuses any edit to one. Re-pinning that baseline is a decision belonging to the phase that owns
the freeze, not to this one, so the wording there is left alone and named here instead.

**What it would take:** a phase that re-pins the frozen set, with the reason recorded the way
that guard's own header asks for. Until then, `references/reconcile.md` carries the old sentence
and this page is the correction.

## Two rows point at files that are not here

Repeated outside the table because a skill that tells you to keep a document it does not itself
keep is the confusion this page exists to remove:

- **`docs/STATUS.md`** — absent BY DESIGN, per the ruling above.
- **`docs/cognition.md`** — absent, and **not** by design. `/capture` writes intents to a cold
  log and `/cognition-distill` regenerates this document from it; neither has run here often
  enough to produce one. That is a starved capability rather than an unwanted one. The row stays
  because the skill still points at it.

## What this page is not

- **Not a link index.** It says who owns each document, not what links to what. A cross-document
  discovery index is filed separately and deliberately not built here.
- **Not a retention policy.** Sizes, caps and archiving are in `references/retention.md`.
- **It cannot tell you whether a document is CORRECT.** It tells you who is responsible for one.
  A `RESUME.md` a phase out of date is still the read-first document; freshness is the context
  floor's job, not this table's.
