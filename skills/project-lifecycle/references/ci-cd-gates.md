# CI/CD Gates

Pre-PR and PR-time checks every project using `project-lifecycle` should enforce. The skill's milestone-done gate (`milestone-done.md`) demands "CI green" without prescribing what CI is — this doc fills that gap.

## Why this matters under AI-driven development

AI agents generate diff faster than a human can read it. Without machinery that catches the common failure modes automatically, every PR becomes a deep manual audit, which kills the velocity AI was supposed to buy. CI is the safety net that lets a phase ship without re-reviewing every line.

Three layers — fail fast at the cheapest one:

```
[local pre-commit]  →  [PR-time CI]  →  [merge protection]
   fast, every       full suite,      configured once
   commit            every push        in repo settings
```

## Layer 1: Local pre-commit (every commit)

Required hooks (use [pre-commit framework](https://pre-commit.com/) or equivalent):

- **Formatter**: language-native (`ruff format`, `prettier`, `gofmt`, etc.). Auto-fix on hook run.
- **Linter**: `ruff check`, `eslint`, `clippy`, etc. Fail on violations.
- **Type checker** for typed languages: `mypy` / `tsc --noEmit` / `cargo check`.
- **Secret scanner**: `gitleaks` or `detect-secrets`. Always.
- **Trailing whitespace + EOF newline + JSON/YAML syntax**: standard `pre-commit-hooks`.
- **Targeted test** (optional but recommended for hot files): run pytest / vitest on the changed module only — full suite is too slow for every commit; do it in CI.

**Forbidden:**
- `--no-verify` on `git commit` / `git push`. If a hook fails, fix the underlying issue. If the hook is wrong, fix the hook config in the same commit.

**Rationale:** pre-commit catches the trivial 80% (format drift, syntax error, leaked `.env`) before they touch CI's queue.

## Layer 2: PR-time CI (every push to the PR branch)

Required jobs (run on every push):

| Gate | What it checks | Tooling examples |
|---|---|---|
| **Format** | No drift from formatter | `ruff format --check`, `prettier --check`, `gofmt -l` |
| **Lint** | No new violations | `ruff check`, `eslint`, `clippy -D warnings` |
| **Type check** | No type errors | `mypy`, `tsc --noEmit`, `cargo check` |
| **Unit + integration tests** | Test suite passes | `pytest`, `vitest`, `go test ./...` |
| **Coverage floor** | At or above project floor | `pytest --cov`, `vitest --coverage`, `go test -cover` |
| **Schema drift** | Generated artifacts not stale | `make schema && git diff --exit-code` for OpenAPI / GraphQL / TS types |
| **Migration round-trip** (Django/Rails-style) | Migrations apply + reverse cleanly | `python manage.py makemigrations --check --dry-run`, `migrate --plan` |
| **Codemap drift** (if `make codemap` pattern adopted) | Codemaps not stale | `make codemap-check` (exit non-zero on drift) |
| **Security scan** | No new high-severity findings | `bandit`, `pip-audit`, `npm audit`, `cargo audit` |
| **E2E** (Track B) | Playwright (or equivalent) green | `playwright test` against a built preview |

**Optional but valuable:**
- **Branch name check**: enforce `feat/phase-X.Y-<slug>` convention.
- **Commit message lint**: enforce `<type>(mX.Y/...): ...` convention.
- **PR title lint**: enforce conventional commits or include `[mX.Y]` tag.
- **Bundle size diff** for frontend: report on PR comment.

> The handoff file was retired (see `references/handoff-template.md`) — its one non-derivable
> section (§7 findings/gotchas) now lives in the journal fragment under the FACT schema, checked
> deterministically by `close-gate.sh phase`'s journal-touched row instead. There is no equivalent
> per-phase-tag CI assertion to run in its place; a phase's journal-touched check already covers it.

## Layer 3: Merge protection (configured once per repo)

GitHub / GitLab branch protection rules on `main`:

- Require PR before merge (no direct push).
- Require all Layer 2 status checks to pass before merge.
- Require at least 1 approving review (or self-review for solo developers with `dismissStaleReviews: true`).
- Require branches to be up-to-date before merge (force a rebase / merge-from-main).
- Require linear history OR require merge commits — pick one and stick.
- Block force pushes to `main`.
- Restrict who can push to `main` (limit to merge-via-PR).

For solo-developer + AI workflows (no co-reviewer available), the practical setup:

- Require status checks ✅
- Require linear history ✅
- Block force pushes to main ✅
- Required reviews: 0 (you ARE the reviewer; the PR review IS the human checkpoint)

## Anti-patterns

- **Pre-commit hooks ran first time at PR open** — wastes the CI queue on format drift the local hook would have caught in 200ms. Run hooks on every commit.
- **`--no-verify` on a "trivial" commit** — every untriggered hook is a future regression. If the hook is wrong, fix the hook config; don't bypass it.
- **CI that only runs `pytest`** — no lint / type / coverage = code passes that should have failed.
- **Coverage threshold set to current% then never raised** — make it part of the milestone-done gate to raise the floor by 1–2pp per milestone.
- **Schema drift discovered post-merge** — block in CI. Stale generated types break downstream consumers silently.
- **Force-pushing to a PR branch after review** — destroys review history. Use new commits + auto-resolve "stale review" on merge.
- **Single "CI" job that does everything** — when it fails, you can't tell which gate broke. Split into named jobs so the GitHub UI surfaces the specific failure.

## Tie-in to milestone-done gate

The `milestone-done.md` hard gates assume Layer 1 + 2 are in place:

- "Linter / formatter / type checker clean across changed files" → Layer 1 + 2 enforce.
- "Automated test suite green" → Layer 2.
- "Generated artifacts regenerated and committed" → Layer 2 (schema drift check).
- "Pre-commit run on all changed files locally before final push" → Layer 1.
- "PR opened, CI green, merged to main" → Layer 2 + Layer 3.

Without Layer 1 + 2 + 3 in place, the milestone-done gate is honor-based and will drift. Set up CI before the first phase ships.

## Minimum first-week setup checklist (for a new project)

- [ ] `pre-commit-config.yaml` with formatter / linter / type / secret-scan / EOF / whitespace hooks.
- [ ] CI workflow (GitHub Actions / GitLab CI / etc.) running format + lint + type + test on every push.
- [ ] Coverage tool wired (`pytest-cov`, `vitest --coverage`, etc.) with a project floor in CI.
- [ ] Schema-drift check in CI for any codegen artifact.
- [ ] Branch protection on `main` requiring CI green + no force push.
- [ ] `make phase-checks PHASE=X.Y` target (or equivalent) for local one-shot runs.

When these exist, the per-phase workflow can rely on "CI green" as a real signal. Until they exist, build them as task one of the first phase.

## Anti-pattern that hurts AI-driven work specifically

AI agents tend to over-generate "fix" attempts when CI fails — try lint fix, re-push, lint fails differently, etc. **Surface the actual diff to a human or to the agent's controller after 2 failed CI runs on the same PR.** Indefinite "let CI guide me" loops burn money and produce frankenstein commits.

## CI-billing-paused fallback (Pattern E)

### Decision: try CI first; fall back only on confirmed billing block

**Default path always tried first.** Open the PR, push, watch the CI workflow run. Trigger `@copilot review` once CI is green. Do not pre-emptively skip CI because it was blocked in a prior phase — re-verify each phase. Billing can be topped up, repos can be made public, runner config can change. Skipping CI without verifying it's still blocked wastes the chance to get green CI signal.

**Switch to Pattern E (fallback) ONLY when** one of these conditions is observed *for this PR*:

| Trigger | Signal | Action |
|---|---|---|
| CI workflow refuses to start | GitHub web UI shows red ✗ with body `The job was not started because recent GitHub Actions payments have failed or your spending limit needs to be increased` | switch workflow to `workflow_dispatch` dormant + run R5 locally |
| Copilot review job aborts mid-run | PR conversation shows `Copilot stopped work ... due to an error` linking to the same billing message | drop Copilot loop + dispatch a general-purpose reviewer stand-in (per `references/reviewer-brief.md`) |
| Self-hosted runner registration fails | `api.github.com/actions/runner-registration` returns `404` | Actions is disabled at the account; same fallback applies |

If none of the above triggers fire for the current PR, **use the default path**. Pattern E is a fallback, not the new normal.

### Why these specific errors

**Copilot's PR-review job runs on Actions infrastructure**, so the `@copilot review` loop also stops working when Actions billing is blocked — the first pass usually completes (the review-spawn job had already started before the billing hit), but re-triggers silently die. The audit table above is the only reliable way to detect this from the AI controller's side.

### Two failure modes that are NOT acceptable

- Delete the workflow file (loses the spec at the conventional location; new contributors see empty `.github/workflows/` and assume no CI ever existed).
- Keep `on: push/pull_request` + accept perpetually-red ✗ checks (trains reviewers to ignore CI status; when billing returns and a real failure surfaces, the team overlooks it).

### Pattern E — workflow_dispatch dormant

Keep the workflow file in the repo. Change its trigger to manual-only. Document the restoration path inline.

```yaml
name: test

# ──────────────────────────────────────────────────────────────────────────────
# DORMANT (workflow_dispatch only) while GitHub Actions billing is blocked.
# The workflow stays in-repo as the canonical CI spec; auto-trigger
# on push / PR is disabled so PRs are not polluted by inevitable billing-blocked
# failures.
#
# **To restore auto-CI once billing is resolved:**
#   Replace the `on:` block below with the standard triggers:
#     on:
#       push:
#         branches: [main]
#       pull_request:
#   Commit + push. Auto-runs resume immediately on the next push/PR.
#
# **Until then — local R5 verification protocol:**
#   <type-check>                                       # 0 errors
#   for i in 1 2 3; do <test runner> || exit 1; done   # 3/3 unit+integration green
#   for i in 1 2 3; do <e2e runner> || exit 1; done    # 3/3 regression/e2e green
#   Post the output as a PR COMMENT (not the body) per ci-cd-gates §"Posting test evidence".
# ──────────────────────────────────────────────────────────────────────────────

on:
  workflow_dispatch:

jobs:
  test:
    runs-on: ubuntu-latest    # canonical target for when CI returns
    steps:
      # ... unchanged from the active workflow
```

**Why this beats deleting the file:**

- **Observability**: future-me / future contributor / future Claude looks at `.github/workflows/` (the convention location) — finds the workflow + the header comment explains why it's dormant + how to restore. No hunting through git log or handoff docs.
- **Traceability**: the spec lives at the conventional location, baked in YAML, version-controlled. Restoration is a 4-line `on:` block edit, not a re-write.
- **No PR pollution**: workflow_dispatch doesn't auto-trigger on push or PR, so there's no perpetually-red `test (pull_request)` check. PR status reads cleanly.
- **Manual triggering still possible**: if billing returns intermittently, owner can click "Run workflow" in GH Actions UI to do a one-off validation without code changes.

### Local R5 verify protocol (the substitute for CI runs)

Document this in the workflow header comment itself (see the DORMANT block above) — that's the live, version-controlled copy; there is no separate handoff doc to mirror it into.

**Full gate — ALL three layers, ALL three runs:**

```bash
<type-check>                                        # must be clean (e.g. `tsc --noEmit` / `mypy` / `cargo check`)
for i in 1 2 3; do <unit test runner> || exit 1; done     # R5: 3 consecutive green runs (e.g. `bun test` / `pytest -q` / `go test ./...`)
for i in 1 2 3; do <e2e runner> || exit 1; done           # R5: 3 consecutive green runs (e.g. `playwright test`)
```

**Skipping the e2e layer because "this phase is BE-only" is a Pattern E violation.** The R5 gate exists to prove the whole project still works after this phase's diff — that includes existing UI tests, not just the tests touched by this phase. A BE-only phase that breaks an existing e2e is exactly what R5 catches.

## Posting test evidence — required as a PR comment (both paths)

Whether you ran via default CI or local Pattern E, the test evidence MUST be posted as a **separate PR comment**, not buried inside the PR description body. This rule applies to BOTH paths — only the source of the output differs (CI run page link vs local run paste).

### Why a comment, not the body

- **Visibility**: a comment appears in the PR thread feed; the body is collapsed below the diff and easy to miss during review.
- **Audit trail**: comments are timestamped + attributable; the body is editable and history is hidden behind a "modified" badge.
- **Re-runs**: when fixup commits land and tests are re-run, a new comment is posted with the new evidence — the thread shows the progression. A body edit overwrites the prior evidence and loses the trace.
- **Reviewer expectation**: external reviewers (Copilot, a general-purpose reviewer subagent, human collaborators) read the thread top-to-bottom; the body is treated as a summary, not a proof artifact.

### Required fields (same for both paths)

Use `gh pr comment <PR#> --body "..."` (or equivalent). Comment must include:

1. **Header** with timestamp + environment + branch + HEAD sha + path used ("default CI" or "Pattern E local"). For Pattern E: link to ci-cd-gates §Pattern E so reviewer sees the decision rationale.
2. **Type-check output** (`tsc --noEmit` / `mypy` / `cargo check`) — must be clean.
3. **Unit test output × 3 consecutive runs** — flake-check; pass count must be identical or strictly increasing.
4. **Integration test output × 3 consecutive runs** — if integration runs as a separate suite. If integration is folded into the unit suite, note that explicitly.
5. **Regression / e2e test output × 3 consecutive runs** — Playwright or framework equivalent. Even on BE-only phases (existing UI tests catch silent regressions).
6. **Phase-specific suite outputs** — any new test files this phase introduced (e.g. `tests/<area>/<phase>-<surface>.test.<ext>`, Track B smoke harness).
7. **Track A manual smoke summary table** (if user-visible phase) — stages × cases × pass/fail.
8. **Findings tally** — S1 (must-fix-before-merge) / S2 (ship with follow-up) / S3 (forward-looking backlog) counts. For each deferred S3, list Trigger + Exit criteria.
9. **Copilot or stand-in review status** — for default path: "@copilot review triggered → N findings → resolved in <SHA>". For Pattern E: "Copilot job aborted with billing error → stand-in subagent dispatched → APPROVED-CLEAN at <SHA> (derived: zero open CRITICAL/IMPORTANT in pass-2 findings)".
10. **Merge-readiness statement** — "Ready for merge; will flip RESUME post-merge" / "Blocked on X" / "Awaiting human Track A confirmation".

### Default-path specifics

- Link to the CI run page in the header (`https://github.com/<owner>/<repo>/actions/runs/<run-id>`) — reviewer can click through to see raw logs without you pasting them.
- Still paste a summary block per gate (last 5-10 lines of output) so the thread is self-contained if the CI logs expire.
- Copilot inline findings are captured in the per-finding inline replies + the fixup commit body (`Fx-NN`); the evidence comment lists Copilot status at the summary level only.

### Pattern E specifics

- No CI run page exists — paste the full local output verbatim in code blocks.
- For each command, capture stdout + exit code marker so future readers can spot a silently-ignored failure (e.g. `(exit 0 — empty output = clean)` for `tsc --noEmit`).
- Stand-in status field gets two sub-bullets: pass 1 findings (with resolution per finding) + pass 2 re-loop verdict.

**Anti-pattern:** test evidence only in the PR body — violates the audit-trail rule, both paths.

### Copilot review when Actions is billing-blocked

Copilot's 1st pass usually completes (the review job already started); subsequent `@copilot review` triggers fail silently with the same billing error. When this happens:

- **Address every 1st-pass finding** per the standard `copilot-review-loop.md` protocol (inline reply per finding, fixup commit with Fx labels).
- **Dispatch an independent general-purpose reviewer** (briefed per `references/reviewer-brief.md`) as the review gate — Copilot is advisory, so this is the actual reviewer, not a substitute for one. Brief it with: "Copilot's pass is advisory and blocked by external infra; you are the review gate. Verify the fixup commit addresses each 1st-round finding correctly + spot-check for regressions the fixup might have introduced."
- **Apply that subagent's findings** before merging — its computed verdict (per `references/review-record.md` §"Termination contract") is the merge gate; Copilot's findings were only ever advisory.
- **In the PR body**, note: "Copilot 2nd pass blocked by Actions billing; an independent general-purpose reviewer acted as the 2nd reviewer (see `<short summary of findings>` resolved in `<sha>`)."

### When to revert Pattern E

The moment billing is restored:

1. Edit the workflow file `on:` block back to push/pull_request triggers.
2. Push.
3. Verify auto-runs resume on the next PR push.
4. Remove the dormant comment block (or leave it as historical evidence — owner's choice).
5. Remove the dormant workflow header comment's "local-only R5" language (or leave it as historical evidence per step 4) — the header comment is the only place that language lived.

The Pattern E commit + the restoration commit together form a clean audit trail of *why* CI was off during that interval — useful for retrospectives and for any phase whose merge was bottlenecked by the pause.

### Anti-patterns specific to Pattern E

- **Switching back to `on: push/pull_request` without first verifying billing is actually restored** — auto-runs immediately re-fail with the same billing error, re-polluting PRs.
- **Skipping the local R5 3× loop just because there's no CI gate** — the 3× is the flake-guard, not just CI ceremony. Run it locally.
- **Letting the workflow file rot** (out-of-sync with current build commands, test runner names) — when restored, the workflow will fail for *new* reasons. Treat it as living documentation; update it whenever the project's `package.json` scripts / test runner / e2e config changes.
- **Documenting the local R5 protocol only in a chat session** — owner forgets the protocol three phases later. Bake it into the workflow header comment (the version-controlled, conventional-location copy).
