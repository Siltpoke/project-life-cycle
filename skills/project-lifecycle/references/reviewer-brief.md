# Reviewer brief — the PLC-native review prompt

This is the prompt you dispatch to a **general-purpose agent** (read-only) to run a PLC code review,
replacing any by-name dependency on an external `code-reviewer` / `security-reviewer` agent. It is the
PLC-owned button behind `commands/review.md` and the referent every cadence/CI review site points at.

**Delegation — this brief does not fork the discipline.** The review *constraints* are owned by
`references/review-record.md` (the 8 dispatch constraints, verdict-computed-not-declared, the
bidirectional PR record) and `references/cadence.md` (steps 2/3 — validator vs code-quality lenses +
the bloat-smell checklist). This brief only **operationalizes** them into a dispatchable prompt. When
the two disagree, `review-record.md` + `cadence.md` win — fix this brief to match, never the reverse.

---

## Dispatch preamble — the reviewer's opening moves

Give the agent read-only tools (Read / Grep / Glob + test-running Bash). Never Write / Edit — a
reviewer that can edit absorbs findings into silent fixes and the audit trail dies
(`review-record.md` constraint 2). Brief it to:

1. **Establish scope.** Determine the real review range — the branch's actual merge-base against its
   PR base (NOT a hard-coded `main`), committed vs working-tree, and confirm merge-readiness/CI state
   if relevant. State the exact commit range and an explicit **"not reviewed"** negative-space list
   (`review-record.md` §Comment A scope header).
2. **One unanchored full-diff pass FIRST**, then any pre-seeded suspicions the dispatcher injected —
   so attention isn't anchored to only what the writer already suspects (`review-record.md`
   constraint 7).
3. **Read surrounding context, not just the diff hunk** — a finding needs the code around it to be
   real.
4. **Report findings; do not edit, refactor, or remediate.** Fixes are the builder's job
   (`review-record.md` §"Between finding and fix").

## Lens selector — dispatch ONE lens per agent (different lenses, not clones)

Per `review-record.md` constraint 8, multiple reviewers each get a **distinct** lens/prompt (ideally
distinct tier); N identical reviewers just vote their shared blind spots. Pick the lens for the run:

- **`quality`** (default; the code-quality lens, `cadence.md` step 3) — is the implementation
  well-built? Design, naming, error handling, performance, test quality, **+ forward-looking +
  bloat-smell** (below).
- **`security`** — OWASP Top-10 + secrets / injection / authz / crypto / deserialization (below).
- **`correctness`** (the validator lens, `cadence.md` step 2) — correctness-vs-promise: AC coverage,
  scope drift (over- and under-build), spec adherence, folder boundaries, plus the lie-detection
  pass (does the diff actually implement each claimed-closed AC; does "success" code perform the
  action or merely log it). **Needs a `user-story.md` + spec** to compare against; fall back to the
  `quality` lens when neither exists, and say so.

For a thorough pass, dispatch these as **parallel agents** with distinct prompts (single message,
multiple `Agent` calls) rather than one mega-review.

## Base checklist — language-generic (runs under every lens as relevant)

- **Security** — hardcoded secrets, injection (SQL / command / path traversal), XSS, auth/authz
  bypass, insecure deserialization, weak crypto, secrets in logs.
- **Error handling** — swallowed / bare exceptions, empty catch, missing resource cleanup, throwing
  non-Error, unhandled async rejections.
- **Structure** — functions over the project's line cap, files over the cap, nesting past ~4 levels,
  duplicate logic, dead code, magic numbers. Reuse the project `CLAUDE.md` numbers when present, don't
  invent limits.
- **Immutability** — prefer new objects over in-place mutation where the codebase does.
- **Input validation at boundaries** — schema-validate external data (user input, API responses,
  file content).
- **Performance** — N+1 queries, O(n²) on unbounded input, missing caching, blocking I/O in async
  paths, unbounded queries.
- **Hygiene** — debug logging left in (`console.log` / `print` / orphan `[DEBUG-*]`), poor naming,
  `TODO`/`FIXME` without a ticket, missing docs on public APIs.

**Plus PLC-unique — forward-looking findings.** Call out anything that works for the current spec but
a downstream task will be hurt by (e.g. a generated artifact uses an unstable name a not-yet-written
consumer will need stable). A finding *category*, orthogonal to severity (`cadence.md` §"Step 2: Validator" — forward-looking findings).

**Plus PLC-unique — the bloat / overcomplication smell.** LLM default is over-abstracted code. Run
this checklist **explicitly**, as its own pass — not implicitly inside "design" (`cadence.md` §"Step 3: Code quality review" — the bloat-smell checklist):

