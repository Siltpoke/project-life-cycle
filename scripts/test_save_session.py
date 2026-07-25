#!/usr/bin/env python3
"""Tests for save_session.py (PLC-native automatic session save)."""

from __future__ import annotations

import io
import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import save_session as ss  # noqa: E402


# --- fixtures ---------------------------------------------------------------

def _transcript(*events: dict) -> str:
    return "\n".join(json.dumps(e) for e in events) + "\n"


@pytest.fixture
def sample() -> str:
    return _transcript(
        {"type": "user", "message": {"role": "user", "content": "first ask"}},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "ok"},
            {"type": "tool_use", "name": "Read", "input": {"file_path": "/a.py"}},
        ]}},
        {"type": "user", "message": {"role": "user", "content": "second ask"}},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "name": "Edit", "input": {"file_path": "/src/x.py"}},
            {"type": "tool_use", "name": "Write", "input": {"file_path": "/src/y.py"}},
        ]}},
        # a tool-result-shaped user turn that must NOT become a "task"
        {"type": "user", "message": {"role": "user", "content": "<tool_result>…"}},
    )


@pytest.fixture
def git() -> dict:
    return {"repo": "myproj", "branch": "main", "worktree": "/w", "head_sha": "abc",
            "dirty": False}


# --- extraction (AC2) --------------------------------------------------

def test_extract_tasks_are_user_messages(sample, git):
    d = ss.extract_digest(sample, {"session_id": "sess12345678"}, git)
    assert d["tasks"] == ["first ask", "second ask"]  # <tool_result> excluded


def test_extract_files_only_write_tools(sample, git):
    d = ss.extract_digest(sample, {}, git)
    assert d["files"] == ["/src/x.py", "/src/y.py"]  # Read's /a.py excluded


def test_extract_tools_deduped_in_order(sample, git):
    d = ss.extract_digest(sample, {}, git)
    assert d["tools"] == ["Read", "Edit", "Write"]


def test_extract_user_count_includes_all_user_turns(sample, git):
    d = ss.extract_digest(sample, {}, git)
    assert d["user_count"] == 3


def test_extract_caps(git):
    events = [{"type": "user", "message": {"role": "user", "content": f"m{i}"}}
              for i in range(25)]
    d = ss.extract_digest(_transcript(*events), {}, git)
    assert len(d["tasks"]) == ss.MAX_TASKS
    assert d["tasks"][-1] == "m24"  # keeps the LAST N


# --- session key + sanitize (AC3) --------------------------------------

def test_session_key_uses_full_session_id(git):
    assert ss.session_key({"session_id": "abcdef1234567890"}, git) == "abcdef1234567890"


def test_session_key_no_collision_on_shared_tail(git):
    # two ids sharing the trailing 8 chars must NOT map to one key
    a = ss.session_key({"session_id": "AAAA-1234abcd"}, git)
    b = ss.session_key({"session_id": "BBBB-1234abcd"}, git)
    assert a != b


def test_session_key_fallback_when_no_session_id(git):
    key = ss.session_key({"transcript_path": "/t.jsonl"}, git)
    assert key.startswith("myproj-") and len(key) == len("myproj-") + 8


def test_sanitize_non_ascii_hashes(git):
    out = ss.sanitize_id("café-ñoño")  # accented Latin, non-ASCII
    assert len(out) == 8 and out.isalnum()


def test_sanitize_strips_unsafe():
    assert ss.sanitize_id("a/b c!d") == "abcd"


# --- render -----------------------------------------------------------

def test_render_contains_all_sections(sample, git):
    d = ss.extract_digest(sample, {"session_id": "s"}, git)
    out = ss.render_digest(d)
    for header in ("# Session:", "## Tasks", "## Files Modified",
                   "## Tools Used", "## Stats", "Total user messages: 3"):
        assert header in out


def test_render_empty_sections_say_none(git):
    d = ss.extract_digest("", {}, git)
    out = ss.render_digest(d)
    assert "- (none)" in out and "Total user messages: 0" in out


# --- atomic write + full run (AC1, AC3, AC4) ---------------------------

