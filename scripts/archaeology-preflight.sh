#!/usr/bin/env bash
# archaeology-preflight -- what the brownfield archaeology pass looks at BEFORE it drafts anything.
#
# WHY THIS IS A SCRIPT AND NOT ANOTHER PARAGRAPH. The archaeology pass was entirely prose. On a
# real brownfield repository the pass can draft confident documents from a stale checkout --
# anchoring on `git ls-files` of whatever branch happens to be checked out -- and read-only agents
# can cross the evidence boundary their own prompts state. A fourth prose rule, added to a pass
# whose prose rules do not bind, patches at the layer that fails.
#
# EXIT CODES, AND THE THIRD ONE IS THE POINT:
#   0  no finding                 -> the pass proceeds to its three read-only agents
#   1  finding, report printed    -> the pass STOPS. Zero drafts. The human decides.
#   3  the check could not run    -> the pass STOPS, and says it could not run.
# 3 exists because a check that could not run must never report as though it had. A
# pre-flight that exits 0 because it failed to start is this phase's own defect facing the other way.
# THE 3 PATH IS REACHED BY AN EXPLICIT TRAP, NOT BY FALLING THROUGH `set -e`: under a bare `set -e`
# an uncaught error exits with the failing command's status, which is usually 1 -- silently
# reclassifying "the check never ran" as "the check ran and found something", with no report body.
#
# THIS SCRIPT NEVER WRITES. No fetch, no checkout, no switch, no reset, no `remote set-head`. It is
# read by strangers' repositories and the only thing it is allowed to change is stdout. Where it
# cannot answer a question it says so and, where a remedy exists, prints it for the human to run.
#

set -euo pipefail

PROG="archaeology-preflight"

# The explicit could-not-run path. Anything unexpected lands here as 3, never as 1.
_trap_could_not_run() {
  local rc=$?
  printf '%s: COULD NOT RUN (unexpected failure, status %s)\n' "$PROG" "$rc" >&2
  exit 3
}
trap _trap_could_not_run ERR

die_could_not_run() {
  printf '%s: COULD NOT RUN -- %s\n' "$PROG" "$1" >&2
  exit 3
}

usage() {
  cat <<'USAGE'
usage: archaeology-preflight.sh check [--repo <path>]

  check   report what the archaeology pass is about to read, and stop it if anything is off.
          exit 0 = no finding, 1 = finding (the pass must not draft), 3 = could not run.

  detect  answer the adoption-entry decision: `adoption-entry` or `new-project`, and why.
          exit 0 either way -- it reports a classification, it does not pass or fail.
USAGE
}

# ---------------------------------------------------------------------------
# git helpers. Every one of them is read-only, and the intentional-failure ones
# carry `|| true` so a legitimate "this ref does not exist" never trips the ERR trap.
# ---------------------------------------------------------------------------

g() { /usr/bin/git -C "$REPO" "$@"; }

# ---------------------------------------------------------------------------
# The existing-artifact scan. Three tiers, first hit wins per directory, and every reported
# row names the tier that fired -- the tier is how a human weighs the row, and a path printed
# without one asks the reader to re-derive the check's own reasoning.
#
# IT READS TRACKED FILES ONLY (`git ls-files`), the same rule the detection contract already uses:
# vendored and installed directories are normally untracked, and a scan that counted them would
# report somebody else's ADRs as this project's.
#
# BOUNDARY, stated where it is implemented: a path containing a newline is not handled. `git
# ls-files` quotes such paths and this scan would read the quoted form. That is a real gap, it is
# rarer than the gap of not scanning, and it is written here rather than discovered later.
# ---------------------------------------------------------------------------

