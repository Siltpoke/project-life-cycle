"""The standing assertion that the close gate is reachable in the hook git
will actually run.

The installer runs ONCE PER CLONE; reachability is a standing property of a file the
installer does not own. A later hook reinstall, an added `exec` shim, or a `core.hooksPath`
setting un-wires the chain, and every one of those has the same invisible symptom: pushes
keep succeeding.

The invariant's limit, restated so nobody reads more into a green than is there: this check cannot
run when the wiring is broken in the way that matters most to it — if the hook does not
fire, this does not run from the hook either. It is the PAIR to the installer's insertion
order, not a replacement, and it earns its keep on a hand-typed `close-gate.sh`.
"""
import json
import subprocess
import stat
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
INVARIANT = ROOT / "scripts/invariants/close-gate-wiring.sh"
INSTALLER = ROOT / "scripts/install-close-gate-hook.sh"

MARK = "# >>> close-gate wrap-up chain (scripts/install-close-gate-hook.sh) >>>"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _run(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["/bin/bash", str(INVARIANT), *args], cwd=cwd,
                          capture_output=True, text=True, check=False)


def _repo(tmp_path: Path, name: str = "repo") -> Path:
    repo = tmp_path / name
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@t.t")
    _git(repo, "config", "user.name", "t")
    (repo / "scripts").mkdir()
    stub = repo / "scripts/close-gate-prepush.sh"
    stub.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IRWXU)
    (repo / "README.md").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    return repo


def _write_hook(repo: Path, body: str, *, where: Path | None = None) -> Path:
    hook = (where or repo / ".git/hooks") / "pre-push"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(body, encoding="utf-8")
    hook.chmod(hook.stat().st_mode | stat.S_IEXEC | stat.S_IRWXU)
    return hook


CHAINED = f"""#!/bin/bash
{MARK}
if [ -x scripts/close-gate-prepush.sh ]; then scripts/close-gate-prepush.sh </dev/null || exit 1; fi
# <<< close-gate wrap-up chain <<<

echo "the rest of the hook"
exit 0
"""

EXEC_SHIM_ABOVE_CHAIN = f"""#!/bin/bash
exec /usr/bin/true "$@"
{MARK}
if [ -x scripts/close-gate-prepush.sh ]; then scripts/close-gate-prepush.sh </dev/null || exit 1; fi
# <<< close-gate wrap-up chain <<<
exit 0
"""

INIT_HARNESS_SHAPE = """#!/bin/bash
# This hook IS the gate — nothing foreign precedes it, so position is not the question.
set -u
exec bash scripts/close-gate-prepush.sh
"""


# --- the invariant contract --------------------------------------------------------
def _code_lines(path: Path) -> str:
    """Comments stripped. Every assertion below is about what the script DOES; asking a
    literal-text question of a file whose comments discuss the very tokens it must not
    invoke is the use-versus-mention error."""
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("#"):
            continue
        out.append(line.split(" #", 1)[0])
    return "\n".join(out)


def test_it_obeys_the_invariant_contract():
    """Self-contained, no `source`, prints its own reason, 0 holds / non-0 fails."""
    code = _code_lines(INVARIANT)
    assert "source " not in code and "\n. " not in code, "an invariant must be self-contained"
    assert "python" not in code, "the gate's dependency envelope is jq-only"
    assert "exit 0" in code and "exit 1" in code
    assert "printf 'PASS" in code and "printf 'FAIL" in code


def test_the_sentinel_matches_the_installers_copy():
    """One string, two files. `MARK` is pinned as a literal in the invariant so it does not
    have to parse the installer at runtime; this is what stops the two drifting apart."""
    installer = INSTALLER.read_text(encoding="utf-8")
    assert f'MARK="{MARK}"' in installer, "the installer's sentinel changed"
    assert f'MARK="{MARK}"' in INVARIANT.read_text(encoding="utf-8")


def test_it_is_registered_in_both_places_and_only_those():
    manifest = json.loads((ROOT / ".claude/close-gate.json").read_text(encoding="utf-8"))
    names = [i["name"] for i in manifest["invariants"]]
    assert "close-gate-wiring" in names
    envelope = (ROOT / "scripts/invariants/gate-jq-only-envelope.sh").read_text(encoding="utf-8")
    assert "scripts/invariants/close-gate-wiring.sh" in envelope, "missing from DECLARED"


def test_it_states_its_own_limit():
    """The limit is in the script, not only in a design document — it cannot run when
    the wiring is broken in the way it exists to catch."""
    # Comment markers dropped and whitespace collapsed, because the statement lives in a
    # wrapped comment block: an exact-substring assertion breaks on the line wrap and on the
    # leading `#` of the continuation line, neither of which is about the meaning.
    raw = INVARIANT.read_text(encoding="utf-8").replace("#", " ")
    src = " ".join(raw.split())
    assert "if the hook does not fire, this check does not run from the hook either" in src


