"""Security and policy validation gate for local tester releases."""

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
DEFAULT_POLICY_PATH = Path("runtime") / "security_policy.json"
DEFAULT_REPORT_DIR = Path("runtime-state") / "security-policy"
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


class SecurityCheckStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class SecurityPolicyValidationConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path | None = None
    include_secret_value_scan: bool = True


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_REPORT_DIR / f"security-policy-{utc_timestamp()}.json"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def resolve_path(config_root: Path, raw_path: Path | str) -> Path:
    path = raw_path if isinstance(raw_path, Path) else Path(raw_path)
    return path if path.is_absolute() else config_root / path


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object at {path}")
    return value


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def check(
    check_id: str,
    status: SecurityCheckStatus,
    message: str,
    *,
    category: str,
    details: dict[str, Any] | None = None,
    next_action: str = "",
) -> dict[str, Any]:
    return {
        "id": check_id,
        "category": category,
        "status": status.value,
        "message": message,
        "details": details or {},
        "next_action": next_action,
    }


def path_exists(config_root: Path, raw_path: object) -> bool:
    return isinstance(raw_path, str) and bool(raw_path.strip()) and resolve_path(config_root, raw_path).exists()


def normalize_root_value(raw_root: str) -> str:
    normalized = raw_root.strip().replace("\\", "/")
    while normalized.endswith("/") and normalized not in {"/", "C:/"}:
        normalized = normalized[:-1]
    if normalized == "C:/":
        return "C:"
    return normalized


def validate_policy_shape(policy: dict[str, Any], *, config_root: Path, policy_path: Path) -> dict[str, Any]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if policy.get("kind") != "security_policy":
        errors.append("kind must be security_policy")
    version = policy.get("version")
    if not isinstance(version, str) or not SEMVER_RE.fullmatch(version):
        errors.append("version must be semantic version x.y.z")
    if policy.get("release_channel") != "release-candidate":
        errors.append("release_channel must be release-candidate")
    for field_name in ("docs", "examples", "required_scripts"):
        values = string_list(policy.get(field_name))
        if not values:
            errors.append(f"{field_name} must be a non-empty string array")
            continue
        missing = [value for value in values if not path_exists(config_root, value)]
        if missing:
            errors.append(f"{field_name} missing files: {missing}")
    return check(
        "policy.shape",
        SecurityCheckStatus.PASSED if not errors else SecurityCheckStatus.FAILED,
        "Security policy manifest shape is valid." if not errors else "Security policy manifest shape is invalid.",
        category="policy",
        details={"policy_path": str(policy_path), "version": version, "errors": errors},
        next_action="" if not errors else "Fix runtime/security_policy.json before running release security review.",
    )


def validate_fixture_boundaries(policy: dict[str, Any], *, config_root: Path) -> dict[str, Any]:
    errors: list[str] = []
    boundaries = policy.get("filesystem_boundaries") if isinstance(policy.get("filesystem_boundaries"), dict) else {}
    allowed_roots = string_list(boundaries.get("allowed_target_roots"))
    forbidden_roots = {normalize_root_value(root) for root in string_list(boundaries.get("forbidden_root_values"))}
    for root in allowed_roots:
        normalized = normalize_root_value(root)
        if normalized in forbidden_roots:
            errors.append(f"allowed_target_roots contains forbidden broad root: {root}")
    manifest_path = resolve_path(config_root, str(boundaries.get("fixture_manifest") or "runtime/fixtures.json"))
    try:
        manifest = read_json_object(manifest_path)
        fixtures = manifest.get("fixtures")
        if not isinstance(fixtures, list) or not fixtures:
            errors.append("fixture manifest must contain fixtures")
        else:
            for item in fixtures:
                if not isinstance(item, dict):
                    errors.append("fixture entry must be an object")
                    continue
                fixture_id = str(item.get("id") or "unknown")
                if item.get("protected") is not True:
                    errors.append(f"fixture {fixture_id} must be protected")
                if item.get("disposable_only") is not True:
                    errors.append(f"fixture {fixture_id} must be disposable_only")
                source_path = item.get("source_path")
                if isinstance(source_path, str) and normalize_root_value(source_path) in forbidden_roots:
                    errors.append(f"fixture {fixture_id} source_path is too broad: {source_path}")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"fixture manifest could not be read: {type(exc).__name__}: {exc}")
    return check(
        "filesystem.fixture_boundaries",
        SecurityCheckStatus.PASSED if not errors else SecurityCheckStatus.FAILED,
        "Fixture and filesystem boundaries are valid." if not errors else "Fixture or filesystem boundaries are invalid.",
        category="filesystem",
        details={"manifest_path": str(manifest_path), "errors": errors},
        next_action="" if not errors else "Fix fixture protection/disposable metadata before external release.",
    )


