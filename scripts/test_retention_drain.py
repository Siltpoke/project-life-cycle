"""archive-working must MOVE, never delete — deletion is deferred until distill
quality is proven over 2-3 tracks."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from close_gate_lib import extract_retention_drain_script, make_fixture_repo

DRAIN = Path(__file__).resolve().parent / "retention-drain.sh"
RETENTION_MD = (
    Path(__file__).resolve().parents[1]
    / "skills/project-lifecycle/references/retention.md"
)


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(DRAIN), *args], cwd=repo, capture_output=True, text=True, check=False
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_fixture_repo(
        tmp_path,
        manifest={"retention": {"archive_dir": "docs/archive"}},
        files={"docs/superpowers/specs/2026-07-13-foo-design.md": "body\n"},
    )


def test_archive_working_moves_the_file(repo: Path) -> None:
    result = _run(repo, "archive-working", "docs/superpowers/specs/2026-07-13-foo-design.md")
    assert result.returncode == 0, result.stdout + result.stderr
    src = repo / "docs/superpowers/specs/2026-07-13-foo-design.md"
    dst = repo / "docs/archive/working/superpowers/specs/2026-07-13-foo-design.md"
    assert not src.exists(), "source must be gone from the hot path"
    assert dst.read_text() == "body\n", "content must survive byte-for-byte"


def test_archive_working_is_idempotent(repo: Path) -> None:
    p = "docs/superpowers/specs/2026-07-13-foo-design.md"
    assert _run(repo, "archive-working", p).returncode == 0
    second = _run(repo, "archive-working", p)
    assert second.returncode == 0, "re-running on an already-archived path must not fail"
    assert (repo / "docs/archive/working/superpowers/specs/2026-07-13-foo-design.md").exists()


def test_archive_working_refuses_screenshots(repo: Path) -> None:
    shot = repo / "docs/pr-drafts/screenshots/01.png"
    shot.parent.mkdir(parents=True)
    shot.write_bytes(b"png")
    result = _run(repo, "archive-working", "docs/pr-drafts/screenshots/01.png")
    assert result.returncode != 0
    assert shot.exists(), "load-bearing PR screenshots must never be moved"


def test_archive_working_missing_file_is_a_real_failure(repo: Path) -> None:
    result = _run(repo, "archive-working", "docs/superpowers/specs/never-existed.md")
    assert result.returncode != 0, "a file that was never archived and doesn't exist must fail"


def test_archive_working_refuses_to_clobber_a_differing_archived_original(repo: Path) -> None:
    """A re-opened/re-created track whose spec/plan filename collides with an
    already-archived original must NOT be silently overwritten by a plain `mv` — that archived
    original is the sole evidence the deferred-deletion decision rests on. RED against
    the pre-fix script: this assertion fails because `mv -- "$src" "$dst"` has no `-n` and
    clobbers `$dst` unconditionally."""
    p = "docs/superpowers/specs/2026-07-13-foo-design.md"
    assert _run(repo, "archive-working", p).returncode == 0
    dst = repo / "docs/archive/working/superpowers/specs/2026-07-13-foo-design.md"
    original_content = dst.read_text()
    assert original_content == "body\n"

    # simulate a re-opened track: the same path is recreated with DIFFERENT content
    src = repo / p
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("a second round of work, not the original body\n")

    result = _run(repo, "archive-working", p)
    assert result.returncode != 0, "must refuse rather than overwrite a differing archived original"
    assert dst.read_text() == original_content, "the archived original must survive byte-for-byte"
    assert src.exists(), "the recreated source must be left in place, not consumed by a failed move"


def test_archive_working_byte_identical_dst_is_a_harmless_no_op(repo: Path) -> None:
    """Companion case: if `$dst` already exists and is byte-identical to `$src` (e.g. the
    cadence retried archive-working before deleting/using the recreated source), that is not
    the dangerous case — nothing would be lost — so it must succeed as a no-op, not refuse."""
    p = "docs/superpowers/specs/2026-07-13-foo-design.md"
    assert _run(repo, "archive-working", p).returncode == 0
    dst = repo / "docs/archive/working/superpowers/specs/2026-07-13-foo-design.md"

    # recreate the source with the EXACT same bytes as what was already archived
    src = repo / p
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(dst.read_text())

    result = _run(repo, "archive-working", p)
    assert result.returncode == 0, result.stdout + result.stderr
    assert dst.read_text() == "body\n"


def test_archive_working_handles_untracked_file(repo: Path) -> None:
    # This repo gitignores docs/, so PLC-minted spec/plan files are frequently untracked.
    # `git mv` fails outright on an untracked path — archive-working must not blow up here.
    untracked = repo / "docs/superpowers/specs/2026-07-13-untracked-bar.md"
    untracked.parent.mkdir(parents=True, exist_ok=True)
    untracked.write_text("untracked body\n")
    # Confirm the fixture is actually untracked before trusting the assertion below.
    status = subprocess.run(
        ["git", "status", "--porcelain", str(untracked)],
        cwd=repo, capture_output=True, text=True, check=True,
    )
    assert status.stdout.startswith("??"), "fixture setup must produce an untracked file"

    result = _run(repo, "archive-working", "docs/superpowers/specs/2026-07-13-untracked-bar.md")
    assert result.returncode == 0, result.stdout + result.stderr
    dst = repo / "docs/archive/working/superpowers/specs/2026-07-13-untracked-bar.md"
    assert not untracked.exists()
    assert dst.read_text() == "untracked body\n"


def test_retention_md_fence_is_byte_identical_to_the_real_script() -> None:
    """retention.md embeds a full copy of retention-drain.sh as the canonical
    source /init-harness materializes into a project. That copy is a cache —
    prose derived from a live source — and caches rot silently unless something
    mechanically checks them. This is that check: if retention-drain.sh changes
    and the doc's fence isn't updated to match, this test goes red."""
    embedded = extract_retention_drain_script(RETENTION_MD)
    real = DRAIN.read_text(encoding="utf-8")
    assert embedded == real, (
        "skills/project-lifecycle/references/retention.md's ```bash fence has "
        "drifted from scripts/retention-drain.sh — resync the fence verbatim"
    )
