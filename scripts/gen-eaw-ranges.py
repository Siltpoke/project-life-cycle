#!/usr/bin/env python3
"""Regenerate `scripts/lib/eaw-ranges.jq` from the Unicode database.

RUN THIS BY HAND, NOT FROM THE GATE. The output is a frozen jq literal that the
gate reads; this generator is not in the gate's dependency envelope and must not
become part of it (`CLAUDE.md`: the close gate stays jq-only, because it is a
drop-in for other people's repos and every interpreter it needs is one more thing
an adopter must already have).

WHY A GENERATED TABLE AND NOT A HAND-WRITTEN THRESHOLD. The spec's rev 2 carried
four hand-written lines of jq for this:

    def dispwidth: [explode[] | if . > 0x2E80 then 2 else 1 end] | add;

Two independent defects, both measured rather than argued:
  1. It cannot parse. `jq -n '0x2E80'` is `syntax error, unexpected IDENT` --
     jq's number grammar has no hex literal. Those four lines had never been run,
     and they sat immediately below a sentence promising not to pretend the
     approximation was a real width table.
  2. The sentence beside it -- "the direction is conservative, it never
     under-counts" -- was false. U+1100 (HANGUL CHOSEONG KIYEOK) and U+2329 are
     both East_Asian_Width=W and that threshold returns 1 for both.

The lesson taken was not "pick a better threshold". A per-codepoint width is a
property of the Unicode database, so it gets EXPORTED from the database, and the
export is checked against that same database at every range boundary. Nobody
gets to guess which codepoints are wide.

Usage:
    python3 scripts/gen-eaw-ranges.py            > scripts/lib/eaw-ranges.jq
    python3 scripts/gen-eaw-ranges.py --snapshot > scripts/lib/eaw-boundary-widths.json

TWO OUTPUTS, AND THE SECOND ONE IS WHY (p35). The header line records the Unicode
version the table came from. `test_eaw_width.py` used to re-derive its
expectations from `unicodedata` at run time, which sounds like the two moving
together and is in fact the two moving together ONLY on an interpreter whose
Unicode version equals the one in that header. On every other interpreter the
comparison has no oracle, so it skipped -- and CI ran Python 3.12 against a table
declaring 15.1.0, so the three comparison tests skipped on every CI run since the
table landed. MEASURED, not argued: with `[4352,4447]` mutated to `[4352,4448]`,
Python 3.10 (unidata 13.0.0) reports passes and skips and exits 0, while
Python 3.13 (unidata 15.1.0) reports failures. A wrong table, and a green run.

So the expectations are now EXPORTED here too, next to the table and from the same
database read, and the comparison tests read the export instead of the live
database. That makes them interpreter-independent: a mutated table disagrees with
the snapshot on any Python.

WHAT THIS PAIR DOES NOT PROVE, stated rather than implied. Table and snapshot come
out of the same `unicodedata`, so they cannot cross-check each other's SOURCE --
they catch a hand-edit to either file and a bug in the jq lookup, and they do not
catch a generator that read the database wrongly. That claim needs the live
database, has no oracle under version skew, and is left to the one remaining
version-gated test in `test_eaw_width.py`.

--snapshot writes to STDOUT rather than editing the .json in place, deliberately:
`test_table_and_snapshot_are_what_the_generator_produces_today` runs this generator
during the test run, and a generator with a side effect on a tracked file would
rewrite the very artifact the suite is checking.
"""
import json
import sys
import unicodedata

WIDE = ("W", "F")


def ranges():
    out = []
    start = None
    prev = None
    for cp in range(0, 0x110000):
        if unicodedata.east_asian_width(chr(cp)) in WIDE:
            if start is None:
                start = cp
            prev = cp
        elif start is not None:
            out.append((start, prev))
            start = None
    if start is not None:
        out.append((start, prev))
    return out


def boundary_points(rs):
    """The four points per range where an off-by-one shows: start-1, start, end, end+1.

    This is the same set `test_eaw_width.py` used to build from the live database.
    It is computed here so the snapshot and the test cannot disagree about WHICH points
    are checked -- a snapshot covering a different set than the test asks for would be a
    silent hole rather than a failure.
    """
    pts = set()
    for a, b in rs:
        for p in (a - 1, a, b, b + 1):
            if 0 <= p < 0x110000:
                pts.add(p)
    return sorted(pts)


