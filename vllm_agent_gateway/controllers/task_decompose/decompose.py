"""Read-only deterministic multi-step task decomposition workflow."""

from __future__ import annotations

import json
import os
import re
import shlex
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from enum import Enum
from http import HTTPStatus
from pathlib import Path
from typing import Any

from vllm_agent_gateway.invocation import InvocationResult, WorkflowStatus


WORKFLOW_ID = "task.decompose"
SCHEMA_VERSION = 1
WORK_PACKAGE_SCHEMA_VERSION = 3
DEFAULT_OUTPUT_DIR = "task-decompositions"
MAX_SELECTED_SKILLS = 5
MAX_SELECTED_TOOLS = 5
MAX_READY_WORK_PACKAGES = 5
PHASE113_TENET_IDS = ["T01", "T02", "T03"]
PHASE114_TENET_IDS = ["T04", "T05"]
PHASE115_TENET_IDS = ["T06", "T07"]
PHASE119_TENET_IDS = ["T19", "T20"]


class DecompositionStatus(str, Enum):
    READY = "ready"
    NEEDS_CLARIFICATION = "needs_clarification"
    BLOCKED = "blocked"


class PromptFamily(str, Enum):
    AMBIGUOUS = "ambiguous"
    ADVANCED_REFACTOR_DEFERRED = "advanced_refactor_deferred"
    FAILING_TEST_REMEDIATION = "failing_test_remediation"
    FEATURE_OR_SMALL_CHANGE = "feature_or_small_change"
    MULTI_STEP_INVESTIGATION = "multi_step_investigation"
    GENERAL_DEVELOPMENT_TASK = "general_development_task"
    OVERSIZED = "oversized"
    REQUIREMENTS_TRANSLATION = "requirements_translation"
    INCREMENTAL_IMPLEMENTATION_PLAN = "incremental_implementation_plan"
    DELIVERY_MENTORSHIP = "delivery_mentorship"


class RiskLevel(str, Enum):
    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class WorkPackageStage(str, Enum):
    INVESTIGATION = "investigation"
    PREP_APPROVAL_GATE = "prep_approval_gate"
    IMPLEMENTATION_PREP = "implementation_prep"
    VERIFICATION = "verification"
    TERMINAL_STOP = "terminal_stop"


class MutationPolicy(str, Enum):
    READ_ONLY = "read_only_no_source_mutation"
    DRAFT_ONLY_UNTIL_APPROVAL = "draft_only_until_approval"
    MUTATION_BLOCKED = "repository_mutation_blocked"
    UNSUPPORTED_DEFERRED = "unsupported_deferred_until_phase_105"


class NextAction(str, Enum):
    EXECUTE_READ_ONLY = "execute_read_only"
    ASK_BLOCKING_QUESTION = "ask_blocking_question"
    NONE = "none"


class TaskDecompositionError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "task_decomposition_error",
        status: HTTPStatus = HTTPStatus.UNPROCESSABLE_ENTITY,
    ):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class TaskDecompositionRequest:
    config_root: Path | str = "."
    target_root: Path | str = "."
    output_root: Path | str = ".agentic_controller"
    workflow: str = WORKFLOW_ID
    schema_version: int = SCHEMA_VERSION
    user_request: str = ""
    role_id: str = "architect/default"
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        config_root: Path,
        target_root: Path,
        output_root: Path,
    ) -> "TaskDecompositionRequest":
        values: dict[str, Any] = {
            "config_root": config_root,
            "target_root": target_root,
            "output_root": output_root,
        }
        names = {item.name for item in fields(cls)}
        for key, value in payload.items():
            if key in names:
                values[key] = value
        return cls(**values)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def artifact_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TaskDecompositionError(f"Missing {label}: {path}", code=f"missing_{label.replace(' ', '_')}") from exc
    except json.JSONDecodeError as exc:
        raise TaskDecompositionError(f"Invalid {label} JSON: {exc}", code=f"invalid_{label.replace(' ', '_')}") from exc
    if not isinstance(value, dict):
        raise TaskDecompositionError(f"{label} must contain a JSON object.", code=f"invalid_{label.replace(' ', '_')}")
    return value


def lower_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def load_workflows(config_root: Path) -> dict[str, dict[str, Any]]:
    manifest = read_json_object(config_root / "runtime" / "workflows.json", "workflow catalog")
    workflows = manifest.get("workflows")
    if not isinstance(workflows, list):
        raise TaskDecompositionError("runtime/workflows.json must contain a workflows list.", code="invalid_workflow_catalog")
    return {item["id"]: item for item in workflows if isinstance(item, dict) and isinstance(item.get("id"), str)}


def load_skills(config_root: Path) -> dict[str, dict[str, Any]]:
    manifest = read_json_object(config_root / "runtime" / "skills.json", "skill catalog")
    skills = manifest.get("skills")
    if not isinstance(skills, list):
        raise TaskDecompositionError("runtime/skills.json must contain a skills list.", code="invalid_skill_catalog")
    return {item["id"]: item for item in skills if isinstance(item, dict) and isinstance(item.get("id"), str)}


def load_tools(config_root: Path) -> dict[str, dict[str, Any]]:
    manifest = read_json_object(config_root / "runtime" / "tools.json", "tool catalog")
    tools = manifest.get("tools")
    if not isinstance(tools, list):
        raise TaskDecompositionError("runtime/tools.json must contain a tools list.", code="invalid_tool_catalog")
    return {item["id"]: item for item in tools if isinstance(item, dict) and isinstance(item.get("id"), str)}


def workflow_tool_ids(workflow: dict[str, Any], limit: int = MAX_SELECTED_TOOLS) -> list[str]:
    values = string_list(workflow.get("controller_tool_ids"))
    conditional = workflow.get("conditional_controller_tool_ids")
    if isinstance(conditional, list):
        for rule in conditional:
            if isinstance(rule, dict):
                values.extend(string_list(rule.get("tool_ids")))
    deduped = sorted(set(values))
    return deduped[:limit]


def skill_ids_for_workflow(
    skills: dict[str, dict[str, Any]],
    workflow_id: str,
    request_text: str,
    *,
    limit: int = MAX_SELECTED_SKILLS,
) -> list[str]:
    scored: list[tuple[int, str]] = []
    words = set(re.findall(r"[a-z0-9_]+", request_text))
    for skill_id, skill in skills.items():
        if workflow_id not in string_list(skill.get("workflows")):
            continue
        if skill.get("eval_status") == "deprecated":
            continue
        triggers = string_list(skill.get("triggers"))
        hit_count = sum(1 for trigger in triggers if trigger.lower() in request_text or trigger.lower() in words)
        priority = 0
        priorities = skill.get("workflow_priorities")
        if isinstance(priorities, dict) and isinstance(priorities.get(workflow_id), int):
            priority = int(priorities[workflow_id])
        scored.append((hit_count * 100 + priority, skill_id))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [skill_id for score, skill_id in scored if score >= 0][:limit]


def validate_request(request: TaskDecompositionRequest) -> None:
    if request.workflow != WORKFLOW_ID:
        raise TaskDecompositionError("workflow must be task.decompose.", code="unsupported_workflow")
    if request.schema_version != SCHEMA_VERSION:
        raise TaskDecompositionError("schema_version must be 1.", code="unsupported_schema_version")
    if not isinstance(request.user_request, str) or not request.user_request.strip():
        raise TaskDecompositionError("user_request is required.", code="missing_user_request", status=HTTPStatus.BAD_REQUEST)
    if not Path(request.target_root).resolve().is_dir():
        raise TaskDecompositionError("target_root must be an existing directory.", code="invalid_target_root")


def is_ambiguous_request(user_request: str) -> bool:
    text = lower_text(user_request)
    meaningful = re.findall(r"[a-z0-9_]+", text)
    if len(meaningful) < 5:
        return True
    return bool(re.fullmatch(r"(fix|change|update|refactor|investigate)\s+(it|this|that)", text))


def is_advanced_refactor_request(user_request: str) -> bool:
    text = lower_text(user_request)
    explicit_advanced_terms = (
        "single path",
        "one code path",
        "only one path",
        "only one code path",
        "consolidate paths",
        "duplicate path",
        "broad refactor",
        "whole subsystem",
    )
    return any(term in text for term in explicit_advanced_terms)


def is_oversized_request(user_request: str) -> bool:
    text = lower_text(user_request)
    oversized_terms = (
        "entire repo",
        "entire repository",
        "whole repo",
        "whole repository",
        "whole project",
        "whole codebase",
        "entire codebase",
        "whole application",
        "rewrite everything",
        "all modules",
        "all files",
        "complete product",
    )
    return any(term in text for term in oversized_terms)


def classify_prompt_family(user_request: str) -> tuple[PromptFamily, RiskLevel]:
    text = lower_text(user_request)
    if is_delivery_mentorship_request(text):
        return PromptFamily.DELIVERY_MENTORSHIP, RiskLevel.MEDIUM
    if is_advanced_refactor_request(user_request):
        return PromptFamily.ADVANCED_REFACTOR_DEFERRED, RiskLevel.HIGH
    if is_oversized_request(user_request):
        return PromptFamily.OVERSIZED, RiskLevel.HIGH
    if is_requirements_translation_request(text):
        return PromptFamily.REQUIREMENTS_TRANSLATION, RiskLevel.MEDIUM
    if is_incremental_implementation_plan_request(text):
        return PromptFamily.INCREMENTAL_IMPLEMENTATION_PLAN, RiskLevel.MEDIUM
    if any(term in text for term in ("failing test", "pytest failure", "fix test", "test failure")):
        return PromptFamily.FAILING_TEST_REMEDIATION, RiskLevel.MEDIUM
    if any(term in text for term in ("add", "create", "implement", "build", "feature")):
        return PromptFamily.FEATURE_OR_SMALL_CHANGE, RiskLevel.MEDIUM
    if any(term in text for term in ("investigate", "diagnose", "trace", "map")):
        return PromptFamily.MULTI_STEP_INVESTIGATION, RiskLevel.LOW
    return PromptFamily.GENERAL_DEVELOPMENT_TASK, RiskLevel.MEDIUM


