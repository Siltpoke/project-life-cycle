"""the two corpus-wide validators, and the archive control.

**No CJK in this file, deliberately.** This project bans CJK in shipped files outside
`README*` / `CHANGELOG.md` / `GUIDE*`.

These two guards differ from the per-document ones in their INPUT SET, which is the whole reason they are
separate scripts: they read every closure declaration in the repository, `docs/archive/**`
included, while the per-document ones read `docs/ROADMAP.md` alone. So the fixtures here are trees, not
single files, and several cases exist only to pin that the archive really is in scope.

**Why `test_positive_control_*` comes first.** On the real repository today
`closed-step-refs-resolve.sh` reports `⊘ 0 tokens`: no declaration has been written under
the new format yet. A guard proven only able to print a clean line over an empty scope has
been proven nothing — filed here as p38 and p32 — so every red case below is paired with
a green one over a NON-empty scope.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
INV = REPO / "scripts" / "invariants"
LIB = REPO / "scripts" / "lib"
REFS = INV / "closed-step-refs-resolve.sh"
STATE = INV / "station-state-consistency.sh"
FENCE = "`" * 3


def roadmap(*blocks: str, active: list[str] | None = None, plan: bool = True) -> str:
    """A minimal but real ROADMAP: a mainline table, the plan section, the active section.
    Built the way the contract says rather than trimmed to what the parser happens to need,
    so a case cannot pass because the fixture was too small to reach the rule."""
    rows = "\n".join(f"| row for {b.splitlines()[0][4:]} | what | light | eta |" for b in blocks)
    out = ["## \U0001f6e3 mainline", "", "| station | what | weight | eta |",
           "|---|---|---|---|", rows, ""]
    if plan:
        out += ["## \U0001f9ed station plans", "", "<!-- plc-station-plan v1 -->", ""]
        out += list(blocks)
    out += ["## \U0001f6a6 in flight", "", "<!-- plc-station-active v1 -->"]
    out += [f"- {a}" for a in (active or [])]
    out += [""]
    return "\n".join(out) + "\n"


def block(sid: str, nsteps: int, deps: str = "none") -> str:
    steps = "\n".join(f"  - s{i} step {i} of {sid}" for i in range(1, nsteps + 1))
    return (f"### {sid}\n"
            f"- binds-to: row for {sid}\n"
            f"- depends-on: {deps}\n"
            f"- steps:\n{steps}\n")


def declaration(*lines: str) -> str:
    return "# a phase doc\n\n" + "\n".join([f"{FENCE}plc-closes", *lines, FENCE, ""])


def tree(tmp_path: Path, rm: str, docs: dict[str, str]) -> tuple[Path, Path]:
    """Writes a roadmap and a corpus. `docs` maps a path relative to the corpus root to a
    document body, so a case can place a declaration under `archive/` on purpose."""
    root = tmp_path / "docs"
    root.mkdir(parents=True, exist_ok=True)
    rm_path = tmp_path / "ROADMAP.md"
    rm_path.write_text(rm, encoding="utf-8")
    for rel, body in docs.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return rm_path, root


def run(script: Path, rm_path: Path, root: Path) -> subprocess.CompletedProcess:
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
           "ROADMAP_PATH": str(rm_path),
           "CLOSURE_CORPUS_ROOT": str(root)}
    return subprocess.run(["/bin/bash", str(script)], cwd=REPO, env=env,
                          capture_output=True, text=True)


def tokens_via_shipped_helper(root: Path) -> list[str]:
    """The step tokens the corpus yields, obtained by calling the SHIPPED helper rather than
    by re-implementing it here. A test that parses the corpus its own way would agree with a
    broken helper."""
    script = (
        f'. "{LIB}/closure-corpus.sh"\n'
        f'files=$(closure_corpus_files "{root}")\n'
        f'[ -n "$files" ] || exit 0\n'
        f'closure_step_records "{REPO}/scripts/closure-declaration.sh" $files'
    )
    p = subprocess.run(["/bin/bash", "-c", script], cwd=REPO, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return sorted(ln.split("\t")[0] for ln in p.stdout.splitlines() if ln.strip())


# ================================================================ closed-step-refs-resolve


def test_positive_control_a_resolvable_token_is_accepted(tmp_path: Path) -> None:
    """The green half. Without it these guards are only proven able to go red."""
    rm, root = tree(tmp_path, roadmap(block("ci-line", 3), active=["ci-line"]),
                    {"specs/a.md": declaration("closed: B9001", "closed-step: ci-line.s1")})
    p = run(REFS, rm, root)
    assert p.returncode == 0, p.stderr
    assert p.stdout.startswith("✓"), p.stdout
    # The count is asserted, not just the tick: `⊘ 0 tokens` also exits 0 and would otherwise
    # be indistinguishable from having resolved something.
    assert "1 token(s)" in p.stdout, p.stdout


def test_token_naming_an_unknown_station_is_rejected(tmp_path: Path) -> None:
    rm, root = tree(tmp_path, roadmap(block("ci-line", 3)),
                    {"specs/a.md": declaration("closed-step: gate-line.s1")})
    p = run(REFS, rm, root)
    assert p.returncode != 0
    assert "no station plan declares a station 'gate-line'" in p.stderr, p.stderr


def test_token_naming_a_step_the_station_does_not_declare_is_rejected(tmp_path: Path) -> None:
    rm, root = tree(tmp_path, roadmap(block("ci-line", 3)),
                    {"specs/a.md": declaration("closed-step: ci-line.s9")})
    p = run(REFS, rm, root)
    assert p.returncode != 0
    assert "declares no step s9" in p.stderr, p.stderr


def test_the_failure_names_the_document_it_came_from(tmp_path: Path) -> None:
    """A corpus-wide check that cannot say WHERE sends the reader through fourteen files."""
    rm, root = tree(tmp_path, roadmap(block("ci-line", 3)),
                    {"specs/deep/nested/a.md": declaration("closed-step: ci-line.s9")})
    p = run(REFS, rm, root)
    assert p.returncode != 0
    assert "specs/deep/nested/a.md:" in p.stderr, p.stderr


def test_archive_is_in_scope(tmp_path: Path) -> None:
    """The reason this validator is corpus-wide at all. retention-drain moves the specs that
    hold declarations into the archive; a live-only scan would make every position reverse
    at that moment with nothing having happened."""
    rm, root = tree(tmp_path, roadmap(block("ci-line", 3)),
                    {"archive/working/old.md": declaration("closed-step: ci-line.s9")})
    p = run(REFS, rm, root)
    assert p.returncode != 0, "a declaration in the archive was not scanned"
    assert "declares no step s9" in p.stderr, p.stderr


def test_none_sentinel_resolves_to_nothing_and_is_not_a_dangling_reference(tmp_path: Path) -> None:
    rm, root = tree(tmp_path, roadmap(block("ci-line", 3)),
                    {"specs/a.md": declaration("closed: B9001", "closed-step: none")})
    p = run(REFS, rm, root)
    assert p.returncode == 0, p.stderr
    assert p.stdout.startswith("⊘"), p.stdout
    assert "0 `closed-step:` tokens" in p.stdout, p.stdout


def test_empty_corpus_says_so_instead_of_passing(tmp_path: Path) -> None:
    rm, root = tree(tmp_path, roadmap(block("ci-line", 3)), {})
    p = run(REFS, rm, root)
    assert p.returncode == 0, p.stderr
    assert p.stdout.startswith("⊘"), "an empty scope printed like a verified one"
    assert "0 tokens checked" in p.stdout, p.stdout


def test_an_unparseable_declaration_is_a_red_not_an_undercount(tmp_path: Path) -> None:
    rm, root = tree(tmp_path, roadmap(block("ci-line", 3)),
                    {"specs/a.md": declaration("closed-step: ci-line.s1"),
                     "specs/b.md": declaration("this line is not an entry")})
    p = run(REFS, rm, root)
    assert p.returncode != 0
    assert "could not be read" in p.stderr, p.stderr


# ============================================================= station-state-consistency


def test_derived_done_and_declared_in_flight_at_once_is_rejected(tmp_path: Path) -> None:
    rm, root = tree(tmp_path, roadmap(block("ci-line", 2), active=["ci-line"]),
                    {"specs/a.md": declaration("closed-step: ci-line.s1",
                                               "closed-step: ci-line.s2")})
    p = run(STATE, rm, root)
    assert p.returncode != 0
    assert "derived done (2/2" in p.stderr, p.stderr
    assert "will not pick a winner" in p.stderr, p.stderr


def test_done_and_not_in_flight_is_accepted(tmp_path: Path) -> None:
    rm, root = tree(tmp_path, roadmap(block("ci-line", 2), active=[]),
                    {"specs/a.md": declaration("closed-step: ci-line.s1",
                                               "closed-step: ci-line.s2")})
    p = run(STATE, rm, root)
    assert p.returncode == 0, p.stderr
    assert "1 derived done" in p.stdout, p.stdout


def test_partly_closed_and_in_flight_is_the_normal_case(tmp_path: Path) -> None:
    rm, root = tree(tmp_path, roadmap(block("ci-line", 3), active=["ci-line"]),
                    {"specs/a.md": declaration("closed-step: ci-line.s1")})
    p = run(STATE, rm, root)
    assert p.returncode == 0, p.stderr
    assert "0 derived done" in p.stdout, p.stdout


def test_the_same_step_named_twice_counts_once(tmp_path: Path) -> None:
    """Distinct steps, not rows. Counting rows would let a two-step station derive as done
    from two declarations that both touched step 1 — the numerator would be right and the
    thing it counted would be wrong."""
    rm, root = tree(tmp_path, roadmap(block("ci-line", 2), active=["ci-line"]),
                    {"specs/a.md": declaration("closed-step: ci-line.s1"),
                     "specs/b.md": declaration("closed-step: ci-line.s1")})
    p = run(STATE, rm, root)
    assert p.returncode == 0, p.stderr + p.stdout
    assert "0 derived done" in p.stdout, p.stdout


def test_a_second_station_does_not_borrow_the_first_ones_steps(tmp_path: Path) -> None:
    rm, root = tree(
        tmp_path,
        roadmap(block("ci-line", 2), block("gate-line", 2), active=["gate-line"]),
        {"specs/a.md": declaration("closed-step: ci-line.s1", "closed-step: ci-line.s2")},
    )
    p = run(STATE, rm, root)
    assert p.returncode == 0, p.stderr
    assert "1 derived done" in p.stdout, p.stdout


def test_no_blocks_says_so_instead_of_passing(tmp_path: Path) -> None:
    rm, root = tree(tmp_path, roadmap(plan=False, active=[]), {})
    p = run(STATE, rm, root)
    assert p.returncode == 0, p.stderr
    assert p.stdout.startswith("⊘"), "an empty scope printed like a verified one"
    assert "0 stations compared" in p.stdout, p.stdout


# ==================================================================== the archive control
# design 2.4 / AC-13. An executable control, not an assertion about the drain.


def test_archiving_a_declaration_does_not_move_any_position(tmp_path: Path) -> None:
    """Positions are the numerator over the denominator, and the numerator is exactly the
    set of distinct step tokens in the corpus. This moves a declaration from where the specs
    live to where the drain puts them and asserts that set is byte-identical.

    STATED, NOT GLOSSED: this SIMULATES the move rather than invoking
    `scripts/retention-drain.sh`, so what it proves is that the derivation is
    location-independent — not that the drain lands files at this particular path. The
    destination is read from the repository's own retention policy rather than invented, so
    the two cannot drift silently; the residue is that a drain writing somewhere else
    entirely would still satisfy this test.
    """
    import json
    policy = json.loads((REPO / ".claude" / "close-gate.json").read_text())
    archive_dir = policy.get("retention", {}).get("archive_dir", "docs/archive")
    assert archive_dir.startswith("docs/"), archive_dir
    dest_rel = archive_dir[len("docs/"):] + "/working"

    rm, root = tree(
        tmp_path,
        roadmap(block("ci-line", 3), active=["ci-line"]),
        {"superpowers/specs/a.md": declaration("closed: B9001", "closed-step: ci-line.s1",
                                               "closed-step: ci-line.s2")},
    )
    before = tokens_via_shipped_helper(root)
    assert before == ["ci-line.s1", "ci-line.s2"], before

    src = root / "superpowers" / "specs" / "a.md"
    dst = root / dest_rel / "a.md"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(src.read_bytes())
    src.unlink()

    after = tokens_via_shipped_helper(root)
    assert after == before, f"archiving moved the position: {before} -> {after}"

    # And both guards still decide the same way afterwards.
    assert run(REFS, rm, root).returncode == 0
    assert run(STATE, rm, root).returncode == 0
