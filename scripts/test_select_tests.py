"""the selector: the oracle (AC1/AC2), the fallbacks (AC4), AC9, AC10.

**No CJK in this file, deliberately.** This project bans CJK in shipped files outside
`README*` / `CHANGELOG.md` / `GUIDE*`.

**The rule this file pins:** a flagged test, and a test that reads an untracked path or a
directory, is a PERMANENT MEMBER of every selected set -- not a `FULL` trigger. So the design's five
fallbacks are four `FULL` triggers plus one membership rule, and the tests below say which.

AC1, AC2 and AC10 run the SHIPPED selector on the SHIPPED map, table and detector: no fixture, no
override. The rest build the condition they assert on.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SELECT = REPO / "scripts" / "select-tests.sh"
REAL_MAP = REPO / ".claude" / "test-input-map.tsv"
ORACLE = "scripts/test_roadmap_lead_length.py"
# The files one real commit changed. Listed here because CI checks out shallow and the commit
# may be absent; when it is present, the test below checks this list against git itself.
ORACLE_CHANGED = [".claude/roadmap-row-edits.txt", "docs/ROADMAP.md", "docs/qa-log.d/reconcile.log"]

MAP_HEADER = "test-file\tinput-path\tvia\ttracked\n"
EDGE_HEADER = "generator\treads\twrites\n"
PATH_ENV = "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"


def real(stdin: str, *args: str) -> subprocess.CompletedProcess:
    """The shipped selector on the shipped map, table and detector -- with the STALENESS check
    skipped. Any commit touching code makes the pinned map stale and the selector print FULL
    until someone regenerates it; these tests are about lookup and membership, and would otherwise
    go red on every unrelated code commit. Staleness has its own tests in test_input_map_guards.py."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("TEST_INPUT_MAP", "GENERATOR_EDGES", "BLIND_SPOT_FLAGS", "SELECT_ROOT")}
    env["TEST_INPUT_FINGERPRINT"] = "none"
    return subprocess.run(["bash", str(SELECT), *args], input=stdin, env=env, cwd=REPO,
                          capture_output=True, text=True, timeout=120)


def fixture(tmp_path: Path, stdin: str, map_text: str, edges: str = EDGE_HEADER,
            flags: str = "", args: tuple[str, ...] = (), root: Path | None = None,
            run_detector: bool = False) -> subprocess.CompletedProcess:
    """`root` is where git runs and the detector reads sources; `run_detector` runs the real
    detector there instead of handing the selector `flags`. A root without the map's test files
    makes the detector fail -- which is FULL, correctly -- so the two are separate switches."""
    (tmp_path / "map.tsv").write_text(map_text, encoding="utf-8")
    (tmp_path / "edges.tsv").write_text(edges, encoding="utf-8")
    (tmp_path / "flags.tsv").write_text(flags, encoding="utf-8")
    env = {"PATH": os.environ.get("PATH", PATH_ENV), "TEST_INPUT_MAP": str(tmp_path / "map.tsv"),
           "GENERATOR_EDGES": str(tmp_path / "edges.tsv"), "TEST_INPUT_FINGERPRINT": "none"}
    if not run_detector:
        env["BLIND_SPOT_FLAGS"] = str(tmp_path / "flags.tsv")
    if root is not None:
        env["SELECT_ROOT"] = str(root)
    return subprocess.run(["bash", str(SELECT), *args], input=stdin, env=env, cwd=REPO,
                          capture_output=True, text=True, timeout=120)


def lines(res: subprocess.CompletedProcess) -> list[str]:
    assert res.returncode == 0, res.stderr
    return res.stdout.splitlines()


# --- AC1 + AC2: the oracle, on the shipped artifacts ------------------------------------------

def test_the_oracle_changed_list_matches_git_when_the_commit_is_present():
    if subprocess.run(["git", "-C", str(REPO), "cat-file", "-e", "deadbeef^{commit}"],
                      capture_output=True).returncode != 0:
        pytest.skip("deadbeef not in this checkout (shallow clone); the list is pinned above")
    got = subprocess.run(["git", "-C", str(REPO), "diff-tree", "--no-commit-id", "--name-only",
                          "-r", "deadbeef"], capture_output=True, text=True, check=True).stdout
    assert sorted(got.split()) == sorted(ORACLE_CHANGED)


def test_ac1_the_oracle_is_selected():
    assert ORACLE in lines(real("".join(p + "\n" for p in ORACLE_CHANGED)))


def test_ac1_is_decided_by_lookup_not_by_membership():
    """Found in review: with the two declarations removed, the oracle test is flagged, becomes
    a permanent member, and AC1 still passes -- for the reason AC3 exists to rule out. Pin that it
    is NOT a permanent member, so 'selected' above means 'the map and the edges found it'."""
    assert ORACLE not in lines(real(""))


