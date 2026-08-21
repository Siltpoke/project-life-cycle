"""The careful-paths write-back, and the four sentences the tick-box round has to carry.

This file exists because of a specific failure shape. A plausible
first shape of the write-back has a whole chain -- render tick-boxes, take a selection, save
it, never ask again -- with NO MECHANISM behind it: the acceptance assertion is "the key is
present", and the key is written by the test. An implementation that does nothing passes.

So the write is a separate callable act, and these are the assertions that a no-op fails.
"""
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
WRITE = REPO / "skills/project-lifecycle/hooks/plc-careful-write.sh"
KICKOFF = REPO / "skills/project-lifecycle/hooks/plc-kickoff-check.sh"
SCREEN_DOC = REPO / "skills/project-lifecycle/references/kickoff-confirmation.md"

MISSES = ["your-marking", "incomplete-ecosystems", "english-words", "path-not-intent"]


def run_write(md: Path, paths: str = "", script: Path = None, stdin: str = ""):
    args = ["/bin/bash", str(script or WRITE), "--claude-md", str(md)]
    if paths:
        args += ["--paths", paths]
    return subprocess.run(args, input=stdin, capture_output=True, text=True)


def md(tmp_path: Path, body: str = "# project\n") -> Path:
    p = tmp_path / "CLAUDE.md"
    p.write_text(body, encoding="utf-8")
    return p


# --- the write actually happens ---------------------------------------------------------------


def test_the_chosen_paths_land_in_claude_md(tmp_path):
    """The assertion a no-op implementation fails."""
    f = md(tmp_path)
    r = run_write(f, "src/auth/,db/")
    assert r.returncode == 0, r.stderr
    assert "careful-paths: src/auth/, db/" in f.read_text(encoding="utf-8")


def test_a_write_that_does_nothing_is_caught(tmp_path, mutant):
    """The mutant for the row above. Without it, the test proves only that the file ends up
    containing a string -- not that this script is what put it there."""
    f = md(tmp_path)
    broken = mutant(
        WRITE,
        'printf \'%s: %s\\n\' "$force_key" "$value" >>"$claude_md"',
        ':',
    )
    run_write(f, "src/auth/", script=broken)
    assert "careful-paths" not in f.read_text(encoding="utf-8"), (
        "the file gained the key with the write removed, so the write line is not what puts it there"
    )


def test_the_paths_can_arrive_on_stdin(tmp_path):
    f = md(tmp_path)
    assert run_write(f, stdin="src/auth/\ndb/\n").returncode == 0
    assert "careful-paths: src/auth/, db/" in f.read_text(encoding="utf-8")


# --- running it twice ---------------------------------------------------------------------------


def test_running_twice_leaves_the_file_byte_identical(tmp_path):
    """A re-run that appends a second key gives the reader of CLAUDE.md two answers to one
    question, and nothing downstream says which one wins."""
    f = md(tmp_path)
    run_write(f, "src/auth/")
    once = f.read_bytes()
    r = run_write(f, "src/auth/")
    assert r.returncode == 0, r.stderr
    assert f.read_bytes() == once
    assert r.stdout.startswith("unchanged\t")


def test_an_existing_different_declaration_is_refused_not_overwritten(tmp_path):
    """The key is the user's own declaration. A tool that proposed the alternatives does not get to
    silently replace the answer."""
    f = md(tmp_path, "# project\ncareful-paths: src/mine/\n")
    r = run_write(f, "src/auth/")
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert "src/mine/" in f.read_text(encoding="utf-8")
    assert "src/auth/" not in f.read_text(encoding="utf-8")
    assert "refused" in r.stderr


# --- choosing nothing ---------------------------------------------------------------------------


def test_choosing_nothing_writes_nothing_and_says_which_case_this_is(tmp_path):
    """The empty-choice constraint reaches this far too. An empty key would be indistinguishable
    from a half-finished run."""
    f = md(tmp_path)
    before = f.read_bytes()
    r = run_write(f, stdin="\n  \n")
    assert r.returncode == 3
    assert f.read_bytes() == before
    assert r.stdout.startswith("nothing-chosen\t")


