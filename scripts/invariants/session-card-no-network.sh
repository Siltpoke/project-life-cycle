#!/usr/bin/env bash
# Invariant: `scripts/session_card.py` reaches the outside world through exactly the
# call sites it is pinned to, and no others.
#
# WHY THIS EXISTS. The card's CI row rests on one rule -- PLC reads a file and never queries a
# forge. Without this script that rule would be ENFORCED NOWHERE. A requirement that is
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
WANT_TOKEN_EXTRA=0
WANT_NETGIT=0
# The card spells no runner call sites of its own -- every git command added for the reconciliation lives in the
# module -- but it does MENTION the runner's name (the parameter it threads through, and the
# production injection in main()). Pinning the mentions is what makes "0 call sites here" mean
# something rather than being true by accident.
WANT_RUNNER=0
WANT_RUNNER_TOKENS=8

# --- SECOND TARGET ---------------------------------------------------------------
#
# WHY A SECOND TARGET AT ALL, since the header above is emphatic that these counts bound what ONE
# FILE spells and never the transitive behaviour of what it calls. The card CALLs a new
# module, `scripts/handoff_reconcile.py`, and moves every new git command into it. Under the old
# single-target shape that is a hole with a green light: the card's own counts would not move (the
# commands are not spelled there), so `WANT_GIT` could not be raised to record anything, and a
# future edit could add a network call to the module with this guard still passing. Both cross-check
# agents of that phase found the same hole independently, and the first draft of its spec promised
# to "update WANT_GIT in the same commit as the new call" -- a promise that was VACUOUS, because the
# number it named could not move. The transitive limit stays true in general; it is closed for this
# one callee by naming the callee.
#
# WHY THE CONSERVATION LAW IS SPELLED DIFFERENTLY HERE. The card's law is TOKENS == NET + 1 exactly
# (one import, N call sites). The module legitimately mentions the module object WITHOUT calling it:
# `except subprocess.TimeoutExpired:` is how a mandatory timeout is caught, and the timeout is what
# the design requires. So the law becomes TOKENS == NET + 1 + EXTRA with EXTRA pinned per target. It keeps
# the property that matters -- an aliasing import adds a token and goes red -- while not pretending
# the card's exact arithmetic transfers. EXTRA is 0 for the card, 1 for the module.
#
# WHY A NET-CAPABLE-SUBCOMMAND ARM. All of the module's git commands go through its single process
# spawn, so the subprocess count cannot distinguish "asked git a local question" from "asked git to
# talk to a remote". The arm below pins the number of git subcommands that CAN reach the network,
# quoted as string literals. The module is allowed exactly ONE (`ls-remote`, behind `--refresh`,
# which is the only networked path); the card is allowed ZERO. A second one moves the
# number. This is lexical like everything else here and inherits the same limits.
WANT_NET_RECONCILE=1
# RUNNER MOVED 6 -> 7, and this is the record the pin above asks for. The seventh call
# is `git diff --name-only <merge-base>..<origin/main>`, which answers whether the commits the
# upstream gained since the fork point touch code or only docs -- the input the `doc-behind` /
# `code-behind` split needs. It is a LOCAL question (`netgit` below stays 1), and it replaced a
# per-PR `log -40` + `show --name-only` lookup rather than adding to it: the card still runs those
# two for its "Recently shipped" row, which is a different consumer and is why they stay.
# RUNNER MOVED 7 -> 9. The two new calls are `rev-parse HEAD` and
# `rev-parse --abbrev-ref HEAD`, read by `stamp_anchor` so that /handoff's snapshot line is
# assembled by code instead of by a model running three commands and concatenating them.
#
# AND THE REASON THIS NUMBER IS 9 RATHER THAN 7 IS WORTH THE PARAGRAPH, because the first draft
# of that function kept it at 7 while adding both commands. It bound the runner to a two-letter
# local name and called that, and the arm below counts the runner's call sites by their literal
# spelling -- so two real git commands were invisible to the pin written to catch exactly that.
# This is the renaming evasion the card's alias arm already records in its own words ("right about
# renaming the CALL and wrong about renaming the IMPORT"); this was the call half. Every runner
# parameter in the module is now spelled the same way, and the conservation arm below makes a
# future alias a red rather than a silence.
WANT_RUNNER_RECONCILE=9
# Every mention of the runner's name must be one of: the `def run_git` line, the pinned call
# sites, or a parameter/argument spelling of the same name. A short alias adds a mention without
# adding a counted call site, which moves this number. Derived the same way the `subprocess`
# conservation law is, and for the same measured reason.
WANT_RUNNER_TOKENS_RECONCILE=27
WANT_TOKEN_EXTRA_RECONCILE=1
WANT_NETGIT_RECONCILE=1

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

