# References-log capture — discipline (schema lives in the global log)

Gated auto-offer: during brainstorm/research, when the user shares an offer-worthy external
reference for analysis, PLC offers to capture it into the user's **global** references-log —
never silently. This doc owns the *capture discipline*. It deliberately does **not** carry the
entry schema: the schema (and the stance) live in the global log's own header and the user
evolves them there, so PLC reads them **live at capture time**. Copying the schema here would
guarantee drift.

## Prerequisite — armed only by the key

Active only when the `references-log:` policy key (user-global — see `output-format.md`) resolves
to an existing git repo path. If the key is unset or the path is missing, the auto-offer never
fires and this doc does nothing. Default is off, so users who haven't set the key are unaffected.

## Offer-worthy — the noise guard

Offer ONLY for a clear external reference the user brings in **for analysis**. The shapes below
are **illustrative, not exhaustive** — the global log header's `Type` enum is the live source for
what kinds exist; treat anything that reads as "an external thing to study" as a candidate:
- a URL to a repo / paper / blog / tool / video / talk, OR
- an **offline document** the user drops in by local file path or DOI (e.g. a downloaded PDF
  whitepaper / report — it has a locatable path + readable content), OR
- an explicitly-shared AI-chat log / screenshot / pasted note dropped in "for you to look at".

Do NOT offer for:
- a link used incidentally (a docs lookup mid-task),
- the user's own repo / PR,
- a bare action or instruction.

When unsure, **skip rather than nag** — there is no `/ref` fallback, so keep the bar high, but
don't spam. Over-offering is the failure mode to avoid.

## The gated offer — never silent

When an offer-worthy reference is shared during brainstorm/research, ask once, plainly:
"Want me to log this to your references-log?" — y/n. **Never write without the yes.**

## On yes — compose the entry (schema read live)

1. **Read the schema + stance live** from the top of `<references-log path>/references-log.md`
   — the header block. Follow whatever field list, order, and enums it currently defines. Do
   not rely on any copy; the header is the single source of truth and it changes over time.
2. **Dup-check:** scan existing entries for the same source. If found, surface it and offer a
   typed-edge update (the header's `duplicates →` edge / a supersede) instead of a fresh entry
   — reuse a supersede-style confirm (elicit-lightly, confirm-back, never-silent).
3. **Compose** the entry with your analysis — following the header's fields (a scannable TL;DR,
   your take, how hard the backing is, typed `Related` edges, `Actionables` that cite the
   relevant project's STATUS/backlog items), and tag the header's project field appropriately.
4. **Append newest-on-top** per the log's own convention (newest date section on top; within a
   date, in the order shared).

## Commit — scoped, no push

```
git -C <references-log path> add references-log.md
git -C <references-log path> commit -m "log: <ref-id> <short-slug>"
```

Commit **only** `references-log.md` — never `git add -A` (that would bundle unrelated
uncommitted work in that repo). **No push** — the user pushes on their own cadence.

## Confirm back — surface the analysis, not just a receipt

Two parts, **both required**:
1. **The receipt** — one line: "Logged [<ref-id>] <slug> to your references-log."
2. **The analysis, inline** — surface the take you just composed *into the conversation*: the
   core judgment (what's worth borrowing from the reference and what to avoid) + the Actionables.
   The user reads the payoff here, without opening the log.

A silent write the user has to go open the file to read is a **broken Grudin loop** — the person
who prompted the capture must see the value, and the value is your *analysis*, not the fact that a
file changed. The log entry is the durable record; the in-chat surfacing is the live payoff. Keep
it tight — the take's key judgment + the actionables, not the whole entry re-pasted.

## Relationship to the rest of the harness

- Reuses an existing confirm-flow as a **pattern** (elicit-lightly, dup-check, confirm-back,
  never-silent), NOT as shared code — a different store (a global Markdown log vs the project
  JSONL cognition store).
- The gate signal that fires this offer is wired in `brainstorm-research-protocol.md` and
  `intent-gate.md` (§"Capture trigger — rationale signals" sibling line).
- Distinct from the cognition `/capture` flow (that captures *rationale* into the project's cold
  intent-log; this captures *external references* into the user's cross-project global log).

## Out of scope

A `/ref` command; a per-project log; a heavy write script; the one-time backfill transcript
sweep (separate pending task); retention/pruning of the growing global log (future); content
privacy filtering (the content here is your composed analysis plus a shared link — lower risk).
