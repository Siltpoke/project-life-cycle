"""Gate 4's emptiness predicate, measured across eleven payload shapes × BOTH callers.

This file is the oracle for the predicate, for `empty-answer` as its own reason
class, and for both callers (not only the one where the defect was measured).

WHY IT IS PARAMETRIZED PER SHAPE PER CALLER, and not one function with eleven asserts:
`xfail` granularity is the test id. Rows that encode a fix not yet landed are deliberately
red until it lands. Written as one function with
eleven asserts, marking it xfail would also switch off the seven rows that must KEEP
passing — including `false`, the single guard against a
predicate rewrite that un-fixes it. One shape × one caller = one id, so the intentional
reds are individually addressable and a real regression cannot hide behind them.

WHY BOTH CALLERS: Gate 4 is shared, but the two callers do not exercise it identically.
`--require independent_pick` may legitimately be a NON-EMPTY OBJECT, and that row exists
only on the brainstorm side. Measuring the predicate on the code-review caller alone and
publishing the result as a property of the gate is how the one row that matters gets
missed.
"""
import pytest

from test_cross_family_review import _run as _run_brainstorm
from test_cross_family_code_review import _run as _run_codereview

# A payload that omits the required key entirely. `None` already means JSON null, which
# is a DIFFERENT row, so absence needs its own sentinel rather than being spelled None.
ABSENT = object()

# (id, value of the required field, expected status AFTER the fix, expected reason AFTER)
#
# The expectations below are the POST-fix contract. Running this file
# against the pre-fix runner produces a red/green record: the rows that
# encode the fix come back red, and the rows that must not regress come back green.
SHAPES = [
    # --- unchanged: already falls back today, must keep falling back ---
    ("absent", ABSENT, "fallback", "unparseable"),
    ("null", None, "fallback", "unparseable"),
    # `false` keeps BOTH its verdict and its reason word. It falls back today only as a
    # side effect of jq's `//` treating false like null, and the emptiness rule does not
    # reach it (there is no "empty boolean" the way there is an empty string, array or
    # object) — so it is not an `empty-answer`, it is the status quo preserved. The
    # documents pin the verdict and are silent on the reason; this row is the choice,
    # made to match the exclusive definition of `empty-answer` and its precedent of
    # leaving an inaccurate reason word in place rather than widening scope.
    ("false", False, "fallback", "unparseable"),
    # --- the measured holes: pass today, must fall back after the fix ---
    ("empty_string", "", "fallback", "empty-answer"),
    ("whitespace_only", " \t\n ", "fallback", "empty-answer"),
    ("empty_array", [], "fallback", "empty-answer"),
    ("empty_object", {}, "fallback", "empty-answer"),
    # --- must stay passing: a predicate that reddens any of these is a regression ---
    ("nonempty_object", {"option": "a", "why": "b"}, "succeeded", None),
    ("nonempty_array", ["a"], "succeeded", None),
    ("zero", 0, "succeeded", None),
    ("one_word_string", "clean", "succeeded", None),
]

# While a fix is pending, its rows go here as xfail(strict=True) — they encode a fix that
# does not exist yet, and strict means an early green is a failure too, so nothing
# can turn them green except the fix and no new red can hide in a red background.
# Once the fix lands, every one of them turns green, which under strict is
# reported as an unexpected pass, so the markers come off with it. The set is
# kept, empty, so the mechanism is visible to the next task that needs it.
NOT_YET_FIXED: set[str] = set()


def _payload(field: str, value):
    return {} if value is ABSENT else {field: value}


def _mark(shape_id):
    if shape_id in NOT_YET_FIXED:
        return pytest.mark.xfail(strict=True, reason="the fix has not landed yet")
    return ()


def _cases():
    return [pytest.param(sid, val, status, reason, marks=_mark(sid), id=sid)
            for sid, val, status, reason in SHAPES]


@pytest.mark.parametrize("shape_id,value,expected_status,expected_reason", _cases())
def test_brainstorm_caller(tmp_path, shape_id, value, expected_status, expected_reason):
    """`cross-family-review.sh` with its default `--require independent_pick`."""
    _cp, r = _run_brainstorm(tmp_path, payload=_payload("independent_pick", value))
    assert r is not None, "no envelope was written"
    assert r["status"] == expected_status, r
    if expected_status == "fallback":
        assert r["fallback_reason"] == expected_reason, r
        assert "pick" not in r, r
    else:
        assert "fallback_reason" not in r, r


@pytest.mark.parametrize("shape_id,value,expected_status,expected_reason", _cases())
def test_code_review_caller(tmp_path, shape_id, value, expected_status, expected_reason):
    """`cross-family-code-review.sh`, which fixes `--require verdict`."""
    _cp, r, _tp = _run_codereview(tmp_path, payload=_payload("verdict", value))
    assert r is not None, "no envelope was written"
    assert r["status"] == expected_status, r
    if expected_status == "fallback":
        assert r["fallback_reason"] == expected_reason, r
        assert "review" not in r, r
    else:
        assert "fallback_reason" not in r, r
