#!/usr/bin/env python3
"""blind_spots.py (the tracer's static half) — flag the test files one traced run does not fully
describe.

The criterion, from the Q1 lock: the tests where "what this run read" and "what this test could
read" differ. The output is a flag and nothing else -- it never adds an edge and never removes one.
What a flag MEANS for selection is `scripts/select-tests.sh`'s business (its documented fallback).

Output: TSV on stdout, one row per finding, sorted and unique:
    test-file <TAB> category <TAB> where
categories:
    enumerate   a directory listing: glob / iglob / rglob / walk / fwalk / listdir / scandir /
                iterdir. The trace saw the files that existed; a different tree lists others.
    find        `find` in a subprocess argv or shell string -- the same, run in a child.
    env         a path taken from the environment: os.getenv, os.environ.get / [...],
                expanduser, expandvars, Path.home(). Another environment reads another file.
    subprocess  a child whose reads the trace cannot see and no declaration accounts for:
                a repo script the map says the test ran (via=subprocess) that is not in
                .claude/generator-edges.tsv; inline code (`bash -c`, `python -c`); shell=True;
                os.system / os.popen / subprocess.getoutput.
    unparseable the file does not parse, so nothing above could be checked.

WHY THE AST AND NOT THE TEXT. A text scan cannot tell a use from a mention. An early run
was failed by a gate that read a word in a docstring as a use of it. So a string, a comment, or
`{**os.environ}` (the env copy nearly every subprocess test makes) flags nothing here.

WHY THE MAP FOR SUBPROCESSES. Which script a child runs is usually a path built at runtime
(`REPO / "scripts" / "x.sh"`); the trace recorded the real one. A DATA file in argv (a `.md`
handed to a script) is an input the trace already has -- only an executable (a `#!` line, or
`.sh` / `.bash` / `.py`) can hide reads.

BOUNDARY, stated: an argv list built in a variable is invisible to the inline-code check; if it
runs `bash -c` on a string, and no repo script path appears in its argv, nothing here flags it.
The completeness guard is what catches a read that no row explains.

PRECISION, measured and not fixed: most `enumerate` hits on the real repo list a directory the test
built itself under `tmp_path` (`out.glob(...)`, `index_dir.glob(...)`). That set is fully decided by
the test, so the flag is a false positive -- but telling a tmp-rooted variable from a repo-rooted
one needs dataflow across assignments and fixtures, and a wrong answer there is a silent miss.
Over-flagging only costs speed, so it is left, and counted.

Exit 0 with rows (or none); exit 2 on an unreadable input or a malformed edges row.
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import sys
from pathlib import Path

ENUMERATE = {"glob", "iglob", "rglob", "listdir", "scandir", "iterdir", "copytree"}
# `walk` / `fwalk` on anything but the `ast` module: os.walk, Path.walk (3.12+), aliases of both.
# `ast.walk(tree)` walks a syntax tree, and was a real-repo hit.
WALKS = {"walk", "fwalk"}
# Composing a child's PATH names no repo file. MEASURED: 5 of the first 13 env hits.
ENV_EXEMPT_KEYS = {"PATH"}
SPAWN = {"run", "call", "check_call", "check_output", "Popen", "create_subprocess_exec"}
ALWAYS_SHELL = {"system", "popen", "getoutput", "getstatusoutput", "create_subprocess_shell"}
# The process is replaced or forked with no argv this detector reads: always opaque.
OPAQUE = re.compile(r"^(exec[lv]p?e?|spawn[lv]p?e?|posix_spawnp?|fork|forkpty)$")
SHELLS = {"bash", "sh", "zsh", "dash", "python", "python3"}
# An interpreted file can hide reads whatever its first line says: `awk -f x.awk` can `getline`.
SCRIPT_SUFFIXES = {".sh", ".bash", ".py", ".awk", ".jq", ".sed", ".pl", ".rb", ".js", ".mjs"}
FIND_IN_SHELL = re.compile(r"(^|[\s;&|(`])find\s")


def _aliases(tree: ast.AST) -> dict[str, str]:
    """Local name -> dotted origin, from every import in the file. MEASURED by review: without
    this, `import os as o; o.walk(...)` and `from subprocess import run as r` were unflagged --
    the same class a sibling checker in this repo (p40) had already been defeated by."""
    names: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                names[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module:
            for a in node.names:
                names[a.asname or a.name] = f"{node.module}.{a.name}"
    return names


def _dotted(node: ast.AST, aliases: dict[str, str]) -> str:
    """Canonical dotted name of an expression, aliases resolved; `?` where it is not a name
    (`os.environ.copy()` -> `?.copy`'s receiver is a call). Never None, so the last part of an
    attribute chain is always there to match on."""
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value, aliases)}.{node.attr}"
    return "?"


def _mentions_environ(node: ast.AST, aliases: dict[str, str]) -> bool:
    """True if the environment mapping appears anywhere in this expression -- so
    `os.environ.copy()['X']` and `dict(os.environ)['X']` count like `os.environ['X']`."""
    for sub in ast.walk(node):
        if isinstance(sub, (ast.Name, ast.Attribute)):
            d = _dotted(sub, aliases)
            if d == "os.environ" or d == "environ" or d.endswith(".environ"):
                return True
    return False


def _argv_elements(call: ast.Call, varargs: bool = False) -> list[ast.AST]:
    """Elements of a literal argv list/tuple passed as the first positional argument or `args=`;
    with `varargs`, every positional argument (`create_subprocess_exec('bash', '-c', ...)`)."""
    if varargs:
        return list(call.args)
    first = call.args[0] if call.args else next(
        (k.value for k in call.keywords if k.arg == "args"), None)
    if isinstance(first, (ast.List, ast.Tuple)):
        return list(first.elts)
    return [first] if first is not None else []


def _const(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _exempt_key(node: ast.AST | None) -> bool:
    return node is not None and _const(node) in ENV_EXEMPT_KEYS


def _may_be_shell_program(node: ast.AST) -> bool:
    """A literal program name is a shell only if it is one (`git -c` is a config flag). Anything
    else -- `sys.executable`, a variable holding "bash" -- cannot be ruled out, so it counts."""
    s = _const(node)
    return os.path.basename(s) in SHELLS if s is not None else True


def scan_source(rel: str, source: str) -> list[tuple[str, str]]:
    """(category, where) for one test file's source."""
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return [("unparseable", f"{rel}:{e.lineno or 0}")]
    aliases = _aliases(tree)
    found: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        where = f"{rel}:{getattr(node, 'lineno', 0)}"
        if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load) \
                and _mentions_environ(node.value, aliases) and not _exempt_key(node.slice):
            found.append(("env", where))
        if not isinstance(node, ast.Call):
            continue
        callee = _dotted(node.func, aliases)
        name = callee.rsplit(".", 1)[-1]
        first_arg = node.args[0] if node.args else None
        if name in ENUMERATE or (name in WALKS and not callee.startswith("ast.")):
            found.append(("enumerate", where))
        if (name == "getenv" and not _exempt_key(first_arg)) or \
                name in ("expanduser", "expandvars") or \
                (name == "get" and _mentions_environ(node.func, aliases)
                 and not _exempt_key(first_arg)) or \
                (name == "home" and callee.endswith("Path.home")):
            found.append(("env", where))
        if OPAQUE.match(name) and callee.split(".", 1)[0] in ("os", "pty", name) or \
                callee == "pty.spawn":
            found.append(("subprocess", where))
            continue
        if name in ALWAYS_SHELL:
            found.append(("subprocess", where))
            elts = [node.args[0]] if node.args else []
        elif name in SPAWN:
            elts = _argv_elements(node, varargs=(name == "create_subprocess_exec"))
            if any(k.arg == "shell" and isinstance(k.value, ast.Constant) and k.value.value is True
                   for k in node.keywords):
                found.append(("subprocess", where))
            for i, e in enumerate(elts):
                if _const(e) == "-c" and i > 0 and _may_be_shell_program(elts[i - 1]):
                    found.append(("subprocess", where))
        else:
            continue
        for e in elts:
            s = _const(e)
            if s is not None and (os.path.basename(s) == "find" or FIND_IN_SHELL.search(s)):
                found.append(("find", where))
    return found


