#!/bin/bash
# plc-python.sh -- run a WORKING Python 3, or say plainly that there is none.
#
# WHY THIS EXISTS. On a default Windows install `python3` is an App Execution Alias: a stub
# that is not an interpreter. Two shapes are reported in the wild -- one exits non-zero with
# a "install from the Microsoft Store" message, one exits 0 and prints nothing at all. A
# caller that tests only the exit code passes straight through the second. Every `python3`
# written into this repo's command docs went to such a stub unchecked.
#
# ORDER IS NOT SELECTION. Every candidate must pass the probe; being earlier only decides who
# is asked first. In particular there is deliberately NO branch on whether a resolved path
# contains `WindowsApps`: a genuine Store-installed Python lives there too, so that substring
# yields a false rejection. pipx uses it as a trigger for a real probe, never as the verdict.
#
# BUILTINS ONLY ON THE SELECTION PATH. No `sed`, no `grep`, no `tr`. The tests run this with
# PATH set to a fixture directory and nothing else, so reaching for an external tool would
# break rows that are meant to prove rejection -- and, worse, would make this script need the
# very environment it exists to survive.
#
# THE ONE EXCEPTION, NAMED RATHER THAN HIDDEN: hook mode's rate limit needs the wall clock,
# and `date` is not a bash builtin (`$EPOCHSECONDS` and `printf '%(%s)T'` are bash 5 / 4.2,
# while this must run under the bash 3.2 that ships with macOS). When `date` cannot be run,
# the throttle CANNOT be evaluated, and it then WARNS rather than going quiet -- a throttle
# that suppressed on ignorance would be a guard reporting enforcement it is not performing,
# the shape already closed elsewhere. R21 pins that direction.
#
# Two modes:
#   direct  (no flag)  what a command doc calls. `exec`s the interpreter; invisible on
#                      success, `COULD NOT RUN` on stderr and exit 3 on failure.
#   --hook  (FIRST arg, stripped before forwarding) what the generated Stop entry calls.
#                      Runs rather than `exec`s, and exits 0 on every path.
#
# Exit codes:
#   0  direct: the selected interpreter ran (its own status is passed through by `exec`)
#   0  hook: always, on every path -- selected, failed, warned or throttled
#   3  direct only: no candidate passed the probe -- message on stderr, nothing on stdout
set -u

# `--hook` must be the FIRST argument. It is this script's own flag, never the
# interpreter's, and is stripped before anything is forwarded (R20).
HOOK=0
if [ "${1-}" = "--hook" ]; then
  HOOK=1
  shift
fi

# Rate-limit state for hook mode. The Stop hook fires after every assistant turn, so an
# un-throttled warning repeats forever and becomes noise the user silences by removing the
# hook -- `skills/project-lifecycle/hooks/guard.sh:63-67` records exactly that cost for its
# own notice.
#
# KEYED BY A TIME WINDOW, NOT BY SESSION, and the claim is narrowed to match the mechanism
# rather than the other way round: a per-session key needs the session id, the id arrives
# only in the Stop payload on stdin, and the stdin-passthrough requirement forbids consuming it. Both
# could not hold. The cost of the substitute is stated: two different sessions inside one
# window see one warning, so the guarantee is "not endless", never "once per reader".
WARN_WINDOW="${PLC_PYTHON_WARN_WINDOW-21600}"   # 6h
WARN_MARKER="${PLC_PYTHON_WARN_MARKER-${HOME-/tmp}/.claude/plc-session-data/.plc-python-warn}"

# hook_should_warn -- returns 0 (warn) or 1 (stay quiet), and records the emission.
hook_should_warn() {
  now="$(date +%s 2>/dev/null || true)"
  case "$now" in
    ''|*[!0-9]*)
      # No readable clock. Warn; never suppress on ignorance. See R21.
      return 0
      ;;
  esac

  last=""
  if [ -r "$WARN_MARKER" ]; then
    # `read` is a builtin; `cat` would be one more external dependency for no gain.
    read -r last < "$WARN_MARKER" 2>/dev/null || last=""
  fi

  case "$last" in
    ''|*[!0-9]*) last=0 ;;   # absent or corrupt marker == never warned
  esac

  if [ "$last" -le "$now" ] && [ $((now - last)) -lt "$WARN_WINDOW" ]; then
    return 1
  fi

  # Record the emission. A marker that cannot be written means the next call warns again,
  # which is the same fail-toward-speaking-up direction as the unreadable clock.
  mkdir -p "${WARN_MARKER%/*}" 2>/dev/null || true
  printf '%s\n' "$now" > "$WARN_MARKER" 2>/dev/null || true
  return 0
}

# The probe prints the interpreter's own version and nothing else, rather than a bespoke
# marker: inventing a string would contradict this project's rule
# to port proven approaches. This is what pipx (`interpreter.py`) and token-optimizer
# (`install.sh _resolve_python`) actually do.
PROBE='import sys; sys.stdout.write("%d.%d" % sys.version_info[:2])'

