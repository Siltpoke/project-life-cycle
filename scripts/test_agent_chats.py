from __future__ import annotations

import io
import json
import os
from pathlib import Path as _Path

import pytest

import agent_chats as ac


def _rec(**kw):
    base = dict(
        resume_id="id1", family="claude", model="opus-4.8", intensity="high",
        repo="proj", branch="main", worktree="/w/proj", head_sha="abc123",
        dirty=True, topic="a topic", tags=["x", "y"], transcript_path="/t/s.jsonl",
        capture_source="skill", created_at="2026-07-06 10:00",
        last_updated="2026-07-06 10:00", msg_count=8,
    )
    base.update(kw)
    return ac.ChatRecord(**base)


def test_record_roundtrips_all_fields():
    rec = _rec()
    text = ac.render_lines([rec])
    parsed = ac.parse_lines(text)
    assert len(parsed) == 1
    assert ac.record_to_dict(parsed[0]) == ac.record_to_dict(rec)
    assert parsed[0].dirty is True
    assert parsed[0].msg_count == 8
    assert parsed[0].tags == ["x", "y"]


def test_parse_skips_blank_and_bad_lines():
    text = '\n{"resume_id": "id1", "family": "claude"}\n   \nnot json\n'
    parsed = ac.parse_lines(text)
    assert len(parsed) == 1
    assert parsed[0].resume_id == "id1"
    # missing keys default, never crash
    assert parsed[0].dirty is False
    assert parsed[0].msg_count == 0
    assert parsed[0].tags == []


def test_render_sorts_newest_first():
    rows = [_rec(resume_id="old", last_updated="2026-07-06 09:00"),
            _rec(resume_id="new", last_updated="2026-07-06 12:00")]
    text = ac.render_lines(rows)
    assert text.index("new") < text.index("old")


def test_render_empty_is_empty_string():
    assert ac.render_lines([]) == ""


def test_upsert_replaces_same_family_and_id():
    rows = [_rec(resume_id="id1", topic="old")]
    out = ac.upsert_record(rows, _rec(resume_id="id1", topic="new"))
    assert len(out) == 1
    assert out[0].topic == "new"


def test_upsert_appends_new():
    out = ac.upsert_record([_rec(resume_id="id1")], _rec(resume_id="id2"))
    assert {r.resume_id for r in out} == {"id1", "id2"}


def test_upsert_same_id_different_family_are_distinct():
    a = _rec(resume_id="shared", family="claude")
    b = _rec(resume_id="shared", family="codex")
    out = ac.upsert_record([a], b)
    assert len(out) == 2


def test_upsert_preserves_created_at():
    old = _rec(resume_id="id1", created_at="2026-07-01 09:00", last_updated="2026-07-01 09:00")
    new = _rec(resume_id="id1", created_at="2026-07-06 10:00",
               last_updated="2026-07-06 10:00", topic="updated")
    out = ac.upsert_record([old], new)
    assert len(out) == 1
    assert out[0].created_at == "2026-07-01 09:00"   # preserved
    assert out[0].last_updated == "2026-07-06 10:00"  # bumped
    assert out[0].topic == "updated"


def test_hook_over_skill_preserves_curated():
    """Trigger B (hook) landing after Trigger A (skill) must keep curated fields,
    but refresh mechanical fields (msg_count, model, etc.)."""
    skill = _rec(
        resume_id="id1", capture_source="skill", topic="Profit model design",
        intensity="high", tags=["profit", "pricing"], msg_count=5,
        model="opus-4.8", created_at="2026-07-06 09:00", last_updated="2026-07-06 09:00",
    )
    hook = _rec(
        resume_id="id1", capture_source="hook", topic="first user msg",
        intensity="", tags=[], msg_count=40, model="opus-4.8",
        created_at="2026-07-06 12:00", last_updated="2026-07-06 12:00",
    )
    out = ac.upsert_record(ac.upsert_record([], skill), hook)
    assert len(out) == 1
    row = out[0]
    assert row.topic == "Profit model design"
    assert row.intensity == "high"
    assert row.tags == ["profit", "pricing"]
    assert row.msg_count == 40
    assert row.model == "opus-4.8"
    assert row.capture_source == "skill"
    assert row.created_at == "2026-07-06 09:00"


