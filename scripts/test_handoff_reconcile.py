"""Tests for scripts/handoff_reconcile.py.

Written BEFORE the module, one behaviour at a time.

Note on the stub: this file deliberately does NOT reuse `test_session_card.py`'s `_fake_run`.
That stub returns stdout only, which is exactly
the return-code failure mode: `git merge-base --is-ancestor` and `git cat-file -e` answer through their RETURN CODE
and print nothing, so a stdout-only stub cannot tell `behind` from `diverged` from `unavailable`,
and would pass while the real runner lied. The stub here returns (returncode, stdout, stderr).
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import handoff_reconcile as hr  # noqa: E402

SHA_A = "0123456789abcdef0123456789abcdef01234567"
SHA_B = "fedcba9876543210fedcba9876543210fedcba98"
SHA_M = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _fake_git(mapping: dict, *, default=None):
    """mapping: "args joined" -> (returncode, stdout). stderr defaults to ""."""
    def run_git(args, *, timeout=None):
        key = " ".join(args)
        if key in mapping:
            v = mapping[key]
            rc, out = v if isinstance(v, tuple) else (0, v)
            return hr.GitResult(rc, out, "")
        if default is not None:
            return hr.GitResult(*default)
        raise AssertionError(f"unexpected git {key}")
    return run_git


# ---------------------------------------------------------------- read_anchor

def test_read_anchor_finds_sha_in_wellformed_snapshot_line():
    block = (
        "# RESUME — snapshot\n"
        "> **Staleness anchor:** `origin/main` **%s** ·\n"
        "> snapshot: HEAD %s · main · 2026-01-02T03:04:05Z\n"
    ) % (SHA_B, SHA_A)
    a = hr.read_anchor(block)
    assert a is not None
    assert a.sha == SHA_A
    assert a.branch == "main"
    assert a.taken_at == "2026-01-02T03:04:05Z"


def test_read_anchor_returns_none_for_legacy_pr_only_resume():
    """AC12: a legacy RESUME has no snapshot line. That is the legacy case, not an error."""
    block = "## ⏳ CURRENT — 2026-01-17 — example work (#32201 open)\nnext: reconcile\n#32101 #32201\n"
    assert hr.read_anchor(block) is None


def test_read_anchor_reads_only_the_block_it_was_handed():
    """read_anchor must never select a block itself."""
    newest = "## ⏳ CURRENT — 2026-01-20\n> snapshot: HEAD %s · main · 2026-01-20T00:00:00Z\n" % SHA_A
    older = "## ⏳ CURRENT — 2026-01-10\n> snapshot: HEAD %s · main · 2026-01-10T00:00:00Z\n" % SHA_B
    assert hr.read_anchor(newest).sha == SHA_A
    assert hr.read_anchor(older).sha == SHA_B
    # handed only the newest block, the older sha must not leak in
    assert hr.read_anchor(newest).sha != SHA_B


def test_read_anchor_has_no_pr_number_fallback():
    """POSITIVE CONTROL. Mutating read_anchor to fall back to max(#N) must turn this red."""
    block = "## ⏳ CURRENT — 2026-01-20 — no snapshot line here (#99901)\n"
    a = hr.read_anchor(block)
    assert a is None, "read_anchor fell back to a PR number; that path is retired"


# ----------------------------------------------------------------- reconcile

def _anchor(sha=SHA_A):
    return hr.Anchor(sha=sha, branch="main", taken_at="2026-01-02T03:04:05Z")


def _row(rec, check):
    [r] = [r for r in rec.rows if r.check == check]
    return r


_IN_GIT = {"rev-parse --git-dir": (0, ".git")}


def test_unchanged_when_both_sides_are_the_same_object():
    run = _fake_git({
        **_IN_GIT,
        "rev-parse --verify --quiet %s^{commit}" % SHA_A: (0, SHA_A),
        "rev-parse --verify --quiet HEAD^{commit}": (0, SHA_A),
        "rev-parse --verify --quiet origin/main^{commit}": (0, SHA_A),
    })
    rec = hr.reconcile(_anchor(), run)
    assert _row(rec, "checkout").outcome == "unchanged"
    assert _row(rec, "upstream").outcome == "unchanged"
    assert rec.upstream_advance == 0


def test_checkout_behind_when_the_tree_lags_the_anchor():
    """The measured case: anchor == origin/main, working tree behind.

    The outcome word describes THE ROW'S OWN SUBJECT. This row is `checkout`, so `behind`
    means the checkout is behind — which is what AC3 requires the card to say.
    """
    run = _fake_git({
        **_IN_GIT,
        "rev-parse --verify --quiet %s^{commit}" % SHA_A: (0, SHA_A),
        "rev-parse --verify --quiet HEAD^{commit}": (0, SHA_B),
        "rev-parse --verify --quiet origin/main^{commit}": (0, SHA_A),
        "merge-base %s %s" % (SHA_A, SHA_B): (0, SHA_B),
        "rev-list --count %s..%s" % (SHA_B, SHA_B): (0, "0"),
        "rev-list --count %s..%s" % (SHA_B, SHA_A): (0, "4"),
    })
    rec = hr.reconcile(_anchor(), run)
    co = _row(rec, "checkout")
    assert co.outcome == "behind", co
    assert co.anchor_only == 4                # 4 commits the anchor has that the tree lacks
    assert _row(rec, "upstream").outcome == "unchanged"
    assert rec.upstream_advance == 0


def test_upstream_ahead_when_origin_moved_past_the_anchor():
    run = _fake_git({
        **_IN_GIT,
        "rev-parse --verify --quiet %s^{commit}" % SHA_A: (0, SHA_A),
        "rev-parse --verify --quiet HEAD^{commit}": (0, SHA_A),
        "rev-parse --verify --quiet origin/main^{commit}": (0, SHA_B),
        "merge-base %s %s" % (SHA_A, SHA_B): (0, SHA_A),
        "rev-list --count %s..%s" % (SHA_A, SHA_B): (0, "4"),
        "rev-list --count %s..%s" % (SHA_A, SHA_A): (0, "0"),
    })
    rec = hr.reconcile(_anchor(), run)
    up = _row(rec, "upstream")
    assert up.outcome == "ahead"             # origin/main moved ahead of the anchor...
    assert up.subject_advance == 4
    assert rec.upstream_advance == 4         # ...so the SAVE is behind, which the tier says


def test_diverged_reports_both_counts():
    """The NORMAL case here — a squash-orphaned feature-branch anchor."""
    run = _fake_git({
        **_IN_GIT,
        "rev-parse --verify --quiet %s^{commit}" % SHA_A: (0, SHA_A),
        "rev-parse --verify --quiet HEAD^{commit}": (0, SHA_A),
        "rev-parse --verify --quiet origin/main^{commit}": (0, SHA_B),
        "merge-base %s %s" % (SHA_A, SHA_B): (0, SHA_M),
        "rev-list --count %s..%s" % (SHA_M, SHA_B): (0, "7"),
        "rev-list --count %s..%s" % (SHA_M, SHA_A): (0, "3"),
    })
    rec = hr.reconcile(_anchor(), run)
    up = _row(rec, "upstream")
    assert up.outcome == "diverged"
    assert (up.subject_advance, up.anchor_only) == (7, 3)
    assert rec.upstream_advance == 7, "the tier keys on upstream_advance even when diverged"


def test_unresolvable_saved_sha_is_unavailable_with_a_cause():
    """Never fall back to the PR path, never report `unchanged`."""
    run = _fake_git({
        **_IN_GIT,
        "rev-parse --verify --quiet %s^{commit}" % SHA_A: (1, ""),
        "rev-parse --verify --quiet HEAD^{commit}": (0, SHA_B),
        "rev-parse --verify --quiet origin/main^{commit}": (0, SHA_B),
    })
    rec = hr.reconcile(_anchor(), run)
    for check in ("checkout", "upstream"):
        r = _row(rec, check)
        assert r.outcome == "unavailable"
        assert SHA_A[:12] in r.cause and "not present" in r.cause
    assert rec.upstream_advance is None


def test_missing_origin_ref_keeps_the_checkout_row():
    """Contingency 2: no remote-tracking ref -> that row unavailable, the other still reported."""
    run = _fake_git({
        **_IN_GIT,
        "rev-parse --verify --quiet %s^{commit}" % SHA_A: (0, SHA_A),
        "rev-parse --verify --quiet HEAD^{commit}": (0, SHA_A),
        "rev-parse --verify --quiet origin/main^{commit}": (1, ""),
        "symbolic-ref --quiet --short refs/remotes/origin/HEAD": (1, ""),
    })
    rec = hr.reconcile(_anchor(), run)
    assert _row(rec, "checkout").outcome == "unchanged"
    up = _row(rec, "upstream")
    assert up.outcome == "unavailable"
    assert up.cause == "no remote-tracking ref"


def test_no_git_at_all_emits_no_rows():
    """Contingency 3: the /handoff `no-git` path wins. NOT rows full of `unavailable`."""
    run = _fake_git({"rev-parse --git-dir": (128, "")})
    rec = hr.reconcile(_anchor(), run)
    assert rec.rows == []
    assert rec.no_git is True


def test_remote_row_is_not_attempted_unless_refresh():
    run = _fake_git({
        **_IN_GIT,
        "rev-parse --verify --quiet %s^{commit}" % SHA_A: (0, SHA_A),
        "rev-parse --verify --quiet HEAD^{commit}": (0, SHA_A),
        "rev-parse --verify --quiet origin/main^{commit}": (0, SHA_A),
    })
    rec = hr.reconcile(_anchor(), run)
    rem = _row(rec, "remote")
    assert rem.outcome == "not-attempted"
    assert "--refresh" in rem.cause
    # not-attempted is NOT unverified, or every default run exits non-zero
    assert rec.unverified == []
    assert rec.exit_code == 0


def test_every_tier_classify_can_return_is_in_the_declared_vocabulary():
    """The first version of this test was VACUOUS — it asserted a constant against a
    literal copy of itself.

    `TIERS` had no production reader; `classify_tier` returns string literals. So
    `assert hr.TIERS == {...}` compared the implementation to itself, and adding
    `return "unknown"` to `classify_tier` would have left every row green. Found by the
    review. This version drives the function over its whole input grid
    and asserts the OUTPUTS, which is the only form that can fail.
    """
    seen = set()
    for has_handoff in (True, False):
        for upstream_advance in (None, 0, 1, 7):
            for has_code in (None, True, False):
                seen.add(hr.classify_tier(upstream_advance=upstream_advance,
                                          has_code=has_code, has_handoff=has_handoff))
    assert seen <= hr.TIERS, seen - hr.TIERS
    assert "unknown" not in {s.lower() for s in seen}
    # and every declared tier is reachable — a vocabulary with a dead word is a vocabulary
    # whose guard has nothing to say about that word
    assert seen == hr.TIERS, hr.TIERS - seen


def test_tier_keys_on_upstream_advance_for_every_outcome():
    assert hr.classify_tier(upstream_advance=0, has_code=False) == "fresh"
    assert hr.classify_tier(upstream_advance=4, has_code=False) == "doc-behind"
    assert hr.classify_tier(upstream_advance=4, has_code=True) == "code-behind"
    assert hr.classify_tier(upstream_advance=None, has_code=False) == "unverified"
    assert hr.classify_tier(upstream_advance=0, has_code=False, has_handoff=False) == "no-handoff"


# ------------------------------------------- positive control: a REAL git repo, not the stub

def _real_repo(tmp_path):
    """A throwaway repo. The stub cannot catch that failure mode, because the defect IS the stub's shape."""
    import subprocess as sp

    def g(*args, **kw):
        return sp.run(["git", *args], cwd=tmp_path, capture_output=True, text=True, **kw)

    g("init", "-q", "-b", "main")
    g("config", "user.email", "t@example.invalid")
    g("config", "user.name", "t")
    (tmp_path / "a.md").write_text("one\n")
    g("add", "-A")
    g("commit", "-q", "-m", "docs: one")
    first = g("rev-parse", "HEAD").stdout.strip()
    (tmp_path / "b.py").write_text("x = 1\n")
    g("add", "-A")
    g("commit", "-q", "-m", "feat: two")
    second = g("rev-parse", "HEAD").stdout.strip()
    return first, second


def _real_runner(tmp_path):
    import subprocess as sp
    env = dict(**{k: v for k, v in hr.GIT_ENV_HARDENING.items()})
    import os as _os
    full = dict(_os.environ); full.update(env)

    def run_git(args, *, timeout=None):
        p = sp.run(["git", *args], cwd=tmp_path, capture_output=True, text=True,
                   timeout=timeout, env=full)
        return hr.GitResult(p.returncode, p.stdout, p.stderr)
    return run_git


def test_real_repo_unresolvable_sha_is_unavailable_not_unchanged(tmp_path):
    """POSITIVE CONTROL for the return-code failure mode.

    A stdout-only runner returns "" for a failed `rev-parse --verify --quiet`, and a module built
    on it would compare "" to "" and report `unchanged`. Against a real repo that mistake is
    visible. Reverting `run_git` to return only stdout must turn this test red.
    """
    _real_repo(tmp_path)
    run = _real_runner(tmp_path)
    absent = "dead" * 10  # 40 hex chars, no such object
    rec = hr.reconcile(hr.Anchor(sha=absent, branch="main", taken_at=None), run)
    co = _row(rec, "checkout")
    assert co.outcome == "unavailable", co
    assert "not present" in co.cause
    assert co.outcome != "unchanged", "a stdout-only runner would have said unchanged here"
    assert rec.exit_code == 4
    assert rec.upstream_advance is None


def test_real_repo_checkout_behind_is_counted(tmp_path):
    """The measured shape, against real git: the anchor is newer than the checked-out tree."""
    first, second = _real_repo(tmp_path)
    run = _real_runner(tmp_path)
    import subprocess as sp
    sp.run(["git", "checkout", "-q", first], cwd=tmp_path, capture_output=True, text=True)
    rec = hr.reconcile(hr.Anchor(sha=second, branch="main", taken_at=None), run)
    co = _row(rec, "checkout")
    assert co.outcome == "behind", co
    assert co.anchor_only == 1
    # no origin remote in this fixture -> that row is unavailable WITH a cause, and the
    # checkout row above still survives (contingency 2, proven against real git)
    assert _row(rec, "upstream").cause == "no remote-tracking ref"
    assert rec.exit_code == 4


def test_real_repo_default_path_makes_no_network_call(tmp_path):
    """AC7 against real git: a bogus origin URL must not be contacted on the default path."""
    _real_repo(tmp_path)
    import subprocess as sp
    sp.run(["git", "remote", "add", "origin", "https://127.0.0.1:1/nope.git"],
           cwd=tmp_path, capture_output=True, text=True)
    run = _real_runner(tmp_path)
    head = sp.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True,
                  text=True).stdout.strip()
    rec = hr.reconcile(hr.Anchor(sha=head, branch="main", taken_at=None), run)
    assert _row(rec, "checkout").outcome == "unchanged"
    assert _row(rec, "remote").outcome == "not-attempted"
    assert rec.exit_code == 4  # upstream is unavailable: the ref was never fetched


