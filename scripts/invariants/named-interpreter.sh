#!/usr/bin/env bash
# Invariant: no tracked shell script LAUNCHES another script with a bare `bash`.
#
# THE RULE:
#
#     Named interpreter. /bin/bash, never bare `bash` (Homebrew bash 5 may be first on PATH) and
#        never the caller's shell -- zsh and bash disagree on operators used here.
#
# WHY IT NEEDS A CHECK AT ALL. Nothing enforced it, and violations accumulated.
# No off-the-shelf linter covers this. ShellCheck's only
# interpreter-path check (SC2239) inspects a SHEBANG line and never a command invocation, so
# "adopt an existing tool" was not available and this hand-rolled check is the only enforcing
# option. https://www.shellcheck.net/wiki/SC2239
#
# SCOPE, stated so the green can be read at face value: every tracked `*.sh` in the repo
# (`git ls-files`). There is no fence, no allow-list, and no waiver mechanism -- deliberately.
# A waiver is an unenforced convention riding on top of an enforcement mechanism; rust-lang/rust
# had to add a warning because its `ignore-tidy-<check>` annotation was misspelled often enough to
# silently stop suppressing (rust-lang/rust#135421). git's own `t/check-non-portable-shell.pl` runs
# comment-blind AND waiver-less and reports no harm; this is strictly gentler than that.
#
# SHELL ONLY -- this check is about `bash` and NOTHING ELSE. The suites also invoke `git`, `grep`,
# `python3`, `jq`, `awk` and `mktemp` bare, and those are deliberately out of scope: the rule
# names the shell and gives a shell-specific reason (operator divergence between shells). Widening
# is a NEW rule needing its own evidence, not an extension of this one. Nothing this script prints
# may imply that all interpreters are named -- only that bash launchers are.
#
# WHAT COUNTS AS A COMMENT is approximated the way POSIX sh actually defines it: a `#` at the start
# of a line, or preceded by whitespace, begins one; the line is truncated there and only the
# surviving code is searched. Two consequences worth naming:
#   * a script's OWN shebang (`#!/usr/bin/env bash`) is truncated as a comment and never flagged.
#     That is correct, not incidental: the invariant governs interpreters a file LAUNCHES, not the
#     interpreter it is itself run under. The test suites keep `#!/usr/bin/env bash`.
#   * `test-hooks.sh` quotes the banned form inside comments, as deliberate NEGATIVE EXAMPLES.
#     They must never be flagged.
#
# WHY THIS FILE DOES NOT FLAG ITSELF, without an exclusion -- and how that claim was wrong once.
# The corpus is `git ls-files`, so this file is in it, and the pattern requires whitespace after the
# token. Every occurrence in this file's CODE is therefore either inside the pattern literal (where
# `[` follows the token, not whitespace) or inside a comment (truncated). No exclusion, no fence.
#
# The first version of this comment asserted exactly that -- and it was FALSE when written. The
# check had only ever been run while this file was still UNTRACKED, so `git ls-files` did not list
# it and it was never in its own corpus. The first run after `git add` flagged two lines of its own
# failure message, which quoted the rule verbatim and so contained ` bash ` twice. A claim about the
# real object, verified against a proxy.
#
# The fix was NOT to exempt this file and NOT to reword English until a grep is satisfied: the rule's
# verbatim text lives in the header above, and the failure message CITES it
# rather than reprinting it. An enforcer that cannot survive its own rule is evidence about the
# rule; an enforcer exempted from it is evidence about nothing.
#
# WHAT THIS WOULD MISS (lexical, all of it -- named rather than implied):
#   * indirection -- `B=bash; $B x`, `$INTERP x`, `exec "$(command -v bash)"`. The token never
#     appears contiguously before its argument, so no grep of any shape sees it. Deliberate evasion
#     is not the threat; DRIFT is, and drift arrives spelled out.
#   * a `#` inside a quoted string that swallows a real invocation to its right, e.g.
#     `eval "echo '#' ; bash x"`. The truncation rule is per-line and quote-blind.
#   * a bare launcher inside a HEREDOC BODY that is itself shell source (a fixture writing a script
#     it will later run). The body's lines are ordinary lines to this check, so such a launcher IS
#     flagged if it looks like one and IS missed if the heredoc is quoted in a way that puts a `#`
#     to its left. This file cannot tell a heredoc body from surrounding code -- `test-hooks.sh`
#     is a live reminder that even a human reader mistakes `EOF'` for a heredoc terminator when it
#     is really closing a single-quoted string opened two lines earlier.
#   * untracked files. `git ls-files` is the corpus; a violation in an untracked script is invisible
#     until it is added, which is the moment the check wants to fire anyway. This one is not
#     theoretical: this file was written, run, and declared self-clean while still untracked, and
#     the claim was wrong (see "WHY THIS FILE DOES NOT FLAG ITSELF" above).
#   * SHELL LIVING OUTSIDE A `*.sh` FILE -- a JSON manifest string, a CI YAML `run:` block, a settings hook.
#     That is a different corpus, and this check does not see it.
#
# THE ONE STRUCTURAL EXCLUSION, and why it is not a waiver. A launcher's first argument is never
# `+`, so `bash[[:space:]]+\+` cannot be an invocation. This exists because the repo says
# "envelope is bash + git + jq + coreutils" in two runtime OUTPUT strings
# (scripts/invariants/gate-jq-only-envelope.sh and
# skills/project-lifecycle/hooks/test-context-floor-contract.sh), where `bash` is a noun in a
# sentence. Those are not comments and CANNOT be moved into one -- they are text a user reads when a
# check fails -- so the "just move the sentence into a comment" escape this file offers below does
# not reach them. This exclusion is global, structural, and stated; it is not a per-site annotation,
# which is the thing this file refuses.
#
# REJECTED, and rejected on measurement rather than taste: restricting the match to "command
# position" (line start, or after `| ; & ( {` / backtick / `exec` / an env assignment). It looks
# like the principled fix and it is strictly worse -- it loses REAL launchers
# (`$( … )` bodies, continuation lines, multi-prefix env forms) to remove a few false ones. Trading
# false negatives for fewer false positives is the wrong direction for a check whose entire job is to
# not miss anything.
#
# WHAT THIS WOULD FALSELY FLAG:
#   * a non-launching mention in code, e.g. `command -v bash |` or `echo "run bash now"` -- the
#     token followed by whitespace reads as executable because the truncation rule understands
#     comments, not quoting or command semantics. Cost accepted: the false direction is a loud,
#     one-line, trivially-fixed failure, whereas the alternative is a shell parser in a file whose
#     whole value is being a few lines of awk that run in milliseconds.
#   * a lowercase variable spelled `$bash ` -- same class, same cost.
#
# Envelope: bash + git + grep + awk. No python3, no jq.
set -uo pipefail

