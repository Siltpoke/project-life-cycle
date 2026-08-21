"""The danger check reads the real changed files.

Every test here builds a throwaway git repository under `tmp_path`. Nothing mutates the real
working tree: an earlier shape elsewhere in this suite wrote to tracked files and restored them in
a `finally`, which a SIGKILL or a `pytest -x` interrupt leaves planted.
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
CHECK = REPO / "skills/project-lifecycle/hooks/plc-careful-check.sh"
DATA = REPO / "skills/project-lifecycle/references/careful-paths.md"

SENTINEL = re.compile(
    r"<!-- plc-careful-data:begin -->\s*```json\n(.*?)\n```", re.S
)


def data_block(text: str | None = None) -> dict:
    src = DATA.read_text(encoding="utf-8") if text is None else text
    m = SENTINEL.search(src)
    assert m, "no fenced json block between the careful-data sentinels"
    return json.loads(m.group(1))


def _clean_env() -> dict:
    """The environment minus every GIT_* variable that redirects where git reads and writes.

    A git hook exports GIT_DIR (and friends), and GIT_DIR beats `-C`. Any fixture spawned from a
    hook inherits it, so `git -C <tmp> commit` lands in the real repository.
    """
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True, text=True, check=True, env=_clean_env(),
    ).stdout


def make_repo(tmp_path: Path, tracked: dict[str, str] | None = None) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    git(root.parent, "init", "-q", str(root))
    git(root, "config", "user.email", "t@example.invalid")
    git(root, "config", "user.name", "t")
    (root / "CLAUDE.md").write_text("# project\n", encoding="utf-8")
    for rel, body in (tracked or {}).items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    # NEVER COMMIT INTO THE REPOSITORY UNDER TEST -- and the reason is specific.
    # A git hook exports GIT_DIR, and GIT_DIR OVERRIDES `-C`. A fixture that inherits it commits
    # into the repository the hook is running for: the fixture's tree would land on the real
    # branch and every real file would come out as a deletion. `git()` below strips the whole GIT_*
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


def write(root: Path, rel: str, body: str = "x\n") -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def set_key(root: Path, line: str) -> None:
    p = root / "CLAUDE.md"
    p.write_text(p.read_text(encoding="utf-8") + line + "\n", encoding="utf-8")


def run(root: Path, data: Path | None = None, check: Path | None = None):
    return subprocess.run(
        [
            "/bin/bash",
            str(check or CHECK),
            "--claude-md",
            str(root / "CLAUDE.md"),
            "--repo",
            str(root),
            "--data",
            str(data or DATA),
        ],
        capture_output=True,
        text=True,
    )


def rows(out: str) -> list[tuple[str, str, str]]:
    return [
        tuple(line.split("\t"))  # type: ignore[misc]
        for line in out.strip().splitlines()
        if line and line != "no-hit"
    ]


# --- the changed-file list -----------------------------------------------------------------------------------


def test_a_declared_careful_path_is_hit_and_the_rule_is_named(tmp_path):
    """The hit is not enough -- the criterion requires saying WHICH path matched, so the
    assertion is on the rule column, not on the exit status."""
    root = make_repo(tmp_path, {"src/auth/session.ts": "old\n", "src/ui/button.ts": "old\n"})
    set_key(root, "careful-paths: src/auth/")
    write(root, "src/auth/session.ts", "changed\n")

    r = run(root)
    assert r.returncode == 0, r.stderr
    assert rows(r.stdout) == [("careful-path", "src/auth/", "src/auth/session.ts")]


def test_a_change_outside_every_declared_path_is_no_hit(tmp_path):
    """The negative half. A guard that always fires is worth as much as one that never does, so the
    quiet case is asserted with the same weight as the loud one."""
    root = make_repo(tmp_path, {"src/auth/session.ts": "old\n", "src/ui/button.ts": "old\n"})
    set_key(root, "careful-paths: src/auth/")
    write(root, "src/ui/button.ts", "changed\n")

    r = run(root)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "no-hit"


def test_a_brand_new_untracked_file_under_a_careful_path_is_hit(tmp_path):
    """The single most important row in this file.

    `git ls-files` lists TRACKED files only. Without --others a newly created
    src/auth/new-login.ts lands in the changed-file list and misses the pathspec set: the user marks
    src/auth/, the mechanism works exactly as designed, and writing a brand-new login file -- the
    shape most deserving of the upgrade -- is invisible to it.
    """
    root = make_repo(tmp_path, {"src/auth/session.ts": "old\n"})
    set_key(root, "careful-paths: src/auth/")
    write(root, "src/auth/new-login.ts", "brand new\n")

    r = run(root)
    assert r.returncode == 0, r.stderr
    assert ("careful-path", "src/auth/", "src/auth/new-login.ts") in rows(r.stdout)


def test_dropping_untracked_from_the_match_set_makes_the_new_file_invisible(tmp_path, mutant):
    """The mutant for the row above. Without it, that test proves only that the current code
    happens to pass -- not that the --others flag is what makes it pass."""
    root = make_repo(tmp_path, {"src/auth/session.ts": "old\n"})
    set_key(root, "careful-paths: src/auth/")
    write(root, "src/auth/new-login.ts", "brand new\n")

    broken = mutant(CHECK, "--cached --others --exclude-standard", "--cached")
    r = run(root, check=broken)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "no-hit", (
        "dropping --others still found the untracked file, so the flag is not what makes "
        "test_a_brand_new_untracked_file_under_a_careful_path_is_hit pass"
    )


def test_the_change_is_seen_while_it_is_still_uncommitted(tmp_path):
    """The implementer's work is not committed when the check runs. Reading a commit
    range would give a permanently empty list -- a guard that never fires."""
    root = make_repo(tmp_path, {"src/auth/session.ts": "old\n"})
    set_key(root, "careful-paths: src/auth/")
    write(root, "src/auth/session.ts", "uncommitted\n")

    assert git(root, "status", "--porcelain").strip(), "fixture is not actually dirty"
    assert rows(run(root).stdout), "an uncommitted change was not seen"


def test_reading_a_commit_range_instead_of_the_worktree_finds_nothing(tmp_path, mutant):
    """The mutant for the row above."""
    root = make_repo(tmp_path, {"src/auth/session.ts": "old\n"})
    set_key(root, "careful-paths: src/auth/")
    write(root, "src/auth/session.ts", "uncommitted\n")

    broken = mutant(
        CHECK,
        'git -C "$repo" status --porcelain=1 -z --untracked-files=all',
        'git -C "$repo" diff --name-only -z HEAD',
    )
    r = run(root, check=broken)
    assert r.stdout.strip() == "no-hit"


# --- the signal list -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rel,expected_class",
    [
        ("package.json", "dependency"),
        ("go.mod", "dependency"),
        ("mix.exs", "dependency"),
        ("migrations/001_init.sql", "migration"),
        ("db/migrate/20260819_add.rb", "migration"),
        (".github/workflows/ci.yml", "deploy-ci"),
        ("Dockerfile", "deploy-ci"),
    ],
)
def test_each_signal_fires_and_names_its_own_class(tmp_path, rel, expected_class):
    """`mix.exs` is in this list on purpose -- it is named among the
    entries the ecosystem list should carry, so it must be a HIT, never the not-covered example."""
    root = make_repo(tmp_path)
    write(root, rel)
    got = rows(run(root).stdout)
    assert got, f"{rel} fired nothing"
    assert {cls for cls, _, _ in got} == {expected_class}
    assert all(path == rel for _, _, path in got)


def test_an_ecosystem_the_list_does_not_name_is_a_miss_and_that_is_the_design(tmp_path):
    """The written-down list is fixed, so an ecosystem it does not name IS a miss, and
    that boundary is stated rather than papered over. The fixture is deliberately NOT mix.exs."""
    block = data_block()
    covered = {p for s in block["signals"].values() for p in s["paths"]}
    assert "dune-project" not in covered, "pick a fixture the shipped list really does not name"

    root = make_repo(tmp_path)
    write(root, "dune-project")
    assert run(root).stdout.strip() == "no-hit"


def test_editing_only_the_scripts_block_still_fires_and_the_wording_survives_it(tmp_path):
    """The dependency signal is a PATH match. Editing package.json's scripts block fires it, and
    the shipped `says` string has to remain true when it does -- which is why it reads 'touched the
    dependency manifest' and not 'added a third-party dependency'."""
    root = make_repo(tmp_path, {"package.json": '{"scripts":{"a":"1"}}\n'})
    write(root, "package.json", '{"scripts":{"a":"2"}}\n')

    assert rows(run(root).stdout), "a package.json edit did not fire"
    says = data_block()["signals"]["dependency"]["says"]
    assert "add" not in says.lower(), f"the dependency wording claims an event it cannot see: {says}"


