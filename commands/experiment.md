---
description: Write an experiment proposal for this phase, one section at a time, stopping for the user at each. Nine sections — Hypothesis / Baseline / Dataset / Ground Truth / Metrics / Procedure / Variance / Decision Rule / Cost — landed as a file under docs/experiments/. Per-phase step 3.5. It does NOT run the experiment, and it does not decide whether one is needed for you.
---

# /experiment — say what would count as better, before building it

Writes the proposal that per-phase **step 3.5** asks for, following
`skills/project-lifecycle/references/experiment-gate.md`. Output is one file:
`docs/experiments/YYYY-MM-DD-phase-<phase>-<slug>.md`.

**Guts, not new capability.** The template, the trigger conditions and the three-state Decision Rule
all live in the reference doc. This command is the button; it adds no rules of its own, and where
this file and the reference doc disagree, **the reference doc wins** — do not re-derive its content
here.

## First: does this phase even need one?

**Do not skip this and start filling in sections.** A proposal demanded on every phase is a rubber
stamp, which is worse than nothing — it costs the time, returns a document nobody believes, and
makes the record look like the discipline is running.

Apply the reference doc's Section D. The one-sentence test: **can you write "changing X improves
Y"?** If you cannot, either this change needs no proposal, or you do not yet know what you are doing
— and the second is exactly when to stop rather than proceed.

If the answer is that no proposal is owed, **say so to the user, name the category, and stop.** Tell
them the line to put in the journal's "Plan deviations":

```
SKIP: experiment-proposal — <one of: rename | docs | formatting | dependency-bump |
                             equivalent-rewrite | no-measurable-behaviour>
```

`no-measurable-behaviour` is the one category that also needs a clause after it, naming what was
considered and why it does not move. The other five are checkable against the diff; that one is a
judgement with nothing behind it but the claim.

## Then: one section at a time

**Ask about ONE section, wait for the answer, then move to the next.** Do not draft all nine and
present them for approval.

That is the whole shape of this command and it is not a style preference. **A proposal the user did
not participate in writing is the rubber stamp Section D exists to prevent, arriving through a
different door** — a nine-section draft handed over for a yes gets a yes, and the hypothesis it
contains is the AI's, not theirs. The reference doc puts it plainly: the definition of success is
brainstormed **with** the user, never proposed-and-nodded-at.

Order matters — later sections depend on earlier answers:

1. **Hypothesis** — push for a falsifiable sentence. "Let us see what happens" is not one. If they
   cannot state it, that is the finding: go back to the section above.
2. **Baseline** — what the number is today, where it came from, which commit. **No baseline, no
   experiment.** If there is no baseline, measuring one is the first experiment.
3. **Dataset** — which cases, how stratified, whether they represent the real distribution.
4. **Ground truth** — where each case's right answer comes from.
5. **Metrics** — one primary, plus guardrails. Ask what would be wrecked by moving the primary.
6. **Procedure** — what is held fixed; one change at a time.
7. **Variance** — how many runs, how reported, **and whether the instrument can resolve the
   difference they are hoping for.** This is where "we cannot tell" gets discovered cheaply.
8. **Decision Rule** — three states: pass / fail / **not-measurable**. Fixed before looking. If they
   offer two, name what the third prevents: an unresolvable result forced into "fail" and then read
   as "the change did nothing", when the truth is the scale cannot see it.
9. **Cost** — money and hours. **Anything paid stops for an explicit yes**, and read the script
   header before calling something free.

## Offer tiers, not a single proposal

Where success could reasonably be defined at more than one level, **give the user tiers with each
tier's cost in plain language** and let them choose or change it. A single option is a decision
already made, presented as a question.

## What this command does not do

- **It does not run the experiment.** It produces the proposal and stops.
- **It does not decide whether a proposal is needed.** It applies Section D's triggers and tells the
  user what it found; the skip is theirs to record.
- **It does not judge the proposal.** Neither does the close gate — check 12 verifies the file
  exists and carries nine headings, and prints that bound on every pass. Nothing in this repo reads
  a hypothesis and tells you it is a good one.
