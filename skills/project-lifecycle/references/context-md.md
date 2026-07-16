# CONTEXT.md — Ubiquitous Language Glossary

Project-wide domain glossary. Adopted from Eric Evans's ubiquitous-language idea from *Domain-Driven Design* (2003) and Matt Pocock's grilling skills ([`mattpocock/skills`](https://github.com/mattpocock/skills) → `skills/productivity`; the idea originally lived in a `grill-with-docs` skill, since reorganized into `grilling`).

**Why this exists:** when AI replies stay verbose and re-explain domain terms every phase, the project is missing a shared-language anchor. CONTEXT.md anchors the vocabulary that code + docs + chat all use. Benefits: terser AI replies, tighter thinking traces, easier-to-navigate code, fewer naming drifts between spec ↔ implementation.

## Hard Boundary — Glossary ONLY

`CONTEXT.md` is a glossary. Not a spec, not a scratch pad, not an implementation-decisions doc.

- ✅ Term definitions, relationships, example dialogues, flagged ambiguities
- ❌ Implementation details, API contracts, file paths, decision rationale, architecture diagrams

Implementation decisions → spec doc / plan doc. Hard-to-reverse decisions → ADR (`references/adr.md`). General programming concepts (timeouts, error types, utility patterns) → NOT in CONTEXT.md, even if used heavily.

**Test before adding a term:** is this a concept unique to this project's domain, or a general programming concept? Only the former.

## File Structure

### Single-context (most repos)

```
/
├── CONTEXT.md
├── docs/
│   └── adr/
└── src/
```

### Multi-context (large monorepos)

```
/
├── CONTEXT-MAP.md
├── docs/
│   └── adr/                          ← system-wide decisions
├── src/
│   ├── ordering/
│   │   ├── CONTEXT.md
│   │   └── docs/adr/                 ← context-specific decisions
│   └── billing/
│       ├── CONTEXT.md
│       └── docs/adr/
```

**Detection rule:**
- `CONTEXT-MAP.md` at root exists → multi-context; read map to find each `CONTEXT.md`
- Only root `CONTEXT.md` exists → single-context
- Neither exists → create root `CONTEXT.md` lazily when first term is resolved

## Lazy Creation

Do NOT pre-fill CONTEXT.md at project start. Create when the **first** term needs definition (typically during the first brainstorm). Add terms incrementally as language gets resolved through grilling / Q&A / code exploration.

## Format

```markdown
# {Context Name}

{One or two sentence description of what this context is and why it exists.}

## Language

**Order**:
A confirmed customer request for one or more products.
_Avoid:_ Purchase, transaction

**Invoice**:
A request for payment sent to a customer after delivery.
_Avoid:_ Bill, payment request

**Customer**:
A person or organization that places orders.
_Avoid:_ Client, buyer, account

## Relationships

- An **Order** produces one or more **Invoices**
- An **Invoice** belongs to exactly one **Customer**
- A **Fulfillment** confirmation must occur before an **Invoice** is generated

## Example dialogue

> **Dev:** "When a **Customer** places an **Order**, do we create the **Invoice** immediately?"
> **Domain expert:** "No — an **Invoice** is only generated once a **Fulfillment** is confirmed."

## Flagged ambiguities

- "account" was used to mean both **Customer** and **User** — resolved: these are distinct concepts. **Account** removed from vocabulary; use **Customer** or **User** explicitly.
```

## CONTEXT-MAP.md Format (multi-context only)

```markdown
# Context Map

## Contexts

- [Ordering](./src/ordering/CONTEXT.md) — receives and tracks customer orders
- [Billing](./src/billing/CONTEXT.md) — generates invoices and processes payments
- [Fulfillment](./src/fulfillment/CONTEXT.md) — manages warehouse picking and shipping

## Relationships

- **Ordering → Fulfillment**: Ordering emits `OrderPlaced` events; Fulfillment consumes them to start picking
- **Fulfillment → Billing**: Fulfillment emits `ShipmentDispatched` events; Billing consumes them to generate invoices
- **Ordering ↔ Billing**: Shared types for `CustomerId` and `Money`
```

## Discipline Rules

- **Be opinionated.** Multiple words for the same concept → pick the best one, list others under `_Avoid:_`. Don't preserve every synonym.
- **Flag conflicts explicitly.** Ambiguous term → call it out in "Flagged ambiguities" with the resolution. Don't bury it.
- **Definitions stay tight.** One sentence max. Define what it IS, not what it does.
- **Show relationships + cardinality.** Use bold term names. "An X produces one or more Y" beats "X has Y."
- **Group under subheadings** only when natural clusters emerge. Flat list is fine for cohesive areas.
- **Write an example dialogue.** A dev ↔ domain-expert conversation that clarifies boundaries between related concepts. Forces precision.

## When to Update

CONTEXT.md updates happen **inline during work**, not in batch:

- **During brainstorm grilling** — when a term gets resolved or sharpened, update CONTEXT.md in the same turn
- **During code exploration** — when a term gets discovered in code that wasn't in the glossary yet, add it
- **During reviews** — when a reviewer flags vague language, sharpen the term + update glossary

Same commit as the source change. Never leave the glossary stale.

## CLAUDE.md Pointer (mandatory)

Every project's `CLAUDE.md` carries a pointer so the AI knows where to look:

```yaml
# Single-context
domain-docs: ./CONTEXT.md

# Multi-context
domain-docs: ./CONTEXT-MAP.md
```

Without the pointer, the AI may not discover the glossary and the alignment benefit evaporates.

## Anti-patterns

- **CONTEXT.md treated as scratch pad** — accumulating implementation notes, todo items, half-formed ideas. Revert; CONTEXT.md is glossary only. Move other content to spec / journal / scratch doc.
- **Pre-filling CONTEXT.md at project start** — creates terms nobody uses, generates noise, doesn't reflect actual vocabulary in play. Always lazy.
- **Adding general programming concepts** (timeout / retry / error code) — these aren't domain-specific. Keep them out even if heavily used.
- **Glossary updated in a batch at end of phase** — terms drift between when resolved and when written; small details lost. Update inline.
- **Two terms for the same concept both kept "for compatibility"** — pick one, add the other to `_Avoid:_`. Compatibility-preservation is how vocabulary drifts.
