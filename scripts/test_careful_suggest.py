"""Candidates read off this project's own tree, with reasons that state facts.

Every test builds a throwaway git repository under `tmp_path`. Nothing mutates the real tree.
"""
import json
import os
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SUGGEST = REPO / "skills/project-lifecycle/hooks/plc-careful-suggest.sh"
DATA = REPO / "skills/project-lifecycle/references/careful-paths.md"

SENTINEL = re.compile(r"<!-- plc-careful-data:begin -->\s*```json\n(.*?)\n```", re.S)

INFERENCE_WORDS = [
    "sensitive", "risky", "dangerous", "looks like", "probably", "seems",
    "appears", "critical", "important", "should",
]


def block() -> dict:
    m = SENTINEL.search(DATA.read_text(encoding="utf-8"))
    assert m
    return json.loads(m.group(1))


def _clean_env() -> dict:
    """The environment minus every GIT_* variable that redirects where git reads and writes.

    p33 CORRECTION. This docstring used to read: "A git hook exports GIT_DIR (and friends), and
    GIT_DIR beats `-C`. Any fixture spawned from a hook inherits it, so `git -C <tmp> commit` lands
    in the real repository." The second sentence reproduces. The FIRST DOES NOT: measured
    on a recent git across pre-commit, prepare-commit-msg, commit-msg, post-commit,
    pre-push and post-checkout, no hook type exports GIT_DIR, and nothing in this repository
    exports it either. The old wording is quoted rather than deleted so the surviving conclusion
    keeps its support and a correction does not read as an oversight.

    What remains true: with GIT_DIR set by ANY means, `git -C <tmp> commit` lands in the repository
    GIT_DIR names. the incident is real history; its stated mechanism is not, and its actual
    cause is recorded as unknown rather than guessed at. This filter is therefore standing
    insurance against an unidentified vector — cheap, and labelled as insurance. The earlier filings record it.
    """
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True, text=True, check=True, env=_clean_env(),
    ).stdout


def make_repo(tmp_path: Path, files: dict, claude_md: str = "# project\n") -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    git(root.parent, "init", "-q", str(root))
    git(root, "config", "user.email", "t@example.invalid")
    git(root, "config", "user.name", "t")
    (root / "CLAUDE.md").write_text(claude_md, encoding="utf-8")
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    # NEVER COMMIT INTO THE REPOSITORY UNDER TEST. p33: this comment used to justify itself with
    # "a git hook exports GIT_DIR" -- false, see `_clean_env` above; git exports it to no hook type.
    # What IS measured is the consequence once GIT_DIR is set by any means: the fixture's tree lands
    # on the real branch and every real file comes out as a deletion. `git()` below strips the whole
    # GIT_*
    # family from the environment, and the assertion is on `--absolute-git-dir` rather than on
    # `--show-toplevel`, because the top level follows the cwd while the commit follows GIT_DIR --
    # an assertion on the top level passes while the commit still goes to the wrong place.
    gd = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--absolute-git-dir"],
        capture_output=True, text=True, env=_clean_env(),
    ).stdout.strip()
    assert gd == str((root / ".git").resolve()), (
        f"fixture {root} resolves to git dir {gd!r}; refusing to commit -- this is the assertion "
        "that stops a test writing into the repository under test"
    )
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    return root


def run(root: Path, script: Path = None):
    return subprocess.run(
        [
            "/bin/bash", str(script or SUGGEST),
            "--repo", str(root),
            "--claude-md", str(root / "CLAUDE.md"),
            "--data", str(DATA),
        ],
        capture_output=True, text=True,
    )


def rows(out: str):
    return [tuple(l.split("\t", 1)) for l in out.strip().splitlines() if l]


# --- hard constraint 1: every proposed path really exists --------------------------------------


def test_every_proposed_path_exists_on_disk(tmp_path):
    """A suggestion pointing at something not on disk is a defect, and this
    is the assertion that makes 'read the project on the spot' mean anything."""
    root = make_repo(tmp_path, {
        "src/auth/session.ts": "x\n",
        "src/billing/invoice.ts": "x\n",
        "README.md": "x\n",
    })
    got = rows(run(root).stdout)
    assert got, "nothing proposed on a tree that plainly contains matches"
    for path, _ in got:
        assert (root / path.rstrip("/")).exists(), f"proposed a path that is not there: {path}"


def test_a_suggester_that_skips_the_existence_check_is_caught(tmp_path, mutant):
    """The mutant for the row above. Without it, the existence assertion passes trivially because
    every candidate happens to be derived from a real entry -- it proves the derivation, not the
    check. Here the file is deleted from disk while git still lists it in the index, so only the
    check can drop it."""
    root = make_repo(tmp_path, {"src/auth/session.ts": "x\n"})
    (root / "src/auth/session.ts").unlink()
    (root / "src/auth").rmdir()

    ok = run(root)
    assert ok.stdout.strip().startswith("no-candidates"), (
        f"the existence check did not drop an indexed-but-deleted path: {ok.stdout!r}"
    )

    broken = mutant(SUGGEST, '[ -e "$repo/${target%/}" ] || continue', ':')
    r = run(root, script=broken)
    assert not r.stdout.strip().startswith("no-candidates"), (
        "removing the existence check changed nothing, so that line is not what enforces it"
    )


# --- hard constraint 2: every proposal says why, and the why is a fact --------------------------


def test_every_proposal_carries_a_reason(tmp_path):
    root = make_repo(tmp_path, {"src/auth/session.ts": "x\n"})
    got = rows(run(root).stdout)
    assert got
    for path, reason in got:
        assert reason.strip(), f"{path} was proposed with nothing to justify it"


