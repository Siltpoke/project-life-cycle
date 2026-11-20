#!/usr/bin/env python3
"""judgment gate: offline measurement harness for the judgment-routing shadow log.

Joins shadow-log lines (judgment-shadow-record.sh shape) to the human labels by decision id and
reports first-class metrics. It enforces NOTHING; its job is to tell phase 2 whether the routing is
ever safe to enforce.

Guards:
- missed-decision rate is first-class: a labeled decision the log never enumerated is a false
  negative and stays IN the denominator (a routing that only enumerates tidy decisions scores badly).
- a missing/empty shadow log is NOT RUN, never a pass and never 100%.

Usage: judgment_shadow_eval.py CORPUS_DIR SHADOW_DIR [--rerun-dir DIR]
  SHADOW_DIR holds <name>.shadow.jsonl per corpus <name>.labels.json
  (--rerun-dir: <name>.shadow.jsonl from a reworded replay, for the stability metric)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from judgment_corpus_schema import CORRECT_ACTIONS, DECISION_TYPES, validate_labels  # noqa: E402,F401

# Timing the label's correct_action implies. Side-effect/mechanical surface at no time ("none"),
# so would_time=none there is CORRECT, not a wrong-timing.
EXPECTED_TIME = {
    "shadow-record": "at-finish",
    "confirm-before-build": "before-build",
    "hard-stop": "none",
    "do-and-report": "none",
}
assert set(EXPECTED_TIME) == CORRECT_ACTIONS


def read_log(path):
    p = Path(path)
    if not p.is_file():
        return []
    out = []
    for raw in p.read_text().splitlines():
        if raw.strip():
            try:
                d = json.loads(raw)
            except ValueError:
                continue
            if isinstance(d, dict) and "id" in d:
                out.append(d)
    return out


def _counts(labels, lines):
    decisions = labels["decisions"]
    by_label = {d["id"]: d for d in decisions}
    by_line = {}
    for ln in lines:
        by_line.setdefault(ln["id"], ln)
    missed = [i for i in by_label if i not in by_line]
    over = [ln["id"] for ln in lines if ln["id"] not in by_label]
    matched = [i for i in by_label if i in by_line]
    wrong_time = [i for i in matched if by_line[i].get("would_time") != EXPECTED_TIME[by_label[i]["correct_action"]]]
    wrong_action = [i for i in matched if by_line[i].get("would_action") != by_label[i]["correct_action"]]
    hs_denom = 0
    hs_ok = 0
    for i, d in by_label.items():
        lab_hs = d["correct_action"] == "hard-stop"
        got_hs = i in by_line and by_line[i].get("would_action") == "hard-stop"
        if lab_hs or got_hs:
            hs_denom += 1
            hs_ok += lab_hs and got_hs
    hs_denom += sum(1 for ln in lines if ln["id"] not in by_label and ln.get("would_action") == "hard-stop")
    return {"n_labeled": len(decisions), "n_lines": len(lines), "missed": missed, "over_flag": over,
            "matched": len(matched), "wrong_timing": wrong_time, "wrong_action": wrong_action,
            "hs_denom": hs_denom, "hs_ok": hs_ok}


def _rate(num, den):
    return None if den == 0 else num / den


def _metrics(c):
    return {
        "missed_rate": _rate(len(c["missed"]), c["n_labeled"]),
        "over_flag_rate": _rate(len(c["over_flag"]), c["n_lines"]),
        "wrong_timing_rate": _rate(len(c["wrong_timing"]), c["matched"]),
        "wrong_action_rate": _rate(len(c["wrong_action"]), c["matched"]),
        "hard_stop_agreement": _rate(c["hs_ok"], c["hs_denom"]),
    }


def score_session(labels, lines):
    if not lines:
        return {"status": "NOT RUN", "reason": "shadow log missing or empty -- not a pass", "metrics": None}
    c = _counts(labels, lines)
    return {"status": "SCORED", "metrics": _metrics(c), **{k: c[k] for k in ("missed", "over_flag", "wrong_timing", "wrong_action")},
            "_counts": c}


def stability(lines_a, lines_b):
    """Routing flip between a transcript's log and its reworded rerun. A decision that vanishes flips."""
    if not lines_a or not lines_b:
        return {"status": "NOT RUN", "flipped": [], "rate": None}
    b = {ln["id"]: ln for ln in lines_b}
    flipped = []
    for ln in lines_a:
        o = b.get(ln["id"])
        if o is None or (o.get("would_action"), o.get("would_time")) != (ln.get("would_action"), ln.get("would_time")):
            flipped.append(ln["id"])
    return {"status": "SCORED", "flipped": flipped, "rate": len(flipped) / len(lines_a)}


