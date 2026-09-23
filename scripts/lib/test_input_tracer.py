"""Record which repo files a test process opens, by watching a real run.

The instrument behind `scripts/gen-test-input-map.sh`. The generator runs ONE pytest
process per test file and labels every row this module writes with that file, so this module
records only `<path> <TAB> <mode>` and knows nothing about pytest or test ids.

**Why one process per test file, and not an earlier prototype's per-test-id stamping.** MEASURED,
and it corrects that prototype's map: it ran many test files in one process, and a module is opened only by the
FIRST file that imports it -- every later importer finds it in `sys.modules` and opens nothing. So
`scripts/test_card_row_state.py` and `scripts/test_backlog_ledger.py`, which both
`import session_card` at top level, had no `scripts/session_card.py` row: a change to it would not
have selected them. That is a silent miss, the one failure direction the design forbids. A process per file
gives every file a cold `sys.modules`, which is the only way "what does this file read" has an
answer that does not depend on which files ran before it.

Why an audit hook and not coverage.py: coverage records which *lines ran*, never which *files were
read*. `sys.addaudithook` fires on `open` and on `subprocess.Popen`, so one pass yields the data-file
edges and the module-import edges, and it sees a path handed to a subprocess'd generator -- the
case ([M1] in the phase Q&A) that kills every source-text parser, because
`scripts/test_roadmap_lead_length.py` never contains the string `docs/ROADMAP.md`.

Usage (the generator does this; stated for debugging one file by hand):
    PYTHONPATH=scripts/lib PLC_TRACE_OUT=/path/to/out.tsv \\
        python3 -m pytest scripts/test_x.py -q -p test_input_tracer

Output is TSV, one record per line, deduplicated, in the order first seen:
    <repo-relative path> <TAB> <mode>
    mode `r` = opened in a way that can read what was already there
    mode `x` = named in a subprocess's argv, as the executable or as an argument

Properties that are load-bearing and easy to get wrong:

1. **The hook never opens a file.** Rows are appended with `os.write`, which raises no audit event,
   so writing from inside the hook cannot re-enter it -- a `print` or a buffered file object here
   would recurse forever. Rows reach disk as they are seen. MEASURED: the first design
   buffered everything and wrote once at session end; a run killed by the OS at 57% left zero bytes.

2. **Its own file is never recorded.** A test that reads the tracer's source would otherwise list it
   as an input, and the map would carry the instrument's footprint while looking completely normal.
   Nothing is lost by the filter: a change to the tracer forces a full run anyway (fallback 3).

3. **A path is recorded only if it is there at the moment it is seen -- and an `open` only if it
   names a regular file.** MEASURED: without the existence check, 44% of recorded paths were
   argv tokens that are not paths (`--emitter`, `p43`, hex like `4b`), because `_rel` joins any
   non-absolute string with cwd. The check has to happen here and not at analysis time: a test can
   create an input and delete it again.
   The regular-file half closes the prototype's "residual 4%, mechanism UNKNOWN" -- MEASURED, and the
   mechanism is now known. pytest removes old tmp dirs with `shutil.rmtree`, which opens each
   directory as `os.open(<name>, dir_fd=<parent>)`. The audit event carries `<name>` and not the
   fd, so `_rel` resolved it against cwd: `.git`, `scripts`, `objects`, `03`, from fixture repos
   earlier runs left behind. Existence alone could not drop them, because `.git` and `scripts`
   exist at the root. Worse than noise: the rows depended on leftover tmp dirs, so two runs
   differed and AC7 was unreachable -- with one process per test file, at every file that uses
   `tmp_path`. rmtree opens only directories, and a directory `open` is never a content read (a
   listing is `os.scandir` / `os.listdir`, which raise other events), so nothing real is lost.
   **Boundary, stated:** a test that depends on a file NOT existing is not represented. Opening an
   absent path is dropped here, and `Path.exists()` / `os.stat` raise no audit event at all, so
   that dependency was never visible to this mechanism in the first place. The same holds for a
   directory listing: `os.scandir` is not recorded, so "a new file appeared in this directory"
   reaches a test only through whatever else it reads.

4. **A write-only open is not recorded.** A file a test only writes is an output, not an input.
   An open that can read existing content (`r`, `r+`, `a+`, or `os.open` without `O_WRONLY` /
   `O_TRUNC`) IS recorded, because missing an input is silent while an extra row is only slow.

5. **`PLC_TRACE_OUT` is removed from the environment once read.** A child Python that inherited it
   and loaded this module would reopen the parent's output with `O_TRUNC` and erase it.
"""

import os
import sys

# Repo root: this file is <root>/scripts/lib/test_input_tracer.py
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ROOT_PREFIX = _ROOT + os.sep

_records = set()
_fd = -1

# Directories no changed-file set ever names, so a row under one can never select anything; it is
# only churn in the pin. `.git` counts at the root; the caches at any depth, because pytest puts
# `.pytest_cache` in whichever directory it picked as rootdir (both `./` and `scripts/` exist here).
_NOISE_CACHES = (".pytest_cache", ".mypy_cache")


def _is_noise(rel):
    if rel == ".git" or rel.startswith(".git" + os.sep):
        return True
    parts = rel.split(os.sep)
    return any(c in parts for c in _NOISE_CACHES)

# This file itself, repo-relative. Property 2 above.
_SELF_REL = os.path.relpath(os.path.abspath(__file__), _ROOT)


