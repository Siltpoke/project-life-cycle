# Where Does This Go?

Routing for a **side discovery**: something real that surfaces while you are working on a phase and
**is not that phase's subject**. A gate error that names no cause. A document that contradicts
itself. A surface that was disabled and never deleted. A remark in passing.

**The gap this fills, stated exactly.** Three routers already existed, each correct inside its own
input scope, and none of them accepts an item of this kind:

| router | accepts | outcomes |
|---|---|---|
| `defer-vs-fix.md` | reviewer findings, the ambiguous Important ones | fix now / defer to backlog |
| `findings-tier.md` | smoke findings, review concerns, known limitations of a delivered phase | S1 / S2 / S3 |
| `intent-gate.md` | a fresh user request | trivial / medium / large (how much ceremony) |

So an item that is **neither a user request nor a review finding** had no route at all, and survived
only when a human happened to ask about it. This file takes that class. It does **not** replace any
of the three above -- each is still correct and still in use.

## Capture first, decide later. They are different acts.

**Capture, at the moment of discovery:** append one line. No decision, no classification, no prompt
to anyone. This is deliberately the cheapest act available, because it is the one nothing can
enforce -- see "What this cannot do".

**Decide, once, at phase close:** every captured line gets an outcome. Nothing reaches a human
except the two cases named under "Who drains this".

The split is not a preference. Four independent systems converge on it -- GTD separates capture
("without filtering") from clarify; Linear's Triage is an inbox drained with four fixed verbs;
Chromium's network team runs a sheriff rotation whose target is an empty untriaged query; Mozilla
defines "triaged" as two checkable fields rather than a judgement. All four report the same failure
mode, which is worth knowing before you adopt this: **an inbox is only as good as its drain.**

## The queue, and its grammar

**One file per PHASE**, at the manifest's `sidelines` path -- `.claude/sidelines/{PHASE}.md`, which
the gate's accessor expands, so this phase's queue is `.claude/sidelines/<phase>.md`. **Not tracked**
-- `scripts/invariants/sidelines-never-tracked.sh` asserts that for the whole family, and
`.gitignore` carries it with its reason. It is working state; the phase's outcome in the journal is
the permanent record, and phase mode now **checks** that rather than trusting it.

Copy this header into a new queue:

```
# Side discoveries — phase <id>
```

> **This paragraph used to say "One file per branch", and the wording is quoted rather than deleted
> because it was the bug.** Nothing read a branch name -- the gate has no
> `BRANCH` variable -- so the file belonged to the directory on disk. Before the fix, with the
> previous phase's drained queue at the old fixed path, row 13 printed
> `N item line(s) ... zero untriaged` on a phase that had recorded nothing, and
> `sidelines-never-tracked` stayed green beside it. The previous phase's evidence vouched for the
> next one. The path now carries the phase id, so a new phase's queue is **absent** until it is
> written, and absence at phase close is a red that names any leftover queue it finds.
>
> **The bound that replaces it, printed in the row's own output as `bound:keyed-by-phase`:** two
> branches sharing one phase id share one queue, so a previous cut's drained queue would still
> vouch for a re-cut under the same id. Closing that needs a check over refs and is not built.

**The path has two readers and they do not read the same source, which is a known gap and not a
feature.** The gate's row 13 reads the manifest key `sidelines` and nothing else. The tracking
invariant reads `PLC_SIDELINES_FILE` or its own default, and never the manifest -- deliberately, so
that a configured value which is not a path is refused fail-closed rather than matching the whole
index. With that variable set, the invariant would certify one file while the gate checked another.
**Do not set it.** Filed with an Exit criterion that
makes one of the two the single source.

One item per line:

```
- [untriaged] <what was found> | ctx: <what made it legible at the time>
- [landed:fix <sha>] <what was found> | ctx: <...>
- [landed:backlog <id>] <what was found> | ctx: <...>
- [landed:mainline-proposed] <what was found> | ctx: <...>
- [refused] <what was found> | ctx: <...> | class: <1|2|3|4>
- [declined] <what was found> | ctx: <...> | why: <reason>
- [none] <nothing out-of-theme surfaced in this phase>
```

**Why each field is there, since a grammar nobody understands gets filled in wrongly:**

- `ctx:` is **not** a second description. It is the thing that made the discovery legible *at the
  moment it surfaced* -- the two files that contradicted each other, the command whose output was
  wrong. By the time the queue is drained the context is colder, and this field is what survives
  that gap. It is the one concession to the fact that the enforced moment is the late one.
- `class:` on `refused` names which of the four refusal classes applies, so a rising refusal rate can
  be read by class rather than as one undifferentiated number.
