"""A guard for the hand-written generator edges table: rows, the found-in-code rule (found-outside-
comments matching with the asymmetric boundary), the header rule (a writes cell vouched for by a tracked
GENERATED-by header), reporting (collects every violation), and gate registration; exemption
lines and their four red states.

The exemption code is exercised by the fixtures below and nowhere else.

Red rows assert the FAIL reason, not only the exit code: a fixture with a second, unrelated fault
exits 1 just the same, and one of this file's own rows was masked that way once.

No CJK in this file, deliberately. This project bans CJK in shipped files outside
README*/CHANGELOG.md/GUIDE*.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import test_gate_envelope as envelope_tests

REPO = Path(__file__).resolve().parents[1]
INVARIANT = REPO / "scripts" / "invariants" / "generator-edges-declared.sh"
CLOSE_GATE_JSON = REPO / ".claude" / "close-gate.json"
FIXED_PATH = "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"
HEADER = "generator\treads\twrites\n"
INV_REL = "scripts/invariants/generator-edges-declared.sh"


def _bash() -> str:
    b = shutil.which("bash")
    assert b, "bash not found on the test-runner's own PATH"
    return b


def _write(root: Path, rel: str, content: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    # newline="" so a "\r\n" in a fixture reaches disk unchanged.
    with open(p, "w", encoding="utf-8", newline="") as fh:
        fh.write(content)


def make_repo(tmp_path: Path, files: dict[str, str], table: str | None,
              untracked: tuple[str, ...] = (),
              base: dict[str, str] | None = None) -> Path:
    """Write `files` (repo-relative path -> content) plus the edges table (None = no table file
    at all), `git init` the tree, `git add` everything except `untracked`, and copy the REAL
    invariant into the fixture's own scripts/invariants/ so its root derives correctly (the guard
    takes no environment overrides -- it finds its table by deriving the root from its own
    on-disk location, so a fixture must carry a real copy, not point an existing one elsewhere).

    `base` gives the fixture a MERGE-BASE, which a ratchet subject is compared against. The files
    in it are written and committed FIRST, `refs/remotes/origin/main` is pointed at that commit,
    and only then is the working tree written over the top. A plain `update-ref` is enough: the
    guard asks git for a merge-base, and never for a remote. Without `base` the repo has no
    commits at all -- the shape every pre-ratchet fixture already had, and the one a ratchet
    subject must refuse to pass on.
    """
    root = tmp_path
    all_rel: set[str] = set()

    if base is not None:
        for rel, content in base.items():
            _write(root, rel, content)
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "--literal-pathspecs", "add", "--", *sorted(base)],
                       cwd=root, check=True)
        env = {**os.environ,
               "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
        subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=root, check=True, env=env)
        subprocess.run(["git", "update-ref", "refs/remotes/origin/main", "HEAD"],
                       cwd=root, check=True)

    if table is not None:
        _write(root, ".claude/generator-edges.tsv", table)
        all_rel.add(".claude/generator-edges.tsv")

    for rel, content in files.items():
        _write(root, rel, content)
        all_rel.add(rel)

    (root / "scripts" / "invariants").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(INVARIANT, root / INV_REL)
    all_rel.add(INV_REL)

    if base is None:
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    to_add = sorted(all_rel - set(untracked))
    if to_add:
        # --literal-pathspecs: a fixture path like `scripts/[A]AA.sh` must add exactly that file.
        subprocess.run(["git", "--literal-pathspecs", "add", "--", *to_add], cwd=root, check=True)
    return root


def run_invariant(root: Path, extra_env: dict[str, str] | None = None,
                  path_override: str | None = None) -> subprocess.CompletedProcess:
    env = {"PATH": path_override if path_override is not None else FIXED_PATH,
           "HOME": os.environ.get("HOME", "/tmp")}
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [_bash(), str(root / INV_REL)],
        cwd=root, env=env, capture_output=True, text=True, timeout=30)


def fails(res: subprocess.CompletedProcess) -> list[str]:
    return [ln for ln in res.stdout.splitlines() if ln.startswith("FAIL ")]


def only_fail(res: subprocess.CompletedProcess) -> str:
    assert res.returncode == 1, res.stdout + res.stderr
    f = fails(res)
    assert len(f) == 1, res.stdout
    return f[0]


READS_A = "reads cell 'data/a.md' is not named in 'scripts/g.sh' outside comments"


# --- AC8: not applicable / empty / unreadable / no git / not a work tree -------------------------

def test_ac8_no_table_is_not_applicable(tmp_path):
    root = make_repo(tmp_path, {}, table=None)
    res = run_invariant(root)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "not applicable" in res.stdout


def test_ac8_header_only_table_is_zero_rows(tmp_path):
    root = make_repo(tmp_path, {}, table=HEADER)
    res = run_invariant(root)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "ok  generator-edges-declared: 0 rows -- nothing checked" in res.stdout.splitlines()


def test_ac8_unreadable_table_exits_3(tmp_path):
    root = make_repo(tmp_path, {}, table=HEADER)
    table = root / ".claude" / "generator-edges.tsv"
    table.chmod(0o000)
    try:
        res = run_invariant(root)
        assert res.returncode == 3, res.stdout + res.stderr
        assert "not readable" in res.stderr
    finally:
        table.chmod(0o644)


def test_ac8_not_a_git_work_tree_exits_3(tmp_path):
    root = tmp_path
    (root / ".claude").mkdir()
    (root / ".claude" / "generator-edges.tsv").write_text(HEADER, encoding="utf-8")
    (root / "scripts" / "invariants").mkdir(parents=True)
    shutil.copyfile(INVARIANT, root / INV_REL)
    res = run_invariant(root)
    assert res.returncode == 3, res.stdout + res.stderr
    assert "not a git work tree" in res.stderr


def test_ac8_git_not_on_path_exits_3(tmp_path, tmp_path_factory):
    root = make_repo(tmp_path, {"scripts/g.sh": "F=\"data/a.md\"\n"},
                     table=HEADER + "scripts/g.sh\tdata/a.md\t-\n")
    bindir = tmp_path_factory.mktemp("nogit-bin")
    for tool in ("awk", "dirname"):
        real = shutil.which(tool)
        assert real, "%s missing on the test-runner's own PATH" % tool
        (bindir / tool).symlink_to(real)
    res = run_invariant(root, path_override=str(bindir))
    assert res.returncode == 3, res.stdout + res.stderr
    assert "git is not on PATH" in res.stderr


# --- row shape --------------------------------------------------------------------------------

def test_row_with_two_fields_is_red_and_shows_the_whole_row(tmp_path):
    root = make_repo(tmp_path, {"scripts/g.sh": "F=\"data/a.md\"\n"},
                     table=HEADER + "scripts/g.sh\tdata/a.md\n")
    f = only_fail(run_invariant(root))
    assert ":2:" in f and "3 non-empty" in f
    # Both fields reach the message; before the <TAB> rendering it was cut to `scripts/g.sh`.
    assert f.endswith("scripts/g.sh<TAB>data/a.md"), f


def test_row_with_four_fields_is_red(tmp_path):
    root = make_repo(tmp_path, {"scripts/g.sh": "F=\"data/a.md\"\n"},
                     table=HEADER + "scripts/g.sh\tdata/a.md\t-\textra\n")
    f = only_fail(run_invariant(root))
    assert ":2:" in f and "3 non-empty" in f and f.endswith("<TAB>extra"), f


def test_row_with_an_empty_field_is_red(tmp_path):
    root = make_repo(tmp_path, {"scripts/g.sh": "F=\"data/a.md\"\n"},
                     table=HEADER + "scripts/g.sh\t\t-\n")
    f = only_fail(run_invariant(root))
    assert ":2:" in f and "3 non-empty" in f


def test_a_crlf_table_is_read_like_an_lf_table(tmp_path):
    """A `core.autocrlf=true` checkout rewrites every line ending. Without the parse's CR strip,
    the header line reads as a data row and `-\\r` no longer equals `-`."""
    root = make_repo(tmp_path, {"scripts/g.sh": "F=\"data/a.md\"\n"},
                     table="generator\treads\twrites\r\nscripts/g.sh\tdata/a.md\t-\r\n")
    res = run_invariant(root)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "1 rows, 1 path cells checked" in res.stdout


# --- AC5: script cell --------------------------------------------------------------------------

def test_ac5_missing_script_is_red_and_its_cells_are_still_checked(tmp_path):
    """Collect-all includes the cascade: the script line AND the cell that script cannot name."""
    root = make_repo(tmp_path, {}, table=HEADER + "scripts/missing.sh\tdata/a.md\t-\n")
    res = run_invariant(root)
    assert res.returncode == 1, res.stdout + res.stderr
    f = fails(res)
    assert len(f) == 2, res.stdout
    assert "script 'scripts/missing.sh' is missing or not a regular file" in f[0]
    assert "reads cell 'data/a.md' is not named in 'scripts/missing.sh'" in f[1]


def test_ac5_untracked_script_is_red(tmp_path):
    root = make_repo(tmp_path, {"scripts/g.sh": "F=\"data/a.md\"\n"},
                     table=HEADER + "scripts/g.sh\tdata/a.md\t-\n",
                     untracked=("scripts/g.sh",))
    f = only_fail(run_invariant(root))
    assert "script 'scripts/g.sh' is not tracked by git" in f


def test_ac5_a_tracked_directory_is_not_a_regular_file(tmp_path):
    root = make_repo(tmp_path, {"scripts/g.sh/inner.txt": "x\n"},
                     table=HEADER + "scripts/g.sh\tdata/a.md\t-\n")
    res = run_invariant(root)
    assert res.returncode == 1, res.stdout + res.stderr
    f = fails(res)
    assert len(f) == 2, res.stdout
    assert "script 'scripts/g.sh' is missing or not a regular file" in f[0]


def test_ac5_a_glob_shaped_script_name_is_matched_literally(tmp_path):
    """Review measured it: `git ls-files -- 'scripts/[A]AA.sh'` matches the tracked `scripts/AAA.sh`,
    so an UNTRACKED file literally named `scripts/[A]AA.sh` used to pass as tracked."""
    body = "F=\"data/a.md\"\n"
    root = make_repo(tmp_path, {"scripts/AAA.sh": body, "scripts/[A]AA.sh": body},
                     table=HEADER + "scripts/[A]AA.sh\tdata/a.md\t-\n",
                     untracked=("scripts/[A]AA.sh",))
    f = only_fail(run_invariant(root))
    assert "script 'scripts/[A]AA.sh' is not tracked by git" in f


# --- AC2: misspelled reads ----------------------------------------------------------------------

def test_ac2_misspelled_reads_path_is_red_and_names_the_line(tmp_path):
    root = make_repo(tmp_path, {"scripts/g.sh": "F=\"data/a.md\"\n"},
                     table=HEADER + "scripts/g.sh\tdata/a.mdx\t-\n")
    f = only_fail(run_invariant(root))
    assert ".claude/generator-edges.tsv:2:" in f and "reads cell 'data/a.mdx'" in f


# --- AC3: comment-only vs. code -------------------------------------------------------------------

def test_ac3_path_named_only_in_a_comment_is_red(tmp_path):
    root = make_repo(tmp_path, {"scripts/g.sh": "# data/a.md\n"},
                     table=HEADER + "scripts/g.sh\tdata/a.md\t-\n")
    assert READS_A in only_fail(run_invariant(root))


def test_ac3_control_path_also_named_in_code_is_green(tmp_path):
    root = make_repo(tmp_path, {"scripts/g.sh": "# data/a.md\nF=\"data/a.md\"\n"},
                     table=HEADER + "scripts/g.sh\tdata/a.md\t-\n")
    res = run_invariant(root)
    assert res.returncode == 0, res.stdout + res.stderr


def test_ac3_a_hash_after_whitespace_truncates_the_line(tmp_path):
    root = make_repo(tmp_path, {"scripts/g.sh": "echo x # data/a.md\n"},
                     table=HEADER + "scripts/g.sh\tdata/a.md\t-\n")
    assert READS_A in only_fail(run_invariant(root))


def test_ac3_a_hash_after_a_tab_truncates_the_line(tmp_path):
    """The TAB half of "preceded by a space or tab". The row above uses a space, so a mutant that
    dropped the TAB comparison survived it."""
    root = make_repo(tmp_path, {"scripts/g.sh": "echo x\t# data/a.md\n"},
                     table=HEADER + "scripts/g.sh\tdata/a.md\t-\n")
    assert READS_A in only_fail(run_invariant(root))


# --- AC4: the asymmetric boundary, and a byte-literal match -------------------------------------

def test_ac4_bak_suffix_is_red(tmp_path):
    root = make_repo(tmp_path, {"scripts/g.sh": "F=\"docs/a.md.bak\"\n"},
                     table=HEADER + "scripts/g.sh\tdocs/a.md\t-\n")
    assert "reads cell 'docs/a.md'" in only_fail(run_invariant(root))


def test_ac4_longer_prefix_is_red(tmp_path):
    root = make_repo(tmp_path, {"scripts/g.sh": "F=\"olddocs/a.md\"\n"},
                     table=HEADER + "scripts/g.sh\tdocs/a.md\t-\n")
    assert "reads cell 'docs/a.md'" in only_fail(run_invariant(root))


def test_ac4_default_expansion_before_the_path_is_green(tmp_path):
    root = make_repo(tmp_path, {"scripts/g.sh": "ROADMAP=\"${P:-docs/a.md}\"\n"},
                     table=HEADER + "scripts/g.sh\tdocs/a.md\t-\n")
    res = run_invariant(root)
    assert res.returncode == 0, res.stdout + res.stderr


def test_ac4_quoted_assignment_is_green(tmp_path):
    root = make_repo(tmp_path, {"scripts/g.sh": "F=\"docs/a.md\"\n"},
                     table=HEADER + "scripts/g.sh\tdocs/a.md\t-\n")
    res = run_invariant(root)
    assert res.returncode == 0, res.stdout + res.stderr


def test_ac4_a_derived_name_after_a_code_occurrence_stays_green(tmp_path):
    """The plan's `"$F.new"` shape: `backlog-toc.sh` names the path once and then writes `$F.new`."""
    root = make_repo(tmp_path, {"scripts/g.sh": "F=\"docs/a.md\"\nprintf x > \"$F.new\" && mv \"$F.new\" \"$F\"\n"},
                     table=HEADER + "scripts/g.sh\tdocs/a.md\tdocs/a.md\n")
    res = run_invariant(root)
    assert res.returncode == 0, res.stdout + res.stderr


