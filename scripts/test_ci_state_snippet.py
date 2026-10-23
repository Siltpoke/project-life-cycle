"""The documented ci-status producer snippet must still parse.

PLC does not ship forge-specific code, so the producer for
`.claude/ci-status.json` lives in references/ci-cd-gates.md as an example an
adopter copies. That leaves it with no gate behind it -- prose asserting
something no mechanism checks.

Two mechanisms cover it, split by where they are allowed to run:

  * the schema string is pinned by scripts/invariants/documented-snippet-matches-reader.sh,
    which runs inside the gate and therefore may not invoke python
  * the snippet PARSING is checked here, where python is available

Neither covers whether `gh`'s JSON field names have moved. That needs the
network, and ci-cd-gates.md argues against a gate that needs the network.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

DOC = Path(__file__).resolve().parents[1] / "skills" / "project-lifecycle" / "references" / "ci-cd-gates.md"
HEADING = "### Putting the state on record"


def _snippet() -> str:
    text = DOC.read_text(encoding="utf-8")
    assert HEADING in text, f"{DOC.name} no longer has the section that holds the snippet"
    after = text[text.index(HEADING):]
    m = re.search(r"```python\n(.*?)```", after, re.S)
    assert m, "the section exists but carries no python block"
    return m.group(1)


def test_the_documented_snippet_parses() -> None:
    ast.parse(_snippet())


def test_the_snippet_is_not_empty() -> None:
    """Without this, deleting the body leaves an empty block that parses fine and
    the parse test goes green over nothing."""
    body = _snippet().strip()
    assert len(body.splitlines()) > 10, f"snippet is only {len(body.splitlines())} lines; did it get gutted?"


def test_the_snippet_still_defines_the_observer() -> None:
    tree = ast.parse(_snippet())
    names = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert "observe" in names, f"expected an observe() function, found {sorted(names)}"


def test_the_snippet_passes_a_timeout_to_gh() -> None:
    """an earlier measurement had `gh` hanging on a routable-but-silent host,
    because cli/go-gh's Timeout defaults to zero. A copied snippet without a
    timeout reintroduces that into whatever the adopter wires it to."""
    assert re.search(r"timeout\s*=\s*\d+", _snippet()), "the snippet calls gh with no timeout"
