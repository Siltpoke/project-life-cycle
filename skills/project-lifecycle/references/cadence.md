# Per-Task Cadence

Six steps per task by default (was five; **step 1.5 acceptance verifier** added 2026-05-27). Each is a separate, observable artifact (subagent dispatch, commit, or both).

For phases spanning backend + frontend, **step 1 splits into 1a (backend builder) + 1b (frontend builder)** per `builder-split.md`. Layer-pure phases use a single builder.

## Step 1: Dispatch implementer subagent(s)

**Cross-layer phases** → split into 1a backend-builder + 1b frontend-builder. See `builder-split.md` for the folder-scoped pattern, prompt templates, and Builder Summary format. The shared discipline below applies to BOTH builders (and to the single-implementer case on layer-pure phases).

Controller (the orchestrating agent) prepares each implementer prompt:

- **Full task text** from the plan (don't make the subagent read the plan file).
- **Acceptance Criteria this task closes** — explicit AC IDs from `user-story.md` (e.g., "this task closes AC3, AC4"). Builder pre-flight block MUST restate which ACs it's targeting.
- **Scene-setting context** — what previous tasks built that this one depends on. For frontend builder, this includes the Backend Summary verbatim (see `builder-split.md`).
- **Contingencies injection** — if `user-story.md` declares a Contingencies section, paste it verbatim into the builder prompt. The builder consults it before escalating: a situation matching a declared contingency follows the pre-decided action (and notes which one fired in the Builder Summary); only undeclared surprises go through BLOCKED / NEEDS_CONTEXT. Saves a full controller round-trip per foreseeable failure path.
- **Folder-scope clause (mandatory on split phases)** — explicit allowed write paths from `CLAUDE.md` `folder-map`; explicit forbidden paths. Controller rejects any diff touching forbidden paths.
- **Adapt-to-existing-patterns guidance** — when the plan was written before the codebase matured, the live code may have established conventions (typed wrappers, helper objects, naming) that the plan snippet doesn't reflect. The controller MUST tell the implementer to use the live conventions, not blindly copy the plan.
- **First-of-its-kind detection** — if this task is the first to introduce a new tooling category (test runner, language toolchain, container runtime, contract format, etc.), the controller MUST either insert a bootstrap step or list the missing infra in the prompt.
- **Test priority confirmation (when task involves tests)** — controller MUST confirm with the user which behaviors matter most BEFORE the implementer writes tests. You can't test everything. Critical paths + complex logic, not exhaustive edge-case enumeration. Surface the proposed test list to the user; let them prune. Note: **acceptance tests are NOT the builder's job** — they're written in step 1.5 by an independent verifier against `user-story.md` ACs. Builder writes unit + integration tests for the code it produces.
- **Per-task verification command + no-placeholder plan check** — each task in the plan doc should carry an explicit, **runnable verification command** (the exact `pytest -k …` / `npm test -- -t …` / `curl …` / build invocation that proves THIS task works) plus its `Depends-on` edge; the controller passes that command into the implementer brief and confirms it ran green before accepting `DONE`. A plan entry that is a vague placeholder ("add validation", "wire it up later") with no concrete files-touched estimate and no verify command is **not ready to dispatch** — send it back to planning first. This tightens the plan→execute handoff: the implementer knows exactly what "done" means for this task, and the controller holds a concrete per-task oracle instead of only the phase-level test-evidence. Distinct from step 1.5 — that verifier checks `user-story.md` ACs independently; this is the builder's own per-task self-check. (General engineering practice; note the plan-doc's per-task detail is legitimate here because the plan is consumed immediately by this phase's cadence — unlike a long-lived issue body, where `issue-breakdown.md` deliberately keeps file paths OUT because they rot before an async agent picks the ticket up.)
- **Vertical-slice TDD enforcement** — implementer MUST work in tracer-bullet cycles: 1 test → minimal impl → next test → minimal impl. Never write all tests first then all impl ("horizontal slicing" produces tests that verify imagined shape, not real behavior, and pass when behavior actually breaks). Refactor only while GREEN.
- **Pre-flight assumption block (MANDATORY before any code)** — implementer MUST output an assumption block BEFORE writing the first line of code. Format:
  ```
  ## Pre-flight
  Assumptions (3+):
    1. [about input shape / data source / existing pattern / integration point]
    2. ...
    3. ...
  Alternative interpretations of the task (if any):
    - [interpretation A] vs [interpretation B] → I'm picking A because [reason]
    - or: "single unambiguous reading, no alternatives"
  Simpler approach considered:
    - [the dumbest thing that could work] → rejected because [reason]
    - or: "this IS the simplest approach"
  STOP here. Wait for controller confirmation. No silent picks.
  ```
  Controller reviews → confirms / corrects / surfaces to user if ambiguity is real → implementer proceeds. Rationale: LLM default behavior is wrong-assumption-then-run; the block forces surface-before-code. Karpathy: "they make wrong assumptions on your behalf and just run along with them without checking."
- **Surgical scope (MANDATORY clause in implementer brief)** —
  ```
  Surgical scope rules:
    - Touch ONLY files/lines tracing directly to this task text.
    - Do NOT reformat, rename, or "improve" adjacent code.
    - Do NOT remove pre-existing dead code, even if obviously unused, unless the task asks for it.
    - Do NOT modify comments you didn't author UNLESS the task changes their meaning.
    - If you notice an unrelated issue (bug / dead code / smell) → log it in the journal "Findings" section; do NOT fix it in this commit.
    - Every changed line must trace to a sentence in the task text.
  ```
  Rationale: Karpathy: "they sometimes change/remove comments and code they don't understand as side effects, even if it is orthogonal to the task at hand." Surgical-scope clause is the counter-instruction.
- **Soft time budget (MANDATORY line in implementer brief)** —
  ```
  Soft budget: note the start time (`date`) in your pre-flight block, and
  note a fresh `date` each time the controller confirms after a STOP —
  active-work elapsed accumulates between a resume and the next STOP, so
  waiting on controller confirmation never counts. Re-check elapsed time
  every ~10 tool calls. Past ~15 minutes of active work, STOP and return
  SPLIT_PROPOSED with (a) a summary of what is already done — leave it
  UNCOMMITTED; nothing is committed or pushed until the controller's
  split-vs-continue decision — and (b) a proposed split of the remainder
  into vertical slices. Do not push through a 25-minute task silently.
  ```
  Soft means report-back, not kill: the controller reviews the proposal and either dispatches the slices or explicitly authorizes continuing (recorded in the journal "Plan deviations"; the task then ends in its single `feat(...)` commit as usual — the invariant is never relaxed). On a split, the done-so-far work becomes the first slice's starting state, committed by that slice under the normal one-task-one-commit rule — and the slice-1 dispatch **names the inherited uncommitted diff as explicit input**: slice 1's pre-flight block must restate assumptions covering that inherited code (adopt-or-flag — a flag returns BLOCKED and routes back to the controller for a re-split decision, the same way an FE mismatch goes back to the BE builder) before adding its own work. The budget is a **best-effort heuristic, not a trusted control**: an LLM's elapsed-time introspection is unreliable even with the `date` proxy, so the pre-split rule below is the primary (static) control and this is only the runtime backstop. A SPLIT_PROPOSED return also holds the background verification tail — per §"Background-by-default" the tail fires only on the claimed-complete statuses (DONE / DONE_WITH_CONCERNS), so verifier/CQ dispatch only after the controller's decision produces such a return. Rationale: the top wall-clock offenders in measured runs were 26-30 minute opaque synchronous implementer calls (top-2 single ops: 29m40s, 26m08s) — the controller learns nothing until they return.
- **Controller pre-split rule (before dispatch)** — when the task's plan text predicts more than one file-cluster (touches multiple unrelated modules/directories, or its description contains several independently-shippable verbs), pre-split it into vertical tracer-bullet slices and dispatch each as its own task (one slice = one commit; same invariant as ever). The soft budget above is the runtime backstop; this rule is the cheaper static catch. Risk: over-splitting adds dispatch overhead — when unsure, keep it one task and let the soft budget decide at runtime.
- **Status reporting format** — DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT | SPLIT_PROPOSED (soft budget exceeded; carries the done-so-far list + proposed slices).
- **Builder Summary on completion** — required on split-phase dispatches; recommended on single-implementer dispatches. Schema in `builder-split.md` §Builder Summary format. Frontend builder's input includes the Backend Summary; mismatch flags go BACK to backend builder, never silently massaged on the client.

The implementer commits the work as a `feat(...)` (or `test(...)` / `fix(...)` if appropriate) commit and reports back.

For a **non-technical audience** (`adaptive`/`plain`), while building, watch for high-value app-improvement opportunities (frontend loading/images/lists; backend caching/pagination/indexes/N+1) and surface them inline in plain language + offer to apply, per `references/proactive-tips.md` (anti-nag rules apply: high-value only, one tip, never re-surface a declined one). Skipped under `audience: technical`.

## Step 1.5: Acceptance verifier

**Independent subagent.** Distinct from the unit/integration tests the builder wrote in step 1. Lens: **does the feature actually do what `user-story.md` says it should, judged from outside the system?**

Required when `user-story.md` exists (i.e., any user-observable phase). Skip only for layer-pure refactor / dep bump / docs phases that produced no `user-story.md`.

### Dispatch contract

```
You are the ACCEPTANCE VERIFIER for phase X.Y.

Inputs (read these, do NOT read the implementation source code):
- docs/superpowers/specs/<...>-user-story.md (acceptance criteria, ground truth)
- Backend Summary + Frontend Summary from step 1 (what was built + API contract)

Job:
1. For each AC in user-story.md, write exactly one acceptance test.
2. Test names MUST encode the AC ID: `test_AC3_<short_description>`.
3. Tests exercise the system from outside (HTTP call / UI interaction / DB query as
   observable side-effect / emitted event capture). Do NOT call internal functions
   directly — that's a unit test, not an acceptance test.
4. Use the existing test framework + fixtures the project already has.
5. Place tests in tests/acceptance/phase-X.Y/ (or project-equivalent path).

What you do NOT do:
- Modify backend or frontend source code (read-only on src/).
- Invent acceptance tests for behaviors not in user-story.md ACs.
- Mark an AC as "covered" if you can only observe it via internals.
- Silently skip an AC because it's "hard to test" — report it as UNTESTABLE
  with the specific reason; controller surfaces to user.

Allowed tools: Read, Edit/Write (LIMITED to tests/acceptance/* and test fixtures), Bash (test runner).

Output (mandatory):

## Acceptance Verifier Report — Phase X.Y

### AC Coverage Table
| AC  | Test name                          | Status   | Notes                           |
|-----|------------------------------------|----------|---------------------------------|
| AC1 | test_AC1_user_can_register         | ✅ PASS  |                                 |
| AC2 | test_AC2_email_validation          | ❌ FAIL  | Returns 500 not 400 on bad email|
| AC3 | test_AC3_admin_audit_log_written   | ✅ PASS  |                                 |
| AC4 | (none)                             | ⚠ UNTESTABLE | No external observation; only logged at DEBUG. Promote to log capture or expose via /audit endpoint. |

### Summary
- ACs total: N
- Passing: N
- Failing: N (with file:line of failure)
- Untestable: N (with reason for each)

### Failures (full pytest/vitest output blocks)
{verbatim test output for each fail}

### Recommended next action
- FAIL on AC2 → goes to BACKEND builder (input validation in src/api/...)
- UNTESTABLE on AC4 → needs spec amendment (expose audit log) before retry
```

### Routing failures

- **AC fails because the code is wrong** → fix dispatch to the builder owning that layer (BE or FE).
- **AC fails because the test is wrong** (verifier misread the AC) → re-dispatch verifier with the correction.
- **AC marked UNTESTABLE because the system has no external observation** → spec gap; surface to user. Options: amend the spec to expose observation (add endpoint / emit event / log to capturable channel), or accept AC as "manual-only" + log in handoff §findings.
- **Verifier wants to modify source code to make a test pass** → REJECT. Verifier is read-only on `src/`. If the impl is wrong, route to builder.

### Acceptance tests live separately from unit tests

- `tests/unit/` — builder's responsibility, white-box, tests internal correctness
- `tests/integration/` — builder's responsibility, tests inter-module behavior
- `tests/acceptance/` — verifier's responsibility, black-box, tests AC satisfaction

Different lifecycles. Unit tests change when impl changes; acceptance tests change when ACs change. Don't conflate.

### Commit

Acceptance verifier commits as `test(acceptance): phase X.Y AC1-N coverage` — separate from builder's `feat(...)` commit. Failed-then-fixed flows get a follow-up `fix(...)` commit from the builder, then the verifier re-runs (no new commit if tests didn't change).