def test_hook_over_skill_backfills_missing_curated():
    """When the skill record left curated fields blank, the hook's mechanical
    values should backfill them instead of staying blank."""
    skill = _rec(resume_id="id1", capture_source="skill", topic="",
                  created_at="2026-07-06 09:00", last_updated="2026-07-06 09:00")
    hook = _rec(resume_id="id1", capture_source="hook", topic="mech",
                created_at="2026-07-06 12:00", last_updated="2026-07-06 12:00")
    out = ac.upsert_record(ac.upsert_record([], skill), hook)
    assert out[0].topic == "mech"


def test_skill_over_hook_full_replace():
    """A handoff skill capture after a prior hook capture should fully replace —
    the curated fields win outright, no merge."""
    hook = _rec(resume_id="id1", capture_source="hook", topic="mech topic",
                intensity="", tags=[], msg_count=40,
                created_at="2026-07-06 09:00", last_updated="2026-07-06 09:00")
    skill = _rec(resume_id="id1", capture_source="skill", topic="curated topic",
                 intensity="high", tags=["a"], msg_count=0,
                 created_at="2026-07-06 12:00", last_updated="2026-07-06 12:00")
    out = ac.upsert_record(ac.upsert_record([], hook), skill)
    assert len(out) == 1
    row = out[0]
    assert row.topic == "curated topic"
    assert row.intensity == "high"
    assert row.tags == ["a"]
    assert row.msg_count == 0
    assert row.capture_source == "skill"
    assert row.created_at == "2026-07-06 09:00"  # earliest still preserved


def test_hook_over_hook_full_replace():
    """Two hook captures on the same key: second fully replaces the first
    (except created_at) — no merge logic applies between hook and hook."""
    first = _rec(resume_id="id1", capture_source="hook", topic="first mech",
                 msg_count=10, created_at="2026-07-06 09:00", last_updated="2026-07-06 09:00")
    second = _rec(resume_id="id1", capture_source="hook", topic="second mech",
                  msg_count=20, created_at="2026-07-06 12:00", last_updated="2026-07-06 12:00")
    out = ac.upsert_record(ac.upsert_record([], first), second)
    assert len(out) == 1
    row = out[0]
    assert row.topic == "second mech"
    assert row.msg_count == 20
    assert row.capture_source == "hook"
    assert row.created_at == "2026-07-06 09:00"


def test_upsert_is_atomic_via_replace(tmp_path):
    """upsert() should write through a same-dir temp file + os.replace, leaving
    no stray temp files behind and correct final content after two sequential
    writes."""
    reg = tmp_path / "docs" / "agent-chats-index.md"
    ac.upsert(ac.ChatRecord(resume_id="id1", last_updated="2026-07-06 10:00"), reg)
    ac.upsert(ac.ChatRecord(resume_id="id2", last_updated="2026-07-06 11:00"), reg)
    rows = ac.parse_lines(reg.read_text(encoding="utf-8"))
    assert {r.resume_id for r in rows} == {"id1", "id2"}
    # no leftover temp files in the registry's directory
    leftovers = [p for p in reg.parent.iterdir() if p != reg]
    assert leftovers == []


def test_blank_or_family_literal_id_dedups_on_transcript_path():
    # Codex sets session_id to the literal "codex"; a blank id also falls back.
    a = _rec(resume_id="", family="codex", transcript_path="/t/a.jsonl")
    b = _rec(resume_id="codex", family="codex", transcript_path="/t/a.jsonl")
    c = _rec(resume_id="codex", family="codex", transcript_path="/t/b.jsonl")
    out = ac.upsert_record(ac.upsert_record([a], b), c)
    assert len(out) == 2  # a & b collapse (same path); c distinct