# One target per call. It writes its summary to the global SUMMARY and prints NOTHING on success.
#
# IT IS CALLED WITHOUT COMMAND SUBSTITUTION, ON PURPOSE, and this paragraph is here because the
# first draft of this refactor got it wrong in the exact shape this script exists to prevent. That
# draft wrote `OUT="$(check_target ...)"`, which captures stdout -- so every `fail` message went
# into the variable and was DISCARDED when the exit fired. The guard then printed nothing at all
# while rejecting the file: a check whose failures are invisible is worse than no check, because
# the transcript carries silence that reads exactly like a pass. Measured by mutating the module to
# add a `git fetch` and watching the guard emit zero bytes.
#
# The FAILURE MESSAGES BELOW ARE WORD-FOR-WORD what the single-target version printed. They are
# asserted verbatim by scripts/test_session_card_no_network.py, and the point of keeping them is
# not the test -- it is that a guard's wording is its interface to whoever is woken by it.
check_target() {
  label="$1"; target="$2"; want_net="$3"; want_runner="$4"; want_extra="$5"; want_netgit="$6"; runner_pat="$7"; want_runner_tokens="$8"

  # `-f`, never `-e`: a DIRECTORY with this name is not a file this can read, and `-e` would send it
  # into a grep that produces zero matches and a confident, false PASS. This repo has filed the
  # `-e`-where-`-f`-was-meant shape before.
  [ -f "$target" ] || cannot_run "not a readable file: $target"
  [ -r "$target" ] || cannot_run "not readable: $target"

  # Strip whole-line comments before counting. Blank the line rather than delete it so that any
  # future line-number reporting stays honest.
  BODY="$(sed 's/^[[:space:]]*#.*$//' "$target")"

  count() { printf '%s\n' "$BODY" | grep -oE "$1" | grep -c . ; }

  NET="$(count 'subprocess\.[A-Za-z_]+\(')"
  ALL_RUN="$(count "$runner_pat")"
  NET_RUN="$(count "subprocess\.${runner_pat#\\b}")"
  RUNNER=$(( ALL_RUN - NET_RUN ))

  # A zero here is not a pass. An empty scan and a clean file are the same number, and telling them
  # apart is the difference between "I checked" and "I looked away" -- the failure mode this repo
  # has measured in several shapes.
  if [ "$ALL_RUN" -eq 0 ] && [ "$NET" -eq 0 ]; then
    cannot_run "found ZERO call sites of any kind in $target -- a file this size should have some, so the scan itself is suspect (wrong file, or a grep that matched nothing). Refusing to report a clean bill of health from an empty measurement"
  fi

  if [ "$NET" -ne "$want_net" ]; then
    fail "subprocess call sites: $NET found, $want_net expected  [target: $label -- $target]
  -> The card's CI row adds NO new subprocess call site; the CI state is read from a
     local file and the reference SHA comes through the runner that already exists.
  -> If a new one is genuinely needed, that is a change to what this file is allowed to reach, and
     it belongs in a phase with a story -- raise the pinned count there, not here."
  fi

  TOKENS="$(count '\bsubprocess\b')"
  if [ "$TOKENS" -ne $(( NET + 1 + want_extra )) ]; then
    fail "the \`subprocess\` token appears $TOKENS times but only $(( NET + 1 + want_extra )) are accounted for (1 import + $NET call sites + $want_extra non-call reference(s))  [target: $label]
  -> Something references the module in a way this guard's call-site counts cannot see. The known
     shape is an aliasing import (\`from subprocess import run as _r\`, \`import subprocess as sp\`),
     which is how the first draft of THIS script was defeated by its own test.
  -> If the extra mention is innocent (a docstring, a string literal), it still hides real ones.
     Reword it, or move the baseline in a phase that says why."
  fi

  if [ "$RUNNER" -ne "$want_runner" ]; then
    fail "injected-runner call sites: $RUNNER found, $want_runner expected  [target: $label -- pattern $runner_pat]
  -> Every git command this file runs goes through one runner so that tests can stub it and so that
     the set of commands is countable. A change here means it asks git something new.
  -> Legitimate? Then move the pinned count in the phase that adds the command, with the reason
     written down beside it."
  fi

  # --- the runner conservation arm, and it exists because this guard's own pin was walked
  # around by a rename. The reconciliation added two real git commands to the module while the call-site
  # count stayed put: the runner had been bound to a short local name and that name was called.
  # The arm below is the same conservation law the `subprocess` arm uses, applied to the runner:
  # every mention of its name must be one of the counted call sites or a parameter/argument
  # spelling of it. A short alias adds a mention without adding a call site, so it moves this
  # number and goes red. The card's alias arm already recorded half of this lesson in its own
  # words -- "right about renaming the CALL and wrong about renaming the IMPORT" -- and this is
  # the call half, measured rather than anticipated.
  RUNNER_TOKENS="$(count '\brun_git\b')"
  if [ "$RUNNER_TOKENS" -ne "$want_runner_tokens" ]; then
    fail "the \`run_git\` token appears $RUNNER_TOKENS times but $want_runner_tokens are accounted for  [target: $label]
  -> A mention that is not one of the $RUNNER counted call sites is either a new call reached
     through an ALIAS (the shape that made two git commands invisible to this pin once already),
     or prose. Both move this number, which is the property being bought.
  -> If the extra mention is innocent (a docstring, a comment on a code line), it still hides
     real ones. Reword it, or move the baseline in a phase that says why."
  fi

  NETGIT="$(count '"(ls-remote|fetch|push|pull|clone)"')"
  if [ "$NETGIT" -ne "$want_netgit" ]; then
    fail "network-capable git subcommands named as string literals: $NETGIT found, $want_netgit expected  [target: $label]
  -> Every git command in this file goes through ONE process spawn, so the subprocess count cannot
     tell a local question from a remote one. This arm is what does.
  -> The design locks offline-by-default with exactly one networked path (\`ls-remote\`, behind
     \`--refresh\`). A second one is a change to that decision and belongs in a phase with a story."
  fi

  # --- the os-level spawn arm, and it exists because an independent review DEFEATED the two
  # arms above with it. The counts measure `subprocess.` and the injected runner; the OS spawn
  # family is a different API reaching the same place. Measured on scratch copies with a positive
  # control (a new runner call did go red): `os.system("git fetch origin")` in the module,
  # `os.popen("curl http://x")` in the card, and `import os, urllib.request` in place of
  # `import os` ALL printed PASS with every pinned number unchanged.
  #
  # The header above said a count "cannot be satisfied by renaming". That is true of renaming the
  # CALL and of renaming the IMPORT -- both already have arms -- and FALSE of using a different
  # spawn API, which is neither. The claim was wider than the mechanism, in the file whose job is
  # to stop exactly that.
  #
  # Zero, not pinned: neither file has any business spawning a process outside the one runner, so
  # there is no baseline to move and no judgement to make. `os.environ` / `os.path` are untouched
  # by this pattern on purpose -- the module needs both.
  OSSPAWN="$(count 'os[[:space:]]*\.[[:space:]]*(system|popen|posix_spawn[a-z_]*|exec[lv][a-z]*|spawn[lv][a-z]*|fork|forkpty|openpty)[[:space:]]*\(')"
  if [ "$OSSPAWN" -ne 0 ]; then
    fail "$target spawns a process through the os module ($OSSPAWN occurrence(s) of os.system / os.popen / os.exec* / os.spawn* / os.fork)  [target: $label]
  -> A different spawn API reaches the same place as \`subprocess\` while moving neither the
     subprocess count nor the runner count. This arm exists because a review defeated the other
     two with precisely that.
  -> Every process these files start goes through the single runner. If a future phase needs
     another, that is a change to what this file is allowed to reach and it belongs in a phase
     with a story."
  fi

  # --- RESTORED, and the restoration is the finding -------------------------------------------
  #
  # A refactor DELETED this whole header when it parameterised the arms, and nothing in the
  # targeted test subset noticed. The full suite did:
  # `test_ensure_lychee.py::test_the_no_network_guard_names_the_evasion_it_declines_to_chase`
  # asserts the strings `DECLINED ON PURPOSE` and `string-splitting` are present, because a decline
  # is only honest if it is written where the next reader meets it. A test in a file named after
  # `lychee` guards a property of THIS file, which is exactly why a subset chosen by reasoning
  # about which files a change touches could not find it.
  # --- the dynamic-import arm, closed rather than left documented ----------------------------
  #
  # This header used to NAME `__import__` as a known limit, and the evidence row repeated it.
  # The cross-family reviewer supplied the exact input --
  # `__import__("urllib.request").request.urlopen(...)` -- which carries no `subprocess` token, no
  # `run([`, and no import STATEMENT for the arm below to see. A documented hole is still a hole,
  # this one was documented instead of closed because closing it looked expensive. It is one line.
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
  # -- whitespace after the attribute dot -- is VALID PYTHON and a tight regex would miss it; confirmed by
  # executing it, not by reading the grammar. This is the ordinary-drift end of the spectrum (an
  # autoformatter or a line wrap produces it), unlike the string-splitting evasion named above, which
  # is why this one is closed and that one is not.
  #
  # FALSE-POSITIVE DIRECTION, NAMED (same reviewer, and it is the same limit the `subprocess`
  # conservation arm already carries): whole-line comments are stripped, STRING LITERALS are not. A
  # `detail = "Error in __import__ call"` in this file would red. Parsing Python to tell the two apart
  # is outside this script's bash-only envelope, and the failure direction is the safe one -- a loud,
  # one-line, trivially-resolved red, versus a silent widening. Reword the string, or move the
  # baseline in a phase that says why.
  DYNIMPORT="$(count '__import__|importlib[[:space:]]*\.[[:space:]]*import_module')"
  if [ "$DYNIMPORT" -ne 0 ]; then
    fail "$target performs a DYNAMIC IMPORT ($DYNIMPORT occurrence(s) of __import__ / importlib.import_module)  [target: $label]
  -> A dynamic import reaches a module without an import statement and without moving either
     call-site count, which is exactly how the counts above are evaded.
  -> This file has no legitimate need for one. If a future phase does, that is a change to what it
     is allowed to reach and it belongs in a phase with a story."
  fi

  # The weaker arm, kept last so its verdict cannot be mistaken for the load-bearing one.
  # `(\w+,[[:space:]]*)*` before the net module: `import os, urllib.request` anchored past the
  # first name and slipped through, which the same review measured. Still lexical, still bounded.
  NETLIBS="$(printf '%s\n' "$BODY" \
    | grep -nE '^[[:space:]]*(import|from)[[:space:]]+([A-Za-z_][A-Za-z0-9_.]*[[:space:]]*,[[:space:]]*)*(urllib|http|socket|ssl|requests|httpx|aiohttp|ftplib|telnetlib|smtplib|xmlrpc)\b' || true)"
  if [ -n "$NETLIBS" ]; then
    fail "a networking module is imported by $target:
$NETLIBS
  -> PLC forbids forge-specific and network code ANYWHERE, not merely on the render path.
  -> This arm is weaker than the counts above and does not close the hole; tripping it means
     something quite direct happened."
  fi

  SUMMARY="subprocess call sites: $NET (pinned $want_net) · injected-runner call sites: $RUNNER (pinned $want_runner) · runner mentions: $RUNNER_TOKENS (pinned $want_runner_tokens) · network-capable git subcommands: $NETGIT (pinned $want_netgit) · no os-level spawn · no dynamic import · no networking import"
}

check_target card "$REPO_ROOT/scripts/session_card.py" \
  "$WANT_NET" "$WANT_GIT" "$WANT_TOKEN_EXTRA" "$WANT_NETGIT" '\brun\(\[' "$WANT_RUNNER_TOKENS"
SUM_CARD="$SUMMARY"

check_target reconcile "$REPO_ROOT/scripts/handoff_reconcile.py" \
  "$WANT_NET_RECONCILE" "$WANT_RUNNER_RECONCILE" "$WANT_TOKEN_EXTRA_RECONCILE" \
  "$WANT_NETGIT_RECONCILE" '\brun_git\(\[' "$WANT_RUNNER_TOKENS_RECONCILE"
SUM_RECONCILE="$SUMMARY"

pass "$SUM_CARD
  reconcile (scripts/handoff_reconcile.py) -- $SUM_RECONCILE
  Counts bound what each FILE spells. The transitive limit named in the header still holds in
  general; it is closed for the card's new callee by naming that callee as its own target."