def emit_snapshot(rs):
    pts = boundary_points(rs)
    if len(pts) <= 100:
        # Same floor the test asserts. A snapshot with a handful of points would let the
        # boundary test pass while checking almost nothing, which is the failure shape
        # this whole file exists to keep out.
        print("refusing to emit a snapshot with only %d boundary points" % len(pts),
              file=sys.stderr)
        return 1
    # Fields, and what is deliberately NOT a field. `generated_by` names BOTH commands
    # because the pair must be regenerated together and this file is one of the two places
    # a maintainer actually opens. Two prose fields ("what" / "not_proven") used to live
    # here and were removed: nothing reads them, they were the sixth and seventh copy of an
    # explanation the generator docstring and the phase spec already carry, and because the
    # sync test compares this file BYTE FOR BYTE, fixing a typo in English prose forced
    # regenerating a 437-line data file on a version-matching interpreter.
    doc = {
        "generated_by": (
            "python3 scripts/gen-eaw-ranges.py --snapshot > scripts/lib/eaw-boundary-widths.json"
            "  (regenerate its pair in the same breath: "
            "python3 scripts/gen-eaw-ranges.py > scripts/lib/eaw-ranges.jq)"
        ),
        "unicode_version": unicodedata.unidata_version,
        "widths": {str(cp): (2 if unicodedata.east_asian_width(chr(cp)) in WIDE else 1)
                   for cp in pts},
    }
    # sort_keys is load-bearing for reproducibility: the sync test compares this output
    # byte-for-byte against the committed file.
    sys.stdout.write(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    return 0


def main():
    rs = ranges()
    if not rs:
        # A build of Python whose unicodedata reports nothing wide would silently
        # produce a table that calls every character single-width, and every
        # width check downstream would pass while measuring nothing.
        print("refusing to emit an empty range table", file=sys.stderr)
        return 1

    if "--snapshot" in sys.argv[1:]:
        return emit_snapshot(rs)

    w = sys.stdout.write
    w("# GENERATED by scripts/gen-eaw-ranges.py -- do not hand-edit.\n")
    w("# Source: python3 unicodedata %s, East_Asian_Width in {W, F}.\n"
      % unicodedata.unidata_version)
    w("# %d ranges. THE PAIR IS REGENERATED TOGETHER -- run both, on ONE interpreter:\n" % len(rs))
    w("#     python3 scripts/gen-eaw-ranges.py            > scripts/lib/eaw-ranges.jq\n")
    w("#     python3 scripts/gen-eaw-ranges.py --snapshot > scripts/lib/eaw-boundary-widths.json\n")
    w("# Regenerating only this file leaves the snapshot an oracle for a table that no\n")
    w("# longer exists, and the suite tells you so one red cycle later than it needs to.\n")
    w("#\n")
    w("# DECLARED BEHAVIOUR, so it is a choice on the page rather than a silent bias:\n")
    w("#   * East_Asian_Width=Ambiguous counts as 1. That includes glyphs this repo's own\n")
    w("#     ROADMAP uses every day -- U+25B6 (▶), U+25CB (○), U+25D0 (◐), U+26A0 (⚠) --\n")
    w("#     which a CJK-locale terminal renders two columns wide. Ambiguous width is\n")
    w("#     context-dependent BY DEFINITION, so any implementation that does not read the\n")
    w("#     locale has to pick a side; this one picks 1 and says so.\n")
    w("#   * Combining marks and zero-width characters are not subtracted. They do not\n")
    w("#     appear in step text; if they did, width would be OVER-counted, which is the\n")
    w("#     survivable direction.\n")
    w("def wide_ranges: [\n")
    w(",\n".join("  [%d,%d]" % (a, b) for a, b in rs))
    w("\n];\n")
    w("def cw: . as $c | if any(wide_ranges[]; .[0] <= $c and $c <= .[1]) then 2 else 1 end;\n")
    w("def dispwidth: [explode[] | cw] | add // 0;\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
