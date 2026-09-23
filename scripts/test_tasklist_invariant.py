"""The tasklist is guarded at the path actually configured.

The defect: `.gitignore` names `/.claude/tasklist.md` at exactly one path while the writer resolves
``${PLC_TASKLIST_FILE:-.claude/tasklist.md}`` and can be pointed anywhere, and without `tasklist-never-tracked.sh` no
invariant mentioned `tasklist` at all. A committed tasklist — session nonce plus per-phase working
state — passed every declared check.

Every fixture below builds a REAL git repository and runs the REAL scripts. A model of
`git check-ignore` would be exactly the kind of proxy that hides the defect: the
whole criterion set is about git's own answers, and its exit-code contract (0 ignored, 1 not,
128 fatal) is the thing under test.
"""

from close_gate_lib import assert_fixture_is_its_own_repo
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
INVARIANT = REPO / "scripts" / "invariants" / "tasklist-never-tracked.sh"
GUARD_DIR = REPO / "scripts" / "tasklist-guard-dir.sh"


def mkrepo(tmp_path: Path, ignore_body: str = "/.claude/tasklist.md\n") -> Path:
    root = tmp_path / "repo"
    root.mkdir()

    def g(*a):
        subprocess.run(["/usr/bin/git", *a], cwd=str(root), check=True, capture_output=True)

    g("init", "-q", "-b", "main")
    g("config", "user.email", "t@example.invalid")
    g("config", "user.name", "t")
    (root / ".gitignore").write_text(ignore_body)
    (root / ".claude").mkdir()
    (root / ".claude" / "settings.json").write_text("{}\n")
    (root / "README.md").write_text("x\n")
    g("add", "-A")
    g("commit", "-q", "-m", "fixture")
    return root


def run_inv(root: Path, env_extra: dict | None = None, arg: str | None = None):
    env = {**os.environ, **(env_extra or {})}
    env.pop("PLC_TASKLIST_FILE", None)
    if env_extra and "PLC_TASKLIST_FILE" in env_extra:
        env["PLC_TASKLIST_FILE"] = env_extra["PLC_TASKLIST_FILE"]
    cmd = ["/bin/bash", str(INVARIANT)]
    if arg:
        cmd.append(arg)
    return subprocess.run(cmd, cwd=str(root), capture_output=True, text=True, env=env)


def run_guard(root: Path, rel: str):
    return subprocess.run(
        ["/bin/bash", str(GUARD_DIR), rel], cwd=str(root), capture_output=True, text=True
    )


def track(root: Path, rel: str):
    # p33 — refuse to commit into anything but this fixture. One line here covers every
    # call site this helper serves; see close_gate_lib for why the check is on the git dir
    # and not the top level, and why it is insurance rather than a fix for a measured path.
    assert_fixture_is_its_own_repo(root)
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("- [ ] a task\nnonce: abc123\n")
    subprocess.run(
        ["/usr/bin/git", "add", "-f", rel], cwd=str(root), check=True, capture_output=True
    )
    subprocess.run(
        ["/usr/bin/git", "commit", "-q", "-m", f"track {rel}"],
        cwd=str(root), check=True, capture_output=True,
    )


# ------------------------------------------------------------------ the configured path


def test_the_default_path_is_ignored_and_untracked(tmp_path):
    root = mkrepo(tmp_path)
    r = run_inv(root)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "PASS tasklist-never-tracked" in r.stdout


def test_a_configured_path_is_checked_at_the_configured_location(tmp_path):
    """The whole point. `.gitignore` covers the default and nothing else, so an override into an
    uncovered path must FAIL — the criterion is about the path actually in use, not the one written
    down in 2026."""
    root = mkrepo(tmp_path)
    r = run_inv(root, {"PLC_TASKLIST_FILE": "work/tasklist.md"})
    assert r.returncode == 1, r.stdout
    assert "is NOT ignored" in r.stdout
    assert "work/tasklist.md" in r.stdout


def test_a_configured_path_passes_once_its_directory_carries_the_marker(tmp_path):
    """The other half of the row above, and the control that keeps it from being satisfied by
    'any override fails'. Same override, after the guard places its marker: PASS."""
    root = mkrepo(tmp_path)
    g = run_guard(root, "work/tasklist.md")
    assert g.returncode == 0, g.stdout + g.stderr
    assert (root / "work" / ".gitignore").read_text().strip() == "*"
    r = run_inv(root, {"PLC_TASKLIST_FILE": "work/tasklist.md"})
    assert r.returncode == 0, r.stdout + r.stderr


