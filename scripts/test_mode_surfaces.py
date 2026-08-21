"""The surfaces the two modes share: artifact shape, skip markers, dispatch.

Grouped in one file on purpose. These criteria are all assertions about ONE document
(references/mode.md) and the small shipped scripts that read it, and splitting them across four
files would make it easy to add a fifth surface with no test and not notice.
"""

import json
import pathlib
import re
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
HOOKS = ROOT / "skills/project-lifecycle/hooks"
SKIP = HOOKS / "plc-skip-marker.sh"
VERIFY = HOOKS / "plc-verify-stage.sh"
MODE_MD = ROOT / "skills/project-lifecycle/references/mode.md"

EXPECTED_MARKER = (
    "<!-- plc-mode-skip: second-agent | mode=fast | phase=1.2 -->",
    "_Not run under the fast mode. To fill it in: set `mode: detailed` and re-run this step._",
)


def _block(name):
    text = MODE_MD.read_text(encoding="utf-8")
    found = re.findall(
        rf"<!-- plc-{name}:begin -->(.*?)<!-- plc-{name}:end -->", text, re.S
    )
    assert len(found) == 1, f"expected exactly one plc-{name} block, found {len(found)}"
    return found[0]


def _dispatch_table():
    fenced = re.search(r"```json\n(.*?)\n```", _block("dispatch"), re.S)
    assert fenced, "the dispatch block holds no fenced json"
    return json.loads(fenced.group(1))


# --- the skip marker is a template, not a sentence a model composes -------------------


def test_the_two_lines_are_exactly_the_template():
    out = subprocess.run(
        ["bash", str(SKIP), "second-agent", "fast", "1.2"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    assert out == list(EXPECTED_MARKER)


def test_the_emitter_has_no_free_text_slot():
    """The half that matters: a model must not be able to write either line."""
    src = SKIP.read_text(encoding="utf-8")
    assert '"$*"' not in src, "a catch-all argument is a free-text slot"
    assert '"$@"' not in src, "a catch-all argument is a free-text slot"
    # The two printf templates take three positional substitutions between them and no others.
    templates = [l for l in src.splitlines() if l.startswith("printf '<!--") or l.startswith("printf '_Not")]
    assert len(templates) == 2, f"expected exactly two emitting printfs, found {len(templates)}"


@pytest.mark.parametrize(
    "args",
    [
        ("second-agent", "fast"),
        ("second-agent", "fast", "1.2", "extra"),
        ("", "fast", "1.2"),
        ("second agent", "fast", "1.2"),
        ("second-agent", "fa|st", "1.2"),
    ],
)
def test_a_field_the_format_cannot_carry_is_refused(args):
    """A marker with a blank or separator-bearing field is uncountable, so it is refused loudly."""
    p = subprocess.run(["bash", str(SKIP), *args], capture_output=True, text=True)
    assert p.returncode != 0
    assert p.stdout.strip() == "", "a refused invocation must not also emit half a marker"


# --- one table drives both modes -----------------------------------------------------


def test_one_artifact_table_serves_both_modes():
    """Path set and heading set are equal BY CONSTRUCTION: there is no per-mode variant."""
    table = _block("artifact-shape")
    assert "fast" not in table and "detailed" not in table, (
        "the artifact-shape table names a mode, so the two modes can diverge"
    )
    rows = [l for l in table.splitlines() if l.strip().startswith("|")]
    # header + separator + at least four artifacts
    assert len(rows) >= 6, f"the artifact-shape table has only {len(rows)} rows"


def test_the_mode_document_says_the_mode_never_removes_a_heading():
    """The rule the table encodes has to be stated, or a reader infers the opposite.

    Whitespace-normalised, and that is not laziness: the sentence wraps across two lines in the
    source, so a byte-exact match here would assert the line-wrap rather than the rule, and would
    red on a reflow that changed nothing.
    """
    text = " ".join(MODE_MD.read_text(encoding="utf-8").split())
    assert "never decides whether the heading is there" in text


# --- the dispatch table ------------------------------------------------


def test_compressed_is_two_slots_and_full_is_strictly_more():
    """The count comes from the table, not from prose."""
    table = _dispatch_table()
    assert len(table["cadence"]["compressed"]) == 2
    assert len(table["cadence"]["full"]) > len(table["cadence"]["compressed"])


def test_the_acceptance_author_is_never_the_implementer():
    """The hard constraint, checked in BOTH modes rather than only in the compressed one."""
    table = _dispatch_table()
    forbidden = table["acceptance_author_must_not_be"]
    for mode, slots in table["cadence"].items():
        for slot in slots:
            if "acceptance-tests" in slot["writes"]:
                assert slot["slot"] != forbidden, (
                    f"{mode}: {forbidden} writes the acceptance tests"
                )


def test_compressed_dissolves_no_stage():
    """Compressed changes WHO and HOW MANY, never WHETHER."""
    table = _dispatch_table()
    for mode, slots in table["cadence"].items():
        produced = {w for slot in slots for w in slot["writes"]}
        for stage in table["stages"]:
            assert any(stage in w for w in produced), (
                f"the {mode} dispatch produces no {stage} artifact -- that stage was dissolved"
            )


def test_every_stage_has_a_report_of_its_own():
    """A stage whose only output is shared with another cannot be dispatched alone."""
    table = _dispatch_table()
    produced = {w for slots in table["cadence"].values() for s in slots for w in s["writes"]}
    for stage in table["stages"]:
        assert f"{stage}-report" in produced, f"{stage} has no report artifact of its own"


def test_one_stage_runs_alone(tmp_path):
    """Dispatching one stage produces its report and neither of the other two."""
    subprocess.run(["bash", str(VERIFY), "acceptance"], cwd=tmp_path, check=True)
    assert (tmp_path / "acceptance-report.md").exists()
    assert not (tmp_path / "validation-report.md").exists()
    assert not (tmp_path / "quality-report.md").exists()


def test_an_unknown_stage_is_named_not_guessed(tmp_path):
    p = subprocess.run(
        ["bash", str(VERIFY), "correctness"], cwd=tmp_path, capture_output=True, text=True
    )
    assert p.returncode == 2
    assert "correctness" in p.stderr
    for stage in _dispatch_table()["stages"]:
        assert stage in p.stderr


def test_the_stage_runner_names_no_stage():
    """Same property as the resolver: the stage list is data, so the runner may not hardcode it."""
    src = VERIFY.read_text(encoding="utf-8")
    for stage in _dispatch_table()["stages"]:
        assert stage not in src, f"plc-verify-stage.sh hardcodes the stage name {stage!r}"
