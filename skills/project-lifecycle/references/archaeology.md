# Archaeology — brownfield adoption pass

One-time pass offered when the skill is adopted on an existing codebase (brownfield). Its document derivation is **read-only**; its one behavior-baseline step (the seventh artifact, below) additionally **runs the repo's carrier tests** — executing code, but writing only to `.claude/`, never to source. It derives the baseline context artifacts a greenfield project would have accumulated progressively — ROADMAP, glossary, backfilled ADRs, journal start line, RESUME, an adoption-snapshot review index, plus a **behavior baseline** (seeded behavior-lock rows + recorded baselines, so the repo arrives with a runnable regression net — not just documents) — from repo evidence, every one clearly marked as an **AI-inferred draft** the human must review. The artifacts are **seeds of living docs**: after adoption they are maintained by the normal milestone flow (roadmap updates at milestone boundaries, glossary growth per phase, ADRs at decision time). They are never regenerated wholesale — re-running the pass is an idempotent merge, not a refresh.

## Detection contract

**The rule is runnable, and this section describes its SHAPE rather than restating its lists.**

```sh
bash "${CLAUDE_PLUGIN_ROOT}/scripts/archaeology-preflight.sh" detect      # prints `adoption-entry` or `new-project`, and why
```

The **adoption entry** fires only when BOTH conditions hold:

1. **Both plc anchors absent** — no RESUME file AND no iteration journal, each counting as present at **either** conventional location. One anchor present → existing-project branch wins.
2. **Substantial existing code** — a recognized manifest, OR ≥1 recognized source file outside the whitelist.

**The four lists those two conditions read — anchors, manifests, source extensions, whitelist — live in exactly one place**, the `plc-adoption-rule` block in `scripts/archaeology-preflight.sh`, and `scripts/invariants/adoption-rule-single-source.sh` keeps them there. They used to be restated in seven places across five shipped files with nothing checking they agreed; that is what this pointer replaces. To read a list, read the block — do not copy it back here.

Both conditions evaluate **tracked files only** (`git ls-files`), never the raw working tree: vendored and installed directories are typically untracked and must not trigger detection. Plain manifest names match at the **repo root**; the glob manifests and the source-extension check match at **any depth**. Untracked-only repo (no commits yet) → new-project.

Keep the manifest list in step with the language-detection table in `references/init-harness.md` — every stack `/init-harness` recognizes must be detectable here, or brownfield repos of that stack misroute to new-project. (That table answers a different question — which stack, which test command — so it legitimately names the same filenames and is deliberately not covered by the single-source guard.)

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
| 7 | behavior baseline — seeded `.claude/behavior-lock.tsv` PRESERVE rows + recorded `.claude/behavior-baseline.tsv` baselines (see "Behavior baseline" below) | controller (baseline step) |

## Pre-flight — the pass looks at what it is about to read, BEFORE it drafts

**This is the first step of the pass, and it is not optional.** Run it before the fan-out below:

```sh
bash "${CLAUDE_PLUGIN_ROOT}/scripts/archaeology-preflight.sh" check
```

**Branch on the exit code itself. Never on truthiness.** `if preflight; then … else … fi` collapses
"a finding, which a human must weigh" and "the check could not run" into one bucket, and the report
body — the only part that says what was actually found — is then never shown.

| Exit | Meaning | What the pass does |
|---|---|---|
| `0` | no finding | **continue** to the fan-out below |
| `1` | a finding; the report names it | **stop. Produce zero drafts.** Show the report and hand the decision to the human |
| `3` | the check could not run | **stop. Produce zero drafts.** Say it could not run — never "nothing was found" |

**On exit `0` with a withheld draft.** When the report says the inferred `docs/ROADMAP.md` will not
be written, produce the other five artifacts and not that one. The project already has a file holding
that role, and writing a competing draft over it is the failure this pre-flight exists to prevent.

**Why this is a script and not another paragraph.** The pass was entirely prose. On a real
brownfield repository it can draft confident documents from a stale checkout — anchoring on the
branch that happens to be checked out rather than on the project as it is — and read-only agents
can cross the evidence boundary their own prompts state. A fourth prose rule, added to a pass whose
prose rules do not bind, would patch at the layer that failed.

**What this section can and cannot enforce, stated rather than implied.** The pre-flight's own
behaviour is covered by tests and a mutation matrix. Whether an agent reading this section actually
runs it, and actually branches on the code rather than on truthiness, is a prose instruction like
every other one here — and the paragraph above is the measured evidence that prose instructions do
not always bind. The honest position is that this moves the detection from prose to code and leaves
the *invocation* in prose.

## Pass structure

Runs as **init-harness Phase 1b**, strictly read-only, only after the user accepts the offer at CHECKPOINT 1 (or invokes `/init-harness --archaeology` directly), **and only after the pre-flight above exited `0`**. Fan out three read-only subagents:

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

## Behavior baseline

**The seventh artifact.** A greenfield project accumulates a Behavior Lock (the behavior-capture step in `references/careful-paths.md`, backed by `scripts/behavior-lock.sh`) as it changes code; a brownfield repo arrives with none, so the behavior it *already* has is unpinned and the M1 promise — "the requested change works, but something that used to work no longer does gets caught" — does not hold until someone writes rows by hand. This step lays down a runnable regression baseline at intake, so the lock is there from day one.

