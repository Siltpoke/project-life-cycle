---
description: Write a schema-enforced, MOMENT-tense mid-session continuity snapshot to RESUME.md (+ a conditional journal FACT) by following references/handoff-snapshot.md. Captures the invisible state git can't recover — current task+phase, next concrete action, staleness anchor, and (when non-empty) decisions / what-NOT-to-retry / blockers / gotchas — so the next session resumes with zero re-derivation. Refuses to write on a missing core field; never fabricates rationale.
---

# /handoff — mid-session continuity snapshot, PLC-native

Wraps PLC's own continuity discipline (`skills/project-lifecycle/references/handoff-snapshot.md`) as a
standalone button — the PLC-native replacement for reaching to an external end-of-session tool.
Symmetric with `/research` and `/review`: it adds NO new snapshot logic and
never forks the schema. The engine already exists in PLC — `RESUME.md` (the moment doc the
SessionStart:resume hook reads) + `references/journal-schema.md` (the durable FACT schema); this command
just wraps them into one shot.

**Guts, not new capability:** the continuity artifacts already exist in PLC. This command assembles the
session's invisible state, self-validates it, writes the snapshot, and reports honestly what was
committed vs written-local.

## Interface

```
/handoff                         # write the mid-session snapshot to RESUME.md (+ conditional journal FACT)
```

- **No flags, no arguments (v1)** — YAGNI. Auto-firing (on context-pressure / phase-boundary) and a
  `--commit` / `--no-commit` override are explicitly out of scope; invoke `/handoff` manually when
  context is filling, before a `/clear`, or when pausing mid-task.

## Flow (delegates to the brief — do not re-implement here)

1. **Assemble.** Gather the session's invisible state into the 8-field schema — core (task+phase /
   next-action / staleness-anchor) + progressive (state-so-far / decisions / what-NOT-to-retry /
   blockers / gotchas). Actively scan for the what-NOT-to-retry field (reverted edits, abandoned
   approaches), not just forward progress. See `handoff-snapshot.md` §"The snapshot schema".
2. **Self-validate.** Run the four generation-time checks — core-check (refuse if any core field is
   unfillable), fabrication-guard (mark-absent, never invent), progressive-prune (drop empties, no
   "None"), staleness-stamp (`git rev-parse HEAD` + branch + timestamp; `no-git` fallback). See
   `handoff-snapshot.md` §"Generation-time self-validation".
3. **Write RESUME.md.** Overwrite (not append) the root `RESUME.md` with the MOMENT-tense snapshot.
   See `handoff-snapshot.md` §"The snapshot schema" (rendered shape).
4. **Conditional journal FACT.** Append a FACT to `docs/journal.d/<date>-<branch-slug>.md` ONLY if the
   session produced a non-derivable decision/gotcha; else skip silently. See `handoff-snapshot.md`
   §"The conditional journal FACT".
5. **Commit or report local.** Commit RESUME + FACT where tracked; where gitignored, write local files
   and report the local-only reality — never a phantom "committed" claim. See `handoff-snapshot.md`
   §"Commit behavior".

## Hard rules (inherited from the brief)

- **Refuse on missing core.** No snapshot is written if any of the 3 core fields cannot be truthfully
  filled — surface which one is unresolvable instead.
- **Mark absent, never fabricate.** A field with no session-grounded content is marked absent ("no
  explicit decision recorded"), not filled with invented rationale. Fabrication is worse than empty.
- **MOMENT-tense.** Record the moment, never the state — a state-tense snapshot rots into a lie.
- **No phantom commit.** If the writes are gitignored/local, say so; do not claim a commit that did not
  happen.

## Not this command's job

- **NOT the phase-delivery handoff** — this is continuity (`RESUME.md` + conditional FACT), not the retired standalone phase-delivery handoff doc / PR-body appendix (that shape lives in `references/handoff-template.md`). Same word, different artifact.
- **Modifying the SessionStart:resume hook** — `/handoff` writes what the hook already reads.
- **Forking the FACT schema** — the durable half reuses `references/journal-schema.md`; that file wins.
- **Enforcing via close-gate** — the RESUME snapshot is validated at generation, not gated at push
  (the journal FACT half keeps its existing `phase-done` grep).
