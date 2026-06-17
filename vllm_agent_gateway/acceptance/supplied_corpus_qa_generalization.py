"""Phase 280 supplied-corpus QA generalization validation."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.large_context_500k_candidate_rebaseline import (
    sha256_file,
    validation_error,
    write_json,
    write_text,
)
from vllm_agent_gateway.acceptance.skill_selection_hardening import (
    DEFAULT_ANYTHINGLLM_API_BASE_URL,
    DEFAULT_MODEL_BASE_URL,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    DEFAULT_WORKSPACE,
    json_request,
    text_response,
)
from vllm_agent_gateway.controller_service.server import ControllerServiceConfig, handle_workflow_router_chat_completion
from vllm_agent_gateway.controllers.supplied_corpus_qa import answer_supplied_corpus_qa
from vllm_agent_gateway.controllers.workflow_router.plan import SUPPLIED_CORPUS_QA_STATUS


SCHEMA_VERSION = 1
EXPECTED_REPORT_KIND = "supplied_corpus_qa_generalization_report"
EXPECTED_PHASE = 280
EXPECTED_BACKLOG_ID = "P0-M6-280"
EXPECTED_MILESTONE_IDS = ("M2", "M4", "M6", "M8", "M13", "M15", "M16")
DEFAULT_OUTPUT_PATH = Path("runtime-state") / "phase280" / "phase280-supplied-corpus-qa-generalization-report.json"
DEFAULT_MARKDOWN_OUTPUT_PATH = Path("runtime-state") / "phase280" / "phase280-supplied-corpus-qa-generalization-report.md"
DEFAULT_ARTIFACT_DIR = Path("runtime-state") / "phase280" / "supplied-corpus-qa-generalization"


PHASE280_CASES: tuple[dict[str, Any], ...] = (
    {
        "id": "precedence_date",
        "failure_mode": "precedence/superseded facts",
        "corpus": """
SECTION 01 -- DELIVERY BASELINE
Initial deployment date: July 1, 2027.

SECTION 02 -- CHANGE LOG
Change Request CR-9 moved the deployment date from July 1, 2027 to August 12, 2027.
The August 12 date supersedes the earlier deployment date.
""",
        "questions": [
            "What is the correct deployment date?",
            "Identify any superseded facts that should not control the final answer.",
        ],
        "must_contain": ["August 12, 2027", "July 1, 2027", "superseded", "SECTION 02"],
        "must_not_contain": ["missing_target_root_for_coding_request"],
    },
    {
        "id": "boundary_stitching",
        "failure_mode": "boundary-stitching",
        "corpus": """
SECTION 01 -- CONTROL PART A
The operator override code is LIMESTONE-

SECTION 02 -- CONTROL PART B
42.
This code must be treated as a single contiguous value.
""",
        "questions": ["What is the operator override code?"],
        "must_contain": ["LIMESTONE-42", "SECTION 01", "SECTION 02"],
        "must_not_contain": ["LIMESTONE-\n", "missing_target_root_for_coding_request"],
    },
    {
        "id": "ordered_markers",
        "failure_mode": "ordered facts",
        "corpus": """
SECTION 01 -- FIRST MARKER
Sequence item: RIVER-01.

SECTION 02 -- SECOND MARKER
Sequence item: HARBOR-02.

SECTION 03 -- THIRD MARKER
Sequence item: SUMMIT-03.
""",
        "questions": ["List the sequence items in document order."],
        "must_contain": ["RIVER-01, HARBOR-02, SUMMIT-03", "document order"],
        "must_not_contain": ["HARBOR-02, RIVER-01", "missing_target_root_for_coding_request"],
    },
    {
        "id": "cost_calculation",
        "failure_mode": "cost or numeric calculation",
        "corpus": """
SECTION 01 -- COST MODEL
The rollout has 40 seats.
The vendor charges $75 per seat per month.
The contract term is 12 months.
There is also a one-time setup fee of $5,000.

SECTION 02 -- APPROVAL LIMIT
The approved budget ceiling is $50,000.
Any total projected cost above that amount requires finance approval.
""",
        "questions": ["What is the total projected contract cost, and is approval required?"],
        "must_contain": ["40 x $75/month x 12 months = $36,000", "$5,000", "$41,000", "approval is not required"],
        "must_not_contain": ["$45,000", "approval is required because $41,000 is above", "missing_target_root_for_coding_request"],
    },
    {
        "id": "contradiction_blocker",
        "failure_mode": "contradiction handling",
        "corpus": """
