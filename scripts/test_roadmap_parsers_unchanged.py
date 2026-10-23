"""adding the station-plan blocks does not change what an
UNCHANGED parser sees.

WHY THIS IS A TEST AND NOT AN INVARIANT. AC-2 was split into three
separately-falsifiable criteria: [a] the mainline table's
bytes are unchanged, [b] the new `## ` blocks cut no existing section open, and
[c] PLC's own two parsers produce byte-identical output across the change.
[a] and [b] are pure text and live in the gate, in
`scripts/invariants/roadmap-station-blocks-placement.sh`. **[c] cannot live
there**: it has to run `session_card.py`, which is `python3`, and every script
under `scripts/invariants/` is watched by `gate-jq-only-envelope.sh` (widened by
B9003 from three named files to that whole directory). The gate is a drop-in for
other people's repos and each interpreter it needs is one more thing an adopter
must already have. So [c] runs here, under the manifest's declared
`test_command`. **Do not move it into the invariants directory because it looks
like the same job as [a]/[b].**

WHY [a] IS NOT ENOUGH ON ITS OWN — the reason the review's shortcut was rejected.
Both consumers define a section's body as "after this `## ` heading, up to the
NEXT `## `" (a downstream consumer's parser). The new blocks
are `## ` sections, so one dropped into the middle of an existing section
truncates that section's body **while every byte of every table row is still
exactly where it was**. "The table did not change" is necessary, not sufficient.

WHAT THE PASSES ARE WORTH. `test_insertion_points_are_all_safe` checks nine
placements and expects nine matches. Nine greens on their own say nothing — a
bench that compared the file with itself would print the same. The four
`test_control_*` cases are what make them quotable: three mutations that must
change the output, and one that attacks the bench itself.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ROADMAP = REPO / "docs" / "ROADMAP.md"

sys.path.insert(0, str(REPO / "scripts"))
import session_card as sc  # noqa: E402

# The two blocks the station-plan format introduces, in the shape its own example uses.
# The CONTENT here is synthetic and deliberately English: this file is shipped bytes and the
# CJK rule refuses CJK outside docs/. What the test needs from these lines is their SHAPE —
# two `## ` sections carrying the two marker comments — and no assertion below reads a word of
# the prose, so translating it changes nothing the test measures. (The real block in
# docs/ROADMAP.md is Chinese and stays that way; docs/ is exempt.)
BLOCKS = """## 🧭 Station plans

<!-- plc-station-plan v1 -->

### ci-line
- binds-to: **▶ example line — a sample station this fixture binds to**
- depends-on: none
- steps:
  - s1 measure which assertions a docs-only change can move
  - s2 narrow the trigger from everything to that set
  - s3 make the green state which tree it tested

## 🚦 In flight

