"""The executable oracle `/init-harness` never had.

`/init-harness` is a prose command: no code runs it, so its own oracle has only ever been
"`validate.py` is green and the spec mentions the thing". That proves the doc SAYS the right
words; it cannot prove an adopter who follows the doc ends up with a gate that actually works.

These tests close that by making the doc's output machine-readable and then running it: the
manifest template the reference doc hands a new adopter is extracted, planted in a fixture repo,
and put through the REAL canonical gate extracted from `references/close-gate.md`. Every verdict
below is the gate's, not a string match against the doc — so a template with a typo'd key reds
here even though the prose around it still reads correctly.

What is being pinned: a fresh init-harness run produces a manifest whose
test-evidence check is in **fingerprint** mode, not the legacy mtime mode.
"""
import json
import subprocess
from pathlib import Path

import pytest

from close_gate_lib import (
    _git,
    extract_evidence_runner_script,
    extract_gate_script,
    extract_init_harness_manifest,
    make_fixture_repo,
    run_gate,
)

ROOT = Path(__file__).resolve().parents[1]
GATE_MD = ROOT / "skills/project-lifecycle/references/close-gate.md"
INIT_MD = ROOT / "skills/project-lifecycle/references/init-harness.md"

# The two branches of `check_evidence` print different sentences. Binding to these is what makes
# the assertions behavioural: the gate decides which mode it is in, the test only reads the verdict.
FINGERPRINT_MARK = "declared test_evidence_inputs are unchanged since this file was generated"
MTIME_MARK = "mtime is not evidence the tests ran"


@pytest.fixture(scope="module")
def gate_script() -> str:
    return extract_gate_script(GATE_MD)


@pytest.fixture(scope="module")
def generated_manifest() -> dict:
    return extract_init_harness_manifest(INIT_MD)


def test_the_doc_carries_a_parseable_manifest_template(generated_manifest: dict) -> None:
    """Floor assertion. Without it every test below could pass vacuously on an empty template,
    which would read as green while checking nothing."""
    assert isinstance(generated_manifest, dict) and generated_manifest, (
        "the generated-manifest fence parsed to nothing"
    )


def test_generated_manifest_declares_test_evidence_inputs(generated_manifest: dict) -> None:
    inputs = generated_manifest.get("test_evidence_inputs")
    assert isinstance(inputs, list) and inputs, (
        "the manifest /init-harness generates must declare a non-empty test_evidence_inputs array "
        "— an absent key is exactly what keeps a new adopter on the legacy mtime check"
    )


def test_generated_runner_prepends_the_evidence_header(generated_manifest: dict) -> None:
    """The opt-in has two halves and declaring the key is only the first. Without the header the
    gate hard-fails rather than falling back, so a manifest that declares inputs but keeps a bare
    runner hands the adopter a gate that cannot pass at all."""
    cmd = generated_manifest.get("test_evidence_command") or generated_manifest.get("test_command")
    assert cmd, "the manifest declares no test command"
    assert "evidence-header" in cmd, (
        f"the generated test-evidence command must prepend the header; got: {cmd!r}"
    )


def _fixture_with(manifest: dict, tmp_path: Path, evidence_body: str) -> Path:
    """A repo carrying the generated manifest, plus the tracked inputs it declares."""
    return make_fixture_repo(
        tmp_path,
        manifest,
        {
            "src/app.py": "print('hi')\n",
            "tests/test_app.py": "def test_ok() -> None:\n    assert True\n",
            manifest["test_evidence"]: evidence_body,
        },
    )


def _digest_via_gate(repo: Path, gate_script: str) -> str:
    """Ask the gate itself for the header it would write, rather than re-deriving the digest here.
    A test that recomputed the digest with its own copy of the algorithm would be its own oracle."""
    res = run_gate(repo, gate_script, "evidence-header", "phase")
    assert res.returncode == 0, f"evidence-header failed: {res.stdout}\n{res.stderr}"
    return res.stdout