## Background-by-default: the verification tail (steps 1.5 → 2 ∥ 3)

> **Canonical executor: `.claude/workflows/verify-tail.mjs`.**
> For the full-cadence tail the controller does NOT hand-dispatch three reviewer subagents — it
> **invokes the script**, which owns both the control flow (verifier ∥ code-quality at
> implementer-return, validator joining on the verifier report, the skipped-1.5 branch, the
> missing-report = hole degradation) AND the full review-record dispatch contracts (the script's
> inline prompts carry them — see the prose below, which is now the human-readable spec of what
> those prompts encode, kept in sync with the script in the SAME commit).
>
> **How to run it** (at implementer-return, on a claimed-complete status):
> ```
> Workflow({ scriptPath: '.claude/workflows/verify-tail.mjs', args: {
>   builderCommitSHA, prevTaskTip,        // → cq/validator diff range (prevTaskTip..SHA)
>   builderSummary,                        // the Builder Summary (builder-split.md schema)
>   storyPath,                             // null → skipped-1.5 branch (no verifier lane)
>   specPath, planPath,                    // validator inputs; null → validate vs story+diff
>   folderMapSide                          // routing hint (reserved)
> }})
> ```
> It returns `{ verifier, cq, validator, holes }` — the controller consumes that for the fixup
> step (step 4); a non-empty `holes` = a missing/failed report → re-dispatch once then surface,
> never proceed with a verification hole.
>
> **Scope:** the script is canonical for the **full-cadence** tail only. Cadence **compression**
> (6→4, §below — a single merged validator+CQ pass the script does not implement), **step 1**
> (implementer), and **step 4** (fixup) stay prose-authoritative and hand-dispatched. Invoke by
> `scriptPath` — this harness does not auto-register `.claude/workflows/*.mjs` by name.