# <!-- plc-adoption-rule:begin -->
# THE ADOPTION-ENTRY DECISION. This block is the ONLY place its operative content lives.
#
# Previously the same rule was restated in seven places across five shipped files, with nothing
# checking they agreed. Prose may describe the SHAPE of the decision and must point here for the
# lists; `scripts/invariants/adoption-rule-single-source.sh` enforces that against a written-down
# list of sites, and states its own two blind spots in its header.
#
# The decision: the adoption entry fires when BOTH hold --
#   1. both plc anchors are absent, each counting as present at EITHER conventional location;
#   2. substantial existing code: a recognised manifest, OR >=1 recognised source file outside the
#      whitelist.
# Tracked files only (`git ls-files`); manifests match at the repository ROOT, the glob manifests and
# the source-extension check match at ANY depth. No commit-count or LOC threshold: zero industry
# precedent, and any numeric threshold misclassifies imported mature code (1 commit, 50k LOC).
ADOPTION_ANCHORS="RESUME.md docs/RESUME.md docs/iteration-journal.md iteration-journal.md"
ADOPTION_MANIFESTS="package.json Cargo.toml pyproject.toml go.mod pom.xml Gemfile composer.json mix.exs pubspec.yaml requirements.txt setup.py"
ADOPTION_MANIFEST_GLOBS="build.gradle* *.csproj *.sln"
ADOPTION_SOURCE_EXTS="ts tsx js jsx mjs py rs go java kt swift dart c h cpp hpp cs rb php ex exs scala clj sh sql vue svelte"
ADOPTION_WHITELIST=".git .hg .gitignore .gitattributes .DS_Store Thumbs.db .travis.yml .gitlab-ci.yml .idea .vscode .zed .claude .cursor docs/ LICENSE README.md mkdocs.yml npm-debug.log yarn-error.log yarn-debug.log *.iml .yarn"
# <!-- plc-adoption-rule:end -->

# ---------------------------------------------------------------------------
# THE SIGNATURE TABLE. One block, read by BOTH the scan and the floor the report prints.
#
# This is not tidiness. The floor is the sentence that tells a reader what this check CANNOT see,
# and a hand-copied floor goes stale the moment a signature is added -- it then either over-claims
# safety or warns about a gap that was closed, with nothing catching the drift. A future change is expected to
# add signatures. So the floor is generated from these four values and a test asserts the two agree.
# ---------------------------------------------------------------------------
ADR_MARKERS=".adr-dir .log4brains.yml adr.config.json"
ADR_DIR_TOKENS="adr decision decisions"
ADR_FILENAME_SHAPE="NNNN-*.md"
ADR_FINGERPRINTS="## Consequences|## Decision Outcome|## Considered Options"

# The roadmap half has NO marker file, NO stable filename convention and NO stable content shape --
# none of the three techniques above transfers. So it is matched by NAME only and reported as the
# weak signal it is. That is the terminal state until someone finds a structurally different technique,
# not a debt.
ROADMAP_NAME_TOKEN="roadmap"

fingerprint_re() { printf '^## (%s)[[:space:]]*$' "$(printf '%s' "$ADR_FINGERPRINTS" | /usr/bin/sed 's/## //g')"; }

floor_text() {
  printf 'Signatures checked: marker files (%s); directories whose name contains %s and\n' \
    "$(printf '%s' "$ADR_MARKERS" | /usr/bin/sed 's/ /, /g')" \
    "$(printf '%s' "$ADR_DIR_TOKENS" | /usr/bin/sed 's/ /\//g')"
  printf 'hold at least one %s; content fingerprints (%s) in a directory holding at least two.\n' \
    "$ADR_FILENAME_SHAPE" "$ADR_FINGERPRINTS"
  printf 'A project using none of these is invisible to this check -- including one that keeps\n'
  printf 'exactly ONE record in a directory named none of those words. "Nothing matched" is a\n'
  printf 'statement about this check, never about your repository.\n'
  printf 'Roadmaps are matched by FILENAME only: whether one is maintained was not checked.\n'
}

lower() { printf '%s' "$1" | /usr/bin/tr '[:upper:]' '[:lower:]'; }

