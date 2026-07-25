# Native Claude Code Harness Primitives

This skill predates a wave of native Claude Code primitives that now realize, as
first-class platform features, several harness concepts the skill previously could
only describe in prose ("dispatch parallel reviewers", "the un-bypassable layer",
"auto-load RESUME on resume"). This doc maps each **verified** primitive to the
skill node it strengthens, and how to use it.

> **Verification provenance.** Every primitive below was checked against the
> official `code.claude.com/docs` changelog + hooks reference on **2026-06-08**.
> Two primitives a research pass had suggested were checked and **NOT found** —
> `/batch` and skill-frontmatter `invocationMode` — and are deliberately omitted.
> Do not cite them. Re-verify versions before relying on exact behavior; the
> platform moves fast.

The skill's framing still holds: **the harness IS the contract.** These primitives
just move more of the contract from "model remembers the prose rule" to
"platform enforces it deterministically" — which is exactly the direction the
"Definition of Done" + close-gate already point.

---

## 1. Skill-frontmatter hooks — the self-enforcing layer

**What it is.** Hooks declared directly in this skill's YAML frontmatter, scoped to
the skill's lifecycle: they fire **only while the skill is active** (invoked). All
hook events are supported (`PreToolUse`, `Stop`, `SubagentStop`, …). `Stop` /
`SubagentStop` can return `hookSpecificOutput.additionalContext` to inject text
back into the model's context.

**Verified firing (2026-06-08).** A throwaway test skill confirms in a
live session that a frontmatter `PreToolUse:Bash` hook fires on a real tool call
AND its `additionalContext` is injected into the transcript. Registration happened
**mid-session** on skill invocation (no restart needed to register; but see the
caveat below).

**Node it strengthens.** "Definition of Done" + `references/close-gate.md`. The
close-gate's weakest layer was "model-run discipline". Frontmatter hooks add a
platform-enforced nudge that ships *with the skill* — no per-project `settings.json`
wiring required.

**How this skill uses it** (see SKILL.md frontmatter `hooks:` block + scripts in
`skills/project-lifecycle/hooks/`):
- `PreToolUse:Bash` → `hooks/guard.sh`: blocks `--no-verify` and direct
  `git push` to `main` while the skill is active (exit 2 = block). Belt-and-braces
  with the git pre-push hook; this one travels with the skill.
- `PreToolUse:TaskCreate|TodoWrite` + `PreToolUse:Edit|Write|MultiEdit|NotebookEdit`
  → `hooks/tasklist-first.sh` (`mark` / `check`): realizes Definition-of-Done forcing
  function 1 as platform enforcement — the first file edit of each phase is blocked ONCE
  (exit 2, actionable message carrying a nonce to transcribe) when no task list has been
  created yet. After that single block it is still never a wall, but it no longer goes
  silent: each later gated call returns `permissionDecision: "defer"` plus an
  `additionalContext` **UNVERIFIED** notice, keeping "could not verify" distinct from
  "verified" in the model's context. `defer` is deliberate — `allow` would proceed
  *without the user's permission prompt*, buying the guard's visibility with the human's
  consent, and `permissionDecisionReason` is explicitly not shown anywhere under `allow`, and unspecified under `defer`. A close-gate run
  (`make task-done`/`phase-done`, `close-gate.sh`) re-arms the guard so the NEXT phase
  re-forces a fresh ≥`PLC_TASKLIST_MIN` list — PLC's "one task = one list = one gate"
  boundary (`PLC_TASKLIST_REARM=1`, default on; set `0` for once-per-session).
  `RESUME.md` writes exempt (context-floor deadlock guard); `PLC_TASKLIST_GUARD=0` disables.
- `Stop` + `SubagentStop` → `hooks/close-gate-nudge.sh`: **conditional** — emits an
  `additionalContext` reminder ONLY when on a `feat/phase-*` branch with uncommitted
  changes or stale test-evidence. Silent otherwise (no per-turn noise).

**Caveats / layer rules.**
- **`SessionStart` does NOT belong in skill frontmatter** — at session start the
  skill is not yet active, so the hook would never fire. Session-start behavior
  (e.g. RESUME injection, §2) lives in project `settings.json`.
- Keep hook *logic* in a shipped script (`hooks/*.sh`), not inline in the
  frontmatter command string — the script is unit-testable standalone (pipe it a
  fake event JSON, assert stdout shape + exit code); the frontmatter is not.
