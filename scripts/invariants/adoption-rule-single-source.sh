#!/usr/bin/env bash
# Invariant `adoption-rule-single-source`: the adoption-entry decision's operative content
# lives in exactly ONE executable place, and the prose points at it.
#
# THE DEFECT THIS CLOSES, measured rather than asserted. Previously the same rule was restated in
# SEVEN places across FIVE shipped files -- SKILL.md three times, references/archaeology.md,
# commands/init-harness.md, references/init-harness.md, references/onboarding.md -- with nothing
# checking they agreed.
# A rule restated seven times is seven things that can drift apart, and the drift is invisible.
#
# THE MECHANISM HAS THREE ARMS:
#   1. exactly ONE `plc-adoption-rule` sentinel pair exists in the repository
#   2. the SHIPPED `detect` subcommand is RUN against two fixtures -- a brownfield tree and a
#      greenfield one -- rather than a second parser being written here. A second parser can be
#      green while the product is broken; this repo keeps rediscovering that.
#   3. every site on the written-down list still exists and carries a pointer at the script
#
# ARM 3'S LIST IS A WRITTEN-DOWN LITERAL, NOT A PATTERN, and that is deliberate. A repo-wide scan
# for the list's member tokens fires on `references/init-harness.md`'s language-detection table,
# which names the same manifest filenames to answer an entirely different question (which stack,
# which test command). That is a net fired at the product, a shape this repository has paid for
# before. A literal list grows only by a visible edit.
#
# TWO BLIND SPOTS, stated here rather than discovered later:
#   - a restatement written in DIFFERENT WORDS ("any Rust project counts") carries none of the
#     list's tokens and is invisible to arm 3. This catches copy-paste drift, which is the failure
#     that actually happened.
#   - a NEW file restating the rule is invisible until somebody adds it to the list below.
#
# A LISTED SITE THAT NO LONGER EXISTS IS A FAILURE, NOT A SKIP. A guard that quietly stops checking
# a location that was deleted or merged away shrinks its own coverage with nobody noticing. That
# gap was named by a cross-check review of the plan, whose only falsifier was "paste a token back".
#
# Verdicts: 0 pass, 1 the repository is wrong, 3 the check could not run (a check that could
# not run must never report as though it had).
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# THE DEFINITION TOKEN IS ASSEMBLED, NEVER WRITTEN WHOLE. If this guard spelled the sentinel out,
# it would count itself and report two definitions of a rule defined once -- the collision
# a sibling guard already documented, where quoting an anchor inflated its own count and
# reddened a guard on correct documentation. Measured here too: the first run of this check found a duplicate, and
# the second file was this one.
TOK="plc-adoption-rule"
BEG="${TOK}:begin"
END="${TOK}:end"

SCRIPT="scripts/archaeology-preflight.sh"
# The pointer is matched as a PATTERN, not as a fixed string, because the call sites are now
# anchored to the plugin root -- `bash "${CLAUDE_PLUGIN_ROOT}/scripts/archaeology-preflight.sh" detect`
# -- and a closing quote sits between the script name and its subcommand. The property this arm
# asserts is "the document points at the runnable decision", which the quoted spelling satisfies;
# a fixed-string match asserted a BYTE SEQUENCE instead, and went red on correct documents the
# moment the spelling changed. The pattern still requires the subcommand, so a document that merely
# names the script without pointing at `detect` is still a FAIL.
POINTER_RE='archaeology-preflight\.sh"?[[:space:]]+detect'
POINTER="archaeology-preflight.sh detect"   # human-readable form, used in the message only

SITES="skills/project-lifecycle/SKILL.md
skills/project-lifecycle/references/archaeology.md
commands/init-harness.md
skills/project-lifecycle/references/init-harness.md
skills/project-lifecycle/references/onboarding.md"

# The one file that USED to hold the lists and must no longer. `references/init-harness.md` is
# deliberately absent: it names the same filenames for a different question.
LIST_FREE="skills/project-lifecycle/references/archaeology.md"

[ -r "$SCRIPT" ] || { printf 'COULD NOT RUN: %s is not readable\n' "$SCRIPT" >&2; exit 3; }
command -v git >/dev/null 2>&1 || { printf 'COULD NOT RUN: git is not on PATH\n' >&2; exit 3; }

fail=0

# --- arm 1: exactly one sentinel pair ---------------------------------------
# TWO CORRECTIONS HERE, both measured, both found in review of this range.
#
# [1] THE SCAN IS NO LONGER LIMITED BY FILE EXTENSION. It used to pass `--include='*.sh'
#     --include='*.md'`, while this guard's header claims the pair is unique "in the repository".
#     A duplicate pair in a `.json` file was invisible and the guard printed `ok`. The header named
#     two blind spots and this was an undisclosed third; the cheapest honest fix is to stop having
#     it. False positives are not a concern for a token this specific, and `docs/archive/` is still
#     excluded because its bytes may not be edited.
#
# [2] `--` GOES AFTER THE OPTIONS, NOT BEFORE THEM. Writing `grep -rlF -- "$BEG" --include=...`
#     turns the `--include` flags into FILE OPERANDS -- caught here immediately, while fixing [1],
#     by the guard failing in a new way rather than by reading it.
begins="$(/usr/bin/grep -rlF --exclude-dir=.git -- "$BEG" . 2>/dev/null | /usr/bin/grep -v '/docs/archive/' | /usr/bin/wc -l | /usr/bin/tr -d ' ')"
inb="$(/usr/bin/grep -cF -- "$BEG" "$SCRIPT" 2>/dev/null || true)"
ine="$(/usr/bin/grep -cF -- "$END" "$SCRIPT" 2>/dev/null || true)"
if [ "$begins" != 1 ] || [ "$inb" != 1 ] || [ "$ine" != 1 ]; then
  printf 'FAIL expected exactly one %s block, in %s: %s file(s), %s begin / %s end\n' \
    "$TOK" "$SCRIPT" "$begins" "$inb" "$ine" >&2
  fail=1
