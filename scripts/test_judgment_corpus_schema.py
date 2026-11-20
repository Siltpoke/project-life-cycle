"""Tests for the judgment-recognition evaluation corpus (the oracle).

Risk is recorded as FACT booleans about the action, never a numeric score.
"""

import copy
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import judgment_corpus_schema as S  # noqa: E402

CORPUS = (pathlib.Path(__file__).parent.parent
          / "skills/project-lifecycle/hooks/fixtures/corpus")

GOOD = {
    "decisions": [{
        "id": "d1",
        "what": "strikethrough style for deleted links",
        "authorization": {"who": "ai-guess", "what": "screenshot shows a deleted link",
                          "scope": "visual style not specified"},
        "risk_facts": {"touches_data_model": False, "touches_public_api": False,
                       "destructive": False, "prod": False, "remote": False},
        "decision_type": "taste",
        "correct_action": "shadow-record",
    }],
    "known_hard_failures": [
        {"kind": "missed-enumeration", "decision_id": "d1", "note": "x"}],
}


def _case(**over):
    c = copy.deepcopy(GOOD)
    c.update(over)
    return c


def test_label_schema_accepts_wellformed():
    assert S.validate_labels(GOOD) == []


def _errs_for(mutate):
    c = copy.deepcopy(GOOD)
    mutate(c)
    return " | ".join(S.validate_labels(c))


def test_rejects_score_field():
    five = dict(GOOD["decisions"][0]["risk_facts"])
    # extra score key alongside otherwise-valid facts
    e = _errs_for(lambda c: c["decisions"][0]["risk_facts"].update(risk=2))
    assert "unknown fact 'risk'" in e and "missing" not in e
    e = _errs_for(lambda c: c["decisions"][0]["risk_facts"].update(severity_score=1))
    assert "unknown fact 'severity_score'" in e
    # score in place of facts
    e = _errs_for(lambda c: c["decisions"][0].update(risk_facts={"risk": 2}))
    assert "unknown fact 'risk'" in e
    # decision-level score
    e = _errs_for(lambda c: c["decisions"][0].update(risk_score=3))
    assert "unknown key 'risk_score'" in e and "numeric scores are not allowed" in e
    # top-level score
    e = _errs_for(lambda c: c.update(risk_score=3))
    assert "unknown key 'risk_score'" in e and "numeric scores are not allowed" in e
    # numeric instead of boolean fact
    e = _errs_for(lambda c: c["decisions"][0]["risk_facts"].update(touches_data_model=2))
    assert "touches_data_model: must be a boolean" in e
    assert five and S.validate_labels(GOOD) == []


def test_expect_silent_must_be_bool():
    assert "expect_silent: must be a boolean" in _errs_for(
        lambda c: c.update(expect_silent=1))
    assert S.validate_labels(_case(expect_silent=True)) == []


def test_requires_known_hard_failures_nonempty():
    assert S.validate_labels(_case(known_hard_failures=[]))
    c = copy.deepcopy(GOOD)
    del c["known_hard_failures"]
    assert S.validate_labels(c)


def test_decision_type_enum_exact():
    assert S.DECISION_TYPES == {"taste", "product-boundary", "side-effect", "mechanical"}
    c = copy.deepcopy(GOOD)
    c["decisions"][0]["decision_type"] = "style"
    assert S.validate_labels(c)


def test_correct_action_enum_and_missing_fact_rejected():
    c = copy.deepcopy(GOOD)
    c["decisions"][0]["correct_action"] = "ask"
    assert S.validate_labels(c)
    c = copy.deepcopy(GOOD)
    del c["decisions"][0]["risk_facts"]["prod"]
    assert S.validate_labels(c)


def test_duplicate_ids_and_dangling_failure_ref_rejected():
    c = copy.deepcopy(GOOD)
    c["decisions"].append(copy.deepcopy(c["decisions"][0]))
    assert S.validate_labels(c)
    c = copy.deepcopy(GOOD)
    c["known_hard_failures"][0]["decision_id"] = "nope"
    assert S.validate_labels(c)


def _cases():
    return sorted(CORPUS.glob("*.labels.json"))


def test_corpus_has_required_cases():
    names = {p.name.replace(".labels.json", "") for p in _cases()}
    assert {"stickies-deleted-link", "learning-layer-data-model"} <= names
    assert len(names) >= 4


def test_every_case_has_transcript_and_valid_labels_and_hard_failure():
    for p in _cases():
        stem = p.name.replace(".labels.json", "")
        t = CORPUS / f"{stem}.transcript.jsonl"
        assert t.is_file(), f"missing transcript for {stem}"
        for line in t.read_text(encoding="utf-8").splitlines():
            assert json.loads(line)["role"] in {"user", "assistant", "tool"}
        labels = json.loads(p.read_text(encoding="utf-8"))
        assert S.validate_labels(labels) == [], (stem, S.validate_labels(labels))
        assert labels["known_hard_failures"], stem


def test_stickies_english_copy_is_missed_enumeration_hard_failure():
    labels = json.loads((CORPUS / "stickies-deleted-link.labels.json").read_text())
    ids = {d["id"]: d for d in labels["decisions"]}
    assert len(ids) == 4  # four named decisions only; no invented ones
    hits = [f for f in labels["known_hard_failures"]
            if f["kind"] == "missed-enumeration"
            and "english" in ids[f["decision_id"]]["what"].lower()]
    assert hits


def test_learning_layer_data_model_labels():
    labels = json.loads((CORPUS / "learning-layer-data-model.labels.json").read_text())
    dm = [d for d in labels["decisions"] if d["risk_facts"]["touches_data_model"]]
    assert dm and dm[0]["decision_type"] == "product-boundary"


def test_corpus_has_both_negatives():
    kinds = set()
    for p in _cases():
        labels = json.loads(p.read_text())
        ds = labels["decisions"]
        if ds and all(d["decision_type"] == "mechanical" for d in ds):
            kinds.add("mechanical-only")
        if labels.get("expect_silent"):
            kinds.add("silent")
    assert kinds == {"mechanical-only", "silent"}


def test_corpus_files_have_no_cjk():
    cjk = re.compile("[" + "".join(chr(c) for c in (0x3000, 0x2d, 0x303f, 0x3400, 0x2d, 0x9fff, 0xff00, 0x2d, 0xffef)) + "]")
    files = list(CORPUS.glob("*")) + [pathlib.Path(S.__file__), pathlib.Path(__file__)]
    for f in files:
        assert not cjk.search(f.read_text(encoding="utf-8")), f
