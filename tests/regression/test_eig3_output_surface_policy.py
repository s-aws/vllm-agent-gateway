from __future__ import annotations

import copy
import json
from pathlib import Path

from vllm_agent_gateway.acceptance.eig3_output_surface_policy import (
    DEFAULT_POLICY_PATH,
    EIG3OutputSurfacePolicyConfig,
    run_eig3_output_surface_policy_validation,
)
from vllm_agent_gateway.acceptance.eig3_sensitive_data import DEFAULT_FIXTURE_PATH


REPO_ROOT = Path(__file__).resolve().parents[2]


def write_json(path: Path, value: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def policy() -> dict[str, object]:
    return json.loads((REPO_ROOT / DEFAULT_POLICY_PATH).read_text(encoding="utf-8"))


def fixture_pack() -> dict[str, object]:
    return json.loads((REPO_ROOT / DEFAULT_FIXTURE_PATH).read_text(encoding="utf-8"))


def fixture_by_id(pack: dict[str, object], fixture_id: str) -> dict[str, object]:
    fixtures = pack["fixtures"]
    assert isinstance(fixtures, list)
    for fixture in fixtures:
        assert isinstance(fixture, dict)
        if fixture["id"] == fixture_id:
            return fixture
    raise AssertionError(f"missing fixture {fixture_id}")


def run_with_values(tmp_path: Path, policy_value: dict[str, object], fixture_value: dict[str, object] | None = None) -> dict[str, object]:
    policy_path = write_json(tmp_path / "policy.json", policy_value)
    fixture_path = write_json(tmp_path / "fixtures.json", fixture_value or fixture_pack())
    return run_eig3_output_surface_policy_validation(
        EIG3OutputSurfacePolicyConfig(
            config_root=REPO_ROOT,
            policy_path=policy_path,
            fixture_path=fixture_path,
            output_path=tmp_path / "report.json",
        )
    )


def error_ids(report: dict[str, object]) -> set[str]:
    errors = report["validation_errors"]
    assert isinstance(errors, list)
    return {str(item["id"]) for item in errors if isinstance(item, dict)}


def test_eig3_output_surface_policy_passes(tmp_path: Path) -> None:
    report = run_eig3_output_surface_policy_validation(
        EIG3OutputSurfacePolicyConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "report.json",
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["fixture_count"] == 30
    assert report["summary"]["surface_count"] == 6
    assert report["summary"]["phase300_ready"] is True
    assert report["summary"]["json_default_parity_required"] is True
    assert report["summary"]["raw_fixture_text_retained_in_report"] is False
    serialized = json.dumps(report, sort_keys=True)
    assert "casey.meridian@example.test" not in serialized
    assert "sk-synth-ABCDEF1234567890" not in serialized
    assert "Synthetic profile" not in serialized


def test_eig3_output_surface_policy_rejects_json_default_drift(tmp_path: Path) -> None:
    pack = copy.deepcopy(fixture_pack())
    fixture = fixture_by_id(pack, "EIG3-PII-R1")
    surfaces = fixture["surface_decisions"]
    assert isinstance(surfaces, dict)
    surfaces["json"] = "summarize"

    report = run_with_values(tmp_path, policy(), pack)

    assert report["status"] == "failed"
    assert "fixture.json_default_parity" in error_ids(report)


def test_eig3_output_surface_policy_rejects_secret_chat_allow(tmp_path: Path) -> None:
    pack = copy.deepcopy(fixture_pack())
    fixture = fixture_by_id(pack, "EIG3-SEC-R1")
    surfaces = fixture["surface_decisions"]
    assert isinstance(surfaces, dict)
    surfaces["chat"] = "allow"
    surfaces["json"] = "allow"

    report = run_with_values(tmp_path, policy(), pack)

    assert report["status"] == "failed"
    assert "fixture.surface_decision_not_allowed" in error_ids(report)
    assert "fixture.secret_allow" in error_ids(report)


def test_eig3_output_surface_policy_rejects_missing_run_state_policy(tmp_path: Path) -> None:
    mutated = copy.deepcopy(policy())
    surface_rules = mutated["surface_rules"]
    assert isinstance(surface_rules, dict)
    del surface_rules["run_state_summary"]

    report = run_with_values(tmp_path, mutated)

    assert report["status"] == "failed"
    assert "policy.surface_rules" in error_ids(report)


def test_eig3_output_surface_policy_rejects_negative_control_without_refusal(tmp_path: Path) -> None:
    mutated = copy.deepcopy(policy())
    negative = mutated["negative_control"]
    assert isinstance(negative, dict)
    negative["chat"] = "mask"

    report = run_with_values(tmp_path, mutated)

    assert report["status"] == "failed"
    assert "policy.negative_control" in error_ids(report)
    assert "fixture.surface_decision_not_allowed" in error_ids(report)
