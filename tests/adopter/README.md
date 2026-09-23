# Adopter fixture

`run.sh` builds a container from `debian:bookworm-slim` (git, jq, ca-certificates, bash — no
python3, no lychee, no node), initializes an EMPTY git repository inside it, drops a fabricated
`.claude/close-gate.json` at the exact hardcoded path `close-gate.sh` reads, points
`refs/remotes/origin/main` at the pre-phase commit (a fresh `git init` has no remote and the gate
exits 1 without one), then runs `scripts/close-gate.sh phase 1.0` the way an
adopter — someone with none of this repo's own directories, hooks, or prior config — would. This
exercises the two gate branches that are gated on an adopter *lacking* a config key
(`user_story_glob`, `closure_declaration`), and which are therefore unreachable from a
repository that declares those keys. The fabricated manifest deliberately omits `user_story_glob` and
`closure_declaration`; those omissions are the fixture. Output is captured to
`${TMPDIR:-/tmp}/plc-adopter-run.txt`, where `compare-reached.sh` and `compare-verdict.sh` assert on it.

**What this fixture actually runs, stated narrowly because the sentence it replaces was not.**
It used to open *"This fixture exercises the close gate's adopter path."* That claim is wider than
the mechanism in two ways, and both are now written down rather than left to be discovered:

- **It runs THIS REPOSITORY'S VARIANT of the gate, not the one adopters copy.** The container does
  `cp -r /src/scripts ./scripts`, so the script under test is `scripts/close-gate.sh` — 1400+ lines
  of this repo's own gate. The script an adopter actually copies is the fence embedded in
  `skills/project-lifecycle/references/close-gate.md`, and **nothing here runs it.** The two are
  independently maintained and have diverged before, including at the command line (the variant
  REQUIRES a phase argument; the canonical gate does not). Where the canonical gate's coverage
  lives is `scripts/test_gate_conformance.py`, which runs each gate ALONE against a requirement
  authored from acceptance prose rather than from either script.
- **The run is not purely adopter-facing.** `run.sh` also invokes
  two invariants that do not ship (`a-maintainer-only-invariant.sh` is the placeholder
  name this suite gives them). Those are maintainer-only checks about this
  repository's own publishing surface; an adopter has neither. They are in the capture because
  `tests/adopter/expected-branches.txt` asserts their rows, not because an adopter would run them.

What IS genuinely adopter-shaped: an empty repository with none of this repo's directories, hooks,
or prior config, running the gate over a fabricated minimal manifest — which is what makes the two
gate branches gated on an adopter *lacking* a key or directory reachable at all.

**It does not exercise `/init-harness`** — that command needs an agent and four human checkpoints,
so the tree it would produce is fabricated here instead. That half of the fixture's own goal is
left half-completed on purpose.

**The verdict this fixture expects is a PASS as of 2026-08-25.** It expected a FAIL for as long as
the narrowed-inputs finding was open — the fabricated manifest narrowed `test_evidence_inputs` and declared no
`validator_input_paths_rationale`. That is fixed, the fixture's manifest carries a filled rationale,
and `expected-verdict.txt` now declares `NO-FAIL-ROWS` explicitly rather than merely listing none.
