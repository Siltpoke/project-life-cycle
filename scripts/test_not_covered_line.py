"""The untracked-artifact skips are printed as a counted ABSENCE OF COVERAGE that
names the artifact responsible, and a skip never renders as a pass.

A reviewer reading the line once is not a regression guard.
"""
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PRINTER = REPO / "tests" / "adopter" / "print-not-covered.sh"
BASELINE = REPO / "tests" / "adopter" / "skip-baseline.txt"

# The words the design bans on this line. "skipped" is the word a reader's eye slides past, which
# is how rows of missing coverage come to read as passes.
BANNED = ("skip", "ok", "pass")


def _run(baseline=BASELINE):
    return subprocess.run(
        ["/bin/bash", str(PRINTER), str(baseline)], capture_output=True, text=True,
    )


def _artifacts():
    rows = BASELINE.read_text(encoding="utf-8").splitlines()
    return sorted({r.split(" -> ", 1)[1] for r in rows if " -> " in r})


def test_every_artifact_is_named():
    """The criterion is "naming the artifact responsible" -- a total names nobody."""
    proc = _run()
    assert proc.returncode == 0, proc.stdout + proc.stderr
    for artifact in _artifacts():
        assert artifact in proc.stdout, f"{artifact} costs coverage and is not named"


def test_no_banned_word_appears():
    """Whole-word, case-insensitive. Substring matching would fire on "package"/"okay" and a
    guard that cannot be satisfied gets deleted rather than obeyed."""
    import re
    proc = _run()
    for word in BANNED:
        assert not re.search(rf"\b{word}\w*", proc.stdout, re.I), (
            f"the word {word!r} renders missing coverage as success: {proc.stdout!r}"
        )


def test_the_count_is_the_baseline_count():
    proc = _run()
    n = len([r for r in BASELINE.read_text(encoding="utf-8").splitlines() if r.strip()])
    assert f"{n} rows NOT COVERED in total" in proc.stdout


def test_a_row_moving_to_a_new_artifact_changes_what_is_named(tmp_path):
    """The falsifier for "is it really reading the baseline". A printer that hardcoded today's
    artifacts would pass every test above."""
    b = tmp_path / "baseline.txt"
    b.write_text("scripts/test_x.py::1 -> some/other/artifact.sh\n", encoding="utf-8")
    proc = _run(b)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "some/other/artifact.sh is not tracked" in proc.stdout
    assert ".git/hooks/pre-push" not in proc.stdout


def test_empty_baseline_fails(tmp_path):
    """Zero rows and a baseline that failed to generate look identical in a count. "0 rows NOT
    COVERED" would read as full coverage, which is the wrong-green this whole criterion is about."""
    b = tmp_path / "empty.txt"
    b.write_text("", encoding="utf-8")
    proc = _run(b)
    assert proc.returncode != 0
    assert "not evidence of full coverage" in proc.stderr


def test_unreadable_baseline_fails(tmp_path):
    proc = _run(tmp_path / "does-not-exist.txt")
    assert proc.returncode != 0
    assert "unreadable" in proc.stderr


def test_the_container_run_uses_this_printer():
    """A pin on the WIRING. Every test above would stay green if run.sh quietly went back to its
    own inline echo -- which is exactly the form this replaces."""
    run_sh = (REPO / "tests" / "adopter" / "run.sh").read_text(encoding="utf-8")
    assert "print-not-covered.sh" in run_sh
    assert "rows NOT COVERED -- gated on artifacts" not in run_sh, "the un-naming form came back"