def test_ac4_a_boundary_miss_does_not_stop_the_search_on_that_line(tmp_path):
    """The first occurrence fails the boundary (`.bak`); the second, later on the SAME line, is real."""
    root = make_repo(tmp_path, {"scripts/g.sh": "cp docs/a.md.bak docs/a.md\n"},
                     table=HEADER + "scripts/g.sh\tdocs/a.md\t-\n")
    res = run_invariant(root)
    assert res.returncode == 0, res.stdout + res.stderr


def test_ac4_a_backslash_in_a_path_is_matched_byte_for_byte(tmp_path):
    """`awk -v` would expand `\\t` to a TAB and search for that; the path reaches awk via ENVIRON."""
    root = make_repo(tmp_path, {"scripts/g.sh": "F='data/a\\tb.md'\n"},
                     table=HEADER + "scripts/g.sh\tdata/a\\tb.md\t-\n")
    res = run_invariant(root)
    assert res.returncode == 0, res.stdout + res.stderr


# --- AC6: the header rule for writes cells --------------------------------------------------

TARGET = "out/baseline.tsv"
WRITES_T = "writes cell 'out/baseline.tsv' is not named in 'scripts/g.sh' outside comments"


def _header_repo(tmp_path, header_line: str, target_rel: str = TARGET,
                 untracked_target: bool = False, cell_role: str = "writes",
                 extra: dict[str, str] | None = None):
    # scripts/g.sh always genuinely names data/a.md in code (code-found), so the OTHER cell in the
    # row is never at stake: the writes-role fixtures put the header target in writes (reads is
    # the code-found data/a.md); the reads-role fixture puts the header target in reads (writes is
    # the code-found data/a.md). That isolation matters -- a mutant that lets the header
    # rule vouch for a reads cell too must be caught by THIS row alone going green, not masked by
    # an unrelated writes-cell failure making the row red for the wrong reason.
    files = {"scripts/g.sh": "F=\"data/a.md\"\n", target_rel: header_line, **(extra or {})}
    row = "scripts/g.sh\tdata/a.md\t%s\n" % target_rel if cell_role == "writes" \
        else "scripts/g.sh\t%s\tdata/a.md\n" % target_rel
    untracked = (target_rel,) if untracked_target else ()
    return make_repo(tmp_path, files, table=HEADER + row, untracked=untracked)


