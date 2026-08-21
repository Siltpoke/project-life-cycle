"""Tests for scripts/install-close-gate-hook.sh.

THE ONE THING THIS FILE MUST NOT DO is assert on what the installer PRINTS, or on
whether the MARK string ended up somewhere in the file. The pre-fix defect is a
SILENT SUCCESS: the installer appends its chain after an `exec` line, prints
`✓ chained close-gate into existing …`, and exits 0. A fixture asserting the output
or the presence of the mark is GREEN BOTH BEFORE AND AFTER the fix — which would let
the requirement "the same fixture is proven FAIL against the pre-fix installer" be satisfied by
something that never tested anything.

So every fixture here RUNS THE HOOK and observes whether the chain actually executed.

The observation mechanism: the installer owns every byte it injects, so a fixture
cannot plant a marker at "the chain position". Instead each fixture repo gets a real
executable `scripts/close-gate-prepush.sh` stub that touches a marker file — which
turns the injected `[ -x scripts/close-gate-prepush.sh ]` test into the switch. All six
fixtures need the stub, including the synthesized-hook one (without it the generated
chain is a silent no-op and the fixture proves nothing).
"""
import os
import subprocess
import stat
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
INSTALLER = HERE / "install-close-gate-hook.sh"

RAN = "gate-ran.marker"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _repo(tmp_path: Path, *, hook_body: str | None, gate_exit: int = 0) -> Path:
    """A git repo with the prepush stub in place and, optionally, a pre-existing hook."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@t.t")
    _git(repo, "config", "user.name", "t")

    scripts = repo / "scripts"
    scripts.mkdir()
    stub = scripts / "close-gate-prepush.sh"
    # The observable. `exit {gate_exit}` is how fixture 6 makes the chain FAIL.
    stub.write_text(f"#!/bin/bash\ntouch '{RAN}'\nexit {gate_exit}\n", encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IRWXU)

    (repo / "README.md").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")

    if hook_body is not None:
        hook = repo / ".git/hooks/pre-push"
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text(hook_body, encoding="utf-8")
        hook.chmod(hook.stat().st_mode | stat.S_IEXEC | stat.S_IRWXU)
    return repo


def _install(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(INSTALLER)], cwd=repo,
                          capture_output=True, text=True, check=False)


def _run_hook(repo: Path, *, refline: str = "refs/heads/m sha1 refs/heads/m sha2\n"):
    """Execute the hook the way git does: as a PROGRAM, with ref lines on stdin.

    Not `bash <path>`. That form was here first and it made the whole bench blind to the
    shebang: git runs the hook file directly, so a hook that lost its `#!` line does not
    run at all — but under `bash <path>` it runs fine. A mutant that replaces
    the installer's `sed -n '1p'` (the line that carries the shebang
    through) with `true` leaves every such fixture green. The interpreter has
    to come from the file, or the fixtures are not testing the file git will execute.
    """
    hook = repo / ".git/hooks/pre-push"
    return subprocess.run([str(hook)], cwd=repo, input=refline,
                          capture_output=True, text=True, check=False)


def _chain_ran(repo: Path) -> bool:
    return (repo / RAN).exists()


# --- fixture 1: the exec shim — MUST BE RED PRE-FIX ------------------------------
EXEC_SHIM = """#!/bin/bash
exec /usr/bin/true "$@"
echo "never reached"
exit 0
"""


def test_exec_shim_hook_still_runs_the_chain(tmp_path):
    """THE reverse fixture. Pre-fix the installer appends below the `exec`, so the chain
    is dead code — while the installer prints success and exits 0."""
    repo = _repo(tmp_path, hook_body=EXEC_SHIM)
    cp = _install(repo)
    # These two lines are the receipt, not the oracle: they are green BEFORE and AFTER
    # the fix. An "assert the installer reported success" fixture would therefore prove
    # nothing here, which is exactly why the assertion below runs the hook instead.
    assert cp.returncode == 0, cp.stderr
    assert "✓" in cp.stdout, cp.stdout + cp.stderr
    _run_hook(repo)
    assert _chain_ran(repo), "the chain was installed where the hook never reaches it"


# --- fixture 2: trailing `exit 0` — the normal path stays working ----------------
TRAILING_EXIT = """#!/bin/bash
echo "existing hook ran"
exit 0
"""


def test_trailing_exit_zero_hook_runs_the_chain(tmp_path):
    repo = _repo(tmp_path, hook_body=TRAILING_EXIT)
    cp = _install(repo)
    assert cp.returncode == 0, cp.stderr
    r = _run_hook(repo)
    assert _chain_ran(repo), r.stdout + r.stderr
    assert r.returncode == 0


# --- fixture 3: no hook at all — the synthesized branch ---------------------------
def test_synthesized_hook_runs_the_chain(tmp_path):
    """Neither refusal may reject here: a fresh clone has no hook, and this is the very
    path close-gate-wiring.sh clause 4 tells the user to take."""
    repo = _repo(tmp_path, hook_body=None)
    cp = _install(repo)
    assert cp.returncode == 0, cp.stderr
    r = _run_hook(repo)
    assert _chain_ran(repo), r.stdout + r.stderr
    assert r.returncode == 0


def test_the_synthesized_hook_omits_a_notice_that_would_be_false_there(tmp_path):
    """A fresh clone has no "rest of the hook", so the failure notice would be false BY
    CONSTRUCTION — which is the exact thing the notice exists to avoid. Two assertions,
    because the fresh line differs from the normal one in one way and must NOT differ in
    the other: no notice, but the stdin redirect stays."""
    repo = _repo(tmp_path, hook_body=None)
    assert _install(repo).returncode == 0
    body = (repo / ".git/hooks/pre-push").read_text()
    assert "the rest of this pre-push hook did not run" not in body
    assert "</dev/null" in body, "the fresh branch dropped the stdin redirect"


# --- fixture 4: adopter's `set -euo pipefail` on line 2 --------------------------
STRICT_MODE = """#!/bin/bash
set -euo pipefail
echo "existing hook ran"
exit 0
"""


def test_strict_mode_hook_runs_the_chain(tmp_path):
    """The chain lands ABOVE the adopter's `set -euo pipefail`. Bounded (the chain is a
    subprocess), but bounded is not the same as looked at."""
    repo = _repo(tmp_path, hook_body=STRICT_MODE)
    cp = _install(repo)
    assert cp.returncode == 0, cp.stderr
    r = _run_hook(repo)
    assert _chain_ran(repo), r.stdout + r.stderr
    assert r.returncode == 0


# --- fixture 5: non-shell shebang — named refusal --------------------------------
PYTHON_HOOK = """#!/usr/bin/env python3
import sys
sys.exit(0)
"""


def test_non_shell_shebang_is_refused_by_name(tmp_path):
    repo = _repo(tmp_path, hook_body=PYTHON_HOOK)
    cp = _install(repo)
    assert cp.returncode != 0, "a hook it cannot safely insert into was accepted"
    assert "python3" in (cp.stdout + cp.stderr), "the refusal does not name what it refused"


# --- core.hooksPath points somewhere git will not read our hook -------------
def test_a_redirected_hooks_path_is_refused(tmp_path):
    """The installer's own thesis, applied to itself. Before this, an adopter using husky
    or lefthook — or this skill's own `/init-harness` — got a written file, a printed
    check-mark, exit 0, and a hook git never runs."""
    repo = _repo(tmp_path, hook_body=None)
    (repo / ".githooks").mkdir()
    _git(repo, "config", "core.hooksPath", ".githooks")
    cp = _install(repo)
    assert cp.returncode != 0, "wrote a hook into a directory git does not consult"
    assert ".githooks" in (cp.stdout + cp.stderr), "the refusal does not name where it points"
    assert not (repo / ".git/hooks/pre-push").exists(), "it wrote the file anyway"


def test_hooks_path_aliasing_the_default_dir_is_not_a_refusal(tmp_path):
    """The other direction, and the reason the check asks git for BOTH paths instead of
    testing whether the key is set. `core.hooksPath` pointing AT the default directory
    changes nothing about which file git runs, so refusing there would be a false
    positive — first found on the sibling predicate, close-gate-wiring.sh."""
    repo = _repo(tmp_path, hook_body=TRAILING_EXIT)
    _git(repo, "config", "core.hooksPath", str(repo / ".git/hooks"))
    cp = _install(repo)
    assert cp.returncode == 0, cp.stdout + cp.stderr
    r = _run_hook(repo)
    assert _chain_ran(repo), r.stdout + r.stderr


# --- an already-wired install is never re-judged ----------------------------------
def test_an_already_wired_hook_is_not_re_judged_by_the_shebang_refusal(tmp_path):
    """The idempotent early return sits ABOVE the shebang refusal on purpose.

    Put the refusal first and re-running this script on a clone wired before the refusal existed
    would flip from exit 0 to a non-zero refusal — an idempotence regression that "the
    normal path is unchanged" does not cover, because this is not the normal path."""
    repo = _repo(tmp_path, hook_body=TRAILING_EXIT)
    assert _install(repo).returncode == 0
    hook = repo / ".git/hooks/pre-push"
    body = hook.read_text().split("\n", 1)[1]
    hook.write_text("#!/usr/bin/env python3\n" + body)  # wired, but now unacceptable
    again = _install(repo)
    assert again.returncode == 0, again.stdout + again.stderr
    assert "already installed" in again.stdout


