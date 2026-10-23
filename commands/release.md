---
description: Cut a new release end-to-end. Computes SemVer bump from CHANGELOG [Unreleased], renames the section, bumps all plugin manifests, validates, commits, tags, pushes, and verifies the GitHub Release landed. One human checkpoint (confirm bump + version).
---

# /release — Automated Release Cut

Self-contained orchestrator for cutting a release under the `project-lifecycle` skill's CHANGELOG / SemVer / PR-label discipline. Designed so the human does NOT touch CHANGELOG, manifests, or git tags by hand — `/release` does it all.

## When to use

- Repo follows the `project-lifecycle` skill's release discipline (Keep a Changelog 1.1.0 `CHANGELOG.md`, two Claude-plugin manifests at `.claude-plugin/{marketplace,plugin}.json`, `.github/workflows/release.yml` that turns a `v*.*.*` tag into a GitHub Release).
- `[Unreleased]` section has accumulated at least one user-visible change.
- You're on `main` (or the repo's default branch), tree is clean (aside from locally-gitignored paths), and remote is reachable.

## When NOT to use

- Repo has no `CHANGELOG.md` or no Claude-plugin manifests → this skill's release discipline doesn't apply; use the project's own release process.
- `[Unreleased]` is empty or contains only chore-quiet items → nothing user-visible to ship; skip.
- Mid-phase, before the phase's PR has merged → release the phase first, then cut.

## Arguments

```
/release            # auto bump (default — infer from [Unreleased] contents)
/release auto       # same as no-arg
/release patch      # force PATCH bump
/release minor      # force MINOR bump
/release major      # force MAJOR bump
```

## Chain (orchestrator executes in order; pause once for human confirm)

### Phase 0 — Preconditions

1. `git rev-parse --abbrev-ref HEAD` → must be `main` (or repo default). Abort with explanation if not.
2. `git status --porcelain` → must be empty of meaningful changes (gitignored paths excepted). Abort if dirty.
3. Confirm `CHANGELOG.md` + `.claude-plugin/marketplace.json` + `.claude-plugin/plugin.json` + `.qoder-plugin/plugin.json` + `.qoder-plugin/marketplace.json` + `.codebuddy-plugin/plugin.json` + `.codebuddy-plugin/marketplace.json` + `plugin.json` (Antigravity, top-level) + `.github/workflows/release.yml` all exist. Abort if any missing — fall back to plain `git tag` workflow.

### Phase 1 — Read current state

**Every Python call in this command goes through `bash scripts/plc-python.sh`, so `bash` is a
prerequisite.** The wrapper finds a working Python and runs the script through it, because on
Windows a bare `python3` is often an App Execution Alias rather than an interpreter — a release
that silently did nothing is worse here than one that refuses. If no interpreter works it prints
`COULD NOT RUN` naming each candidate it tried and exits 3, which is a hard abort for this command.

**The `scripts/...` paths in this command are repo-relative ON PURPOSE, and every one of them
assumes the working directory is the root of the repository being released**. They are not
anchored to `${CLAUDE_PLUGIN_ROOT}` the way `/catchup`, `/recall`, `/handoff`, `/capture`,
`/cognition-distill`, `/plc-status` and `/init-harness` anchor theirs, because those commands call
scripts that ship WITH the plugin, while this one releases the repository you are standing in: its
`scripts/validate.py` validates that repository's manifests (it resolves its own root from
`__file__`, so a plugin-anchored copy would validate the wrong tree), and its
`scripts/gen-test-evidence.sh` writes that repository's gate evidence. Anchoring them would point
at a different checkout and silently release against the wrong one. Every other path this command
touches — `.claude-plugin/plugin.json`, `CHANGELOG.md`, `changelog.d/` — carries the same
assumption already. If you are not at the repo root, `cd` there first; the calls will fail loudly
with `No such file or directory` rather than doing something partial.

