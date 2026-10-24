"""The branch-staleness half of the archaeology pre-flight.


WHAT THESE TESTS DELIBERATELY DO NOT COVER YET. The existing-artifact scan (AC7-AC11), the roadmap
note and its suppressed draft (AC12, AC17), the false-negative floor (AC13) and the single-source
guard (AC14-AC16) are covered in later sections. AC1's second clause -- that the pass actually CONTINUES on
exit 0 -- is call-site behaviour, covered in the call-site section. Saying so here is not a disclaimer: a reader who found
`test_AC1_*` in this file and assumed all of AC1 was covered would be repeating, inside the test
suite, the exact mistake this phase exists to fix.
"""

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "archaeology-preflight.sh"


def git(cwd, *args, check=True):
    p = subprocess.run(
        ["/usr/bin/git", "-C", str(cwd), *args], capture_output=True, text=True
    )
    if check and p.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed in {cwd}: {p.stderr}")
    return p.stdout.strip()


def run(repo, *extra):
    return subprocess.run(
        ["/bin/bash", str(SCRIPT), "check", "--repo", str(repo), *extra],
        capture_output=True, text=True,
    )


def _identity(repo):
    git(repo, "config", "user.email", "t@example.invalid")
    git(repo, "config", "user.name", "t")


def make_pair(tmp_path, behind=0):
    """A bare `origin` plus a clone. `behind` extra commits are pushed to origin's default branch
    AFTER the working checkout is parked, so the checkout is genuinely behind rather than merely
    different. Returns the working clone."""
    origin = tmp_path / "origin.git"
    seed = tmp_path / "seed"
    work = tmp_path / "work"

    git(tmp_path, "init", "--bare", "--initial-branch=main", str(origin))
    git(tmp_path, "clone", str(origin), str(seed))
    _identity(seed)
    (seed / "README.md").write_text("seed\n")
    git(seed, "add", "README.md")
    git(seed, "commit", "-m", "seed")
    git(seed, "push", "origin", "main")

    git(tmp_path, "clone", str(origin), str(work))
    _identity(work)

    if behind:
        for i in range(behind):
            (seed / f"f{i}.txt").write_text(f"{i}\n")
            git(seed, "add", f"f{i}.txt")
            git(seed, "commit", "-m", f"later {i}")
        git(seed, "push", "origin", "main")
        git(work, "fetch", "origin")
        # park the checkout on the old commit: a branch that does not move with origin
        git(work, "checkout", "-b", "parked")
    return work


# --------------------------------------------------------------------------- AC1


def test_AC1_clean_repo_exits_zero_and_prints_a_report(tmp_path):
    """AC1, first clause. A current repo exits 0 AND prints something. An exit code with no output
    is indistinguishable from a check that did nothing -- which is the whole failure mode here."""
    work = make_pair(tmp_path)
    p = run(work)
    assert p.returncode == 0, p.stdout + p.stderr
    assert p.stdout.strip(), "exit 0 with empty stdout is not a report"
    assert "no finding" in p.stdout


# --------------------------------------------------------------------------- AC3 / AC5


def test_AC3_the_check_never_writes(tmp_path):
    """AC3. HEAD, the branch and the porcelain status must be byte-identical across the run."""
    work = make_pair(tmp_path, behind=3)
    before = (
        git(work, "rev-parse", "HEAD"),
        git(work, "rev-parse", "--abbrev-ref", "HEAD"),
        git(work, "status", "--porcelain"),
    )
    run(work)
    after = (
        git(work, "rev-parse", "HEAD"),
        git(work, "rev-parse", "--abbrev-ref", "HEAD"),
        git(work, "status", "--porcelain"),
    )
    assert before == after


MUTATING_VERBS = (
    "checkout", "switch", "reset", "set-head", "fetch", "push", "commit",
    "merge", "rebase", "branch", "tag", "stash", "clean", "gc", "update-ref",
)


def test_AC3_the_check_never_writes_with_origin_head_absent(tmp_path):
    """AC3, on the OTHER default-ref branch. The original AC3 test used a fixture that always has
    refs/remotes/origin/HEAD, so the `[ -z "$default_ref" ]` branch never received an immutability
    check at all -- and that branch is the one a sizeable share of real remote-carrying
    repositories take. A mutation planted there wrote to the repo with every test green."""
    work = make_pair(tmp_path)
    git(work, "symbolic-ref", "-d", "refs/remotes/origin/HEAD")
    before = (
        git(work, "rev-parse", "HEAD"),
        git(work, "rev-parse", "--abbrev-ref", "HEAD"),
        git(work, "status", "--porcelain"),
        sorted(p.name for p in (work / ".git" / "refs" / "heads").iterdir()),
    )
    run(work)
    after = (
        git(work, "rev-parse", "HEAD"),
        git(work, "rev-parse", "--abbrev-ref", "HEAD"),
        git(work, "status", "--porcelain"),
        sorted(p.name for p in (work / ".git" / "refs" / "heads").iterdir()),
    )
    assert before == after


def test_AC5_the_source_contains_no_mutating_git_verb(tmp_path):
    """AC5. A source-level pin, because the behavioural tests can only prove the paths they reach.

    IT MUST KNOW THE SCRIPT'S OWN IDIOM, AND THE FIRST VERSION DID NOT. Every real git call in the
    script is written `g <verb>` through the wrapper at the top of the file, never `git <verb>`. The
    first version of this pin searched only for the literal `git <verb>`, so a line written the way
    the file writes every one of its own lines -- `g checkout -q -b oops` -- passed straight
    through. A review inserted exactly that line into the unresolved-origin/HEAD branch
    and measured the result: the script really did check out and create a branch, and every
    test stayed green. Reproduced before being accepted (`main` -> `__mutant_writes_here__`).

    Boundary, stated: this catches a mutating verb written literally in either form. A verb
    assembled at runtime from pieces is still invisible, which is why the behavioural immutability
    check now runs on BOTH default-ref branches rather than this pin being the only proof."""
    import re

    body = "\n".join(
        line for line in SCRIPT.read_text().split("\n")
        if not line.lstrip().startswith("#")
    )
    for verb in MUTATING_VERBS:
        assert f"git {verb}" not in body, f"`git {verb}` appears outside a comment"
        assert not re.search(rf"(?m)^\s*g\s+{verb}\b", body), (
            f"`g {verb}` -- the script's own calling idiom -- appears outside a comment"
        )


