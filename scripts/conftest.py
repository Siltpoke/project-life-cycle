import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# ---------------------------------------------------------------------------------------------
# Tests that cannot pass in this repository, skipped with a stated reason instead of deleted.
#
# Each one checks a record that belongs to the maintainers' own working copy -- planning docs,
# the backlog closure ledger, the project's own `.claude/` gate configuration, or changelog
# entries older than the public changelog -- none of which ship here. Run against this tree they
# fail for that reason alone, and a red suite on a clean clone would hide any real failure behind
# them. They are listed by name so the list is reviewable, and the skip reason is printed, so a
# skipped test is never mistaken for a pass.
#
# The list is MEASURED, not remembered: it is exactly the set that fails when this hook is removed
# and the suite runs against this tree. It is re-measured for every release rather than carried
# forward, and entries that have stopped failing are dropped -- adding a test here that would pass
# is a silent loss of coverage, which is why the list shrank the last two times it was measured.
#
# 4.1.1 dropped four. Two were freed by a fix in this release; the other two were freed by
# RESTORING CONTENT TO THE CHANGELOG. They had been failing because this changelog's entry for
# the breaking change named the key without showing a value you could paste, and the rows exist
# to catch exactly that. A row that goes red because a notice is thin is not a row to skip.
#
# Ids are matched WITHOUT their parameters, so a parametrised test listed here is skipped for
# every parameter, including any that would pass on their own.
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
    "scripts/test_corpus_validators.py::test_archiving_a_declaration_does_not_move_any_position",
    "scripts/test_document_map.py::test_the_claim_about_status_doc_is_true_of_this_repo",
    "scripts/test_exit_zero_claims.py::test_the_changelog_entry_is_marked_superseded_not_rewritten",
    "scripts/test_filings.py::test_the_entry_exists_and_is_a_filing_not_a_mention",
    "scripts/test_filings.py::test_the_index_lists_every_filing_as_open",
    "scripts/test_filings.py::test_the_label_judgement_is_recorded_as_a_decision",
    "scripts/test_gate_envelope.py::test_mutant_manifest_with_an_argument_defeats_the_no_arguments_row",
    "scripts/test_gate_envelope.py::test_the_gate_invokes_this_checker_with_no_arguments",
    "scripts/test_generator_edges.py::test_a_backslash_in_the_map_path_does_not_change_which_file_is_which",
    "scripts/test_generator_edges.py::test_crlf_input_is_read_as_the_same_paths",
    "scripts/test_generator_edges.py::test_the_generator_edge_alone_selects_the_oracle",
    "scripts/test_generator_edges.py::test_the_real_table_declares_both_required_edges",
    "scripts/test_input_map_guards.py::test_the_invariant_is_registered_in_the_real_gate",
    "scripts/test_ledger_writers.py::test_a_failing_writer_cannot_change_the_gates_verdict",
    "scripts/test_ledger_writers.py::test_a_stage_the_gate_never_reached_renders_missing_not_done",
    "scripts/test_ledger_writers.py::test_mutant_a_propagating_writer_failure_reds_the_gate",
    "scripts/test_ledger_writers.py::test_removing_only_one_guard_is_not_enough",
    "scripts/test_ledger_writers.py::test_the_gate_records_the_checks_it_ran",
    "scripts/test_no_icloud_guard.py::test_the_manifest_description_matches_the_mechanism",
    "scripts/test_obituary.py::test_each_surface_says_the_constraint_was_lifted",
    "scripts/test_release_notice.py::test_the_notice_says_the_phrasing_constraint_is_GONE",
    "scripts/test_roadmap_parsers_unchanged.py::test_control_fifth_column",
    "scripts/test_roadmap_parsers_unchanged.py::test_control_heading_inside_the_table",
    "scripts/test_roadmap_parsers_unchanged.py::test_control_one_character_in_a_mainline_row",
    "scripts/test_roadmap_parsers_unchanged.py::test_insertion_points_are_all_safe",
    "scripts/test_select_tests.py::test_ac10_a_tracked_only_reader_is_not",
    "scripts/test_select_tests.py::test_ac10_an_untracked_reader_is_selected_for_an_empty_change",
    "scripts/test_select_tests.py::test_ac1_the_oracle_is_selected",
    "scripts/test_select_tests.py::test_ac2_and_it_is_not_everything",
    "scripts/test_session_card_no_network.py::test_the_guard_is_declared_in_the_close_gate_manifest",
    "scripts/test_stage_registry.py::test_the_invariant_is_declared_in_the_gate_manifest",
}

_REASON = ("checks records the maintainers keep outside this repository (planning docs, "
           "gate configuration, or changelog history older than this public changelog)")


def pytest_collection_modifyitems(config, items):
    for item in items:
        if item.nodeid.split("[", 1)[0] in _NEEDS_MAINTAINER_RECORDS:
            item.add_marker(pytest.mark.skip(reason=_REASON))
