"""judgment gate: shadow-mode recorder hook (records what the routing WOULD do; never interferes)."""
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from judgment_corpus_schema import CORRECT_ACTIONS, DECISION_TYPES  # noqa: E402  (enums imported, never redefined)

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "skills/project-lifecycle/hooks/judgment-shadow-record.sh"
ACTION_GATE = ROOT / "skills/project-lifecycle/hooks/judgment-action-gate.sh"

# decision-type -> timing map: (would_action, would_time)
TIMING = {
    "taste": ("shadow-record", "at-finish"),
    "product-boundary": ("confirm-before-build", "before-build"),
    "side-effect": ("hard-stop", "none"),
    "mechanical": ("do-and-report", "none"),
}
LOG_FIELDS = {"id", "what", "authorization_tier", "decision_type", "would_action", "would_time"}


def sid():
    return "s-" + uuid.uuid4().hex


def decision(i="d1", dt="taste", **kw):
    d = {"id": i, "what": "pick a button label", "authorization_tier": "delegated", "decision_type": dt}
    d.update(kw)
    return d


def payload(session_id, decisions, tool="Edit", extra=None):
    ti = {"file_path": "/x"}
    if decisions is not None:
        ti["judgment"] = decisions
    if extra:
        ti.update(extra)
    p = {"tool_name": tool, "tool_input": ti}
    if session_id is not None:
        p["session_id"] = session_id
    return p


def run(p, tmp, path=None, raw=None):
    env = dict(os.environ)
    env["TMPDIR"] = str(tmp)
    if path is not None:
        env["PATH"] = path
    data = raw if raw is not None else json.dumps(p)
    return subprocess.run(["/bin/sh", str(HOOK)], input=data, text=True, capture_output=True, env=env)


def log(tmp, s):
    f = Path(tmp) / f"plc-judgment-shadow.{s}.jsonl"
    if not f.exists():
        return []
    return [json.loads(x) for x in f.read_text().splitlines() if x.strip()]


def test_timing_map_covers_exactly_the_schema_enums():
    assert set(TIMING) == DECISION_TYPES
    assert {a for a, _ in TIMING.values()} <= CORRECT_ACTIONS


@pytest.mark.parametrize("dt", sorted(DECISION_TYPES))
def test_timing_map_by_decision_type(tmp_path, dt):
    s = sid()
    r = run(payload(s, [decision(dt=dt)]), tmp_path)
    assert r.returncode == 0
    (line,) = log(tmp_path, s)
    assert (line["would_action"], line["would_time"]) == TIMING[dt]
    assert line["decision_type"] == dt


def test_records_without_blocking(tmp_path):
    s = sid()
    for dt in sorted(DECISION_TYPES):
        r = run(payload(s, [decision(dt=dt)]), tmp_path)
        assert r.returncode == 0 and r.stderr == "" and r.stdout == ""
    assert len(log(tmp_path, s)) == 4


def test_never_exit_2_even_on_destructive_side_effect(tmp_path):
    s = sid()
    p = payload(s, [decision(dt="side-effect")], tool="Bash",
                extra={"command": "kubectl delete ns prod"})
    r = run(p, tmp_path)
    assert r.returncode == 0 and r.stderr == ""
    assert log(tmp_path, s)[0]["would_action"] == "hard-stop"


def test_side_effect_agrees_with_action_gate_factual_trigger(tmp_path):
    """Cross-check: the destructive command the action gate really blocks is what the map calls hard-stop."""
    s = sid()
    cmd = {"command": "aws s3 rm s3://bucket --recursive"}
    p = payload(s, [decision(dt="side-effect")], tool="Bash", extra=cmd)
    gate = subprocess.run(["/bin/sh", str(ACTION_GATE)], input=json.dumps(p), text=True,
                          capture_output=True, env={**os.environ, "TMPDIR": str(tmp_path)})
    assert gate.returncode == 2
    run(p, tmp_path)
    assert log(tmp_path, s)[0]["would_action"] == "hard-stop"


def test_shadow_log_shape(tmp_path):
    s = sid()
    run(payload(s, [decision("a", "taste"), decision("b", "mechanical")]), tmp_path)
    rows = log(tmp_path, s)
    assert [r["id"] for r in rows] == ["a", "b"]
    for r in rows:
        assert set(r) == LOG_FIELDS
        assert r["would_action"] in CORRECT_ACTIONS
        assert r["would_time"] in {"before-build", "at-finish", "none"}
        assert r["authorization_tier"] == "delegated" and r["what"]


def test_log_is_append_only_across_calls(tmp_path):
    s = sid()
    run(payload(s, [decision("a")]), tmp_path)
    run(payload(s, [decision("b")]), tmp_path)
    assert [r["id"] for r in log(tmp_path, s)] == ["a", "b"]


def test_sessions_get_separate_logs(tmp_path):
    s1, s2 = sid(), sid()
    run(payload(s1, [decision("a")]), tmp_path)
    run(payload(s2, [decision("b")]), tmp_path)
    assert [r["id"] for r in log(tmp_path, s1)] == ["a"]
    assert [r["id"] for r in log(tmp_path, s2)] == ["b"]


def test_no_declared_decisions_records_nothing_silently(tmp_path):
    s = sid()
    r = run(payload(s, None), tmp_path)
    assert r.returncode == 0 and r.stdout == "" and r.stderr == ""
    assert log(tmp_path, s) == []


def test_invalid_decisions_are_skipped_not_guessed(tmp_path):
    s = sid()
    bad = [decision(dt="vibes"), {"id": "x"}, "junk", decision("ok", "taste")]
    r = run(payload(s, bad), tmp_path)
    assert r.returncode == 0
    assert [x["id"] for x in log(tmp_path, s)] == ["ok"]


def test_single_object_decision_is_accepted(tmp_path):
    s = sid()
    run(payload(s, decision("solo", "product-boundary")), tmp_path)
    assert log(tmp_path, s)[0]["would_time"] == "before-build"


def test_unrelated_tool_is_ignored(tmp_path):
    s = sid()
    r = run(payload(s, [decision()], tool="Read"), tmp_path)
    assert r.returncode == 0 and r.stdout == "" and log(tmp_path, s) == []


def test_defers_and_records_nothing_on_absent_jq(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for tool in ("sh", "cat", "printf"):
        p = shutil.which(tool)
        if p:
            (bindir / tool).symlink_to(p)
    s = sid()
    r = run(payload(s, [decision()]), tmp_path, path=str(bindir))
    assert r.returncode == 0
    out = json.loads(r.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "defer" and "did NOT" in out["additionalContext"]
    assert log(tmp_path, s) == []


def test_defers_and_records_nothing_without_session_id(tmp_path):
    r = run(payload(None, [decision()]), tmp_path)
    assert r.returncode == 0
    assert json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] == "defer"
    assert list(tmp_path.glob("plc-judgment-shadow.*")) == []


def test_defers_and_records_nothing_on_malformed_input(tmp_path):
    r = run(None, tmp_path, raw="{not json")
    assert r.returncode == 0
    assert json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] == "defer"
    assert list(tmp_path.glob("plc-judgment-shadow.*")) == []


def test_unwritable_tmpdir_still_exits_zero(tmp_path):
    r = run(payload(sid(), [decision()]), tmp_path / "does-not-exist")
    assert r.returncode == 0


def test_hook_source_never_exits_2_and_has_no_cjk_or_network():
    src = HOOK.read_text(encoding="utf-8")
    assert "exit 2" not in src
    assert all(ord(c) < 0x2E80 or ord(c) > 0x9FFF for c in src)
    for banned in ("python", "curl", "wget", "gh "):
        assert banned not in src