def test_AC5_the_pin_has_a_positive_control():
    """A pin nobody has seen fire is not evidence it can fire. Both spellings must be caught."""
    import re

    for sample in ("  git checkout -b oops", "  g checkout -q -b oops"):
        caught = ("git checkout" in sample) or bool(
            re.search(r"(?m)^\s*g\s+checkout\b", sample)
        )
        assert caught, f"the pin does not fire on {sample!r}"


# --------------------------------------------------------------------------- AC4


def test_AC4_stale_branch_is_a_finding_with_count_and_date(tmp_path):
    """AC4. The one line must name the branch, how far behind, and the default branch's last
    commit date. Each clause is asserted separately: a test that only checked 'behind' appears
    would stay green while the date silently stopped printing."""
    work = make_pair(tmp_path, behind=3)
    p = run(work)
    assert p.returncode == 1, p.stdout + p.stderr
    out = p.stdout
    assert "parked" in out, "the current branch must be named"
    assert "3 commits behind" in out, "the distance must be a number"
    assert "origin/main" in out, "the default branch must be named"
    last = git(work, "log", "-1", "--format=%cs", "origin/main")
    assert last in out, "the default branch's last-commit date must be printed"
    assert "STOPPED" in out and "No drafts" in out


def test_AC4_stale_report_says_nothing_was_changed(tmp_path):
    """The locked decision is that the pass does not re-point itself. A report that stops without
    saying so invites the reader to assume it did."""
    work = make_pair(tmp_path, behind=2)
    p = run(work)
    assert "Nothing was changed" in p.stdout
    assert "no branch switch" in p.stdout


def test_ahead_is_not_reported_as_up_to_date(tmp_path):
    """Story Edge Cases. Being 0 behind is not parity. An early version of the script reported a
    feature branch carrying unpushed commits as
    'up to date with origin/main' -- a correct judgement wearing a sentence wider than itself."""
    work = make_pair(tmp_path)
    _identity(work)
    (work / "local.txt").write_text("local\n")
    git(work, "add", "local.txt")
    git(work, "commit", "-m", "local only")
    p = run(work)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "1 commits ahead" in p.stdout
    assert "up to date" not in p.stdout, "ahead must not be described as parity"


def test_the_as_last_fetched_clause_is_printed(tmp_path):
    """`rev-list --count` reads whatever the
    remote-tracking ref last saw, so a clone nobody has fetched in months can report 0 behind while
    upstream has moved. No fetch is possible without breaking AC3, so this clause IS the whole
    mitigation -- and a mitigation that is not printed is not a mitigation. Added after a mutation
    run: deleting the clause left every test green."""
    work = make_pair(tmp_path)
    p = run(work)
    assert "compared against remote refs as last fetched" in p.stdout


def test_the_could_not_run_trap_is_wired_and_exits_three():
    """If an unforeseen failure trips bash's own
    error exit before the script reaches its intentional exit 3, a genuine could-not-run presents
    as exit 1 with no report -- 'the check never ran' silently reclassified as 'the check ran'.

    THIS IS A SOURCE PIN PLUS A SHAPE TEST, AND THE REASON IS NOT A DISCLAIMER. The trap exists to
    catch the UNFORESEEN; by construction no fixture can manufacture one, and every foreseen failure
    in this script is routed through the explicit die_could_not_run instead. So the two halves cover
    two different things and neither covers the third: the pin proves the trap is still installed,
    the shape test proves a trap written this way does yield 3, and NOTHING here proves that some
    future unhandled command actually reaches it. That last gap is real and is stated rather than
    left for a reader to assume away. Added after a mutation run in which deleting the trap
    outright left every test green."""
    body = SCRIPT.read_text()
    assert "trap _trap_could_not_run ERR" in body, "the ERR trap is not installed"
    assert "exit 3" in body

    shape = subprocess.run(
        ["/bin/bash", "-c",
         'set -euo pipefail; t() { exit 3; }; trap t ERR; false; echo unreachable'],
        capture_output=True, text=True,
    )
    assert shape.returncode == 3, (
        "a trap of this shape must turn an uncaught failure into 3, not into 1"
    )


def test_a_diverged_branch_reports_both_directions(tmp_path):
    """`N commits behind` on a branch that also carries local
    commits reads as a fast-forward relationship that does not exist -- the same claim-wider-than-
    the-measurement defect the ahead-vs-parity fix closed for the behind==0 case, still open for
    behind>0. Cross-checked against git's own arithmetic (`rev-list --left-right --count`)
    rather than against the script's. `git status -sb` was the first choice and was wrong for
    this fixture: the parked branch has no upstream, so porcelain prints `## parked` and nothing
    else -- the oracle would have been measuring a config field, not the divergence."""
    work = make_pair(tmp_path, behind=3)
    _identity(work)
    for i in range(2):
        (work / f"local{i}.txt").write_text("x\n")
        git(work, "add", f"local{i}.txt")
        git(work, "commit", "-m", f"local {i}")
    counts = git(work, "rev-list", "--left-right", "--count", "origin/main...HEAD")
    behind_n, ahead_n = counts.split()
    assert (behind_n, ahead_n) == ("3", "2"), f"fixture is not diverged: {counts}"

    p = run(work)
    assert p.returncode == 1, p.stdout + p.stderr
    assert "diverged" in p.stdout
    assert "3 commits behind" in p.stdout
    assert "2 ahead" in p.stdout


def test_detached_head_is_not_double_parenthesised(tmp_path):
    """Cosmetic, from the same review. A doubled parenthetical reads as a typo in a report whose
    whole job is to be read carefully."""
    work = make_pair(tmp_path)
    git(work, "checkout", "--detach")
    p = run(work)
    assert "(detached HEAD)" not in p.stdout
    assert "detached HEAD" in p.stdout


