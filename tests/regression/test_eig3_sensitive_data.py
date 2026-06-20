from __future__ import annotations

import copy
import json
from pathlib import Path

from vllm_agent_gateway.acceptance.eig3_sensitive_data import (
    DEFAULT_FIXTURE_PATH,
    EIG3SensitiveDataConfig,
    run_eig3_sensitive_data_validation,
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
    return run_eig3_sensitive_data_validation(
        EIG3SensitiveDataConfig(
            config_root=REPO_ROOT,
            fixture_path=fixture_path,
            output_path=tmp_path / "report.json",
        )
    )


def fixture_by_id(pack: dict[str, object], fixture_id: str) -> dict[str, object]:
    fixtures = pack["fixtures"]
    assert isinstance(fixtures, list)
    for fixture in fixtures:
        assert isinstance(fixture, dict)
        if fixture["id"] == fixture_id:
            return fixture
    raise AssertionError(f"missing fixture {fixture_id}")


def error_ids(report: dict[str, object]) -> set[str]:
    errors = report["validation_errors"]
    assert isinstance(errors, list)
    return {str(item["id"]) for item in errors if isinstance(item, dict)}


def test_eig3_sensitive_data_fixture_pack_passes(tmp_path: Path) -> None:
    report = run_eig3_sensitive_data_validation(
        EIG3SensitiveDataConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "report.json",
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["fixture_count"] == 30
    assert report["summary"]["archetype_count"] == 3
    assert report["summary"]["phase299_ready"] is True
    assert report["summary"]["raw_fixture_text_retained_in_report"] is False
    serialized = json.dumps(report, sort_keys=True)
    assert "casey.meridian@example.test" not in serialized
    assert "sk-synth-ABCDEF1234567890" not in serialized
    assert "Synthetic profile" not in serialized


def test_eig3_sensitive_data_rejects_missing_required_case_count(tmp_path: Path) -> None:
    pack = fixture_pack()
    mutated = copy.deepcopy(pack)
    fixtures = mutated["fixtures"]
    assert isinstance(fixtures, list)
    mutated["fixtures"] = [
        fixture
        for fixture in fixtures
        if not (isinstance(fixture, dict) and fixture.get("id") == "EIG3-PII-R1")
    ]

    report = run_with_pack(tmp_path, mutated)

    assert report["status"] == "failed"
    assert "counts.required" in error_ids(report)


def test_eig3_sensitive_data_rejects_false_negative_expectation(tmp_path: Path) -> None:
    pack = copy.deepcopy(fixture_pack())
    fixture_by_id(pack, "EIG3-SEC-R1")["expected_sensitive_classes"] = []

    report = run_with_pack(tmp_path, pack)

    assert report["status"] == "failed"
    assert "fixture.detected_classes" in error_ids(report)


def test_eig3_sensitive_data_rejects_secret_chat_allow_surface(tmp_path: Path) -> None:
    pack = copy.deepcopy(fixture_pack())
    fixture = fixture_by_id(pack, "EIG3-SEC-R1")
    surfaces = fixture["surface_decisions"]
    assert isinstance(surfaces, dict)
    surfaces["chat"] = "allow"

    report = run_with_pack(tmp_path, pack)

    assert report["status"] == "failed"
    assert "fixture.secret_surface_allow" in error_ids(report)


def test_eig3_sensitive_data_rejects_non_synthetic_fixture(tmp_path: Path) -> None:
    pack = copy.deepcopy(fixture_pack())
    fixture_by_id(pack, "EIG3-BIZ-R1")["synthetic_only"] = False

    report = run_with_pack(tmp_path, pack)

    assert report["status"] == "failed"
    assert "fixture.synthetic_only" in error_ids(report)
