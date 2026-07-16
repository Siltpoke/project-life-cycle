# Intent Gate — the workflow front door

The first thing that runs on **any fresh user request inside this workflow** — milestone kickoff *and* mid-phase ad-hoc instructions ("now fix this modal"). It turns a fuzzy human ask into a confirmed **intent**, then a precise executable **prompt**, before any code is written. Two jobs: **(a)** turn fuzzy dissatisfaction into a precise root-cause + explicit expectation; **(b)** verify the fix against an external oracle, not self-assessment (Stage 3).

It also doubles as the **machinery triage**: Stage 1's size axis decides whether the request earns the full Per-Phase Workflow, a per-task cadence, or just a one-liner — the cure for over-invoking the heavy path.

Flow: **classify → confirm intent → reframe+sharpen**. Feeds the brainstorm (step 1) for large work, or the cadence directly for a single task.

## Stage 1 — Classify (read-only)

Runs as a read-only pass in the main loop, NOT a subagent (cost). Discipline: no file writes before the reframe is confirmed.

| Axis | Cheap signal | Effect |
|---|---|---|
| **Ambiguity** (CLAM) | underspecified? multiple readings? | ambiguous → stage 2; **default is assume, NOT ask** |
| **Already-precise** | user already wrote a sharp spec | skip gate → one-line "I read this as X", go straight to the cadence |
| **Size** | trivial / medium / large | trivial+clear → skip the workflow, one-line "I read this as X", do it inline; medium → per-task cadence; large → seed brainstorm (step 1) |
| **Reversibility** | delete / migrate / publish / state change | irreversible → always confirm, even if 1 line |
| **Continuation** | same task as the active thread? | continuation → one-line restate only, no full ceremony |
| **Archetype** | what *kind* of work is this — make-new / make-production / delete-simplify / tune-PMF / keep-mature? | auto-infer from language → reshapes the chain Size routed into (which cadence steps fire + default oracle + diff direction). Default `Builder` (full baseline). See `#archetype--chain-shape-selector` |
| **AFK-eligibility** | at least one strong oracle (specified/differential/golden)? scope fence definable? no irreversible class? no design judgment? | all four hold → offer AFK mode (never auto-start); any fails → HITL as usual |

The AFK axis emits the same HITL/AFK vocabulary as `issue-breakdown.md` — one taxonomy, two scopes: request-level here, slice-level there. Eligible → the gate **offers** a loop contract ("this qualifies for AFK; want a loop contract?") and the user accepts or declines. **The gate never starts a loop on its own.**

The contract has 4 mandatory fields — **Goal** (machine-checkable, fence-scoped) / **Stop** / **Budget** (rounds + hours are a floor; a blank Budget is not a contract) / **Report** — and a **runtime** executes it. This skill does not ship one. **This axis is the judgment half, and it belongs here regardless**: deciding *whether* a request may run unattended is a question about the request, not about the runtime. A project with no runtime installed can still run this gate — it just answers "yes, and you'd need one."

## Stage 2 — Confirm intent

**Default aggressiveness = `assume`** (lay out assumptions; ask only when genuinely blocked).

1. Step-back: name the problem class — **bug / missing-capability / design-choice / scope-undefined**
2. Restate: "I read your intent as X"
3. **Default path (ambiguous but assumable):** lay out the specific assumptions filling the blanks → user one-tap approve or corrects only the wrong line.
4. **Exception path (ask):** ask **one** highest-Gain/Q question ONLY when a key ambiguity cannot be resolved by a reasonable assumption and getting it wrong would require redoing significant work. **When the user is a non-technical vibe coder struggling to describe the problem** (per `references/audience-tone.md`, `adaptive`/`plain` audience), the strongest "one question" is often not words: offer the screenshot/example cue instead of or alongside the text question — *"No worries — you can paste a screenshot, or point me at an example of what you WANT it to look like. That tells me more than words."* Skipped entirely under `audience: technical`.

**Brainstorm handoff:** large work → seed `superpowers:brainstorming` (Per-Phase Workflow step 1) with the confirmed intent. Do NOT re-ask intent downstream — the gate's confirmed intent IS the brainstorm seed. (Gate = first 10 seconds of a big job; full lifetime of a small one.) **At new-project / first-milestone kickoff for a non-technical audience** (`adaptive`/`plain`), run the repo-intake first — a plain-language "do you have a GitHub link?" with a what-is-GitHub explainer + an offer to create the repo _for_ them (prereq-gated `gh` ladder; account sign-up + `gh auth login` stay the user's steps; guide-link fallback) when absent, ensuring local git regardless, never blocking (`references/repo-intake.md`). Skipped under `audience: technical`. This runs once at kickoff, not on mid-phase ad-hoc requests.

**Early screenshot mention (once):** at the first project kickoff of a session, drop a single low-key note that this option always exists — *"Tip: if you ever can't put something into words, just send a screenshot or an example — works great."* One time, not per request. Governed by the `audience:` key (`adaptive`/`plain` only; skipped under `technical`). See `references/audience-tone.md`.

## Stage 3 — Reframe + sharpen

