"""Phase 147 external tester dry-run validation."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.first_time_user_doctor import (
    DEFAULT_LLM_GATEWAY_BASE_URL,
    DEFAULT_MODEL_BASE_URL,
    FirstTimeUserDoctorConfig,
    run_first_time_user_doctor,
)
from vllm_agent_gateway.acceptance.onboarding import (
    DEFAULT_ONBOARDING_PACK_PATH,
    OnboardingValidationConfig,
    selected_cases,
    validate_external_tester_onboarding,
)
from vllm_agent_gateway.acceptance.release_channels import (
    DEFAULT_MANIFEST_PATH as DEFAULT_RELEASE_CHANNELS_MANIFEST_PATH,
    ReleaseChannelValidationConfig,
    validate_release_channels,
)
from vllm_agent_gateway.acceptance.release_notes import (
    DEFAULT_POLICY_PATH as DEFAULT_RELEASE_NOTES_POLICY_PATH,
    ReleaseNotesConfig,
    run_release_notes_validation,
)
from vllm_agent_gateway.acceptance.v1 import (
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_CONTROLLER_BASE_URL,
    DEFAULT_TARGET_ROOTS,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
)


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "external_tester_dry_run_policy"
EXPECTED_REPORT_KIND = "external_tester_dry_run_report"
EXPECTED_PHASE = 147
EXPECTED_BACKLOG_ID = "P0-BB-020"
DEFAULT_POLICY_PATH = Path("runtime") / "external_tester_dry_run_policy.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "external-tester-dry-run" / "phase147"


@dataclass(frozen=True)
class ExternalTesterDryRunConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path | None = None
    live_runtime: bool = False
    include_feedback: bool = True
    anythingllm_api_base_url: str = DEFAULT_ANYTHINGLLM_API_BASE_URL
    workflow_router_gateway_base_url: str = DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL
    controller_base_url: str = DEFAULT_CONTROLLER_BASE_URL
    model_base_url: str = DEFAULT_MODEL_BASE_URL
    llm_gateway_base_url: str = DEFAULT_LLM_GATEWAY_BASE_URL
    workspace: str = DEFAULT_WORKSPACE
    api_key_env: str = "ANYTHINGLLM_API_KEY"
    timeout_seconds: int = 900


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"external-tester-dry-run-{utc_timestamp()}.json"


def resolve_path(config_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_root / path


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object at {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact_hash(path: Path | None) -> str | None:
    return sha256_file(path) if path is not None and path.is_file() else None


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def string_dict(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items() if isinstance(item, str)}


def child_ref(path: Path | None, report: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(path) if path else None,
        "sha256": artifact_hash(path),
        "kind": report.get("kind"),
        "status": report.get("status"),
        "phase": report.get("phase"),
    }


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"policy.schema_version must be {SCHEMA_VERSION}")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(f"policy.phase must be {EXPECTED_PHASE}")
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    if policy.get("channel_under_test") != "stable":
        errors.append("policy.channel_under_test must be stable")
    if policy.get("onboarding_case_id") != "ONB-001":
        errors.append("policy.onboarding_case_id must be ONB-001")
    if not string_list(policy.get("required_docs_followed")):
        errors.append("policy.required_docs_followed must be a non-empty string list")
    if not isinstance(policy.get("required_doc_markers"), dict):
        errors.append("policy.required_doc_markers must be an object")
    if not string_list(policy.get("forbidden_doc_markers")):
        errors.append("policy.forbidden_doc_markers must be a non-empty string list")
    if not isinstance(policy.get("expected_environment"), dict):
        errors.append("policy.expected_environment must be an object")
    if set(string_list(policy.get("required_child_reports"))) != {
        "release_channels",
        "first_time_user_doctor",
        "release_notes",
        "external_onboarding_static",
        "external_onboarding_live",
    }:
        errors.append("policy.required_child_reports must name the Phase 147 child reports")
    return errors


def docs_audit(policy: dict[str, Any], *, config_root: Path) -> dict[str, Any]:
    blockers: list[str] = []
    ambiguities: list[str] = []
    docs: dict[str, dict[str, Any]] = {}
    markers = policy.get("required_doc_markers") if isinstance(policy.get("required_doc_markers"), dict) else {}
    forbidden_markers = string_list(policy.get("forbidden_doc_markers"))
    for raw_path in string_list(policy.get("required_docs_followed")):
        path = resolve_path(config_root, raw_path)
        if not path.is_file():
            blockers.append(f"required doc is missing: {raw_path}")
            docs[raw_path] = {"exists": False, "missing_markers": [], "sha256": None}
            continue
        text = path.read_text(encoding="utf-8")
        required_markers = string_list(markers.get(raw_path))
        missing = [marker for marker in required_markers if marker not in text]
        forbidden_hits = [marker for marker in forbidden_markers if marker in text]
        if missing:
            blockers.append(f"{raw_path} missing required markers: {missing}")
        if forbidden_hits:
            blockers.append(f"{raw_path} contains forbidden markers: {forbidden_hits}")
        docs[raw_path] = {
            "exists": True,
            "sha256": sha256_file(path),
            "required_marker_count": len(required_markers),
            "missing_markers": missing,
            "forbidden_hits": forbidden_hits,
        }
    external_text = (config_root / "README.external-tester-onboarding.md").read_text(encoding="utf-8")
    getting_started_text = (config_root / "README.getting-started.md").read_text(encoding="utf-8")
    if "Current stable external tester path" not in external_text or "release-candidate origin" not in external_text:
        ambiguities.append("stable-vs-release-candidate channel wording is not resolved")
    if "Minimum External Tester Dry Run" not in external_text or "Minimum External Tester Dry Run" not in getting_started_text:
        ambiguities.append("minimum external tester dry-run path is not explicit")
    if "Use `ONB-001` first" not in external_text:
        ambiguities.append("first manual external tester prompt is not pinned to ONB-001")
    if "Bash/WSL" not in external_text:
        ambiguities.append("canonical shell for the external tester dry run is not explicit")
    if "my-workspace" not in external_text:
        ambiguities.append("default AnythingLLM workspace is not explicit")
    if "Advanced broad refactor orchestration is not released" not in external_text:
        ambiguities.append("advanced refactor deferral is not explicit in onboarding docs")
    return {
        "status": "passed" if not blockers and not ambiguities else "failed",
        "docs_followed": string_list(policy.get("required_docs_followed")),
        "docs": docs,
        "blockers": blockers,
        "ambiguities": ambiguities,
        "resolved_findings": [
            "stable channel is named for current testing while release-candidate origin is explained",
            "minimum dry-run command is explicit",
            "ONB-001 is the first manual prompt",
            "Bash/WSL is the canonical dry-run shell",
            "my-workspace is documented as the default automated workspace",
            "advanced broad refactor remains deferred",
        ]
        if not blockers and not ambiguities
        else [],
    }


def child_status_errors(
    *,
    release_channels: dict[str, Any],
    doctor: dict[str, Any],
    release_notes: dict[str, Any],
    onboarding_static: dict[str, Any],
    onboarding_live: dict[str, Any],
    live_runtime: bool,
) -> list[str]:
    errors: list[str] = []
    if release_channels.get("kind") != "release_channel_validation_report":
        errors.append("release_channels.kind must be release_channel_validation_report")
    if release_channels.get("status") != "passed":
        errors.append("release_channels.status must be passed")
    stable_check = next(
        (
            item
            for item in release_channels.get("checks", [])
            if isinstance(item, dict) and item.get("id") == "stable.readiness"
        ),
        {},
    )
    if stable_check.get("status") != "passed":
        errors.append("release_channels stable.readiness must be passed")
    if release_notes.get("kind") != "release_notes_validation_report":
        errors.append("release_notes.kind must be release_notes_validation_report")
    if release_notes.get("status") != "passed":
        errors.append("release_notes.status must be passed")
    if onboarding_static.get("kind") != "external_tester_onboarding_validation_report":
        errors.append("external_onboarding_static.kind must be external_tester_onboarding_validation_report")
    if onboarding_static.get("status") != "passed":
        errors.append("external_onboarding_static.status must be passed")
    static_summary = onboarding_static.get("summary") if isinstance(onboarding_static.get("summary"), dict) else {}
    if static_summary.get("case_count") != 5:
        errors.append("external_onboarding_static.summary.case_count must be 5")
    if live_runtime:
        if doctor.get("kind") != "first_time_user_doctor_report":
            errors.append("first_time_user_doctor.kind must be first_time_user_doctor_report")
        if doctor.get("status") != "passed":
            errors.append("first_time_user_doctor.status must be passed")
        doctor_summary = doctor.get("summary") if isinstance(doctor.get("summary"), dict) else {}
        if doctor_summary.get("failed_check_ids") != []:
            errors.append("first_time_user_doctor.summary.failed_check_ids must be empty")
        if onboarding_live.get("kind") != "external_tester_onboarding_validation_report":
            errors.append("external_onboarding_live.kind must be external_tester_onboarding_validation_report")
        if onboarding_live.get("status") != "passed":
            errors.append("external_onboarding_live.status must be passed")
        live_summary = onboarding_live.get("summary") if isinstance(onboarding_live.get("summary"), dict) else {}
        if live_summary.get("live_status") != "passed":
            errors.append("external_onboarding_live.summary.live_status must be passed")
        if live_summary.get("live_case_count") != 1:
            errors.append("external_onboarding_live.summary.live_case_count must be 1")
        if live_summary.get("feedback_count") != 1:
            errors.append("external_onboarding_live.summary.feedback_count must be 1")
        live = onboarding_live.get("live") if isinstance(onboarding_live.get("live"), dict) else {}
        cases = [item for item in live.get("cases", []) if isinstance(item, dict)] if isinstance(live.get("cases"), list) else []
        if not cases:
            errors.append("external_onboarding_live.live.cases must contain ONB-001")
        else:
            case = cases[0]
            if case.get("case_id") != "ONB-001":
                errors.append("external_onboarding_live first case must be ONB-001")
            if case.get("status") != "passed":
                errors.append("external_onboarding_live ONB-001 status must be passed")
            if not str(case.get("run_id", "")).startswith("workflow-router-"):
                errors.append("external_onboarding_live ONB-001 must expose workflow-router run_id")
            if not str(case.get("feedback_run_id", "")).startswith("workflow-feedback-"):
                errors.append("external_onboarding_live ONB-001 must expose workflow-feedback run_id")
            visible = case.get("visible_response") if isinstance(case.get("visible_response"), dict) else {}
            feedback = case.get("feedback_response") if isinstance(case.get("feedback_response"), dict) else {}
            if visible.get("marker_status") != "passed":
                errors.append("external_onboarding_live ONB-001 visible_response.marker_status must be passed")
            if feedback.get("marker_status") != "passed":
                errors.append("external_onboarding_live ONB-001 feedback_response.marker_status must be passed")
    else:
        if onboarding_live.get("status") != "skipped":
            errors.append("external_onboarding_live.status must be skipped when live_runtime is false")
        if doctor.get("status") != "skipped":
            errors.append("first_time_user_doctor.status must be skipped when live_runtime is false")
    return errors


def build_external_tester_dry_run_report(
    *,
    policy: dict[str, Any],
    docs: dict[str, Any],
    release_channels: dict[str, Any],
    doctor: dict[str, Any],
    release_notes: dict[str, Any],
    onboarding_static: dict[str, Any],
    onboarding_live: dict[str, Any],
    environment: dict[str, Any],
    live_runtime: bool,
    policy_path: Path | None = None,
    release_channels_path: Path | None = None,
    doctor_path: Path | None = None,
    release_notes_path: Path | None = None,
    onboarding_static_path: Path | None = None,
    onboarding_live_path: Path | None = None,
) -> dict[str, Any]:
    errors = validate_policy(policy)
    errors.extend(docs.get("blockers", []))
    errors.extend(docs.get("ambiguities", []))
    errors.extend(
        child_status_errors(
            release_channels=release_channels,
            doctor=doctor,
            release_notes=release_notes,
            onboarding_static=onboarding_static,
            onboarding_live=onboarding_live,
            live_runtime=live_runtime,
        )
    )
    expected_env = policy.get("expected_environment") if isinstance(policy.get("expected_environment"), dict) else {}
    for key, expected in string_dict(expected_env).items():
        actual = environment.get(key)
        if key == "api_key_env":
            continue
        if actual != expected:
            errors.append(f"environment.{key} must be {expected}")
    if live_runtime and not environment.get("anythingllm_api_key_present"):
        errors.append("environment.anythingllm_api_key_present must be true for live dry run")
    live_summary = onboarding_live.get("summary") if isinstance(onboarding_live.get("summary"), dict) else {}
    doctor_summary = doctor.get("summary") if isinstance(doctor.get("summary"), dict) else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": "passed" if not errors else "failed",
        "created_at": utc_timestamp(),
        "tester_id": "external-contextless-phase147",
        "channel_under_test": policy.get("channel_under_test"),
        "docs_audit": docs,
        "environment": environment,
        "child_reports": {
            "policy": child_ref(policy_path, policy),
            "release_channels": child_ref(release_channels_path, release_channels),
            "first_time_user_doctor": child_ref(doctor_path, doctor),
            "release_notes": child_ref(release_notes_path, release_notes),
            "external_onboarding_static": child_ref(onboarding_static_path, onboarding_static),
            "external_onboarding_live": child_ref(onboarding_live_path, onboarding_live),
        },
        "manual_prompt": {
            "case_id": policy.get("onboarding_case_id"),
            "prompt": first_onboarding_prompt(onboarding_static),
            "run_id": first_live_case(onboarding_live).get("run_id"),
            "expected_markers_missing": first_live_case(onboarding_live)
            .get("visible_response", {})
            .get("missing_markers", []),
            "selected_workflow": "code_investigation.plan",
            "source_mutation": False,
        },
        "feedback_capture": {
            "attempted": live_runtime,
            "feedback_run_id": first_live_case(onboarding_live).get("feedback_run_id"),
            "linked_run_found": bool(first_live_case(onboarding_live).get("feedback_run_id")),
        },
        "summary": {
            "live_runtime": live_runtime,
            "doc_blocker_count": len(docs.get("blockers", [])),
            "doc_ambiguity_count": len(docs.get("ambiguities", [])),
            "doctor_failed_check_count": len(doctor_summary.get("failed_check_ids", []))
            if isinstance(doctor_summary.get("failed_check_ids"), list)
            else None,
            "onboarding_live_status": live_summary.get("live_status"),
            "onboarding_live_case_count": live_summary.get("live_case_count"),
            "feedback_count": live_summary.get("feedback_count"),
            "error_count": len(errors),
        },
        "errors": errors,
    }


def first_live_case(onboarding_live: dict[str, Any]) -> dict[str, Any]:
    live = onboarding_live.get("live") if isinstance(onboarding_live.get("live"), dict) else {}
    cases = [item for item in live.get("cases", []) if isinstance(item, dict)] if isinstance(live.get("cases"), list) else []
    return cases[0] if cases else {}


def first_onboarding_prompt(onboarding_static: dict[str, Any]) -> str:
    pack_path = onboarding_static.get("pack_path")
    if isinstance(pack_path, str) and Path(pack_path).is_file():
        try:
            pack = read_json_object(Path(pack_path))
            case = selected_cases(pack, ("ONB-001",))[0]
            prompt = case.get("prompt")
            return prompt if isinstance(prompt, str) else ""
        except Exception:  # noqa: BLE001
            return ""
    return ""


def skipped_report(kind: str) -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "kind": kind, "status": "skipped", "summary": {}}


def run_external_tester_dry_run(config: ExternalTesterDryRunConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = config.output_path or default_report_path(config_root)
    if not output_path.is_absolute():
        output_path = config_root / output_path
    child_dir = output_path.parent / "children"
    policy = read_json_object(policy_path) if policy_path.is_file() else {}
    environment = {
        "anythingllm_api_base_url": config.anythingllm_api_base_url,
        "workflow_router_gateway_base_url": config.workflow_router_gateway_base_url,
        "controller_base_url": config.controller_base_url,
        "model_base_url": config.model_base_url,
        "llm_gateway_base_url": config.llm_gateway_base_url,
        "workspace": config.workspace,
        "api_key_env": config.api_key_env,
        "anythingllm_api_key_present": bool(os.environ.get(config.api_key_env)),
    }
    docs = docs_audit(policy, config_root=config_root)
    release_channels_path = child_dir / "release-channels.json"
    release_channels = validate_release_channels(
        ReleaseChannelValidationConfig(
            config_root=config_root,
            manifest_path=DEFAULT_RELEASE_CHANNELS_MANIFEST_PATH,
            output_path=release_channels_path,
            channel=str(policy.get("channel_under_test") or "stable"),
        )
    )
    release_notes_path = child_dir / "release-notes.json"
    release_notes = run_release_notes_validation(
        ReleaseNotesConfig(
            config_root=config_root,
            policy_path=DEFAULT_RELEASE_NOTES_POLICY_PATH,
            output_path=release_notes_path,
            require_artifacts=True,
        )
    )
    onboarding_static_path = child_dir / "external-onboarding-static.json"
    onboarding_static = validate_external_tester_onboarding(
        OnboardingValidationConfig(
            config_root=config_root,
            pack_path=DEFAULT_ONBOARDING_PACK_PATH,
            output_path=onboarding_static_path,
        )
    )
    doctor_path: Path | None = child_dir / "first-time-user-doctor.json"
    onboarding_live_path: Path | None = child_dir / "external-onboarding-live.json"
    if config.live_runtime:
        doctor = run_first_time_user_doctor(
            FirstTimeUserDoctorConfig(
                config_root=config_root,
                model_base_url=config.model_base_url,
                llm_gateway_base_url=config.llm_gateway_base_url,
                workflow_router_gateway_base_url=config.workflow_router_gateway_base_url,
                controller_base_url=config.controller_base_url,
                anythingllm_api_base_url=config.anythingllm_api_base_url,
                workspace=config.workspace,
                expected_anythingllm_llm_base_url=config.workflow_router_gateway_base_url,
                api_key_env=config.api_key_env,
                target_roots=tuple(DEFAULT_TARGET_ROOTS),
                output_path=doctor_path,
                timeout_seconds=min(config.timeout_seconds, 60),
            )
        )
        onboarding_live = validate_external_tester_onboarding(
            OnboardingValidationConfig(
                config_root=config_root,
                pack_path=DEFAULT_ONBOARDING_PACK_PATH,
                output_path=onboarding_live_path,
                anythingllm_api_base_url=config.anythingllm_api_base_url,
                workspace=config.workspace,
                api_key_env=config.api_key_env,
                timeout_seconds=config.timeout_seconds,
                live_anythingllm=True,
                include_feedback=config.include_feedback,
                case_ids=(str(policy.get("onboarding_case_id") or "ONB-001"),),
            ),
            api_key=os.environ.get(config.api_key_env),
        )
    else:
        doctor = skipped_report("first_time_user_doctor_report")
        onboarding_live = skipped_report("external_tester_onboarding_validation_report")
        doctor_path = None
        onboarding_live_path = None
    report = build_external_tester_dry_run_report(
        policy=policy,
        docs=docs,
        release_channels=release_channels,
        doctor=doctor,
        release_notes=release_notes,
        onboarding_static=onboarding_static,
        onboarding_live=onboarding_live,
        environment=environment,
        live_runtime=config.live_runtime,
        policy_path=policy_path if policy_path.is_file() else None,
        release_channels_path=release_channels_path if release_channels_path.is_file() else None,
        doctor_path=doctor_path if doctor_path is not None and doctor_path.is_file() else None,
        release_notes_path=release_notes_path if release_notes_path.is_file() else None,
        onboarding_static_path=onboarding_static_path if onboarding_static_path.is_file() else None,
        onboarding_live_path=onboarding_live_path if onboarding_live_path is not None and onboarding_live_path.is_file() else None,
    )
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    return report
