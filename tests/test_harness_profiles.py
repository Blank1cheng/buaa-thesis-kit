from copy import deepcopy
from dataclasses import FrozenInstanceError, is_dataclass

import pytest

from buaa_thesis_kit.harness.profiles import (
    HarnessProfile,
    evaluate_profile,
    load_profile,
    normalize_gate_board,
)


LATEX_REQUIRED_GATES = {
    "G20",
    "G21",
    "G22",
    "G23",
    "G24",
    "G25",
    "G27",
    "G28",
}
WORD_LAYOUT_GATES = {"G07", "G08"}
PROFILE_NAMES = {
    "latex_pdf",
    "word_editable",
    "legacy_word_layout",
    "agent_visual_review",
}


def _board_with_required_statuses(profile, status="pass"):
    return {gate_id: {"status": status} for gate_id in profile.required_gates}


def test_load_latex_pdf_profile_is_frozen_and_has_expected_gate_policy():
    profile = load_profile("latex_pdf")

    assert isinstance(profile, HarnessProfile)
    assert is_dataclass(profile)
    assert profile.name == "latex_pdf"
    assert LATEX_REQUIRED_GATES <= set(profile.required_gates)
    assert "G26" in profile.optional_gates
    assert "G07" not in profile.required_gates

    with pytest.raises(FrozenInstanceError):
        profile.name = "changed"


def test_word_and_legacy_profiles_are_separate_from_latex_gate_policy():
    latex = load_profile("latex_pdf")
    word = load_profile("word_editable")
    legacy = load_profile("legacy_word_layout")

    assert word.name == "word_editable"
    assert legacy.name == "legacy_word_layout"
    assert word != legacy
    assert set(word.required_gates) != set(legacy.required_gates)
    assert WORD_LAYOUT_GATES <= (
        set(legacy.required_gates) | set(legacy.optional_gates)
    )
    assert WORD_LAYOUT_GATES.isdisjoint(
        set(latex.required_gates) | set(latex.optional_gates)
    )


def test_agent_visual_review_requires_manifest_identity_then_completeness():
    profile = load_profile("agent_visual_review")

    assert profile.name == "agent_visual_review"
    required = list(profile.required_gates)
    assert required[:2] == ["V00", "V01"]


def test_unknown_profile_lists_available_profiles():
    with pytest.raises(ValueError) as exc_info:
        load_profile("not-a-profile")

    message = str(exc_info.value)
    assert "not-a-profile" in message
    for profile_name in PROFILE_NAMES:
        assert profile_name in message


@pytest.mark.parametrize(
    "gate_board, gate_id",
    [
        ({"G20": {"status": "pass"}}, "G20"),
        ({"gates": [{"id": "G00", "status": "pass"}]}, "G00"),
    ],
)
def test_normalize_gate_board_supports_mapping_and_legacy_progress_without_mutation(
    gate_board, gate_id
):
    original = deepcopy(gate_board)

    normalized = normalize_gate_board(gate_board)

    assert normalized[gate_id]["status"] == "pass"
    assert gate_board == original
    assert normalized is not gate_board


def test_evaluate_profile_passes_when_every_required_gate_passes():
    profile = load_profile("latex_pdf")

    result = evaluate_profile(profile, _board_with_required_statuses(profile))

    assert result["profile"] == "latex_pdf"
    assert result["status"] == "pass"
    assert result["missing_gates"] == []
    assert result["failed_gates"] == []
    assert result["review_gates"] == []
    assert set(result["required_gates"]) == set(profile.required_gates)
    assert set(result["optional_gates"]) == set(profile.optional_gates)


@pytest.mark.parametrize("optional_status", [None, "todo", "skipped"])
def test_optional_absent_todo_or_skipped_does_not_change_a_passing_profile(
    optional_status,
):
    profile = load_profile("latex_pdf")
    board = _board_with_required_statuses(profile)
    if optional_status is not None:
        board[profile.optional_gates[0]] = {"status": optional_status}

    result = evaluate_profile(profile, board)

    assert result["status"] == "pass"
    assert result.get("optional_failed_gates", []) == []
    assert result["optional_review_gates"] == []


