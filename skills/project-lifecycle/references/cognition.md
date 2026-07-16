# Cognition — Intent Capture + Cold Intent-Log (Phase 1)

The **input side** of the project-cognition memory layer. Git captures *what* changed; the
iteration journal captures *what happened*. Neither reliably captures *why the human wanted
it that way* — the rationale, the rejected alternative, the quality bar someone stated out
loud and then the conversation moved on. This reference defines how that stated intent gets
captured, in what shape, and where it lands. Phase 2 (distill into a hot, queryable doc) is
out of scope here — this is capture + cold storage only.

## Purpose

Users state reasons constantly in the flow of a session — "let's do X because Y", "not Z,
that felt wrong last time", "good enough here means under 200ms" — and almost none of it
survives past the conversation that produced it. Code shows the *what*; commit messages and
the journal show the *what happened, when*; nothing durable shows the *why*, especially the
soft, evolving, not-yet-formal reasons that never rise to ADR weight. `cognition.md` is the
contract for capturing that stated intent cheaply, at the moment it's spoken, without turning
every request into a form to fill out.

## Intent schema

Canonical fields, 3 required + 2 optional:

| Field | Required | Type | Meaning |
|---|---|---|---|
| `intent` | **required** | string | What the user is trying to achieve, in their words or a tight paraphrase. |
| `subject` | **required** | string | What this intent is about — a component, decision, file, or concept. The join key for contradiction-at-capture (below). |
| `criterion` | **required** | string | What "good" looks like for this intent — the bar, the test, the acceptance condition. |
| `rejected` | optional | string | The alternative that was considered and turned down, if one was stated. |
| `supersedes` | optional | string (entry `id`) | Set when this entry additively replaces an earlier entry on the same `subject` (see Contradiction-at-capture). |

Two more fields carry defaults rather than being blank-optional:

| Field | Values | Default |
|---|---|---|
| `status` | `tentative` \| `firm` \| `superseded` | `tentative` |
| `salience` | integer `1`–`5` | `3` |

**Auto-metadata** — never asked of the user, always stamped by the capture mechanism:

- `ts` — capture timestamp
- `author` — who stated the intent
- `source` — `brainstorm` or `capture` (see Provenance)
- `verbatim_quote` — the exact sentence the intent was lifted from, for audit
- `id` — unique identifier for this entry, referenced by later `supersedes` fields

Example entry (see Cold intent-log below for the file it lives in):

```json
{"id":"c-2026-01-15-0001","ts":"2026-01-15T14:32:00-08:00","author":"user","source":"capture","intent":"keep thumbnail generation synchronous","subject":"image upload path","criterion":"thumbnails render inline on upload — moving them to a queue makes a failure invisible to the person who just uploaded","rejected":"a background worker with a retry queue","status":"firm","salience":4,"verbatim_quote":"if they cannot see it fail, they will assume it worked"}
```

## Cold intent-log

- **Format**: JSONL — one JSON object per line, no wrapping array, no trailing commas.
- **Path**: `docs/cognition-log.d/<YYYY-MM-DD>-<branch-slug>.jsonl` — one fragment per
  branch per day, the same per-branch fragment convention already used by the journal
  (`docs/journal.d/`), qa-log (`docs/qa-log.d/`), and changelog (`changelog.d/`) in
  `retention.md`. Conflict-free across concurrent branches/worktrees by construction —
  no two branches ever write the same fragment file.
- **Append-only, add-only**: entries are never edited or deleted in place. A change of mind
  is a *new* entry with `supersedes` pointing at the old entry's `id`; the old entry stays on
  disk untouched. This makes the log safe to `cat`, `grep`, and diff, and safe for multiple
  sessions to append to concurrently.
- **Lazy creation**: `docs/cognition-log.d/` and its fragments are created on first capture,
  same discipline as `docs/adr/` in `adr.md` — no empty scaffolding ahead of need.
- Downstream distillation (Phase 2: compiling fragments into a hot, queryable doc) follows
  the same drain shape as journal/qa-log fragments in `retention.md`, but is not specified
  here — this reference stops at capture + cold storage.

## When to capture (rationale signals)

Capture triggers on **rationale**, not on any statement. Listen for:

- **Causal / purposive** — *because, so that, to avoid, in order to*. ("Splitting this into
  two files because the reviewer agent chokes on 800+ line diffs.")
- **Contrastive** — *instead of, rather than, the problem with X is*. ("Using a fragment dir
  instead of one monolith — the monolith kept producing merge conflicts.")
- **Evaluative** — *better, cleaner, isn't good enough, feels wrong*. ("This error message
  isn't good enough — it needs to name the failing field.")
- **Keep/drop justification** — an explicit reason for retaining or removing something that
  isn't self-evident from the diff. ("Keeping the legacy adapter around — two client repos
  still import it directly.")

Any of these, stated about a `subject` with a `criterion` attached (explicit or one
elicitation question away), is a capture candidate.

## When NOT to capture (anti-signals)

- **Bare imperatives** with no stated why — *fix this, rename that, clean up the imports*.
  An instruction alone is not an intent; it's a task. Capturing it produces an entry with no
  `criterion` worth anything.
- **Status pings** — *any updates?, are we done?, how's it going*. Conversational, not
  decision-bearing.
- **Tooling chatter** — the "terse value judgment" class: *ugh, nice, lol, yeah that works*.
  Reaction, not rationale. If a terse judgment is followed by an unpacked reason, capture the
  reason, not the reaction.

Default is **don't capture**. The bar is a positive rationale signal, not merely "this was
said."

## Three-way line — ADR vs. capturable intent vs. noise

The same "someone explained why" moment can land in three different places. Use this line to
route it, cheapest test first:

| | Committed? | Architecturally significant? | Costly to reverse? | Destination |
|---|---|---|---|---|
| **ADR** | yes | yes | yes (quarter+ of work, breaking migration, customer-visible churn) | `adr.md` — all three hold, per its 3-criteria gate |
| **Capturable intent** | soft/evolving, not yet locked | no, or not clearly | no, or unknown | this log — a quality bar, a keep/drop call, a reason that might change |
| **Noise** | — | — | — | drop — no "why" was actually stated, just an instruction or a reaction |

If it clears the ADR gate, it goes to `adr.md`, not here — the cognition log is for
rationale that hasn't (yet, or ever) hardened into an architectural commitment. If it has a
`subject` and a `criterion` but isn't hard-to-reverse-and-surprising, it belongs here. If
there's no stated "why" at all, it's noise — drop it, don't force an entry.

## Elicitation (≤2 questions)

When a signal fires but `subject` or `criterion` is missing, ask — at most **two** questions,
and only when a signal already fired (never speculatively, never as a form on every request):

1. "What are you really trying to achieve?" — fills `intent` / `subject`.
2. "What would 'good' look like?" — fills `criterion`.

Ask only what's actually missing; a signal that already carries both fields gets captured
silently, no questions asked. This caps the tax at two questions precisely to avoid the
capture-bottleneck failure mode (Grudin — a mandatory rationale form kills the practice it's
meant to encourage; people stop stating reasons at all rather than fill out the form). The
elicitation questions are a light, occasional prompt, never a structured intake.

Primary trigger = the plc brainstorm-gate (see `references/intent-gate.md`); `/capture` is
the manual surface.

## Contradiction-at-capture (Phase 1)

When a new intent shares a `subject` with an existing entry, surface the prior entry before
writing the new one — "you previously said X about this; now you're saying Y — is this a
change of mind?" — and let the user confirm.

Phase 1 records **additively**: on confirmation, write a new entry with `supersedes` set to
the old entry's `id`; the old entry is left in place, untouched, `status` unchanged on disk
(a reader resolves "which entry is current" by following the `supersedes` chain forward).
**Full destructive supersede — rewriting or marking the old entry `superseded` in place — is
Phase 2.** Phase 1 never mutates a previously written line; append-only holds even across
contradictions.

## Provenance

`source` is one of two values, both **stated** (i.e., authoritative — the human said it,
directly or in direct response to elicitation):

- `brainstorm` — captured during a `superpowers:brainstorming` / brainstorm-research-protocol
  session.
- `capture` — captured ad hoc, mid-session, outside a formal brainstorm.

There is no `inferred` source in Phase 1. This reference does not specify a mechanism for
deriving intent the user never stated (e.g., pattern-mining commit history) — every entry
traces back to a `verbatim_quote` someone actually said. Inferred writes, if ever added,
are a distinct future phase with its own confidence/trust model, not a silent extension of
`capture`.

## Distill (regenerate)

Phase 2 turns the cold log into a small, always-loaded "hot" doc. Distill is a **regenerate**,
not an edit — every run reads `docs/cognition-log.d/*.jsonl` fresh and rewrites
`docs/cognition.md` wholesale. It never reads the prior hot doc as input.

**Regenerate-from-source is the load-bearing rule here.** Summarizing the previous summary
compounds drift — each pass smooths away a little more nuance until the doc confidently
states things the cold log no longer supports. Reading only the cold log, every time, means
the hot doc's worst failure mode is *incomplete*, never *confidently wrong*.

- **Trigger**: the `/cognition-distill` command, or the milestone-done distill-proposal step
  (`references/milestone-done.md`) offering to run it. Either way it is a deliberate,
  human-visible step — never a silent background rewrite.
- **Runs outside the jq gate.** The distill's LLM step is not part of `close-gate.sh`'s
  jq-only dependency envelope (that envelope stays python3-free
  and, by the same logic, LLM-free). **Distill failure never blocks close** — a broken or
  skipped distill leaves the gate unaffected; worst case the hot doc goes stale, which the
  confidence surface below will say out loud.
- **Procedure**: load non-`superseded` entries from the cold log (Phase 1's `status` field —
  `superseded` entries are excluded outright, never rendered, never counted), group them into
  the four hot-doc sections (Why/intent, Invariants/what-good, Active focus, Open questions),
  and render each surviving entry as one bulleted fact carrying its `[<id>]` source pointer
  and a `[stated]` tag. **No free causal prose** — the only causal language permitted is
  `because → [source]`, and only when a source pointer backs it; the distill step does not
  get to editorialize or infer connections the cold log doesn't state.
- **After rendering**, the distill step invokes `scripts/cognition_render.py guards` — the
  deterministic pass (staleness marking, cap enforcement, dead-path lint, coverage report,
  snapshot write) described in Hot cognition doc format and Confidence surface below. Guards
  run in Python, zero LLM calls, so the numbers and markers in the confidence surface are
  never model-generated.

## Hot cognition doc format

- **Path**: `docs/cognition.md` — sibling to the cold log dir. Whether `docs/` is tracked
  or ignored is the project's own choice; follow whatever the project already does.
- **Hard cap**: **120.** `enforce_cap` in `cognition_render.py` enforces this as a maximum
  **entry count** (120 rendered facts); the "~120-line" file size is an approximate target,
  not the arithmetic — the header, section titles, and the confidence-surface footer are not
  counted against the 120. This is deliberately small — the hot doc is the thin,
  always-loaded core; depth lives in the cold log, one `[<id>]` retrieval away. When
  surviving entries would exceed the cap, `enforce_cap` keeps the best-ranked subset (highest
  `salience`, ties broken by newest `ts`) and evicts the rest.
  Eviction is **visible**, not silent — evicted count surfaces in the confidence surface
  footer — and evicted content is never lost: it stays in the cold log, unaffected by the
  hot-doc rewrite.
- **Four sections**, fixed order:
  1. **Why / intent** — the effortless-onboarding, first-principles reasons a thing exists.
  2. **Invariants / what-good** — stated quality bars and things that must not regress.
  3. **Active focus** — what's currently being worked, and why that and not something else.
  4. **Open questions** — decisions not yet made, flagged so an agent doesn't silently
     assume an answer.
- **Header disclaimer**: every regenerated doc opens with a one-line notice — *auto-regenerated,
  don't hand-edit, retrieve the cold log for depth* — so a human or agent who opens the file
  mid-session doesn't mistake it for something safe to patch by hand.
- **Gated loading**: the hot doc is not loaded on every turn. It's pulled in for complex or
  multi-session work — the same gating discipline as other hot docs under `retention.md`
  (RESUME.md, status) — not blindly prepended to every prompt regardless of task size.

Canonical shape:

```markdown
# Project Cognition  (auto-regenerated from docs/cognition-log.d — do not hand-edit; 120-line cap)
> Thin always-loaded core. Full intent + history in the cold log; retrieve for depth.

## Why / intent
- effortless onboarding — first success without docs `[a1b2c3d4]` [stated] (fresh, 2d)

## Invariants / what-good
- never blame the user in error copy `[e5f6a7b8]` [stated] (firm, 14d)

## Active focus
- cache layer rework `[c3d4e5f6]` [stated] (⚠ stale? 96d unconfirmed)

## Open questions
- keep dry-run flag? `[b2c3d4e5]` [stated]

---
<!-- confidence-surface (auto) -->
coverage: 4 subjects, 8 intents · gaps: none
evicted this run: 0 · dead-path flags: 0 · stale (>90d): 1
snapshot: docs/.cognition-audit/2026-07-09T14-32-00.json
```

## Confidence surface

Every hot-doc line and the doc as a whole carry legible signal about how much to trust them —
readable by a human skimming the file and actionable by an agent deciding whether to trust a
fact or go retrieve/verify it first.

**Per-line freshness marker** — appended after the `[stated]` tag on a load-bearing fact line,
one of three forms. The marker has two parts with two different provenances, and the split
matters:

- **The deterministic part — age + staleness — is code-computed** by `age_and_staleness(ts,
  now, stale_days=90)` in `cognition_render.py`, which sees only the entry's `ts` and the
  current time. It returns the human age (`Nd`) and a boolean staleness flag; that is *all*
  it computes. Once `ts` is past the 90-day threshold, this is what renders `⚠ stale? Nd
  unconfirmed`. Never LLM-judged, never hand-set.
- **The qualitative word — `fresh` / `firm` — is data-driven, not computed by the guard**, and
  must not be attributed to `age_and_staleness` (it structurally cannot see `status`; the
  guards report exposes only a flat `stale_ids`, with no fresh/firm split). The word reflects
  the entry's own `status` field, surfaced by the distill step at render time: `firm` when
  `status == "firm"`, `fresh` for a recent `tentative` entry. It is a **data tag**, the same
  authoritative-because-stated class as `[stated]` — not free causal prose the distill step
  invents.

The three rendered forms:

- `fresh, Nd` — a `tentative` entry, `N` days old, inside the staleness window.
- `firm, Nd` — a `firm` entry, `N` days old, inside the staleness window.
- `⚠ stale? Nd unconfirmed` — `ts` past the 90-day threshold with no newer entry on the same
  subject reconfirming it; the `age_and_staleness` staleness flag drives this and it replaces
  the `fresh`/`firm` word once the window is crossed, for either status.

**Not every hot-doc line carries a freshness marker.** Load-bearing **fact** lines — Why /
intent, Invariants / what-good, Active focus — carry `[stated]` *and* the freshness marker,
because they assert something that can go stale. An **Open questions** entry is an unsettled
question, not a fact — there is nothing to age — so it may carry just `[stated]` and no
freshness marker (as the `- keep dry-run flag? \`[b2c3d4e5]\` [stated]` line in the canonical
shape above shows). The distill render step should mark the three fact sections and leave Open
questions marker-free.

**Staleness threshold: 90 days.** An entry crosses from fresh/firm into `⚠ stale?` once its
`ts` is more than 90 days old with no superseding or reaffirming entry since. The `⚠ stale?`
marker is a deliberate trust downgrade, not decoration — it tells the reading agent "this
fact hasn't been re-said in three months; retrieve the cold log and confirm before relying on
it," the same way a missing source pointer tells the agent not to treat a line as
authoritative on its own.

**Auto footer** — appended below the four sections on every regenerate, entirely
code-computed from the guard functions in `cognition_render.py`, never authored by the
distill LLM step:

- `coverage: <subjects> subjects, <intents> intents · gaps: <list or "none">` —
  `coverage_report`'s subject/intent counts and any subjects whose entries are all missing a
  `criterion` (a stated intent with no bar for "good," worth flagging as a capture gap).
- `evicted this run: <n>` — how many surviving entries `enforce_cap` cut to hold the 120-line
  cap; the evicted entries themselves remain retrievable from the cold log.
- `dead-path flags: <n>` — count from `dead_path_scan`: path-like tokens the hot doc
  references that no longer exist on disk, a lint against citing rot.
- `stale (>90d): <n>` — count of entries currently carrying the `⚠ stale?` marker.
- `snapshot: <path>` — where `write_snapshot` wrote this run's audit copy under
  `docs/.cognition-audit/`, a point-in-time record of the hot doc at this regen. Phase 1
  writes the snapshot only; it does not itself emit a diff against the prior run.
  `diff_snapshot` in `cognition_render.py` can compute that diff when invoked, but it is
  not wired into the guards CLI's automatic output yet — treat it as a manual/future
  capability, not a per-regen diff you'll see printed.
- `unknown_ids: <list>` — from `unknown_cited_ids`: hot-doc `[<id>]` source pointers
  (exactly 8 lowercase hex chars, so provenance tags like `[stated]`/`[firm]`/`[fresh]`
  never match) that don't resolve to any entry in the cold log. Deterministic,
  non-blocking — a dangling or typo'd citation, surfaced as a warn signal the same way
  `dead_paths` surfaces a rotted file reference.

The footer and the per-line markers exist for the same reason: a hot doc that states things
confidently but wrongly is worse than no hot doc at all. Marking freshness and surfacing
gaps/evictions/dead-paths in the open lets both the human and the agent calibrate trust per
line instead of taking the whole file on faith.

## Measurement (Phase-1 close / Phase-2 gate)

**Why it exists.** Phase 2 — destructive supersede, full contradiction resolution, the
heavier arbitration machinery hinted at throughout this reference — is not something to build
on faith. It's gated on proof the cognition layer actually earns its keep. The measurement
instrument is how that proof accumulates: a small, deterministic log of whether loading
cognition context correlates with fewer re-explanations over successive milestones. If the
numbers show no benefit, the honest conclusion is that Phase 1 stands alone and Phase 2 is
correctly never built — that's not a failure of the instrument, it's the instrument doing its
job.

**Primary metric — re-explanation events.** A re-explanation is the moment a user has to
re-state something the cognition layer should already have held — the clearest signal the
hot doc failed at its one job. These are captured the same way any intent is: `/capture
--source reexplain` tags the entry at the moment it happens (see `commands/capture.md`).
`cognition_measure.py` derives `reexplain_count` from these tagged entries deterministically
— counted by the script, never hand-entered — over the window since the last recorded
measurement row.

**Secondary — turns / tokens_est.** Honest, self-reported estimates of how much conversation
a milestone took, supplied by whoever runs the record step. These may be `null` when no
honest estimate is available — never fabricated to look precise. They exist to catch the
failure mode where re-explanations go down but the cost of getting there goes up (verbose
cognition doc, more retrieval round-trips) — a wash dressed up as a win.

**Row + fragment.** Each milestone close appends one row to
`docs/cognition-measure.d/<date>-<branch>.jsonl` — the same per-branch fragment convention as
the cold intent-log, journal, and qa-log. Eight fields per row: `milestone`, `ts`, `turns`,
`tokens_est`, `cognition_loaded`, `cognition_intents`, `reexplain_count`, `note`.

**The decision gate.** After roughly 5–8 milestones closed with cognition loaded, look at the
trend: if `reexplain_count` is trending down *and* `turns`/`tokens_est` are not inflating to
buy that improvement, Phase 2 is justified by data. If the trend is flat or worse, the answer
is to stop — per Markus Sandelin's ["The First Controlled Benchmark of AI Memory in Coding Agents"](https://medium.com/@mrsandelin/the-first-controlled-benchmark-of-ai-memory-in-coding-agents-8e0bb776d39e), memory is overhead when it doesn't pay for itself, and continuing
to build on an unproven layer is the mistake, not a discipline gap. `cognition_measure.py
report` prints which side of the line the accumulated data falls on; a human reads the report
and makes the call — the script hints, it does not decide.

**Honesty rule.** The report opens with a limits banner — observational, not a controlled
experiment; small N; `turns`/`tokens_est` are self-reported estimates; `cognition_loaded` is
self-reported too — the same confidence-surface discipline applied elsewhere in this
reference, now applied to the instrument measuring the reference's own value.

**Runs outside the jq gate**, at milestone close, alongside distill. Failure here never
blocks close — the same non-blocking posture as distill above, for the same reason: a
measurement instrument that could stall shipping would itself be a cost the layer imposes,
undermining the very thing it's trying to prove.
