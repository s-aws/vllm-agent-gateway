from __future__ import annotations

import http.client
import json
import shutil
import threading
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.connector_eval_release_gate import run_connector_eval_release_gate
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


def make_connector_catalog_root(tmp_path: Path) -> Path:
    root = tmp_path / "connector-catalog-root"
    shutil.copytree(REPO_ROOT / "runtime", root / "runtime")
    return root


def runtime_snapshot(config_root: Path) -> dict[str, str]:
    return {
        "runtime/connectors.json": (config_root / "runtime" / "connectors.json").read_text(encoding="utf-8"),
        "runtime/tools.json": (config_root / "runtime" / "tools.json").read_text(encoding="utf-8"),
        "runtime/workflows.json": (config_root / "runtime" / "workflows.json").read_text(encoding="utf-8"),
        "runtime/roles.json": (config_root / "runtime" / "roles.json").read_text(encoding="utf-8"),
    }


def valid_connector_manifest() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "connector_admission_manifest",
        "connector": {
            "id": "ticketing_stub",
            "owner": "agentic_agents",
            "description": "Stub ticketing connector used only to validate governed connector contracts.",
            "protocol": "local_stub",
            "mediation": "controller_owned",
            "auth": {
                "type": "none_for_stub",
                "required_scopes": [],
            },
            "safety": {
                "data_classification": "public",
                "pii_policy": "not_allowed",
                "external_network": False,
                "raw_mcp_allowed": False,
                "direct_model_tool_access": False,
            },
            "operations": [
                {
                    "id": "lookup_ticket",
                    "description": "Look up one stub ticket by identifier for validation fixtures.",
                    "operation_class": "read",
                    "approval_required": False,
                    "input_schema": {
                        "type": "object",
                        "properties": {"ticket_id": {"type": "string"}},
                        "required": ["ticket_id"],
                    },
                    "output_schema": {
                        "type": "object",
                        "properties": {"status": {"type": "string"}},
                        "required": ["status"],
                    },
                    "allowed_workflows": ["workflow_router.plan"],
                    "eval_fixtures": ["connector_eval.ticketing_stub.lookup_ticket.basic"],
                }
            ],
        },
    }


def registered_stub_connector(*, enabled: bool = True) -> dict[str, Any]:
    connector = dict(valid_connector_manifest()["connector"])
    operation = dict(connector["operations"][0])
    operation["stub_response"] = {"status": "open", "source": "local_stub"}
    connector["operations"] = [operation]
    connector["enabled"] = enabled
    return connector


def registered_write_stub_connector() -> dict[str, Any]:
    connector = registered_stub_connector()
    connector["id"] = "ticketing_writer_stub"
    connector["auth"] = {"type": "oauth_user_scope", "required_scopes": ["tickets:write"]}
    operation = dict(connector["operations"][0])
    operation["id"] = "update_ticket"
    operation["description"] = "Dry-run update of one stub ticket for mediation validation."
    operation["operation_class"] = "write"
    operation["approval_required"] = True
    operation["stub_response"] = {"status": "dry_run_update_ready", "source": "local_stub"}
    connector["operations"] = [operation]
    return connector


def install_connector(config_root: Path, connector: dict[str, Any]) -> None:
    connectors_path = config_root / "runtime" / "connectors.json"
    catalog = json.loads(connectors_path.read_text(encoding="utf-8"))
    catalog["connectors"].append(connector)
    write_json(connectors_path, catalog)


def controller_config(config_root: Path, tmp_path: Path) -> ControllerServiceConfig:
    return ControllerServiceConfig(
        config_root=config_root,
        output_root=tmp_path / "controller-output",
        allowed_target_roots=(tmp_path / "allowed",),
        port=0,
    )


