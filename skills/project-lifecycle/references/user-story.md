# User Story + Acceptance Criteria

The **source of truth** for everything downstream. Spec, plan, builders, acceptance verifier, and validator all anchor to this file.

## Why this exists

Spec describes *how* to build. PRD describes *product framing*. Neither produces a list of testable behaviors that proves the feature satisfies what the user actually asked for. The user story file does.

Without it:
- Acceptance verifier has nothing concrete to map tests to → "done" is judged by vibes.
- Validator can't say which requirement is unmet → reports become opinion lists.
- Builders silently expand or contract scope → reviewers can't tell what was promised.

With it:
- Every AC is a row in the acceptance test table.
- Every "done" claim is verifiable.
- Scope drift is visible (anything in code without an AC = scope creep; any AC without code = under-build).

## When to write it

**Mandatory** for any phase that delivers user-observable behavior (new feature, new endpoint, new UI surface, new CLI flag, new background job triggered by user action).

**Skip** for: pure refactor / dep bump / docs-only / internal-tooling phase with no observable behavior change.

## Position in the workflow

```
brainstorm → user-story.md → [HUMAN CHECKPOINT 1: approve story]
              ↓
            spec.md → [HUMAN CHECKPOINT 2: approve spec]
              ↓
            plan.md → builders → acceptance verifier → validator → fix loop
              ↓                                ↑
            [HUMAN CHECKPOINT 3: approve PR]   |
                                               |
              acceptance verifier reads user-story.md to derive test list
              validator reads user-story.md to check coverage
```

Approval gate before spec writing. No spec / plan / code until the story is signed.

## File location

`docs/superpowers/specs/YYYY-MM-DD-phase-N-<slug>-user-story.md`

Same dir as spec + (optional) PRD.

## Template

```markdown
# {Phase title — user voice}

## Story

As a {role}, I want {behavior}, so that {outcome}.

> One sentence. If two sentences are required, the story is two stories — split.

## Acceptance Criteria

Each AC is a single observable behavior, numbered, testable by an outside-the-system observer.

- **AC1**: {Given …, When …, Then …}
- **AC2**: …
- **AC3**: …

Cover:
- Happy path (≥1)
- Each failure path the user can trigger (≥1 per failure mode)
- Each business rule the story implies (≥1 per rule)
- Boundary cases the story implies (empty, max, zero, negative — if applicable)

Each AC must be:
- **Observable** from outside (HTTP response / UI state / DB row / emitted event / log line — never "internal state X is set")
- **Atomic** (single behavior, not "and / also")
- **Phrased so a test can verify it directly** — if you can't sketch the assertion in one sentence, the AC is too vague

## Out of Scope

Explicit no's. Things a reader might assume are in but are not. Prevents scope creep.

- {Behavior X — out, deferred to phase N+1}
- {Behavior Y — out, never; rationale: …}

## Edge Cases (for builder + verifier awareness)

Behaviors the story *doesn't directly require* but the builder needs to think about. These do not get acceptance tests unless promoted to ACs.

- {Tenant isolation: this endpoint must reject cross-tenant access}
- {Timezone: timestamps must be UTC at storage, local at render}
- {Retry safety: handler must be idempotent}

## Contingencies (pre-declared "when X → do Y")

Foreseeable mid-implementation situations with a pre-decided response, declared at story time and injected verbatim into the builder prompt (cadence step 1). The builder consults this list before escalating: a situation matching a declared contingency follows the pre-decided action (noted in the Builder Summary); only undeclared surprises escalate via BLOCKED / NEEDS_CONTEXT.

- {When the third-party API rate-limits during backfill → switch to batched mode, log a Findings entry}
- {When the migration finds rows violating the new constraint → abort, surface the row count, do NOT auto-fix data}
- or: `none` — written explicitly. Absence must be a decision, not an omission.

Rules:
- Format is `when <observable situation> → <single pre-decided action>`. "Handle gracefully" is not an action.
- Only situations foreseeable at story time. Mid-task surprises still follow status reporting + `diagnose-loop.md`.
- A contingency is NOT an AC — it gets no acceptance test unless promoted to one.

## Invariants (machine-checkable, optional)

Phase-specific constraints that pure code can verify — distinct from ACs (behavior promises) and Edge Cases (builder awareness). Each entry MUST ship with a runnable check command; an invariant without a command is an Edge Case, not an invariant.

- {No response payload exceeds 1 MB → `bun run check:payload-size`}
- {Schema round-trips losslessly → `make schema-roundtrip`}

Rules:
- Run each declared command once at declaration time (it must work and must be able to fail — a check that cannot fail, e.g. `echo ok`, is rejected).
- At phase close, run all declared invariant commands and include output in the test-evidence/PR comment. The canonical close gate in `references/close-gate.md` does not run them, so this step is by hand.

## Open Questions

Things genuinely unknown. NEVER guess — list them, surface to user, block on answers.

- {Q1: …}
- {Q2: …}

## Sign-off

- [ ] User approved this story on {date}
- [ ] Out-of-scope list reviewed
- [ ] Open questions resolved or accepted as deferred
```

