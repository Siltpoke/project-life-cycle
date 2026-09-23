#!/usr/bin/env bash
# Invariant: `scripts/session_card.py` reaches the outside world through exactly the
# call sites it is pinned to, and no others.
#
# WHY THIS EXISTS. The card's CI row rests on one rule -- PLC reads a file and never queries a
# forge. Without this script that rule would be ENFORCED
# NOWHERE. A requirement that is
# substantively true and mechanically unchecked is how a requirement quietly stops being one.
#
# Why a forge query is the wrong shape here:
# `gh run list` can report `conclusion: failure` for runs that NEVER
# EXECUTED (e.g. billing-blocked); two blocked repos can produce two DIFFERENT structured
# shapes for the same cause; and `gh` has no request timeout (`cli/go-gh`'s `Timeout` defaults to
# zero), so a routable-but-silent host can hang it. A welcome-back card that can hang
# is worse than one that says less.
#
# WHY COUNTS AND NOT ABSENCE. Assert a COUNT against a pinned baseline, never
# the absence of a substring. An absence guard passes while a new call hides behind an alias
# (`from subprocess import run as _r`). A count
# cannot be satisfied by renaming; adding a call moves the number whatever it is called.
#
# TWO COUNTS, NOT ONE, because they pin different things and both are real:
#
#   * NET  -- `subprocess.` call sites. The file has two today:
#     `_run_resume`'s `save_session.py` shell-out and `main()`'s git runner. The CI row adds NEITHER, and
#     that is the point: the new git command goes through the runner that already exists.
#   * GIT  -- invocations of the INJECTED runner, `run([...])`. This number moved when the CI row landed (5 -> 6,
#     the `rev-parse origin/main`).
#     Pinning it makes "one additional invocation of the existing runner" a checked
#     statement rather than a sentence in a commit message.
#
# WHAT THIS DOES NOT PROVE, stated rather than implied:
#
#   * It does not prove the two pinned `subprocess.` sites are HARMLESS. They run `save_session.py`
#     and `git`; that they are the right two is a human judgement, not a
#     property this script can check.
#   * The import arm below is STRICTLY WEAKER than the counts and is not the load-bearing one. An
#     `__import__("urllib.request")` or a network call reached through a helper module defeats it.
#     It is here because a new networking import is the cheapest early signal, not because it
#     closes the hole.
#   * Nothing here observes a running process. A file that passes every arm could still open a
#     socket through a dependency. The counts bound what THIS FILE spells; they do not bound the
#     transitive behaviour of what it calls.
#
# COMMENT LINES ARE STRIPPED BEFORE COUNTING, and that is a real limit rather than a subtlety worth
# hiding: a `subprocess.` mentioned inside a DOCSTRING still counts, because this script does not
# parse Python. If a future edit needs to discuss the token in prose, it will move this number and
# the failure will say so. A wrong red is recoverable; a silent widening is not.
#
# Envelope: bash + grep only. No python3, no jq.

set -uo pipefail

NAME="session-card-no-network"

# The pinned baselines. Changing either of these is a DESIGN DECISION about what the card is allowed
# to reach, and it belongs in a phase with a story -- not in the commit that happens to trip it.
#
# NET MOVED 2 -> 3 IN A LATER CHANGE, and this paragraph is the record the line above asks for. The card
# now derives a station's POSITION, which design section 2.3 defines as the closed steps named
# across the closure declarations over the steps the station plan declares. Reading those two
# formats is the feature; it is not a convenience the card could do without and still answer the
# question the phase exists to answer.
#
# WHY IT IS A SUBPROCESS AND NOT PYTHON, which is the part worth checking rather than the number.
# Both formats already have exactly one reader in this repository -- scripts/lib/station-blocks.awk
# for the plan blocks and scripts/closure-declaration.sh for the closure grammar. A Python copy of
# either would be a second implementation of a grammar, which is the encoder-divergence class the
# p36 design forbids by name (and which this repo has already paid for once). So the card shells
# out to the readers it ships.
#
# ONE SITE, NOT TWO: `_station_facts` runs both commands through a single local `_sh` helper, so
# the count moves by one rather than by two. That is deliberate and it is why the number below is
# 3 and not 4.
#
# WHAT THIS COSTS, stated: the card now runs two local commands it did not run before. Neither
# touches the network; both are bounded by a 20-second timeout and degrade to `available: False`
# with a stated reason rather than raising, so a missing reader makes a position print `-` instead
# of making the card fail. `-` and `0/N` are deliberately different strings.
WANT_NET=3
WANT_GIT=6

