"""judgment gate: first-edit judgment-gate PreToolUse hook."""
import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "skills/project-lifecycle/hooks/judgment-gate.sh"
CONTRACT = "skills/project-lifecycle/references/judgment-gate.md"


def run(session_id, tool="Edit", env_extra=None, path=None, tmp=None):
    env = dict(os.environ)
    env["TMPDIR"] = str(tmp)
    if path is not None:
        env["PATH"] = path
    payload = json.dumps({"tool_name": tool, "session_id": session_id,
                          "tool_input": {"file_path": "/x"}})
    return subprocess.run(["/bin/sh", str(HOOK)], input=payload, text=True,
                          capture_output=True, env=env)


def sid():
    return "s-" + uuid.uuid4().hex


def test_first_edit_of_session_is_denied_with_reason(tmp_path):
    r = run(sid(), tmp=tmp_path)
    assert r.returncode == 2
    assert CONTRACT in r.stderr
    assert "A-2" in r.stderr and "A-1" in r.stderr


def test_second_edit_same_session_is_allowed(tmp_path):
    s = sid()
    assert run(s, tmp=tmp_path).returncode == 2
    r = run(s, tool="Write", tmp=tmp_path)
    assert r.returncode == 0
    assert r.stdout == "" and r.stderr == ""


def test_new_session_after_clear_refires(tmp_path):
    assert run(sid(), tmp=tmp_path).returncode == 2
    assert run(sid(), tmp=tmp_path).returncode == 2


def test_missing_jq_defers_honestly_not_false_pass(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for tool in ("sh", "cat", "printf"):
        p = shutil.which(tool)
        if p:
            (bindir / tool).symlink_to(p)
    r = run(sid(), tmp=tmp_path, path=str(bindir))
    assert r.returncode == 0
    out = json.loads(r.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "defer"
    assert "did NOT check" in out["additionalContext"]


def test_reason_carries_both_attended_and_unattended_branches(tmp_path):
    r = run(sid(), tmp=tmp_path)
    assert "Attended" in r.stderr and "wait for the human" in r.stderr
    assert "Unattended" in r.stderr and "subagent" in r.stderr
    assert "skip that one" in r.stderr and "never hang" in r.stderr


def test_non_edit_tool_is_ignored(tmp_path):
    r = run(sid(), tool="Bash", tmp=tmp_path)
    assert r.returncode == 0 and r.stderr == ""


def _run_raw(payload, tmp):
    env = dict(os.environ)
    env["TMPDIR"] = str(tmp)
    return subprocess.run(["/bin/sh", str(HOOK)], input=json.dumps(payload),
                          text=True, capture_output=True, env=env)


def test_missing_or_empty_session_id_defers_honestly_every_time(tmp_path):
    for payload in ({"tool_name": "Edit"}, {"tool_name": "Edit", "session_id": ""}):
        for _ in range(2):  # no shared marker may suppress/deny the 2nd id-less call
            r = _run_raw(payload, tmp_path)
            assert r.returncode == 0
            out = json.loads(r.stdout)["hookSpecificOutput"]
            assert out["permissionDecision"] == "defer"
            assert "session_id" in out["additionalContext"]
    assert not list(tmp_path.glob("plc-judgment-gate.*"))


def test_unwritable_tmpdir_fails_open_not_permanent_deny(tmp_path):
    ro = tmp_path / "ro"
    ro.mkdir()
    ro.chmod(0o500)
    try:
        if os.access(ro, os.W_OK):
            import pytest
            pytest.skip("running as root; cannot make dir unwritable")
        s = sid()
        for _ in range(2):
            r = run(s, tmp=ro)
            assert r.returncode == 0
            out = json.loads(r.stdout)["hookSpecificOutput"]
            assert out["permissionDecision"] == "defer"
            assert "marker" in out["additionalContext"]
        # Also run explicitly under dash where present. On macOS /bin/sh is bash,
        # which does NOT treat a redirection failure on the special built-in `:` as
        # fatal; dash (Ubuntu /bin/sh) does, and it hard-blocked here until the
        # marker write was wrapped in a subshell. This pins that regression on any
        # machine that has dash, not only in CI.
        dash = shutil.which("dash")
        if dash:
            payload = json.dumps({"tool_name": "Edit", "session_id": sid(),
                                  "tool_input": {}})
            env = dict(os.environ, TMPDIR=str(ro))
            r = subprocess.run([dash, str(HOOK)], input=payload, text=True,
                               capture_output=True, env=env)
            assert r.returncode == 0, f"dash hard-blocked on unwritable TMPDIR: rc={r.returncode} err={r.stderr!r}"
            out = json.loads(r.stdout)["hookSpecificOutput"]
            assert out["permissionDecision"] == "defer"
            assert "marker" in out["additionalContext"]
    finally:
        ro.chmod(0o700)


def test_reason_has_absolute_contract_path_from_foreign_cwd(tmp_path):
    cwd = tmp_path / "elsewhere"
    cwd.mkdir()
    env = dict(os.environ, TMPDIR=str(tmp_path))
    payload = json.dumps({"tool_name": "Edit", "session_id": sid(), "tool_input": {}})
    r = subprocess.run(["/bin/sh", str(HOOK)], input=payload, text=True,
                       capture_output=True, env=env, cwd=cwd)
    assert r.returncode == 2
    import re
    m = re.search(r"(/\S*judgment-gate\.md|/\S*plc-judgment-gate\.contract\.md)", r.stderr)
    assert m, r.stderr
    assert os.path.isabs(m.group(1)) and Path(m.group(1)).is_file()
    assert "A-2" in r.stderr and "Attended" in r.stderr  # gist still inlined


def test_installed_layout_prefers_contract_beside_hook(tmp_path):
    d = tmp_path / "hooks"
    d.mkdir()
    shutil.copy(HOOK, d / "plc-judgment-gate.sh")
    (d / "plc-judgment-gate.contract.md").write_text("x")
    env = dict(os.environ, TMPDIR=str(tmp_path))
    payload = json.dumps({"tool_name": "Edit", "session_id": sid()})
    r = subprocess.run(["/bin/sh", str(d / "plc-judgment-gate.sh")], input=payload,
                       text=True, capture_output=True, env=env, cwd=tmp_path)
    assert r.returncode == 2
    assert str(d / "plc-judgment-gate.contract.md") in r.stderr


def test_malformed_json_with_jq_defers_honestly(tmp_path):
    env = dict(os.environ, TMPDIR=str(tmp_path))
    r = subprocess.run(["/bin/sh", str(HOOK)], input="{not json", text=True,
                       capture_output=True, env=env)
    assert r.returncode == 0
    out = json.loads(r.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "defer"
    assert "did NOT check" in out["additionalContext"]
    assert "not a pass" in out["additionalContext"]
