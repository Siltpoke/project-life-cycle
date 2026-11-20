"""AC suite the Behavior Lock parser (scripts/behavior-lock.sh).

Closes: (registry file + BL-<n> schema: id / class / behavior / carrier / why) and
the carrier-resolution primitive the carrier-resolution primitive rests on.

**No CJK in this file, deliberately.** This project bans CJK in shipped files outside
README* / CHANGELOG.md / GUIDE*.

Tests assert POSITIVE counts, not only exit codes: a parser that skipped every line would
exit 0 on a good file, which is byte-identical to a correct pass over an empty file. Each
positive case therefore checks the row count the parser reports.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "behavior-lock.sh"

HEADER = "# id\tclass\tbehavior\tcarrier\twhy\n"


def run(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["/bin/bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=REPO,
        input=stdin,
    )


def row(id_="BL-1", cls="PRESERVE", beh="the gate exits non-zero on a missing artifact",
        car="scripts/test_behavior_lock.py::run", why="keystone of the close gate") -> str:
    return "\t".join([id_, cls, beh, car, why])


def write(tmp_path: Path, *rows: str) -> Path:
    p = tmp_path / "behavior-lock.tsv"
    p.write_text(HEADER + "".join(r + "\n" for r in rows), encoding="utf-8")
    return p


# --- check-line: grammar -------------------------------------------------------------------

def test_check_line_accepts_wellformed():
    assert run("--check-line", stdin=row()).returncode == 0


def test_check_line_rejects_backlog_b_id():
    # A plain tracker-style id is a backlog id, not a behavior id -- the namespaces are separate.
    r = run("--check-line", stdin=row(id_="X407"))
    assert r.returncode == 1
    assert "bad id shape" in r.stderr


def test_check_line_rejects_bad_class():
    r = run("--check-line", stdin=row(cls="KEEP"))
    assert r.returncode == 1
    assert "bad class" in r.stderr


def test_check_line_rejects_empty_behavior():
    r = run("--check-line", stdin=row(beh=""))
    assert r.returncode == 1
    assert "empty behavior" in r.stderr


def test_check_line_rejects_dash_carrier():
    # A behavior with no bound test is exactly what this feature exists to forbid.
    r = run("--check-line", stdin=row(car="-"))
    assert r.returncode == 1
    assert "empty carrier" in r.stderr


def test_check_line_rejects_empty_why():
    r = run("--check-line", stdin=row(why=""))
    assert r.returncode == 1
    assert "empty why" in r.stderr


def test_check_line_rejects_wrong_column_count():
    r = run("--check-line", stdin="BL-1\tPRESERVE\tonly three columns")
    assert r.returncode == 1
    assert "not 5 tab-separated columns" in r.stderr


def test_check_line_accepts_comment_and_blank():
    assert run("--check-line", stdin="# a comment").returncode == 0
    assert run("--check-line", stdin="").returncode == 0


# --- check-file ----------------------------------------------------------------------------

def test_check_file_counts_rows(tmp_path):
    f = write(tmp_path, row(id_="BL-1"), row(id_="BL-2"))
    r = run("--check-file", str(f))
    assert r.returncode == 0
    assert "checked 2 behavior row(s)" in r.stdout


def test_check_file_fails_on_a_bad_row(tmp_path):
    f = write(tmp_path, row(id_="BL-1"), row(id_="nope"))
    r = run("--check-file", str(f))
    assert r.returncode == 1
    assert "bad id shape" in r.stderr


def test_check_file_empty_registry_is_zero_rows(tmp_path):
    f = tmp_path / "behavior-lock.tsv"
    f.write_text(HEADER, encoding="utf-8")
    r = run("--check-file", str(f))
    assert r.returncode == 0
    assert "checked 0 behavior row(s)" in r.stdout


# --- list-ids / carriers -------------------------------------------------------------------

def test_list_ids(tmp_path):
    f = write(tmp_path, row(id_="BL-2"), row(id_="BL-1"))
    ids = run("--list-ids", str(f)).stdout.split()
    assert ids == ["BL-1", "BL-2"]  # sorted, unique


def test_carriers_pairs_id_and_carrier(tmp_path):
    f = write(tmp_path, row(id_="BL-1", car="a/b.py::test_x"))
    out = run("--carriers", str(f)).stdout.strip()
    assert out == "BL-1\ta/b.py::test_x"


# --- resolve -------------------------------------------------------------------------------

def test_resolve_path_only_when_file_exists(tmp_path):
    (tmp_path / "t.py").write_text("def test_x(): pass\n", encoding="utf-8")
    assert run("--resolve", "t.py", str(tmp_path)).returncode == 0


def test_resolve_path_only_fails_when_absent(tmp_path):
    assert run("--resolve", "missing.py", str(tmp_path)).returncode == 1


def test_resolve_name_when_present(tmp_path):
    (tmp_path / "t.py").write_text("def test_keeps_promise():\n    pass\n", encoding="utf-8")
    assert run("--resolve", "t.py::test_keeps_promise", str(tmp_path)).returncode == 0


def test_resolve_name_fails_when_file_present_but_name_absent(tmp_path):
    # The file exists but the named test does not -- the carrier points at nothing.
    (tmp_path / "t.py").write_text("def test_other(): pass\n", encoding="utf-8")
    assert run("--resolve", "t.py::test_keeps_promise", str(tmp_path)).returncode == 1


def test_resolve_name_fails_when_file_absent(tmp_path):
    assert run("--resolve", "missing.py::test_x", str(tmp_path)).returncode == 1


# --- graduate ------------------------------------------------------------------------------

def test_graduate_moves_the_row_out(tmp_path):
    f = write(tmp_path, row(id_="BL-1"), row(id_="BL-2"))
    g = tmp_path / "graduated.tsv"
    r = run("--graduate", "BL-1", str(f), str(g))
    assert r.returncode == 0
    # BL-1 is gone from the live registry, BL-2 remains.
    live_ids = run("--list-ids", str(f)).stdout.split()
    assert live_ids == ["BL-2"]
    # BL-1 landed in the graduated archive.
    assert "BL-1" in g.read_text(encoding="utf-8")


def test_graduate_unknown_id_fails(tmp_path):
    f = write(tmp_path, row(id_="BL-1"))
    g = tmp_path / "graduated.tsv"
    r = run("--graduate", "BL-99", str(f), str(g))
    assert r.returncode == 1
    assert "no live row" in r.stderr