def test_a_bare_repository_is_not_called_not_a_repository(tmp_path):
    """Same review. Exit 3 is right -- there is no worktree to check -- but the wording sent the
    reader to look for a problem that is not there."""
    bare = tmp_path / "b.git"
    git(tmp_path, "init", "--bare", "-q", "--initial-branch=main", str(bare))
    p = run(bare)
    assert p.returncode == 3
    # The substring "bare repository" is NOT a sufficient assertion: a message saying the repo is
    # "not a bare repository" contains it too, and a mutant that flipped the sentence survived on
    # exactly that. Assert the whole clause.
    assert "is a bare repository: there is no working tree to check" in p.stderr
    assert "is not inside a git repository" not in p.stderr


# --------------------------------------------------------------------------- AC6


def test_AC6_missing_origin_head_says_not_checked_and_prints_the_remedy(tmp_path):
    """AC6. Measured: a sizeable share of real remote-carrying repos lack the
    ref. 'Not checked' alone is honest and is a dead end, so the remedy is printed -- as text."""
    work = make_pair(tmp_path)
    git(work, "symbolic-ref", "-d", "refs/remotes/origin/HEAD")
    p = run(work)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "staleness not checked" in p.stdout
    assert "git remote set-head origin -a" in p.stdout
    assert "will" in p.stdout and "not create it" in p.stdout


def test_AC6_the_remedy_is_printed_not_run(tmp_path):
    """AC3 again, aimed at the one place most likely to break it: the fix is a write."""
    work = make_pair(tmp_path)
    git(work, "symbolic-ref", "-d", "refs/remotes/origin/HEAD")
    run(work)
    p = subprocess.run(
        ["/usr/bin/git", "-C", str(work), "symbolic-ref", "-q", "--short",
         "refs/remotes/origin/HEAD"],
        capture_output=True, text=True,
    )
    assert p.returncode != 0, "the check created the ref it said it would not create"


def test_AC6_no_origin_main_fallback_in_the_source():
    """AC6. scripts/close-gate.sh:1346 carries `|| echo origin/main`. That fallback turns 'I could
    not find out' into a confident measurement against a branch that may not exist, and this script
    runs on strangers' repositories. The pin is on the source because the behaviour it forbids is
    invisible on any repo whose default branch happens to be main."""
    body = "\n".join(
        line for line in SCRIPT.read_text().split("\n")
        if not line.lstrip().startswith("#")
    )
    assert "echo origin/main" not in body
    assert "origin/master" not in body
    assert "symbolic-ref -q --short refs/remotes/origin/HEAD" in body, (
        "the house idiom must be the one used"
    )


# --------------------------------------------------------------------------- exit 3


def test_exit_3_when_not_a_git_repository(tmp_path):
    """Could-not-run is its own code. Exiting 1 here would mean 'finding', and the pass would
    stop for the wrong stated reason with no report body."""
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    p = run(plain)
    assert p.returncode == 3, p.stdout + p.stderr
    assert "COULD NOT RUN" in p.stderr


def test_exit_3_is_not_1_on_an_unknown_subcommand():
    p = subprocess.run(
        ["/bin/bash", str(SCRIPT), "frobnicate"], capture_output=True, text=True
    )
    assert p.returncode == 3


def test_repo_with_no_commits_is_not_an_error(tmp_path):
    """Story Edge Cases. A repo with no commits has nothing to be stale against, and the detection
    contract already routes it to new-project. The pre-flight must not be the thing that crashes."""
    empty = tmp_path / "fresh"
    empty.mkdir()
    git(empty, "init", "--initial-branch=main")
    _identity(empty)
    p = run(empty)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "no commits yet" in p.stdout


# ===========================================================================
# The existing-artifact scan. AC7 (marker), AC8 (name + filename shape),
# AC9 (the negative control that makes AC8 mean something), AC10 (content
# fingerprint, both families), AC11 (every row names its tier).
# ===========================================================================


def add_tracked(repo, paths):
    """Write and COMMIT files. The scan reads `git ls-files`, so an uncommitted file is invisible
    to it -- which is the detection contract's own rule, not an accident of this helper."""
    for rel, text in paths.items():
        f = repo / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
    _identity(repo)
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "fixture")


NYGARD = "# 0001 Use Postgres\n\n## Status\n\nAccepted\n\n## Consequences\n\nWe run one database.\n"
MADR = (
    "---\nstatus: accepted\n---\n# Use Postgres\n\n"
    "## Context and Problem Statement\n\nWe need a database.\n\n"
    "## Considered Options\n\n* Postgres\n* MySQL\n\n"
    "## Decision Outcome\n\nChosen: Postgres.\n"
)


def test_AC7_marker_file_is_reported_with_its_tier(tmp_path):
    """AC7. adr-tools writes `.adr-dir`, one line naming the directory -- and the research found it
    pointing at paths no fixed list would guess."""
    work = make_pair(tmp_path)
    add_tracked(work, {".adr-dir": "doc/architecture/decisions\n"})
    p = run(work)
    assert p.returncode == 1, p.stdout + p.stderr
    assert "doc/architecture/decisions" in p.stdout
    assert "evidence tier: marker" in p.stdout


def test_AC7_log4brains_adr_folder_is_read_not_guessed(tmp_path):
    """AC7. A marker file can point at a path such as
    `./documentation/adr` -- a path no default would find."""
    work = make_pair(tmp_path)
    add_tracked(work, {".log4brains.yml": "project:\n  name: x\nadrFolder: ./documentation/adr\n"})
    p = run(work)
    assert p.returncode == 1
    assert "./documentation/adr" in p.stdout
    assert "evidence tier: marker (.log4brains.yml)" in p.stdout