def test_ac6_correct_header_on_line_one_is_green(tmp_path):
    root = _header_repo(tmp_path, "# GENERATED by scripts/g.sh -- do not hand-edit.\n")
    res = run_invariant(root)
    assert res.returncode == 0, res.stdout + res.stderr
    assert ", 1 by header," in res.stdout


def test_ac6_header_ending_exactly_at_the_script_name_is_green(tmp_path):
    """The header rule's "or end of line" arm. Every other fixture, and the real table, has text after the name."""
    root = _header_repo(tmp_path, "# GENERATED by scripts/g.sh\n")
    res = run_invariant(root)
    assert res.returncode == 0, res.stdout + res.stderr
    assert ", 1 by header," in res.stdout


def test_ac6_crlf_header_ending_at_the_script_name_is_green(tmp_path):
    """A CRLF checkout must not redden a target nobody touched (review ran it: it did, before the strip)."""
    root = _header_repo(tmp_path, "# GENERATED by scripts/g.sh\r\nrow\r\n")
    res = run_invariant(root)
    assert res.returncode == 0, res.stdout + res.stderr
    assert ", 1 by header," in res.stdout


def test_ac6_correct_header_on_line_two_is_red(tmp_path):
    root = _header_repo(tmp_path, "#\n# GENERATED by scripts/g.sh -- do not hand-edit.\n")
    assert WRITES_T in only_fail(run_invariant(root))


def test_ac6_header_naming_another_script_is_red(tmp_path):
    root = _header_repo(tmp_path, "# GENERATED by scripts/other.sh -- do not hand-edit.\n")
    assert WRITES_T in only_fail(run_invariant(root))


def test_ac6_header_naming_a_longer_script_name_is_red(tmp_path):
    root = _header_repo(tmp_path, "# GENERATED by scripts/g.shx -- do not hand-edit.\n")
    assert WRITES_T in only_fail(run_invariant(root))


def test_ac6_correct_header_on_an_untracked_target_is_red(tmp_path):
    root = _header_repo(tmp_path, "# GENERATED by scripts/g.sh -- do not hand-edit.\n",
                        untracked_target=True)
    assert WRITES_T in only_fail(run_invariant(root))


def test_ac6_a_glob_shaped_untracked_target_is_matched_literally(tmp_path):
    """The target-side twin of the AC5 glob case: an untracked `out/[b]aseline.tsv` beside a
    tracked `out/baseline.tsv` must not borrow the tracked file's index entry."""
    header = "# GENERATED by scripts/g.sh -- do not hand-edit.\n"
    root = _header_repo(tmp_path, header, target_rel="out/[b]aseline.tsv", untracked_target=True,
                        extra={"out/baseline.tsv": header})
    assert "writes cell 'out/[b]aseline.tsv'" in only_fail(run_invariant(root))


def test_ac6_header_rule_does_not_vouch_for_a_reads_cell(tmp_path):
    root = _header_repo(tmp_path, "# GENERATED by scripts/g.sh -- do not hand-edit.\n",
                        cell_role="reads")
    f = only_fail(run_invariant(root))
    assert "reads cell 'out/baseline.tsv' is not named in 'scripts/g.sh' outside comments" in f


# --- no environment override ---------------------------------------------------------------------

def test_no_environment_variable_relocates_the_table_or_root(tmp_path, tmp_path_factory):
    root = make_repo(tmp_path, {"scripts/g.sh": "F=\"data/a.md\"\n"},
                     table=HEADER + "scripts/g.sh\tdata/a.md\t-\n")
    decoy_dir = tmp_path_factory.mktemp("decoy")
    decoy_table = decoy_dir / "broken.tsv"
    decoy_table.write_text(HEADER + "no/such.sh\tdoes/not\texist\n", encoding="utf-8")
    res = run_invariant(root, extra_env={
        "GENERATOR_EDGES": str(decoy_table),
        "GENERATOR_EDGES_ROOT": str(decoy_dir),
        "GENERATOR_EDGES_TABLE": str(decoy_table),
    })
    assert res.returncode == 0, res.stdout + res.stderr
    assert "1 rows, 1 path cells checked" in res.stdout


# --- AC9: every violation is reported, not only the first ------------------------------------------

def test_ac9_two_independent_faults_produce_two_fail_lines(tmp_path):
    """Two faults that do NOT cascade from each other: row 1's misspelled reads cell, row 2's
    writes cell that neither the found-in-code rule nor the header rule vouches for. The cascading shape -- a missing
    script plus its unfound cell -- is `test_ac5_missing_script_is_red_and_its_cells_are_still_checked`."""
    root = make_repo(tmp_path, {
        "scripts/g1.sh": "F=\"data/a.md\"\n",
        "scripts/g2.sh": "F=\"data/b.md\"\n",
    }, table=(HEADER + "scripts/g1.sh\tdata/a.mdx\t-\n"
              "scripts/g2.sh\tdata/b.md\tout/c.tsv\n"))
    res = run_invariant(root)
    assert res.returncode == 1, res.stdout + res.stderr
    f = fails(res)
    assert len(f) == 2, res.stdout
    assert ":2:" in f[0] and "reads cell 'data/a.mdx'" in f[0]
    assert ":3:" in f[1] and "writes cell 'out/c.tsv'" in f[1]


# --- AC7: exemption lines --------------------------------------------------------------------------
#
# `scripts/g.sh` below builds `data/a.md` by concatenation, so the path is used but never named:
# the cell is code-unfound and only an exemption can make it green (see the stated limits of that rule).

CONCAT = {"scripts/g.sh": "D=\"data\"\nF=\"${D}/a.md\"\n"}
NAMED = {"scripts/g.sh": "F=\"data/a.md\"\n"}
ROW_A = "scripts/g.sh\tdata/a.md\t-\n"
EX_A = "#exempt\tscripts/g.sh\tdata/a.md\tbuilt by concatenation\n"


def _ok_counts(res: subprocess.CompletedProcess) -> tuple[str, ...]:
    assert res.returncode == 0, res.stdout + res.stderr
    m = re.search(
        r"ok  generator-edges-declared: (\d+) rows, (\d+) path cells checked, "
        r"(\d+) by header, (\d+) exemptions", res.stdout)
    assert m, res.stdout
    return m.groups()


def test_ac7_a_reasoned_exemption_turns_a_red_reads_cell_green(tmp_path):
    root = make_repo(tmp_path, CONCAT, table=HEADER + ROW_A + EX_A)
    assert _ok_counts(run_invariant(root)) == ("1", "1", "0", "1")


def test_ac7_a_reasoned_exemption_turns_a_red_writes_cell_green(tmp_path):
    root = make_repo(tmp_path, {"scripts/g.sh": "F=\"data/b.md\"\nD=\"out\"\nprintf x > \"${D}/c.tsv\"\n"},
                     table=(HEADER + "scripts/g.sh\tdata/b.md\tout/c.tsv\n"
                            "#exempt\tscripts/g.sh\tout/c.tsv\tbuilt by concatenation\n"))
    assert _ok_counts(run_invariant(root)) == ("1", "2", "0", "1")


# Malformed: each fixture's cell NEEDS an exemption, so a malformed line that was quietly accepted
# would turn the run green, and one quietly skipped as a comment would leave only the cell's FAIL.
# Both are told apart from the right answer: exactly the malformed line AND the unexempted cell.

def _malformed(tmp_path, ex_line: str, why: str):
    root = make_repo(tmp_path, CONCAT, table=HEADER + ROW_A + ex_line)
    res = run_invariant(root)
    assert res.returncode == 1, res.stdout + res.stderr
    f = fails(res)
    assert len(f) == 2, res.stdout
    assert READS_A in f[1], res.stdout
    assert ":3: malformed exemption line" in f[0] and why in f[0], res.stdout


def test_ac7_an_exemption_with_an_empty_reason_is_red(tmp_path):
    _malformed(tmp_path, "#exempt\tscripts/g.sh\tdata/a.md\t\n", "the reason is empty")


