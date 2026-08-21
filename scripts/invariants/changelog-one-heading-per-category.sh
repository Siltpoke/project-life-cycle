#!/usr/bin/env bash
# INVARIANT — within any one '## ' section of CHANGELOG.md, no '### ' heading appears twice.
#
# WHY. `commands/release.md` defines one heading per category per section, and `[Unreleased]`
# can end up with `### Added` and `### Fixed` twice each — even where the release command states the
# rule. Entries then land under whichever copy the writer scrolled to first. A drain that
# rewrites the file moves the line numbers
# while THE SHAPE STAYS: the defect does not fix itself,
# and that is the argument for a machine check over another manual
# merge.
#
# SCOPE, stated rather than implied:
#   * EVERY '## ' section of CHANGELOG.md, not just '[Unreleased]'. A check scoped to
#     '[Unreleased]' goes silently vacuous the moment `/release` renames that heading.
#   * ONLY CHANGELOG.md. `docs/archive/**` is out: the retention policy forbids hand-editing archived
#     content, so a red there would be UNFIXABLE BY POLICY — which converts a gate you clear into
#     a gate you bypass. `changelog.d/` is out: where it does not exist, a check
#     over an absent path is a vacuous pass.
#   * EVERY '### ' heading counts, not a whitelist of the six Keep-a-Changelog names.
#     A repeated `### Fixes` (typo) is the same defect and a whitelist waves it through.
#
# CASE IS NOT FOLDED. '### Fixed' and '### fixed' are two distinct headings and neither is
# reported as a duplicate of the other. That is deliberate: catching that pair is a DIFFERENT
# check (canonical spelling), and folding it in here would make one failure message ambiguous
# about which rule fired.
#
# FENCED BLOCKS ARE EXCLUDED — the retention drain has already hit this exact class, so it is
# designed in up front. Stated blind spots, all three
# MEASURED rather than imagined:
#   * PER-LINE and QUOTE-BLIND. The toggle flips on any line whose first non-space run (at most
#     three spaces, see below) is ``` or ~~~; it does not model nested fences of differing lengths,
#     nor a fence inside a quoted string. Same approximation, same accepted cost, as
#     gate-jq-only-envelope.sh's comment-truncation rule.
#   * HTML BLOCKS ARE NOT MODELLED, and this produces a FALSE RED. In CommonMark a "<div>" opens an
#     HTML block that runs to the next blank line, so a "### Added" inside it is raw text, not a
#     heading — this script counts it. Concrete input, measured exit 1:
#         ## S / (blank) / ### Added / (blank) / <div> / ### Added / </div>
#     NOT FIXED, deliberately: closing it means tracking CommonMark's seven HTML-block start
#     conditions, i.e. a parser, in a file whose whole value is being fast and greppable. The
#     failure direction is the survivable one — a loud red on a file the author can edit, not a
#     silent pass.
#     scripts/test_changelog_headings.py pins it as a LIMIT so it stays a decision.
#   * TABS ARE NOT INDENT. The three-space fence bound counts spaces only.
#
# NO VACUOUS PASS. A missing file, an unreadable file, and a file with zero '## ' sections are all
# hard FAILs, never a silent 0. An empty set comparing equal to an empty set is a pass that
# checks nothing.
#
# Envelope: bash + grep + awk. No python3 — an invariant proving the gate needs no extra
# interpreter must not need one. NOTE, and this is a real limit rather than a boast:
# gate-jq-only-envelope.sh reads three NAMED files and this is not one of them, so nothing
# standing enforces that sentence. scripts/test_changelog_headings.py asserts it for this file.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# The target is an EXPLICIT ARGUMENT, never an environment variable. An env override (the old
# `PLC_CHANGELOG_PATH`, so fixtures could redirect it) has a demonstrated consequence:
# any ambient environment could point this at a
# README, get `exit 0` because a README has `## ` sections, and the close gate would print
# `✓ invariant 'changelog-one-heading-per-category' holds` while `CHANGELOG.md` went unread.
# The three guards below (regular file / readable / has sections) do not stop that, because the
# decoy satisfies all three.
#
# The answer: AN ENVIRONMENT VARIABLE IS
# NOT A CAPABILITY. Deleting the feature beats lengthening the token — an argument has to be passed
# by whoever invokes the script, and the only invocation that matters is the one written into the
# tracked `.claude/close-gate.json`, where it is visible in every diff.
# `scripts/test_changelog_headings.py::test_the_old_env_override_is_inert` keeps it deleted.
TARGET="${1:-$HERE/../../CHANGELOG.md}"
NAME="changelog-one-heading-per-category"

