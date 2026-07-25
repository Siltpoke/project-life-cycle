"""Unit tests for the two out-of-envelope AC3 producers:
  - scripts/diff-guards.sh   → diff-guards.json   (R5, guard routing)
  - scripts/potency-runner.sh → potency-result.json (R4, potency proof)

python here is TEST tooling (subprocess-drives the bash producers against fixture git repos),
NOT part of any gate envelope. The producers are themselves out-of-envelope (bash + jq + git +
the fixture's own toolchain); only verify-gate.sh must stay jq-only.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
DIFF_GUARDS = SCRIPTS / "diff-guards.sh"
POTENCY = SCRIPTS / "potency-runner.sh"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _init(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")


def _write(repo: Path, rel: str, body: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def _commit(repo: Path, msg: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", msg)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo,
                          check=True, capture_output=True, text=True).stdout.strip()


def _run(script: Path, *args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(script), *args], cwd=cwd,
                          capture_output=True, text=True,
                          env={**os.environ})


# ---------------------------------------------------------------- diff-guards.sh ----

def _diff_file(repo: Path, base: str, head: str) -> Path:
    d = repo / "pr.diff"
    out = subprocess.run(["git", "diff", "--unified=0", base, head], cwd=repo,
                         check=True, capture_output=True, text=True).stdout
    d.write_text(out, encoding="utf-8")
    return d


def test_diff_guards_routes_real_guard_only(tmp_path: Path) -> None:
    """AC3.2/AC3.3: a real added `throw` routes; a `throw` in a comment and one in a .md
    file do NOT route."""
    repo = tmp_path / "r"
    _init(repo)
    _write(repo, "src/a.js", "function f(){ return 1 }\n")
    base = _commit(repo, "base")
    _write(repo, "src/a.js",
           "function f(){\n"
           "  if (x) throw new Error('boom')   // real guard\n"
           "  // throw new Error('commented')  -- must NOT route\n"
           "  const s = 'throw new Error(quoted)'  // string literal, must NOT route\n"
           "  return 1\n"
           "}\n")
    _write(repo, "docs/note.md", "throw new Error in prose must not route\n")
    head = _commit(repo, "add guard + noise")
    diff = _diff_file(repo, base, head)
    out = repo / "diff-guards.json"
    r = _run(DIFF_GUARDS, "--base", base, "--head", head, "--diff", str(diff),
             "--out", str(out), cwd=repo)
    assert r.returncode == 0, r.stdout + r.stderr
    data = json.loads(out.read_text())
    guards = data["guards"]
    kinds = [g["kind"] for g in guards]
    files = {g["file"] for g in guards}
    assert kinds.count("throw") == 1, f"expected exactly one routed throw, got {guards}"
    assert files == {"src/a.js"}, f"only src/a.js should route, got {files}"


def test_diff_guards_empty_when_no_guards(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    _init(repo)
    _write(repo, "src/a.js", "const x = 1\n")
    base = _commit(repo, "base")
    _write(repo, "src/a.js", "const x = 2\n")
    head = _commit(repo, "no guards")
    diff = _diff_file(repo, base, head)
    out = repo / "diff-guards.json"
    r = _run(DIFF_GUARDS, "--base", base, "--head", head, "--diff", str(diff),
             "--out", str(out), cwd=repo)
    assert r.returncode == 0, r.stdout + r.stderr
    assert json.loads(out.read_text())["guards"] == []


def test_diff_guards_kinds(tmp_path: Path) -> None:
    """assert / return false / process.exit / CI exit 1 each classify."""
    repo = tmp_path / "r"
    _init(repo)
    _write(repo, "src/a.py", "x = 1\n")
    base = _commit(repo, "base")
    _write(repo, "src/a.py",
           "assert x == 1\n"
           "def g():\n"
           "    return False\n")
    _write(repo, "ci/run.sh", "#!/bin/sh\nexit 1\n")
    _write(repo, "src/b.js", "process.exit(1)\n")
    head = _commit(repo, "kinds")
    diff = _diff_file(repo, base, head)
    out = repo / "diff-guards.json"
    r = _run(DIFF_GUARDS, "--base", base, "--head", head, "--diff", str(diff),
             "--out", str(out), cwd=repo)
    assert r.returncode == 0, r.stdout + r.stderr
    kinds = {g["kind"] for g in json.loads(out.read_text())["guards"]}
    assert {"assert", "return-false", "exit", "ci-exit"} <= kinds, kinds


# ---------------------------------------------------------------- potency-runner.sh ----

def _manifest_repo(tmp_path: Path, guard_line: str) -> tuple[Path, str]:
    """A repo with a guard in src/guard.sh, a firing fixture that FAILS iff the guard line
    is present (so neuter → fixture passes → impotent), and a manifest binding them."""
    repo = tmp_path / "r"
    _init(repo)
    # guard.sh exits 1 (the guard) when called with 'bad'
    _write(repo, "src/guard.sh",
           "#!/bin/sh\n"
           "if [ \"$1\" = bad ]; then\n"
           f"  {guard_line}\n"
           "fi\n"
           "echo ok\n")
    # fixture: the guard MUST fire (exit non-zero) on bad input. Fixture PASSES when guard bites.
    _write(repo, "fixtures/guard_fires.sh",
           "#!/bin/sh\n"
           "if bash src/guard.sh bad >/dev/null 2>&1; then\n"
           "  echo 'guard did NOT fire' >&2; exit 1\n"  # fixture fails → guard impotent
           "fi\n"
           "echo 'guard fired'; exit 0\n")
    manifest = [{
        "guardId": "src/guard.sh:3",
        "file": "src/guard.sh", "line": 3,
        "firingFixture": "sh fixtures/guard_fires.sh",
        "neuterCmd": "sed -i.bak '3s/.*/  :/' src/guard.sh",
    }]
    _write(repo, ".plc/guard-manifest.json", json.dumps(manifest))
    head = _commit(repo, "guard + fixture + manifest")
    return repo, head


def test_potency_intact_guard_is_potent(tmp_path: Path) -> None:
    """AC3.5: intact guard → fixtureResult passed, neuterResult failed (potent)."""
    repo, head = _manifest_repo(tmp_path, "exit 1")
    out = repo / "potency-result.json"
    r = _run(POTENCY, "--head", head, "--manifest", ".plc/guard-manifest.json",
             "--diff-guards", "-", "--out", str(out), cwd=repo)
    assert r.returncode == 0, r.stdout + r.stderr
    data = json.loads(out.read_text())
    assert data["prHeadSha"] == head
    assert "manifestHash" in data and "runId" in data
    pg = {g["guardId"]: g for g in data["perGuard"]}
    g = pg["src/guard.sh:3"]
    assert g["fixtureResult"] == "passed", data
    assert g["neuterResult"] == "failed", data


def test_potency_preneutered_guard_is_impotent(tmp_path: Path) -> None:
    """A guard that never fires (`:` no-op) → fixture already fails → fixtureResult failed."""
    repo, head = _manifest_repo(tmp_path, ":")   # guard line is a no-op: never exits 1
    out = repo / "potency-result.json"
    r = _run(POTENCY, "--head", head, "--manifest", ".plc/guard-manifest.json",
             "--diff-guards", "-", "--out", str(out), cwd=repo)
    assert r.returncode == 0, r.stdout + r.stderr
    pg = {g["guardId"]: g for g in json.loads(out.read_text())["perGuard"]}
    assert pg["src/guard.sh:3"]["fixtureResult"] == "failed"


def test_diff_guards_multiline_constructs_not_routed(tmp_path: Path) -> None:
    """AC3.2 multi-line: guard tokens inside a multi-line /* */ block, a JS template literal,
    and a Python triple-quoted docstring must NOT route (cross-line state, R5 no over-route)."""
    repo = tmp_path / "r"
    _init(repo)
    _write(repo, "src/a.js", "const x = 1\n")
    _write(repo, "m.py", "y = 1\n")
    base = _commit(repo, "base")
    _write(repo, "src/a.js",
           "/*\n"
           " * JSDoc: throw new Error('example in block comment')\n"
           " */\n"
           "const t = `line1\n"
           "throw new Error('inside template literal')\n"
           "line3`\n"
           "const ok = 2\n")
    _write(repo, "m.py",
           'def f():\n'
           '    """\n'
           '    assert False  # example inside docstring\n'
           '    """\n'
           '    return 1\n')
    head = _commit(repo, "multi-line noise")
    diff = _diff_file(repo, base, head)
    out = repo / "diff-guards.json"
    r = _run(DIFF_GUARDS, "--base", base, "--head", head, "--diff", str(diff),
             "--out", str(out), cwd=repo)
    assert r.returncode == 0, r.stdout + r.stderr
    guards = json.loads(out.read_text())["guards"]
    assert guards == [], f"multi-line constructs must not route, got {guards}"


