#!/bin/sh
# project-lifecycle -- PreToolUse:Bash|Edit|Write action-level hard-stop.
# The ONLY thing in the phase-1 mechanism that blocks a tool call. It blocks (exit 2) only
# when the CALL ITSELF is an observably destructive action -- read from the tool args and the
# target named in them -- never because the model "thinks" something is risky (the model's
# self-reported judgment is not enforced here; that was rejected as score laundering).
#
# Trigger set (small, explicit, over ACTION + TARGET; matched on the command with quoted
# strings removed, so a string literal / test fixture mentioning a trigger does NOT fire):
#   1 destructive migration  : down/rollback/reset/drop migration or dropdb against a REAL target
#                              (prod/production token, or a DB URL / -h host that is not local)
#   2 remote-resource delete : aws s3 rm|rb, ec2 terminate, kubectl delete, forge repo delete,
#                              force-push / branch-delete on origin|upstream (a personal fork
#                              remote does not fire)
#   3 prod write             : a write verb (apply/deploy/destroy/rollout/...) + a prod/production token
#   4 public-API break       : npm unpublish|deprecate, cargo yank
#   5 permission escalation  : chmod 777, aws iam attach/put, admin grants
#   6 real send              : sendmail, mail -s, aws ses/sns send/publish
# Edit/Write and every other tool: no trigger (an edit of a local file is not a destructive action).
#
# STATED BOUND -- this check is NOT complete, and does not claim to be. It is lexical over the tool
# args, so it is DEFEATED BY INDIRECTION: `$CMD migrate`, a renamed binary, a script that runs the
# destructive command inside, `bash -c '...'` / `eval` (quoted bodies are stripped on purpose),
# or a destructive command split across variables all PASS. It under-fires by design; a pass here
# is "no observable trigger matched", never "this call is safe". Pinned by
# scripts/test_judgment_action_gate.py::test_underfire_on_indirection_is_documented.
#
# jq + POSIX sh only. No network and no forge tooling, ever. Mirrors judgment-gate.sh: when it
# cannot run it says so (honest defer), never a silent pass.
# Global blast radius (fires in every project): additive, fail-open / honest-defer.

INPUT="$(cat 2>/dev/null || true)"

# jq absent: say so, honestly. NOT a pass and NOT a block. Fixed literal; nothing from $INPUT.
if ! command -v jq >/dev/null 2>&1; then
  printf '%s' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"defer","additionalContext":"UNVERIFIED (project-lifecycle judgment-action-gate.sh) -- jq is not on PATH, so this hook parsed nothing and did NOT check whether this call is an observably destructive action. The action-level hard-stop is not enforcing while jq is missing. This is not a pass. The normal permission flow is untouched. To restore this layer, install jq."}}'
  exit 0
fi

TOOL="$(printf '%s' "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)"
case "$TOOL" in
  Bash|Edit|Write) ;;
  "")
    printf '%s' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"defer","additionalContext":"UNVERIFIED (project-lifecycle judgment-action-gate.sh) -- could not parse tool input (malformed JSON or no tool_name), so this hook did NOT check whether this call is an observably destructive action. The action-level hard-stop is not enforcing for this call. This is not a pass. The normal permission flow is untouched."}}'
    exit 0 ;;
  *) exit 0 ;;
esac

SID="$(printf '%s' "$INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)"
if [ -z "$SID" ]; then
  printf '%s' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"defer","additionalContext":"UNVERIFIED (project-lifecycle judgment-action-gate.sh) -- the hook input had no session_id (not a well-formed hook call), so this hook did NOT check whether this call is an observably destructive action. The action-level hard-stop is not enforcing for this call. This is not a pass. The normal permission flow is untouched."}}'
  exit 0
fi

# Only Bash carries an action to inspect; Edit/Write have no trigger.
[ "$TOOL" = "Bash" ] || exit 0

CMD="$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)"
[ -n "$CMD" ] || exit 0

# Resemblance is not action: drop quoted strings (and lowercase) before matching.
S="$(printf '%s' "$CMD" | tr '\n' ' ' | sed -e "s/'[^']*'//g" -e 's/"[^"]*"//g' | tr 'A-Z' 'a-z')"

# Raw command (quotes kept) is consulted ONLY for a DB URL target, which is often quoted.
R="$(printf '%s' "$CMD" | tr 'A-Z' 'a-z')"

