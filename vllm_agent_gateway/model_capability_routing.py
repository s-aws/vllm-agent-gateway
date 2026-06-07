"""Fail-closed model capability routing policy.

This module turns advisory model capability profiles into runtime routing
constraints without introducing a second workflow selector.
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.model_capability_profile import (
    ProfileStatus,
    TaskPolicyStatus,
)


SCHEMA_VERSION = 1
MODEL_CAPABILITY_ROUTING_POLICY_PATH = Path("runtime") / "model_capability_routing.json"


class ModelCapabilityTaskClass(str, Enum):
    READ_ONLY_L1 = "read_only_l1"
    DRAFT_ONLY_L1 = "draft_only_l1"
    APPROVAL_GATED_L1 = "approval_gated_l1"
    L2_READ_ONLY = "l2_read_only"
    APPLY_PREP = "apply_prep"
    REAL_APPLY = "real_apply"
    UNKNOWN = "unknown"


class ModelCapabilityGateStatus(str, Enum):
    APPROVED = "approved"
    CONDITIONAL = "conditional"
    BLOCKED = "blocked"
    NOT_APPLICABLE = "not_applicable"


def read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {
            "kind": "missing",
            "path": str(path),
            "error": f"missing_{label}",
        }
    except json.JSONDecodeError as exc:
        return {
            "kind": "invalid",
            "path": str(path),
            "error": f"invalid_{label}",
            "message": str(exc),
        }
    if not isinstance(value, dict):
        return {
            "kind": "invalid",
            "path": str(path),
            "error": f"invalid_{label}",
            "message": f"{label} must be a JSON object.",
        }
    return value


def policy_path(config_root: Path) -> Path:
    path = MODEL_CAPABILITY_ROUTING_POLICY_PATH
    return path if path.is_absolute() else config_root / path


def profile_path(config_root: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else config_root / path


def normalize_base_url(value: str | None) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip().rstrip("/")


def route_task_class(
    *,
    selected_workflow: str | None,
    route_rules: list[str],
    mode: str,
    approval: dict[str, Any],
    packet_operations: list[dict[str, Any]],
) -> ModelCapabilityTaskClass:
    if selected_workflow is None:
        return ModelCapabilityTaskClass.UNKNOWN
    if mode == "apply_disposable_copy":
        return ModelCapabilityTaskClass.APPLY_PREP
    route_rule_set = set(route_rules)
    if selected_workflow == "execution_planning.plan":
        approval_status = approval.get("status") if isinstance(approval, dict) else None
        approval_scope = approval.get("scope") if isinstance(approval, dict) else None
        apply_allowed = approval.get("apply_allowed") if isinstance(approval, dict) else None
        draft_boundary = (
            isinstance(approval_scope, str)
            and "draft" in approval_scope
            and apply_allowed is False
            and not packet_operations
        )
        if any(rule.startswith("l1_") or rule.startswith("d1_") for rule in route_rule_set) and (
            approval_status is None or draft_boundary
        ):
            return ModelCapabilityTaskClass.DRAFT_ONLY_L1
        if approval_status in {"approved_for_packet_design", "approved_for_disposable_apply"} or packet_operations:
            return ModelCapabilityTaskClass.APPLY_PREP
        if any(rule.startswith("l1_") or rule.startswith("d1_") for rule in route_rule_set):
            return ModelCapabilityTaskClass.DRAFT_ONLY_L1
        return ModelCapabilityTaskClass.APPROVAL_GATED_L1
    if selected_workflow == "refactor.single_path":
        return ModelCapabilityTaskClass.L2_READ_ONLY
    if selected_workflow in {"task.decompose", "skill_batch.propose"}:
        return ModelCapabilityTaskClass.L2_READ_ONLY
    if any(rule.startswith("l2_") for rule in route_rule_set):
        return ModelCapabilityTaskClass.L2_READ_ONLY
    if any(rule.startswith("l1_") for rule in route_rule_set):
        return ModelCapabilityTaskClass.READ_ONLY_L1
    if selected_workflow in {"code_context.lookup", "code_investigation.plan", "workflow_feedback.record"}:
        return ModelCapabilityTaskClass.READ_ONLY_L1
    return ModelCapabilityTaskClass.UNKNOWN


def default_profile_entry(policy: dict[str, Any]) -> dict[str, Any] | None:
    profile_id = policy.get("default_profile_id")
    profiles = policy.get("profiles")
    if not isinstance(profile_id, str) or not isinstance(profiles, list):
        return None
    for item in profiles:
        if isinstance(item, dict) and item.get("profile_id") == profile_id:
            return item
    return None


def task_rule(policy: dict[str, Any], task_class: ModelCapabilityTaskClass) -> dict[str, Any] | None:
    rules = policy.get("task_class_rules")
    if not isinstance(rules, dict):
        return None
    value = rules.get(task_class.value)
    return value if isinstance(value, dict) else None


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def blocked_decision(
    *,
    reason: str,
    message: str,
    task_class: ModelCapabilityTaskClass,
    policy: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
    profile_entry: dict[str, Any] | None = None,
    task_policy_key: str | None = None,
    task_policy_status: str | None = None,
) -> dict[str, Any]:
    return {
        "kind": "model_capability_routing_decision",
        "schema_version": SCHEMA_VERSION,
        "status": ModelCapabilityGateStatus.BLOCKED.value,
        "enforcement_mode": "fail_closed",
        "task_class": task_class.value,
        "task_policy_key": task_policy_key,
        "task_policy_status": task_policy_status,
        "profile_id": profile_entry.get("profile_id") if isinstance(profile_entry, dict) else None,
        "profile_path": profile_entry.get("profile_path") if isinstance(profile_entry, dict) else None,
        "profile_status": profile.get("status") if isinstance(profile, dict) else None,
        "policy_path": policy.get("policy_path") if isinstance(policy, dict) else None,
        "blockers": [{"reason": reason, "message": message}],
    }


def evaluate_model_capability_routing(
    *,
    config_root: Path,
    selected_workflow: str | None,
    route_rules: list[str],
    mode: str,
    approval: dict[str, Any],
    packet_operations: list[dict[str, Any]],
    role_base_url: str | None,
    model: str,
) -> dict[str, Any]:
    task_class = route_task_class(
        selected_workflow=selected_workflow,
        route_rules=route_rules,
        mode=mode,
        approval=approval,
        packet_operations=packet_operations,
    )
    if selected_workflow is None:
        return {
            "kind": "model_capability_routing_decision",
            "schema_version": SCHEMA_VERSION,
            "status": ModelCapabilityGateStatus.NOT_APPLICABLE.value,
            "enforcement_mode": "fail_closed",
            "task_class": task_class.value,
            "blockers": [],
        }

    policy_file = policy_path(config_root)
    policy = read_json_object(policy_file, "model_capability_routing_policy")
    policy["policy_path"] = str(policy_file)
    if policy.get("kind") != "model_capability_routing_policy":
        return blocked_decision(
            reason="model_capability_policy_missing",
            message="No valid model capability routing policy is available.",
            task_class=task_class,
            policy=policy,
        )
    if policy.get("enforcement_mode") != "fail_closed":
        return blocked_decision(
            reason="model_capability_policy_not_fail_closed",
            message="Model capability routing policy must use fail_closed enforcement.",
            task_class=task_class,
            policy=policy,
        )

    profile_entry = default_profile_entry(policy)
    if profile_entry is None:
        return blocked_decision(
            reason="model_capability_default_profile_missing",
            message="Model capability routing policy has no default active profile.",
            task_class=task_class,
            policy=policy,
        )
    raw_profile_path = profile_entry.get("profile_path")
    if not isinstance(raw_profile_path, str) or not raw_profile_path.strip():
        return blocked_decision(
            reason="model_capability_profile_path_missing",
            message="Default model capability profile entry does not include a profile_path.",
            task_class=task_class,
            policy=policy,
            profile_entry=profile_entry,
        )

    profile_file = profile_path(config_root, raw_profile_path)
    profile = read_json_object(profile_file, "model_capability_profile")
    if profile.get("kind") != "model_capability_profile":
        return blocked_decision(
            reason="model_capability_profile_missing",
            message="No valid model capability profile is available for routing enforcement.",
            task_class=task_class,
            policy=policy,
            profile=profile,
            profile_entry=profile_entry,
        )
    if profile.get("status") == ProfileStatus.FAILED.value:
        return blocked_decision(
            reason="model_capability_profile_failed",
            message="The selected model capability profile failed and cannot approve routing.",
            task_class=task_class,
            policy=policy,
            profile=profile,
            profile_entry=profile_entry,
        )

    rule = task_rule(policy, task_class)
    if rule is None:
        return blocked_decision(
            reason="model_capability_task_rule_missing",
            message=f"No model capability task rule exists for {task_class.value}.",
            task_class=task_class,
            policy=policy,
            profile=profile,
            profile_entry=profile_entry,
        )
    task_policy_key = rule.get("task_policy_key")
    if not isinstance(task_policy_key, str):
        return blocked_decision(
            reason="model_capability_task_policy_key_missing",
            message=f"Model capability task rule {task_class.value} is missing task_policy_key.",
            task_class=task_class,
            policy=policy,
            profile=profile,
            profile_entry=profile_entry,
        )
    task_policy = profile.get("task_policy")
    task_policy_entry = task_policy.get(task_policy_key) if isinstance(task_policy, dict) else None
    if not isinstance(task_policy_entry, dict):
        return blocked_decision(
            reason="model_capability_task_policy_missing",
            message=f"Profile does not include task policy {task_policy_key}.",
            task_class=task_class,
            policy=policy,
            profile=profile,
            profile_entry=profile_entry,
            task_policy_key=task_policy_key,
        )

    task_policy_status = task_policy_entry.get("status")
    allowed_statuses = set(string_list(rule.get("allowed_task_policy_statuses")))
    if not isinstance(task_policy_status, str) or task_policy_status not in allowed_statuses:
        return blocked_decision(
            reason="model_capability_task_not_approved",
            message=(
                f"Task class {task_class.value} requires {task_policy_key} status in "
                f"{sorted(allowed_statuses)}, but the profile reports {task_policy_status!r}."
            ),
            task_class=task_class,
            policy=policy,
            profile=profile,
            profile_entry=profile_entry,
            task_policy_key=task_policy_key,
            task_policy_status=task_policy_status if isinstance(task_policy_status, str) else None,
        )

    status = (
        ModelCapabilityGateStatus.CONDITIONAL
        if task_policy_status == TaskPolicyStatus.CONDITIONAL.value
        else ModelCapabilityGateStatus.APPROVED
    )
    approval_status = approval.get("status") if isinstance(approval, dict) else None
    if task_class in {ModelCapabilityTaskClass.APPLY_PREP, ModelCapabilityTaskClass.APPROVAL_GATED_L1}:
        if approval_status not in {"approved_for_packet_design", "approved_for_disposable_apply"}:
            return blocked_decision(
                reason="model_capability_conditional_approval_missing",
                message=(
                    f"Task class {task_class.value} is only conditionally approved by the model profile "
                    "and requires explicit controller approval before routing."
                ),
                task_class=task_class,
                policy=policy,
                profile=profile,
                profile_entry=profile_entry,
                task_policy_key=task_policy_key,
                task_policy_status=task_policy_status if isinstance(task_policy_status, str) else None,
            )
    if task_class == ModelCapabilityTaskClass.DRAFT_ONLY_L1:
        apply_allowed = approval.get("apply_allowed") if isinstance(approval, dict) else None
        if apply_allowed is True:
            return blocked_decision(
                reason="model_capability_draft_boundary_conflict",
                message="Draft-only L1 routing cannot approve an apply_allowed request.",
                task_class=task_class,
                policy=policy,
                profile=profile,
                profile_entry=profile_entry,
                task_policy_key=task_policy_key,
                task_policy_status=task_policy_status if isinstance(task_policy_status, str) else None,
            )
    return {
        "kind": "model_capability_routing_decision",
        "schema_version": SCHEMA_VERSION,
        "status": status.value,
        "enforcement_mode": "fail_closed",
        "task_class": task_class.value,
        "task_policy_key": task_policy_key,
        "task_policy_status": task_policy_status,
        "profile_id": profile_entry.get("profile_id"),
        "profile_path": str(profile_file),
        "profile_status": profile.get("status"),
        "policy_path": str(policy_file),
        "candidate_model_base_url": profile.get("candidate", {}).get("candidate_model_base_url")
        if isinstance(profile.get("candidate"), dict)
        else None,
        "request_role_base_url": normalize_base_url(role_base_url),
        "request_model": model,
        "required_evidence": task_policy_entry.get("required_evidence", []),
        "conditions": string_list(rule.get("conditions")),
        "blockers": [],
    }


def model_capability_blockers(decision: dict[str, Any]) -> list[dict[str, str]]:
    blockers = decision.get("blockers")
    if not isinstance(blockers, list):
        return []
    return [
        {
            "reason": str(item.get("reason") or "model_capability_blocked"),
            "message": str(item.get("message") or "Model capability routing blocked this request."),
        }
        for item in blockers
        if isinstance(item, dict)
    ]
