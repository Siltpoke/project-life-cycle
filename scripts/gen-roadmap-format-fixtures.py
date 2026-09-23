"""One-shot: write the p36 golden fixture set."""
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])

TABLE = """# Roadmap — fixture

## 🛣 Mainline (follow it down)

| station | what | weight | eta |
|---|---|---|---|
| **○ CI line** | a docs-only change should not wait 31 minutes | 🔴 heavy | several sessions |
| **○ gate line** | whether the gates are right themselves | 🔴 heavy | several sessions |

"""


def plan(*blocks):
    return "## 🧭 Station plans\n\n<!-- plc-station-plan v1 -->\n\n" + "\n".join(blocks)


def active(*ids):
    body = "".join("- %s\n" % i for i in ids)
    return "## 🚦 In flight\n\n<!-- plc-station-active v1 -->\n" + body


CI = """### ci-line
- binds-to: **○ CI line**
- depends-on: none
- steps:
  - s1 measure the oracle
  - s2 filter the trigger by that oracle
"""

GATE = """### gate-line
- binds-to: **○ gate line**
- depends-on: ci-line
- steps:
  - s1 inventory the oracle behind each gate
"""

VALID = {
    "01-minimal": (
        TABLE + plan(CI) + "\n" + active("ci-line"),
        {"stations": ["ci-line"], "doing": ["ci-line"], "note":
         "One station, one plan block, one active entry. The baseline every "
         "invalid case is a single mutation away from."},
    ),
    "02-two-stations-with-deps": (
        TABLE + plan(CI, GATE) + "\n" + active(),
        {"stations": ["ci-line", "gate-line"], "doing": [], "note":
         "gate-line depends on ci-line; the active list is EMPTY but present. "
         "An empty list means 'nothing in flight'; a missing block is red, and "
         "this fixture pins that the two are not the same thing."},
    ),
}

EIGHT = """### ci-line
- binds-to: **○ CI line**
- depends-on: none
- steps:
""" + "".join("  - s%d step %d\n" % (i, i) for i in range(1, 9))

