# PR comment template — the audit-narrative layer

> Complement to `references/ci-cd-gates.md` §"Posting test evidence". That spec covers **proof that tests passed** (raw type-check / unit×3 / integration×3 / regression×3). This spec covers the **audit narrative** — the layers that make the PR easy to review long after it's merged.
>
> Both go in the same PR comment. The raw evidence goes inside a folded `<details>` block at the bottom; the audit narrative is the visible body.
>
> Audience: anyone (human reviewer, future you, an auditor 6 months later) who needs to answer "what changed, what's the user-visible effect, does it work, what's known broken, what should I audit." They should NOT need to clone + run + grep the diff to know this.

## Why this layer exists

Reviewing a PR strictly via diff is expensive: every file change is a fragment with no narrative. A folded `<details>` of raw test logs proves tests passed but does NOT tell the reviewer what was DEMONSTRATED about the new feature.

The audit-narrative layer answers the questions a reviewer (or future-you) actually has:

- **Does the new thing work when I run it?** → Layer 1 (golden-path demo).
- **Do error paths handle gracefully?** → Layer 2 (negative-path demo).
- **What's the user-visible value vs before?** → Layer 3 (before/after).
- **What does it cost to use?** → Layer 4 (cost transparency, only relevant for LLM-using / paid-API features).
- **Does it meet the published perf targets?** → Layer 5 (gates measured vs target).
- **What's intentionally broken or deferred?** → Layer 6 (findings tier).
- **Did the gate actually fire?** → Layer 7 (close-gate output paste).
- **What should I specifically audit?** → Layer 8 (reviewer asks).
- **What's coming next?** → Layer 9 (carry-forward).
- **Proof tests passed?** → folded `<details>` (raw evidence per ci-cd-gates §"Posting test evidence").

Without these layers a reviewer either skips the PR (rubber stamp) or burns 30+ minutes clone+run+grep just to form an opinion. With them a reviewer scrolls top-to-bottom in 5 minutes and lands at a confident merge / block / change-request decision.

## The 9-layer structure (mandatory order)

Use exactly this section order. Reviewers learn the shape once; subsequent PRs land in the same layout = lower cognitive cost.

```
## 🎬 Layer 1 — Demo (golden path)
## 🚨 Layer 2 — Demo (negative paths)
## 🔄 Layer 3 — Before / After
## 💵 Layer 4 — Cost transparency  ← optional (LLM / paid-API features only)
## ⚡ Layer 5 — Performance vs targets
## 🐛 Layer 6 — Findings (PLC tier S1/S2/S3)
## 🔒 Layer 7 — close-gate output
## 👀 Layer 8 — Reviewer asks
## 🛣️ Layer 9 — What's next

<details>
<summary>📜 Raw test evidence (audit layer)</summary>
... ci-cd-gates §"Posting test evidence" 10-field block ...
</details>
```

Skip a layer ONLY when the reason is **structurally impossible** to fill (e.g., Layer 4 cost transparency on a feature with no paid call). Write `(N/A — <reason>)` rather than removing the heading; the empty heading proves the layer was considered, not forgotten.

## Per-layer rules

### 🎬 Layer 1 — Demo (golden path)

**One concrete command per major user-facing surface, with real stdout.** Not test output — actual invocation as a user would run it.

For each demo block:

```
### <AC#> — <one-line description>

$ <exact command>
<verbatim real stdout, NOT a test mock>

Real wall time: <N s>. <Cost / cache state / etc. if applicable>.
```

Rules:

- **Real run, not test fixture**. The point is to prove the feature works end-to-end against a realistic environment. Test-fixture output buried in `<details>` is fine; it's not Layer 1.
- **Include the AC ID** the demo verifies. Cross-references back to `user-story.md` make later audits easy.
- **Show only the interesting parts** of long outputs (truncate w/ `[...]` markers). Reviewer doesn't need 100 KB of JSON.
- **Demo 3-5 surfaces, not 1**. A single demo is a screenshot; 3-5 cover the breadth.
- **For dashboard / SSR routes**: embed Playwright screenshots (see "Visual capture" below). Don't paste HTML source.

### 🚨 Layer 2 — Demo (negative paths)

**Error handling is also a feature.** Negative paths are the most-skipped review surface; surface them deliberately.

Pattern per negative path:

```
### <AC#> — <error description>

$ <command that produces error>
<verbatim error output>

<exit code / no-side-effect verification>
```

Rules:

