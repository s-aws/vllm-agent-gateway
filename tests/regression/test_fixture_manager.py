from __future__ import annotations

import json
from pathlib import Path

from vllm_agent_gateway.fixtures.manager import (
    FixtureCommand,
    FixtureManagerError,
    cleanup_run,
    load_fixture_manifest,
    run_fixture_manager,
    validate_fixture_manifest,
)
from scripts.validate_multi_repo_fixtures_live import LIVE_CASES


REPO_ROOT = Path(__file__).resolve().parents[2]


def make_fixture_source(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    (source / "README.md").write_text("# Fixture\n", encoding="utf-8")
    (source / "service").mkdir()
    (source / "service" / "orders.py").write_text("def resolve_order_status():\n    return 'ok'\n", encoding="utf-8")
    return source


def manifest_for(source: Path) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "fixture_manifest",
        "fixtures": [
            {
                "id": "unit-fixture",
                "source_path": str(source),
                "category": "unit",
                "description": "unit fixture",
                "protected": True,
                "disposable_only": True,
                "watched_paths": ["README.md", "service/orders.py"],
            }
        ],
    }


def write_manifest(tmp_path: Path, source: Path) -> Path:
    path = tmp_path / "fixtures.json"
    path.write_text(json.dumps(manifest_for(source)), encoding="utf-8")
    return path


def test_fixture_manager_project_manifest_is_valid() -> None:
    manifest = load_fixture_manifest(REPO_ROOT)

    assert {item["id"] for item in manifest["fixtures"]} >= {
        "coinbase-frozen",
        "coinbase-frozen-git",
        "python-service-generalization",
        "node-cli-generalization",
    }
    by_id = {item["id"]: item for item in manifest["fixtures"]}
    assert by_id["node-cli-generalization"]["category"] == "synthetic-node-cli"


def test_multi_repo_live_case_catalog_covers_coinbase_and_node_fixture() -> None:
    by_fixture = {case.fixture_id: case for case in LIVE_CASES}

    assert {"coinbase-frozen", "coinbase-frozen-git", "node-cli-generalization"} <= set(by_fixture)
    assert by_fixture["node-cli-generalization"].expected_artifact == "downstream_configuration_lookup"
    assert "hardcoded" not in by_fixture["node-cli-generalization"].prompt_template.lower()


def test_fixture_manager_setup_copies_and_cleanup_removes_without_source_mutation(tmp_path: Path) -> None:
    source = make_fixture_source(tmp_path)
    manifest = write_manifest(tmp_path, source)
    output_root = tmp_path / "managed"

    report = run_fixture_manager(
        config_root=tmp_path,
        command=FixtureCommand.SETUP,
        manifest_path=manifest,
        fixture_ids=("unit-fixture",),
        output_root=output_root,
        run_id="unit-run",
        cleanup_after=True,
        report_path=tmp_path / "report.json",
    )

    assert report["status"] == "passed"
    assert report["setup"][0]["source_unchanged"] is True
    assert report["setup"][0]["copy_hash_count"] == 2
    assert report["cleanup"]["removed"] is True
    assert not (output_root / "unit-run").exists()
    assert (source / "service" / "orders.py").read_text(encoding="utf-8") == "def resolve_order_status():\n    return 'ok'\n"


def test_fixture_manager_snapshot_reports_watched_hashes(tmp_path: Path) -> None:
    source = make_fixture_source(tmp_path)
    manifest = write_manifest(tmp_path, source)

    report = run_fixture_manager(
        config_root=tmp_path,
        command=FixtureCommand.SNAPSHOT,
        manifest_path=manifest,
        fixture_ids=("unit-fixture",),
        report_path=tmp_path / "snapshot.json",
    )

    assert report["status"] == "passed"
    assert set(report["snapshots"][0]["watched_hashes"]) == {"README.md", "service/orders.py"}


def test_fixture_manager_rejects_invalid_manifest(tmp_path: Path) -> None:
    source = make_fixture_source(tmp_path)
    manifest = manifest_for(source)
    manifest["fixtures"][0]["watched_paths"] = ["../outside.py"]

    errors = validate_fixture_manifest(manifest, config_root=tmp_path)

    assert any("watched_paths" in error for error in errors)


def test_fixture_manager_cleanup_refuses_outside_root(tmp_path: Path) -> None:
    output_root = tmp_path / "managed"
    output_root.mkdir()

    try:
        cleanup_run(output_root, run_id="../outside")
    except FixtureManagerError as exc:
        assert "must stay under" in str(exc)
    else:
        raise AssertionError("cleanup_run accepted an out-of-root run id")
