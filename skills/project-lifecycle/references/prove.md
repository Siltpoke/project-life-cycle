# Prove — one vocabulary for "did it work?"

PLC says "did it work?" in several places (the acceptance-verifier, the validator, M1's
behavior-lock, the test-evidence fingerprint, the trial rule's coverage tags). This reference is
the single vocabulary that ties them together. It does not replace any of them; it names them once.

## Verification-status enum (the 5 tokens)

One word for the state of a claim, used everywhere a verification result is reported:

| Token | Meaning |
|---|---|
| **VERIFIED** | You ran it AND an assertion exercised the behavior's contract. Code reading is never VERIFIED; a test's name is never VERIFIED. |
| **FAIL** | You ran it and an assertion failed. |
| **PARTIAL** | A meaningful assertion checks *part* of the contract, but not all of it. |
| **UNVERIFIED** | No meaningful assertion checks it -- even if the whole suite is green. A completion claim with no execution evidence is UNVERIFIED, not PASS. |
| **BLOCKED** | Could not run (missing dependency, environment, or a prerequisite that failed). Not a pass and not a fail -- it never ran. |

The one rule that makes the enum honest: **a green suite is not proof of no regression.** Say which
behaviors it covers. "The suite passed" maps to VERIFIED only for the behaviors an assertion actually
exercised; everything else in the diff is UNVERIFIED until shown otherwise.

## Regression vs validation (two different jobs)

"Prove it works" is two questions, and PLC answers them with two different mechanisms:

- **Regression** — did this change preserve what already worked? Proven by the **Behavior Lock**
  (M1): a PRESERVE row bound to a carrier test, with a before/after characterization baseline
  (`scripts/behavior-baseline.sh`). The question is "is the old behavior still VERIFIED?"
- **Validation** — does the new behavior meet what was asked? Proven by the **user-story + the
  acceptance-verifier**: each acceptance criterion checked against the running change. The question
  is "is the new behavior VERIFIED against its AC?"

A green suite on its own is neither. Regression needs the preserved behaviors named and their
carriers run; validation needs the ACs named and checked. Keep the two apart in any report.

## Per-behavior evidence (the fields)

For one behavior, the evidence that moves it to VERIFIED is a fixed set of fields:

- **assertion** — the exact assertion that exercises the contract (quoted, not paraphrased). This is
  the behavior-lock carrier.
- **command** — what was run (the repro command).
- **exit** — the exit code observed.
- **before / after** — the result on the SAME inputs and environment, before and after the change.
  Recorded by `scripts/behavior-baseline.sh` (`--record <id> before|after ...`). Expected
  transitions: PRESERVE pass->pass, FIX fail->pass, NEW na->pass; a contradiction is red.

The Behavior Lock registry (`.claude/behavior-lock.tsv`) already carries behavior + carrier + why;
the baseline carries cmd/exit/before/after. Together they ARE the per-behavior evidence record --
this reference names the full set, it does not add a new file.

## The acceptance ladder (four rungs, not one)

"Done" is four distinct states, and a claim can sit on any rung:

1. **Implemented** — the code exists.
2. **Tested** — a test runs the code.
3. **Verified** — an assertion exercises the behavioral contract AND you ran it (the enum's
   VERIFIED). Tested without a meaningful assertion is still UNVERIFIED.
4. **Accepted** — the human signed off against the user-story's acceptance criteria.

The rungs do not collapse. "Implemented" is not "Tested"; "Tested" (green suite) is not "Verified";
"Verified" is not "Accepted". **A completion claim with no execution evidence is UNVERIFIED, not
PASS** -- this is what the close-gate's test-evidence check guards (it requires an evidence file
whose fingerprint matches the tree; it is "evidence present", not "evidence good").

## Don't weaken the test to get green

The trial rule's standing instruction: never weaken, skip, or delete a test to get green. The
`test-weakening-guard` close-gate invariant enforces the deletion half of this: it reds when the
branch's net count of test functions across all test files DROPS below the merge-base, unless the
journal carries a `SKIP: test-weakening -- <reason>` waiver (in git, attributable by commit). It
counts test functions, not assert lines (counting lines reds on legitimate rewording -- the
`growth-declares-a-deletion` lesson). It catches a deleted test; it does not grade a test's quality
and does not catch an assertion gutted inside a surviving test -- that stays a human call, the
UNVERIFIED-vs-VERIFIED judgment this reference defines.

## Related

- `references/careful-paths.md` — the risk tier (M2) that decides how much Protect/Prove work a
  change owes.
- `scripts/behavior-lock.sh` / `scripts/behavior-baseline.sh` — the regression half (M1).
- `scripts/invariants/test-weakening-guard.sh` — the deletion guard (this phase).
- `scripts/invariants/growth-declares-a-deletion.sh` — the mirror invariant (a growth declares a
  deletion; the test-weakening guard makes a shrink declare a reason).
