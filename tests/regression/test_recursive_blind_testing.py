from __future__ import annotations

import json
from pathlib import Path

from vllm_agent_gateway.acceptance.recursive_blind_testing import (
    RecursiveBlindTestingValidationConfig,
    validate_recursive_blind_testing,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def write_json(path: Path, value: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_policy() -> dict[str, object]:
    return json.loads((REPO_ROOT / "runtime" / "recursive_blind_testing_policy.json").read_text(encoding="utf-8"))


def validate(tmp_path: Path, *, policy_path: Path | None = None, report_path: Path | None = None) -> dict[str, object]:
    return validate_recursive_blind_testing(
        RecursiveBlindTestingValidationConfig(
            config_root=REPO_ROOT,
            policy_path=policy_path or Path("runtime/recursive_blind_testing_policy.json"),
            report_path=report_path,
            output_path=tmp_path / "recursive-blind-testing-validation.json",
        )
    )


def valid_recursive_report() -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "recursive_blind_testing_report",
        "status": "passed",
        "policy_id": "bounded-recursive-blind-testing-v1",
        "scenario_id": "stable_handoff_usability",
        "rounds": [
            {
                "round_id": "round-1",
                "evaluator_context": {
                    "fork_context": False,
                    "agent_id": "blind-agent-1",
                    "input_summary": "README.stable-handoff.md plus Phase 92 roadmap excerpt",
                },
                "input_refs": [
                    "README.stable-handoff.md",
                    "docs/ACTIONABLE_WORKFLOW_ROADMAP.md",
                ],
                "blind_findings": [
                    {
                        "id": "F001",
                        "category": "docs_usability",
                        "severity": "medium",
                        "message": "Rollback command should be easier to find.",
                        "evidence_refs": ["README.stable-handoff.md"],
                    }
                ],
                "accepted_findings": [
                    {
                        "id": "F001",
                        "category": "docs_usability",
                        "severity": "medium",
                        "message": "Move rollback summary closer to stable smoke.",
                        "evidence_refs": ["README.stable-handoff.md"],
                        "owner": "docs",
                        "action": "Tighten stable handoff rollback section.",
                        "validation_refs": ["python scripts/check_docs_index.py"],
                    }
                ],
                "rejected_findings": [],
            },
            {
                "round_id": "round-2",
                "evaluator_context": {
                    "fork_context": False,
                    "agent_id": "blind-agent-2",
                    "input_summary": "Updated README.stable-handoff.md plus stable smoke report",
                },
                "input_refs": [
                    "README.stable-handoff.md",
                    "runtime-state/stable-handoff/phase91-bash-stable-smoke.json",
                ],
                "blind_findings": [],
                "accepted_findings": [],
                "rejected_findings": [],
            },
        ],
        "score_summary": {
            "total_score": 91,
            "category_scores": {
                "route_workflow_skill_tool_correctness": 95,
                "evidence_grounding_and_artifact_quality": 90,
                "semantic_correctness": 90,
                "output_contract_and_chat_visible_markers": 90,
                "verification_command_relevance": 90,
                "safety_approval_and_mutation_boundary": 95,
                "diagnosability": 90,
            },
        },
        "convergence": {
            "status": "converged",
            "summary": "No critical/high findings and live proof remained green.",
            "evidence_refs": [
                "runtime-state/stable-handoff/phase91-bash-stable-smoke.json",
                "python -m pytest tests/regression/ -v",
            ],
        },
    }


def test_project_recursive_blind_testing_policy_passes(tmp_path: Path) -> None:
    report = validate(tmp_path)

    assert report["status"] == "passed"
    assert report["summary"]["failed_check_ids"] == []
    by_id = {item["id"]: item for item in report["checks"]}
    assert by_id["policy.contract"]["status"] == "passed"
    assert by_id["report.contract"]["status"] == "skipped"


def test_recursive_blind_testing_policy_rejects_unbounded_rounds(tmp_path: Path) -> None:
    policy = load_policy()
    policy["round_limits"]["max_rounds"] = 5  # type: ignore[index]
    policy_path = write_json(tmp_path / "policy.json", policy)

    report = validate(tmp_path, policy_path=policy_path)

    assert report["status"] == "failed"
    errors = report["checks"][0]["details"]["errors"]
    assert "round_limits.max_rounds must be an integer from 1 through 3" in errors


def test_recursive_blind_testing_policy_requires_no_context_evaluators(tmp_path: Path) -> None:
    policy = load_policy()
    policy["context_policy"]["fork_context"] = True  # type: ignore[index]
    policy_path = write_json(tmp_path / "policy.json", policy)

    report = validate(tmp_path, policy_path=policy_path)

    assert report["status"] == "failed"
    errors = report["checks"][0]["details"]["errors"]
    assert "context_policy.fork_context must be false" in errors


def test_recursive_blind_testing_policy_rejects_blind_pass_fail_authority(tmp_path: Path) -> None:
    policy = load_policy()
    policy["adjudication_policy"]["blind_evaluator_is_pass_fail_authority"] = True  # type: ignore[index]
    policy_path = write_json(tmp_path / "policy.json", policy)

    report = validate(tmp_path, policy_path=policy_path)

    assert report["status"] == "failed"
    errors = report["checks"][0]["details"]["errors"]
    assert "adjudication_policy.blind_evaluator_is_pass_fail_authority must be false" in errors


def test_recursive_blind_testing_policy_rejects_bad_score_rubric(tmp_path: Path) -> None:
    policy = load_policy()
    policy["score_rubric"]["dimensions"][0]["points"] = 19  # type: ignore[index]
    policy_path = write_json(tmp_path / "policy.json", policy)

    report = validate(tmp_path, policy_path=policy_path)

    assert report["status"] == "failed"
    errors = report["checks"][0]["details"]["errors"]
    assert "score_rubric.dimensions[route_workflow_skill_tool_correctness].points must be 20" in errors


def test_recursive_blind_testing_report_passes_contract(tmp_path: Path) -> None:
    report_path = write_json(tmp_path / "recursive-report.json", valid_recursive_report())

    report = validate(tmp_path, report_path=report_path)

    assert report["status"] == "passed"
    by_id = {item["id"]: item for item in report["checks"]}
    assert by_id["policy.contract"]["status"] == "passed"
    assert by_id["report.contract"]["status"] == "passed"


def test_recursive_blind_testing_report_rejects_context_contamination(tmp_path: Path) -> None:
    recursive_report = valid_recursive_report()
    recursive_report["rounds"][0]["evaluator_context"]["fork_context"] = True  # type: ignore[index]
    report_path = write_json(tmp_path / "recursive-report.json", recursive_report)

    report = validate(tmp_path, report_path=report_path)

    assert report["status"] == "failed"
    errors = report["checks"][1]["details"]["errors"]
    assert "rounds[0].evaluator_context.fork_context must be false" in errors


def test_recursive_blind_testing_report_rejects_accepted_finding_without_validation(tmp_path: Path) -> None:
    recursive_report = valid_recursive_report()
    recursive_report["rounds"][0]["accepted_findings"][0]["validation_refs"] = []  # type: ignore[index]
    report_path = write_json(tmp_path / "recursive-report.json", recursive_report)

    report = validate(tmp_path, report_path=report_path)

    assert report["status"] == "failed"
    errors = report["checks"][1]["details"]["errors"]
    assert any("validation_refs must be non-empty" in item for item in errors)


def test_recursive_blind_testing_report_rejects_unresolved_high_findings(tmp_path: Path) -> None:
    recursive_report = valid_recursive_report()
    recursive_report["rounds"][0]["blind_findings"].append(  # type: ignore[index]
        {
            "id": "F999",
            "category": "routing_miss",
            "severity": "high",
            "message": "Wrong workflow selected.",
            "evidence_refs": ["route-decision.json"],
        }
    )
    report_path = write_json(tmp_path / "recursive-report.json", recursive_report)

    report = validate(tmp_path, report_path=report_path)

    assert report["status"] == "failed"
    errors = report["checks"][1]["details"]["errors"]
    assert "critical/high blind findings must be accepted or rejected: ['F999']" in errors


def test_recursive_blind_testing_report_rejects_low_score_pass(tmp_path: Path) -> None:
    recursive_report = valid_recursive_report()
    recursive_report["score_summary"]["total_score"] = 84  # type: ignore[index]
    report_path = write_json(tmp_path / "recursive-report.json", recursive_report)

    report = validate(tmp_path, report_path=report_path)

    assert report["status"] == "failed"
    errors = report["checks"][1]["details"]["errors"]
    assert "score_summary.total_score must be at least acceptance_minimum=85 for passed reports" in errors


def test_recursive_blind_testing_report_rejects_round_limit_as_pass(tmp_path: Path) -> None:
    recursive_report = valid_recursive_report()
    recursive_report["convergence"]["status"] = "round_limit_exhausted"  # type: ignore[index]
    report_path = write_json(tmp_path / "recursive-report.json", recursive_report)

    report = validate(tmp_path, report_path=report_path)

    assert report["status"] == "failed"
    errors = report["checks"][1]["details"]["errors"]
    assert "passed recursive blind-testing reports require convergence.status=converged" in errors
