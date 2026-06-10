#!/usr/bin/env python3
"""Validate task decomposition against the live local stack."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vllm_agent_gateway.acceptance.task_decomposition_quality import evaluate_task_decomposition_plan


DEFAULT_CONTROLLER_BASE_URL = "http://127.0.0.1:8400"
DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL = "http://127.0.0.1:8500/v1"
DEFAULT_ANYTHINGLLM_API_BASE_URL = "http://127.0.0.1:3001"
DEFAULT_WORKSPACE = "my-workspace"
DEFAULT_CONFIG_ROOT = "/mnt/c/agentic_agents"
DEFAULT_REPORT_PATH = "runtime-state/task-decomposition/phase113-live.json"
DEFAULT_TARGET_ROOTS = [
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
    "/mnt/c/agentic_agents/tests/fixtures/generalization/python_service_fixture",
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
WATCHED_SOURCE_SUFFIXES = {".go", ".js", ".json", ".md", ".py", ".toml", ".yaml", ".yml"}
FORMAT_A_MARKERS = [
    "I completed workflow_router.plan.",
    "workflow_router.plan completed",
    "run_id: workflow-router-",
    "Result:",
    "- Selected workflow: task.decompose",
    "- Next action: none",
    "Task Decomposition:",
    "- Work-package schema: 3",
    "- Work packages:",
    "- Acceptance criteria:",
    "- Dependencies:",
    "- Approval gates:",
    "- Stop conditions:",
    "- Package verification:",
    "- Uncertainty:",
    "- Verification:",
    "- Source mutation: False",
    "Artifacts:",
]


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


def task_subject_for_target(target_root: str) -> str:
    root = Path(target_root)
    if (root / "service" / "orders.py").exists():
        return phase113_subjects_for_target(target_root)["feature"]
    return "add a focused unit test for placed_order_id stealth lookup after investigating related tests"


def phase113_subjects_for_target(target_root: str) -> dict[str, str]:
    root = Path(target_root)
    if (root / "service" / "orders.py").exists():
        return {
            "feature": "add a focused unit test for resolve_order_status after investigating related tests",
            "bug": "fix a failing test around resolve_order_status returning empty for zero-item orders",
            "requirement": "add a requirement note for the create-order response to document the resolved order status without changing files yet",
        }
    return {
        "feature": "add a focused unit test for placed_order_id stealth lookup after investigating related tests",
        "bug": "fix a failing test around placed_order_id stealth lookup returning no result for a stored order",
        "requirement": "add a requirement note for the stealth-order lookup answer to include whether placed_order_id evidence was found without changing files yet",
    }


def deferred_subject_for_target(target_root: str) -> str:
    root = Path(target_root)
    if (root / "service" / "orders.py").exists():
        return "refactor the resolve_order_status decision logic so there is one code path"
    return "refactor the placed_order_id stealth lookup so there is one code path"


def task_prompt(target_root: str, *, json_output: bool = False, subject: str | None = None) -> str:
    suffix = " Return JSON." if json_output else " Return the answer in the default format."
    return (
        f"In {target_root}, decompose this multi-step task into work packages with dependencies, "
        f"approval gates, and verification strategy: {subject or task_subject_for_target(target_root)}.{suffix}"
    )


def direct_payload(target_root: str, user_request: str | None = None) -> dict[str, Any]:
    return {
        "workflow": "task.decompose",
        "schema_version": 1,
        "target_root": target_root,
        "user_request": user_request
        or (
            "Decompose this multi-step task into work packages with dependencies, approval gates, "
            f"and verification strategy: {task_subject_for_target(target_root)}."
        ),
    }


def gateway_payload(target_root: str, *, json_output: bool = False, subject: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": "agentic-workflow-router",
        "messages": [{"role": "user", "content": task_prompt(target_root, json_output=json_output, subject=subject)}],
    }
    if json_output:
        payload["response_format"] = {"type": "json_object"}
    return payload


def anythingllm_payload(target_root: str, *, json_output: bool = False, subject: str | None = None) -> dict[str, Any]:
    return {
        "message": task_prompt(target_root, json_output=json_output, subject=subject),
        "mode": "chat",
        "sessionId": f"task-decomposition-{uuid.uuid4().hex}",
    }


def phase113_family_request(target_root: str, subject: str) -> str:
    return (
        "Decompose this multi-step task into work packages with dependencies, approval gates, "
        f"and verification strategy: {subject}."
    )


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


def json_content(body: dict[str, Any]) -> dict[str, Any]:
    text = text_response(body)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"assistant content was not parseable JSON: {text[:800]}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("assistant JSON content was not an object")
    return parsed


def read_json_artifact(path_value: Any) -> dict[str, Any]:
    if not isinstance(path_value, str):
        raise RuntimeError(f"artifact path was not a string: {path_value!r}")
    path = Path(path_value)
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"could not read JSON artifact {path}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"artifact {path} did not contain a JSON object")
    return parsed


def require_phase113_contract(plan: dict[str, Any], target_root: str, label: str) -> None:
    if plan.get("work_package_schema_version") != 3:
        raise RuntimeError(f"{label} work package schema mismatch for {target_root}: {plan.get('work_package_schema_version')!r}")
    quality_report = evaluate_task_decomposition_plan(plan)
    if quality_report.get("status") != "passed":
        raise RuntimeError(f"{label} Phase 113 quality contract failed for {target_root}: {json.dumps(quality_report, ensure_ascii=True)}")
    packages = plan.get("work_packages")
    if not isinstance(packages, list):
        raise RuntimeError(f"{label} missing work_packages for {target_root}")
    package_ids = [item.get("id") for item in packages if isinstance(item, dict)]
    expected_ids = ["WP1", "GATE2", "WP3", "WP4", "STOP5"]
    if package_ids != expected_ids:
        raise RuntimeError(f"{label} package order mismatch for {target_root}: {package_ids!r}")
    expected_edges = [
        {"from": "WP1", "to": "GATE2"},
        {"from": "GATE2", "to": "WP3"},
        {"from": "WP3", "to": "WP4"},
        {"from": "WP4", "to": "STOP5"},
    ]
    if plan.get("dependency_edges") != expected_edges:
        raise RuntimeError(f"{label} dependency edge mismatch for {target_root}: {json.dumps(plan.get('dependency_edges'), ensure_ascii=True)}")
    by_id = {item.get("id"): item for item in packages if isinstance(item, dict)}
    stage_expectations = {
        "WP1": "investigation",
        "GATE2": "prep_approval_gate",
        "WP3": "implementation_prep",
        "WP4": "verification",
        "STOP5": "terminal_stop",
    }
    for package_id, expected_stage in stage_expectations.items():
        item = by_id.get(package_id)
        if not isinstance(item, dict) or item.get("stage") != expected_stage:
            raise RuntimeError(f"{label} stage mismatch for {target_root} package={package_id}: {item}")
        if not isinstance(item.get("stop_conditions"), list) or not item["stop_conditions"]:
            raise RuntimeError(f"{label} missing stop conditions for {target_root} package={package_id}")
        if not isinstance(item.get("acceptance_criteria"), list) or not item["acceptance_criteria"]:
            raise RuntimeError(f"{label} missing acceptance criteria for {target_root} package={package_id}")
        if not isinstance(item.get("scope_boundary"), dict) or item["scope_boundary"].get("independently_reviewable") is not True:
            raise RuntimeError(f"{label} missing independent scope boundary for {target_root} package={package_id}")
        verification = item.get("verification")
        if not isinstance(verification, dict) or not verification.get("status"):
            raise RuntimeError(f"{label} missing verification status for {target_root} package={package_id}")
    gates = plan.get("approval_gates")
    gate_packages = [item.get("package_id") for item in gates if isinstance(item, dict)] if isinstance(gates, list) else []
    if gate_packages != ["GATE2", "STOP5"]:
        raise RuntimeError(f"{label} approval gate package mismatch for {target_root}: {gate_packages!r}")


def require_phase113_inline_contract(contract: dict[str, Any], target_root: str, label: str) -> None:
    if contract.get("work_package_schema_version") != 3:
        raise RuntimeError(f"{label} inline work package schema mismatch for {target_root}: {contract.get('work_package_schema_version')!r}")
    tenet_contract = contract.get("tenet_contract")
    if not isinstance(tenet_contract, dict) or tenet_contract.get("phase") != 113:
        raise RuntimeError(f"{label} inline contract missing Phase 113 tenet contract for {target_root}")
    packages = contract.get("work_packages")
    if not isinstance(packages, list):
        raise RuntimeError(f"{label} inline contract missing work packages for {target_root}")
    package_ids = [item.get("id") for item in packages if isinstance(item, dict)]
    expected_ids = ["WP1", "GATE2", "WP3", "WP4", "STOP5"]
    if package_ids != expected_ids:
        raise RuntimeError(f"{label} inline package order mismatch for {target_root}: {package_ids!r}")
    for item in packages:
        if not isinstance(item, dict):
            continue
        package_id = item.get("id")
        if not isinstance(item.get("acceptance_criteria"), list) or not item["acceptance_criteria"]:
            raise RuntimeError(f"{label} inline contract missing acceptance criteria for {target_root} package={package_id}")
        if not isinstance(item.get("scope_boundary"), dict) or item["scope_boundary"].get("independently_reviewable") is not True:
            raise RuntimeError(f"{label} inline contract missing scope boundary for {target_root} package={package_id}")
    gates = contract.get("approval_gates")
    gate_packages = [item.get("package_id") for item in gates if isinstance(item, dict)] if isinstance(gates, list) else []
    if gate_packages != ["GATE2", "STOP5"]:
        raise RuntimeError(f"{label} inline approval gate package mismatch for {target_root}: {gate_packages!r}")


def require_advanced_refactor_deferred(plan: dict[str, Any], target_root: str, label: str) -> None:
    quality_report = evaluate_task_decomposition_plan(plan)
    if quality_report.get("status") != "passed":
        raise RuntimeError(f"{label} Phase 113 quality contract failed for {target_root}: {json.dumps(quality_report, ensure_ascii=True)}")
    if plan.get("status") != "blocked" or plan.get("prompt_family") != "advanced_refactor_deferred":
        raise RuntimeError(f"{label} did not defer advanced refactor for {target_root}: {json.dumps(plan, ensure_ascii=True)[:1000]}")
    if plan.get("deferred_to_phase") != 105:
        raise RuntimeError(f"{label} deferred phase mismatch for {target_root}: {plan.get('deferred_to_phase')!r}")
    package_ids = [
        item.get("id")
        for item in plan.get("work_packages", [])
        if isinstance(item, dict)
    ]
    if package_ids != ["DEFER1"] or plan.get("selected_workflow_ids") != []:
        raise RuntimeError(f"{label} advanced refactor created executable packages for {target_root}: {package_ids!r}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def watched_files_for_root(root: Path) -> list[str]:
    preferred = [relative for relative in WATCHED_TARGET_FILES if (root / relative).exists()]
    if preferred:
        return preferred
    selected: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if ".git" in path.parts or "__pycache__" in path.parts:
            continue
        if path.suffix.lower() not in WATCHED_SOURCE_SUFFIXES:
            continue
        selected.append(path.relative_to(root).as_posix())
        if len(selected) >= 20:
            break
    return selected


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
    return sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))


def git_status(root: Path) -> str | None:
    if not (root / ".git").exists():
        return None
    result = subprocess.run(["git", "-C", str(root), "status", "--short"], check=True, capture_output=True, text=True)
    return result.stdout


def validate_no_target_mutation(
    root: Path,
    relatives: list[str],
    before_hashes: dict[str, str],
    before_status: str | None,
    label: str,
) -> None:
    changed = changed_hashes(before_hashes, watched_hashes(root, relatives))
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
        print(f"PHASE113 PORT PASS label={label} url={url}")
    return checks


def require_direct_response(
    body: dict[str, Any],
    target_root: str,
    *,
    expected_prompt_family: str = "feature_or_small_change",
) -> None:
    summary = body.get("summary")
    if not isinstance(summary, dict):
        raise RuntimeError("direct response did not include summary")
    expected = {
        "decomposition_status": "ready",
        "prompt_family": expected_prompt_family,
        "target_repository_changed": False,
        "runtime_registry_changed": False,
    }
    wrong = {
        key: {"expected": expected_value, "actual": summary.get(key)}
        for key, expected_value in expected.items()
        if summary.get(key) != expected_value
    }
    if wrong:
        raise RuntimeError(f"direct task decomposition summary mismatch for {target_root}: {json.dumps(wrong, sort_keys=True)}")
    artifacts = body.get("artifacts")
    if not isinstance(artifacts, dict) or "task_decomposition" not in artifacts:
        raise RuntimeError(f"direct response missing task_decomposition artifact for {target_root}")
    if any("packet" in key for key in artifacts):
        raise RuntimeError(f"direct response created packet artifact for {target_root}: {sorted(artifacts)}")
    require_phase113_contract(read_json_artifact(artifacts["task_decomposition"]), target_root, "direct")


def require_ambiguous_response(body: dict[str, Any], target_root: str) -> None:
    summary = body.get("summary")
    if not isinstance(summary, dict):
        raise RuntimeError("ambiguous direct response did not include summary")
    if summary.get("decomposition_status") != "needs_clarification":
        raise RuntimeError(f"ambiguous task was not blocked for {target_root}: {json.dumps(summary, sort_keys=True)}")
    if summary.get("next_action") != "ask_blocking_question" or summary.get("package_count") != 0:
        raise RuntimeError(f"ambiguous task did not request clarification for {target_root}: {json.dumps(summary, sort_keys=True)}")


def require_format_a(body: dict[str, Any], target_root: str, label: str) -> str:
    text = text_response(body)
    missing = [marker for marker in FORMAT_A_MARKERS if marker not in text]
    if missing:
        raise RuntimeError(f"{label} missing FormatA markers for {target_root}: {missing}")
    compact = body.get("agentic_controller_response")
    if isinstance(compact, dict):
        summary = compact.get("summary")
        if isinstance(summary, dict) and summary.get("selected_workflow") != "task.decompose":
            raise RuntimeError(f"{label} selected wrong workflow for {target_root}: {summary.get('selected_workflow')!r}")
        artifacts = compact.get("artifacts")
        if isinstance(artifacts, dict) and any("packet" in key for key in artifacts):
            raise RuntimeError(f"{label} created packet artifact for {target_root}: {sorted(artifacts)}")
    return text


def require_json_contract(parsed: dict[str, Any], target_root: str, label: str) -> None:
    if parsed.get("output_format") != "json":
        raise RuntimeError(f"{label} output_format mismatch for {target_root}: {parsed.get('output_format')!r}")
    contract = parsed.get("chat_contract")
    if not isinstance(contract, dict):
        raise RuntimeError(f"{label} JSON did not include chat_contract for {target_root}")
    expected_contract = {
        "workflow": "workflow_router.plan",
        "status": "completed",
        "selected_workflow": "task.decompose",
        "next_action": "none",
    }
    wrong = {
        key: {"expected": expected_value, "actual": contract.get(key)}
        for key, expected_value in expected_contract.items()
        if contract.get(key) != expected_value
    }
    if wrong:
        raise RuntimeError(f"{label} chat_contract mismatch for {target_root}: {json.dumps(wrong, sort_keys=True)}")
    summary = parsed.get("summary")
    if not isinstance(summary, dict) or summary.get("downstream_workflow") != "task.decompose":
        raise RuntimeError(f"{label} JSON missing downstream task.decompose summary for {target_root}")
    artifacts = parsed.get("artifacts")
    if not isinstance(artifacts, dict) or "downstream_task_decomposition" not in artifacts:
        raise RuntimeError(f"{label} JSON missing downstream_task_decomposition for {target_root}")
    if any("packet" in key for key in artifacts):
        raise RuntimeError(f"{label} JSON created packet artifact for {target_root}: {sorted(artifacts)}")
    contract = parsed.get("task_decomposition_contract")
    if not isinstance(contract, dict):
        raise RuntimeError(f"{label} JSON did not include task_decomposition_contract for {target_root}")
    require_phase113_inline_contract(contract, target_root, f"{label} JSON contract")
    require_phase113_contract(
        read_json_artifact(artifacts["downstream_task_decomposition"]),
        target_root,
        f"{label} JSON artifact",
    )


def validate_direct(args: argparse.Namespace, target_root: str) -> dict[str, Any]:
    status, body = json_request(
        f"{args.controller_base_url.rstrip('/')}/v1/controller/task-decompositions",
        payload=direct_payload(target_root),
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"direct controller returned HTTP {status} for {target_root}: {json.dumps(body, ensure_ascii=True)}")
    require_direct_response(body, target_root)
    family_runs: list[dict[str, Any]] = [{"family": "feature", "run_id": body.get("run_id")}]
    for family, subject in phase113_subjects_for_target(target_root).items():
        if family == "feature":
            continue
        family_status, family_body = json_request(
            f"{args.controller_base_url.rstrip('/')}/v1/controller/task-decompositions",
            payload=direct_payload(target_root, phase113_family_request(target_root, subject)),
            timeout_seconds=args.timeout_seconds,
        )
        if family_status != 200:
            raise RuntimeError(
                f"direct controller returned HTTP {family_status} for {target_root} family={family}: "
                f"{json.dumps(family_body, ensure_ascii=True)}"
            )
        expected_family = "failing_test_remediation" if family == "bug" else "feature_or_small_change"
        require_direct_response(family_body, target_root, expected_prompt_family=expected_family)
        family_runs.append({"family": family, "run_id": family_body.get("run_id")})
    ambiguous_status, ambiguous_body = json_request(
        f"{args.controller_base_url.rstrip('/')}/v1/controller/task-decompositions",
        payload=direct_payload(target_root, "fix it"),
        timeout_seconds=args.timeout_seconds,
    )
    if ambiguous_status != 200:
        raise RuntimeError(
            f"ambiguous direct controller returned HTTP {ambiguous_status} for {target_root}: "
            f"{json.dumps(ambiguous_body, ensure_ascii=True)}"
        )
    require_ambiguous_response(ambiguous_body, target_root)
    deferred_status, deferred_body = json_request(
        f"{args.controller_base_url.rstrip('/')}/v1/controller/task-decompositions",
        payload=direct_payload(
            target_root,
            "Decompose this multi-step task into work packages with dependencies, approval gates, "
            f"and verification strategy: {deferred_subject_for_target(target_root)}.",
        ),
        timeout_seconds=args.timeout_seconds,
    )
    if deferred_status != 200:
        raise RuntimeError(
            f"advanced refactor direct controller returned HTTP {deferred_status} for {target_root}: "
            f"{json.dumps(deferred_body, ensure_ascii=True)}"
        )
    artifacts = deferred_body.get("artifacts")
    if not isinstance(artifacts, dict) or "task_decomposition" not in artifacts:
        raise RuntimeError(f"advanced refactor response missing task_decomposition artifact for {target_root}")
    require_advanced_refactor_deferred(
        read_json_artifact(artifacts["task_decomposition"]),
        target_root,
        "direct advanced refactor",
    )
    print(f"PHASE113 DIRECT PASS target={target_root} run_id={body.get('run_id')}")
    return {
        "target_root": target_root,
        "run_id": body.get("run_id"),
        "family_runs": family_runs,
        "ambiguous_run_id": ambiguous_body.get("run_id"),
        "deferred_run_id": deferred_body.get("run_id"),
    }


def validate_gateway(args: argparse.Namespace, target_root: str) -> dict[str, Any]:
    status, body = json_request(
        f"{args.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload=gateway_payload(target_root),
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"gateway returned HTTP {status} for {target_root}: {json.dumps(body, ensure_ascii=True)}")
    text = require_format_a(body, target_root, "gateway")
    family_runs: list[dict[str, Any]] = [{"family": "feature", "format_a_run_id": run_id_from_text(text)}]
    for family, subject in phase113_subjects_for_target(target_root).items():
        if family == "feature":
            continue
        family_status, family_body = json_request(
            f"{args.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
            payload=gateway_payload(target_root, subject=subject),
            timeout_seconds=args.timeout_seconds,
        )
        if family_status != 200:
            raise RuntimeError(
                f"gateway returned HTTP {family_status} for {target_root} family={family}: "
                f"{json.dumps(family_body, ensure_ascii=True)}"
            )
        family_text = require_format_a(family_body, target_root, f"gateway {family}")
        family_runs.append({"family": family, "format_a_run_id": run_id_from_text(family_text)})

    json_status, json_body = json_request(
        f"{args.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload=gateway_payload(target_root, json_output=True),
        timeout_seconds=args.timeout_seconds,
    )
    if json_status != 200:
        raise RuntimeError(f"gateway JSON returned HTTP {json_status} for {target_root}: {json.dumps(json_body, ensure_ascii=True)}")
    parsed = json_content(json_body)
    require_json_contract(parsed, target_root, "gateway")
    run_id = parsed.get("run_id")
    print(f"PHASE113 GATEWAY PASS target={target_root} run_id={run_id}")
    return {"target_root": target_root, "format_a_run_id": run_id_from_text(text), "json_run_id": run_id, "family_runs": family_runs}


def run_id_from_text(text: str) -> str:
    marker = "run_id:"
    if marker not in text:
        return "unknown"
    return text.split(marker, 1)[1].strip().split()[0]


def validate_anythingllm(args: argparse.Namespace, target_root: str, api_key: str) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {api_key}"}
    status, body = json_request(
        f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{args.workspace}/chat",
        payload=anythingllm_payload(target_root),
        headers=headers,
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"AnythingLLM returned HTTP {status} for {target_root}: {json.dumps(body, ensure_ascii=True)}")
    text = require_format_a(body, target_root, "AnythingLLM")
    family_runs: list[dict[str, Any]] = [{"family": "feature", "format_a_run_id": run_id_from_text(text)}]
    for family, subject in phase113_subjects_for_target(target_root).items():
        if family == "feature":
            continue
        family_status, family_body = json_request(
            f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{args.workspace}/chat",
            payload=anythingllm_payload(target_root, subject=subject),
            headers=headers,
            timeout_seconds=args.timeout_seconds,
        )
        if family_status != 200:
            raise RuntimeError(
                f"AnythingLLM returned HTTP {family_status} for {target_root} family={family}: "
                f"{json.dumps(family_body, ensure_ascii=True)}"
            )
        family_text = require_format_a(family_body, target_root, f"AnythingLLM {family}")
        family_runs.append({"family": family, "format_a_run_id": run_id_from_text(family_text)})

    json_status, json_body = json_request(
        f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{args.workspace}/chat",
        payload=anythingllm_payload(target_root, json_output=True),
        headers=headers,
        timeout_seconds=args.timeout_seconds,
    )
    if json_status != 200:
        raise RuntimeError(f"AnythingLLM JSON returned HTTP {json_status} for {target_root}: {json.dumps(json_body, ensure_ascii=True)}")
    parsed = json_content(json_body)
    require_json_contract(parsed, target_root, "AnythingLLM")
    run_id = parsed.get("run_id")
    print(f"PHASE113 ANYTHINGLLM PASS target={target_root} run_id={run_id}")
    return {"target_root": target_root, "format_a_run_id": run_id_from_text(text), "json_run_id": run_id, "family_runs": family_runs}


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
    parser.add_argument("--output-path", default=DEFAULT_REPORT_PATH)
    parser.add_argument("--target-root", action="append", dest="target_roots")
    parser.add_argument("--skip-anythingllm", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_root = Path(args.config_root).resolve()
    output_path = Path(args.output_path)
    if not output_path.is_absolute():
        output_path = config_root / output_path
    target_roots = [Path(value).resolve() for value in (args.target_roots or DEFAULT_TARGET_ROOTS)]

    runtime_before = watched_hashes(config_root, WATCHED_RUNTIME_FILES)
    target_watch_files = {str(root): watched_files_for_root(root) for root in target_roots}
    target_before = {str(root): watched_hashes(root, target_watch_files[str(root)]) for root in target_roots}
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
        validate_no_target_mutation(root, target_watch_files[target], target_before[target], target_git_before[target], "direct controller")
        checks["gateway"].append(validate_gateway(args, target))
        validate_no_target_mutation(root, target_watch_files[target], target_before[target], target_git_before[target], "gateway")

    if not args.skip_anythingllm:
        api_key = os.environ.get(args.api_key_env)
        if not api_key:
            raise RuntimeError(f"{args.api_key_env} is required unless --skip-anythingllm is set")
        for root in target_roots:
            target = str(root)
            checks["anythingllm"].append(validate_anythingllm(args, target, api_key))
            validate_no_target_mutation(root, target_watch_files[target], target_before[target], target_git_before[target], "AnythingLLM")

    runtime_changed = changed_hashes(runtime_before, watched_hashes(config_root, WATCHED_RUNTIME_FILES))
    if runtime_changed:
        raise RuntimeError(f"canonical runtime metadata mutated during live validation: {runtime_changed}")

    report = {
        "kind": "task_decomposition_live_validation",
        "schema_version": 1,
        "status": "passed",
        "created_at": utc_now(),
        "config_root": str(config_root),
        "target_roots": [str(root) for root in target_roots],
        "controller_base_url": args.controller_base_url,
        "workflow_router_gateway_base_url": args.workflow_router_gateway_base_url,
        "anythingllm_applicable": not args.skip_anythingllm,
        "checks": checks,
        "runtime_changed_files": runtime_changed,
        "target_changed_files": {},
    }
    write_json(output_path, report)
    print(f"PHASE113 TASK DECOMPOSITION LIVE PASS report={output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
