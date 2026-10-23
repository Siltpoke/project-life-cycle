# Close Gate — the deterministic forcing function for "done"

The #1 failure mode of this skill: the AI finishes the *interesting* work (code that runs), feels done, and silently skips the wrap-up steps — journal, tests-3×, handoff, CHANGELOG, PR-comment. Prose "MANDATORY" does not stop this; the model treats prose as soft and the wrap-up steps are last in the list, furthest from attention by the time code works.

The fix is structural, per the skill's own rule (*structure > rules*): a **pure-code gate that exits non-zero when a required artifact is missing.** The model cannot lie past a script that greps for the journal file. This is the harness contract the rest of the skill promises — realized for wrap-up.

Two layers, used together:

1. **Visible state** — the AI materializes the step list at invocation — **the portable contract is `.claude/tasklist.md`, one `- [ ]` line per step**, wrap-up steps included; a host task tool (`TaskCreate` / `update_plan` / equivalent) is the upgrade where present, never the required mechanism — a `PreToolUse` hook cannot enumerate the session's tools and no two CLIs agree on the primitive's name (see SKILL.md "Two ways to satisfy it" + "Definition of Done"). Enumerate each step, never announce a count. Unchecked wrap-up tasks glare at done-time.
2. **Hard gate** — `task-done` / `phase-done` exits 1 on any missing required artifact. The AI MUST run it and paste the output before claiming the task/phase is complete. A pre-push hook makes it automatic (though `--no-verify` still skips it; only a required CI check is un-bypassable).

State #1 makes skips *obvious*; gate #2 makes them *impossible to hide*.

---

## What the gate checks

