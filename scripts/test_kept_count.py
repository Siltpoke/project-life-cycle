"""p30:AC3 -- the kept-count is derived, and BOTH gate homes derive it the same way.

No CJK in this file, deliberately. The CJK rule exempts `docs/` outright and nothing
else, so every byte under `scripts/` is ASCII.

WHY THESE TESTS AND NOT A PINNED DIGEST. The one-time property actually needed was "the
refactor did not change `evidence_digest`'s output". That was measured live, old code against new
code over the same tree, and both returned 21fd6c767cbeef1f88d01153849e771cef16dacd (and the
zero-match sentinel path matched too). It is NOT reproduced here as a pinned constant: freezing a
derived value into a literal is the assertion shape this repo filed, where a pin computed
from the thing it was meant to guard turned every honest change into a false regression. What is
pinned below is behaviour that stays true as the tree grows -- agreement between the two homes,
agreement with an independent count, and which sentinel belongs to which empty case.

THE TWO HOMES ARE TWO ARTIFACTS. `scripts/close-gate.sh` and the fenced script inside
`skills/project-lifecycle/references/close-gate.md` cannot share source. an earlier task factored the
pathspec resolution in each of them separately, with the same function names and contract. What
must never differ is the ANSWER, which is what `test_both_homes_agree_*` exists to catch -- a
one-home edit is the failure mode cross-check agent B found in p30's own plan.
"""

import os
import pathlib
import re
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from close_gate_lib import extract_gate_script  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parent.parent
GATE_MD = REPO / "skills" / "project-lifecycle" / "references" / "close-gate.md"
GATE_SH = REPO / "scripts" / "close-gate.sh"

FN_NAMES = ("evidence_matched_files", "evidence_kept_count")


def _home_sources():
    return {
        "canonical": extract_gate_script(GATE_MD),
        "variant": GATE_SH.read_text(encoding="utf-8"),
    }


def _extract_fns(src, home):
    """Pull the two functions out of a gate's source as text.

    Deliberately textual: the point is to exercise the SHIPPED bytes of each home, not a
    re-implementation of them. A test that reasoned about what the functions do instead of running
    them would pass against a home that no longer contains them at all.
    """
    out = []
    for name in FN_NAMES:
        m = re.search(rf"^{name}\(\).*?(?:^\}}$|;\s*\}}$)", src, re.S | re.M)
        assert m, f"{home}: {name}() not found -- did a home lose the p30 factoring?"
        out.append(m.group(0))
    return "\n".join(out)


def _run_count(home, src, inputs, tree):
    """Run one home's evidence_kept_count() against `inputs` inside `tree`."""
    manifest = tree / ".claude" / "close-gate.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        '{"test_evidence_inputs": [%s], "test_command": "true", '
        '"test_evidence": ".claude/e"}' % ", ".join('"%s"' % i for i in inputs),
        encoding="utf-8",
    )
    harness = (
        'M=".claude/close-gate.json"\n'
        'GATE_RELEVANT_PATHS="$(jq -r \'.test_evidence_inputs[]\' "$M" 2>/dev/null || true)"\n'
        + _extract_fns(src, home)
        + "\nevidence_kept_count\n"
    )
    script = tree / f"probe-{home}.sh"
    script.write_text(harness, encoding="utf-8")
    r = subprocess.run(
        ["bash", str(script)], cwd=str(tree), capture_output=True, text=True
    )
    assert r.returncode == 0, f"{home}: probe exited {r.returncode}: {r.stderr[:400]}"
    return r.stdout.strip()


@pytest.fixture
def tree():
    """A tiny real git repo. Real, because `git ls-files` only sees tracked files."""
    with tempfile.TemporaryDirectory() as d:
        t = pathlib.Path(d)
        subprocess.run(["git", "init", "-q"], cwd=str(t), check=True)
        subprocess.run(
            ["git", "config", "user.email", "t@example.invalid"], cwd=str(t), check=True
        )
        subprocess.run(["git", "config", "user.name", "t"], cwd=str(t), check=True)
        (t / "a.md").write_text("a\n", encoding="utf-8")
        (t / "b.md").write_text("b\n", encoding="utf-8")
        (t / "sub").mkdir()
        (t / "sub" / "c.md").write_text("c\n", encoding="utf-8")
        (t / "d.txt").write_text("d\n", encoding="utf-8")
        (t / "untracked.md").write_text("u\n", encoding="utf-8")
        subprocess.run(["git", "add", "a.md", "b.md", "sub/c.md", "d.txt"],
                       cwd=str(t), check=True)
        subprocess.run(["git", "commit", "-qm", "seed"], cwd=str(t), check=True)
        yield t


