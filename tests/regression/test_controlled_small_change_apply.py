from __future__ import annotations

import hashlib
import http.client
import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from vllm_agent_gateway.controller_service.server import ControllerServiceConfig, create_server
from vllm_agent_gateway.controllers.workflow_router import plan as workflow_router_plan


REPO_ROOT = Path(__file__).resolve().parents[2]
EXTERNAL_COINBASE_GITHUB_TARGET = Path("C:/coinbase_testing_repo_frozen_tmp.github")
FROZEN_INVARIANT_OLD = (
    "- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\n"
    "  maps, dashboard references, follow-up claims, fill ledger ownership, and DB\n"
    "  local rows."
)
FROZEN_INVARIANT_NEW = (
    "- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\n"
    "  maps, dashboard references, follow-up claims, fill ledger ownership, DB\n"
    "  local rows, and stealth manager placed-order index keys."
)


class RunningControllerService:
    def __init__(self, config: ControllerServiceConfig):
        self.server = create_server(config)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> "RunningControllerService":
        self.thread.start()
        time.sleep(0.05)
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    @property
    def host(self) -> str:
        return str(self.server.server_address[0])

    @property
    def port(self) -> int:
        return int(self.server.server_address[1])


def request_json(
    host: str,
    port: int,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    data = json.dumps(body or {}).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    last_error: OSError | None = None
    for _attempt in range(20):
        connection = http.client.HTTPConnection(host, port, timeout=20)
        try:
            connection.request(method, path, body=data, headers=headers)
            response = connection.getresponse()
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw)
        except OSError as exc:
            last_error = exc
            time.sleep(0.05)
        finally:
            connection.close()
    assert last_error is not None
    raise last_error