def test_ac2_and_it_is_not_everything():
    out = lines(real("".join(p + "\n" for p in ORACLE_CHANGED)))
    total = len({row.split("\t", 1)[0] for row in REAL_MAP.read_text().splitlines()[1:]})
    assert out != ["FULL"]
    assert len(out) < total, f"{len(out)} of {total}"


# --- AC10: permanent membership, both directions, real files ----------------------------------

AC10_POSITIVE = "scripts/test_close_gate_local.py"   # measured: 32 untracked reads, all real
# Reads only itself and scripts/conftest.py; not flagged; no untracked row. Picked from the map.
AC10_NEGATIVE = "scripts/test_cjk_exemption_scope.py"


def test_ac10_an_untracked_reader_is_selected_for_an_empty_change():
    assert AC10_POSITIVE in lines(real(""))


def test_ac10_a_tracked_only_reader_is_not():
    assert AC10_NEGATIVE not in lines(real(""))
    assert AC10_NEGATIVE not in lines(real("docs/ROADMAP.md\n"))
    # Positive control: it IS selected when something it reads changes.
    assert AC10_NEGATIVE in lines(real(AC10_NEGATIVE + "\n"))


# --- AC4: the fallbacks, one test each ---------------------------------------------------------

BASE_MAP = MAP_HEADER + ("scripts/test_a.py\tp.txt\tdirect\tyes\n"
                         "scripts/test_b.py\tq.txt\tdirect\tyes\n")


def test_fallback_1_an_unknown_path_is_full(tmp_path):
    res = fixture(tmp_path, "nobody/reads/this.txt\n", BASE_MAP)
    assert lines(res) == ["FULL"]
    assert "nobody/reads/this.txt" in res.stderr
    assert lines(fixture(tmp_path, "p.txt\n", BASE_MAP)) == ["scripts/test_a.py"], "control"


def test_fallback_2_is_membership_not_full_since_c8(tmp_path):
    """A flagged test, and a test with an untracked (or directory) row, ride along on every run."""
    m = BASE_MAP + "scripts/test_u.py\t.claude/local.txt\tdirect\tno\n"
    out = lines(fixture(tmp_path, "p.txt\n", m, flags="scripts/test_b.py\tenumerate\tx:1\n"))
    assert out == ["scripts/test_a.py", "scripts/test_b.py", "scripts/test_u.py"]


@pytest.mark.parametrize("changed", [
    "scripts/lib/anything.sh", "scripts/lib/test_input_tracer.py", "scripts/gen-test-input-map.sh",
    "scripts/select-tests.sh", "scripts/blind_spots.py", ".claude/generator-edges.tsv",
    ".claude/test-input-map.tsv", ".claude/test-input-map.fingerprint", "scripts/g.sh",
])
def test_fallback_3_the_machinery_changing_is_full(tmp_path, changed):
    """`scripts/g.sh` is a generator only because the fixture table declares it."""
    edges = EDGE_HEADER + "scripts/g.sh\tp.txt\tq.txt\n"
    # The map row keeps fallback 1 from firing instead: the path is known, and still FULL.
    m = BASE_MAP + "scripts/test_c.py\t%s\tdirect\tyes\n" % changed
    res = fixture(tmp_path, changed + "\n", m, edges)
    assert lines(res) == ["FULL"]
    assert "machinery" in res.stderr


def test_fallback_4_a_missing_map_is_full(tmp_path):
    res = fixture(tmp_path, "p.txt\n", BASE_MAP)
    (tmp_path / "map.tsv").unlink()
    env = {"PATH": os.environ.get("PATH", PATH_ENV), "TEST_INPUT_MAP": str(tmp_path / "map.tsv"),
           "GENERATOR_EDGES": str(tmp_path / "edges.tsv"),
           "BLIND_SPOT_FLAGS": str(tmp_path / "flags.tsv"), "TEST_INPUT_FINGERPRINT": "none"}
    res = subprocess.run(["bash", str(SELECT)], input="p.txt\n", env=env, cwd=REPO,
                         capture_output=True, text=True, timeout=60)
    assert lines(res) == ["FULL"]


def _git(d: Path, *a: str) -> str:
    return subprocess.run(["git", "-C", str(d), *a], check=True, capture_output=True,
                          text=True).stdout.strip()


@pytest.fixture
def upstream(tmp_path):
    u = tmp_path / "up"
    u.mkdir()
    _git(u, "init", "-q", "-b", "main")
    _git(u, "config", "user.email", "t@example.invalid")
    _git(u, "config", "user.name", "t")
    for i, name in enumerate(["p.txt", "q.txt"]):
        (u / name).write_text(str(i), encoding="utf-8")
        _git(u, "add", name)
        _git(u, "commit", "-q", "-m", name)
    return u


