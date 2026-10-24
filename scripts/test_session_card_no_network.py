"""The standing oracle for `session-card-no-network.sh`.

A mutation demonstrated once at the keyboard is a
MEASUREMENT, not an oracle: it proves the check could go red that day and
nothing about tomorrow. These tests are what keeps it true — every arm is
exercised against a COPY of the real file in `tmp_path`, so nothing here can
leave the working tree mutated the way a `git checkout`-based matrix can (such
a matrix can erase an uncommitted
fix and then report a clean sweep).
"""
from __future__ import annotations
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO = Path(__file__).resolve().parent.parent
GUARD = REPO / "scripts" / "invariants" / "session-card-no-network.sh"


def _tree(tmp_path: Path, body: str | None = None,
          reconcile_body: str | None = None) -> Path:
    """A minimal work-tree-shaped directory holding a copy of BOTH guarded files.

    Not a git repo: the guard takes the root as its argument, so it never needs
    one. That keeps every case here independent of the real index.

    The guard has a SECOND target (`scripts/handoff_reconcile.py`), so the
    tree carries a copy of that too. The alternative -- letting the guard skip a
    target that is absent -- was rejected: a missing target is `COULD NOT RUN`,
    never a silent pass, which is the whole reason this guard has a third verdict.
    """
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    dst = tmp_path / "scripts" / "session_card.py"
    if body is None:
        shutil.copyfile(REPO / "scripts" / "session_card.py", dst)
    else:
        dst.write_text(body, encoding="utf-8")
    rec = tmp_path / "scripts" / "handoff_reconcile.py"
    if reconcile_body is None:
        shutil.copyfile(REPO / "scripts" / "handoff_reconcile.py", rec)
    else:
        rec.write_text(reconcile_body, encoding="utf-8")
    return dst


def _run(root: Path):
    return subprocess.run(
        ["/bin/bash", str(GUARD), str(root)],
        capture_output=True, text=True,
    )


