#!/usr/bin/env bash
# close-gate.sh — deterministic wrap-up gate for THIS repo (project-life-cycle).
#
# Usage: close-gate.sh task X.Y     (per-commit subset — run by the pre-push hook)
#        close-gate.sh phase X.Y    (phase close — adds CHANGELOG / spec / plan / ROADMAP; pre-merge)
#        close-gate.sh diff         (no phase: the DIFF-triggered subset — see below)
#
# WHY THIS IS NOT the canonical gate from references/close-gate.md:
# The canonical gate proves the journal / spec / plan / ROADMAP ceremony
# via git commit-range checks (git diff origin/main..HEAD), which structurally CANNOT see
# uncommitted or gitignored files. This gate proves the same
# ceremony via LOCAL FILE signals (existence + FACT content + freshness-vs-branch-point)
# instead — the only observable evidence for docs that are not (or not yet) committed. Tracked artifacts
# (CHANGELOG.md, the feat/fix commit, the test-evidence file) are still checked via git / file
# as normal.
#
# Envelope: bash + git + jq + coreutils only. NO python3 (a hard rule for this gate — the
# gate must stay a drop-in with a minimal dependency footprint).
set -euo pipefail

M=".claude/close-gate.json"   # hoisted: evidence_digest (below) reads test_evidence_inputs
                               # from here, but must keep working with no manifest at all —
                               # see the comment on GATE_RELEVANT_PATHS just below.

# --- test-evidence content fingerprint (shared by the runner and row 7) --------------------
#
# GATE-RELEVANT PATHS and the rationale for keeping the list narrow now live in the manifest
# (test_evidence_inputs, validator_input_paths_rationale — .claude/close-gate.json) instead of
# hardcoded here, so the two can never drift. Read OPTIMISTICALLY, before the manifest
# is required to exist below: the `evidence-header` subcommand must still work with no
# manifest at all (producing evidence cannot itself need a configured manifest), so a missing/
# unreadable/malformed test_evidence_inputs resolves to an EMPTY list here rather than erroring
# — evidence_digest() below turns "no pathspecs resolved" into the same sentinel it already
# uses for "declared paths matched no file in this repo", and row 7 (which DOES require the
# manifest) already fails closed on that sentinel, so a present-but-misconfigured manifest
# still reddens the gate at the point where reddening is actionable.
GATE_RELEVANT_PATHS=""
if [ -f "$M" ] \
   && _tei_type="$(jq -r '.test_evidence_inputs | type' "$M" 2>/dev/null)" \
   && [ "$_tei_type" = array ]; then
  GATE_RELEVANT_PATHS="$(jq -r '.test_evidence_inputs[]' "$M" 2>/dev/null || true)"
fi

# evidence_digest: a stable fingerprint of validate.py's tracked inputs, from WORKING-TREE
# content (so an uncommitted edit is caught). `git hash-object` is content-addressed — same
# bytes, same hash, on any machine — and keeps the envelope inside git (no sha256sum dep). The
# per-file hashes are sorted so ordering never perturbs the digest, then hashed as one blob.
# This is why the SHA-anchor design was abandoned: a fingerprint cannot be fooled by commit
# order, has no same-commit off-by-one (commits don't change content), and needs no anchor.
evidence_digest() {
  # Disable globbing while splitting the pattern list: '*.md' must reach `git ls-files` as a
  # (recursive) PATHSPEC, not be expanded by the shell against the cwd first — in a directory
  # that happens to contain a top-level .md, an unquoted '*.md' globs to that one file and the
  # recursive match silently collapses. `set -- $LIST` under `set -f` passes them verbatim.
  set -f
  # shellcheck disable=SC2086
  set -- $GATE_RELEVANT_PATHS
  set +f
  # No pathspecs at all — either the manifest has no valid test_evidence_inputs (row 7 will
  # reject this) or `evidence-header` ran with no manifest configured at all. `git ls-files --`
  # with ZERO pathspecs after `--` matches EVERY tracked file, not none, so this case must be
  # caught explicitly here or an unresolved list would silently fingerprint the whole repo
  # instead of nothing.
  if [ "$#" -eq 0 ]; then
    printf 'EMPTY-no-gate-relevant-paths-matched\n'
    return 0
  fi
  # Zero matches must NOT fall through to `git hash-object --stdin` on empty input: that
  # returns the FIXED empty-blob SHA e69de29b…, a constant that passes the header regex, so
  # row 7 would compare constant-to-constant and PASS vacuously — an adopter whose layout does
  # not fit GATE_RELEVANT_PATHS would silently green, the exact silent-degrade this check
  # removes. Emit a non-hex sentinel instead; the gate rejects it loudly (row 7).
  if [ -z "$(git ls-files -z -- "$@" 2>/dev/null | tr -d '\0')" ]; then
    printf 'EMPTY-no-gate-relevant-paths-matched\n'
    return 0
  fi
  git ls-files -z -- "$@" 2>/dev/null \
    | while IFS= read -r -d '' _f; do
        printf '%s %s\n' "$(git hash-object "$_f" 2>/dev/null || echo MISSING)" "$_f"
      done \
    | LC_ALL=C sort \
    | git hash-object --stdin
}

# The header the runner must write as the evidence file's first line. ONE definition, emitted
# by the `evidence-header` subcommand below and re-derived (its digest half — evidence_digest)
# by row 7 — the runner and the gate can never drift because they share that function.
#
# `set` records which gate mode this evidence was generated for
# (task|phase) so a task-mode and a phase-mode evidence file are distinguishable after the
# fact. It goes on the SAME header line and is MANDATORY — a caller with no set value gets no
# header at all (below), never a header missing the field. The gate does NOT compare this
# against the mode it is currently run in (out of scope: the field is recorded, not enforced) —
# row 7 only checks that the field is present and well-formed.
evidence_header() { printf '# plc-gate-evidence inputs=%s set=%s\n' "$(evidence_digest)" "$1"; }

# Subcommand: print just the header, so the runner can prepend it. Runs BEFORE the phase/
# manifest requirements — producing evidence must not itself need a configured manifest.
#
# The set value comes from an explicit second arg ONLY (`evidence-header task|phase`). The
# manifest's declared test_command carries the same value via a `{SET}` placeholder (same
# substitution idiom as `{PHASE}`/`{EVIDENCE_FILE}` — see the {EVIDENCE_FILE} comment at row 7
# below), resolved by gen-test-evidence.sh before it runs the command — never by an env var.
# There is deliberately no environment-variable fallback: an env var is public API the moment it
# ships. Absent, or not
# task/phase, is a hard fail: a header cannot be honest about a mode nobody supplied.
if [ "${1:-}" = evidence-header ]; then
  _EH_SET="${2:-}"
  case "$_EH_SET" in
    task|phase) ;;
    *) echo "✗ evidence-header needs a set value — pass it as \`close-gate.sh evidence-header task|phase\`"; exit 1 ;;
  esac
  evidence_header "$_EH_SET"; exit 0
fi

MODE="${1:?usage: close-gate.sh <task|phase|diff|test-command> X.Y}"
PHASE="${2:-}"
# Two modes. `task` (per-commit, run by the pre-push hook on every push) gates the
# per-task subset — product-tree change + this task's journal FACT + test-evidence unchanged since
# it was generated +
# declared invariants — so a phase's first completed task is pushable the moment it exists,
# reconciling SKILL.md's push-immediate rule with the gate that used to demand phase-close
# artifacts on commit one. `phase` (run before PR-merge) additionally requires the phase-close
# artifacts: CHANGELOG [Unreleased], spec + plan docs, and the ROADMAP row. The un-bypassable
# pre-push layer is not weakened — it still runs on every push; only its scope now matches the
# push moment (a task) instead of demanding a whole phase up front.
# `diff` is the third gating mode — the subset that applies to a branch with NO
# phase (this repo's `chore/…`, `docs/…`, `fix/…` branches, and `main`). It is triggered by what
# the DIFF touches rather than by what the branch is called: the manifest's declared
# product_paths decide whether the CHANGELOG + test-evidence rows fire, the declared invariants
# run regardless, and the phase-artifact rows (spec / plan / journal / ROADMAP) are not run at
# all because no phase exists for them to describe. The branch NAME is not read here — the
# caller (scripts/close-gate-prepush.sh) decides the mode; this script still derives nothing
# from the current branch.
case "$MODE" in
  task|phase) ;;
  diff) ;;          # the diff-triggered subset for a branch with no phase
  test-command) ;;  # a per-value accessor, not a phase-gating mode — see below
  *) echo "✗ mode must be 'task' (per-commit, pre-push), 'phase' (phase close), 'diff' (diff-triggered subset, no phase) or 'test-command' (print the declared test_command) — got '$MODE'"; exit 1 ;;
esac
# test-command needs no PHASE — it prints one manifest key, unrelated to any phase's rows.
# `diff` needs none either, and that is structural rather than a convenience: every row it runs
# is a property of the diff or of the working tree, so a phase id would have nothing to select.
if [ "$MODE" != test-command ] && [ "$MODE" != diff ]; then
  [ -n "$PHASE" ] || { echo "✗ $MODE mode needs a PHASE arg (e.g. close-gate.sh $MODE X.Y-X.Z)"; exit 1; }
fi

[ -f "$M" ] || { echo "✗ missing manifest $M"; exit 1; }
g() { jq -r ".$1 // empty" "$M" | sed "s/{PHASE}/$PHASE/g"; }

# Subcommand: print ONLY the raw declared test_command — no human decoration,
# no {EVIDENCE_FILE} substitution (that placeholder stays UNRESOLVED here; resolving it is the
# runner's job — gen-test-evidence.sh — exactly like the substitution already done at row 7
# below). Deliberately NOT a general `get <key>` accessor: one subcommand, one key, so an
# accessor's output never becomes a wider contract than the one key it was built for.
#
# Placed HERE, after the manifest-existence check just above — unlike `evidence-header` (which
# runs before any manifest is required, because producing evidence must not itself need one),
# this accessor READS the manifest, so requiring one to exist first is the correct order for
# THIS subcommand; the analogy with `evidence-header`'s placement does not carry over.
if [ "$MODE" = test-command ]; then
  # Failing clearly: an absent key and a malformed manifest used to print the SAME "no
  # test_command declared" message — jq's own parse-error stderr was suppressed on the read
  # below, so the two causes were indistinguishable from the message alone. `jq empty` parses
  # without producing output and fails only on invalid JSON, so that cause gets checked, and
  # reported, before the key is even looked up.
  jq empty "$M" >/dev/null 2>&1 || { echo "✗ $M is not valid JSON — cannot read test_command"; exit 1; }
  TC="$(jq -r '.test_command // empty' "$M" 2>/dev/null)"
  [ -n "$TC" ] || { echo "✗ no test_command declared in $M"; exit 1; }
  printf '%s\n' "$TC"
  exit 0
fi

fail=0

