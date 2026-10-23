"""`scripts/plc-python.sh` resolves a WORKING interpreter, or says so.

WHY THIS FILE IS PYTHON AND NOT SHELL. CI runs `python -m pytest scripts/ -q`
(`.github/workflows/validate.yml:44`), so a pytest file here is actually executed. A new
`*.sh` would instead land in `scripts/invariants/named-interpreter.sh`'s corpus, which is
`git ls-files -- '*.sh'` (that script, :113) — a waiver-less corpus this file has no business
joining just to hold test fixtures.

THE ROWS LAUNCH THE RESOLVER AS `/bin/bash`, NEVER BARE `bash`. AC11 requires it. AC11's
stated REASON — "because the test files are tracked `*.sh`" — is measurably wrong: this file
is `.py` and the corpus above binds `*.sh` only, which is why the sibling
`scripts/test_mode_branch_protection.py` gets away with bare `bash` at its `run()` helper and
again in its module-level `subprocess.run`. The requirement is kept because it is strictly
stricter and costs nothing; only its rationale is corrected, here and in the journal, rather
than quietly followed or quietly dropped.

THE PATH FARM IS HERMETIC, EXCEPT FOR TWO ROWS THAT SAY SO. R0b and R7 deliberately use the
real environment, because their whole job is to involve a genuine interpreter. Every other
row runs with `PATH` set to the farm directory and NOTHING else — not `/usr/bin`, which on
a machine with a real `python3` would silently rescue a row meant to prove
rejection. (An earlier version of this paragraph said "every row but R7", which was one row
short.) Note the residual: the two non-hermetic rows do not neutralise `$PLC_PYTHON` or
`$PYTHON`, so a CI host that exports either would change what they measure. The resolver is
written against bash builtins only; a row that starts failing because the resolver reached
for `sed` is the farm doing its job, not the farm being wrong.

R0 RUNS FIRST AND VALIDATES EVERY FIXTURE SHAPE, not just one. If a double does not behave
the way the row names claim, then a "rejected" verdict below proves nothing — it could be the
double being broken rather than the resolver being right. The shape being copied lives in
`skills/project-lifecycle/hooks/test-hooks.sh` (its probe-validity block). Honest residual,
stated because the first version of this paragraph overstated it: pytest imposes no ordering,
so "R0 first" holds by file order and by nothing else. A `-k` or random-order run can execute
a dependent row without it. What R0 buys is that a broken fixture is *reported* as a broken
fixture somewhere in the run, not that it is reported first.
"""

import os
import pathlib
import shutil
import stat
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
RESOLVER = ROOT / "scripts/plc-python.sh"

# The probe string the resolver is specified to send. Rows that stub an
# interpreter recognise the probe by `version_info`, so a stub can answer the probe one way
# and the real call another — which is what makes "selected" observable.
PROBE_MARK = "version_info"

# `commands/release.md:41` verbatim, minus the leading `python3 `. R3b forwards exactly this,
# single quotes and `['version']` and all, because an inline `-c` that survives re-quoting in
# a hand-written fixture proves nothing about the real call site.
RELEASE_41_C_ARG = (
    "import json,sys; print(json.load(open('.claude-plugin/plugin.json'))['version'])"
)

REAL_PYTHON = shutil.which("python3")


def _bindir(tmp_path, name="bin"):
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def make_stub(bindir, body, name="python3"):
    """Write an executable shell double at <bindir>/<name>."""
    p = bindir / name
    p.write_text("#!/bin/bash\n" + body, encoding="utf-8")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return p


SILENT_EXIT_0 = """
exit 0
"""

# The alias shape as reported in the wild. NOTE, AND IT IS NOT A DETAIL: `exit 9009` in a
# POSIX shell is truncated to `9009 % 256` = **49**. The community-reported 9009 is what the
# Windows command processor surfaces; a shell double cannot reproduce the number, only the
# shape. R0c measures and asserts the 49, so the file cannot drift back into claiming
# otherwise.
ALIAS_9009 = """
echo "Python was not found; run without arguments to install from the Microsoft Store, or disable this shortcut from Settings > Manage App Execution Aliases."
exit 9009
"""

# AC2 forbids depending on any specific exit number, so two DIFFERENT observed codes are
# required to show it. This stub used to `exit 49` — which, because of the truncation above,
# was the *same* observed code as ALIAS_9009's. The two-codes requirement was therefore
# claimed and not met, from the plan down through the AC and the journal, and the row that
# caught it is the fixture-validity row added in a later fixup. `2` is far from 256 and is not
# produced by truncating anything in this file.
SILENT_EXIT_2 = """
exit 2
"""

# Exit 0 with NON-EMPTY, non-version output. Without this shape every stub that reaches the
# regex branch prints either nothing or a valid version, which made "exact match" and "merely
# non-empty" the same test — measured: replacing the regex with `.` left every original row
# green. This is the row that tells them apart.
GARBAGE_EXIT_0 = """
echo "Python was not found; run without arguments to install from the Microsoft Store."
exit 0
"""