def test_dedup_key_empty_when_both_ids_blank():
    r = _rec(resume_id="", family="codex", transcript_path="")
    assert ac._dedup_key(r) == ("codex", "")


def test_parse_skips_wrong_typed_json_fields():
    """Parse lines should skip lines with wrong-typed fields (e.g. tags as int, msg_count as array)."""
    text = (
        '{"resume_id": "good1", "family": "claude"}\n'
        '{"resume_id": "bad_tags", "family": "claude", "tags": 5}\n'
        '{"resume_id": "bad_msgcount", "family": "claude", "msg_count": [1, 2]}\n'
        '{"resume_id": "good2", "family": "claude"}\n'
    )
    parsed = ac.parse_lines(text)
    # Should only parse the good records, skip the ones with wrong-typed fields
    assert len(parsed) == 2
    assert parsed[0].resume_id == "good1"
    assert parsed[1].resume_id == "good2"


def test_render_tiebreak_family_ascending_on_same_timestamp():
    """When last_updated is the same, family should be ascending, not reversed."""
    rows = [
        _rec(resume_id="z1", family="zebra", last_updated="2026-07-06 12:00"),
        _rec(resume_id="a1", family="apple", last_updated="2026-07-06 12:00"),
    ]
    text = ac.render_lines(rows)
    # apple should come before zebra (ascending on family when timestamps match)
    assert text.index("apple") < text.index("zebra")


def test_upsert_tags_copied_not_referenced():
    """Upsert should copy tags, not store a reference to the input record's tags list."""
    new = _rec(resume_id="id1", tags=["x", "y"])
    out = ac.upsert_record([], new)

    # Mutate the input record's tags
    new.tags.append("z")

    # The stored record should not be affected
    assert out[0].tags == ["x", "y"]
    assert new.tags == ["x", "y", "z"]


def test_upsert_tags_copied_on_replace():
    """When replacing an existing record, tags should be copied, not referenced."""
    old = _rec(resume_id="id1", tags=["old"])
    new = _rec(resume_id="id1", tags=["new"])
    out = ac.upsert_record([old], new)

    # Mutate the input record's tags
    new.tags.append("mutated")

    # The stored record should not be affected
    assert out[0].tags == ["new"]
    assert new.tags == ["new", "mutated"]


def test_resolve_git_fields_on_this_repo():
    fields = ac.resolve_git_fields(str(ac.REPO))
    assert fields["repo"]        # basename, non-empty
    assert fields["head_sha"]    # real short sha
    assert isinstance(fields["dirty"], bool)


def test_resolve_git_fields_non_git_dir(tmp_path):
    fields = ac.resolve_git_fields(str(tmp_path))
    assert fields["head_sha"] == ""
    assert fields["branch"] == ""
    assert fields["dirty"] is False
    assert fields["repo"] == tmp_path.name


def test_upsert_creates_file_and_appends(tmp_path):
    reg = tmp_path / "docs" / "agent-chats-index.md"
    ac.upsert(ac.ChatRecord(resume_id="id1", last_updated="2026-07-06 10:00"), reg)
    ac.upsert(ac.ChatRecord(resume_id="id2", last_updated="2026-07-06 11:00"), reg)
    rows = ac.parse_lines(reg.read_text(encoding="utf-8"))
    assert {r.resume_id for r in rows} == {"id1", "id2"}


def test_upsert_same_id_updates_not_duplicates(tmp_path):
    reg = tmp_path / "docs" / "agent-chats-index.md"
    ac.upsert(ac.ChatRecord(resume_id="id1", topic="old", created_at="2026-07-06 10:00",
                            last_updated="2026-07-06 10:00"), reg)
    ac.upsert(ac.ChatRecord(resume_id="id1", topic="new", created_at="2026-07-06 12:00",
                            last_updated="2026-07-06 12:00"), reg)
    rows = ac.parse_lines(reg.read_text(encoding="utf-8"))
    assert len(rows) == 1
    assert rows[0].topic == "new"
    assert rows[0].created_at == "2026-07-06 10:00"  # preserved across file round-trip


