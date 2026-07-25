# Review Record — making AI review trustworthy and auditable

The agent that writes code must not be the agent that judges it — and the human who merges must be able to audit BOTH sides of that conversation. This reference defines (1) the bias constraints on how reviewer subagents are dispatched, (2) the **review record**: two companion PR comments (reviewer's verbatim report + builder's per-finding response), and (3) what happens between a finding and a fix.

Everything here was extracted from real incidents on a real project's first `pr-boundary` track (two independent review rounds; each caught one real issue; one reviewer-suggested fix snippet itself introduced a real data-loss bug that the second round caught) plus the published evidence on LLM self-review bias.

## Why a separate reviewer is necessary but not sufficient

Self-review bias decomposes into three mechanisms with separate evidence:

1. **In-context ownership** — judging work in the conversation that produced it. The largest component, and it *amplifies* over iterations ([Xu et al., ACL 2024](https://arxiv.org/abs/2402.11436)). A fresh-context reviewer subagent eliminates this term entirely.
2. **Style familiarity** — judges favor output that is low-perplexity *to them*, regardless of authorship labels ([Wataoka et al. 2024](https://arxiv.org/html/2410.21819v1); [Panickssery et al., NeurIPS 2024](https://arxiv.org/abs/2404.13076)). Blinding does not remove this.
3. **Family-level taste correlation** — same-vendor judge/author pairs show systematic inflation and ~correlated errors ([Play Favorites 2025](https://arxiv.org/abs/2508.06709); [Correlated Errors 2025](https://arxiv.org/pdf/2506.07962)).

So: a separate same-family reviewer removes the biggest bias term but keeps a **residual leniency floor**. The dispatch constraints and the record below exist to compress that residue and to keep the human auditor in a position to catch what slips through.

## Reviewer dispatch constraints (all reviewer subagents: validator, code-quality, final-pass)

1. **Fresh context, always.** Never review in the session/context that wrote the code. (Kills mechanism 1.)
2. **Read-only tools** (Read/Grep/Glob + test-running Bash). Hard constraint, not prompt text: a reviewer that can edit absorbs findings into silent fixes and the audit trail dies.
3. **Tier asymmetry.** Set the reviewer's model explicitly; prefer reviewer-tier ≥ implementer-tier. Same-tier-reviews-same-tier is the maximally correlated configuration; larger models self-bias less and critique better ([CriticGPT](https://arxiv.org/pdf/2407.00215)).
4. **Refute-first, verdict-last.** The output schema starts with "the strongest case against this diff / likely failure modes", then per-criterion analysis, then findings; any verdict field comes LAST. Reasoning-before-verdict measurably improves judge quality; verdict-first invites rationalization.
5. **Evidence gate: every finding cites `file:line` + a quoted snippet.** A finding that cannot quote the code it indicts is discarded before triage ([CriticGPT](https://openai.com/index/finding-gpt4s-mistakes-with-gpt-4/) — grounding is the main hallucination/nitpick control).
6. **Verdict is computed, never self-declared.** Reviewers output per-criterion pass/fail + severity-tagged findings; "approved / not approved" is derived by the controller from those fields, never taken from a reviewer-stated boolean. **The general rule: the controller counts open findings in the active severity scale's top two tiers as merge-blocking — whatever the scale.** (Same principle as the security rule: routing-critical booleans come from code, not from the LLM.) Default scale for reviewer findings is **CRITICAL / HIGH / MEDIUM / LOW** (top two = CRITICAL/HIGH); re-grades (builder response) stay on the active scale. Other established scales (e.g. the Copilot stand-in's CRITICAL/IMPORTANT/MINOR/NIT in `copilot-review-loop.md`) follow the same top-two rule. Once severity is settled, fix-vs-defer follows `defer-vs-fix.md` (mapping: CRITICAL→Critical, HIGH/MEDIUM→Important, LOW→Minor; defer-vs-fix's Forward-looking is a finding *category*, not a severity tier — a forward-looking finding carries its own severity and maps through the same table) and PR-level findings map to the S1/S2/S3 tiers of `findings-tier.md`.
7. **Pre-seeded suspicions are allowed, AFTER an unanchored pass.** The dispatcher may inject specific worries ("verify the cleanup path can't delete a file the guard skipped") — live experience shows these catch real bugs — but the prompt must require one unanchored full-diff pass FIRST, then the seeded checks, so the reviewer's attention isn't anchored to only what the writer already suspects.
8. **Different lenses, not clones.** When multiple reviewers run, give each a distinct lens (correctness-vs-promise / security / code-quality), distinct prompt, ideally distinct tier. N identical reviewers vote their shared blind spots ([PoLL 2024](https://arxiv.org/abs/2404.18796)).

## Termination contract — when the review gate is satisfied

The review gate has **three** outcomes, not two. Reading "no findings surfaced" as "reviewed and
clean" is the defect this contract exists to remove: absence of findings is not the same
event as an affirmative clean review, and the gate must be able to tell them apart.

The gate is the **independent general-purpose reviewer** (dispatched per `reviewer-brief.md` under
the constraints above). An external bot (Copilot, per `copilot-review-loop.md`) is **advisory
input only** — its output feeds the FINDINGS state but never produces a PASS and never satisfies
the coverage window. See that file's STATUS banner for why (a present review object is not a
performed review — 7/7 quota-failure objects here would otherwise read as clean).

| Outcome | Condition | What it licenses |
|---|---|---|
| **FINDINGS** | An affirmative reviewer report with ≥1 open finding in the active scale's top two tiers (constraint 6). | The fix loop: address each, one review-fix = one commit, then re-dispatch a fresh pass over the new commits. |
| **PASS** | An **affirmative** computed clean verdict (a real per-criterion report with **zero** open top-two-tier findings — constraint 6, never a reviewer-stated boolean) **AND** an empty coverage window (the recorded dispatch-SHA reaches HEAD: `git log <review-SHA>..HEAD` is empty). | Merge. |
| **UNVERIFIED** | Anything else: the reviewer produced no parseable per-criterion report, produced nothing, crashed/failed to spawn, the coverage window is non-empty (commits after the last review SHA), or only an advisory bot signal exists. | **Nothing on its own.** Never silently a PASS. |

**PASS requires an affirmative report, not the absence of one.** An empty reviewer output, a timed-
out dispatch, or a bot failure body are all **UNVERIFIED** — identical to silence. This rule applies
to the independent reviewer too, not only to Copilot: removing the flaky bot
does not remove the silence risk, it relocates it to the reviewer you now depend on.

**Closing a phase under UNVERIFIED requires an explicit, logged `SKIP:`** — the same escape-hatch
shape every other absent artifact uses (`close-gate.md`: *"a skip is legit only with a `SKIP:`
line"*; *"State #1 makes skips obvious; gate #2 makes them impossible to hide"*). Write
`SKIP: reviewer-unverified — <reason>` in the journal "Plan deviations" section. No `SKIP:` line →
the phase does not close. A silent empty result is **never** a pass. The human owns that decision;
the machine's job is to make the skip un-hideable, not to forbid it — a hard block would only push
a pressured builder to fabricate the "verified" signal, reintroducing the self-certification this
whole file guards against.

**The coverage window is the authoritative, un-spoofable half of PASS** (see §"Coverage window"
below): the recorded review-SHA at dispatch vs `HEAD`, computed by `git log` range emptiness —
**never** a SHA string pasted into a writer-editable file (that is a spoofable proxy, the exact
self-certification class this file warns about).

## The review record — two companion PR comments

In `pr-boundary` mode (and on any PR where reviewer subagents ran), the PR carries the full bidirectional review conversation. Both files are drafted to the session scratchpad first (normal draft-first workflow, `references/pr-comment-template.md` §"Draft-first workflow" — the draft dies with the session, the posted PR comment is the durable record), then posted via `--body-file`.

### Comment A — review verbatim

`<session scratchpad>/YYYY-MM-DD-<slug>-review-verbatim.md`

- **Scope header per round**: commit range reviewed (`merge-base..<SHA>`), what the reviewer could see (working tree vs committed), method (read code / ran tests / exercised app), and an explicit **"not reviewed"** list — the honest negative space.
- **The reviewer's report AS RETURNED — the writer must not edit, condense, or re-synthesize it.** A writer that summarizes its own auditor's reasoning is a self-serving channel: the live incident was a "verbatim" comment that silently shrank the reviewer's reasoning by ~60%, dropping exactly the exploratory traces the merger needed. Mechanism: save the subagent's final report to the draft file untouched; long reports go inside `<details>` folds, never get shortened.
- **Dispatch prompt provenance**: the prompt each reviewer was dispatched with (or its draft-file path), folded. Auditing a review requires knowing what it was asked — including which suspicions were pre-seeded.
- One section per round (mid-branch round, final-pass round, …), newest last.

### Comment B — builder response

`<session scratchpad>/YYYY-MM-DD-<slug>-builder-response.md`

Per finding, in the reviewer's order:

```markdown
**[SEVERITY] <finding title>** — Agree / Disagree (+ why, in one or two sentences)
- **Re-graded severity**: <severity by actual impact, if different — reviewer labels are
  calibration-noisy (live: pre-existing low-impact issues tagged HIGH); triage re-grades
  by impact, recorded here, never silently>
- **What I changed**: <commit SHA + one line> | nothing
- **What I deliberately did not change**: <+ why>
```

Closing **Net judgment** paragraph: overall disposition + anything routed to "Reviewer asks" for the human. This is what lets the merger audit *whether each fix was premised on a correct reading of the finding* — the disposition summary alone cannot.

## Between finding and fix

1. **Routing split.** Mechanically verifiable findings (a RED test or deterministic check can prove them) → the coding agent fixes. Judgment calls (design taste, semantics tie-breaks, "should this persist?") → report-only: they go to the PR's "Reviewer asks" layer for the HUMAN to decide. This is the guard against "the reviewer was wrong and the code drifted to match it".
2. **One review-fix = one commit.** Each accepted finding's fix is an independent commit referencing the finding. Wrong premise → revert exactly one. (Violation note: this rule was stated and then fixes were folded/batched anyway — treat it as a checklist item at commit time, not an intention.)
3. **The reviewer's suggested fix code is untrusted input.** Adopt the *finding* (the problem statement); derive the fix yourself from the surrounding code and ship it with a test. Incident: a reviewer-suggested guard snippet, pasted nearly verbatim, created a partial-state interaction with existing cleanup logic — silent loss of a user-visible artifact — caught only by the next round. Never paste reviewer snippets.
4. **Review-fixes are unreviewed code → final-pass is mandatory.** After fixes (and any other post-review commits: hooks, config, docs that gate behavior), dispatch a fresh final-pass reviewer scoped to everything the previous round did not see. The live track's round 2 caught a real MEDIUM introduced by a round-1 fix — this step has already paid for itself once.

## Coverage window — the mechanical check

Every review round's scope header pins the SHA it reviewed up to. **Any commit after the last review SHA is unreviewed code** — a real branch shipped its close-gate hook commit unreviewed until someone happened to ask. Before merge: `git log <last-review-SHA>..HEAD` must be empty, or those commits get a final-pass round. This is greppable/deterministic — projects using the close gate can wire it as a phase-mode check. Caveat for the wiring: "review-verbatim draft contains the branch HEAD SHA" alone is a **spoofable proxy** (a writer can paste the SHA without a review covering it — the exact self-certification class this file warns about); the authoritative check is the `git log` range emptiness against a review SHA recorded at dispatch time, not a string in a writer-editable file.

## Catch-parity ledger (pr-boundary experiment data)

The `close-gate: pr-boundary` experiment (`close-gate.md` §"Approval timing") needs its two signals recorded, not remembered. Append one line per track to the review-verbatim draft's footer:

```
catch-parity: track N — rounds=2, real-findings=1H+1M, fix-introduced-bugs-caught=1, human-merge-time-finds=0
```

2-3 tracks of these lines are the rollback/keep evidence.

## Anti-patterns — STOP

- **Review runs only in the writer's session** ("I'll just re-read my diff") → not a review; bias mechanism 1 at full strength. Dispatch a fresh subagent.
- **Writer condenses/paraphrases the reviewer's report for the PR** → self-serving channel; post verbatim, fold if long.
- **Pasting the reviewer's suggested code** → untrusted input; adopt the finding, re-derive the fix, add a test.
- **"All findings fixed" 30 seconds after the report, no disposition recorded** → triage happened invisibly; the builder-response comment is mandatory, including re-graded severities and deliberate non-fixes.
- **Reviewer-stated "APPROVED" treated as the gate** → verdicts are computed from per-criterion fields + open-severity counts by the controller.
- **Commits after the last review round merged without a final pass** → unreviewed code in a "reviewed" PR; check the coverage window.
- **Three identical reviewers as a "panel"** → same blind spots, three votes; use distinct lenses/tiers or one good reviewer.