def test_AC8_a_named_directory_with_NNNN_files_is_reported(tmp_path):
    """AC8: the ADRs live in a token-named directory, `docs/adr/`, holding NNNN-*.md files."""
    work = make_pair(tmp_path)
    add_tracked(work, {
        "docs/adr/0001-retire-legacy-api.md": "# 1\n",
        "docs/adr/0002-adopt-new-renderer.md": "# 2\n",
    })
    p = run(work)
    assert p.returncode == 1
    assert "docs/adr/" in p.stdout
    assert "evidence tier: name + filename shape" in p.stdout
    assert "2 files" in p.stdout


def test_AC8_directory_matching_is_case_insensitive(tmp_path):
    """AC8. `docs/ADR/` is as real as `docs/adr/`. Locked at brainstorm as `-iname`, never
    `-iregex`, because BSD and GNU find disagree on the latter -- and this repo's adopters are not
    all on macOS. Without a mixed-case fixture nothing pins the insensitivity at all."""
    work = make_pair(tmp_path)
    add_tracked(work, {"docs/ADR/0001-a.md": "# a\n", "docs/ADR/0002-b.md": "# b\n"})
    p = run(work)
    assert p.returncode == 1, p.stdout + p.stderr
    assert "docs/ADR/" in p.stdout
    assert "evidence tier: name + filename shape" in p.stdout


def test_AC9_a_named_directory_without_NNNN_files_is_not_reported(tmp_path):
    """AC9 -- the negative control that makes AC8 mean something. A bare `*/decisions/` rule hits a
    recurring tutorial folder in many repositories (where "Decisions" means
    if/else branching), and in datasets and meeting logs. Remove the NNNN gate and this
    fixture gets reported."""
    work = make_pair(tmp_path)
    add_tracked(work, {
        "src/Tutorials/Decisions/Program.cs": "if (x) {}\n",
        "src/Tutorials/Decisions/README.md": "# branching\n",
    })
    p = run(work)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "Decisions" not in p.stdout


def test_AC9_a_token_directory_is_not_rescued_by_the_fingerprint_tier(tmp_path):
    """AC9's sharper half. If tier 3 could pick up a token-carrying directory that failed the NNNN
    gate, the gate would be decorative -- the same directory would come back through the next door."""
    work = make_pair(tmp_path)
    add_tracked(work, {
        "notes/decisions/monday.md": NYGARD,
        "notes/decisions/tuesday.md": NYGARD,
    })
    p = run(work)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "notes/decisions" not in p.stdout


def test_AC10_nygard_fingerprint(tmp_path):
    """AC10, the measured family: `^## Consequences`, measured on a real repository's
    decision records."""
    work = make_pair(tmp_path)
    add_tracked(work, {"docs/why/a.md": NYGARD, "docs/why/b.md": NYGARD})
    p = run(work)
    assert p.returncode == 1
    assert "docs/why/" in p.stdout
    assert "evidence tier: content fingerprint" in p.stdout


def test_AC10_madr_fingerprint_has_a_fixture_and_therefore_ships(tmp_path):
    """AC10, the UNMEASURED family. MADR v4 shares almost no literal strings with Nygard, so a
    single-family fingerprint is blind to the most-cited ADR specification. A repository can contain
    zero occurrences of `MADR`, `Decision Outcome` or `Considered Options`, so this family could have no
    positive control anywhere -- it does not ship without one. This is that control."""
    work = make_pair(tmp_path)
    add_tracked(work, {"docs/rationale/a.md": MADR, "docs/rationale/b.md": MADR})
    p = run(work)
    assert p.returncode == 1
    assert "docs/rationale/" in p.stdout
    assert "evidence tier: content fingerprint" in p.stdout


def test_a_single_fingerprint_match_is_a_note_not_a_finding(tmp_path):
    """Measured the first time the scan ran on a second repository: it fired on this project's own
    `references/` directory, which holds PROSE ABOUT the ADR format and not one ADR. A directory
    that keeps records accumulates more than one; a document that describes the format is one file.

    The cost is a real false negative -- a project with exactly one record, in a directory named
    none of the tokens -- and it is carried in the report rather than hidden."""
    work = make_pair(tmp_path)
    add_tracked(work, {"docs/guide/format.md": NYGARD})
    p = run(work)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "docs/guide/" in p.stdout
    assert "too weak to" in p.stdout


def test_AC11_every_decisions_row_names_its_tier(tmp_path):
    """AC11. The tier is how a human weighs the row; a path printed without one asks the reader to
    re-derive the check's own reasoning."""
    work = make_pair(tmp_path)
    add_tracked(work, {
        "docs/adr/0001-a.md": "# a\n",
        "docs/rationale/a.md": MADR,
        "docs/rationale/b.md": MADR,
    })
    p = run(work)
    rows = [l for l in p.stdout.split("\n") if l.strip().startswith("[decisions]")]
    assert len(rows) >= 2, p.stdout
    for row in rows:
        assert "evidence tier:" in row, f"row without a tier: {row!r}"


def test_the_scan_does_not_run_on_a_stale_tree(tmp_path):
    """A report that printed a branch finding and a decisions finding
    side by side would be wrong: a tree already known to be stale hides the very decision
    records the scan would look for. Scanning a tree
    already known to be the wrong one is the thing this phase exists to stop."""
    work = make_pair(tmp_path, behind=3)
    add_tracked(work, {"docs/adr/0001-a.md": "# a\n"})
    p = run(work)
    assert p.returncode == 1
    assert "[branch]" in p.stdout
    assert "[decisions]" not in p.stdout, "the scan ran on a tree the gate did not clear"
    assert "not scanned" in p.stdout


def test_the_two_count_disclosures_are_printed_with_the_rows(tmp_path):
    """The two count-disclosure risks, made falsifiable once found to be
    a narrative promise with no test behind them."""
    work = make_pair(tmp_path)
    add_tracked(work, {"docs/adr/0001-a.md": "# a\n"})
    p = run(work)
    assert "SHAPE matches" in p.stdout
    assert "de-duplicates nothing across" in p.stdout


