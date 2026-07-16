import json
import cognition_log as cl

def _valid():
    return {"intent": "x", "subject": "onboarding", "criterion": "y"}

def test_valid_minimal_entry_has_no_errors():
    assert cl.validate_entry(_valid()) == []

def test_missing_required_field_reported():
    e = _valid(); del e["criterion"]
    errs = cl.validate_entry(e)
    assert any("criterion" in x for x in errs)

def test_bad_status_reported():
    e = _valid(); e["status"] = "maybe"
    assert any("status" in x for x in cl.validate_entry(e))

def test_salience_out_of_range_reported():
    e = _valid(); e["salience"] = 9
    assert any("salience" in x for x in cl.validate_entry(e))

def test_append_creates_fragment_and_returns_id(tmp_path):
    e = {"intent": "x", "subject": "auth", "criterion": "y"}
    out = cl.append_entry(e, root=tmp_path, branch="feat/x",
                          now="2026-07-09T10:00:00", author="v", source="capture")
    frag = cl.fragment_path(tmp_path, "feat/x", "2026-07-09")
    assert frag.exists()
    lines = frag.read_text().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["id"] == out["id"] and rec["subject"] == "auth"
    assert rec["source"] == "capture" and rec["status"] == "tentative"

def test_append_is_add_only(tmp_path):
    for s in ("auth", "cache"):
        cl.append_entry({"intent": "x", "subject": s, "criterion": "y"},
                        root=tmp_path, branch="feat/x",
                        now="2026-07-09T10:00:00", author="v", source="capture")
    frag = cl.fragment_path(tmp_path, "feat/x", "2026-07-09")
    assert len(frag.read_text().splitlines()) == 2  # appended, not overwritten

def test_branch_slug_sanitized(tmp_path):
    p = cl.fragment_path(tmp_path, "feat/phase-3", "2026-07-09")
    assert p.name == "2026-07-09-feat-phase-3.jsonl"

