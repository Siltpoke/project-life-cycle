"""AC suite for the SKILL.md reconstruction guard
(scripts/invariants/skill-reconstruction.sh).

the diet relocates ~half of the always-injected SKILL.md into load-on-demand references/ files,
preserving every byte (a MOVE, not a deletion). This guard is the keystone that proves the move
lost nothing: it rebuilds the pre-move SKILL.md from (the slim SKILL.md + each moved block pulled
from its destination by marker, spliced back at its pointer line) and asserts BYTE-EQUALITY against
the pinned pre-move git blob. No existing invariant guards SKILL.md prose, so this is net-new.

Each test asserts the EXIT CODE and, on a red path, that the failure is NAMED -- so a vacuous
always-green guard is caught. Sabotage cases (dropped line / reordered block / tampered bytes /
wrong pinned blob / absent-or-duplicated pointer / summarizing pointer / marker leak) must each go
RED; the faithful fixture and the real empty-manifest baseline must go GREEN.

The pre-move image is a PINNED GIT BLOB (cross-check A failure mode: a file copy can be post-edit or
from the stale core.bare main checkout). So every fixture creates a REAL blob via `git hash-object
-w` in a throwaway repo and pins that sha in its manifest header -- there is NO file-copy bypass
flag to test around.

**No CJK here** (leak gate). Pure subprocess over fixture paths.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
GUARD = REPO / "scripts" / "invariants" / "skill-reconstruction.sh"


# --- fixture building ---------------------------------------------------------------------------

ORIGINAL = (
    "line A top\n"
    "<!-- plc-move:one -->\n"  # markers are illustrative; blocks below are marker-free
    "BLOCK ONE CONTENT L1\n"
    "BLOCK ONE CONTENT L2\n"
    "line B middle\n"
    "BLOCK TWO CONTENT\n"
    "line C bottom\n"
)
# The ORIGINAL above is only a scratch string; the real fixtures are assembled block by block so a
# test can perturb one piece. Build them explicitly instead.

BLOCK_ONE = "BLOCK ONE CONTENT L1\nBLOCK ONE CONTENT L2\n"
BLOCK_TWO = "BLOCK TWO CONTENT\n"
PTR_ONE = "see references/d1.md when doing one"
PTR_TWO = "see references/d2.md when doing two"


def preimage_bytes() -> bytes:
    return (
        b"line A top\n"
        + BLOCK_ONE.encode()
        + b"line B middle\n"
        + BLOCK_TWO.encode()
        + b"line C bottom\n"
    )


def slim_bytes() -> bytes:
    return (
        b"line A top\n"
        + PTR_ONE.encode()
        + b"\n"
        + b"line B middle\n"
        + PTR_TWO.encode()
        + b"\n"
        + b"line C bottom\n"
    )


def delimited(block_id: str, body: str) -> str:
    return f"<!-- plc-move:{block_id} -->\n{body}<!-- /plc-move:{block_id} -->\n"


class Fixture:
    """A throwaway git repo holding a slim SKILL, dest refs, a manifest, and a pinned pre-move blob."""

    def __init__(self, tmp_path: Path):
        self.root = tmp_path
        subprocess.run(["git", "init", "-q"], cwd=str(self.root), check=True)
        (self.root / "references").mkdir(exist_ok=True)
        # defaults -- a faithful move
        self.preimage = preimage_bytes()
        self.skill = slim_bytes()
        self.d1 = delimited("one", BLOCK_ONE)
        self.d2 = delimited("two", BLOCK_TWO)
        self.rows = [
            ("one", "references/d1.md", "1", PTR_ONE),
            ("two", "references/d2.md", "2", PTR_TWO),
        ]
        self.write_d1 = True
        self.write_d2 = True

    def pin(self, data: bytes) -> str:
        p = self.root / "_preimage.tmp"
        p.write_bytes(data)
        sha = subprocess.run(
            ["git", "hash-object", "-w", str(p)],
            cwd=str(self.root),
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        p.unlink()
        return sha

    def materialize(self) -> tuple[Path, Path]:
        (self.root / "SKILL.md").write_bytes(self.skill)
        if self.write_d1:
            (self.root / "references" / "d1.md").write_text(self.d1)
        if self.write_d2:
            (self.root / "references" / "d2.md").write_text(self.d2)
        sha = self.pin(self.preimage)
        lines = [
            "# skill-move-manifest -- test fixture",
            f"# preimage-blob: {sha}",
            "# skill-file: SKILL.md",
            "# columns (tab-separated): block_id  dest_file  insert_order  pointer_line",
        ]
        for bid, dest, order, ptr in self.rows:
            lines.append("\t".join([bid, dest, order, ptr]))
        manifest = self.root / "manifest.tsv"
        manifest.write_text("\n".join(lines) + "\n")
        return self.root / "SKILL.md", manifest

    def run(self) -> subprocess.CompletedProcess:
        skill, manifest = self.materialize()
        return subprocess.run(
            ["/bin/bash", str(GUARD), "--check", "--skill", str(skill), "--manifest", str(manifest)],
            cwd=str(self.root),
            capture_output=True,
            text=True,
            env=dict(os.environ),
        )


# --- GREEN paths --------------------------------------------------------------------------------


def test_faithful_move_reconstructs_and_passes(tmp_path):
    """Slim SKILL + blocks spliced at their pointers == the pinned pre-move blob -> exit 0."""
    r = Fixture(tmp_path).run()
    assert r.returncode == 0, r.stdout + r.stderr
    assert "PASS" in r.stdout


def test_empty_manifest_untouched_file_passes(tmp_path):
    """Before any move: empty manifest, SKILL == pre-move blob -> reconstruction is identity -> 0."""
    f = Fixture(tmp_path)
    f.skill = f.preimage  # nothing moved yet
    f.rows = []
    f.write_d1 = f.write_d2 = False
    r = f.run()
    assert r.returncode == 0, r.stdout + r.stderr
    assert "PASS" in r.stdout


# --- RED: reconstruction byte-equality ----------------------------------------------------------


def test_dropped_line_in_moved_block_fails(tmp_path):
    """A moved block missing a line -> reconstruction shorter than the blob -> exit 1, named."""
    f = Fixture(tmp_path)
    f.d1 = delimited("one", "BLOCK ONE CONTENT L1\n")  # L2 dropped
    r = f.run()
    assert r.returncode == 1, r.stdout + r.stderr
    assert "FAIL" in r.stdout
    assert "reconstruct" in r.stdout.lower()


def test_reordered_block_content_fails(tmp_path):
    """Two lines of a block swapped -> bytes differ from the blob -> exit 1."""
    f = Fixture(tmp_path)
    f.d1 = delimited("one", "BLOCK ONE CONTENT L2\nBLOCK ONE CONTENT L1\n")
    r = f.run()
    assert r.returncode == 1, r.stdout + r.stderr
    assert "FAIL" in r.stdout


def test_tampered_block_bytes_fail(tmp_path):
    """A single altered byte in a moved block -> reconstruction mismatch -> exit 1."""
    f = Fixture(tmp_path)
    f.d1 = delimited("one", "BLOCK ONE CONTENT L1 TAMPERED\nBLOCK ONE CONTENT L2\n")
    r = f.run()
    assert r.returncode == 1, r.stdout + r.stderr
    assert "FAIL" in r.stdout


def test_reconstruction_against_wrong_blob_fails(tmp_path):
    """The manifest pins a sha for DIFFERENT content -> faithful move still mismatches -> exit 1."""
    f = Fixture(tmp_path)
    f.preimage = preimage_bytes() + b"an extra pre-move line\n"  # blob no longer matches the move
    r = f.run()
    assert r.returncode == 1, r.stdout + r.stderr
    assert "FAIL" in r.stdout


# --- RED: pointer presence + uniqueness ---------------------------------------------------------


def test_pointer_absent_from_skill_fails(tmp_path):
    """A manifest pointer that appears in no SKILL line -> exit 1 (can't splice the block back)."""
    f = Fixture(tmp_path)
    f.rows = [
        ("one", "references/d1.md", "1", "see references/d1.md when doing something-absent"),
        ("two", "references/d2.md", "2", PTR_TWO),
    ]
    r = f.run()
    assert r.returncode == 1, r.stdout + r.stderr
    assert "FAIL" in r.stdout


def test_pointer_matching_twice_fails(tmp_path):
    """A pointer line that appears 2x in SKILL is an ambiguous splice point -> exit 1."""
    f = Fixture(tmp_path)
    f.skill = f.skill + PTR_ONE.encode() + b"\n"  # the d1 pointer now appears twice
    r = f.run()
    assert r.returncode == 1, r.stdout + r.stderr
    assert "FAIL" in r.stdout


# --- RED: pointer SHAPE --------------------------------------------------------------------------


def test_summarizing_pointer_is_too_long_fails(tmp_path):
    """A long pointer that reproduces the moved body makes the agent never open the ref -> exit 1."""
    f = Fixture(tmp_path)
    summary = "see references/d1.md " + "x" * 250  # names the dest but is a wall of text
    f.skill = (
        b"line A top\n"
        + summary.encode()
        + b"\n"
        + b"line B middle\n"
        + PTR_TWO.encode()
        + b"\n"
        + b"line C bottom\n"
    )
    # preimage must correspond to this slim's splice so ONLY the shape check can fail it
    f.preimage = (
        b"line A top\n" + BLOCK_ONE.encode() + b"line B middle\n" + BLOCK_TWO.encode() + b"line C bottom\n"
    )
    f.rows = [
        ("one", "references/d1.md", "1", summary),
        ("two", "references/d2.md", "2", PTR_TWO),
    ]
    r = f.run()
    assert r.returncode == 1, r.stdout + r.stderr
    assert "FAIL" in r.stdout
    assert "pointer" in r.stdout.lower()


def test_pointer_not_naming_dest_fails(tmp_path):
    """A pointer that does not name its destination ref -> exit 1 (points nowhere)."""
    f = Fixture(tmp_path)
    bad = "go read the other doc when doing one"
    f.skill = (
        b"line A top\n"
        + bad.encode()
        + b"\n"
        + b"line B middle\n"
        + PTR_TWO.encode()
        + b"\n"
        + b"line C bottom\n"
    )
    f.rows = [
        ("one", "references/d1.md", "1", bad),
        ("two", "references/d2.md", "2", PTR_TWO),
    ]
    r = f.run()
    assert r.returncode == 1, r.stdout + r.stderr
    assert "FAIL" in r.stdout
    assert "pointer" in r.stdout.lower()


# --- RED: manifest grammar + dest extraction ----------------------------------------------------


def test_duplicate_block_id_fails(tmp_path):
    """Two rows sharing a block_id -> exit 1 (ids must be unique)."""
    f = Fixture(tmp_path)
    f.rows = [
        ("one", "references/d1.md", "1", PTR_ONE),
        ("one", "references/d2.md", "2", PTR_TWO),
    ]
    r = f.run()
    assert r.returncode == 1, r.stdout + r.stderr
    assert "FAIL" in r.stdout


def test_two_delimited_blocks_for_one_id_fails(tmp_path):
    """A dest holding the same id's block twice is ambiguous -> exit 1."""
    f = Fixture(tmp_path)
    f.d1 = delimited("one", BLOCK_ONE) + delimited("one", BLOCK_ONE)
    r = f.run()
    assert r.returncode == 1, r.stdout + r.stderr
    assert "FAIL" in r.stdout


def test_marker_leak_into_reference_fails(tmp_path):
    """A moved block carrying a plc-p31/plc-p34 bracket marker out of SKILL -> exit 1."""
    f = Fixture(tmp_path)
    leaked = "BLOCK ONE CONTENT L1\n<!-- plc-p31:start -->\nBLOCK ONE CONTENT L2\n"
    f.d1 = delimited("one", leaked)
    # keep reconstruction honest: the blob would have to contain the marker too, but the leak check
    # fires on the extracted block regardless of byte-equality.
    f.preimage = (
        b"line A top\n" + leaked.encode() + b"line B middle\n" + BLOCK_TWO.encode() + b"line C bottom\n"
    )
    r = f.run()
    assert r.returncode == 1, r.stdout + r.stderr
    assert "FAIL" in r.stdout
    assert "marker" in r.stdout.lower()


# --- CANNOT-RUN (exit 3), never a silent pass ---------------------------------------------------


def test_missing_skill_is_cannot_run(tmp_path):
    f = Fixture(tmp_path)
    skill, manifest = f.materialize()
    skill.unlink()
    r = subprocess.run(
        ["/bin/bash", str(GUARD), "--check", "--skill", str(skill), "--manifest", str(manifest)],
        cwd=str(f.root),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 3, r.stdout + r.stderr
    assert "CANNOT-RUN" in r.stdout


def test_missing_manifest_is_cannot_run(tmp_path):
    f = Fixture(tmp_path)
    r = subprocess.run(
        ["/bin/bash", str(GUARD), "--check", "--skill", str(tmp_path / "SKILL.md"),
         "--manifest", str(tmp_path / "nope.tsv")],
        cwd=str(f.root),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 3, r.stdout + r.stderr
    assert "CANNOT-RUN" in r.stdout


def test_missing_dest_file_is_cannot_run(tmp_path):
    """A manifest row naming a dest that is not on disk is a broken read -> exit 3, not a pass."""
    f = Fixture(tmp_path)
    f.write_d1 = False  # d1.md referenced by the manifest but never written
    r = f.run()
    assert r.returncode == 3, r.stdout + r.stderr
    assert "CANNOT-RUN" in r.stdout


def test_bad_preimage_sha_is_cannot_run(tmp_path):
    """A preimage header that is not resolvable as a blob -> exit 3 (never judge against nothing)."""
    f = Fixture(tmp_path)
    skill, manifest = f.materialize()
    text = manifest.read_text().replace(
        [l for l in manifest.read_text().splitlines() if l.startswith("# preimage-blob:")][0],
        "# preimage-blob: deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
    )
    manifest.write_text(text)
    r = subprocess.run(
        ["/bin/bash", str(GUARD), "--check", "--skill", str(skill), "--manifest", str(manifest)],
        cwd=str(f.root),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 3, r.stdout + r.stderr
    assert "CANNOT-RUN" in r.stdout


# --- regression lock on the shipped files -------------------------------------------------------


def test_dest_resolves_relative_to_skill_dir_not_cwd(tmp_path):
    """dest_file is relative to the SKILL file's directory (so SKILL.md can keep its
    `references/X` pointer convention), NOT to the process cwd. Run the guard from a cwd that is
    NOT the skill dir and confirm it still finds the dest refs under the skill dir."""
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
    skilldir = tmp_path / "skills" / "plc"
    (skilldir / "references").mkdir(parents=True)
    (skilldir / "SKILL.md").write_bytes(slim_bytes())
    (skilldir / "references" / "d1.md").write_text(delimited("one", BLOCK_ONE))
    (skilldir / "references" / "d2.md").write_text(delimited("two", BLOCK_TWO))
    pre = tmp_path / "_pre.tmp"
    pre.write_bytes(preimage_bytes())
    sha = subprocess.run(
        ["git", "hash-object", "-w", str(pre)], cwd=str(tmp_path),
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    manifest = tmp_path / "manifest.tsv"
    manifest.write_text(
        f"# preimage-blob: {sha}\n# skill-file: skills/plc/SKILL.md\n"
        f"one\treferences/d1.md\t1\t{PTR_ONE}\n"
        f"two\treferences/d2.md\t2\t{PTR_TWO}\n"
    )
    # cwd = repo root (tmp_path), skill is two dirs down -> dest must resolve under the skill dir
    r = subprocess.run(
        ["/bin/bash", str(GUARD), "--check", "--skill", "skills/plc/SKILL.md",
         "--manifest", str(manifest)],
        cwd=str(tmp_path), capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "PASS" in r.stdout


def test_real_skill_and_shipped_manifest_pass():
    """The shipped SKILL.md + .claude/skill-move-manifest.tsv must reconstruct clean in THIS repo.

    Before the move lands the manifest has zero data rows and SKILL == the pinned blob, so this is
    an identity reconstruction; after each move it proves no byte was lost. Either way: exit 0.
    """
    r = subprocess.run(
        ["/bin/bash", str(GUARD), "--check"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "PASS" in r.stdout
