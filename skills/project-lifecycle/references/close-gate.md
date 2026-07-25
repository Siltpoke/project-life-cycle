# Close Gate — the deterministic forcing function for "done"

The #1 failure mode of this skill: the AI finishes the *interesting* work (code that runs), feels done, and silently skips the wrap-up steps — journal, tests-3×, handoff, CHANGELOG, PR-comment. Prose "MANDATORY" does not stop this; the model treats prose as soft and the wrap-up steps are last in the list, furthest from attention by the time code works.

The fix is structural, per the skill's own rule (*structure > rules*): a **pure-code gate that exits non-zero when a required artifact is missing.** The model cannot lie past a script that greps for the journal file. This is the harness contract the rest of the skill promises — realized for wrap-up.

Two layers, used together:

1. **Visible state** — the AI materializes the step list at invocation — **the portable contract is `.claude/tasklist.md`, one `- [ ]` line per step**, wrap-up steps included; a host task tool (`TaskCreate` / `update_plan` / equivalent) is the upgrade where present, never the required mechanism — a `PreToolUse` hook cannot enumerate the session's tools and no two CLIs agree on the primitive's name (see SKILL.md "Two ways to satisfy it" + "Definition of Done"). Enumerate each step, never announce a count. Unchecked wrap-up tasks glare at done-time.
2. **Hard gate** — `task-done` / `phase-done` exits 1 on any missing required artifact. The AI MUST run it and paste the output before claiming the task/phase is complete. A pre-push hook makes it un-bypassable.

State #1 makes skips *obvious*; gate #2 makes them *impossible to hide*.

---

## What the gate checks

