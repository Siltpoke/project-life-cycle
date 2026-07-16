import cognition_render as cr

def test_fresh_recent():
    age, stale = cr.age_and_staleness("2026-07-07T10:00:00", "2026-07-09T10:00:00")
    assert age == "2d" and stale is False

def test_stale_past_threshold():
    age, stale = cr.age_and_staleness("2026-04-01T10:00:00", "2026-07-09T10:00:00", stale_days=90)
    assert stale is True

def test_months_formatting():
    age, _ = cr.age_and_staleness("2026-04-09T10:00:00", "2026-07-09T10:00:00")
    assert age.endswith("mo")

def test_unparseable_ts_is_stale():
    age, stale = cr.age_and_staleness("garbage", "2026-07-09T10:00:00")
    assert age == "unknown" and stale is True

def test_offset_aware_ts_parses():
    age, stale = cr.age_and_staleness("2026-07-08T10:00:00-07:00", "2026-07-09T17:00:00+00:00")
    assert stale is False  # ~1 day apart

def _e(id, salience, ts, status="tentative"):
    return {"id": id, "salience": salience, "ts": ts, "status": status,
            "subject": id, "intent": "i", "criterion": "c"}

def test_under_cap_keeps_all():
    es = [_e("a", 3, "2026-07-01"), _e("b", 4, "2026-07-02")]
    kept, evicted = cr.enforce_cap(es, cap=5)
    assert len(kept) == 2 and evicted == []

def test_evicts_lowest_salience_first():
    es = [_e("hi", 5, "2026-07-01"), _e("lo", 1, "2026-07-02")]
    kept, evicted = cr.enforce_cap(es, cap=1)
    assert [k["id"] for k in kept] == ["hi"] and [e["id"] for e in evicted] == ["lo"]

def test_tie_salience_evicts_oldest():
    es = [_e("old", 3, "2026-07-01"), _e("new", 3, "2026-07-05")]
    kept, evicted = cr.enforce_cap(es, cap=1)
    assert kept[0]["id"] == "new" and evicted[0]["id"] == "old"

def test_does_not_mutate_input():
    es = [_e("a", 1, "2026-07-01"), _e("b", 2, "2026-07-02")]
    cr.enforce_cap(es, cap=1)
    assert len(es) == 2

def test_flags_missing_path(tmp_path):
    (tmp_path / "real.py").write_text("x")
    text = "see `src/real.py` and `src/gone.py`"
    # neither 'src/real.py' exists (it's real.py at root) — craft precisely:
    (tmp_path / "src").mkdir(); (tmp_path / "src" / "real.py").write_text("x")
    assert cr.dead_path_scan(text, tmp_path) == ["src/gone.py"]

def test_ignores_urls(tmp_path):
    assert cr.dead_path_scan("visit https://example.com/x/y", tmp_path) == []

def test_empty_when_all_exist(tmp_path):
    (tmp_path / "a").mkdir(); (tmp_path / "a" / "b.md").write_text("x")
    assert cr.dead_path_scan("ref `a/b.md`", tmp_path) == []

def test_dead_path_skips_prose_slash_token_turn(tmp_path):
    assert cr.dead_path_scan("mechanical token/turn measurement", tmp_path) == []

def test_dead_path_skips_prose_slash_and_or(tmp_path):
    assert cr.dead_path_scan("do X and/or Y", tmp_path) == []

def test_dead_path_skips_prose_slash_io(tmp_path):
    assert cr.dead_path_scan("blocked on I/O", tmp_path) == []

def test_dead_path_skips_prose_slash_tcp_ip(tmp_path):
    assert cr.dead_path_scan("runs over TCP/IP", tmp_path) == []

def test_dead_path_still_flags_missing_extension_path(tmp_path):
    (tmp_path / "src").mkdir()
    assert cr.dead_path_scan("see src/gone.py", tmp_path) == ["src/gone.py"]

def test_dead_path_still_skips_existing_extension_path(tmp_path):
    (tmp_path / "a").mkdir(); (tmp_path / "a" / "b.md").write_text("x")
    assert cr.dead_path_scan("ref a/b.md", tmp_path) == []

def test_counts_subjects_and_intents():
    es = [_e("auth", 3, "t"), _e("auth", 3, "t"), _e("cache", 3, "t")]
    r = cr.coverage_report(es)
    assert r["subjects"] == 2 and r["intents"] == 3

def test_excludes_superseded():
    es = [_e("auth", 3, "t"), _e("old", 3, "t", status="superseded")]
    r = cr.coverage_report(es)
    assert r["subjects"] == 1 and r["intents"] == 1

def test_flags_criterion_gap():
    es = [{"id": "1", "subject": "x", "intent": "i", "criterion": "", "status": "tentative", "salience": 3, "ts": "t"}]
    assert cr.coverage_report(es)["gaps"] == ["x"]

