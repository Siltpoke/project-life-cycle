"""judgment gate — install/uninstall wiring for the judgment-gate hook (fixture settings.json)."""
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALL = ROOT / "scripts" / "install-judgment-gate-hook.sh"
UNINSTALL = ROOT / "scripts" / "uninstall-judgment-gate-hook.sh"
GUARD = {"matcher": "Edit|Write", "hooks": [{"type": "command", "command": "/x/guard.sh"}]}


def run(script, tmp_path):
    env = dict(os.environ, CLAUDE_SETTINGS=str(tmp_path / "settings.json"),
               CLAUDE_HOOKS_DIR=str(tmp_path / "hooks"))
    return subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True)


def load(tmp_path):
    return json.loads((tmp_path / "settings.json").read_text())


def ours(settings):
    return [e for e in settings["hooks"]["PreToolUse"]
            if any("plc-judgment-gate.sh" in h["command"] for h in e["hooks"])]


def seed(tmp_path, data):
    (tmp_path / "settings.json").write_text(json.dumps(data))


def test_install_adds_one_pretooluse_entry(tmp_path):
    seed(tmp_path, {})
    r = run(INSTALL, tmp_path)
    assert r.returncode == 0, r.stderr
    e = ours(load(tmp_path))
    assert len(e) == 1 and e[0]["matcher"] == "Edit|Write"
    cmd = e[0]["hooks"][0]["command"]
    assert e[0]["hooks"][0]["type"] == "command"
    assert Path(cmd).is_file() and os.access(cmd, os.X_OK)
    assert Path(cmd).read_bytes() == (ROOT / "skills/project-lifecycle/hooks/judgment-gate.sh").read_bytes()
    contract = tmp_path / "hooks" / "plc-judgment-gate.contract.md"
    assert contract.is_file()
    assert contract.read_bytes() == (ROOT / "skills/project-lifecycle/references/judgment-gate.md").read_bytes()


def test_install_is_idempotent(tmp_path):
    seed(tmp_path, {})
    assert run(INSTALL, tmp_path).returncode == 0
    assert run(INSTALL, tmp_path).returncode == 0
    assert len(ours(load(tmp_path))) == 1


def test_install_preserves_existing_pretooluse_hooks(tmp_path):
    seed(tmp_path, {"model": "x", "hooks": {"PreToolUse": [GUARD], "Stop": [{"hooks": []}]}})
    assert run(INSTALL, tmp_path).returncode == 0
    s = load(tmp_path)
    assert GUARD in s["hooks"]["PreToolUse"] and len(ours(s)) == 1
    assert s["model"] == "x" and "Stop" in s["hooks"]


def test_uninstall_removes_only_our_entry(tmp_path):
    seed(tmp_path, {"hooks": {"PreToolUse": [GUARD]}})
    run(INSTALL, tmp_path)
    r = run(UNINSTALL, tmp_path)
    assert r.returncode == 0, r.stderr
    s = load(tmp_path)
    assert s["hooks"]["PreToolUse"] == [GUARD]
    assert not (tmp_path / "hooks" / "plc-judgment-gate.sh").exists()
    assert not (tmp_path / "hooks" / "plc-judgment-gate.contract.md").exists()
    assert run(UNINSTALL, tmp_path).returncode == 0  # idempotent


def test_uninstall_spares_lookalike_and_sibling_in_same_entry(tmp_path):
    look = {"matcher": "Edit|Write", "hooks": [{"type": "command", "command": "/x/my-plc-judgment-gate.sh"}]}
    sib = {"type": "command", "command": "/x/sibling.sh"}
    seed(tmp_path, {"hooks": {"PreToolUse": [look]}})
    run(INSTALL, tmp_path)
    s = load(tmp_path)
    mine = [e for e in s["hooks"]["PreToolUse"] if e is not look and e != look][0]
    mine["hooks"].append(sib)  # user hand-merged a sibling into our entry object
    seed(tmp_path, s)
    assert run(UNINSTALL, tmp_path).returncode == 0
    after = load(tmp_path)["hooks"]["PreToolUse"]
    assert look in after
    assert any(h == sib for e in after for h in e["hooks"])
    assert not any(h["command"].endswith("/plc-judgment-gate.sh") for e in after for h in e["hooks"])