**The rule:** the post-implementation verification tail dispatches as
`run_in_background` agents the moment the implementer returns **with a
claimed-complete status (DONE / DONE_WITH_CONCERNS)** — a SPLIT_PROPOSED return is
an intentionally-incomplete diff, so the tail holds until the controller's
split-vs-continue decision produces a real return (reviewing a diff nobody claimed
finished only manufactures noise); the controller does NOT sit idle watching them. Measured
sessions ran validators sync + one-at-a-time (33m of one 4h19m session; 7 serial diff
reviews = 24m in another) while the parallel primitive already existed and was already
the habit for acceptance verifiers — the waste was pure default-habit, ~30-60m/phase.

Dispatch timing follows the real data dependencies, nothing else:

- **Code-quality review (step 3)** needs only the builder's diff + Builder Summary →
  dispatch in background **the moment the implementer returns**. Pin its scope to THIS
  task's commits at dispatch time — `<previous-task tip>..<builder-commit-SHA>` (on the
  phase's first task that is the branch fork point; on later tasks it is NOT `merge-base..`,
  which would sweep the whole phase-to-date diff back into every review). The pin exists
  because the concurrently-running acceptance verifier lands a `test(acceptance)` commit
  mid-flight, so a generic "review the diff" instruction would race against it (the old
  sequential order never had this ambiguity).
