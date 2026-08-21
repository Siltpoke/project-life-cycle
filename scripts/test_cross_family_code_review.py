"""Tests for scripts/cross-family-code-review.sh — the cross-family CODE review runner.

The stub `codex` is FAITHFUL to the real CLI's observed shape, copied from
test_cross_family_review.py rather than invented: `codex login status` writes to
STDERR in both the authed and unauthed cases, and `codex exec ... -o <file>`
writes the structured payload to that file while printing JSONL events to stdout.
An unfaithful stub once let a probe that could never pass ship green.

The distinction this file exists to hold: `status:fallback` means NO REVIEW HAPPENED
and `findings: []` means a review happened and found nothing. Reading the first as the
second is the failure this file guards against.
"""
import json
import os
import stat
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "cross-family-code-review.sh"

# A review that FOUND something — the positive control. A runner that cannot surface
# this is indistinguishable from one that silently returns nothing.
REAL_REVIEW = {
    "checks_performed": [
        {"check": "grep for the removed guard", "known_good_input": "ran it against the pre-image, which matched", "confirmed_working": True}
    ],
    "findings": [
        {
            "severity": "Important",
            "file": "hooks/example.sh",
            "line": 42,
            "claim": "the guard is skipped when the path is relative",
            "failure_scenario": "event without cwd -> ART resolves relative -> stats a different file",
            "refutation_attempted": "tried to construct an absolute-path case that also fails; could not",
        }
    ],
    "defect_class_both_oracles_would_miss": "a state file written to the right name with wrong contents",
    "verdict": "1 Important, 0 Critical",
}

# A review that ran and found nothing. Structurally VALID — this must not be confused
# with a fallback.
CLEAN_REVIEW = {
    "checks_performed": [
        {"check": "reverted the new predicate", "known_good_input": "it reddened the row it names", "confirmed_working": True}
    ],
    "findings": [],
    "defect_class_both_oracles_would_miss": "none identified",
    "verdict": "clean",
}


def _write_stub_codex(bindir: Path, *, mode="ok", authed=True, payload=None):
    codex = bindir / "codex"
    auth_line = "Logged in using ChatGPT" if authed else "Not logged in"
    body = json.dumps(payload if payload is not None else REAL_REVIEW)
    script = f"""#!/usr/bin/env bash
sub="$1"; shift || true
if [ "$sub" = "login" ]; then
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
  # Record what actually arrived on stdin, so a test can assert the diff was handed
  # over rather than left for the reviewer to go and find.
  [ -n "${{STUB_PACKET_COPY:-}}" ] && cat > "$STUB_PACKET_COPY" || cat >/dev/null
  case "{mode}" in
    hang) sleep 30;;
    spawnfail) echo '{{"type":"turn.failed"}}'; exit 1;;
    noverdict) [ -n "$out" ] && printf '{{"findings":[]}}' > "$out"; exit 0;;
    ok) [ -n "$out" ] && cat > "$out" <<'JSON'
{body}
JSON
        echo '{{"type":"turn.completed"}}'
        exit 0;;
  esac
fi
exit 0
"""
    codex.write_text(script)
    codex.chmod(codex.stat().st_mode | stat.S_IEXEC | stat.S_IRWXU)
    return codex


def _run(tmp_path, *, mode="ok", authed=True, payload=None, diff_text="--- a\n+++ b\n+broken line\n",
         brief_text="LENS: attack the new predicate.\n", timeout="5", capture_packet=False):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    codex_bin = _write_stub_codex(bindir, mode=mode, authed=authed, payload=payload)
    diff = tmp_path / "d.patch"; diff.write_text(diff_text)
    brief = tmp_path / "brief.md"; brief.write_text(brief_text)
    out = tmp_path / "result.json"
    env = dict(os.environ)
    env["CODEX_BIN"] = str(codex_bin)
    if capture_packet:
        env["STUB_PACKET_COPY"] = str(tmp_path / "packet.seen")
    cp = subprocess.run(
        ["bash", str(SCRIPT), "--diff", str(diff), "--brief", str(brief),
         "--out", str(out), "--timeout", timeout],
        capture_output=True, text=True, env=env,
    )
    result = json.loads(out.read_text()) if out.exists() else None
    return cp, result, tmp_path


