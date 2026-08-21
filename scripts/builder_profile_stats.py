#!/usr/bin/env python3
"""PASS-1 deterministic stats for ``/builder-profile``.

Parses local Claude Code transcripts (``~/.claude/projects/**/*.jsonl``, one
JSON event per line) and emits a ``stats.json`` payload. This is the
deterministic half of the builder-profile pipeline: every number here is
re-computable from the raw logs, with no LLM in the loop. The qualitative
passes (cold read + adversarial verify) consume this file plus sampled
excerpts — see ``skills/project-lifecycle/references/builder-profile.md``.

100% local. Pure stdlib. Run::

    python3 scripts/builder_profile_stats.py            # -> stdout
    python3 scripts/builder_profile_stats.py --out stats.json
    python3 scripts/builder_profile_stats.py --root /path/to/projects --days 90
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from statistics import median as _median

SCHEMA_VERSION = 2  # 2: plan_mode gained `signal` + a nullable `ratio`
WORD_RE = re.compile(r"[a-z0-9]+")
NIGHT_HOURS = set(range(18, 24)) | set(range(0, 6))  # 18:00–05:59 local
DAY_HOURS = set(range(9, 18))  # 09:00–17:59 local
TOP_NGRAMS = 10

# Keys a permission-mode event is known to carry the mode under. Read as a
# field-presence assertion, not just a lookup: if a real permission-mode event
# carries none of these, the transcript schema moved and the plan-mode number is
# unknown rather than zero.
PERMISSION_MODE_KEYS = ("permissionMode", "mode")

PLAN_SIGNAL_NOTES = {
    "present": (
        "permission-mode events carrying a known mode key were found, so the "
        "ratio is a real measurement."
    ),
    "schema-drift": (
        "permission-mode events exist but NONE carries a known mode key "
        f"({', '.join(PERMISSION_MODE_KEYS)}) — the transcript field was "
        "renamed. ratio is unknown, NOT zero: re-verify the field against a raw "
        "transcript and update PERMISSION_MODE_KEYS before citing plan mode."
    ),
    "absent": (
        "no permission-mode event of any mode appears in the window, so "
        "'plan mode genuinely unused' and 'the event type was renamed' are "
        "indistinguishable. ratio is unknown, NOT zero."
    ),
}


# --------------------------------------------------------------------------- #
# event classification + extraction                                           #
# --------------------------------------------------------------------------- #
def classify_turn(event: dict) -> str:
    """One of ``user_prompt`` / ``tool_result`` / ``assistant`` / ``other``.

    A ``type: "user"`` turn is a real prompt only if it carries text — turns
    that carry *only* a ``tool_result`` block are the agent's tool output
    echoed back, not the human typing.
    """
    kind = event.get("type")
    if kind == "assistant":
        return "assistant"
    if kind != "user":
        return "other"
    content = event.get("message", {}).get("content")
    if isinstance(content, str):
        return "user_prompt" if content.strip() else "other"
    if isinstance(content, list):
        blocks = [b for b in content if isinstance(b, dict)]
        if any(b.get("type") == "text" for b in blocks):
            return "user_prompt"
        if any(b.get("type") == "tool_result" for b in blocks):
            return "tool_result"
    return "other"


def prompt_text(event: dict) -> str:
    content = event.get("message", {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            b.get("text", "")
            for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


def assistant_tools(event: dict) -> list[str]:
    content = event.get("message", {}).get("content")
    if not isinstance(content, list):
        return []
    return [
        b["name"]
        for b in content
        if isinstance(b, dict) and b.get("type") == "tool_use" and "name" in b
    ]


def parse_ts(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def local_hour(dt: datetime, tz: tzinfo | None) -> int | None:
    # Honest-metrics: a naive timestamp has no true wall-clock hour — skip it
    # rather than silently assuming UTC and skewing the night-owl histogram.
    if dt.tzinfo is None:
        return None
    return dt.astimezone(tz).hour


# --------------------------------------------------------------------------- #
# small numeric helpers                                                       #
# --------------------------------------------------------------------------- #
def _percentile_nearest_rank(values: list[int], q: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    k = max(1, math.ceil(q * len(ordered)))
    return ordered[k - 1]


def _ratio(num: int, den: int) -> float:
    return round(num / den, 4) if den else 0.0


def _ngrams(tokens: list[str], n: int) -> list[str]:
    return [" ".join(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]


# --------------------------------------------------------------------------- #
# per-session reduction                                                       #
# --------------------------------------------------------------------------- #
def _session_id(events: list[dict], index: int) -> str:
    for ev in events:
        sid = ev.get("sessionId")
        if sid:
            return str(sid)
    return f"session-{index}"


def is_sidechain(event: dict) -> bool:
    """True for sub-agent turns (interleaved in the file via ``isSidechain``)."""
    return event.get("isSidechain") is True


def is_permission_mode_event(event: dict) -> bool:
    """True for a permission-mode switch event, whatever mode it carries.

    This is the *channel* plan-mode detection rides on. Counted separately from
    plan itself so a vanished channel is distinguishable from a real zero — see
    ``PLAN_SIGNAL_NOTES``.
    """
    return event.get("type") == "permission-mode"


def permission_mode_value(event: dict) -> str | None:
    """The mode a permission-mode event carries, or None if it uses no known key."""
    for key in PERMISSION_MODE_KEYS:
        value = event.get(key)
        if value is not None:
            return str(value)
    return None


def is_plan_event(event: dict) -> bool:
    """A ``permission-mode`` event switching into plan mode.

    Verified against real transcripts: plan mode is recorded as a
    ``type:"permission-mode"`` event with ``permissionMode == "plan"`` (the
    field is ``permissionMode``, and the event carries no timestamp) — *not*
    as an ``ExitPlanMode`` tool_use (which never appears in practice).
    """
    if not is_permission_mode_event(event):
        return False
    return permission_mode_value(event) == "plan"


def _reduce_session(events: list[dict], index: int, tz: tzinfo | None) -> dict:
    sid = _session_id(events, index)
    timestamps: list[datetime] = []
    word_lengths: list[int] = []
    char_lengths: list[int] = []
    hours: list[int] = []
    models: Counter[str] = Counter()
    tools: Counter[str] = Counter()
    ngram_lines: list[list[str]] = []
    user_prompts = 0
    plan = False
    pm_events = 0
    pm_keyed = 0

    for ev in events:
        # Skip sub-agent turns — the profile is about how the *user* drives.
        if is_sidechain(ev):
            continue
        if is_permission_mode_event(ev):
            # Counted for every mode, before the plan check: this is the
            # field-presence evidence that tells a real zero from a dead parser.
            pm_events += 1
            if permission_mode_value(ev) is not None:
                pm_keyed += 1
        if is_plan_event(ev):
            plan = True
            continue

        ts = parse_ts(ev.get("timestamp"))
        if ts is not None:
            timestamps.append(ts)
        kind = classify_turn(ev)

        if kind == "assistant":
            model = ev.get("message", {}).get("model")
            if model:
                models[str(model)] += 1
            tools.update(assistant_tools(ev))
        elif kind == "user_prompt":
            user_prompts += 1
            text = prompt_text(ev)
            word_lengths.append(len(text.split()))
            char_lengths.append(len(text))
            ngram_lines.append(WORD_RE.findall(text.lower()))
            if ts is not None:
                hour = local_hour(ts, tz)
                if hour is not None:
                    hours.append(hour)

    return {
        "session_id": sid,
        "start": min(timestamps) if timestamps else None,
        "end": max(timestamps) if timestamps else None,
        "plan": plan,
        "pm_events": pm_events,
        "pm_keyed": pm_keyed,
        "user_prompts": user_prompts,
        "word_lengths": word_lengths,
        "char_lengths": char_lengths,
        "hours": hours,
        "models": models,
        "tools": tools,
        "ngram_lines": ngram_lines,
    }


# --------------------------------------------------------------------------- #
# trajectory                                                                  #
# --------------------------------------------------------------------------- #
def _subset_metrics(subset: list[dict], plan_signal: str) -> dict:
    sessions = len(subset)
    planned = sum(1 for s in subset if s["plan"])
    words = [w for s in subset for w in s["word_lengths"]]
    return {
        "sessions": sessions,
        # Same rule as the top-level block: without a live signal channel this is
        # unknown, not 0.0 — otherwise a dead parser reads as "stopped planning".
        "plan_ratio": _ratio(planned, sessions) if plan_signal == "present" else None,
        "prompt_len_median": int(_median(words)) if words else 0,
    }


def _trajectory(reduced: list[dict], plan_signal: str) -> dict:
    dated = [s for s in reduced if s["start"] is not None]
    if len(dated) < 3:
        return {"status": "insufficient"}
    dated.sort(key=lambda s: s["start"])
    third = len(dated) // 3  # guard above guarantees third >= 1
    return {
        "status": "ok",
        "first_third": _subset_metrics(dated[:third], plan_signal),
        "last_third": _subset_metrics(dated[-third:], plan_signal),
        # honest-metrics: the middle band is intentionally not in either third;
        # name it so a reader doesn't assume the two thirds exhaust the data.
        "middle_sessions_excluded": len(dated) - 2 * third,
    }


# --------------------------------------------------------------------------- #
# top-level compute                                                           #
# --------------------------------------------------------------------------- #
def compute_stats(
    sessions: list[list[dict]],
    *,
    tz: tzinfo | None = None,
    window_days: int = 90,
) -> dict:
    """Reduce a list of sessions (each a list of ordered events) to stats."""
    reduced = [_reduce_session(events, i, tz) for i, events in enumerate(sessions)]

    all_ts = [t for s in reduced for t in (s["start"], s["end"]) if t is not None]
    models: Counter[str] = Counter()
    tools: Counter[str] = Counter()
    hours: Counter[int] = Counter()
    word_lengths: list[int] = []
    char_lengths: list[int] = []
    ngram_counters = {n: Counter() for n in (2, 3, 4)}
    planned_sessions = 0
    pm_events = 0
    pm_keyed = 0

    for s in reduced:
        models.update(s["models"])
        tools.update(s["tools"])
        hours.update(s["hours"])
        word_lengths.extend(s["word_lengths"])
        char_lengths.extend(s["char_lengths"])
        planned_sessions += 1 if s["plan"] else 0
        pm_events += s["pm_events"]
        pm_keyed += s["pm_keyed"]
        for tokens in s["ngram_lines"]:
            for n in (2, 3, 4):
                ngram_counters[n].update(_ngrams(tokens, n))

    total_models = sum(models.values())
    night = sum(c for h, c in hours.items() if h in NIGHT_HOURS)
    day = sum(c for h, c in hours.items() if h in DAY_HOURS)
    prompt_hours = sum(hours.values())
    if prompt_hours == 0:
        verdict = "insufficient"
    elif night / prompt_hours >= 0.5:
        verdict = "night-owl"
    elif day / prompt_hours >= 0.6:
        verdict = "9-5"
    else:
        verdict = "mixed"

    longest = _longest_session(reduced)

    # Field-presence assertion, tri-state. A bare `ratio: 0.0` cannot tell
    # "never used plan mode" from "the transcript field moved and the detector
    # now matches nothing", so the channel is measured alongside the value.
    if pm_keyed > 0:
        plan_signal = "present"
    elif pm_events > 0:
        plan_signal = "schema-drift"
    else:
        plan_signal = "absent"

    return {
        "schema_version": SCHEMA_VERSION,
        "window": {
            "days": window_days,
            "from": min(all_ts).isoformat() if all_ts else None,
            "to": max(all_ts).isoformat() if all_ts else None,
            "sessions": len(sessions),
        },
        "models": {m: _ratio(c, total_models) for m, c in models.most_common()},
        "hour_of_day": {str(h): hours.get(h, 0) for h in range(24)},
        "night_owl": {
            "verdict": verdict,
            "night_share": _ratio(night, prompt_hours),
            "day_share": _ratio(day, prompt_hours),
            "basis": "night=18:00–05:59, day=09:00–17:59 local",
        },
        "prompt_length": {
            "words": {
                "median": int(_median(word_lengths)) if word_lengths else 0,
                "p80": _percentile_nearest_rank(word_lengths, 0.8)
                if len(word_lengths) >= 5
                else None,
            },
            "chars": {
                "median": int(_median(char_lengths)) if char_lengths else 0,
                "p80": _percentile_nearest_rank(char_lengths, 0.8)
                if len(char_lengths) >= 5
                else None,
            },
            "n": len(word_lengths),
        },
        "plan_mode": {
            "signal": plan_signal,
            "sessions_with_plan": planned_sessions,
            "ratio": _ratio(planned_sessions, len(sessions))
            if plan_signal == "present"
            else None,
            "permission_mode_events": pm_events,
            "permission_mode_events_with_known_key": pm_keyed,
            "known_keys": list(PERMISSION_MODE_KEYS),
            "note": PLAN_SIGNAL_NOTES[plan_signal],
        },
        "tools": {
            "ranking": [[name, c] for name, c in tools.most_common()],
            "diversity": len(tools),
        },
        "longest_session": longest,
        "steering": {
            "status": "deferred-to-pass-2",
            "note": "No reliable deterministic interrupt signal exists in the "
            "transcript (a tool_result always sits between an assistant tool_use "
            "and the next user prompt). PASS-2 judges redirection from sampled "
            "exchanges instead.",
        },
        "ngrams": {
            str(n): [[phrase, c] for phrase, c in ngram_counters[n].most_common(TOP_NGRAMS)]
            for n in (2, 3, 4)
        },
        "trajectory": _trajectory(reduced, plan_signal),
    }


def _longest_session(reduced: list[dict]) -> dict:
    best: dict | None = None
    best_minutes = -1.0
    for s in reduced:
        if s["start"] is None or s["end"] is None:
            continue
        minutes = round((s["end"] - s["start"]).total_seconds() / 60, 1)
        if minutes > best_minutes:
            best_minutes = minutes
            best = {
                "session_id": s["session_id"],
                "duration_minutes": minutes,
                "from": s["start"].isoformat(),
                "to": s["end"].isoformat(),
            }
    return best or {"session_id": None, "duration_minutes": 0, "from": None, "to": None}


# --------------------------------------------------------------------------- #
# IO                                                                          #
# --------------------------------------------------------------------------- #
def load_session_file(path: Path) -> tuple[list[dict], int]:
    """Return ``(events, skipped_lines)`` for one ``.jsonl`` transcript."""
    events: list[dict] = []
    skipped = 0
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return events, skipped
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            skipped += 1
            continue
        if isinstance(obj, dict):
            events.append(obj)
        else:
            skipped += 1
    return events, skipped


def _recent(events: list[dict], cutoff: datetime) -> bool:
    for ev in events:
        ts = parse_ts(ev.get("timestamp"))
        if ts is not None and ts.tzinfo is not None and ts.astimezone(timezone.utc) >= cutoff:
            return True
    return False


def has_real_prompt(events: list[dict]) -> bool:
    """A real conversation has ≥1 non-sidechain user text prompt.

    Filters out sub-agent / automated transcript files that carry only tool
    chatter, so the session count reflects the user's actual conversations.
    """
    return any(
        not is_sidechain(ev) and classify_turn(ev) == "user_prompt" for ev in events
    )


def collect(root: Path, window_days: int) -> tuple[list[list[dict]], dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    files = sorted(root.glob("**/*.jsonl"))
    sessions: list[list[dict]] = []
    skipped_lines = 0
    parsed = 0
    skipped_no_prompt = 0
    for path in files:
        events, skipped = load_session_file(path)
        skipped_lines += skipped
        if not events or not _recent(events, cutoff):
            continue
        if not has_real_prompt(events):
            skipped_no_prompt += 1
            continue
        sessions.append(events)
        parsed += 1
    sampling = {
        "files_total": len(files),
        "files_in_window": parsed,
        "files_dropped_no_prompt": skipped_no_prompt,
        "skipped_lines": skipped_lines,
    }
    return sessions, sampling


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.home() / ".claude" / "projects",
        help="transcript root (default ~/.claude/projects)",
    )
    parser.add_argument("--days", type=int, default=90, help="window in days (default 90)")
    parser.add_argument("--out", type=Path, default=None, help="write JSON here (default stdout)")
    args = parser.parse_args(argv)

    if not args.root.exists():
        print(f"ERROR: transcript root not found: {args.root}", file=sys.stderr)
        return 1

    sessions, sampling = collect(args.root, args.days)
    stats = compute_stats(sessions, tz=None, window_days=args.days)
    stats["sampling"] = sampling

    payload = json.dumps(stats, indent=2, ensure_ascii=False)
    if args.out:
        args.out.write_text(payload + "\n", encoding="utf-8")
        print(f"wrote {args.out} ({sampling['files_in_window']} sessions in window)")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
