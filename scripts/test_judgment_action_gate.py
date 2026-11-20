"""judgment gate: action-level hard-stop (observable facts only) PreToolUse hook."""
import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "skills/project-lifecycle/hooks/judgment-action-gate.sh"


def run(cmd=None, tool="Bash", session_id="s-" + uuid.uuid4().hex, path=None, raw=None, tool_input=None):
    env = dict(os.environ)
    if path is not None:
        env["PATH"] = path
    if raw is None:
        ti = tool_input if tool_input is not None else {"command": cmd}
        payload = {"tool_name": tool, "tool_input": ti}
        if session_id is not None:
            payload["session_id"] = session_id
        raw = json.dumps(payload)
    return subprocess.run(["/bin/sh", str(HOOK)], input=raw, text=True,
                          capture_output=True, env=env)


def assert_blocked(cmd):
    r = run(cmd)
    assert r.returncode == 2, (cmd, r.stdout, r.stderr)
    assert "observable" in r.stderr


def assert_passes(cmd):
    r = run(cmd)
    assert r.returncode == 0 and r.stdout == "" and r.stderr == "", (cmd, r.stdout, r.stderr)


def test_blocks_destructive_migration():
    assert_blocked("alembic downgrade base --url postgresql://u:p@db.prod.example.com/app")
    assert_blocked("rails db:rollback RAILS_ENV=production")
    assert_blocked("dropdb -h db.example.com customers")


def test_blocks_remote_resource_delete():
    assert_blocked("aws s3 rm s3://company-data --recursive")
    assert_blocked("kubectl delete namespace payments")
    assert_blocked("gh repo delete acme/service --yes")
    assert_blocked("git push --force origin main")


def test_blocks_prod_write():
    assert_blocked("kubectl --context prod apply -f deploy.yaml")
    assert_blocked("terraform apply -var env=production")


def test_blocks_public_api_break_permission_escalation_real_send():
    assert_blocked("npm unpublish my-pkg@1.0.0")
    assert_blocked("chmod -R 777 /srv/app")
    assert_blocked("aws iam attach-user-policy --user-name bob --policy-arn arn:aws:iam::aws:policy/AdministratorAccess")
    assert_blocked("aws ses send-email --to a@b.com --subject hi")


def test_bare_mail_word_not_blocked_but_real_send_is():
    assert_passes("make mail")
    assert_passes("npm run mail")
    assert_blocked('mail -s "hi" person@example.com')
    assert_blocked("sendmail root")


def test_does_not_block_drop_in_string_literal():
    assert_passes("echo 'DROP TABLE users; alembic downgrade base on prod'")
    assert_passes("grep -r \"aws s3 rm\" tests/fixtures")
    assert_passes("git commit -m \"kubectl delete namespace in docs\"")


def test_does_not_block_local_migration_or_fork_push():
    assert_passes("alembic downgrade -1")
    assert_passes("git push --force fork feature/x")
    assert_passes("git push origin feature/x")


def test_non_bash_tools_and_ordinary_commands_pass():
    assert_passes("ls -la && pytest -q")
    r = run(tool="Edit", tool_input={"file_path": "/x", "old_string": "a", "new_string": "b"})
    assert r.returncode == 0 and r.stderr == ""
    r = run(tool="Read", tool_input={"file_path": "/x"})
    assert r.returncode == 0 and r.stderr == ""


def _defer(r, needle):
    assert r.returncode == 0
    out = json.loads(r.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "defer"
    assert needle in out["additionalContext"] and "not a pass" in out["additionalContext"]


def test_defers_on_absent_jq(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for tool in ("sh", "cat", "printf"):
        p = shutil.which(tool)
        if p:
            (bindir / tool).symlink_to(p)
    _defer(run("kubectl delete ns x", path=str(bindir)), "did NOT")


def test_defers_on_malformed_input():
    _defer(run(raw="not json {"), "did NOT")


def test_defers_on_missing_session_id():
    _defer(run("kubectl delete ns x", session_id=None), "did NOT")


def test_underfire_on_indirection_is_documented():
    # Known, stated bound: a lexical/arg check is defeated by indirection.
    assert_passes("CMD='alembic downgrade'; $CMD base --url postgresql://u:p@db.prod.example.com/app")
    assert_passes("K=kubectl; $K delete namespace payments")
    header = HOOK.read_text().split("INPUT=", 1)[0]
    assert "indirection" in header.lower() and "NOT complete" in header


def test_hook_has_no_forge_or_network_cli_or_python():
    body = "\n".join(l for l in HOOK.read_text().splitlines() if not l.lstrip().startswith("#"))
    for banned in ("curl ", "wget ", "git fetch", "python3", "gh api", " gh "):
        assert banned not in body, banned


def test_plain_push_with_dash_f_in_branch_name_not_blocked():
    assert_passes("git push origin my-feature")
    assert_passes("git push -u origin ship-faster")
    assert_blocked("git push --force origin main")
    assert_blocked("git push --delete origin x")
    assert_blocked("git push -f origin main")


def test_readonly_prod_rollout_not_blocked():
    assert_passes("kubectl rollout status deploy/api -n prod")
    assert_passes("kubectl rollout history deploy/api -n prod")
    assert_blocked("kubectl rollout restart deploy/api -n prod")
