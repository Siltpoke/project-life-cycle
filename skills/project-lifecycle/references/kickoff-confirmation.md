# The start-of-work screen — the one stop `fast` makes before it starts

> **The mode rides on a stop that was happening anyway.** `fast` does not add a screen to announce
> itself; it puts the mode on the first line of the confirmation that already existed. Tapping
> **Start** confirms the mode and the content together.

## Why a preset and not a question

A person using this for the first time does not know what `fast` and `detailed` mean. Asking them
to choose means teaching them before they can answer. So the assistant **presets** one, **says
which**, and says how to change it. Nobody has to decide anything to begin, and the information is
given all the same. This is the same default the intent gate already runs on: state the assumption,
take one tap, do not interrogate.

## The screen

Rendered in the user's language. The template below is the structure, not the wording — every line
is written in plain language at run time.

```
┌───────────────────────────────────────────────────────┐
│  Mode: fast   <- my guess. Say the word and I'll switch│
│    fast = I don't interrupt in the middle. I stop here,│
│           and again when it's time to merge.           │
│    slow = I check with you at each step, and an        │
│           independent pass reviews the result.         │
│                                                        │
│  Don't use fast for: logins and passwords · taking     │
│  payments · storing other people's personal details ·  │
│  anything strangers will see on the open internet.     │
├───────────────────────────────────────────────────────┤
│  What kind of work this is: building something new     │
│    <- my read, because you said "make a ..."           │
├───────────────────────────────────────────────────────┤
│  What I'm going to do: <one sentence>                  │
│                                                        │
│  When it's done, it will:   <- ALL of them, none left  │
│    1. <criterion 1>                    out             │
│    2. <criterion 2>                                    │
│    (!) 3. <criterion 3>  <- I'm unsure here. Answer     │
│           before we start: <question>                  │
│                                                        │
│  How: <plan summary>                                   │
└───────────────────────────────────────────────────────┘
        [ Start ]              [ Change something ]
```

## The five rules, and what each one is for

### 1. No jargon on this screen

The screen is the one surface a non-technical person is asked to act on. **These words may not
appear on it**, and the list is a checkable one rather than an instruction to "write plainly":

```
cadence · archetype · oracle · AC · close-gate · subagent · validator
```

The list is deliberately short and deliberately mechanical. "Use plain language" cannot be checked
and so was never enforced; a word list can be, and it catches the specific vocabulary this skill
leaks. It does **not** guarantee the rest of the screen is readable — that part is still a judgement
nobody can automate, and saying so here is better than implying the check covers it.

### 2. The work-kind line, with a reason

`fast` does not stop to confirm what kind of work this is — it infers it and moves on. But two
protections ride on that inference being right: the net-delete check on tidy-up work, and the
mandatory security review on maintenance work. If the inference is wrong, **both fail silently**,
and the user is never told anything happened.

So the screen states the inference **and the reason for it**, in one line. That is a receiver for
the risk at zero extra interruption: the user can see "building something new — because you said
*make a*" and correct it in the same breath they approve everything else.

### 3. Every acceptance criterion, all of them, in order

The list on this screen is the designated receiver for the risk that the implementing agent reads
the criteria too narrowly. A receiver that shows three of nine criteria is not a receiver.

**All of them, in the story's order.** Not a summary, not the interesting ones. If the list is long,
it is long — that is information about the size of the work, and hiding it is the thing the screen
exists to prevent.

### 4. Uncertainty becomes a question that must be answered

`fast` reduces **how often you are interrupted**. It does not reduce **how much is asked**. Those
are different things, and confusing them is how a fast run ends up building the wrong thing quickly.

So: every point the assistant is unsure about appears on this screen as a **question that must be
answered**, marked so it stands out. **Start** is not available until each one has an answer.

**What counts as "a new interruption", stated so it can be checked:** a turn *outside this screen*
that waits for user input before anything can continue. Questions on the screen itself are not new
interruptions — the screen was always going to stop.

### 5. What not to use `fast` for

Four things, named on the screen before the user commits to anything:

- logins and passwords
- taking payments
- storing other people's personal details
- anything strangers will see on the open internet

**This is a warning, not a barrier.** A user who wants `fast` for these gets `fast`. The reason it
is a warning is not politeness — it is that "is this work touching a login?" cannot be decided
mechanically, and a barrier built on a guess would block the wrong work and miss the right work.

**Why it is here at all**: there are two real ways `fast` gets
someone hurt — a login built with only the success path tested, and a public page that leaks a home
address. Neither is caught by a path-based safety rule (a new project has no auth folder yet to
mark, and a leak of the wrong content matches no path), and neither is caught by automated smoke.
Telling the user before they choose is the one cheap action that actually helps.

