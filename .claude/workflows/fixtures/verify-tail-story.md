# Synthetic user story — verify-tail self-test (story-exists path)

Minimal 2-AC story used ONLY to exercise the story-exists orchestration branch of
verify-tail.mjs (verifier lane runs, then the validator joins on its report). The ACs
describe the verify-tail workflow's own observable contract.

## Acceptance criteria

- **AC1** — Given a task with a user story, the verification tail dispatches an acceptance
  verifier lane in parallel with code-quality, and the validator only starts after the
  verifier report lands.
- **AC2** — The merged return exposes a `holes` array that is empty when every dispatched
  lane returns a well-formed report.

## Out of scope

- The checkpoint-gated outer /ship chain.