# --- the four sentences on the screen -----------------------------------------------------------


def _screen(tmp_path: Path, careful: str | None) -> Path:
    frag = tmp_path / "qa.md"
    lines = [
        "<!-- plc-kickoff:begin -->",
        "mode: fast | source: project-default | confirmed-at: kickoff",
        "not-for-fast: logins-and-passwords | taking-payments | "
        "other-peoples-personal-details | public-to-strangers",
        'work-kind: builder | because: the request says "make a ..."',
        "criteria: t:AC1",
        "must-answer: 0 outstanding",
    ]
    if careful is not None:
        lines.append(careful)
    lines.append("<!-- plc-kickoff:end -->")
    frag.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return frag


def _story(tmp_path: Path) -> Path:
    s = tmp_path / "user-story.md"
    s.write_text("- **AC1** {#t:AC1}: a thing\n", encoding="utf-8")
    return s


def run_kickoff(frag: Path, story: Path):
    return subprocess.run(
        ["/bin/bash", str(KICKOFF), str(frag), "--story", str(story), "--phase", "t"],
        capture_output=True, text=True,
    )


def test_a_screen_with_no_careful_round_is_not_in_breach(tmp_path):
    """Conditional by design: the round only happens on a first fast run with nothing marked, so
    its absence is 'did not apply', never 'was skipped'."""
    r = run_kickoff(_screen(tmp_path, None), _story(tmp_path))
    assert r.returncode == 0, r.stderr
    assert "no careful round" in r.stdout


def test_a_careful_round_stating_all_four_misses_passes(tmp_path):
    line = "careful: proposed=3 chosen=2 | misses: " + " ".join(MISSES)
    r = run_kickoff(_screen(tmp_path, line), _story(tmp_path))
    assert r.returncode == 0, r.stderr + r.stdout
    assert "four stated misses" in r.stdout


@pytest.mark.parametrize("dropped", MISSES)
def test_dropping_any_one_of_the_four_misses_reddens(tmp_path, dropped):
    """Each of the four is a DIFFERENT way this feature will miss something, so each is asserted on
    its own. A single 'the misses are present' check would pass on three of four."""
    kept = [m for m in MISSES if m != dropped]
    line = "careful: proposed=3 chosen=2 | misses: " + " ".join(kept)
    r = run_kickoff(_screen(tmp_path, line), _story(tmp_path))
    assert r.returncode == 1, (r.returncode, r.stdout, r.stderr)
    assert dropped in r.stderr


def test_a_careful_round_without_counts_reddens(tmp_path):
    """'It suggested nothing' and 'it was never run' must not read alike in the record."""
    line = "careful: misses: " + " ".join(MISSES)
    r = run_kickoff(_screen(tmp_path, line), _story(tmp_path))
    assert r.returncode == 1
    assert "proposed=" in r.stderr


def test_the_reference_document_states_all_four_misses(tmp_path):
    """The markers are what the checker reads; the sentences are what the person reads. Both have
    to exist, or the checker is guarding a document that never made the promise."""
    text = SCREEN_DOC.read_text(encoding="utf-8").lower()
    for needle in ["do not mark", "do not name is a miss", "english words", "removed", "moved"]:
        assert needle in text, f"the screen document does not state: {needle}"


def test_the_reference_document_names_the_scripted_write_back():
    assert "plc-careful-write.sh" in SCREEN_DOC.read_text(encoding="utf-8")


@pytest.fixture
def mutant(tmp_path):
    made = []

    def _make(src: Path, old: str, new: str) -> Path:
        text = src.read_text(encoding="utf-8")
        assert old in text, f"mutation target not present: {old!r}"
        assert text.count(old) == 1, (
            f"{old!r} occurs {text.count(old)} times; a mutant that rewrites the wrong one proves "
            "nothing and its survivor is indistinguishable from a real one"
        )
        dst = tmp_path / f"mutant-{len(made)}-{src.name}"
        dst.write_text(text.replace(old, new, 1), encoding="utf-8")
        dst.chmod(0o755)
        made.append(dst)
        return dst

    return _make