def test_invalid_entry_raises(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        cl.append_entry({"intent": "x"}, root=tmp_path, branch="b",
                        now="2026-07-09T10:00:00", author="v", source="capture")

def test_load_entries_reads_all_fragments(tmp_path):
    for br in ("feat/a", "feat/b"):
        cl.append_entry({"intent": "x", "subject": br, "criterion": "y"},
                        root=tmp_path, branch=br,
                        now="2026-07-09T10:00:00", author="v", source="capture")
    got = cl.load_entries(tmp_path)
    assert {e["subject"] for e in got} == {"feat/a", "feat/b"}

def test_load_entries_skips_malformed(tmp_path):
    frag = cl.fragment_path(tmp_path, "feat/x", "2026-07-09")
    frag.parent.mkdir(parents=True, exist_ok=True)
    frag.write_text('{"intent":"x","subject":"s","criterion":"c"}\nnot json\n\n')
    assert len(cl.load_entries(tmp_path)) == 1

def test_load_entries_empty_when_no_dir(tmp_path):
    assert cl.load_entries(tmp_path) == []

def test_load_entries_skips_non_dict_json(tmp_path):
    frag = cl.fragment_path(tmp_path, "feat/x", "2026-07-09")
    frag.parent.mkdir(parents=True, exist_ok=True)
    frag.write_text('{"intent":"x","subject":"s","criterion":"c"}\n[1, 2, 3]\n')
    got = cl.load_entries(tmp_path)
    assert len(got) == 1
    assert got[0]["subject"] == "s"

def _e(subject, ts, status="tentative"):
    return {"id": ts, "subject": subject, "intent": "i", "criterion": "c",
            "ts": ts, "status": status}

def test_find_related_matches_same_subject():
    ex = [_e("onboarding", "2026-07-01"), _e("cache", "2026-07-02")]
    r = cl.find_related("Onboarding", ex)
    assert [e["subject"] for e in r] == ["onboarding"]

def test_find_related_token_overlap():
    ex = [_e("cache layer", "2026-07-01")]
    assert cl.find_related("cache", ex)  # shares token 'cache'

def test_find_related_excludes_superseded():
    ex = [_e("auth", "2026-07-01", status="superseded")]
    assert cl.find_related("auth", ex) == []

def test_find_related_recent_first():
    ex = [_e("auth", "2026-07-01"), _e("auth", "2026-07-05")]
    assert [e["ts"] for e in cl.find_related("auth", ex)] == ["2026-07-05", "2026-07-01"]

def test_normalize_entry_id_is_eight_hex_chars():
    e = {"intent": "x", "subject": "auth", "criterion": "y"}
    out = cl.normalize_entry(e, now="2026-07-09T10:00:00", author="v", source="capture")
    assert len(out["id"]) == 8
    assert all(c in "0123456789abcdef" for c in out["id"])

def test_normalize_entry_id_collision_resistant_same_second():
    # Two same-second captures of the same subject+intent (e.g. two parallel
    # sessions) must not collide, even with identical now/subject/intent/author/source.
    e = {"intent": "x", "subject": "auth", "criterion": "y"}
    out1 = cl.normalize_entry(e, now="2026-07-09T10:00:00", author="v", source="capture")
    out2 = cl.normalize_entry(e, now="2026-07-09T10:00:00", author="v", source="capture")
    assert out1["id"] != out2["id"]

import subprocess, sys
from pathlib import Path
SCRIPT = str(Path(__file__).parent / "cognition_log.py")

def test_cli_append_writes_and_prints(tmp_path):
    r = subprocess.run([sys.executable, SCRIPT, "append",
        "--intent", "effortless onboarding", "--subject", "onboarding",
        "--criterion", "first success no docs", "--branch", "feat/x",
        "--author", "v", "--root", str(tmp_path)],
        capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    rec = json.loads(r.stdout)
    assert rec["subject"] == "onboarding" and rec["source"] == "capture"

def test_cli_append_validation_error_exit2(tmp_path):
    r = subprocess.run([sys.executable, SCRIPT, "append",
        "--intent", "x", "--subject", "s", "--root", str(tmp_path)],  # no --criterion
        capture_output=True, text=True)
    assert r.returncode == 2
    assert "criterion" in r.stderr

def test_cli_append_supersedes_threaded_through(tmp_path):
    r = subprocess.run([sys.executable, SCRIPT, "append",
        "--intent", "effortless onboarding v2", "--subject", "onboarding",
        "--criterion", "first success no docs", "--status", "firm",
        "--supersedes", "abc12345", "--branch", "feat/x",
        "--author", "v", "--root", str(tmp_path)],
        capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    rec = json.loads(r.stdout)
    assert rec["supersedes"] == "abc12345"

def test_cli_append_source_flag(tmp_path):
    import glob
    r = subprocess.run([sys.executable, SCRIPT, "append",
                        "--intent", "re-said the auth rule", "--subject", "auth",
                        "--criterion", "what would settle it", "--source", "reexplain",
                        "--branch", "feat/x", "--root", str(tmp_path)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    frags = glob.glob(str(tmp_path / "docs" / "cognition-log.d" / "*.jsonl"))
    assert frags, "no fragment written"
    rec = json.loads(Path(frags[0]).read_text().strip().splitlines()[-1])
    assert rec["source"] == "reexplain"

def test_cli_append_source_defaults_capture(tmp_path):
    import glob
    r = subprocess.run([sys.executable, SCRIPT, "append",
                        "--intent", "why", "--subject", "s", "--criterion", "c",
                        "--branch", "feat/x", "--root", str(tmp_path)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    frags = glob.glob(str(tmp_path / "docs" / "cognition-log.d" / "*.jsonl"))
    rec = json.loads(Path(frags[0]).read_text().strip().splitlines()[-1])
    assert rec["source"] == "capture"