- `why:` on `declined` exists because **a refusal with no reason is indistinguishable from
  forgetting**, and telling those two apart is the whole point of the file.
- `[none]` is an explicit verdict, not an empty file. An absent queue and a phase that genuinely
  tripped over nothing must not look the same -- that is the shape where a lost queue reads as a
  clean phase.

**`snoozed` is deliberately not a state.** A thing that should come back later is
`landed:backlog <id>` with the wake-up condition written in that entry's `Trigger`. The queue is
per-phase and untracked, so a state meaning "stay here until later" would be left behind by the next
phase, which reads a different file; and nothing in this discipline fires on a date, so there is no
timer to resurface it with.
Using the backlog's existing `Trigger` costs nothing and actually survives.

**Two checks, two different questions, and `close-gate.sh` row 13 (`sidelines`) performs them.**

`close-gate.sh task` -- which the pre-push hook runs on *every* push -- checks only that each line
is a well-formed item: anchored at column 0, opening with a **recognised state token**. A missing
file is fine. `close-gate.sh phase` requires the file to exist, `untriaged` to be empty or `[none]`
present, and every `refused` / `declined` to carry its field.

The split is load-bearing: if "empty" were checked on every push, capturing a line would block the
next push until it was routed, which would make capture expensive and therefore kill it. **Capture
must stay free.**

The row reports its own bound, `bound:declarations-only`: it reads what was DECLARED and cannot see
a discovery nobody wrote down, so `- [none]` is a statement and not a verified fact. What the row
buys is that a *captured* discovery can no longer be lost **silently** -- never that none is lost.
One further limit, measured rather than reasoned, still open: the row does not verify that a landing
id **resolves** to anything, so `- [landed:backlog B99999]` and `- [landed:fix not-a-real-commit]` both pass.
"It has a landing" still means "someone typed parseable characters" (a tracked defect).

> **The second limit on this list is closed, and the sentence is rewritten rather
> than deleted.** It read: *"and it does not read the journal, so 'the outcome is in the journal
> fragment' is a discipline and not a check"*. Phase mode now reads the journal fragment the gate
> had already resolved and requires both a side-discovery outcome section and coverage of every
> landing id (a tracked change). The hole was demonstrated before it was closed: with a
> drained queue and **zero** journal fragments for the phase, the row printed
> `✓ sidelines: N item line(s) ... zero untriaged`.
>
> Its replacement bound, printed with the verdict as `bound:outcome-by-heading`: the outcome section
> is recognised by its **heading**, so a heading that merely mentions side discoveries satisfies it.
> Reading the section's content would need a machine-written fenced block — which would red every
> fragment written before that day, including the golden control this check is tested against — or
> semantic judgement. Neither was taken.

> **This paragraph used to say the opposite, and the history is kept rather than deleted.** Until
> the row landed it read *"the gate row that performs them is NOT BUILT YET ... until the row exists
> nothing enforces any of it"*, written that way deliberately, because describing an unbuilt
> mechanism in the present tense is a claim wider than its mechanism. The row then landed in the
> same phase and **nobody came back to this paragraph** -- so for the length of one PR this document
> told its readers that the mechanism it ships with does not exist, which is the same defect with
> the sign flipped. Found by review, and not
> by any check: no invariant reads this paragraph. That is the standing gap, recorded here because
> deleting the wrong sentence would also delete the evidence that a document can go stale against
> code written beside it on the same day.

Without the row, the queue would be discipline-only, and a prose-only rule gets skipped -- even by a
session that has just read the record of the same failure. That is why the row exists.

## The four outcomes

Decided by questions, not by a score. Scoring formulas (RICE, ICE, WSJF) produce an *ordering*; the
frameworks that route work into different *containers* -- Shape Up's betting table, SAFe's epic gate
-- all do it with a gate.

**1. Fix now** -- it blocks this phase's own subject, **or** the fix lies inside the diff already
open. The second half matters: a one-line correction in a file you are already editing is cheaper to
do than to file.

**2. Backlog entry** -- it stands alone, and one entry holds it completely. This is the default, and
it should be: an entry is cheap, and a wrongly-filed entry costs an edit.

**3. Main-line candidate** -- **it has a thesis.** An argument that binds several entries into one
track, rather than a single fact that one entry can state. **Proposed to a human, never written by
the mechanism.**

**4. Refused** -- handed to a human, because this criterion does not decide it. See below. Refused
is *not* a fourth container; it is the absence of a routing decision.

### Why "a thesis" and not a size or a count

Two earlier versions of test 3 were wrong, and both are recorded because the reasoning is the
useful part:

- *"a cluster of at least two related entries"* -- an **invented number**. No published threshold
  exists for "a theme emerges from N related items"; SAFe defines an epic by approval, Shape Up by a
  time budget, and other sources by decomposability. Three different axes, no count.
- *"its appetite exceeds one session"* -- **not a reliable separator.** Appetite is an estimate, and
  the estimates for a promoted case and a deferred one can differ by a margin far too thin to route on.
  Under that rule a case that deserved promotion might not have qualified.

What separates them is Shape Up's **shaped**: a thing is bettable once it has been given an argument
and a boundary, not once it is large. Appetite survives as a *second* gate -- a thing with a thesis
that one session would close is still a backlog entry.

## Refuses to decide

This criterion does not decide the following, and hands them to a human instead. Naming them is the
point: a rule that claims to decide every case is a claim wider than the mechanism behind it.

1. **It changes what a container means.** A proposal to redefine "backlog entry" or "main line" is
   not an item to route.
2. **It would enact a reversal of a landing a human already made.** The criterion may **propose** a
   reversal and show its evidence -- that is expected, see "Routing down". What it may never do is
   carry one out.
3. **The cluster is visible but its thesis is not yet articulable.** This is Cynefin's *confusion*
   state, whose documented exit is to decompose and re-route each part, not to decide. If you cannot
   write the argument down in a sentence, there is no thesis yet.
4. **Its appetite cannot be estimated** because the work is unscoped. An unscoped thing cannot be
   compared against a session.

### Pricing the hatch

An escape hatch that costs nothing becomes the default path, and then the criterion has stopped
working while looking diligent. Medical triage handles this by publishing an accepted over-triage
rate and watching it, rather than forbidding over-triage.

**So the expectation is written down and watchable: the refusal rate is a minority of routed items.**
No number is published yet, and the reason is stated rather than hidden -- the calibration set is
three items, and a rate from three is not a rate. The outcome record written at every phase close is
what makes the real rate countable later.

**If refusals exceed half of all routed items, that is a defect to file against this criterion, not
a safe default.** A criterion that mostly refuses is not deciding.

## Routing down

A landing can be reversed, and the reversal is a proposal carrying its evidence -- never a silent
flip (refusal class 2).

This direction is not decoration. The roadmap's own index table is **in-only**: entries go onto it
and never come off. That is the recorded proof that neither direction had a criterion before this
file, only habit.

## Who drains this

Every capture-plus-inbox system surveyed assumes a **named owner** for the drain. Without one, the
inbox rots -- that is the single failure mode all four sources agree on. So the split is explicit:

| outcome | who executes it |
|---|---|
| fix now | the agent |
| backlog entry | the agent |
| main-line candidate | **proposed to the human**, who decides |
| refused | **handed to the human**, who decides |

The asymmetry is deliberate: a misfiled backlog entry costs an edit, a misfiled main-line row costs
a track. Nothing else reaches the human, which is what keeps the drain affordable enough to actually
happen.

## Calibration

Three landings decided before this criterion existed. **They are the
oracle. The criterion is adjusted to them; they are never adjusted to the criterion.**

| discovery | landing | why, under the tests above |
|---|---|---|
| **B7272** -- a discovery that carries a thesis shared with other entries | **main line** | the thesis -- a claim the project makes about itself that its own tooling contradicts -- is an argument no single entry can hold, so it needs a place above the entries |
| **B7270** -- a standalone discovery with one self-contained fix | **backlog entry** | one entry states it completely |
| **B7271** -- a second standalone discovery with one self-contained fix | **backlog entry** | one entry states it completely |

The criterion must also route down: an entry whose main-line thesis stops being supported returns to a plain backlog entry (see "Routing down"). A criterion that can only promote fails that case.

## What this cannot do

Written here, not left for a reader to discover:

- **It cannot detect a discovery nobody wrote down.** Capture is the one unenforced act, and it sits
  exactly where forgetting happens. A gate can force a *declaration*; it cannot know what was never
  declared. So the honest claim is that a side discovery can no longer be lost **silently** -- never
  that none is lost.
- **It cannot tell an over-capture from a real discovery.** If in-theme observations get captured as
  "harmless", the drain's cost grows with the false positives. Record the share that turn out to be
  in-theme; that number is what makes a target possible later.
- **It does not resurface anything on a timer.** Nothing in this discipline fires on a date. A thing
  that should come back later becomes a backlog entry whose `Trigger` names the condition -- the
  existing, tracked mechanism, rather than a scheduler.
- **The refusal classes are ours, not an industry pattern.** No field surveyed publishes a threshold
  for "worth interrupting a human over". Treat class boundaries as the highest-priority thing to
  review when this criterion gets something wrong.
