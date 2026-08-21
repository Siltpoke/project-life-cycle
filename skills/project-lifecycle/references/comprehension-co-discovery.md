# Comprehension Co-Discovery

> Anti-cognitive-offloading mechanism for the `/ship` cadence. Re-inserts the two acts AI silently removes — **generating** an answer yourself and **retrieving/reconstructing** it yourself — because those are what actually encode memory. Off by default. Cadence hook: `cadence.md` §"Comprehension Co-Discovery". Policy key: `output-format.md` (`comprehension: off | lite | full`).

## The problem it addresses

Heavy AI-coding use produces measurable **skill atrophy**: shipping systems but unable to explain their implementation, no longer sweating correctness ("errors are cheap, I can regenerate"), and passing one AI's output to another with no human anchoring truth. This is **cognitive offloading** — a documented phenomenon, not a motivation failure. The capacity needed to *oversee* AI-generated code (spotting when code is wrong and why) is exactly what offloading erodes.

## The mechanism

Memory is encoded by two effortful acts that AI does *for* you by default:

- **Generation effect** — producing an answer yourself encodes far more durably than reading a provided one. Reading a long AI output is *reading*, not generating → the shallow path → "I read it and forgot it immediately."
- **Retrieval practice (testing effect)** — effortful, successful reconstruction *strengthens* what's retrieved. AI handing you the finished answer means retrieval never happens, so nothing is strengthened.
- **Learning ≠ performance** (Bjork; Soderstrom & Bjork 2015) — the conditions that make you perform best *now* (smooth AI assist) often produce the *least durable* learning. The smoothness is the trap, not the reward.

The mechanism's only job: force *retrieval* (reconstruct/explain after) — the round below does exactly that; a *generation* step (predict before you see) is not part of it.

## The behavior (COMPREHEND)

One round, once per phase, after the diff is validated + quality-reviewed, before the PR checkpoint:

1. Harness reads the **real diff**.
2. Asks **one** *why*-style / *what-if* question that only makes sense if you've read the implementation.
3. User answers in their own words.
4. Harness checks the answer against the diff and says what's right, what's off, and **why**.
5. The round ends and is **discarded**. No score, no tally. Next phase = fresh.

## Two load-bearing constraints (getting these wrong makes it harmful, not just useless)

| Constraint | Why | Concretely |
|---|---|---|
| **Discovery, not judgment** | Judgment framing turns the round into a graded test — it feeds self-criticism instead of curiosity, and a mechanism that feels like a verdict gets disabled. Curiosity is the engine; self-criticism is the brake. Press the engine, never the brake. | "Interesting — you expected retry, it actually throws" (a gap to explore), never "you got this wrong / you don't understand async" (a deficiency). |
| **Per-round feedback, NO cumulative scoreboard** | Immediate right/wrong-with-reasons is *information* (has a payoff). Accumulating it into a running grade is what mutates into self-judgment. | Keep the in-round "right here / off there, because…". Drop any persistent tally. A milestone roll-up (if ever added) must be a *map of where to look next*, not a report card. |

Plus: **< 30s total per phase** (lighter to do than to delete), **gap ≠ blocker** (a weak answer never blocks the PR; it leaves an optional `[COMPREHENSION-GAP]` note), and **tamper-resistance via incentive, not enforcement** (the lazy path = the honest path; routing the question to another AI costs *more* effort than just answering, and there's zero penalty for a gap).

## Why naive gamification is the wrong fix

Adding extrinsic rewards (points / streaks / badges) **backfires** via the *overjustification effect* — it crowds out intrinsic interest, and people with higher initial interest are more susceptible. Rewards have a *controlling* function (undermines) and an *informational* function (signals competence, preserves motivation). Make every signal **informational, not controlling**: the strongest one for a systems-builder is *competence made visible* — the gap between your reconstruction and the diff closing over phases, a category of gaps shrinking to zero, no longer going blank when questioned. Replicate the flow conditions (immediate feedback + right-sized challenge + clear goal), not the scoreboard.

## The honest caveat (validate by hand first)

A tool can force the *action* (a pause, a question) but not the *engagement* (actually thinking). The validating first step is **not to build this** — it's to run the bare behavior by hand on one real task: before reading what the AI writes, write one line predicting how it'll do it; then read; then look at the delta. If the "oh — I thought X, it's actually Y" surprise feels *generative/curious*, harden it. If it feels like pure load, no design will save it — and that's worth knowing before writing code.

## References (verify figures against the preprint before quoting)

- Shen, J. H., & Tamkin, A. (2026). *How AI Impacts Skill Formation.* arXiv:2601.20245 — RCT: AI group scored ~17% lower on comprehension (largest gap on debugging); the differentiator was *how* AI was used (generation-then-comprehension / hybrid / conceptual-only scored high; full-delegation scored low), not *whether*.
- Generation effect (Slamecka & Graf 1978); retrieval practice / testing effect (Roediger & Karpicke 2006); desirable difficulties (Bjork; Soderstrom & Bjork 2015).
- Overjustification (Deci 1971; Lepper, Greene & Nisbett 1973; Deci, Koestner & Ryan 1999); informational vs. controlling rewards (Cognitive Evaluation Theory).
