---
description: Run a PLC-native code review on the current branch's diff (or a given path/range) by dispatching a general-purpose agent briefed with references/reviewer-brief.md. Produces findings under the brief's format — file:line evidence, refute-first, verdict-LAST. It does NOT compute its own approve/block verdict; the controller/human derives that from the open-severity counts.
---

# /review — a PLC-native code review, no external reviewer agent

Wraps PLC's own reviewer prompt (`skills/project-lifecycle/references/reviewer-brief.md`) as a
standalone button — the PLC-native replacement for reaching to an external `code-reviewer` /
`security-reviewer` agent. Symmetric with `/research`: it adds NO new review logic and never forks
the discipline. The brief operationalizes `references/review-record.md` (dispatch constraints,
verdict-computed-not-declared) + `references/cadence.md` (validator vs code-quality lenses +
bloat-smell); this command just dispatches it.

**Guts, not new capability:** the review constraints already exist in PLC. This command dispatches
a general-purpose agent (read-only) with the brief, on a scoped diff.

## Interface

```
/review                          # review this branch's diff vs its merge-base, quality lens (default)
/review --lens security          # security lens (OWASP + secrets/injection/authz)
/review --lens correctness       # validator lens — needs a user-story.md + spec to compare against
/review <path-or-range>          # review a specific file / commit range instead of the branch diff
```

- **`--lens {quality|security|correctness}`** — default `quality`. `correctness` needs a
  `user-story.md` + spec; if neither exists, say so and fall back to `quality`. For a thorough pass,
  dispatch the lenses as **parallel** agents (single message, multiple `Agent` calls) — different
  lenses, not clones (`review-record.md` constraint 8).
- **Argument** — a file path or a `git` commit range. Absent → the current branch's diff against its
  actual merge-base (not a hard-coded `main`).

## Flow (delegates to the brief — do not re-implement here)

1. **Scope.** Resolve the review range: the branch's real merge-base vs its PR base, or the given
   path/range. Note working-tree vs committed.
2. **Detect languages.** Grep the changed files' extensions → select the matching brief
   appendix(es) by heading (they compose for a mixed-language diff; appendices the brief adds later
   are picked up here without editing this command). The base checklist always runs.
3. **Dispatch a `general-purpose` agent, read-only** (Read / Grep / Glob + test-running Bash — never
   Write/Edit) **with an explicit model ≥ the implementer's tier** (`review-record.md` constraint 3 —
   never let the reviewer silently inherit the writer's model), briefed with
   `references/reviewer-brief.md` + the chosen lens + the selected appendix(es) + the scope.
   Optionally pre-seed specific suspicions — the brief requires one unanchored full-diff pass FIRST
   regardless.
4. **Surface** the agent's findings in the brief's format: the strongest-case-against first, then
   per-criterion pass/fail, then findings by severity (each `file:line` + quoted snippet), then
   forward-looking + bloat-smell.
5. **Report severity counts, NOT a verdict.** Show the open Critical/Important/Minor counts; the
   approve/block decision is the controller's/human's to compute from the top-two-tier count.

## Hard rules (inherited from the brief + review-record)

- **No self-verdict.** This command never prints "APPROVED" / "blocked" — it prints findings +
  counts. Approve/block is controller-computed (`review-record.md` constraint 6). An anti-pattern is
  treating a `/review` transcript as the merge gate.
- **Read-only.** The dispatched agent reports; it does not edit or remediate. Fixes route to the
  builder (`review-record.md` §"Between finding and fix").
- **Evidence gate.** A finding that can't quote the code it indicts is dropped before it's reported.

## Not this command's job

- Posting the PR review record (Comment A verbatim + Comment B builder response) — `review-record.md`.
- Applying fixes — the builder adopts findings and re-derives fixes (reviewer snippets are untrusted).
- Modifying `reviewer-brief.md` — both `/review` and the cadence read it; neither forks it.
