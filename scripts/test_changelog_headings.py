"""Within one `## ` section of CHANGELOG.md, no `### ` heading appears twice.

These rows run the
REAL script against throwaway fixtures under `tmp_path` — nothing here reads the repo's own
changelog, because a suite whose verdict depends on a tracked document goes red for reasons that
have nothing to do with the mechanism.

Every green row below is paired with a reason it could go red; a fixture that cannot fail is not
a control. The per-section row is the important one — "count headings per file" is the most
likely wrong implementation and it is the only thing that row distinguishes.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

# Overridable so the suite can be mutation-tested without editing the tracked script.
INVARIANT = Path(
    os.environ.get(
        "PLC_CHANGELOG_HEADINGS_IMPL",
        Path(__file__).resolve().parent / "invariants/changelog-one-heading-per-category.sh",
    )
)


def _run(target: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """The target is passed as an ARGUMENT, never through the environment — see
    `test_the_old_env_override_is_inert` for why that distinction is load-bearing."""
    return subprocess.run(
        ["/bin/bash", str(INVARIANT), str(target)],
        env={**os.environ, **(env or {})},
        capture_output=True,
        text=True,
        check=False,
    )


def _write(tmp_path: Path, body: str) -> Path:
    target = tmp_path / "CHANGELOG.md"
    target.write_text(body)
    return target


def test_duplicate_heading_in_one_section_fails(tmp_path: Path) -> None:
    """AC1/AC6. A duplicate heading in one section, planted."""
    target = _write(
        tmp_path,
        "## [Unreleased]\n\n### Added\n- a\n\n### Fixed\n- b\n\n### Added\n- c\n",
    )
    result = _run(target)
    assert result.returncode != 0, result.stdout + result.stderr
    assert "## [Unreleased]" in result.stdout
    assert "### Added" in result.stdout
    # BOTH line numbers, not just the second. The second alone says something is wrong and
    # withholds where the other one is.
    #
    # Asserted as the literal rendered list, NOT as `"3" in stdout and "9" in stdout`. That was
    # the first draft and it SURVIVED the mutation that reports only the last line number —
    # `tmp_path` is spelled into the message and supplies stray digits, so the row was passing
    # on the fixture's own directory name. Measured, not reasoned: the mutant passed.
    assert "lines 3, 9" in result.stdout


def test_distinct_headings_pass(tmp_path: Path) -> None:
    """AC2. Would go red if the dedup key ignored the heading text."""
    target = _write(tmp_path, "## [Unreleased]\n\n### Added\n- a\n\n### Fixed\n- b\n")
    result = _run(target)
    assert result.returncode == 0, result.stdout + result.stderr


def test_same_heading_in_two_different_sections_passes(tmp_path: Path) -> None:
    """The check is per-SECTION, not per-file.

    A `### Added` in `[Unreleased]` and another in `[1.0.0]` is the normal shape of every
    changelog ever written. An implementation that counted headings per file would be red here
    and green nowhere useful — this row is the only thing that tells the two apart, and it is
    measured red against exactly that mutation (dropping the section from the dedup key).
    """
    target = _write(
        tmp_path,
        "## [Unreleased]\n\n### Added\n- a\n\n## [1.0.0]\n\n### Added\n- b\n",
    )
    result = _run(target)
    assert result.returncode == 0, result.stdout + result.stderr


def test_duplicate_inside_a_backtick_fence_is_not_counted(tmp_path: Path) -> None:
    """AC8. Fenced content is not a heading — a class the retention drain has also had to
    handle. Red without the fence toggle."""
    target = _write(
        tmp_path,
        "## [Unreleased]\n\n### Added\n- a\n\n```\n### Added\n### Added\n```\n\n- still a\n",
    )
    result = _run(target)
    assert result.returncode == 0, result.stdout + result.stderr


def test_duplicate_inside_a_tilde_fence_is_not_counted(tmp_path: Path) -> None:
    """AC8, the other fence spelling. CommonMark allows `~~~` and a toggle written only for
    backticks would pass every backtick fixture while being half a check."""
    target = _write(
        tmp_path,
        "## [Unreleased]\n\n### Added\n- a\n\n~~~\n### Added\n~~~\n",
    )
    result = _run(target)
    assert result.returncode == 0, result.stdout + result.stderr


def test_absent_file_is_a_hard_failure(tmp_path: Path) -> None:
    """No vacuous pass. An empty set comparing equal to an empty set checks nothing."""
    result = _run(tmp_path / "does-not-exist.md")
    assert result.returncode != 0, result.stdout + result.stderr
    assert "not a regular file" in result.stdout


def test_file_with_no_sections_is_a_hard_failure(tmp_path: Path) -> None:
    """Same class. A changelog with zero `## ` sections is a broken input, not a clean one —
    and note the fixture repeats `### Added` twice, so a check that merely 'found no sections
    and therefore no duplicates' would be silently wrong rather than loudly."""
    target = _write(tmp_path, "just prose\n\n### Added\n### Added\n")
    result = _run(target)
    assert result.returncode != 0, result.stdout + result.stderr
    assert "no \"## \" section found" in result.stdout


def test_case_is_not_folded(tmp_path: Path) -> None:
    """A stated limit, pinned so it is a decision rather than a bug someone 'fixes' later.

    `### Fixed` and `### fixed` are two distinct headings. Catching that pair is a different
    check (canonical spelling); folding it in here would make one failure message ambiguous
    about which rule fired.
    """
    target = _write(tmp_path, "## [Unreleased]\n\n### Fixed\n- a\n\n### fixed\n- b\n")
    result = _run(target)
    assert result.returncode == 0, result.stdout + result.stderr


