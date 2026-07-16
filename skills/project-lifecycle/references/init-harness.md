# /init-harness — Project Bootstrap Spec

Canonical spec consumed by the `/init-harness` slash command (`commands/init-harness.md`). This reference is the contract `/init-harness` follows; the slash command is the user-facing surface.

Realizes Tejas Kumar's "year of dynamic harnesses" vision in this skill's context: instead of every project author hand-writing CLAUDE.md + folder-map + handlers, `/init-harness` inspects the project, generates the matching scaffolding, and gets the project to "ready for `/ship`" in one command.

## What "bootstrap" means

A project is bootstrapped when these artifacts exist + are wired together:

| Artifact | Required? | Purpose |
|---|---|---|
| `CLAUDE.md` (repo root) | ✅ | Universal project rules + folder-map + policy keys; auto-loaded into every Claude Code session |
| `CONTEXT.md` (or `CONTEXT-MAP.md` + per-context `CONTEXT.md`) | ✅ (placeholder OK) | Ubiquitous-language domain glossary; lazy-populated during brainstorms |
| `docs/RESUME.md` | ✅ (placeholder OK) | Current milestone state; updated at every phase boundary |
| `docs/iteration-journal.md` | ✅ (placeholder OK) | Per-task journal (or per-phase fragments under `docs/journal.d/` — see `references/retention.md` §"Fragment convention"); append-only with TOC |
| `docs/qa-log.d/` | ✅ (scaffold OK, only when the fragment convention is adopted) | Per-branch brainstorm Q&A fragments (`<date>-<branch-slug>.md`) that compile into the hot monolith `docs/brainstorming-qa-log.md` at milestone close — see `references/retention.md` §"Fragment convention" (qa-log) |
| `changelog.d/` | ✅ (scaffold OK, only when the fragment convention is adopted) | Per-branch CHANGELOG fragments (`<date>-<branch-slug>.md`) that compile into `CHANGELOG.md` `[Unreleased]` at `/release` time — see `references/retention.md` §"Fragment convention" + `references/changelog.md` §"Per-PR discipline" |
| `.claude/commands/` | ✅ (skeleton OK) | Team-shared project-scoped slash commands |
| `.claude/handlers/` | ✅ (scaffold OK) | Deterministic pre-step handlers (auth, lint, secret guard, migration safety, tenant isolation) |
| `.claude/hooks/inject-resume.sh` + `.claude/settings.json` `SessionStart:resume` block | ✅ (when `docs/RESUME.md` is used) | Auto-injects the current phase branch + head of `RESUME.md` on session resume, so the model re-grounds in the phase without being told to read RESUME. **Project-level, NOT skill frontmatter** — at session start the skill is not yet active, so a frontmatter hook would never fire. Installed from the template shipped at the skill's `hooks/inject-resume.sh.template`. See `references/harness-primitives.md` §2 |
| `scripts/close-gate.sh` + `scripts/test-close-gate.sh` + `.claude/close-gate.json` + `make task-done`/`phase-done`/`test-gate` + **active** pre-push hook (`.githooks/pre-push` + `git config core.hooksPath .githooks`) | ✅ (scaffold + **hook ACTIVATED, not a stub**) | Deterministic "done" gate — exits non-zero on missing wrap-up artifacts (journal / journal FACT-entry fields / tests-evidence / CHANGELOG / smoke / ROADMAP). `test_command` + `exempt_*` flags filled from detected stack; optional `retention` block (hot caps / count caps / archive dir / coverage floor / journal dir / `qa_log_dir` / `changelog_dir`) mirrored from the CLAUDE.md `retention:` key per `references/retention.md` §"Policy keys". **The pre-push hook is the un-bypassable layer and MUST be activated** (`core.hooksPath` set) — scaffolding the scripts without activating the hook leaves only the weakest model-discipline layer, which is the exact gap that lets wrap-up (esp. tests) get skipped. `test-close-gate.sh` is the gate's own self-test (throwaway-worktree, asserts every check flips) — run `make test-gate PHASE=X.Y` after wiring. See `references/close-gate.md` |
| `scripts/retention-drain.sh` | ✅ (scaffold OK, only when a `retention:` key or default drain is in use) | Deterministic no-LLM archival drain materialized from `references/retention.md`'s embedded spec (same ship-pattern as `close-gate.sh`) — the milestone-done "Archival drain run" step invokes it per doc. No hook wiring (it runs at milestone close, not on push). See `references/retention.md` §"Embedded portable script". |
| `CHANGELOG.md` | ✅ (empty seed OK) | Keep a Changelog 1.1.0 format |
| `.claude-plugin/{marketplace,plugin}.json` | Only if project is itself a Claude-plugin | Plugin manifest pair |
| `.github/release.yml` | Only if Claude-plugin OR user opts in | PR-label release-notes config |
| `.github/workflows/release.yml` | Only if Claude-plugin OR user opts in | Tag-driven GitHub Release builder |

