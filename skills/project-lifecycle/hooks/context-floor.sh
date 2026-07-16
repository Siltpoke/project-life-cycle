#!/usr/bin/env bash
# project-lifecycle — context-saturation hard floor (enforce-only, self-arming).
# Wired as PreToolUse:Edit|Write (machine-local global). When the session's context
# occupancy crosses an absolute-token floor, blocks Edit/Write (exit 2) until RESUME.md
# is refreshed. Deliberately does NOT warn: three soft %-based warners already exist
# (a statusline indicator, a UserPromptSubmit warner, a PostToolUse monitor).
# The floor's only job is the hard block those soft layers cannot do.
#
# Occupancy = newest assistant turn's input_tokens + cache_read + cache_creation
# (read from the transcript JSONL). Floor: env PLC_CONTEXT_FLOOR (default 150000;
# 0 = disabled). Re-arm step after a checkpoint: PLC_CONTEXT_FLOOR_STEP (default 30000).
#
# Window-% mode (opt-in): set PLC_CONTEXT_FLOOR_PCT (e.g. 70) to trigger at a
# FRACTION of the running model's window instead of an absolute token count.
# When >0 it OVERRIDES PLC_CONTEXT_FLOOR — effective floor = window * pct/100,
# where window = PLC_CONTEXT_WINDOW (default 1000000). This lets a 1M-window
# user set one %-threshold that holds across models, instead of re-deriving an
# absolute floor per window size (a 150K floor is 75% of a 200K window but only
# 15% of a 1M window). Absolute mode stays the default — rot tracks absolute
# context size, not window fraction (references/harness-primitives.md §9) — but
# the %-knob is there for users whose mental model is window-occupancy.
# Disable entirely: PLC_CONTEXT_FLOOR=0 AND PLC_CONTEXT_FLOOR_PCT=0 (or unset).
# Self-arms: the first over-floor Edit/Write creates a session-keyed marker; a RESUME.md
# newer than that marker clears it and allows work. Fails OPEN (exit 0) on any
# read/parse/write error — a broken floor must never block work. NOT a frontmatter hook
# (would miss non-workflow sessions).
#
# Escape hatches, and where they may be MENTIONED:
#   - PLC_CONTEXT_FLOOR=0 (or _PCT=0) — a deliberate config decision. Named in the block
#     message; fine.
#   - deleting the marker — a human who reads this source can do it. NOT named in the
#     block message, and the marker path is not printed there either. The block message
#     used to say "or `rm <marker>` to override once", and an agent blocked mid-task did
#     exactly that: it deleted the guard's state to get past the guard, because the guard
#     told it how. A guard that ships its own bypass in its error message is a guard that
#     will be bypassed — and the agent taking it is not even disobeying, it is following
#     instructions. Keep the hatch; stop advertising it at the moment of maximum incentive
#     to take it.
set -uo pipefail
INPUT="$(cat 2>/dev/null || true)"
python3 - "$INPUT" <<'PY'
import json, os, sys

try:
    ev = json.loads(sys.argv[1]) if sys.argv[1] else {}
except Exception:
    sys.exit(0)  # unparseable event -> fail-open
if not isinstance(ev, dict):
    sys.exit(0)

try:
    floor_abs = int(os.environ.get("PLC_CONTEXT_FLOOR", "150000") or "0")
except Exception:
    floor_abs = 150000
try:
    floor_pct = float(os.environ.get("PLC_CONTEXT_FLOOR_PCT", "0") or "0")
except Exception:
    floor_pct = 0.0
# Nominal window of the running model (1M for Opus 4.8 [1m]). Always drives the
# %-rendered in the block message; in window-% mode it also drives the TRIGGER.
try:
    window = int(os.environ.get("PLC_CONTEXT_WINDOW", "1000000") or "1000000")
except Exception:
    window = 1000000
# Window-% mode (opt-in) overrides the absolute floor when PLC_CONTEXT_FLOOR_PCT
# > 0: trigger tracks a fraction of the window instead of an absolute count.
if floor_pct > 0 and window > 0:
    floor = int(window * floor_pct / 100)
    pct_mode = True
else:
    floor = floor_abs
    pct_mode = False
if floor <= 0:
    sys.exit(0)  # disabled (escape hatch: PLC_CONTEXT_FLOOR=0 and no PCT)
try:
    step = int(os.environ.get("PLC_CONTEXT_FLOOR_STEP", "30000") or "30000")
except Exception:
    step = 30000

sid = ev.get("session_id") or "nosession"
cwd = ev.get("cwd") or os.getcwd()
tpath = ev.get("transcript_path") or ""

