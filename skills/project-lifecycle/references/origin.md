# Skill Origin

This skill was distilled from a working practice and validated against one pilot milestone before being formalized.

- **Pilot run:** one milestone of a real production project.
- **Pilot evidence:** the cadence as it stood at the pilot — five steps, before the acceptance-verifier step was added — was applied to every task of the milestone, and every plan deviation it surfaced was documented as it happened.

## What the pilot validated

- Two independent reviewer agents (spec compliance + code quality) catch disjoint bug classes; single-reviewer flows miss one or the other.
- Fixup commits as separate commits preserve the review trail in `git log`; squashing erases it.
- Pre-commit hooks must run locally before commit, not at PR time — at least one CI failure in the pilot was attributable to skipping the local run.
- Plan deviations are routine; capturing them in the journal entry under a required header forces an active drift check.
- "Forward-looking" review findings (works now but downstream task will be hurt) are real and don't fit cleanly into spec compliance or code quality review.
- Cadence compression for trivial mechanical tasks saved agent invocations without missing bugs.

## Companion artifacts

- `superpowers:brainstorming` — Q&A capture this skill calls into.
- `superpowers:writing-plans` — implementation plan generation this skill calls into.
- `superpowers:subagent-driven-development` — per-task execution mechanics this skill wraps.
- `superpowers:writing-skills` — the skill that produced this one (TDD applied to documentation).