scan_artifacts() {
  local tmp base dir f hit
  tmp="$(mktemp -d)" || die_could_not_run "cannot create a temporary directory"

  g ls-files > "$tmp/all" 2>/dev/null || true
  : > "$tmp/reported"

  # --- tier 1: tool-written marker files ------------------------------------
  # These are written by adr-tools, log4brains and dotnet-adr at the repository root. Root only:
  # that is where the three tools put them, and widening the search would turn a high-precision
  # signal into a guess.
  if [ -f "$REPO/.adr-dir" ]; then
    hit="$(/usr/bin/head -1 "$REPO/.adr-dir" 2>/dev/null || true)"
    [ -n "$hit" ] || hit="(.adr-dir is empty)"
    finding_lines+=("[decisions] ${hit}   evidence tier: marker (.adr-dir)")
    printf '%s\n' "$hit" >> "$tmp/reported"
    findings=$((findings + 1))
  fi
  if [ -f "$REPO/.log4brains.yml" ]; then
    hit="$(/usr/bin/grep -E '^[[:space:]]*adrFolder:' "$REPO/.log4brains.yml" 2>/dev/null \
           | /usr/bin/head -1 | /usr/bin/sed 's/^[[:space:]]*adrFolder:[[:space:]]*//; s/^["'"'"']//; s/["'"'"']$//' || true)"
    [ -n "$hit" ] || hit="(.log4brains.yml names no adrFolder)"
    finding_lines+=("[decisions] ${hit}   evidence tier: marker (.log4brains.yml)")
    printf '%s\n' "$hit" >> "$tmp/reported"
    findings=$((findings + 1))
  fi
  if [ -f "$REPO/adr.config.json" ]; then
    finding_lines+=("[decisions] adr.config.json is present   evidence tier: marker (adr.config.json)")
    findings=$((findings + 1))
  fi

  # --- tier 2: directory name + filename shape ------------------------------
  # The NNNN-*.md gate is load-bearing, not decoration. Name-matching alone hits a recurring
  # tutorial `Decisions/` folder in many repositories, and in datasets
  # and meeting logs. A directory that carries one of the tokens but no NNNN-*.md is reported by
  # NOTHING -- not by this tier, and deliberately not by tier 3 either, or the gate would be
  # decorative.
  /usr/bin/sed 's|/[^/]*$||' "$tmp/all" | /usr/bin/sort -u > "$tmp/dirs"
  : > "$tmp/token_dirs"
  while IFS= read -r dir; do
    [ -n "$dir" ] || continue
    base="$(lower "${dir##*/}")"
    case "$base" in
      *adr*|*decision*|*decisions*) printf '%s\n' "$dir" >> "$tmp/token_dirs" ;;
    esac
  done < "$tmp/dirs"

  while IFS= read -r dir; do
    [ -n "$dir" ] || continue
    hit="$(/usr/bin/grep -cE "^${dir}/[0-9][0-9][0-9][0-9]-[^/]*\.md$" "$tmp/all" 2>/dev/null || true)"
    [ -n "$hit" ] || hit=0
    if [ "$hit" -gt 0 ]; then
      finding_lines+=("[decisions] ${dir}/   evidence tier: name + filename shape (${hit} files matching NNNN-*.md)")
      printf '%s\n' "$dir" >> "$tmp/reported"
      findings=$((findings + 1))
    fi
  done < "$tmp/token_dirs"

  # --- tier 3: content fingerprint, for directories carrying NEITHER token ---
  # Two families, because the two dominant ADR formats share almost no literal strings: Nygard /
  # adr-tools uses `## Consequences`; MADR v4 uses `## Decision Outcome` / `## Considered Options`.
  # The Nygard family is measured on a real repository's decision records. The MADR family is
  # derived from the specification and is proved here only by a fixture.
  : > "$tmp/fp_dirs"
  /usr/bin/grep -E '\.md$' "$tmp/all" 2>/dev/null > "$tmp/md" || true
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    dir="${f%/*}"
    [ "$dir" = "$f" ] && dir="."
    if /usr/bin/grep -qE "$(fingerprint_re)" "$REPO/$f" 2>/dev/null; then
      printf '%s\n' "$dir" >> "$tmp/fp_dirs"
    fi
  done < "$tmp/md"

  if [ -s "$tmp/fp_dirs" ]; then
    /usr/bin/sort -u "$tmp/fp_dirs" > "$tmp/fp_uniq"
    while IFS= read -r dir; do
      [ -n "$dir" ] || continue
      /usr/bin/grep -qxF -- "$dir" "$tmp/token_dirs" 2>/dev/null && continue   # tier 2's domain
      /usr/bin/grep -qxF -- "$dir" "$tmp/reported"  2>/dev/null && continue
      hit="$(/usr/bin/grep -cxF -- "$dir" "$tmp/fp_dirs" 2>/dev/null || true)"
      [ -n "$hit" ] || hit=0
      if [ "$hit" -ge 2 ]; then
        finding_lines+=("[decisions] ${dir}/   evidence tier: content fingerprint (${hit} files)")
        findings=$((findings + 1))
      else
        # ONE MATCHING FILE IS A NOTE, NOT A FINDING, and the reason is principled rather than
        # tuned: a directory that KEEPS decision records accumulates more than one; a document that
        # DESCRIBES the format is a single file. Measured the first time this scan ran on a second
        # repository -- it fired on `skills/project-lifecycle/references/`, which holds this
        # project's own prose about the ADR format and not one ADR.
        #
        # THE COST, stated because it is real: a project with exactly ONE decision record, in a
        # directory whose name carries none of the tokens, is now a note instead of a finding. That
        # is a false negative this threshold creates, and it belongs in the floor the report prints.
        #
        # THE BOUNDARY: the zero-false-positive measurement came from a small sample, and a
        # further repository produced one immediately. A small sample is not a rate.
        note_lines+=("  decisions   ${dir}/ carries ${hit} file(s) matching a content fingerprint -- too weak to")
        note_lines+=("              stop on; a directory that keeps records usually has more than one")
        weak_decisions=$((weak_decisions + 1))
      fi
    done < "$tmp/fp_uniq"
  fi

  # --- roadmap: NAME only, one collapsed row, and one suppressed draft ------
  # ONE row regardless of N. A monorepo carrying a ROADMAP.md per package would otherwise push the
  # findings off the top of the report, which is the harm; the paths all stay, indented under it,
  # because the story's Contingencies forbid silent truncation.
  : > "$tmp/roadmaps"
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    base="$(lower "${f##*/}")"
    # A MARKDOWN FILE WHOSE NAME *IS* A ROADMAP, not any file with the word in it. The first
    # version matched `*roadmap*` against every tracked path and returned scripts,
    # invariants, test files and a rules file. That is a net fired at the
    # product, the same shape as the fingerprint tier's false positive above.
    # BOUNDARY, stated where it is decided: `product-roadmap.md` and `roadmap_2026.md` match;
    # `plans/q3.md` does not, however much it is a roadmap. Name-only was always the weak signal
    # here, and narrowing it does not make it strong -- it makes it honest about being narrow.
    case "$base" in
      *.md) : ;;
      *) continue ;;
    esac
    base="${base%.md}"
    case "$base" in
      "$ROADMAP_NAME_TOKEN"|*-"$ROADMAP_NAME_TOKEN"|*_"$ROADMAP_NAME_TOKEN"|"$ROADMAP_NAME_TOKEN"-*|"$ROADMAP_NAME_TOKEN"_*)
        printf '%s\n' "$f" >> "$tmp/roadmaps" ;;
    esac
  done < "$tmp/all"

  if [ -s "$tmp/roadmaps" ]; then
    hit="$(/usr/bin/wc -l < "$tmp/roadmaps" | /usr/bin/tr -d ' ')"
    note_lines+=("  roadmap     ${hit} file(s) match by name -- weak signal: a file with this name exists;")
    note_lines+=("              whether it is maintained was not checked")
    while IFS= read -r f; do
      [ -n "$f" ] || continue
      note_lines+=("                ${f}")
    done < "$tmp/roadmaps"
    # The pass PROCEEDS -- a name-only signal fires on every repository carrying a long-dead
    # ROADMAP.md, and a gate that stops that often gets read as noise. What it must not do is write
    # a competing draft over a file that is already there, which is the exact failure to avoid. So one
    # artifact is withheld and the report names the file that took its place.
    note_lines+=("  suppressed  the inferred docs/ROADMAP.md will NOT be written: the file(s) above already")
    note_lines+=("              hold that role. The other five drafts are unaffected.")
    roadmap_suppressed=1
  fi

  rm -rf "$tmp"
}

