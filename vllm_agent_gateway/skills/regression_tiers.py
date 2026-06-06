"""Skill regression tier catalog validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


DEFAULT_TIER_PATH = Path("runtime") / "skill_regression_tiers.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "skill-regression-tiers"
REQUIRED_TARGET_ROOTS = {
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
}


class RegressionTierId(str, Enum):
    OFFLINE = "offline"
    CONTROLLER = "controller"
    GATEWAY = "gateway"
    ANYTHINGLLM_API = "anythingllm-api"
    ANYTHINGLLM_UI = "anythingllm-ui"
    FIXTURE_MUTATION = "fixture-mutation"
    RELEASE_CANDIDATE = "release-candidate"


class RegressionTierReportStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


REQUIRED_TIER_ORDER = [tier.value for tier in RegressionTierId]
REQUIRED_REQUIREMENT_FIELDS = {
    "localhost_8000",
    "gateway_8300",
    "workflow_router_gateway_8500",
    "controller_8400",
    "role_8205",
    "anythingllm_api",
    "anythingllm_ui",
    "both_frozen_coinbase_fixtures",
    "disposable_mutation",
    "full_regression",
}


@dataclass(frozen=True)
class SkillRegressionTierConfig:
    config_root: Path
    tier_path: Path | None = None
    output_path: Path | None = None


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return value


def default_output_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"skill-regression-tiers-{utc_timestamp()}.json"


def list_strings(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def add_error(errors: list[dict[str, Any]], tier_id: str, field: str, message: str) -> None:
    errors.append({"tier_id": tier_id, "field": field, "message": message})


def command_target_exists(config_root: Path, token: str) -> bool:
    if token.startswith("-"):
        return True
    if token in {"python", "python3"}:
        return True
    if token == "-m":
        return True
    if token.startswith("scripts/") or token.startswith("tests/"):
        return (config_root / token).exists()
    return True


def command_contains(command: list[str], *tokens: str) -> bool:
    return all(token in command for token in tokens)


def validate_command_refs(config_root: Path, tier_id: str, command: Any, errors: list[dict[str, Any]]) -> list[str]:
    if not isinstance(command, list) or not command or not all(isinstance(item, str) and item for item in command):
        add_error(errors, tier_id, "commands", "each command must be a non-empty list of strings")
        return []
    for token in command:
        if not command_target_exists(config_root, token):
            add_error(errors, tier_id, "commands", f"command references missing path: {token}")
    return list(command)


def validate_requirements(tier_id: str, requirements: Any, errors: list[dict[str, Any]]) -> dict[str, bool]:
    if not isinstance(requirements, dict):
        add_error(errors, tier_id, "requirements", "requirements must be an object")
        return {}
    missing = sorted(REQUIRED_REQUIREMENT_FIELDS - set(requirements))
    extra = sorted(set(requirements) - REQUIRED_REQUIREMENT_FIELDS)
    for field in missing:
        add_error(errors, tier_id, "requirements", f"missing requirement: {field}")
    for field in extra:
        add_error(errors, tier_id, "requirements", f"unsupported requirement: {field}")
    normalized: dict[str, bool] = {}
    for field in REQUIRED_REQUIREMENT_FIELDS:
        value = requirements.get(field)
        if not isinstance(value, bool):
            add_error(errors, tier_id, "requirements", f"{field} must be boolean")
        else:
            normalized[field] = value
    return normalized


def validate_tier(
    *,
    config_root: Path,
    tier: dict[str, Any],
    expected_id: str,
    expected_order: int,
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    tier_id = str(tier.get("id") or "<missing>")
    if tier_id != expected_id:
        add_error(errors, tier_id, "id", f"expected tier id {expected_id}")
    if tier.get("order") != expected_order:
        add_error(errors, tier_id, "order", f"expected order {expected_order}")
    if not isinstance(tier.get("purpose"), str) or len(str(tier.get("purpose")).strip()) < 20:
        add_error(errors, tier_id, "purpose", "purpose must be descriptive")
    minimums = list_strings(tier.get("minimum_for_change_types"))
    if not minimums:
        add_error(errors, tier_id, "minimum_for_change_types", "tier must map at least one change type")
    requirements = validate_requirements(tier_id, tier.get("requirements"), errors)
    commands = [validate_command_refs(config_root, tier_id, item, errors) for item in tier.get("commands", [])]
    if not commands:
        add_error(errors, tier_id, "commands", "tier must define at least one command")
    target_roots = set(list_strings(tier.get("target_roots")))
    if requirements.get("both_frozen_coinbase_fixtures") and target_roots != REQUIRED_TARGET_ROOTS:
        add_error(errors, tier_id, "target_roots", "tier must include exactly both frozen Coinbase fixture roots")
    return {
        "id": tier_id,
        "order": tier.get("order"),
        "command_count": len(commands),
        "minimum_change_type_count": len(minimums),
        "requirements": requirements,
        "target_roots": sorted(target_roots),
    }


def validate_cross_tier_contracts(tiers: dict[str, dict[str, Any]], errors: list[dict[str, Any]]) -> None:
    gateway = tiers.get(RegressionTierId.GATEWAY.value, {})
    gateway_requirements = gateway.get("requirements") if isinstance(gateway.get("requirements"), dict) else {}
    for field in ("localhost_8000", "gateway_8300", "workflow_router_gateway_8500", "controller_8400", "role_8205"):
        if gateway_requirements.get(field) is not True:
            add_error(errors, RegressionTierId.GATEWAY.value, "requirements", f"gateway tier must require {field}")
    gateway_commands = gateway.get("commands") if isinstance(gateway.get("commands"), list) else []
    if not any(isinstance(command, list) and "scripts/validate_multi_repo_fixtures_live.py" in command for command in gateway_commands):
        add_error(errors, RegressionTierId.GATEWAY.value, "commands", "gateway tier must include multi-repo fixture live validation")
    api = tiers.get(RegressionTierId.ANYTHINGLLM_API.value, {})
    api_requirements = api.get("requirements") if isinstance(api.get("requirements"), dict) else {}
    if api_requirements.get("anythingllm_api") is not True:
        add_error(errors, RegressionTierId.ANYTHINGLLM_API.value, "requirements", "AnythingLLM API tier must require API access")
    ui = tiers.get(RegressionTierId.ANYTHINGLLM_UI.value, {})
    ui_requirements = ui.get("requirements") if isinstance(ui.get("requirements"), dict) else {}
    if ui_requirements.get("anythingllm_ui") is not True:
        add_error(errors, RegressionTierId.ANYTHINGLLM_UI.value, "requirements", "AnythingLLM UI tier must require UI access")
    mutation = tiers.get(RegressionTierId.FIXTURE_MUTATION.value, {})
    mutation_requirements = mutation.get("requirements") if isinstance(mutation.get("requirements"), dict) else {}
    if mutation_requirements.get("disposable_mutation") is not True:
        add_error(errors, RegressionTierId.FIXTURE_MUTATION.value, "requirements", "fixture mutation tier must require disposable mutation")
    release = tiers.get(RegressionTierId.RELEASE_CANDIDATE.value, {})
    release_requirements = release.get("requirements") if isinstance(release.get("requirements"), dict) else {}
    for field in (
        "localhost_8000",
        "gateway_8300",
        "workflow_router_gateway_8500",
        "controller_8400",
        "role_8205",
        "anythingllm_api",
        "both_frozen_coinbase_fixtures",
        "disposable_mutation",
        "full_regression",
    ):
        if release_requirements.get(field) is not True:
            add_error(errors, RegressionTierId.RELEASE_CANDIDATE.value, "requirements", f"release candidate must require {field}")
    release_commands = release.get("commands") if isinstance(release.get("commands"), list) else []
    if not any(
        isinstance(command, list)
        and "scripts/validate_skill_release_gate.py" in command
        and command_contains(command, "--profile", "release-candidate")
        for command in release_commands
    ):
        add_error(errors, RegressionTierId.RELEASE_CANDIDATE.value, "commands", "release candidate must run release-candidate profile")
    if not any(isinstance(command, list) and "scripts/validate_multi_repo_fixtures_live.py" in command for command in release_commands):
        add_error(errors, RegressionTierId.RELEASE_CANDIDATE.value, "commands", "release candidate must include multi-repo fixture live validation")
    if not any(isinstance(command, list) and "tests/regression/" in command and "-v" in command for command in release_commands):
        add_error(errors, RegressionTierId.RELEASE_CANDIDATE.value, "commands", "release candidate must include full regression")


def validate_change_type_minimums(
    *,
    manifest: dict[str, Any],
    tier_ids: set[str],
    tier_minimums: dict[str, list[str]],
    errors: list[dict[str, Any]],
) -> dict[str, str]:
    minimums = manifest.get("change_type_minimums")
    if not isinstance(minimums, dict):
        add_error(errors, "<manifest>", "change_type_minimums", "change_type_minimums must be an object")
        return {}
    normalized: dict[str, str] = {}
    for change_type, tier_id in minimums.items():
        if not isinstance(change_type, str) or not change_type:
            add_error(errors, "<manifest>", "change_type_minimums", "change type keys must be strings")
            continue
        if not isinstance(tier_id, str) or tier_id not in tier_ids:
            add_error(errors, "<manifest>", "change_type_minimums", f"unknown tier for change type {change_type}: {tier_id}")
            continue
        normalized[change_type] = tier_id
    for tier_id, change_types in tier_minimums.items():
        for change_type in change_types:
            if normalized.get(change_type) != tier_id:
                add_error(errors, tier_id, "minimum_for_change_types", f"change type missing from catalog minimums: {change_type}")
    return normalized


def validate_skill_regression_tiers(config: SkillRegressionTierConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    tier_path = config.tier_path or config_root / DEFAULT_TIER_PATH
    manifest = load_json(tier_path)
    errors: list[dict[str, Any]] = []
    if manifest.get("kind") != "skill_regression_tier_catalog":
        add_error(errors, "<manifest>", "kind", "kind must be skill_regression_tier_catalog")
    if manifest.get("schema_version") != 1:
        add_error(errors, "<manifest>", "schema_version", "schema_version must be 1")
    raw_tiers = manifest.get("tiers") if isinstance(manifest.get("tiers"), list) else []
    if len(raw_tiers) != len(REQUIRED_TIER_ORDER):
        add_error(errors, "<manifest>", "tiers", "tier catalog must include every required tier exactly once")
    tier_summaries: list[dict[str, Any]] = []
    tier_minimums: dict[str, list[str]] = {}
    for index, expected_id in enumerate(REQUIRED_TIER_ORDER, start=1):
        raw_tier = raw_tiers[index - 1] if index - 1 < len(raw_tiers) and isinstance(raw_tiers[index - 1], dict) else {}
        summary = validate_tier(
            config_root=config_root,
            tier=raw_tier,
            expected_id=expected_id,
            expected_order=index,
            errors=errors,
        )
        tier_summaries.append(summary)
        tier_minimums[expected_id] = list_strings(raw_tier.get("minimum_for_change_types"))
    tier_ids = {summary["id"] for summary in tier_summaries if summary["id"] in REQUIRED_TIER_ORDER}
    validate_change_type_minimums(
        manifest=manifest,
        tier_ids=tier_ids,
        tier_minimums=tier_minimums,
        errors=errors,
    )
    tiers_by_id = {
        item.get("id"): item
        for item in raw_tiers
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    validate_cross_tier_contracts(tiers_by_id, errors)
    report = {
        "schema_version": 1,
        "kind": "skill_regression_tier_report",
        "status": RegressionTierReportStatus.PASSED.value if not errors else RegressionTierReportStatus.FAILED.value,
        "created_at": utc_timestamp(),
        "tier_path": str(tier_path.resolve()),
        "summary": {
            "tier_count": len(raw_tiers),
            "required_tier_count": len(REQUIRED_TIER_ORDER),
            "change_type_count": len(manifest.get("change_type_minimums") or {}),
            "error_count": len(errors),
        },
        "tiers": tier_summaries,
        "errors": errors,
    }
    output_path = config.output_path or default_output_path(config_root)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    return report
