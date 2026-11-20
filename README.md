# Project Life Cycle

**English** · [简体中文](README.zh-CN.md)

**Project Life Cycle turns ad-hoc AI coding sessions into a repeatable, traceable software workflow** — one [Claude Code](https://docs.claude.com/en/docs/claude-code) skill that runs the same spec → plan → build → verify → ship → release discipline on every project, driven by three slash commands: `/init-harness` → `/ship` → `/release`.

Verified to load in [Claude Code](#claude-code-setup), [Codex](#codex-setup), [Qoder](#qoder-setup) and [CodeBuddy](#codebuddy-setup) — each checked with that host's own plugin validator, with the output recorded in [HOST-VERIFICATION.md](HOST-VERIFICATION.md). [Antigravity](#antigravity-setup) ships a manifest and is [**not yet verified**](HOST-VERIFICATION.md#unverified) (its `agy` CLI loads the plugin, and a partial end-to-end run passed every row it reached; three rows are still unrun — see [Antigravity end-to-end run](HOST-VERIFICATION.md#antigravity-end-to-end-run)). Those checks cover discovery and loading. A later end-to-end run drove a small phase through each of the four hosts; what it found — including where the skill's hooks do **not** run — is in the same file. None of it ran on Windows.

**Want the details?** The [**Guide**](GUIDE.md) covers what it does, when to use it, the full workflow, and a file-by-file repo map. [CHANGELOG.md](CHANGELOG.md) is what shipped.

## Setup

### Claude Code setup

```bash
# 1. Register this repo as a Claude Code marketplace
claude plugin marketplace add Siltpoke/project-life-cycle

# 2. Install the skill
claude plugin install project-lifecycle@project-life-cycle
```

Restart Claude Code. Skill becomes available as `project-lifecycle`; auto-triggers when you start a new project, plan a milestone, or run per-phase work. The three headline commands — `/project-lifecycle:init-harness` (bootstrap a project), `/project-lifecycle:ship` (vertical-slice feature), `/project-lifecycle:release` (cut a release) — drive the core arc, alongside the opt-in `/project-lifecycle:builder-profile` (a local snapshot of how you actually use an AI coding agent). A set of auxiliary commands rounds out the workflow — `/catchup`, `/handoff`, `/reconcile`, `/review`, `/research`, `/capture`, `/recall`, `/cognition-distill`, `/plc-status`, `/experiment` — see the [Guide](GUIDE.md) for what each does. The bare forms (`/init-harness`, `/ship`, …) used throughout this README also work, as long as no other installed command claims the same name.

Update later:

```bash
claude plugin marketplace update project-life-cycle
claude plugin update project-lifecycle
```

Uninstall: `claude plugin uninstall project-lifecycle@project-life-cycle`.

### Codex setup

This repo also ships Codex plugin metadata:

- `.codex-plugin/plugin.json` makes the checkout a Codex plugin.
- `skills/project-lifecycle/agents/openai.yaml` provides Codex skill UI metadata and the default prompt.

Codex installs plugins from configured marketplaces. For local use, place or symlink this checkout at `~/plugins/project-lifecycle`, then add this entry to `~/.agents/plugins/marketplace.json`:

```json
{
  "name": "project-lifecycle",
  "source": {
    "source": "local",
    "path": "./plugins/project-lifecycle"
  },
  "policy": {
    "installation": "AVAILABLE",
    "authentication": "ON_INSTALL"
  },
  "category": "Productivity"
}
```

Then install it:

```bash
codex plugin add project-lifecycle@<your-marketplace-name>
```

Start a new Codex thread after installing so the `project-lifecycle` skill metadata is loaded. Claude Code hooks and slash commands remain Claude-specific; Codex consumes the skill instructions and bundled references through the Codex plugin manifest.

Update Codex after local edits:

```bash
python3 ~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py ~/plugins/project-lifecycle
python3 ~/.codex/skills/.system/plugin-creator/scripts/update_plugin_cachebuster.py ~/plugins/project-lifecycle
codex plugin add project-lifecycle@<your-marketplace-name>
```

Then start a new Codex thread. The cachebuster step stamps the version in `.codex-plugin/plugin.json` with a fresh local build suffix (`X.Y.Z+codex.YYYYMMDDHHMMSS`), which forces Codex to refresh its installed plugin cache. Use this update flow after changing `SKILL.md`, bundled references, Codex UI metadata, or `.codex-plugin/plugin.json`.

### Qoder setup

This repo also ships Qoder plugin metadata in `.qoder-plugin/plugin.json` (the plugin manifest) and `.qoder-plugin/marketplace.json` (required for `qodercli plugins marketplace add`). The `skills/` directory layout and `SKILL.md` frontmatter match Qoder's plugin conventions, and the frontmatter hook paths use `${QODER_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}`, so the skill loads in both Qoder and Claude Code. **The skill's frontmatter hooks do not run in Qoder.** Qoder's hook documentation describes hooks in settings files and in a plugin's `hooks/hooks.json`, not in a skill's frontmatter, and in an end-to-end run the task-list guard never intercepted a write ([HOST-VERIFICATION.md](HOST-VERIFICATION.md#skill-hooks-on-codebuddy-and-qoder)). The skill's hooks are Claude Code-only. The pre-push close gate is a git hook, not a skill hook, and is unaffected.

Install from a local checkout:

```bash
qodercli plugins install /path/to/project-life-cycle
```

Or register the repo as a marketplace and install by name:

```bash
qodercli plugins marketplace add Siltpoke/project-life-cycle
qodercli plugins install project-lifecycle
```

Restart the CLI or run `/plugins reload` in the TUI to load the skill.

Update later:

```bash
qodercli plugins marketplace update project-life-cycle
qodercli plugins update project-lifecycle
```

Uninstall: `qodercli plugins uninstall project-lifecycle`.

### Antigravity setup

This repo also ships a native Antigravity (`agy`) plugin manifest:

- `plugin.json` makes the checkout a native Antigravity plugin.
- `skills/` contains the custom skills.

**Limits on Antigravity** (measured with `agy` 1.4.8; check your own version with `agy plugin validate /path/to/project-life-cycle`):

- **Only the first 24,000 bytes of the main skill file are loaded.** The file is about 116,000 bytes, so roughly the last four fifths are not read. The Definition of Done and the close-gate rules sit within those first 24,000 bytes (a test checks their byte position; whether the agent then follows them has not been tested); the per-phase workflow and the sections after it are beyond the cut.
- **Commands become skills on install.** Antigravity has no slash commands; ask for the skill by name (for example, "use the project-lifecycle plugin's `init-harness` skill").
- **The skill's hooks do not run.** Antigravity has no frontmatter hooks. The pre-push close gate is a git hook, so it is unaffected.

To install it locally in the Antigravity CLI:

```bash
# Install the plugin from the local checkout path
agy plugin install /path/to/project-life-cycle
```

To verify the installation:

```bash
agy plugin list
```

Update the plugin after local edits:

```bash
# Force re-install from the local path
agy plugin install /path/to/project-life-cycle
```

### CodeBuddy setup

This repo ships CodeBuddy plugin metadata in `.codebuddy-plugin/plugin.json` (the plugin manifest) and `.codebuddy-plugin/marketplace.json` (required for `/plugin marketplace add`). **The skill's frontmatter hooks do not run in CodeBuddy.** CodeBuddy registers a skill's frontmatter hooks only inside a subagent or a forked skill; this skill runs in the main session, so they are never registered. Its `allowUntrustedFrontmatterHooks` setting does not change that: with the setting on, the task-list guard still did not intercept a write ([HOST-VERIFICATION.md](HOST-VERIFICATION.md#skill-hooks-on-codebuddy-and-qoder)). The skill's hooks are Claude Code-only. The pre-push close gate is a git hook, not a skill hook, and is unaffected.

Load from a local checkout:

```bash
codebuddy --plugin-dir /path/to/project-life-cycle
```

Or register the repo as a marketplace and install by name — run these as slash commands inside the CodeBuddy TUI:

```
/plugin marketplace add Siltpoke/project-life-cycle
/plugin install project-lifecycle@project-life-cycle
```

Run `/reload-plugins` (or restart) to load the skill. Manage installed plugins from the `/plugin` **Installed** tab.

Update later (in the TUI):

```
/plugin marketplace update project-life-cycle
```

Uninstall: `/plugin marketplace remove project-life-cycle`.

## Contributing

This skill evolves through real project use. Findings from real phases beat speculative rules. **Full guide**: [`CONTRIBUTING.md`](CONTRIBUTING.md) — commits, PR body, PR labels, CHANGELOG discipline, release flow.

## License

PolyForm Perimeter 1.0.1 — see [LICENSE](LICENSE).