- **Acceptance verifier (step 1.5)** reads only the story + Builder Summaries (never
  implementation source — its own contract above forbids it) and writes only
  `tests/acceptance/*` → same background batch at implementer-return.
- **Validator (step 2)** consumes the Acceptance Verifier Report (its lie-detection
  cross-checks builder claims against it) → dispatch in background **the moment the
  verifier report lands**. When step 1.5 is skipped (no `user-story.md`) but the full
  cadence runs, the validator joins the initial batch at implementer-return. On a
  **compressed** cadence there is no separate validator at all — the single merged
  validator+CQ pass (per §"Cadence Compression" below) dispatches at implementer-return.

**Block at the fixup step, not at dispatch.** Step 4 is the first point that needs both
reports — that is the ONLY sync point. Between dispatch and there, the controller keeps
working: journal-entry prep, next-task grounding (reading the next task's plan text +
files), PR-draft scaffolding. Sync early only when a gate decision genuinely needs a
result sooner.

**Risk containment:** none of the three agents writes implementation source (the
verifier writes only `tests/acceptance/*`), so background concurrency cannot conflict. A background agent that dies or returns BLOCKED surfaces
at the fixup-step wait — treat a missing report exactly like a failed report (re-dispatch
once, then surface to the user; never proceed to fixup with a verification hole).

## Step 2: Spec + AC compliance review (Validator)

Independent subagent. **Strictly read-only on source.** Lens: **does the implementation satisfy the user story and spec, with no scope drift in either direction?**

> **Reviewer dispatch constraints apply** (`references/review-record.md`): fresh context (never the writer's session), read-only tools, explicit model tier (prefer ≥ implementer's), refute-first output order with the verdict field LAST, every finding cites `file:line` + quoted snippet (unquotable findings are discarded), and the pass/fail verdict is computed by the controller from per-criterion fields + open-severity counts — never taken from a reviewer-stated "approved". Pre-seeded suspicions are allowed only AFTER the prompt requires one unanchored full-diff pass.

### Dispatch contract

