from __future__ import annotations

import http.client
import json
import threading
from pathlib import Path
from typing import Any

from vllm_agent_gateway.controller_service.server import ControllerServiceConfig, create_server


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
    connection = http.client.HTTPConnection(host, port, timeout=60)
    try:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        connection.request(method, path, body=body, headers={"Content-Type": "application/json"})
        response = connection.getresponse()
        parsed = json.loads(response.read().decode("utf-8"))
        return response.status, parsed
    finally:
        connection.close()


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


def assert_phase102_work_package_contract(plan: dict[str, Any]) -> None:
    assert plan["work_package_schema_version"] == 2
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
        assert isinstance(item["stop_conditions"], list) and item["stop_conditions"]
        assert isinstance(item["verification"], dict)
        assert item["verification"]["status"]
    assert [gate["package_id"] for gate in plan["approval_gates"]] == ["GATE2", "STOP5"]
    assert {gate["approval_scope"] for gate in plan["approval_gates"]} == {"packet_design_only", "repository_mutation"}


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
    assert_phase102_work_package_contract(plan)
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
    assert plan["blockers"][0]["reason"] == "ambiguous_task"
    assert plan["target_repository_changed"] is False
    assert plan["runtime_registry_changed"] is False


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
    assert plan["work_packages"][0]["stop_conditions"][0]["code"] == "phase_105_not_ready"
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
    assert "- Work-package schema: 2" in content
    assert "- Work packages:" in content
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
    assert contract["work_package_schema_version"] == 2
    assert [item["id"] for item in contract["work_packages"]] == ["WP1", "GATE2", "WP3", "WP4", "STOP5"]
    assert contract["approval_gates"][0]["package_id"] == "GATE2"


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