def test_cli_upsert_noops_without_ids(tmp_path, monkeypatch):
    reg = tmp_path / "docs" / "agent-chats-index.md"
    monkeypatch.delenv("CLAUDE_CODE_CHILD_SESSION", raising=False)
    rc = ac.main(["upsert", "--resume-id", "", "--transcript-path", "",
                  "--cwd", str(tmp_path), "--registry", str(reg)])
    assert rc == 0
    assert not reg.exists()


def test_cli_upsert_writes_even_with_child_session_env(tmp_path, monkeypatch):
    # CLAUDE_CODE_CHILD_SESSION is set for every Claude Code Bash subprocess,
    # main session included, so it must NOT gate the upsert.
    reg = tmp_path / "docs" / "agent-chats-index.md"
    monkeypatch.setenv("CLAUDE_CODE_CHILD_SESSION", "1")
    rc = ac.main(["upsert", "--resume-id", "id1", "--cwd", str(tmp_path),
                  "--registry", str(reg)])
    assert rc == 0
    assert reg.exists()
    assert ac.parse_lines(reg.read_text(encoding="utf-8"))[0].resume_id == "id1"


def test_cli_upsert_writes_row_with_authored_and_git_fields(tmp_path, monkeypatch):
    reg = tmp_path / "docs" / "agent-chats-index.md"
    monkeypatch.delenv("CLAUDE_CODE_CHILD_SESSION", raising=False)
    rc = ac.main(["upsert", "--resume-id", "id9", "--family", "claude",
                  "--model", "opus-4.8", "--intensity", "high",
                  "--topic", "hello world", "--tags", "x, y",
                  "--cwd", str(tmp_path), "--now", "2026-07-06 10:00",
                  "--registry", str(reg)])
    assert rc == 0
    rows = ac.parse_lines(reg.read_text(encoding="utf-8"))
    assert rows[0].resume_id == "id9"
    assert rows[0].model == "opus-4.8"
    assert rows[0].intensity == "high"
    assert rows[0].tags == ["x", "y"]
    assert rows[0].capture_source == "skill"
    assert rows[0].created_at == "2026-07-06 10:00"
    assert rows[0].repo == tmp_path.name  # non-git tmp → basename


_CLAUDE = "\n".join(json.dumps(o) for o in [
    {"type": "user", "message": {"role": "user", "content": "How do I make money with this?"}},
    {"type": "assistant", "message": {"role": "assistant", "content": "Here are options"}},
    {"type": "user", "message": {"role": "user", "content": "tell me more"}},
    {"type": "assistant", "message": {"role": "assistant", "content": "..."}},
])

_CODEX = "\n".join(json.dumps(o) for o in [
    {"type": "session_meta", "payload": {"model": "gpt-5.5"}},
    {"type": "event_msg", "payload": {"type": "user_message", "message": "codex please refactor"}},
    {"type": "event_msg", "payload": {"type": "agent_message", "message": "done"}},
    {"type": "event_msg", "payload": {"type": "user_message", "message": "again"}},
    {"type": "event_msg", "payload": {"type": "agent_message", "message": "ok"}},
])


def test_count_turns_claude():
    assert ac.count_turns(_CLAUDE) == 4


def test_count_turns_codex_envelope():
    assert ac.count_turns(_CODEX) == 4  # session_meta not counted


def test_passes_substance_threshold():
    assert ac.passes_substance(_CLAUDE, min_msgs=4) is True
    assert ac.passes_substance("\n".join(_CLAUDE.splitlines()[:2]), min_msgs=4) is False
    assert ac.passes_substance("", min_msgs=4) is False


def test_extract_topic_from_first_user_message():
    assert ac.extract_topic(_CLAUDE).startswith("How do I make money")


def test_extract_topic_codex_first_user_message():
    assert ac.extract_topic(_CODEX).startswith("codex please refactor")


