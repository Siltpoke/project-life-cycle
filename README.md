# Project Life Cycle

**English** · [简体中文](README.zh-CN.md)

**Project Life Cycle turns ad-hoc AI coding sessions into a repeatable, traceable software workflow** — one [Claude Code](https://docs.claude.com/en/docs/claude-code) skill that runs the same spec → plan → build → verify → ship → release discipline on every project, driven by three slash commands: `/init-harness` → `/ship` → `/release`.

Works in [Claude Code](#claude-code-setup), [Codex](#codex-setup), [Qoder](#qoder-setup), [Antigravity](#antigravity-setup), and [CodeBuddy](#codebuddy-setup).

**Want the details?** The [**Guide**](GUIDE.md) covers what it does, when to use it, the full workflow, and a file-by-file repo map. [CHANGELOG.md](CHANGELOG.md) is what shipped.

## Setup

### Claude Code setup

```bash
# 1. Register this repo as a Claude Code marketplace
claude plugin marketplace add Victoriakaey/project-life-cycle

# 2. Install the skill
claude plugin install project-lifecycle@project-life-cycle
```

Restart Claude Code. Skill becomes available as `project-lifecycle`; auto-triggers when you start a new project, plan a milestone, or run per-phase work. The three headline commands — `/project-lifecycle:init-harness` (bootstrap a project), `/project-lifecycle:ship` (vertical-slice feature), `/project-lifecycle:release` (cut a release) — drive the core arc, alongside the opt-in `/project-lifecycle:builder-profile` (a local snapshot of how you actually use an AI coding agent). A set of auxiliary commands rounds out the workflow — `/catchup`, `/handoff`, `/reconcile`, `/review`, `/research`, `/capture`, `/recall`, `/cognition-distill`, `/tasklist` — see the [Guide](GUIDE.md) for what each does. The bare forms (`/init-harness`, `/ship`, …) used throughout this README also work, as long as no other installed command claims the same name.

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

Then start a new Codex thread. The cachebuster step updates `.codex-plugin/plugin.json` from `0.11.0` to a local build version such as `0.11.0+codex.YYYYMMDDHHMMSS`, which forces Codex to refresh its installed plugin cache. Use this update flow after changing `SKILL.md`, bundled references, Codex UI metadata, or `.codex-plugin/plugin.json`.

### Qoder setup

This repo also ships Qoder plugin metadata in `.qoder-plugin/plugin.json` (the plugin manifest) and `.qoder-plugin/marketplace.json` (required for `qodercli plugins marketplace add`). The `skills/` directory layout and `SKILL.md` frontmatter match Qoder's plugin conventions, and the frontmatter hook paths use `${QODER_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}` so the same skill works in both Qoder and Claude Code.

Install from a local checkout:

```bash
qodercli plugins install /path/to/project-life-cycle
```

Or register the repo as a marketplace and install by name:

```bash
qodercli plugins marketplace add Victoriakaey/project-life-cycle
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

This repo ships CodeBuddy plugin metadata in `.codebuddy-plugin/plugin.json` (the plugin manifest) and `.codebuddy-plugin/marketplace.json` (required for `/plugin marketplace add`). CodeBuddy natively supports `${CLAUDE_PLUGIN_ROOT}` as a Claude Code compatibility alias, so the same `SKILL.md` frontmatter hooks run unchanged.

Load from a local checkout:

```bash
codebuddy --plugin-dir /path/to/project-life-cycle
```

Or register the repo as a marketplace and install by name — run these as slash commands inside the CodeBuddy TUI:

```
/plugin marketplace add Victoriakaey/project-life-cycle
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