# --- the data block is the single source ------------------------------------------------------


def test_the_check_hard_codes_none_of_the_shipped_paths():
    """A literal in the script is how the next editor learns that two copies are acceptable."""
    src = CHECK.read_text(encoding="utf-8")
    block = data_block()
    leaked = sorted(
        p for s in block["signals"].values() for p in s["paths"] if p in src
    )
    assert leaked == [], f"these live in both the data block and the script: {leaked}"


def test_the_check_hard_codes_none_of_the_shipped_words():
    src = CHECK.read_text(encoding="utf-8")
    leaked = sorted(w for w in data_block()["words"] if re.search(rf'"{w}"', src))
    assert leaked == []


def test_a_second_data_block_is_refused_rather_than_silently_picked(tmp_path):
    """Two copies and a reader that picks one is the drift the single-block shape exists to stop."""
    doubled = tmp_path / "doubled.md"
    text = DATA.read_text(encoding="utf-8")
    m = SENTINEL.search(text)
    assert m
    doubled.write_text(
        text.replace(m.group(0), m.group(0) + "\n```json\n{}\n```", 1), encoding="utf-8"
    )

    root = make_repo(tmp_path)
    r = run(root, data=doubled)
    assert r.returncode == 3, (r.returncode, r.stdout, r.stderr)


