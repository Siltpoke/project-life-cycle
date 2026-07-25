---
description: Reconcile conversation-made roadmap/status decisions (and merged PRs since the last checkpoint) against docs/ROADMAP.md + the project's read-first status doc (RESUME.md by default; STATUS.md where present). Proposes staged, individually-approvable edits + a drift-latency report. Human-invoked; never auto-commits.
---

# /reconcile — chat-decision-drift sweep

The session-close net for the chat-drift arm (full mechanics: `skills/project-lifecycle/references/reconcile.md`). Catches roadmap/status decisions that were made in conversation (or shipped in PRs) but never landed in the docs, and proposes the edits to land them — **staged + you approve each; this command NEVER auto-commits to ROADMAP or the status doc.**

## Gather (read-only)

1. **git input (mechanical).** Read the status doc's `Last reviewed:` anchor date — a field `/reconcile` itself introduces (no PLC status-doc convention pre-defines it; if this is the first run, or the field is absent, fall back to the last `/reconcile` marker in `docs/qa-log.d/reconcile.log`). List merged PRs since it — uncapped, UTC-safe:

   ```bash
   gh pr list --state merged --limit 500 --json number,title,mergedAt,labels \
     --search "merged:>=<ANCHOR-DATE>"
   ```

   Treat `mergedAt` as a UTC instant; do not compare it to a bare local date-string (it false-fires across the midnight boundary). This LISTS merges only — it does NOT presence-check `#N` against the status doc: a presence-check on `#N` is a proven false-negative (drifted entries never cite their PRs), so the match is **semantic**, below.

2. **conversation input (semantic).** From this session's context, collect the structural roadmap/status decisions + Decisions-log-worthy calls made (add/drop/reorder a station · done↔doing · vision/current change · new backlog item · re-estimate weight/eta · a strategic decision) — **structural + Decisions-log scope ONLY, not every chat commitment.** This is your judgment, not a grep.

## Match + propose

For each candidate (merged PR outcome OR session decision):
- Semantically match it against the live `docs/ROADMAP.md` + the project's read-first status doc (RESUME.md by default; STATUS.md where present). When matching a PR `#N` mentioned in prose, repo-qualify it (this repo's `#N` ≠ another repo's `#N`).
- If the docs already reflect it → note "already correct", propose nothing.
- If not → propose ONE staged edit, shown as a diff, of the smallest faithful shape. The edit's SHAPE is layout-dependent — use the glyphs/sections THIS project's ROADMAP actually defines, never a fixed set:
  - ROADMAP, milestone-table layout (PLC's own `docs/ROADMAP.md`): move a station done↔current using the legend in `references/roadmap.md` §"Status legend" (`✅`↔`▶`, or `☐`/`⏸`/`✗` as applicable); edit the Milestones table row; log a scope change under the dated "Plan changes" section; edit the head vision/current-state bold line (whatever language the doc uses).
  - ROADMAP, sectioned/fisheye layout (the shape `/catchup`'s parser also supports): move a station between the `## ✅` (done) and `## 🔄` (doing) sections; add/reorder a `## 🛣` (mainline/future) row; add a `## 🗂` (backlog) row.
  - Status doc: update whatever field tracks the active track (e.g. STATUS's `🎯 Now` section — on RESUME.md map this to its own current-task field); close out a finished track per the status-file ring protocol (`references/roadmap.md` §"Close protocol"), whatever that status doc uses for it; append a Decisions-log entry if the doc keeps one; move a shipped item out of its "up next" list (e.g. STATUS's Locked-next — on RESUME.md, its own next-action field).
- **Every edit preserves structure**: whichever ROADMAP layout this project uses — milestone-table columns + status-legend glyphs, or emoji section headers + 4-column mainline/backlog tables — stays intact (the `/catchup` fisheye parser keys off it). Removals are **archive-never-delete** (status-file ring / `docs/archive`, per `references/roadmap.md` + `references/retention.md`), never a raw delete.

Present the batch. The user approves/rejects EACH edit. Apply only the approved ones.

## Apply + report

- Apply approved edits, then commit **doc-only** (`git add` the touched docs + any archive move; commit atomically; re-read the moved block to confirm it is byte-identical after the move (a file-syncing daemon can silently duplicate or re-touch files mid-move).
- If `HEAD` is `main`: commit locally and STOP — do not push (AI never pushes main); tell the user to push, or offer to move the edits onto a branch. **Never run `/reconcile`'s writes from an automated hook — human-invoked only.**
- Append one line to `docs/qa-log.d/reconcile.log`: `<date> · reconciled N edits (git-drift: G, chat-drift: C) · <anchor→now>`.
- **Advance the anchor** so the next run doesn't re-list already-reconciled merges: propose bumping the status doc's `Last reviewed:` line to today (a staged edit like any other — the user approves it; the field itself is a `/reconcile`-introduced convention, not a pre-existing PLC status-doc field — see Gather step 1). Left un-bumped, every future run re-lists all merges since the last manual hygiene pass (the semantic match still dedupes them as "already correct", but the noise grows).
- **Report (never silent):** print what changed, what was already correct, and the **drift-latency count** = how many chat-drift edits you had to propose that the in-the-moment rule should have caught at the source. A non-zero chat-drift count is the signal that the in-the-moment discipline is slipping.

## Degrade

If neither `docs/ROADMAP.md` nor the project's read-first status doc (RESUME.md/STATUS.md) exists, report "no ROADMAP/status doc to reconcile" and stop. If only one exists, reconcile against that one.

Read-only until the user approves an edit. Do NOT start unrelated work.
