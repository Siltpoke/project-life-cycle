#!/usr/bin/env python3
"""PLC-native automatic session save — a Stop hook.

Fires after every assistant turn (Claude Code ``Stop`` event), scrapes the
transcript deterministically (zero LLM), and writes a mechanical digest to
``~/.claude/plc-session-data/`` so ``/recall`` can brief the next session. This
is the automatic mechanical half; the LLM-quality curated handoff stays manual
(``/handoff`` → RESUME.md).

Design invariants:
  * NEVER blocks or crashes the session — malformed input still ``exit 0``.
  * Bounded transcript read (tail only) so a huge transcript can't hit the
    hook timeout and silently drop the save.
  * Atomic write (temp → ``os.replace``) — no truncated digest on crash.
  * PLC's own dir, ``.md`` extension.
  * Per-conversation keying (``session_id``), repo-basename fallback.
  * Retention cap: prune old digests (age + count) to bound file sprawl.

Reuses the shared multi-family parse + git primitives from ``transcript_util``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from transcript_util import (
    iter_events,
    now_stamp,
    resolve_git_fields,
    truncate,
    turn_role,
    turn_text,
)

# --- tunables -------------------------------------------
MAX_TASKS = 10          # last-N user messages
TASK_CHARS = 200        # per-message truncation
MAX_TOOLS = 20          # distinct tool names
MAX_FILES = 30          # distinct modified file paths
TAIL_LINES = 800        # keep only the last N transcript lines
TAIL_BYTES = 512 * 1024  # …and read only the last N bytes off disk (true bound)
RETAIN_DAYS = 30        # prune digests older than this…
RETAIN_COUNT = 50       # …and keep at most this many, newest first
_WRITE_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})
_SAFE = re.compile(r"[^A-Za-z0-9_-]")


def sessions_dir() -> Path:
    """PLC's own digest dir."""
    return Path(os.path.expanduser("~")) / ".claude" / "plc-session-data"


def sanitize_id(raw: str) -> str:
    """Sanitize an id fragment: keep safe chars; non-ASCII → sha256[:8]."""
    if not raw:
        return ""
    if any(ord(c) > 127 for c in raw):
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
    cleaned = _SAFE.sub("", raw)
    return cleaned or hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]


def session_key(payload: dict, git: dict) -> str:
    """Per-conversation key: the FULL sanitized session_id, else repo+hash fallback.

    Uses the whole session_id (not a truncated tail) so two same-repo same-day
    sessions can never collide onto one digest file — one conversation, one file.
    """
    sid = str(payload.get("session_id") or "").strip()
    key = sanitize_id(sid) if sid else ""
    if key:
        return key
    repo = sanitize_id(str(git.get("repo") or "session")) or "session"
    seed = str(payload.get("transcript_path") or git.get("worktree") or repo)
    return f"{repo}-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:8]}"


def read_tail(path: Path, max_bytes: int = TAIL_BYTES,
              max_lines: int = TAIL_LINES) -> str:
    """Read only the LAST ``max_bytes`` off disk, then keep the last ``max_lines``.

    Bounds BOTH I/O/memory and parse cost. A multi-hundred-MB transcript
    must never be slurped whole every turn — that is exactly the silent-drop
    timeout bug. Seeks from the end and discards the first (partial) line.
    """
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            if size > max_bytes:
                f.seek(-max_bytes, os.SEEK_END)
                f.readline()  # drop the partial line the seek landed inside
            data = f.read()
    except OSError:
        return ""
    lines = data.decode("utf-8", errors="replace").splitlines()
    return "\n".join(lines[-max_lines:])


def _tool_uses(obj: dict):
    """Yield (name, input_dict) for each tool_use part in an assistant event."""
    msg = obj.get("message", obj)
    content = msg.get("content") if isinstance(msg, dict) else None
    if not isinstance(content, list):
        return
    for part in content:
        if isinstance(part, dict) and part.get("type") == "tool_use":
            name = part.get("name")
            if isinstance(name, str) and name:
                inp = part.get("input")
                yield name, inp if isinstance(inp, dict) else {}