def test_no_hit_is_printed_rather_than_left_silent(tmp_path):
    """Silence and a crash look identical to the caller."""
    root = make_repo(tmp_path)
    write(root, "README.md", "hello\n")
    r = run(root)
    assert r.returncode == 0
    assert r.stdout.strip() == "no-hit"


@pytest.fixture
def mutant(tmp_path):
    """Copy a script with one literal replaced, so a test can prove the original line is what makes
    another test pass. Returns a path; the copy lives under tmp_path and is never the real file."""
    made = []

    def _make(src: Path, old: str, new: str) -> Path:
        text = src.read_text(encoding="utf-8")
        assert old in text, f"mutation target not present, so this mutant proves nothing: {old!r}"
        # Measured on the first run of this file: the target string also appeared in a COMMENT
        # above the code, `replace(..., 1)` rewrote the comment, the code was untouched, and the
        # mutant "survived" -- which reads exactly like a real surviving mutant and is not one.
        # A target that occurs more than once is refused rather than guessed at.
        assert text.count(old) == 1, (
            f"{old!r} occurs {text.count(old)} times in {src.name}; a mutant that rewrites the "
            "wrong one proves nothing, and a survivor for that reason is indistinguishable from "
            "a real one"
        )
        dst = tmp_path / f"mutant-{len(made)}-{src.name}"
        dst.write_text(text.replace(old, new, 1), encoding="utf-8")
        dst.chmod(0o755)
        made.append(dst)
        return dst

    return _make
