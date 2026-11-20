"""Label schema + validator for the judgment-recognition evaluation corpus.

Risk is recorded as FACT booleans about the action. A numeric risk score is
rejected on purpose: self-reported scores are untrustworthy ("score laundering").
"""

DECISION_TYPES = {"taste", "product-boundary", "side-effect", "mechanical"}
CORRECT_ACTIONS = {"shadow-record", "confirm-before-build", "hard-stop", "do-and-report"}
RISK_FACTS = ("touches_data_model", "touches_public_api", "destructive", "prod", "remote")
FAILURE_KINDS = {"missed-enumeration", "weak-authorization-claim",
                 "over-asking", "type-misjudged"}
DECISION_KEYS = {"id", "what", "authorization", "risk_facts", "decision_type",
                 "correct_action"}
AUTH_KEYS = {"who", "what", "scope"}
TOP_KEYS = {"decisions", "known_hard_failures", "expect_silent"}
_SCORE_WORDS = ("score", "risk", "severity", "level", "rating")


def _nonempty_str(v):
    return isinstance(v, str) and v.strip() != ""


def _validate_decision(d, i, errs):
    p = f"decisions[{i}]"
    if not isinstance(d, dict):
        errs.append(f"{p}: not an object")
        return None
    for k in d:
        if k not in DECISION_KEYS:
            hint = " (numeric scores are not allowed; use risk_facts booleans)" \
                if any(w in k.lower() for w in _SCORE_WORDS) else ""
            errs.append(f"{p}: unknown key {k!r}{hint}")
    for k in DECISION_KEYS - set(d):
        errs.append(f"{p}: missing {k!r}")
    for k in ("id", "what"):
        if k in d and not _nonempty_str(d[k]):
            errs.append(f"{p}.{k}: must be a non-empty string")
    auth = d.get("authorization")
    if "authorization" in d:
        if not isinstance(auth, dict) or set(auth) != AUTH_KEYS \
                or not all(_nonempty_str(v) for v in auth.values()):
            errs.append(f"{p}.authorization: need exactly {sorted(AUTH_KEYS)} as non-empty strings")
    rf = d.get("risk_facts")
    if "risk_facts" in d:
        if not isinstance(rf, dict):
            errs.append(f"{p}.risk_facts: not an object")
        else:
            for k, v in rf.items():
                if k not in RISK_FACTS:
                    errs.append(f"{p}.risk_facts: unknown fact {k!r} (facts only, no scores)")
                elif type(v) is not bool:
                    errs.append(f"{p}.risk_facts.{k}: must be a boolean, got {v!r}")
            for k in RISK_FACTS:
                if k not in rf:
                    errs.append(f"{p}.risk_facts: missing {k!r}")
    if "decision_type" in d and d["decision_type"] not in DECISION_TYPES:
        errs.append(f"{p}.decision_type: {d['decision_type']!r} not in {sorted(DECISION_TYPES)}")
    if "correct_action" in d and d["correct_action"] not in CORRECT_ACTIONS:
        errs.append(f"{p}.correct_action: {d['correct_action']!r} not in {sorted(CORRECT_ACTIONS)}")
    return d.get("id")


def validate_labels(labels):
    """Return a list of error strings; empty means valid."""
    errs = []
    if not isinstance(labels, dict):
        return ["labels: not an object"]
    for k in labels:
        if k not in TOP_KEYS:
            hint = " (numeric scores are not allowed; use risk_facts booleans)" \
                if any(w in k.lower() for w in _SCORE_WORDS) else ""
            errs.append(f"labels: unknown key {k!r}{hint}")
    if "expect_silent" in labels and type(labels["expect_silent"]) is not bool:
        errs.append("labels.expect_silent: must be a boolean")
    decisions = labels.get("decisions")
    if not isinstance(decisions, list):
        errs.append("decisions: must be a list")
        decisions = []
    ids = []
    for i, d in enumerate(decisions):
        ids.append(_validate_decision(d, i, errs))
    dup = {x for x in ids if x is not None and ids.count(x) > 1}
    if dup:
        errs.append(f"decisions: duplicate ids {sorted(dup)}")
    hf = labels.get("known_hard_failures")
    if not isinstance(hf, list) or not hf:
        errs.append("known_hard_failures: must be a non-empty list")
    else:
        for i, f in enumerate(hf):
            p = f"known_hard_failures[{i}]"
            if not isinstance(f, dict):
                errs.append(f"{p}: not an object")
                continue
            if f.get("kind") not in FAILURE_KINDS:
                errs.append(f"{p}.kind: {f.get('kind')!r} not in {sorted(FAILURE_KINDS)}")
            if f.get("decision_id") not in ids:
                errs.append(f"{p}.decision_id: {f.get('decision_id')!r} matches no decision")
            if not _nonempty_str(f.get("note")):
                errs.append(f"{p}.note: must be a non-empty string")
    return errs