# --- clause 2: position, not presence ----------------------------------------------
def test_the_chain_shape_passes(tmp_path):
    repo = _repo(tmp_path)
    _write_hook(repo, CHAINED)
    cp = _run(repo)
    assert cp.returncode == 0, cp.stdout + cp.stderr
    assert "chain shape" in cp.stdout


def test_the_init_harness_shape_passes(tmp_path):
    """Without this second accepted shape the clause is UNSATISFIABLE for the wiring this
    skill's own /init-harness mandates: the sentinel exists in exactly one file in the whole
    product, and the shipped .githooks/pre-push carries none of it."""
    repo = _repo(tmp_path)
    _write_hook(repo, INIT_HARNESS_SHAPE)
    cp = _run(repo)
    assert cp.returncode == 0, cp.stdout + cp.stderr
    assert "gate shape" in cp.stdout


def test_an_exec_above_the_chain_is_caught(tmp_path):
    """POSITIVE CONTROL 1, and the reason clause 2 is about position rather than presence.
    The sentinel is present, bracketed and complete — and the chain never runs. A
    presence-only check passes this hook."""
    repo = _repo(tmp_path)
    _write_hook(repo, EXEC_SHIM_ABOVE_CHAIN)
    cp = _run(repo)
    assert cp.returncode != 0
    assert "NOT as the first line after the shebang" in cp.stdout


def test_a_hook_without_the_sentinel_is_caught(tmp_path):
    repo = _repo(tmp_path)
    _write_hook(repo, "#!/bin/bash\necho hi\nexit 0\n")
    cp = _run(repo)
    assert cp.returncode != 0
    assert "does not reach the close gate" in cp.stdout


# --- clause 1: the orphan, and the fixture layout that is part of the AC -------------
def test_an_orphaned_hook_is_caught_and_named(tmp_path):
    """POSITIVE CONTROL 2. THE LAYOUT IS PART OF THE AC, and the intuitive one does not work.

    The hook must sit at `.git/hooks/pre-push` WITH its sentinel, and `core.hooksPath` is
    merely set. Clearing the key alone then turns it green.

    The intuitive layout — the hook only under `.githooks/` — cannot produce red→green:
    clearing hooksPath makes `--git-path` resolve back to `.git/hooks/pre-push`, which does
    not exist in that layout, so the supposed green is red for a reason unrelated to clause
    1. Worse, in that layout clauses 1 and 2 fire together and the red is unattributable,
    violating the one-mutation-at-a-time rule this repo's own envelope guard writes down.
    """
    repo = _repo(tmp_path)
    _write_hook(repo, CHAINED)                 # wired, at the DEFAULT path
    (repo / ".githooks").mkdir()
    _git(repo, "config", "core.hooksPath", ".githooks")

    cp = _run(repo)
    assert cp.returncode != 0, cp.stdout
    assert "ORPHANED" in cp.stdout
    assert ".githooks" in cp.stdout, "the failure does not name where git now reads hooks from"
    assert "not wired" not in cp.stdout, "a correct refusal giving the wrong reason"

    _git(repo, "config", "--unset", "core.hooksPath")   # the ONLY change
    cp = _run(repo)
    assert cp.returncode == 0, cp.stdout + cp.stderr


def test_hooks_path_aliasing_the_default_dir_is_not_an_orphan(tmp_path):
    """The false positive the literal-path version produced, pinned. Setting core.hooksPath
    TO the default directory changes nothing about which file git runs."""
    repo = _repo(tmp_path)
    _write_hook(repo, CHAINED)
    _git(repo, "config", "core.hooksPath", str(repo / ".git/hooks"))
    cp = _run(repo)
    assert cp.returncode == 0, cp.stdout + cp.stderr


def test_hooks_path_elsewhere_with_no_default_hook_is_not_an_orphan(tmp_path):
    """An adopter who followed /init-harness has no hook at the default path, so nothing is
    orphaned. Setting the key is not itself the failure — a clause that treated it as one
    would be a guard that fails on the wiring four other shipped files mandate."""
    repo = _repo(tmp_path)
    hooks = repo / ".githooks"
    hooks.mkdir()
    _write_hook(repo, INIT_HARNESS_SHAPE, where=hooks)
    _git(repo, "config", "core.hooksPath", ".githooks")
    cp = _run(repo)
    assert cp.returncode == 0, cp.stdout + cp.stderr


# --- clause 3: the two layouts no other fixture reaches ------------------------------
def test_it_works_from_a_subdirectory(tmp_path):
    """`--git-path` output is cwd-relative, and that is exactly what makes it correct here."""
    repo = _repo(tmp_path)
    _write_hook(repo, CHAINED)
    (repo / "scripts/invariants").mkdir(parents=True, exist_ok=True)
    cp = _run(repo / "scripts/invariants", str(repo))
    assert cp.returncode == 0, cp.stdout + cp.stderr