def test_a_tracked_tasklist_at_the_default_path_reds(tmp_path):
    """The first of two tracked-tasklist fixtures. `git add -f` is what a real accident
    looks like — and note the ignore rule still passes here, because TRACKED BEATS IGNORED. A check
    that only asked `check-ignore` would report green over a committed tasklist."""
    root = mkrepo(tmp_path)
    track(root, ".claude/tasklist.md")
    r = run_inv(root)
    assert r.returncode == 1, r.stdout
    assert "is git-tracked" in r.stdout
    assert ".claude/tasklist.md" in r.stdout


def test_a_tracked_tasklist_at_a_configured_path_reds(tmp_path):
    """The second tracked-tasklist fixture. The tracked-anywhere check must follow the override too, or it
    only guards the one path .gitignore already guarded."""
    root = mkrepo(tmp_path)
    run_guard(root, "work/tasklist.md")
    track(root, "work/tasklist.md")
    r = run_inv(root, {"PLC_TASKLIST_FILE": "work/tasklist.md"})
    assert r.returncode == 1, r.stdout
    assert "is git-tracked" in r.stdout


# ------------------------------------------------------------------ no broad sweep


def test_no_broad_tasklist_sweep_over_ls_files(tmp_path):
    """No broad sweep, asserted BEHAVIOURALLY rather than by grepping the script for a forbidden string.

    The false positive to rule out is concrete: this repo really does track
    `scripts/tasklist-view.sh`, its test, and a command doc. A sweep for `*tasklist*` over
    `git ls-files` would red on all three. The fixture plants exactly that shape — tracked files
    whose names contain `tasklist` but which are not tasklists — and requires a PASS.
    """
    root = mkrepo(tmp_path)
    (root / "scripts").mkdir()
    for name in ("tasklist-view.sh", "tasklist-view.test.sh", "my-tasklist-notes.md"):
        (root / "scripts" / name).write_text("# not a tasklist artifact\n")
    subprocess.run(["/usr/bin/git", "add", "-A"], cwd=str(root), check=True, capture_output=True)
    subprocess.run(
        ["/usr/bin/git", "commit", "-q", "-m", "tooling"], cwd=str(root), check=True, capture_output=True
    )
    r = run_inv(root)
    assert r.returncode == 0, (
        "a tracked file merely NAMED like a tasklist reddened the invariant — that is the broad "
        f"sweep this invariant forbids:\n{r.stdout}"
    )


def test_the_script_pins_paths_rather_than_globbing(tmp_path):
    """The structural companion to the behavioural row above. Both are kept: the behavioural one
    can pass against an implementation that globs but happens not to match the fixture, and this one
    can pass against an implementation that pins the wrong paths."""
    src = INVARIANT.read_text()
    assert "PLC_TASKLIST_FILE:-.claude/tasklist.md" in src, "the override is not being resolved"

    # Read CODE, not prose. The first version scanned the whole file and went red on the script's
    # own header, which spells the forbidden glob while explaining that it does not use it -- the
    # same shape gate-jq-only-envelope.sh records about itself: a checker cannot lexically scan a
    # file that necessarily names the token in order to say why it is banned.
    code = "\n".join(
        ln.split(" #", 1)[0] for ln in src.splitlines() if not ln.lstrip().startswith("#")
    )
    assert code.strip(), "comment-stripping left no code at all -- the filter is wrong"
    assert "*tasklist*" not in code, (
        "the invariant globs for *tasklist*, which is forbidden: this repo tracks "
        "tasklist-view.sh and friends, and a sweep reds on all of them"
    )
    assert "ls-files" in code, "the tracked-anywhere check disappeared from the code"


# ------------------------------------------------------------------ marker placement


def test_no_marker_is_written_into_a_preexisting_directory(tmp_path):
    """Fixture (a). Dropping an ignore-everything file into a directory the user already had would
    silently un-track their work — a far worse outcome than an unprotected tasklist."""
    root = mkrepo(tmp_path)
    (root / "src").mkdir()
    (root / "src" / "keep.py").write_text("x = 1\n")
    g = run_guard(root, "src/tasklist.md")
    assert g.returncode == 0, g.stdout + g.stderr
    assert not (root / "src" / ".gitignore").exists(), (
        "a marker was written into a pre-existing source directory"
    )
    assert "already exists" in g.stdout


