"""`cut -c` cannot truncate this repository's text, and the rule is attached to the SHAPE.

`cut -c` counts characters in a BSD/UTF-8 shell and BYTES in GNU coreutils regardless of locale.
A generator that truncates multibyte text with it can, under a
C locale, rewrite a document as invalid UTF-8 (a dangling lead byte, exactly what a Linux CI
runner reports) or mangle a multibyte status glyph.

**Forcing a UTF-8 locale is not a fix.** Keeping `cut -c` under a forced UTF-8 locale
works on macOS and does nothing on Linux, and a guard that measures rather than assumes
finds no usable locale on such a runner and refuses to run, turning every generator into a
hard failure. No amount of locale selection makes a byte-based tool character-aware.

`scripts/utf8-text.sh` removes the delegation: it walks bytes under `LC_ALL=C` and counts
characters by UTF-8's own continuation-byte rule, so the answer never depends on any tool being
multibyte-aware. This file pins the helpers' behaviour, their locale-independence, and the rule
that keeps the next script from reintroducing the defect (a rule attached to a file does not
travel to the next file of the same shape).
"""

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HELPERS = ROOT / "scripts" / "utf8-text.sh"

# `cut -c` is the locale-sensitive form. `cut -b`, `cut -f` and `cut -d` are byte/field based and
# behave identically everywhere, so they are deliberately NOT matched — a net that fired on them
# would be noise, and noise is how a net gets switched off.
#
# `-c(?![a-zA-Z])` and NOT `-c\b`: the real call is `cut -c1-12`, and `c` followed by `1` is not a
# word boundary, so `\b` never fired on a single actual call site. The first version of this net
# used `\b` AND scanned raw source including comments — where `` `cut -c` `` is written with a
# trailing space — so its positive control passed while matching nothing but prose. Tightening the
# scan to code-only is what exposed it. A net proven only against the text that describes it has
# not been proven at all.
CUT_C = re.compile(r"\bcut\s+(?:-\w+\s+)*(?:-c(?![a-zA-Z])|--characters)")

# Named exemptions with their reasons, never a looser pattern. A pattern that grows until the
# count balances is the back door exemption tables exist to slam shut.
EXEMPT = {
    "ledger-run.sh": "operates on a git object id, which is ASCII hex — byte and character "
                     "counting agree there, so `cut -c1-12` is safe on any machine",
}

# CJK assembled from escapes, so this tracked source carries no literal CJK and stays
# ASCII-only.
ZH = b"\xe4\xb8\xad\xe6\x96\x87".decode("utf-8")   # two 3-byte characters


def _sh(call: str, env: dict | None = None) -> str:
    res = subprocess.run(
        ["/bin/bash", "-c", f'. "{HELPERS}"; {call}'], capture_output=True, env=env, check=False
    )
    assert res.returncode == 0, res.stderr.decode()
    return res.stdout.decode("utf-8")


def _code(src: str) -> str:
    """Source with whole-line comments removed.

    Scanning raw text for a token cannot tell USING it from TALKING ABOUT it — for example, a
    rule matched a helper's own usage line in a header comment.
    """
    return "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))


SOURCES_HELPERS = re.compile(r"^\s*(?:\.|source)\s+.*utf8-text\.sh", re.M)


# ------------------------------------------------------------------ the helpers themselves


@pytest.mark.parametrize("n,expected", [
    (0, ""), (1, "a"), (2, "ab"), (3, "ab" + ZH[0]), (4, "ab" + ZH),
    (5, "ab" + ZH + "c"), (6, "ab" + ZH + "cd"), (99, "ab" + ZH + "cd"),
])
def test_head_takes_characters_not_bytes(n, expected):
    """`ab<2 CJK>cd` is 6 characters and 10 bytes. A byte-based implementation returns `ab` plus a
    fragment at n=3 — the corruption, in one row."""
    assert _sh(f'plc_utf8_head "ab{ZH}cd" {n}') == expected


@pytest.mark.parametrize("n,expected", [
    (0, "ab" + ZH + "cd"), (2, ZH + "cd"), (3, ZH[1] + "cd"), (4, "cd"), (6, ""), (99, ""),
])
def test_tail_drops_characters_not_bytes(n, expected):
    assert _sh(f'plc_utf8_tail "ab{ZH}cd" {n}') == expected


def test_head_and_tail_partition_the_string():
    """The property both callers depend on: nothing lost, nothing duplicated, at every boundary
    including the ones inside a multibyte character."""
    s = "x" + ZH + "y" + ZH
    for n in range(0, 8):
        assert _sh(f'plc_utf8_head "{s}" {n}') + _sh(f'plc_utf8_tail "{s}" {n}') == s


def test_the_answer_does_not_depend_on_the_ambient_locale():
    """THE row. The defect was a truncation whose answer changed with the locale, and the first
    fix's mistake was pinning the locale instead of removing the dependency."""
    outs = {}
    for loc in ("C", "POSIX", "en_US.UTF-8"):
        outs[loc] = _sh(f'plc_utf8_head "ab{ZH}cd" 3',
                        env={"LC_ALL": loc, "LANG": loc, "PATH": "/usr/bin:/bin"})
    assert len(set(outs.values())) == 1, outs
    assert outs["C"] == "ab" + ZH[0], outs


