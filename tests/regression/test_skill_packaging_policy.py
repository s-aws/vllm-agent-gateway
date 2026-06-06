from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from vllm_agent_gateway.skills.packaging_policy import (
    DEFAULT_POLICY_PATH,
    SkillPackPolicyConfig,
    read_json,
    run_skill_packaging_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def write_json(path: Path, value: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    return path


def project_policy() -> dict[str, object]:
    return read_json(REPO_ROOT / DEFAULT_POLICY_PATH)


def run_policy(tmp_path: Path, policy: dict[str, object]) -> dict[str, object]:
    policy_path = write_json(tmp_path / "runtime" / "skill_pack_policy.json", policy)
    return run_skill_packaging_policy(
        SkillPackPolicyConfig(
            config_root=tmp_path,
            policy_path=policy_path,
            output_path=tmp_path / "report.json",
        )
    )


def test_project_skill_packaging_policy_passes(tmp_path: Path) -> None:
    report = run_skill_packaging_policy(
        SkillPackPolicyConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "test-policy.json",
        )
    )

    assert report["status"] == "passed"
    assert report["policy_id"] == "project-local-skill-packaging"
    assert report["summary"]["allowed_namespace_count"] == 13


def test_skill_packaging_policy_rejects_namespace_drift(tmp_path: Path) -> None:
    policy = deepcopy(project_policy())
    namespace = policy["namespace_ownership"]
    assert isinstance(namespace, dict)
    namespace["allowed_route_namespaces"] = ["code"]

    report = run_policy(tmp_path, policy)

    assert report["status"] == "failed"
    assert any("allowed_route_namespaces" in error for error in report["errors"])


def test_skill_packaging_policy_rejects_manifest_contract_drift(tmp_path: Path) -> None:
    policy = deepcopy(project_policy())
    manifest = policy["manifest_contract"]
    assert isinstance(manifest, dict)
    fields = manifest["required_fields"]
    assert isinstance(fields, list)
    manifest["required_fields"] = [field for field in fields if field != "eval_cases"]

    report = run_policy(tmp_path, policy)

    assert report["status"] == "failed"
    assert any("required_fields" in error and "eval_cases" in error for error in report["errors"])


def test_skill_packaging_policy_rejects_uninstall_enablement_without_roadmap(tmp_path: Path) -> None:
    policy = deepcopy(project_policy())
    import_export = policy["import_export"]
    assert isinstance(import_export, dict)
    import_export["uninstall_supported"] = True

    report = run_policy(tmp_path, policy)

    assert report["status"] == "failed"
    assert any("uninstall_supported" in error for error in report["errors"])
