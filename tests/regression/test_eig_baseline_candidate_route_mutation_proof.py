from __future__ import annotations

import copy
import json
from pathlib import Path

from vllm_agent_gateway.acceptance.eig_baseline_candidate_route_mutation_proof import (
    EIGBaselineCandidateRouteMutationProofConfig,
    run_eig_baseline_candidate_route_mutation_proof,
    validate_policy,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "runtime" / "eig_baseline_candidate_route_mutation_proof_policy.json"


def load_policy() -> dict:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    return path


def connector_report(path: Path) -> Path:
    return write_json(
        path,
        {
            "kind": "eig_runtime_breadth_chat_report",
            "status": "passed",
            "summary": {
                "case_count": 3,
                "passed_case_count": 3,
                "failed_case_count": 0,
                "source_connector_registry_changed": False,
            },
            "case_results": [
                {"case_id": "EIG-RUNTIME-WORK-LOOKUP", "status": "passed", "workflow": "connector.invoke", "run_id": "r1", "errors": []},
                {"case_id": "EIG-RUNTIME-RECORD-LOOKUP", "status": "passed", "workflow": "connector.invoke", "run_id": "r2", "errors": []},
                {"case_id": "EIG-RUNTIME-KNOWLEDGE-SEARCH", "status": "passed", "workflow": "connector.invoke", "run_id": "r3", "errors": []},
            ],
        },
    )


def privacy_report(path: Path) -> Path:
    case_ids = [
        "EIG3-RUNTIME-SEC-REFUSE",
        "EIG3-RUNTIME-PII-AUTH",
        "EIG3-RUNTIME-BIZ-JSON",
        "EIG3-RUNTIME-MEMORY",
    ]
    return write_json(
        path,
        {
            "kind": "eig3_privacy_runtime_chat_report",
            "status": "passed",
            "summary": {
                "result_count": 8,
                "surface_count": 2,
                "surfaces": ["anythingllm", "workflow_router_gateway"],
                "raw_source_content_retained_in_report": False,
            },
            "case_results": [
                {
                    "case_id": case_id,
                    "surface": surface,
                    "status": "passed",
                    "selected_workflow": "none",
                    "route_status": "eig3_privacy_policy_no_target",
                    "finding_count": 0,
                    "findings": [],
                }
                for case_id in case_ids
                for surface in ("workflow_router_gateway", "anythingllm")
            ],
        },
    )


def live_report(tmp_path: Path) -> Path:
    connector_gateway = connector_report(tmp_path / "connector-gateway.json")
    connector_anythingllm = connector_report(tmp_path / "connector-anythingllm.json")
    privacy = privacy_report(tmp_path / "privacy.json")
    return write_json(
        tmp_path / "live.json",
        {
            "kind": "eig_baseline_candidate_live_replay_report",
            "status": "passed",
            "baseline_corpus": {"status": "passed"},
            "summary": {
                "candidate_count": 2,
                "covered_surface_count": 2,
                "live_result_count": 14,
                "missing_surface_count": 0,
                "stable_corpus_mutated": False,
                "stable_corpus_promotion_allowed": False,
            },
            "child_reports": {
                "connector_gateway": {"report_path": str(connector_gateway)},
                "connector_anythingllm": {"report_path": str(connector_anythingllm)},
                "privacy_runtime": {"report_path": str(privacy)},
            },
        },
    )


def test_route_mutation_proof_policy_passes() -> None:
    assert validate_policy(load_policy()) == []


def test_route_mutation_proof_passes_synthetic_report(tmp_path: Path) -> None:
    report = run_eig_baseline_candidate_route_mutation_proof(
        EIGBaselineCandidateRouteMutationProofConfig(
            config_root=REPO_ROOT,
            live_replay_report_path=live_report(tmp_path),
            output_path=tmp_path / "proof.json",
        )
    )

    assert report["status"] == "passed"
    assert report["summary"]["route_proof_recorded"] is True
    assert report["summary"]["no_mutation_proof_recorded"] is True
    assert report["summary"]["recorded_evidence"] == ["route_proof", "no_mutation_proof"]
    assert report["summary"]["remaining_missing_evidence"] == ["founder_approval", "holdout"]


def test_route_mutation_proof_rejects_wrong_connector_route(tmp_path: Path) -> None:
    live_path = live_report(tmp_path)
    connector_path = tmp_path / "connector-gateway.json"
    connector = json.loads(connector_path.read_text(encoding="utf-8"))
    connector["case_results"][0]["workflow"] = "raw_tool.invoke"
    write_json(connector_path, connector)

    report = run_eig_baseline_candidate_route_mutation_proof(
        EIGBaselineCandidateRouteMutationProofConfig(
            config_root=REPO_ROOT,
            live_replay_report_path=live_path,
            output_path=tmp_path / "proof.json",
        )
    )

    assert report["status"] == "failed"
    assert any("workflow must be connector.invoke" in error for error in report["validation_errors"])


def test_route_mutation_proof_rejects_stable_corpus_mutation(tmp_path: Path) -> None:
    live_path = live_report(tmp_path)
    live = json.loads(live_path.read_text(encoding="utf-8"))
    live["summary"]["stable_corpus_mutated"] = True
    write_json(live_path, live)

    report = run_eig_baseline_candidate_route_mutation_proof(
        EIGBaselineCandidateRouteMutationProofConfig(
            config_root=REPO_ROOT,
            live_replay_report_path=live_path,
            output_path=tmp_path / "proof.json",
        )
    )

    assert report["status"] == "failed"
    assert any("stable_corpus_mutated must be false" in error for error in report["validation_errors"])


def test_route_mutation_proof_rejects_policy_drift() -> None:
    policy = copy.deepcopy(load_policy())
    policy["stable_corpus_promotion_allowed"] = True

    errors = validate_policy(policy)

    assert any("stable_corpus_promotion_allowed must be false" in error for error in errors)
