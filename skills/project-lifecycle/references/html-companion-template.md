# HTML Companion Template — Brainstorm / Spec / Design Exploration

> Reusable structural pattern for every HTML opt-in artifact `output-format.md` defines. That file is the single list of which artifacts exist and when each is offered — this one never restates that list as a count or a registry. The preset table below is keyed by artifact only to recommend a skin; it is not the registry, and it carries ad-hoc artifacts that the count deliberately excludes.
>
> **MD remains canonical** in every case. HTML is a generated companion view — same content, richer presentation.

## Goals

The HTML companion exists to do three things the MD can't:

1. **Bridge non-engineer audiences** — operators, stakeholders, customers, regulators read it without parsing markdown tables / code blocks.
2. **Show concrete examples side-by-side** — when the spec offers 2-N options, render each option with realistic example content so the reader compares visually.
3. **Surface every research citation as a clickable link** — not a code reference buried at the bottom.

## Audience principle (zero-domain-knowledge mode)

Assume the reader has no domain knowledge. Operator language ≠ engineer language ≠ stakeholder language. Translate:

- Industry acronyms → spelled out at first use + listed in the Glossary section at the end.
- Abstract phrases like "industry pattern" → name the actual reference products / standards in plain prose.
- Schema decisions → describe what changes in the database when the user performs the action (no SQL inline).
- Tradeoffs → include a Real-world scenario callout under each option showing what a real user does.
- Reasoning behind a decision → "Why box" callout linking back to the original pain point captured in §0.

If the project's primary operator reads a non-English language (per project `CLAUDE.md` `language` key or recent user messages), generate the HTML body text in that language. Keep technical jargon verbatim (acronyms, code identifiers, regulation names) — the audience must learn those terms anyway, not translate them. **This guidance is per-project — this template + skeleton remain English-only because they live in a cross-project skill.**

## Required sections (always include)

Number with the §N notation. The skeleton at `html-companion-skeleton.html` ships these in order; deviate only per the "When to deviate" section below.

1. **§0 Customer voice (verbatim)** — direct quotes from the operator / user / interviewee that motivated this phase. Verbatim, in the original language. The whole spec must trace back here.
2. **§1 Stakeholder lens / gatekeeper view** — what does the downstream reviewer / auditor / payer / regulator / approver / customer see? Concrete walkthrough: their checklist, what they look for, why each item exists. Examples by domain:
   - Regulated industry: the auditor opens the document and looks for N required fields.
   - Consumer product: the user opens the app at the worst possible moment — what do they see?
   - B2B SaaS: the admin needs to set up SSO — what's the click path?
   The point: render the gatekeeper's mental model so every subsequent product decision traces to "this serves that gatekeeper."
3. **§2 Side-by-side option comparison** — for any 2-N choice in the spec, render each option with realistic example content. Same input rendered N ways. The reader compares visually.
4. **§3 to §M Mechanic explanations** — one section per non-trivial rule: pricing logic, eligibility check, state transition, data flow, policy boundary. Each carries:
   - Table or diagram of the rule.
   - "Why box" callout (see below) tying the rule back to a pain quote in §0.
5. **§M+1 Form/UI mockup** — at least one rendered HTML mock of the primary surface. Annotated:
   - Pre-filled fields: amber background, with provenance note ("from prior session 2026-04-22").
   - Placeholder fields: italic muted, "required, still empty".
   - Error fields: red background.
   - AI / suggestion rows: ✨ accent text describing what the assistant proposes.
6. **§M+2 State machine / before-after** — if the artifact involves a state transition (draft→signed, anonymous→authenticated, pending→approved, free→trial→paid), render both states with: what the user sees + what the database does + what audit row is written. Side-by-side cards with arrows between them.
7. **§M+3 Decisions table + disagreement comparison**:
   - Full locked-decisions list with evidence-strength badges (🟢 / 🟡 / 🔴).
   - Then any 1st-agent vs blind 2nd-agent disagreements as side-by-side option cards. Recommended option marked by green halo + "✅ Recommended — short reason" small caption. Each option gets a Real-world scenario callout (see below).
