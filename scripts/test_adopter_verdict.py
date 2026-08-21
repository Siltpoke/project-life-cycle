import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CMP = REPO / "tests" / "adopter" / "compare-verdict.sh"
EXPECTED = REPO / "tests" / "adopter" / "expected-verdict.txt"

# A synthetic capture, so these run without docker. It carries the two exit pins and the two ✗
# rows expected-verdict.txt declares, plus surrounding noise -- the noise matters: the ✗ oracle
# is set-equality over ✗ ROWS ONLY, and a ✓/⚠ row appearing or vanishing must not move it.
CAPTURE = """=== gen-test-evidence (adopter path) ===
\u2713 evidence written: .adopter/.last-test-run (set=phase)
ADOPTER-EVIDENCE-EXIT=0
=== close-gate ===
\u2713 CHANGELOG.md touched in range
\u26a0 no invariants declared in manifest \u2014 skipping the invariants run
{rows}
ADOPTER-GATE-EXIT={gate}
=== end ===
"""


def _rows():
    return [
        ln for ln in EXPECTED.read_text(encoding="utf-8").splitlines()
        if ln.startswith("\u2717 ")
    ]


def _capture(tmp_path, rows=None, gate="1", name="capture.txt"):
    text = CAPTURE.format(rows="\n".join(_rows() if rows is None else rows), gate=gate)
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def _run(capture, expected=EXPECTED):
    return subprocess.run(
        ["/bin/bash", str(CMP), str(capture), str(expected)],
        capture_output=True, text=True,
    )


def test_control_matching_run_passes(tmp_path):
    """The control. Without it every red below could be red for an unrelated reason."""
    proc = _run(_capture(tmp_path))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "set-equal" in proc.stdout


def test_expected_row_vanishing_fails(tmp_path):
    """The finding fixed in the product = this fixture MUST go red. That is the whole reason the
    fabricated manifest is not simply given the missing key: a subset oracle would let the
    finding disappear silently, and then nothing would ever force the finding closed."""
    rows = _rows()
    proc = _run(_capture(tmp_path, rows=[r for r in rows if "validator_input_paths_rationale" not in r]))
    assert proc.returncode != 0
    assert "did NOT produce" in proc.stdout
    assert "validator_input_paths_rationale" in proc.stdout, "the missing row must be NAMED"


def test_new_untriaged_row_fails(tmp_path):
    """A ✗ nobody has looked at is a new product finding. Extra output is fine for
    compare-reached.sh (subset) and must NOT be fine here."""
    proc = _run(_capture(tmp_path, rows=_rows() + ["\u2717 some brand new product defect"]))
    assert proc.returncode != 0
    assert "nobody has looked at" in proc.stdout
    assert "brand new product defect" in proc.stdout


def test_abort_does_not_read_as_the_expected_fail(tmp_path):
    """The gate exits 90 when it aborts half-way (scripts/invariants/gate-abort-is-not-success.sh).
    Pinning "non-zero" would let an abort -- a run that checked almost nothing -- satisfy a file
    whose whole claim is that these specific checks ran and produced these specific rows."""
    proc = _run(_capture(tmp_path, gate="90"))
    assert proc.returncode != 0
    assert "ADOPTER-GATE-EXIT=90" in proc.stdout


def test_evidence_regression_fails(tmp_path):
    """The adopter evidence path exiting non-zero is a regression seen before (the generator was run
    before `git add`, so it fingerprinted nothing). Nothing watched it until this pin."""
    cap = _capture(tmp_path)
    cap.write_text(
        cap.read_text(encoding="utf-8").replace("ADOPTER-EVIDENCE-EXIT=0", "ADOPTER-EVIDENCE-EXIT=1"),
        encoding="utf-8",
    )
    proc = _run(cap)
    assert proc.returncode != 0
    assert "ADOPTER-EVIDENCE-EXIT" in proc.stdout


def test_duplicate_pin_fails(tmp_path):
    """Two runs concatenated into one capture. "the value is in there somewhere" is a weaker
    claim than "this run produced it", and the two must not be confusable."""
    cap = _capture(tmp_path)
    cap.write_text(cap.read_text(encoding="utf-8") * 2, encoding="utf-8")
    proc = _run(cap)
    assert proc.returncode != 0
    assert "appears 2 times" in proc.stdout


def test_empty_expected_file_fails(tmp_path):
    """Zero is never vacuous. A truncated or bad-merged expected file must not assert nothing
    and print ok."""
    e = tmp_path / "empty.txt"
    e.write_text("", encoding="utf-8")
    proc = _run(_capture(tmp_path), expected=e)
    assert proc.returncode != 0
    assert "asserts nothing" in proc.stdout


def test_pins_without_rows_needs_the_sentinel(tmp_path):
    """"I expect no ✗ rows" and "I forgot to write the ✗ rows" must not look the same."""
    e = tmp_path / "pins-only.txt"
    e.write_text("ADOPTER-GATE-EXIT=1\n", encoding="utf-8")
    proc = _run(_capture(tmp_path), expected=e)
    assert proc.returncode != 0
    assert "NO-FAIL-ROWS" in proc.stdout


def test_sentinel_alone_is_a_legal_declaration(tmp_path):
    """The sentinel is not decoration -- it is the shape this file takes the day the product has
    no findings left. Asserted so the escape hatch is known to work before anyone needs it."""
    e = tmp_path / "none.txt"
    e.write_text("NO-FAIL-ROWS\n", encoding="utf-8")
    proc = _run(_capture(tmp_path, rows=[]), expected=e)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_sentinel_contradicting_listed_rows_fails(tmp_path):
    e = tmp_path / "both.txt"
    e.write_text(EXPECTED.read_text(encoding="utf-8") + "NO-FAIL-ROWS\n", encoding="utf-8")
    proc = _run(_capture(tmp_path), expected=e)
    assert proc.returncode != 0
    assert "NO-FAIL-ROWS" in proc.stdout


def test_unrecognized_line_is_not_skipped(tmp_path):
    """A ✗ row that lost its glyph to an editor would otherwise silently shrink what this file
    asserts. An unparsed line is not evidence of absence."""
    e = tmp_path / "typo.txt"
    e.write_text(
        EXPECTED.read_text(encoding="utf-8").replace("\u2717 close-gate FAIL", "close-gate FAIL"),
        encoding="utf-8",
    )
    proc = _run(_capture(tmp_path), expected=e)
    assert proc.returncode != 0
    assert "unrecognized line" in proc.stdout


def test_shipped_expected_file_still_pins_the_finding(tmp_path):
    """A pin on the FILE, not on behaviour. Every test above would stay green if someone edited
    the finding's row out of expected-verdict.txt and out of the fixture at the same time; this is the
    one that would not."""
    text = EXPECTED.read_text(encoding="utf-8")
    assert "validator_input_paths_rationale" in text
    assert "fixed in the product" in text, "the finding this row protects must be explained where it is edited"
