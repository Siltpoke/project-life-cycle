"""Controls for `scripts/skill_duplication_census.py`.

WHAT THESE ROWS DO AND DO NOT COVER, because the difference is the whole history of this file.

Earlier versions of this suite asserted a published calibration -- that light edits land in one
band, heavy paraphrase in another, and that no original passage is ever admitted. Every one of
those claims turned out false:

  * the "no false positives" row drew its negative population by removing a passage's own
    source file from the index and calling the rest original. Two reference files here share a
    verbatim block, so 26 of 50 seeds put a genuine duplicate into that population and the row
    fails. It passed on seed 11. A row that depends on a seed is not a control.
  * the band rows simulated editing by DELETING one word in seven or four. Deletion breaks only
    the shingles straddling the gap; substitution at the same rate breaks every shingle
    containing the word and drops the light band from 100% admitted to 15-26%. The rows
    measured the edit model, not the metric.
  * both were calibrated on paragraphs of 80+ words, while 80% of real SKILL.md units are
    shorter -- the population where the metric is most volatile was never tested.

So the probe was downgraded to a candidate generator, and this suite was cut to match. It now
tests only MECHANICS -- things that are true or false about the code regardless of what any
corpus looks like. There is deliberately no row asserting a duplication rate, a false-positive
rate, or a band boundary, because nothing in this repo can honestly establish one.

Every row below is checked by at least one mutant that swaps the real implementation.
`shingles()` resolves k at call time so that mutation is real rather than frozen at import.
"""
from __future__ import annotations

import random
import textwrap
from pathlib import Path

import pytest

import skill_duplication_census as census

REPO = Path(__file__).resolve().parent.parent
REF_DIR = REPO / "skills" / "project-lifecycle" / "references"
SKILL = REPO / "skills" / "project-lifecycle" / "SKILL.md"


# --------------------------------------------------------------------------------------
# Fixture trees
# --------------------------------------------------------------------------------------

REF_BODY = textwrap.dedent(
    """\
    # Retention contract

    The drain moves bytes verbatim from the hot document into the dated archive file, and
    leaves a pointer stub behind naming the archive it went to, so a reader who follows the
    stub lands on the exact text that used to be here rather than on a summary of it.
    """
)

ORIGINAL_SKILL = textwrap.dedent(
    """\
    # Test Skill

    ## Conventions

    - **Never work on the trunk branch** -- cut one branch per milestone so that an
      unfinished change is never one keystroke away from everybody else's checkout.

    ## References

    - `references/retention.md` -- retention contract
    """
)

PLANTED = (
    "- The drain moves bytes verbatim from the hot document into the dated archive file, "
    "and leaves a pointer stub behind naming the archive it went to, so a reader who "
    "follows the stub lands on the exact text that used to be here."
)


def _make_tree(root: Path, skill_body: str, refs: dict[str, str] | None = None) -> Path:
    pkg = root / "skills" / "project-lifecycle"
    (pkg / "references").mkdir(parents=True)
    for name, body in (refs or {"retention.md": REF_BODY}).items():
        (pkg / "references" / name).write_text(body, encoding="utf-8")
    (pkg / "SKILL.md").write_text(skill_body, encoding="utf-8")
    return root


SCATTER_BLOCKS = [
    "the close gate blocks a push",
    "when the journal fragment is missing",
    "and the changelog entry was never",
    "written into the unreleased section above",
    "so the roadmap row stays stale",
    "until somebody reads the whole thing",
]
# Same words, same 3-word windows, blocks reordered: shingle containment 71% (well over the
# shortlist) while the longest consecutive run is 6 of 36 words (17%, under MIN_RUN). This is
# the shape shingle containment cannot distinguish from a duplicate on its own, and the reason
# the run column exists.
SCATTER_REF = " ".join(SCATTER_BLOCKS)
SCATTER_SKILL = " ".join(SCATTER_BLOCKS[i] for i in (3, 0, 5, 1, 4, 2))


def _scatter_tree(root):
    return _make_tree(root, f"# T\n\n## G\n\n- {SCATTER_SKILL}\n",
                      {"g.md": SCATTER_REF + "\n"})


# --------------------------------------------------------------------------------------
# Does it find a real duplicate, and stay quiet otherwise?
# --------------------------------------------------------------------------------------

def test_clean_fixture_yields_no_candidates(tmp_path):
    """Control for the plant below. Without it, a hit proves only that something was hit."""
    root = _make_tree(tmp_path / "clean", ORIGINAL_SKILL)
    *_, units, _, _ = census.run(root)
    assert [u for u in units if u.is_candidate] == []


