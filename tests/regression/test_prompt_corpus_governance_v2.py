import json
from pathlib import Path

from vllm_agent_gateway.acceptance.prompt_corpus_governance_v2 import (
    PromptCorpusGovernanceV2Config,
    build_prompt_corpus_governance_v2_report,
    run_prompt_corpus_governance_v2,
    validate_policy,
    validate_prompt_corpus_governance_v2_report,
)


def write_json(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def synthetic_sources(tmp_path: Path) -> tuple[dict, dict, dict, dict[str, Path]]:
    catalog = {
        "kind": "prompt_catalog",
        "cases": [{"case_id": "P01"}, {"case_id": "P02"}, {"case_id": "P03"}],
    }
    delta_report = {
        "kind": "blind_baseline_delta_report",
        "status": "passed",
        "deltas": [
            {"family": "family_a", "role": "target", "case_id": "P01", "score": 90},
            {"family": "family_a", "role": "holdout", "case_id": "P02", "score": 91},
        ],
    }
    policy = {
        "schema_version": 1,
        "kind": "prompt_corpus_governance_v2_policy",
        "phase": 179,
        "priority_backlog_id": "P0-BB-043",
        "source_catalog_path": "catalog.json",
        "source_delta_report_path": "delta.json",
        "expected_catalog_case_count": 3,
        "minimum_holdout_score": 85,
        "roles": {
            "target": ["P01"],
            "holdout": ["P02"],
            "regression": ["P01", "P02", "P03"],
            "promotion_candidate": ["P01"],
            "retired": [],
        },
        "target_holdout_links": [
            {
                "family": "family_a",
                "target_case_id": "P01",
                "holdout_case_ids": ["P02"],
            }
        ],
        "promotion_rules": {
            "stable_corpus_update_requires_separate_phase": True,
            "auto_promote_allowed": False,
        },
        "promotion_candidate_groups": [
            {
                "candidate_id": "candidate-a",
                "case_ids": ["P01"],
                "required_holdout_case_ids": ["P02"],
                "decision_status": "blocked_pending_founder_approval",
                "founder_approval": {"status": "not_requested"},
            }
        ],
    }
    paths = {
        "policy": write_json(tmp_path / "policy.json", policy),
        "catalog": write_json(tmp_path / "catalog.json", catalog),
        "delta": write_json(tmp_path / "delta.json", delta_report),
    }
    return policy, catalog, delta_report, paths


def test_prompt_corpus_governance_v2_policy_passes_synthetic_sources(tmp_path: Path) -> None:
    policy, catalog, delta_report, _ = synthetic_sources(tmp_path)

    assert validate_policy(policy, catalog, delta_report) == []


def test_prompt_corpus_governance_v2_report_passes_synthetic_sources(tmp_path: Path) -> None:
    policy, catalog, delta_report, paths = synthetic_sources(tmp_path)

    report = build_prompt_corpus_governance_v2_report(
        config_root=tmp_path,
        policy=policy,
        catalog=catalog,
        delta_report=delta_report,
        policy_path=paths["policy"],
        catalog_path=paths["catalog"],
        delta_report_path=paths["delta"],
    )

    assert report["status"] == "passed"
    assert report["summary"]["target_count"] == 1
    assert report["summary"]["holdout_count"] == 1
    assert report["summary"]["blocked_candidate_count"] == 1


def test_prompt_corpus_governance_v2_rejects_unassigned_catalog_case(tmp_path: Path) -> None:
    policy, catalog, delta_report, _ = synthetic_sources(tmp_path)
    policy["roles"]["regression"].remove("P03")

    errors = validate_policy(policy, catalog, delta_report)

    assert any(error["id"] == "roles.unassigned" for error in errors)


def test_prompt_corpus_governance_v2_rejects_target_without_holdout_link(tmp_path: Path) -> None:
    policy, catalog, delta_report, _ = synthetic_sources(tmp_path)
    policy["target_holdout_links"] = []

    errors = validate_policy(policy, catalog, delta_report)

    assert any(error["id"] == "target_holdout_links.missing" for error in errors)


def test_prompt_corpus_governance_v2_rejects_target_as_own_holdout(tmp_path: Path) -> None:
    policy, catalog, delta_report, _ = synthetic_sources(tmp_path)
    policy["roles"]["holdout"].append("P01")
    policy["target_holdout_links"][0]["holdout_case_ids"] = ["P01"]

    errors = validate_policy(policy, catalog, delta_report)

    assert any(error["id"] == "target_holdout_links[0].self_holdout" for error in errors)


def test_prompt_corpus_governance_v2_rejects_approved_candidate_without_founder_approval(tmp_path: Path) -> None:
    policy, catalog, delta_report, _ = synthetic_sources(tmp_path)
    policy["promotion_candidate_groups"][0]["decision_status"] = "approved_for_promotion"

    errors = validate_policy(policy, catalog, delta_report)

    assert any(error["id"] == "promotion_candidate_groups[0].founder_approval" for error in errors)


def test_prompt_corpus_governance_v2_rejects_promoted_status_in_same_phase(tmp_path: Path) -> None:
    policy, catalog, delta_report, _ = synthetic_sources(tmp_path)
    policy["promotion_candidate_groups"][0]["decision_status"] = "promoted"
    policy["promotion_candidate_groups"][0]["founder_approval"] = {"status": "approved"}

    errors = validate_policy(policy, catalog, delta_report)

    assert any(error["id"] == "promotion_candidate_groups[0].promoted" for error in errors)


def test_prompt_corpus_governance_v2_rejects_missing_delta_holdout(tmp_path: Path) -> None:
    policy, catalog, delta_report, _ = synthetic_sources(tmp_path)
    delta_report["deltas"] = [delta_report["deltas"][0]]

    errors = validate_policy(policy, catalog, delta_report)

    assert any(error["id"] == "target_holdout_links[0].holdout_delta.P02" for error in errors)


def test_run_prompt_corpus_governance_v2_writes_json_and_markdown(tmp_path: Path) -> None:
    _, _, _, _ = synthetic_sources(tmp_path)

    report = run_prompt_corpus_governance_v2(
        PromptCorpusGovernanceV2Config(
            config_root=tmp_path,
            policy_path=Path("policy.json"),
            output_path=Path("out/report.json"),
            markdown_output_path=Path("out/report.md"),
        )
    )
    persisted = json.loads((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))

    assert report["status"] == "passed"
    assert persisted["report_path"] == str((tmp_path / "out" / "report.json").resolve())
    assert (tmp_path / "out" / "report.md").read_text(encoding="utf-8").startswith("# Prompt Corpus Governance V2")
    assert (
        validate_prompt_corpus_governance_v2_report(
            persisted,
            config_root=tmp_path,
            policy=json.loads((tmp_path / "policy.json").read_text(encoding="utf-8")),
            catalog=json.loads((tmp_path / "catalog.json").read_text(encoding="utf-8")),
            delta_report=json.loads((tmp_path / "delta.json").read_text(encoding="utf-8")),
            policy_path=tmp_path / "policy.json",
            catalog_path=tmp_path / "catalog.json",
            delta_report_path=tmp_path / "delta.json",
        )
        == []
    )
