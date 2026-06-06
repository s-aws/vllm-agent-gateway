from __future__ import annotations

import json
from pathlib import Path

from vllm_agent_gateway.acceptance.release_channels import ReleaseChannelValidationConfig, validate_release_channels


REPO_ROOT = Path(__file__).resolve().parents[2]


def write_json(path: Path, value: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_current_manifest() -> dict[str, object]:
    return json.loads((REPO_ROOT / "runtime" / "release_channels.json").read_text(encoding="utf-8"))


def test_release_channel_manifest_passes_current_contract(tmp_path: Path) -> None:
    report = validate_release_channels(
        ReleaseChannelValidationConfig(
            config_root=REPO_ROOT,
            output_path=tmp_path / "release-channels.json",
        )
    )

    assert report["status"] == "passed"
    assert report["channel_ids"] == ["dev", "release-candidate", "stable"]
    assert report["summary"]["failed_check_ids"] == []
    assert Path(report["report_path"]).exists()
    stable = next(item for item in report["checks"] if item["id"] == "stable.readiness")
    assert stable["status"] == "passed"
    assert stable["details"]["stable_status"] == "blocked"


def test_release_channel_validation_rejects_missing_required_doc(tmp_path: Path) -> None:
    manifest = load_current_manifest()
    channels = manifest["channels"]
    assert isinstance(channels, list)
    release_candidate = channels[1]
    assert isinstance(release_candidate, dict)
    release_candidate["required_docs"] = [*release_candidate["required_docs"], "README.missing-release-doc.md"]
    manifest_path = write_json(tmp_path / "release_channels.json", manifest)

    report = validate_release_channels(
        ReleaseChannelValidationConfig(
            config_root=REPO_ROOT,
            manifest_path=manifest_path,
            output_path=tmp_path / "report.json",
        )
    )

    assert report["status"] == "failed"
    by_id = {item["id"]: item for item in report["checks"]}
    assert by_id["channel.release-candidate.contract"]["status"] == "failed"
    assert any("required_docs missing files" in item for item in by_id["channel.release-candidate.contract"]["details"]["errors"])


def test_stable_channel_cannot_be_active_without_release_candidate_report(tmp_path: Path) -> None:
    manifest = load_current_manifest()
    channels = manifest["channels"]
    assert isinstance(channels, list)
    stable = channels[2]
    assert isinstance(stable, dict)
    stable["status"] = "active"
    manifest_path = write_json(tmp_path / "release_channels.json", manifest)

    report = validate_release_channels(
        ReleaseChannelValidationConfig(
            config_root=REPO_ROOT,
            manifest_path=manifest_path,
            output_path=tmp_path / "report.json",
        )
    )

    assert report["status"] == "failed"
    stable_check = next(item for item in report["checks"] if item["id"] == "stable.readiness")
    assert stable_check["status"] == "failed"
    assert "release-candidate report path was not provided" in stable_check["details"]["errors"]


def test_stable_channel_can_be_active_with_passing_release_candidate_report(tmp_path: Path) -> None:
    manifest = load_current_manifest()
    channels = manifest["channels"]
    assert isinstance(channels, list)
    stable = channels[2]
    assert isinstance(stable, dict)
    stable["status"] = "active"
    manifest_path = write_json(tmp_path / "release_channels.json", manifest)
    release_candidate_report = write_json(
        tmp_path / "v1-acceptance.json",
        {
            "schema_version": 1,
            "kind": "v1_acceptance_report",
            "status": "passed",
            "profile": "release-candidate",
        },
    )

    report = validate_release_channels(
        ReleaseChannelValidationConfig(
            config_root=REPO_ROOT,
            manifest_path=manifest_path,
            output_path=tmp_path / "report.json",
            channel="stable",
            release_candidate_report_path=release_candidate_report,
        )
    )

    assert report["status"] == "passed"
    stable_check = next(item for item in report["checks"] if item["id"] == "stable.readiness")
    assert stable_check["status"] == "passed"
    assert stable_check["details"]["status"] == "passed"
    assert stable_check["details"]["profile"] == "release-candidate"


def test_stable_channel_can_be_active_with_passing_v1_1_release_candidate_report(tmp_path: Path) -> None:
    manifest = load_current_manifest()
    channels = manifest["channels"]
    assert isinstance(channels, list)
    stable = channels[2]
    assert isinstance(stable, dict)
    stable["status"] = "active"
    manifest_path = write_json(tmp_path / "release_channels.json", manifest)
    release_candidate_report = write_json(
        tmp_path / "v1-1-acceptance.json",
        {
            "schema_version": 1,
            "kind": "v1_acceptance_report",
            "status": "passed",
            "profile": "v1.1-release-candidate",
        },
    )

    report = validate_release_channels(
        ReleaseChannelValidationConfig(
            config_root=REPO_ROOT,
            manifest_path=manifest_path,
            output_path=tmp_path / "report.json",
            channel="stable",
            release_candidate_report_path=release_candidate_report,
        )
    )

    assert report["status"] == "passed"
    stable_check = next(item for item in report["checks"] if item["id"] == "stable.readiness")
    assert stable_check["status"] == "passed"
    assert stable_check["details"]["status"] == "passed"
    assert stable_check["details"]["profile"] == "v1.1-release-candidate"
