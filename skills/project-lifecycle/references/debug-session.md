# Debug Session — behavior-locked debugging you enter when stuck

A **session** you enter when you are already on a bug — not a proactive "scan the code for bugs" pass.
You bring a bug; the session walks you through it with the behavior lock baked in — it locks the
behaviors around the bug so a fix that breaks one is caught (Step 4 says exactly how much of that is
gated vs. agent-run). The intent gate **offers** this session when a request is a
bug, and **never auto-starts it** — SKILL.md's front-door bug handling carries the offer; on decline you
get the ad-hoc `diagnose-loop.md` path.

**What this adds over `diagnose-loop.md`.** `diagnose-loop.md` is the 8-phase debug mechanics and already
writes a regression test for *the bug* (its Phase 5). It does **not** lock *the neighbors* — the behaviors
around the bug that currently work — so a fix can silently break an adjacent behavior no test pins. And a
real debug session usually turns up more than the one bug. This session threads two things onto the loop:
**lock the neighbors first** (M1 behavior lock) and **tier anything else you find** (`findings-tier.md`).
It does not restate the 8 phases — it points at them.

Run from the repo root. The session writes only to `.claude/` (the registry + baselines); running a
carrier executes the suite's code, with whatever side effects that suite has.

## Step 1 — Lock the neighbors (before you poke)

List the behaviors adjacent to the suspected bug that **currently pass** — the ones a careless fix could
regress. For each:

- **Carrier resolves** (`scripts/behavior-lock.sh --resolve "<carrier>"` exits 0) → append a `PRESERVE`
  row to `.claude/behavior-lock.tsv` (`id<TAB>PRESERVE<TAB><behavior><TAB><carrier><TAB><why>`, next
  `BL-<n>`) and record its `before` baseline from the carrier's own exit (which passes, `0`):
  `scripts/behavior-baseline.sh --record <id> before 0 "<carrier-cmd>" "<env>"`.
- **Carrier does not resolve** → the neighbor has no test that proves it. Do **not** seed a row (a
  dangling carrier would red the first close-gate via M1's `behavior-lock-carriers-resolve`). Log it as a
  **Coverage gap** — a candidate for a characterization test — and move on.

Then lock the bug itself as a **`FIX`** row (its carrier is the repro test; its `before` baseline is the
**failing** exit, non-zero): `scripts/behavior-baseline.sh --record <id> before <non-zero> "<cmd>" "<env>"`.

Every seeded row is a draft for human review, same provenance rules as any other registry row.

## Step 2 — Find the root cause (reuse `diagnose-loop.md`)

Run the 8-phase loop in `references/diagnose-loop.md` (that doc owns the phases — do not restate them
here). **Iron Law unchanged: no fix without root cause.**

## Step 3 — Tier anything else you turn up (reuse `findings-tier.md`)

A debug session routinely surfaces problems that are not the bug you came for. Do **not** scope-creep the
fix to chase them. Tier each incidental finding **S1 / S2 / S3** per `references/findings-tier.md` (that
doc owns what each tier means and the action it drives). One bug in, one fix out; the rest get tiered.

## Step 4 — Prove the fix regressed nothing

Two layers, and they catch **different** breaks — be precise about which is gated:

- **Gated (close-gate): the carrier still exists.** Run M1's
  `scripts/invariants/behavior-lock-carriers-resolve.sh` — it reds if the fix **removed or renamed** a
  locked neighbor's carrier test. This is the enforced guarantee: the sneakiest regression — silently
  deleting the test that pinned a neighbor — cannot ship. It does **not** check that a still-present test
  passes.
- **Agent-run, NOT gated: the neighbor still passes.** For each row, run the carrier, record its `after`
  exit (`scripts/behavior-baseline.sh --record <id> after <exit> ...`), then check the transition
  (`scripts/behavior-baseline.sh --check-transition <id>`): the **`FIX`** row must be **fail→pass**
  (`before` non-zero, `after` 0); every **`PRESERVE`** neighbor must be **pass→pass**. A neighbor whose
  test is still present but now **fails** is caught **here and nowhere else** — `--check-transition`
  flags pass→fail, while `behavior-lock-carriers-resolve` stays green for it. Running Step 4 is the
  agent's discipline, the same way diagnose-loop's regression test is.

Cold rows graduate out once the behavior is pinned by a permanent suite test (M1's graduation rule); the
registry stays lean.

## Honest boundary (stated)

Whether the agent offers the session, and whether you accept, is prose — like the AFK offer in
`intent-gate.md` and like the brownfield baseline in `archaeology.md`. This is **not** a gate that forces
a debug session, and there is **no new script** — the four steps are documented commands over
`behavior-lock.sh`, `behavior-baseline.sh`, `diagnose-loop.md`, and `findings-tier.md`. What is
**mechanically enforced at close-gate** is only Step 4's first layer: once a row exists,
`behavior-lock-carriers-resolve` reds if its carrier is **removed or renamed**. The pass→fail check
(`--check-transition`) is **not wired into any gate** — it depends on the agent running the carrier and
recording `after`, so a neighbor whose test is present but failing is caught only if Step 4 is actually
run. That is the real boundary: the lock gates the carrier's **existence**, not its **green-ness**.

A standalone `/debug` command (an explicit way to start the session without the gate's offer) is a
possible later add; the primary entry is the gate offer.
