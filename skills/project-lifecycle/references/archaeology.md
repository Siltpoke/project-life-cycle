# Archaeology — brownfield adoption pass

One-time, **read-only** pass offered when the skill is adopted on an existing codebase (brownfield). It derives the baseline context artifacts a greenfield project would have accumulated progressively — ROADMAP, glossary, backfilled ADRs, journal start line, RESUME, plus an adoption-snapshot review index — from repo evidence, every one clearly marked as an **AI-inferred draft** the human must review. The artifacts are **seeds of living docs**: after adoption they are maintained by the normal milestone flow (roadmap updates at milestone boundaries, glossary growth per phase, ADRs at decision time). They are never regenerated wholesale — re-running the pass is an idempotent merge, not a refresh.

## Detection contract

Anchor all checks at `git rev-parse --show-toplevel`. The **adoption entry** fires only when BOTH conditions hold:

1. **Both plc anchors absent** — no RESUME file AND no iteration journal. Each anchor counts as present at **either** conventional location (`RESUME.md` at repo root or `docs/RESUME.md`; `docs/iteration-journal.md` or root `iteration-journal.md`) — a repo keeping `docs/RESUME.md` must NOT fire the adoption entry. One anchor present → existing-project branch wins (current behavior preserved).
2. **Substantial existing code** — a recognized manifest is present, OR ≥1 recognized source file exists outside the whitelist.

Both checks evaluate **tracked files only** (`git ls-files`), never the raw working tree — vendored/installed directories (`node_modules/`, `vendor/`, build output) are typically untracked and must not trigger detection. Manifest names match at the **repo root**; `*.csproj` / `*.sln` / `build.gradle*` globs and the source-extension check match tracked paths at **any depth**. Untracked-only repo (no commits yet) → treat as new-project.

**Recognized manifests:**

`package.json` · `Cargo.toml` · `pyproject.toml` · `go.mod` · `pom.xml` · `build.gradle*` · `Gemfile` · `composer.json` · `mix.exs` · `*.csproj` · `*.sln` · `pubspec.yaml` · `requirements.txt` · `setup.py`

Keep this list in sync with the language-detection table in `references/init-harness.md` — every stack `/init-harness` recognizes must be detectable here, or brownfield repos of that stack misroute to new-project.

**Recognized source files** (the other arm of the OR): any file outside the whitelist with one of these extensions — `.ts` `.tsx` `.js` `.jsx` `.mjs` `.py` `.rs` `.go` `.java` `.kt` `.swift` `.dart` `.c` `.h` `.cpp` `.hpp` `.cs` `.rb` `.php` `.ex` `.exs` `.scala` `.clj` `.sh` `.sql` `.vue` `.svelte`. This fixed list is the deterministic floor; Phase 1 stack detection may add stack-specific extensions on top, never remove from the floor.

**Whitelist** (files/dirs that do NOT count as code; create-next-app lineage, ~24 entries):

| Category | Entries |
|---|---|
| VCS dirs | `.git` · `.hg` |
| Dotfiles | `.gitignore` · `.gitattributes` · `.DS_Store` · `Thumbs.db` |
| CI configs | `.travis.yml` · `.gitlab-ci.yml` |
| IDE dirs | `.idea` · `.vscode` · `.zed` |
| Agent dirs | `.claude` · `.cursor` |
| Docs | `docs/` · `LICENSE` · `README.md` · `mkdocs.yml` |
| Error logs | `npm-debug.log` · `yarn-error.log` · `yarn-debug.log` |
| Tooling residue | `*.iml` · `.yarn` |

**No commit-count or LOC thresholds.** Zero industry precedent (CRA/next/vite/cargo all use file-presence checks), and any numeric threshold misclassifies imported-mature-code repos (1 commit, 50k LOC).

**Ambiguous case:** whitelist-only files + a manifest with zero dependencies → classify as **new-project**. False-negative preferred: a brownfield user can still reach the pass via `/init-harness --archaeology`; a greenfield user nagged with an adoption offer cannot un-see it.

**Monorepo caveat:** when cwd ≠ toplevel AND cwd has its own manifest, do not silently pick either scope — surface the ambiguity and ask which scope the adoption targets.

## Entry surfaces

| Surface | Trigger | Behavior |
|---|---|---|
| Auto-offer | `/init-harness` Phase 1 detection confirms brownfield | offer asked at **CHECKPOINT 1** (alongside stack confirmation), gated by the `archaeology` policy key |
| Skill invocation | plain skill entry routes to the adoption branch | surface the offer, pointing at `/init-harness` |
| Manual | `/init-harness --archaeology` | runs the pass explicitly — works even after a recorded `skipped` |

There is no standalone `/archaeology` command — it would duplicate init-harness's checkpoint + idempotency machinery.

## Artifact set

An accepted pass produces exactly these drafts — no more:

| # | Artifact | Produced by |
|---|---|---|
| 1 | `docs/ROADMAP.md` (inferred) | position/roadmap agent |
| 2 | `CONTEXT.md` glossary draft | glossary agent |
| 3 | ≤5 ADRs (aim 2–3) in `docs/adr/` | ADR archaeology agent |
| 4 | `docs/iteration-journal.md` adoption preamble | controller |
| 5 | `docs/RESUME.md` initial state (the path `/init-harness` generates; root `RESUME.md` if the project already uses that location) | controller |
| 6 | `docs/adoption-snapshot.md` index | controller |