def test_generated_manifest_lands_in_fingerprint_mode(
    generated_manifest: dict, gate_script: str, tmp_path: Path
) -> None:
    """The load-bearing one. A repo configured exactly as /init-harness prescribes must put the
    gate's test-evidence row in fingerprint mode — and must NOT reach the mtime branch."""
    repo = _fixture_with(generated_manifest, tmp_path, "placeholder\n")
    header = _digest_via_gate(repo, gate_script)
    (repo / generated_manifest["test_evidence"]).write_text(
        header + "all tests passed\nRUNS=3\n", encoding="utf-8"
    )
    res = run_gate(repo, gate_script, "task", "1.1")
    assert FINGERPRINT_MARK in res.stdout, (
        f"test-evidence row did not run in fingerprint mode:\n{res.stdout}"
    )
    assert MTIME_MARK not in res.stdout, (
        f"test-evidence row fell through to the legacy mtime branch:\n{res.stdout}"
    )


@pytest.fixture(scope="module")
def runner_script() -> str:
    return extract_evidence_runner_script(GATE_MD)


def _repo_with_runner(
    manifest: dict, gate_script: str, runner_script: str, tmp_path: Path
) -> Path:
    """A fixture repo carrying BOTH portable scripts side by side, the layout the runner assumes
    (it resolves the gate relative to its own directory)."""
    repo = _fixture_with(manifest, tmp_path, "pre-existing good evidence\n")
    scripts = repo / "scripts"
    scripts.mkdir(exist_ok=True)
    (scripts / "close-gate.sh").write_text(gate_script, encoding="utf-8")
    (scripts / "close-gate.sh").chmod(0o755)
    (scripts / "gen-test-evidence.sh").write_text(runner_script, encoding="utf-8")
    (scripts / "gen-test-evidence.sh").chmod(0o755)
    return repo


