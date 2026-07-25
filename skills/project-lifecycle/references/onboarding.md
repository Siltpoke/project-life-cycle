# Onboarding — First Day in a Project

The first day on a project (for a human, for an AI agent, for a contractor, for a returning maintainer after a long pause) is **Q&A only**. No edits. No PRs. No `/ship`. Just questions about the codebase.

Sourced from Anthropic's internal onboarding practice (Boris Cherny, "Practical Tips for Claude Code"): "On the first day in technical onboarding, you learn about Claude Code, you download it, you get it set up, and then you immediately start asking questions about the codebase. Onboarding used to take two or three weeks. It's now about two or three days."

## Why Q&A-first

| Edit-first failure | Q&A-first counter |
|---|---|
| New joiner doesn't know which conventions to follow → diff drifts from house style | Q&A surfaces conventions before code is written |
| New joiner asks teammates → taxes the team's attention | AI answers in seconds with the actual code as reference |
| New joiner reads docs that have rotted → wrong mental model | AI reads current code (no stale wiki) and synthesizes accurate explanation |
| New joiner tries a one-shot edit → it doesn't compile / breaks tests / hits a hidden invariant | Q&A teaches the boundaries of what's safe to touch BEFORE touching |

The cost of one day of Q&A is far less than the cost of one week of un-shippable PRs from someone who skipped onboarding.

## Day 1 protocol (mandatory for any new contributor — human or AI)

### Step 1: Read the anchors (10 minutes)

In order, no skipping:

1. `CLAUDE.md` at repo root — universal project rules + folder map + policy keys.
2. `CONTEXT.md` (or `CONTEXT-MAP.md` + per-bounded-context `CONTEXT.md`) — domain glossary.
3. `docs/RESUME.md` — current milestone state + last phase delivered.
4. `docs/iteration-journal.md` (read the index/TOC + last 3 entries) — recent task history. On fragment-convention projects also `ls docs/journal.d/` for the undrained current-milestone entries (per `references/retention.md` §"Fragment convention").
5. `ls docs/superpowers/specs/` — what the active + recently-shipped phases are about; recently-shipped phases' FACT entries (`docs/journal.d/*.md`, or the compiled journal archive for a drained milestone) are the retired handoff file's replacement (`references/journal-schema.md` §"The FACT entry") — read those, not a `docs/handoff/` directory, which no longer exists on a post-retirement project.
6. `ls docs/adr/` — hard-to-reverse decisions to respect (skim titles; read bodies on demand).