# ------------------------------------------------------- files_changed

def test_row_carries_its_merge_base_so_the_range_is_reusable():
    run = _fake_git({
        **_IN_GIT,
        "rev-parse --verify --quiet %s^{commit}" % SHA_A: (0, SHA_A),
        "rev-parse --verify --quiet HEAD^{commit}": (0, SHA_A),
        "rev-parse --verify --quiet origin/main^{commit}": (0, SHA_B),
        "merge-base %s %s" % (SHA_A, SHA_B): (0, SHA_M),
        "rev-list --count %s..%s" % (SHA_M, SHA_B): (0, "7"),
        "rev-list --count %s..%s" % (SHA_M, SHA_A): (0, "3"),
    })
    rec = hr.reconcile(_anchor(), run)
    up = _row(rec, "upstream")
    assert up.merge_base == SHA_M
    assert up.subject_sha == SHA_B
    assert rec.upstream_range == (SHA_M, SHA_B)


def test_upstream_range_is_none_when_there_is_nothing_to_compare():
    run = _fake_git({
        **_IN_GIT,
        "rev-parse --verify --quiet %s^{commit}" % SHA_A: (0, SHA_A),
        "rev-parse --verify --quiet HEAD^{commit}": (0, SHA_A),
        "rev-parse --verify --quiet origin/main^{commit}": (1, ""),
        "symbolic-ref --quiet --short refs/remotes/origin/HEAD": (1, ""),
    })
    assert hr.reconcile(_anchor(), run).upstream_range is None