def test_diff_guards_two_block_comments_no_fail_open(tmp_path: Path) -> None:
    """HIGH-1 regression: a greedy /* */ strip would swallow a live guard sitting BETWEEN two
    single-line block comments on one added line = fail-OPEN (real guard escapes). The
    non-greedy strip must still route the throw."""
    repo = tmp_path / "r"
    _init(repo)
    _write(repo, "src/a.js", "const x = 1\n")
    base = _commit(repo, "base")
    _write(repo, "src/a.js",
           "if (bad) /* legacy */ throw new Error('bad') /* TODO cleanup */\n")
    head = _commit(repo, "guard between two block comments")
    diff = _diff_file(repo, base, head)
    out = repo / "diff-guards.json"
    r = _run(DIFF_GUARDS, "--base", base, "--head", head, "--diff", str(diff),
             "--out", str(out), cwd=repo)
    assert r.returncode == 0, r.stdout + r.stderr
    kinds = [g["kind"] for g in json.loads(out.read_text())["guards"]]
    assert kinds == ["throw"], f"live guard between block comments must route, got {kinds}"


def test_potency_no_residual_bak(tmp_path: Path) -> None:
    """MED-3: a neuterCmd using `sed -i.bak` must leave NO .bak in the tree after the run, and the
    guarded file is restored byte-identical."""
    repo, head = _manifest_repo(tmp_path, "exit 1")   # manifest neuterCmd uses sed -i.bak
    before = (repo / "src/guard.sh").read_bytes()
    out = repo / "potency-result.json"
    r = _run(POTENCY, "--head", head, "--manifest", ".plc/guard-manifest.json",
             "--diff-guards", "-", "--out", str(out), cwd=repo)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (repo / "src/guard.sh").read_bytes() == before, "guard file not restored byte-identical"
    assert not (repo / "src/guard.sh.bak").exists(), "residual .bak left in the working tree"
