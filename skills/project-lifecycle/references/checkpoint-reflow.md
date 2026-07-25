# Checkpoint-rejection reflow (adopter contract)

**Status: design-only.** This reference defines a contract; this skill ships no runtime for it.
An adopter whose `/ship` chain runs with human checkpoints implements the contract below. The
skill itself does not run `/ship` on its own repo, so it has no personal consumer — the same
contract-not-runtime split as `references/verify-gate.md`'s liveness layer.

## The problem

`/ship`'s spec-writer (per-phase step 1 dispatch, `references/cadence.md`) is a **fresh-context
subagent**: its input is the user-story ACs + researcher findings + `CLAUDE.md`, nothing else.
When a human REJECTS at a checkpoint (story / spec / PR) with a reason — "spec rejected because
tenant-isolation was deferred" — and the spec-writer is re-dispatched, that reason never reaches
the fresh spec-writer. It can repeat a mistake the human already rejected. The harness/learning
separation is correct; the only missing wire is **learning-signal → factory-chain dispatch**.

## The hard constraint: no failure scoreboard

The reflow must NEVER become a **tool-maintained failure scoreboard** — an artifact whose job is
to accumulate rejections and reflect a running failure count/log back at the person. That is a
self-judgment / gamification trigger. The reflow must read as **forward requirements**, never a
record of past failures, and is scoped to the **current phase only**.

**Scope of the guarantee (stated to avoid an impossible goal).** The red line is "no
*tool-maintained* failure tally reflected at the person." It is NOT "the human can never infer
that they rejected things" — the human performed the rejections; that memory is theirs, and a
version-control diff will always show that requirements changed. The contract governs what the
**tool builds and shows**, not what a participant can remember or reconstruct. A design that
tries to also erase the human's own inferability is chasing an impossibility.

## The contract

1. **Trigger** — only on an explicit human checkpoint rejection **with a reason**, within `/ship`.
2. **Source of truth** — the phase's checkpoint rejection events, which already exist in the
   durable `/ship` / VCS / PR history. The controller **reads** these; it never writes a parallel
   rejection store.
3. **Transform** — controller-side, **lossy**: rewrite each rejection into a positive imperative
   constraint ("must handle X") and **discard the rejection event**. No `reason`/`why` field, no
   round number, no timestamp, no failure framing. **Preserve the acceptance level**: a blocking
   rejection yields a blocking-force constraint ("must handle X **before** …"), not a soft
   "consider X"; ambiguous force is confirmed with the human at the next checkpoint, never guessed.
4. **Wording validation** — each constraint is a standalone forward imperative, validated against
   a **banned-pattern list** (temporal / failure / round words: `again`, `still`, `failed`, `re-`,
   `retry`, `round`, `attempt`, any prior-round reference). The list, its normalization, and the
   on-violation behavior (re-derive or hold — never inject raw) are REQUIRED parameters; a default
   list ships with this contract; an adopter may tighten, never loosen.
5. **Assembly** — at re-dispatch, derive the constraint set and dedupe by normalized text.
   Near-duplicates that differ in scope / object / acceptance are **both injected** (the
   spec-writer and the next human checkpoint resolve them); the controller never silently picks
   one. Because the set is ephemeral (step 7), nothing is persisted to "display as repeated
   corrections".
6. **Injection** — the constraint set enters **only the spec-writer's dispatch input for that one
   turn**, alongside the ACs and researcher findings. The spec-writer never receives a rejection
   log or any per-round history.
7. **No persistence** — nothing rejection-derived is written to the requirements artifact, a side
   file, or any new artifact. Re-derive each dispatch. Cross-round carry within a phase is
   achieved by re-deriving from the durable rejection history, not by a persisted accumulator — a
   spec-writer that keeps dropping a constraint gets it re-asserted every round, which is exactly
   the failure this reflow exists to stop.
8. **Human authority** — the requirements artifact stays the human-signed artifact; it is never
   mutated by the controller. The spec-writer's output is signed at the next checkpoint as normal,
   so no controller-authored requirement ever sits unsigned inside the human's artifact.
9. **Per-phase** — the controller reads only the current phase's rejection events; nothing crosses
   the phase boundary; no copy-forward / templating carries constraints into a later phase.
10. **No scoreboard** — no persisted rejection artifact; no count / order / label / meter anywhere
    the tool renders to the person.

## Conformance checklist (adopter-runnable)

- After N rejections in a phase, the requirements artifact and the repo contain **no** new
  rejection-derived file, section, or monotonic ID series (a grep is empty).
- The spec-writer's dispatch input on a re-run contains the forward constraints, and they vanish
  after the turn (not persisted).
- A blocking rejection yields a blocking-force constraint.
- The banned-pattern validator rejects a constraint containing "again".
- Opening the next phase re-derives zero constraints from a different phase's history.

## Why every persisted form was rejected

Design convergence (recorded in the phase's design spec) tried and discarded each persisted
shape, because each leaked or muddied:

- A **labeled subsection** with monotonic IDs (`RC1, RC2, …`) titled "auto-derived from
  rejections" *is* a compact accumulating failure tally — a labeled, ordered, growing list.
- An **unlabeled merge** into the human-signed requirements artifact creates an author-authority
  ambiguity (controller-authored requirements that read as human-signed) and a participant can
  still recover a count from document growth across rounds.
- A **phase-scoped side file** is a store whose purpose is "rejections" — a ledger by another name.
- **Most-recent-only** loses distinct earlier constraints; **controller-context-only** (no
  re-derivation) dies at a mid-phase context reset.

The resolution is to persist **nothing** and re-derive from the rejection record that already
exists — audit substrate the tool does not reflect back, not a new scoreboard the tool maintains.