fi

# --- arm 2: run the SHIPPED detect against two fixtures ---------------------
tmp="$(mktemp -d)" || { printf 'COULD NOT RUN: cannot create a temporary directory\n' >&2; exit 3; }
trap 'rm -rf "$tmp"' EXIT

# EVERY git call below this line must be isolated from an inherited git environment, and
# `cd` does not do that: it changes the directory and leaves GIT_DIR, GIT_INDEX_FILE and the rest
# pointing wherever the caller's did.
#
# NOT A THEORETICAL RISK. Measured: this arm, reached through the pre-push hook from a
# linked worktree, created commits with subject `fixture` ON THE BRANCH BEING PUSHED and
# replaced that branch's index with the fixture's, which made `git status` report the entire
# repository as untracked. The push was refused by the gate, so nothing reached the remote -- the
# damage was wholly local, and wholly invisible until someone read `git status`.
#
# The trigger is narrower than "a hook ran it", and that narrowness is measured rather than argued
# (throwaway repos; the real one never named):
#     GIT_DIR alone             -> the fixture commits into GIT_DIR's repo
#     GIT_DIR + GIT_INDEX_FILE  -> same
#     GIT_INDEX_FILE alone      -> harmless
#     GIT_DIR + GIT_WORK_TREE   -> harmless
#     all three                 -> harmless
# i.e. GIT_DIR set WITHOUT GIT_WORK_TREE: `git init .` then adopts the inherited GIT_DIR instead of
# creating a repository, and `add`/`commit` land there.
#
# WHAT IS STILL NOT ESTABLISHED, so that this comment does not claim more than was seen: that git
# exported exactly that shape during that push was INFERRED from the damage matching that row. It
# was not observed, because observing it means editing a `.git/hooks` file shared with the main
# checkout and with any peer session.
#
# Unset ONCE, here, rather than per call: `mk` is not the only consumer. The `detect` run below
# executes `archaeology-preflight.sh`, which makes ten git calls of its own against `--repo`, and an
# inherited GIT_DIR would make it answer about the WRONG repository -- a quiet wrong answer that
# would surface as this invariant disagreeing with itself rather than as damage.
unset GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE GIT_OBJECT_DIRECTORY \
      GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_COMMON_DIR GIT_NAMESPACE

mk() {
  local d="$1"; shift
  mkdir -p "$d"
  # stderr is CAPTURED and surfaced on failure, not discarded. The original sent both commands'
  # output to /dev/null, so while they were operating on the wrong repository they said nothing --
  # the same what-a-silent-failure-costs shape.
  local err
  if ! err="$( cd "$d" && /usr/bin/git init -q --initial-branch=main . 2>&1 \
       && /usr/bin/git config user.email t@example.invalid 2>&1 \
       && /usr/bin/git config user.name t 2>&1 )"; then
    printf 'COULD NOT RUN: could not create the fixture repository at %s: %s\n' "$d" "$err" >&2
    exit 3
  fi
  local f
  for f in "$@"; do mkdir -p "$d/$(dirname "$f")"; printf 'x\n' > "$d/$f"; done
  if ! err="$( cd "$d" && /usr/bin/git add -A 2>&1 && /usr/bin/git commit -qm fixture 2>&1 )"; then
    printf 'COULD NOT RUN: could not commit the fixture at %s: %s\n' "$d" "$err" >&2
    exit 3
  fi
}

mk "$tmp/brown" "package.json" "src/app.ts"
mk "$tmp/green" "README.md" "LICENSE"

for pair in "brown:adoption-entry" "green:new-project"; do
  d="${pair%%:*}"; want="${pair##*:}"
  got="$(/bin/bash "$SCRIPT" detect --repo "$tmp/$d" 2>&1 | /usr/bin/awk '{print $1}')"
  if [ "$got" != "$want" ]; then
    printf 'FAIL the shipped `detect` answered %s for the %s fixture; expected %s\n' \
      "${got:-<nothing>}" "$d" "$want" >&2
    fail=1
  fi
done

# --- arm 3: every listed site exists and points at the script ---------------
while IFS= read -r site; do
  [ -n "$site" ] || continue
  if [ ! -f "$site" ]; then
    printf 'FAIL listed site %s does not exist -- a vanished site is a failure, not a skip\n' "$site" >&2
    fail=1
    continue
  fi
  if ! /usr/bin/grep -qE -- "$POINTER_RE" "$site"; then
    printf 'FAIL %s refers to the adoption-entry decision but does not point at `%s`\n' "$site" "$POINTER" >&2
    fail=1
  fi
done <<EOF
$SITES
EOF

# --- arm 3b: the file that used to hold the lists must not hold them --------
hits=0
for name in package.json Cargo.toml pyproject.toml go.mod pom.xml Gemfile composer.json mix.exs; do
  if /usr/bin/grep -qF -- "$name" "$LIST_FREE" 2>/dev/null; then hits=$((hits + 1)); fi
done
if [ "$hits" -ge 3 ]; then
  printf 'FAIL %s carries %s manifest names -- the list moved back into prose\n' "$LIST_FREE" "$hits" >&2
  fail=1
fi

if [ "$fail" -ne 0 ]; then exit 1; fi
printf 'ok  adoption rule: one block in %s, the shipped `detect` is correct on both fixtures, %s sites point at it\n' \
  "$SCRIPT" "$(printf '%s\n' "$SITES" | /usr/bin/grep -c .)"