- A broken frontmatter `hooks:` block can make the skill fail to load. Always run
  the YAML-parse + script-standalone checks (see `hooks/test-hooks.sh`) before
  committing a hook change.
- Live skill edits do not reload mid-session — new/changed hooks take effect next
  session.

---

## 2. `SessionStart` hook matchers (`resume` / `clear` / `compact` / `startup`)

**What it is.** A `SessionStart` hook can match on *how* the session began. The
`resume` matcher fires on `--resume` / `--continue` / `/resume`; `clear` fires on
`/clear`; `compact` on compaction.

**Node it strengthens.** The skill's core context-boundary contract: mandatory
`/clear` between phases + `RESUME.md` as the canonical resume artifact. Today the
model is *told* to read RESUME on resume; a `SessionStart:resume` hook makes that
deterministic — inject the current phase + RESUME head automatically.

**How to wire it.** This is a **project** concern, not a skill-frontmatter one
(skill inactive at session start). Ship it as a recommended block in the project's
`.claude/settings.json`, installed by `/init-harness`:

```json
{ "hooks": { "SessionStart": [
  { "matcher": "resume",
    "hooks": [{ "type": "command",
      "command": ".claude/hooks/inject-resume.sh" }] } ] } }
```

where `inject-resume.sh` emits `hookSpecificOutput.additionalContext` with the head
of `RESUME.md` + the current `feat/phase-*` branch. Do NOT install this into the
user's global `~/.claude/settings.json` — it is per-project, and the global file
holds the user's own unrelated hooks.

---

## 3. Dynamic Workflows / `ultracode` — deterministic cadence orchestration

**What it is.** Script-driven orchestration (`pipeline()` / `parallel()` /
`agent({schema})`) that fans work across many subagents with code-controlled flow
and schema-forced structured output. Triggered by the `ultracode` keyword (renamed
from `workflow`, v2.1.160) or "ask Claude to create a workflow".

**Node it strengthens.** The per-task cadence (`references/cadence.md`) and `/ship`
are currently prose step-lists executed by model self-discipline — exactly the
"model feels done, skips wrap-up" failure the skill fights. A Workflow script makes
the fan-out (implementer → {acceptance verifier ∥ code-quality, independent}; validator
joins once the verifier reports — not waiting on code-quality — then fixup → journal,
per `cadence.md` §"Background-by-default") **deterministic control flow**, and
`schema` forces each step to return a validated object instead of free text.

**Status / how to adopt.**
- **Documented option now.** When a cadence task or `/ship` slice is large and the
  orchestration shape is known, encode it as a Workflow script: `pipeline()` over
  the cadence steps, `parallel()` for the independent reviewers (§4), `schema` on
  each `agent()` for the Builder Summary / Validator Report / Acceptance Report.
- **Full `/ship` → Workflow conversion is its own milestone**, not a doc edit — it
  re-implements `commands/ship.md` as a script and must go through this skill's own
  brainstorm → spec → TDD discipline; do not silently rewrite.

---

## 4. `run_in_background` + `Monitor` — parallel independent reviewers

**What it is.** `Agent(run_in_background: true)` detaches a subagent; `Monitor`
waits on completion. Parallel sibling tool calls no longer cancel each other on one
failure (v2.1.154).

**Node it strengthens.** The cadence verification tail — acceptance verifier
(step 1.5: reads only the story + Builder Summaries, never implementation source,
writes only `tests/acceptance/*`) plus Validator (step 2) and Code-quality review
(step 3), both read-only passes over the builder's diff. None of the three writes
to source, so background concurrency is conflict-free. This is now
**background-by-default**, not an optional optimization: verifier + CQ dispatch in
background at implementer-return, the validator joins when the verifier report
lands, and the controller blocks only at the fixup step. Canonical rule +
dependency graph:
`references/cadence.md` §"Background-by-default: the verification tail"
(sequential one-at-a-time reviews add substantial pure waiting per phase).

**Guard.** Keep the ordering dependencies that ARE real: implementer (step 1) →
the tail; and the validator's lie-detection consumes the Acceptance Verifier
Report as well as the Builder Summary, so the validator starts after the verifier
report lands (with implementer-return when step 1.5 is skipped/compressed).

---

## 5. Worktree isolation (`isolation: "worktree"`, `EnterWorktree`)

**What it is.** An agent can run in its own git worktree so parallel agents mutating
files don't collide. (Expensive — only when agents actually write in parallel.)