## How downstream artifacts use this

| Downstream artifact | What it pulls from user-story.md |
|---|---|
| `spec.md` | Maps each AC → data model / API / file changes needed to satisfy it |
| `plan.md` | Tasks are organized so each task closes ≥1 AC (no orphan tasks, no orphan ACs) |
| Backend builder | Implements ACs assigned to its scope; cross-checks scope against "Out of Scope" before adding anything; receives Contingencies verbatim in its prompt |
| Frontend builder | Same; reads BE builder summary to consume API contract |
| Acceptance verifier | Writes 1 test per AC; reports per-AC pass/fail |
| Validator | Reports any AC without test coverage, any code without an AC, any "Out of Scope" item that snuck in |
| PR body §1 | User-facing summary derived from story + ACs ("After this PR, user can: AC1 paraphrased, AC2 paraphrased, …") |

## Conventions

- **AC IDs are stable** — never renumber. If AC2 is dropped mid-phase, leave the gap (AC1, AC3, AC4) so test names + journal references stay valid.
- **AC IDs appear in test names** — `test_AC3_rejects_invalid_email`, `test_AC7_emails_user_on_failure`. One-to-one mapping makes coverage trivial to audit.
- **Promote edge case → AC** if it gets a test. Anything in the test file must trace to a numbered AC.
- **Edit the file as ACs sharpen during brainstorm** — append a note `AC2 (refined 2026-05-27: was "user can ...", now requires explicit confirm)`. Don't silently rewrite history.

## Anti-patterns

- **AC phrased as implementation** — "AC3: stores user ID in `users` table" → reframe as observable ("AC3: a registered user can log in within 5 minutes of registering"). Storage is a *how*, not a *what*.
- **AC vaguer than "Given/When/Then"** — "AC4: works correctly" is not an AC. If you can't sketch the assertion, you can't test it.
- **AC bundling multiple behaviors with "and"** — split. One AC = one test = one verifier output row.
- **Missing "Out of Scope" section** — scope creeps. Validator can't flag drift if there's nothing to compare against.
- **Open questions hidden inside ACs** — surface them in the dedicated section. ACs are decisions, not questions.
- **Skipping the file for "this is obvious"** — the obvious feature is where the most scope creep happens, because nobody wrote down what "done" means.
- **Renumbering ACs mid-phase** — breaks test names, journal links, validator references. Append, don't renumber.
- **Writing the spec before the story is approved** — defeats the checkpoint. Spec assumptions baked into a wrong story = expensive rewrite. Stop and get the story signed.
- **Contingency phrased without an observable trigger or a single concrete action** — "when things go wrong → be careful" gives the builder nothing. Either sharpen to `when <observable> → <action>` or delete it.
- **Builder improvises on a situation a declared contingency covers** — the pre-decided action exists precisely so the builder doesn't guess; re-dispatch with the contingency quoted.
- **Invariant declared without a runnable check command** — that's an Edge Case wearing an invariant's name. Move it, or write the command.