### `task-done` (one cadence task)
- [ ] the phase **touched the product tree** — the files changed in the branch range `origin/main...HEAD` (HEAD's own commit when there is no `origin/main` yet) include a path under manifest `.product_paths[]`, where an entry names a directory, a single file (`calc.py`), or the repo root (`.`) (e.g. `src/`, or `backend/`+`frontend/` for a split app, `skills/` for a skill repo). Path-based is the honest check: a legit `refactor:`/`docs(skill):` that changes the product passes, a meta-only change fails — the old commit-verb proxy couldn't tell them apart. **Backward-compatible:** when `product_paths` is not declared, this falls back to the legacy check that the same range holds a `feat(...)`/`fix(...)` commit. **Why the range and not HEAD:** the next row requires a separate `docs:` journal commit, which the cadence writes after the code — so a HEAD-only check failed every correctly finished task
- [ ] a `docs:` journal commit exists in the branch range (`origin/main..HEAD`), and the journal entry contains the literal header `## Plan deviations` (present even if body = "none") — the journal checked is the **most-recently-modified** `*.md` fragment under `retention.journal_dir` (default `docs/journal.d/`) when one exists (mtime order, deliberately not filename order: same-day fragments like `…-note10.md` vs `…-note5.md` sort wrong lexicographically, and multiple undrained fragments coexisting within a milestone is the expected state), else the manifest `journal` monolith
- [ ] a **non-empty** test-evidence file, unchanged since it was generated (NOT proof a command ran) — by **content fingerprint** when the manifest declares `test_evidence_inputs` (the evidence file's `# plc-gate-evidence inputs=<digest>` header must match the current-tree digest of the declared inputs), else by the legacy **mtime** check (newer than the feat commit). `-s` not just `-f` — an empty-but-fresh file is a false pass, e.g. an interrupted `tee`. Written by the project's test runner, not by hand; if `test_runs_required` > 1 the file must also contain a `RUNS=N` line with N ≥ required. **Scope note:** after a fixup, task-level evidence may be scoped to the suites the fixup diff touched (per `cadence.md` §"Selective re-verification after fixup") — the scoping is task-level ONLY; `phase-done` below always demands full-suite evidence, and that full run is the safety net for anything task-level scoping skipped
- [ ] `user-story.md` exists for the phase (unless `exempt_user_story` true) — **required at `task-done`, not only at `phase-done`**, because the `ac-oracle-binding` row below reads the story to get its denominator. A task-mode gate with no story has nothing to count against, and passing over that absence would hand a green row to every phase that never wrote one
- [ ] `ac-oracle-binding` — every acceptance criterion has a runnable oracle or a still-true written-down exclusion. At `task-done` the scope is **what this task's commits declare they close** (`Closes: <phase>:AC<n>` trailers in the range `merge-base(<default-branch>, HEAD)..HEAD`), so a task is gated on its own claims and not on criteria it never touched. An empty scope prints a loud informational line, never a silent ✓ — nothing requires a trailer to exist, and a gate that reports a pass over an empty set is reporting a ceremony it only inferred. Base the range on the **default branch**, never `@{u}`: on a phase branch `@{u}` is that branch's own remote, which makes the merge-base equal HEAD and the scope empty
- [ ] no orphan `[DEBUG-` logs remain in the diff
- [ ] **(Sweeper only)** if a commit in range carries an `Archetype: sweep` trailer, the code diff (`docs/**` + `CHANGELOG.md` excluded) is net-negative LOC **or** a `SWEEP-PERF: <evidence>` line is logged — see §"Sweeper diff-direction"
- [ ] if any artifact is absent, a `SKIP:` line with a reason exists in the journal "Plan deviations" section

### `phase-done` (phase close, before PR-merge)
- [ ] `user-story.md` exists for the phase (unless `exempt_user_story` true — refactor/docs/infra)
- [ ] `ac-oracle-binding` — every acceptance criterion has a runnable oracle or a still-true written-down exclusion. At `phase-done` the scope is the **whole criterion set** the story declares, not just what the branch's trailers claim, so a criterion nobody ever pointed at fails the phase by its qualified id. Exemption is never silent: `exempt_user_story: true` prints a SKIPPED row that names the `SKIP:` line the journal still owes. A criterion may be excluded instead of mapped only by a written-down exclusion whose **condition** is machine-checkable; the exclusion self-destructs when that condition stops holding. Removal from the grandfathering baseline happens here, at phase close — never in the pre-push hook, where writing a tracked file leaves the pushed commit without it, the remote stale, and the operator holding a dirty tree
- [ ] spec doc + plan doc exist for the phase
- [ ] the journal was touched in this phase's commit range — a change under manifest `retention.journal_dir` (default `docs/journal.d/`) **or** the manifest `journal` path (monolith fallback for projects not yet on the fragment convention) satisfies this (per-task completeness is a reviewer concern, not deterministically gated)
- [ ] the newest `*.md` fragment under `retention.journal_dir` (or the monolith fallback) contains a complete FACT entry — `Date`, `Decision`, `Why`, **`Backing`**, `Rejected`, `Source`
      - **After the milestone-close drain, look in the archive.** The drain is mandated and it empties the hot directory (`references/retention.md`: *"the hot directory drains to zero"*), so a gate that only reads `retention.journal_dir` demands an artifact another mandated step deletes, and reports "write this phase's FACT entry" about an entry that was written and archived. This is not only a close-time annoyance: the same row runs in **task** mode, which the pre-push hook runs on every push of a `feat/phase-*` branch, so a drained branch stops being pushable. When no fragment for the phase exists, fall back to **`<archive_dir>/journal/*.md` specifically** — not `<archive_dir>/*.md`. The qa-log archive sits in the same directory, is written by the same drain, and carries **the same sentinel format and the same `<date>-phase-<id>-<slug>.md` fragment names**, so the wider glob reads a locked Q&A decision as though it were this phase's journal entry. Match this phase's `<!-- fragment: … -->` sentinel and evaluate **only that fragment's slice**, from its sentinel to the line before the next one. Reading the whole archive would let another phase's complete FACT fields turn these rows green, which is the same failure the cross-phase fallback below is already fenced against. **A sentinel is a position, not a string** — a line counts as a fragment boundary only when it is outside any fenced code block **and** preceded by a blank line or the start of the file, both conditions and not either. Match the fence, do not count it: remember the opening delimiter's character and run length, and close only on the same character, at least as long, with nothing but whitespace after it — a ``` block quoting a `~~~` line is one block, not two, and a parity counter inverts on it for the rest of the file. **Then stop claiming to parse markdown.** The mechanism claims exactly one property and can be checked against it: **every ambiguity costs a FAIL, never a PASS.** Three rules deliver that, and each is chosen for its error direction rather than its correctness. (i) A boundary is accepted only when the fence state is closed at it, so an unterminated fence is *not* discarded — it propagates, and every later boundary in that archive stops being readable. That is a loud false FAIL, and the gate must name the archive rather than telling the operator to write an entry that already exists. Discarding the fence instead is what lets a fence holding *two* quoted sentinels have its second one accepted — a false PASS built out of the repair for a false FAIL. (ii) A slice ends at **any** sentinel-shaped boundary, fenced or not: ending early can only make the gate demand more, while running long is exactly how one phase collects another's FACT fields. (iii) Report the ambiguous case; do not resolve it. Recognise fences at column 1 only. Scanning for the literal marker cannot tell a boundary from a passage that merely *quotes* one, and archives full of tooling notes quote it, so a phase that wrote no journal at all can read as `close-gate PASS`, exit 0, on the strength of a code block in another entry. The same rule governs choosing **which** archive file to read, not just where the slice starts — the two scans have the same blind spot and must be the same scan. Freshness is **not** asserted on the archive path — the archive's mtime belongs to the drain, not to the phase, so claiming mtime evidence there would be a `✓` about something the gate cannot see. The FACT fields must all be present as `- **Field:**` markdown bullets (the canonical form — matches what journals written under this schema use; see `references/journal-schema.md` §"The FACT entry"). Any missing field → hard fail naming exactly which. This is where the retired handoff file's one non-derivable section (§7 findings/gotchas) is *actually* enforced, not merely asserted to be — the journal-touched check above only proves some file changed, not that it carries the FACT content. **`Backing` is required for the same reason the other five are**: without a slot for the evidence, a distilled `Why` degrades into an assertion and drops the statistic its argument rested on.
- [ ] `CHANGELOG.md` `[Unreleased]` was touched in this phase's commit range — a change under manifest `retention.changelog_dir` (default `changelog.d/`) **or** `CHANGELOG.md` itself satisfies this (unless `exempt_changelog`)
- [ ] smoke artifacts exist — Track A checklist + Track B spec — when `user_visible` true
- [ ] acceptance tests exist for the phase (glob `acceptance_glob`), unless `exempt_user_story` true (cadence step 1.5)
- [ ] `docs/ROADMAP.md` touched in the phase's commit range **and the phase identifier actually appears in it**. Both, because "touched" is a proxy: a whitespace edit satisfies it, and an mtime check is weaker still — it can print `✓ ROADMAP.md updated this phase` while `grep -c <phase> docs/ROADMAP.md` returns 0. A row must not report a ceremony it only inferred; where the artifact's content is readable, read it
- [ ] **non-empty test-evidence file exists and is unchanged since it was generated** (`test_evidence`, `-s` — an empty file, e.g. an interrupted `bun test | tee`, is rejected). **What this does NOT prove:** that a test command ever ran. The gate reads a file; a hand-authored file carrying a valid header passes. It catches evidence that has gone *out of date* relative to the declared inputs — nothing more, and the ✓ it prints says only that. Freshness is a **content fingerprint** of `test_evidence_inputs` when declared, else mtime newer than HEAD. If `test_runs_required` > 1 the file must also contain `RUNS=N` with N ≥ required. Skipped only when the manifest has no `test_command`. **This is the check that makes the pre-push hook force tests** — without it, `phase-done` passed with tests never run, and the test pile silently slipped (the original gap). The PR-comment evidence block is the human-facing companion; this file check is the machine gate.
- [ ] every absent-but-claimed-skipped item has a `SKIP: <reason>` line
- [ ] **(armed by the manifest; absent key = the check does not run at all)** `closure-declaration` — the phase declares which backlog ids it closed, and the declaration agrees with the closure ledger in **both** directions. Configure with a `closure_declaration` object naming a `ledger` (an append-only closure log) and a `deriver` (whatever answers "what state is this id in"). **Its absence is the disarm**, deliberately: a check that fires on projects which never configured the feature turns their green runs red for a feature they never opted into.
      - **Three verdicts, and the middle one is the whole point.** No declaration block → **FAIL**. A block saying `closes: none` → **PASS**. A block naming ids → passes only if every id it declares closed derives to `closed` in the ledger. If "absent" also passed it would be indistinguishable from "declared nothing", and *forgetting* is precisely the failure this check exists to catch: a phase that forgot must not look like a phase that decided.
      - **Both directions, scoped to what THIS BRANCH added.** A declared closure with no ledger event fails. A closure line **this branch added** that the declaration names under neither key also fails. The scoping is what lets both hold at once: closures that predate the branch point are silent, so adopting this never becomes a retroactive audit of work already done. Without the second direction the check reproduces the exact defect it was built for — a phase closing three ids and declaring two leaves the third indistinguishable from a legitimate historical backfill.
      - **"Deliberately left open" is a first-class statement.** `left-open: <id> — <reason>` makes no claim about the ledger and requires no event, but the reason is **mandatory**: a stated non-closure with no reason is indistinguishable from having forgotten, which is the thing being fixed.
      - **Nothing in this check ever matches prose.** The declaration is parsed as data and the reason is stored, never branched on. A text matcher reports an entry as done that is deliberately still open, because the reason it stays open is written in words no matcher can read. **The writer has to run at close, when the person knows.**
      - **Phase mode only.** What a phase closes is knowable only when it is closing; its first task cannot know. A per-push variant would demand an answer that does not exist yet.
      - Scripts: `scripts/closure-declaration.sh` (`extract` / `reconcile`) and `scripts/lib/closure-log-added.sh`. **Not embedded in this document, and that is a decision rather than an omission:** the two embedded copies below exist because their scripts are small and their drift is invisible; a third embed adds surface that an invariant must keep byte-identical forever. Copy the files instead.
- [ ] **(warn-only, never fails the gate)** the context-floor hook (`context-floor.sh`) is wired in `~/.claude/settings.json` or the project's `.claude/settings*.json`, **and `jq` was resolvable when the gate ran**. The floor is a machine-local user-settings hook (`references/harness-primitives.md` §9) — a project gate must not fail on a user's global config — but an un-armed floor is exactly how a session runs far past it unnoticed. **Three reported states, never two** (a fourth — wired, `jq` present, but the hook's shared floor library missing or unusable — is not distinguished and reads as wired): not wired → `⚠` pointing at `/init-harness --refresh`; wired → `✓`; wired but inert (`jq` missing, and `context-floor.sh` exits 0 without it) → `⚠`. Wiring is *liveness*, `jq` is *readiness*; a row that reports only the first reads as though it had reported both. The `✓` claims only that `jq` was resolvable **when the gate ran, in the gate's own process** — not that the hook works, will run, or is verified: the client that later spawns the hook may hand it a stripped `PATH` in which the same probe fails. Note that the third state's `⚠` **cannot print for a user in either direction** — a genuinely jq-less machine kills this gate at its first `jq` call before any row is reached, and the stripped-`PATH` client this warning is about leaves the gate itself able to find `jq`, so it prints the `✓`. The branch is a contract for gates that *can* reach it, not a warning you will see; the row's comment in the gate spells this out along with the `PATH` blind spot
- [ ] **(warn-only, never fails the gate)** hot-doc retention caps: each configured hot doc (defaults: RESUME 200L/25K, status doc 300L/30K, `docs/journal.d/` total 100K, qa-log 50K, `changelog.d/` total 50K; overrides via manifest `retention.hot_caps`) is measured `wc -l` + `wc -c`; over either limit → `⚠` row. Same doc over-cap at two consecutive closes (tracked in `.claude/retention-state.json`) → wording escalates to "SECOND consecutive over-cap close". See `references/retention.md` §"Hot-doc caps".
- [ ] **(warn-only, never fails the gate)** coverage discovery: any `docs/**/*.md` over `retention.coverage_floor_kb` (default 50K) that is neither manifest-known nor under `journal_dir`/`archive_dir` → `⚠` row naming the file ("manifest-known" is a v1 approximation: a substring match of the file's basename against the manifest text — slightly looser than "referenced by a manifest key"). See `references/retention.md` §"Coverage discovery".
- [ ] **(warn-only, never fails the gate)** qa-log citation coverage: each `### Q` section in a `retention.qa_log_dir` fragment (default `docs/qa-log.d/`) that carries a `**Locked:**` decision but **no `http(s)` URL** → `⚠` row naming the fragment + Q header. Enforces the brainstorm protocol's "no citation, no send" rule (`references/brainstorm-research-protocol.md`) — the #1 silent degradation is skipping research and opinion-polling. Deliberately **warn-only, not hard-fail**: a compressed established-pattern decision may legitimately cite a prior-phase lock (`M2.3 Q4`) rather than a URL, which a URL-only hard gate would false-block; the row informs the human at PR instead. Scoped to the fragment dir (current-phase, short-lived); the compiled monolith is historical and not re-litigated (v1 limitation — un-adopted projects that write only the monolith get no row).
- [ ] **(warn-only at `task`/`phase`; BLOCKING at `milestone` — see §"Milestone mode")** retention **count** caps: the number of `.md` files under `docs/superpowers/specs/`, `docs/superpowers/plans/`, and `docs/**` (excluding `*/screenshots/*` **and** `retention.archive_dir` — an archived doc must be able to clear the cap that told you to archive it) is compared against manifest `retention.count_caps` (defaults: specs 10, plans 10, docs_total 150 — applied by `cc()`'s default arg even when `count_caps` or the whole `retention` block is absent from the manifest; never silently unlimited). `0` = unlimited, `"none"` = exempt. **Why a count axis exists at all:** the size caps and the 50K coverage floor are blind to many-small-files growth: a directory of hundreds of small drafts can sit below every size threshold and stay invisible to the net in its entirety. See `references/retention.md` §"The count axis".
- [ ] **(non-blocking `⊘` at `task`/`phase`; BLOCKING at `milestone`, unconditionally — see §"Milestone mode")** required-artifact manifest keys `phase_docs_glob`, `plan_glob`, `acceptance_glob`: an absent key prints a visible `⊘ <key> not configured in manifest` row (never a ✓, never silent) but never fails task/phase. At milestone close — `PHASE` arg or not — any of these three still unconfigured is a hard failure — the accumulated, ignored `⊘` finally stops being free. (`handoff_glob` is deliberately not in this set — the handoff file was retired.)

Checks are deliberately **deterministic + greppable** (file exists / header present / commit in range / mtime fresh). The gate does NOT judge quality — that is the validator + code-quality reviewer. The gate only proves the *ceremony actually happened*.

### What `ac-oracle-binding` does NOT prove

Read this before wiring the check, and keep both sentences when you materialize your own gate — they are the bound on what a green row means, and a row whose bound goes missing reads as a stronger claim than the mechanism can make:

> this proves each criterion HAS an oracle. It never proves the oracle is correct,
> and an exclusion self-destructs only when its condition fails, never when its reasoning was wrong.

Concretely: a criterion mapped to a test that asserts nothing passes this check. An exclusion whose stated condition still holds passes it forever, however bad the reasoning behind that condition was. The check moves one failure mode — *a criterion nobody ever pointed at* — and moves no others. It is deliberately not a coverage percentage, a score, or any single number: a ratio invites the reader to treat 15/16 as nearly-done, when the one criterion missing an oracle is the entire finding.

---

## Milestone mode — `close-gate.sh milestone [PHASE]`

The only mode where a retention row **fails the gate**. Rationale — three shapes in which warn-only is worth exactly zero:

1. A CI lint job **exits 1**, parked behind a "make it blocking later" comment. It never blocks anything; the comment is a promise that never comes true.
2. A deferred-work list carries a dated trigger: a module has crossed its own hard line-count cap, and the next edit is to split it first, "no longer optional". The module keeps growing. The trigger fires. Nothing happens.
3. A status doc carries a banner announcing that its own headline count is stale and understated — dozens of lines above the line still printing the stale number. **The document names its own lie and keeps telling it — because nothing fails.**

> **A warn-only gate is not a gentle gate. It is no gate — and it is worse than none, because it manufactures the feeling of safety.**

Blocking daily was rejected for the symmetric reason: a gate that bites every commit is switched off by the person it bites.

Milestone mode intentionally does **not** re-run the full `phase` artifact block (spec/plan docs, CHANGELOG/ROADMAP/journal-touched, test-evidence, hot-caps, coverage, qa-log citations, the FACT-entry field check) — those checks all assume a single phase's `origin/main..HEAD` commit range, which a milestone spanning several phases doesn't have. The FACT check does not need re-running here: under WIP=1 every phase in the milestone already passed its own `phase-done` before merging, and `phase-done` is unconditional on the FACT fields, so a milestone composed entirely of merged phases has already had each one checked. It checks two things only:

1. **Retention count caps** (same `count_row` logic as `phase`, same three rows) — over cap is now a hard `✗`, not a `⚠`.
2. **Required-artifact manifest keys**, checked unconditionally, `PHASE` arg or not: `phase_docs_glob`, `plan_glob`, `acceptance_glob`. At `task`/`phase` close, an absent key prints a visible `⊘ <key> not configured in manifest` row and is deliberately non-blocking — a hard failure there would brick the gate for every manifest predating the key, disabling it project-wide. Milestone is where that stops being free. `PHASE` is optional at `milestone` (unlike `phase` mode, where it's mandatory) because this check tests **manifest wiring** — is the key configured at all — **not per-phase artifact existence**: `[ -n "$(g "$key")" ]` only asks whether the (already-`{PHASE}`-substituted) glob string is non-empty, and substituting an empty `$PHASE` into a configured, non-empty glob pattern does not make that string become empty. There is nothing phase-scoped for a `PHASE` arg to unlock here, so a bare `milestone` close runs this check exactly the same as one with `PHASE` supplied — it must not be skipped just because `PHASE` was omitted (that omission is also what `$(PHASE)` expands to when `make milestone-done` is invoked without `PHASE=X.Y`, so silently skipping here would silently skip the check for the most common invocation of the checked-in `make` target). (`handoff_glob` was dropped from this set: the handoff file was retired, so a required-artifact key naming it can no longer be satisfied by any manifest value; see `references/handoff-template.md`.)

Failure message naming the exact unconfigured keys:

```
✗ milestone cannot close with required-artifact checks never configured in manifest: phase_docs_glob plan_glob acceptance_glob — configure them in .claude/close-gate.json
```

---

## Project manifest — `.claude/close-gate.json`

The gate is stack-agnostic; per-project specifics live in a small manifest the gate reads. A ready-to-edit manifest built from the block below (plus an empty `invariants` list and the `retention.order` / `retention.non_entry_headings` keys) ships at `.claude/close-gate.json.example` — copy it to `.claude/close-gate.json` and replace `test_command`. Neither the example nor the block below carries `validator_input_paths_rationale`: the gate that ships in this repository's own `scripts/close-gate.sh` requires that key — a JSON array whose text states the argument for keeping `test_evidence_inputs` narrow (shape-checked: at least two numbers plus a word beginning "track") — and hard-fails whenever the test-evidence rows run (`task`, `phase`, and a `diff` that touches `product_paths`). The portable gate embedded further down never reads it. The manifest shape:

```json
{
  "phase_docs_glob": "docs/superpowers/specs/*-phase-{PHASE}-*",
  "plan_glob": "docs/superpowers/plans/*-phase-{PHASE}-*",
  "journal": "docs/iteration-journal.md",
  "status_doc": "docs/STATUS.md",
  "smoke_a_glob": "docs/smoke/*-phase-{PHASE}-*checklist*",
  "smoke_b_glob": "tests/e2e/**/*phase-{PHASE}*",
  "acceptance_glob": "tests/acceptance/**/*phase-{PHASE}*",
  "test_evidence": ".claude/.last-test-run",
  "test_command": "{ bash scripts/close-gate.sh evidence-header {SET}; REPLACE_ME e.g. 'bun test' or '.venv/bin/python -m pytest -q'; } | tee {EVIDENCE_FILE}",
  "test_evidence_inputs": ["src/**", "tests/**"],
  "test_runs_required": 1,
  "user_visible": true,
  "exempt_user_story": false,
  "exempt_changelog": false,
  "product_paths": ["src/"],
  "retention": {
    "hot_caps": { "resume": [200, 25], "status": [300, 30], "journal_hot": [0, 100], "qa_log_hot": [0, 50], "changelog_hot": [0, 50] },
    "count_caps": { "specs": 10, "plans": 10, "docs_total": 150 },
    "archive_dir": "docs/archive",
    "coverage_floor_kb": 50,
    "journal_dir": "docs/journal.d",
    "qa_log_dir": "docs/qa-log.d",
    "changelog_dir": "changelog.d"
  },
  "user_story_glob": "docs/superpowers/specs/*-phase-{PHASE}-*user-story*",
  "exempt_user_story": false,
  "ac_evidence": ".claude/ac-evidence.json",
  "ac_baseline": ".claude/ac-baseline.json",
  "ac_heading_set": ["acceptance criteria"]
}
```

The last five keys drive `ac-oracle-binding`, and **they are in this template on purpose**: without
`user_story_glob` the check prints `⊘ … not configured` on every run and the gate still passes, so an
adopter who copied the template unchanged would have the checklist row, the scripts, and no binding —
a shipped ceremony. `exempt_user_story` is written out rather than left absent because an absent key
resolving to *not exempt* by accident is one refactor away from resolving the other way; declare the
answer you mean. `ac_heading_set` lists the headings a user story's acceptance-criteria section may
carry — add your own spelling here rather than
teaching the parser new heuristics. `ac_baseline` may be omitted while you have nothing to
grandfather; the other four should not be.

`retention` cap values are `[lines, KB]`; `0` means that dimension is unlimited. The whole block is optional — the gate falls back to these defaults when it (or any key inside it) is absent. `hot_caps.<doc>: "none"` exempts that doc — the only exemption mechanism. See `references/retention.md` §"Hot-doc caps" / §"Policy keys".

`count_caps` values are **file counts** of `*.md` (never PNGs — `*/screenshots/*` is excluded by construction, since those are load-bearing assets embedded in live PR comments via raw URLs, not documents; `docs_total` additionally excludes `retention.archive_dir` — the gate's own prescribed remedy for an over-cap close is to archive, so the count that gate rechecks must be capable of going back down). `0` = unlimited, `"none"` = exempt. Absent block, or an absent individual key inside it → **specs 10, plans 10, docs_total 150** — the gate's `cc()` helper defaults every key exactly the way `cap_val()` defaults `hot_caps`, so an unconfigured count axis is never silently unlimited.

`status_doc` (optional, default `docs/STATUS.md`) names the read-first status doc measured by the hot-cap row; `RESUME.md` and `docs/brainstorming-qa-log.md` are conventional paths and stay hardcoded in the gate. `retention.qa_log_dir` (default `docs/qa-log.d`) and `retention.changelog_dir` (default `changelog.d`) are manifest-driven, mirroring `journal_dir`.

`product_paths` (optional array, **task mode**) names the code/product tree; a task satisfies check #1 when the branch range (`origin/main...HEAD`, or HEAD's own commit with no `origin/main`) touches a path under it — an entry may name a directory (`src/`, matches only its contents), a single file (`calc.py`), or the repo root (`.`, any change). This asks the honest question — *did the task change the product* — that the legacy `feat|fix` commit-verb check only proxied: a legitimate `refactor:` or `docs(skill):` that changes the product now passes, while a meta-only change fails, which no widened verb list could tell apart. Set it to your product tree — `["src/"]`, `["backend/","frontend/"]`, `["skills/"]` for a skill repo. **Backward-compatible:** an *absent* key falls back to the legacy `feat|fix` check, so a manifest predating this key is unaffected and no adopter's gate flips on upgrade — the path check is opt-in by declaring the key. A malformed value (present but not a non-empty array — an object, string, or empty array) fails closed.

`test_evidence_inputs` (optional array) switches the **test-evidence freshness** check from mtime to a **content fingerprint**. mtime is not evidence that the tests ran against the *current* code — git does not preserve mtime across a checkout, and a fresh clone / CI checkout / synced folder shuffles mtimes, so a mtime-only row false-PASSES by construction there. Declare the inputs whose change means "the tests must be re-run" (globs, e.g. `["src/**","tests/**"]`); the gate then requires the evidence file's first line to be a `# plc-gate-evidence inputs=<digest>` header that matches the current-tree digest of those inputs. **The runner must produce that header** — prepend it with the `evidence-header` subcommand: `{ close-gate.sh evidence-header; <test_command>; } | tee <test_evidence>`. **Two-part opt-in, so no adopter breaks:** an *absent* key keeps the legacy mtime check byte-identical (existing manifests are untouched), and even a declared key does nothing until the runner writes the header — a declared-but-unheaded evidence file **hard-fails** (never silently falls back to mtime) with the exact regenerate command. Inputs that match no tracked file, or a malformed value, fail closed. The digest is over git-**tracked** working-tree content (an uncommitted edit to a tracked input *is* caught; a brand-new *unstaged* file is not — stage before generating evidence), the same git-tracked convention `product_paths` uses. **`/init-harness` generates both for new adopters**: the key is filled from the detected source/test tree, the `test_command` is emitted in the header-prefixed placeholder form above, and `scripts/gen-test-evidence.sh` (§Evidence runner) is scaffolded — so a bootstrapped repo is in fingerprint mode from its first run rather than only if someone knew to turn it on. **Do not hand-write the pipeline** even when retrofitting: the documented `… | tee <file>` form ends in a bare `tee`, which exits 0 even when the step writing the header fails, silently overwriting good evidence with a broken file. Copy the runner instead. An *existing* manifest with no key is still untouched and stays on mtime, so no adopter's gate flips on upgrade.

`validator_input_paths_rationale` (**object**, required whenever `test_evidence_inputs` is a non-empty array; an array of strings is the DEPRECATED shape and still passes behind a warning) is the written argument for that narrowing. Narrowing is safety-REDUCING -- it shrinks what the freshness fingerprint can see -- so the manifest must say why the narrowed set is the right one. The shape:

```json
"validator_input_paths_rationale": {
  "surface_total": 3020,
  "basis": "tracked-files",
  "why": ["the narrowed set is exactly the validator's inputs; nothing else is read"]
}
```

`surface_total` must be a JSON **number** greater than zero (a numeric string is refused). `basis` says what universe that total counts, and must be exactly one of `tracked-files` / `all-files` / `glob-set` / `explicit-path-list`. `why` is a non-empty array of non-empty strings, **free prose in any language and any script -- the gate reads none of it** and checks only that it is there.

**Do not write `surface_kept`.** The gate DERIVES how many files the narrowing matches, from the same pathspec resolution the fingerprint itself uses, and a manifest that declares the member is refused. A number you cannot write is one you cannot fake and cannot leave to rot -- and the rotting is not hypothetical: a manifest was found stating a count far below the truth, with this row green over it the whole time.

**What p30 removed, stated rather than silently dropped.** Until p30 the value was an array of strings and the row asserted a measurement SHAPE inside that prose: at least two ASCII digit groups plus a case-insensitive match on the English root `track`. Both predicates were language-bound, so an argument that was entirely true but spelled its numbers out, or was written in another language, or made the case without that word, was REFUSED by a hard-fail gate. And the anti-gaming strength the rule was assumed to buy was measured and was not there -- `0 0 track` satisfied it. The one property it reliably delivered, that an untouched scaffold placeholder fails, is preserved. **There is no longer any requirement to use Arabic numerals or the English word `tracked` anywhere.**

**SHAPE, not truth.** The gate type-checks `surface_total` and `basis` and audits neither, and the ✓ row says so in those words. It also does not cross-check `basis` against what `test_evidence_inputs` actually is -- an author can declare `explicit-path-list` while narrowing by glob and nothing notices (filed). **Coupled to what it justifies**: with no `test_evidence_inputs`, an empty array, or a malformed value, the row does not fire at all -- there is no narrowing to argue for. A single blank glob (`["  "]`) DOES fire: that is a declared narrowing, merely a broken one. **The escape hatch is real and it is not free** -- deleting `test_evidence_inputs` silences this row and simultaneously drops the freshness check back to the legacy mtime comparison, which git does not preserve across a checkout.

> **Declare inputs that cover what `test_command` actually exercises — the two must be read together, and nothing checks that they agree.** The failure is silent in *both* directions and neither is visible in the gate's output. **Under-declare** and the row greens on evidence older than the code it is trusted to guarantee: a commit touching only an undeclared path recomputes a byte-identical digest, so the ✓ prints while the evidence predates the change. **Over-declare** and the digest breaks on files the command never runs, so the ✓ certifies freshness for things nothing tested — which trains you to clear a red row by re-running the command as a reflex, and a gate cleared by reflex is worse than no gate. This is the "missing dependency" bug class every incremental build system names: Bazel calls the result *"an incorrect incremental build"*, and Gradle states the asymmetry — *"Failing to specify an input that affects the task's outputs can result in incorrect builds, while needlessly specifying inputs that do not affect the task's output can cause cache misses."* Under-declaring costs correctness; over-declaring costs time. When a suite is too slow to put in `test_command`, do **not** declare its inputs here to compensate — run it in CI and leave this row's scope honest.
>
> Two related traps in the runner, neither of which the gate can see:
> - `{ …; } | tee <file>` exits with **`tee`'s** status, so a failing `test_command` still writes a green-looking evidence file. Put the runner in a script with `set -o pipefail`, or check the command's status explicitly.
> - The gate never executes `test_command` — it is interpolated into failure messages so a reader is told how to satisfy the row. Its dependency envelope is the *runner's*, not the gate's, so it may use tools the jq-only gate may not.

When `test_runs_required` > 1, the project's `make test-evidence` (or test runner) **MUST emit a `RUNS=N` line** into the evidence file (e.g. `echo "RUNS=$n" >> .claude/.last-test-run`). The gate reads that line; if absent it treats the run-count as 0 and fails.

`{PHASE}` is substituted from the `PHASE=X.Y` arg. `/init-harness` generates this manifest from the detected stack; hand-edit per phase to flip the `exempt_*` / `user_visible` flags (and the gate FORCES a `SKIP:` reason when an exempt flag suppresses a check).

---

## Portable gate script — `scripts/close-gate.sh`

Drop this in the project; wire `make task-done` / `make phase-done` to call it. Pure bash + `git` + `jq`, no stack assumptions.

```bash
#!/usr/bin/env bash
# Usage: close-gate.sh task              (gate one cadence task)
#        close-gate.sh phase X.Y         (gate a phase close)
#        close-gate.sh evidence-header   (print the evidence file's required first line)
#        close-gate.sh test-command      (print the declared test_command, placeholders unresolved)
set -euo pipefail
MODE="${1:?task|phase|milestone}"; PHASE="${2:-}"
M=".claude/close-gate.json"; [ -f "$M" ] || { echo "✗ missing $M"; exit 1; }
g() { jq -r ".$1 // empty" "$M" | sed "s/{PHASE}/$PHASE/g"; }

# --- test-evidence content fingerprint -------------------------------------------------
# The freshness check below has two modes. The DEFAULT (no `test_evidence_inputs` in the manifest)
# is the legacy mtime check, byte-identical to before — no adopter's gate flips on upgrade. The
# OPT-IN mode (declare `test_evidence_inputs`) fingerprints CONTENT instead: mtime is not evidence
# that the tests ran against the CURRENT tree — git does not preserve mtime across a checkout, and a
# fresh clone / CI checkout / synced folder shuffles mtimes, so a mtime-only row false-PASSES by
# construction on those. A content fingerprint answers the real question: does this evidence file
# describe the current bytes of the inputs the adopter declared as "changing these means re-run".
#
# evidence_digest: a stable fingerprint of the manifest-declared inputs, from WORKING-TREE content
# (so an uncommitted edit is caught). `git hash-object` is content-addressed — same bytes, same
# hash, on any machine — and keeps the envelope inside git (no sha256sum dep). Per-file hashes are
# sorted so ordering never perturbs the digest, then hashed as one blob. The inputs come from the
# manifest (the canonical gate serves ANY tree — unlike a project-local variant of this gate, it cannot hardcode
# a validator's inputs).
# ONE resolution of "which tracked files does the declared narrowing match" (p30:AC3).
#
# It exists because check 9 now REPORTS that count and check 7 fingerprints those same files, and
# two consumers reading the manifest separately is two implementations of the same question — the
# drift p30:AC3 forbids and the story's Contingency pre-declares. Both callers below go through
# here; neither re-reads `test_evidence_inputs`.
#
# Writes the matched paths NUL-separated to stdout, and writes NOTHING for either empty case. The
# two empty cases are NOT the same thing and callers must still tell them apart — use
# `evidence_inputs_declared` for that. This function deliberately does not encode which sentinel
# belongs to which case, because the two gate homes word them differently and folding that in here
# would make one home's wording leak into the other.
#
# NUL-separated because a tracked path may contain a newline; the output is consumed by a pipeline,
# never captured into a variable, since command substitution drops NUL bytes.
evidence_matched_files() {
  _inputs="$(jq -r '.test_evidence_inputs[]?' "$M" 2>/dev/null)"
  [ -n "$_inputs" ] || return 0
  # Disable globbing while splitting the pattern list: a pattern like 'src/**' must reach
  # `git ls-files` as a (recursive) PATHSPEC, not be expanded by the shell against the cwd first.
  # `set -- $LIST` under `set -f` passes them verbatim.
  set -f
  # shellcheck disable=SC2086
  set -- $_inputs
  set +f
  git ls-files -z -- "$@" 2>/dev/null
}
# Whether the manifest declares a narrowing at all. Separate from "did it match anything", because
# an empty pathspec list means "no restriction" (matches the WHOLE tracked tree), not "match
# nothing" — so `evidence-header` on a manifest without test_evidence_inputs would otherwise
# silently hash the entire repo. check_evidence never reaches that path (it gates on a non-empty
# array), but the `evidence-header` subcommand is adopter-reachable directly.
evidence_inputs_declared() { [ -n "$(jq -r '.test_evidence_inputs[]?' "$M" 2>/dev/null)" ]; }
# How many tracked files the declared narrowing matches. This is the number check 9 reports, and it
# is DERIVED rather than declared precisely so it cannot be faked or go stale (p30).
# Counts NUL delimiters rather than lines: a path may contain a newline, and `wc -l` would then
# over-count. Measured on BSD and GNU `tr` alike.
evidence_kept_count() { evidence_matched_files | tr -cd '\000' | LC_ALL=C wc -c | tr -d ' '; }
evidence_digest() {
  evidence_inputs_declared || { printf 'EMPTY-no-test-evidence-inputs-declared\n'; return 0; }
  # Zero matches must NOT fall through to `git hash-object --stdin` on empty input: that returns the
  # FIXED empty-blob SHA e69de29b…, a constant that passes the header regex, so the row would compare
  # constant-to-constant and PASS vacuously — an adopter whose globs match nothing would silently
  # green, the exact silent-degrade this mode removes. Emit a non-hex sentinel; check_evidence rejects
  # it loudly.
  [ "$(evidence_kept_count)" -gt 0 ] || { printf 'EMPTY-no-test-evidence-inputs-matched\n'; return 0; }
  evidence_matched_files \
    | while IFS= read -r -d '' _f; do
        printf '%s %s\n' "$(git hash-object "$_f" 2>/dev/null || echo MISSING)" "$_f"
      done \
    | LC_ALL=C sort \
    | git hash-object --stdin
}
# The header the runner must write as the evidence file's FIRST line. ONE definition, emitted by the
# `evidence-header` subcommand and re-derived by check_evidence — runner and gate call the same
# function, so they can never drift on how the fingerprint is computed.
evidence_header() { printf '# plc-gate-evidence inputs=%s\n' "$(evidence_digest)"; }
# Subcommand: print just the header so the runner can prepend it —
#   { close-gate.sh evidence-header; <test_command>; } | tee <test_evidence>
# Exits before the phase/PHASE-arg requirements. (Unlike a project-local variant, this
# one DOES read the manifest — the declared inputs live there — so it needs `$M`, already resolved.)
if [ "$MODE" = evidence-header ]; then evidence_header; exit 0; fi
# Subcommand: print the DECLARED test_command, raw and with its placeholders UNRESOLVED. This is
# the one place that value is read from the manifest; the evidence runner below resolves the
# placeholders, so runner and gate cannot drift on what the declared command is. Not a gating
# mode — it needs no PHASE, and it prints one manifest key rather than judging a phase.
# `jq empty` is checked first so "the manifest is not valid JSON" and "the key is absent" stop
# being the same message: without it, jq's parse error is swallowed and both causes print the
# absent-key text, sending an adopter to look for a key in a file that never parsed.
if [ "$MODE" = test-command ]; then
  jq empty "$M" >/dev/null 2>&1 || { echo "✗ $M is not valid JSON — cannot read test_command"; exit 1; }
  TC="$(jq -r '.test_command // empty' "$M" 2>/dev/null)"
  [ -n "$TC" ] || { echo "✗ no test_command declared in $M"; exit 1; }
  printf '%s\n' "$TC"
  exit 0
fi

fail=0
ok()  { echo "✓ $1"; }
bad() { echo "✗ $1"; fail=1; }
warn() { echo "⚠ $1"; }   # never touches $fail — warn-only by construction

# --- resolving the journal AFTER the mandated milestone-close drain --------------------------
# THIS LIVES IN THE SCRIPT, not only in the checklist at the top of this file: the script is
# the artifact `/init-harness` scaffolds into every adopter's repo, so a fix made only in the
# checklist would leave an adopter who closed a milestone with the exact bug it describes,
# including the unpushable branch (this row runs in task mode, which the pre-push hook
# runs on every push). Unlike `retention.md`, whose embedded copy is byte-compared against the
# real script by the suite, this file's script is a DIFFERENT gate (the canonical git-range
# variant) and cannot be byte-compared, so no test watches this copy for drift.
#
# Resolution order: this phase's own fragment (last by NAME — see the ordering note at the
# fragment lookup below) → this phase's slice of the archive → the newest fragment → the monolith.
# The archive step is what the milestone-close drain makes necessary: it empties the hot
# directory by design, so a gate that only reads it demands an artifact another mandated step
# deletes.
JARCHIVE=""; JSLICE=""; JFENCED=""
# A sentinel is a POSITION, not a string: a line counts as a fragment boundary only outside a
# fenced block AND preceded by a blank line or BOF. Fences are MATCHED (opening character and run
# length remembered, closed only by the same character at least as long with nothing after it),
# never counted. The one property this parser claims is that EVERY AMBIGUITY COSTS A FAIL, NEVER
# A PASS: an unterminated fence is not discarded (that would let a fence holding two quoted
# sentinels have its second one accepted), a slice ends at ANY sentinel-shaped line fenced or
# not, and the ambiguous case is reported (exit 2) rather than resolved. See this file's check-5
# entry for why each rule is chosen by its error direction rather than by correctness.
journal_slice() {
  awk -v pat="phase-$2" '
    # The length of the delimiter run this line opens with, or 0 if it is not a fence line.
    function frun(s) { if (match(s, /^(`+|~+)/) && RLENGTH >= 3) return RLENGTH; return 0 }
    # A closer for an open <ch>-fence of length <ln>: same character, at least as long, and
    # NOTHING but whitespace after it -- a bare delimiter run closes, and a run carrying a language
    # tag after it is content and an opener, not a closer. (The two forms are not spelled out with
    # literal backtick runs on purpose: the adopter-facing reference embeds this program inside a
    # markdown fence, and a triple run here ends that fence early. Measured: one such line cut the
    # extracted gate from 79,554 bytes to 9,504 -- 88% of it -- with nothing reporting a problem.)
    function fclose(s, ch, ln,   r) {
      r = frun(s)
      if (!r || substr(s, 1, 1) != ch || r < ln) return 0
      return (substr(s, r + 1) ~ /^[[:space:]]*$/)
    }
    # The payload of an ACCEPTED sentinel line: what sits between the opener and the ` -->`
    # terminator. Returns "" for the two shapes the grammar calls malformed -- an empty or
    # all-whitespace payload, and a comment with no terminator on its line -- so one return value
    # means "do not use this", and the caller decides how loudly to say so.
    function fpay(s,   t, i) {
      t = substr(s, length(PFX) + 1)
      i = index(t, " -->")
      if (i == 0) return ""
      t = substr(t, 1, i - 1)
      if (t ~ /^[[:space:]]*$/) return ""
      # WHITESPACE INSIDE THE PAYLOAD IS MALFORMED, which the grammar above has always said and
      # this function did not check. A payload names a PATH; a space in it means the line is not
      # the thing it looks like, and scoring it anyway hands the phase-name test a token nobody
      # wrote. Derived from a census of existing markers, the way the rest of this grammar was:
      # none has whitespace in the payload, so enforcing the stated rule refuses
      # nothing that exists. Returning "" routes it to the same loud failure as an empty payload.
      if (t ~ /[[:space:]]/) return ""
      return t
    }
    BEGIN { PFX = "<!-- fragment: "; fopen = 0; prevblank = 1; inb = 0; found = 0; fenced = 0
            printed = 0; malformed = 0 }
    {
      if (prevblank == 1 && $0 ~ /^<!-- fragment: /) {
        k = index($0, pat)
        after = (k > 0) ? substr($0, k + length(pat), 1) : ""
        nm = (k > 0 && (after == "-" || after == ".")) ? 1 : 0
        if (fopen == 0) {
          # ACCEPTED boundary. It both ends the previous slice and opens this one; the sentinel
          # line itself is never body.
          #
          # PAYLOAD MODE, and it is inert unless asked for: with -v emit=payload the caller gets
          # the markers themselves rather than the slice belonging to one phase.
          #
          # THE REASON IS FAIL-LOUD, not reach. A caller can already ask "is there a boundary for
          # this phase" with the exit status above, and measurement says that answer is right for
          # every marker in this archive today. What it CANNOT do is tell a malformed marker from
          # an absent one: a sentinel line with an empty payload exits 1 up there, which a caller
          # reads as "this file holds nothing for you" -- a fail-OPEN reading of the one shape the
          # grammar wants to fail loudly. Code 3 below is where that distinction lives.
          #
          # It also moves the NAME test to the caller, which already owns one, so a payload ending
          # AT the phase name parses -- the substring rule above needs a following `-` or `.`.
          # Stated rather than implied: that form is not load-bearing today. Such lines in
          # this archive sit directly beneath a full-path marker naming the same fragment, with no
          # blank line above them, so none of them is a boundary and the exit status misses
          # nothing. The grammar accepts the form; no archived evidence depends on it.
          #
          # Malformedness is judged HERE and only for accepted boundaries: a sentinel quoted inside
          # a fence is not a marker, so a malformed quoted example must fail no scan.
          if (emit == "payload") {
            p = fpay($0)
            if (p == "") malformed = 1
            else { print p; printed = 1 }
            prevblank = 0
            next
          }
          inb = nm
          if (nm) found = 1
          prevblank = 0
          next
        }
        # REJECTED — sentinel-shaped, but inside a fence. Rule 2: it still ENDS the open slice,
        # so no slice can ever reach into the next fragment. Rule 3: if it names this phase, say
        # so rather than dropping it silently. The line then falls through as ordinary body.
        if (nm) fenced = 1
        inb = 0
      }
      if (fopen == 0) { r = frun($0); if (r) { fopen = 1; fchar = substr($0, 1, 1); flen = r } }
      else if (fclose($0, fchar, flen)) fopen = 0
      if (inb) print
      prevblank = ($0 ~ /^[[:space:]]*$/) ? 1 : 0
    }
    # Slice mode: 0 a boundary for this phase was found, 1 none was, 2 one naming it was rejected
    # as fenced. Payload mode keeps the same error DIRECTION and adds one code rather than reusing
    # a quieter one: 3 means a malformed marker was seen, and it outranks having printed others,
    # because the whole point of the grammar is that fail-loud stays reachable.
    END { if (emit == "payload") exit(malformed ? 3 : (printed ? 0 : 1))
          exit(found ? 0 : (fenced ? 2 : 1)) }
  ' "$1"
}
# $1 journal dir  $2 phase  $3 archive dir (may be empty)  $4 monolith fallback
resolve_journal() {
  _rj_jd="$1"; _rj_ph="$2"; _rj_ad="${3:-docs/archive}"; _rj_fb="$4"; _rj_p=""
  if [ -n "$_rj_ph" ]; then
    _rj_p="$(ls "$_rj_jd"/*phase-"$_rj_ph"-*.md 2>/dev/null | tail -1 || true)"
    if [ -z "$_rj_p" ]; then
      # `<archive_dir>/journal/` explicitly, never `<archive_dir>/*.md`: the qa-log archive lives
      # beside it and carries the SAME sentinel format and the same fragment names, so the wider
      # glob reads Q&A content as though it were the journal.
      for _rj_a in "$_rj_ad"/journal/*.md; do
        [ -f "$_rj_a" ] || continue
        _rj_s="$(mktemp)" || return 1
        # `&& … || …`, never `cmd; rc=$?`: under `set -e` a bare non-zero simple command aborts
        # the gate, and this one returns non-zero on every archive that is not the right one —
        # i.e. on the common case.
        journal_slice "$_rj_a" "$_rj_ph" > "$_rj_s" && _rj_rc=0 || _rj_rc=$?
        if [ "$_rj_rc" -eq 0 ]; then JARCHIVE="$_rj_a"; JSLICE="$_rj_s"; printf '%s' "$_rj_s"; return 0; fi
        [ "$_rj_rc" -eq 2 ] && JFENCED="${JFENCED:-$_rj_a}"
        rm -f "$_rj_s"
      done
    fi
  fi
  [ -n "$_rj_p" ] || _rj_p="$(ls -t "$_rj_jd"/*.md 2>/dev/null | head -1 || true)"
  [ -n "$_rj_p" ] || _rj_p="$_rj_fb"
  printf '%s' "$_rj_p"
}
glob_exists() { compgen -G "$1" >/dev/null 2>&1; }
# `compgen -G ""` exits 0 vacuously — an ABSENT manifest glob key (empty pattern)
# used to print a silent ✓ for every glob-gated bad() (hard-fail) check below, so a manifest
# that predates a key could never fail on that check. req_glob routes an empty pattern to a
# visible ⊘ row instead: not a ✓ (nobody can mistake it for a pass) and not a hard bad() (a
# hard failure here would brick every pre-existing project manifest, switching the whole gate
# off in practice — the exact failure mode this branch exists to kill).
req_glob() { # $1=pattern (already {PHASE}-substituted, may be empty) $2=ok-label $3=bad-label $4=manifest-key (message text only)
  if [ -z "$1" ]; then echo "⊘ $4 not configured in manifest — $2 check skipped"
  elif glob_exists "$1"; then ok "$2"
  else bad "$3"; fi
}
# context-floor arming row — WARN-ONLY (never flips $fail): the floor is a machine-local
# user-settings hook, so a project gate must not fail on it; but an un-armed floor silently
# costs 2-3x per late-session turn. Built as a function with no arguments and no
# reads of gate state so the same bytes can be exercised on their own — every branch of a
# warn-only row is otherwise reached only through a full gate run, and one of the three
# cannot be reached that way at all (see "THE INERT BRANCH CANNOT PRINT FOR A USER" below).
#
# MORE THAN TWO states. Wiring and capability are different questions — liveness
# (configured) vs readiness (able to do its job) — and a row that answers only the first
# reads as though it had answered both:
#   not wired        no settings file names context-floor.sh
#   wired            settings name it AND `jq` was resolvable when this gate ran
#   wired but inert  settings name it and `jq` was NOT resolvable when this gate ran.
#                    hooks/context-floor.sh's first act is `command -v jq >/dev/null || exit 0`,
#                    so the floor is silently off wherever that probe fails — the fail-open is
#                    deliberate (a broken floor must never block work) and this row is the
#                    separate warning that comment relies on.
#
# A FOURTH state exists and this row does NOT distinguish it: wired, `jq` present,
# but the shared floor library (`hooks/lib/floor-env.sh`, or wherever `PLC_FLOOR_LIB` points) is
# absent or unusable. The hook fails open there too, and says so on its own stderr once per
# session — but from this gate's vantage that host still reads as plain `wired ✓`.
# That is stated here rather than papered over: the row's narrowness is the point, and a reader
# counting states is exactly who this comment is for.
# Detecting the fourth state from the gate would mean re-running the hook's own library probe
# in the gate's environment, which is the blind spot named below in different clothes. So it
# is not attempted.
# The two ⚠ states and the ✓ state all go through ok()/warn(), never bad(), so warn-only is
# structural here rather than a property to be remembered.
#
# ${HOME:-}: under set -u a stripped hook/CI environment without HOME would abort the whole
# gate on the bare expansion — the one thing a warn-only row must not do.
#
# WHAT THE CAPABILITY BRANCH DOES NOT PROVE — written here because the row's text is
# deliberately narrower than a reader's instinct, and widening it is the failure this row
# exists to stop rather than an improvement to it. `command -v jq` runs in THIS process, with
# THIS PATH, at gate time. It is the same probe the hook uses, in a different environment, and
# it says nothing about the environment the hook is later spawned in. The concrete blind spot
# is a GUI client (or any launchd-started app) whose PATH is stripped to /usr/bin:/bin while
# jq lives in /opt/homebrew/bin: the gate, started from a login shell, finds jq and prints
# "wired", and the hook that client spawns does not and exits 0. So the ✓ may say only that jq
# was resolvable when the gate ran; it may not say the hook works, will run, or is verified.
#
# THE INERT BRANCH CANNOT PRINT FOR A USER, IN EITHER DIRECTION. Stated plainly rather than as a
# testing note, because it bounds what this branch IS. The gate is bash + git + jq and reads the
# manifest through `jq` (`g()`) long before this row runs, so both worlds the warning could
# describe swallow it:
#   • a genuinely jq-less machine — the gate dies at its first `g` call with rc 127 and prints
#     NOTHING AT ALL. No row is reached, so this one is not either.
#   • a GUI/launchd client with a stripped PATH — the case this warning is actually about — the
#     gate runs from a login shell, finds jq, and prints the ✓ WIRED row. The hook is the inert
#     one; this branch stays silent while the row above it says "wired".
# There is no third arrangement: the branch is wired into the row and is unreachable in any real
# run of THIS gate. It exists as a CONTRACT for gates that CAN reach it — an adopter's variant
# that drops the jq dependency, or a runner that reaches this row under a different PATH than the
# one its manifest was read with — and driving `floor_arming_row` directly in the tests is not a
# convenience but the only execution context in which the branch exists at all.
# Consequently the parenthetical in hooks/context-floor.sh ("The arming path warns about this
# separately") is true about THIS ROW'S EXISTENCE — a wired-but-inert floor is named somewhere in
# the gate — and is NOT a claim that any user will see the warning fire. Do not upgrade it to one.
#
# WHAT THE GREP CAN AND CANNOT SEE: it is a literal substring search for `context-floor.sh` across
# the three settings files, which is exactly what the ✓ claims ("settings reference
# context-floor.sh") — pattern and claim are deliberately the same string, so neither can drift
# wider than the other. It does NOT parse the hooks array: the same ✓ prints when the name appears
# only in a comment, in an unrelated key, or inside a `disabledHooks` list. That residual is the
# price of staying grep-only in the not-wired branch (jq is not yet known to exist there — it is
# the very thing the next branch probes), and it is why the row says "settings reference" instead
# of "the hook is installed".
#
# The ⚠ is held to the same tie, and was not at first: it said "project `.claude/settings*.json`"
# while the grep reads two named files, so the row whose entire subject is a claim wider than its
# mechanism carried one. It now names the three paths the grep is given, in the same order, with
# `~` for the `${HOME:-}` the shell expands. A test pins the ⚠'s path list to the grep's the way
# the ✓'s pattern is already pinned — adding a file to the grep without naming it in the ⚠ (or
# widening the ⚠ back to a glob) is a failure, not a wording preference.
floor_arming_row() {
  if ! grep -qs 'context-floor\.sh' "${HOME:-}/.claude/settings.json" .claude/settings.json .claude/settings.local.json 2>/dev/null; then
    warn "context-floor hook not wired in ~/.claude/settings.json, project .claude/settings.json or .claude/settings.local.json — sessions can silently run to very large per-turn contexts. Fix: /init-harness --refresh (references/harness-primitives.md §9)"
  elif command -v jq >/dev/null 2>&1; then
    ok "context-floor hook wired (settings reference context-floor.sh) and jq was resolvable when this gate ran — not proof the hook fires where your client spawns it"
  else
    warn "context-floor hook wired but inert: jq was not resolvable when this gate ran, and hooks/context-floor.sh exits 0 without jq — the floor is silently off. Fix: install jq"
  fi
}
# bash 3.2's `[ a -nt b ]` truncates mtimes to whole seconds — verified on macOS
# /bin/bash 3.2: two files placed 0.2-0.9s apart in the SAME wall-clock second compare
# `-nt` FALSE regardless of which one is actually newer, so a freshness check built on `-nt`
# can wrongly reject genuinely-fresh evidence written less than a second after the commit it
# covers. `find X -newer Y` reads the full (sub-second) mtime — verified on macOS
# /usr/bin/find to order two such files correctly in both directions — and, checked
# empirically, prints nothing for byte-identical timestamps, i.e. it fails CLOSED on an exact
# tie (equal timestamps = NOT fresh) with no separate fallback needed.
fresh() { [ -e "$1" ] && [ -e "$2" ] && [ -n "$(find "$1" -newer "$2" -print 2>/dev/null)" ]; }
# Defect: `.git/HEAD`'s FILE mtime does not track HEAD — `git commit` leaves it at the time the
# branch was checked out (verified: two commits apart, `.git/HEAD` mtime is unchanged). So a legacy
# `fresh $EV .git/HEAD` compared the evidence against WHEN THE BRANCH WAS CHECKED OUT, not the commit
# it claims to cover: evidence written after checkout but before the current HEAD commit is newer than
# `.git/HEAD` yet older than HEAD, and false-PASSES as fresh. Anchor freshness to HEAD's committer-date
# (the semantic commit time) instead. `touch -t` is whole-second, so this carries a documented ≤1s
# fail-OPEN residual (evidence in the same second as the commit reads fresh — the correct side in the
# realistic run-tests-then-commit order); identical to a project-local variant's `stamp_ref`.
stamp_head_date() { touch -t "$(git show -s --format=%cd --date=format-local:%Y%m%d%H%M.%S HEAD)" "$1" 2>/dev/null; }
# The RUNS=N tail shared by both evidence modes: when test_runs_required>1 the evidence must carry a
# RUNS=N line with N>=required (the runner emits it). $1=evidence-file $2=required $3=ok-detail.
#
# $3 IS THE WHOLE CLAIM, and the CALLER owns it. This helper used to prefix every ✓ with the
# word "fresh", which asserts more than EITHER mode actually checks: the fingerprint mode proves only
# that the DECLARED inputs are unchanged (it is blind to every path outside `test_evidence_inputs`),
# and the mtime mode proves only that the file is newer than the branch point (mtime is not evidence
# that anything ran). A reader takes "fresh test-evidence" as "the tests are fresh", so the
# adjective made the row claim the one thing neither mechanism can support. Hard-coding it here also
# put the claim out of reach of the callers that DO know their own scope. Do not reintroduce it.
#
# NEITHER MAY $3 SAY "since it ran". One move breaks that wording:
# hand-author the evidence file with a valid header and a body reading "I DID
# NOT RUN ANY TEST", run nothing, and the gate prints its ✓ and PASSes.
# The gate reads a FILE; no branch of it observes a process. "since it ran" smuggles execution
# back into a claim about bytes -- the same defect class the adjective was removed for, one wording
# further in. Say "since this file was generated".
evidence_runs_ok() {
  if [ "$2" -gt 1 ]; then
    n=$(grep -oE 'RUNS=[0-9]+' "$1" | head -1 | cut -d= -f2 || true); n=${n:-0}
    if [ "$n" -ge "$2" ]; then ok "test-evidence RUNS=$n (>=$2); $3"
    else bad "test-evidence RUNS=$n < required $2 — run tests ${2}× (runner must emit 'RUNS=N')"; fi
  else ok "test-evidence non-empty; $3"; fi
}
# check_evidence: the one evidence check, called from both task and phase mode (they were byte-identical
# duplicates). TWO modes, selected by whether the manifest declares `test_evidence_inputs`:
#   • declared (non-empty array) → CONTENT FINGERPRINT (opt-in). The evidence file's first line
#     must be the `# plc-gate-evidence inputs=<digest>` header the runner prepended; the gate recomputes
#     the digest of the declared inputs from the working tree and compares. A missing header, the EMPTY
#     sentinel (globs matched nothing), or a mismatch are ALL hard fails — never a silent fall-back to
#     mtime (that silent-degrade is the whole point of moving off mtime).
#   • absent → LEGACY mtime check, byte-identical to before (no adopter's gate flips on upgrade). The
#     path check is opt-in by declaring the inputs, exactly like product_paths is.
#   • malformed (present but not a non-empty array) → fail closed, same type-guard as product_paths.
# p30: echo a manifest value back to the author, safely, using nothing but jq.
#
# WHY jq AND NOT `cut`/`head`. This repository shipped `scripts/utf8-text.sh` because `cut -c`
# truncates by BYTES and sliced a CJK title mid-character. The gates cannot source that
# file -- the canonical one is a self-contained script an adopter copies, and reaching outside it
# would make the gate depend on this repository. jq is already in the dependency envelope and
# slices strings by CODEPOINT, so it solves both halves with no new dependency.
#
# WHY `\p{Cc}` AND NOT A PATTERN FOR ANSI SEQUENCES, measured rather than assumed. Printing
# untrusted text containing escape sequences to a terminal is CWE-150, with live CVEs. On a fixture
# whose escape sequence straddles the truncation point:
#
#     strip then truncate, this class-based stripper       -> 0 ESC bytes
#     truncate then strip, this class-based stripper       -> 0 ESC bytes
#     truncate then strip, a whole-CSI-pattern stripper    -> 1 ESC byte   <- the real failure
#
# So the load-bearing property is that the stripper matches the CHARACTER, not the sequence: a bare
# ESC left behind by a cut is still removed. Strip-first is kept because it is easier to reason
# about, but the order is not what makes this safe and this comment must not be read as saying so.
#
# `\p{Cc}` is Unicode category Control -- both the C0 range and C1. An earlier attempt spelled the
# same class as a bracket range written with backslash-u escapes. It LOOKS right and silently
# destroyed the text: Oniguruma does not accept `\uXXXX`, so the class degenerated into ASCII
# ranges and ate the digits and letters this echo exists to show. It was caught by reading the
# output, not by the expression failing -- it never failed.
rationale_echo() {
  jq -r --argjson n 100 '
      .validator_input_paths_rationale
    | ( if   type == "object" then (.why // "") | (if type == "array" then map(tostring) | join(" ") else tostring end)
        elif type == "array"  then map(tostring) | join(" ")
        else tostring end )
    | gsub("\\p{Cc}"; "")
    | if length > $n then .[0:$n] + " [truncated]" else . end
  ' "$M" 2>/dev/null || printf '<unreadable>'
}
check_evidence() {
  # MAINTAINER WARNING (the conformance design): this function now holds TWO checks, not one. Below the evidence
  # freshness modes (fingerprint / legacy mtime) sits the `validator_input_paths_rationale` row.
  # It is a MANIFEST check, not an evidence-file check, and it deliberately runs BEFORE the
  # `[ -s "$EV" ]` early return — a repo whose evidence file is missing must still be told that its
  # narrowing is unargued. If you move, guard, or early-return out of the legacy-mtime branch, the
  # rationale row moves with you. Re-read this whole function before editing either half.
  TEI_TYPE="$(jq -r '.test_evidence_inputs | type' "$M" 2>/dev/null || echo null)"
  TEI_LEN="$(jq -r '.test_evidence_inputs | length' "$M" 2>/dev/null || echo 0)"
  # --- validator_input_paths_rationale: the narrowing argument must be DECLARED, not just enforced
  # `test_evidence_inputs` narrows what the freshness fingerprint can see. Narrowing is a
  # safety-REDUCING choice, so the manifest must carry the argument for why the narrowed set is the
  # right one. Content-checked, not merely present: an untouched scaffold placeholder must not
  # satisfy it, or the key becomes a formality.
  #
  # p30 CHANGED WHAT IS CHECKED, AND THE REASON THE OLD RULE EXISTED IS QUOTED RATHER THAN DELETED.
  #
  # What was here until p30: the value was an array of strings, and the row asserted the SHAPE of a
  # measurement argument inside that prose -- at least two ASCII digit groups, plus a case-insensitive
  # match on the English root "track". (An even earlier version keyed on the literal digits of one
  # repo's measurement with a proximity window, and was rejected because it punished honest
  # re-measurement and rewarded staleness. That rejection still stands; p30 is the next notch of the
  # same argument.)
  #
  # Why that rule is gone. Both predicates were language-dependent, so an honest argument written in
  # Chinese, or with its numbers spelled out, or carrying no numbers at all, was REFUSED by a
  # hard-fail gate. And the anti-gaming strength it was assumed to be buying was measured and is not
  # there: `0 0 track` -- nine characters, no measurement, no argument -- satisfied it, as did
  # `track track 00 00`. The one property it reliably delivered is that an untouched placeholder
  # fails, and that property is preserved below.
  #
  # What replaces it. The checkable part moves OUT of prose and into named members, following the
  # precedent of tools that solved this class (Bandit's `# nosec B602,B607` replaced free text with
  # enumerated codes; SPDX replaced license prose with language-neutral tokens). The prose member
  # `why` is free text in ANY language and is checked for PRESENCE only -- the gate asserts nothing
  # about what it says, because every policy tool surveyed that gates on justification prose
  # (SARIF, Snyk, Dependabot) enforces presence and never content.
  #
  # And `surface_kept` is DERIVED, not declared -- see evidence_kept_count(). A number the author
  # cannot write is a number they cannot fake and cannot leave to rot. This was not the original
  # design: it was added after a review found that declared numbers drift silently, and after the
  # repository that ships this gate was found stating a count far below the truth, with this very row
  # green over it.
  #
  # WHAT THIS ROW STILL DOES NOT DO, stated here so the ✓ text and this comment cannot drift apart:
  # it does not verify `surface_total`, which remains a declared figure only type-checked; it does
  # not cross-check `basis` against what `test_evidence_inputs` actually is (filed); and it
  # cannot tell a fresh measurement from a stale copy of `surface_total`.
  #
  # Gated on a present, NON-EMPTY `test_evidence_inputs` (the conformance design): with no narrowing declared there
  # is no narrowing to argue for, so nothing may be demanded. A malformed value (present but not an
  # array) falls through to the type-guard at the bottom of this function, which fails closed --
  # and NOT because nothing was narrowed: somebody writing `"test_evidence_inputs": "src/**"` is
  # plainly trying to. The value is rejected as malformed, which names the actual problem.
  # SEQUENCING, measured, because it reads as silence and is not: that type-guard sits BELOW the
  # `[ -s "$EV" ]` early return, so a repo with no evidence file yet is told about the missing
  # evidence first and about the malformed value on its next run. Red either way.
  if [ "$TEI_TYPE" = array ] && [ "${TEI_LEN:-0}" -gt 0 ]; then
    RAT_TYPE="$(jq -r '.validator_input_paths_rationale | type' "$M" 2>/dev/null || echo null)"
    # p30 (review): the help/note tail below was written out in full in EACH of check 9's three
    # refusal rows, in both gate homes -- six copies of the same ~500 characters. It had already
    # drifted once: two copies carried the "(here: N files)" parenthetical and the third did not,
    # and nothing distinguishes the three branches' tails from each other, so a reviewer found the
    # drift rather than a test. Built once here instead. This is INTRA-file only; the two homes stay
    # separate artifacts, and cross-home agreement is what test_gate_conformance.py holds.
    RAT_SHAPE='"validator_input_paths_rationale": {"surface_total": <number greater than 0>, "basis": "tracked-files"|"all-files"|"glob-set"|"explicit-path-list", "why": ["<free prose, any language>"]}'
    RAT_TAIL="help: paste this and edit the numbers -- $RAT_SHAPE -- and do NOT write surface_kept, this gate derives it (here: $(evidence_kept_count) files) | note: deleting test_evidence_inputs silences this row, and it ALSO drops the freshness check back to the legacy mtime comparison, which false-PASSES by construction in a fresh clone or CI. NOTE: this gate no longer requires Arabic numerals or the English word \"tracked\" anywhere -- that rule was removed in p30 because it refused honest arguments written in other languages, and because it was measured to pass strings that say nothing. Write why in whatever language you think in; this gate reads none of it."
    case "$RAT_TYPE" in
      object)
        # The declared members, each read by name. Every jq read is guarded: a read that exits
        # non-zero under `set -euo pipefail` would abort the whole gate with a raw trace instead of
        # printing this row, which is the class the legacy branch's `|| RAT_JOINED="__ERR__"` guards.
        RAT_TOTAL_TYPE="$(jq -r '.validator_input_paths_rationale.surface_total | type' "$M" 2>/dev/null || echo null)"
        RAT_TOTAL="$(jq -r '.validator_input_paths_rationale.surface_total // 0' "$M" 2>/dev/null || echo 0)"
        RAT_BASIS="$(jq -r '.validator_input_paths_rationale.basis // ""' "$M" 2>/dev/null || echo "")"
        # "an array of strings, at least one of which says something" -- in ONE jq expression, so the
        # sub-conditions cannot drift apart across three shell reads.
        #
        # NOT "every element non-empty", and the difference was found in use rather than by
        # design: this repository's own `why` is a multi-line prose block that uses empty strings as
        # PARAGRAPH SEPARATORS, and the first version of this rule refused it. The property that
        # actually matters is that the value says something, so `["", "", "x"]` passes and
        # `["", "  "]` does not. Elements must still all be strings -- a number in there is a
        # malformed value, not a formatting choice.
        RAT_WHY_OK="$(jq -r '.validator_input_paths_rationale.why | if type=="array" and length>0 and (all(.[]; type=="string")) and (any(.[]; gsub("\\s";"")|length>0)) then "yes" else "no" end' "$M" 2>/dev/null || echo no)"
        RAT_HAS_KEPT="$(jq -r 'if (.validator_input_paths_rationale|has("surface_kept")) then "yes" else "no" end' "$M" 2>/dev/null || echo no)"
        RAT_MISSING=""
        # A declared surface_kept is REFUSED rather than ignored. Accepting-and-ignoring it would let
        # a stale copied number sit in the manifest looking authoritative while nothing reads it --
        # which is exactly the stale-count shape this change exists to remove.
        [ "$RAT_HAS_KEPT" = yes ] && RAT_MISSING="$RAT_MISSING surface_kept-is-derived-remove-it"
        [ "$RAT_TOTAL_TYPE" = number ] || RAT_MISSING="$RAT_MISSING surface_total-must-be-a-json-number"
        if [ "$RAT_TOTAL_TYPE" = number ]; then
          # `jq` may print a float; compare in jq rather than in `[ ]`, which is integer-only.
          [ "$(jq -r '.validator_input_paths_rationale.surface_total | if . > 0 then "yes" else "no" end' "$M" 2>/dev/null || echo no)" = yes ] \
            || RAT_MISSING="$RAT_MISSING surface_total-must-be-greater-than-zero"
        fi
        case "$RAT_BASIS" in
          tracked-files|all-files|glob-set|explicit-path-list) ;;
          *) RAT_MISSING="$RAT_MISSING basis-must-be-one-of-tracked-files|all-files|glob-set|explicit-path-list" ;;
        esac
        [ "$RAT_WHY_OK" = yes ] || RAT_MISSING="$RAT_MISSING why-must-be-a-non-empty-array-of-non-empty-strings"
        if [ -z "$RAT_MISSING" ]; then
          ok "validator_input_paths_rationale: surface_kept=$(evidence_kept_count) files, DERIVED by this gate from the declared pathspecs; surface_total=$RAT_TOTAL and basis=$RAT_BASIS are DECLARED figures this gate only type-checked, not audited; why is free prose in any language and is checked for presence only"
        else
          bad "validator_input_paths_rationale [check9-object] declares a narrowing, so it must carry the argument for it | what this manifest has: $(rationale_echo) | what is missing:$RAT_MISSING | $RAT_TAIL"
        fi
        ;;
      array)
        # LEGACY SHAPE. Still accepted, deliberately and for a stated window: this repository is the
        # only KNOWN runner of this check, but the canonical gate is copied by adopters nobody can
        # enumerate -- unknown population, not zero population. The window's end condition is filed
        # as an open backlog item, because "for a window" with no trigger is an open-ended commitment dressed as a
        # bounded one.
        #
        # `|| RAT_JOINED="__ERR__"`: `jq join` EXITS NON-ZERO (not just empty) when the array holds a
        # non-string element -- `echo '{"r":[1,{"a":1}]}' | jq -r '.r|join(" ")'` exits 5 -- and under
        # `set -euo pipefail` a bare assignment would abort the whole gate with a raw jq trace instead
        # of printing this row. The sentinel routes it into the shape check, where zero numbers and no
        # "track" fail closed.
        RAT_JOINED="$(jq -r '.validator_input_paths_rationale | join(" ")' "$M" 2>/dev/null)" || RAT_JOINED="__ERR__"
        RAT_NUM_COUNT="$(printf '%s' "$RAT_JOINED" | grep -oE '[0-9]+' 2>/dev/null | wc -l | tr -d ' ')" || RAT_NUM_COUNT=0
        if [ "$RAT_JOINED" != "__ERR__" ] && [ "${RAT_NUM_COUNT:-0}" -ge 2 ] && printf '%s' "$RAT_JOINED" | grep -qiE 'track'; then
          # DEPRECATION, NOT REMOVAL: this must never touch $fail. A warning that fails the build is
          # a removal wearing a warning's words. `warn` is warn-only by construction (see its
          # definition), and the test for this row asserts on the row's TYPE, not on the substring --
          # this repository has measured an entire suite staying green while a row flipped from bad
          # to warn, because every assertion keyed on whether the line appeared.
          warn "[p30-deprecated-array-shape] validator_input_paths_rationale is the DEPRECATED array-of-strings shape. It still passes, and its old rule still applies to it (at least two ASCII digits plus the English word \"track\") -- which is the rule p30 replaced because it refuses honest arguments written in other languages. Migrate to the object shape -- paste this and edit the numbers: \"validator_input_paths_rationale\": {\"surface_total\": <number>, \"basis\": \"tracked-files\", \"why\": [\"<your existing prose, unchanged, in any language>\"]}. Do not add surface_kept; this gate derives it (here: $(evidence_kept_count) files)"
        else
          bad "validator_input_paths_rationale [check9-legacy] is the deprecated array shape and does not satisfy even that shape own rule | what this manifest has: $(rationale_echo) | what is missing: at-least-two-ascii-digits-and-the-english-word-track -- which is precisely the language-bound rule you should stop trying to satisfy | $RAT_TAIL"
        fi
        ;;
      *)
        # Neither object nor array -- including absent (jq prints "null"). Named as malformed rather
        # than silently treated as "no narrowing to argue for": the manifest DID declare a narrowing
        # (this branch is gated on that), so the argument is owed.
        bad "validator_input_paths_rationale [check9-type] declares a narrowing but the value is $RAT_TYPE | what this manifest has: $(rationale_echo) | what is missing: the-value-must-be-an-object -- an array of strings is the deprecated shape and still works | $RAT_TAIL"
        ;;
    esac
  fi
  EV="$(g test_evidence)"; REQ="$(jq -r '.test_runs_required // 1' "$M")"
  # Absent/empty test_evidence is a HARD FAIL, not a warn-skip — byte-identical to the pre-existing
  # inline blocks (an absent key gave EV="", `[ -s "" ]` false, then bad). Do NOT downgrade this to
  # a skip: a manifest with a test_command but no evidence path is a misconfiguration the gate must
  # surface, and a silent pass here is the vacuous-pass-on-absent-key defect this file guards against.
  [ -s "$EV" ] || { bad "stale/missing test-evidence — run: $(g test_command)"; return 0; }
  REGEN="{ close-gate.sh evidence-header; $(g test_command); } | tee $EV"
  if [ "$TEI_TYPE" = array ] && [ "${TEI_LEN:-0}" -gt 0 ]; then
    EVDIG="$(sed -n '1s/^# plc-gate-evidence inputs=\([0-9a-f]\{40,64\}\)[[:space:]]*$/\1/p' "$EV" 2>/dev/null)"
    NOWDIG="$(evidence_digest)"
    if [ "${NOWDIG#EMPTY-}" != "$NOWDIG" ]; then
      bad "test_evidence_inputs matched no tracked files — the fingerprint checks nothing; fix the globs in the manifest"
    elif [ -z "$EVDIG" ]; then
      bad "test-evidence $EV has no '# plc-gate-evidence inputs=<digest>' first line — regenerate it: $REGEN"
    elif [ "$EVDIG" != "$NOWDIG" ]; then
      bad "test-evidence $EV is stale — a declared test_evidence_input changed since it was generated — re-run: $REGEN"
    else
      evidence_runs_ok "$EV" "$REQ" "declared test_evidence_inputs are unchanged since this file was generated — NOT proof a test command ran, and blind outside that set"
    fi
  elif [ "$TEI_TYPE" = null ]; then
    HREF="$(mktemp)"; stamp_head_date "$HREF" || true  # HEAD committer-date, not .git/HEAD mtime.
    # `|| true`: on a stamp failure (bad/empty date → touch -t non-zero) set -e must NOT abort before the
    # rm below, or the temp file leaks. HREF then keeps its recent mktemp mtime, so evidence reads older
    # → fail-CLOSED (never a false fresh); the failure just cannot leak a /tmp file.
    if fresh "$EV" "$HREF"; then evidence_runs_ok "$EV" "$REQ" "$EV is newer than the branch point by mtime — mtime is not evidence the tests ran"
    else bad "stale/missing test-evidence — run: $(g test_command)"; fi
    rm -f "$HREF"
  else
    bad "test_evidence_inputs present in manifest but not a non-empty JSON array — fix the manifest"
  fi
}
# escape-hatch: an exempt_* flag is only legitimate if a 'SKIP: <reason>' line is written in the journal
skip_logged() { grep -qE '^[[:space:]]*SKIP:' "$(g journal)" 2>/dev/null; }
# --- retention: COUNT axis helpers (size caps are blind to many-small-files growth) ---
# Defined at top scope (not inline where they used to live, inside the phase branch) so BOTH
# phase mode (warn-only) and milestone mode (hard-fail via MILESTONE_COUNT_FAIL) can call the
# same three functions — the counting logic is identical in both modes, only what happens with
# MILESTONE_COUNT_FAIL afterwards differs. jq -r on an absent key yields empty; on "none"
# yields the literal string; else the number.
# cc(): $1=key $2=default. Mirrors hot_caps' cap_val ($3-default arg) below — jq -r on an
# absent key (or an entirely absent 'retention'/'count_caps' block, via jq's null-safe
# chaining) yields empty, and count_row's `case "$3" in ""|none|0) return 0 ;; esac` then
# swallows that SILENTLY: no row, no warn, no ⊘. That is the same vacuous-pass-on-absent-key defect `req_glob` above
# exists to kill, on the count axis.
# Routing through a caller-supplied default (specs/plans 10,
# docs_total 150 — the values this doc's manifest example and §"Project manifest" prose have
# always claimed as defaults) makes that prose true instead of aspirational.
cc() { jq -r ".retention.count_caps.$1 // $2" "$M"; }
count_md() { # $1=path $2=optional dir to exclude entirely, in addition to screenshots.
  # docs_total must not count the archive: archiving a doc is the gate's own prescribed remedy
  # for an over-cap close (the ✗ message says "run: bash scripts/retention-drain.sh"), so a
  # docs_total that still counts archived files makes that remedy a no-op — a blocking gate
  # with no reachable escape. The coverage-discovery row four lines below already excludes $AD
  # for the identical reason; this is the same exclusion applied to the count axis.
  local excl="${2:-}"
  if [ -n "$excl" ]; then
    find "$1" -name '*.md' -not -path '*/screenshots/*' -not -path "$excl/*" 2>/dev/null | wc -l | tr -d ' '
  else
    find "$1" -name '*.md' -not -path '*/screenshots/*' 2>/dev/null | wc -l | tr -d ' '
  fi
}
count_row() { # $1=label $2=count $3=cap — silent when at/under cap, "none", or "0" (unlimited)
  case "$3" in ""|none|0) return 0 ;; esac
  if [ "$2" -gt "$3" ]; then warn "count: $1 $2 files (cap $3)"; MILESTONE_COUNT_FAIL=1; fi
}

# ac-oracle-binding — every acceptance criterion has a runnable oracle or a still-true written-down
# exclusion. Implemented in the two companion scripts shipped below (`scripts/ac-evidence.sh`,
# `scripts/ac-baseline.sh`); this is only the wiring.
#
# Mode split: `task` checks ONLY what this branch's `Closes: <phase>:AC<n>` trailers claim, so a
# task is gated on its own declarations; `phase` checks the whole set the story declares, so a
# criterion nobody ever pointed at fails the close. Called from both mode blocks below.
#
# THREE non-pass rows, none of them silent, because each means something different:
#   ⊘  the manifest never configured this (same rule as req_glob — a hard failure here would brick
#      every manifest that predates the key, i.e. switch the whole gate off in practice)
#   ⚠  configured, but task mode was invoked without a phase id, so no criterion set resolved
#   ✗  configured, resolved, and a criterion in scope has neither an oracle nor a live exclusion
# A green with no row reads exactly like a green with a passing row; that is why none of these is
# allowed to print nothing.
ac_oracle_binding() { # $1 = mode (task|phase)
  local mode="$1" ac_sh="scripts/ac-evidence.sh" ac_bl="scripts/ac-baseline.sh"
  local exempt story_glob pat story args base_file ids out base mb
  exempt="$(jq -r '.exempt_user_story // false' "$M" 2>/dev/null || echo false)"
  story_glob="$(jq -r '.user_story_glob // ""' "$M" 2>/dev/null || echo "")"

  if [ "$exempt" = true ]; then
    # Inherits the guard that already exists rather than adding a second one: this gate already
    # requires a journal `SKIP:` line when the flag is true, and naming it here keeps the
    # exemption from being silent.
    ok "ac-oracle-binding SKIPPED — manifest sets exempt_user_story:true; the journal must carry the matching \`SKIP: user-story.md — <reason>\` line"
    return
  fi
  if [ -z "$story_glob" ]; then
    echo "⊘ user_story_glob not configured in manifest — ac-oracle-binding skipped"
    return
  fi
  if [ ! -r "$ac_sh" ]; then
    bad "ac-oracle-binding: $ac_sh is missing — the gate declares a check it cannot run (copy it from the section below)"
    return
  fi
  if [ -z "$PHASE" ]; then
    # HARD failure, deliberately. This branch is only reachable once the project has DECLARED the
    # check (a non-empty `user_story_glob` and no exemption), and at that point "I could not resolve
    # a criterion set" is a gate that has checked nothing while reporting a task complete.
    # A warning that returned 0 here would let a task close having checked nothing.
    # If your `make task-done` does not pass
    # PHASE, that is the thing to fix; see the `task-done` target below.
    bad "ac-oracle-binding: no PHASE argument — the check is configured but nothing was checked. Pass one (\`close-gate.sh $mode <PHASE>\`, or \`make task-done PHASE=X.Y\`)"
    return
  fi

  pat="$(printf '%s' "$story_glob" | sed "s/{PHASE}/$PHASE/g")"
  # shellcheck disable=SC2086
  set -- $pat
  if [ "$#" -gt 1 ]; then
    bad "ac-oracle-binding: user_story_glob matched $# files for phase $PHASE — exactly one is required, never a silent pick"
    return
  fi
  if [ ! -f "${1:-}" ]; then
    # Deliberately a FAIL, not a pass over an empty set: passing here hands a green row to every
    # phase that never wrote a story.
    bad "ac-oracle-binding: no user story resolves for phase $PHASE via \`$pat\` — set exempt_user_story:true if this phase legitimately has none"
    return
  fi
  story="$1"; args=""; ids=""
  base_file="$(jq -r '.ac_baseline // ""' "$M" 2>/dev/null || echo "")"
  [ -n "$base_file" ] && [ -r "$base_file" ] && args="--baseline $base_file"

  if [ "$mode" = phase ]; then
    # Baseline removal is automatic, and happens HERE at phase close — never in the pre-push hook,
    # where writing a tracked file leaves the pushed commit without it, the remote stale, and the
    # operator holding a dirty tree.
    if [ -n "$base_file" ] && [ -r "$base_file" ] && [ -r "$(jq -r '.ac_evidence // ""' "$M")" ] && [ -r "$ac_bl" ]; then
      bash "$ac_bl" prune --file "$base_file" --evidence "$(jq -r '.ac_evidence' "$M")" || true
    fi
  else
    ids="$(mktemp)"
    # The base is the DEFAULT branch, never `@{u}`. Measured: on a phase branch `@{u}` is that
    # branch's own remote, so merge-base(@{u}, HEAD) is HEAD, the scope comes back empty, and the
    # row goes green having checked nothing at all.
    base="$(git symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null || echo origin/main)"
    mb="$(git merge-base "$base" HEAD 2>/dev/null || echo unknown)"; export AC_MERGE_BASE="$mb"
    # A FAILURE and an EMPTY SCOPE are different facts. `|| : > "$ids"` collapsed them: an unset
    # origin/HEAD or an absent merge-base became "no criteria claimed by any commit on this
    # branch" and a green row. Keep stderr and fail loudly.
    #
    # A MALFORMED TRAILER IS NO LONGER ONE OF THOSE CASES, and the list above used to say
    # it was. `scope-from-trailers` now tokenises without judging, so a malformed value travels
    # to `report`, which names it with a MALFORMED verdict distinct from ORPHAN. The reason the
    # verdict moved is that a verdict is only worth what the reader of it sees: in the reference
    # project's own gate the equivalent call is `... 2>/dev/null || : > "$AC_IDS"`, so a `die`
    # here was swallowed AND the id file truncated, turning a red with the wrong message into a
    # GREEN printing "no criteria claimed". This variant never had that bug -- it already failed
    # loudly -- so for THIS gate the move is a better message rather than a fixed colour.
    #
    # The branch below is still reachable and still load-bearing: `scope-from-trailers` continues
    # to `die` on an undeterminable default branch and on an absent merge-base, which are what
    # those two remaining cases are.
    if ! bash "$ac_sh" scope-from-trailers "$PHASE" --base "$base" > "$ids" 2>"$ids.err"; then
      bad "ac-oracle-binding: could not determine what this branch claims to close — $(head -3 "$ids.err" | tr '\n' ' ')"
      rm -f "$ids" "$ids.err"
      return
    fi
    rm -f "$ids.err"
  fi

  # shellcheck disable=SC2086
  if out="$(bash "$ac_sh" report "$story" "$PHASE" $args ${ids:+--ids "$ids"} 2>&1)"; then
    ok "ac-oracle-binding ($mode): every criterion in scope has an oracle or a still-true exclusion — this proves each HAS one, never that the oracle is correct"
    printf '%s\n' "$out" | sed 's/^/    /'
  else
    bad "ac-oracle-binding ($mode) FAILED — a criterion in scope has neither an oracle nor a still-true exclusion:"
    printf '%s\n' "$out" | sed 's/^/    /'
  fi
  # NOT `[ -n "$ids" ] && rm -f "$ids"`. In phase mode `ids` is empty, so that AND-list returns 1 --
  # and as the LAST statement of a function it becomes the FUNCTION's return value. The call site is
  # a bare statement under `set -euo pipefail`, so a SUCCESSFUL phase run printed its ✓ row and then
  # killed the gate before the PASS/FAIL banner. Measured, not reasoned: the same shape mid-script is
  # exempt from `set -e` (the failing command is not the last in the list), which is why the
  # identical line survives mid-script -- the bug exists only where the
  # list is a function's tail. Explicit `return 0` rather than relying on `rm`'s status.
  if [ -n "$ids" ]; then rm -f "$ids"; fi
  return 0
}

if [ "$MODE" = task ]; then
  # Did this phase ship a product change? A path check asks the real question that
  # the old `feat|fix` commit-VERB test only proxied — a legit refactor-only commit under the product
  # tree had to be mislabeled `feat` to pass. Paths come from the manifest `.product_paths[]`.
  # BACKWARD-COMPATIBLE: an ABSENT key falls back to the legacy verb check, so a manifest predating
  # this key keeps its behavior — the path check is opt-in by declaring product_paths.
  #
  # SCOPE: the branch range `origin/main...HEAD`, NOT HEAD's own commit. This row used to read
  # `git diff-tree … HEAD` only, and the row right below it requires a SEPARATE `docs:` journal
  # commit in the range. The cadence writes that journal AFTER the code, so HEAD is the docs commit
  # and a correctly finished task failed here with "changed no product-tree path" — measured on
  # real hosts in the v5.0.0 release test, where one workaround was to rewrite this row to get past
  # it. The two rows could only both pass if the journal went first or into the code commit. The
  # range is also what SKILL.md's check table and this repo's own gate already say ("the phase diff
  # touched the product tree"). No `origin/main` (a repo with no remote yet, e.g. an adopter's very
  # first commit) → fall back to HEAD's own commit; `--root` keeps a root commit's files visible.
  if git rev-parse -q --verify origin/main >/dev/null 2>&1; then
    P1_SCOPE="origin/main...HEAD"
    # core.quotePath=false: with git's default, a non-ASCII path prints C-quoted ("src/caf\303\251.py"),
    # whose leading `"` never matches `^src`.
    P1_FILES="$(git -c core.quotePath=false diff --name-only origin/main...HEAD 2>/dev/null || true)"
    P1_SUBJ="$(git log origin/main..HEAD --format=%s 2>/dev/null || true)"
  else
    P1_SCOPE="HEAD (no origin/main to diff against)"
    P1_FILES="$(git -c core.quotePath=false diff-tree --no-commit-id --name-only -r --root HEAD 2>/dev/null || true)"
    P1_SUBJ="$(git log -1 --format=%s 2>/dev/null || true)"
  fi
  # Gate on the JSON *type*: `.product_paths[]?` also iterates an object's values, so a `{"a":"src/"}`
  # typo would silently run on those — only a non-empty ARRAY takes the path branch; null (absent) →
  # verb fallback; anything else (object / string / empty array) → fail closed.
  PP_TYPE="$(jq -r '.product_paths | type' "$M" 2>/dev/null || echo null)"
  if [ "$PP_TYPE" = array ] && PP_LIST="$(jq -r '.product_paths[]' "$M" 2>/dev/null)" && [ -n "$PP_LIST" ]; then
    # strip trailing slash, escape EVERY ERE metachar (so an adopter path like `c++/` or `app(v2)/`
    # can't reach grep -E raw and false-FAIL), join with `|`.
    PP_ALT="$(printf '%s\n' "$PP_LIST" | sed -e 's#/*$##' -e 's#[][(){}.^$*+?|\\]#\\&#g' | paste -sd'|' -)"
    # A ROOT entry (`.`, `./`, or a sole `/`) means "the product tree IS this repo" (a flat layout).
    # As a regex it would be `^\./` or empty, which no repo-relative path ever matches, so it would
    # fail forever; it means match-everything instead, i.e. "did the range change anything at all".
    PP_ROOT=0
    while IFS= read -r _pp; do
      _pp="$(printf '%s' "$_pp" | sed -e 's#/*$##')"
      if [ -z "$_pp" ] || [ "$_pp" = "." ]; then PP_ROOT=1; fi
    done <<<"$PP_LIST"
    # `(/|$)`, not a hard-appended `/`: an entry naming a FILE (`calc.py`, `Makefile`) must match
    # itself — with `/` it matched nothing, ever (init-harness wrote `["calc.py"]` for a
    # single-file project on real hosts) — while a directory entry still matches only its CONTENTS,
    # so `src` does not match `src-old/x.py`. grep -c … -gt 0 (not grep -q) for the same
    # pipefail/SIGPIPE reason the docs:/[DEBUG- checks below use.
    if { [ "$PP_ROOT" = 1 ] && [ -n "$P1_FILES" ]; } \
       || [ "$(grep -cE "^(${PP_ALT})(/|\$)" <<<"$P1_FILES" || true)" -gt 0 ]; then
      ok "phase touches the product tree in $P1_SCOPE (${PP_ALT})"
    else bad "no product-tree path changed in $P1_SCOPE (${PP_ALT}) — a task must ship a product change (or fix product_paths)"; fi
  elif [ "$PP_TYPE" = null ]; then
    grep -qE '^(feat|fix)(\(|:)' <<<"$P1_SUBJ" && ok "feat/fix commit in $P1_SCOPE" || bad "no feat/fix commit in $P1_SCOPE"
  else
    bad "product_paths present in manifest but not a non-empty JSON array — fix the manifest"
  fi
  # capture-then-herestring, NOT `git log … | grep -q`: a multi-commit range means grep -q can match
  # a docs: subject early and SIGPIPE the still-writing git log → pipefail non-zero → false-negative.
  DOCS_SUBJ="$(git log origin/main..HEAD --format=%s 2>/dev/null || true)"
  grep -qE '^docs:' <<<"$DOCS_SUBJ" && ok "docs: journal commit in branch" || bad "no docs: journal commit in branch range"
  # journal target: MOST-RECENTLY-MODIFIED docs/journal.d/*.md fragment if the dir has one
  # (fragment pilot). mtime (ls -t), NOT filename sort: same-day fragments 2026-01-02-note10.md
  # vs 2026-01-02-note5.md sort wrong lexicographically ('1'<'5'), and multiple undrained fragments
  # coexisting within a milestone is the expected state. macOS sort has no -V; ls -t is portable.
  # Falls back to the manifest 'journal' monolith path (back-compat for non-fragment projects).
  JD="$(g retention.journal_dir 2>/dev/null)"; JD="${JD:-docs/journal.d}"
  J="$(resolve_journal "$JD" "$PHASE" "$(g retention.archive_dir 2>/dev/null)" "$(g journal)")"
  # match the journal-schema canonical bold form (**Plan deviations** / **Plan deviations:**) AND an H2/H3 header form
  if grep -qE '\*\*Plan deviations:?\*\*|^#{1,4}[[:space:]]*Plan deviations' "$J" 2>/dev/null; then ok "journal Plan-deviations header"; else bad "journal missing 'Plan deviations' header"; fi
  check_evidence   # content fingerprint when test_evidence_inputs is declared, else legacy mtime
  # only ADDED lines (^+), and exclude the gate tooling itself (these scripts legitimately contain "[DEBUG-")
  # capture-then-herestring, NOT `git diff … | grep -q`: under pipefail a grep -q early-exit on the
  # first match SIGPIPEs the still-writing git diff (141), pipefail surfaces 141 over grep's 0, the
  # `if` sees non-zero and falls to the else "no orphan" branch — a silent FALSE NEGATIVE that lets a
  # real [DEBUG- line through the gate whenever the diff is large enough for git to still be writing.
  DBG_DIFF="$(git diff HEAD~1 2>/dev/null -- . ':(exclude)scripts/close-gate.sh' ':(exclude)scripts/test-close-gate.sh' || true)"
  if grep -qE '^\+.*\[DEBUG-' <<<"$DBG_DIFF"; then bad "orphan [DEBUG- logs in diff"; else ok "no orphan debug logs"; fi
  # Sweeper diff-direction teeth — inert unless a commit in range is tagged 'Archetype: sweep'.
  # A sweep MUST subtract code (net-negative LOC, audit-artifact paths excluded) or log a SWEEP-PERF win.
  # capture-then-herestring, NOT `git log … | grep -q`: an early Archetype: sweep trailer in a large
  # multi-commit range would SIGPIPE the still-writing git log → pipefail non-zero → the whole sweep
  # diff-direction gate silently SKIPPED (a mislabelled sweep escapes its net-negative-LOC teeth).
  SWEEP_BODIES="$(git log origin/main..HEAD --format=%B 2>/dev/null || true)"
  if grep -qiE '^Archetype:[[:space:]]*sweep' <<<"$SWEEP_BODIES"; then
    nums="$(git diff --numstat origin/main..HEAD -- . ':(exclude)docs/**' ':(exclude)CHANGELOG.md' 2>/dev/null)"
    add=$(awk '{a+=$1} END{print a+0}' <<<"$nums"); del=$(awk '{d+=$2} END{print d+0}' <<<"$nums")
    if [ "$del" -gt "$add" ]; then ok "sweep diff net-negative ($add added, $del deleted)"
    elif grep -qE '^[[:space:]]*SWEEP-PERF:' "$(g journal)" 2>/dev/null; then ok "sweep diff not net-negative but SWEEP-PERF evidence logged"
    else bad "Archetype: sweep but diff not net-negative ($add added / $del deleted) and no 'SWEEP-PERF: <evidence>' in journal — a sweep must subtract or prove a perf win"; fi
  fi
  ac_oracle_binding task
elif [ "$MODE" = phase ]; then
  [ -n "$PHASE" ] || { echo "✗ phase mode needs PHASE arg"; exit 1; }
  RANGE="origin/main..HEAD"
  PDG="$(g phase_docs_glob)"; PLG="$(g plan_glob)"
  if [ "$(jq -r .exempt_user_story "$M")" = true ]; then
    skip_logged && ok "user-story exempt (SKIP: logged)" || bad "exempt_user_story=true but no 'SKIP:' line in journal"
  else req_glob "${PDG:+${PDG}*user-story*}" "user-story.md" "no user-story.md for phase $PHASE" "phase_docs_glob"; fi
  req_glob "$PDG" "spec doc"    "no spec doc for phase $PHASE"    "phase_docs_glob"
  req_glob "$PLG" "plan doc"    "no plan doc for phase $PHASE"    "plan_glob"
  ac_oracle_binding phase
  # NOTE: no handoff-doc check here — the handoff file was retired; its one
  # non-derivable section (§7 findings/gotchas) is enforced by the journal-touched check
  # above instead (FACT schema, references/journal-schema.md). handoff-template.md is
  # retained for its §7 field definitions + PR-description appendix, but names no output
  # file any more, so there is nothing left for a glob-based artifact check to find.
  # CHANGELOG-touched: accept a change under retention.changelog_dir (fragment convention)
  # OR CHANGELOG.md itself (back-compat / un-adopted projects) — capture-then-grep, no
  # pipe into grep -q (mirrors the journal-touched union-grep below).
  CD="$(g retention.changelog_dir 2>/dev/null)"; CD="${CD:-changelog.d}"
  CL_DIFF="$(git diff --name-only $RANGE 2>/dev/null)"
  if [ "$(jq -r .exempt_changelog "$M")" = true ]; then
    skip_logged && ok "changelog exempt (SKIP: logged)" || bad "exempt_changelog=true but no 'SKIP:' line in journal";
  elif grep -qE "^(${CD}/|CHANGELOG\.md$)" <<<"$CL_DIFF"; then ok "CHANGELOG [Unreleased] touched";
  else bad "CHANGELOG.md not touched in $RANGE"; fi
  if [ "$(jq -r .user_visible "$M")" = true ]; then
    req_glob "$(g smoke_a_glob)" "Track A smoke checklist" "no Track A smoke checklist" "smoke_a_glob"
    req_glob "$(g smoke_b_glob)" "Track B e2e spec"        "no Track B e2e spec"        "smoke_b_glob"
  fi
  if [ "$(jq -r .exempt_user_story "$M")" = true ]; then ok "acceptance tests exempt (user-story exempt)";
  else req_glob "$(g acceptance_glob)" "acceptance tests present" "no acceptance tests for phase $PHASE (cadence step 1.5 unrun?)" "acceptance_glob"; fi
  # capture-then-herestring, NOT `git diff … | grep -q`: many changed files means grep -q can match
  # ROADMAP early and SIGPIPE the still-writing git diff → pipefail non-zero → false-POSITIVE failure.
  ROADMAP_DIFF="$(git diff --name-only $RANGE 2>/dev/null || true)"
  # TWO independent facts, both required. "Touched in range" proves this phase changed the
  # file; it does NOT prove the phase is IN it — a whitespace edit satisfies a touch check.
  # The row's claim is "the roadmap reflects this phase", and that is only observable in the
  # text, so grep the phase identifier too. A gate that checks only
  # recency can print "✓ ROADMAP.md updated this phase" while the phase appears nowhere in the
  # file. Touch and mtime are both proxies; the content is the thing.
  # The id match is ANCHORED. `grep -F` disables regex; it does NOT make the match whole-token,
  # so a bare `-F "$PHASE"` lets phase `1.2` be satisfied by a row that only says `1.20`, and
  # `X4` by `X40`. Require a non-identifier character (or a line edge) on both sides; the id
  # itself is regex-escaped — the class covers BOTH the BRE and the ERE metacharacters,
  # so `.` in `1.2` cannot match any character and `|` in an id cannot become an alternation.
  PHASE_RE="$(printf '%s' "$PHASE" | sed 's/[][\.*^$/&+?(){}|]/\\&/g')"
  if ! grep -q 'docs/ROADMAP.md' <<<"$ROADMAP_DIFF"; then bad "ROADMAP.md not updated in $RANGE"
  elif ! grep -qE "(^|[^0-9A-Za-z._-])${PHASE_RE}([^0-9A-Za-z._-]|$)" docs/ROADMAP.md 2>/dev/null; then
    bad "docs/ROADMAP.md was touched in $RANGE but never mentions phase $PHASE — a touch is not the ceremony"
  else ok "ROADMAP names phase $PHASE"; fi
  # journal-touched: accept a change under retention.journal_dir (fragment pilot) OR the
  # manifest 'journal' monolith path (back-compat) — capture-then-grep, no pipe into grep -q.
  # BSD grep errors ('empty (sub)expression', exit 2) on an alternation with an
  # empty branch, e.g. `^(docs/journal.d/|)` when manifest 'journal' is unset — GNU grep
  # tolerates it, BSD (macOS default, verified on /usr/bin/grep) does not. JD always has a
  # convention default so it can never itself be empty; JN (the monolith path) has none, so
  # only include its branch when it is actually configured — never emit an empty alternative.
  JD="$(g retention.journal_dir 2>/dev/null)"; JD="${JD:-docs/journal.d}"
  DIFF_FILES="$(git diff --name-only $RANGE 2>/dev/null)"
  JN="$(g journal)"
  # explicit if/then, NOT `[ -n "$JN" ] && JOURNAL_PATTERN=…`: under `set -e` that &&-list
  # returns 1 whenever JN is empty. It happens to be exempt from set -e (a non-final command
  # in an && list), but this file already carries one bug born of a too-clever `||` fallback —
  # spell it out rather than make the next reader re-derive the exemption.
  JOURNAL_PATTERN="^(${JD}/"
  if [ -n "$JN" ]; then JOURNAL_PATTERN="${JOURNAL_PATTERN}|${JN}"; fi
  JOURNAL_PATTERN="${JOURNAL_PATTERN})"
  if grep -qE "$JOURNAL_PATTERN" <<<"$DIFF_FILES"; then ok "journal touched this phase"; else bad "journal not touched in $RANGE"; fi
  # FACT-entry enforcement: the retired handoff file's one non-derivable section (§7
  # findings/gotchas) survives only in the journal's FACT entry (references/journal-schema.md
  # §"The FACT entry"), and this loop is what backs the checklist's "is enforced" claim.
  # Canonical field form is the markdown-bullet style journal entries use under this
  # schema ("- **Decision:** ..."), not a bare "Decision:" line.
  # $J = newest fragment under $JD (mtime, not filename — same rationale as task mode's $J,
  # same $JN monolith fallback the journal-touched check above already resolved).
  #
  # `Backing` is the evidence slot. A schema with a slot for the CONCLUSION and none for the
  # EVIDENCE it rests on lets every argument silently degrade into an assertion, and the one
  # statistic an argument turns on is the first thing a distilled `Why` drops.
  # A missing field cannot be patched by writing more
  # prose into an adjacent one: with no slot that says "the number you must not drop," the writer
  # drops it. Hence a slot of its own,
  # so a claim cannot be stated without its support.
  J="$(resolve_journal "$JD" "$PHASE" "$(g retention.archive_dir 2>/dev/null)" "$JN")"
  [ -n "${JFENCED:-}" ] && [ -z "${JARCHIVE:-}" ] && warn "a line naming phase $PHASE exists in $JFENCED but sits inside a code fence, so it is not read as a fragment boundary — either it is a quoted example, or an unterminated fence earlier in that file is hiding a real one"
  MISSING_FACT=""
  for field in Date Decision Why Backing Rejected Source; do
    grep -qE "^-[[:space:]]*\*\*${field}:\*\*" "$J" 2>/dev/null || MISSING_FACT="$MISSING_FACT $field"
  done
  if [ -n "$MISSING_FACT" ]; then
    bad "journal FACT entry missing required field(s):$MISSING_FACT — see references/journal-schema.md §\"The FACT entry\""
  else
    ok "journal FACT entry has all required fields"
  fi
  # test-evidence at phase close. check_evidence runs in BOTH task and phase mode, and the
  # pre-push hook runs task mode on every push, so the evidence row is checked on every
  # pushed task, not only at phase close. Skipped only when the project has no test_command.
  # (Was missing here originally — tests fell through every hooked gate.)
  #
  # Say "the evidence row is checked", NOT "tests are forced". The row proves that an evidence
  # artifact exists and that the DECLARED inputs have not changed since it was produced. It is
  # blind to every path outside test_evidence_inputs, and it cannot tell a real run from a
  # hand-written file. Both blind spots are recoverable by declaring honestly; neither is
  # recoverable by wording the ✓ as though the mechanism were stronger.
  if [ -n "$(g test_command)" ]; then
    check_evidence   # content fingerprint when test_evidence_inputs is declared, else legacy mtime
  fi
  # context-floor arming row — WARN-ONLY (not wired · wired · wired but inert: jq missing).
  # A fourth real state — wired, jq present, shared floor library unusable — is NOT
  # distinguished here and reads as plain `wired`. Defined with the helpers above, where its
  # full rationale, the PATH blind spot the ✓ must not outrun, the unreported fourth state,
  # and the jq bootstrap wrinkle are written out.
  floor_arming_row
  # retention hot-cap rows — WARN-ONLY (never flips $fail). See references/retention.md §"Hot-doc caps"
  # cap_val: read retention.hot_caps.<key>[0|1] from the manifest, default when absent (jq's
  # null-safe chaining means a missing 'retention' block never errors — runs with zero config).
  cap_val() { jq -r "(.retention.hot_caps.$1[$2])? // $3" "$M" 2>/dev/null; }
  cap_none() { [ "$(jq -r ".retention.hot_caps.$1 // empty" "$M" 2>/dev/null)" = "none" ]; }
  RM=".claude/retention-state.json"
  RET_OVER=""
  ret_warn() { # $1=state-key(path) $2=label $3=over-description — the ONE warn/escalate/record path
    if grep -qs "\"$1\"" "$RM" 2>/dev/null; then
      echo "⚠ $2 over hot cap ($3) — SECOND consecutive over-cap close — this doc is not draining"
    else
      echo "⚠ $2 over hot cap ($3) — drain at milestone close or raise retention.hot-caps"
    fi
    RET_OVER="$RET_OVER\"$1\", "
  }
  ret_cap() { # $1=path $2=hot_caps-key $3=default-lines $4=default-kb $5=label
    [ -f "$1" ] || return 0
    if cap_none "$2"; then ok "$5 exempt (retention.hot-caps: none)"; return 0; fi
    ML="$(cap_val "$2" 0 "$3")"; MK="$(cap_val "$2" 1 "$4")"
    RL=$(wc -l < "$1" | tr -d ' '); RK=$(( $(wc -c < "$1") / 1024 )); over=""
    [ "$ML" -gt 0 ] && [ "$RL" -gt "$ML" ] && over="lines $RL>$ML"
    [ "$MK" -gt 0 ] && [ "$RK" -gt "$MK" ] && over="${over:+$over, }size ${RK}K>${MK}K"
    if [ -n "$over" ]; then ret_warn "$1" "$5" "$over"; else ok "$5 under hot cap"; fi
  }
  ret_cap "RESUME.md" resume 200 25 "RESUME.md"
  # status_doc: ${VAR:-default}, NOT `|| echo` — g() prints empty with exit 0 on a missing
  # key, so an `||` fallback never fires (that bug shipped once: the status row was dead code)
  SD="$(g status_doc 2>/dev/null)"; SD="${SD:-docs/STATUS.md}"
  ret_cap "$SD" status 300 30 "status doc"
  ret_cap "docs/brainstorming-qa-log.md" qa_log_hot 0 50 "qa-log"
  # qa-log fragment dir: directory total, KB only — ADDITIONAL to the monolith file cap
  # above, not a replacement. Unlike journal (drains to zero, no hot monolith), qa-log keeps
  # BOTH a hot monolith (capped above) and a fragment dir (capped here). Shares the qa_log_hot
  # exemption key with the monolith cap — one 'qa-log: none' exempts file and dir together.
  QD="$(g retention.qa_log_dir 2>/dev/null)"; QD="${QD:-docs/qa-log.d}"
  if [ -d "$QD" ]; then
    if cap_none qa_log_hot; then ok "qa-log hot zone exempt (retention.hot-caps: none)"; else
      QMK="$(cap_val qa_log_hot 1 50)"
      QK=$(( $(du -sk "$QD" | cut -f1) ))
      if [ "$QMK" -gt 0 ] && [ "$QK" -gt "$QMK" ]; then ret_warn "$QD" "qa-log hot zone" "size ${QK}K>${QMK}K"
      else ok "qa-log hot zone under cap"; fi
    fi
  fi
  # qa-log citation coverage — WARN-ONLY (never flips $fail). The brainstorm protocol's #1 silent
  # degradation is skipping research and opinion-polling: every **Locked:** decision must cite ≥1
  # source ("no citation, no send", references/brainstorm-research-protocol.md). This row surfaces
  # any locked decision whose ### Q section carries no http(s) URL. Scoped to the fragment dir
  # (short-lived, current-phase); the compiled monolith is historical and deliberately NOT
  # re-litigated. WARN-ONLY on purpose, not hard-fail: a compressed established-pattern decision may
  # legitimately cite a PRIOR-PHASE lock (e.g. "M2.3 Q4") instead of a URL, which a URL-only hard
  # gate would false-block — so the row informs the human at PR without blocking a legit compressed
  # cite. awk splits each fragment on ### headers; a section with a Locked line but no URL prints its
  # header (function declared first so the pattern rules can call flush() on each new section + END).
  if [ -d "$QD" ]; then
    for qf in "$QD"/*.md; do
      [ -f "$qf" ] || continue
      uncited="$(awk '
        function flush() { if (hdr!="" && locked && !cited) print hdr }
        /^###[[:space:]]/ { flush(); hdr=$0; locked=0; cited=0; next }
        /\*\*Locked:?\*\*/ { locked=1 }
        /https?:\/\// { cited=1 }
        END { flush() }
      ' "$qf" 2>/dev/null || true)"
      if [ -n "$uncited" ]; then
        while IFS= read -r qh; do
          [ -n "$qh" ] && echo "⚠ qa-log: $(basename "$qf") — locked decision with no citation URL — \"$qh\" — research skipped? (brainstorm-research-protocol.md: no citation, no send)"
        done <<<"$uncited"
      fi
    done
  fi
  # changelog fragment dir: directory total, KB only. changelog.d lives OUTSIDE docs/, so the
  # coverage-floor find below never scans it — this dir-cap row is its ONLY size monitor, and
  # its fragments compile only at /release (infrequent) so unbounded between-release growth
  # would otherwise be invisible. Own exemption key (changelog_hot); warn-only like every
  # retention row. $CD was resolved above at the CHANGELOG-touched check.
  if [ -d "$CD" ]; then
    if cap_none changelog_hot; then ok "changelog hot zone exempt (retention.hot-caps: none)"; else
      CMK="$(cap_val changelog_hot 1 50)"
      CK=$(( $(du -sk "$CD" | cut -f1) ))
      if [ "$CMK" -gt 0 ] && [ "$CK" -gt "$CMK" ]; then ret_warn "$CD" "changelog hot zone" "size ${CK}K>${CMK}K"
      else ok "changelog hot zone under cap"; fi
    fi
  fi
  # journal hot zone: directory total, KB only (lines dimension is unused for a directory).
  # Same exemption (cap_none) + same warn/escalate/record path (ret_warn) as the file caps.
  # $JD was resolved above at the journal-touched check.
  if [ -d "$JD" ]; then
    if cap_none journal_hot; then ok "journal hot zone exempt (retention.hot-caps: none)"; else
      JMK="$(cap_val journal_hot 1 100)"
      JK=$(( $(du -sk "$JD" | cut -f1) ))
      if [ "$JMK" -gt 0 ] && [ "$JK" -gt "$JMK" ]; then ret_warn "$JD" "journal hot zone" "size ${JK}K>${JMK}K"
      else ok "journal hot zone under cap"; fi
    fi
  fi
  # persist the over-cap list for the consecutive-close escalation. jq merge (not python3 —
  # the gate has no python3 dependency elsewhere) preserves any existing 'declined_distill' key.
  # if/then (not `&& mv || printf`): a fallback chained with || would also fire on an mv
  # failure and overwrite the state file, losing declined_distill; here an mv failure keeps
  # the old (stale but intact) state file instead.
  mkdir -p .claude
  OVER_JSON="[${RET_OVER%, }]"
  if [ -f "$RM" ] && jq --argjson over "$OVER_JSON" '.over_cap_at_last_close = $over' "$RM" > "$RM.tmp" 2>/dev/null; then
    mv "$RM.tmp" "$RM" || rm -f "$RM.tmp"
  else
    rm -f "$RM.tmp" 2>/dev/null
    printf '{ "over_cap_at_last_close": %s }\n' "$OVER_JSON" > "$RM"
  fi
  # coverage discovery — WARN-ONLY. See references/retention.md §"Coverage discovery"
  AD="$(g retention.archive_dir 2>/dev/null)"; AD="${AD:-docs/archive}"
  case "$AD" in docs/*) : ;; *) echo "⚠ retention.archive-dir '$AD' outside docs/ — config error, falling back to docs/archive"; AD=docs/archive ;; esac
  FLOOR="$(g retention.coverage_floor_kb 2>/dev/null)"; FLOOR="${FLOOR:-50}"
  # $CD is a defensive no-op under the default config: `find docs ...` only ever scans under
  # docs/, and changelog_dir defaults to changelog.d at the repo root, so $CD can never match
  # here by default. Kept in the exclusion list for the projects that nest changelog_dir under
  # docs/ (e.g. docs/changelog.d) — for those, $CD DOES match and this line is what excludes it.
  COVER_HITS="$(find docs -name '*.md' -size +"${FLOOR}"k 2>/dev/null | grep -vE "^($AD|$JD|$QD|$CD)/" || true)"
  if [ -n "$COVER_HITS" ]; then
    while IFS= read -r f; do
      # known-set membership is a v1 approximation: substring match of the basename against the
      # manifest text — looser than "referenced by a manifest key" (a basename collision counts
      # as known). Deliberate: warn-only row, cheap check, false-negative beats a parser here.
      grep -qs "$(basename "$f")" "$M" 2>/dev/null && continue
      echo "⚠ coverage: $f ($(du -k "$f" | cut -f1)K) not in retention net — add to manifest known set or archive it"
    done <<<"$COVER_HITS"
  fi
  # --- retention: COUNT axis (size caps are blind to many-small-files growth) ---
  # WARN-ONLY at task/phase — never touches $fail (count_row calls warn(), never bad()).
  # MILESTONE_COUNT_FAIL is set here so milestone mode (below) can consume it as a hard gate.
  # cc/count_md/count_row are defined at top scope — see the comment above the task-mode branch.
  MILESTONE_COUNT_FAIL=0
  count_row "docs/superpowers/specs" "$(count_md docs/superpowers/specs)" "$(cc specs 10)"
  count_row "docs/superpowers/plans" "$(count_md docs/superpowers/plans)" "$(cc plans 10)"
  count_row "docs/**/*.md"           "$(count_md docs "$AD")"            "$(cc docs_total 150)"
elif [ "$MODE" = milestone ]; then
  # --- milestone mode: the ONE point where retention counts — and, below, unconfigured
  # required-artifact manifest keys — actually block. Warn-only everywhere else is deliberate:
  # a gate that bites every commit gets switched off by the person it bites; a gate that never
  # bites is not a gate. Milestone close is the moment retention.md already chose for its
  # drain — "the one moment nothing else is competing for attention". Deliberately does NOT
  # reuse the full phase-mode artifact block (CHANGELOG/ROADMAP/journal-touched/test-evidence/
  # hot-caps/coverage/qa-log-citation all assume a single phase's commit range, which a
  # milestone — spanning multiple phases — does not have); those stay phase-scoped checks.
  # $AD is not in scope here (phase mode computes it further down its own branch) — resolve it
  # the same way (config-error fallback included) so docs_total excludes the archive here too.
  AD="$(g retention.archive_dir 2>/dev/null)"; AD="${AD:-docs/archive}"
  case "$AD" in docs/*) : ;; *) AD=docs/archive ;; esac
  MILESTONE_COUNT_FAIL=0
  count_row "docs/superpowers/specs" "$(count_md docs/superpowers/specs)" "$(cc specs 10)"
  count_row "docs/superpowers/plans" "$(count_md docs/superpowers/plans)" "$(cc plans 10)"
  count_row "docs/**/*.md"           "$(count_md docs "$AD")"            "$(cc docs_total 150)"
  if [ "$MILESTONE_COUNT_FAIL" = 1 ]; then
    echo "✗ milestone cannot close over a retention count cap — run: bash scripts/retention-drain.sh"
    fail=1
  fi
  # --- required-artifact configuration check ---
  # The same 3 manifest keys that print a ⊘ "not configured in manifest" row at every
  # task/phase close (req_glob) are non-blocking THERE by design: a hard
  # failure on a project's FIRST-EVER close would brick the gate for any manifest predating the
  # key, which gets the whole gate disabled. Milestone is different — an accumulated, ignored
  # ⊘ finally stops being free here. (handoff_glob is NOT in this set — the handoff
  # file was retired, so a required key naming it could never be satisfied by any manifest
  # value, hard-failing every milestone close out of the box.)
  # UNCONDITIONAL — runs whether or not a PHASE arg was supplied. This check tests MANIFEST
  # WIRING (`[ -n "$(g "$key")" ]`: is the key configured at all), not per-phase artifact
  # existence — g() substitutes $PHASE into the glob string via sed, but substituting an empty
  # $PHASE into a configured, non-empty glob does not make that string become empty. PHASE was
  # never architecturally required here, so it must never gate whether this block runs: a bare
  # `close-gate.sh milestone` (no PHASE) — exactly what `$(PHASE)` expands to when `make
  # milestone-done` is invoked without `PHASE=X.Y`, the checked-in wiring below — has to be
  # caught by this check the same as a `milestone` close with PHASE supplied. Silently skipping
  # it on a missing PHASE arg would silently disable the one block this whole mode exists for,
  # on the one invocation most likely to happen by accident.
  UNCONFIGURED_KEYS=""
  for key in phase_docs_glob plan_glob acceptance_glob; do
    [ -n "$(g "$key")" ] || UNCONFIGURED_KEYS="$UNCONFIGURED_KEYS $key"
  done
  if [ -n "$UNCONFIGURED_KEYS" ]; then
    echo "✗ milestone cannot close with required-artifact checks never configured in manifest:$UNCONFIGURED_KEYS — configure them in .claude/close-gate.json"
    fail=1
  fi
fi
[ $fail -eq 0 ] && { echo "── close-gate PASS"; exit 0; } || { echo "── close-gate FAIL ($MODE)"; exit 1; }
```

`make` wiring:

```make
task-done:      ; @bash scripts/close-gate.sh task $(PHASE)
phase-done:     ; @bash scripts/close-gate.sh phase $(PHASE)
milestone-done: ; @bash scripts/close-gate.sh milestone $(PHASE)
test-gate:      ; @bash scripts/test-close-gate.sh $(PHASE)
```

---

## Evidence runner — `scripts/gen-test-evidence.sh`

Generates the test-evidence file. **Use this instead of writing the pipeline by hand.** The
manual incantation documented above — `{ close-gate.sh evidence-header; <test_command>; } | tee
<file>` — ends in a bare `tee`, and `tee` exits with **its own** status: a failing test command,
or a failing `evidence-header` step, still leaves `tee` returning 0 and a green-looking evidence
file written over whatever was there before. This runner closes that: it runs under `pipefail`
so the real exit status survives the pipe, writes to a temp file in the evidence file's own
directory, and replaces the real file **only on success** — so a failing run leaves a
pre-existing good evidence file completely untouched rather than truncated.

It is also the piece that resolves the two placeholders a declared `test_command` may carry,
`{EVIDENCE_FILE}` and `{SET}`, which is what lets one manifest entry serve both `task` and
`phase` evidence without a second key. Substitution is bash parameter expansion, never `sed` —
a path substituted through `sed` collides with its delimiter and backreference syntax.

`/init-harness` scaffolds this file and wires the manifest's `test_command` to match; an adopter
retrofitting an existing repo copies it in and switches their `test_command` to the placeholder
form shown under §Project manifest.

```bash
#!/usr/bin/env bash
# gen-test-evidence.sh — safe runner for the project's test-evidence file.
# Usage: gen-test-evidence.sh <task|phase>   (run from the repo root)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE="$HERE/close-gate.sh"
M=".claude/close-gate.json"

SET_MODE="${1:?usage: gen-test-evidence.sh <task|phase>}"
case "$SET_MODE" in
  task|phase) ;;
  *) echo "✗ set mode must be 'task' or 'phase' — got '$SET_MODE'"; exit 1 ;;
esac

[ -f "$M" ] || { echo "✗ missing manifest $M"; exit 1; }
EV="$(jq -r '.test_evidence // empty' "$M" 2>/dev/null)"
[ -n "$EV" ] || { echo "✗ manifest has no test_evidence path declared"; exit 1; }

# TEST-ONLY hook: run a different command instead of the manifest's declared one, so the
# refusal-on-failure behaviour can be demonstrated with a deliberately failing command without
# mutating the manifest. Never set this for a real evidence run.
if [ -n "${PLC_GEN_TEST_EVIDENCE_CMD_OVERRIDE:-}" ]; then
  EVCMD_TMPL="$PLC_GEN_TEST_EVIDENCE_CMD_OVERRIDE"
else
  EVCMD_TMPL="$(/bin/bash "$GATE" test-command)"
fi
[ -n "$EVCMD_TMPL" ] || { echo "✗ no test_command to run (declared value is empty)"; exit 1; }

# Report a genuine mkdir failure at its real cause rather than deferring to a less informative
# downstream error several steps later (a `tee` that cannot open a file in a missing directory).
EV_DIR="$(dirname "$EV")"
if ! MKDIR_ERR="$(mkdir -p "$EV_DIR" 2>&1)"; then
  echo "✗ could not create evidence directory $EV_DIR: ${MKDIR_ERR:-mkdir failed (permissions or quota?)}"
  exit 1
fi

# Same directory as the real evidence file, so the final `mv` is a same-filesystem rename —
# atomic, and never leaves the destination half-written.
TMP="$(mktemp "${EV}.XXXXXX")"
trap 'rm -f "$TMP"' EXIT

EVCMD="${EVCMD_TMPL//\{EVIDENCE_FILE\}/$TMP}"
EVCMD="${EVCMD//\{SET\}/$SET_MODE}"

# `-o pipefail` on the inner shell too: a fresh `bash -c` child does not inherit the parent's
# shell options, so without it the pipeline's status would again be the last command's.
set +e
/bin/bash -o pipefail -c "$EVCMD"
RC=$?
set -e

if [ "$RC" -eq 0 ]; then
  # A zero exit status is not the same claim as "an artifact the gate could accept". Both guards
  # below destroy VALID state while printing a ✓; neither can buy a green (the gate's test-evidence
  # row rejects both afterwards), so what is at stake is the last good evidence file plus a success
  # message that means its opposite.
  #
  # Read the first line with `read`, not `head -n1 | grep`: under `-o pipefail` a `grep -q` that
  # matches exits before `head` finishes writing, `head` takes SIGPIPE, and the pipeline's status
  # is 141. `case` needs no external command and no regex dialect.
  if [ ! -s "$TMP" ]; then
    echo "✗ gen-test-evidence: the command exited 0 but wrote nothing to {EVIDENCE_FILE} — $EV left unchanged. The declared test_command must write THROUGH the {EVIDENCE_FILE} placeholder (a runner that writes to its own report file instead produces exactly this)."
    exit 1
  fi
  IFS= read -r FIRSTLINE < "$TMP" || FIRSTLINE=""
  case "$FIRSTLINE" in
    '# plc-gate-evidence inputs=EMPTY-'*)
      # `evidence-header` emits an EMPTY-* sentinel INSTEAD of a digest, and exits 0, when
      # test_evidence_inputs matched no tracked file — deliberately, so the gate can reject it
      # loudly instead of fingerprinting nothing. The producer needs the matching refusal, or the
      # first run in a repo whose source is not committed yet (or whose layout is not `src/`
      # + `tests/`) overwrites good evidence with a file that cannot pass. Scoped to this sentinel
      # prefix, NOT to "the header is missing": an adopter who never opted into fingerprint mode
      # declares no test_evidence_inputs, calls no evidence-header, and their headerless evidence
      # must keep working.
      echo "✗ gen-test-evidence: the evidence header fingerprints nothing — the manifest's test_evidence_inputs matched no tracked files, so the gate will reject this file. $EV left unchanged. Fix the globs in $M (or \`git add\` the paths they name), then re-run."
      exit 1
      ;;
  esac
  mv -f "$TMP" "$EV"
  trap - EXIT
  echo "✓ evidence written: $EV (set=$SET_MODE)"
  exit 0
