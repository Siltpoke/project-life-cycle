"""Controls for scripts/invariants/roadmap-has-vision.sh.

Each green row is paired with a RED row that differs by the one thing the check is about,
and the empty cases are the point: a heading or bold line that is present but blank must
fail, otherwise "required" means "required to type the label".
"""

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GUARD = REPO / "scripts" / "invariants" / "roadmap-has-vision.sh"
CJK_LABEL = chr(0x613f) + chr(0x666f)   # built from code points so this tracked file stays ASCII
IDEO_SP = chr(0x3000)


def run(tmp_path: Path, body: str | None) -> subprocess.CompletedProcess:
    rm = tmp_path / "ROADMAP.md"
    if body is not None:
        rm.write_text(body, encoding="utf-8")
    return subprocess.run(["/bin/bash", str(GUARD), str(rm)],
                          capture_output=True, text=True, cwd=REPO)


TABLE_OK = "# Roadmap\n\n## The one-sentence goal\nA tool that does the thing.\n\n## Milestones\n| a | b |\n"


def test_table_layout_goal_passes(tmp_path):
    r = run(tmp_path, TABLE_OK)
    assert r.returncode == 0, r.stdout + r.stderr


def test_english_bold_vision_passes(tmp_path):
    r = run(tmp_path, "# R\n\n**vision** A thing for people.\n**current** x\n\n## Done\n")
    assert r.returncode == 0, r.stdout + r.stderr


def test_cjk_bold_vision_with_ideographic_space_passes(tmp_path):
    r = run(tmp_path, f"# R\n\n**{CJK_LABEL}**{IDEO_SP}An end-to-end skill.\n\n## x\n")
    assert r.returncode == 0, r.stdout + r.stderr


def test_no_vision_at_all_is_red(tmp_path):
    r = run(tmp_path, "# R\n\n## Milestones\n| a | b |\n\n## Done\nstuff\n")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "no non-empty vision" in r.stderr


def test_empty_goal_heading_is_red(tmp_path):
    r = run(tmp_path, "# R\n\n## The one-sentence goal\n\n## Milestones\ntext here\n")
    assert r.returncode == 1, r.stdout + r.stderr


def test_goal_heading_at_eof_with_no_body_is_red(tmp_path):
    assert run(tmp_path, "# R\n\n## The one-sentence goal\n").returncode == 1


def test_unfilled_placeholder_goal_is_red(tmp_path):
    r = run(tmp_path, "# R\n\n## The one-sentence goal\n<what this project is, in one sentence>\n\n## Next\n")
    assert r.returncode == 1, r.stdout + r.stderr


def test_empty_bold_line_is_red(tmp_path):
    assert run(tmp_path, "# R\n\n**vision**\n\n## x\ntext\n").returncode == 1
    assert run(tmp_path, "# R\n\n**vision**   \n\n## x\n").returncode == 1


def test_empty_cjk_bold_line_is_red(tmp_path):
    assert run(tmp_path, f"# R\n\n**{CJK_LABEL}**{IDEO_SP}\n\n## x\n").returncode == 1


def test_bold_vision_after_first_header_does_not_count(tmp_path):
    # the parser only reads the head, so a late line is invisible to the card
    assert run(tmp_path, "# R\n\n## x\n**vision** too late\n").returncode == 1


def test_goal_body_in_a_different_section_does_not_leak_in(tmp_path):
    r = run(tmp_path, "# R\n\n## The one-sentence goal\n\n## Milestones\nreal text\n")
    assert r.returncode == 1, r.stdout + r.stderr


def test_missing_file_is_could_not_run_not_pass(tmp_path):
    r = run(tmp_path, None)
    assert r.returncode == 3, r.stdout + r.stderr


def test_live_repo_roadmap_passes():
    r = subprocess.run(["/bin/bash", str(GUARD)], capture_output=True, text=True, cwd=REPO)
    assert r.returncode == 0, r.stdout + r.stderr