<!-- plc-station-active v1 -->
- ci-line
"""


def _fingerprint(text):
    """What an unchanged consumer sees. Both of PLC's parsers, serialised.

    `_milestone_table_rows` is included alongside `parse_roadmap` deliberately:
    they are the two glyph parsers a later merge will unify, and the criterion is about BOTH.
    Serialising with sort_keys makes the comparison byte-exact rather than
    structural, so a reordering that a dict comparison would forgive still shows
    up.
    """
    return json.dumps(
        {
            "parse_roadmap": sc.parse_roadmap(text),
            "milestone_table_rows": sc._milestone_table_rows(text),
        },
        ensure_ascii=False,
        sort_keys=True,
    )


@pytest.fixture(scope="module")
def roadmap():
    md = ROADMAP.read_text()
    # An empty or unparseable roadmap would make every comparison below trivially
    # equal. Two empty fingerprints compare the same as two verified ones.
    assert md.strip(), "docs/ROADMAP.md is empty — every comparison here would be vacuous"
    rows = sc._milestone_table_rows(md)
    assert rows, "no mainline rows parsed — the comparisons below would verify nothing"
    return md


@pytest.fixture(scope="module")
def baseline(roadmap):
    return _fingerprint(roadmap)


def _headings(md):
    return [i for i, line in enumerate(md.split("\n")) if line.startswith("## ")]


def _insert_at(md, index):
    lines = md.split("\n")
    return "\n".join(lines[:index] + BLOCKS.split("\n") + lines[index:])


def test_insertion_points_are_all_safe(roadmap, baseline):
    """AC-2c. Nine placements — before each existing `## `, and at EOF.

    Read together with the four control tests below; on their own these nine
    passes are not evidence.
    """
    points = _headings(roadmap) + [len(roadmap.split("\n"))]
    assert len(points) >= 2, "fewer than two candidate insertion points — scope too small to mean anything"
    changed = [i for i in points if _fingerprint(_insert_at(roadmap, i)) != baseline]
    assert changed == [], (
        "inserting the station blocks at these line indexes changed what an "
        f"unchanged parser sees: {changed}"
    )


def test_control_one_character_in_a_mainline_row(roadmap, baseline):
    """Negative control. If this passes, the bench is not reading the table."""
    # Escapes, not characters: this file is shipped bytes and the CJK rule refuses them
    # outside docs/. The target text lives in docs/ROADMAP.md, which is not ASCII and stays
    # that way, so the control has to name it somehow — U+7EBF is swapped for its variant
    # U+7DBB, a one-character change that must move the fingerprint.
    mutated = roadmap.replace("\u25cb \u793a\u4f8b\u7ebf", "\u25cb \u793a\u4f8b\u7dbb", 1)
    assert mutated != roadmap, "mutation did not apply — the control proves nothing"
    assert _fingerprint(mutated) != baseline


def test_control_heading_inside_the_table(roadmap, baseline):
    """Negative control, and the one that refutes 'just compare the table bytes'.

    Every table ROW is byte-identical after this mutation; only a `## ` line was
    inserted between two of them. The output must still change.
    """
    lines = roadmap.split("\n")
    head = next(i for i, l in enumerate(lines) if l.startswith("## 🛣"))
    row = next(i for i in range(head, len(lines)) if lines[i].startswith("| **○"))
    # The heading text after the emoji is not read by either parser — both key on the
    # emoji — so this control says the same thing in English.
    mutated = "\n".join(lines[: row + 1] + ["## \U0001f9ed Station plans"] + lines[row + 1 :])
    assert _fingerprint(mutated) != baseline


def test_control_fifth_column(roadmap, baseline):
    """Negative control. Reproduces the measurement that ruled out a fifth column."""
    lines = roadmap.split("\n")
    head = next(i for i, l in enumerate(lines) if l.startswith("## 🛣"))
    row = next(i for i in range(head, len(lines)) if lines[i].startswith("| **○"))
    lines[row] = lines[row].rstrip() + " x |"
    assert _fingerprint("\n".join(lines)) != baseline


def test_control_bad_base_sha_is_loud(tmp_path):
    """Negative control aimed at the BENCH, not the subject.

    The three controls above mutate the roadmap. This one attacks the way a
    future version of this bench is most likely to break: resolving the
    pre-change parser via `git show <base>:path` and, when that fails, falling
    through to an empty string — after which "before" and "after" compare equal
    and the bench reports a pass having read nothing.

    Nothing in this file uses `git show` today (the fingerprints come from the
    in-tree parser). This test pins the requirement for when that merge lands and the
    comparison has to reach back for the pre-merge parser: the failure must be
    loud. It asserts on git's own behaviour so it cannot rot into a tautology.
    """
    proc = subprocess.run(
        ["git", "show", "0000000000000000000000000000000000000000:docs/ROADMAP.md"],
        cwd=REPO, capture_output=True, text=True,
    )
    assert proc.returncode != 0, "git show on a nonexistent object must fail, not return empty"
    assert proc.stdout == "", (
        "git show wrote content for a nonexistent object; a bench that ignores the "
        "exit code would silently compare against this"
    )
