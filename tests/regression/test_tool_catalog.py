from __future__ import annotations

import http.client
import json
import shutil
import threading
from pathlib import Path
from typing import Any

from vllm_agent_gateway.controller_service.server import ControllerServiceConfig, create_server
from vllm_agent_gateway.controller_service.tool_policy import resolve_controller_tool_policy


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


def request_json(host: str, port: int, path: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    connection = http.client.HTTPConnection(host, port, timeout=30)
    try:
        connection.request(
            "POST",
            path,
            body=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        body = json.loads(response.read().decode("utf-8"))
        return response.status, body
    finally:
        connection.close()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def runtime_snapshot(config_root: Path) -> dict[str, str]:
    return {
        "runtime/tools.json": (config_root / "runtime" / "tools.json").read_text(encoding="utf-8"),
        "runtime/workflows.json": (config_root / "runtime" / "workflows.json").read_text(encoding="utf-8"),
        "runtime/roles.json": (config_root / "runtime" / "roles.json").read_text(encoding="utf-8"),
    }


def runtime_tool_ids(config_root: Path) -> list[str]:
    manifest = json.loads((config_root / "runtime" / "tools.json").read_text(encoding="utf-8"))
    return [item["id"] for item in manifest["tools"]]


def make_tool_catalog_root(tmp_path: Path, *, remove_tool_id: str | None = None) -> Path:
    root = tmp_path / "tool-catalog-root"
    shutil.copytree(REPO_ROOT / "runtime", root / "runtime")
    if remove_tool_id:
        tools_path = root / "runtime" / "tools.json"
        manifest = json.loads(tools_path.read_text(encoding="utf-8"))
        manifest["tools"] = [item for item in manifest["tools"] if item.get("id") != remove_tool_id]
        write_json(tools_path, manifest)
    return root


def scan_files_tool_manifest() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "tool_admission_manifest",
        "tool": {
            "id": "scan_files",
            "owner": "agentic_agents",
            "kind": "filesystem_read",
            "description": "Scan repository files for first-run or bootstrap discovery.",
            "read_only": True,
            "args_schema": {
                "ignored_dirs": {
                    "type": "array",
                    "required": False,
                }
            },
            "input_schema": {
                "type": "object",
                "properties": {
                    "ignored_dirs": {"type": "array", "items": {"type": "string"}},
                },
                "required": [],
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "paths": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["paths"],
            },
            "safety_class": "read_only",
            "mutation_policy": "no_repository_mutation",
            "allowed_workflows": ["documenter.review"],
            "allowed_roles": ["documenter/default"],
        },
    }


def tool_registration_approval() -> dict[str, Any]:
    return {
        "status": "approved_for_tool_catalog_registration",
        "scope": "tool_catalog_registration",
        "runtime_tool_append": True,
        "approval_refs": ["phase51-controlled-copy"],
    }


def test_tool_catalog_validate_and_register_restores_supported_tool_metadata_only(tmp_path: Path) -> None:
    config_root = make_tool_catalog_root(tmp_path, remove_tool_id="scan_files")
    output_root = tmp_path / "controller-output"
    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=output_root,
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    before = runtime_snapshot(config_root)
    with RunningControllerService(config) as service:
        host, port = service.base_url
        validation_status, validation_body = request_json(
            host,
            port,
            "/v1/controller/tool-catalog/validations",
            {
                "workflow": "tool_catalog.validate",
                "schema_version": 1,
                "tool_manifest": scan_files_tool_manifest(),
            },
        )
        registration_status, registration_body = request_json(
            host,
            port,
            "/v1/controller/tool-catalog/registrations",
            {
                "workflow": "tool_catalog.register",
                "schema_version": 1,
                "tool_manifest": scan_files_tool_manifest(),
                "approval": tool_registration_approval(),
            },
        )

    assert validation_status == 200
    assert validation_body["summary"]["validation_status"] == "passed"
    assert validation_body["summary"]["runtime_registry_changed"] is False
    assert validation_body["summary"]["target_repository_changed"] is False
    assert registration_status == 200
    assert registration_body["summary"]["registration_status"] == "installed"
    assert registration_body["summary"]["tool_id"] == "scan_files"
    assert registration_body["summary"]["changed_runtime_files"] == ["runtime/tools.json"]
    assert registration_body["summary"]["runtime_workflow_registry_changed"] is False
    assert registration_body["summary"]["runtime_role_registry_changed"] is False
    assert registration_body["summary"]["target_repository_changed"] is False
    assert (config_root / "runtime" / "tools.json").read_text(encoding="utf-8") != before["runtime/tools.json"]
    assert (config_root / "runtime" / "workflows.json").read_text(encoding="utf-8") == before["runtime/workflows.json"]
    assert (config_root / "runtime" / "roles.json").read_text(encoding="utf-8") == before["runtime/roles.json"]

    policy = resolve_controller_tool_policy(
        config_root,
        "documenter.review",
        "documenter/default",
        {"document_scope": "all"},
        [],
    )
    assert "scan_files" in policy.controller_tool_ids
    assert policy.model_visible_tool_ids == []
    unrelated_policy = resolve_controller_tool_policy(
        config_root,
        "code_investigation.plan",
        "architect/default",
        {},
        [],
    )
    assert "scan_files" not in unrelated_policy.controller_tool_ids
    assert "scan_files" not in unrelated_policy.model_visible_tool_ids


def test_tool_catalog_validate_rejects_unsafe_file_access(tmp_path: Path) -> None:
    config_root = make_tool_catalog_root(tmp_path, remove_tool_id="scan_files")
    before = runtime_snapshot(config_root)
    manifest = scan_files_tool_manifest()
    manifest["tool"]["read_only"] = False
    manifest["tool"]["safety_class"] = "test_execution"
    manifest["tool"]["mutation_policy"] = "test_execution"
    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        status, body = request_json(
            *service.base_url,
            "/v1/controller/tool-catalog/validations",
            {
                "workflow": "tool_catalog.validate",
                "schema_version": 1,
                "tool_manifest": manifest,
            },
        )

    assert status == 200
    assert body["status"] == "failed"
    assert body["failures"][0]["code"] == "unsafe_file_access"
    assert runtime_snapshot(config_root) == before
    assert "scan_files" not in runtime_tool_ids(config_root)


def test_tool_catalog_validate_rejects_invalid_role_exposure(tmp_path: Path) -> None:
    config_root = make_tool_catalog_root(tmp_path, remove_tool_id="scan_files")
    before = runtime_snapshot(config_root)
    manifest = scan_files_tool_manifest()
    manifest["tool"]["allowed_roles"] = ["architect/default"]
    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        status, body = request_json(
            *service.base_url,
            "/v1/controller/tool-catalog/validations",
            {
                "workflow": "tool_catalog.validate",
                "schema_version": 1,
                "tool_manifest": manifest,
            },
        )

    assert status == 200
    assert body["status"] == "failed"
    assert body["failures"][0]["code"] == "role_exposure_incompatible"
    assert runtime_snapshot(config_root) == before


def test_tool_catalog_register_rejects_duplicate_existing_tool_without_mutation(tmp_path: Path) -> None:
    config_root = make_tool_catalog_root(tmp_path)
    before = (config_root / "runtime" / "tools.json").read_text(encoding="utf-8")
    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        status, body = request_json(
            *service.base_url,
            "/v1/controller/tool-catalog/registrations",
            {
                "workflow": "tool_catalog.register",
                "schema_version": 1,
                "tool_manifest": scan_files_tool_manifest(),
                "approval": tool_registration_approval(),
            },
        )

    assert status == 422
    assert body["error"]["code"] == "tool_already_registered"
    assert (config_root / "runtime" / "tools.json").read_text(encoding="utf-8") == before


def test_tool_catalog_register_rejects_missing_approval_without_mutation(tmp_path: Path) -> None:
    config_root = make_tool_catalog_root(tmp_path, remove_tool_id="scan_files")
    before = runtime_snapshot(config_root)
    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        status, body = request_json(
            *service.base_url,
            "/v1/controller/tool-catalog/registrations",
            {
                "workflow": "tool_catalog.register",
                "schema_version": 1,
                "tool_manifest": scan_files_tool_manifest(),
            },
        )

    assert status == 403
    assert body["error"]["code"] == "missing_tool_catalog_registration_approval"
    assert runtime_snapshot(config_root) == before


def test_tool_catalog_validate_rejects_unsupported_executable_tool_without_mutation(tmp_path: Path) -> None:
    config_root = make_tool_catalog_root(tmp_path)
    before = runtime_snapshot(config_root)
    manifest = scan_files_tool_manifest()
    manifest["tool"]["id"] = "repo_secret_dump"
    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )
    with RunningControllerService(config) as service:
        status, body = request_json(
            *service.base_url,
            "/v1/controller/tool-catalog/validations",
            {
                "workflow": "tool_catalog.validate",
                "schema_version": 1,
                "tool_manifest": manifest,
            },
        )

    assert status == 200
    assert body["status"] == "failed"
    assert body["failures"][0]["code"] == "unsupported_executable_tool"
    assert runtime_snapshot(config_root) == before