# Exact match, so empty output cannot pass. A loosened pattern would re-admit the silent stub,
# which is the whole hazard. Cost, accepted and named: stdout noise before the probe's write
# (a sitecustomize.py, a venv banner) falsely rejects a good interpreter -- so the failure
# message prints what was actually received, rather than leaving it a mystery.
VERSION_RE='^[0-9][0-9]*\.[0-9][0-9]*$'

SELECTED=""
# 1 when SELECTED was accepted as ONE whole value (an executable whose path may contain
# spaces) rather than as a word split. Without this flag the final `exec $SELECTED` --
# unquoted, which the split case needs -- re-splits the whole value and undoes the
# selection. That is not hypothetical: it is what R18b caught on its first run.
SELECTED_WHOLE=0
REPORT=""

note() {
  if [ -n "$REPORT" ]; then
    REPORT="$REPORT; "
  fi
  REPORT="$REPORT$1"
}

# try <word>... -- probe one candidate. Sets SELECTED and returns 0 on acceptance.
try() {
  # The label brackets EACH WORD separately, so the failure message shows what the value
  # actually split into: `[python3]`, `[py] [-3]`, and -- the case this exists for --
  # `[/opt/sp] [ace/py]` for PLC_PYTHON='/opt/sp ace/py'. A `"$*"` join printed back something
  # byte-identical to what the user typed, so the message said "not found" about a file that
  # does exist and hid the only fact that would have explained it. The comment further down
  # promised this behaviour while the code did not have it; the promise is kept and the code
  # fixed, rather than the promise quietly dropped. Found by review, not by a test.
  # `candidate_words` is what gets RUN; `candidate_label` is what gets PRINTED. They were one
  # variable until the bracketing landed, and `exec` promptly tried to run a program called
  # `[apy]`. The new precedence rows caught it on the first run, which is the whole argument
  # for having added them.
  candidate_words="$*"
  candidate_label=""
  for word in "$@"; do
    if [ -n "$candidate_label" ]; then
      candidate_label="$candidate_label "
    fi
    candidate_label="$candidate_label[$word]"
  done
  candidate_name="$1"

  if ! command -v "$candidate_name" >/dev/null 2>&1; then
    note "$candidate_label (not found)"
    return 1
  fi

  # `< /dev/null` is load-bearing, not hygiene: in hook mode this process is handed the Stop
  # payload on stdin, and a probe inheriting stdin could consume it before the real
  # interpreter reads it.
  probe_out="$("$@" -c "$PROBE" </dev/null 2>/dev/null)"
  probe_rc=$?

  if [ "$probe_rc" -ne 0 ]; then
    note "$candidate_label (exit $probe_rc)"
    return 1
  fi

  if [[ ! $probe_out =~ $VERSION_RE ]]; then
    note "$candidate_label (unexpected output: '$probe_out')"
    return 1
  fi

  if [ "${probe_out%%.*}" -lt 3 ]; then
    note "$candidate_label (Python $probe_out, need 3 or newer)"
    return 1
  fi

  SELECTED="$candidate_words"
  return 0
}

