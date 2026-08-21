"""The phase record says which mode ran, where it came from, and (under
`fast`) carries exactly one blind review.

Every assertion is proved against a fixture fragment. The real fragment is one document in one
state; a guard tested only against it has been shown to accept that state and nothing else.
"""

import os
import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
INV = ROOT / "scripts/invariants/mode-provenance-recorded.sh"

GOOD = "mode: detailed | source: project-default | confirmed-at: explicit\n"


def run(tmp_path, fragment_text, mode=None):
    frag = tmp_path / "frag.md"
    frag.write_text(fragment_text, encoding="utf-8")
    claude = tmp_path / "CLAUDE.md"
    claude.write_text(f"mode: {mode}\n" if mode else "# nothing\n", encoding="utf-8")
    env = dict(os.environ)
    env.update({
        "PROVENANCE_ROOT": str(tmp_path),
        "PROVENANCE_FRAGMENT": str(frag),
        "PROVENANCE_CLAUDE_MD": str(claude),
    })
    return subprocess.run(
        ["bash", str(INV)], capture_output=True, text=True, cwd=tmp_path, env=env
    )


def test_a_well_formed_record_passes(tmp_path):
    """Positive control."""
    p = run(tmp_path, GOOD)
    assert p.returncode == 0, p.stdout + p.stderr


def test_a_missing_provenance_line_reds(tmp_path):
    """Without it, 'which mode did this run in' has no answer."""
    p = run(tmp_path, "# a fragment with no provenance line\n")
    assert p.returncode == 1
    assert "P1:" in p.stderr and "no provenance line" in p.stderr


def test_an_unrecognised_source_is_named_not_ignored(tmp_path):
    """An unmatched value must never fall through silently."""
    p = run(tmp_path, "mode: fast | source: inherited | confirmed-at: kickoff\n")
    assert p.returncode == 1
    assert "P1:" in p.stderr and "'inherited' is not one of" in p.stderr


def test_two_default_confirmations_red(tmp_path):
    """`fast` raises the mode once per phase. Twice means it asked again."""
    p = run(tmp_path, GOOD + GOOD)
    assert p.returncode == 1
    assert "P2:" in p.stderr and "raised more than once" in p.stderr


def test_an_override_alongside_a_default_is_legal(tmp_path):
    """A genuine mid-phase change is recorded as a second line carrying `override`.

    This is the case the 'exactly one' rule must NOT reject: the second line IS the record of the
    change, and rejecting it would push a real event out of the record to satisfy a counter.
    """
    text = GOOD + "mode: detailed | source: override | confirmed-at: explicit\n"
    p = run(tmp_path, text)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "1 default confirmation" in p.stdout


def test_a_fast_phase_with_no_blind_review_reds(tmp_path):
    """The quick setting reduces the blind review's frequency, never to zero."""
    p = run(tmp_path, "mode: fast | source: project-default | confirmed-at: kickoff\n", mode="fast")
    assert p.returncode == 1
    assert "P4:" in p.stderr and "never to zero" in p.stderr


def test_a_fast_phase_with_two_blind_reviews_reds(tmp_path):
    """Two is the full setting's frequency leaking into the quick one -- a different defect."""
    text = (
        "mode: fast | source: project-default | confirmed-at: kickoff\n"
        "blind-review: round 1\nblind-review: round 2\n"
    )
    p = run(tmp_path, text, mode="fast")
    assert p.returncode == 1
    assert "P4:" in p.stderr and "leaking" in p.stderr


def test_a_fast_phase_with_exactly_one_blind_review_passes(tmp_path):
    text = (
        "mode: fast | source: project-default | confirmed-at: kickoff\n"
        "blind-review: no findings\n"
    )
    p = run(tmp_path, text, mode="fast")
    assert p.returncode == 0, p.stdout + p.stderr


