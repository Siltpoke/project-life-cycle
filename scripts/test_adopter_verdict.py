import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CMP = REPO / "tests" / "adopter" / "compare-verdict.sh"
EXPECTED = REPO / "tests" / "adopter" / "expected-verdict.txt"

# A synthetic capture, so these run without docker. It carries the two exit pins and whatever ✗
# rows expected-verdict.txt declares -- which since 2026-08-25 is NONE -- plus surrounding noise.
# The noise matters: the ✗ oracle is set-equality over ✗ ROWS ONLY, and a ✓/⚠ row appearing or
# vanishing must not move it.
#
# A SYNTHETIC ✗ ROW, used by the tests below that need the comparator to have something to compare.
# It is deliberately NOT a row any real gate prints: these tests exercise the comparator's grammar,
# and drawing their material from the shipped expected file made four of them collateral damage the
# day that file legitimately went empty.
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


SYNTHETIC_ROW = "\u2717 a fabricated finding, for the comparator's benefit only"


def _synthetic_expected(tmp_path, name, rows=(SYNTHETIC_ROW,), gate="1", extra=""):
    """An expected file written HERE rather than derived from the shipped one."""
    body = f"ADOPTER-EVIDENCE-EXIT=0\nADOPTER-GATE-EXIT={gate}\n" + "\n".join(rows) + "\n" + extra
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


def _capture(tmp_path, rows=None, gate="0", name="capture.txt"):
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
    """REWRITTEN, not deleted. It used to assert that deleting the the narrowed-inputs finding row
    from a capture was caught -- the finding must not be able to vanish silently. the narrowed-inputs finding is now
    fixed, the fixture is clean, and there is no row left to delete: written against the shipped
    file, this test would have become a no-op that passed (the filter matches nothing, the sets
    stay equal). A pin that cannot fail is worse than a deleted one, because it still counts.

    The same property, on material of its own: a row the expected file declares and the run did
    NOT produce is a failure, and the missing row is NAMED rather than merely counted."""
    e = _synthetic_expected(tmp_path, "declared.txt")
    proc = _run(_capture(tmp_path, rows=[], gate="1"), expected=e)
    assert proc.returncode != 0
    assert "did NOT produce" in proc.stdout
    assert "fabricated finding" in proc.stdout, "the missing row must be NAMED"


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
    """Material is synthetic since 2026-08-25: the shipped file now legitimately declares
    NO-FAIL-ROWS and lists nothing, so deriving "a file that says both" from it is impossible."""
    e = _synthetic_expected(tmp_path, "both.txt", extra="NO-FAIL-ROWS\n")
    proc = _run(_capture(tmp_path, rows=[SYNTHETIC_ROW], gate="1"), expected=e)
    assert proc.returncode != 0
    assert "NO-FAIL-ROWS" in proc.stdout


def test_unrecognized_line_is_not_skipped(tmp_path):
    """A ✗ row that lost its glyph to an editor would otherwise silently shrink what this file
    asserts. An unparsed line is not evidence of absence."""
    e = _synthetic_expected(tmp_path, "typo.txt", rows=(SYNTHETIC_ROW.replace("\u2717 ", ""),))
    proc = _run(_capture(tmp_path, rows=[SYNTHETIC_ROW], gate="1"), expected=e)
    assert proc.returncode != 0
    assert "unrecognized line" in proc.stdout


def test_shipped_expected_file_still_pins_the_finding(tmp_path):
    """A pin on the FILE, not on behaviour. REWRITTEN 2026-08-25 (p37:AC10) rather than deleted:
    it used to require the shipped file to carry the the narrowed-inputs finding ✗ row and to name the narrowed-inputs finding where that row is
    edited. The row is gone because the finding is FIXED, so what needs protecting changed -- but
    the reason for a file-level pin did not. Two things must survive:

      * the emptiness is DECLARED, not merely empty. `NO-FAIL-ROWS` is the grammar's explicit way
        to say "zero ✗ rows expected"; a file that simply listed none would be a FAIL, because
        "I meant none" and "I forgot" look identical.
      * the narrowed-inputs finding stays NAMED. This file is where the finding lived, so it is where the record of its
        closing belongs. A green fixture with no history says nothing about what it used to catch.
    """
    text = EXPECTED.read_text(encoding="utf-8")
    assert "NO-FAIL-ROWS" in text, "the empty ✗ set must be DECLARED, not merely absent"
    assert not [ln for ln in text.splitlines() if ln.startswith("\u2717 ")], (
        "a ✗ row reappeared in the shipped expected file; if that is a real new finding it needs "
        "triage, and this pin's NO-FAIL-ROWS half needs rewriting with it"
    )
    assert "NARROWED-INPUTS FINDING" in text.upper(), "the finding this file used to protect must stay named where it is edited"


# --- p37:AC11 --------------------------------------------------------------------------------
README = REPO / "tests" / "adopter" / "README.md"


def test_readme_does_not_open_with_the_unqualified_adopter_path_claim():
    """The retired sentence is QUOTED in the new text on purpose -- this repo keeps a wrong claim
    visible rather than deleting it -- so this asserts it is no longer the OPENING claim, not that
    the words are absent. The check is positional: the first paragraph after the title must not
    assert an unqualified 'adopter path'."""
    lines = [ln for ln in README.read_text(encoding="utf-8").splitlines() if ln.strip()]
    head = " ".join(lines[1:6])
    assert "exercises the close gate's adopter path" not in head, (
        "the unqualified claim is back at the top of the file:\n" + head
    )


def test_readme_names_the_script_it_actually_runs_and_the_one_it_does_not():
    """A fixture that runs one gate while a reader believes it runs the other is the shape the narrowed-inputs finding
    itself was. Both scripts must be named, and the conformance suite must be pointed at as where
    the canonical gate's coverage lives."""
    text = README.read_text(encoding="utf-8")
    for needle, why in (
        ("scripts/close-gate.sh", "the script this fixture actually copies and runs"),
        ("references/close-gate.md", "the script an adopter actually copies, which this does NOT run"),
        ("scripts/test_gate_conformance.py", "where the canonical gate's coverage does live"),
        ("a-maintainer-only-invariant.sh", "an invariant that does not ship, invoked as if adopter-facing"),
    ):
        assert needle in text, f"{README.name} does not name {needle} -- {why}"
