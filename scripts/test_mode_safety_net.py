"""`fast` switches nothing off, and each assertion is shown to red.

THE GREEN RUN IS NOT THE EVIDENCE. Every assertion below is proved by mutating a COPY of the file
it reads and requiring the named failure. The three real files are in the frozen `detailed` set or are
the mode document itself, so mutating them in place would fight a different guard -- and a guard
nobody has watched fail is a guard nobody has run.
"""

import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
NET = ROOT / "scripts/invariants/fast-keeps-the-net.sh"
GATE = ROOT / "scripts/close-gate.sh"
CONTRACT = ROOT / "skills/project-lifecycle/references/close-gate.md"
MODE_DOC = ROOT / "skills/project-lifecycle/references/mode.md"


def run(gate=None, contract=None, mode_doc=None):
    env = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin",
        "NET_GATE": str(gate or GATE),
        "NET_CONTRACT": str(contract or CONTRACT),
        "NET_MODE_DOC": str(mode_doc or MODE_DOC),
    }
    return subprocess.run(
        ["bash", str(NET)], capture_output=True, text=True, cwd=ROOT, env=env
    )


def copy(tmp_path, src):
    dst = tmp_path / src.name
    shutil.copy(src, dst)
    return dst


def test_the_real_tree_is_green():
    """Positive control. Without it, a check that reds on everything would look perfect."""
    p = run()
    assert p.returncode == 0, p.stdout + p.stderr


def test_n1_reds_when_the_gate_branches_on_the_approval_key(tmp_path):
    """A gate that branches on the key could be switched off by it."""
    g = copy(tmp_path, GATE)
    g.write_text(
        g.read_text(encoding="utf-8")
        + '\nif [ "$APPROVAL" = "pr-boundary" ]; then RUN_JOURNAL=0; fi\n',
        encoding="utf-8",
    )
    p = run(gate=g)
    assert p.returncode == 1
    assert "N1:" in p.stderr and "branch on the approval-timing key" in p.stderr


def test_n2_reds_when_the_teeth_stop_matching_the_trailer(tmp_path):
    """The net-delete check is trailer-driven, so the trailer is the dependency."""
    c = copy(tmp_path, CONTRACT)
    c.write_text(
        c.read_text(encoding="utf-8").replace("Archetype:[[:space:]]*sweep", "Kind:[[:space:]]*tidy"),
        encoding="utf-8",
    )
    p = run(contract=c)
    assert p.returncode == 1
    assert "N2:" in p.stderr and "no longer matches" in p.stderr


def test_n2_reds_when_silent_stops_meaning_infer_and_apply(tmp_path):
    """The whole hazard: read `silent` as 'do not classify' and two protections go quiet."""
    d = copy(tmp_path, MODE_DOC)
    d.write_text(
        d.read_text(encoding="utf-8").replace("infer and apply, do not ask", "skip classification"),
        encoding="utf-8",
    )
    p = run(mode_doc=d)
    assert p.returncode == 1
    assert "N2:" in p.stderr and "infer-and-apply" in p.stderr


def test_n3_reds_when_the_automated_smoke_stops_being_a_gate_item(tmp_path):
    """'Still runs' is not the claim; 'still gates' is."""
    d = copy(tmp_path, MODE_DOC)
    d.write_text(
        d.read_text(encoding="utf-8").replace(
            "Track B runs automatically **and is a gate item**",
            "Track B runs automatically when convenient",
        ),
        encoding="utf-8",
    )
    p = run(mode_doc=d)
    assert p.returncode == 1
    assert "N3:" in p.stderr and "gate item" in p.stderr


def test_n4_reds_when_a_preset_switches_something_off(tmp_path):
    """A preset may never carry a disabling value -- turning a thing off is the project's act."""
    d = copy(tmp_path, MODE_DOC)
    d.write_text(
        d.read_text(encoding="utf-8").replace(
            '"archetype": "silent"', '"archetype": "off"'
        ),
        encoding="utf-8",
    )
    p = run(mode_doc=d)
    assert p.returncode == 1
    assert "N4:" in p.stderr and "fast: archetype=off" in p.stderr


def test_only_the_mutated_assertion_reds(tmp_path):
    """One mutant, one assertion. A coarse mutant that trips two proves neither."""
    d = copy(tmp_path, MODE_DOC)
    d.write_text(
        d.read_text(encoding="utf-8").replace('"archetype": "silent"', '"archetype": "off"'),
        encoding="utf-8",
    )
    err = run(mode_doc=d).stderr
    tripped = {n for n in ("N1:", "N2:", "N3:", "N4:") if n in err}
    assert tripped == {"N4:"}, f"expected only N4, got {sorted(tripped)}"


def test_the_gate_really_does_not_read_the_key():
    """Stated as its own assertion because it is the load-bearing fact behind the first test.

    Not 'reads it and ignores it' -- there is no executable line in which the token appears.
    """
    lines = [
        l for l in GATE.read_text(encoding="utf-8").splitlines()
        if ("pr-boundary" in l or "per-task" in l) and not l.strip().startswith("#")
    ]
    assert lines == [], f"the deterministic gate has executable lines naming the key: {lines}"


@pytest.mark.parametrize("phrase", [
    "It runs on every push and blocks when red",
    "moves *the human approval*, not *the gate*",
])
def test_the_mode_document_states_the_gate_is_unchanged(phrase):
    doc = " ".join(MODE_DOC.read_text(encoding="utf-8").split())
    assert phrase in doc
