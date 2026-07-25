#!/usr/bin/env python3
"""Machine-local registry mapping CLI-agent conversations to their resume ids.

Multi-family: Claude Code, Codex, and future agents (Antigravity/Qoder). Pure
stdlib. Two entry points (see ``main``): ``upsert`` (Trigger A, skill-moment)
and ``capture-hook`` (Trigger B, SessionEnd). Writes ``docs/agent-chats-index.md``
as JSONL (one record per line, no header) — gitignored, never committed.

Deliberately does NOT store cost / tokens: that belongs to a companion
analytics tool. External tools join on ``resume_id``; keeping cost out avoids a
second, drifting ledger.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

# Shared multi-family transcript + git primitives (a prior extraction). Aliased to
# the historical private names so the rest of this module is unchanged.
from transcript_util import (
    iter_events as _iter_events,
    now_stamp as _now,
    resolve_git_fields,
    truncate as _truncate,
    turn_role as _turn_role,
    turn_text as _turn_text,
)

REPO = Path(__file__).resolve().parent.parent
REGISTRY = REPO / "docs" / "agent-chats-index.md"

# Codex rollout envelope types — mirror src/router/codex-transcript.ts.
_CODEX_ENVELOPE_TYPES = frozenset(
    {"session_meta", "turn_context", "response_item", "event_msg"}
)


@dataclass
class ChatRecord:
    resume_id: str = ""
    family: str = "claude"
    model: str = ""
    intensity: str = ""
    repo: str = ""
    branch: str = ""
    worktree: str = ""
    head_sha: str = ""
    dirty: bool = False
    topic: str = ""
    tags: list[str] = field(default_factory=list)
    transcript_path: str = ""
    capture_source: str = ""
    created_at: str = ""
    last_updated: str = ""
    msg_count: int = 0


def record_to_dict(rec: ChatRecord) -> dict:
    d = asdict(rec)
    d["tags"] = [str(t) for t in rec.tags]
    d["dirty"] = bool(rec.dirty)
    d["msg_count"] = int(rec.msg_count)
    return d


def record_from_dict(obj: object) -> ChatRecord:
    if not isinstance(obj, dict):
        raise ValueError("record must be a JSON object")
    return ChatRecord(
        resume_id=str(obj.get("resume_id", "")),
        family=str(obj.get("family", "") or "claude"),
        model=str(obj.get("model", "")),
        intensity=str(obj.get("intensity", "")),
        repo=str(obj.get("repo", "")),
        branch=str(obj.get("branch", "")),
        worktree=str(obj.get("worktree", "")),
        head_sha=str(obj.get("head_sha", "")),
        dirty=bool(obj.get("dirty", False)),
        topic=str(obj.get("topic", "")),
        tags=[str(t) for t in obj.get("tags", []) if str(t).strip()],
        transcript_path=str(obj.get("transcript_path", "")),
        capture_source=str(obj.get("capture_source", "")),
        created_at=str(obj.get("created_at", "")),
        last_updated=str(obj.get("last_updated", "")),
        msg_count=int(obj.get("msg_count", 0) or 0),
    )


def parse_lines(text: str) -> list[ChatRecord]:
    records: list[ChatRecord] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        try:
            records.append(record_from_dict(obj))
        except (ValueError, TypeError):
            continue
    return records


def render_lines(records: list[ChatRecord]) -> str:
    # Stable sort: first by family and resume_id (ascending), then by last_updated (descending).
    # This ensures secondary tiebreak keys are ascending when last_updated is equal.
    ordered = sorted(records, key=lambda r: (r.family, r.resume_id))
    ordered = sorted(ordered, key=lambda r: r.last_updated, reverse=True)
    return "".join(
        json.dumps(record_to_dict(r), ensure_ascii=False, sort_keys=True) + "\n"
        for r in ordered
    )


def _dedup_key(rec: ChatRecord) -> tuple[str, str]:
    fam = rec.family.strip() or "claude"
    rid = rec.resume_id.strip()
    if not rid or rid == fam:  # blank or Codex's literal "codex" fallback
        rid = rec.transcript_path.strip()
    return (fam, rid)


def _merge_records(existing: ChatRecord, new: ChatRecord) -> ChatRecord:
    """Merge an incoming record into the existing one sharing the same dedup key.

    Default is a full replace (incoming wins on every field except created_at,
    which always keeps the earliest value). The one exception: when a hook
    capture (Trigger B, mechanical) lands over a skill capture (Trigger A,
    LLM-curated), the curated fields (topic/tags/intensity) and the "skill"
    provenance marker are preserved from the existing record whenever they are
    non-empty — everything else (including msg_count/model/git fields) still
    takes the fresh incoming value.
    """
    merged = replace(new, created_at=existing.created_at or new.created_at, tags=list(new.tags))
    if new.capture_source == "hook" and existing.capture_source == "skill":
        merged = replace(
            merged,
            topic=existing.topic or merged.topic,
            tags=list(existing.tags) if existing.tags else merged.tags,
            intensity=existing.intensity or merged.intensity,
            capture_source=existing.capture_source,
        )
    return merged


def upsert_record(records: list[ChatRecord], new: ChatRecord) -> list[ChatRecord]:
    key = _dedup_key(new)
    out: list[ChatRecord] = []
    replaced = False
    for r in records:
        if _dedup_key(r) == key:
            if not replaced:
                out.append(_merge_records(r, new))
                replaced = True
            # drop any duplicate stale rows sharing the key
        else:
            out.append(r)
    if not replaced:
        out.append(replace(new, tags=list(new.tags)))
    return out


def upsert(record: ChatRecord, registry: Path = REGISTRY) -> None:
    registry = Path(registry)
    existing = registry.read_text(encoding="utf-8") if registry.exists() else ""
    records = upsert_record(parse_lines(existing), record)
    registry.parent.mkdir(parents=True, exist_ok=True)
    content = render_lines(records)
    tmp = registry.parent / f".{registry.name}.{os.getpid()}.tmp"
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, registry)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def _cmd_upsert(args: argparse.Namespace) -> int:
    # NB: no CLAUDE_CODE_CHILD_SESSION guard — that env var is set for every
    # Claude Code Bash subprocess (main session included), so it does not
    # distinguish a subagent and would suppress the main-thread call this
    # command exists for. Trigger A is scoped by its caller (the skill's
    # main-thread handoff step); the empty-id check below is the only guard.
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    git = resolve_git_fields(args.cwd)
    now = args.now or _now()
    rec = ChatRecord(
        resume_id=args.resume_id.strip(),
        family=(args.family or "claude").strip(),
        model=args.model,
        intensity=args.intensity,
        repo=git["repo"],
        branch=git["branch"],
        worktree=git["worktree"],
        head_sha=git["head_sha"],
        dirty=git["dirty"],
        topic=" ".join(args.topic.split())[:80],  # authored, already clean
        tags=tags,
        transcript_path=args.transcript_path,
        capture_source="skill",
        created_at=now,
        last_updated=now,
        msg_count=0,  # the LLM does not count turns; Trigger B fills this
    )
    if not _dedup_key(rec)[1]:
        print("agent_chats: no resume id or transcript — skipping.", file=sys.stderr)
        return 0
    upsert(rec, Path(args.registry))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog="agent_chats")
    sub = parser.add_subparsers(dest="cmd", required=True)

    up = sub.add_parser("upsert")
    up.add_argument("--resume-id", default=os.environ.get("CLAUDE_CODE_SESSION_ID", ""))
    up.add_argument("--family", default="claude")
    up.add_argument("--model", default="")
    up.add_argument("--intensity", default="")
    up.add_argument("--topic", default="")
    up.add_argument("--tags", default="")
    up.add_argument("--transcript-path", default="")
    up.add_argument("--cwd", default=None)
    up.add_argument("--now", default=None)
    up.add_argument("--registry", default=str(REGISTRY))

    hook = sub.add_parser("capture-hook")
    hook.add_argument("--min-msgs", type=int, default=4)
    hook.add_argument("--cwd", default=None)
    hook.add_argument("--now", default=None)
    hook.add_argument("--registry", default=str(REGISTRY))

    args = parser.parse_args(argv)
    if args.cmd == "upsert":
        return _cmd_upsert(args)
    if args.cmd == "capture-hook":
        return _cmd_capture_hook(args)
    return 1


def count_turns(text: str) -> int:
    return sum(1 for o in _iter_events(text) if _turn_role(o) in ("user", "assistant"))


def passes_substance(text: str, min_msgs: int = 4) -> bool:
    return count_turns(text) >= min_msgs


def extract_topic(text: str, max_len: int = 80) -> str:
    # Topic = the first substantive user message in the transcript.
    for obj in _iter_events(text):
        if _turn_role(obj) == "user":
            t = _turn_text(obj)
            if t.strip():
                return _truncate(t, max_len)
    return "untitled session"


def detect_family(text: str) -> str:
    for obj in _iter_events(text):
        if obj.get("type") in _CODEX_ENVELOPE_TYPES and isinstance(obj.get("payload"), dict):
            return "codex"
    return "claude"


def extract_model(text: str, family: str) -> str:
    if family == "codex":
        for obj in _iter_events(text):
            if obj.get("type") in ("session_meta", "turn_context"):
                payload = obj.get("payload")
                if isinstance(payload, dict):
                    model = payload.get("model")
                    if isinstance(model, str) and model.strip():
                        return model.strip()
        return ""
    for obj in _iter_events(text):  # claude: assistant message carries model
        msg = obj.get("message")
        if isinstance(msg, dict):
            # Only extract model from assistant turns
            if obj.get("type") == "assistant" or msg.get("role") == "assistant":
                model = msg.get("model")
                if isinstance(model, str) and model.strip():
                    return model.strip()
    return ""


def _cmd_capture_hook(args: argparse.Namespace) -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    resume_id = str(payload.get("session_id") or "").strip()
    tpath = str(payload.get("transcript_path", "") or "")
    if not resume_id or not tpath or not Path(tpath).exists():
        print("agent_chats: no capturable session — skipping.", file=sys.stderr)
        return 0

    try:
        text = Path(tpath).read_text(encoding="utf-8", errors="replace")
    except OSError:
        print("agent_chats: cannot read transcript — skipping.", file=sys.stderr)
        return 0
    if not passes_substance(text, args.min_msgs):
        print("agent_chats: trivial session — skipping.", file=sys.stderr)
        return 0

    # An upstream hook may stamp `agent_family` on the payload as an explicit
    # family hint; otherwise we sniff it from the transcript shape.
    family = str(payload.get("agent_family", "") or "").strip() or detect_family(text)
    git = resolve_git_fields(payload.get("cwd") or args.cwd)
    now = args.now or _now()
    rec = ChatRecord(
        resume_id=resume_id,
        family=family,
        model=extract_model(text, family),
        intensity="",  # not deterministically available in Trigger B
        repo=git["repo"],
        branch=git["branch"],
        worktree=git["worktree"],
        head_sha=git["head_sha"],
        dirty=git["dirty"],
        topic=extract_topic(text),
        tags=[],
        transcript_path=tpath,
        capture_source="hook",
        created_at=now,
        last_updated=now,
        msg_count=count_turns(text),
    )
    upsert(rec, Path(args.registry))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