def read_declared(edges: Path) -> set[str]:
    declared: set[str] = set()
    for n, line in enumerate(edges.read_text(encoding="utf-8").splitlines(), 1):
        line = line.rstrip("\r")
        if not line or line.startswith("#") or line == "generator\treads\twrites":
            continue
        fields = line.split("\t")
        if len(fields) != 3 or not all(fields):
            raise ValueError(f"{edges}:{n}: an edges row needs exactly 3 non-empty fields: {line}")
        declared.add(fields[0])
    return declared


def subprocess_scripts(map_path: Path) -> dict[str, set[str]]:
    """test-file -> repo paths the trace saw in a child's argv."""
    out: dict[str, set[str]] = {}
    with map_path.open(encoding="utf-8") as fh:
        next(fh, None)
        for line in fh:
            fields = line.rstrip("\n").split("\t")
            if len(fields) == 4 and fields[2] == "subprocess":
                out.setdefault(fields[0], set()).add(fields[1])
    return out


def is_script(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.suffix in SCRIPT_SUFFIXES:
        return True
    try:
        with path.open("rb") as fh:
            return fh.read(2) == b"#!"
    except OSError:
        return False


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--map")
    ap.add_argument("--edges")
    ap.add_argument("files", nargs="*",
                    help="repo-relative test files; default: every test file in the map")
    a = ap.parse_args(argv)
    root = Path(a.root)
    map_path = Path(a.map) if a.map else root / ".claude" / "test-input-map.tsv"
    edges = Path(a.edges) if a.edges else root / ".claude" / "generator-edges.tsv"
    try:
        declared = read_declared(edges)
        spawned = subprocess_scripts(map_path)
        files = a.files or sorted({line.split("\t", 1)[0] for line in
                                   map_path.read_text(encoding="utf-8").splitlines()[1:] if line})
        rows: set[tuple[str, str, str]] = set()
        for rel in files:
            source = (root / rel).read_text(encoding="utf-8")
            rows.update((rel, cat, where) for cat, where in scan_source(rel, source))
            for p in spawned.get(rel, ()):
                if p not in declared and is_script(root / p):
                    rows.add((rel, "subprocess", f"runs undeclared {p}"))
    except (OSError, ValueError) as e:
        print(f"blind_spots: {e}", file=sys.stderr)
        return 2
    for row in sorted(rows):
        print("\t".join(row))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
