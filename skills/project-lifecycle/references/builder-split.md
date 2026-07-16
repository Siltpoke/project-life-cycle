# Builder Split — Backend vs Frontend, Folder-Scoped

Cadence step 1 (implementer dispatch) splits into **backend-builder** and **frontend-builder** for any phase that spans both layers. Two separate subagent dispatches, each with **physically scoped tool access** to its own folders.

> **When BE + FE run concurrently**, folder-scoped tools are a soft boundary; the
> physical one is `isolation: "worktree"` on each `Agent` dispatch (separate git
> worktrees so parallel writes can't collide). Use it only when actually
> parallelizing — the default BE→summary→FE sequence does not need it, and worktree
> setup has real per-agent cost. See `references/harness-primitives.md` §5.

## Why split

Single implementer pattern fails in three ways on cross-layer phases:

1. **Atomic-commit drift** — implementer "just touches" a UI file while building the API, or vice versa. The diff conflates two concerns; reviewers can't isolate.
2. **Context bloat** — one subagent reads the entire BE codebase *and* the entire FE codebase. Context fills with material it doesn't need, output quality degrades on the half it's currently writing.
3. **API contract is implicit** — no point in the workflow where "the BE has finished and the FE consumes it" is enforced. FE invents endpoints; BE adds fields the FE doesn't use; mismatch surfaces in smoke or production.

Splitting fixes all three:

- Each builder's diff is layer-pure. Atomic-commit invariant holds.
- Each builder reads only its layer. Context stays tight.
- BE finishes first + emits a summary. FE reads the summary as the API contract. Mismatch is impossible (or visible immediately when FE flags "the BE shape doesn't fit the UI need").

## When to split

**Split** when phase touches both layers:
- New endpoint + new UI consuming it
- Schema change + UI surfacing the new field
- New background job + UI status display

**Don't split** when phase is layer-pure:
- BE-only refactor / new endpoint with no UI
- FE-only redesign / new component over existing API
- Infra / tooling / docs

**Don't split** when project is single-layer (CLI tool, library, pure BE service).

## Folder map (in `CLAUDE.md`)

Each project declares its folder boundaries in `CLAUDE.md`:

```yaml
folder-map:
  backend:
    - src/api/
    - src/services/
    - src/jobs/
    - src/db/
    - migrations/
    - tests/api/
    - tests/services/
  frontend:
    - src/components/
    - src/pages/
    - src/hooks/
    - src/lib/client/
    - tests/components/
    - tests/pages/
  shared:
    - src/types/         # type defs both consume (carefully edited by either with explicit reason)
    - src/lib/shared/
  forbidden-cross:
    - src/components/* may NOT import from src/db/ or src/services/
    - src/api/* may NOT import from src/components/ or src/pages/
```

If `folder-map` is missing, **controller must elicit it from the user before dispatching builders** — don't guess. Single-layer projects can set `folder-map: single-layer` to skip the split.

## Backend builder prompt template

```
You are the BACKEND builder for task T-N.

Scope (allowed write paths — anything else is forbidden):
{folder-map.backend, joined}

Shared paths (write ONLY if absolutely required + state reason in summary):
{folder-map.shared, joined}

You are forbidden to:
- Edit any file under {folder-map.frontend, joined}
- Add new dependencies without instruction
- Modify files outside the allowed paths

Task: {task text}
ACs this task closes: AC{n}, AC{m}, ...
Spec sections: {file links}
Pre-flight assumption block: MANDATORY before any code (see cadence.md §step-1).
Surgical scope clause: MANDATORY (see cadence.md §step-1).
Vertical-slice TDD: MANDATORY (1 test → minimal impl → next).
Soft time budget: MANDATORY (see cadence.md §step-1) — note start time in
pre-flight and a fresh date at each resume-after-STOP; active work = sum
of resume→STOP segments only (controller waits never count); re-check
every ~10 tool calls; past ~15 min of active work, STOP and return
SPLIT_PROPOSED (done-so-far summary, UNCOMMITTED + proposed vertical
slices).

When done, output the BACKEND SUMMARY (see below).
Status: DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT | SPLIT_PROPOSED.
```

## Frontend builder prompt template

```
You are the FRONTEND builder for task T-N.

Scope (allowed write paths — anything else is forbidden):
{folder-map.frontend, joined}

Shared paths (write ONLY if absolutely required + state reason in summary):
{folder-map.shared, joined}

You are forbidden to:
- Edit any file under {folder-map.backend, joined}
- Invent endpoints or response shapes not in the Backend Summary
- Add new dependencies without instruction

READ FIRST: Backend Summary from prior dispatch (pasted below).
If the API shape doesn't fit the UI need, STOP and report mismatch — do NOT silently
work around it (no client-side massaging of bad shapes, no "stitching" two endpoints
to fake one). Mismatch goes back to BE builder.

{paste of Backend Summary}

Task: {task text}
ACs this task closes: AC{n}, AC{m}, ...
Spec sections: {file links}
Pre-flight assumption block: MANDATORY.
Surgical scope clause: MANDATORY.
Vertical-slice TDD: MANDATORY.
Soft time budget: MANDATORY (see cadence.md §step-1) — note start time in
pre-flight and a fresh date at each resume-after-STOP; active work = sum
of resume→STOP segments only (controller waits never count); re-check
every ~10 tool calls; past ~15 min of active work, STOP and return
SPLIT_PROPOSED (done-so-far summary, UNCOMMITTED + proposed vertical
slices).

When done, output the FRONTEND SUMMARY.
Status: DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT | SPLIT_PROPOSED.
```

## Builder Summary format (both layers)

Each builder ends its run with a structured summary the next stage consumes:

```markdown
## {BACKEND|FRONTEND} Summary — Task T-N

### Files added
- path/to/new-file.ts — purpose

### Files edited
- path/to/existing.ts — what changed in one line

### ACs claimed closed
- AC3 (covered by `src/api/foo.ts` + unit test `tests/api/foo.test.ts:42`)
- AC4 (covered by ...)

### Reused patterns / helpers
- Used `existingValidator()` from src/lib/validation.ts (already in use elsewhere)
- Followed pattern from src/services/billing.ts (same shape as adjacent service)

### NEW infra introduced (if any — flag explicitly for reviewer)
- Added new BullMQ queue `reminders` — first user of this queue category

### Cross-layer contract (BACKEND only) — what FE will consume
- Endpoint: POST /api/reminders/send
  - Request: { invoiceId: string }
  - Response 200: { sentAt: ISO8601, recipientEmail: string }
  - Response 404: { error: "invoice_not_found" }
  - Response 403: { error: "cross_tenant_denied" }
  - Auth: requires session cookie + tenant match on invoice
- DB shape change: invoices.last_reminder_sent_at (nullable timestamp)
- Background job: `send-reminder` enqueued on POST, BullMQ retries 3x

### CLAUDE.md gaps (rules that would have helped)
- "Reminders use BullMQ, not cron" was not in CLAUDE.md — suggest adding

### Tests passing
<!-- narrative counts alone never count as evidence (cadence.md §step-2 lie
     detection) — each claim cites the test file the diff contains -->
- 12 unit tests passing — `tests/api/foo.test.ts`, `tests/api/bar.test.ts`
- Lint clean, typecheck clean — commands run: `bun lint`, `bun typecheck`
```

The **Cross-layer contract** section is what the FE builder consumes verbatim. It's the API specification frozen by the backend dispatch.

## Sequencing rules

1. **Backend builder runs first**. Always. FE has nothing to consume otherwise.
2. **Backend summary is human-reviewed before FE dispatch** when the contract section is non-trivial (new endpoint, schema change, breaking shape). Reviewer = controller agent + (optionally) user. Trivial cases (1 field added to existing response) skip the review.
3. **Frontend builder reads the Backend Summary as input**, not the BE source code. Forces the contract to be self-describing.
4. **If FE flags a mismatch** ("the contract returns flat fields but the UI needs a tree shape"), it does NOT patch client-side. It goes back to BE builder with a contract-revision task. New BE summary. Then FE proceeds.
5. **Parallel builders only when layers are truly independent** — two BE-only tasks against disjoint folders, or BE-only + FE-only tasks with no contract relationship. Rare. Default is sequential.

## Folder boundary enforcement

- Controller checks the diff after each builder returns. Any file modified outside the allowed paths → reject the dispatch, ask for explanation, possibly re-dispatch with corrected scope.
- Pre-commit hook (recommended) greps the diff against `forbidden-cross` rules — fails commit if a frontend file imports from backend folders.
- Review (cadence step 2) explicitly checks folder boundary as part of spec compliance.

## Anti-patterns

- **Single implementer for cross-layer phase** — splits the atomic-commit invariant. Use the split.
- **FE builder dispatched without BE summary** — FE invents endpoints. Block.
- **FE silently massaging a bad BE shape** ("I'll just flatten the array client-side") — hides the real bug (the contract is wrong). Surface as mismatch; revise contract.
- **BE builder editing FE files because "I needed to update a type"** — types in `shared/` belong to either, but only with explicit reason logged in summary. BE editing a component is a scope violation.
- **`folder-map` missing from CLAUDE.md + builder dispatched anyway** — guessing boundaries leaks scope. Elicit first.
- **Builder summary missing "Cross-layer contract" on BE side** — FE has nothing to read. Re-dispatch with summary requirement.
- **Reviewing the builder split as one combined diff** — defeats the split. Review BE diff and FE diff separately (different lens, different reviewer focus).
- **Allowing builder to add new dependencies silently** — both BE and FE must surface new deps explicitly; controller decides if they're acceptable.
