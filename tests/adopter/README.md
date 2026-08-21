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

This fixture exercises the close gate's adopter path. **It does not exercise `/init-harness`** —
that command needs an agent and four human checkpoints, so the tree it would produce is
fabricated here instead.