def test_planted_duplicate_is_found_attributed_and_carries_its_evidence(tmp_path):
    root = _make_tree(tmp_path / "planted",
                      ORIGINAL_SKILL.replace("## References", PLANTED + "\n\n## References"))
    *_, units, _, _ = census.run(root)
    cands = [u for u in units if u.is_candidate]
    assert len(cands) == 1, [u.text[:40] for u in cands]
    assert cands[0].target == "retention.md"
    assert cands[0].run_fraction >= 0.9, (
        f"run fraction {cands[0].run_fraction:.0%} — the evidence column is what a reader "
        f"checks instead of the score, so a verbatim plant must show a near-total run"
    )


def test_shared_vocabulary_without_a_consecutive_run_is_not_shortlisted(tmp_path):
    """The MIN_RUN gate, exercised by a passage that DOES clear the shingle shortlist.

    An earlier version of this row used a fixture scoring 35% -- below the shortlist -- so it
    passed without ever reaching the gate it claimed to test, and the mutant below said so.
    """
    root = _scatter_tree(tmp_path / "scattered")
    *_, units, _, _ = census.run(root)
    body = max(units, key=lambda u: u.nbytes)
    assert body.score >= census.SHORTLIST, (
        f"fixture only scored {body.score:.0%}; it must clear the shortlist or this row "
        f"never reaches MIN_RUN"
    )
    assert body.run_fraction < census.MIN_RUN
    assert not body.is_candidate


def test_a_heading_is_shortlisted_and_left_for_the_reader_to_reject(tmp_path):
    """The probe deliberately does NOT filter headings any more.

    The previous filter was `text.startswith("#")`, which excluded genuine prose beginning
    with a hash and admitted Setext headings written with an underline. Rather than build a
    markdown parser to support a judgement the probe should not be making, headings are
    shortlisted like anything else and a person rejects them in a second. This row pins that
    choice so it is not silently reverted into a half-correct filter.
    """
    root = _make_tree(tmp_path / "heading",
                      "# Retention contract policy\n\n## S\n\nunrelated words entirely here\n",
                      {"r.md": "# Retention contract policy\n\nbody text here now\n"})
    *_, units, _, _ = census.run(root)
    assert any(u.is_candidate and u.text.startswith("#") for u in units)


# --------------------------------------------------------------------------------------
# Coverage: an identity, and the categories must be right, not just balanced
# --------------------------------------------------------------------------------------

SHAPES = [
    "",
    "a\n",
    "a",
    "# T\n\n## A\n\nhello world here\n",
    "# T\n\n## A\n\nhello world here",
    "- one\n- two\n",
    "x\n   \n   \ny\n",
    "# T\n\n```\n## Fake\n- bullet\n```\n\nreal\n",
    "| a | b |\n|---|---|\n| 1 | 2 |\n",
    "# Title\n\n## Section\n\n### Sub\n\nBody words here now\n",
]


@pytest.mark.parametrize("body", SHAPES, ids=range(len(SHAPES)))
def test_coverage_residue_is_exactly_zero(tmp_path, body):
    """An earlier version charged every unit a trailing separator byte including the last, so
    residue was -1 on EVERY input -- a negative count of bytes not looked at. The old
    assertion (`0 <= residue < 0.001 * total`) could not see it because it only ran against
    this repo, where a larger positive error hid it."""
    root = _make_tree(tmp_path / f"cov{abs(hash(body))}", body, {"r.md": "x y z"})
    _, _, _, _, lines, category = census.run(root)
    total, per_cat, residue = census.coverage(lines, category)
    assert residue == 0, f"residue {residue} on {body!r}: {per_cat}"
    assert total == len((root / "skills/project-lifecycle/SKILL.md").read_bytes())


def test_every_heading_level_is_categorised_as_heading_not_prose(tmp_path):
    """The identity can balance while the buckets are wrong, which is worse than a non-zero
    residue because the report prints 0 as proof. `#` and `###` lines used to land in the
    prose bucket while being excluded from results, so 'prose bytes' included headings."""
    root = _make_tree(tmp_path / "levels",
                      "# Title\n\n## Section\n\n### Sub\n\nBody words here now\n",
                      {"r.md": "x y z"})
    _, _, _, _, lines, category = census.run(root)
    for line, cat in zip(lines, category):
        if line.lstrip().startswith("#"):
            assert cat == "heading", f"{line!r} categorised {cat}"


def test_coverage_residue_is_zero_on_the_real_skill():
    _, _, _, _, lines, category = census.run(REPO)
    assert census.coverage(lines, category)[2] == 0


# --------------------------------------------------------------------------------------
# Structure and blind spots
# --------------------------------------------------------------------------------------

def test_fenced_code_does_not_fabricate_a_section(tmp_path):
    body = ("# T\n\n## Output Format\n\nThe tool prints:\n\n```\n"
            "## Nested Example Heading\n- alpha\n- beta\n```\n\nThat is all.\n")
    root = _make_tree(tmp_path / "fenced", body)
    *_, units, _, _ = census.run(root)
    assert {u.section for u in units} == {"(preamble)", "Output Format"}


