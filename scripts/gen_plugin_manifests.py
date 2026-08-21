"""Generate every host plugin manifest from one source file. No LLM, no network.

WHY THIS EXISTS. Each agent host hardcodes its own manifest path (`.claude-plugin/`,
`.codex-plugin/`, `.qoder-plugin/`, `.codebuddy-plugin/`, …), so the directories cannot be
collapsed — that is imposed by the hosts, not a design choice here. What CAN be collapsed is
the *maintenance*: 8 files, ~90% identical, kept in step by hand.

But the sharper problem is not that they were out of step. It is that **which hosts are SUPPOSED to
move together was not written anywhere a reader would look.** Before this generator, the manifests read:

    .claude-plugin/plugin.json      version 3.7.0                          <-- synced set
    .qoder-plugin/plugin.json       version 3.7.0                          <-- synced set
    .codebuddy-plugin/plugin.json   version 3.7.0                          <-- synced set
    .codex-plugin/plugin.json       version 0.11.0+codex.20260707001844    <-- independent BY DESIGN
    plugin.json (antigravity)       no version field at all                <-- its schema forbids one

    .qoder-plugin/marketplace.json  ==  .codebuddy-plugin/marketplace.json  (byte-identical)
    .claude-plugin/marketplace.json vs .qoder-plugin/marketplace.json       (differs by one $schema line)

Those three intents lived in three different places: the synced set inside a `for` loop in
scripts/invariants/manifest-version-sync.sh, codex's exemption in a COMMENT in that same script, and
antigravity's in a comment in scripts/validate.py. Nothing showed all three at once, and none of them
is visible from the manifests themselves.

That gap is easy to fall into: a generator that reads validate.py but never the invariants sees
codex's `0.11.0+...` sitting beside three `3.7.0`s
and "fixes" it -- flattening a deliberate versioning scheme onto the shared version. It is not a bug.
`hostVersionOverrides` in the source now states that intent as data, beside everything else, and
test_regenerating_never_drags_an_overridden_host_onto_the_shared_version fails if it is ever
collapsed again.

So: one source file carrying the shared values AND the per-host exemptions, one generator, and a
`--check` mode the validator calls. Adding a host is one entry in TARGETS below.

Usage:
    python3 scripts/gen_plugin_manifests.py            # write manifests
    python3 scripts/gen_plugin_manifests.py --check    # verify on-disk == generated (CI gate)
"""
from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path

# The source lives UNDER .claude-plugin/ despite serving all five hosts. It is NOT Claude-specific.
SOURCE_FILE = ".claude-plugin/plugin.source.json"
CC_MARKETPLACE_SCHEMA = "https://anthropic.com/claude-code/marketplace.schema.json"

# One entry per host. Adding a host = adding one dict here.
#
# `plugin_keys` / `marketplace_keys` carry BOTH the field set and the field ORDER, because the
# generated files are committed and reviewed as diffs — a reordered key reads as a change.
# Syntax: "field" takes source["field"]; "out:src" writes key `out` from source path `src`.
#
# Paths are explicit rather than derived from a directory, because Antigravity's manifest lives
# at the repo ROOT (`plugin.json`), not under a `.<host>-plugin/` dir.
TARGETS: list[dict] = [
    {
        # Claude Code. Ships the richest description (shown in the plugin list) and is the only
        # host whose marketplace file carries a $schema. Note the key order differs from the
        # others (description before version) — preserved verbatim, not normalized.
        "name": "claude",
        "plugin_path": ".claude-plugin/plugin.json",
        "plugin_keys": ["name", "description:descriptions.detailed", "version", "author"],
        "marketplace_path": ".claude-plugin/marketplace.json",
        "marketplace_keys": ["$schema", "name:marketplaceName", "description:descriptions.marketplace", "owner:author", "plugins"],
        "schema": CC_MARKETPLACE_SCHEMA,
    },
    {
        # Codex. No marketplace file; instead it wants `skills` + a rich `interface` block for
        # its own UI surface.
        "name": "codex",
        "plugin_path": ".codex-plugin/plugin.json",
        "plugin_keys": [
            "name", "version", "description:descriptions.short", "author",
            "repository", "license", "keywords", "skills", "interface",
        ],
        "marketplace_path": None,
        "marketplace_keys": None,
    },
    {
        # Qoder (Claude-Code fork). Same shape as codebuddy — they are generated identical on
        # purpose; do not "dedupe" by deleting one, each host reads only its own path.
        "name": "qoder",
        "plugin_path": ".qoder-plugin/plugin.json",
        "plugin_keys": ["name", "version", "description:descriptions.short", "author", "repository", "license", "keywords"],
        "marketplace_path": ".qoder-plugin/marketplace.json",
        "marketplace_keys": ["name:marketplaceName", "description:descriptions.marketplace", "owner:author", "plugins"],
    },
    {
        # CodeBuddy (Claude-Code fork).
        "name": "codebuddy",
        "plugin_path": ".codebuddy-plugin/plugin.json",
        "plugin_keys": ["name", "version", "description:descriptions.short", "author", "repository", "license", "keywords"],
        "marketplace_path": ".codebuddy-plugin/marketplace.json",
        "marketplace_keys": ["name:marketplaceName", "description:descriptions.marketplace", "owner:author", "plugins"],
    },
    {
        # Antigravity native manifest, at the repo ROOT. Two constraints the others don't have,
        # both verified against scripts/validate.py check 2c and the file it validates:
        #   - its schema is additionalProperties:false over {name, description} + $schema, so it
        #     carries NO version and must never be version-bumped;
        #   - the committed file is ASCII-escaped (`→` for →), so it is rendered with
        #     ensure_ascii=True to stay byte-identical.
        "name": "antigravity",
        "plugin_path": "plugin.json",
        "plugin_keys": ["$schema", "name", "description:descriptions.detailed"],
        "schema": "https://antigravity.google/schemas/v1/plugin.json",
        "ascii": True,
        "marketplace_path": None,
        "marketplace_keys": None,
    },
]


