# Fixture — a sample phase's criteria, in the qualified declaration form

**This file is a hand-written list of a sample phase's criteria, not a claim about the true
denominator.** Counting a phase's criteria by hand, from its notes, or with a mechanical `AC[0-9]+`
scan gives three different answers, and nothing available can mechanically decide which is right.
The fourteen below stand for the ones a phase's design document declares at the
start of a line in its own form (`**ACn** — …`), which is a *measurable* subset.

**What the guard-removal test in `scripts/test_ac_evidence.py` needs from this file** is only that `p4:AC10` is in the list and that
the list is **identical across the two runs**. The differential is the evidence; the denominator is
not. If a fifteenth criterion is added here, that test's meaning is
unchanged.

The ids are written as `p4:ACn`. A design document may write them **bare** (`**AC10** — …`),
which is the unqualified form the parser refuses on purpose; a fixture in that form could not
be parsed at all, which is a different fact from the one under test.

The prose note above sits **outside** the section below on purpose: the parser's section grammar is closed,
so a bare explanatory line inside the section is a hard failure, not a comment.

## Acceptance criteria

- **p4:AC1**: Gate 4's predicate rejects a payload whose required field is present, non-null, and
  empty.
- **p4:AC2**: that rejection carries its own reason class, `empty-answer`, distinct from the
  malformed one.
- **p4:AC3**: the reason enumeration is updated in all four places it is declared.
- **p4:AC4**: the runner exits 3 when it did not obtain an answer, and 0 only when it did.
- **p4:AC5**: the envelope is a discriminated union whose two arms are key-disjoint.
- **p4:AC6**: every claim that the runner always exits 0, or that it never blocks or degrades, is
  corrected at the sites a caller copies from.
- **p4:AC8**: both callers are covered, not only the code-review path where the defect was first
  seen.
- **p4:AC9**: the chain is inserted immediately after the shebang, not before the last `exit 0`.
- **p4:AC10**: the gate order inverts, and every claim about it is made true in the same commit.
- **p4:AC11**: the reason class reaches the consumers that branch on it.
- **p4:AC12**: the normal path is unchanged — a hook with a trailing `exit 0` still gets the chain.
- **p4:AC14**: the new invariant follows the invariant contract exactly as the gate defines it.
- **p4:AC15**: its own limit is stated in the script rather than overclaimed — it cannot run when
  the wiring is absent.
- **p4:AC20**: the envelope's `mv` half is declared un-oracled rather than quietly counted.
