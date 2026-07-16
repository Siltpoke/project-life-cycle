# Release Process

Canonical spec for cutting a release under the `project-lifecycle` skill's discipline. The slash command `/release` (shipped via `commands/release.md`) automates everything below; this reference is the contract `/release` follows + the manual fallback when something needs hand intervention.

> If you're authoring a fresh project that uses this skill, ship `commands/release.md` from this skill's marketplace + add `CHANGELOG.md` + the two `.claude-plugin/` manifests + the two `.qoder-plugin/` manifests + the two `.codebuddy-plugin/` manifests + `.github/workflows/release.yml`. From then on, releases are: edit nothing, type `/release`.

## Inputs the process depends on

| Artifact | Path | Owner |
|---|---|---|
| Version log | `CHANGELOG.md` (Keep a Changelog 1.1.0) | Maintained per-PR per `references/changelog.md` |
| Claude plugin manifest | `.claude-plugin/plugin.json` | `version` field |
| Claude marketplace manifest | `.claude-plugin/marketplace.json` | `plugins[0].version` (must match plugin.json) |
| Qoder plugin manifest | `.qoder-plugin/plugin.json` | `version` field (must match plugin.json) |
| Qoder marketplace manifest | `.qoder-plugin/marketplace.json` | `plugins[0].version` (must match plugin.json) |
| CodeBuddy plugin manifest | `.codebuddy-plugin/plugin.json` | `version` field (must match plugin.json) |
| CodeBuddy marketplace manifest | `.codebuddy-plugin/marketplace.json` | `plugins[0].version` (must match plugin.json) |
| Antigravity native manifest | `plugin.json` (top-level) | `name` + `description` only — schema forbids a `version` field, so it is **not** version-bumped; the validator name-checks it against the Claude manifest |
| Release workflow | `.github/workflows/release.yml` | Tag-driven; extracts CHANGELOG section as body |
| Release-notes config | `.github/release.yml` | PR-label grouping for auto-generated notes |
| Repo validator | `scripts/validate.py` | Rejects mismatched manifest versions; enforces UTF-8 + frontmatter + reference link integrity |

Missing any of the above → release process doesn't apply; use the project's own flow.

## SemVer bump rules

Bump is computed from `CHANGELOG.md` `[Unreleased]` content **AND any uncompiled `changelog.d/` fragments** (the effective release set), unless the human overrides. Under the fragment convention most releases have an empty inline `[Unreleased]` body with all content sitting in `changelog.d/*.md`, so the bump inference (and the "nothing to release" check) must read the union of both — reading the inline body alone mis-bumps (e.g. falls to PATCH when a fragment carries `### Added` = MINOR).

| `[Unreleased]` contains | Bump | Example |
|---|---|---|
| Any `### Removed` content OR any bullet containing `BREAKING` / breaking-change marker | **MAJOR** | `0.2.0 → 1.0.0` |
| Any `### Added` content OR `### Changed` content (new reference / new command / new convention / restructured behavior) | **MINOR** | `0.2.0 → 0.3.0` |
| Only `### Fixed` / `### Security` / `### Deprecated` | **PATCH** | `0.2.0 → 0.2.1` |

`### Deprecated` alone is patch — deprecation is a warning, not a break. Removal of the deprecated item later is the MAJOR.

Pre-1.0 caveat: while at `0.x.y`, breaking changes can theoretically ship in MINOR. We don't — we still treat breaking as MAJOR (jumps to `1.0.0`) so users see the signal. The discipline only matters if it's consistent.

## Per-release artifact updates (atomic, in one commit)

