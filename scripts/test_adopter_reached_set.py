import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CMP = REPO / "tests" / "adopter" / "compare-reached.sh"
EXPECTED = REPO / "tests" / "adopter" / "expected-branches.txt"


def _run(capture_text, tmp_path):
    cap = tmp_path / "capture.txt"
    cap.write_text(capture_text)
    return subprocess.run(
        ["/bin/bash", str(CMP), str(cap), str(EXPECTED)],
        capture_output=True, text=True,
    )


def test_empty_capture_fails(tmp_path):
    """A run that reached NOTHING has exercised nothing; it must be red."""
    proc = _run("nothing interesting happened\n", tmp_path)
    assert proc.returncode != 0
    assert "0/2" in proc.stdout or "reached 0" in proc.stdout.lower()


def test_partial_capture_names_the_missing(tmp_path):
    lines = EXPECTED.read_text().splitlines()
    proc = _run("\n".join(lines[:1]) + "\n", tmp_path)
    assert proc.returncode != 0
    for missing in lines[1:]:
        assert missing in proc.stdout, "each missing branch must be named, not just counted"


def test_full_capture_passes(tmp_path):
    proc = _run(EXPECTED.read_text(), tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_empty_expected_set_fails(tmp_path):
    """An empty (or all-blank) expected-set file must never let
    this comparator read as success -- that would be a
    check that claims a scope it does not actually assert over. A truncated or bad-merged
    expected-branches.txt must FAIL, loudly, not pass with `reached 0/0`."""
    empty_expected = tmp_path / "expected-empty.txt"
    empty_expected.write_text("")
    cap = tmp_path / "capture.txt"
    cap.write_text("anything at all\n")
    proc = subprocess.run(
        ["/bin/bash", str(CMP), str(cap), str(empty_expected)],
        capture_output=True, text=True,
    )
    assert proc.returncode != 0
    assert "empty" in proc.stdout.lower()
