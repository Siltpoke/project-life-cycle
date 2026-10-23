"""The three Windows-audit findings that were filed unfixed, held to their exit criteria.

WHY THIS FILE EXISTS. Each of the three is a claim wider than the mechanism under it, and
each was previously "fixed" nowhere: the command docs assumed a working directory, the frontmatter
hooks assumed an executable bit, and the README named five hosts with no record that any had been
tried. A one-time edit closes none of them -- the next author adds a sixth bare path, a sixth host,
or a sixth hook, and nothing says anything. These rows are what makes the three stay closed.

The rows are deliberately shaped as ENUMERATE-THEN-SUBTRACT rather than as a fixed expected list:
a hard-coded count expires the moment a command doc is added, and an expired assertion is how this
repository has been caught out before (a test that hardcoded a state value). What is pinned
here is the PROPERTY -- every invocation is anchored or declared -- never the tally.
"""
import re
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
COMMANDS = ROOT / "commands"
SKILL_MD = ROOT / "skills" / "project-lifecycle" / "SKILL.md"
LEDGER = ROOT / "HOST-VERIFICATION.md"

# A `bash scripts/...` call that is NOT anchored to a plugin root. The leading class excludes the
# anchored form (which is preceded by `/` or `}`) and `${...}` expansions.
BARE_CALL = re.compile(r"(?:^|[^/${])bash scripts/")

# The sites that stay repo-relative ON PURPOSE, each with the reason. Anchoring one of these to
# ${CLAUDE_PLUGIN_ROOT} would point at the plugin's own checkout instead of the repository being
# acted on -- a silent wrong-tree bug, which is worse than the portability cost it would remove.
DECLARED_REPO_RELATIVE = {
    "release.md": (
        "/release acts on the repository you are standing in: validate.py resolves its own root "
        "from __file__, and gen-test-evidence.sh writes that repository's gate evidence. The "
        "command states the working-directory assumption in its own text."
    ),
}


def _command_docs():
    return sorted(p for p in COMMANDS.glob("*.md"))


def _bare_sites(path: Path):
    """Executable bare sites in one command doc, as (lineno, text). Prose is excluded by the
    caller's eye, never by this function -- see the test below for why that distinction is kept."""
    out = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if BARE_CALL.search(line):
            out.append((i, line.strip()))
    return out


def test_no_unanchored_plugin_script_calls_in_command_docs():
    """AC1/AC2 — every command doc either anchors its script calls or is declared repo-relative."""
    offenders = []
    for doc in _command_docs():
        if doc.name in DECLARED_REPO_RELATIVE:
            continue
        for lineno, text in _bare_sites(doc):
            offenders.append(f"{doc.relative_to(ROOT)}:{lineno}: {text[:120]}")
    assert not offenders, (
        "command docs call a script by a repo-relative path without being declared:\n"
        + "\n".join(offenders)
        + "\n\nAnchor it as bash \"${CLAUDE_PLUGIN_ROOT}/scripts/...\" (the form catchup.md, "
        "handoff.md and recall.md already use) when the script SHIPS WITH THE PLUGIN; or add the "
        "file to DECLARED_REPO_RELATIVE with the reason when it acts on the repository the user "
        "is standing in, and state the working-directory assumption in the doc itself."
    )


def test_the_declared_repo_relative_set_is_not_a_blank_cheque():
    """AC2 — a declared file must actually SAY it assumes the repo root, or the declaration is
    just a suppression. The reason string living in this file is not enough: the reader of the
    command doc is the one who needs it."""
    for name in DECLARED_REPO_RELATIVE:
        doc = COMMANDS / name
        assert doc.exists(), f"DECLARED_REPO_RELATIVE names {name}, which does not exist"
        text = doc.read_text(encoding="utf-8")
        assert "assumes the working directory is the root" in text, (
            f"{name} is declared repo-relative but never tells its reader so. Add the assumption "
            "to the document, not only to this test."
        )


def test_every_frontmatter_hook_runs_through_bash():
    """AC3 — Windows checkouts do not preserve an executable bit, and `.sh` is not an executable
    extension there. Measured on macOS with the bit stripped: the bare form exits 126 Permission
    denied, the `bash` form exits 0."""
    text = SKILL_MD.read_text(encoding="utf-8")
    frontmatter = text.split("---", 2)[1]
    commands = re.findall(r"^\s*command:\s*(.+)$", frontmatter, flags=re.M)
    assert commands, "SKILL.md frontmatter declares no hook commands -- did the block move?"
    bad = [c for c in commands if not c.strip().startswith('"bash \\"')]
    assert not bad, (
        "these frontmatter hook commands do not run through bash with a quoted path:\n"
        + "\n".join(bad)
        + "\n\nWithout `bash` they need an executable bit the checkout may not carry; without the "
        "inner quotes a plugin root containing a space word-splits."
    )


