"""AC1-AC11 — growth on a counted surface must be declared, and the check must be able to
go red on every input it exists to reject.

Every test builds a throwaway repository in `tmp_path` and copies the invariant into it, so the
script's own `dirname/../..` root resolution lands on the fixture. Nothing here mutates this
working tree: restoring a mutant with `git checkout` on an uncommitted tree has destroyed real
work in this repository before, so the mutation lives in a fixture and dies with it.

Read these as pairs wherever possible. AC2 and AC3 run the SAME fixture and differ only by one
declaration line, so a green cannot come from the fixture being built wrong.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
INVARIANT = ROOT / "scripts/invariants/growth-declares-a-deletion.sh"
TABLE_REL = "skills/project-lifecycle/references/step-enforcement.md"

# Every blind spot the design spec and the Q&A promise the header states out loud (AC11). Each is
# a DISTINCT substring: one combined pattern would let the removal of one sentence pass while
# another still matched.
BLIND_SPOTS = (
    "It never checks a declaration is TRUE",
    "It never counts lines",
    "Blocking points -- the weight the user actually reports -- are invisible",
    "does not confirm the named deletion ever existed",
    "Surfaces are ENUMERATED below, not discovered",
    "an UNTRACKED new reference is invisible",
    "including one inside a fenced code block",
    "An UNTRACKED journal fragment is accepted",
    "NET ZERO RECORDS NOTHING",
)


def _git(repo: Path, *args: str, **kw) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update(
        GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t.t",
        GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t.t",
    )
    return subprocess.run(["git", *args], cwd=repo, check=kw.pop("check", True),
                          capture_output=True, text=True, env=env, **kw)


def _run(repo: Path, *, path_without_git: bool = False) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if path_without_git:
        # bash is invoked by absolute path, so the script still starts; `command -v git` must fail.
        empty = repo / "_nobin"
        empty.mkdir(exist_ok=True)
        env["PATH"] = str(empty)
    return subprocess.run(
        ["/bin/bash", "scripts/invariants/growth-declares-a-deletion.sh"],
        cwd=repo, capture_output=True, text=True, check=False, env=env,
    )


def _table(a: int = 14, b: int = 12, c: int = 11) -> str:
    return (
        "# Step -> enforcement\n\n"
        f"- Band A rows: **{a}**\n"
        f"- Band B rows: **{b}**\n"
        f"- Band C rows: **{c}**\n"
    )


def _repo(tmp_path: Path, *, refs: int = 3, cmds: int = 2, table: str | None = None,
          origin: bool = True, name: str = "repo") -> Path:
    """A base commit with `refs` references, `cmds` commands and a step-enforcement table,
    plus a local refs/remotes/origin/main pointing at it so the merge base resolves."""
    repo = tmp_path / name
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")

    refdir = repo / "skills/project-lifecycle/references"
    refdir.mkdir(parents=True)
    for i in range(refs):
        (refdir / f"r{i:02d}.md").write_text("x\n", encoding="utf-8")

    cmddir = repo / "commands"
    cmddir.mkdir()
    for i in range(cmds):
        (cmddir / f"c{i:02d}.md").write_text("x\n", encoding="utf-8")

    (repo / TABLE_REL).write_text(_table() if table is None else table, encoding="utf-8")

    invdir = repo / "scripts/invariants"
    invdir.mkdir(parents=True)
    shutil.copy2(INVARIANT, invdir / INVARIANT.name)

    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    if origin:
        _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    return repo


def _add_reference(repo: Path, slug: str) -> None:
    p = repo / "skills/project-lifecycle/references" / f"{slug}.md"
    p.write_text("new\n", encoding="utf-8")
    _git(repo, "add", str(p.relative_to(repo)))


def _declare(repo: Path, line: str) -> None:
    d = repo / "docs/journal.d"
    d.mkdir(parents=True, exist_ok=True)
    (d / "2026-01-18-phase-p165-x.md").write_text(line + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- AC8
def test_no_growth_needs_no_declaration(tmp_path: Path) -> None:
    r = _run(_repo(tmp_path))
    assert r.returncode == 0, r.stderr
    assert "no counted surface grew" in r.stdout


def test_head_equal_to_merge_base_is_green(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    # origin/main IS head here, so every delta is 0 — the state `main` is always in.
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    origin = _git(repo, "rev-parse", "refs/remotes/origin/main").stdout.strip()
    assert head == origin
    assert _run(repo).returncode == 0


# --------------------------------------------------------------------------- AC2 / AC3 (one pair)
def test_undeclared_reference_growth_is_red(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _add_reference(repo, "zz-new")
    r = _run(repo)
    assert r.returncode == 1, r.stdout + r.stderr
    assert r.stderr.startswith("FAIL[undeclared-growth]")
    assert "references" in r.stderr
    assert "grew by 1" in r.stderr


def test_the_declaration_is_what_turns_it_green(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _add_reference(repo, "zz-new")
    assert _run(repo).returncode == 1  # same tree, red first
    _declare(repo, "GROWTH: references +1 cannot-delete: nothing here is removable yet")
    r = _run(repo)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "every grown surface is declared" in r.stdout


# --------------------------------------------------------------------------- AC4
def test_declaration_in_a_commit_message_counts(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _add_reference(repo, "zz-new")
    _git(repo, "commit", "-qm",
         "feat: add a reference\n\nGROWTH: references +1 deleted: an older duplicate")
    r = _run(repo)
    assert r.returncode == 0, r.stdout + r.stderr


def test_a_branch_with_no_journal_dir_is_still_satisfiable(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert not (repo / "docs/journal.d").exists()
    _add_reference(repo, "zz-new")
    _git(repo, "commit", "-qm", "docs: x\n\nGROWTH: references +1 cannot-delete: docs branch")
    assert _run(repo).returncode == 0


# --------------------------------------------------------------------------- AC5
def test_a_deletion_elsewhere_does_not_pay_for_growth(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _add_reference(repo, "zz-new")
    _git(repo, "rm", "-q", "commands/c00.md")
    r = _run(repo)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "references" in r.stderr, "the net is zero, but references still grew"


# --------------------------------------------------------------------------- AC6
def test_a_declaration_for_another_surface_pays_for_nothing(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _add_reference(repo, "zz-new")
    _declare(repo, "GROWTH: commands +9 deleted: plenty, but not in references")
    r = _run(repo)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "references" in r.stderr


# --------------------------------------------------------------------------- AC7
def test_under_declaring_is_red_and_names_both_numbers(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _add_reference(repo, "zz-one")
    _add_reference(repo, "zz-two")
    _declare(repo, "GROWTH: references +1 deleted: only one of the two")
    r = _run(repo)
    assert r.returncode == 1, r.stdout + r.stderr
    assert r.stderr.startswith("FAIL[under-declared-growth]")
    assert "grew by 2" in r.stderr
    assert "account for 1" in r.stderr


def test_two_declarations_can_sum_to_cover_the_delta(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _add_reference(repo, "zz-one")
    _add_reference(repo, "zz-two")
    d = repo / "docs/journal.d"
    d.mkdir(parents=True)
    (d / "a.md").write_text("GROWTH: references +1 deleted: first\n", encoding="utf-8")
    (d / "b.md").write_text("GROWTH: references +1 deleted: second\n", encoding="utf-8")
    assert _run(repo).returncode == 0


# --------------------------------------------------------------------------- AC1 (steps surface)
def test_steps_growth_is_read_from_the_declared_band_totals(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / TABLE_REL).write_text(_table(c=12), encoding="utf-8")  # 37 -> 38
    _git(repo, "add", TABLE_REL)
    r = _run(repo)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "'steps'" in r.stderr
    assert "37 -> 38" in r.stderr


def test_steps_shrinking_needs_no_declaration(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / TABLE_REL).write_text(_table(c=10), encoding="utf-8")  # 37 -> 36
    _git(repo, "add", TABLE_REL)
    assert _run(repo).returncode == 0


# --------------------------------------------------------------------------- AC9 (never 0, never 1)
def test_no_merge_base_is_could_not_run(tmp_path: Path) -> None:
    repo = _repo(tmp_path, origin=False)
    r = _run(repo)
    assert r.returncode == 3, r.stdout + r.stderr
    assert r.stderr.startswith("CANNOT-RUN[no-merge-base]")


def test_git_absent_is_could_not_run(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    r = _run(repo, path_without_git=True)
    assert r.returncode == 3, r.stdout + r.stderr
    assert r.stderr.startswith("CANNOT-RUN[no-git]")


def test_an_unreadable_counted_surface_is_could_not_run(tmp_path: Path) -> None:
    """The table is gone at HEAD, so `steps` cannot be counted. A surface that cannot be read is
    exit 3 — it must never fold into the 0 that means `nothing grew`."""
    repo = _repo(tmp_path)
    _git(repo, "rm", "-q", TABLE_REL)
    r = _run(repo)
    assert r.returncode == 3, r.stdout + r.stderr
    assert "CANNOT-RUN[unreadable-head-steps]" in r.stderr


def test_a_malformed_band_block_is_could_not_run(tmp_path: Path) -> None:
    """Two band lines instead of three. A partial read reported as clean is the defect class this
    whole phase is about."""
    repo = _repo(tmp_path)
    (repo / TABLE_REL).write_text("# t\n\n- Band A rows: **14**\n- Band B rows: **12**\n",
                                  encoding="utf-8")
    _git(repo, "add", TABLE_REL)
    r = _run(repo)
    assert r.returncode == 3, r.stdout + r.stderr


# --------------------------------------------------------------------------- AC10
def test_lines_are_not_counted(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    big = repo / "skills/project-lifecycle/references/r00.md"
    big.write_text("filler\n" * 3000, encoding="utf-8")
    _git(repo, "add", str(big.relative_to(repo)))
    r = _run(repo)
    assert r.returncode == 0, "3000 added lines in existing files are not growth by this unit"


def test_the_line_exclusion_still_carries_its_reason() -> None:
    """If a future edit deletes the measurement citation, the exclusion becomes an unexplained
    omission and the next reader adds a line counter back. The citation is load-bearing text."""
    src = INVARIANT.read_text(encoding="utf-8")
    assert "LINES ARE NOT COUNTED" in src
    assert "swept over SKILL.md" in src
    assert "qualified nowhere" in src, "the measured result, not just the instruction"


# --------------------------------------------------------------------------- AC11
@pytest.mark.parametrize("sentence", BLIND_SPOTS)
def test_the_header_states_every_blind_spot(sentence: str) -> None:
    assert sentence in INVARIANT.read_text(encoding="utf-8"), \
        f"the header no longer states: {sentence!r} — the stated scope must match the mechanism"


# ----------------------------------------------- the gaps found by probing the holes
#
# Every test below exists because a reviewer either probed the hole or showed that deleting a piece
# of production code left the suite green. Each is a red-first case.

def test_the_commands_surface_can_red_on_its_own(tmp_path: Path) -> None:
    """The quality AND correctness lenses both found this: no test grew `commands`, so stubbing
    `count_commands` to 0 — or mistyping `^commands/` — left every case green. A counter with no
    positive coverage is a counter nobody is checking."""
    repo = _repo(tmp_path)
    p = repo / "commands/zz-new.md"
    p.write_text("new\n", encoding="utf-8")
    _git(repo, "add", "commands/zz-new.md")
    r = _run(repo)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "'commands'" in r.stderr
    assert "2 -> 3" in r.stderr


def test_the_commands_surface_goes_green_on_its_own_declaration(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "commands/zz-new.md").write_text("new\n", encoding="utf-8")
    _git(repo, "add", "commands/zz-new.md")
    _declare(repo, "GROWTH: commands +1 cannot-delete: no command became redundant")
    assert _run(repo).returncode == 0


def test_a_non_ascii_filename_is_still_counted(tmp_path: Path) -> None:
    """git's default core.quotePath wraps any non-ASCII path in quotes with octal escapes, so a
    `^skills` anchor never matched it and real growth exited 0. Probed by the correctness lens."""
    repo = _repo(tmp_path)
    p = repo / "skills/project-lifecycle/references/été.md"
    p.write_text("new\n", encoding="utf-8")
    _git(repo, "add", "-A")
    r = _run(repo)
    assert r.returncode == 1, "a non-ASCII reference name is growth like any other"
    assert "'references'" in r.stderr
    # 4, not `refs=3`: the fixture's step-enforcement table lives under references/ and is itself
    # a reference file by this counter's definition.
    assert "4 -> 5" in r.stderr


def test_a_broken_listing_is_could_not_run_not_a_shrink(tmp_path: Path) -> None:
    """The first version piped the listing into `grep -c`, so the pipeline status was grep's and a
    failed `git ls-files` became "0 files" — which against a real base count reads as a clean
    SHRINK and exits 0. Probed by the correctness lens with a corrupted index."""
    repo = _repo(tmp_path)
    _add_reference(repo, "zz-new")
    (repo / ".git/index").write_bytes(b"\x00" * 64)
    r = _run(repo)
    assert r.returncode == 3, r.stdout + r.stderr
    assert "CANNOT-RUN" in r.stderr
    assert r.returncode != 0, "a broken read must never read as nothing-grew"


def test_one_declaration_written_twice_pays_once(tmp_path: Path) -> None:
    """The design offers two doors (journal fragment OR commit message), so writing the same line
    in both is natural — and summing every matching line made `+1` twice pay for a delta of 2."""
    repo = _repo(tmp_path)
    _add_reference(repo, "zz-one")
    _add_reference(repo, "zz-two")
    line = "GROWTH: references +1 deleted: one older duplicate"
    _declare(repo, line)
    _git(repo, "commit", "-qm", f"feat: two references\n\n{line}")
    r = _run(repo)
    assert r.returncode == 1, "identical text is one claim, not two"
    assert "account for 1" in r.stderr


def test_a_stale_fragment_from_an_earlier_phase_pays_for_nothing(tmp_path: Path) -> None:
    """Journal fragments from already-merged phases sit in the tree until the next retention drain,
    and the first implementation read the whole directory. A `GROWTH: references +5` line left
    behind by an older phase silently covered a later phase's growth."""
    repo = _repo(tmp_path)
    d = repo / "docs/journal.d"
    d.mkdir(parents=True)
    (d / "2026-01-01-phase-old-x.md").write_text(
        "GROWTH: references +5 cannot-delete: an older phase said so\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base: an older phase's fragment")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")

    _add_reference(repo, "zz-new")
    r = _run(repo)
    assert r.returncode == 1, "a declaration from a merged phase is not this branch's declaration"
    assert "'references'" in r.stderr


