# Claude Code Ergonomics — Per-Session + Per-Project Habits

Per-session keyboard shortcuts, prompt-entry tricks, and multimodal patterns that compound over time. Sourced from Boris Cherny's "Practical Tips for Claude Code" + Anthropic internal usage. These aren't part of any agentic workflow per se — they're the **muscle memory** that makes the workflow feel fast.

Read this once. Internalize the 5 things below. The rest is reference.

## The 5 things to internalize

| Habit | Why it matters | Cost to learn |
|---|---|---|
| **`#` prefix → auto-append to CLAUDE.md** | Every time AI uses wrong tool / wrong convention / wrong pattern, ask yourself "would a one-line rule in CLAUDE.md have prevented this?" If yes, type `#` + the rule. CLAUDE.md grows into a record of every surprising assumption — sessions get noticeably better in a couple weeks. | 1 minute |
| **`!` prefix → bash mode w/ output in context** | Run a command locally; result lands in conversation context. AI sees both the command and its output on the next turn. For long-running checks, recon commands, "let me confirm the dev server is up" moments. | 30 seconds |
| **`shift-tab` → auto-accept edits mode** | Stops the constant approval prompts. Bash commands still need approval (safety); file edits auto-apply. Toggle when AI is on the right track. Always reversible — ask AI to undo if it goes wrong. | 30 seconds |
| **`escape` → safely interrupt** | Any time, any state. Won't corrupt the session. Use it the moment you see the wrong direction — don't let the AI burn budget on the wrong path. `escape escape` jumps back in history. | 10 seconds |
| **Drag-drop image → multimodal** | Drag a mockup / screenshot / error image into the prompt. AI consumes it as context. Pair with a verify loop (Track B Playwright screenshot loop per `verify-loop.md`) for "build this UI" tasks that iterate to pixel-perfect. | 30 seconds |

If you only adopt 2: `#` + `shift-tab`. Those alone change the daily texture of working with Claude Code.

## Full reference

### Prompt-entry primitives

| Input | Effect |
|---|---|
| `<text>` | Standard prompt. |
| `# <text>` | Append to CLAUDE.md. Picker asks which memory file (project / user / enterprise / nested). Use for "AI keeps doing X — make it stop." |
| `! <command>` | Drop to bash. Runs locally. Command + output enter context window. AI sees both next turn. |
| `@<file>` or `@<dir>` | At-mention pulls the file/dir into context. AI reads on next turn. Lower-overhead than asking AI to read. |
| Drag-drop image | Image becomes a multimodal input. Works for mockups, error screenshots, photos of whiteboards. |
| Copy + paste image | Same as drag-drop. |
| Paste file path | AI reads the file. |
| `shift-enter` | Newline without submit (after `claude /terminal-setup` once per machine). |

### Keyboard shortcuts (in-session)

| Key | Action |
|---|---|
| `shift-tab` | Toggle auto-accept-edits mode. File edits auto-apply; bash still prompts. |
| `escape` | Safe interrupt. Stop whatever AI is doing. Tell it what to do differently. |
| `escape escape` | Jump back in history (rewind the conversation). |
| `ctrl-R` | Show full output — what AI sees in its context window, including hidden tool results. |
| `tab` | Cycle through file/symbol completions when typing `@`. |
| `up arrow` | Recall previous prompts. |

### Session continuity

| Command | Effect |
|---|---|
| `claude --resume` | Pick a past session to continue. |
| `claude --continue` | Continue the most recent session. |
| `/clear` | Drop the conversation context (run `/handoff` first — it writes the RESUME snapshot the next session reads). |
| `/compact` | Compress context manually before auto-compact fires. |

### Setup commands (run once per machine)

| Command | Effect |
|---|---|
| `claude /terminal-setup` | Enables `shift-enter` for newlines (otherwise need backslash). |
| `/theme` | Light / dark / daltonize themes. |
| `/install-github-app` | Installs the Anthropic GitHub app. Lets `@claude` mention work on any GitHub issue / PR. |
| `claude /allowedTools` | Customize the allow-list so AI doesn't prompt for routine bash commands every time. |

### Multimodal in the terminal

Claude Code has been multimodal from launch. The terminal hides this — there's no upload button. But:

- Drag-drop an image file onto the terminal window.
- Copy an image to clipboard, paste with cmd-V.
- Pass a file path to an image and ask the AI to "look at this image."
- Combine with Playwright/Puppeteer to generate screenshots in a verify loop, then drag the saved screenshot back in.

Useful for: "build this UI from the mock I just dropped in", "this is the error screen — debug it", "compare these two screenshots before/after my change."

### Dictation (macOS-specific)

System Settings → Accessibility → Dictation → enable + assign a keyboard shortcut (default: double-tap `fn`).

Then double-tap fn, talk to Claude Code like another engineer, hit enter. Faster than typing for long-form prompts. Useful for setting context: "I'm trying to build X, the constraints are Y and Z, the existing code does W, what's the right approach?" — much faster to say than to type.

Linux / Windows: equivalent native dictation or third-party (Whisper-based) tools.

### `claude -p` / SDK mode

`claude -p "<prompt>" --allowed-tools <tools> --output-format json` runs Claude headless and emits JSON. Treat it like a Unix utility:

```bash
# pipe a log into it
gcloud logging read ... | claude -p "summarize unusual events" --output-format json | jq

# use in CI
claude -p "review this diff" --output-format json > review.json
```

Use for: CI integration, incident response, batch processing, log triage, autonomous loops.

Full SDK reference: <https://docs.claude.com/en/docs/agents-and-tools/sdk-overview>

### Multi-Claude parallelism

Power users run multiple Claude sessions against the same project:

- Several `tmux` panes, each with its own session, working on different files.
- Several checkouts of the same repo (one per session), or git worktrees for isolation.
- Several SSH sessions from a laptop into a beefier dev box.

Skill-level convention: when running parallel builders (`backend-builder` + `frontend-builder` per `references/builder-split.md`), they must operate on disjoint folder paths (the folder-map enforces this). Parallelism against shared files = merge conflicts; parallelism across folder-scoped builders = safe.

See `references/cost-aware-behaviors.md` for budget-aware parallelism rules.

## What NOT to do

- **Don't use `--dangerously-skip-permissions`.** Configure `/allowedTools` instead. The skip flag is a footgun.
- **Don't memorize keybindings before you've used the basics.** `#`, `shift-tab`, `escape`. The rest is reference — look up when needed.
- **Don't paste secrets / API keys into the prompt** because "Claude needs them to test something." Put them in env vars; reference by name.
- **Don't run `! <command>` for destructive operations** without reading the output first. Bash mode is convenient — that's exactly why it's also dangerous.
- **Don't use dictation in a shared space** without privacy-checking what you're about to say. Microphone is on; transcript leaves your machine through whatever dictation backend you've enabled.

## Cross-reference

- `references/onboarding.md` — Day 1 introduces these in context.
- `references/cost-aware-behaviors.md` — `/clear` discipline + parallelism budget rules.
- `references/verify-loop.md` — multimodal + screenshot loop is the visual verify loop.
- `references/builder-split.md` — folder-map enables safe parallelism.
- `references/self-update-flow.md` — `#`-recorded rules promote to skill-level when they hold across ≥2 projects.
