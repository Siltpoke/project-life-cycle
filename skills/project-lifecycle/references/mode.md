# `mode: fast | detailed` — one dial the user turns, and the keys it expands into

> **The one key a user sets.** Everything below it has its own name and can be turned on its own.
> That is not a nicety — it is the property that keeps an ablation experiment possible, and it is
> the reason `mode` is a **preset**, never a mechanism.

## Why this key exists

The problem it answers: the process grows too elaborate — work
that used to take minutes picks up more and more steps in the middle. The weight is not in
the prose — a measurement of this skill's always-loaded text (`references/progressive-disclosure.md`) found ~1.2% of it redundant, so
trimming words was the wrong lever. The weight is in **how many times a human is stopped** and
**how many agents each task dispatches**.

`mode` moves those two numbers. It changes **how heavily each step runs**, never **which files come
out** — both modes produce the same artifacts (see §"Artifact shape").

**The axis is the stakes, not the size and not the user's skill.** Something built for fun, and
something built to take money, deserve different amounts of care from the same person on the same
day. `archetype` answers *what shape is this work*; `mode` answers *does it matter if this is
wrong*.

## The key

```yaml
# CLAUDE.md
mode: fast          # fast | detailed
```

**Default: unset.** An unset `mode` is byte-identical to a project that never heard of this key —
every low-level key keeps its own default, which is today's behaviour and is what `detailed` names.

**It is a hat the work wears, not an identity the repo holds.** One sentence overrides it for a
single run — *"do this one carefully"* — and the next phase goes back to the project default. The
record says which of the two it was every time (§"Provenance").

**`mode` may be set by the user or by the assistant.** On first contact the assistant presets one
and *says so* on the start-of-work screen (`kickoff-confirmation.md`) rather than asking a question
the user cannot yet answer.

## The expansion map

This block is **the** map. It is data, it is read by `hooks/mode-expand.sh`, and it is the only
place any of this is written down.

**Adding a key here is the whole edit *for the resolver*** — `mode-expand.sh` names no key at all,
not in code and not in a comment, and a test greps it for every declared name and requires zero
hits. **The claim stops there.**
A key's *consumers* may still need work: `hooks/plc-kickoff-check.sh` and two
invariants branch on `mode` being `fast`, so a new key that some step must react to needs that step
taught about it. What the map buys is that **resolution** never becomes a second place to edit —
which is what keeps a per-key ablation possible.

<!-- plc-mode-map:begin -->
```json
{
  "version": 1,
  "modes": ["fast", "detailed"],
  "keys": [
    "intent-gate",
    "brainstorm",
    "cadence",
    "autonomy",
    "close-gate",
    "smoke-mode",
    "archetype",
    "second-agent-family"
  ],
  "never_set_by_mode": ["intent-gate", "second-agent-family"],
  "presets": {
    "fast": {
      "brainstorm": "quick",
      "cadence": "compressed",
      "autonomy": "ship-shape",
      "close-gate": "pr-boundary",
      "smoke-mode": "self",
      "archetype": "silent"
    },
    "detailed": {
      "brainstorm": "full",
      "cadence": "full",
      "autonomy": "full",
      "close-gate": "per-task",
      "archetype": "auto"
    }
  }
}
```
<!-- plc-mode-map:end -->

**Three shapes in that block are load-bearing and easy to misread:**

1. **`never_set_by_mode` is data, not a promise in prose.** `intent-gate` is on that list because
   the gate is cheap (it lays out assumptions for one tap; it does not interrogate) and turning it
   down is how a fast run starts from a misunderstanding. `second-agent-family` is on it because
   that key names a *lineage*, which is a project setting; `mode` picks the blind review's
   *frequency*, and the two are orthogonal. The resolver drops these keys even if a preset were
   edited to set one, so the guarantee does not depend on the preset staying quiet.

2. **`detailed` does not set `smoke-mode`.** That is an absence, not a value: `detailed` asks the
   smoke interaction question once per phase, which is what an unset key already does.