def test_files_changed_lists_the_range_and_degrades_to_none_not_empty():
    """An empty list and "could not look" must not be the same value.

    `[]` would read as "the range touched no files", which is a verdict. A failed
    lookup has no verdict, and `classify_tier` must not be handed one.
    """
    ok = _fake_git({"diff --name-only %s..%s" % (SHA_M, SHA_B): (0, "docs/a.md\nscripts/b.py\n")})
    assert hr.files_changed(ok, (SHA_M, SHA_B)) == ["docs/a.md", "scripts/b.py"]

    empty = _fake_git({"diff --name-only %s..%s" % (SHA_M, SHA_B): (0, "")})
    assert hr.files_changed(empty, (SHA_M, SHA_B)) == []

    broken = _fake_git({"diff --name-only %s..%s" % (SHA_M, SHA_B): (128, "")})
    assert hr.files_changed(broken, (SHA_M, SHA_B)) is None

    assert hr.files_changed(ok, None) is None


def test_tier_is_unverified_when_the_code_question_could_not_be_answered():
    """`has_code=None` is not `has_code=False`. Guessing "docs only" would be a verdict."""
    assert hr.classify_tier(upstream_advance=4, has_code=None) == "unverified"
    assert hr.classify_tier(upstream_advance=0, has_code=None) == "fresh", \
        "with origin unmoved the code question does not arise, so it cannot block the tier"


