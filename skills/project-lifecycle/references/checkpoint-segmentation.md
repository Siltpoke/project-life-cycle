# Checkpoint Segmentation — Human Checkpoints Between Background Workflow Segments

Design reference for splitting a checkpoint-gated chain (like `/ship`'s outer chain) into
Workflow-scriptable segments. Distilled from the checkpoint-FREE verification
*tail*, `.claude/workflows/verify-tail.mjs`, while scoping the checkpoint-GATED
*outer* chain that wraps it. No implementation lands with this doc; it is a design reference
for the future segmented `/ship` script, same category as `cadence.md` and
`builder-split.md`.

## Why a checkpoint cannot live inside a workflow

A Workflow script runs in the background and returns only on completion — it has no
mechanism to pause mid-run and block for human input. A checkpoint, by definition, blocks
until the user approves. Put the two together and the conclusion is mechanical, not a
design preference: **a checkpoint can never be a step inside a workflow script.** It can
only be a **main-thread** step *between* two workflow invocations, where the controller
itself is waiting on the user, not the script.

This is the load-bearing constraint the rest of this pattern derives from. Every other
rule below exists to make "checkpoint between two scripts" actually work in practice.

## Segment / surface / wait / resume

Split the chain at each checkpoint boundary into N segments:

- Each segment is a **self-contained** `.claude/workflows/*.mjs` script that runs to
  completion and **returns structured output** — the artifact path(s) it produced, plus
  whatever state the next segment needs to pick up where this one left off.
- The main thread does four things per boundary, in order:
  1. **Read** the segment's return value.
  2. **Surface** the artifact to the user (the file, the diff, the summary — whatever the
     checkpoint is actually approving).
  3. **Wait** for explicit approval. This is the checkpoint; nothing about it is scripted.
  4. **Resume** by invoking the next segment, passing the prior segment's output forward
     via `args`.

### Worked instance — the `/ship` chain's three segments

`commands/ship.md`'s eleven phases (Phase 0–10) collapse into three segments at the three
checkpoints it already defines:

1. **Segment 1** — Phase 0 (research) + Phase 1 (story) → **⏸ CHECKPOINT 1** (approve
   story).
2. **Segment 2** — Phase 2 (spec) → **⏸ CHECKPOINT 2** (approve spec).
3. **Segment 3** — Phase 3 (BE build) + Phase 4 (FE build) + the already-scripted
   `verify-tail` (Phases 5, 6, 8: acceptance verifier ∥ code-quality, validator joins on
   the verifier report; returns findings + holes) + the controller's **Phase 7 fix loop**
   orchestrated *around* `verify-tail` (route each finding to a builder, commit a
   `fix(...)`, re-run `verify-tail`, loop until clean — STOP after 3 iterations on the
   same finding and escalate to the user per `commands/ship.md` Phase 7) + Phase 9 (journal) + Phase 10 (smoke + PR draft) →
   **⏸ CHECKPOINT 3** (approve PR).

Segment 3 is the largest because it has no checkpoint inside it to split on — everything
between "spec approved" and "PR drafted" runs unattended today, per `commands/ship.md`
§"Three checkpoints (all others run unattended)". A segment boundary tracks a checkpoint
boundary; it does not track phase count.

## Checkpoint-rejection reflow

When the user rejects at a checkpoint, re-run **only that segment** with the rejection
feedback folded into its input — never the whole chain. Prior segments already produced
approved artifacts (the story, the spec); those stay untouched and are not regenerated.
Re-running segment 2 after a spec rejection, for example, re-invokes only the spec-writing
segment, still anchored on the already-approved story from segment 1.

This is a different mechanism from the Phase-7 fix loop the controller hand-dispatches
*around* `verify-tail` within segment 3 (`commands/ship.md` Phase 7 — STOP after 3
iterations on the same finding and escalate) — that loop wraps `verify-tail` rather than
living inside it, and re-runs in
response to a failing validator or acceptance test, not a human checkpoint rejection.
Don't conflate the two: one is a human saying "not this," the other is an automated
reviewer saying "not correct yet."

## `args` handoff + Workflow gotchas

Segment-to-segment state travels through the next segment's `args` parameter — the same
mechanism `verify-tail.mjs` already uses to receive `builderCommitSHA`, `prevTaskTip`,
`builderSummary`, and friends (`cadence.md` §"Background-by-default: the verification
tail"). One handoff-specific hazard: `args` may arrive as a JSON **string** rather than an
already-parsed object, so every receiving segment must guard at its own entry point:

```js
const parsed = typeof args === 'string' ? JSON.parse(args) : args;
```

This is one of several hard constraints the Workflow tool imposes on any script built
against it. The authoritative set is:
self-containment (no module resolution), the
top-level-`return` syntax-gate that blocks `node --check` and `import`-ing the entry,
invoke-by-`scriptPath` (never by name), and args-may-arrive-as-a-string. Any new segmented script (now
or later) is written against those four, not against assumptions re-litigated per script.

## Related

- `references/cadence.md` §"Background-by-default: the verification tail" — the
  checkpoint-FREE tail this pattern wraps; segment 3 invokes it as one step.
- `references/builder-split.md` — the BE/FE builder split that runs inside segment 3.
- `commands/ship.md` — the eleven-phase chain (Phase 0–10) and three checkpoints this doc segments.
