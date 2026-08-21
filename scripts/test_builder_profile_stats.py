#!/usr/bin/env python3
"""Tests for the PASS-1 deterministic builder-profile stats parser.

Pure-function tests: every assertion runs against ``compute_stats`` /
classification helpers fed synthetic event lists, so nothing touches the real
``~/.claude`` directory. Run::

    pytest scripts/test_builder_profile_stats.py -v
"""

from __future__ import annotations

from datetime import timezone

import builder_profile_stats as bp


# --------------------------------------------------------------------------- #
# helpers to build synthetic transcript events                                #
# --------------------------------------------------------------------------- #
def user_prompt(text: str, ts: str, session: str = "s1") -> dict:
    return {
        "type": "user",
        "timestamp": ts,
        "sessionId": session,
        "message": {"content": text},
    }


def tool_result(ts: str, session: str = "s1", tool_use_id: str = "t1") -> dict:
    return {
        "type": "user",
        "timestamp": ts,
        "sessionId": session,
        "message": {
            "content": [
                {"type": "tool_result", "tool_use_id": tool_use_id, "content": "ok"}
            ]
        },
    }


def permission_mode(mode: str, ts: str, session: str = "s1") -> dict:
    # Real shape: field is ``permissionMode`` and the event carries no timestamp.
    return {"type": "permission-mode", "permissionMode": mode, "sessionId": session}


def assistant(
    ts: str,
    *,
    model: str = "claude-opus-4-5",
    tools: list[str] | None = None,
    text: str = "sure",
    session: str = "s1",
) -> dict:
    content: list[dict] = [{"type": "text", "text": text}]
    for i, name in enumerate(tools or []):
        content.append(
            {"type": "tool_use", "id": f"t{i}", "name": name, "input": {}}
        )
    return {
        "type": "assistant",
        "timestamp": ts,
        "sessionId": session,
        "message": {"model": model, "content": content},
    }


UTC = timezone.utc


# --------------------------------------------------------------------------- #
# classification                                                              #
# --------------------------------------------------------------------------- #
def test_classify_distinguishes_prompt_from_tool_result() -> None:
    assert bp.classify_turn(user_prompt("hi", "2026-01-01T10:00:00Z")) == "user_prompt"
    assert bp.classify_turn(tool_result("2026-01-01T10:00:01Z")) == "tool_result"
    assert (
        bp.classify_turn(assistant("2026-01-01T10:00:02Z", tools=["Read"]))
        == "assistant"
    )


def test_classify_user_array_with_text_is_prompt() -> None:
    ev = {
        "type": "user",
        "timestamp": "2026-01-01T10:00:00Z",
        "message": {"content": [{"type": "text", "text": "do the thing"}]},
    }
    assert bp.classify_turn(ev) == "user_prompt"


# --------------------------------------------------------------------------- #
# model ratio                                                                 #
# --------------------------------------------------------------------------- #
def test_model_ratio() -> None:
    sessions = [
        [
            assistant("2026-01-01T10:00:00Z", model="claude-opus-4-5"),
            assistant("2026-01-01T10:01:00Z", model="claude-opus-4-5"),
            assistant("2026-01-01T10:02:00Z", model="claude-sonnet-4-6"),
            assistant("2026-01-01T10:03:00Z", model="claude-sonnet-4-6"),
        ]
    ]
    stats = bp.compute_stats(sessions, tz=UTC)
    assert stats["models"]["claude-opus-4-5"] == 0.5
    assert stats["models"]["claude-sonnet-4-6"] == 0.5


# --------------------------------------------------------------------------- #
# plan mode                                                                   #
# --------------------------------------------------------------------------- #
def test_plan_mode_detection_via_permission_mode_event() -> None:
    sessions = [
        [permission_mode("plan", "2026-01-01T10:00:00Z"),
         user_prompt("plan it", "2026-01-01T10:00:01Z")],  # planned
        [permission_mode("auto", "2026-01-02T10:00:00Z"),
         user_prompt("go", "2026-01-02T10:00:01Z")],  # not
        [user_prompt("hi", "2026-01-03T10:00:00Z")],  # not
    ]
    stats = bp.compute_stats(sessions, tz=UTC)
    assert stats["plan_mode"]["sessions_with_plan"] == 1
    assert round(stats["plan_mode"]["ratio"], 3) == round(1 / 3, 3)


def test_exitplanmode_tooluse_does_not_count_as_plan() -> None:
    # ExitPlanMode tool_use never appears in real transcripts; must NOT trigger.
    sessions = [[assistant("2026-01-01T10:00:00Z", tools=["ExitPlanMode"])]]
    stats = bp.compute_stats(sessions, tz=UTC)
    assert stats["plan_mode"]["sessions_with_plan"] == 0