4. Current version: parse `.version` from `.claude-plugin/plugin.json` (`bash scripts/plc-python.sh -c "import json,sys; print(json.load(open('.claude-plugin/plugin.json'))['version'])"`).
5. Verify `.claude-plugin/marketplace.json` plugins[0].version matches `.claude-plugin/plugin.json`. Also verify `.qoder-plugin/*` and `.codebuddy-plugin/*` (plugin.json `.version` + marketplace.json plugins[0].version) all match. Abort if any disagree — that's the bug the validator catches; fix first.
6. Build the **effective `[Unreleased]` body** — READ-ONLY, no file mutation here (the actual compile + `git rm` stays in Phase 4 step 11.5, after the human confirm, so a cancel leaves files untouched):
   - **Read the configured changelog fragment dir first**: `.claude/close-gate.json` `retention.changelog_dir` (default `changelog.d` when the manifest, or the key, is absent). This is the same manifest key `close-gate.sh`'s `phase-done` reads for its CHANGELOG-touched check — `/release` must honor whatever override a project has set there, not assume the literal path `changelog.d/`. Use this resolved directory (call it "the changelog fragment dir" below) for the rest of this step and step 11.5.
   - Extract the inline `[Unreleased]` section body:
     ```bash
     awk '/^## \[Unreleased\]/{f=1; next} f && /^## /{exit} f' CHANGELOG.md
     ```
   - If the changelog fragment dir exists and is non-empty, concatenate the contents of all its `*.md` fragments onto that inline body. This concatenation is the **effective body** used by steps 7, 8, and 10 — under the fragment convention the inline body is typically empty while all real content lives in the fragments, so reading the inline body alone would false-abort and mis-bump. Read only; do not compile or delete anything yet.
7. If the **effective body** (inline + fragments) is empty (or only whitespace + a placeholder like `_Nothing yet —_`), abort: "Nothing to release. Add a `changelog.d/` fragment (or a `CHANGELOG.md [Unreleased]` entry) first."

### Phase 2 — Compute bump

8. If user passed an explicit bump arg, use it. Otherwise infer from the **effective body** (inline `[Unreleased]` + `changelog.d/` fragments — NOT the inline body alone):
   - If the effective body contains a `### Removed` section with content OR any bullet with `BREAKING` / `breaking` → **MAJOR**.
   - Else if it contains `### Added` with content OR `### Changed` with content (the common case for new references / commands / convention changes) → **MINOR**.
   - Else (only `### Fixed` / `### Security` / `### Deprecated`) → **PATCH**.
9. Compute next version: increment the right component, reset lower components to 0.
   - `0.2.0` + minor → `0.3.0`
   - `0.2.0` + patch → `0.2.1`
   - `0.2.0` + major → `1.0.0`

### Phase 3 — Human checkpoint (single AskUserQuestion)

10. Ask the user once: "Cut release vX.Y.Z (BUMP)? Bumping from CURRENT_VERSION → NEW_VERSION based on N entries in [Unreleased]." (N = entries counted from the **effective body** — inline `[Unreleased]` + `changelog.d/` fragments — so the count reflects what will actually be compiled at step 11.5.) Options:
    - **Proceed** (default)
    - **Force different bump** (offer the other two; one further round if picked)
    - **Cancel**

If cancelled, exit gracefully without touching files.

### Phase 4 — Update files (atomic prep before commit)