def test_run_writes_named_digest(tmp_path, sample, monkeypatch):
    tp = tmp_path / "t.jsonl"
    tp.write_text(sample)
    monkeypatch.setattr(ss, "resolve_git_fields", lambda cwd: {
        "repo": "myproj", "branch": "main", "worktree": "/w", "head_sha": "x",
        "dirty": False})
    out = ss.run({"session_id": "sess99887766", "transcript_path": str(tp)},
                 base_dir=tmp_path)
    assert out.exists() and out.name.endswith("-myproj-sess99887766.md")
    assert "second ask" in out.read_text()


def test_run_preserves_started_across_rewrites(tmp_path, sample, monkeypatch):
    tp = tmp_path / "t.jsonl"
    tp.write_text(sample)
    monkeypatch.setattr(ss, "resolve_git_fields", lambda cwd: {
        "repo": "p", "branch": "b", "worktree": "/w", "head_sha": "x", "dirty": False})
    payload = {"session_id": "sess00110011", "transcript_path": str(tp)}
    first = ss.run(payload, base_dir=tmp_path)
    started = ss._existing_started(first)
    time.sleep(0.01)
    second = ss.run(payload, base_dir=tmp_path)
    assert ss._existing_started(second) == started  # Started frozen


def test_atomic_write_no_tmp_left(tmp_path):
    p = tmp_path / "d.md"
    ss.atomic_write(p, "hi")
    assert p.read_text() == "hi"
    assert not list(tmp_path.glob(".*.tmp"))


def test_run_reuses_file_across_midnight(tmp_path, sample, monkeypatch):
    """A session crossing midnight updates ONE file, not two dated files."""
    tp = tmp_path / "t.jsonl"; tp.write_text(sample)
    monkeypatch.setattr(ss, "resolve_git_fields", lambda cwd: {
        "repo": "myproj", "branch": "b", "worktree": "/w", "head_sha": "x",
        "dirty": False})
    # a digest already written "yesterday" for the same session key
    yesterday = tmp_path / "2026-07-15-myproj-sess99887766.md"
    yesterday.write_text("# Session: 2026-07-15\n**Started:** 2026-07-15 23:59"
                         "   **Last Updated:** 2026-07-15 23:59\n")
    out = ss.run({"session_id": "sess99887766", "transcript_path": str(tp)},
                 base_dir=tmp_path)
    assert out == yesterday                              # reused, not a new date
    assert len(list(tmp_path.glob("*-myproj-sess99887766.md"))) == 1  # exactly one file


def test_render_includes_dir(sample, git):
    d = ss.extract_digest(sample, {}, git)
    d["worktree"] = "/some/where"
    assert "**Dir:** /some/where" in ss.render_digest(d)


def test_read_tail_missing_file_returns_empty(tmp_path):
    assert ss.read_tail(tmp_path / "nope.jsonl") == ""       # OSError branch → ""


# --- retention --------------------------------------------------------

def test_prune_by_count(tmp_path):
    now = time.time()
    for i in range(60):
        p = tmp_path / f"2026-07-16-proj-{i:03d}.md"
        p.write_text("x")
        os.utime(p, (now - i, now - i))  # newest = i0
    deleted = ss.prune(tmp_path, days=9999, count=50, now=now)
    assert deleted == 10 and len(list(tmp_path.glob("*.md"))) == 50


def test_prune_by_age(tmp_path):
    now = time.time()
    fresh = tmp_path / "a.md"; fresh.write_text("x"); os.utime(fresh, (now, now))
    old = tmp_path / "b.md"; old.write_text("x")
    os.utime(old, (now - 40 * 86400, now - 40 * 86400))
    ss.prune(tmp_path, days=30, count=50, now=now)
    assert fresh.exists() and not old.exists()


# --- select_digest: the /recall read side -----------------------------

def _seed(directory, name, mtime, project="myproj"):
    """Seed a digest whose **Project:** header (the authoritative scope) is `project`."""
    p = directory / name
    p.write_text(f"# Session\n**Project:** {project}   **Branch:** b   **Session:** k\n")
    os.utime(p, (mtime, mtime))
    return p


def test_select_no_arg_picks_newest_for_repo(tmp_path):
    now = time.time()
    _seed(tmp_path, "2026-07-14-myproj-aaa.md", now - 200)
    newest = _seed(tmp_path, "2026-07-16-myproj-bbb.md", now - 10)
    _seed(tmp_path, "2026-07-16-other-ccc.md", now, project="other")  # newer, other proj
    pick = ss.select_digest(tmp_path, "myproj", now=now)
    assert pick.path == newest and pick.cross_project is False


