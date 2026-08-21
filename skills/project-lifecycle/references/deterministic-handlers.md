# Deterministic Handlers — Harness-Injected Pre-Steps

> "The harness checks the tool history and actually sees what happened. The login handler runs every agent loop just before we push to the traces. If we're on a login page, it fills in credentials and submits — programmatically, from the harness, not from the agent." — Tejas Kumar, ["Harnesses in AI: A Deep Dive"](https://www.youtube.com/watch?v=C_GG5g38vLU) (IBM, 2026)

A deterministic handler is a piece of **pure code** the harness runs on every agent-loop iteration BEFORE handing control to the LLM. It exists to handle failure modes that have ONE right answer — auth, secrets, pre-flight checks, environment setup — where letting the LLM "figure it out" wastes tokens, leaks secrets, or produces inconsistent results.

The LLM never sees the handler's internals. It only sees the handler's effect (a state change + an injected message). This is how a harness keeps the LLM grounded in reality.

## When to use a deterministic handler vs let the LLM do it

| Symptom | Handler | LLM |
|---|---|---|
| One right answer, every time | ✅ Handler | ❌ |
| Involves secrets / credentials | ✅ Handler (secrets never enter LLM context) | ❌ |
| LLM "fakes" success ("clicked login button" — but actually got 401) | ✅ Handler verifies + injects truth | ❌ (LLM lies because it can't see the truth) |
| Decision requires judgment / context / multiple options | ❌ | ✅ LLM |
| Multi-step reasoning over messy data | ❌ | ✅ LLM |
| Plumbing / state machine / auth flow | ✅ Handler | ❌ |
| Long-tail edge cases the harness author can't enumerate | ❌ | ✅ LLM (with verify loop per `verify-loop.md`) |

Heuristic: "Could a junior engineer write this as a 20-line function in 10 minutes?" If yes, deterministic handler. If "no, this needs judgment", LLM.

## Anatomy of a handler

```
function handler(session, context) -> { action_taken: string, message_for_llm: string } | null

  // 1. Cheap state check — exit immediately if not applicable
  if (state doesn't match this handler's trigger) return null

  // 2. Deterministic action (no LLM, no judgment, no probabilistic logic)
  perform the action (call API / set env / inject auth / write file / etc.)

  // 3. Return a structured signal the harness injects into the LLM's next turn
  return {
    action_taken: "logged_in_via_harness",
    message_for_llm: "Harness logged you in as user@example.com. Continue with the task."
  }
```

Three discipline rules:

1. **Pure code.** No LLM call inside the handler. No "let me ask Claude what to do" hidden in there. If you can't write it deterministically, it's the LLM's job.
2. **Exits early when not applicable.** Handlers run every loop iteration. The 99% case where the handler doesn't apply must cost <1ms — usually a single state check at the top.
3. **Always injects a visible signal.** When the handler DOES act, the LLM must see the action on the next turn (via injected message). Otherwise the LLM re-tries the same thing and the handler fires again — infinite loop. The signal also creates the audit trail.

## Where handlers attach in this skill's cadence

Handlers slot in at **cadence step 1 (builder dispatch)** as part of the builder's runtime, BEFORE each LLM turn. The builder's prompt template (see `references/builder-split.md`) gets a section:

```
This builder runs with the following deterministic handlers (do NOT re-implement
any of them in tool calls; they fire automatically):

  - <name>: <one-line description> — fires when <trigger>
  - <name>: <one-line description> — fires when <trigger>
  ...

When a handler fires, you will see a system message tagged [HARNESS] describing
the action. Continue with the task using the new state.
```

Concrete handler implementations live in project code (e.g., `src/harness/handlers/` or `.claude/handlers/` per project convention) and are wired into the builder's invocation by the orchestrator (e.g., `/ship`).

## Canonical handler examples

### 1. Auth / login handler

**Trigger**: current URL matches a known login page; or current API call returned 401/403.
**Action**: inject credentials from the secret store (env var, vault, keychain), submit the form / re-issue the request with token.
**Why it's a handler not an LLM job**: secrets must never enter LLM context; the action is deterministic per environment.
**Inject**: `[HARNESS] Logged in as <user>. Resuming previous request.`

### 2. Pre-flight lint handler

**Trigger**: builder just wrote a file with extension `.ts` / `.py` / `.go` / etc.
**Action**: run the project's formatter + linter on the changed file; if errors, attempt the formatter's auto-fix.
**Why it's a handler not an LLM job**: formatters produce one answer; letting the LLM reason about whitespace is wasteful.
**Inject**: `[HARNESS] Formatted <file> with prettier. 0 lint errors.` (or `[HARNESS] Lint failed: <error>. Fix before continuing.`)

### 3. Secret-leak guard handler

**Trigger**: builder just wrote a file; harness greps for known secret patterns (`API_KEY=`, `Bearer ey...`, `-----BEGIN PRIVATE KEY-----`).
**Action**: revert the write; alert.
**Why it's a handler not an LLM job**: zero-tolerance check; LLM judgment introduces false negatives that cost real money / trust.
**Inject**: `[HARNESS] BLOCKED: secret-like pattern detected in <file>. Use env vars; reference by name.`

### 4. Migration-safety handler

**Trigger**: builder added a new migration file to `migrations/`.
**Action**: run the migration against a throwaway DB clone; assert success + rollback. Block the commit if either fails.
**Why it's a handler not an LLM job**: migrations either apply or they don't; LLM "looks right to me" is not safety.
**Inject**: `[HARNESS] Migration <file> applied + rolled back cleanly. Safe to commit.` (or `[HARNESS] Migration FAILED at step <N>: <error>. Fix before commit.`)

### 5. Test-failure attribution handler

**Trigger**: builder ran the test suite (via verify-loop) and got failures.
**Action**: parse the failure list; for each, run `git blame` on the failing line to attribute pre-existing failures (NOT caused by this builder's diff) vs. regressions (caused by this builder's diff).
**Why it's a handler not an LLM job**: attribution is mechanical; LLM tends to claim "this test was already broken" without checking.
**Inject**: `[HARNESS] 3 test failures: 1 regression introduced by this diff (file:line), 2 pre-existing (last touched by <user> in <commit>).`

### 6. Tenant-isolation tripwire

**Trigger**: builder wrote a SQL query / ORM call against a tenant-scoped table.
**Action**: pattern-match for missing `WHERE tenant_id = …` or equivalent ORM scope.
**Why it's a handler not an LLM job**: tenant isolation is a binary safety property; either every query is scoped or you have a data leak.
**Inject**: `[HARNESS] Query at <file:line> missing tenant scope. Add WHERE tenant_id = current_tenant() or the equivalent <ORM scope>.`

## Wiring handlers into a builder dispatch

In the orchestrator (e.g., `/ship` Phase 3 backend-builder dispatch):

```
1. Controller loads the handler set for this builder (from project's
   .claude/handlers/<builder>.json or hardcoded in /ship's prompt).
2. Controller injects the handler list into the builder's system prompt
   (see template above) — the LLM knows handlers exist + what they do.
3. Each agent loop iteration:
   a. Handlers run in order. First handler to return non-null wins for
      this iteration (subsequent handlers wait for the next iteration).
   b. The handler's `message_for_llm` is injected as a system message
      tagged [HARNESS] into the LLM's next turn.
   c. LLM proceeds with the new state visible.
4. If a handler blocks (e.g., secret leak, migration fail), the loop
   exits with status BLOCKED and the message is escalated to the
   controller.
```

## Discipline rules

- **One handler, one trigger.** Don't combine "auth" and "format" in one handler — splitting keeps each handler ≤30 lines and trivially testable.
- **Cheap-state-check at the top.** Handlers run on every iteration; expensive checks (subprocess spawns, network calls) inside the early-exit path = budget burn.
- **Always return a message when the handler acts.** No silent action — every action is visible to the LLM (so it doesn't re-try) and to the audit log (so reviewers can see what happened).
- **Never call an LLM inside a handler.** That's a different agent, not a handler. (If you need LLM judgment inside a sub-step, dispatch a subagent from the controller, not from within a handler.)
- **Test handlers like pure functions.** They are pure functions. Unit-test them with mock sessions.
- **Version-control the handler set per project.** `.claude/handlers/` checked into the repo; team-shared, like project-level slash commands per `references/onboarding.md`.

## Anti-patterns

- **"I'll just prompt the LLM to log in via the credentials in CLAUDE.md"** → secrets leak into LLM context, into logs, into transcripts shared with reviewers. Use a handler.
- **Handler that uses an LLM to "decide if this is a login page"** → defeats the purpose; handler is no longer deterministic. Use a regex / URL check / DOM selector.
- **Handler that fires every iteration whether or not it applies** (because the state check is wrong) → infinite loop. Always exit early when the trigger doesn't match.
- **Handler that acts silently** (no `message_for_llm`) → LLM re-tries the same failing action; another iteration fires the handler again; loop. Always inject visible signal.
- **Putting business logic in a handler** ("if the user is on the pricing page, automatically select the Pro plan") → that's product logic, not a harness concern. Handler scope is plumbing (auth / secrets / safety / format / attribution). Business logic belongs in the application.
- **Skipping the handler because "the LLM did it last time"** → the LLM is non-deterministic; "last time" doesn't predict this time. Every iteration that needs auth/safety/format gets the handler treatment.

## Path to dynamic handlers (Tejas Kumar's prediction)

The static handler set described above is the 2026 pattern. The next step (Tejas's "year of dynamic on-the-fly harnesses"): the orchestrator inspects the task, the codebase, and the failure history → generates a handler set tailored to THIS task → runs it.

This skill is positioned for that step:
- `references/builder-split.md` already lets the orchestrator pick which builder to dispatch based on phase shape.
- `commands/ship.md` already chains researcher → story → spec → builders dynamically per the feature.
- `/init-harness` scaffolds a handler set (lint, secret guard, migration safety, tenant isolation) from the project's detected stack and risk markers, with the project-specific logic left as `TODO`.

It runs once per project, at bootstrap — the handler set is derived from the project's detected risks, not from the feature being built. Deriving a handler set per feature, as a step inside `/ship`, is not built.

## Cross-reference

- `references/verify-loop.md` — verify is "did this work?" (loop). Handler is "do this first" (pre-step). Both are harness primitives; complementary.
- `references/builder-split.md` — builders are where handlers attach in this skill.
- `references/cadence.md` — step 1 builder dispatch + step 2 validator (validator confirms handler injections are honest).
- `references/ci-cd-gates.md` — pre-commit hooks are the CI-side equivalent of these handlers (same idea, different runtime).
- `references/diagnose-loop.md` — when a handler keeps firing on the same trigger across iterations, that's a hard-bug symptom; switch to diagnose-loop.
