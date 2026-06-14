from __future__ import annotations

import copy
import hashlib
import subprocess
from pathlib import Path

from vllm_agent_gateway.acceptance.context_index_prototype import read_json_object, write_json
from vllm_agent_gateway.acceptance.external_tester_feedback_loop_from_clone import (
    ExternalTesterFeedbackLoopFromCloneConfig,
    validate_external_tester_feedback_loop_from_clone,
    validate_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "runtime" / "external_tester_feedback_loop_from_clone_policy.json"
CASES_PATH = REPO_ROOT / "runtime" / "external_tester_feedback_loop_from_clone_cases.json"


def policy() -> dict:
    return read_json_object(POLICY_PATH)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def write_target_run_artifacts(tmp_path: Path, run_id: str, prompt: str) -> Path:
    run_dir = tmp_path / "controller-artifacts" / "workflow-router" / run_id
    downstream_dir = run_dir / "code-investigation" / f"code-investigation-{run_id}"
    route_decision = {
        "kind": "workflow_router_decision",
        "run_id": run_id,
        "status": "ready",
        "selected_workflow": "code_investigation.plan",
        "selected_skills": ["request-triage", "code-explanation-summarizer"],
        "selected_tools": ["structure_index", "git_grep", "read_file"],
    }
    request = {
        "kind": "workflow_router_request",
        "run_id": run_id,
        "workflow": "workflow_router.plan",
        "user_request": prompt,
    }
    output_artifact = {
        "kind": "code_explanation",
        "status": "completed",
        "source_refs": ["core/stealth_order_manager.py"],
    }
    write_json(run_dir / "route-decision.json", route_decision)
    write_json(run_dir / "request.json", request)
    write_json(downstream_dir / "code-explanation.json", output_artifact)
    write_json(
        run_dir / "run-state.json",
        {
            "kind": "workflow_router_run_state",
            "run_id": run_id,
            "status": "completed",
            "artifacts": {
                "request": str(run_dir / "request.json"),
                "route_decision": str(run_dir / "route-decision.json"),
                "downstream_code_explanation": str(downstream_dir / "code-explanation.json"),
            },
        },
    )
    return run_dir


def case_report(
    tmp_path: Path,
    *,
    case_id: str,
    surface: str,
    target_root: str,
    prompt: str,
    feedback_run_id: str,
    classifications: list[str],
    decision_kind: str,
    decision_status: str,
    gap_class: str,
    validation_result: dict,
) -> dict:
    target_run_id = f"workflow-router-{case_id.lower()}"
    run_dir = write_target_run_artifacts(tmp_path, target_run_id, prompt)
    feedback_record = {
        "kind": "workflow_feedback_record",
        "status": "completed",
        "run_id": feedback_run_id,
        "target_run_id": target_run_id,
        "target_workflow": "workflow_router.plan",
        "target_root": target_root,
        "feedback": {"useful": ["ok"] if "useful" in classifications else [], "wrong": ["bad"] if "wrong" in classifications else [], "notes": "notes"},
        "feedback_context": {
            "target_run_found": True,
            "target_run_id": target_run_id,
            "target_workflow": "workflow_router.plan",
            "target_status": "completed",
            "target_root": target_root,
            "selected_workflow": "code_investigation.plan",
            "route_decision": str(run_dir / "route-decision.json"),
            "prompt_case": case_id,
        },
        "linked_run": {
            "found": True,
            "run_id": target_run_id,
            "workflow": "workflow_router.plan",
            "status": "completed",
            "artifact_keys": ["request", "route_decision", "downstream_code_explanation"],
        },
        "classifications": classifications,
        "governed_decision": {
            "kind": decision_kind,
            "decision_status": decision_status,
            "gap_class": gap_class,
            "target_run_id": target_run_id,
            "feedback_run_id": feedback_run_id,
            "target_workflow": "code_investigation.plan",
            "prompt_case_id": case_id,
            "mutation_policy": "controller_artifacts_only",
            "validation_result": validation_result,
        },
    }
    return {
        "case_id": case_id,
        "status": "passed",
        "surface": surface,
        "target_root": target_root,
        "target_run_id": target_run_id,
        "feedback_run_id": feedback_run_id,
        "feedback_record": feedback_record,
        "decision": feedback_record["governed_decision"],
        "prompt_hash": sha256_text(prompt),
        "errors": [],
    }


def live_report(tmp_path: Path) -> dict:
    positive_prompt = (
        "In /mnt/c/coinbase_testing_repo_frozen_tmp.github, explain what "
        "find_stealth_order_by_placed_order_id does in core/stealth_order_manager.py. "
        "Read only. Include key inputs, outputs, side effects, and tests."
    )
    defect_prompt = (
        "In /mnt/c/coinbase_testing_repo_frozen_tmp, diagnose why a placed_order_id stealth lookup answer "
        "might miss the likely root cause. Read only. Include evidence and uncertainty."
    )
    return {
        "kind": "founder_feedback_loop_live_report",
        "status": "passed",
        "config_root": "/tmp/agentic_agents_phase243_remote_clone",
        "source_git": {
            "branch": "codex/m14-release-clone-proof",
            "commit": "abc123",
            "remote_origin_url": "https://github.com/s-aws/vllm-agent-gateway.git",
            "status_short": "",
        },
        "cases": [
            case_report(
                tmp_path,
                case_id="FL243-001",
                surface="gateway",
                target_root="/mnt/c/coinbase_testing_repo_frozen_tmp.github",
                prompt=positive_prompt,
                feedback_run_id="workflow-feedback-fl243-001",
                classifications=["useful"],
                decision_kind="rejected_finding",
                decision_status="rejected",
                gap_class="none",
                validation_result={"status": "passed", "reason": "useful-only feedback does not create repair work"},
            ),
            case_report(
                tmp_path,
                case_id="FL243-002",
                surface="anythingllm",
                target_root="/mnt/c/coinbase_testing_repo_frozen_tmp",
                prompt=defect_prompt,
                feedback_run_id="workflow-feedback-fl243-002",
                classifications=["wrong"],
                decision_kind="repair_followup",
                decision_status="accepted",
                gap_class="model_capability",
                validation_result={"status": "recorded_pending_eval", "required_gate": "eval_repair_loop"},
            ),
        ],
        "mutation_proof": {
            "runtime_changed_files": [],
            "target_changed_files": {},
            "target_git_changed": {},
        },
    }


def write_policy_and_report(tmp_path: Path, policy_value: dict, report_value: dict) -> Path:
    config_root = tmp_path / "config-root"
    config_root.mkdir()
    (config_root / ".gitignore").write_text("runtime-state/\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(config_root), "init"], check=True, stdout=subprocess.DEVNULL)
    path = config_root / "policy.json"
    live_path = config_root / "runtime-state" / "external-tester-feedback-loop-from-clone" / "phase243" / "live.json"
    policy_value["cases_path"] = str(CASES_PATH)
    policy_value["live_feedback_report_path"] = "runtime-state/external-tester-feedback-loop-from-clone/phase243/live.json"
    write_json(path, policy_value)
    write_json(live_path, report_value)
    return path


def config_root_for_policy(policy_path: Path) -> Path:
    return policy_path.parent


def test_phase243_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase243_static_allows_missing_live_artifacts(tmp_path: Path) -> None:
    policy_path = write_policy_and_report(tmp_path, copy.deepcopy(policy()), {})
    (config_root_for_policy(policy_path) / "runtime-state").mkdir(exist_ok=True)
    (config_root_for_policy(policy_path) / "runtime-state" / "external-tester-feedback-loop-from-clone" / "phase243" / "live.json").unlink()

    report = validate_external_tester_feedback_loop_from_clone(
        ExternalTesterFeedbackLoopFromCloneConfig(
            config_root=config_root_for_policy(policy_path),
            policy_path=policy_path,
            output_path="runtime-state/external-tester-feedback-loop-from-clone/phase243/report.json",
            markdown_output_path="runtime-state/external-tester-feedback-loop-from-clone/phase243/report.md",
            require_live_artifacts=False,
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["phase244_ready"] is False


def test_phase243_live_report_passes(tmp_path: Path) -> None:
    policy_path = write_policy_and_report(tmp_path, copy.deepcopy(policy()), live_report(tmp_path))

    report = validate_external_tester_feedback_loop_from_clone(
        ExternalTesterFeedbackLoopFromCloneConfig(
            config_root=config_root_for_policy(policy_path),
            policy_path=policy_path,
            output_path="runtime-state/external-tester-feedback-loop-from-clone/phase243/report.json",
            markdown_output_path="runtime-state/external-tester-feedback-loop-from-clone/phase243/report.md",
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["phase244_ready"] is True
    assert report["summary"]["trace_count"] == 2
    assert all(item["prompt_hash"] for item in report["live_report"]["traces"])
    assert all(item["output_artifact_sha256"] for item in report["live_report"]["traces"])


def test_phase243_rejects_active_workspace_live_report(tmp_path: Path) -> None:
    report_value = live_report(tmp_path)
    report_value["config_root"] = "/mnt/c/agentic_agents"
    policy_path = write_policy_and_report(tmp_path, copy.deepcopy(policy()), report_value)

    report = validate_external_tester_feedback_loop_from_clone(
        ExternalTesterFeedbackLoopFromCloneConfig(
            config_root=config_root_for_policy(policy_path),
            policy_path=policy_path,
            output_path="runtime-state/external-tester-feedback-loop-from-clone/phase243/report.json",
            markdown_output_path="runtime-state/external-tester-feedback-loop-from-clone/phase243/report.md",
        )
    )

    assert report["status"] == "failed"
    assert any(item["id"] == "live_report.config_root" for item in report["validation_errors"])


def test_phase243_rejects_missing_route_decision(tmp_path: Path) -> None:
    report_value = live_report(tmp_path)
    report_value["cases"][0]["feedback_record"]["feedback_context"]["route_decision"] = str(tmp_path / "missing.json")
    policy_path = write_policy_and_report(tmp_path, copy.deepcopy(policy()), report_value)

    report = validate_external_tester_feedback_loop_from_clone(
        ExternalTesterFeedbackLoopFromCloneConfig(
            config_root=config_root_for_policy(policy_path),
            policy_path=policy_path,
            output_path="runtime-state/external-tester-feedback-loop-from-clone/phase243/report.json",
            markdown_output_path="runtime-state/external-tester-feedback-loop-from-clone/phase243/report.md",
        )
    )

    assert report["status"] == "failed"
    assert any(item["id"] == "cases.FL243-001.route_decision" for item in report["validation_errors"])


def test_phase243_rejects_accepted_repair_without_rerun_contract(tmp_path: Path) -> None:
    mutated = copy.deepcopy(policy())
    mutated["accepted_finding_rerun_cases"] = []
    policy_path = write_policy_and_report(tmp_path, mutated, live_report(tmp_path))

    report = validate_external_tester_feedback_loop_from_clone(
        ExternalTesterFeedbackLoopFromCloneConfig(
            config_root=config_root_for_policy(policy_path),
            policy_path=policy_path,
            output_path="runtime-state/external-tester-feedback-loop-from-clone/phase243/report.json",
            markdown_output_path="runtime-state/external-tester-feedback-loop-from-clone/phase243/report.md",
        )
    )

    assert report["status"] == "failed"
    assert any("accepted_finding_rerun_cases" in item["id"] for item in report["validation_errors"])
