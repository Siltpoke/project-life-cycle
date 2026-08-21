# Builder Profile — Mechanism

Reference for `/builder-profile` (`commands/builder-profile.md`). Holds the four-gate prompt, the JSONL parser schema, the framing-safety rules, and the report shape + location.

---

## What this is for

A **point-in-time snapshot of how the user actually uses an AI coding agent.** One markdown report (`~/.claude/builder-profile.md`), readable by the user (self-understanding → use it better) and by any agent on demand (richer context about who they work with). Usage drifts, so every run is a fresh snapshot. The report **is** the product — there is no separate machine artifact, and v1 does not wire any skill step to consume it. The five behavioral dimensions are signals read from the transcripts; the report describes patterns, it does not grade.

Two independent risks, two independent mitigations:

- **Verdict-spiral risk** (a score card triggers self-criticism) → handled by **framing**: descriptive default, operating-modes-not-archetype, co-discovery-questions-not-growth-edge, no cumulative scoreboard.
- **Flattery risk** (the profiler just served this user → primed to flatter) → handled by **self-blinding + adversarial verify**: cold-read the logs as a stranger's, then try to refute each claim.

Both are required. Neither covers the other.

---

## The pipeline prompt (run verbatim)

One local run, multiple passes, no network.

```
Read this machine's local AI-coding transcripts and produce a builder profile.
Everything runs locally — no network call, no upload. State this at the top of
the report.

You are NOT profiling "your user." Treat these transcripts as a stranger's logs
and cold-read them. Do not pre-load what a "good" builder looks like. A
dimension with too little evidence is marked `insufficient signal`, never guessed.

Data source:
- Claude Code: ~/.claude/projects/**/*.jsonl  (one JSON event per line)
- (Claude Code only. Codex / Cursor not read.)

═══ PASS 1 — deterministic ═══
Run `python3 scripts/builder_profile_stats.py --days 90 --out <tmp>/stats.json`
— pure stdlib, local, emits stats.json. All later qualitative work cites its
fields; do not re-eyeball the numbers. Window: last 90 days. stats.json holds
(every number re-computable from the jsonl):
1. total sessions + actual time range
2. model share (assistant `message.model`; assistant turns only)
3. hour-of-day distribution (local tz) → night-owl / 9-5 verdict + basis
4. user-prompt length distribution (median / p80, chars + words)
5. plan-mode ratio: share of sessions containing a `type=="permission-mode"`
   event with `permissionMode=="plan"`. (Verified: plan lives in the
   permission-mode event's `permissionMode` field, which has no timestamp;
   `ExitPlanMode` tool_use is never observed — do not use it.)
   **Read `plan_mode.signal` before citing the ratio.** This metric rides on a
   vendor field that can be renamed or removed, and a detector matching nothing
   would otherwise report a confident `0.0` — indistinguishable from a real "the user
   never plans". So the parser asserts the *channel* alongside the value:
   - `present` — permission-mode events carrying a known mode key were found;
     `ratio` is a real number and a `0.0` is a genuine zero.
   - `absent` — no permission-mode event of any mode in the window; "never used"
     and "event type renamed" cannot be told apart → `ratio` is `null`.
   - `schema-drift` — permission-mode events exist but none carries a known key
     (`permissionMode` / `mode`) → the field moved; `ratio` is `null`.
   `absent` / `schema-drift` are **parser alarms, not findings**: fix the
   detector (`PERMISSION_MODE_KEYS` in `scripts/builder_profile_stats.py`)
   against a raw transcript before the profile says anything about plan mode.
   The same rule applies to `trajectory.*.plan_ratio`, which is `null` too
   whenever the signal is not `present`.
6. tool_use frequency ranking (top + diversity count)
7. longest single session (by timestamp)
8. top 2–4-gram phrases in user prompts
9. trajectory: split the window into first third vs last third, compare
   plan-ratio / prompt length (reported only with ≥3 sessions, else
   status=insufficient; `plan_ratio` is `null` unless `plan_mode.signal ==
   "present"` — never narrate a null as "stopped planning")

Data hygiene (the parser already does this): skip `isSidechain==true` events
(sub-agent turns, not the user driving directly); a session = a file with ≥1
real (non-sidechain) user text prompt — sub-agent-only files are not counted as
sessions. Dropped files/lines are logged in stats.json's `sampling` field — no
silent truncation.

Note: steering is NOT computed in PASS 1. A `tool_result` always sits between an
assistant `tool_use` and the next user prompt, so there is no reliable
deterministic "interrupt" signal — steering is judged from samples in PASS 2
(`stats.json.steering.status == "deferred-to-pass-2"`).

═══ PASS 1.5 — evidence gate ═══
For each dimension, count evidence instances first (from stats.json + sampled
excerpts). < 3 instances → mark the dimension `insufficient signal`; PASS 2 may
not narrate it.

`insufficient signal` is not the same verdict as a broken detector, and the gate
must not merge them: if a dimension is empty because its **signal channel** is
missing (`plan_mode.signal != "present"`), report it as `detector unverified` and
say which field to re-check. "No evidence" invites "so the user doesn't do this";
"detector unverified" correctly says nothing was measured at all.

═══ PASS 2 — qualitative / cold read (read stats.json + a stratified raw sample) ═══
Sampling (no cherry-picking): stratified — the longest N sessions + plan-mode
sessions + error-recovery excerpts + a handful of evenly-spread sessions.

0. SPINE before everything (this step produces the result; the rest only
   expand it): first find whether a single disposition runs through all the
   evidence. If one does, it leads, and the modes / dimensions / signature
   moves below are all organized as projections of it — not parallel,
   independent findings. Enumeration comes after synthesis, never instead. After
   each dimension converges to the spine, run the over-fit reverse-check: does
   it have any non-spine component? 100%-spine + thin evidence → downgrade or
   merge, don't pad the list.
1. modes: fewest orthogonal count. If two descriptions are the same disposition
   at different latency/intensity → merge them. Before splitting, ask: two
   different axes, or one axis at two speeds? Each mode cites a real session.
2. five dimensions, descriptive observation + evidence: steering / execution /
   engineering / product instinct / planning. [Descriptive by default; 1-10
   only with --scores.] Confidence is two things: label the INTERPRETATION's
   confidence, not the underlying number's. Exact numbers ≠ trustworthy story;
   two equally-fitting readings → mark `contested`, don't pick the flattering
   one. Any tool-count / delegation claim must state in-sentence which layer it
   measured (stats tool/prompt counts = main-thread; sidechain + excluded
   sub-agent files are NOT counted), and no narrative may contradict its own
   magnitude (15:1 is not "orchestration").
3. signature moves: recurring moves, each with a real session_id:line —
   organized as the spine's tactical surface, not scattered points.
4. trajectory: how patterns shift over time — describe the trend only, no
   prescription.
5. co-discovery questions: 3 curiosity-framed ("huh, you assumed X but it was
   Y") — never a deficit list or a score.
6. level/band (restrained): band only metrics whose prior has shape (session
   volume, model-tier), as an inline gloss hung off the raw number, flagged as a
   stale + tail-biased prior. Do NOT band quiet metrics whose prior ≈ 0
   (plan-ratio, tool-counts/session). Add one line stating: precise rating /
   ranking needs an external population this tool deliberately does not do. A
   band never enters the deterministic table and never gets its own section.

═══ PASS 3 — adversarial verify (local, same run) ═══
Re-read each PASS-2 conclusion against the grain: could this sample support the
opposite reading? Magnitude check: is the narrative consistent with the
magnitude of the numbers it cites (15:1 is not "orchestration")? Refutable /
propped by a single excerpt / contradicting its own numbers → downgrade or cut.
Keep only what survives.

═══ OUTPUT ═══
One markdown report, written to ~/.claude/builder-profile.md (overwrite; the
user keeps an old copy if they want history).
- Header: snapshot date + window ("snapshot as of YYYY-MM-DD, last 90 days") +
  the local-only statement.
- Structure is spine-first: lead with the through-line disposition; modes /
  dimensions / signature moves / trajectory / co-discovery are all laid out as
  its projections, not as a parallel list.
- Every conclusion traces to a stats.json field or a session_id:line
  (quantitative → cite the field, qualitative → cite the line). Fabrication =
  failure. No raw excerpts embedded — conclusions only.
This one file is the whole product — the user reads it to understand themselves;
any agent reads it on demand for context. No separate memory seed, no skill step
wired to consume it.

═══ PASS 4 — independent verification (do not trust the generator's self-report; gates delivery) ═══
After the draft is written, before it counts as delivered, run two independent
checks. Any fail → back to PASS-2/3 to rework and rewrite; not delivered:
4a. Automated assertions: run `python3 scripts/builder_profile_verify.py <report>`.
    Hard checks (script, exit 1 on failure): no Level section; a band only on a
    volume/model-tier line and carrying a provenance token; every dimension has
    a confidence label; any dimension citing a tool-count carries a scope token
    in the same paragraph.
4b. Cold critic: spawn a fresh-context critic instance (Agent) and feed it only
    two things — this reference's full rules + the finished report. Do NOT give
    it the generation trace or the generator's self-defense (that would pollute
    the judgment). Have it emit pass/fail + one evidence line per rule, watching
    the four known failure points: (1) did the spine actually converge or
    just get a heading; (2) did any dimension use a measured surface to smuggle
    a conclusion about scope-excluded data (the engineering trap); (3) was
    measurement-confidence laundered into interpretation-confidence; (4) is a
    band disguised as a verdict. Any fail → rework, not delivered.

═══ DELIVERY — explain it in plain language in the conversation, not just a path ═══
Once PASS 4 passes, give the user a plain-language walkthrough in the
conversation (not the raw markdown pasted back):
- Lead with the spine: say the one disposition in plain words and how it runs
  through everything else.
- Walk through the 1-2 modes and the key dimensions — especially the honest
  ones: any dimension that could not be measured, any reading marked
  `contested`. Say in plain words what is real signal vs caveat (polluted prompt
  counts, unmeasured delegation).
- Ask the three co-discovery questions as real questions (curiosity, not a
  deficit checklist).
- Hold the framing: descriptive not evaluative, no scores, no cumulative
  scoreboard, you-vs-you.
- Close: the report lives at ~/.claude/builder-profile.md (a snapshot, refreshed
  on re-run); any agent reads it there on demand.
The goal is that the user actually gets themselves and re-engages — not that a
task got closed.
```