def test_a_declaration_with_an_empty_reason_is_rejected(tmp_path: Path) -> None:
    """`deleted:` with nothing after it is the one thing a what-did-it-cost ledger must refuse, and
    the `[^[:space:]]` guard that refuses it had no test."""
    repo = _repo(tmp_path)
    _add_reference(repo, "zz-new")
    _declare(repo, "GROWTH: references +1 deleted:")
    assert _run(repo).returncode == 1


def test_a_multi_digit_declaration_parses(tmp_path: Path) -> None:
    """The number extraction was only ever exercised with single digits."""
    repo = _repo(tmp_path, refs=3)
    for i in range(12):
        _add_reference(repo, f"zz-{i:02d}")
    _declare(repo, "GROWTH: references +12 cannot-delete: a batch import, nothing redundant")
    r = _run(repo)
    assert r.returncode == 0, r.stdout + r.stderr


def test_a_fourth_band_does_not_pass_unnoticed(tmp_path: Path) -> None:
    """`/^- Band [ABC]/` with a bare `n == 3` check ignored a future `- Band D rows:` line
    entirely: the sum undercounted and the invariant stayed green."""
    repo = _repo(tmp_path)
    (repo / TABLE_REL).write_text(_table() + "- Band D rows: **4**\n", encoding="utf-8")
    _git(repo, "add", TABLE_REL)
    r = _run(repo)
    assert r.returncode == 3, r.stdout + r.stderr