def dig(source: dict, path: str):
    """Resolve a dotted source path, e.g. "descriptions.short"."""
    node = source
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(f"{SOURCE_FILE} is missing '{path}'")
        node = node[part]
    return node


def host_version(source: dict, target: dict) -> str:
    """The version this host publishes.

    Not always the source's top-level `version`. `scripts/invariants/manifest-version-sync.sh` syncs
    exactly .claude-plugin / .qoder-plugin / .codebuddy-plugin and DELIBERATELY excludes codex, which
    carries its own `X.Y.Z+codex.<stamp>` scheme. `hostVersionOverrides` is how that intent is stated as
    data instead of being flattened away — a host listed there is independent by design, not behind.
    Regenerating must never drag such a host onto the shared version."""
    override = source.get("hostVersionOverrides", {}).get(target["name"])
    return override if override is not None else source["version"]


def build(source: dict, keys: list[str], target: dict, extra: dict | None = None) -> dict:
    """Assemble one manifest in the exact key order `keys` declares."""
    extra = extra or {}
    out: dict = {}
    for key in keys:
        name, _, src = key.partition(":")
        if name in extra:
            out[name] = extra[name]
        elif name == "$schema":
            out[name] = target["schema"]
        elif name == "version":
            out[name] = host_version(source, target)
        else:
            out[name] = dig(source, src or name)
    return out


def marketplace_plugins(source: dict, target: dict) -> list[dict]:
    entry = source["marketplaceEntry"]
    return [{
        "name": source["name"],
        "description": dig(source, "descriptions.marketplaceEntry"),
        "source": entry["source"],
        "category": entry["category"],
        # host_version, not source["version"] — validate.py check 2b compares a host's
        # marketplace entry against that same host's plugin.json, so an overridden host must
        # stay self-consistent rather than matching the shared version.
        "version": host_version(source, target),
    }]


def render(obj: dict, ascii_only: bool = False) -> str:
    """2-space JSON with a trailing newline — matches the hand-written files being replaced."""
    return json.dumps(obj, indent=2, ensure_ascii=ascii_only) + "\n"


def generate(source: dict) -> dict[str, str]:
    """Return {relative path: file text} for every manifest this repo ships."""
    files: dict[str, str] = {}
    for target in TARGETS:
        ascii_only = target.get("ascii", False)
        files[target["plugin_path"]] = render(
            build(source, target["plugin_keys"], target), ascii_only
        )
        if target["marketplace_keys"]:
            extra = {"plugins": marketplace_plugins(source, target)}
            files[target["marketplace_path"]] = render(
                build(source, target["marketplace_keys"], target, extra), ascii_only
            )
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify on-disk manifests match; write nothing")
    parser.add_argument("--root", default=".", help="repo root (default: cwd)")
    args = parser.parse_args(argv)

    root = Path(args.root)
    source_path = root / SOURCE_FILE
    if not source_path.is_file():
        print(f"FATAL: {source_path} not found", file=sys.stderr)
        return 2
    source = json.loads(source_path.read_text(encoding="utf-8"))

    files = generate(source)

    if args.check:
        stale: list[str] = []
        for rel, want in sorted(files.items()):
            path = root / rel
            have = path.read_text(encoding="utf-8") if path.is_file() else ""
            if have != want:
                stale.append(rel)
                diff = difflib.unified_diff(
                    have.splitlines(keepends=True), want.splitlines(keepends=True),
                    fromfile=f"{rel} (on disk)", tofile=f"{rel} (generated)",
                )
                sys.stderr.writelines(diff)
        if stale:
            print(
                f"\nFAIL: {len(stale)} manifest(s) out of sync with {SOURCE_FILE}: {', '.join(stale)}\n"
                f"Fix: edit {SOURCE_FILE} (never the generated files), then run "
                f"`python3 scripts/gen_plugin_manifests.py`.",
                file=sys.stderr,
            )
            return 1
        print(f"OK: {len(files)} manifests match {SOURCE_FILE}")
        return 0

    for rel, text in sorted(files.items()):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        changed = not path.is_file() or path.read_text(encoding="utf-8") != text
        path.write_text(text, encoding="utf-8")
        print(f"{'wrote' if changed else 'ok   '} {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
