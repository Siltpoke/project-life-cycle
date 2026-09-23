#!/usr/bin/env bash
# Invariant: the ci-status producer snippet in the docs writes the schema the reader accepts.
#
# WHY. references/ci-cd-gates.md carries an example producer for `.claude/ci-status.json`, because
# R1 forbids PLC shipping forge-specific code and the permitted form is a snippet an adopter copies
#. That leaves the snippet with NO GATE BEHIND IT -- prose asserting something no mechanism
# checks, which is the defect class p33 spent a day on. This is the mechanism.
#
# It pins the one thing that silently breaks the snippet without breaking its syntax: the schema
# string. `session_card.read_ci_status` rejects any artifact whose `schema` is not exactly
# CI_SCHEMA, and rejects it as UNREADABLE rather than partially valid. So a snippet that drifts by
# one character produces a file the card reports as "present but unreadable" -- on the adopter's
# machine, silently, with the docs still reading as correct.
#
# SCOPE, stated rather than implied. This checks the SCHEMA STRING and nothing else. It does not
# check that the snippet parses, still runs, or that `gh`'s JSON fields still carry those names:
# the parse check lives in scripts/test_ci_state_snippet.py, because this file runs inside the
# gate's jq-only envelope and may not invoke a python interpreter to do it. What no check covers is
# whether the FORGE's field names have moved -- that needs the network, and a gate that needs the
# network is the thing ci-cd-gates.md itself argues against.
#
# Verdicts: 0 pass, 1 they disagree, 3 could not run.

set -uo pipefail

NAME="documented-snippet-matches-reader"
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
DOC="$ROOT/skills/project-lifecycle/references/ci-cd-gates.md"
READER="$ROOT/scripts/session_card.py"

[ -f "$DOC" ] || { printf 'COULD-NOT-RUN %s: %s missing\n' "$NAME" "$DOC" >&2; exit 3; }
[ -f "$READER" ] || { printf 'COULD-NOT-RUN %s: %s missing\n' "$NAME" "$READER" >&2; exit 3; }

# The reader's constant is the authority; the snippet must match it.
reader_schema="$(sed -n 's/^CI_SCHEMA = "\(.*\)"$/\1/p' "$READER" | head -1)"
[ -n "$reader_schema" ] || { printf 'COULD-NOT-RUN %s: could not read CI_SCHEMA from %s\n' "$NAME" "$READER" >&2; exit 3; }

snippet_schema="$(sed -n 's/.*"schema": "\([^"]*\)".*/\1/p' "$DOC" | head -1)"
if [ -z "$snippet_schema" ]; then
  printf 'FAIL %s: no `"schema": "..."` found in %s — the documented producer snippet is gone or no longer writes a schema field. If the snippet was removed on purpose, remove this guard with it.\n' "$NAME" "${DOC#$ROOT/}" >&2
  exit 1
fi

if [ "$snippet_schema" != "$reader_schema" ]; then
  printf 'FAIL %s: the documented snippet writes schema "%s" but session_card.CI_SCHEMA is "%s".\n' "$NAME" "$snippet_schema" "$reader_schema" >&2
  printf '  -> read_ci_status rejects a mismatched schema as UNREADABLE, so an adopter copying the\n' >&2
  printf '     snippet would produce a file the card reports as "present but unreadable" while the\n' >&2
  printf '     documentation still reads as correct. Update whichever one is wrong.\n' >&2
  exit 1
fi

# The scope sentence lives here rather than in the message below: gate-jq-only-envelope
# matches the interpreter's NAME anywhere in an executable line, and cannot tell a mention
# from an invocation. Naming the companion test in a printf would red this file for talking
# about the rule it follows. See the SCOPE block at the top for what is and is not covered.
printf 'PASS %s: the documented producer snippet writes schema "%s", matching session_card.CI_SCHEMA. Scope: the schema string only — see this file'"'"'s header for the two things it deliberately does not check.\n' "$NAME" "$snippet_schema"
