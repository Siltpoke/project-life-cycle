# Dependency boundary — PLC depends on nothing external; integrate via open contracts

PLC is **drop-in-anywhere**. That is the whole claim, and it constrains every integration
decision: **PLC must depend on no external product, host, or tool to perform any of its own
steps** — progress display, the review gate, session continuity, the close gate. A step that
only works when some *other* thing is installed is not portable, and portability is the product.

This generalizes the self-sufficiency rule (genericize or declare every by-name external
dependency; see `SKILL.md` and the `reviewer-brief.md` / `handoff-snapshot.md`
buttons that replaced by-name agent dependencies): not merely "no by-name agent dependency," but
**no external-product dependency in either direction**.

## The rule

**Interoperate through open, documented, versioned file-format contracts — never through runtime
dependency.** A sibling tool may cooperate with PLC, but only by producing or consuming a format
that *any* tool or human could also produce or consume (e.g. the `.claude/tasklist.md`
checkbox-markdown convention; PLC's Markdown artifacts). Depending on such a format is depending on
a *spec* — like depending on JSON — not on a product.

- **Mutual independence.** Neither PLC nor a sibling tool runtime-depends on the other. PLC runs
  with none of them installed; a consumer runs with no PLC (it simply finds no artifact and shows
  nothing). The only shared thing is the format.
- **Data-flow direction ≠ dependency.** A consumer reading a PLC-produced file does **not** depend
  on PLC — it reads a *format*, and the file could have come from anywhere (a markdown viewer
  reading `.md` does not depend on any particular editor). This is what keeps "mutual independence"
  true even when bytes flow one way.
- **Residual coupling = shared schema, and only that.** Where PLC *defines* the format, manage the
  link by writing the format down as a **standalone versioned contract** ("the `<file>` convention",
  not "PLC's private file"), so a consumer depends on the spec, not on the PLC runtime. This is the
  mildest coupling class — not "one can't work without the other."

## PULL over EMIT

Two integration shapes exist and they are **not** equally decoupled:

- **EMIT** (PLC → consumer, armed by an opt-in key like `references-log:`): PLC *additionally*
  pushes to a receiver when the key is armed. PLC still carries a consumer-shaped code path, even if
  it is off by default — a mild residual coupling, and PLC now knows the consumer exists.
- **PULL** (consumer reads PLC's on-disk open-format artifact; **PLC knows nothing**): the consumer
  reads a stable artifact PLC already writes for its own reasons. PLC changes zero and is completely
  ignorant of the consumer. **Strictly more decoupled**, and the shape that satisfies *mutual*
  independence.

**Prefer PULL wherever the artifact is (or can be made) a stable on-disk open contract.** Reserve
EMIT for artifacts that have no persistent path a consumer could read.

## Forbidden (the coupling smell)

- PLC reaching into a specific external product (a PLC command knowing about that product's UI or
  surface).
- Any PLC core step (review gate, progress visibility, continuity) *requiring* an external product
  to function — that silently re-narrows "works anywhere" to "works only if you also run X," the
  exact regression the file-based portable contracts exist to prevent.

## Cross-reference

- `SKILL.md` §"Self-update" — scope check (cross-project rules vs project `CLAUDE.md`); this boundary
  is the dependency half of that scope discipline.
- `references/self-update-flow.md` — when a rule belongs in the skill vs a project.
- `references/output-format.md` — the armed-optional `references-log:` key, the canonical EMIT-shape
  precedent (opt-in, off by default, MD always written first regardless).