SECTION 01 -- REGION BASELINE
Initial rollout regions: Alpha, Beta, Gamma.

SECTION 02 -- REGULATORY HOLD
Beta rollout is blocked until the permit is signed.

SECTION 03 -- FINAL REVIEW
As of final review, Beta permit has not been signed.
""",
        "questions": [
            "Which regions may proceed?",
            "Is Beta rollout allowed?",
        ],
        "must_contain": ["Alpha and Gamma", "Beta may not proceed", "Beta rollout is not allowed", "not been signed"],
        "must_not_contain": ["Alpha and Beta and Gamma", "Beta rollout is allowed", "missing_target_root_for_coding_request"],
    },
)


@dataclass(frozen=True)
class SuppliedCorpusQaGeneralizationConfig:
    config_root: Path
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path = DEFAULT_MARKDOWN_OUTPUT_PATH
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR
    include_direct_engine: bool = True
    include_direct_router: bool = True
    include_live_gateway: bool = False
    include_anythingllm: bool = False
    workflow_router_gateway_base_url: str = DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL
    model_base_url: str = DEFAULT_MODEL_BASE_URL
    anythingllm_api_base_url: str = DEFAULT_ANYTHINGLLM_API_BASE_URL
    workspace: str = DEFAULT_WORKSPACE
    api_key_env: str = "ANYTHINGLLM_API_KEY"
    timeout_seconds: int = 1200


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def resolve_path(config_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_root / path


def prompt_for_case(case: dict[str, Any]) -> str:
    question_lines = ["Based only on the supplied corpus, answer the following:", ""]
    question_lines.extend(f"{index}. {question}" for index, question in enumerate(case["questions"], start=1))
    return str(case["corpus"]).strip() + "\n\n" + "\n".join(question_lines) + "\n"


def score_case_answer(case: dict[str, Any], answer: str) -> dict[str, Any]:
    missing = [marker for marker in case["must_contain"] if str(marker) not in answer]
    forbidden = [marker for marker in case["must_not_contain"] if str(marker) in answer]
    passed = not missing and not forbidden
    return {
        "case_id": case["id"],
        "failure_mode": case["failure_mode"],
        "status": "passed" if passed else "failed",
        "missing_markers": missing,
        "forbidden_markers": forbidden,
        "answer_sha256": sha256_text(answer),
    }


def sha256_text(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def direct_engine_result(case: dict[str, Any], answer_dir: Path) -> dict[str, Any]:
    prompt = prompt_for_case(case)
    answer, extraction = answer_supplied_corpus_qa(prompt)
    answer_path = answer_dir / f"{case['id']}-direct-engine-answer.txt"
    extraction_path = answer_dir / f"{case['id']}-direct-engine-extraction.json"
    write_text(answer_path, answer)
    write_json(extraction_path, extraction)
    return {
        "surface": "direct_engine",
        "case_id": case["id"],
        "http_status": None,
        "route_status": extraction.get("extraction_status"),
        "answer_path": str(answer_path.resolve()),
        "extraction_path": str(extraction_path.resolve()),
        "score": score_case_answer(case, answer),
    }


def direct_router_result(case: dict[str, Any], config_root: Path, answer_dir: Path) -> dict[str, Any]:
    prompt = prompt_for_case(case)
    output_root = answer_dir / "direct-router-output"
    target_root = output_root / "allowed-placeholder"
    target_root.mkdir(parents=True, exist_ok=True)
    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=output_root,
        allowed_target_roots=(target_root,),
        port=0,
    )
    body = handle_workflow_router_chat_completion(
        {
            "model": "agentic-workflow-router",
            "messages": [{"role": "user", "content": prompt}],
            "budgets": {"max_model_calls": 0, "max_selected_skills": 5, "max_selected_tools": 5},
        },
        config,
    )
    answer = text_response(body)
    answer_path = answer_dir / f"{case['id']}-direct-router-answer.txt"
    write_text(answer_path, answer)
    summary = body.get("agentic_controller_response", {}).get("summary", {})
    artifacts = body.get("agentic_controller_response", {}).get("artifacts", {})
    return {
        "surface": "direct_router",
        "case_id": case["id"],
        "http_status": 200,
        "route_status": summary.get("route_status"),
        "selected_workflow": summary.get("selected_workflow"),
        "answer_path": str(answer_path.resolve()),
        "artifacts": artifacts,
        "score": score_case_answer(case, answer),
    }


def live_gateway_result(case: dict[str, Any], config: SuppliedCorpusQaGeneralizationConfig, answer_dir: Path) -> dict[str, Any]:
    payload = {
        "model": "agentic-workflow-router",
        "messages": [{"role": "user", "content": prompt_for_case(case)}],
        "role_base_url": config.model_base_url,
        "budgets": {"max_model_calls": 3, "max_selected_skills": 5, "max_selected_tools": 5},
    }
    status, body = json_request(
        f"{config.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload=payload,
        timeout_seconds=config.timeout_seconds,
    )
    try:
        answer = text_response(body)
    except RuntimeError:
        answer = json.dumps(body, ensure_ascii=True, sort_keys=True)
    answer_path = answer_dir / f"{case['id']}-live-gateway-answer.txt"
    write_text(answer_path, answer)
    summary = body.get("agentic_controller_response", {}).get("summary", {}) if isinstance(body, dict) else {}
    return {
        "surface": "live_gateway",
        "case_id": case["id"],
        "http_status": status,
        "route_status": summary.get("route_status"),
        "selected_workflow": summary.get("selected_workflow"),
        "answer_path": str(answer_path.resolve()),
        "body_sha256": sha256_text(json.dumps(body, ensure_ascii=True, sort_keys=True)),
        "score": score_case_answer(case, answer),
    }


def anythingllm_result(
    case: dict[str, Any],
    config: SuppliedCorpusQaGeneralizationConfig,
    api_key: str,
    answer_dir: Path,
) -> dict[str, Any]:
    payload = {
        "message": prompt_for_case(case),
        "mode": "chat",
        "sessionId": f"phase280-{case['id']}-{uuid.uuid4().hex}",
    }
    status, body = json_request(
        f"{config.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{config.workspace}/chat",
        payload=payload,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=config.timeout_seconds,
    )
    try:
        answer = text_response(body)
    except RuntimeError:
        answer = json.dumps(body, ensure_ascii=True, sort_keys=True)
    answer_path = answer_dir / f"{case['id']}-anythingllm-answer.txt"
    write_text(answer_path, answer)
    return {
        "surface": "anythingllm",
        "case_id": case["id"],
        "http_status": status,
        "answer_path": str(answer_path.resolve()),
        "body_sha256": sha256_text(json.dumps(body, ensure_ascii=True, sort_keys=True)),
        "score": score_case_answer(case, answer),
    }


def no_target_coding_guard(config_root: Path, artifact_dir: Path) -> dict[str, Any]:
    output_root = artifact_dir / "no-target-output"
    target_root = output_root / "allowed-placeholder"
    target_root.mkdir(parents=True, exist_ok=True)
    config = ControllerServiceConfig(
        config_root=config_root,
        output_root=output_root,
        allowed_target_roots=(target_root,),
        port=0,
    )
    body = handle_workflow_router_chat_completion(
        {
            "model": "agentic-workflow-router",
            "messages": [{"role": "user", "content": "Explain where the order lookup starts and how to test it. Read only."}],
            "budgets": {"max_model_calls": 0, "max_selected_skills": 5, "max_selected_tools": 5},
        },
        config,
    )
    answer = text_response(body)
    summary = body.get("agentic_controller_response", {}).get("summary", {})
    answer_path = artifact_dir / "no-target-coding-guard-answer.txt"
    write_text(answer_path, answer)
    guard_passed = summary.get("route_status") == "missing_target_root_for_coding_request" or "missing_target_root_for_coding_request" in answer
    return {
        "status": "passed" if guard_passed else "failed",
        "route_status": summary.get("route_status"),
        "answer_path": str(answer_path.resolve()),
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Supplied Corpus QA Generalization",
        "",
        f"- Status: `{report['status']}`",
        f"- Case count: `{summary['case_count']}`",
        f"- Failed result count: `{summary['failed_result_count']}`",
        f"- Direct engine: `{summary['direct_engine_status']}`",
        f"- Direct router: `{summary['direct_router_status']}`",
        f"- Live gateway: `{summary['live_gateway_status']}`",
        f"- AnythingLLM: `{summary['anythingllm_status']}`",
        f"- Coding guard: `{summary['no_target_coding_guard_status']}`",
        "",
        "## Results",
    ]
    for result in report["results"]:
        score = result["score"]
        lines.append(f"- `{result['surface']}` `{result['case_id']}`: `{score['status']}`")
    if report["errors"]:
        lines.extend(["", "## Errors"])
        lines.extend(f"- `{item['id']}`: {item['message']}" for item in report["errors"])
    return "\n".join(lines) + "\n"


def validate_supplied_corpus_qa_generalization(config: SuppliedCorpusQaGeneralizationConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    output_path = resolve_path(config_root, config.output_path)
    markdown_output_path = resolve_path(config_root, config.markdown_output_path)
    artifact_dir = resolve_path(config_root, config.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for case in PHASE280_CASES:
        if config.include_direct_engine:
            results.append(direct_engine_result(case, artifact_dir))
        if config.include_direct_router:
            results.append(direct_router_result(case, config_root, artifact_dir))
        if config.include_live_gateway:
            results.append(live_gateway_result(case, config, artifact_dir))
        if config.include_anythingllm:
            api_key = os.environ.get(config.api_key_env, "")
            if not api_key:
                errors.append(
                    validation_error(
                        "anythingllm.api_key",
                        f"{config.api_key_env} is required for AnythingLLM validation",
                        source="anythingllm",
                        severity="critical",
                    )
                )
            else:
                results.append(anythingllm_result(case, config, api_key, artifact_dir))

    coding_guard = no_target_coding_guard(config_root, artifact_dir)
    if coding_guard["status"] != "passed":
        errors.append(
            validation_error(
                "coding_guard.missing_target_root",
                "normal coding prompt without target_root did not return missing-target guidance",
                source="controller",
                severity="critical",
            )
        )

    for result in results:
        score = result["score"]
        if score["status"] != "passed":
            errors.append(
                validation_error(
                    f"{result['surface']}.{result['case_id']}.score",
                    f"{result['surface']} answer failed markers for {result['case_id']}",
                    source=result["surface"],
                    severity="critical",
                )
            )
        if result["surface"] in {"direct_router", "live_gateway"} and result.get("route_status") != SUPPLIED_CORPUS_QA_STATUS:
            errors.append(
                validation_error(
                    f"{result['surface']}.{result['case_id']}.route_status",
                    f"{result['surface']} did not use supplied-corpus QA route for {result['case_id']}",
                    source=result["surface"],
                    severity="critical",
                )
            )
        if result.get("http_status") not in {None, 200}:
            errors.append(
                validation_error(
                    f"{result['surface']}.{result['case_id']}.http_status",
                    f"{result['surface']} returned HTTP {result.get('http_status')}",
                    source=result["surface"],
                    severity="critical",
                )
            )

    def status_for(surface: str) -> str:
        surface_results = [item for item in results if item["surface"] == surface]
        if not surface_results:
            return "not_run"
        return "passed" if all(item["score"]["status"] == "passed" for item in surface_results) else "failed"

    status = "passed" if not errors else "failed"
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_ids": list(EXPECTED_MILESTONE_IDS),
        "generated_at": utc_timestamp(),
        "status": status,
        "case_ids": [case["id"] for case in PHASE280_CASES],
        "failure_modes": [case["failure_mode"] for case in PHASE280_CASES],
        "artifact_dir": str(artifact_dir.resolve()),
        "live_config": {
            "workflow_router_gateway_base_url": config.workflow_router_gateway_base_url,
            "model_base_url": config.model_base_url,
            "anythingllm_api_base_url": config.anythingllm_api_base_url,
            "workspace": config.workspace,
            "include_live_gateway": config.include_live_gateway,
            "include_anythingllm": config.include_anythingllm,
        },
        "results": results,
        "no_target_coding_guard": coding_guard,
        "errors": errors,
        "summary": {
            "case_count": len(PHASE280_CASES),
            "result_count": len(results),
            "failed_result_count": len([item for item in results if item["score"]["status"] != "passed"]),
            "direct_engine_status": status_for("direct_engine"),
            "direct_router_status": status_for("direct_router"),
            "live_gateway_status": status_for("live_gateway"),
            "anythingllm_status": status_for("anythingllm"),
            "no_target_coding_guard_status": coding_guard["status"],
            "phase280_ready": status == "passed",
        },
    }
    write_json(output_path, report)
    write_text(markdown_output_path, render_markdown(report))
    return report