8. **§M+4 Phase timeline** — N steps with the current step highlighted, future steps dimmed. Each step: 1-sentence summary of scope.
9. **§M+5 Cross-phase carryover** — what is reused from prior phases (data models, gates, conventions, F-findings, deferred decisions).
10. **§M+6 Operator next steps** — numbered list: what the operator does after closing this HTML.
11. **§M+7 Glossary** — definitions for every technical term used. One short paragraph per term, written for the zero-domain-knowledge audience. Sorted by appearance order in the document, not alphabetically.
12. **§M+8 Citations index** — every research source as a clickable link, grouped into collapsible `<details>` categories. Categories vary by domain — typical groupings are: domain references / reference products / authoritative standards / tooling docs.

## Optional frontmatter (design-system tagging)

When a project has generated more than one HTML companion, tag each artifact with YAML frontmatter so future generators can match the right preset and skin:

```yaml
---
node: design        # design | finalization | milestone-summary | stakeholder-deck
audience: operator  # engineer | operator | stakeholder | regulator | leadership
design_system: default-cool   # default-cool | kami-parchment | swiss-grid | xhs-pastel
generated: 2026-05-27
source: docs/superpowers/specs/2026-05-27-phase-N-<slug>-design.md
---
```

`design_system` is advisory — the skeleton ships `default-cool` (the palette in `Style tokens` below). Switch presets per the recommendation table in `Style preset recommendations` below. Pattern borrowed from `nexu-io/html-anything` SKILL.md frontmatter convention (`mode` / `scenario` / `design_system` / `preview`) — adapted to the structural-spec audience.

## Style tokens (consistent across projects)

The CSS token palette below should be reused for every project's HTML companion so the operator's eye learns the palette once:

```css
:root {
  --bg: #fafaf9;          /* page background */
  --surface: #ffffff;     /* card background */
  --ink: #18181b;         /* primary text */
  --muted: #71717a;       /* secondary text */
  --line: #e4e4e7;        /* borders / dividers */
  --accent: #4f46e5;      /* primary action / link */
  --accent-soft: #eef2ff; /* accent background */
  --green: #16a34a;       /* recommend / strong evidence / success */
  --green-soft: #ecfdf5;
  --amber: #d97706;       /* pending / mixed evidence / warning */
  --amber-soft: #fef3c7;
  --red: #dc2626;         /* blocked / fail / denied */
  --red-soft: #fee2e2;
  --teal: #0d9488;        /* informational secondary tag */
  --teal-soft: #f0fdfa;
  --shadow: 0 1px 2px rgba(0,0,0,.04), 0 4px 16px rgba(0,0,0,.06);
  --radius: 10px;
}
```

Use system fonts only — never load external font files (slow + privacy). For projects with CJK content add the CJK fallback chain at the front of `font-family`:

```css
font-family:
  -apple-system, BlinkMacSystemFont,
  "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei",   /* CJK fallbacks if applicable */
  "Inter", system-ui, sans-serif;
```

## Style preset recommendations (per artifact)

`default-cool` works for most artifacts. Switch presets when audience or read-length warrants. All presets share the same CSS token names — only the values change, so swapping is a one-block edit.

| Artifact | Recommended preset | Why |
|---|---|---|
| spec/design exploration (§0–§M+8) | `default-cool` | Neutral indigo accents; long structured technical read |
| Spec finalization stakeholder view | `swiss-grid` | Tight grid + single saturated accent; signals "approved & formal" to leadership |
| Milestone summary report | `kami-parchment` | Warm-parchment ground (`#f5f4ed`) + ink-blue accent + single serif; calmer long-form reading for executive recap, inspired by `tw93/kami` / `nexu-io/html-anything` `doc-kami-parchment` skill |
| Mode B review sheet | `default-cool` | Same long structured technical read as spec/design, and the reader moves between the two; a different skin would read as a different kind of document |
| Customer-facing stakeholder card | `xhs-pastel` | Pastel surfaces + soft shadow; works as standalone share card if exported via PNG |

Presets above are **palette + font-family + radius/shadow swaps only**. Section structure, mandatory callouts (`why-box`, `scenario`), badge taxonomy, and citation discipline are unchanged across presets — they are the structural contract of this template.