@pytest.mark.parametrize("home", ["canonical", "variant"])
@pytest.mark.parametrize(
    "inputs,expected",
    [
        (["*.md"], "3"),          # recursive pathspec: a.md, b.md, sub/c.md -- NOT untracked.md
        (["d.txt"], "1"),         # a second, differently-shaped set
        (["no/such/**"], "0"),    # matches nothing
    ],
)
def test_kept_count_matches_reality(home, inputs, expected, tree):
    """The derived count equals what git actually reports -- per home, on 3 pathspec sets.

    `untracked.md` exists on disk and is NOT counted. That is the whole point of the number: it
    describes the tracked surface the fingerprint covers, not the directory listing.
    """
    src = _home_sources()[home]
    assert _run_count(home, src, inputs, tree) == expected


@pytest.mark.parametrize("inputs", [["*.md"], ["d.txt"], ["no/such/**"], ["*.md", "d.txt"]])
def test_both_homes_agree(inputs, tree):
    """Two artifacts, two factorings, one answer.

    This is the assertion cross-check agent B's CRITICAL finding produced: p30's plan originally
    factored one home and left the other to invent its own resolution.
    """
    srcs = _home_sources()
    canonical = _run_count("canonical", srcs["canonical"], inputs, tree)
    variant = _run_count("variant", srcs["variant"], inputs, tree)
    assert canonical == variant, (
        f"homes disagree on {inputs}: canonical={canonical} variant={variant}"
    )


@pytest.mark.parametrize("home", ["canonical", "variant"])
def test_digest_and_count_read_the_same_resolution(home, tree):
    """A zero count and the digest's zero-match sentinel must agree with each other.

    If they could disagree, there would be two resolutions again -- the count saying "0 files" while
    the digest happily fingerprints something, or the reverse. Running both against the same tree is
    what makes "one resolution" a measured property rather than a claim about the source.
    """
    src = _home_sources()[home]
    assert _run_count(home, src, ["no/such/**"], tree) == "0"
    assert _run_count(home, src, ["*.md"], tree) != "0"


def test_canonical_keeps_its_two_distinct_sentinels():
    """The canonical gate distinguishes "nothing declared" from "declared, matched nothing".

    The variant deliberately folds both into one sentinel and always has; p30 did not change that,
    because splitting it would alter row 7's output for an adopter who never asked. This test pins
    the asymmetry so a later reader does not "tidy" the two homes into agreement and silently change
    one gate's reporting.
    """
    src = _home_sources()["canonical"]
    assert "EMPTY-no-test-evidence-inputs-declared" in src
    assert "EMPTY-no-test-evidence-inputs-matched" in src
    variant = _home_sources()["variant"]
    assert "EMPTY-no-gate-relevant-paths-matched" in variant
    assert "EMPTY-no-test-evidence-inputs-declared" not in variant


def test_a_tracked_path_containing_a_newline_is_counted_once(tree):
    """One file, not two -- the reason the count reads NUL delimiters instead of lines.

    ADDED BY A SURVIVING MUTANT, not by foresight. The first version of this file carried a comment
    saying "counts NUL delimiters rather than lines: a path may contain a newline and `wc -l` would
    then over-count" and shipped no test for it: swapping the implementation to
    `tr '\\000' '\\n' | wc -l` left all 13 tests green. A claim wider than the mechanism backing it,
    inside the phase about that exact class. The fixture below is what makes the comment true.
    """
    weird = tree / "we\nird.md"
    weird.write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "--", str(weird)], cwd=str(tree), check=True)
    subprocess.run(["git", "commit", "-qm", "newline"], cwd=str(tree), check=True)
    srcs = _home_sources()
    # a.md, b.md, sub/c.md, and the newline-bearing one == 4 files, however many lines that prints
    for home in ("canonical", "variant"):
        assert _run_count(home, srcs[home], ["*.md"], tree) == "4", (
            f"{home} miscounted a path containing a newline"
        )


@pytest.mark.parametrize("home", ["canonical", "variant"])
def test_an_empty_input_list_counts_zero_not_everything(home, tree):
    """No pathspecs must mean "match nothing", never "match the whole tracked tree".

    ALSO ADDED BY A SURVIVING MUTANT. Deleting the `[ "$#" -gt 0 ] || return 0` guard left every
    test green, because every fixture passed at least one pathspec and the guard was never reached.
    `git ls-files --` with zero pathspecs after the separator matches EVERY tracked file, so without
    this the fingerprint would silently cover the whole repo -- the silent-degrade closed earlier, which
    would have been reopened here with a full green board.
    """
    src = _home_sources()[home]
    assert _run_count(home, src, [], tree) == "0"
