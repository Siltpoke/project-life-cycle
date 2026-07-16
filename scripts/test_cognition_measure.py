import cognition_measure as cm

def test_fragment_path_shape(tmp_path):
    p = cm.measure_fragment_path(tmp_path, "feat/cognition-measure", "2026-07-10")
    assert p.name == "2026-07-10-feat-cognition-measure.jsonl"
    assert p.parent.name == "cognition-measure.d"

def test_load_measures_empty(tmp_path):
    assert cm.load_measures(tmp_path) == []

def test_load_measures_skips_malformed(tmp_path):
    d = tmp_path / "docs" / "cognition-measure.d"
    d.mkdir(parents=True)
    (d / "2026-07-10-x.jsonl").write_text('{"milestone":"a","ts":"t"}\n\nnot-json\n[1,2]\n')
    rows = cm.load_measures(tmp_path)
    assert len(rows) == 1 and rows[0]["milestone"] == "a"

def _re(ts, source="reexplain"):
    return {"source": source, "ts": ts, "subject": "s", "intent": "i"}

def test_reexplain_counts_only_reexplain_source():
    es = [_re("2026-07-10T01:00:00"), _re("2026-07-10T02:00:00", source="capture")]
    assert cm.reexplain_count(es, since_ts=None, until_ts="2026-07-10T09:00:00") == 1

def test_reexplain_window_excludes_before_since():
    es = [_re("2026-07-09T10:00:00"), _re("2026-07-10T10:00:00")]
    assert cm.reexplain_count(es, since_ts="2026-07-10T00:00:00", until_ts="2026-07-10T23:00:00") == 1

def test_reexplain_window_excludes_after_until():
    es = [_re("2026-07-10T10:00:00"), _re("2026-07-11T10:00:00")]
    assert cm.reexplain_count(es, since_ts=None, until_ts="2026-07-10T23:00:00") == 1

def test_record_row_derives_and_appends(tmp_path):
    import cognition_log as cl
    # one reexplain-tagged entry + one plain capture in the cold log
    cl.append_entry({"intent": "re-said auth", "subject": "auth", "criterion": "bar"},
                    root=tmp_path, branch="feat/x", now="2026-07-10T05:00:00",
                    author="v", source="reexplain")
    cl.append_entry({"intent": "why", "subject": "cache", "criterion": "bar"},
                    root=tmp_path, branch="feat/x", now="2026-07-10T06:00:00",
                    author="v", source="capture")
    row = cm.record_row(tmp_path, milestone="feat/x", branch="feat/x",
                        now="2026-07-10T09:00:00", turns=12, tokens_est=90000,
                        cognition_loaded=True, note="")
    assert row["reexplain_count"] == 1
    assert row["cognition_intents"] == 2  # both active (neither superseded)
    assert row["turns"] == 12 and row["tokens_est"] == 90000
    assert row["cognition_loaded"] is True and row["milestone"] == "feat/x"
    # persisted
    rows = cm.load_measures(tmp_path)
    assert len(rows) == 1 and rows[0]["ts"] == "2026-07-10T09:00:00"

def test_record_row_window_since_last_measure(tmp_path):
    import cognition_log as cl
    # a reexplain BEFORE the first measure row must not be counted by the second
    cl.append_entry({"intent": "old re", "subject": "a", "criterion": "b"},
                    root=tmp_path, branch="feat/x", now="2026-07-10T01:00:00",
                    author="v", source="reexplain")
    cm.record_row(tmp_path, milestone="m1", branch="feat/x", now="2026-07-10T02:00:00",
                  turns=None, tokens_est=None, cognition_loaded=True)
    cl.append_entry({"intent": "new re", "subject": "c", "criterion": "d"},
                    root=tmp_path, branch="feat/x", now="2026-07-10T03:00:00",
                    author="v", source="reexplain")
    row2 = cm.record_row(tmp_path, milestone="m2", branch="feat/x", now="2026-07-10T04:00:00",
                         turns=None, tokens_est=None, cognition_loaded=True)
    assert row2["reexplain_count"] == 1  # only the one after m1's ts

def test_record_row_tolerates_null_turns(tmp_path):
    row = cm.record_row(tmp_path, milestone="m", branch="b", now="2026-07-10T09:00:00",
                        turns=None, tokens_est=None, cognition_loaded=False)
    assert row["turns"] is None and row["tokens_est"] is None
    assert row["reexplain_count"] == 0 and row["cognition_intents"] == 0