pass() { printf 'PASS %s: %s\n' "$NAME" "$1"; exit 0; }
fail() { printf 'FAIL %s: %s\n' "$NAME" "$1"; exit 1; }
# A third verdict for "the CHECK failed, not the file". The gate reads exit status only, so
# 1 and 3 both block -- which is the fail-closed behaviour a check that could not run must have.
# What 3 buys is that a direct caller, CI, or a test can tell the two apart.
cannot_run() { printf 'FAIL %s: COULD NOT RUN -- %s\n' "$NAME" "$1"; exit 3; }

REPO_ROOT="${1:-$(git rev-parse --show-toplevel 2>/dev/null || true)}"
[ -n "$REPO_ROOT" ] || cannot_run "not inside a git work tree (git rev-parse --show-toplevel failed)"
while [ "$REPO_ROOT" != "/" ] && [ "$REPO_ROOT" != "${REPO_ROOT%/}" ]; do
  REPO_ROOT="${REPO_ROOT%/}"
done

TARGET="$REPO_ROOT/scripts/session_card.py"
# `-f`, never `-e`: a DIRECTORY named session_card.py is not a file this can read, and `-e` would
# send it into a grep that produces zero matches and a confident, false PASS.
[ -f "$TARGET" ] || cannot_run "not a readable file: $TARGET"
[ -r "$TARGET" ] || cannot_run "not readable: $TARGET"

# Strip whole-line comments before counting. Blank the line rather than delete it so that any future
# line-number reporting stays honest.
BODY="$(sed 's/^[[:space:]]*#.*$//' "$TARGET")"

count() { printf '%s\n' "$BODY" | grep -oE "$1" | grep -c . ; }

NET="$(count 'subprocess\.[A-Za-z_]+\(')"
ALL_RUN="$(count '\brun\(\[')"
NET_RUN="$(count 'subprocess\.run\(\[')"
GIT=$(( ALL_RUN - NET_RUN ))

# A zero here is not a pass. An empty scan and a clean file are the same number, and telling them
# apart is the difference between "I checked" and "I looked away".
if [ "$ALL_RUN" -eq 0 ] && [ "$NET" -eq 0 ]; then
  cannot_run "found ZERO call sites of any kind in $TARGET -- a file this size should have some, so the scan itself is suspect (wrong file, or a grep that matched nothing). Refusing to report a clean bill of health from an empty measurement"
fi

if [ "$NET" -ne "$WANT_NET" ]; then
  fail "subprocess call sites: $NET found, $WANT_NET expected
  -> The card's CI row adds NO new subprocess call site; the CI state is read from a
     local file and the reference SHA comes through the runner that already exists.
  -> If a new one is genuinely needed, that is a change to what the welcome-back card is allowed
     to reach, and it belongs in a phase with a story -- raise WANT_NET there, not here."
fi