def extract_digest(text: str, payload: dict, git: dict) -> dict:
    """Scrape the transcript into the mechanical digest fields."""
    tasks: list[str] = []
    tools: list[str] = []
    files: list[str] = []
    seen_tools: set[str] = set()
    seen_files: set[str] = set()
    user_count = 0

    for obj in iter_events(text):
        role = turn_role(obj)
        if role == "user":
            user_count += 1
            t = turn_text(obj).strip()
            if t and not t.startswith("<"):  # skip tool-result / system-shaped blobs
                tasks.append(truncate(t, TASK_CHARS))
        elif role == "assistant":
            for name, inp in _tool_uses(obj):
                if name not in seen_tools:
                    seen_tools.add(name)
                    tools.append(name)
                if name in _WRITE_TOOLS:
                    fp = inp.get("file_path") or inp.get("notebook_path")
                    if isinstance(fp, str) and fp and fp not in seen_files:
                        seen_files.add(fp)
                        files.append(fp)

    return {
        "tasks": tasks[-MAX_TASKS:],
        "tools": tools[:MAX_TOOLS],
        "files": files[:MAX_FILES],
        "user_count": user_count,
        "project": git.get("repo") or "",
        "branch": git.get("branch") or "",
        "worktree": git.get("worktree") or "",
        "key": session_key(payload, git),
        "now": now_stamp(),
    }


def render_digest(data: dict, started: str | None = None) -> str:
    """Render the mechanical digest markdown."""
    now = data["now"]
    lines = [
        f"# Session: {now[:10]}",
        f"**Project:** {data['project'] or 'unknown'}   "
        f"**Branch:** {data['branch'] or 'unknown'}   "
        f"**Session:** {data['key']}",
        f"**Dir:** {data['worktree'] or 'unknown'}",
        f"**Started:** {started or now}   **Last Updated:** {now}",
        "",
        "## Tasks",
    ]
    lines += [f"- {t}" for t in data["tasks"]] or ["- (none)"]
    lines += ["", "## Files Modified"]
    lines += [f"- {f}" for f in data["files"]] or ["- (none)"]
    lines += ["", "## Tools Used", ", ".join(data["tools"]) or "(none)"]
    lines += ["", "## Stats", f"- Total user messages: {data['user_count']}", ""]
    return "\n".join(lines)


def _existing_started(path: Path) -> str | None:
    """Preserve the original **Started:** stamp across per-turn rewrites."""
    if not path.exists():
        return None
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            m = re.search(r"\*\*Started:\*\*\s*(.+?)\s{2,}\*\*Last Updated", line)
            if m:
                return m.group(1).strip()
    except OSError:
        return None
    return None


