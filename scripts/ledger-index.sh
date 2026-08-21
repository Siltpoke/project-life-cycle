#!/usr/bin/env bash
# The global discovery index. One file per run under XDG state.
#
# Modes:
#   repo-id   [--repo-root R] [--with-basis]        derive this repo's identity
#   upsert    --run-id … --ledger-path … [...]      write/replace one entry
#   rebuild   --ledger-dir D [...]                  re-derive every entry from the ledgers
#   list      [--index-dir D]                       print entries in a DEFINED order, with state
#
# THE LEDGER IS THE TRUTH; THIS IS A CACHE. Deleting the whole index loses nothing but
# discovery speed, which is why `rebuild` exists and why `list`'s output is the thing asserted
# byte-identical across a delete-and-rebuild.
#
# ORDER IS DEFINED, NOT INHERITED FROM THE FILESYSTEM, and it is defined in exactly ONE place.
# `list` sorts by `started_at` with ties broken by `run_id`. `rebuild` does NOT sort, because the
# order entries are CREATED in is invisible to every consumer -- sorting there too would be a second
# claim with nothing able to observe it, and it would make the ordering mutant unkillable, since a
# fixture built in sorted order reads the same whether or not the reader sorts. Without `list`'s
# sort, the suite's byte-identical assertion would turn on directory-listing luck; on APFS a handful of
# entries can have readdir order coincidentally track creation order, which is why the suite's
# fixture deliberately scrambles `started_at` against creation order.
#
# repo_id IS NOT A PATH, AND ITS BASIS IS RECORDED. Projects get moved between
# parent directories, and git
# worktree metadata keys on absolute paths and silently prunes when they vanish. The fallback order
# is PINNED:
#
#     1. the first-commit SHA        (stable across renames, remotes and clones)
#     2. a hash of the remote URL    (when there is no commit yet)
#     3. an explicit marker file     (.claude/repo-id -- when there is neither)
#
# and the basis that won is stored in the entry. That is what makes a later change DETECTABLE rather
# than silent: a history rewrite changes the first-commit SHA and therefore the identity, and the
# recorded basis plus value is the only thing that would let a reader notice the identity bifurcated
# rather than quietly treating one repo as two.
#
# WHAT IS ATOMIC AND WHAT IS NOT. An entry is a whole small file written to a temp and renamed, which
# is the one operation POSIX guarantees atomic within a filesystem -- so a reader sees the
# old entry or the new one, never half of either. This is the OPPOSITE of the ledger's rule, and
# deliberately: temp-then-rename on the append-only ledger would be read-modify-write and would lose
# records, which is exactly the defect the append rule exists to prevent.
#
# Envelope: bash + jq + git + coreutils. No python3.

set -euo pipefail

# Handle for the in-flight temp file, so the cleanup trap has something in scope to name.
PENDING_TMP=""

die() { printf 'ledger-index: %s\n' "$1" >&2; exit "${2:-2}"; }

usage() {
  cat >&2 <<'EOF'
usage:
  ledger-index.sh repo-id [--repo-root <dir>] [--with-basis]
  ledger-index.sh upsert --run-id <id> --ledger-path <file>
                         [--repo-root <dir>] [--repo-id <id>] [--repo-id-basis <basis>]
                         [--repo-name <name>] [--worktree-path <dir>]
                         [--started-at <RFC3339-UTC>] [--now <RFC3339-UTC>] [--index-dir <dir>]
  ledger-index.sh rebuild --ledger-dir <dir> [--repo-root <dir>] [--index-dir <dir>] [--now <t>]
  ledger-index.sh list [--index-dir <dir>]
EOF
}

default_index_dir() {
  printf '%s/plc/runs\n' "${XDG_STATE_HOME:-$HOME/.local/state}"
}

need_jq() { command -v jq >/dev/null 2>&1 || die "jq not found"; }

