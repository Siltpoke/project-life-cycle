# reconcile — chat-decision-drift sweep (reference)

`/reconcile` (`commands/reconcile.md`) is the **write-twin of `/catchup`**: catchup *reads* ROADMAP/status-doc
drift and surfaces it on the welcome-back card; reconcile *lands* the drifted decisions back into
`docs/ROADMAP.md` + the project's read-first status doc (RESUME.md by default; STATUS.md where present),
staged and human-approved. Human-invoked; never auto-commits the SSOT.

> First designed elsewhere, then adopted into PLC because reconciling
> roadmap/status drift is lifecycle management — PLC's remit, not the other tool's. The original design doc lives in
> that other project as historical provenance.

## Two arms of drift

- **git-drift** — decisions that shipped in merged PRs since the last checkpoint but never landed in the
  docs. Listed mechanically (`gh pr list --state merged --search "merged:>=<anchor>"`, UTC-safe), then
  matched **semantically** against the live docs. A presence-check of `#N` against the status doc is a proven
  false-negative — drifted entries never cite their PRs — so matching is never mechanical.
- **chat-drift** — structural roadmap/status decisions made in conversation (add/drop/reorder a station ·
  done↔doing · vision/current change · new backlog item · re-estimate weight/eta · a strategic call) that
  never got written down. Scope is **structural + Decisions-log ONLY**, not every chat commitment.

## The in-the-moment rule (the primary arm)

reconcile is the **net**, not the first line of defense. The first line is the in-the-moment discipline
(SKILL.md, Documentation & traceability): when a conversation produces a structural roadmap/status change
or a Decisions-log-worthy call, draft the ROADMAP/status-doc edit **inline and get approval before moving on** —
land it at the source. reconcile catches whatever slipped and counts it.

## drift-latency metric

reconcile reports a **drift-latency count** = how many chat-drift edits it had to propose that the
in-the-moment rule should have caught at the source. A non-zero count is the falsification signal that the
in-the-moment discipline is slipping — not a score to accumulate, just a per-run health read.

## Invariants

- **Never auto-commit the SSOT** — the human approves each staged edit individually; apply only approved ones.
- **Human-invoked only** — never run reconcile's writes from an automated hook.
- **Structure-preserving** — whichever ROADMAP layout the project uses stays intact: milestone-table columns
  + status-legend glyphs (PLC's own `docs/ROADMAP.md`), or emoji section headers + 4-column mainline/backlog
  tables (the sectioned/fisheye shape). Either way the `/catchup` fisheye parser keys off it. See
  `references/roadmap.md`.
- **Archive-never-delete** — removals go through the status-file ring / `docs/archive` (`references/roadmap.md`
  §status-file ring + `references/retention.md`), never a raw delete.
- **Anchor advance** — propose bumping the status doc's `Last reviewed:` to today each run, or every future run
  re-lists all merges since the last manual hygiene pass. This field is a `/reconcile`-introduced convention —
  no PLC status-doc convention pre-defines it; when absent, fall back to the last `/reconcile` marker in
  `docs/qa-log.d/reconcile.log`.
- **Degrade** — no ROADMAP and no status doc (RESUME.md/STATUS.md) → report and stop; only one present →
  reconcile that one.
- **Log** — append one line per run to `docs/qa-log.d/reconcile.log`.

## Related

- `references/roadmap.md` — ROADMAP whole-plan map + the status-file ring close protocol.
- `references/retention.md` — archive-never-delete + hot/cold tiers.
- `commands/catchup.md` — the read-twin; its `code-behind` save-state path points here.