If any of these are missing, surface as a finding before proceeding (project hasn't adopted this skill fully yet).

### Step 2: Codebase Q&A (the rest of day 1)

Ask the AI questions. NOT edits. Examples that teach the right mental model fast:

```
How is the <Repository|Service|Model> X used? Show me 3 different callers.
Why does this function have 15 arguments? Look through git history.
What does the <auth|payment|notification> system look like end to end?
How are <multi-tenant|timezone|i18n> concerns handled? Show me the pattern.
What's the difference between <ModuleA> and <ModuleB>? When do I use each?
Which tests cover <area X>? Are there gaps?
Look through GitHub issues labelled <bug|on-hold> — what are the recurring themes?
What did the team ship last week? (or "What did <user> ship this month?")
Walk me through the smoke checklist for the last shipped phase.
Which files in this repo are >800 lines? Are any of them ripe for splitting?
```

The AI uses `git log`, `gh issue list`, file reads, grep — no indexing required, no remote upload.

### Step 3: Run the project locally + smoke an existing phase (end of day 1)

- Run the install / build / test commands from `CLAUDE.md`.
- Pick the most recent Track A smoke checklist (`docs/smoke/*checklist*`, per `references/smoke-tracks.md`) and follow it. (There is no handoff doc to pick it from any more — the file was retired; the checklist is its own artifact.)
- Report back: what worked, what didn't, what was unclear in the docs.

Output is a "Day 1 findings" comment / message to the team — surfaces stale instructions + tooling gaps the team has stopped noticing.

### Step 4 (only on day 2+): Edit work via `/ship`

After day 1, pick the smallest user-observable feature in the backlog. Run `/ship <feature>` per the vertical-slice orchestrator. This forces the new contributor through the full discipline (story → spec → BE → FE → verifier → validator → PR) on a small surface where mistakes are cheap.

Day 2+ is when the team can start expecting actual deliverables. Day 1 is investment.

## End-to-end walkthrough: one real `/ship` run

Step 4 names the chain (`story → spec → BE → FE → verifier → validator → PR`) but structure alone doesn't show how each link *hands off*. Here is one real, merged phase traced link-by-link — the phase that built this skill's own `/tasklist` reader. Every excerpt below is real.

**Read the honest boundary first.** This repo is **single-layer** (a skill/docs repo, no backend/frontend split — declared `folder-map: single-layer`). The literal one-shot `/ship` command is built for a *user-observable vertical slice on an app*, so one of its links — the **Builder** — **degrades** here rather than firing in full: there is no backend/frontend to split. That one is flagged `⤵ degrades` below with what it would do on a real app. Every other link fired; where this phase shaped a link differently from the textbook (story merged into the design doc; the acceptance oracle was a test suite, not a separate verifier subagent), the row says so rather than dressing it up. This is the walkthrough's real lesson for anyone adopting plc on a similar single-layer repo — the chain doesn't lie about which links it actually ran, or how.

| Chain link | What really happened |
|---|---|
| **0. Intent-gate + research** | a one-line kickoff → Mode A brainstorm → research on the in-progress marker: `- [/]` is the Obsidian-Tasks de-facto status (🟢, ≥2 refs), beating `- [~]` (no backing) and a `🔁` glyph (breaks the checkbox family). |
| **1. Story** (**checkpoint 1**) | A real user story + nine numbered acceptance criteria were written and signed off. Shape note: they were captured *inside the design doc* (titled `# user story — <phase>`) rather than a standalone `user-story.md`, and the criteria doubled as the phase's "pinned exit regressions." On a bigger feature the story is usually its own file signed off *before* the spec. |
| **2. Spec** (**checkpoint 2**) | Locked decisions: `- [/]` marker · on-demand-only placement (statusline/watch-pane deferred) · "expand" = two verbosity levels (`brief` + `--tree`), because a terminal command's stdout can't do interactive fold. |
| **3. Builder** ⤵ degrades | Single-layer → **no BE/FE split**: one implementer. The terminal renderer core landed in an early commit (`scripts/tasklist-view.sh` + its test suite) and was reshaped to the shipped `brief`/`--tree` form in a later pivot commit. On a cross-layer app this link splits into folder-scoped BE→FE with a BE-emitted API contract the FE consumes. |
| **4. Acceptance oracle** | The nine exit regressions were verified by a **RED→GREEN `scripts/tasklist-view.test.sh` suite** (one of them label-independent) rather than a separate acceptance-verifier subagent, plus a **Track A smoke**: a real render of both `/tasklist` (brief) and `/tasklist --tree` against this phase's own `.claude/tasklist.md` (the reader reads the contract that tracked building the reader). |
| **5. Validator + code review** | The independent reviewer **proved the (then-present) browser-Artifact JSON injection broken on ordinary input** — awk `gsub` isn't literal, so a `&`/`\`/`${…}` in a task label silently corrupted or self-XSS'd the page — plus a second finding: a dead `total=` line. Read-only reviewer; the writer never graded its own work. |
| **6. Fix loop** | **Real mid-build PIVOT (drift = signal):** an artifact layer was built (`--json` flag, the `scripts/tasklist-artifact.html` template, the `/tasklist` command), rendered a blank page on this phase's own backtick-heavy text, and — after the user clarified they only wanted the collapse→expand *feel* in the terminal — was **removed wholesale** (three of the acceptance criteria marked VOID), taking every Important finding with it. Commits stay in history, never squashed; the removal is a later commit. |
| **7. PR** (**checkpoint 3**) | PR body = a plain-language **TL;DR** (Problem / What we did / Why / Result + honest boundary) above the 3-section format, with a `### Use cases` subsection; the 9-layer audit narrative + raw test evidence went on as a PR **comment**. Merged after both reviewer rounds came back clean. |

**What to take from it:** the chain is a hand-off contract, not a script that runs every link the same way every time. On a single-layer repo the Builder link degrades and says so; on an app it fires in full. Some links shape themselves to the phase (story folded into the design doc; a test suite as the acceptance oracle) — the record names the real shape instead of pretending the textbook ran. And a phase that pivots mid-build (link 6) isn't a failure — the honest record of *what was built, why it was removed, and where the commits still live* is exactly what the journal's "Plan deviations" header exists to force.

## Project-level shared `.claude/commands/`

Beyond the universal commands shipped via this skill (`/ship`, `/release`), every project should curate its OWN team-shared slash commands under `.claude/commands/` in the project root — checked into source control so every contributor (and every AI invocation) inherits the same shortcuts.

### Directory hierarchy (per Claude Code docs)

| Path | Scope | Checked in? | Use for |
|---|---|---|---|
| `~/.claude/commands/<name>.md` | User-personal | NO | Your own shortcuts; not shared |
| `.claude/commands/<name>.md` (in project root) | Project-shared | YES | Team-shared shortcuts everyone in this repo uses |
| Enterprise-policy path (org-level) | Org-shared | YES (org-managed) | Cross-repo policy commands the company maintains |

When the same name exists at multiple levels, more-specific wins (project > user > org).

### What belongs in `.claude/commands/<name>.md`

Every command file: YAML frontmatter with at least `description:`, body = the prompt / instructions the model executes when the user types `/<name>`.

```markdown
---
description: <one-line surfaced in the command picker>
---

# /<name>

<prompt body — instructions, tool list, expected output shape, error recovery, anti-patterns>
```

### Common project-shared commands (pick what fits)

| Command | What it does |
|---|---|
| `/test-phase` | Runs `make phase-checks PHASE=<arg>` with the right args + posts evidence in the format `references/ci-cd-gates.md` expects |
| `/db-snapshot` | Dumps current DB schema + sample rows so AI can answer schema Qs without a fresh inspection |
| `/start-stack` | Spins up the project's dev stack (DB, Redis, queue, frontend, backend) in tmux panes |
| `/triage-bug` | Loads `references/diagnose-loop.md` discipline + drops into Phase 1 feedback-loop construction |
| `/new-feature` | Project-specific wrapper over `/ship` that pre-fills the scenario table per the project's domain |
| `/release` | If your project overrides the universal `/release` (e.g., your CI gate needs a manual approval before tag push), drop the override here |

A project's `.claude/commands/` is its operational memory. Treat it the same as a team-shared `~/.bashrc.d/` — convention encoded in code.

### Onboarding handover: surface the project-shared commands on Day 1

The Day 1 anchor checklist (Step 1 above) gets one more entry when the project ships team commands:

```
7. ls .claude/commands/ — what slash commands does the team share?
```

Read each one's frontmatter description. Don't run them yet — but know they exist before you need them.

## When the project does NOT yet use this skill

If you land in a project that doesn't have `CLAUDE.md` / `CONTEXT.md` / `docs/RESUME.md` (or root `RESUME.md`) / `docs/iteration-journal.md` (or root — either location counts), Day 1 becomes: Q&A about the codebase + propose adopting this skill. Don't force adoption — surface the gap with concrete pain ("we don't know which conventions the team follows, so my edits will drift") and let the team decide. If the team decides to adopt: run `/init-harness` — on brownfield repos it detects the missing plc artifacts and offers the one-time archaeology pass (baseline ROADMAP / glossary / backfilled-ADR drafts, all AI-inferred and human-reviewed via `docs/adoption-snapshot.md`) at CHECKPOINT 1; full contract in `references/archaeology.md`.

## Anti-patterns

- **Skipping Day 1 because "I've used this kind of codebase before"** → every codebase has invariants the AI can't infer from the language alone (DB tenancy model, retry semantics, deploy gates, legal red lines). Q&A surfaces them in hours; skipping costs weeks.
- **Letting the AI agent edit on Day 1 because "it'll learn faster"** → edits before mental-model = drift that compounds. Q&A first is faster overall.
- **One-shot mega-Q&A** (asking 20 questions in one prompt) → the AI's responses become shallow; cap at one focused question per turn.
- **Asking questions a `grep` would answer in main context** → dispatch an `Explore` subagent; main context bloat hurts every later turn (per `cost-aware-behaviors.md`).
- **Project ships `.claude/commands/` without frontmatter descriptions** → command picker shows nothing useful; AI can't discover what's available. Every file needs `description:`.
- **User-personal commands at `~/.claude/commands/` shadow project-shared commands** → unexpected behavior for teammates. Name personal commands distinctly (e.g., `/my-<name>`) to avoid collision.
- **`.claude/commands/` not checked into source control** → defeats the team-shared point; everyone re-invents the same shortcuts.

## Cross-reference

- `references/cost-aware-behaviors.md` — Q&A in subagents not main context.
- `references/context-md.md` — the `CONTEXT.md` glossary read in Step 1.
- `references/builder-split.md` — `CLAUDE.md` `folder-map` schema read in Step 1.
- `commands/ship.md` — Day 2+ edit workflow.
- `references/release-process.md` — release flow (Day 1 onboarding doesn't release; later contributors do via `/release`).
