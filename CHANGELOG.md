# Changelog

All notable changes to the `project-lifecycle` plugin are documented here.

The format follows [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/); versioning follows [Semantic Versioning 2.0.0](https://semver.org/). Newest release is listed first. Comparison links below cover the release points this repository carries a tag for.

---

## [Unreleased]

Nothing yet.

## [3.7.0] - 2026-07-25

### Added

- Adds an optional per-pull-request verification gate: a reviewer's report is checked against your acceptance criteria before merge, including a check that your code's own safety guards still catch real breakage — not just that tests pass.
- The independent second-opinion review used during brainstorming can now run on a different AI assistant (opt-in), for a genuinely independent perspective.
- Adds `/tasklist`, a terminal reader for the `.claude/tasklist.md` checklist file, so you can see the current task list at two levels of detail without opening the file. Works on every supported CLI.

### Changed

- The close-gate now runs in two modes — a check on every commit, and a stricter check before merge — so the first finished piece of a phase can be pushed right away instead of waiting for the whole phase to close.
- Renames this plugin's `/resume` command to `/recall`, so it no longer collides with Claude Code's own built-in `/resume` (which reopens a past conversation rather than briefing you from the saved digest). Behaviour is unchanged; update anything that invoked the old name.

### Fixed

- Fixes several safety-hook bugs: a push-safety check that matched on the wrong text, a reminder that could re-arm itself even after a failed check, and file "freshness" checks that are now proven from file content rather than a timestamp that file-syncing tools can silently alter.

## [3.6.0] - 2026-07-19

### Added

- Adds `/reconcile`, which finds roadmap or status decisions made in conversation or shipped in merged changes but never written down, and proposes them back into your project's roadmap and status docs for your approval.

## [3.5.0] - 2026-07-18

### Added

- `/catchup` now renders a richer roadmap view — pinned project vision, a "you are here" marker, collapsed completed work, and expanded detail for the current and upcoming stations.

## [3.4.0] - 2026-07-17

### Added

- `/handoff` now archives the previous session snapshot before overwriting it, so a full history of past continuity notes accumulates instead of being lost on every write.

### Fixed

- Fixes `/catchup` and `/resume` failing outright on plugin installations, caused by an incorrect internal file path.

## [3.3.0] - 2026-07-17

### Added

- Adds `/catchup`, a warm "welcome back" summary combining your git state, your saved status file, and your last session's digest.

## [3.2.0] - 2026-07-17

### Added

- Adds a background-agent script for the standard post-implementation review sequence (verify, code-quality, validate), replacing a manual, prose-driven review flow.
- The close-gate can now run declared project-specific checks automatically, not just confirm that required files exist.

## [3.1.0] - 2026-07-16

### Added

- Adds automatic session-save: a digest of every turn's transcript is saved locally, with a `/resume` command that briefs a new session from the latest save for the current project.

### Changed

- Adds a fourth onboarding habit covering session continuity — the automatic save versus the curated handoff file, and when to use each.

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

[Unreleased]: https://github.com/Victoriakaey/project-life-cycle/compare/v3.7.0...HEAD
[3.7.0]: https://github.com/Victoriakaey/project-life-cycle/compare/v3.0.0...v3.7.0
[3.0.0]: https://github.com/Victoriakaey/project-life-cycle/compare/v1.0.0...v3.0.0
[1.0.0]: https://github.com/Victoriakaey/project-life-cycle/compare/v0.4.0...v1.0.0
[0.4.0]: https://github.com/Victoriakaey/project-life-cycle/releases/tag/v0.4.0