Self-refine (whole block, once): before surfacing to the user, critique the drafted prompt against the oracle ladder + the wrong-if clause — is the oracle the strongest available? is the root cause mechanism-level or still a symptom? is the scope minimal? Fix inline, then surface. One pass, not a loop.

```
[Problem]   symptom + expectation. Now X, should Y.
            wrong-if: this is wrong if <Z>          ← falsifiable clause
[Root cause (hypothesis)]   mechanism-level + evidence anchor
            (a log line / a specific var / a file:line).
            If unsure: "Suspect X — investigate before changing."
[Scope]     change only <files>; don't touch <rest>. Separate commit.
[Oracle]    name the STRONGEST available type (see Oracle ladder):
            specified > differential/golden > metamorphic > implicit.
[Verify]    reproduce <action> → screenshot/output → diff against oracle →
            paste evidence + "matches/differs". One thing at a time.
```

For a large request, this sharpened block becomes the seed the brainstorm + `user-story.md` expand on (numbered ACs = the formal version of the expectation + oracle). For a single cadence task, it becomes the task text + ACs handed to the implementer.

## Capture trigger — rationale signals

During the gate (or the brainstorm it seeds), a user often says more than an instruction — a
*why*, a quality bar, or a keep/drop call ("because the reviewer chokes on 800+ line diffs",
"good enough here means under 200ms", "keeping the legacy adapter — two client repos still
import it"). When one of these rationale signals fires (`cognition.md` §"When to capture"),
offer to capture it via the `/capture` flow **as a byproduct** of the gate — at most two
elicitation questions (`cognition.md` §"Elicitation"), never a form. This is the **primary**
capture surface; `/capture` run standalone mid-session is the manual complement.

**Sibling signal — reference-share.** The same gate also watches for a *reference-share*: when
the user brings in an offer-worthy external reference (a repo/paper/blog/tool/video/talk link, an
offline doc by local path / DOI such as a downloaded PDF, or an explicitly-shared AI-chat log /
screenshot / pasted note — illustrative, not exhaustive; the log header's `Type` enum is live)
for analysis, offer to capture it
into their global references-log — the gated y/n offer in `references/references-log.md`, armed
only by the user-global `references-log:` key (default off). This is a distinct capture surface
from the rationale `/capture` above: rationale → the project's cold intent-log; a shared
reference → the user's cross-project references-log.

## Oracle ladder

| Type | Use when | Example |
|---|---|---|
| **specified** | a spec / ticket / API contract / prototype exists | diff against §X of the spec, or `Prototype.html` |
| **differential** | a prior version or independent impl should agree | compare old build vs new; two impls of same function |
| **golden / snapshot** | a known-good output can be frozen | committed screenshot / recorded stdout / snapshot test |
| **metamorphic** | exact output unknowable, but invariants hold | `f(x) == f(transform(x))`; sort then reverse |
| **implicit** | nothing else exists — always available, weak | must not crash / leak / throw type error |

**No-oracle branch (explicit):** when none of specified/differential/golden applies and the request is a new capability, choose one of:
1. **manufacture** a golden/snapshot now (capture the intended output as truth), or
2. **flag low confidence** — "this is judged by vibes; accept that," or
3. **reclassify** — recognize "this isn't a bug, it's a missing Phase" and route it to brainstorming as a new phase rather than patching.

Treat a fabricated, confident-but-wrong oracle or root cause as worse than admitting there is none. The gate must be allowed to say "I can't form a hypothesis — investigate first."

## Archetype — chain-shape selector

`Size` (Stage 1) does the **machinery triage** — *how much* ceremony (trivial→inline / medium→cadence / large→brainstorm). `Archetype` is orthogonal: once Size has routed the work into a chain, archetype decides *what shape* that chain takes — which cadence steps fire, the default oracle, and the **diff direction** (add vs subtract). The two compose; archetype never overrides the size triage.

Five archetypes, modelled on the energy a piece of work carries (not on a job title or a person — a developer runs different archetypes by the hour). The baseline is **Builder = the current full chain**; the other four are deltas off it.

**Assignment = auto-infer + one-tap confirm**, re-evaluated every request (same `assume` discipline as Stage 2): the classifier guesses the archetype from language signals, states it ("reading this as a *Sweeper* task"), and the user corrects only if wrong. Per-request re-evaluation is the guard against archetype freezing into a fixed box — **it is a hat the work wears, not an identity the person or repo holds.** Default when nothing signals: `Builder`.

| Archetype | Language signal | Chain delta vs Builder | Default oracle | Diff direction | Journal tag |
|---|---|---|---|---|---|
| **Builder** (baseline) | "make this production-grade", "turn the prototype into a real feature" | full chain: user-story + TDD + acceptance verifier + validator + code-quality + security-where-relevant + PR | specified (story ACs) | add | `build` |
| **Prototyper** | "try", "spike", "throwaway", "explore", "brand-new idea", "churn a few" | **off**: user-story, acceptance verifier (1.5), validator (2), code-quality, 80% coverage, security gate. Output is **NOT directly mergeable to main** — a good prototype **re-enters as Builder** through the full chain. Touches secrets/auth → force reclassify (not a safe Prototyper lane) | implicit (state plainly: "judged by vibes, accept that") | add, marked disposable | `experiment` |
| **Sweeper** | "delete", "simplify", "unship", "remove", "optimize", "this is too slow/bloated" | **forbid new surface**; **on**: regression suite (deletion safety); **keep** validator (do existing ACs still pass after the simplification?); **off**: user-story | differential (behavior before == behavior after) | **subtract** — net-negative LOC OR perf-positive (the deterministic teeth, below) | `sweep` + record what was deleted + LOC delta |
| **Grower** | "iterate", "improve PMF", "A/B", "move the metric", "increase conversion" | metric-gated: every change needs a **metric oracle + rollback path** (feature-flag mandatory). Lighter architecture review, heavier measurement. **Keep** acceptance verifier + validator (still shipping to users) | differential / metric (A/B, before-after metric) | add, must be reversible | `grow` + record metric + hypothesis + rollback |
| **Maintainer** | "secure", "harden", "make reliable", "scale", "fix this bug" on a mature system | heaviest: security review **mandatory** (per `references/reviewer-brief.md` security lens; not where-relevant), regression suite **mandatory**, minimal diff, **forbid scope creep**. Force security pass even on a "BE-only" change | specified + regression golden | minimal | `maintain` |

Two load-bearing distinctions:

- **Prototyper output is a candidate, not cargo.** This is what separates it from "Builder but lighter" — it is loose enough to throw away, therefore it must not ship as-is. Promotion to main = a fresh Builder pass. (Cadence compression — `cadence.md` — is a *different* lever: it shrinks ceremony for a mechanical task that still ships. Prototyper shrinks ceremony for exploration that deliberately does not.)
- **Sweeper's teeth only police the direction**, not the correctness of the deletion. "Did it delete the *right* thing" is the differential oracle (behavior unchanged) + the validator. The teeth exist solely to stop work flying a `sweep` flag while quietly adding surface.

### The deterministic teeth — Sweeper diff-direction (the one enforced delta)

The four non-Builder archetypes are mostly prose deltas (the model applies them, same as it applies Size triage). **Exactly one delta gets deterministic enforcement** because it is the one genuinely-new signal the harness had no concept of before: diff direction. When a task's HEAD commit carries `Archetype: sweep`, the close gate (`close-gate.md`) asserts the change is net-negative LOC (code paths only — docs/journal/CHANGELOG additions excluded) **or** carries a human-written `SWEEP-PERF: <evidence>` escape line in the journal Plan-deviations (the LOC-went-up-but-perf-improved case, e.g. adding a cache). No `sweep` trailer → the check is inert; this adds zero friction to every other archetype. Full check + self-test in `close-gate.md` §"Sweeper diff-direction".

### Recording the label — the seam for later consumers

The chosen archetype is recorded inline, zero new files: a `Archetype: <tag>` trailer on the task's `feat(...)`/`fix(...)` commit **and** the same line in the journal entry header. This is deliberately the cheap half of the "mechanism + vocabulary" decision — the label is a greppable signal that downstream consumers (a future `builder-profile` archetype-mix readout; a future ROADMAP per-milestone archetype marker) read *without re-touching the gate*. Produce the signal here; consume it in a separate phase. Absent that downstream wiring, the trailer still earns its place: it makes `git log --grep='Archetype: sweep'` answer "what kind of work has this branch been."

## Policy & escape

- **Project key** in `CLAUDE.md`: `archetype: auto | <name> | off` (default `auto` — infer + one-tap confirm per request; `<name>` pins a default archetype for a repo whose work is overwhelmingly one kind, still per-request overridable; `off` = always Builder baseline, full backward-compat).
- **Project key** in `CLAUDE.md`: `intent-gate: ask | assume | off` (default `assume`).
- **Verbal bypass**: "skip gate" / "just do it" → execute without the gate this turn.
- **Auto-skip**: classifier detects an already-precise prompt → no ceremony.
- **Persistence**: trivial → not stored. Anything committed → the reframe block goes into the commit message or the iteration journal "Plan deviations"/context. Store inline with the code — zero new files, greppable.

## Relationship to the rest of the harness

The gate is the **front** of the pieces that already enforce precision deeper in the workflow — it doesn't replace them, it feeds them:

| Gate field | Downstream enforcer |
|---|---|
| confirmed intent | `superpowers:brainstorming` (step 1) |
| archetype verdict | `cadence.md` chain shape + `close-gate.md` §"Sweeper diff-direction" (the enforced delta) + the `Archetype:` commit/journal trailer |
| expectation / wrong-if | `user-story.md` numbered ACs |
| oracle | acceptance verifier (cadence 1.5) + validator (cadence 2) diff against the story |
| root-cause hypothesis | `diagnose-loop.md` (when the request is a bug) |
| restate-before-code | implementer pre-flight assumption block (cadence step 1) |
| language sharpening | `CONTEXT.md` glossary |
| AFK-eligibility verdict | the 4-field loop contract (Goal / Stop / Budget / Report) + this eligibility gate. A runtime executes the contract; this skill does not ship one |
