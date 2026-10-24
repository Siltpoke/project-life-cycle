# Host verification record

`README.md` says which hosts this plugin works in.
This file is what the sentence is allowed to rest on, and it ships beside the README so the link to it
resolves wherever the README is read.

**One rule:** a host may be named in the README as working only if it has a row here with a probe,
a verbatim result and a date. Everything else is named as unverified, with the reason.

## What "verified" means here, and what it does not

**Verified (shallow):** the host discovers this plugin, accepts its manifest, and loads its
components — checked with **the host's own validator**, not with an assertion made by this
repository about itself.

**NOT verified by the rows below:** that a full phase runs inside that host. The rows exercise no
cadence, gate, hook or slash command. **Do not read a row below as "a phase was run there."** A
separate end-to-end run did drive a phase through four hosts; it is recorded in its own section,
[End-to-end run](#end-to-end-run), and it changes no row.

**Also not verified: Windows.** Every probe ran on macOS. The changes released after 4.1.1 remove assumptions that
are false on Windows (a repo-relative path, an executable bit); removing a false assumption is not
the same as verifying the host, and no row here claims a Windows run.

## Rows

| host | probe | result | date | version seen |
|---|---|---|---|---|
| Claude Code | `claude plugin list` · `claude plugin details project-lifecycle@project-life-cycle` | installed + enabled; component inventory loaded, 15 skills | 2026-10-18 | 3.7.0 |
| Qoder | `qoder plugins validate <checkout>` | rc=0 — `Plugin "project-lifecycle" is valid and ready to install`, `skills (2)`, `commands (14)` | 2026-10-18 | 0.12.0 installed, enabled |
| CodeBuddy | `codebuddy plugin validate <checkout>` | rc=0 — `✔ Validation passed`, `"type": "marketplace", "valid": true` | 2026-10-18 | 3.7.0 installed, enabled |
| Codex | Codex's plugin validator (`validate_plugin.py <checkout>`) | rc=0 — `Plugin validation passed` | 2026-10-18 | a local marketplace configured; `codex plugin list` reports **`not installed`** |
| Antigravity | — | **unverified**: no command-line entry point was found. Verifying it needs someone to open the IDE. | 2026-10-18 | — |

## Unverified

A host listed here is shipped with a manifest but has **no row above that verifies it**. The README
links its "not yet verified" wording to this section, in every language, and a test holds it to that.

- **Antigravity** — the row above says there was no command-line entry point; that is no longer
  true (`agy` exists and loads the plugin, see [End-to-end run](#end-to-end-run)), but running a
  session through it needs an interactive browser login, so it is still unverified.
- **Windows** (not a host, a platform) — see "Also not verified" above.

## Two things the probes turned up

Neither changes a row above, and both are open.

1. **Codex can carry two entries for this plugin.** The entry the README's Codex
   section produces (a local marketplace entry) reports
   `not installed`, while an entry from another marketplace can be `installed, enabled` and point
   at an older build. So a Codex user may be loading an old build while the line next to it says
   nothing is loaded. **Its version string will not tell you this:** the Codex manifest is versioned
   independently by design (`0.11.0+codex.…`) and does not move with releases, so compare the
   installed content, not the version.
2. **The probed builds were not the current version.** The version column is what each host had
   installed at the time, and Codex's version string never changes (see above).
   Each row proves that *a* build loads in that host, not that this tree does.

## End-to-end run

2026-10-23, release `5.0.0`, macOS. Each host got its own throwaway Python repo with a local bare
`origin`, the plugin loaded from the release tree into an isolated config directory, and an
unattended prompt. Each outcome below was read from repo state and exit codes, never from the
agent's own account of itself. Hosts ran in their non-interactive mode (Claude Code `-p`, CodeBuddy `-p -y`,
Qoder `-p` with `bypass_permissions`, `codex exec`); interactive sessions were not tested.

| host | loads `5.0.0` | `/catchup` read-only | `/init-harness` + active pre-push | small phase, gate re-run by the checker | incomplete branch push refused | skill hooks (task-list guard) | `/handoff` then `/catchup` |
|---|---|---|---|---|---|---|---|
| Claude Code | yes | yes | files written; hook not activated — the test's own sandbox forbids writing `.git/config`, and the agent said so instead of working around it | see note 1 | not testable (hook inactive) | **runs**: a separate probe was blocked once, as designed | yes |
| CodeBuddy | yes | yes | yes (`.git/hooks`) | yes | yes | **did not run**: skill loaded, a write was not intercepted, the guard left no state | yes |
| Qoder | yes | yes | **no**: gate script and pre-push hook missing, while the run reported the bootstrap as complete | passed, but the gate it used was not the one generated for the repo — see note 2 | not testable (no hook) | **did not run**: same as CodeBuddy | yes |
| Codex | yes (its own independent version string) | yes | yes (`.githooks` + `core.hooksPath`) | passed after the agent edited the generated gate — see note 1 | yes | not claimed for Codex | yes |
| Antigravity | yes (via `agy`) | not run: needs an interactive login | not run | not run | not run | not claimed | not run |

1. **The generated gate failed a correctly finished task.** Its product-change check read only the
   last commit, while the next check requires a separate journal commit, which the cadence writes
   after the code. A file named directly as the product tree (`calc.py`) also never matched. Both
   were fixed after this run; the agent on Codex had already patched its own copy to get past it.
2. Qoder copied this repository's own gate instead of the generated one, so its product-change check
   fell back to this repository's directory names and was satisfied by the gate script itself.

Also seen on Antigravity at load time: commands are converted to skills on install, and only the
first 24,000 bytes of the main skill file are read, which is about a fifth of it.

## The marker the README must carry

`scripts/test_host_portability.py` reads this line rather than hard-coding it. It is a link
target, not a phrase, so the same marker serves the English and the Chinese README and this file
needs no translated wording of its own:

```
readme-marker-unverified = HOST-VERIFICATION.md#unverified
```

## How to add a row

Run that host's own validator against a checkout, paste the **verbatim** result, date it, and say
what the probe does not cover. A row written from the setup instructions rather than from a run is
exactly the defect this file exists to end.
