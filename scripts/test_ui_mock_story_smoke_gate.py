"""The two new phase-mode close-gate checks, each shown RED before GREEN.

Scope: checks 14 (ui-mock-contract) and 15 (story-driven-smoke) ONLY. Every other row this gate
runs is uncovered here on purpose — a bare fixture trips several of them, and this file asserts on
the 14/15 ROWS alone (their ✓/✗ line), never on the gate's overall verdict. The gate is run as the
variant (`scripts/close-gate.sh`); the canonical portable gate in close-gate.md does not implement
the phase-only checks 11-15, by the same choice that left 11-13 out of it.

Both checks verify PRESENCE, never correctness: 14 that a mock link + a checked confirm box exist
(not that the user truly confirmed); 15 that every AC id is NAMED in Track A (not that the step
walked the UI). The tests assert exactly that boundary.
"""
from pathlib import Path

import pytest

from close_gate_lib import make_fixture_repo, run_gate

ROOT = Path(__file__).resolve().parents[1]
GATE_SH = ROOT / "scripts/close-gate.sh"
PHASE = "demo-phase"

SPEC = f"docs/superpowers/specs/2026-01-01-phase-{PHASE}-x-design.md"
PLAN = f"docs/superpowers/plans/2026-01-01-phase-{PHASE}-x.md"
STORY = f"docs/superpowers/specs/2026-01-01-phase-{PHASE}-x-user-story.md"
SMOKE = f"docs/research/2026-01-01-m{PHASE}-smoke-checklist.md"


@pytest.fixture
def gate() -> str:
    return GATE_SH.read_text(encoding="utf-8")


def _row(stdout: str, needle: str) -> str:
    """The single ✓/✗ line whose text contains `needle` (the check name)."""
    for line in stdout.splitlines():
        if needle in line and (line.lstrip().startswith("✓") or line.lstrip().startswith("✗")):
            return line
    return ""


def _skipped_line(stdout: str) -> str:
    """The check-set line that enumerates the SKIPPED check ids."""
    for line in stdout.splitlines():
        if "check-set" in line and "skipped" in line:
            return line
    return ""


def _reached_gate(stdout: str) -> bool:
    """Proof the gate ran its full check-set (not an early abort): the running line is present."""
    return any("check-set" in ln and "running" in ln for ln in stdout.splitlines())


# ------------------------------------------------------------------ check 14: ui-mock-contract

def _spec(mock: bool, confirmed: bool, image: bool = True) -> str:
    body = ["# spec", "", "## UI Contract (confirmed mock)", ""]
    if mock:
        body.append("- **Mock**: [the screen](./mock/home.html)")
        if image:  # the approved visual is inline-embedded in the spec
            body.append("")
            body.append("![approved home screen](./mock/home.png)")
            body.append("")
    if confirmed:
        body.append("- [x] User confirmed this mock on 2026-01-01")
    else:
        body.append("- [ ] User confirmed this mock on {date}")
    body.append("")
    body.append("## Acceptance Criteria")
    body.append("- **AC1**: something observable")
    return "\n".join(body) + "\n"


def _ui_manifest(ui_change) -> dict:
    m = {
        "phase_docs_glob": "docs/superpowers/specs/*-phase-{PHASE}-*",
        "plan_glob": "docs/superpowers/plans/*-phase-{PHASE}-*",
        "user_story_glob": "docs/superpowers/specs/*-phase-{PHASE}-*-user-story.md",
        "exempt_user_story": True,
    }
    if ui_change is not None:
        m["ui_change"] = ui_change
    return m


def test_AC1_ui_mock_armed_without_mock_RED(tmp_path, gate):
    repo = make_fixture_repo(tmp_path, _ui_manifest(True), {SPEC: _spec(mock=False, confirmed=False), PLAN: "# plan\n"})
    r = run_gate(repo, gate, "phase", PHASE)
    row = _row(r.stdout, "ui-mock-contract")
    assert row.lstrip().startswith("✗"), f"expected RED ui-mock-contract row, got: {row!r}\n--full--\n{r.stdout}"
    assert "LINK" in row or "link" in row


def test_AC1_ui_mock_armed_with_mock_and_confirm_GREEN(tmp_path, gate):
    repo = make_fixture_repo(tmp_path, _ui_manifest(True), {SPEC: _spec(mock=True, confirmed=True), PLAN: "# plan\n"})
    r = run_gate(repo, gate, "phase", PHASE)
    row = _row(r.stdout, "ui-mock-contract")
    assert row.lstrip().startswith("✓"), f"expected GREEN ui-mock-contract row, got: {row!r}\n--full--\n{r.stdout}"
    assert "PRESENCE" in row  # the honest boundary is stated in the pass text