def test_ac7_an_exemption_with_a_whitespace_only_reason_is_red(tmp_path):
    _malformed(tmp_path, "#exempt\tscripts/g.sh\tdata/a.md\t   \n", "the reason is empty")


def test_ac7_an_exemption_with_three_fields_is_red(tmp_path):
    _malformed(tmp_path, "#exempt\tscripts/g.sh\tdata/a.md\n", "4 tab-separated fields")


def test_ac7_an_exemption_with_five_fields_is_red(tmp_path):
    """The other side of "exactly 4": a stray trailing TAB. Every row above has too FEW fields, so
    `n != 4` -> `n < 4` survived them all and accepted this line as an exemption."""
    _malformed(tmp_path, "#exempt\tscripts/g.sh\tdata/a.md\tbuilt by concatenation\t\n",
               "4 tab-separated fields")


def test_ac7_an_exemption_keyword_glued_to_the_script_is_red(tmp_path):
    """`#exempt` must be the whole first field: a missing TAB is a typo, not a comment."""
    _malformed(tmp_path, "#exempt scripts/g.sh\tdata/a.md\tbuilt by concatenation\n",
               "4 tab-separated fields")


def test_ac7_an_orphan_exemption_is_red(tmp_path):
    root = make_repo(tmp_path, NAMED,
                     table=HEADER + ROW_A + "#exempt\tscripts/g.sh\tdata/zzz.md\tno such cell\n")
    f = only_fail(run_invariant(root))
    assert ":3: exemption for 'scripts/g.sh' 'data/zzz.md' matches no row" in f, f


def test_ac7_an_exemption_naming_the_path_under_another_script_is_an_orphan(tmp_path):
    """The pair is the key, not the path: `data/a.md` is a cell, but not of `scripts/other.sh`."""
    root = make_repo(tmp_path, NAMED,
                     table=HEADER + ROW_A + "#exempt\tscripts/other.sh\tdata/a.md\twrong script\n")
    f = only_fail(run_invariant(root))
    assert ":3: exemption for 'scripts/other.sh' 'data/a.md' matches no row" in f, f


def test_ac7_an_exemption_for_a_cell_passing_by_rule_is_stale(tmp_path):
    root = make_repo(tmp_path, NAMED, table=HEADER + ROW_A + EX_A)
    f = only_fail(run_invariant(root))
    assert ":3: exemption for 'scripts/g.sh' 'data/a.md' is stale" in f, f


def test_ac7_an_exemption_for_a_cell_passing_by_the_header_is_stale(tmp_path):
    root = _header_repo(tmp_path, "# GENERATED by scripts/g.sh -- do not hand-edit.\n")
    table = root / ".claude" / "generator-edges.tsv"
    with open(table, "a", encoding="utf-8", newline="") as fh:
        fh.write("#exempt\tscripts/g.sh\t%s\tthe header already vouches\n" % TARGET)
    f = only_fail(run_invariant(root))
    assert ":3: exemption for 'scripts/g.sh' '%s' is stale" % TARGET in f, f


# One exemption, two cells naming its pair: one needs it, one passes by the header rule. It is
# needed, so it is not stale -- in either order. Every other fixture gives a pair ONE cell, so a
# plausible `else ex_needed=0` (needed = the LAST cell's state) survived them all;
# the reverse order catches needed = the FIRST cell's state.
SELF_HEADER = {"scripts/g.sh": CONCAT["scripts/g.sh"], "data/a.md": "# GENERATED by scripts/g.sh -- x\n"}


def test_ac7_an_exemption_needed_by_one_cell_is_not_stale_when_a_later_cell_passes(tmp_path):
    root = make_repo(tmp_path, SELF_HEADER, table=HEADER + "scripts/g.sh\tdata/a.md\tdata/a.md\n" + EX_A)
    assert _ok_counts(run_invariant(root)) == ("1", "2", "1", "1")


def test_ac7_an_exemption_needed_by_one_cell_is_not_stale_when_an_earlier_cell_passes(tmp_path):
    root = make_repo(tmp_path, SELF_HEADER,
                     table=HEADER + "scripts/g.sh\t-\tdata/a.md\n" + ROW_A + EX_A)
    assert _ok_counts(run_invariant(root)) == ("2", "2", "1", "1")


def test_ac7_a_duplicate_exemption_is_red(tmp_path):
    """The cell needs its exemption (code-unfound, no header), so neither a stale nor an orphan verdict
    can make this red by accident: duplication is the only fault."""
    root = make_repo(tmp_path, CONCAT, table=HEADER + ROW_A + EX_A + EX_A)
    f = only_fail(run_invariant(root))
    assert ":4: duplicate exemption for 'scripts/g.sh' 'data/a.md' (first at line 3)" in f, f


def test_ac7_a_prose_comment_about_exempting_is_ignored(tmp_path):
    root = make_repo(tmp_path, NAMED, table=HEADER + ROW_A + "# exempt this row if it breaks\n")
    assert _ok_counts(run_invariant(root)) == ("1", "1", "0", "0")


def test_ac7_a_space_after_the_hash_is_not_an_exemption_even_with_tabs(tmp_path):
    """`# exempt<TAB>...` is a comment: it neither exempts the cell nor counts as malformed."""
    root = make_repo(tmp_path, CONCAT,
                     table=HEADER + ROW_A + "# exempt\tscripts/g.sh\tdata/a.md\tlooks like one\n")
    assert READS_A in only_fail(run_invariant(root))


# --- AC13 (half): RETIRED with its subject -------------------------------------------
#
# Both readers this half exercised -- `scripts/select-tests.sh` and `scripts/blind_spots.py` --
# were deleted with the selector. A reader that does not exist cannot accept a table, so the two
# tests and their positive controls went with it instead of being pointed at something else.


# --- AC11: no python3, and the envelope checker scans it ---------------------------------------------

def test_ac11_the_envelope_checker_declares_the_new_invariant():
    """Membership only, parsed by the envelope suite's own reader. The rest of AC11 is already
    proven by `scripts/test_gate_envelope.py`, which reads DECLARED dynamically on every run:
    `test_every_declared_file_gets_its_own_ok_row` (scanned, no python) and
    `test_self_coverage_proves_every_declared_file_was_read` (a planted `python3` in a copy of
    each declared file turns the checker red and names it). The first version of this row re-ran
    the whole checker here -- nearly all of this file's runtime, duplicating those two rows, under a
    timeout it came close to."""
    assert INV_REL in envelope_tests.declared_files()
    assert INV_REL not in envelope_tests.exempt_files()


# --- the content half ---------------------------------------------------------------
#
# Positive controls were run against a real repository.
# They prove the mechanism once. These fixtures are what keeps it
# proven: a hand-run control is evidence about one run, and the lines it exercised would
# otherwise ship with nothing watching them. Each red row asserts the FAIL TEXT, not just exit 1 --
# a fixture with an unrelated fault exits 1 the same way.
#
# The guard's subject list is hard-coded (no environment overrides, by design), so a fixture supplies
# the two declared artifacts and stand-in generators at exactly those paths.

G1_ARTIFACT = ".claude/roadmap-lead-baseline.tsv"
G1_GEN = "scripts/gen-roadmap-lead-baseline.sh"
G2_ARTIFACT = "docs/BACKLOG.md"
G2_GEN = "scripts/backlog-toc.sh"

# A table with no rows: the content half must stand on its own, so these fixtures deliberately give
# the declaration half nothing to say.
EMPTY_TABLE = HEADER


def test_edges_both_subjects_absent_is_not_applicable_and_says_so(tmp_path):
    """An absent subject and a checked subject used to print the same thing -- nothing."""
    root = make_repo(tmp_path, {}, table=EMPTY_TABLE)
    res = run_invariant(root)
    assert res.returncode == 0, res.stdout + res.stderr
    out = res.stdout
    assert "content not applicable -- no .claude/roadmap-lead-baseline.tsv" in out
    assert "content not applicable -- no docs/BACKLOG.md" in out
    assert "content checked 0 of 2 declared subjects (2 not applicable, 0 failed)" in out


