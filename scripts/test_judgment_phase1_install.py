"""judgment gate — install/uninstall wiring for the phase-1 hooks (action-gate + shadow-recorder).

Runs ONLY against a temp settings file via CLAUDE_SETTINGS / CLAUDE_HOOKS_DIR; never touches ~/.claude.
"""
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALL = ROOT / "scripts" / "install-judgment-phase1-hooks.sh"
UNINSTALL = ROOT / "scripts" / "uninstall-judgment-phase1-hooks.sh"
HOOKS = ROOT / "skills" / "project-lifecycle" / "hooks"
GUARD = {"matcher": "Edit|Write", "hooks": [{"type": "command", "command": "/x/guard.sh"}]}
GATE, REC = "plc-judgment-action-gate.sh", "plc-judgment-shadow-record.sh"


def run(script, tmp_path):
    env = dict(os.environ, CLAUDE_SETTINGS=str(tmp_path / "settings.json"),
               CLAUDE_HOOKS_DIR=str(tmp_path / "hooks"))
    return subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True)


def load(tmp_path):
    return json.loads((tmp_path / "settings.json").read_text())


def seed(tmp_path, data):
    (tmp_path / "settings.json").write_text(json.dumps(data))


def entries(s, base):
    return [e for e in s["hooks"]["PreToolUse"]
            if any(h["command"].endswith("/" + base) for h in e["hooks"])]


def test_wires_both_hooks(tmp_path):
    seed(tmp_path, {})
    r = run(INSTALL, tmp_path)
    assert r.returncode == 0, r.stderr
    s = load(tmp_path)
    g, rec = entries(s, GATE), entries(s, REC)
    assert len(g) == 1 and len(rec) == 1
    assert g[0]["matcher"] == "Bash"  # command-level triggers only; Edit|Write would spawn per edit
    assert rec[0]["matcher"] == "Bash|Edit|Write"
    for base, src in ((GATE, "judgment-action-gate.sh"), (REC, "judgment-shadow-record.sh")):
        dest = tmp_path / "hooks" / base
        assert dest.is_file() and os.access(dest, os.X_OK)
        assert dest.read_bytes() == (HOOKS / src).read_bytes()
    assert (tmp_path / "hooks" / "plc-judgment-phase1.contract.md").is_file()


def test_idempotent(tmp_path):
    seed(tmp_path, {})
    assert run(INSTALL, tmp_path).returncode == 0
    first = (tmp_path / "settings.json").read_bytes()
    assert run(INSTALL, tmp_path).returncode == 0
    assert (tmp_path / "settings.json").read_bytes() == first
    s = load(tmp_path)
    assert len(entries(s, GATE)) == 1 and len(entries(s, REC)) == 1


def test_preserves_existing_hooks(tmp_path):
    seed(tmp_path, {"model": "x", "hooks": {"PreToolUse": [GUARD], "Stop": [{"hooks": []}]}})
    assert run(INSTALL, tmp_path).returncode == 0
    s = load(tmp_path)
    assert GUARD in s["hooks"]["PreToolUse"] and s["model"] == "x" and "Stop" in s["hooks"]


def test_uninstall_removes_only_markers(tmp_path):
    look = {"matcher": "Bash", "hooks": [{"type": "command", "command": "/x/my-" + GATE}]}
    sib = {"type": "command", "command": "/x/sibling.sh"}
    seed(tmp_path, {"hooks": {"PreToolUse": [GUARD, look]}})
    run(INSTALL, tmp_path)
    s = load(tmp_path)
    entries(s, GATE)[0]["hooks"].append(sib)  # hand-merged sibling inside our entry
    seed(tmp_path, s)
    r = run(UNINSTALL, tmp_path)
    assert r.returncode == 0, r.stderr
    after = load(tmp_path)["hooks"]["PreToolUse"]
    assert GUARD in after and look in after
    assert any(h == sib for e in after for h in e["hooks"])
    assert not any(h["command"].endswith("/" + GATE) or h["command"].endswith("/" + REC)
                   for e in after for h in e["hooks"])
    for f in (GATE, REC, "plc-judgment-phase1.contract.md"):
        assert not (tmp_path / "hooks" / f).exists()
    assert run(UNINSTALL, tmp_path).returncode == 0  # idempotent


def test_action_gate_in_pushpath_invariant():
    src = (ROOT / "scripts/invariants/premerge-no-network-on-push-path.sh").read_text()
    assert "skills/project-lifecycle/hooks/judgment-action-gate.sh" in src
    r = subprocess.run(["/bin/bash", "scripts/invariants/premerge-no-network-on-push-path.sh"],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_probe_hook_records_keys_and_is_inert(tmp_path):
    probe = ROOT / "scripts" / "probe-judgment-channel-hook.sh"
    out = tmp_path / "probe.jsonl"
    env = dict(os.environ, PLC_PROBE_OUT=str(out))
    for ti, want in (({"command": "ls", "judgment": {"id": "p"}}, True), ({"command": "ls"}, False)):
        r = subprocess.run(["sh", str(probe)], input=json.dumps({"tool_name": "Bash", "tool_input": ti}),
                           env=env, capture_output=True, text=True)
        assert r.returncode == 0 and r.stdout == ""
        assert json.loads(out.read_text().splitlines()[-1])["judgment_present"] is want
