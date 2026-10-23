"""Mutation harness for `retention-drain.sh` — build a mutant, run the suite against it, report.

WHY THIS IS TRACKED. It is the only evidence behind the drain's mutation-coverage claims: which
fixture catches which removed mechanism.
A tool whose output is cited as
proof cannot live somewhere a reboot deletes.

MUTANTS ARE NAMED BY THE TEXT THEY REMOVE, never by a line number. A matrix keyed on integers is
one insertion away from mutating the wrong line while still reporting a kill — and the line
numbers in this file's own subject drift with every edit.

EVERY MUTANT MUST PROVE IT RAN. A mutant that never executed and a mutant that executed and was
killed look identical from an exit code alone, so `build()` refuses a needle that does not
resolve exactly once, and the runner flags a kill-rate high enough to mean a broken invocation
rather than a real kill.

A MUTANT MAY NEED SEVERAL EDITS TO BE FAITHFUL. A no-staging mutant that changed only the
dated branch and dropped the swap would leave the UNDATED branch writing into a staging directory
the same mutant then removed — so it would produce no segments and the undated fixture would die on
its own vacuity guard instead of on the property it exists to measure. A kill by collapsed
precondition is not evidence for the assertion it bypasses.

Usage:
    python3 scripts/mutate_retention_drain.py            # build all, run the suite against each
    python3 scripts/mutate_retention_drain.py M-noguard  # just one

`scripts/test_mutation_harness.py` asserts every needle still resolves and every mutant still
builds into runnable bash, so a production edit that strands a needle fails loudly instead of
producing a matrix of vacuous survivors.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "scripts" / "retention-drain.sh"
SUITE = "scripts/test_retention_drain.py"

# (name, what it breaks, [(needle, replacement), ...])
MUTANTS: list[tuple[str, str, list[tuple[str, str]]]] = [
    (
        "M-restore",
        "drain_restore's byte check",
        [(
            '        cmp -s "$stage/files/$rel" "$rel" || { echo "✗ restore: $rel differs after restore"; bad=1; continue; }\n',
            "",
        )],
    ),
    (
        "M-capture",
        "capture_preimage's byte check — the restore-side twin",
        [('        && cmp -s "$f" "$stage/files/$rel" || {\n', "        || {\n")],
    ),
    (
        "M-prop-dispatch",
        "the dispatch arm's return-code propagation (call site 2 of 2)",
        [(
            '      check_rollover "$AD/$(basename "$SUB" .md)-archive.md" "${3:-25}" || rc=$?\n',
            '      check_rollover "$AD/$(basename "$SUB" .md)-archive.md" "${3:-25}"\n',
        )],
    ),
    (
        "M-prop-qalog",
        "drain_qa_log's return-code propagation (call site 1 of 2)",
        [(
            '    check_rollover "$AD/$(basename "$mono" .md)-archive.md" 50 || rc=$?\n',
            '    check_rollover "$AD/$(basename "$mono" .md)-archive.md" 50\n',
        )],
    ),
    (
        "M-nostage",
        "the month split's staging ONLY — the swap is left in place, so this mutant throws its "
        "own output away. Kept as the DISCARDED shape: it 'kills' by making a fixture vacuous, "
        "which is the reading this harness exists to prevent, so it is here to be recognised.",
        [('    awk -v segdir="$stage" \'\n', '    mkdir -p "$segdir"; awk -v segdir="$segdir" \'\n')],
    ),
    (
        "M-nostage3",
        "the stage-then-swap retry safety on BOTH branches — every write target moved back to "
        "$segdir and the swap removed, i.e. the pre-staging shape, faithfully",
        [
            (
                '    awk -v segdir="$stage" \'\n',
                '    mkdir -p "$segdir" || { echo "✗ cannot create $segdir"; return 1; }\n'
                '    awk -v segdir="$segdir" \'\n',
            ),
            # The chunk branch stages into a scratch dir UNDER $stage and then renames each piece
            # to the next free suffix beside the segments already there (the previous
            # shape re-split from part-aa every time and overwrote same-named segments, losing
            # archived entries). Re-aimed with it, not around it: the three
            # needles below are where that branch decides WHERE to write, so moving them to
            # $segdir still produces the pre-staging shape this mutant exists to describe.
            (
                '    local newdir="$stage/.split" n_existing=0 k=0 target hi lo\n',
                '    mkdir -p "$segdir" || { echo "✗ cannot create $segdir"; return 1; }\n'
                '    local newdir="$segdir/.split" n_existing=0 k=0 target hi lo\n',
            ),
            (
                '    for s in "$stage"/part-*.md; do [ -f "$s" ] && n_existing=$((n_existing + 1)); done\n',
                '    for s in "$segdir"/part-*.md; do [ -f "$s" ] && n_existing=$((n_existing + 1)); done\n',
            ),
            (
                '      target="$stage/part-${alpha:hi:1}${alpha:lo:1}.md"\n',
                '      target="$segdir/part-${alpha:hi:1}${alpha:lo:1}.md"\n',
            ),
            ('    for s in "$stage"/*.md; do\n', '    for s in "$segdir"/*.md; do\n'),
            ('  } > "$stage/index.md" \\\n', '  } > "$segdir/index.md" \\\n'),
            (
                '  old=""\n'
                '  if [ -d "$segdir" ]; then\n'
                '    old="$stage.old"\n'
                '    mv "$segdir" "$old" \\\n'
                '      || { echo "✗ cannot move $segdir aside for the roll-over"; rm -rf "$stage"; rm -f "$newarchive"; return 1; }\n'
                "  fi\n"
                '  if ! mv "$stage" "$segdir"; then\n'
                '    echo "✗ cannot move the staged roll-over into $segdir"\n'
                '    [ -n "$old" ] && mv "$old" "$segdir"\n'
                '    rm -rf "$stage"; rm -f "$newarchive"; return 1\n'
                "  fi\n",
                '  old=""\n  rm -rf "$stage"\n',
            ),
        ],
    ),
    (
        "R-postswap",
        "the archive rewrite's staging — puts the rewrite back BELOW the swap, where "
        "a failure returns 1 with $segdir already "
        "replaced and the archive still holding every entry, so the retry doubles them",
        [
            (
                '  newarchive="$segdir.rollover-archive"\n'
                '  if [ -e "$newarchive" ] && [ ! -f "$newarchive" ]; then\n'
                '    echo "✗ $newarchive exists and is not a regular file — refusing to roll over $archive"\n'
                '    rm -rf "$stage"; return 1\n'
                "  fi\n"
                "  { printf '# %s — archive, rolled over into segments\\n\\n' \"$name\"\n"
                '    pointer_stub "$segdir/index.md" "see segment index"; } > "$newarchive" \\\n'
                '    || { echo "✗ cannot stage the rewritten $archive"; rm -rf "$stage"; rm -f "$newarchive"; return 1; }\n',
                "",
            ),
            (
                '  mv -f "$newarchive" "$archive" \\\n'
                '    || { echo "✗ cannot rewrite $archive"; rm -f "$newarchive"; return 1; }\n',
                "  { printf '# %s — archive, rolled over into segments\\n\\n' \"$name\"\n"
                '    pointer_stub "$segdir/index.md" "see segment index"; } > "$archive" \\\n'
                '    || { echo "✗ cannot rewrite $archive"; return 1; }\n',
            ),
        ],
    ),
    (
        "R-noseed",
        "the stage-seeding `cp -R` — the stage starts EMPTY, so a second roll-over silently "
        "drops every segment the first one wrote",
        [(
            '  if [ -d "$segdir" ]; then\n'
            "    # A second roll-over legitimately ADDS entries to a month an earlier one created, so the\n"
            "    # stage begins as a copy of what is already there — never empty. Seeding it wrong would\n"
            "    # trade duplicated content for lost content, which is the worse of the two.\n"
            '    cp -R "$segdir/." "$stage/" 2>/dev/null \\\n'
            '      || { echo "✗ cannot stage the existing segments of $segdir"; rm -rf "$stage"; return 1; }\n'
            "  fi\n",
            "",
        )],
    ),
    (
        "X-order",
        "the ORDER of the archive staging — moves it back below the swap while keeping `mv -f`, "
        "so a staging failure reports with $segdir already replaced. Kept separate from "
        "R-postswap because the fix had two halves and R-postswap only exercises the other one",
        [
            (
                '  newarchive="$segdir.rollover-archive"\n'
                '  if [ -e "$newarchive" ] && [ ! -f "$newarchive" ]; then\n'
                '    echo "✗ $newarchive exists and is not a regular file — refusing to roll over $archive"\n'
                '    rm -rf "$stage"; return 1\n'
                "  fi\n"
                "  { printf '# %s — archive, rolled over into segments\\n\\n' \"$name\"\n"
                '    pointer_stub "$segdir/index.md" "see segment index"; } > "$newarchive" \\\n'
                '    || { echo "✗ cannot stage the rewritten $archive"; rm -rf "$stage"; rm -f "$newarchive"; return 1; }\n',
                "",
            ),
            (
                '  preimage_note_absent "$segdir/index.md" "$segdir"/*.md\n',
                '  preimage_note_absent "$segdir/index.md" "$segdir"/*.md\n'
                '  newarchive="$segdir.rollover-archive"\n'
                '  if [ -e "$newarchive" ] && [ ! -f "$newarchive" ]; then\n'
                '    echo "✗ $newarchive exists and is not a regular file — refusing to roll over $archive"\n'
                "    return 1\n"
                "  fi\n"
                "  { printf '# %s — archive, rolled over into segments\\n\\n' \"$name\"\n"
                '    pointer_stub "$segdir/index.md" "see segment index"; } > "$newarchive" \\\n'
                '    || { echo "✗ cannot stage the rewritten $archive"; rm -f "$newarchive"; return 1; }\n',
            ),
        ],
    ),
    (
        "X-rmswap",
        "the move-aside swap — puts back `rm -rf \"$segdir\" && mv`, which deletes what it can "
        "and only then fails, permanently destroying previously archived segments",
        [(
            '  old=""\n'
            '  if [ -d "$segdir" ]; then\n'
            '    old="$stage.old"\n'
            '    mv "$segdir" "$old" \\\n'
            '      || { echo "✗ cannot move $segdir aside for the roll-over"; rm -rf "$stage"; rm -f "$newarchive"; return 1; }\n'
            "  fi\n"
            '  if ! mv "$stage" "$segdir"; then\n'
            '    echo "✗ cannot move the staged roll-over into $segdir"\n'
            '    [ -n "$old" ] && mv "$old" "$segdir"\n'
            '    rm -rf "$stage"; rm -f "$newarchive"; return 1\n'
            "  fi\n",
            '  old=""\n'
            '  rm -rf "$segdir" && mv "$stage" "$segdir" \\\n'
            '    || { echo "✗ cannot move the staged roll-over into $segdir"; rm -rf "$stage"; rm -f "$newarchive"; return 1; }\n',
        )],
    ),
    (
        "M-noguard",
        "the refusal when a non-directory sits at $segdir, which `rm -rf` would have deleted",
        [(
            '  if [ -e "$segdir" ] && [ ! -d "$segdir" ]; then\n'
            '    echo "✗ $segdir exists and is not a directory — refusing to roll over $archive"; return 1\n'
            "  fi\n",
            "",
        )],
    ),
]

MUTANTS_BY_NAME = {name: (breaks, edits) for name, breaks, edits in MUTANTS}


class StrandedNeedle(AssertionError):
    """A needle no longer resolves to exactly one place in the source.

    Raised rather than warned about. A stranded needle produces a mutant that is either
    byte-identical to the source (every fixture passes, reported as SURVIVED, read as a coverage
    hole that is not there) or mutated in more places than intended.
    """


def build(name: str, source: str | None = None) -> str:
    """Return the mutated source for `name`, or raise if any needle does not resolve exactly once."""
    if name not in MUTANTS_BY_NAME:
        raise KeyError(f"unknown mutant {name!r}; known: {', '.join(MUTANTS_BY_NAME)}")
    text = SRC.read_text(encoding="utf-8") if source is None else source
    _, edits = MUTANTS_BY_NAME[name]
    stranded = [(n, text.count(n)) for n, _ in edits if text.count(n) != 1]
    if stranded:
        detail = "; ".join(f"{count}x {needle!r}" for needle, count in stranded)
        raise StrandedNeedle(f"{name}: needle(s) did not resolve to exactly one place — {detail}")
    for needle, repl in edits:
        text = text.replace(needle, repl)
    return text


FAILED = re.compile(r"^FAILED (\S+)", re.M)


def _run_one(name: str, breaks: str, outdir: Path) -> tuple[str, str, str, list[str]]:
    path = outdir / f"{name}.sh"
    path.write_text(build(name), encoding="utf-8")

    source = SRC.read_text(encoding="utf-8")
    assert path.read_text(encoding="utf-8") != source, f"{name} is byte-identical to the source"
    syn = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
    if syn.returncode != 0:
        print(f"!! {name}: syntax error, mutant is not runnable\n{syn.stderr}")
        return name, breaks, "BROKEN", []

    # ABSOLUTE, because the suite resolves the override relative to nothing and a relative path
    # silently falls back to the tracked script — a whole matrix of false kills.
    assert path.is_absolute(), "PLC_DRAIN_IMPL must be absolute"
    run = subprocess.run(
        [sys.executable, "-m", "pytest", SUITE, "-q", "-p", "no:cacheprovider", "--no-header", "-rf"],
        cwd=REPO, env={**os.environ, "PLC_DRAIN_IMPL": str(path)},
        capture_output=True, text=True,
    )
    body = run.stdout + run.stderr
    killed = sorted({m.split("::")[-1] for m in FAILED.findall(body)})
    # Counted per OUTCOME rather than by matching one summary shape. `(\d+) failed, (\d+) passed`
    # does not match a tail carrying errors — `F failed, E errors, P passed` fell through to a
    # denominator of P, dropping the errored tests from both the kill list and the total.
    counts = {k: int(v) for v, k in re.findall(r"(\d+) (passed|failed|errors?|xfailed|xpassed)", body)}
    total = sum(v for k, v in counts.items() if k in ("passed", "failed", "xfailed", "xpassed"))
    errors = sum(v for k, v in counts.items() if k.startswith("error"))

    # pytest exits 0 (all passed) or 1 (tests failed). ANYTHING ELSE — collection error, no such
    # file, internal error, interrupt — means the suite did not run, and a run that executed
    # nothing produced no FAILED lines, which used to fall through to `SURVIVED (0/0)`: the exact
    # misreading `StrandedNeedle` exists to prevent, arriving from the runner instead of the
    # builder. A mutant with no verdict has to say so.
    if run.returncode not in (0, 1) or total == 0 or errors:
        detail = f"rc={run.returncode}, {total} tests, {errors} error(s)"
        return name, breaks, f"BROKEN ({detail} — the suite did not run cleanly)", killed

    if killed and len(killed) / total > 0.60:
        verdict = f"SUSPECT ({len(killed)}/{total} = >60%, the shape of a broken invocation)"
    elif killed:
        verdict = f"KILLED ({len(killed)}/{total})"
    else:
        verdict = f"SURVIVED (0/{total})"
    return name, breaks, verdict, killed


def main(argv: list[str]) -> int:
    wanted = argv[1:] or [name for name, _, _ in MUTANTS]
    outdir = Path(os.environ.get("PLC_MUTANT_DIR") or tempfile.mkdtemp(prefix="plc-mutants-"))
    outdir.mkdir(parents=True, exist_ok=True)
    print(f"# mutants in {outdir}\n")

    rows = []
    for name in wanted:
        breaks, _ = MUTANTS_BY_NAME[name]
        row = _run_one(name, breaks, outdir)
        rows.append(row)
        print(f"{row[0]:<16} {row[2]}")
        for k in row[3]:
            print(f"                 - {k}")

    print("\n\n## Mutation matrix — retention-drain.sh\n")
    print("| mutant | what it removes | verdict | fixtures that caught it |")
    print("|---|---|---|---|")
    for name, breaks, verdict, killed in rows:
        names = "<br>".join(k.replace("test_", "") for k in killed) or "—"
        print(f"| `{name}` | {breaks} | **{verdict}** | {names} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