def test_a_review_that_found_a_defect_is_surfaced(tmp_path):
    """POSITIVE CONTROL. A runner that cannot carry a real finding through is
    indistinguishable from one that silently returns nothing."""
    cp, r, _ = _run(tmp_path, mode="ok")
    # PINNED AT 0 — the second of the two success-arm pins.
    assert cp.returncode == 0, cp.stderr
    assert r["status"] == "succeeded"
    assert r["engine"] == "foreign:codex"
    assert len(r["review"]["findings"]) == 1
    assert r["review"]["findings"][0]["severity"] == "Important"
    assert r["review"]["findings"][0]["line"] == 42
    assert r["review"]["verdict"] == "1 Important, 0 Critical"


def test_a_clean_review_is_not_a_fallback(tmp_path):
    """The distinction the whole runner exists for: `findings: []` from a review that
    ran is a RESULT; `status:fallback` means no review happened at all."""
    cp, r, _ = _run(tmp_path, mode="ok", payload=CLEAN_REVIEW)
    # The success arm that must be most carefully protected; without this line it has no
    # returncode assertion at all.
    assert cp.returncode == 0, cp.stderr
    assert r["status"] == "succeeded"
    assert r["review"]["findings"] == []
    assert r["review"]["verdict"] == "clean"
    assert "fallback_reason" not in r, "the success arm must not carry the fallback key"


def test_the_diff_is_handed_over_not_left_to_be_found(tmp_path):
    """A reviewer handed no diff can spend its whole budget discovering the repo.
    The packet must contain the change itself."""
    cp, r, tp = _run(tmp_path, mode="ok", capture_packet=True,
                     diff_text="--- a\n+++ b\n+A_VERY_DISTINCTIVE_TOKEN\n")
    seen = (tp / "packet.seen").read_text()
    assert "A_VERY_DISTINCTIVE_TOKEN" in seen
    assert "LENS: attack the new predicate." in seen
    assert "refutation_attempted" in seen  # the refute-first instruction rides along


def test_an_empty_diff_is_fatal_not_a_clean_review(tmp_path):
    cp, r, _ = _run(tmp_path, diff_text="")
    assert cp.returncode == 2
    assert "not a clean review" in cp.stderr
    assert r is None


def test_a_response_without_a_verdict_falls_back(tmp_path):
    """Gate 4 insists on the field that proves a real answer came back."""
    cp, r, _ = _run(tmp_path, mode="noverdict")
    assert cp.returncode == 3
    assert r["status"] == "fallback"
    # This does NOT become `empty-answer`. The payload parsed and the required field
    # is ABSENT, not present-and-contentless. `unparseable` is the wrong word for it and
    # it is knowingly left as is rather than widened here.
    assert r["fallback_reason"] == "unparseable"
    assert "review" not in r, "the fallback arm must not carry the payload key"


def test_timeout_is_a_fallback_not_a_hang(tmp_path):
    """A hung reviewer must not wait for the caller's tool timeout to kill it. The runner owns the cap."""
    cp, r, _ = _run(tmp_path, mode="hang", timeout="1")
    assert cp.returncode == 3
    assert r["status"] == "fallback"
    assert r["fallback_reason"] == "timed-out"


def test_unauthed_falls_back_without_running(tmp_path):
    cp, r, _ = _run(tmp_path, authed=False)
    assert cp.returncode == 3
    assert r["status"] == "fallback"
    assert r["fallback_reason"] == "not-authed"


def test_the_wrappers_exit_status_is_the_runners(tmp_path):
    """The consumer oracle, stated over a consumer that exists.

    An earlier draft asserted that "the two committed callers branch on status or on a
    non-zero exit". Measured: there is exactly ONE programmatic caller, and it is
    `exec /bin/bash "$RUNNER" …` — after `exec` there is no "after", so it reads neither
    the envelope nor `$?`. The runner's exit status simply BECOMES the wrapper's. That
    composite surface is the only place a consumer can be observed at all, so it is what
    gets asserted."""
    cp, r, _ = _run(tmp_path, mode="hang", timeout="1")
    assert r["status"] == "fallback"
    assert cp.returncode == 3, "the wrapper swallowed the runner's exit status"


def test_missing_brief_is_fatal(tmp_path):
    bindir = tmp_path / "bin"; bindir.mkdir()
    _write_stub_codex(bindir)
    diff = tmp_path / "d.patch"; diff.write_text("x\n")
    cp = subprocess.run(
        ["bash", str(SCRIPT), "--diff", str(diff), "--brief", str(tmp_path / "nope.md"),
         "--out", str(tmp_path / "o.json")],
        capture_output=True, text=True,
    )
    assert cp.returncode == 2
    assert "missing or unreadable" in cp.stderr
