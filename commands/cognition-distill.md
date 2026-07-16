---
description: Regenerate the hot cognition doc (docs/cognition.md) from the cold intent-log — reads the log, not the prior doc (regenerate-from-source). Groups non-superseded intents into four sections, one fact + source pointer per line, then runs the deterministic guards (freshness, cap, dead-path, coverage, snapshot).
---

# /cognition-distill — Rebuild the project cognition

Runs at milestone close (see references/milestone-done.md) or on demand. Runs OUTSIDE the
close-gate; if it fails, the gate is unaffected.

## Procedure
1. Read every non-superseded entry from `docs/cognition-log.d/*.jsonl`
   (helper: `python3 scripts/cognition_log.py` module `load_entries`, or read the JSONL directly).
   Do NOT read the prior `docs/cognition.md` — regenerate from the log, never summarize the summary.
2. Write `docs/cognition.md`. FIRST emit the header disclaimer block verbatim (the doc must
   OPEN with it):
   ```
   # Project Cognition  (auto-regenerated from docs/cognition-log.d — do not hand-edit; 120-line cap)
   > Thin always-loaded core. Full intent + history in the cold log; retrieve for depth.
   ```
   Then the four sections in fixed order (Why/intent, Invariants/what-good, Active focus,
   Open questions). For each entry: one bulleted FACT, a `` `[<id>]` `` source pointer, and a
   `[stated]` tag. NO free causal prose — only `because → [source]`. Prefer the entry's own
   words (extractive) over paraphrase for load-bearing facts. Keep it under ~120 lines; if
   there are more intents than fit, keep highest-salience/newest.
   - **Fact lines** (Why/intent, Invariants/what-good, Active focus) carry, AFTER `[stated]`,
     a per-line freshness marker `(<word>, Nd)`: `<word>` is `firm` when the entry's own
     `status == "firm"` else `fresh` (the word is a **data tag** off the entry's `status`
     field — NOT computed by `age_and_staleness`, which cannot see `status`), and `Nd` is the
     entry's age from `age_and_staleness(ts, now)` in `cognition_render.py`. E.g.
     ``- never blame the user in error copy `[e5f6a7b8]` [stated] (firm, 14d)``.
   - **Open-questions lines** stay marker-free — just `[stated]`, no freshness marker (an
     open question is unsettled, nothing to age).
3. Run the deterministic guards:
   `python3 scripts/cognition_render.py guards --hot docs/cognition.md --root "$(git rev-parse --show-toplevel)"`
4. Read the JSON guard report and append the confidence-surface footer to `docs/cognition.md`
   (coverage + gaps, evicted count, dead-path flags, stale count, snapshot path). For any fact
   line whose entry id is in the report's `stale_ids`, REPLACE its `(fresh/firm, Nd)` marker
   with `⚠ stale? Nd unconfirmed` (the stale override; `age_and_staleness`'s 90-day flag
   drives it).
5. Never hand-edit `docs/cognition.md` outside this flow — it is regenerated wholesale.

See `skills/project-lifecycle/references/cognition.md` §"Distill (regenerate)",
§"Hot cognition doc format", §"Confidence surface".