def test_closing_atx_sequence_is_the_same_heading(tmp_path: Path) -> None:
    """`### Added ###` and `### Added` render as the same h3, so they are one heading.

    Reproduced before being believed: an earlier implementation
    keyed the raw line and returned **exit 0** on this input — a real duplicate, silently passed.
    """
    target = _write(
        tmp_path, "## S\n\n### Added ###\n- a\n\n### Added\n- b\n"
    )
    result = _run(target)
    assert result.returncode != 0, result.stdout + result.stderr
    assert "lines 3, 6" in result.stdout


def test_a_heading_ending_in_a_hash_is_not_truncated(tmp_path: Path) -> None:
    """The control for the row above. CommonMark requires a closing sequence to be preceded by
    whitespace, so `### C#` keeps its hash — without this row, stripping trailing hashes could
    silently merge two genuinely different headings and nothing would notice."""
    target = _write(tmp_path, "## S\n\n### C#\n- a\n\n### C\n- b\n")
    result = _run(target)
    assert result.returncode == 0, result.stdout + result.stderr


def test_four_space_indented_backticks_are_code_not_a_fence(tmp_path: Path) -> None:
    """A fence may be indented at most three spaces; four makes it indented code CONTENT.

    Treating it as a fence is the dangerous direction — the toggle flips and every real heading
    after it is skipped. Measured at **exit 0** before the bound existed, on two genuine duplicates.
    """
    target = _write(
        tmp_path, "## S\n\n    ```\n### Added\n\n### Added\n    ```\n"
    )
    result = _run(target)
    assert result.returncode != 0, result.stdout + result.stderr
    assert "lines 4, 6" in result.stdout


def test_three_space_indented_fence_is_still_a_fence(tmp_path: Path) -> None:
    """The boundary on the other side. Without this row the bound could be tightened to zero
    indent and every fixture above would stay green."""
    target = _write(
        tmp_path, "## S\n\n### Added\n\n   ```\n### Added\n   ```\n"
    )
    result = _run(target)
    assert result.returncode == 0, result.stdout + result.stderr


def test_headings_inside_an_html_block_are_counted_LIMIT(tmp_path: Path) -> None:
    """LIMIT, asserted rather than wished away — this is a **false red**.

    In CommonMark a `<div>` opens an HTML block running to the next blank line, so the second
    `### Added` below is raw text and not a heading. This script counts it and fails. Closing that
    means modelling CommonMark's seven HTML-block start conditions — a parser, in a file whose
    value is being fast and greppable — and the failure direction is the survivable one: a loud red
    on a file the author can edit, not a silent pass.

    The row asserts the LIMIT, so anyone who closes it makes this fail and has to read this note.
    """
    target = _write(tmp_path, "## S\n\n### Added\n\n<div>\n### Added\n</div>\n")
    result = _run(target)
    assert result.returncode != 0, result.stdout + result.stderr


def test_the_old_env_override_is_inert(tmp_path: Path) -> None:
    """The deleted `PLC_CHANGELOG_PATH` must not come back quietly under its own name.

    It existed so fixtures could redirect the target, and a real run showed the cost:
    pointed at a `README.md` — a regular, readable file with `## `
    sections — the invariant returned **exit 0** and the close gate printed `✓ … holds` while
    `CHANGELOG.md` was never opened. The three guards (regular file / readable / has sections) all
    pass on that decoy, which is the point: they were never the thing standing between an ambient
    environment and a green gate.

    Here the argument names a file with a duplicate and the environment variable names a clean one.
    A run that honours the environment goes green; the invariant must stay **red**.
    """
    dirty = _write(tmp_path, "## S\n\n### Added\n- a\n\n### Added\n- b\n")
    clean = tmp_path / "clean.md"
    clean.write_text("## S\n\n### Added\n- a\n")
    result = _run(dirty, env={"PLC_CHANGELOG_PATH": str(clean)})
    assert result.returncode != 0, result.stdout + result.stderr


def test_invariant_source_names_no_env_override() -> None:
    """The other half of the row above: a grep is what catches the variable coming back under a
    different spelling in the source, where a behavioural row only sees the one name it knows."""
    source = (
        Path(__file__).resolve().parent / "invariants/changelog-one-heading-per-category.sh"
    ).read_text()
    executable = [ln for ln in source.splitlines() if not ln.lstrip().startswith("#")]
    assert not any("PLC_CHANGELOG_PATH" in line for line in executable), (
        "the target is an explicit argument; an environment override is not a capability"
    )


def test_invariant_source_contains_no_python_interpreter() -> None:
    """AC7, kept here as a file-local check beside the envelope's.

    `scripts/invariants/gate-jq-only-envelope.sh` declares this file too, but that list lives in
    another script and can be narrowed there without anyone reading this file. With this row the
    no-python property stays pinned next to the file's own tests, so the envelope sentence in that
    script's header cannot quietly become a claim wider than its mechanism.
    """
    source = (
        Path(__file__).resolve().parent / "invariants/changelog-one-heading-per-category.sh"
    ).read_text()
    executable = []
    for line in source.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        executable.append(line)
    assert not any("python" in line for line in executable), (
        "the invariant's envelope is bash + grep + awk; a python interpreter appeared in a "
        "non-comment line"
    )