**Node it strengthens.** `references/builder-split.md` (BE + FE builders) and
`references/issue-breakdown.md` (tracer-bullet issues). The split currently relies
on **folder-scoped tools** as a soft boundary; worktree isolation is the *physical*
version when BE and FE genuinely run concurrently. Use it only when parallelizing
builders — the BE→FE sequence (BE emits contract, FE consumes) usually does NOT
need it, and worktree setup has real per-agent cost.

---

## 6. `AskUserQuestion` — structured opt-in checkpoints

**What it is.** A native structured multiple-choice prompt (labels + descriptions +
a recommended-first option), instead of free-text "I'll ask in prose".

**Node it strengthens.** The skill has many "ask the user once" opt-ins currently
phrased as prose questions:
- brainstorm Mode A vs B (`references/brainstorm-research-protocol.md`)
- `html-policy` companion opt-in (at the asking moments `references/output-format.md` defines — that file is the only place they are listed)
- `smoke-mode` self vs guided (step 8)
- intent-gate confirm-intent (`references/intent-gate.md`, when a question is
  genuinely needed)

Use `AskUserQuestion` for these: it makes the choice + recommendation legible and
one-tap, and the answer is machine-readable. Keep prose for genuinely open-ended
elicitation (brainstorm design questions) — `AskUserQuestion` is for bounded forks.

---

## 7. Plan mode (`EnterPlanMode` / `ExitPlanMode`) — checkpoint gates

**What it is.** A native read-only planning mode; `ExitPlanMode` surfaces the plan
for explicit user approval before any edit.

**Node it strengthens.** The skill's human checkpoints: `/ship`'s 3 checkpoints
(story / spec / PR) and the per-phase Plan step (4). Wrapping the plan/spec
sign-off in native plan mode turns "the model promises it paused for approval" into
a platform-enforced gate that cannot edit until the user exits plan mode.

---

## 8. Smaller wins — `/goal`, `/context`, `/branch`

- **`/goal`** (v2.1.139): set a completion condition; Claude keeps working across
  turns until met. Useful for a long-running phase that spans `/clear` boundaries —
  encode the phase's exit criteria (close-gate green) as the goal. Optional.
  **Loop-design rules when adopting it** (🟡 Anthropic loop-design write-up,
  R. Lance Martin 2026-06 — vendor post, small-n; direction trusted, numbers not):
  - **The rubric must be checkable, not vibes.** This skill already has one: the
    close-gate manifest (`make phase-done` criteria). Point the goal at "gate
    exits 0 with output pasted", never at prose like "phase feels complete".
  - **Grading stays out of the worker's context.** The write-up's finding —
    verifier sub-agent outperforms self-critique because grading happens in an
    independent context window — is this skill's existing rule ("the writer never
    reviews its own work", controller-computed verdicts). `/goal` adds
    persistence, NOT a license to self-grade; satisfaction is still judged by the
    deterministic gate + independent verifier subagents, not by the looping model.
  - **Layering:** `/goal` = self-correction layer (model keeps hillclimbing);
    close gate + pre-push hook = un-bypassable floor. The former never replaces
    the latter.
- **`/context`** (and `/context all`): visualize what consumes the window
  (CLAUDE.md / skills / subagents / MCP / history). Add to
  `references/cost-aware-behaviors.md` as the tool to decide `/clear` vs `/compact`
  at a phase boundary, instead of guessing.
- **`/branch`**: fork the session mid-conversation to try an alternate approach
  without losing the original. Useful during brainstorm when exploring two designs,
  or before a risky refactor. Optional.

---

## 9. Context-saturation hard floor — deterministic block (enforce-only)

**What it is.** `hooks/context-floor.sh`, a single PreToolUse:Edit|Write hook that
turns the prose "`/clear` at >50%" rule (`cost-aware-behaviors.md`) into a
deterministic *block*. It reads the transcript JSONL's newest assistant `usage`
(`input_tokens + cache_read_input_tokens + cache_creation_input_tokens`) to compute
context occupancy and compares it to an **absolute-token** floor. Over the floor and
without a fresh `RESUME.md`, it `exit 2`s — blocking the edit until the model
checkpoints.

**Why no warning / no Stop hook.** A soft "you're getting full, consider
compacting" warning layer is a separate concern, and deliberately not part of this skill.
The floor deliberately does the ONE thing a warning
cannot: a hard block. It is **enforce-only** — no `detect` mode, no Stop hook, no
additionalContext message.

**Self-arming.** The first over-floor Edit/Write creates a session-keyed marker and
blocks. A `RESUME.md` newer than that marker clears it and allows work. No separate
arming step is needed — the gate arms itself on the tool call it blocks.

