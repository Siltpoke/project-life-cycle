# Agent-chats resume registry (multi-family)

Machine-local, per-repo index mapping this repo's CLI-agent conversations to
their resume ids — across families (Claude Code, Codex, and future ones like
Antigravity/Qoder) — so a topic can be turned back into `<cli> --resume <id>`.
Stored as JSONL (one record per line, no header) in
`docs/agent-chats-index.md` (gitignored — never committed).

## Record schema (every key always present)

`resume_id`, `family`, `model`, `intensity`, `repo`, `branch`, `worktree`,
`head_sha`, `dirty`, `topic` (≤80 chars), `tags` (list), `transcript_path`,
`capture_source` (`skill` | `hook`), `created_at`, `last_updated`,
`msg_count`. Unknown values are `""` / `false` / `0` / `[]` — never omitted.

**Not stored: cost / tokens.** Spend belongs in a dedicated analytics store —
anything tracking it can join on `resume_id`. Keeping cost out of this file
avoids a second ledger that drifts against the first.

## Family → resume command (derived at display time, not stored)

- `claude` → `claude --resume <resume_id>`
- `codex`  → check your installed codex-cli for its `resume` invocation; the
  exact syntax varies by version.
- `antigravity` / `qoder` / others → not yet mapped.

Derive the command from `family` at display time so it can never go stale.

## Trigger A — skill-moment (this skill)

When you write a handoff or update `RESUME.md`, also record this conversation.
Run from the **main thread** (not a subagent). You author the fields only you
know (`--family` / `--model` / `--intensity` / `--topic` / `--tags`); the
script fills repo/branch/worktree/head_sha/dirty/timestamps:

    python3 scripts/agent_chats.py upsert \
      --resume-id "$CLAUDE_CODE_SESSION_ID" \
      --family claude \
      --model "opus-4.8" \
      --intensity "high" \
      --topic "<one-line summary of this conversation>" \
      --tags "<comma,separated,keywords>"

It no-ops safely when both the resume id and transcript path are empty, so it
is always safe to call. Run it from the main thread (the skill's handoff step),
not from a dispatched subagent.

## Trigger B — SessionEnd hook (automatic, multi-family)

Auto-captures every substantive session's resume id — including the interrupted
ones you never ran a handoff on — deterministically, no LLM. Machine-local: the
hook config lives in your `~/.claude/settings.json` (or project
`.claude/settings.json`) and does NOT travel with the repo. Re-add it on each
machine.

Add to the `hooks` block of settings.json (adjust the absolute repo path):

    "hooks": {
      "SessionEnd": [
        {
          "hooks": [
            {
              "type": "command",
              "command": "python3 /ABSOLUTE/PATH/TO/REPO/scripts/agent_chats.py capture-hook"
            }
          ]
        }
      ]
    }

The harness passes `{ "session_id", "transcript_path", "cwd", ... }` on stdin.
An upstream hook may also stamp `agent_family: "<family>"` (e.g. `"codex"`) — the
command honors that as the family hint, else it sniffs the transcript shape. It
then skips trivial sessions (< 4 user+assistant messages), detects family,
extracts model + a deterministic topic (first user message, else
"untitled session"), counts turns into `msg_count`, and upserts
`docs/agent-chats-index.md`.

- SessionEnd is best-effort — a crash / `kill -9` / context-limit may skip it.
  Trigger A (skill-moment) still covers disciplined sessions.
- Tune the threshold with `--min-msgs N`.
- Codex sessions whose `session_id` is the literal `"codex"` are de-duplicated by
  `transcript_path`, so distinct rollouts stay distinct rows.
