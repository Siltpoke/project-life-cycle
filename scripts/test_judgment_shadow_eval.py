"""judgment gate: measurement harness -- scores shadow-log routing against human labels."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from judgment_corpus_schema import CORRECT_ACTIONS, DECISION_TYPES  # noqa: E402  (enums imported, never redefined)
import judgment_shadow_eval as ev  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "skills/project-lifecycle/hooks/fixtures/corpus"


def label(i, dt="taste", action="shadow-record"):
    return {"id": i, "what": "w", "authorization": {"who": "ai-guess", "what": "x", "scope": "y"},
            "risk_facts": {k: False for k in ("touches_data_model", "touches_public_api", "destructive", "prod", "remote")},
            "decision_type": dt, "correct_action": action}


def line(i, dt="taste", action="shadow-record", time="at-finish"):
    return {"id": i, "what": "w", "authorization_tier": "delegated", "decision_type": dt,
            "would_action": action, "would_time": time}


def labels(*ds):
    return {"decisions": list(ds), "known_hard_failures": [{"kind": "over-asking", "decision_id": ds[0]["id"], "note": "n"}]}


def test_enums_are_imported_not_redefined():
    assert ev.DECISION_TYPES is DECISION_TYPES
    assert ev.CORRECT_ACTIONS is CORRECT_ACTIONS


def test_missed_decision_is_false_negative():
    # routing only enumerates the small tidy decision; the big one is silently missing
    r = ev.score_session(labels(label("small"), label("big", "product-boundary", "confirm-before-build")),
                         [line("small")])
    assert r["status"] == "SCORED"
    assert r["missed"] == ["big"]
    assert r["metrics"]["missed_rate"] == 0.5  # counted against, denominator includes it


def test_tidy_only_routing_scores_badly_on_missed():
    ls = labels(*[label(f"d{i}") for i in range(4)])
    r = ev.score_session(ls, [line("d0")])
    assert r["metrics"]["missed_rate"] == 0.75


def test_over_flag_counted():
    r = ev.score_session(labels(label("a")), [line("a"), line("ghost")])
    assert r["over_flag"] == ["ghost"]
    assert r["metrics"]["over_flag_rate"] == 0.5


def test_wrong_timing_counted():
    r = ev.score_session(labels(label("a", "product-boundary", "confirm-before-build")),
                         [line("a", "product-boundary", "confirm-before-build", "at-finish")])
    assert r["wrong_timing"] == ["a"]
    assert r["metrics"]["wrong_timing_rate"] == 1.0


def test_none_time_for_side_effect_and_mechanical_is_not_wrong_timing():
    r = ev.score_session(labels(label("m", "mechanical", "do-and-report"), label("s", "side-effect", "hard-stop")),
                         [line("m", "mechanical", "do-and-report", "none"), line("s", "side-effect", "hard-stop", "none")])
    assert r["wrong_timing"] == []
    assert r["metrics"]["wrong_timing_rate"] == 0.0


def test_hard_stop_agreement():
    ls = labels(label("s", "side-effect", "hard-stop"), label("t"))
    good = ev.score_session(ls, [line("s", "side-effect", "hard-stop", "none"), line("t")])
    assert good["metrics"]["hard_stop_agreement"] == 1.0
    bad = ev.score_session(ls, [line("s", "mechanical", "do-and-report", "none"), line("t")])
    assert bad["metrics"]["hard_stop_agreement"] < 1.0
    over = ev.score_session(ls, [line("s", "side-effect", "hard-stop", "none"), line("t", "side-effect", "hard-stop", "none")])
    assert over["metrics"]["hard_stop_agreement"] < 1.0


def test_hard_stop_missed_is_disagreement():
    ls = labels(label("s", "side-effect", "hard-stop"))
    r = ev.score_session(ls, [line("other")])
    assert r["metrics"]["hard_stop_agreement"] == 0.0


def test_missing_shadow_log_is_not_run_not_pass(tmp_path):
    (tmp_path / "x.labels.json").write_text(json.dumps(labels(label("a"))))
    rep = ev.evaluate_corpus(tmp_path, tmp_path / "nologs")
    assert rep["status"] == "NOT RUN"
    assert rep["metrics"] is None
    assert "100" not in json.dumps(rep["metrics"])


def test_empty_shadow_log_is_not_run(tmp_path):
    (tmp_path / "x.labels.json").write_text(json.dumps(labels(label("a"))))
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "x.shadow.jsonl").write_text("")
    rep = ev.evaluate_corpus(tmp_path, logs)
    assert rep["status"] == "NOT RUN"
    assert rep["sessions"]["x"]["status"] == "NOT RUN"


def test_partial_when_some_sessions_have_no_log(tmp_path):
    for n in ("a", "b"):
        (tmp_path / f"{n}.labels.json").write_text(json.dumps(labels(label("d"))))
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "a.shadow.jsonl").write_text(json.dumps(line("d")) + "\n")
    rep = ev.evaluate_corpus(tmp_path, logs)
    assert rep["status"] == "PARTIAL"
    assert rep["sessions"]["b"]["status"] == "NOT RUN"
    assert rep["metrics"]["missed_rate"] == 0.0


def test_aggregate_pools_counts_not_averages(tmp_path):
    (tmp_path / "a.labels.json").write_text(json.dumps(labels(label("d"))))
    (tmp_path / "b.labels.json").write_text(json.dumps(labels(*[label(f"e{i}") for i in range(3)])))
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "a.shadow.jsonl").write_text(json.dumps(line("d")) + "\n")
    (logs / "b.shadow.jsonl").write_text(json.dumps(line("e0")) + "\n")
    rep = ev.evaluate_corpus(tmp_path, logs)
    assert rep["metrics"]["missed_rate"] == 2 / 4


def test_stability_flip_detected():
    a = [line("x", "taste", "shadow-record", "at-finish")]
    same = ev.stability(a, [line("x")])
    assert same["flipped"] == [] and same["rate"] == 0.0
    flip = ev.stability(a, [line("x", "product-boundary", "confirm-before-build", "before-build")])
    assert flip["flipped"] == ["x"] and flip["rate"] == 1.0


def test_stability_decision_vanishing_counts_as_flip():
    assert ev.stability([line("x")], [line("y")])["flipped"] == ["x"]


def test_stability_not_run_without_both_logs():
    assert ev.stability([], [line("x")])["status"] == "NOT RUN"


def test_real_corpus_with_no_logs_is_not_run():
    rep = ev.evaluate_corpus(CORPUS, CORPUS / "does-not-exist")
    assert rep["status"] == "NOT RUN"
    assert len(rep["sessions"]) >= 4


def test_oracle_log_from_real_labels_scores_perfect_on_real_corpus(tmp_path):
    # harness sanity only (labels -> ideal log), NOT a routing baseline
    for f in CORPUS.glob("*.labels.json"):
        ls = json.loads(f.read_text())
        out = [line(d["id"], d["decision_type"], d["correct_action"], ev.EXPECTED_TIME[d["correct_action"]])
               for d in ls["decisions"]]
        (tmp_path / f.name.replace(".labels.json", ".shadow.jsonl")).write_text("\n".join(json.dumps(x) for x in out) + "\n")
    rep = ev.evaluate_corpus(CORPUS, tmp_path)
    m = rep["metrics"]
    assert rep["status"] == "SCORED"
    assert (m["missed_rate"], m["over_flag_rate"], m["wrong_timing_rate"]) == (0.0, 0.0, 0.0)
    # the real corpus has no hard-stop labels: agreement is n/a (None), not a fabricated 1.0
    assert m["hard_stop_agreement"] is None