# Exit 0 printing `major.minor.patch`. The spec accepts `major.minor` and nothing else, so an
# anchored regex must reject this. A prefix match would admit it, and nothing else here would
# notice.
THREE_COMPONENT_EXIT_0 = """
printf '%s' '3.12.1'
exit 0
"""

# A valid version string AND a non-zero exit. This is the only shape that can distinguish the
# exit-status check from the output check: every other failing stub is rejected by BOTH, so
# deleting either one left the suite green. AC2's "exits non-zero is rejected" had no oracle
# until this row.
VERSION_THEN_NONZERO = """
printf '%s' '3.12'
exit 1
"""

# Consumes stdin during the probe, echoes stdin on the real call. With the `< /dev/null` seal
# the probe reads nothing and the payload survives to the real call; without it, the probe
# eats the payload and the real call sees an empty stream. The seal's own comment calls it
# "load-bearing" — this row is what makes that a measured claim rather than an assertion.
STDIN_EATER = f"""
case "$*" in
  *{PROBE_MARK}*) /bin/cat > /dev/null; printf '%s' '3.12' ;;
  *) /bin/cat ;;
esac
"""


def py_launcher_stub():
    """A `py` double that behaves as a launcher: it only works when given `-3` first.

    This is the only candidate carried as TWO tokens, and it is the one that routes around
    the App Execution Alias entirely. Deleting the `py -3` candidate from the resolver left
    every original row green, because nothing planted a `py`.
    """
    return f"""
if [ "$1" != "-3" ]; then
  echo "PY-CALLED-WITHOUT-3: $*"
  exit 1
fi
shift
case "$*" in
  *{PROBE_MARK}*) printf '%s' '3.12' ;;
  *) echo "PY3-RAN: $*" ;;
esac
"""


def fake_python(version, marker):
    """A double that answers the probe with `version` and otherwise prints `marker`.

    Answering the probe is what gets it SELECTED; printing the marker on every other call is
    what makes the selection observable without needing a real interpreter.
    """
    return f"""
case "$*" in
  *{PROBE_MARK}*) printf '%s' '{version}' ;;
  *) echo "{marker}: $*" ;;
esac
"""


def forwarding_stub():
    """A double that IS the real interpreter — used where forwarding must be genuine."""
    return f'exec {REAL_PYTHON} "$@"\n'


def run(bindir, *args, env_extra=None, stdin=None, hermetic=True):
    env = {"PATH": str(bindir)} if hermetic else dict(os.environ)
    if not hermetic and bindir is not None:
        env["PATH"] = f"{bindir}:{env['PATH']}"
    # HOME is kept out of the hermetic env on purpose: nothing in direct mode may reach for a
    # dotfile, and a row that starts needing one should fail loudly here.
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["/bin/bash", str(RESOLVER), *args],
        capture_output=True,
        text=True,
        env=env,
        input=stdin,
    )


# --------------------------------------------------------------------------------------
# R0 — probe validity. First, and above every row that depends on it.
# --------------------------------------------------------------------------------------


def test_r0_the_farm_resolves_to_the_planted_double(tmp_path):
    """The `python3` the farm resolves IS the double this file planted, and nothing else."""
    bindir = _bindir(tmp_path)
    planted = make_stub(bindir, SILENT_EXIT_0)

    which = subprocess.run(
        ["/bin/bash", "-c", "command -v python3"],
        capture_output=True,
        text=True,
        env={"PATH": str(bindir)},
    )
    assert which.returncode == 0, "no python3 on the farm PATH at all — rows below are void"
    assert which.stdout.strip() == str(planted), (
        "the farm resolved a different python3 than the one planted; every rejection row "
        f"below would be unattributable. got: {which.stdout.strip()!r}"
    )

    # And the double really does behave as the row names claim.
    out = subprocess.run(
        [str(planted), "-c", "anything"], capture_output=True, text=True
    )
    assert out.returncode == 0 and out.stdout == "", (
        "the silent-exit-0 double is not silent-exit-0; R1 would be testing nothing"
    )


def test_r0c_every_fixture_shape_behaves_as_its_name_claims(tmp_path):
    """EVERY double, not just the first one.

    The earlier version of R0 validated `SILENT_EXIT_0` alone and left four other shapes
    unchecked, which is the same gap in miniature: a fixture nobody probed can make a
    rejection row pass for the wrong reason.
    """
    bindir = _bindir(tmp_path)
    probe = ["-c", "import sys; sys.stdout.write('x') # version_info"]

    cases = [
        # (body, name, expected rc, expected stdout prefix-or-exact, note)
        (SILENT_EXIT_0, "silent0", 0, "", "exit 0, prints nothing"),
        (SILENT_EXIT_2, "silent2", 2, "", "exit 2, prints nothing"),
        (ALIAS_9009, "alias", 49, "Python was not found", "alias shape; 9009 truncates to 49"),
        (GARBAGE_EXIT_0, "garbage", 0, "Python was not found", "exit 0, non-version text"),
        (THREE_COMPONENT_EXIT_0, "three", 0, "3.12.1", "exit 0, three components"),
        (VERSION_THEN_NONZERO, "vernonzero", 1, "3.12", "valid version, non-zero exit"),
    ]
    for body, name, want_rc, want_out, note in cases:
        p = make_stub(bindir, body, name=name)
        r = subprocess.run([str(p), *probe], capture_output=True, text=True)
        assert r.returncode == want_rc, f"{name} ({note}): rc {r.returncode} != {want_rc}"
        if want_out == "":
            assert r.stdout == "", f"{name} ({note}): expected silence, got {r.stdout!r}"
        else:
            assert r.stdout.startswith(want_out), (
                f"{name} ({note}): stdout {r.stdout!r} does not start with {want_out!r}"
            )

    # The version-answering double must answer the probe AND be distinguishable on a real call.
    p = make_stub(bindir, fake_python("3.12", "MARKER"), name="fake3")
    assert subprocess.run([str(p), *probe], capture_output=True, text=True).stdout == "3.12"
    real = subprocess.run([str(p), "-c", "whatever"], capture_output=True, text=True)
    assert "MARKER" in real.stdout, "the version double is not observable on a real call"


