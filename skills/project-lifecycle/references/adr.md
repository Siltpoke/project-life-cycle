# ADR — Architectural Decision Records

Lightweight markdown records for **hard-to-reverse** decisions with non-obvious trade-offs. Adopted from Matt Pocock's grilling skills ([`mattpocock/skills`](https://github.com/mattpocock/skills) → `skills/productivity`; originally a `grill-with-docs` skill, since reorganized into `grilling`).

**Distinct from spec-doc locked decisions:** spec-doc decisions are phase-scoped, captured during brainstorm w/ evidence tags. ADRs are repo-wide, survive milestones, and answer "why did we do it this way?" for a future engineer who never saw the original conversation.

## When to Offer an ADR (3-Criteria Gate)

All three MUST be true. Missing one → skip the ADR.

1. **Hard to reverse** — cost of changing your mind later is meaningful (quarter+ of work, breaking migration, customer-visible churn)
2. **Surprising without context** — a future reader will look at the code and wonder "why on earth did they do it this way?"
3. **Result of a real trade-off** — genuine alternatives existed and you picked one for specific reasons

If easy to reverse → skip; you'll just reverse it. If not surprising → nobody will wonder why. If no real alternative → nothing to record beyond "we did the obvious thing."

## What Qualifies

| Category | Example |
|---|---|
| **Architectural shape** | "Write model is event-sourced, read model is projected into Postgres." |
| **Cross-context integration patterns** | "Ordering and Billing communicate via domain events, not synchronous HTTP." |
| **Tech choices with lock-in** | DB, message bus, auth provider, deployment target. Not every library — only ones that take a quarter to swap out. |
| **Boundary + scope** | "Customer data is owned by Customer context; other contexts reference by ID only." Explicit no's are as valuable as yes's. |
| **Deliberate deviations from obvious path** | "Using manual SQL instead of ORM because X." Stops future "fixes" of intentional choices. |
| **Constraints invisible in code** | "Can't use AWS because of compliance." "Response times must be <200ms because of partner API contract." |
| **Non-obvious rejections** | If GraphQL was considered + REST picked for subtle reasons, record it. Otherwise someone re-suggests GraphQL in 6 months. |

## What Does NOT Qualify

- Interchangeable library swaps (axios vs fetch — easy reverse)
- Naming conventions (covered by CONTEXT.md + style guide)
- File layout choices (visible in the code)
- Phase-specific implementation decisions (live in spec doc / journal)
- Decisions that "feel important" but pass the easy-reverse test

## File Structure + Numbering

```
docs/
└── adr/
    ├── 0001-event-sourced-write-model.md
    ├── 0002-postgres-for-read-projections.md
    └── 0003-domain-events-not-sync-http.md
```

- Sequential numbering: scan `docs/adr/` for highest existing → increment by 1
- Slug = short kebab-case decision summary
- **Lazy creation** — create `docs/adr/` only when first ADR is needed
- Multi-context repos: per-context ADRs at `src/<context>/docs/adr/`, system-wide at root `docs/adr/`

## Template (default minimum)

```markdown
# {Short title of the decision}

{1-3 sentences: what's the context, what did we decide, and why.}
```

That's it. An ADR can be a single paragraph. The value is recording *that* a decision was made and *why* — not in filling out sections nobody reads.

## Optional Sections (add only when they earn their keep)

- **Status frontmatter** (`proposed | accepted | deprecated | superseded by ADR-NNNN`) — useful when decisions get revisited
- **Considered Options** — only when rejected alternatives are worth remembering
- **Consequences** — only when non-obvious downstream effects need to be called out

## Example — Minimum

```markdown
# Event-sourced write model

The Ordering context uses event sourcing for the write side. Read model is a projection into Postgres, rebuilt from the event log. Picked over CRUD because audit history is a regulatory requirement and projection rebuild gives free schema migration.
```

## Example — With Optional Sections

```markdown
---
status: accepted
---

# Event-sourced write model

The Ordering context uses event sourcing for the write side. Read model is a projection into Postgres.

## Considered Options
- CRUD with audit log table — rejected: audit log gets out of sync with main table under concurrent writes
- Bi-temporal table — rejected: query complexity too high for read path
- Event sourcing (chosen)

## Consequences
- Schema migrations are projection rebuilds, not ALTER TABLE — slower but safer
- Debugging requires reading events, not table state — onboarding cost
- All writes go through command handlers; no direct DB writes allowed
```

## When to Offer During Brainstorm / Grilling

User rejects a candidate with a load-bearing reason → offer ADR framed as:

> "Want me to record this as an ADR so future architecture reviews don't re-suggest it?"

Only offer when the reason would actually be needed by a future explorer. Skip ephemeral reasons ("not worth it right now") and self-evident ones.

## Anti-patterns

- **ADRs for trivial decisions** — turns the ADR dir into noise; future readers stop reading. Apply 3-criteria gate strictly.
- **ADRs written as essays** — 1-3 sentences default. Long ADRs go unread. Add sections only when they earn it.
- **ADRs duplicating spec-doc decisions** — phase-scoped locked decisions live in spec. ADRs are for repo-wide, milestone-spanning calls.
- **Updating an old ADR in place** — instead, supersede with new ADR + add `superseded by ADR-NNNN` to old. Preserves history.
- **ADR dir pre-created with placeholder ADRs** — lazy creation. Empty dir is fine until the first real ADR.
