# PRD Template — Product-Facing Phase Synthesis

Optional brainstorm-stage artifact for **user-facing / product-shaped** phases. Adopted from Matt Pocock's `to-prd` skill ([mattpocock/skills](https://github.com/mattpocock/skills)).

**When to use:** phase delivers user-visible feature where stakeholder framing matters (a product owner / customer / non-engineer audience needs to read + sign off). Examples: new app surface, new entity in the product, redesign, externally-visible API.

**When NOT to use:** infrastructure / refactor / internal-tooling phases where there's no user-facing story. Use the standard spec doc only.

**Complement, not replace:** the PRD is product-facing (user stories + problem framing); the spec doc is engineer-facing (decisions + evidence tags + research citations). Both ship for user-facing phases; only spec ships for internal phases.

## Process

### 1. Synthesize from Context — Don't Re-interview

The PRD is generated from what's already in the conversation context after brainstorm. Do NOT re-interview the user. The brainstorm Q&A log + spec doc + CONTEXT.md already contain the material; the PRD reshapes it into product framing.

Explore the repo if not already done. Use CONTEXT.md vocabulary throughout. Respect ADRs in the area being touched.

### 2. Sketch Modules

Sketch the major modules to build or modify. Actively look for opportunities to extract **deep modules** that can be tested in isolation (small interface, deep implementation, rarely changes).

Check with user:
- Do these modules match expectations?
- Which modules need tests written for them?

### 3. Write the PRD

Use the template below. Publish to project issue tracker if the project tracks; otherwise commit to `docs/superpowers/specs/YYYY-MM-DD-phase-N-<slug>-prd.md` alongside the engineer-facing spec doc.

Apply the `ready-for-agent` triage label (or project equivalent) if publishing to tracker.

## Template

```markdown
# {Phase title — product-facing}

## Problem Statement

The problem the user is facing, from the user's perspective. Use CONTEXT.md vocabulary. Avoid implementation jargon.

## Solution

The solution to the problem, from the user's perspective. What can the user DO after this phase ships that they couldn't before?

## User Stories

A LONG, numbered list of user stories. Each in the format:

1. As an <actor>, I want a <feature>, so that <benefit>

Examples:
1. As a mobile bank customer, I want to see balance on my accounts, so that I can make better informed decisions about my spending.
2. As a mobile bank customer, I want to filter transactions by date range, so that I can find a specific charge quickly.
3. As an account holder, I want to label transactions, so that I can categorize my spending over time.

This list MUST be extensive and cover all aspects of the feature. 10-30 stories is normal. If you have <5, you haven't thought hard enough.

## Implementation Decisions

A list of implementation decisions that were made. Include:

- Modules built / modified
- Interfaces of those modules
- Technical clarifications from the developer
- Architectural decisions
- Schema changes
- API contracts
- Specific interactions

Do NOT include specific file paths or code snippets — they go stale fast.

**Exception:** if a prototype produced a snippet that encodes a decision more precisely than prose can (state machine, reducer, schema, type shape), inline it within the relevant decision + note briefly it came from a prototype. Trim to decision-rich parts only.

## Testing Decisions

- What makes a good test (only test external behavior, not implementation details)
- Which modules will be tested
- Prior art for tests (similar test types in the codebase)

## Out of Scope

A description of things out of scope for this PRD. Explicit no's prevent scope creep and tell future readers what was deliberately left out.

## Further Notes

Any further notes about the feature.
```

## Relationship to Other Artifacts

| Doc | Audience | Lives | When Created |
|---|---|---|---|
| `brainstorming-qa-log.md` | AI + audit | project root `docs/` | Every brainstorm Q |
| `phase-N-design.md` (spec) | Engineers + reviewers | `docs/superpowers/specs/` | After brainstorm locks |
| `phase-N-prd.md` (this doc) | Product owner + stakeholders | `docs/superpowers/specs/` | After brainstorm locks, user-facing phases only |
| `phase-N.md` (plan) | Implementer + reviewers | `docs/superpowers/plans/` | After spec + PRD sign-off |
| FACT journal entry | PR reviewers + product owner | `docs/journal.d/<date>-<branch-slug>.md` | After phase implementation done, at track close (replaces the retired `phase-N-handoff.md` — see `references/handoff-template.md`) |

PRD + spec ship together for user-facing phases. PRD ships to issue tracker if project tracks; spec stays in repo.

## Anti-patterns

- **Re-interviewing the user when writing the PRD** — context already exists from brainstorm. Synthesize from it. PRD is a reshape, not new info-gathering.
- **<5 user stories** — feature isn't decomposed enough. Push harder.
- **User stories framed as developer tasks** — "As a developer, I want to refactor X" is NOT a user story. Re-frame from the actual user's POV.
- **Implementation decisions w/ file paths + code snippets** — goes stale fast. Behavior + module names + interfaces only.
- **No "Out of Scope" section** — scope creeps; future readers can't tell what was deliberately excluded.
- **PRD written for internal-only phase** — wasted ceremony; just ship the spec doc.
- **Vocabulary drift from CONTEXT.md** — PRD invents new terms instead of using glossary. Sync back to CONTEXT.md if new term is needed.
