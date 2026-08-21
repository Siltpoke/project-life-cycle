"""The mutation harness's own guard: a stranded needle must be RED, not a silent survivor.

The harness in `mutate_retention_drain.py` locates each mutation by the exact TEXT it removes.
That is deliberate — a matrix keyed on line numbers mutates the wrong line the moment anything is
inserted above it, while still printing a kill. But text has its own failure mode: when the
production code is edited, a needle can stop matching, and then the "mutant" is byte-identical to
the source, every fixture passes, and the matrix reports `SURVIVED (0/N)`.

That reads exactly like a coverage hole. Somebody would go and write a fixture for a mechanism
that is already covered, and the mechanism the needle was actually pointing at would go unguarded.

So the harness raises on a needle that does not resolve to exactly one place, and these tests are
what make that raise reach anyone: they run in the ordinary suite, on every push, without anyone
choosing to re-run the matrix.

They deliberately do NOT run the matrix. That takes minutes per mutant and its verdicts belong in
a phase's evidence, not in the suite that has to stay fast enough to run three times.
"""
from __future__ import annotations

import subprocess

import pytest

from mutate_retention_drain import MUTANTS, SRC, StrandedNeedle, build

MUTANT_NAMES = [name for name, _, _ in MUTANTS]


@pytest.mark.parametrize("name", MUTANT_NAMES)
def test_every_needle_still_resolves_to_exactly_one_place(name: str) -> None:
    """Each mutant's needles match the CURRENT source, once each.

    Parametrised per mutant rather than looped, so a failure names the stranded one instead of
    stopping at the first and leaving the rest unmeasured.
    """
    build(name)  # raises StrandedNeedle with the offending needle and its count


@pytest.mark.parametrize("name", MUTANT_NAMES)
def test_every_mutant_differs_from_the_source_and_is_runnable_bash(name: str, tmp_path) -> None:
    """A mutant has to be both changed and executable, or its verdict means nothing.

    Byte-identical → every fixture passes and the matrix calls it SURVIVED. Syntactically broken →
    every fixture fails and the matrix calls it KILLED, by ~everything, for a reason that has
    nothing to do with the mechanism removed.
    """
    source = SRC.read_text(encoding="utf-8")
    mutated = build(name, source)
    assert mutated != source, f"{name} produced the tracked source unchanged"

    path = tmp_path / f"{name}.sh"
    path.write_text(mutated, encoding="utf-8")
    syn = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
    assert syn.returncode == 0, f"{name} is not runnable bash:\n{syn.stderr}"


def test_a_stranded_needle_raises_rather_than_building_a_no_op() -> None:
    """The positive control for the two tests above.

    Without this, both would pass against a `build()` that silently skipped needles it could not
    find — which is precisely the failure they exist to prevent, and it would look identical from
    a green suite.
    """
    source = SRC.read_text(encoding="utf-8")
    name = MUTANT_NAMES[0]
    needle = MUTANTS[0][2][0][0]
    assert source.count(needle) == 1, "this control's own assumption no longer holds"

    with pytest.raises(StrandedNeedle) as caught:
        build(name, source.replace(needle, "# the production code moved on\n"))
    assert name in str(caught.value)

    # And the other direction: a needle matching TWICE is stranded too, because the replacement
    # would land in a place nobody chose.
    with pytest.raises(StrandedNeedle):
        build(name, source.replace(needle, needle + needle))


def test_the_harness_carries_no_absolute_paths() -> None:
    """It is tracked now, so it has to work in someone else's checkout.

    The scratch version hardcoded an absolute path to one machine's home directory. That is both
    broken for every other clone and an identifier that has no place in a tracked file.
    """
    from mutate_retention_drain import __file__ as harness_file
    from pathlib import Path

    # Both prefixes are ASSEMBLED rather than written out, so this file does not itself carry
    # the literal home-directory prefixes it forbids in the harness.
    banned = ("/" + "Users" + "/", "/" + "home" + "/")
    text = Path(harness_file).read_text(encoding="utf-8")
    for line_no, line in enumerate(text.splitlines(), 1):
        for prefix in banned:
            assert prefix not in line, (
                f"absolute home path at mutate_retention_drain.py:{line_no}: {line.strip()}"
            )
