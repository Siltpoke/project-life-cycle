#!/usr/bin/env python3
"""Validate the project-lifecycle skill repo.

Checks:
1. ``.claude-plugin/marketplace.json`` parses as JSON and has required fields.
2. ``.claude-plugin/plugin.json`` parses as JSON and has required fields.
3. Each sibling plugin dir (``.qoder-plugin``, ``.codebuddy-plugin``) has a ``plugin.json``
   and ``marketplace.json`` that parse as JSON, carry required fields, and match the Claude
   plugin manifest on ``name`` and ``version``.
4. The top-level ``plugin.json`` (Antigravity native manifest) parses as JSON, has
   ``name`` + ``description``, and matches the Claude manifest ``name`` (its schema forbids
   a ``version`` field, so it is name-checked only).
5. Every ``skills/*/SKILL.md`` has valid frontmatter (``name`` + ``description``).
6. Every reference mentioned in ``SKILL.md`` exists on disk.
7. Every ``commands/*.md`` listed in ``scripts/commands-manifest.txt``
   exists on disk and has frontmatter with at least a ``description``.
8. Every command file under ``commands/`` is listed in the manifest (and
   vice versa) — no orphans, no missing files.
9. Every **tracked** ``.md`` file is valid UTF-8 (``git ls-files``, not a filesystem
   walk — see ``md_files_to_check``; outside a git work tree it walks and says so).

Pure stdlib. Run locally or in CI:

    python3 scripts/validate.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

ERRORS: list[str] = []


def md_files_to_check(repo: Path) -> tuple[list[Path], str]:
    """The ``.md`` files this repo is responsible for, plus HOW they were found.

    Deliberately ``git ls-files``, not ``rglob``. A filesystem walk of this repo
    reaches orders of magnitude more ``.md`` files than are tracked; the rest are a co-located
    tool's cache directory, a gitignored ``docs/`` tree this project keeps out of version control,
    and other dot-directories. Walking them made the validator's verdict depend on
    unrelated local state, and — the load-bearing reason — left
    ``close-gate.sh``'s test-evidence freshness row unanswerable: freshness is
    "did a relevant path change since the recorded SHA", git can only see tracked
    paths, so a validator with nearly all of its inputs invisible to git has no checkable
    freshness at all. Narrowing here is what lets that row claim exactly what it
    verified.

    Returns ``(files, "tracked")`` normally. Outside a git work tree (a tarball, a
    vendored copy) it returns ``(files, "walk")`` — the caller REPORTS that mode
    rather than swapping surfaces silently, because an unannounced fallback is
    the same defect class this narrowing exists to remove.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "ls-files", "-z", "--", "*.md"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return ([p for p in repo.rglob("*.md") if ".git" not in p.parts], "walk")
    # git ls-files still names a tracked file after it's deleted in the working tree
    # but not yet staged; skip those so a mid-refactor `rm` cannot crash check_utf8
    # (a FileNotFoundError there would also land a traceback in the evidence file).
    return ([f for rel in out.split("\0") if rel and (f := repo / rel).exists()], "tracked")


def error(msg: str) -> None:
    ERRORS.append(msg)
    print(f"ERROR: {msg}", file=sys.stderr)


def check_json(path: Path, required: set[str]) -> dict | None:
    if not path.exists():
        error(f"missing: {path.relative_to(REPO)}")
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        error(f"{path.relative_to(REPO)} invalid JSON: {e}")
        return None
    missing = required - set(data)
    if missing:
        error(f"{path.relative_to(REPO)} missing keys: {sorted(missing)}")
    return data