def test_untracked_files_are_invisible_to_the_scan(tmp_path):
    """The detection contract's own rule: tracked files only. Vendored and installed directories are
    normally untracked, and a scan that counted them would report somebody else's ADRs as this
    project's."""
    work = make_pair(tmp_path)
    d = work / "node_modules" / "pkg" / "docs" / "decisions"
    d.mkdir(parents=True)
    (d / "0001-theirs.md").write_text("# theirs\n")
    p = run(work)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "node_modules" not in p.stdout


# ===========================================================================
# The roadmap note (AC12), the one suppressed draft (AC17), and the
# false-negative floor (AC13).
# ===========================================================================


def test_AC12_a_roadmap_is_a_note_with_the_fixed_caveat(tmp_path):
    """AC12. Roadmaps have no marker file, no stable filename convention and no stable content
    shape, so none of the three ADR techniques transfers. The caveat is a FIXED string so a test can
    pin it -- softening it later then becomes a visible edit rather than a drift."""
    work = make_pair(tmp_path)
    add_tracked(work, {"docs/engineering/roadmap.md": "# roadmap\n"})
    p = run(work)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "docs/engineering/roadmap.md" in p.stdout
    assert "a file with this name exists;" in p.stdout
    assert "whether it is maintained was not checked" in p.stdout
    assert "[roadmap]" not in p.stdout, "a roadmap match is a note, never a finding"


def test_AC17_a_roadmap_only_match_does_not_stop_the_pass(tmp_path):
    """AC17. Halting on a name-only signal would fire on every repository carrying a long-dead
    ROADMAP.md, and a gate that stops that often gets read as noise."""
    work = make_pair(tmp_path)
    add_tracked(work, {"ROADMAP.md": "# r\n"})
    p = run(work)
    assert p.returncode == 0, p.stdout + p.stderr


def test_AC17_the_competing_draft_is_named_as_withheld(tmp_path):
    """AC17. Drafting anyway reproduces the exact failure -- a competing draft written over a
    maintained file. Suppressing the one draft aims at the harm and not at the pass; and a pass that
    silently produced one fewer artifact than its own contract lists would read as a bug, so the
    headline carries the count."""
    work = make_pair(tmp_path)
    add_tracked(work, {"ROADMAP.md": "# r\n"})
    p = run(work)
    assert "5 of 6 drafts" in p.stdout
    assert "docs/ROADMAP.md will NOT be written" in p.stdout


def test_AC17_no_roadmap_means_no_suppression_claim(tmp_path):
    """The negative control. Without it, a script that ALWAYS claimed suppression would pass the
    test above."""
    work = make_pair(tmp_path)
    p = run(work)
    assert "will NOT be written" not in p.stdout
    assert "5 of 6" not in p.stdout


def test_the_collapse_rule_is_one_row_with_every_path_under_it(tmp_path):
    """Decided after the first draft was found to restate two options with
    an "or" and call that a decision. One row regardless of N; every path kept, because the story's
    Contingencies forbid silent truncation."""
    work = make_pair(tmp_path)
    add_tracked(work, {
        "packages/a/ROADMAP.md": "# a\n",
        "packages/b/ROADMAP.md": "# b\n",
        "packages/c/roadmap.md": "# c\n",
    })
    p = run(work)
    headers = [l for l in p.stdout.split("\n") if l.strip().startswith("roadmap ")]
    assert len(headers) == 1, f"expected one collapsed row, got {headers}"
    assert "3 file(s) match by name" in p.stdout
    for path in ("packages/a/ROADMAP.md", "packages/b/ROADMAP.md", "packages/c/roadmap.md"):
        assert path in p.stdout, f"{path} was truncated away"


def test_the_roadmap_match_is_a_name_not_a_substring(tmp_path):
    """The first version matched `*roadmap*` against every tracked path and returned scripts,
    invariants, test files and a rules file. A net fired at the product, the same
    shape as the fingerprint tier's false positive."""
    work = make_pair(tmp_path)
    add_tracked(work, {
        "scripts/gen-roadmap-fixtures.py": "x = 1\n",
        "scripts/roadmap-batchmap-status.sh": "echo hi\n",
        "docs/ROADMAP.md": "# real\n",
    })
    p = run(work)
    assert "1 file(s) match by name" in p.stdout
    assert "gen-roadmap-fixtures.py" not in p.stdout
    assert "roadmap-batchmap-status.sh" not in p.stdout


def test_AC13_the_floor_prints_on_every_shape(tmp_path):
    """AC13. A clean report that does not carry the floor is the most dangerous shape this check can
    produce: it reads as a statement about the repository when it is a statement about the check."""
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    clean = make_pair(tmp_path / "a")
    stale = make_pair(tmp_path / "b", behind=2)
    for repo, code in ((clean, 0), (stale, 1)):
        p = run(repo)
        assert p.returncode == code, p.stdout + p.stderr
        assert "Signatures checked:" in p.stdout
        assert "is invisible to this check" in p.stdout
        assert "never about your repository" in p.stdout


def test_AC13_the_floor_is_generated_from_the_table_the_check_reads(tmp_path):
    """A hand-copied floor goes stale the moment a
    signature is added -- it then either over-claims safety or warns about a gap already closed,
    with nothing catching the drift.

    The test asserts AGREEMENT, not wording: every value in the shell table must appear in the
    printed floor. A floor that dropped one would pass a `"Signatures checked" in stdout` assertion."""
    src = SCRIPT.read_text()
    table = {}
    for key in ("ADR_MARKERS", "ADR_DIR_TOKENS", "ADR_FILENAME_SHAPE", "ADR_FINGERPRINTS"):
        line = [l for l in src.split("\n") if l.startswith(f"{key}=")][0]
        table[key] = line.split("=", 1)[1].strip().strip('"')

    work = make_pair(tmp_path)
    out = run(work).stdout

    for marker in table["ADR_MARKERS"].split():
        assert marker in out, f"{marker} is in the table and not in the floor"
    for token in table["ADR_DIR_TOKENS"].split():
        assert token in out, f"{token} is in the table and not in the floor"
    assert table["ADR_FILENAME_SHAPE"] in out
    for fp in table["ADR_FINGERPRINTS"].split("|"):
        assert fp in out, f"{fp} is in the table and not in the floor"