else
  echo "✗ gen-test-evidence: command exited $RC — evidence NOT written; $EV left unchanged"
  exit "$RC"
fi
```

## AC-oracle binding — `scripts/ac-evidence.sh`

The check the `ac-oracle-binding` rows above name. It reads the phase user story for the criterion
set, reads `.claude/ac-evidence.json` for what points at each one, and prints one line per
criterion. It deliberately prints **no ratio and no total** — a coverage number invites the reader
to treat 15/16 as nearly-done, when the one criterion nobody pointed at is the entire finding.

Copy it verbatim. The copy below is byte-identical to the one this skill ships and is held that
way by an invariant; if you edit it, you are forking it and the next skill update will not reach
your copy.

````bash
#!/bin/bash
# scripts/ac-evidence.sh — every acceptance criterion owns an oracle, or a written-down exclusion.
#
# This proves each criterion HAS an oracle. It never proves the oracle is correct, and an exclusion
# self-destructs only when its condition fails, never when its reasoning was wrong.
#
# Envelope: bash + jq + git ONLY. No python3, and no `shasum` either -- it is a perl
# script on macOS and would widen that envelope.
# Hashing, where this file needs it, goes through `git hash-object`.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST="${AC_MANIFEST:-$HERE/../.claude/close-gate.json}"

die() { printf '%s\n' "$*" >&2; exit 1; }

# The heading set is declared in the manifest so an adopter can extend it without editing the gate.
# Real user stories differ in this heading: `## Acceptance criteria`
# (lowercase c), a CJK heading (U+9A8C U+6536 U+6807 U+51C6), and
# `## Acceptance Criteria` all occur. A single literal would be blind to most of them.
heading_set() {
  if [ -r "$MANIFEST" ] && jq -e '.ac_heading_set' "$MANIFEST" >/dev/null 2>&1; then
    jq -r '.ac_heading_set[]' "$MANIFEST"
  else
    # The CJK heading is emitted as octal UTF-8, not as a literal, so this file carries no CJK bytes.
    # Verified byte-identical to the literal. `$'\uXXXX'` is NOT an option --
    # macOS /bin/bash is 3.2 and that syntax needs 4.2+.
    printf '%s\n' 'acceptance criteria' "$(printf '\351\252\214\346\224\266\346\240\207\345\207\206')"
  fi
}

