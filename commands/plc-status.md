---
description: Render the lifecycle ledger — for every mandated stage of a run, whether it was observed, only claimed, missing, not-applicable, or unrecoverable. Default shows the current run, `--run <id>` shows one run's rows plus its timeline, `--all` shows the conformance matrix over every run on disk. Read-only, terminal-only, jq the single dependency. Reads the lifecycle ledger and nothing else; the separate `.claude/tasklist.md` progress contract has no reader command any more (`/tasklist` has been retired, and the contract file itself is unchanged).
---

# /plc-status — did this run actually follow the process?

Renders `<repo>/.claude/.gate-runs/ledger/<run_id>.jsonl` against the stage registry in
`.claude/stage-registry.json`. It **never writes the ledger**.

Run and render its stdout **verbatim** as your reply:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/plc-status.sh"
```

(In the installed plugin this path is under the skill dir; in a checkout of this repository it is
`scripts/plc-status.sh`.)

## Modes

| invocation | what it shows |
|---|---|
| `plc-status.sh` | the current run (`PLC_RUN_ID`, else the newest ledger by mtime), one row per registry stage |
| `plc-status.sh --run <id>` | that run's rows, then its timeline with derived durations and artifact paths |
| `plc-status.sh --all` | one line per run: the five state counts and a total |

## Reading the output

Five states, and none of them collapses into "done":

| glyph | state | means |
|---|---|---|
| `+` | observed | a deterministic writer saw it, or the artifact is on disk |
| `?` | claimed | records exist, but nothing observed anything. **Not the same as done.** |
| `-` | missing | the stage is in the registry and nothing mentions it. **`missing` means NOT SEEN, not necessarily SKIPPED** — the row carries the condition the registry states, and nothing yet evaluates those conditions |
| `~` | not-applicable (unverified) | a record says it does not apply, and nothing yet authorizes that |
| `.` | unknown (retro) | a pre-ledger run, for a stage whose evidence cannot exist retroactively |

`total=` on every `--all` line is the number of stages in the registry, for every run, always. A
run whose total differs is a defect in the reader, not a property of that run.

**`not-applicable (unverified)` says "unverified" for a reason.** Until the ledger models
owner/scope/expiry, any writer can emit a suppression, so the reader marks every one of them as
unauthorized. A suppression that looked exactly like an authorized one is the failure this
command exists to stop.

**`unknown (retro)` is not a criticism and not a pass**, and it comes in two kinds that the row
tells apart. Most of them mean the evidence could not have survived — there is no artifact a later
reader could find, and there is nothing to do. Two of them (`changelog`, `cross_family_review`) say
**NOT IMPLEMENTED**: recovery is possible in principle and this scanner declines it, because it
would mean matching content rather than a filename. **A person can still check those by hand**, and
the row says so rather than leaving both looking unanswerable.

**`--index-dir` is refused, not accepted.** `--all` reads the per-repo ledger directory; the global
discovery index has its own reader (`ledger-index.sh list`). A flag that was parsed and ignored
would answer a question you did not ask.

**With no run declared, the tool says so on stdout.** It picks the newest ledger by mtime and
prints a note saying that is what it did — because stdout is what you are shown, and "newest by
mtime" looked exactly like "the run you are in".

## What it does not do

- It does not judge. There is no score, no percentage, and no pass/fail line — the states are the
  output.
- It does not write, ever. The ledger's writers are the close gate and the cross-family review
  runner; this reads what they left.
- With `jq` absent it **exits non-zero with a named error and prints no matrix at all**. A wrong
  conformance matrix is worse than no matrix.