def test_AC13_the_floor_names_the_false_negative_the_threshold_created(tmp_path):
    """The single-match threshold introduced earlier creates a false negative -- exactly one record,
    in a directory named none of the tokens. A threshold that creates a blind spot must say so where
    the blind spots are listed, or the floor is itself a claim wider than the mechanism."""
    work = make_pair(tmp_path)
    out = run(work).stdout
    assert "exactly ONE record" in out


# ===========================================================================
# The call site. AC2 (a finding produces zero drafts) and AC1's second
# clause (exit 0 continues).
#
# WHAT THESE CAN AND CANNOT PROVE, said once and not repeated per test: the
# pass is prose, so the "call site" is a section of `references/archaeology.md`.
# These pin what that section SAYS. Nothing here proves an agent reading it
# obeys -- and the measured run that motivated this whole phase is the evidence
# that prose instructions do not always bind. That gap is why the section
# states it about itself too.
# ===========================================================================

PASS_DOC = REPO / "skills/project-lifecycle/references/archaeology.md"


def pass_doc_flat():
    """Wrapped prose: a phrase a human reads as one sentence can carry a newline in the middle of
    it. An assertion that cannot cross a line break is testing the line width, not the content --
    caught when a correct sentence failed its own test."""
    import re
    return re.sub(r"\s+", " ", PASS_DOC.read_text())


# The call sites are anchored to the plugin root now --
# `bash "${CLAUDE_PLUGIN_ROOT}/scripts/archaeology-preflight.sh" detect` -- so a closing quote sits
# between the script name and its subcommand. These two rows used fixed strings and therefore
# asserted a BYTE SEQUENCE where the AC is about a PROPERTY ("the document points at the runnable
# source"). They reddened correct documents the moment the spelling changed, which is the
# same shape `scripts/invariants/adoption-rule-single-source.sh` was corrected for in the same
# phase. Matching the subcommand is still required, so a document that merely names the script
# does not satisfy either row.
def _points_at(text: str, subcommand: str) -> bool:
    return re.search(r'archaeology-preflight\.sh"?\s+' + re.escape(subcommand), text) is not None


def test_AC2_the_call_site_names_all_three_exit_codes():
    """AC2. A caller that knows only "worked / did not work" cannot honour the contract: a
    stale branch and a broken repository would produce the same message and the report body would
    never be shown."""
    doc = PASS_DOC.read_text()
    assert _points_at(doc, "check"), "the pass never invokes the pre-flight"
    for code in ("`0`", "`1`", "`3`"):
        assert code in doc, f"exit {code} is not named at the call site"


def test_AC2_a_finding_means_zero_drafts_at_the_call_site():
    doc = PASS_DOC.read_text()
    assert "Produce zero drafts" in doc
    assert doc.count("Produce zero drafts") >= 2, (
        "both stopping codes (1 and 3) must say zero drafts; one of them is missing"
    )


def test_exit_three_is_not_reported_as_nothing_found():
    """`3` says the check could not run. Reporting it as "nothing was found" is the exact
    reclassification -- "the check never ran" into "the check ran and found nothing" -- that the
    third exit code exists to make impossible."""
    doc = pass_doc_flat()
    assert 'never "nothing was found"' in doc


def test_AC1_second_clause_the_pass_continues_on_zero():
    """AC1's second clause. Every stop-path assertion in this file would stay green while a
    pre-flight halted a perfectly healthy repository; this is the one that would not."""
    doc = pass_doc_flat()
    assert "**continue** to the fan-out" in doc
    assert "only after the pre-flight above exited `0`" in doc


def test_the_call_site_forbids_the_truthiness_idiom():
    """A rule, not a suggestion. `if preflight; then` is the idiom a reader
    reaches for by default, so the document has to say not to -- and a positive control proves this
    assertion can fire."""
    doc = pass_doc_flat()
    assert "Never on truthiness" in doc
    assert "collapses" in doc
    # positive control: the assertion above must be capable of failing
    assert "Never on truthiness" not in "if preflight; then echo ok; fi"


def test_AC17_the_withheld_draft_is_named_at_the_call_site():
    """AC17 reaches the pass, not only the report. A pre-flight that says a draft is withheld, read
    by a pass that writes all six anyway, has changed nothing."""
    doc = pass_doc_flat()
    assert "will not be written" in doc
    assert "other five artifacts" in doc


def test_the_call_site_admits_what_it_cannot_enforce():
    """The section claims prose cannot be proven to bind, and that claim is itself load-bearing --
    it is the reason the detection moved into code. A version that dropped it would read as if
    running the script were guaranteed."""
    doc = pass_doc_flat()
    assert "cannot enforce" in doc
    assert "leaves the *invocation* in prose" in doc


# ===========================================================================
# One executable source for the adoption rule. AC14, AC15, AC16, plus
# the requirement that `detect` REPLACES the routing read.
# ===========================================================================

GUARD = REPO / "scripts/invariants/adoption-rule-single-source.sh"
SITES = [
    "skills/project-lifecycle/SKILL.md",
    "skills/project-lifecycle/references/archaeology.md",
    "commands/init-harness.md",
    "skills/project-lifecycle/references/init-harness.md",
    "skills/project-lifecycle/references/onboarding.md",
]


def run_guard():
    return subprocess.run(["/bin/bash", str(GUARD)], capture_output=True, text=True, cwd=REPO)


def test_AC14_exactly_one_block_holds_the_rule():
    """AC14. The lists live in one executable place. Two blocks is the dangerous shape, not zero:
    zero is a broken file anybody notices on the next run, two reads fine to a human while a reader
    silently picks one -- the same fact written twice with consumers landing on the stale copy."""
    body = SCRIPT.read_text()
    token = "plc-adoption" + "-rule"
    assert body.count(token + ":begin") == 1
    assert body.count(token + ":end") == 1
    for key in ("ADOPTION_ANCHORS", "ADOPTION_MANIFESTS", "ADOPTION_SOURCE_EXTS", "ADOPTION_WHITELIST"):
        assert f"{key}=" in body, f"{key} is not in the single source"


