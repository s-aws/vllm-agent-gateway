from __future__ import annotations

import json
import shutil
from pathlib import Path

from vllm_agent_gateway.skills.regression_tiers import (
    REQUIRED_TARGET_ROOTS,
    REQUIRED_TIER_ORDER,
    SkillRegressionTierConfig,
    validate_skill_regression_tiers,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def copy_tier_root(tmp_path: Path) -> Path:
    root = tmp_path / "tier-root"
    shutil.copytree(REPO_ROOT / "runtime", root / "runtime")
    shutil.copytree(REPO_ROOT / "scripts", root / "scripts")
    shutil.copytree(REPO_ROOT / "tests" / "regression", root / "tests" / "regression")
    return root


def test_project_skill_regression_tier_catalog_passes(tmp_path: Path) -> None:
    report = validate_skill_regression_tiers(
        SkillRegressionTierConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "skill-regression-tiers.json",
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["tier_count"] == len(REQUIRED_TIER_ORDER)
    assert report["summary"]["error_count"] == 0
    assert [tier["id"] for tier in report["tiers"]] == REQUIRED_TIER_ORDER
    release = next(tier for tier in report["tiers"] if tier["id"] == "release-candidate")
    assert set(release["target_roots"]) == REQUIRED_TARGET_ROOTS
    assert release["requirements"]["full_regression"] is True
    assert release["requirements"]["anythingllm_api"] is True


def test_skill_regression_tiers_reject_missing_release_candidate_profile(tmp_path: Path) -> None:
    root = copy_tier_root(tmp_path)
    tier_path = root / "runtime" / "skill_regression_tiers.json"
    manifest = json.loads(tier_path.read_text(encoding="utf-8"))
    release = next(item for item in manifest["tiers"] if item["id"] == "release-candidate")
    release["commands"][0] = ["python3", "scripts/validate_skill_release_gate.py", "--profile", "live-full"]
    write_json(tier_path, manifest)

    report = validate_skill_regression_tiers(
        SkillRegressionTierConfig(
            config_root=root,
            output_path=tmp_path / "tier-report.json",
        )
    )

    assert report["status"] == "failed"
    assert any(
        error["tier_id"] == "release-candidate" and "release-candidate profile" in error["message"]
        for error in report["errors"]
    )


def test_skill_regression_tiers_reject_missing_frozen_fixture_target(tmp_path: Path) -> None:
    root = copy_tier_root(tmp_path)
    tier_path = root / "runtime" / "skill_regression_tiers.json"
    manifest = json.loads(tier_path.read_text(encoding="utf-8"))
    gateway = next(item for item in manifest["tiers"] if item["id"] == "gateway")
    gateway["target_roots"] = ["/mnt/c/coinbase_testing_repo_frozen_tmp"]
    write_json(tier_path, manifest)

    report = validate_skill_regression_tiers(
        SkillRegressionTierConfig(
            config_root=root,
            output_path=tmp_path / "tier-report.json",
        )
    )

    assert report["status"] == "failed"
    assert any(error["tier_id"] == "gateway" and "both frozen Coinbase" in error["message"] for error in report["errors"])


def test_skill_regression_tiers_require_multi_repo_live_command(tmp_path: Path) -> None:
    root = copy_tier_root(tmp_path)
    tier_path = root / "runtime" / "skill_regression_tiers.json"
    manifest = json.loads(tier_path.read_text(encoding="utf-8"))
    release = next(item for item in manifest["tiers"] if item["id"] == "release-candidate")
    release["commands"] = [
        command
        for command in release["commands"]
        if "scripts/validate_multi_repo_fixtures_live.py" not in command
    ]
    write_json(tier_path, manifest)

    report = validate_skill_regression_tiers(
        SkillRegressionTierConfig(
            config_root=root,
            output_path=tmp_path / "tier-report.json",
        )
    )

    assert report["status"] == "failed"
    assert any(
        error["tier_id"] == "release-candidate" and "multi-repo fixture" in error["message"]
        for error in report["errors"]
    )


def test_skill_regression_tiers_reject_missing_command_path(tmp_path: Path) -> None:
    root = copy_tier_root(tmp_path)
    tier_path = root / "runtime" / "skill_regression_tiers.json"
    manifest = json.loads(tier_path.read_text(encoding="utf-8"))
    offline = next(item for item in manifest["tiers"] if item["id"] == "offline")
    offline["commands"].append(["python", "scripts/missing_validator.py"])
    write_json(tier_path, manifest)

    report = validate_skill_regression_tiers(
        SkillRegressionTierConfig(
            config_root=root,
            output_path=tmp_path / "tier-report.json",
        )
    )

    assert report["status"] == "failed"
    assert any("missing path" in error["message"] for error in report["errors"])