RULE_SRC="scripts/invariants/named-interpreter.sh"

# Corpus: every tracked shell script. NO fence.
FILES="$(git ls-files -- '*.sh' 2>/dev/null || true)"

# Empty corpus is a hard FAIL, never a vacuous pass. An empty set compared equal to an empty set is
# how scripts/invariants/ledger-contract-sync.sh once passed while checking nothing; that lesson is
# paid for and does not need paying twice.
if [ -z "$FILES" ]; then
  echo "FAIL named-interpreter: corpus is EMPTY -- 'git ls-files -- *.sh' matched nothing"
  echo "  -> a check that scans no files reports success about nothing. Either this is not a git"
  echo "     work tree, or the glob is broken. Both are failures, not passes."
  exit 1
fi

# Print `file:line: text` for every line whose CODE launches a bare bash.
# The character class before the token excludes `/` so `/bin/bash` -- the required form -- does not
# match, and excludes alphanumerics/`_`/`.`/`-` so `BASH_VERSION`, `mybash` and `foo.bash` do not.
HITS="$(printf '%s\n' "$FILES" | while IFS= read -r f; do
  [ -r "$f" ] || continue
  awk -v F="$f" '
    {
      code = $0
      sub(/^[[:space:]]*#.*$/, "", code)
      sub(/[[:space:]]#.*$/, "", code)
      if (code ~ /(^|[^[:alnum:]_.\/-])bash[[:space:]]/ &&
          code !~ /(^|[^[:alnum:]_.\/-])bash[[:space:]]+\+/) print F ":" NR ": " $0
    }
  ' "$f"
done)"

if [ -n "$HITS" ]; then
  N="$(printf '%s\n' "$HITS" | grep -c '')"
  echo "FAIL named-interpreter: $N bare \`bash\` launcher(s) in tracked shell scripts"
  printf '%s\n' "$HITS"
  echo "  -> The rule, the long form of why, and what this check misses are in the header of"
  echo "     $RULE_SRC."
  echo "     Write the interpreter out: \`/bin/bash \"\$X\"\`, inline at the call site. That is what the"
  echo "     context-floor contract suite already does, including the rows that deliberately shadow PATH."
  echo "     This check covers the SHELL only -- bare \`jq\`, \`python3\`, \`git\` etc. are out of its scope"
  echo "     by design and their absence from this output is not a statement about them."
  exit 1
fi

echo "ok named-interpreter: no bare \`bash\` launcher in any tracked shell script (shell only; other interpreters are not in this check's scope)"
