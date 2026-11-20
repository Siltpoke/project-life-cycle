# Skill overview: harness framing + unattended-run judgment (moved verbatim)

<!-- plc-move:unattended-runs -->
The runtime that used to live here was extracted 2026-07-14 into its own repo, full history
preserved. *Why the split*: this skill is markdown fed to a coding agent — it sits **inside** that
agent's loop and changes how it thinks. The runtime is **code that spawns the agent as a worker**.
Same machine, inverted topology.

**What stays here is the judgment**: the intent-gate's 4-condition AFK-eligibility axis
(`references/intent-gate.md`), the HITL/AFK labels (`references/issue-breakdown.md`), the 4-field
loop contract as a *spec* (Goal / Stop / Budget / Report), and the **egress policy** — loop terminus
is a pushed `loop/` branch plus a report; merge is human-only (see Red Flags). **What left is the
how**: the fence and its one real wall (the post-round out-of-fence diff check — a `PreToolUse` hook
fails open and is telemetry, not a wall), the end states with derived death codes, the dual-window
budget breaker, the run-scoped registry where `passes` is writable **only** by the deterministic
verify step, and the task-orchestrator layer on top.

> ⚠️ **Corrected 2026-08-06.** This section used to end: *"That runtime has never run against the
> real `claude` CLI — 397 tests, all against a stub."* **That was stale by three weeks.** The
> real-CLI smoke ran 2026-07-15: run 1 caught a scope-fence false positive that no amount of green
> unit tests could surface (the stub reported paths the way the fence expected and the real CLI did
> not); run 2, after the fix, reached `COMPLETE` with the fence passing. The claim is corrected here
> rather than quietly deleted, because **the same stale sentence lived in two repos and only one of
> them was fixed** — a status line outliving its
> evidence in a second copy is exactly the failure mode this skill's verification story is about.
> **What is still unproven is the budget half**: run 2 landed in a fresh window at 0%/0%, so the
> breaker's window math has never fired in anger. Cite that as the open gap, not the smoke.
<!-- /plc-move:unattended-runs -->

<!-- plc-move:harness-framing -->
Borrowing Tejas Kumar's framing ("Why Your AI Agent Needs a Harness", 2026): an **agent harness** is everything around the model that grounds it in reality. The model is a black box; the harness is the deterministic scaffolding that makes the model's output reliable enough to ship.

This skill is exactly that — applied to multi-phase software development. Its parts map cleanly onto the harness primitives Tejas describes:

| Harness primitive | Realized in this skill as |
|---|---|
| **Tool registry** | The set of subagents the orchestrator dispatches: researcher, story-writer, spec-writer, backend-builder, frontend-builder, acceptance-verifier, validator, reviewer, journal-writer (per `references/cadence.md` + `references/builder-split.md` + `references/reviewer-brief.md`) |
| **Guardrails** | Mandatory Conventions + Red Flags below; folder-map scoping; cadence step caps; CHANGELOG / PR label / Conventional Commits enforcement |
| **Context management** | Mandatory `/clear` between phases; journal entry + RESUME.md as canonical session-boundary contract; cost-aware behaviors (offset+limit reads, subagent investigation, compact output flags) |
| **Agent loop** | Per-phase workflow (11 steps) + per-task cadence (6 steps); orchestrated by `/ship` for single vertical slices |
| **Verify step** | Acceptance verifier (cadence step 1.5) + Validator (cadence step 2) + dual-track smoke (`references/smoke-tracks.md`) + verify-loop pattern (`references/verify-loop.md`) — all designed so the AI doesn't self-grade |
| **Deterministic pre-step handlers** | Pattern doc at `references/deterministic-handlers.md` for project-specific auth / secret / pre-flight / safety injection |
| **Lie detection** | Validator explicitly checks builder claims against the diff + acceptance verifier report (`references/cadence.md` §step-2) |

If you're new to the skill, the practical implication of the harness framing is: **the AI alone is not enough; the harness IS the contract.** Don't ask "can the model do this" — the model can do most things. Ask "is the harness wired correctly for the model to do this safely + verifiably + repeatably."

**Native platform primitives.** Several harness concepts above are now realized by first-class Claude Code features rather than prose the model must remember — skill-frontmatter hooks (this skill ships a `hooks:` block: a **best-effort, fail-open** `--no-verify` / push-to-main speed bump + a throttled close-gate nudge — the enforcing layers remain the pre-push hook and branch protection), `SessionStart:resume` RESUME injection, dynamic Workflows for deterministic cadence fan-out, `run_in_background` parallel reviewers, worktree-isolated builders, `AskUserQuestion` for opt-in checkpoints, and plan mode for sign-off gates. The verified map (which primitive strengthens which node + how to wire it, with verification provenance) is `references/harness-primitives.md`. Each one moves a rule from "model self-discipline" toward "platform enforcement" — the same direction Definition of Done + the close gate already point.
<!-- /plc-move:harness-framing -->

<!-- plc-move:builder-profile-blurb -->
**Builder profile (opt-in, user-typed `/builder-profile`)** — reads the user's own local Claude Code transcripts (`~/.claude/projects`) and writes one markdown report to `~/.claude/builder-profile.md`: a point-in-time snapshot of how this user actually uses an AI coding agent. Purpose is self-understanding (the user sees their own patterns → can use the agent better) + shared passive context any agent can read on demand. 100% local (no network call). Gated pipeline (deterministic `stats.json` → evidence gate → self-blinded cold read → adversarial verify → independent verification: a tested `builder_profile_verify.py` hard-assertion gate + a fresh-context cold critic, so the generator doesn't grade itself); spine-first synthesis; descriptive by default (1-10 scores behind `--scores`), operating-modes-not-archetype, co-discovery-not-growth-edge, you-vs-you-not-leaderboard — same discovery-over-judgment discipline as comprehension co-discovery. The report **is** the product — no separate memory seed, no skill step wired to consume it. After it passes verification the command **walks the user through it in plain language** in-conversation (spine-first, honest about what couldn't be measured, co-discovery as real questions), not just a path drop. **Output lives at the stable read-contract path `~/.claude/builder-profile.md`** (present → passive working-style context; absent → not yet profiled) — see `references/builder-profile.md` §"Read contract". See `commands/builder-profile.md` + `references/builder-profile.md`.
<!-- /plc-move:builder-profile-blurb -->

<!-- plc-move:comprehension-blurb -->
**Comprehension co-discovery (opt-in, phase-level)** — when `comprehension` is `lite`/`full` in `CLAUDE.md`, run one anti-cognitive-offloading round once per phase after validation (a *why*-question on the validated diff; discovery framing, non-blocking, no scoreboard, <30s). Off by default. See `references/comprehension-co-discovery.md` + `references/cadence.md` §"Comprehension Co-Discovery".
<!-- /plc-move:comprehension-blurb -->