def test_the_ambiguous_middle_case_marks_only_the_leaf_it_created(tmp_path):
    """Fixture (b) — the case that must have a recorded behaviour
    rather than a reading, because the check originally tested
    only the negative case.

    `.claude/scratch/tasklist.md` with `.claude/` present and `scratch/` absent. The resolution is
    THE LEAF, never the whole path: `.claude/` often holds configuration such as settings.json that is
    tracked, so a marker there would ignore it.
    """
    root = mkrepo(tmp_path)
    assert (root / ".claude").is_dir() and not (root / ".claude" / "scratch").exists()

    g = run_guard(root, ".claude/scratch/tasklist.md")
    assert g.returncode == 0, g.stdout + g.stderr

    assert (root / ".claude" / "scratch" / ".gitignore").read_text().strip() == "*", (
        "the leaf this script created was not marked"
    )
    assert not (root / ".claude" / ".gitignore").exists(), (
        "the PRE-EXISTING parent was marked — that would ignore settings.json and close-gate.json"
    )

    # And the consequence that makes it worth pinning: the parent's tracked files stay visible.
    out = subprocess.run(
        ["/usr/bin/git", "check-ignore", "-q", "--", ".claude/settings.json"],
        cwd=str(root), capture_output=True,
    )
    assert out.returncode == 1, "a tracked file in the pre-existing parent became ignored"


def test_an_existing_marker_is_never_overwritten(tmp_path):
    root = mkrepo(tmp_path)
    (root / "work").mkdir()
    (root / "work" / ".gitignore").write_text("# somebody's decision\n!keep.txt\n")
    g = run_guard(root, "work/tasklist.md")
    assert g.returncode == 0
    assert "somebody's decision" in (root / "work" / ".gitignore").read_text()


def test_a_bare_filename_gets_no_marker(tmp_path):
    """`PLC_TASKLIST_FILE=tasklist.md` puts the artifact in the cwd, which this script certainly did
    not create. Marking it would ignore the entire repository."""
    root = mkrepo(tmp_path)
    g = run_guard(root, "tasklist.md")
    assert g.returncode == 0
    assert not (root / ".gitignore").read_text().strip() == "*"
    assert "did not create" in g.stdout


# ------------------------------------------------------------------ could not run


def test_a_broken_git_environment_reports_could_not_run_not_a_finding(tmp_path):
    """Exit 128 is the CHECK failing; exit 1 is a finding about the repo. Treating
    'any nonzero' as 'not ignored' turns an environment bug into a confident, false claim.

    Run outside any work tree, which is what a wrong cwd or an unset GIT_DIR produces in practice.
    """
    outside = tmp_path / "not-a-repo"
    outside.mkdir()
    env = {**os.environ, "GIT_CEILING_DIRECTORIES": str(tmp_path)}
    env.pop("PLC_TASKLIST_FILE", None)
    r = subprocess.run(
        ["/bin/bash", str(INVARIANT)],
        cwd=str(outside), capture_output=True, text=True, env=env,
    )
    assert r.returncode == 3, (
        f"could-not-run must exit 3, not {r.returncode}. `!= 0` was the old assertion and it "
        f"could not tell the third verdict from an ordinary finding — deleting the third verdict "
        f"outright would have left it green:\n{r.stdout}"
    )
    assert "COULD NOT RUN" in r.stdout, (
        f"a check that could not run reported as though it had:\n{r.stdout}"
    )
    assert "is NOT ignored" not in r.stdout, (
        "an environment failure was reported as a finding about the repository"
    )


def test_an_ordinary_finding_still_exits_1_not_3(tmp_path):
    """The control that makes the row above mean something. Without it, exit 3 could be what this
    script returns for everything, and asserting 3 on the broken-environment path would prove
    nothing about the distinction."""
    root = mkrepo(tmp_path)
    (root / "deep").mkdir()
    r = run_inv(root, {"PLC_TASKLIST_FILE": "deep/tasklist.md"})
    assert r.returncode == 1, (
        f"a real finding about the repo must be exit 1, distinct from could-not-run's 3:\n{r.stdout}"
    )
    assert "COULD NOT RUN" not in r.stdout, r.stdout


