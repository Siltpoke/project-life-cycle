"""The command-doc Python guard, and the anchor its exemptions use.

WHY THIS FILE EXISTS AT ALL. `scripts/invariants/commands-no-bare-python.sh` shipped
wired into the gate and with NO test of its own. Every claim about it was held by review. This
file is the measurement, and it was written when the exemption anchor changed (a content
anchor was chosen over narrowing the rule).

WHAT CHANGED AND WHAT THE ORACLE HAS TO BE. The first version keyed each exemption on
`path:line`. The killer case is NOT "a line moved and the check went quiet" -- a moved line is
usually loud, just loud about the wrong line. It is `test_rewritten_exempt_line_is_not_excused`:
rewrite the exempted line itself into a real invocation and the line-number version prints
`ok ... exempt` and exits 0, with a `python3 ... --wipe` instruction wearing a reason written
for a prose mention. So the oracle here is not "the guard failed"; it is WHICH LINE the guard
excused. Several rows assert on the message text for exactly that reason.

Each test copies the real guard, optionally rewrites its EXEMPT list with a plain string
replacement, and runs it against a fixture tree handed over through `COMMANDS_PY_ROOT`. The
fixture is a copy of the real command docs, so a row cannot pass by testing a toy corpus that
shares nothing with what ships.
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GUARD = REPO / "scripts" / "invariants" / "commands-no-bare-python.sh"
EXTRA = "skills/project-lifecycle/references/init-harness.md"

# The real entry this suite mutates. Written out rather than parsed, so a row cannot quietly
# follow the guard's own list into a change nobody noticed.
REAL_KEY = "commands/cognition-distill.md|python3 scripts/cognition_log.py|"


def _run(guard: Path, root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["/bin/bash", str(guard)],
        env={"COMMANDS_PY_ROOT": str(root), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="cnbp-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = self.tmp / "fx"
        (self.root / "commands").mkdir(parents=True)
        (self.root / EXTRA).parent.mkdir(parents=True)
        for md in (REPO / "commands").glob("*.md"):
            shutil.copy2(md, self.root / "commands" / md.name)
        shutil.copy2(REPO / EXTRA, self.root / EXTRA)
        self.doc = self.root / "commands" / "cognition-distill.md"
        self.pristine = self.doc.read_text(encoding="utf-8").splitlines(keepends=True)
        # The fixture must be a corpus the guard actually has something to say about, or every
        # row below would pass against an empty set.
        self.assertTrue(
            any("cognition_log.py" in ln for ln in self.pristine),
            "fixture setup failed: the exempted line is not in the copied doc",
        )

    def guard_with(self, replacement: str | None = None) -> Path:
        """A copy of the real guard, optionally with its one real EXEMPT entry rewritten."""
        text = GUARD.read_text(encoding="utf-8")
        self.assertIn(REAL_KEY, text, "the guard's EXEMPT entry changed shape; update REAL_KEY")
        out = self.tmp / "guard.sh"
        if replacement is None:
            out.write_text(text, encoding="utf-8")
        else:
            mutated = text.replace(REAL_KEY, replacement)
            self.assertNotEqual(mutated, text, "the mutation did not reach the file")
            out.write_text(mutated, encoding="utf-8")
        return out

    def rewrite_doc(self, lines: list[str]) -> None:
        self.doc.write_text("".join(lines), encoding="utf-8")

    def exempt_line_index(self) -> int:
        for i, ln in enumerate(self.pristine):
            if "python3 scripts/cognition_log.py" in ln:
                return i
        self.fail("fixture setup failed: no exempted line found")


class TestControls(Base):
    def test_unmodified_fixture_is_green(self) -> None:
        """Without this, every red row below could be red for an unrelated reason."""
        r = _run(self.guard_with(), self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("2 written exemptions", r.stdout)

    def test_the_real_repo_is_green(self) -> None:
        r = _run(GUARD, REPO)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_a_resolver_routed_invocation_is_not_flagged(self) -> None:
        """The guard must not simply flag every Python-looking line."""
        lines = list(self.pristine)
        lines.insert(0, "Run `bash scripts/plc-python.sh scripts/thing.py --go`.\n")
        self.rewrite_doc(lines)
        r = _run(self.guard_with(), self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_an_unrouted_invocation_is_flagged(self) -> None:
        lines = list(self.pristine)
        lines.insert(0, "Run `python3 scripts/thing.py --go`.\n")
        self.rewrite_doc(lines)
        r = _run(self.guard_with(), self.root)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("invokes a Python interpreter directly", r.stdout)


class TestTheAnchorIsContent(Base):
    def test_rewritten_exempt_line_is_not_excused(self) -> None:
        """THE ROW THAT MOTIVATED THE CHANGE.

        Replace the exempted line's text with a genuine, destructive invocation. Under a
        line-number anchor the guard prints `ok ... exempt` and exits 0 -- measured, not argued.
        Under a content anchor the planted line is flagged AND the exemption is reported expired.
        """
        lines = list(self.pristine)
        lines[self.exempt_line_index()] = "1. Run `python3 scripts/evil.py --wipe` first.\n"
        self.rewrite_doc(lines)
        r = _run(self.guard_with(), self.root)
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("evil.py", r.stdout)
        self.assertIn("invokes a Python interpreter directly", r.stdout)
        self.assertIn("the exemption has expired", r.stdout)

    def test_a_planted_line_does_not_inherit_the_exemption(self) -> None:
        """A new invocation inserted ABOVE the exempted line takes its old number, not its reason.

        The old anchor excused the planted line and reported the innocent one; both the verdict
        and the line named in it are asserted, because the verdict alone cannot tell the two
        versions apart here -- both exit non-zero.
        """
        idx = self.exempt_line_index()
        lines = list(self.pristine)
        lines.insert(idx, "   (planted: `python3 scripts/evil.py` -- a real invocation)\n")
        self.rewrite_doc(lines)
        r = _run(self.guard_with(), self.root)
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f"commands/cognition-distill.md:{idx + 1} invokes", r.stdout)
        self.assertIn("exempt -- prose naming a module", r.stdout)
        self.assertNotIn("evil.py` -- a real invocation)\n", r.stdout.split("exempt --")[-1])


class TestExemptionHygiene(Base):
    def test_an_exemption_matching_nothing_is_reported_expired(self) -> None:
        r = _run(
            self.guard_with("commands/cognition-distill.md|python3 scripts/gone.py|still here|"),
            self.root,
        )
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("the exemption has expired", r.stdout)

    def test_an_exemption_matching_twice_is_reported_over_broad(self) -> None:
        """One written reason silently covering two call sites is the same hole, reversed."""
        idx = self.exempt_line_index()
        lines = list(self.pristine)
        lines.insert(idx, self.pristine[idx])
        self.rewrite_doc(lines)
        r = _run(self.guard_with(), self.root)
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("matched 2 invocations", r.stdout)

    def test_an_empty_fragment_is_refused(self) -> None:
        """An empty anchor is a blanket exemption wearing the costume of a targeted one."""
        r = _run(self.guard_with("commands/cognition-distill.md||any reason at all|"), self.root)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("EMPTY fragment", r.stdout)

    def test_an_exemption_without_a_reason_is_refused(self) -> None:
        r = _run(
            self.guard_with("commands/cognition-distill.md|python3 scripts/cognition_log.py\n"),
            self.root,
        )
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("carries no written reason", r.stdout)

    def test_an_out_of_scope_path_is_refused(self) -> None:
        """An entry naming a file the guard never reads can never expire, so it never dies."""
        r = _run(
            self.guard_with("docs/NOT-IN-SCOPE.md|python3 scripts/cognition_log.py|reason|"),
            self.root,
        )
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("is not in this check's scope", r.stdout)


class TestEmptyCorpus(Base):
    def test_an_empty_scope_is_a_hard_failure(self) -> None:
        """Two empty sets compare equal and the run looks exactly like a clean one."""
        empty = self.tmp / "empty"
        empty.mkdir()
        r = _run(self.guard_with(), empty)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("scope is EMPTY", r.stdout)


if __name__ == "__main__":
    unittest.main()