# --- [G1], the ratchet half. ------------------------------------------------------------------
#
# THERE WAS A `stdout` MODE HERE, with two rows asserting regenerate-and-compare on [G1], and one
# of them argued for it by name ("red on any difference, not only a shrink"). Review measured that
# this was backwards FOR THIS SUBJECT: `.claude/roadmap-lead-baseline.tsv` deliberately holds OLD
# values, so "byte-identical to a fresh generation" is the sentence "every pin equals today's
# measurement" -- which made `roadmap-lead-length.sh`'s pinned-row branch unfirable while it was green, and, when a
# row really did grow, printed `regenerate it`, re-pinning at the grown length and turning BOTH
# guards green. The rows are replaced rather than deleted quietly, and the argument they carried is
# quoted here rather than dropped, because it is right for [G2] and wrong for [G1]. `stdout` mode
# itself is gone: [G1] was its only subject.

# A stand-in baseline: <key>\t<name-cols>\t<lead-cols>\t<prefix>, the real file's shape.
def _pins(*rows: tuple[str, int, int, str]) -> str:
    head = "# GENERATED by scripts/gen-roadmap-lead-baseline.sh -- do not hand-edit.\n"
    return head + "".join("%s\t%d\t%d\t%s\n" % r for r in rows)


G1_GEN_BODY = "#!/usr/bin/env bash\nprintf 'unused by ratchet mode\\n'\n"


def _ratchet_repo(tmp_path, base_pins: str, now_pins: str, **kw):
    """The generator must exist (an artifact whose generator is gone is a failure in either mode),
    but ratchet mode never runs it -- the comparison is against git, not against a re-run."""
    return make_repo(
        tmp_path,
        {G1_ARTIFACT: now_pins, G1_GEN: G1_GEN_BODY},
        table=EMPTY_TABLE,
        base={G1_ARTIFACT: base_pins, G1_GEN: G1_GEN_BODY},
        **kw)


def test_edges_ratchet_green_when_nothing_grew_and_it_says_how_many_it_compared(tmp_path):
    pins = _pins(("k1", 100, 59, "B7001 a row"), ("k2", 80, 40, "B7002 another"))
    root = _ratchet_repo(tmp_path, pins, pins)
    res = run_invariant(root)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "no pinned value in column 3 exceeds its value at the merge-base" in res.stdout, res.stdout
    # An empty scan and a clean scan are different answers, and
    # collapsing them is a known failure.
    assert "(2 pin(s) compared)" in res.stdout, res.stdout


def test_edges_ratchet_red_when_a_pin_grows(tmp_path):
    root = _ratchet_repo(
        tmp_path,
        _pins(("k1", 100, 59, "B7001 a row")),
        _pins(("k1", 100, 60, "B7001 a row")))
    res = run_invariant(root)
    assert res.returncode == 1, res.stdout + res.stderr
    f = only_fail(res)
    assert "a pinned value GREW" in f, f
    assert "'B7001 a row' went from 59 to 60 display columns in column 3" in f, f


def test_edges_ratchet_green_when_a_pin_shrinks(tmp_path):
    """THE ROW THAT PROVES THIS IS NOT THE OLD CHECK RENAMED. Regenerate-and-compare went red on a
    shrink too -- it could not tell the two directions apart, which is exactly why it disabled the
    ratchet. A ratchet PERMITS this direction: the wall getting smaller is the deliverable."""
    root = _ratchet_repo(
        tmp_path,
        _pins(("k1", 100, 59, "B7001 a row")),
        _pins(("k1", 100, 40, "B7001 a row")))
    res = run_invariant(root)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "(1 pin(s) compared)" in res.stdout, res.stdout


def test_edges_ratchet_allows_a_new_key(tmp_path):
    """A new or renamed row is UNPINNED and must meet the bound outright -- that is
    `roadmap-lead-length.sh`'s job, not this one's. Enforcing it here as well would red a legal
    state and duplicate a rule in a second place."""
    root = _ratchet_repo(
        tmp_path,
        _pins(("k1", 100, 59, "B7001 a row")),
        _pins(("k1", 100, 59, "B7001 a row"), ("k2", 900, 900, "B7002 brand new and huge")))
    res = run_invariant(root)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "(1 pin(s) compared)" in res.stdout, res.stdout


def test_edges_ratchet_allows_a_removed_key(tmp_path):
    root = _ratchet_repo(
        tmp_path,
        _pins(("k1", 100, 59, "B7001 a row"), ("k2", 80, 40, "B7002 another")),
        _pins(("k1", 100, 59, "B7001 a row")))
    res = run_invariant(root)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "(1 pin(s) compared)" in res.stdout, res.stdout


def test_edges_ratchet_says_so_when_it_compared_nothing(tmp_path):
    """Every key renamed at once: legal, and nothing for the ratchet to say. The count is what
    keeps this from reading like a comparison that happened."""
    root = _ratchet_repo(
        tmp_path,
        _pins(("k1", 100, 59, "B7001 a row")),
        _pins(("k9", 100, 59, "B7001 a row")))
    res = run_invariant(root)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "(0 pin(s) compared)" in res.stdout, res.stdout


def test_edges_ratchet_ignores_column_2_and_that_is_deliberate(tmp_path):
    """Only column 3 has a consumer. `roadmap-lead-length.sh`'s ONLY-THE-LEAD-IS-RATCHETED comment records that a name-cell
    ratchet was written first and its mutant SURVIVED, being unreachable by construction: the pin
    is keyed on a digest of the name cell, so changing the name changes the key. Asserted rather
    than left as an absence, so the gap is a decision somebody can find."""
    root = _ratchet_repo(
        tmp_path,
        _pins(("k1", 100, 59, "B7001 a row")),
        _pins(("k1", 999, 59, "B7001 a row")))
    res = run_invariant(root)
    assert res.returncode == 0, res.stdout + res.stderr


def test_edges_ratchet_red_on_a_record_it_cannot_read(tmp_path):
    """A baseline that cannot be parsed cannot be ratcheted, and a silent skip there is the
    vacuous pass this repo forbids."""
    root = _ratchet_repo(
        tmp_path,
        _pins(("k1", 100, 59, "B7001 a row")),
        _pins(("k1", 100, 59, "B7001 a row")) + "k2\t80\tnot-a-number\tB7002\n")
    res = run_invariant(root)
    assert res.returncode == 1, res.stdout + res.stderr
    f = only_fail(res)
    assert "the working tree copy has a record at line 3 with no readable column 3" in f, f


def test_edges_ratchet_without_a_merge_base_cannot_run_and_does_not_pass(tmp_path):
    """No commits, so no merge-base. The subject EXISTS, so silence here would be a guard that any
    repo can switch off by having no default branch. COULD NOT RUN (3) is the honest verdict --
    `longterm-candidates-not-in-diff.sh` makes the same call."""
    root = make_repo(tmp_path, {
        G1_ARTIFACT: _pins(("k1", 100, 59, "B7001 a row")),
        G1_GEN: G1_GEN_BODY,
    }, table=EMPTY_TABLE)
    res = run_invariant(root)
    assert res.returncode == 3, res.stdout + res.stderr
    assert "no merge-base" in res.stderr, res.stderr


def test_edges_ratchet_states_an_artifact_that_is_new_since_the_base(tmp_path):
    """Absent at the base: every pin in it is new, and a new pin is what the ratchet permits. It
    must not be counted as a comparison that happened."""
    root = make_repo(
        tmp_path,
        {G1_ARTIFACT: _pins(("k1", 100, 59, "B7001 a row")), G1_GEN: G1_GEN_BODY},
        table=EMPTY_TABLE,
        base={G1_GEN: G1_GEN_BODY})
    res = run_invariant(root)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "exists at neither the merge-base" in res.stdout, res.stdout
    assert "content checked 0 of 2 declared subjects (2 not applicable, 0 failed)" in res.stdout, res.stdout


def test_edges_self_mode_takes_the_generators_own_check_exit_code(tmp_path):
    root = make_repo(tmp_path, {
        G2_ARTIFACT: "# Backlog\n",
        G2_GEN: "#!/usr/bin/env bash\n[ \"$1\" = --check ] || exit 9\nexit 0\n",
    }, table=EMPTY_TABLE)
    res = run_invariant(root)
    assert res.returncode == 0, res.stdout + res.stderr
    assert f"{G2_ARTIFACT} is what {G2_GEN} --check reports as current" in res.stdout

    # The same fixture with a --check that reports stale.
    (tmp_path / G2_GEN).write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
    red = run_invariant(root)
    assert red.returncode == 1, red.stdout + red.stderr
    assert only_fail(red) == (
        f"FAIL generator-edges-declared: {G2_ARTIFACT} is NOT current:"
        f" '{G2_GEN} --check' exited 1 -- regenerate it: /bin/bash {G2_GEN}")