# --- field-presence assertion (a dead detector must not read as a real zero) - #
def test_plan_signal_present_when_channel_alive_but_plan_never_chosen() -> None:
    # The honest zero: permission-mode events exist, none of them is plan.
    sessions = [
        [permission_mode("auto", "2026-01-01T10:00:00Z"),
         user_prompt("go", "2026-01-01T10:00:01Z")],
    ]
    stats = bp.compute_stats(sessions, tz=UTC)["plan_mode"]
    assert stats["signal"] == "present"
    assert stats["sessions_with_plan"] == 0
    assert stats["ratio"] == 0.0  # a measured zero stays a number
    assert stats["permission_mode_events_with_known_key"] == 1


def test_plan_signal_absent_reports_unknown_not_zero() -> None:
    # No permission-mode event at all: "never used" and "event type renamed"
    # are indistinguishable, so the ratio must not claim 0.0.
    sessions = [[user_prompt("hi", "2026-01-01T10:00:00Z")]]
    stats = bp.compute_stats(sessions, tz=UTC)["plan_mode"]
    assert stats["signal"] == "absent"
    assert stats["ratio"] is None
    assert stats["permission_mode_events"] == 0


def test_plan_signal_schema_drift_when_mode_key_renamed() -> None:
    # The channel is alive but the mode moved to an unknown key — this is a
    # parser break and must be surfaced, not silently counted as zero.
    drifted = {
        "type": "permission-mode",
        "permission_mode": "plan",  # snake_case: not in PERMISSION_MODE_KEYS
        "sessionId": "s1",
    }
    sessions = [[drifted, user_prompt("plan it", "2026-01-01T10:00:00Z")]]
    stats = bp.compute_stats(sessions, tz=UTC)["plan_mode"]
    assert stats["signal"] == "schema-drift"
    assert stats["ratio"] is None
    assert stats["permission_mode_events"] == 1
    assert stats["permission_mode_events_with_known_key"] == 0
    assert "renamed" in stats["note"]


def test_trajectory_plan_ratio_unknown_when_signal_not_present() -> None:
    # The same silent zero used to survive in the trajectory subsets.
    sessions = [
        [user_prompt("a", f"2026-01-0{d}T10:00:00Z", session=f"s{d}")]
        for d in (1, 2, 3)
    ]
    traj = bp.compute_stats(sessions, tz=UTC)["trajectory"]
    assert traj["status"] == "ok"
    assert traj["first_third"]["plan_ratio"] is None
    assert traj["last_third"]["plan_ratio"] is None


# --------------------------------------------------------------------------- #
# steering — deferred to PASS-2 (no honest deterministic signal)              #
# --------------------------------------------------------------------------- #
def test_steering_is_deferred_to_pass2() -> None:
    sessions = [
        [
            user_prompt("start", "2026-01-01T10:00:00Z"),
            assistant("2026-01-01T10:00:05Z", tools=["Read"]),
            user_prompt("no, differently", "2026-01-01T10:00:09Z"),
        ]
    ]
    stats = bp.compute_stats(sessions, tz=UTC)
    assert stats["steering"]["status"] == "deferred-to-pass-2"


# --------------------------------------------------------------------------- #
# sidechain exclusion                                                         #
# --------------------------------------------------------------------------- #
def test_sidechain_events_excluded() -> None:
    main_assist = assistant("2026-01-01T10:00:00Z", tools=["Read"])
    sub_assist = assistant("2026-01-01T10:00:01Z", tools=["Bash", "Bash"])
    sub_assist["isSidechain"] = True
    stats = bp.compute_stats([[main_assist, sub_assist]], tz=UTC)
    ranking = dict(stats["tools"]["ranking"])
    assert ranking.get("Read") == 1
    assert "Bash" not in ranking  # sub-agent tool calls excluded


def test_has_real_prompt_filters_subagent_only_files() -> None:
    sub = assistant("2026-01-01T10:00:00Z", tools=["Read"])
    sub["isSidechain"] = True
    assert bp.has_real_prompt([sub]) is False
    assert bp.has_real_prompt([user_prompt("hi", "2026-01-01T10:00:00Z")]) is True


