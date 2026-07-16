# Milestone-Done Gate

A milestone is "done" only when all of the following are true. Anything else is "code-complete, not done."

## Hard gates

- [ ] All planned tasks closed (each with a journal entry).
- [ ] All Important review findings either fixed or written to backlog with Trigger + Exit criteria.
- [ ] **S1-tier findings:** zero open (S2 / S3 OK with follow-up issues — see `findings-tier.md`).
- [ ] Automated test suite green (unit + integration + relevant E2E).
- [ ] Coverage at or above the project floor.
- [ ] Linter / formatter / type checker clean across changed files.
- [ ] Generated artifacts (schema, types, migrations) regenerated and committed.
- [ ] Pre-commit run on all changed files locally before final push (see `ci-cd-gates.md` Layer 1).
- [ ] **CI pipeline complete** — format / lint / type / tests / coverage floor / schema drift all green (see `ci-cd-gates.md` Layer 2).
- [ ] **Branch protection enforced** on `main` (no direct push, no force push, CI required — see `ci-cd-gates.md` Layer 3).
- [ ] **PR description opens with a plain-language TL;DR** (4-6 sentences, zero jargon, as 4 bullet points: Problem / What we did / Why we did it / Result + honest boundary), then folds in the daily-use summary (PR body §1, built from the journal FACT entry) + the Track A/B smoke summary + the findings (journal §7 findings/gotchas) — template shape in `references/handoff-template.md` §"PR description appendix".
- [ ] PR opened, CI green, merged to main.
- [ ] If the milestone introduced user-visible surface: **dual-track smoke** done — Track A manual checklist run end-to-end (real browser / device) + Track B Playwright (or equivalent) green. See `smoke-tracks.md`.

## Documentation gates

- [ ] `RESUME.md` updated with the milestone's progress section + commit SHAs.
- [ ] **Archival drain run** (generalizes the status-file ring — see `references/retention.md` §"The drain algorithm"): (a) journal fragments compiled newest-first into `docs/archive/journal/YYYY-MM.md` and deleted; (b) every known append-only monolith (incl. qa-log — qa-log now writes to `docs/qa-log.d/` fragments, compiled into the hot monolith `docs/brainstorming-qa-log.md` at milestone close via `retention-drain.sh drain qa-log`, before this step's eviction runs against it) keeps active + 2 most recent closed entries, older entries moved **verbatim** to `docs/archive/<name>-archive.md` with pointer stub + TOC entry behind; (c) status doc ring rotated as before (`references/roadmap.md` §"Close protocol — the status-file ring"); (d) any archive over 4× its source cap rolled into `docs/archive/<name>/YYYY-MM.md` segments + index — invoke `retention-drain.sh drain <doc> <that-doc's-KB-cap>` once per doc so the roll-over threshold matches the caps table (omitting the cap defaults to RESUME's 25K for every doc). Decision-bearing content is never deleted; mechanical artifacts (drained fragments, scratch, regenerable HTML) are deleted — git is their cold storage. Legacy pre-convention tails move whole, script-chunked, never LLM-rewritten. Deliberately not machine-gated.
- [ ] **Distill proposal surfaced** (skip silently when `retention.distill: off` — see `references/retention.md` §"Distill protocol"): promotions (locked decisions → CONTEXT.md glossary / ADR offer / principle line) + demotions (superseded hot content → archive), each citing its source archive anchor; human approves per item — nothing writes without approval; supersede chain maintained (`supersedes:` / `superseded-by:`); declining all is legitimate — one journal-fragment line + declined anchors recorded in `.claude/retention-state.json` (never re-proposed).
  - Also run `/cognition-distill` to regenerate `docs/cognition.md` from the cold intent-log — skip silently when `retention.distill: off`, and never let it block close (runs outside the jq gate). See `references/cognition.md` §"Distill (regenerate)".
  - **Cognition measurement** (same skip/non-blocking posture — skip silently when `retention.distill: off`, runs outside the jq gate, failure never blocks close): (1) reflect — did we re-explain anything the cognition layer should have held during this milestone? If yes, capture it now with `/capture --source reexplain` before recording, so this milestone's row counts it; (2) record the milestone's row: `python3 scripts/cognition_measure.py record --milestone <slug> --root "$(git rev-parse --show-toplevel)" --branch "$(git rev-parse --abbrev-ref HEAD)" [--turns N] [--tokens-est M] --cognition-loaded <true|false>`, using honest estimates for `--turns`/`--tokens-est` (omit rather than guess) and `--cognition-loaded true` only if the hot doc was actually pulled into context this milestone. See `references/cognition.md` §"Measurement" for the metric definitions and decision gate.
- [ ] The journal (fragments in `docs/journal.d/` or the monolith fallback) has an entry for every task.
- [ ] Backlog files updated for any deferred items.
- [ ] Project-wide Q&A log appended with milestone completion record — written directly to the compiled hot monolith `docs/brainstorming-qa-log.md`, not as a new `docs/qa-log.d/` fragment: the archival drain in the line above has already compiled and emptied the fragment dir into that monolith by this point in the close sequence, and milestone close is a single-writer post-merge event (`references/retention.md` §"Post-merge single-writer boundary"), so appending straight to the monolith here doesn't reopen the parallel-branch collision the fragment convention exists to avoid.
- [ ] ADRs created for any architectural decisions made during the milestone (per `adr.md` 3-criteria gate; skip if no decision qualified).
- [ ] CONTEXT.md / CONTEXT-MAP.md reflects every new domain term resolved during the milestone (per `context-md.md`). No silent drift between code names ↔ glossary.
- [ ] If new dependencies were adopted: README installation / setup instructions updated.
- [ ] All locked design decisions in the spec carry an evidence-strength tag (🟢 / 🟡 / 🔴) — 🔴 entries explicitly flagged for higher-priority review.

## Validation gates

- [ ] No journal entry has an empty "Plan deviations" body without explicit "none" (use the schema in `journal-schema.md`).
- [ ] No "Important" or "Critical" review findings are open without resolution.
- [ ] No Critical finding was downgraded to Important without explicit justification in the journal.
- [ ] The smoke checklist (if applicable) covers the milestone's headline user flows, not just unit-test surfaces.
- [ ] **If this is the project's terminal milestone** (or the user signals the project is done): offer non-technical deploy help per `references/deploy.md` — "want help putting this online?" + plain-English options + prerequisite-gated run. Project finish only; skipped under `audience: technical`. (Non-blocking — an offer, not a gate.)

## When to roll back

If a milestone fails the gate, the milestone is not done. Don't ship. Options:

1. Add a closing task that addresses the failing gate.
2. Defer the gap to backlog (only for non-blocking items).
3. Roll back the merge if the gap is a regression.

The gate is the line. Crossing it without fixing is a process violation.