def test_edges_an_artifact_whose_generator_is_gone_is_red_not_skipped(tmp_path):
    """Absent artifact = not applicable. Artifact present with no generator = the exact state where
    nothing can say whether the file is current, which is the hole this half closes."""
    root = make_repo(tmp_path, {G1_ARTIFACT: "pinned\n"}, table=EMPTY_TABLE)
    res = run_invariant(root)
    assert res.returncode == 1, res.stdout + res.stderr
    assert only_fail(res) == (
        f"FAIL generator-edges-declared: {G1_ARTIFACT} exists but its declared generator"
        f" '{G1_GEN}' does not -- nothing can say whether this file is current")


# `test_edges_a_generator_that_crashes_is_red_and_says_nothing_was_checked` lived here. Its subject
# was `stdout` mode running a generator that exits non-zero; ratchet mode never runs the
# generator, so the behaviour it pinned no longer exists. The SAME QUESTION on the remaining mode
# -- `self` calling every non-zero exit "is NOT current", when `backlog-toc.sh` exits 2..10 for
# "could not run / refused" -- is a known gap and is not covered by any row today. Named
# here rather than left as a silently shrinking test file.


def test_edges_a_missing_table_does_not_imply_the_content_half_passed(tmp_path):
    """The table half's not-applicable path used to be an unconditional exit 0. A pass printed
    before anything looked is a `vacuous pass`."""
    root = make_repo(tmp_path, {G1_ARTIFACT: "pinned\n"}, table=None)
    res = run_invariant(root)
    assert res.returncode == 1, res.stdout + res.stderr
    assert f"'{G1_GEN}' does not" in only_fail(res)
    assert "table half not applicable" in res.stdout

    # Control: the same missing table with nothing for the content half to object to is still a pass,
    # and still says which half was skipped.
    ok_root = make_repo(tmp_path / "clean", {}, table=None)
    ok = run_invariant(ok_root)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "not applicable -- no .claude/generator-edges.tsv" in ok.stdout


# --- the declaration line, and the two non-zero cases `self` used to collapse ---------------------


def test_edges_self_mode_separates_stale_from_could_not_run(tmp_path):
    """`backlog-toc.sh` exits 1 for "differs" and 2..10 for refused / could-not-run. Reporting
    all of them as "is NOT current -- regenerate it" asserts staleness nothing measured AND
    recommends the operation that was just declined. The declared stale code is what tells them
    apart; anything else is could-not-run, and the generator's stderr rides along because it is the
    only text that distinguishes the two."""
    root = make_repo(tmp_path, {
        G2_ARTIFACT: "# Backlog\n",
        G2_GEN: "#!/usr/bin/env bash\nprintf 'refusing: no vocabulary\\n' >&2\nexit 9\n",
    }, table=EMPTY_TABLE)
    res = run_invariant(root)
    assert res.returncode == 1, res.stdout + res.stderr
    f = only_fail(res)
    assert "exited 9, which is not its declared stale code (1)" in f, f
    assert f"nothing checked whether {G2_ARTIFACT} is current" in f, f
    assert "refusing: no vocabulary" in f, f
    # The wrong answer, asserted as absent: it must not claim the file is stale, and it must not
    # tell the reader to run the thing that just refused.
    assert "is NOT current" not in f, f
    assert "regenerate it" not in f, f


def test_edges_self_mode_still_reports_the_declared_stale_code_as_stale(tmp_path):
    """The control for the row above: the ONE code that does mean stale keeps its old message, so
    the fix narrowed the claim rather than removing it."""
    root = make_repo(tmp_path, {
        G2_ARTIFACT: "# Backlog\n",
        G2_GEN: "#!/usr/bin/env bash\nexit 1\n",
    }, table=EMPTY_TABLE)
    res = run_invariant(root)
    assert res.returncode == 1, res.stdout + res.stderr
    assert only_fail(res) == (
        f"FAIL generator-edges-declared: {G2_ARTIFACT} is NOT current:"
        f" '{G2_GEN} --check' exited 1 -- regenerate it: /bin/bash {G2_GEN}")


def test_edges_the_summary_counts_close_and_a_failing_run_does_not_say_ok(tmp_path):
    """The old summary never mentioned failures, so one FAIL read `0 of 2 (1 not applicable)` --
    0+1 != 2, with the missing subject nowhere on the line -- and it carried the `ok ` prefix on a
    failing run."""
    root = make_repo(tmp_path, {G1_ARTIFACT: "pins\n"}, table=EMPTY_TABLE)
    res = run_invariant(root)
    assert res.returncode == 1, res.stdout + res.stderr
    assert "content checked 0 of 2 declared subjects (1 not applicable, 1 failed)" in res.stdout, res.stdout
    summary = [l for l in res.stdout.splitlines() if "content checked" in l]
    assert len(summary) == 1, res.stdout
    # Neither `ok` (the defect) nor `FAIL` (the first fix, which made the countable-violation
    # property untrue). The summary accounts for the violations; it is not one of them.
    assert summary[0].startswith("note "), summary[0]
    assert len(fails(res)) == 1, res.stdout


def test_edges_the_last_line_of_a_failing_no_table_run_is_not_an_ok(tmp_path):
    """The sharper half: on the missing-table path the `ok` about the TABLE half used to be the
    LAST line an rc=1 run printed."""
    root = make_repo(tmp_path, {G1_ARTIFACT: "pins\n"}, table=None)
    res = run_invariant(root)
    assert res.returncode == 1, res.stdout + res.stderr
    last = [l for l in res.stdout.splitlines() if l.strip()][-1]
    assert last.startswith("FAIL "), res.stdout


def _crlf_subject_list(src: str) -> str:
    """Put a CR on every line of the invariant's own CONTENT_SUBJECTS block, which is what a
    `core.autocrlf=true` checkout does to it."""
    out, inside = [], False
    for line in src.splitlines(keepends=True):
        if line.startswith('CONTENT_SUBJECTS="'):
            inside = True
            out.append(line)
            continue
        if inside:
            if line.rstrip("\n") == '"':
                inside = False
                out.append(line)
                continue
            out.append(line.rstrip("\n") + "\r\n")
            continue
        out.append(line)
    return "".join(out)


CRLF_GEN = '#!/usr/bin/env bash\n[ "$1" = --check ] || exit 9\nexit 0\n'


def test_edges_a_crlf_subject_list_does_not_change_any_verdict(tmp_path):
    """This row is BEHAVIOURAL because its first version was not. Under
    `core.autocrlf=true` the subject list arrives with trailing CRs: before the strip, the blank
    first line became `mode=[CR]` and reached the unknown-mode branch (inflating the total), and a
    real row's last field became `1CR`, rejected as a bad stale code. Three wrong answers from one
    byte.

    The first version of this row asserted `src.index(strip) < src.index(cut)` on the invariant's
    SOURCE TEXT, with a docstring claiming a fixture could not reach the behaviour. A review
    measured that wrong twice over: a mutant that kept the literal but made it unreachable left the
    whole suite green, and the fixture already writes its own copy of the invariant -- so the CRs go
    on THAT copy.
    """
    root = make_repo(tmp_path, {G2_ARTIFACT: "# Backlog\n", G2_GEN: CRLF_GEN}, table=EMPTY_TABLE)
    crlf = _crlf_subject_list(INVARIANT.read_text(encoding="utf-8"))
    assert "|--check|1\r\n" in crlf, "the fixture did not actually add a CR to a subject row"
    with open(root / INV_REL, "w", encoding="utf-8", newline="") as fh:
        fh.write(crlf)
    res = run_invariant(root)
    assert res.returncode == 0, res.stdout + res.stderr
    assert f"{G2_ARTIFACT} is what {G2_GEN} --check reports as current" in res.stdout, res.stdout
    # Two subjects declared, one absent -- the CR must not have inflated the total either.
    assert "content checked 1 of 2 declared subjects (1 not applicable, 0 failed)" in res.stdout, res.stdout


