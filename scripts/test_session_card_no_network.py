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


def _tree(tmp_path: Path, body: str | None = None) -> Path:
    """A minimal work-tree-shaped directory holding a copy of session_card.py.

    Not a git repo: the guard takes the root as its argument, so it never needs
    one. That keeps every case here independent of the real index.
    """
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    dst = tmp_path / "scripts" / "session_card.py"
    if body is None:
        shutil.copyfile(REPO / "scripts" / "session_card.py", dst)
    else:
        dst.write_text(body, encoding="utf-8")
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
