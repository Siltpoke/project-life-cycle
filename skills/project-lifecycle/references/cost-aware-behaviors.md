# Cost-Aware Behaviors

Per-token leverage rules. Synthesized from a survey of RTK, context-mode, token-savior, caveman, claude-token-efficient, plus common token-waste patterns in long agent sessions.

Even where cost is not the binding constraint, **every token should earn its place** — each wasted token compresses the working context window and increases the chance of hitting `/clear`-required limits mid-phase.

## Hard rules (apply every turn)

### Reading files

- **Default to `Read` with offset + limit** for any file over 200 lines. Read the whole file only when you have established (via grep / Explore) that you need ≥80% of it.
- **Re-reading the same file** in a session is a smell. Either:
  - The first read was too wide (use a tighter offset next time), OR
  - You're context-starved (note this and consider `/clear` or compaction)
- **Skill files** load on demand — invoke `Skill`, don't `Read` skill markdown.

### Running commands

- **Default to compact output flags:** `pytest -q`, `vitest --reporter=line`, `playwright --reporter=line`, `ruff check --output-format=concise`, `gh pr view --json title,state,url`.
- **Pipe verbose commands through `tail` / `head`** when only the last N lines matter (build output, test summary, log).
- **Capture into files** for anything > 50 lines that might need re-inspection: `pytest ... > /tmp/pytest.out` then `tail /tmp/pytest.out`. Lets you re-read selectively.
- **Use `-q` / `--quiet` modes** on every CLI that supports them. Loud-by-default tools (`npm install`, `pip install`) eat 500+ tokens of progress bars.

### Grep before Read

- **Search before reading.** A `grep -n 'symbol'` is ~50 tokens; a `Read` of a 600-line file is 3-5k tokens. Use grep to land at the line first, then narrow `Read` to ±20 lines around it.
- **Use the `Explore` agent** for "where is X / which files reference Y" — it reads excerpts only and returns a synthesis, cheaper than running 5 sequential greps yourself.
- **Codebase index** (codemap / token-savior / code-review-graph) — when available, query the index first. Treat it as authoritative for "where is X defined."

### Output discipline

- **One-sentence updates** between tool calls. "Running tests now." not "Let me kick off the test suite and we'll wait for the results."
- **No closing pleasantries.** Don't end every turn with "let me know if anything else." Just stop.
- **No re-summarizing the diff** after Edit/Write — the tool result already shows it.
- **No preamble.** "Sure! I'll..." → just do it.
- **Code comments default off** (system rule). Only add when WHY is non-obvious.

### Tool result hygiene

- **Tool results decay in usefulness** — that 500-line grep output from 10 turns ago is now noise. When a search is no longer relevant, summarize what you kept in 1 sentence in chat (it commits to context) and move on; the raw result decays into the context cache.
- **Capture tool output to files** when you'll need it later. Don't rely on scrolling back.

### Session boundaries

- **`/clear` at natural breaks** — phase boundary, task boundary, when context >50% and starting fresh work. The handoff doc + RESUME.md + mid-phase resume note make `/clear` safe.
- **Hot-path artifacts before /clear**: confirm handoff doc / journal / resume note are written so the next session has a tight entry point.
- **Deterministic backstop:** the `/clear at >50%` rule above is model-discipline; `hooks/context-floor.sh` (machine-local global PreToolUse:Edit|Write hook) enforces an absolute-token floor (default 150K) that blocks new Edit/Write until RESUME.md is refreshed. It is deliberately a hard block only — soft, advisory warnings are left to whatever session monitoring your host provides. See `references/harness-primitives.md` §9. Tune `PLC_CONTEXT_FLOOR` after watching it fire a few times. **Verify it's actually armed** — the `phase-done` gate prints a warn-only row when no settings file wires `context-floor.sh`, and `/init-harness --refresh` repairs the wiring (un-armed floors let sessions run far past the floor unnoticed). At task boundaries, `close-gate-nudge.sh` adds a throttled "/clear now" nudge when the task close passed clean and occupancy is over the floor.

### Skill invocation triage

Before invoking `project-lifecycle` (or any heavyweight workflow skill), apply triage:

| Task | Invoke project-lifecycle? | Action |
|---|---|---|
| Fresh project setup | YES | Full workflow |
| New milestone | YES | Full workflow |
| Multi-task feature with dependencies | YES | Full workflow |
| Decision needing online research | YES | At least brainstorm + research gate |
| One-off bug fix (small diff) | NO | Inline fix, single commit |
| Single-file polish | NO | Inline edit |
| Typo / docs tweak | NO | Inline edit |
| Single config knob change | NO | Inline edit |
| Refactor of one function | NO | Inline + journal one-liner |
| Test for one new function | NO | TDD inline |

The full workflow (brainstorm → plan → 6-step cadence → handoff → PR) is **100-300K tokens per phase**. Trivial work doesn't earn that overhead. Triage saves the majority of token waste from skill misuse.

### Workflow compression (when workflow IS invoked)

