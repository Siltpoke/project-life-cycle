"""Deterministic guards for the hot cognition doc. No LLM."""
from __future__ import annotations
from datetime import datetime
import re
import json
import difflib
import argparse
import sys
from pathlib import Path
import cognition_log

_PATH_RE = re.compile(r"[\w.\-/]+/[\w.\-/]+")

def _parse(ts: str):
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None

def age_and_staleness(ts: str, now: str, stale_days: int = 90) -> tuple[str, bool]:
    t, n = _parse(ts), _parse(now)
    if t is None or n is None:
        return ("unknown", True)
    if t.tzinfo is None and n.tzinfo is not None:
        n = n.replace(tzinfo=None)
    if t.tzinfo is not None and n.tzinfo is None:
        t = t.replace(tzinfo=None)
    days = (n - t).days
    if days >= 60:
        age = f"{days // 30}mo"
    else:
        age = f"{days}d"
    return (age, days >= stale_days)

def enforce_cap(entries: list[dict], cap: int) -> tuple[list[dict], list[dict]]:
    # rank best-first: high salience, then newest ts
    ranked = sorted(entries, key=lambda e: (e.get("salience", 3), e.get("ts", "")), reverse=True)
    kept = ranked[:cap]
    evicted = ranked[cap:]
    return (kept, evicted)

def dead_path_scan(text: str, root) -> list[str]:
    root = Path(root)
    dead = set()
    for m in _PATH_RE.findall(text):
        if "://" in m or m.startswith("http") or m.startswith("//"):
            continue
        tok = m.strip("`.,)")
        if "/" not in tok:
            continue
        if not _EXT_RE.search(tok.rsplit("/", 1)[-1]):
            continue
        if not (root / tok).exists():
            dead.add(tok)
    return sorted(dead)

_EXT_RE = re.compile(r"\.[A-Za-z0-9]{1,8}$")

_CITED_ID_RE = re.compile(r"\[([0-9a-f]{8})\]")

def active_entries(entries: list[dict]) -> list[dict]:
    """Entries that are current: not self-marked superseded, and not pointed to by a
    later entry's `supersedes` (Phase 1 supersession is pointer-based — the old entry's
    own `status` is left unchanged on disk, so status alone misses the pointer chain)."""
    superseded_ids = {e.get("supersedes") for e in entries if e.get("supersedes")}
    return [e for e in entries
            if e.get("status") != "superseded" and e.get("id") not in superseded_ids]

def unknown_cited_ids(hot_text: str, entries: list[dict]) -> list[str]:
    """`[<id>]` source pointers in the hot doc that don't resolve to a real cold-log
    entry id. Exactly 8 lowercase hex chars, so provenance tags like `[stated]`/
    `[firm]`/`[fresh]` never match. Warn-only signal — callers still exit 0."""
    known = {e.get("id") for e in entries}
    cited = {m for m in _CITED_ID_RE.findall(hot_text)}
    return sorted(cited - known)

def coverage_report(entries: list[dict]) -> dict:
    active = active_entries(entries)
    subjects = {e.get("subject", "") for e in active}
    by_subj: dict[str, list[dict]] = {}
    for e in active:
        by_subj.setdefault(e.get("subject", ""), []).append(e)
    gaps = sorted(s for s, es in by_subj.items()
                  if not any((e.get("criterion") or "").strip() for e in es))
    return {"subjects": len(subjects), "intents": len(active), "gaps": gaps}

def write_snapshot(hot_text: str, audit_dir, now: str) -> Path:
    d = Path(audit_dir)
    d.mkdir(parents=True, exist_ok=True)
    safe = now.replace(":", "-")
    p = d / f"{safe}.json"
    p.write_text(json.dumps({"ts": now, "text": hot_text}, ensure_ascii=False), encoding="utf-8")
    return p

def diff_snapshot(prev_text: str, cur_text: str) -> list[str]:
    diff = difflib.unified_diff(prev_text.splitlines(), cur_text.splitlines(), lineterm="")
    out = []
    for ln in diff:
        # Drop only unified-diff headers. With lineterm="" and no fromfile/tofile,
        # the file headers are exactly "--- "/"+++ " (trailing space, empty name).
        # A broad startswith("---"/"+++") would swallow content lines like a markdown
        # rule "---" (emitted as "----" after the removal marker) — killing the audit.
        if ln.startswith("@@") or ln in ("--- ", "+++ "):
            continue
        out.append(ln)
    return out

def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="cognition_render")
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("guards")
    g.add_argument("--hot", required=True)
    g.add_argument("--root", required=True)
    g.add_argument("--cap", type=int, default=120)
    g.add_argument("--now", default=None)
    ns = p.parse_args(argv)
    hot = Path(ns.hot)
    if not hot.exists():
        print(f"hot doc not found: {hot}", file=sys.stderr)
        return 2
    now = ns.now or datetime.now().astimezone().isoformat(timespec="seconds")
    entries = cognition_log.load_entries(ns.root)
    active = active_entries(entries)
    cov = coverage_report(entries)
    hot_text = hot.read_text(encoding="utf-8")
    dead = dead_path_scan(hot_text, ns.root)
    unknown_ids = unknown_cited_ids(hot_text, entries)
    kept, evicted = enforce_cap(active, ns.cap)
    stale = [e.get("id") for e in active if age_and_staleness(e.get("ts", ""), now)[1]]
    snap = write_snapshot(hot_text,
                          Path(ns.root) / "docs" / ".cognition-audit", now)
    report = {"coverage": cov, "dead_paths": dead,
              "evicted_ids": [e.get("id") for e in evicted],
              "stale_ids": stale, "unknown_ids": unknown_ids, "snapshot": str(snap)}
    print(json.dumps(report, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
