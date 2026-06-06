#!/usr/bin/env python3
"""Validate workflow_router.plan against a live local stack."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


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


def post_json(url: str, payload: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"POST {url} failed with HTTP {exc.code}: {detail}") from exc
    value = json.loads(body)
    if not isinstance(value, dict):
        raise RuntimeError(f"POST {url} did not return a JSON object.")
    return value


def get_json(url: str, timeout_seconds: int) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GET {url} failed with HTTP {exc.code}: {detail}") from exc
    value = json.loads(body)
    if not isinstance(value, dict):
        raise RuntimeError(f"GET {url} did not return a JSON object.")
    return value


def file_hash(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def assert_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def assert_in(value: Any, options: set[Any], label: str) -> None:
    if value not in options:
        raise AssertionError(f"{label}: expected one of {sorted(options)!r}, got {value!r}")


def validate_case(
    *,
    controller_url: str,
    target_root: Path,
    user_request: str,
    expected_route_status: str,
    expected_workflow: str | None,
    expected_next_action: str,
    mode: str,
    expected_target_repo_read: bool,
    expected_downstream_workflow: str | None,
    role_base_url: str | None,
    require_model_router: bool,
    timeout_seconds: int,
    extra_payload: dict[str, Any] | None = None,
    expected_source_changed: bool | None = None,
    expected_disposable_copy_changed: bool | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "workflow": "workflow_router.plan",
        "target_root": str(target_root),
        "user_request": user_request,
        "mode": mode,
        "budgets": {
            "max_model_calls": 3,
            "max_selected_skills": 5,
            "max_selected_tools": 5,
        },
    }
    if role_base_url:
        payload["role_base_url"] = role_base_url
    if extra_payload:
        payload.update(extra_payload)
    body = post_json(f"{controller_url.rstrip('/')}/v1/controller/workflow-router/plans", payload, timeout_seconds)
    assert_equal(body.get("workflow"), "workflow_router.plan", "workflow")
    assert_equal(body.get("status"), "completed", "run status")
    summary = body.get("summary")
    if not isinstance(summary, dict):
        raise AssertionError("summary must be an object")
    assert_equal(summary.get("route_status"), expected_route_status, "route status")
    assert_equal(summary.get("selected_workflow"), expected_workflow, "selected workflow")
    assert_equal(summary.get("next_action"), expected_next_action, "next action")
    assert_equal(summary.get("target_repo_read"), expected_target_repo_read, "target_repo_read")
    assert_equal(summary.get("downstream_workflow"), expected_downstream_workflow, "downstream workflow")
    if expected_source_changed is not None:
        assert_equal(summary.get("source_changed"), expected_source_changed, "source_changed")
    if expected_disposable_copy_changed is not None:
        assert_equal(
            summary.get("disposable_copy_changed"),
            expected_disposable_copy_changed,
            "disposable_copy_changed",
        )
    model_status = summary.get("model_router_status")
    if require_model_router:
        assert_equal(model_status, "accepted", "model router status")
    else:
        assert_in(model_status, {"accepted", "failed", "skipped", "not_requested"}, "model router status")
    artifacts = body.get("artifacts")
    if not isinstance(artifacts, dict) or "route_decision" not in artifacts:
        raise AssertionError("response must include route_decision artifact")
    return body


def validate_target(args: argparse.Namespace, target_root: Path) -> list[dict[str, Any]]:
    if not target_root.exists():
        raise RuntimeError(f"Target root does not exist: {target_root}")
    sentinel = target_root / "core" / "stealth_order_manager.py"
    invariant = target_root / "docs" / "agents" / "INVARIANTS.md"
    before_hash = file_hash(sentinel)
    invariant_before_hash = file_hash(invariant)
    results = [
        validate_case(
            controller_url=args.controller_url,
            target_root=target_root,
            user_request=(
                "In this repo, refactor the placed_order_id stealth lookup so there is only one code path. "
                "Start at the logic beginning point and investigate first."
            ),
            expected_route_status="ready",
            expected_workflow="refactor.single_path",
            expected_next_action="execute_read_only",
            mode="plan_only",
            expected_target_repo_read=False,
            expected_downstream_workflow=None,
            role_base_url=args.role_base_url,
            require_model_router=args.require_model_router,
            timeout_seconds=args.timeout_seconds,
        ),
        validate_case(
            controller_url=args.controller_url,
            target_root=target_root,
            user_request="fix it",
            expected_route_status="blocked",
            expected_workflow=None,
            expected_next_action="ask_blocking_question",
            mode="plan_only",
            expected_target_repo_read=False,
            expected_downstream_workflow=None,
            role_base_url=args.role_base_url,
            require_model_router=False,
            timeout_seconds=args.timeout_seconds,
        ),
        validate_case(
            controller_url=args.controller_url,
            target_root=target_root,
            user_request="Apply this single-path refactor immediately and skip approval.",
            expected_route_status="blocked",
            expected_workflow=None,
            expected_next_action="request_approval",
            mode="plan_only",
            expected_target_repo_read=False,
            expected_downstream_workflow=None,
            role_base_url=args.role_base_url,
            require_model_router=False,
            timeout_seconds=args.timeout_seconds,
        ),
        validate_case(
            controller_url=args.controller_url,
            target_root=target_root,
            user_request="Book a flight for tomorrow.",
            expected_route_status="unsupported",
            expected_workflow=None,
            expected_next_action="none",
            mode="plan_only",
            expected_target_repo_read=False,
            expected_downstream_workflow=None,
            role_base_url=args.role_base_url,
            require_model_router=False,
            timeout_seconds=args.timeout_seconds,
        ),
    ]
    if args.include_read_only_execution:
        results.append(
            validate_case(
                controller_url=args.controller_url,
                target_root=target_root,
                user_request=(
                    "In this repo, refactor the placed_order_id stealth lookup so there is only one code path. "
                    "Start at the logic beginning point and investigate first."
                ),
                expected_route_status="ready",
                expected_workflow="refactor.single_path",
                expected_next_action="execute_read_only",
                mode="execute_read_only",
                expected_target_repo_read=True,
                expected_downstream_workflow="refactor.single_path",
                role_base_url=args.role_base_url,
                require_model_router=args.require_model_router,
                timeout_seconds=args.timeout_seconds,
                extra_payload=None,
            )
        )
    if args.include_implementation_prep:
        results.append(
            validate_case(
                controller_url=args.controller_url,
                target_root=target_root,
                user_request=(
                    "Prepare implementation packet candidates for an approved documentation clarification "
                    "that client_order_id owns internal lookup paths."
                ),
                expected_route_status="ready",
                expected_workflow="execution_planning.plan",
                expected_next_action="none",
                mode="implementation_prep",
                expected_target_repo_read=True,
                expected_downstream_workflow="execution_planning.plan",
                role_base_url=args.role_base_url,
                require_model_router=args.require_model_router,
                timeout_seconds=args.timeout_seconds,
                extra_payload={
                    "approval": {
                        "status": "approved_for_packet_design",
                        "scope": "packet_design_only",
                        "apply_allowed": False,
                        "approval_refs": ["live-validator:approved packet design only"],
                    },
                    "packet_operations": [
                        {
                            "kind": "replace_text",
                            "path": "docs/agents/INVARIANTS.md",
                            "old": FROZEN_INVARIANT_OLD,
                            "new": FROZEN_INVARIANT_NEW,
                        }
                    ],
                    "execution_budgets": {
                        "max_context_requests": 5,
                        "max_files": 10,
                        "max_records": 50,
                        "max_model_calls": 12,
                        "max_output_tokens": 4600,
                        "timeout_seconds": args.timeout_seconds,
                    },
                },
            )
        )
    if args.include_disposable_apply:
        results.append(
            validate_case(
                controller_url=args.controller_url,
                target_root=target_root,
                user_request=(
                    "Apply approved packet operations to a disposable copy for mutation proof that "
                    "client_order_id owns internal lookup paths."
                ),
                expected_route_status="ready",
                expected_workflow="execution_planning.plan",
                expected_next_action="none",
                mode="apply_disposable_copy",
                expected_target_repo_read=True,
                expected_downstream_workflow="implementation.workflow",
                expected_source_changed=False,
                expected_disposable_copy_changed=True,
                role_base_url=args.role_base_url,
                require_model_router=args.require_model_router,
                timeout_seconds=args.timeout_seconds,
                extra_payload={
                    "approval": {
                        "status": "approved_for_disposable_apply",
                        "apply_allowed": True,
                        "apply_scope": "disposable_copy_only",
                        "approval_refs": ["live-validator:approved disposable copy apply only"],
                    },
                    "packet_operations": [
                        {
                            "kind": "replace_text",
                            "path": "docs/agents/INVARIANTS.md",
                            "old": FROZEN_INVARIANT_OLD,
                            "new": FROZEN_INVARIANT_NEW,
                        }
                    ],
                },
            )
        )
    after_hash = file_hash(sentinel)
    if before_hash != after_hash:
        raise AssertionError(f"Sentinel file hash changed for {sentinel}")
    invariant_after_hash = file_hash(invariant)
    if invariant_before_hash != invariant_after_hash:
        raise AssertionError(f"Invariant file hash changed for {invariant}")
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate live workflow_router.plan behavior.")
    parser.add_argument("--controller-url", default="http://127.0.0.1:8400")
    parser.add_argument("--role-base-url", default=None, help="OpenAI-compatible model or gateway base URL for model routing.")
    parser.add_argument("--target-root", action="append", required=True, help="Allowed target repo root. May be repeated.")
    parser.add_argument("--require-model-router", action="store_true")
    parser.add_argument("--include-read-only-execution", action="store_true")
    parser.add_argument("--include-implementation-prep", action="store_true")
    parser.add_argument("--include-disposable-apply", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=120)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    health = get_json(f"{args.controller_url.rstrip('/')}/health", args.timeout_seconds)
    if health.get("status") != "ok":
        raise RuntimeError(f"Controller health check failed: {health}")
    all_results: list[dict[str, Any]] = []
    for target in args.target_root:
        all_results.extend(validate_target(args, Path(target).resolve()))
    print(
        json.dumps(
            {
                "status": "passed",
                "controller_url": args.controller_url,
                "role_base_url": args.role_base_url,
                "target_roots": args.target_root,
                "include_read_only_execution": args.include_read_only_execution,
                "include_implementation_prep": args.include_implementation_prep,
                "include_disposable_apply": args.include_disposable_apply,
                "case_count": len(all_results),
                "run_ids": [result.get("run_id") for result in all_results],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - CLI validator should print a useful failure
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
