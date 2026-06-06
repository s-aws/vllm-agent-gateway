from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import vllm_agent_gateway.acceptance.first_time_user_doctor as doctor
from vllm_agent_gateway.acceptance.first_time_user_doctor import FirstTimeUserDoctorConfig, run_first_time_user_doctor


def write_json(path: Path, value: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def write_fixture(root: Path) -> None:
    (root / "core").mkdir(parents=True)
    (root / "tests").mkdir(parents=True)
    (root / "core" / "stealth_order_manager.py").write_text("class StealthOrderManager: pass\n", encoding="utf-8")
    (root / "configuration.py").write_text("COINBASE_API_KEY = None\n", encoding="utf-8")
    (root / "tests" / "test_order_id.py").write_text("def test_placeholder(): pass\n", encoding="utf-8")


def write_manifest(config_root: Path, fixture_a: Path, fixture_b: Path) -> Path:
    return write_json(
        config_root / "runtime" / "fixtures.json",
        {
            "schema_version": 1,
            "kind": "fixture_manifest",
            "fixtures": [
                {
                    "id": "fixture-a",
                    "source_path": str(fixture_a),
                    "category": "test",
                    "description": "test fixture a",
                    "protected": True,
                    "disposable_only": True,
                    "watched_paths": ["configuration.py", "core/stealth_order_manager.py"],
                },
                {
                    "id": "fixture-b",
                    "source_path": str(fixture_b),
                    "category": "test",
                    "description": "test fixture b",
                    "protected": True,
                    "disposable_only": True,
                    "watched_paths": ["configuration.py", "core/stealth_order_manager.py"],
                },
            ],
        },
    )


def write_roles(config_root: Path) -> Path:
    return write_json(
        config_root / "runtime" / "roles.json",
        {
            "schema_version": 1,
            "roles": [
                {"id": "reviewer/code", "role": "reviewer", "subrole": "code", "port": 8101},
                {"id": "tester/code", "role": "tester", "subrole": "code", "port": 8102},
            ],
        },
    )


def fake_json_request_factory(
    *,
    config_root: Path,
    target_roots: tuple[Path, ...],
    anythingllm_base: str = "http://127.0.0.1:8500/v1",
    allowed_roots: list[str] | None = None,
):
    allowed = allowed_roots or [str(config_root), *(str(root) for root in target_roots)]

    def fake_json_request(
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout_seconds: int,
    ) -> tuple[int, dict[str, Any]]:
        del payload, headers, timeout_seconds
        if url.endswith("/v1/models"):
            return 200, {"object": "list", "data": [{"id": "test-model"}]}
        if url == "http://127.0.0.1:8300/__gateway/health":
            return 200, {
                "ok": True,
                "target_base_url": "http://127.0.0.1:8000",
                "controller_routing": "explicit_envelope",
                "controller_harness_url": "http://127.0.0.1:8400/v1/controller/harness/chat/completions",
            }
        if url == "http://127.0.0.1:8500/__gateway/health":
            return 200, {
                "ok": True,
                "target_base_url": "http://127.0.0.1:8000",
                "controller_routing": "workflow_router",
                "controller_harness_url": "http://127.0.0.1:8400/v1/controller/workflow-router/chat/completions",
            }
        if url.endswith("/__proxy/health"):
            if ":8101/" in url:
                return 200, {"role_key": "reviewer", "subrole": "code"}
            if ":8102/" in url:
                return 200, {"role_key": "tester", "subrole": "code"}
        if url == "http://127.0.0.1:8400/health":
            return 200, {"kind": "controller_service", "status": "ok", "allowed_target_roots": allowed}
        if url == "http://127.0.0.1:3001/api/ping":
            return 200, {"online": True}
        if url == "http://127.0.0.1:3001/api/v1/workspaces":
            return 200, {"workspaces": [{"slug": "my-workspace"}]}
        if url == "http://127.0.0.1:3001/api/v1/system":
            return 200, {"settings": {"GenericOpenAiBasePath": anythingllm_base}}
        raise AssertionError(f"unexpected URL {url}")

    return fake_json_request


def doctor_config(tmp_path: Path) -> tuple[FirstTimeUserDoctorConfig, tuple[Path, Path]]:
    config_root = tmp_path / "repo"
    fixture_a = tmp_path / "fixture-a"
    fixture_b = tmp_path / "fixture-b"
    write_fixture(fixture_a)
    write_fixture(fixture_b)
    manifest = write_manifest(config_root, fixture_a, fixture_b)
    roles = write_roles(config_root)
    return (
        FirstTimeUserDoctorConfig(
            config_root=config_root,
            target_roots=(str(fixture_a), str(fixture_b)),
            manifest_path=manifest,
            roles_path=roles,
            output_path=tmp_path / "doctor.json",
        ),
        (fixture_a, fixture_b),
    )


def test_first_time_user_doctor_passes_when_stack_and_fixtures_are_configured(tmp_path: Path, monkeypatch) -> None:
    config, roots = doctor_config(tmp_path)
    monkeypatch.setenv("ANYTHINGLLM_API_KEY", "test-key")
    monkeypatch.setattr(
        doctor,
        "json_request",
        fake_json_request_factory(config_root=config.config_root, target_roots=roots),
    )

    report = run_first_time_user_doctor(config)

    assert report["status"] == "passed"
    assert report["summary"]["status_counts"]["failed"] == 0
    assert Path(report["report_path"]).exists()
    assert "controller.allowed_roots" not in report["summary"]["failed_check_ids"]


def test_first_time_user_doctor_fails_when_anythingllm_points_to_wrong_gateway(tmp_path: Path, monkeypatch) -> None:
    config, roots = doctor_config(tmp_path)
    monkeypatch.setenv("ANYTHINGLLM_API_KEY", "test-key")
    monkeypatch.setattr(
        doctor,
        "json_request",
        fake_json_request_factory(
            config_root=config.config_root,
            target_roots=roots,
            anythingllm_base="http://127.0.0.1:8300/v1",
        ),
    )

    report = run_first_time_user_doctor(config)

    assert report["status"] == "failed"
    assert "anythingllm.target_url" in report["summary"]["failed_check_ids"]


def test_first_time_user_doctor_fails_when_controller_allowed_roots_are_missing(tmp_path: Path, monkeypatch) -> None:
    config, roots = doctor_config(tmp_path)
    monkeypatch.setenv("ANYTHINGLLM_API_KEY", "test-key")
    monkeypatch.setattr(
        doctor,
        "json_request",
        fake_json_request_factory(
            config_root=config.config_root,
            target_roots=roots,
            allowed_roots=[str(config.config_root)],
        ),
    )

    report = run_first_time_user_doctor(config)

    assert report["status"] == "failed"
    assert "controller.allowed_roots" in report["summary"]["failed_check_ids"]


def test_first_time_user_doctor_fails_and_skips_anythingllm_details_without_api_key(tmp_path: Path, monkeypatch) -> None:
    config, roots = doctor_config(tmp_path)
    monkeypatch.delenv("ANYTHINGLLM_API_KEY", raising=False)
    monkeypatch.setattr(
        doctor,
        "json_request",
        fake_json_request_factory(config_root=config.config_root, target_roots=roots),
    )

    report = run_first_time_user_doctor(config)

    assert report["status"] == "failed"
    assert "anythingllm.api_key" in report["summary"]["failed_check_ids"]
    skipped = [item["id"] for item in report["checks"] if item["status"] == "skipped"]
    assert "anythingllm.target_url" in skipped


def test_first_time_user_doctor_warns_for_fixture_line_ending_only_git_noise(tmp_path: Path, monkeypatch) -> None:
    config, roots = doctor_config(tmp_path)
    subprocess.run(["git", "-C", str(roots[0]), "init"], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(roots[0]), "add", "."], check=True, capture_output=True, text=True)
    (roots[0] / "configuration.py").write_text("COINBASE_API_KEY = None\r\n", encoding="utf-8")
    monkeypatch.setenv("ANYTHINGLLM_API_KEY", "test-key")
    monkeypatch.setattr(
        doctor,
        "json_request",
        fake_json_request_factory(config_root=config.config_root, target_roots=roots),
    )

    report = run_first_time_user_doctor(config)

    assert report["status"] == "passed"
    warning_ids = report["summary"]["warning_check_ids"]
    assert "fixtures.fixture-a" in warning_ids
    fixture_check = next(item for item in report["checks"] if item["id"] == "fixtures.fixture-a")
    assert fixture_check["details"]["git_eol_only_dirty"] is True