def _run_runner(repo: Path, mode: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    import os

    env = {**os.environ, **(env_extra or {})}
    return subprocess.run(
        ["bash", "scripts/gen-test-evidence.sh", mode],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_ported_runner_resolves_both_placeholders(
    generated_manifest: dict, gate_script: str, runner_script: str, tmp_path: Path
) -> None:
    """The runner is the only thing that resolves `{SET}` and `{EVIDENCE_FILE}`; a manifest
    carrying them without it is inert. Proven by running it, not by reading the doc."""
    repo = _repo_with_runner(generated_manifest, gate_script, runner_script, tmp_path)
    res = _run_runner(
        repo,
        "phase",
        # Shaped like a real declared command — the placeholders only mean anything if the command
        # actually writes THROUGH {EVIDENCE_FILE}, which is the form the generated manifest uses.
        {"PLC_GEN_TEST_EVIDENCE_CMD_OVERRIDE": "{ echo set-was={SET}; } | tee {EVIDENCE_FILE}"},
    )
    assert res.returncode == 0, f"runner failed: {res.stdout}\n{res.stderr}"
    written = (repo / generated_manifest["test_evidence"]).read_text(encoding="utf-8")
    assert "set-was=phase" in written, f"{{SET}} was not resolved: {written!r}"
    assert "{EVIDENCE_FILE}" not in written, f"{{EVIDENCE_FILE}} was left literal: {written!r}"


def test_ported_runner_leaves_good_evidence_untouched_on_failure(
    generated_manifest: dict, gate_script: str, runner_script: str, tmp_path: Path
) -> None:
    """The whole reason the runner exists instead of a bare `tee`: a failing command must not
    overwrite a pre-existing good evidence file. This is the hazard a hand-written
    tee pipeline has, so it is the one behaviour porting the runner has to actually carry."""
    repo = _repo_with_runner(generated_manifest, gate_script, runner_script, tmp_path)
    evidence = repo / generated_manifest["test_evidence"]
    before = evidence.read_text(encoding="utf-8")
    res = _run_runner(
        repo, "task", {"PLC_GEN_TEST_EVIDENCE_CMD_OVERRIDE": "echo partial output; exit 7"}
    )
    assert res.returncode == 7, f"runner swallowed the failure: rc={res.returncode} {res.stdout}"
    assert evidence.read_text(encoding="utf-8") == before, (
        "a failing run overwrote the pre-existing evidence file — the bare-`tee` hazard survived "
        "the port"
    )


def test_generated_command_actually_runs_without_the_test_override(
    generated_manifest: dict, gate_script: str, runner_script: str, tmp_path: Path
) -> None:
    """The case every other runner test here skips.

    Every other runner test here passes `PLC_GEN_TEST_EVIDENCE_CMD_OVERRIDE`, so none of them ever
    executed the command the doc actually generates. They were green while a fresh adopter
    following the doc got `close-gate.sh: command not found` and rc 127 — the gate was named
    bare, and it is not on PATH. A mechanism justified by a use case is not done until it is run
    against that use case, so this test runs the generated command with nothing replaced except
    the one `REPLACE_ME` marker the adopter is told to fill in.
    """
    manifest = dict(generated_manifest)
    manifest["test_command"] = manifest["test_command"].replace(
        "REPLACE_ME_TEST_COMMAND", "echo the-real-suite-ran"
    )
    assert "REPLACE_ME" not in manifest["test_command"], (
        f"a REPLACE_ME marker other than the test command survived: {manifest['test_command']!r}"
    )
    repo = _repo_with_runner(manifest, gate_script, runner_script, tmp_path)
    res = _run_runner(repo, "phase")
    assert res.returncode == 0, (
        f"the generated command does not run as written: rc={res.returncode}\n"
        f"{res.stdout}\n{res.stderr}"
    )
    written = (repo / manifest["test_evidence"]).read_text(encoding="utf-8")
    assert written.startswith("# plc-gate-evidence inputs="), (
        f"the generated command did not put the gate's header first: {written[:120]!r}"
    )
    assert "the-real-suite-ran" in written, f"the test command's output is missing: {written!r}"
    # And the whole point: evidence produced this way must satisfy the gate it was produced for.
    gate_res = run_gate(repo, gate_script, "task", "1.1")
    assert FINGERPRINT_MARK in gate_res.stdout, (
        f"evidence generated by the documented runner did not satisfy the gate:\n{gate_res.stdout}"
    )


# --- The promotion guard -----------------------------------------------------------------
#
# Both cases below are about the SAME line: the runner promotes its temp file on the command's
# exit status alone. Exit status is not the same claim as "an artifact the gate could accept",
# and where they differ the runner prints `✓ evidence written` while destroying the adopter's
# last good evidence.
#
# Parametrised over BOTH copies of the runner — the one embedded in `references/close-gate.md`
# (what an adopter gets) and `scripts/gen-test-evidence.sh` (what this repo runs). They are not
# byte-identical files, so a guard added to one and forgotten in the other is exactly the drift
# this test exists to catch; running the same behaviour against both catches it without asserting
# anything about the text of either.
RUNNER_SOURCES = ("doc-ported", "in-repo")


@pytest.fixture(params=RUNNER_SOURCES)
def any_runner_script(request: pytest.FixtureRequest) -> str:
    if request.param == "doc-ported":
        return extract_evidence_runner_script(GATE_MD)
    return (ROOT / "scripts/gen-test-evidence.sh").read_text(encoding="utf-8")


def test_runner_refuses_to_promote_an_empty_result(
    generated_manifest: dict, gate_script: str, any_runner_script: str, tmp_path: Path
) -> None:
    """A declared command that exits 0 while writing nothing to `{EVIDENCE_FILE}` — a test
    runner configured to write its own report file, or a `REPLACE_ME` filled in without the
    placeholder — leaves the temp file empty. Promoting it destroys the previous good evidence and
    reports success. The gate's `-s` check rejects the empty file afterwards, so this never buys a
    green; what it costs is valid state, and a `✓` that means the opposite of what it says."""
    repo = _repo_with_runner(generated_manifest, gate_script, any_runner_script, tmp_path)
    evidence = repo / generated_manifest["test_evidence"]
    before = evidence.read_text(encoding="utf-8")
    res = _run_runner(repo, "task", {"PLC_GEN_TEST_EVIDENCE_CMD_OVERRIDE": "true"})
    assert res.returncode != 0, (
        f"the runner reported success for a command that wrote nothing:\n{res.stdout}"
    )
    assert evidence.read_text(encoding="utf-8") == before, (
        "an empty result replaced the pre-existing good evidence"
    )


def test_runner_refuses_to_promote_a_header_that_fingerprints_nothing(
    generated_manifest: dict, gate_script: str, any_runner_script: str, tmp_path: Path
) -> None:
    """A header that fingerprints nothing must not be promoted either.

    When `test_evidence_inputs` matches no TRACKED file, `evidence-header` emits an `EMPTY-…`
    sentinel instead of a digest and exits 0 — deliberately, so the gate can reject it loudly
    (`close-gate.sh` has a dedicated branch for exactly this header). The producer had no matching
    refusal: the command succeeds, the header is well-formed-but-unusable, and the runner promotes
    it over good evidence.

    This is NOT the empty-output case above. The command here writes exactly what it was asked to.
    The reachable shape is ordinary, not adversarial: `/init-harness` generates `src/**` and
    `tests/**`, so an adopter whose source is not committed yet, or whose layout is `lib/`/`app/`,
    hits it on the first run — measured, with a positive control in a real git repo returning a
    real digest from the same fixture.
    """
    # No override anywhere in this test: the command that runs is the one the doc generates, with
    # only the `REPLACE_ME` marker an adopter is told to fill in substituted.
    manifest = dict(generated_manifest)
    manifest["test_command"] = manifest["test_command"].replace(
        "REPLACE_ME_TEST_COMMAND", "echo the-real-suite-ran"
    )
    repo = _repo_with_runner(manifest, gate_script, any_runner_script, tmp_path)
    evidence = repo / manifest["test_evidence"]
    # Untrack everything the manifest fingerprints, leaving a REAL git repo — the sentinel comes
    # from "no tracked match", not from the absence of git.
    subprocess.run(["git", "rm", "-r", "-q", "--cached", "src", "tests"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "untrack the declared inputs"], cwd=repo, check=True)
    before = evidence.read_text(encoding="utf-8")
    res = _run_runner(repo, "task")
    assert res.returncode != 0, (
        "the runner promoted a header carrying the EMPTY sentinel and reported success:\n"
        f"{res.stdout}"
    )
    assert evidence.read_text(encoding="utf-8") == before, (
        "evidence that fingerprints nothing replaced the pre-existing good evidence"
    )
    assert "test_evidence_inputs" in res.stdout, (
        f"the refusal does not name the cause the adopter has to fix:\n{res.stdout}"
    )


def test_runner_still_writes_evidence_that_carries_no_header_at_all(
    generated_manifest: dict, gate_script: str, any_runner_script: str, tmp_path: Path
) -> None:
    """The over-rejection control for the two guards above, and the reason neither of them
    requires a header: an adopter who has NOT opted into fingerprint mode declares no
    `test_evidence_inputs`, calls no `evidence-header`, and stays on the legacy mtime check. Their
    evidence has no header by design. A guard that demanded one would break them, so the refusal
    is scoped to the `EMPTY-` sentinel and to an empty file — never to a missing header."""
    repo = _repo_with_runner(generated_manifest, gate_script, any_runner_script, tmp_path)
    evidence = repo / generated_manifest["test_evidence"]
    res = _run_runner(
        repo, "task", {"PLC_GEN_TEST_EVIDENCE_CMD_OVERRIDE": "echo plain-suite-output | tee {EVIDENCE_FILE}"}
    )
    assert res.returncode == 0, f"the runner refused headerless evidence: {res.stdout}\n{res.stderr}"
    assert evidence.read_text(encoding="utf-8").strip() == "plain-suite-output"


def test_unheaded_evidence_hard_fails_instead_of_falling_back(
    generated_manifest: dict, gate_script: str, tmp_path: Path
) -> None:
    """The silent-degrade guard. With the key declared and the header missing the gate must reject
    and name the regenerate command — never quietly revert to mtime, which would hand back the
    weaker check under a green."""
    repo = _fixture_with(generated_manifest, tmp_path, "all tests passed\nRUNS=3\n")
    res = run_gate(repo, gate_script, "task", "1.1")
    assert MTIME_MARK not in res.stdout, "unheaded evidence silently fell back to mtime"
    assert "plc-gate-evidence" in res.stdout, (
        f"gate did not name the missing header / regenerate command:\n{res.stdout}"
    )


# --- p37:AC5 ---------------------------------------------------------------------------------
# The scaffolded `validator_input_paths_rationale` placeholder must FAIL the gate, and nothing else
# in the generated template may fail with it. Two claims in one run, and the second is the one that
# is easy to lose: a test asserting only "check 9 is red" would stay green if the template had also
# broken three other rows.

RATIONALE_KEY = "validator_input_paths_rationale"


def _template_repo(manifest: dict, tmp_path: Path, gate_script: str) -> Path:
    """A repo configured EXACTLY as /init-harness prescribes, driven to the state a first real
    cadence task reaches: the product tree and the journal land in the branch range, a `docs:`
    subject exists, and the evidence file carries a header the gate itself produced."""
    repo = make_fixture_repo(tmp_path, manifest, {"README.md": "seed\n"})
    files = {
        "src/app.py": "print('hi')\n",
        "tests/test_app.py": "def test_ok() -> None:\n    assert True\n",
        manifest["journal"]: (
            "# Journal\n\n## FACT — a scaffolded project's first task\n\n"
            "- **Date:**     2026-08-25\n- **Decision:** x\n- **Why:**      x\n"
            "- **Backing:**  x\n\n## Plan deviations\n\n- none\n"
        ),
    }
    for rel, body in files.items():
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    # ORDER MATTERS and it is not cosmetic: the product-tree row reads the HEAD COMMIT ALONE
    # (`git diff-tree ... HEAD`), while the `docs:` row scans the whole branch RANGE. A `docs:`
    # commit on top therefore turns the product-tree row red for a project that did ship product
    # code. Measured, not reasoned -- the first version of this fixture had them the other way and
    # produced exactly that second red row.
    _git(repo, "add", "--", str(manifest["journal"]))
    _git(repo, "commit", "-qm", "docs: journal")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "feat: the first task")
    header = _digest_via_gate(repo, gate_script)
    (repo / manifest["test_evidence"]).write_text(header + "all tests passed\n", encoding="utf-8")
    return repo


def test_the_scaffolded_placeholder_is_the_only_thing_the_gate_refuses(
    generated_manifest: dict, gate_script: str, tmp_path: Path
) -> None:
    repo = _template_repo(generated_manifest, tmp_path, gate_script)
    res = run_gate(repo, gate_script, "task", "p37")
    failing = [ln for ln in res.stdout.splitlines() if ln.startswith("\u2717")]
    assert len(failing) == 1, (
        "a freshly scaffolded project must fail on the unfilled rationale and on NOTHING else --\n"
        "any other red row is a regression in the generated template, not an adopter's mistake.\n"
        + "\n".join(failing)
    )
    assert RATIONALE_KEY in failing[0], f"the one failing row is not check 9's:\n{failing[0]}"


def test_the_scaffolded_placeholder_cannot_satisfy_the_shape_check(generated_manifest: dict) -> None:
    """Asserted on the VALUE, independently of any gate run: the placeholder must break at least one
    of the object shape's rules. If a future placeholder ever satisfies them, the doc's own
    instruction is to change the placeholder rather than the check -- this is what would notice.

    p30 RE-POINTED THIS, and what it used to assert is worth keeping in view: that the placeholder
    carried neither two ASCII digits nor the English word "track". Both of those were requirements
    on the author's PROSE, and p30 removed them because they refused honest arguments written in
    other languages. The placeholder is now an object, and what makes it unsatisfiable is that
    `surface_total` is 0 (the gate wants greater than zero) and `basis` is not in the enum. The
    property being asserted is unchanged: the scaffolded value must not pass.
    """
    assert RATIONALE_KEY in generated_manifest, (
        f"the generated template does not emit {RATIONALE_KEY} at all. Measured as a mutant: with "
        f"the key deleted the gate still fails (on the MISSING branch instead of the placeholder "
        f"branch), so the one-failing-row assertion above cannot notice this -- which is why the "
        f"key's presence is asserted here, on the value, and not only through a gate run."
    )
    value = generated_manifest[RATIONALE_KEY]
    assert isinstance(value, dict), (
        f"{RATIONALE_KEY} must be scaffolded as the OBJECT shape (an array is the deprecated form "
        f"and a new adopter must not be started on it): {value!r}"
    )
    assert "surface_kept" not in value, (
        f"the scaffold must NOT emit surface_kept -- the gate derives it, and a scaffolded member "
        f"the gate refuses would teach an adopter to write it: {value!r}"
    )
    assert value.get("surface_total") == 0, (
        f"surface_total must be scaffolded as 0 so the gate refuses it as not-greater-than-zero: "
        f"{value!r}"
    )
    assert value.get("basis") not in ("tracked-files", "all-files", "glob-set", "explicit-path-list"), (
        f"basis must be scaffolded OUTSIDE the enum so the gate refuses it: {value!r}"
    )
    joined = " ".join(str(v) for v in (value.get("basis"), *(value.get("why") or [])))
    assert "REPLACE_ME" in joined, f"the scaffolded value must be an unmissable marker: {joined!r}"
    assert isinstance(value.get("why"), list) and value["why"], (
        f"why must be scaffolded as a non-empty array so the only failures are the intended two: "
        f"{value!r}"
    )


# --- p37:AC6 ---------------------------------------------------------------------------------
# Documented where an adopter looks. Three tracked files, each of which read ZERO occurrences of
# the key before this phase. Asserted against the tracked bytes, not against a rendered page.

COMMANDS_INIT = ROOT / "commands/init-harness.md"


def test_the_key_is_documented_where_an_adopter_looks() -> None:
    for path, why in (
        (GATE_MD, "the gate's own reference is where a manifest key is looked up"),
        (INIT_MD, "the scaffold's reference is where a new adopter reads what was generated"),
        (COMMANDS_INIT, "the command page is what a person reads before running /init-harness"),
    ):
        text = path.read_text(encoding="utf-8")
        assert RATIONALE_KEY in text, f"{path.relative_to(ROOT)} does not name the key -- {why}"


def test_the_gate_reference_shows_a_real_example_not_just_the_name() -> None:
    """Naming a key an adopter cannot copy is not documentation. The example has to be one the
    check would actually accept, so this asserts the SHAPE the check wants rather than a literal
    sentence -- pinning the sentence would rot the moment the numbers are re-measured."""
    import re

    text = GATE_MD.read_text(encoding="utf-8")
    para = [ln for ln in text.splitlines() if RATIONALE_KEY in ln and "tracked" in ln]
    assert para, f"{GATE_MD.name} names the key but shows no tracked-surface example"
    assert any(len(re.findall(r"\d+", ln)) >= 2 for ln in para), (
        "the documented example carries fewer than two numbers, so it is an example of a value the "
        "gate would REFUSE"
    )