If a project wants a new preset, define it as a CSS `:root` token block + a one-line description of when to use it, drop it into project `CLAUDE.md` under `html-presets:`, and reference it via the `design_system:` frontmatter key. Do NOT redesign the section list or badge taxonomy.

## Quality floor (anti-AI-slop hard rules)

Four constraints every generated HTML companion must satisfy. They exist because LLM-default HTML drifts into low-contrast, generic-stock, made-up-data territory unless these are enforced explicitly. Adapted from the discipline embedded in `alchaincyf/huashu-md-html` and surfaced by `nexu-io/html-anything`:

1. **CJK-first font stack when project language is CJK** — `"PingFang SC"`, `"Hiragino Sans GB"`, `"Microsoft YaHei"` BEFORE any Latin fallback. Latin-first stacks produce broken CJK glyph metrics (vertical alignment + line-height + punctuation kerning all wrong). Enforce via the snippet in `Style tokens` above; do not let the generator silently swap to `Inter, sans-serif` as the first family.
2. **8 px baseline grid** — every vertical spacing value (`margin`, `padding`, `gap`, `line-height` translated to px) is a multiple of 8 px (or 4 px for half-step). No `13px` margin, no `1.7em` line-height that lands on a half-pixel. Reason: arbitrary spacing produces the "almost right but uneasy" look that signals AI generation; grid-snapped spacing reads as designed.
3. **Contrast ≥ 4.5 for body text, ≥ 3.0 for ≥18 px** — WCAG AA minimum. The default-cool palette satisfies it (`--ink #18181b` on `--bg #fafaf9` = 18.7 : 1; `--muted #71717a` on `--bg` = 5.0 : 1 — safe for body). If switching presets, re-check the muted color against the new background. Reason: low-contrast muted text is the most common AI-generated readability failure.
4. **Must-use-real-data rule** — every example, mockup field, and side-by-side comparison uses real values from `docs/brainstorming-qa-log.md` or the verbatim customer voice in §0. No "Lorem ipsum", no "Acme Corp", no "user@example.com" placeholders, no fabricated numbers. If real data is unavailable for a slot, mark the slot with `[needs example from operator]` in the same amber Why-box style — surface the gap, do not paper over it. Reason: fabricated examples train the reader to distrust the artifact and let real issues hide behind plausible-looking filler.

A companion that fails any one of these rules is not "shippable" — regenerate with the failing constraint enforced in the prompt, or hand-edit the failing section before publishing.

## Badge taxonomy (evidence strength + state)

Reuse these badges across every project's HTML companion:

```html
<span class="badge green">🟢 strong</span>     <!-- ≥3 authoritative refs agree -->
<span class="badge amber">🟡 mixed</span>      <!-- industry split, partial evidence -->
<span class="badge red">🔴 inference</span>    <!-- AI-only, highest review priority -->
<span class="badge teal">label</span>          <!-- domain-neutral informational tag -->

<span class="badge green">APPROVED</span>      <!-- state: locked / live / signed -->
<span class="badge amber">DRAFT</span>         <!-- state: in progress -->
<span class="badge red">BLOCKED</span>         <!-- state: denied / failed -->
```

CSS:

```css
.badge { display: inline-block; padding: .12rem .55rem; border-radius: 6px;
         font-size: .72rem; font-weight: 700; letter-spacing: .02em; }
.badge.green { background: var(--green-soft); color: var(--green); border: 1px solid #86efac; }
.badge.amber { background: var(--amber-soft); color: var(--amber); border: 1px solid #fcd34d; }
.badge.red   { background: var(--red-soft);   color: var(--red);   border: 1px solid #fca5a5; }
.badge.teal  { background: var(--teal-soft);  color: var(--teal);  border: 1px solid #5eead4; }
```

## "Why box" callout (mandatory after each mechanic explanation)

Every mechanic section ends with an amber "Why box" tying the rule back to a customer pain quote captured in §0. Format:

```html
<div class="why-box">
  <span class="why-label">So what?</span>
  <strong>One-line summary of the product impact.</strong> Optional 1-2 sentence
  detail. Optional inline research links to supporting refs.
</div>
```

