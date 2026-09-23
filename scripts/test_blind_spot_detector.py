"""the blind-spot detector: which tests does one traced run NOT fully describe.

**No CJK in this file, deliberately.** This project bans CJK in shipped files outside
`README*` / `CHANGELOG.md` / `GUIDE*`.

The criterion, from the Q1 lock: flag the tests where "what this run read" and "what this test
could read" differ. Five categories, one positive each, and the negative the
rule turns on: a subprocess to a DECLARED script is not flagged.

**Syntax, not text.** The detector walks the AST. A text scan cannot tell a use from a mention
-- an early run was failed by a gate that read the word in a docstring as a use of it --
so two negatives below mention every trigger word without using any of them.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
DETECTOR = REPO / "scripts" / "blind_spots.py"

MAP_HEADER = "test-file\tinput-path\tvia\ttracked\n"
EDGE_HEADER = "generator\treads\twrites\n"

TESTS = {
    "scripts/test_uses_glob.py":
        "from pathlib import Path\n\ndef test_x():\n    list(Path('docs').glob('*.md'))\n",
    "scripts/test_uses_walk.py":
        "import os\n\ndef test_x():\n    list(os.walk('docs'))\n",
    "scripts/test_uses_find.py":
        "import subprocess\n\ndef test_x():\n"
        "    subprocess.run(['find', 'docs', '-name', '*.md'], check=True)\n",
    "scripts/test_uses_env.py":
        "import os\nfrom pathlib import Path\n\ndef test_x():\n"
        "    Path(os.environ.get('PLC_DOC', 'docs/a.md')).read_text()\n",
    # Its subprocess edge comes from the map, below: the script it runs is not in the edges table.
    "scripts/test_runs_undeclared.py":
        "import subprocess\n\ndef test_x():\n"
        "    subprocess.run(['bash', 'scripts/undeclared.sh'], check=True)\n",
    "scripts/test_runs_declared.py":
        "import subprocess\n\ndef test_x():\n"
        "    subprocess.run(['bash', 'scripts/declared.sh'], check=True)\n",
    "scripts/test_inline_shell.py":
        "import subprocess\n\ndef test_x():\n"
        "    subprocess.run(['bash', '-c', 'cat docs/a.md'], check=True)\n",
    "scripts/test_shell_true.py":
        "import subprocess\n\ndef test_x():\n"
        "    subprocess.run('true', shell=True, check=True)\n",
    # Mentions every trigger and uses none: strings, a comment, and the env copy every subprocess
    # test makes.
    "scripts/test_only_mentions.py":
        "import os\n\n# glob rglob os.walk find os.environ.get shell=True bash -c\n"
        "NOTE = 'glob / os.walk / find / os.getenv / shell=True / -c'\n\n"
        "def test_x():\n    env = {**os.environ}\n    env2 = os.environ.copy()\n"
        "    assert NOTE and env is not env2\n",
    "scripts/test_plain.py":
        "from pathlib import Path\n\ndef test_x():\n    Path('docs/a.md').read_text()\n",
}

SCRIPTS = {
    "scripts/undeclared.sh": "#!/bin/bash\ncat docs/a.md\n",
    "scripts/declared.sh": "#!/bin/bash\ncat docs/a.md\n",
    "docs/a.md": "a\n",
}

MAP = MAP_HEADER + (
    "scripts/test_runs_undeclared.py\tscripts/undeclared.sh\tsubprocess\tyes\n"
    "scripts/test_runs_declared.py\tscripts/declared.sh\tsubprocess\tyes\n"
    # A DATA file in argv is an input the trace recorded, not a script that hides reads.
    "scripts/test_plain.py\tdocs/a.md\tsubprocess\tyes\n"
)
EDGES = EDGE_HEADER + "scripts/declared.sh\tdocs/a.md\t-\n"


def run(tmp_path: Path, files: list[str], edges: str = EDGES,
        extra: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    for rel, text in {**TESTS, **SCRIPTS, **(extra or {})}.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    (tmp_path / "map.tsv").write_text(MAP, encoding="utf-8")
    (tmp_path / "edges.tsv").write_text(edges, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(DETECTOR), "--root", str(tmp_path),
         "--map", str(tmp_path / "map.tsv"), "--edges", str(tmp_path / "edges.tsv"), *files],
        capture_output=True, text=True, timeout=60)


def detect(tmp_path: Path, edges: str = EDGES) -> dict[str, set[str]]:
    res = run(tmp_path, sorted(TESTS), edges)
    assert res.returncode == 0, res.stderr
    flags: dict[str, set[str]] = {}
    for line in res.stdout.splitlines():
        test_file, category = line.split("\t")[:2]
        flags.setdefault(test_file, set()).add(category)
    return flags


def test_glob_is_flagged(tmp_path):
    assert "enumerate" in detect(tmp_path).get("scripts/test_uses_glob.py", set())


def test_walk_is_flagged(tmp_path):
    assert "enumerate" in detect(tmp_path).get("scripts/test_uses_walk.py", set())


def test_find_is_flagged(tmp_path):
    assert "find" in detect(tmp_path).get("scripts/test_uses_find.py", set())


def test_an_env_var_path_is_flagged(tmp_path):
    assert "env" in detect(tmp_path).get("scripts/test_uses_env.py", set())


@pytest.mark.parametrize("expr", [
    "os.environ['PLC_DOC']", "os.getenv('PLC_DOC')", "str(Path.home())",
    "os.path.expanduser('~/x')", "os.path.expandvars('$HOME/x')",
])
def test_every_env_form_is_flagged(tmp_path, expr):
    """One positive per form: deleting the `os.environ[...]` branch passed every test above."""
    extra = {"scripts/test_env_form.py":
             "import os\nfrom pathlib import Path\n\ndef test_x():\n    %s\n" % expr}
    res = run(tmp_path, ["scripts/test_env_form.py"], extra=extra)
    assert res.returncode == 0, res.stderr
    assert "\tenv\t" in res.stdout


@pytest.mark.parametrize("expr", ["os.listdir('docs')", "os.scandir('docs')",
                                  "Path('docs').iterdir()", "Path('docs').rglob('*')"])
def test_every_listing_form_is_flagged(tmp_path, expr):
    extra = {"scripts/test_list_form.py":
             "import os\nfrom pathlib import Path\n\ndef test_x():\n    list(%s)\n" % expr}
    res = run(tmp_path, ["scripts/test_list_form.py"], extra=extra)
    assert res.returncode == 0, res.stderr
    assert "\tenumerate\t" in res.stdout


@pytest.mark.parametrize("expr", [
    "list(ast.walk(ast.parse('x')))",            # a syntax-tree walk is not a directory walk
    "os.environ['PATH'] + ':/x'",                # composing a child's PATH names no repo file
    "os.environ.get('PATH', '')",
])
def test_measured_false_positives_are_not_flagged(tmp_path, expr):
    """Both were hits on the real repo: scripts/test_ci_state_snippet.py:52 walks an AST, and five
    test files read PATH only to put a stub directory in front of it."""
    extra = {"scripts/test_fp.py":
             "import ast\nimport os\n\ndef test_x():\n    %s\n" % expr}
    res = run(tmp_path, ["scripts/test_fp.py"], extra=extra)
    assert res.returncode == 0, res.stderr
    assert res.stdout == ""


def test_os_walk_imported_bare_is_still_flagged(tmp_path):
    extra = {"scripts/test_bare_walk.py":
             "from os import walk\n\ndef test_x():\n    list(walk('docs'))\n"}
    res = run(tmp_path, ["scripts/test_bare_walk.py"], extra=extra)
    assert "\tenumerate\t" in res.stdout


@pytest.mark.parametrize("src, category", [
    # Aliases. Every positive above imports unaliased; review found each of these unflagged, and a
    # sibling checker in this repo (p40) had already been defeated by the same class.
    ("import os as o\n\ndef test_x():\n    list(o.walk('docs'))\n", "enumerate"),
    ("from os import walk as w\n\ndef test_x():\n    list(w('docs'))\n", "enumerate"),
    ("from os import environ as E\n\ndef test_x():\n    E['PLC_X']\n", "env"),
    ("from os import environ as E\n\ndef test_x():\n    E.get('PLC_X')\n", "env"),
    ("from os import getenv as g\n\ndef test_x():\n    g('PLC_X')\n", "env"),
    ("from subprocess import run as r\n\ndef test_x():\n    r(['bash', '-c', 'x'])\n",
     "subprocess"),
    ("import glob as G\n\ndef test_x():\n    G.glob('docs/*')\n", "enumerate"),
    # Primitives the first version did not list.
    ("import asyncio\n\ndef test_x():\n    asyncio.create_subprocess_shell('ls')\n", "subprocess"),
    # exec takes argv as separate arguments, not one list -- `-c` is the second of them. A plain
    # `create_subprocess_exec('ls')` is treated like `subprocess.run(['ls'])`: not flagged.
    ("import asyncio\n\ndef test_x():\n    asyncio.create_subprocess_exec('bash', '-c', 'x')\n",
     "subprocess"),
    ("from pathlib import Path\n\ndef test_x():\n    list(Path('docs').walk())\n", "enumerate"),
    ("import os\n\ndef test_x():\n    os.environ.copy()['PLC_X']\n", "env"),
    ("import os\n\ndef test_x():\n    dict(os.environ)['PLC_X']\n", "env"),
    ("import subprocess\n\ndef test_x():\n    sh = 'bash'\n    subprocess.run([sh, '-c', 'x'])\n",
     "subprocess"),
    ("import shutil\n\ndef test_x():\n    shutil.copytree('docs', '/tmp/d')\n", "enumerate"),
    ("import os\n\ndef test_x():\n    os.execv('/bin/sh', ['sh'])\n", "subprocess"),
    ("import pty\n\ndef test_x():\n    pty.spawn('sh')\n", "subprocess"),
])
def test_review_found_under_flags_are_flagged(tmp_path, src, category):
    res = run(tmp_path, ["scripts/test_form.py"], extra={"scripts/test_form.py": src})
    assert res.returncode == 0, res.stderr
    assert f"\t{category}\t" in res.stdout, res.stdout


def test_git_dash_c_is_not_inline_code(tmp_path):
    """`git -c key=value` is a config flag. Only a shell or interpreter before `-c` -- or a name
    the detector cannot see through -- counts as inline code."""
    src = ("import subprocess\n\ndef test_x():\n"
           "    subprocess.run(['git', '-c', 'user.name=t', 'commit'])\n")
    res = run(tmp_path, ["scripts/test_git_c.py"], extra={"scripts/test_git_c.py": src})
    assert res.stdout == ""


@pytest.mark.parametrize("suffix", [".awk", ".jq"])
def test_a_script_without_shebang_or_shell_suffix_is_still_a_script(tmp_path, suffix):
    """`awk -f scripts/x.awk` can `getline < file`; treating it as a data file hid its reads."""
    script = "scripts/hidden" + suffix
    m = MAP_HEADER + "scripts/test_runs_awk.py\t%s\tsubprocess\tyes\n" % script
    for rel, text in {"scripts/test_runs_awk.py": "def test_x():\n    pass\n",
                      script: "{ print }\n"}.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    (tmp_path / "map.tsv").write_text(m, encoding="utf-8")
    (tmp_path / "edges.tsv").write_text(EDGE_HEADER, encoding="utf-8")
    res = subprocess.run(
        [sys.executable, str(DETECTOR), "--root", str(tmp_path), "--map", str(tmp_path / "map.tsv"),
         "--edges", str(tmp_path / "edges.tsv"), "scripts/test_runs_awk.py"],
        capture_output=True, text=True, timeout=60)
    assert f"runs undeclared {script}" in res.stdout


def test_an_unparseable_file_is_flagged_not_skipped(tmp_path):
    res = run(tmp_path, ["scripts/test_broken.py"],
              extra={"scripts/test_broken.py": "def test_x(:\n"})
    assert res.returncode == 0, res.stderr
    assert "\tunparseable\t" in res.stdout


def test_an_undeclared_subprocess_is_flagged(tmp_path):
    assert "subprocess" in detect(tmp_path).get("scripts/test_runs_undeclared.py", set())


def test_a_declared_subprocess_is_not_flagged(tmp_path):
    """The rule's oracle. Positive control in the same run: the undeclared twin,
    identical but for the table, IS flagged."""
    flags = detect(tmp_path)
    assert "scripts/test_runs_undeclared.py" in flags
    assert "scripts/test_runs_declared.py" not in flags


def test_declaring_the_script_is_what_unflags_it(tmp_path):
    flags = detect(tmp_path, edges=EDGES + "scripts/undeclared.sh\tdocs/a.md\t-\n")
    assert "scripts/test_runs_undeclared.py" not in flags


def test_inline_code_and_shell_true_are_flagged(tmp_path):
    """`bash -c '...'` and `shell=True` run code no argv entry names, so the trace records no
    script for them -- an undeclared-script check alone would find nothing to flag."""
    flags = detect(tmp_path)
    assert "subprocess" in flags.get("scripts/test_inline_shell.py", set())
    assert "subprocess" in flags.get("scripts/test_shell_true.py", set())


def test_mentions_are_not_uses(tmp_path):
    flags = detect(tmp_path)
    assert "scripts/test_uses_glob.py" in flags, "positive control"
    assert "scripts/test_only_mentions.py" not in flags
    assert "scripts/test_plain.py" not in flags


def test_every_row_names_where(tmp_path):
    """A flag nobody can locate is a flag nobody can clear: each row carries file:line or the
    undeclared script's path."""
    res = run(tmp_path, ["scripts/test_uses_glob.py", "scripts/test_runs_undeclared.py"])
    rows = [line.split("\t") for line in res.stdout.splitlines()]
    assert ["scripts/test_uses_glob.py", "enumerate", "scripts/test_uses_glob.py:4"] in \
        [r[:3] for r in rows]
    assert any(r[:2] == ["scripts/test_runs_undeclared.py", "subprocess"]
               and "scripts/undeclared.sh" in r[2] for r in rows)
