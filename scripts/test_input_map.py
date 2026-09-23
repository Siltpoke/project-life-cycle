"""the tracer and the map generator, tested on a miniature repo.

**No CJK in this file, deliberately.** This project bans CJK in shipped files outside
`README*` / `CHANGELOG.md` / `GUIDE*`.

**Why a miniature repo and not the real one.** A traced run of the real suite takes about
80 minutes, and AC7 asks for two of them. The fixture below copies the real generator and the
real tracer into a throwaway git repo with the same layout (`scripts/`, `scripts/lib/`,
`.claude/`), so the tracer's own root -- derived from its `__file__` -- IS the fixture, and every
property below is exercised by the shipping code rather than by a re-implementation of it.

**No skip marker for an absent generator.** The neighbouring test files skip when their subject
is missing; here that would turn the red this task starts from into a quiet skip. (That sentence
once named the marker literally, and `skip-baseline-matches` -- a line scanner -- read the mention
as a use and failed the gate.)

**Every comparison carries a positive control.** Two empty maps are byte-identical, and a map
with no rows contains no tracer row and no `self` value -- each of the assertions below would
pass against a generator that recorded nothing. So each one first asserts that the rows the
fixture was built to produce are really there.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
GENERATOR = REPO / "scripts" / "gen-test-input-map.sh"
TRACER = REPO / "scripts" / "lib" / "test_input_tracer.py"

HEADER = "test-file\tinput-path\tvia\ttracked"
VIA_VALUES = {"direct", "subprocess", "generator"}

READS = "scripts/test_fixture_reads.py"
SECOND = "scripts/test_fixture_second.py"
SELF = "scripts/test_fixture_self.py"

# Real files a fixture test reads in-process AND hands to a subprocess. `.git` only at the root; the
# two caches at any depth, because pytest puts its cache in whichever directory it picks as rootdir.
NOISE_FILES = (".git/HEAD", ".mypy_cache/probe.json", "scripts/.mypy_cache/probe.json",
               ".pytest_cache/probe.txt", "scripts/.pytest_cache/probe.txt")

FILES = {
    # Mirrors the real scripts/conftest.py, so `import helper_mod` resolves the same way.
    "scripts/conftest.py": (
        "import sys\nfrom pathlib import Path\n\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parent))\n"),
    "scripts/helper_mod.py": "def value():\n    return 1\n",
    "scripts/tool.sh": "#!/bin/bash\nexit 0\n",
    "data/tracked.txt": "t\n",
    "data/dslash.txt": "d\n",
    # Same basename as the tracer, different path: the self-filter must match the path, not the name.
    "data/test_input_tracer.py": "# not the tracer\n",
    READS: (
        "import subprocess\nfrom pathlib import Path\n\nimport helper_mod\n\n"
        "ROOT = Path(__file__).resolve().parent.parent\n\n\n"
        "def test_reads_a_tracked_and_an_untracked_file():\n"
        "    assert (ROOT / 'data' / 'tracked.txt').read_text() == 't\\n'\n"
        "    assert (ROOT / 'data' / 'untracked.txt').read_text() == 'u\\n'\n"
        "    assert helper_mod.value() == 1\n\n\n"
        "def test_opens_a_path_that_does_not_exist():\n"
        "    try:\n"
        "        open(ROOT / 'data' / 'no-such-file.txt').close()\n"
        "    except FileNotFoundError:\n"
        "        pass\n\n\n"
        # Probe-while-absent, create, read: the shape that pins the ORDER of the tracer's dedup
        # and existence checks. `mkdir -p`-then-read fixtures take it in the real suite.
        "def test_probes_an_absent_path_then_creates_it_and_reads_it():\n"
        "    p = ROOT / 'data' / 'late.txt'\n"
        "    try:\n"
        "        open(p).close()\n"
        "    except FileNotFoundError:\n"
        "        pass\n"
        "    p.write_text('l\\n')\n"
        "    assert open(p).read() == 'l\\n'\n\n\n"
        "def test_shells_out_with_a_path_and_two_tokens_that_are_not_paths():\n"
        "    subprocess.run(['bash', str(ROOT / 'scripts' / 'tool.sh'), '--flag', 'p1'],\n"
        "                   check=True)\n\n\n"
        # What shutil.rmtree does -- and pytest runs it on old tmp dirs at the start of any
        # process that uses tmp_path. The name is relative to a dir fd; the audit event does not
        # carry the fd, so it reads as `<root>/data`, which also exists.
        # An absolute path that is in the repo only after normalisation: a doubled separator
        # ABOVE the root, so the literal string does not start with the root prefix.
        "def test_reads_through_a_path_with_a_doubled_separator():\n"
        "    p = str(ROOT.parent) + '//' + ROOT.name + '/data/dslash.txt'\n"
        "    assert open(p).read() == 'd\\n'\n\n\n"
        "def test_opens_a_directory_relative_to_a_dir_fd(tmp_path):\n"
        "    import os\n"
        "    (tmp_path / 'data').mkdir()\n"
        "    fd = os.open(tmp_path, os.O_RDONLY)\n"
        "    try:\n"
        "        os.close(os.open('data', os.O_RDONLY, dir_fd=fd))\n"
        "    finally:\n"
        "        os.close(fd)\n"),
    # Imports the same helper as READS. Before this design the suite ran many test files in one process,
    # and the second importer of a module never opens it -- so it never appeared in the map.
    SECOND: (
        "import helper_mod\n\n\n"
        "def test_uses_the_shared_helper():\n"
        "    assert helper_mod.value() == 1\n"),
    SELF: (
        "from pathlib import Path\n\n"
        "ROOT = Path(__file__).resolve().parent.parent\n\n\n"
        "def test_reads_the_tracer_source_and_a_tracked_file():\n"
        "    assert (ROOT / 'scripts' / 'lib' / 'test_input_tracer.py').read_text()\n"
        "    assert (ROOT / 'data' / 'test_input_tracer.py').read_text()\n"
        "    assert (ROOT / 'data' / 'tracked.txt').read_text() == 't\\n'\n\n\n"
        # Real files under two of the tracer's noise prefixes. A changed-file set never names a
        # path in either, so a row there can never select anything -- it is only churn in a pin.
        "def test_reads_under_the_noise_prefixes():\n"
        "    import subprocess\n"
        "    for rel in NOISE:\n"
        "        assert (ROOT / rel).read_text()\n"
        "    subprocess.run(['bash', str(ROOT / 'scripts' / 'tool.sh'), *NOISE], check=True)\n"
        "\n\nNOISE = %r\n" % (NOISE_FILES,)),
}


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def build_fixture(root: Path, extra: dict[str, str] | None = None) -> Path:
    """A throwaway repo with the real generator + tracer in the real layout."""
    for rel, text in {**FILES, **(extra or {})}.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    for src, rel in ((GENERATOR, "scripts/gen-test-input-map.sh"),
                     (TRACER, "scripts/lib/test_input_tracer.py")):
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture")
    # Created AFTER the commit, so they exist on disk and are not tracked.
    (root / "data" / "untracked.txt").write_text("u\n", encoding="utf-8")
    for rel in NOISE_FILES:
        if rel != ".git/HEAD":
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text("noise\n", encoding="utf-8")
    return root


def generate(root: Path) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items()
           if k not in ("PLC_TRACE_OUT", "PYTHONPATH")}
    # The generator keeps its work dir on failure, by design. Point it inside the fixture's own tmp
    # tree so a deliberately failing run does not leave one in the system tmp dir per test run --
    # MEASURED: 29 had piled up during the mutant sweeps.
    tmp = root.parent / (root.name + "-tmp")
    tmp.mkdir(exist_ok=True)
    env["TMPDIR"] = str(tmp)
    return subprocess.run(["bash", str(root / "scripts" / "gen-test-input-map.sh")],
                          cwd=root, env=env, capture_output=True, text=True, timeout=300)


def rows(text: str) -> list[tuple[str, ...]]:
    lines = text.splitlines()
    assert lines and lines[0] == HEADER, "first line must be the header, got %r" % lines[:1]
    return [tuple(line.split("\t")) for line in lines[1:]]


@pytest.fixture(scope="module")
def two_runs(tmp_path_factory):
    """Generate twice on one unchanged tree. The first run is on a cold `__pycache__` and the
    second on a warm one -- the case measured as the thing that made maps differ."""
    root = build_fixture(tmp_path_factory.mktemp("repo"))
    out = root / ".claude" / "test-input-map.tsv"
    first = generate(root)
    assert first.returncode == 0, first.stdout + first.stderr
    a = out.read_bytes()
    second = generate(root)
    assert second.returncode == 0, second.stdout + second.stderr
    b = out.read_bytes()
    return a, b


def test_regenerating_on_an_unchanged_tree_is_byte_identical(two_runs):
    a, b = two_runs
    got = rows(a.decode("utf-8"))
    assert (READS, "data/tracked.txt", "direct", "yes") in got, "positive control: map is empty"
    assert a == b


def test_the_tracer_does_not_record_its_own_reads(two_runs):
    got = rows(two_runs[0].decode("utf-8"))
    # Positive control: the fixture file that reads the tracer's source WAS traced.
    assert (SELF, "data/tracked.txt", "direct", "yes") in got
    assert [r for r in got if r[1] == "scripts/lib/test_input_tracer.py"] == []
    # And the filter is the tracer's PATH, not its basename: a same-named file elsewhere is an input.
    assert (SELF, "data/test_input_tracer.py", "direct", "yes") in got


def test_reads_under_the_noise_prefixes_are_not_recorded(two_runs):
    got = rows(two_runs[0].decode("utf-8"))
    assert (SELF, "data/tracked.txt", "direct", "yes") in got, "positive control"
    assert (SELF, "scripts/tool.sh", "subprocess", "yes") in got, "positive control: argv traced"
    noise = [r for r in got
             if r[1] == ".git" or r[1].startswith(".git/")
             or {".mypy_cache", ".pytest_cache"} & set(r[1].split("/"))]
    assert noise == []


def test_an_absolute_path_that_normalises_into_the_repo_is_recorded(two_runs):
    """`_rel` skips normalising absolute paths that do not start with the root, for speed. A doubled
    separator above the root defeats the literal prefix test and still resolves into the repo."""
    got = rows(two_runs[0].decode("utf-8"))
    assert (READS, "data/dslash.txt", "direct", "yes") in got


def test_an_untracked_read_is_marked_untracked_and_no_via_value_is_self(two_runs):
    got = rows(two_runs[0].decode("utf-8"))
    assert (READS, "data/untracked.txt", "direct", "no") in got
    assert (READS, "data/tracked.txt", "direct", "yes") in got
    assert (READS, "scripts/tool.sh", "subprocess", "yes") in got
    # This subset check is what pins "no via value is self": `self` is not in VIA_VALUES.
    vias = {r[2] for r in got}
    assert vias <= VIA_VALUES, vias - VIA_VALUES
    assert {r[3] for r in got} <= {"yes", "no"}


def test_a_path_that_does_not_exist_is_not_recorded(two_runs):
    got = rows(two_runs[0].decode("utf-8"))
    assert (READS, "scripts/tool.sh", "subprocess", "yes") in got, "positive control"
    paths = {r[1] for r in got}
    for absent in ("data/no-such-file.txt", "--flag", "p1"):
        assert absent not in paths, absent


def test_a_path_seen_absent_is_recorded_when_a_later_read_finds_it(two_runs):
    """Pins the ORDER of the two checks in the tracer's `_emit`: dedup first, existence second, and
    the key is added only once the path is PRESENT. Moving `_records.add(key)` above the existence
    check leaves every other test in this file green -- reported by the phase's oracle-lens review,
    which reproduced the silent miss against real files. It matters more than an ordinary ordering
    bug because AC6's completeness guard re-runs THIS tracer to check the map, so both nets are the
    same instrument: a mutated tracer writes a map that its own `--check` then calls complete."""
    got = rows(two_runs[0].decode("utf-8"))
    assert (READS, "data/tracked.txt", "direct", "yes") in got, "positive control: map is empty"
    # The absent probe must still record nothing under its own name ...
    assert "data/no-such-file.txt" not in {r[1] for r in got}, "positive control: absence still wins"
    # ... while the path that was absent on the first open and present on the second IS a row.
    assert (READS, "data/late.txt", "direct", "no") in got


def test_a_directory_open_is_not_recorded_as_an_input(two_runs):
    """MEASURED: this is the prototype's "residual 4%, mechanism UNKNOWN". pytest's cleanup of old
    tmp dirs walks them with `os.open(<name>, dir_fd=...)`, the tracer resolved `<name>` against
    cwd, and the names -- `.git`, `scripts`, `objects`, `03`, from old fixture repos -- depended
    on what earlier runs left behind. Rows that change with leftover tmp dirs make AC7 unreachable
    on the real map, and requiring existence alone cannot catch them: `.git` and `scripts` exist."""
    got = rows(two_runs[0].decode("utf-8"))
    assert (READS, "data/tracked.txt", "direct", "yes") in got, "positive control"
    assert [r for r in got if r[1] == "data"] == []


def test_two_test_files_importing_the_same_module_both_record_it(two_runs):
    got = rows(two_runs[0].decode("utf-8"))
    importers = {r[0] for r in got if r[1] == "scripts/helper_mod.py"}
    assert importers == {READS, SECOND}


@pytest.mark.parametrize("mode, flags, reads", [
    ("r", 0, True), ("rb", 0, True), ("r+", 0, True), ("a+", 0, True),
    ("w", 0, False), ("wb", 0, False), ("w+", 0, False), ("a", 0, False), ("x", 0, False),
    (None, os.O_RDONLY, True), (None, os.O_RDWR, True),
    (None, os.O_WRONLY | os.O_CREAT, False), (None, os.O_RDWR | os.O_TRUNC, False),
    (None, None, True),
])
def test_an_open_counts_as_a_read_exactly_when_it_can_read_existing_content(mode, flags, reads):
    """Write-only opens are dropped from the map, so this classifier is the only thing standing
    between `r+` and a silently missing input. The prototype called `r+` a write -- harmless
    while writes were kept, a silent miss the moment they are dropped."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_b289_tracer_under_test", TRACER)
    tracer = importlib.util.module_from_spec(spec)
    env_before = os.environ.pop("PLC_TRACE_OUT", None)
    try:
        spec.loader.exec_module(tracer)   # unarmed: PLC_TRACE_OUT is not set
    finally:
        if env_before is not None:
            os.environ["PLC_TRACE_OUT"] = env_before
    assert tracer._can_read(mode, flags) is reads


def test_a_failing_run_leaves_the_existing_map_untouched(tmp_path):
    root = build_fixture(tmp_path, extra={
        "scripts/test_fixture_fails.py": "def test_fails():\n    assert False\n"})
    out = root / ".claude" / "test-input-map.tsv"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(b"previous map\n")
    res = generate(root)
    assert res.returncode != 0, res.stdout + res.stderr
    assert "scripts/test_fixture_fails.py" in res.stdout + res.stderr
    assert out.read_bytes() == b"previous map\n"
