# Experiment Gate

When a change must say, before it exists, what it expects to improve and how we would know.

The failure this exists to stop is not "we did not measure enough". It is that **there was no
hypothesis to measure against**, so the change shipped and nobody could call it an improvement or a
non-improvement. Writing the proposal is what forces the hypothesis to exist. That is the whole
mechanism; everything below is its shape.

Runs at **per-phase step 3.5**, between the spec cross-check (step 3) and Plan (step 4).

## Why 3.5 and not after the plan

The spec says what to build. The proposal says how we will know it worked. **Only then can the plan
schedule the work of building the measurement.** Placed after Plan, the measurement's cost sits
outside the plan and is the first thing squeezed out when the phase runs long.

There is a second reason, specific to this skill's shape: step 4 carries the plan↔spec cross-check
(agent B), which requires every spec item to have a covering plan step. At 3.5 the proposal is a
spec item and that cross-check will demand a plan step for it. At 4.5 it is invisible to the check
entirely.

## Section A — the three things that must exist before work starts

| | who decides | what is NOT allowed |
|---|---|---|
| **The definition of success** | brainstormed **with** the user | AI proposes, user nods. Offer **tiers with each tier's cost**, in plain language, so there is something to choose between and something to push back on |
| **How many experiments** | confirmed with the user | AI splits the work and announces it. **The split is itself a decision** |
| **The proposal** | AI drafts, user confirms, *then* anything runs | written afterwards to explain a result |

The middle row is the one most often skipped, because splitting looks like planning rather than
deciding. It is deciding: it fixes what gets compared against what.

## Section B — the proposal template

Nine sections. Write one before each experiment runs.

```
## Experiment <n> · <one-line title>

**Hypothesis**    A falsifiable sentence: changing X improves Y, or at least does not make it
                  worse. NOT "let us see what happens".
**Baseline**      What the number is today, where it came from, which commit it was measured on.
                  No baseline, no experiment.
**Dataset**       Which cases; how they are stratified (normal / edge / known-failure / difficulty);
                  whether they represent the real distribution.
**Ground Truth**  Where the right answer for each case comes from — planted, human-labelled, a test
                  failure, a production incident.
**Metrics**       One primary (decides pass/fail) plus guardrails (proves you did not wreck
                  something else to move the primary).
**Procedure**     What is held fixed; how many runs; one change at a time.
**Variance**      How many repeats; how reported (mean / spread / interval); whether the instrument
                  can even resolve the difference you are looking for.
**Decision Rule** What number counts as pass, as fail, and as NOT MEASURABLE. Three states. Fixed
                  before looking.
**Cost**          Money and human hours. Anything paid is stated and waits for an explicit yes.
```

### Decision Rule is three-state, and the third state is the point

**pass / fail / not-measurable.**

With only two states, a result the instrument cannot resolve gets forced into "fail", and "fail" is
then read as *"the change did nothing"*. The truth was **the scale could not see it**. Those are
different findings with different next actions — one says stop, the other says get a better scale.

## Section C — after it runs: suspect the instrument first

A checker that has never been wrong has usually never been checked. In the run this discipline came
from, the checker produced **five** confidently wrong numbers before it produced a trustworthy one —
every one of them looking like a finding.

**Three tells that it is the instrument, not the system:**

- **One-sided results** — sixteen wrong and fourteen wrong in the *same direction* is a systematic
  offset, not a discovery.
- **A constant offset** — every difference is exactly `-1`. That is a units or counting mismatch.
- **An implausible ratio** — *"67% of the citations are fabricated"*. Assume you are wrong first.

**Hard rule: hand-check three or four cases before reporting any finding.** In the originating run,
every single hand-check overturned the number that prompted it. No exceptions.

**Confirm a mechanism by reading the source, never by reasoning backwards from the number.**

### Things not to say, and what to say instead

Each row is a real near-miss, not a style preference.

| do not say | say | why |
|---|---|---|
| "fabricated" | **"not found"** | three "cannot find it" cases were all things that had *moved* |
| "no effect" | **"not measured"** | the scale not seeing it is not the thing not existing |
| "the path does not exist" | **"not found at the old address"** | renames and moves, three separate times |
| "it ran, so it works" | **"the mechanism fires"** + **"it has not been run for real"** | two claims; say the weak one out loud |
| "this one is free" | read the script header first | a paid run was nearly approved as free |

**Every "cannot find it" is a move until proven otherwise.** A rename map ships with the script and
carries its date — a missing entry does not error, it **manufactures a false finding**.

### The defect this whole gate is shaped around

> Many systems' "evidence validation" only checks **existence** and reports it as **"evidence
> verified"**. A citation that exists but does not support the conclusion is an entirely different
> failure.

That is why the close-gate check below prints the bound on its own pass. A mechanical check reported
without its limit gets read as a quality judgement, and *that* is the thing being guarded against —
not any particular missing file.

## Section D — when a proposal is NOT required

**A proposal demanded on every phase becomes a rubber stamp, which is worse than nothing.** A rubber
stamp costs the time and returns a document nobody believes, while also making the record look like
the discipline is running. This section is what keeps that from happening, and the reason has to
travel with the list — a trigger list without its reason gets widened by the next person who reads it.

### MUST write a proposal

The change moves a **measurable behaviour**: accuracy, recall, latency, cost, or a quality the user
can perceive.

### MAY skip