# Print "<start-line> <end-line>" for the acceptance-criteria section, or die naming the heading set.
section_range() {
  local file="$1" h start level end
  start=""
  while IFS= read -r h; do
    # DO NOT use awk's `==` here. On macOS awk (version 20200816) string equality returns TRUE for
    # ANY two non-ASCII strings: comparing a story heading (U+6545 U+4E8B) with the
    # acceptance heading (U+9A8C U+6536 U+6807 U+51C6) prints EQUAL, while "foo" == "bar" prints
    # notequal. Under `==` this matcher locks onto the FIRST CJK heading in a file
    # instead of the real acceptance section.
    # `length()` plus `index()` compares bytes and is portable.
    start="$(awk -v want="$(printf '%s' "$h" | tr '[:upper:]' '[:lower:]')" '
      function same(a, b) { return (length(a) == length(b)) && (index(a, b) == 1) }
      /^#+[[:space:]]/ {
        line = tolower($0)
        sub(/^#+[[:space:]]*/, "", line)
        gsub(/[[:punct:]]+$/, "", line)
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", line)
        if (same(line, want)) { print NR; exit }
      }' "$file")"
    [ -n "$start" ] && break
  done < <(heading_set)

  # Section ABSENT is its own failure, distinct from section-empty. A missing section must never
  # read as "this phase has no criteria".
  [ -n "$start" ] || die "no acceptance-criteria section found in $file -- the heading set is: $(heading_set | tr '\n' '/')"

  level="$(awk -v n="$start" 'NR==n { match($0, /^#+/); print RLENGTH }' "$file")"
  end="$(awk -v n="$start" -v L="$level" '
    NR > n && /^#+[[:space:]]/ { match($0, /^#+/); if (RLENGTH <= L) { print NR; exit } }' "$file")"
  [ -n "$end" ] || end="$(( $(wc -l < "$file") + 1 ))"
  printf '%s %s\n' "$start" "$end"
}