INVALID = {
    "01-zero-steps": (
        TABLE + plan("""### ci-line
- binds-to: **○ CI line**
- depends-on: none
- steps:
""") + "\n" + active(),
        "steps-lower-bound",
        "An empty steps list satisfies 'no more than 7' and 'no gaps' — both "
        "upper-bound style rules — and leaves a divide-by-zero in the position "
        "derivation. Only an explicit lower bound of 1 rejects it.",
    ),
    "02-eight-steps": (
        TABLE + plan(EIGHT) + "\n" + active(),
        "steps-upper-bound",
        "Eight steps, one over the bound.",
    ),
    "03-step-number-gap": (
        TABLE + plan("""### ci-line
- binds-to: **○ CI line**
- depends-on: none
- steps:
  - s1 measure the oracle
  - s3 filter the trigger by that oracle
""") + "\n" + active(),
        "steps-consecutive",
        "s2 is missing. A closure declaration naming ci-line.s2 would then be a "
        "dangling reference nobody could resolve.",
    ),
    "04-duplicate-station-id": (
        TABLE + plan(CI, CI.replace("**○ CI line**", "**○ gate line**")) + "\n" + active(),
        "station-id-unique",
        "Two blocks claim the same id while binding different rows. Measured "
        "precedent: two sessions filed the same id on the same day "
        "because the id allocator did not reserve.",
    ),
    "05-orphan-binds-to": (
        TABLE + plan(CI.replace("**○ CI line**", "**○ a station that does not exist**")) + "\n" + active(),
        "binds-to-resolves",
        "binds-to matches no mainline row. This is the cost of text binding, and "
        "the reason it is acceptable: the break is LOUD, unlike the silent "
        "text-as-identity breakage this format's research found elsewhere.",
    ),
    "06-two-blocks-one-row": (
        TABLE + plan(CI, CI.replace("### ci-line", "### ci-line-2")) + "\n" + active(),
        "row-bound-at-most-once",
        "Two distinct ids bind the same row; position would be ambiguous.",
    ),
    "07-self-loop": (
        TABLE + plan(CI.replace("depends-on: none", "depends-on: ci-line")) + "\n" + active(),
        "deps-acyclic",
        "A one-node cycle. A checker that only compares adjacent pairs reports "
        "this correctly and still lets 08 through — the two cases are not "
        "interchangeable.",
    ),
    "08-three-hop-cycle": (
        TABLE + plan(
            CI.replace("depends-on: none", "depends-on: gate-line"),
            GATE.replace("depends-on: ci-line", "depends-on: third-line"),
            """### third-line
- binds-to: **○ CI line**
- depends-on: ci-line
- steps:
  - s1 the third one
""",
        ) + "\n" + active(),
        "deps-acyclic",
        "a → b → c → a. The case a pairwise checker passes. (This fixture also "
        "trips row-bound-at-most-once; the declared rule is the cycle, and a "
        "runner must confirm the cycle is among the reasons, not merely that it "
        "was rejected.)",
    ),
    "09-dangling-dependency": (
        TABLE + plan(CI.replace("depends-on: none", "depends-on: no-such-station")) + "\n" + active(),
        "deps-resolve",
        "depends-on names an id no block declares.",
    ),
    "10-bare-done-line": (
        TABLE + plan("""### ci-line
- binds-to: **○ CI line**
- depends-on: none
- done
- steps:
  - s1 measure the oracle
""") + "\n" + active(),
        "closed-line-set",
        "`- done` carries NO COLON, so a key detector anchored on ':' never "
        "classifies it as a key and the closed-key-set rule does not see it. "
        "This is why the rule is stated over LINES.",
    ),
    "11-active-names-missing-station": (
        TABLE + plan(CI) + "\n" + active("no-such-station"),
        "active-names-known-station",
        "The active list names a station with no plan block.",
    ),
    "12-progress-written-in-what-cell": (
        TABLE.replace("a docs-only change should not wait 31 minutes", "a docs-only change should not wait 31 minutes (выполнено 2/3 шага)")
        + plan(CI) + "\n" + active(),
        "no-stored-position",
        "A hand-written position in the table's `what` cell, wrapped in a language the "
        "checker was never taught. A scanner looking for the English words "
        "done/position/progress matches none of it and passes while a position is very "
        "much stored; face 2 catches it because it scans for the SHAPE `N/M`, not for "
        "words. The wrapper was Chinese until the branch was first pushed and the leak "
        "gate refused CJK under skills/ (shipped bytes). It is Cyrillic now rather than "
        "English: rendering it in English would have deleted the only empirical case "
        "behind the language-neutrality claim and left the regex vouching for itself.",
    ),
    "13-block-inside-a-section": (
        TABLE.replace(
            "| **○ CI line** | a docs-only change should not wait 31 minutes | 🔴 heavy | several sessions |\n",
            "| **○ CI line** | a docs-only change should not wait 31 minutes | 🔴 heavy | several sessions |\n"
            "## 🧭 Station plans\n",
        ) + plan(CI) + "\n" + active(),
        "block-placement",
        "The plan heading is BETWEEN TWO TABLE ROWS — rows continue below it. "
        "Every table row's bytes are unchanged, which is exactly why 'compare "
        "the table bytes' is not sufficient evidence on its own. "
        "NOTE: the first version of this fixture put the heading AFTER THE LAST "
        "table row, which is a SAFE position (one of the nine measured), and "
        "it passed only because the guard's first implementation tested one side "
        "of a two-sided rule. A negative fixture rejected for the wrong reason "
        "proves nothing about the rule it claims — this one proved it about "
        "itself. (This fixture also trips other rules; the declared rule is "
        "placement.)",
    ),
}

for name, (text, meta) in VALID.items():
    d = ROOT / "valid" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "input.md").write_text(text)
    meta = dict(meta)
    meta["valid"] = True
    (d / "expected.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")

for name, (text, rule, why) in INVALID.items():
    d = ROOT / "invalid" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "input.md").write_text(text)
    (d / "expected.json").write_text(json.dumps(
        {"valid": False, "rule": rule, "why": why},
        ensure_ascii=False, indent=2) + "\n")

print("valid: %d  invalid: %d" % (len(VALID), len(INVALID)))