def test_a_redirected_hooks_path_reports_the_orphan_it_found(tmp_path):
    """The correction to this test's first version, which asserted exit 0 and was wrong.

    When `core.hooksPath` moves away AFTER a chain was installed, the early return cannot
    apply: `$HOOK` moved with it, so the wired file is not the file git will run — the
    install is ORPHANED. Exiting 0 there would be the very defect under test, a success signal
    with nothing behind it. It refuses, and the message names the orphan rather than
    repeating the generic hooksPath sentence, because that is the state close-gate-wiring.sh clause 1
    exists to detect and the more useful thing to be told."""
    repo = _repo(tmp_path, hook_body=TRAILING_EXIT)
    assert _install(repo).returncode == 0
    (repo / ".githooks").mkdir()
    _git(repo, "config", "core.hooksPath", ".githooks")
    again = _install(repo)
    assert again.returncode != 0
    assert "orphaned" in again.stderr, again.stdout + again.stderr


# --- fixture 6: the chain FAILS ------------------------------------------------
def test_failing_chain_makes_the_hook_exit_nonzero(tmp_path):
    """This half is GREEN pre-fix — `|| exit 1` already exists — and it is
    here so that a mutant which deletes it is caught. Do not read its green as evidence
    that the failure notice shipped."""
    repo = _repo(tmp_path, hook_body=TRAILING_EXIT, gate_exit=1)
    assert _install(repo).returncode == 0
    r = _run_hook(repo)
    assert _chain_ran(repo), r.stdout + r.stderr
    assert r.returncode != 0, "a failing gate did not block the push"