3. **`archetype: silent` means *infer and apply, do not ask*.** It does **not** mean *do not
   classify*. Two zero-interruption protections ride on the archetype still being decided and still
   being written into the `Archetype:` trailer — Sweeper's net-negative-LOC check and Maintainer's
   mandatory security review. Both cost the user no time, so switching them off would trade safety
   for nothing. Reading `silent` as *do not classify* silently disarms both.

## Resolving the effective keys

Run the resolver; do not read the table by eye.

```bash
bash skills/project-lifecycle/hooks/mode-expand.sh --claude-md CLAUDE.md
```

Output is one row per effective key, tab-separated, sorted:

```
archetype	silent	preset:fast
brainstorm	quick	preset:fast
cadence	compressed	preset:fast
close-gate	pr-boundary	preset:fast
```

The third column is the **source**, and it is what makes conflicts visible instead of accidental.

**Precedence, written down rather than emergent:** an explicitly set low-level key **always** beats
the preset. `mode: fast` plus `cadence: full` resolves to `cadence=full source=explicit`, and every
other key still comes from the `fast` preset. This is a rule, not a side effect of the order the
file happens to be read in.

**An unrecognised `mode` is an error, not a default.** `mode: turbo` exits 2, names the value and
the legal set, and emits **no** resolved configuration. A value that quietly falls through to some
default is a silent misconfiguration.

## The three new low-level keys

- **`brainstorm: full | quick`** — how heavily the decision stage runs. `quick` skips the A/B mode
  question, skips the two cross-check agents (spec↔Q&A, plan↔spec), and asks the user only at a
  real fork. **The blind second agent is kept**, at reduced frequency: `full` runs one per design
  question, `quick` runs **one per phase, positioned after the plan is written**. That position is
  chosen because it is the last moment where changing course is still cheap. It runs in the
  background and reports only if it finds something, so it adds no pause.

- **`cadence: full | compressed`** — how many agents each task dispatches. `compressed` is 2. See
  §"Dispatch" — and note it is **not** the same thing as the condition-triggered *cadence
  compression* in `cadence.md`, which skips the acceptance step. `compressed` skips no stage.

- **`autonomy: full | ship-shape`** — how many points a human appears at. `ship-shape` means the
  spec is not handed to a person to read (a cross-check agent reads it and reports only
  deviations), roadmap and status edits are batched to one approval at close, and distilled lessons
  are not promoted one interruption at a time.

## What `fast` keeps

A shorter list would be easier to sell and would be a lie. `fast` keeps:

| Kept | Why |
|---|---|
| the intent gate | It defaults to *here are my assumptions, tap to confirm* rather than a question. Only an explicit `intent-gate:` turns it down; `mode` never does |
| the Q&A record, the spec, the plan | All three are still written. What `quick` drops is the pair of agents that cross-read them |
| Track A checklist and Track B automation | Track B runs automatically **and is a gate item**. That is precisely why `fast` can stop only twice — nobody has to be summoned to click through a smoke pass |
| the close gate | It runs on every push and blocks when red. `pr-boundary` moves *the human approval*, not *the gate* |
| every document | Both modes emit the same files. See §"Artifact shape" |
| Sweeper's net-delete check, Maintainer's security review | They cost no human time |

## What `fast` drops, and which key owns each

| Dropped | Owned by |
|---|---|
| the archetype confirmation tap | `archetype: silent` |
| the brainstorm A/B mode question | `brainstorm: quick` |
| the two cross-check agents | `brainstorm: quick` |
| per-task human close approval | `close-gate: pr-boundary` |
| the smoke interaction-mode question | `smoke-mode: self` |
| roadmap and status edits approved one at a time | `autonomy: ship-shape` |
| distilled lessons promoted one at a time | `autonomy: ship-shape` |
| the spec handed to a person to read | `autonomy: ship-shape` |

**If a step needs dropping and has no key of its own — stop and report.** Writing the behaviour
into `mode` directly would make the dial a black box and would end the ablation.

## Dispatch

