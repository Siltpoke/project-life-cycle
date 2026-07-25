# Research Gate

When to do online research before deciding. Triggers and exclusions are project-agnostic; the specific surface labels in trigger (c) vary by domain.

## MUST research before deciding

A decision matches the gate if **any** of the following holds:

a. **Introduces a new persistent data shape or schema migration.** New table, new column on a busy table, new field on a contract that downstream consumers will type against, ORM/DB migration with rollback consequences.

b. **Changes a cross-phase / cross-package / cross-service contract.** Public API, RPC schema, event payload, generated TS/Go/protobuf type, OpenAPI spec, message broker topic shape.

c. **Touches a security or compliance surface.** Authn / authz / audit / secret handling / sensitive-data-at-rest / sensitive-data-in-transit / regulated content. (Specific list per project — fintech adds PCI, healthcare adds HIPAA/PHI, EU products add GDPR/PIPL, etc.)

d. **Adopts or replaces a third-party dependency.** New library on a critical path, runtime upgrade (Node major, Python major, Postgres major), framework swap.

## MAY skip research

Decisions that **don't** match the gate:

- Bug fixes within an existing established pattern.
- Styling / copy / accessibility polish in already-adopted patterns.
- Pure test additions (no code change).
- Refactors that preserve external behavior.

## Citation format

When research happens, capture in the spec or ADR:

```markdown
## Research

- [Source title](https://example.com/path) — what it claims, why it's relevant. Date accessed YYYY-MM-DD.
- [Counter-source](https://example.com/other) — disagrees with the above on X; we choose Y because Z.
```

Two to five sources is usually right. Single-source is a weak signal.

## Risk-naming after each major decision (cross-check agent A)

Append to the decision record, for each major decision:

> Given the choice made, name at least two things that could go wrong that we may be missing. For each: when would it bite? How would we detect it? What's the rollback?

This is produced by the **cross-check agent A** (SKILL.md step 3, `references/reviewer-brief.md` §"Cross-check lens" output C) — an independent read-only agent at brainstorm close, **not** the spec's writer self-grading. Its output fills the qa-log entry's `Risks (what could go wrong with this choice)` field, tagged `cross-check agent A` to keep it distinguishable from the lines the blind 2nd agent produced.

This forces explicit consideration of downside before locking in.
