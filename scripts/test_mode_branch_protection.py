"""Branch protection is on, AND a push to the default branch is refused.

THE STUB IS FAITHFUL, and here is why. A `gh` stub that answers on stdout
what the real tool writes to stderr lets a probe pass its whole suite and fail on first
contact with reality. So each stub below reproduces the SHAPE the real `gh` produces, including
the ambiguity of a 404 (GitHub returns it both for "no protection" and for "you may not read
protection") -- which is the whole reason this check separates verdict 1 from verdict 3.

VERDICT 3 IS NOT A PASS. Half these tests exist to hold that line: most adopters see 3 in CI, and a
check that reported that as green would be the most reassuring useless check in the suite.
"""

import os
import pathlib
import stat
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHECK = ROOT / "skills/project-lifecycle/hooks/plc-branch-protection.sh"


def make_stub(tmp_path, body, name="gh"):
    d = tmp_path / "bin"
    d.mkdir(exist_ok=True)
    p = d / name
    p.write_text("#!/bin/bash\n" + body, encoding="utf-8")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return d


def run(tmp_path, bindir=None, force=True, claude_md=None):
    env = dict(os.environ)
    env["PATH"] = f"{bindir}:{env['PATH']}" if bindir else "/usr/bin:/bin"
    if force:
        env["PROTECTION_FORCE"] = "1"
    if claude_md:
        env["PROTECTION_CLAUDE_MD"] = str(claude_md)
    return subprocess.run(
        ["bash", str(CHECK)], capture_output=True, text=True, cwd=tmp_path, env=env
    )


GH_COMMON = """
case "$1 $2" in
  "auth status") exit 0 ;;
  "repo view") echo "o/r" ;;
esac
"""


def gh_stub(protection_body, protection_rc=0):
    return f"""
if [ "$1" = "auth" ]; then exit 0; fi
if [ "$1" = "repo" ]; then
  case "$*" in
    *nameWithOwner*) echo "o/r"; exit 0 ;;
    *defaultBranchRef*) echo "main"; exit 0 ;;
    *permissions.admin*) echo "false"; exit 0 ;;
  esac
  exit 0
fi
if [ "$1" = "api" ]; then
  case "$2" in
    *"/protection") printf '%s\\n' {protection_body!r} >&2; exit {protection_rc} ;;
    *) echo "false"; exit 0 ;;
  esac
fi
exit 0
"""


GIT_REFUSES = """
if [ "$1" = "push" ]; then echo "protected branch" >&2; exit 1; fi
exec /usr/bin/git "$@"
"""

GIT_ACCEPTS = """
if [ "$1" = "push" ]; then exit 0; fi
exec /usr/bin/git "$@"
"""


def test_no_gh_is_could_not_run(tmp_path):
    """Verdict 3, the one most adopters will see. It must not be 0."""
    p = run(tmp_path, bindir=make_stub(tmp_path, 'exit 127\n', name="placeholder"))
    # PATH deliberately excludes gh
    p = subprocess.run(
        ["bash", str(CHECK)], capture_output=True, text=True, cwd=tmp_path,
        env={"PATH": "/usr/bin:/bin", "PROTECTION_FORCE": "1"},
    )
    assert p.returncode == 3, p.stdout + p.stderr
    assert "COULD NOT RUN" in p.stderr
    assert p.stdout.strip() == "", "a check that could not run must not print a passing line"


def test_unprotected_is_a_failure_not_a_could_not_run(tmp_path):
    d = make_stub(tmp_path, gh_stub("Branch not protected", protection_rc=1))
    (d / "git").write_text("#!/bin/bash\n" + GIT_REFUSES, encoding="utf-8")
    (d / "git").chmod(0o755)
    p = run(tmp_path, bindir=d)
    assert p.returncode == 1, p.stdout + p.stderr
    assert "NOT protected" in p.stderr


def test_a_404_without_admin_is_could_not_run(tmp_path):
    """The ambiguity GitHub actually produces. Calling it a failure would cry wolf in CI."""
    d = make_stub(tmp_path, gh_stub("Not Found (HTTP 404)", protection_rc=1))
    (d / "git").write_text("#!/bin/bash\n" + GIT_REFUSES, encoding="utf-8")
    (d / "git").chmod(0o755)
    p = run(tmp_path, bindir=d)
    assert p.returncode == 3, p.stdout + p.stderr
    assert "indistinguishable" in p.stderr


def test_protected_and_push_refused_passes(tmp_path):
    d = make_stub(tmp_path, gh_stub("", protection_rc=0))
    (d / "git").write_text("#!/bin/bash\n" + GIT_REFUSES, encoding="utf-8")
    (d / "git").chmod(0o755)
    p = run(tmp_path, bindir=d)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "both halves checked" in p.stdout