<!-- plc-dispatch:begin -->
```json
{
  "cadence": {
    "full": [
      {"slot": "implementer", "writes": ["code", "unit-tests"]},
      {"slot": "acceptance", "writes": ["acceptance-tests", "acceptance-report"]},
      {"slot": "validation", "writes": ["validation-report"]},
      {"slot": "quality", "writes": ["quality-report"]}
    ],
    "compressed": [
      {"slot": "implementer", "writes": ["code", "unit-tests"]},
      {"slot": "reviewer", "writes": ["acceptance-tests", "acceptance-report", "validation-report", "quality-report"]}
    ]
  },
  "stages": ["acceptance", "validation", "quality"],
  "acceptance_author_must_not_be": "implementer"
}
```
<!-- plc-dispatch:end -->

**Two hard constraints, and both are checkable from the table above:**

1. **`compressed` changes who does the work and how many are dispatched — never whether a stage
   runs.** All three verification stages run in both modes. In `compressed` they share one agent
   and run back to back, and each remains an operation that can be **dispatched on its own and
   produces its own report** (`hooks/plc-verify-stage.sh`). Inlining a stage into the implementer's
   prompt would destroy that, and a later feature that wants to expose these stages as commands the
   user types would have nothing left to expose.

2. **The agent that writes the acceptance tests is never the agent that wrote the code.** Each
   agent is a fresh instance with its own context that cannot see the main conversation. That
   isolation is the point: an agent that wrote the code will defend it.

**What `fast` gives up here is depth, not independence.** Three stages read by one agent in
sequence is weaker than three agents each arriving with its own lens. `fast` assumes being wrong is
cheap. Work that does not fit that assumption belongs in `detailed`.

## Artifact shape

**Both modes produce the same files with the same headings.** One table drives both — there is no
per-mode variant to diverge:

<!-- plc-artifact-shape:begin -->
| Artifact | Path |
|---|---|
| user story | `docs/superpowers/specs/<date>-phase-<phase>-user-story.md` |
| design spec | `docs/superpowers/specs/<date>-phase-<phase>-design.md` |
| plan | `docs/superpowers/plans/<date>-phase-<phase>.md` |
| Q&A log | `docs/qa-log.d/<date>-<branch-slug>.md` |
| journal | `docs/journal.d/<date>-<branch-slug>-<task>.md` |
| pre-merge brief | the PR body, top block (`pre-merge-brief.md`) |
<!-- plc-artifact-shape:end -->

`mode` decides whether a heading has prose under it or a skip marker. It never decides whether the
heading is there.

Three reasons this is the shape, and the third is the one that outlives the others:

1. Preserving context is the point of the whole discipline; a mode that drops it is not a mode.
2. A blank section with no explanation reads as a bug.
3. It makes the difference between the modes **auditable** — open any phase's record and you can
   see which steps ran. An experiment asking *which step produced the benefit* needs exactly that.

## Skipped fields

A step the current mode did not run keeps its heading. The body is exactly two lines, and **both
come from `hooks/plc-skip-marker.sh`** — neither is written by a model:

```markdown
### 2nd-agent independent pick

<!-- plc-mode-skip: second-agent | mode=fast | phase=1.2 -->
_Not run under the fast mode. To fill it in: set `mode: detailed` and re-run this step._
```

- Line 1 is machine-read. Its format is fixed so that *which phases skipped which steps* is
  countable. A hand-written variant is a row nobody ever counts.
- Line 2 answers *why is this blank* for a human. It is fixed English so the marker block stays
  stable and greppable; the plain-language rendering happens in conversation.
- The wording says "set `mode: detailed`" unconditionally. `detailed` never skips a step, so the
  marker cannot legitimately appear with `mode=detailed` and the sentence has no self-contradicting
  case to cover.
- **Its first consumer is item 3 of the pre-merge brief**, which counts skipped steps straight off
  these markers rather than keeping a second list. A second list would drift.

## Provenance — what every phase's record must say

One line, fixed shape, in the phase's Q&A log fragment:

```
mode: fast · source: project-default · confirmed-at: kickoff
```