# ------------------------------------------------------------ --refresh

_LSR = "ls-remote --heads origin refs/heads/main"


def _refresh_fixture(extra):
    return _fake_git({
        **_IN_GIT,
        "rev-parse --verify --quiet %s^{commit}" % SHA_A: (0, SHA_A),
        "rev-parse --verify --quiet HEAD^{commit}": (0, SHA_A),
        "rev-parse --verify --quiet origin/main^{commit}": (0, SHA_A),
        **extra,
    })


def test_refresh_reports_unchanged_when_the_real_remote_matches_the_local_ref():
    run = _refresh_fixture({_LSR: (0, "%s\trefs/heads/main\n" % SHA_A)})
    rec = hr.reconcile(_anchor(), run, refresh=True)
    rem = _row(rec, "remote")
    assert rem.outcome == "unchanged"
    assert rec.exit_code == 0


def test_refresh_reports_differs_not_a_direction_it_cannot_prove():
    """The remote row compares the REAL remote against the local `origin/main` ref.

    When the remote tip is not an object in this repository, we know the two differ and we do
    NOT know the direction -- establishing it would mean fetching objects, which the offline contract forbids on
    every path. `differs` is used rather than borrowing `ahead`, because `ahead` would claim a
    direction the mechanism cannot establish. The five-word vocabulary AC2 fixes is for the two
    ANCHOR rows; this row is a different pair and says so.
    """
    run = _refresh_fixture({_LSR: (0, "%s\trefs/heads/main\n" % SHA_B)})
    rec = hr.reconcile(_anchor(), run, refresh=True)
    rem = _row(rec, "remote")
    assert rem.outcome == "differs"
    assert rem.outcome not in ("ahead", "behind"), "direction was not established"
    assert SHA_A[:12] in rem.cause and SHA_B[:12] in rem.cause
    # it is a real finding, not an inconclusive check -- the run still exits 0
    assert rec.exit_code == 0