def test_active_entries_excludes_pointer_superseded():
    # old entry's id is later pointed to by a newer entry's `supersedes` — old must drop
    # out of the active set even though its own `status` was never flipped to "superseded".
    old = _e("old", 3, "2026-07-01")
    new = _e("new", 3, "2026-07-02")
    new["supersedes"] = "old"
    active = cr.active_entries([old, new])
    assert [e["id"] for e in active] == ["new"]

def test_active_entries_keeps_plain_entry_with_no_supersedes():
    es = [_e("a", 3, "2026-07-01")]
    assert cr.active_entries(es) == es

def test_coverage_report_excludes_pointer_superseded():
    old = _e("auth", 3, "t")
    new = _e("cache", 3, "t")
    new["supersedes"] = "auth"
    r = cr.coverage_report([old, new])
    assert r["subjects"] == 1 and r["intents"] == 1

def test_unknown_cited_ids_flags_bogus_id():
    hot_text = "- onboarding `[deadbeef]` [stated]"
    entries = [_e("a1b2c3d4", 3, "t")]
    assert cr.unknown_cited_ids(hot_text, entries) == ["deadbeef"]

def test_unknown_cited_ids_empty_for_known_id():
    hot_text = "- onboarding `[a1b2c3d4]` [stated]"
    entries = [_e("a1b2c3d4", 3, "t")]
    assert cr.unknown_cited_ids(hot_text, entries) == []

def test_unknown_cited_ids_ignores_provenance_tags():
    hot_text = "- x `[a1b2c3d4]` [stated] [firm] [fresh]"
    entries = [_e("a1b2c3d4", 3, "t")]
    assert cr.unknown_cited_ids(hot_text, entries) == []

import json

def test_write_snapshot_roundtrip(tmp_path):
    p = cr.write_snapshot("hello", tmp_path / "audit", "2026-07-09T14:32:00-07:00")
    assert p.exists()
    data = json.loads(p.read_text())
    assert data["text"] == "hello" and data["ts"].startswith("2026-07-09")
    assert ":" not in p.name  # colon-free filename (portable)

def test_diff_snapshot_detects_change():
    d = cr.diff_snapshot("a\nb\n", "a\nc\n")
    assert any(line.startswith("-b") for line in d) and any(line.startswith("+c") for line in d)

def test_diff_snapshot_identical_empty():
    assert cr.diff_snapshot("x\n", "x\n") == []

def test_diff_snapshot_keeps_hr_content_lines():
    # A markdown rule '---' changed to '===' must survive; the removed '---' content
    # line is emitted as '----' and must NOT be dropped as a diff header.
    d = cr.diff_snapshot("a\n---\n", "a\n===\n")
    assert any(ln == "----" for ln in d), d
    assert any(ln == "+===" for ln in d), d

import subprocess, sys
from pathlib import Path
SCRIPT = str(Path(__file__).parent / "cognition_render.py")

def test_cli_guards_reports(tmp_path):
    # seed a cold log via cognition_log
    import cognition_log as cl
    cl.append_entry({"intent": "effortless onboarding", "subject": "onboarding",
                     "criterion": "no docs"}, root=tmp_path, branch="feat/x",
                    now="2026-07-09T10:00:00", author="v", source="capture")
    hot = tmp_path / "docs" / "cognition.md"
    hot.parent.mkdir(parents=True, exist_ok=True)
    hot.write_text("# Project Cognition\n- onboarding `[x]` see `src/gone.py`\n")
    r = subprocess.run([sys.executable, SCRIPT, "guards", "--hot", str(hot),
                        "--root", str(tmp_path), "--now", "2026-07-09T10:00:00"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    rep = json.loads(r.stdout)
    assert rep["coverage"]["intents"] == 1
    assert "src/gone.py" in rep["dead_paths"]
    assert Path(rep["snapshot"]).exists()

def test_cli_guards_missing_hot_exit2(tmp_path):
    r = subprocess.run([sys.executable, SCRIPT, "guards", "--hot",
                        str(tmp_path / "nope.md"), "--root", str(tmp_path)],
                       capture_output=True, text=True)
    assert r.returncode == 2

def test_cli_guards_reports_unknown_cited_ids(tmp_path):
    # seed a real cold-log entry, then cite it AND a bogus id from the hot doc
    import cognition_log as cl
    rec = cl.append_entry({"intent": "effortless onboarding", "subject": "onboarding",
                           "criterion": "no docs"}, root=tmp_path, branch="feat/x",
                          now="2026-07-09T10:00:00", author="v", source="capture")
    real_id = rec["id"]
    hot = tmp_path / "docs" / "cognition.md"
    hot.parent.mkdir(parents=True, exist_ok=True)
    hot.write_text(
        f"# Project Cognition\n"
        f"- onboarding `[{real_id}]` [stated]\n"
        f"- bogus fact `[deadbeef]` [stated]\n"
    )
    r = subprocess.run([sys.executable, SCRIPT, "guards", "--hot", str(hot),
                        "--root", str(tmp_path), "--now", "2026-07-09T10:00:00"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    rep = json.loads(r.stdout)
    assert rep["unknown_ids"] == ["deadbeef"]