def atomic_write(path: Path, content: str) -> None:
    """Write via temp + os.replace so a crash never leaves a half file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{os.getpid()}.tmp"
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def prune(directory: Path, days: int = RETAIN_DAYS, count: int = RETAIN_COUNT,
          now: float | None = None) -> int:
    """Delete digests older than ``days`` or beyond the newest ``count``.

    Returns the number deleted. Never raises on a single unlink failure.
    """
    if not directory.exists():
        return 0
    files = [p for p in directory.glob("*.md") if p.is_file()]
    if not files:
        return 0
    stamped = sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)
    ref = now if now is not None else max(p.stat().st_mtime for p in stamped)
    cutoff = ref - days * 86400
    deleted = 0
    for i, p in enumerate(stamped):
        too_old = p.stat().st_mtime < cutoff
        over_count = i >= count
        if too_old or over_count:
            try:
                p.unlink()
                deleted += 1
            except OSError:
                pass
    return deleted


def _project_slug(data: dict) -> str:
    return sanitize_id(data["project"] or "session") or "session"


def build_filename(data: dict) -> str:
    return f"{data['now'][:10]}-{_project_slug(data)}-{data['key']}.md"


def find_existing(directory: Path, data: dict) -> Path | None:
    """Return this conversation's existing digest regardless of date prefix.

    Keyed by project+session, NOT the write-time date — so a session that crosses
    midnight keeps updating ONE file in place instead of spawning a second
    dated file and resetting Started.
    """
    if not directory.exists():
        return None
    matches = sorted(
        directory.glob(f"*-{_project_slug(data)}-{data['key']}.md"),
        key=lambda p: p.stat().st_mtime, reverse=True,
    )
    return matches[0] if matches else None


def run(payload: dict, base_dir: Path | None = None) -> Path | None:
    """Core: build + atomically write the digest, then prune. Returns the path."""
    tpath = str(payload.get("transcript_path") or "")
    text = read_tail(Path(tpath)) if tpath and Path(tpath).exists() else ""
    git = resolve_git_fields(payload.get("cwd"))
    data = extract_digest(text, payload, git)
    directory = base_dir or sessions_dir()
    path = find_existing(directory, data) or (directory / build_filename(data))
    body = render_digest(data, started=_existing_started(path))
    atomic_write(path, body)
    prune(directory)
    return path


# --- /recall read side (testable selection logic; the prose command calls this) --

_DATE_GLOB = "????-??-??"
STALE_DAYS = 7          # /recall flags a digest older than this


@dataclass(frozen=True)
class DigestPick:
    """A resolved digest for /recall to brief from."""
    path: Path
    stale_days: int          # age in whole days
    cross_project: bool      # True = no digest for the asked repo, fell back to global

    @property
    def stale(self) -> bool:
        return self.stale_days > STALE_DAYS


def _age_days(path: Path, now: float) -> int:
    return int((now - path.stat().st_mtime) // 86400)


def digest_project(path: Path) -> str:
    """Read a digest's declared ``**Project:**`` value (the authoritative repo).

    Repo scoping matches on THIS, not on the filename — both the project slug and
    the session key may contain '-', so a filename glob like ``*-app-*`` wrongly
    catches ``app-web`` digests (prefix collision). The header is unambiguous.
    """
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.search(r"\*\*Project:\*\*\s*(.+?)\s{2,}\*\*", line)
            if m:
                return m.group(1).strip()
    except OSError:
        return ""
    return ""


def select_digest(directory: Path, repo: str, arg: str | None = None,
                  now: float | None = None) -> DigestPick | None:
    """Resolve which digest ``/recall`` should brief from. Read-only.

    - ``arg`` a path (contains ``/`` or ends ``.md``) → that exact file.
    - ``arg`` a ``YYYY-MM-DD`` → that date, current repo, newest.
    - no ``arg`` → newest for the current repo; if none, newest GLOBAL with
      ``cross_project=True`` (never silently surface another project's state).

    Repo scoping is by the digest's ``**Project:**`` header, NOT the filename —
    filename globbing leaks across prefix-colliding project names (``app`` vs
    ``app-web``) because slug and key both allow '-'.
    """
    ref = now if now is not None else time.time()

    # Path arg (explicit teammate-handoff) is independent of the local dir — check
    # it BEFORE the dir-existence guard, or a fresh machine (no digest dir yet)
    # wrongly returns None for a perfectly readable explicit file.
    if arg and ("/" in arg or arg.endswith(".md")):
        p = Path(arg)
        return DigestPick(p, _age_days(p, ref), False) if p.exists() else None

    if not directory.exists():
        return None

    def newest(paths: list[Path]) -> list[Path]:
        return sorted(paths, key=lambda p: p.stat().st_mtime, reverse=True)

    def date_ok(p: Path) -> bool:
        return arg is None or p.name[:10] == arg

    candidates = [p for p in directory.glob(f"{_DATE_GLOB}-*.md") if date_ok(p)]
    repo_hits = newest([p for p in candidates if digest_project(p) == repo])
    if repo_hits:
        return DigestPick(repo_hits[0], _age_days(repo_hits[0], ref), False)

    global_hits = newest(candidates)
    if global_hits:
        return DigestPick(global_hits[0], _age_days(global_hits[0], ref), True)
    return None


def _cmd_resume(args: list[str]) -> int:
    """Read-only `/recall` dispatch — print the resolved digest as JSON, never write.

    Usage: ``save_session.py resume [<YYYY-MM-DD>|<path>]``. Repo is derived from the
    cwd. `/recall` (commands/recall.md) calls this and formats the briefing.
    """
    arg = args[0] if args and args[0] else None
    repo = resolve_git_fields(None).get("repo") or ""
    pick = select_digest(sessions_dir(), repo, arg)
    if pick is None:
        print(json.dumps({"found": False}))
        return 0
    print(json.dumps({
        "found": True,
        "path": str(pick.path),
        "project": digest_project(pick.path),
        "stale_days": pick.stale_days,
        "stale": pick.stale,
        "cross_project": pick.cross_project,
    }))
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entrypoint. `resume` subcommand = read-only briefing; else = Stop-hook stdin
    write path. ALWAYS exit 0."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "resume":
        return _cmd_resume(argv[1:])
    try:
        raw = sys.stdin.read()
    except (OSError, ValueError):
        raw = ""
    try:
        payload = json.loads(raw or "{}")
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        run(payload)
    except Exception as exc:  # noqa: BLE001 — a hook must never break the session
        print(f"save_session: skipped ({exc})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