def test_refresh_failure_is_unverified_and_quotes_the_exit_status():
    """Contingency 4: the offline rows are unaffected and the command does not fail as a whole."""
    run = _refresh_fixture({_LSR: (128, "")})
    rec = hr.reconcile(_anchor(), run, refresh=True)
    rem = _row(rec, "remote")
    assert rem.outcome == "unavailable"
    assert "128" in rem.cause
    assert _row(rec, "checkout").outcome == "unchanged"   # offline rows unaffected
    assert _row(rec, "upstream").outcome == "unchanged"
    assert rec.exit_code == 4      # attempted and could not conclude


def test_refresh_timeout_is_unverified_and_says_so():
    """A routable-but-silent host must not hang the card."""
    run = _refresh_fixture({_LSR: (124, "")})
    rec = hr.reconcile(_anchor(), run, refresh=True)
    rem = _row(rec, "remote")
    assert rem.outcome == "unavailable"
    assert "124" in rem.cause


def test_refresh_with_no_matching_remote_branch_is_unverified():
    run = _refresh_fixture({_LSR: (0, "")})
    rec = hr.reconcile(_anchor(), run, refresh=True)
    assert _row(rec, "remote").outcome == "unavailable"
    assert "refs/heads/main" in _row(rec, "remote").cause