# Closed section grammar: inside the acceptance-criteria section every line must be a recognised
# declaration, an indented continuation, a blank line, a fenced block or a blockquote. Anything else
# is a hard failure naming the line -- which turns `### AC3` and a table row from a SILENT
# under-count into a red, without the checker ever deciding what they mean.
parse_criteria() {
  local file="$1" phase="$2" range start end
  [ -r "$file" ] || die "story file is unreadable: $file"
  range="$(section_range "$file")"
  read -r start end <<<"$range"

  awk -v start="$start" -v end="$end" -v phase="$phase" '
    function emit(id, ln,   tok) {
      tok = id; sub(/:.*$/, "", tok)
      if (tok != phase) {
        printf "declaration at line %d carries phase token %s, expected %s\n", ln, tok, phase > "/dev/stderr"
        bad = 1; return
      }
      if (id in seen) {
        printf "duplicate id %s at lines %d and %d\n", id, seen[id], ln > "/dev/stderr"
        bad = 1; return
      }
      seen[id] = ln
      order[++n] = id
    }
    NR <= start || NR >= end { next }
    /^```/            { fence = !fence; next }
    fence             { next }
    /^[[:space:]]*>/  { next }   # blockquote
    /^[[:space:]]*$/  { next }   # blank
    /^[[:space:]]+/   { next }   # indented continuation of a declaration
    {
      line = $0
      # long form:  - **<phase>:AC3**:   or   - **<phase>:AC3** —
      if (match(line, /^- \*\*[A-Za-z0-9_.-]+:AC[0-9]+(\.[0-9]+)?[a-z]?\*\*[[:space:]]*([:—–])/)) {
        id = line; sub(/^- \*\*/, "", id); sub(/\*\*.*$/, "", id)
        emit(id, NR); next
      }
      # short form: - **AC3** {#<phase>:AC3}:   -- the human label, plus the
      # machine-visible scoped anchor.
      if (match(line, /^- \*\*AC[0-9]+(\.[0-9]+)?[a-z]?\*\*[[:space:]]*\{#[A-Za-z0-9_.-]+:AC[0-9]+(\.[0-9]+)?[a-z]?\}[[:space:]]*([:—–])/)) {
        label = line; sub(/^- \*\*/, "", label); sub(/\*\*.*$/, "", label)
        anchor = line; sub(/^[^{]*\{#/, "", anchor); sub(/\}.*$/, "", anchor)
        bare = anchor; sub(/^[^:]*:/, "", bare)
        if (bare != label) {
          printf "label/anchor mismatch at line %d: **%s** vs {#%s}\n", NR, label, anchor > "/dev/stderr"
          bad = 1; next
        }
        emit(anchor, NR); next
      }
      printf "unrecognised construct in the acceptance-criteria section, line %d: %s\n", NR, line > "/dev/stderr"
      bad = 1
    }
    END {
      if (bad) exit 1
      if (n == 0) { print "no declarations parsed from the acceptance-criteria section" > "/dev/stderr"; exit 1 }
      for (i = 1; i <= n; i++) print order[i]
    }
  ' "$file"
}

# The declaration line for one id plus every following indented continuation, whitespace-normalised.
# This is the digest preimage for the baseline (scripts/ac-baseline.sh). Full declaration, not the
# first line: criteria in real stories wrap across three and four lines, and hashing only
# the `- **id**:` line would let a one-word semantic inversion inside a continuation pass while a
# pure rewrap reds.
declaration_text() {
  local file="$1" id="$2" range start end
  [ -r "$file" ] || die "story file is unreadable: $file"
  range="$(section_range "$file")"
  read -r start end <<<"$range"
  awk -v start="$start" -v end="$end" -v id="$id" '
    NR <= start || NR >= end { next }
    /^- \*\*/ {
      want = (index($0, id) > 0)
      if (want) { inside = 1; buf = $0; next }
      if (inside) { exit }
      inside = 0; next
    }
    inside && /^[[:space:]]+/ { buf = buf " " $0; next }
    inside && /^[[:space:]]*$/ { next }
    inside { exit }
    END { if (buf != "") { gsub(/[[:space:]]+/, " ", buf); sub(/^ /, "", buf); sub(/ $/, "", buf); print buf } }
  ' "$file"
}

# Walk a covered_by_oracle chain. Returns 0 only when it terminates on a row whose status is
# `oracle` -- a chain that merely leaves the exclusion graph proves nothing. `seen` carries the path
# so a cycle is reported with its members instead of recursing forever.
#
# What this CANNOT see, stated because the neighbouring comment would otherwise over-claim: whether
# the terminal carrier actually asserts anything. That is a stated bound, not a hole to patch.
chain_terminates() {
  local id="$1" ev="$2" seen="${3:-}" row status next
  case " $seen " in *" $id "*) printf '%s -> %s\n' "${seen# }" "$id"; return 1 ;; esac
  row="$(jq -c --arg id "$id" '.criteria[]? | select(.id == $id)' "$ev")"
  [ -n "$row" ] || return 1
  status="$(jq -r '.status // ""' <<<"$row")"
  [ "$status" = "oracle" ] && return 0
  [ "$status" = "excluded" ] || return 1
  [ "$(jq -r '.exclusion.type // ""' <<<"$row")" = "covered_by_oracle" ] || return 1
  while IFS= read -r next; do
    [ -n "$next" ] || continue
    chain_terminates "$next" "$ev" "$seen $id" || return 1
  done < <(jq -r '.exclusion.condition.criteria_still_naming[]?' <<<"$row")
  return 0
}

# Validate one `status: excluded` row. Two types are BUILT; `certified_once` is specified in the
# format and deliberately not implemented (no criterion has needed that shape yet), and a row
# declaring it is routed to UNMAPPED rather than silently accepted or mis-reported as unknown.
# Everything malformed fails CLOSED -- explicitly against Snyk's precedent of honouring a malformed
# expiry forever.
exclusion_row() {
  local id="$1" row="$2" ev="$3" type names n path cyc
  type="$(jq -r '.exclusion.type // ""' <<<"$row")"
  case "$type" in
    covered_by_oracle)
      names="$(jq -r '.exclusion.condition.criteria_still_naming[]?' <<<"$row")"
      if [ -z "$names" ]; then
        printf '  %-12s UNMAPPED  malformed: covered_by_oracle with an empty criteria_still_naming\n' "$id"
        return 1
      fi
      while IFS= read -r n; do
        [ -n "$n" ] || continue
        if ! cyc="$(chain_terminates "$n" "$ev" "$id")"; then
          if [ -n "$cyc" ]; then
            printf '  %-12s UNMAPPED  cycle in covered_by_oracle: %s\n' "$id" "$cyc"
          else
            printf '  %-12s UNMAPPED  condition no longer holds: %s is not (or no longer reaches) an oracle\n' "$id" "$n"
          fi
          return 1
        fi
      done <<<"$names"
      printf '  %-12s excluded  %-14s condition holds\n' "$id" "$type"
      ;;
    ci_unreachable_carrier)
      path="$(jq -r '.exclusion.condition.path // ""' <<<"$row")"
      if [ -z "$path" ]; then
        printf '  %-12s UNMAPPED  malformed: ci_unreachable_carrier with no path\n' "$id"; return 1
      fi
      if [ ! -e "${AC_CARRIER_ROOT:-$HERE/..}/$path" ]; then
        # Environment-determined, and said so rather than blamed on the author: in CI a gitignored
        # path usually does not exist at all, so this condition can only be evaluated where the
        # tree is complete. Fail closed, but name the environment.
        printf '  %-12s UNMAPPED  condition unevaluable here (path absent): %s\n' "$id" "$path"; return 1
      fi
      if ! git -C "${AC_CARRIER_ROOT:-$HERE/..}" check-ignore -q "$path"; then
        printf '  %-12s UNMAPPED  condition no longer holds: %s is no longer gitignored, so a real carrier is possible\n' "$id" "$path"
        return 1
      fi
      printf '  %-12s excluded  %-14s condition holds\n' "$id" "$type"
      ;;
    certified_once)
      printf "  %-12s UNMAPPED  exclusion type 'certified_once' is specified but not implemented; this criterion is unmapped\n" "$id"
      return 1
      ;;
    *)
      printf '  %-12s UNMAPPED  malformed: unknown exclusion type %s\n' "$id" "${type:-<absent>}"
      return 1
      ;;
  esac
  return 0
}

# Reference discipline over the artifacts THIS PHASE creates.
#
# STAGED, and saying so is the point: four kinds of artifact carry criterion links -- test name, journal,
# review finding, evidence row. This checks ONE of them, and leaves two questions open:
# where the authority to grandfather REFERENCES comes from (the baseline grandfathers
# criteria, not references), and how a checker tells a claim from a quotation in an
# append-only record. A green row here does NOT mean a repo's test files are clean: they can
# still carry bare AC ids.
#
# A qualifier is `<token>:` only. `<token>-` would make ordinary prose qualify -- "the pre-AC10
# behaviour" reads as phase `pre`, and every hyphenated word becomes a namespace.
scan_refs() {
  local phase="$1" declared="$2" fail=0 file label val stripped tok
  shift 2
  while [ $# -gt 0 ]; do
    file="$1"; label="$2"; shift 2
    [ -n "$file" ] && [ -r "$file" ] || continue
    while IFS= read -r val; do
      [ -n "$val" ] || continue
      # Delete every QUALIFIED id first; anything of the shape AC<n> still standing is bare.
      stripped="$(printf '%s' "$val" | sed -E 's/[A-Za-z0-9_.-]+:AC[0-9]+(\.[0-9]+)?[a-z]?//g')"
      if printf '%s' "$stripped" | grep -qE '(^|[^A-Za-z0-9_])AC[0-9]'; then
        printf '  REFERENCE  bare AC id in %s (%s): %s\n' "$label" "$file" "$val"
        fail=1
      fi
      # A this-phase id the story does not declare is an ORPHAN, distinct from "unmapped".
      for tok in $(printf '%s' "$val" | grep -oE "$phase:AC[0-9]+(\.[0-9]+)?[a-z]?" || true); do
        if ! printf '%s\n' "$declared" | grep -qFx "$tok"; then
          printf '  %-12s ORPHAN    referenced in %s, but the current story declares no such criterion\n' "$tok" "$label"
          fail=1
        fi
      done
    done < <(jq -r '.criteria[]? | .id, (.why // empty), (.exclusion.why // empty)' "$file" 2>/dev/null || true)
  done
  return "$fail"
}

# Task-mode scope: the union of `Closes:` trailers on this branch. Branch-cumulative, because the
# gate is handed a PHASE and never a task id.
# Nothing unclaimed ever enters scope, which is the guarantee this scope gives.
#
# Two properties this carrier does NOT have, stated so nobody relies on them: trailers do not
# survive squash-merge, and the scope moves when the merge-base moves. The second is mitigated by
# disclosure only -- the computed merge-base is printed on every run.
scope_from_trailers() {
  local phase="$1" base="" mb raw tok out=""
  shift
  while [ $# -gt 0 ]; do
    case "$1" in
      --base) base="$2"; shift 2 ;;
      *) die "scope-from-trailers: unknown option $1" ;;
    esac
  done
  if [ -z "$base" ]; then
    base="$(git symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null || true)"
    [ -n "$base" ] || die "cannot determine the default branch: origin/HEAD is unset (a --single-branch clone or a fork remote does this). Pass --base <ref>, or run: git remote set-head origin -a"
  fi
  mb="$(git merge-base "$base" HEAD 2>/dev/null)" || die "no merge-base between $base and HEAD"
  printf 'scope computed from merge-base %s\n' "$mb" >&2

  raw="$(git log --format='%(trailers:key=Closes,valueonly)' "$mb..HEAD" | tr ' ' '\n' | sed '/^$/d')"
  [ -n "$raw" ] || return 0
  while IFS= read -r tok; do
    [ -n "$tok" ] || continue
    # THIS STEP TOKENISES AND NO LONGER JUDGES, and the reason is WHERE THE VERDICT IS READ.
    #
    # It used to classify here, with `case "$tok" in *:AC*)` -- a CONTAINMENT test -- and `die` for
    # anything else. Measured (while writing a commit): `Closes: p1:AC5,
    # p1:AC6` on one line tokenises through `tr ' ' '\n'`, which splits on spaces and NOT on
    # commas, so `p1:AC5,` reached the comparison with its comma attached, was accepted as a
    # well-formed id, matched nothing in the story, and was reported as
    # `ORPHAN  ...the current story declares no such criterion` -- a factual assertion about the
    # USER STORY. A comma in the author's own commit message was reported as a defect in a
    # different file.
    #
    # THE OBVIOUS FIX WAS ANCHORING THE GLOB HERE, AND IT MADE THINGS WORSE. Measured rather than
    # reasoned: `scripts/close-gate.sh:1348` invokes this step as
    #
    #     ... scope-from-trailers ... > "$AC_IDS" 2>/dev/null || : > "$AC_IDS"
    #
    # so a `die` is SWALLOWED **and the id file is truncated**. With an anchored glob here the
    # gate went from `ORPHAN -> report exits 1 -> RED` (wrong reason, right colour) to
    # `die -> swallowed -> empty scope -> report exits 0 printing "no criteria claimed by any
    # commit on this branch" -> GREEN`. A fix for a wrong message that turns a red into a
    # reassuring green is worse than the message it replaces.
    #
    # So the token TRAVELS, and `report` -- where verdicts live, and where the gate reads them --
    # names it. That move closes THREE silences, not one: this `die`, the swallow above, and
    # `report`'s own `case "$id" in "$phase":AC*) ;; *) continue ;;`, which dropped every
    # non-matching token without a word.
    #
    # WHAT DID NOT CHANGE: commas are still not separators. The convention is one `Closes:` per
    # line, and the requirement is the malformed VERDICT rather than a new accepted input
    # shape -- widening the parser would be a feature wearing a bug fix's clothes.
    out="$out$tok"$'\n'
  done <<<"$raw"
  printf '%s' "$out" | sort -u
}