def test_extract_topic_is_first_user_message():
    text = json.dumps({"type": "user",
                       "message": {"role": "user", "content": "Profit model design"}})
    assert "Profit model design" in ac.extract_topic(text)


def test_extract_topic_truncates():
    long = "x" * 200
    line = json.dumps({"type": "user", "message": {"role": "user", "content": long}})
    assert len(ac.extract_topic(line)) <= 80


def test_extract_topic_default_when_empty():
    assert ac.extract_topic("") == "untitled session"


def test_detect_family_claude():
    assert ac.detect_family(_CLAUDE) == "claude"


def test_detect_family_codex():
    assert ac.detect_family(_CODEX) == "codex"


def test_detect_family_empty_defaults_claude():
    assert ac.detect_family("") == "claude"


def test_extract_model_claude():
    text = json.dumps({"type": "assistant",
                       "message": {"role": "assistant", "model": "claude-opus-4-8", "content": "hi"}})
    assert ac.extract_model(text, "claude") == "claude-opus-4-8"


def test_extract_model_codex():
    assert ac.extract_model(_CODEX, "codex") == "gpt-5.5"


def test_extract_model_unknown_is_empty():
    assert ac.extract_model(_CLAUDE, "claude") == ""


def test_extract_model_claude_ignores_nonassistant_model():
    """Claude transcript with user turn carrying model should be ignored; extract from assistant turn."""
    text = "\n".join(json.dumps(o) for o in [
        {"type": "user", "message": {"role": "user", "model": "WRONG", "content": "hi"}},
        {"type": "assistant", "message": {"role": "assistant", "model": "opus-4.8", "content": "hello"}},
    ])
    # Should return "opus-4.8" from assistant, NOT "WRONG" from user
    assert ac.extract_model(text, "claude") == "opus-4.8"


def test_extract_model_codex_turn_context():
    """Codex transcript with turn_context event should extract model from payload."""
    text = "\n".join(json.dumps(o) for o in [
        {"type": "turn_context", "payload": {"model": "gpt-5.5"}},
        {"type": "event_msg", "payload": {"type": "user_message", "message": "refactor"}},
        {"type": "event_msg", "payload": {"type": "agent_message", "message": "done"}},
    ])
    assert ac.extract_model(text, "codex") == "gpt-5.5"
    assert ac.detect_family(text) == "codex"


def test_capture_hook_writes_claude_row(tmp_path, monkeypatch):
    reg = tmp_path / "docs" / "agent-chats-index.md"
    t = tmp_path / "sess.jsonl"
    t.write_text(_CLAUDE, encoding="utf-8")
    payload = json.dumps({"session_id": "abc123", "transcript_path": str(t)})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    rc = ac.main(["capture-hook", "--cwd", str(tmp_path), "--registry", str(reg),
                  "--now", "2026-07-06 10:00"])
    assert rc == 0
    rows = ac.parse_lines(reg.read_text(encoding="utf-8"))
    assert rows[0].resume_id == "abc123"
    assert rows[0].family == "claude"
    assert rows[0].capture_source == "hook"
    assert rows[0].intensity == ""
    assert rows[0].msg_count == 4
    assert rows[0].topic.startswith("How do I make money")


def test_capture_hook_codex_uses_host_hint_and_model(tmp_path, monkeypatch):
    reg = tmp_path / "docs" / "agent-chats-index.md"
    t = tmp_path / "sess.jsonl"
    t.write_text(_CODEX, encoding="utf-8")
    payload = json.dumps({"session_id": "codex", "transcript_path": str(t),
                          "agent_family": "codex"})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    rc = ac.main(["capture-hook", "--cwd", str(tmp_path), "--registry", str(reg)])
    assert rc == 0
    rows = ac.parse_lines(reg.read_text(encoding="utf-8"))
    assert rows[0].family == "codex"
    assert rows[0].model == "gpt-5.5"
    # session_id == "codex" literal falls back to transcript_path for the key
    assert rows[0].transcript_path == str(t)


