"""The three invariants this phase added, held to their REFUSALS and not only to their PASS.

WHY THIS FILE EXISTS. All three shipped with a one-off manual red and nothing else: a full-repo
search for each name found the manifest, the envelope's DECLARED list, some docs, and the script
itself -- no test anywhere. The phase-close review then found the consequence by hand: changing ONE
character of the anchored probe in `one-fragment-sentinel-reader.sh` left it printing
`PASS ... no fourth anchored matcher`, and nothing in the repo reddened. A one-off red proves the
check COULD refuse on the day it was written; a fixture proves it still can.

Every refusal test is paired with a control. A check that refuses everything passes a refusal test
just as well as a correct one, and this repo has recorded mutants scored dead for reasons unrelated
to the mutation.

The invariants resolve their own root with `git rev-parse --show-toplevel || pwd`, so a fixture tree
is driven by running them with `cwd` set to it. `_assert_not_in_a_repo` is not decoration: if a
fixture directory were inside some git repo, every one of these tests would silently be measuring
THAT repo instead, and would still pass.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
INV = SCRIPTS / "invariants"
RING_INV = INV / "no-ledger-evidence-under-preimages.sh"
READER_INV = INV / "one-fragment-sentinel-reader.sh"
KEEP_INV = INV / "preimage-keep-faces-agree.sh"

SENTINEL_REL = "scripts/lib/fragment-sentinel.awk"
EMBEDDING_RELS = ("scripts/close-gate.sh", "skills/project-lifecycle/references/close-gate.md")

# Assembled, never spelled: a file that talks about the sentinel must not read as a fourth matcher
# for it. The guard this file tests refuses exactly that, and refused its own sibling once already.
#
# `str.join`, NOT `+`. CPython CONSTANT-FOLDS an addition of two literals, so the joined string
# lands whole in `scripts/__pycache__/*.pyc` -- and the guard scans the filesystem, so it names the
# bytecode. Measured here: this file's first version was written with `+` and
# the invariant failed on its own `.pyc` while the source was clean. A method call is not folded.
ANCHORED = "".join(("^<!-- ", "fragment: "))


def _run(script: Path, cwd: Path, **env: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", str(script)],
        cwd=cwd, capture_output=True, text=True, check=False,
        env={**os.environ, **env},
    )


def _assert_not_in_a_repo(d: Path) -> None:
    probe = subprocess.run(
        ["/usr/bin/git", "rev-parse", "--show-toplevel"],
        cwd=d, capture_output=True, text=True, check=False,
    )
    assert probe.returncode != 0, (
        f"{d} is inside the git repo {probe.stdout.strip()!r}, so these scripts would resolve "
        "their root to that repo and every assertion below would be about the wrong tree"
    )


# ── no-ledger-evidence-under-preimages ────────────────────────────────────────────────────

def _registry_with_root(root: str) -> dict:
    return {
        "stages": [
            {
                "stage_id": "qa_log",
                "retro_evidence": [{"kind": "fragment-marker", "roots": [root]}],
            }
        ]
    }


def _ring_fixture(tmp_path: Path, root: str, archive_dir: str = "docs/archive") -> Path:
    d = tmp_path / "repo"
    (d / ".claude").mkdir(parents=True)
    (d / ".claude" / "stage-registry.json").write_text(
        json.dumps(_registry_with_root(root)), encoding="utf-8"
    )
    (d / ".claude" / "close-gate.json").write_text(
        json.dumps({"retention": {"archive_dir": archive_dir}}), encoding="utf-8"
    )
    _assert_not_in_a_repo(d)
    return d




def test_ring_invariant_refuses_a_root_inside_the_ring(tmp_path: Path) -> None:
    repo = _ring_fixture(tmp_path, "docs/archive/.pre-images/0004/files/docs/qa-log.d/x.md")
    result = _run(RING_INV, repo)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "names the pre-image ring" in result.stderr, result.stderr
    assert "stage qa_log, kind fragment-marker" in result.stderr, result.stderr


def test_ring_invariant_refuses_the_same_root_spelled_with_a_leading_dot(tmp_path: Path) -> None:
    """Measured hole, not a hypothetical: against the version this phase first shipped, this exact
    registry exited 0 and printed PASS. A location check that depends on the spelling of the path
    is a location check that can be stepped around by accident."""
    repo = _ring_fixture(tmp_path, "./docs/archive/.pre-images/0004/files/docs/qa-log.d/x.md")
    result = _run(RING_INV, repo)
    assert result.returncode == 1, (
        "a ring root written with a leading ./ was accepted:\n" + result.stdout + result.stderr
    )


def test_ring_invariant_cannot_run_when_the_registry_declares_no_roots(tmp_path: Path) -> None:
    d = tmp_path / "repo"
    (d / ".claude").mkdir(parents=True)
    (d / ".claude" / "stage-registry.json").write_text(
        json.dumps({"stages": [{"stage_id": "qa_log", "retro_evidence": None}]}), encoding="utf-8"
    )
    (d / ".claude" / "close-gate.json").write_text(
        json.dumps({"retention": {"archive_dir": "docs/archive"}}), encoding="utf-8"
    )
    _assert_not_in_a_repo(d)
    result = _run(RING_INV, d)
    assert result.returncode == 3, (
        "0 declared roots passed instead of refusing to run:\n" + result.stdout + result.stderr
    )
    assert "would pass by having nothing to read" in result.stderr, result.stderr


def test_ring_invariant_cannot_run_without_the_manifest_that_locates_the_ring(
    tmp_path: Path,
) -> None:
    repo = _ring_fixture(tmp_path, "docs/archive/brainstorming-qa-log/part-aa.md")
    (repo / ".claude" / "close-gate.json").unlink()
    result = _run(RING_INV, repo)
    assert result.returncode == 3, (
        "the ring's location was unknown and the check passed anyway:\n"
        + result.stdout + result.stderr
    )


def test_ring_invariant_reads_the_archive_dir_rather_than_spelling_it(tmp_path: Path) -> None:
    """Both directions, because only the pair proves the value is READ. With the archive dir
    declared as `docs/vault`, a root under `docs/vault/.pre-images` must refuse and a root under
    `docs/archive/.pre-images` -- the hardcoded path -- must not even be looked at."""
    offending = _ring_fixture(
        tmp_path / "a", "docs/vault/.pre-images/0001/files/docs/qa-log.d/x.md", "docs/vault"
    )
    assert _run(RING_INV, offending).returncode == 1, "the declared archive dir was not used"

    elsewhere = _ring_fixture(
        tmp_path / "b", "docs/archive/.pre-images/0001/files/docs/qa-log.d/x.md", "docs/vault"
    )
    result = _run(RING_INV, elsewhere)
    assert result.returncode == 0, (
        "a path that is not under THIS repo's ring was refused, so the check is still matching a "
        "hardcoded string:\n" + result.stdout + result.stderr
    )


# ── one-fragment-sentinel-reader ───────────────────────────────────────────────────────────

def test_reader_invariant_passes_on_the_real_tree() -> None:
    result = _run(READER_INV, ROOT)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "2 embeddings byte-identical" in result.stdout, result.stdout


def test_reader_invariant_cannot_run_when_its_own_probe_stops_matching(tmp_path: Path) -> None:
    """A surviving mutant: one character of the anchored probe, and
    the PASS line still asserted "no fourth anchored matcher" -- from a probe that could no longer
    match one. Run against the REAL tree, because the mutant's whole point is that the tree is
    fine and the probe is not."""
    src = READER_INV.read_text(encoding="utf-8")
    needle = "ANCHORED='^<!-- '\"fragment: \""
    assert src.count(needle) == 1, "the probe is not assembled where this mutant expects"
    mutant = tmp_path / "reader-mutant.sh"
    mutant.write_text(src.replace(needle, "ANCHORED='^<!-- '\"fragmentZZ: \""), encoding="utf-8")

    control = _run(READER_INV, ROOT)
    assert control.returncode == 0, "the unmutated invariant does not pass, so this proves nothing"

    result = _run(mutant, ROOT)
    assert result.returncode == 3, (
        f"a probe that matches none of its own allow-list exited {result.returncode}:\n"
        + result.stdout + result.stderr
    )
    assert "DECLARED to match" in result.stderr, result.stderr


def test_reader_invariant_refuses_a_fourth_anchored_matcher(tmp_path: Path) -> None:
    """Check 2's actual job, in a tree where a fourth matcher can be planted. The three declared
    files are copied from the repo so check 1 (the byte pinning) still passes and the failure can
    only be check 2."""
    d = tmp_path / "repo"
    for rel in (SENTINEL_REL, *EMBEDDING_RELS):
        target = d / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, target)
    _assert_not_in_a_repo(d)

    control = _run(READER_INV, d)
    assert control.returncode == 0, (
        "the copied tree does not pass, so a later red could be about the copy:\n"
        + control.stdout + control.stderr
    )

    stray = d / "scripts" / "stray-boundary-reader.sh"
    stray.write_text(f'#!/bin/bash\nawk \'/{ANCHORED}/ {{ print }}\' "$1"\n', encoding="utf-8")
    result = _run(READER_INV, d)
    assert result.returncode == 1, (
        f"a fourth anchored matcher exited {result.returncode}:\n" + result.stdout + result.stderr
    )
    assert "stray-boundary-reader.sh" in result.stderr, result.stderr


def test_reader_invariant_cannot_run_without_its_source_text(tmp_path: Path) -> None:
    d = tmp_path / "repo"
    (d / "scripts").mkdir(parents=True)
    _assert_not_in_a_repo(d)
    result = _run(READER_INV, d)
    assert result.returncode == 3, result.stdout + result.stderr


# ── preimage-keep-faces-agree ──────────────────────────────────────────────────────────────

def _keep_fixture(tmp_path: Path, human: str, machine: object) -> Path:
    d = tmp_path / "repo"
    (d / ".claude").mkdir(parents=True)
    (d / "scripts").mkdir(parents=True)
    shutil.copy(ROOT / "scripts" / "retention-drain.sh", d / "scripts" / "retention-drain.sh")
    (d / "CLAUDE.md").write_text(
        "# Fixture\n\n```yaml\nretention:\n  " + human + "\n```\n", encoding="utf-8"
    )
    manifest: dict = {"retention": {"archive_dir": "docs/archive"}}
    if machine is not None:
        manifest["retention"]["preimage_keep"] = machine
    (d / ".claude" / "close-gate.json").write_text(json.dumps(manifest), encoding="utf-8")
    _assert_not_in_a_repo(d)
    return d


def test_keep_invariant_passes_on_a_fixture_whose_faces_agree(tmp_path: Path) -> None:
    """The control for every refusal below: the fixture shape itself is accepted when it is
    correct, so a red further down is about the planted disagreement and not about the fixture."""
    repo = _keep_fixture(tmp_path, "preimage-keep: 5", 5)
    result = _run(KEEP_INV, repo)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "human,machine,expected",
    [
        ("preimage-keep: 5", 4, "the two policy faces disagree"),
        ("preimage-keep: 5", None, "declares no `retention.preimage_keep`"),
        ("preimage-keep: five", "five", "not a non-negative integer"),
        ("preimage-keep: 0", 0, "A ring that keeps nothing"),
    ],
    ids=["faces-disagree", "machine-face-missing", "not-an-integer", "floor-of-one"],
)
def test_keep_invariant_refuses(
    tmp_path: Path, human: str, machine: object, expected: str
) -> None:
    repo = _keep_fixture(tmp_path, human, machine)
    result = _run(KEEP_INV, repo)
    assert result.returncode == 1, (
        f"expected a refusal, got {result.returncode}:\n" + result.stdout + result.stderr
    )
    assert expected in result.stderr, result.stderr


def test_keep_invariant_refuses_two_declarations_on_the_human_face(tmp_path: Path) -> None:
    repo = _keep_fixture(tmp_path, "preimage-keep: 5", 5)
    (repo / "CLAUDE.md").write_text(
        "# Fixture\n\n```yaml\nretention:\n  preimage-keep: 5\n  preimage-keep: 7\n```\n",
        encoding="utf-8",
    )
    result = _run(KEEP_INV, repo)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "declaration(s)" in result.stderr, result.stderr