def test_a_lead_byte_is_not_misread_as_ascii():
    """The regression that cost a debugging round: `printf '%d' "'$byte"` returns a SIGNED value,
    so 0xE4 arrives as -28 and a naive `< 128` test calls every lead byte ASCII. That produced
    wrong offsets in BOTH locales at once — which is why "it agrees across locales" is necessary
    and not sufficient. This row is the sufficiency half."""
    assert _sh(f'plc_utf8_head "{ZH}" 1') == ZH[0]
    assert len(_sh(f'plc_utf8_head "{ZH}" 1').encode()) == 3


def test_ascii_only_input_is_unaffected():
    """The negative control. Without it, an implementation that returned the whole string would
    pass several rows above."""
    assert _sh('plc_utf8_head "abcdef" 3') == "abc"
    assert _sh('plc_utf8_tail "abcdef" 3') == "def"


# ------------------------------------------------------------------ the rule, attached to a shape


def _scripts() -> list[Path]:
    return sorted(p for p in (ROOT / "scripts").glob("*.sh") if p.is_file())


def test_the_net_matches_something_at_all():
    """The positive control. "Every offender uses the helper" passes vacuously the moment the net
    stops matching — which is what happens if someone writes `cut --characters=1-105`. Confirm the
    net still finds the known remaining user before trusting any conclusion drawn from it."""
    hits = {p.name for p in _scripts() if CUT_C.search(_code(p.read_text(encoding="utf-8")))}
    assert hits, "the `cut -c` net matches nothing at all — it has stopped working"
    assert hits <= set(EXEMPT), (
        f"unexpected `cut -c` users: {sorted(hits - set(EXEMPT))}. Either switch them to "
        f"plc_utf8_head / plc_utf8_tail, or add them to EXEMPT with a written reason."
    )


def test_every_exemption_carries_a_reason():
    """An exemption table whose entries have no reason is a list of holes. Countable and justified,
    or not present."""
    for name, why in EXEMPT.items():
        assert (ROOT / "scripts" / name).exists(), f"EXEMPT names a script that is gone: {name}"
        assert len(why) > 40, f"{name}'s exemption reason is too thin to audit: {why!r}"


@pytest.mark.parametrize("script", ["backlog-toc.sh", "roadmap-batchmap-status.sh"])
def test_the_repaired_generators_source_the_helpers(script):
    src = (ROOT / "scripts" / script).read_text(encoding="utf-8")
    assert SOURCES_HELPERS.search(_code(src)), f"{script} does not source utf8-text.sh"
    assert not CUT_C.search(_code(src)), f"{script} still truncates with `cut -c`"


@pytest.mark.parametrize("script", ["backlog-toc.sh", "roadmap-batchmap-status.sh"])
def test_the_generators_produce_identical_bytes_under_C_and_UTF8(script, tmp_path):
    """Behaviour, not lexical presence. Sourcing the helper is worth nothing if the call sites
    still route through a byte-based tool, and an `in src` check would pass on that."""
    fixture = "docs/BACKLOG.md" if script == "backlog-toc.sh" else "docs/ROADMAP.md"
    original = ROOT / fixture
    if not original.exists():
        pytest.skip(f"{fixture} is absent in this checkout")

    outs = {}
    for loc in ("C", "en_US.UTF-8"):
        work = tmp_path / loc.replace(".", "_")
        (work / "docs").mkdir(parents=True)
        target = work / fixture
        target.write_bytes(original.read_bytes())
        args = ["/bin/bash", str(ROOT / "scripts" / script)]
        if script != "backlog-toc.sh":
            args.append(str(target))
        subprocess.run(
            args, cwd=str(work), capture_output=True, check=False,
            env={"LC_ALL": loc, "LANG": loc, "PATH": "/usr/bin:/bin:/usr/local/bin",
                 "PLC_CLOSURE_LOG": str(work / "no-such-ledger.tsv")},
        )
        outs[loc] = target.read_bytes()

    for loc, data in outs.items():
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as e:
            pytest.fail(f"{script} under LC_ALL={loc} produced invalid UTF-8: {e}")

    assert outs["C"] == outs["en_US.UTF-8"], (
        f"{script} produces different bytes under LC_ALL=C than under a UTF-8 locale"
    )


def test_no_tracked_script_carries_literal_CJK():
    """Tracked scripts carry no literal CJK probe string. Asserted
    as a test, so the next author learns it when the suite runs.

    `git grep -P` and not `/usr/bin/grep -P`: BSD grep has no `-P`, and a probe written with it
    answers "no CJK found" whatever the input — a meaningless answer. The control below is
    what makes a negative result mean anything.
    """
    def hits(pathspec: str) -> str:
        return subprocess.run(
            ["/usr/bin/git", "grep", "-l", "-P", r"[\x{4e00}-\x{9fff}]", "--", pathspec],
            cwd=str(ROOT), capture_output=True, text=True, check=False,
        ).stdout.strip()

    if not hits("README.zh-CN.md"):
        pytest.skip("the CJK net found nothing in README.zh-CN.md either — it is broken, not clean")
    assert not hits("scripts/"), f"literal CJK in tracked scripts: {hits('scripts/').split()}"
