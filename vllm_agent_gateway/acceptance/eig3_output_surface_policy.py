"""EIG-3 output-surface policy matrix validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.eig3_sensitive_data import (
    DEFAULT_FIXTURE_PATH,
    EIG3FixtureCaseType,
    EIG3HandlingDecision,
    EIG3OutputSurface,
    EIG3SensitiveDataConfig,
    EIG3SensitiveDataArchetype,
    EIG3ValidationStatus,
    detect_unsafe_request,
    read_json_object,
    run_eig3_sensitive_data_validation,
    sha256_text,
    string_list,
    validation_error,
    write_json,
)


SCHEMA_VERSION = 1
DEFAULT_POLICY_PATH = Path("runtime") / "eig3_output_surface_policy.json"
DEFAULT_REPORT_DIR = Path("runtime-state") / "eig3-output-surface-policy"
RUN_STATE_SURFACE = "run_state_summary"
REQUIRED_SURFACES = {
    EIG3OutputSurface.CHAT.value,
    EIG3OutputSurface.JSON.value,
    EIG3OutputSurface.ARTIFACT.value,
    EIG3OutputSurface.AUDIT_SUMMARY.value,
    EIG3OutputSurface.MEMORY.value,
    RUN_STATE_SURFACE,
}
REQUIRED_DECISIONS = {item.value for item in EIG3HandlingDecision}
SENSITIVE_ARCHETYPES = {item.value for item in EIG3SensitiveDataArchetype}
NON_SECRET_POLICY_TOKENS = {
    "confidential",
    "contract",
    "financial",
    "procurement",
    "legal",
    "review",
    "internal",
    "incident",
    "reconstruct",
    "sensitive",
    "synthetic",
    "business",
    "personal",
    "secret",
    "values",
    "omitted",
    "masked",
    "refused",
}


@dataclass(frozen=True)
class EIG3OutputSurfacePolicyConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    fixture_path: Path | None = None
    output_path: Path | None = None


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def resolve_path(config_root: Path, raw_path: Path | str) -> Path:
    path = raw_path if isinstance(raw_path, Path) else Path(raw_path)
    return path if path.is_absolute() else config_root / path


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"eig3-output-surface-policy-{utc_timestamp()}.json"


def ordered_decisions(surface_decisions: dict[str, str], run_state_decision: str) -> dict[str, str]:
    return {
        "chat_default": surface_decisions.get(EIG3OutputSurface.CHAT.value, ""),
        "json_output": surface_decisions.get(EIG3OutputSurface.JSON.value, ""),
        "generated_artifact": surface_decisions.get(EIG3OutputSurface.ARTIFACT.value, ""),
        "connector_audit_summary": surface_decisions.get(EIG3OutputSurface.AUDIT_SUMMARY.value, ""),
        "run_state_summary": run_state_decision,
        "memory": surface_decisions.get(EIG3OutputSurface.MEMORY.value, ""),
    }


def safe_render_sample(fixture: dict[str, Any], surface: str, decision: str) -> str:
    classes = ", ".join(string_list(fixture.get("expected_sensitive_classes"))) or "none"
    if decision == EIG3HandlingDecision.ALLOW.value:
        return f"{surface}: allowed synthetic non-sensitive fixture {fixture['id']}."
    if decision == EIG3HandlingDecision.MASK.value:
        return f"{surface}: sensitive value masked for fixture {fixture['id']} [{classes}]."
    if decision == EIG3HandlingDecision.REFUSE.value:
        return (
            f"{surface}: request refused for fixture {fixture['id']} because it asks to reveal, transform, "
            "store, or reconstruct sensitive data. I can provide a safe summary or remediation guidance."
        )
    if decision == EIG3HandlingDecision.SUMMARIZE.value:
        return f"{surface}: safe summary for fixture {fixture['id']}; sensitive values omitted [{classes}]."
    return f"{surface}: sensitive content omitted for fixture {fixture['id']}."


def sample_leaks_raw_fixture_text(sample: str, fixture_text: str) -> bool:
    if not fixture_text:
        return False
    sample_lower = sample.lower()
    raw_tokens = [
        token.strip(".,;:!()[]{}\"'")
        for token in fixture_text.split()
        if len(token.strip(".,;:!()[]{}\"'")) >= 10
    ]
    sensitive_tokens = [
        token
        for token in raw_tokens
        if token.lower() not in NON_SECRET_POLICY_TOKENS
        and (
            "@" in token
            or any(char.isdigit() for char in token)
            or "synth" in token.lower()
            or token.startswith("-----BEGIN")
            or "://" in token
        )
    ]
    return any(token.lower() in sample_lower for token in sensitive_tokens)


def validate_policy_shape(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", f"schema_version must be {SCHEMA_VERSION}"))
    if policy.get("kind") != "eig3_output_surface_policy":
        errors.append(validation_error("policy.kind", "kind must be eig3_output_surface_policy"))
    if policy.get("phase") != 299:
        errors.append(validation_error("policy.phase", "phase must be 299"))
    if not isinstance(policy.get("fixture_pack"), str) or not policy["fixture_pack"].strip():
        errors.append(validation_error("policy.fixture_pack", "fixture_pack must be a non-empty string"))
    if not isinstance(policy.get("source_matrix"), str) or not policy["source_matrix"].strip():
        errors.append(validation_error("policy.source_matrix", "source_matrix must be a non-empty string"))
    required_decisions = set(string_list(policy.get("required_decisions")))
    if required_decisions != REQUIRED_DECISIONS:
        errors.append(validation_error("policy.required_decisions", f"required_decisions must be {sorted(REQUIRED_DECISIONS)}"))
    surface_rules = policy.get("surface_rules")
    if not isinstance(surface_rules, dict):
        errors.append(validation_error("policy.surface_rules", "surface_rules must be an object"))
    else:
        missing_surfaces = sorted(REQUIRED_SURFACES - set(surface_rules))
        if missing_surfaces:
            errors.append(validation_error("policy.surface_rules", f"missing surface rules: {', '.join(missing_surfaces)}"))
        for surface, rules in surface_rules.items():
            if surface not in REQUIRED_SURFACES:
                errors.append(validation_error("policy.surface_rules", f"unsupported surface: {surface}"))
                continue
            if not isinstance(rules, dict):
                errors.append(validation_error("policy.surface_rules", f"{surface} rules must be an object"))
                continue
            for key in ("safe_allowed", "sensitive_allowed"):
                values = set(string_list(rules.get(key)))
                if not values or not values <= REQUIRED_DECISIONS:
                    errors.append(validation_error("policy.surface_rules", f"{surface}.{key} contains unsupported decisions"))
    negative = policy.get("negative_control")
    if not isinstance(negative, dict):
        errors.append(validation_error("policy.negative_control", "negative_control must be an object"))
    else:
        for surface in REQUIRED_SURFACES:
            if surface not in negative:
                errors.append(validation_error("policy.negative_control", f"missing negative control surface: {surface}"))
        if negative.get(EIG3OutputSurface.CHAT.value) != EIG3HandlingDecision.REFUSE.value:
            errors.append(validation_error("policy.negative_control", "negative-control chat decision must be refuse"))
        if negative.get(EIG3OutputSurface.JSON.value) != EIG3HandlingDecision.REFUSE.value:
            errors.append(validation_error("policy.negative_control", "negative-control json decision must be refuse"))
    derived = policy.get("derived_surfaces")
    if not isinstance(derived, dict) or not isinstance(derived.get(RUN_STATE_SURFACE), dict):
        errors.append(validation_error("policy.derived_surfaces", "run_state_summary derived surface policy is required"))
    return errors


def surface_decisions_for_fixture(fixture: dict[str, Any], policy: dict[str, Any]) -> dict[str, str]:
    surfaces = fixture.get("surface_decisions") if isinstance(fixture.get("surface_decisions"), dict) else {}
    derived = policy.get("derived_surfaces", {}).get(RUN_STATE_SURFACE, {})
    if fixture.get("case_type") == EIG3FixtureCaseType.DEFERRED.value:
        run_state_decision = str(derived.get("deferred_decision") or EIG3HandlingDecision.OMIT.value)
    elif string_list(fixture.get("expected_sensitive_classes")):
        run_state_decision = str(derived.get("sensitive_decision") or EIG3HandlingDecision.OMIT.value)
    else:
        run_state_decision = str(derived.get("safe_decision") or EIG3HandlingDecision.ALLOW.value)
    return {
        EIG3OutputSurface.CHAT.value: str(surfaces.get(EIG3OutputSurface.CHAT.value) or ""),
        EIG3OutputSurface.JSON.value: str(surfaces.get(EIG3OutputSurface.JSON.value) or ""),
        EIG3OutputSurface.ARTIFACT.value: str(surfaces.get(EIG3OutputSurface.ARTIFACT.value) or ""),
        EIG3OutputSurface.AUDIT_SUMMARY.value: str(surfaces.get(EIG3OutputSurface.AUDIT_SUMMARY.value) or ""),
        EIG3OutputSurface.MEMORY.value: str(surfaces.get(EIG3OutputSurface.MEMORY.value) or ""),
        RUN_STATE_SURFACE: run_state_decision,
    }


def allowed_decisions_for_fixture(fixture: dict[str, Any], policy: dict[str, Any], surface: str) -> set[str]:
    if fixture.get("case_type") == EIG3FixtureCaseType.DEFERRED.value:
        return {EIG3HandlingDecision.OMIT.value}
    if fixture.get("case_type") == EIG3FixtureCaseType.NEGATIVE_CONTROL.value:
        negative = policy.get("negative_control", {})
        return {str(negative.get(surface) or "")}
    rules = policy.get("surface_rules", {}).get(surface, {})
    if string_list(fixture.get("expected_sensitive_classes")):
        return set(string_list(rules.get("sensitive_allowed")))
    return set(string_list(rules.get("safe_allowed")))


def validate_fixture_output_policy(fixture: dict[str, Any], policy: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    fixture_id = str(fixture.get("id"))
    decisions = surface_decisions_for_fixture(fixture, policy)
    sample_hashes: dict[str, str] = {}
    for surface, decision in decisions.items():
        allowed = allowed_decisions_for_fixture(fixture, policy, surface)
        if decision not in allowed:
            errors.append(
                validation_error(
                    "fixture.surface_decision_not_allowed",
                    f"{surface} decision {decision!r} is not in allowed decisions {sorted(allowed)}",
                    fixture_id=fixture_id,
                )
            )
        sample = safe_render_sample(fixture, surface, decision)
        sample_hashes[surface] = sha256_text(sample)
        if sample_leaks_raw_fixture_text(sample, str(fixture.get("text") or "")):
            errors.append(validation_error("fixture.safe_sample_leak", f"{surface} sample leaked raw fixture token", fixture_id=fixture_id))
    if decisions[EIG3OutputSurface.CHAT.value] != decisions[EIG3OutputSurface.JSON.value]:
        errors.append(validation_error("fixture.json_default_parity", "chat and json decisions must match", fixture_id=fixture_id))
    if fixture.get("case_type") == EIG3FixtureCaseType.NEGATIVE_CONTROL.value:
        if not detect_unsafe_request(str(fixture.get("text") or "")):
            errors.append(validation_error("fixture.negative_control_prompt", "negative control must contain an unsupported disclosure term", fixture_id=fixture_id))
        if decisions[EIG3OutputSurface.CHAT.value] != EIG3HandlingDecision.REFUSE.value:
            errors.append(validation_error("fixture.negative_control_chat", "negative control chat output must refuse", fixture_id=fixture_id))
        if decisions[EIG3OutputSurface.JSON.value] != EIG3HandlingDecision.REFUSE.value:
            errors.append(validation_error("fixture.negative_control_json", "negative control json output must refuse", fixture_id=fixture_id))
    if EIG3SensitiveDataArchetype.SECRET_LIKE.value in string_list(fixture.get("expected_sensitive_classes")):
        for surface, decision in decisions.items():
            if decision == EIG3HandlingDecision.ALLOW.value:
                errors.append(validation_error("fixture.secret_allow", f"secret-like fixture allows {surface}", fixture_id=fixture_id))
    result = {
        "id": fixture_id,
        "case_type": fixture.get("case_type"),
        "archetype": fixture.get("archetype"),
        "decisions": ordered_decisions(decisions, decisions[RUN_STATE_SURFACE]),
        "safe_sample_hashes": sample_hashes,
        "status": EIG3ValidationStatus.PASSED.value if not errors else EIG3ValidationStatus.FAILED.value,
        "error_ids": [item["id"] for item in errors],
    }
    return result, errors


def validate_decision_coverage(results: list[dict[str, Any]]) -> list[dict[str, str]]:
    observed: set[str] = set()
    for result in results:
        decisions = result.get("decisions")
        if isinstance(decisions, dict):
            observed.update(str(item) for item in decisions.values())
    missing = sorted(REQUIRED_DECISIONS - observed)
    if missing:
        return [validation_error("coverage.required_decisions", f"missing decision coverage: {', '.join(missing)}")]
    return []


def validate_unsupported_disclosure_coverage(fixtures: list[dict[str, Any]], policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    terms = set(string_list(policy.get("unsupported_disclosure_terms")))
    if not terms:
        errors.append(validation_error("coverage.unsupported_disclosure_terms", "unsupported disclosure terms must not be empty"))
        return errors
    for archetype in sorted(SENSITIVE_ARCHETYPES):
        controls = [
            item
            for item in fixtures
            if item.get("archetype") == archetype and item.get("case_type") == EIG3FixtureCaseType.NEGATIVE_CONTROL.value
        ]
        if not controls:
            errors.append(validation_error("coverage.negative_controls", f"{archetype} has no negative controls"))
            continue
        if not any(any(term in str(item.get("text") or "").lower() for term in terms) for item in controls):
            errors.append(validation_error("coverage.unsupported_disclosure_terms", f"{archetype} negative controls lack unsupported disclosure terms"))
    return errors


def run_eig3_output_surface_policy_validation(config: EIG3OutputSurfacePolicyConfig) -> dict[str, Any]:
    policy_path = resolve_path(config.config_root, config.policy_path)
    output_path = config.output_path or default_report_path(config.config_root)
    errors: list[dict[str, str]] = []
    fixture_results: list[dict[str, Any]] = []
    try:
        policy = read_json_object(policy_path)
    except Exception as exc:  # noqa: BLE001
        policy = {}
        errors.append(validation_error("policy.read", f"could not read policy: {type(exc).__name__}: {exc}"))
    errors.extend(validate_policy_shape(policy))
    fixture_path = config.fixture_path or Path(str(policy.get("fixture_pack") or DEFAULT_FIXTURE_PATH))
    resolved_fixture_path = resolve_path(config.config_root, fixture_path)
    fixture_report_path = output_path.parent / f"{output_path.stem}-phase298-fixture-validation.json"
    fixture_report = run_eig3_sensitive_data_validation(
        EIG3SensitiveDataConfig(
            config_root=config.config_root,
            fixture_path=resolved_fixture_path,
            output_path=fixture_report_path,
        )
    )
    if fixture_report.get("status") != EIG3ValidationStatus.PASSED.value:
        errors.append(validation_error("phase298_fixture_validation", "Phase 298 fixture validation must pass before output policy validation"))
    try:
        fixture_pack = read_json_object(resolved_fixture_path)
    except Exception as exc:  # noqa: BLE001
        fixture_pack = {}
        errors.append(validation_error("fixture_pack.read", f"could not read fixture pack: {type(exc).__name__}: {exc}"))
    fixtures = fixture_pack.get("fixtures") if isinstance(fixture_pack.get("fixtures"), list) else []
    shaped_fixtures = [item for item in fixtures if isinstance(item, dict)]
    for fixture in shaped_fixtures:
        result, fixture_errors = validate_fixture_output_policy(fixture, policy)
        fixture_results.append(result)
        errors.extend(fixture_errors)
    errors.extend(validate_decision_coverage(fixture_results))
    errors.extend(validate_unsupported_disclosure_coverage(shaped_fixtures, policy))
    status = EIG3ValidationStatus.PASSED.value if not errors else EIG3ValidationStatus.FAILED.value
    summary = {
        "status": status,
        "fixture_count": len(shaped_fixtures),
        "surface_count": len(REQUIRED_SURFACES),
        "failed_fixture_count": sum(1 for item in fixture_results if item["status"] == EIG3ValidationStatus.FAILED.value),
        "validation_error_count": len(errors),
        "phase300_ready": status == EIG3ValidationStatus.PASSED.value,
        "json_default_parity_required": True,
        "raw_fixture_text_retained_in_report": False,
        "phase298_report_path": fixture_report.get("report_path"),
    }
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "eig3_output_surface_policy_validation_report",
        "phase": 299,
        "status": status,
        "policy_path": str(policy_path),
        "fixture_pack_path": str(resolved_fixture_path),
        "summary": summary,
        "fixture_results": fixture_results,
        "validation_errors": errors,
        "report_path": str(output_path),
    }
    write_json(output_path, report)
    return report
