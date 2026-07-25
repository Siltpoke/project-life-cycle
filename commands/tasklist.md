---
description: Render the current phase's progress from .claude/tasklist.md (the tasklist contract) in the terminal. Default is a brief collapsed line — phase name, a progress bar with done/total, and the one step in progress ("▶ now: …"). `/tasklist --tree` expands the full overview — every task group with its count and each step glyphed ✓ done / ▶ in-progress / ○ todo, the current `- [/]` step flagged "← here". Pure jq-free bash, portable on every CLI. Read-only — renders the contract, never writes it.
---

# /tasklist — render the PLC tasklist progress view (terminal)

Show progress for the current phase from `.claude/tasklist.md` (the tasklist contract file).
The host todo widget (`TaskCreate` / `TodoWrite`) is absent on some session profiles and was never
portable across CLIs — this is PLC's own reader for the same contract, all in the terminal (no browser,
no artifact). Two verbosity levels, mirroring a collapsed → expanded view:

## Default — brief (collapsed "where we are now")

Run and render its stdout **verbatim** as your reply:

```bash
bash scripts/tasklist-view.sh
```

(In the installed plugin this path is under the skill dir; in a checkout of this repository it is
`scripts/tasklist-view.sh`.) Prints the phase name (from the `# …` line), a fixed-width progress bar
with a `done/total` count, and a single `▶ now: <task group> · <current step>` line for the first
in-progress (`- [/]`) step, ending with a `(/tasklist --tree to expand)` hint. If no step is marked
`- [/]`, it says so. Missing or empty file → a friendly message, exit 0.

## `/tasklist --tree` — expanded overview

```bash
bash scripts/tasklist-view.sh --tree
```

Same header, then the full tree: each `## task` group with its own `done/total`, and every step marked
`✓` done · `▶` in-progress · `○` todo. The **first** `- [/]` step is flagged `← here`; any further
in-progress steps render `▶` without the callout. Unknown checkbox chars are treated as todo; malformed
lines are skipped.

## Discipline

Read-only. This view **renders** the contract; it never writes `.claude/tasklist.md`. The writer sets
`- [/]` on the step in progress (see SKILL.md "Definition of Done" → the in-progress marker); `/tasklist`
only reads it.
