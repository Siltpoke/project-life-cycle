---
description: Bootstrap a project to use the project-lifecycle skill — detect stack + folder layout + tooling, generate CLAUDE.md / folder-map / policy keys / project-shared commands / deterministic handler scaffolds. Idempotent (merges into existing files; never overwrites without explicit confirm). 4 human checkpoints.
---

# /init-harness — Project Bootstrap for the Project-Lifecycle Skill

Dynamic-on-the-fly harness generator (Tejas Kumar's next-step-for-harnesses idea, brought forward). Detects what the project actually is, then generates the deterministic scaffolding the rest of the skill expects: `CLAUDE.md`, `CONTEXT.md` placeholder, `folder-map`, policy keys, project-shared `.claude/commands/`, deterministic handler stubs in `.claude/handlers/`, `CHANGELOG.md` + `.github/release.yml` + `release.yml` workflow if missing.

## When to use

- **Fresh project** — empty repo or repo where the skill has never been wired up. `/init-harness` is the first command you run.
- **Existing project adopting the skill** — repo has code but no `CLAUDE.md` / `docs/RESUME.md` (or root `RESUME.md`) / `docs/iteration-journal.md` (or root — either location counts, per the detection contract in `references/archaeology.md`). `/init-harness` reads the existing code, generates the scaffolding, surfaces conflicts (e.g., existing CLAUDE.md style differs from what the skill expects). Brownfield repos additionally get the one-time archaeology offer at CHECKPOINT 1 (baseline ROADMAP / glossary / backfilled-ADR / journal-start drafts, per `references/archaeology.md`).
- **After a major refactor** — folder layout changed; `folder-map` is stale. `/init-harness --refresh` re-detects + proposes diff.

## When NOT to use

- Project already uses the skill end-to-end (`CLAUDE.md` + `RESUME.md` + journal all present and current) → no need to bootstrap; just keep working.
- You only want one piece (e.g., just generate the `.github/workflows/release.yml`) → do that directly; `/init-harness` is the full bootstrap.

## Arguments

```
/init-harness               # full bootstrap, interactive
/init-harness --refresh     # re-detect folder-map + handlers against current code; propose diff
/init-harness --dry-run     # detect + report, write nothing
/init-harness --archaeology # run/re-run the brownfield archaeology pass (see references/archaeology.md)
```

## Chain (orchestrator executes; 4 human checkpoints)

### Phase 0 — Preconditions

1. `pwd` + `git rev-parse --show-toplevel` → must be in a git repo (or offer `git init` if not).
2. Inventory existing artifacts: does `CLAUDE.md` / `CONTEXT.md` / `RESUME.md` / `docs/iteration-journal.md` / `.claude/commands/` / `.claude/handlers/` / `CHANGELOG.md` / `.github/workflows/release.yml` / `.github/release.yml` / `.claude-plugin/` exist? Record state so each generated artifact can MERGE (when target exists) vs CREATE (when absent). NEVER overwrite a non-empty existing file without an explicit `OVERWRITE` confirm.

### Phase 1 — Stack detection (read-only)

3. Dispatch a read-only `Explore` subagent (or run inline if the project is small) to detect:

| Signal | Where to look | Output |
|---|---|---|
| Language(s) | `package.json` / `pyproject.toml` / `Cargo.toml` / `go.mod` / `Gemfile` / `*.csproj` / `pubspec.yaml` / `pom.xml` | `["typescript", "python"]` etc. |
| Frameworks | dependencies in the above + obvious markers (`next.config.*`, `vite.config.*`, `manage.py`, `config/routes.rb`, `pages/`, `app/`, `cmd/`) | `["nextjs", "fastapi"]` etc. |
| Test runner | scripts in package.json + presence of `vitest.config.*` / `jest.config.*` / `pytest.ini` / `tests/` dir | `vitest` / `pytest` / `cargo test` |
| Lint + format | `.eslintrc.*` / `ruff.toml` / `pyproject.toml [tool.ruff]` / `.prettierrc` / `rustfmt.toml` | `[ruff, prettier]` |
| Package manager | `pnpm-lock.yaml` / `package-lock.json` / `bun.lockb` / `poetry.lock` / `uv.lock` / `requirements.txt` / `Cargo.lock` | `pnpm` / `bun` / `poetry` / etc. |
| DB / ORM | `prisma/` / `migrations/` / `alembic/` / `db/migrate/` / `schema.sql` / `models.py` w/ Django patterns | `[prisma, postgres]` etc. |
| Queue / background | imports of `bullmq` / `celery` / `sidekiq` / `delayed_job` / `rq` | `bullmq` etc. |
| Auth pattern | `auth/` dir / `next-auth` / `passport` / `django.contrib.auth` / `clerk` / `supabase` / `lucia` | `next-auth` etc. |
| Multi-tenant markers | columns named `tenant_id` / `organization_id` / `workspace_id` in schemas + middleware that scopes by them | true / false |
| Timezone-sensitive | uses of `datetime.now()` / `Date.now()` / `new Date()` w/o explicit UTC | flag w/ file:line |
| Layer split | `frontend/` + `backend/` dirs? `apps/web/` + `apps/api/` monorepo? `src/components/` + `src/services/` mixed? | `cross-layer` / `single-layer` / `monorepo-workspace` |
| CI present | `.github/workflows/*.yml` | list of workflow names |
| Containerized | `Dockerfile` / `compose.yaml` / `docker-compose.yml` | true / false |
| Existing CLAUDE.md | repo root + `~/.claude/CLAUDE.md` | content if any |

Subagent returns a structured detection report. Do NOT proceed to generation until detection is complete.

### Phase 1b — Archaeology pass (brownfield only, read-only, opt-in)

Runs only when Phase 0 inventory found NO plc artifacts AND Phase 1 confirmed substantial existing code (detection contract in `references/archaeology.md`), AND the user accepted the offer at CHECKPOINT 1 — or `--archaeology` was passed explicitly. Fan out the three read-only subagents (position/roadmap · glossary · ADR archaeology) with read budgets per `references/archaeology.md`; controller assembles the journal adoption preamble, the `docs/RESUME.md` initial state (root `RESUME.md` if the project already uses that location), and the `docs/adoption-snapshot.md` review index. All outputs are AI-inferred drafts carrying provenance headers; they join Phase 2's generate/merge set (checkpoints 2-4 unchanged).

### ⏸ HUMAN CHECKPOINT 1 — Confirm detected stack

4. Show the detection report. Ask user:
   - "Detected: <stack summary>. Anything wrong / missing?"
   - If user corrects (e.g., "we also use Redis for caching, you missed it"), incorporate into the model BEFORE generating.
   - On brownfield repos (per the Phase 1b conditions) the checkpoint additionally asks the one-time archaeology offer — gated by the `archaeology` policy key (`done YYYY-MM-DD | skipped`; unset = ask; any value = never re-ask; `--archaeology` stays available after `skipped`).

### Phase 2 — Generate / merge artifacts

Generate each in order. For each, check whether it already exists; if yes, propose a MERGE diff for user approval; if no, CREATE.

#### 5. `CLAUDE.md` at repo root

Template (filled from detection):

```markdown
# Project: <repo name>

## What this is

<1-2 sentence project description — ask user if not obvious from README>

## Stack

- Language(s): <detected>
- Framework(s): <detected>
- Package manager: <detected>
- DB / ORM: <detected>
- Queue / background: <detected>
- Auth: <detected>
- Test runner: <detected>

## Commands (one-liners)

```bash
<install>      # e.g., pnpm install
<dev>          # e.g., pnpm dev
<test>         # e.g., pnpm test
<lint>         # e.g., pnpm lint
<typecheck>    # e.g., pnpm typecheck
<build>        # e.g., pnpm build
<migrate-dev>  # e.g., pnpm prisma migrate dev
<phase-checks> # if Makefile target exists; else placeholder
```

## Architecture rules

- Business logic lives in services / use-cases. API routes stay thin.
- <other rules inferred from existing patterns OR ask user>

## Don't do

- No hardcoded secrets — env vars + secret manager only.
- No `--no-verify` on commits. Fix the hook complaint.
- No raw error strings to clients (leak internal info).
- <project-specific don'ts inferred OR asked>

## Folder map (used by /ship BE/FE builder split)

```yaml
folder-map:
  backend: [<inferred backend paths>]
  frontend: [<inferred frontend paths>]
  shared: [<types / lib dirs both sides import>]
  forbidden-cross:
    - <frontend folder> may NOT import from <backend folder>
    - <backend folder> may NOT import from <frontend folder>
```

If single-layer project: `folder-map: single-layer` (skip BE/FE split in /ship).

## Skill policy keys

```yaml
domain-docs: ./CONTEXT.md            # or ./CONTEXT-MAP.md
html-policy: ask                     # ask | always-md | always-html
smoke-mode: guided                   # ask | self | guided
comprehension: off                   # off | lite | full — anti-cognitive-offloading co-discovery round per phase
close-gate: per-task                 # per-task | pr-boundary — where the human-blocking close approval sits
archetype: auto                      # auto | builder | prototyper | sweeper | grower | maintainer | off
retention: { distill: on }           # doc-retention; hot-caps/archive-dir default when omitted; mirrored into the close-gate manifest — see references/retention.md
# archaeology: (leave UNSET)          # written only when the offer is answered: the pass sets `done YYYY-MM-DD`; declining sets `skipped`. Pre-setting a value suppresses the one-time offer.
```

## Pointers to deeper docs

- `docs/architecture.md` — <if exists>
- `docs/billing.md` — <if exists>
- `CONTEXT.md` — domain glossary (DDD-style anchor)
- `docs/RESUME.md` — current milestone state
- `docs/ROADMAP.md` — whole-plan map (goal + milestone table + status)
```

If `CLAUDE.md` exists, propose merge: new sections (stack, commands, folder-map, policy keys) appended; existing sections preserved.

#### 6. `CONTEXT.md` placeholder

If absent, create with:

```markdown
# CONTEXT

Ubiquitous-language glossary for <project>. Add terms as they sharpen during brainstorms.

Format per term: term name + 1-sentence definition + (optional) example.

## Terms

(none yet — populate during first brainstorm)
```

#### 7. `docs/RESUME.md` + `docs/iteration-journal.md` placeholders

Create empty scaffolds with TOC stubs (per `references/document-indexing.md`) so the first phase has somewhere to write. **When the project opts into the fragment convention** (per `references/retention.md` §"Fragment convention"), also scaffold the fragment directories with a `.gitkeep` so they exist under source control from day one: `docs/qa-log.d/.gitkeep` and `changelog.d/.gitkeep`. Empty scaffolds only — the first fragment file is written by the first brainstorm / PR / release, not by bootstrap.

#### 7b. `docs/ROADMAP.md` whole-plan-map stub

Seed `docs/ROADMAP.md` (per `references/roadmap.md`) with the one-sentence goal (ask user if not obvious from README), an empty milestone table with the status legend, and the standard "how a milestone runs" loop block. The milestone rows are filled in during the first milestone's brainstorm once the breakdown is known — at bootstrap it's a stub so the whole-plan map exists from day one. An optional `docs/ROADMAP.html` companion follows the normal `html-policy` opt-in.

#### 8. `.claude/commands/` project-shared slash commands (skeleton)

Create the directory + 2-3 starter commands tailored to the stack:

| File | Purpose |
|---|---|
| `test-phase.md` | Wraps the project's test command with PHASE arg routing |
| `start-stack.md` | Wraps install + dev-server startup for the detected stack |
| `db-snapshot.md` | (if DB detected) dumps schema + sample rows for AI Q&A |

Each gets YAML frontmatter w/ description per `references/onboarding.md` schema. Check into source control.

#### 9. `.claude/handlers/` deterministic handler scaffolds

Per `references/deterministic-handlers.md`. Create the dir + scaffold for handlers that match detected risks:

| Handler | Generated when |
|---|---|
| `pre-flight-lint.<ts|py|go>` | Always (every stack benefits) |
| `secret-leak-guard.<lang>` | Always |
| `migration-safety.<lang>` | DB detected |
| `tenant-isolation.<lang>` | Multi-tenant markers detected |
| `auth-handler.<lang>` | Auth pattern detected |
| `test-failure-attribution.<lang>` | Test runner detected |

Each scaffold is a `// TODO` skeleton with the trigger + action + inject signature filled in for the detected stack. User fills in project-specific logic later.

#### 9b. `.claude/hooks/inject-resume.sh` + `SessionStart:resume` (when `docs/RESUME.md` is used)

Copy the skill's `hooks/inject-resume.sh.template` → `.claude/hooks/inject-resume.sh` (`chmod +x`) and additively wire the `SessionStart:resume` block into `.claude/settings.json` (never clobber existing SessionStart hooks). On resume it injects the current branch + head of `RESUME.md` as `additionalContext` so the session re-grounds in the live phase deterministically. Project-level, NOT skill frontmatter (skill inactive at session start). Spec: `references/init-harness.md` §"RESUME-injection hook" + `references/harness-primitives.md` §2.

#### 10. `CHANGELOG.md`

If absent, create with Keep a Changelog 1.1.0 format + empty `[Unreleased]` block (per `references/changelog.md` template).

#### 11. `.claude-plugin/{marketplace,plugin}.json`

Only if this project is itself a Claude-plugin (likely not for most app projects). Skip otherwise. If creating, use 0.0.1 + repo name + 1-line description (ask user).

#### 12. `.github/release.yml` + `.github/workflows/release.yml`

Only if this project is a Claude-plugin OR user explicitly opts in. Use the templates from this skill's own repo (label-based release notes + CHANGELOG-section-extracting release workflow).

#### 13. `.github/workflows/validate.yml`

If `.claude-plugin/` was created, ship a validator workflow too.

### ⏸ HUMAN CHECKPOINT 2 — Approve folder-map

14. Surface the proposed `folder-map` (Phase 2 step 5 sub-section). Ask user:
    - "Does this layer split match your mental model? Any folder I miscategorized?"
    - If user corrects, edit the map BEFORE writing CLAUDE.md.

### ⏸ HUMAN CHECKPOINT 3 — Approve policy keys + handler set

15. Surface:
    - `html-policy` / `smoke-mode` / `retention` defaults (with brief explanation of each option)
    - List of handler scaffolds to be generated
    - Ask: "Approve? Toggle any?"

### Phase 3 — Write everything

16. Write all approved files. For files marked as MERGE, write the merge diff (show user once more before each merge write).
17. Run `git status` to surface what changed.
18. If `scripts/validate.py` exists in the repo (this is the skill's own repo or another project that uses it), run it. Abort + revert (`git checkout -- .`) on validator failure.

### ⏸ HUMAN CHECKPOINT 4 — Approve commit

19. Show the proposed commit:
    ```
    chore(harness): bootstrap project-lifecycle skill — initial scaffolding

    Generated by /init-harness:
    - CLAUDE.md (stack + commands + folder-map + policy keys + don't-do)
    - CONTEXT.md placeholder
    - docs/RESUME.md + docs/iteration-journal.md placeholders
- docs/ROADMAP.md whole-plan-map stub
    - docs/qa-log.d/.gitkeep + changelog.d/.gitkeep (if fragment convention adopted)
    - .claude/commands/<list>
    - .claude/handlers/<list>
    - CHANGELOG.md (if was missing)
    - .github/workflows/release.yml + .github/release.yml (if Claude-plugin)
    ```
20. On approval: `git add` the new files + `git commit`. Do NOT push automatically — let the user push when ready (some teams have pre-push hooks; respect them).

### Phase 4 — Report

21. Show the user:
    - List of files created / merged
    - Next-step suggestions:
      - "Run `/ship <first feature>` to try the per-task cadence on a real change."
      - "Edit `.claude/handlers/<file>` to fill in the TODO scaffolds with project-specific logic."
      - "Add real terms to CONTEXT.md as you go (lazy creation; first term during first brainstorm)."
    - Link to `references/onboarding.md` so the user (or any future contributor) knows Day 1 protocol.

## --refresh mode

When `/init-harness --refresh` is invoked on an already-bootstrapped project:

1. Re-run Phase 1 detection.
2. Diff detected state against current `CLAUDE.md` `folder-map` + handler set.
3. Surface drift as: "Folder X is in your folder-map but no longer exists on disk; folder Y exists but isn't in folder-map; handler Z's trigger no longer matches any code in the repo."
4. Ask user which drift to fix.
5. Apply fixes via the same merge flow as Phase 2.
6. Skip CHANGELOG / release / handler-scaffold creation if those already exist.
7. Verify the context-floor hook is armed (`context-floor.sh` referenced under `PreToolUse` in `~/.claude/settings.json` or project `.claude/settings*.json`); if not, offer to merge the wiring per `references/harness-primitives.md` §9 — append to existing `PreToolUse` arrays, never clobber. (An un-armed floor lets sessions run far past it unnoticed.)

## --dry-run mode

Detect + report only. Write nothing. Useful for "what would this do to my repo?" before committing to the bootstrap.

## Error recovery

- **Detection subagent fails to identify stack** → fall back to asking user directly. Don't guess wildly.
- **User declines proposed folder-map** → loop back to Phase 1, re-elicit, regenerate.
- **Merge would overwrite custom CLAUDE.md content** → STOP. Show the conflict in 3-way diff form. Let user pick line-by-line.
- **Write fails mid-Phase 3** → `git checkout -- .` to revert; surface error; do not leave repo in partial state.
- **User cancels at any checkpoint** → write nothing, report what was about to be created, exit cleanly.

## Anti-patterns

- **Running `/init-harness` on a repo already bootstrapped to overwrite** → use `--refresh` instead; refresh diffs and merges, full bootstrap overwrites.
- **Skipping the 4 human checkpoints because "the detection looked right"** → the user's mental model of the layer split is often different from what file paths suggest; always confirm.
- **Generating handler stubs and forgetting to fill them in** → scaffolded `.claude/handlers/*.<ext>` files are TODOs, not working handlers. Either fill them in (with project-specific logic) or remove the scaffold. Empty handlers fire every iteration with no action = budget burn.
- **Detecting "single-layer" when project is actually monorepo** → re-check workspace markers (pnpm-workspace.yaml, yarn workspaces, lerna.json, turbo.json, nx.json). If detected, surface as `folder-map: monorepo-workspace` and ask user how `/ship` should route BE/FE per package.
- **Forcing the skill on a project that doesn't fit** (e.g., a 100-line Python script with no phases / no team / no users) → the skill earns its overhead at multi-task projects; for trivial repos, skip the bootstrap and just work.

## Related

- `~/.claude/skills/project-lifecycle/references/init-harness.md` — full spec including detection signal table, merge strategy, handler scaffold templates per language.
- `~/.claude/skills/project-lifecycle/references/onboarding.md` — Day 1 protocol for new contributors (post-bootstrap).
- `~/.claude/skills/project-lifecycle/references/builder-split.md` — `folder-map` schema this command generates.
- `~/.claude/skills/project-lifecycle/references/deterministic-handlers.md` — handler pattern + 6 canonical examples this command scaffolds from.
- `~/.claude/skills/project-lifecycle/references/changelog.md` — CHANGELOG format this command generates an empty seed of.
- `~/.claude/skills/project-lifecycle/references/output-format.md` — policy keys this command pre-fills.
- `/ship` — first command to run after `/init-harness` completes.
- `/release` — release-cut command (only relevant when project is a Claude-plugin OR user opts in to the release workflow).