DISCLAIMER_1="this proves each criterion HAS an oracle. It never proves the oracle is correct,"
DISCLAIMER_2="and an exclusion self-destructs only when its condition fails, never when its reasoning was wrong."

# Validate one `status: oracle` row. Prints its line; returns non-zero when the row is unmapped.
oracle_row() {
  local id="$1" row="$2" klass carrier path sym root
  klass="$(jq -r '.class // ""' <<<"$row")"
  case "$klass" in
    mutant-killed|tracked-suite|local-only|pin) ;;
    *) printf '  %-12s UNMAPPED  malformed: class %s\n' "$id" "${klass:-<absent>}"; return 1 ;;
  esac
  carrier="$(jq -r '.carrier // ""' <<<"$row")"
  path="${carrier%%::*}"
  sym=""
  case "$carrier" in *::*) sym="${carrier#*::}" ;; esac
  root="${AC_CARRIER_ROOT:-$HERE/..}"
  if [ -z "$path" ] || [ ! -e "$root/$path" ]; then
    printf '  %-12s UNMAPPED  carrier path does not exist: %s\n' "$id" "${path:-<absent>}"; return 1
  fi
  # Dangling-pointer check, NOT a quality judgement: a carrier naming a symbol that is no longer in
  # the file points at nothing. Without it, removing a guard cannot change any verdict and
  # a guard-removal test can never go red. Known false green: a mention in a comment satisfies
  # a plain string match. Still strictly stronger than path-existence.
  if [ -n "$sym" ] && ! grep -qF -- "$sym" "$root/$path"; then
    printf '  %-12s UNMAPPED  carrier names %s, which is not in %s\n' "$id" "$sym" "$path"; return 1
  fi
  printf '  %-12s oracle    %-14s %s\n' "$id" "$klass" "$carrier"
  return 0
}

# One row per criterion in scope. Exit 0 only when every one of them is mapped.
report() {
  local story="" phase="" ev="" ids_file="" baseline="" fail=0 declared scope id row status why
  story="${1:?report: <story> <phase>}"; phase="${2:?report: <story> <phase>}"; shift 2
  while [ $# -gt 0 ]; do
    case "$1" in
      --evidence) ev="$2"; shift 2 ;;
      --ids)      ids_file="$2"; shift 2 ;;
      --baseline) baseline="$2"; shift 2 ;;
      *) die "report: unknown option $1" ;;
    esac
  done
  [ -n "$ev" ] || ev="$(jq -r '.ac_evidence // ".claude/ac-evidence.json"' "$MANIFEST")"

  # A top-level parse failure is reported ONCE as a broken file. Reporting it as "every criterion is
  # unmapped" reads as catastrophe and sends the reader to write evidence instead of fix a comma.
  jq -e . "$ev" >/dev/null 2>&1 || die "evidence file is unreadable or not valid JSON: $ev -- nothing about individual criteria can be concluded from this"

  declared="$(parse_criteria "$story" "$phase")"

  printf 'ac-oracle-binding  phase %s\n' "$phase"
  # The scope line names WHERE the scope came from, never how big it is, and it differs
  # per mode: saying "the declared set" while checking a trailer-derived set would be misleading,
  # and printing nothing for an empty task scope is the empty-set-guard shape.
  if [ -n "$ids_file" ]; then
    if [ -s "$ids_file" ]; then
      printf '  scope: the criteria this branch declares it closes (merge-base %s)\n' "${AC_MERGE_BASE:-unknown}"
    else
      printf '  scope: no criteria claimed by any commit on this branch\n'
    fi
    # An id a commit CLAIMS that the story does not declare must be reported. The intersection
    # below would silently drop it, and an unclaimed id must be reported distinctly.
    # THREE VERDICTS, AND THE ORDER IS THE POINT.
    #
    # The grammar is checked BEFORE the phase filter. That filter used to be the first thing a
    # token met -- `case "$id" in "$phase":AC*) ;; *) continue ;;` -- so a token that was not a
    # well-formed id of this phase was DROPPED WITHOUT A WORD. Combined with the tokeniser
    # `die`ing upstream and the gate swallowing that `die`, a comma in a `Closes:` trailer had
    # three separate ways to end in silence.
    #
    # MALFORMED is a verdict about the COMMIT MESSAGE. ORPHAN is a claim about the USER STORY.
    # Both are red, and the distinction exists because the gate printed the second when the first was true,
    # sending the reader to the wrong file. The grammar is the one this file already applies at
    # the story end, so the two sides of the comparison cannot disagree about what an id IS.
    #
    # `#NNN` keeps its own sentence rather than folding into MALFORMED: `Closes: #NNN` is
    # habitual forge idiom and this repository files backlog items under its own ids, so the reader needs
    # to be told it is the WRONG KIND of reference, not a typo.
    while IFS= read -r id; do
      [ -n "$id" ] || continue
      case "$id" in
        '#'*)
          printf '  %-12s MALFORMED names an issue, not an acceptance criterion -- use `Refs:` for issues\n' "$id"
          fail=1; continue ;;
      esac
      if ! printf '%s' "$id" | grep -qE '^[A-Za-z0-9_.-]+:AC[0-9]+(\.[0-9]+)?[a-z]?$'; then
        printf '  %-12s MALFORMED not a bare criterion id; expected <phase>:AC<n>[.<n>][a-z], one `Closes:` per line, space-separated within a line -- a trailing comma is part of the token\n' "$id"
        fail=1; continue
      fi
      # Another phase's well-formed id is not this phase's business, and is not an error.
      case "$id" in "$phase":AC*) ;; *) continue ;; esac
      if ! grep -qFx "$id" <<<"$declared"; then
        printf '  %-12s ORPHAN    claimed by a `Closes:` trailer, but the current story declares no such criterion\n' "$id"
        fail=1
      fi
    done < "$ids_file"
    scope="$(grep -Fxf "$ids_file" <<<"$declared" || true)"
  else
    printf '  scope: the declared set of %s\n' "$story"
    scope="$declared"
  fi

  # Reference discipline across the artifacts this phase creates: bare ids fail, this-phase ids the
  # story does not declare are ORPHANS (distinct from "unmapped" -- two mistakes, two messages).
  scan_refs "$phase" "$declared" "$ev" "evidence row" ${baseline:+"$baseline" "baseline entry"} || fail=1

  while IFS= read -r id; do
    [ -n "$id" ] || continue
    row="$(jq -c --arg id "$id" '.criteria[]? | select(.id == $id)' "$ev")"
    if [ -z "$row" ]; then
      baselined_row "$id" "$baseline" "$story" || fail=1
      continue
    fi
    why="$(jq -r '.why // .exclusion.why // ""' <<<"$row")"
    if [ -z "$why" ]; then
      printf '  %-12s UNMAPPED  malformed: row has no `why`\n' "$id"; fail=1; continue
    fi
    status="$(jq -r '.status // ""' <<<"$row")"
    case "$status" in
      oracle)   oracle_row "$id" "$row" || fail=1 ;;
      excluded) exclusion_row "$id" "$row" "$ev" || fail=1 ;;
      *)        printf '  %-12s UNMAPPED  malformed: status %s\n' "$id" "${status:-<absent>}"; fail=1 ;;
    esac
  done <<<"$scope"

  baseline_rows "$baseline" || true
  printf '  %s\n  %s\n' "$DISCLAIMER_1" "$DISCLAIMER_2"
  return "$fail"
}

# The dispatcher lists every arm, so a new arm adds a FUNCTION above it and never
# has to touch this block. An un-implemented arm dies with a clear message.
not_yet() { die "$1: not implemented until its task lands"; }
# A criterion with no evidence row is UNMAPPED unless the baseline grandfathers it -- and a
# grandfathered entry loses its protection the moment its declaration TEXT changes, which is what
# makes the scoping "new-or-CHANGED" rather than merely "new". Cross-phase entries carry a null
# digest (their story is unreadable here), so change detection is current-phase-only; that hole is
# real and is stated here.
baselined_row() {
  local id="$1" baseline="$2" story="$3" entry want have
  if [ -z "$baseline" ] || [ ! -r "$baseline" ]; then
    printf '  %-12s UNMAPPED  no evidence row\n' "$id"; return 1
  fi
  entry="$(jq -c --arg id "$id" '.criteria[]? | select(.id == $id)' "$baseline")"
  if [ -z "$entry" ]; then
    printf '  %-12s UNMAPPED  no evidence row\n' "$id"; return 1
  fi
  want="$(jq -r '.digest // ""' <<<"$entry")"
  if [ -n "$want" ]; then
    # Byte-for-byte the same preimage as scripts/ac-baseline.sh's declaration_digest: `printf %s`,
    # no trailing newline. Measured: the pipeline form appends one and the two digests then never
    # match, so a freshly-added entry reads as CHANGED on the very next run. Two code paths
    # computing "the same" digest differently is the encoder-divergence class.
    have="$(printf '%s' "$(declaration_text "$story" "$id" 2>/dev/null)" | git hash-object --stdin)"
    if [ "$want" != "$have" ]; then
      printf '  %-12s UNMAPPED  baselined, but its declaration has CHANGED since it was grandfathered -- it needs an oracle now\n' "$id"
      return 1
    fi
  fi
  printf '  %-12s baselined grandfathered   %s\n' "$id" "$(jq -r '.why' <<<"$entry")"
  return 0
}

# Nothing forces the baseline to shrink. Printing what remains on every run is the whole mitigation.
baseline_rows() {
  local baseline="$1" id
  [ -n "$baseline" ] && [ -r "$baseline" ] || return 0
  while IFS= read -r id; do
    [ -n "$id" ] || continue
    printf '  baseline: %s (explicit action required to add; removals automatic at phase close)\n' "$id"
  done < <(jq -r '.criteria[]?.id // empty' "$baseline")
  return 0
}

case "${1:-}" in
  parse-criteria)      shift; parse_criteria "$@" ;;
  declaration-text)    shift; declaration_text "$@" ;;
  report)              shift; report "$@" ;;
  scope-from-trailers) shift; scope_from_trailers "$@" ;;
  scan-refs)           shift; scan_refs "$@" ;;
  *) die "usage: ac-evidence.sh <parse-criteria|declaration-text|report|scope-from-trailers|scan-refs> ..." ;;
esac
````

## AC baseline — `scripts/ac-baseline.sh`

Grandfathering, so adopting the check on an existing project is not a wall of red. The asymmetry
is the point: an entry leaves the baseline **automatically** the moment its criterion gets an
oracle, and entering it is a **named, deliberate act**. Nothing forces the baseline to shrink; it
is printed every run and that is all.

Byte-identical to the shipped script, same as above.

````bash
#!/bin/bash
# scripts/ac-baseline.sh -- the two named actions on the AC baseline, and its guard digest.
#
# Asymmetry is the point: REMOVAL is automatic and happens at phase close, ADDITION
# requires this tool. A hand-edited entry leaves the guard stale and the gate fails naming it.
#
# The guard is a DIGEST, not a signature. There is no secret, so anyone can recompute it by hand and
# bless new debt as old debt. That is the intended design -- adding must be an explicit, named
# ACTION, not impossible -- and this tool never claims to be tamper-proof. What a reviewer cannot
# tell from a green gate is `ac-baseline.sh add` from a hand-edit plus a recompute; that residual is
# stated here rather than papered over.
#
# Envelope: bash + jq + git ONLY. Hashing is `git hash-object`, NOT `shasum` -- shasum is a perl
# script on macOS and would widen that envelope; `git hash-object` is content-addressed and
# already inside it.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
die() { printf '%s\n' "$*" >&2; exit 1; }

sha() { git hash-object --stdin; }
guard_of() { jq -S -c '.criteria' "$1" | sha; }

# Digest of a criterion's FULL declaration, or empty when this story does not declare it (which is
# the normal case for a cross-phase id). The empty case is guarded EXPLICITLY: piping nothing into a
# hasher yields the hash of the empty string, which is non-empty, so a cross-phase entry would get a
# bogus digest instead of null and then lose its baseline protection on the next run for no reason.
declaration_digest() {
  local story="$1" id="$2" text
  [ -n "$story" ] && [ -r "$story" ] || return 1
  text="$("$HERE/ac-evidence.sh" declaration-text "$story" "$id" 2>/dev/null)" || return 1
  [ -n "$text" ] || return 1
  printf '%s' "$text" | sha
}

cmd_init() {
  local f="$1"
  [ -e "$f" ] && die "refusing to overwrite an existing baseline: $f"
  printf '{\n  "criteria": [],\n  "guard": ""\n}\n' > "$f"
  jq --arg g "$(guard_of "$f")" '.guard = $g' "$f" > "$f.tmp" && mv "$f.tmp" "$f"
}

cmd_verify() {
  local f="$1" want have
  jq -e . "$f" >/dev/null 2>&1 || die "baseline is unreadable or not valid JSON: $f"
  want="$(jq -r '.guard // ""' "$f")"
  have="$(guard_of "$f")"
  [ "$want" = "$have" ] && return 0
  printf 'baseline guard is STALE -- an entry was added or edited without `ac-baseline.sh add`.\n' >&2
  jq -r '.criteria[] | select(.action != "scripts/ac-baseline.sh add") | "  suspect entry: \(.id) (action: \(.action))"' "$f" >&2
  printf '  expected guard %s, the file says %s\n' "$have" "$want" >&2
  return 1
}

cmd_add() {
  local f="$1" id="$2" why="$3" story="${4:-}" digest d
  # Verify BEFORE mutating. The other order would recompute the guard over a set that also holds a
  # hand-added entry, laundering it in the same run.
  cmd_verify "$f" || die "refusing to add on top of a stale guard -- resolve that first"
  digest="null"
  if [ -n "$story" ] && d="$(declaration_digest "$story" "$id")" && [ -n "$d" ]; then
    digest="\"$d\""
  fi
  jq --arg id "$id" --arg why "$why" --arg d "$(date -u +%Y-%m-%d)" --argjson dg "$digest" \
     '.criteria += [{id: $id, digest: $dg, added: $d, action: "scripts/ac-baseline.sh add", why: $why}]' \
     "$f" > "$f.tmp" && mv "$f.tmp" "$f"
  jq --arg g "$(guard_of "$f")" '.guard = $g' "$f" > "$f.tmp" && mv "$f.tmp" "$f"
}

cmd_prune() {
  local f="$1" ev="$2" id removed=0
  cmd_verify "$f" || die "refusing to prune on a stale guard -- that would launder a hand-added entry"
  jq -e . "$ev" >/dev/null 2>&1 || die "evidence file is unreadable: $ev"
  while IFS= read -r id; do
    [ -n "$id" ] || continue
    if jq -e --arg id "$id" '.criteria[]? | select(.id == $id)' "$ev" >/dev/null 2>&1; then
      printf 'baseline: removed %s -- it now has an evidence row\n' "$id"
      jq --arg id "$id" '.criteria |= map(select(.id != $id))' "$f" > "$f.tmp" && mv "$f.tmp" "$f"
      removed=1
    fi
  done < <(jq -r '.criteria[].id' "$f")
  if [ "$removed" = 1 ]; then
    jq --arg g "$(guard_of "$f")" '.guard = $g' "$f" > "$f.tmp" && mv "$f.tmp" "$f"
  fi
  return 0
}

FILE=".claude/ac-baseline.json"; STORY=""; EV=""; WHY=""; HAVE_WHY=0
SUB="${1:-}"; shift || true
POS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --file)     FILE="$2"; shift 2 ;;
    --story)    STORY="$2"; shift 2 ;;
    --evidence) EV="$2"; shift 2 ;;
    --why)      WHY="$2"; HAVE_WHY=1; shift 2 ;;
    -*)         die "unknown option $1" ;;
    *)          POS[${#POS[@]}]="$1"; shift ;;
  esac
done

case "$SUB" in
  init)   cmd_init "$FILE" ;;
  verify) cmd_verify "$FILE" ;;
  add)
    [ "${#POS[@]}" -ge 1 ] || die "add requires a criterion id"
    [ "$HAVE_WHY" = 1 ] && [ -n "$WHY" ] || die "add requires --why <reason>: an entry with no stated reason is the rot this baseline exists to make visible"
    cmd_add "$FILE" "${POS[0]}" "$WHY" "$STORY"
    ;;
  prune)
    [ -n "$EV" ] || die "prune requires --evidence <path>"
    cmd_prune "$FILE" "$EV"
    ;;
  *) die "usage: ac-baseline.sh init|verify|add <id> --why <reason>|prune --evidence <path> [--file F] [--story S]" ;;
esac
````

## Self-test — `scripts/test-close-gate.sh`

The gate is a bash script, so it can silently rot (a grep that never matches passes everything; a check wired to the wrong path always ✓). This self-test proves each check actually flips: it stands up a **throwaway detached git worktree** (real working tree never touched), then for every check removes/mangles the artifact and asserts the gate emits ✗, plus a baseline that asserts ✓ when all artifacts are present. Manifest-driven — no project-specific paths baked in. Run `make test-gate PHASE=X.Y` (or `bash scripts/test-close-gate.sh X.Y`) after editing the gate or the manifest.

