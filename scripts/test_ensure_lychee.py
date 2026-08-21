# scripts/test_ensure_lychee.py
import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ENSURE = REPO / "scripts" / "lib" / "ensure-lychee.sh"
PIN = REPO / "scripts" / "lib" / "lychee-pin.env"


def test_control_fails_loudly_when_lychee_is_unavailable(tmp_path):
    """Absence of the tool must be a FAILURE, not a quiet pass.

    A guard that degrades to a skip when its instrument is missing is precisely the
    defect such guards exist to close; it must not exist in this one.
    """
    control = REPO / "scripts" / "invariants" / "link-check-reaches-deep.sh"
    env = dict(
        os.environ,
        LYCHEE_PIN_FILE=str(REPO / "scripts" / "lib" / "lychee-pin.env"),
        LYCHEE_CACHE_DIR=str(tmp_path / "cache"),
        PATH="/nonexistent",          # no curl, no tar, no shasum -> install cannot succeed
    )
    proc = subprocess.run(
        ["/bin/bash", str(control)], capture_output=True, text=True, env=env
    )
    assert proc.returncode != 0, "a control that cannot run must not exit 0"
    out = proc.stdout + proc.stderr
    assert "FAIL" in out
    for forbidden in ("skip", "SKIP", "not applicable", "N/A"):
        assert forbidden not in out, f"the control degraded to {forbidden!r} instead of failing"


def test_pin_file_declares_every_required_key():
    text = PIN.read_text()
    for key in (
        "LYCHEE_VERSION",
        "LYCHEE_SHA256_x86_64_linux",
        "LYCHEE_SHA256_aarch64_darwin",
        "LYCHEE_ARGS_COMMON",
        "LYCHEE_TARGET",
        "LYCHEE_TARGET_SHALLOW",
    ):
        assert f"{key}=" in text, f"{key} missing from {PIN}"


def test_version_floor_is_documented_at_the_pin():
    """The pin carries the REASON it is load-bearing, at its definition.

    A pin whose comment says 'see the comment there' satisfies nothing; the
    regex/v0.20.0 fact must be present in the file itself.
    """
    text = PIN.read_text()
    assert "v0.20.0" in text
    assert "no-op" in text.lower() or "no op" in text.lower()


def test_corrupted_checksum_makes_the_installer_fail(tmp_path):
    """The one behaviour that must never degrade: an unverified binary is not used."""
    fake_pin = tmp_path / "pin.env"
    fake_pin.write_text(
        PIN.read_text().replace(
            "LYCHEE_SHA256_x86_64_linux=1f4e0ef7f6554a6ed33dd7ac144fb2e1bbed98598e7af973042fc5cd43951c9a",
            "LYCHEE_SHA256_x86_64_linux=" + "0" * 64,
        ).replace(
            "LYCHEE_SHA256_aarch64_darwin=c9d3740ea2d891854d37116c9fba840f37b6e7c89d330e7db84ac333631c4977",
            "LYCHEE_SHA256_aarch64_darwin=" + "0" * 64,
        )
    )
    env = dict(os.environ, LYCHEE_PIN_FILE=str(fake_pin), LYCHEE_CACHE_DIR=str(tmp_path / "cache"))
    proc = subprocess.run(["/bin/bash", str(ENSURE)], capture_output=True, text=True, env=env)
    assert proc.returncode != 0, "a checksum mismatch must not exit 0"
    assert "checksum" in proc.stderr.lower()
    cache = tmp_path / "cache"
    leftovers = list(cache.rglob("*")) if cache.exists() else []
    assert not any(p.is_file() for p in leftovers), (
        "the unverified download must be deleted, not left in the cache for a later run to reuse"
    )


# ---------------------------------------------------------------------------
# Nested work trees are not part of this tree's link surface
#
# The failure: a second agent session creates a git work tree,
# a different branch is checked out under `.claude/worktrees/<name>/`, and every
# `.md` in that checkout is reported as "an untracked file not on
# the declared-safe list". An unrelated branch cannot be pushed, though the invariant
# was green a moment earlier.
#
# It is a product defect, not bad luck: lychee's glob has no git-awareness, the
# declared-safe list is a list of individual FILES and cannot express "a second
# checkout", and a worktree per session is a common fix for concurrent
# sessions — so the guard broke on an ordinary workflow.
#
# These assertions are over the SCRIPT's derivation, not over a live worktree: a
# test may not create one in this repo (it would mutate the real .git), and one
# that shells out to a throwaway repo cannot run lychee against it in reasonable
# time. Named as the limit it is.
# ---------------------------------------------------------------------------