def test_refresh_mutates_no_ref_and_fetches_no_object():
    """AC9, as a check on the COMMAND SET rather than a promise in prose.

    Every git command the refresh path issues is recorded, and the assertion is that none of them
    is a writing or object-fetching verb. `ls-remote` reads refs over the wire and writes nothing.
    """
    issued = []

    def run_git(args, *, timeout=None):
        issued.append(list(args))
        key = " ".join(args)
        table = {
            **_IN_GIT,
            "rev-parse --verify --quiet %s^{commit}" % SHA_A: (0, SHA_A),
            "rev-parse --verify --quiet HEAD^{commit}": (0, SHA_A),
            "rev-parse --verify --quiet origin/main^{commit}": (0, SHA_A),
            _LSR: (0, "%s\trefs/heads/main\n" % SHA_A),
        }
        rc, out = table[key] if isinstance(table[key], tuple) else (0, table[key])
        return hr.GitResult(rc, out, "")

    hr.reconcile(_anchor(), run_git, refresh=True)
    verbs = {a[0] for a in issued}
    assert verbs <= {"rev-parse", "merge-base", "rev-list", "diff", "ls-remote", "cat-file"}, verbs
    for bad in ("fetch", "pull", "clone", "update-ref", "remote", "push", "checkout", "reset"):
        assert bad not in verbs, bad
    assert ["ls-remote", "--heads", "origin", "refs/heads/main"] in issued
    # exactly one wire call
    assert sum(1 for a in issued if a[0] == "ls-remote") == 1


def test_the_default_path_issues_no_ls_remote_at_all():
    issued = []

    def run_git(args, *, timeout=None):
        issued.append(list(args))
        key = " ".join(args)
        table = {
            **_IN_GIT,
            "rev-parse --verify --quiet %s^{commit}" % SHA_A: (0, SHA_A),
            "rev-parse --verify --quiet HEAD^{commit}": (0, SHA_A),
            "rev-parse --verify --quiet origin/main^{commit}": (0, SHA_A),
        }
        rc, out = table[key] if isinstance(table[key], tuple) else (0, table[key])
        return hr.GitResult(rc, out, "")

    hr.reconcile(_anchor(), run_git)
    assert not any(a[0] == "ls-remote" for a in issued), issued


# --------------------------------------------- the offline row says HOW stale it may be

def test_the_offline_row_reports_the_age_of_the_last_fetch(tmp_path):
    """A mandatory row that readers learn to skip is decoration.

    `origin/main` is only as current as the last fetch, so the row carries that date. No new git
    call: the git dir is already known from the `rev-parse --git-dir` the reconciliation runs
    first, and `FETCH_HEAD`'s mtime is a file read.
    """
    import os
    import time
    gd = tmp_path / ".git"
    gd.mkdir()
    fh = gd / "FETCH_HEAD"
    fh.write_text("x\n")
    old = time.time() - 3 * 86400
    os.utime(fh, (old, old))

    run = _fake_git({
        "rev-parse --git-dir": (0, str(gd)),
        "rev-parse --verify --quiet %s^{commit}" % SHA_A: (0, SHA_A),
        "rev-parse --verify --quiet HEAD^{commit}": (0, SHA_A),
        "rev-parse --verify --quiet origin/main^{commit}": (0, SHA_A),
    })
    rem = _row(hr.reconcile(_anchor(), run), "remote")
    assert rem.outcome == "not-attempted"
    assert "--refresh" in rem.cause
    assert "3d" in rem.cause, rem.cause


