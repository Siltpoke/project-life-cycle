"""Tests for scripts/gen_plugin_manifests.py.

The load-bearing test here is `test_check_fails_when_a_manifest_is_hand_edited`: a guard that
cannot be shown firing is indistinguishable from a guard that is wired to nothing.
Every other test would still pass if --check always returned 0.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import gen_plugin_manifests as gen

REPO_ROOT = Path(__file__).resolve().parent.parent


def seed_source(root: Path, payload: str | None = None) -> Path:
    """Place a source file at gen.SOURCE_FILE under `root`, creating its parent dir.

    SOURCE_FILE carries a directory component (see the note on it in gen_plugin_manifests), so every
    test that writes one has to mkdir first — hence this helper rather than a bare copy/write."""
    path = root / gen.SOURCE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    if payload is None:
        shutil.copy(REPO_ROOT / gen.SOURCE_FILE, path)
    else:
        path.write_text(payload, encoding="utf-8")
    return path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A scratch repo carrying the real source file + freshly generated manifests."""
    seed_source(tmp_path)
    assert gen.main(["--root", str(tmp_path)]) == 0
    return tmp_path


def test_generates_every_declared_manifest(repo: Path):
    for target in gen.TARGETS:
        assert (repo / target["plugin_path"]).is_file(), target["name"]
        if target["marketplace_keys"]:
            assert (repo / target["marketplace_path"]).is_file(), target["name"]


def test_antigravity_manifest_carries_no_version(repo: Path):
    """Its schema is additionalProperties:false over {$schema, name, description} — a version
    field here is a hard validation failure, so the generator must never add one
    (scripts/validate.py check 2c documents the constraint)."""
    agy = json.loads((repo / "plugin.json").read_text(encoding="utf-8"))
    assert "version" not in agy
    assert list(agy) == ["$schema", "name", "description"]


def test_antigravity_manifest_is_ascii_escaped(repo: Path):
    """The committed file escapes non-ASCII; drifting to literal UTF-8 would show as a whole-file
    diff on the next regeneration even though nothing changed."""
    raw = (repo / "plugin.json").read_text(encoding="utf-8")
    assert "\\u2192" in raw
    assert "→" not in raw


def test_check_passes_on_freshly_generated(repo: Path, capsys):
    assert gen.main(["--check", "--root", str(repo)]) == 0
    assert "OK:" in capsys.readouterr().out


def test_check_fails_when_a_manifest_is_hand_edited(repo: Path, capsys):
    """The guard's firing evidence. Hand-edit one field; --check must fail and name the file."""
    victim = repo / ".qoder-plugin" / "plugin.json"
    data = json.loads(victim.read_text(encoding="utf-8"))
    data["version"] = "0.0.1-hand-edited"
    victim.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    assert gen.main(["--check", "--root", str(repo)]) == 1
    err = capsys.readouterr().err
    assert ".qoder-plugin/plugin.json" in err
    assert "0.0.1-hand-edited" in err  # the diff shows what drifted, not just that it did


def test_check_fails_when_a_manifest_is_missing(repo: Path):
    (repo / ".codex-plugin" / "plugin.json").unlink()
    assert gen.main(["--check", "--root", str(repo)]) == 1


def test_write_is_idempotent(repo: Path):
    before = {p: p.read_bytes() for p in repo.rglob("*.json")}
    assert gen.main(["--root", str(repo)]) == 0
    assert {p: p.read_bytes() for p in repo.rglob("*.json")} == before


def test_version_is_single_sourced_for_the_synced_hosts(repo: Path):
    """One version in the source, same version across every host that is IN the synced set.

    Two documented exemptions, both asserted separately below: antigravity has no version field at
    all, and any host in `hostVersionOverrides` is independent by design."""
    source = json.loads((repo / gen.SOURCE_FILE).read_text(encoding="utf-8"))
    overrides = source.get("hostVersionOverrides", {})
    for target in gen.TARGETS:
        if "version" not in target["plugin_keys"] or target["name"] in overrides:
            continue
        plugin = json.loads((repo / target["plugin_path"]).read_text(encoding="utf-8"))
        assert plugin["version"] == source["version"], target["name"]
        if target["marketplace_keys"]:
            marketplace = json.loads((repo / target["marketplace_path"]).read_text(encoding="utf-8"))
            assert marketplace["plugins"][0]["version"] == source["version"], target["name"]