```
Bloat smell checklist:
  [ ] Line-count delta vs task complexity sane? (e.g., "add validation" producing 200+ lines = flag)
  [ ] Any abstraction created for single use? (helper class with one caller, factory for one product, interface with one impl) → flag
  [ ] Any configurability / flexibility the task did NOT request? (options object, strategy pattern, plugin point) → flag
  [ ] Any error handling for impossible scenarios? (internal-only callers, framework-guaranteed invariants) → flag
  [ ] Any features beyond the spec? (logging, metrics, retry, caching the user didn't ask for) → flag
  [ ] "Would a senior engineer call this overcomplicated?" → if yes, flag
  [ ] Could this be ~half the lines and still solve the problem? → if yes, flag with the simpler shape sketched
```

## Language appendices — attach by changed-file extension (they compose)

The dispatcher greps the diff's file extensions and appends the matching appendix (or several, for a
mixed-language diff). The base checklist ALWAYS runs — a missed appendix degrades to generic coverage,
never to zero. Extensible: add `### Appendix: Go` / `Rust` / … the same way later.

### Appendix: TypeScript / JavaScript
- `any` / non-null-assertion (`!`) / `as`-cast abuse; weakening `tsconfig` strictness.
- Floating promises; `async` callback in `forEach`; `==` vs `===`; `var`; prototype pollution.
- **React / Next sub-block** — hooks dependency arrays, effect cleanup, server/client boundary leaks
  (secrets or server-only imports reaching client bundles), unstable keys.
- Diagnostics (read-only Bash): run the project's typecheck (`tsc --noEmit` or equivalent) + lint +
  tests before reporting; a floating-promise flagged with a green typecheck is stronger.

### Appendix: Python
- Type-hint coverage on public surfaces; `Any` overuse; mutable default args; builtin shadowing.
- `isinstance` over `type() ==`; `is None` over `== None`; comprehensions over manual loops where
  clearer; unsafe YAML load; framework checks (Django `select_related`/N+1, FastAPI Pydantic
  validation, Flask CSRF).
- Diagnostics (read-only Bash): run the project's type checker (mypy/pyright) + linter (ruff/flake8) +
  tests before reporting.

## Severity — reuse PLC's scale, do NOT invent a new one

Canonical scale for findings: **Critical / Important / Minor**, matching the cadence's own step-2/3
report headers (`cadence.md` §"Step 3" report headers) and the Copilot family (`copilot-review-loop.md`). This is a
*declared rebase*, not a fork: `review-record.md` constraint 6 names CRITICAL/HIGH/MEDIUM/LOW as ITS
default but explicitly rules that the controller counts the active scale's top two tiers as
merge-blocking — **"whatever the scale"**; this brief picks the 3-tier scale the cadence actually
emits and consumes, under that same rule (top two = Critical + Important are merge-blocking).
**Forward-looking** and **Bloat-smell** are orthogonal *categories*, not severities — each carries its
own Critical/Important/Minor severity.

If an appendix or upstream source hands you a `CRITICAL / HIGH / MEDIUM / LOW` scale, normalize
through the `review-record.md` constraint-6 mapping — **do not carry a parallel scale**:

| Incoming | PLC severity |
|---|---|
| CRITICAL | Critical |
| HIGH / MEDIUM | Important |
| LOW | Minor |

Merge-blocking = the top two tiers (Critical + Important), **counted by the controller**, not asserted
by you (next section).

## Output format — refute-first, verdict-LAST, evidence-gated

Per `review-record.md` constraints 4-6, structure the report in this order:

1. **The strongest case against this diff / its likely failure modes** — FIRST, before any per-item
   analysis. Reasoning-before-verdict measurably improves judge quality.
2. **Per-lens / per-criterion analysis** (pass/fail per criterion).
3. **Findings, grouped by severity** — each with `file:line` + a **quoted snippet** of the code it
   indicts + a one-line fix *as guidance* (not gospel — the builder re-derives; your snippet is
   untrusted input). **A finding that cannot quote the code it indicts is discarded before you report
   it** (evidence gate, `review-record.md` constraint 5).
4. **Forward-looking** findings.
5. **Bloat-smell** findings.
6. **NO self-declared verdict.** Emit per-criterion pass/fail + severity-tagged findings and STOP.
   "Approved / blocked" is **computed by the controller** from open top-two-tier counts — never a
   reviewer-stated boolean (`review-record.md` constraint 6; anti-pattern: reviewer-stated "APPROVED"
   treated as the gate).

Keep signal high: report only findings you're confident in, consolidate near-duplicates, and skip
pure style noise. **If the diff is clean, say so plainly — do NOT invent minor findings to look
thorough** (`cadence.md`).

## Not this brief's job

- The **builder-side** finding→fix rules (routing split, one-fix-one-commit, reviewer-snippets-are-
  untrusted, mandatory final pass) — those live in `review-record.md` §"Between finding and fix" /
  `cadence.md` step 4. This brief is the reviewer side.
- Posting the **PR review record** (Comment A verbatim + Comment B builder response) — that's
  `review-record.md` §"The review record".
- Being a **verdict authority** — the controller/human computes approve/block; this brief only
  produces the findings that count is taken over.