# ---------------------------------------------------------------------------
# detect -- the adoption-entry decision, as a runnable answer instead of seven paragraphs.
# Prints `adoption-entry` or `new-project` and why. Exit 0 either way: this reports a
# classification, it does not pass or fail.
# ---------------------------------------------------------------------------

cmd_detect() {
  local toplevel f p ext anchor_found="" manifest_found="" source_found="" tmp

  toplevel="$(g rev-parse --show-toplevel 2>/dev/null || true)"
  [ -n "$toplevel" ] || die_could_not_run "$REPO is not inside a git repository"
  REPO="$toplevel"

  tmp="$(mktemp -d)" || die_could_not_run "cannot create a temporary directory"
  g ls-files > "$tmp/all" 2>/dev/null || true

  if [ ! -s "$tmp/all" ]; then
    # Untracked-only repository (no commits yet) -> new-project, per the detection contract.
    printf 'new-project   no tracked files: nothing to adopt\n'
    rm -rf "$tmp"; return 0
  fi

  for f in $ADOPTION_ANCHORS; do
    if /usr/bin/grep -qxF -- "$f" "$tmp/all"; then anchor_found="$f"; break; fi
  done
  if [ -n "$anchor_found" ]; then
    printf 'new-project   a plc anchor is already present: %s\n' "$anchor_found"
    rm -rf "$tmp"; return 0
  fi

  for f in $ADOPTION_MANIFESTS; do
    if /usr/bin/grep -qxF -- "$f" "$tmp/all"; then manifest_found="$f"; break; fi
  done
  if [ -z "$manifest_found" ]; then
    for f in $ADOPTION_MANIFEST_GLOBS; do
      # glob manifests match at ANY depth, unlike the root-anchored plain names above
      # A GLOB IS NOT A REGEX, so this does not convert one into the other. The first version
      # substituted only `*` and left every other metacharacter live: `*.csproj` became
      # `(^|/)[^/]*.csproj$`, whose unescaped `.` matches ANY character, so `src/fooXcsproj` -- a
      # file with no dot in its name at all -- was read as a recognised manifest and flipped
      # `new-project` to `adoption-entry`. Reproduced here.
      #
      # THE SECOND VERSION WAS WORSE AND THAT IS WHY IT IS NOT HERE: escaping the metacharacters
      # with sed produced a broken sed expression, which `2>&1` turned into a "classification" of
      # `sed:` -- a wrong answer dressed as an answer. `case` is glob-native. No conversion, no
      # escaping, and the semantics are the ones the glob actually means.
      while IFS= read -r p; do
        [ -n "$p" ] || continue
        case "${p##*/}" in
          $f) manifest_found="$f"; break ;;
        esac
      done < "$tmp/all"
      [ -n "$manifest_found" ] && break
    done
  fi

  if [ -z "$manifest_found" ]; then
    while IFS= read -r f; do
      [ -n "$f" ] || continue
      case "$f" in
        .git/*|.hg/*|.idea/*|.vscode/*|.zed/*|.claude/*|.cursor/*|docs/*|.yarn/*) continue ;;
      esac
      ext="${f##*.}"
      [ "$ext" = "$f" ] && continue
      case " $ADOPTION_SOURCE_EXTS " in
        *" $ext "*) source_found="$f"; break ;;
      esac
    done < "$tmp/all"
  fi
  rm -rf "$tmp"

  if [ -n "$manifest_found" ]; then
    printf 'adoption-entry   no plc anchor, and a recognised manifest is present: %s\n' "$manifest_found"
  elif [ -n "$source_found" ]; then
    printf 'adoption-entry   no plc anchor, and a recognised source file outside the whitelist: %s\n' "$source_found"
  else
    printf 'new-project   no plc anchor, and no substantial existing code\n'
  fi
  return 0
}

# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------

cmd_check() {
  local toplevel current default_ref behind ahead last findings=0 weak_decisions=0 roadmap_suppressed=0
  local -a finding_lines=() note_lines=()

  toplevel="$(g rev-parse --show-toplevel 2>/dev/null || true)"
  if [ -z "$toplevel" ]; then
    # A bare repository IS a repository; it just has no worktree, and every check below needs one.
    # Saying "not a git repository" there would send the reader to look for the wrong problem.
    if [ "$(g rev-parse --is-bare-repository 2>/dev/null || true)" = "true" ]; then
      die_could_not_run "$REPO is a bare repository: there is no working tree to check"
    fi
    die_could_not_run "$REPO is not inside a git repository"
  fi
  REPO="$toplevel"

  # A repository with no commits has nothing to be stale against, and is not an error.
  if ! g rev-parse --verify -q HEAD >/dev/null 2>&1; then
    printf '%s -- no finding.\n\n' "$PROG"
    printf '  branch      this repository has no commits yet; there is nothing to compare\n'
    exit 0
  fi

  current="$(g symbolic-ref -q --short HEAD 2>/dev/null || true)"
  # No surrounding parentheses: the note lines below add their own, and a doubled parenthetical
  # reads as a typo in a report whose whole job is to be read carefully.
  [ -n "$current" ] || current="detached HEAD"

  # THE HOUSE IDIOM, AND DELIBERATELY NO FALLBACK. `|| echo origin/main` appears at
  # scripts/close-gate.sh:1346 and is NOT copied here: it turns "I could not find out" into a
  # confident measurement against a branch that may not exist. close-gate may keep it, because its
  # blast radius is one repository it already knows. This runs on strangers' repositories.
  default_ref="$(g symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null || true)"

  if [ -z "$default_ref" ]; then
    # Many real repositories lack this ref, so this is not a corner. Reporting "not checked" alone is honest AND a dead end;
    # the remedy is printed, and this script does not run it, because running it writes a ref and this check never writes a ref.
    note_lines+=("  branch      staleness not checked -- this repository has no refs/remotes/origin/HEAD,")
    note_lines+=("              so there is no default branch to compare against. This check will")
    note_lines+=("              not create it. To get the comparison, run this yourself:")
    note_lines+=("")
    note_lines+=("                  git remote set-head origin -a")
    note_lines+=("")
    note_lines+=("              then run the pre-flight again.")
  else
    behind="$(g rev-list --count "HEAD..${default_ref}" 2>/dev/null || true)"
    if [ -z "$behind" ]; then
      note_lines+=("  branch      staleness not checked -- ${default_ref} could not be compared against HEAD")
    elif [ "$behind" -eq 0 ]; then
      # "up to date with" is a claim of PARITY, and being 0 behind does not establish parity -- a
      # branch carrying its own unmerged commits is AHEAD, and an early version of this script
      # reported such a branch as "up to date with origin/main". The judgement was right and the sentence was wider than it.
      ahead="$(g rev-list --count "${default_ref}..HEAD" 2>/dev/null || true)"
      if [ -n "$ahead" ] && [ "$ahead" -gt 0 ]; then
        note_lines+=("  branch      ${current} is ${ahead} commits ahead of ${default_ref} and 0 behind it, compared against remote refs as last fetched")
      else
        note_lines+=("  branch      ${current} (up to date with ${default_ref}, compared against remote refs as last fetched)")
      fi
    else
      last="$(g log -1 --format=%cs "$default_ref" 2>/dev/null || true)"
      [ -n "$last" ] || last="unknown date"
      # DIVERGENCE IS REPORTED, not dropped. "N behind" alone reads as a fast-forward relationship,
      # and on a branch that also carries local commits -- or on one with no common ancestor at all
      # -- that sentence is wider than what was measured. This is the same defect the ahead-vs-parity
      # fix already closed for the behind==0 case; it was still open here.
      ahead="$(g rev-list --count "${default_ref}..HEAD" 2>/dev/null || true)"
      if [ -n "$ahead" ] && [ "$ahead" -gt 0 ]; then
        finding_lines+=("[branch]    ${current} has diverged from ${default_ref}: ${behind} commits behind and ${ahead} ahead; ${default_ref}'s last commit is ${last}")
      else
        finding_lines+=("[branch]    ${current} is ${behind} commits behind ${default_ref}; ${default_ref}'s last commit is ${last}")
      fi
      findings=$((findings + 1))
    fi
  fi

  # THE SCAN RUNS ONLY ON A TREE THE STALENESS GATE CLEARED, and when it does not run the report
  # says so. Scanning a tree already known to be the wrong one is the very thing this check exists to prevent: the
  # answer would be about a branch nobody works on. A report that printed a branch finding and a decisions finding
  # side by side would be wrong: the ADRs are invisible from the branch that was checked out. The behaviour is fixed here, where it happens.
  if [ "$findings" -gt 0 ]; then
    note_lines+=("  decisions   not scanned -- the branch above is not the tree this project works on,")
    note_lines+=("              so anything found here would describe the wrong one. Resolve the branch")
    note_lines+=("              first, then run the pre-flight again.")
  else
    scan_artifacts
    # "nothing matched" must not be printed next to a row that just matched weakly -- the report
    # would contradict itself in adjacent lines.
    if [ "$findings" -eq 0 ] && [ "$weak_decisions" -eq 0 ]; then
      note_lines+=("  decisions   nothing matched the signatures this check knows")
    fi
  fi

  if [ "$findings" -gt 0 ]; then
    printf '%s -- STOPPED, %s finding(s). No drafts were produced.\n\n' "$PROG" "$findings"
    local line
    # reachable only when findings > 0, so the array is never empty here
    for line in "${finding_lines[@]}"; do printf '  %s\n' "$line"; done
    if [ "${#note_lines[@]}" -gt 0 ]; then
      printf '\n  note, not a finding:\n'
      for line in "${note_lines[@]}"; do printf '%s\n' "$line"; done
    fi
    if printf '%s\n' "${finding_lines[@]}" | /usr/bin/grep -q '^\[decisions\]'; then
      # Both disclosures ride with the rows they qualify, not in a comment. A limitation a reader
      # cannot see while reading the row is not a limitation they have been told about.
      printf '\n  about those counts: a file count is a count of SHAPE matches, not of confirmed\n'
      printf '  decision records; and the content-fingerprint tier de-duplicates nothing across\n'
      printf '  directories, so an unrelated document carrying one of those headings fires on its own.\n'
    fi
    printf '\nNothing was changed: no branch switch, no fetch, no write.\n'
    printf 'You decide what happens next.\n\n'
    floor_text
    exit 1
  fi

  if [ "$roadmap_suppressed" -eq 1 ]; then
    printf '%s -- no finding. The pass will produce 5 of 6 drafts.\n\n' "$PROG"
  else
    printf '%s -- no finding.\n\n' "$PROG"
  fi
  # bash 3.2 (the /bin/bash macOS ships) errors on an empty array expansion under `set -u`, so the
  # guard is not decoration -- without it a repository in a state that produces no notes would exit
  # 3 from the ERR trap instead of 0, and the failure would read as "could not run".
  if [ "${#note_lines[@]}" -gt 0 ]; then
    local line
    for line in "${note_lines[@]}"; do printf '%s\n' "$line"; done
  fi
  printf '\n'
  floor_text
  exit 0
}

# ---------------------------------------------------------------------------

REPO="$PWD"
SUB="${1-}"
[ "$#" -gt 0 ] && shift || true

while [ "$#" -gt 0 ]; do
  case "$1" in
    --repo) REPO="${2-}"; [ -n "$REPO" ] || die_could_not_run "--repo needs a path"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) printf '%s: unknown argument: %s\n' "$PROG" "$1" >&2; usage >&2; exit 3 ;;
  esac
done

case "$SUB" in
  check)  cmd_check ;;
  detect) cmd_detect ;;
  -h|--help|"") usage; exit 0 ;;
  *) printf '%s: unknown subcommand: %s\n' "$PROG" "$SUB" >&2; usage >&2; exit 3 ;;
esac