```bash
#!/usr/bin/env bash
# Self-test for scripts/close-gate.sh — verifies each gate check emits ✗ when its artifact is
# missing and ✓ when present. Manifest-driven (reads .claude/close-gate.json); runs in a throwaway
# DETACHED git worktree so the real working tree is never touched.
# Usage: scripts/test-close-gate.sh <PHASE>     e.g.  scripts/test-close-gate.sh 1.1
set -uo pipefail
PHASE="${1:?usage: test-close-gate.sh <PHASE>}"
ROOT="$(git rev-parse --show-toplevel)"
M="$ROOT/.claude/close-gate.json"; [ -f "$M" ] || { echo "✗ missing $M"; exit 1; }
g() { jq -r ".$1 // empty" "$M" | sed "s/{PHASE}/$PHASE/g"; }
sedi() { sed -i '' "$@" 2>/dev/null || sed -i "$@"; }   # portable in-place sed (GNU vs BSD)
TMP="$(mktemp -d)"; WT="$TMP/wt"
cleanup() { git -C "$ROOT" worktree remove --force "$WT" >/dev/null 2>&1 || true
            git -C "$ROOT" worktree remove --force "$TMP/wt2" >/dev/null 2>&1 || true; rm -rf "$TMP"; }
trap cleanup EXIT
git -C "$ROOT" worktree add --quiet --detach "$WT" HEAD
cd "$WT"
mkdir -p "$(dirname "$(g test_evidence)")"; echo "test-run output" > "$(g test_evidence)"   # evidence is gitignored → absent in fresh worktree

pass=0; failc=0
run()     { bash scripts/close-gate.sh "$@" 2>&1 || true; }
neg()     { local d="$1" re="$2"; shift 2; if run "$@" | grep -qE "$re"; then echo "  ✓ NEG  $d"; pass=$((pass+1)); else echo "  ✗ NEG  $d — expected /$re/"; failc=$((failc+1)); fi; }
pos()     { local d="$1"; shift; if bash scripts/close-gate.sh "$@" >/dev/null 2>&1; then echo "  ✓ POS  $d"; pass=$((pass+1)); else echo "  ✗ POS  $d — gate failed unexpectedly"; failc=$((failc+1)); fi; }
# journal fragment dir — resolved once (journal_dir never changes mid-run); used by restore()'s
# hermetic cleanup below. `|| true` + the `${JD_RESTORE:-…}` default keep it safe under set -u/pipefail
# even when the manifest omits the key (falls back to the convention default docs/journal.d).
JD_RESTORE="$(g retention.journal_dir 2>/dev/null || true)"; JD_RESTORE="${JD_RESTORE:-docs/journal.d}"
restore() { git checkout --quiet -- . 2>/dev/null || true; git clean -fdq 2>/dev/null || true
            # hermetic guarantee (structural, order-independent): drop the journal fragment dir
            # AFTER the checkout. It is the one tracked fixture whose RESURRECTION corrupts a LATER
            # test — when a fragment is present the gate prefers the freshest-mtime fragment over the
            # monolith, so a checkout-restored fragment would shadow the monolith that the task-mode
            # journal assertions mangle. No test needs a *committed* fragment present (the fragment
            # tests build their own as untracked working-tree files, cleared by `git clean` above),
            # so removing it here unconditionally makes every test block hermetic regardless of order.
            # Mirrors the RESUME.md explicit-cleanup precedent — the inverse direction: there restore()
            # fails to remove a gitignored file, here it wrongly restores a committed one.
            rm -rf "$JD_RESTORE" 2>/dev/null || true
            echo "test-run output" > "$(g test_evidence)"; }

echo "── baseline ──"
pos "phase-done passes with all artifacts" phase "$PHASE"

echo "── phase-mode missing-artifact fail-paths ──"
rm -f $(g phase_docs_glob)*user-story* ;  neg "missing user-story"  'no user-story'  phase "$PHASE"; restore
rm -f $(g plan_glob) ;                    neg "missing plan doc"    'no plan doc'    phase "$PHASE"; restore
# NOTE: no handoff-doc fail-path here — the handoff file was retired and
# phase mode no longer checks for it; see close-gate.sh's phase-mode branch comment.
rm -f $(g smoke_a_glob) ;                 neg "missing Track A smoke" 'no Track A'   phase "$PHASE"; restore
[ -n "$(g smoke_b_glob)" ] && { rm -f $(g smoke_b_glob); neg "missing Track B e2e" 'no Track B' phase "$PHASE"; restore; }
rm -f $(g phase_docs_glob) ;              neg "missing spec doc (all phase docs gone)" 'no spec doc' phase "$PHASE"; restore
[ -n "$(g test_command)" ] && { rm -f "$(g test_evidence)"; neg "phase: stale/missing test-evidence" 'stale/missing test-evidence' phase "$PHASE"; restore; }
[ -n "$(g test_command)" ] && { printf '' > "$(g test_evidence)"; neg "phase: empty-but-fresh test-evidence rejected (-s)" 'stale/missing test-evidence' phase "$PHASE"; restore; }
# missing acceptance tests
rm -f $(g acceptance_glob) ; neg "missing acceptance tests" 'no acceptance tests for phase' phase "$PHASE"; restore
# test_runs_required in phase mode
[ -n "$(g test_command)" ] && {
  tmp=$(mktemp); jq '.test_runs_required=3' "$M" > "$tmp" && mv "$tmp" .claude/close-gate.json
  echo "test-run output" > "$(g test_evidence)"  # fresh but no RUNS= marker
  neg "phase: test_runs_required=3, evidence has no RUNS line" 'RUNS=0 < required 3' phase "$PHASE"
  printf 'RUNS=3\n' >> "$(g test_evidence)"
  pos "phase: test_runs_required=3, RUNS=3 present" phase "$PHASE"
  restore
}

echo "── diff-range checks (CHANGELOG / ROADMAP / journal touched) — tested at an empty range ──"
WT2="$TMP/wt2"
if git -C "$ROOT" worktree add --quiet --detach "$WT2" origin/main 2>/dev/null; then
  mkdir -p "$WT2/scripts" "$WT2/.claude"; cp scripts/close-gate.sh "$WT2/scripts/"; cp "$M" "$WT2/.claude/close-gate.json"
  o="$(cd "$WT2" && bash scripts/close-gate.sh phase "$PHASE" 2>&1 || true)"
  grep -qE 'CHANGELOG.md not touched' <<<"$o" && { echo "  ✓ NEG  CHANGELOG not touched (empty range)"; pass=$((pass+1)); } || { echo "  ✗ NEG  CHANGELOG not-touched path"; failc=$((failc+1)); }
  grep -qE 'ROADMAP.md not updated'   <<<"$o" && { echo "  ✓ NEG  ROADMAP not touched (empty range)";   pass=$((pass+1)); } || { echo "  ✗ NEG  ROADMAP not-updated path"; failc=$((failc+1)); }
  grep -qE 'journal not touched in'   <<<"$o" && { echo "  ✓ NEG  journal not touched (empty range)";   pass=$((pass+1)); } || { echo "  ✗ NEG  journal not-touched path"; failc=$((failc+1)); }
  git -C "$ROOT" worktree remove --force "$WT2" >/dev/null 2>&1 || true
else echo "  ⚠ SKIP diff-range test (could not create origin/main worktree)"; fi

echo "── SKIP escape-hatch (exempt flag requires a logged SKIP) ──"
tmp=$(mktemp); jq '.exempt_user_story=true' "$M" > "$tmp" && mv "$tmp" .claude/close-gate.json
rm -f $(g phase_docs_glob)*user-story*
neg "exempt_user_story=true + no SKIP line"  "exempt_user_story=true but no 'SKIP:'"  phase "$PHASE"
printf '\nSKIP: user-story intentionally omitted (self-test)\n' >> "$(g journal)"
pos "exempt_user_story=true + SKIP logged"   phase "$PHASE"
restore

echo "── exempt_changelog escape-hatch (requires a logged SKIP) ──"
tmp=$(mktemp); jq '.exempt_changelog=true' "$M" > "$tmp" && mv "$tmp" .claude/close-gate.json
neg "exempt_changelog=true + no SKIP line"  "exempt_changelog=true but no 'SKIP:'"  phase "$PHASE"
restore

echo "── context-floor arming row (warn-only — THREE states, must NEVER fail the gate) ──"
# The three states' discriminators. No marker may be a substring of another state's row: the old
# predicate here was a bare `context-floor hook wired`, which ALSO matches the inert row
# (`…wired but inert…`) — a check that cannot tell two states apart while looking like one that
# can, which is the blur the three-state contract forbids. So the wired marker carries its parenthetical and the
# inert marker carries `but inert`, and each state is asserted to exclude the other two rather
# than merely to contain its own.
FLOOR_NOT_WIRED='context-floor hook not wired'
FLOOR_WIRED='context-floor hook wired (settings reference context-floor.sh)'
FLOOR_INERT='context-floor hook wired but inert'
FLOOR_SETTINGS='{"hooks":{"PreToolUse":[{"matcher":"Edit|Write","hooks":[{"type":"command","command":"/path/to/context-floor.sh"}]}]}}'
FH="$TMP/fakehome"; mkdir -p "$FH"   # isolate from the real ~/.claude/settings.json
o="$(HOME="$FH" bash scripts/close-gate.sh phase "$PHASE" 2>&1)"; rc=$?
if grep -qF "$FLOOR_NOT_WIRED" <<<"$o" && ! grep -qF "$FLOOR_WIRED" <<<"$o" && ! grep -qF "$FLOOR_INERT" <<<"$o" && [ "$rc" -eq 0 ]; then echo "  ✓ NEG  un-armed floor warns (state 1 alone) without failing the gate"; pass=$((pass+1)); else echo "  ✗ NEG  un-armed floor warn row (rc=$rc)"; failc=$((failc+1)); fi
printf '%s\n' "$FLOOR_SETTINGS" > .claude/settings.json
# capture-then-grep, herestring not a pipe: piping the gate straight into grep -q
# makes grep's early exit SIGPIPE the still-writing gate (exit 141), and pipefail
# surfaces 141 over grep's 0 — the direct-pipe assertion failed 100% of the time.
o="$(HOME="$FH" bash scripts/close-gate.sh phase "$PHASE" 2>&1 || true)"
if grep -qF "$FLOOR_WIRED" <<<"$o" && ! grep -qF "$FLOOR_NOT_WIRED" <<<"$o" && ! grep -qF "$FLOOR_INERT" <<<"$o"; then echo "  ✓ POS  armed floor prints the wired row and no other state"; pass=$((pass+1)); else echo "  ✗ POS  armed floor wired row"; failc=$((failc+1)); fi
rm -f .claude/settings.json; restore
# State 3 (wired but inert) is NOT reachable by running the gate, and that is a fact about the
# gate rather than a limitation of this harness: the gate reads its manifest through `jq` long
# before this row runs, so a machine where `command -v jq` fails kills it at the first `g` call
# with rc 127 and no row prints at all. (Nor does the other direction help: the stripped-PATH GUI
# client this warning is ABOUT leaves the gate itself able to resolve jq, so that world prints the
# ✓ wired row and the HOOK is the inert one.) The branch is a contract for gates that CAN reach
# it, so the only honest way to exercise it is to run the row's OWN BYTES, extracted from the
# gate and never re-typed, under a PATH that has grep and no jq. A hand-written copy of the row
# here would be a second implementation certifying itself.
FR="$TMP/floor-row.sh"
{ echo 'set -euo pipefail'; grep -E '^(ok|warn)\(\)' scripts/close-gate.sh
  sed -n '/^floor_arming_row() {/,/^}/p' scripts/close-gate.sh; echo 'floor_arming_row'; } > "$FR"
FB="$TMP/floor-bin"; mkdir -p "$FB"; ln -sf "$(command -v grep)" "$FB/grep"
# bash resolved BEFORE the PATH is narrowed: `PATH=… bash …` searches the NEW PATH for bash
# itself, and $FB deliberately holds nothing but grep.
FBASH="$(command -v bash)"
FW="$TMP/floor-wt"; mkdir -p "$FW/.claude"; printf '%s\n' "$FLOOR_SETTINGS" > "$FW/.claude/settings.json"
o="$(cd "$FW" && HOME="$FH" PATH="$FB" "$FBASH" "$FR" 2>&1)"; rc=$?
if grep -qF "$FLOOR_INERT" <<<"$o" && ! grep -qF "$FLOOR_WIRED" <<<"$o" && ! grep -qF "$FLOOR_NOT_WIRED" <<<"$o" && [ "$rc" -eq 0 ]; then echo "  ✓ NEG  wired-but-inert floor warns (state 3 alone) without failing"; pass=$((pass+1)); else echo "  ✗ NEG  wired-but-inert floor row (rc=$rc) — got: $o"; failc=$((failc+1)); fi

echo "── retention hot-cap rows (warn-only — must NEVER fail the gate) ──"
# NEG: over-cap RESUME warns without failing (first close — also seeds retention-state.json)
python3 -c "print('x\n'*250)" > RESUME.md
o="$(bash scripts/close-gate.sh phase "$PHASE" 2>&1)"; rc=$?
grep -q 'RESUME.md over hot cap' <<<"$o" && [ "$rc" -eq 0 ] \
  && { echo "  ✓ NEG  over-cap doc warns without failing"; pass=$((pass+1)); } \
  || { echo "  ✗ NEG  over-cap doc warn row (rc=$rc)"; failc=$((failc+1)); }
# The SAME doc still over-cap at the second consecutive close escalates the wording
o="$(bash scripts/close-gate.sh phase "$PHASE" 2>&1)"; rc=$?
grep -q 'SECOND consecutive over-cap close' <<<"$o" && [ "$rc" -eq 0 ] \
  && { echo "  ✓ NEG  second consecutive close escalates wording"; pass=$((pass+1)); } \
  || { echo "  ✗ NEG  escalation wording (rc=$rc)"; failc=$((failc+1)); }
# explicit fixture cleanup: RESUME.md is gitignored in many projects, and restore()'s
# `git clean` (no -x) skips ignored files — the fixture would leak into the POS below
rm -f RESUME.md .claude/retention-state.json
restore
# POS: under-cap (or absent) doc → no row
o="$(bash scripts/close-gate.sh phase "$PHASE" 2>&1)"
grep -q 'RESUME.md over hot cap' <<<"$o" \
  && { echo "  ✗ POS  false-positive cap row"; failc=$((failc+1)); } \
  || { echo "  ✓ POS  under-cap doc silent"; pass=$((pass+1)); }
restore
# NEG: status-doc row fires (regression guard — a dead `|| echo` fallback once made this row
# silently never run for any project; the row must be exercised, not assumed)
SDOC="$(jq -r '.status_doc // "docs/STATUS.md"' "$M")"
mkdir -p "$(dirname "$SDOC")"
python3 -c "print('x\n'*350)" > "$SDOC"
o="$(bash scripts/close-gate.sh phase "$PHASE" 2>&1)"; rc=$?
grep -q 'status doc over hot cap' <<<"$o" && [ "$rc" -eq 0 ] \
  && { echo "  ✓ NEG  over-cap status doc warns without failing"; pass=$((pass+1)); } \
  || { echo "  ✗ NEG  status-doc cap row (rc=$rc)"; failc=$((failc+1)); }
rm -f "$SDOC" .claude/retention-state.json
restore
# POS: hot_caps.journal_hot: "none" exempts the directory total (exemption must work
# uniformly across file caps AND the dir cap)
tmp=$(mktemp); jq '.retention.hot_caps.journal_hot="none"' "$M" > "$tmp" && mv "$tmp" .claude/close-gate.json
mkdir -p docs/journal.d
python3 -c "print('x'*120000)" > docs/journal.d/big-fragment.md
o="$(bash scripts/close-gate.sh phase "$PHASE" 2>&1)"; rc=$?
grep -q 'journal hot zone exempt' <<<"$o" && ! grep -q 'journal hot zone over' <<<"$o" && [ "$rc" -eq 0 ] \
  && { echo "  ✓ POS  journal_hot: none exempts the dir cap"; pass=$((pass+1)); } \
  || { echo "  ✗ POS  journal_hot none exemption (rc=$rc)"; failc=$((failc+1)); }
rm -rf docs/journal.d .claude/retention-state.json
restore
# POS: qa-log.d dir-total cap fires ADDITIONALLY to the monolith file cap tested above —
# same warn/never-fail discipline, own state-key ($QD, not the monolith path)
mkdir -p docs/qa-log.d
python3 -c "print('x'*61440)" > docs/qa-log.d/big-fragment.md
o="$(bash scripts/close-gate.sh phase "$PHASE" 2>&1)"; rc=$?
grep -q 'qa-log hot zone over hot cap' <<<"$o" && [ "$rc" -eq 0 ] \
  && { echo "  ✓ NEG  qa-log.d dir-total over cap warns without failing"; pass=$((pass+1)); } \
  || { echo "  ✗ NEG  qa-log.d dir-total cap row (rc=$rc)"; failc=$((failc+1)); }
rm -rf docs/qa-log.d .claude/retention-state.json
restore
# qa-log citation coverage (warn-only — surfaces a locked decision with no source URL, never fails)
# NEG: a **Locked:** section with no http URL warns, gate stays rc 0
mkdir -p docs/qa-log.d
printf '### Q1: export format — 2026-07-11\n**Locked:** Excel\n**User decision:** Excel (no research done)\n' > docs/qa-log.d/uncited.md
o="$(bash scripts/close-gate.sh phase "$PHASE" 2>&1)"; rc=$?
grep -q 'locked decision with no citation URL' <<<"$o" && [ "$rc" -eq 0 ] \
  && { echo "  ✓ NEG  uncited locked decision surfaces (warn-only)"; pass=$((pass+1)); } \
  || { echo "  ✗ NEG  qa-log citation row (rc=$rc)"; failc=$((failc+1)); }
rm -rf docs/qa-log.d; restore
# POS: a **Locked:** section that cites a URL is silent (no false positive)
mkdir -p docs/qa-log.d
printf '### Q1: export format — 2026-07-11\n**Locked:** Excel\n**Citations:**\n- https://example.com/excel-export — reference\n' > docs/qa-log.d/cited.md
o="$(bash scripts/close-gate.sh phase "$PHASE" 2>&1)"
grep -q 'locked decision with no citation URL' <<<"$o" \
  && { echo "  ✗ POS  cited locked decision wrongly flagged"; failc=$((failc+1)); } \
  || { echo "  ✓ POS  cited locked decision silent"; pass=$((pass+1)); }
rm -rf docs/qa-log.d; restore
# POS: an OPEN section (no **Locked:** line) is never flagged even without a URL — the row polices
# locked decisions, not in-progress discussion
mkdir -p docs/qa-log.d
printf '### Q1: still open — 2026-07-11\njust discussion, nothing locked yet, no url\n' > docs/qa-log.d/open.md
o="$(bash scripts/close-gate.sh phase "$PHASE" 2>&1)"
grep -q 'locked decision with no citation URL' <<<"$o" \
  && { echo "  ✗ POS  open (unlocked) section wrongly flagged"; failc=$((failc+1)); } \
  || { echo "  ✓ POS  open unlocked section not flagged"; pass=$((pass+1)); }
rm -rf docs/qa-log.d; restore
# NEG: changelog.d dir-total cap fires (warn-only). changelog.d lives OUTSIDE docs/, so the
# coverage-floor find never sees it — this dir-cap row is its ONLY between-release size monitor.
mkdir -p changelog.d
python3 -c "print('x'*61440)" > changelog.d/big-fragment.md
o="$(bash scripts/close-gate.sh phase "$PHASE" 2>&1)"; rc=$?
grep -q 'changelog hot zone over hot cap' <<<"$o" && [ "$rc" -eq 0 ] \
  && { echo "  ✓ NEG  changelog.d dir-total over cap warns without failing"; pass=$((pass+1)); } \
  || { echo "  ✗ NEG  changelog.d dir-total cap row (rc=$rc)"; failc=$((failc+1)); }
rm -rf changelog.d .claude/retention-state.json
restore

echo "── coverage-discovery row (warn-only) ──"
python3 -c "print('x'*61440)" > docs/orphan.md
o="$(bash scripts/close-gate.sh phase "$PHASE" 2>&1)"; rc=$?
grep -q 'coverage: docs/orphan.md' <<<"$o" && [ "$rc" -eq 0 ] \
  && { echo "  ✓ NEG  oversize orphan doc surfaces"; pass=$((pass+1)); } \
  || { echo "  ✗ NEG  coverage row (rc=$rc)"; failc=$((failc+1)); }
mkdir -p docs/archive; mv docs/orphan.md docs/archive/
o="$(bash scripts/close-gate.sh phase "$PHASE" 2>&1)"
grep -q 'coverage: ' <<<"$o" \
  && { echo "  ✗ POS  archived file still flagged"; failc=$((failc+1)); } \
  || { echo "  ✓ POS  archived file exempt"; pass=$((pass+1)); }
restore
# POS: fragment dirs (qa-log.d) are excluded from coverage-discovery even when oversize —
# they are covered by the dir-total hot-cap row above instead, not the coverage-floor row
mkdir -p docs/qa-log.d
python3 -c "print('x'*61440)" > docs/qa-log.d/oversized-fragment.md
o="$(bash scripts/close-gate.sh phase "$PHASE" 2>&1)"
grep -q 'coverage: docs/qa-log.d' <<<"$o" \
  && { echo "  ✗ POS  qa-log.d fragment flagged by coverage (should be excluded)"; failc=$((failc+1)); } \
  || { echo "  ✓ POS  qa-log.d excluded from coverage-discovery"; pass=$((pass+1)); }
rm -rf docs/qa-log.d
restore

echo "── fragment-aware journal checks ──"
mkdir -p docs/journal.d
printf '## M9.9 Task 1 — t\n**Plan deviations:** none\n' > docs/journal.d/2026-01-02-note5.md
o="$(bash scripts/close-gate.sh task 2>&1)"; rc=$?
[ "$rc" -eq 0 ] && { echo "  ✓ POS  fragment satisfies task-done journal check"; pass=$((pass+1)); } \
  || { echo "  ✗ POS  fragment not accepted (rc=$rc)"; failc=$((failc+1)); }
# same-day fragments must resolve by MTIME, not filename sort: lexicographically
# 2026-01-02-note10.md < 2026-01-02-note5.md ('1'<'5'), so a filename sort would validate the
# stale note5 fragment. Backdate note5 (now header-less) and put the valid header in a newer note10.
printf '## stale entry, header mangled away\n' > docs/journal.d/2026-01-02-note5.md
touch -t 202607080000 docs/journal.d/2026-01-02-note5.md
printf '## M9.9 Task 2 — t\n**Plan deviations:** none\n' > docs/journal.d/2026-01-02-note10.md
o="$(bash scripts/close-gate.sh task 2>&1)"; rc=$?
[ "$rc" -eq 0 ] && { echo "  ✓ POS  newest-mtime fragment (note10) wins over lexicographic (note5)"; pass=$((pass+1)); } \
  || { echo "  ✗ POS  same-day fragment picked by filename, not mtime (rc=$rc)"; failc=$((failc+1)); }
rm -rf docs/journal.d
o="$(bash scripts/close-gate.sh task 2>&1)"; rc=$?
[ "$rc" -eq 0 ] && { echo "  ✓ POS  monolith fallback intact"; pass=$((pass+1)); } \
  || { echo "  ✗ POS  monolith fallback broken (rc=$rc)"; failc=$((failc+1)); }
restore

echo "── fragment-aware CHANGELOG checks ──"
# POS: a changelog.d/ fragment satisfies the CHANGELOG-touch check. Needs a
# real commit (not just a working-tree file) so it lands in the origin/main..HEAD diff range —
# same technique as the [DEBUG- probe / sweep tests below (commit, assert, hard-reset off).
mkdir -p changelog.d
printf '### Added\n- self-test changelog fragment\n' > changelog.d/2026-07-08-selftest.md
git add changelog.d/2026-07-08-selftest.md && git -c user.email=t@t -c user.name=t commit --quiet -m "test: changelog.d fragment (self-test)"
o="$(bash scripts/close-gate.sh phase "$PHASE" 2>&1)"
grep -q 'CHANGELOG \[Unreleased\] touched' <<<"$o" \
  && { echo "  ✓ POS  changelog.d fragment satisfies CHANGELOG-touch check"; pass=$((pass+1)); } \
  || { echo "  ✗ POS  changelog.d fragment not accepted"; failc=$((failc+1)); }
git reset --quiet --hard HEAD~1; restore
# POS: a direct CHANGELOG.md edit still satisfies the check (back-compat / un-adopted projects)
printf '\n- self-test CHANGELOG.md edit\n' >> CHANGELOG.md
git add CHANGELOG.md && git -c user.email=t@t -c user.name=t commit --quiet -m "test: CHANGELOG.md edit (self-test)"
o="$(bash scripts/close-gate.sh phase "$PHASE" 2>&1)"
grep -q 'CHANGELOG \[Unreleased\] touched' <<<"$o" \
  && { echo "  ✓ POS  CHANGELOG.md edit still satisfies check (back-compat)"; pass=$((pass+1)); } \
  || { echo "  ✗ POS  CHANGELOG.md edit not accepted"; failc=$((failc+1)); }
git reset --quiet --hard HEAD~1; restore
# NEG (case c, neither touched): already exercised above by the empty-range WT2 diff-range
# test ("CHANGELOG not touched (empty range)") — that assertion's message text is unchanged
# by the changelog.d support, and it now runs the union-grep path (changelog.d/ nor CHANGELOG.md touched at
# an empty range → still 'CHANGELOG.md not touched'), so no separate case-c test is added here.

echo "── invariant: two branches adding different fragments merge conflict-free ──"
# The machine-checkable proof this invariant rests on: the fragment layout means two parallel branches each
# writing their OWN <date>-<branch-slug>.md fragment touch DIFFERENT files, so a merge cannot conflict.
# Built in an ISOLATED throwaway repo (never the worktree) so branch churn is contained. Detection
# is the EXIT CODE of a real `git merge` (rc 0 = clean, non-zero = conflict) — deliberately NOT a
# `git merge-tree` marker-grep: the old three-arg merge-tree prints conflict markers as diff-ADDED
# lines ('+<<<<<<<'), so a '^<<<<<<<' grep silently misses them (a false pass). A real merge's rc
# has teeth by construction — a genuine shared-tail append (the pre-fragment layout) returns non-zero.
# docs/journal.d runs through this same loop alongside the other fragment dirs (changelog.d, docs/qa-log.d):
# journal is the doc that HAD the collision risk before its retroactive branch-slug rename (it
# was first shipped as a monthly monolith; the <date>-<branch-slug>.md naming was retrofitted onto
# it) — so this loop is that retrofit's machine-checkable proof too, not just its own two dirs.
for D in changelog.d docs/qa-log.d docs/journal.d; do
  INV="$TMP/inv-$(echo "$D" | tr / -)"; rm -rf "$INV"; mkdir -p "$INV"
  git -C "$INV" init -q
  git -C "$INV" config user.email t@t; git -C "$INV" config user.name t
  mkdir -p "$INV/$D"; : > "$INV/$D/.gitkeep"
  git -C "$INV" add -A; git -C "$INV" commit -q -m base
  base="$(git -C "$INV" rev-parse HEAD)"
  git -C "$INV" checkout -q -b brancha
  printf '### Added\n- alpha branch fragment\n' > "$INV/$D/2026-07-08-brancha.md"
  git -C "$INV" add -A; git -C "$INV" commit -q -m a
  git -C "$INV" checkout -q -b branchb "$base"
  printf '### Fixed\n- beta branch fragment\n' > "$INV/$D/2026-07-08-branchb.md"
  git -C "$INV" add -A; git -C "$INV" commit -q -m b
  git -C "$INV" checkout -q brancha
  # both branches diverge from base → a real (non-fast-forward) merge; rc has teeth
  if git -C "$INV" merge --no-edit branchb >/dev/null 2>&1; then
    echo "  ✓ INV  $D two-branch fragment merge is conflict-free (git merge rc 0)"; pass=$((pass+1))
  else
    echo "  ✗ INV  $D two-branch fragment merge conflicted (rc non-zero)"; failc=$((failc+1))
  fi
  rm -rf "$INV"
done

echo "── task-mode fail-paths ──"
# NOTE: these assertions mangle the MONOLITH journal directly, so they require docs/journal.d to be
# ABSENT (a present fragment shadows the monolith — the gate prefers the freshest-mtime fragment).
# That absence is now guaranteed structurally by restore() (which strips $JD_RESTORE after every
# checkout), not by a point-fix here — so it holds regardless of test order.
J="$(g journal)"; sedi 's/\*\*Plan deviations/\*\*Plan XXXXX/g' "$J"; neg "journal missing Plan-deviations" "missing 'Plan deviations'" task; restore
# order-independence regression guard: a SECOND monolith-mangle assertion AFTER the first's restore().
# If restore() ever stops stripping the resurrected fragment, the checkout between the two would
# revive docs/journal.d and this second assertion would read the valid fragment instead of the
# mangled monolith → gate would (wrongly) pass → neg would fail. Both green ⇒ order-independent.
J="$(g journal)"; sedi 's/\*\*Plan deviations/\*\*Plan XXXXX/g' "$J"; neg "journal missing Plan-deviations (2nd, order-independence guard)" "missing 'Plan deviations'" task; restore
rm -f "$(g test_evidence)" ; neg "stale/missing test-evidence" 'stale/missing test-evidence' task; restore
printf '' > "$(g test_evidence)" ; neg "empty-but-fresh test-evidence rejected (-s)" 'stale/missing test-evidence' task; restore

# --- what row 7's ✓ is ALLOWED to claim ---------------------------------------------------------
# Deliberately adjacent to the test-evidence fail-paths above: those pin what the row DOES, these
# pin what its ✓ may SAY: never more than the mechanism behind it (no "fresh", no "since it ran",
# only the caller-owned detail string) --
# the gate reads a FILE and no branch of it observes a process.
#
# The same assertion also lives in `scripts/test_close_gate.py` in the project-life-cycle
# repo. The two intentionally cover the SAME locked contract in different execution contexts --
# this harness is what an adopter materializes and runs against their own gate, and the pytest
# copy is the only layer whose red path can be observed there. Neither replaces the other.
# ROW7_CONTRACT_PHRASE and ROW7_FORBIDDEN_TOKENS below are BYTE-IDENTICAL to that file's constants
# of the same names; a change to either literal must be made in BOTH places, and a
# cross-file check in that file reddens on divergence.
ROW7_CONTRACT_PHRASE='this row may only claim fingerprint/evidence agreement, not test execution'
# GUIDANCE, NOT ENFORCEMENT. These four wordings each overclaim what this row can know;
# matching one is a tripwire for that specific phrasing, NOT a proof that the row is
# honest. An unlisted synonym ("verified", "confirmed", "attests") passes this list. What stops
# that is a human reading ROW7_CONTRACT_PHRASE when rewording -- which is why the phrase is in the
# failure message rather than a bare "assertion failed".
ROW7_FORBIDDEN_TOKENS=("fresh" "since it ran" "proves" "proving")
# The basis nouns are deliberately NOT part of the mirrored pair: the two evidence modes carry
# different nouns, an adopter may legitimately re-word the sentence around them, and the pytest
# copy holds the full required-token tuples. Kept here to the load-bearing halves of each mode's
# claim, as INDEPENDENT tokens rather than one contiguous phrase -- a contiguous
# 'unchanged since this file was generated' reddens on an added comma or a re-ordered clause,
# which is the false red this looser check exists to avoid (the pytest home uses four
# independent tokens for the same reason).
if [ "$(jq -r '.test_evidence_inputs | type' "$M" 2>/dev/null || echo null)" = array ]; then
  R7_BASIS_TOKENS=("unchanged" "generated"); R7_DISCLAIM='not proof'
  # fingerprint mode needs a real header, and it must come from the gate's own subcommand rather
  # than a hand-written line -- the digest is the gate's to compute. The set arg is accepted by
  # gates that require one and ignored by gates that do not, so this call is portable.
  #
  # temp-then-move, NOT `{ header; body; } > "$EV"`: the redirect truncates the destination before
  # the header step can fail, so a failing header still leaves a body-only file behind. That is the
  # same shape gen-test-evidence.sh exists to avoid, and reproducing it here would make this
  # fixture write the very artifact its assertions then judge.
  R7EVTMP="$(mktemp)"
  if bash scripts/close-gate.sh evidence-header task > "$R7EVTMP" 2>/dev/null && [ -s "$R7EVTMP" ]; then
    echo "test-run output" >> "$R7EVTMP"
    mv -f "$R7EVTMP" "$(g test_evidence)"
  else
    rm -f "$R7EVTMP"
    echo "  ✗ SETUP row-7 fixture: 'close-gate.sh evidence-header task' produced no header; the"
    echo "         two row-7 assertions below judge whatever evidence file was already present"
  fi
else
  R7_BASIS_TOKENS=("mtime"); R7_DISCLAIM='not evidence'
fi
# Taken from a REAL gate run, not from the gate's source text: a source grep cannot tell a row
# that is printed from one that is unreachable. PHASE is passed because task mode requires it on
# some gates and ignores it on others; passing it works against both.
R7OUT="$(bash scripts/close-gate.sh task "$PHASE" 2>&1 || true)"
R7ROW="$(grep '^✓' <<<"$R7OUT" | grep 'test-evidence' || true)"
# ASCII whitespace collapse + case fold, with the locale PINNED. This mirrors the MATCHING
# SEMANTICS of _normalised() in scripts/test_close_gate.py, and the pin is what makes that true:
# measured on macOS, BSD `tr -s '[:space:]'` under a UTF-8 locale IS multibyte-aware and collapses
# U+00A0, while the Python side (an explicit ASCII character class) is not -- so without LC_ALL=C
# a row separated by non-breaking spaces was caught HERE and missed THERE, and the byte-identity
# check above cannot see a divergence in matching semantics. ASCII-only Python plus a C-locale
# `tr` are what agree; neither alone does. Named limitation, stated rather than implied: with the
# locale pinned, BOTH homes now miss a banned wording split by non-ASCII whitespace.
R7NORM="$(printf '%s' "$R7ROW" | LC_ALL=C tr -s '[:space:]' ' ' | LC_ALL=C tr '[:upper:]' '[:lower:]')"
# (i) presence + names its evidence basis. A banned-claims assertion alone is structurally blind
# to the row DISAPPEARING: deleting it removes the offending words too, and a negative-only test
# goes green on an empty screen.
R7MISSING=""
for t7 in "${R7_BASIS_TOKENS[@]}" "$R7_DISCLAIM"; do
  case "$R7NORM" in *"$t7"*) ;; *) R7MISSING="$R7MISSING '$t7'" ;; esac
done
if [ -n "$R7ROW" ] && [ -z "$R7MISSING" ]; then
  echo "  ✓ POS  row 7's ✓ is printed and names its evidence basis"; pass=$((pass+1))
else
  echo "  ✗ POS  row 7's ✓ missing or no longer names its evidence basis (missing$R7MISSING) — $ROW7_CONTRACT_PHRASE, and it has to say which basis it means; row: ${R7ROW:-<none printed>}"; failc=$((failc+1))
fi
# (ii) banned claims. Reported by token, so the message says WHICH wording came back.
R7BANNED=""
for t in "${ROW7_FORBIDDEN_TOKENS[@]}"; do
  case "$R7NORM" in *"$t"*) R7BANNED="$R7BANNED '$t'" ;; esac
done
if [ -z "$R7ROW" ]; then
  # An absent row must not be reported as a clean banned-list scan: with nothing to read this
  # check has no opinion, and printing one would be the vacuous pass it exists to prevent.
  echo "  ✗ NEG  row 7's ✓ was not printed at all, so the banned-claims scan read nothing — $ROW7_CONTRACT_PHRASE"; failc=$((failc+1))
elif [ -z "$R7BANNED" ]; then
  echo "  ✓ NEG  row 7's ✓ makes no execution/freshness claim"; pass=$((pass+1))
else
  echo "  ✗ NEG  row 7's ✓ makes an execution/freshness claim$R7BANNED — $ROW7_CONTRACT_PHRASE; row: $R7ROW"; failc=$((failc+1))
fi
restore

# test_runs_required neg/pos
tmp=$(mktemp); jq '.test_runs_required=3' "$M" > "$tmp" && mv "$tmp" .claude/close-gate.json
echo "test-run output" > "$(g test_evidence)"  # fresh but no RUNS= marker
neg "task: test_runs_required=3, evidence has no RUNS line" 'RUNS=0 < required 3' task
printf 'RUNS=3\n' >> "$(g test_evidence)"
pos "task: test_runs_required=3, RUNS=3 present" task
restore
# regression guard for the pipefail-SIGPIPE false-negative (production close-gate.sh orphan-[DEBUG-
# check): the [DEBUG- marker is on line 1, followed by a LARGE block of added lines. With the old
# `git diff | grep -q` pipe, grep matches line 1 and exits, SIGPIPE-killing the still-writing git
# diff → pipefail 141 → gate falls to "no orphan" (false negative) → this neg fails. With the
# capture-then-herestring fix there is no pipe, so the marker is always seen and `bad` fires.
{ echo 'x = 1  # [DEBUG-probe] leftover'; for i in $(seq 1 20000); do echo "filler_line_$i = $i"; done; } > .close-gate-probe.py
git add .close-gate-probe.py && git -c user.email=t@t -c user.name=t commit --quiet -m "test: inject debug probe (large diff, marker first)"
neg "orphan [DEBUG- in diff (large-diff SIGPIPE guard)"  'orphan \[DEBUG- logs'  task
git reset --quiet --hard HEAD~1; restore
# Check #1 reads the BRANCH RANGE, so an empty commit stacked on this (passing) branch no
# longer fails it — the range still holds the branch's product change, and that is the point of that check
# (a docs: journal commit after the code is the normal cadence order). The fail path is an EMPTY
# range instead: a detached worktree at origin/main, where the range holds nothing. Path-based when
# the manifest declares product_paths ('no product-tree path'), the legacy verb check otherwise ('no
# feat/fix commit'); an empty range fails BOTH, so accept either message.
WT3="$TMP/wt3"
if git -C "$ROOT" worktree add --quiet --detach "$WT3" origin/main 2>/dev/null; then
  mkdir -p "$WT3/scripts" "$WT3/.claude"; cp scripts/close-gate.sh "$WT3/scripts/"; cp "$M" "$WT3/.claude/close-gate.json"
  o="$(cd "$WT3" && bash scripts/close-gate.sh task 2>&1 || true)"
  grep -qE 'no feat/fix commit|no product-tree path' <<<"$o" && { echo "  ✓ NEG  no product change in the range (empty range)"; pass=$((pass+1)); } || { echo "  ✗ NEG  product-tree check on an empty range"; failc=$((failc+1)); }
  git -C "$ROOT" worktree remove --force "$WT3" >/dev/null 2>&1 || true
else echo "  ⚠ SKIP product-tree empty-range test (could not create origin/main worktree)"; fi
# Sweeper diff-direction teeth: a sweep-tagged commit that ADDS code must fail; a SWEEP-PERF line rescues it.
# ALSO the regression guard for the sweep-DETECTION SIGPIPE (production close-gate.sh sweep check): the
# Archetype: sweep trailer sits on line 3 of a LARGE commit body (thousands of filler lines). With the old
# `git log --format=%B | grep -q` pipe, grep matches the trailer early and SIGPIPE-kills the still-writing
# git log → pipefail non-zero → detection misses the tag → the ENTIRE sweep gate is skipped → this
# net-positive diff is NOT flagged → this neg fails. Capture-then-herestring reads the full body, detects
# the tag, and flags. (The huge body is the commit MESSAGE only; the diff stays a 3-line net-positive add.)
printf 'a\nb\nc\n' > .sweep-probe.txt
{ printf 'feat: add probe (net-positive)\n\nArchetype: sweep\n'; for i in $(seq 1 20000); do echo "body_filler_line_$i"; done; } > "$TMP/sweepmsg.txt"
git add .sweep-probe.txt && git -c user.email=t@t -c user.name=t commit --quiet -F "$TMP/sweepmsg.txt"
neg "sweep tag + net-positive diff flagged (large-body detection guard)" 'not net-negative' task
printf '\nSWEEP-PERF: cache cut p99 by 40ms (self-test escape)\n' >> "$(g journal)"
# capture-then-grep, herestring not a pipe (same SIGPIPE race as the context-floor
# assertion above: piping the gate straight into grep -q races grep's early exit
# against the gate still writing, and pipefail surfaces the gate's 141 over grep's 0).
o="$(bash scripts/close-gate.sh task 2>&1)"
if grep -qE 'SWEEP-PERF evidence logged' <<<"$o"; then echo "  ✓ POS  sweep + SWEEP-PERF escape passes direction check"; pass=$((pass+1)); else echo "  ✗ POS  sweep SWEEP-PERF escape"; failc=$((failc+1)); fi
git reset --quiet --hard HEAD~1; restore
# no docs: commit in branch range — use detached wt2 at origin/main (empty range has no docs: commit)
WT2_DOCS="$TMP/wt2docs"
if git -C "$ROOT" worktree add --quiet --detach "$WT2_DOCS" origin/main 2>/dev/null; then
  mkdir -p "$WT2_DOCS/scripts" "$WT2_DOCS/.claude"; cp scripts/close-gate.sh "$WT2_DOCS/scripts/"; cp "$M" "$WT2_DOCS/.claude/close-gate.json"
  o_docs="$(cd "$WT2_DOCS" && bash scripts/close-gate.sh task 2>&1 || true)"
  grep -qE 'no docs: journal commit in branch range' <<<"$o_docs" && { echo "  ✓ NEG  no docs: journal commit (empty range)"; pass=$((pass+1)); } || { echo "  ✗ NEG  docs: commit branch-range path"; failc=$((failc+1)); }
  git -C "$ROOT" worktree remove --force "$WT2_DOCS" >/dev/null 2>&1 || true
else echo "  ⚠ SKIP docs:-commit range test (could not create origin/main worktree)"; fi

echo ""
echo "════════════════════════════════════════"
echo "close-gate self-test: $pass passed, $failc failed"
[ $failc -eq 0 ] && { echo "── ALL GATE CHECKS BEHAVE CORRECTLY"; exit 0; } || { echo "── SOME CHECKS MISBEHAVE"; exit 1; }
```