## The recorded form

The screen is a conversation surface, and a conversation surface cannot be checked after the fact.
So when the user taps **Start**, the screen is written verbatim into the phase's Q&A log fragment,
wrapped in a fixed header block. **The header is the checkable part; the prose above and below it is
the screen as the user saw it, in whatever language they read.**

```markdown
<!-- plc-kickoff:begin -->
mode: fast | source: project-default | confirmed-at: kickoff
not-for-fast: logins-and-passwords | taking-payments | other-peoples-personal-details | public-to-strangers
work-kind: builder | because: the request says "make a ..."
criteria: p1:AC1 p1:AC2 p1:AC3
must-answer: 0 outstanding
<!-- plc-kickoff:end -->

...the screen exactly as the user saw it...
```

Five fields, one per rule above:

| Field | Rule | Checked how |
|---|---|---|
| `mode` | the mode line is first | present, its value is a declared mode, and it is **the same line** the phase record carries (`mode.md` §"Provenance") — if the two used different fields, "the tap confirmed the mode" would split from the record that is supposed to prove it |
| `not-for-fast` | rule 5 | exactly the four declared items |
| `work-kind` | rule 2 | present **and** carries a non-empty `because:` |
| `criteria` | rule 3 | the story's declared ids, all of them, in the story's order |
| `must-answer` | rule 4 | `0 outstanding` — Start was not available otherwise |
| `careful` | the extra round below | **present only when that round ran.** Carries the two counts and the four miss markers: `careful: proposed=<n> chosen=<n> \| misses: your-marking incomplete-ecosystems english-words path-not-intent`. All four markers required; the prose above them is the user's language and is not checked |

`hooks/plc-kickoff-check.sh <fragment> --story <user-story.md>` validates one recorded screen.
The jargon ban (rule 1) is checked over **the whole recorded block**, header and prose alike.

**What this does not do, stated rather than implied:** it checks the record, not the screen. Nothing
here proves the screen was shown, or that the user read it. The record is what a later reader —
including the person deciding whether to merge — actually has.

## The one extra round, on a first `fast` run with nothing marked

**Only when `careful-paths` is unset.** Once it has a value the question is never asked again — a
key that is already answered is not a question.

The round is a set of tick-boxes. Candidates come from
`hooks/plc-careful-suggest.sh --repo . --claude-md CLAUDE.md`, which reads **this project's own
directory structure**, never a shipped guess about what any particular framework looks like. Every
candidate arrives with the fact that produced it, and **zero candidates is a legal result** — the
screen then says so and asks the user to mark it themselves rather than inventing rows.

The answer is written back by `hooks/plc-careful-write.sh`, not by hand. The write is a scripted act
on purpose: it is the only way "did the answer actually get saved" becomes a question something can
fail on.

### Four sentences that go on this round, and all four are required

The tick-boxes are the moment the user forms an expectation of what this does. All four appear
together, because each is a different miss:

1. **You are marking this list, so anything you do not mark is not covered.** PLC does not claim to
   find every risky change automatically — it cannot.
2. **A language or framework the built-in signals do not name is a miss.** Dependency files and
   migration folders look different everywhere, and that list is fixed, not worked out on the spot.
3. **The suggestions are matched against English words.** Files and folders named in another
   language, or by your own convention, will not be suggested.
4. **This looks at which files changed, never at what the change did.** A change whose danger is in
   what it **removed** or **moved** does not show up here.

`hooks/plc-kickoff-check.sh` fails if a recorded screen carries a careful round with fewer than four
of them. The four are matched on a fixed marker line each, not on their prose — the wording is the
user's language, the marker is the checkable part, the same split the header block already uses.

## Where this screen sits

Once per phase, before any code. It is stop 1 of the two `fast` makes; stop 2 is the user clicking
merge. See `mode.md` §"Provenance" for the line this screen's approval writes into the record.

## Anti-patterns

- **Summarising the acceptance criteria.** The list is a receiver; a summary is not one.
- **Marking an uncertainty as a note instead of a question.** A note can be scrolled past; that is
  the whole difference.
- **Adding a second screen to ask the uncertainties.** That is a new interruption, and it is what
  the must-answer form exists to avoid.
- **Dropping the reason from the work-kind line.** Without it the user has nothing to correct
  against, and the line becomes an announcement rather than a receiver.
- **Treating the "don't use fast for" list as a gate.** It warns. It does not block.