# --- the alias arm, and it exists because the FIRST draft of this guard was defeated -------------
#
# The test written to demonstrate that counting beats
# absence-of-substring instead demonstrated that this script had the same hole it was built to
# close. `from subprocess import run as _r` followed by `_r([...])` matches NEITHER `subprocess\.`
# NOR `run\(\[`, so both counts stayed at their baselines and the guard passed a file that had just
# grown a new process spawn. The counting argument ("a count cannot be satisfied by renaming") was
# right about renaming the CALL and wrong about renaming the IMPORT.
#
# The fix is a conservation law rather than a third pattern to evade: every mention of the token
# `subprocess` in this file must be either the single `import subprocess` line or one of the pinned
# `subprocess.` call sites. TOKENS == NET + 1. An aliasing import adds a token without adding a
# call site; `import subprocess as sp` removes call sites without removing the token. Both move a
# number, which is the property being bought here -- not that this particular spelling is banned.
TOKENS="$(count '\bsubprocess\b')"
if [ "$TOKENS" -ne $(( NET + 1 )) ]; then
  fail "the \`subprocess\` token appears $TOKENS times but only $(( NET + 1 )) are accounted for (1 import + $NET call sites)
  -> Something references the module in a way this guard's call-site counts cannot see. The known
     shape is an aliasing import (\`from subprocess import run as _r\`, \`import subprocess as sp\`),
     which is how the first draft of THIS script was defeated by its own test.
  -> If the extra mention is innocent (a docstring, a string literal), it still hides real ones.
     Reword it, or move the baseline in a phase that says why."
fi

if [ "$GIT" -ne "$WANT_GIT" ]; then
  fail "injected-runner call sites: $GIT found, $WANT_GIT expected
  -> Every git command the card runs goes through the injected \`run\` so that tests can stub it and
     so that the set of commands is countable. A change here means the card asks git something new.
  -> Legitimate? Then move WANT_GIT in the phase that adds the command, with the reason written
     down beside it."
fi

# --- the dynamic-import arm, closed rather than left documented ----------------------------
#
# `__import__` is closed here rather than left as a documented limit. The exact input --
# `__import__("urllib.request").request.urlopen(...)` -- which carries no `subprocess` token, no
# `run([`, and no import STATEMENT for the arm below to see. A documented hole is still a hole,
# and closing this one takes one line.
#
# The remaining evasions are named rather than implied and are NOT closed: `importlib.import_module`
# is caught below only through the networking-import arm's `import importlib` (which a file could
# have for innocent reasons), and a network call reached through a HELPER MODULE is invisible to
# every arm here. This bounds what the file spells; it never bounded what it calls.
#
# AND ONE EVASION, DECLINED ON PURPOSE:
# `builtins.__dict__["__imp" "ort__"]("urllib.request")` defeats every arm above, and so does any
# `getattr`-and-string-concatenation spelling of the same idea. THIS IS NOT CHASED, and refusing to
# chase it is the decision rather than an oversight. EVERY lexical guard falls to string-splitting;
# adding a fourth pattern buys one spelling and implies completeness this file cannot have. The
# sibling `gate-jq-only-envelope.sh` draws the identical boundary in its own header, in its own
# words: "Deliberate evasion is not the threat; DRIFT is, and drift arrives spelled out." A
# contributor who writes `builtins.__dict__["__imp" "ort__"]` is not drifting. The honest answer is
# to say so here, where the next reader meets it, and to keep the PASS line's scope sentence narrow.
# `[[:space:]]*` around the dot: `importlib. import_module`
# -- whitespace after the attribute dot -- is VALID PYTHON and a tight regex would miss it.
# This is the ordinary-drift end of the spectrum (an
# autoformatter or a line wrap produces it), unlike the string-splitting evasion named above, which
# is why this one is closed and that one is not.
#
# FALSE-POSITIVE DIRECTION, NAMED (the same limit the `subprocess`
# conservation arm already carries): whole-line comments are stripped, STRING LITERALS are not. A
# `detail = "Error in __import__ call"` in this file would red. Parsing Python to tell the two apart
# is outside this script's bash-only envelope, and the failure direction is the safe one -- a loud,
# one-line, trivially-resolved red, versus a silent widening. Reword the string, or move the
# baseline in a phase that says why.
DYNIMPORT="$(count '__import__|importlib[[:space:]]*\.[[:space:]]*import_module')"
if [ "$DYNIMPORT" -ne 0 ]; then
  fail "$TARGET performs a DYNAMIC IMPORT ($DYNIMPORT occurrence(s) of __import__ / importlib.import_module)
  -> A dynamic import reaches a module without an import statement and without moving either
     call-site count, which is exactly how the counts above are evaded.
  -> This file has no legitimate need for one. If a future phase does, that is a change to what the
     welcome-back card is allowed to reach and it belongs in a phase with a story."
fi

# The weaker arm, kept last so its verdict cannot be mistaken for the load-bearing one.
NETLIBS="$(printf '%s\n' "$BODY" \
  | grep -nE '^[[:space:]]*(import|from)[[:space:]]+(urllib|http|socket|ssl|requests|httpx|aiohttp|ftplib|telnetlib|smtplib|xmlrpc)\b' || true)"
if [ -n "$NETLIBS" ]; then
  fail "a networking module is imported by $TARGET:
$NETLIBS
  -> PLC forbids forge-specific and network code ANYWHERE, not merely on the render path.
  -> This arm is weaker than the counts above and does not close the hole; tripping it means
     something quite direct happened."
fi

pass "subprocess call sites: $NET (pinned $WANT_NET) · injected-runner call sites: $GIT (pinned $WANT_GIT) · no dynamic import · no networking import. Counts bound what this FILE spells, never the transitive behaviour of what it calls"