- **Cadence compression** — for tasks with small diff + no new logic + no security/compliance surface, merge spec + code review into one pass. Saves ~15-30K tokens per task.
- **Brainstorm Mode B for ≥3 questions** — Mode A dispatches research subagents per Q (2-4 agents/Q). Mode B shares overhead. Multi-Q phases save 50-100K tokens.
- **Single-tier research for BE-only / data-shape questions** — skip Tier 2 novice agent when the question doesn't have a UX dimension. Floor is still ≥2 reference products / sources.
- **Skip blind 2nd-agent only when explicitly safe** — `references/brainstorm-research-protocol.md` requires the blind step on locked decisions. Don't compress it to save tokens; the cost of confirmation bias is worse than the dispatch cost.

### Investigation: subagent vs main context

Big lookups burn main context. Heuristic:

| Investigation scope | Where to do it |
|---|---|
| Single grep / one file Read | Main context, direct tool |
| 2-3 quick lookups for a known answer | Main context, parallel tools |
| "Where is X defined / what calls Y / map this directory" | `Explore` subagent — returns synthesis, cheaper than 5 sequential greps |
| "Audit this entire dir / find all uses of Z across repo" | `general-purpose` subagent |
| Deep multi-step research with web | a deep-research subagent (e.g. PLC's `/research`) |
| Cross-file consistency / open-ended analysis | `general-purpose` with explicit synthesis instruction |

Main context bloat hurts every subsequent turn until `/clear`. Subagent results land as a compact summary that the main context absorbs cheaply.

### Model selection per subagent

| Model | Best for | Cost relative |
|---|---|---|
| **Haiku 4.5** | High-frequency lightweight: trivial implementer, journal entry generator, brainstorm Tier 2 research, simple linter-fix dispatch | 1x |
| **Sonnet 4.6** | General coding: typical implementer, spec reviewer, code reviewer, brainstorm Tier 1 research, plan generator | ~3x Haiku |
| **Opus 4.7** | Orchestrator / controller context, architectural decisions, deep verification, blind 2nd-agent on critical decisions | ~10x Haiku |

Default subagent dispatches in `superpowers:*` inherit the orchestrator's model unless overridden. **Explicitly specify model when dispatching** to avoid burning Opus tokens on a typo-fix subagent.

Example: `Agent(subagent_type=Explore, model=haiku, …)` for cheap lookups.

## Adopt-on-tool list (when these tools are installed)

| Tool | What changes |
|---|---|
| **RTK** (Rust bash proxy) | Most `git`/`pytest`/`playwright`/`eslint` calls auto-compress 60-90%. No code change; just expect tool results to be shorter. Failures are tee'd to disk for re-inspect. |
| **token-savior** (MCP) | Use `mcp__token-savior__*` tools for symbol lookup INSTEAD of `Read` on large files. The tool reports a large reduction in injected characters; measure on your own codebase before relying on the figure. |
| **context-mode** (MCP) | Tool outputs sandboxed; query with intent strings to get only relevant chunks. Heavy install — only adopt for large-codebase / long-session projects. |
| **code-review-graph** (MCP) | Use `mcp__code-review-graph__*` for blast-radius analysis BEFORE editing — find affected callers/tests with one query instead of grep-fests. |

## Project-specific Make targets

Every project should have:

- `make codemap` — generates a per-directory index (≤200 lines each) listing classes / functions / routes. Used as the "where is X" pre-Read filter.
- `make phase-checks PHASE=X.Y` — see `smoke-tracks.md`. Outputs feed handoff doc §5/§6.

## Anti-patterns

- **"Just to be safe, I'll read the whole file"** — that's 5k tokens of caution. Read 30 lines around the symbol; if you find you needed more, expand. Token cost of being wrong once < cost of being conservative every time.
- **Narrating each tool call in chat** — "Now I'll check the migrations folder..." → just check it. The tool call IS the update.
- **Capturing full test output for verification** — `pytest -q | tail -3` gives you `N passed in Xs` which is all you need 90% of the time.
- **Re-deriving via grep what you already learned this session** — write it down in TaskCreate / a memory entry; don't burn tokens re-discovering.
- **Re-reading CLAUDE.md / spec / plan to "refresh memory"** — they're in your context already if the session loaded them, or they're not (in which case Read with tight offset/limit on the section you need).

## Measuring

There's no perfect token-cost telemetry. Proxy measures:

- **Session length before /clear** — if phases used to need /clear at T8 and now reach T12 without it, the discipline is working.
- **Number of full-file Reads per phase** — count from session log; trend should drop.
- **Tool output size** — RTK / token-optimizer / context-mode all surface this metric in their dashboards.

Discipline > tools. The tools amplify discipline; without discipline (re-reading, narrating, capturing whole outputs), tools just defer the problem.

## Origin

This doc distills a survey of 8 token-optimization tools (RTK, context-mode, code-review-graph, token-savior, claude-token-optimizer (nadimtuhin), token-optimizer (alexgreensh), caveman, claude-token-efficient). Synthesis: 80% of the value comes from disciplined behaviors that don't need any tool; the remaining 20% comes from RTK + token-savior install. This doc captures the discipline; the install-tier recommendation is separate (per-project decision).