---

## JSONL parser schema

Get these field names right or PASS 1 is fiction.

All rows verified against a real `~/.claude/projects` corpus, not assumed.

| Thing | Location | Note |
|---|---|---|
| turn type | top-level `type` | `user` / `assistant` / `system` / `summary` / `file-history-snapshot` / `permission-mode` / `attachment` / `last-prompt` |
| model | `message.model` | **assistant turns only** (e.g. `claude-opus-4-7`); `<synthetic>` appears for synthetic msgs |
| timestamp | top-level `timestamp` | ISO-8601; **absent on some event types** (e.g. `permission-mode`) — guard for None |
| tool call | `message.content[]` → `{type:"tool_use", name, id, input}` | `name` is the tool (Read/Edit/Bash/Task/…) |
| user prompt vs tool echo | `type=="user"` + content **has a `text` block** → real prompt; content with only a `tool_result` block → tool echo, not the human | distinguishing these is load-bearing for prompt/hour/ngram counts |
| thinking | `message.content[]` → `{type:"thinking", thinking:"…"}` | key is **`thinking`**, not `content` |
| **plan mode** | `type=="permission-mode"` event, **`permissionMode == "plan"`** | verified: field is `permissionMode`; `ExitPlanMode` tool_use **never observed** in any transcript examined. No timestamp on these events. **This row is the one metric whose signal can vanish without any error**, so the parser also asserts the channel is alive — see `plan_mode.signal` in step 5. |
| **sub-agent turns** | per-event **`isSidechain == true`** | interleaved in the file; **exclude** from all counts (sub-agent ≠ user driving). A file with no real non-sidechain prompt is not a session. |
| token usage | `message.usage.{input_tokens, output_tokens, cache_read_input_tokens}` | optional; not used in v1 |