def test_the_worktree_exclusion_is_derived_and_never_a_literal():
    """The exclusion asks `git worktree list` at run time. A hardcoded
    `.claude/worktrees/` would be wrong twice: it misses a worktree placed
    anywhere else (`git worktree add ../elsewhere` is the common spelling), and
    it swallows a real directory of that name that is NOT a work tree."""
    src = (REPO / "scripts" / "invariants" / "link-check-reaches-deep.sh").read_text(
        encoding="utf-8"
    )
    code = "\n".join(
        l for l in src.split("\n") if not l.lstrip().startswith("#")
    )
    assert "git worktree list --porcelain" in code
    # The literal must not appear in the EXECUTABLE part — it is fine, and
    # deliberate, in the comment that explains what was measured.
    assert ".claude/worktrees" not in code


def test_the_exclusion_announces_itself_rather_than_filtering_silently():
    """A filter that removes rows without saying so is indistinguishable from a
    scan that never reached them — the exact shape this whole invariant exists to
    catch, which is why the drop is printed with a count and the worktree paths."""
    src = (REPO / "scripts" / "invariants" / "link-check-reaches-deep.sh").read_text(
        encoding="utf-8"
    )
    assert "nested work tree(s) excluded from the scan" in src
    assert "path(s) dropped" in src


def test_the_exclusion_only_narrows_the_extras_side():
    """It must be impossible for this to hide a MISSING tracked file. The expected
    set comes from `git ls-files` on THIS index, and a path inside another work
    tree is by construction not in it — so the filter is applied to the MATCHED
    set only, and the missing check reads the same file it always did."""
    src = (REPO / "scripts" / "invariants" / "link-check-reaches-deep.sh").read_text(
        encoding="utf-8"
    )
    # The filter writes ac1-matched.txt; ac1-expected.txt is never touched by it.
    filt = src.split("NESTED WORK TREES", 1)[1].split("expected_n=", 1)[0]
    assert "ac1-matched" in filt
    assert "ac1-expected" not in filt


def test_the_worktree_prefix_match_is_literal_not_a_regex():
    """The defect can arrive inside its own fix. A first draft that
    filters with `grep -v "^$wt_rel/"` treats a real directory name as a
    PATTERN: a work tree at `.claude/worktrees/a.b/` yields `^.claude/worktrees/a.b/`,
    whose `.` matches any character, so an unrelated `.claude/worktrees/axb/leak.md`
    was dropped with it — a file that should have been REPORTED, disappearing
    silently, which is the exact failure the exclusion exists to avoid.

    Two assertions, because either alone is weak: the executable span must not
    use a regex-anchored grep for this, AND the behaviour is demonstrated on the
    two tools directly so the claim rests on measurement rather than on reading."""
    import subprocess as _sp
    src = (REPO / "scripts" / "invariants" / "link-check-reaches-deep.sh").read_text(
        encoding="utf-8"
    )
    span = src.split("NESTED WORK TREES", 1)[1].split("expected_n=", 1)[0]
    code = "\n".join(l for l in span.split("\n") if not l.lstrip().startswith("#"))
    assert 'grep -v "^$wt_rel/"' not in code
    assert "index($0, p) != 1" in code

    rows = "a.b/keep.md\naxb/leak.md\nother.md\n"
    regex_out = _sp.run(["/usr/bin/grep", "-v", "^a.b/"], input=rows,
                        capture_output=True, text=True).stdout
    literal_out = _sp.run(["/usr/bin/awk", "-v", "p=a.b/", 'index($0,p)!=1'],
                          input=rows, capture_output=True, text=True).stdout
    # The regex form swallows the unrelated path; the literal form keeps it.
    assert "axb/leak.md" not in regex_out
    assert "axb/leak.md" in literal_out
    assert "a.b/keep.md" not in literal_out


def test_the_no_network_guard_names_the_evasion_it_declines_to_chase():
    """A known evasion is `builtins.__dict__["__imp" "ort__"](...)`, which
    defeats every arm. It is NOT chased — every lexical guard falls to
    string-splitting, and a fourth pattern would buy one spelling while implying
    a completeness the file cannot have. Declining is only honest if the decline
    is written where the next reader meets it, so that is what is asserted."""
    src = (REPO / "scripts" / "invariants" / "session-card-no-network.sh").read_text(
        encoding="utf-8"
    )
    assert "DECLINED ON PURPOSE" in src
    assert "string-splitting" in src