```
You are the VALIDATOR for phase X.Y.

Inputs (read-only):
- docs/superpowers/specs/<...>-user-story.md (ground truth for "what was promised")
- docs/superpowers/specs/<...>-design.md (spec)
- docs/superpowers/plans/<...>.md (plan)
- Builder Summaries from step 1
- Acceptance Verifier Report from step 1.5 (when step 1.5 ran; absent on skip/compress —
  lie-detection then cross-checks against Builder Summaries + the diff only)
- Implementation source on disk (git diff vs base branch)

What you do (every check, every run):
0. Lie detection (FIRST pass, before everything else):
   - For each AC the Builder Summary claims as "closed": does the diff
     actually touch code that could close that AC? If the summary says
     "AC3 closed" but no file in the diff implements AC3's behavior,
     OR the acceptance verifier reported FAIL for AC3, that's a lie
     → CRITICAL with the file:line of the false claim.
   - For each "success" assertion in the implementation (e.g., a tool
     call that logs "sent email" / "saved record" / "logged in user"):
     does the code actually do the asserted thing, or does it only log
     the assertion without performing the action? Compare against the
     acceptance verifier's tool-trace report when it exists; without a
     verifier report (skip/compress), the diff itself must demonstrate
     the asserted behavior. False success = lie = CRITICAL.
   - For any "verified" / "tested" / "works" claim in builder
     summaries: trace to the actual test result (acceptance verifier
     report when it exists; otherwise a test the diff itself contains —
     located via the Builder Summary's citation, independently
     re-runnable by the validator; a narrative "tests passing" claim
     alone never counts). Unverifiable claim = CRITICAL — absence
     of a verifier report never downgrades an untraceable claim.
   Rationale: LLMs default to claiming success because the training
   reward favored confident outputs. The validator is the read-only
   harness component that catches this. (See Tejas Kumar's "Harnesses in
   AI: A Deep Dive" (https://www.youtube.com/watch?v=C_GG5g38vLU) — the lying-agent demo at hacker-news
   shows exactly this failure mode.)
1. Acceptance criteria coverage:
   - For each AC, is there a passing acceptance test? (cross-check with verifier report)
   - For each AC, can you trace its implementation in the diff?
   - Any AC marked covered without a passing test → CRITICAL.
2. Out-of-scope drift:
   - Any code change that doesn't trace to an AC → flag (over-build / scope creep).
   - Any item from user-story.md "Out of Scope" that snuck in → CRITICAL.
3. Spec adherence:
   - Are the data model / API / file changes from spec.md actually in the diff?
   - Any spec bullet missing from code → CRITICAL.
   - Any new infra not listed in spec → flag (over-build or required infra-spec amendment).
4. Folder boundary (on split phases):
   - BE builder touched only backend paths? FE only frontend?
   - Any forbidden cross-imports (per folder-map.forbidden-cross)?
5. CLAUDE.md / convention adherence:
   - Any pattern divergence from established codebase conventions?
   - Any duplicate logic that should reuse an existing helper?
6. Security (per the security lens of `references/reviewer-brief.md`, read-only):
   - Auth checks on new endpoints?
   - Tenant isolation on multi-tenant queries?
   - Secrets/PII in logs?
   - Raw errors leaking to clients?
7. Edge-case coverage from user-story.md "Edge Cases" section:
   - Timezone / multi-tenant / retry-safety items that the spec called out — actually handled in code?

What you do NOT do:
- Modify any file (read-only on the entire repo).
- Invent issues to look thorough. If clean, say so plainly.
- Propose architectural redesigns. Stick to gaps against spec/story.
- Re-do step 3's code-quality review. That's a separate pass with a different lens (design / naming / perf / bloat). Validator is correctness vs promise, not craftsmanship.

Allowed tools: Read, Grep, Glob, Bash (read-only inspection: git diff, git log, test runner without write effects). NO Edit, NO Write.

Output (mandatory):

## Validator Report — Phase X.Y

### Findings (grouped by severity)

#### Critical (blocks merge)
- {file}:{line} — AC{N} claimed covered but acceptance test failing: ... {fix: ...}
- {file}:{line} — endpoint /api/foo missing tenant check (multi-tenant rule in user-story.md edge cases): ... {fix: ...}

#### Important (should fix before merge)
- {file}:{line} — new BullMQ queue added but not in spec; either amend spec or remove
- {file}:{line} — duplicate validation logic; existing helper at src/lib/validation.ts:42 covers this

#### Minor (reviewer call, opinion-based)
- {file}:{line} — variable name `x` could be more descriptive

### Coverage Summary
- ACs total: N
- ACs with passing acceptance test: N
- ACs with implementation but no test: N (LIST)
- ACs with test but no traceable implementation: N (LIST)
- Code changes without an AC: N files, N lines (LIST — possible scope creep)

### Out-of-scope drift
- {explicit list of any user-story "Out of Scope" item that appeared in diff, or "none"}

### Folder boundary
- BE paths touched: {list}
- FE paths touched: {list}
- Violations: {list, or "none"}

### Verdict
- ✅ CLEAN — ready for code-quality review (step 3) and PR (step 8)
- OR ❌ {N Critical + N Important} — return to {builder(s) / spec amendment / verifier}
```

### Routing fixes

- Critical → mandatory fix before merge. Goes back to the appropriate builder (BE or FE) or verifier (for test-coverage gaps) or back to spec amendment (for spec-vs-impl gaps where the spec was wrong).
- Important → defer-vs-fix triage per `defer-vs-fix.md`.
- Minor → reviewer's call; default is defer to backlog.

### Why validator is read-only

A reviewer who can edit code starts editing. Their findings become invisible (folded into the edit), the diff loses traceability, and the loop muddles. Read-only forces the reviewer to **describe the gap precisely enough for someone else to fix** — which is the only way the report stays useful as an audit artifact and as a teaching signal for the builder.

### Why validator does NOT do code quality

Step 3 (code quality review) covers design / naming / perf / a11y / bloat-smell. Validator covers correctness-vs-promise. Different lenses, different outputs, different anti-patterns. Combining them in one pass produces a sprawling report where critical correctness issues get buried under style nits.

### If validator finds nothing

Say so plainly: "No findings. Coverage 100%. No drift. Ready for step 3." Do NOT invent minor findings to look thorough. A clean run is a real outcome, not a sign the reviewer didn't try.

### Re-run loop

After fix dispatched, re-run validator on the new diff. Iterate until CLEAN.

## Step 3: Code quality review

> **Background-by-default.** This pass dispatches as a background agent at
> implementer-return, in the same batch as the acceptance verifier; the validator joins
> when the verifier report lands. The controller blocks only at the fixup step. Full
> rule + dependency graph: §"Background-by-default: the verification tail" above;
> platform mechanics: `references/harness-primitives.md` §4.