def test_protected_but_push_accepted_fails(tmp_path):
    """The half the criterion insists on: reading the config is not enough."""
    d = make_stub(tmp_path, gh_stub("", protection_rc=0))
    (d / "git").write_text("#!/bin/bash\n" + GIT_ACCEPTS, encoding="utf-8")
    (d / "git").chmod(0o755)
    p = run(tmp_path, bindir=d)
    assert p.returncode == 1, p.stdout + p.stderr
    assert "was accepted" in p.stderr


def test_not_armed_outside_fast(tmp_path):
    c = tmp_path / "CLAUDE.md"
    c.write_text("mode: detailed\n", encoding="utf-8")
    p = run(tmp_path, force=False, claude_md=c)
    assert p.returncode == 0
    assert "not applicable" in p.stdout
    assert "mode=detailed" in p.stdout


def test_a_written_admission_passes_and_says_what_was_given_up(tmp_path):
    """The escape, and it exists because the requirement is UNSATISFIABLE for many of this skill's
    users: on GitHub a PRIVATE repository on the Free plan cannot have branch protection at all --
    neither protected branches nor rulesets, both public-only at that tier.

    It must pass, and it must SAY what was given up. An escape that prints `ok` and nothing else
    would leave a reader believing they still have the boundary.
    """
    c = tmp_path / "CLAUDE.md"
    c.write_text("mode: fast\nmerge-boundary: unprotected-acknowledged\n", encoding="utf-8")
    p = run(tmp_path, force=False, claude_md=c)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "ACKNOWLEDGED, NOT PROTECTED" in p.stdout
    assert "pushing the default branch directly" in p.stdout
    assert "only human act left" in p.stdout


def test_the_admission_is_not_reached_by_accident(tmp_path):
    """`protected` and an absent key both mean 'check it for real', not 'let it through'."""
    for value in ("", "merge-boundary: protected\n"):
        c = tmp_path / "CLAUDE.md"
        c.write_text("mode: fast\n" + value, encoding="utf-8")
        d = make_stub(tmp_path, gh_stub("Branch not protected", protection_rc=1))
        (d / "git").write_text("#!/bin/bash\n" + GIT_REFUSES, encoding="utf-8")
        (d / "git").chmod(0o755)
        p = run(tmp_path, bindir=d, force=False, claude_md=c)
        assert p.returncode == 1, f"value={value!r}: {p.stdout}{p.stderr}"
        assert "NOT protected" in p.stderr


def test_an_unrecognised_admission_is_named_not_ignored(tmp_path):
    """Same rule as an unrecognised mode: a value nobody recognises must never fall through."""
    c = tmp_path / "CLAUDE.md"
    c.write_text("mode: fast\nmerge-boundary: whatever\n", encoding="utf-8")
    p = run(tmp_path, force=False, claude_md=c)
    assert p.returncode == 2, p.stdout + p.stderr
    assert "whatever" in p.stderr
    assert "unprotected-acknowledged" in p.stderr


def test_a_not_protected_failure_names_a_way_forward(tmp_path):
    """A failure that names no action is a wall, and for a free private repo there is no setting
    to change -- the feature is not sold at that tier."""
    d = make_stub(tmp_path, gh_stub("Branch not protected", protection_rc=1))
    (d / "git").write_text("#!/bin/bash\n" + GIT_REFUSES, encoding="utf-8")
    (d / "git").chmod(0o755)
    p = run(tmp_path, bindir=d)
    assert p.returncode == 1
    assert "merge-boundary: unprotected-acknowledged" in p.stderr
    assert "Free plan" in p.stderr, "the failure must name why turning it on may not be possible"


def test_the_document_and_the_checker_agree_on_the_free_plan_fact(tmp_path):
    """The measured fact lives in two places and must not drift: a reader who only opens the
    reference must learn the same thing the failure message tells them."""
    doc = " ".join(
        (ROOT / "skills/project-lifecycle/references/mode.md").read_text(encoding="utf-8").split()
    )
    src = CHECK.read_text(encoding="utf-8")
    assert "Free plan cannot have branch protection" in doc
    assert "Free plan" in src
    assert "unprotected-acknowledged" in doc and "unprotected-acknowledged" in src


def test_the_push_probe_is_a_dry_run():
    """This check must never be the thing that pushes to the default branch."""
    src = CHECK.read_text(encoding="utf-8")
    pushes = [l for l in src.splitlines() if "git push" in l and not l.strip().startswith("#")]
    assert pushes, "no push probe found"
    for line in pushes:
        assert "--dry-run" in line, f"a push probe without --dry-run: {line}"
