"""`scripts/ledger-append.sh`, the ledger's sole JSON emitter.

Four assertions, one per clause of the record contract's oracle, and one mutant per assertion. Every mutant
below is BUILT AND RUN by this suite rather than described in a commit message: a mutant that is
only claimed is a claim.

Two rules the mutation helper enforces so a mutant cannot silently no-op:
  * the text it replaces must occur EXACTLY once, asserted; and
  * the mutated file must differ from the original, asserted.
"Mutant did not take effect" and "mutant survived" print the same green otherwise.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

IMPL = Path(
    os.environ.get(
        "PLC_LEDGER_APPEND_IMPL",
        Path(__file__).resolve().parent / "ledger-append.sh",
    )
)

# The required-field list, written out here rather than imported from the script under test. An oracle that
# reads its expectation out of its subject is not an oracle: a test that
# reads the declaration from the file it is testing goes green on a stub.
REQUIRED_FIELDS = [
    "specversion",
    "run_id",
    "repo_id",
    "phase",
    "stage_id",
    "attempt_id",
    "type",
    "status",
    "observed",
    "observer",
    "started_at",
    "completed_at",
    "artifacts",
]

# Every one of these has bitten a value encoder somewhere: a quote and a backslash are the JSON
# metacharacters, a tab and a newline are the two whitespace bytes JSON refuses raw inside a
# string, and a leading `-` is the path that gets eaten by an argument parser rather than by an
# encoder. The last one is why paths reach jq as OPTION VALUES and never as positional arguments.
HOSTILE_PATHS = [
    'docs/quote".md',
    "docs/back\\slash.md",
    "docs/tab\there.md",
    "docs/new\nline.md",
    "-leading-dash.md",
    "docs/all\"of\\them\t\nat once.md",
    # Multibyte, but deliberately NOT CJK: any non-ASCII sequence exercises the same multibyte
    # path, so the fixture does not need CJK to cover it.
    "docs/unicode-é-ß-→.md",
]


def _run(impl: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", str(impl), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _append(impl: Path, ledger: Path, **over: str | list[str] | None):
    """One valid record, with named overrides. Every field is passed as a scalar — the helper is
    never handed pre-built JSON, which is the property that makes it the SOLE encoder."""
    fields: dict[str, str | None] = {
        "--run-id": "run-1",
        "--repo-id": "repo-abc",
        "--phase": "p1",
        "--stage-id": "qa_log",
        "--attempt-id": "1",
        "--type": "stage_observation",
        "--status": "done",
        "--observed": "true",
        "--observer": "close-gate.sh",
        "--started-at": "2026-08-13T10:00:00Z",
        "--completed-at": "2026-08-13T10:00:05Z",
    }
    artifacts = over.pop("artifacts", []) or []
    attributes = over.pop("attributes", []) or []
    retro = bool(over.pop("retro", False))
    for key, value in over.items():
        fields["--" + key.replace("_", "-")] = value  # type: ignore[assignment]

    argv: list[str] = ["append", "--file", str(ledger)]
    for key, value in fields.items():
        if value is None:
            continue
        argv += [key, str(value)]
    if retro:
        argv += ["--retro"]  # a flag, not a name/value pair
    for path in artifacts:  # type: ignore[union-attr]
        argv += ["--artifact", path]
    for pair in attributes:  # type: ignore[union-attr]
        argv += ["--attribute", pair]
    return _run(impl, *argv)


def _sub(tmp_path: Path, name: str = "run") -> Path:
    """A fresh directory for a mutant run, so its ledger never lands beside the real one."""
    target = tmp_path / name
    target.mkdir(parents=True, exist_ok=True)
    return target


def _records(ledger: Path) -> list[dict]:
    return [json.loads(line) for line in ledger.read_text().splitlines() if line]


def _mutant(tmp_path: Path, old: str, new: str, name: str = "mutant.sh") -> Path:
    source = IMPL.read_text()
    assert source.count(old) == 1, (
        f"mutation target must occur exactly once, found {source.count(old)}: {old!r}"
    )
    target = tmp_path / name
    target.write_text(source.replace(old, new))
    assert target.read_text() != source, "mutant did not change the file"
    return target


# ---------------------------------------------------------------------------
# The corpus: every record shape this suite produces. Assertions 2 and 3 are stated over it,
# because the oracle's wording is "every record the test suite produces" and not "one happy record".
# ---------------------------------------------------------------------------
def _build_corpus(impl: Path, ledger: Path) -> list[dict]:
    expected = 0

    result = _append(impl, ledger, artifacts=HOSTILE_PATHS, attributes=["k=v", "note=a=b"])
    assert result.returncode == 0, result.stderr
    expected += 1

    # A running stage: no end time yet, and the field is present-and-null rather than absent.
    result = _append(
        impl, ledger, stage_id="spec", status="running", observed="false",
        type="stage_claim", completed_at=None,
    )
    assert result.returncode == 0, result.stderr
    expected += 1

    # A real retry: attempt 1 fails, attempt 2 follows. Written as two records because the
    # file-level rule requires the attempt sequence of a (run_id, stage_id) to be 1..N with no
    # gaps — and it caught this fixture, which had a lone attempt 2. The rule was right and the
    # fixture was wrong: an attempt 2 with no attempt 1 is a lost record, which is precisely what
    # the rule is for.
    for attempt in ("1", "2"):
        result = _append(
            impl, ledger, stage_id="close_gate_task", status="failed", observed="true",
            attempt_id=attempt, task_id="T1",
        )
        assert result.returncode == 0, result.stderr
        expected += 1

    result = _append(
        impl, ledger, stage_id="smoke", type="applicability", observed="false",
        reason="no user-visible surface in this phase",
    )
    assert result.returncode == 0, result.stderr
    expected += 1

    result = _append(impl, ledger, stage_id="journal", observed="false", retro="")
    assert result.returncode == 0, result.stderr
    expected += 1

    records = _records(ledger)
    # Non-emptiness, asserted rather than assumed. A corpus that failed to build makes every
    # "no record does X" assertion below vacuously true — the exact shape of a green that proves
    # nothing.
    assert len(records) == expected, f"expected {expected} records, got {len(records)}"
    return records


# ---------------------------------------------------------------------------
# Assertion (i) — hostile paths round-trip byte-for-byte.
# ---------------------------------------------------------------------------
def _assert_hostile_paths_round_trip(impl: Path, tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    result = _append(impl, ledger, artifacts=HOSTILE_PATHS)
    assert result.returncode == 0, result.stdout + result.stderr
    records = _records(ledger)
    assert len(records) == 1, f"expected 1 record, got {len(records)}"
    read_back = [a["path"] for a in records[0]["artifacts"]]
    assert read_back == HOSTILE_PATHS, f"paths did not round-trip: {read_back!r}"
    # Each record is exactly one physical line, even with a newline inside a path — the property
    # that makes single-line `>>` appends safe at all.
    lines = ledger.read_text().splitlines()
    assert len(lines) == 1, f"one record must be one physical line, got {len(lines)}"


def test_hostile_paths_round_trip(tmp_path: Path) -> None:
    _assert_hostile_paths_round_trip(IMPL, tmp_path)


def test_mutant_hand_rolled_encoder_breaks_hostile_paths(tmp_path: Path) -> None:
    """Drop the escaping — build the artifacts array by string concatenation, which is the
    encoder-divergence class in its purest form."""
    mutant = _mutant(
        tmp_path,
        """artifacts_json=$(printf '%s' "$artifacts_json" | jq -c --arg p "$2" '. + [{path: $p}]')""",
        """artifacts_json="${artifacts_json%]}"; [ "$artifacts_json" = "[" ] || """
        """artifacts_json="$artifacts_json,"; artifacts_json="$artifacts_json{\\"path\\":\\"$2\\"}]" """,
    )
    with pytest.raises(AssertionError):
        _assert_hostile_paths_round_trip(mutant, _sub(tmp_path))


def test_mutant_sanitizing_encoder_breaks_hostile_paths(tmp_path: Path) -> None:
    """The sharper half of the same mutant, and the reason it exists: the one above dies at the
    WRITER — a hand-rolled encoder emits text jq refuses, so the script exits non-zero and the
    byte-for-byte comparison is never reached. That proves the write path can fail; it proves
    nothing about the comparison. This one emits VALID JSON carrying the WRONG bytes (it strips
    the metacharacters instead of escaping them), which only the comparison can catch."""
    mutant = _mutant(
        tmp_path,
        """jq -c --arg p "$2" '. + [{path: $p}]'""",
        """jq -c --arg p "$2" '. + [{path: ($p | gsub("[\\"\\\\\\\\\\t\\n]"; ""))}]'""",
        name="sanitizer.sh",
    )
    with pytest.raises(AssertionError):
        _assert_hostile_paths_round_trip(mutant, _sub(tmp_path, "sanitized"))


# ---------------------------------------------------------------------------
# Assertion (ii) — every required field is present on every record the suite produces.
# ---------------------------------------------------------------------------
def _assert_every_required_field_present(impl: Path, tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    records = _build_corpus(impl, ledger)
    for index, record in enumerate(records):
        missing = [f for f in REQUIRED_FIELDS if f not in record]
        assert not missing, f"record {index} is missing {missing}: {record}"
    # `completed_at` is PRESENT on a running record and null — the field is required, the value is
    # not yet known, and fabricating an end time would make a derived duration a lie.
    running = [r for r in records if r["status"] == "running"]
    assert running and all(r["completed_at"] is None for r in running)
    assert all(r["completed_at"] is not None for r in records if r["status"] != "running")
    # And the script agrees with itself: its own validator accepts everything it wrote.
    assert _run(impl, "validate", str(ledger)).returncode == 0


def test_every_required_field_present_on_every_record(tmp_path: Path) -> None:
    _assert_every_required_field_present(IMPL, tmp_path)


def test_mutant_dropped_field_reds_the_presence_assertion(tmp_path: Path) -> None:
    """Drops `observer` from the emitter. This one dies at the writer's own validator — the record
    is refused and never reaches disk."""
    mutant = _mutant(tmp_path, "       observer: $observer,\n", "")
    with pytest.raises(AssertionError):
        _assert_every_required_field_present(mutant, _sub(tmp_path))


def test_mutant_dropped_field_on_both_sides_reds_the_presence_assertion(tmp_path: Path) -> None:
    """And this one drops it from the validator's required list too, so a record genuinely missing
    `observer` IS written. Only then does the suite's own field-presence check — rather than the
    script's refusal — have to be the thing that reds. Same reason as the sanitizing encoder above:
    a mutant killed by the guard in front of an assertion says nothing about the assertion."""
    stripped = _mutant(tmp_path, "       observer: $observer,\n", "", name="stripped.sh")
    source = stripped.read_text()
    required = '"observed","observer","started_at","completed_at","artifacts"]'
    assert source.count(required) == 1
    both = tmp_path / "both.sh"
    both.write_text(source.replace(required, '"observed","started_at","completed_at","artifacts"]'))
    with pytest.raises(AssertionError):
        _assert_every_required_field_present(both, _sub(tmp_path, "both"))


# ---------------------------------------------------------------------------
# Assertion (iii) — no record stores a duration.
# ---------------------------------------------------------------------------
def _assert_no_record_stores_a_duration(impl: Path, tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    records = _build_corpus(impl, ledger)
    for index, record in enumerate(records):
        stored = [k for k in record if k.startswith("duration")]
        stored += [
            "attributes." + k
            for k in record.get("attributes", {})
            if k.startswith("duration")
        ]
        assert not stored, f"record {index} stores {stored}"


def _assert_validate_rejects_a_stored_duration(impl: Path, tmp_path: Path) -> None:
    """The other half: a record that reached disk some other way is still refused on read."""
    ledger = tmp_path / "planted.jsonl"
    good = {
        "specversion": "1", "run_id": "r", "repo_id": "x", "phase": "p1",
        "stage_id": "qa_log", "attempt_id": 1, "type": "stage_observation", "status": "done",
        "observed": True, "observer": "scan", "started_at": "2026-08-13T10:00:00Z",
        "completed_at": "2026-08-13T10:00:05Z", "artifacts": [],
    }
    ledger.write_text(
        json.dumps({**good, "duration_ms": 5000}) + "\n"
        + json.dumps({**good, "attributes": {"duration_s": "5"}}) + "\n"
    )
    result = _run(impl, "validate", str(ledger))
    assert result.returncode != 0, "validate accepted records that store a duration"
    # Both bans are asserted separately on purpose: they are two independent clauses, and removing
    # only the top-level one still leaves the file rejected by the attributes one — so a test that
    # judged this by exit code alone would score that mutant as dead while it was still alive.
    assert "duration must never be stored: duration_ms" in result.stderr, (
        f"the top-level duration ban did not fire: {result.stderr!r}"
    )
    assert "duration must never be stored: attributes.duration_s" in result.stderr, (
        f"the attributes duration ban did not fire: {result.stderr!r}"
    )


def test_no_record_stores_a_duration(tmp_path: Path) -> None:
    _assert_no_record_stores_a_duration(IMPL, tmp_path)


def test_validate_rejects_a_stored_duration(tmp_path: Path) -> None:
    _assert_validate_rejects_a_stored_duration(IMPL, tmp_path)


def test_mutant_stored_duration_reds_the_no_duration_assertion(tmp_path: Path) -> None:
    """Two edits, and the second one is the finding: storing a duration in the emitter alone is
    caught by the script's OWN validator before the record is ever written, so the write fails and
    the corpus is empty. The ban therefore has to be lifted from the validator as well before the
    emitter mutation can even reach disk — the guard is doubled, and this mutant proves it by
    needing both halves removed to survive one of them."""
    mutant = _mutant(
        tmp_path,
        "       artifacts: $artifacts\n",
        '       artifacts: $artifacts,\n       duration_s: 5\n',
    )
    doubly = tmp_path / "mutant2.sh"
    source = mutant.read_text()
    ban = '    + [ ($r | keys[] | select(test("^duration")) | "duration must never be stored: " + .) ]\n'
    assert source.count(ban) == 1
    doubly.write_text(source.replace(ban, ""))
    with pytest.raises(AssertionError):
        _assert_no_record_stores_a_duration(doubly, _sub(tmp_path))


def test_mutant_dropped_duration_ban_reds_the_validate_assertion(tmp_path: Path) -> None:
    mutant = _mutant(
        tmp_path,
        '    + [ ($r | keys[] | select(test("^duration")) | "duration must never be stored: " + .) ]\n',
        "",
    )
    with pytest.raises(AssertionError):
        _assert_validate_rejects_a_stored_duration(mutant, _sub(tmp_path))


# ---------------------------------------------------------------------------
# Assertion (iv) — an applicability record with no usable reason is refused AT WRITE TIME.
# ---------------------------------------------------------------------------
def _assert_applicability_without_reason_is_refused(impl: Path, tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    assert _append(impl, ledger).returncode == 0
    before = ledger.read_bytes()

    for label, over in (
        ("absent", {}),
        ("empty", {"reason": ""}),
        ("blank", {"reason": "   \t "}),
    ):
        result = _append(
            impl, ledger, stage_id="smoke", type="applicability", observed="false", **over
        )
        assert result.returncode != 0, f"{label}: expected refusal, got 0\n{result.stdout}"
        assert "non-empty reason" in result.stderr, f"{label}: {result.stderr}"
        # Refused means NOTHING was written. A partial or appended-anyway record is the forged
        # suppression this guard exists to stop (the interim authorization gap).
        assert ledger.read_bytes() == before, f"{label}: the ledger was modified"

    accepted = _append(
        impl, ledger, stage_id="smoke", type="applicability", observed="false",
        reason="no user-visible surface",
    )
    assert accepted.returncode == 0, accepted.stderr
    assert _records(ledger)[-1]["reason"] == "no user-visible surface"


def test_applicability_without_reason_is_refused(tmp_path: Path) -> None:
    _assert_applicability_without_reason_is_refused(IMPL, tmp_path)


def test_mutant_dropped_reason_check_reds_the_refusal_assertion(tmp_path: Path) -> None:
    mutant = _mutant(
        tmp_path,
        '        then "an applicability record requires a non-empty reason" else empty end ]',
        "        then empty else empty end ]",
    )
    with pytest.raises(AssertionError):
        _assert_applicability_without_reason_is_refused(mutant, _sub(tmp_path))


# ---------------------------------------------------------------------------
# Supporting rows: the validator's other clauses, each paired with a reason it could go red.
# ---------------------------------------------------------------------------
def test_validate_accepts_nothing_it_did_not_have_to(tmp_path: Path) -> None:
    """Bad records, one clause each. Every row here would pass a validator that only parsed JSON."""
    good = {
        "specversion": "1", "run_id": "r", "repo_id": "x", "phase": "p1",
        "stage_id": "qa_log", "attempt_id": 1, "type": "stage_observation", "status": "done",
        "observed": True, "observer": "scan", "started_at": "2026-08-13T10:00:00Z",
        "completed_at": "2026-08-13T10:00:05Z", "artifacts": [],
    }
    cases = [
        ({"observed": "true"}, "observed must be a boolean"),
        ({"attempt_id": 0}, "attempt_id must be an integer >= 1"),
        ({"type": "stage_done"}, "type must be one of"),
        ({"status": "ok"}, "status must be one of"),
        ({"started_at": "2026-08-13 10:00:00"}, "started_at must be RFC3339 UTC"),
        ({"status": "running"}, "a running record must have completed_at: null"),
        ({"completed_at": None}, "completed_at is required once status is done"),
        ({"artifacts": ["docs/x.md"]}, "artifacts[] entries must be exactly"),
        ({"artifacts": [{"path": "a", "size": 1}]}, "artifacts[] entries must be exactly"),
        ({"stage_id": ""}, "stage_id must be a non-empty string"),
    ]
    for over, expected in cases:
        ledger = tmp_path / "bad.jsonl"
        ledger.write_text(json.dumps({**good, **over}) + "\n")
        result = _run(IMPL, "validate", str(ledger))
        assert result.returncode != 0, f"{over} was accepted"
        assert expected in result.stderr, f"{over}: {result.stderr}"

    ledger = tmp_path / "missing.jsonl"
    stripped = {k: v for k, v in good.items() if k != "observed"}
    ledger.write_text(json.dumps(stripped) + "\n")
    result = _run(IMPL, "validate", str(ledger))
    assert result.returncode != 0
    assert "missing required field: observed" in result.stderr

    ledger = tmp_path / "good.jsonl"
    ledger.write_text(json.dumps(good) + "\n")
    assert _run(IMPL, "validate", str(ledger)).returncode == 0


def test_validate_reports_a_torn_last_line(tmp_path: Path) -> None:
    """No trailing newline is a truncated append, not a style. It is reported, and the last record
    is still judged rather than dropped — dropping it would turn a torn write into a clean read."""
    ledger = tmp_path / "torn.jsonl"
    assert _append(IMPL, ledger).returncode == 0
    body = ledger.read_text()
    ledger.write_text(body + body.rstrip("\n").replace('"observed":true', '"observed":"yes"'))
    result = _run(IMPL, "validate", str(ledger))
    assert result.returncode != 0
    assert "does not end with a newline" in result.stderr
    assert "observed must be a boolean" in result.stderr


def test_validate_rejects_junk_lines(tmp_path: Path) -> None:
    ledger = tmp_path / "junk.jsonl"
    ledger.write_text("not json\n\n[1,2]\n")
    result = _run(IMPL, "validate", str(ledger))
    assert result.returncode != 0
    assert "not valid JSON" in result.stderr
    assert "empty line" in result.stderr
    assert "record is not a JSON object" in result.stderr


def test_valid_json_that_is_not_an_object_says_so(tmp_path: Path) -> None:
    """`null` and `false` parse. Reporting them as unparseable would name the wrong defect, and
    that is exactly what `jq -e .` does — it exits non-zero on both, so the parse probe uses a
    bare `jq .`. The distinction only shows up on these two literals, which is why they get a row
    rather than a comment."""
    ledger = tmp_path / "literals.jsonl"
    ledger.write_text("null\nfalse\n")
    result = _run(IMPL, "validate", str(ledger))
    assert result.returncode != 0
    assert "not valid JSON" not in result.stderr, result.stderr
    assert result.stderr.count("record is not a JSON object") == 2, result.stderr


def test_usage_errors_are_distinguishable_from_invalid_records(tmp_path: Path) -> None:
    """Exit 2 is "you called me wrong", exit 1 is "the record is not legal". A caller that wraps
    this in `|| true` (as every caller does) still has the two apart in its logs."""
    assert _run(IMPL).returncode == 2
    assert _run(IMPL, "append", "--file", str(tmp_path / "l.jsonl")).returncode == 2
    assert _run(IMPL, "append", "--file", str(tmp_path / "l.jsonl"), "--nope", "x").returncode == 2
    result = _append(IMPL, tmp_path / "l.jsonl", observed="yes")
    assert result.returncode == 2
    assert "--observed must be true or false" in result.stderr
    assert not (tmp_path / "l.jsonl").exists()


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq is the dependency under test")
def test_jq_absent_is_a_named_failure_not_a_silent_one(tmp_path: Path) -> None:
    """The named-failure rule is the reader's, but the same posture is cheap here and the alternative — a writer that
    quietly emits nothing when jq is missing — is a ledger that lies by omission."""
    empty_path = tmp_path / "bin"
    empty_path.mkdir()
    result = subprocess.run(
        ["/bin/bash", str(IMPL), "validate", str(tmp_path / "x.jsonl")],
        capture_output=True, text=True, check=False,
        env={**os.environ, "PATH": str(empty_path)},
    )
    assert result.returncode == 2
    assert "jq not found" in result.stderr