1. **Compile the changelog fragment dir's fragments into `CHANGELOG.md` `[Unreleased]`** — BEFORE the rename in step 2, same atomic commit:
   - **Resolve the fragment dir from the manifest first**: `.claude/close-gate.json` `retention.changelog_dir` (default `changelog.d` when the manifest, or the key, is absent) — the same key `close-gate.sh`'s `phase-done` reads for its CHANGELOG-touched check. Hardcoding the literal path `changelog.d/` here would silently break for any project that overrides the key, since `phase-done` and `/release` would then be checking two different directories for the same content.
   - Read every `*.md` fragment in that dir. Group their bullets by the 6 Keep-a-Changelog categories (Added / Changed / Deprecated / Removed / Fixed / Security, in that fixed order — omit categories with no bullets), merging same-named `### <Category>` sections from different fragments into one section per category under `[Unreleased]`. Within a category, keep fragments in filename (date) order.
   - **Byte-verify** the compiled content actually landed in `CHANGELOG.md` — read the file back and confirm every fragment's bullets are present — BEFORE deleting anything. Mirrors the verify-then-delete discipline `references/retention.md`'s drain uses for its own archive writes: a failed or partial write leaves the fragments untouched and the release aborts.
   - Only once verified, `git rm` the compiled fragments from that dir so they don't linger as stale duplicates.
   - **Zero-fragments contingency:** if the dir doesn't exist or is empty, this step is a no-op — proceed straight to step 2, preserving whatever bullets are already inline under `[Unreleased]` (the documented fallback path for un-adopted projects, or a manual edit that landed directly).
2. **`CHANGELOG.md`**:
   - Rename `## [Unreleased]` → `## [X.Y.Z] — YYYY-MM-DD` (ISO 8601, UTC date), now containing both the compiled fragment bullets and any pre-existing inline bullets.
   - Insert fresh `## [Unreleased]` block above with placeholder body (e.g., `_Nothing yet — `git log vX.Y.Z..HEAD` for the in-flight set._`).
   - Update compare links at bottom:
     - `[Unreleased]: …compare/vX.Y.Z...HEAD`
     - Insert new line `[X.Y.Z]: …compare/v<PREV>...vX.Y.Z`
3. **`.claude-plugin/plugin.json`** → `version` = `X.Y.Z`.
4. **`.claude-plugin/marketplace.json`** → `plugins[0].version` = `X.Y.Z`.
5. **`.qoder-plugin/plugin.json`** → `version` = `X.Y.Z`.
6. **`.qoder-plugin/marketplace.json`** → `plugins[0].version` = `X.Y.Z`.
7. **`.codebuddy-plugin/plugin.json`** → `version` = `X.Y.Z`.
8. **`.codebuddy-plugin/marketplace.json`** → `plugins[0].version` = `X.Y.Z`.

Everything else in the same commit = wrong (mixes user-facing change with the release) — **except** the `changelog.d/` fragment compile + removal in step 1, which is intentionally part of this atomic commit: the fragments' content is what becomes the `[X.Y.Z]` section, so compiling and removing them alongside the rename is the release, not a separate change riding along with it. The release commit is purely a version-bump + CHANGELOG-compile-and-rename commit.

## Commit + tag conventions

```bash
git commit -m "chore(release): vX.Y.Z

<paste the new [X.Y.Z] CHANGELOG section verbatim — intro paragraph
+ Added/Changed/Fixed/etc. subsections>"
```

The CHANGELOG section in the commit body lets `git log` carry the release notes without round-tripping to the GitHub Release page.

```bash
git tag vX.Y.Z -m "vX.Y.Z — <one-line summary from the section's intro paragraph>"
git push origin vX.Y.Z
```

Both tag forms are supported by `release.yml`:
- `vX.Y.Z` (plain SemVer)
- `project-lifecycle--vX.Y.Z` (the `claude plugin tag` style)

Use plain SemVer unless your tool produces the prefixed form.

> **Strict main protection**: projects that adopt the strict main-branch ruleset (PR-required, empty bypass list — the same main-protection posture an unattended runtime demands) can't push the release commit to `main` directly — the release commit goes through a PR too. `/release` prepares the release commit on a short-lived branch (e.g. `release/vX.Y.Z`), the human merges it, and the tag is then created on the merge commit. The direct-push flow above only works on repos without the strict ruleset.

## What the workflow does on tag push

`.github/workflows/release.yml` triggers on push of either tag form. It:

1. Derives `X.Y.Z` from the tag.
2. Extracts the `## [X.Y.Z]` section from `CHANGELOG.md` (between that heading and the next `## ` heading).
3. Builds the GitHub Release body = extracted section + a footer link to `CHANGELOG.md`.
4. Sets `generate_release_notes: true` so GitHub also appends PR-label-grouped auto-notes (using `.github/release.yml` taxonomy) after the body.
5. Marks the release as latest (unless tag name contains `-`, which signals prerelease).