def test_the_offline_row_says_never_when_there_is_no_fetch_head(tmp_path):
    """A missing FETCH_HEAD is not age zero. 'never fetched' is the stronger warning of the two."""
    gd = tmp_path / ".git"
    gd.mkdir()
    run = _fake_git({
        "rev-parse --git-dir": (0, str(gd)),
        "rev-parse --verify --quiet %s^{commit}" % SHA_A: (0, SHA_A),
        "rev-parse --verify --quiet HEAD^{commit}": (0, SHA_A),
        "rev-parse --verify --quiet origin/main^{commit}": (0, SHA_A),
    })
    rem = _row(hr.reconcile(_anchor(), run), "remote")
    assert "never fetched" in rem.cause, rem.cause
    assert "0d" not in rem.cause


# ------------------------------------------------- the CLI /handoff calls

def _stamp_fixture(**extra):
    return _fake_git({
        **_IN_GIT,
        "rev-parse HEAD": (0, SHA_A),
        "rev-parse --abbrev-ref HEAD": (0, "feat/x"),
        "rev-parse --verify --quiet %s^{commit}" % SHA_A: (0, SHA_A),
        "rev-parse --verify --quiet HEAD^{commit}": (0, SHA_A),
        "rev-parse --verify --quiet origin/main^{commit}": (0, SHA_B),
        "merge-base %s %s" % (SHA_A, SHA_B): (0, SHA_A),
        "rev-list --count %s..%s" % (SHA_A, SHA_B): (0, "4"),
        "rev-list --count %s..%s" % (SHA_A, SHA_A): (0, "0"),
        **extra,
    })


def test_the_cli_output_round_trips_through_read_anchor(capsys):
    """The strongest check available here: the WRITER's line must be readable by the READER.

    `/handoff` writes the snapshot line and `/catchup` parses it. Before this contract existed those two halves
    were connected by nothing at all — the line was written and never read — so a format drift
    on either side was undetectable. Pinning them to each other is what makes it one contract
    instead of two conventions.
    """
    hr.main([], run_git=_stamp_fixture())
    out = capsys.readouterr().out
    back = hr.read_anchor(out)
    assert back is not None, out
    assert back.sha == SHA_A
    assert back.branch == "feat/x"
    assert back.taken_at  # a timestamp was stamped


def test_the_cli_reports_that_the_anchor_it_is_about_to_write_is_already_behind(capsys):
    """AC11. Writing a stamp while the upstream has already moved is the normal case here."""
    rc = hr.main([], run_git=_stamp_fixture())
    out = capsys.readouterr().out
    assert "upstream" in out and "ahead" in out
    assert "4" in out
    assert rc == 0, "a known-stale anchor is a FINDING, not an inconclusive check"


def test_the_cli_exits_four_when_a_check_could_not_conclude(capsys):
    run = _fake_git({
        **_IN_GIT,
        "rev-parse HEAD": (0, SHA_A),
        "rev-parse --abbrev-ref HEAD": (0, "feat/x"),
        "rev-parse --verify --quiet %s^{commit}" % SHA_A: (0, SHA_A),
        "rev-parse --verify --quiet HEAD^{commit}": (0, SHA_A),
        "rev-parse --verify --quiet origin/main^{commit}": (1, ""),
        "symbolic-ref --quiet --short refs/remotes/origin/HEAD": (1, ""),
    })
    rc = hr.main([], run_git=run)
    out = capsys.readouterr().out
    assert rc == 4
    assert "no remote-tracking ref" in out


def test_the_cli_exits_two_when_there_is_no_head_to_stamp(capsys):
    run = _fake_git({**_IN_GIT, "rev-parse HEAD": (128, "")})
    rc = hr.main([], run_git=run)
    err = capsys.readouterr().err
    assert rc == 2
    assert "HEAD" in err