def validate_manifest(config_root: Path, tmp_path: Path, manifest: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    with RunningControllerService(controller_config(config_root, tmp_path)) as service:
        return request_json(
            *service.base_url,
            "/v1/controller/connector-catalog/validations",
            {
                "workflow": "connector_catalog.validate",
                "schema_version": 1,
                "connector_manifest": manifest,
            },
        )


def invoke_connector(
    config_root: Path,
    tmp_path: Path,
    *,
    connector_id: str = "ticketing_stub",
    operation_id: str = "lookup_ticket",
    arguments: dict[str, Any] | None = None,
    dry_run: bool = True,
    approval: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    payload: dict[str, Any] = {
        "workflow": "connector.invoke",
        "schema_version": 1,
        "connector_id": connector_id,
        "operation_id": operation_id,
        "arguments": {"ticket_id": "T-123"} if arguments is None else arguments,
        "dry_run": dry_run,
    }
    if approval is not None:
        payload["approval"] = approval
    with RunningControllerService(controller_config(config_root, tmp_path)) as service:
        return request_json(*service.base_url, "/v1/controller/connectors/invocations", payload)


def connector_invocation_approval(connector_id: str, operation_id: str) -> dict[str, Any]:
    return {
        "status": "approved_for_connector_invocation",
        "scope": "connector_invocation",
        "connector_id": connector_id,
        "operation_id": operation_id,
        "approval_refs": ["phase282-test-approval"],
    }


def connector_registration_approval(*, enabled: bool) -> dict[str, Any]:
    scope: list[str] = ["connector_catalog_registration"]
    if enabled:
        scope.append("connector_enablement")
    return {
        "status": "approved_for_connector_catalog_registration",
        "scope": scope,
        "runtime_connector_append": True,
        "enabled": enabled,
        "approval_refs": ["phase284-test-approval"],
    }


def register_connector(
    config_root: Path,
    tmp_path: Path,
    *,
    manifest: dict[str, Any] | None = None,
    approval: dict[str, Any] | None = None,
    release_gate_report_path: Path | None = None,
) -> tuple[int, dict[str, Any]]:
    payload: dict[str, Any] = {
        "workflow": "connector_catalog.register",
        "schema_version": 1,
        "connector_manifest": valid_connector_manifest() if manifest is None else manifest,
    }
    if approval is not None:
        payload["approval"] = approval
    if release_gate_report_path is not None:
        payload["release_gate_report_path"] = str(release_gate_report_path)
    with RunningControllerService(controller_config(config_root, tmp_path)) as service:
        return request_json(*service.base_url, "/v1/controller/connector-catalog/registrations", payload)


def write_release_gate_report(tmp_path: Path, *, connector_id: str = "ticketing_stub") -> Path:
    output_path = tmp_path / "controller-output" / "release-gates" / f"{connector_id}.json"
    report = run_connector_eval_release_gate(config_root=REPO_ROOT, output_path=output_path)
    if connector_id != "ticketing_stub":
        report["summary"]["connector_id"] = connector_id
        write_json(output_path, report)
    return output_path


def test_connector_catalog_validate_accepts_governed_stub_without_mutation(tmp_path: Path) -> None:
    config_root = make_connector_catalog_root(tmp_path)
    before = runtime_snapshot(config_root)
    status, body = validate_manifest(config_root, tmp_path, valid_connector_manifest())

    assert status == 200
    assert body["status"] == "completed"
    assert body["summary"]["validation_status"] == "passed"
    assert body["summary"]["connector_id"] == "ticketing_stub"
    assert body["summary"]["operation_count"] == 1
    assert body["summary"]["runtime_registry_changed"] is False
    assert body["summary"]["runtime_behavior_changed"] is False
    assert body["summary"]["target_repository_changed"] is False
    assert body["tool_policy"]["workflow"] == "connector_catalog.validate"
    assert body["tool_policy"]["controller_tool_ids"] == []
    assert body["tool_policy"]["model_visible_tool_ids"] == []
    assert Path(body["artifacts"]["connector_catalog_validation"]).exists()
    assert runtime_snapshot(config_root) == before


def test_connector_catalog_validate_rejects_raw_mcp_bypass_without_mutation(tmp_path: Path) -> None:
    config_root = make_connector_catalog_root(tmp_path)
    before = runtime_snapshot(config_root)
    manifest = valid_connector_manifest()
    manifest["connector"]["protocol"] = "mcp_mediated"
    manifest["connector"]["auth"] = {"type": "oauth_user_scope", "required_scopes": ["tickets:read"]}
    manifest["connector"]["safety"]["raw_mcp_allowed"] = True
    status, body = validate_manifest(config_root, tmp_path, manifest)

    assert status == 200
    assert body["status"] == "failed"
    assert body["failures"][0]["code"] == "raw_mcp_bypass_not_allowed"
    assert runtime_snapshot(config_root) == before


def test_connector_catalog_validate_rejects_write_without_approval(tmp_path: Path) -> None:
    config_root = make_connector_catalog_root(tmp_path)
    before = runtime_snapshot(config_root)
    manifest = valid_connector_manifest()
    operation = manifest["connector"]["operations"][0]
    operation["operation_class"] = "write"
    operation["approval_required"] = False
    manifest["connector"]["auth"] = {"type": "oauth_user_scope", "required_scopes": ["tickets:write"]}
    status, body = validate_manifest(config_root, tmp_path, manifest)

    assert status == 200
    assert body["status"] == "failed"
    assert body["failures"][0]["code"] == "unsafe_connector_write_operation"
    assert runtime_snapshot(config_root) == before


def test_connector_catalog_validate_rejects_missing_eval_fixtures(tmp_path: Path) -> None:
    config_root = make_connector_catalog_root(tmp_path)
    before = runtime_snapshot(config_root)
    manifest = valid_connector_manifest()
    manifest["connector"]["operations"][0]["eval_fixtures"] = []
    status, body = validate_manifest(config_root, tmp_path, manifest)

    assert status == 200
    assert body["status"] == "failed"
    assert body["failures"][0]["code"] == "invalid_connector_manifest"
    assert runtime_snapshot(config_root) == before


def test_connector_catalog_validate_rejects_duplicate_connector_id_without_mutation(tmp_path: Path) -> None:
    config_root = make_connector_catalog_root(tmp_path)
    manifest = valid_connector_manifest()
    connectors_path = config_root / "runtime" / "connectors.json"
    catalog = json.loads(connectors_path.read_text(encoding="utf-8"))
    catalog["connectors"].append(
        {
            "id": "ticketing_stub",
            "owner": "agentic_agents",
            "description": "Existing stub connector.",
            "enabled": False,
            "operations": [],
        }
    )
    write_json(connectors_path, catalog)
    before = runtime_snapshot(config_root)
    status, body = validate_manifest(config_root, tmp_path, manifest)

    assert status == 200
    assert body["status"] == "failed"
    assert body["failures"][0]["code"] == "connector_already_registered"
    assert runtime_snapshot(config_root) == before


def test_connector_catalog_validate_rejects_unknown_workflow(tmp_path: Path) -> None:
    config_root = make_connector_catalog_root(tmp_path)
    before = runtime_snapshot(config_root)
    manifest = valid_connector_manifest()
    manifest["connector"]["operations"][0]["allowed_workflows"] = ["missing.workflow"]
    status, body = validate_manifest(config_root, tmp_path, manifest)

    assert status == 200
    assert body["status"] == "failed"
    assert body["failures"][0]["code"] == "unknown_workflow"
    assert runtime_snapshot(config_root) == before


def test_connector_invocation_executes_enabled_local_stub_without_mutation(tmp_path: Path) -> None:
    config_root = make_connector_catalog_root(tmp_path)
    install_connector(config_root, registered_stub_connector())
    before = runtime_snapshot(config_root)
    status, body = invoke_connector(config_root, tmp_path)

    assert status == 200
    assert body["status"] == "completed"
    assert body["summary"]["invocation_status"] == "completed"
    assert body["summary"]["connector_id"] == "ticketing_stub"
    assert body["summary"]["operation_id"] == "lookup_ticket"
    assert body["summary"]["controller_owned_path"] is True
    assert body["summary"]["raw_mcp_used"] is False
    assert body["summary"]["direct_model_tool_access_used"] is False
    assert body["summary"]["external_network_called"] is False
    assert body["summary"]["runtime_registry_changed"] is False
    assert body["summary"]["target_repository_changed"] is False
    assert body["tool_policy"]["workflow"] == "connector.invoke"
    assert body["tool_policy"]["controller_tool_ids"] == []
    assert body["tool_policy"]["model_visible_tool_ids"] == []
    assert Path(body["artifacts"]["connector_invocation"]).exists()
    assert runtime_snapshot(config_root) == before


def test_connector_invocation_rejects_unknown_connector_with_artifact(tmp_path: Path) -> None:
    config_root = make_connector_catalog_root(tmp_path)
    before = runtime_snapshot(config_root)
    status, body = invoke_connector(config_root, tmp_path)

    assert status == 200
    assert body["status"] == "failed"
    assert body["failures"][0]["code"] == "unknown_connector"
    assert Path(body["artifacts"]["connector_invocation"]).exists()
    assert runtime_snapshot(config_root) == before


def test_connector_invocation_rejects_disabled_connector(tmp_path: Path) -> None:
    config_root = make_connector_catalog_root(tmp_path)
    install_connector(config_root, registered_stub_connector(enabled=False))
    before = runtime_snapshot(config_root)
    status, body = invoke_connector(config_root, tmp_path)

    assert status == 200
    assert body["status"] == "failed"
    assert body["failures"][0]["code"] == "connector_not_enabled"
    assert runtime_snapshot(config_root) == before


def test_connector_invocation_rejects_raw_mcp_bypass(tmp_path: Path) -> None:
    config_root = make_connector_catalog_root(tmp_path)
    connector = registered_stub_connector()
    connector["safety"]["raw_mcp_allowed"] = True
    install_connector(config_root, connector)
    before = runtime_snapshot(config_root)
    status, body = invoke_connector(config_root, tmp_path)

    assert status == 200
    assert body["status"] == "failed"
    assert body["failures"][0]["code"] == "raw_mcp_bypass_not_allowed"
    assert runtime_snapshot(config_root) == before


def test_connector_invocation_rejects_unsupported_argument(tmp_path: Path) -> None:
    config_root = make_connector_catalog_root(tmp_path)
    install_connector(config_root, registered_stub_connector())
    before = runtime_snapshot(config_root)
    status, body = invoke_connector(config_root, tmp_path, arguments={"ticket_id": "T-123", "extra": "no"})

    assert status == 200
    assert body["status"] == "failed"
    assert body["failures"][0]["code"] == "unsupported_connector_argument"
    assert runtime_snapshot(config_root) == before


def test_connector_invocation_write_requires_approval(tmp_path: Path) -> None:
    config_root = make_connector_catalog_root(tmp_path)
    install_connector(config_root, registered_write_stub_connector())
    before = runtime_snapshot(config_root)
    status, body = invoke_connector(
        config_root,
        tmp_path,
        connector_id="ticketing_writer_stub",
        operation_id="update_ticket",
    )

    assert status == 200
    assert body["status"] == "failed"
    assert body["failures"][0]["code"] == "missing_connector_invocation_approval"
    assert runtime_snapshot(config_root) == before


def test_connector_invocation_write_allows_approved_dry_run_only(tmp_path: Path) -> None:
    config_root = make_connector_catalog_root(tmp_path)
    install_connector(config_root, registered_write_stub_connector())
    before = runtime_snapshot(config_root)
    approval = connector_invocation_approval("ticketing_writer_stub", "update_ticket")
    status, body = invoke_connector(
        config_root,
        tmp_path,
        connector_id="ticketing_writer_stub",
        operation_id="update_ticket",
        dry_run=True,
        approval=approval,
    )

    assert status == 200
    assert body["status"] == "completed"
    assert body["summary"]["operation_class"] == "write"
    assert body["summary"]["dry_run"] is True
    assert runtime_snapshot(config_root) == before

    status, body = invoke_connector(
        config_root,
        tmp_path,
        connector_id="ticketing_writer_stub",
        operation_id="update_ticket",
        dry_run=False,
        approval=approval,
    )
    assert status == 200
    assert body["status"] == "failed"
    assert body["failures"][0]["code"] == "connector_write_execution_not_supported"
    assert runtime_snapshot(config_root) == before


def test_connector_catalog_register_installs_draft_connector_metadata_only(tmp_path: Path) -> None:
    config_root = make_connector_catalog_root(tmp_path)
    before = runtime_snapshot(config_root)
    status, body = register_connector(
        config_root,
        tmp_path,
        approval=connector_registration_approval(enabled=False),
    )

    assert status == 200
    assert body["status"] == "completed"
    assert body["summary"]["registration_status"] == "installed"
    assert body["summary"]["connector_id"] == "ticketing_stub"
    assert body["summary"]["enabled"] is False
    assert body["summary"]["changed_runtime_files"] == ["runtime/connectors.json"]
    assert body["summary"]["runtime_connector_registry_changed"] is True
    assert body["summary"]["runtime_tool_registry_changed"] is False
    assert body["summary"]["runtime_workflow_registry_changed"] is False
    assert body["summary"]["runtime_role_registry_changed"] is False
    assert body["summary"]["target_repository_changed"] is False
    after = runtime_snapshot(config_root)
    assert after["runtime/connectors.json"] != before["runtime/connectors.json"]
    assert after["runtime/tools.json"] == before["runtime/tools.json"]
    assert after["runtime/workflows.json"] == before["runtime/workflows.json"]
    assert after["runtime/roles.json"] == before["runtime/roles.json"]
    catalog = json.loads(after["runtime/connectors.json"])
    assert catalog["connectors"][0]["enabled"] is False


def test_connector_catalog_register_installs_enabled_connector_with_release_gate(tmp_path: Path) -> None:
    config_root = make_connector_catalog_root(tmp_path)
    release_report = write_release_gate_report(tmp_path)
    before = runtime_snapshot(config_root)
    status, body = register_connector(
        config_root,
        tmp_path,
        approval=connector_registration_approval(enabled=True),
        release_gate_report_path=release_report,
    )

    assert status == 200
    assert body["status"] == "completed"
    assert body["summary"]["enabled"] is True
    assert body["summary"]["release_gate_required"] is True
    assert body["summary"]["release_gate_passed"] is True
    assert body["summary"]["changed_runtime_files"] == ["runtime/connectors.json"]
    after = runtime_snapshot(config_root)
    assert after["runtime/connectors.json"] != before["runtime/connectors.json"]
    assert after["runtime/tools.json"] == before["runtime/tools.json"]
    assert after["runtime/workflows.json"] == before["runtime/workflows.json"]
    assert after["runtime/roles.json"] == before["runtime/roles.json"]

    status, invocation = invoke_connector(config_root, tmp_path)
    assert status == 200
    assert invocation["status"] == "completed"
    assert invocation["summary"]["connector_id"] == "ticketing_stub"


def test_connector_catalog_register_rejects_enablement_without_release_gate(tmp_path: Path) -> None:
    config_root = make_connector_catalog_root(tmp_path)
    before = runtime_snapshot(config_root)
    status, body = register_connector(
        config_root,
        tmp_path,
        approval=connector_registration_approval(enabled=True),
    )

    assert status == 403
    assert body["error"]["code"] == "missing_connector_release_gate_proof"
    assert runtime_snapshot(config_root) == before


def test_connector_catalog_register_rejects_missing_approval_without_mutation(tmp_path: Path) -> None:
    config_root = make_connector_catalog_root(tmp_path)
    before = runtime_snapshot(config_root)
    status, body = register_connector(config_root, tmp_path)

    assert status == 403
    assert body["error"]["code"] == "missing_connector_catalog_registration_approval"
    assert runtime_snapshot(config_root) == before


def test_connector_catalog_register_rejects_duplicate_without_mutation(tmp_path: Path) -> None:
    config_root = make_connector_catalog_root(tmp_path)
    install_connector(config_root, registered_stub_connector())
    before = runtime_snapshot(config_root)
    status, body = register_connector(
        config_root,
        tmp_path,
        approval=connector_registration_approval(enabled=False),
    )

    assert status == 422
    assert body["error"]["code"] == "connector_already_registered"
    assert runtime_snapshot(config_root) == before


def test_connector_catalog_register_rejects_release_gate_mismatch_without_mutation(tmp_path: Path) -> None:
    config_root = make_connector_catalog_root(tmp_path)
    release_report = write_release_gate_report(tmp_path, connector_id="other_stub")
    before = runtime_snapshot(config_root)
    status, body = register_connector(
        config_root,
        tmp_path,
        approval=connector_registration_approval(enabled=True),
        release_gate_report_path=release_report,
    )

    assert status == 403
    assert body["error"]["code"] == "connector_release_gate_mismatch"
    assert runtime_snapshot(config_root) == before
