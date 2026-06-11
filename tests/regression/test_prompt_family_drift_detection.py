import json
from pathlib import Path

from vllm_agent_gateway.acceptance.prompt_family_drift_detection import (
    PromptFamilyDriftDetectionConfig,
    build_prompt_family_drift_detection_report,
    run_prompt_family_drift_detection,
    validate_policy,
    validate_prompt_family_drift_detection_report,
    validate_sources,
)


def write_json(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def synthetic_policy() -> dict:
    return {
        "schema_version": 1,
        "kind": "prompt_family_drift_detection_policy",
        "phase": 191,
        "priority_backlog_id": "P0-BB-055",
        "acceptance_marker": "PHASE191 PROMPT FAMILY DRIFT DETECTION PASS",
        "source_catalog_path": "catalog.json",
        "source_skill_coverage_path": "coverage.json",
        "source_corpus_governance_path": "governance.json",
        "source_holdout_bank_path": "holdouts.json",
        "source_prompt_pack_path": "pack.json",
        "source_kinds": {
            "catalog": "prompt_catalog",
            "skill_coverage": "prompt_skill_coverage_registry",
            "corpus_governance": "prompt_corpus_governance_v2_policy",
            "holdout_bank": "priority0_holdout_prompt_bank",
            "prompt_pack": "founder_test_prompt_pack",
        },
        "expected_catalog_case_count": 2,
        "expected_coverage_entry_count": 1,
        "expected_corpus_role_counts": {
            "target": 1,
            "holdout": 1,
            "regression": 2,
            "promotion_candidate": 0,
            "retired": 0,
        },
        "expected_prompt_pack_tiers": ["smoke"],
        "allowed_active_catalog_blocking_drift_count": 0,
        "decision_contract": {
            "allowed_decisions": ["in_coverage", "holdout", "partial_drift", "out_of_coverage"],
            "allowed_weak_layers": [
                "none",
                "workflow",
                "router",
                "skill",
                "tool",
                "policy",
                "docs",
                "test_coverage",
                "prompt_governance",
                "runtime_proof",
            ],
            "allowed_required_verification_gates": [
                "static_registry",
                "live_gateway_anythingllm",
                "prompt_governance_update",
                "workflow_repair",
                "new_skill_tool_proposal",
                "unsupported_scope_backlog",
            ],
            "required_probe_decisions": ["in_coverage", "holdout", "partial_drift", "out_of_coverage"],
            "required_report_fields": [
                "prompt_id",
                "prompt_text",
                "prompt_family",
                "decision",
                "confidence",
                "expected_intent",
                "matched_workflow",
                "matched_skill",
                "matched_router_path",
                "missing_or_weak_layer",
                "evidence_artifacts_checked",
                "reasoning_summary",
                "required_verification_gate",
                "recommended_next_action",
                "coverage_version_or_commit",
                "timestamp",
            ],
        },
        "drift_probe_cases": [
            {
                "prompt_id": "PFDD-T1",
                "prompt_text": "Explain a function.",
                "prompt_family": "L1-code-explanation",
                "expected_decision": "in_coverage",
                "confidence": "high",
                "expected_intent": "explain function",
                "expected_workflow": "code_investigation.plan",
                "expected_route_rule": "l1_explain_code_terms",
                "matched_coverage_entry_ids": ["L1-002"],
                "missing_or_weak_layer": ["none"],
                "required_verification_gate": "live_gateway_anythingllm",
                "recommended_next_action": "keep in regression",
            },
            {
                "prompt_id": "PFDD-T2",
                "prompt_text": "Holdout trace.",
                "prompt_family": "L2-request-flow-map",
                "expected_decision": "holdout",
                "confidence": "high",
                "expected_intent": "holdout request flow",
                "expected_workflow": "code_investigation.plan",
                "expected_route_rule": "l1_explain_code_terms",
                "matched_coverage_entry_ids": ["L1-002"],
                "missing_or_weak_layer": ["none"],
                "required_verification_gate": "live_gateway_anythingllm",
                "recommended_next_action": "keep as holdout",
            },
            {
                "prompt_id": "PFDD-T3",
                "prompt_text": "Generate new prompt families.",
                "prompt_family": "prompt-corpus-expansion",
                "expected_decision": "partial_drift",
                "confidence": "medium",
                "expected_intent": "expand prompt corpus",
                "expected_workflow": "",
                "expected_route_rule": "",
                "matched_coverage_entry_ids": [],
                "missing_or_weak_layer": ["skill", "test_coverage"],
                "required_verification_gate": "new_skill_tool_proposal",
                "recommended_next_action": "write proposal",
            },
            {
                "prompt_id": "PFDD-T4",
                "prompt_text": "Review startup pricing.",
                "prompt_family": "business-critique",
                "expected_decision": "out_of_coverage",
                "confidence": "high",
                "expected_intent": "business critique",
                "expected_workflow": "",
                "expected_route_rule": "",
                "matched_coverage_entry_ids": [],
                "missing_or_weak_layer": ["workflow", "skill"],
                "required_verification_gate": "unsupported_scope_backlog",
                "recommended_next_action": "keep unsupported",
            },
        ],
    }


def synthetic_sources(tmp_path: Path) -> tuple[dict, dict[str, dict], dict[str, Path]]:
    docs = write_json(tmp_path / "docs" / "example.json", {"ok": True})
    policy = synthetic_policy()
    catalog = {
        "kind": "prompt_catalog",
        "cases": [
            {
                "case_id": "P01",
                "prompt": "Explain the function.",
                "baseline_target": "function explanation",
                "expected_rule": "l1_explain_code_terms",
                "expected_workflow": "code_investigation.plan",
                "target_root": "/tmp/repo",
            },
            {
                "case_id": "P02",
                "prompt": "Explain the same function as holdout.",
                "baseline_target": "function explanation holdout",
                "expected_rule": "l1_explain_code_terms",
                "expected_workflow": "code_investigation.plan",
                "target_root": "/tmp/repo",
            },
        ],
    }
    coverage = {
        "kind": "prompt_skill_coverage_registry",
        "entries": [
            {
                "id": "L1-002",
                "prompt_family": "L1-code-explanation",
                "status": "implemented",
                "selected_workflow": "code_investigation.plan",
                "route_rule": "l1_explain_code_terms",
                "skill_ids": ["code-explanation-summarizer"],
                "tool_ids": ["read_file"],
                "validation_suites": ["workflow_router_l1_suite"],
                "docs_examples": [str(docs.relative_to(tmp_path))],
            }
        ],
    }
    governance = {
        "kind": "prompt_corpus_governance_v2_policy",
        "roles": {
            "target": ["P01"],
            "holdout": ["P02"],
            "regression": ["P01", "P02"],
            "promotion_candidate": [],
            "retired": [],
        },
        "target_holdout_links": [
            {
                "family": "family_a",
                "target_case_id": "P01",
                "holdout_case_ids": ["P02"],
            }
        ],
    }
    holdouts = {"kind": "priority0_holdout_prompt_bank", "entries": []}
    pack = {"kind": "founder_test_prompt_pack", "tiers": [{"tier": "smoke", "case_ids": ["P01"]}]}
    sources = {
        "catalog": catalog,
        "skill_coverage": coverage,
        "corpus_governance": governance,
        "holdout_bank": holdouts,
        "prompt_pack": pack,
    }
    paths = {
        "policy": write_json(tmp_path / "policy.json", policy),
        "catalog": write_json(tmp_path / "catalog.json", catalog),
        "skill_coverage": write_json(tmp_path / "coverage.json", coverage),
        "corpus_governance": write_json(tmp_path / "governance.json", governance),
        "holdout_bank": write_json(tmp_path / "holdouts.json", holdouts),
        "prompt_pack": write_json(tmp_path / "pack.json", pack),
    }
    return policy, sources, paths


def test_prompt_family_drift_detection_policy_passes_synthetic_sources(tmp_path: Path) -> None:
    policy, sources, paths = synthetic_sources(tmp_path)

    errors = validate_sources(
        config_root=tmp_path,
        policy=policy,
        sources=sources,
        paths={key: value for key, value in paths.items() if key != "policy"},
    )

    assert errors == []


def test_prompt_family_drift_detection_report_classifies_catalog_and_probes(tmp_path: Path) -> None:
    policy, sources, paths = synthetic_sources(tmp_path)

    report = build_prompt_family_drift_detection_report(
        config_root=tmp_path,
        policy=policy,
        sources=sources,
        paths={key: value for key, value in paths.items() if key != "policy"},
        policy_path=paths["policy"],
    )

    assert report["status"] == "passed"
    assert report["summary"]["catalog_case_count"] == 2
    assert report["summary"]["probe_case_count"] == 4
    assert report["summary"]["decision_counts"]["in_coverage"] == 2
    assert report["summary"]["decision_counts"]["holdout"] == 2
    assert report["summary"]["decision_counts"]["partial_drift"] == 1
    assert report["summary"]["decision_counts"]["out_of_coverage"] == 1
    assert report["summary"]["decision_counts_by_source"]["catalog"] == {"holdout": 1, "in_coverage": 1}
    assert report["summary"]["decision_counts_by_source"]["drift_probe"] == {
        "holdout": 1,
        "in_coverage": 1,
        "out_of_coverage": 1,
        "partial_drift": 1,
    }
    assert report["summary"]["active_catalog_blocking_drift_count"] == 0
    p02 = next(record for record in report["records"] if record["prompt_id"] == "P02")
    assert p02["holdout_for_families"] == ["family_a"]
    assert p02["holdout_independence_status"] == "independent_holdout"


def test_prompt_family_drift_detection_labels_cross_family_dual_role_holdout(tmp_path: Path) -> None:
    policy, sources, paths = synthetic_sources(tmp_path)
    policy["expected_corpus_role_counts"]["target"] = 2
    policy["expected_corpus_role_counts"]["holdout"] = 2
    policy["expected_corpus_role_counts"]["promotion_candidate"] = 1
    sources["corpus_governance"]["roles"]["target"].append("P02")
    sources["corpus_governance"]["roles"]["holdout"].append("P01")
    sources["corpus_governance"]["roles"]["promotion_candidate"].append("P02")
    sources["corpus_governance"]["target_holdout_links"].append(
        {
            "family": "family_b",
            "target_case_id": "P02",
            "holdout_case_ids": ["P01"],
        }
    )

    report = build_prompt_family_drift_detection_report(
        config_root=tmp_path,
        policy=policy,
        sources=sources,
        paths={key: value for key, value in paths.items() if key != "policy"},
        policy_path=paths["policy"],
    )

    p02 = next(record for record in report["records"] if record["prompt_id"] == "P02")
    assert report["status"] == "passed"
    assert p02["decision"] == "holdout"
    assert p02["target_for_families"] == ["family_b"]
    assert p02["holdout_for_families"] == ["family_a"]
    assert p02["holdout_independence_status"] == "cross_family_dual_role_allowed"
    assert "different governed family" in p02["reasoning_summary"]


def test_prompt_family_drift_detection_rejects_same_family_target_holdout_overlap(tmp_path: Path) -> None:
    policy, sources, paths = synthetic_sources(tmp_path)
    policy["expected_corpus_role_counts"]["target"] = 2
    sources["corpus_governance"]["roles"]["target"].append("P02")
    sources["corpus_governance"]["target_holdout_links"].append(
        {
            "family": "family_a",
            "target_case_id": "P02",
            "holdout_case_ids": ["P01"],
        }
    )

    report = build_prompt_family_drift_detection_report(
        config_root=tmp_path,
        policy=policy,
        sources=sources,
        paths={key: value for key, value in paths.items() if key != "policy"},
        policy_path=paths["policy"],
    )

    p02 = next(record for record in report["records"] if record["prompt_id"] == "P02")
    assert report["status"] == "failed"
    assert p02["decision"] == "partial_drift"
    assert p02["holdout_independence_status"] == "invalid_same_family_overlap"
    assert any(error["id"] == "records.active_catalog_blocking_drift" for error in report["validation_errors"])


def test_prompt_family_drift_detection_rejects_missing_probe_decision(tmp_path: Path) -> None:
    policy, _, _ = synthetic_sources(tmp_path)
    policy["drift_probe_cases"] = [case for case in policy["drift_probe_cases"] if case["expected_decision"] != "out_of_coverage"]

    errors = validate_policy(policy)

    assert any(error["id"] == "drift_probe_cases.required_decisions" for error in errors)


def test_prompt_family_drift_detection_rejects_partial_drift_without_weak_layer(tmp_path: Path) -> None:
    policy, _, _ = synthetic_sources(tmp_path)
    policy["drift_probe_cases"][2]["missing_or_weak_layer"] = ["none"]

    errors = validate_policy(policy)

    assert any(error["id"].endswith(".missing_or_weak_layer") for error in errors)


def test_prompt_family_drift_detection_rejects_catalog_case_without_coverage(tmp_path: Path) -> None:
    policy, sources, paths = synthetic_sources(tmp_path)
    sources["catalog"]["cases"][1]["expected_rule"] = "missing_route_rule"

    report = build_prompt_family_drift_detection_report(
        config_root=tmp_path,
        policy=policy,
        sources=sources,
        paths={key: value for key, value in paths.items() if key != "policy"},
        policy_path=paths["policy"],
    )

    assert report["status"] == "failed"
    assert report["summary"]["active_catalog_blocking_drift_count"] == 1
    assert any(error["id"] == "records.active_catalog_blocking_drift" for error in report["validation_errors"])


def test_prompt_family_drift_detection_rejects_stale_report(tmp_path: Path) -> None:
    policy, sources, paths = synthetic_sources(tmp_path)
    report = build_prompt_family_drift_detection_report(
        config_root=tmp_path,
        policy=policy,
        sources=sources,
        paths={key: value for key, value in paths.items() if key != "policy"},
        policy_path=paths["policy"],
    )
    report["summary"]["decision_counts"]["in_coverage"] = 999

    errors = validate_prompt_family_drift_detection_report(
        report,
        config_root=tmp_path,
        policy=policy,
        sources=sources,
        paths={key: value for key, value in paths.items() if key != "policy"},
        policy_path=paths["policy"],
    )

    assert errors == ["report must match rebuilt prompt-family drift detection report"]


def test_run_prompt_family_drift_detection_writes_json_and_markdown(tmp_path: Path) -> None:
    synthetic_sources(tmp_path)

    report = run_prompt_family_drift_detection(
        PromptFamilyDriftDetectionConfig(
            config_root=tmp_path,
            policy_path=Path("policy.json"),
            output_path=Path("out/report.json"),
            markdown_output_path=Path("out/report.md"),
        )
    )
    persisted = json.loads((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))

    assert report["status"] == "passed"
    assert persisted["report_path"] == str((tmp_path / "out" / "report.json").resolve())
    markdown = (tmp_path / "out" / "report.md").read_text(encoding="utf-8")
    assert markdown.startswith("# Prompt Family Drift Detection")
    assert "## Catalog Coverage" in markdown
    assert "target_for=" in markdown
    assert "holdout_for=" in markdown