## Pass structure

Runs as **init-harness Phase 1b**, strictly read-only, only after the user accepts the offer at CHECKPOINT 1 (or invokes `/init-harness --archaeology` directly). Fan out three read-only subagents:

| Agent | Evidence | Output draft | Boundary |
|---|---|---|---|
| position/roadmap | tree + README + shallow git signals (tags, recent activity) — NEVER motive/"why" mining from history: that is the documented fabrication zone | inferred `docs/ROADMAP.md` with ALL required sections per `references/roadmap.md`; far-out milestones one line each; first post-adoption task = "review the 🔴 drafts" | explicit read budget |
| glossary | code + docs terminology | `CONTEXT.md` glossary draft, per `references/context-md.md` discipline | explicit read budget |
| ADR archaeology | tree-visible decisions ONLY (lockfile, framework choice, config) | ≤5 ADRs (aim 2–3) in `docs/adr/NNNN-slug.md` — **cap, not quota**: 2 well-evidenced beats 5 padded | explicit read budget |

Every agent carries an explicit read budget. When a cap truncates coverage (or git history is unavailable — shallow clone, no tags), the gap MUST be logged in the snapshot index. No silent truncation.

## Controller-assembled artifacts

The controller (not the subagents) assembles three artifacts from the fan-out results:

- **Journal adoption preamble** — a blockquote placed ABOVE the first entry of `docs/iteration-journal.md`:

  ```markdown
  > Adopted project-lifecycle on YYYY-MM-DD via archaeology pass. History before this line lives in git.
  ```

  It is a preamble, not a task entry — it does not violate `journal-schema.md`.

- **`docs/RESUME.md` initial state** — next action = review the drafts listed in `docs/adoption-snapshot.md`. (Same either-location rule as detection: if the project already keeps a root `RESUME.md`, write there — never create a second competing resume file.)

- **`docs/adoption-snapshot.md`** — the review-gate index (format below).

Drafts then flow into Phase 2's normal generate/merge set; checkpoints 2–4 are unchanged.

## Provenance rules

Every generated file carries this header block:

```markdown
> **AI-inferred draft** — generated YYYY-MM-DD by `/init-harness --archaeology`.
> Evidence strength: <🟢|🟡|🔴 per claim class>. Human review required — see `docs/adoption-snapshot.md`.
```

Backfilled ADRs additionally carry:

- `Status: proposed` — never `accepted`; a human flips it at review
- `Confidence: high|medium|low`
- `## Provenance` section citing the evidence `file:line`
- 🔴 evidence tag

**Motives are never inferred without a citable artifact.** "The tree shows Postgres via the lockfile" is evidence; "they chose Postgres for reliability" is fabrication unless a doc says so.

## Snapshot index format

`docs/adoption-snapshot.md` — generation date in the header, one row per generated draft:

```markdown
# Adoption snapshot — generated YYYY-MM-DD

| Draft | What it is | Review status |
|---|---|---|
| `docs/ROADMAP.md` | inferred whole-plan map | ☐ pending |
| `CONTEXT.md` | glossary draft | ☐ pending |
| `docs/adr/0001-....md` | backfilled ADR | ☐ pending |

## Coverage gaps
- <agent> hit its read budget before covering <area>
- git history unavailable (shallow clone) — position derived from tree+README only
```

- Status values: `☐ pending` / `✅ reviewed YYYY-MM-DD` — per-item reviewed dates, not a single sign-off.
- The index **retires** (archive or delete) when every row is ✅. There is NO recurring re-audit mechanism.

## Policy key

Project `CLAUDE.md`:

```
archaeology: done YYYY-MM-DD | skipped
```

- **Unset** → ask once at the adoption entry.
- **Any recorded value** → never ask again. Prefix-match on `done|skipped` (house skip semantics).
- `skipped` is **declined-but-reachable**: `/init-harness --archaeology` still works after a recorded `skipped` (git `advice.*` pattern).
- **Self-heal:** key absent but `docs/adoption-snapshot.md` exists → write `done <snapshot generation date>` into `CLAUDE.md`; do not re-ask.

## Idempotent re-run

Re-running `--archaeology` follows init-harness's existing merge-vs-create rules: create when absent, merge when generated-and-unedited, and **never overwrite human-edited content without an explicit `OVERWRITE` confirm**. Seed framing answers staleness — living docs stay current through the normal milestone flow, so there is nothing for a re-run to "refresh"; the dated policy key is merely the future hook for a (deferred) staleness reminder.

## Anti-patterns

- **Fabricating decision rationale not visible in the tree** — motives require a citable artifact; git-history "why" mining is the fabrication zone.
- **Filling the ADR quota** — 5 is a hard cap, 2–3 the aim. Padding to 5 turns `docs/adr/` into noise on day one.
- **Backfilling journal history** — git IS the pre-adoption history; the journal starts at the adoption preamble line.
- **Numeric detection thresholds** (commit counts, LOC) — no precedent; misclassifies imported mature code.
- **Putting the offer text in the User Cheatsheet** — a once-per-project event does not belong among per-session habits; the cheatsheet does not grow to hold it.
- **Sentinel-doc-only ask-once** — a snapshot-file-exists check cannot represent `skipped`; declined users get re-prompted forever. The policy key carries both states.
- **Regenerating instead of seed-maintaining** — post-adoption drift is fixed by the milestone flow (roadmap amendments, glossary growth), not by re-running the pass.