def test_regenerating_never_drags_an_overridden_host_onto_the_shared_version(repo: Path):
    """The mistake this test exists to prevent, because it is an easy one to make.

    `scripts/invariants/manifest-version-sync.sh` syncs exactly .claude-plugin / .qoder-plugin /
    .codebuddy-plugin and DELIBERATELY excludes codex, which carries its own `X.Y.Z+codex.<stamp>`
    scheme. That intent lived only in a comment inside that shell script, so a reader looking at
    `.codex-plugin/plugin.json` alone sees a version that merely LOOKS behind — and a generator author
    can "fix" it, flattening a deliberate scheme onto the shared version and
    calling the result a bug fix. `hostVersionOverrides` states the intent as data instead, and
    this test fails if regeneration ever collapses it again."""
    source = json.loads((repo / gen.SOURCE_FILE).read_text(encoding="utf-8"))
    overrides = source.get("hostVersionOverrides", {})
    assert overrides, "expected at least one deliberately-independent host to be declared"

    for host, expected in overrides.items():
        target = next(t for t in gen.TARGETS if t["name"] == host)
        plugin = json.loads((repo / target["plugin_path"]).read_text(encoding="utf-8"))
        assert plugin["version"] == expected, host
        assert plugin["version"] != source["version"], (
            f"{host} is declared as an override but resolved to the shared version — "
            "the override is being ignored"
        )


def test_synced_hosts_are_exactly_the_invariants_synced_set(repo: Path):
    """Pin the generator's notion of 'synced' against the invariant that enforces it.

    `manifest-version-sync.sh` hardcodes its three directories. If the two lists ever disagree, one of
    them is silently wrong — which is the whole failure class this file is about."""
    invariant = (REPO_ROOT / "scripts/invariants/manifest-version-sync.sh").read_text(encoding="utf-8")
    source = json.loads((repo / gen.SOURCE_FILE).read_text(encoding="utf-8"))
    overrides = source.get("hostVersionOverrides", {})

    # The invariant declares its set as a shell `for d in <dirs>; do` list. Parse that line rather
    # than substring-matching the whole file: a bare `in ".codebuddy-plugin" in text` also matches a
    # mention in a comment, and the trailing `;` defeats a naive " dir " probe.
    loop = next(ln for ln in invariant.splitlines() if ln.strip().startswith("for d in "))
    synced_dirs = {tok for tok in loop.replace("for d in", "").replace(";", " ").replace("do", " ").split()}
    assert len(synced_dirs) == 3, f"expected 3 synced dirs, parsed {synced_dirs}"

    for target in gen.TARGETS:
        if "version" not in target["plugin_keys"]:
            continue  # antigravity: no version field, outside both notions
        directory = target["plugin_path"].rsplit("/", 1)[0]
        expected_synced = target["name"] not in overrides
        assert (directory in synced_dirs) == expected_synced, (
            f"{target['name']}: generator says synced={expected_synced}, "
            f"manifest-version-sync.sh says synced={directory in synced_dirs}"
        )


