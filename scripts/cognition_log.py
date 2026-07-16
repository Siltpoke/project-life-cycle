"""Deterministic cognition intent-log helper."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path

REQUIRED = ("intent", "subject", "criterion")
STATUSES = {"tentative", "firm", "superseded"}

def validate_entry(entry: dict) -> list[str]:
    errs: list[str] = []
    for f in REQUIRED:
        v = entry.get(f)
        if not isinstance(v, str) or not v.strip():
            errs.append(f"required field '{f}' missing or empty")
    status = entry.get("status", "tentative")
    if status not in STATUSES:
        errs.append(f"status '{status}' not in {sorted(STATUSES)}")
    sal = entry.get("salience", 3)
    if not isinstance(sal, int) or not (1 <= sal <= 5):
        errs.append("salience must be int 1..5")
    return errs

def _slug(branch: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", branch.lower()).strip("-")

def fragment_path(root, branch: str, day: str) -> Path:
    return Path(root) / "docs" / "cognition-log.d" / f"{day}-{_slug(branch)}.jsonl"

def normalize_entry(entry: dict, *, now: str, author: str, source: str) -> dict:
    out = dict(entry)
    out.setdefault("rejected", None)
    out.setdefault("supersedes", None)
    out["status"] = entry.get("status", "tentative")
    out["salience"] = entry.get("salience", 3)
    out["ts"] = now
    out["author"] = author
    out["source"] = source
    seed = (f'{now}{entry.get("subject","")}{entry.get("intent","")}'
            f'{author}{source}{uuid.uuid4().hex}').encode()
    out["id"] = hashlib.sha256(seed).hexdigest()[:8]
    return out

def append_entry(entry: dict, *, root, branch: str, now: str, author: str, source: str) -> dict:
    errs = validate_entry(entry)
    if errs:
        raise ValueError("; ".join(errs))
    rec = normalize_entry(entry, now=now, author=author, source=source)
    day = now[:10]
    frag = fragment_path(root, branch, day)
    frag.parent.mkdir(parents=True, exist_ok=True)
    with frag.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec

def load_entries(root) -> list[dict]:
    d = Path(root) / "docs" / "cognition-log.d"
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
            if not isinstance(obj, dict):
                continue
            out.append(obj)
    return out

def _tokens(s: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", s.lower()) if len(t) >= 3}

def find_related(subject: str, existing: list[dict]) -> list[dict]:
    want = _tokens(subject)
    sub_l = subject.strip().lower()
    hits = []
    for e in existing:
        if e.get("status") == "superseded":
            continue
        es = str(e.get("subject", ""))
        if es.strip().lower() == sub_l or (want & _tokens(es)):
            hits.append(e)
    return sorted(hits, key=lambda e: e.get("ts", ""), reverse=True)

def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="cognition_log")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("append")
    a.add_argument("--intent", required=True)
    a.add_argument("--subject", required=True)
    a.add_argument("--criterion", required=True)
    a.add_argument("--rejected", default=None)
    a.add_argument("--status", default="tentative")
    a.add_argument("--salience", type=int, default=3)
    a.add_argument("--supersedes", default=None)
    a.add_argument("--quote", dest="verbatim_quote", default="")
    a.add_argument("--branch", default="HEAD")
    a.add_argument("--author", default="unknown")
    a.add_argument("--source", default="capture")
    a.add_argument("--root", default=".")
    ns = p.parse_args(argv)
    entry = {"intent": ns.intent, "subject": ns.subject, "criterion": ns.criterion,
             "rejected": ns.rejected, "status": ns.status, "salience": ns.salience,
             "supersedes": ns.supersedes, "verbatim_quote": ns.verbatim_quote}
    errs = validate_entry(entry)
    if errs:
        print("; ".join(errs), file=sys.stderr)
        return 2
    related = find_related(ns.subject, load_entries(ns.root))
    for r in related:
        print(f"related prior intent [{r.get('id')}] {r.get('subject')}: "
              f"{r.get('intent')} — confirm supersede if this replaces it", file=sys.stderr)
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    rec = append_entry(entry, root=ns.root, branch=ns.branch,
                       now=now, author=ns.author, source=ns.source)
    print(json.dumps(rec, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