def test_failing_chain_says_so_itself(tmp_path):
    """The half that is RED pre-fix — the notice does not exist yet.

    Split from the exit-code half deliberately: the two have DIFFERENT pre-fix colours,
    and one id covering both would report a single colour for two facts.

    The asserted text says only what the installer can actually observe. It must NOT
    name what that hook is: the installer never reads the body it inserts above, so for an
    adopter whose pre-push is a linter that claim is simply false.
    """
    repo = _repo(tmp_path, hook_body=TRAILING_EXIT, gate_exit=1)
    assert _install(repo).returncode == 0
    r = _run_hook(repo)
    assert "the rest of this pre-push hook did not run" in r.stderr, r.stdout + r.stderr


# --- the chain must not eat the hook's stdin -------------------------------------
#
# git hands the pre-push hook a `<local ref> <local sha> <remote ref> <remote sha>` line
# per ref on fd 0. If the chain reads fd 0 without a redirect, everything BELOW it in the
# adopter's hook gets an empty stdin — silently.
#
# Why this needs a synthetic bench rather than the receipt already in this repo:
# `scripts/invariants/backlog-no-title-markers.sh` records an end-to-end measurement
# that *nothing in the chain down to close-gate.sh redirects fd 0*. That receipt describes
# the world the redirect exists to end. Reusing it as the oracle would be asserting the very fact
# the redirect makes false.
#
# The stand-in below is FIXED IN THE FIXTURE and never mutated — the mutation test removes
# the `</dev/null` redirect, one at a time, and nothing else.