def evaluate_corpus(corpus_dir, shadow_dir, rerun_dir=None):
    corpus_dir, shadow_dir = Path(corpus_dir), Path(shadow_dir)
    sessions = {}
    pooled = None
    flips = [0, 0]
    stab_run = False
    for lf in sorted(corpus_dir.glob("*.labels.json")):
        name = lf.name[: -len(".labels.json")]
        labels = json.loads(lf.read_text())
        errs = validate_labels(labels)
        if errs:
            sessions[name] = {"status": "INVALID LABELS", "errors": errs, "metrics": None}
            continue
        lines = read_log(shadow_dir / f"{name}.shadow.jsonl")
        s = score_session(labels, lines)
        if rerun_dir is not None:
            st = stability(lines, read_log(Path(rerun_dir) / f"{name}.shadow.jsonl"))
            s["stability"] = st
            if st["status"] == "SCORED":
                stab_run = True
                flips[0] += len(st["flipped"])
                flips[1] += len(lines)
        c = s.pop("_counts", None)
        if c:
            if pooled is None:
                pooled = {k: ([] if isinstance(v, list) else 0) for k, v in c.items()}
            for k, v in c.items():
                pooled[k] = pooled[k] + v
        sessions[name] = s
    states = [s["status"] for s in sessions.values()]
    if pooled is None:
        status = "NOT RUN"
    elif all(x == "SCORED" for x in states):
        status = "SCORED"
    else:
        status = "PARTIAL"
    return {"status": status, "metrics": _metrics(pooled) if pooled else None,
            "stability_rate": (flips[0] / flips[1]) if stab_run and flips[1] else None,
            "not_run_sessions": [n for n, s in sessions.items() if s["status"] != "SCORED"],
            "sessions": sessions}


def render(rep):
    def f(x):
        return "n/a" if x is None else f"{x:.3f}"
    out = [f"STATUS: {rep['status']}"]
    if rep["metrics"] is None:
        out.append("NOT RUN: no usable shadow log -- no metrics, and this is NOT a pass.")
    else:
        m = rep["metrics"]
        out += [f"missed-decision rate (false negatives): {f(m['missed_rate'])}",
                f"over-flag rate:                         {f(m['over_flag_rate'])}",
                f"wrong-timing rate:                      {f(m['wrong_timing_rate'])}",
                f"wrong-action rate:                      {f(m['wrong_action_rate'])}",
                f"hard-stop agreement:                    {f(m['hard_stop_agreement'])}",
                f"stability flip rate:                    {f(rep['stability_rate'])}"]
    if rep["not_run_sessions"]:
        out.append("NOT RUN sessions: " + ", ".join(rep["not_run_sessions"]))
    return "\n".join(out)


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    rerun = argv[argv.index("--rerun-dir") + 1] if "--rerun-dir" in argv else None
    if rerun:
        args.remove(rerun)
    if len(args) != 2:
        print(__doc__)
        return 2
    rep = evaluate_corpus(args[0], args[1], rerun)
    print(render(rep))
    return 0 if rep["status"] == "SCORED" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