def test_r0b_a_real_interpreter_exists_for_the_forwarding_rows():
    """R3a/R3b/R7 need a genuine interpreter; say so plainly if the host has none."""
    assert REAL_PYTHON, "no real python3 on PATH — R3a/R3b/R7 cannot be honest here"
    out = subprocess.run(
        [REAL_PYTHON, "-c", "print('ok')"], capture_output=True, text=True
    )
    assert out.returncode == 0 and out.stdout.strip() == "ok"


# --------------------------------------------------------------------------------------
# R1 / R2 — the two shapes of a broken `python3` are both rejected.
# --------------------------------------------------------------------------------------


def test_r1_exit_zero_and_silent_is_rejected(tmp_path):
    """AC1 — the 0-byte alias: exits 0, prints nothing. Exit code alone cannot catch it."""
    bindir = _bindir(tmp_path)
    make_stub(bindir, SILENT_EXIT_0)
    r = run(bindir, "-c", "print('should not run')")
    assert r.returncode == 3, r.stderr
    assert "COULD NOT RUN" in r.stderr
    assert "should not run" not in r.stdout


def test_r2a_nonzero_9009_with_alias_message_is_rejected(tmp_path):
    """AC2 — rejected on `exit != 0`, not on the number 9009."""
    bindir = _bindir(tmp_path)
    make_stub(bindir, ALIAS_9009)
    r = run(bindir, "-c", "print('should not run')")
    assert r.returncode == 3, r.stderr
    assert "COULD NOT RUN" in r.stderr


def test_r2b_nonzero_49_and_silent_is_rejected(tmp_path):
    """AC2, second code. One exit code cannot show that no specific number is depended on."""
    bindir = _bindir(tmp_path)
    make_stub(bindir, SILENT_EXIT_2)
    r = run(bindir, "-c", "print('should not run')")
    assert r.returncode == 3, r.stderr
    assert "COULD NOT RUN" in r.stderr


# --------------------------------------------------------------------------------------
# R3 — a real interpreter is selected and the arguments arrive verbatim.
# --------------------------------------------------------------------------------------


def test_r3a_script_path_form_is_forwarded_verbatim(tmp_path):
    """AC3 — the script-path form, with arguments after it."""
    bindir = _bindir(tmp_path)
    make_stub(bindir, forwarding_stub())
    script = tmp_path / "echo_argv.py"
    script.write_text("import sys; print('|'.join(sys.argv[1:]))\n", encoding="utf-8")

    r = run(bindir, str(script), "alpha", "beta gamma")
    assert r.returncode == 0, r.stderr
    assert r.stdout == "alpha|beta gamma\n", r.stdout


