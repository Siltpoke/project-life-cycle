# The pre-merge brief — the block at the top of a `fast` PR

> **This is where the risk `fast` moved went.** A fast run drops two cross-reading agents, the
> per-task human approval, and the spec hand-off. Nearly all of what those caught now arrives at one
> moment: the person clicking merge. A design that moves risk to a moment and then says nothing
> about what that moment looks like has not moved the risk — it has hidden it.

## Shape

One guidance line, then **exactly four items**. Missing one is a malformed brief, and so is a fifth.

```markdown
> **This is a report of what I did and what I missed. It is NOT someone having read the code.**

mode: fast

Stops in this phase:
  - phase-level: 2 (this start-of-work screen, and you clicking merge)
  - intent gate, one tap per request: 3

<!-- plc-brief-guidance -->
I suggest you look at:

  - scripts/pricing.py:88-104 -- the payment total is computed differently now
      before:
          def total(items):
              return sum(i.price for i in items)
    Nothing checked that amounts round to the nearest cent.

  - docs/notes.md -- one long-term rule is waiting on your decision (nothing written by default)

<!-- plc-brief-item: what-i-did -->
### 1. What I did

<!-- plc-brief-item: unchecked-criteria -->
### 2. Which acceptance criteria nothing checked

none

<!-- plc-brief-item: skipped-steps -->
### 3. Which steps were skipped this time

<!-- plc-brief-item: long-term -->
### 4. What would stick around

- [ ] ...

---
Manual smoke checklist (does not block merging):
- [ ] ...
```

**The `<!-- plc-brief-* -->` markers are how a checker tells an item from a heading that looks like
one.** Counting headings is not enough: four headings where the fourth points somewhere else is
neither four items nor a fourth item.

## The guidance line

**At most three things**, chosen in this order of priority:

1. an acceptance criterion nothing checked
2. a change to somewhere the user marked as needing care
3. a long-term record waiting on their decision

When all three are empty, it says so — *"nothing in particular to watch"* — rather than being
omitted. An absent line and a line saying "nothing" are different messages, and only one of them is
honest about having looked.

**Each thing carries three parts. Missing any one makes it unusable:**

1. **`file:line-range`** — somewhere to click
2. **the lines as they were before** — pasted, not described
3. **one sentence on why it is worth a look**

**Why "before" and not just "after".** Someone who does not read code cannot tell whether the new
version is correct. They *can* tell whether the old and new versions are doing the same kind of
thing. And later, when they want to know what something used to be, it is in the PR instead of
somewhere in the history.

The guidance line sits **above** the four items and is not one of them.

## Item 1 — What I did

One line per task, each naming which acceptance criteria it closed.

## Item 2 — Which acceptance criteria nothing checked

Listed one by one. **When the set is empty, write "none" explicitly.** Omitting the section is not
allowed, because an absent section and an empty one look identical to a reader and mean opposite
things. This is the most important line in the brief.

## Item 3 — Which steps were skipped

**Counted straight off the skip markers in the artifacts** (`mode.md` §"Skipped fields"), never
written out a second time. A second list drifts from the first, and then the brief is confidently
wrong.

## Item 4 — What would stick around

Some of what a phase learns gets distilled into files the assistant **reads first in every future
conversation**. Getting that right is valuable. Getting it wrong means it is still acting on the
wrong note three months later, and almost nothing points back to it as the cause.

**So: everything that would be written is listed here, every box unticked, and nothing is written
until a box is ticked.**

```markdown
### 4. What would stick around
- [ ] Add to the roadmap: "export to CSV follows in the next milestone"
- [ ] Add a standing rule: "prefer the resolver over reading the table"
```

**Two conditions, and it takes both to close the loop:**

1. **The candidates are not in this PR's diff.** If the change is already in the diff, an unticked
   box means nothing — merging writes it anyway.
   Without this half there is *no closed loop*.
2. **Writing happens after the choosing**, as a separate action
   (`hooks/plc-longterm-write.sh`). **Merging writes nothing.**

**How to check it:** run a phase that produces candidates, tick nothing, merge. Every long-term
record file must be **unchanged**.

The asymmetry behind the default: a missing note is fixed by mentioning it next time; a wrong note
is found three months later.

## The manual smoke checklist

Pasted **below** the four items, and **it does not block merging**. It is not a fifth item.

Automated smoke cannot see what a real browser shows a real person — a button hidden behind another
element passes every automated check. So the checklist has to be in front of the reader. But
blocking on it would reintroduce the wait that `fast` exists to remove.

## The sentence that must be printed

> This is a report of what I did and what I missed. **It is NOT someone having read the code.**

Without it, clicking merge reads as *it was reviewed*. It was not.

## The counts

The brief carries **two numbers, separately**:

```
Stops in this phase:
  - phase-level: 2 (this start-of-work screen, and you clicking merge)
  - intent gate, one tap per request: <measured>
```

**They may not be merged into one number, and the second may not be omitted.** The intent gate is a
real place a person is asked for a tap; folding it away would make "only two stops" true by
accounting rather than by design.

## The mode line

The brief states which mode this phase actually ran in. This is the third of the three places the
mode is visible (`mode.md` §"Where the mode is visible"), and it is the one that survives nobody
having read the first two.

## Anti-patterns

- **Omitting item 2 when it is empty.** Write "none".
- **A fifth item**, or an item that is a pointer to something else rather than the thing itself.
- **Re-listing skipped steps by hand** instead of counting the markers.
- **Long-term candidates inside the diff.** Then the tick-box is decoration.
- **Merging the two counts.** Or dropping the intent-gate one.
- **Putting the smoke checklist among the four items**, or making it block.
