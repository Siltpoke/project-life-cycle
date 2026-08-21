#!/usr/bin/env python3
"""Tests for the PASS-4a automated verifier (hard gate on a finished report).

These are the deterministic framing-safety assertions: things a script can
prove about the report text without judgment. The judgment layer (PASS-4b cold
critic) is an LLM step, not tested here. Run::

    pytest scripts/test_builder_profile_verify.py -v
"""

from __future__ import annotations

import builder_profile_verify as v

GOOD = """# Builder Profile — snapshot

## Five dimensions

- **Steering — the spine.** *(interpretation confidence: med — qual.)* evidence.
- **Engineering — not assessable.** *(confidence: n/a.)* Bash 1200 vs Agent 400
  = 3:1, main-thread only; delegated work excluded / unmeasured. No verdict.

## Usage (band — external prior, inline only)

- **Volume:** 40 conversations ≈ heavy — per a stale, tail-biased impression.
- **Model tier:** Opus almost exclusively ≈ top-tier — same prior caveat.
"""


def test_good_report_passes() -> None:
    assert v.verify_report(GOOD) == []


# --- no Level section ------------------------------------------------------- #
def test_level_section_blocked() -> None:
    bad = GOOD + "\n## Usage Level\n\nyou rank high.\n"
    fails = v.check_no_level_section(bad)
    assert fails
    assert any("level" in f.lower() for f in fails)


def test_level_inside_word_not_flagged() -> None:
    # "level" only flagged as a heading, not in prose like "usage-level"
    ok = "## Usage\n\nthis is usage-level only, no heading.\n"
    assert v.check_no_level_section(ok) == []


# --- band placement --------------------------------------------------------- #
def test_band_on_plan_ratio_blocked() -> None:
    bad = "## Usage\n\n- **Plan-ratio:** ≈ heavy this month.\n"
    fails = v.check_band_placement(bad)
    assert fails


def test_band_on_volume_ok() -> None:
    ok = "## Usage\n\n- **Volume:** 42 sessions ≈ heavy — per prior.\n"
    assert v.check_band_placement(ok) == []


# --- dimension confidence --------------------------------------------------- #
def test_dimension_without_confidence_blocked() -> None:
    bad = """## Five dimensions

- **Steering — the spine.** evidence but no such marker here.
"""
    fails = v.check_dimension_confidence(bad)
    assert fails


def test_dimension_with_confidence_ok() -> None:
    ok = """## Five dimensions

- **Steering — the spine.** *(confidence: med)* evidence.
"""
    assert v.check_dimension_confidence(ok) == []


# --- tool-count scope ------------------------------------------------------- #
def test_toolcount_without_scope_blocked() -> None:
    bad = """## Five dimensions

- **Engineering.** *(confidence: med)* Bash 1200 vs Agent 400, very hands-on.
"""
    fails = v.check_toolcount_scope(bad)
    assert fails


def test_toolcount_with_scope_ok() -> None:
    ok = """## Five dimensions

- **Engineering.** *(confidence: n/a)* Bash 1200 main-thread only; delegated
  work excluded / unmeasured.
"""
    assert v.check_toolcount_scope(ok) == []


# --- band provenance -------------------------------------------------------- #
def test_band_without_provenance_blocked() -> None:
    bad = "## Usage\n\n- **Volume:** 42 sessions ≈ heavy.\n"
    fails = v.check_band_provenance(bad)
    assert fails


def test_band_with_provenance_ok() -> None:
    ok = "## Usage\n\n- **Volume:** 42 sessions ≈ heavy — per a stale impression.\n"
    assert v.check_band_provenance(ok) == []


def test_band_provenance_paragraph_level_not_line_level() -> None:
    # band on a wrapped continuation line; provenance on the bullet's first line.
    # spec says "same sentence OR paragraph" -> must PASS (no false-fail).
    ok = "## Usage\n\n- **Model tier:** Opus mostly, per a stale prior\n  ≈ top-tier here.\n"
    assert v.check_band_provenance(ok) == []


def test_band_provenance_wrapped_but_truly_missing_still_fails() -> None:
    # wrapped bullet with no provenance token anywhere -> must still FAIL.
    bad = "## Usage\n\n- **Model tier:** Opus mostly\n  ≈ top-tier, same caveat.\n"
    assert v.check_band_provenance(bad)


# --- main ------------------------------------------------------------------- #
def test_main_passes_good_report(tmp_path) -> None:
    f = tmp_path / "r.md"
    f.write_text(GOOD, encoding="utf-8")
    assert v.main([str(f)]) == 0


def test_main_blocks_bad_report(tmp_path) -> None:
    f = tmp_path / "r.md"
    f.write_text(GOOD + "\n## Final Level\n\nrank.\n", encoding="utf-8")
    assert v.main([str(f)]) == 1
