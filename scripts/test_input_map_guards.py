"""The two guards: freshness and completeness.

**No CJK in this file, deliberately.** This project bans CJK in shipped files outside
`README*` / `CHANGELOG.md` / `GUIDE*`.

**Why freshness is split in two.** The design borrows "the pin equals what the generator produces today"
from `.claude/roadmap-lead-baseline.tsv`, whose generator runs in seconds. This map's takes 90+
minutes, so no test can re-run it. What replaces it:
  - the generator writes `.claude/test-input-map.fingerprint`: the map's own git blob, and the blob
    of every file whose change could change what a test reads (the tracer, the generator, the
    conftest, every test file, every code file the map lists as an input);
  - the close-gate invariant checks the MAP line only: a hand edit is red (AC5), and it does not
    demand a 90-minute regeneration for every commit that touches code;
  - the selector checks every INPUT line and prints FULL while any of them is stale -- so a
    docs-only change can be selected, and a code change runs everything until someone regenerates.

**Completeness** is `gen-test-input-map.sh --check`: a traced run that writes nothing and fails on
every (test file, path) it saw that the pinned map does not name.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

import test_input_map as t1

REPO = Path(__file__).resolve().parents[1]
INVARIANT = REPO / "scripts" / "invariants" / "test-input-map-fresh.sh"
SELECT = REPO / "scripts" / "select-tests.sh"
DETECTOR = REPO / "scripts" / "blind_spots.py"


def git_blob(path: Path) -> str:
    return subprocess.run(["git", "hash-object", str(path)], capture_output=True, text=True,
                          check=True).stdout.strip()


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    """The miniature repo, generated once, plus the invariant, the selector and the detector."""
    # Two inputs a review found unguarded: a `.mjs` code file (5 real map rows; the first
    # fingerprint filter left it out) and a code path with a space (the selector split on it).
    root = t1.build_fixture(tmp_path_factory.mktemp("guards"), extra={
        "tools/runner.mjs": "export const x = 1;\n",
        "tools/has space.sh": "#!/bin/bash\nexit 0\n",
        "scripts/test_fixture_code.py": (
            "from pathlib import Path\n\nROOT = Path(__file__).resolve().parent.parent\n\n\n"
            "def test_reads_two_code_files():\n"
            "    assert (ROOT / 'tools' / 'runner.mjs').read_text()\n"
            "    assert (ROOT / 'tools' / 'has space.sh').read_text()\n"),
    })
    for src, rel in ((INVARIANT, "scripts/invariants/test-input-map-fresh.sh"),
                     (SELECT, "scripts/select-tests.sh"), (DETECTOR, "scripts/blind_spots.py")):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, root / rel)
    (root / ".claude").mkdir(exist_ok=True)
    (root / ".claude" / "generator-edges.tsv").write_text("generator\treads\twrites\n")
    res = t1.generate(root)
    assert res.returncode == 0, res.stdout + res.stderr
    return root


def invariant(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(root / "scripts/invariants/test-input-map-fresh.sh")],
                          cwd=root, capture_output=True, text=True, timeout=60)


def fingerprint(root: Path) -> list[list[str]]:
    return [line.split(" ", 2) for line in
            (root / ".claude" / "test-input-map.fingerprint").read_text().splitlines()]


# --- the fingerprint the generator writes -------------------------------------------------------

def test_the_generator_writes_a_fingerprint_that_names_the_map_and_its_code_inputs(repo):
    fp = fingerprint(repo)
    assert fp[0] == ["map", git_blob(repo / ".claude" / "test-input-map.tsv")]
    inputs = {path: blob for kind, blob, path in fp[1:]}
    for rel in ("scripts/lib/test_input_tracer.py", "scripts/gen-test-input-map.sh",
                "scripts/conftest.py", "scripts/test_fixture_reads.py", "scripts/helper_mod.py",
                "scripts/tool.sh"):
        assert inputs.get(rel) == git_blob(repo / rel), rel
    assert inputs.get("tools/runner.mjs") == git_blob(repo / "tools" / "runner.mjs")
    assert inputs.get("tools/has space.sh") == git_blob(repo / "tools" / "has space.sh")
    # A data file's CONTENT does not change which files a test opens, so it is not an input here.
    assert "data/tracked.txt" not in inputs
    assert all(kind == "input" for kind, _, _ in fp[1:])


def test_the_generator_and_the_detector_agree_on_what_code_is():
    """Two lists of 'code' suffixes drifted once (the generator missed .mjs). Pin them together."""
    import re
    import blind_spots
    gen = (REPO / "scripts" / "gen-test-input-map.sh").read_text()
    m = re.search(r"CODE_SUFFIXES='([^']*)'", gen)
    assert m, "gen-test-input-map.sh must declare CODE_SUFFIXES='...'"
    assert {"." + s for s in m.group(1).split()} == set(blind_spots.SCRIPT_SUFFIXES)


def test_an_unchanged_code_path_with_a_space_is_not_stale(repo):
    res = select(repo, "data/tracked.txt\n")
    assert res.returncode == 0 and res.stdout != "FULL\n", res.stderr


def test_a_changed_mjs_input_makes_the_map_stale(repo):
    f = repo / "tools" / "runner.mjs"
    good = f.read_bytes()
    try:
        f.write_bytes(good + b"// changed\n")
        res = select(repo, "data/tracked.txt\n")
        assert res.stdout == "FULL\n" and "tools/runner.mjs" in res.stderr
    finally:
        f.write_bytes(good)


# --- AC5: the gate half ---------------------------------------------------------------------------

def test_ac5_the_invariant_is_green_on_a_fresh_map(repo):
    res = invariant(repo)
    assert res.returncode == 0, res.stdout + res.stderr


def test_ac5_a_hand_edited_map_is_red_and_regenerating_makes_it_green(repo):
    m = repo / ".claude" / "test-input-map.tsv"
    good = m.read_bytes()
    try:
        m.write_bytes(good + b"scripts/test_fixture_reads.py\tdata/hand-added.txt\tdirect\tyes\n")
        res = invariant(repo)
        assert res.returncode != 0
        assert "hand" in (res.stdout + res.stderr).lower()
    finally:
        m.write_bytes(good)
    regen = t1.generate(repo)
    assert regen.returncode == 0, regen.stderr
    assert invariant(repo).returncode == 0


def test_ac5_a_map_without_its_fingerprint_is_red(repo):
    fp = repo / ".claude" / "test-input-map.fingerprint"
    saved = fp.read_bytes()
    try:
        fp.unlink()
        res = invariant(repo)
        # The MESSAGE, not the code: with the check deleted, the script crashed reading the missing
        # file under `set -e` -- non-zero anyway, for no reason anyone could act on.
        assert res.returncode != 0
        assert "no .claude/test-input-map.fingerprint" in res.stderr and "regenerate" in res.stderr
    finally:
        fp.write_bytes(saved)


def test_ac5_a_fingerprint_without_its_map_is_red_not_not_applicable(tmp_path):
    (tmp_path / "scripts" / "invariants").mkdir(parents=True)
    shutil.copyfile(INVARIANT, tmp_path / "scripts/invariants/test-input-map-fresh.sh")
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "test-input-map.fingerprint").write_text("map deadbeef\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    res = invariant(tmp_path)
    assert res.returncode != 0
    assert "does not" in res.stderr


def test_ac5_a_repo_without_the_map_is_not_applicable(tmp_path):
    """A check must not fire where the feature was never configured."""
    (tmp_path / "scripts" / "invariants").mkdir(parents=True)
    shutil.copyfile(INVARIANT, tmp_path / "scripts/invariants/test-input-map-fresh.sh")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    res = invariant(tmp_path)
    assert res.returncode == 0, res.stderr
    assert "not applicable" in res.stdout.lower()


def test_the_invariant_is_registered_in_the_real_gate():
    """Registered is not run -- the close-gate output is the proof it ran. This pins registered."""
    cfg = json.loads((REPO / ".claude" / "close-gate.json").read_text())
    assert any(i.get("command", "").endswith("scripts/invariants/test-input-map-fresh.sh")
               for i in cfg["invariants"])


# --- the selector half of freshness ---------------------------------------------------------------

def select(root: Path, stdin: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items()
           if k not in ("TEST_INPUT_MAP", "GENERATOR_EDGES", "BLIND_SPOT_FLAGS")}
    env["SELECT_ROOT"] = str(root)
    return subprocess.run(["bash", str(root / "scripts/select-tests.sh")], input=stdin, env=env,
                          cwd=root, capture_output=True, text=True, timeout=120)


def test_a_long_fingerprint_whose_first_input_is_stale_still_prints_full(repo):
    """A stale FIRST input plus a long fingerprint: the shape that used to exit 141 with an EMPTY
    stdout, which a caller reads as `run no tests` -- the one failure direction the design forbids.

    The cause was `stale="$(paste ... | awk '...; exit')"` under `set -euo pipefail`: awk's early exit
    closed the pipe while paste was still writing, paste died of SIGPIPE, and `set -e` killed the
    script before `full` printed anything. MEASURED on the real repository before the fix: 1 of 3 runs
    exited 141 with no output; at this fixture's size it was 6 of 6. The padding is what makes paste
    still be writing when awk leaves, so it is load-bearing, not decoration -- the same test with a
    short fingerprint passes against the defect.

    Three iterations, because the pre-fix failure was a race and one green run proved nothing."""
    fp = repo / ".claude" / "test-input-map.fingerprint"
    good = fp.read_bytes()
    try:
        head, first, *rest = good.decode().splitlines()
        kind, _blob, path = first.split(" ", 2)
        stale_line = "%s %s %s" % (kind, "0" * 40, path)
        pad = ["input %s %s" % (git_blob(repo / "scripts" / "conftest.py"), "scripts/conftest.py")] * 4000
        fp.write_text("\n".join([head, stale_line, *rest, *pad]) + "\n", encoding="utf-8")
        for i in range(3):
            res = select(repo, "data/tracked.txt\n")
            assert res.returncode == 0, "run %d exited %d, stdout %r" % (i, res.returncode, res.stdout)
            assert res.stdout == "FULL\n", "run %d printed %r" % (i, res.stdout)
            assert path in res.stderr, "run %d stderr %r" % (i, res.stderr)
    finally:
        fp.write_bytes(good)
    after = select(repo, "data/tracked.txt\n")
    assert after.returncode == 0 and after.stdout != "FULL\n", "control: restored fingerprint"


def test_a_code_input_changing_makes_the_selector_print_full(repo):
    helper = repo / "scripts" / "helper_mod.py"
    good = helper.read_bytes()
    before = select(repo, "data/tracked.txt\n")
    assert before.returncode == 0 and before.stdout != "FULL\n", before.stderr   # control
    try:
        helper.write_bytes(good + b"# changed\n")
        after = select(repo, "data/tracked.txt\n")
        assert after.stdout == "FULL\n"
        assert "stale" in after.stderr and "scripts/helper_mod.py" in after.stderr
    finally:
        helper.write_bytes(good)


def test_a_data_file_changing_does_not(repo):
    data = repo / "data" / "tracked.txt"
    good = data.read_bytes()
    try:
        data.write_bytes(b"different\n")
        res = select(repo, "data/tracked.txt\n")
        assert res.returncode == 0 and res.stdout != "FULL\n", res.stderr
    finally:
        data.write_bytes(good)


# --- AC6: completeness ----------------------------------------------------------------------------

def check(root: Path) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in ("PLC_TRACE_OUT", "PYTHONPATH")}
    env["TMPDIR"] = str(root.parent)
    return subprocess.run(["bash", str(root / "scripts/gen-test-input-map.sh"), "--check"],
                          cwd=root, env=env, capture_output=True, text=True, timeout=300)


def test_ac6_check_is_green_when_the_map_is_complete(repo):
    res = check(repo)
    assert res.returncode == 0, res.stdout + res.stderr


def test_ac6_a_planted_read_the_map_lacks_is_red_and_the_map_is_untouched(repo):
    """A real read, planted, not hypothesised. `--check` must name it and must not write."""
    test_file = repo / "scripts" / "test_fixture_second.py"
    planted = repo / "data" / "planted.txt"
    good = test_file.read_bytes()
    map_before = (repo / ".claude" / "test-input-map.tsv").read_bytes()
    try:
        planted.write_text("p\n", encoding="utf-8")
        test_file.write_bytes(good + b"\n\ndef test_planted():\n"
                              b"    import pathlib\n"
                              b"    pathlib.Path(__file__).resolve().parent.parent.joinpath("
                              b"'data', 'planted.txt').read_text()\n")
        res = check(repo)
        assert res.returncode != 0
        assert "scripts/test_fixture_second.py\tdata/planted.txt" in res.stdout + res.stderr
        assert (repo / ".claude" / "test-input-map.tsv").read_bytes() == map_before
    finally:
        test_file.write_bytes(good)
        planted.unlink(missing_ok=True)
