---
description: Run PLC's brainstorm research protocol on a single question OUTSIDE a brainstorm, and write a cited report to docs/research/. Dispatches parallel Tier-1/Tier-2 survey agents, synthesizes a cited recommendation, and (by default) runs a blind 2nd-agent verification. Produces a research artifact — it does NOT lock a decision or write the qa-log.
---

# /research — a cited answer to one question

Wraps PLC's existing research engine (`skills/project-lifecycle/references/brainstorm-research-protocol.md`)
as a standalone button. Use it when you want a **research-backed, cited answer to one question**
without opening a full brainstorm — the PLC-native replacement for reaching to an external
deep-research tool.

**Guts, not new capability:** this command adds NO new research logic. It runs the protocol's
Step 0 + steps 1-3, 6 (+4-5 unless `--quick`) and writes the result to a report file. The protocol
doc is the single source of truth — this command links to it, never duplicates it.

## When to use `/research` vs brainstorm

| You want… | Use |
|---|---|
| A cited answer to **one** question, as an artifact | `/research` |
| To **lock a design decision** (options → chosen, recorded in qa-log) | brainstorm (inside `project-lifecycle`) |
| To resolve **several** dependency-ordered decisions for a phase | brainstorm (Mode A/B) |

`/research` is single-question and produces a report. It does **NOT** lock a decision, does **NOT**
append to `docs/qa-log.d/`, and does **NOT** run the Mode A/B multi-question cadence. If you need a
decision on the record, run the question through brainstorm instead (or run `/research` first to
gather evidence, then lock it in brainstorm).

## Invocation

```
/research <question or topic>       # default: full rigor (incl. blind 2nd-agent)
/research --quick <question>        # skip the blind 2nd-agent; research + synthesize only
/research --tier1 <question>        # single-tier survey (BE / data-shape / architecture Q)
```

- **`<question>`** — free text. If omitted, ask once for the question (never a form, never a list).
- **`--quick`** — skips protocol steps 4-5 (blind 2nd-agent). The report is still fully cited, but is
  tagged **unverified (no 2nd-agent)** and its evidence-strength caps at 🟡 (never 🟢) — a `--quick`
  answer never claims industry-pattern confidence.
- **`--tier1`** — single advanced/professional tier only, for questions with no novice-audience axis
  (backend architecture, data shape, perf strategy). Default without a flag is **auto**: two-tier
  (Tier-1 advanced + Tier-2 novice) for UX / design-pattern questions, single-tier when the question
  has no novice-UX dimension. When in doubt, use two-tier.

The flags compose: `--quick --tier1` is valid — one skips the 2nd-agent, the other forces
single-tier; they are independent.

## Flow (delegates to the protocol — do not re-implement here)

Follow `references/brainstorm-research-protocol.md`:

0. **Language-first vocabulary sweep** (protocol §Step 0) — before framing, sweep the question's
   terms against the project's `CONTEXT.md`; sharpen any fuzzy / overloaded / undefined term first.
   Skip only for a trivial mechanical question with no domain-vocabulary surface. Asking a research
   question over fuzzy vocabulary produces citations framed against the wrong concept.
1. **Frame** the question (protocol §Step 1). If it fans into 3 sub-questions, surface the split and
   run the first one; tell the user the rest are separate `/research` runs.
2. **Dispatch parallel research agents** (§Step 2) — `general-purpose`, survey-only prompt (report
   what reference products/sources do + cite URLs; NO recommendation). Tier-1 + Tier-2 in parallel
   (single message, multiple `Agent` calls) unless `--tier1`/auto-single. Tier target lists come
   from the project's `CLAUDE.md` when present.
3. **Synthesize** a cited recommendation **in the shape §Step 3 defines** — read it there rather
   than from here; it is evidence-before-verdict and restating it is how the two drift apart.
4. **Blind 2nd-agent** (§Step 4) — SKIP if `--quick`. Fresh agent sees the options + the verbatim
   research, NOT your recommendation. **Compare** (§Step 5): on disagreement, surface both sides in
   the report — never silently pick.
5. **Evidence-tag** 🟢/🟡/🔴 (§Step 6). Bias toward downgrading. `--quick` caps at 🟡.
6. **Write the report** → `docs/research/YYYY-MM-DD-<slug>.md`, where `<slug>` is kebab-case of the
   first ~6 words of the question. If that path already exists (same day, similar question), append
   `-2`, `-3`, … rather than overwrite a prior research artifact. Report sections:
   - a one-line **disclaimer**: "Research report — NOT a locked decision. To lock, run this through
     brainstorm."
   - the synthesized recommendation (shape from step 3)
   - the 2nd-agent's independent conclusion + any disagreement (omit if `--quick`, and say so)
   - the evidence-strength tag
   - a **Citations** section: every source URL, deduplicated, ordered Tier-1 then Tier-2
7. **Surface** a short in-chat summary (recommendation + tag + one line why) + the report path.

## Hard rules (inherited from the protocol)

- **No citation, no send.** A synthesis whose `**Citations:**` block carries zero URLs is a malformed
  report — do not write it. If the research agents returned no citable sources (ISP block, no
  reference products for the topic), surface *"research returned no citable sources for <question>;
  here is what was attempted"* instead of emitting a confident citation-free report. (§Step 7,
  "no citation, no send".)
- **Survey before opinion.** Never write a recommendation the research agents didn't run first —
  `/research` with no dispatched survey is the banned "opinion alone" pattern.
- **Two-tier for UX questions.** Tier-1-only ships too-professional/unusable; Tier-2-only ships
  friendly-but-noncompliant. Single-tier is only for questions with no novice-audience axis.

## Not this command's job

- Locking a decision or writing `docs/qa-log.d/` — brainstorm owns that.
- Multi-question Mode A/B cadence — brainstorm owns that.
- Modifying the protocol doc — both `/research` and brainstorm read it; neither forks it.
