#!/usr/bin/env bash
# project-lifecycle — shared floor-math jq definitions.
#
# SOURCED, never executed. It defines exactly one shell variable, `PLC_FLOOR_JQ_DEFS`, holding
# the three jq definitions both context hooks need — `trim`, `intenv`, `floatenv` — and nothing
# else. The env READS stay in each caller: they bind to different downstream shapes
# (`context-floor.sh` also needs `$step`, and its non-finite branch signals OVERFLOW where the
# nudge maps to 0), and folding those in would be the "unify the differences away" move that must be avoided.
#
# WHY THIS FILE EXISTS. The two hooks carried byte-identical copies of these definitions, and
# the copies drifted twice in ways that mattered: `close-gate-nudge.sh` lost the
# `* 1` that `context-floor.sh` carried — the counter-example sat one file away
# and nothing connected them, and the consequence was the nudge going SILENT on a subnormal
# percentage floor where python would have warned. That is the drift class this file closes.
#
# WHAT IT DOES NOT CLOSE, stated so the claim is not read wider than the mechanism: it closes
# SOURCE-level drift within one tree. It does NOT close deployment-version drift — a hook run
# from the plugin cache and a hook run from the working tree can still source different copies
# of this file, because they are different trees. That is a separate problem.
#
# The heredoc delimiter is QUOTED (`<<'PLC_FLOOR_JQ_EOF'`). Unquoted, bash would expand jq's own
# `$n` / `$v` / `$unset` / `$empty` before jq ever saw them, blanking parts of a program that
# still PARSES — a corruption that shows up as a wrong number, not as an error.
PLC_FLOOR_JQ_DEFS="$(cat <<'PLC_FLOOR_JQ_EOF'
  # python int()/float() tolerate surrounding whitespace; jq tonumber does not. An
  # un-trimmed value matched the pattern, then errored, then took the whole program
  # into the caller's fallback -- silence where python read a perfectly good number.
  # Trim before every conversion.
  def trim: sub("^\\s+"; "") | sub("\\s+$"; "");
  # `[+-]?` because python int("+80000") succeeds; rejecting a leading + would
  # silently move an adopter s floor from 80K to the 150K default.
  #
  # python's int() REJECTS a decimal string ("0.5" raised, falling back to the default), so
  # this requires an integer pattern rather than accepting whatever tonumber would swallow.
  def intenv($n; $unset; $empty):
    env[$n] as $v
    | if   $v == null then $unset
      elif $v == ""   then $empty
      elif ($v | test("^\\s*[+-]?[0-9]+\\s*$")) then ($v | trim | tonumber)
      else $unset end;
  # python float() reaches infinity by two routes: the literal spellings AND an
  # overflowing exponent ("1e309"). Enumerating literals can never be complete, so
  # produce a real infinity here and let the caller decide.
  #
  # The `* 1` is load-bearing. jq keeps a numeric LITERAL at
  # arbitrary precision, so `1e-400 > 0` is true there while python -- which parses into a C
  # double -- UNDERFLOWS it to 0.0 and falls through to the absolute floor. Multiplying by 1
  # forces the value through IEEE754 and reproduces the underflow exactly. Measured:
  # `jq -n ("1e-400"|tonumber) > 0` is true, the same expression `* 1` is false, and python
  # agrees with the second.
  #
  # (Apostrophes are safe HERE and nowhere downstream. This text lives in a quoted heredoc and
  # reaches jq through a DOUBLE-quoted expansion, so a `'` is just a byte. The hazard is text
  # written literally inside a caller's single-quoted jq program -- one apostrophe closes that
  # quote, which is exactly how an earlier attempt at the nudge's version of this comment broke
  # the hook, measured as 5 red rows. Any comment added to a CALLER still obeys the old rule.)
  def floatenv($n; $unset; $empty):
    env[$n] as $v
    | if   $v == null then $unset
      elif $v == ""   then $empty
      elif ($v | test("^\\s*\\+?inf(inity)?\\s*$"; "i")) then  infinite
      elif ($v | test("^\\s*-inf(inity)?\\s*$";    "i")) then -infinite
      else ((($v | trim | tonumber?) // $unset) * 1) end;
PLC_FLOOR_JQ_EOF
)"
