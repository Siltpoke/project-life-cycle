---
description: Capture a stated project intent (the "why") into the cold cognition log. Elicits at most two questions, then appends a validated entry to docs/cognition-log.d/<date>-<branch>.jsonl. Surfaces any prior intent on the same subject for supersede confirmation.
---

# /capture — Pin an intent

Use when the user expresses a *reason, quality bar, or keep/drop justification*
(rationale signals: because / so that / instead of / isn't good enough / keep X because).
Do NOT use for bare actions (fix, rename, clean up) — that is noise.

## Flow
1. If intent/subject/criterion aren't already clear from what the user just said,
   ask AT MOST two: "What are you really trying to achieve?" and
   "What would 'good' look like?" Never more. Never a form.
   `criterion` is always required (it is the success oracle). For a decision/quality
   intent it is the good-enough bar; for an **open question** it is the *resolution
   bar* — what would settle it (e.g. "decide before Phase 2 whether X"). An open
   question with no resolvable bar is not yet capture-worthy.
2. Determine the current branch: `git rev-parse --abbrev-ref HEAD`.
3. Call the helper:
   `python3 scripts/cognition_log.py append --intent "<why>" --subject "<what>"
    --criterion "<good-enough bar, or an open question's resolution bar>" [--rejected "<alt+why>"] [--status tentative|firm]
    [--salience 1-5] [--supersedes "<prior-id>"] --quote "<verbatim user words>"
    --branch "<branch>" --author "<name>" --root "$(git rev-parse --show-toplevel)"`

   Pass user-supplied values (intent/subject/criterion/quote/etc.) literally as argv —
   the script uses argparse, not a shell, so do not wrap the call in a way that lets
   quotes, backticks, or `$()` in the user's own words get re-evaluated by a shell.
4. If stderr prints `related prior intent […]`, show it to the user and ask whether
   this supersedes it. If yes, re-run passing `--supersedes <prior-id>` and
   `--status firm`; Phase-1 leaves the old entry in place (additive).
5. Confirm back: "Captured [<id>] <subject> — I'll recall this when it's relevant."
   (Closing the Grudin loop: the recorder must see the payoff.)

Default `source` is `capture`. Pass `--source reexplain` instead when this capture is a
*re-explanation* — the user re-stating something the cognition layer should already have
held — rather than a fresh intent; the measurement instrument counts these entries toward
`reexplain_count` (see `references/cognition.md` §"Measurement").

See `skills/project-lifecycle/references/cognition.md` for the schema, signals, and the
ADR-vs-intent-vs-noise line.