def test_AC1_ui_mock_link_but_unconfirmed_RED(tmp_path, gate):
    repo = make_fixture_repo(tmp_path, _ui_manifest(True), {SPEC: _spec(mock=True, confirmed=False), PLAN: "# plan\n"})
    r = run_gate(repo, gate, "phase", PHASE)
    row = _row(r.stdout, "ui-mock-contract")
    assert row.lstrip().startswith("✗"), f"link present but unconfirmed must RED, got: {row!r}\n--full--\n{r.stdout}"
    assert "confirm" in row.lower()


def test_ui_mock_armed_no_inline_image_RED(tmp_path, gate):
    # link + checked confirm present, but NO inline image embed -> RED naming the missing embed.
    repo = make_fixture_repo(tmp_path, _ui_manifest(True), {SPEC: _spec(mock=True, confirmed=True, image=False), PLAN: "# plan\n"})
    r = run_gate(repo, gate, "phase", PHASE)
    row = _row(r.stdout, "ui-mock-contract")
    assert row.lstrip().startswith("\u2717"), f"no inline image must RED, got: {row!r}\n{r.stdout}"
    assert "inline image" in row, row


def test_ui_mock_armed_with_inline_image_GREEN(tmp_path, gate):
    repo = make_fixture_repo(tmp_path, _ui_manifest(True), {SPEC: _spec(mock=True, confirmed=True, image=True), PLAN: "# plan\n"})
    r = run_gate(repo, gate, "phase", PHASE)
    row = _row(r.stdout, "ui-mock-contract")
    assert row.lstrip().startswith("\u2713"), f"inline image present must GREEN, got: {row!r}\n{r.stdout}"
    assert "EXISTENCE" in row  # honest boundary: existence only, not that the image is the right one


def test_ui_mock_unset_skipped_and_said(tmp_path, gate):
    # ui_change unset + no image: nothing fires, and the SKIPPED check-set line says 14 is off (and why).
    repo = make_fixture_repo(tmp_path, _ui_manifest(None), {SPEC: _spec(mock=False, confirmed=False), PLAN: "# plan\n"})
    r = run_gate(repo, gate, "phase", PHASE)
    assert _reached_gate(r.stdout), r.stdout
    assert _row(r.stdout, "ui-mock-contract") == "", r.stdout
    assert "14(ui-mock-contract)" in _skipped_line(r.stdout), _skipped_line(r.stdout)


def test_AC2_ui_mock_disarmed_no_over_fire(tmp_path, gate):
    # ui_change absent → the check must NOT fire: no ✓/✗ ui-mock row, and its id sits on the SKIPPED
    # check-set line (not the running one), and the gate ran its full check-set (no early abort).
    repo = make_fixture_repo(tmp_path, _ui_manifest(None), {SPEC: _spec(mock=False, confirmed=False), PLAN: "# plan\n"})
    r = run_gate(repo, gate, "phase", PHASE)
    assert _reached_gate(r.stdout), f"gate did not reach its check-set: {r.stdout}"
    assert _row(r.stdout, "ui-mock-contract") == "", f"disarmed check fired: {r.stdout}"
    assert "14(ui-mock-contract)" in _skipped_line(r.stdout), f"14 not on the skipped line: {r.stdout}"


def test_AC2_ui_mock_disarmed_when_false(tmp_path, gate):
    repo = make_fixture_repo(tmp_path, _ui_manifest(False), {SPEC: _spec(mock=False, confirmed=False), PLAN: "# plan\n"})
    r = run_gate(repo, gate, "phase", PHASE)
    assert _row(r.stdout, "ui-mock-contract") == "", f"ui_change:false must disarm: {r.stdout}"
    assert "14(ui-mock-contract)" in _skipped_line(r.stdout), f"14 not on the skipped line: {r.stdout}"


def test_AC2_ui_mock_unrelated_checked_box_does_not_green(tmp_path, gate):
    # A checked box about something OTHER than the mock must not satisfy the confirm marker.
    spec = (
        "# spec\n\n## UI Contract (confirmed mock)\n\n- **Mock**: [the screen](./mock/home.html)\n"
        "- [x] Reviewer confirmed the build passes\n\n## Acceptance Criteria\n- **AC1**: x\n"
    )
    repo = make_fixture_repo(tmp_path, _ui_manifest(True), {SPEC: spec, PLAN: "# plan\n"})
    r = run_gate(repo, gate, "phase", PHASE)
    row = _row(r.stdout, "ui-mock-contract")
    assert row.lstrip().startswith("✗"), f"an unrelated checked box must NOT green the mock-confirm check: {row!r}\n{r.stdout}"


