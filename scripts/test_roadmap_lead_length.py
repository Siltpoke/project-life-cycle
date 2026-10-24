"""The lead-sentence rule, and a falsifier that requires the check to go red.

**No CJK in this file, deliberately.** This project bans CJK in shipped files outside
`README*` / `CHANGELOG.md` / `GUIDE*`.

**The requirement, stated, because these tests exist to satisfy it exactly:**

    The format contract declares the lead-sentence-plus-detail rule, with a falsifier
    that puts a multi-hundred-character blob in a lead position and requires the check to go
    red.

`test_a_blob_in_lead_position_is_rejected` IS that falsifier.

**Why a ratchet and not a bound.** Measured on the real roadmap in display columns: most
name cells and leads already exceed 60. A rule that reddens most rows on the day it
lands is a rule somebody switches off. So each row is pinned at its current width and may only
shrink, while a row that is new — or renamed, which is the same as having been touched — must
meet the bound outright. The tests below pin BOTH halves, because a ratchet with only one of
them is either a wall of red or a no-op.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
GUARD = REPO / "scripts" / "invariants" / "roadmap-lead-length.sh"
GENERATOR = REPO / "scripts" / "gen-roadmap-lead-baseline.sh"
REAL_BASELINE = REPO / ".claude" / "roadmap-lead-baseline.tsv"

pytestmark = pytest.mark.skipif(
    not GUARD.is_file(), reason="guard absent")

SHORT_NAME = "**S1 short row**"
SHORT_WHAT = "A short lead. Then as much detail as anyone wants, and it is not capped: "
BLOB = "x" * 400


def roadmap(rows: list[tuple[str, str]]) -> str:
    head = ("# R\n\n## \U0001f6e3 Mainline\n\n| station | what | weight | eta |\n"
            "|---|---|---|---|\n")
    body = "".join("| %s | %s | w | e |\n" % (n, w) for n, w in rows)
    return head + body + "\n"


def write(tmp_path: Path, rows, baseline: str | None = None):
    rm = tmp_path / "ROADMAP.md"
    rm.write_text(roadmap(rows), encoding="utf-8")
    bl = tmp_path / "baseline.tsv"
    bl.write_text(baseline if baseline is not None else "# empty\n", encoding="utf-8")
    return rm, bl


def run(rm: Path, bl: Path, cols: str = "60") -> subprocess.CompletedProcess:
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
           "ROADMAP_PATH": str(rm), "ROADMAP_LEAD_BASELINE": str(bl),
           "MAX_LEAD_COLS": cols}
    return subprocess.run(["/bin/bash", str(GUARD)], cwd=REPO, env=env,
                          capture_output=True, text=True)


def gen(rm: Path) -> str:
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
           "ROADMAP_PATH": str(rm)}
    p = subprocess.run(["/bin/bash", str(GENERATOR)], cwd=REPO, env=env,
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return p.stdout


# ================================================================= the falsifier


def test_a_blob_in_lead_position_is_rejected(tmp_path: Path) -> None:
    """The exit criterion, word for word: a multi-hundred-character blob in a lead position must make
    the check go red. Nothing marks the end of a lead in this row, so the whole cell is the
    lead — which is the honest reading, not a loophole."""
    rm, bl = write(tmp_path, [(SHORT_NAME, BLOB)])
    p = run(rm, bl)
    assert p.returncode != 0, p.stdout
    assert "the lead of its `what` cell is 400 display columns" in p.stderr, p.stderr


def test_the_same_blob_is_accepted_once_a_lead_is_marked(tmp_path: Path) -> None:
    """The positive control, and it is the whole point of the rule. The detail is NOT capped —
    Capping is rejected, because the detail is load-bearing. Marking where the lead ends is
    what makes the same text legal."""
    rm, bl = write(tmp_path, [(SHORT_NAME, "A short lead. " + BLOB)])
    p = run(rm, bl)
    assert p.returncode == 0, p.stderr + p.stdout
    assert p.stdout.startswith("✓"), p.stdout


def test_a_long_name_is_rejected_too(tmp_path: Path) -> None:
    """The column whose job is "which row is this" is the one measured worst in practice.
    It gets the same bound."""
    rm, bl = write(tmp_path, [("**" + "y" * 200 + "**", SHORT_WHAT + "detail")])
    p = run(rm, bl)
    assert p.returncode != 0
    # 204, not 200: the two `**` pairs are part of the cell a reader sees.
    assert "name cell is 204 display columns" in p.stderr, p.stderr


# ================================================================= the ratchet, both halves


def test_a_pinned_row_may_stay_as_long_as_it_is(tmp_path: Path) -> None:
    rows = [(SHORT_NAME, BLOB)]
    rm, bl = write(tmp_path, rows)
    bl.write_text(gen(rm), encoding="utf-8")
    p = run(rm, bl)
    assert p.returncode == 0, p.stderr + p.stdout
    assert "1 pinned" in p.stdout, p.stdout


def test_a_pinned_row_may_not_grow(tmp_path: Path) -> None:
    """The half that makes the pin a ratchet instead of an exemption. Without it a pinned row
    could be made twice as bad and nothing would say so."""
    rm, bl = write(tmp_path, [(SHORT_NAME, BLOB)])
    bl.write_text(gen(rm), encoding="utf-8")
    rm.write_text(roadmap([(SHORT_NAME, BLOB + "z" * 50)]), encoding="utf-8")
    p = run(rm, bl)
    assert p.returncode != 0, p.stdout
    assert "grew from 400 to 450" in p.stderr, p.stderr


def test_a_pinned_row_may_shrink(tmp_path: Path) -> None:
    rm, bl = write(tmp_path, [(SHORT_NAME, BLOB)])
    bl.write_text(gen(rm), encoding="utf-8")
    rm.write_text(roadmap([(SHORT_NAME, "A short lead. " + BLOB)]), encoding="utf-8")
    p = run(rm, bl)
    assert p.returncode == 0, p.stderr + p.stdout


def test_renaming_a_row_drops_its_pin(tmp_path: Path) -> None:
    """The key is the name cell, and that is a property rather than an accident: renaming a row
    IS editing it, so it stops being grandfathered. Position would have been the obvious key and
    rots on the first reorder; the backlog id was measured instead of assumed and cannot serve —
    some rows carry none, and an id can appear twice."""
    rm, bl = write(tmp_path, [(SHORT_NAME, BLOB)])
    bl.write_text(gen(rm), encoding="utf-8")
    rm.write_text(roadmap([("**S1 renamed row**", BLOB)]), encoding="utf-8")
    p = run(rm, bl)
    assert p.returncode != 0, p.stdout
    assert "new or was renamed" in p.stderr, p.stderr


def test_a_pinned_rows_name_cannot_change_while_pinned(tmp_path: Path) -> None:
    """Why there is no name ratchet, asserted rather than left as an absence.

    A mutant disabling the name ratchet SURVIVED, and the mutant was right: the pin is keyed on
    the name cell, so any edit to the name yields a different key and the row lands on the
    unpinned branch, where the bound applies outright. The ratchet could never fire. This case
    pins that reasoning: change only the name, and the row is treated as unpinned.
    """
    rm, bl = write(tmp_path, [("**S1 short row**", "A short lead. " + BLOB)])
    bl.write_text(gen(rm), encoding="utf-8")

    # [1] A SHORT rename: the row must lose its pin even though nothing goes red. The
    #     assertion is on the MECHANISM -- the count line -- not on a failure, because a
    #     rename that happens to stay within the bound is legal and must still be re-checked.
    rm.write_text(roadmap([("**S1 renamed but still short**", "A short lead. " + BLOB)]),
                  encoding="utf-8")
    p = run(rm, bl)
    assert p.returncode == 0, p.stderr
    assert "1 pinned, 1 unpinned" in p.stdout, (
        "the renamed row kept its pin, so the key is not the name cell: " + p.stdout)

    # [2] A LONG rename: same mechanism, now with a consequence. It reports the unpinned
    #     reason and NOT a ratchet message -- the ratchet is unreachable and was deleted.
    rm.write_text(roadmap([("**" + "n" * 80 + "**", "A short lead. " + BLOB)]),
                  encoding="utf-8")
    p = run(rm, bl)
    assert p.returncode != 0, p.stdout
    assert "new or was renamed" in p.stderr, p.stderr
    assert "grew from" not in p.stderr, "the unreachable ratchet came back: " + p.stderr


# ================================================================= scope honesty


def test_an_empty_scan_says_so_instead_of_passing(tmp_path: Path) -> None:
    rm = tmp_path / "ROADMAP.md"
    rm.write_text("# R\n\nno table here\n", encoding="utf-8")
    bl = tmp_path / "baseline.tsv"
    bl.write_text("# empty\n", encoding="utf-8")
    p = run(rm, bl)
    assert p.returncode == 0
    assert p.stdout.startswith("⊘"), "an empty scope printed like a verified one"
    assert "0 rows checked" in p.stdout


def test_the_generator_and_the_guard_measure_with_one_ruler(tmp_path: Path) -> None:
    """They share `scripts/lib/roadmap-lead.sh`. If they ever measured separately, a baseline
    would be a comparison between two different rulers — the encoder-divergence class this repo
    has already paid for."""
    src = GUARD.read_text(encoding="utf-8") + GENERATOR.read_text(encoding="utf-8")
    assert src.count("roadmap_lead_rows") >= 2
    assert "roadmap-lead.sh" in GUARD.read_text(encoding="utf-8")


def _parse_pins(text: str) -> dict[str, tuple[int, int]]:
    out: dict[str, tuple[int, int]] = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        f = line.split("\t")
        if len(f) < 3 or not f[1].isdigit() or not f[2].isdigit():
            continue
        out[f[0]] = (int(f[1]), int(f[2]))
    return out


# `test_the_real_baseline_is_what_the_generator_produces` lived here, and it asserted BYTE-IDENTITY
# between the pinned baseline and a fresh generation. Phase documents cite it by name, so the
# name is retired here rather than silently reused. **Its contract was wrong for a ratchet, and the
# reason is measurable:** byte-identity is the sentence "every pin equals today's
# measurement", so a lead that legitimately SHRANK without being re-pinned went red, and the failure
# message said `regenerate it rather than editing it by hand` -- which re-pins, and is the exact
# instruction `generator-edges-declared.sh` now calls the laundering route. Two mechanisms telling a
# maintainer opposite things. The row below keeps the property that test was actually reaching for
# (nobody hand-writes a number nothing measured) and drops the one it got wrong (that a pin must
# equal today).
@pytest.mark.skipif(not REAL_BASELINE.is_file(), reason="baseline absent (fresh clone)")
def test_the_real_baseline_is_an_upper_bound_never_below_todays_measurement() -> None:
    """A pin is an UPPER BOUND, so the honest assertions are: the key sets match, each pinned name
    width equals today's (the key is a digest of the name cell, so it cannot differ while the key
    matches), and each pinned lead is `>=` today's measurement.

    Under this rule a lead that shrank without re-pinning is GREEN -- it is the direction the
    ratchet exists to allow -- a hand-edit BELOW the measurement is RED, and a lead that grew is
    RED. Those are the same three answers `roadmap-lead-length.sh` gives, so the two readers of this
    file stop disagreeing.
    """
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"}
    p = subprocess.run(["/bin/bash", str(GENERATOR)], cwd=REPO, env=env,
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    today = _parse_pins(p.stdout)
    pinned = _parse_pins(REAL_BASELINE.read_text(encoding="utf-8"))
    assert today, "the generator produced no parsable records, so this row would be vacuous"
    assert set(pinned) == set(today), (
        "the baseline's key set differs from today's: only in the baseline "
        f"{sorted(set(pinned) - set(today))!r}, only in today's output "
        f"{sorted(set(today) - set(pinned))!r} -- regenerate it, a key set can only change when a "
        "row is added, removed or renamed")
    below = {k: (pinned[k][1], today[k][1]) for k in pinned if pinned[k][1] < today[k][1]}
    assert not below, (
        "a pinned lead is BELOW today's measurement, so the pin claims a width nothing measured: "
        f"{below!r} (pinned, today). Either the row grew -- which roadmap-lead-length.sh reds -- or "
        "the pin was hand-edited downward.")
    namediff = {k: (pinned[k][0], today[k][0]) for k in pinned if pinned[k][0] != today[k][0]}
    assert not namediff, (
        "a pinned name width differs from today's while the key matches, which the key being a "
        f"digest of the name cell should make impossible: {namediff!r}")


@pytest.mark.skipif(not REAL_BASELINE.is_file(), reason="baseline absent (fresh clone)")
def test_the_baseline_covers_every_row_the_guard_reads() -> None:
    """A generator that dies MID-FILE still leaves a plausible-looking baseline.

    Measured, not imagined: `grep -o` exits 1 on a row carrying no backlog id — one row does —
    and under `set -o pipefail` that killed the generator partway through the table. The file looked
    complete. `test_the_real_baseline_is_what_the_generator_produces` cannot catch it either:
    a re-run truncates identically, and comparing a broken thing to itself agrees.

    The assertion is on the GUARD's own count of unpinned rows, not on a row counter written
    here. A second counter would be a second reader of the same grammar — the divergence class
    this repo keeps paying for — and it was tried: it disagreed with the shipped reader by one
    row (a nested table's header) and the disagreement was the test's fault, not the file's.
    A truncated baseline shows up as unpinned rows and nothing else has to be re-implemented
    to see it.
    """
    roadmap_md = REPO / "docs" / "ROADMAP.md"
    if not roadmap_md.is_file():
        pytest.skip("docs/ROADMAP.md absent (adopter checkout; docs/ is tracked here since p39)")
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"}
    p = subprocess.run(["/bin/bash", str(GUARD)], cwd=REPO, env=env,
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr + p.stdout
    assert "0 unpinned" in p.stdout, (
        "the baseline does not cover every row the guard reads: " + p.stdout)
    # And the scope is not empty, which would make the line above vacuous.
    assert "0 row" not in p.stdout, p.stdout


# ================================================== The guard must REPORT, in either locale

# `run()` above passes no LANG/LC_ALL, so every test before this point has exercised the guard in
# the C locale only -- which is exactly the failure to avoid: "the suite is green" meant "the suite
# has never run it in the shell a person actually has". These two rows run it in both.

UTF8_LOCALE = "en_US.UTF-8"


def _locale_available(name: str) -> bool:
    """`LC_ALL=xx_YY.NOPE` makes bash fall back to C SILENTLY, so a row parametrised over two
    locales can collapse to one and stay green -- which would make the locale half untested on
    any host that generates only C/C.UTF-8 (a slim Linux container, for instance) while the
    CHANGELOG says the red paths are asserted in both. Checked rather than assumed."""
    if name == "C":
        return True
    try:
        out = subprocess.run(["locale", "-a"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    have = {l.strip() for l in out.stdout.splitlines()}
    return name in have or name.replace("-", "") in have


def run_in_locale(rm: Path, bl: Path, locale: str, guard: Path | None = None,
                  cols: str = "60") -> subprocess.CompletedProcess:
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
           "ROADMAP_PATH": str(rm), "ROADMAP_LEAD_BASELINE": str(bl),
           "MAX_LEAD_COLS": cols,
           "LANG": locale, "LC_ALL": locale,
           # A copy of the guard outside scripts/invariants/ cannot derive the library from its
           # own location, so a mutant fixture is told where it is.
           "EAW_LIB_DIR": str(REPO / "scripts" / "lib")}
    return subprocess.run(["/bin/bash", str(guard or GUARD)], cwd=REPO, env=env,
                          capture_output=True, text=True)


@pytest.mark.parametrize("locale", ["C", UTF8_LOCALE])
def test_p171_a_real_violation_is_reported_in_either_locale(tmp_path: Path, locale: str) -> None:
    """MEASURED before the fix, on bash 3.2.57: with LANG=en_US.UTF-8 the guard read the `...`
    glued to `$pref` as part of the variable name, died under `set -u`, and -- because its EXIT
    trap ended with `rm` -- exited ZERO. The gate's own invocation shape then printed
    `ok invariant 'roadmap-lead-length' holds` for a roadmap that really did violate the ratchet.

    All THREE of its `bad` call sites had the shape -- the two unpinned-row paths and the ratchet
    path, which is every red path the guard has -- so in a
    UTF-8 shell it could not report ANY violation.
    """
    if not _locale_available(locale):
        pytest.skip(f"{locale} is not generated on this host, so this row would silently "
                    f"re-run the C case and report a green it did not earn")
    rm, bl = write(tmp_path, [(SHORT_NAME, BLOB)])
    bl.write_text(gen(rm), encoding="utf-8")
    rm.write_text(roadmap([(SHORT_NAME, BLOB + "z" * 50)]), encoding="utf-8")
    p = run_in_locale(rm, bl, locale)
    assert p.returncode == 1, (
        "expected the guard's own FAILED verdict (1), got %s: %s" % (p.returncode, p.stderr))
    assert "grew from 400 to 450" in p.stderr, p.stderr
    assert "unbound variable" not in p.stderr, p.stderr


@pytest.mark.parametrize("locale", ["C", UTF8_LOCALE])
def test_p171_the_unpinned_red_paths_report_in_either_locale(tmp_path: Path, locale: str) -> None:
    """The other two `$pref` sites. Asserted separately because the ratchet path and the two
    unpinned-row paths are reached by different inputs -- a fix to one line leaves
    the others exactly as they were, and only a test that reaches them would say so."""
    if not _locale_available(locale):
        pytest.skip(f"{locale} is not generated on this host")
    rm, bl = write(tmp_path, [(SHORT_NAME, BLOB)])
    p = run_in_locale(rm, bl, locale)
    assert p.returncode == 1, (
        "expected the guard's own FAILED verdict (1), got %s: %s" % (p.returncode, p.stderr))
    assert "new or was renamed" in p.stderr, p.stderr
    assert "unbound variable" not in p.stderr, p.stderr


def _this_bash_launders_a_fatal(tmp_path: Path) -> bool:
    """Does THIS bash hand back the EXIT trap's last command status when a `set -u` abort fires?

    MEASURED PER HOST, never inferred from a version number. The second failure is a bash 3.2
    behaviour: there, a trap entered from a fatal sees `$?` ALREADY 0, so a trap ending in `rm`
    exits ZERO out of a half-finished run. Measured on both platforms:

        bash 3.2 (macOS default)   no-fix -> exit 0    fixed -> exit 90
        bash 5.x                   no-fix -> exit 1    fixed -> exit 1

    So on bash 5 the laundering does not exist, the guard's `_ec=90` substitution deliberately does
    not fire (it only overrides a ZERO), and a row asserting 90 there asserts a macOS artefact
    rather than a property. Worse, it could not tell the fix from the defect at all -- both exit 1.
    This probe is what lets the rows below say which of the two claims they are making.
    """
    probe = tmp_path / "launder-probe.sh"
    probe.write_text(
        "set -euo pipefail\n"
        'tmp="$(mktemp)"\n'
        "trap 'rm -f \"$tmp\"' EXIT\n"
        ': "$DELIBERATELY_UNSET_FOR_THE_PROBE"\n'
        "echo GREEN\n", encoding="utf-8")
    r = subprocess.run(["/bin/bash", str(probe)], capture_output=True, text=True)
    assert "DELIBERATELY_UNSET_FOR_THE_PROBE" in r.stderr, (
        "the probe's own fatal did not fire, so it measured nothing: " + r.stderr)
    return r.returncode == 0


def test_p171_a_fatal_after_the_trap_is_not_reported_as_a_pass(tmp_path: Path) -> None:
    """The second half of this guard, which the first half hides. Bracing `${pref}` makes every row
    above green while leaving the laundering in place, so this row reaches it directly: an
    unrelated fatal is injected immediately after the trap is registered, and the guard must not
    exit 0. On bash 3.2.57 an EXIT trap entered from a `set -u` abort sees `$?` ALREADY 0, so a
    trap ending in `rm` hands back the status of `rm`.

    The marker is positive (`VERDICT_REACHED`), not an inference, and 90 is the code
    `.github/workflows/validate.yml` already uses for "the check did not reach its own summary".
    Same shape as the fix in close-gate.sh, whose header records that the obvious repair --
    ending the trap with `exit "$_ec"` -- does not work here, because `$_ec` is already 0.
    """
    src = GUARD.read_text(encoding="utf-8")
    assert "\ntrap " in src, "the guard no longer registers an EXIT trap; this row is stale"

    out_lines = []
    injected = False
    for line in src.splitlines(keepends=True):
        out_lines.append(line)
        if line.startswith("trap ") and line.rstrip().endswith("EXIT") and not injected:
            out_lines.append(': "$DELIBERATELY_UNSET_FOR_THE_CONTROL"\n')
            injected = True
    assert injected, "no `trap ... EXIT` line to inject after"

    mutant = tmp_path / "mutant-guard.sh"
    mutant.write_text("".join(out_lines), encoding="utf-8")

    # A clean roadmap: with no violation to report, a guard that merely ran to its verdict would
    # exit 0. So a non-zero here can only come from the injected fatal being caught.
    rm, bl = write(tmp_path, [(SHORT_NAME, SHORT_WHAT)])
    bl.write_text(gen(rm), encoding="utf-8")

    control = run_in_locale(rm, bl, UTF8_LOCALE)
    assert control.returncode == 0, (
        "the unmutated guard must be GREEN on this input, or the mutant proves nothing: "
        + control.stdout + control.stderr)

    p = run_in_locale(rm, bl, UTF8_LOCALE, guard=mutant)
    assert "DELIBERATELY_UNSET_FOR_THE_CONTROL" in p.stderr, (
        "the injected fatal did not fire, so this row measured nothing: " + p.stderr)
    assert p.returncode != 0, (
        "a guard that died before judging was reported as a PASS -- the exit status was laundered"
        " by the EXIT trap")
    if _this_bash_launders_a_fatal(tmp_path):
        # This bash CAN launder, so the marker is what makes the status non-zero and 90 is the
        # code it substitutes. Here the row is a real regression guard for the second half.
        assert p.returncode == 90, (
            "expected 90 (did not reach its own verdict), got %s" % p.returncode)
    else:
        # This bash lets the fatal's own status survive into the trap, so the substitution does not
        # fire by design -- it only overrides a ZERO. The row still asserts the property that
        # matters (a half-finished run is not a pass) but CANNOT distinguish the fix from the
        # defect here, and says so rather than implying coverage it does not have.
        assert p.returncode == 1, (
            "expected the fatal's own status (1) to survive, got %s" % p.returncode)


@pytest.mark.parametrize("site,anchor", [
    ("right after the trap is registered", "trap "),
    ("inside the row loop, where the original abort was", "  pin=\"$(awk -F'\\t'"),
])
def test_p171_a_fatal_is_not_laundered_wherever_it_happens(tmp_path: Path, site: str,
                                                           anchor: str) -> None:
    """A surviving mutant, and the finding is about the ORACLE.

    The fix's own regression test injects its fatal immediately after the `trap` line. That is
    upstream of `VERDICT_REACHED=1` wherever the marker sits -- so moving the marker from just
    before the verdicts to just before the `while` loop left every row green, while re-opening the
    laundering for a `set -u` abort INSIDE the loop. Which is exactly where the original abort was: the
    three `$pref` sites are loop-body lines.

    So the property is the marker's POSITION, and pinning it needs a second injection site that the
    loop reaches. This row is parametrised over both; the marker has to be downstream of each one.
    """
    src = GUARD.read_text(encoding="utf-8")
    assert src.count(anchor) >= 1, f"the {site} anchor is gone; this row is stale"

    out, injected = [], False
    for line in src.splitlines(keepends=True):
        out.append(line)
        if not injected and line.startswith(anchor):
            out.append(': "$DELIBERATELY_UNSET_FOR_THE_CONTROL"\n')
            injected = True
    assert injected, f"nothing to inject after for site: {site}"

    mutant = tmp_path / "mutant-guard.sh"
    mutant.write_text("".join(out), encoding="utf-8")

    rm, bl = write(tmp_path, [(SHORT_NAME, SHORT_WHAT)])
    bl.write_text(gen(rm), encoding="utf-8")

    control = run_in_locale(rm, bl, "C")
    assert control.returncode == 0, (
        "the unmutated guard must be GREEN on this input, or the mutant proves nothing: "
        + control.stdout + control.stderr)

    p = run_in_locale(rm, bl, "C", guard=mutant)
    assert "DELIBERATELY_UNSET_FOR_THE_CONTROL" in p.stderr, (
        f"the injected fatal did not fire at {site}, so this row measured nothing: " + p.stderr)
    assert p.returncode != 0, (
        f"a guard that died before judging at {site} was reported as a PASS -- the EXIT trap "
        f"laundered the status")
    if _this_bash_launders_a_fatal(tmp_path):
        assert p.returncode == 90, (
            f"a guard that died before judging at {site} was not reported as unfinished; got "
            f"{p.returncode} (0 means the EXIT trap laundered it into a pass)")
    else:
        assert p.returncode == 1, (
            f"on a bash that does not launder, the fatal's own status should survive at {site}; "
            f"got {p.returncode}")