if [ ! -f "$TARGET" ]; then
  echo "✗ $NAME: '$TARGET' is not a regular file — refusing to pass over a file that is not there"
  exit 1
fi
if [ ! -r "$TARGET" ]; then
  echo "✗ $NAME: '$TARGET' is not readable"
  exit 1
fi

awk -v name="$NAME" '
  # --- measure the indent first; awk runs rules in source order, so this precedes every pattern.
  {
    nlead = 0
    while (substr($0, nlead + 1, 1) == " ") nlead++
    rest = substr($0, nlead + 1)
  }

  # --- fenced-block toggle. Checked BEFORE any heading rule so a fence line is never a heading.
  #
  # AT MOST THREE SPACES OF INDENT. Four or more makes the line INDENTED CODE CONTENT, not a fence,
  # and treating it as one is the dangerous direction: the toggle flips, and every real heading
  # after it is skipped. Concrete input, which returned exit 0 before
  # this bound existed — two genuine duplicate headings, silently passed:
  #     ## S / (blank) / ␣␣␣␣``` / ### Added / (blank) / ### Added / ␣␣␣␣```
  # Tabs are not counted as indent here; a tab-indented fence is out of scope and stated rather
  # than implied.
  nlead <= 3 && (rest ~ /^```/ || rest ~ /^~~~/) { infence = !infence; next }
  infence { next }

  # "^## " cannot match "### Added": the third character must be a space.
  /^## / {
    section = $0
    sub(/[[:space:]]+$/, "", section)
    sub(/[[:space:]]+#+$/, "", section)
    nsections++
    next
  }

  /^### / {
    heading = $0
    sub(/[[:space:]]+$/, "", heading)
    # --- strip a CLOSING ATX SEQUENCE. "### Added ###" and "### Added" are the SAME heading once
    # rendered, and keying them separately let a real duplicate pass (exit 0, measured). CommonMark
    # requires the closing run to be preceded by whitespace, which is exactly what this matches --
    # so a heading legitimately ENDING in a hash, "### C#", is untouched.
    sub(/[[:space:]]+#+$/, "", heading)
    sec = (section == "" ? "(before any \"## \" section)" : section)
    key = sec SUBSEP heading
    if (!(key in count)) {
      # First-seen order, because awk array iteration order is unspecified and a failure message
      # that reorders between runs is a failure message nobody can diff.
      order[++n] = key
      secof[key] = sec
      headof[key] = heading
      lines[key] = NR
    } else {
      lines[key] = lines[key] ", " NR
    }
    count[key]++
    next
  }

  # --- empty-set guard: a file with no sections is a FAIL, not a vacuous pass.
  END {
    if (nsections == 0) {
      printf "✗ %s: no \"## \" section found — a check over nothing is not a pass\n", name
      exit 1
    }
    bad = 0
    for (i = 1; i <= n; i++) {
      key = order[i]
      if (count[key] > 1) {
        bad = 1
        printf "✗ %s: %s repeats %s (%d times, lines %s)\n", \
          name, secof[key], headof[key], count[key], lines[key]
      }
    }
    if (bad) exit 1
    exit 0
  }
' "$TARGET"
rc=$?

if [ "$rc" -ne 0 ]; then
  echo "  file: $TARGET"
  echo "  rule: within one \"## \" section, each \"### \" heading may appear at most once"
  exit 1
fi

echo "ok $NAME: every \"### \" heading is unique within its \"## \" section ($TARGET)"
exit 0