def test_clean_copy_passes(tmp_path):
    _tree(tmp_path)
    r = _run(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "PASS session-card-no-network" in r.stdout
    # The pinned numbers are printed, not merely compared. A guard that says only
    # "ok" cannot be audited by the person reading its output.
    # 2 -> 3 in the station-position change: the card now derives a station position, which means reading
    # the two shipped grammar readers rather than re-parsing either format in Python.
    # The guard's own header carries the design reason; this line carries the number.
    assert "subprocess call sites: 3 (pinned 3)" in r.stdout
    assert "injected-runner call sites: 6 (pinned 6)" in r.stdout


def test_a_new_subprocess_call_site_goes_red(tmp_path):
    """The plan's named mutation, made standing.

    Written earlier, when the criterion said that phase added no new call site. the station-position change DID
    add one, deliberately, with the reason recorded in the guard's own header. What
    this case still proves is the durable half, and it is the half that matters: a
    call site appearing WITHOUT the baseline moving is red."""
    dst = _tree(tmp_path)
    src = dst.read_text(encoding="utf-8")
    needle = "def main(argv=None) -> int:\n"
    assert src.count(needle) == 1
    dst.write_text(
        src.replace(needle, needle + '    subprocess.run(["echo", "probe"])\n'),
        encoding="utf-8",
    )
    r = _run(tmp_path)
    assert r.returncode == 1
    assert "subprocess call sites: 4 found, 3 expected" in r.stdout


def test_an_aliased_import_goes_red(tmp_path):
    """THE MUTATION THAT DEFEATS A COUNT-ONLY GUARD, kept as the
    regression for the arm that closed it.

    Written to demonstrate that counting beats absence-of-substring, it instead
    demonstrated that this guard had the very hole it was built to close:
    `from subprocess import run as _r` followed by `_r([...])` matches neither
    `subprocess.` nor `run([`, both counts stayed at their baselines, and a file
    that had just grown a new process spawn passed clean. The counting argument
    was right about renaming the CALL and wrong about renaming the IMPORT.

    The arm that fixed it is a conservation law — every `subprocess` token is
    either the one import or one of the pinned call sites — so it is not one
    more spelling to evade."""
    dst = _tree(tmp_path)
    src = dst.read_text(encoding="utf-8")
    needle = "def main(argv=None) -> int:\n"
    dst.write_text(
        src.replace(
            needle,
            "from subprocess import run as _r\n\n\n" + needle
            + '    _r(["echo", "probe"])\n',
        ),
        encoding="utf-8",
    )
    r = _run(tmp_path)
    assert r.returncode == 1, r.stdout
    assert "`subprocess` token appears 5 times but only 4 are accounted for" in r.stdout


def test_aliasing_the_module_itself_goes_red(tmp_path):
    """The other half of the same hole: `import subprocess as sp` keeps the token
    count at one while emptying the call-site count. It trips a different arm,
    which is the point — the property bought is "every spelling moves SOME
    number", not "this one pattern is banned"."""
    dst = _tree(tmp_path)
    src = dst.read_text(encoding="utf-8")
    assert src.count("import subprocess\n") == 1
    src = src.replace("import subprocess\n", "import subprocess as sp\n")
    src = src.replace("subprocess.run(", "sp.run(")
    dst.write_text(src, encoding="utf-8")
    r = _run(tmp_path)
    assert r.returncode == 1, r.stdout
    assert "subprocess call sites: 0 found, 3 expected" in r.stdout


def test_a_seventh_git_command_goes_red(tmp_path):
    """The second count, which is the one the CI row actually MOVED (5 -> 6). Without
    it, "one additional invocation of the existing runner" would be a claim in
    prose rather than a checked statement."""
    dst = _tree(tmp_path)
    src = dst.read_text(encoding="utf-8")
    needle = '    clean = run(["status", "--porcelain"]).strip() == ""\n'
    assert src.count(needle) == 1
    dst.write_text(
        src.replace(needle, needle + '    _p = run(["config", "--get", "remote.origin.url"])\n'),
        encoding="utf-8",
    )
    r = _run(tmp_path)
    assert r.returncode == 1
    assert "injected-runner call sites: 7 found, 6 expected" in r.stdout


def test_a_networking_import_goes_red(tmp_path):
    dst = _tree(tmp_path)
    src = dst.read_text(encoding="utf-8")
    dst.write_text("import urllib.request\n" + src, encoding="utf-8")
    r = _run(tmp_path)
    assert r.returncode == 1
    assert "a networking module is imported" in r.stdout


def test_a_missing_target_cannot_run_rather_than_passing(tmp_path):
    """The could-not-run distinction. A check that could not run must never report as though
    it did — and it must BLOCK, because the gate reads status only."""
    r = _run(tmp_path)                       # no scripts/session_card.py at all
    assert r.returncode == 3
    assert "COULD NOT RUN" in r.stdout
    assert "PASS" not in r.stdout


def test_a_directory_named_session_card_py_cannot_run(tmp_path):
    """`-f`, never `-e`. A directory would send `-e` into a grep that matches
    nothing and produce a confident, false PASS."""
    (tmp_path / "scripts" / "session_card.py").mkdir(parents=True)
    r = _run(tmp_path)
    assert r.returncode == 3
    assert "COULD NOT RUN" in r.stdout


def test_an_empty_scan_cannot_run_rather_than_passing(tmp_path):
    """THE EMPTY-SET GUARD, and it is the assertion this file exists for. A file
    with zero call sites and a scan that matched nothing produce the same two
    numbers. Reporting PASS for the second is 'I looked away' wearing the
    costume of 'I checked'."""
    _tree(tmp_path, body="x = 1\n")
    r = _run(tmp_path)
    assert r.returncode == 3
    assert "ZERO call sites" in r.stdout
    assert "PASS" not in r.stdout


def test_the_guard_is_declared_in_the_close_gate_manifest(tmp_path):
    """A guard nothing runs is a guard that does not exist. Checked here rather
    than trusted, because the wiring and the script are edited in different
    files and drift one at a time."""
    import json
    m = json.loads((REPO / ".claude" / "close-gate.json").read_text(encoding="utf-8"))
    names = [i["name"] for i in m["invariants"]]
    assert "session-card-no-network" in names
    row = next(i for i in m["invariants"] if i["name"] == "session-card-no-network")
    assert "session-card-no-network.sh" in row["command"]


def test_dunder_import_goes_red(tmp_path):
    """`__import__` is closed rather than left as a known limit — a
    documented hole is still a hole, and closing it
    takes one line.

    The exact input:
    `__import__("urllib.request").request.urlopen(...)` — no `subprocess` token,
    no `run([`, and no import STATEMENT for the networking-import arm to see."""
    dst = _tree(tmp_path)
    src = dst.read_text(encoding="utf-8")
    needle = "def main(argv=None) -> int:\n"
    dst.write_text(
        src.replace(
            needle,
            needle + '    __import__("urllib.request").request.urlopen("https://example.invalid")\n',
        ),
        encoding="utf-8",
    )
    r = _run(tmp_path)
    assert r.returncode == 1, r.stdout
    assert "__import__" in r.stdout


def test_the_dunder_import_arm_is_not_satisfied_by_a_mention_in_a_comment(tmp_path):
    """The arm strips whole-line comments before counting, the same way the
    subprocess arms do — otherwise the guard's own explanatory comment about
    `__import__` would make the file permanently red, and the obvious 'fix'
    would be to delete the explanation."""
    dst = _tree(tmp_path)
    src = dst.read_text(encoding="utf-8")
    dst.write_text("# a note mentioning __import__ in prose\n" + src, encoding="utf-8")
    r = _run(tmp_path)
    assert r.returncode == 0, r.stdout


def test_importlib_with_whitespace_after_the_dot_goes_red(tmp_path):
    """`importlib. import_module(...)` — whitespace
    after the attribute dot — is VALID PYTHON, and a
    tight regex misses it. This is the ordinary-drift end of the spectrum (a line
    wrap or an autoformatter produces it), which is why it is closed while the
    string-splitting evasion is deliberately not."""
    dst = _tree(tmp_path)
    src = dst.read_text(encoding="utf-8")
    needle = "def main(argv=None) -> int:\n"
    dst.write_text(
        src.replace(
            needle,
            "import importlib\n\n\n" + needle
            + '    importlib. import_module("urllib.request")\n',
        ),
        encoding="utf-8",
    )
    r = _run(tmp_path)
    assert r.returncode == 1, r.stdout
    assert "DYNAMIC IMPORT" in r.stdout


# ---------------------------------------------------------------------------
# The SECOND target. Each arm below was also demonstrated by hand, and
# that is exactly why these exist: this file's own docstring says a pasted
# transcript is a measurement, not an oracle. It proves the arm could go red
# today and nothing about tomorrow.
# ---------------------------------------------------------------------------

def _rec_src() -> str:
    return (REPO / "scripts" / "handoff_reconcile.py").read_text(encoding="utf-8")


def test_clean_copy_of_the_reconcile_module_passes(tmp_path):
    _tree(tmp_path)
    r = _run(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "reconcile (scripts/handoff_reconcile.py)" in r.stdout
    assert "subprocess call sites: 1 (pinned 1)" in r.stdout
    assert "network-capable git subcommands: 1 (pinned 1)" in r.stdout


def test_a_missing_second_target_cannot_run_rather_than_passing(tmp_path):
    """Fail-closed. An absent target must NOT be skipped into a clean bill of health."""
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO / "scripts" / "session_card.py",
                    tmp_path / "scripts" / "session_card.py")
    r = _run(tmp_path)
    assert r.returncode == 3, r.stdout
    assert "COULD NOT RUN" in r.stdout
    assert "handoff_reconcile.py" in r.stdout
    assert "PASS" not in r.stdout


def test_a_second_network_capable_git_subcommand_goes_red(tmp_path):
    """The arm that exists because every git command shares ONE process spawn."""
    src = _rec_src()
    assert src.count('"ls-remote"') == 1
    _tree(tmp_path, reconcile_body=src + '\n_ALSO = ["push"]\n')
    r = _run(tmp_path)
    assert r.returncode == 1, r.stdout
    assert "network-capable git subcommands named as string literals: 2 found, 1 expected" in r.stdout
    assert "target: reconcile" in r.stdout


def test_a_new_git_command_in_the_reconcile_module_goes_red(tmp_path):
    src = _rec_src()
    _tree(tmp_path, reconcile_body=src +
          '\n\ndef _sneak(run_git):\n    return run_git(["status"], timeout=5.0)\n')
    r = _run(tmp_path)
    assert r.returncode == 1, r.stdout
    # 9 is the baseline after `stamp_anchor`'s two calls were added; the number moved with
    # the code and the pin, which is the only way this assertion stays an oracle.
    assert "injected-runner call sites: 10 found, 9 expected" in r.stdout
    assert "target: reconcile" in r.stdout


def test_an_aliasing_import_in_the_reconcile_module_goes_red(tmp_path):
    """The conservation law, re-proved on the target whose EXTRA is 1 rather than 0."""
    src = _rec_src()
    _tree(tmp_path, reconcile_body=src + "\nimport subprocess as sp\n")
    r = _run(tmp_path)
    assert r.returncode == 1, r.stdout
    assert "`subprocess` token appears 4 times but only 3 are accounted for" in r.stdout


def test_a_failure_in_the_second_target_is_actually_PRINTED(tmp_path):
    """The regression this refactor itself introduced, and the reason this test exists.

    The first draft called the per-target checker inside a command substitution,
    which captured its stdout -- so every failure message went into a variable and
    was discarded when the exit fired. The guard rejected the file while emitting
    ZERO bytes. Silence that reads exactly like a pass is the failure mode this
    whole guard was built to prevent, reproduced inside it.
    """
    src = _rec_src()
    _tree(tmp_path, reconcile_body=src + '\n_ALSO = ["fetch"]\n')
    r = _run(tmp_path)
    assert r.returncode != 0
    assert r.stdout.strip(), "the guard failed SILENTLY -- no stdout at all"
    assert "FAIL session-card-no-network" in r.stdout


def test_a_git_call_reached_through_an_alias_goes_red(tmp_path):
    """The runner conservation arm, against the exact evasion that defeated the pin once.

    Real git commands were added to the module while the pinned call-site count stayed put: the
    runner had been bound to a two-letter local name and that name was called, so the literal
    spelling the arm counts never appeared. The card's own alias arm already records half of this
    lesson — "right about renaming the CALL and wrong about renaming the IMPORT" — and this is the
    call half. Written as a test rather than a paragraph because the paragraph was already there
    and did not stop it.
    """
    src = _rec_src()
    _tree(tmp_path, reconcile_body=src + (
        "\n\ndef _sneaky(run_git):\n"
        "    rg = run_git\n"
        "    return rg([\"status\", \"--porcelain\"], timeout=5.0)\n"))
    r = _run(tmp_path)
    assert r.returncode == 1, r.stdout
    assert "`run_git` token appears 29 times but 27 are accounted for" in r.stdout
    assert "ALIAS" in r.stdout



# ---------------------------------------------------------------------------
# The three mutants a review used to DEFEAT this
# guard. All three printed PASS with every pinned number unchanged. They are
# standing rows now, not a transcript, for the reason this file's docstring
# gives: a measurement proves the check could go red on one day and nothing
# about tomorrow.
# ---------------------------------------------------------------------------

def test_os_system_in_the_reconcile_module_goes_red(tmp_path):
    src = _rec_src()
    _tree(tmp_path, reconcile_body=src + (
        '\n\ndef _sneak():\n    return os.system("git fetch origin")\n'))
    r = _run(tmp_path)
    assert r.returncode == 1, r.stdout
    assert "spawns a process through the os module" in r.stdout
    assert "target: reconcile" in r.stdout


def test_os_popen_in_the_card_goes_red(tmp_path):
    card = (REPO / "scripts" / "session_card.py").read_text(encoding="utf-8")
    _tree(tmp_path, body=card + '\n\ndef _sneak():\n    return os.popen("curl http://x")\n')
    r = _run(tmp_path)
    assert r.returncode == 1, r.stdout
    assert "spawns a process through the os module" in r.stdout
    assert "target: card" in r.stdout


def test_a_networking_module_hidden_in_a_comma_import_goes_red(tmp_path):
    """`import os, urllib.request` anchored past the first name and slipped through."""
    src = _rec_src()
    assert "import os\n" in src
    _tree(tmp_path, reconcile_body=src.replace("import os\n", "import os, urllib.request\n", 1))
    r = _run(tmp_path)
    assert r.returncode == 1, r.stdout
    assert "a networking module is imported" in r.stdout


def test_the_os_spawn_arm_does_not_fire_on_os_path_or_os_environ(tmp_path):
    """The control. The module legitimately uses `os.environ` and `os.path`, and an arm that
    reddened on those would be removed within a week — which is how a guard dies."""
    src = _rec_src()
    assert "os.environ" in src and "os.path" in src
    _tree(tmp_path)
    r = _run(tmp_path)
    assert r.returncode == 0, r.stdout
    assert "no os-level spawn" in r.stdout
