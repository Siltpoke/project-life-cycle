"""Long-term records are not written by merging.

THE NOT-APPLICABLE PATH IS NOT EVIDENCE. This repository runs with no `mode` key, so the invariant
reports "not applicable" here and would do so forever. Every assertion below therefore builds a
throwaway git repository with `mode: fast` in its CLAUDE.md and runs the real script against it.
A guard proven only on the branch that cannot arm it is a guard nobody has run.

The acceptance test the criterion itself names is `test_ticking_nothing_writes_nothing`: produce a
phase with candidates, tick none, merge, and require every long-term file unchanged.
"""

import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
INVARIANT = ROOT / "scripts/invariants/longterm-candidates-not-in-diff.sh"
WRITER = ROOT / "skills/project-lifecycle/hooks/plc-longterm-write.sh"
PATHS_LIST = "docs/ROADMAP.md\ndocs/BACKLOG.md\nCLAUDE.md\n"  # the long-term record paths each fixture declares


def git(repo, *args, **kw):
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True, **kw
    )


@pytest.fixture
def repo(tmp_path):
    """A throwaway repo with a base commit, a `main`, and a feature branch off it."""
    r = tmp_path / "r"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    git(r, "config", "user.email", "t@example.invalid")
    git(r, "config", "user.name", "t")
    (r / "docs").mkdir()
    (r / "docs/ROADMAP.md").write_text("# roadmap\n", encoding="utf-8")
    (r / "CLAUDE.md").write_text("mode: fast\n", encoding="utf-8")
    (r / "src.txt").write_text("v1\n", encoding="utf-8"); (tmp_path / "longterm-record-paths.txt").write_text(PATHS_LIST, encoding="utf-8")
    git(r, "add", "-A")
    git(r, "commit", "-q", "-m", "base")
    git(r, "checkout", "-q", "-b", "feat/phase-x")
    return r


def run_invariant(repo, base="main"):
    env = {
        "LONGTERM_ROOT": str(repo),
        "LONGTERM_PATHS": str(repo.parent / "longterm-record-paths.txt"),
        "LONGTERM_CLAUDE_MD": str(repo / "CLAUDE.md"),
        "LONGTERM_BASE": base,
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
    }
    return subprocess.run(
        ["bash", str(INVARIANT)], capture_output=True, text=True, cwd=repo, env=env
    )


def test_an_ordinary_commit_passes(repo):
    (repo / "src.txt").write_text("v2\n", encoding="utf-8")
    git(repo, "commit", "-q", "-am", "change the product")
    p = run_invariant(repo)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "in the brief, not the diff" in p.stdout


def test_an_unauthorised_long_term_write_reds(repo):
    """The mutant that matters: the roadmap edited inside the feature branch, no trailer."""
    (repo / "docs/ROADMAP.md").write_text("# roadmap\n- a new standing rule\n", encoding="utf-8")
    git(repo, "commit", "-q", "-am", "quietly update the roadmap")
    p = run_invariant(repo)
    assert p.returncode == 1, p.stdout + p.stderr
    assert "on a feature branch" in p.stderr
    assert "docs/ROADMAP.md" in p.stderr
    assert "out of the diff entirely" in p.stderr


def test_a_trailer_does_not_exempt_a_commit_on_the_feature_branch(repo):
    """A trailer alone is not authorisation, and that is the criterion.

    Accepting any commit carrying the trailer would reduce "the candidates are
    not in this PR's diff" to "the commit that puts them there says it meant to". A trailer-bearing
    commit on the feature branch is STILL IN THE DIFF, so merging still writes it.
    """
    (repo / "docs/ROADMAP.md").write_text("# roadmap\n- a new standing rule\n", encoding="utf-8")
    git(repo, "commit", "-q", "-am", "update the roadmap\n\nLongterm-write: roadmap-entry-1")
    p = run_invariant(repo)
    assert p.returncode == 1, p.stdout + p.stderr
    assert "on a FEATURE branch" in p.stderr
    assert "still in the PR diff" in p.stderr


def test_the_rule_is_not_armed_outside_fast(repo):
    """And it SAYS it is not armed, rather than printing a clean-looking pass."""
    (repo / "CLAUDE.md").write_text("mode: detailed\n", encoding="utf-8")
    (repo / "docs/ROADMAP.md").write_text("# roadmap\n- anything\n", encoding="utf-8")
    git(repo, "commit", "-q", "-am", "roadmap under detailed")
    p = run_invariant(repo)
    assert p.returncode == 0
    assert "not applicable" in p.stdout
    assert "mode=detailed" in p.stdout


def test_ticking_nothing_writes_nothing(repo):
    """The acceptance test the criterion names, run end to end.

    A phase produces candidates, the user ticks none, the branch is merged. Every long-term record
    file must be byte-identical to what it was before.
    """
    before = (repo / "docs/ROADMAP.md").read_bytes()

    # A phase that learned something: the candidates go in the brief, NOT in the diff.
    (repo / "brief.md").write_text(
        "<!-- plc-brief-item: long-term -->\n- [ ] Add to the roadmap: a new standing rule\n",
        encoding="utf-8",
    )
    (repo / "src.txt").write_text("v2\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "the phase's actual work")

    assert run_invariant(repo).returncode == 0

    git(repo, "checkout", "-q", "main")
    git(repo, "merge", "-q", "--no-ff", "-m", "merge", "feat/phase-x")

    assert (repo / "docs/ROADMAP.md").read_bytes() == before, (
        "merging wrote a long-term record that nobody ticked"
    )


def test_the_writer_refuses_when_nothing_was_ticked(repo):
    p = subprocess.run(
        ["bash", str(WRITER), "--brief", "/dev/null"],
        capture_output=True, text=True, cwd=repo,
    )
    assert p.returncode != 0
    assert "nothing was selected" in p.stderr


def test_the_writer_commits_only_ticked_entries(repo):
    brief = repo / "brief.md"
    brief.write_text(
        "<!-- plc-brief-item: long-term -->\n"
        "- [x] docs/ROADMAP.md :: a rule the user ticked\n"
        "- [ ] docs/ROADMAP.md :: a rule the user did not tick\n",
        encoding="utf-8",
    )
    p = subprocess.run(
        ["bash", str(WRITER), "--brief", str(brief)],
        capture_output=True, text=True, cwd=repo,
    )
    assert p.returncode == 0, p.stdout + p.stderr
    body = (repo / "docs/ROADMAP.md").read_text(encoding="utf-8")
    assert "a rule the user ticked" in body
    assert "did not tick" not in body
    trailer = git(repo, "log", "-1", "--format=%(trailers:key=Longterm-write,valueonly)").stdout
    assert trailer.strip(), "the writer's own commit must carry the authorising trailer"
