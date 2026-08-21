"""The expansion map is data, and the reader never names a key.

WHY A STRUCTURAL HALF EXISTS ALONGSIDE THE BEHAVIOURAL ONE. A behavioural-only assertion (add a key
to a copy of the map, watch it resolve) passes on a reader that special-cases the eight keys it
knows and happens to agree with the map today. The structural half greps the reader for every
declared key name and requires zero occurrences, which is the property that matters:
adding a key is an edit to ONE file. Neither half alone is the criterion.
"""

import json
import pathlib
import re
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXPAND = ROOT / "skills/project-lifecycle/hooks/mode-expand.sh"
MODE_MD = ROOT / "skills/project-lifecycle/references/mode.md"

KEYS = (
    "intent-gate",
    "brainstorm",
    "cadence",
    "autonomy",
    "close-gate",
    "smoke-mode",
    "archetype",
    "second-agent-family",
)


def run(claude_md, map_path=None, expect=0):
    cmd = ["bash", str(EXPAND), "--claude-md", str(claude_md)]
    if map_path is not None:
        cmd += ["--map", str(map_path)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    assert p.returncode == expect, f"exit {p.returncode}, expected {expect}: {p.stderr}"
    return p


def parse(out):
    rows = {}
    for line in out.strip().splitlines():
        key, value, source = line.split("\t")
        rows[key] = (value, source)
    return rows


def extract_map():
    text = MODE_MD.read_text(encoding="utf-8")
    block = re.search(
        r"<!-- plc-mode-map:begin -->\s*```json\n(.*?)\n```\s*<!-- plc-mode-map:end -->",
        text,
        re.S,
    )
    assert block, "no single fenced map block between the sentinels"
    return json.loads(block.group(1))


def test_only_the_key_you_set_moves(tmp_path):
    """No `mode`, one low-level key set, and nothing else changes."""
    bare = tmp_path / "bare.md"
    bare.write_text("# CLAUDE.md\n", encoding="utf-8")
    one = tmp_path / "one.md"
    one.write_text("# CLAUDE.md\n\ncadence: compressed\n", encoding="utf-8")

    base = parse(run(bare).stdout)
    after = parse(run(one).stdout)

    assert after["cadence"] == ("compressed", "explicit")
    base.pop("cadence", None)
    after.pop("cadence", None)
    assert base == after, "a key other than `cadence` moved"


def test_intent_gate_is_never_moved_by_mode(tmp_path):
    """`mode` does not touch `intent-gate`; only an explicit key does."""
    for value in ("fast", "detailed"):
        f = tmp_path / f"{value}.md"
        f.write_text(f"# CLAUDE.md\n\nmode: {value}\n", encoding="utf-8")
        rows = parse(run(f).stdout)
        assert rows.get("intent-gate", (None, None))[1] != f"preset:{value}"

    explicit = tmp_path / "explicit.md"
    explicit.write_text("# CLAUDE.md\n\nmode: fast\nintent-gate: ask\n", encoding="utf-8")
    assert parse(run(explicit).stdout)["intent-gate"] == ("ask", "explicit")


def test_second_agent_family_is_never_moved_by_mode(tmp_path):
    """`second-agent-family` is a project setting; `mode` picks frequency, not lineage."""
    for value in ("fast", "detailed"):
        f = tmp_path / f"{value}.md"
        f.write_text(f"# CLAUDE.md\n\nmode: {value}\n", encoding="utf-8")
        rows = parse(run(f).stdout)
        assert rows.get("second-agent-family", (None, None))[1] != f"preset:{value}"


def test_the_reader_names_no_key():
    """The structural half — a key literal in the reader is a hardcoded key."""
    src = EXPAND.read_text(encoding="utf-8")
    # The reader's own prose may not name one either: a comment naming a key is how the next
    # editor learns it is safe to branch on one.
    for key in KEYS:
        assert key not in src, f"mode-expand.sh names the key {key!r}"


def test_a_new_key_takes_effect_from_the_map_alone(tmp_path):
    """The behavioural half — add a key to a COPY of the map, nothing else."""
    data = extract_map()
    data["keys"].append("verification")
    data["presets"]["fast"]["verification"] = "on-demand"
    data["presets"]["detailed"]["verification"] = "auto"

    copy = tmp_path / "mode.md"
    copy.write_text(
        "<!-- plc-mode-map:begin -->\n```json\n"
        + json.dumps(data, indent=2)
        + "\n```\n<!-- plc-mode-map:end -->\n",
        encoding="utf-8",
    )
    f = tmp_path / "CLAUDE.md"
    f.write_text("# CLAUDE.md\n\nmode: fast\n", encoding="utf-8")

    rows = parse(run(f, map_path=copy).stdout)
    assert rows["verification"] == ("on-demand", "preset:fast")


def test_an_illegal_mode_is_named_not_defaulted(tmp_path):
    """Edge case — `mode: turbo` must SAY SO; a silent fallthrough is a misconfiguration nobody sees."""
    f = tmp_path / "CLAUDE.md"
    f.write_text("# CLAUDE.md\n\nmode: turbo\n", encoding="utf-8")
    p = run(f, expect=2)
    assert "turbo" in p.stderr
    assert "fast" in p.stderr and "detailed" in p.stderr
    assert p.stdout.strip() == "", "an illegal mode must not also emit a resolved config"


def test_an_explicit_key_beats_the_preset_and_says_so(tmp_path):
    """Edge case — `mode: fast` + `cadence: full`. Written-down rule, visible source."""
    f = tmp_path / "CLAUDE.md"
    f.write_text("# CLAUDE.md\n\nmode: fast\ncadence: full\n", encoding="utf-8")
    rows = parse(run(f).stdout)
    assert rows["cadence"] == ("full", "explicit")
    assert rows["brainstorm"] == ("quick", "preset:fast")


def test_no_mode_and_no_keys_resolves_to_nothing(tmp_path):
    """The un-adopting project. `mode` absent must be byte-identical to never having heard of it."""
    f = tmp_path / "CLAUDE.md"
    f.write_text("# CLAUDE.md\n\nsome: other-key\n", encoding="utf-8")
    assert run(f).stdout.strip() == ""


def test_a_commented_out_key_is_not_a_setting(tmp_path):
    """A `#`-led line is a comment, not a value -- otherwise documentation sets policy."""
    f = tmp_path / "CLAUDE.md"
    f.write_text("# CLAUDE.md\n\n# mode: fast\n", encoding="utf-8")
    assert run(f).stdout.strip() == ""


def test_a_trailing_comment_is_stripped(tmp_path):
    """`mode: fast   # for now` is `fast`, not `fast   # for now`."""
    f = tmp_path / "CLAUDE.md"
    f.write_text("# CLAUDE.md\n\nmode: fast   # for now\n", encoding="utf-8")
    rows = parse(run(f).stdout)
    assert rows["cadence"] == ("compressed", "preset:fast")


@pytest.mark.parametrize("mode", ["fast", "detailed"])
def test_every_preset_key_is_declared(mode):
    """A preset naming a key outside `keys` would resolve to nothing and read as a silent drop."""
    data = extract_map()
    declared = set(data["keys"])
    for key in data["presets"][mode]:
        assert key in declared, f"preset {mode} sets {key!r}, which `keys` does not declare"


def test_never_set_by_mode_keys_are_absent_from_every_preset():
    """Belt and braces: the reader enforces it, and the DATA must not contradict the reader."""
    data = extract_map()
    for key in data["never_set_by_mode"]:
        for mode, preset in data["presets"].items():
            assert key not in preset, f"preset {mode} sets {key!r}, which mode must never touch"