def test_the_could_not_run_message_is_distinguishable_from_a_finding():
    """The two verdicts must not be confusable by a reader skimming output, so the strings are
    asserted to be different rather than merely both present.

    The exit code is asserted behaviourally by the two rows above; this row is the lexical half —
    that the script still NAMES the 128 case rather than folding it into the generic arm.
    """
    src = INVARIANT.read_text()
    assert "COULD NOT RUN" in src
    assert "128" in src, "the 128 case is not named in the script at all"
    assert "CANNOT_RUN_RC=3" in src, (
        "the third verdict no longer has its own exit code; the comment claiming it is distinct "
        "from a finding was contradicted by `exit 1` on the next token once already"
    )


# ------------------------------------------------------------- scope, stated


def test_an_override_outside_the_repo_says_so_rather_than_failing(tmp_path):
    """No `.gitignore` anywhere can ignore a path outside the work tree, so reporting a failure
    would be reporting something the repo cannot fix. It exits 0 — and says WHY, rather than
    passing silently.

    What it must NOT say is that something protects that path. The old
    message ended "the directory marker is what protects it", which asserted a protection nothing
    checked — and for the likeliest shape, a sibling repo's pre-existing `.claude/`,
    `tasklist-guard-dir.sh` refuses to write a marker at all. The honest verdict is out-of-scope
    and unverified, which is what is asserted here.
    """
    root = mkrepo(tmp_path)
    outside = tmp_path / "elsewhere" / "tasklist.md"
    r = run_inv(root, {"PLC_TASKLIST_FILE": str(outside)})
    assert r.returncode == 0, r.stdout + r.stderr
    assert "outside this repo" in r.stdout
    assert "OUT OF SCOPE, UNVERIFIED" in r.stdout, r.stdout
    assert "marker is what protects it" not in r.stdout, (
        "the out-of-scope verdict is claiming a protection it does not check"
    )


@pytest.mark.parametrize("spelling", ["../tasklist.md", "../elsewhere/.claude/tasklist.md"])
def test_a_relative_escape_gets_the_same_verdict_as_the_absolute_one(tmp_path, spelling):
    """The same situation must not get two verdicts.

    `PLC_TASKLIST_FILE=../tasklist.md` used to fall through as a literal relative path,
    `git check-ignore` refused it with exit 128, and the script announced "COULD NOT RUN — bad
    cwd, unset GIT_DIR, or not a work tree". None of that was true, and spelling the identical
    location absolutely was a documented PASS. The override is now resolved to an absolute path
    before the in-repo/out-of-repo split, so both spellings land in the same arm.
    """
    root = mkrepo(tmp_path)
    r = run_inv(root, {"PLC_TASKLIST_FILE": spelling})
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OUT OF SCOPE, UNVERIFIED" in r.stdout, r.stdout
    assert "COULD NOT RUN" not in r.stdout, (
        f"a relative escape is still being reported as a broken environment:\n{r.stdout}"
    )


def test_a_repo_root_argument_with_a_trailing_slash_still_checks_something(tmp_path):
    """A trailing slash on the repo root must not make the check look away.

    The in-repo test is `"$REPO_ROOT"/*`. A root passed as `/path/to/repo/` produced
    `/path/to/repo//*`, which matches nothing — so the DEFAULT `.claude/tasklist.md` was reported
    as resolving OUTSIDE the repo and the invariant exited 0 having checked nothing at all. Green
    meaning "I looked away". The root is a documented argument, so a trailing slash is a spelling
    a caller will really use.

    The assertion is that both spellings produce the SAME verdict, not merely that the slashed one
    exits 0 — an out-of-scope PASS also exits 0, which is exactly how this hid.
    """
    root = mkrepo(tmp_path)
    plain = run_inv(root, arg=str(root))
    slashed = run_inv(root, arg=f"{root}/")
    assert plain.returncode == 0, plain.stdout + plain.stderr
    assert slashed.returncode == plain.returncode, (slashed.stdout, plain.stdout)
    assert "OUT OF SCOPE" not in slashed.stdout, (
        f"a trailing slash on the repo root made the default path look external, so the check "
        f"scanned nothing and still passed:\n{slashed.stdout}"
    )
    assert "is ignored" in slashed.stdout, slashed.stdout


