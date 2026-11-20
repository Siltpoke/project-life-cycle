# Checkpoint modes — risk-sized PROGRESS checkpoints

PLC has two kinds of checkpoint, and they are not the same thing:

- **Approval checkpoints** (`/ship`'s story / spec / PR, `references/checkpoint-segmentation.md`) —
  human gates that **block** until the user approves. They stop the chain.
- **Progress checkpoints** (this doc) — short status posts sized to risk that **inform** and do
  **not** block. You post one and keep going.

This doc is only about the second kind. It adopts the "Checkpoints and report" section of the
risk-adaptive-verification trial rule into PLC, wired to M2's risk tier.

## The load-bearing property: post and keep going

A progress checkpoint is **never** an approval gate. You post it and continue working — you do not
stop and wait for the user to react. The only things that stop you are the real stop conditions
that already applied before any checkpoint existed:

- destructive or irreversible changes (data deletion, migrations on real data, force-push, history
  rewrite, outward-facing actions);
- a significant architectural trade-off the user has not decided;
- a material change to agreed product behavior;
- ambiguous or unresolved requirements where a wrong guess changes what gets built.

If none of those apply, post the checkpoint and carry on. Treating a progress checkpoint as a
"may I continue?" gate is the anti-pattern — it re-introduces stop-and-ask between approved steps,
which is exactly what the user does not want.

## Sized to the M2 risk tier

The checkpoint cadence is sized to the phase's **effective risk tier** (the risk tier:
`max(objective careful-paths floor, declared risk: tier)`, resolved by `scripts/risk-tier.sh` +
`plc-careful-check.sh`). There is no second risk notion — it is the same tier M2 already computes.

| Effective tier | Progress checkpoints owed | Notes |
|---|---|---|
| LOW | none | the final report is the whole report; LOW is never jammed into mid-phase reporting |
| MEDIUM | one mid-phase checkpoint | posted after the first working implementation |
| HIGH | one mid-phase checkpoint | same requirement as MEDIUM at this layer |

The trial rule asks MEDIUM/HIGH for "two checkpoints", but checkpoint #2 — "before finalizing" — **is
the final report**, which PLC already makes mandatory (the journal FACT + the close report). So the
only *new* required artifact is the mid-phase checkpoint, and only for MEDIUM/HIGH. In PLC's cadence,
"after the first working implementation" means: after the builder returns and the validator passes
(cadence step 2), before extensive further work.

## The content shape (<=150 words)

A progress checkpoint is short — aim for under 150 words. Five bullets:

- **changed** — what changed and why, with the affected files.
- **tests** — which tests actually ran, their results, and what their assertions verify. Keep
  observed evidence apart from assumptions; never claim full regression coverage because a suite is
  green.
- **surprises** — unexpected failures, behavior changes, or scope expansion (or "none").
- **needs-judgment** — decisions or trade-offs that need the user (or "none"). This names them; it
  does not stop for them unless a real stop condition above applies.
- **next** — the next highest-value action.

The final report (checkpoint #2) adds: the risk level and whether it changed · each success
criterion met/not met, with the command and what it showed · remaining gaps · any unresolved
instruction conflicts.

## Where it is recorded (so the gate can see it)

A progress checkpoint is posted to chat **and** recorded in the phase qa-log fragment
(`docs/qa-log.d/<date>-<branch>.md`) — the same fragment `mode-provenance-recorded` and M2's
`risk-tier-evidence-floor` already read. One machine-readable marker line, then the content:

```
## Checkpoint — mid-phase (<date>)
checkpoint: mid-phase | risk: <LOW|MEDIUM|HIGH>
- changed: ...
- tests: ...
- surprises: ...
- needs-judgment: ...
- next: ...
```

The record is what makes the checkpoint verifiable. A checkpoint that lives only in chat is prose
the gate cannot see — the advisory shape the whole adoption exists to end.

## Enforcement (phase close, not runtime)

`scripts/invariants/checkpoint-floor.sh` (a close-gate check) verifies at **phase close** that a
MEDIUM/HIGH phase recorded its mid-phase checkpoint: it reds if the qa-log fragment carries no
`checkpoint: mid-phase` marker for a MEDIUM/HIGH effective tier. LOW owes nothing.

This fires once, at close — it is **not** a runtime block. The gate enforces that you *recorded* the
checkpoint, never that you *paused* for it. That separation is what lets "inform, not gate" and "the
gate enforces it" both be true.

**Anti-starvation escape:** if the floor genuinely does not apply, a
`SKIP: checkpoint-floor -- <reason>` line in the branch journal satisfies it. The waiver is in git,
so it is attributable by commit — the same controlled-waiver shape as M2's `SKIP: risk-floor`.

## Related

- `references/careful-paths.md` §"The 3-tier risk call" — the M2 tier this cadence is sized to.
- `scripts/risk-tier.sh` — resolves the declared/effective tier.
- `references/checkpoint-segmentation.md` — the *approval* checkpoints this doc is NOT about.