def test_fallback_5_a_shallow_checkout_is_full(tmp_path, upstream):
    shallow = tmp_path / "shallow"
    subprocess.run(["git", "clone", "-q", "--depth", "1", f"file://{upstream}", str(shallow)],
                   check=True, capture_output=True)
    res = fixture(tmp_path, "", BASE_MAP, args=("--base", "HEAD~1"), root=shallow)
    assert lines(res) == ["FULL"]
    assert "shallow" in res.stderr


def test_fallback_5_an_unresolvable_merge_base_is_full(tmp_path, upstream):
    """Asserts the reason: with the check deleted, `git diff ""` fails next and FULL comes out
    anyway -- a mutant that passed the first version of this test."""
    res = fixture(tmp_path, "", BASE_MAP, args=("--base", "no-such-ref"), root=upstream)
    assert lines(res) == ["FULL"]
    assert "merge-base" in res.stderr


def test_base_mode_reports_both_sides_of_a_rename(tmp_path, upstream):
    """git detects renames by default and `--name-only` then prints only the NEW path; a test that
    read the old one was silently dropped (a review, reproduced). Non-ASCII names ride along:
    git quotes them unless core.quotePath is off, and a quoted name matches no map row."""
    _git(upstream, "mv", "p.txt", "r.txt")
    (upstream / "café.txt").write_text("c", encoding="utf-8")
    _git(upstream, "add", "-A")
    _git(upstream, "commit", "-q", "-m", "rename")
    m = BASE_MAP + ("scripts/test_r.py\tr.txt\tdirect\tyes\n"
                    "scripts/test_c.py\tcafé.txt\tdirect\tyes\n")
    res = fixture(tmp_path, "", m, args=("--base", "HEAD~1"), root=upstream)
    assert lines(res) == ["scripts/test_a.py", "scripts/test_c.py", "scripts/test_r.py"]


def test_a_declared_output_nobody_reads_is_unknown(tmp_path):
    """A generator's write-target with no map reader was 'known' and selected nothing, silently
    (a review). Known now means: some map row reads it, or some declared script reads it."""
    edges = EDGE_HEADER + "scripts/g.sh\tp.txt\tout/nobody.txt\n"
    assert lines(fixture(tmp_path, "out/nobody.txt\n", BASE_MAP, edges)) == ["FULL"]


def test_a_malformed_flags_file_is_full(tmp_path):
    res = fixture(tmp_path, "p.txt\n", BASE_MAP, flags="not a flag row\n")
    assert lines(res) == ["FULL"]
    assert "flags" in res.stderr


def test_fallback_4_a_failing_detector_is_full(tmp_path, upstream):
    """The map names test files the tree does not have, so the detector cannot read them. This is
    the rule that made this file's own base-mode test print FULL before the fixture was fixed --
    it fired, and no test watched it."""
    res = fixture(tmp_path, "p.txt\n", BASE_MAP, root=upstream, run_detector=True)
    assert lines(res) == ["FULL"]
    assert "detector" in res.stderr


def test_base_mode_selects_from_the_diff_when_it_can(tmp_path, upstream):
    """Positive control for the two above: a full clone and a real base give a real set."""
    res = fixture(tmp_path, "", BASE_MAP, args=("--base", "HEAD~1"), root=upstream)
    assert lines(res) == ["scripts/test_b.py"]


# --- AC9: undeclared subprocess = always selected; declared = selected by its inputs ------------

def _ac9_root(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    files = {
        "scripts/test_runs_tool.py":
            "import subprocess\n\ndef test_x():\n    subprocess.run(['bash', 'scripts/tool.sh'])\n",
        "scripts/test_other.py": "def test_x():\n    open('q.txt').read()\n",
        "scripts/tool.sh": "#!/bin/bash\ncat docs/a.md\n",
        "docs/a.md": "a\n", "q.txt": "q\n",
    }
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return root


AC9_MAP = MAP_HEADER + ("scripts/test_runs_tool.py\tscripts/tool.sh\tsubprocess\tyes\n"
                        "scripts/test_other.py\tq.txt\tdirect\tyes\n")


def test_ac9_undeclared_the_test_is_selected_for_an_unrelated_change(tmp_path):
    root = _ac9_root(tmp_path)
    out = lines(fixture(tmp_path, "q.txt\n", AC9_MAP, root=root, run_detector=True))
    assert out == ["scripts/test_other.py", "scripts/test_runs_tool.py"]


def test_ac9_declared_the_same_test_is_selected_only_when_its_input_changes(tmp_path):
    root = _ac9_root(tmp_path)
    edges = EDGE_HEADER + "scripts/tool.sh\tdocs/a.md\t-\n"
    assert lines(fixture(tmp_path, "q.txt\n", AC9_MAP, edges, root=root, run_detector=True)) == \
        ["scripts/test_other.py"]
    assert lines(fixture(tmp_path, "docs/a.md\n", AC9_MAP, edges, root=root, run_detector=True)) == \
        ["scripts/test_runs_tool.py"]