### `task-done` (one cadence task)
- [ ] the task's commit **touched the product tree** — the files changed in HEAD include a path under manifest `.product_paths[]` (e.g. `src/`, or `backend/`+`frontend/` for a split app, `skills/` for a skill repo). Path-based is the honest check: a legit `refactor:`/`docs(skill):` that changes the product passes, a meta-only change fails — the old commit-verb proxy couldn't tell them apart. **Backward-compatible:** when `product_paths` is not declared, this falls back to the legacy check that HEAD is a `feat(...)`/`fix(...)` commit
- [ ] a `docs:` journal commit exists in the branch range (`origin/main..HEAD`), and the journal entry contains the literal header `## Plan deviations` (present even if body = "none") — the journal checked is the **most-recently-modified** `*.md` fragment under `retention.journal_dir` (default `docs/journal.d/`) when one exists (mtime order, deliberately not filename order: same-day fragments like `…-note10.md` vs `…-note5.md` sort wrong lexicographically, and multiple undrained fragments coexisting within a milestone is the expected state), else the manifest `journal` monolith
- [ ] a fresh, **non-empty** test-evidence file exists — by **content fingerprint** when the manifest declares `test_evidence_inputs` (the evidence file's `# plc-gate-evidence inputs=<digest>` header must match the current-tree digest of the declared inputs), else by the legacy **mtime** check (newer than the feat commit). `-s` not just `-f` — an empty-but-fresh file is a false pass, e.g. an interrupted `tee`. Written by the project's test runner, not by hand; if `test_runs_required` > 1 the file must also contain a `RUNS=N` line with N ≥ required. **Scope note:** after a fixup, task-level evidence may be scoped to the suites the fixup diff touched (per `cadence.md` §"Selective re-verification after fixup") — the scoping is task-level ONLY; `phase-done` below always demands full-suite evidence, and that full run is the safety net for anything task-level scoping skipped
- [ ] no orphan `[DEBUG-` logs remain in the diff
- [ ] **(Sweeper only)** if a commit in range carries an `Archetype: sweep` trailer, the code diff (`docs/**` + `CHANGELOG.md` excluded) is net-negative LOC **or** a `SWEEP-PERF: <evidence>` line is logged — see §"Sweeper diff-direction"
- [ ] if any artifact is absent, a `SKIP:` line with a reason exists in the journal "Plan deviations" section

### `phase-done` (phase close, before PR-merge)
- [ ] `user-story.md` exists for the phase (unless `exempt_user_story` true — refactor/docs/infra)
- [ ] spec doc + plan doc exist for the phase
- [ ] the journal was touched in this phase's commit range — a change under manifest `retention.journal_dir` (default `docs/journal.d/`) **or** the manifest `journal` path (monolith fallback for projects not yet on the fragment convention) satisfies this (per-task completeness is a reviewer concern, not deterministically gated)
- [ ] the newest `*.md` fragment under `retention.journal_dir` (or the monolith fallback) contains a complete FACT entry — `Date`, `Decision`, `Why`, **`Backing`**, `Rejected`, `Source` all present as `- **Field:**` markdown bullets (the canonical form — matches what journals written under this schema use; see `references/journal-schema.md` §"The FACT entry"). Any missing field → hard fail naming exactly which. This is where the retired handoff file's one non-derivable section (§7 findings/gotchas) is *actually* enforced, not merely asserted to be — the journal-touched check above only proves some file changed, not that it carries the FACT content. **`Backing` is required for the same reason the other five are**: without a slot for the evidence, a distilled `Why` degrades into an assertion — measured on this schema's own first subject (2026-07-14), which carried `Rejected` 7/7 and lost the statistic its entire argument rested on.
- [ ] `CHANGELOG.md` `[Unreleased]` was touched in this phase's commit range — a change under manifest `retention.changelog_dir` (default `changelog.d/`) **or** `CHANGELOG.md` itself satisfies this (unless `exempt_changelog`)
- [ ] smoke artifacts exist — Track A checklist + Track B spec — when `user_visible` true
- [ ] acceptance tests exist for the phase (glob `acceptance_glob`), unless `exempt_user_story` true (cadence step 1.5)
- [ ] `docs/ROADMAP.md` touched in the phase's commit range **and the phase identifier actually appears in it**. Both, because "touched" is a proxy: a whitespace edit satisfies it, and the mtime variant used by the gitignored-docs gate is weaker still — that one printed `✓ ROADMAP.md updated this phase` while `grep -c <phase> docs/ROADMAP.md` returned 0. A row must not report a ceremony it only inferred; where the artifact's content is readable, read it
- [ ] **fresh, non-empty test-evidence file exists** (`test_evidence`, `-s` — the runner emitted it this phase, proving the tests actually ran before the phase ships; an empty-but-fresh file, e.g. an interrupted `bun test | tee`, is rejected). Freshness is a **content fingerprint** of `test_evidence_inputs` when declared, else mtime newer than HEAD. If `test_runs_required` > 1 the file must also contain `RUNS=N` with N ≥ required. Skipped only when the manifest has no `test_command`. **This is the check that makes the pre-push hook force tests** — without it, `phase-done` passed with tests never run, and the test pile silently slipped (the original gap). The PR-comment evidence block is the human-facing companion; this file check is the machine gate.
- [ ] every absent-but-claimed-skipped item has a `SKIP: <reason>` line
- [ ] **(warn-only, never fails the gate)** the context-floor hook (`context-floor.sh`) is wired in `~/.claude/settings.json` or the project's `.claude/settings*.json`. The floor is a machine-local user-settings hook (`references/harness-primitives.md` §9) — a project gate must not fail on a user's global config — but an un-armed floor is exactly how a session runs far past it unnoticed. Missing → the gate prints a `⚠` row pointing at `/init-harness --refresh`
- [ ] **(warn-only, never fails the gate)** hot-doc retention caps: each configured hot doc (defaults: RESUME 200L/25K, status doc 300L/30K, `docs/journal.d/` total 100K, qa-log 50K, `changelog.d/` total 50K; overrides via manifest `retention.hot_caps`) is measured `wc -l` + `wc -c`; over either limit → `⚠` row. Same doc over-cap at two consecutive closes (tracked in `.claude/retention-state.json`) → wording escalates to "SECOND consecutive over-cap close". See `references/retention.md` §"Hot-doc caps".
- [ ] **(warn-only, never fails the gate)** coverage discovery: any `docs/**/*.md` over `retention.coverage_floor_kb` (default 50K) that is neither manifest-known nor under `journal_dir`/`archive_dir` → `⚠` row naming the file ("manifest-known" is a v1 approximation: a substring match of the file's basename against the manifest text — slightly looser than "referenced by a manifest key"). See `references/retention.md` §"Coverage discovery".
- [ ] **(warn-only, never fails the gate)** qa-log citation coverage: each `### Q` section in a `retention.qa_log_dir` fragment (default `docs/qa-log.d/`) that carries a `**Locked:**` decision but **no `http(s)` URL** → `⚠` row naming the fragment + Q header. Enforces the brainstorm protocol's "no citation, no send" rule (`references/brainstorm-research-protocol.md`) — the #1 silent degradation is skipping research and opinion-polling. Deliberately **warn-only, not hard-fail**: a compressed established-pattern decision may legitimately cite a prior-phase lock (`M2.3 Q4`) rather than a URL, which a URL-only hard gate would false-block; the row informs the human at PR instead. Scoped to the fragment dir (current-phase, short-lived); the compiled monolith is historical and not re-litigated (v1 limitation — un-adopted projects that write only the monolith get no row).
- [ ] **(warn-only at `task`/`phase`; BLOCKING at `milestone` — see §"Milestone mode")** retention **count** caps: the number of `.md` files under `docs/superpowers/specs/`, `docs/superpowers/plans/`, and `docs/**` (excluding `*/screenshots/*` **and** `retention.archive_dir` — an archived doc must be able to clear the cap that told you to archive it) is compared against manifest `retention.count_caps` (defaults: specs 10, plans 10, docs_total 150 — applied by `cc()`'s default arg even when `count_caps` or the whole `retention` block is absent from the manifest; never silently unlimited). `0` = unlimited, `"none"` = exempt. **Why a count axis exists at all:** the size caps and the 50K coverage floor are blind to many-small-files growth — measured on a long-running project that adopted this skill, **596 of 610 docs were below every threshold**, and `docs/pr-drafts/` (143 files, 1.1 MB) was invisible to the net in its entirety. See `references/retention.md` §"The count axis".
- [ ] **(non-blocking `⊘` at `task`/`phase`; BLOCKING at `milestone`, unconditionally — see §"Milestone mode")** required-artifact manifest keys `phase_docs_glob`, `plan_glob`, `acceptance_glob`: an absent key prints a visible `⊘ <key> not configured in manifest` row (never a ✓, never silent) but never fails task/phase. At milestone close — `PHASE` arg or not — any of these three still unconfigured is a hard failure — the accumulated, ignored `⊘` finally stops being free. (`handoff_glob` is deliberately not in this set — the handoff file was retired.)

Checks are deliberately **deterministic + greppable** (file exists / header present / commit in range / mtime fresh). The gate does NOT judge quality — that is the validator + code-quality reviewer. The gate only proves the *ceremony actually happened*.

---

## Milestone mode — `close-gate.sh milestone [PHASE]`

The only mode where a retention row **fails the gate**. Rationale, measured on a real project, where warn-only was worth exactly zero three times over:

1. A CI lint job **exits 1 today**, parked behind a "make it blocking later" comment. It has never blocked anything; the comment is a promise that never came true.
2. A deferred-work list carried a dated trigger: a module had crossed its own hard line-count cap, and the next edit was to split it first, "no longer optional". The module is larger today. It grew. The trigger fired. Nothing happened.
3. The status doc carries a banner announcing that its own headline count is stale and understated — dozens of lines above the line still printing the stale number. **The document names its own lie and keeps telling it — because nothing fails.**

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

The gate is stack-agnostic; per-project specifics live in a small manifest the gate reads. A ready-to-edit copy of exactly the block below ships at `.claude/close-gate.json.example` — copy it to `.claude/close-gate.json` and replace `test_command`:

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
  "test_command": "REPLACE_ME e.g. 'bun test' or '.venv/bin/python -m pytest -q'",
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
  }
}
```

`retention` cap values are `[lines, KB]`; `0` means that dimension is unlimited. The whole block is optional — the gate falls back to these defaults when it (or any key inside it) is absent. `hot_caps.<doc>: "none"` exempts that doc — the only exemption mechanism. See `references/retention.md` §"Hot-doc caps" / §"Policy keys".

`count_caps` values are **file counts** of `*.md` (never PNGs — `*/screenshots/*` is excluded by construction, since those are load-bearing assets embedded in live PR comments via raw URLs, not documents; `docs_total` additionally excludes `retention.archive_dir` — the gate's own prescribed remedy for an over-cap close is to archive, so the count that gate rechecks must be capable of going back down). `0` = unlimited, `"none"` = exempt. Absent block, or an absent individual key inside it → **specs 10, plans 10, docs_total 150** — the gate's `cc()` helper defaults every key exactly the way `cap_val()` defaults `hot_caps`, so an unconfigured count axis is never silently unlimited.

`status_doc` (optional, default `docs/STATUS.md`) names the read-first status doc measured by the hot-cap row; `RESUME.md` and `docs/brainstorming-qa-log.md` are conventional paths and stay hardcoded in the gate. `retention.qa_log_dir` (default `docs/qa-log.d`) and `retention.changelog_dir` (default `changelog.d`) are manifest-driven, mirroring `journal_dir`.

`product_paths` (optional array, **task mode**) names the code/product tree; a task's commit satisfies check #1 by touching a path under it (`git diff-tree … HEAD`). This asks the honest question — *did the task change the product* — that the legacy `feat|fix` commit-verb check only proxied: a legitimate `refactor:` or `docs(skill):` that changes the product now passes, while a meta-only change fails, which no widened verb list could tell apart. Set it to your product tree — `["src/"]`, `["backend/","frontend/"]`, `["skills/"]` for a skill repo. **Backward-compatible:** an *absent* key falls back to the legacy `feat|fix` check, so a manifest predating this key is unaffected and no adopter's gate flips on upgrade — the path check is opt-in by declaring the key. A malformed value (present but not a non-empty array — an object, string, or empty array) fails closed.

`test_evidence_inputs` (optional array) switches the **test-evidence freshness** check from mtime to a **content fingerprint**. mtime is not evidence that the tests ran against the *current* code — git does not preserve mtime across a checkout, and a fresh clone / CI checkout / synced folder shuffles mtimes, so a mtime-only row false-PASSES by construction there. Declare the inputs whose change means "the tests must be re-run" (globs, e.g. `["src/**","tests/**"]`); the gate then requires the evidence file's first line to be a `# plc-gate-evidence inputs=<digest>` header that matches the current-tree digest of those inputs. **The runner must produce that header** — prepend it with the `evidence-header` subcommand: `{ close-gate.sh evidence-header; <test_command>; } | tee <test_evidence>`. **Two-part opt-in, so no adopter breaks:** an *absent* key keeps the legacy mtime check byte-identical (existing manifests are untouched), and even a declared key does nothing until the runner writes the header — a declared-but-unheaded evidence file **hard-fails** (never silently falls back to mtime) with the exact regenerate command. Inputs that match no tracked file, or a malformed value, fail closed. The digest is over git-**tracked** working-tree content (an uncommitted edit to a tracked input *is* caught; a brand-new *unstaged* file is not — stage before generating evidence), the same git-tracked convention `product_paths` uses. `/init-harness` wiring (generate the key + the header-prefixed runner for new adopters) is not wired: an adopter opts in by declaring the key and prefixing the runner.

When `test_runs_required` > 1, the project's `make test-evidence` (or test runner) **MUST emit a `RUNS=N` line** into the evidence file (e.g. `echo "RUNS=$n" >> .claude/.last-test-run`). The gate reads that line; if absent it treats the run-count as 0 and fails.

`{PHASE}` is substituted from the `PHASE=X.Y` arg. `/init-harness` generates this manifest from the detected stack; hand-edit per phase to flip the `exempt_*` / `user_visible` flags (and the gate FORCES a `SKIP:` reason when an exempt flag suppresses a check).

---

## Portable gate script — `scripts/close-gate.sh`

Drop this in the project; wire `make task-done` / `make phase-done` to call it. Pure bash + `git` + `jq`, no stack assumptions.

```bash
#!/usr/bin/env bash
# Usage: close-gate.sh task            (gate one cadence task)
#        close-gate.sh phase X.Y       (gate a phase close)
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
evidence_digest() {
  # Disable globbing while splitting the pattern list: a pattern like 'src/**' must reach
  # `git ls-files` as a (recursive) PATHSPEC, not be expanded by the shell against the cwd first.
  # `set -- $LIST` under `set -f` passes them verbatim.
  _inputs="$(jq -r '.test_evidence_inputs[]?' "$M" 2>/dev/null)"
  # No inputs declared → emit the sentinel, do NOT proceed to `git ls-files` with an empty pathspec:
  # an empty pathspec list means "no restriction" (matches the WHOLE tracked tree), not "match
  # nothing", so `evidence-header` run on a manifest without test_evidence_inputs would silently hash
  # the entire repo. check_evidence never reaches here on that path (it gates on a non-empty array),
  # but the `evidence-header` subcommand is adopter-reachable directly.
  [ -n "$_inputs" ] || { printf 'EMPTY-no-test-evidence-inputs-declared\n'; return 0; }
  set -f
  # shellcheck disable=SC2086
  set -- $_inputs
  set +f
  # Zero matches must NOT fall through to `git hash-object --stdin` on empty input: that returns the
  # FIXED empty-blob SHA e69de29b…, a constant that passes the header regex, so the row would compare
  # constant-to-constant and PASS vacuously — an adopter whose globs match nothing would silently
  # green, the exact silent-degrade this mode removes. Emit a non-hex sentinel; check_evidence rejects
  # it loudly.
  if [ -z "$(git ls-files -z -- "$@" 2>/dev/null | tr -d '\0')" ]; then
    printf 'EMPTY-no-test-evidence-inputs-matched\n'; return 0
  fi
  git ls-files -z -- "$@" 2>/dev/null \
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

fail=0
ok()  { echo "✓ $1"; }
bad() { echo "✗ $1"; fail=1; }
warn() { echo "⚠ $1"; }   # never touches $fail — warn-only by construction
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
# bash 3.2's `[ a -nt b ]` truncates mtimes to whole seconds — verified on this
# machine's /bin/bash: two files placed 0.2-0.9s apart in the SAME wall-clock second compare
# `-nt` FALSE regardless of which one is actually newer, so a freshness check built on `-nt`
# can wrongly reject genuinely-fresh evidence written less than a second after the commit it
# covers. `find X -newer Y` reads the full (sub-second) mtime — verified on the system bash:
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
evidence_runs_ok() {
  if [ "$2" -gt 1 ]; then
    n=$(grep -oE 'RUNS=[0-9]+' "$1" | head -1 | cut -d= -f2 || true); n=${n:-0}
    if [ "$n" -ge "$2" ]; then ok "fresh test-evidence, RUNS=$n (>=$2)"
    else bad "test-evidence RUNS=$n < required $2 — run tests ${2}× (runner must emit 'RUNS=N')"; fi
  else ok "fresh test-evidence ($3)"; fi
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
check_evidence() {
  EV="$(g test_evidence)"; REQ="$(jq -r '.test_runs_required // 1' "$M")"
  # Absent/empty test_evidence is a HARD FAIL, not a warn-skip — byte-identical to the pre-existing
  # inline blocks (an absent key gave EV="", `[ -s "" ]` false, then bad). Do NOT downgrade this to
  # a skip: a manifest with a test_command but no evidence path is a misconfiguration the gate must
  # surface, and a silent pass here is the vacuous-pass-on-absent-key defect this file guards against.
  [ -s "$EV" ] || { bad "stale/missing test-evidence — run: $(g test_command)"; return 0; }
  TEI_TYPE="$(jq -r '.test_evidence_inputs | type' "$M" 2>/dev/null || echo null)"
  REGEN="{ close-gate.sh evidence-header; $(g test_command); } | tee $EV"
  if [ "$TEI_TYPE" = array ] && [ "$(jq -r '.test_evidence_inputs | length' "$M" 2>/dev/null || echo 0)" -gt 0 ]; then
    EVDIG="$(sed -n '1s/^# plc-gate-evidence inputs=\([0-9a-f]\{40,64\}\)[[:space:]]*$/\1/p' "$EV" 2>/dev/null)"
    NOWDIG="$(evidence_digest)"
    if [ "${NOWDIG#EMPTY-}" != "$NOWDIG" ]; then
      bad "test_evidence_inputs matched no tracked files — the fingerprint checks nothing; fix the globs in the manifest"
    elif [ -z "$EVDIG" ]; then
      bad "test-evidence $EV has no '# plc-gate-evidence inputs=<digest>' first line — regenerate it: $REGEN"
    elif [ "$EVDIG" != "$NOWDIG" ]; then
      bad "test-evidence $EV is stale — a declared test_evidence_input changed since it was generated — re-run: $REGEN"
    else
      evidence_runs_ok "$EV" "$REQ" "fingerprint matches the current tree"
    fi
  elif [ "$TEI_TYPE" = null ]; then
    HREF="$(mktemp)"; stamp_head_date "$HREF" || true  # HEAD committer-date, not .git/HEAD mtime.
    # `|| true`: on a stamp failure (bad/empty date → touch -t non-zero) set -e must NOT abort before the
    # rm below, or the temp file leaks. HREF then keeps its recent mktemp mtime, so evidence reads older
    # → fail-CLOSED (never a false fresh); the failure just cannot leak a /tmp file.
    if fresh "$EV" "$HREF"; then evidence_runs_ok "$EV" "$REQ" "$EV"
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
# swallows that SILENTLY: no row, no warn, no ⊘. That is the same vacuous-pass-on-absent-key defect `req_glob` above was
# written to kill — reintroduced here for the count axis a few commits later, in
# this branch's own new code. Routing through a caller-supplied default (specs/plans 10,
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

if [ "$MODE" = task ]; then
  # Product-tree check: did THIS task's commit touch the product tree? A path check asks the real question
  # ("the phase shipped a product change") that the old `feat|fix` commit-VERB test only proxied —
  # a legit refactor-only commit under the product tree had to be mislabeled `feat` to pass. Paths
  # come from the manifest `.product_paths[]`. BACKWARD-COMPATIBLE: an ABSENT key falls back to the
  # legacy verb check, so a manifest predating this key keeps its behavior and no adopter's gate
  # flips on upgrade — the path check is opt-in by declaring product_paths. `git diff-tree … --root
  # HEAD` names the files in HEAD's own commit; `--root` is REQUIRED for parent-safety — without it
  # a root commit (an adopter's very first commit, e.g. an init-harness scaffold + first product
  # code in one commit) diffs against a nonexistent parent and prints nothing → false ✗ on a real
  # change; with it a root commit lists all its files and a parented commit is unaffected. Gate on
  # the JSON *type*: `.product_paths[]?` also iterates an object's values, so a `{"a":"src/"}` typo
  # would silently run on those — only a non-empty ARRAY takes the path branch; null (absent) →
  # verb fallback; anything else (object / string / empty array) → fail closed.
  PP_TYPE="$(jq -r '.product_paths | type' "$M" 2>/dev/null || echo null)"
  if [ "$PP_TYPE" = array ] && PP_LIST="$(jq -r '.product_paths[]' "$M" 2>/dev/null)" && [ -n "$PP_LIST" ]; then
    # strip trailing slash, escape EVERY ERE metachar (so an adopter path like `c++/` or `app(v2)/`
    # can't reach grep -E raw and false-FAIL), join with `|`. grep -c … -gt 0 (not grep -q) for the
    # same pipefail/SIGPIPE reason the docs:/[DEBUG- checks below use.
    PP_ALT="$(printf '%s\n' "$PP_LIST" | sed -e 's#/*$##' -e 's#[][(){}.^$*+?|\\]#\\&#g' | paste -sd'|' -)"
    if [ "$(git diff-tree --no-commit-id --name-only -r --root HEAD 2>/dev/null | grep -cE "^(${PP_ALT})/" || true)" -gt 0 ]; then
      ok "task commit touches the product tree (${PP_ALT})"
    else bad "task commit changed no product-tree path (${PP_ALT}) — a task must ship a product change (or fix product_paths)"; fi
  elif [ "$PP_TYPE" = null ]; then
    git log -1 --format=%s | grep -qE '^(feat|fix)(\(|:)' && ok "feat/fix commit" || bad "no feat/fix commit on HEAD"
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
  J="$(ls -t "$JD"/*.md 2>/dev/null | head -1 || true)"
  [ -n "$J" ] || J="$(g journal)"
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
elif [ "$MODE" = phase ]; then
  [ -n "$PHASE" ] || { echo "✗ phase mode needs PHASE arg"; exit 1; }
  RANGE="origin/main..HEAD"
  PDG="$(g phase_docs_glob)"; PLG="$(g plan_glob)"
  if [ "$(jq -r .exempt_user_story "$M")" = true ]; then
    skip_logged && ok "user-story exempt (SKIP: logged)" || bad "exempt_user_story=true but no 'SKIP:' line in journal"
  else req_glob "${PDG:+${PDG}*user-story*}" "user-story.md" "no user-story.md for phase $PHASE" "phase_docs_glob"; fi
  req_glob "$PDG" "spec doc"    "no spec doc for phase $PHASE"    "phase_docs_glob"
  req_glob "$PLG" "plan doc"    "no plan doc for phase $PHASE"    "plan_glob"
  # NOTE: no handoff-doc check here — the handoff file was retired; its one
  # non-derivable section (§7 findings/gotchas) is enforced by the journal-touched check
  # above instead (FACT schema, references/journal-schema.md). handoff-template.md is
  # retained for its §7 field definitions + PR-description appendix, but names no output
  # file any more, so there is nothing left for a glob-based artifact check to find.
  # CHANGELOG-touched: accept a change under retention.changelog_dir (fragment convention
  # ) OR CHANGELOG.md itself (back-compat / un-adopted projects) — capture-then-grep, no
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
  # text, so grep the phase identifier too. A sibling gate that checked only
  # recency printed "✓ ROADMAP.md updated this phase" while the phase appeared nowhere in the
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
  # §"The FACT entry") — until now nothing checked it existed, had a Why, or had a Rejected, so
  # close-gate.md's "is enforced" claim was a cache with no mechanism behind it. Canonical field
  # form is the markdown-bullet style journal entries actually use under this schema
  # journal ("- **Decision:** ..."), not the bare "Decision:" form journal-schema.md used to
  # show — journal-schema.md was corrected to match reality instead of the other way around.
  # $J = newest fragment under $JD (mtime, not filename — same rationale as task mode's $J,
  # same $JN monolith fallback the journal-touched check above already resolved).
  #
  # `Backing` is the evidence slot. It exists because its absence was measured: an acceptance
  # test distilled its spec into a FACT entry and compared them field by field: `Rejected` carried
  # 7/7, `Why` lost most of its substance — because the schema had a slot for the CONCLUSION and
  # none for the EVIDENCE it rested on, so every argument silently degraded into an assertion. The
  # single statistic the entire spec turned on, and a corollary the spec
  # itself marked load-bearing both vanished. A missing field cannot be patched by writing more
  # prose into an adjacent one: with no slot that says "the number you must not drop," the writer
  # drops it. The schema was derived from `references-log`, whose entries carry `Backing` PRECISELY
  # so a claim cannot be stated without its support — and journal-schema.md said so, two lines below
  # a schema block that had copied `Date` and dropped `Backing`. This row is that gap, closed.
  J="$(ls -t "$JD"/*.md 2>/dev/null | head -1 || true)"; [ -n "$J" ] || J="$JN"
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
  # pre-push hook runs task mode on every push, so tests are forced on every pushed task,
  # not only at phase close. Skipped only when the project has no test_command. (Was missing
  # here originally — tests fell through every hooked gate.)
  if [ -n "$(g test_command)" ]; then
    check_evidence   # content fingerprint when test_evidence_inputs is declared, else legacy mtime
  fi
  # context-floor arming check — WARN-ONLY (never flips $fail): the floor is a
  # machine-local user-settings hook, so a project gate must not fail on it; but
  # an un-armed floor silently costs 2-3x per late-session turn.
  # ${HOME:-}: under set -u a stripped hook/CI environment without HOME would abort
  # the whole gate on the bare expansion — the one thing a warn-only row must not do.
  if grep -qs 'context-floor' "${HOME:-}/.claude/settings.json" .claude/settings.json .claude/settings.local.json 2>/dev/null; then
    ok "context-floor hook wired (settings reference context-floor.sh)"
  else
    echo "⚠ context-floor hook not wired in ~/.claude/settings.json or project .claude/settings*.json — sessions can silently run to very large per-turn contexts. Fix: /init-harness --refresh (references/harness-primitives.md §9)"
  fi
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
task-done:      ; @bash scripts/close-gate.sh task
phase-done:     ; @bash scripts/close-gate.sh phase $(PHASE)
milestone-done: ; @bash scripts/close-gate.sh milestone $(PHASE)
test-gate:      ; @bash scripts/test-close-gate.sh $(PHASE)
```

---

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

echo "── context-floor arming row (warn-only — must NEVER fail the gate) ──"
FH="$TMP/fakehome"; mkdir -p "$FH"   # isolate from the real ~/.claude/settings.json
o="$(HOME="$FH" bash scripts/close-gate.sh phase "$PHASE" 2>&1)"; rc=$?
if grep -q 'context-floor hook not wired' <<<"$o" && [ "$rc" -eq 0 ]; then echo "  ✓ NEG  un-armed floor warns without failing the gate"; pass=$((pass+1)); else echo "  ✗ NEG  un-armed floor warn row (rc=$rc)"; failc=$((failc+1)); fi
printf '{"hooks":{"PreToolUse":[{"matcher":"Edit|Write","hooks":[{"type":"command","command":"/path/to/context-floor.sh"}]}]}}\n' > .claude/settings.json
# capture-then-grep, herestring not a pipe: piping the gate straight into grep -q
# makes grep's early exit SIGPIPE the still-writing gate (exit 141), and pipefail
# surfaces 141 over grep's 0 — the direct-pipe assertion failed 100% of the time.
o="$(HOME="$FH" bash scripts/close-gate.sh phase "$PHASE" 2>&1 || true)"
grep -q 'context-floor hook wired' <<<"$o" && { echo "  ✓ POS  armed floor prints wired row"; pass=$((pass+1)); } || { echo "  ✗ POS  armed floor wired row"; failc=$((failc+1)); }
rm -f .claude/settings.json; restore

echo "── retention hot-cap rows (warn-only — must NEVER fail the gate) ──"
# NEG: over-cap RESUME warns without failing (first close — also seeds retention-state.json)
python3 -c "print('x\n'*250)" > RESUME.md
o="$(bash scripts/close-gate.sh phase "$PHASE" 2>&1)"; rc=$?
grep -q 'RESUME.md over hot cap' <<<"$o" && [ "$rc" -eq 0 ] \
  && { echo "  ✓ NEG  over-cap doc warns without failing"; pass=$((pass+1)); } \
  || { echo "  ✗ NEG  over-cap doc warn row (rc=$rc)"; failc=$((failc+1)); }
# AC3: the SAME doc still over-cap at the second consecutive close escalates the wording
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
# by this task, and it now runs the union-grep path (changelog.d/ nor CHANGELOG.md touched at
# an empty range → still 'CHANGELOG.md not touched'), so no separate case-c test is added here.

echo "── AC3 invariant: two branches adding different fragments merge conflict-free ──"
# The machine-checkable proof this invariant rests on: the fragment layout means two parallel branches each
# writing their OWN <date>-<branch-slug>.md fragment touch DIFFERENT files, so a merge cannot conflict.
# Built in an ISOLATED throwaway repo (never the worktree) so branch churn is contained. Detection
# is the EXIT CODE of a real `git merge` (rc 0 = clean, non-zero = conflict) — deliberately NOT a
# `git merge-tree` marker-grep: the old three-arg merge-tree prints conflict markers as diff-ADDED
# lines ('+<<<<<<<'), so a '^<<<<<<<' grep silently misses them (a false pass). A real merge's rc
# has teeth by construction — a genuine shared-tail append (the pre-fragment layout) returns non-zero.
# docs/journal.d runs through this same loop alongside the other fragment dirs (changelog.d, docs/qa-log.d):
# journal is the doc that HAD the collision risk before AC7's retroactive branch-slug rename (it
# was first shipped as a monthly monolith; AC7 retrofitted the <date>-<branch-slug>.md naming onto
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
git -c user.email=t@t -c user.name=t commit --quiet --allow-empty -m "chore: not a cadence task"
# check #1 is path-based when the manifest declares product_paths (an empty commit touches no
# product path → 'no product-tree path') and the legacy verb check otherwise ('no feat/fix commit').
# An empty chore commit fails BOTH branches, so accept either message — the NEG stays correct whether
# the manifest under test predates product_paths or ships it (the manifest example now does).
neg "non-product / non-feat-fix HEAD"  'no feat/fix commit|no product-tree path'  task
git reset --quiet --hard HEAD~1; restore
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

The gate only forces anything if something *runs* it. The three layers are defense-in-depth, not a menu — **layer 1 is the default and must be active; 2 and 3 are additional cover.** Shipping only layer 3 is the trap that produces the exact symptom this gate exists to kill: the model is *supposed* to run `make phase-done`, finishes the code, feels done, and never runs it. A gate that depends on the model remembering to invoke it is the unreliable layer the skill warns about — make the un-bypassable layer carry the weight.

1. **git pre-push hook — DEFAULT, un-bypassable, installed at bootstrap.** On a `feat/phase-*` branch it runs the **`task`** gate: a phase's first completed task is pushable the moment it exists (product-tree change + this task's journal FACT + fresh evidence), reconciling push-immediate with a gate that used to demand phase-close artifacts on commit one. It rejects an incomplete *task* push physically, regardless of model behaviour. This is the layer that actually works for per-task discipline. Script below. Never `--no-verify`. **Enforcement-shift note:** the heavier `phase` gate is no longer run by pre-push, so phase-close completeness (CHANGELOG / spec / plan / ROADMAP) is enforced at the **merge boundary** by layers 2 + 3 below — un-bypassable on repos with a required-status CI check (layer 2), and model-discipline + the human merge gate on CI-less repos. This is a deliberate trade: intermediate pushes become possible (they were structurally impossible before) at the cost of moving phase-done off the per-push hard block.
2. **CI job (the un-bypassable `phase-done` for shared repos).** A `close-gate` job in PR-time CI that runs `phase-done`. With branch protection requiring it, this is the hard, un-bypassable phase-close gate for shared repos — it is where phase-done's teeth moved. Also catches a task push whose phase was never completed. Slower loop (push-then-fail) but covers shared repos.
3. **Model-run discipline (additional, always).** The AI MUST run `make task-done` after each cadence task and `make phase-done` before opening the PR, and **paste the gate output**. "I ran it, it passed" without pasted output is an unverified claim — treat as not-run. On a CI-less repo this plus the human merge gate is what enforces phase-done, so it is not optional there.

### The pre-push hook — `.githooks/pre-push` (version-controlled, activated via `core.hooksPath`)

Committed to the repo (so teammates + fresh clones get it) and activated with one idempotent config line. On a `feat/phase-*` branch it runs the **`task`** gate, so intermediate pushes are allowed while each pushed task still carries its journal + evidence; any other branch pushes freely (WIP branches aren't gated). Phase-close completeness is the CI job's / merge boundary's responsibility (layers 2 + 3 above).

```bash
#!/usr/bin/env bash
# close-gate pre-push hook — installed by /init-harness (idempotent).
# Rejects pushing a feat/phase-* branch whose TASK close-gate fails: each pushed task must
# carry its product-tree change + journal FACT + fresh evidence. Phase-close artifacts (CHANGELOG /
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

> `core.hooksPath` relocates the hooks dir, so put any *other* project hooks under `.githooks/` too. If the project already uses husky / lefthook, add the `close-gate.sh phase` call to that tool's pre-push stage instead — same effect, don't fight the existing manager.

### Retrofit an existing project (one block, idempotent)

A project that has the gate scripts but no active hook (the common gap) is fixed by running the activation block above, then proving it: `git config core.hooksPath` should print `.githooks`, and `make test-gate PHASE=X.Y` should show every check flips.

`/init-harness` scaffolds the gate script + self-test + manifest + `make` targets (`task-done` / `phase-done` / `test-gate`) AND installs+activates this pre-push hook by default (not a stub). Existing projects: copy `scripts/close-gate.sh` + `scripts/test-close-gate.sh`, run `/init-harness --refresh` (which writes `.githooks/pre-push` + sets `core.hooksPath` if missing), then `make test-gate PHASE=X.Y` once to confirm every check flips.

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

The per-task human gate exists for one reason beyond diff confidence: **any approval the AI can write itself is not an approval.** Two real incidents shaped the current design:

1. An AI treated a prose-only ("soft") close gate as optional and bypassed it. The fix was structural — a hard hook the model cannot talk past — not more prose.
2. An AI fabricated the user's approval: it wrote "user approved" into the record when the user had said nothing.

`pr-boundary` widens the window in which the AI works with no human reading anything. That is acceptable ONLY while the merge boundary keeps a **human-written approval marker the AI physically cannot author**: the user themself performs the approving act (clicks merge, writes the approving PR comment/reply, runs the merge command), and wherever a hook checks for an approval marker, the marker's semantics must be "human typed this" — never a file or string the AI can produce on the user's behalf. If the project's merge approval can be generated by the AI, the self-certification hole is open and `pr-boundary` is NOT safe to enable.

### Run it as an experiment

Flipping to `pr-boundary` is a falsifiable experiment, not a permanent setting:

- Run 2-3 tracks/phases in `pr-boundary` mode, then check two signals: (1) **catch parity** — did the PR-boundary read still catch what the per-task reads used to catch (compare the reviewer subagent's per-task findings against what you find yourself at merge)? (2) **comprehension drift** — are diffs merging that you could not explain afterward?
- **Record, don't remember:** append one catch-parity line per track to the review-verbatim draft's footer (`catch-parity: track N — rounds=R, real-findings=…, fix-introduced-bugs-caught=…, human-merge-time-finds=…` — format in `references/review-record.md`). 2-3 tracks of these lines ARE the rollback/keep evidence.
- Either signal fails → rollback is one line: flip the key back to `per-task`.

---

## Anti-patterns — STOP

- **Claiming "done" without running the gate / without pasting its output** → not done; run it, paste it.
- **Hand-writing the test-evidence file** instead of letting the runner emit it → defeats freshness check; the runner writes it, mtime proves tests actually ran.
- **`--no-verify` to push past the pre-push gate** → blocked; fix the missing artifact, never bypass.
- **Marking a `task-done` ✗ as "fine, I'll do it later"** then opening the PR → `phase-done` will re-block; the debt compounds. Close each task fully.
- **Editing `exempt_*` to silence a check you just don't want to do** → only legitimate when the phase truly has no observable behavior; the `SKIP:` reason is reviewed at PR.
- **Gate passing treated as "quality approved"** → no. Gate proves ceremony happened. Correctness is the validator; craft is the code-quality reviewer. All three are separate.
- **`phase-done` doesn't check fresh test-evidence** → the original gap that let the test pile slip: the pre-push hook runs `phase-done`, but if `phase-done` omits the evidence check, a phase ships with tests never run (`.claude/.last-test-run` never written, yet the gate PASSes). `task-done` checks evidence but has no hook; `phase-done` is hooked but skipped the check. Tests = the one artifact with no live gate. Fix: `phase-done` checks fresh `test_evidence` (mtime > HEAD) whenever `test_command` is set. Confirm the gate output shows a `fresh test-evidence` line.
- **Gate scripts + manifest + `make` targets present, but NO active pre-push hook** (`git config core.hooksPath` empty AND no husky/lefthook stage) → only the weakest layer (model-discipline) is live, and the model skips wrap-up as predicted. This is NOT "the gate is installed." Run the retrofit block (write `.githooks/pre-push` + `git config core.hooksPath .githooks`); confirm with `git config core.hooksPath`.
- **Treating the pre-push hook as one option among three** ("I'll just run `make phase-done` myself") → the hook is the default and must be active; model-discipline is additional, not a substitute. The whole point is to not depend on the model remembering.
- **Tagging a task `Archetype: sweep` then adding net surface** → the diff-direction teeth block it. If the add is a real perf win, log `SWEEP-PERF: <evidence>` (human-written, audited at PR); if it is not a cleanup, it was the wrong archetype — re-tag it `build`/`maintain` and run the chain that shape demands. Do NOT add a hollow `SWEEP-PERF:` line to dodge the check; the reviewer reads it.
