# ROADMAP station-plan format — v1

An open, versioned file format for saying **what a station plans to do, how far it has
got, and what it waits on**, inside a `ROADMAP.md` that existing parsers already read.

This is a **format contract**, not a runtime. Anything that reads `ROADMAP.md` may
implement it; nothing is required to. The golden fixtures beside this file are published
so a third party can check their own reader **without depending on this project** —
PULL, not EMIT. No consumer is asked to run our checks.

---

## The one rule everything else follows

> **Derivable ⇒ must not be written down. Not derivable ⇒ must be written down.**

A plan is *intent*: nobody can compute it, so a human writes it. A position is *history*:
it is computable from the record, so writing it creates a second copy that rots. This is
why the format has a `steps:` list and **no** `done:`, `position:` or `progress:` field —
their absence is the design, not an omission.

---

## Where the blocks go

Two new sections, both at `## ` level, both **after** the mainline table.

**Placement is a hard constraint, not a style preference.** Readers of this file
(including this project's own and at least one third-party renderer) define a section's
body as *"everything after this `## ` heading up to the next `## `"*. A `## ` block
dropped inside another section therefore **truncates that section's body** — while every
byte of every table row stays exactly where it was.

> **A block must sit immediately before an existing `## ` heading, or at end of file.**
> Never inside another section's body.

So "the table did not change" is **necessary but not sufficient** evidence that a reader
sees the same thing. Both conditions have to hold.

---

## `## 🧭` — the plan blocks

```markdown
## 🧭 Station plans

<!-- plc-station-plan v1 -->

### ci-line
- binds-to: **▶ CI line — a docs-only change should not wait 31 minutes** ([[B<n>]] · [[B<m>]])
- depends-on: none
- steps:
  - s1 measure which assertions a docs-only change can move
  - s2 narrow the trigger from everything to that set
  - s3 make the green state which tree it tested
```

| Rule | Value | Violation |
|---|---|---|
| `### <station-id>` | `^[a-z0-9][a-z0-9-]{1,31}$` | red |
| station id | unique across the file | red |
| `binds-to:` | verbatim equal to some mainline row's `name` cell | zero matches (orphan) → red |
| one row ← one block | a row may be bound by at most one block | red |
| missing id or `binds-to:` | forbidden | red |
| `depends-on:` | space-separated station ids, or literal `none` | empty → red; unknown id → red |
| dependency graph | acyclic, **transitively**, self-loops included | cycle → red |
| `steps:` | **1–7 entries**, `s<N> <text>`, `N` consecutive from 1 | zero / >7 / gap / duplicate → red |
| each step's text | ≤ 60 **display columns** (see below) | over → red |
| lines inside a block | **closed set** — see below | anything else → red |

### The line set is closed, and that is deliberate

Only these lines may appear inside a `### <station-id>` block: the three key lines
(`binds-to:`, `depends-on:`, `steps:`), the `  - sN …` step lines under `steps:`, and
blank lines. **Anything else is red, with or without a colon.**

It is stated as a closed set of **lines**, not of **keys**, because a key-shaped check
anchored on `:` does not see a bare line. A line reading just `- done` carries no colon,
so a key detector never classifies it as a key at all — and the whole point of the closed
set is that `done` cannot come back.

This is knowingly against the usual advice (OpenAPI calls `additionalProperties: false`
"the enemy of backwards compatibility"). The cost is accepted because the risk it answers
is specific and was named up front: *somebody will add a field called "status", and then
`done` slowly moves back into it*. Widening the set means editing the validator, and the
validator carries a test asserting `done` may not be declared. **To extend, bump the
`v1` in the block marker.**

### Dependency semantics

- **Cycle detection is transitive.** `a → b → c → a` is red. So is `a → a`.
- **Rendering `blocked-by:` is one hop.** The transitive closure is not expanded.

The two have deliberately different reach. One hop is what a reader can verify by eye; a
closure is a wall of text, which is the very problem this format exists to reduce.

### "60 display columns" — of what, exactly

> **The rendered line, including its `sN ` prefix, excluding the markdown `  - ` marker.**

The number exists for one reason: a step should not wrap in an 80-column terminal, and
wrapping is what makes a roadmap unreadable. What wraps is the line a renderer *prints*.
Measuring the source line would charge the budget for two spaces and a hyphen; measuring
the bare text would miss the three columns `s1 ` occupies. Neither is what happens in the
terminal.

Width is per Unicode `East_Asian_Width`: `W` and `F` count 2, everything else counts 1.
**`Ambiguous` counts 1** — including `▶` `○` `◐` `⚠`, which a CJK-locale terminal renders
two columns wide. Ambiguous width is context-dependent by definition, so any
implementation that does not read the locale must pick a side; this format picks 1 and
says so rather than leaving it to each reader.

**Both bounds — 7 steps, 60 columns — are chosen, not derived.** No evidence supports
either number. They are adjustable. What is *not* adjustable is that some decidable bound
must exist: "keep it short" is not a mechanism.

---

## `## 🚦` — the active list

```markdown
## 🚦 In flight

<!-- plc-station-active v1 -->
- ci-line
```

The **only** source of `doing`. Deliberately outside the table so a human's choice and a
row's decorative text cannot be confused for one another.

- The list may be empty (nothing in flight) but **the block must exist**. A missing block
  cannot be told apart from an unfilled one.
- It may name **only stations that have an id** — announcing you are doing something
  requires having said how you plan to do it.
- Naming a station that does not exist is **red**.

---

## How position is derived

> **A station's position = the de-duplicated count of steps named by `closed-step:` across
> all closure declarations, over the number of steps the station declares.**

Traces come from **structured closure declarations only** — never from merged PR titles,
never from keywords in free text. That is not fastidiousness: keyword-in-free-text is the
shape that fails *silently* in every major implementation surveyed (a close keyword on a
non-default branch, a keyword in a comment, a smart-commit with a wrong key or an
ambiguous email — all of them drop the signal with no error).

| Case | Behaviour |
|---|---|
| N steps declared, zero traces | renders **`0/N`** — not blank, not complete |
| the same step named twice | counted once, not an error |
| a trace naming an undeclared step | **red** — dangling reference |
| a trace naming a nonexistent station | **red** — dangling reference |
| steps appended after a closure | N grows, numerator does not. The ratio drops, and that is correct: the plan got wider, so progress got smaller, visibly |
| denominator zero | impossible — the ≥ 1 lower bound stops it. If reached anyway, fail hard rather than return a value |

`done` means numerator = denominator, with denominator ≥ 1. There is no other test.

**The cost, stated:** position advances only when a phase closes, not per commit. A
station being worked on right now still reads `0/N`. That is correct rather than a defect
— "half done" is not something a closure record can prove, and this format declines to
display what it cannot prove.

**Archiving must not move position.** A reader that scans only live documents will watch
position go *backwards* the moment specs are archived, while no history changed. Scan the
live tree and the archive, then de-duplicate.

---

## Three states, three sources, no overlap

| State | Sole source |
|---|---|
| `done` | derived (above) |
| `doing` | the `## 🚦` list |
| `future` | neither — it is the difference |

A station derived `done` **and** listed as `doing` is red. Glyphs in the table are
rendered *out of* state; they are never read back *in*.

---

## The lead rule — a row has to open with something a person can read

**A mainline row's `name` cell, and the LEAD of its `what` cell, are each at most 60 display
columns. The detail after the lead is not capped.**

The lead is the text before the first of `。`, `. ` (a full stop and a space, so `v1.1` is not
a sentence end) or `<br>`. A cell with none of those is all lead — the honest reading, not a
loophole.

**Why a lead rule and not a length cap.** Twice, a reader opened the progress page and bounced
off it with the same two words: too long. Both times the text came from this format. A cap was
rejected because the detail is load-bearing — entries exist to preserve reasoning, and deleting
it to fit a number is worse than the wall. But the cell was never formless: measured on this
repo, the `what` cell has a median of 953 characters while its FIRST SENTENCE has a median of
78. The lead already existed. Nothing marked where it ended, so nothing downstream could show
it alone — and a downstream consumer is forbidden to summarise, because a view derived from a
hand-maintained copy drifts (measured here, not feared). Marking the lead gives a renderer
something AUTHORED to show, and showing a declared lead is not summarising.

**Enforced as a ratchet, because the honest starting point is bad.** In display columns, on the
day this rule landed: **49 of 52 name cells and 45 of 52 leads were over the bound.** A rule
that reds on 45 rows is a rule somebody switches off. So every row is pinned at its current
width in `.claude/roadmap-lead-baseline.tsv`:

| the row is… | the rule |
|---|---|
| pinned | may stay exactly as long as it is — and **may not grow** |
| not pinned (new, or renamed — which is the same as edited) | must meet the bound outright |

The pin is keyed on the **name cell**: not on position, and not on the backlog id. Position rots
on the first reorder. The backlog id was measured rather than assumed and cannot serve — 51 of
52 rows carry one, one carries none, and one id appears twice. Keying on the name buys the
property for free: renaming a row is touching it, so it stops being grandfathered.

**What this does not do:** it makes no existing row readable. It stops the wall growing and
makes it countable, and the count is the part that did not exist before. Shortening those 45 is
human work no check can do.

---

## What this format does not solve

Named, because a format whose gaps are unwritten gets trusted for things it cannot do.

1. **A short plan list and a detailed task file have no mechanical relation.** They can
   contradict each other and nothing fails.
2. **No undo.** Once a step is named by `closed-step:`, a later revert cannot take it
   back — position keeps reporting it complete. Adding `reopened-step:` would require
   defining a time order between declarations, which v1 does not have.
3. **`depends-on: none` and `closed-step: none` buy "somebody typed it", not "somebody
   checked".** An explicit `none` is indistinguishable from a hurried one.
4. **`0/N` cannot tell three states apart**: never touched · touched but nothing closed ·
   plan block created in this very commit.
5. **A station spanning several phases has nothing forcing the second phase's author to
   read the steps the first one declared.**
6. **All three numeric bounds are guesses** (7 steps; 60 columns for a step line; 60
   columns for a name and a lead). The third reuses the second's number and its reason —
   an 80-column terminal — rather than inventing a fourth. It is the only one that ships
   with the DISTRIBUTION it was chosen against, on the page above.
7. **The lead rule cannot make a bad lead good.** A row can open with 60 columns of
   nothing and pass. Length is checkable; whether the sentence is worth reading is not.

---

## Fixtures

`roadmap-format/fixtures/` holds `NN-name/input.md` + `expected.json` pairs. `valid/`
cases must parse; `invalid/` cases must be rejected, and each declares in
`expected.json` **which rule** rejects it — a fixture that fails for an unintended reason
is not evidence about the rule it claims to cover.

Check the fixture set itself with:

```bash
python3 scripts/test_roadmap_format_fixtures.py   # or: pytest scripts/test_roadmap_format_fixtures.py
```
