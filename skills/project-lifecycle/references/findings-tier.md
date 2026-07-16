# Findings Tier Triage

Every smoke finding / review concern / known limitation gets a tier. The tier drives the action.

## The three tiers

### S1 — Must fix before merge

**Definition:** blocks the phase from shipping. PR cannot merge until resolved.

**Examples:**
- Core flow doesn't work (S1 step in checklist fails)
- 500 / 400 on the happy path
- Security vulnerability (auth bypass, authorization boundary leak, secret exposure)
- Data corruption (writes to wrong scope/account, soft-delete doesn't cascade)
- Wrong copy on a high-traffic surface (e.g. label misspelled on the save button)
- Build / type check fails in CI

**Action:** fix in this phase. Add a `fix(...)` commit. Re-run smoke for the affected step.

### S2 — Should fix, post-merge follow-up

**Definition:** real bug or polish gap, but doesn't block this phase shipping. Tracked in a follow-up issue, scheduled in a later phase or a dedicated polish sprint.

**Examples:**
- Cosmetic bug (toast displays raw JSON, modal closes too fast)
- UX nit on a secondary surface (form doesn't auto-focus the right field)
- Performance issue under known load conditions but not in normal use
- Stale client-side data cache requiring user refresh
- Missing entity name in API response (causes blank UI text but data is correct)

**Action:** log in the journal entry's findings section, open a follow-up issue with label like `polish-X.Y` or `post-mX.Y`, add to the next polish/maintenance phase backlog.

### S3 — Deferrable, later phase or out of scope

**Definition:** real but not urgent. Architectural improvement, nice-to-have feature, or work that genuinely belongs in a future milestone.

**Examples:**
- "It'd be nicer if the picker also showed a hint when the user pauses typing" (UX enhancement)
- "We don't have a toast aggregation system yet — the spec said this should be aggregated" (cross-cutting feature gap)
- "The audit log doesn't yet have a filter UI" (separate phase scope)
- "Should this be cached in Redis?" (perf optimization, no current pain)

**Action:** log in the journal entry's findings section and name the phase that should cover it — but do NOT open an issue yet. Will get picked up when relevant milestone planning happens.

## Decision tree

```
A finding surfaces. Should I fix it now?

  1. Does it break the core flow? YES → S1
  2. Is it a security / data integrity issue? YES → S1
  3. Is it on a high-traffic surface (homepage, save button, etc.)? YES → likely S1
  4. Is it cosmetic / polish on a secondary surface? → S2
  5. Is it a real bug with a workaround? → S2
  6. Is it a nice-to-have, no current pain? → S3
  7. Is it cross-cutting work that belongs in a different milestone? → S3
```

## When in doubt, escalate up (not down)

If you can't decide between S1 and S2, treat it as S1 and ask the product owner. Better to fix something that wasn't needed than ship a regression.

## Findings format (journal findings section + smoke checklist findings file)

Stable IDs: `F1`, `F2`, ... per phase. Once assigned, the ID does NOT change even if the finding gets fixed and moved to a different tier.

```markdown
### Must-fix (S1)
- none open

### Should-fix (S2 — post-merge follow-up)
- **F1** — Draft restore wipes nested field
  - Repro: open /new-entry, fill nested row, leave, come back, click "Restore draft" → nested row absent
  - Workaround: full reload (Cmd+Shift+R)
  - Fix idea: invalidate query cache after reset(draft)
  - Issue: #N (TBD)

### Deferrable (S3 — later phase)
- **F4** — aggregated notification not wired
  - Spec calls for an aggregated banner on save listing all flagged items
  - Defer to: next polish phase or the milestone where the underlying aggregation infra lands
```

Localized labels (e.g. translated S1/S2/S3 headers in any target language) can be added in the project's own copy of the template via the project's `CLAUDE.md`, but the skill ships the English form only.

## Anti-patterns

- Marking everything S1 to be "safe" — slows shipping; reviewers stop trusting tier signal.
- Marking S1 issues as S2 to ship faster — the regression hits production.
- Filing S2 follow-up issues that never get scheduled — open a tracking project/milestone, not orphan issues.
- Listing S3 items in handoff §7 without naming the phase that should cover them — guarantees they get lost.
- Reusing finding IDs across phases — keep them per-phase (F1 in Phase X.Y ≠ F1 in Phase X.Z).

## Tier sanity check

Before publishing the handoff doc, scan §7:
- If S1 list is non-empty → don't open PR yet. Fix or escalate.
- If S2 list is empty but there are known bugs you mentioned in chat → write them down, don't trust memory.
- If S3 list has 10+ items → you may have been over-broadening the spec. Push back to spec author.