# --- repo identity ------------------------------------------------------------------------------
derive_repo_id() {
  local root="$1" sha remote marker
  sha="$(git -C "$root" rev-list --max-parents=0 HEAD 2>/dev/null | head -1 || true)"
  if [ -n "$sha" ]; then
    printf 'first-commit\t%s\n' "$sha"
    return 0
  fi
  remote="$(git -C "$root" config --get remote.origin.url 2>/dev/null || true)"
  if [ -n "$remote" ]; then
    printf 'remote-url\t%s\n' "$(printf '%s' "$remote" | git hash-object --stdin)"
    return 0
  fi
  marker="$root/.claude/repo-id"
  if [ -r "$marker" ]; then
    printf 'marker\t%s\n' "$(head -1 "$marker" | tr -d '[:space:]')"
    return 0
  fi
  return 1
}

cmd_repo_id() {
  local root="" with_basis=0 pair
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --repo-root)  [ "$#" -ge 2 ] || die "--repo-root needs a value"; root="$2"; shift 2 ;;
      --with-basis) with_basis=1; shift ;;
      *) die "unknown argument: $1" ;;
    esac
  done
  [ -n "$root" ] || root="$PWD"
  pair="$(derive_repo_id "$root" || true)"
  [ -n "$pair" ] || die "cannot derive a repo id for $root: no first commit, no remote.origin.url, and no .claude/repo-id marker. Write the marker rather than letting the identity be guessed."
  if [ "$with_basis" -eq 1 ]; then
    printf '%s\n' "$pair"
  else
    printf '%s\n' "${pair#*	}"
  fi
}

# --- upsert -------------------------------------------------------------------------------------
write_entry() {
  local index_dir="$1" run_id="$2" repo_id="$3" basis="$4" repo_name="$5" worktree="$6" \
        ledger="$7" started="$8" now="$9"
  mkdir -p "$index_dir"
  local target="$index_dir/$run_id.json" tmp="$index_dir/.$run_id.json.tmp.$$"

  # A failed writer must leave no partial file, and there are three separate mechanisms
  # here because no one of them covers the whole of it:
  #
  #  1. the temp is HIDDEN and does not end in `.json`, so `list`'s glob cannot see it. Whatever
  #     else happens, a partial write is never READ as an entry.
  #  2. a trap removes it on a normal exit, and on INT and TERM.
  #  3. SIGKILL cannot be trapped by anything, ever -- so a hard kill really can leave a temp on
  #     disk, and pretending otherwise would be a claim wider than the mechanism.
  #     The next write for the same run sweeps temps belonging to processes that are gone.
  local stale
  for stale in "$index_dir/.$run_id.json.tmp."*; do
    [ -f "$stale" ] || continue
    local owner="${stale##*.}"
    case "$owner" in
      ''|*[!0-9]*) continue ;;
      "$$") continue ;;
    esac
    kill -0 "$owner" 2>/dev/null || rm -f "$stale"
  done
  # The trap body is evaluated when it FIRES, not when it is set, so it cannot name a `local`: by
  # then `write_entry` has returned and `$tmp` is out of scope, which under `set -u` turns the
  # cleanup itself into "unbound variable" and takes the script down.
  # The handle is a global, cleared after the rename.
  PENDING_TMP="$tmp"
  trap 'rm -f "${PENDING_TMP:-}"' EXIT INT TERM

  jq -n \
    --arg run_id "$run_id" --arg repo_id "$repo_id" --arg repo_id_basis "$basis" \
    --arg repo_name "$repo_name" --arg worktree_path "$worktree" \
    --arg ledger_path "$ledger" --arg started_at "$started" --arg updated_at "$now" \
    '{run_id: $run_id, repo_id: $repo_id, repo_id_basis: $repo_id_basis, repo_name: $repo_name,
      worktree_path: $worktree_path, ledger_path: $ledger_path,
      started_at: $started_at, updated_at: $updated_at}' > "$tmp"
  # `mv` within one directory is a rename: a reader sees the old file or the new one, never a
  # partially written one. The temp lives beside the target, NOT in /tmp, because a rename across
  # filesystems is a copy and loses the guarantee entirely.
  mv -f "$tmp" "$target"
  PENDING_TMP=""
}