# --------------------------------------------------------------------------- #
# prompt length                                                               #
# --------------------------------------------------------------------------- #
def test_prompt_length_percentiles() -> None:
    # word counts 1..5
    texts = ["a", "a b", "a b c", "a b c d", "a b c d e"]
    sessions = [
        [user_prompt(t, f"2026-01-01T10:0{i}:00Z") for i, t in enumerate(texts)]
    ]
    stats = bp.compute_stats(sessions, tz=UTC)
    assert stats["prompt_length"]["words"]["median"] == 3
    # nearest-rank p80 of 1..5 -> ceil(0.8*5)=4 -> 4th value = 4
    assert stats["prompt_length"]["words"]["p80"] == 4
    assert stats["prompt_length"]["n"] == 5


# --------------------------------------------------------------------------- #
# night owl                                                                   #
# --------------------------------------------------------------------------- #
def test_night_owl_verdict() -> None:
    # all prompts at 23:00 / 01:00 UTC -> night-owl
    sessions = [
        [
            user_prompt("x", "2026-01-01T23:00:00Z"),
            user_prompt("y", "2026-01-02T01:00:00Z"),
            user_prompt("z", "2026-01-02T02:00:00Z"),
        ]
    ]
    stats = bp.compute_stats(sessions, tz=UTC)
    assert stats["night_owl"]["verdict"] == "night-owl"
    assert stats["hour_of_day"]["23"] == 1
    assert stats["hour_of_day"]["1"] == 1


def test_nine_to_five_verdict() -> None:
    sessions = [
        [
            user_prompt("x", "2026-01-01T10:00:00Z"),
            user_prompt("y", "2026-01-01T13:00:00Z"),
            user_prompt("z", "2026-01-01T15:00:00Z"),
        ]
    ]
    stats = bp.compute_stats(sessions, tz=UTC)
    assert stats["night_owl"]["verdict"] == "9-5"


# --------------------------------------------------------------------------- #
# tools                                                                       #
# --------------------------------------------------------------------------- #
def test_tool_ranking_and_diversity() -> None:
    sessions = [
        [
            assistant("2026-01-01T10:00:00Z", tools=["Read", "Read", "Edit"]),
            assistant("2026-01-01T10:01:00Z", tools=["Read", "Bash"]),
        ]
    ]
    stats = bp.compute_stats(sessions, tz=UTC)
    ranking = dict(stats["tools"]["ranking"])
    assert ranking["Read"] == 3
    assert ranking["Edit"] == 1
    assert ranking["Bash"] == 1
    assert stats["tools"]["diversity"] == 3
    # ranking sorted desc by count -> Read first
    assert stats["tools"]["ranking"][0][0] == "Read"


# --------------------------------------------------------------------------- #
# longest session                                                             #
# --------------------------------------------------------------------------- #
def test_longest_session_duration() -> None:
    sessions = [
        [
            user_prompt("a", "2026-01-01T10:00:00Z", session="short"),
            assistant("2026-01-01T10:05:00Z", session="short"),
        ],
        [
            user_prompt("a", "2026-01-02T10:00:00Z", session="long"),
            assistant("2026-01-02T11:00:00Z", session="long"),
        ],
    ]
    stats = bp.compute_stats(sessions, tz=UTC)
    assert stats["longest_session"]["session_id"] == "long"
    assert stats["longest_session"]["duration_minutes"] == 60


# --------------------------------------------------------------------------- #
# n-grams                                                                     #
# --------------------------------------------------------------------------- #
def test_ngrams_top_phrase() -> None:
    sessions = [
        [
            user_prompt("fix the bug", "2026-01-01T10:00:00Z"),
            user_prompt("fix the test", "2026-01-01T10:01:00Z"),
            user_prompt("fix the lint", "2026-01-01T10:02:00Z"),
        ]
    ]
    stats = bp.compute_stats(sessions, tz=UTC)
    bigrams = dict(stats["ngrams"]["2"])
    assert bigrams["fix the"] == 3


# --------------------------------------------------------------------------- #
# trajectory                                                                  #
# --------------------------------------------------------------------------- #
def test_trajectory_split_reports_thirds() -> None:
    # 6 sessions, chronological; first third = 2, last third = 2
    sessions = []
    for i in range(6):
        day = i + 1
        sessions.append(
            [user_prompt("hello world here", f"2026-01-0{day}T10:00:00Z", session=f"s{i}")]
        )
    stats = bp.compute_stats(sessions, tz=UTC)
    assert stats["trajectory"]["first_third"]["sessions"] == 2
    assert stats["trajectory"]["last_third"]["sessions"] == 2


def test_trajectory_insufficient_when_too_few_sessions() -> None:
    sessions = [[user_prompt("a", "2026-01-01T10:00:00Z")]]
    stats = bp.compute_stats(sessions, tz=UTC)
    assert stats["trajectory"]["status"] == "insufficient"