def test_edges_the_crlf_control_is_red_without_the_strip(tmp_path):
    """The positive control for the row above: with the strip neutered, the same CRLF fixture goes
    RED on the CR reaching the fields. Without this, a green CRLF row proves nothing about CRs."""
    src = INVARIANT.read_text(encoding="utf-8")
    strip = '    line="${line%$' + chr(39) + chr(92) + 'r' + chr(39) + '}"'
    assert strip in src, "the CR strip line is no longer where this control expects it"
    neutered = src.replace(
        strip, '    if [ "${GEDC_NEVER_TRUE:-0}" = 1 ]; then ' + strip.strip() + '; fi')
    assert neutered != src
    root = make_repo(tmp_path, {G2_ARTIFACT: "# Backlog\n", G2_GEN: CRLF_GEN}, table=EMPTY_TABLE)
    with open(root / INV_REL, "w", encoding="utf-8", newline="") as fh:
        fh.write(_crlf_subject_list(neutered))
    res = run_invariant(root)
    assert res.returncode == 1, res.stdout + res.stderr
    # The CR lands INSIDE the field, so it also splits the FAIL line: `fails()` sees only the text
    # up to it. Assert on that half -- it is the half that proves the CR reached the field at all.
    assert "has mode self but its fifth field is" in "\n".join(fails(res)), res.stdout


def test_edges_a_subject_line_with_four_fields_is_a_malformed_declaration(tmp_path):
    """Not an unknown mode. `${line#*|}` returns the whole remainder when there is no further `|`,
    so a four-field row used to put the mode where the argument goes and be reported as an unknown
    mode -- a message that sends the reader to the wrong field."""
    src = INVARIANT.read_text(encoding="utf-8")
    bad = src.replace("docs/BACKLOG.md|scripts/backlog-toc.sh|self|--check|1",
                      "docs/BACKLOG.md|scripts/backlog-toc.sh|self|--check")
    assert bad != src, "the subject line this row edits is no longer in the invariant"
    root = make_repo(tmp_path, {G2_ARTIFACT: "# Backlog\n",
                                G2_GEN: "#!/usr/bin/env bash\nexit 0\n"}, table=EMPTY_TABLE)
    (root / INV_REL).write_text(bad, encoding="utf-8")
    res = run_invariant(root)
    assert res.returncode == 1, res.stdout + res.stderr
    f = only_fail(res)
    assert "needs five |-separated fields" in f, f
    assert "unknown mode" not in f, f


def test_edges_ratchet_tells_a_missing_path_from_a_git_that_could_not_answer(tmp_path):
    """The same defect shape as the `self` exit-code collapse, in the ratchet code: `git show ... || <benign
    conclusion>` reads a broken repository as "this artifact is new, so every pin in it is allowed"
    -- the most permissive verdict the branch can produce. The existence question is asked with
    `cat-file -e`, whose answer is a fact about the tree, and a `show` that then fails is
    could-not-run.

    **THIS ROW IS SOURCE-TEXT ONLY and its name promises more than it delivers**, stated rather than
    left for a reader to discover. Making `git show` fail on a path `cat-file -e` just confirmed
    needs a repository corrupted between two commands, which no fixture here can arrange. So the row
    pins the ORDER of the two calls and the presence of the `cannot_run`; the behaviour it is named
    after is argued, not measured. Other rows in this file used to be like this and were
    replaced with behavioural versions; this is the one that could not be.
    """
    src = INVARIANT.read_text(encoding="utf-8")
    # The message used to be `src[:0]`, i.e. the empty string: a red row that printed nothing.
    assert 'git cat-file -e "$CONTENT_BASE_REV:$artifact"' in src, (
        "the existence probe is gone from the invariant, so this row is stale")
    i_probe = src.index('git cat-file -e "$CONTENT_BASE_REV:$artifact"')
    i_show = src.index('git show "$CONTENT_BASE_REV:$artifact"')
    assert i_probe < i_show, "the existence probe must precede the read"
    assert "cannot_run \"git could not read" in src, "a failing read must be could-not-run"


# --- the ratchet bound, the base lookup, duplicate keys and the subject loop --------------------


