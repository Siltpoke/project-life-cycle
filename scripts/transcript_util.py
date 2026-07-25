#!/usr/bin/env python3
"""Shared transcript + git primitives for the session-continuity tools.

Extracted so ``agent_chats.py`` (SessionEnd registry, Trigger B) and
``save_session.py`` (Stop-hook digest) parse the same multi-family transcript
shape from one place instead of two drifting copies. Pure stdlib, no side
effects on import.

Multi-family aware: Claude Code JSONL, Codex rollout envelopes, and the
``{"message": {"role", "content"}}`` shape all resolve through the same helpers.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


def iter_events(text: str) -> Iterator[dict]:
    """Yield each JSONL line as a dict; silently skip blank / malformed lines."""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            yield obj


def turn_role(obj: dict) -> str:
    """Return 'user' / 'assistant' / '' for a transcript event (multi-family)."""
    typ = obj.get("type")
    if typ in ("user", "assistant"):
        return typ
    if typ == "event_msg":  # Codex envelope
        payload = obj.get("payload")
        if isinstance(payload, dict):
            kind = payload.get("type")
            if kind == "user_message":
                return "user"
            if kind == "agent_message":
                return "assistant"
    msg = obj.get("message")
    if isinstance(msg, dict) and msg.get("role") in ("user", "assistant"):
        return msg["role"]
    return ""


def turn_text(obj: dict) -> str:
    """Extract the human-readable text of a transcript event (multi-family)."""
    if obj.get("type") == "event_msg":  # Codex
        payload = obj.get("payload")
        if isinstance(payload, dict) and isinstance(payload.get("message"), str):
            return payload["message"]
    msg = obj.get("message", obj)
    content = msg.get("content") if isinstance(msg, dict) else None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                return part.get("text", "")
            if isinstance(part, str):
                return part
    return ""


def truncate(s: str, n: int) -> str:
    """Collapse whitespace and cap at ``n`` chars with an ellipsis."""
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def now_stamp() -> str:
    """Local-time 'YYYY-MM-DD HH:MM' stamp."""
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


def _git(args: list[str], cwd: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=5
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def resolve_git_fields(cwd: str | None) -> dict:
    """Resolve repo / branch / worktree / head_sha / dirty for ``cwd``.

    Never raises — missing git or a non-repo cwd degrades to basename + empties.
    """
    cwd = str(cwd or os.getcwd())
    toplevel = _git(["rev-parse", "--show-toplevel"], cwd)
    worktree = toplevel or str(Path(cwd).resolve())
    repo = Path(toplevel).name if toplevel else Path(cwd).resolve().name
    status = _git(["status", "--porcelain"], cwd)
    return {
        "repo": repo,
        "branch": _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd) or "",
        "worktree": worktree,
        "head_sha": _git(["rev-parse", "--short", "HEAD"], cwd) or "",
        "dirty": bool(status) if status is not None else False,
    }