def test_the_blind_review_rule_is_not_armed_outside_fast(tmp_path):
    p = run(tmp_path, GOOD, mode="detailed")
    assert p.returncode == 0
    assert "P4 not applicable" in p.stdout


def _phase_repo(tmp_path, add_phase_docs: bool):
    """A throwaway repo with a `main` and a branch off it, optionally adding phase documents."""
    r = tmp_path / "r"
    r.mkdir()
    for args in (
        ["init", "-q", "-b", "main"],
        ["config", "user.email", "t@example.invalid"],
        ["config", "user.name", "t"],
    ):
        subprocess.run(["git", "-C", str(r), *args], check=True, capture_output=True)
    (r / "seed.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(r), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(r), "commit", "-qm", "base"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(r), "checkout", "-qb", "work"], check=True, capture_output=True)

    if add_phase_docs:
        d = r / "docs/superpowers/specs"
        d.mkdir(parents=True)
        (d / "2026-08-19-phase-bxxx-something-design.md").write_text("# spec\n", encoding="utf-8")
    else:
        (r / "docs").mkdir(parents=True, exist_ok=True)
        (r / "docs/ROADMAP.md").write_text("# roadmap\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(r), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(r), "commit", "-qm", "work"], check=True, capture_output=True)
    return r


def _run_in(repo):
    env = dict(os.environ)
    env.update({
        "PROVENANCE_ROOT": str(repo),
        "PROVENANCE_QA_DIR": str(repo / "docs/qa-log.d"),
        "PROVENANCE_CLAUDE_MD": str(repo / "CLAUDE.md"),
        "PROVENANCE_BASE": "main",
    })
    return subprocess.run(["bash", str(INV)], capture_output=True, text=True, cwd=repo, env=env)


def test_a_branch_that_is_not_a_phase_is_not_applicable(tmp_path):
    """A chore branch stamping a merged PR
    into the roadmap must not be BLOCKED by this file: it has no Q&A fragment and never should.

    close-gate's invariant runner reads exit STATUS only, so a verdict 3 blocks exactly like
    a 1 -- a check firing where nothing was configured.
    """
    p = _run_in(_phase_repo(tmp_path, add_phase_docs=False))
    assert p.returncode == 0, p.stdout + p.stderr
    assert "not applicable" in p.stdout
    assert "not a phase working branch" in p.stdout


def test_a_phase_branch_with_no_fragment_still_cannot_run(tmp_path):
    """The half that matters: the escape must not swallow a real phase that forgot its record."""
    p = _run_in(_phase_repo(tmp_path, add_phase_docs=True))
    assert p.returncode == 3, p.stdout + p.stderr
    assert "adds phase documents but no Q&A log fragment" in p.stderr
    assert "2026-08-19-phase-bxxx-something-design.md" in p.stderr


def test_a_tree_that_is_not_a_git_work_tree_is_could_not_run(tmp_path):
    """NARROWED, and the narrowing is recorded rather than the old row quietly deleted.

    This used to assert that ANY missing fragment was COULD NOT RUN. That was too wide -- it is
    what blocked the chore branch above -- so "missing fragment" now splits: a phase branch owes a
    record (verdict 3, asserted by test_a_phase_branch_with_no_fragment_still_cannot_run), any other
    branch does not (verdict 0). What survives from the original row is the case where the check
    genuinely cannot look: no git work tree at all, so no branch, so nothing to resolve a fragment
    from. That is still 3 and still must not read as clean.
    """
    env = dict(os.environ)
    env.update({
        "PROVENANCE_ROOT": str(tmp_path),
        "PROVENANCE_QA_DIR": str(tmp_path / "nowhere"),
        "GIT_CEILING_DIRECTORIES": str(tmp_path.parent),
    })
    p = subprocess.run(["bash", str(INV)], capture_output=True, text=True, cwd=tmp_path, env=env)
    assert p.returncode == 3, p.stdout + p.stderr
    assert "COULD NOT RUN" in p.stderr
