from __future__ import annotations

from vllm_agent_gateway.acceptance.founder_feedback_loop import (
    FounderFeedbackLoopCase,
    feedback_decision_for_record,
    load_founder_feedback_loop_cases,
    validate_case_catalog,
    validate_feedback_record_decision,
    validate_founder_feedback_loop_report,
)
from vllm_agent_gateway.controllers.workflow_feedback.record import feedback_governance_decision
from scripts.validate_task_decomposition_live import changed_hashes


def case(
    *,
    expected_classifications: tuple[str, ...] = ("useful", "missing"),
    expected_decision_kind: str = "baseline_prompt_candidate",
    expected_gap_class: str = "deterministic_formatter",
) -> FounderFeedbackLoopCase:
    return FounderFeedbackLoopCase(
        case_id="FL125-X",
        surface="gateway",
        target_root="/mnt/c/coinbase_testing_repo_frozen_tmp.github",
        seed_prompt="Explain a function.",
        feedback_template="Record feedback for run {run_id}: missing: baseline candidate.",
        expected_classifications=expected_classifications,
        expected_decision_kind=expected_decision_kind,
        expected_gap_class=expected_gap_class,
    )


def record(*, classifications: list[str], feedback: dict[str, object] | None = None) -> dict[str, object]:
    feedback_value = feedback or {"useful": ["target was right"], "missing": ["baseline candidate"], "notes": ""}
    context = {
        "selected_workflow": "code_investigation.plan",
        "target_run_id": "workflow-router-test",
        "target_workflow": "workflow_router.plan",
        "prompt_case": "FL125-X",
    }
    data: dict[str, object] = {
        "kind": "workflow_feedback_record",
        "status": "completed",
        "run_id": "workflow-feedback-test",
        "target_run_id": "workflow-router-test",
        "target_workflow": "workflow_router.plan",
        "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
        "feedback": feedback_value,
        "feedback_context": context,
        "classifications": classifications,
    }
    decision = feedback_governance_decision(classifications, context, feedback_value)  # type: ignore[arg-type]
    decision["feedback_run_id"] = data["run_id"]
    data["governed_decision"] = decision
    return data


def test_founder_feedback_loop_case_catalog_is_governed() -> None:
    cases = load_founder_feedback_loop_cases()

    assert not validate_case_catalog(cases)
    assert {item.surface for item in cases} == {"gateway", "anythingllm"}
    assert {item.expected_decision_kind for item in cases} == {
        "baseline_prompt_candidate",
        "holdout_prompt_candidate",
        "repair_followup",
        "rejected_finding",
    }


def test_feedback_decision_maps_missing_to_baseline_candidate() -> None:
    test_case = case()
    test_record = record(classifications=["useful", "missing"])
    decision = feedback_decision_for_record(test_record, test_case)

    assert decision["kind"] == "baseline_prompt_candidate"
    assert decision["decision_status"] == "accepted"
    assert decision["gap_class"] == "deterministic_formatter"
    assert decision["validation_result"]["required_gate"] == "baseline_corpus"
    assert validate_feedback_record_decision(test_case, test_record, decision) == []


def test_feedback_decision_maps_holdout_text_to_holdout_candidate() -> None:
    test_case = case(
        expected_decision_kind="holdout_prompt_candidate",
        expected_gap_class="test_coverage",
    )
    test_record = record(
        classifications=["useful", "missing"],
        feedback={"useful": ["read only"], "missing": ["add this as a holdout prompt"], "notes": ""},
    )
    decision = feedback_decision_for_record(test_record, test_case)

    assert decision["kind"] == "holdout_prompt_candidate"
    assert decision["gap_class"] == "test_coverage"
    assert validate_feedback_record_decision(test_case, test_record, decision) == []


def test_feedback_decision_maps_wrong_to_repair_followup() -> None:
    test_case = case(
        expected_classifications=("wrong",),
        expected_decision_kind="repair_followup",
        expected_gap_class="model_capability",
    )
    test_record = record(classifications=["wrong"], feedback={"wrong": ["missed root cause"], "notes": ""})
    decision = feedback_decision_for_record(test_record, test_case)

    assert decision["kind"] == "repair_followup"
    assert decision["validation_result"]["required_gate"] == "eval_repair_loop"
    assert validate_feedback_record_decision(test_case, test_record, decision) == []


def test_feedback_decision_maps_useful_only_to_rejected_finding() -> None:
    test_case = case(
        expected_classifications=("useful",),
        expected_decision_kind="rejected_finding",
        expected_gap_class="none",
    )
    test_record = record(classifications=["useful"], feedback={"useful": ["clear answer"], "notes": ""})
    decision = feedback_decision_for_record(test_record, test_case)

    assert decision["kind"] == "rejected_finding"
    assert decision["decision_status"] == "rejected"
    assert decision["validation_result"]["status"] == "passed"
    assert validate_feedback_record_decision(test_case, test_record, decision) == []