mdir = os.path.join(os.environ.get("TMPDIR", "/tmp"), "plc-context-floor")
marker = os.path.join(mdir, sid + ".marker")
clearedat_f = os.path.join(mdir, sid + ".clearedat")
resume = os.environ.get("PLC_RESUME_PATH") or os.path.join(cwd, "RESUME.md")

# Never gate the checkpoint file itself — writing/refreshing RESUME.md is the
# action that CLEARS the block. Gating it would deadlock (can't write the
# unblock). Exempt by absolute-path match OR a RESUME.md basename anywhere.
ti = ev.get("tool_input") if isinstance(ev.get("tool_input"), dict) else {}
target = ti.get("file_path") or ti.get("path") or ""
if target:
    try:
        ta = target if os.path.isabs(target) else os.path.join(cwd, target)
        ta = os.path.abspath(ta)
        if ta == os.path.abspath(resume) or os.path.basename(ta) == "RESUME.md":
            sys.exit(0)
    except Exception:
        pass

def occupancy(path):
    if not path or not os.path.exists(path):
        return None
    occ = None
    try:
        with open(path, "r", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                u = None
                if isinstance(o, dict):
                    m = o.get("message")
                    if isinstance(m, dict):
                        u = m.get("usage")
                    if u is None:
                        u = o.get("usage")
                if isinstance(u, dict):
                    tot = ((u.get("input_tokens") or 0)
                           + (u.get("cache_read_input_tokens") or 0)
                           + (u.get("cache_creation_input_tokens") or 0))
                    if tot > 0:
                        occ = tot
    except Exception:
        return None
    return occ

def read_int(p):
    try:
        with open(p) as f:
            return int(f.read().strip())
    except Exception:
        return None

def mtime(p):
    try:
        return os.path.getmtime(p)
    except Exception:
        return None

occ = occupancy(tpath)
if occ is None:
    sys.exit(0)                # fail-open
if occ < floor:
    sys.exit(0)                # under floor -> allow

ca = read_int(clearedat_f)
if ca is not None and occ < ca + step:
    sys.exit(0)                # within post-checkpoint grace -> allow

# Over floor and past grace: require a RESUME.md refreshed since we armed.
try:
    os.makedirs(mdir, exist_ok=True)
    if not os.path.exists(marker):
        open(marker, "w").close()   # self-arm on first over-floor heavy tool
except Exception:
    sys.exit(0)                # cannot manage marker -> fail-open (never block)

rt = mtime(resume)
mt = mtime(marker)
if rt is not None and mt is not None and rt > mt:
    # checkpointed since arming -> record occupancy for re-arm grace, clear, allow
    try:
        with open(clearedat_f, "w") as f:
            f.write(str(occ))
        os.remove(marker)
    except Exception:
        pass                   # fail-open: if we can't record, still allow
    sys.exit(0)

pct = round(occ / window * 100, 1) if window > 0 else 0.0
if pct_mode:
    trigger_desc = "the %%-floor (%s%% of the %dK window = ~%dK)" % (
        round(floor_pct, 1), round(window / 1000), round(floor / 1000))
    note = ""
    disable_hint = "set PLC_CONTEXT_FLOOR_PCT=0 to disable"
else:
    trigger_desc = "floor %dK" % (round(floor / 1000),)
    note = ("Trigger is absolute tokens, not window %%, so this fires even when "
            "the window-%% looks small. ")
    disable_hint = "set PLC_CONTEXT_FLOOR=0 to disable"
# The message names ONE action: refresh RESUME.md. It deliberately does NOT hand
# out the marker path or an `rm` command.
#
# It used to. An agent, blocked mid-task, read the suggestion and reached straight
# for `rm <marker>` -- deleting the guard's own state to get past the guard. It did
# that because THE GUARD TOLD IT TO. A guard that ships its own bypass in its error
# message is a guard that will be bypassed, and the agent is not even being
# disobedient when it happens: it is following instructions.
#
# The escape hatch still exists -- the env knob below, and the marker is still a file
# on disk for a human who knows where to look. What changed is that it is no longer
# ADVERTISED at the moment of maximum incentive to take it. A config knob a human
# sets deliberately is a decision; a shell command dangled in front of a blocked
# agent is a trap.
sys.stderr.write(
    "[context-floor] Blocked: context ~%dK (~%s%% of %dK window) over %s and RESUME.md not refreshed since. "
    "%s"
    "Refresh RESUME.md to clear this -- it is the checkpoint the floor exists to force, "
    "and it is almost certainly stale if you are seeing this. "
    "(To turn the floor off on this machine: %s.)\n"
    % (round(occ / 1000), pct, round(window / 1000), trigger_desc, note, disable_hint))
sys.exit(2)
PY
