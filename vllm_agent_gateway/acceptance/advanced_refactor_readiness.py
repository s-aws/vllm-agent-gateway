"""Phase 105 advanced-refactor readiness gate.

This gate is intentionally read-only. It composes existing proof artifacts and
decides whether a limited pilot prompt set may be reviewed; it never promotes
broad refactor orchestration into stable runtime behavior.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
DEFAULT_REPORT_DIR = Path("runtime-state") / "advanced-refactor-readiness"
DEFAULT_GATE_REPORT_PATH = DEFAULT_REPORT_DIR / "phase105-readiness.json"
DEFAULT_TARGET_ROOTS = (
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
)
DEFAULT_PORT_LABELS = {
    "localhost-model",
    "llm-gateway",
    "controller",
    "workflow-router-gateway",
    "reviewer-code",
    "tester-code",
    "architect-default",
    "dispatcher-default",
    "implementer-default",
    "researcher-default",
    "documenter-default",
}
DEFAULT_CONTROLLER_ARTIFACT_ROOTS = (
    Path("runtime-state") / "controller-artifacts",
    Path("C:/private_agentic_agents/runtime-state/controller-artifacts"),
    Path("/mnt/c/private_agentic_agents/runtime-state/controller-artifacts"),
)
DEFAULT_IMPLEMENTATION_PREP_REPORTS = (
    Path("runtime-state/implementation-prep-expansion/phase96-implementation-prep-direct.json"),
    Path("runtime-state/implementation-prep-expansion/phase96-implementation-prep-gateway.json"),
    Path("runtime-state/implementation-prep-expansion/phase96-implementation-prep-anythingllm.json"),
)
DEFAULT_APPROVAL_CONTINUATION_REPORTS = (
    Path("runtime-state/approval-continuation-robustness/phase97-approval-direct.json"),
    Path("runtime-state/approval-continuation-robustness/phase97-approval-gateway.json"),
    Path("runtime-state/approval-continuation-robustness/phase97-approval-anythingllm.json"),
)
DEFAULT_DISPOSABLE_APPLY_REPORTS = (
    Path("runtime-state/disposable-apply-expansion/phase98-direct.json"),
    Path("runtime-state/disposable-apply-expansion/phase98-gateway.json"),
    Path("runtime-state/disposable-apply-expansion/phase98-anythingllm.json"),
)
DEFAULT_MULTI_REPO_REPORT = Path("runtime-state/multi-repo-fixtures/phase101-gateway-anythingllm.json")
DEFAULT_TASK_DECOMPOSITION_REPORT = Path("runtime-state/task-decomposition/phase102-live.json")
DEFAULT_EVAL_REPAIR_LOOP_REPORT = Path("runtime-state/eval-repair-loop/phase104-live-failed-founder-repair.json")
DEFAULT_MODEL_POLICY = Path("runtime/model_capability_routing.json")
REQUIRED_PREREQUISITE_IDS = (
    "implementation_prep_proven",
    "approval_continuation_proven",
    "disposable_apply_proven",
    "rollback_proven",
    "verification_proven",
    "multi_repo_fixture_coverage_proven",
    "advanced_refactor_deferral_proven",
    "model_policy_real_apply_blocked",
    "eval_repair_loop_proven",
)


class AdvancedRefactorReadinessReportStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class AdvancedRefactorReadinessStatus(str, Enum):
    BLOCKED = "blocked"
    PILOT_READY = "pilot_ready"


class PrerequisiteStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    MISSING = "missing"


class PilotPromptSetStatus(str, Enum):
    BLOCKED = "blocked"
    ADMITTED = "admitted"


class PilotMutationPolicy(str, Enum):
    NOT_ADMITTED = "not_admitted"
    APPROVAL_GATED_DISPOSABLE_COPY_ONLY = "approval_gated_disposable_copy_only"


class StablePromotionStatus(str, Enum):
    BLOCKED_REQUIRES_LATER_EXPLICIT_PROMOTION = "blocked_requires_later_explicit_promotion"


@dataclass(frozen=True)
class AdvancedRefactorReadinessConfig:
    config_root: Path
    implementation_prep_reports: tuple[Path, ...] = DEFAULT_IMPLEMENTATION_PREP_REPORTS
    approval_continuation_reports: tuple[Path, ...] = DEFAULT_APPROVAL_CONTINUATION_REPORTS
    disposable_apply_reports: tuple[Path, ...] = DEFAULT_DISPOSABLE_APPLY_REPORTS
    multi_repo_report: Path = DEFAULT_MULTI_REPO_REPORT
    task_decomposition_report: Path = DEFAULT_TASK_DECOMPOSITION_REPORT
    eval_repair_loop_report: Path = DEFAULT_EVAL_REPAIR_LOOP_REPORT
    model_policy_path: Path = DEFAULT_MODEL_POLICY
    advanced_refactor_deferred_plan_paths: tuple[Path, ...] = ()
    controller_artifact_roots: tuple[Path, ...] = DEFAULT_CONTROLLER_ARTIFACT_ROOTS
    target_roots: tuple[str, ...] = DEFAULT_TARGET_ROOTS
    output_path: Path | None = None
    markdown_output_path: Path | None = None


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"advanced-refactor-readiness-{utc_timestamp()}.json"


def default_markdown_path(report_path: Path) -> Path:
    return report_path.with_suffix(".md")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def object_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def resolve_path(config_root: Path, path: Path) -> Path:
    if path.is_absolute():
        return host_readable_path(path) or path
    return host_readable_path(config_root / path) or config_root / path


def host_readable_path(path: Path) -> Path | None:
    candidates = [path]
    text = path.as_posix()
    mount_match = re.match(r"^/mnt/([A-Za-z])/(.+)$", text)
    if mount_match and os.name == "nt":
        candidates.append(Path(f"{mount_match.group(1).upper()}:/{mount_match.group(2)}"))
    for candidate in candidates:
        try:
            if candidate.exists():
                return candidate
        except OSError:
            continue
    return None


def read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    readable = host_readable_path(path) or path
    try:
        value = json.loads(readable.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, f"missing report: {path}"
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON at {path}: {exc}"
    if not isinstance(value, dict):
        return None, f"report must be a JSON object: {path}"
    return value, None


def evidence_ref(path: Path, marker: str = "") -> str:
    suffix = f":{marker}" if marker else ""
    return f"{path.as_posix()}{suffix}"


def target_roots_present(values: list[str], expected_roots: tuple[str, ...]) -> bool:
    return set(expected_roots).issubset(set(values))


def checks_from_report(report: dict[str, Any]) -> list[dict[str, Any]]:
    checks = report.get("checks")
    return object_list(checks)


def prerequisite(
    prerequisite_id: str,
    *,
    name: str,
    required_evidence: list[str],
    evidence_refs: list[str],
    details: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    status = PrerequisiteStatus.PASSED
    if errors:
        status = PrerequisiteStatus.FAILED
    if any(error.startswith("missing report:") for error in errors):
        status = PrerequisiteStatus.MISSING
    return {
        "id": prerequisite_id,
        "name": name,
        "status": status.value,
        "required_evidence": required_evidence,
        "evidence_refs": evidence_refs,
        "details": details,
        "errors": errors,
    }


def expected_surface(path: Path) -> str:
    name = path.name.lower()
    if "anythingllm" in name:
        return "anythingllm"
    if "gateway" in name:
        return "gateway"
    return "direct"


def require_report(
    *,
    config_root: Path,
    path: Path,
    expected_kind: str,
    evidence_refs: list[str],
    errors: list[str],
) -> dict[str, Any] | None:
    resolved = resolve_path(config_root, path)
    report, error = read_json(resolved)
    evidence_refs.append(evidence_ref(resolved))
    if error:
        errors.append(error)
        return None
    if report is None:
        errors.append(f"missing report: {resolved}")
        return None
    if report.get("kind") != expected_kind:
        errors.append(f"{path} kind must be {expected_kind}, got {report.get('kind')!r}")
    if report.get("status") != "passed":
        errors.append(f"{path} status must be passed, got {report.get('status')!r}")
    return report


def evaluate_implementation_prep(config: AdvancedRefactorReadinessConfig) -> dict[str, Any]:
    errors: list[str] = []
    evidence_refs: list[str] = []
    surfaces: dict[str, dict[str, Any]] = {}
    for path in config.implementation_prep_reports:
        report = require_report(
            config_root=config.config_root,
            path=path,
            expected_kind="implementation_prep_expansion_report",
            evidence_refs=evidence_refs,
            errors=errors,
        )
        if report is None:
            continue
        surface = expected_surface(path)
        summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
        if not summary.get(f"{surface}_enabled"):
            errors.append(f"{path} must have summary.{surface}_enabled=true")
        if string_list(summary.get("failed_check_ids")):
            errors.append(f"{path} failed_check_ids must be empty")
        checks = checks_from_report(report)
        if not checks:
            errors.append(f"{path} must include checks")
        failed_checks = [item.get("id") for item in checks if item.get("status") != "passed"]
        if failed_checks:
            errors.append(f"{path} has non-passed checks: {failed_checks}")
        ready_proposals = 0
        verification_commands = 0
        source_mutation_flags: list[Any] = []
        covered_target_roots: set[str] = set()
        for check in checks:
            details = check.get("details")
            if not isinstance(details, dict):
                continue
            if isinstance(details.get("target_root"), str):
                covered_target_roots.add(details["target_root"])
            if details.get("proposal_status") == "ready":
                ready_proposals += 1
            if details.get("downstream_repo_mutated") is not None:
                source_mutation_flags.append(details.get("downstream_repo_mutated"))
            if details.get("summary_source_changed") is not None:
                source_mutation_flags.append(details.get("summary_source_changed"))
            verification_commands += int(details.get("downstream_verification_command_count") or 0)
            verification_commands += len(string_list(details.get("proposal_verification_commands")))
        if ready_proposals < 1:
            errors.append(f"{path} must include at least one ready implementation-prep proposal")
        if verification_commands < 1:
            errors.append(f"{path} must include at least one verification command")
        if any(flag is not False for flag in source_mutation_flags):
            errors.append(f"{path} implementation prep must not mutate source or downstream repo")
        if surface in {"gateway", "anythingllm"} and not target_roots_present(sorted(covered_target_roots), config.target_roots):
            errors.append(f"{path} must cover both frozen target roots")
        surfaces[surface] = {
            "path": str(resolve_path(config.config_root, path)),
            "check_count": len(checks),
            "ready_proposal_count": ready_proposals,
            "verification_command_count": verification_commands,
            "covered_target_roots": sorted(covered_target_roots),
        }
    missing_surfaces = sorted({"direct", "gateway", "anythingllm"} - set(surfaces))
    if missing_surfaces:
        errors.append(f"implementation prep is missing surfaces: {missing_surfaces}")
    return prerequisite(
        "implementation_prep_proven",
        name="Implementation prep is draft-only, produces packet proposals, and records verification commands.",
        required_evidence=[
            "Phase 96 direct report passed",
            "Phase 96 gateway report passed",
            "Phase 96 AnythingLLM report passed",
            "ready proposal artifact exists",
            "source mutation flags are false",
            "verification commands are present",
        ],
        evidence_refs=evidence_refs,
        details={"surfaces": surfaces},
        errors=errors,
    )


def evaluate_approval_continuation(config: AdvancedRefactorReadinessConfig) -> dict[str, Any]:
    errors: list[str] = []
    evidence_refs: list[str] = []
    surfaces: dict[str, dict[str, Any]] = {}
    required_error_keys = {
        "wrong_run_error",
        "duplicate_error",
        "denial_error",
        "target_mismatch_error",
        "scope_change_error",
    }
    for path in config.approval_continuation_reports:
        report = require_report(
            config_root=config.config_root,
            path=path,
            expected_kind="approval_continuation_robustness_report",
            evidence_refs=evidence_refs,
            errors=errors,
        )
        if report is None:
            continue
        surface = expected_surface(path)
        summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
        if not summary.get(f"{surface}_enabled"):
            errors.append(f"{path} must have summary.{surface}_enabled=true")
        if int(summary.get("failed_count") or 0) != 0:
            errors.append(f"{path} failed_count must be 0")
        if not target_roots_present(string_list(summary.get("target_roots")), config.target_roots):
            errors.append(f"{path} must cover both frozen target roots")
        checks = checks_from_report(report)
        if not checks:
            errors.append(f"{path} must include checks")
        failed_checks = [item.get("id") for item in checks if item.get("status") != "passed"]
        if failed_checks:
            errors.append(f"{path} has non-passed checks: {failed_checks}")
        observed_error_keys: set[str] = set()
        fixture_guards = 0
        for check in checks:
            details = check.get("details")
            if not isinstance(details, dict):
                continue
            observed_error_keys.update(key for key in required_error_keys if isinstance(details.get(key), str))
            if details.get("fixture_state_unchanged") is True:
                fixture_guards += 1
        missing_error_keys = sorted(required_error_keys - observed_error_keys)
        if missing_error_keys:
            errors.append(f"{path} missing approval rejection proof fields: {missing_error_keys}")
        if fixture_guards < 1:
            errors.append(f"{path} must prove fixture_state_unchanged=true")
        surfaces[surface] = {
            "path": str(resolve_path(config.config_root, path)),
            "check_count": len(checks),
            "rejection_fields": sorted(observed_error_keys),
            "fixture_guard_count": fixture_guards,
        }
    missing_surfaces = sorted({"direct", "gateway", "anythingllm"} - set(surfaces))
    if missing_surfaces:
        errors.append(f"approval continuation is missing surfaces: {missing_surfaces}")
    return prerequisite(
        "approval_continuation_proven",
        name="Approval continuations bind to source run identity and reject stale, duplicate, denied, and scope-changing continuations.",
        required_evidence=[
            "Phase 97 direct report passed",
            "Phase 97 gateway report passed",
            "Phase 97 AnythingLLM report passed",
            "wrong-run, duplicate, denial, target-mismatch, and scope-change rejections exist",
            "protected fixture state remains unchanged",
        ],
        evidence_refs=evidence_refs,
        details={"surfaces": surfaces},
        errors=errors,
    )


def disposable_case_details(report: dict[str, Any]) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    for check in checks_from_report(report):
        item = check.get("details")
        if isinstance(item, dict) and isinstance(item.get("case_id"), str):
            details.append(item)
    return details


def evaluate_disposable_apply(config: AdvancedRefactorReadinessConfig) -> dict[str, Any]:
    errors: list[str] = []
    evidence_refs: list[str] = []
    surfaces: dict[str, dict[str, Any]] = {}
    for path in config.disposable_apply_reports:
        report = require_report(
            config_root=config.config_root,
            path=path,
            expected_kind="disposable_apply_expansion_report",
            evidence_refs=evidence_refs,
            errors=errors,
        )
        if report is None:
            continue
        surface = expected_surface(path)
        summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
        if not summary.get(f"{surface}_enabled"):
            errors.append(f"{path} must have summary.{surface}_enabled=true")
        if string_list(summary.get("failed_check_ids")):
            errors.append(f"{path} failed_check_ids must be empty")
        if int(summary.get("case_count") or 0) < 3:
            errors.append(f"{path} must cover at least three disposable apply cases")
        if int(summary.get("live_case_count") or 0) < 2 and surface != "direct":
            errors.append(f"{path} must cover at least two live disposable apply cases")
        checks = checks_from_report(report)
        failed_checks = [item.get("id") for item in checks if item.get("status") != "passed"]
        if failed_checks:
            errors.append(f"{path} has non-passed checks: {failed_checks}")
        case_details = disposable_case_details(report)
        changed_copy_cases = [
            item
            for item in case_details
            if item.get("case_id") in {"DAE-001", "DAE-002"}
            and item.get("source_tree_changed") is False
            and item.get("copy_tree_restored") is True
            and item.get("fixture_state_unchanged") is True
        ]
        create_file_blocks = [
            item
            for item in case_details
            if item.get("case_id") == "DAE-003"
            and item.get("fixture_state_unchanged") is True
            and isinstance(item.get("blocked"), dict)
            and item["blocked"].get("error_code") == "unsupported_disposable_operation_kind"
        ]
        if len(changed_copy_cases) < 2:
            errors.append(f"{path} must prove DAE-001 and DAE-002 changed only disposable copies and restored them")
        protected_source_refusals = [
            check
            for check in checks
            if isinstance(check.get("id"), str)
            and "protected_source_apply_refusal" in check["id"]
            and check.get("status") == "passed"
            and isinstance(check.get("details"), dict)
            and check["details"].get("fixture_state_unchanged") is True
            and isinstance(check["details"].get("target_root"), str)
        ]
        protected_refusal_roots = sorted(
            {
                check["details"]["target_root"]
                for check in protected_source_refusals
                if isinstance(check.get("details"), dict)
            }
        )
        if surface == "direct" and not create_file_blocks:
            errors.append(f"{path} must prove unsupported create_file is blocked")
        if surface in {"gateway", "anythingllm"} and not target_roots_present(protected_refusal_roots, config.target_roots):
            errors.append(f"{path} must prove protected source-apply refusal on both frozen target roots")
        surfaces[surface] = {
            "path": str(resolve_path(config.config_root, path)),
            "check_count": len(checks),
            "disposable_copy_cases": len(changed_copy_cases),
            "create_file_block_count": len(create_file_blocks),
            "protected_source_refusal_roots": protected_refusal_roots,
        }
    missing_surfaces = sorted({"direct", "gateway", "anythingllm"} - set(surfaces))
    if missing_surfaces:
        errors.append(f"disposable apply is missing surfaces: {missing_surfaces}")
    return prerequisite(
        "disposable_apply_proven",
        name="Disposable-copy apply is approval-gated, source-safe, and blocks unsupported operation kinds.",
        required_evidence=[
            "Phase 98 direct report passed",
            "Phase 98 gateway report passed",
            "Phase 98 AnythingLLM report passed",
            "DAE-001 and DAE-002 mutate only disposable copies",
            "direct DAE-003 blocks create_file",
            "gateway and AnythingLLM protected source-apply refusal covers both frozen roots",
        ],
        evidence_refs=evidence_refs,
        details={"surfaces": surfaces},
        errors=errors,
    )


def evaluate_rollback(config: AdvancedRefactorReadinessConfig) -> dict[str, Any]:
    errors: list[str] = []
    evidence_refs: list[str] = []
    restored_cases = 0
    source_safe_cases = 0
    for path in config.disposable_apply_reports:
        report = require_report(
            config_root=config.config_root,
            path=path,
            expected_kind="disposable_apply_expansion_report",
            evidence_refs=evidence_refs,
            errors=errors,
        )
        if report is None:
            continue
        for item in disposable_case_details(report):
            if item.get("case_id") in {"DAE-001", "DAE-002"}:
                if item.get("copy_tree_restored") is True:
                    restored_cases += 1
                if item.get("source_tree_changed") is False and item.get("fixture_state_unchanged") is True:
                    source_safe_cases += 1
    if restored_cases < 6:
        errors.append("rollback proof must include restored disposable copies for DAE-001 and DAE-002 across direct, gateway, and AnythingLLM")
    if source_safe_cases < 6:
        errors.append("rollback proof must include unchanged source fixture guards across direct, gateway, and AnythingLLM")
    return prerequisite(
        "rollback_proven",
        name="Rollback proof confirms disposable copies are restored and protected sources remain unchanged.",
        required_evidence=[
            "copy_tree_restored=true for DAE-001 and DAE-002 on direct, gateway, and AnythingLLM",
            "source_tree_changed=false and fixture_state_unchanged=true for those cases",
        ],
        evidence_refs=evidence_refs,
        details={"restored_case_count": restored_cases, "source_safe_case_count": source_safe_cases},
        errors=errors,
    )


def evaluate_verification(config: AdvancedRefactorReadinessConfig) -> dict[str, Any]:
    errors: list[str] = []
    evidence_refs: list[str] = []
    verification_command_count = 0
    surfaces: set[str] = set()
    for path in config.implementation_prep_reports:
        report = require_report(
            config_root=config.config_root,
            path=path,
            expected_kind="implementation_prep_expansion_report",
            evidence_refs=evidence_refs,
            errors=errors,
        )
        if report is None:
            continue
        surface = expected_surface(path)
        for check in checks_from_report(report):
            details = check.get("details")
            if not isinstance(details, dict):
                continue
            count = int(details.get("downstream_verification_command_count") or 0)
            count += len(string_list(details.get("proposal_verification_commands")))
            if count:
                verification_command_count += count
                surfaces.add(surface)
    if verification_command_count < 3:
        errors.append("verification proof must include implementation-prep verification commands across surfaces")
    if surfaces != {"direct", "gateway", "anythingllm"}:
        errors.append(f"verification proof must cover direct, gateway, and AnythingLLM surfaces, got {sorted(surfaces)}")
    return prerequisite(
        "verification_proven",
        name="Verification commands are emitted before any advanced refactor pilot can be admitted.",
        required_evidence=[
            "proposal verification commands exist",
            "downstream verification commands exist",
            "verification proof covers direct, gateway, and AnythingLLM",
        ],
        evidence_refs=evidence_refs,
        details={"verification_command_count": verification_command_count, "surfaces": sorted(surfaces)},
        errors=errors,
    )


def evaluate_multi_repo(config: AdvancedRefactorReadinessConfig) -> dict[str, Any]:
    errors: list[str] = []
    evidence_refs: list[str] = []
    report = require_report(
        config_root=config.config_root,
        path=config.multi_repo_report,
        expected_kind="multi_repo_fixture_live_report",
        evidence_refs=evidence_refs,
        errors=errors,
    )
    details: dict[str, Any] = {}
    if report is not None:
        summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
        clients = set(string_list(summary.get("clients")))
        categories = set(string_list(summary.get("categories")))
        if {"gateway", "anythingllm"} - clients:
            errors.append("multi-repo report must cover gateway and AnythingLLM clients")
        required_categories = {
            "real-world-python-git",
            "real-world-python-non-git",
            "synthetic-python-service",
            "synthetic-node-cli",
            "synthetic-go-http-service",
        }
        if required_categories - categories:
            errors.append(f"multi-repo report missing categories: {sorted(required_categories - categories)}")
        cases = object_list(report.get("cases"))
        frozen_cases = [
            item
            for item in cases
            if item.get("target_root") in set(config.target_roots)
            and item.get("client") in {"gateway", "anythingllm"}
            and item.get("status") == "passed"
            and item.get("source_unchanged") is True
            and item.get("git_status_unchanged") is True
        ]
        if len(frozen_cases) < 4:
            errors.append("multi-repo report must include passed gateway and AnythingLLM cases for both frozen Coinbase fixtures")
        port_failures = [item for item in object_list(report.get("port_health")) if item.get("status") != "passed"]
        if port_failures:
            errors.append(f"multi-repo port health failures: {port_failures}")
        details = {
            "clients": sorted(clients),
            "categories": sorted(categories),
            "frozen_case_count": len(frozen_cases),
            "port_health_count": len(object_list(report.get("port_health"))),
        }
    return prerequisite(
        "multi_repo_fixture_coverage_proven",
        name="Gateway and AnythingLLM validation covers both frozen Coinbase fixtures and synthetic repo layouts.",
        required_evidence=[
            "Phase 101 multi-repo report passed",
            "gateway and AnythingLLM clients are both covered",
            "both frozen Coinbase fixtures are covered",
            "protected fixture state remains unchanged",
        ],
        evidence_refs=evidence_refs,
        details=details,
        errors=errors,
    )


def deferred_plan_candidates(config: AdvancedRefactorReadinessConfig, run_id: str) -> list[Path]:
    candidates: list[Path] = []
    for root in config.controller_artifact_roots:
        resolved_root = resolve_path(config.config_root, root)
        candidates.append(resolved_root / "task-decompositions" / run_id / "task-decomposition.json")
    return candidates


def find_deferred_plan(config: AdvancedRefactorReadinessConfig, run_id: str) -> Path | None:
    for candidate in deferred_plan_candidates(config, run_id):
        readable = host_readable_path(candidate)
        if readable is not None:
            return readable
    return None


def validate_deferred_plan(path: Path, plan: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if plan.get("kind") != "task_decomposition":
        errors.append(f"{path} kind must be task_decomposition")
    expected = {
        "status": "blocked",
        "prompt_family": "advanced_refactor_deferred",
        "deferred_to_phase": 105,
        "mutation_policy": "unsupported_deferred_until_phase_105",
        "target_repository_changed": False,
        "runtime_registry_changed": False,
    }
    wrong = {key: {"expected": expected_value, "actual": plan.get(key)} for key, expected_value in expected.items() if plan.get(key) != expected_value}
    if wrong:
        errors.append(f"{path} deferred plan mismatch: {json.dumps(wrong, ensure_ascii=True, sort_keys=True)}")
    if plan.get("selected_workflow_ids") != []:
        errors.append(f"{path} must not select executable workflows")
    if plan.get("selected_skill_ids") != []:
        errors.append(f"{path} must not select skills")
    if plan.get("selected_tool_ids") != []:
        errors.append(f"{path} must not select tools")
    if plan.get("approval_gates") != []:
        errors.append(f"{path} must not create approval gates")
    work_packages = object_list(plan.get("work_packages"))
    package_ids = [item.get("id") for item in work_packages]
    if package_ids != ["DEFER1"]:
        errors.append(f"{path} must include only DEFER1, got {package_ids}")
    if any(item.get("workflow_id") is not None for item in work_packages):
        errors.append(f"{path} DEFER1 must not have workflow_id")
    text = json.dumps(plan, ensure_ascii=True).lower()
    if "packet-preview" in text or "implementation-packet" in text:
        errors.append(f"{path} must not include implementation packet artifacts")
    return errors


def validate_task_decomposition_live_report(
    report: dict[str, Any],
    *,
    path: Path,
    config: AdvancedRefactorReadinessConfig,
    evidence_refs: list[str],
    errors: list[str],
) -> dict[str, Any]:
    details: dict[str, Any] = {}
    checks = report.get("checks")
    if not isinstance(checks, dict):
        errors.append(f"{path} checks must be an object grouped by surface")
        return details
    for surface in ("direct", "gateway", "anythingllm"):
        rows = object_list(checks.get(surface))
        roots = [str(item.get("target_root")) for item in rows if isinstance(item.get("target_root"), str)]
        if not target_roots_present(roots, config.target_roots):
            errors.append(f"{path} {surface} checks must cover both frozen target roots")
    ports = object_list(checks.get("ports"))
    passed_port_labels = {str(item.get("label")) for item in ports if item.get("status") == "passed"}
    if DEFAULT_PORT_LABELS - passed_port_labels:
        errors.append(f"{path} missing passed featured ports: {sorted(DEFAULT_PORT_LABELS - passed_port_labels)}")
    if report.get("runtime_changed_files") != []:
        errors.append(f"{path} runtime_changed_files must be empty")
    if report.get("target_changed_files") != {}:
        errors.append(f"{path} target_changed_files must be empty")
    plan_paths = list(config.advanced_refactor_deferred_plan_paths)
    if not plan_paths:
        for row in object_list(checks.get("direct")):
            run_id = row.get("deferred_run_id")
            if isinstance(run_id, str) and run_id:
                found = find_deferred_plan(config, run_id)
                if found is None:
                    errors.append(f"missing deferred task-decomposition artifact for run {run_id}")
                else:
                    plan_paths.append(found)
    validated_plan_count = 0
    for raw_plan_path in plan_paths:
        resolved = resolve_path(config.config_root, raw_plan_path)
        plan, error = read_json(resolved)
        evidence_refs.append(evidence_ref(resolved, "advanced_refactor_deferred_plan"))
        if error:
            errors.append(error)
            continue
        if plan is None:
            errors.append(f"missing deferred task-decomposition artifact: {resolved}")
            continue
        plan_errors = validate_deferred_plan(resolved, plan)
        if plan_errors:
            errors.extend(plan_errors)
        else:
            validated_plan_count += 1
    if validated_plan_count < len(config.target_roots):
        errors.append("advanced refactor deferral proof must validate a deferred plan for each frozen target root")
    details = {
        "direct_case_count": len(object_list(checks.get("direct"))),
        "gateway_case_count": len(object_list(checks.get("gateway"))),
        "anythingllm_case_count": len(object_list(checks.get("anythingllm"))),
        "passed_port_labels": sorted(passed_port_labels),
        "validated_deferred_plan_count": validated_plan_count,
    }
    return details


def evaluate_advanced_refactor_deferral(config: AdvancedRefactorReadinessConfig) -> dict[str, Any]:
    errors: list[str] = []
    evidence_refs: list[str] = []
    report = require_report(
        config_root=config.config_root,
        path=config.task_decomposition_report,
        expected_kind="task_decomposition_live_validation",
        evidence_refs=evidence_refs,
        errors=errors,
    )
    details: dict[str, Any] = {}
    if report is not None:
        details = validate_task_decomposition_live_report(
            report,
            path=resolve_path(config.config_root, config.task_decomposition_report),
            config=config,
            evidence_refs=evidence_refs,
            errors=errors,
        )
    return prerequisite(
        "advanced_refactor_deferral_proven",
        name="Natural advanced-refactor prompts remain blocked and create no executable packages.",
        required_evidence=[
            "Phase 102 live report passed",
            "direct, gateway, AnythingLLM checks cover both frozen fixtures",
            "localhost 8000 and all controller/gateway featured ports pass",
            "advanced-refactor deferred plans are blocked with selected_workflow_ids=[]",
            "no packet artifacts or source mutation are created",
        ],
        evidence_refs=evidence_refs,
        details=details,
        errors=errors,
    )


def evaluate_model_policy(config: AdvancedRefactorReadinessConfig) -> dict[str, Any]:
    errors: list[str] = []
    evidence_refs: list[str] = []
    policy_path = resolve_path(config.config_root, config.model_policy_path)
    policy, error = read_json(policy_path)
    evidence_refs.append(evidence_ref(policy_path))
    details: dict[str, Any] = {}
    if error:
        errors.append(error)
    elif policy is not None:
        if policy.get("kind") != "model_capability_routing_policy":
            errors.append("model policy kind must be model_capability_routing_policy")
        if policy.get("enforcement_mode") != "fail_closed":
            errors.append("model policy must use fail_closed enforcement")
        task_rules = policy.get("task_class_rules") if isinstance(policy.get("task_class_rules"), dict) else {}
        real_apply = task_rules.get("real_apply") if isinstance(task_rules.get("real_apply"), dict) else {}
        if real_apply.get("allowed_task_policy_statuses") != []:
            errors.append("model policy must keep real_apply allowed_task_policy_statuses empty")
        apply_prep = task_rules.get("apply_prep") if isinstance(task_rules.get("apply_prep"), dict) else {}
        if "conditional" not in string_list(apply_prep.get("allowed_task_policy_statuses")):
            errors.append("model policy must keep apply_prep conditional")
        profile_path_text = None
        for entry in object_list(policy.get("profiles")):
            if entry.get("profile_id") == policy.get("default_profile_id") and isinstance(entry.get("profile_path"), str):
                profile_path_text = entry["profile_path"]
                break
        if profile_path_text is None:
            errors.append("model policy must reference a default profile path")
        else:
            profile_path = resolve_path(config.config_root, Path(profile_path_text))
            profile, profile_error = read_json(profile_path)
            evidence_refs.append(evidence_ref(profile_path))
            if profile_error:
                errors.append(profile_error)
            elif profile is not None:
                task_policy = profile.get("task_policy") if isinstance(profile.get("task_policy"), dict) else {}
                real_apply_policy = task_policy.get("real_apply") if isinstance(task_policy.get("real_apply"), dict) else {}
                apply_prep_policy = task_policy.get("apply_prep") if isinstance(task_policy.get("apply_prep"), dict) else {}
                if real_apply_policy.get("status") != "not_approved":
                    errors.append("model profile must keep task_policy.real_apply.status=not_approved")
                if apply_prep_policy.get("status") != "conditional":
                    errors.append("model profile must keep task_policy.apply_prep.status=conditional")
                details["profile_status"] = profile.get("status")
                details["profile_path"] = str(profile_path)
        details["policy_path"] = str(policy_path)
        details["enforcement_mode"] = policy.get("enforcement_mode")
        details["real_apply_allowed_statuses"] = real_apply.get("allowed_task_policy_statuses")
    return prerequisite(
        "model_policy_real_apply_blocked",
        name="Model capability routing remains fail-closed and real repository apply remains unapproved.",
        required_evidence=[
            "runtime/model_capability_routing.json uses fail_closed enforcement",
            "real_apply has no allowed task policy statuses",
            "apply_prep remains conditional",
            "default profile keeps real_apply not_approved",
        ],
        evidence_refs=evidence_refs,
        details=details,
        errors=errors,
    )


def evaluate_eval_repair_loop(config: AdvancedRefactorReadinessConfig) -> dict[str, Any]:
    errors: list[str] = []
    evidence_refs: list[str] = []
    report = require_report(
        config_root=config.config_root,
        path=config.eval_repair_loop_report,
        expected_kind="eval_repair_loop_report",
        evidence_refs=evidence_refs,
        errors=errors,
    )
    details: dict[str, Any] = {}
    if report is not None:
        summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
        if summary.get("fixture_mutation_guard") is not True:
            errors.append("eval repair loop must enforce fixture_mutation_guard=true")
        if int(summary.get("max_repair_cycles_per_issue") or 0) > 2:
            errors.append("eval repair loop max_repair_cycles_per_issue must be <= 2")
        if report.get("blocking_errors"):
            errors.append("eval repair loop blocking_errors must be empty")
        if report.get("validation_errors"):
            errors.append("eval repair loop validation_errors must be empty")
        details = {
            "recommendation_count": summary.get("recommendation_count"),
            "advisory_recommendation_count": summary.get("advisory_recommendation_count"),
            "current_phase_tightening_count": summary.get("current_phase_tightening_count"),
            "fixture_mutation_guard": summary.get("fixture_mutation_guard"),
        }
    return prerequisite(
        "eval_repair_loop_proven",
        name="Eval-driven repair loop is bounded, advisory by default, and fixture-mutation guarded.",
        required_evidence=[
            "Phase 104 repair report passed",
            "fixture mutation guard is true",
            "repair cycles are bounded to two",
            "blocking and validation errors are empty",
        ],
        evidence_refs=evidence_refs,
        details=details,
        errors=errors,
    )


def evaluate_prerequisites(config: AdvancedRefactorReadinessConfig) -> list[dict[str, Any]]:
    return [
        evaluate_implementation_prep(config),
        evaluate_approval_continuation(config),
        evaluate_disposable_apply(config),
        evaluate_rollback(config),
        evaluate_verification(config),
        evaluate_multi_repo(config),
        evaluate_advanced_refactor_deferral(config),
        evaluate_model_policy(config),
        evaluate_eval_repair_loop(config),
    ]


def pilot_prompt_set(readiness_status: AdvancedRefactorReadinessStatus, target_roots: tuple[str, ...]) -> dict[str, Any]:
    if readiness_status != AdvancedRefactorReadinessStatus.PILOT_READY:
        return {
            "status": PilotPromptSetStatus.BLOCKED.value,
            "policy": PilotMutationPolicy.NOT_ADMITTED.value,
            "admitted_prompts": [],
            "candidate_count": 2,
            "reason": "At least one prerequisite is not passed.",
        }
    prompts = [
        {
            "id": "P105-PILOT-001",
            "title": "Single named function duplicate-branch refactor pilot",
            "prompt_template": (
                "In {target_root}, investigate one named function with a suspected duplicate branch. "
                "Create an implementation-prep plan only after approval, and apply only to a disposable copy."
            ),
            "target_roots": list(target_roots),
            "approval_gate": {
                "required": True,
                "required_before": "implementation_prep_or_disposable_apply",
                "allowed_scopes": ["approved_for_packet_design", "approved_for_disposable_apply"],
            },
            "mutation_policy": PilotMutationPolicy.APPROVAL_GATED_DISPOSABLE_COPY_ONLY.value,
            "source_apply_enabled": False,
            "stable_channel_eligible": False,
        },
        {
            "id": "P105-PILOT-002",
            "title": "Single behavior narrowed code-path cleanup pilot",
            "prompt_template": (
                "In {target_root}, start from the logic beginning point for one named behavior, "
                "produce a read-only investigation, wait for approval, then run disposable-copy-only packet proof."
            ),
            "target_roots": list(target_roots),
            "approval_gate": {
                "required": True,
                "required_before": "implementation_prep_or_disposable_apply",
                "allowed_scopes": ["approved_for_packet_design", "approved_for_disposable_apply"],
            },
            "mutation_policy": PilotMutationPolicy.APPROVAL_GATED_DISPOSABLE_COPY_ONLY.value,
            "source_apply_enabled": False,
            "stable_channel_eligible": False,
        },
    ]
    return {
        "status": PilotPromptSetStatus.ADMITTED.value,
        "policy": PilotMutationPolicy.APPROVAL_GATED_DISPOSABLE_COPY_ONLY.value,
        "admitted_prompts": prompts,
        "candidate_count": len(prompts),
        "reason": "All prerequisites passed; pilots remain approval-gated and disposable-copy-only.",
    }


def stable_promotion_block() -> dict[str, Any]:
    return {
        "status": StablePromotionStatus.BLOCKED_REQUIRES_LATER_EXPLICIT_PROMOTION.value,
        "enabled": False,
        "reason": "Phase 105 can admit limited pilots only. Stable broad-refactor promotion requires a later explicit roadmap phase.",
    }


def advanced_refactor_gate_decision(config_root: Path, report_path: Path | None = None) -> dict[str, Any]:
    """Return the fail-closed runtime gate decision for natural advanced-refactor routes."""

    raw_path = report_path or DEFAULT_GATE_REPORT_PATH
    resolved = resolve_path(config_root, raw_path)
    report, error = read_json(resolved)
    if error:
        return {
            "kind": "advanced_refactor_readiness_gate_decision",
            "schema_version": SCHEMA_VERSION,
            "status": "blocked",
            "readiness_status": "missing",
            "report_path": str(resolved),
            "reason": "advanced_refactor_readiness_report_missing_or_unreadable",
            "message": f"Advanced refactor remains blocked until a valid Phase 105 readiness report exists: {error}",
        }
    assert report is not None
    validation_errors = validate_advanced_refactor_readiness_report(report)
    if validation_errors:
        return {
            "kind": "advanced_refactor_readiness_gate_decision",
            "schema_version": SCHEMA_VERSION,
            "status": "blocked",
            "readiness_status": report.get("readiness_status"),
            "report_path": str(resolved),
            "reason": "advanced_refactor_readiness_report_invalid",
            "message": "Advanced refactor remains blocked because the Phase 105 readiness report failed validation.",
            "validation_errors": validation_errors,
        }
    if report.get("status") != AdvancedRefactorReadinessReportStatus.PASSED.value:
        return {
            "kind": "advanced_refactor_readiness_gate_decision",
            "schema_version": SCHEMA_VERSION,
            "status": "blocked",
            "readiness_status": report.get("readiness_status"),
            "report_path": str(resolved),
            "reason": "advanced_refactor_readiness_report_not_passed",
            "message": "Advanced refactor remains blocked because the Phase 105 readiness report did not pass.",
        }
    if report.get("readiness_status") != AdvancedRefactorReadinessStatus.PILOT_READY.value:
        failed = [
            item.get("id")
            for item in object_list(report.get("prerequisites"))
            if item.get("status") != PrerequisiteStatus.PASSED.value
        ]
        return {
            "kind": "advanced_refactor_readiness_gate_decision",
            "schema_version": SCHEMA_VERSION,
            "status": "blocked",
            "readiness_status": report.get("readiness_status"),
            "report_path": str(resolved),
            "reason": "advanced_refactor_readiness_not_ready",
            "message": "Advanced refactor remains blocked because at least one Phase 105 prerequisite is not passed.",
            "failed_prerequisites": failed,
        }
    return {
        "kind": "advanced_refactor_readiness_gate_decision",
        "schema_version": SCHEMA_VERSION,
        "status": "ready",
        "readiness_status": report.get("readiness_status"),
        "report_path": str(resolved),
        "reason": "advanced_refactor_pilot_ready",
        "message": "Phase 105 readiness passed; only approval-gated disposable-copy pilots are admitted.",
        "pilot_policy": report.get("pilot_prompt_set", {}).get("policy")
        if isinstance(report.get("pilot_prompt_set"), dict)
        else None,
        "stable_promotion_status": report.get("stable_promotion", {}).get("status")
        if isinstance(report.get("stable_promotion"), dict)
        else None,
    }


def validate_advanced_refactor_readiness_report(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if report.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if report.get("kind") != "advanced_refactor_readiness_report":
        errors.append("kind must be advanced_refactor_readiness_report")
    if report.get("status") not in {item.value for item in AdvancedRefactorReadinessReportStatus}:
        errors.append("status must be passed or failed")
    readiness_status = report.get("readiness_status")
    if readiness_status not in {item.value for item in AdvancedRefactorReadinessStatus}:
        errors.append("readiness_status must be blocked or pilot_ready")
    prerequisites = object_list(report.get("prerequisites"))
    if not prerequisites:
        errors.append("prerequisites must be non-empty")
    prerequisite_ids = [item.get("id") for item in prerequisites]
    valid_prerequisite_ids = [item for item in prerequisite_ids if isinstance(item, str)]
    missing_prerequisite_ids = sorted(set(REQUIRED_PREREQUISITE_IDS) - set(valid_prerequisite_ids))
    extra_prerequisite_ids = sorted(set(valid_prerequisite_ids) - set(REQUIRED_PREREQUISITE_IDS))
    if missing_prerequisite_ids:
        errors.append(f"prerequisites missing required Phase 105 IDs: {missing_prerequisite_ids}")
    if extra_prerequisite_ids:
        errors.append(f"prerequisites include unknown Phase 105 IDs: {extra_prerequisite_ids}")
    if len(valid_prerequisite_ids) != len(set(valid_prerequisite_ids)):
        errors.append("prerequisites must not contain duplicate IDs")
    for item in prerequisites:
        if item.get("status") not in {status.value for status in PrerequisiteStatus}:
            errors.append(f"prerequisite {item.get('id')} has invalid status")
        if not string_list(item.get("required_evidence")):
            errors.append(f"prerequisite {item.get('id')} must name required_evidence")
        if not string_list(item.get("evidence_refs")):
            errors.append(f"prerequisite {item.get('id')} must include evidence_refs")
    all_prereqs_passed = all(item.get("status") == PrerequisiteStatus.PASSED.value for item in prerequisites)
    pilot_set = report.get("pilot_prompt_set") if isinstance(report.get("pilot_prompt_set"), dict) else {}
    if readiness_status == AdvancedRefactorReadinessStatus.PILOT_READY.value and not all_prereqs_passed:
        errors.append("readiness_status cannot be pilot_ready unless all prerequisites passed")
    if readiness_status == AdvancedRefactorReadinessStatus.BLOCKED.value and all_prereqs_passed:
        errors.append("readiness_status cannot be blocked when all prerequisites passed")
    if readiness_status == AdvancedRefactorReadinessStatus.BLOCKED.value:
        if pilot_set.get("status") != PilotPromptSetStatus.BLOCKED.value:
            errors.append("blocked readiness must keep pilot_prompt_set.status=blocked")
        if object_list(pilot_set.get("admitted_prompts")):
            errors.append("blocked readiness must not admit pilot prompts")
    if readiness_status == AdvancedRefactorReadinessStatus.PILOT_READY.value:
        if pilot_set.get("status") != PilotPromptSetStatus.ADMITTED.value:
            errors.append("pilot_ready readiness must admit the limited pilot prompt set")
        if pilot_set.get("policy") != PilotMutationPolicy.APPROVAL_GATED_DISPOSABLE_COPY_ONLY.value:
            errors.append("admitted pilots must use approval_gated_disposable_copy_only policy")
        prompts = object_list(pilot_set.get("admitted_prompts"))
        if not prompts:
            errors.append("pilot_ready readiness must include admitted prompts")
        for prompt in prompts:
            approval_gate = prompt.get("approval_gate") if isinstance(prompt.get("approval_gate"), dict) else {}
            if approval_gate.get("required") is not True:
                errors.append(f"pilot prompt {prompt.get('id')} must require approval")
            if prompt.get("mutation_policy") != PilotMutationPolicy.APPROVAL_GATED_DISPOSABLE_COPY_ONLY.value:
                errors.append(f"pilot prompt {prompt.get('id')} must be disposable-copy-only")
            if prompt.get("source_apply_enabled") is not False:
                errors.append(f"pilot prompt {prompt.get('id')} must keep source_apply_enabled=false")
            if prompt.get("stable_channel_eligible") is not False:
                errors.append(f"pilot prompt {prompt.get('id')} must keep stable_channel_eligible=false")
    stable = report.get("stable_promotion") if isinstance(report.get("stable_promotion"), dict) else {}
    if stable.get("enabled") is not False:
        errors.append("stable_promotion.enabled must remain false")
    if stable.get("status") != StablePromotionStatus.BLOCKED_REQUIRES_LATER_EXPLICIT_PROMOTION.value:
        errors.append("stable_promotion.status must require later explicit promotion")
    runtime_behavior = report.get("runtime_behavior") if isinstance(report.get("runtime_behavior"), dict) else {}
    if runtime_behavior.get("router_behavior_changed") is not False:
        errors.append("Phase 105 readiness report must not change router behavior")
    if runtime_behavior.get("broad_refactor_runtime_enabled") is not False:
        errors.append("Phase 105 readiness report must not enable broad refactor runtime behavior")
    return errors


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Advanced Refactor Readiness Report",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Readiness: `{report.get('readiness_status')}`",
        f"- Pilot policy: `{report.get('pilot_prompt_set', {}).get('policy')}`",
        f"- Stable promotion: `{report.get('stable_promotion', {}).get('status')}`",
        "",
        "## Prerequisites",
        "",
    ]
    for item in object_list(report.get("prerequisites")):
        lines.append(f"- `{item.get('id')}`: `{item.get('status')}`")
        for error in string_list(item.get("errors")):
            lines.append(f"  - error: {error}")
        for ref in string_list(item.get("evidence_refs"))[:5]:
            lines.append(f"  - evidence: `{ref}`")
    lines.extend(["", "## Pilot Prompt Set", ""])
    pilot_set = report.get("pilot_prompt_set") if isinstance(report.get("pilot_prompt_set"), dict) else {}
    lines.append(f"- Status: `{pilot_set.get('status')}`")
    lines.append(f"- Policy: `{pilot_set.get('policy')}`")
    for prompt in object_list(pilot_set.get("admitted_prompts")):
        lines.append(f"- `{prompt.get('id')}`: {prompt.get('title')}")
    lines.extend(["", "## Validation Errors", ""])
    errors = string_list(report.get("validation_errors"))
    if errors:
        for error in errors:
            lines.append(f"- {error}")
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def run_advanced_refactor_readiness(config: AdvancedRefactorReadinessConfig) -> dict[str, Any]:
    prerequisites = evaluate_prerequisites(config)
    all_prereqs_passed = all(item["status"] == PrerequisiteStatus.PASSED.value for item in prerequisites)
    readiness_status = (
        AdvancedRefactorReadinessStatus.PILOT_READY
        if all_prereqs_passed
        else AdvancedRefactorReadinessStatus.BLOCKED
    )
    report_path = resolve_path(config.config_root, config.output_path) if config.output_path else default_report_path(config.config_root)
    markdown_path = (
        resolve_path(config.config_root, config.markdown_output_path)
        if config.markdown_output_path
        else default_markdown_path(report_path)
    )
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "advanced_refactor_readiness_report",
        "created_at": utc_now(),
        "status": AdvancedRefactorReadinessReportStatus.PASSED.value,
        "readiness_status": readiness_status.value,
        "summary": {
            "prerequisite_count": len(prerequisites),
            "passed_prerequisite_count": sum(1 for item in prerequisites if item["status"] == PrerequisiteStatus.PASSED.value),
            "failed_prerequisite_count": sum(1 for item in prerequisites if item["status"] == PrerequisiteStatus.FAILED.value),
            "missing_prerequisite_count": sum(1 for item in prerequisites if item["status"] == PrerequisiteStatus.MISSING.value),
            "broad_refactor_runtime_enabled": False,
            "stable_promotion_enabled": False,
        },
        "target_roots": list(config.target_roots),
        "prerequisites": prerequisites,
        "pilot_prompt_set": pilot_prompt_set(readiness_status, config.target_roots),
        "stable_promotion": stable_promotion_block(),
        "runtime_behavior": {
            "router_behavior_changed": False,
            "broad_refactor_runtime_enabled": False,
            "natural_advanced_refactor_prompt_behavior": (
                "blocked by task.decompose advanced_refactor_deferred proof unless a later explicit runtime phase changes it"
            ),
        },
        "validation_errors": [],
        "report_path": str(report_path),
        "markdown_report_path": str(markdown_path),
    }
    validation_errors = validate_advanced_refactor_readiness_report(report)
    report["validation_errors"] = validation_errors
    if validation_errors:
        report["status"] = AdvancedRefactorReadinessReportStatus.FAILED.value
    write_json(report_path, report)
    write_text(markdown_path, markdown_report(report))
    return report
