import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# ---------------------------------------------------------------------------------------------
# Tests that cannot pass in this repository, skipped with a stated reason instead of deleted.
#
# Each one checks a record that belongs to the maintainers' own working copy -- planning docs,
# the backlog closure ledger, the project's own `.claude/` gate configuration, or changelog
# entries older than the public changelog -- none of which ship here. Run against this tree they fail for that reason alone, and a red suite on a clean
# clone would hide any real failure behind them. They are listed by name so the list is
# reviewable, and the skip reason is printed, so a skipped test is never mistaken for a pass.
#
# The list is MEASURED, not remembered: it is exactly the set that fails when this hook is removed
# and the suite runs against this tree (re-measured 2026-09-23; five entries that had stopped
# failing were dropped that way). Adding a test here that would pass is a silent loss of coverage.
# ---------------------------------------------------------------------------------------------
import pytest

_NEEDS_MAINTAINER_RECORDS = {
    "scripts/test_ac_evidence.py::test_diff_mode_says_out_loud_that_it_did_not_run",
    "scripts/test_ac_evidence.py::test_task_mode_does_not_write_the_baseline",
    "scripts/test_ac_evidence.py::test_the_check_is_in_both_modes_check_sets",
    "scripts/test_backlog_ledger.py::test_ac10_every_ruled_id_carries_a_human_written_rationale",
    "scripts/test_backlog_ledger.py::test_ac11_migration_tool_is_gone_and_the_report_it_produced_is_present",
    "scripts/test_backlog_ledger.py::test_ac14a_the_in_progress_prose_asserts_no_completion_state",
    "scripts/test_backlog_ledger.py::test_ac14b_the_you_are_here_paragraph_asserts_no_completion_state",
    "scripts/test_backlog_ledger.py::test_ac18_marker_glyphs_are_banned_but_prose_is_not",
    "scripts/test_backlog_ledger.py::test_ac19_no_placeholder_rows_and_at_least_one_backed_closed_value",
    "scripts/test_backlog_ledger.py::test_ac1_key_set_is_whole_minus_exactly_one_named_exemption",
    "scripts/test_backlog_ledger.py::test_ac1b_maxid_input_set_is_unchanged_by_the_fix",
    "scripts/test_backlog_ledger.py::test_ac1c_a_malformed_id_is_refused_not_laundered",
    "scripts/test_backlog_ledger.py::test_ac20_report_matches_the_premigration_snapshot_not_itself",
    "scripts/test_backlog_ledger.py::test_ac3_state_is_derived_from_the_ledger_not_from_title_words",
    "scripts/test_backlog_ledger.py::test_ac4_header_names_which_column_comes_from_where_and_points_at_the_right_one",
    "scripts/test_backlog_ledger.py::test_meta_the_tracked_artifacts_really_are_tracked",
    "scripts/test_ci_status_invariant.py::test_the_guard_is_declared_in_the_close_gate_manifest",
    "scripts/test_close_gate_closure_check.py::test_ac3_unarmed_repo_is_not_failed",
    "scripts/test_close_gate_closure_check.py::test_ac5_check_11_is_present_in_phase_mode",
    "scripts/test_close_gate_wiring_invariant.py::test_every_registered_invariant_points_at_a_file_that_exists",
    "scripts/test_close_gate_wiring_invariant.py::test_every_registration_uses_one_spelling_of_the_interpreter",
    "scripts/test_close_gate_wiring_invariant.py::test_it_is_registered_in_both_places_and_only_those",
    "scripts/test_close_gate_wiring_invariant.py::test_the_registered_names_appear_in_the_scripts_they_name",
    "scripts/test_exit_zero_claims.py::test_the_changelog_entry_is_marked_superseded_not_rewritten",
    "scripts/test_gate_envelope.py::test_mutant_manifest_with_an_argument_defeats_the_no_arguments_row",
    "scripts/test_gate_envelope.py::test_the_gate_invokes_this_checker_with_no_arguments",
    "scripts/test_ledger_writers.py::test_a_failing_writer_cannot_change_the_gates_verdict",
    "scripts/test_ledger_writers.py::test_a_stage_the_gate_never_reached_renders_missing_not_done",
    "scripts/test_ledger_writers.py::test_mutant_a_propagating_writer_failure_reds_the_gate",
    "scripts/test_ledger_writers.py::test_removing_only_one_guard_is_not_enough",
    "scripts/test_ledger_writers.py::test_the_gate_records_the_checks_it_ran",
    "scripts/test_no_icloud_guard.py::test_the_manifest_description_matches_the_mechanism",
    "scripts/test_session_card_no_network.py::test_the_guard_is_declared_in_the_close_gate_manifest",
    "scripts/test_stage_registry.py::test_the_invariant_is_declared_in_the_gate_manifest",
}

_REASON = ("checks records the maintainers keep outside this repository (planning docs, "
           "gate configuration, or changelog history older than this public changelog)")


def pytest_collection_modifyitems(config, items):
    for item in items:
        if item.nodeid.split("[", 1)[0] in _NEEDS_MAINTAINER_RECORDS:
            item.add_marker(pytest.mark.skip(reason=_REASON))