def test_the_bootstrap_probe_is_never_called_repo_relative():
    """AC1, widened by measurement rather than by taste. `archaeology-preflight.sh` is the one
    plugin-shipped script called from the SKILL and its references, and it runs during bootstrap --
    before the adopter's repository has a `scripts/` directory at all, so a repo-relative call
    there cannot resolve even on a POSIX host with the working directory in the right place.

    The sweep is narrow ON PURPOSE. 54 `bash scripts/...` lines live under skills/, and almost all
    of them name `close-gate.sh` or `retention-drain.sh` -- scripts the adopter COPIES INTO their
    own repository, where repo-relative is the correct spelling. Pinning the whole tree would
    demand a judgement per line and would redden on a correct one; pinning this script is a
    property, so it survives new call sites nobody has written yet."""
    bare = re.compile(r'(?:^|[^/${"])bash scripts/archaeology-preflight')
    offenders = []
    for path in sorted(ROOT.rglob("*.md")):
        rel = path.relative_to(ROOT)
        parts = rel.parts
        if parts[0] in {"docs", ".git"} and not (len(parts) > 1 and parts[0] == "docs" and parts[1] == "superpowers"):
            # docs/ holds the archive, whose bytes are moved verbatim and must never be edited.
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if bare.search(line):
                offenders.append(f"{rel}:{i}")
    assert not offenders, (
        "archaeology-preflight.sh is called by a repo-relative path here:\n" + "\n".join(offenders)
        + '\n\nIt ships WITH the plugin and runs before the adopter repo has a scripts/ directory. '
        'Write it as bash "${CLAUDE_PLUGIN_ROOT}/scripts/archaeology-preflight.sh".'
    )


def _ledger_hosts(ledger: str):
    """Every host named by a ledger row, verified or not."""
    hosts = []
    for line in ledger.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2 or cells[0] in ("host", "---") or set(cells[0]) <= {"-", " "}:
            continue
        hosts.append(cells[0])
    return hosts


def _unverified_hosts(ledger: str):
    """Host names the ledger's own rows mark unverified, read from the table.

    Derived, not listed: a hardcoded tuple silently stops checking the moment a SECOND host is
    marked unverified, and the only symptom is a row that keeps passing. The marker is the same
    `**unverified**` string the rows already use, so adding a host to the ledger is all it takes
    for this row to start guarding it."""
    hosts = []
    for line in ledger.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2 or cells[0] in ("host", "---"):
            continue
        if "**unverified**" in line:
            hosts.append(cells[0])
    assert hosts, (
        "no ledger row is marked `**unverified**`. Either every host really is verified -- in which "
        "case this row has nothing to guard and should be revisited -- or a row lost its marker."
    )
    return hosts


def _unverified_markers(ledger: str):
    """The markers the README may use to say a host is unverified, read from the LEDGER.

    Read, not hard-coded, so the ledger stays the one source. The marker is a LINK TARGET into the
    ledger's own `## Unverified` section rather than a phrase: a phrase needs one spelling per
    README language, and the Chinese spelling could live neither here (`scripts/` ships, and
    `scripts/invariants/no-cjk-in-shipped-files.sh` refuses CJK bytes there) nor in the ledger,
    which now ships too. A link target is ASCII and identical in every language."""
    markers = re.findall(r"^readme-marker-unverified(?:-\w+)?\s*=\s*(.+)$", ledger, flags=re.M)
    assert markers, (
        "HOST-VERIFICATION.md declares no `readme-marker-unverified` line, so this row "
        "has nothing to check the README against"
    )
    return [m.strip() for m in markers]


def _readme_host_line(path: Path, marker: str) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if marker in line:
            return line
    raise AssertionError(f"{path.name}: no host-claim line found (marker {marker!r})")


@pytest.mark.parametrize(
    "readme,marker",
    [("README.md", "#claude-code-setup"), ("README.zh-CN.md", "#claude-code-")],
)
def test_the_readme_host_claim_is_bounded_by_the_ledger(readme, marker):
    """AC5/AC6 — a host may be claimed only if the ledger carries a row for it, and a host the
    ledger marks unverified may not be claimed. The ledger is the source; the README is the view."""
    assert LEDGER.exists(), "HOST-VERIFICATION.md is missing -- the claim has nothing under it"
    ledger = LEDGER.read_text(encoding="utf-8")
    line = _readme_host_line(ROOT / readme, marker)

    # The rule is a property, and so is the CODE below: the unverified hosts are DERIVED from the
    # ledger rather than listed here. An earlier version said this in the comment while looping over
    # a hardcoded ("Antigravity",) -- the doc-wider-than-the-mechanism shape this very phase exists
    # to close, reproduced inside the fix for it, and caught by an independent reviewer.
    # The exact link target, not a substring: a longer path that contains the same name
    # would pass a substring check while pointing at a file that does not exist.
    assert "](HOST-VERIFICATION.md)" in line, (
        f"{readme}: the host claim does not link to HOST-VERIFICATION.md, so a reader has "
        "no way to check it -- which is the state this check exists to prevent."
    )
    assert "**unverified**" in ledger, "the ledger marks nothing unverified -- is every row real?"
    all_hosts = _ledger_hosts(ledger)
    for host in _unverified_hosts(ledger):
        idx = line.find(host)
        assert idx != -1, f"{readme}: {host} is in the ledger but missing from the claim line"
        # The window ENDS at the next host named on the line, and that bound is load-bearing. With
        # an open-ended tail, a host sitting earlier in the sentence passes on a marker that belongs
        # to a LATER host -- measured: marking a second row unverified left this row green, because
        # the trailing "not yet verified" about Antigravity was still somewhere to its right. A
        # mutant now kills it.
        later = [line.find(h) for h in all_hosts if h != host and line.find(h) > idx]
        end = min(later) if later else len(line)
        tail = line[idx:end]
        markers = _unverified_markers(ledger)
        assert any(m in tail for m in markers), (
            f"{readme}: {host} is marked unverified in the ledger but the README does not say "
            f"so in any declared wording {markers}. Narrow the claim, or add a real row to the "
            "ledger, or declare the wording in the ledger's markers block."
        )
