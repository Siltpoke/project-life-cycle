#!/usr/bin/env python3
"""Mounted vs opened, for every capability this plugin ships.

The question this answers is not "is the skill any good". It is the one question
you cannot answer by reading the repo: *which of the things we ship has anyone
ever actually invoked?* A command that is mounted and never opened is not
evidence that it is useless — it is usually evidence that its description never
said which problem it solves. Those two cases look identical from inside the
repo, and they stay identical until someone counts.

Counting has to be done carefully, and the careless version is wrong in both
directions:

* **Matching the capability's name over-counts wildly.** Every session's system
  prompt lists every available skill, so a bare name match reports thousands of
  "hits" for a skill that was invoked a handful of times.
* **Counting only the Skill-tool form under-counts.** A user typing `/catchup`
  never produces a Skill tool call, and slash invocations can outnumber
  Skill-tool ones by a wide margin, so counting only one shape can
  report a heavily-used command as unused.

So only real invocation records are counted, in both call shapes, in both the
bare and the plugin-namespaced spelling. A capability reads as zero only when
all of them are zero.

Read-only: opens nothing but ~/.claude/projects/**/*.jsonl.
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TRANSCRIPTS = Path.home() / ".claude" / "projects"

# A Skill tool call records the skill it invoked; a slash command records the
# literal the user typed. Neither shape knows about the other, and a capability
# can be reached by either, so its count is the sum over both.
SKILL_CALL = re.compile(r'"name"\s*:\s*"Skill"\s*,\s*"input"\s*:\s*\{\s*"skill"\s*:\s*"([^"]+)"')
SLASH_CALL = re.compile(r"<command-name>/([a-zA-Z0-9:_-]+)</command-name>")
STAMP = re.compile(r'"timestamp"\s*:\s*"(\d{4}-\d{2}-\d{2})')


def mounted() -> list[str]:
    """Every capability this plugin ships, under the name a caller would type."""
    names = [p.stem for p in sorted((REPO / "commands").glob("*.md"))]
    names += [p.parent.name for p in sorted((REPO / "skills").glob("*/SKILL.md"))]
    return names


def scan() -> tuple[dict[str, dict[str, int]], dict[str, str], int]:
    """One pass over every transcript, tallying both call shapes per capability."""
    opened: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    last: dict[str, str] = {}
    files = sorted(TRANSCRIPTS.rglob("*.jsonl"))
    if not files:
        sys.exit(f"no transcripts under {TRANSCRIPTS} — refusing to report zeros "
                 f"that only mean nothing was read")
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for shape, pattern in (("skill", SKILL_CALL), ("slash", SLASH_CALL)):
            for m in pattern.finditer(text):
                # Both spellings collapse onto the capability's own name: the
                # namespaced form is the same button, not a second one.
                name = m.group(1).split(":")[-1]
                opened[name][shape] += 1
                stamp = STAMP.search(text, m.end(), m.end() + 4000)
                if stamp and stamp.group(1) > last.get(name, ""):
                    last[name] = stamp.group(1)
    return opened, last, len(files)


def main() -> int:
    caps = mounted()
    if not caps:
        sys.exit("no capabilities found — run this from inside the plugin repo")
    opened, last, scanned = scan()

    rows = []
    for c in caps:
        o = opened.get(c, {})
        sk, sl = o.get("skill", 0), o.get("slash", 0)
        rows.append((c, sk, sl, sk + sl, last.get(c, "never")))
    rows.sort(key=lambda r: (-r[3], r[0]))

    print(f"capability health — {len(caps)} mounted, {scanned} transcripts scanned\n")
    print(f"{'capability':<30}{'skill':>7}{'slash':>7}{'opened':>8}  last opened")
    print("-" * 66)
    for name, sk, sl, total, when in rows:
        print(f"{name:<30}{sk:>7}{sl:>7}{total:>8}  {when}")
    print("-" * 66)

    dead = [r[0] for r in rows if r[3] == 0]
    print(f"never opened: {len(dead)}/{len(caps)}")
    if dead:
        for d in dead:
            print(f"  - {d}")
        print("\nA zero is a question, not a verdict. Before removing any of these,")
        print("establish which one it is: nobody needs it, or nobody could tell when")
        print("to reach for it. Deleting it destroys the evidence that separates them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