def run_command(args: list[str], cwd: Path, *, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_target_repo(tmp_path: Path) -> Path:
    target = tmp_path / "target"
    target.mkdir()
    write_text(target / "README.md", "# Project\n\nInstall with Docker.\n")
    write_text(target / "docs" / "guide.md", "# Guide\n\nOriginal guide text.\n")
    write_text(
        target / "tests" / "test_docs.py",
        "from pathlib import Path\n\n\ndef test_readme_exists():\n    assert Path('README.md').exists()\n",
    )
    assert run_command(["git", "init"], target).returncode == 0
    assert run_command(["git", "add", "README.md", "docs/guide.md", "tests/test_docs.py"], target).returncode == 0
    return target


def controller_config(tmp_path: Path, *allowed_roots: Path) -> ControllerServiceConfig:
    return ControllerServiceConfig(
        config_root=REPO_ROOT,
        output_root=tmp_path / "controller-state",
        allowed_target_roots=tuple(root.resolve() for root in allowed_roots),
        host="127.0.0.1",
        port=0,
    )


def dry_run_approval() -> dict[str, Any]:
    return {
        "status": "approved_for_small_change_dry_run",
        "scope": "controlled_small_change_preview",
        "apply_allowed": False,
        "approval_refs": ["phase54-test-dry-run"],
    }


def real_apply_approval() -> dict[str, Any]:
    return {
        "status": "approved_for_real_apply",
        "scope": "controlled_small_change_apply",
        "apply_allowed": True,
        "apply_scope": "target_root",
        "explicit_real_apply": True,
        "approval_refs": ["phase54-test-real-apply"],
    }


def disposable_apply_approval() -> dict[str, Any]:
    return {
        "status": "approved_for_disposable_apply",
        "scope": "workflow_router_disposable_copy",
        "apply_allowed": True,
        "apply_scope": "disposable_copy_only",
        "approval_refs": ["phase54-test-disposable-apply"],
    }


def readme_replace_operation() -> dict[str, Any]:
    return {
        "kind": "replace_text",
        "path": "README.md",
        "old": "Install with Docker.",
        "new": "Install with Docker or Podman.",
    }


def readme_append_operation(marker: str = "Phase 98 README append") -> dict[str, Any]:
    return {
        "kind": "append_text",
        "path": "README.md",
        "content": f"\n<!-- {marker} -->\n",
    }


def guide_append_operation(marker: str = "Phase 98 guide append") -> dict[str, Any]:
    return {
        "kind": "append_text",
        "path": "docs/guide.md",
        "content": f"\n<!-- {marker} -->\n",
    }


def create_file_operation() -> dict[str, Any]:
    return {
        "kind": "create_file",
        "path": "docs/new-phase98-file.md",
        "content": "# New file\n",
    }


def pytest_verification() -> list[dict[str, Any]]:
    return [
        {
            "id": "pytest:tests",
            "command": [sys.executable, "-m", "pytest", "tests"],
            "timeout_seconds": 60,
            "associated_files": ["tests"],
        }
    ]


def implementation_payload(
    target: Path,
    *,
    mode: str,
    approval: dict[str, Any],
    packet_operations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "workflow": "implementation.workflow",
        "schema_version": 1,
        "target_root": str(target),
        "mode": mode,
        "approval": approval,
        "packet_operations": packet_operations if packet_operations is not None else [readme_replace_operation()],
        "verification_commands": pytest_verification(),
        "no_structure_index": True,
    }


def test_controlled_implementation_dry_run_creates_patch_preview_without_mutation(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    before = (target / "README.md").read_text(encoding="utf-8")
    with RunningControllerService(controller_config(tmp_path, target)) as service:
        status, body = request_json(
            service.host,
            service.port,
            "POST",
            "/v1/controller/implementation-runs",
            implementation_payload(target, mode="dry_run", approval=dry_run_approval()),
        )

    assert status == 200
    assert body["workflow"] == "implementation.workflow"
    assert body["summary"]["mode"] == "draft"
    assert body["summary"]["target_repository_changed"] is False
    assert body["summary"]["patch_preview_count"] == 1
    assert (target / "README.md").read_text(encoding="utf-8") == before
    report = json.loads(Path(body["artifacts"]["implementation_report"]).read_text(encoding="utf-8"))
    patch_path = Path(report["changed_artifacts"][0]["patch_preview"])
    assert patch_path.exists()
    patch_text = patch_path.read_text(encoding="utf-8")
    assert "--- a/README.md" in patch_text
    assert "+++ b/README.md" in patch_text


def test_controlled_implementation_real_apply_requires_explicit_approval(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    before = (target / "README.md").read_text(encoding="utf-8")
    with RunningControllerService(controller_config(tmp_path, target)) as service:
        status, body = request_json(
            service.host,
            service.port,
            "POST",
            "/v1/controller/implementation-runs",
            implementation_payload(target, mode="apply", approval=dry_run_approval()),
        )

    assert status == 403
    assert body["error"]["code"] == "real_apply_approval_required"
    assert (target / "README.md").read_text(encoding="utf-8") == before


def test_controlled_implementation_real_apply_modifies_only_allowed_tracked_file_and_verifies(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    guide_before = sha256_file(target / "docs" / "guide.md")
    with RunningControllerService(controller_config(tmp_path, target)) as service:
        status, body = request_json(
            service.host,
            service.port,
            "POST",
            "/v1/controller/implementation-runs",
            implementation_payload(target, mode="real_apply", approval=real_apply_approval()),
        )

    assert status == 200
    assert body["summary"]["mode"] == "apply"
    assert body["summary"]["target_repository_changed"] is True
    assert body["summary"]["modified_targets"] == ["README.md"]
    assert body["summary"]["patch_preview_count"] == 1
    assert body["summary"]["rollback_operation_count"] == 1
    assert body["summary"]["verification_statuses"] == ["passed"]
    assert "Install with Docker or Podman." in (target / "README.md").read_text(encoding="utf-8")
    assert sha256_file(target / "docs" / "guide.md") == guide_before
    report = json.loads(Path(body["artifacts"]["implementation_report"]).read_text(encoding="utf-8"))
    changed = report["changed_artifacts"][0]
    assert Path(changed["patch_preview"]).exists()
    assert changed["rollback_operation"]["kind"] == "replace_text"


def test_controlled_implementation_rejects_out_of_scope_packet_path(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    before = (target / "README.md").read_text(encoding="utf-8")
    operation = {
        "kind": "replace_text",
        "path": "../outside.md",
        "old": "anything",
        "new": "nope",
    }
    with RunningControllerService(controller_config(tmp_path, target)) as service:
        status, body = request_json(
            service.host,
            service.port,
            "POST",
            "/v1/controller/implementation-runs",
            implementation_payload(
                target,
                mode="dry_run",
                approval=dry_run_approval(),
                packet_operations=[operation],
            ),
        )

    assert status == 422
    assert body["error"]["code"] == "implementation_workflow_error"
    assert "outside target root" in body["error"]["message"]
    assert (target / "README.md").read_text(encoding="utf-8") == before


def test_controlled_implementation_rejects_real_apply_to_protected_frozen_root(tmp_path: Path) -> None:
    if not EXTERNAL_COINBASE_GITHUB_TARGET.exists():
        pytest.skip(f"External frozen Coinbase fixture is not present: {EXTERNAL_COINBASE_GITHUB_TARGET}")
    invariant = EXTERNAL_COINBASE_GITHUB_TARGET / "docs" / "agents" / "INVARIANTS.md"
    before = invariant.read_text(encoding="utf-8")
    assert FROZEN_INVARIANT_OLD in before
    git_before = run_command(["git", "status", "--short"], EXTERNAL_COINBASE_GITHUB_TARGET)
    operation = {
        "kind": "replace_text",
        "path": "docs/agents/INVARIANTS.md",
        "old": FROZEN_INVARIANT_OLD,
        "new": FROZEN_INVARIANT_NEW,
    }

    with RunningControllerService(controller_config(tmp_path, EXTERNAL_COINBASE_GITHUB_TARGET)) as service:
        status, body = request_json(
            service.host,
            service.port,
            "POST",
            "/v1/controller/implementation-runs",
            implementation_payload(
                EXTERNAL_COINBASE_GITHUB_TARGET,
                mode="apply",
                approval=real_apply_approval(),
                packet_operations=[operation],
            ),
        )

    assert status == 403
    assert body["error"]["code"] == "protected_frozen_real_apply_denied"
    assert invariant.read_text(encoding="utf-8") == before
    git_after = run_command(["git", "status", "--short"], EXTERNAL_COINBASE_GITHUB_TARGET)
    assert git_after.stdout == git_before.stdout


def test_workflow_router_disposable_apply_rolls_back_copy_after_mutation_proof(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    source_before = (target / "README.md").read_text(encoding="utf-8")
    with RunningControllerService(controller_config(tmp_path, target)) as service:
        status, body = request_json(
            service.host,
            service.port,
            "POST",
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "schema_version": 1,
                "target_root": str(target),
                "user_request": "Apply this approved small text edit only to a disposable copy.",
                "mode": "apply_disposable_copy",
                "approval": disposable_apply_approval(),
                "packet_operations": [readme_replace_operation()],
                "budgets": {"max_model_calls": 0},
            },
        )

    assert status == 200
    assert body["summary"]["downstream_workflow"] == "implementation.workflow"
    assert body["summary"]["source_changed"] is False
    assert body["summary"]["disposable_copy_changed"] is True
    assert body["summary"]["approval_state_status"] == "finished"
    assert body["summary"]["approval_type"] == "disposable_copy_apply"
    assert (target / "README.md").read_text(encoding="utf-8") == source_before
    decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    approval_state = json.loads(Path(body["artifacts"]["approval_state"]).read_text(encoding="utf-8"))
    assert approval_state["status"] == "finished"
    assert approval_state["approval_type"] == "disposable_copy_apply"
    proof = decision["disposable_apply"]["mutation_proof"]
    assert body["summary"]["mutation_sandbox_status"] == "active"
    assert body["summary"]["mutation_diff_file_count"] == 1
    assert body["summary"]["mutation_rollback_status"] == "restored"
    assert "disposable_mutation_proof" in body["artifacts"]
    assert "disposable_mutation_sandbox_contract" in body["artifacts"]
    assert "disposable_mutation_diff" in body["artifacts"]
    assert proof["source_changed"] == {}
    assert proof["copy_changed"]["README.md"]["before"] != proof["copy_changed"]["README.md"]["after"]
    assert proof["kind"] == "disposable_mutation_proof"
    assert proof["sandbox_contract"]["status"] == "active"
    assert proof["sandbox_contract"]["allowed_write_root"] == proof["disposable_copy_root"]
    assert proof["structured_diff"]["changed_file_count"] == 1
    assert proof["structured_diff"]["records"][0]["path"] == "README.md"
    assert proof["structured_diff"]["records"][0]["status"] == "changed"
    assert proof["rollback"]["status"] == "restored"
    assert Path(proof["rollback"]["artifact"]).exists()
    assert Path(proof["artifact"]).exists()
    copy_root = Path(proof["disposable_copy_root"])
    assert (copy_root / "README.md").read_text(encoding="utf-8") == source_before


def test_workflow_router_disposable_apply_supports_append_text_with_tree_proof(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    source_before = (target / "README.md").read_text(encoding="utf-8")
    with RunningControllerService(controller_config(tmp_path, target)) as service:
        status, body = request_json(
            service.host,
            service.port,
            "POST",
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "schema_version": 1,
                "target_root": str(target),
                "user_request": "Apply this approved append only to a disposable copy.",
                "mode": "apply_disposable_copy",
                "approval": disposable_apply_approval(),
                "packet_operations": [readme_append_operation()],
                "budgets": {"max_model_calls": 0},
            },
        )

    assert status == 200
    assert body["summary"]["source_changed"] is False
    assert body["summary"]["source_tree_changed"] is False
    assert body["summary"]["disposable_copy_changed"] is True
    assert body["summary"]["copy_tree_restored"] is True
    assert body["summary"]["mutation_diff_file_count"] == 1
    assert body["summary"]["mutation_diff_paths"] == ["README.md"]
    assert body["summary"]["mutation_operation_kinds"] == ["append_text"]
    assert body["summary"]["mutation_rollback_status"] == "restored"
    assert (target / "README.md").read_text(encoding="utf-8") == source_before
    decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    proof = decision["disposable_apply"]["mutation_proof"]
    assert proof["source_tree_changed"] is False
    assert proof["copy_tree_restored"] is True
    assert proof["structured_diff"]["records"][0]["operation_kind"] == "append_text"
    assert proof["structured_diff"]["records"][0]["added_line_count"] >= 1
    copy_root = Path(proof["disposable_copy_root"])
    assert (copy_root / "README.md").read_text(encoding="utf-8") == source_before


def test_workflow_router_disposable_apply_supports_multi_operation_rollback(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    readme_before = (target / "README.md").read_text(encoding="utf-8")
    guide_before = (target / "docs" / "guide.md").read_text(encoding="utf-8")
    operations = [readme_replace_operation(), guide_append_operation()]

    with RunningControllerService(controller_config(tmp_path, target)) as service:
        status, body = request_json(
            service.host,
            service.port,
            "POST",
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "schema_version": 1,
                "target_root": str(target),
                "user_request": "Apply these approved packet operations only to a disposable copy.",
                "mode": "apply_disposable_copy",
                "approval": disposable_apply_approval(),
                "packet_operations": operations,
                "budgets": {"max_model_calls": 0},
            },
        )

    assert status == 200
    assert body["summary"]["source_changed"] is False
    assert body["summary"]["source_tree_changed"] is False
    assert body["summary"]["disposable_copy_changed"] is True
    assert body["summary"]["copy_tree_restored"] is True
    assert body["summary"]["mutation_diff_file_count"] == 2
    assert sorted(body["summary"]["mutation_diff_paths"]) == ["README.md", "docs/guide.md"]
    assert body["summary"]["mutation_operation_kinds"] == ["replace_text", "append_text"]
    assert (target / "README.md").read_text(encoding="utf-8") == readme_before
    assert (target / "docs" / "guide.md").read_text(encoding="utf-8") == guide_before
    proof = json.loads(Path(body["artifacts"]["disposable_mutation_proof"]).read_text(encoding="utf-8"))
    structured = proof["structured_diff"]
    assert structured["changed_file_count"] == 2
    records = {record["path"]: record for record in structured["records"]}
    assert records["README.md"]["operation_kind"] == "replace_text"
    assert records["docs/guide.md"]["operation_kind"] == "append_text"
    assert set(proof["rollback"]["backup_artifacts"]) == {"README.md", "docs/guide.md"}
    copy_root = Path(proof["disposable_copy_root"])
    assert (copy_root / "README.md").read_text(encoding="utf-8") == readme_before
    assert (copy_root / "docs" / "guide.md").read_text(encoding="utf-8") == guide_before


def test_workflow_router_disposable_apply_refuses_create_file_apply(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    with RunningControllerService(controller_config(tmp_path, target)) as service:
        status, body = request_json(
            service.host,
            service.port,
            "POST",
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "schema_version": 1,
                "target_root": str(target),
                "user_request": "Apply this approved create_file operation only to a disposable copy.",
                "mode": "apply_disposable_copy",
                "approval": disposable_apply_approval(),
                "packet_operations": [create_file_operation()],
                "budgets": {"max_model_calls": 0},
            },
        )

    assert status == 200
    assert body["summary"]["route_status"] == "blocked"
    assert body["summary"]["disposable_copy_changed"] is False
    decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    assert any(blocker["reason"] == "unsupported_disposable_operation_kind" for blocker in decision["blockers"])
    assert "disposable_mutation_proof" not in body["artifacts"]
    assert not (target / "docs" / "new-phase98-file.md").exists()


def test_workflow_router_disposable_apply_blocks_out_of_bounds_packet_path(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    source_before = (target / "README.md").read_text(encoding="utf-8")
    with RunningControllerService(controller_config(tmp_path, target)) as service:
        status, body = request_json(
            service.host,
            service.port,
            "POST",
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "schema_version": 1,
                "target_root": str(target),
                "user_request": "Apply this approved small text edit only to a disposable copy.",
                "mode": "apply_disposable_copy",
                "approval": disposable_apply_approval(),
                "packet_operations": [
                    {
                        "kind": "replace_text",
                        "path": "../outside.md",
                        "old": "anything",
                        "new": "nope",
                    }
                ],
                "budgets": {"max_model_calls": 0},
            },
        )

    assert status == 200
    assert body["summary"]["route_status"] == "blocked"
    assert body["summary"]["downstream_workflow"] is None
    assert body["summary"]["disposable_copy_changed"] is False
    assert body["summary"]["approval_state_status"] == "blocked"
    assert body["summary"]["approval_type"] == "disposable_copy_apply"
    assert (target / "README.md").read_text(encoding="utf-8") == source_before
    decision = json.loads(Path(body["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    approval_state = json.loads(Path(body["artifacts"]["approval_state"]).read_text(encoding="utf-8"))
    assert approval_state["status"] == "blocked"
    assert approval_state["approval_status"] == "approved"
    assert any(blocker["reason"] == "invalid_disposable_operation_path" for blocker in decision["blockers"])
    assert "disposable_mutation_proof" not in body["artifacts"]


def test_workflow_router_disposable_apply_cleanup_failure_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = make_target_repo(tmp_path)
    source_before = (target / "README.md").read_text(encoding="utf-8")

    def missing_backup_artifact(
        root: Path,
        packet_operations: list[dict[str, Any]],
        backup_dir: Path,
    ) -> dict[str, str]:
        return {"README.md": str(backup_dir / "missing-readme.bak")}

    monkeypatch.setattr(workflow_router_plan, "backup_operation_targets", missing_backup_artifact)
    with RunningControllerService(controller_config(tmp_path, target)) as service:
        status, body = request_json(
            service.host,
            service.port,
            "POST",
            "/v1/controller/workflow-router/plans",
            {
                "workflow": "workflow_router.plan",
                "schema_version": 1,
                "target_root": str(target),
                "user_request": "Apply this approved small text edit only to a disposable copy.",
                "mode": "apply_disposable_copy",
                "approval": disposable_apply_approval(),
                "packet_operations": [readme_replace_operation()],
                "budgets": {"max_model_calls": 0},
            },
        )

    assert status == 422
    assert body["error"]["code"] == "disposable_copy_rollback_failed"
    assert (target / "README.md").read_text(encoding="utf-8") == source_before
    proof_paths = sorted((tmp_path / "controller-state").glob("workflow-router/**/disposable-mutation-proof.json"))
    assert len(proof_paths) == 1
    proof = json.loads(proof_paths[0].read_text(encoding="utf-8"))
    assert proof["source_changed"] == {}
    assert proof["copy_changed"]["README.md"]["before"] != proof["copy_changed"]["README.md"]["after"]
    assert proof["rollback"]["status"] == "failed"
    assert proof["rollback"]["blockers"][0]["reason"] == "missing_rollback_backup"


def test_natural_workflow_router_disposable_apply_requires_exact_packet_json_and_rolls_back(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    source_before = (target / "README.md").read_text(encoding="utf-8")
    packet_json = json.dumps({"packet_operations": [readme_replace_operation()]}, ensure_ascii=True)
    message = (
        f"In {target}, approved disposable copy apply only. Apply these exact packet_operations "
        f"to a disposable copy and do not mutate the source repo: {packet_json}"
    )

    with RunningControllerService(controller_config(tmp_path, target)) as service:
        status, body = request_json(
            service.host,
            service.port,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [{"role": "user", "content": message}],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    assert compact["summary"]["downstream_workflow"] == "implementation.workflow"
    assert compact["summary"]["source_changed"] is False
    assert compact["summary"]["disposable_copy_changed"] is True
    assert (target / "README.md").read_text(encoding="utf-8") == source_before
    content = body["choices"][0]["message"]["content"]
    assert "workflow_router.plan completed" in content
    assert "- source_changed: False" in content
    assert "- source_tree_changed: False" in content
    assert "- mutation_diff_file_count: 1" in content
    assert "Disposable Apply:" in content
    assert "- Changed files: 1" in content
    assert "README.md (replace_text" in content
    decision = json.loads(Path(compact["artifacts"]["route_decision"]).read_text(encoding="utf-8"))
    proof = decision["disposable_apply"]["mutation_proof"]
    assert proof["rollback"]["status"] == "restored"
    assert (Path(proof["disposable_copy_root"]) / "README.md").read_text(encoding="utf-8") == source_before


def test_natural_workflow_router_disposable_apply_accepts_copy_only_exact_packet_language(tmp_path: Path) -> None:
    target = make_target_repo(tmp_path)
    source_before = (target / "README.md").read_text(encoding="utf-8")
    packet_json = json.dumps({"packet_operations": [readme_replace_operation()]}, ensure_ascii=True)
    message = (
        f"In {target}, apply this exact packet only to a disposable copy and prove the source repo did not change: "
        f"{packet_json}"
    )

    with RunningControllerService(controller_config(tmp_path, target)) as service:
        status, body = request_json(
            service.host,
            service.port,
            "POST",
            "/v1/controller/workflow-router/chat/completions",
            {
                "model": "agentic-workflow-router",
                "messages": [{"role": "user", "content": message}],
            },
        )

    assert status == 200
    compact = body["agentic_controller_response"]
    assert compact["summary"]["downstream_workflow"] == "implementation.workflow"
    assert compact["summary"]["source_changed"] is False
    assert compact["summary"]["disposable_copy_changed"] is True
    assert (target / "README.md").read_text(encoding="utf-8") == source_before
    content = body["choices"][0]["message"]["content"]
    assert "workflow_router.plan completed" in content
    assert "- source_changed: False" in content
    assert "- source_tree_changed: False" in content
    assert "- disposable_copy_changed: True" in content
    assert "Disposable Apply:" in content