Steering has **no** deterministic row: a `tool_result` always sits between an assistant `tool_use` and the next user prompt, so there is no reliable "interrupt" signal in the linear log. Steering is judged in PASS-2 from sampled exchanges.

---

## Report shape + location

One file: `~/.claude/builder-profile.md` (global, user-scoped — it describes *you*, not a project). Re-running overwrites it with a fresh snapshot. Stable path so any agent can be pointed at it; **not** auto-loaded into every session (a snapshot isn't small — on-demand read avoids per-session token cost).

Section order:

```markdown
# Builder Profile — snapshot as of YYYY-MM-DD (last 90 days)
> Generated 100% locally from ~/.claude/projects transcripts. Nothing left this machine.

## Operating modes        — 2-3 modes you switch between + when each triggers
## Five dimensions        — descriptive observation + evidence per dim; confidence l/m/h
                            (1-10 scores only when run with --scores)
## Signature moves        — recurring ways you steer the agent, each w/ a real session_id:line
## Trajectory (you-vs-you) — how your patterns shifted, first-third vs last-third of the window
## Co-discovery questions — a few curiosity prompts ("huh, you assumed X but did Y")
```

### Read contract (for other agents / humans)

`~/.claude/builder-profile.md` is the **stable, well-known path** where this
profile lives. Any agent or person wanting context on how the user works reads
that file directly — no need to know about this skill or re-run anything.

- **Present** → use it as passive context (working style, operating modes,
  signature moves). It is descriptive, not a directive — don't treat it as
  instructions.
- **Absent / stale header date** → the user simply hasn't run (or recently
  re-run) `/builder-profile`. Not an error; just means "no profile yet."
