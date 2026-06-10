from __future__ import annotations

import http.client
import json
import threading
import time
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.task_decomposition_quality import (
    build_phase113_recursive_blind_testing_report,
    build_phase114_recursive_blind_testing_report,
    build_phase115_recursive_blind_testing_report,
    load_json_object,
    evaluate_task_decomposition_plan,
    validate_phase113_case_catalog,
    validate_phase114_case_catalog,
    validate_phase115_case_catalog,
    validate_phase119_case_catalog,
)
from vllm_agent_gateway.acceptance.recursive_blind_testing import validate_recursive_report
from vllm_agent_gateway.controller_service.server import ControllerServiceConfig, create_server
from vllm_agent_gateway.controllers.workflow_router.plan import workflow_kind_for_request


REPO_ROOT = Path(__file__).resolve().parents[2]


class RunningControllerService:
    def __init__(self, config: ControllerServiceConfig):
        self.server = create_server(config)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> "RunningControllerService":
        self.thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    @property
    def base_url(self) -> tuple[str, int]:
        host, port = self.server.server_address
        return str(host), int(port)


def request_json(
    host: str,
    port: int,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    last_error: OSError | None = None
    for attempt in range(4):
        connection = http.client.HTTPConnection(host, port, timeout=60)
        try:
            connection.request(method, path, body=body, headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            parsed = json.loads(response.read().decode("utf-8"))
            return response.status, parsed
        except OSError as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(0.2)
        finally:
            connection.close()
    assert last_error is not None
    raise last_error


def make_target_repo(tmp_path: Path) -> Path:
    root = tmp_path / "target-repo"
    (root / "core").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "core" / "stealth_order_manager.py").write_text(
        "def find_stealth_order_by_placed_order_id(placed_order_id):\n"
        "    return placed_order_id\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_stealth_order_manager.py").write_text(
        "def test_find_stealth_order_by_placed_order_id():\n"
        "    assert True\n",
        encoding="utf-8",
    )
    return root


def controller_config(tmp_path: Path, target_root: Path) -> ControllerServiceConfig:
    return ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(target_root,),
        port=0,
    )


def decompose_payload(target_root: Path, user_request: str | None = None) -> dict[str, Any]:
    return {
        "workflow": "task.decompose",
        "schema_version": 1,
        "target_root": str(target_root),
        "user_request": user_request
        or (
            "Decompose this multi-step task into work packages with dependencies, approval gates, "
            "and verification strategy: add a focused unit test for "
            "find_stealth_order_by_placed_order_id after investigating related tests."
        ),
    }


def chat_payload(target_root: Path, content: str, *, json_output: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": "agentic-workflow-router",
        "messages": [{"role": "user", "content": content}],
    }
    if json_output:
        payload["response_format"] = {"type": "json_object"}
    return payload


def load_artifact(response: dict[str, Any], key: str) -> dict[str, Any]:
    artifact_path = response["artifacts"][key]
    return json.loads(Path(artifact_path).read_text(encoding="utf-8"))


def registered_ids(catalog: str, item_key: str) -> set[str]:
    manifest = json.loads((REPO_ROOT / "runtime" / catalog).read_text(encoding="utf-8"))
    return {item["id"] for item in manifest[item_key]}


def non_null_workflow_ids(plan: dict[str, Any]) -> set[str]:
    return {
        item["workflow_id"]
        for item in plan.get("work_packages", [])
        if isinstance(item, dict) and isinstance(item.get("workflow_id"), str)
    }


def normalized_plan(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": plan["status"],
        "work_package_schema_version": plan["work_package_schema_version"],
        "prompt_family": plan["prompt_family"],
        "risk_level": plan["risk_level"],
        "work_packages": plan["work_packages"],
        "dependency_edges": plan["dependency_edges"],
        "selected_workflow_ids": plan["selected_workflow_ids"],
        "selected_skill_ids": plan["selected_skill_ids"],
        "selected_tool_ids": plan["selected_tool_ids"],
        "approval_gates": plan["approval_gates"],
        "verification_strategy": plan["verification_strategy"],
        "uncertainty": plan["uncertainty"],
        "next_action": plan["next_action"],
    }