def test_text_the_metric_cannot_see_is_flagged_not_scored_zero(tmp_path, capsys):
    """A byte-identical non-ASCII duplicate scores 0% and would otherwise be reported clean.

    The fixture is Greek, not CJK: any text the metric cannot see will do, and
    Greek exercises the same code path. The assertion below is what makes
    that claim true rather than assumed -- if the string is later edited into something the
    regex CAN see, this row says so instead of passing for the wrong reason.
    """
    foreign = ("αρχειοθετηση πολιτικης διατηρησης "
               "και μεταφορας δεδομενων στο αρχειο")
    assert not census.words(foreign), "fixture must be invisible to the word regex"
    root = _make_tree(tmp_path / "foreign", f"# T\n\n## P\n\n{foreign}\n",
                      {"p.md": f"# P\n\n{foreign}\n"})
    census.report(root)
    out = capsys.readouterr().out
    assert "WARNING" in out and "byte-identical copy" in out


def test_the_warning_does_not_fire_on_merely_short_units(tmp_path, capsys):
    """That warning's first version fired on a two-word heading while announcing 'no ASCII
    letters or digits' -- a message wider than its trigger."""
    root = _make_tree(tmp_path / "short-units",
                      "# T\n\n## A\n\n### Documentation & traceability\n\nreal words here now\n")
    census.report(root)
    assert "byte-identical copy" not in capsys.readouterr().out


def test_score_credits_one_file_and_never_sums_across_the_tree(tmp_path):
    """A union across files reaches 100% on a passage assembled from windows that each live in
    a different document, while the passage exists nowhere. A union score used to be computed
    and published as 'content present somewhere in the tree'; it is gone, and this row keeps
    it gone."""
    a = "the drain moves bytes verbatim from the hot document"
    b = "and leaves a pointer stub behind naming the archive"
    root = _make_tree(tmp_path / "twofiles", f"# T\n\n## P\n\n{a} {b}\n",
                      {"a.md": a + "\n", "b.md": b + "\n"})
    *_, units, _, _ = census.run(root)
    passage = max(units, key=lambda u: u.nbytes)
    assert passage.score < 0.85, (
        f"score {passage.score:.0%}: a passage split across two files must not score as if "
        f"one file held all of it"
    )


# --------------------------------------------------------------------------------------
# Contract
# --------------------------------------------------------------------------------------

def test_root_argument_points_the_probe_away_from_this_repo(tmp_path):
    root = _make_tree(tmp_path / "elsewhere", ORIGINAL_SKILL)
    skill, *_ = census.run(root)
    assert skill == root / "skills" / "project-lifecycle" / "SKILL.md"
    assert REPO not in skill.parents


def test_missing_skill_is_an_error_not_an_empty_pass(tmp_path):
    (tmp_path / "skills" / "project-lifecycle" / "references").mkdir(parents=True)
    with pytest.raises(SystemExit):
        census.run(tmp_path)


def test_probe_reads_its_inputs_and_writes_nothing(tmp_path):
    """Absence of writes AND presence of a real read. The mtime comparison alone passed
    against `run = lambda root: None` -- an absence assertion that a run which never happened
    also satisfies."""
    root = _make_tree(tmp_path / "readonly", ORIGINAL_SKILL)
    before = {p: p.stat().st_mtime_ns for p in root.rglob("*") if p.is_file()}
    *_, units, lines, category = census.run(root)
    after = {p: p.stat().st_mtime_ns for p in root.rglob("*") if p.is_file()}
    assert before == after
    assert len(units) >= 3 and any(u.section == "Conventions" for u in units)
    assert "prose" in category and len(lines) > 5


def test_report_states_that_its_figures_are_not_measurements(capsys):
    """The probe's headline restraint is load-bearing and therefore asserted. Over-claims
    have crept into this file before; another must not be able to
    creep back into the summary line without a red row."""
    census.report(REPO)
    out = capsys.readouterr().out
    assert "CANDIDATES, not verdicts" in out
    assert "Neither figure is a measurement of duplication" in out


# --------------------------------------------------------------------------------------
# Mutants
# --------------------------------------------------------------------------------------

def test_mutant_k8_collapses_the_shortlist(monkeypatch):
    """The original defect: an eight-word window is destroyed by one edited word, so
    near-verbatim matches vanish. If this passes, the mutation is not reaching the code."""
    monkeypatch.setattr(census, "SHINGLE_K", 8)
    idx = census.build_index(REF_DIR)
    edited = " ".join(
        w for i, w in enumerate(
            (REF_DIR / "cadence.md").read_text().split()[:200]) if i % 7 != 3)
    assert census.score(edited, idx)[0] < census.SHORTLIST