def test_trajectory_names_excluded_middle_band() -> None:
    # 7 sessions -> third=2, first 2 + last 2, middle 3 excluded (not hidden)
    sessions = [
        [user_prompt("hi there now", f"2026-01-0{i + 1}T10:00:00Z", session=f"s{i}")]
        for i in range(7)
    ]
    stats = bp.compute_stats(sessions, tz=UTC)
    assert stats["trajectory"]["first_third"]["sessions"] == 2
    assert stats["trajectory"]["last_third"]["sessions"] == 2
    assert stats["trajectory"]["middle_sessions_excluded"] == 3


# --------------------------------------------------------------------------- #
# honest-metrics guards (from code review)                                    #
# --------------------------------------------------------------------------- #
def test_p80_is_null_for_small_n() -> None:
    sessions = [
        [user_prompt(t, f"2026-01-01T10:0{i}:00Z") for i, t in enumerate(["a", "a b", "a b c"])]
    ]
    stats = bp.compute_stats(sessions, tz=UTC)
    # n=3 (<5) -> p80 meaningless -> null, not a fabricated number
    assert stats["prompt_length"]["words"]["p80"] is None
    assert stats["prompt_length"]["words"]["median"] == 2


def test_naive_timestamp_excluded_from_hours() -> None:
    # no 'Z'/offset -> naive -> no true wall-clock hour -> skipped
    sessions = [[user_prompt("x", "2026-01-01T23:00:00")]]
    stats = bp.compute_stats(sessions, tz=UTC)
    assert sum(stats["hour_of_day"].values()) == 0
    assert stats["night_owl"]["verdict"] == "insufficient"


# --------------------------------------------------------------------------- #
# robustness                                                                  #
# --------------------------------------------------------------------------- #
def test_empty_input_is_safe() -> None:
    stats = bp.compute_stats([], tz=UTC)
    assert stats["window"]["sessions"] == 0
    assert stats["models"] == {}
    assert stats["steering"]["status"] == "deferred-to-pass-2"


def test_malformed_line_counted_and_skipped(tmp_path) -> None:
    f = tmp_path / "s.jsonl"
    good = '{"type":"user","timestamp":"2026-01-01T10:00:00Z","sessionId":"s1","message":{"content":"hi"}}'
    f.write_text(good + "\n" + "{not json}\n", encoding="utf-8")
    events, skipped = bp.load_session_file(f)
    assert len(events) == 1
    assert skipped == 1


def test_load_skips_non_object_lines(tmp_path) -> None:
    f = tmp_path / "s.jsonl"
    f.write_text('"a bare string"\n[1,2,3]\n', encoding="utf-8")
    events, skipped = bp.load_session_file(f)
    assert events == []
    assert skipped == 2


# --------------------------------------------------------------------------- #
# IO: collect + main                                                          #
# --------------------------------------------------------------------------- #
def _write_jsonl(path, events: list[dict]) -> None:
    import json as _json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(_json.dumps(e) for e in events) + "\n", encoding="utf-8"
    )


def test_collect_filters_by_window(tmp_path) -> None:
    # "future" ts is always within any look-back window; year-2000 never is.
    _write_jsonl(
        tmp_path / "a" / "recent.jsonl",
        [user_prompt("hi", "2099-01-01T10:00:00Z", session="recent")],
    )
    _write_jsonl(
        tmp_path / "b" / "old.jsonl",
        [user_prompt("hi", "2000-01-01T10:00:00Z", session="old")],
    )
    sessions, sampling = bp.collect(tmp_path, window_days=30)
    assert sampling["files_total"] == 2
    assert sampling["files_in_window"] == 1
    assert len(sessions) == 1


def test_main_writes_valid_json(tmp_path) -> None:
    import json as _json

    _write_jsonl(
        tmp_path / "p" / "s.jsonl",
        [
            user_prompt("do a thing", "2099-01-01T23:00:00Z"),
            assistant("2099-01-01T23:00:05Z", tools=["Read"]),
        ],
    )
    out = tmp_path / "stats.json"
    rc = bp.main(["--root", str(tmp_path), "--days", "365000", "--out", str(out)])
    assert rc == 0
    data = _json.loads(out.read_text(encoding="utf-8"))
    assert data["schema_version"] == bp.SCHEMA_VERSION
    assert data["window"]["sessions"] == 1
    assert "sampling" in data


def test_main_missing_root_returns_error(tmp_path) -> None:
    rc = bp.main(["--root", str(tmp_path / "nope"), "--out", str(tmp_path / "o.json")])
    assert rc == 1
