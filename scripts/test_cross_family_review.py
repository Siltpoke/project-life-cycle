"""Tests for scripts/cross-family-review.sh — the cross-family blind-2nd-agent adapter.

The stub `codex` is FAITHFUL to the real CLI's observed shape (probe 2026-07-24,
docs/research/<date>-<id>-codex-probe.md): `codex login status` prints a
"Logged in ..." line; `codex exec ... -o <file>` writes a clean structured JSON
payload to that file and prints JSONL events to stdout. Building the stub on the
REAL shape is the `claude-p` fabricated-envelope lesson applied.

The adapter must ALWAYS exit 0 (a foreign reviewer failing must never block the
brainstorm) and emit {engine,status,pick|null,fallback_reason} to --out.
"""
import json
import os
import stat
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "cross-family-review.sh"

# The real -o payload shape (verbatim field set from the probe).
REAL_PICK = {
    "criteria": ["c1", "c2"],
    "option_holes": [{"option": "A", "strongest_hole": "h"}],
    "independent_pick": "B. the pick",
    "rationale": "because",
    "missing_option": "a 4th",
    "risk_with_pick": "a risk",
}


def _write_stub_codex(bindir: Path, *, mode="ok", authed=True):
    """Write a fake `codex` honoring `login status` + `exec ... -o <file>`.

    mode: ok | unparseable | spawnfail | hang
    """
    codex = bindir / "codex"
    auth_line = "Logged in using ChatGPT" if authed else "Not logged in"
    # The exec branch must find the `-o <file>` pair and write to it.
    # FAITHFULNESS: real codex-cli (0.143.0) writes `login status` to STDERR in BOTH
    # the authed and unauthed cases (verified against the real CLI). The stub must too — an
    # earlier stub echoed the authed line to STDOUT, which masked the gate-2 bug where
    # the probe discarded stderr and always fell back not-authed. Keeping the stub
    # faithful (authed line on stderr) makes test_success_returns_parsed_pick the
    # regression guard for that contract.
    script = f"""#!/usr/bin/env bash
sub="$1"; shift || true
if [ "$sub" = "login" ]; then
  # `codex login status` — status goes to STDERR (both cases), like real codex.
  {"echo '" + auth_line + "' >&2; exit 0" if authed else "echo '" + auth_line + "' >&2; exit 1"}
fi
if [ "$sub" = "exec" ]; then
  out=""
  while [ $# -gt 0 ]; do
    case "$1" in
      -o|--output-last-message) out="$2"; shift 2;;
      *) shift;;
    esac
  done
  case "{mode}" in
    hang) sleep 30;;
    spawnfail) echo '{{"type":"turn.failed"}}'; exit 1;;
    unparseable) [ -n "$out" ] && printf 'not json{{' > "$out"; echo '{{"type":"turn.completed"}}'; exit 0;;
    ok) [ -n "$out" ] && cat > "$out" <<'JSON'
{json.dumps(REAL_PICK)}
JSON
        echo '{{"type":"thread.started","thread_id":"t"}}'
        echo '{{"type":"turn.completed","usage":{{"input_tokens":1}}}}'
        exit 0;;
  esac
fi
exit 0
"""
    codex.write_text(script)
    codex.chmod(codex.stat().st_mode | stat.S_IEXEC | stat.S_IRWXU)
    return codex


def _run(tmp_path, *, mode="ok", authed=True, family="codex", install_codex=True, timeout="5"):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    codex_bin = _write_stub_codex(bindir, mode=mode, authed=authed) if install_codex else (bindir / "codex")
    packet = tmp_path / "packet.txt"
    packet.write_text("QUESTION: x\nOPTIONS: A/B\nRESEARCH: none\n")
    out = tmp_path / "result.json"
    env = dict(os.environ)
    env["CODEX_BIN"] = str(codex_bin)  # adapter honors this override for tests
    cp = subprocess.run(
        ["bash", str(SCRIPT), "--family", family, "--packet", str(packet),
         "--out", str(out), "--timeout", timeout],
        capture_output=True, text=True, env=env,
    )
    result = json.loads(out.read_text()) if out.exists() else None
    return cp, result


def test_success_returns_parsed_pick(tmp_path):
    cp, r = _run(tmp_path, mode="ok")
    assert cp.returncode == 0, cp.stderr
    assert r["engine"] == "foreign:codex"
    assert r["status"] == "succeeded"
    assert r["fallback_reason"] in (None, "")
    assert r["pick"]["independent_pick"] == "B. the pick"


def test_not_installed_falls_back(tmp_path):
    cp, r = _run(tmp_path, install_codex=False)
    assert cp.returncode == 0
    assert r["status"] == "fallback"
    assert r["fallback_reason"] == "not-installed"
    assert r["pick"] is None


def test_not_authed_falls_back(tmp_path):
    cp, r = _run(tmp_path, authed=False)
    assert cp.returncode == 0
    assert r["status"] == "fallback"
    assert r["fallback_reason"] == "not-authed"


def test_spawn_failure_falls_back(tmp_path):
    cp, r = _run(tmp_path, mode="spawnfail")
    assert cp.returncode == 0
    assert r["status"] == "fallback"
    assert r["fallback_reason"] == "spawn-failed"


def test_unparseable_output_falls_back(tmp_path):
    cp, r = _run(tmp_path, mode="unparseable")
    assert cp.returncode == 0
    assert r["status"] == "fallback"
    assert r["fallback_reason"] == "unparseable"


def test_timeout_falls_back(tmp_path):
    cp, r = _run(tmp_path, mode="hang", timeout="1")
    assert cp.returncode == 0
    assert r["status"] == "fallback"
    assert r["fallback_reason"] == "timed-out"


def test_unsupported_family_falls_back(tmp_path):
    cp, r = _run(tmp_path, family="gemini")
    assert cp.returncode == 0
    assert r["status"] == "fallback"
    assert r["fallback_reason"] == "unsupported-family"
