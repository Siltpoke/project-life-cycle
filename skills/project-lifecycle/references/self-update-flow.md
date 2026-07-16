# Self-Update Flow

How an AI agent (the assistant using this skill) updates the skill itself when the user says "update the workflow" / "add this rule" / "change how we do X."

**The repo is the single source of truth.** The skill is consumed as a versioned plugin (installed from the marketplace into the plugin cache); released changes reach users only through a version bump + release. Unreleased changes are run straight from the repo working tree via `claude --plugin-dir <repo-path>` — no second "live" copy, no sync step.

> Historical note: this skill used to maintain a live copy at `~/.claude/skills/project-lifecycle/` mirrored to the repo by `scripts/sync.sh`. That flow was retired (the live copy stopped existing; the plugin cache replaced it as the consumption path). If you find sync instructions anywhere, they are stale — edit the repo.

## When to update the skill (vs. a project's CLAUDE.md)

When the user asks for a rule change, FIRST decide scope:

| Signal | Update the skill | Update project's CLAUDE.md |
|---|---|---|
| Rule applies to every project the user runs | ✅ | ❌ |
| Rule about a specific stack (Django, Rails, Postgres) | ❌ | ✅ |
| Rule about a specific business domain (accounting, healthcare) | ❌ | ✅ |
| Rule about specific tools (RTK, caveman) | ✅ (adopt-tier doc) | ❌ |
| Rule about the per-phase workflow itself | ✅ | ❌ |
| Rule about audience / mom-test / industry references | ❌ (project-specific) | ✅ |
| The user explicitly says "add this to the project-lifecycle skill" | ✅ | ❌ |
| First time seeing this pattern, not yet proven cross-project | ❌ (try in CLAUDE.md first, promote later) | ✅ |

**Default when ambiguous:** put it in the project's CLAUDE.md. Promote to the skill only after the same rule has been useful in ≥2 projects, or the user explicitly says it should be universal.

## Default update flow (no release)

Triggered when user says: "update the workflow to X", "add this rule to the skill", "note this for future projects", etc. (the user's actual wording may be in any language; intent = cross-project scope).

```
1. Confirm scope (skill vs project CLAUDE.md) — ASK if ambiguous.
2. Edit the repo: skills/project-lifecycle/SKILL.md or references/<file>.md,
   on a feature branch (never direct to main).
2b. If you touched the skill's `hooks/` (frontmatter hook scripts or the
    SessionStart template), run `hooks/test-hooks.sh` and confirm all green BEFORE
    committing — a broken `hooks:` block can stop the skill loading. See
    `references/harness-primitives.md` §1.
3. Run `python3 scripts/validate.py` — must pass before the PR.
4. PR per CONTRIBUTING.md (Conventional Commits title, one label, CHANGELOG
   [Unreleased] entry when user-visible).
5. NO version bump, NO tag, NO release. Edits accumulate; release is a
   separate explicit step. Installed sessions keep using the released
   version until the next release ships.
```

## Trying unreleased changes

To prove a change on a real phase before (or after) merging — without cutting a release:

```
claude --plugin-dir /path/to/your/clone/project-life-cycle
```

- The working-tree version of the plugin loads for that session and **shadows the installed marketplace version** (same plugin name → local wins for the session).
- The flag is per-session — a session launched without it runs the released cache version. Confirm what's loaded via `/plugins` at session start before trusting the result.
- SKILL.md / reference text edits take effect immediately; `hooks/` and `commands/` changes need `/reload-plugins` (or a session restart).
- The working tree is live: whatever branch + uncommitted state the repo is on is what runs. Record the commit SHA when reporting a finding from such a run.

## Release flow (explicit, version-bumping)

Triggered ONLY when user says: "release vX.Y.Z", "ship the skill", "tag a release", or equivalent explicit publish intent in any language. Never auto-triggered.

Use `/release` (see `references/release-process.md`) — it computes the SemVer bump from `[Unreleased]`, renames the CHANGELOG section, bumps both `.claude-plugin/marketplace.json` and `.claude-plugin/plugin.json` (they MUST match), commits, tags, pushes, and verifies the GitHub Release. One human checkpoint (confirm version). After release: installed copies pull via `claude plugin marketplace update project-life-cycle && claude plugin update project-lifecycle`.

## Mid-phase update safety

If the user asks to update the skill while mid-phase on another project:

1. A repo edit does not change any running session — sessions run the released cache version (or an explicit `--plugin-dir` working tree). That isolation is a feature: merge freely; adoption happens at the next release + update.
2. If the rule is about the active project's process, prefer putting it in that project's CLAUDE.md first (immediate effect, low risk).
3. Never cut a RELEASE mid-phase if the change alters the current phase's exit criteria. That's a moving-target violation of the milestone-done gate's contract. Merging to main is fine; releasing waits for the phase boundary.

## What to write down vs. what to verify first

The user might say "we should always do X" in a moment of frustration. Before editing the skill:

- Has this happened ≥2 times across projects? If only once, it might be project-specific.
- Is the user proposing a rule, or just venting? Clarify if ambiguous.
- Will adding this rule conflict with an existing rule? If so, surface the conflict — don't silently override.

The skill is the high-water mark of process discipline. Adding a rule means every future project pays a small attention cost reading it. The bar is "I've been bitten by this enough times that future-me wants reminding."

## Anti-patterns

- **Auto-bumping version on every edit** — pollutes Releases with non-events. Bump only on explicit release.
- **Editing `~/.claude/skills/project-lifecycle/` expecting it to publish** — that path is not part of this skill's flow anymore (and on most machines doesn't exist). Edit the repo; try it with `--plugin-dir`.
- **Trying a change without checking what is loaded** — a session launched without `--plugin-dir` silently runs the released version; "my change has no effect" is then a false negative. `/plugins` first.
- **Releasing mid-phase when the change affects the current phase's criteria** — moving target. Merge OK; release waits.
- **Adding rules without checking if they conflict with existing references** — duplicates and contradictions hurt more than no rule.
- **Skipping validate.py** — it gates the PR. Don't bypass.
- **Cherry-picking rules from one project into the skill without abstracting them** — project-specific glossary entries or a particular audience label (e.g. "novice users in vertical X") do NOT belong in the universal skill; promote the *pattern* (in-context help on novice surfaces, audience-priority concept) without project specifics.

## Bootstrapping a fresh agent

If a new Claude Code session starts and the user says "update the workflow," the agent should:

1. Read this doc (`references/self-update-flow.md`) first.
2. Find the repo via the user (or search common clone locations: `~/Code/`, `~/repos/`, `~/src/`, `~/Projects/`, etc.).
3. Work on a feature branch in the repo; follow the default update flow above.