# --- the lifecycle ledger, and why it cannot make this gate fail -----------------------------
#
# `ok`/`bad` take an OPTIONAL second argument: the registry stage this row is about. When given,
# the outcome is REMEMBERED here and every remembered outcome is written once, at the very end, by
# `ledger_flush`. Two properties follow from doing it that way rather than emitting inline:
#
#   * the gate's control flow is untouched. Nothing between the first check and the verdict gains a
#     new way to exit, which is what "no currently-unenforced stage becomes a gate
#     failure" has to mean in code and not only in prose.
#   * the writes happen after `GATE_VERDICT_REACHED`-adjacent work is done, so a ledger problem
#     cannot land between the last row and the verdict.
#
# FAIL-OPEN, ALWAYS. `ledger_flush` swallows every error and returns 0. A stage whose
# record never got written then reads as claimed/unknown in `/plc-status` -- never observed, and
# never a gate failure. That is a hard requirement, and it is the whole reason the emission is a tail call
# behind `|| true` rather than a check.
#
# NO AGENT-AUTHORED CLAIMS. Everything written here is `observed:true`, because the gate genuinely
# saw the thing. `bad` records `status=failed` and stays observed -- the gate watched it fail, which
# is a stronger fact than absence and is why a failed check is a record rather than a silence.
LEDGER_ROWS=""
ledger_note() { LEDGER_ROWS="${LEDGER_ROWS}$1 $2
"; }

ok()   { echo "✓ $1"; [ $# -ge 2 ] && ledger_note "$2" done   || true; }
bad()  { echo "✗ $1"; fail=1; [ $# -ge 2 ] && ledger_note "$2" failed || true; }
warn() { echo "⚠ $1"; }   # never touches $fail
glob_exists() { compgen -G "$1" >/dev/null 2>&1; }

ledger_flush() {
  [ "${PLC_LEDGER:-1}" = "1" ] || return 0
  # Relative to the working directory, exactly like `M=".claude/close-gate.json"` above: this gate
  # is defined to run from the repo root and every other path in it already assumes that.
  local emitter="scripts/ledger-append.sh" runner="scripts/ledger-run.sh"

  [ -r "$emitter" ] && [ -r "$runner" ] || return 0
  command -v jq >/dev/null 2>&1 || return 0

  local run_id ledger now stage status attempt
  run_id="$(PLC_RUN_ID="${PLC_RUN_ID:-}" /bin/bash "$runner" run-id --phase "${PHASE:-nophase}" 2>/dev/null)" || return 0
  [ -n "$run_id" ] || return 0
  # `--owner-pid $$` -- the gate is the writer, and only the writer knows its own pid. Without it
  # `ledger-path` would blame $PPID, which for a gate invoked from a hook is a shell that exits
  # first, and the ownership claim would name a corpse.
  ledger="$(/bin/bash "$runner" ledger-path "$run_id" --repo-root "$PWD" --owner-pid $$ 2>/dev/null)" || return 0
  [ -n "$ledger" ] || return 0
  # A deliberate break, for the fail-open oracle. It must make the emitter genuinely FAIL, not skip:
  # an absent emitter is handled above and returns 0 early, which would exercise the graceful path
  # instead of the criterion. A ledger path under /dev/null cannot be created, so the real emitter
  # runs and really fails -- and `|| true` at the call site is then the only thing keeping the gate
  # green. A test seam, never a mode anyone runs.
  [ -z "${PLC_LEDGER_BREAK:-}" ] || ledger="/dev/null/impossible/ledger.jsonl"
  now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

  # The gate's own run is a stage too, and its status is the verdict the reader would otherwise
  # have to infer from the other rows.
  ledger_note "close_gate_${MODE}" "$( [ "$fail" -eq 0 ] && printf done || printf failed )"

  # ONE record per stage per run, and `failed` wins. Without this, check 8 emits a row per declared
  # invariant -- one record and one attempt number each -- which reads as N retries of a stage that
  # ran once. A stage is a stage; the individual invariants are its content, not its history.
  local collapsed
  collapsed="$(printf '%s' "$LEDGER_ROWS" | awk '
      NF == 2 { if ($2 == "failed") state[$1] = "failed"; else if (!($1 in state)) state[$1] = $2 }
      END { for (k in state) print k, state[k] }' | sort)"

  while read -r stage status; do
    [ -n "$stage" ] || continue
    # A REFUSAL IS NOT A DEFAULT. `next-attempt` refuses when the ledger has a line it cannot
    # parse, precisely so nobody mints an id that may already exist -- and `|| attempt=1` would turn
    # that refusal into a guess of exactly the value it refused to give, producing a duplicate
    # attempt 1. The rule binds every CALLER, not only the callee.
    # Skipping the stage is the fail-open direction -- an
    # unwritten record renders `claimed`/`missing`, never `observed`.
    if ! attempt="$(/bin/bash "$runner" next-attempt "$ledger" "$stage" 2>/dev/null)" \
       || [ -z "$attempt" ]; then
      continue
    fi
    /bin/bash "$emitter" append --file "$ledger" \
      --run-id "$run_id" --repo-id "${PLC_REPO_ID:-$(git rev-list --max-parents=0 HEAD 2>/dev/null | head -1)}" \
      --phase "${PHASE:-nophase}" --stage-id "$stage" --attempt-id "$attempt" \
      --type stage_observation --status "$status" --observed true \
      --observer close-gate.sh --started-at "$now" --completed-at "$now" >/dev/null 2>&1 || true
  done <<EOF
$collapsed
EOF
  return 0
}

# context-floor arming row — WARN-ONLY (never flips $fail): the floor is a machine-local
# user-settings hook, so a project gate must not fail on it; but an un-armed floor silently
# costs 2-3x per late-session turn. The row is ported here from the canonical gate
# in skills/project-lifecycle/references/close-gate.md, where the FULL rationale is written out.
#
# THE FUNCTION BODY BELOW IS BYTE-IDENTICAL TO THE ONE IN references/close-gate.md, and
# nothing in this tree asserts that. ONE row in TWO files is two copies that can
# silently disagree, so a wording change to either copy has to be made in both. The durable fix
# is one source both gates read; it is not built here. What is deliberately NOT mirrored is the
# CALL SITE: the canonical gate calls this from its phase branch, and this gate calls it in every
# gating mode, because the pre-push hook runs `task` on every push and a floor warning that
# only reached the human at phase close would arrive once per milestone instead of once per push.
# The byte-identity covers the row, not where it is called.
#
# THREE states, never two. Wiring and capability are different questions — liveness (configured)
# vs readiness (able to do its job) — and a row that answers only the first reads as though it
# had answered both:
#   not wired        no settings file names context-floor.sh
#   wired            settings name it AND `jq` was resolvable when this gate ran
#   wired but inert  settings name it and `jq` was NOT resolvable when this gate ran.
#                    skills/project-lifecycle/hooks/context-floor.sh's first act is
#                    `command -v jq >/dev/null || exit 0`, so the floor is silently off wherever
#                    that probe fails — the fail-open is deliberate (a broken floor must never
#                    block work) and this row is the separate warning that comment relies on.
# All three go through ok()/warn(), never bad(), so warn-only is structural rather than a
# property to be remembered. `${HOME:-}`: under set -u a stripped hook/CI environment without
# HOME would abort the whole gate on a bare expansion — the one thing a warn-only row must not do.
#
# WHAT THE ✓ DOES NOT PROVE. `command -v jq` runs in THIS process, with THIS PATH, at gate time.
# It is the same probe the hook uses, in a different environment, and says nothing about the
# environment the hook is later spawned in. The concrete blind spot is a GUI client (or any
# launchd-started app) whose PATH is stripped to /usr/bin:/bin while jq lives in
# /opt/homebrew/bin: this gate, started from a login shell, finds jq and prints "wired", and the
# hook that client spawns does not and exits 0. So the ✓ may say only that jq was resolvable when
# the gate ran; it may not say the hook works, will run, or is verified.
#
# WHAT THE GREP SEES: a literal substring search for `context-floor.sh` across the three settings
# files — exactly the string the ✓ names, so neither can drift wider than the other. It does NOT
# parse the hooks array: the same ✓ prints when the name appears only in a comment, in an
# unrelated key, or inside a `disabledHooks` list. That is the price of staying grep-only in the
# not-wired branch (jq is not yet known to exist there — it is what the next branch probes), and
# it is why the row says "settings reference" rather than "the hook is installed".
#
# THE INERT BRANCH CANNOT PRINT FOR A USER, IN EITHER DIRECTION — a product fact about this
# branch, not a note about how it is tested. This gate is jq-only and reads its manifest through
# `jq` long before this row runs, so both worlds the warning could describe swallow it: on a
# genuinely jq-less machine the gate dies at its first `g` call with rc 127 and prints NOTHING AT
# ALL; on the stripped-PATH GUI client this warning is actually about, the gate resolves jq and
# prints the ✓ WIRED row while the HOOK is the inert one. Both measured. The branch
# exists as a CONTRACT for gates that CAN reach it, and the tests drive floor_arming_row directly
# because that is the only execution context in which it exists at all.
#
# The ⚠ is held to the same claim↔pattern tie as the ✓, and was not at first: it said "project
# `.claude/settings*.json`" while the grep reads two named files, so the row whose entire subject
# is a claim wider than its mechanism carried one. It now names the three paths the grep is given,
# in the same order, with `~` for the `${HOME:-}` the shell expands. A test pins the ⚠'s path list
# to the grep's the way the ✓'s pattern is already pinned — adding a file to the grep without
# naming it in the ⚠, or widening the ⚠ back to a glob, is a failure and not a wording preference.
floor_arming_row() {
  if ! grep -qs 'context-floor\.sh' "${HOME:-}/.claude/settings.json" .claude/settings.json .claude/settings.local.json 2>/dev/null; then
    warn "context-floor hook not wired in ~/.claude/settings.json, project .claude/settings.json or .claude/settings.local.json — sessions can silently run to very large per-turn contexts. Fix: /init-harness --refresh (references/harness-primitives.md §9)"
  elif command -v jq >/dev/null 2>&1; then
    ok "context-floor hook wired (settings reference context-floor.sh) and jq was resolvable when this gate ran — not proof the hook fires where your client spawns it"
  else
    warn "context-floor hook wired but inert: jq was not resolvable when this gate ran, and hooks/context-floor.sh exits 0 without jq — the floor is silently off. Fix: install jq"
  fi
}

# freshness: `find X -newer Y` reads full sub-second mtime (bash 3.2's `[ a -nt b ]` truncates
# to whole seconds and mis-orders files placed <1s apart). Fails
# CLOSED on an exact tie (equal mtime = NOT fresh).
#
# ⚠ mtime IS NOT EVIDENCE OF CONTENT, and under a sync daemon it is barely evidence
# of anything at all: such a daemon rewrites and re-touches
# files it did not change. A freshness-only row
# here false-PASSES *by construction*, not by accident: a gate can print
# `✓ ROADMAP.md updated this phase` while a grep for the phase identifier returns 0.
# So: where the artifact's CONTENT can be checked, check the content — `fresh()` is only
# for rows where nothing but recency is being claimed, and those rows must SAY so in their
# ✓ text. Do not reintroduce `fresh`-only as proof that a ceremony was performed.
fresh() { [ -e "$1" ] && [ -e "$2" ] && [ -n "$(find "$1" -newer "$2" -print 2>/dev/null)" ]; }

# Stamp a temp file's mtime to a commit's committer-date. --date=format-LOCAL renders the digits
# in THIS machine's timezone — exactly how `touch -t` interprets them. (Plain --date=format:
# renders in the commit's OWN offset, which touch -t then misreads as local time — a cross-tz
# freshness bug that can false-PASS stale docs or false-FAIL fresh ones. format-local sidesteps
# it and stays BSD-touch-safe, unlike a GNU-only `touch -d @epoch`.)
#
# ⚠ `touch -t` accepts whole seconds only, so the stamped mtime is the committer-date TRUNCATED
# down to its second. A file written earlier in that same second carries a larger sub-second mtime
# and so reads `fresh` — a ≤1s fail-OPEN window. Benign for the ONLY remaining consumer, BPREF
# (the branch-point commit): a phase artifact is written after `git checkout -b`, never within the
# same second as the merge-base commit it is compared against, so the tie cannot occur in a real
# run. The row where the window WAS reachable (test-evidence, once compared to a HEAD-second ref)
# no longer uses mtime at all — it fingerprints content (row 7). If a future `fresh()` consumer
# ever compares against a reference that CAN fall within 1s of the artifact, give it sub-second
# resolution instead of `touch -t` (e.g. a feature-detected GNU `touch -d @<epoch.frac>`); do not
# assume this truncation stays harmless.
stamp_ref() { touch -t "$(git show -s --format=%cd --date=format-local:%Y%m%d%H%M.%S "$1")" "$2"; }

# Branch-point ref: a docs artifact written DURING this phase is newer than the commit the branch
# forked from. Fail CLOSED if origin/main can't be resolved — the old genesis-commit fallback made
# every freshness check trivially pass (anything postdates the repo's first commit → false PASS).
BP="$(git merge-base origin/main HEAD 2>/dev/null || true)"
[ -n "$BP" ] || { echo "✗ cannot resolve 'git merge-base origin/main HEAD' — fetch origin/main before running the gate"; exit 1; }
# --- The gate publishes its own completion signal ------------------------------------
# Detecting "a close gate ran" by word-matching a bare gate-script
# token in ANY Bash command would count `wc -l` on this file and `git add` of this file each as
# a phase close.
# Reading a file about the gate is not the gate running, and nothing about a token scan
# can tell the two apart. The gate is a script this project owns, so it states the fact rather
# than being guessed at.
#
# Deliberately NOT an mtime, and not "the file exists": a checked-out tree may live under a file-syncing
# directory whose daemon re-touches files (the same reasoning drove the
# nonce in hooks/tasklist-first.sh). Identity comes from a per-RUN id the reader compares against
# what it last saw, so a marker left by an earlier run cannot be mistaken for a new one.
#
# Both outcomes are recorded, with the exit code. A gate that RAN AND FAILED is a different fact
# from a gate that never ran, and flattening the two is the defect this check exists to remove —
# the consumer decides what to do with each. (Today: hooks/tasklist-first.sh re-arms only on
# exit=0.)
GATE_RUN_DIR=".claude/.gate-runs"
GATE_MARKER="$GATE_RUN_DIR/last-run"
GATE_RUN_ID="$$-$(date +%s 2>/dev/null || echo 0)"
write_gate_marker() {
  _ec="${1:-1}"
  mkdir -p "$GATE_RUN_DIR" 2>/dev/null || return 0
  # The directory ships its OWN ignore entry — the pytest / mypy / husky pattern — so an adopter
  # never commits machine-local run state without having to edit anything first.
  [ -s "$GATE_RUN_DIR/.gitignore" ] || printf '*\n' > "$GATE_RUN_DIR/.gitignore" 2>/dev/null || true
  _tmp="$GATE_MARKER.$$.tmp"
  {
    printf 'run=%s\n'   "$GATE_RUN_ID"
    printf 'exit=%s\n'  "$_ec"
    printf 'phase=%s\n' "$PHASE"
    printf 'head=%s\n'  "$(git rev-parse HEAD 2>/dev/null || echo unknown)"
    printf 'at=%s\n'    "$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)"
  } > "$_tmp" 2>/dev/null || { rm -f "$_tmp" 2>/dev/null || true; return 0; }
  # write-temp-then-rename: POSIX rename() is atomic and keeps the destination name visible
  # throughout, so a reader sees either the previous marker or the new one, never a partial file.
  mv -f "$_tmp" "$GATE_MARKER" 2>/dev/null || rm -f "$_tmp" 2>/dev/null || true
}

# register the cleanup trap right after the mktemp so a later abort can't leak the temp file.
# `_gec=$?` MUST be the trap's first statement — anything before it clobbers the status being
# recorded. The trap (rather than a line at each exit point) is what makes the marker survive an
# early `set -e` abort or a signal: those paths are exactly the ones a final-line write misses.
#
# `$JSLICE` (the archived-fragment slice, created far below) is removed here too, and NOT at the
# point of use: the slice stays `$J` for the whole run, so there is no in-body line where deleting
# it would be correct. `${JSLICE:+…}` expands to nothing while the variable is still empty, which
# is its state on every run that never reaches the archive path.
# THE TRAP CANNOT LEARN THE EXIT STATUS FROM `$?`, AND THAT IS MEASURED, NOT ASSUMED.
# On bash 3.2.57 (what macOS ships, and what this gate is written for) an abort from `set -u`
# enters the EXIT trap with `$?` ALREADY 0. Probe:
#
#     trap '_g=$?; echo "TRAP SAW $?=$_g"' EXIT; set -euo pipefail; : "$UNBOUND"
#     -> "TRAP SAW $?=0", script exit 0
#
# So the old trap did two wrong things at once, and the second is worse than the exit code:
# the script exited **0** out of a half-finished run, AND `write_gate_marker` was handed **0**,
# recording a SUCCESS for a run that never reached a verdict. The obvious repair -- ending the
# trap with `exit "$_gec"` -- DOES NOT WORK for this shape and was measured failing before it
# was discarded: `_gec` is already 0, so exiting with it exits 0.
#
# THE FIX IS A POSITIVE MARK, NOT AN INFERENCE. `GATE_VERDICT_REACHED` is set to 1 only on the
# line immediately before the two explicit verdict exits, so its absence means control never got
# there -- for ANY reason, including ones nobody has thought of. The general rule:
# a success signal must be something the successful path WRITES, never something the failure path
# happens not to have disturbed.
#
# 90 is deliberate: it means "the check did not reach its own summary".
# A half-run gate is not a FAILING gate
# (exit 1 means "gate ran and judged: no") and must not be reported as one.
# IT ONLY OVERRIDES A ZERO, and that restraint is deliberate rather than chosen for elegance.
# Making EVERY unfinished run exit 90 would erase a diagnostic: this
# gate dies **127** when `jq` is unresolvable, and 127 tells "died on jq" from "died on
# something else". Flattening it to 90 would discard a real diagnostic to fix a problem 127 never had.
# So a non-zero status already says "did not succeed" and passes through untouched; 90 substitutes
# only for the case that is actually broken -- a ZERO with no verdict behind it.
GATE_VERDICT_REACHED=0
BPREF="$(mktemp)"; trap '_gec=$?; [ "${GATE_VERDICT_REACHED:-0}" = 1 ] || [ "$_gec" -ne 0 ] || _gec=90; write_gate_marker "$_gec"; rm -f "$BPREF" ${JSLICE:+"$JSLICE"}; exit "$_gec"' EXIT
stamp_ref "$BP" "$BPREF"
# (A HEAD-committer-date ref used to be stamped here for the test-evidence row's mtime freshness
# check. That row now compares a content fingerprint instead (row 7), so the HEAD ref had
# no remaining reader and was removed: a stamped reference that nothing consumes reads as a check
# that still runs when it does not — the exact honest-guards defect this design removes.)

# THREE dots, and that is load-bearing. For `git diff` two dots is not a commit range at all —
# `git diff A..B` is plain `git diff A B`, a tree-to-tree comparison. So on a branch that does
# not contain origin/main's tip, everything origin/main gained meanwhile shows up here IN
# REVERSE (as this branch deleting it): a file someone else added under skills/ matched the
# product-path test, and a docs-only branch was blocked and told to add a CHANGELOG entry for a
# file it never touched. `A...B` is `git diff $(git merge-base A B) B` — the branch's own
# changes and nothing else, which is the only thing this gate has standing to judge. (Same
# commit as $BP above; the symbolic form is used so every message that prints $RANGE stays
# readable instead of naming a bare SHA.)
RANGE="origin/main...HEAD"

# --- the declared product tree, and what THIS diff touches ------------------------------
# Hoisted above the rows because TWO consumers need the same answer: check 1 ("did this phase
# ship a product change?") and the diff TRIGGER ("does this diff owe the CHANGELOG + test-evidence
# rows at all?"). One resolution, one match computation, both consumers reading the same two
# variables — so the check-set line printed below cannot claim something different from what the
# rows are actually gated on. (A printed claim that CAN disagree with the logic it
# describes is the same true-but-shallow shape row 7 was repaired for. It is structurally
# prevented here, not asserted.)
#
# Gate on the JSON *type* first: `.product_paths[]?` also iterates an OBJECT's values, so a
# `{"a":"skills/"}` typo would silently run on those instead of failing closed. Only a non-empty
# ARRAY takes the read branch; an absent key (type "null") falls back to this repo's default
# tree; anything else leaves the list EMPTY, which check 1 turns into a ✗ in every mode.
PP_TYPE="$(jq -r '.product_paths | type' "$M" 2>/dev/null || echo null)"
# Why the list is unusable, in the manifest's own terms. The old fail-closed message said
# "present but empty or not a JSON array" for EVERY cause, including a sole `"/"` entry — which
# is present, non-empty AND well-typed, so the message named three things that were all false
# and the real fault (see pp_is_root below) went unnamed.
PP_BAD_WHY=""
if [ "$PP_TYPE" = array ] && PP_LIST="$(jq -r '.product_paths[]' "$M" 2>/dev/null)" && [ -n "$PP_LIST" ]; then
  PP_ENTRIES="$PP_LIST"
elif [ "$PP_TYPE" = null ]; then
  # absent key → this repo's default tree. Written as ENTRIES (not as a ready-made alternation)
  # so the default goes through the exact same escaping and matching path as a declared list —
  # a second hand-written form of the same list is how two copies drift apart.
  PP_ENTRIES='skills/
commands/
scripts/
.claude-plugin/'
else
  PP_ENTRIES=""   # present but not a non-empty array (object / string / empty array) → fail-closed
  if [ "$PP_TYPE" = array ]; then
    PP_BAD_WHY="it is a JSON array, but empty (or every entry is an empty string)"
  else
    PP_BAD_WHY="it is JSON type '$PP_TYPE', not a JSON array of path strings"
  fi
fi

# Normalise, then escape. Trailing slashes are stripped so `skills/`, `skills` and `skills//`
# are one entry; then EVERY ERE metachar is escaped (not just `.`, so an adopter path like
# `c++/` or `app(v2)/` can't reach grep -E raw and false-FAIL).
pp_norm()  { printf '%s' "$1" | sed -e 's#/*$##'; }
pp_regex() { pp_norm "$1" | sed -e 's#[][(){}.^$*+?|\\]#\\&#g'; }
# ROOT declarations. An entry that normalises to empty (a sole `/`) or to `.` (`.` or `./`) is
# a flat-layout adopter saying "the product tree IS this repo", and BOTH used to fail silently
# in opposite directions: `pp_regex(".")` gave `^\./`, which no `git diff --name-only` path can
# ever match (they are repo-relative and carry no `./` prefix), so the entire enforcement
# boundary vanished with no sound and checks 2/7/9 were off forever; a sole `/` normalised to
# the empty string and fell into the fail-closed arm above, which then blamed a manifest that
# is present, non-empty and well-typed. Neither is a manifest the adopter needs to fix — the
# intent is unambiguous — so both mean match-everything, and the report names them explicitly
# (a boundary that covers the whole tree is exactly the kind of fact a reader must not have to
# infer from a bare entry name).
pp_is_root() { _n="$(pp_norm "$1")"; [ -z "$_n" ] || [ "$_n" = "." ]; }

PP_DISPLAY=""; PP_MATCHED=""; PP_ROOT_NOTES=""
# `-c core.quotePath=false`: with git's DEFAULT quotePath, any path containing a non-ASCII byte
# comes back C-quoted — `skills/café.md` prints as `"skills/caf\303\251.md"`, whose first
# character is a double quote, so `^skills/` never matches. Enforcement would be silently off
# for that path AND the check-set line below would print `[none]` about a diff that plainly touched
# the product tree. Belongs on every `--name-only` read that feeds a path match; this is the
# only one in this gate, and a new one must carry it too.
CHANGED_FILES="$(git -c core.quotePath=false diff --name-only "$RANGE" 2>/dev/null || true)"
if [ -n "$PP_ENTRIES" ]; then
  PP_DISPLAY="$(printf '%s\n' "$PP_ENTRIES" | paste -sd' ' -)"
  # WHICH declared entries the diff touched, not just whether any did: the check-set line names them on every
  # run, so a stale or too-narrow product_paths is visible instead of silently under-firing.
  # Per-entry rather than one
  # `^(a|b|c)/` alternation because an alternation cannot say which arm matched; the union of
  # these tests is identical to that alternation by construction.
  while IFS= read -r _pp; do
    [ -n "$_pp" ] || continue
    if pp_is_root "$_pp"; then
      # Every changed path is inside the repo root, so "did the diff touch this entry?" is
      # exactly "is the diff non-empty?" — no regex can express that more honestly.
      PP_ROOT_NOTES="${PP_ROOT_NOTES:+$PP_ROOT_NOTES }$_pp"
      # an `if`, not `[ … ] && PP_MATCHED=…`: a trailing false AND-list leaves $? = 1 for
      # whatever reads it next (the hazard already written up at EV_SET below).
      if [ -n "$CHANGED_FILES" ]; then
        PP_MATCHED="${PP_MATCHED:+$PP_MATCHED }$_pp"
      fi
      continue
    fi
    # `grep -c … || true` then `-gt 0`, NEVER `grep -q`. `grep -q` exits at the FIRST match;
    # `printf` is then killed by SIGPIPE (141), and `set -o pipefail` makes 141 the PIPELINE's
    # status — so a MATCH reads as a non-match on any diff whose path list outruns the pipe
    # buffer (~64KB). Example: a diff whose FIRST path is the matching one (the match lands on
    # line 1 with the rest of the list unread) prints `touched by … [none]` and PASSES --
    # exactly the hole this row closes.
    # `grep -c` drains its input, so there is no early exit and no SIGPIPE. Check 2 below has
    # always used this idiom; the warning that said so was lost with an earlier rewrite of this
    # block, which is how `grep -q` got here.
    #
    # `(/|\$)` rather than a hard-appended `/`: an entry naming a FILE (`Makefile`) has to match
    # itself, or it silently matches nothing forever — while a directory entry must still match
    # only its CONTENTS, so `skills` must not match `skills-old/x.md`.
    if [ "$(printf '%s\n' "$CHANGED_FILES" | grep -cE "^$(pp_regex "$_pp")(/|\$)" || true)" -gt 0 ]; then
      PP_MATCHED="${PP_MATCHED:+$PP_MATCHED }$_pp"
    fi
  done <<PP_EOF
$PP_ENTRIES
PP_EOF
fi
DIFF_TOUCHES_PRODUCT=0
if [ -n "$PP_MATCHED" ]; then DIFF_TOUCHES_PRODUCT=1; fi

# --- which check-set this mode runs, and why ---------------------------------------------
# ONE table, read by the rows below AND by the report printed right after it.
#
#   1 product-tree change    — a MODE PRECONDITION (task/phase), never an any-branch obligation
#   2 CHANGELOG [Unreleased] — any branch whose diff touches product_paths (and every phase close)
#   3 spec · 4 plan · 5 journal · 6 ROADMAP — all four presuppose a phase exists
#   7 test-evidence          — same trigger as 2
#   9 rationale              — rides with 7. It is the argument for 7's OWN input list, so
#                              running it where 7 does not run would check a key nothing
#                              consumed on that run.
#   8 declared invariants    — EVERY branch, always (each one is a property
#                              of the working tree and cheap to run, and at least
#                              one — no-icloud-conflict-copies — guards an artifact that appears
#                              with nobody editing anything, so a docs-only branch is exactly
#                              where it must fire). Deliberately NOT gated on product_paths.
RUN_PRODUCT_TREE=0; RUN_CHANGELOG=0; RUN_PHASE_DOCS=0; RUN_JOURNAL=0; RUN_ROADMAP=0; RUN_EVIDENCE=0; RUN_AC=0
RUN_DIVERGENCE=0
RUN_CLOSURE_DECL=0
SKIP_WHY=""
case "$MODE" in
  phase)
    RUN_PRODUCT_TREE=1; RUN_CHANGELOG=1; RUN_PHASE_DOCS=1; RUN_JOURNAL=1; RUN_ROADMAP=1; RUN_EVIDENCE=1; RUN_AC=1
    RUN_DIVERGENCE=1
    # 11 is PHASE-ONLY, and not for cost. What a phase closes is only knowable when it is
    # closing: a phase's first task cannot know what the phase will close, so running this on
    # the push path would demand an answer that does not exist yet. It must never be on that path.
    RUN_CLOSURE_DECL=1
    SKIP_WHY="nothing skipped — phase close runs every declared check"
    ;;
  task)
    RUN_PRODUCT_TREE=1; RUN_JOURNAL=1; RUN_EVIDENCE=1; RUN_AC=1
    # 9b stays OFF here, and the reason is not its cost. `task` is what the PRE-PUSH hook
    # runs, and git opens the connection and negotiates refs BEFORE it runs pre-push -- so the
    # hook's whole duration is idle time on an already-open socket. A slow enough hook -- 9b takes
    # minutes on a diff touching the pinned hook -- gets the push killed by the remote:
    # `Connection to github.com closed by remote host` / rc 141 (SIGPIPE), over SSH and
    # HTTPS alike. Reasoning about SLOWNESS alone misses it: the effect on
    # the diffs it actually fires for is not a slow push but an IMPOSSIBLE one -- and a gate that
    # cannot be satisfied is worse than a slow one, because the only way past it is the
    # `--no-verify` no gate should be designed toward.
    # Coverage is unchanged: 9b runs in `phase` (the pre-merge gate, invoked by hand with no
    # socket held open).
    SKIP_WHY="2/3/4/6 are phase-close artifacts one cadence task does not produce — \`close-gate.sh phase $PHASE\` checks them before the merge; 9b is held off the push path and runs at phase close when the differential harness is in the tree"
    ;;
  diff)
    if [ "$DIFF_TOUCHES_PRODUCT" = 1 ]; then
      RUN_CHANGELOG=1; RUN_EVIDENCE=1
      SKIP_WHY="1/3/4/5/6 each need a phase (product-tree precondition, spec, plan, journal FACT, ROADMAP row) and this branch has none"
    elif [ -z "$PP_ENTRIES" ]; then
      # A DIFFERENT cause, and it must not be reported as the one below. "nothing matched" sends
      # the reader to audit their own diff; "nothing COULD match" sends them to the manifest,
      # which is where the fault actually is. The row below fails closed and names it.
      SKIP_WHY="1/3/4/5/6 each need a phase and this branch has none; 2/7/9 did not fire because product_paths is UNUSABLE (✗ below), so nothing could have matched it — this is NOT a statement about what this diff touched"
    else
      SKIP_WHY="1/3/4/5/6 each need a phase and this branch has none; 2/7/9 did not fire because this diff touches NONE of the declared product_paths — if that is wrong, the declared list below is stale, which is the failure this line exists to make visible"
    fi
    ;;
esac

# Declared-invariant COUNT, read here rather than at check 8 because the check-set label below
# has to state it. `8(invariants)` printed unqualified even when the manifest declares
# `invariants: []` and the very next line says it is skipping the run — a label that reads as
# "the invariants ran" when there are none to run. Display only; check 8 does its own reads and
# its own fail-closed handling of a malformed value.
INV_DECLARED="$(jq -r 'if (.invariants|type)=="array" then (.invariants|length|tostring) elif has("invariants") then "malformed" else "0" end' "$M" 2>/dev/null || echo unknown)"
[ -n "$INV_DECLARED" ] || INV_DECLARED=unknown

# skip-escape-hatch: an exempt_* flag is only legit if a 'SKIP: <reason>' line is in the newest journal.
JD="$(g retention.journal_dir)"; JD="${JD:-docs/journal.d}"
# `|| true` on BOTH the pipeline and the assignment: with no *.md fragment (brand-new phase, or
# the dir absent), the glob doesn't expand, `ls` exits non-zero, and under `pipefail` the pipeline
# reports that — an unguarded `J="$(...)"` under `set -e` would then kill the script silently,
# before any ✗ row prints, on the exact "journal not written yet" case the gate must report.
newest_journal() { ls -t "$JD"/*.md 2>/dev/null | head -1 || true; }
# Prefer the fragment that NAMES this phase over the merely-newest one. `ls -t` is an mtime
# proxy for "the fragment this phase wrote", and it is wrong whenever a fragment from another
# phase is newer — a leftover, a parallel branch, or a sync-daemon re-touch. When that happens the
# FACT-field and Plan-deviations rows below are judged against the WRONG file, which can both
# false-FAIL a correct phase and false-PASS an incomplete one. Fragments are named
# `<date>-phase-<PHASE>-<slug>.md`, so identity is available; use it, and keep `ls -t` only as
# the fallback for projects whose fragments predate that convention.
# Within ONE phase's fragments, take the LAST BY NAME — not `head -1` (which took the
# earliest, so a phase that wrote a stub early and its real FACT entry later was judged on
# the stub) and deliberately not `ls -t`. Fragments are `<date>-phase-<id>-<slug>.md`, so the
# name already carries the ordering, and a name is something a background sync daemon cannot
# rewrite. Using mtime to order a phase's own fragments would reintroduce exactly the
# dependence this gate is being cured of.
phase_journal() { ls "$JD"/*phase-"$PHASE"-*.md 2>/dev/null | tail -1 || true; }
J="$(phase_journal || true)"
# FALLBACK IS NOT A SUBSTITUTE. If the phase has no fragment of its own, `ls -t` picks the
# newest fragment belonging to some OTHER phase, and every row below then judges that file —
# printing ✓ FACT / ✓ Plan-deviations for a phase that wrote no journal at all. The fallback
# exists only for repos whose fragments predate the `-phase-<id>-` naming convention, so it
# is allowed ONLY when no fragment in the directory carries that convention at all. Anything
# else is a missing journal, and must be reported as one.
# After the mandated milestone-close drain the fragment is GONE from $JD by design
# (`references/retention.md`: "the hot directory drains to zero"), so this row used to demand an
# artifact another mandated step deletes, and said "write this phase's FACT entry" about an entry
# that was written and archived.
#
# It is not only a close-time annoyance: this row runs in TASK mode too, and the pre-push hook runs
# task mode on every push of a feat/phase-* branch — so a drained branch could not be pushed at all,
# while the Stop hook kept advising the operator to run the command that could not pass.
#
# THIS BLOCK MUST STAY ABOVE THE JFALLBACK BLOCK BELOW. That fallback fires exactly when no
# `*phase-*.md` exists in $JD, which is precisely the post-drain state; placed after it, `J` would
# already hold whatever file happened to be newest by mtime and this lookup would never run on the
# case it exists for. A leftover draft — or an iCloud `" 2"` phantom copy — would then be judged
# instead, and the rows would print green about a file belonging to nothing.
AD="$(g retention.archive_dir)"; AD="${AD:-docs/archive}"
JARCHIVE=""; JSLICE=""; JFENCED=""
# The SLICE, never the whole file: from this phase's sentinel to the line before the next one
# (or EOF when it is the last). A whole-file read would let ANOTHER phase's complete FACT
# fields turn these rows green — the same "FALLBACK IS NOT A SUBSTITUTE" failure documented
# above, arriving through a different door. The `[-.]` accepts the slugless fragment name too.
#
# A SENTINEL IS A POSITION, NOT A STRING. Scanning for the literal marker cannot tell a fragment
# boundary written by `drain_journal` from a line that merely QUOTES that format — a code block in
# some other phase's archived entry showing what a sentinel looks like, and naming this phase while
# it does so, redirected the slice and printed `✓ journal FACT entry read from the archived slice`
# over that other phase's content. Measured end-to-end as exit 0 / `close-gate PASS` for a phase
# that wrote no journal at all. So a line counts as a boundary only when BOTH hold — not either:
#   (a) it is outside a fenced code block, and
#   (b) it is preceded by a blank line, or is the first line of the file.
# Both are faithful to the writer rather than defensive guesses: `drain_journal` emits
# `printf '\n<!-- fragment: %s -->\n'`, so a genuine sentinel always has a blank line above it and
# is never inside a fence.
#
# THE FENCE TRACKER IS MATCHED, NOT COUNTED. Toggling one flag on `^(```|~~~)` is wrong:
# in markdown a block opened with ``` is closed only by
# ```, and a `~~~` line inside it is literal content. So a single ``` block quoting a `~~~` line
# would invert the flag for the REST OF THE FILE, with both directions reachable on the
# real gate — the phase's own genuine sentinel becoming invisible (`✗ write this phase's FACT
# entry`, and because row 5 runs in task mode, an unpushable branch), and a neighbouring phase
# collecting someone else's FACT fields for a `close-gate PASS`. A parity counter is a claim
# wider than its mechanism; the mechanism has to be delimiter identity.
#
# A delimiter MATCHER — remember the opening run's character and
# length, close only on the same character, at least as long, with nothing but whitespace after it
# — is still a claim wider than its mechanism if it is FILE-scoped, because the
# writer is FRAGMENT-scoped. `drain_journal` concatenates
# independently-authored fragments, so one fragment's unterminated fence is closed by a LATER
# fragment's ordinary opener, and every genuine sentinel in between is marked as fenced.
#
# WHAT THIS PARSER CLAIMS, AND IT IS THE ONLY THING IT CLAIMS: **every ambiguity costs a FAIL,
# never a PASS.** It is not a markdown parser and does not pretend to be one. Three rules, each
# chosen because its error direction is fail-safe:
#
#   1. A boundary is accepted only when the fence state is CLOSED at it. An unterminated fence is
#      therefore NOT discarded — it propagates, and every following boundary in that archive stops
#      being readable. That is a loud, diagnosable false FAIL (exit 2 below names the archive), not
#      a silent misread. The alternative — discarding an open fence at each candidate — is exactly
#      what lets a fence containing TWO quoted sentinels have its second one accepted, which is a
#      false PASS. Between an unreadable archive and a forged one, this gate takes unreadable.
#   2. A slice ENDS at any candidate sentinel line, fenced or not. Ending early can only make the
#      gate demand more; running long is how one phase collects another's FACT fields. This is what
#      kills the second direction outright rather than by parsing correctly.
#   3. A sentinel-shaped line naming this phase that was rejected as fenced is REPORTED (exit 2),
#      not swallowed. The message is neutral about which case it is — a genuinely quoted example,
#      or a real boundary hidden behind an unclosed fence upstream — because the gate cannot tell,
#      and saying which would be the same over-claim a third time.
#
# DECLARED LIMITS: fences are recognised at column 1 only (no leading-space indent), backticks and
# tildes only; an unterminated fence costs every boundary after it in that archive, loudly.
#
# The FILE SELECTION below runs through this same function, deliberately: a plain `grep -qE`
# would have the identical blind spot one layer up, so a quoted sentinel could point the gate at the wrong
# archive file entirely. Selection succeeds only when the slicer itself reports a genuine boundary
# for this phase (its exit status), NOT when the slice is merely non-empty — a real fragment with
# an empty body must still select its file, so the FACT rows below report the missing entry instead
# of the gate reporting a missing journal.
journal_slice() {
  awk -v pat="phase-$2" '
    # The length of the delimiter run this line opens with, or 0 if it is not a fence line.
    function frun(s) { if (match(s, /^(`+|~+)/) && RLENGTH >= 3) return RLENGTH; return 0 }
    # A closer for an open <ch>-fence of length <ln>: same character, at least as long, and
    # NOTHING but whitespace after it — ``` done and ```sh are content and openers, not closers.
    function fclose(s, ch, ln,   r) {
      r = frun(s)
      if (!r || substr(s, 1, 1) != ch || r < ln) return 0
      return (substr(s, r + 1) ~ /^[[:space:]]*$/)
    }
    BEGIN { fopen = 0; prevblank = 1; inb = 0; found = 0; fenced = 0 }
    {
      if (prevblank == 1 && $0 ~ /^<!-- fragment: /) {
        k = index($0, pat)
        after = (k > 0) ? substr($0, k + length(pat), 1) : ""
        nm = (k > 0 && (after == "-" || after == ".")) ? 1 : 0
        if (fopen == 0) {
          # ACCEPTED boundary. It both ends the previous slice and opens this one; the sentinel
          # line itself is never body.
          inb = nm
          if (nm) found = 1
          prevblank = 0
          next
        }
        # REJECTED — sentinel-shaped, but inside a fence. Rule 2: it still ENDS the open slice,
        # so no slice can ever reach into the next fragment. Rule 3: if it names this phase, say
        # so rather than dropping it silently. The line then falls through as ordinary body.
        if (nm) fenced = 1
        inb = 0
      }
      if (fopen == 0) { r = frun($0); if (r) { fopen = 1; fchar = substr($0, 1, 1); flen = r } }
      else if (fclose($0, fchar, flen)) fopen = 0
      if (inb) print
      prevblank = ($0 ~ /^[[:space:]]*$/) ? 1 : 0
    }
    END { exit(found ? 0 : (fenced ? 2 : 1)) }
  ' "$1"
}
if [ -z "$J" ]; then
  for _a in "$AD"/journal/*.md; do
    [ -f "$_a" ] || continue
    _js="$(mktemp)" || { echo "✗ mktemp failed"; exit 1; }
    journal_slice "$_a" "$PHASE" > "$_js" && _jrc=0 || _jrc=$?
    if [ "$_jrc" -eq 0 ]; then
      JARCHIVE="$_a"; JSLICE="$_js"; J="$JSLICE"; break
    fi
    # exit 2: a line naming this phase exists in that archive but sits inside a code fence. Kept
    # for the ✗ row below so the operator is told WHERE to look instead of being told the entry
    # does not exist — the two are very different repairs.
    [ "$_jrc" -eq 2 ] && JFENCED="${JFENCED:-$_a}"
    rm -f "$_js"
  done
fi

JFALLBACK=0
# `*phase-*` (no trailing `-*`): a slugless `<date>-phase-<id>.md` still USES the
# convention, and requiring a slug sent it to the fallback the narrowing exists to stop.
#
# This is deliberately the OPPOSITE strictness of close-gate-prepush.sh's branch-name
# check. A journal filename is an ARTIFACT this gate is looking for, not an input it parses —
# being strict here would reject a file that exists and is correct, and push the gate onto the
# cross-phase fallback below, which judges some OTHER phase's fragment. A branch name, by
# contrast, IS an input the gate parses to decide what to check, so an ambiguous one silently
# produces the WRONG check; rejecting it there costs the pusher one `git branch -m` and is
# caught before any work runs.
#
# Strictness is cheap on the input side and expensive on the artifact side.
if [ -z "$J" ] && ! ls "$JD"/*phase-*.md >/dev/null 2>&1; then
  J="$(newest_journal || true)"
  [ -n "$J" ] && JFALLBACK=1
fi
skip_logged() { [ -n "$J" ] && grep -qE '^[[:space:]]*SKIP:' "$J" 2>/dev/null; }

echo "── close-gate $MODE${PHASE:+ $PHASE} (gitignored-docs mode) ──"

# EVERY run says which check-set it ran and why anything was skipped — there is no path
# out of this script that exits 0 in silence. The documented GitHub-Actions pathology is the
# reason: a required check skipped by a filter is indistinguishable from one that passed, and
# the field's fix is to always run and filter INSIDE. Without this, diff mode would reproduce that
# silent-degrade class on exactly the branches it newly covers.
#
# The labels are derived from the SAME RUN_* flags that gate the rows — there is no second list
# to keep in sync.
#
# That only holds while every row branches on those flags: rows gated on
# `[ "$MODE" = phase ]` while only this printer reads RUN_PHASE_DOCS / RUN_ROADMAP would make those
# variables the second list, and a mutant making the printer claim a row ran in a mode where it
# does not would survive the entire suite. The rows
# below branch on the same flags, so a mutation here changes behaviour and gets caught.
# Keep it that way: a row gated on $MODE directly re-creates the divergence.
CS_RAN=""; CS_SKIPPED=""
cs() { if [ "$1" = 1 ]; then CS_RAN="${CS_RAN:+$CS_RAN }$2"; else CS_SKIPPED="${CS_SKIPPED:+$CS_SKIPPED }$2"; fi; }
cs "$RUN_PRODUCT_TREE" "1(product-tree)"
cs "$RUN_CHANGELOG"    "2(CHANGELOG)"
cs "$RUN_PHASE_DOCS"   "3(spec)"
cs "$RUN_PHASE_DOCS"   "4(plan)"
cs "$RUN_JOURNAL"      "5(journal)"
cs "$RUN_ROADMAP"      "6(ROADMAP)"
cs "$RUN_EVIDENCE"     "7(test-evidence)"
cs 1                   "8(invariants:$INV_DECLARED)"
cs "$RUN_EVIDENCE"     "9(rationale)"
# Reads the SAME flag the row branches on. Writing `[ "$MODE" = phase ]` in either place would
# recreate exactly the second list this printer's own header (above) records two mutants escaping
# through.
cs "$RUN_DIVERGENCE"   "9b(divergence-records)"
cs "$RUN_AC"           "10(ac-oracle-binding)"
# Reads the SAME flag the row branches on, for the reason 9b records one line up.
cs "$RUN_CLOSURE_DECL" "11(closure-declaration)"
echo "check-set ($MODE): running ${CS_RAN:-none}"
echo "check-set ($MODE): skipped ${CS_SKIPPED:-none} — $SKIP_WHY"
echo "check-set ($MODE): product_paths declared [${PP_DISPLAY:-<none: unusable product_paths>}] · touched by $RANGE [${PP_MATCHED:-none}]"
# Printed as its OWN line, not folded into the entry name above: a declared entry that covers
# the WHOLE tree is the widest possible enforcement boundary, and a reader must not have to
# infer that from a bare `.` in a bracketed list.
# (an `if`, not `[ … ] && echo`: a trailing false AND-list leaves $? = 1, which the next
# construct to read it would misinterpret — the hazard already written up at EV_SET below.)
if [ -n "$PP_ROOT_NOTES" ]; then
  echo "check-set ($MODE): product_paths entr(y/ies) [$PP_ROOT_NOTES] name the repo root, so each matches EVERY path in the diff (flat-layout declaration)"
fi

# 1. the phase's diff touched the product tree (content check, not commit verb).
#    The old `feat|fix` commit-verb test was a proxy: the deliverable here IS markdown under
#    skills/**, so a legit refactor-only phase (e.g. a skill-content-only phase) had to be mislabeled
#    `feat` to pass. Path-based asks the real question — did this phase change the product — so a
#    meta-only README typo correctly fails while an honest `refactor(skill):` passes. Paths are
#    manifest-driven (.product_paths[]) so an adopter with a different tree sets their own; an
#    absent key falls back to this repo's default, a malformed key fails closed.
#    The list itself, its escaping, and the per-entry match are resolved ABOVE because
#    they are now also the trigger for checks 2/7/9; this row only reports the answer.
#
#    This row is a MODE PRECONDITION (task/phase), not an any-branch obligation — a
#    `chore/` branch is not required to ship a product change, it is only required to declare
#    one properly when it does. Hence the RUN_PRODUCT_TREE gate.
if [ -z "$PP_ENTRIES" ]; then
  # Fail-closed in EVERY mode, `diff` included, and that is not merely tidiness: product_paths
  # is no longer just this row's input, it is the diff TRIGGER. An unusable list would otherwise
  # switch checks 2/7/9 silently OFF on a non-phase branch rather than failing one row loudly —
  # the enforcement boundary disappearing without a sound.
  #
  # The message names the ACTUAL cause ($PP_BAD_WHY) rather than reciting all three possible
  # ones. A sole `"/"` used to land here and be told it was "present but empty or not a JSON
  # array" — three claims, all false, about a manifest that needed no fixing at all; that entry
  # is now a root declaration (pp_is_root) and never reaches this arm.
  bad "product_paths in $M is unusable — $PP_BAD_WHY; it must be a non-empty JSON array of path strings. It is also the diff trigger for checks 2/7/9, so the check-set line above cannot be trusted either."
elif [ "$RUN_PRODUCT_TREE" = 1 ]; then
  if [ "$DIFF_TOUCHES_PRODUCT" = 1 ]; then
    ok "phase diff touches the product tree ($RANGE): $PP_MATCHED" product_diff
  else
    bad "no product-tree change in $RANGE — a phase must ship a product change (paths: ${PP_DISPLAY})" product_diff
  fi
fi

# 2. CHANGELOG.md [Unreleased] touched in range (tracked → git check).
#
# This is a PHASE-CLOSE artifact: one cadence task does not produce it, so `task` mode
# skips it. It has a second trigger — ANY branch whose
# diff touches the declared product tree. Without it, user-visible skill changes could ship
# from a `chore/…` branch with no CHANGELOG entry while a gate that only
# looked at branch NAMES said nothing. What obliges a changelog entry is changing the product, not being
# on a particular branch.
if [ "$RUN_CHANGELOG" = 1 ]; then
if [ "$(g exempt_changelog)" = true ]; then
  # The SKIP: line lives in the phase's journal fragment, so the exemption can only be AUDITED
  # that way where a phase exists. On a non-phase branch there is no fragment to carry one, and
  # demanding one there would turn a deliberate, manifest-declared, PR-reviewed exemption into
  # an unsatisfiable block on every non-phase push. The ✓ therefore says exactly what was
  # checked — the manifest flag, and nothing about a justification — instead of implying an
  # audit that did not happen.
  #
  # This ✓ used to add "no phase journal exists on this branch", which it INFERRED from
  # MODE=diff and never looked for. A phase fragment can perfectly well sit in the journal dir
  # on a non-phase branch, so that clause was a claim the row had no mechanism behind — the
  # same true-but-shallow shape row 7 was repaired for, in the message that was supposed to be
  # the narrow one. Deliberately NOT fixed by adding a journal lookup: the row's job is the
  # manifest flag, and a second mechanism would widen the claim rather than narrow it.
  if [ "$MODE" = diff ]; then
    ok "changelog exempt (manifest exempt_changelog=true) — no justification was checked" changelog
  else
    skip_logged && ok "changelog exempt (SKIP: logged)" || bad "exempt_changelog=true but no 'SKIP:' line in newest journal"
  fi
elif [ "$(printf '%s\n' "$CHANGED_FILES" | grep -cE '^CHANGELOG\.md$' || true)" -gt 0 ]; then
  ok "CHANGELOG.md touched in range" changelog
else bad "CHANGELOG.md not touched in $RANGE (add an [Unreleased] entry, or set exempt_changelog + SKIP:)"; fi
fi  # end check 2

# 3 + 4 are PHASE-CLOSE artifacts: the spec + plan docs. A single cadence task does not
# produce them, and a branch with no phase has no phase for them to describe, so only `phase`
# mode requires them.
#
# Gated on RUN_PHASE_DOCS, NOT on `[ "$MODE" = phase ]`. The two were equivalent by
# coincidence, which made RUN_PHASE_DOCS a printer-only variable — a second list, and the
# mutant that set it in `diff` mode made the check-set line claim rows 3+4 ran while they did
# not, surviving the whole suite. One flag, read by both.
if [ "$RUN_PHASE_DOCS" = 1 ]; then
# 3 + 4. spec + plan docs exist for the phase (LOCAL files).
if [ "$(g exempt_docs)" = true ]; then
  skip_logged && ok "spec/plan exempt (SKIP: logged)" || bad "exempt_docs=true but no 'SKIP:' line in newest journal"
else
  SPEC="$(g phase_docs_glob)"; PLAN="$(g plan_glob)"
  { [ -n "$SPEC" ] && glob_exists "$SPEC"; } && ok "spec doc exists ($SPEC)" || bad "no spec doc matching '$SPEC'"
  { [ -n "$PLAN" ] && glob_exists "$PLAN"; } && ok "plan doc exists ($PLAN)" || bad "no plan doc matching '$PLAN'"
fi
fi  # end phase-only (checks 3-4)

# 5. newest journal.d fragment: exists + fresh-vs-branch-point + FACT fields + Plan-deviations.
#    task AND phase: every pushed task owes a FACT entry. `diff` mode skips it — a branch
#    with no phase has no fragment to look for, and the fallback below would then judge some
#    OTHER phase's fragment, printing ✓ rows for work this branch never did.
if [ "$RUN_JOURNAL" != 1 ]; then
  :
elif [ -z "$J" ]; then
  bad "no journal fragment matching '*phase-$PHASE-*.md' under $JD/, and no archived slice for it under $AD/journal/ — write this phase's FACT entry" journal
  # Two very different repairs share that one ✗, so name the second one when it applies: a line
  # that DOES name this phase was found, inside a code fence. Either it is a quoted example (write
  # the entry) or a real boundary hidden behind an unclosed fence upstream (fix that fragment).
  # The gate cannot tell which, and says so rather than picking one.
  [ -n "${JFENCED:-}" ] && warn "a line naming phase $PHASE exists in $JFENCED but sits inside a code fence, so it is not read as a fragment boundary — either it is a quoted example, or an unterminated fence earlier in that file is hiding a real one"
else
  [ "$JFALLBACK" = 1 ] && warn "no '-phase-<id>-' fragment names exist in $JD/ — falling back to the newest file ($(basename "$J")); its rows below are judged by mtime, not by phase identity"
  if [ -n "$JARCHIVE" ]; then
    # Freshness is deliberately NOT asserted on this path. The archive's mtime belongs to the
    # drain, not to the phase, so an mtime comparison here would be a `✓` about evidence the gate
    # does not have. Say what was read.
    ok "journal FACT entry read from the archived slice in $JARCHIVE (drained; freshness not asserted — the archive's mtime is the drain's, not this phase's)" journal
  else
  fresh "$J" "$BPREF" && ok "journal fragment newer than the branch point, by mtime ($(basename "$J"))" journal \
    || bad "journal fragment $(basename "$J") is older than the branch point — write this phase's FACT entry" journal
  fi
  MISS=""
  for f in Decision Why Backing; do
    grep -qE "^[[:space:]]*[-*][[:space:]]+\*\*${f}:?\*\*" "$J" || MISS="$MISS $f"
  done
  [ -z "$MISS" ] && ok "journal FACT fields present (Decision/Why/Backing)" journal \
                 || bad "journal FACT entry missing field(s):$MISS" journal
  grep -qE '\*\*Plan deviations:?\*\*|^#{1,4}[[:space:]]*Plan deviations' "$J" \
    && ok "journal 'Plan deviations' header present" || bad "journal missing 'Plan deviations' header"
fi

# 6. ROADMAP.md exists + NAMES THIS PHASE (LOCAL file).
# TWO independent facts, both required — content AND recency.
#
#   content: the ceremony this row claims ("the roadmap reflects this phase") is only
#     observable in the file's text, so grep for the phase id.
#   recency: content alone is pre-satisfied by any row written in an EARLIER phase. Every
#     `planned` row in a real roadmap already names a phase that has not started, so a
#     content-only check greens before the work exists. So
#     this row AND-s with the freshness check; it never replaces it.
#
# The match is ANCHORED, not a bare substring: `grep -F` disables regex, it does NOT make a
# match whole-token, so `P9` would match a roadmap containing only `P99`. Collisions in any
# numbered namespace look like this: P3 in P33, P4 in P44..P49. Require a non-identifier
# character (or a line edge) on both sides. `[^0-9A-Za-z._-]` keeps `P48-P50` matchable as a
# whole while rejecting `P4` against `P48`. TWO DELIBERATE CONSEQUENCES, both verified:
# (a) an id ending a sentence (`... see P57.`) does NOT match, because `.` is excluded on
#     purpose — that exclusion is what keeps `1.2` out of `1.2.1`;
# (b) a GROUPED row (`| P51–P56 |`) does not satisfy its members — closing a bundled
#     phase means naming the bundle in the roadmap, which is the honest record anyway.
# grep -E is ERE, so the escape class must cover the ERE metacharacters (`+ ? ( ) { } |`) as well as the BRE ones — an id like `B|C` would otherwise be read as an
# alternation and match an unrelated row. No GNU-only `\b` (BSD grep).
# PHASE-CLOSE artifact: flipping the ROADMAP row is a phase-boundary act, not a per-task one,
# so `task` mode skips it; only `phase` mode requires it.
# Gated on RUN_ROADMAP, not on `[ "$MODE" = phase ]` — see the note at checks 3+4: the
# surviving mutant made the printer claim this row ran in every mode, and nothing reddened
# because the row read a different condition than the label did.
if [ "$RUN_ROADMAP" = 1 ]; then
if [ -f docs/ROADMAP.md ]; then
  if ! grep -qE "(^|[^0-9A-Za-z._-])$(printf '%s' "$PHASE" | sed 's/[][\.*^$/&+?(){}|]/\\&/g')([^0-9A-Za-z._-]|$)" docs/ROADMAP.md; then
    bad "docs/ROADMAP.md never mentions phase $PHASE — add its row and flip ✅/▶" roadmap_row
  elif ! fresh docs/ROADMAP.md "$BPREF"; then
    bad "docs/ROADMAP.md names phase $PHASE but has not been touched since the branch point — the row predates this phase, so it proves nothing about it"
  else
    ok "ROADMAP.md names phase $PHASE and was updated this phase" roadmap_row
  fi
else bad "docs/ROADMAP.md missing"; fi
fi  # end phase-only (check 6)

# 7. non-empty test-evidence that DEMONSTRABLY describes the current tree.
#    The gate does NOT run validate.py itself (jq-only envelope); the runner writes evidence,
#    the gate checks it. Skipped only when the manifest configures no test_evidence.
#
#    ⚠ NOT an mtime compare (evidence mtime vs HEAD's committer-date), deliberately.
#    mtime is not evidence of content, and in many trees it is barely evidence of anything: git
#    does not preserve mtime across checkout, and a file-sync daemon can re-touch files in place.
#    So this row checks CONTENT: the runner
#    stamps a fingerprint of validate.py's inputs into the evidence header (evidence_header,
#    top of file); the gate recomputes it and compares. Do not reintroduce an mtime compare.
#
#    In `diff` mode this row (and check 9 with it) fires only when the diff touches the
#    declared product tree — same trigger as check 2. The check-set line at the top of the run
#    says which way it went, so a skip here is never mistaken for a pass.
if [ "$RUN_EVIDENCE" = 1 ]; then
EV="$(g test_evidence)"
# Two different strings serve two different jobs.
#
#   REMEDIATION_CMD — the thing every failure message below tells the reader to TYPE. Always the
#   safe generator (gen-test-evidence.sh), NEVER the raw declared pipeline: the declared command
#   ends in a bare `{ ...; } | tee {EVIDENCE_FILE}`, and `tee` exits with ITS OWN status — a
#   reader who copy-pastes it gets a pipeline that silently overwrites a good evidence file with
#   a broken one while still exiting 0 (an upstream `evidence-header` hard-fail inside that `{
#   ...; }` group is masked by the `;` before it — bash keeps only the LAST command's status —
#   so even `pipefail` on the outer pipe would not have caught it; this is not the same failure
#   gen-test-evidence.sh's pipefail wrapping closes, it is the one underneath it).
#   gen-test-evidence.sh instead writes to a temp file and only moves it into place on success,
#   so this hazard cannot reach the real evidence file through it. A contract nobody is told how
#   to satisfy SAFELY is a trap, not a gate.
#
#   EVIDENCE_CMD — the declared command itself, shown for CONTEXT ONLY ("this is what the
#   generator runs"), never as an instruction to run directly. Declared in the manifest
#   (test_command, with {EVIDENCE_FILE} and {SET} placeholders — same substitution idiom `g()`
#   already uses for {PHASE}) instead of hardcoded here, so gate and manifest can never disagree
#   about what the runner does. `{SET}` is resolved to the CURRENT $MODE purely for this
#   display; gen-test-evidence.sh does the real resolution when it actually runs the command.
#
#   $MODE is NOT passed straight through: gen-test-evidence.sh takes the evidence header's `set`
#   value, whose domain is task|phase — `diff` is a gate mode, not a set value, and telling the
#   reader to run `gen-test-evidence.sh diff` would hand them a command that exits 1. A non-phase
#   branch's evidence is task-set evidence (row 7 does not compare the recorded set against the
#   mode it is run in — see evidence_header's comment), so `diff` maps to `task`.
#   (Written as an `if`, not `[ … ] && EV_SET=task`: under `set -e` a trailing false `&&` list is
#   the script's exit status and would abort the gate on every non-diff run.)
EV_SET="$MODE"
if [ "$MODE" = diff ]; then EV_SET=task; fi
REMEDIATION_CMD="/bin/bash scripts/gen-test-evidence.sh $EV_SET"
EVCMD_TMPL="$(g test_command)"
if [ -z "$EVCMD_TMPL" ]; then
  EVIDENCE_CMD="<test_command not declared in $M>"
else
  # Bash parameter expansion, not `sed`: sed's delimiter/backreference model makes a
  # `{EVIDENCE_FILE}` substitution unsafe for three character classes a real EVIDENCE_FILE path
  # could contain — a `&` in the replacement is a sed backreference (silently reinserts the whole
  # match, leaking the literal placeholder text into the command shown to the user instead of the
  # path), and a `#` or an embedded newline breaks the `s#...#...#g` delimiter and makes sed exit
  # non-zero, which under `set -e` aborts the whole gate instead of printing its `bad` row.
  # `${var//pat/repl}` has no delimiter and no metacharacter table, so none of the three apply.
  EV_DISPLAY="${EV:-<evidence-file>}"
  EVIDENCE_CMD="${EVCMD_TMPL//\{EVIDENCE_FILE\}/$EV_DISPLAY}"
  EVIDENCE_CMD="${EVIDENCE_CMD//\{SET\}/$EV_SET}"
fi
if [ -z "$EV" ]; then
  warn "no test_evidence configured in manifest — skipping the test-ran check"
elif [ ! -s "$EV" ]; then
  bad "empty/missing test-evidence $EV — run: $REMEDIATION_CMD (this is what it runs: $EVIDENCE_CMD)" test_evidence
else
  # First line must be the fingerprint header. A missing/garbled header is a HARD fail, never a
  # fallback to a weaker check: silently degrading is the defect class this check removes.
  #
  # EVDIG is deliberately LOOSE (captures the digest regardless of what follows it on the line)
  # so a header with a valid digest but a missing/garbled 'set=' field is distinguishable from a
  # header that has no digest at all — EVSET below is the STRICT, whole-line check that carries
  # that distinction ('set=<task|phase>' is on the SAME line and MANDATORY).
  EVDIG="$(sed -n '1s/^# plc-gate-evidence inputs=\([0-9a-f]\{40,64\}\).*$/\1/p' "$EV" 2>/dev/null)"
  # `-E` (ERE) here, not BRE like EVDIG above: `\|` alternation inside `\(...\)` is a GNU sed
  # extension that BSD/macOS sed's BRE mode does NOT support — it matches nothing there, silently
  # (on BSD sed, BRE `\(task\|phase\)` returns empty on a literal "task"). ERE's
  # `(task|phase)` has no backslash-alternation ambiguity and is portable to both sed families.
  EVSET="$(sed -E -n '1s/^# plc-gate-evidence inputs=[0-9a-f]{40,64} set=(task|phase)[[:space:]]*$/\1/p' "$EV" 2>/dev/null)"
  NOWDIG="$(evidence_digest)"
  if [ "${NOWDIG#EMPTY-}" != "$NOWDIG" ]; then
    # evidence_digest signalled that ZERO gate-relevant paths matched. Never a pass — a gate
    # that fingerprints nothing checks nothing. Loud, so a mis-scoped test_evidence_inputs (or a
    # repo restructure that renamed the manifests) surfaces instead of greening vacuously.
    bad "no gate-relevant paths matched in this repo — the manifest's test_evidence_inputs list does not fit this layout, so the test-evidence fingerprint checks nothing. Fix the list before trusting this row."
  elif sed -n '1p' "$EV" 2>/dev/null | grep -q '^# plc-gate-evidence inputs=EMPTY-'; then
    # The header line IS present, but it stores the EMPTY sentinel (this evidence was generated
    # in a tree/manifest state where zero gate-relevant paths matched) rather than a digest. That
    # is a real header the hex-only regex above just doesn't match — routing it into the "no
    # header" branch below would blame the wrong thing (a missing line, not a stale scope).
    bad "test-evidence $EV was generated when no gate-relevant paths matched (its stored header carries the EMPTY sentinel, not a digest) — fix test_evidence_inputs, then regenerate: $REMEDIATION_CMD (this is what it runs: $EVIDENCE_CMD)"
  elif [ -z "$EVDIG" ]; then
    bad "test-evidence $EV has no '# plc-gate-evidence inputs=<digest>' first line — regenerate it: $REMEDIATION_CMD (this is what it runs: $EVIDENCE_CMD)"
  elif [ -z "$EVSET" ]; then
    # A DIFFERENT cause from the branch above: the digest half of the header is fine (EVDIG
    # matched), but 'set=task' or 'set=phase' is missing or malformed on that same line — e.g.
    # evidence generated before 'set' existed, or hand-edited. 'set' is mandatory, so a digest match
    # alone does not satisfy this row; blame THIS, not a missing header (a
    # fourth cause needs a fourth message, not a reuse of one of the first three).
    bad "test-evidence $EV's header has a digest but no well-formed 'set=task' or 'set=phase' on that line — regenerate it: $REMEDIATION_CMD (this is what it runs: $EVIDENCE_CMD)"
  elif [ "$EVDIG" = "$NOWDIG" ]; then
    # This ✓ used to read "its input fingerprint matches the current tree", which a reader
    # takes as "the tests are fresh". The mechanism cannot support that and never claimed to in
    # code: GATE_RELEVANT_PATHS above is exactly validate.py's inputs, and the evidence file is
    # exactly validate.py's output. Nothing here has ever covered `hooks/*.sh`, the test suites,
    # or this script -- so a hooks-only commit recomputes a byte-identical digest and passes on
    # evidence older than the code it is trusted to guarantee (measured).
    # The list was NOT widened to close that. Widening the declaration while the command stays a
    # 0.08s manifest validator moves the lie rather than removing it -- the ✓ would then certify
    # freshness for files whose tests never ran. The hook suites are proven where proof is
    # affordable (CI, per PR) and this row's text now says only what it checks.
    #
    # 'set=$EVSET' is reported because the value is only required to be RECORDED and distinguishable
    # after the fact — it is explicitly NOT compared against the mode this run is gating (that
    # comparison is out of scope; see evidence_header's comment). Say only what was checked.
    ok "test-evidence non-empty; validate.py's declared inputs are unchanged since this file was generated ($EV, set=$EVSET) — NOT proof anything ran, and the recorded set is not checked against how the gate is being run now; hook + test suites are proven in CI, not here" test_evidence
  else
    bad "test-evidence $EV is stale — a path validate.py reads has changed since it was generated (fingerprint $(printf '%.12s' "$EVDIG")… ≠ $(printf '%.12s' "$NOWDIG")…) — re-run: $REMEDIATION_CMD (this is what it runs: $EVIDENCE_CMD)" test_evidence
  fi
fi
fi  # end check 7 (RUN_EVIDENCE)

# 8. declared repo-integrity invariants: the gate does not just check that artifacts
#    exist — it RUNS every invariant the manifest declares. jq reads invariants[]; each
#    .command is executed and a non-zero exit is a FAIL. This is what closes the loop the
#    seeded invariants opened: a mechanism that is declared but never run is a
#    claim, not a gate.
#    Fail-CLOSED at every seam: an unreadable/malformed manifest, a non-array invariants
#    value, or an entry that isn't an object / is missing its name/command, is a ✗ — never
#    a silent skip that would let a broken invariant slip by. Every jq read is guarded with
#    a sentinel fallback so a bad SHAPE produces a graceful ✗ row, not a raw jq trace + a
#    `set -e` abort that truncates the remaining invariants (the crash-under-set-e lesson
#    already learned in scripts/invariants/manifest-version-sync.sh).
#    Envelope stays jq-only: the invariant COMMANDS may use git/grep/etc., but the gate's
#    own iteration is pure jq + bash (no python3).
#    TRUST BOUNDARY: `eval "$CMD"` runs a string straight from the git-tracked manifest, so a
#    manifest edit is arbitrary-code-execution-equivalent — review `.command` changes with the
#    same care as a script change. Deliberate: the manifest is PR-reviewed repo config, same
#    trust tier as scripts/*.sh, and this gate is local dev-time only (never fed untrusted input).
if ! INV_JSON="$(jq -c '.invariants // []' "$M" 2>/dev/null)"; then
  bad "invariants[]: manifest unreadable or malformed JSON — cannot run declared invariants"
else
  # `.invariants` present-but-not-an-array (e.g. a `"invariants": true` typo) would make a bare
  # `jq length` error out under set -e; map any non-array to -1 and report it, don't crash.
  INV_COUNT="$(printf '%s' "$INV_JSON" | jq 'if type=="array" then length else -1 end' 2>/dev/null)" || INV_COUNT=-1
  if [ "${INV_COUNT:--1}" -lt 0 ]; then
    bad "invariants[] is present but not a JSON array — fix the manifest"
  elif [ "$INV_COUNT" -eq 0 ]; then
    warn "no invariants declared in manifest — skipping the invariants run"
  else
    i=0
    while [ "$i" -lt "$INV_COUNT" ]; do
      # an array element that isn't an object (a stray string/number) makes `.[$i].name` error
      # under set -e; the `if (.[i]|type)=="object"` wrapper + `|| __ERR__` fallback turns that
      # into the malformed-entry ✗ row instead of a script abort that skips later invariants.
      NAME="$(printf '%s' "$INV_JSON" | jq -r "if (.[$i]|type)==\"object\" then (.[$i].name // \"\") else \"__ERR__\" end" 2>/dev/null)" || NAME="__ERR__"
      CMD="$(printf  '%s' "$INV_JSON" | jq -r "if (.[$i]|type)==\"object\" then (.[$i].command // \"\") else \"__ERR__\" end" 2>/dev/null)" || CMD="__ERR__"
      if [ "$NAME" = "__ERR__" ] || [ "$CMD" = "__ERR__" ] || [ -z "$NAME" ] || [ -z "$CMD" ]; then
        bad "invariant #$i is malformed (not an object, or missing name/command) — fix the manifest"
      # run the declared command in a subshell so its own `set -e`/cwd can't leak into the
      # gate; suppress its chatter (the ✗ row names the command to re-run for detail).
      elif ( eval "$CMD" ) >/dev/null 2>&1; then
        ok "invariant '$NAME' holds" invariants
      else
        bad "invariant '$NAME' FAILED — \`$CMD\` exited non-zero (run it directly to see why)" invariants
      fi
      i=$((i+1))
    done
  fi
fi

# 9b. divergence-record freshness. The differential harness pins each deliberate-lead row to
#     the blob SHA of the hook it recorded, and `--check-divergences` is what enforces that pin. Where that harness file is absent the row prints that it does not apply.
#
#     WHY THIS IS CONDITIONAL. The check takes minutes -- several times the whole task-mode gate --
#     so wiring it unconditionally makes
#     every push that much slower, and a slow gate is one people
#     route around with `--no-verify`. The pin is keyed on ONE file's blob, so ONLY a diff that
#     touches that file can stale a record; every other push pays nothing.
#
#     THE SKIP IS PRINTED, NOT SILENT. A check that vanishes when it does not apply is
#     indistinguishable from a check that was never wired -- the same reason row 10 announces its
#     own inapplicability instead of disappearing.
#
#     IT READS THE OUTPUT, NOT JUST THE EXIT CODE: the
#     check prints `checked N records` on every non-vacuous run, INCLUDING a failing one, so its
#     ABSENCE means the run did not reach its own summary -- whatever it exited with.
CF_HOOK="skills/project-lifecycle/hooks/context-floor.sh"
DIFF_SUITE="skills/project-lifecycle/hooks/test-context-floor-differential.sh"
if [ "$RUN_DIVERGENCE" != 1 ]; then
  # Announced, never silent — same reason the touched/not-touched skip below is announced. A check
  # that vanishes in the mode people run most is indistinguishable from one that was never wired,
  # and this one is now OFF in exactly the mode that runs on every push.
  ok "divergence-record check not in this mode's set — it runs at \`close-gate.sh phase\` when the differential harness is present in the tree; it is held off the push path because git keeps the connection open for the whole pre-push hook"
elif [ ! -f "$DIFF_SUITE" ] || [ ! -f "$CF_HOOK" ]; then ok "divergence-record check not applicable — $DIFF_SUITE is not in this tree, so there is no recorded pin to check"; else
  if printf '%s\n' "$CHANGED_FILES" | grep -qxF "$CF_HOOK"; then
    _divout="$(/bin/bash "$DIFF_SUITE" --check-divergences 2>&1)" && _divrc=0 || _divrc=$?
    _divcount="$(printf '%s\n' "$_divout" | grep -oE '^checked [0-9]+ records$' | tail -1 || true)"
    if [ -z "$_divcount" ]; then
      bad "divergence records: the check printed no 'checked N records' line, so it did not run to completion — whatever its exit code ($_divrc) says. Run: /bin/bash $DIFF_SUITE --check-divergences"
    elif [ "$_divrc" -ne 0 ]; then
      bad "divergence records are STALE against the current $CF_HOOK ($_divcount). Any edit to that file — comments included — restales every record, because the pin is its blob SHA. Regenerate the census from the check's own output and re-bless: strip the ' (a pinned expectation was missed …)' suffix, pass the names NEWLINE-delimited from a /bin/bash shell (a name may contain spaces, and zsh will not word-split it), then: /bin/bash $DIFF_SUITE --bless-divergences \"\$name\"…"
    else
      ok "divergence records match the current $CF_HOOK blob ($_divcount)"
    fi
  else
    ok "divergence-record check skipped — this diff does not touch $CF_HOOK, whose blob is the only thing the pin is keyed on (the check is slow; skipping it here is what keeps it affordable to run at all)"
  fi
fi

# 10. ac-oracle-binding: every acceptance criterion has a runnable oracle or a still-true
#     written-down exclusion. Named, not numbered, in references/close-gate.md -- that document's
#     checks are unnumbered bullets, and "row 10" is a close-gate.sh-local label.
#
#     Mode split: `task` checks only what this branch's `Closes:` trailers claim,
#     `phase` checks the whole declared set. `diff` and `test-command` do not run it AND SAY SO --
#     a green with no row is indistinguishable from a green with a passing row.
if [ "$RUN_AC" = 1 ]; then
  AC_SH="scripts/ac-evidence.sh"
  AC_BL="scripts/ac-baseline.sh"
  EXEMPT_STORY="$(jq -r '.exempt_user_story // false' "$M" 2>/dev/null || echo false)"
  STORY_GLOB="$(jq -r '.user_story_glob // ""' "$M" 2>/dev/null || echo "")"
  # ORDER IS LOAD-BEARING: asking "is the script here?"
  # before "did this project opt in at all" would give a manifest that declares neither `user_story_glob`
  # nor `exempt_user_story` -- i.e. every manifest predating this check -- a HARD FAILURE about
  # a missing script it never asked for.
  # That is a
  # brick-every-existing-manifest failure, which is why
  # the unconfigured case is a visible `⊘` and not a `bad`.
  if [ "$EXEMPT_STORY" = "true" ]; then
    # Inherits the guard that already exists rather than adding a second one: this document already
    # requires a journal `SKIP:` line when the flag is true, and the skip message names it so the
    # exemption is never silent.
    ok "ac-oracle-binding SKIPPED — manifest sets exempt_user_story:true; the journal must carry the matching \`SKIP: user-story.md — <reason>\` line (that obligation is check 5's, not this one's)"
  elif [ -z "$STORY_GLOB" ]; then
    # Visible, never silent, and never a ✓. Nobody can mistake this for a pass,
    # and it does not brick a manifest that predates the key.
    echo "⊘ user_story_glob not configured in manifest — ac-oracle-binding skipped (declare the glob, or set exempt_user_story:true)"
  elif [ ! -r "$AC_SH" ]; then
    # Only now is a missing script a real failure: the project asked for the check.
    bad "ac-oracle-binding: $AC_SH is missing — the gate declares a check it cannot run"
  else
    AC_STORY_PAT="$(printf '%s' "$STORY_GLOB" | sed "s/{PHASE}/$PHASE/g")"
    # shellcheck disable=SC2086
    set -- $AC_STORY_PAT
    if [ "$#" -gt 1 ]; then
      bad "ac-oracle-binding: \`user_story_glob\` matched $# files for phase $PHASE — exactly one is required, never a silent pick"
    elif [ ! -f "${1:-}" ]; then
      # Deliberately a FAIL, not a pass over an empty set: passing here would hand a green row to
      # every phase that ever logged `SKIP: user-story.md`.
      bad "ac-oracle-binding: no user story resolves for phase $PHASE via \`$AC_STORY_PAT\` — set exempt_user_story:true if this phase legitimately has none"
    else
      AC_STORY="$1"
      AC_ARGS=""
      AC_BASE_FILE="$(jq -r '.ac_baseline // ""' "$M" 2>/dev/null || echo "")"
      [ -n "$AC_BASE_FILE" ] && [ -r "$AC_BASE_FILE" ] && AC_ARGS="--baseline $AC_BASE_FILE"
      if [ "$MODE" = phase ]; then
        # Removal is automatic but happens HERE, at phase close -- never inside the
        # pre-push hook, where a write to a tracked file leaves the pushed commit without it, the
        # remote stale, and the operator holding a dirty tree.
        if [ -n "$AC_BASE_FILE" ] && [ -r "$AC_BASE_FILE" ] && [ -r "$(jq -r '.ac_evidence // ""' "$M")" ]; then
          /bin/bash "$AC_BL" prune --file "$AC_BASE_FILE" --evidence "$(jq -r '.ac_evidence' "$M")" || true
        fi
        AC_IDS=""
      else
        AC_IDS="$(mktemp)"
        # The base is the DEFAULT branch, never `@{u}`. Measured: `@{u}` on a phase branch is that
        # branch's own remote, so merge-base(@{u}, HEAD) is HEAD and the scope came back empty --
        # a green row that had checked nothing at all.
        AC_BASE="$(git symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null || echo origin/main)"
        AC_MB="$(git merge-base "$AC_BASE" HEAD 2>/dev/null || echo unknown)"; export AC_MERGE_BASE="$AC_MB"
        /bin/bash "$AC_SH" scope-from-trailers "$PHASE" --base "$AC_BASE" > "$AC_IDS" 2>/dev/null || : > "$AC_IDS"
      fi
      # shellcheck disable=SC2086
      if AC_OUT="$(/bin/bash "$AC_SH" report "$AC_STORY" "$PHASE" $AC_ARGS ${AC_IDS:+--ids "$AC_IDS"} 2>&1)"; then
        ok "ac-oracle-binding ($MODE): every criterion in scope has an oracle or a still-true exclusion — this proves each HAS one, never that the oracle is correct"
        printf '%s\n' "$AC_OUT" | sed 's/^/    /'
      else
        bad "ac-oracle-binding ($MODE) FAILED — a criterion in scope has neither an oracle nor a still-true exclusion:"
        printf '%s\n' "$AC_OUT" | sed 's/^/    /'
      fi
      [ -n "$AC_IDS" ] && rm -f "$AC_IDS"
    fi
  fi
else
  ok "ac-oracle-binding SKIPPED in $MODE mode — a criterion set is a phase concept and $MODE has no phase context (said out loud: a green with no row reads the same as a green with a passing row)"
fi

# 11. closure-declaration. A phase must say which backlog ids it closed, and the gate
#     refuses to open while that declaration and the closure lines THIS BRANCH ADDED disagree
#     in either direction.
#
#     ARMED BY THE MANIFEST, and that is the whole reason this row can exist at all. With no
#     `closure_declaration` key the row does not run, prints nothing, and leaves the check-set
#     line untouched -- a check firing on projects that had never
#     configured the feature is the defect this avoids.
#
#     THREE VERDICTS, and the middle one is why "absent" cannot pass. `closes: none` is a
#     statement a human made at the moment they knew; an absent block is a step nobody
#     performed, which is the entire defect this check exists to fix. If both passed they would
#     be the same verdict, and the criterion asks for three.
if [ "$RUN_CLOSURE_DECL" = 1 ]; then
  CD_LEDGER="$(jq -r '.closure_declaration.ledger // empty' "$M")"
  CD_DERIVER="$(jq -r '.closure_declaration.deriver // empty' "$M")"
  if [ -z "$CD_LEDGER" ] || [ -z "$CD_DERIVER" ]; then
    ok "closure-declaration NOT ARMED — no \`closure_declaration\` key in $M, so this phase is not asked to declare what it closed (an adopter who has not configured it is not failed by it)"
  else
    CD_DOCS=""
    for _g in "$(g phase_docs_glob)" "$(g plan_glob)"; do
      [ -n "$_g" ] || continue
      glob_exists "$_g" && CD_DOCS="$CD_DOCS $_g"
    done
    # shellcheck disable=SC2086
    if [ -z "$CD_DOCS" ]; then
      bad "closure-declaration: no phase documents matched \`phase_docs_glob\` or \`plan_glob\` for phase $PHASE, so there is nowhere for the declaration to live" closure_declaration
    elif ! CD_OUT="$(/bin/bash scripts/closure-declaration.sh extract $CD_DOCS 2>&1)"; then
      bad "closure-declaration: the declaration could not be read — $CD_OUT" closure_declaration
    elif [ -z "$CD_OUT" ]; then
      bad "closure-declaration: no \`plc-closes\` block in any phase document for $PHASE. Declare what this phase closed, or declare \`closes: none\` — forgetting and deciding must not look the same" closure_declaration
    elif ! CD_REC="$(/bin/bash scripts/closure-declaration.sh reconcile --ledger "$CD_LEDGER" --deriver "$CD_DERIVER" $CD_DOCS 2>&1)"; then
      bad "closure-declaration: the declaration and $CD_LEDGER disagree:
$(printf '%s\n' "$CD_REC" | sed 's/^/      /')" closure_declaration
    else
      ok "closure-declaration: every id this phase declares closed has a ledger event, and every closure this branch added is declared — NOT proof the declaration is true, only that it is consistent with the ledger" closure_declaration
    fi
  fi
fi

# 9. validator_input_paths_rationale: the manifest must carry the load-bearing argument
#    for why test_evidence_inputs stays narrow (tracked-only). Content-checked, not just
#    presence: a placeholder string must not satisfy this row.
#
#    SHAPE-checked, not VALUE-checked. Requiring the literal digits
#    of one particular measurement, with a proximity window between them, would be wrong twice:
#    an honest rewording that moves the words further apart would be REJECTED, and
#    keying on literal numbers means the next honest RE-measurement (a tree grows;
#    the counts will change) is GUARANTEED to fail unless the stale digits are kept forever — the
#    check would punish updating and reward staleness. So this row asserts only the SHAPE of a
#    measurement argument (at least two numbers, plus the tracked-surface word "track...", with
#    no proximity requirement), not that any particular numbers appear, and not that the
#    measurement is still current or true — the ✓/✗ text says exactly that and no more.
#
#    This row rides with check 7 (RUN_EVIDENCE), not with check 8. It is the
#    declared argument for check 7's OWN input list, so on a run where check 7 does not fire it
#    would be asserting the shape of a rationale for a fingerprint nobody computed.
if [ "$RUN_EVIDENCE" = 1 ]; then
RAT_TYPE="$(jq -r '.validator_input_paths_rationale | type' "$M" 2>/dev/null || echo null)"
if [ "$RAT_TYPE" != array ]; then
  bad "manifest missing validator_input_paths_rationale (or it is not a JSON array) — the test_evidence_inputs narrowing argument must be declared, not just enforced"
else
  # `|| RAT_JOINED="__ERR__"` guards the same class check 8's NAME/CMD reads guard against
  # (scripts/close-gate.sh, invariants loop): `jq join` exits non-zero (not just empty output)
  # when the array holds a non-string element — `echo '{"r":[1,{"a":1}]}' | jq -r '.r|join(" ")'`
  # exits 5 — and this was a bare top-level assignment under `set -euo pipefail`, so a manifest
  # with one non-string rationale entry crashed the whole gate with a raw jq trace instead of
  # printing this row's `bad`. The fallback routes it into the shape check below, where zero
  # numbers/no "track" naturally fails closed instead of aborting the script.
  RAT_JOINED="$(jq -r '.validator_input_paths_rationale | join(" ")' "$M" 2>/dev/null)" || RAT_JOINED="__ERR__"
  RAT_NUM_COUNT="$(printf '%s' "$RAT_JOINED" | grep -oE '[0-9]+' 2>/dev/null | wc -l | tr -d ' ')" || RAT_NUM_COUNT=0
  if [ "$RAT_JOINED" != "__ERR__" ] && [ "${RAT_NUM_COUNT:-0}" -ge 2 ] && printf '%s' "$RAT_JOINED" | grep -qiE 'track'; then
    ok "validator_input_paths_rationale present and shaped like a measurement (two numbers + a tracked-surface argument) — NOT a check that the measurement is current or true"
  else
    bad "validator_input_paths_rationale present but not shaped like a measurement — needs two numbers and a tracked-surface argument (e.g. 'N files, M tracked'); a placeholder does not satisfy this row"
  fi
fi
fi  # end check 9 (RUN_EVIDENCE)

# context-floor arming row — WARN-ONLY, three states (not wired · wired · wired but inert: jq
# missing). Defined with the helpers above, where its rationale, the PATH blind spot the ✓ must
# not outrun, and the byte-identity contract with references/close-gate.md are written out.
#
# Called unconditionally, in EVERY gating mode — not gated on a RUN_* flag. The check-set table
# above selects the rows that are properties of a PHASE's artifacts; this one is a property of
# the machine the gate is running on, which is the same fact in task, phase and diff mode. The
# pre-push hook runs `task` on every push, so this is also the only placement in which the
# warning reaches the human more than once per milestone.
floor_arming_row

echo "──"
# THE ONLY PLACE THIS IS SET. Everything above it counts as "the gate did not finish", and the
# EXIT trap turns that into 90. Do not hoist it earlier to "simplify" -- its entire value is that it
# sits AFTER the last row and BEFORE the verdict, so a check added later cannot land between the two
# and inherit a mark it did not earn.
GATE_VERDICT_REACHED=1

# AFTER the last row and after the verdict is decided, BEFORE it is printed -- so the
# ledger can never change what the gate says, and `|| true` means it can never change whether the
# gate says anything at all.
ledger_flush || true

[ $fail -eq 0 ] && { echo "✓ close-gate PASS ($MODE${PHASE:+ $PHASE})"; exit 0; } \
                || { echo "✗ close-gate FAIL ($MODE${PHASE:+ $PHASE}) — fix the ✗ rows above, then re-run"; exit 1; }