def test_the_reason_names_the_word_that_matched(tmp_path):
    """A reason the reader can check and overrule. 'contains a file whose name contains "auth"'
    can be disagreed with; 'this looks sensitive' cannot."""
    root = make_repo(tmp_path, {"src/auth/session.ts": "x\n"})
    got = dict(rows(run(root).stdout))
    assert "src/auth/" in got
    assert '"auth"' in got["src/auth/"]


def test_a_directory_named_after_what_it_holds_is_found_even_when_no_file_matches(tmp_path):
    """The bug this test exists for passes a basename-only test suite easily.

    The first version compared only the BASENAME, so `src/auth/session.ts` matched nothing: the
    directory literally named `auth` was invisible, and naming a directory after what it holds is
    the single most likely way a project marks this out. The other tests passed because their file
    names happened to match too. This fixture is chosen so ONLY the directory segment can match.
    """
    root = make_repo(tmp_path, {"src/auth/handler.ts": "x\n"})
    got = dict(rows(run(root).stdout))
    assert "src/auth/" in got, f"a directory named `auth` was not found: {got}"
    assert '"auth"' in got["src/auth/"]


def test_the_directorys_own_name_beats_a_file_inside_it_as_the_stated_reason(tmp_path):
    """When a path matches several ways, the direct evidence has to be the one shown. Measured:
    `src/auth/session.ts` first reported 'contains a file whose name contains "session"' -- a true
    sentence, and the weaker of the two available ones, chosen only because it sorted earlier."""
    root = make_repo(tmp_path, {"src/auth/session.ts": "x\n"})
    reason = dict(rows(run(root).stdout))["src/auth/"]
    assert '"auth"' in reason, reason
    assert "contains a file" not in reason, reason


def test_no_reason_uses_an_inference_word(tmp_path):
    """The hard constraint: a reason states what was observed, never what it means -- the
    counterweight to shipping a word list at all."""
    root = make_repo(tmp_path, {
        "src/auth/session.ts": "x\n",
        "src/billing/stripe.ts": "x\n",
        "config/secret.env": "x\n",
    })
    for _, reason in rows(run(root).stdout):
        low = reason.lower()
        for w in INFERENCE_WORDS:
            assert w not in low, f"a reason infers rather than states: {reason}"


# --- hard constraint 3: proposing nothing is legal ---------------------------------------------


def test_a_project_matching_nothing_gets_an_honest_line_and_exit_zero(tmp_path):
    """Not an error, not silence, and not a manufactured suggestion."""
    root = make_repo(tmp_path, {"lib/widget.ts": "x\n", "README.md": "x\n"})
    r = run(root)
    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith("no-candidates\t")
    assert "mark it yourself" in r.stdout.lower()


def test_the_empty_case_is_not_reported_as_a_failure(tmp_path):
    """An empty result that exits non-zero would train the caller to treat 'nothing to be careful
    about' as a broken run."""
    root = make_repo(tmp_path, {"README.md": "x\n"})
    assert run(root).returncode == 0


# --- the false positives are expected, and the wording has to survive them ----------------------


def test_a_test_fixture_named_like_a_secret_is_proposed_and_the_reason_stays_factual(tmp_path):
    """password_generator.py WILL be proposed. That is the shipped behaviour, not a bug -- and it is
    exactly why the reason may only state the fact: a reader can see 'contains a file whose name
    contains "password"' and recognise their own test fixture. They could not do that with 'this
    handles sensitive data'."""
    root = make_repo(tmp_path, {"tests/fixtures/password_generator.py": "x\n"})
    got = dict(rows(run(root).stdout))
    assert "tests/fixtures/" in got, "the false positive did not occur, so this test proves nothing"
    reason = got["tests/fixtures/"].lower()
    assert '"password"' in reason
    for w in INFERENCE_WORDS:
        assert w not in reason


def test_an_ascii_word_matches_inside_a_path_with_accented_characters(tmp_path):
    """The shipped vocabulary is ASCII, so it matches regardless of whether the filesystem stored
    the accented parts composed or decomposed -- the accents are not what is being matched.

    Normalisation before matching is deliberately not done: normalising needs a
    dependency this envelope does not carry, and a NON-ASCII word added by a project is compared
    byte for byte. The limit is named in the script rather than a normalisation being claimed.
    """
    root = make_repo(tmp_path, {"src/authentification/café.ts": "x\n"})
    got = dict(rows(run(root).stdout))
    assert "src/authentification/" in got


# --- the project's own additions ---------------------------------------------------------------


def test_a_project_can_add_its_own_words(tmp_path):
    root = make_repo(
        tmp_path,
        {"src/kassa/pay.ts": "x\n"},
        claude_md="# project\ncareful-words: kassa\n",
    )
    assert "src/kassa/" in dict(rows(run(root).stdout))


def test_the_shipped_word_list_is_not_written_in_the_script():
    src = SUGGEST.read_text(encoding="utf-8")
    leaked = sorted(w for w in block()["words"] if re.search(rf'"{w}"', src))
    assert leaked == [], f"the vocabulary must live in the data block only: {leaked}"


def test_one_row_per_path_even_when_several_words_match(tmp_path):
    """src/auth/ matches 'auth' and its file matches 'login'. Proposing it twice would read as two
    findings and make the screen noisier than the evidence warrants."""
    root = make_repo(tmp_path, {"src/auth/login.ts": "x\n"})
    paths = [p for p, _ in rows(run(root).stdout)]
    assert len(paths) == len(set(paths)), paths


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