Pure rename · pure docs · pure formatting · dependency bump · a rewrite that preserves behaviour.

### The one-sentence test

**Can you write "changing X improves Y"?**

If you cannot, one of two things is true: this change needs no proposal, **or you do not yet know
what you are doing** — and the second is exactly when to stop rather than proceed.

### Recording a skip

A skip is a decision and goes in the record. In the journal's "Plan deviations":

```
SKIP: experiment-proposal — docs
SKIP: experiment-proposal — no-measurable-behaviour — the rename touches no call site and both
      suites cover the same paths
```

**Why a skip must be written at all.** If skipping is silent, *"we considered it and it does not
apply"* and *"nobody considered it"* leave **identical repository state**. Six months later nothing
can tell them apart. The written line makes the absence speak.

**Why it must name a category rather than be free text.** Free text produces `SKIP: not needed`,
which is a rubber stamp with extra steps. A token is an assertion someone can later find wrong.

The six, and they are closed — the gate matches against this list:

| token | means |
|---|---|
| `rename` | identifiers changed, behaviour did not |
| `docs` | prose only |
| `formatting` | whitespace or layout only |
| `dependency-bump` | a version moved, no call site changed |
| `equivalent-rewrite` | same behaviour, different implementation |
| `no-measurable-behaviour` | nothing measurable moves — **needs a clause, see below** |

**Why one token is not like the other five.** The first five are checkable against the diff: a
reader can confirm or refute "this was a rename". `no-measurable-behaviour` is a **judgement**, and
it is the same judgement this gate exists to force someone to make carefully. Bare, it is
`SKIP: not needed` with a hyphen in it, and it becomes the majority token because it is the one that
always holds in the writer's own opinion. So **that token alone carries a clause** naming what was
considered and why it does not move. A sentence is what the one-sentence test asks for anyway.

## Section E — the close-gate check

Armed by the `experiment-gate` policy key in `CLAUDE.md`, mirrored as `experiment_gate` in
`.claude/close-gate.json`. Phase mode only.

| value | behaviour |
|---|---|
| `required` | a proposal file must exist. A `SKIP:` line does not satisfy it |
| `ask` | a proposal file **or** a well-formed `SKIP:` line. Neither = `✗` |
| `off` | the row does not run. It is **listed as skipped, with its reason, on the check-set line** — not made invisible |

**Why `off` is still printed.** Making it vanish would satisfy the phrase this table used to
carry — "absent from the check-set line" — while breaking the rule that phrase exists to serve: a
check a filter removed silently is indistinguishable from one that passed, and an absent row is
also indistinguishable from a gate version that has no check 12 at all. *This sentence replaced a
false one. The old row described behaviour the code shipped alongside it does not have, which is
the exact defect this gate's own filings are about — caught by an independent
reviewer, in the document written to be the authoritative description.*

`ask` is not "warn instead of fail". A warning is not a refusal: a check downgraded to warn-only
here once produced twenty passes and zero reds, because the oracle read failure as "the line does
not start with ✓" and `⚠` does not either. `ask` means *the human decides per phase, and the
decision lands in the record either way*.

The check verifies: the proposal file exists at `docs/experiments/*-phase-<PHASE>-*.md`; it carries
all nine section headings; or a `SKIP:` line names one of the six tokens, with a clause when the
token is `no-measurable-behaviour`.

**What it prints, and why it must.** Three bounds, every run:

- it checked **existence and structure**, never whether the hypothesis is any good;
- **which enforcement it performed** on the category — a gate-side assertion, not a doc-side
  convention;
- for a clause, that one is **present**, never that it is **good**.

A gate is code. It cannot read a hypothesis and tell you it is well designed, and **a pass that does
not say so is read as saying so** — the existence-reported-as-verified failure named in Section C,
committed by the very mechanism built to teach the lesson.

## Section F — how often is this being skipped?

If `SKIP` runs at 90% after two months, the triggers in Section D are drawn wrong. That should be
visible from the record rather than from a feeling.

**Nothing counts this, deliberately.** Both satisfiers are already in git — proposals under
`docs/experiments/`, skips in the journal — so the ratio is a search:

```bash
# proposals written
git ls-files 'docs/experiments/*-phase-*.md' | wc -l
# skips recorded (hot fragments AND the archive — a milestone drain moves them)
git grep -c 'SKIP: experiment-proposal' -- 'docs/journal.d/' 'docs/archive/journal/'
```

The command is written down here, with its scope, so that two people running it months apart get
the same denominator rather than two different impressions.

**A tallied counter is refused on two independent grounds**, either sufficient: it is a derived
value frozen into a file, which rots and then lies; and it is a cumulative scoreboard, which reads
as a standing judgement rather than as information. The search answers the question without
becoming either.

## Section G — talking to a human about any of this

Two rules, both earned rather than assumed.

**When someone says they do not follow — change the telling, do not add detail.** Repeating the
sentence with annotations does not work. More detail is worse. In the originating run all three
successful repairs were **analogies**: the precision of a bathroom scale; a passing grade versus a
finish line; a teaching assistant grading their own exam.

**A passing bar is not a finish line, and conflating them will be caught.** The bar for "did this
change help" is low *because of what the instrument can resolve*, not because the standard is low.
The finish line — "is this actually fixed" — can be far higher and take many rounds. Describe the
bar as the finish line and the honest reaction is *"isn't that too little?"*, and that reaction is
correct.