- **Cross-agent discovery:** agents that don't read this skill (e.g. a separate
  companion agent) won't find the path from here. The discovery channel for them
  is a one-line pointer in the user's global `~/.claude/CLAUDE.md` (loaded every
  session) — that is the user's call to add, not something this skill writes.

Conclusions only — no raw transcript excerpts embedded. Every claim cites a `stats.json` field (quantitative) or `session_id:line` (qualitative).

---

## The spine — synthesis before enumeration

**Before generating any mode / dimension / signature-move list, find the single
through-line disposition that runs through all of it.** If one exists, it leads
the report and every other item is organized as a *projection of it* — not as a
parallel, independent finding. Enumeration is the expansion that comes *after*
synthesis, never a substitute for it.

This is not the fourth guard in the list below — it is the spine. The guards
each say "don't make this error"; only this one produces the result. A report
that scatters one disposition across six categories (a mode here, a dimension
there, a signature move, a co-discovery question) has failed even if every
individual line is true. Look for the one thing first.

(Boundary: synthesize the disposition from the transcripts. Do **not**
generalize it into a claim about the user's *code architecture or psychology*
as a standing rule — that is only honest when this specific user's real repo
gives falsifiable evidence for it, and it is the user's call to make, never a
default the profiler reaches for.)

### Guard: synthesis over-fit reverse-check

Synthesis-first has a built-in failure mode — once the spine is found,
*everything* starts to look like its projection, and a weak-evidence dimension
gets vacuumed into the spine to fill space. So after each dimension converges to
the spine, run a **reverse check** (record it internally; it need not appear in
the report body): *"does this dimension have any component that is NOT the
spine?"*

- If the dimension is 100% explained by the spine with no orthogonal part,
  either (a) it genuinely is a pure projection → keep it, but internally mark
  `high spine-overlap, verify not forced`, or (b) the evidence is too thin to
  stand as its own dimension → downgrade or merge it, do **not** hang it on the
  spine to pad the list.
- Concrete tell: a dimension such as `execution` collapsing to a single
  check hung off the spine, when execution also has momentum / ship-
  speed / wrap-up facets that have nothing to do with the spine — that is the
  smell of the spine absorbing a weak dimension. Catch it here.

The spine is right; this guard is its counterweight so synthesis doesn't
normalize non-spine material into the spine.

## Honesty / provenance rules (non-negotiable)

- **Confidence is two separate things.** `measurement-confidence` ≠
  `interpretation-confidence`. A dimension labels the confidence of the
  *interpretation*, not the underlying number. "The hard number is exact"
  (high) does **not** transfer to "the story I read off it is trustworthy."
  When two interpretations fit the same number equally, say `contested` and
  don't pick the flattering one.