After `/init-harness` completes, the project should pass: "Day 1 anchor checklist" (per `references/onboarding.md` Step 1) — i.e., any new contributor can read those files and have a usable mental model.

## Detection signals (Phase 1 of /init-harness)

The detection subagent reads (NOT edits) the project tree and produces a structured report. Detection signals + how to read them:

### Language(s)

| File | Implies |
|---|---|
| `package.json` | JS/TS — check `engines.node`, deps for type (TypeScript / JavaScript) |
| `pyproject.toml` / `setup.py` / `requirements.txt` | Python |
| `Cargo.toml` | Rust |
| `go.mod` | Go |
| `Gemfile` | Ruby |
| `*.csproj` / `*.sln` | C# / .NET |
| `pubspec.yaml` | Dart / Flutter |
| `pom.xml` / `build.gradle*` | Java / Kotlin |
| `composer.json` | PHP |

Multi-language projects: list all, primary first (by LOC or by entry-point convention).

### Frameworks

| Marker | Framework |
|---|---|
| `next.config.*` + `pages/` or `app/` | Next.js |
| `nuxt.config.*` | Nuxt |
| `vite.config.*` + `src/main.tsx` | Vite + React |
| `svelte.config.*` | SvelteKit |
| `astro.config.*` | Astro |
| `manage.py` + `settings.py` | Django |
| `app.py` or `main.py` with `from fastapi` | FastAPI |
| `app.py` with `Flask(__name__)` | Flask |
| `config/routes.rb` | Rails |
| `package.json` deps including `express` | Express |
| `package.json` deps including `hono` | Hono |
| `cargo` w/ `actix-web` / `axum` / `rocket` | Rust web framework |
| `cmd/*/main.go` w/ `gin` / `echo` / `fiber` | Go web framework |
| `Application.kt` w/ Spring annotations | Spring Boot |

### Test runner

| Marker | Runner |
|---|---|
| `vitest.config.*` OR `vitest` in deps | vitest |
| `jest.config.*` OR `jest` in deps | jest |
| `pytest.ini` / `pyproject.toml [tool.pytest]` / `conftest.py` | pytest |
| `Cargo.toml` (built-in) | cargo test |
| Go (built-in) | go test |
| `karma.conf.*` | karma (legacy; flag) |
| `playwright.config.*` | playwright (E2E) |
| `cypress.config.*` | cypress (E2E) |

### DB / ORM

| Marker | Stack |
|---|---|
| `prisma/schema.prisma` | Prisma + (Postgres / MySQL / SQLite per `provider`) |
| `migrations/` + `alembic.ini` | Alembic + SQLAlchemy |
| `db/migrate/` | Rails ActiveRecord |
| `models.py` w/ `from django.db import models` | Django ORM |
| `drizzle.config.*` | Drizzle ORM |
| `mongoose` in deps | Mongoose / MongoDB |
| `supabase` in deps OR `supabase/` dir | Supabase |

### Queue / background

| Marker | Stack |
|---|---|
| `bullmq` in deps | BullMQ + Redis |
| `celery` in pyproject | Celery |
| `sidekiq` in Gemfile | Sidekiq |
| `delayed_job` in Gemfile | DelayedJob |
| `rq` in pyproject | Redis Queue |
| `temporalio` | Temporal |

### Auth pattern