def test_the_cli_refuses_an_unknown_flag(capsys):
    rc = hr.main(["--refesh"], run_git=_stamp_fixture())
    assert rc == 2
    assert "--refesh" in capsys.readouterr().err


def test_the_cli_passes_refresh_through(capsys):
    run = _stamp_fixture(**{_LSR: (0, "%s\trefs/heads/main\n" % SHA_B)})
    hr.main(["--refresh"], run_git=run)
    out = capsys.readouterr().out
    assert "remote" in out
    assert "not-attempted" not in out


def test_an_unknown_row_outcome_is_refused_at_construction():
    """`Row.outcome` was a bare string, so a typo rendered into the card silently.

    A nonsense word printed with the confidence of a verdict is this phase's own defect class, one
    layer down from the one it was opened for. Found in review.
    """
    import pytest
    for good in sorted(hr.OUTCOMES):
        hr.Row("checkout", good)            # must not raise
    with pytest.raises(ValueError) as e:
        hr.Row("checkout", "ahed")          # the plausible typo
    assert "ahed" in str(e.value)
    assert "unchanged" in str(e.value)      # the message names what IS known


def test_the_outcome_set_is_declared_wider_than_AC2_on_purpose():
    """Seven, not five, and the two extras are named rather than smuggled in."""
    assert hr.ANCHOR_OUTCOMES == {"unchanged", "ahead", "behind", "diverged", "unavailable"}
    assert hr.OUTCOMES - hr.ANCHOR_OUTCOMES == {"not-attempted", "differs"}


def test_a_timeout_is_not_reported_as_a_missing_object():
    """Every non-zero used to read as "not present in this repository"."""
    run = _fake_git({
        **_IN_GIT,
        "rev-parse --verify --quiet %s^{commit}" % SHA_A: (124, ""),
        "rev-parse --verify --quiet HEAD^{commit}": (0, SHA_B),
        "rev-parse --verify --quiet origin/main^{commit}": (0, SHA_B),
    })
    c = _row(hr.reconcile(_anchor(), run), "checkout").cause
    assert "124" in c, c
    assert "not present" not in c, c


def test_a_genuinely_absent_object_still_says_not_present():
    """The control: exit 1 IS "no such object", and that sentence must survive."""
    run = _fake_git({
        **_IN_GIT,
        "rev-parse --verify --quiet %s^{commit}" % SHA_A: (1, ""),
        "rev-parse --verify --quiet HEAD^{commit}": (0, SHA_B),
        "rev-parse --verify --quiet origin/main^{commit}": (0, SHA_B),
    })
    assert "not present" in _row(hr.reconcile(_anchor(), run), "checkout").cause


def test_a_broken_origin_ref_is_not_called_a_missing_remote_tracking_ref():
    """Same shape on the subject side: only exit 1 means the ref is absent."""
    run = _fake_git({
        **_IN_GIT,
        "rev-parse --verify --quiet %s^{commit}" % SHA_A: (0, SHA_A),
        "rev-parse --verify --quiet HEAD^{commit}": (0, SHA_A),
        "rev-parse --verify --quiet origin/main^{commit}": (128, "fatal: bad object"),
    })
    c = _row(hr.reconcile(_anchor(), run), "upstream").cause
    assert "128" in c, c
    assert c != "no remote-tracking ref"


def test_snapshot_line_present_separates_absent_from_unparseable():
    """`read_anchor` returning None covered two situations with opposite causes."""
    legacy = "## ⏳ CURRENT — 2026-01-17 (#32201)\n#32101 #32201\n"
    assert hr.read_anchor(legacy) is None
    assert hr.snapshot_line_present(legacy) is False

    # the format's own separator inside a branch name: git permits it, the pattern does not
    weird = "> snapshot: HEAD %s · feat/a·b · 2026-01-21T00:00:00Z\n" % SHA_A
    assert hr.snapshot_line_present(weird) is True, "the line IS there"
    # whether read_anchor copes is a separate question; the CAUSE must not deny the line exists
