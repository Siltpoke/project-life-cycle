"""Tests for scripts/cross-family-review.sh — the cross-family blind-2nd-agent adapter.

The stub `codex` is FAITHFUL to the real CLI's observed shape (from a real probe run):
`codex login status` prints a
"Logged in ..." line; `codex exec ... -o <file>` writes a clean structured JSON
payload to that file and prints JSONL events to stdout. Building the stub on the
REAL shape is the point: a stub built on a guessed shape lets a probe that can never pass ship green.

The adapter emits a KEY-DISJOINT envelope to --out — the success arm carries no
`fallback_reason` key, the fallback arm carries no `pick` key — and its exit status says
which happened: 0 an answer came back, 3 none did, 2 the call itself was wrong, 1 the
answer could not be written. It does NOT always exit 0; that older contract is what let
a chained caller run its next step whether or not a review existed.
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


def _write_stub_codex(bindir: Path, *, mode="ok", authed=True, payload=None):
    """Write a fake `codex` honoring `login status` + `exec ... -o <file>`.

    mode: ok | unparseable | spawnfail | hang

    `payload` replaces REAL_PICK in the `ok` branch, so a caller can hand this stub
    ANY payload shape. The code-review stub has this too; without it this side would be
    SILENTLY weaker — Gate 4's predicate is shared by both callers,
    so without it every measurement of the predicate is taken on one caller and
    published as a property of the gate. The one line that exists only on this side
    (`--require independent_pick`, which may legitimately be a non-empty OBJECT) is
    exactly the line that measurement would miss.
    """
    codex = bindir / "codex"
    auth_line = "Logged in using ChatGPT" if authed else "Not logged in"
    body = json.dumps(payload if payload is not None else REAL_PICK)
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
{body}
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


def _run(tmp_path, *, mode="ok", authed=True, family="codex", install_codex=True, timeout="5",
         payload=None, require=None):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    codex_bin = (_write_stub_codex(bindir, mode=mode, authed=authed, payload=payload)
                 if install_codex else (bindir / "codex"))
    packet = tmp_path / "packet.txt"
    packet.write_text("QUESTION: x\nOPTIONS: A/B\nRESEARCH: none\n")
    out = tmp_path / "result.json"
    env = dict(os.environ)
    env["CODEX_BIN"] = str(codex_bin)  # adapter honors this override for tests
    argv = ["bash", str(SCRIPT), "--family", family, "--packet", str(packet),
            "--out", str(out), "--timeout", timeout]
    if require is not None:
        argv += ["--require", require]
    cp = subprocess.run(argv, capture_output=True, text=True, env=env)
    result = json.loads(out.read_text()) if out.exists() else None
    return cp, result


def test_success_returns_parsed_pick(tmp_path):
    """PINNED AT 0, and it is one of only two assertions that are.

    This is the entire mechanism for the second half of "exit 3 when no answer came back, 0 only when it did".
    Flipping every returncode assertion to the new contract, and nothing more, would have
    left nothing asserting that a successful run exits 0."""
    cp, r = _run(tmp_path, mode="ok")
    assert cp.returncode == 0, cp.stderr
    assert r["engine"] == "foreign:codex"
    assert r["status"] == "succeeded"
    assert "fallback_reason" not in r, "the success arm must not carry the fallback key"
    assert r["pick"]["independent_pick"] == "B. the pick"


def test_not_installed_falls_back(tmp_path):
    cp, r = _run(tmp_path, install_codex=False)
    assert cp.returncode == 3
    assert r["status"] == "fallback"
    assert r["fallback_reason"] == "not-installed"
    assert "pick" not in r, "the fallback arm must not carry the payload key"


def test_not_authed_falls_back(tmp_path):
    cp, r = _run(tmp_path, authed=False)
    assert cp.returncode == 3
    assert r["status"] == "fallback"
    assert r["fallback_reason"] == "not-authed"


def test_spawn_failure_falls_back(tmp_path):
    cp, r = _run(tmp_path, mode="spawnfail")
    assert cp.returncode == 3
    assert r["status"] == "fallback"
    assert r["fallback_reason"] == "spawn-failed"


def test_unparseable_output_falls_back(tmp_path):
    cp, r = _run(tmp_path, mode="unparseable")
    assert cp.returncode == 3
    assert r["status"] == "fallback"
    assert r["fallback_reason"] == "unparseable"


def test_timeout_falls_back(tmp_path):
    cp, r = _run(tmp_path, mode="hang", timeout="1")
    assert cp.returncode == 3
    assert r["status"] == "fallback"
    assert r["fallback_reason"] == "timed-out"


def test_unsupported_family_exits_two_not_three(tmp_path):
    """The one fallback that is NOT a 3.

    2 means "the invocation itself was wrong". `--family cluade` is a configuration
    typo, and an `&&` chain SHOULD break on it; reporting it as "the foreign reviewer
    had no answer" points the diagnostic at the wrong actor. The envelope still reads
    status:"fallback", so every caller that reads the envelope is unaffected."""
    cp, r = _run(tmp_path, family="gemini")
    assert cp.returncode == 2
    assert r["status"] == "fallback"
    assert r["fallback_reason"] == "unsupported-family"


def test_an_unreadable_schema_is_also_a_two(tmp_path):
    """Exit 2's other occupant, pinned so the two are not silently merged."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    _write_stub_codex(bindir)
    packet = tmp_path / "packet.txt"
    packet.write_text("QUESTION: x\n")
    cp = subprocess.run(
        ["bash", str(SCRIPT), "--family", "codex", "--packet", str(packet),
         "--out", str(tmp_path / "o.json"), "--schema", str(tmp_path / "nope.json")],
        capture_output=True, text=True,
    )
    assert cp.returncode == 2
    assert "missing or unreadable" in cp.stderr


def test_an_unwritable_out_exits_one_not_zero(tmp_path):
    """The envelope's write half. An answer DID come back; it could not be stored.

    3 would be wrong here — it would tell the caller "no answer" and invite a retry of
    a foreign reviewer that already answered. 0 would be a claim wider than its mechanism: a
    successful-looking exit with no trustworthy envelope on disk."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    codex_bin = _write_stub_codex(bindir)
    packet = tmp_path / "packet.txt"
    packet.write_text("QUESTION: x\n")
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o555)
    env = dict(os.environ)
    env["CODEX_BIN"] = str(codex_bin)
    try:
        cp = subprocess.run(
            ["bash", str(SCRIPT), "--family", "codex", "--packet", str(packet),
             "--out", str(locked / "result.json"), "--timeout", "5"],
            capture_output=True, text=True, env=env,
        )
        assert cp.returncode == 1, cp.stdout + cp.stderr
    finally:
        locked.chmod(0o755)


def test_the_stub_can_be_handed_an_arbitrary_payload(tmp_path):
    """The harness assertion for `payload=`, not a test of the runner.

    Without it, a `payload=` that is silently ignored looks exactly like a payload
    that was honoured and happened to pass: the stub would keep writing REAL_PICK,
    every shape row below would read `independent_pick == "B. the pick"`, and the
    whole eleven-shape table would agree with itself while measuring one payload.
    A harness that cannot be shown to vary is not a harness.
    """
    cp, r = _run(tmp_path, payload={"independent_pick": "A_DISTINCTIVE_PICK_NOT_IN_REAL_PICK"})
    assert r["status"] == "succeeded", r
    assert r["pick"]["independent_pick"] == "A_DISTINCTIVE_PICK_NOT_IN_REAL_PICK"
    assert r["pick"] != REAL_PICK
