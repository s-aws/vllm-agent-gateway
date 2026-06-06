#!/usr/bin/env python3
"""Validate Phase 54 controlled small-change apply against the live local stack."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_CONTROLLER_BASE_URL = "http://127.0.0.1:8400"
DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL = "http://127.0.0.1:8500/v1"
DEFAULT_ANYTHINGLLM_API_BASE_URL = "http://127.0.0.1:3001"
DEFAULT_WORKSPACE = "my-workspace"
DEFAULT_CONFIG_ROOT = "/mnt/c/agentic_agents"
DEFAULT_CONTROLLER_ARTIFACT_ROOT = "/mnt/c/private_agentic_agents/runtime-state/controller-artifacts"
DEFAULT_REPORT_PATH = "runtime-state/controlled-small-change-apply/phase54-live.json"
DEFAULT_TARGET_ROOTS = [
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
]
PORT_HEALTH_PROBES = [
    ("localhost-model", "http://127.0.0.1:8000/v1/models"),
    ("llm-gateway", "http://127.0.0.1:8300/v1/models"),
    ("controller", "http://127.0.0.1:8400/health"),
    ("workflow-router-gateway", "http://127.0.0.1:8500/v1/models"),
    ("reviewer-code", "http://127.0.0.1:8101/v1/models"),
    ("tester-code", "http://127.0.0.1:8102/v1/models"),
    ("architect-default", "http://127.0.0.1:8201/v1/models"),
    ("dispatcher-default", "http://127.0.0.1:8202/v1/models"),
    ("implementer-default", "http://127.0.0.1:8203/v1/models"),
    ("researcher-default", "http://127.0.0.1:8204/v1/models"),
    ("documenter-default", "http://127.0.0.1:8205/v1/models"),
]
WATCHED_RUNTIME_FILES = [
    "runtime/workflows.json",
    "runtime/skills.json",
    "runtime/tools.json",
]
WATCHED_TARGET_FILES = [
    "core/stealth_order_manager.py",
    "tests/unit/test_order_id_and_followup_rules.py",
    "docs/agents/INVARIANTS.md",
]
RUN_ID_RE = re.compile(r"\brun_id:\s*(?P<run_id>workflow-router-\d{8}T\d+Z)\b")
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


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def json_request(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout_seconds: int,
    method: str = "POST",
) -> tuple[int, dict[str, Any]]:
    request_headers = dict(headers or {})
    data = None
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            text = response.read().decode("utf-8")
            return response.status, json.loads(text) if text else {}
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(text)
        except json.JSONDecodeError:
            body = {"error": {"message": text, "code": "invalid_json_error_body"}}
        return exc.code, body


def text_response(body: dict[str, Any]) -> str:
    for key in ("textResponse", "response", "message"):
        value = body.get(key)
        if isinstance(value, str):
            return value
    choices = body.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                return message["content"]
    raise RuntimeError("response did not include assistant text")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def watched_hashes(root: Path, relatives: list[str]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative in relatives:
        path = root / relative
        if path.exists():
            hashes[relative] = sha256_file(path)
    if not hashes:
        raise RuntimeError(f"{root} did not contain watched files")
    return hashes


def changed_hashes(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(key for key, value in after.items() if before.get(key) != value)


def git_status(root: Path) -> str | None:
    if not (root / ".git").exists():
        return None
    result = subprocess.run(["git", "-C", str(root), "status", "--short"], check=True, capture_output=True, text=True)
    return result.stdout


def validate_no_target_mutation(root: Path, before_hashes: dict[str, str], before_status: str | None, label: str) -> None:
    changed = changed_hashes(before_hashes, watched_hashes(root, WATCHED_TARGET_FILES))
    if changed:
        raise RuntimeError(f"{label} mutated watched files for {root}: {changed}")
    after_status = git_status(root)
    if before_status is not None and after_status != before_status:
        raise RuntimeError(f"{label} changed git status for {root}: {after_status!r}")


def validate_port_health(timeout_seconds: int) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for label, url in PORT_HEALTH_PROBES:
        status, body = json_request(url, timeout_seconds=timeout_seconds, method="GET")
        if status != 200:
            raise RuntimeError(f"{label} health probe returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
        checks.append({"label": label, "url": url, "status": "passed"})
        print(f"PHASE54 PORT PASS label={label} url={url}")
    return checks


def packet_operation() -> dict[str, Any]:
    return {
        "kind": "replace_text",
        "path": "docs/agents/INVARIANTS.md",
        "old": FROZEN_INVARIANT_OLD,
        "new": FROZEN_INVARIANT_NEW,
    }


def dry_run_approval() -> dict[str, Any]:
    return {
        "status": "approved_for_small_change_dry_run",
        "scope": "phase54_live_patch_preview",
        "apply_allowed": False,
        "approval_refs": ["phase54-live-dry-run"],
    }


def real_apply_approval() -> dict[str, Any]:
    return {
        "status": "approved_for_real_apply",
        "scope": "phase54_live_protected_apply_boundary",
        "apply_allowed": True,
        "apply_scope": "target_root",
        "explicit_real_apply": True,
        "approval_refs": ["phase54-live-real-apply-boundary"],
    }


def implementation_payload(target_root: str, *, mode: str, approval: dict[str, Any]) -> dict[str, Any]:
    return {
        "workflow": "implementation.workflow",
        "schema_version": 1,
        "target_root": target_root,
        "mode": mode,
        "approval": approval,
        "packet_operations": [packet_operation()],
        "no_structure_index": True,
    }


def natural_apply_message(target_root: str) -> str:
    packet_json = json.dumps({"packet_operations": [packet_operation()]}, ensure_ascii=True)
    return (
        f"In {target_root}, approved disposable copy apply only. Apply these exact packet_operations "
        f"to a disposable copy and do not mutate the source repo: {packet_json}"
    )


def gateway_payload(target_root: str) -> dict[str, Any]:
    return {
        "model": "agentic-workflow-router",
        "messages": [{"role": "user", "content": natural_apply_message(target_root)}],
    }


def anythingllm_payload(target_root: str) -> dict[str, Any]:
    return {
        "message": natural_apply_message(target_root),
        "mode": "chat",
        "sessionId": f"controlled-small-change-apply-{uuid.uuid4().hex}",
    }


def require_direct_dry_run(body: dict[str, Any], target_root: str) -> str:
    summary = body.get("summary")
    if not isinstance(summary, dict):
        raise RuntimeError("direct dry-run response did not include summary")
    expected = {
        "mode": "draft",
        "target_repository_changed": False,
        "patch_preview_count": 1,
    }
    wrong = {
        key: {"expected": expected_value, "actual": summary.get(key)}
        for key, expected_value in expected.items()
        if summary.get(key) != expected_value
    }
    if wrong:
        raise RuntimeError(f"direct dry-run summary mismatch for {target_root}: {json.dumps(wrong, sort_keys=True)}")
    artifacts = body.get("artifacts")
    if not isinstance(artifacts, dict) or "implementation_report" not in artifacts:
        raise RuntimeError(f"direct dry-run missing implementation_report for {target_root}")
    report = json.loads(Path(artifacts["implementation_report"]).read_text(encoding="utf-8"))
    patch_path = Path(report["changed_artifacts"][0]["patch_preview"])
    if not patch_path.exists():
        raise RuntimeError(f"direct dry-run patch preview was not written for {target_root}: {patch_path}")
    patch_text = patch_path.read_text(encoding="utf-8")
    if "--- a/docs/agents/INVARIANTS.md" not in patch_text or "+++ b/docs/agents/INVARIANTS.md" not in patch_text:
        raise RuntimeError(f"direct dry-run patch preview missing diff markers for {target_root}")
    return str(patch_path)


def require_protected_apply_refusal(body: dict[str, Any], status: int, target_root: str) -> None:
    if status != 403:
        raise RuntimeError(f"protected real apply should return 403 for {target_root}, got HTTP {status}: {body}")
    error = body.get("error") if isinstance(body.get("error"), dict) else {}
    if error.get("code") != "protected_frozen_real_apply_denied":
        raise RuntimeError(f"protected real apply returned wrong error for {target_root}: {json.dumps(body, sort_keys=True)}")


def require_route_decision_proof(decision: dict[str, Any], target_root: str, label: str) -> dict[str, Any]:
    approval_state = decision.get("approval_state")
    if not isinstance(approval_state, dict):
        raise RuntimeError(f"{label} route decision missing approval_state for {target_root}")
    expected_approval = {
        "status": "finished",
        "approval_type": "disposable_copy_apply",
        "approval_status": "approved",
        "target_root": str(Path(target_root).resolve()),
    }
    wrong_approval = {
        key: {"expected": expected_value, "actual": approval_state.get(key)}
        for key, expected_value in expected_approval.items()
        if approval_state.get(key) != expected_value
    }
    if wrong_approval:
        raise RuntimeError(f"{label} approval_state mismatch for {target_root}: {json.dumps(wrong_approval, sort_keys=True)}")
    disposable_apply = decision.get("disposable_apply")
    if not isinstance(disposable_apply, dict):
        raise RuntimeError(f"{label} route decision missing disposable_apply for {target_root}")
    if disposable_apply.get("workflow") != "implementation.workflow" or disposable_apply.get("status") != "completed":
        raise RuntimeError(f"{label} disposable_apply status mismatch for {target_root}: {json.dumps(disposable_apply, sort_keys=True)}")
    proof = disposable_apply.get("mutation_proof")
    if not isinstance(proof, dict):
        raise RuntimeError(f"{label} missing mutation proof for {target_root}")
    if proof.get("kind") != "disposable_mutation_proof":
        raise RuntimeError(f"{label} mutation proof kind mismatch for {target_root}: {proof.get('kind')!r}")
    proof_artifact = proof.get("artifact")
    if not isinstance(proof_artifact, str) or not Path(proof_artifact).exists():
        raise RuntimeError(f"{label} mutation proof artifact missing for {target_root}: {proof_artifact!r}")
    sandbox_contract = proof.get("sandbox_contract")
    if not isinstance(sandbox_contract, dict) or sandbox_contract.get("status") != "active":
        raise RuntimeError(f"{label} sandbox contract missing or inactive for {target_root}: {json.dumps(sandbox_contract, sort_keys=True)}")
    contract_artifact = sandbox_contract.get("artifact")
    if not isinstance(contract_artifact, str) or not Path(contract_artifact).exists():
        raise RuntimeError(f"{label} sandbox contract artifact missing for {target_root}: {contract_artifact!r}")
    structured_diff = proof.get("structured_diff")
    if not isinstance(structured_diff, dict) or structured_diff.get("changed_file_count") != 1:
        raise RuntimeError(f"{label} structured diff proof mismatch for {target_root}: {json.dumps(structured_diff, sort_keys=True)}")
    diff_artifact = structured_diff.get("artifact")
    if not isinstance(diff_artifact, str) or not Path(diff_artifact).exists():
        raise RuntimeError(f"{label} structured diff artifact missing for {target_root}: {diff_artifact!r}")
    records = structured_diff.get("records")
    if not isinstance(records, list) or not records or records[0].get("path") != "docs/agents/INVARIANTS.md":
        raise RuntimeError(f"{label} structured diff records missing target file for {target_root}: {json.dumps(records, sort_keys=True)}")
    if proof.get("source_changed") != {}:
        raise RuntimeError(f"{label} source changed for {target_root}: {json.dumps(proof.get('source_changed'), sort_keys=True)}")
    copy_changed = proof.get("copy_changed")
    if not isinstance(copy_changed, dict) or "docs/agents/INVARIANTS.md" not in copy_changed:
        raise RuntimeError(f"{label} copy mutation proof missing target file for {target_root}: {json.dumps(proof, sort_keys=True)}")
    rollback = proof.get("rollback")
    if not isinstance(rollback, dict) or rollback.get("status") != "restored":
        raise RuntimeError(f"{label} rollback did not restore disposable copy for {target_root}: {json.dumps(rollback, sort_keys=True)}")
    rollback_artifact = rollback.get("artifact")
    if not isinstance(rollback_artifact, str) or not Path(rollback_artifact).exists():
        raise RuntimeError(f"{label} rollback artifact missing for {target_root}: {rollback_artifact!r}")
    copy_root = proof.get("disposable_copy_root")
    if not isinstance(copy_root, str):
        raise RuntimeError(f"{label} mutation proof missing disposable_copy_root for {target_root}")
    copy_text = (Path(copy_root) / "docs" / "agents" / "INVARIANTS.md").read_text(encoding="utf-8")
    if FROZEN_INVARIANT_OLD not in copy_text or FROZEN_INVARIANT_NEW in copy_text:
        raise RuntimeError(f"{label} disposable copy was not restored for {target_root}")
    return proof


def require_gateway_response(body: dict[str, Any], target_root: str) -> dict[str, Any]:
    text = text_response(body)
    required_markers = [
        "workflow_router.plan completed",
        "- downstream_workflow: implementation.workflow",
        "- source_changed: False",
        "- disposable_copy_changed: True",
        "Approval:",
        "- State: finished",
        "- Type: disposable_copy_apply",
        "Skill Selection:",
        "- Why: Selected execution_planning.plan",
        "disposable_apply_terms",
    ]
    missing = [marker for marker in required_markers if marker not in text]
    if missing:
        raise RuntimeError(f"gateway missing FormatA markers for {target_root}: {missing}")
    compact = body.get("agentic_controller_response")
    if not isinstance(compact, dict):
        raise RuntimeError(f"gateway missing agentic_controller_response for {target_root}")
    summary = compact.get("summary")
    if not isinstance(summary, dict) or summary.get("downstream_workflow") != "implementation.workflow":
        raise RuntimeError(f"gateway summary mismatch for {target_root}: {json.dumps(summary, sort_keys=True)}")
    if summary.get("source_changed") is not False or summary.get("disposable_copy_changed") is not True:
        raise RuntimeError(f"gateway mutation summary mismatch for {target_root}: {json.dumps(summary, sort_keys=True)}")
    if summary.get("approval_state_status") != "finished" or summary.get("approval_type") != "disposable_copy_apply":
        raise RuntimeError(f"gateway approval summary mismatch for {target_root}: {json.dumps(summary, sort_keys=True)}")
    artifacts = compact.get("artifacts")
    if not isinstance(artifacts, dict) or "route_decision" not in artifacts:
        raise RuntimeError(f"gateway missing route_decision artifact for {target_root}")
    for artifact_key in (
        "disposable_mutation_proof",
        "disposable_mutation_sandbox_contract",
        "disposable_mutation_diff",
        "disposable_rollback_proof",
        "approval_state",
    ):
        artifact_path = artifacts.get(artifact_key)
        if not isinstance(artifact_path, str) or not Path(artifact_path).exists():
            raise RuntimeError(f"gateway missing {artifact_key} artifact for {target_root}: {artifact_path!r}")
    approval_state = json.loads(Path(artifacts["approval_state"]).read_text(encoding="utf-8"))
    if approval_state.get("status") != "finished" or approval_state.get("approval_type") != "disposable_copy_apply":
        raise RuntimeError(f"gateway approval_state artifact mismatch for {target_root}: {json.dumps(approval_state, sort_keys=True)}")
    decision = json.loads(Path(artifacts["route_decision"]).read_text(encoding="utf-8"))
    proof = require_route_decision_proof(decision, target_root, "gateway")
    return {"run_id": compact.get("run_id"), "proof": proof}


def run_id_from_text(text: str) -> str:
    match = RUN_ID_RE.search(text)
    if not match:
        raise RuntimeError(f"response did not include workflow-router run_id: {text[:800]}")
    return match.group("run_id")


def route_decision_for_run(artifact_root: Path, run_id: str) -> Path:
    direct = artifact_root / "workflow-router" / run_id / "route-decision.json"
    if direct.exists():
        return direct
    matches = sorted(artifact_root.glob(f"**/{run_id}/route-decision.json"))
    if matches:
        return matches[-1]
    raise RuntimeError(f"could not locate route-decision.json for run_id={run_id} under {artifact_root}")


def require_anythingllm_response(body: dict[str, Any], target_root: str, artifact_root: Path) -> dict[str, Any]:
    text = text_response(body)
    required_markers = [
        "workflow_router.plan completed",
        "- downstream_workflow: implementation.workflow",
        "- source_changed: False",
        "- disposable_copy_changed: True",
        "Approval:",
        "- State: finished",
        "- Type: disposable_copy_apply",
        "Skill Selection:",
        "- Why: Selected execution_planning.plan",
        "disposable_apply_terms",
    ]
    missing = [marker for marker in required_markers if marker not in text]
    if missing:
        raise RuntimeError(f"AnythingLLM missing FormatA markers for {target_root}: {missing}")
    run_id = run_id_from_text(text)
    decision_path = route_decision_for_run(artifact_root, run_id)
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    approval_state_path = decision_path.parent / "approval-state.json"
    if not approval_state_path.exists():
        raise RuntimeError(f"AnythingLLM missing approval-state.json for {target_root}: {approval_state_path}")
    approval_state = json.loads(approval_state_path.read_text(encoding="utf-8"))
    if approval_state.get("status") != "finished" or approval_state.get("approval_type") != "disposable_copy_apply":
        raise RuntimeError(f"AnythingLLM approval_state artifact mismatch for {target_root}: {json.dumps(approval_state, sort_keys=True)}")
    proof = require_route_decision_proof(decision, target_root, "AnythingLLM")
    return {"run_id": run_id, "route_decision": str(decision_path), "proof": proof}


def validate_direct(args: argparse.Namespace, target_root: str) -> dict[str, Any]:
    status, body = json_request(
        f"{args.controller_base_url.rstrip('/')}/v1/controller/implementation-runs",
        payload=implementation_payload(target_root, mode="dry_run", approval=dry_run_approval()),
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"direct dry-run returned HTTP {status} for {target_root}: {json.dumps(body, ensure_ascii=True)}")
    patch_preview = require_direct_dry_run(body, target_root)

    apply_status, apply_body = json_request(
        f"{args.controller_base_url.rstrip('/')}/v1/controller/implementation-runs",
        payload=implementation_payload(target_root, mode="apply", approval=real_apply_approval()),
        timeout_seconds=args.timeout_seconds,
    )
    require_protected_apply_refusal(apply_body, apply_status, target_root)
    print(f"PHASE54 DIRECT PASS target={target_root} dry_run={body.get('run_id')}")
    return {"target_root": target_root, "dry_run_id": body.get("run_id"), "patch_preview": patch_preview}


def validate_gateway(args: argparse.Namespace, target_root: str) -> dict[str, Any]:
    status, body = json_request(
        f"{args.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload=gateway_payload(target_root),
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"gateway returned HTTP {status} for {target_root}: {json.dumps(body, ensure_ascii=True)}")
    result = require_gateway_response(body, target_root)
    print(f"PHASE54 GATEWAY PASS target={target_root} run_id={result.get('run_id')}")
    return {"target_root": target_root, "run_id": result.get("run_id")}


def validate_anythingllm(args: argparse.Namespace, target_root: str, api_key: str, artifact_root: Path) -> dict[str, Any]:
    status, body = json_request(
        f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{args.workspace}/chat",
        payload=anythingllm_payload(target_root),
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"AnythingLLM returned HTTP {status} for {target_root}: {json.dumps(body, ensure_ascii=True)}")
    result = require_anythingllm_response(body, target_root, artifact_root)
    print(f"PHASE54 ANYTHINGLLM PASS target={target_root} run_id={result.get('run_id')}")
    return {"target_root": target_root, "run_id": result.get("run_id"), "route_decision": result.get("route_decision")}


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=DEFAULT_CONFIG_ROOT)
    parser.add_argument("--controller-base-url", default=DEFAULT_CONTROLLER_BASE_URL)
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--controller-artifact-root", default=DEFAULT_CONTROLLER_ARTIFACT_ROOT)
    parser.add_argument("--output-path", default=DEFAULT_REPORT_PATH)
    parser.add_argument("--target-root", action="append", dest="target_roots")
    parser.add_argument("--skip-anythingllm", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_root = Path(args.config_root).resolve()
    artifact_root = Path(args.controller_artifact_root).resolve()
    output_path = Path(args.output_path)
    if not output_path.is_absolute():
        output_path = config_root / output_path
    target_roots = [Path(value).resolve() for value in (args.target_roots or DEFAULT_TARGET_ROOTS)]

    for root in target_roots:
        invariant = root / "docs" / "agents" / "INVARIANTS.md"
        text = invariant.read_text(encoding="utf-8")
        if FROZEN_INVARIANT_OLD not in text:
            raise RuntimeError(f"{root} does not contain the expected Phase54 invariant anchor")

    runtime_before = watched_hashes(config_root, WATCHED_RUNTIME_FILES)
    target_before = {str(root): watched_hashes(root, WATCHED_TARGET_FILES) for root in target_roots}
    target_git_before = {str(root): git_status(root) for root in target_roots}
    checks: dict[str, Any] = {
        "ports": validate_port_health(args.timeout_seconds),
        "direct": [],
        "gateway": [],
        "anythingllm": [],
    }

    for root in target_roots:
        target = str(root)
        checks["direct"].append(validate_direct(args, target))
        validate_no_target_mutation(root, target_before[target], target_git_before[target], "direct controller")
        checks["gateway"].append(validate_gateway(args, target))
        validate_no_target_mutation(root, target_before[target], target_git_before[target], "gateway")

    if not args.skip_anythingllm:
        api_key = os.environ.get(args.api_key_env)
        if not api_key:
            raise RuntimeError(f"{args.api_key_env} is required unless --skip-anythingllm is set")
        for root in target_roots:
            target = str(root)
            checks["anythingllm"].append(validate_anythingllm(args, target, api_key, artifact_root))
            validate_no_target_mutation(root, target_before[target], target_git_before[target], "AnythingLLM")

    runtime_changed = changed_hashes(runtime_before, watched_hashes(config_root, WATCHED_RUNTIME_FILES))
    if runtime_changed:
        raise RuntimeError(f"canonical runtime metadata mutated during live validation: {runtime_changed}")

    report = {
        "kind": "controlled_small_change_apply_live_validation",
        "schema_version": 1,
        "status": "passed",
        "created_at": utc_now(),
        "config_root": str(config_root),
        "controller_artifact_root": str(artifact_root),
        "target_roots": [str(root) for root in target_roots],
        "controller_base_url": args.controller_base_url,
        "workflow_router_gateway_base_url": args.workflow_router_gateway_base_url,
        "anythingllm_applicable": not args.skip_anythingllm,
        "checks": checks,
        "runtime_changed_files": runtime_changed,
        "target_changed_files": {},
    }
    write_json(output_path, report)
    print(f"PHASE54 CONTROLLED SMALL-CHANGE APPLY LIVE PASS report={output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