**No new machinery — documented commands over the two M1 scripts.** PLC does not run the tests; the adopting coding agent does, and records the result. For each critical surface the read-only fan-out surfaced (the behaviors named in the position/ADR drafts — not a row per tested function), the controller:

1. **Decides the carrier** — the existing test that proves the surface — and asks whether it resolves:

   ```sh
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/behavior-lock.sh" --resolve "<carrier>" "<repo-root>"
   ```

2. **Carrier resolves (exit 0)** → run **that carrier** — the specific test, NOT the whole suite — from the repo root, and read its own exit. The baseline is per behavior: one carrier's exit records against one row, because a whole-suite exit shared across rows would red every row for one unrelated failure.

   - **The carrier passes (exit 0)** → append ONE `PRESERVE` row to the adopted repo's `.claude/behavior-lock.tsv` (`BL-<n><TAB>PRESERVE<TAB><behavior><TAB><carrier><TAB><why>`; create the file with its `# id<TAB>class<TAB>behavior<TAB>carrier<TAB>why` header if absent) and record `before` = `0`:

     ```sh
     bash "${CLAUDE_PLUGIN_ROOT}/scripts/behavior-baseline.sh" --record BL-<n> before 0 "<carrier-cmd>" "<env>"
     ```

   - **The carrier fails (non-zero)** → do **NOT** seed a `PRESERVE` row: a behavior that does not currently pass is not a PRESERVE (which is `pass→pass`), and `behavior-baseline.sh --check-transition` would rightly call a PRESERVE whose `before` is non-zero a CONTRADICTION. Record it under `## Coverage gaps` as a *failing* surface the adopter must triage first.

3. **Carrier does NOT resolve (exit 1)** → the surface has no test that proves it. Add a line under the snapshot's `## Coverage gaps` ("`<surface>` has no test — candidate for a characterization test") and **seed NO row**. This is the one correctness property that matters: a PRESERVE row whose carrier does not resolve reds the adopter's very first `close-gate` (M1's `scripts/invariants/behavior-lock-carriers-resolve.sh`), so intake must never seed a dangling row. An untested-but-critical surface is a gap to fill, not a lie to pin.

Seed **lean**: only the critical surfaces the fan-out already judged worth a draft become rows — the registry grows with churn and risk, not with codebase size (`references/careful-paths.md`). **Provenance, stated precisely:** a strict 5-column TSV row cannot carry the markdown provenance header the document drafts use, so the seeded block is prefixed with a `# AI-inferred draft — see docs/adoption-snapshot.md` comment line (the parsers skip `#`), and the human-review pointer lives in the snapshot index, not on the row. **What the step writes vs what it runs:** it writes only to the adopted repo's `.claude/` (the registry + the baseline record), never to source — but it does **run** the carrier tests, which execute code and carry whatever side effects the adopter's own suite has; PLC neither sandboxes nor guards those. This is the one step of the pass that executes code, as against the read-only document derivation above.

**What this step can and cannot enforce, stated rather than implied** (the same honest position as the pre-flight). Once a row exists, the carrier-resolve invariant mechanically reds if its carrier stops resolving. Whether an agent reading this section actually performs the baseline step is a prose instruction like every other one here — this phase adds no gate forcing intake to produce a baseline. It moves the baseline from "never offered" to "a documented, tested command path that M1's guard then protects," and claims no more.

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
| `.claude/behavior-lock.tsv` `BL-1` (+ its `.claude/behavior-baseline.tsv` `before` record) | PRESERVE row seeded from a passing tested surface, with its recorded baseline | ☐ pending |

## Coverage gaps
- <agent> hit its read budget before covering <area>
- git history unavailable (shallow clone) — position derived from tree+README only
- `<surface>` has no test that proves it — candidate for a characterization test (behavior baseline seeded no row for it)
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

Re-running `--archaeology` follows init-harness's existing merge-vs-create rules: create when absent, merge when generated-and-unedited, and **never overwrite human-edited content without an explicit `OVERWRITE` confirm**. Seed framing answers staleness — living docs stay current through the normal milestone flow, so there is nothing for a re-run to "refresh"; the date in the policy key only records when the seed ran.

## Anti-patterns

- **Fabricating decision rationale not visible in the tree** — motives require a citable artifact; git-history "why" mining is the fabrication zone.
- **Filling the ADR quota** — 5 is a hard cap, 2–3 the aim. Padding to 5 turns `docs/adr/` into noise on day one.
- **Backfilling journal history** — git IS the pre-adoption history; the journal starts at the adoption preamble line.
- **Numeric detection thresholds** (commit counts, LOC) — no precedent; misclassifies imported mature code.
- **Putting the offer text in the User Cheatsheet** — a once-per-project event does not belong among per-session habits; the cheatsheet does not grow to hold it.
- **Sentinel-doc-only ask-once** — a snapshot-file-exists check cannot represent `skipped`; declined users get re-prompted forever. The policy key carries both states.
- **Regenerating instead of seed-maintaining** — post-adoption drift is fixed by the milestone flow (roadmap amendments, glossary growth), not by re-running the pass.
