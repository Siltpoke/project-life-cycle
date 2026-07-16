# CHANGELOG + PR Discipline

Every project this skill touches MUST maintain a `CHANGELOG.md` at the repo root and enforce the per-PR release-notes discipline below. Same convention applies to the `project-life-cycle` repo itself — this is the skill's universal rule, not a project-specific add-on.

## Why this exists

Three audiences, three failure modes when missing:

1. **New users** read `README.md` to understand what the project does. They don't care what changed.
2. **Existing users / upgraders** want to know what changed between the version they have and the version they're about to install. `git log` is too noisy (merge commits, syncs, fixup commits, prose drift). They need a curated `CHANGELOG.md`.
3. **Stakeholders / oncall / regulators** want a single place that says "as of date X, the system did Y; as of date Y+1, it does Z". Release notes on GitHub serve this — but only if PRs are labelled and the changelog is current.

Skip the discipline → users miss breaking changes → trust erodes. Adopt it consistently → upgrades become trivial.

## Format: Keep a Changelog 1.1.0

Canonical reference: <https://keepachangelog.com/en/1.1.0/>. Distilled rules:

- **File location**: `CHANGELOG.md` at repo root.
- **Encoding**: UTF-8, markdown.
- **Dates**: ISO 8601 (`2026-05-27`), never regional formats.
- **Newest version at the top.** Walk down to find what changed between any two versions.
- **`[Unreleased]` section** at the top — accumulates changes since the last tag. When a release is cut, rename the section to `[X.Y.Z] — YYYY-MM-DD` and start a fresh `[Unreleased]` block above it.
- **Six fixed categories** (in this order, omit empty ones):

| Category | When to use |
|---|---|
| **Added** | New features, new references, new commands, new public API |
| **Changed** | Modifications to existing behavior, refactors that change user-visible output, doc restructures |
| **Deprecated** | Soon-to-be-removed features still present and working — surface BEFORE removing |
| **Removed** | Features deleted in this release |
| **Fixed** | Bug fixes (only those users would observe — internal-only fixes go in the commit message, not here) |
| **Security** | Vulnerability patches, secret rotations, hardening that closes a real attack surface |

- **Each bullet** is a one-line user-facing sentence + (where useful) a link to the relevant `references/` file or PR. Bullets must be greppable: name the file / endpoint / command / convention by its real identifier.
- **Compare links at the bottom** point at the GitHub diff range:
  ```
  [Unreleased]: https://github.com/<owner>/<repo>/compare/v0.1.0...HEAD
  [0.1.0]:      https://github.com/<owner>/<repo>/releases/tag/v0.1.0
  ```

## PR label taxonomy (drives auto release notes)

GitHub auto-generates the release-notes body from PR labels via `.github/release.yml`. Every PR MUST carry exactly one category label from the list below.

| Label | Maps to Keep-a-Changelog | When to apply |
|---|---|---|
| `breaking` | Changed + warning header | API / convention / file-layout break that requires migration |
| `feature` | Added | New feature, new endpoint, new UI surface |
| `new-reference` | Added | New `references/<file>.md` shipped in a skill |
| `new-command` | Added | New slash command shipped via `commands/` |
| `cadence` | Changed | Edits to per-task cadence (`references/cadence.md`) |
| `workflow` | Changed | Edits to per-phase workflow (SKILL.md numbered steps) |
| `convention` | Changed | New / changed mandatory convention or Red Flag |
| `bug` / `fix` | Fixed | Bug fix |
| `docs` | (often omitted from notes) | Doc-only change; can carry release-notes line if user-visible |
| `ci` / `tooling` | (own subsection) | CI workflow, validator, repo tooling |
| `dependencies` | (own subsection) | Bumps + lock-file updates |
| `chore` | (own subsection) | Repo housekeeping not worth a behavior line |
| `skip-release-notes` | excluded from notes | Explicit opt-out for internal-only churn |

PR with no category label → lands in `Other Changes` catch-all → fix before cutting the release. The validator + PR template should remind authors.

## Per-PR discipline (mandatory)

Every PR that ships a user-visible change MUST:

1. **Carry exactly one category label** from the taxonomy above.
2. **Write a `changelog.d/<date>-<branch-slug>.md` fragment** — one file per branch, not per PR/task: if the branch's fragment already exists (e.g. a second commit on the same branch), append to it rather than creating a second file — same one-fragment-per-branch rule journal and qa-log follow, per `references/retention.md` §"Fragment convention". The fragment must contain at least one category-tagged bullet (`### <Category>` heading matching the taxonomy below + the bullet), in the same commit set. Reviewers reject PRs that change skill behavior without a changelog fragment. Compilation into `CHANGELOG.md` `[Unreleased]` happens at `/release` time (`references/release-process.md`), not per-PR — see `references/retention.md` §"Fragment convention" for the naming scheme and the post-merge single-writer boundary this fragment layout depends on.
   - **Fallback (un-adopted projects):** if the repo hasn't wired up `changelog.d/`, edit `CHANGELOG.md` `[Unreleased]` directly instead — this remains a fully supported path, just not the default for projects that have adopted the fragment convention.