def test_mutant_bag_of_words_reddens_the_scattered_row(monkeypatch, tmp_path):
    """k=1 turns the metric into vocabulary overlap, which is exactly what the MIN_RUN gate
    and the scattered-vocabulary row exist to survive."""
    monkeypatch.setattr(census, "SHINGLE_K", 1)
    seq = census.words(SKILL.read_text(encoding="utf-8"))
    random.Random(1).shuffle(seq)
    assert census.score(" ".join(seq[:400]), census.build_index(REF_DIR))[0] >= 0.05


def test_mutant_no_min_run_admits_the_scattered_passage(monkeypatch, tmp_path):
    """Dropping the evidence gate must let scattered vocabulary through, or MIN_RUN is
    decoration and the run column is not doing the work this file says it does."""
    root = _scatter_tree(tmp_path / "minrun")
    monkeypatch.setattr(census, "MIN_RUN", 0.0)
    *_, units, _, _ = census.run(root)
    body = max(units, key=lambda u: u.nbytes)
    assert body.is_candidate, (
        f"score {body.score:.0%} run {body.run_fraction:.0%} — with MIN_RUN removed this "
        f"passage must be shortlisted, otherwise the gate was never what excluded it"
    )

def test_score_needs_shared_ORDER_not_merely_shared_vocabulary(tmp_path):
    """Kills the k=1 mutant, which no other row detected.

    With k=1 the metric degenerates to vocabulary overlap. The scattered fixture does not
    catch that -- MIN_RUN excludes it either way -- so without this row a unigram metric ships
    green. Here the two texts share every word and no 3-word window at all.
    """
    ref = "gate journal changelog roadmap push fragment section stale entry missing"
    skill = "missing entry stale section fragment push roadmap changelog journal gate"
    root = _make_tree(tmp_path / "order", f"# T\n\n## G\n\n- {skill}\n", {"g.md": ref + "\n"})
    *_, units, _, _ = census.run(root)
    body = max(units, key=lambda u: u.nbytes)
    assert body.score < census.SHORTLIST, (
        f"score {body.score:.0%} on text sharing 100% of its vocabulary and 0% of its "
        f"3-word windows — the metric has become a bag of words"
    )


def test_a_near_verbatim_duplicate_still_clears_the_run_gate(tmp_path):
    """Kills the MIN_RUN=0.99 mutant, which no other row detected.

    Every other row uses either an exact plant (run ~100%, survives any gate) or scattered
    vocabulary (excluded anyway), so a gate tightened to near-exact would have shipped green
    while silently dropping every real duplicate that is not byte-identical.
    """
    shared = ("the drain moves bytes verbatim from the hot document into the dated archive "
              "file and leaves a pointer stub behind naming the archive it went to so a "
              "reader who follows the stub lands on the exact text")
    root = _make_tree(
        tmp_path / "nearverbatim",
        f"# T\n\n## P\n\n- {shared}, then writes a short note for whoever\n",
        {"d.md": shared + " that used to be here\n"})
    *_, units, _, _ = census.run(root)
    body = max(units, key=lambda u: u.nbytes)
    assert 0.25 <= body.run_fraction < 0.99, (
        f"fixture run fraction {body.run_fraction:.0%} is outside the band this row defends; "
        f"it must be a partial overlap, not an exact copy"
    )
    assert body.is_candidate, (
        f"a passage sharing {body.run_fraction:.0%} of its words as one consecutive run must "
        f"be shortlisted — a gate that only admits exact copies finds nothing real"
    )


def test_the_shingle_shortlist_can_veto_a_long_consecutive_run(tmp_path):
    """A property found while building the row above, recorded rather than smoothed over.

    A passage sharing 14 of its 25 words (56%) as ONE consecutive run scores 52% on shingle
    containment and is therefore NOT shortlisted: the score gate binds before the evidence
    gate. So the shortlist is not a superset of "obviously worth reading" -- short passages
    with a real partial overlap fall out. That is a reason the printed list is a reading queue
    rather than a total, and it is asserted here so nobody later reads the shortlist as
    exhaustive.
    """
    shared = ("the drain moves bytes verbatim from the hot document into the dated "
              "archive file")
    root = _make_tree(
        tmp_path / "vetoed",
        f"# T\n\n## P\n\n- {shared}, then writes a short note for whoever comes later\n",
        {"d.md": shared + " and leaves a pointer stub behind naming the archive\n"})
    *_, units, _, _ = census.run(root)
    body = max(units, key=lambda u: u.nbytes)
    assert body.run_fraction >= 0.50, f"run {body.run_fraction:.0%}"
    assert body.score < census.SHORTLIST, f"score {body.score:.0%}"
    assert not body.is_candidate
