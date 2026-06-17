"""Phase 278 adversarial context-stitching validation fixture."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vllm_agent_gateway.acceptance.large_context_500k_candidate_rebaseline import (
    dict_value,
    object_list,
    read_json_object,
    sha256_file,
    string_list,
    validation_error,
    write_json,
    write_text,
)
from vllm_agent_gateway.acceptance.skill_selection_hardening import (
    DEFAULT_MODEL_BASE_URL,
    DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL,
    json_request,
    text_response,
)


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "adversarial_context_stitching_policy"
EXPECTED_REPORT_KIND = "adversarial_context_stitching_report"
EXPECTED_PHASE = 278
EXPECTED_BACKLOG_ID = "P0-M6-278"
EXPECTED_MILESTONE_IDS = {"M2", "M4", "M6", "M8", "M15", "M16"}
EXPECTED_CORPUS_ID = "meridian_gate_adversarial_context_stitching_v1"
EXPECTED_MODES = {"standard", "zero_overlap", "randomized_retrieval_order"}
REQUIRED_HARD_FAILURE_OUTCOMES = {
    "launch_date",
    "regions",
    "eu_rollout",
    "payments_api",
    "contract_cost",
    "kill_switch",
    "sentinel_order",
    "obsolete_facts",
}
DEFAULT_POLICY_PATH = Path("runtime") / "adversarial_context_stitching_policy.json"
DEFAULT_OUTPUT_PATH = (
    Path("runtime-state")
    / "phase278"
    / "phase278-adversarial-context-stitching-report.json"
)
DEFAULT_MARKDOWN_OUTPUT_PATH = (
    Path("runtime-state")
    / "phase278"
    / "phase278-adversarial-context-stitching-report.md"
)
DEFAULT_FIXTURE_DIR = Path("runtime-state") / "phase278" / "fixture"
SENTINELS = ("ALPHA-19", "BRAVO-27", "CHARLIE-08", "DELTA-66")


class AdversarialContextStitchingStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class FixtureMode(str, Enum):
    STANDARD = "standard"
    ZERO_OVERLAP = "zero_overlap"
    RANDOMIZED_RETRIEVAL_ORDER = "randomized_retrieval_order"


@dataclass(frozen=True)
class AdversarialContextStitchingConfig:
    config_root: Path
    policy_path: Path = DEFAULT_POLICY_PATH
    output_path: Path = DEFAULT_OUTPUT_PATH
    markdown_output_path: Path = DEFAULT_MARKDOWN_OUTPUT_PATH
    fixture_dir: Path = DEFAULT_FIXTURE_DIR
    answer_file: Path | None = None
    live_gateway: bool = False
    workflow_router_gateway_base_url: str = DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL
    model_base_url: str = DEFAULT_MODEL_BASE_URL
    timeout_seconds: int = 1200


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def resolve_path(config_root: Path, value: str | Path) -> Path:
    text = str(value)
    if os.name == "nt" and len(text) > 7 and text.startswith("/mnt/") and text[5].isalpha() and text[6] == "/":
        return Path(f"{text[5].upper()}:/{text[7:]}")
    path = Path(value)
    return path if path.is_absolute() else config_root / path


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def token_count(value: str) -> int:
    return len(re.findall(r"\S+", value))


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def number_tokens(value: str) -> set[int]:
    numbers: set[int] = set()
    for match in re.finditer(r"\$?\b\d[\d,]*\b", value):
        try:
            numbers.add(int(match.group(0).replace("$", "").replace(",", "")))
        except ValueError:
            continue
    return numbers


def policy_modes(policy: dict[str, Any]) -> set[str]:
    return set(string_list(policy.get("fixture_modes")))


def validate_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append(validation_error("policy.schema_version", "schema_version must be 1"))
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(validation_error("policy.kind", f"kind must be {EXPECTED_POLICY_KIND}"))
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append(validation_error("policy.phase", "phase must be 278"))
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(validation_error("policy.priority_backlog_id", f"priority_backlog_id must be {EXPECTED_BACKLOG_ID}"))
    if set(string_list(policy.get("milestone_ids"))) != EXPECTED_MILESTONE_IDS:
        errors.append(validation_error("policy.milestone_ids", "milestone_ids must be M2, M4, M6, M8, M15, and M16"))
    if policy.get("corpus_id") != EXPECTED_CORPUS_ID:
        errors.append(validation_error("policy.corpus_id", f"corpus_id must be {EXPECTED_CORPUS_ID}"))
    if policy_modes(policy) != EXPECTED_MODES:
        errors.append(validation_error("policy.fixture_modes", "standard, zero_overlap, and randomized_retrieval_order are required"))
    if set(string_list(policy.get("required_hard_failure_outcomes"))) != REQUIRED_HARD_FAILURE_OUTCOMES:
        errors.append(validation_error("policy.required_hard_failure_outcomes", "all eight hard-failure outcomes are required"))
    filler = dict_value(policy.get("filler"))
    if int(filler.get("minimum_token_count", 0)) < 2000:
        errors.append(validation_error("policy.filler.minimum_token_count", "minimum filler token count must be at least 2000"))
    if int(filler.get("standard_token_count", 0)) < int(filler.get("minimum_token_count", 0)):
        errors.append(validation_error("policy.filler.standard_token_count", "standard filler must be at least the minimum"))
    if int(filler.get("boundary_minimum_token_count", 0)) < int(filler.get("minimum_token_count", 0)):
        errors.append(validation_error("policy.filler.boundary_minimum_token_count", "boundary filler must be at least the minimum"))
    if int(filler.get("maximum_token_count", 0)) > 5000:
        errors.append(validation_error("policy.filler.maximum_token_count", "maximum filler token count must not exceed 5000"))
    if len(string_list(policy.get("required_docs"))) < 4:
        errors.append(validation_error("policy.required_docs", "required docs are missing"))
    if not dict_value(policy.get("required_doc_markers")):
        errors.append(validation_error("policy.required_doc_markers", "required_doc_markers is required"))
    if policy.get("acceptance_marker") != "PHASE278 ADVERSARIAL CONTEXT STITCHING PASS":
        errors.append(validation_error("policy.acceptance_marker", "acceptance marker must match Phase 278"))
    return errors


def docs_checks(config_root: Path, policy: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    results: list[dict[str, Any]] = []
    required_markers = dict_value(policy.get("required_doc_markers"))
    for raw_path in string_list(policy.get("required_docs")):
        path = resolve_path(config_root, raw_path)
        result: dict[str, Any] = {"path": raw_path, "exists": path.is_file(), "sha256": None, "missing_markers": []}
        if not path.is_file():
            errors.append(validation_error(f"docs.{raw_path}.missing", "required doc is missing", source="docs"))
            results.append(result)
            continue
        text = path.read_text(encoding="utf-8")
        result["sha256"] = sha256_file(path)
        missing = [marker for marker in string_list(required_markers.get(raw_path)) if marker not in text]
        result["missing_markers"] = missing
        for marker in missing:
            errors.append(validation_error(f"docs.{raw_path}.marker", f"required marker missing: {marker}", source="docs"))
        results.append(result)
    return results, errors


def corpus_sections() -> list[dict[str, str]]:
    return [
        {
            "id": "01",
            "title": "PROJECT BASELINE",
            "body": "\n".join(
                [
                    "Project Codename: Meridian Gate.",
                    "Initial launch date: November 15, 2026.",
                    "Initial rollout regions: United States, Canada, European Union.",
                    "Initial API requirement: Payments API v2.",
                    "Sentinel sequence item: ALPHA-19.",
                ]
            ),
        },
        {
            "id": "02",
            "title": "COST MODEL",
            "body": "\n".join(
                [
                    "The implementation has 90 licensed users.",
                    "The vendor charges $120 per user per month.",
                    "The contract term is 18 months.",
                    "There is also a one-time onboarding fee of $30,000.",
                ]
            ),
        },
        {
            "id": "03",
            "title": "SECURITY EXCEPTION",
            "body": "\n".join(
                [
                    "Payments API v2 is temporarily allowed for sandbox testing only.",
                    "Production use of Payments API v2 is prohibited after October 1, 2026.",
                    "Sentinel sequence item: BRAVO-27.",
                ]
            ),
        },
        {
            "id": "04",
            "title": "LEGAL REVIEW",
            "body": "\n".join(
                [
                    "The European Union rollout requires a signed Data Processing Addendum.",
                    "Without a signed DPA, EU rollout is blocked.",
                    "The Canadian rollout does not require this DPA.",
                ]
            ),
        },
        {
            "id": "05",
            "title": "BOUNDARY TEST PART A",
            "body": "The emergency kill-switch code is ORCHID-",
        },
        {
            "id": "06",
            "title": "BOUNDARY TEST PART B",
            "body": "\n".join(
                [
                    "17.",
                    "This code must be treated as a single contiguous value.",
                ]
            ),
        },
        {
            "id": "07",
            "title": "PROCUREMENT LIMIT",
            "body": "\n".join(
                [
                    "The approved budget ceiling is $240,000.",
                    "Any total projected cost above that amount requires CFO approval.",
                    "Sentinel sequence item: CHARLIE-08.",
                ]
            ),
        },
        {
            "id": "08",
            "title": "UPDATED TECHNICAL STANDARD",
            "body": "\n".join(
                [
                    "Payments API v3 is now mandatory for production.",
                    "Payments API v2 must not be used in production.",
                    "This supersedes all earlier technical guidance.",
                ]
            ),
        },
        {
            "id": "09",
            "title": "UPDATED LAUNCH DECISION",
            "body": "\n".join(
                [
                    "Change Request CR-44 moved the launch date from November 15, 2026 to December 3, 2026.",
                    "The December 3 date supersedes the earlier launch date.",
                ]
            ),
        },
        {
            "id": "10",
            "title": "DPA STATUS",
            "body": "\n".join(
                [
                    "As of the final review, the EU Data Processing Addendum has not been signed.",
                    "Therefore, the EU rollout remains blocked.",
                    "Sentinel sequence item: DELTA-66.",
                ]
            ),
        },
    ]


def filler_block(block_id: int, token_target: int) -> str:
    tokens = [f"filler{block_id:02d}_{index:04d}" for index in range(1, token_target + 1)]
    return " ".join(tokens)


def section_text(section: dict[str, str]) -> str:
    return f"SECTION {section['id']} -- {section['title']}\n{section['body']}"


def build_corpus(policy: dict[str, Any], mode: FixtureMode) -> dict[str, Any]:
    filler = dict_value(policy.get("filler"))
    standard_target = int(filler.get("standard_token_count", 2400))
    boundary_target = int(filler.get("boundary_minimum_token_count", 2600))
    sections = corpus_sections()
    parts: list[str] = []
    filler_reports: list[dict[str, Any]] = []
    for index, section in enumerate(sections):
        parts.append(section_text(section))
        if index == len(sections) - 1:
            continue
        target = boundary_target if section["id"] == "05" else standard_target
        filler_text = filler_block(index + 1, target)
        parts.append(filler_text)
        filler_reports.append(
            {
                "after_section_id": section["id"],
                "before_section_id": sections[index + 1]["id"],
                "token_count": token_count(filler_text),
                "boundary_split": section["id"] == "05",
            }
        )
    corpus = "\n\n".join(parts) + "\n"
    canonical_chunks = [
        {
            "chunk_id": f"section-{section['id']}",
            "section_id": section["id"],
            "title": section["title"],
            "text_sha256": sha256_text(section_text(section)),
        }
        for section in sections
    ]
    randomized_order = ["07", "03", "01", "10", "05", "02", "08", "06", "04", "09"]
    randomized_chunks = [
        next(chunk for chunk in canonical_chunks if chunk["section_id"] == section_id)
        for section_id in randomized_order
    ]
    chunk_manifest = canonical_chunks
    if mode is FixtureMode.RANDOMIZED_RETRIEVAL_ORDER:
        chunk_manifest = randomized_chunks
    return {
        "mode": mode.value,
        "corpus": corpus,
        "corpus_sha256": sha256_text(corpus),
        "estimated_token_count": token_count(corpus),
        "sections": sections,
        "filler_blocks": filler_reports,
        "chunk_manifest": chunk_manifest,
        "randomized_retrieval_order": randomized_order,
        "boundary_assertion": {
            "part_a_section_id": "05",
            "part_b_section_id": "06",
            "expected_contiguous_value": "ORCHID-17",
            "zero_overlap_required": mode is FixtureMode.ZERO_OVERLAP,
        },
    }


def question_text() -> str:
    return "\n".join(
        [
            "Based only on the supplied corpus, answer the following:",
            "",
            "1. What is the correct production launch date?",
            "2. Which regions may proceed?",
            "3. Is EU rollout allowed?",
            "4. Which Payments API version is allowed in production?",
            "5. What is the total projected contract cost, and is CFO approval required?",
            "6. What is the emergency kill-switch code?",
            "7. List the sentinel sequence items in document order.",
            "8. Identify any superseded or obsolete facts that should not control the final answer.",
        ]
    )


def prompt_for_corpus(corpus: str) -> str:
    return f"{corpus}\n\n{question_text()}\n"


def expected_answer() -> str:
    return "\n".join(
        [
            "1. Correct production launch date: December 3, 2026.",
            "   Reason: CR-44 supersedes the original November 15, 2026 date.",
            "",
            "2. Regions that may proceed: United States and Canada.",
            "   The EU may not proceed.",
            "",
            "3. EU rollout is not allowed.",
            "   Reason: the DPA is required and has not been signed.",
            "",
            "4. Payments API v3 is required for production.",
            "   Payments API v2 is sandbox-only / obsolete for production.",
            "",
            "5. Total projected contract cost:",
            "   90 users x $120/month x 18 months = $194,400",
            "   Plus $30,000 onboarding = $224,400",
            "   CFO approval is not required because $224,400 is below the $240,000 ceiling.",
            "",
            "6. Emergency kill-switch code: ORCHID-17.",
            "",
            "7. Sentinel sequence in document order:",
            "   ALPHA-19, BRAVO-27, CHARLIE-08, DELTA-66.",
            "",
            "8. Superseded or obsolete facts:",
            "   The November 15, 2026 launch date is superseded.",
            "   The initial EU rollout approval is blocked by the unsigned DPA.",
            "   Payments API v2 is not valid for production because v3 is now mandatory.",
        ]
    )


def contains_negated_eu_allowed(text: str) -> bool:
    normalized = normalize(text)
    return bool(
        re.search(r"\beu\b.{0,80}(not|blocked|may not|cannot|can't|isn't|not allowed|not proceed)", normalized)
        or re.search(r"(not|blocked|may not|cannot|can't|not allowed).{0,80}\beu\b", normalized)
        or re.search(r"european union.{0,80}(blocked|not allowed|may not|cannot)", normalized)
    )


def hard_eu_allowed_claim(text: str) -> bool:
    normalized = normalize(text)
    positive = re.search(r"\b(eu|european union)\b.{0,80}(may proceed|can proceed|is allowed|allowed to proceed|rollout is allowed)", normalized)
    return bool(positive and not contains_negated_eu_allowed(positive.group(0)))


def hard_v2_production_claim(text: str) -> bool:
    normalized = normalize(text)
    positive_v2 = r"(allowed|required|valid|mandatory|must be used|should be used|can be used|use|uses|using)"
    for match in re.finditer(rf"payments api v2.{0,100}{positive_v2}.{0,100}(production|prod)", normalized):
        window = match.group(0)
        if not re.search(r"(not|must not|prohibited|obsolete|sandbox-only|sandbox only)", window):
            return True
    for match in re.finditer(rf"(production|prod).{0,100}{positive_v2}.{0,100}payments api v2", normalized):
        window = match.group(0)
        if not re.search(r"(not|must not|prohibited|obsolete|sandbox-only|sandbox only)", window):
            return True
    return False


def score_answer(answer: str) -> dict[str, Any]:
    text = normalize(answer)
    numbers = number_tokens(answer)
    checks: list[dict[str, Any]] = []

    def add(outcome: str, passed: bool, message: str, *, hard_failure: bool = False) -> None:
        checks.append(
            {
                "outcome": outcome,
                "status": "passed" if passed else "failed",
                "message": message,
                "hard_failure": bool(hard_failure and not passed),
            }
        )

    dec3 = "december 3, 2026" in text or "december 3 2026" in text
    nov_controls = bool(
        re.search(
            r"(correct production launch date|correct launch date|production launch date|final launch date)\s*:?\s*november 15,? 2026",
            text,
        )
    )
    add("launch_date", dec3 and not nov_controls, "requires December 3, 2026 as controlling launch date", hard_failure=True)

    has_us = "united states" in text or re.search(r"\bus\b", text)
    has_canada = "canada" in text or "canadian" in text
    eu_blocked = contains_negated_eu_allowed(answer)
    add("regions", bool(has_us and has_canada and eu_blocked and not hard_eu_allowed_claim(answer)), "requires United States and Canada only", hard_failure=True)

    dpa_unsigned = ("dpa" in text or "data processing addendum" in text) and bool(
        re.search(r"(not signed|unsigned|has not been signed|without a signed)", text)
    )
    add("eu_rollout", bool(eu_blocked and dpa_unsigned), "requires EU blocked because DPA is unsigned", hard_failure=True)

    api_v3 = "payments api v3" in text and ("production" in text or "mandatory" in text or "required" in text)
    v2_non_prod = "payments api v2" in text and bool(re.search(r"(sandbox|obsolete|not valid|must not|prohibited|not be used)", text))
    add("payments_api", bool(api_v3 and v2_non_prod and not hard_v2_production_claim(answer)), "requires v3 for production and v2 non-production only", hard_failure=True)

    cost_ok = {194400, 30000, 224400, 240000}.issubset(numbers)
    no_cfo = bool(re.search(r"cfo.{0,60}(not required|not need|no approval|required is false|is not required)", text)) or bool(
        re.search(r"(not required|no cfo).{0,60}cfo", text)
    )
    cfo_required = bool(re.search(r"cfo.{0,60}(required|approval required|needs approval)", text)) and not no_cfo
    add("contract_cost", bool(cost_ok and no_cfo and not cfo_required), "requires $224,400 total and no CFO approval", hard_failure=True)

    add("kill_switch", "orchid-17" in text, "requires contiguous ORCHID-17", hard_failure=True)

    sentinel_positions = [text.find(sentinel.lower()) for sentinel in SENTINELS]
    sentinel_ok = all(position >= 0 for position in sentinel_positions) and sentinel_positions == sorted(sentinel_positions)
    add("sentinel_order", sentinel_ok, "requires ALPHA, BRAVO, CHARLIE, DELTA in document order", hard_failure=True)

    obsolete_nov = "november 15, 2026" in text and bool(re.search(r"november 15,? 2026.{0,100}(superseded|obsolete|earlier)", text))
    obsolete_eu = ("eu" in text or "european union" in text) and bool(re.search(r"(blocked|not allowed|may not proceed).{0,120}(dpa|data processing addendum)", text))
    obsolete_v2 = "payments api v2" in text and bool(re.search(r"payments api v2.{0,120}(not valid|not be used|obsolete|sandbox|superseded)", text))
    add("obsolete_facts", bool(obsolete_nov and obsolete_eu and obsolete_v2), "requires obsolete launch, EU, and API facts", hard_failure=True)

    failed = [item for item in checks if item["status"] != "passed"]
    hard_failures = [item for item in failed if item["hard_failure"]]
    return {
        "status": AdversarialContextStitchingStatus.PASSED.value if not failed else AdversarialContextStitchingStatus.FAILED.value,
        "score": len(checks) - len(failed),
        "max_score": len(checks),
        "failed_outcome_count": len(failed),
        "hard_failure_count": len(hard_failures),
        "checks": checks,
    }


def fixture_integrity_errors(policy: dict[str, Any], fixtures: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    filler_policy = dict_value(policy.get("filler"))
    minimum = int(filler_policy.get("minimum_token_count", 2000))
    maximum = int(filler_policy.get("maximum_token_count", 5000))
    boundary_minimum = int(filler_policy.get("boundary_minimum_token_count", 2600))
    for mode, fixture in fixtures.items():
        if "ORCHID-\n\n" not in fixture["corpus"]:
            errors.append(validation_error(f"fixture.{mode}.boundary_marker", "ORCHID- must be separated from section 06 by filler", source="fixture"))
        for filler in object_list(fixture.get("filler_blocks")):
            count = int(filler.get("token_count", 0))
            if count < minimum or count > maximum:
                errors.append(validation_error(f"fixture.{mode}.filler", "filler token count outside policy range", source="fixture"))
            if filler.get("boundary_split") and count < boundary_minimum:
                errors.append(validation_error(f"fixture.{mode}.boundary_filler", "boundary filler below required minimum", source="fixture"))
        if mode == FixtureMode.ZERO_OVERLAP.value:
            manifest = object_list(fixture.get("chunk_manifest"))
            part_a = next((item for item in manifest if item.get("section_id") == "05"), {})
            part_b = next((item for item in manifest if item.get("section_id") == "06"), {})
            if not part_a or not part_b or part_a.get("chunk_id") == part_b.get("chunk_id"):
                errors.append(validation_error("fixture.zero_overlap.boundary_chunks", "ORCHID split parts must land in separate chunks", source="fixture"))
        if mode == FixtureMode.RANDOMIZED_RETRIEVAL_ORDER.value:
            order = [item.get("section_id") for item in object_list(fixture.get("chunk_manifest"))]
            if order == sorted(order):
                errors.append(validation_error("fixture.randomized_retrieval_order.order", "randomized retrieval order must differ from document order", source="fixture"))
            sentinel_order = [
                item.get("section_id")
                for item in object_list(fixture.get("chunk_manifest"))
                if item.get("section_id") in {"01", "03", "07", "10"}
            ]
            if sentinel_order == ["01", "03", "07", "10"]:
                errors.append(validation_error("fixture.randomized_retrieval_order.sentinel_chunks", "sentinel-bearing chunks must be shuffled", source="fixture"))
    return errors


def write_fixture_artifacts(fixture_dir: Path, policy: dict[str, Any]) -> dict[str, Any]:
    fixture_dir.mkdir(parents=True, exist_ok=True)
    fixtures: dict[str, dict[str, Any]] = {}
    artifacts: dict[str, Any] = {}
    for mode in FixtureMode:
        fixture = build_corpus(policy, mode)
        fixtures[mode.value] = fixture
        mode_dir = fixture_dir / mode.value
        write_text(mode_dir / "corpus.txt", fixture["corpus"])
        write_text(mode_dir / "prompt.txt", prompt_for_corpus(fixture["corpus"]))
        write_json(
            mode_dir / "chunk-manifest.json",
            {
                "schema_version": SCHEMA_VERSION,
                "mode": mode.value,
                "corpus_sha256": fixture["corpus_sha256"],
                "chunks": fixture["chunk_manifest"],
                "boundary_assertion": fixture["boundary_assertion"],
            },
        )
        artifacts[mode.value] = {
            "corpus_path": str((mode_dir / "corpus.txt").resolve()),
            "prompt_path": str((mode_dir / "prompt.txt").resolve()),
            "chunk_manifest_path": str((mode_dir / "chunk-manifest.json").resolve()),
            "corpus_sha256": fixture["corpus_sha256"],
            "estimated_token_count": fixture["estimated_token_count"],
            "chunk_count": len(object_list(fixture.get("chunk_manifest"))),
        }
    expected_path = fixture_dir / "expected-answer.txt"
    question_path = fixture_dir / "question.txt"
    write_text(expected_path, expected_answer() + "\n")
    write_text(question_path, question_text() + "\n")
    artifacts["expected_answer_path"] = str(expected_path.resolve())
    artifacts["expected_answer_sha256"] = sha256_file(expected_path)
    artifacts["question_path"] = str(question_path.resolve())
    artifacts["question_sha256"] = sha256_file(question_path)
    artifacts["fixtures"] = fixtures
    return artifacts


def gateway_answer(config: AdversarialContextStitchingConfig, prompt: str) -> tuple[int, dict[str, Any], str]:
    payload: dict[str, Any] = {
        "model": "agentic-workflow-router",
        "messages": [{"role": "user", "content": prompt}],
        "role_base_url": config.model_base_url,
        "budgets": {"max_model_calls": 3, "max_selected_skills": 5, "max_selected_tools": 5},
    }
    status, body = json_request(
        f"{config.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload=payload,
        timeout_seconds=config.timeout_seconds,
    )
    response_text = ""
    if status == 200:
        try:
            response_text = text_response(body)
        except RuntimeError:
            response_text = json.dumps(body, ensure_ascii=True, sort_keys=True)
    return status, body, response_text


def live_gateway_mode_result(
    config: AdversarialContextStitchingConfig,
    *,
    fixture_dir: Path,
    mode: str,
    prompt_path: str,
) -> dict[str, Any]:
    prompt = Path(prompt_path).read_text(encoding="utf-8")
    status, body, response_text = gateway_answer(config, prompt)
    live_score = score_answer(response_text)
    live_answer_path = fixture_dir / f"live-gateway-answer-{mode}.txt"
    write_text(live_answer_path, response_text)
    return {
        "mode": mode,
        "http_status": status,
        "body_sha256": sha256_text(json.dumps(body, ensure_ascii=True, sort_keys=True)),
        "response_sha256": sha256_text(response_text),
        "score": live_score,
        "answer_path": str(live_answer_path.resolve()),
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = dict_value(report.get("summary"))
    lines = [
        "# Adversarial Context Stitching",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Error count: `{summary.get('error_count')}`",
        f"- Fixture mode count: `{summary.get('fixture_mode_count')}`",
        f"- Expected-answer hard failures: `{summary.get('expected_answer_hard_failure_count')}`",
        f"- Answer-file hard failures: `{summary.get('answer_file_hard_failure_count')}`",
        f"- Live-gateway hard failures: `{summary.get('live_gateway_hard_failure_count')}`",
        "",
        "## Errors",
    ]
    errors = object_list(report.get("errors"))
    if errors:
        lines.extend(f"- `{item.get('severity')}` `{item.get('id')}`: {item.get('message')}" for item in errors)
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def validate_adversarial_context_stitching(config: AdversarialContextStitchingConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy_path = resolve_path(config_root, config.policy_path)
    output_path = resolve_path(config_root, config.output_path)
    markdown_output_path = resolve_path(config_root, config.markdown_output_path)
    fixture_dir = resolve_path(config_root, config.fixture_dir)
    policy = read_json_object(policy_path)

    policy_errors = validate_policy(policy)
    docs, docs_errors = docs_checks(config_root, policy)
    artifacts = write_fixture_artifacts(fixture_dir, policy)
    fixtures = {key: value for key, value in dict_value(artifacts.get("fixtures")).items() if isinstance(value, dict)}
    integrity_errors = fixture_integrity_errors(policy, fixtures)
    expected_score = score_answer(expected_answer())
    errors = policy_errors + docs_errors + integrity_errors
    if expected_score["status"] != AdversarialContextStitchingStatus.PASSED.value:
        errors.append(validation_error("expected_answer.score", "built-in expected answer does not satisfy the scorer", source="scorer", severity="critical"))

    answer_file_score: dict[str, Any] | None = None
    answer_file_path: str | None = None
    if config.answer_file is not None:
        resolved_answer_file = resolve_path(config_root, config.answer_file)
        answer_file_path = str(resolved_answer_file)
        if not resolved_answer_file.is_file():
            errors.append(validation_error("answer_file.missing", "answer-file does not exist", source="answer_file", severity="critical"))
        else:
            answer_file_score = score_answer(resolved_answer_file.read_text(encoding="utf-8"))
            if answer_file_score["status"] != AdversarialContextStitchingStatus.PASSED.value:
                errors.append(validation_error("answer_file.score", "answer-file failed adversarial stitching score", source="answer_file", severity="critical"))

    live_gateway_result: dict[str, Any] | None = None
    live_gateway_results: list[dict[str, Any]] = []
    if config.live_gateway:
        for mode in FixtureMode:
            prompt_path = str(dict_value(artifacts.get(mode.value)).get("prompt_path") or "")
            result = live_gateway_mode_result(config, fixture_dir=fixture_dir, mode=mode.value, prompt_path=prompt_path)
            live_gateway_results.append(result)
            if mode is FixtureMode.STANDARD:
                live_gateway_result = result
                legacy_answer_path = fixture_dir / "live-gateway-answer.txt"
                write_text(legacy_answer_path, Path(result["answer_path"]).read_text(encoding="utf-8"))
                live_gateway_result["legacy_answer_path"] = str(legacy_answer_path.resolve())
            if result["http_status"] != 200:
                errors.append(
                    validation_error(
                        f"live_gateway.{mode.value}.http_status",
                        f"live gateway returned HTTP {result['http_status']} for {mode.value}",
                        source="live_gateway",
                        severity="critical",
                    )
                )
            if dict_value(result.get("score")).get("status") != AdversarialContextStitchingStatus.PASSED.value:
                errors.append(
                    validation_error(
                        f"live_gateway.{mode.value}.score",
                        f"live gateway answer failed adversarial stitching score for {mode.value}",
                        source="live_gateway",
                        severity="critical",
                    )
                )

    status = AdversarialContextStitchingStatus.PASSED.value if not errors else AdversarialContextStitchingStatus.FAILED.value
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "milestone_ids": sorted(EXPECTED_MILESTONE_IDS),
        "generated_at": utc_timestamp(),
        "status": status,
        "policy_path": str(policy_path),
        "policy_sha256": sha256_file(policy_path) if policy_path.is_file() else None,
        "docs": docs,
        "fixture_artifacts": {key: value for key, value in artifacts.items() if key != "fixtures"},
        "fixture_summaries": [
            {
                "mode": mode,
                "corpus_sha256": value.get("corpus_sha256"),
                "estimated_token_count": value.get("estimated_token_count"),
                "filler_block_count": len(object_list(value.get("filler_blocks"))),
                "chunk_count": len(object_list(value.get("chunk_manifest"))),
            }
            for mode, value in fixtures.items()
        ],
        "expected_answer_score": expected_score,
        "answer_file_path": answer_file_path,
        "answer_file_score": answer_file_score,
        "live_gateway_result": live_gateway_result,
        "live_gateway_results": live_gateway_results,
        "errors": errors,
        "summary": {
            "error_count": len(errors),
            "fixture_mode_count": len(fixtures),
            "fixture_modes": sorted(fixtures),
            "standard_prompt_path": dict_value(artifacts.get("standard")).get("prompt_path"),
            "zero_overlap_manifest_path": dict_value(artifacts.get("zero_overlap")).get("chunk_manifest_path"),
            "randomized_retrieval_order_manifest_path": dict_value(artifacts.get("randomized_retrieval_order")).get("chunk_manifest_path"),
            "expected_answer_hard_failure_count": expected_score.get("hard_failure_count"),
            "answer_file_hard_failure_count": None if answer_file_score is None else answer_file_score.get("hard_failure_count"),
            "live_gateway_hard_failure_count": None
            if not live_gateway_results
            else sum(int(dict_value(result.get("score")).get("hard_failure_count") or 0) for result in live_gateway_results),
            "live_gateway_mode_count": len(live_gateway_results),
            "live_gateway_failed_mode_count": len(
                [
                    result
                    for result in live_gateway_results
                    if dict_value(result.get("score")).get("status") != AdversarialContextStitchingStatus.PASSED.value
                    or result.get("http_status") != 200
                ]
            ),
            "phase279_ready": not errors,
        },
    }
    write_json(output_path, report)
    write_text(markdown_output_path, render_markdown(report))
    return report