REFLINES = "".join(f"refs/heads/b{i} sha{i} refs/heads/b{i} rsha{i}\n" for i in range(3))

# A hook whose body, AFTER the chain, counts the ref lines still readable on fd 0.
COUNTING_HOOK = """#!/bin/bash
n=0
while read -r _l; do n=$((n+1)); done
echo "REFS_SEEN=$n"
exit 0
"""


def _stdin_eating_standin(repo: Path) -> None:
    """Replace the gate stub with one that DRAINS fd 0, like a real gate that reads stdin.

    Without the redirect this is what steals the adopter's ref lines. With it, the drain
    happens on /dev/null and the hook body still sees all three.
    """
    stub = repo / "scripts/close-gate-prepush.sh"
    stub.write_text(f"#!/bin/bash\ntouch '{RAN}'\ncat >/dev/null\nexit 0\n", encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IRWXU)


def _refs_seen(out: str) -> int:
    for line in out.splitlines():
        if line.startswith("REFS_SEEN="):
            return int(line.split("=", 1)[1])
    raise AssertionError(f"the hook body never ran: {out!r}")


def test_the_bench_itself_can_see_stdin_being_eaten(tmp_path):
    """CONTROL for the bench, and it deliberately does NOT use the installer.

    Measured while building this bench: the pre-fix installer put the chain BELOW the
    hook body, so the chain cannot eat anything the body has not already read, and an
    installer-driven control comes back green while observing nothing. `strict=True`
    caught that as an unexpected pass — the honest statement is that **the stdin redirect is not
    observable until the chain sits above the body.**

    So this control hand-builds the chain-first LAYOUT (unredirected chain line first,
    reader second) and proves the bench can see a drain at all. It is installer-free on
    purpose: it must keep answering "can this bench observe?" even while the installer
    is mid-change.
    """
    repo = _repo(tmp_path, hook_body=COUNTING_HOOK)
    _stdin_eating_standin(repo)
    hook = repo / ".git/hooks/pre-push"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(
        "#!/bin/bash\n"
        "if [ -x scripts/close-gate-prepush.sh ]; then scripts/close-gate-prepush.sh; fi\n"
        + COUNTING_HOOK.split("\n", 1)[1],
        encoding="utf-8",
    )
    hook.chmod(hook.stat().st_mode | stat.S_IEXEC | stat.S_IRWXU)
    r = _run_hook(repo, refline=REFLINES)
    assert _chain_ran(repo), r.stdout + r.stderr
    assert _refs_seen(r.stdout) == 0, "the bench cannot observe a drained stdin"


def test_the_chain_does_not_consume_the_hooks_stdin(tmp_path):
    """The stdin redirect, through the REAL installer.

    NOT marked xfail. It is a real oracle only because the installer puts the chain at the
    top: with the chain below the reader there would be nothing for it to eat, and a green
    would be vacuous. With the chain first, its mutation (delete `</dev/null`, one at a time)
    reddens it, so this green is conditioned on chain-first insertion, not independent.
    """
    repo = _repo(tmp_path, hook_body=COUNTING_HOOK)
    assert _install(repo).returncode == 0
    _stdin_eating_standin(repo)
    r = _run_hook(repo, refline=REFLINES)
    assert _chain_ran(repo), r.stdout + r.stderr
    assert _refs_seen(r.stdout) == 3, "the chain ate the hook's ref lines"


def test_a_gate_that_does_not_read_stdin_leaves_the_refs_alone(tmp_path):
    """The other control: with no draining stand-in, the count is correct even today, so a
    green here is NOT evidence the redirect exists. It is here to keep the two variables
    apart — a single test would confound 'the gate drains' with 'the redirect is missing'.
    """
    repo = _repo(tmp_path, hook_body=COUNTING_HOOK)
    assert _install(repo).returncode == 0
    r = _run_hook(repo, refline=REFLINES)
    assert _refs_seen(r.stdout) == 3, r.stdout + r.stderr