def _rel(path):
    """Repo-relative path, or None if outside the repo. String operations only — no syscalls.

    `os.path.realpath` would be more correct about symlinks and is deliberately not used: it stats,
    and this runs on every `open` in a 1929-test suite.
    """
    try:
        p = os.fspath(path)
    except TypeError:
        return None
    if not isinstance(p, str):
        try:
            p = p.decode("utf-8", "replace")
        except Exception:
            return None
    if not p:
        return None
    # Fast bail before normpath. This runs on EVERY open in the suite and most opens are stdlib
    # imports far outside the repo, so paying normpath for them dominated the first run (81 min
    # against a 26-31 min baseline). Only safe when normpath has nothing to collapse: `..`
    # (`/elsewhere/../<root>/x`), a doubled separator or a `.` component above the root
    # (`/home//me/<repo>/x`) all normalise INTO the repo, and dropping them would lose a real edge.
    if os.path.isabs(p):
        if (".." not in p and "//" not in p and "/./" not in p
                and not p.startswith(_ROOT_PREFIX)):
            return None
    else:
        p = os.path.join(os.getcwd(), p)
    p = os.path.normpath(p)
    if not p.startswith(_ROOT_PREFIX):
        return None
    rel = p[len(_ROOT_PREFIX):]
    # A path carrying a tab or a newline breaks the TSV it is written into. MEASURED: the
    # mode column of the first run contained `here.md` and 641 empty values, because rows split on
    # embedded separators. Dropped rather than escaped -- an input whose name contains a tab is not
    # a case this map needs to serve, and silently mangling the file it lands in is worse.
    if "\t" in rel or "\n" in rel or "\r" in rel:
        return None
    return rel


def _present(rel, mode):
    """Is this path there right now, in the form its mode needs? Property 3.

    An `r` row must be a regular file; an `x` row may be anything that exists, because a directory
    handed to a script is a real input -- the script can walk it.
    """
    try:
        p = os.path.join(_ROOT, rel)
        return os.path.isfile(p) if mode == "r" else os.path.exists(p)
    except Exception:
        return False


def _normalise_bytecode(rel):
    """Map `<d>/__pycache__/<stem>.cpython-313-pytest-9.1.1.pyc` back to `<d>/<stem>.py`.

    MEASURED, and it corrects the spec: the design says the audit hook "yields the code-dependency
    edges and the data-file edges in one pass". That is only true on a COLD `__pycache__`. With a
    warm cache — the normal case — CPython opens the `.pyc` and never touches the `.py`, so the same
    one-file run recorded 0 source files warm and 2 cold. Filtering `__pycache__` as noise (the first
    draft) therefore did not remove noise; it removed the entire import half of the map.

    Returning `<stem>.py` makes warm and cold runs agree, which is the only reason AC7 (a map that
    regenerates byte-identical) is reachable at all. pytest's assertion rewriting also writes
    `<stem>.cpython-...pyc.<PID>` temps, whose PID makes two runs differ; those are write-only opens
    and never reach this function (property 4).
    """
    head, base = os.path.split(rel)
    if os.path.basename(head) != "__pycache__":
        return rel
    if ".pyc" not in base:
        return None
    stem = base.split(".", 1)[0]
    if not stem:
        return None
    return os.path.join(os.path.dirname(head), stem + ".py")


def _can_read(mode, flags):
    """True when this open can read content that was already in the file. Property 4.

    `open` is raised by both `builtins.open` (mode is a string) and `os.open` (mode is None and the
    int flags carry the intent). When neither says, the answer is True: an extra row is slow, a
    missing one is a silent miss.
    """
    if isinstance(mode, str):
        return "r" in mode or ("a" in mode and "+" in mode)
    if isinstance(flags, int):
        if flags & os.O_TRUNC:
            return False
        return (flags & os.O_ACCMODE) in (os.O_RDONLY, os.O_RDWR)
    return True


def _emit(rel, mode):
    """Record once per (path, mode), and only if the path exists now (property 3).

    The dedup test runs BEFORE the stat, so a path opened a thousand times costs one stat. A path
    that was absent is NOT added to the set, so it is recorded the first time it is seen present.
    """
    key = (rel, mode)
    if key in _records:
        return
    if not _present(rel, mode):
        return
    _records.add(key)
    if _fd >= 0:
        try:
            os.write(_fd, ("%s\t%s\n" % key).encode("utf-8", "replace"))
        except Exception:
            pass          # a failed write must not propagate into arbitrary user code


def _hook(event, args):
    if event == "open":
        rel = _rel(args[0])
        if rel is None or _is_noise(rel):
            return
        mode = args[1] if len(args) > 1 else None
        flags = args[2] if len(args) > 2 else None
        if not _can_read(mode, flags):
            return
        rel = _normalise_bytecode(rel)
        if rel is None or rel == _SELF_REL:
            return
        _emit(rel, "r")
    elif event == "subprocess.Popen":
        # args = (executable, args, cwd, env). The child's own opens are NOT visible here (an audit
        # hook does not cross exec()), so the paths in its argv are the only edges this event can
        # supply -- the script it runs, and any data file handed to it.
        exe = args[0] if args else None
        rel = _rel(exe) if exe else None
        if rel is not None and rel != _SELF_REL and not _is_noise(rel):
            _emit(rel, "x")
        argv = args[1] if len(args) > 1 else None
        if isinstance(argv, (list, tuple)):
            for a in argv:
                r = _rel(a)
                if r is not None and r != _SELF_REL and not _is_noise(r):
                    _emit(r, "x")


# Armed ONLY when a destination is set. `sys.addaudithook` can never be removed, and `test_*.py`
# is pytest's collection pattern, so a run that merely collects this file without meaning to trace
# would otherwise carry an unremovable hook for the rest of the session.
_OUT = os.environ.pop("PLC_TRACE_OUT", None)      # property 5
if _OUT:
    # Opened BEFORE the hook is armed, so this open is not recorded and cannot recurse.
    _fd = os.open(_OUT, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    sys.addaudithook(_hook)
