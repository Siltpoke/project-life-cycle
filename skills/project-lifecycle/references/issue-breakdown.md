# Issue Breakdown — Plan → Vertical-Slice Tracer-Bullet Issues

Optional Step 4b in the per-phase workflow. Use when the project uses an issue tracker (GitHub Issues / Linear / Jira) and the plan needs to be split into independently-grabbable units for async agents or distributed contributors. Adopted from Matt Pocock's `to-issues` skill.

**Skip this step if:** the phase is owned end-to-end by a single agent / contributor, or the project doesn't issue-track. In those cases the single plan doc + phased branch is enough.

## Vertical Slice = Tracer Bullet

Each issue is a **thin vertical slice** that cuts through ALL integration layers end-to-end, NOT a horizontal slice of one layer.

**Rules:**
- Each slice delivers a narrow but COMPLETE path through every layer (schema → API → UI → tests)
- A completed slice is demoable or verifiable on its own
- Prefer many thin slices over few thick ones

### Horizontal vs Vertical (don't get this wrong)

```
WRONG (horizontal — layer-by-layer):
  Issue 1: All schema changes
  Issue 2: All API endpoints
  Issue 3: All UI components
  Issue 4: All tests

RIGHT (vertical — feature-by-feature):
  Issue 1: Create pitch (schema bit + API endpoint + UI form + tests)
  Issue 2: List pitches (schema view + API list + UI page + tests)
  Issue 3: Delete pitch (schema cascade + API endpoint + UI button + tests)
```

Horizontal slices appear productive but produce no demoable behavior until all layers ship together. Vertical slices ship behavior incrementally and surface integration issues early.

## HITL vs AFK Labels

Each slice is tagged for execution mode:

- **AFK** — Can be implemented and brought to PR-ready without human interaction; **the merge itself always stays human** (egress policy: an unattended loop's terminus is a pushed `loop/` branch + an exit report, and nothing further — no PR, no merge, no tag, no publish). Default; prefer this.
- **HITL** — Requires human interaction (architectural decision, design review, ambiguous requirement, UX call). Use sparingly.

**Bias toward AFK.** HITL is a sign the slice has unresolved questions that should have been answered during brainstorm. If many slices are HITL, the brainstorm under-resolved — go back to step 1 before issue-breakdown.

## Process

### 1. Gather Context

Work from the plan doc already produced in Step 4. If user passes an issue reference (number / URL / path), fetch its full body and comments first.

### 2. Explore Codebase (if not already done)

Issue titles and descriptions MUST use the project's CONTEXT.md vocabulary. Respect ADRs in the area being touched.

### 3. Draft Vertical Slices

Break the plan into tracer-bullet issues. For each slice, capture:

- **Title** — short descriptive name using CONTEXT.md vocabulary
- **Type** — HITL or AFK
- **Blocked by** — which other slices must complete first
- **User stories covered** — which user stories this addresses (if source material has them)

### 4. Quiz the User

Present the proposed breakdown as a numbered list. Ask:

- Does the granularity feel right? (too coarse / too fine)
- Are dependency relationships correct?
- Should any slices be merged or split further?
- Are the correct slices marked HITL vs AFK?

Iterate until user approves.

### 5. Publish

Publish issues in **dependency order** (blockers first) so real issue identifiers can be referenced in "Blocked by" fields. Apply the project's "ready for agent" triage label (per project's `CLAUDE.md`).

Do NOT close or modify the parent issue.

## Issue Body Template

```markdown
## Parent

A reference to the parent issue on the tracker (if source was an existing issue, otherwise omit).

## What to build

A concise description of this vertical slice. Describe the end-to-end behavior, not layer-by-layer implementation.

Avoid specific file paths or code snippets — they go stale fast. Exception: if a prototype produced a snippet that encodes a decision more precisely than prose can (state machine, reducer, schema, type shape), inline it here and note briefly that it came from a prototype. Trim to decision-rich parts only.

## Acceptance criteria

- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3

## Blocked by

- #<ISSUE-N> — title of blocking ticket

Or "None — can start immediately" if no blockers.
```

## Anti-patterns

- **Horizontal slicing** (one issue per layer) — produces undemoable interim states; ship one slice = ship nothing. Always vertical.
- **One mega-issue for the whole phase** — defeats the point of breakdown; can't parallelise; can't track partial progress.
- **HITL on everything** — means brainstorm under-resolved. Go back, finish the brainstorm, then re-slice.
- **Slices with overlapping file ownership** — parallel agents conflict. Either serialize (Blocked by) or restructure slices.
- **Issue body w/ file paths + code snippets** — goes stale fast. Describe behavior + acceptance criteria; let implementers find the files.
- **Publishing out of dependency order** — "Blocked by" references break or get backfilled later. Publish blockers first.
- **Closing / modifying the parent issue when publishing children** — parent stays open as tracking issue.
