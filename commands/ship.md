---
description: Ship one vertical-slice feature end-to-end via the project-lifecycle factory chain. Chains researcher → story → spec → BE builder → FE builder → acceptance verifier → validator → fix loop → PR. 3 human checkpoints (story / spec / PR).
---

# /ship — Vertical-Slice Feature Factory

Thin orchestrator over the existing `project-lifecycle` skill's per-task cadence. Use for **one user-observable feature inside an active phase** — not a full phase, not a milestone.

## When to use

- Phase is already kicked off (brainstorm done at phase level, plan exists).
- You want to ship ONE feature (one user story, ~3-10 ACs) end-to-end without manually dispatching each cadence step.
- The feature is a vertical slice: touches BE + FE (or layer-pure if project is single-layer).

## When NOT to use

- Fresh project / new milestone → use full `project-lifecycle` workflow.
- Trivial bug fix / typo / single-file polish → just do it inline.
- Refactor / dep bump / docs-only → skip; no user story to anchor on.
- Feature spans >10 ACs or >1 week of work → split into multiple `/ship` calls or escalate to a sub-phase.

## Usage

```
/ship <one-line feature description>
```

Example:
```
/ship Build invoice reminders for invoices unpaid for more than 7 days.
```

## Step 0 — Materialize the chain as a task list (FIRST action, before Phase 0)

Before dispatching any subagent, the controller emits the phase chain as a `TaskCreate` task list — **one `TaskCreate` call per phase below** (Phase 0 research → … → the final smoke + PR), plus the 3 human checkpoints as their own tasks. `TaskCreate` creates one task per call; enumerate each phase, never just announce "N-phase chain". The wrap-up phases (journal / smoke / PR / test-evidence) are **non-optional tasks**. Mark each `in_progress`→`completed` via `TaskUpdate` as the chain advances. Announcing the chain length without emitting the tasks is a skip — the tail phases are the ones that silently drop once the build "feels done".

## Chain (controller executes in order)

### Phase 0 — Codebase research (read-only)

Dispatch `Explore` subagent. Inputs: feature description, project CLAUDE.md, relevant docs.

Output:
- Relevant files + their roles
- Existing patterns to follow
- Similar features already built
- Risks (tenant isolation, timezone, retry-safety, security)
- Tests that will need updating
- New infra likely needed

No edits.

### Phase 1 — Story Writer

Dispatch `Story Writer` subagent. Inputs: feature description + researcher findings.