- **`source`** is `project-default` or `override`. A one-off *"do this carefully"* records
  `override`; the **next** phase records `project-default`, and that next record is the externally
  observable evidence that the override did not stick.
- **`confirmed-at`** is `kickoff` when the user's tap on the start-of-work screen carried it, which
  is the normal case — the mode rides on a stop that was happening anyway.
- **One line per confirmation.** A second line in the same phase means the mode was raised a second
  time, which `fast` is not allowed to do — unless the mode genuinely changed mid-phase, in which
  case the extra line is the record of that change and must carry its own `source: override`.
- An unrecognised `source` is an error, the same way an unrecognised `mode` is.

## When the merge button is not a boundary

`fast` reduces the human to two moments, and the second one — clicking merge — carries the weight of
everything the other stops used to catch. It can only carry that weight for one reason: **an
assistant cannot click it.** That reason depends entirely on the forge refusing a direct push to the
default branch. Take the protection away and the button stops being a boundary; it becomes a
formality an assistant can walk around with `git push`.

**On GitHub, a private repository on the Free plan cannot have branch protection at all** — neither
classic protected branches nor rulesets. Both are public-repository-only on Free and require Pro,
Team or Enterprise for private repositories. That is exactly the shape a lot of this skill's users
are in: a private project, a free account, no intention of publishing it.

So the requirement has an escape, and the escape is a written admission rather than a silence:

```yaml
# CLAUDE.md
merge-boundary: unprotected-acknowledged
```

- **Unset (the default)** — under `fast`, the default branch must be protected and a push to it must
  actually be refused. Both halves, because reading the setting is not the same as the rule applying
  to this actor.
- **`unprotected-acknowledged`** — you have said, in writing, that this repository's merge button is
  not a hard boundary. The check then prints that in one line and does not block.

**One sentence has to survive being repeated, because it is the whole content of the admission:**
on such a repository nothing stops an assistant from pushing the default branch directly, so
"nobody merged it" is not a thing you can conclude.

**Why an admission and not just silence.** Anyone can write that line, so it buys no safety at all —
it is not meant to. What it removes is a person believing they have a boundary they do not have.
`fast` is already the mode whose premise is *being wrong is cheap*; going without the merge boundary
is a real cost, and the only honest thing to do with a cost you cannot remove is to name it before
someone pays it.

**What would NOT work, checked rather than assumed:** substituting some other action an assistant
cannot perform. In a repository where the assistant has full write access there is no such action —
a local `pre-push` hook is a file it can delete, a branch is one it can push. The GitHub merge
button was special *only* because of a server-side rule.

## The exception channel out of `fast`

Some changes do not fit `fast`'s assumption that being wrong is cheap. When a task's uncommitted
changes touch a place the project marked, or one of three signals that need no marking at all, that
task's verification tail runs at `cadence: full` — the four-agent arm of the table above rather than
the two-agent one.

**It moves `cadence` and nothing else.** `brainstorm` is phase-scoped and is structurally already
past by the time a task runs, and `autonomy`'s per-task surface is the human close approval, which
the `close-gate` key owns.

**The lists live in `references/careful-paths.md` and are not repeated here.** One data block, one
reader; a second copy is the drift that shape exists to prevent.

## Where the mode is visible

1. The first line of the start-of-work screen, once per phase — so it can never be discovered six
   months in.
2. Whenever the assistant changes it mid-run, with the reason, at the moment it happens.
3. In the pre-merge brief, so the record carries it even if nobody read the screen closely.

Everywhere else it stays quiet.

## Anti-patterns

- **Writing a behaviour directly into `mode`** with no key of its own — it makes the dial opaque
  and ends any hope of measuring which step earned its keep.
- **Reading `archetype: silent` as "do not classify"** — it silently disarms two protections that
  cost the user nothing.
- **Restating the expansion map anywhere else** — one map, one file. A second copy is a stale copy.
- **Treating `close-gate: pr-boundary` as "the gate is off"** — it moves the human approval, not
  the gate.
- **Treating `smoke-mode: self` as "no smoke"** — Track B still runs and still gates.
