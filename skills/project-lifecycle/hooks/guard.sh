#!/bin/sh
# project-lifecycle — PreToolUse:Bash guard.
# Enforces two rules the skill states in prose (SKILL.md "Commits & branching"):
# never the no-verify bypass flag, never push directly to main. Travels WITH the
# skill (frontmatter hook), complementing the per-project git pre-push hook.
#
# WHAT THIS IS, EXACTLY. This is a best-effort pattern match over a command
# STRING, and that is all it can ever be. Lexical analysis of a shell command line
# cannot decide what the command will do -- config, aliases, substitution and
# quoting all move the answer outside the text. The layers that actually ENFORCE
# are the git pre-push hook and the forge's branch protection, both of which see
# the resolved ref rather than the typed command. This hook is a speed bump in
# front of those, and its messages say so. Claiming otherwise was the defect this
# hook exists to fix: it reported the event it inferred, not the one it checked.
#
# DEPENDENCY ENVELOPE: jq + POSIX sh, no python3. These hooks install with the
# plugin (SKILL.md frontmatter, ${CLAUDE_PLUGIN_ROOT} paths) and run on the
# adopter's machine, so they sit inside the same envelope as close-gate.sh.
# This file used python3 `shlex` from the repo's first
# commit, i.e. it never satisfied the rule that names it -- fixed here.
#
# Exit 2 blocks the tool call; exit 0 allows. Fails OPEN on anything unparseable:
# a weird-but-legitimate command is never wrongly blocked, and the pre-push hook
# remains the un-bypassable backstop.

INPUT="$(cat 2>/dev/null || true)"
CMD="$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)"
[ -n "$CMD" ] || exit 0

# --- step 1: drop quoted spans -------------------------------------------------
# Everything inside '...' or "..." is DATA, not command structure: a commit
# message may legitimately contain --no-verify, the word main, or an && . POSIX
# word-splitting is not quote-aware (unlike the shlex this replaces), so the
# quoted spans are removed BEFORE anything is tokenized. Removing rather than
# unquoting is deliberate -- it fails toward allowing, which is the correct
# direction for a guard that is explicitly not a boundary.
# KNOWN RESIDUAL: escaped quotes (\") and nested quoting are not modelled. A
# command that defeats this is a command that also defeats reading it.
BARE="$(printf '%s' "$CMD" | sed -e "s/'[^']*'//g" -e 's/"[^"]*"//g' 2>/dev/null || true)"
[ -n "$BARE" ] || exit 0

# --- step 2: split into segments ------------------------------------------------
# `git push origin feat/x && gh pr create --base main` is TWO commands. The old
# check scanned the whole line as one flat token list, so `push` from the first
# and `main` from the second combined into a verdict about neither -- it blocked
# `gh pr create --base main` and branch-delete pushes, 8 times live during development.
# Splitting on the operator CHARACTERS (not on tokens) also handles the unspaced
# form `x&&gh`, which a token-level split silently misses.
# `$(...)` contents stay in their enclosing segment: that over-blocks rather than
# under-blocks, which is the safe direction.
SEGS="$(printf '%s' "$BARE" | tr '&|;\n' '\n\n\n\n' 2>/dev/null || true)"

deny() {
  printf '[project-lifecycle] Blocked: this looks like %s.\n' "$1" >&2
  printf 'Checked: the command text only. Open a feat/phase-* branch and a PR.\n' >&2
  printf 'The layers that actually enforce this are the git pre-push hook and branch protection --\n' >&2
  printf 'this hook is a best-effort match and does not see config, aliases or expansion.\n' >&2
  printf '(SKILL.md §Commits & branching)\n' >&2
  exit 2
}

# Is a refspec's TARGET the branch main?
#   +main          -> strip the force marker      -> main
#   :main          -> delete-by-refspec, dst side -> main
#   main:release   -> dst is release              -> NOT main
#   refs/heads/main-> fully-qualified form        -> main
# The target is the dst (right of the colon) when a colon is present, else the
# src. Matching `main` anywhere -- the previous rule -- gets main:release wrong in
# one direction and +main / refs/heads/main wrong in the other.
targets_main() {
  _r="${1#+}"                       # force marker is not part of the ref
  case "$_r" in *:*) _r="${_r#*:}" ;; esac
  _r="${_r#refs/heads/}"
  [ "$_r" = "main" ]
}

