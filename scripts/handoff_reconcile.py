"""handoff_reconcile — reconcile a handoff snapshot against the repository.

ONE shared module, TWO callers: `session_card.py` (behind /catchup) imports it, and /handoff
invokes its CLI through `scripts/plc-python.sh`. The reconciliation is code, not
prose the model is asked to remember, because the defect it fixes WAS a prose-layer defect — the
model read an ambiguous state value and rendered "no checkpoint yet - clean start" over a correct
handoff.

Why this module owns its own git runner instead of reusing the card's:
`session_card.py`'s injected `_run` returns **stdout only**. `git merge-base --is-ancestor` and
`git cat-file -e` answer through their RETURN CODE and print nothing, so through a stdout-only
runner a failed `rev-parse`, a "not an ancestor" answer and a genuine empty result are the same
empty string. `run_git` therefore returns (returncode, stdout, stderr) and takes a mandatory
timeout — which the card's runner also cannot provide, and the design requires.

Offline by default: nothing here touches the network unless `refresh=True`, which is the
only path allowed to run `git ls-remote`. `GIT_NO_LAZY_FETCH=1` is set on every call because on a
blobless/treeless partial clone `merge-base`/`rev-list`/`cat-file` can trigger a lazy object fetch
— the default path would then reach the network with no new process-spawn site, leaving the invariant
green and the guarantee broken.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional

# `/handoff` writes: `snapshot: HEAD <sha> · <branch> · <iso-ts>` (handoff-snapshot.md:69).
# The separator is U+00B7 MIDDLE DOT. Accept a plain `-` or `|` too, so a handoff that lost its
# non-ASCII punctuation in transit still parses rather than silently becoming "no anchor".
_SNAPSHOT_RE = re.compile(
    r"snapshot:\s*HEAD\s+(?P<sha>[0-9a-fA-F]{7,40})"
    r"(?:\s*[·|-]\s*(?P<branch>[^·|\n]+?)"
    r"(?:\s*[·|-]\s*(?P<ts>[^·|\n]+?))?)?\s*$",
    re.MULTILINE,
)

GIT_ENV_HARDENING = {
    "GIT_TERMINAL_PROMPT": "0",   # never block on credentials
    "GIT_OPTIONAL_LOCKS": "0",    # never take a lock just to answer a question
    "GIT_NO_LAZY_FETCH": "1",     # a partial clone must not fetch to answer us
}


@dataclass(frozen=True)
class GitResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    @property
    def out(self) -> str:
        return self.stdout.strip()


@dataclass(frozen=True)
class Anchor:
    sha: str
    branch: Optional[str]
    taken_at: Optional[str]


_SNAPSHOT_TOKEN = re.compile(r"snapshot:\s*HEAD\b", re.IGNORECASE)


def snapshot_line_present(block_text: str) -> bool:
    """Whether the block carries a `snapshot: HEAD …` line AT ALL.

    `read_anchor` returning None covered two different situations: a legacy handoff with no such
    line, and a line that is there and did not parse — a branch name containing `|` or the middle
    dot the format uses as its separator, or a sha length the pattern does not accept. The card
    reported both as "the handoff carries no `snapshot: HEAD <sha>` line", which is FALSE in the
    second case. A cause that lies about a check that honestly failed is this phase's own defect
    class.
    """
    return bool(block_text) and bool(_SNAPSHOT_TOKEN.search(block_text))


def read_anchor(block_text: str) -> Optional[Anchor]:
    """Parse the anchor out of ONE already-selected checkpoint block.

    It is handed the block and never selects one. `parse_newest_checkpoint` already owns that
    choice and has two shapes (a stacked `⏳` header block, or the head of the file); a second
    selector here could read one block's header beside another block's sha, which is this repo's
    encoder-divergence class.

    Returns None when the block carries no snapshot line. That is the legacy case — every
    handoff written before the snapshot line existed — not an error, and NOT a fallback to the PR-number path that was
    retired: a block with a PR reference and no snapshot line has no anchor.
    """
    if not block_text:
        return None
    m = _SNAPSHOT_RE.search(block_text)
    if not m:
        return None
    branch = (m.group("branch") or "").strip() or None
    ts = (m.group("ts") or "").strip() or None
    return Anchor(sha=m.group("sha"), branch=branch, taken_at=ts)


def run_git(args, *, timeout: float) -> GitResult:
    """Run one git command, surfacing the return code. `timeout` is mandatory on purpose."""
    env = dict(os.environ)
    env.update(GIT_ENV_HARDENING)
    try:
        p = subprocess.run(
            ["git", *args], capture_output=True, text=True, timeout=timeout, env=env,
        )
    except subprocess.TimeoutExpired:
        return GitResult(124, "", f"timed out after {timeout}s")
    except OSError as exc:
        return GitResult(127, "", str(exc))
    return GitResult(p.returncode, p.stdout, p.stderr)


# --------------------------------------------------------------------- tiers

# The SAVE-STATE vocabulary. `unknown` is deliberately absent: it used to mean BOTH "no handoff
# exists" (where "clean start" is true) and "a handoff exists but carried no parseable anchor"
# (where "clean start" is false). One word, opposite truths. Also not
# named `UNKNOWN`: Trivy's `UNKNOWN` labels a finding's severity, not a failed check, and reusing
# the word imports the wrong meaning.
TIERS = {"fresh", "doc-behind", "code-behind", "no-handoff", "unverified"}

# The closed set of row outcomes. `Row.outcome` was a bare string, so a typo (`"ahed"`) rendered
# silently into the card -- a nonsense word printed with the confidence of a verdict, which is the
# shape this phase exists to remove. Found in review.
#
# SEVEN, not five. The spec fixes five for the two ANCHOR rows; `not-attempted` is a deliberate skip
# rather than an outcome of a comparison, and `differs` belongs to the `remote` row alone, whose
# pair is different and whose direction is not establishable without a fetch. The count is stated
# here so the next phase adding a row has to decide whether its word belongs, instead of inventing
# one that renders.
ANCHOR_OUTCOMES = {"unchanged", "ahead", "behind", "diverged", "unavailable"}
OUTCOMES = ANCHOR_OUTCOMES | {"not-attempted", "differs"}


def classify_tier(*, upstream_advance, has_code, has_handoff: bool = True) -> str:
    """The tier keys on `upstream_advance` ALONE, which is defined for every row outcome.

    That is what makes `ahead` and `diverged` representable without a tier per outcome. In this
    repo a handoff is written on a feature branch and merges are squashes, so after a merge
    the anchor is never again an ancestor of `origin/main` and the upstream row is permanently
    `diverged` — the normal case, which the first draft of this design had no tier for at all.
    """
    if not has_handoff:
        return "no-handoff"
    if upstream_advance is None:
        return "unverified"
    if upstream_advance == 0:
        # The code question does not arise when the upstream has not moved, so an
        # unanswerable `has_code` cannot block the tier here.
        return "fresh"
    if has_code is None:
        # NOT "doc-behind". `has_code=None` means the file list could not be read, and
        # defaulting it to False would turn "I could not look" into the verdict "docs only"
        # -- the exact substitution this phase exists to remove.
        return "unverified"
    return "code-behind" if has_code else "doc-behind"


# ----------------------------------------------------------------- the rows

_NOT_ATTEMPTED_REMOTE = "not checked (offline by default) — run /catchup --refresh"


def _fetch_age(git_dir: str) -> str:
    """How stale `origin/main` may be, as a phrase for the offline row.

    The offline row is mandatory on every default run, so a reader learns to skip it
    unless it says something. The age of the last fetch is what makes it worth reading.

    A MISSING `FETCH_HEAD` is reported as "never fetched", never as age zero -- it is the
    stronger of the two warnings, and zero would read as "just now".
    """
    if not git_dir:
        return ""
    try:
        mtime = os.path.getmtime(os.path.join(git_dir, "FETCH_HEAD"))
    except OSError:
        return "never fetched in this clone"
    secs = max(0.0, time.time() - mtime)
    if secs < 3600:
        return "last fetch %dm ago" % int(secs // 60)
    if secs < 86400:
        return "last fetch %dh ago" % int(secs // 3600)
    return "last fetch %dd ago" % int(secs // 86400)


@dataclass
class Row:
    check: str                      # checkout | upstream | remote
    outcome: str                    # unchanged | ahead | behind | diverged | unavailable | not-attempted
    subject_advance: Optional[int] = None   # commits the SUBJECT has that the anchor lacks
    anchor_only: Optional[int] = None       # commits the ANCHOR has that the subject lacks
    cause: str = ""                 # mandatory whenever outcome is unavailable / not-attempted
    merge_base: Optional[str] = None        # kept so the range can be reused without recomputing it
    subject_sha: Optional[str] = None       # the resolved subject, for the same reason

    def __post_init__(self):
        if self.outcome not in OUTCOMES:
            raise ValueError(
                "unknown row outcome %r (known: %s)"
                % (self.outcome, ", ".join(sorted(OUTCOMES))))

    @property
    def is_unverified(self) -> bool:
        """`not-attempted` is NOT unverified.

        A check that was deliberately skipped must not move the exit status, or the offline
        default — which always skips the remote check — would make every single run non-zero,
        and an exit code that fires every time carries no information.
        """
        return self.outcome == "unavailable"


@dataclass
class Reconciliation:
    rows: list
    upstream_advance: Optional[int] = None
    no_git: bool = False

    @property
    def upstream_range(self):
        """`(merge_base, origin_sha)` for the upstream row, or None.

        Returned rather than recomputed by the caller: a second `merge-base` call is a second
        chance for the two answers to disagree, which is this repo's encoder-divergence class.
        """
        for r in self.rows:
            if r.check == "upstream" and r.merge_base and r.subject_sha:
                return (r.merge_base, r.subject_sha)
        return None

    @property
    def unverified(self) -> list:
        return [r for r in self.rows if r.is_unverified]

    @property
    def exit_code(self) -> int:
        # 4, never 3: plc-python.sh:288 already exits 3 for "no working Python interpreter",
        # commands/catchup.md documents that 3, and the wrapper `exec`s this script so the code
        # passes straight through. A 3 meaning both would be this phase's own defect, reproduced.
        return 4 if self.unverified else 0


def _resolve(run_git, rev: str, timeout: float):
    return run_git(["rev-parse", "--verify", "--quiet", "%s^{commit}" % rev], timeout=timeout)


def _resolve_cause(result, what: str) -> str:
    """Why a revision would not resolve, WITHOUT claiming more than the status says.

    Every non-zero used to be reported as "not present in this repository". A timeout (124), a
    missing git (127) and a corrupt repository (128) all read as a deleted object, which is a
    cause that lies about a check that honestly failed — the defect class this phase is named
    after, one layer inside its own error path.
    `rev-parse --verify --quiet` exits 1 for "no such object"; anything else is quoted.
    """
    if result.returncode == 1:
        return "%s not present in this repository" % what
    detail = (result.stderr or "").strip().splitlines()
    return "%s could not be resolved (rev-parse exited %d%s)" % (
        what, result.returncode, ": " + detail[0] if detail else "")


def _compare(run_git, anchor_sha: str, subject_rev: str, check: str, timeout: float) -> Row:
    a = _resolve(run_git, anchor_sha, timeout)
    if not a.ok:
        return Row(check, "unavailable",
                   cause=_resolve_cause(a, "saved commit %s" % anchor_sha[:12]))
    s = _resolve(run_git, subject_rev, timeout)
    if not s.ok:
        if subject_rev.startswith("origin/") and s.returncode == 1:
            cause = "no remote-tracking ref"
        else:
            cause = _resolve_cause(s, subject_rev)
        return Row(check, "unavailable", cause=cause)
    if a.out == s.out:
        return Row(check, "unchanged", subject_advance=0, anchor_only=0,
                   merge_base=a.out, subject_sha=s.out)
    mb = run_git(["merge-base", a.out, s.out], timeout=timeout)
    if not mb.ok or not mb.out:
        return Row(check, "unavailable", cause="no common ancestor with %s" % subject_rev)
    fwd = run_git(["rev-list", "--count", "%s..%s" % (mb.out, s.out)], timeout=timeout)
    back = run_git(["rev-list", "--count", "%s..%s" % (mb.out, a.out)], timeout=timeout)
    if not (fwd.ok and back.ok):
        return Row(check, "unavailable", cause="commit distance could not be counted")
    try:
        subject_advance, anchor_only = int(fwd.out), int(back.out)
    except ValueError:
        return Row(check, "unavailable", cause="commit distance was not a number")
    if subject_advance and anchor_only:
        outcome = "diverged"
    elif subject_advance:
        outcome = "ahead"
    elif anchor_only:
        outcome = "behind"
    else:
        outcome = "unchanged"
    return Row(check, outcome, subject_advance=subject_advance, anchor_only=anchor_only,
               merge_base=mb.out, subject_sha=s.out)


def reconcile(anchor: Anchor, run_git, *, refresh: bool = False, timeout: float = 5.0) -> Reconciliation:
    """Compare the anchor against the checkout and against `origin/main`, and say so per row.

    Two comparisons, not one: `checkout` answers "did my tree move", `upstream` answers "did
    the upstream move". Reporting only one of them is how the card could call a save `fresh` while
    the working tree sat behind — an ABSENT comparison, not a wrong one.
    """
    git_dir = run_git(["rev-parse", "--git-dir"], timeout=timeout)
    if not git_dir.ok:
        # The /handoff reference's existing `no-git` path wins. Emitting rows full of
        # `unavailable` here would dress "there is no repository" up as "I tried and failed".
        return Reconciliation(rows=[], no_git=True)

    rows = [
        _compare(run_git, anchor.sha, "HEAD", "checkout", timeout),
        _compare(run_git, anchor.sha, "origin/main", "upstream", timeout),
    ]
    upstream = rows[1]
    upstream_advance = None if upstream.outcome == "unavailable" else upstream.subject_advance

    if refresh:
        rows.append(_refresh_remote(run_git, timeout, local_ref_sha=upstream.subject_sha))
    else:
        age = _fetch_age(git_dir.out)
        rows.append(Row("remote", "not-attempted",
                        cause=_NOT_ATTEMPTED_REMOTE + (" · %s" % age if age else "")))

    return Reconciliation(rows=rows, upstream_advance=upstream_advance)


def _refresh_remote(run_git, timeout: float, *, local_ref_sha) -> Row:
    """The ONLY path allowed to touch the network. Bounded, read-only, mutates no ref.

    THIS ROW COMPARES A DIFFERENT PAIR than the other two, and the gloss says so. `checkout` and
    `upstream` both compare against the anchor; this one compares the **real remote** against the
    **local `origin/main` ref** -- because the question `--refresh` exists to answer is "is the
    ref I have been comparing against itself stale", and the anchor cannot answer that.

    `differs`, NOT `ahead`. When the remote tip is not an object in this repository we know the
    two are different and we do NOT know the direction; establishing it would mean fetching
    objects, which this design forbids on every path including this one. Borrowing `ahead` would state a
    direction the mechanism cannot establish -- the claim-wider-than-mechanism shape this repo
    keeps paying for. The five-word vocabulary the spec fixes is for the two anchor rows.
    """
    r = run_git(["ls-remote", "--heads", "origin", "refs/heads/main"], timeout=timeout)
    if not r.ok:
        # 124 is this module's own timeout code (see run_git), and it is surfaced as the status
        # rather than reworded, so a hung remote and a rejected connection stay distinguishable.
        return Row("remote", "unavailable", cause="ls-remote exited %d" % r.returncode)
    tip = ""
    for ln in r.stdout.split("\n"):
        parts = ln.split()
        if len(parts) >= 2 and parts[1] == "refs/heads/main":
            tip = parts[0]
            break
    if not tip:
        return Row("remote", "unavailable",
                   cause="the remote reported no refs/heads/main")
    if local_ref_sha and tip == local_ref_sha:
        return Row("remote", "unchanged",
                   cause="real remote matches your local origin/main")
    return Row("remote", "differs", subject_sha=tip,
               cause="real remote is %s, your local origin/main is %s — "
                     "direction not established (that would need a fetch)"
                     % (tip[:12], (local_ref_sha or "unknown")[:12]))


def files_changed(run_git, rng, *, timeout: float = 5.0):
    """The files a commit range touched, or **None** when the question could not be answered.

    `None` and `[]` are deliberately different. `[]` is a verdict -- the range touched nothing --
    and `classify_tier` is allowed to act on it. A failed lookup has no verdict, and handing it
    `[]` would silently convert "I could not look" into "docs only", which is the substitution
    this phase exists to remove.
    """
    if not rng:
        return None
    a, b = rng
    r = run_git(["diff", "--name-only", "%s..%s" % (a, b)], timeout=timeout)
    if not r.ok:
        return None
    return [ln.strip() for ln in r.stdout.split("\n") if ln.strip()]


# ------------------------------------------------------------------- the CLI


def stamp_anchor(run_git, *, timeout: float = 5.0):
    """Read the anchor `/handoff` is about to write. Returns (Anchor | None, the HEAD result).

    THE PARAMETER IS NAMED `run_git` ON PURPOSE, and so is every other runner parameter in this
    module. The no-network guard counts the runner's call sites by their literal spelling, so a
    call made through a local alias -- binding the runner to a short name and calling that --
    adds a real git command **without moving the pinned count**. The first draft of this function did exactly that: commands were
    added and the count stayed put. That is the renaming evasion the card's own guard was
    defeated by once already -- its alias arm says the "a count cannot be renamed around"
    argument was right about the CALL and wrong about the IMPORT. This is the call half, and it
    is real. One spelling everywhere is what makes the count mean anything.
    """
    head = run_git(["rev-parse", "HEAD"], timeout=timeout)
    if not head.ok or not head.out:
        return None, head
    branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], timeout=timeout)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return Anchor(sha=head.out, branch=(branch.out or None), taken_at=ts), head

def _render_rows(rec) -> list:
    out = []
    for r in rec.rows:
        if r.outcome in ("ahead", "behind"):
            n = r.subject_advance if r.outcome == "ahead" else r.anchor_only
            detail = "%s %s commit%s" % (r.outcome, n, "" if n == 1 else "s")
        elif r.outcome == "diverged":
            detail = "diverged (subject +%s, anchor +%s)" % (r.subject_advance, r.anchor_only)
        else:
            detail = r.outcome
        line = "%s: %s" % (r.check, detail)
        if r.cause:
            line += " — " + r.cause
        out.append(line)
    return out


def main(argv=None, *, run_git=None, timeout: float = 5.0) -> int:
    """The deterministic step `/handoff` runs before it stamps an anchor.

    It prints the `snapshot:` line itself, rather than leaving the model to assemble one from
    three separate commands, and prints the reconciliation of the anchor it is about to write.
    AC11: an anchor that is ALREADY behind the upstream is recorded, not omitted — which is the
    normal case in this repo, where handoffs are written on feature branches.

    The printed `snapshot:` line is the same format `read_anchor` parses, and a test pins the
    round trip. Originally the writer and the reader were connected by nothing: the line was
    written and never read, so a drift on either side was undetectable.

    Exit status matches the card's, deliberately: 0 verified, 4 something was attempted and could
    not conclude, 2 could not run. Never 3 — `scripts/plc-python.sh` owns that one.

    IT PRINTS NO TIER, AND THAT IS INTENDED. The card answers "is my save current" and needs a
    single word for it; `/handoff` is about to WRITE the anchor, so the useful output is the
    comparison itself, not a verdict about a snapshot that does not exist yet. `files_changed` is
    therefore not called here and the doc/code split is never computed on this path. Stated because
    the asymmetry between the two callers looks like an omission (a review
    read it as one) and is a decision.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    refresh = False
    for a in args:
        if a == "--refresh":
            refresh = True
        else:
            print("handoff_reconcile: unknown argument %r (known: --refresh)" % a,
                  file=sys.stderr)
            return 2

    runner = run_git if run_git is not None else globals()["run_git"]

    anchor, head = stamp_anchor(runner, timeout=timeout)
    if anchor is None:
        # No HEAD to stamp. The reference's `no-git` path owns this case; emitting rows full of
        # `unavailable` would dress "there is nothing to compare" up as "I tried and failed".
        print("handoff_reconcile: no HEAD to stamp (%s)"
              % (head.stderr.strip() or "rev-parse HEAD exited %d" % head.returncode),
              file=sys.stderr)
        return 2
    print("snapshot: HEAD %s · %s · %s" % (anchor.sha, anchor.branch or "-", anchor.taken_at))

    rec = reconcile(anchor, runner, refresh=refresh, timeout=timeout)
    if rec.no_git:
        return 2
    for line in _render_rows(rec):
        print(line)
    return rec.exit_code


if __name__ == "__main__":  # pragma: no cover - exercised through the CLI tests
    raise SystemExit(main())
