# Parallel Work — WIP=1, the sidecar exception, and the single-writer rule

How much work can run at once in a project using this skill, and who is allowed to write what. The rules below are implicit in most single-session work and only bite once several sessions share a repo.

## WIP=1 — one active code track per project

**One code track active at a time, per project.** A "code track" is anything that runs the per-task cadence (see `cadence.md` — implementer, then the verification tail, then fixup + journal) and ends in commits.

Why: every code track serializes on the same human — story/spec sign-off, close approval, smoke runs. Parallel code tracks don't speed delivery; they multiply gate load on the one serial resource (the human) and add merge risk between tracks. The bottleneck is the gate chain, not the typing speed.

Scope: WIP=1 is per project (repo/worktree). Working two *different* projects in parallel is outside this rule.

## The sidecar exception

**Doc-only research/investigation may run parallel to the active code track without violating WIP=1.** A sidecar is a session/agent that satisfies ALL three constraints:

1. **No gate chain** — no cadence, no close gate, no Task Close Report.
2. **Zero code changes** — nothing in `src/`, tests, config, or migrations.
3. **Writes only research docs** (e.g. `docs/research/`) — never the status/roadmap file, never specs/plans the active track owns.

Examples: deep-research on a future milestone's options; a codebase map for an upcoming phase; surveying an upstream library's changelog. The sidecar's output is a doc; that doc enters the project through the normal track later.

A sidecar that wants to edit code or the status file is not a sidecar — it is a second code track. Stop it, or close the active track first.

## Single-writer rule

**When multiple sessions share a worktree, exactly one session holds the pen for the status/roadmap file** (`STATUS.md` / `ROADMAP.md` / `RESUME.md` — whatever the project's "read first every session" file is).

- Sidecars never write it.
- A sidecar's findings enter the status file **through the pen-holding session** — the sidecar hands over a doc path or a summary; the pen-holder integrates it.
- Handover of the pen is explicit ("you hold STATUS.md now"), never assumed.

Why: two sessions editing the same status file collide. Collisions are usually loud and recoverable (stale-write refusal in the editor tooling), but recovery burns time, and the partial-write window still exists. One pen, zero ambiguity.

## Append-doc fragments are conflict-free — WIP=1 still stays

The single-writer rule above is about the status/roadmap file specifically. A separate layer — journal, qa-log, and CHANGELOG entries — used to share that same collision risk when every branch appended to one monolith tail. That layer is now fragment-based: each branch appends only to its own `docs/journal.d/<date>-<branch-slug>.md` / `docs/qa-log.d/<date>-<branch-slug>.md` / `changelog.d/<date>-<branch-slug>.md` file (see `references/retention.md` §"Fragment convention"). Two branches never touch the same fragment file, so this layer no longer needs a single-writer rule to stay conflict-free.

**This does NOT relax WIP=1.** WIP=1's rationale was never merge mechanics — it is human gate-chain bandwidth: every code track still serializes on the same person for story/spec sign-off, close approval, and smoke runs (see "WIP=1" above). Fragments being merge-safe removes one *source* of conflict; it does nothing to the human bottleneck that WIP=1 actually guards. Relaxing WIP=1 on the strength of this fix would be a different, unevaluated claim — out of scope here, and it would need its own evidence (a multi-track trial measuring gate-chain load, not just merge cleanliness) before being considered.

**The compile step is still a single-writer moment — and it runs post-merge.** Fragments stay conflict-free only as long as nothing compiles them into the shared file (hot monolith, archive, or `CHANGELOG.md`) before merge. Compile/drain runs at milestone close on an already-merged branch, or as part of `/release` — by construction the sole HEAD doing the write. Running compile pre-merge on a feature branch is banned: it relocates the exact conflict the fragment layout exists to eliminate onto the compiled file instead (see `references/retention.md` §"Post-merge single-writer boundary").

## Quick table

| Want to do, while a code track is active | Allowed? |
|---|---|
| Second code track (cadence + commits) | ✗ — WIP=1; finish or pause the active track first |
| Doc-only research writing to `docs/research/` | ✓ — sidecar |
| Sidecar updates STATUS/ROADMAP "just to note a finding" | ✗ — single-writer; hand the finding to the pen-holder |
| Sidecar fixes a "tiny" bug it noticed | ✗ — that's code; log it as a finding for the active track instead |
| Two sessions, both need the status file | ✗ — one holds the pen; the other routes writes through it |
| Two branches each appending their own journal/qa-log/CHANGELOG fragment | ✓ — conflict-free (per-branch fragment files, no shared tail); WIP=1 still applies to the code track itself |

## Anti-patterns — STOP

- **"It's only a one-line code fix" from a sidecar** → still a second code track; the line bypasses every gate. Route it to the active track or queue it.
- **Sidecar appends to the status file because "the pen-holder is busy"** → exactly the collision window the rule closes. Wait, or hand over the pen explicitly.
- **Implicit pen handover** (each session assumes the other holds it — or both assume they do) → state it in chat; ambiguity is how double-writes happen.
- **Promoting a sidecar to a code track mid-flight without closing the active track** → now two gate chains compete for the same human; WIP=1 broke silently.