m() { printf '%s' "$S" | grep -Eq "$1"; }

WHY=""
PROD='(^|[^a-z0-9_])(prod|production)([^a-z0-9_]|$)'

# 1 destructive migration against a real target
MIG='(alembic +downgrade|migrate[: ]+(down|reset|rollback|fresh)|db:(drop|rollback|reset)|migrate:(rollback|reset|fresh)|drizzle-kit +drop|(^|[;&| ])dropdb( |$))'
if m "$MIG"; then
  REAL=0
  m "$PROD" && REAL=1
  # non-local DB URL or -h/--host that is not localhost/127.0.0.1
  printf '%s' "$R" | grep -Eq '(postgres(ql)?|mysql|mongodb(\+srv)?)://[^ /]*@?[a-z0-9._-]+' \
    && ! printf '%s' "$R" | grep -Eq '://[^ /@]*@?(localhost|127\.0\.0\.1|\[::1\])([:/ ]|$)' && REAL=1
  m '(^| )(-h|--host)[ =]+[a-z0-9._-]+' && ! m '(^| )(-h|--host)[ =]+(localhost|127\.0\.0\.1)( |$)' && REAL=1
  [ "$REAL" = 1 ] && WHY="destructive migration/drop against a non-local or prod target"
fi

# 2 remote-resource delete
if [ -z "$WHY" ]; then
  # NB: `g[h]` is deliberate -- the bracket keeps this regex from reading as a forge CLI call to the
  # push-path invariant scanner. Do NOT "simplify" it to the literal command name.
  if m '(^|[;&| ])aws +s3(api)? +(rm|rb|delete-bucket|delete-object)|aws +ec2 +terminate-instances|aws +rds +delete-|(^|[;&| ])kubectl +delete( |$)|(^|[;&| ])gcloud .* delete( |$)|g[h] +repo +delete'; then
    WHY="remote-resource delete"
  elif m '(^|[;&| ])git +push( .*)? (-f|--force|--force-with-lease|--delete)( |$)|(^|[;&| ])git +push .* :[^ ]+' && m 'git +push( +-[a-z-]+)* +(origin|upstream)( |$)'; then
    WHY="force-push / branch-delete on a shared remote (origin|upstream)"
  fi
fi

# 3 prod write
if [ -z "$WHY" ] && m "$PROD" && ! m '(^|[;&| ])kubectl +rollout +(status|history)( |$)' && m '(^|[;&| ])(kubectl|helm|terraform|pulumi|serverless|sls|cdk|flyctl|fly|vercel|heroku|cap)( +[^ ]+)* +(apply|deploy|destroy|rollout|upgrade|install|scale|delete|promote|--prod)( |$)'; then
  WHY="write verb against a prod/production target"
fi

# 4 public-API break
if [ -z "$WHY" ] && m '(^|[;&| ])(npm|pnpm|yarn) +(unpublish|deprecate)( |$)|(^|[;&| ])cargo +yank( |$)'; then
  WHY="public package unpublish/deprecate/yank"
fi

# 5 permission escalation
if [ -z "$WHY" ] && m '(^|[;&| ])chmod( +-[a-z]+)* +(0?777|a\+rwx)|aws +iam +(attach|put|create-access-key)|usermod +-a?g +(sudo|wheel|admin)|chown( +-[a-z]+)* +root'; then
  WHY="permission escalation"
fi

# 6 real send
if [ -z "$WHY" ] && m '(^|[;&| ])sendmail( |$)|(^|[;&| ])mailx? +([^;&|]* )?(-s|--subject)( |=|$)|(^|[;&| ])mailx? +[^;&| ]*@|aws +ses +send-|aws +sns +publish'; then
  WHY="real outbound send"
fi

[ -n "$WHY" ] || exit 0

{
  printf '[project-lifecycle] Blocked: %s.\n' "$WHY"
  printf 'This call matched an observable destructive-action trigger in its own args/target (judgment-action-gate.sh).\n'
  printf 'This is a fact about the command, not a judgment about your intent. If a human has explicitly approved this exact action, ask them to run it themselves or to confirm and have the permission flow handle it.\n'
  printf 'Note: this check is lexical and does not catch indirection; a pass elsewhere is not a safety claim.\n'
} >&2
exit 2