def is_requirements_translation_request(text: str) -> bool:
    requirement_terms = (
        "business requirement",
        "business requirements",
        "technical requirement",
        "technical requirements",
        "translate requirement",
        "translate this requirement",
        "translate these requirements",
        "requirements translation",
        "acceptance requirement",
    )
    estimate_terms = (
        "estimate effort",
        "effort estimate",
        "estimate the work",
        "estimate development",
        "scope driver",
        "revise estimate",
        "updated estimate",
    )
    return any(term in text for term in requirement_terms) or any(term in text for term in estimate_terms)


def is_incremental_implementation_plan_request(text: str) -> bool:
    plan_terms = (
        "incremental implementation plan",
        "implementation plan",
        "implementation steps",
        "plan the implementation",
        "plan implementation",
        "changeset",
        "change set",
        "change-set",
        "isolated changes",
        "isolated commits",
        "small commits",
        "commit message",
        "commit messages",
        "version control plan",
        "version-control plan",
    )
    if any(term in text for term in plan_terms):
        return any(
            term in text
            for term in (
                "implement",
                "implementation",
                "change",
                "changes",
                "feature",
                "fix",
                "add",
                "update",
                "test",
                "commit",
                "version control",
            )
        )
    return False


def is_delivery_mentorship_request(text: str) -> bool:
    mentorship_terms = (
        "mentor",
        "coach",
        "teach",
        "junior engineer",
        "less experienced engineer",
        "walk me through",
        "explain the workflow",
    )
    delivery_terms = (
        "end-to-end",
        "end to end",
        "from intake through",
        "deployment readiness",
        "release readiness",
        "definition of done",
        "delivery plan",
        "safe implementation path",
        "small-to-medium feature",
        "small to medium feature",
    )
    engineering_practice_terms = (
        "task decomposition",
        "testing strategy",
        "debugging methodology",
        "code quality",
        "development workflow",
        "quality gate",
        "regression test",
        "review feedback",
        "rollback",
        "observability",
    )
    has_mentorship = any(term in text for term in mentorship_terms)
    has_delivery = any(term in text for term in delivery_terms)
    has_practice = any(term in text for term in engineering_practice_terms)
    return (has_delivery and has_practice) or (has_mentorship and (has_delivery or has_practice))


def source_requirement_text(user_request: str) -> str:
    text = " ".join(user_request.strip().split())
    for marker in (":", " requirement is ", " requirements are "):
        if marker in text:
            if marker == ":":
                split_index = next(
                    (
                        match.start()
                        for match in re.finditer(":", text)
                        if not (
                            match.start() > 0
                            and text[match.start() - 1].isalpha()
                            and match.start() + 1 < len(text)
                            and text[match.start() + 1] in "\\/"
                        )
                    ),
                    -1,
                )
                if split_index < 0:
                    continue
                candidate = text[split_index + 1 :].strip()
            else:
                candidate = text.split(marker, 1)[1].strip()
            if candidate:
                return strip_output_instruction(candidate)[:500]
    return strip_output_instruction(text)[:500]


