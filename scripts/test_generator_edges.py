"""the declared generator edges, and the selector's edge-only path (AC3).

**No CJK in this file, deliberately.** This project bans CJK in shipped files outside
`README*` / `CHANGELOG.md` / `GUIDE*`.

**What AC3 is for.** AC1 says the selector picks `scripts/test_roadmap_lead_length.py` for commit
`deadbeef`. That could be true for an unrelated reason. AC3 removes every other reason: the map
below holds ONE row -- the test reading the pinned baseline -- and no row names
`docs/ROADMAP.md` at all. The only way from the changed file to the test is the declared edge
`gen-roadmap-lead-baseline.sh: docs/ROADMAP.md -> .claude/roadmap-lead-baseline.tsv`.
The control test runs the same input with the edge removed and must select nothing; without it,
AC3 would also pass for a selector that selected the test for some other reason.

**Why the edges are expanded at selection time and not written into the map.** Writing them into
the map would make every new declaration cost a full traced regeneration (90+ minutes), and the
spec expects about 46 of them. The map holds only what a run observed.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SELECT = REPO / "scripts" / "select-tests.sh"
REAL_EDGES = REPO / ".claude" / "generator-edges.tsv"

MAP_HEADER = "test-file\tinput-path\tvia\ttracked\n"
EDGE_HEADER = "generator\treads\twrites\n"
ORACLE = "scripts/test_roadmap_lead_length.py"


def run_select(stdin: str, map_text: str | None, edges_text: str, tmp_path: Path,
               map_path: Path | None = None) -> subprocess.CompletedProcess:
    m = map_path or tmp_path / "map.tsv"
    m.parent.mkdir(parents=True, exist_ok=True)
    if map_text is not None:
        m.write_text(map_text, encoding="utf-8")
    e = tmp_path / "edges.tsv"
    e.write_text(edges_text, encoding="utf-8")
    flags = tmp_path / "no-flags.tsv"
    flags.write_text("", encoding="utf-8")
    # BLIND_SPOT_FLAGS: these fixtures have no test sources for the detector to read, so they
    # hand the selector an empty flag set instead. The detector is tested on its own.
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
           "TEST_INPUT_MAP": str(m), "GENERATOR_EDGES": str(e), "BLIND_SPOT_FLAGS": str(flags),
           "TEST_INPUT_FINGERPRINT": "none"}
    return subprocess.run(["bash", str(SELECT)], input=stdin, env=env, cwd=REPO,
                          capture_output=True, text=True, timeout=60)


def select(changed: list[str], map_text: str, edges_text: str, tmp_path: Path):
    res = run_select("".join(p + "\n" for p in changed), map_text, edges_text, tmp_path)
    assert res.returncode == 0, res.stderr
    return res.stdout.splitlines()


ONE_ROW_MAP = MAP_HEADER + ORACLE + "\t.claude/roadmap-lead-baseline.tsv\tdirect\tyes\n"


def test_the_generator_edge_alone_selects_the_oracle(tmp_path):
    out = select(["docs/ROADMAP.md"], ONE_ROW_MAP, REAL_EDGES.read_text(encoding="utf-8"), tmp_path)
    assert ORACLE in out


def test_without_the_edge_the_same_input_does_not_select_the_oracle_by_lookup(tmp_path):
    """Since the fallback landed an unknown path falls back to FULL (fallback 1), so the control reads: without
    the edge, nothing in the map or the table knows docs/ROADMAP.md, and the selector can only say
    FULL. It never names the oracle as a discriminating selection."""
    assert select(["docs/ROADMAP.md"], ONE_ROW_MAP, EDGE_HEADER, tmp_path) == ["FULL"]


def test_the_real_table_declares_both_required_edges():
    rows = {tuple(line.split("\t")) for line in REAL_EDGES.read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#")}
    assert ("scripts/gen-roadmap-lead-baseline.sh", "docs/ROADMAP.md",
            ".claude/roadmap-lead-baseline.tsv") in rows
    # The same-file loop no surveyed build system models: it reads and writes one path.
    assert ("scripts/backlog-toc.sh", "docs/BACKLOG.md", "docs/BACKLOG.md") in rows
    # Read one level down, through scripts/backlog-closures.sh --states. Missed by the first
    # version of this table; found by review: 4 test files read docs/BACKLOG.md and have no row
    # for the closure log, so a commit touching only the log would not have selected them.
    assert ("scripts/backlog-toc.sh", ".claude/backlog-closures.tsv", "docs/BACKLOG.md") in rows
    # The invariant the oracle test shells out to. Removing these passed every test until the
    # a review, because the oracle then became a permanent member and was selected anyway.
    assert ("scripts/invariants/roadmap-lead-length.sh", "docs/ROADMAP.md", "-") in rows
    assert ("scripts/invariants/roadmap-lead-length.sh", ".claude/roadmap-lead-baseline.tsv",
            "-") in rows


def test_a_same_file_loop_terminates_and_selects_its_readers(tmp_path):
    m = MAP_HEADER + "scripts/test_reads_backlog.py\tdocs/BACKLOG.md\tdirect\tyes\n"
    e = EDGE_HEADER + "scripts/backlog-toc.sh\tdocs/BACKLOG.md\tdocs/BACKLOG.md\n"
    assert select(["docs/BACKLOG.md"], m, e, tmp_path) == ["scripts/test_reads_backlog.py"]


def test_edges_chain(tmp_path):
    """A generated file that is another generator's input. One hop would miss the far reader.
    The second hop is listed FIRST: in table order, a single pass would reach it anyway."""
    m = MAP_HEADER + "scripts/test_far.py\tout/y.txt\tdirect\tyes\n"
    e = (EDGE_HEADER + "scripts/g2.sh\tout/x.txt\tout/y.txt\n"
         + "scripts/g1.sh\tsrc/a.txt\tout/x.txt\n")
    assert select(["src/a.txt"], m, e, tmp_path) == ["scripts/test_far.py"]


def test_a_three_hop_chain_listed_backwards(tmp_path):
    """A closure bounded to two passes passed every test above. The spec expects ~46 edges."""
    m = MAP_HEADER + "scripts/test_far3.py\tout/z.txt\tdirect\tyes\n"
    e = (EDGE_HEADER + "scripts/g3.sh\tout/y.txt\tout/z.txt\n"
         + "scripts/g2.sh\tout/x.txt\tout/y.txt\n" + "scripts/g1.sh\tsrc/a.txt\tout/x.txt\n")
    assert select(["src/a.txt"], m, e, tmp_path) == ["scripts/test_far3.py"]


def test_a_dash_in_writes_is_not_a_path(tmp_path):
    m = MAP_HEADER + "scripts/test_x.py\t-\tdirect\tyes\n"
    e = EDGE_HEADER + "scripts/reader.sh\tdocs/a.md\t-\n"
    assert select(["docs/a.md"], m, e, tmp_path) == []


def test_a_changed_read_selects_the_tests_that_run_the_script(tmp_path):
    """A declared script whose input changed behaves differently, so a test that RUNS it is in
    scope even if it never reads the script's output. This is what gives a declaration with
    `writes = -` (a pure reader, like the invariant test_b247 shells out to) any meaning."""
    m = (MAP_HEADER + "scripts/test_runs_it.py\tscripts/reader.sh\tsubprocess\tyes\n"
         + "scripts/test_unrelated.py\tdocs/b.md\tdirect\tyes\n")
    e = EDGE_HEADER + "scripts/reader.sh\tdocs/a.md\t-\n"
    assert select(["docs/a.md"], m, e, tmp_path) == ["scripts/test_runs_it.py"]


def test_crlf_input_is_read_as_the_same_paths(tmp_path):
    res = run_select("docs/ROADMAP.md\r\n", ONE_ROW_MAP, REAL_EDGES.read_text(encoding="utf-8"),
                     tmp_path)
    assert res.returncode == 0, res.stderr
    assert ORACLE in res.stdout.splitlines()


def test_a_backslash_in_the_map_path_does_not_change_which_file_is_which(tmp_path):
    """awk -v processes escapes (`\\f` is a form feed) and FILENAME does not."""
    odd = tmp_path / "we\\fird" / "map.tsv"
    res = run_select("docs/ROADMAP.md\n", ONE_ROW_MAP, REAL_EDGES.read_text(encoding="utf-8"),
                     tmp_path, map_path=odd)
    assert res.returncode == 0, res.stderr
    assert ORACLE in res.stdout.splitlines()


# Bad inputs used to be exit 2; they are now FULL with the reason on stderr (fallback 4):
# a selector that cannot trust its inputs runs everything rather than stopping CI.

def test_a_malformed_edge_row_falls_back_not_skips(tmp_path):
    e = EDGE_HEADER + "scripts/g.sh\tsrc/in.txt\n"          # the `writes` field is missing
    res = run_select("src/in.txt\n", MAP_HEADER, e, tmp_path)
    assert (res.returncode, res.stdout) == (0, "FULL\n")
    assert "edges" in res.stderr


def test_a_map_without_its_header_falls_back(tmp_path):
    res = run_select("out/w.txt\n", "scripts/test_z.py\tout/w.txt\tdirect\tyes\n", EDGE_HEADER,
                     tmp_path)
    assert (res.returncode, res.stdout) == (0, "FULL\n")
    assert "header" in res.stderr


def test_the_map_and_the_edges_being_one_file_falls_back(tmp_path):
    """Asserts the MESSAGE, not just the outcome: one file can never satisfy both formats, so FULL
    comes out either way -- and the first version of this test passed with the check deleted."""
    same = tmp_path / "edges.tsv"
    res = run_select("x\n", None, EDGE_HEADER, tmp_path, map_path=same)
    assert (res.returncode, res.stdout) == (0, "FULL\n")
    assert "same file" in res.stderr


def test_output_is_sorted_and_unique(tmp_path):
    m = (MAP_HEADER + "scripts/test_b.py\tp.txt\tdirect\tyes\n"
         + "scripts/test_a.py\tp.txt\tdirect\tyes\n" + "scripts/test_a.py\tp.txt\tsubprocess\tyes\n")
    assert select(["p.txt"], m, EDGE_HEADER, tmp_path) == ["scripts/test_a.py", "scripts/test_b.py"]