def test_r3b_inline_dash_c_from_the_real_call_site_survives(tmp_path):
    """AC3 — `commands/release.md:41`'s actual string, quoting and all."""
    bindir = _bindir(tmp_path)
    make_stub(bindir, forwarding_stub())
    manifest_dir = tmp_path / ".claude-plugin"
    manifest_dir.mkdir()
    (manifest_dir / "plugin.json").write_text('{"version": "9.9.9"}\n', encoding="utf-8")

    r = subprocess.run(
        ["/bin/bash", str(RESOLVER), "-c", RELEASE_41_C_ARG],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={"PATH": str(bindir)},
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "9.9.9", r.stdout


# --------------------------------------------------------------------------------------
# R4 — nothing works, and the message says what was tried.
# --------------------------------------------------------------------------------------


def test_r4_direct_mode_names_every_candidate_it_tried(tmp_path):
    """AC4 — stderr, exit 3, and each candidate named with how it failed."""
    bindir = _bindir(tmp_path)
    make_stub(bindir, SILENT_EXIT_0)
    make_stub(bindir, SILENT_EXIT_2, name="python")

    r = run(bindir, "-c", "print(1)")
    assert r.returncode == 3
    assert r.stdout == "", "a failure must not write to stdout; callers parse it"
    assert "COULD NOT RUN" in r.stderr

    # BOTH assertions below replaced vacuous ones, and the replacement is the point of the
    # row. The originals were `"python3" in stderr and "python" in stderr` — which cannot
    # fail, because `python` is a substring of `python3` — and `any(word in stderr for word
    # in ("exit", "output", "not found"))`, which the farm satisfies forever because `py -3`
    # is always reported "(not found)". Measured: stripping every per-candidate reason from
    # the resolver left the old row green.
    #
    # The exact strings below bind each candidate to ITS OWN reason, so a message that names
    # candidates without saying how each failed now goes red.
    assert "[python3] (unexpected output: '')" in r.stderr, (
        f"python3 exits 0 and prints nothing; its reason must say so. got: {r.stderr!r}"
    )
    assert "[python] (exit 2)" in r.stderr, (
        f"python exits 2; its reason must carry the code. got: {r.stderr!r}"
    )
    assert "[py] [-3] (not found)" in r.stderr, (
        f"the two-token candidate must be reported as two words. got: {r.stderr!r}"
    )


# --------------------------------------------------------------------------------------
# R6 — a Python 2 reached through candidate 5 is rejected.
# --------------------------------------------------------------------------------------


def test_r6_python_two_is_rejected_when_python3_is_absent(tmp_path):
    """AC6 — the major floor. `python` is candidate 5, so a Python 2 is genuinely reachable."""
    bindir = _bindir(tmp_path)
    make_stub(bindir, fake_python("2.7", "PY2-RAN"), name="python")

    r = run(bindir, "-c", "print(1)")
    assert r.returncode == 3, r.stderr
    assert "COULD NOT RUN" in r.stderr
    assert "PY2-RAN" not in r.stdout


# --------------------------------------------------------------------------------------
# R7 — on an unmodified PATH the resolver is invisible.
# --------------------------------------------------------------------------------------


def test_r7_unmodified_path_is_byte_identical_to_calling_python3(tmp_path):
    """The control. If this row ever diverges, the resolver has started having opinions."""
    script = tmp_path / "noisy.py"
    script.write_text(
        "import sys\n"
        "sys.stdout.write('OUT')\n"
        "sys.stderr.write('ERR')\n"
        "sys.exit(7)\n",
        encoding="utf-8",
    )
    direct = subprocess.run(
        [REAL_PYTHON, str(script)], capture_output=True, text=True
    )
    through = subprocess.run(
        ["/bin/bash", str(RESOLVER), str(script)], capture_output=True, text=True
    )
    assert through.stdout == direct.stdout == "OUT"
    assert through.stderr == direct.stderr == "ERR"
    assert through.returncode == direct.returncode == 7


# --------------------------------------------------------------------------------------
# R10 — a WindowsApps path is not a verdict.
# --------------------------------------------------------------------------------------


def test_r10_a_working_interpreter_under_windowsapps_is_selected(tmp_path):
    """AC7 — a genuine Store-installed Python lives there too; the substring is not evidence."""
    bindir = _bindir(tmp_path, name="AppData/Local/Microsoft/WindowsApps")
    make_stub(bindir, fake_python("3.12", "WINAPPS-RAN"))

    r = run(bindir, "-c", "print(1)")
    assert r.returncode == 0, r.stderr
    assert "WINAPPS-RAN" in r.stdout, r.stdout


# --------------------------------------------------------------------------------------
# R11 / R12 / R13 / R14 — precedence, fall-through, and "order is not selection".
# --------------------------------------------------------------------------------------


def test_r11_a_failing_override_falls_through(tmp_path):
    """A stale `$PLC_PYTHON` is a far more common accident than a deliberate one."""
    bindir = _bindir(tmp_path)
    make_stub(bindir, fake_python("3.12", "PYTHON3-RAN"))
    make_stub(bindir, SILENT_EXIT_0, name="brokenpy")

    r = run(bindir, "-c", "print(1)", env_extra={"PLC_PYTHON": "brokenpy"})
    assert r.returncode == 0, r.stderr
    assert "PYTHON3-RAN" in r.stdout, r.stdout


def test_r12_a_passing_override_wins_over_python3(tmp_path):
    """Precedence, proven where it is observable — both candidates work."""
    bindir = _bindir(tmp_path)
    make_stub(bindir, fake_python("3.12", "PYTHON3-RAN"))
    make_stub(bindir, fake_python("3.11", "OVERRIDE-RAN"), name="mypy3")

    r = run(bindir, "-c", "print(1)", env_extra={"PLC_PYTHON": "mypy3"})
    assert r.returncode == 0, r.stderr
    assert "OVERRIDE-RAN" in r.stdout, r.stdout
    assert "PYTHON3-RAN" not in r.stdout


def test_r13_the_conventional_python_var_is_honoured(tmp_path):
    """`$PYTHON` is candidate 2 — the var node-gyp also honours."""
    bindir = _bindir(tmp_path)
    make_stub(bindir, fake_python("3.12", "PYTHON3-RAN"))
    make_stub(bindir, fake_python("3.11", "PYTHONVAR-RAN"), name="othrpy")

    r = run(bindir, "-c", "print(1)", env_extra={"PYTHON": "othrpy"})
    assert r.returncode == 0, r.stderr
    assert "PYTHONVAR-RAN" in r.stdout, r.stdout


def test_r14_bare_python_is_selected_when_it_is_a_python_three(tmp_path):
    """Candidate 5 is reachable, and reaching it is not by itself a failure."""
    bindir = _bindir(tmp_path)
    make_stub(bindir, fake_python("3.12", "BAREPY-RAN"), name="python")

    r = run(bindir, "-c", "print(1)")
    assert r.returncode == 0, r.stderr
    assert "BAREPY-RAN" in r.stdout, r.stdout


# ======================================================================================
# Rows below were added in a later fixup. Independent reviews, run on different
# lenses, found that the original rows left a documented guarantee unpinned: several
# separate mutations of the resolver kept them all green. Each row below exists to kill
# one named mutation, and the mutation it kills is written in its docstring — a row whose
# mutation is not named is a row nobody can check.
# ======================================================================================


def test_r1b_exit_zero_with_non_version_output_is_rejected(tmp_path):
    """Kills: regex loosened to "any non-empty output", and to an unanchored match.

    Every original stub that reached the regex printed either nothing or a valid version, so
    "matches `^N.N$`" and "is non-empty" were the same test. Measured: replacing the whole
    regex with `.` left every row green. This stub exits 0 and prints a sentence.
    """
    bindir = _bindir(tmp_path)
    make_stub(bindir, GARBAGE_EXIT_0)
    r = run(bindir, "-c", "print('should not run')")
    assert r.returncode == 3, r.stderr
    assert "COULD NOT RUN" in r.stderr
    assert "unexpected output" in r.stderr, (
        f"the reason must say the output was wrong, not that the exit code was: {r.stderr!r}"
    )


def test_r1c_a_three_component_version_is_rejected(tmp_path):
    """Kills: the trailing `$` dropped from the version regex.

    The spec accepts `major.minor` and nothing else. A prefix match admits `3.12.1`, and
    before this row nothing noticed.
    """
    bindir = _bindir(tmp_path)
    make_stub(bindir, THREE_COMPONENT_EXIT_0)
    r = run(bindir, "-c", "print('should not run')")
    assert r.returncode == 3, r.stderr
    assert "3.12.1" in r.stderr, (
        f"the rejected output should be quoted back so the cause is visible: {r.stderr!r}"
    )


def test_r2c_a_valid_version_with_a_nonzero_exit_is_rejected(tmp_path):
    """Kills: the `probe_rc -ne 0` check deleted entirely.

    This is the AC2 oracle that was missing. R2a and R2b both print nothing or a sentence, so
    the OUTPUT check rejected them whether or not the exit code was ever looked at — measured:
    replacing the rc check with `if false` left every row green. Only a stub that satisfies the
    output check and fails the exit check can tell the two apart.
    """
    bindir = _bindir(tmp_path)
    make_stub(bindir, VERSION_THEN_NONZERO)
    r = run(bindir, "-c", "print('should not run')")
    assert r.returncode == 3, r.stderr
    assert "[python3] (exit 1)" in r.stderr, (
        f"rejection must be attributed to the exit status, not the output: {r.stderr!r}"
    )


def test_r9a_the_stdin_seal_keeps_the_payload_for_the_real_call(tmp_path):
    """Kills: `< /dev/null` deleted from the probe.

    The seal's own comment calls it load-bearing because hook mode is handed the Stop
    payload on stdin. Measured: deleting it left every row green. This stub eats stdin during the
    probe and echoes it on the real call, so an unsealed probe produces an empty echo.
    """
    bindir = _bindir(tmp_path)
    make_stub(bindir, STDIN_EATER)
    r = run(bindir, "-c", "unused", stdin="PAYLOAD-SURVIVED")
    assert r.returncode == 0, r.stderr
    assert r.stdout == "PAYLOAD-SURVIVED", (
        "the probe consumed the payload before the real call could read it; "
        f"got {r.stdout!r}"
    )


def test_r15_the_two_token_py_launcher_is_a_real_candidate(tmp_path):
    """Kills: the `py -3` candidate deleted, and the shell-word split collapsed.

    `py -3` is the only candidate carried as two tokens and the only one that routes around
    the App Execution Alias through the registry rather than PATH. Measured: deleting it left
    every row green, because nothing planted a `py`. The stub refuses to work unless it actually
    receives `-3` as its first argument, so a single-token `py` would fail this row.
    """
    bindir = _bindir(tmp_path)
    make_stub(bindir, py_launcher_stub(), name="py")
    make_stub(bindir, SILENT_EXIT_0)  # python3 present but broken

    r = run(bindir, "-c", "print(1)")
    assert r.returncode == 0, r.stderr
    assert "PY3-RAN: -c print(1)" in r.stdout, r.stdout
    assert "PY-CALLED-WITHOUT-3" not in r.stdout, (
        "the launcher was invoked without its -3, so the candidate was not split into words"
    )


def test_r16_python3_is_preferred_over_python_when_both_work(tmp_path):
    """Kills: `python` moved ahead of `python3` in the candidate list.

    R14 planted only `python`, so it proved reachability, never precedence. Measured: the
    swap left every row green. On a real Windows box with both present, the swap picks the wrong
    interpreter.
    """
    bindir = _bindir(tmp_path)
    make_stub(bindir, fake_python("3.12", "PYTHON3-RAN"))
    make_stub(bindir, fake_python("3.11", "BAREPY-RAN"), name="python")

    r = run(bindir, "-c", "print(1)")
    assert r.returncode == 0, r.stderr
    assert "PYTHON3-RAN" in r.stdout, r.stdout
    assert "BAREPY-RAN" not in r.stdout


def test_r17_plc_python_outranks_python_when_both_are_set_and_both_work(tmp_path):
    """Kills: `$PYTHON` moved ahead of `$PLC_PYTHON`.

    R12 and R13 each pinned one env var against `python3`, never against each other.
    Measured: the swap left every row green.
    """
    bindir = _bindir(tmp_path)
    make_stub(bindir, fake_python("3.12", "PYTHON3-RAN"))
    make_stub(bindir, fake_python("3.11", "PLCVAR-RAN"), name="apy")
    make_stub(bindir, fake_python("3.10", "PYTHONVAR-RAN"), name="bpy")

    r = run(bindir, "-c", "print(1)", env_extra={"PLC_PYTHON": "apy", "PYTHON": "bpy"})
    assert r.returncode == 0, r.stderr
    assert "PLCVAR-RAN" in r.stdout, r.stdout
    assert "PYTHONVAR-RAN" not in r.stdout
    assert "PYTHON3-RAN" not in r.stdout


def test_r18_a_spaced_value_that_is_NOT_a_file_still_shows_its_split(tmp_path):
    """Kills: the per-word bracketing collapsed back to a `"$*"` join.

    The script promised "the failure message shows what the value split into" while printing
    something byte-identical to the value typed, so a path with a space was reported "not
    found" with nothing naming the cause. The promise was kept and the code fixed.

    THIS ROW'S FIXTURE CHANGED when the whole-value-first branch landed: it now uses a path
    that does NOT exist, because an existing executable with a space in it is no longer a
    failure at all — that is R18b. A row whose premise a later change quietly removed is
    worse than a missing row, so the premise was changed with it rather than the assertion
    weakened.
    """
    # Exactly ONE space, because the assertion below splits on one. The first version of
    # this fixture used "no such dir" — three words — and the row went red on the
    # assertion's arithmetic rather than on the behaviour. The test was wrong, not the code.
    missing = str(tmp_path / "no-such-dir" / "py thon9")

    bindir = _bindir(tmp_path)
    make_stub(bindir, SILENT_EXIT_0)

    r = run(bindir, "-c", "print(1)", env_extra={"PLC_PYTHON": missing})
    assert r.returncode == 3, r.stderr
    head, tail = missing.split(" ", 1)
    assert f"[{head}] [{tail}]" in r.stderr, (
        "the message must show the words the value became, not the value as typed; "
        f"got {r.stderr!r}"
    )


def test_r18b_an_executable_path_containing_spaces_is_used_whole(tmp_path):
    """Kills: the whole-value-first branch deleted, or weakened to a guess.

    `C:\\Program Files\\Python312\\python.exe` is the commonest shape of the commonest
    override on the one platform this script exists for, and until this branch existed it
    was split into two words and reported "not found" about a file that does exist.

    The rule is a DISCRIMINATOR, not a heuristic: if the entire value names an executable
    file then it cannot also be a `command + argument` line, because a two-token command line
    is not a filename. R15 holds the other side — `py -3` is not a file, so it still splits.
    """
    spaced = tmp_path / "sp ace"
    spaced.mkdir()
    real = make_stub(spaced, fake_python("3.12", "SPACED-RAN"), name="python9")
    assert " " in str(real), "the fixture must actually contain a space, or this proves nothing"

    bindir = _bindir(tmp_path)
    make_stub(bindir, SILENT_EXIT_0)  # python3 present but broken, so nothing else can rescue

    r = run(bindir, "-c", "print(1)", env_extra={"PLC_PYTHON": str(real)})
    assert r.returncode == 0, (
        f"an executable whose path contains a space must be usable; got {r.stderr!r}"
    )
    assert "SPACED-RAN" in r.stdout, r.stdout


# ======================================================================================
# Hook mode. `--hook` is the FIRST argument, is stripped before forwarding, and the
# resolver exits 0 unconditionally because `commands/init-harness.md:234` documents the
# generated Stop hook as having to. Consequence, stated rather than discovered: the
# interpreter's own exit status is DISCARDED in this mode, so hook mode guarantees "speaks up
# when the interpreter is missing" and NOT "speaks up when the script fails".
# ======================================================================================

# A double whose probe output carries a double quote, a backslash and a newline. If any part
# of the emitted JSON were interpolated from what a candidate printed, this payload would
# break it. The envelope is specified as all-literal; this is what holds that line.
HOSTILE_OUTPUT_EXIT_0 = """
printf '%s' 'he said "hi" \\ and
then a newline'
exit 0
"""

# Exits non-zero on the REAL call while passing the probe. Hook mode must still exit 0.
GOOD_PROBE_FAILING_SCRIPT = f"""
case "$*" in
  *{PROBE_MARK}*) printf '%s' '3.12' ;;
  *) echo "RAN: $*"; exit 7 ;;
esac
"""

# Echoes whatever reaches it on stdin, on the real call only.
HOOK_STDIN_ECHO = f"""
case "$*" in
  *{PROBE_MARK}*) printf '%s' '3.12' ;;
  *) /bin/cat ;;
esac
"""


INTERPRETER_NAMES = ("python3", "python", "py")


def _assert_only_the_farm_supplies_an_interpreter(path: str, bindir) -> None:
    """The test's isolation, checked instead of assumed.

    THIS ROW EXISTS BECAUSE THE ASSUMPTION WAS FALSE AND CI SAID SO. `with_bin=True` used to
    append `/bin` to PATH, justified in this docstring by "`/bin` carries no python on
    macOS". That is a fact about one machine, not about the test: on the Linux runner `/bin`
    is `/usr/bin` and carries a real `python`, so the resolver found it, ran it, and hook
    mode printed the script's own output instead of the envelope. Rows went red in CI
    after a full local suite was green — the claim (the farm decides which interpreter is
    found) was wider than the mechanism (it only held where /bin happens to be empty of
    pythons). Reproduced locally before it was fixed, by putting a real `python` beside the
    clock: stdout became `1\\n`, byte-identical to the runner's.
    """
    for name in INTERPRETER_NAMES:
        found = shutil.which(name, path=path)
        if found is None:
            continue
        assert pathlib.Path(found).parent == pathlib.Path(bindir), (
            f"test isolation broken: {name} resolves to {found}, outside the stub farm "
            f"{bindir}. The resolver would find a real interpreter and this row would be "
            f"measuring the wrong thing."
        )


def hook_run(bindir, *args, env_extra=None, stdin=None, with_bin=False):
    """Launch the resolver in hook mode.

    `with_bin=True` means "hook mode needs a clock" — reading one is the only thing in this
    script that is not a bash builtin (see R21, which pins what happens when it is
    unavailable). It is satisfied by linking `date` INTO the farm, never by putting a system
    directory on PATH: what such a directory contains is a property of the host, and this
    suite must not depend on one. `_assert_only_the_farm_supplies_an_interpreter` is the
    guard that keeps that true on a host nobody here has run on.
    """
    if with_bin:
        clock = shutil.which("date", path="/bin:/usr/bin") or "/bin/date"
        link = pathlib.Path(bindir) / "date"
        if not link.exists():
            link.symlink_to(clock)
    path = str(bindir)
    _assert_only_the_farm_supplies_an_interpreter(path, bindir)
    env = {"PATH": path}
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["/bin/bash", str(RESOLVER), "--hook", *args],
        capture_output=True,
        text=True,
        env=env,
        input=stdin,
    )


