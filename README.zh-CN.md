# project-lifecycle

**[English](README.md)** · 简体中文

**Project Life Cycle 把临时起意的 AI coding session 变成可重复、可追溯的软件开发工作流** —— 一个 [Claude Code](https://docs.claude.com/en/docs/claude-code) skill，在每个项目上跑同一套 spec → plan → build → verify → ship → release 纪律，由三个斜杠命令驱动：`/init-harness` → `/ship` → `/release`。

已验证可在 [Claude Code](#claude-code-安装)、[Codex](#codex-安装)、[Qoder](#qoder-安装)、[CodeBuddy](#codebuddy-安装) 中加载 —— 每个都用该 host 自己的插件校验器跑过，输出记录在 [HOST-VERIFICATION.md](HOST-VERIFICATION.md)。[Antigravity](#antigravity-安装) 附带了 manifest，但[**尚未验证**](HOST-VERIFICATION.md#unverified)（它的 `agy` 命令行能加载这个插件；一次不完整的端到端测试里，跑到的每一项都通过了，还有三项没跑 —— 见 [Antigravity 端到端测试](HOST-VERIFICATION.md#antigravity-end-to-end-run)）。这些检查覆盖的是「能被发现并加载」。之后又做了一次端到端测试，在四个 host 上各跑了一个小 phase；它发现的问题 —— 包括 skill 的 hook 在哪里**不会**运行 —— 记在同一个文件里。这些都没有在 Windows 上跑过。

**想了解更多？** [**指南（GUIDE）**](GUIDE.zh-CN.md) 讲清它做什么、什么时候用、完整工作流，以及逐文件的仓库地图。[CHANGELOG.md](CHANGELOG.md) 是发布记录。

## 安装

### Claude Code 安装

```bash
# 1. 把这个仓库注册为 Claude Code marketplace
claude plugin marketplace add Siltpoke/project-life-cycle

# 2. 安装 skill
claude plugin install project-lifecycle@project-life-cycle
```

重启 Claude Code。Skill 以 `project-lifecycle` 名注册；新项目启动 / 规划 milestone / 跑 per-phase 工作时自动触发。三个主命令 —— `/project-lifecycle:init-harness`（bootstrap 项目）、`/project-lifecycle:ship`（vertical-slice feature）、`/project-lifecycle:release`（切版）—— 驱动核心主线，外加 opt-in 的 `/project-lifecycle:builder-profile`（你实际怎么用 AI coding agent 的本机快照）。另有一组辅助命令补全工作流 —— `/catchup`、`/handoff`、`/reconcile`、`/review`、`/research`、`/capture`、`/recall`、`/cognition-distill`、`/plc-status`、`/experiment` —— 各自作用见 [Guide](GUIDE.md)。本 README 通篇用的裸形式（`/init-harness`、`/ship`……）也能用，前提是没有别的已安装命令占用同名。

升级：

```bash
claude plugin marketplace update project-life-cycle
claude plugin update project-lifecycle
```

卸载：`claude plugin uninstall project-lifecycle@project-life-cycle`。

### Codex 安装

这个仓库也带了 Codex plugin 元数据：

- `.codex-plugin/plugin.json` 让这个 checkout 可被 Codex 识别为 plugin。
- `skills/project-lifecycle/agents/openai.yaml` 提供 Codex skill UI 元数据和默认 prompt。

Codex 通过已配置的 marketplace 安装 plugin。本机使用时，把这个 checkout 放到或 symlink 到 `~/plugins/project-lifecycle`，然后在 `~/.agents/plugins/marketplace.json` 里加入这个 entry：

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

然后安装：

```bash
codex plugin add project-lifecycle@<your-marketplace-name>
```

安装后开启新的 Codex thread，让 `project-lifecycle` skill metadata 被重新加载。Claude Code hooks 和斜杠命令仍然是 Claude 专用；Codex 会通过 Codex plugin manifest 消费 skill 指令和 bundled references。

本地改完后更新 Codex：

```bash
python3 ~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py ~/plugins/project-lifecycle
python3 ~/.codex/skills/.system/plugin-creator/scripts/update_plugin_cachebuster.py ~/plugins/project-lifecycle
codex plugin add project-lifecycle@<your-marketplace-name>
```

然后开启新的 Codex thread。cachebuster 这一步会给 `.codex-plugin/plugin.json` 的版本号打上新的本地构建后缀（形如 `X.Y.Z+codex.YYYYMMDDHHMMSS`），用来强制 Codex 刷新已安装的 plugin cache。改了 `SKILL.md`、bundled references、Codex UI metadata 或 `.codex-plugin/plugin.json` 后，都走这套 update 流程。

### Qoder 安装

这个仓库也带了 Qoder plugin 元数据：`.qoder-plugin/plugin.json`（plugin 清单）和 `.qoder-plugin/marketplace.json`（`qodercli plugins marketplace add` 需要）。`skills/` 目录布局和 `SKILL.md` frontmatter 符合 Qoder 的 plugin 约定，frontmatter hook 路径用 `${QODER_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}`，所以 skill 在 Qoder 和 Claude Code 里都能加载。**skill 的 frontmatter hook 在 Qoder 里不运行。**Qoder 的 hook 文档只讲了设置文件里的 hook 和插件的 `hooks/hooks.json`，没有讲 skill frontmatter 里的 hook；端到端测试中「先写任务清单」守卫也一次都没拦过写文件（[HOST-VERIFICATION.md](HOST-VERIFICATION.md#skill-hooks-on-codebuddy-and-qoder)）。skill 的 hook 只在 Claude Code 里生效。pre-push 收尾闸门是 git hook，不是 skill hook，不受影响。

从本地 checkout 安装：

```bash
qodercli plugins install /path/to/project-life-cycle
```

或把仓库注册为 marketplace 再按名安装：

```bash
qodercli plugins marketplace add Siltpoke/project-life-cycle
qodercli plugins install project-lifecycle
```

重启 CLI 或在 TUI 里跑 `/plugins reload` 加载 skill。

升级：

```bash
qodercli plugins marketplace update project-life-cycle
qodercli plugins update project-lifecycle
```

卸载：`qodercli plugins uninstall project-lifecycle`。

### Antigravity 安装

这个仓库也带了原生 Antigravity (`agy`) plugin 元数据：

- `plugin.json` 让这个 checkout 可被 Antigravity 识别为原生 plugin。
- `skills/` 包含自定义的 skills。

**Antigravity 上的限制**（用 `agy` 1.4.8 实测；你的版本可以用 `agy plugin validate /path/to/project-life-cycle` 自己查）：

- **主 skill 文件只读进前 24,000 字节。** 文件约 116,000 字节，后面大约五分之四读不到。「完成标准」（Definition of Done）和闸门规则位于这前 24,000 字节之内（有测试检查它们的字节位置；agent 读到后是否照做，还没有测试过）；每个 phase 的流程以及之后的章节在截断线之后。
- **命令在安装时被转成 skill。** Antigravity 没有斜杠命令；按名字要那个 skill 即可（例如「用 project-lifecycle 插件的 `init-harness` skill」）。
- **skill 的 hook 不运行。** Antigravity 没有 frontmatter hook。pre-push 闸门是 git hook，不受影响。

要在 Antigravity CLI 中本地安装：

```bash
# 从本地路径安装插件
agy plugin install /path/to/project-life-cycle
```

确认安装：

```bash
agy plugin list
```

本地改动后更新 Antigravity 插件：

```bash
# 强制重新安装
agy plugin install /path/to/project-life-cycle
```

### CodeBuddy 安装

这个仓库带了 CodeBuddy plugin 元数据：`.codebuddy-plugin/plugin.json`（plugin 清单）和 `.codebuddy-plugin/marketplace.json`（`/plugin marketplace add` 需要）。**skill 的 frontmatter hook 在 CodeBuddy 里不运行。**CodeBuddy 只在子代理或 fork 出去的 skill 里注册 skill 的 frontmatter hook；这个 skill 在主会话里运行，所以 hook 从来不会被注册。它的 `allowUntrustedFrontmatterHooks` 设置改变不了这一点：打开这个设置后，「先写任务清单」守卫仍然没有拦下写文件（[HOST-VERIFICATION.md](HOST-VERIFICATION.md#skill-hooks-on-codebuddy-and-qoder)）。skill 的 hook 只在 Claude Code 里生效。pre-push 收尾闸门是 git hook，不是 skill hook，不受影响。

从本地 checkout 加载：

```bash
codebuddy --plugin-dir /path/to/project-life-cycle
```

或把仓库注册为 marketplace 再按名安装 —— 在 CodeBuddy TUI 里作为斜杠命令运行：

```
/plugin marketplace add Siltpoke/project-life-cycle
/plugin install project-lifecycle@project-life-cycle
```

跑 `/reload-plugins`（或重启）加载 skill。已安装 plugin 在 `/plugin` 的 **Installed** 标签页管理。

升级（在 TUI 里）：

```
/plugin marketplace update project-life-cycle
```

卸载：`/plugin marketplace remove project-life-cycle`。

## 贡献

这个 skill 通过真实项目使用进化。真实 phase 的发现比臆测规则更值钱。**完整指南**：[`CONTRIBUTING.md`](CONTRIBUTING.md) —— commit、PR body、PR label、CHANGELOG 纪律、发版流程。

## 许可

PolyForm Perimeter 1.0.1 —— 见 [LICENSE](LICENSE)。