def test_select_scopes_by_project_header_not_filename(tmp_path):
    """Regression (historical fix, CRITICAL): repo 'app' must NOT catch 'app-web' digests."""
    now = time.time()
    app = _seed(tmp_path, "2026-07-15-app-abc.md", now - 100, project="app")
    _seed(tmp_path, "2026-07-16-app-web-xyz.md", now, project="app-web")  # newer, prefix
    pick = ss.select_digest(tmp_path, "app", now=now)
    assert pick.path == app and pick.cross_project is False  # not the app-web file
    # and 'app-web' asking gets its own, not 'app'
    pick2 = ss.select_digest(tmp_path, "app-web", now=now)
    assert ss.digest_project(pick2.path) == "app-web" and pick2.cross_project is False


def test_select_no_repo_match_falls_back_global_flagged(tmp_path):
    now = time.time()
    g = _seed(tmp_path, "2026-07-16-otherproj-xyz.md", now - 5, project="otherproj")
    pick = ss.select_digest(tmp_path, "myproj", now=now)
    assert pick.path == g and pick.cross_project is True  # never silent cross-project


def test_select_date_arg_filters(tmp_path):
    now = time.time()
    _seed(tmp_path, "2026-07-16-myproj-a.md", now)
    want = _seed(tmp_path, "2026-07-10-myproj-b.md", now - 100)
    pick = ss.select_digest(tmp_path, "myproj", arg="2026-07-10", now=now)
    assert pick.path == want


def test_select_path_arg_returns_exact(tmp_path):
    p = _seed(tmp_path, "2026-07-16-anyproj-z.md", time.time(), project="anyproj")
    pick = ss.select_digest(tmp_path, "myproj", arg=str(p))
    assert pick.path == p and pick.cross_project is False


def test_select_staleness(tmp_path):
    now = time.time()
    _seed(tmp_path, "2026-07-01-myproj-a.md", now - 9 * 86400)
    pick = ss.select_digest(tmp_path, "myproj", now=now)
    assert pick.stale_days == 9 and pick.stale is True


def test_digest_project_reads_header(tmp_path):
    p = _seed(tmp_path, "2026-07-16-foo-bar.md", time.time(), project="foo-bar")
    assert ss.digest_project(p) == "foo-bar"


def test_select_path_arg_works_when_dir_absent(tmp_path):
    """Teammate-handoff /recall <path> must resolve even on a machine with no digest dir."""
    external = tmp_path / "shared.md"
    external.write_text("# Session\n**Project:** whatever   **Branch:** b\n")
    pick = ss.select_digest(tmp_path / "does-not-exist", "myproj", arg=str(external))
    assert pick is not None and pick.path == external


def test_select_date_arg_global_fallback_flagged(tmp_path):
    now = time.time()
    g = _seed(tmp_path, "2026-07-16-otherproj-x.md", now, project="otherproj")
    pick = ss.select_digest(tmp_path, "myproj", arg="2026-07-16", now=now)
    assert pick.path == g and pick.cross_project is True


def test_select_empty_dir_returns_none(tmp_path):
    assert ss.select_digest(tmp_path / "nope", "myproj") is None
    assert ss.select_digest(tmp_path, "myproj") is None


# --- resume CLI subcommand (read-only /recall dispatch) ---------------------

def test_resume_cli_prints_json_and_is_read_only(tmp_path, monkeypatch, capsys):
    d = tmp_path / "plc-session-data"; d.mkdir()
    f = _seed(d, "2026-07-16-myproj-abc.md", time.time(), project="myproj")
    before = f.stat().st_mtime
    monkeypatch.setattr(ss, "sessions_dir", lambda: d)
    monkeypatch.setattr(ss, "resolve_git_fields", lambda cwd: {"repo": "myproj"})
    assert ss.main(["resume"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["found"] is True and out["project"] == "myproj"
    assert f.stat().st_mtime == before          # read-only: mtime unchanged


def test_resume_cli_not_found(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ss, "sessions_dir", lambda: tmp_path / "empty")
    monkeypatch.setattr(ss, "resolve_git_fields", lambda cwd: {"repo": "myproj"})
    assert ss.main(["resume"]) == 0
    assert json.loads(capsys.readouterr().out) == {"found": False}


def test_resume_cli_does_not_read_stdin(tmp_path, monkeypatch, capsys):
    """The resume subcommand must NOT take the Stop-hook write path."""
    monkeypatch.setattr(ss, "sessions_dir", lambda: tmp_path / "empty")
    monkeypatch.setattr(ss, "resolve_git_fields", lambda cwd: {"repo": "r"})
    # stdin holds a valid Stop payload — resume must ignore it and NOT write
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"session_id": "x"})))
    ss.main(["resume"])
    assert not (tmp_path / "empty").exists()    # no digest written