def iter_globbed_files(config_root: Path, patterns: list[str], *, max_file_bytes: int) -> list[Path]:
    files: set[Path] = set()
    for pattern in patterns:
        for path in config_root.glob(pattern):
            if not path.is_file():
                continue
            try:
                if path.stat().st_size > max_file_bytes:
                    continue
            except OSError:
                continue
            files.add(path)
    return sorted(files)


def scan_file_for_values(path: Path, values: dict[str, str]) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return [name for name, value in values.items() if value and value in text]


def secret_value_scan(policy: dict[str, Any], *, config_root: Path, include_secret_value_scan: bool) -> dict[str, Any]:
    secret_policy = policy.get("secret_handling") if isinstance(policy.get("secret_handling"), dict) else {}
    secret_env_vars = string_list(secret_policy.get("secret_env_vars"))
    available_values = {
        name: os.environ.get(name, "")
        for name in secret_env_vars
        if len(os.environ.get(name, "")) >= 8
    }
    if not include_secret_value_scan or not available_values:
        return check(
            "secret.value_scan",
            SecurityCheckStatus.SKIPPED,
            "Secret value scan skipped because no secret values were available or scanning was disabled.",
            category="secrets",
            details={"secret_env_vars": secret_env_vars, "available_secret_count": len(available_values)},
        )
    patterns = string_list(secret_policy.get("scan_globs"))
    max_file_bytes = int(secret_policy.get("max_file_bytes") or 4_194_304)
    matches: list[dict[str, str]] = []
    scanned_files = iter_globbed_files(config_root, patterns, max_file_bytes=max_file_bytes)
    for path in scanned_files:
        found = scan_file_for_values(path, available_values)
        if found:
            matches.append(
                {
                    "path": path.resolve().relative_to(config_root.resolve()).as_posix(),
                    "secret_names": ",".join(sorted(found)),
                }
            )
    return check(
        "secret.value_scan",
        SecurityCheckStatus.PASSED if not matches else SecurityCheckStatus.FAILED,
        "No configured secret values were found in scanned files."
        if not matches
        else "Configured secret values were found in scanned files.",
        category="secrets",
        details={
            "secret_env_vars": secret_env_vars,
            "available_secret_count": len(available_values),
            "scanned_file_count": len(scanned_files),
            "matches": matches,
        },
        next_action="" if not matches else "Remove secret values from artifacts or source-controlled files and rotate the exposed secret.",
    )


def command_policy_scan(policy: dict[str, Any], *, config_root: Path) -> dict[str, Any]:
    command_policy = policy.get("command_policy") if isinstance(policy.get("command_policy"), dict) else {}
    fragments = string_list(command_policy.get("forbidden_fragments"))
    patterns = string_list(command_policy.get("scan_globs"))
    matches: list[dict[str, str]] = []
    for path in iter_globbed_files(config_root, patterns, max_file_bytes=2_097_152):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        found = [fragment for fragment in fragments if fragment in text]
        if found:
            matches.append(
                {
                    "path": path.resolve().relative_to(config_root.resolve()).as_posix(),
                    "fragments": ", ".join(found),
                }
            )
    return check(
        "command_policy.forbidden_fragments",
        SecurityCheckStatus.PASSED if not matches else SecurityCheckStatus.FAILED,
        "No forbidden command fragments were found in executable project files."
        if not matches
        else "Forbidden command fragments were found in executable project files.",
        category="commands",
        details={"matches": matches, "fragment_count": len(fragments)},
        next_action="" if not matches else "Remove destructive command fragments or move them behind an explicit approved safety gate.",
    )