@pytest.mark.parametrize("optional_status", ["needs_review", "unknown_status"])
def test_optional_review_or_unknown_nonempty_status_requires_review(optional_status):
    profile = load_profile("latex_pdf")
    board = _board_with_required_statuses(profile)
    optional_gate = profile.optional_gates[0]
    board[optional_gate] = {"status": optional_status}

    result = evaluate_profile(profile, board)

    assert result["status"] == "needs_review"
    assert result.get("optional_failed_gates", []) == []
    assert result["optional_review_gates"] == [optional_gate]


def test_failed_optional_gate_fails_without_polluting_required_failures():
    profile = load_profile("latex_pdf")
    board = _board_with_required_statuses(profile)
    optional_gate = profile.optional_gates[0]
    board[optional_gate] = {"status": "failed"}

    result = evaluate_profile(profile, board)

    assert result.get("optional_failed_gates", []) == [optional_gate]
    assert result["failed_gates"] == []
    assert result["status"] == "failed"


def test_evaluate_profile_reports_exact_failed_gate():
    profile = load_profile("latex_pdf")
    board = _board_with_required_statuses(profile)
    failed_gate = profile.required_gates[0]
    board[failed_gate]["status"] = "failed"

    result = evaluate_profile(profile, board)

    assert result["status"] == "failed"
    assert result["failed_gates"] == [failed_gate]
    assert result["missing_gates"] == []
    assert result["review_gates"] == []


@pytest.mark.parametrize("gate_status", ["needs_review", "todo", "skipped"])
def test_evaluate_profile_requires_review_for_unresolved_required_gate(gate_status):
    profile = load_profile("latex_pdf")
    board = _board_with_required_statuses(profile)
    review_gate = profile.required_gates[0]
    board[review_gate]["status"] = gate_status

    result = evaluate_profile(profile, board)

    assert result["status"] == "needs_review"
    assert result["failed_gates"] == []
    assert result["missing_gates"] == []
    assert result["review_gates"] == [review_gate]


def test_evaluate_profile_fails_when_a_required_gate_is_missing():
    profile = load_profile("latex_pdf")
    board = _board_with_required_statuses(profile)
    missing_gate = profile.required_gates[0]
    del board[missing_gate]

    result = evaluate_profile(profile, board)

    assert result["status"] == "failed"
    assert result["missing_gates"] == [missing_gate]
    assert result["failed_gates"] == []


def test_one_passing_gate_does_not_override_another_failed_gate():
    profile = load_profile("latex_pdf")
    board = _board_with_required_statuses(profile)
    passing_gate, failed_gate = profile.required_gates[:2]
    board[passing_gate]["status"] = "pass"
    board[failed_gate]["status"] = "failed"

    result = evaluate_profile(profile, board)

    assert result["status"] == "failed"
    assert result["failed_gates"] == [failed_gate]


def test_evaluate_profile_result_contains_the_complete_contract():
    profile = load_profile("latex_pdf")

    result = evaluate_profile(profile, _board_with_required_statuses(profile))

    assert {
        "profile",
        "status",
        "missing_gates",
        "failed_gates",
        "review_gates",
        "required_gates",
        "optional_gates",
        "optional_failed_gates",
    } <= result.keys()


def test_failed_source_status_is_preserved_verbatim_during_evaluation():
    profile = load_profile("latex_pdf")
    board = _board_with_required_statuses(profile)
    failed_gate = profile.required_gates[0]
    board[failed_gate] = {"status": "failed", "detail": "source verdict"}
    original = deepcopy(board)

    result = evaluate_profile(profile, board)

    assert board == original
    assert board[failed_gate]["status"] == "failed"
    assert normalize_gate_board(board)[failed_gate]["status"] == "failed"
    assert result["status"] == "failed"
    assert result["failed_gates"] == [failed_gate]