If the tag points at a commit that PREDATES the workflow file (retroactive tag), the workflow can't fire. Create the release manually:

```bash
awk '/^## \[X.Y.Z\]/{f=1; print; next} f && /^## /{exit} f' CHANGELOG.md > /tmp/notes.md
gh release create vX.Y.Z --title vX.Y.Z --notes-file /tmp/notes.md
```

## Verification checklist (before declaring release done)

- [ ] Workflow run succeeded (`gh run list --workflow=release.yml --limit 1`)
- [ ] Release exists and is marked Latest (`gh release view vX.Y.Z`)
- [ ] Release body starts with the `## [X.Y.Z] — YYYY-MM-DD` heading + the intro paragraph
- [ ] CHANGELOG `[Unreleased]` is empty / placeholder
- [ ] All plugin manifests on `main` agree on `X.Y.Z`
- [ ] Compare link `[X.Y.Z]: …compare/v<PREV>...vX.Y.Z` works (returns a non-empty diff)

## Common failure modes + recovery

| Symptom | Cause | Fix |
|---|---|---|
| `gh run list` shows no run | Tag pushed to a commit predating `release.yml` | Create release manually via `gh release create --notes-file <extracted-section>` |
| Release body is empty / says "falling back to commit log" | Tag's commit doesn't have a matching `## [X.Y.Z]` section in CHANGELOG | Edit release body: `gh release edit vX.Y.Z --notes-file <extracted-section>` |
| Validator rejects mismatched manifest versions | Hand-edited only one of plugin.json / marketplace.json | Sync them; re-commit; force-push if already pushed (or amend if not) |
| Release marked as not-latest because cut after an older retroactive tag | `gh` marks the release with the latest publish-time as Latest by default; retro tags publish later | `gh release edit vX.Y.Z --latest` |
| Tag exists but no release | Workflow failed mid-run | `gh run view <id> --log-failed`; once fixed, `gh release create vX.Y.Z --notes-file <section>` to publish manually |
| Pushed wrong version (e.g., `v0.3.0` when meant `v0.2.1`) | Bumped without thinking | DO NOT delete the tag (it's published; users may have pulled). Cut the next correct version on top (e.g., `v0.3.1` w/ `[Unreleased]` empty of new content, body = "Re-cut after v0.3.0 mistake; no functional change"). Document in CHANGELOG. |

## Retroactive tags (cleanup for historical versions)

When a tag exists for a commit that predates `release.yml`, the workflow can't auto-publish a release. Manual flow:

```bash
# 1. Extract the relevant CHANGELOG section
awk '/^## \[X.Y.Z\]/{f=1; print; next} f && /^## /{exit} f' CHANGELOG.md > /tmp/v-X.Y.Z-notes.md

# 2. Create the release directly
gh release create vX.Y.Z --title vX.Y.Z --notes-file /tmp/v-X.Y.Z-notes.md

# 3. If you cut this AFTER newer releases, restore Latest on the actual newest one
gh release edit v<NEWER> --latest
```

## Frequency + cadence guidance

- **Cut releases on milestone boundaries**, not per-PR. Many PRs → one release.
- **Don't ship a release with only chore-quiet entries** — that's a non-release. Either accumulate more or skip until there's user-visible content.
- **A typical month for an active skill**: 1–3 MINOR releases + 0–2 PATCH releases. If you're cutting more than 5/month, you're either over-versioning (consolidate) or your `[Unreleased]` discipline is bleeding (a `feature` is being labelled as a `fix`).
- **Pre-1.0 (`0.x.y`)**: ship freely; users expect churn. **Post-1.0**: every MINOR is a public commitment to compatibility within the major line.

## Cross-reference

- `references/changelog.md` — per-PR discipline (what feeds `[Unreleased]`).
- `references/self-update-flow.md` — when to bump version for the skill's OWN repo (vs. routine update-without-release).
- `references/handoff-template.md` §"PR description appendix" — PR body shape that produces good CHANGELOG entries.
- `commands/release.md` — the slash command that automates everything above.