def _row(ts, reex, turns, loaded=True):
    return {"milestone": "m", "ts": ts, "turns": turns, "tokens_est": None,
            "cognition_loaded": loaded, "cognition_intents": 3, "reexplain_count": reex, "note": ""}

def test_report_has_honesty_banner_and_lines():
    out = cm.report([_row("2026-07-10T01:00:00", 2, 10)])
    assert "observational" in out and "milestone" in out.lower()

def test_trend_directions():
    assert cm._trend([3, 2, 1]) == "down"
    assert cm._trend([1, 5]) == "up"
    assert cm._trend([2, 2]) == "flat"
    assert cm._trend([None, 1]) == "flat"  # <2 numerics

def test_trend_robust_to_equal_endpoints_middle_dip():
    # endpoints equal (3==3) but the body sits lower → half-vs-half reads "down"
    assert cm._trend([3, 1, 1, 1, 3]) == "down"

def test_decision_keep_measuring_under_5():
    rows = [_row(f"2026-07-1{i}T00:00:00", 1, 10) for i in range(3)]
    assert "KEEP MEASURING" in cm.report(rows)

def test_decision_justified_when_reexplain_down_efficiency_flat():
    rows = [_row(f"2026-07-0{i}T00:00:00", 5 - i, 10) for i in range(1, 6)]  # reex 4,3,2,1,0; turns flat 10
    out = cm.report(rows)
    assert "Phase 2 JUSTIFIED" in out

def test_decision_stop_when_reexplain_not_falling():
    rows = [_row(f"2026-07-0{i}T00:00:00", 3, 10) for i in range(1, 6)]  # reex flat
    out = cm.report(rows)
    assert "STOP" in out

def test_last_narrows_display_only_not_decision():
    # 5 loaded rows, reexplain trending down (4,3,2,1,0) → full-set decision is JUSTIFIED.
    rows = [_row(f"2026-07-0{i}T00:00:00", 5 - i, 10) for i in range(1, 6)]
    out = cm.report(rows, last=1)
    assert "JUSTIFIED" in out, f"--last must not starve the decision, got: {out}"
    assert "KEEP MEASURING" not in out
    # only 1 per-row line shown (lines starting with "- ")
    row_lines = [ln for ln in out.splitlines() if ln.startswith("- ")]
    assert len(row_lines) == 1

def test_decision_stop_when_tokens_inflate():
    # Reexplain trending DOWN, turns FLAT, but tokens_est trending UP → decision STOP
    rows = [{"milestone": "m", "ts": f"2026-07-0{i}T00:00:00", "turns": 10,
             "tokens_est": i * 5000, "cognition_loaded": True,
             "cognition_intents": 3, "reexplain_count": 6 - i, "note": ""}
            for i in range(1, 6)]  # reex 5..1 (down), turns flat (10), tokens_est 5k..25k (up)
    out = cm.report(rows)
    assert "STOP" in out, f"Expected STOP decision but got: {out}"


import subprocess, sys, json
from pathlib import Path
MSCRIPT = str(Path(__file__).parent / "cognition_measure.py")

def test_cli_record_then_report(tmp_path):
    r = subprocess.run([sys.executable, MSCRIPT, "record", "--milestone", "feat/x",
                        "--root", str(tmp_path), "--branch", "feat/x",
                        "--turns", "10", "--cognition-loaded", "true",
                        "--now", "2026-07-10T09:00:00"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    row = json.loads(r.stdout)
    assert row["milestone"] == "feat/x" and row["turns"] == 10 and row["cognition_loaded"] is True
    rep = subprocess.run([sys.executable, MSCRIPT, "report", "--root", str(tmp_path)],
                         capture_output=True, text=True)
    assert rep.returncode == 0
    assert "feat/x" in rep.stdout and "KEEP MEASURING" in rep.stdout

def test_cli_record_requires_cognition_loaded(tmp_path):
    r = subprocess.run([sys.executable, MSCRIPT, "record", "--milestone", "m",
                        "--root", str(tmp_path)], capture_output=True, text=True)
    assert r.returncode == 2  # argparse: missing required --cognition-loaded