def test_the_isolation_guard_fires_when_an_interpreter_lives_outside_the_farm(tmp_path):
    """A control for the guard above, which no other row can exercise.

    `hook_run` now builds PATH from the farm alone, so inside the suite the guard can never
    see an outside interpreter — it is there to catch a FUTURE edit that puts a system
    directory back on PATH, which is exactly the edit that produced red rows in CI. An
    assertion nothing can make fail is indistinguishable from one that was deleted, so this
    row hands it the broken shape directly.
    """
    farm = _bindir(tmp_path)
    make_stub(farm, SILENT_EXIT_0)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "python").write_text("#!/bin/bash\nprintf '%s' 3.12\n", encoding="utf-8")
    (outside / "python").chmod(0o755)

    # The shape the suite uses today: clean.
    _assert_only_the_farm_supplies_an_interpreter(str(farm), farm)

    # The shape that broke CI: a system directory appended, carrying a real interpreter.
    with pytest.raises(AssertionError, match="test isolation broken"):
        _assert_only_the_farm_supplies_an_interpreter(f"{farm}:{outside}", farm)


def test_r5_hook_mode_emits_a_system_message_and_exits_zero(tmp_path):
    """AC5 — the failure channel is a JSON object on stdout, and the exit code is 0."""
    import json

    bindir = _bindir(tmp_path)
    make_stub(bindir, SILENT_EXIT_0)
    marker = tmp_path / "warn-marker"

    r = hook_run(
        bindir,
        "-c",
        "print(1)",
        env_extra={"PLC_PYTHON_WARN_MARKER": str(marker)},
        with_bin=True,
    )
    assert r.returncode == 0, (
        f"hook mode must exit 0 even when nothing works; got {r.returncode}, {r.stderr!r}"
    )
    assert r.stdout.count("\n") <= 1, f"the envelope must be one line: {r.stdout!r}"
    payload = json.loads(r.stdout)
    assert "systemMessage" in payload, payload
    assert payload["systemMessage"].strip(), "an empty systemMessage says nothing"