- **Every inference sanity-checks its own magnitude + states scope.** No
  narrative that contradicts the magnitude of its own metric (a 15:1 ratio is
  not "orchestration"). Any tool-count claim must say *in the sentence* which
  layer it measured and which it did not. **Tool/prompt counts in `stats.json`
  are main-thread only** — sidechain events and the excluded sub-agent
  transcript files are *not* in the totals, so a delegation/engineering claim
  must name that the delegated work is unmeasured rather than imply the
  measured surface is the whole picture.
- **Level claims carry provenance; only band a metric whose prior has shape.**
  Any level/comparison claim labels its source *in-claim*: `measured population`
  vs `model prior`. Only attach a band to metrics where the prior carries a
  rough distribution (session volume, model-tier), and note that prior is stale
  + tail-biased (people who publicly write up their workflow skew overwhelmingly
  power-user). For quiet metrics where the prior ≈ 0 (plan-ratio,
  tool-counts-per-session) give **no band** — banding them fabricates precision.
- **Band is an inline gloss, never a section; ranking is out-of-scope.** A band
  is a third provenance (external prior) and the only claim in the whole report
  that local logs cannot falsify, so: keep it out of the deterministic table,
  don't dress it as a number, and never give it its own "Level" section (a
  section reads as a verdict). It hangs as a clause off the raw number it can
  honestly touch. Add one explicit line: precise rating / ranking needs an
  external population and this tool deliberately does not do it.

## Framing-safety rules (non-negotiable)

1. **Descriptive default.** Scores only behind `--scores`. The default output is a mirror, not a grade.
2. **Fewest orthogonal modes.** Merge two descriptions that are the same disposition at different latency / intensity into one. Before splitting, ask: two different axes, or one axis at two speeds? Never reduce the user to a single box either.
3. **Co-discovery, not growth edge.** Gaps are curiosity questions ("huh, you assumed X but did Y"), surfaced during work. Never a deficit count, never a cumulative scoreboard.
4. **You-vs-you only.** No ranking, no external baseline, no comparison to other people.
5. **Self-blinded.** Cold-read as a stranger's logs. Do not pre-load what a "good" builder looks like.
6. **Evidence floor.** `< 3` instances → `insufficient signal`. No manufactured narrative.
7. **Local-only.** No network call. The report states this at the top.

---

## PASS 4 — independent verification (the generator does not grade itself)

Every rule above is self-assessed by the same agent that wrote the report — and
judging whether the spine converged or the scope was black-boxed needs exactly
the synthesis judgment the generator is least able to apply to its own output. Judge and contestant
are the same. So a **separate verification pass gates delivery**, and it does not
trust the generator's self-report. Two parts:

**4a — automated assertions** (`scripts/builder_profile_verify.py <report>`, pure
stdlib, exit 1 blocks delivery). Hard checks a script can prove without judgment:
no `Level` section heading; a band (`≈ <tier>`) only on a volume / model-tier
line and never on a prior≈0 metric; every band carries a provenance token; every
dimension bullet carries a `confidence` label; any dimension citing a tool-count
also carries a scope token (`main-thread` / `excluded` / …). Tested in
`scripts/test_builder_profile_verify.py`.

**4b — cold critic** (LLM, for framing failures assertions can't catch). Spawn a
**fresh-context** critic agent fed only two things: this reference's rules + the
finished report — **not** the generation trace, **not** the generator's
self-defense (that defense is exactly what would pollute the judgment). It
returns pass/fail + one evidence line per rule, watching the four known
failure points: (1) did the spine actually converge or just get a heading;
(2) did any dimension use a measured surface to smuggle a conclusion about
scope-excluded data (the `engineering` trap); (3) was measurement-confidence
laundered onto interpretation; (4) is a band disguised as a verdict. Any fail →
back to PASS-2/3, not delivered.

**Why this is in the spine, not bolted on.** The profile's whole method is
evidence before conclusion. A generator that demands that of every claim
and then trusts its own output is violating the very discipline it is
applying. PASS 4 makes the builder-profile generator obey its own rules:
the system that says "verify before trusting" must verify *itself* before
delivering.