cmd_upsert() {
  need_jq
  local run_id="" ledger="" root="" repo_id="" basis="" repo_name="" worktree="" started="" now="" index_dir=""
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --run-id)        [ "$#" -ge 2 ] || die "--run-id needs a value";        run_id="$2";   shift 2 ;;
      --ledger-path)   [ "$#" -ge 2 ] || die "--ledger-path needs a value";   ledger="$2";   shift 2 ;;
      --repo-root)     [ "$#" -ge 2 ] || die "--repo-root needs a value";     root="$2";     shift 2 ;;
      --repo-id)       [ "$#" -ge 2 ] || die "--repo-id needs a value";       repo_id="$2";  shift 2 ;;
      --repo-id-basis) [ "$#" -ge 2 ] || die "--repo-id-basis needs a value"; basis="$2";    shift 2 ;;
      --repo-name)     [ "$#" -ge 2 ] || die "--repo-name needs a value";     repo_name="$2";shift 2 ;;
      --worktree-path) [ "$#" -ge 2 ] || die "--worktree-path needs a value"; worktree="$2"; shift 2 ;;
      --started-at)    [ "$#" -ge 2 ] || die "--started-at needs a value";    started="$2";  shift 2 ;;
      --now)           [ "$#" -ge 2 ] || die "--now needs a value";           now="$2";      shift 2 ;;
      --index-dir)     [ "$#" -ge 2 ] || die "--index-dir needs a value";     index_dir="$2";shift 2 ;;
      *) die "unknown argument: $1" ;;
    esac
  done
  [ -n "$run_id" ] || die "--run-id is required"
  [ -n "$ledger" ] || die "--ledger-path is required"
  case "$run_id" in *[!a-zA-Z0-9._-]*) die "run id must be filename-safe: $run_id" ;; esac
  [ -n "$root" ] || root="$PWD"
  [ -n "$worktree" ] || worktree="$root"
  [ -n "$repo_name" ] || repo_name="$(basename "$root")"
  [ -n "$index_dir" ] || index_dir="$(default_index_dir)"
  [ -n "$now" ] || now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  [ -n "$started" ] || started="$now"
  if [ -z "$repo_id" ]; then
    local pair; pair="$(derive_repo_id "$root" || true)"
    [ -n "$pair" ] || die "cannot derive a repo id for $root; pass --repo-id"
    basis="${pair%%	*}"; repo_id="${pair#*	}"
  fi
  [ -n "$basis" ] || basis="given"
  write_entry "$index_dir" "$run_id" "$repo_id" "$basis" "$repo_name" "$worktree" "$ledger" "$started" "$now"
}

# --- rebuild ------------------------------------------------------------------------------------
#
# Re-derives the whole index from the ledgers. Every fact in an entry except `updated_at` comes out
# of the ledger file itself, which is what makes "deleting the index loses nothing but discovery
# speed" true rather than aspirational.
cmd_rebuild() {
  need_jq
  local ledger_dir="" root="" index_dir="" now="" f run_id repo_id started n=0
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --ledger-dir) [ "$#" -ge 2 ] || die "--ledger-dir needs a value"; ledger_dir="$2"; shift 2 ;;
      --repo-root)  [ "$#" -ge 2 ] || die "--repo-root needs a value";  root="$2";       shift 2 ;;
      --index-dir)  [ "$#" -ge 2 ] || die "--index-dir needs a value";  index_dir="$2";  shift 2 ;;
      --now)        [ "$#" -ge 2 ] || die "--now needs a value";        now="$2";        shift 2 ;;
      *) die "unknown argument: $1" ;;
    esac
  done
  [ -n "$ledger_dir" ] || die "--ledger-dir is required"
  [ -d "$ledger_dir" ] || die "ledger dir is not a directory: $ledger_dir"
  [ -n "$root" ] || root="$PWD"
  [ -n "$index_dir" ] || index_dir="$(default_index_dir)"
  [ -n "$now" ] || now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  mkdir -p "$index_dir"

  # NO SORT HERE, and that is a decision rather than an omission. The observable order is `list`'s,
  # which reads the directory and sorts; whatever order entries are CREATED in is invisible to
  # every consumer. Sorting here as well would be a second claim with no mechanism behind it -- the
  # "declaration wider than mechanism" shape -- and it would also
  # make the ordering mutant unkillable, because a fixture built in sorted order looks identical
  # whether or not the reader sorts.
  while IFS=$'\x1f' read -r started run_id repo_id basis ledger; do
    [ -n "$run_id" ] || continue
    write_entry "$index_dir" "$run_id" "$repo_id" "$basis" "$(basename "$root")" "$root" "$ledger" "$started" "$now"
    n=$((n + 1))
  done <<EOF