# Candidates, in ask-first order:
#   1. $PLC_PYTHON  explicit override, and the escape hatch for a broken machine
#   2. $PYTHON      the conventional var node-gyp also honours
#   3. py -3        the Windows launcher; resolves through the registry, routing around the
#                   alias entirely. Two tokens, which is why candidates are shell words.
#   4. python3
#   5. python       reachable, and therefore the reason the major-version floor exists
#
# An override that is SET BUT FAILS falls through rather than being fatal: a stale $PYTHON in
# a shell profile is far more common than a deliberate one, and making it fatal would turn a
# forgotten export into a hard outage. It is still named in the failure message as tried.
#
# Values are shell words, so `py -3` and PLC_PYTHON="py -3" both work. The limitations that
# follow are stated rather than papered over. The first was already written down; the other
# three were found by review, and the list used to stop after the first -- which made it
# narrower than the truth:
#   1. A path containing SPACES now WORKS, and this entry is kept rather than deleted because
#      it said the opposite for most of this phase. It used to read: *"A path containing
#      SPACES cannot be passed. `PLC_PYTHON='/opt/sp ace/py'` splits into two words. The
#      failure message brackets each word (`[/opt/sp] [ace/py]`) so the cause is visible."*
#      That was true until the whole-value attempt below existed. Each candidate is now tried
#      ONCE as a single word before it is split, so an interpreter at `/opt/sp ace/py` or
#      `C:\Program Files\Python312\python.exe` resolves. What survives of the old entry: a
#      spaced value that resolves to NOTHING is still reported as the words it split into
#      (R18), which is what makes a typo in such a path readable instead of mysterious.
#   2. PATHNAME EXPANSION applies. `PYTHON='/opt/py*'` matching two files makes the second an
#      argument to the first; the probe then reports a plain `(exit N)` and nothing names the
#      glob. A value with no match stays literal and is reported "not found".
#   3. EXTRA WORDS ARE EXECUTED. The value is a command line, not a filename. A value of the
#      form `<interpreter> <script-that-prints-a-version>` would pass the probe and then be
#      run. This is inherent to "an environment variable chooses the executable" and is not a
#      new hole -- whoever sets it already controls the environment -- but "spaces" was the
#      only word the docs used for it, and that was too small.
#   4. QUOTE CHARACTERS ARE LITERAL. `PLC_PYTHON='"/opt/sp ace/py"'` does not rescue case 1;
#      the quotes become part of the first word. There is no supported quoting form.
for candidate in "${PLC_PYTHON-}" "${PYTHON-}" "py -3" "python3" "python"; do
  [ -n "$candidate" ] || continue

  # WHOLE VALUE FIRST, THEN THE SPLIT. The value is tried once as a SINGLE word before it is
  # split, which is what makes `PLC_PYTHON='C:\Program Files\Python312\python.exe'` work --
  # the commonest shape of the commonest override, on the one platform this script exists for.
  # Until this existed, such a path was split in two and reported "not found" about a file
  # that does exist.
  #
  # `py -3` is untouched, and that is measured rather than hoped: nothing resolves under the
  # single name `py -3`, so this attempt fails and the split below runs. R15 pins the launcher
  # and R18b pins the spaced path, so the two cannot be silently traded for each other.
  #
  # AN EARLIER VERSION GUARDED THIS WITH `[ -x "$candidate" ]` AND THE COMMENT CALLED THAT "a
  # discriminator, not a heuristic". A mutation deleting the guard left every row green,
  # which is the measurement that says it was not load-bearing: `try` already resolves the
  # name itself. The guard was removed rather than the claim softened, because an unnecessary
  # test that a comment describes as essential is the claim-wider-than-mechanism shape this
  # phase has now caught -- here, in code written minutes earlier.
  #
  # WHAT REMAINS TRUE, and still written down: a value that is neither resolvable whole nor a
  # clean word split (a glob, a quoted string, trailing extra words) behaves as the numbered
  # list above describes.
  if try "$candidate"; then
    SELECTED_WHOLE=1
    break
  fi

  # Deliberately unquoted: this is the word split described above.
  # shellcheck disable=SC2086
  if try $candidate; then
    break
  fi
done

if [ -n "$SELECTED" ]; then
  if [ "$HOOK" -eq 1 ]; then
    # RUN, never `exec`, and then exit 0 unconditionally, because
    # `commands/init-harness.md:234` documents the generated Stop entry as always exiting 0.
    # The consequence is stated rather than left to be discovered: the interpreter's own
    # status is DISCARDED here, so hook mode guarantees "speaks up when the interpreter is
    # missing" and NOT "speaks up when the script fails". Today that loses nothing --
    # `save_session.py` returns 0 anyway -- and the guarantee is deliberately not widened
    # past what the mechanism does. R19 pins it.
    if [ "$SELECTED_WHOLE" = 1 ]; then
      "$SELECTED" "$@"
    else
      # shellcheck disable=SC2086
      $SELECTED "$@"
    fi
    exit 0
  fi
  # `exec` so the exit code and all three streams pass through byte-for-byte. On an
  # unmodified PATH this script must be invisible; R7 pins that.
  if [ "$SELECTED_WHOLE" = 1 ]; then
    exec "$SELECTED" "$@"
  fi
  # shellcheck disable=SC2086
  exec $SELECTED "$@"
fi

if [ "$HOOK" -eq 1 ]; then
  if hook_should_warn; then
    # HAND-WRITTEN JSON IS SAFE **HERE** AND WOULD NOT BE SAFE GENERALLY: every byte below is
    # a fixed literal in this file. `$REPORT` is deliberately NOT interpolated, although it is
    # the most informative string available -- it contains whatever a candidate printed to
    # stdout, which may carry quotes, backslashes, newlines and control characters of any
    # length, and a `printf '{"systemMessage":"%s"}'` of that produces invalid JSON on the
    # first quote. The same constraint `skills/project-lifecycle/hooks/guard.sh:71-73` records
    # for its own envelope. R5b pins it: a candidate whose output carries a quote and a
    # newline must not appear in this payload. The detailed diagnosis stays reachable by
    # running the same command without `--hook`, and the message says so.
    printf '%s' '{"systemMessage":"project-lifecycle: no working Python interpreter was found, so the session digest was NOT saved. On Windows, `python3` is often an App Execution Alias rather than an interpreter. Set PLC_PYTHON to a real interpreter, or install Python and reopen the shell. For the full list of what was tried and why each was rejected, run scripts/plc-python.sh without --hook. This notice is rate limited; it will not repeat for a while."}'
  fi
  # Exit 0 on every path, warned or throttled. A Stop hook that exits non-zero is a different
  # failure for the user than the one being reported.
  exit 0
fi

# Nothing on stdout: callers parse it. The message names each candidate AND how it failed,
# which is the half that makes it actionable rather than decorative.
printf 'COULD NOT RUN: no working Python interpreter. Tried: %s.\n' "$REPORT" >&2
exit 3