def strip_output_instruction(text: str) -> str:
    return re.sub(
        r"\s+return\s+(?:json|the answer in the default format|the response in json|the answer as json)\.?\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()


def request_mentions_scope_revision(user_request: str) -> bool:
    text = lower_text(user_request)
    revision_terms = (
        "scope changed",
        "scope change",
        "now also",
        "also include",
        "instead include",
        "revise estimate",
        "updated estimate",
        "new information",
    )
    return any(term in text for term in revision_terms)


def estimate_band_for_request(user_request: str) -> dict[str, Any]:
    text = lower_text(user_request)
    if request_mentions_scope_revision(user_request):
        band = "medium"
        cycle_range = "2-4 short cycles"
        confidence = "low"
    elif any(term in text for term in ("new endpoint", "new route", "new api", "database", "schema", "migration")):
        band = "medium"
        cycle_range = "2-3 short cycles"
        confidence = "medium"
    else:
        band = "small"
        cycle_range = "1-2 short cycles"
        confidence = "medium"
    return {"estimate_band": band, "cycle_count_range": cycle_range, "confidence": confidence}


STOPWORDS = {
    "a",
    "an",
    "and",
    "answer",
    "also",
    "because",
    "business",
    "changed",
    "changing",
    "effort",
    "estimate",
    "file",
    "files",
    "for",
    "include",
    "into",
    "need",
    "needs",
    "note",
    "now",
    "requirement",
    "requirements",
    "scope",
    "say",
    "should",
    "show",
    "technical",
    "that",
    "the",
    "this",
    "to",
    "translate",
    "users",
    "whether",
    "with",
    "without",
    "work",
    "yet",
}


def requirement_keywords(requirement_text: str) -> list[str]:
    normalized = requirement_text.replace("-", "_")
    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", normalized)
    keywords: list[str] = preserved_requirement_phrases(normalized)
    for token in tokens:
        lowered = token.lower()
        if len(lowered) < 3 or lowered in STOPWORDS:
            continue
        if "_" in token or token != lowered or lowered.endswith(("lookup", "evidence", "response", "status", "order")):
            if token not in keywords:
                keywords.append(token)
        elif len(keywords) < 4 and token not in keywords:
            keywords.append(token)
    return keywords[:6] or ["requested_behavior"]


def preserved_requirement_phrases(normalized_requirement_text: str) -> list[str]:
    text = normalized_requirement_text.lower()
    phrases: list[str] = []
    for phrase in ("resolved order status", "requirement note", "documentation note"):
        if phrase in text:
            phrases.append(phrase.replace(" ", "_"))
    for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", normalized_requirement_text):
        if "_" in token and token.lower() not in STOPWORDS:
            phrases.append(token)
    return list(dict.fromkeys(phrases))


def keyword_present_in_text(keyword: str, text: str) -> bool:
    lowered = text.lower()
    normalized = keyword.lower()
    return normalized in lowered or normalized.replace("_", " ") in lowered


def requirement_surface(requirement_text: str, keywords: list[str]) -> str:
    text = requirement_text.lower()
    if "lookup" in text:
        return "lookup answer"
    if "response" in text:
        return "response payload"
    if "message" in text:
        return "user-facing message"
    if keywords:
        return f"{keywords[0]} behavior"
    return "requested behavior"


def observable_condition(requirement_text: str, keywords: list[str]) -> str:
    text = requirement_text.lower()
    evidence_keyword = next((item for item in keywords if "evidence" in item.lower()), None)
    if "resolved" in text and "order" in text and "status" in text:
        condition = f"the {requirement_surface(requirement_text, keywords)} shows the resolved order status"
    elif evidence_keyword:
        condition = f"the {requirement_surface(requirement_text, keywords)} explicitly reports whether {evidence_keyword} is present"
    elif "found" in text or "whether" in text:
        key = keywords[0] if keywords else "the requested evidence"
        condition = f"the {requirement_surface(requirement_text, keywords)} explicitly reports whether {key} was found"
    else:
        condition = f"the {requirement_surface(requirement_text, keywords)} exposes the requested outcome for {', '.join(keywords[:3])}"
    missing_keywords = [keyword for keyword in keywords if not keyword_present_in_text(keyword, condition)]
    if missing_keywords:
        condition = f"{condition} and includes {', '.join(missing_keywords)}"
    return condition


def build_requirements_translation_contract(user_request: str) -> dict[str, Any]:
    requirement_text = source_requirement_text(user_request)
    keywords = requirement_keywords(requirement_text)
    surface = requirement_surface(requirement_text, keywords)
    condition = observable_condition(requirement_text, keywords)
    estimate = estimate_band_for_request(user_request)
    revision_requested = request_mentions_scope_revision(user_request)
    return {
        "kind": "requirements_translation_contract",
        "schema_version": 1,
        "phase": 114,
        "tenet_ids": PHASE114_TENET_IDS,
        "status": "ready_for_review",
        "source_business_requirements": [
            {
                "id": "BR1",
                "source": "user_request",
                "text": requirement_text,
                "status": "explicit",
            }
        ],
        "technical_requirements": [
            {
                "id": "TR1",
                "derived_from": ["BR1"],
                "requirement": f"Find the existing {surface} path that can expose: {condition}.",
                "domain_terms": keywords,
                "observable_outcome": condition,
                "complexity_guardrail": f"Do not add new subsystems, data stores, APIs, or broad architecture changes unless BR1 explicitly requires them for {', '.join(keywords[:3])}.",
                "verification_hint": f"WP1 must identify source references for {surface} and {', '.join(keywords[:3])} before drafting any change packet.",
            },
            {
                "id": "TR2",
                "derived_from": ["BR1"],
                "requirement": f"Define the smallest testable outcome: {condition}.",
                "domain_terms": keywords,
                "observable_outcome": condition,
                "complexity_guardrail": f"Prefer the existing {surface} and tests when repo evidence supports the {', '.join(keywords[:3])} behavior.",
                "verification_hint": f"Acceptance criteria must name observable output for {surface}, source evidence, or a smallest useful test command.",
            },
        ],
        "explicit_assumptions": [
            {
                "id": "A1",
                "assumption": "The named target repository is the only implementation boundary for this request.",
                "why_needed": "The request enters task.decompose with one target root.",
                "confidence": "high",
            },
            {
                "id": "A2",
                "assumption": "Implementation details must be confirmed by repository evidence before any packet design or source apply step.",
                "why_needed": "task.decompose is read-only and does not inspect source content itself.",
                "confidence": "high",
            },
        ],
        "rejected_assumptions": [
            {
                "id": "RA1",
                "assumption": f"A new database, service, or public API is required to satisfy {', '.join(keywords[:3])}.",
                "rejection_reason": f"BR1 only asks for {condition}; it does not explicitly require new infrastructure or a public contract change.",
            },
            {
                "id": "RA2",
                "assumption": "Source files may be edited during requirements translation.",
                "rejection_reason": f"task.decompose is a read-only planning workflow; any source change for {surface} requires a later approved implementation path.",
            },
        ],
        "dependencies": [
            {
                "id": "D1",
                "description": "WP1 must gather source evidence before estimates or implementation packets are treated as implementation-ready.",
                "domain_terms": keywords,
                "blocks": ["implementation_prep"],
            }
        ],
        "risk_notes": [
            {
                "id": "R1",
                "level": "medium",
                "risk": "The business requirement may hide unstated product, API, or compatibility constraints.",
                "mitigation": f"Keep unstated details about {surface} and {', '.join(keywords[:3])} as rejected assumptions until source evidence or caller clarification supports them.",
            }
        ],
        "effort_estimate": {
            "estimate_band": estimate["estimate_band"],
            "cycle_count_range": estimate["cycle_count_range"],
            "confidence": estimate["confidence"],
            "assumption_ids": ["A1", "A2"],
            "scope_drivers": [
                f"number of affected {surface} files or interfaces discovered by WP1",
                f"whether existing tests already cover {', '.join(keywords[:3])}",
                "whether caller adds API, persistence, migration, or compatibility requirements",
            ],
            "revision_triggers": [
                f"WP1 finds more than one bounded {surface} implementation surface",
                f"source evidence shows missing tests around {', '.join(keywords[:3])}",
                "caller adds persistence, API, compatibility, or cross-module scope",
            ],
            "revision_policy": "Revise the estimate before implementation prep whenever a revision trigger is observed.",
        },
        "estimate_revision": {
            "status": "revised" if revision_requested else "not_requested",
            "changed_scope_factors": (
                [
                    "The request says scope changed or adds an additional included behavior.",
                    "The updated estimate must be reviewed before implementation prep.",
                ]
                if revision_requested
                else []
            ),
            "requires_reapproval_before_implementation_prep": revision_requested,
        },
        "unsupported_assumptions_policy": "Unsupported assumptions must be rejected or converted into blocking clarification before implementation prep.",
    }


def implementation_subject_text(user_request: str) -> str:
    text = source_requirement_text(user_request)
    text = re.sub(r"^in\s+\S+,\s+", "", text, flags=re.IGNORECASE)
    behavior_match = re.search(
        r"\bfor\s+((?:add|adding|update|updating|fix|fixing|change|changing|implement|implementing|cover|covering)\b.+)$",
        text,
        flags=re.IGNORECASE,
    )
    if behavior_match:
        text = behavior_match.group(1).strip()
    text = re.sub(
        r"^(?:please\s+)?(?:create|draft|write|make|build)?\s*(?:an?\s+)?"
        r"(?:incremental\s+)?implementation\s+plan\s+(?:for|to)\s+",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\s+(?:include|with)\s+(?:isolated\s+)?(?:changesets?|change sets?|commits?).*$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = strip_output_instruction(text)
    return text[:500] or "requested implementation behavior"


def implementation_domain_terms(user_request: str) -> list[str]:
    terms = requirement_keywords(implementation_subject_text(user_request))
    filtered = [
        term
        for term in terms
        if term.lower()
        not in {
            "implementation",
            "incremental",
            "plan",
            "changeset",
            "changesets",
            "commit",
            "commits",
            "message",
            "messages",
            "version",
            "control",
            "add",
            "adding",
            "update",
            "updating",
            "change",
            "changing",
            "fix",
            "fixing",
        }
    ]
    return filtered[:5] or ["requested_behavior"]


def commit_subject(verb: str, noun: str) -> str:
    normalized = re.sub(r"\s+", " ", noun.replace("_", " ")).strip()
    subject = f"{verb} {normalized}".strip()
    return subject[:72].rstrip()


def behavior_label_for_implementation(subject: str, terms: list[str]) -> str:
    if not terms:
        return requirement_surface(subject, terms)
    first = terms[0].replace("_", " ")
    context: list[str] = []
    for term in terms[1:]:
        normalized = term.replace("_", " ")
        if normalized in first or normalized in context:
            continue
        context.append(normalized)
    if context:
        return f"{first} to {' '.join(context[:3])}"[:56].strip()
    return first[:56].strip()


def pytest_candidate_paths(target_root: Path, terms: list[str]) -> list[tuple[int, str]]:
    if not target_root.is_dir():
        return []
    ignored_dirs = {".git", ".hg", ".svn", ".venv", "venv", "__pycache__", "node_modules", ".mypy_cache", ".pytest_cache"}
    candidates: list[tuple[int, str]] = []
    inspected = 0
    normalized_terms = [term.lower().replace("_", " ") for term in terms]
    for directory, dirnames, filenames in os.walk(target_root):
        dirnames[:] = [item for item in dirnames if item not in ignored_dirs]
        for filename in filenames:
            if not (filename.startswith("test") and filename.endswith(".py")) and not filename.endswith("_test.py"):
                continue
            inspected += 1
            if inspected > 1000:
                break
            path = Path(directory) / filename
            relative = path.relative_to(target_root).as_posix()
            searchable = relative.lower().replace("_", " ").replace("-", " ")
            score = 0
            for index, term in enumerate(normalized_terms):
                if term and term in searchable:
                    score += 6 if index == 0 else 3
                else:
                    for part in term.split():
                        if len(part) >= 3 and part in searchable:
                            score += 2 if index == 0 else 1
            if "regression" in searchable:
                score += 1
            if "integration" in searchable:
                score += 1
            candidates.append((score, relative))
        if inspected > 1000:
            break
    return sorted(candidates, key=lambda item: (-item[0], item[1]))


def targeted_pytest_command(target_root: Path | None, terms: list[str]) -> str | None:
    if target_root is None:
        return None
    candidates = pytest_candidate_paths(target_root, terms)
    if not candidates:
        return None
    return f"python -m pytest {shlex.quote(candidates[0][1])} -q"


def verification_command_for_subject(subject: str, *, target_root: Path | None = None, terms: list[str] | None = None) -> str:
    lowered = subject.lower()
    if any(term in lowered for term in ("readme", "doc", "documentation")):
        return "python scripts/check_docs_index.py"
    targeted = targeted_pytest_command(target_root, terms or [])
    if targeted:
        return targeted
    return "blocked: no existing targeted test file found during read-only planning"


def build_incremental_implementation_plan_contract(user_request: str, *, target_root: Path | None = None) -> dict[str, Any]:
    subject = implementation_subject_text(user_request)
    terms = implementation_domain_terms(user_request)
    surface = requirement_surface(subject, terms)
    behavior_label = behavior_label_for_implementation(subject, terms)
    verification_command = verification_command_for_subject(subject, target_root=target_root, terms=terms)
    change_subject = ", ".join(terms[:3])
    return {
        "kind": "incremental_implementation_plan_contract",
        "schema_version": 1,
        "phase": 115,
        "tenet_ids": PHASE115_TENET_IDS,
        "status": "ready_for_review",
        "source_request": {
            "text": subject,
            "domain_terms": terms,
                "traceability_policy": "Every changeset must trace to this request or a named verification need.",
        },
        "changesets": [
            {
                "id": "CS1",
                "title": f"Confirm {surface} implementation boundary",
                "change_type": "investigation",
                "depends_on": [],
                "objective": f"Identify the smallest source boundary for {change_subject} before drafting code.",
                "functional_outcome": f"A reviewer can point to the exact files or evidence gap for {change_subject}.",
                "isolation_boundary": {
                    "one_behavior": True,
                    "primary_file_group": "investigation_artifacts",
                    "unrelated_changes_policy": "reject",
                },
                "verification_commands": ["git status --short"],
                "acceptance_checks": [
                    f"source references or an explicit evidence gap exist for {change_subject}",
                    "no source files are changed during this planning step",
                ],
                "commit_message": {
                    "subject": commit_subject("Identify", behavior_label),
                    "body": f"Trace the implementation boundary and tests for {change_subject} before source changes.",
                    "rationale": "A separate evidence changeset keeps later implementation scope reviewable.",
                },
                "traceability": {
                    "source_request_terms": terms,
                    "proof_artifacts": ["investigation_plan", "git_status_before"],
                },
                "not_in_scope": ["source mutation", "unrelated cleanup", "broad refactor"],
            },
            {
                "id": "CS2",
                "title": f"Implement one bounded {surface} change",
                "change_type": "implementation",
                "depends_on": ["CS1"],
                "objective": f"Make only the smallest implementation change needed for {change_subject}.",
                "functional_outcome": f"The requested {surface} behavior is available behind the existing code path.",
                "isolation_boundary": {
                    "one_behavior": True,
                    "primary_file_group": "implementation_files",
                    "unrelated_changes_policy": "reject",
                },
                "verification_commands": [verification_command],
                "acceptance_checks": [
                    f"only files needed for {change_subject} are modified",
                    "targeted verification command names an existing test file or records a blocking evidence gap",
                ],
                "commit_message": {
                    "subject": commit_subject("Add", behavior_label),
                    "body": f"Implement the bounded behavior for {change_subject} without mixing unrelated cleanup.",
                    "rationale": "The implementation commit must be independently revertible and reviewable.",
                },
                "traceability": {
                    "source_request_terms": terms,
                    "proof_artifacts": ["implementation_diff", "targeted_test_output"],
                },
                "not_in_scope": ["format-only churn", "unrelated files", "implicit API expansion"],
            },
            {
                "id": "CS3",
                "title": f"Add or update tests for {surface}",
                "change_type": "test",
                "depends_on": ["CS2"],
                "objective": f"Prove expected behavior, edge case, or regression coverage for {change_subject}.",
                "functional_outcome": f"Tests fail without the {surface} behavior and pass with the bounded implementation.",
                "isolation_boundary": {
                    "one_behavior": True,
                    "primary_file_group": "test_files",
                    "unrelated_changes_policy": "reject",
                },
                "verification_commands": [verification_command],
                "acceptance_checks": [
                    "test intent names the expected behavior or regression",
                    "test command names an existing targeted test file before any broader suite is recommended",
                ],
                "commit_message": {
                    "subject": commit_subject("Cover", behavior_label),
                    "body": f"Add focused verification for {change_subject} so the implementation result is reproducible.",
                    "rationale": "The test commit records why the behavior is complete and guards regression.",
                },
                "traceability": {
                    "source_request_terms": terms,
                    "proof_artifacts": ["test_diff", "targeted_test_output"],
                },
                "not_in_scope": ["rewriting unrelated tests", "broad fixture redesign", "skipping targeted tests"],
            },
        ],
        "version_control_plan": {
            "branch_name": f"agent/{terms[0].replace('_', '-')}-implementation-plan",
            "commit_order": ["CS1", "CS2", "CS3"],
            "commit_policy": "Use one meaningful commit per isolated changeset after verification passes.",
            "traceability_artifacts": ["git status --short", "changed-file summary", "targeted test output"],
            "pre_commit_checks": ["git status --short", verification_command],
            "separation_policy": "Reject unrelated changes, generated runtime-state files, and broad refactor work from these changesets.",
        },
        "source_apply_policy": {
            "status": "blocked_in_task_decompose",
            "reason": "Phase 115 validates implementation and version-control planning only; source apply requires a later approved implementation path.",
        },
    }


def delivery_risk_controls(subject: str) -> list[str]:
    lowered = subject.lower()
    controls: list[str] = []
    if "csv" in lowered or "export" in lowered:
        controls.extend([
            "preserve existing JSON export",
            "verify filtered results source of truth",
            "check data sensitivity and permissions",
            "bound export size",
        ])
    if "archive" in lowered or "restorable" in lowered or "admin" in lowered:
        controls.extend([
            "model archive state explicitly",
            "preserve admin restore behavior",
            "filter archived records from normal lists",
            "enforce authorization server-side",
            "record auditability requirements",
        ])
    if "staging" in lowered or "500" in lowered:
        controls.extend([
            "reproduce with request ID",
            "inspect logs before naming root cause",
            "compare staging configuration and data",
            "trace request path",
        ])
    if "skip regression" in lowered or "demo" in lowered:
        controls.extend([
            "do not skip regression without reducing scope",
            "name schedule risk",
            "choose a smaller safe alternative",
            "record minimum verification bar",
        ])
    if "duplicate" in lowered or "second implementation" in lowered or "one code path" in lowered:
        controls.extend([
            "reject duplicate implementation as final state",
            "preserve one code path",
            "add characterization tests before consolidation",
            "separate readability debt from feature delivery",
        ])
    if "retry" in lowered or "payment" in lowered:
        controls.extend([
            "prove idempotency before retry",
            "avoid duplicate charges",
            "limit retry scope to safe operations",
            "classify provider error cases",
        ])
    if "bulk" in lowered or "spreadsheet" in lowered or "import" in lowered:
        controls.extend([
            "validate input before mutation",
            "define partial failure behavior",
            "enforce permissions",
            "record audit trail",
            "bound upload size or background processing",
        ])
    if "scheduled" in lowered or "weekly" in lowered or "monthly" in lowered:
        controls.extend([
            "handle time zones",
            "make scheduled jobs idempotent",
            "define retry behavior",
            "monitor delivery failures",
        ])
    if not controls:
        controls.extend([
            "bound implementation scope",
            "choose risk-based tests",
            "confirm rollback path",
            "verify observability before release",
        ])
    deduped: list[str] = []
    for item in controls:
        if item not in deduped:
            deduped.append(item)
    return deduped[:8]


def build_delivery_mentorship_contract(user_request: str, *, target_root: Path | None = None) -> dict[str, Any]:
    subject = implementation_subject_text(user_request)
    terms = implementation_domain_terms(user_request)
    surface = requirement_surface(subject, terms)
    verification_command = verification_command_for_subject(subject, target_root=target_root, terms=terms)
    return {
        "kind": "delivery_mentorship_contract",
        "schema_version": 1,
        "phase": 119,
        "tenet_ids": PHASE119_TENET_IDS,
        "status": "ready_for_review",
        "source_request": {
            "text": subject,
            "domain_terms": terms,
            "traceability_policy": "Every teaching step must trace to the requested feature, bug, or engineering practice.",
        },
        "case_specific_risk_controls": delivery_risk_controls(subject),
        "delivery_sequence": [
            {
                "id": "DM1",
                "stage": "requirement_intake",
                "mentor_action": f"Restate the requested {surface} outcome and separate known facts from assumptions.",
                "deliverable": "bounded requirement packet with objective acceptance criteria",
                "why": "Feature delivery starts by making the desired behavior reviewable before design or code.",
                "evidence_or_gate": "source request, acceptance criteria, explicit assumptions",
            },
            {
                "id": "DM2",
                "stage": "task_decomposition",
                "mentor_action": f"Split {surface} into independently reviewable investigation, implementation, test, and release-readiness work.",
                "deliverable": "short-cycle work packages with dependencies and stop conditions",
                "why": "Small packages reduce review risk and make incomplete or ambiguous work visible.",
                "evidence_or_gate": "work package list, dependency edges, approval gates",
            },
            {
                "id": "DM3",
                "stage": "implementation_planning",
                "mentor_action": f"Choose the smallest code path that can satisfy {surface} without parallel behavior.",
                "deliverable": "draft-only implementation plan or packet candidate",
                "why": "One behavior path is easier to test, review, and roll back than duplicated logic.",
                "evidence_or_gate": "single-code-path check, unrelated-changes rejection",
            },
            {
                "id": "DM4",
                "stage": "verification_strategy",
                "mentor_action": "Pick targeted tests first, then identify integration, regression, and live/manual checks that cover remaining risk.",
                "deliverable": "risk-based verification plan",
                "why": "A passing local test is not enough unless it covers the changed behavior and known regression risks.",
                "evidence_or_gate": verification_command,
            },
            {
                "id": "DM5",
                "stage": "review_feedback",
                "mentor_action": "Review correctness, maintainability, testability, scope control, and system impact before requesting approval.",
                "deliverable": "review-ready change summary with risks and tradeoffs",
                "why": "Peer review is more effective when the author has already checked the engineering standard.",
                "evidence_or_gate": "self-review checklist, changed-file summary, test output",
            },
            {
                "id": "DM6",
                "stage": "deployment_readiness",
                "mentor_action": "Confirm release boundaries, rollback, observability, documentation, and user-visible verification before calling the work done.",
                "deliverable": "deployment-readiness checklist",
                "why": "Implemented and unit-tested is not the same as ready to release.",
                "evidence_or_gate": "CI result, rollback notes, monitoring/logging check, docs impact",
            },
        ],
        "testing_strategy": {
            "tiers": [
                {
                    "tier": "unit",
                    "purpose": f"Prove the smallest behavior branch for {surface}.",
                    "example_command": verification_command,
                    "covered_risk": "local behavior regression",
                },
                {
                    "tier": "integration",
                    "purpose": "Prove the changed path works with adjacent modules, handlers, or persistence boundaries.",
                    "example_command": "blocked: choose an existing integration test after WP1 evidence is gathered",
                    "covered_risk": "contract mismatch between cooperating components",
                },
                {
                    "tier": "regression",
                    "purpose": "Run the relevant regression slice after source changes are approved and implemented.",
                    "example_command": "python -m pytest tests/regression/ -v",
                    "covered_risk": "unintended behavior drift outside the targeted change",
                },
                {
                    "tier": "live_or_manual",
                    "purpose": "Validate user-visible behavior through the same runtime path a tester will use.",
                    "example_command": "blocked: no live/manual command until an approved implementation exists",
                    "covered_risk": "deployment or harness behavior differs from local test assumptions",
                },
            ],
            "selection_rationale": "Use the smallest meaningful test first, then add broader checks only for risks not covered by the targeted test.",
        },
        "debugging_methodology": [
            "Reproduce the reported failure or expected behavior with the smallest command or request.",
            "Inspect logs, stack traces, run IDs, and configuration before naming a root cause.",
            "Compare expected versus observed data at each boundary in the request or job flow.",
            "Verify the fix with the reproduction case and at least one regression or holdout check.",
        ],
        "code_quality_practices": [
            "Keep one code path per behavior and reject duplicate implementations unless the old path is being removed in the same approved change.",
            "Use named enums or existing constants where the codebase already provides them.",
            "Keep unrelated cleanup and broad refactors outside the feature delivery changeset.",
            "Write a self-review summary before requesting peer review.",
        ],
        "development_workflow": {
            "branch_policy": "Use an isolated branch or changeset for the requested behavior.",
            "commit_policy": "Use meaningful commits that trace to one behavior and one verification result.",
            "review_policy": "Request review only after targeted verification, self-review, and known gaps are documented.",
            "feedback_policy": "Convert review feedback into bounded follow-up tasks or explicit non-blocking debt.",
        },
        "deployment_readiness": {
            "status": "readiness_review_only",
            "checks": [
                "CI and targeted tests passed",
                "migration or config changes are named, reversible, or explicitly absent",
                "observability/logging impact is known",
                "rollback or disablement path is documented",
                "user-facing documentation or release notes are updated when behavior changes",
                "live/manual verification path is identified for the tester",
            ],
            "not_ready_if": [
                "acceptance criteria are subjective",
                "authorization or data-safety risk is untested",
                "rollback is unknown for a production-impacting change",
                "the plan relies on UI-only enforcement for security behavior",
            ],
        },
        "mentorship_notes": [
            "Explain why each step exists; do not only assign tasks.",
            "Challenge unsafe shortcuts directly and offer a smaller safe alternative.",
            "Teach the engineer how to decide the test level from risk and blast radius.",
            "Keep tone direct, specific, and non-patronizing.",
        ],
        "definition_of_done": [
            "Requirement and assumptions are traceable.",
            "Implementation scope is bounded to one behavior path.",
            "Acceptance criteria and verification commands are objective.",
            "Review risks, blockers, and technical debt are documented separately.",
            "Deployment-readiness checks have evidence or explicit blockers.",
        ],
        "stop_conditions": [
            {
                "code": "missing_acceptance_criteria",
                "reason": "Stop before implementation if the expected behavior cannot be objectively checked.",
            },
            {
                "code": "approval_required_for_mutation",
                "reason": "Stop before source mutation; task.decompose is read-only and draft-only.",
            },
            {
                "code": "unsafe_quality_shortcut",
                "reason": "Do not skip required tests or review gates for schedule pressure without reducing scope.",
            },
            {
                "code": "security_or_data_boundary_unclear",
                "reason": "Stop if authorization, data export, or production-safety requirements are ambiguous.",
            },
        ],
        "source_apply_policy": {
            "status": "blocked_in_task_decompose",
            "deployment_status": "not_deployed_by_this_workflow",
            "reason": "Phase 119 teaches delivery and validates readiness planning; it does not apply source changes or deploy.",
        },
    }


def tenet_contract_for_family(family: PromptFamily, *, blocked_status: str = "audit_ready") -> dict[str, Any]:
    if family == PromptFamily.DELIVERY_MENTORSHIP:
        return {
            "phase": 119,
            "tenet_ids": PHASE119_TENET_IDS,
            "status": blocked_status,
            "requires_end_to_end_delivery_sequence": True,
            "requires_testing_strategy": True,
            "requires_debugging_methodology": True,
            "requires_code_quality_practices": True,
            "requires_deployment_readiness_boundary": True,
            "requires_mentorship_notes": True,
            "source_apply_policy": "blocked_in_task_decompose",
        }
    if family == PromptFamily.INCREMENTAL_IMPLEMENTATION_PLAN:
        return {
            "phase": 115,
            "tenet_ids": PHASE115_TENET_IDS,
            "status": blocked_status,
            "requires_isolated_changesets": True,
            "requires_functional_outcomes": True,
            "requires_verification_commands": True,
            "requires_meaningful_commit_messages": True,
            "source_apply_policy": "blocked_in_task_decompose",
        }
    if family == PromptFamily.REQUIREMENTS_TRANSLATION:
        return {
            "phase": 114,
            "tenet_ids": PHASE114_TENET_IDS,
            "status": blocked_status,
            "requires_business_requirement_traceability": True,
            "requires_rejected_assumptions": True,
            "requires_estimate_assumptions": True,
            "requires_revision_triggers": True,
            "unsupported_assumption_policy": "reject_or_clarify_before_implementation_prep",
        }
    return {
        "phase": 113,
        "tenet_ids": PHASE113_TENET_IDS,
        "status": blocked_status,
        "acceptance_criteria_required": True,
        "max_ready_work_packages": MAX_READY_WORK_PACKAGES,
        "requires_independent_review_boundary": True,
        "unsupported_implementation_claim_policy": "no_source_apply_from_task_decompose",
    }


def scope_boundary_for(package_id: str) -> dict[str, Any]:
    boundaries = {
        "WP1": {
            "review_boundary": "Review only the investigation artifact and evidence gaps before approving any downstream prep.",
            "not_in_scope": ["source edits", "implementation packet creation", "test execution"],
        },
        "GATE2": {
            "review_boundary": "Review only whether the WP1 run is specific enough to authorize draft packet design.",
            "not_in_scope": ["implicit approval", "source edits", "new implementation scope"],
        },
        "WP3": {
            "review_boundary": "Review only draft packet candidates, allowed operations, and attached verification commands.",
            "not_in_scope": ["source apply", "repository mutation", "unbounded refactor planning"],
        },
        "WP4": {
            "review_boundary": "Review only readiness evidence for the draft packet and verification plan.",
            "not_in_scope": ["approving source apply", "changing package scope", "running unrelated test suites"],
        },
        "STOP5": {
            "review_boundary": "Review only whether a separate source-apply approval should be requested.",
            "not_in_scope": ["automatic apply", "approval reuse", "source mutation inside task.decompose"],
        },
        "DEFER1": {
            "review_boundary": "Review only the deferral reason and the smaller prompt family to use instead.",
            "not_in_scope": ["advanced refactor execution", "implementation packet creation", "source mutation"],
        },
    }
    boundary = boundaries.get(
        package_id,
        {
            "review_boundary": "Review the package artifact before starting dependent work.",
            "not_in_scope": ["source mutation without approval", "unbounded scope expansion"],
        },
    )
    return {
        "independently_reviewable": True,
        "estimated_cycle": "short",
        "review_boundary": boundary["review_boundary"],
        "not_in_scope": boundary["not_in_scope"],
    }


def acceptance_criteria_for(
    package_id: str,
    *,
    expected_artifacts: list[str],
    exit_criteria: list[str],
    verification: dict[str, Any],
) -> list[dict[str, Any]]:
    artifact_name = expected_artifacts[0] if expected_artifacts else "task_decomposition"
    templates = {
        "WP1": [
            (
                "evidence-bounded",
                "WP1 is complete only when the investigation artifact records an entry point or an explicit evidence gap.",
                ["investigation_plan.entrypoint_candidates", "investigation_plan.evidence_gaps"],
                "Inspect the WP1 investigation artifact.",
                "An entry point or named evidence gap is present.",
            ),
            (
                "test-scope-bounded",
                "WP1 is complete only when related tests or a no-related-test gap are recorded.",
                ["investigation_plan.related_tests", "investigation_plan.verification_commands"],
                "Inspect the WP1 investigation artifact.",
                "Related tests, a smallest useful test command, or an explicit test gap is present.",
            ),
        ],
        "GATE2": [
            (
                "approval-scoped",
                "GATE2 is complete only when approval is recorded for packet design from the specific WP1 run.",
                ["approval_record.target_root", "approval_record.source_run_id", "approval_record.scope"],
                "Inspect the approval record before WP3 starts.",
                "Approval scope is packet_design_only and matches the WP1 target root and run identity.",
            )
        ],
        "WP3": [
            (
                "draft-only-packet",
                "WP3 is complete only when packet candidates are draft-only and include allowed operations.",
                ["packet_file.allowed_operations", "implementation_draft.mutation_policy"],
                "Inspect the draft implementation packet.",
                "The packet contains bounded operations and does not apply source changes.",
            ),
            (
                "verification-attached",
                "WP3 is complete only when verification commands or an explicit verification gap are attached.",
                ["verification_plan.commands", "verification_plan.explicit_gap"],
                "Inspect the draft verification plan.",
                "At least one command or explicit verification gap is present.",
            ),
        ],
        "WP4": [
            (
                "readiness-reviewed",
                "WP4 is complete only when the draft packet and verification plan have been reviewed together.",
                ["verification_review.packet_scope", "verification_review.commands"],
                "Inspect the verification review artifact.",
                "The review records packet readiness or a named blocker.",
            ),
            (
                "no-source-mutation",
                "WP4 is complete only when mutation proof shows source files stayed unchanged.",
                ["verification_review.target_repository_changed"],
                "Inspect mutation proof fields.",
                "target_repository_changed is false.",
            ),
        ],
        "STOP5": [
            (
                "separate-apply-approval",
                "STOP5 is complete only when source apply remains blocked unless a separate approval is recorded.",
                ["approval_record.scope", "approval_record.source_run_id"],
                "Inspect the terminal approval boundary.",
                "No apply proceeds from task.decompose; any apply approval is separate and run-bound.",
            )
        ],
        "DEFER1": [
            (
                "deferred-without-execution",
                "DEFER1 is complete only when the advanced refactor request is blocked without executable packages.",
                ["task_decomposition.status", "task_decomposition.selected_workflow_ids"],
                "Inspect the blocked decomposition artifact.",
                "status is blocked and selected_workflow_ids is empty.",
            )
        ],
    }
    selected = templates.get(
        package_id,
        [
            (
                "artifact-proven",
                exit_criteria[0] if exit_criteria else "Package completion must be proven by a named artifact.",
                [artifact_name],
                "Inspect the named package artifact.",
                verification.get("status", "package artifact is present"),
            )
        ],
    )
    criteria: list[dict[str, Any]] = []
    for index, (suffix, description, evidence_required, method, signal) in enumerate(selected, start=1):
        criteria.append(
            {
                "id": f"AC-{package_id}-{index}",
                "name": suffix,
                "description": description,
                "evidence_required": evidence_required,
                "verification_method": method,
                "completion_signal": signal,
                "objectivity": {
                    "observable_outcome": signal,
                    "evidence_source": evidence_required[0],
                    "pass_fail_rule": "Pass only when the named evidence is present; otherwise fail or request clarification.",
                },
                "requires_source_mutation": False,
            }
        )
    return criteria


def package(
    package_id: str,
    *,
    title: str,
    workflow_id: str,
    stage: WorkPackageStage,
    objective: str,
    depends_on: list[str],
    blocks: list[str],
    workflows: dict[str, dict[str, Any]],
    skills: dict[str, dict[str, Any]],
    request_text: str,
    approval_required: bool,
    approval_scope: str,
    mutation_policy: MutationPolicy,
    entry_conditions: list[str],
    exit_criteria: list[str],
    stop_conditions: list[dict[str, str]],
    expected_artifacts: list[str],
    verification: dict[str, Any],
) -> dict[str, Any]:
    workflow = workflows[workflow_id]
    return {
        "id": package_id,
        "title": title,
        "stage": stage.value,
        "workflow_id": workflow_id,
        "objective": objective,
        "depends_on": depends_on,
        "dependency_contract": {
            "depends_on": depends_on,
            "blocks": blocks,
            "can_start_when": "all_dependencies_complete",
            "parallelizable": False,
        },
        "selected_tools": workflow_tool_ids(workflow),
        "selected_skills": skill_ids_for_workflow(skills, workflow_id, request_text),
        "approval_gate": {
            "required": approval_required,
            "scope": approval_scope,
            "decision_options": ["approve", "deny"] if approval_required else [],
        },
        "approval_required": approval_required,
        "mutation_policy": mutation_policy.value,
        "entry_conditions": entry_conditions,
        "exit_criteria": exit_criteria,
        "acceptance_criteria": acceptance_criteria_for(
            package_id,
            expected_artifacts=expected_artifacts,
            exit_criteria=exit_criteria,
            verification=verification,
        ),
        "scope_boundary": scope_boundary_for(package_id),
        "stop_conditions": stop_conditions,
        "expected_artifacts": expected_artifacts,
        "verification": verification,
        "uncertainty": [
            {
                "code": "repo_evidence_not_read",
                "reason": "task.decompose does not inspect source files; this package must gather or validate repo evidence.",
            }
        ],
    }


def gate_package(
    package_id: str,
    *,
    title: str,
    stage: WorkPackageStage,
    objective: str,
    depends_on: list[str],
    blocks: list[str],
    approval_scope: str,
    decision_options: list[str],
    mutation_policy: MutationPolicy,
    entry_conditions: list[str],
    exit_criteria: list[str],
    stop_conditions: list[dict[str, str]],
    expected_artifacts: list[str],
    verification: dict[str, Any],
    uncertainty: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "id": package_id,
        "title": title,
        "stage": stage.value,
        "workflow_id": None,
        "objective": objective,
        "depends_on": depends_on,
        "dependency_contract": {
            "depends_on": depends_on,
            "blocks": blocks,
            "can_start_when": "all_dependencies_complete",
            "parallelizable": False,
        },
        "selected_tools": [],
        "selected_skills": [],
        "approval_gate": {
            "required": True,
            "scope": approval_scope,
            "decision_options": decision_options,
        },
        "approval_required": True,
        "mutation_policy": mutation_policy.value,
        "entry_conditions": entry_conditions,
        "exit_criteria": exit_criteria,
        "acceptance_criteria": acceptance_criteria_for(
            package_id,
            expected_artifacts=expected_artifacts,
            exit_criteria=exit_criteria,
            verification=verification,
        ),
        "scope_boundary": scope_boundary_for(package_id),
        "stop_conditions": stop_conditions,
        "expected_artifacts": expected_artifacts,
        "verification": verification,
        "uncertainty": uncertainty or [],
    }


def manual_package(
    package_id: str,
    *,
    title: str,
    stage: WorkPackageStage,
    objective: str,
    depends_on: list[str],
    blocks: list[str],
    mutation_policy: MutationPolicy,
    entry_conditions: list[str],
    exit_criteria: list[str],
    stop_conditions: list[dict[str, str]],
    expected_artifacts: list[str],
    verification: dict[str, Any],
    uncertainty: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "id": package_id,
        "title": title,
        "stage": stage.value,
        "workflow_id": None,
        "objective": objective,
        "depends_on": depends_on,
        "dependency_contract": {
            "depends_on": depends_on,
            "blocks": blocks,
            "can_start_when": "all_dependencies_complete",
            "parallelizable": False,
        },
        "selected_tools": [],
        "selected_skills": [],
        "approval_gate": {
            "required": False,
            "scope": "none",
            "decision_options": [],
        },
        "approval_required": False,
        "mutation_policy": mutation_policy.value,
        "entry_conditions": entry_conditions,
        "exit_criteria": exit_criteria,
        "acceptance_criteria": acceptance_criteria_for(
            package_id,
            expected_artifacts=expected_artifacts,
            exit_criteria=exit_criteria,
            verification=verification,
        ),
        "scope_boundary": scope_boundary_for(package_id),
        "stop_conditions": stop_conditions,
        "expected_artifacts": expected_artifacts,
        "verification": verification,
        "uncertainty": uncertainty or [],
    }


def advanced_refactor_deferred_package() -> list[dict[str, Any]]:
    return [
        manual_package(
            "DEFER1",
            title="Advanced refactor orchestration deferred",
            stage=WorkPackageStage.TERMINAL_STOP,
            objective="Stop broad single-path refactor orchestration until the Phase 105 readiness gate is explicitly satisfied.",
            depends_on=[],
            blocks=[],
            mutation_policy=MutationPolicy.UNSUPPORTED_DEFERRED,
            entry_conditions=["request asks for broad single-path or one-code-path refactor orchestration"],
            exit_criteria=["advanced refactor readiness is explicitly approved in Phase 105"],
            stop_conditions=[
                {
                    "code": "phase_105_not_ready",
                    "reason": "Do not create implementation prep or source-apply packages for broad refactor prompts yet.",
                },
                {
                    "code": "unsupported_refactor_orchestration",
                    "reason": "Use smaller L1/L2 investigation and change-surface prompts before advanced orchestration.",
                },
            ],
            expected_artifacts=[],
            verification={
                "commands": [],
                "proof_gates": ["confirm no implementation packet artifacts were created"],
                "status": "blocked_deferred_scope",
            },
            uncertainty=[
                {
                    "code": "advanced_refactor_deferred",
                    "reason": "Phase 102 plans multi-step work packages but does not enable broad refactor execution.",
                }
            ],
        )
    ]


def build_work_packages(
    *,
    family: PromptFamily,
    workflows: dict[str, dict[str, Any]],
    skills: dict[str, dict[str, Any]],
    request_text: str,
) -> list[dict[str, Any]]:
    if family == PromptFamily.ADVANCED_REFACTOR_DEFERRED:
        return advanced_refactor_deferred_package()

    packages: list[dict[str, Any]] = []
    packages.append(
        package(
            "WP1",
            title="Gather bounded repository evidence",
            workflow_id="code_investigation.plan",
            stage=WorkPackageStage.INVESTIGATION,
            objective="Find beginning points, participating files, related tests, risks, and verification commands.",
            depends_on=[],
            blocks=["GATE2"],
            workflows=workflows,
            skills=skills,
            request_text=request_text,
            approval_required=False,
            approval_scope="none",
            mutation_policy=MutationPolicy.READ_ONLY,
            entry_conditions=["request is specific enough to locate behavior, file, test, or desired outcome"],
            exit_criteria=[
                "entry point or explicit evidence gap is recorded",
                "related files and tests are bounded",
                "smallest useful verification command is proposed",
            ],
            stop_conditions=[
                {
                    "code": "no_repo_evidence",
                    "reason": "Stop if the investigation cannot identify evidence for the requested behavior.",
                },
                {
                    "code": "scope_too_large",
                    "reason": "Stop if the task expands beyond a bounded L1/L2 workflow or approved package.",
                },
            ],
            expected_artifacts=["investigation_plan"],
            verification={
                "commands": [],
                "proof_gates": ["inspect investigation evidence", "confirm selected tests are relevant"],
                "status": "pending_wp1_execution",
            },
        )
    )
    packages.append(
        gate_package(
            "GATE2",
            title="Approval gate before implementation prep",
            stage=WorkPackageStage.PREP_APPROVAL_GATE,
            objective="Stop after investigation until the caller approves draft-only implementation planning from the specific WP1 result.",
            depends_on=["WP1"],
            blocks=["WP3"],
            approval_scope="packet_design_only",
            decision_options=["approve_packet_design", "deny", "request_more_investigation"],
            mutation_policy=MutationPolicy.READ_ONLY,
            entry_conditions=["WP1 evidence has been reviewed"],
            exit_criteria=["approval decision is recorded with target root and source run identity"],
            stop_conditions=[
                {
                    "code": "missing_packet_design_approval",
                    "reason": "Stop until approval.status=approved_for_packet_design is present.",
                },
                {
                    "code": "evidence_not_reviewed",
                    "reason": "Stop if WP1 evidence has not been reviewed by the caller.",
                },
            ],
            expected_artifacts=["approval_record"],
            verification={
                "commands": [],
                "proof_gates": ["confirm approval is scoped to WP1 run identity"],
                "status": "waiting_for_approval",
            },
        )
    )
    packages.append(
        package(
            "WP3",
            title="Draft implementation packet plan",
            workflow_id="execution_planning.plan",
            stage=WorkPackageStage.IMPLEMENTATION_PREP,
            objective="Convert approved evidence into bounded draft packet candidates without applying source changes.",
            depends_on=["GATE2"],
            blocks=["WP4"],
            workflows=workflows,
            skills=skills,
            request_text=request_text,
            approval_required=False,
            approval_scope="preapproved_by_gate2",
            mutation_policy=MutationPolicy.DRAFT_ONLY_UNTIL_APPROVAL,
            entry_conditions=[
                "WP1 completed with bounded evidence",
                "GATE2 approval is recorded for packet design only",
            ],
            exit_criteria=[
                "packet objective is narrow",
                "candidate operations are draft-only",
                "verification commands are attached to the packet design",
            ],
            stop_conditions=[
                {
                    "code": "missing_packet_design_approval",
                    "reason": "Stop if approval.status=approved_for_packet_design is missing or references the wrong run.",
                },
                {
                    "code": "source_apply_requested",
                    "reason": "Stop if the request asks to mutate source files during implementation prep.",
                },
            ],
            expected_artifacts=["packet_file", "verification_plan", "implementation_draft"],
            verification={
                "commands": [],
                "proof_gates": ["inspect packet preview", "confirm no source files changed"],
                "status": "pending_approval_and_wp3_execution",
            },
        )
    )
    packages.append(
        manual_package(
            "WP4",
            title="Verify package readiness",
            stage=WorkPackageStage.VERIFICATION,
            objective="Review the draft plan, attached verification commands, and mutation proof before any apply decision.",
            depends_on=["WP3"],
            blocks=["STOP5"],
            mutation_policy=MutationPolicy.READ_ONLY,
            entry_conditions=["WP3 draft package plan exists"],
            exit_criteria=[
                "verification commands are present or an explicit gap is recorded",
                "draft package remains source-non-mutating",
                "review result is ready for an apply approval decision",
            ],
            stop_conditions=[
                {
                    "code": "verification_missing",
                    "reason": "Stop if no smallest useful verification command or explicit verification gap exists.",
                },
                {
                    "code": "draft_mutated_source",
                    "reason": "Stop if implementation prep changed repository files.",
                },
            ],
            expected_artifacts=["verification_review"],
            verification={
                "commands": [],
                "proof_gates": ["inspect WP3 verification plan", "confirm target_repository_changed=false"],
                "status": "pending_wp3_execution",
            },
        )
    )
    packages.append(
        gate_package(
            "STOP5",
            title="Stop before repository mutation",
            stage=WorkPackageStage.TERMINAL_STOP,
            objective="End this decomposition before source mutation; source apply requires a separate approved implementation workflow.",
            depends_on=["WP4"],
            blocks=[],
            approval_scope="repository_mutation",
            decision_options=["approve_apply_in_disposable_copy", "deny", "request_new_plan"],
            mutation_policy=MutationPolicy.MUTATION_BLOCKED,
            entry_conditions=["WP4 readiness review is complete", "caller asks to continue beyond draft-only prep"],
            exit_criteria=["separate source-apply approval is recorded with matching target root and run id"],
            stop_conditions=[
                {
                    "code": "missing_apply_approval",
                    "reason": "Stop until a separate source-apply approval is present.",
                },
                {
                    "code": "target_mismatch",
                    "reason": "Stop if the approval target differs from the planned target root.",
                },
            ],
            expected_artifacts=["approval_record"],
            verification={
                "commands": [],
                "proof_gates": ["confirm approval run identity", "confirm mutation policy before apply"],
                "status": "pending_separate_apply_approval",
            },
            uncertainty=[
                {
                    "code": "source_apply_not_part_of_task_decompose",
                    "reason": "task.decompose only plans; it does not apply repository changes.",
                }
            ],
        )
    )
    return packages


def dependency_edges(work_packages: list[dict[str, Any]]) -> list[dict[str, str]]:
    edges: list[dict[str, str]] = []
    for item in work_packages:
        package_id = item.get("id")
        for dependency in string_list(item.get("depends_on")):
            if isinstance(package_id, str):
                edges.append({"from": dependency, "to": package_id})
    return edges


def selected_values(work_packages: list[dict[str, Any]], key: str) -> list[str]:
    values: list[str] = []
    for item in work_packages:
        for value in string_list(item.get(key)):
            if value not in values:
                values.append(value)
    return values


def selected_workflow_ids(work_packages: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for item in work_packages:
        workflow_id = item.get("workflow_id")
        if isinstance(workflow_id, str) and workflow_id and workflow_id not in values:
            values.append(workflow_id)
    return values


def approval_gates_for(work_packages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gates: list[dict[str, Any]] = []
    for item in work_packages:
        if not isinstance(item, dict):
            continue
        gate = item.get("approval_gate")
        if not isinstance(gate, dict) or gate.get("required") is not True:
            continue
        package_id = item.get("id")
        if not isinstance(package_id, str):
            continue
        gates.append(
            {
                "id": f"approval_for_{package_id.lower()}",
                "package_id": package_id,
                "required_before": item.get("workflow_id") or package_id,
                "approval_scope": gate.get("scope"),
                "decision_options": gate.get("decision_options")
                if isinstance(gate.get("decision_options"), list)
                else [],
            }
        )
    return gates


def validate_registered_references(plan: dict[str, Any], workflows: dict[str, dict[str, Any]], skills: dict[str, dict[str, Any]], tools: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for item in plan.get("work_packages", []):
        if not isinstance(item, dict):
            continue
        workflow_id = item.get("workflow_id")
        if isinstance(workflow_id, str) and workflow_id not in workflows:
            errors.append({"code": "unknown_workflow", "value": workflow_id})
        for skill_id in string_list(item.get("selected_skills")):
            if skill_id not in skills:
                errors.append({"code": "unknown_skill", "value": skill_id})
        for tool_id in string_list(item.get("selected_tools")):
            if tool_id not in tools:
                errors.append({"code": "unknown_tool", "value": tool_id})
    return errors


def build_decomposition(request: TaskDecompositionRequest) -> dict[str, Any]:
    config_root = Path(request.config_root).resolve()
    workflows = load_workflows(config_root)
    skills = load_skills(config_root)
    tools = load_tools(config_root)
    text = lower_text(request.user_request)
    family, risk_level = classify_prompt_family(request.user_request)

    if is_ambiguous_request(request.user_request):
        return {
            "kind": "task_decomposition",
            "schema_version": SCHEMA_VERSION,
            "work_package_schema_version": WORK_PACKAGE_SCHEMA_VERSION,
            "workflow": WORKFLOW_ID,
            "status": DecompositionStatus.NEEDS_CLARIFICATION.value,
            "prompt_family": PromptFamily.AMBIGUOUS.value,
            "risk_level": RiskLevel.UNKNOWN.value,
            "target_root": str(Path(request.target_root).resolve()),
            "user_request": request.user_request,
            "work_packages": [],
            "dependency_edges": [],
            "selected_workflow_ids": [],
            "selected_skill_ids": [],
            "selected_tool_ids": [],
            "approval_gates": [],
            "verification_strategy": {
                "status": "blocked",
                "commands": [],
                "proof_gates": [],
                "reason": "The task is too ambiguous to decompose safely.",
            },
            "tenet_contract": {
                "phase": 113,
                "tenet_ids": PHASE113_TENET_IDS,
                "status": "blocked_until_clarified",
                "acceptance_criteria_required": True,
                "max_ready_work_packages": MAX_READY_WORK_PACKAGES,
            },
            "uncertainty": [
                {
                    "code": "ambiguous_task",
                    "reason": "Name the behavior, failing test, file, or desired outcome before decomposition.",
                }
            ],
            "blockers": [{"reason": "ambiguous_task", "message": "Clarify the requested behavior or outcome."}],
            "next_action": NextAction.ASK_BLOCKING_QUESTION.value,
            "mutation_policy": MutationPolicy.READ_ONLY.value,
            "runtime_registry_changed": False,
            "target_repository_changed": False,
        }

    if is_oversized_request(request.user_request):
        return {
            "kind": "task_decomposition",
            "schema_version": SCHEMA_VERSION,
            "work_package_schema_version": WORK_PACKAGE_SCHEMA_VERSION,
            "workflow": WORKFLOW_ID,
            "status": DecompositionStatus.NEEDS_CLARIFICATION.value,
            "prompt_family": PromptFamily.OVERSIZED.value,
            "risk_level": RiskLevel.HIGH.value,
            "target_root": str(Path(request.target_root).resolve()),
            "user_request": request.user_request,
            "work_packages": [],
            "dependency_edges": [],
            "selected_workflow_ids": [],
            "selected_skill_ids": [],
            "selected_tool_ids": [],
            "approval_gates": [],
            "verification_strategy": {
                "status": "blocked",
                "commands": [],
                "proof_gates": [],
                "reason": "The requested scope is too broad for independently reviewable short-cycle packages.",
            },
            "tenet_contract": {
                "phase": 113,
                "tenet_ids": PHASE113_TENET_IDS,
                "status": "blocked_until_decomposed_further",
                "acceptance_criteria_required": True,
                "max_ready_work_packages": MAX_READY_WORK_PACKAGES,
            },
            "uncertainty": [
                {
                    "code": "oversized_task",
                    "reason": "Choose one feature, bug, requirement, file, or behavior before implementation planning.",
                }
            ],
            "blockers": [
                {
                    "reason": "oversized_task",
                    "message": "Narrow the request to one feature, bug, requirement, file, or behavior.",
                }
            ],
            "decomposition_guidance": [
                "Pick one user-visible behavior or failing test.",
                "Name the target file, route, function, or requirement if known.",
                "Ask for a new decomposition after narrowing scope.",
            ],
            "next_action": NextAction.ASK_BLOCKING_QUESTION.value,
            "mutation_policy": MutationPolicy.READ_ONLY.value,
            "runtime_registry_changed": False,
            "target_repository_changed": False,
        }

    work_packages = build_work_packages(family=family, workflows=workflows, skills=skills, request_text=text)
    is_deferred_advanced_refactor = family == PromptFamily.ADVANCED_REFACTOR_DEFERRED
    requirements_translation = (
        build_requirements_translation_contract(request.user_request)
        if family == PromptFamily.REQUIREMENTS_TRANSLATION
        else None
    )
    incremental_implementation_plan = (
        build_incremental_implementation_plan_contract(request.user_request, target_root=Path(request.target_root).resolve())
        if family == PromptFamily.INCREMENTAL_IMPLEMENTATION_PLAN
        else None
    )
    delivery_mentorship = (
        build_delivery_mentorship_contract(request.user_request, target_root=Path(request.target_root).resolve())
        if family == PromptFamily.DELIVERY_MENTORSHIP
        else None
    )
    plan = {
        "kind": "task_decomposition",
        "schema_version": SCHEMA_VERSION,
        "work_package_schema_version": WORK_PACKAGE_SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "status": DecompositionStatus.BLOCKED.value if is_deferred_advanced_refactor else DecompositionStatus.READY.value,
        "prompt_family": family.value,
        "risk_level": risk_level.value,
        "target_root": str(Path(request.target_root).resolve()),
        "user_request": request.user_request,
        "work_packages": work_packages,
        "dependency_edges": dependency_edges(work_packages),
        "selected_workflow_ids": selected_workflow_ids(work_packages),
        "selected_skill_ids": selected_values(work_packages, "selected_skills"),
        "selected_tool_ids": selected_values(work_packages, "selected_tools"),
        "approval_gates": approval_gates_for(work_packages),
        "tenet_contract": tenet_contract_for_family(
            family,
            blocked_status="blocked_deferred_scope" if is_deferred_advanced_refactor else "audit_ready",
        ),
        "verification_strategy": {
            "status": "blocked_deferred_scope" if is_deferred_advanced_refactor else "pending_repo_evidence",
            "commands": [],
            "proof_gates": (
                ["confirm no implementation packet artifacts were created"]
                if is_deferred_advanced_refactor
                else [
                    "review source business requirements and derived technical requirements",
                    "review explicit and rejected assumptions before implementation prep",
                    "review effort estimate assumptions and revision triggers",
                ]
                if family == PromptFamily.REQUIREMENTS_TRANSLATION
                else [
                    "review isolated changesets",
                    "confirm each changeset has a functional outcome",
                    "confirm verification commands are targeted",
                    "confirm commit messages are meaningful and traceable",
                ]
                if family == PromptFamily.INCREMENTAL_IMPLEMENTATION_PLAN
                else [
                    "review delivery sequence from requirement intake through deployment readiness",
                    "confirm testing strategy includes targeted, regression, and live/manual tiers",
                    "confirm mentorship notes explain why each step exists",
                    "confirm source apply and deployment are blocked in task.decompose",
                ]
                if family == PromptFamily.DELIVERY_MENTORSHIP
                else [
                "run WP1 read-only evidence workflow",
                "derive smallest related test command from WP1 artifacts",
                    "run full regression only after an approved implementation phase changes code",
                ]
            ),
            "reason": (
                "Advanced refactor orchestration is deferred until Phase 105 readiness."
                if is_deferred_advanced_refactor
                else "Requirements translation is ready for review; source evidence still comes from WP1."
                if family == PromptFamily.REQUIREMENTS_TRANSLATION
                else "Incremental implementation plan is ready for review; source apply remains blocked."
                if family == PromptFamily.INCREMENTAL_IMPLEMENTATION_PLAN
                else "Delivery mentorship plan is ready for review; source apply and deployment remain blocked."
                if family == PromptFamily.DELIVERY_MENTORSHIP
                else "No source files were read by task.decompose."
            ),
        },
        "uncertainty": (
            [
                {
                    "code": "advanced_refactor_deferred",
                    "reason": "Broad single-path refactor orchestration remains deferred until Phase 105 readiness.",
                }
            ]
            if is_deferred_advanced_refactor
            else [
            {
                "code": "repo_evidence_not_read",
                "reason": "This workflow uses registry metadata only. Run the first work package to gather source evidence.",
            }
            ]
        ),
        "blockers": (
            [
                {
                    "reason": "advanced_refactor_deferred",
                    "message": "Use smaller L1/L2 investigation and change-surface prompts until Phase 105 readiness is complete.",
                }
            ]
            if is_deferred_advanced_refactor
            else []
        ),
        "deferred_to_phase": 105 if is_deferred_advanced_refactor else None,
        "next_action": NextAction.NONE.value if is_deferred_advanced_refactor else NextAction.EXECUTE_READ_ONLY.value,
        "mutation_policy": (
            MutationPolicy.UNSUPPORTED_DEFERRED.value if is_deferred_advanced_refactor else MutationPolicy.READ_ONLY.value
        ),
        "runtime_registry_changed": False,
        "target_repository_changed": False,
    }
    if requirements_translation is not None:
        plan["requirements_translation"] = requirements_translation
    if incremental_implementation_plan is not None:
        plan["incremental_implementation_plan"] = incremental_implementation_plan
    if delivery_mentorship is not None:
        plan["delivery_mentorship"] = delivery_mentorship
    reference_errors = validate_registered_references(plan, workflows, skills, tools)
    if reference_errors:
        plan["status"] = DecompositionStatus.BLOCKED.value
        plan["blockers"] = [{"reason": "unregistered_reference", "message": json.dumps(reference_errors, ensure_ascii=True)}]
        plan["next_action"] = NextAction.NONE.value
    return plan


def summary_for(plan: dict[str, Any]) -> dict[str, Any]:
    requirements_translation = (
        plan.get("requirements_translation")
        if isinstance(plan.get("requirements_translation"), dict)
        else {}
    )
    effort_estimate = (
        requirements_translation.get("effort_estimate")
        if isinstance(requirements_translation.get("effort_estimate"), dict)
        else {}
    )
    incremental_implementation_plan = (
        plan.get("incremental_implementation_plan")
        if isinstance(plan.get("incremental_implementation_plan"), dict)
        else {}
    )
    changesets = (
        incremental_implementation_plan.get("changesets")
        if isinstance(incremental_implementation_plan.get("changesets"), list)
        else []
    )
    delivery_mentorship = (
        plan.get("delivery_mentorship")
        if isinstance(plan.get("delivery_mentorship"), dict)
        else {}
    )
    delivery_sequence = (
        delivery_mentorship.get("delivery_sequence")
        if isinstance(delivery_mentorship.get("delivery_sequence"), list)
        else []
    )
    mentorship_notes = (
        delivery_mentorship.get("mentorship_notes")
        if isinstance(delivery_mentorship.get("mentorship_notes"), list)
        else []
    )
    return {
        "decomposition_status": plan.get("status"),
        "prompt_family": plan.get("prompt_family"),
        "risk_level": plan.get("risk_level"),
        "package_count": len(plan.get("work_packages", [])) if isinstance(plan.get("work_packages"), list) else 0,
        "selected_workflow_ids": plan.get("selected_workflow_ids", []),
        "selected_skill_ids": plan.get("selected_skill_ids", []),
        "selected_tool_ids": plan.get("selected_tool_ids", []),
        "approval_gate_count": len(plan.get("approval_gates", [])) if isinstance(plan.get("approval_gates"), list) else 0,
        "uncertainty_count": len(plan.get("uncertainty", [])) if isinstance(plan.get("uncertainty"), list) else 0,
        "next_action": plan.get("next_action"),
        "requirements_translation_status": requirements_translation.get("status"),
        "effort_estimate_band": effort_estimate.get("estimate_band"),
        "effort_estimate_confidence": effort_estimate.get("confidence"),
        "incremental_plan_status": incremental_implementation_plan.get("status"),
        "changeset_count": len(changesets),
        "delivery_mentorship_status": delivery_mentorship.get("status"),
        "delivery_sequence_count": len(delivery_sequence),
        "mentorship_note_count": len(mentorship_notes),
        "runtime_registry_changed": False,
        "target_repository_changed": False,
    }


def invoke_task_decomposition(request: TaskDecompositionRequest) -> InvocationResult:
    validate_request(request)
    output_root = Path(request.output_root).resolve()
    run_id = f"task-decomposition-{artifact_timestamp()}"
    run_dir = output_root / DEFAULT_OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    request_artifact = {
        "kind": "task_decomposition_request",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "target_root": str(Path(request.target_root).resolve()),
        "user_request": request.user_request,
        "metadata": request.metadata,
        "created_at": utc_now(),
    }
    write_json(run_dir / "request.json", request_artifact)

    plan = build_decomposition(request)
    plan["run_id"] = run_id
    plan["created_at"] = utc_now()
    write_json(run_dir / "task-decomposition.json", plan)
    summary = summary_for(plan)
    status = WorkflowStatus.COMPLETED
    artifacts = {
        "request": str(run_dir / "request.json"),
        "task_decomposition": str(run_dir / "task-decomposition.json"),
    }
    run_state = {
        "kind": "task_decomposition_run_state",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": status.value,
        "summary": summary,
        "artifacts": artifacts,
        "updated_at": utc_now(),
    }
    write_json(run_dir / "run-state.json", run_state)
    artifacts["run_state"] = str(run_dir / "run-state.json")
    report = {
        "kind": "task_decomposition_report",
        "schema_version": SCHEMA_VERSION,
        "workflow": WORKFLOW_ID,
        "run_id": run_id,
        "status": status.value,
        "summary": summary,
        "task_decomposition": plan,
        "artifacts": artifacts,
        "warnings": [],
        "failures": [],
    }
    return InvocationResult(
        workflow=WORKFLOW_ID,
        status=status,
        artifact_paths=artifacts,
        summary_text=f"{WORKFLOW_ID} completed with decomposition_status={summary['decomposition_status']}",
        failures=[],
        resume_key={"schema_version": SCHEMA_VERSION, "run_state": str(run_dir / "run-state.json")},
        report=report,
        run_id=run_id,
    )