$(
  for f in "$ledger_dir"/*.jsonl; do
    [ -f "$f" ] || continue
    run_id="$(basename "$f" .jsonl)"
    # The ledger is the source. An empty ledger still has a run -- "this run produced nothing" is
    # the answer the ledger exists to be able to give -- so its facts fall back to the
    # filename and the tree rather than the entry being dropped.
    repo_id="$(jq -rs 'first(.[]? | select(type == "object") | .repo_id // empty) // ""' "$f" 2>/dev/null || true)"
    started="$(jq -rs '[.[]? | select(type == "object") | .started_at // empty] | sort | first // ""' "$f" 2>/dev/null || true)"
    [ -n "$repo_id" ] || { repo_id="$(derive_repo_id "$root" | cut -f2)"; }
    [ -n "$started" ] || started="1970-01-01T00:00:00Z"
    printf '%s\x1f%s\x1f%s\x1f%s\x1f%s\n' "$started" "$run_id" "$repo_id" "ledger" "$f"
  done
)
EOF
  printf 'rebuilt %s entries into %s\n' "$n" "$index_dir"
}

# --- list ---------------------------------------------------------------------------------------
#
# THE defined order, and the only one any consumer can see. `updated_at` is deliberately not
# printed: it is bookkeeping about the index, it necessarily changes when the index is rebuilt, and
# including it would fail the byte-identical assertion for a reason that has nothing to do with
# whether the rebuild recovered the same information.
#
# `--compare` additionally drops `repo_id_basis`, and the reason is the point of that field rather
# than an exception to it. The byte-identical assertion runs across a delete-and-rebuild, and
# a rebuilt entry's repo_id comes out of the LEDGER while a live entry's was derived from the tree.
# Those are different provenances for the same value, honestly recorded -- so a byte comparison that
# included them would be asserting that provenance does not change when the whole point of storing
# it is that it can. What that assertion is about is whether the RUN's facts survived, and that is what
# `--compare` prints.
cmd_list() {
  need_jq
  local index_dir="" f state compare=0
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --index-dir) [ "$#" -ge 2 ] || die "--index-dir needs a value"; index_dir="$2"; shift 2 ;;
      --compare)   compare=1; shift ;;
      *) die "unknown argument: $1" ;;
    esac
  done
  [ -n "$index_dir" ] || index_dir="$(default_index_dir)"
  [ -d "$index_dir" ] || return 0
  {
    for f in "$index_dir"/*.json; do
      [ -f "$f" ] || continue
      jq -e . "$f" >/dev/null 2>&1 || { printf 'UNREADABLE\t%s\n' "$f" >&2; continue; }
      # STALE is a RENDERED state, never a silent prune and never a silent follow. An entry whose
      # ledger has gone is still the record that the run happened.
      if [ -e "$(jq -r '.ledger_path' "$f")" ]; then state=ok; else state=STALE; fi
      if [ "$compare" -eq 1 ]; then
        jq -r --arg state "$state" \
          '[$state, .started_at, .run_id, .repo_id, .repo_name, .worktree_path, .ledger_path]
           | @tsv' "$f"
      else
        jq -r --arg state "$state" \
          '[$state, .started_at, .run_id, .repo_id, .repo_id_basis, .repo_name, .worktree_path, .ledger_path]
           | @tsv' "$f"
      fi
    done
  } | sort -t"$(printf '\t')" -k2,2 -k3,3
}

main() {
  [ "$#" -ge 1 ] || { usage; exit 2; }
  local mode="$1"; shift
  case "$mode" in
    repo-id)   cmd_repo_id "$@" ;;
    upsert)    cmd_upsert "$@" ;;
    rebuild)   cmd_rebuild "$@" ;;
    list)      cmd_list "$@" ;;
    -h|--help) usage; exit 0 ;;
    *)         usage; exit 2 ;;
  esac
}

main "$@"