Independent subagent — dispatch a general-purpose agent briefed per `references/reviewer-brief.md` (or `superpowers:requesting-code-review`, or your own reviewer). Lens: **is the implementation well-built?** The same reviewer dispatch constraints as step 2 apply (`references/review-record.md`) — and steps 2/3 are intentionally **different lenses, not clones**: distinct prompts (ideally distinct tiers) is what makes a multi-reviewer pass worth more than one reviewer voting twice.

Standard concerns: design, naming, error handling, security, a11y (UI), performance, test quality.

**Plus a third category — forward-looking findings.** A finding that says "this works for the spec, but a downstream task will be hurt by it" (e.g., generated artifact uses an unstable name; consumer task hasn't been written yet but will need a stable name). Reviewer should explicitly call these out.

**Plus a fourth category — bloat / overcomplication smell.** LLM default is over-eager / over-abstracted code. Reviewer MUST run this checklist explicitly (not implicitly inside "design"):

```
Bloat smell checklist:
  [ ] Line-count delta vs task complexity sane? (e.g., "add validation" producing 200+ lines = flag)
  [ ] Any abstraction created for single use? (helper class with one caller, factory for one product, interface with one impl) → flag
  [ ] Any configurability / flexibility the task did NOT request? (options object, strategy pattern, plugin point) → flag
  [ ] Any error handling for impossible scenarios? (internal-only callers, framework-guaranteed invariants) → flag
  [ ] Any features beyond the spec? (logging, metrics, retry, caching the user didn't ask for) → flag
  [ ] "Would a senior engineer call this overcomplicated?" → if yes, flag
  [ ] Could this be ~half the lines and still solve the problem? → if yes, flag with the simpler shape sketched
```

Output: Strengths / Critical / Important / Minor / Forward-looking / **Bloat-smell** / Overall Assessment.

Rationale: Karpathy: "they will implement an inefficient, bloated, brittle construction over 1000 lines of code and it's up to you to be like 'umm couldn't you just do this instead?' and they will be like 'of course!' and immediately cut it down to 100 lines." The reviewer should be the one catching this, not the user.

If issues found, dispatch a fix subagent (typically the same implementer pattern). Re-review until approved.

## Step 4: Fixup commit

If review found issues, the fixup is a **separate commit** on top of the original. Never amend the original `feat(...)`; never squash the review history away.

**Between finding and fix, four rules** (full rationale + live incidents in `references/review-record.md`):

1. **Routing split** — mechanically verifiable findings (a RED test / deterministic check can prove them) → fix; judgment calls (design taste, semantics tie-breaks) → report-only, routed to the human via the PR's "Reviewer asks". Guard against "the reviewer was wrong and the code drifted to match it".
2. **One review-fix = one commit**, referencing the finding — wrong premise = revert exactly one. This is a commit-time checklist item, not an intention (it was stated and then violated on its first live track).
3. **The reviewer's suggested fix code is untrusted input.** Adopt the finding; derive the fix yourself from the surrounding code and ship it with a test. A pasted reviewer snippet has already caused a real silent-data-loss bug.
4. **Review-fixes are unreviewed code** — after fixes (and any other post-review commits), a fresh **final-pass reviewer** covers everything earlier rounds did not see, before the task/PR closes.

**If the fixup is a non-trivial bug** (root cause unclear, reproduces only sometimes, 3+ minutes to understand) → invoke `diagnose-loop.md` before patching. Iron Law: no fix without root cause. Don't substitute "review reviewer said fix X" for a real diagnosis when the bug isn't obvious.

Resulting git log per task:

```
feat(...): original implementation
fix(...): review follow-ups (if any)
fix(...): smaller follow-up (if any)
docs(...): journal entry
```

This makes review feedback traceable in `git log` and preserves the original work as a reviewable artifact.

### Selective re-verification after fixup (task level ONLY)

Re-running the whole verification chain after every fixup burns tokens proportional to ceremony, not to what changed. At task level, scope the re-verification to what the fixup diff actually touched:

- Map the fixup diff to scopes: folder-map sides (BE / FE) + the AC IDs the changed lines trace to.
- **Acceptance verifier** → re-run only the acceptance tests for affected ACs.
- **Validator** → re-check only its own raised findings + the fixup commit's diff (not the full original diff again).
- **Unaffected-scope suites** (e.g. BE unit/integration when the fixup is FE-only) may be skipped at task level; the task-done test-evidence may be scoped accordingly.

**Two hard boundaries:**

1. **The phase-level gate stays full.** `phase-done` still requires complete fresh full-suite test-evidence (incl. `RUNS=N`) before the PR. That full run is the safety net — it is exactly what catches a regression that task-level selectivity skipped. This subsection changes nothing in `close-gate.md` phase mode.
2. **Falsification rule.** If the phase gate catches a regression that a skipped task-level re-run would have caught, log it in the journal ("Plan deviations") and stop using selectivity for the remainder of the phase — the rule is falsified for this codebase until re-examined.

Adoption note: on a project currently mid-phase, this takes effect from the next phase boundary — never change a running phase's exit criteria.

## Step 5: Journal entry

Separate `docs:` commit. Follows the 6-section schema in `journal-schema.md`. Covers the **whole task** (all of its commits), not each commit individually.

**Write path:** the entry appends to the current branch's fragment file `docs/journal.d/<date>-<branch-slug>.md` — one fragment per BRANCH, not per task; if the fragment already exists, append to it. Fragments carry no TOC (short-lived hot files); at milestone close they are compiled into `docs/archive/journal/YYYY-MM.md` and deleted (see `references/retention.md` §"Fragment convention"). Projects without `docs/journal.d/` keep appending to the monolith path in the close-gate manifest (`journal`) — the gate accepts either.

Naming is branch-, not phase-, keyed: under WIP=1 a branch and a phase are effectively the same unit of work, so this still reads as "one fragment per phase" in practice — but keying the filename on the branch specifically is what keeps two branches active at once (or a branch that outlives one phase) from colliding on a shared filename.

### Approval timing — the `close-gate` policy key

Projects that adopt a human-blocking close approval (a CLAUDE.md rule that the Task Close Report awaits the user's "ok" before commit) control WHERE that approval sits via `close-gate: per-task | pr-boundary` in CLAUDE.md:

- `per-task` (default) — block here, at every task close, on the user's "ok".
- `pr-boundary` — an independent **read-only** reviewer subagent does the per-task read; the Task Close Report is still written every task (audit trail) but does not block; the human's blocking approval moves to once per PR/merge, which must carry a **human-written approval marker the AI cannot author**.

The deterministic `make task-done` gate runs identically in both modes — the key never relaxes it. Full mechanics, the self-certification attack surface, and the experiment protocol (catch parity + comprehension drift over 2-3 tracks, rollback = flip the key): `close-gate.md` §"Approval timing".

## Cadence Compression (Mechanical Tasks)

For purely mechanical tasks — single-file regen, schema bump, lockfile update, mechanical refactor that preserves behavior — the default 6-step cadence is overhead.

**Compress to 4 steps** when **all three** conditions hold:

1. The diff is small relative to project norms.
2. No new logic or control flow is introduced.
3. No security / compliance / auth surface is touched.

Compression rules:
- **Skip step 1.5 (acceptance verifier)** — only applies when `user-story.md` is present; mechanical tasks don't have user-observable behavior changes.
- **Merge step 2 (validator) + step 3 (code quality)** into one combined reviewer pass.
- Step 1 stays single-implementer (no BE/FE split on layer-pure mechanical work).
- Steps 4 (fixup) + 5 (journal) unchanged.

If even one of the three conditions fails, run the full cadence.

## Comprehension Co-Discovery (opt-in, phase-level)

> Anti-cognitive-offloading. Full rationale + the two load-bearing constraints: `comprehension-co-discovery.md`. **Off by default** (`comprehension: off | lite | full` policy key — see `output-format.md`). Scope is this one step; the predict-before-build variant is not part of it.

After the phase's work is validated (step 2) and quality-reviewed (step 3) — the diff is now real, correct, and about to head to the PR checkpoint — **optionally** run **one** comprehension round with the user. This is the highest-offloading-risk moment: "looks done, merge it" without having read the implementation.

- **Once per phase, NOT per task.** Skip entirely on mechanical / compressed-cadence work. Budget: **< 30s total**. If it feels like "sit down and take a quiz," it's mis-designed.
- The harness reads the real diff, asks **one** *why*-style question that only makes sense if you've read the implementation ("why X instead of Y here?", "what happens if input becomes Z?", "what's the failure mode of this line?"). User answers in their own words. The harness compares the answer **against the diff** and says what's right / what's off / **and why**.
- **Co-discovery, not a quiz.** Framing is "interesting — you expected X, it actually does Y" (curiosity), never "you got this wrong / you don't understand X" (judgment). The harness can be wrong too — it's comparing notes against ground truth, not grading.
- **Non-blocking.** A weak answer does NOT block the PR. Optionally leaves a `[COMPREHENSION-GAP]` note in the journal Findings and moves on. **No cumulative score / scoreboard** — immediate per-round feedback only, then the round is discarded. Next phase = a fresh round.

Why here: this is the repo's own `verify-loop.md` ("give the LLM a way to check its own work, or it self-grades and lies") **turned on the human**, and structurally the validator's lie-detection (cross-reference a claim against the diff) applied to the user's *claimed understanding* instead of a builder's claimed work. Reversible behavior — **NOT an ADR** (fails the `adr.md` hard-to-reverse criterion).

## Track close — distill, then archive

Runs once per closed track (after merge), before the milestone-close drain (`references/retention.md` §"The three tiers").

1. **Distill.** Read the track's `docs/superpowers/specs/*` and `plans/*`. Extract ONLY what is **not derivable from a live source** — the reasoning of the day, the rejected options and why, the traps hit. Write it as a FACT entry (schema: `references/journal-schema.md` §"The FACT entry") into the current journal fragment (`docs/journal.d/<date>-<branch-slug>.md`, per the "Write path" note under Step 5). Length is unbounded; **tense is not** — every claim is about that day.

   **Do not copy** anything derivable: file inventories (git has them), test results (the run has them), the PR body (GitHub has it), code blocks (the code has them, and it has since moved). Measured: 26.4% of the sampled corpus's spec bytes were literal code blocks — every one of them a copy that has since drifted.

2. **Archive the working docs.** For each spec/plan of the closed track:

   ```bash
   bash scripts/retention-drain.sh archive-working docs/superpowers/specs/<file>.md
   bash scripts/retention-drain.sh archive-working docs/superpowers/plans/<file>.md
   ```

   They move to `<archive_dir>/working/…` — out of the hot read/grep path, still on disk, still searchable. **Never `rm`** — deletion is deferred until distill quality is proven over 2-3 tracks (`references/retention.md` §"The three tiers", Deep-cold row). Record the pre-move path + the SHA in the FACT entry's `Source:` field.

3. **Commit** as a `docs:` commit alongside the track's journal entry.

**Why the spec/plan leave the hot path.** They are **working state**, not documentation — consumed by the cadence during the track and false the moment the track lands. Measured: **12 of 12** sampled plans described a future that had already shipped; a spec still named a rendering library the code had stopped using three months earlier. An agent reading them does not gain context — it is poisoned by a confident description of a system that no longer exists. This is the same MOMENT-vs-STATE law that governs journal tense (`references/journal-schema.md` §"Tense"): *a document that records a MOMENT does not rot; a document that claims a STATE always rots* — a spec/plan is written entirely in STATE claims ("the system does X"), so by definition it cannot outlive the track that produced it. The FACT entry is the MOMENT-shaped residue that survives; the spec/plan is the STATE-shaped scaffold that is archived once it has served its purpose.

## Controller Anti-Patterns

- Letting the implementer read the plan file directly — wastes context, lets implementer skip the controller-added "adapt" guidance.
- Dispatching multiple implementers in parallel against the same files — they'll conflict.
- Merging review feedback into the implementer's prompt instead of running a separate fix dispatch — loses the review trail.
- Skipping the acceptance verifier (step 1.5) on a user-observable phase because "the unit tests pass" — different concern; unit tests verify the implementation's internals, acceptance tests verify the user-story ACs. Both required.
- Skipping the validator (step 2) because "code-quality review will catch it" — different lens. Validator covers correctness-vs-promise (AC coverage, scope drift, security gaps relative to spec). Code-quality covers craftsmanship (design, naming, bloat). Combining them buries critical findings under nits.
- Skipping code quality review (step 3) because validator passed — different bug class.
- **Blocking the main loop on a synchronous validator / code-quality review when nothing needs the result yet** — the verification tail is background-by-default; the only sync point is the fixup step. Sitting idle through a 10-30 minute sync review call is the measured top waste. Dispatch background, keep working, wait at step 4.
- Marking task complete with open Important findings unaddressed — apply defer-vs-fix triage instead.
- **Dispatching implementer without enforcing the pre-flight assumption block** — controller loses the chance to catch wrong assumptions before code is written; first surface of the assumption becomes the diff, by which point sunk-cost bias makes correction expensive.
- **Dispatching a task whose plan text predicts multiple file-clusters as one implementer, or dispatching without the soft-budget line** — 26-30 minute opaque sync calls were the single worst measured UX offender; the pre-split rule is the static catch, the soft budget the runtime backstop. Both belong in every dispatch.
- **Ignoring a SPLIT_PROPOSED return (telling the implementer "just finish it") without recording why** — the proposal is the budget doing its job; either dispatch the slices or note the authorization-to-continue in the journal "Plan deviations". Silently overriding it re-creates the opaque long call the budget exists to kill.
- **Letting implementer skip the surgical-scope clause** — silent drive-by edits (reformatting / "improved" comments / dead-code purge orthogonal to task) pollute the diff and break review traceability. Every changed line must trace to the task text.
- **Code reviewer skips the bloat-smell checklist because "design looks clean"** — clean design ≠ minimum design. Bloat smell is its own pass; run it explicitly.
- **Cross-layer phase dispatched as a single implementer** — atomic-commit invariant breaks; reviewers can't isolate BE vs FE concerns; FE+BE conflate into one diff. Split per `builder-split.md`.
- **Frontend builder dispatched before backend builder summary exists** — FE invents endpoints; mismatch surfaces in smoke or production. Sequence: BE → BE summary → FE reads summary → FE builds.
- **Validator given Edit/Write permissions** — reviewer who can edit, edits. Findings vanish into the edit, audit trail dies. Validator is read-only on `src/` always.
- **Acceptance verifier writing tests against internal functions** — that's a unit test, not an acceptance test. Verifier exercises the system from outside (HTTP / UI / observable side-effect only).
- **Acceptance verifier marking an AC "covered" without a passing test** — coverage means a green test, not "I checked the code and it looks right." If untestable, mark UNTESTABLE with reason.