def test_AC1_ui_mock_armed_no_files_RED(tmp_path, gate):
    # ui_change armed but neither story nor spec resolves → a RED that says there is nowhere for the contract.
    m = _ui_manifest(True)
    repo = make_fixture_repo(tmp_path, m, {PLAN: "# plan\n"})  # no SPEC, no STORY
    r = run_gate(repo, gate, "phase", PHASE)
    row = _row(r.stdout, "ui-mock-contract")
    assert row.lstrip().startswith("✗"), f"armed with no files must RED, got: {row!r}\n{r.stdout}"


# -------------------------------------------------------------- check 15: story-driven-smoke

def _story(acs) -> str:
    lines = ["# story", "", "## Acceptance Criteria", ""]
    lines += [f"- **{a}**: observable thing {a}" for a in acs]
    return "\n".join(lines) + "\n"


def _smoke(acs) -> str:
    lines = ["# Track A smoke", "", "| # | Step | Pass criteria | AC | Notes |", "|---|---|---|---|---|"]
    lines += [f"| S{i} | do {a} | ok | {a} | note |" for i, a in enumerate(acs, 1)]
    return "\n".join(lines) + "\n"


def _smoke_manifest() -> dict:
    return {
        "phase_docs_glob": "docs/superpowers/specs/*-phase-{PHASE}-*",
        "plan_glob": "docs/superpowers/plans/*-phase-{PHASE}-*",
        "user_story_glob": "docs/superpowers/specs/*-phase-{PHASE}-*-user-story.md",
        "smoke_a_glob": "docs/research/*-m{PHASE}-smoke-checklist.md",
        "exempt_user_story": False,
    }


def test_AC3_story_smoke_missing_ac_RED(tmp_path, gate):
    repo = make_fixture_repo(
        tmp_path, _smoke_manifest(),
        {STORY: _story(["AC1", "AC2", "AC3"]), SMOKE: _smoke(["AC1", "AC2"]), SPEC: "# spec\n", PLAN: "# plan\n"},
    )
    r = run_gate(repo, gate, "phase", PHASE)
    row = _row(r.stdout, "story-driven-smoke")
    assert row.lstrip().startswith("✗"), f"Track A missing AC3 must RED, got: {row!r}\n--full--\n{r.stdout}"
    assert "AC3" in row


def test_AC3_story_smoke_all_named_GREEN(tmp_path, gate):
    repo = make_fixture_repo(
        tmp_path, _smoke_manifest(),
        {STORY: _story(["AC1", "AC2", "AC3"]), SMOKE: _smoke(["AC1", "AC2", "AC3"]), SPEC: "# spec\n", PLAN: "# plan\n"},
    )
    r = run_gate(repo, gate, "phase", PHASE)
    row = _row(r.stdout, "story-driven-smoke")
    assert row.lstrip().startswith("✓"), f"all ACs named must GREEN, got: {row!r}\n--full--\n{r.stdout}"
    assert "NAMED" in row  # the honest boundary


def test_AC4_story_smoke_disarmed_no_smoke_glob(tmp_path, gate):
    # No smoke_a_glob → check 15 must not fire; its id sits on the SKIPPED line; gate ran fully.
    m = _smoke_manifest()
    del m["smoke_a_glob"]
    repo = make_fixture_repo(tmp_path, m, {STORY: _story(["AC1"]), SPEC: "# spec\n", PLAN: "# plan\n"})
    r = run_gate(repo, gate, "phase", PHASE)
    assert _reached_gate(r.stdout), f"gate did not reach its check-set: {r.stdout}"
    assert _row(r.stdout, "story-driven-smoke") == "", f"disarmed check fired: {r.stdout}"
    assert "15(story-driven-smoke)" in _skipped_line(r.stdout), f"15 not on the skipped line: {r.stdout}"


