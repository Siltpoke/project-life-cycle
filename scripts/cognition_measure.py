"""Deterministic cognition measurement instrument. No LLM."""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

import cognition_log
import cognition_render


def _slug(branch: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", branch.lower()).strip("-")


def measure_fragment_path(root, branch: str, day: str) -> Path:
    return Path(root) / "docs" / "cognition-measure.d" / f"{day}-{_slug(branch)}.jsonl"


def load_measures(root) -> list[dict]:
    d = Path(root) / "docs" / "cognition-measure.d"
    if not d.is_dir():
        return []
    out: list[dict] = []
    for frag in sorted(d.glob("*.jsonl")):
        for line in frag.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                out.append(obj)
    return out


def reexplain_count(entries: list[dict], *, since_ts: str | None, until_ts: str) -> int:
    n = 0
    for e in entries:
        if e.get("source") != "reexplain":
            continue
        ts = e.get("ts", "")
        if ts > until_ts:
            continue
        if since_ts is not None and ts <= since_ts:
            continue
        n += 1
    return n


def record_row(root, *, milestone: str, branch: str, now: str,
               turns: int | None, tokens_est: int | None,
               cognition_loaded: bool, note: str = "") -> dict:
    entries = cognition_log.load_entries(root)
    prior = load_measures(root)
    last_ts = max((m.get("ts", "") for m in prior), default="") or None
    reex = reexplain_count(entries, since_ts=last_ts, until_ts=now)
    intents = len(cognition_render.active_entries(entries))
    row = {
        "milestone": milestone, "ts": now,
        "turns": turns, "tokens_est": tokens_est,
        "cognition_loaded": bool(cognition_loaded),
        "cognition_intents": intents,
        "reexplain_count": reex, "note": note,
    }
    frag = measure_fragment_path(root, branch, now[:10])
    frag.parent.mkdir(parents=True, exist_ok=True)
    with frag.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


HONESTY = ("observational, not controlled; small N; turns/tokens_est are self-reported "
           "estimates; cognition_loaded is self-reported.")


def _trend(vals) -> str:
    nums = [v for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if len(nums) < 2:
        return "flat"
    h = len(nums) // 2
    first = sum(nums[:h]) / h
    second = sum(nums[h:]) / (len(nums) - h)
    if second < first:
        return "down"
    if second > first:
        return "up"
    return "flat"


def _decision_hint(rows: list[dict]) -> str:
    loaded = [r for r in rows if r.get("cognition_loaded")]
    if len(loaded) < 5:
        return (f"decision: KEEP MEASURING — {len(loaded)}/5+ milestones with cognition loaded "
                "(need ~5-8 before deciding Phase 2).")
    reex = _trend([r.get("reexplain_count") for r in loaded])
    turns = _trend([r.get("turns") for r in loaded])
    tokens = _trend([r.get("tokens_est") for r in loaded])
    if reex == "down" and turns != "up" and tokens != "up":
        return "decision: Phase 2 JUSTIFIED (data) — reexplain trend down, efficiency not inflated."
    return ("decision: STOP / do not build Phase 2 — reexplain not falling or efficiency inflated "
            "(Markus Sandelin: memory is overhead when it doesn't pay).")


def report(rows: list[dict], *, last: int | None = None) -> str:
    rows = sorted(rows, key=lambda r: r.get("ts", ""))
    hint = _decision_hint(rows)  # decision over the FULL set, always
    shown = rows[-last:] if last else rows
    lines = [f"# cognition measurement — {len(rows)} milestone(s)",
             f"(honesty: {HONESTY})", ""]
    for r in shown:
        lines.append(
            f"- {str(r.get('ts', '?'))[:10]} {r.get('milestone', '?')}: "
            f"reexplain={r.get('reexplain_count', '?')} turns={r.get('turns')} "
            f"tokens_est={r.get('tokens_est')} loaded={r.get('cognition_loaded')} "
            f"intents={r.get('cognition_intents')}")
    return "\n".join(lines + ["", hint])


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="cognition_measure")
    sub = p.add_subparsers(dest="cmd", required=True)

    rec = sub.add_parser("record")
    rec.add_argument("--milestone", required=True)
    rec.add_argument("--root", required=True)
    rec.add_argument("--branch", default="HEAD")
    rec.add_argument("--turns", type=int, default=None)
    rec.add_argument("--tokens-est", dest="tokens_est", type=int, default=None)
    rec.add_argument("--cognition-loaded", dest="cognition_loaded",
                     required=True, choices=["true", "false"])
    rec.add_argument("--note", default="")
    rec.add_argument("--now", default=None)

    rep = sub.add_parser("report")
    rep.add_argument("--root", required=True)
    rep.add_argument("--last", type=int, default=None)

    ns = p.parse_args(argv)
    if ns.cmd == "record":
        now = ns.now or datetime.now().astimezone().isoformat(timespec="seconds")
        row = record_row(ns.root, milestone=ns.milestone, branch=ns.branch, now=now,
                         turns=ns.turns, tokens_est=ns.tokens_est,
                         cognition_loaded=(ns.cognition_loaded == "true"), note=ns.note)
        print(json.dumps(row, ensure_ascii=False))
        return 0
    if ns.cmd == "report":
        print(report(load_measures(ns.root), last=ns.last))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
