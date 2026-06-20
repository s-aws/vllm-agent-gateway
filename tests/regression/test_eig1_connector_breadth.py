from __future__ import annotations

import copy
import json
from pathlib import Path

from vllm_agent_gateway.acceptance.eig1_connector_breadth import (
    DEFAULT_FIXTURE_PATH,
    EIG1ConnectorBreadthConfig,
    run_eig1_connector_breadth_validation,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def write_json(path: Path, value: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def fixture_pack() -> dict[str, object]:
    return json.loads((REPO_ROOT / DEFAULT_FIXTURE_PATH).read_text(encoding="utf-8"))


def run_with_pack(tmp_path: Path, pack: dict[str, object]) -> dict[str, object]:
    fixture_path = write_json(tmp_path / "fixtures.json", pack)
    return run_eig1_connector_breadth_validation(
        EIG1ConnectorBreadthConfig(
            config_root=REPO_ROOT,
            fixture_path=fixture_path,
            output_path=tmp_path / "report.json",
        )
    )


def error_ids(report: dict[str, object]) -> set[str]:
    errors = report["validation_errors"]
    assert isinstance(errors, list)
    return {str(item["id"]) for item in errors if isinstance(item, dict)}


def test_eig1_connector_breadth_fixture_pack_passes(tmp_path: Path) -> None:
    report = run_eig1_connector_breadth_validation(
        EIG1ConnectorBreadthConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "report.json",
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["connector_manifest_count"] == 3
    assert report["summary"]["archetype_count"] == 3
    assert report["summary"]["positive_invocation_count"] == 6
    assert report["summary"]["negative_control_count"] == 10
    assert report["summary"]["runtime_registry_changed"] is False
    assert report["summary"]["target_repository_changed"] is False
    assert report["summary"]["external_network_called"] is False
    assert report["summary"]["raw_mcp_used"] is False
    assert report["summary"]["direct_model_tool_access_used"] is False
    assert report["summary"]["raw_fixture_arguments_retained_in_report"] is False
    assert report["summary"]["phase290_ready"] is True


def test_eig1_connector_breadth_rejects_missing_archetype(tmp_path: Path) -> None:
    pack = fixture_pack()
    mutated = copy.deepcopy(pack)
    manifests = mutated["connector_manifests"]
    assert isinstance(manifests, list)
    mutated["connector_manifests"] = [
        item for item in manifests if not (isinstance(item, dict) and item.get("archetype") == "business_record")
    ]

    report = run_with_pack(tmp_path, mutated)

    assert report["status"] == "failed"
    assert "pack.connector_manifests.archetypes" in error_ids(report)


def test_eig1_connector_breadth_rejects_missing_negative_control(tmp_path: Path) -> None:
    pack = fixture_pack()
    mutated = copy.deepcopy(pack)
    controls = mutated["negative_controls"]
    assert isinstance(controls, list)
    mutated["negative_controls"] = [
        item for item in controls if not (isinstance(item, dict) and item.get("scenario") == "raw_mcp_allowed_manifest")
    ]

    report = run_with_pack(tmp_path, mutated)

    assert report["status"] == "failed"
    assert "pack.negative_controls.scenarios" in error_ids(report)


def test_eig1_connector_breadth_rejects_raw_mcp_enabled_manifest(tmp_path: Path) -> None:
    pack = fixture_pack()
    mutated = copy.deepcopy(pack)
    manifests = mutated["connector_manifests"]
    assert isinstance(manifests, list)
    first_manifest = manifests[0]
    assert isinstance(first_manifest, dict)
    manifest = first_manifest["manifest"]
    assert isinstance(manifest, dict)
    connector = manifest["connector"]
    assert isinstance(connector, dict)
    safety = connector["safety"]
    assert isinstance(safety, dict)
    safety["raw_mcp_allowed"] = True

    report = run_with_pack(tmp_path, mutated)

    assert report["status"] == "failed"
    assert "raw_mcp_bypass_not_allowed" in error_ids(report)


def test_eig1_connector_breadth_rejects_raw_argument_retention(tmp_path: Path) -> None:
    pack = fixture_pack()
    mutated = copy.deepcopy(pack)
    cases = mutated["positive_invocation_cases"]
    assert isinstance(cases, list)
    first_case = cases[0]
    assert isinstance(first_case, dict)
    arguments = first_case["arguments"]
    assert isinstance(arguments, dict)
    arguments["work_item_id"] = "WORK-SYN-1042"

    report = run_with_pack(tmp_path, mutated)

    serialized = json.dumps(report, sort_keys=True)
    assert "WORK-SYN-1042" not in serialized
    assert report["summary"]["raw_fixture_arguments_retained_in_report"] is False