3. **Include a release-notes-style PR body** (per `handoff-template.md` 3-section format: §1 What was done + §2 Why this approach + §3 Requirements satisfied). The §1 prose intro becomes the line GitHub surfaces in the release notes when the PR is merged.
4. **Title in conventional-commits style** (`feat: ...`, `fix: ...`, `feat!: ...` for breaking, `docs: ...`, etc.) — this is what auto-release-notes displays as the bullet text alongside the PR number.

The 4 rules ARE the audit trail. Skipping any one breaks the chain that lets a future reader (or auditor, or upgrader) walk from "what changed" → "why" → "who decided" → "what they tested".

## Exempt PRs (no changelog line required)

- Internal-only refactors with zero user-visible delta (apply `chore-quiet` or `skip-release-notes`).
- Test-only additions that don't change behavior (still surface in PR body; label `chore`).
- Comment-only / formatting-only changes (label `chore`).

When in doubt, add the entry. Over-documentation is recoverable; under-documentation requires git-archaeology.

## Releasing (cut a version)

Prefer `/release`, which automates this entire walkthrough (and, under the fragment convention, **compiles all `changelog.d/*.md` fragments into `[Unreleased]` before the rename** — see `references/release-process.md` §"Per-release artifact updates" step 1). The manual steps below are the fallback when `/release` can't run; on a fragment-adopting project, do step 0 first.

When `[Unreleased]` has accumulated enough to warrant a tag:

0. **(fragment-adopting projects)** Compile `changelog.d/*.md` fragments into `[Unreleased]` first — group bullets under the 6 categories, byte-verify they landed, then `git rm` the fragments (same atomic commit as the rename below). Skip if the project hasn't adopted `changelog.d/`.
1. Decide the version bump per SemVer — from the effective set (inline `[Unreleased]` **plus** any not-yet-compiled `changelog.d/` fragments):
   - **MAJOR** if any `breaking` PR is in the unreleased set.
   - **MINOR** if any `feature` / `new-reference` / `new-command` is in.
   - **PATCH** if only `fix` / `docs` / `chore` are in.
2. In `CHANGELOG.md`:
   - Rename `## [Unreleased]` → `## [X.Y.Z] — YYYY-MM-DD`.
   - Add a fresh empty `## [Unreleased]` block above it.
   - Add the new compare link at the bottom: `[X.Y.Z]: https://github.com/<owner>/<repo>/compare/v(X.Y.Z-prev)...vX.Y.Z`. Update the `[Unreleased]` compare link to `vX.Y.Z...HEAD`.
3. Bump version in both `.claude-plugin/marketplace.json` and `.claude-plugin/plugin.json` (must agree).
4. Commit as `chore(release): vX.Y.Z` with body = the CHANGELOG section verbatim.
5. Tag: `git tag vX.Y.Z && git push --tags`.
6. GitHub Actions `release.yml` builds the GitHub Release; the release-notes body is auto-generated from PR labels via `.github/release.yml`. Review + publish (or `gh release edit vX.Y.Z --draft=false` if it ships draft).
7. Optionally append the CHANGELOG section to the release body for completeness (auto-notes alone may miss prose context).

## Anti-patterns

- **PR opened without a category label** → next release notes land items in "Other Changes" catch-all; reviewer asks author to label before merge.
- **PR opened without a CHANGELOG fragment (or, on un-adopted projects, an `[Unreleased]` entry)** on a user-visible change → blocked; author adds the fragment (or line) in a follow-up commit on the same PR.
- **CHANGELOG entries written in commit-message tone** ("refactor X for clarity") → rewrite in user-facing tone ("Renamed the `validator` agent's output section from `Spec compliance` to `AC coverage`"). Audience is upgraders, not git archaeologists.
- **Bullets without file / endpoint / command identifiers** ("Improved the cadence" — improved how? which step?) → name the artifact; bullet must be greppable.
- **Releases cut without renaming `[Unreleased]` first** → next contributor adds entries under the wrong section; rebase to fix or accept the drift in the following release.
- **Version bumped in only one manifest** (`marketplace.json` ≠ `plugin.json`) → CI validator catches; never bypass.
- **Deprecation skipped** — feature removed in one release without a prior "Deprecated" section in an earlier release → users discover via breakage. Always announce in `Deprecated` first, remove in a later MAJOR.
- **Calling everything `feat:`** in commit titles to game the SemVer bump → reviewers catch; `feat` is for user-visible new behavior only.

## Cross-reference

- **PR body shape** — `references/handoff-template.md` §"PR description appendix" (3-section format: What / Why / Requirements satisfied).
- **Commit message format** — Conventional Commits subset; durable artifacts (commits, PR bodies, CHANGELOG) in English.
- **Release flow inside this skill's repo** — `references/self-update-flow.md` (when to bump version vs ship a routine update).
- **ADRs vs CHANGELOG** — ADRs live forever and document *why* a hard-to-reverse choice was made. CHANGELOG documents *what* changed in each release. Different artifacts, different lifecycles; both required.
- **Journal vs CHANGELOG** — `iteration-journal.md` is per-task narrative inside the project; CHANGELOG is per-version aggregation for external users. Don't conflate.