def test_capture_hook_skips_trivial_session(tmp_path, monkeypatch):
    reg = tmp_path / "docs" / "agent-chats-index.md"
    t = tmp_path / "sess.jsonl"
    t.write_text("\n".join(_CLAUDE.splitlines()[:2]), encoding="utf-8")
    payload = json.dumps({"session_id": "abc123", "transcript_path": str(t)})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    assert ac.main(["capture-hook", "--registry", str(reg)]) == 0
    assert not reg.exists()


def test_capture_hook_skips_missing_transcript(tmp_path, monkeypatch):
    reg = tmp_path / "docs" / "agent-chats-index.md"
    payload = json.dumps({"session_id": "abc", "transcript_path": str(tmp_path / "no.jsonl")})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    assert ac.main(["capture-hook", "--registry", str(reg)]) == 0
    assert not reg.exists()


def test_capture_hook_skips_without_session_id(tmp_path, monkeypatch):
    reg = tmp_path / "docs" / "agent-chats-index.md"
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({})))
    assert ac.main(["capture-hook", "--registry", str(reg)]) == 0
    assert not reg.exists()


def test_capture_hook_bad_stdin_is_noop(tmp_path, monkeypatch):
    reg = tmp_path / "docs" / "agent-chats-index.md"
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    assert ac.main(["capture-hook", "--registry", str(reg)]) == 0
    assert not reg.exists()


def test_capture_hook_null_session_id_noops(tmp_path, monkeypatch):
    """When session_id is JSON null, capture-hook should noop (return 0, create no registry)."""
    reg = tmp_path / "docs" / "agent-chats-index.md"
    t = tmp_path / "sess.jsonl"
    t.write_text(_CLAUDE, encoding="utf-8")  # Substantive transcript (4 turns)
    payload = json.dumps({"session_id": None, "transcript_path": str(t)})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    rc = ac.main(["capture-hook", "--cwd", str(tmp_path), "--registry", str(reg)])
    assert rc == 0
    assert not reg.exists()


@pytest.mark.skipif(os.geteuid() == 0, reason="Cannot test chmod perms as root")
def test_capture_hook_unreadable_transcript_noops(tmp_path, monkeypatch):
    """When transcript file is unreadable (permission denied), capture-hook should noop."""
    reg = tmp_path / "docs" / "agent-chats-index.md"
    t = tmp_path / "sess.jsonl"
    t.write_text(_CLAUDE, encoding="utf-8")  # Substantive transcript (4 turns)
    try:
        os.chmod(str(t), 0o000)
        payload = json.dumps({"session_id": "abc123", "transcript_path": str(t)})
        monkeypatch.setattr("sys.stdin", io.StringIO(payload))
        rc = ac.main(["capture-hook", "--cwd", str(tmp_path), "--registry", str(reg)])
        assert rc == 0
        assert not reg.exists()
    finally:
        # Ensure cleanup: restore read permission so tmp_path cleanup works
        os.chmod(str(t), 0o644)


_SKILL = _Path(__file__).resolve().parent.parent / "skills" / "project-lifecycle"


def test_registry_reference_exists_and_documents_commands():
    ref = _SKILL / "references" / "agent-chats-registry.md"
    assert ref.exists()
    body = ref.read_text(encoding="utf-8")
    assert "agent_chats.py upsert" in body
    assert "CLAUDE_CODE_SESSION_ID" in body
    assert "claude --resume" in body       # family→command map
    assert "cost" in body.lower()          # cost-exclusion note


def test_hook_reference_documents_sessionend_and_machine_local():
    # agent-chats-hook.md was folded into agent-chats-registry.md (an earlier commit);
    # the hook documentation now lives in the consolidated registry reference.
    ref = _SKILL / "references" / "agent-chats-registry.md"
    assert ref.exists()
    body = ref.read_text(encoding="utf-8")
    assert "SessionEnd" in body
    assert "agent_chats.py capture-hook" in body
    assert "machine-local" in body.lower()


def test_skill_points_at_reference():
    body = (_SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert "agent-chats-registry.md" in body