def _ratchet_repo_with_commit(tmp_path, base_pins: str, head_pins: str, now_pins: str):
    """Three distinct values for one key: at the merge-base, at HEAD, and in the working tree.
    `make_repo`'s `base` makes the first commit and points origin/main at it; this adds a SECOND
    commit so HEAD differs from the merge-base, which is the only shape that can exercise the grow-back case."""
    root = make_repo(
        tmp_path,
        {G1_ARTIFACT: head_pins, G1_GEN: G1_GEN_BODY},
        table=EMPTY_TABLE,
        base={G1_ARTIFACT: base_pins, G1_GEN: G1_GEN_BODY})
    env = {**os.environ,
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
    subprocess.run(["git", "commit", "-q", "-am", "branch work"], cwd=root, check=True, env=env)
    (root / G1_ARTIFACT).write_text(now_pins, encoding="utf-8")
    return root


def test_edges_ratchet_catches_a_grow_back_after_a_committed_shrink(tmp_path):
    """A grow-back after a committed shrink, REPRODUCED before a line of the fix was written.

    The first version compared the working tree against the merge-base ONLY, while its header stated
    the claim as "this branch did not launder a pin". Measured: merge-base 100, the branch COMMITS a
    legitimate shrink to 60 -- the deliverable this whole mechanism exists to encourage -- and the
    working tree grows it back to 80. Green, because 80 is under 100, and the wall grew on this
    branch with nothing objecting. Every step of that sequence is the documented workflow.
    """
    root = _ratchet_repo_with_commit(
        tmp_path,
        _pins(("k1", 100, 100, "B7001 a row")),
        _pins(("k1", 100, 60, "B7001 a row")),
        _pins(("k1", 100, 80, "B7001 a row")))
    res = run_invariant(root)
    assert res.returncode == 1, res.stdout + res.stderr
    f = only_fail(res)
    assert "went from 60 to 80 display columns in column 3" in f, f
    # The message must name WHICH committed value the bound came from, or a reader cannot tell this
    # case from a plain merge-base violation.
    assert "measured against HEAD" in f, f


def test_edges_ratchet_still_permits_shrinking_past_a_committed_shrink(tmp_path):
    """The control for the row above, and the one that keeps the grow-back fix from being a length cap:
    60 -> 40 is the direction the ratchet exists to allow, and it must stay GREEN."""
    root = _ratchet_repo_with_commit(
        tmp_path,
        _pins(("k1", 100, 100, "B7001 a row")),
        _pins(("k1", 100, 60, "B7001 a row")),
        _pins(("k1", 100, 40, "B7001 a row")))
    res = run_invariant(root)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "(1 pin(s) compared)" in res.stdout, res.stdout


def test_edges_ratchet_still_catches_a_grow_past_the_merge_base(tmp_path):
    """The other leg. `HEAD:` alone was rejected because a grown pin committed before the check ran
    would pass forever; the bound is the MINIMUM, so a value above the merge-base is still red even
    when HEAD already holds it."""
    grown = _pins(("k1", 100, 200, "B7001 a row"))
    root = _ratchet_repo_with_commit(
        tmp_path, _pins(("k1", 100, 100, "B7001 a row")), grown, grown)
    res = run_invariant(root)
    assert res.returncode == 1, res.stdout + res.stderr
    f = only_fail(res)
    assert "went from 100 to 200 display columns in column 3" in f, f
    assert "measured against the merge-base" in f, f


def test_edges_ratchet_reports_a_duplicate_key(tmp_path):
    """The first version took the LAST occurrence while `roadmap-lead-length.sh`'s reader ends
    its awk with `exit` after the FIRST -- two readers of one file disagreeing, which is this repo's
    encoder-divergence class. Measured on the last-wins version: a base holding the key at 59 then
    200 let a working-tree 80 pass GREEN. Now the first wins AND the duplicate is reported, because
    a second row is either dead weight or a disagreement nobody declared."""
    # THE DUPLICATE IS ON THE BASE SIDE ONLY, and the first version of this row put it on both --
    # so the head side's report satisfied the assertion and a mutant that disabled the base side
    # survived. Same "two copies, one tested" shape as the base-side `printf` mutant below.
    # HEAD carries a LARGER clean value, so the bound can only come from the base side's FIRST
    # occurrence: under last-wins the bound would be 200 and a working tree of 80 would pass.
    root = _ratchet_repo_with_commit(
        tmp_path,
        _pins(("k1", 100, 59, "B7001 a row"), ("k1", 100, 200, "B7001 again")),
        _pins(("k1", 100, 300, "B7001 a row")),
        _pins(("k1", 100, 80, "B7001 a row")))
    res = run_invariant(root)
    assert res.returncode == 1, res.stdout + res.stderr
    joined = "\n".join(fails(res))
    assert "the merge-base copy names the key 'k1' twice" in joined, joined
    # First-wins is asserted by the GROW, not just by the report: against 59 a working tree of 80
    # is a grow, and under last-wins (200) it would not be.
    assert "went from 59 to 80" in joined, joined


def test_edges_ratchet_reports_a_duplicate_key_on_the_head_side_too(tmp_path):
    """The symmetric half. Both committed copies are parsed by the same function, but "the same
    function handles it" is an argument about the code, not a test of it -- and the asymmetry it
    would hide is exactly what the first duplicate-key fix measured."""
    root = _ratchet_repo_with_commit(
        tmp_path,
        _pins(("k1", 100, 300, "B7001 a row")),
        _pins(("k1", 100, 59, "B7001 a row"), ("k1", 100, 200, "B7001 again")),
        _pins(("k1", 100, 80, "B7001 a row")))
    res = run_invariant(root)
    assert res.returncode == 1, res.stdout + res.stderr
    joined = "\n".join(fails(res))
    assert "the HEAD copy names the key 'k1' twice" in joined, joined
    assert "went from 59 to 80" in joined, joined


def test_edges_ratchet_reports_a_malformed_record_on_the_base_side_too(tmp_path):
    """A surviving mutant: replacing the base-side `printf` with a bare `next` left the whole
    suite green. The behaviour was already right; only the assertion was missing, while the header
    claims the property for BOTH copies."""
    bad_base = _pins(("k1", 100, 59, "B7001 a row")) + "k2\t80\tnot-a-number\tB7002\n"
    root = _ratchet_repo_with_commit(
        tmp_path, bad_base, bad_base, _pins(("k1", 100, 59, "B7001 a row")))
    res = run_invariant(root)
    assert res.returncode == 1, res.stdout + res.stderr
    joined = "\n".join(fails(res))
    assert "the merge-base copy has a record at line 3 with no readable column 3" in joined, joined


def test_edges_a_malformed_record_is_reported_in_full_not_just_its_first_field(tmp_path):
    """`ratchet_report` emits the offending record as the last field of a TSV line, and the
    shell reader splits on TAB -- so the record, itself TSV, was cut down to its first field. The
    reader was told `k2`: the one field that was fine. Tabs are now spaces before the record is
    emitted."""
    root = _ratchet_repo(
        tmp_path,
        _pins(("k1", 100, 59, "B7001 a row")),
        _pins(("k1", 100, 59, "B7001 a row")) + "k2\t80\tnot-a-number\tB7002\n")
    res = run_invariant(root)
    assert res.returncode == 1, res.stdout + res.stderr
    f = only_fail(res)
    assert "cannot be ratcheted: k2 80 not-a-number B7002" in f, f


def test_edges_the_default_branch_may_be_anything_not_just_main(tmp_path):
    """A surviving mutant: deleting the `origin/HEAD` leg of the base lookup left the whole
    suite green, because every fixture set only `refs/remotes/origin/main`. This one sets
    `refs/remotes/origin/HEAD` to a branch that is NOT named main, and no origin/main at all -- the
    shape of any adopter whose default branch is `master`, `trunk` or `develop`."""
    pins = _pins(("k1", 100, 59, "B7001 a row"))
    root = make_repo(
        tmp_path,
        {G1_ARTIFACT: pins, G1_GEN: G1_GEN_BODY},
        table=EMPTY_TABLE,
        base={G1_ARTIFACT: pins, G1_GEN: G1_GEN_BODY})
    subprocess.run(["git", "update-ref", "-d", "refs/remotes/origin/main"], cwd=root, check=True)
    subprocess.run(["git", "branch", "-f", "trunk", "HEAD"], cwd=root, check=True)
    subprocess.run(["git", "update-ref", "refs/remotes/origin/trunk", "HEAD"], cwd=root, check=True)
    subprocess.run(["git", "symbolic-ref", "refs/remotes/origin/HEAD",
                    "refs/remotes/origin/trunk"], cwd=root, check=True)
    res = run_invariant(root)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "(1 pin(s) compared)" in res.stdout, res.stdout
    # And the negative control: with NEITHER ref the subject cannot be checked, and that is a
    # could-not-run rather than a pass.
    subprocess.run(["git", "symbolic-ref", "-d", "refs/remotes/origin/HEAD"], cwd=root, check=True)
    subprocess.run(["git", "update-ref", "-d", "refs/remotes/origin/trunk"], cwd=root, check=True)
    blind = run_invariant(root)
    assert blind.returncode == 3, blind.stdout + blind.stderr


def _subjects_reversed(src: str) -> str:
    """Swap the two declared subject rows in a copy of the invariant, so the `self` subject runs
    FIRST. Order is what makes the here-doc defect latent rather than live today, and a fixture that does not
    change it cannot reach the defect: by the time the second subject's generator runs, the
    here-doc it would eat is already exhausted."""
    lines = src.splitlines(keepends=True)
    idx = [i for i, l in enumerate(lines) if l.startswith(".claude/roadmap-lead-baseline.tsv|")
           or l.startswith("docs/BACKLOG.md|")]
    assert len(idx) == 2, f"expected exactly two subject rows, found {len(idx)}"
    a, b = idx
    lines[a], lines[b] = lines[b], lines[a]
    return "".join(lines)


def test_edges_a_generator_that_reads_stdin_cannot_eat_the_subject_list(tmp_path):
    """stdin inside the loop is the here-doc DRIVING the loop, so a `self` generator that
    reads stdin consumed the remaining subjects -- and every summary number still closed, because
    `content_total` is counted by the loop itself. Two halves: `</dev/null` on the call, and an
    expected count written OUTSIDE the loop so a truncated run is visible at all.

    THE SUBJECT ORDER IS REVERSED HERE, and the first version of this row forgot to do that and
    survived the mutant as a result. With the `self` subject second there is nothing left in the
    here-doc for its generator to eat, so the fixture measured nothing while reading green.
    """
    root = make_repo(tmp_path, {
        G2_ARTIFACT: "# Backlog\n",
        # `cat` drains whatever stdin it is given; with the fix it gets /dev/null and exits 0.
        G2_GEN: "#!/usr/bin/env bash\ncat >/dev/null\nexit 0\n",
        G1_ARTIFACT: _pins(("k1", 100, 59, "B7001 a row")),
        G1_GEN: G1_GEN_BODY,
    }, table=EMPTY_TABLE, base={G1_ARTIFACT: _pins(("k1", 100, 59, "B7001 a row")),
                                G1_GEN: G1_GEN_BODY})
    (root / INV_REL).write_text(
        _subjects_reversed(INVARIANT.read_text(encoding="utf-8")), encoding="utf-8")
    res = run_invariant(root)
    assert res.returncode == 0, res.stdout + res.stderr
    # BOTH subjects must have been examined. Before the fix the generator ate the rest of the list.
    assert "content checked 2 of 2 declared subjects (0 not applicable, 0 failed)" in res.stdout, res.stdout


def test_edges_a_truncated_subject_loop_is_a_failure_not_a_tidy_summary(tmp_path):
    """The here-doc defect's other half, reached directly: the expected count is a literal, so a loop that stops
    early is visible. Without it, `1 of 1 declared subjects (0 not applicable, 0 failed)` is what a
    truncated run prints -- four numbers that add up, describing half a check."""
    src = INVARIANT.read_text(encoding="utf-8")
    assert "CONTENT_SUBJECTS_EXPECTED=2" in src, "the declared count is no longer 2"
    bumped = src.replace("CONTENT_SUBJECTS_EXPECTED=2", "CONTENT_SUBJECTS_EXPECTED=3")
    root = make_repo(tmp_path, {}, table=EMPTY_TABLE)
    (root / INV_REL).write_text(bumped, encoding="utf-8")
    res = run_invariant(root)
    assert res.returncode == 1, res.stdout + res.stderr
    assert "examined 2 declared subjects but 3 are declared" in "\n".join(fails(res)), res.stdout
