---
description: Read your own local Claude Code transcripts and produce a markdown snapshot of how you actually use an AI coding agent. 100% local — nothing leaves the machine. Gated pipeline (deterministic stats → evidence gate → cold-read → adversarial verify → independent verification). Default descriptive (mirror, not score card); 1-10 scores behind --scores. Written to ~/.claude/builder-profile.md.
---

# /builder-profile — A Snapshot of How You Build

Reads your local Claude Code session transcripts and writes one markdown report (`~/.claude/builder-profile.md`): a point-in-time snapshot of how you actually work with an AI coding agent.

Two readers, one file: **you** — see your own patterns, learn how you might use the agent better; **any agent** (Claude Code, a companion agent, …) — read the same file on demand for richer context about who they're working with. Usage drifts, so each run is a fresh snapshot.

## When to use

- Before your first real milestone with this skill — let it calibrate to your style.
- Any time you want a mirror of your own AI-coding work patterns, traceable to real sessions.
- Periodically — the you-vs-you trajectory only gets interesting over time.

## When NOT to use

- As a report card to show someone else. There is no ranking, no leaderboard, no comparison to other people. It only compares you to your earlier self.
- Expecting a punch list of fixes. Gaps surface as curiosity questions the skill explores *during* work — not a deficit count.

## What it does

1. **PASS 1 — deterministic** (Python over `~/.claude/projects/**/*.jsonl`) → emits `stats.json`. No guessing; every number re-computable from the logs.
2. **PASS 1.5 — evidence gate** → a dimension with `< 3` evidence instances is marked `insufficient signal`, never narrated.
3. **PASS 2 — cold read** → the agent reads `stats.json` + a stratified raw-excerpt sample, **self-blinded** (treats the transcripts as a stranger's logs, so it can't flatter you).
4. **PASS 3 — adversarial verify** → each conclusion is re-read with intent to refute it; only survivors ship.
5. **PASS 4 — independent verification** → the generator doesn't grade itself: `scripts/builder_profile_verify.py` runs hard framing assertions (exit 1 blocks delivery), then a fresh-context cold critic — fed only the rules + the finished report — checks the framing failures a script can't. Any fail → rework, not deliver.

## Output

**One markdown report**, written to `~/.claude/builder-profile.md` (and printed). A point-in-time snapshot — re-running overwrites it with a fresh one. Contents: 2-3 operating modes you switch between + per-dimension descriptive observation with evidence + signature moves + you-vs-you trajectory + a few co-discovery questions. Header carries the snapshot date + window; opens with the local-only statement.

That one file is the whole product. You read it to understand your own patterns; any agent (Claude Code, a companion agent, …) can be pointed at the same path to read it on demand. No separate memory file, no skill step wired to consume it.

**It also explains itself.** Once the report passes verification, the command doesn't just hand you a path — it walks you through it in plain language in the conversation: the one disposition that runs through everything, the modes and the honest dimensions (including what *couldn't* be measured and why), and the co-discovery questions asked as real curiosities. Same framing throughout — descriptive, no scores, no scoreboard, you-vs-you. The goal is that you actually get yourself, not that a file got saved.

## Flags

- `--scores` — also render the five dimensions (steering / execution / engineering / product instinct / planning) as 1-10. Off by default; the default output is descriptive, not a grade.

## Privacy

The agent reading your transcripts already runs locally. There is no remote step, no upload, no payload sent anywhere. The report says so at the top, and the pipeline forbids any network call.

## Mechanism

Full pipeline prompt, JSONL parser schema, framing-safety rules (incl. the synthesis spine + provenance + PASS-4 verification), and report shape: `skills/project-lifecycle/references/builder-profile.md`.