def test_one_band_declared_twice_is_could_not_run(tmp_path: Path) -> None:
    """`A, B, A` satisfied the old `n == 3` check and double-counted a band."""
    repo = _repo(tmp_path)
    (repo / TABLE_REL).write_text(
        "# t\n\n- Band A rows: **14**\n- Band B rows: **12**\n- Band A rows: **11**\n",
        encoding="utf-8")
    _git(repo, "add", TABLE_REL)
    assert _run(repo).returncode == 3


def test_a_band_line_the_parser_cannot_read_is_could_not_run(tmp_path: Path) -> None:
    """Stripping non-digits from the whole line turned `- Band C rows: **11** (was 10)` into 1110,
    a 1,099 phantom growth — and the same mis-parse on the base side would hide real growth as a
    shrink. A format it cannot read must be visible, not wrong."""
    repo = _repo(tmp_path)
    (repo / TABLE_REL).write_text(
        "# t\n\n- Band A rows: **14**\n- Band B rows: **12**\n- Band C rows: eleven\n",
        encoding="utf-8")
    _git(repo, "add", TABLE_REL)
    assert _run(repo).returncode == 3


def test_the_steps_counter_reads_the_index_not_the_working_tree(tmp_path: Path) -> None:
    """All three surfaces must read the same source per side. An unstaged table edit counting as
    growth while an unstaged reference did not was a review finding, and it also made the
    registration's "both sides are read from git" false for this one counter."""
    repo = _repo(tmp_path)
    (repo / TABLE_REL).write_text(_table(c=12), encoding="utf-8")  # edited, NOT staged
    assert _run(repo).returncode == 0, "an unstaged edit is not in the index"
    _git(repo, "add", TABLE_REL)
    assert _run(repo).returncode == 1, "staged, it is growth"


def test_the_envelope_holds_no_python_and_no_jq() -> None:
    src = INVARIANT.read_text(encoding="utf-8")
    body = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    assert "python3" not in body
    assert "jq " not in body and "jq'" not in body
