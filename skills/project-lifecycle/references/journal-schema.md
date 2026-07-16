# Iteration Journal Entry Schema

Per-task entries (covering all of the task's commits, not each individually) are appended to the current branch's fragment file `docs/journal.d/<date>-<branch-slug>.md` (one fragment per branch — under WIP=1, branch and phase are effectively the same unit of work, so this reads as "one fragment per phase" in practice; monolith `docs/iteration-journal.md` remains the fallback for projects not yet on the fragment convention — see `references/retention.md`). Six required sections.

## Template

```markdown
## Milestone N.M Task K — <one-line summary>

- **Date:** YYYY-MM-DD
- **Commits:** <feat-sha> + <fixup-sha(s)> + journal <docs-sha>
- **Refs:** plan §"..." (path:line); spec §...; research <doc>.

**Observations** — Why does this task exist? What state of the world does it address? What did you notice while working on it that wasn't obvious from the plan?

**Motivations** — Three to five design choices. Each one a paragraph: what was the choice, what alternatives were considered, why this one wins.

**What changed** — File-by-file (or component-by-component) summary of the actual diffs. Should be readable as a description of the change-set, not a re-listing of the file paths.

**Plan deviations** — Required header. If there are no deviations, write "none". If there are, enumerate each:
- What the plan said
- What was actually done
- Why the deviation was necessary or beneficial
Plans always drift; the drift is the most valuable signal for future audits and onboarding.

**Impact** — What can the project / users / future tasks now do that they couldn't before? Include test counts, coverage numbers, and any cross-cutting effects.

**Final verification** — Bullets: targeted test count, full-suite count, coverage, lint, build, schema-drift checks. The actual numbers — this is the audit trail.
```

## Why these six sections

| Section | Bug class it catches |
|---|---|
| Observations | "We forgot why we did this 3 months later" |
| Motivations | "We picked X but no one remembers what we rejected" |
| What changed | Code review without re-reading the diff |
| Plan deviations | Silent drift; audit / onboarding gaps |
| Impact | "Did anyone actually verify the milestone goal moved forward?" |
| Final verification | "Did tests run? Was lint clean?" |

## Anti-patterns

- **Per-commit journal entries.** One entry per task; the task's commits roll up.
- **Skipping "Plan deviations" because there are none.** Keep the header with "none" — its presence forces the active drift check.
- **Narrative storytelling.** This is a project audit log, not a blog post. Bullet-style facts beat narrative prose.
- **Numbers without source.** "All tests pass" is not enough. "N passed + 1 xfailed in 8.3s, coverage 95%" is — the point is that the numbers are there and sourced.
- **Linking to commits without inline summary.** Reader shouldn't have to context-switch to git to understand what shipped.

## The FACT entry (track close)

At track close the working spec/plan are distilled into ONE entry with these fields. **All are required except `Gotcha`** — an entry missing a required field is not a FACT entry. **Canonical form is the markdown bullet** shown below — `- **Field:**` — not a bare `Field:` line; this is the form the check in `references/close-gate.md` (`phase-done`) greps for, and the form a journal written under this schema actually writes.

```markdown
## FACT — <one-line summary>

- **Date:**     2026-07-13
- **Decision:** <what was chosen>
- **Why:**      <the reasoning as it stood that day>
- **Backing:**  <a load-bearing figure> — <where it was measured>   (repeatable)
- **Rejected:** <what was NOT chosen> — <why not>
- **Gotcha:**   <trap hit during the work>   (optional, repeatable)
- **Source:**   <sha>:<the path the working doc had BEFORE it was archived>
```

**Enforced, not exhorted.** `phase-done` greps the newest `docs/journal.d/*.md` fragment (mtime order) for `- **Date:**`, `- **Decision:**`, `- **Why:**`, `- **Backing:**`, `- **Rejected:**`, `- **Source:**` and hard-fails, naming which are missing, if any are absent — see `references/close-gate.md` §"What the gate checks" → `phase-done`. `references-log` is 85–90% rot-resistant *because its schema will not accept a claim without a `Date` and a `Backing`* — not because whoever wrote it was more disciplined. Every rot-resistant document measured in the sampled corpus (Decisions log 95% FACT, brainstorming-qa-log 85%, references-log 85–90%) shares one shape: **a date + a decision + why + the evidence + what was rejected**.

**`Backing` is the evidence slot, and it exists because its absence was measured** (this schema's own first subject). Distilling a spec into a FACT entry carried `Rejected` **7 of 7** and lost most of `Why` — because the schema had a slot for the **conclusion** and none for the **evidence the conclusion rested on**. Every argument silently degraded into an assertion. Gone from one spec: the single statistic its entire case turned on, a corollary the spec itself had marked *load-bearing*.

A missing field cannot be patched by writing more prose into an adjacent one. Length was never the constraint — this schema explicitly permits unbounded length. **With no slot that says "the number you must not drop," the writer drops it.** So: one bullet per load-bearing figure, each carrying the figure *and where it was measured*. If a `Why` clause rests on a number, that number gets a `Backing` line or the `Why` is an assertion.

> The schema was derived from `references-log`, whose entries carry `Backing` *precisely* so a claim cannot be stated without its support. The first version of this file **said that, two lines below a schema block that had copied `Date` and dropped `Backing`.** The mechanism failed at the one place its own source document told it not to. That is the whole argument for this field, and it is not hypothetical.

**`Rejected` is the highest-value field.** Code records what was built. It never records what was almost built and discarded. That information is unrecoverable by construction — it is the reason a FACT layer has to exist at all.

**`Source` is the archive address.** It pins the working doc at the commit where it last lived, so `git show <sha>:<path>` returns it byte-for-byte after archival.

## Tense: record the MOMENT, never the STATE

> **A document that records a MOMENT does not rot. A document that claims a STATE always rots.**

- *"On 2026-07-13 we chose X because Y"* → **permanently true**
- *"The system currently does X"* → **starts dying the second it is written**

Measured: accuracy correlates with a document's **age**, not with the care taken writing it. You cannot write a cache well enough to stop it rotting. Effort does not help; only time does. This is why *"write better docs"* and *"maintain them diligently"* cannot work — they are a footrace against time.

**Journal entries are written in the past tense about a dated moment.** They do not describe the system's present shape.

**Corollary — no PLC document answers "where are we now."** "Now" is read from the live source (`git log`, `gh pr list`, the test run, a generated tracker). Documents answer *how we got here, and why*. A hand-written "current state" section is a cache with a human maintainer attached, and it loses.
