from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.founder_test_prompt_pack import (
    build_prompt_pack_report,
    read_json_object,
    resolve_path,
    validate_pack,
    validate_prompt_pack_report,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
PACK_PATH = REPO_ROOT / "runtime" / "founder_test_prompt_pack.json"


def pack() -> dict[str, Any]:
    return read_json_object(PACK_PATH)


def catalog_for(pack_payload: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    catalog_path = resolve_path(REPO_ROOT, pack_payload["catalog_path"])
    return catalog_path, read_json_object(catalog_path)


def project_report(pack_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = pack_payload or pack()
    catalog_path, catalog = catalog_for(payload)
    return build_prompt_pack_report(
        config_root=REPO_ROOT,
        pack=payload,
        catalog=catalog,
        pack_path=PACK_PATH,
        catalog_path=catalog_path,
    )


def validate_report(report: dict[str, Any], pack_payload: dict[str, Any] | None = None) -> list[str]:
    payload = pack_payload or pack()
    catalog_path, catalog = catalog_for(payload)
    return validate_prompt_pack_report(
        report,
        config_root=REPO_ROOT,
        pack=payload,
        catalog=catalog,
        pack_path=PACK_PATH,
        catalog_path=catalog_path,
    )


def test_project_founder_test_prompt_pack_passes() -> None:
    payload = pack()
    _catalog_path, catalog = catalog_for(payload)
    assert validate_pack(payload, catalog=catalog, config_root=REPO_ROOT) == []
    report = project_report(payload)
    assert validate_report(report, payload) == []
    assert report["status"] == "passed"
    assert report["summary"]["case_count"] >= 12
    assert report["tiers"]["smoke"] == ["P01", "P02", "P03", "P22"]


def test_prompt_pack_rejects_unknown_case_id() -> None:
    broken = pack()
    broken["tiers"][1]["case_ids"].append("PX999")
    report = project_report(broken)
    assert any("unknown case IDs" in error for error in report["errors"])


def test_prompt_pack_rejects_duplicate_case_id() -> None:
    broken = pack()
    broken["tiers"][1]["case_ids"].append("P01")
    report = project_report(broken)
    assert any("duplicate case IDs" in error for error in report["errors"])


def test_prompt_pack_rejects_draft_only_case() -> None:
    broken = pack()
    broken["tiers"][1]["case_ids"].append("P23")
    report = project_report(broken)
    assert any("forbidden founder-pack tag" in error for error in report["errors"])


def test_prompt_pack_rejects_missing_task_decomposition_workflow() -> None:
    broken = pack()
    broken["tiers"][0]["case_ids"] = ["P01", "P02", "P03", "P04"]
    report = project_report(broken)
    assert any("smoke tier must match" in error for error in report["errors"])
    assert any("task.decompose" in error for error in report["errors"])


def test_prompt_pack_rejects_hidden_summary_change() -> None:
    report = project_report()
    report["summary"]["case_count"] = 999
    errors = validate_report(report)
    assert any("report.summary must match rebuilt founder test prompt pack" in error for error in errors)


def test_prompt_pack_rejects_catalog_without_required_root() -> None:
    broken = copy.deepcopy(pack())
    broken["tiers"][1]["case_ids"] = ["P04", "P05", "P06", "P08", "P09", "P10", "P17", "P19", "P21"]
    report = project_report(broken)
    assert any("missing required target roots" in error for error in report["errors"])