| Marker | Stack |
|---|---|
| `next-auth` / `@auth/*` | NextAuth |
| `clerk` | Clerk |
| `lucia-auth` | Lucia |
| `supabase` + `auth.users` references | Supabase Auth |
| `django.contrib.auth` | Django Auth |
| `devise` in Gemfile | Devise |
| Custom JWT middleware | Flag for user confirmation |

### Multi-tenant markers

Grep schemas + middleware for: `tenant_id`, `organization_id`, `workspace_id`, `account_id` columns OR scoping middleware (`scope_to_tenant`, `tenant_required`, `with_organization`).

If present in 2+ models → likely multi-tenant. Flag in CLAUDE.md "Don't do" list: queries against tenant-scoped tables MUST include the scope.

### Timezone-sensitive

Grep for: `datetime.now()` (Python), `Date.now()` (JS), `new Date()`, `Time.current` (Rails) without explicit UTC suffix / arg.

If 3+ matches → flag tz handling as project concern; add to "Don't do" list.

### Layer split detection

| Pattern | Result |
|---|---|
| Top-level `frontend/` + `backend/` dirs | `cross-layer` w/ those as roots |
| `apps/web/` + `apps/api/` (monorepo) | `monorepo-workspace`; folder-map per-app |
| `src/components/` + `src/api/` (or `src/server/`) | `cross-layer` w/ those as roots |
| Only frontend markers (Vite/Next/Astro no server routes) | `single-layer:frontend` |
| Only backend markers (FastAPI/Express w/o UI) | `single-layer:backend` |
| CLI tool / library | `single-layer` |

### CI present

`ls .github/workflows/*.yml` → list. Flag pre-existing workflows so generated `release.yml` doesn't conflict.

## Phase 1b — Archaeology pass (between detection and generation)

On brownfield repos (no plc artifacts + substantial existing code), an opt-in read-only archaeology pass runs between Phase 1 detection and Phase 2 generation — detection contract, entry surfaces, agent fan-out, artifact set, and provenance rules all in `references/archaeology.md`. Its drafts join Phase 2's normal generate/merge set.

## Merge strategy (when artifact already exists)

`/init-harness` is **idempotent** — running it twice produces the same end-state. Existing files are MERGED, not overwritten. Rules:

### CLAUDE.md (most common merge target)

If exists:
1. Parse existing sections by H2 heading.
2. For each generator-produced section (Stack / Commands / Folder map / Skill policy keys — incl. `retention`), check whether a same-named section exists.
3. If yes → propose diff for that section only. User picks: keep existing / replace with generated / merge line-by-line.
4. If no → append the section to the end.
5. Never delete sections the user wrote.

### CONTEXT.md

If exists with content → leave alone; print pointer in report ("CONTEXT.md already has N terms; not touched").
If exists empty → leave alone (no need to seed twice).
If absent → create placeholder.

### CHANGELOG.md

If exists → check format. If Keep a Changelog format → leave alone. If different format → propose conversion (preserve content; restructure to Keep a Changelog sections).
If absent → create with `[Unreleased]` + introductory header + the "How to read / How to contribute" sections from this skill's own CHANGELOG.

### `.claude/commands/<name>.md`