**RESUME exemption (deadlock guard).** Writing/refreshing `RESUME.md` is the action
that CLEARS the block — so a Write/Edit whose `tool_input.file_path` resolves to the
RESUME path (or any `RESUME.md` basename) is NEVER gated. Without this the gate
deadlocks: you can't write the checkpoint that unblocks you. (Caught in a real session —
the hook went live mid-session and blocked its own RESUME write.)

**Node it strengthens.** `cost-aware-behaviors.md` §Session boundaries and the
RESUME contract. The "80% problem" — the model degrading past its own context
boundary instead of checkpointing — was the one part the soft warners never
enforced; this is the floor.

**Why machine-local global, NOT skill frontmatter.** Frontmatter hooks fire only
while the skill is active (§1) and would miss every non-workflow session, which is
exactly when long single-task sessions saturate. So this wires into the user's
`~/.claude/settings.json` (fires every session), merged with the other live hooks —
it does NOT go in the SKILL.md `hooks:` block.

**Arming verification.** Machine-local wiring has a failure mode the hook
itself cannot catch: it is simply never installed, and nothing notices — a session
can run far past the floor while the hook sits unarmed, and nothing
reports it. Three layers now close the gap: (1) the `phase-done` gate prints a
**warn-only** row when no settings file references `context-floor.sh`
(`references/close-gate.md` — warn, never fail: the floor is the user's global
config); (2) `/init-harness --refresh` offers the idempotent repair (merge the
`PreToolUse` entry, never clobber); (3) `close-gate-nudge.sh` reads the same floor
env at task boundaries — clean tree + fresh test-evidence + occupancy ≥ floor →
one throttled "/clear now" nudge, because the task boundary is the cheapest moment
to checkpoint (late-session turns cost 2-3× early turns).

**Wiring (machine-local `~/.claude/settings.json`, MERGE into existing `PreToolUse`):**

```json
{ "hooks": {
  "PreToolUse": [ { "matcher": "Edit|Write",
    "hooks": [{ "type": "command", "command": "<SCRIPT>" }] } ]
} }
```

`<SCRIPT>` = absolute path to the installed `context-floor.sh`. That file usually already
has other `PreToolUse` entries — append, don't clobber.

**Three safety rails.** (1) Never auto-`/clear` — the script only blocks/records;
the destructive clear is always a human/model action. (2) Threshold is absolute
tokens by default (`PLC_CONTEXT_FLOOR=150000`) — a rot curve bites by ~50K
regardless of window size, so a 1M window at 80% = 800K is the wrong frame. But
window-occupancy is the mental model many users actually run on, so an **opt-in
window-% mode** is available: set `PLC_CONTEXT_FLOOR_PCT` (e.g. `70`) and the
trigger becomes `PLC_CONTEXT_WINDOW × pct/100` (window default 1,000,000),
overriding the absolute floor. Pick one frame; absolute stays the default. (3)
Escape hatches — `PLC_CONTEXT_FLOOR=0` (and `PLC_CONTEXT_FLOOR_PCT=0`) disables;
`rm <marker>` overrides once. Anti-nag: after a checkpoint clears the marker, the
floor re-arms only when occupancy climbs a further `PLC_CONTEXT_FLOOR_STEP`
(default 30K). Fails OPEN on any read/parse/write error. Tests in
`hooks/test-hooks.sh`.

---

## Adoption summary

| Primitive | Skill node | Status |
|---|---|---|
| Frontmatter hooks | close-gate / Definition of Done | **wired** (SKILL.md `hooks:` + `hooks/`) |
| `SessionStart:resume` | RESUME contract | recommended project-settings block (init-harness) |
| Workflows / `ultracode` | cadence + `/ship` | documented option; a full `/ship` port is a separate piece of work |
| `run_in_background` / `Monitor` | cadence steps 1.5-3 | **default** (background verification tail, `cadence.md` §Background-by-default) |
| Worktree isolation | builder-split / issue-breakdown | documented (only when builders run concurrently) |
| `AskUserQuestion` | opt-in checkpoints | documented (replaces freeform forks) |
| Plan mode | `/ship` + Plan-step checkpoints | documented |
| `/goal` `/context` `/branch` | cost-aware / phase span | documented, optional |
| Context-saturation floor | cost-aware / RESUME contract | **shipped** (`hooks/context-floor.sh` + tests); wire machine-local global |
