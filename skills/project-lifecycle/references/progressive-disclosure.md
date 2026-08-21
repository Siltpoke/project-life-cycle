# Progressive disclosure — deciding what may leave an always-loaded surface

A skill's `SKILL.md` is loaded on **every** session. Its `references/` are loaded when relevant.
So the always-loaded cost of a skill is the size of `SKILL.md` alone, and the recurring question
is: *what may be moved out of it without losing anything?*

This reference is the record of answering that question once, on this skill's own `SKILL.md`. The answer was
**"almost nothing, so don't"** — and the more useful output is *how the measurement kept being
wrong*, because every wrong version looked right and produced a number.

## The finding

Hand-verified, on `SKILL.md` as it stood when measured: **10 passages totalling 1,511 bytes — about
1.2% of `SKILL.md`'s prose — are substantially duplicated in an on-demand reference.** Four more
share a quarter to a half of their words and are not movable as they stand. Two are headings.

That does not earn a slimming pass.

**The largest and most redundant-looking block was the cleanest.** A references index looks like
the most obviously wasteful thing in an always-loaded file — dozens of entries describing files
that load on demand anyway. Not one of its entries is a duplicate: each is the skill's own
routing summary, authored for the index, not copied from the target.

## The tool, and what it is not

`scripts/skill_duplication_census.py` is a **one-shot probe**: a candidate generator whose output
is a reading queue. For each passage it prints a shingle-containment score, and — the column that
matters — **the longest run of consecutive words shared with the best-matching file**. A person
reads that run and decides. The probe states no verdict, and its summary line says in as many
words that its figures are not a measurement.

It was not always written that way, and the difference is this document's real content.

## Four claims removed

Each of these looked rigorous and was false. None was visible in the output.

**"The census reports N% duplication."** The first implementation used an 8-word shingle window.
It passed a verbatim control 10 times out of 10 at 100% and reported roughly a quarter of the
real duplication: one edited word destroys every 8-word window containing it, so it measured
*verbatim only* while its stated predicate was "verbatim or near-verbatim". Half a predicate,
behind a clean number. **A control that only tests the easy direction certifies a half-built
instrument.**

**"Zero false positives over 149 passages."** The negative control built its population by
removing a passage's own source file from the index and calling the remainder original.
Reference files in a set like this quote each other — two files here share a verbatim block — so
the premise is false. **26 of 50 random seeds put a genuine duplicate into the "original"
population, where the control fails.** It passed on the seed that was picked. *A control whose
result depends on its seed is not a control.*

**"The reported figure is a lower bound."** Adopted as the fix for the previous over-claim, and
itself an over-claim: a lower bound asserts the true value is never smaller. Shingles are a
**set**, so a passage repeating three words forty times matches a six-word reference at 100%.
The probe can overcount. **The correction for a claim wider than its mechanism was a claim wider
than its mechanism.**

**"N% of the surface exists somewhere in the tree."** Computed by counting a window as covered
if *any* reference held it. A passage whose every window lives in a *different* file scores 100%
on that union while existing nowhere. Removed rather than qualified.

Also removed: a calibration table of "light edit" and "heavy paraphrase" bands. Both were
simulated by **deleting** one word in seven or four. Deletion breaks only the windows straddling
the gap; substitution at the same nominal rate breaks every window containing the word and moves
the light band from 100% admitted to 15-26%. **The bands measured the edit model, not the
metric.** The same calibration also drew only from passages of 80+ words, while 80% of real
`SKILL.md` units are shorter — the regime where the metric is most volatile was never tested.

## What survived, and is asserted

- The probe reads every byte and can prove it: coverage is an accounting identity whose residue
  is `0`, not "small", and the report says nothing can be trusted if it ever is not. An earlier
  version was structurally `−1` on every input — a negative count of bytes not looked at, which
  on a large file surfaces only as a wrong positive number.
- Every candidate carries re-checkable evidence.
- Shared *vocabulary* without shared *order* is not shortlisted; the run column is what excludes
  it, and a mutant that removes the run gate reddens a row.
- The shortlist is **not exhaustive**: a passage sharing 56% of its words as one run can still
  score 52% on containment and fall out. Asserted, so the list is never read as a total.
- Text carrying no ASCII letters or digits scores 0 against everything including a byte-identical
  copy. The probe counts such passages and says they are absent from the list rather than cleared
  by it.

## The predicate that looks right and is not

Before any of the above: the first framing asked *"is this passage referenced by any workflow
step, hook, gate, or command?"* That presumes the consumer of `SKILL.md` is **code**. It is not.
A skill's largest prose blocks — stop-signs, conventions — are leaf instructions read by the
**model**; nothing calls them. Swept literally, that predicate marks the majority of a skill
unreferenced and issues a licence to move exactly the passages whose whole job is to be present
without being summoned.

Checking what a predicate would return on the surface's biggest blocks, *before* building it, was
the cheapest step in the entire exercise.

## If you are about to do this on your own skill

1. **Ask what your predicate would say about your biggest block, before you implement it.** If
   the answer is "move it", check that answer against someone who has read the block.
2. **Calibrate on the population you will actually judge**, not the convenient one. Length
   distribution matters more than sample size.
3. **Your edit model is a claim.** Deleting words, substituting words, and reordering words are
   three different experiments; do not label any of them "paraphrase" without checking the
   others.
4. **A number that nothing can redden is prose.** If a published figure has no assertion behind
   it, it can drift to anything.
5. **Prefer a reading queue to a verdict.** Ten candidates a person can check in five minutes are
   worth more than a percentage nobody can audit — and, on this skill, the honest queue was short
   enough that the whole question answered itself.