def test_a_path_resolving_to_the_work_tree_root_is_inside_the_repo_not_outside(tmp_path):
    """This was the one mutant the first pass did not kill.

    The in-repo test is `"$REPO_ROOT"/*`, which does not match `$REPO_ROOT` itself, so a
    configured path resolving exactly to the work-tree root fell through to the out-of-repo arm
    and was answered "OUT OF SCOPE, UNVERIFIED" — for a path that is inside the repo by
    definition. Removing the root arm leaves every other row in this file green, which is why
    this one exists.

    The correct verdict is a configuration failure, not an out-of-scope pass: the root is not a
    tasklist file.
    """
    root = mkrepo(tmp_path)
    r = run_inv(root, {"PLC_TASKLIST_FILE": str(root)})
    assert r.returncode == 1, (
        f"the work-tree root was not treated as inside the repo:\n{r.stdout}"
    )
    assert "work-tree root itself" in r.stdout, r.stdout
    assert "OUT OF SCOPE" not in r.stdout, (
        f"a path resolving to the repo root was reported as outside the repo:\n{r.stdout}"
    )


@pytest.mark.parametrize("bad", ["*", ".claude/*", ":(glob)x", "a[bc]/tasklist.md"])
def test_a_pattern_instead_of_a_path_is_refused_as_a_pattern(tmp_path, bad):
    """Fail closed, and fail with the RIGHT reason.

    Before the fail-closed arm, `PLC_TASKLIST_FILE='*'` reached the tracked scan and
    `git ls-files --error-unmatch -- '*'` matched the whole index, so the script announced
    "a tasklist artifact is git-tracked: [*]" and sent the reader to `git rm --cached`. Non-zero,
    therefore safe — and a true failure with a false reason, which is the defect class this
    check exists to prevent. The verdict must name the configuration, not an imaginary tracked file.
    """
    root = mkrepo(tmp_path)
    r = run_inv(root, {"PLC_TASKLIST_FILE": bad})
    assert r.returncode == 1, (bad, r.stdout)
    assert "glob or magic-pathspec" in r.stdout, (bad, r.stdout)
    assert "is git-tracked" not in r.stdout, (
        f"{bad} was reported as a tracked tasklist; the reason is false and points the reader at "
        f"`git rm --cached` for a configuration problem:\n{r.stdout}"
    )


def test_a_configured_path_is_not_silently_replaced_by_a_directory_listing(tmp_path):
    """The control for `set -f` inside abspath(), which is the thing that actually broke.

    The splitting loop is an unquoted `$p`, so without noglob the shell pathname-expanded every
    segment: a configured `*` became a listing of the repo root joined by slashes — a path
    nobody configured — and the check ran against THAT and passed. This row asserts the invented
    path never appears in the output, which is a claim about abspath() rather than about the
    fail-closed arm above it: if `set -f` were dropped but the arm kept, the arm's own message
    would echo the expanded garbage.
    """
    root = mkrepo(tmp_path)
    (root / "alpha.md").write_text("x\n")
    (root / "beta.md").write_text("x\n")
    r = run_inv(root, {"PLC_TASKLIST_FILE": "*"})
    assert "alpha.md" not in r.stdout, (
        f"abspath() pathname-expanded the configured value; the check is reasoning about a path "
        f"that was never configured:\n{r.stdout}"
    )
    assert "beta.md" not in r.stdout, r.stdout


def test_a_relative_path_that_climbs_back_into_the_repo_is_still_checked(tmp_path):
    """The control for the row above. Normalisation must not turn every `..` into out-of-scope —
    `docs/../.claude/tasklist.md` names a path INSIDE the repo and has to be checked as one.
    Without this row, an implementation that skipped anything containing `..` would pass the
    escape rows above and quietly stop checking the default location."""
    root = mkrepo(tmp_path)
    r = run_inv(root, {"PLC_TASKLIST_FILE": "docs/../.claude/tasklist.md"})
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OUT OF SCOPE" not in r.stdout, r.stdout
    assert ".claude/tasklist.md' is ignored" in r.stdout, r.stdout


def test_the_repo_root_is_an_argument_not_only_an_environment_variable(tmp_path):
    """An environment variable is not a capability. The root is an
    explicit optional argument so a test can point it somewhere without any ambient state deciding
    what got scanned."""
    root = mkrepo(tmp_path)
    r = subprocess.run(
        ["/bin/bash", str(INVARIANT), str(root)],
        cwd=str(tmp_path), capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