Output: `docs/superpowers/specs/YYYY-MM-DD-<phase>-<slug>-user-story.md` per `~/.claude/skills/project-lifecycle/references/user-story.md` template:
- One sentence: "As a {role}, I want {behavior}, so that {outcome}."
- Numbered ACs (AC1, AC2, …) — each observable from outside, atomic, test-sketchable
- Out of Scope (explicit no's)
- Edge Cases (awareness for builder + verifier)
- Open Questions (NEVER guess — list, block on user)

### ⏸ HUMAN CHECKPOINT 1: Approve story

Surface the story file to user. Wait for explicit approval ("approved" / "yes" / "ship it").

If user requests changes → edit story → re-surface → wait.

Do NOT proceed to spec without sign-off. Open Questions must be resolved or explicitly accepted-as-deferred.

### Phase 2 — Spec Writer

Dispatch `Spec Writer` subagent. Inputs: approved user-story.md + researcher findings + project CLAUDE.md.

Output: `docs/superpowers/specs/YYYY-MM-DD-<phase>-<slug>-design.md`:
- Data model changes (fields, types, migrations)
- API changes (endpoints, request/response shapes) — one entry per AC where applicable
- Frontend changes (components, pages, hooks)
- Background flow / process flow
- Tests required (success + failure + edge)
- Risks + open questions
- Every file that will change
- Evidence-strength tags on locked decisions (🟢 / 🟡 / 🔴)

Maps each AC → which spec section closes it. Calls out new infra explicitly.

### ⏸ HUMAN CHECKPOINT 2: Approve spec

Surface spec to user. Wait for approval. Red flags to ask about: "store IDs in memory", "skip auth check for now", "tenant isolation deferred". Catch here, not after 10 files.

If approved → write `docs/superpowers/plans/YYYY-MM-DD-<phase>-<slug>.md` from spec (lightweight; tasks = AC groupings).

### Phase 3 — Backend Builder (cadence step 1a)

Dispatch `backend-builder` subagent per `~/.claude/skills/project-lifecycle/references/builder-split.md`:
- Allowed write paths: CLAUDE.md `folder-map.backend`
- Forbidden: anything under `folder-map.frontend`
- Pre-flight assumption block MANDATORY before code
- Surgical-scope clause MANDATORY
- Vertical-slice TDD (1 test → minimal impl → next)
- Writes unit + integration tests for its own code

Output: Builder Summary including **Cross-layer contract** section (endpoint shapes + DB changes + job triggers + auth assumptions).

Controller checks diff stays in allowed paths. Re-dispatch if scope violated.

### Phase 4 — Frontend Builder (cadence step 1b)

Skip if project is single-layer (CLAUDE.md `folder-map: single-layer`).

Dispatch `frontend-builder` subagent. Inputs: spec + BE Builder Summary verbatim.
- Allowed write paths: `folder-map.frontend`
- Forbidden: `folder-map.backend`
- READS BE summary as API contract (does NOT re-read BE source)
- If contract doesn't fit UI need → STOP + report mismatch (controller routes back to BE for contract revision; never silently massages client-side)
- Pre-flight + surgical-scope + vertical-slice TDD same as BE
- Writes component + unit tests for UI

Output: Builder Summary.

### Phase 5 — Acceptance Verifier (cadence step 1.5)

Dispatch `acceptance-verifier` subagent. Inputs: approved user-story.md + BE Summary + FE Summary.
- READ-ONLY on `src/`; write access only to `tests/acceptance/`
- Writes exactly one acceptance test per AC: `test_AC<n>_<short_description>`
- Tests exercise system from outside (HTTP / UI / observable side-effect / DB row / emitted event)
- Reports per-AC table: PASS / FAIL / UNTESTABLE

Output: `## Acceptance Verifier Report — <phase>` with AC Coverage Table + Failures (full pytest/vitest output) + Recommended next action per failure.

Commits as `test(acceptance): <phase> AC1-N coverage`.

### Phase 6 — Validator (cadence step 2)

Dispatch `validator` subagent. Inputs: user-story.md + spec.md + Builder Summaries + Acceptance Verifier Report + git diff vs base.
- READ-ONLY on entire repo (NO Edit, NO Write)
- Checks AC coverage + out-of-scope drift + spec adherence + folder boundary + CLAUDE.md/convention adherence + security (auth, tenant, secrets, error leakage) + edge-case coverage from user-story.md
- Outputs Critical / Important / Minor with file:line
- If clean: says so plainly, does NOT invent findings

Verdict: CLEAN → proceed to step 3 (code quality) + PR. Else → fix loop.

### Phase 7 — Fix Loop

For each Critical/Important finding from Validator (or failing AC from Verifier):
- Route to appropriate builder (BE or FE) based on file path
- Builder fixes in `fix(...)` commit (NEVER amends original `feat(...)`)
- Re-run Acceptance Verifier (if AC test failed)
- Re-run Validator
- Loop until: Validator CLEAN + all ACs PASS

If loop iterates 3+ times on the same finding → STOP. Likely spec/story gap; surface to user for amendment.

### Phase 8 — Code Quality Review (cadence step 3)

Dispatch code-quality reviewer. Bloat-smell checklist mandatory. Output: Strengths / Critical / Important / Minor / Forward-looking / Bloat-smell / Overall.

Fix loop again if Critical/Important found.

### Phase 9 — Journal entry (cadence step 5)

Dispatch journal subagent. 6-section schema per `~/.claude/skills/project-lifecycle/references/journal-schema.md`. Plan deviations header required.

Commits as `docs(journal): <phase> <feature>`.

### Phase 10 — Smoke + PR

- Dual-track smoke per `~/.claude/skills/project-lifecycle/references/smoke-tracks.md` (Track A manual checklist + Track B Playwright/equivalent acceptance test set — Track B = the acceptance tests from Phase 5)
- No handoff doc — that file was retired; its one non-derivable content (findings/gotchas) lands in the journal FACT entry at track close (`~/.claude/skills/project-lifecycle/references/journal-schema.md` §"The FACT entry"; `~/.claude/skills/project-lifecycle/references/cadence.md` §"Track close"), the PR body's §1-3 come from `~/.claude/skills/project-lifecycle/references/handoff-template.md`'s retained appendix template instead
- Push branch
- Open PR with 3-section body (§1 What was done w/ Use cases / §2 Why this approach / §3 Requirements satisfied — close each AC explicitly)
- Post test evidence as PR COMMENT (raw output blocks per `~/.claude/skills/project-lifecycle/references/ci-cd-gates.md`)
- Trigger `@copilot review` (or Pattern E stand-in if billing-blocked) per `~/.claude/skills/project-lifecycle/references/copilot-review-loop.md`

### ⏸ HUMAN CHECKPOINT 3: Approve PR

User reviews PR. Smoke interaction mode per CLAUDE.md `smoke-mode` (or ask). Merge on approval.

## Three checkpoints (all others run unattended)

1. **After story** — does this match what user wanted?
2. **After spec** — design sane? red flags caught?
3. **After PR** — final review + smoke + merge?

Everything between checkpoints (research, build BE, build FE, verify, validate, fix, journal, smoke, PR draft) runs without human intervention unless a subagent reports BLOCKED / NEEDS_CONTEXT or a mismatch can't be resolved automatically.

## Anti-patterns

- Running the chain without first emitting each phase as a `TaskCreate` task (Step 0) → the wrap-up phases (journal / smoke / PR) silently drop once the build "feels done".
- Using `/ship` for a 1-line fix → just do it inline.
- Using `/ship` for an entire milestone → too coarse; use phase-level `project-lifecycle` workflow.
- Skipping HUMAN CHECKPOINT 1 because "the story is obvious" → the obvious feature is where scope creep starts.
- Skipping HUMAN CHECKPOINT 2 because story was approved → spec is where wrong assumptions enter; catch here before files change.
- Auto-merging at CHECKPOINT 3 without smoke → smoke is the only thing that proves the feature works for the user, not just the test framework.
- Letting builder skip pre-flight assumption block → wrong-assumption-then-run is the #1 LLM failure mode.
- Skipping Validator + Acceptance Verifier because "code-quality review will catch it" → different lenses. All three required on non-mechanical work.
- Forking off a second `/ship` while one is mid-loop → builders will conflict on shared files. Serialize.

## Related

- `~/.claude/skills/project-lifecycle/SKILL.md` — phase-level workflow this command sits inside
- `~/.claude/skills/project-lifecycle/references/cadence.md` — full per-task cadence (6 steps) this command automates
- `~/.claude/skills/project-lifecycle/references/user-story.md` — story format used at Phase 1
- `~/.claude/skills/project-lifecycle/references/builder-split.md` — BE/FE split used at Phase 3+4
- `superpowers:writing-plans` (or your own planning command) — heavier planner for non-vertical-slice work
- `/review` — PLC-native reviewer for diffs that didn't go through `/ship` (dispatches `references/reviewer-brief.md`)