def test_AC15_every_site_points_at_the_script_instead_of_restating():
    """AC15. Five sites refer to the decision; each must point at the runnable source."""
    for site in SITES:
        text = (REPO / site).read_text()
        assert _points_at(text, "detect"), f"{site} does not point at the script"


def test_AC15_the_file_that_held_the_lists_no_longer_does():
    """AC15's sharper half. `references/archaeology.md` carried the manifest table, the extension
    list and the whitelist. It may describe the SHAPE; it may not carry the lists."""
    text = (REPO / "skills/project-lifecycle/references/archaeology.md").read_text()
    manifests = ["package.json", "Cargo.toml", "pyproject.toml", "go.mod",
                 "pom.xml", "Gemfile", "composer.json", "mix.exs"]
    hits = [m for m in manifests if m in text]
    assert len(hits) < 3, f"the manifest list moved back into prose: {hits}"


def test_AC16_the_guard_passes_on_the_real_tree():
    proc = run_guard()
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "one block in" in proc.stdout


def test_AC16_a_vanished_site_is_a_failure_not_a_skip(tmp_path):
    """AC16's first falsifier was only "paste a token back", never
    "a listed site disappears". A guard that quietly stops checking a deleted location shrinks its
    own coverage with nobody noticing."""
    body = GUARD.read_text()
    assert "does not exist -- a vanished site is a failure, not a skip" in body
    # and it must actually branch on existence, not merely mention it
    assert 'if [ ! -f "$site" ]; then' in body


def test_the_guard_runs_the_shipped_detect_not_a_second_parser():
    """A second parser can be green while the product is broken -- the proxy-versus-real-thing
    defect this repo keeps rediscovering. The guard must INVOKE the script."""
    body = GUARD.read_text()
    assert '"$SCRIPT" detect --repo' in body
    assert "adoption-entry" in body and "new-project" in body


def test_the_guard_does_not_count_itself():
    """Measured: the guard's first run reported TWO definitions of a rule defined once, and the
    second file was the guard, because its own comments spelled the sentinel out. Same collision
    a sibling guard documented. The token is assembled at runtime instead."""
    body = GUARD.read_text()
    token = "plc-adoption" + "-rule"
    assert token + ":begin" not in body, "the guard spells the sentinel and will count itself"
    assert 'BEG="${TOK}:begin"' in body


def test_detect_answers_both_shapes(tmp_path):
    """Does `detect` REPLACE the routing read or mirror it? It
    replaces it, and these are the fixtures that make that checkable.

    WHAT NO TEST HERE REACHES, stated rather than glossed: whether an agent routing a real adoption
    entry actually RUNS this. That is a prose instruction, and no test in this repository can prove
    a model obeyed one."""
    brown = tmp_path / "brown"
    brown.mkdir()
    git(brown, "init", "-q", "--initial-branch=main")
    _identity(brown)
    (brown / "package.json").write_text("{}\n")
    (brown / "src").mkdir()
    (brown / "src" / "a.ts").write_text("x\n")
    git(brown, "add", "-A")
    git(brown, "commit", "-qm", "f")

    green = tmp_path / "green"
    green.mkdir()
    git(green, "init", "-q", "--initial-branch=main")
    _identity(green)
    (green / "README.md").write_text("# x\n")
    git(green, "add", "-A")
    git(green, "commit", "-qm", "f")

    for repo, want in ((brown, "adoption-entry"), (green, "new-project")):
        p = subprocess.run(
            ["/bin/bash", str(SCRIPT), "detect", "--repo", str(repo)],
            capture_output=True, text=True,
        )
        assert p.returncode == 0, p.stdout + p.stderr
        assert p.stdout.split()[0] == want, f"{repo.name}: {p.stdout!r}"


def test_detect_says_why_not_only_what(tmp_path):
    """A classification with no reason forces the reader to re-derive it, which is the thing the
    single source exists to stop."""
    brown = tmp_path / "b"
    brown.mkdir()
    git(brown, "init", "-q", "--initial-branch=main")
    _identity(brown)
    (brown / "Cargo.toml").write_text("[package]\n")
    git(brown, "add", "-A")
    git(brown, "commit", "-qm", "f")
    p = subprocess.run(["/bin/bash", str(SCRIPT), "detect", "--repo", str(brown)],
                       capture_output=True, text=True)
    assert "Cargo.toml" in p.stdout, "detect named no evidence for its answer"


