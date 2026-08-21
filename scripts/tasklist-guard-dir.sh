#!/usr/bin/env bash
# Place a self-ignoring marker beside a tasklist artifact whose path `.gitignore` cannot reach.
#
# THE PROBLEM. `.gitignore` names `/.claude/tasklist.md` -- one path, correctly anchored. The writer
# resolves `${PLC_TASKLIST_FILE:-.claude/tasklist.md}` and the override may be any path, absolute
# included. A static pattern cannot follow a runtime override, so a configured tasklist outside the
# default location has nothing protecting it. This places that protection where the file actually is.
#
# THE PATTERN. A directory containing a `.gitignore` whose body is `*` ignores itself and everything
# under it. mypy, pytest and ruff all do exactly this for their cache directories, and their
# documented failure window applies here unchanged and is ACCEPTED RATHER THAN HIDDEN: a run killed
# between `mkdir` and the marker write leaves the directory unmarked. Re-running closes it.
#
# THE CONSTRAINT THAT MAKES THIS SAFE, and it is the whole design: the marker is written ONLY into a
# directory this script CREATED. Never into a pre-existing directory. Dropping an ignore-everything
# file into a directory a user already had -- and may well want tracked -- would silently un-track
# their work, which is a far worse outcome than an unprotected tasklist.
#
# THE AMBIGUOUS MIDDLE CASE, RESOLVED HERE RATHER THAN LEFT TO READING.
# For `PLC_TASKLIST_FILE=.claude/scratch/tasklist.md` where `.claude/` exists and
# `scratch/` does not: "a directory it created" means **the leaf this script actually made**, never
# the whole path.
#
#   .claude/        pre-existing  -> NEVER marked. Marking it would ignore settings.json,
#                                    close-gate.json, ac-evidence.json -- tracked files, all of them.
#   .claude/scratch/  created here -> marked. It exists only because of this artifact.
#
# So the rule is per-directory and answers "did I bring this into existence", not "is this somewhere
# under a path I touched". A fixture pins both halves; without the pin this paragraph is a reading,
# and a reading is exactly the ambiguity this section exists to remove.
#
# THE DEFAULT PATH IS DELIBERATELY UNPROTECTED BY THIS SCRIPT, and that is fine and is stated so
# nobody later "fixes" it: `.claude/` already exists, so by the rule above no marker is written
# there, and the default location's protection rests entirely on the pre-existing, correctly
# anchored `.gitignore` line.
#
# Envelope: bash + git only. No python3, no jq.

set -uo pipefail

NAME="tasklist-guard-dir"
MARKER_BODY='*'

say()  { printf '%s\n' "$*"; }
die()  { printf '%s: %s\n' "$NAME" "$1" >&2; exit 1; }

ART_REL="${1:-${PLC_TASKLIST_FILE:-.claude/tasklist.md}}"
[ -n "$ART_REL" ] || die "empty tasklist path"

case "$ART_REL" in
  */*) DIR="${ART_REL%/*}" ;;
  *)   DIR="." ;;            # a bare filename lives in the cwd, which this script never created
esac

if [ "$DIR" = "." ] || [ -z "$DIR" ]; then
  say "$NAME: '$ART_REL' sits in the current directory, which this script did not create -- no marker written"
  exit 0
fi

if [ -e "$DIR" ]; then
  if [ -d "$DIR" ]; then
    say "$NAME: '$DIR' already exists -- no marker written (a marker belongs only in a directory this script created)"
    exit 0
  fi
  die "'$DIR' exists and is not a directory"
fi

# From here on, this script is the one bringing the leaf into existence. `mkdir -p` may also create
# intermediate parents; those are NOT marked, per the resolution above -- only $DIR is.
mkdir -p -- "$DIR" || die "could not create '$DIR'"

MARK="$DIR/.gitignore"
if [ -e "$MARK" ]; then
  # Racing with something else that populated the directory between the -e test and the mkdir.
  # Refuse rather than overwrite: an existing .gitignore is somebody's decision.
  say "$NAME: '$MARK' already exists -- left untouched"
  exit 0
fi

printf '%s\n' "$MARKER_BODY" > "$MARK" || die "could not write '$MARK'"
say "$NAME: created '$DIR' and marked it self-ignoring ($MARK contains '$MARKER_BODY')"