def check_skill_frontmatter(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        error(f"{path.relative_to(REPO)} missing YAML frontmatter")
        return None
    body = m.group(1)
    fm: dict[str, str] = {}
    for line in body.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    for key in ("name", "description"):
        if key not in fm or not fm[key]:
            error(f"{path.relative_to(REPO)} frontmatter missing '{key}'")
    return fm


def check_reference_links(skill_md: Path) -> None:
    """Find every `references/<file>.md` mention in SKILL.md and assert it exists."""
    text = skill_md.read_text(encoding="utf-8")
    skill_dir = skill_md.parent
    for ref in re.findall(r"references/([a-zA-Z0-9_-]+\.md)", text):
        target = skill_dir / "references" / ref
        if not target.exists():
            error(f"{skill_md.relative_to(REPO)} references missing file: references/{ref}")


def check_utf8(path: Path) -> None:
    try:
        path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        error(f"{path.relative_to(REPO)} not valid UTF-8: {e}")


def read_manifest(path: Path) -> set[str]:
    """Read commands manifest, returning the set of declared filenames."""
    if not path.exists():
        error(f"missing manifest: {path.relative_to(REPO)}")
        return set()
    out: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        out.add(line)
    return out


def check_command_frontmatter(path: Path) -> None:
    """Slash commands need YAML frontmatter with a description."""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        error(f"{path.relative_to(REPO)} missing YAML frontmatter")
        return
    body = m.group(1)
    fm: dict[str, str] = {}
    for line in body.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    if not fm.get("description"):
        error(f"{path.relative_to(REPO)} frontmatter missing 'description'")


def check_commands(commands_dir: Path, manifest_path: Path) -> None:
    declared = read_manifest(manifest_path)
    if not commands_dir.is_dir():
        if declared:
            error(f"commands/ dir missing but manifest declares: {sorted(declared)}")
        return

    on_disk = {p.name for p in commands_dir.glob("*.md")}

    for name in sorted(declared - on_disk):
        error(f"manifest declares 'commands/{name}' but file missing on disk")

    for name in sorted(on_disk - declared):
        error(
            f"commands/{name} present on disk but NOT listed in scripts/commands-manifest.txt "
            "(add it or remove the file)"
        )

    for name in sorted(declared & on_disk):
        check_command_frontmatter(commands_dir / name)


def check_sibling_manifest(dir_name: str, ref_plugin: dict | None) -> None:
    """Validate a sibling plugin dir (.qoder-plugin / .codebuddy-plugin) — its plugin.json
    and marketplace.json must agree with the Claude manifest on name + version."""
    spl = check_json(REPO / dir_name / "plugin.json", {"name"})
    if ref_plugin and spl:
        if ref_plugin.get("version") != spl.get("version"):
            error(
                f"version mismatch: .claude-plugin/plugin.json has {ref_plugin.get('version')!r}, "
                f"but {dir_name}/plugin.json has {spl.get('version')!r}"
            )
        if ref_plugin["name"] != spl["name"]:
            error(
                f"name mismatch: .claude-plugin/plugin.json name '{ref_plugin['name']}' "
                f"does not match {dir_name}/plugin.json name '{spl['name']}'"
            )
    smp = check_json(REPO / dir_name / "marketplace.json", {"name", "owner", "plugins"})
    if smp and not isinstance(smp.get("plugins"), list):
        error(f"{dir_name}/marketplace.json 'plugins' must be a list")
    if smp and spl:
        names = {p.get("name") for p in smp.get("plugins", []) if isinstance(p, dict)}
        if spl["name"] not in names:
            error(
                f"{dir_name}/plugin.json name '{spl['name']}' not listed in "
                f"{dir_name}/marketplace.json plugins (got {sorted(names)})"
            )
        versions = {
            p.get("version") for p in smp.get("plugins", [])
            if isinstance(p, dict) and p.get("name") == spl["name"]
        }
        if spl.get("version") not in versions:
            error(
                f"version mismatch: {dir_name}/plugin.json has {spl.get('version')!r}, "
                f"but {dir_name}/marketplace.json lists {sorted(versions)} for plugin '{spl['name']}'"
            )


def main() -> int:
    # 1. marketplace.json
    mp = check_json(REPO / ".claude-plugin" / "marketplace.json", {"name", "owner", "plugins"})
    if mp and not isinstance(mp.get("plugins"), list):
        error("marketplace.json 'plugins' must be a list")

    # 2. Claude plugin.json
    pl = check_json(REPO / ".claude-plugin" / "plugin.json", {"name", "description"})

    # marketplace ↔ plugin name consistency
    if mp and pl:
        names_in_market = {p.get("name") for p in mp.get("plugins", []) if isinstance(p, dict)}
        if pl["name"] not in names_in_market:
            error(
                f"plugin.json name '{pl['name']}' not listed in marketplace.json plugins "
                f"(got {sorted(names_in_market)})"
            )

    # 2b. Sibling plugin manifests (Qoder, CodeBuddy) — must match the Claude manifest.
    check_sibling_manifest(".qoder-plugin", pl)
    check_sibling_manifest(".codebuddy-plugin", pl)

    # 2c. Antigravity native manifest (top-level plugin.json). Its schema is
    #     additionalProperties:false with only name + description — no version field —
    #     so it is never version-bumped; enforce name agreement with Claude only.
    agy = check_json(REPO / "plugin.json", {"name", "description"})
    if pl and agy and pl["name"] != agy["name"]:
        error(
            f"name mismatch: .claude-plugin/plugin.json name '{pl['name']}' "
            f"does not match plugin.json (Antigravity) name '{agy['name']}'"
        )

    # 3. Per-skill checks
    skills_dir = REPO / "skills"
    if not skills_dir.is_dir():
        error("missing skills/ directory")
    else:
        for skill_md in skills_dir.glob("*/SKILL.md"):
            check_skill_frontmatter(skill_md)
            check_reference_links(skill_md)

    # 4. Commands ↔ manifest reconciliation
    check_commands(REPO / "commands", REPO / "scripts" / "commands-manifest.txt")

    # 5. UTF-8 on every .md this repo ships (tracked files — see md_files_to_check)
    md_files, how = md_files_to_check(REPO)
    if how == "walk":
        print("note: not a git work tree — UTF-8 check fell back to a filesystem walk")
    for md in md_files:
        check_utf8(md)

    if ERRORS:
        print(f"\nFAILED: {len(ERRORS)} error(s)", file=sys.stderr)
        return 1
    print("OK: Claude + Qoder + CodeBuddy + Antigravity manifests + skill references + commands + UTF-8 all valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
