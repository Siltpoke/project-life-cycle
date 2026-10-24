"""The adoption-rule invariant must not write into an inherited git repository.

WHAT THIS PINS, and why the obvious shape of the test is the wrong one.

The defect was not "the invariant failed". The invariant PASSED -- it printed its ok line -- while
creating commits on the branch that was being pushed and replacing that branch's index. A test
that asserts the invariant's exit code therefore proves nothing about this: both the broken and the
fixed version exit 0. The oracle has to be the STATE OF AN UNRELATED REPOSITORY, not the verdict.

So each test here hands the invariant a victim repository through the environment, runs it, and
asserts the victim did not move. `test_broken_version_is_caught` is the control: it reproduces the
pre-fix shape in a copy and asserts this oracle actually fires, because an assertion that no repo
moved would also pass if the thing under test never ran at all.
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INVARIANT = REPO / "scripts" / "invariants" / "adoption-rule-single-source.sh"


def _git(*args, cwd, env=None):
    e = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    e.update(env or {})
    return subprocess.run(
        ["git", *args], cwd=cwd, env=e, capture_output=True, text=True, check=False
    )


def _make_victim(root: Path) -> tuple[Path, str]:
    """A repository that has nothing to do with the invariant, with one commit."""
    root.mkdir(parents=True, exist_ok=True)
    _git("init", "-q", "--initial-branch=main", ".", cwd=root)
    _git("config", "user.email", "t@e.invalid", cwd=root)
    _git("config", "user.name", "t", cwd=root)
    (root / "REAL.md").write_text("real\n", encoding="utf-8")
    _git("add", "REAL.md", cwd=root)
    _git("commit", "-qm", "real work", cwd=root)
    head = _git("rev-parse", "HEAD", cwd=root).stdout.strip()
    assert head, "fixture setup failed: the victim repo has no HEAD"
    return root, head


def _run_invariant(script: Path, victim: Path, extra_env: dict) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(extra_env)
    return subprocess.run(
        ["bash", str(script)], cwd=REPO, env=env, capture_output=True, text=True, check=False
    )


class FixtureEnvIsolation(unittest.TestCase):
    def _assert_victim_unmoved(self, script: Path, extra_env_factory):
        with tempfile.TemporaryDirectory() as tmp:
            victim, before = _make_victim(Path(tmp) / "victim")
            _run_invariant(script, victim, extra_env_factory(victim))
            after = _git("rev-parse", "HEAD", cwd=victim).stdout.strip()
            subject = _git("log", "--format=%s", "-1", cwd=victim).stdout.strip()
            return before, after, subject

    def test_git_dir_alone_does_not_move_an_unrelated_repo(self):
        """The measured trigger: GIT_DIR set, GIT_WORK_TREE not."""
        before, after, subject = self._assert_victim_unmoved(
            INVARIANT, lambda v: {"GIT_DIR": str(v / ".git")}
        )
        self.assertEqual(
            before,
            after,
            f"the invariant moved an unrelated repository's HEAD (now {after!r}, "
            f"subject {subject!r}) -- p178",
        )

    def test_git_dir_and_index_file_do_not_move_an_unrelated_repo(self):
        before, after, subject = self._assert_victim_unmoved(
            INVARIANT,
            lambda v: {"GIT_DIR": str(v / ".git"), "GIT_INDEX_FILE": str(v / ".git" / "index")},
        )
        self.assertEqual(
            before, after, f"HEAD moved to {after!r} ({subject!r}) -- p178"
        )

    def test_broken_version_is_caught(self):
        """The control. Without it, the two tests above would also pass against a script that
        never ran -- 'no repository moved' is exactly what doing nothing looks like.

        THE COPY HAS TO LIVE BESIDE THE ORIGINAL, and the first attempt at this test is why that
        sentence is here. The invariant derives the repository root from its OWN location
        (`cd "$(dirname "${BASH_SOURCE[0]}")/../.."`), so a copy under /tmp cd'd to /tmp's
        grandparent, failed an earlier readability check with `COULD NOT RUN:
        scripts/archaeology-preflight.sh is not readable`, exited 3, and never reached the arm this
        test is about. It reported the victim as unmoved -- i.e. the control said "the oracle cannot
        fire" for a reason that had nothing to do with the oracle."""
        with tempfile.TemporaryDirectory() as tmp:
            broken = INVARIANT.parent / ".p178-control-copy.sh"
            self.addCleanup(lambda: broken.unlink(missing_ok=True))
            text = INVARIANT.read_text(encoding="utf-8")
            needle = "unset GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE GIT_OBJECT_DIRECTORY \\\n" \
                     "      GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_COMMON_DIR GIT_NAMESPACE"
            self.assertIn(
                needle,
                text,
                "the unset block this test reverts is not in the invariant any more -- "
                "update this control rather than deleting it",
            )
            broken.write_text(text.replace(needle, ": # unset removed by p178's control"),
                              encoding="utf-8")
            shutil.copymode(INVARIANT, broken)

            victim, before = _make_victim(Path(tmp) / "victim")
            _run_invariant(broken, victim, {"GIT_DIR": str(victim / ".git")})
            after = _git("rev-parse", "HEAD", cwd=victim).stdout.strip()
            self.assertNotEqual(
                before,
                after,
                "reverting the unset did NOT move the victim repo -- this oracle cannot fail, "
                "so the two tests above prove nothing",
            )


if __name__ == "__main__":
    unittest.main()