11. Today's date in ISO 8601: `date -u +%Y-%m-%d`.
11.5. **Compile the changelog fragment dir's fragments into `CHANGELOG.md` `[Unreleased]`** (the dir resolved in step 6 — `retention.changelog_dir` in `.claude/close-gate.json`, default `changelog.d`), BEFORE the rename in step 12, per `references/release-process.md` §"Per-release artifact updates" step 1:
    - Read every `*.md` fragment in that dir; group bullets by the 6 Keep-a-Changelog categories (fixed order: Added, Changed, Deprecated, Removed, Fixed, Security — omit empty ones), merging same-named `### <Category>` sections across fragments into one section per category appended under `[Unreleased]`. Within a category, keep fragments in filename (date) order.
    - **Byte-verify** the compiled content landed in `CHANGELOG.md` (read the file back, confirm every fragment's bullets are present) BEFORE deleting anything.
    - Only once verified, `git rm` the compiled fragments from that dir.
    - **Zero-fragments contingency:** if the dir doesn't exist or is empty, this is a no-op — proceed to step 12 with whatever bullets are already inline under `[Unreleased]` (the documented fallback for un-adopted projects).
12. In `CHANGELOG.md`:
    - Replace `## [Unreleased]` heading with `## [X.Y.Z] — YYYY-MM-DD` (preserving the body).
    - Insert a fresh `## [Unreleased]\n\n_Nothing yet — `git log vX.Y.Z..HEAD` for the in-flight set._\n\n---\n\n` block above it.
    - Update compare links at the bottom of the file:
      - Replace `[Unreleased]: ...compare/v<PREV>...HEAD` with `[Unreleased]: ...compare/vX.Y.Z...HEAD`.
      - Insert a new line `[X.Y.Z]: ...compare/v<PREV>...vX.Y.Z` above the previous version's link.
13. **If the repo generates its manifests** (`.claude-plugin/plugin.source.json` + `scripts/gen_plugin_manifests.py`, as this repository does): bump `.version` in the source to `X.Y.Z`, run `bash scripts/plc-python.sh scripts/gen_plugin_manifests.py`, and skip to step 16 — never hand-edit a generated manifest, `scripts/validate.py` rejects one that differs from the source. Otherwise bump `.version` in `.claude-plugin/plugin.json` to `X.Y.Z`.
14. Bump `plugins[0].version` in `.claude-plugin/marketplace.json` to `X.Y.Z`.
15. Bump the sibling manifests to `X.Y.Z` too: `.version` in `.qoder-plugin/plugin.json` + `.codebuddy-plugin/plugin.json`, and `plugins[0].version` in `.qoder-plugin/marketplace.json` + `.codebuddy-plugin/marketplace.json`. (Do NOT touch the top-level `plugin.json` — the Antigravity manifest's schema forbids a `version` field, so it carries none and is never bumped.)

### Phase 5 — Validate

16. Run `bash scripts/plc-python.sh scripts/validate.py`. Abort + revert on any error — surface the validator output. Use the **explicit-HEAD** form so the `git rm`'d fragments are actually restored: `git checkout HEAD -- .claude-plugin/ .qoder-plugin/ .codebuddy-plugin/ CHANGELOG.md changelog.d/`. The bare `git checkout -- changelog.d/` FAILS for the fragments (the pathspec resolves against the index, which no longer holds them after `git rm` → "did not match any file(s)"); `git checkout HEAD -- …` resolves against the `HEAD` tree and restores them (they're still tracked in `HEAD` until this commit lands). The same command also cleanly reverts the in-place edits to `CHANGELOG.md` + the manifests.

### Phase 6 — Commit + tag + push

17. `git add CHANGELOG.md .claude-plugin/marketplace.json .claude-plugin/plugin.json .qoder-plugin/plugin.json .qoder-plugin/marketplace.json .codebuddy-plugin/plugin.json .codebuddy-plugin/marketplace.json`. The `changelog.d/` fragment removals from step 11.5 are already staged via `git rm` and ride along in this same commit — no separate `git add` needed for them. Add `.claude-plugin/plugin.source.json` too when the repo generates its manifests.
18. Commit:
    ```bash
    git commit -m "chore(release): vX.Y.Z

    <paste the new [X.Y.Z] CHANGELOG section verbatim into the body
    so the commit itself carries the release notes>"
    ```
18.5. **Regenerate the close-gate test-evidence file** — only if the repo wires the close-gate pre-push hook (`.claude/close-gate.json` exists with a `test_evidence` key): `bash scripts/gen-test-evidence.sh task`. Then `git add` the evidence file if it is tracked, and `git commit --amend --no-edit` (or leave it untracked/gitignored, whichever this repo does).
     - **Why here and nowhere else**: the release commit rewrites `.claude-plugin/*.json` and `CHANGELOG.md`. In a repo whose manifest declares those files in `product_paths` (so the pre-push gate runs its diff-triggered checks) *and* in `test_evidence_inputs` (so the evidence fingerprint the gate compares against is now stale), step 19 would otherwise be blocked.
     - **Order is load-bearing**: after the bump commit, because the fingerprint covers the bumped manifests — regenerating before step 13–18 produces evidence of the *pre-bump* tree, which is exactly the staleness this step exists to clear. And before step 19, because that is the push the gate blocks.
     - Never hand-write or copy-paste the manifest's declared `test_command` to do this: it ends in a bare `tee`, which exits 0 even when the header-writing step fails and silently replaces good evidence with broken evidence. `gen-test-evidence.sh` writes to a temp file and only moves it into place on success.
19. `git push`.
20. `git tag vX.Y.Z -m "vX.Y.Z — <one-line summary derived from the [X.Y.Z] section's intro paragraph>"`.
21. `git push origin vX.Y.Z`.

### Phase 7 — Verify GitHub Release landed

22. Watch the workflow: `gh run list --workflow=release.yml --limit 1` then `gh run watch <id>`.
23. On workflow success: `gh release view vX.Y.Z`.
24. On workflow failure: surface the failing job log; do NOT delete the tag (manual recovery needed).
25. If multiple existing releases, ensure the new one is marked Latest: `gh release edit vX.Y.Z --latest`.

### Phase 8 — Report

26. Print to the user:
    - The release URL
    - Bump applied
    - Number of `[Unreleased]` entries that shipped
    - Suggested upgrade commands for users:
      - Claude Code: `claude plugin marketplace update <marketplace-name> && claude plugin update <plugin-name>`
      - Qoder: `qodercli plugins marketplace update <marketplace-name> && qodercli plugins update <plugin-name>`

## Error recovery

- **Validate fails** → `git checkout HEAD -- .claude-plugin/ .qoder-plugin/ .codebuddy-plugin/ CHANGELOG.md changelog.d/`, surface error, stop. The explicit-`HEAD` form is required to restore the fragments `git rm`'d in step 11.5 — a bare `git checkout -- changelog.d/` fails ("did not match any file(s)") because they're gone from the index.
- **Commit fails** → unstage with `git reset`, then restore any `git rm`'d fragments with `git checkout HEAD -- changelog.d/` (`git reset` only unstages — it does NOT bring back files `git rm` already deleted from disk, so the working tree is NOT left intact for this file category without the explicit restore). Surface error.
- **Push fails (auth / no upstream)** → leave commit local; instruct user to push manually.
- **Tag push fails after commit pushed** → commit is on remote but no tag yet. Re-run only Phase 6 step 20–21 (don't re-edit files).
- **Workflow fails** → tag is on remote; release page may or may not exist. Inspect via `gh run view <id>`. Common causes: outdated `release.yml` (no `--latest` flag, missing CHANGELOG-section extraction). Fix workflow in a follow-up PR; manually create release via `gh release create vX.Y.Z --notes-file <extracted-section>` in the meantime.
- **Mid-flight cancel** (user hits Ctrl-C between Phase 4 and Phase 6) → run `git checkout HEAD -- .claude-plugin/ .qoder-plugin/ .codebuddy-plugin/ CHANGELOG.md changelog.d/` to undo the file edits (including any `changelog.d/` fragment removals from step 11.5) before retrying. The explicit-`HEAD` form is required — the bare form can't restore `git rm`'d fragments.

## Anti-patterns

- **Editing CHANGELOG / manifests by hand instead of running `/release`** → consistency drifts; next `/release` may misparse. The discipline is exactly that the human doesn't touch these.
- **Running `/release` when `[Unreleased]` is empty or only chore-quiet entries** → no user-visible delta; release notes will be empty; users see a "version bump" with no value. Skip the release.
- **Forcing `major` for a non-breaking change** because "the feature feels big" → SemVer breakage signals migration; misuse erodes trust. MINOR exists exactly for "big but additive". Reserve MAJOR for actual breaks.
- **Cutting a release mid-phase before the phase PR has merged** → the phase's changes won't be in the release; release notes are incomplete. Merge the phase first.
- **Skipping the workflow verification step (Phase 7)** → silently shipping a broken release. Always confirm the GitHub Release page exists and the body is populated.

## Related

- `skills/project-lifecycle/references/release-process.md` — full process spec including SemVer bump table, exempt-PR rules, retroactive-tag flow for cleanup.
- `skills/project-lifecycle/references/changelog.md` — CHANGELOG + per-PR discipline this command depends on.
- `skills/project-lifecycle/references/self-update-flow.md` — how this skill itself versions + ships updates to its repo.
- `/ship` — orchestrator for a single vertical-slice feature (upstream of `/release`; many `/ship` runs accumulate into `[Unreleased]`, then one `/release` ships them).