# --- hook must never crash the session --------------------------------

@pytest.fixture(autouse=True)
def _isolate_sessions_dir(tmp_path, monkeypatch):
    """Never let a test write to the real ~/.claude/plc-session-data/.

    main() → run() uses the real sessions_dir() by default; redirect it so the
    exit-0 tests that exercise the full entrypoint stay hermetic.
    """
    monkeypatch.setattr(ss, "sessions_dir", lambda: tmp_path / "plc-session-data")


def test_main_exit0_on_malformed_stdin(monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("{not json"))
    assert ss.main([]) == 0


def test_main_exit0_on_empty_stdin(monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert ss.main([]) == 0


def test_main_exit0_when_transcript_missing(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "stdin",
                        io.StringIO(json.dumps({"session_id": "s",
                                                "transcript_path": "/nope.jsonl"})))
    assert ss.main([]) == 0


def test_main_happy_path_writes_digest(monkeypatch, tmp_path, sample):
    """main() through the real stdin→json→run() glue lands a digest (not just run())."""
    tp = tmp_path / "t.jsonl"
    tp.write_text(sample)
    monkeypatch.setattr(ss, "resolve_git_fields", lambda cwd: {
        "repo": "myproj", "branch": "b", "worktree": "/w", "head_sha": "x",
        "dirty": False})
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(
        {"session_id": "sess44556677", "transcript_path": str(tp)})))
    assert ss.main([]) == 0
    digests = list((tmp_path / "plc-session-data").glob("*-myproj-sess44556677.md"))
    assert len(digests) == 1 and "second ask" in digests[0].read_text()


# --- read_tail: bounds the READ off disk, not just the parse -----------

def test_read_tail_bounds_bytes(tmp_path):
    big = tmp_path / "big.jsonl"
    # 5000 lines; only the last TAIL_LINES survive, and only the last bytes read
    big.write_text("\n".join(f'{{"n":{i}}}' for i in range(5000)) + "\n")
    out = ss.read_tail(big, max_bytes=2048, max_lines=ss.TAIL_LINES)
    lines = out.splitlines()
    assert len(lines) <= ss.TAIL_LINES
    assert '"n":4999' in out          # kept the tail
    assert '"n":0' not in out         # dropped the head (never read those bytes)


def test_read_tail_small_file_intact(tmp_path):
    p = tmp_path / "s.jsonl"
    p.write_text('{"a":1}\n{"a":2}\n')
    assert ss.read_tail(p) == '{"a":1}\n{"a":2}'


def test_run_never_raises_on_bad_transcript(tmp_path, monkeypatch):
    tp = tmp_path / "bad.jsonl"
    tp.write_text("{broken\n\x00\nnot json")
    monkeypatch.setattr(ss, "resolve_git_fields", lambda cwd: {
        "repo": "p", "branch": "", "worktree": "/w", "head_sha": "", "dirty": False})
    out = ss.run({"session_id": "s12345678", "transcript_path": str(tp)},
                 base_dir=tmp_path)
    assert out.exists()  # a partial/empty digest still lands, no exception


# --- PLC owns its own dir, no external session-tool coupling ----------

def test_writes_only_to_own_dir():
    src = (Path(__file__).resolve().parent / "save_session.py").read_text()
    # the only session dir we build/read is our own — never a bare "session-data"
    # (a common external session-tool dir name).
    assert '"session-data"' not in src
    assert 'plc-session-data' in src


def test_sessions_dir_is_plc_owned():
    d = ss.sessions_dir()
    assert d.name == "plc-session-data"
    assert d.name != "session-data"