def test_r5b_the_envelope_is_all_literal_and_interpolates_nothing(tmp_path):
    """Hand-written JSON is safe ONLY because every byte is fixed in the script.

    A candidate's stdout is attacker- or accident-controlled and may carry quotes, backslashes
    and newlines. If the envelope quoted it, this row would produce invalid JSON. The row
    exists because a reviewer raised exactly this as the risk the original shape handed to hook mode.
    """
    import json

    bindir = _bindir(tmp_path)
    make_stub(bindir, HOSTILE_OUTPUT_EXIT_0)
    marker = tmp_path / "warn-marker"

    r = hook_run(
        bindir,
        "-c",
        "print(1)",
        env_extra={"PLC_PYTHON_WARN_MARKER": str(marker)},
        with_bin=True,
    )
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)  # would raise on a leaked quote or newline
    assert "he said" not in payload["systemMessage"], (
        "the candidate's own output reached the envelope; it must be all-literal"
    )


def test_r8_the_warning_is_rate_limited_by_a_time_window(tmp_path):
    """AC5's throttle. NOT per session — the session id is unreachable, see the AC11 note.

    Three calls: warn, silent inside the window, warn again once the window has elapsed. A
    zero-length window is "the window has elapsed", which is why the third call is a window
    change rather than a sleep.
    """
    bindir = _bindir(tmp_path)
    make_stub(bindir, SILENT_EXIT_0)
    marker = tmp_path / "warn-marker"
    inside = {"PLC_PYTHON_WARN_MARKER": str(marker), "PLC_PYTHON_WARN_WINDOW": "3600"}
    elapsed = {"PLC_PYTHON_WARN_MARKER": str(marker), "PLC_PYTHON_WARN_WINDOW": "0"}

    first = hook_run(bindir, "-c", "print(1)", env_extra=inside, with_bin=True)
    assert first.returncode == 0 and "systemMessage" in first.stdout, first.stdout

    second = hook_run(bindir, "-c", "print(1)", env_extra=inside, with_bin=True)
    assert second.returncode == 0, second.stderr
    assert second.stdout == "", (
        f"a second call inside the window must be silent; got {second.stdout!r}"
    )

    third = hook_run(bindir, "-c", "print(1)", env_extra=elapsed, with_bin=True)
    assert third.returncode == 0 and "systemMessage" in third.stdout, (
        f"once the window has elapsed the warning must return; got {third.stdout!r}"
    )


