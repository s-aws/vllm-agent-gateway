from __future__ import annotations

import copy
from pathlib import Path

from vllm_agent_gateway.acceptance.context_index_prototype import read_json_object, write_json
from vllm_agent_gateway.acceptance.small_skill_admission_pilot import (
    SmallSkillAdmissionPilotConfig,
    validate_live_proof,
    validate_policy,
    validate_small_skill_admission_pilot,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "runtime" / "small_skill_admission_pilot_policy.json"


def policy() -> dict:
    return read_json_object(POLICY_PATH)


def live_case(case_id: str, client: str) -> dict:
    if case_id == "python-service-endpoint-route-lookup":
        return {
            "case_id": case_id,
            "client": client,
            "status": "passed",
            "expected_artifact": "downstream_endpoint_route_lookup",
            "expected_route_hint": "l1_endpoint_route_lookup_terms",
            "selected_skills": ["endpoint-route-locator"],
            "source_unchanged": True,
            "artifact_marker_status": {"required": ["service/api.py", "handle_create_order"], "missing": []},
        }
    return {
        "case_id": case_id,
        "client": client,
        "status": "passed",
        "expected_artifact": "downstream_data_model_lookup",
        "expected_route_hint": "l1_data_model_lookup_terms",
        "selected_skills": ["data-model-schema-locator"],
        "source_unchanged": True,
        "artifact_marker_status": {"required": ["database/schema.py", "OrderRecord", "ORDERS_TABLE_SCHEMA"], "missing": []},
    }


def live_report() -> dict:
    cases = []
    for case_id in ("python-service-endpoint-route-lookup", "python-service-schema-lookup"):
        for client in ("gateway", "anythingllm"):
            cases.append(live_case(case_id, client))
    return {"status": "passed", "cases": cases}


def test_phase230_policy_passes() -> None:
    assert validate_policy(policy()) == []


def test_phase230_policy_rejects_manual_skill_injection() -> None:
    mutated = copy.deepcopy(policy())
    mutated["candidate"]["manual_skill_injection_allowed"] = True

    errors = validate_policy(mutated)

    assert any(item["id"] == "policy.candidate.manual_skill_injection_allowed" for item in errors)


def test_phase230_live_proof_requires_gateway_and_anythingllm() -> None:
    mutated = live_report()
    mutated["cases"] = [case for case in mutated["cases"] if case["client"] == "gateway"]

    errors = validate_live_proof(policy(), mutated)

    assert any("anythingllm" in item["id"] for item in errors)


def test_phase230_live_proof_requires_artifact_markers() -> None:
    mutated = live_report()
    mutated["cases"][0]["artifact_marker_status"]["missing"] = ["handle_create_order"]

    errors = validate_live_proof(policy(), mutated)

    assert any(item["id"].endswith("artifact_markers_missing") for item in errors)


def test_phase230_project_contract_passes_without_live_artifact(tmp_path: Path) -> None:
    report = validate_small_skill_admission_pilot(
        SmallSkillAdmissionPilotConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "report.json",
            markdown_output_path=tmp_path / "report.md",
            require_artifacts=False,
        )
    )

    assert report["summary"]["candidate_id"] == "FX-001"
    assert report["summary"]["candidate_status"] == "implemented"
    assert not any(item["id"].startswith("coverage.") for item in report["validation_errors"])


def test_phase230_project_report_passes_with_synthetic_live_artifact(tmp_path: Path) -> None:
    mutated_policy = copy.deepcopy(policy())
    live_path = tmp_path / "live.json"
    write_json(live_path, live_report())
    mutated_policy["live_proof"]["report_path"] = str(live_path)
    policy_path = tmp_path / "policy.json"
    write_json(policy_path, mutated_policy)

    report = validate_small_skill_admission_pilot(
        SmallSkillAdmissionPilotConfig(
            config_root=REPO_ROOT,
            policy_path=policy_path,
            output_path=tmp_path / "report.json",
            markdown_output_path=tmp_path / "report.md",
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["phase231_ready"] is True


def test_phase230_live_report_path_override_supports_handoff_reruns(tmp_path: Path) -> None:
    mutated_policy = copy.deepcopy(policy())
    stale_live_path = tmp_path / "stale-live.json"
    fresh_live_path = tmp_path / "fresh-live.json"
    write_json(stale_live_path, {"status": "failed", "cases": []})
    write_json(fresh_live_path, live_report())
    mutated_policy["live_proof"]["report_path"] = str(stale_live_path)
    policy_path = tmp_path / "policy.json"
    write_json(policy_path, mutated_policy)

    report = validate_small_skill_admission_pilot(
        SmallSkillAdmissionPilotConfig(
            config_root=REPO_ROOT,
            policy_path=policy_path,
            output_path=tmp_path / "report.json",
            markdown_output_path=tmp_path / "report.md",
            live_report_path=fresh_live_path,
        )
    )

    assert report["status"] == "passed"
    assert report["live_report_path"] == str(fresh_live_path)
