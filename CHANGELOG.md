# Changelog

All notable changes to the `project-lifecycle` plugin are documented here.

The format follows [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/); versioning follows [Semantic Versioning 2.0.0](https://semver.org/). Newest release is listed first. Comparison links below cover the release points this repository carries a tag for.

---

## [Unreleased]

Nothing yet.

## [3.0.0] - 2026-07-15

### Added

- Ships a deterministic close-gate that blocks pushing an incomplete phase branch.
- Adds three standalone commands — `/research`, `/review`, and `/handoff` — so research, code review, and session handoff can each run on their own instead of only inside a full project cycle.

### Removed

- **BREAKING** — the unattended ("AFK") run mode is removed from this plugin and now lives in a separate project; a project that referenced it must point at that project instead. The judgment for whether a request is safe to run unattended stays part of this plugin.

## [2.0.0] - 2026-07-14

### Added

- Adds a required evidence field to the journal's closing entry, so a decision can no longer be recorded without stating what supports it.
- Adds a file-count cap alongside existing size caps for retained project documents, catching growth that many small files caused but no size limit noticed.

### Changed

- **BREAKING** — closing a phase now requires a complete journal entry (decision, reasoning, evidence, rejected alternatives, source). A project upgrading from an earlier version must write one before its next phase close.
- Retires two standing documentation requirements (kept PR-draft bodies, a separate handoff file) in favor of the new journal entry and treating GitHub itself as the source of truth.

## [1.5.0] - 2026-07-11

### Added

- Adds a citation-coverage check for locked research decisions, flagging any decision that carries no supporting link.

### Changed

- Improves guided GitHub repository setup — it can now create the repository for you, instead of only linking to GitHub's own setup guide.
- Strengthens the research protocol: decisions are ordered by dependency, "skip research" is now a named and justified exception rather than a default, and a recommendation with no citation is treated as invalid output.

## [1.4.0] - 2026-07-10

### Added

- Adds a plain-language mode for non-technical users, with adjustable tone, first-use term explanations, and screenshot fallbacks.
- Adds guided GitHub repository setup and a guided deploy offer at project finish, for users without a technical background.
- Adds proactive, opt-in suggestions for high-value best practices as they come up during development.
- Adds an opt-in personal references log that can capture and analyze external material (repos, articles, videos) you share during research.

## [1.3.0] - 2026-07-10

### Added

- Adds project cognition memory: captures the stated intent behind decisions (the "why"), with a capped, cited, auto-distilled summary document.

## [1.2.1] - 2026-07-09

### Fixed

- Fixes task-list enforcement so it reliably requires a real task list (at least three items) on every run, instead of silently accepting a single item or none at all.

## [1.2.0] - 2026-07-09

### Changed

- Documentation cleanup: completes the reference index and folds a duplicate page into its parent document.

## [1.1.0] - 2026-07-09

### Added

- Adds a fragment-based writing convention for shared append-only documents (journal, QA log, changelog), so parallel branches of work stop colliding on the same file.
- Adds document retention: size and line caps on hot documents, an archival step at milestone close, and a human-gated distillation step.
- Adds a context-floor wiring check and a task-boundary reminder to clear context between phases.
- Adds a task-list-first enforcement hook, blocking the first edit of a session until a task list exists.

## [1.0.0] - 2026-07-07

### Added

- Adds native support for Codex, Qoder, CodeBuddy, and Antigravity, alongside Claude Code.
- Splits the README into a short landing page plus a full guide carrying the complete workflow narrative and repository map.

### Changed

- Relicenses from MIT to PolyForm Perimeter 1.0.1 (more restrictive than MIT — review the new terms if you redistribute).

## [0.12.0] - 2026-07-03

### Added

- Internal tooling; no user-facing change.

## [0.11.0] - 2026-06-30

### Added

- Adds an "archetype" classification (Builder / Prototyper / Sweeper / Grower / Maintainer) that shapes which review steps and quality checks a request goes through.
- For cleanup-only work, requires the change to actually shrink the codebase, or an explicit documented reason why not.

## [0.10.0] - 2026-06-26

### Added

- Adds an opt-in percentage-based trigger for the context floor, for models with much larger context windows.

## [0.9.1] - 2026-06-25

### Fixed

- Fixes the context-floor block message to show a percentage that matches what your own status line reports, instead of only raw token counts.

## [0.9.0] - 2026-06-24

### Added

- Adds a hard context-usage floor: past a configurable threshold, edits are blocked until you checkpoint your progress, closing the gap left by softer warnings.

## [0.8.0] - 2026-06-12

### Added

- Adds an unattended ("AFK") run mode with a required goal/stop/budget/report contract, a budget circuit-breaker, and an exit report — merging always stays a human action.

### Fixed

- Fixes enforcement hooks that silently failed to load under a plugin install, caused by an incorrect file path.

## [0.7.0] - 2026-06-11

### Changed

- Extends the hard-bug diagnosis workflow to check past lessons first and record a new one afterward, so the same root cause isn't re-discovered from scratch next time.

## [0.6.0] - 2026-06-11

### Added

- Adds a structured, auditable review record for AI code review: fresh context, read-only tools, evidence quoted per finding, and a verdict computed last rather than self-declared.
- Adds a coverage check confirming every commit since the last review round is actually covered before merge.

## [0.5.0] - 2026-06-11

### Added

- Adds a `close-gate` policy for choosing where human approval happens — every task, or once per pull request with an independent review filling the gap in between.
- Adds `/builder-profile`, a command that reads your own local session history and reports back how you actually use the coding agent — entirely local, nothing uploaded.
- Adds a rolling-archive pattern so a project's status file stays a manageable size instead of growing forever.

### Fixed

- Fixes a safety-guard false positive that blocked commits whose *message* merely mentioned `main` or `--no-verify`, rather than commands that actually did either.

## [0.4.0] - 2026-06-08

### Added

- Ships enforcement hooks: one blocks bypassing commit/push safety checks and direct pushes to the main branch, another reminds you to close out a phase properly.
- Adds an opt-in check that asks one reflection question about your own change after it ships, without keeping a running score.

### Changed

- Every pull request now opens with a short plain-language summary before the technical detail.

## [0.3.0] - 2026-05-28

### Added

- Adds `/init-harness`, which bootstraps a new or existing project with this plugin's conventions and starter documentation in one pass.
- Adds `/release`, which computes the version bump from the changelog, tags, and publishes a release automatically.
- Adds onboarding and verify-loop guides for bringing a new contributor (human or AI) up to speed safely.

### Changed

- The per-task validator now runs a lie-detection pass first, checking a builder's claims against the real diff before accepting them.

## [0.2.0] - 2026-05-27

### Added

- Adds a mandatory user-story and acceptance-criteria file for user-facing work, checked by a new independent acceptance-verifier step.
- Adds `/ship`, a command that runs one feature end-to-end (research, story, spec, build, verify, PR) with a few points where you confirm before continuing.
- Adds quality rules for optional HTML companion documents (accessibility, real data instead of placeholders, consistent styling).

### Changed

- Expands the per-task review cadence from 5 to 6 steps, adding the acceptance-verifier and a stricter, read-only validator.

## [0.1.0] - 2026-05-11

Initial release.

### Added

- Introduces the full spec → plan → execute → journal → milestone-done project workflow, plus a per-task cadence of implement → review → code-quality review → fix → journal.
- Adds a research protocol for locking design decisions, backed by a second, independent reviewer check.
- Adds Architectural Decision Records, a domain glossary convention, and delivery templates (issue breakdown, changelog, PR body).

[Unreleased]: https://github.com/Victoriakaey/project-life-cycle/compare/v3.0.0...HEAD
[3.0.0]: https://github.com/Victoriakaey/project-life-cycle/compare/v1.0.0...v3.0.0
[1.0.0]: https://github.com/Victoriakaey/project-life-cycle/compare/v0.4.0...v1.0.0
[0.4.0]: https://github.com/Victoriakaey/project-life-cycle/releases/tag/v0.4.0