def test_detect_treats_an_existing_anchor_as_new_project(tmp_path):
    """Condition 1. A repo already keeping `docs/RESUME.md` must NOT fire the adoption entry -- the
    either-location rule, which is now read from the block rather than restated in five files."""
    repo = tmp_path / "r"
    repo.mkdir()
    git(repo, "init", "-q", "--initial-branch=main")
    _identity(repo)
    (repo / "package.json").write_text("{}\n")
    (repo / "docs").mkdir()
    (repo / "docs" / "RESUME.md").write_text("# resume\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "f")
    p = subprocess.run(["/bin/bash", str(SCRIPT), "detect", "--repo", str(repo)],
                       capture_output=True, text=True)
    assert p.stdout.split()[0] == "new-project", p.stdout
    assert "docs/RESUME.md" in p.stdout


# ===========================================================================
# Review findings, all reproduced before being
# accepted, all of them inputs the mutants never constructed -- which is
# the point: a mutation matrix attacks the code that exists, not the guarantees
# stated in prose beside it.
# ===========================================================================


def test_a_dash_leading_directory_still_obeys_AC9(tmp_path):
    """`grep -qxF "$dir"` parses a `$dir` beginning with `-` as an
    OPTION: macOS grep reads `-decisions` as an abbreviated `--directories`, exits 2, and
    `2>/dev/null || true` swallows that into "no match". Both dedup guards in the fingerprint tier
    then failed at once, so a token-carrying directory with no `NNNN-*.md` was reported after all --
    AC9's guarantee is that it is reported by NOTHING -- and when it DID carry NNNN files the same
    directory printed twice, once as a finding and once as a contradicting note.

    Measured at the mechanism, not inferred: `grep -qxF "-decisions" f` prints
    `grep: unknown --directories option` and exits 2; with `--` it exits 1, the correct "not found"."""
    work = make_pair(tmp_path)
    add_tracked(work, {"-decisions/a.md": NYGARD, "-decisions/b.md": NYGARD})
    p = run(work)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "-decisions" not in p.stdout


def test_a_dash_leading_directory_is_reported_once_not_twice(tmp_path):
    """The second half of the same defect. With `NNNN-*.md` present, tier 2 reports it AND tier 3's
    dedup missed it, so one directory produced two contradicting lines in one report."""
    work = make_pair(tmp_path)
    add_tracked(work, {
        "-decisions/0001-a.md": NYGARD,
        "-decisions/0002-b.md": NYGARD,
    })
    p = run(work)
    assert p.returncode == 1, p.stdout + p.stderr
    assert p.stdout.count("-decisions") == 1, f"reported more than once:\n{p.stdout}"
    assert "too weak to" not in p.stdout


def test_a_glob_manifest_does_not_match_by_coincidence(tmp_path):
    """The glob arm converted `*` to `[^/]*` and left every other
    metacharacter live, so `*.csproj` became `(^|/)[^/]*.csproj$` -- an unescaped `.` matching ANY
    character. `src/fooXcsproj`, with no dot in its name at all, was classified as a recognised
    manifest, flipping `new-project` to `adoption-entry`.

    The fix is not a better escape: the second attempt escaped with `sed` and produced a BROKEN sed
    expression whose stderr became the "classification" (`sed:`) -- a wrong answer dressed as an
    answer. `case` is glob-native, so no conversion happens at all."""
    repo = tmp_path / "r"
    repo.mkdir()
    git(repo, "init", "-q", "--initial-branch=main")
    _identity(repo)
    for rel in ("src/fooXcsproj", "a/b/buildXgradleXkts", "x/fooXsln"):
        f = repo / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "f")
    p = subprocess.run(["/bin/bash", str(SCRIPT), "detect", "--repo", str(repo)],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    assert p.stdout.split()[0] == "new-project", p.stdout


def test_a_real_glob_manifest_still_matches(tmp_path):
    """The positive control for the fix above. Narrowing a matcher until the false positive stops is
    worthless if the true positive stops with it."""
    for name in ("Real.csproj", "build.gradle.kts", "App.sln"):
        repo = tmp_path / name.replace(".", "_")
        repo.mkdir()
        git(repo, "init", "-q", "--initial-branch=main")
        _identity(repo)
        f = repo / "src" / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "f")
        p = subprocess.run(["/bin/bash", str(SCRIPT), "detect", "--repo", str(repo)],
                           capture_output=True, text=True)
        assert p.stdout.split()[0] == "adoption-entry", f"{name}: {p.stdout!r}"


def test_the_guard_sees_a_duplicate_sentinel_in_any_file_type(tmp_path):
    """Arm 1 passed `--include='*.sh' --include='*.md'` while the
    guard's header claims the pair is unique "in the repository". A duplicate in a `.json` file was
    invisible and the guard printed `ok` -- an undisclosed third blind spot next to the two it does
    disclose. The scan is no longer limited by extension.

    Also fixed while proving it: `--` belongs AFTER the options. `grep -rlF -- "$BEG" --include=...`
    turns the `--include` flags into file operands, which is how this was caught -- the guard failed
    in a new way rather than being read carefully."""
    # SCOPED TO THE COMMAND LINE, NOT THE FILE. The first version of this assertion searched the
    # whole file for `--include=` and fired on the COMMENT that documents this very fix -- a net
    # aimed at the product, which is a known shape.
    lines = [l for l in GUARD.read_text().split("\n")
             if l.startswith("begins=") or (l.strip().startswith("/usr/bin/grep") and "$BEG" in l)]
    assert lines, "the sentinel scan line was not found -- this assertion is measuring nothing"
    for l in lines:
        assert "--include=" not in l, f"the scan is still limited by file extension: {l}"
        # `--` must come AFTER the options: `grep -rlF -- PAT --include=X` reads --include as a file
        if " -- " in l:
            after = l.split(" -- ", 1)[1]
            assert "--include" not in after and "--exclude" not in after, (
                f"an option sits after `--` and will be read as a filename: {l}"
            )

    # NO BEHAVIOURAL HALF, and the reason is stated rather than left as a gap: proving it by
    # behaviour means writing a second sentinel into the repository the guard scans, which is a
    # write into the tree under test. The review did exactly that by hand and cleaned up after
    # itself; a test in the suite should not.


def test_the_second_dedup_also_survives_a_dash_leading_path(tmp_path):
    """The mutant that survived the first run of this batch, and why it survived is the finding.

    There are TWO dedup guards in the fingerprint tier: one against the token directories, one
    against what tier 1 already reported. The dash-leading test above only reaches the FIRST -- its
    directory carries a token, so the loop `continue`s before the second guard runs. Removing `--`
    from the second guard therefore changed nothing and the mutant lived.

    The second guard is reached only when a path is in `reported` and NOT a token directory, which
    is exactly what a MARKER FILE produces: `.adr-dir` may name any directory at all. So this
    fixture is a marker naming a dash-leading directory with no token in its name, holding two
    fingerprint files. Without `--`, the dedup misses and one directory is reported twice."""
    work = make_pair(tmp_path)
    add_tracked(work, {
        ".adr-dir": "-notes\n",
        "-notes/a.md": NYGARD,
        "-notes/b.md": NYGARD,
    })
    p = run(work)
    assert p.returncode == 1, p.stdout + p.stderr
    assert p.stdout.count("-notes") == 1, f"reported more than once:\n{p.stdout}"