CSS:

```css
.why-box {
  background: #fffbeb; border: 1px solid #fcd34d; border-radius: 8px;
  padding: .8rem 1rem; margin: .8rem 0;
}
.why-box .why-label {
  font-size: .72rem; font-weight: 700; letter-spacing: .08em;
  color: var(--amber); text-transform: uppercase;
  display: inline-block; margin-bottom: .25rem;
}
```

## Inline citation discipline

Every research-derived claim in the HTML companion must:

1. Be a clickable `<a href="…">…</a>` link to the source — not a footnote marker like `[1]`.
2. Appear directly in the prose where the claim is made — not at the bottom only.
3. Also be aggregated in §M+8 Citations index, grouped by category, inside `<details>` collapsibles.

This means a single source may be linked 2-3 times across the document (in prose where claimed + in the index). That's intentional — the zero-domain-knowledge audience will not scroll to a separate citations table.

## Real-world scenario callout (under each option in disagreement comparisons)

For every option in a disagreement card, add a Real-world scenario callout showing **a concrete situation where this option matters**. Format:

```html
<div class="scenario">
  Real-world scenario: [one-sentence concrete situation — who does what, when, why].
</div>
```

Pick an emoji prefix that fits the project's tone (📅 / 📌 / 🎯 / 💼 / 📞 — choose one per project and use it consistently).

CSS:

```css
.disagree .opt .scenario {
  font-size: .82rem; color: var(--muted);
  padding: .55rem .6rem; background: #f9f9fb;
  border-radius: 5px; margin-top: .4rem;
}
```

The recommended option also carries `class="opt rec"` (green halo) + a small `<small style="color: var(--green);">✅ Recommended — short reason</small>` line at the bottom.

## Mobile responsive

Use `grid-template-columns: 1fr 1fr 1fr` for desktop three-column comparisons; at `@media (max-width: 720px)` collapse to single-column `1fr`. Don't ship a separate mobile build — the same HTML serves both.

## Document indexing

For long HTML companions (>10 sections) include a clickable TOC at the top after the subtitle. Same anchoring rules as `document-indexing.md` — every `<h2>` and `<h3>` gets an `id`, TOC `<a href="#…">` links to them.

## What NOT to include

- **Build tooling** — no webpack, no SCSS, no JS framework. Single self-contained HTML file with one `<style>` block.
- **External font / icon loaders** — system fonts only; emoji for icons.
- **JavaScript beyond native `<details>` collapsibles** — no SPA, no clickable filters, no charts. The HTML is read top-to-bottom.
- **Tracking / analytics / external scripts** — privacy + repo-clean reasons.
- **Tailwind / Bootstrap / utility CSS frameworks** — write the small set of classes inline. The skeleton uses ~30 unique classes total.

## Footer

Every HTML companion ends with a footer linking back to the canonical MD source and any sibling research docs:

```html
<div class="footer">
  Markdown source:
  <a href="design.md"><code>docs/superpowers/specs/YYYY-MM-DD-…-design.md</code></a>
  · Full research:
  <a href="research.md"><code>…-research.md</code></a>
  · Verbatim Q&amp;A:
  <a href="../../brainstorming-qa-log.md"><code>docs/brainstorming-qa-log.md</code></a>
  · Generated YYYY-MM-DD by the <code>project-lifecycle</code> skill. MD is source of truth.
</div>
```

## Reusable skeleton

The skeleton lives at `references/html-companion-skeleton.html` in this skill. Copy it as the starting point for any spec/design companion, fill in the `<!-- TODO -->` blocks per the section list above, and translate body text to the operator's preferred language (if non-English) while keeping technical jargon verbatim.

## When to deviate

- **Audience is a technical co-engineer**: drop the glossary, expand the schema section, deeper code-block usage.
- **Audience is leadership / investor / regulator**: keep the glossary, hide implementation details, expand the stakeholder-lens section.
- **Single-option spec (no comparisons)**: skip §2 side-by-side; keep mockup + state machine + decisions table.

In every case the §0 customer voice + §M+7 glossary + §M+8 citations remain mandatory.