If file exists → leave alone (user's version wins).
If file absent → create generator scaffold.
Generator scaffolds carry a comment marker: `<!-- generated by /init-harness; edit freely -->` so user knows the file is meant to be customized.

### `.claude/handlers/*`

Same as commands — exists → leave; absent → create scaffold with TODO markers. User fills in project-specific logic.

### `.github/workflows/release.yml`

Only generate if project is a Claude-plugin (detected via `.claude-plugin/` dir presence) OR user explicitly opts in via Phase 1 / Checkpoint 1.
If exists with same trigger pattern (`v*.*.*`) → leave alone.
If exists with different trigger → flag conflict, ask user.

### `.claude/settings.json` (SessionStart:resume hook)

**Additive merge — never clobber.** Read the existing `hooks.SessionStart` array (if any). Append the `resume`-matcher block; do not remove or reorder existing SessionStart hooks (the user / other plugins may have their own). If a `resume`-matcher block already points at `inject-resume.sh` → leave alone. Block to add:

```json
{ "hooks": { "SessionStart": [
  { "matcher": "resume",
    "hooks": [{ "type": "command", "command": ".claude/hooks/inject-resume.sh" }] } ] } }
```

## Handler scaffolds (generated based on detected stack)

Each scaffold is a per-language file under `.claude/handlers/` with the trigger + action + inject signature filled in, but the project-specific logic left as `TODO`. User completes the logic; harness wires the file into the agent loop.

### Pre-flight lint handler

Always generated. Per language:

- **TypeScript / JavaScript** → runs the detected formatter+linter on changed files; injects pass/fail.
- **Python** → runs `ruff` / `black` / `mypy`; injects pass/fail.
- **Go** → runs `gofmt` + `go vet`; injects pass/fail.
- **Rust** → runs `cargo fmt --check` + `cargo clippy`; injects pass/fail.

### Secret-leak guard handler

Always generated. Language-agnostic regex set (`API_KEY=`, `Bearer ey…`, `-----BEGIN PRIVATE KEY-----`, `password\s*=\s*"`). Triggered on file write. Reverts the write + injects BLOCKED message.

### Migration-safety handler

Generated when DB detected. Per stack:

- **Prisma** → `prisma migrate dev --dry-run` against a throwaway DB clone.
- **Alembic** → `alembic upgrade head` + `alembic downgrade -1` against a throwaway DB.
- **Django** → `python manage.py migrate --plan` + `python manage.py migrate --fake-rollback`.
- **Rails** → `rake db:migrate` + `rake db:rollback STEP=1`.

### Tenant-isolation handler

Generated when multi-tenant markers detected. Triggers on writes to files matching API / service / handler paths. Greps the diff for missing tenant scope in queries against tenant-scoped tables (list of tables comes from detection). Injects BLOCKED message with the missing-scope file:line.

### Auth handler

Generated when auth pattern detected. Trigger: current request returns 401/403 OR (for browser-use agents) URL matches detected login pages. Action: inject credentials from env var (`<APP>_TEST_USER` / `<APP>_TEST_PASS`); re-issue request OR submit login form. Injects "Logged in as X" message.

### Test-failure attribution handler

Generated when test runner detected. Trigger: builder ran test suite and got failures. Action: parse failure list; `git blame` each failing line; classify as `regression-introduced-by-this-diff` vs `pre-existing`. Injects classified summary so builder doesn't claim "tests were broken before me" without checking.

## RESUME-injection hook (generated when `docs/RESUME.md` is used)

Copy the skill's `hooks/inject-resume.sh.template` to the project as
`.claude/hooks/inject-resume.sh` (drop the `.template` suffix, `chmod +x`), and wire
the `SessionStart:resume` block into `.claude/settings.json` (see merge strategy
above). The script reads the current branch + first ~1.5 KB of `RESUME.md` and
emits it as `hookSpecificOutput.additionalContext`, so a resumed session
re-grounds in the live phase deterministically instead of relying on the model to
remember to open RESUME. Silent (exit 0) when `RESUME.md` is absent. This is the
deterministic realization of the skill's "`/clear` between phases + RESUME is the
contract" discipline — see `references/harness-primitives.md` §2.

Skip generation only when the project does not use `docs/RESUME.md` (rare —
single-session throwaway repos).

## Generated `.claude/commands/` skeleton

Three starter commands tailored to the stack:

### `test-phase.md`

```markdown
---
description: Run this project's test suite (optionally scoped to a phase via PHASE env var). Emits results in the format references/ci-cd-gates.md §"Posting test evidence" expects.
---

# /test-phase

Runs `<detected-test-cmd>` 3× consecutively per the local test-evidence protocol in `references/ci-cd-gates.md`. Captures output to a tmp file. On final completion, formats the result for posting as a PR comment.

Usage:
- `/test-phase` — full suite
- `/test-phase 2.3` — scoped to phase 2.3 (via `<test-cmd> -k 2.3` or equivalent)

<command body executes the right invocation for the detected runner>
```

### `start-stack.md`

```markdown
---
description: Spin up the project's dev stack (install + DB + queue + dev server) in the right order.
---

# /start-stack

<command body: detected install + db-up + dev server commands>
```

### `db-snapshot.md` (only if DB detected)

```markdown
---
description: Dump current DB schema + sample rows so AI can answer schema Qs without fresh inspection.
---

# /db-snapshot

<command body: detected pg_dump / mysql / sqlite3 invocation; writes to tmp dir; reports row counts per table>
```

## Idempotency guarantees

After `/init-harness` runs once + completes successfully, re-running it (without `--refresh`) should:
- Detect that all artifacts exist + are current.
- Report "Project already bootstrapped — no changes needed."
- Exit without writing.

With `--refresh`:
- Re-detect stack + folder layout.
- Diff against existing CLAUDE.md `folder-map`, handler set.
- Surface drift; propose merges.
- Write only what's approved.
- Archaeology artifacts (ROADMAP / CONTEXT.md glossary / ADRs / adoption-snapshot) follow the same merge-vs-create rules; a re-run never overwrites human-edited content without explicit `OVERWRITE` confirm — full rules in `references/archaeology.md`.
- **Repair the close-gate wiring (idempotent retrofit).** This is the path that fixes already-bootstrapped projects that predate the active-hook default: if `.githooks/pre-push` is missing, write it (script in `references/close-gate.md`); if `git config core.hooksPath` ≠ `.githooks`, set it. Then report `core.hooksPath` value + suggest `make test-gate PHASE=X.Y`. A project with the gate scripts but no active hook is the #1 reason wrap-up gets skipped — `--refresh` closes that gap without disturbing anything else.
- **Verify + repair the context-floor arming (idempotent retrofit).** Check whether `context-floor.sh` is referenced in `~/.claude/settings.json` (or the project's `.claude/settings*.json`) under `PreToolUse`. Not wired → surface it ("context-floor hook not armed — an un-armed floor lets sessions run far past it unnoticed") and offer to MERGE the `PreToolUse: Edit|Write` entry into `~/.claude/settings.json` per `references/harness-primitives.md` §9 (append to existing `PreToolUse` arrays, never clobber; machine-local because frontmatter hooks would miss non-workflow sessions). User declines → respect it; the `phase-done` gate's warn-only row will keep surfacing the gap.

## Anti-patterns (mirror in commands/init-harness.md)

See `commands/init-harness.md` §Anti-patterns. Two worth restating here:

- **Generating handler scaffolds + never filling in the TODOs** — empty handlers fire every iteration with no action = budget burn. Either complete the scaffold or remove the file.
- **Hand-editing CLAUDE.md folder-map after `/init-harness` without re-running `--refresh`** — drift accumulates silently; next `/ship` may dispatch builders against wrong folder scope. Use `--refresh` to keep the map honest.

## Cross-reference

- `commands/init-harness.md` — user-facing slash command surface.
- `references/onboarding.md` — Day 1 protocol assumes bootstrap is complete.
- `references/builder-split.md` — `folder-map` schema this command generates.
- `references/deterministic-handlers.md` — handler pattern + canonical examples this command scaffolds.
- `references/changelog.md` — CHANGELOG format this command seeds.
- `references/output-format.md` — policy keys (`html-policy`, `smoke-mode`, `domain-docs`, `comprehension`, `close-gate`, `retention`) this command pre-fills. `archaeology` is the exception: never pre-filled — written only when the CHECKPOINT 1 offer is answered (`done YYYY-MM-DD` after the pass runs / `skipped` on decline), per `references/archaeology.md`; pre-setting it would suppress the one-time offer.
- `references/context-md.md` — CONTEXT.md format this command seeds.
- `references/roadmap.md` — `docs/ROADMAP.md` whole-plan-map convention this command seeds.
- `references/document-indexing.md` — TOC scheme for RESUME.md + iteration-journal.md placeholders.
- `references/release-process.md` — release workflow this command optionally generates.
- `references/harness-primitives.md` — native CC primitives; §2 defines the `SessionStart:resume` RESUME-injection hook this command installs (project-level, from `hooks/inject-resume.sh.template`).