Note: the orphan-`[DEBUG-` check in `close-gate.sh` excludes both `scripts/close-gate.sh` and `scripts/test-close-gate.sh` from its scan — both legitimately contain the marker as tooling/test data.

---

## Wiring — three layers, the hook is NOT optional

The gate only forces anything if something *runs* it. The three layers are defense-in-depth, not a menu — **layer 1 is the default and must be active; 2 and 3 are additional cover.** Shipping only layer 3 is the trap that produces the exact symptom this gate exists to kill: the model is *supposed* to run `make phase-done`, finishes the code, feels done, and never runs it. A gate that depends on the model remembering to invoke it is the unreliable layer the skill warns about — make the automatic layers carry the weight.

1. **git pre-push hook — DEFAULT, automatic, installed at bootstrap.** (Automatic, *not* un-bypassable: `git push --no-verify` skips every pre-push hook. That is a fact about git, and the layer is strong because skipping it is a deliberate visible act rather than a forgotten step — not because it cannot be skipped. Only layer 2's server-side check is genuinely un-bypassable.) On a `feat/phase-*` branch it runs the **`task`** gate: a phase's first completed task is pushable the moment it exists (product-tree change + this task's journal FACT + fresh evidence), reconciling push-immediate with a gate that used to demand phase-close artifacts on commit one. It rejects an incomplete *task* push physically, regardless of model behaviour. This is the layer that actually works for per-task discipline. Script below. Never `--no-verify`. **Enforcement-shift note:** the heavier `phase` gate is no longer run by pre-push, so phase-close completeness (CHANGELOG / spec / plan / ROADMAP) is enforced at the **merge boundary** by layers 2 + 3 below — un-bypassable on repos with a required-status CI check (layer 2), and model-discipline + the human merge gate on CI-less repos. This is a deliberate trade: intermediate pushes become possible (they were structurally impossible before) at the cost of moving phase-done off the per-push hard block.
2. **CI job (the un-bypassable `phase-done` for shared repos).** A `close-gate` job in PR-time CI that runs `phase-done`. With branch protection requiring it, this is the hard, un-bypassable phase-close gate for shared repos — it is where phase-done's teeth moved. Also catches a task push whose phase was never completed. Slower loop (push-then-fail) but covers shared repos.
3. **Model-run discipline (additional, always).** The AI MUST run `make task-done` after each cadence task and `make phase-done` before opening the PR, and **paste the gate output**. "I ran it, it passed" without pasted output is an unverified claim — treat as not-run. On a CI-less repo this plus the human merge gate is what enforces phase-done, so it is not optional there.

### The pre-push hook — `.githooks/pre-push` (version-controlled, activated via `core.hooksPath`)

Committed to the repo (so teammates + fresh clones get it) and activated with one idempotent config line. On a `feat/phase-*` branch it runs the **`task`** gate, so intermediate pushes are allowed while each pushed task still carries its journal + evidence; any other branch pushes freely (WIP branches aren't gated). Phase-close completeness is the CI job's / merge boundary's responsibility (layers 2 + 3 above).

```bash
#!/usr/bin/env bash
# close-gate pre-push hook — installed by /init-harness (idempotent).
# Rejects pushing a feat/phase-* branch whose TASK close-gate fails: each pushed task must
# carry its product-tree change + journal FACT + evidence unchanged since generated. Phase-close artifacts (CHANGELOG /
# spec / plan / ROADMAP) are enforced by `phase` mode at the merge boundary (CI + human), not here.
# Bypass is NOT allowed — fix the missing artifact. Never --no-verify.
set -uo pipefail
branch="$(git symbolic-ref --short HEAD 2>/dev/null || true)"
case "$branch" in
  feat/phase-*)
    # Phase token = the segment after 'feat/phase-' up to the next '-'; `[^-]+` captures any
    # shape (1.2, X9.1a, X2-X10 → X2). An earlier dotted-numeric regex truncated letter suffixes.
    phase="$(printf '%s' "$branch" | sed -E 's#^feat/phase-([^-]+)-.*#\1#')"
    [ -f scripts/close-gate.sh ] || { echo "pre-push: scripts/close-gate.sh missing — run /init-harness --refresh"; exit 1; }
    echo "pre-push: running close-gate task $phase …"
    if ! bash scripts/close-gate.sh task "$phase"; then
      echo "── push REJECTED: task wrap-up incomplete (close-gate FAIL above)."
      echo "   Fix each ✗ (or log a 'SKIP: <reason>' in the journal Plan-deviations), then push again."
      echo "   Phase-close artifacts are checked by 'phase' mode before merge, not here. Never --no-verify."
      exit 1
    fi
    ;;
  *) : ;;   # non-phase branch — not gated
esac
```

Activation (idempotent — safe to re-run; this is what retrofits an EXISTING project):

```bash
mkdir -p .githooks
# (write the script above to .githooks/pre-push if absent)
chmod +x .githooks/pre-push
git config core.hooksPath .githooks   # activates it for this clone
```

> `core.hooksPath` relocates the hooks dir, so put any *other* project hooks under `.githooks/` too. If the project already uses husky / lefthook, add the `close-gate.sh task` call to that tool's pre-push stage instead — same effect, don't fight the existing manager.

### Retrofit an existing project (one block, idempotent)

A project that has the gate scripts but no active hook (the common gap) is fixed by running the activation block above, then proving it: `git config core.hooksPath` should print `.githooks`, and `make test-gate PHASE=X.Y` should show every check flips.

`/init-harness` scaffolds the gate script + self-test + manifest + `make` targets (`task-done` / `phase-done` / `test-gate`) AND installs+activates this pre-push hook by default (not a stub). Existing projects: materialize `scripts/close-gate.sh` + `scripts/test-close-gate.sh` from §"Portable gate script" and §"Self-test" above, run `/init-harness --refresh` (which writes `.githooks/pre-push` + sets `core.hooksPath` if missing), then `make test-gate PHASE=X.Y` once to confirm every check flips.

---

## The escape-hatch rule

The skill is full of "skip only when…" clauses. Each is individually reasonable; together they let the model rationalize skipping wrap-up. The gate neutralizes this: **a skip is allowed only when it is written down.** When an `exempt_*` flag is set or an artifact is legitimately absent, the gate requires a `SKIP: <one-line reason>` in the journal "Plan deviations" section. A skip you have to type a reason for is taken far less often than a silent one — and it leaves an audit trail.

---

## Sweeper diff-direction

This is the **one deterministic teeth** the archetype axis (`intent-gate.md` §"Archetype") adds to the gate. The other four archetypes reshape the chain by prose delta (the model applies them, the same way it applies the Size triage); diff direction is enforced because it is the single signal the harness previously had no concept of — nothing stopped a "delete / simplify" task from quietly *adding* surface while flying a cleanup flag.

**What fires it:** any commit in `origin/main..HEAD` carrying an `Archetype: sweep` trailer (written by the gate-front per `intent-gate.md` §"Recording the label"). No such trailer → the check is completely inert; it costs every other archetype nothing.

**What it asserts (task mode):** the code diff over `origin/main..HEAD` — with `docs/**` and `CHANGELOG.md` excluded, because those audit artifacts legitimately grow on every task — is **net-negative LOC** (`deletions > insertions`). 

**The escape:** when a sweep legitimately adds lines but improves performance (adding a cache, a memo table, an index-backed query), the author writes a `SWEEP-PERF: <evidence>` line in the journal "Plan deviations" section. Like the `SKIP:` escape, it is human-written and leaves an audit trail — the model cannot satisfy the teeth by fabricating a perf claim without typing the evidence line, and a reviewer sees it at the PR.

**What it does NOT check:** whether the sweep deleted the *right* thing. Correctness of a deletion is the differential oracle (behavior before == behavior after) + the validator (do the existing ACs still pass). The teeth police direction only — they stop a mislabelled add, nothing more.

Scope note: enforced in **task mode** (a sweep is usually a single cadence task). Phase mode does not run it — at phase range the additive audit artifacts dominate LOC and the signal is unreliable; a phase that is wholly a sweep is the rare case, handled by the per-task checks that compose it.

## Approval timing — the `close-gate` policy key

Everything above is the *deterministic* gate. Separately from it, projects that adopt a **human-blocking close approval** (e.g. a CLAUDE.md rule that the Task Close Report awaits the user's explicit "ok" before commit) choose WHERE that human approval sits via a CLAUDE.md policy key:

```
close-gate: per-task | pr-boundary
```

- **`per-task` (default)** — the human's blocking approval happens at every task close: the Task Close Report is posted and the session waits for the user's "ok" before committing. Highest-comprehension mode: the human reads every diff at the moment it lands.
- **`pr-boundary`** — the per-task read is delegated to an independent **read-only** reviewer subagent (same correctness-vs-promise lens as the validator). Task Close Reports are still **written for every task** — the audit trail does not thin out — but they no longer block. The human's blocking approval happens **once per PR/merge**, reading the accumulated reports + the full diff.

**What this key does NOT change:** the deterministic `task-done` / `phase-done` gates above run identically in both modes. The key moves the *human* approval point only; it never relaxes the machine gate, the journal, or the test-evidence checks.

**What `pr-boundary` additionally requires — the review record.** Because the human reads nothing until merge, the merge-time read must be auditable: the PR carries (A) every review round's report **verbatim** (writer-untouched, with SHA-range scope header + "not reviewed" list + dispatch-prompt provenance) and (B) the builder's per-finding response (agree/disagree + why, re-graded severity, what changed / deliberately didn't). Reviewer dispatch follows the bias constraints (fresh context, read-only, tier set explicitly, refute-first, `file:line` evidence gate, controller-computed verdict). **Coverage window check before merge:** `git log <last-review-SHA>..HEAD` must be empty, or those commits get a final-pass round — commits after the last review are unreviewed code in a "reviewed" PR. Full spec: `references/review-record.md`.

### The attack surface — read this before flipping to `pr-boundary`

The per-task human gate exists for one reason beyond diff confidence: **any approval the AI can write itself is not an approval.** Two failure modes shaped the current design:

1. An AI can treat a prose-only ("soft") close gate as optional and bypass it. The fix was structural — a hard hook the model cannot talk past — not more prose.
2. An AI can fabricate the user's approval: write "user approved" into the record when the user has said nothing.

`pr-boundary` widens the window in which the AI works with no human reading anything. That is acceptable ONLY while the merge boundary keeps a **human-written approval marker the AI physically cannot author**: the user themself performs the approving act (clicks merge, writes the approving PR comment/reply, runs the merge command), and wherever a hook checks for an approval marker, the marker's semantics must be "human typed this" — never a file or string the AI can produce on the user's behalf. If the project's merge approval can be generated by the AI, the self-certification hole is open and `pr-boundary` is NOT safe to enable.

### Run it as an experiment

Flipping to `pr-boundary` is a falsifiable experiment, not a permanent setting:

- Run 2-3 tracks/phases in `pr-boundary` mode, then check two signals: (1) **catch parity** — did the PR-boundary read still catch what the per-task reads used to catch (compare the reviewer subagent's per-task findings against what you find yourself at merge)? (2) **comprehension drift** — are diffs merging that you could not explain afterward?
- **Record, don't remember:** append one catch-parity line per track to the review-verbatim draft's footer (`catch-parity: track N — rounds=R, real-findings=…, fix-introduced-bugs-caught=…, human-merge-time-finds=…` — format in `references/review-record.md`). 2-3 tracks of these lines ARE the rollback/keep evidence.
- Either signal fails → rollback is one line: flip the key back to `per-task`.

---

## Anti-patterns — STOP

- **Claiming "done" without running the gate / without pasting its output** → not done; run it, paste it.
- **Hand-writing the test-evidence file** instead of letting the runner emit it → defeats the freshness check; the runner writes it, and even then the gate only checks the file is unchanged since it was generated, never that tests ran.
- **`--no-verify` to push past the pre-push gate** → blocked; fix the missing artifact, never bypass.
- **Marking a `task-done` ✗ as "fine, I'll do it later"** then opening the PR → `phase-done` will re-block; the debt compounds. Close each task fully.
- **Editing `exempt_*` to silence a check you just don't want to do** → only legitimate when the phase truly has no observable behavior; the `SKIP:` reason is reviewed at PR.
- **Gate passing treated as "quality approved"** → no. Gate proves ceremony happened. Correctness is the validator; craft is the code-quality reviewer. All three are separate.
- **`phase-done` doesn't check fresh test-evidence** → the gap that lets the test pile slip: if the gate mode a hook or CI job runs omits the evidence check, a phase ships with tests never run (`.claude/.last-test-run` never written, yet the gate PASSes). Fix: `phase-done` checks `test_evidence` whenever `test_command` is set — by declared-input fingerprint when `test_evidence_inputs` is set, else by mtime > HEAD. Confirm the gate output shows a `test-evidence` line. (It used to say "confirm a **`fresh test-evidence`** line": that adjective was removed from every branch of `evidence_runs_ok`, because neither mode can support it — so an adopter looking for the old string would find nothing and wrongly conclude the check is unwired.)
- **Gate scripts + manifest + `make` targets present, but NO active pre-push hook** (`git config core.hooksPath` empty AND no husky/lefthook stage) → only the weakest layer (model-discipline) is live, and the model skips wrap-up as predicted. This is NOT "the gate is installed." Run the retrofit block (write `.githooks/pre-push` + `git config core.hooksPath .githooks`); confirm with `git config core.hooksPath`.
- **Treating the pre-push hook as one option among three** ("I'll just run `make phase-done` myself") → the hook is the default and must be active; model-discipline is additional, not a substitute. The whole point is to not depend on the model remembering.
- **Tagging a task `Archetype: sweep` then adding net surface** → the diff-direction teeth block it. If the add is a real perf win, log `SWEEP-PERF: <evidence>` (human-written, audited at PR); if it is not a cleanup, it was the wrong archetype — re-tag it `build`/`maintain` and run the chain that shape demands. Do NOT add a hollow `SWEEP-PERF:` line to dodge the check; the reviewer reads it.