def test_AC4_story_smoke_armed_but_exempt_is_visible_skip(tmp_path, gate):
    # smoke_a_glob present but exempt_user_story:true → a visible ⊘ skip ON the story-driven-smoke line.
    m = _smoke_manifest()
    m["exempt_user_story"] = True
    repo = make_fixture_repo(tmp_path, m, {SMOKE: _smoke(["AC1"]), SPEC: "# spec\n", PLAN: "# plan\n"})
    r = run_gate(repo, gate, "phase", PHASE)
    sds_skip = [ln for ln in r.stdout.splitlines() if "⊘" in ln and "story-driven-smoke" in ln]
    assert sds_skip, f"expected a ⊘ line naming story-driven-smoke, got none:\n{r.stdout}"
    assert _row(r.stdout, "story-driven-smoke") == "", f"must not be a ✓/✗ row: {r.stdout}"


def test_AC3_story_smoke_ac1_does_not_cover_ac12(tmp_path, gate):
    # Word-boundary membership: a story with AC1 + AC12 whose Track A names only AC1 must RED on AC12.
    repo = make_fixture_repo(
        tmp_path, _smoke_manifest(),
        {STORY: _story(["AC1", "AC12"]), SMOKE: _smoke(["AC1"]), SPEC: "# spec\n", PLAN: "# plan\n"},
    )
    r = run_gate(repo, gate, "phase", PHASE)
    row = _row(r.stdout, "story-driven-smoke")
    assert row.lstrip().startswith("✗") and "AC12" in row, f"AC1 must not cover AC12: {row!r}\n{r.stdout}"


def test_AC3_story_smoke_subid_ac1_2_does_not_cover_ac1_RED(tmp_path, gate):
    # `grep -qw` treats `.` as a word boundary, so Track A naming only `AC1.2` used to satisfy
    # the story's `AC1`. A missing parent AC must RED even when a sub-id of it is named.
    repo = make_fixture_repo(
        tmp_path, _smoke_manifest(),
        {STORY: _story(["AC1", "AC2"]), SMOKE: _smoke(["AC1.2", "AC2"]), SPEC: "# spec\n", PLAN: "# plan\n"},
    )
    r = run_gate(repo, gate, "phase", PHASE)
    row = _row(r.stdout, "story-driven-smoke")
    assert row.lstrip().startswith("✗") and "AC1" in row, f"AC1.2 must not cover AC1: {row!r}\n{r.stdout}"
    assert "AC2" not in row.split("id(s):", 1)[-1].split("--", 1)[0], f"AC2 is named, must not be missing: {row!r}"


def test_AC3_story_smoke_subid_and_parent_both_named_GREEN(tmp_path, gate):
    repo = make_fixture_repo(
        tmp_path, _smoke_manifest(),
        {STORY: _story(["AC1", "AC2"]), SMOKE: _smoke(["AC1", "AC1.2", "AC2"]), SPEC: "# spec\n", PLAN: "# plan\n"},
    )
    r = run_gate(repo, gate, "phase", PHASE)
    row = _row(r.stdout, "story-driven-smoke")
    assert row.lstrip().startswith("✓"), f"AC1 and AC1.2 both named must GREEN: {row!r}\n{r.stdout}"


def _smoke_prose(lines) -> str:
    return "# Track A smoke\n\n" + "\n".join(lines) + "\n"


@pytest.mark.parametrize("tail", ["covers AC1. Then next step", "covers AC1."])
def test_AC3_story_smoke_sentence_final_ac1_GREEN(tmp_path, gate, tail):
    # a sentence-final `AC1.` (followed by a space, or end of line) is the id, not a sub-id.
    repo = make_fixture_repo(
        tmp_path, _smoke_manifest(),
        {STORY: _story(["AC1", "AC2"]), SMOKE: _smoke_prose([f"1. Step one {tail}", "2. Step two AC2"]),
         SPEC: "# spec\n", PLAN: "# plan\n"},
    )
    r = run_gate(repo, gate, "phase", PHASE)
    row = _row(r.stdout, "story-driven-smoke")
    assert row.lstrip().startswith("✓"), f"sentence-final AC1. must GREEN: {row!r}\n{r.stdout}"


def test_AC3_story_smoke_prose_subid_ac1_2_still_RED(tmp_path, gate):
    repo = make_fixture_repo(
        tmp_path, _smoke_manifest(),
        {STORY: _story(["AC1", "AC2"]), SMOKE: _smoke_prose(["1. Step one covers AC1.2 only", "2. Step two AC2"]),
         SPEC: "# spec\n", PLAN: "# plan\n"},
    )
    r = run_gate(repo, gate, "phase", PHASE)
    row = _row(r.stdout, "story-driven-smoke")
    assert row.lstrip().startswith("✗") and "AC1" in row, f"AC1.2 must not cover AC1: {row!r}\n{r.stdout}"
