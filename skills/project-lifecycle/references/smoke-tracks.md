# Dual-Track Smoke

Every phase that touches a user-visible surface ships **two parallel smoke artifacts**:

- **Track A manual smoke checklist** — markdown doc, runs by hand in a real browser/device
- **Track B Playwright (or equivalent) E2E** — automated, runs in CI + locally

Both required. Neither replaces the other.

## Why two tracks

| Failure mode | Caught by Track A | Caught by Track B |
|---|---|---|
| Visual regression / wrong copy | ✅ | ❌ (unless screenshot diff) |
| Layout break on real viewport | ✅ | 🟡 (depends on assertions) |
| BE 500 / 400 on edge inputs | 🟡 | ✅ |
| Permission gate enforcement | 🟡 | ✅ |
| Performance / animation feel | ✅ | ❌ |
| Cross-account / authorization boundary leak | 🟡 | ✅ |
| Toast / notification fires | ✅ | ✅ |
| Mobile-only bug | ✅ | 🟡 (browser-specific config) |

Track A catches what humans see; Track B catches what code asserts. Neither is sufficient alone.

## Track A — manual smoke checklist

**Path:** `docs/research/YYYY-MM-DD-mX.Y-smoke-checklist.md`

**Structure:**
1. **Preconditions** — exact commands to seed data / start dev servers (`make dev`, `make smoke-seed`, migrations)
2. **Login info** — which fixture user(s) to log in as, and where their credentials come from (the seed script, `.env.example`, or your secret store). Do not paste live passwords into a tracked file, even dev ones
3. **Steps S0–SN** — numbered, each with: action / expected pass criteria / notes
4. **Findings template** — copy-paste structure (see `findings-tier.md`)
5. **End-of-smoke summary template** — final line for "X / N pass, Y findings"

**Per-step format:**
```
| # | Step | Pass criteria | Notes |
|---|---|---|---|
| S1 | Navigate to /foo + click Bar | Modal opens with section X visible | new surface from this phase |
```

**Rules:**
- Steps must be executable by a non-author. No "you know what I mean."
- Pass criteria must be observable (a string appears, a number matches, a button changes color), not inferable.
- Group steps in sections: Setup (S0) / Core flow / Validation surface / Edge cases / Audit log spot check.

## Track B — Playwright E2E

**Path:** `frontend/e2e/mX.Y-<slug>.spec.ts` (or whatever framework convention the project uses)

**Scope:** the **contract level** — API round-trips, permission gates, state transitions. Not pixel-perfect UI.

**Standard scenarios per phase:**
- B1 happy path (create → read → update round-trip)
- B2 validation rejection (the new "must-have" rule blocks invalid input)
- B3 cross-cutting invariant (authorization boundary / data scoping / soft-delete cascade / immutable-after-use guards)

3 scenarios is usually enough. Going beyond 5 adds maintenance cost without proportional value.

**What Track B does NOT cover:**
- Visual polish (copy, color, alignment) — that's Track A
- Real keyboard / mouse interactions on quirky widgets — that's Track A
- Performance perception — neither track; needs a separate perf harness

### Track B Golden Rules (Playwright baseline)

Adopted from the Playwright Skill ecosystem (lackeyjb/playwright-skill, agentmantis/test-skills, neonwatty/qa-skills). Apply unless project's E2E framework conventions override:

1. **`getByRole()` locators first** — a11y-tree-based, semantic, survives DOM refactors. Fall back to `getByLabel` / `getByText` / `getByTestId` in that order. Never CSS / XPath unless no alternative.
2. **Auto-retry waits, never `waitForTimeout(N)`** — `expect(locator).toBeVisible()` / `toHaveText()` retry built-in. Fixed timeouts = flake fuel.
3. **Assert on user-visible state** — "User sees 'Order #123 confirmed'" beats "third div has class `.confirmed`". DOM-structure assertions break on refactor.
4. **Test isolation + fixtures over `beforeEach`** — each test creates its own data + cleans up; Playwright fixtures are typed + parallelizable + auto-cleanup. `beforeEach` is shared state in disguise.
5. **POM when flows repeat** (2+ tests) — encapsulate page interactions behind a class. Premature POM for one-offs = overhead.
6. **Trace + screenshot on failure** — config `trace: 'retain-on-failure'` + `screenshot: 'only-on-failure'`. Cheap debugging gold.

Full reference for E2E pattern depth: lackeyjb/playwright-skill (10 Golden Rules + 46 core guides) or agentmantis/test-skills.

## Coordination

The smoke checklist (Track A) and the Playwright spec (Track B) should reference each other:

- Track A's Findings template explicitly says "if you find it, log it; mention if Track B should also catch it."
- Track B file header includes a comment block listing what Track A covers that Track B does not (visual / UX).

## When the tracks disagree

Track B passes, Track A finds a bug → **always trust Track A.** Add a Track B regression test for the new scenario before declaring the bug fixed. This prevents the same bug from re-shipping.

Track A passes, Track B fails → **debug Track B first.** Either the test is wrong or there's a real bug Track A missed (probably a non-visual one).

## Test runner one-liner

A `make phase-checks PHASE=X.Y` (or equivalent task-runner target) should run the project's BE tests + FE unit tests + E2E suite scoped to the phase. Its output feeds the journal FACT entry's test evidence + the PR body.

Example shape for a Python BE + Node FE project (adapt to your stack):
```make
phase-checks:
	cd backend && pytest $$( [ -n "$$PHASE" ] && echo "-k $$PHASE" || echo "" ) -q
	cd frontend && pnpm exec vitest run $$( [ -n "$$PHASE" ] && echo "-t $$PHASE" || echo "" )
	cd frontend && pnpm exec playwright test $$( [ -n "$$PHASE" ] && echo "e2e/m$$PHASE-*.spec.ts" || echo "" )
```

For other stacks substitute equivalents — e.g. Go + React: `go test ./...` + `pnpm test` + `playwright test`; Rust + Svelte: `cargo test` + `vitest` + `playwright test`. The skill enforces the pattern (one-command phase-scoped check); the commands are project-specific and live in the project's CLAUDE.md.

## Anti-patterns

- Skipping Track A "because we have good Playwright coverage" — Playwright doesn't catch visual regressions or copy bugs.
- Skipping Track B "because the user will catch it manually" — manual smoke doesn't run in CI, regressions slip through PRs.
- Writing Track A AFTER Track B passes — defeats the catch-different-bugs purpose; write them in parallel.
- Track A steps so vague that anyone could pass them ("verify the UI looks right") — make pass criteria observable.
- Marking a step PASS when "it almost worked" — log it as a finding, even if low-tier.