def test_key_order_is_preserved_per_host(repo: Path):
    """Order is part of the contract — these files are reviewed as diffs, and Claude Code's
    plugin.json puts description BEFORE version while every other host puts it after."""
    claude = json.loads((repo / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert list(claude) == ["name", "description", "version", "author"]

    qoder = json.loads((repo / ".qoder-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert list(qoder)[:3] == ["name", "version", "description"]

    marketplace = json.loads((repo / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    assert list(marketplace)[0] == "$schema"
    assert "$schema" not in json.loads(
        (repo / ".qoder-plugin" / "marketplace.json").read_text(encoding="utf-8")
    )


def test_missing_source_field_fails_loudly(tmp_path: Path):
    """A truncated source must not silently emit half a manifest."""
    seed_source(tmp_path, json.dumps({"name": "x"}))
    with pytest.raises(KeyError):
        gen.main(["--root", str(tmp_path)])


def test_repo_manifests_are_in_sync():
    """Runs against the REAL repo — the same assertion CI makes."""
    assert gen.main(["--check", "--root", str(REPO_ROOT)]) == 0


# --- validate.py check 4b -----------------------------------------------------------------
# The point of wiring the generator into validate.py was to close a hole, so the hole has to be
# demonstrated closed. `test_validate_catches_codex_drift` is the one that matters: codex is
# absent from validate.py's hand-enumerated sibling list (checks 2b/2c), which is exactly how it
# can go stale unnoticed. If 4b regresses, that test goes red and nothing else does.


@pytest.fixture
def validate_on(tmp_path: Path, monkeypatch):
    """Point validate.py's module-level REPO at a scratch repo and reset its error list."""
    import validate

    seed_source(tmp_path)
    assert gen.main(["--root", str(tmp_path)]) == 0
    monkeypatch.setattr(validate, "REPO", tmp_path)
    monkeypatch.setattr(validate, "ERRORS", [])
    return validate, tmp_path


def test_validate_passes_on_generated_manifests(validate_on):
    validate, _ = validate_on
    validate.check_manifests_generated()
    assert validate.ERRORS == []


def test_validate_catches_a_hand_edited_codex_manifest(validate_on):
    """The hole 4b exists to close: codex appears in NEITHER of validate.py's other coverage lists.

    checks 2b/2c enumerate `.qoder-plugin` and `.codebuddy-plugin` by hand, and
    `scripts/invariants/manifest-version-sync.sh` deliberately excludes codex. So before 4b, a
    hand-edit to `.codex-plugin/plugin.json` was caught by nothing at all — note this is about
    UNDETECTED EDITS, not about codex's version being wrong (it is correct, and independent by
    design). 4b must catch it while 2b/2c stay silent."""
    validate, repo = validate_on
    victim = repo / ".codex-plugin" / "plugin.json"
    data = json.loads(victim.read_text(encoding="utf-8"))
    data["version"] = "9.9.9-hand-edited"
    victim.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    validate.check_manifests_generated()
    assert len(validate.ERRORS) == 1
    assert ".codex-plugin/plugin.json" in validate.ERRORS[0]


def test_validate_catches_a_hand_edited_codex_field_other_than_version(validate_on):
    """4b's reach is every field, not just the version — that is what makes it broader than either
    of the version-shaped checks it sits beside."""
    validate, repo = validate_on
    victim = repo / ".codex-plugin" / "plugin.json"
    data = json.loads(victim.read_text(encoding="utf-8"))
    data["interface"]["brandColor"] = "#FF0000"
    victim.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    validate.check_manifests_generated()
    assert len(validate.ERRORS) == 1
    assert ".codex-plugin/plugin.json" in validate.ERRORS[0]


def test_validate_catches_a_deleted_manifest(validate_on):
    validate, repo = validate_on
    (repo / "plugin.json").unlink()
    validate.check_manifests_generated()
    assert any("plugin.json is missing" in e for e in validate.ERRORS)


def test_validate_reports_missing_source_file(tmp_path: Path, monkeypatch):
    import validate

    monkeypatch.setattr(validate, "REPO", tmp_path)
    monkeypatch.setattr(validate, "ERRORS", [])
    validate.check_manifests_generated()
    assert any(gen.SOURCE_FILE in e for e in validate.ERRORS)


def test_success_message_lists_every_declared_host():
    """The old hand-written host list omitted codex — the same omission as the version drift.
    The summary must be derived from TARGETS, so a new host cannot be forgotten here."""
    import validate

    summary = validate._generated_host_summary()
    for target in gen.TARGETS:
        assert target["name"].capitalize() in summary, target["name"]