def package_by_id(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        item["id"]: item
        for item in plan.get("work_packages", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }


def assert_registered_references(plan: dict[str, Any]) -> None:
    workflow_ids = registered_ids("workflows.json", "workflows")
    skill_ids = registered_ids("skills.json", "skills")
    tool_ids = registered_ids("tools.json", "tools")
    assert non_null_workflow_ids(plan) <= workflow_ids
    for item in plan["work_packages"]:
        assert set(item.get("selected_skills", [])) <= skill_ids
        assert set(item.get("selected_tools", [])) <= tool_ids


def build_valid_plan(tmp_path: Path, target_root: Path) -> dict[str, Any]:
    config = controller_config(tmp_path, target_root)
    with RunningControllerService(config) as service:
        status, body = request_json(
            *service.base_url,
            "POST",
            "/v1/controller/task-decompositions",
            decompose_payload(target_root),
        )
    assert status == 200
    return load_artifact(body, "task_decomposition")


def assert_phase113_work_package_contract(plan: dict[str, Any]) -> None:
    assert plan["work_package_schema_version"] == 3
    assert plan["tenet_contract"]["phase"] == 113
    assert plan["tenet_contract"]["tenet_ids"] == ["T01", "T02", "T03"]
    assert [item["id"] for item in plan["work_packages"]] == ["WP1", "GATE2", "WP3", "WP4", "STOP5"]
    assert plan["dependency_edges"] == [
        {"from": "WP1", "to": "GATE2"},
        {"from": "GATE2", "to": "WP3"},
        {"from": "WP3", "to": "WP4"},
        {"from": "WP4", "to": "STOP5"},
    ]
    packages = package_by_id(plan)
    assert packages["WP1"]["stage"] == "investigation"
    assert packages["GATE2"]["stage"] == "prep_approval_gate"
    assert packages["GATE2"]["approval_gate"]["scope"] == "packet_design_only"
    assert packages["WP3"]["stage"] == "implementation_prep"
    assert packages["WP3"]["workflow_id"] == "execution_planning.plan"
    assert packages["WP4"]["stage"] == "verification"
    assert packages["STOP5"]["stage"] == "terminal_stop"
    assert packages["STOP5"]["approval_gate"]["scope"] == "repository_mutation"
    for item in plan["work_packages"]:
        assert isinstance(item["dependency_contract"], dict)
        assert isinstance(item["entry_conditions"], list) and item["entry_conditions"]
        assert isinstance(item["exit_criteria"], list) and item["exit_criteria"]
        assert isinstance(item["acceptance_criteria"], list) and item["acceptance_criteria"]
        for criterion in item["acceptance_criteria"]:
            assert criterion["id"].startswith(f"AC-{item['id']}-")
            assert isinstance(criterion["evidence_required"], list) and criterion["evidence_required"]
            assert criterion["requires_source_mutation"] is False
            assert set(criterion["objectivity"]) == {
                "observable_outcome",
                "evidence_source",
                "pass_fail_rule",
            }
        assert item["scope_boundary"]["independently_reviewable"] is True
        assert item["scope_boundary"]["estimated_cycle"] == "short"
        assert item["scope_boundary"]["review_boundary"]
        assert item["scope_boundary"]["not_in_scope"]
        assert isinstance(item["stop_conditions"], list) and item["stop_conditions"]
        assert isinstance(item["verification"], dict)
        assert item["verification"]["status"]
    assert [gate["package_id"] for gate in plan["approval_gates"]] == ["GATE2", "STOP5"]
    assert {gate["approval_scope"] for gate in plan["approval_gates"]} == {"packet_design_only", "repository_mutation"}


def assert_phase114_requirements_translation_contract(
    plan: dict[str, Any],
    *,
    revised: bool = False,
    full_artifact: bool = True,
) -> None:
    assert plan["prompt_family"] == "requirements_translation"
    assert plan["tenet_contract"]["phase"] == 114
    assert plan["tenet_contract"]["tenet_ids"] == ["T04", "T05"]
    contract = plan["requirements_translation"]
    assert contract["kind"] == "requirements_translation_contract"
    assert contract["phase"] == 114
    assert contract["tenet_ids"] == ["T04", "T05"]
    assert contract["source_business_requirements"][0]["id"] == "BR1"
    technical = contract["technical_requirements"]
    assert [item["id"] for item in technical] == ["TR1", "TR2"]
    assert all(item["derived_from"] == ["BR1"] for item in technical)
    assert all(item["complexity_guardrail"] for item in technical)
    assert all(item["domain_terms"] for item in technical)
    assert all(item["observable_outcome"] for item in technical)
    combined_technical = " ".join(
        str(value)
        for item in technical
        for value in [item["requirement"], item["complexity_guardrail"], item["observable_outcome"]]
    ).lower()
    business_text = contract["source_business_requirements"][0]["text"].lower()
    assert any(term.lower() in business_text and term.lower() in combined_technical for term in technical[0]["domain_terms"])
    assert [item["id"] for item in contract["explicit_assumptions"]] == ["A1", "A2"]
    assert [item["id"] for item in contract["rejected_assumptions"]] == ["RA1", "RA2"]
    estimate = contract["effort_estimate"]
    assert estimate["estimate_band"] in {"small", "medium"}
    assert estimate["confidence"] in {"low", "medium", "high"}
    assert estimate["assumption_ids"] == ["A1", "A2"]
    assert estimate["scope_drivers"]
    assert estimate["revision_triggers"]
    revision = contract["estimate_revision"]
    assert revision["status"] == ("revised" if revised else "not_requested")
    assert revision["requires_reapproval_before_implementation_prep"] is revised
    if full_artifact:
        assert evaluate_task_decomposition_plan(plan)["status"] == "passed"


def assert_phase115_incremental_implementation_contract(plan: dict[str, Any]) -> None:
    assert plan["prompt_family"] == "incremental_implementation_plan"
    assert plan["tenet_contract"]["phase"] == 115
    assert plan["tenet_contract"]["tenet_ids"] == ["T06", "T07"]
    contract = plan["incremental_implementation_plan"]
    assert contract["kind"] == "incremental_implementation_plan_contract"
    assert contract["phase"] == 115
    assert contract["tenet_ids"] == ["T06", "T07"]
    assert contract["source_request"]["domain_terms"]
    changesets = contract["changesets"]
    assert [item["id"] for item in changesets] == ["CS1", "CS2", "CS3"]
    assert {item["change_type"] for item in changesets} >= {"implementation", "test"}
    for item in changesets:
        assert item["functional_outcome"]
        assert item["isolation_boundary"]["one_behavior"] is True
        assert item["isolation_boundary"]["unrelated_changes_policy"] == "reject"
        assert item["verification_commands"]
        assert "python -m pytest -q" not in item["verification_commands"]
        assert item["acceptance_checks"]
        assert item["commit_message"]["subject"]
        assert item["commit_message"]["body"]
        assert item["commit_message"]["rationale"]
        assert item["traceability"]["proof_artifacts"]
    version_control = contract["version_control_plan"]
    assert version_control["commit_order"] == ["CS1", "CS2", "CS3"]
    assert version_control["branch_name"].startswith("agent/")
    assert version_control["traceability_artifacts"]
    assert version_control["pre_commit_checks"]
    assert contract["source_apply_policy"]["status"] == "blocked_in_task_decompose"
    assert evaluate_task_decomposition_plan(plan)["status"] == "passed"


def assert_phase119_delivery_mentorship_contract(plan: dict[str, Any]) -> None:
    assert plan["prompt_family"] == "delivery_mentorship"
    assert plan["tenet_contract"]["phase"] == 119
    assert plan["tenet_contract"]["tenet_ids"] == ["T19", "T20"]
    contract = plan["delivery_mentorship"]
    assert contract["kind"] == "delivery_mentorship_contract"
    assert contract["phase"] == 119
    assert contract["tenet_ids"] == ["T19", "T20"]
    assert contract["source_request"]["domain_terms"]
    stages = [item["stage"] for item in contract["delivery_sequence"]]
    assert stages == [
        "requirement_intake",
        "task_decomposition",
        "implementation_planning",
        "verification_strategy",
        "review_feedback",
        "deployment_readiness",
    ]
    tiers = {item["tier"] for item in contract["testing_strategy"]["tiers"]}
    assert {"unit", "integration", "regression", "live_or_manual"} <= tiers
    assert len(contract["debugging_methodology"]) >= 3
    assert any("one code path" in item.lower() or "duplicate" in item.lower() for item in contract["code_quality_practices"])
    readiness = " ".join(contract["deployment_readiness"]["checks"]).lower()
    assert "rollback" in readiness
    assert "observability" in readiness
    assert "live" in readiness
    assert contract["source_apply_policy"]["status"] == "blocked_in_task_decompose"
    assert contract["source_apply_policy"]["deployment_status"] == "not_deployed_by_this_workflow"
    assert evaluate_task_decomposition_plan(plan)["status"] == "passed"


def test_task_decomposition_endpoint_returns_registered_read_only_plan(tmp_path: Path) -> None:
    target_root = make_target_repo(tmp_path)
    config = controller_config(tmp_path, target_root)
    with RunningControllerService(config) as service:
        status, body = request_json(
            *service.base_url,
            "POST",
            "/v1/controller/task-decompositions",
            decompose_payload(target_root),
        )

    assert status == 200
    assert body["workflow"] == "task.decompose"
    assert body["status"] == "completed"
    assert body["summary"]["decomposition_status"] == "ready"
    assert body["summary"]["prompt_family"] == "feature_or_small_change"
    assert body["summary"]["target_repository_changed"] is False
    assert body["summary"]["runtime_registry_changed"] is False
    assert set(body["artifacts"]) == {"request", "task_decomposition", "run_state"}
    plan = load_artifact(body, "task_decomposition")
    assert plan["status"] == "ready"
    assert "code_investigation.plan" in plan["selected_workflow_ids"]
    assert "execution_planning.plan" in plan["selected_workflow_ids"]
    assert "refactor.single_path" not in plan["selected_workflow_ids"]
    assert any(item["id"] == "GATE2" and item["workflow_id"] is None for item in plan["work_packages"])
    assert any(item["id"] == "STOP5" and item["workflow_id"] is None for item in plan["work_packages"])
    assert_phase113_work_package_contract(plan)
    assert evaluate_task_decomposition_plan(plan)["status"] == "passed"
    assert plan["target_repository_changed"] is False
    assert plan["runtime_registry_changed"] is False
    assert_registered_references(plan)


def test_task_decomposition_is_stable_across_repeated_runs(tmp_path: Path) -> None:
    target_root = make_target_repo(tmp_path)
    config = controller_config(tmp_path, target_root)
    with RunningControllerService(config) as service:
        first_status, first_body = request_json(
            *service.base_url,
            "POST",
            "/v1/controller/task-decompositions",
            decompose_payload(target_root),
        )
        second_status, second_body = request_json(
            *service.base_url,
            "POST",
            "/v1/controller/task-decompositions",
            decompose_payload(target_root),
        )

    assert first_status == 200
    assert second_status == 200
    assert normalized_plan(load_artifact(first_body, "task_decomposition")) == normalized_plan(
        load_artifact(second_body, "task_decomposition")
    )


def test_task_decomposition_ambiguous_task_returns_clarification_without_packets(tmp_path: Path) -> None:
    target_root = make_target_repo(tmp_path)
    config = controller_config(tmp_path, target_root)
    with RunningControllerService(config) as service:
        status, body = request_json(
            *service.base_url,
            "POST",
            "/v1/controller/task-decompositions",
            decompose_payload(target_root, "fix it"),
        )

    assert status == 200
    assert body["summary"]["decomposition_status"] == "needs_clarification"
    assert body["summary"]["next_action"] == "ask_blocking_question"
    assert body["summary"]["package_count"] == 0
    assert not any("packet" in key for key in body["artifacts"])
    plan = load_artifact(body, "task_decomposition")
    assert plan["work_packages"] == []
    assert plan["tenet_contract"]["status"] == "blocked_until_clarified"
    assert evaluate_task_decomposition_plan(plan)["status"] == "passed"
    assert plan["blockers"][0]["reason"] == "ambiguous_task"
    assert plan["target_repository_changed"] is False
    assert plan["runtime_registry_changed"] is False


def test_task_decomposition_oversized_task_returns_further_decomposition_guidance(tmp_path: Path) -> None:
    target_root = make_target_repo(tmp_path)
    config = controller_config(tmp_path, target_root)
    request = (
        "Break down this task into independently reviewable steps with dependencies and acceptance criteria: "
        "rewrite the whole project so every module has better architecture."
    )
    with RunningControllerService(config) as service:
        status, body = request_json(
            *service.base_url,
            "POST",
            "/v1/controller/task-decompositions",
            decompose_payload(target_root, request),
        )

    assert status == 200
    assert body["summary"]["decomposition_status"] == "needs_clarification"
    assert body["summary"]["prompt_family"] == "oversized"
    plan = load_artifact(body, "task_decomposition")
    assert plan["work_packages"] == []
    assert plan["blockers"][0]["reason"] == "oversized_task"
    assert plan["decomposition_guidance"]
    assert evaluate_task_decomposition_plan(plan)["status"] == "passed"
    assert not any("packet" in key for key in body["artifacts"])


def test_task_decomposition_defers_advanced_single_path_refactor(tmp_path: Path) -> None:
    target_root = make_target_repo(tmp_path)
    config = controller_config(tmp_path, target_root)
    request = (
        "Decompose this multi-step task into work packages with dependencies, approval gates, "
        "and verification strategy: refactor the placed_order_id stealth lookup so there is one code path."
    )
    with RunningControllerService(config) as service:
        status, body = request_json(
            *service.base_url,
            "POST",
            "/v1/controller/task-decompositions",
            decompose_payload(target_root, request),
        )

    assert status == 200
    assert body["summary"]["decomposition_status"] == "blocked"
    assert body["summary"]["prompt_family"] == "advanced_refactor_deferred"
    assert body["summary"]["next_action"] == "none"
    plan = load_artifact(body, "task_decomposition")
    assert plan["status"] == "blocked"
    assert plan["deferred_to_phase"] == 105
    assert plan["selected_workflow_ids"] == []
    assert [item["id"] for item in plan["work_packages"]] == ["DEFER1"]
    assert plan["work_packages"][0]["mutation_policy"] == "unsupported_deferred_until_phase_105"
    assert plan["work_packages"][0]["acceptance_criteria"][0]["id"] == "AC-DEFER1-1"
    assert plan["work_packages"][0]["stop_conditions"][0]["code"] == "phase_105_not_ready"
    assert evaluate_task_decomposition_plan(plan)["status"] == "passed"
    assert not any("packet" in key for key in body["artifacts"])


def test_workflow_router_chat_task_decomposition_returns_inline_format_a(tmp_path: Path) -> None:
    target_root = make_target_repo(tmp_path)
    config = controller_config(tmp_path, target_root)
    prompt = (
        f"In {target_root}, decompose this multi-step task into work packages with dependencies, "
        "approval gates, and verification strategy: add a focused unit test for "
        "find_stealth_order_by_placed_order_id after investigating related tests. Read only."
    )
    with RunningControllerService(config) as service:
        status, body = request_json(
            *service.base_url,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            chat_payload(target_root, prompt),
        )

    assert status == 200
    content = body["choices"][0]["message"]["content"]
    assert "Result:" in content
    assert "- Selected workflow: task.decompose" in content
    assert "Task Decomposition:" in content
    assert "- Work-package schema: 3" in content
    assert "- Work packages:" in content
    assert "- Acceptance criteria:" in content
    assert "- Dependencies:" in content
    assert "- Approval gates:" in content
    assert "- Stop conditions:" in content
    assert "- Package verification:" in content
    assert "- Uncertainty:" in content
    assert "- Verification:" in content
    assert "- Source mutation: False" in content
    compact = body["agentic_controller_response"]
    assert compact["workflow"] == "workflow_router.plan"
    assert compact["summary"]["selected_workflow"] == "task.decompose"
    assert compact["summary"]["downstream_workflow"] == "task.decompose"
    assert "downstream_task_decomposition" in compact["artifacts"]
    assert not any("packet" in key for key in compact["artifacts"])


def test_workflow_router_chat_task_decomposition_json_contract(tmp_path: Path) -> None:
    target_root = make_target_repo(tmp_path)
    config = controller_config(tmp_path, target_root)
    prompt = (
        f"In {target_root}, decompose this multi-step task into work packages with dependencies, "
        "approval gates, and verification strategy: add a focused unit test for "
        "find_stealth_order_by_placed_order_id after investigating related tests. Return JSON."
    )
    with RunningControllerService(config) as service:
        status, body = request_json(
            *service.base_url,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            chat_payload(target_root, prompt, json_output=True),
        )

    assert status == 200
    parsed = json.loads(body["choices"][0]["message"]["content"])
    assert parsed["output_format"] == "json"
    assert parsed["chat_contract"]["selected_workflow"] == "task.decompose"
    assert parsed["chat_contract"]["next_action"] == "none"
    assert parsed["summary"]["selected_workflow"] == "task.decompose"
    assert parsed["summary"]["downstream_workflow"] == "task.decompose"
    assert "downstream_task_decomposition" in parsed["artifacts"]
    contract = parsed["task_decomposition_contract"]
    assert contract["work_package_schema_version"] == 3
    assert contract["tenet_contract"]["phase"] == 113
    assert [item["id"] for item in contract["work_packages"]] == ["WP1", "GATE2", "WP3", "WP4", "STOP5"]
    assert contract["work_packages"][0]["acceptance_criteria"][0]["id"] == "AC-WP1-1"
    assert contract["work_packages"][0]["scope_boundary"]["independently_reviewable"] is True
    assert contract["approval_gates"][0]["package_id"] == "GATE2"


def test_workflow_router_chat_general_greeting_without_target_returns_guidance(tmp_path: Path) -> None:
    target_root = make_target_repo(tmp_path)
    config = controller_config(tmp_path, target_root)
    with RunningControllerService(config) as service:
        status, body = request_json(
            *service.base_url,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            {"model": "agentic-workflow-router", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert status == 200
    content = body["choices"][0]["message"]["content"]
    assert "general_chat_no_target" in content
    assert "include an allowed target_root path" in content
    assert body["agentic_controller_response"]["summary"]["selected_workflow"] == "none"


def test_workflow_router_chat_general_greeting_with_ui_tracking_tag_returns_guidance(tmp_path: Path) -> None:
    target_root = make_target_repo(tmp_path)
    config = controller_config(tmp_path, target_root)
    with RunningControllerService(config) as service:
        status, body = request_json(
            *service.base_url,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [{"role": "user", "content": "hi Tracking tag: phase167-ui-e2e-test"}],
            },
        )

    assert status == 200
    content = body["choices"][0]["message"]["content"]
    assert "general_chat_no_target" in content
    assert "Selected workflow: none" in content
    assert "include an allowed target_root path" in content
    assert body["agentic_controller_response"]["summary"]["selected_workflow"] == "none"


def test_workflow_router_chat_coding_prompt_without_target_returns_guidance(tmp_path: Path) -> None:
    target_root = make_target_repo(tmp_path)
    config = controller_config(tmp_path, target_root)
    prompt = "Explain what find_stealth_order_by_placed_order_id does."
    with RunningControllerService(config) as service:
        status, body = request_json(
            *service.base_url,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            {"model": "agentic-workflow-router", "messages": [{"role": "user", "content": prompt}]},
        )

    assert status == 200
    content = body["choices"][0]["message"]["content"]
    assert "missing_target_root_for_coding_request" in content
    assert "Selected workflow: none" in content
    assert "I did not start a repository workflow" in content
    assert body["agentic_controller_response"]["summary"]["selected_workflow"] == "none"


def test_task_decomposition_translates_business_requirement_with_estimate(tmp_path: Path) -> None:
    target_root = make_target_repo(tmp_path)
    config = controller_config(tmp_path, target_root)
    request = (
        "Translate this business requirement into technical requirements and estimate effort: "
        "users need the stealth order lookup answer to say whether placed_order_id evidence was found."
    )
    with RunningControllerService(config) as service:
        status, body = request_json(
            *service.base_url,
            "POST",
            "/v1/controller/task-decompositions",
            decompose_payload(target_root, request),
        )

    assert status == 200
    assert body["summary"]["prompt_family"] == "requirements_translation"
    assert body["summary"]["requirements_translation_status"] == "ready_for_review"
    assert body["summary"]["effort_estimate_band"] == "small"
    plan = load_artifact(body, "task_decomposition")
    assert [item["id"] for item in plan["work_packages"]] == ["WP1", "GATE2", "WP3", "WP4", "STOP5"]
    assert [gate["package_id"] for gate in plan["approval_gates"]] == ["GATE2", "STOP5"]
    assert_phase114_requirements_translation_contract(plan)
    assert plan["target_repository_changed"] is False
    assert plan["runtime_registry_changed"] is False


def test_task_decomposition_revises_estimate_when_scope_changes(tmp_path: Path) -> None:
    target_root = make_target_repo(tmp_path)
    config = controller_config(tmp_path, target_root)
    request = (
        "Translate this business requirement into technical requirements and revise estimate because scope changed: "
        "users need the lookup answer to include placed_order_id evidence and now also include a documentation note."
    )
    with RunningControllerService(config) as service:
        status, body = request_json(
            *service.base_url,
            "POST",
            "/v1/controller/task-decompositions",
            decompose_payload(target_root, request),
        )

    assert status == 200
    plan = load_artifact(body, "task_decomposition")
    assert_phase114_requirements_translation_contract(plan, revised=True)
    technical_text = json.dumps(plan["requirements_translation"]["technical_requirements"], ensure_ascii=True).lower()
    assert "documentation_note" in technical_text
    estimate = plan["requirements_translation"]["effort_estimate"]
    assert estimate["estimate_band"] == "medium"
    assert estimate["confidence"] == "low"


def test_requirements_translation_preserves_non_coinbase_business_terms(tmp_path: Path) -> None:
    target_root = make_target_repo(tmp_path)
    config = controller_config(tmp_path, target_root)
    request = (
        "Translate this business requirement into technical requirements and estimate effort: "
        "the create-order response should show resolved order status. Return the answer in the default format."
    )
    with RunningControllerService(config) as service:
        status, body = request_json(
            *service.base_url,
            "POST",
            "/v1/controller/task-decompositions",
            decompose_payload(target_root, request),
        )

    assert status == 200
    plan = load_artifact(body, "task_decomposition")
    contract = plan["requirements_translation"]
    business_text = contract["source_business_requirements"][0]["text"]
    assert "Return the answer" not in business_text
    technical_text = json.dumps(contract["technical_requirements"], ensure_ascii=True).lower()
    assert "resolved order status" in technical_text
    assert "return" not in contract["technical_requirements"][0]["domain_terms"]
    assert "default" not in contract["technical_requirements"][0]["domain_terms"]
    assert evaluate_task_decomposition_plan(plan)["status"] == "passed"


def test_requirements_translation_preserves_revised_scope_note_terms(tmp_path: Path) -> None:
    target_root = make_target_repo(tmp_path)
    config = controller_config(tmp_path, target_root)
    request = (
        "Translate this business requirement into technical requirements and revise estimate because scope changed: "
        "the create-order response should show resolved order status and now also include a requirement note."
    )
    with RunningControllerService(config) as service:
        status, body = request_json(
            *service.base_url,
            "POST",
            "/v1/controller/task-decompositions",
            decompose_payload(target_root, request),
        )

    assert status == 200
    plan = load_artifact(body, "task_decomposition")
    contract = plan["requirements_translation"]
    for item in contract["technical_requirements"]:
        assert "requirement_note" in item["domain_terms"]
        assert "requirement_note" in item["requirement"].lower()
        assert "requirement_note" in item["observable_outcome"].lower()
    assert evaluate_task_decomposition_plan(plan)["status"] == "passed"


def test_workflow_router_routes_requirements_translation_to_task_decompose() -> None:
    prompt = (
        "In /tmp/example, translate this business requirement into technical requirements and estimate effort: "
        "show users whether an order lookup found matching evidence."
    )

    workflow_id, reason, evidence = workflow_kind_for_request(prompt)

    assert workflow_id == "task.decompose"
    assert reason == "ready"
    assert any(item.get("rule") == "task_decomposition_terms" for item in evidence)


def test_workflow_router_chat_requirements_translation_returns_inline_format_a(tmp_path: Path) -> None:
    target_root = make_target_repo(tmp_path)
    config = controller_config(tmp_path, target_root)
    prompt = (
        f"In {target_root}, translate this business requirement into technical requirements and estimate effort: "
        "users need the stealth order lookup answer to say whether placed_order_id evidence was found."
    )
    with RunningControllerService(config) as service:
        status, body = request_json(
            *service.base_url,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            chat_payload(target_root, prompt),
        )

    assert status == 200
    content = body["choices"][0]["message"]["content"]
    assert "- Selected workflow: task.decompose" in content
    assert "Task Decomposition:" in content
    assert "Requirements Translation:" in content
    assert "- Business requirements:" in content
    assert "- Technical requirements:" in content
    assert "- Explicit assumptions:" in content
    assert "- Rejected assumptions:" in content
    assert "- Effort estimate:" in content
    assert "- Revision triggers:" in content


def test_workflow_router_chat_requirements_translation_json_contract(tmp_path: Path) -> None:
    target_root = make_target_repo(tmp_path)
    config = controller_config(tmp_path, target_root)
    prompt = (
        f"In {target_root}, translate this business requirement into technical requirements and estimate effort: "
        "users need the stealth order lookup answer to say whether placed_order_id evidence was found. Return JSON."
    )
    with RunningControllerService(config) as service:
        status, body = request_json(
            *service.base_url,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            chat_payload(target_root, prompt, json_output=True),
        )

    assert status == 200
    parsed = json.loads(body["choices"][0]["message"]["content"])
    contract = parsed["task_decomposition_contract"]
    assert contract["prompt_family"] == "requirements_translation"
    assert_phase114_requirements_translation_contract(contract, full_artifact=False)


def test_task_decomposition_plans_incremental_implementation_changesets(tmp_path: Path) -> None:
    target_root = make_target_repo(tmp_path)
    config = controller_config(tmp_path, target_root)
    request = (
        "Create an incremental implementation plan for adding a requirement note to the create-order response. "
        "Include isolated changesets, verification commands, and meaningful commit messages. Do not change files."
    )
    with RunningControllerService(config) as service:
        status, body = request_json(
            *service.base_url,
            "POST",
            "/v1/controller/task-decompositions",
            decompose_payload(target_root, request),
        )

    assert status == 200
    assert body["summary"]["prompt_family"] == "incremental_implementation_plan"
    assert body["summary"]["incremental_plan_status"] == "ready_for_review"
    assert body["summary"]["changeset_count"] == 3
    plan = load_artifact(body, "task_decomposition")
    assert_phase115_incremental_implementation_contract(plan)
    technical_text = json.dumps(plan["incremental_implementation_plan"], ensure_ascii=True).lower()
    assert "requirement_note" in technical_text
    assert "source mutation" in technical_text


def test_task_decomposition_incremental_plan_strips_target_root_from_subject(tmp_path: Path) -> None:
    target_root = make_target_repo(tmp_path)
    config = controller_config(tmp_path, target_root)
    request = (
        f"In {target_root}, create an incremental implementation plan for adding a requirement note "
        "to the create-order response. Include isolated changesets, verification commands, "
        "and meaningful commit messages. Do not change files."
    )
    with RunningControllerService(config) as service:
        status, body = request_json(
            *service.base_url,
            "POST",
            "/v1/controller/task-decompositions",
            decompose_payload(target_root, request),
        )

    assert status == 200
    plan = load_artifact(body, "task_decomposition")
    assert_phase115_incremental_implementation_contract(plan)
    source_request = plan["incremental_implementation_plan"]["source_request"]
    assert str(target_root).lower() not in source_request["text"].lower()
    assert "requirement_note" in source_request["domain_terms"]
    assert "create" not in source_request["domain_terms"]
    subjects = [
        item["commit_message"]["subject"].lower()
        for item in plan["incremental_implementation_plan"]["changesets"]
    ]
    assert all("requirement note" in subject for subject in subjects)
    commands = [
        command
        for item in plan["incremental_implementation_plan"]["changesets"]
        for command in item["verification_commands"]
    ]
    assert "python -m pytest tests/test_stealth_order_manager.py -q" in commands


def test_task_decomposition_incremental_plan_extracts_behavior_after_with_clause(tmp_path: Path) -> None:
    target_root = make_target_repo(tmp_path)
    config = controller_config(tmp_path, target_root)
    request = (
        f"In {target_root}, create an implementation plan with isolated changesets, verification commands, "
        "and meaningful commit messages for adding a requirement note to the stealth order lookup answer. "
        "Do not change files."
    )
    with RunningControllerService(config) as service:
        status, body = request_json(
            *service.base_url,
            "POST",
            "/v1/controller/task-decompositions",
            decompose_payload(target_root, request),
        )

    assert status == 200
    plan = load_artifact(body, "task_decomposition")
    assert_phase115_incremental_implementation_contract(plan)
    source_request = plan["incremental_implementation_plan"]["source_request"]
    assert source_request["text"].lower().startswith("adding a requirement note")
    assert "requirement_note" in source_request["domain_terms"]
    subjects = [
        item["commit_message"]["subject"].lower()
        for item in plan["incremental_implementation_plan"]["changesets"]
    ]
    assert subjects == [
        "identify requirement note to stealth order lookup",
        "add requirement note to stealth order lookup",
        "cover requirement note to stealth order lookup",
    ]


def test_workflow_router_routes_incremental_implementation_to_task_decompose() -> None:
    prompt = (
        "In /tmp/example, create an implementation plan with isolated changesets, "
        "verification commands, and commit messages for adding a config default."
    )

    workflow_id, reason, evidence = workflow_kind_for_request(prompt)

    assert workflow_id == "task.decompose"
    assert reason == "ready"
    assert any(item.get("rule") == "task_decomposition_terms" for item in evidence)


def test_workflow_router_chat_incremental_plan_returns_inline_format_a(tmp_path: Path) -> None:
    target_root = make_target_repo(tmp_path)
    config = controller_config(tmp_path, target_root)
    prompt = (
        f"In {target_root}, create an incremental implementation plan for adding a requirement note "
        "to the create-order response. Include isolated changesets, verification commands, and commit messages."
    )
    with RunningControllerService(config) as service:
        status, body = request_json(
            *service.base_url,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            chat_payload(target_root, prompt),
        )

    assert status == 200
    content = body["choices"][0]["message"]["content"]
    assert "- Selected workflow: task.decompose" in content
    assert "Task Decomposition:" in content
    assert "Incremental Implementation Plan:" in content
    assert "- Changesets:" in content
    assert "- Changeset verification:" in content
    assert "- Commit messages:" in content
    assert "- Commit order:" in content
    assert "- Source apply policy: blocked_in_task_decompose" in content
    assert "- Source mutation: False" in content


def test_workflow_router_chat_incremental_plan_json_contract(tmp_path: Path) -> None:
    target_root = make_target_repo(tmp_path)
    config = controller_config(tmp_path, target_root)
    prompt = (
        f"In {target_root}, create an implementation plan with isolated changesets, verification commands, "
        "and meaningful commit messages for adding a config default. Return JSON."
    )
    with RunningControllerService(config) as service:
        status, body = request_json(
            *service.base_url,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            chat_payload(target_root, prompt, json_output=True),
        )

    assert status == 200
    parsed = json.loads(body["choices"][0]["message"]["content"])
    contract = parsed["task_decomposition_contract"]
    assert contract["prompt_family"] == "incremental_implementation_plan"
    incremental = contract["incremental_implementation_plan"]
    assert incremental["version_control_plan"]["commit_order"] == ["CS1", "CS2", "CS3"]
    assert incremental["source_apply_policy"]["status"] == "blocked_in_task_decompose"
    assert parsed["chat_contract"]["selected_workflow"] == "task.decompose"


def test_task_decomposition_delivery_mentorship_contract(tmp_path: Path) -> None:
    target_root = make_target_repo(tmp_path)
    config = controller_config(tmp_path, target_root)
    request = (
        "Create an end-to-end delivery plan for adding a requirement note to the create-order response. "
        "Mentor a junior engineer from requirement intake through deployment readiness. Read only. "
        "Include testing strategy, debugging method, code quality practices, review feedback, definition of done, "
        "and stop conditions."
    )
    with RunningControllerService(config) as service:
        status, body = request_json(
            *service.base_url,
            "POST",
            "/v1/controller/task-decompositions",
            decompose_payload(target_root, request),
        )

    assert status == 200
    assert body["summary"]["prompt_family"] == "delivery_mentorship"
    assert body["summary"]["delivery_mentorship_status"] == "ready_for_review"
    assert body["summary"]["delivery_sequence_count"] == 6
    assert body["summary"]["mentorship_note_count"] >= 3
    plan = load_artifact(body, "task_decomposition")
    assert_phase119_delivery_mentorship_contract(plan)


def test_workflow_router_routes_delivery_mentorship_to_task_decompose() -> None:
    prompt = (
        "In /tmp/example, coach a junior engineer through an end-to-end delivery plan "
        "from requirement intake through deployment readiness with testing strategy and code quality gates."
    )

    workflow_id, reason, evidence = workflow_kind_for_request(prompt)

    assert workflow_id == "task.decompose"
    assert reason == "ready"
    assert any(item.get("rule") == "task_decomposition_terms" for item in evidence)


def test_workflow_router_chat_delivery_mentorship_returns_inline_format_a(tmp_path: Path) -> None:
    target_root = make_target_repo(tmp_path)
    config = controller_config(tmp_path, target_root)
    prompt = (
        f"In {target_root}, coach a junior engineer through an end-to-end delivery plan "
        "for adding a requirement note to the create-order response. Read only. Include testing strategy, "
        "debugging method, code quality practices, deployment readiness, definition of done, and stop conditions."
    )
    with RunningControllerService(config) as service:
        status, body = request_json(
            *service.base_url,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            chat_payload(target_root, prompt),
        )

    assert status == 200
    content = body["choices"][0]["message"]["content"]
    assert "- Selected workflow: task.decompose" in content
    assert "Task Decomposition:" in content
    assert "Delivery Mentorship Plan:" in content
    assert "- Delivery sequence:" in content
    assert "- Testing strategy:" in content
    assert "- Debugging method:" in content
    assert "- Code quality practices:" in content
    assert "- Deployment readiness:" in content
    assert "- Mentorship notes:" in content
    assert "- Definition of done:" in content
    assert "- Stop conditions:" in content
    assert "- Source apply policy: blocked_in_task_decompose; deployment=not_deployed_by_this_workflow" in content
    assert "- Source mutation: False" in content


def test_workflow_router_chat_delivery_mentorship_json_contract(tmp_path: Path) -> None:
    target_root = make_target_repo(tmp_path)
    config = controller_config(tmp_path, target_root)
    prompt = (
        f"In {target_root}, mentor a junior engineer through a delivery plan for adding a config default. "
        "Read only. Include testing strategy, debugging methodology, code quality practices, deployment readiness, "
        "and definition of done. Return JSON."
    )
    with RunningControllerService(config) as service:
        status, body = request_json(
            *service.base_url,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            chat_payload(target_root, prompt, json_output=True),
        )

    assert status == 200
    parsed = json.loads(body["choices"][0]["message"]["content"])
    contract = parsed["task_decomposition_contract"]
    assert contract["prompt_family"] == "delivery_mentorship"
    delivery = contract["delivery_mentorship"]
    assert delivery["source_apply_policy"]["status"] == "blocked_in_task_decompose"
    assert delivery["source_apply_policy"]["deployment_status"] == "not_deployed_by_this_workflow"
    assert parsed["chat_contract"]["selected_workflow"] == "task.decompose"


def test_workflow_router_chat_task_decomposition_defers_advanced_refactor_json(tmp_path: Path) -> None:
    target_root = make_target_repo(tmp_path)
    config = controller_config(tmp_path, target_root)
    prompt = (
        f"In {target_root}, decompose this multi-step task into work packages with dependencies, "
        "approval gates, and verification strategy: refactor the placed_order_id stealth lookup so "
        "there is one code path. Return JSON."
    )
    with RunningControllerService(config) as service:
        status, body = request_json(
            *service.base_url,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            chat_payload(target_root, prompt, json_output=True),
        )

    assert status == 200
    parsed = json.loads(body["choices"][0]["message"]["content"])
    assert parsed["chat_contract"]["selected_workflow"] == "task.decompose"
    contract = parsed["task_decomposition_contract"]
    assert contract["status"] == "blocked"
    assert contract["prompt_family"] == "advanced_refactor_deferred"
    assert contract["deferred_to_phase"] == 105
    assert [item["id"] for item in contract["work_packages"]] == ["DEFER1"]
    assert contract["target_repository_changed"] is False


def test_task_decomposition_quality_rejects_missing_acceptance_criteria(tmp_path: Path) -> None:
    target_root = make_target_repo(tmp_path)
    plan = build_valid_plan(tmp_path, target_root)
    del plan["work_packages"][0]["acceptance_criteria"]

    report = evaluate_task_decomposition_plan(plan)

    assert report["status"] == "failed"
    assert any(issue["code"] == "missing_acceptance_criteria" for issue in report["issues"])


def test_task_decomposition_quality_rejects_non_objective_acceptance_criteria(tmp_path: Path) -> None:
    target_root = make_target_repo(tmp_path)
    plan = build_valid_plan(tmp_path, target_root)
    plan["work_packages"][0]["acceptance_criteria"][0]["objectivity"]["evidence_source"] = "unknown.field"

    report = evaluate_task_decomposition_plan(plan)

    assert report["status"] == "failed"
    assert any(issue["code"] == "non_objective_acceptance_criterion" for issue in report["issues"])


def test_task_decomposition_quality_rejects_oversized_package_set(tmp_path: Path) -> None:
    target_root = make_target_repo(tmp_path)
    plan = build_valid_plan(tmp_path, target_root)
    plan["work_packages"].append({**plan["work_packages"][-1], "id": "EXTRA6", "depends_on": ["STOP5"]})

    report = evaluate_task_decomposition_plan(plan)

    assert report["status"] == "failed"
    assert any(issue["code"] == "oversized_package_set" for issue in report["issues"])


def test_task_decomposition_quality_rejects_ambiguous_dependency(tmp_path: Path) -> None:
    target_root = make_target_repo(tmp_path)
    plan = build_valid_plan(tmp_path, target_root)
    plan["work_packages"][1]["depends_on"] = ["MISSING"]

    report = evaluate_task_decomposition_plan(plan)

    assert report["status"] == "failed"
    assert any(issue["code"] == "ambiguous_dependency" for issue in report["issues"])


def test_task_decomposition_quality_rejects_unsupported_implementation_claim(tmp_path: Path) -> None:
    target_root = make_target_repo(tmp_path)
    plan = build_valid_plan(tmp_path, target_root)
    plan["work_packages"][0]["workflow_id"] = "implementation.workflow"

    report = evaluate_task_decomposition_plan(plan)

    assert report["status"] == "failed"
    assert any(issue["code"] == "unsupported_implementation_claim" for issue in report["issues"])


def test_task_decomposition_quality_rejects_untraceable_requirements_translation(tmp_path: Path) -> None:
    target_root = make_target_repo(tmp_path)
    config = controller_config(tmp_path, target_root)
    request = (
        "Translate this business requirement into technical requirements and estimate effort: "
        "users need the stealth order lookup answer to say whether placed_order_id evidence was found."
    )
    with RunningControllerService(config) as service:
        status, body = request_json(
            *service.base_url,
            "POST",
            "/v1/controller/task-decompositions",
            decompose_payload(target_root, request),
        )
    assert status == 200
    plan = load_artifact(body, "task_decomposition")
    plan["requirements_translation"]["technical_requirements"][0]["derived_from"] = ["MISSING"]
    plan["requirements_translation"]["rejected_assumptions"] = []

    report = evaluate_task_decomposition_plan(plan)

    assert report["status"] == "failed"
    assert any(issue["code"] == "invalid_requirements_traceability" for issue in report["issues"])
    assert any(issue["code"] == "unsupported_assumption" for issue in report["issues"])


def test_task_decomposition_quality_rejects_generic_requirements_translation(tmp_path: Path) -> None:
    target_root = make_target_repo(tmp_path)
    config = controller_config(tmp_path, target_root)
    request = (
        "Translate this business requirement into technical requirements and estimate effort: "
        "users need the stealth order lookup answer to say whether placed_order_id evidence was found."
    )
    with RunningControllerService(config) as service:
        status, body = request_json(
            *service.base_url,
            "POST",
            "/v1/controller/task-decompositions",
            decompose_payload(target_root, request),
        )
    assert status == 200
    plan = load_artifact(body, "task_decomposition")
    plan["requirements_translation"]["technical_requirements"][0]["requirement"] = (
        "Identify the bounded code path affected by BR1 before implementation prep."
    )
    plan["requirements_translation"]["technical_requirements"][0]["complexity_guardrail"] = (
        "Do not add unnecessary complexity."
    )
    plan["requirements_translation"]["technical_requirements"][0]["domain_terms"] = []

    report = evaluate_task_decomposition_plan(plan)

    assert report["status"] == "failed"
    assert any(issue["code"] == "invalid_requirements_traceability" for issue in report["issues"])


def test_task_decomposition_quality_rejects_generic_requirement_body_with_side_fields_intact(tmp_path: Path) -> None:
    target_root = make_target_repo(tmp_path)
    config = controller_config(tmp_path, target_root)
    request = (
        "Translate this business requirement into technical requirements and estimate effort: "
        "users need the stealth order lookup answer to say whether placed_order_id evidence was found."
    )
    with RunningControllerService(config) as service:
        status, body = request_json(
            *service.base_url,
            "POST",
            "/v1/controller/task-decompositions",
            decompose_payload(target_root, request),
        )
    assert status == 200
    plan = load_artifact(body, "task_decomposition")
    for item in plan["requirements_translation"]["technical_requirements"]:
        item["requirement"] = "Perform the requested change after reviewing BR1."

    report = evaluate_task_decomposition_plan(plan)

    assert report["status"] == "failed"
    assert any(issue["code"] == "invalid_requirements_traceability" for issue in report["issues"])


def test_task_decomposition_quality_rejects_vague_phase115_commit_message(tmp_path: Path) -> None:
    target_root = make_target_repo(tmp_path)
    config = controller_config(tmp_path, target_root)
    request = (
        "Create an implementation plan with isolated changesets, verification commands, "
        "and meaningful commit messages for adding a config default."
    )
    with RunningControllerService(config) as service:
        status, body = request_json(
            *service.base_url,
            "POST",
            "/v1/controller/task-decompositions",
            decompose_payload(target_root, request),
        )
    assert status == 200
    plan = load_artifact(body, "task_decomposition")
    plan["incremental_implementation_plan"]["changesets"][1]["commit_message"]["subject"] = "Add changes"

    report = evaluate_task_decomposition_plan(plan)

    assert report["status"] == "failed"
    assert any(issue["code"] == "invalid_commit_message" for issue in report["issues"])


def test_task_decomposition_quality_rejects_weak_phase115_commit_traceability(tmp_path: Path) -> None:
    target_root = make_target_repo(tmp_path)
    config = controller_config(tmp_path, target_root)
    request = (
        "Create an implementation plan with isolated changesets, verification commands, "
        "and meaningful commit messages for adding a requirement note to the stealth order lookup answer."
    )
    with RunningControllerService(config) as service:
        status, body = request_json(
            *service.base_url,
            "POST",
            "/v1/controller/task-decompositions",
            decompose_payload(target_root, request),
        )
    assert status == 200
    plan = load_artifact(body, "task_decomposition")
    assert "requirement_note" in plan["incremental_implementation_plan"]["source_request"]["domain_terms"]
    plan["incremental_implementation_plan"]["changesets"][1]["commit_message"]["subject"] = "Add lookup answer"

    report = evaluate_task_decomposition_plan(plan)

    assert report["status"] == "failed"
    assert any(issue["code"] == "invalid_commit_message" for issue in report["issues"])


def test_task_decomposition_quality_rejects_phase115_placeholder_verification_command(tmp_path: Path) -> None:
    target_root = make_target_repo(tmp_path)
    config = controller_config(tmp_path, target_root)
    request = (
        "Create an implementation plan with isolated changesets, verification commands, "
        "and meaningful commit messages for adding a config default."
    )
    with RunningControllerService(config) as service:
        status, body = request_json(
            *service.base_url,
            "POST",
            "/v1/controller/task-decompositions",
            decompose_payload(target_root, request),
        )
    assert status == 200
    plan = load_artifact(body, "task_decomposition")
    plan["incremental_implementation_plan"]["changesets"][1]["verification_commands"] = [
        "python -m pytest <smallest-related-test> -q"
    ]

    report = evaluate_task_decomposition_plan(plan)

    assert report["status"] == "failed"
    assert any(issue["code"] == "invalid_changeset_isolation" for issue in report["issues"])


def test_task_decomposition_quality_rejects_phase115_broad_pytest_command(tmp_path: Path) -> None:
    target_root = make_target_repo(tmp_path)
    config = controller_config(tmp_path, target_root)
    request = (
        "Create an implementation plan with isolated changesets, verification commands, "
        "and meaningful commit messages for adding a config default."
    )
    with RunningControllerService(config) as service:
        status, body = request_json(
            *service.base_url,
            "POST",
            "/v1/controller/task-decompositions",
            decompose_payload(target_root, request),
        )
    assert status == 200
    plan = load_artifact(body, "task_decomposition")
    plan["incremental_implementation_plan"]["changesets"][1]["verification_commands"] = ["python -m pytest -q"]

    report = evaluate_task_decomposition_plan(plan)

    assert report["status"] == "failed"
    assert any(issue["code"] == "invalid_changeset_isolation" for issue in report["issues"])


def test_task_decomposition_quality_rejects_phase115_changeset_without_verification(tmp_path: Path) -> None:
    target_root = make_target_repo(tmp_path)
    config = controller_config(tmp_path, target_root)
    request = (
        "Create an implementation plan with isolated changesets, verification commands, "
        "and meaningful commit messages for adding a config default."
    )
    with RunningControllerService(config) as service:
        status, body = request_json(
            *service.base_url,
            "POST",
            "/v1/controller/task-decompositions",
            decompose_payload(target_root, request),
        )
    assert status == 200
    plan = load_artifact(body, "task_decomposition")
    plan["incremental_implementation_plan"]["changesets"][2]["verification_commands"] = []

    report = evaluate_task_decomposition_plan(plan)

    assert report["status"] == "failed"
    assert any(issue["code"] == "invalid_changeset_isolation" for issue in report["issues"])


def test_phase113_task_decomposition_case_catalog_passes_contract() -> None:
    catalog = load_json_object(REPO_ROOT / "runtime" / "task_decomposition_phase113_cases.json")

    report = validate_phase113_case_catalog(catalog)

    assert report["status"] == "passed"
    assert report["case_count"] >= 4
    assert set(report["prompt_families"]) >= {"feature", "bug", "requirement", "oversized"}


def test_phase114_requirements_translation_case_catalog_passes_contract() -> None:
    catalog = load_json_object(REPO_ROOT / "runtime" / "requirements_translation_phase114_cases.json")

    report = validate_phase114_case_catalog(catalog)

    assert report["status"] == "passed"
    assert report["case_count"] >= 2
    assert set(report["case_types"]) >= {"business_to_technical", "estimate_revision"}


def test_phase113_recursive_blind_testing_report_passes_contract() -> None:
    catalog = load_json_object(REPO_ROOT / "runtime" / "task_decomposition_phase113_cases.json")
    policy = load_json_object(REPO_ROOT / "runtime" / "recursive_blind_testing_policy.json")

    report = build_phase113_recursive_blind_testing_report(
        catalog,
        catalog_report_path="runtime-state/task-decomposition/phase113-case-catalog.json",
        live_report_path="runtime-state/task-decomposition/phase113-live.json",
        engineering_tenet_report_path="runtime-state/engineering-tenet-coverage/phase113-current.json",
        focused_regression_ref="python -m pytest tests/regression/test_task_decomposition.py -q -> 15 passed",
        adjacent_regression_ref=(
            "python -m pytest tests/regression/test_task_decomposition.py "
            "tests/regression/test_chat_response_contract.py tests/regression/test_v1_acceptance.py "
            "tests/regression/test_engineering_tenet_coverage.py -q -> 38 passed"
        ),
        full_regression_ref="bash -lc 'python -m pytest tests/regression/ -v' -> passed",
        recursive_validation_ref=(
            "runtime-state/recursive-blind-testing/phase113-task-decomposition-recursive-validation.json"
        ),
    )

    checks = validate_recursive_report(
        policy,
        report,
        report_path=REPO_ROOT / "runtime-state" / "recursive-blind-testing" / "phase113-task-decomposition-recursive-report.json",
    )

    assert all(item["status"] == "passed" for item in checks)


def test_phase114_recursive_blind_testing_report_passes_contract() -> None:
    catalog = load_json_object(REPO_ROOT / "runtime" / "requirements_translation_phase114_cases.json")
    policy = load_json_object(REPO_ROOT / "runtime" / "recursive_blind_testing_policy.json")

    report = build_phase114_recursive_blind_testing_report(
        catalog,
        catalog_report_path="runtime-state/task-decomposition/phase114-case-catalog.json",
        live_report_path="runtime-state/task-decomposition/phase114-requirements-live.json",
        engineering_tenet_report_path="runtime-state/engineering-tenet-coverage/phase114-current.json",
        focused_regression_ref="python -m pytest tests/regression/test_task_decomposition.py -q -> 27 passed",
        adjacent_regression_ref=(
            "python -m pytest tests/regression/test_task_decomposition.py "
            "tests/regression/test_chat_response_contract.py tests/regression/test_v1_acceptance.py "
            "tests/regression/test_engineering_tenet_coverage.py -q -> 50 passed"
        ),
        full_regression_ref="bash -lc 'python -m pytest tests/regression/ -v' -> passed",
        recursive_validation_ref=(
            "runtime-state/recursive-blind-testing/phase114-requirements-translation-recursive-validation.json"
        ),
        final_audit_ref="contextless subagent follow-up audit -> score 88/100",
    )

    checks = validate_recursive_report(
        policy,
        report,
        report_path=REPO_ROOT / "runtime-state" / "recursive-blind-testing" / "phase114-requirements-translation-recursive-report.json",
    )

    assert all(item["status"] == "passed" for item in checks)


def test_phase115_incremental_implementation_case_catalog_passes_contract() -> None:
    catalog = load_json_object(REPO_ROOT / "runtime" / "incremental_implementation_phase115_cases.json")

    report = validate_phase115_case_catalog(catalog)

    assert report["status"] == "passed"
    assert report["case_count"] >= 2
    assert set(report["case_types"]) >= {"feature_implementation_plan", "test_update_plan"}


def test_phase115_case_catalog_rejects_missing_expected_behavior_term() -> None:
    catalog = load_json_object(REPO_ROOT / "runtime" / "incremental_implementation_phase115_cases.json")
    catalog["cases"][0]["expected_domain_terms"] = ["missing_behavior_term"]

    report = validate_phase115_case_catalog(catalog)

    assert report["status"] == "failed"
    assert any("generated domain terms missing expected term" in issue["message"] for issue in report["issues"])


def test_phase119_delivery_mentorship_case_catalog_passes_contract() -> None:
    catalog = load_json_object(REPO_ROOT / "runtime" / "phase119_delivery_mentorship_prompt_cases.json")

    report = validate_phase119_case_catalog(catalog)

    assert report["status"] == "passed"
    assert report["case_count"] >= 10
    assert report["holdout_count"] >= 2
    assert set(report["case_types"]) >= {
        "feature_delivery",
        "testing_strategy_mentorship",
        "debugging_method_mentorship",
        "quality_gate_mentorship",
        "deployment_readiness",
        "holdout_retry_safety",
        "holdout_bulk_import",
    }


def test_phase119_case_catalog_rejects_missing_delivery_marker() -> None:
    catalog = load_json_object(REPO_ROOT / "runtime" / "phase119_delivery_mentorship_prompt_cases.json")
    catalog["cases"][0]["expected_markers"] = [
        marker for marker in catalog["cases"][0]["expected_markers"] if marker != "- Deployment readiness:"
    ]

    report = validate_phase119_case_catalog(catalog)

    assert report["status"] == "failed"
    assert any("expected_markers missing required values" in issue["message"] for issue in report["issues"])


def test_phase115_recursive_blind_testing_report_passes_contract() -> None:
    catalog = load_json_object(REPO_ROOT / "runtime" / "incremental_implementation_phase115_cases.json")
    policy = load_json_object(REPO_ROOT / "runtime" / "recursive_blind_testing_policy.json")

    report = build_phase115_recursive_blind_testing_report(
        catalog,
        catalog_report_path="runtime-state/task-decomposition/phase115-case-catalog.json",
        live_report_path="runtime-state/task-decomposition/phase115-incremental-implementation-live.json",
        engineering_tenet_report_path="runtime-state/engineering-tenet-coverage/phase115-current.json",
        focused_regression_ref="python -m pytest tests/regression/test_task_decomposition.py -q -> 43 passed",
        adjacent_regression_ref=(
            "python -m pytest tests/regression/test_task_decomposition.py "
            "tests/regression/test_chat_response_contract.py tests/regression/test_v1_acceptance.py "
            "tests/regression/test_engineering_tenet_coverage.py -q -> 66 passed"
        ),
        full_regression_ref="bash -lc 'python -m pytest tests/regression/ -v' -> passed",
        recursive_validation_ref=(
            "runtime-state/recursive-blind-testing/phase115-incremental-implementation-recursive-validation.json"
        ),
        final_audit_ref="contextless subagent final audit -> score 85/100",
    )

    checks = validate_recursive_report(
        policy,
        report,
        report_path=REPO_ROOT / "runtime-state" / "recursive-blind-testing" / "phase115-incremental-implementation-recursive-report.json",
    )

    assert all(item["status"] == "passed" for item in checks)