def test_feedback_decision_maps_advisory_text_to_advisory_finding() -> None:
    test_case = case(
        expected_classifications=("useful",),
        expected_decision_kind="advisory_finding",
        expected_gap_class="documentation",
    )
    test_record = record(
        classifications=["useful"],
        feedback={"useful": ["answer is acceptable"], "notes": "advisory only: monitor if repeated"},
    )
    decision = feedback_decision_for_record(test_record, test_case)

    assert decision["kind"] == "advisory_finding"
    assert decision["decision_status"] == "advisory"
    assert decision["validation_result"]["required_gate"] == "repeat_feedback_or_release_review"
    assert validate_feedback_record_decision(test_case, test_record, decision) == []


def test_feedback_decision_maps_deferred_scope_text_to_deferred_finding() -> None:
    test_case = case(
        expected_classifications=("useful",),
        expected_decision_kind="deferred_finding",
        expected_gap_class="scope_deferred",
    )
    test_record = record(
        classifications=["useful"],
        feedback={"useful": ["answer correctly avoided mutation"], "notes": "advanced refactor remains deferred"},
    )
    decision = feedback_decision_for_record(test_record, test_case)

    assert decision["kind"] == "deferred_finding"
    assert decision["decision_status"] == "deferred"
    assert decision["validation_result"]["required_gate"] == "roadmap_reactivation_approval"
    assert validate_feedback_record_decision(test_case, test_record, decision) == []


def test_feedback_decision_rejects_notes_only_without_actionable_evidence() -> None:
    test_case = case(
        expected_classifications=("notes",),
        expected_decision_kind="rejected_finding",
        expected_gap_class="none",
    )
    test_record = record(classifications=["notes"], feedback={"notes": "too vague to act on"})
    decision = feedback_decision_for_record(test_record, test_case)

    assert decision["kind"] == "rejected_finding"
    assert decision["decision_status"] == "rejected"
    assert decision["validation_result"]["reason"] == "notes-only feedback did not include actionable evidence"
    assert validate_feedback_record_decision(test_case, test_record, decision) == []


def test_founder_feedback_loop_report_rejects_missing_decision_coverage() -> None:
    report = {
        "kind": "founder_feedback_loop_live_report",
        "cases": [
            {
                "case_id": "FL125-001",
                "status": "passed",
                "surface": "gateway",
                "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
                "decision": {"kind": "baseline_prompt_candidate"},
                "errors": [],
            }
        ],
        "mutation_proof": {
            "runtime_changed_files": [],
            "target_changed_files": {},
            "target_git_changed": {},
        },
    }

    errors = validate_founder_feedback_loop_report(report)

    assert any("missing decision coverage" in error for error in errors)
    assert any("missing surface coverage" in error for error in errors)


def test_feedback_record_decision_rejects_missing_durable_decision() -> None:
    test_case = case()
    test_record = record(classifications=["useful", "missing"])
    decision = test_record.pop("governed_decision")

    errors = validate_feedback_record_decision(test_case, test_record, decision)  # type: ignore[arg-type]

    assert f"{test_case.case_id} feedback record missing durable governed_decision" in errors


def test_feedback_record_decision_rejects_target_run_mismatch() -> None:
    test_case = case()
    test_record = record(classifications=["useful", "missing"])
    decision = dict(test_record["governed_decision"])  # type: ignore[arg-type]
    decision["target_run_id"] = "workflow-router-other"

    errors = validate_feedback_record_decision(test_case, test_record, decision)

    assert any("decision target_run_id" in error for error in errors)


def test_feedback_report_validation_replays_case_contract() -> None:
    test_case = case()
    test_record = record(classifications=["useful", "missing"])
    decision = dict(test_record["governed_decision"])  # type: ignore[arg-type]
    decision["prompt_case_id"] = "wrong-case"
    report = {
        "kind": "founder_feedback_loop_live_report",
        "cases": [
            {
                "case_id": "FL125-X",
                "status": "passed",
                "surface": "gateway",
                "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
                "feedback_record": test_record,
                "decision": decision,
                "errors": [],
            }
        ],
        "mutation_proof": {
            "runtime_changed_files": [],
            "target_changed_files": {},
            "target_git_changed": {},
        },
    }

    errors = validate_founder_feedback_loop_report(report, [test_case])

    assert any("decision prompt_case_id" in error for error in errors)


def test_changed_hashes_detects_deleted_watched_file() -> None:
    assert changed_hashes({"a.py": "old", "b.py": "same"}, {"b.py": "same"}) == ["a.py"]
