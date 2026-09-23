"""the lead-sentence rule, and the falsifier its Exit asks for by name.

**No CJK in this file, deliberately.** This project bans CJK in shipped files outside
`README*` / `CHANGELOG.md` / `GUIDE*`.

**The Exit, quoted, because these tests exist to satisfy it exactly:**

    Either the format contract declares the lead-sentence-plus-detail rule, with a falsifier
    that puts a multi-hundred-character blob in a lead position and requires the check to go
    red; or it is written down that these documents are AI-facing only …

`test_a_blob_in_lead_position_is_rejected` IS that falsifier.

**Why a ratchet and not a bound.** Measured on the real roadmap in display columns: 49 of 52
name cells and 45 of 52 leads already exceed 60. A rule that reddens 45 rows on the day it
lands is a rule somebody switches off. So each row is pinned at its current width and may only
shrink, while a row that is new — or renamed, which is the same as having been touched — must
meet the bound outright. The tests below pin BOTH halves, because a ratchet with only one of
them is either a wall of red or a no-op.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
GUARD = REPO / "scripts" / "invariants" / "roadmap-lead-length.sh"
GENERATOR = REPO / "scripts" / "gen-roadmap-lead-baseline.sh"
REAL_BASELINE = REPO / ".claude" / "roadmap-lead-baseline.tsv"

pytestmark = pytest.mark.skipif(
    not GUARD.is_file(), reason="guard absent")

SHORT_NAME = "**S1 short row**"
SHORT_WHAT = "A short lead. Then as much detail as anyone wants, and it is not capped: "
BLOB = "x" * 400


def roadmap(rows: list[tuple[str, str]]) -> str:
    head = ("# R\n\n## \U0001f6e3 Mainline\n\n| station | what | weight | eta |\n"
            "|---|---|---|---|\n")
    body = "".join("| %s | %s | w | e |\n" % (n, w) for n, w in rows)
    return head + body + "\n"


def write(tmp_path: Path, rows, baseline: str | None = None):
    rm = tmp_path / "ROADMAP.md"
    rm.write_text(roadmap(rows), encoding="utf-8")
    bl = tmp_path / "baseline.tsv"
    bl.write_text(baseline if baseline is not None else "# empty\n", encoding="utf-8")
    return rm, bl


def run(rm: Path, bl: Path, cols: str = "60") -> subprocess.CompletedProcess:
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
           "ROADMAP_PATH": str(rm), "ROADMAP_LEAD_BASELINE": str(bl),
           "MAX_LEAD_COLS": cols}
    return subprocess.run(["/bin/bash", str(GUARD)], cwd=REPO, env=env,
                          capture_output=True, text=True)


def gen(rm: Path) -> str:
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
           "ROADMAP_PATH": str(rm)}
    p = subprocess.run(["/bin/bash", str(GENERATOR)], cwd=REPO, env=env,
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return p.stdout


# ================================================================= the Exit's falsifier


def test_a_blob_in_lead_position_is_rejected(tmp_path: Path) -> None:
    """The exit criterion, word for word: a multi-hundred-character blob in a lead position must make
    the check go red. Nothing marks the end of a lead in this row, so the whole cell is the
    lead — which is the honest reading, not a loophole."""
    rm, bl = write(tmp_path, [(SHORT_NAME, BLOB)])
    p = run(rm, bl)
    assert p.returncode != 0, p.stdout
    assert "the lead of its `what` cell is 400 display columns" in p.stderr, p.stderr


def test_the_same_blob_is_accepted_once_a_lead_is_marked(tmp_path: Path) -> None:
    """The positive control, and it is the whole point of the rule. The detail is NOT capped —
    Capping is rejected, because the detail is load-bearing. Marking where the lead ends is
    what makes the same text legal."""
    rm, bl = write(tmp_path, [(SHORT_NAME, "A short lead. " + BLOB)])
    p = run(rm, bl)
    assert p.returncode == 0, p.stderr + p.stdout
    assert p.stdout.startswith("✓"), p.stdout


def test_a_long_name_is_rejected_too(tmp_path: Path) -> None:
    """The column whose job is "which row is this" is the one measured worst in practice
    It gets the same bound."""
    rm, bl = write(tmp_path, [("**" + "y" * 200 + "**", SHORT_WHAT + "detail")])
    p = run(rm, bl)
    assert p.returncode != 0
    # 204, not 200: the two `**` pairs are part of the cell a reader sees.
    assert "name cell is 204 display columns" in p.stderr, p.stderr


# ================================================================= the ratchet, both halves


def test_a_pinned_row_may_stay_as_long_as_it_is(tmp_path: Path) -> None:
    rows = [(SHORT_NAME, BLOB)]
    rm, bl = write(tmp_path, rows)
    bl.write_text(gen(rm), encoding="utf-8")
    p = run(rm, bl)
    assert p.returncode == 0, p.stderr + p.stdout
    assert "52 row" not in p.stdout
    assert "1 pinned" in p.stdout, p.stdout


def test_a_pinned_row_may_not_grow(tmp_path: Path) -> None:
    """The half that makes the pin a ratchet instead of an exemption. Without it a pinned row
    could be made twice as bad and nothing would say so."""
    rm, bl = write(tmp_path, [(SHORT_NAME, BLOB)])
    bl.write_text(gen(rm), encoding="utf-8")
    rm.write_text(roadmap([(SHORT_NAME, BLOB + "z" * 50)]), encoding="utf-8")
    p = run(rm, bl)
    assert p.returncode != 0, p.stdout
    assert "grew from 400 to 450" in p.stderr, p.stderr


def test_a_pinned_row_may_shrink(tmp_path: Path) -> None:
    rm, bl = write(tmp_path, [(SHORT_NAME, BLOB)])
    bl.write_text(gen(rm), encoding="utf-8")
    rm.write_text(roadmap([(SHORT_NAME, "A short lead. " + BLOB)]), encoding="utf-8")
    p = run(rm, bl)
    assert p.returncode == 0, p.stderr + p.stdout


def test_renaming_a_row_drops_its_pin(tmp_path: Path) -> None:
    """The key is the name cell, and that is a property rather than an accident: renaming a row
    IS editing it, so it stops being grandfathered. Position would have been the obvious key and
    rots on the first reorder; the backlog id was measured instead of assumed and cannot serve —
    51 of 52 rows carry one, one carries none, and one id appears twice."""
    rm, bl = write(tmp_path, [(SHORT_NAME, BLOB)])
    bl.write_text(gen(rm), encoding="utf-8")
    rm.write_text(roadmap([("**S1 renamed row**", BLOB)]), encoding="utf-8")
    p = run(rm, bl)
    assert p.returncode != 0, p.stdout
    assert "new or was renamed" in p.stderr, p.stderr


def test_a_pinned_rows_name_cannot_change_while_pinned(tmp_path: Path) -> None:
    """Why there is no name ratchet, asserted rather than left as an absence.

    A mutant disabling the name ratchet SURVIVED, and the mutant was right: the pin is keyed on
    the name cell, so any edit to the name yields a different key and the row lands on the
    unpinned branch, where the bound applies outright. The ratchet could never fire. This case
    pins that reasoning: change only the name, and the row is treated as unpinned.
    """
    rm, bl = write(tmp_path, [("**S1 short row**", "A short lead. " + BLOB)])
    bl.write_text(gen(rm), encoding="utf-8")

    # [1] A SHORT rename: the row must lose its pin even though nothing goes red. The
    #     assertion is on the MECHANISM -- the count line -- not on a failure, because a
    #     rename that happens to stay within the bound is legal and must still be re-checked.
    rm.write_text(roadmap([("**S1 renamed but still short**", "A short lead. " + BLOB)]),
                  encoding="utf-8")
    p = run(rm, bl)
    assert p.returncode == 0, p.stderr
    assert "1 pinned, 1 unpinned" in p.stdout, (
        "the renamed row kept its pin, so the key is not the name cell: " + p.stdout)

    # [2] A LONG rename: same mechanism, now with a consequence. It reports the unpinned
    #     reason and NOT a ratchet message -- the ratchet is unreachable and was deleted.
    rm.write_text(roadmap([("**" + "n" * 80 + "**", "A short lead. " + BLOB)]),
                  encoding="utf-8")
    p = run(rm, bl)
    assert p.returncode != 0, p.stdout
    assert "new or was renamed" in p.stderr, p.stderr
    assert "grew from" not in p.stderr, "the unreachable ratchet came back: " + p.stderr


# ================================================================= scope honesty


def test_an_empty_scan_says_so_instead_of_passing(tmp_path: Path) -> None:
    rm = tmp_path / "ROADMAP.md"
    rm.write_text("# R\n\nno table here\n", encoding="utf-8")
    bl = tmp_path / "baseline.tsv"
    bl.write_text("# empty\n", encoding="utf-8")
    p = run(rm, bl)
    assert p.returncode == 0
    assert p.stdout.startswith("⊘"), "an empty scope printed like a verified one"
    assert "0 rows checked" in p.stdout


def test_the_generator_and_the_guard_measure_with_one_ruler(tmp_path: Path) -> None:
    """They share `scripts/lib/roadmap-lead.sh`. If they ever measured separately, a baseline
    would be a comparison between two different rulers — the encoder-divergence class this repo
    has already paid for."""
    src = GUARD.read_text(encoding="utf-8") + GENERATOR.read_text(encoding="utf-8")
    assert src.count("roadmap_lead_rows") >= 2
    assert "roadmap-lead.sh" in GUARD.read_text(encoding="utf-8")


@pytest.mark.skipif(not REAL_BASELINE.is_file(), reason="baseline absent (fresh clone)")
def test_the_real_baseline_is_what_the_generator_produces() -> None:
    """A hand-edited baseline would pin numbers nobody measured — which is how a ratchet
    silently becomes an exemption list."""
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"}
    p = subprocess.run(["/bin/bash", str(GENERATOR)], cwd=REPO, env=env,
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert p.stdout == REAL_BASELINE.read_text(encoding="utf-8"), (
        "the pinned baseline is not what the generator produces — regenerate it rather than "
        "editing it by hand"
    )


@pytest.mark.skipif(not REAL_BASELINE.is_file(), reason="baseline absent (fresh clone)")
def test_the_baseline_covers_every_row_the_guard_reads() -> None:
    """A generator that dies MID-FILE still leaves a plausible-looking baseline.

    Measured, not imagined: `grep -o` exits 1 on a row carrying no backlog id — one row does —
    and under `set -o pipefail` that killed the generator after 34 of 52 rows. The file looked
    complete. `test_the_real_baseline_is_what_the_generator_produces` cannot catch it either:
    a re-run truncates identically, and comparing a broken thing to itself agrees.

    The assertion is on the GUARD's own count of unpinned rows, not on a row counter written
    here. A second counter would be a second reader of the same grammar — the divergence class
    this repo keeps paying for — and it was tried: it disagreed with the shipped reader by one
    row (a nested table's header) and the disagreement was the test's fault, not the file's.
    A truncated baseline shows up as unpinned rows and nothing else has to be re-implemented
    to see it.
    """
    roadmap_md = REPO / "docs" / "ROADMAP.md"
    if not roadmap_md.is_file():
        pytest.skip("gitignored docs/ absent")
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"}
    p = subprocess.run(["/bin/bash", str(GUARD)], cwd=REPO, env=env,
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr + p.stdout
    assert "0 unpinned" in p.stdout, (
        "the baseline does not cover every row the guard reads: " + p.stdout)
    # And the scope is not empty, which would make the line above vacuous.
    assert "52 row" in p.stdout or "0 row" not in p.stdout, p.stdout