def test_it_works_from_a_linked_worktree(tmp_path):
    """`--absolute-git-dir` is the trap: in a worktree it returns the per-worktree directory,
    where `hooks/pre-push` does not exist, so an invariant built on it is permanently red
    there — reintroducing the defect clause 3 exists to close. Parallel sessions on one repo
    are commonly isolated in worktrees, so this is a normal case."""
    repo = _repo(tmp_path)
    _write_hook(repo, CHAINED)
    wt = tmp_path / "wt"
    _git(repo, "worktree", "add", "-q", "-b", "side", str(wt))
    try:
        cp = _run(wt)
        assert cp.returncode == 0, cp.stdout + cp.stderr
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(wt)],
                       cwd=repo, capture_output=True, check=False)


# --- clause 4: an unwired clone, and the spelling of the cure ------------------------
def test_a_clone_with_no_hook_fails_and_names_the_cure(tmp_path):
    repo = _repo(tmp_path)
    cp = _run(repo)
    assert cp.returncode != 0
    assert "not wired" in cp.stdout
    assert "/bin/bash scripts/install-close-gate-hook.sh" in cp.stdout


def test_the_cure_is_never_spelled_in_the_form_another_invariant_reds():
    """`named-interpreter.sh` reds any non-comment line matching `bash` preceded by a
    non-word character. Spelling the cure `run: bash …` would make a DIFFERENT invariant
    fail on every check-8 run, with the red attributed to that one."""
    cp = subprocess.run(["/bin/bash", str(ROOT / "scripts/invariants/named-interpreter.sh")],
                        cwd=ROOT, capture_output=True, text=True, check=False)
    assert cp.returncode == 0, cp.stdout + cp.stderr


def test_the_reason_text_is_only_reachable_by_running_it_directly():
    """Clause 5, written as a test so the limit cannot be forgotten and then overclaimed.

    check 8 runs each invariant as `( eval "$CMD" ) >/dev/null 2>&1` — BOTH streams
    discarded. A pusher sees only `invariant … FAILED — (run it directly to see why)`. So no
    wording anywhere may say the cure "is printed"; it is reachable, which is a weaker and
    true claim."""
    gate = (ROOT / "scripts/close-gate.sh").read_text(encoding="utf-8")
    assert ">/dev/null 2>&1" in gate, "check 8 no longer discards both streams — re-read this test"
    src = INVARIANT.read_text(encoding="utf-8")
    for overclaim in ("is printed", "will be printed", "the pusher sees"):
        assert overclaim not in src, f"the invariant claims its text {overclaim!r}"


# --- the registration controls every invariant should have had -----------------------
#
# The claim was that "every existing invariant ships a controls test asserting its exact
# registration string". In practice many registrations are not named
# anywhere in a test file at all, and far fewer assert the string. Rather than write one
# bespoke control per registration — nearly all copies of one another, and a copied guard
# drifts — this is ONE control over the whole table. It is strictly stronger than the
# per-invariant version, because it also catches a registration added later with no test.

def _registrations() -> list[dict]:
    return json.loads((ROOT / ".claude/close-gate.json").read_text(encoding="utf-8"))["invariants"]


def test_every_registered_invariant_points_at_a_file_that_exists():
    missing = [i["name"] for i in _registrations()
               if not (ROOT / i["command"].split()[-1]).exists()]
    assert not missing, f"registered but absent from disk: {missing}"


def test_every_registration_uses_one_spelling_of_the_interpreter():
    """Every registration uses the same interpreter spelling.

    `/bin/bash` is the one to keep: `named-interpreter.sh` reds a bare `bash ` in any tracked
    `*.sh`, so the bare spelling is the one that cannot be copied out of this manifest into a
    script without tripping a different guard. A single spelling is also what makes the
    assertion below meaningful rather than a list of accepted variants.
    """
    wrong = [i["name"] for i in _registrations() if not i["command"].startswith("/bin/bash ")]
    assert not wrong, f"registrations not spelled `/bin/bash …`: {wrong}"


def test_the_registered_names_appear_in_the_scripts_they_name():
    """A registration whose `name` appears nowhere in its script reports failures under a
    label the reader cannot then grep for.

    THE STRONGER FORM OF THIS ASSERTION IS NOT MET AND IS NOT BEING MADE. Asking for a
    `NAME="<name>"` declaration finds it in only 7 of the 16 scripts: the other nine — among
    them `no-icloud-conflict-copies`, `manifest-version-sync` and `named-interpreter` — spell the name
    inline in each `echo "PASS <name>: …"` instead. Both conventions are legible; neither is
    wrong; unifying them is a sweep across nine files that is out of scope here, and
    doing it silently under cover of a new test would be worse than leaving it. So the
    assertion is the one that actually holds, and the gap is written down here rather than
    hidden behind a passing test.
    """
    missing = []
    for inv in _registrations():
        src = (ROOT / inv["command"].split()[-1]).read_text(encoding="utf-8")
        if inv["name"] not in src:
            missing.append(inv["name"])
    assert not missing, f"registration name appears nowhere in its script: {missing}"