- **Show the actual error text the user sees**. Not "throws SomeError" — the literal stderr/stdout.
- **Confirm exit code** explicitly (`; echo $?` after the command, OR `$ <cmd>; echo "EXIT: $?"`).
- **For commands that should NOT write state**: prove it by checking the would-be-touched path is unchanged (`ls`, `wc -l`, etc.).
- **Cover at minimum**: bad input, missing prerequisite (e.g., "config not found"), boundary condition (e.g., cap exceeded), auth-fail (if applicable).

### 🔄 Layer 3 — Before / After

**Two-column table or paired before/after blocks.** Pulls the reviewer's attention to the value change, not the implementation change.

```markdown
| Action | Before | After |
|---|---|---|
| <user-facing task> | <effort / steps / time> | <effort / steps / time> |
```

Rules:

- **From the user's POV, not the implementer's**. "Now uses dependency injection" is NOT a before/after row; "user types 1 slash instead of grep+read+open" IS.
- **Quantify where you can**: "30 s vs 3 min", "1 slash vs 5 steps", "$0.07 vs unknown".
- **3-5 rows max**. More dilutes the narrative.

### 💵 Layer 4 — Cost transparency (LLM / paid-API features only)

**Only include for features that call paid APIs.** Skip entirely for pure code / pure deterministic features.

Pattern:

```markdown
| Action | Cost | Notes |
|---|---|---|
| <demo step> | $X.XX | <fresh / cached / aborted, soft/hard cap state> |
| ... |
| **Total session** | $X.XX | <N fresh + M cached + K aborted> |
```

Rules:

- **Real measured dollars, not estimates**. If you ran the smoke for real (on a real run), report what was actually charged.
- **Show cap interactions**: how many calls hit soft warn / hard abort. Proves cost guards live.
- **Total session line** so the reviewer sees the audit cost in aggregate.

### ⚡ Layer 5 — Performance vs targets

**Table: each published go/no-go gate vs the live measurement.** Reviewer instantly sees what passes by how much.

```markdown
| Metric | Target | Measured | Margin |
|---|---|---|---|
| <gate name> | <target value> | <measured value> | <headroom %> |
```

Rules:

- **Targets come from the spec / user-story go/no-go gates section** — don't invent them.
- **Measured values come from real runs**, same session as Layer 1-2 demos.
- **Margin column is optional but recommended** — surfaces a 3× headroom (comfortable) vs 1.1× (on the edge → might regress later).

### 🐛 Layer 6 — Findings (PLC tier)

**Per `references/findings-tier.md`**: S1 blocks merge / S2 ships with follow-up / S3 carry-forward.

```markdown
| ID | Tier | Status | Detail |
|---|---|---|---|
| F<NN> | S<1/2/3> | <block / fix / accept-deferred / done-in-this-PR> | <one sentence> |
```

Rules:

- **Include findings done IN this PR** with status `done in this PR` — they're part of the audit story.
- **For each S2 / S3, give explicit Trigger + Exit criteria** (or link to where they're recorded).
- **S1 with status `block`** = surface to user; do NOT merge until S1 → S2 or S1 → fixed.

### 🔒 Layer 7 — close-gate output paste

**Literal `bash scripts/close-gate.sh phase X.Y` stdout in a code block.**

```
$ bash scripts/close-gate.sh phase X.Y
✓ ...
✓ ...
── close-gate PASS
```

Rules:

- **Run the gate IMMEDIATELY before posting the comment**, so the output reflects the same SHA the PR is at.
- **Both `phase A` AND `phase B` if the PR touches multiple phases** (e.g., a Phase B PR that also carries Phase A retro).
- **Pre-push hook output also counts** as gate evidence — paste the `pre-push: phase branch '...' → running close-gate` block if helpful.

### 👀 Layer 8 — Reviewer asks

**Numbered list, specific things you want the reviewer to audit.** Not "please review the PR" — pointed questions.

```markdown
1. **<thing 1>** — <why this needs second eyes>. <Where the code is>.
2. ...
```

Rules:

- **3-5 asks, not more**. Reviewers ration attention; long lists get rubber-stamped.
- **Each ask points at a specific file:line or design decision**, not a vague "look at security".
- **If you have a strong opinion on the answer, state it** so the reviewer can disagree explicitly rather than reverse-engineer your judgment.

### 🛣️ Layer 9 — What's next

**Bullet list of locked follow-ups + their state.** Sets reviewer expectation for what's deferred.

- **<next milestone / phase>** (LOCKED, Decisions log <date>) — one-line scope.
- **<follow-up finding>** (S2/S3) — scheduled for <phase / hot-fix PR>.

Rules:

- **Only LOCKED items** (decisions log entry exists OR explicit "we will do X" statement). Speculation belongs in Icebox, not this layer.

## Visual capture (Playwright screenshots) — for any user-visible UI surface

When the PR ships UI / SSR routes / dashboard pages, **a dedicated Playwright spec captures screenshots**, NOT just `screenshot: 'only-on-failure'` config.

Pattern:

1. **Dedicated spec file** `tests/e2e/<phase>-screenshots.spec.ts` (separate from functional asserts).
2. **Each scenario sets up its fixture, navigates, screenshots, full-page**:
   ```ts
   await page.screenshot({
     path: join(SHOT_DIR, "01-list-page.png"),
     fullPage: true,
   });
   ```
3. **Output dir**: `docs/pr-drafts/screenshots/` (committed for audit).
4. **Numbered filenames** by user-flow order (`01-`, `02-`, `03-`) so reviewer scans in sequence.
5. **Embed in PR comment Layer 1 (or Layer 2 for error-state UI)** — embed strategy depends on repo visibility:
   - **Public repo** → inline image via raw URL **anchored to the merge commit SHA, NEVER the branch name** (branches get deleted on merge → image 404s):
     ```markdown
     ![<alt + AC ref>](https://raw.githubusercontent.com/<owner>/<repo>/<sha-or-main>/docs/pr-drafts/screenshots/01-list-page.png)
     ```
     Use `main` after merge OR the squash commit SHA. Branch-name URLs are TIME BOMBS.
   - **Private repo** → `raw.githubusercontent.com` requires an auth token; GitHub PR comments cannot pass one, so inline `![](...)` markdown silently 404s. Use one of:
     - **Link-to-blob form** (always works, never expires, but reviewer has to click through):
       ```markdown
       - **AC<NN> <surface>** → [view 01-list-page.png on GitHub](https://github.com/<owner>/<repo>/blob/main/docs/pr-drafts/screenshots/01-list-page.png)
       ```
       Reviewer clicks through to GitHub's file browser; the PNG renders in its file-preview pane.
     - **Web-UI drag-drop (the only true-inline path on private repos)** — manual step: open the PR / issue in browser, click the comment's `…` → Edit, drag the PNGs into the editor; GitHub uploads to its CDN and inserts a `https://private-user-images.githubusercontent.com/...` URL that authenticates against the reviewer's session. AI cannot script this:
       - **Do not attempt `gh gist create --public` as a workaround** — Claude Code auto-mode classifier (and any reasonable security policy) blocks uploading internal-repo screenshots to public GitHub Gist as data exfiltration. The block fires silently; budget burned for no result.
       - **`gh pr edit` / `gh pr comment --edit-last` cannot pass file attachments** to the GitHub upload endpoint that the web UI uses (it requires a session token and the multipart form the official API does not expose).
       - **Right path for AI**: prepare the PR comment with the link-to-blob form so reviewers can click through immediately, then **explicitly instruct the user (in chat + in the comment itself)** to drag-drop the PNGs via web UI if they want true inline rendering. State the 6-step recipe (open PR → find comment → Edit → drag PNG per line → GitHub auto-inserts inline markdown → Update comment). Open the screenshots directory in a file browser via `open <path>` (macOS) / `xdg-open` (Linux) / `explorer` (Windows) as a courtesy so the drag source is one click away.
       - **`--edit-last` discipline**: once the user drag-drops, their inline `![](https://private-user-images.githubusercontent.com/...)` URLs land in the live comment. The corresponding scratchpad draft still has link-to-blob URLs. Either (a) sync the draft to match the live (by editing in the inline URLs) so future `--edit-last` doesn't regress to link-to-blob, or (b) live with the divergence + document it in a note at the top of the draft. The skill prefers (a) for fidelity while the session lasts.
6. **3-5 captures**, not 1. Cover: empty state / populated state / error state / interactive state.
7. **Use deterministic fixture IDs** that match any project-specific regex guards (e.g., `f23000000ace` for a 12-hex `[a-f0-9]{12}` constraint). Cleanup in `afterAll`.

The screenshot spec is committed in the same PR + lives in the regression suite forever. Future UI changes regenerate the screenshots; diff shows what changed visually, not just textually.

## Review record — two companion comments (mandatory when reviewer subagents ran)

Separate from the 9-layer audit narrative: when independent reviewer subagents reviewed this PR's work (always true in `close-gate: pr-boundary` mode), the PR carries the **bidirectional review record** as two additional comments — (A) the reviewer's report **verbatim** (the writer must not condense or re-synthesize it; scope header with SHA range + method + "not reviewed" list; dispatch-prompt provenance folded) and (B) the **builder response** (per-finding Agree/Disagree + why, re-graded severity, what changed with SHA, what was deliberately not changed, closing Net judgment). Layer 6 keeps the disposition *summary*; the record carries the *reasoning* — the merger audits whether each review-fix was premised on a correct reading of the finding. Full spec, dispatch constraints, fix-routing rules, and coverage-window check in `references/review-record.md`.

## Draft-first workflow (write to the session scratchpad, then post)

**Write the PR body + comment as `.md` files in the session scratchpad (outside the repo) BEFORE invoking `gh pr create` / `gh pr comment`.** The scratchpad draft dies with the session — it is a sandbox for composing, not a durable artifact; the PR itself (body + comments, once posted) is the durable record. Screenshots are the one exception (see below): they are committed to the repo because they're a load-bearing asset embedded via raw URL, not a cache of the drafting process.

**PR-thread content passes the same hygiene gates as committed content — BEFORE the `gh` call.** Anything posted to a PR (body, comments, review records) is published, durable, and invisible to git-side gates (a pre-push hook cannot see a `gh api` call). If the project enforces a language policy (e.g. English-only durable artifacts) or a secrets/identifier leak gate on commits, run the same checks on every scratchpad draft file before posting it. The draft-first workflow exists precisely so there is a file to scan — a comment composed inline in the `gh` command has no gate at all.

```
<session scratchpad>/                              ← outside the repo; ephemeral, dies with the session
├── YYYY-MM-DD-phase-X.Y-pr-body.md
├── YYYY-MM-DD-phase-X.Y-pr-comment.md
├── YYYY-MM-DD-phase-X.Y-review-verbatim.md      ← review record comment A (see review-record.md)
├── YYYY-MM-DD-phase-X.Y-builder-response.md     ← review record comment B
└── YYYY-MM-DD-phase-X.Y-followup-decisions.md   ← if reviewer asks get answered post-open

docs/pr-drafts/screenshots/                         ← IN the repo, committed — the one retained exception
├── 01-list-page.png                                  (load-bearing asset embedded in live PR comments via
├── 02-detail-page.png                                 raw.githubusercontent.com, not a cache — never delete)
└── 03-error-state.png
```

Then:

```bash
gh pr create --title "..." --body-file <scratchpad>/YYYY-MM-DD-phase-X.Y-pr-body.md --label feature
gh pr comment <PR#> --body-file <scratchpad>/YYYY-MM-DD-phase-X.Y-pr-comment.md
```

Why scratchpad-first:

- **User can review the audit narrative BEFORE it goes public**. A scratchpad draft = sandbox.
- **Iteration is cheap**: `gh pr comment --edit-last --body-file <updated>` is one command vs re-typing in the web UI.
- **Cross-references work**: PR body can reference paths inside the same commit; comments embed screenshot URLs at the same SHA.

Why NOT commit the `.md` drafts (unlike the earlier `docs/pr-drafts/` convention): the PR itself — body + comments, once posted via `gh` — already is the durable, publicly-readable audit trail; a second, git-committed copy of the same prose was pure cache (the retention count-axis measurement that motivated retiring it found `docs/pr-drafts/` had grown to 143 files / 1.1 MB, invisible to every size-based retention check — see `references/retention.md` §"The count axis"). Screenshots don't have that problem: GitHub's raw-URL embed needs a real file at a real repo path, so `docs/pr-drafts/screenshots/` stays and is never cache.

## When to skip layers (and how to surface that)

The 9-layer structure has an escape valve: **legitimate-N/A skips** are explicit, not silent.

| Skip | When | How |
|---|---|---|
| Layer 1 demo | Pure refactor PR (no user-visible feature) | `## 🎬 Layer 1 — Demo (N/A — pure refactor, no user-visible change)` |
| Layer 2 negative path | No error paths (pure additive infra) | `## 🚨 Layer 2 — Demo (N/A — no new error surfaces)` |
| Layer 3 before/after | First-of-its-kind feature (nothing to compare) | `## 🔄 Layer 3 — Before / After (N/A — first feature of its kind)` |
| Layer 4 cost transparency | No paid-API calls | omit entirely OR write `(N/A — no paid-API surface)` |
| Layer 5 performance | No published gates | `(N/A — no go/no-go gates defined for this surface)` |
| Layer 6 findings | Genuinely no findings | `## 🐛 Layer 6 — Findings (none surfaced)` |
| Visual capture | No UI changes | omit screenshots dir + spec |

The N/A skip with a one-line reason is acceptable; deleting the heading is not. **Empty headings prove the layer was considered; missing headings prove it was forgotten.**

## Anti-patterns — STOP

- **Posting raw `bun test` / `pytest` output AS the PR comment with no narrative layers** → that's audit layer alone; useless for review. Add the 9 layers above it.
- **Layer 1 demo using mock fixtures instead of real runs** → defeats the purpose; the reviewer can't tell what would happen in prod. Run for real.
- **Skipping Layer 2 because "happy path works"** → negative paths are the most-skipped review surface, so deliberate negative-path demos earn the most leverage. Always include.
- **Cost transparency Layer 4 dropped on an LLM-using PR** → reviewer assumes free; cost surprises hit later. Show real spend.
- **Performance Layer 5 written from spec targets without measuring** → table of "target / target / target" is a copy-paste lie. Measure live.
- **Layer 8 reviewer asks as "please review the PR"** → useless. Be specific.
- **Visual capture using only `screenshot: 'only-on-failure'`** → no PR-comment screenshots when tests pass = no visual proof on a green PR. Use a dedicated spec.
- **Single screenshot, full-page or otherwise** → not enough breadth. 3-5 captures covering different UI states.
- **Inline `![](...)` raw URL pointing at the feature branch** → branch gets deleted on merge → image 404s for every future reviewer. Always anchor at the merge commit SHA or `main`. Branch-name URLs are time bombs.
- **Inline `![](raw.githubusercontent.com/...)` on a private repo** → silently 404s for every reviewer (raw URLs need auth tokens GitHub PR comments cannot pass). Use the link-to-blob form (clickable, opens GitHub file browser w/ PNG preview pane) OR web-UI drag-drop upload (only true-inline option, manual step, must be re-uploaded on every `--edit-last`).
- **PR body + comment typed directly into `gh pr create` / `gh pr comment` without a scratchpad draft** → user can't preview; iteration costly. Always draft to the session scratchpad first.
- **Editing the comment via web UI instead of `gh pr comment --edit-last --body-file <updated draft>`** → drift between the scratchpad draft and the live comment; review confusion. Edit the draft + re-post.
- **Reviewer ask answered in a follow-up comment that never actually posts** → audit narrative scattered — the durable copy is the POSTED PR comment, not the scratchpad draft. Write `<date>-phase-<X.Y>-followup-decisions.md` in the scratchpad, then `gh pr comment --body-file` it so the answer lands durably on the PR.

## Quick-reference (paste into chat when the gate is about to fire)

> "Ready to open the PR. Drafts staged in the session scratchpad:
> - `<date>-phase-<X.Y>-pr-body.md` (3-section + Use cases + file-by-file)
> - `<date>-phase-<X.Y>-pr-comment.md` (9 layers + folded raw evidence)
> - `docs/pr-drafts/screenshots/{01,02,03}-*.png` (Playwright dedicated spec, committed to the repo — the one retained exception)
>
> Once you approve I'll run `gh pr create --body-file ...` + `gh pr comment --body-file ...`. After post-open reviewer asks I'll write `<date>-phase-<X.Y>-followup-decisions.md` + `gh pr comment --body-file ...`. Once posted, the PR itself is the durable record — the scratchpad drafts die with the session."

## Cross-reference

- `references/ci-cd-gates.md` §"Posting test evidence" — the raw-evidence companion that goes in the folded `<details>` block at the bottom of every PR comment.
- `references/handoff-template.md` §"PR description appendix" — the 3-section PR body template; PR comment 9 layers extend the body's narrative without duplicating it.
- `references/findings-tier.md` — S1 / S2 / S3 tier definitions used in Layer 6.
- `references/close-gate.md` — produces the output pasted in Layer 7.
- `references/copilot-review-loop.md` — the per-finding inline-reply protocol that runs in parallel with this comment layer.
- `references/smoke-tracks.md` — Track A manual checklist that feeds Layer 1 + Layer 2 transcripts; Track B Playwright spec that feeds visual capture.