def prompt_policy_check(policy: dict[str, Any], *, config_root: Path) -> dict[str, Any]:
    prompt_policy = policy.get("prompt_policy") if isinstance(policy.get("prompt_policy"), dict) else {}
    pack_path = resolve_path(config_root, str(prompt_policy.get("onboarding_pack") or "runtime/external_tester_onboarding.json"))
    suspicious_terms = [term.lower() for term in string_list(prompt_policy.get("suspicious_output_terms"))]
    deferred_terms = [term.lower() for term in string_list(prompt_policy.get("deferred_first_test_terms"))]
    errors: list[str] = []
    try:
        pack = read_json_object(pack_path)
        cases = pack.get("cases")
        if not isinstance(cases, list) or not cases:
            errors.append("onboarding pack must contain cases")
        else:
            for case in cases:
                if not isinstance(case, dict):
                    errors.append("onboarding case must be an object")
                    continue
                case_id = str(case.get("case_id") or "unknown")
                prompt = str(case.get("prompt") or "").lower()
                found_suspicious = [term for term in suspicious_terms if term in prompt]
                found_deferred = [term for term in deferred_terms if term in prompt]
                if found_suspicious:
                    errors.append(f"{case_id} asks for suspicious output: {found_suspicious}")
                if found_deferred:
                    errors.append(f"{case_id} contains deferred first-test terms: {found_deferred}")
                if case.get("mutation_policy") != "read_only":
                    errors.append(f"{case_id} mutation_policy must be read_only")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"onboarding pack could not be read: {type(exc).__name__}: {exc}")
    return check(
        "prompt_policy.onboarding",
        SecurityCheckStatus.PASSED if not errors else SecurityCheckStatus.FAILED,
        "Onboarding prompts satisfy security policy." if not errors else "Onboarding prompts violate security policy.",
        category="prompts",
        details={"pack_path": str(pack_path), "errors": errors},
        next_action="" if not errors else "Remove suspicious or deferred prompt terms from external tester onboarding.",
    )


def validate_security_policy(config: SecurityPolicyValidationConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = config.output_path or default_report_path(config_root)
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "security_policy_validation_report",
        "status": SecurityCheckStatus.FAILED.value,
        "created_at": utc_timestamp(),
        "config_root": str(config_root),
        "policy_path": str(policy_path),
        "checks": [],
        "summary": {},
    }
    try:
        policy = read_json_object(policy_path)
        checks = [
            validate_policy_shape(policy, config_root=config_root, policy_path=policy_path),
            validate_fixture_boundaries(policy, config_root=config_root),
            secret_value_scan(policy, config_root=config_root, include_secret_value_scan=config.include_secret_value_scan),
            command_policy_scan(policy, config_root=config_root),
            prompt_policy_check(policy, config_root=config_root),
        ]
    except Exception as exc:  # noqa: BLE001
        checks = [
            check(
                "policy.load",
                SecurityCheckStatus.FAILED,
                f"Security policy could not be loaded: {type(exc).__name__}: {exc}",
                category="policy",
                next_action="Create runtime/security_policy.json before running the security gate.",
            )
        ]
    failed_ids = [item["id"] for item in checks if item.get("status") == SecurityCheckStatus.FAILED.value]
    report["checks"] = checks
    report["summary"] = {
        "check_count": len(checks),
        "failed_check_ids": failed_ids,
        "status_counts": {
            status.value: sum(1 for item in checks if item.get("status") == status.value)
            for status in SecurityCheckStatus
        },
    }
    report["status"] = SecurityCheckStatus.PASSED.value if not failed_ids else SecurityCheckStatus.FAILED.value
    write_json(output_path, report)
    report["report_path"] = str(output_path.resolve())
    write_json(output_path, report)
    return report
