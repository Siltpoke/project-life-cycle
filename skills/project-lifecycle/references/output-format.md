# Output Format Policy — MD canonical, HTML opt-in companion

## Why this rule exists

Markdown is the default agent ↔ user format because it's cheap (token-light), diffable (audit-friendly), and machine-readable (subagent-consumed). But MD breaks down when:

- the artifact carries rich visuals (mockups, dataflow, side-by-side option grids)
- the audience is non-engineer / stakeholder / leadership
- the artifact is read once and shared widely

For those cases, HTML is a better human-facing format (per Thariq Shihipar's ["Using Claude Code: The unreasonable effectiveness of HTML"](https://claude.com/blog/using-claude-code-the-unreasonable-effectiveness-of-html)). The cost: 2-4x generation time, more tokens, noisier diffs.

**Resolution**: MD stays canonical and source-of-truth for every artifact. HTML is an opt-in *companion view*, co-committed alongside the MD and never replacing it. It is available for **3 artifacts**, offered across **4 asking moments** — the two counts are different things and are defined in the section below.

## Force-MD artifact list (no opt-in, no exceptions)

These artifacts MUST stay markdown. The cost-benefit is already decided:

| Artifact | Why force-MD |
|---|---|
| `docs/brainstorming-qa-log.md` (compiled hot monolith) + per-branch `docs/qa-log.d/<date>-<branch-slug>.md` fragments | append-only audit; diff is the audit trail; subagent reads on context recall. Fragments carry no TOC and compile into the monolith at milestone close (`references/retention.md` §"Fragment convention"); monolith direct-edit is the documented fallback for un-adopted projects |
| `iteration-journal.md` | append-only per-task audit; diff is the audit trail; AI reads every session start |
| `RESUME.md` | AI reads on every session start; diff drives "what changed" understanding |
| `docs/research/YYYY-MM-DD-mX.Y-resume-note.md` | one-shot consumption by next AI session |
| `docs/superpowers/plans/YYYY-MM-DD-phase-N-<slug>.md` | implementer + reviewer subagents read N times; token cost compounds |
| PR description (GitHub body) | GitHub does not render HTML in PR body — HTML escapes to noise. MD is the only valid format. Rich companions ship as separate HTML artifact + link. |
| backlog files | append-only deferred-decision log; diff matters |
| `CONTEXT.md` / `CONTEXT-MAP.md` | AI reads every session for vocabulary alignment; diff is the glossary audit trail; never visual |
| `docs/adr/NNNN-*.md` | sequential audit log; reviewers grep + read in plain text; visuals add no value |
| `docs/superpowers/specs/*-prd.md` | implementer / stakeholder reads; user-story list works in MD; subagent-consumed |

**Red flag**: any of these rendered as HTML → revert immediately.

## HTML opt-in — 3 artifacts across 4 asking moments

Two axes are counted here and they give different numbers, so both are named:

- An **artifact** is a file that can exist as an HTML companion **and has a defined asking moment**.
  There are **3**.
- An **asking moment** is a point in the workflow where the opt-in question fires. There are **4** —
  one artifact (spec/design) is offered at two different moments, which is the whole reason the
  counts diverge.

### What the count deliberately excludes

Other documents may be rendered as HTML companions without being part of this set —
`docs/ROADMAP.html` (`references/roadmap.md`) and one-off stakeholder cards are the current
examples. They are **ad-hoc**: generated on request, at no fixed point in the workflow, so there is
no moment to ask at and nothing to count. The set above counts *scheduled offers*, not *renderable
files*. Anything that later acquires a defined asking moment joins the count here — and nowhere
else.

**`html-policy` governs the ad-hoc class too, but only at one of its values.** `always-md` forbids
HTML everywhere, ad-hoc included. `ask` and `always-html` are both defined over *moments*, and an
ad-hoc artifact has none — so neither prompts for one nor pre-approves one. In practice: under
`ask` or `always-html`, an ad-hoc companion is generated when the user asks for it and never
offered unprompted. That is the whole rule; there is no fourth value.

| Artifact | Asking moment(s) | Companion file |
|---|---|---|
| 1. Spec / design doc | brainstorm exploration (SKILL.md step 1) · spec finalization re-opt-in (step 4) | `docs/superpowers/specs/…-design.html` |
| 2. Milestone-done summary | milestone close (step 10) | `docs/milestone-summary/YYYY-MM-DD-mX-summary.html` |
| 3. Mode B review sheet | the Mode B "ready for review" ping | `docs/qa-log-companions/<date>-<branch-slug>.html` |

The skill asks the user once per **moment** (unless `html-policy` is set):

### Artifact 1. Spec/design doc — 2 moments: opt-in at brainstorm exploration; re-opt-in at spec finalization

This is one artifact (`docs/superpowers/specs/YYYY-MM-DD-phase-N-<slug>-design.html`) with two trigger timings:

**1a. At brainstorm exploration** (SKILL.md step 1) — when `superpowers:brainstorming` produces parallel design options (mockups, dataflow comparisons, side-by-side option grids), prompt:

> Generate HTML companion for design exploration? (2-4x time, richer visuals + shareable link; MD design doc remains source of truth)

If yes: generate `…-design.html` alongside the MD. **Use the structural pattern + reusable skeleton in `references/html-companion-template.md` + `references/html-companion-skeleton.html`** — these capture the mandatory section list (customer voice / stakeholder lens / side-by-side comparison / mockup / state machine / decisions + disagreements / phase timeline / glossary / inline-clickable citations) and the shared CSS token palette so every project's HTML companion looks consistent.

**1b. At spec finalization (re-opt-in)** (SKILL.md step 4) — if user declined at 1a but now wants stakeholder-ready locked spec, re-ask:

> Generate HTML stakeholder view of locked spec? (renders mockups + dataflow + evidence-strength tags)

If yes: regenerate the same `…-design.html` from the now-locked MD using the template in `references/html-companion-template.md`. If already accepted at 1a, skip — the file already exists and can be refreshed in-place by a normal regen prompt.

The two timings exist because exploration HTML may be wasted if the spec drifts during post-decision revision. User may prefer to wait until lock-in.

### Artifact 2. Milestone-done summary — 1 moment: milestone close

At milestone close, prompt:

> Generate HTML milestone summary report? (rendered journal timeline + stakeholder-ready visuals + SVG diagrams of what shipped; MD canonical artifacts unchanged)

If yes: generate `docs/milestone-summary/YYYY-MM-DD-mX-summary.html`. Pulls from iteration-journal (including each phase's FACT entry — the retired handoff file's replacement, `references/journal-schema.md` §"The FACT entry") and smoke results. Renders timeline, key decisions, evidence-strength rollup, "what works now" feature list. Reuse the CSS token palette + badge taxonomy + footer pattern from `references/html-companion-template.md` so milestone summaries look consistent with spec/design companions.

**Note**: this is where iteration-journal becomes visual. The journal MD itself is force-MD (audit/diff-critical), but the milestone summary renders a timeline VIEW of the journal entries. No journal HTML file exists separately.

### Artifact 3. Mode B review sheet — 1 moment: the "ready for review" ping

When a Mode B brainstorm finishes and every question in the batch sits at `PROPOSED`, the ping that hands the batch back is the moment. Prompt:

> Generate HTML companion for this review sheet? (2-4x time, renders each question's options, both agents' criteria + picks, and the evidence-strength tags side by side; the Markdown fragment remains source of truth)

If yes: generate `docs/qa-log-companions/<date>-<branch-slug>.html` — same basename as the fragment it views, so the pair is obvious, but **in its own directory, deliberately outside `docs/qa-log.d/`**. Use the same template + CSS palette as the other artifacts (`references/html-companion-template.md`).

**Why not alongside the fragment.** `docs/qa-log.d/` is the one companion location that is actively managed — it is byte-capped over *every* file it contains and drained by a compile that reads `*.md` and then reports the directory emptied (`references/retention.md` §"Hot-doc caps" + §"Fragment convention" own both numbers; do not restate them here). A companion sitting in there would consume a large share of a budget meant for fragments, survive the drain that claims to have emptied the directory, and eventually trip a "this doc is not draining" escalation about a file the drain is told never to touch. The other artifacts have no such problem: they live in directories nothing drains.

**And the honest cost of moving it.** `docs/qa-log-companions/` is watched by *nothing* — no cap, no drain, and retention's coverage discovery matches `docs/**/*.md`, so an `.html` is outside its net by extension. That is a real trade, not a free win: it swaps "capped by the wrong cap" for "capped by no cap", and an unwatched append-only directory is precisely the growth path `retention.md` names as its observed failure mode. It is the right trade **today** — one path instead of edits to two gate scripts — and it stops being the right trade the moment these companions are generated routinely rather than on request. If that happens, give the directory a `hot-caps` entry rather than moving it back.

The companion is a **view**, never a source: it is generated from the fragment, never edited directly, and never the thing a decision is recorded into. When the fragment is compiled away at milestone close, its companion is stale by construction — delete it, or regenerate it against the compiled monolith.

Two things this opt-in does **not** change:

- **The fragment's force-MD status.** It stays in the table above; this artifact carves out no exception. A decision made while reading the HTML is written back to the fragment.
- **The "no complete sheet, no ping" hard rule** (`references/brainstorm-research-protocol.md` §"Mode selection"). The question is asked *about a sheet that is already complete*; an incomplete batch ships in neither format. Declining the HTML costs nothing — the Markdown sheet is what the ping delivers either way.

## Project-level overrides via `CLAUDE.md`

To avoid repeating the question every phase, set policy keys in project root `CLAUDE.md`:

```
html-policy: ask | always-md | always-html
smoke-mode: ask | self | guided
domain-docs: ./CONTEXT.md          # or ./CONTEXT-MAP.md for multi-context repos
comprehension: off | lite | full
audience: adaptive | plain | technical
close-gate: per-task | pr-boundary
archaeology: done YYYY-MM-DD | skipped   # one-time brownfield archaeology pass (references/archaeology.md)
archetype: auto | builder | prototyper | sweeper | grower | maintainer | off
second-agent-family: auto | same-family | foreign:codex | foreign:<name> | off   # brainstorm blind-2nd-agent lineage; default auto = same-family (byte-identical); see references/cross-family-review.md
retention: { hot-caps: {...}, archive-dir: docs/archive, distill: on }   # doc-retention overrides; see references/retention.md
references-log: <abs-path-to-global-repo> | off   # ⚠ user-global (~/.claude/CLAUDE.md) ONLY — cross-project personal path; see references/references-log.md
```

Defaults:
- `html-policy` = `ask` (skill prompts at each asking moment)
- `smoke-mode` = `ask` (skill prompts at smoke kickoff)
- `domain-docs` = unset (skill discovers `CONTEXT.md` / `CONTEXT-MAP.md` at repo root if present; explicit pointer beats auto-discovery for multi-context or non-root layouts)
- `comprehension` = `off` (anti-cognitive-offloading co-discovery round is opt-in; see `comprehension-co-discovery.md`)
- `audience` = `adaptive` (plain-language floor + passive escalation for non-technical users; see `references/audience-tone.md`)
- `close-gate` = `per-task` (where the human-blocking close approval sits; see `close-gate.md` §"Approval timing")
- `archaeology` = unset (skill offers the archaeology pass once at the adoption entry; recording an answer stops the question forever)
- `archetype` = `auto` (intent-gate infers the work's archetype per request + one-tap confirm; reshapes the chain Size routed into; see `intent-gate.md` §"Archetype")
- `second-agent-family` = `auto` (the brainstorm blind 2nd agent runs on the **same** AI family as the 1st agent — byte-identical to a repo that has never heard of this key). `foreign:codex` (or another armed family) makes it run on a different CLI family for lineage diversity; **armed-optional, never a hard dependency** — an un-armed adopter is unaffected. The value names the ROLE (`same-family` / `foreign:<name>`), not a model, so it is unambiguous regardless of which family the primary agent is. `off` disables **only** the foreign path, never the core Step-4 review. Every failure (not installed / not authed / spawn / parse / timeout / declined install) degrades silently to the same-family subagent with a visible qa-log status stamp. **Discoverability:** the key is offered once — at the first brainstorm step-4, if the key is **absent** (project + user-global) AND a foreign CLI is installed+authed, the skill offers to arm it (ask-once, like `archaeology`); **declining writes `off`**, and **any present value** (`auto` / `off` / `foreign:*`) suppresses the offer. A user with no foreign CLI, or one who set the key, is never offered. See `references/cross-family-review.md` §"Discoverability".
- `retention` = unset (skill defaults: RESUME 200L/25K, status 300L/30K, journal 100K, qa-log 50K; archive-dir `docs/archive`; distill on)
- `references-log` = unset (references auto-capture off; the key is **user-global** — it belongs in `~/.claude/CLAUDE.md`, NOT any tracked project `CLAUDE.md`, because it points at a personal cross-project path; see `references/references-log.md`)

Values:
- `html-policy: always-md` → skip all HTML opt-in questions; force MD everywhere
- `html-policy: always-html` → auto-generate the HTML companion for all 3 artifacts, at every one of the 4 moments; no question asked
- `smoke-mode: self` → AI gives the Track A smoke checklist path (`references/smoke-tracks.md`; the retired handoff file's §4 no longer exists — the checklist itself is the artifact) and waits for findings report
- `smoke-mode: guided` → AI walks user through each smoke stage step by step (recommended default for solo-developer projects)
- `comprehension: lite` → run the COMPREHEND co-discovery round once per phase (the MVP — `cadence.md` §"Comprehension Co-Discovery"); one *why*-question on the validated diff, discovery framing, non-blocking, no scoreboard, <30s
- `comprehension: full` → accepted as a synonym of `lite`; the COMPREHEND round runs once per phase either way.
- `audience: plain` → stay on the plain-language floor always; ignore fluency signals (inline gloss + screenshot fallback still apply; only escalation is off) (repo whose users are always non-technical). `audience: technical` → skip the tone layer entirely (no glossing, no escalation probing, no early screenshot mention — for a technical solo dev). Default `adaptive` runs the full layer. Full semantics: `references/audience-tone.md`
- `archetype: <name>` → pins a default archetype for a repo whose work is overwhelmingly one kind (e.g. a mature service → `maintainer`); still per-request overridable. `archetype: off` → always Builder baseline (full backward-compat, no archetype reshaping). The `auto` default infers + one-tap-confirms per request, which is also the guard against archetype freezing into a fixed box. See `intent-gate.md` §"Archetype"
- `close-gate: pr-boundary` → the per-task human-blocking approval is delegated to an independent read-only reviewer subagent; Task Close Reports are still written every task (audit trail, non-blocking); the human's blocking approval happens once per PR/merge, which MUST keep a human-written approval marker the AI cannot author (the self-certification hole stays closed). Deterministic `task-done`/`phase-done` gates are unchanged in both modes. Treat the flip as an experiment (catch parity + comprehension drift over 2-3 tracks; rollback = flip the key back). Full mechanics + attack surface in `close-gate.md` §"Approval timing"
- `retention:` — `hot-caps: {<doc>: <lines>/<KB> | none}` (per-doc cap override; `none` is the ONLY exemption route — no exempt lists), `archive-dir: <path under docs/>` (outside `docs/` = config error, warn + fallback), `distill: on | off` (`off` skips the milestone distill step silently). Human-facing kebab keys here; `/init-harness` mirrors them into the close-gate manifest's snake_case `retention` block. Full semantics: `references/retention.md` §"Policy keys"
- `archaeology: done YYYY-MM-DD` — pass ran on that date; never offer again. Self-heal: if the key is absent but `docs/adoption-snapshot.md` exists, write `done <snapshot generation date>`.
- `archaeology: skipped` — user declined; never offer again, but `/init-harness --archaeology` stays available (declined-but-reachable).
- `references-log: <absolute-path>` → arms the gated references auto-capture at brainstorm/research (`references/references-log.md`); the path must be an existing git repo (the user's global references-log). Set **once in `~/.claude/CLAUDE.md`** for all projects — never in a project `CLAUDE.md` (leaks a personal path + it's a cross-project concern). `references-log: off` or unset → feature dormant.

## Smoke interaction modes (Mode A vs Mode B)

At step 8 (PR + Track A smoke), AI asks unless `smoke-mode` overrides:

> Track A smoke mode? (A) Self-serve — I give you the checklist path, you run it alone and report findings back, or (B) Guided — I walk you through each stage step-by-step, you report per-stage.

### Mode A (self-serve)
- AI surfaces the Track A smoke checklist path (`references/smoke-tracks.md`) — the retired handoff file's §4 no longer exists
- User runs Track A alone in their own time
- User pings AI with consolidated findings list
- AI triages S1/S2/S3 and proceeds

### Mode B (guided, recommended)
- AI presents smoke stage 1, waits for user result
- User confirms pass or reports finding
- AI logs finding (if any), moves to stage 2
- Repeat until all stages done
- Better for catching mid-flow issues + interactive triage

Both modes still produce the same `docs/smoke-findings.md` artifact. Mode B just delivers it interactively.

## HTML generation guidance (when opt-in fires)

When AI generates an HTML companion:

- **Use `frontend-design:frontend-design` skill** for design-system consistency if available
- **Inline CSS / minimal external deps** — companion must work as a single self-contained file, openable in a browser locally (`open file.html`) or uploaded to S3
- **Mobile-responsive** — stakeholders may view on phone
- **Render SVG inline** for diagrams (not external images)
- **Include "Copy as prompt"-style buttons** for any interactive element that should feed back into Claude (per Shihipar's two-way interaction pattern), e.g., copy summary as prompt for the next session
- **Co-commit with MD** — both files in the same commit, MD listed first
- **Never delete or skip the MD** — HTML is companion, not replacement

## Anti-patterns

| Anti-pattern | Why bad |
|---|---|
| Rendering qa-log / journal / RESUME as HTML | Audit trail dies; diffs become unreadable |
| Plan as HTML | Subagent token cost × N dispatches |
| Inline HTML in PR description | GitHub escapes it; reviewer sees noise |
| Asking "MD or HTML?" for every artifact every phase | Decision fatigue; defeats the policy |
| Generating HTML companion without asking | Steals user time/tokens; violates opt-in contract |
| Skipping the MD because "HTML is better" | Source-of-truth fragmentation; audit dies |
| Setting `html-policy: always-html` then complaining about token cost | User chose the tradeoff |

## Origin

This policy was crystallized after reviewing Shihipar's HTML manifesto (May 2026) against the project-lifecycle skill's existing artifact set. Conclusion: HTML wins for human-facing rich visuals, but the skill's audit/diff/subagent-cost architecture means most artifacts must stay MD. The two artifacts opt-in **at the time** (spec/design + milestone summary) were exactly where HTML's payoff — visual exploration + stakeholder shareability — cleared the cost bar. The current set is above; this paragraph records where the policy came from, not what it is. Spec/design has two trigger timings (exploration vs finalization) because exploration HTML can be wasted if spec drifts; users decide which timing suits them.