def test_r21_an_unreadable_clock_warns_rather_than_suppresses(tmp_path):
    """The throttle fails toward SPEAKING UP, which is the repo's own doctrine.

    Reading the clock is the one non-builtin in this script. With `/bin` off PATH there is no
    `date`, so the window cannot be evaluated. A throttle that silently suppressed on
    ignorance would be a guard reporting enforcement it is not performing — the exact shape
    that has been closed before. Note the marker is pre-filled with a fresh-looking value, so "suppress"
    is the behaviour this row has to rule out.
    """
    bindir = _bindir(tmp_path)
    make_stub(bindir, SILENT_EXIT_0)
    marker = tmp_path / "warn-marker"
    marker.write_text("99999999999\n", encoding="utf-8")  # far future = inside any window

    r = hook_run(
        bindir,
        "-c",
        "print(1)",
        env_extra={"PLC_PYTHON_WARN_MARKER": str(marker), "PLC_PYTHON_WARN_WINDOW": "3600"},
        with_bin=False,  # no /bin, so no `date`
    )
    assert r.returncode == 0, r.stderr
    assert "systemMessage" in r.stdout, (
        "with no readable clock the throttle must warn, never go quiet; "
        f"got {r.stdout!r}"
    )


def test_r9_a_stdin_payload_reaches_the_interpreter_in_hook_mode(tmp_path):
    """AC3's hook half. The Stop payload arrives on stdin and must survive the probe."""
    bindir = _bindir(tmp_path)
    make_stub(bindir, HOOK_STDIN_ECHO)

    r = hook_run(
        bindir, "-c", "unused", stdin='{"session_id":"abc"}', with_bin=True
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout == '{"session_id":"abc"}', (
        f"the probe consumed the Stop payload before the interpreter saw it: {r.stdout!r}"
    )


def test_r19_hook_mode_exits_zero_even_when_the_script_fails(tmp_path):
    """`run`, not `exec`, and then exit 0 unconditionally.

    The guarantee this buys is narrower than it looks and the narrowness is deliberate: hook
    mode reports a MISSING INTERPRETER, not a failing script. An `exec` here would pass the
    script's status through and break the always-exit-0 contract.
    """
    bindir = _bindir(tmp_path)
    make_stub(bindir, GOOD_PROBE_FAILING_SCRIPT)

    r = hook_run(bindir, "-c", "print(1)", with_bin=True)
    assert r.returncode == 0, (
        f"the interpreter exited 7; hook mode must still exit 0, got {r.returncode}"
    )
    assert "RAN: -c print(1)" in r.stdout, r.stdout


def test_r20_the_hook_flag_is_stripped_and_never_forwarded(tmp_path):
    """`--hook` is the resolver's own argument, not the interpreter's."""
    bindir = _bindir(tmp_path)
    make_stub(bindir, fake_python("3.12", "HOOKRUN"))

    r = hook_run(bindir, "-c", "print(1)", with_bin=True)
    assert r.returncode == 0, r.stderr
    assert "HOOKRUN: -c print(1)" in r.stdout, r.stdout
    assert "--hook" not in r.stdout, (
        f"the flag was forwarded to the interpreter: {r.stdout!r}"
    )
