"""The iCloud conflict-copy guard, and the class it used to be blind to.

The guard used to scan `git ls-files` and therefore saw TRACKED FILES ONLY. Conflict copies inside
a gitignored directory — a copy of an append-only ledger, a journal archive — stayed invisible, because
`git ls-files` reports nothing about ignored or untracked paths.

`test_a_copy_inside_a_gitignored_directory_is_caught` is the regression guard for exactly that.
Reverting the scan to `git ls-files` makes it, and only it, go green when it should be red — which
is why it asserts the FAIL itself rather than some property of the output.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUARD = ROOT / "scripts" / "invariants" / "no-icloud-conflict-copies.sh"


def _repo(tmp_path: Path) -> Path:
    """A real git repo, because the guard resolves its root with `git rev-parse`."""
    r = tmp_path / "repo"
    (r / "docs").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(r)], check=True)
    (r / ".gitignore").write_text("docs/\n", encoding="utf-8")
    (r / "real.md").write_text("real\n", encoding="utf-8")
    (r / "docs" / "note.md").write_text("note\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(r), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(r), "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", "base"],
        check=True,
    )
    return r


def _run(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(GUARD)], cwd=str(repo), capture_output=True, text=True, check=False
    )


def test_a_clean_repo_passes(tmp_path: Path) -> None:
    """The control. Without it every FAIL below could be the guard being broken outright."""
    res = _run(_repo(tmp_path))
    assert res.returncode == 0, f"a clean repo was reported dirty:\n{res.stdout}{res.stderr}"


def test_a_copy_inside_a_gitignored_directory_is_caught(tmp_path: Path) -> None:
    """THE regression guard. This is the case a tracked-files-only scan leaves invisible for as
    long as it lasts: inside a gitignored `docs/`, `git ls-files` can never name anything."""
    r = _repo(tmp_path)
    (r / "docs" / "note 2.md").write_text("stale\n", encoding="utf-8")
    res = _run(r)
    assert res.returncode == 1, "a copy in a gitignored directory was not reported"
    assert "docs/note 2.md" in res.stdout, f"the offending path was not named:\n{res.stdout}"
    assert "untracked" in res.stdout, "the report does not say the copy is untracked"


def test_a_copy_of_a_git_internal_is_caught(tmp_path: Path) -> None:
    """`refs/heads/main 2` is the kind of copy that wedges `git fetch` and can make
    a merged PR read as unmerged. `.git/` is never excluded from the scan."""
    r = _repo(tmp_path)
    (r / ".git" / "refs" / "heads" / "main 2").write_text("deadbeef\n", encoding="utf-8")
    res = _run(r)
    assert res.returncode == 1, "a copy of a git internal was not reported"
    assert ".git/refs/heads/main 2" in res.stdout


def test_a_tracked_copy_is_reported_as_tracked(tmp_path: Path) -> None:
    """The original behaviour must survive the widening, and the report must still distinguish the
    two kinds — a tracked copy gets shared, an untracked one only shadows locally."""
    r = _repo(tmp_path)
    (r / "real 2.md").write_text("copy\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(r), "add", "real 2.md"], check=True)
    res = _run(r)
    assert res.returncode == 1
    assert "tracked    real 2.md" in res.stdout, f"a tracked copy was mislabelled:\n{res.stdout}"


def test_regenerated_build_output_is_pruned_but_nothing_else_is(tmp_path: Path) -> None:
    """`__pycache__` is pruned with a written reason: iCloud re-spawns copies there on every test
    run, and a permanently-red gate gets switched off. The second half is what keeps the prune
    from becoming a hole — a real copy alongside it must still fail, and the pruned one must not
    appear in the report."""
    r = _repo(tmp_path)
    cache = r / "scripts" / "__pycache__"
    cache.mkdir(parents=True)
    (cache / "mod 2.pyc").write_bytes(b"x")
    assert _run(r).returncode == 0, "a __pycache__ copy alone should not fail the guard"

    (r / "docs" / "note 2.md").write_text("stale\n", encoding="utf-8")
    res = _run(r)
    assert res.returncode == 1, "a real copy alongside pruned build output was not reported"
    assert "mod 2.pyc" not in res.stdout, "pruned build output leaked into the report"
    assert "docs/note 2.md" in res.stdout


def test_the_tracked_label_is_decided_by_a_literal_path(tmp_path: Path) -> None:
    """`$f` used to be handed to `git ls-files` as a PATHSPEC, so glob metacharacters in
    a filename were interpreted: an untracked `a[b] 2.md` was labelled `tracked` because the
    character class matched a tracked `ab 2.md` sitting beside it. Only the label lied, never the
    hit count — but a label nobody can trust is worse than no label, and this is the assertion that
    was missing when the mutation survived.
    """
    r = _repo(tmp_path)
    (r / "ab 2.md").write_text("tracked copy\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(r), "add", "ab 2.md"], check=True)
    (r / "a[b] 2.md").write_text("untracked copy\n", encoding="utf-8")
    res = _run(r)
    assert res.returncode == 1
    assert "tracked    ab 2.md" in res.stdout, f"the genuinely tracked copy lost its label:\n{res.stdout}"
    assert "untracked  a[b] 2.md" in res.stdout, (
        f"a glob in the filename matched a different file and mislabelled it:\n{res.stdout}"
    )


@pytest.mark.parametrize("digit", ["2", "3", "9"])
def test_every_digit_in_the_range_is_witnessed(tmp_path: Path, digit: str) -> None:
    """The widened range had no test above ` 2`, and the mutant proved it: changing both
    `[2-9]` occurrences to `[2-2]` left all nine tests green. That is not academic — `.git/index 3`
    is exactly the kind of copy a sync client leaves beside git's index, so a realistic
    case was the one nothing pinned.
    """
    r = _repo(tmp_path)
    (r / "docs" / f"note {digit}.md").write_text("stale\n", encoding="utf-8")
    res = _run(r)
    assert res.returncode == 1, f"a copy numbered {digit} was not reported"
    assert f"docs/note {digit}.md" in res.stdout


def test_a_worktree_run_still_covers_the_shared_git_dir(tmp_path: Path) -> None:
    """In a linked worktree `.git` is a ~108-byte FILE, so a plain `find .` walks past
    every git internal. An earlier version printed `PASS … (.git included)` from a worktree while
    the same planted ref made the main checkout FAIL.

    The control matters here: the same tree must be clean once the planted ref is gone, or this
    would pass on a guard that fails from a worktree unconditionally.
    """
    r = _repo(tmp_path)
    wt = tmp_path / "wt"
    subprocess.run(["git", "-C", str(r), "worktree", "add", "-q", "-d", str(wt)], check=True)
    assert (wt / ".git").is_file(), "fixture is not a linked worktree"
    assert _run(wt).returncode == 0, "the control run from a worktree is not clean"

    (r / ".git" / "refs" / "heads" / "planted 2").write_text("deadbeef\n", encoding="utf-8")
    res = _run(wt)
    assert res.returncode == 1, "a run from a worktree missed the shared git dir"
    assert "refs/heads/planted 2" in res.stdout


def test_a_scan_that_could_not_finish_is_a_failure_not_a_clean_bill(tmp_path: Path) -> None:
    """`set -uo pipefail` omits `-e` and stderr was discarded, so an unreadable directory
    produced a partial walk reported as PASS. The unreadable directory hides a real copy here, so
    the test would also fail if the guard simply found it anyway."""
    r = _repo(tmp_path)
    locked = r / "docs" / "locked"
    locked.mkdir()
    (locked / "note 2.md").write_text("stale\n", encoding="utf-8")
    locked.chmod(0o000)
    try:
        res = _run(r)
    finally:
        locked.chmod(0o755)
    assert res.returncode == 1, "a partial scan was reported as a clean bill"
    assert "did not complete" in res.stdout, f"the failure does not name its cause:\n{res.stdout}"


def test_the_manifest_description_matches_the_mechanism(tmp_path: Path) -> None:
    """The machine-readable declaration once read "No git-TRACKED iCloud ' 2' conflict
    copies": the narrow, tracked-only scope, left
    intact while the script's header, PASS and FAIL text were all rewritten. A declaration is part
    of the mechanism's surface, so it gets an assertion rather than a habit."""
    import json as _json
    manifest = _json.loads((ROOT / ".claude" / "close-gate.json").read_text(encoding="utf-8"))
    entry = next(i for i in manifest["invariants"] if i["name"] == "no-icloud-conflict-copies")
    desc = entry["description"].lower()
    # NOT `"tracked" in desc` — that is satisfied by the substring inside "untracked", which is
    # how a vacuous assertion gets written. Name the claim that was wrong and the claims owed.
    assert "git-tracked" not in desc, (
        "the description still declares the narrow, tracked-only scope: " + desc
    )
    for owed in ("untracked", "ignored", "worktree"):
        assert owed in desc, f"the description does not account for {owed} paths: {desc}"


@pytest.mark.parametrize("name", ["part 1.md", "chapter 10.md", "v2.md", "note2.md"])
def test_names_that_are_not_the_icloud_shape_stay_green(tmp_path: Path, name: str) -> None:
    """iCloud numbers copies from 2 and always inserts a space, so ` 1`, a two-digit tail, and a
    digit with no space are all different things. A guard that reddens on ordinary filenames gets
    switched off, which costs more than the copies do."""
    r = _repo(tmp_path)
    (r / "docs" / name).write_text("x\n", encoding="utf-8")
    res = _run(r)
    assert res.returncode == 0, f"{name!r} was misread as a conflict copy:\n{res.stdout}"