OLDIFS="$IFS"
IFS='
'
set -f
# shellcheck disable=SC2086
set -- $SEGS
set +f
IFS="$OLDIFS"

for seg in "$@"; do
  [ -n "$seg" ] || continue

  set -f
  # shellcheck disable=SC2086
  set -- $seg
  set +f
  [ $# -gt 0 ] || continue

  # Rule 1 -- the no-verify bypass flag as a real, unquoted token. Fix the
  # failing hook or linter; do not bypass it.
  for t in "$@"; do
    [ "$t" = "--no-verify" ] && deny "a --no-verify bypass -- fix the failing hook/linter instead"
  done

  # Rule 2 -- a push whose target is main. Both `git` and `push` must appear in
  # THIS segment; that alone is what killed the compound-command false positives.
  has_git=0; has_push=0
  for t in "$@"; do
    [ "$t" = "git" ] && has_git=1
    [ "$t" = "push" ] && has_push=1
  done
  [ "$has_git" = 1 ] && [ "$has_push" = 1 ] || continue

  # Walk the argv AFTER `push`, positionally. The first bare word is the remote;
  # every later bare word is a refspec. Flags that take a VALUE must consume it,
  # or the value gets read as a refspec (`git push -o "target=main"` was a live
  # false positive before the quote-stripping above, and would return without
  # this).
  # --delete/-d is a MODE for the whole segment, not a binding to the single next token. Binding
  # it to the next token missed `git push --delete origin main` / `-d origin main`: the token
  # after --delete (the remote) was eaten as the delete target, and `main` then landed in the
  # refspec slot unchecked (independent-review finding). Every bare word after the remote is a
  # refspec regardless of where --delete sits; whether it is a delete or a push, targeting main
  # is denied either way — the flag only picks the message.
  seen_push=0; seen_remote=0; want_value=0; delete_mode=0
  for t in "$@"; do
    if [ "$seen_push" = 0 ]; then
      [ "$t" = "push" ] && seen_push=1
      continue
    fi
    if [ "$want_value" = 1 ]; then want_value=0; continue; fi
    case "$t" in
      --delete|-d)      delete_mode=1 ;;
      --repo|-o|--push-option|--receive-pack|--exec)
                        want_value=1 ;;
      --repo=*|-o=*|--push-option=*|--receive-pack=*|--exec=*)
                        : ;;                       # value is attached; ignore it
      -*)               : ;;                       # any other flag: not a target
      *)
        if [ "$seen_remote" = 0 ]; then
          seen_remote=1                            # the remote, not a ref
        elif targets_main "$t"; then
          [ "$delete_mode" = 1 ] && deny "a push that deletes main"
          deny "a direct push to main"
        fi
        ;;
    esac
  done
done

# KNOWN FALSE POSITIVE -- heredoc and other inline document bodies. The hook
# receives the whole command string, so a `git commit -F - <<EOF ... EOF` whose
# BODY describes a push to main is read as a segment that performs one. Observed
# immediately: the commit message for this very rewrite was blocked by it.
# NOT FIXED HERE, on purpose. The direction is over-block, which is the safe one
# for a guard that is explicitly not a boundary; the workaround is exact and
# already the project's convention for anything long (`git commit -F <file>`,
# `gh pr create --body-file <file>`); and modelling heredocs means matching
# delimiters, `<<-`, and quoted vs unquoted forms -- new machinery for a case a
# file redirect already solves. Recorded and pinned in test-hooks.sh rather than
# left for the next person to rediscover.
#
# KNOWN FALSE NEGATIVES -- stated rather than silently carried. Each of these
# really does push main while containing no `main` token, so no amount of reading
# the command string finds them:
#   * bare `git push` while standing on main (push.default=simple|current), or
#     from any branch under push.default=matching, or via an upstream set by an
#     earlier, unrelated command (push.default=upstream)
#   * a remote.<name>.push refspec configured in git config
#   * git push --all / --mirror
#   * an alias (`git config alias.p push`, then `git p`) -- the word `push` is
#     not in the command at all
# Closing these by READING LIVE GIT CONFIG (push.default, current branch,
# remote.*.push) was considered and DELIBERATELY REJECTED: it would
# reimplement git's own ref-resolution rules inside a best-effort guard, and a
# reimplementation that drifts is exactly the infer-instead-of-check defect this
# file was rewritten to remove -- one layer deeper, and harder to see. The
# pre-push hook and branch protection resolve the real ref; that is their job.
exit 0
