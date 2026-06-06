"""Canonical skill registry validation and metadata-only selection."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


SKILL_REGISTRY_PATH = Path("runtime") / "skills.json"
SCHEMA_VERSION = 1
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
SAFETY_LEVELS = {
    "read_only_planning",
    "read_only_context_request",
    "approval_gated_packet_design",
    "feedback_only",
}
EVAL_STATUSES = {"draft", "validated", "deprecated"}
APPROVAL_BOUNDARIES = {
    "none",
    "packet_design_required",
    "feedback_only",
}
MUTATION_POLICIES = {
    "no_repository_mutation",
    "draft_artifacts_only",
    "controller_artifacts_only",
}
ROUTE_KEY_NAMESPACES = {
    "code",
    "config",
    "context",
    "data",
    "diagnostics",
    "docs",
    "draft",
    "feedback",
    "git",
    "implementation",
    "planning",
    "test",
    "verification",
}
STRICT_ROUTE_NAMESPACE_RULES = {
    "draft": {
        "workflows": {"execution_planning.plan"},
        "mutation_policy": "draft_artifacts_only",
        "approval_boundary": "packet_design_required",
        "safety_level": "approval_gated_packet_design",
    },
    "implementation": {
        "workflows": {"execution_planning.plan"},
        "mutation_policy": "draft_artifacts_only",
        "approval_boundary": "packet_design_required",
        "safety_level": "approval_gated_packet_design",
    },
    "feedback": {
        "workflows": {"workflow_feedback.record"},
        "mutation_policy": "controller_artifacts_only",
        "approval_boundary": "feedback_only",
        "safety_level": "feedback_only",
    },
}
DEPRECATION_REQUIRED_FIELDS = {"replaced_by", "reason", "effective_date"}
INTENT_STOPWORDS = {
    "a",
    "and",
    "by",
    "for",
    "from",
    "in",
    "of",
    "or",
    "the",
    "to",
}
WORKFLOW_MUTATION_POLICY_ALLOWLIST = {
    "code_context.lookup": {"no_repository_mutation"},
    "code_investigation.plan": {"no_repository_mutation"},
    "refactor.single_path": {"no_repository_mutation"},
    "execution_planning.plan": {"no_repository_mutation", "draft_artifacts_only"},
    "workflow_feedback.record": {"no_repository_mutation", "controller_artifacts_only"},
}
WORKFLOW_APPROVAL_BOUNDARY_ALLOWLIST = {
    "code_context.lookup": {"none"},
    "code_investigation.plan": {"none"},
    "refactor.single_path": {"none"},
    "execution_planning.plan": {"none", "packet_design_required"},
    "workflow_feedback.record": {"none", "feedback_only"},
}
TRIGGER_REQUIRED_PRIORITY = 1000
REQUIRED_SKILL_FIELDS = {
    "id",
    "path",
    "version",
    "owner",
    "description",
    "compatibility",
    "safety_level",
    "allowed_tools",
    "workflows",
    "triggers",
    "workflow_priorities",
    "capability_contract",
    "problem_solving_steps",
    "eval_status",
    "evals",
    "failure_record_refs",
}
REQUIRED_EVAL_CASE_FIELDS = {
    "id",
    "prompt_family",
    "natural_prompt",
    "expected_workflow",
    "expected_artifacts",
    "mutation_policy",
    "live_suite",
}
REQUIRED_ADMISSION_FIELDS = {
    "skill",
    "eval_case",
    "doc_refs",
}


class SkillRegistryError(RuntimeError):
    def __init__(self, message: str, *, code: str = "invalid_skill_registry"):
        super().__init__(message)
        self.code = code


def read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SkillRegistryError(f"Missing {label}: {path}", code="missing_skill_registry") from exc
    except json.JSONDecodeError as exc:
        raise SkillRegistryError(f"Invalid {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise SkillRegistryError(f"{label} must contain a JSON object.")
    return value


def parse_skill_frontmatter(path: Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SkillRegistryError(f"Could not read skill file: {path}") from exc
    if not text.startswith("---\n"):
        raise SkillRegistryError(f"Skill file is missing Agent Skills frontmatter: {path}")
    end = text.find("\n---", 4)
    if end < 0:
        raise SkillRegistryError(f"Skill file frontmatter is not closed: {path}")
    values: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        key = key.strip()
        value = raw_value.strip().strip('"')
        if key in {"name", "description"} and value:
            values[key] = value
    if not values.get("name") or not values.get("description"):
        raise SkillRegistryError(f"Skill frontmatter must include name and description: {path}")
    return values


def string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise SkillRegistryError(f"{label} must be a non-empty list of strings.")
    return list(value)


def int_list(value: Any, label: str) -> list[int]:
    if not isinstance(value, list) or not all(isinstance(item, int) and not isinstance(item, bool) for item in value):
        raise SkillRegistryError(f"{label} must be a list of integers.")
    return list(value)


def registry_ids(path: Path, key: str) -> set[str]:
    manifest = read_json_object(path, str(path))
    items = manifest.get(key)
    if not isinstance(items, list):
        raise SkillRegistryError(f"{path} must contain a {key} list.")
    ids: set[str] = set()
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise SkillRegistryError(f"Each {key} entry must include an id.")
        ids.add(item["id"])
    return ids


def validate_eval_case_item(item: Any, *, workflow_ids: set[str] | None = None) -> dict[str, Any]:
    if not isinstance(item, dict) or not isinstance(item.get("id"), str):
        raise SkillRegistryError("Each skill eval case must include an id.")
    case_id = item["id"]
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", case_id):
        raise SkillRegistryError(f"Skill eval case id is invalid: {case_id!r}")
    missing = sorted(REQUIRED_EVAL_CASE_FIELDS - set(item))
    if missing:
        raise SkillRegistryError(f"Skill eval case {case_id} is missing field(s): {', '.join(missing)}")
    prompt_family = item["prompt_family"]
    natural_prompt = item["natural_prompt"]
    expected_workflow = item["expected_workflow"]
    live_suite = item["live_suite"]
    for field_name, value in (
        ("prompt_family", prompt_family),
        ("natural_prompt", natural_prompt),
        ("expected_workflow", expected_workflow),
        ("live_suite", live_suite),
    ):
        if not isinstance(value, str) or not value.strip():
            raise SkillRegistryError(f"Skill eval case {case_id}.{field_name} must be a non-empty string.")
    mutation_policy = item["mutation_policy"]
    if mutation_policy not in MUTATION_POLICIES:
        raise SkillRegistryError(f"Skill eval case {case_id} has unsupported mutation_policy.")
    if workflow_ids is not None and expected_workflow not in workflow_ids:
        raise SkillRegistryError(f"Skill eval case {case_id} has unknown expected_workflow.")
    expected_artifacts = string_list(item["expected_artifacts"], f"skill_evals.cases.{case_id}.expected_artifacts")
    return {
        "id": case_id,
        "prompt_family": prompt_family,
        "natural_prompt": natural_prompt,
        "expected_workflow": expected_workflow,
        "expected_artifacts": expected_artifacts,
        "mutation_policy": mutation_policy,
        "live_suite": live_suite,
    }


def eval_catalog_ids(path: Path, *, workflow_ids: set[str] | None = None) -> tuple[set[str], set[str]]:
    manifest = read_json_object(path, str(path))
    fixtures = manifest.get("fixtures")
    if not isinstance(fixtures, list):
        raise SkillRegistryError(f"{path} must contain a fixtures list.")
    fixture_ids: set[str] = set()
    for item in fixtures:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise SkillRegistryError("Each skill eval fixture must include an id.")
        fixture_ids.add(item["id"])
    cases = manifest.get("cases", [])
    if not isinstance(cases, list):
        raise SkillRegistryError(f"{path} cases must be a list when present.")
    case_ids: set[str] = set()
    for item in cases:
        eval_case = validate_eval_case_item(item, workflow_ids=workflow_ids)
        if eval_case["id"] in case_ids:
            raise SkillRegistryError(f"Duplicate skill eval case id: {eval_case['id']}")
        case_ids.add(eval_case["id"])
    return fixture_ids, case_ids


def existing_skill_ids_and_route_keys(registry: dict[str, Any]) -> tuple[set[str], set[str]]:
    skills = registry.get("skills")
    if not isinstance(skills, list):
        raise SkillRegistryError("runtime/skills.json must contain a skills list.")
    skill_ids: set[str] = set()
    route_keys: set[str] = set()
    for item in skills:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise SkillRegistryError("Each skill registry entry must include an id.")
        skill_ids.add(item["id"])
        contract = item.get("capability_contract")
        if isinstance(contract, dict) and isinstance(contract.get("route_key"), str):
            route_keys.add(contract["route_key"])
    return skill_ids, route_keys


def validate_doc_refs(config_root: Path, doc_refs: Any) -> list[str]:
    refs = string_list(doc_refs, "skill_admission.doc_refs")
    normalized_refs: list[str] = []
    for ref in refs:
        path_text = ref.split("#", 1)[0]
        if not path_text:
            raise SkillRegistryError(f"skill_admission.doc_refs contains an empty path: {ref!r}")
        path = (config_root / path_text).resolve()
        if not path.is_file():
            raise SkillRegistryError(f"skill_admission.doc_refs path does not exist: {ref}")
        normalized_refs.append(ref)
    return normalized_refs


def validate_capability_contract(
    skill_id: str,
    value: Any,
    *,
    workflows: list[str],
    eval_case_ids: set[str],
    safety_level: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SkillRegistryError(f"{skill_id}.capability_contract must be an object.")
    required = {
        "route_key",
        "task_types",
        "input_artifacts",
        "output_artifacts",
        "approval_boundary",
        "mutation_policy",
        "eval_case_ids",
    }
    missing = sorted(required - set(value))
    if missing:
        raise SkillRegistryError(f"{skill_id}.capability_contract is missing field(s): {', '.join(missing)}")
    route_key = value["route_key"]
    if not isinstance(route_key, str) or not re.fullmatch(r"[a-z][a-z0-9_.-]*", route_key):
        raise SkillRegistryError(f"{skill_id}.capability_contract.route_key is invalid.")
    task_types = string_list(value["task_types"], f"{skill_id}.capability_contract.task_types")
    input_artifacts = string_list(value["input_artifacts"], f"{skill_id}.capability_contract.input_artifacts")
    output_artifacts = string_list(value["output_artifacts"], f"{skill_id}.capability_contract.output_artifacts")
    approval_boundary = value["approval_boundary"]
    if approval_boundary not in APPROVAL_BOUNDARIES:
        raise SkillRegistryError(f"{skill_id}.capability_contract.approval_boundary is unsupported.")
    mutation_policy = value["mutation_policy"]
    if mutation_policy not in MUTATION_POLICIES:
        raise SkillRegistryError(f"{skill_id}.capability_contract.mutation_policy is unsupported.")
    case_ids = string_list(value["eval_case_ids"], f"{skill_id}.capability_contract.eval_case_ids")
    unknown_cases = sorted(set(case_ids) - eval_case_ids)
    if unknown_cases:
        raise SkillRegistryError(
            f"{skill_id}.capability_contract.eval_case_ids contains unknown case(s): {', '.join(unknown_cases)}"
        )
    if approval_boundary == "packet_design_required" and safety_level != "approval_gated_packet_design":
        raise SkillRegistryError(f"{skill_id}.capability_contract approval boundary conflicts with safety_level.")
    if safety_level == "approval_gated_packet_design" and approval_boundary != "packet_design_required":
        raise SkillRegistryError(f"{skill_id}.capability_contract must require packet-design approval.")
    if mutation_policy == "draft_artifacts_only" and approval_boundary != "packet_design_required":
        raise SkillRegistryError(f"{skill_id}.capability_contract draft artifacts require packet-design approval.")
    if mutation_policy == "controller_artifacts_only" and safety_level != "feedback_only":
        raise SkillRegistryError(f"{skill_id}.capability_contract controller artifact mutation is reserved for feedback.")
    if value.get("preferred_workflow") is not None:
        preferred = value["preferred_workflow"]
        if not isinstance(preferred, str) or preferred not in workflows:
            raise SkillRegistryError(f"{skill_id}.capability_contract.preferred_workflow must be one of workflows.")
    return {
        "route_key": route_key,
        "task_types": task_types,
        "input_artifacts": input_artifacts,
        "output_artifacts": output_artifacts,
        "approval_boundary": approval_boundary,
        "mutation_policy": mutation_policy,
        "eval_case_ids": case_ids,
        "preferred_workflow": value.get("preferred_workflow"),
    }


def route_key_namespace(route_key: str) -> str:
    return route_key.split(".", 1)[0]


def validate_route_key_ownership(
    skill_id: str,
    *,
    workflows: list[str],
    safety_level: str,
    capability_contract: dict[str, Any],
) -> str:
    route_key = capability_contract["route_key"]
    namespace = route_key_namespace(route_key)
    if namespace not in ROUTE_KEY_NAMESPACES:
        raise SkillRegistryError(
            f"{skill_id}.capability_contract.route_key has unsupported namespace: {namespace!r}"
        )
    strict_rule = STRICT_ROUTE_NAMESPACE_RULES.get(namespace)
    if strict_rule:
        workflow_set = set(workflows)
        if workflow_set != strict_rule["workflows"]:
            raise SkillRegistryError(
                f"{skill_id}.capability_contract.route_key namespace {namespace!r} "
                f"requires workflows: {', '.join(sorted(strict_rule['workflows']))}"
            )
        if capability_contract["mutation_policy"] != strict_rule["mutation_policy"]:
            raise SkillRegistryError(
                f"{skill_id}.capability_contract.route_key namespace {namespace!r} "
                f"requires mutation_policy={strict_rule['mutation_policy']}"
            )
        if capability_contract["approval_boundary"] != strict_rule["approval_boundary"]:
            raise SkillRegistryError(
                f"{skill_id}.capability_contract.route_key namespace {namespace!r} "
                f"requires approval_boundary={strict_rule['approval_boundary']}"
            )
        if safety_level != strict_rule["safety_level"]:
            raise SkillRegistryError(
                f"{skill_id}.capability_contract.route_key namespace {namespace!r} "
                f"requires safety_level={strict_rule['safety_level']}"
            )
    return namespace


def validate_deprecation_contract(skill_id: str, eval_status: str, value: Any) -> dict[str, Any] | None:
    if eval_status != "deprecated":
        if value is not None:
            raise SkillRegistryError(f"{skill_id}.deprecation is allowed only when eval_status=deprecated.")
        return None
    if not isinstance(value, dict):
        raise SkillRegistryError(f"{skill_id} uses eval_status=deprecated but is missing a deprecation object.")
    missing = sorted(DEPRECATION_REQUIRED_FIELDS - set(value))
    if missing:
        raise SkillRegistryError(f"{skill_id}.deprecation is missing field(s): {', '.join(missing)}")
    replaced_by = value["replaced_by"]
    reason = value["reason"]
    effective_date = value["effective_date"]
    if not isinstance(replaced_by, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", replaced_by):
        raise SkillRegistryError(f"{skill_id}.deprecation.replaced_by must be a skill id.")
    if not isinstance(reason, str) or len(reason.strip()) < 20:
        raise SkillRegistryError(f"{skill_id}.deprecation.reason must be descriptive.")
    if not isinstance(effective_date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", effective_date):
        raise SkillRegistryError(f"{skill_id}.deprecation.effective_date must use YYYY-MM-DD.")
    return {
        "replaced_by": replaced_by,
        "reason": reason,
        "effective_date": effective_date,
    }


def normalized_intent_phrase(value: str) -> str:
    words = [
        word
        for word in re.findall(r"[a-z0-9]+", value.lower().replace("_", " "))
        if word not in INTENT_STOPWORDS
    ]
    return " ".join(words)


def normalized_trigger_phrases(triggers: list[str]) -> set[str]:
    phrases: set[str] = set()
    for trigger in triggers:
        phrase = normalized_intent_phrase(trigger)
        if len(phrase) >= 8:
            phrases.add(phrase)
    return phrases


def semantic_intent_conflicts(
    skills: dict[str, dict[str, Any]],
    *,
    proposed_skill_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Return deterministic duplicate-intent conflicts for registry or batch admission.

    This intentionally avoids fuzzy model similarity. A conflict is only reported when
    two skills share the same workflow and mutation boundary and either repeat the
    same task type, or repeat the same output artifacts with an overlapping trigger.
    """
    proposed = proposed_skill_ids or set(skills)
    values = [skill for skill in skills.values() if skill.get("eval_status") != "deprecated"]
    conflicts: list[dict[str, Any]] = []
    for index, left in enumerate(values):
        left_contract = left["capability_contract"]
        left_workflows = set(left["workflows"])
        left_mutation = left_contract["mutation_policy"]
        left_tasks = set(left_contract["task_types"])
        left_outputs = set(left_contract["output_artifacts"])
        left_triggers = normalized_trigger_phrases(left["triggers"])
        for right in values[index + 1 :]:
            if left["id"] not in proposed and right["id"] not in proposed:
                continue
            right_contract = right["capability_contract"]
            if left_workflows != set(right["workflows"]):
                continue
            if left_mutation != right_contract["mutation_policy"]:
                continue
            right_tasks = set(right_contract["task_types"])
            right_outputs = set(right_contract["output_artifacts"])
            shared_tasks = sorted(left_tasks & right_tasks)
            shared_outputs = sorted(left_outputs & right_outputs)
            shared_triggers = sorted(left_triggers & normalized_trigger_phrases(right["triggers"]))
            if shared_tasks or (left_outputs == right_outputs and shared_triggers):
                conflicts.append(
                    {
                        "skill_ids": [left["id"], right["id"]],
                        "route_keys": [left_contract["route_key"], right_contract["route_key"]],
                        "workflows": sorted(left_workflows),
                        "mutation_policy": left_mutation,
                        "shared_task_types": shared_tasks,
                        "shared_output_artifacts": shared_outputs,
                        "shared_triggers": shared_triggers,
                        "reason": "overlapping semantic intent within the same workflow and mutation boundary",
                    }
                )
    return conflicts


def validate_skill_item(
    item: Any,
    *,
    config_root: Path,
    workflow_ids: set[str],
    tool_ids: set[str],
    eval_fixture_ids: set[str],
    eval_case_ids: set[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise SkillRegistryError("Each skill registry entry must be an object.")
    missing = sorted(REQUIRED_SKILL_FIELDS - set(item))
    if missing:
        raise SkillRegistryError(f"Skill registry entry is missing field(s): {', '.join(missing)}")

    skill_id = item["id"]
    if not isinstance(skill_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", skill_id):
        raise SkillRegistryError(f"Invalid skill id: {skill_id!r}")
    path_value = item["path"]
    if not isinstance(path_value, str) or not path_value.strip():
        raise SkillRegistryError(f"{skill_id}.path must be a string.")
    skill_path = (config_root / path_value).resolve()
    if not skill_path.is_file():
        raise SkillRegistryError(f"{skill_id}.path does not exist: {skill_path}", code="missing_skill")
    frontmatter = parse_skill_frontmatter(skill_path)
    if frontmatter["name"] != skill_id:
        raise SkillRegistryError(f"{skill_id}.path frontmatter name is {frontmatter['name']!r}.")

    version = item["version"]
    if not isinstance(version, str) or not SEMVER_RE.fullmatch(version):
        raise SkillRegistryError(f"{skill_id}.version must be semantic version x.y.z.")
    owner = item["owner"]
    if not isinstance(owner, str) or not owner.strip():
        raise SkillRegistryError(f"{skill_id}.owner must be a non-empty string.")
    description = item["description"]
    if not isinstance(description, str) or len(description.strip()) < 20:
        raise SkillRegistryError(f"{skill_id}.description must be a descriptive string.")
    compatibility = string_list(item["compatibility"], f"{skill_id}.compatibility")
    allowed_tools = string_list(item["allowed_tools"], f"{skill_id}.allowed_tools") if item["allowed_tools"] else []
    unknown_tools = sorted(set(allowed_tools) - tool_ids)
    if unknown_tools:
        raise SkillRegistryError(f"{skill_id}.allowed_tools contains unknown tool(s): {', '.join(unknown_tools)}")
    workflows = string_list(item["workflows"], f"{skill_id}.workflows")
    unknown_workflows = sorted(set(workflows) - workflow_ids)
    if unknown_workflows:
        raise SkillRegistryError(f"{skill_id}.workflows contains unknown workflow(s): {', '.join(unknown_workflows)}")
    triggers = string_list(item["triggers"], f"{skill_id}.triggers")

    safety_level = item["safety_level"]
    if safety_level not in SAFETY_LEVELS:
        raise SkillRegistryError(f"{skill_id}.safety_level is unsupported: {safety_level!r}")
    workflow_priorities = item["workflow_priorities"]
    if not isinstance(workflow_priorities, dict):
        raise SkillRegistryError(f"{skill_id}.workflow_priorities must be an object.")
    for workflow_id, priority in workflow_priorities.items():
        if workflow_id not in workflows:
            raise SkillRegistryError(f"{skill_id}.workflow_priorities includes workflow not listed in workflows: {workflow_id}")
        if not isinstance(priority, int) or isinstance(priority, bool) or priority < 0:
            raise SkillRegistryError(f"{skill_id}.workflow_priorities.{workflow_id} must be a non-negative integer.")
    capability_contract = validate_capability_contract(
        skill_id,
        item["capability_contract"],
        workflows=workflows,
        eval_case_ids=eval_case_ids or set(),
        safety_level=safety_level,
    )
    route_namespace = validate_route_key_ownership(
        skill_id,
        workflows=workflows,
        safety_level=safety_level,
        capability_contract=capability_contract,
    )

    problem_steps = int_list(item["problem_solving_steps"], f"{skill_id}.problem_solving_steps")
    if not all(1 <= step <= 8 for step in problem_steps):
        raise SkillRegistryError(f"{skill_id}.problem_solving_steps values must be 1 through 8.")
    eval_status = item["eval_status"]
    if eval_status not in EVAL_STATUSES:
        raise SkillRegistryError(f"{skill_id}.eval_status is unsupported: {eval_status!r}")
    deprecation = validate_deprecation_contract(skill_id, eval_status, item.get("deprecation"))
    evals = item["evals"]
    if not isinstance(evals, dict) or not isinstance(evals.get("fixtures"), list) or not evals["fixtures"]:
        raise SkillRegistryError(f"{skill_id}.evals must include fixtures.")
    fixtures = string_list(evals["fixtures"], f"{skill_id}.evals.fixtures")
    unknown_fixtures = sorted(set(fixtures) - eval_fixture_ids)
    if unknown_fixtures:
        raise SkillRegistryError(f"{skill_id}.evals.fixtures contains unknown fixture(s): {', '.join(unknown_fixtures)}")
    failure_refs = string_list(item["failure_record_refs"], f"{skill_id}.failure_record_refs")

    return {
        "id": skill_id,
        "path": str(skill_path),
        "version": version,
        "owner": owner,
        "description": description,
        "compatibility": compatibility,
        "safety_level": safety_level,
        "allowed_tools": allowed_tools,
        "workflows": workflows,
        "triggers": triggers,
        "workflow_priorities": dict(workflow_priorities),
        "capability_contract": capability_contract,
        "route_namespace": route_namespace,
        "problem_solving_steps": problem_steps,
        "eval_status": eval_status,
        "deprecation": deprecation,
        "evals": dict(evals),
        "failure_record_refs": failure_refs,
    }


def validate_registry_deprecation_links(validated: dict[str, dict[str, Any]]) -> None:
    for skill_id, skill in validated.items():
        deprecation = skill.get("deprecation")
        if not deprecation:
            continue
        replacement = deprecation["replaced_by"]
        if replacement == skill_id:
            raise SkillRegistryError(f"{skill_id}.deprecation.replaced_by cannot point to itself.")
        if replacement not in validated:
            raise SkillRegistryError(f"{skill_id}.deprecation.replaced_by references unknown skill: {replacement}")
        if validated[replacement]["eval_status"] == "deprecated":
            raise SkillRegistryError(f"{skill_id}.deprecation.replaced_by cannot point to a deprecated skill.")


def validate_skill_registry_manifest(registry: dict[str, Any], config_root: Path) -> dict[str, dict[str, Any]]:
    if registry.get("schema_version") != SCHEMA_VERSION:
        raise SkillRegistryError("runtime/skills.json schema_version must be 1.")
    if registry.get("kind") != "skill_registry":
        raise SkillRegistryError("runtime/skills.json kind must be skill_registry.")
    skills = registry.get("skills")
    if not isinstance(skills, list):
        raise SkillRegistryError("runtime/skills.json must contain a skills list.")
    workflow_ids = registry_ids(config_root / "runtime" / "workflows.json", "workflows")
    tool_ids = registry_ids(config_root / "runtime" / "tools.json", "tools")
    eval_fixture_ids, eval_case_ids = eval_catalog_ids(
        config_root / "runtime" / "skill_evals.json",
        workflow_ids=workflow_ids,
    )
    validated: dict[str, dict[str, Any]] = {}
    route_keys: dict[str, str] = {}
    for item in skills:
        skill = validate_skill_item(
            item,
            config_root=config_root,
            workflow_ids=workflow_ids,
            tool_ids=tool_ids,
            eval_fixture_ids=eval_fixture_ids,
            eval_case_ids=eval_case_ids,
        )
        skill_id = skill["id"]
        if skill_id in validated:
            raise SkillRegistryError(f"Duplicate skill id: {skill_id}")
        route_key = skill["capability_contract"]["route_key"]
        if route_key in route_keys:
            raise SkillRegistryError(f"Duplicate skill capability route_key: {route_key}")
        route_keys[route_key] = skill_id
        validated[skill_id] = skill
    validate_registry_deprecation_links(validated)
    conflicts = semantic_intent_conflicts(validated)
    if conflicts:
        first = conflicts[0]
        raise SkillRegistryError(
            "Skill registry has overlapping semantic intent between "
            f"{first['skill_ids'][0]} and {first['skill_ids'][1]}."
        )
    return validated


def validate_skill_admission_proposal(proposal: Any, config_root: Path) -> dict[str, Any]:
    """Validate one draft skill and one eval case without mutating runtime registries."""
    config_root = config_root.resolve()
    if not isinstance(proposal, dict):
        raise SkillRegistryError("Skill admission proposal must be an object.")
    missing = sorted(REQUIRED_ADMISSION_FIELDS - set(proposal))
    if missing:
        raise SkillRegistryError(f"Skill admission proposal is missing field(s): {', '.join(missing)}")

    registry = read_json_object(config_root / SKILL_REGISTRY_PATH, "skill registry")
    if registry.get("schema_version") != SCHEMA_VERSION or registry.get("kind") != "skill_registry":
        raise SkillRegistryError("runtime/skills.json must be a schema_version 1 skill_registry.")
    workflow_ids = registry_ids(config_root / "runtime" / "workflows.json", "workflows")
    tool_ids = registry_ids(config_root / "runtime" / "tools.json", "tools")
    eval_fixture_ids, existing_eval_case_ids = eval_catalog_ids(
        config_root / "runtime" / "skill_evals.json",
        workflow_ids=workflow_ids,
    )
    existing_skill_ids, existing_route_keys = existing_skill_ids_and_route_keys(registry)
    eval_case = validate_eval_case_item(proposal["eval_case"], workflow_ids=workflow_ids)
    eval_case_id = eval_case["id"]
    if eval_case_id in existing_eval_case_ids:
        raise SkillRegistryError(f"Skill admission eval case already exists: {eval_case_id}")

    skill = validate_skill_item(
        proposal["skill"],
        config_root=config_root,
        workflow_ids=workflow_ids,
        tool_ids=tool_ids,
        eval_fixture_ids=eval_fixture_ids,
        eval_case_ids=existing_eval_case_ids | {eval_case_id},
    )
    skill_id = skill["id"]
    if skill_id in existing_skill_ids:
        raise SkillRegistryError(f"Skill admission skill id already exists: {skill_id}")
    route_key = skill["capability_contract"]["route_key"]
    if route_key in existing_route_keys:
        raise SkillRegistryError(f"Skill admission route_key already exists: {route_key}")
    if skill["eval_status"] != "draft":
        raise SkillRegistryError("Skill admission requires eval_status=draft.")
    contract_case_ids = set(skill["capability_contract"]["eval_case_ids"])
    if eval_case_id not in contract_case_ids:
        raise SkillRegistryError(f"Skill admission skill must reference eval case: {eval_case_id}")
    if skill["capability_contract"]["mutation_policy"] != eval_case["mutation_policy"]:
        raise SkillRegistryError("Skill admission mutation policy must match the eval case.")
    if eval_case["expected_workflow"] not in skill["workflows"]:
        raise SkillRegistryError("Skill admission eval case workflow must be listed in skill.workflows.")
    doc_refs = validate_doc_refs(config_root, proposal["doc_refs"])
    failure_refs = [
        ref
        for ref in skill["failure_record_refs"]
        if isinstance(ref, str) and ref.split("#", 1)[0]
    ]
    if not failure_refs:
        raise SkillRegistryError("Skill admission requires at least one failure_record_refs documentation link.")

    return {
        "status": "ready",
        "schema_version": SCHEMA_VERSION,
        "skill": skill,
        "eval_case": eval_case,
        "doc_refs": doc_refs,
        "runtime_behavior_changed": False,
        "next_action": "review_then_append_skill_and_eval_case",
    }


def load_skill_registry(config_root: Path) -> dict[str, dict[str, Any]]:
    config_root = config_root.resolve()
    registry = read_json_object(config_root / SKILL_REGISTRY_PATH, "skill registry")
    return validate_skill_registry_manifest(registry, config_root)


def skill_matches_workflow_contract(skill: dict[str, Any], workflow_id: str) -> bool:
    if skill.get("eval_status") == "deprecated":
        return False
    workflows = skill.get("workflows", [])
    if workflow_id not in workflows:
        return False
    contract = skill.get("capability_contract")
    if not isinstance(contract, dict):
        return False
    mutation_policy = contract.get("mutation_policy")
    approval_boundary = contract.get("approval_boundary")
    allowed_mutation_policies = WORKFLOW_MUTATION_POLICY_ALLOWLIST.get(workflow_id, MUTATION_POLICIES)
    allowed_approval_boundaries = WORKFLOW_APPROVAL_BOUNDARY_ALLOWLIST.get(workflow_id, APPROVAL_BOUNDARIES)
    return mutation_policy in allowed_mutation_policies and approval_boundary in allowed_approval_boundaries


def selected_skill_capability_route_keys(
    skill_registry: dict[str, dict[str, Any]],
    selected_skills: list[str],
) -> dict[str, str]:
    routes: dict[str, str] = {}
    for skill_id in selected_skills:
        skill = skill_registry.get(skill_id)
        if not isinstance(skill, dict):
            continue
        contract = skill.get("capability_contract")
        if isinstance(contract, dict) and isinstance(contract.get("route_key"), str):
                routes[skill_id] = contract["route_key"]
    return routes


def skill_workflow_priority(skill: dict[str, Any], workflow_id: str) -> int:
    priorities = skill.get("workflow_priorities", {})
    priority = priorities.get(workflow_id, 1000) if isinstance(priorities, dict) else 1000
    try:
        return int(priority)
    except (TypeError, ValueError):
        return 1000


def skill_trigger_hits(skill: dict[str, Any], query_text: str) -> list[str]:
    query = query_text.lower()
    triggers = skill.get("triggers", [])
    return [
        trigger
        for trigger in triggers
        if isinstance(trigger, str) and trigger.strip() and trigger.lower() in query
    ]


def skill_route_key(skill: dict[str, Any]) -> str | None:
    contract = skill.get("capability_contract")
    if isinstance(contract, dict) and isinstance(contract.get("route_key"), str):
        return contract["route_key"]
    return None


def skill_selection_filter_reasons(skill: dict[str, Any], workflow_id: str, query_text: str) -> list[str]:
    reasons: list[str] = []
    if skill.get("eval_status") == "deprecated":
        reasons.append("deprecated")
    workflows = skill.get("workflows", [])
    if not isinstance(workflows, list) or workflow_id not in workflows:
        reasons.append("workflow_not_supported")
    contract = skill.get("capability_contract")
    if not isinstance(contract, dict):
        reasons.append("missing_capability_contract")
    else:
        mutation_policy = contract.get("mutation_policy")
        approval_boundary = contract.get("approval_boundary")
        allowed_mutation_policies = WORKFLOW_MUTATION_POLICY_ALLOWLIST.get(workflow_id, MUTATION_POLICIES)
        allowed_approval_boundaries = WORKFLOW_APPROVAL_BOUNDARY_ALLOWLIST.get(workflow_id, APPROVAL_BOUNDARIES)
        if mutation_policy not in allowed_mutation_policies:
            reasons.append("mutation_policy_not_allowed")
        if approval_boundary not in allowed_approval_boundaries:
            reasons.append("approval_boundary_not_allowed")
    priority = skill_workflow_priority(skill, workflow_id)
    hits = skill_trigger_hits(skill, query_text)
    if int(priority) >= TRIGGER_REQUIRED_PRIORITY and not hits:
        reasons.append("trigger_required_but_missing")
    return reasons


def explain_skill_selection_for_workflow(
    skill_registry: dict[str, dict[str, Any]],
    workflow_id: str,
    *,
    query_text: str,
    limit: int,
    max_filtered: int = 20,
) -> dict[str, Any]:
    candidates: list[tuple[int, int, str, dict[str, Any]]] = []
    filtered: list[dict[str, Any]] = []
    route_namespace_counts: dict[str, int] = {}
    for skill_id, skill in skill_registry.items():
        route_key = skill_route_key(skill)
        if route_key:
            namespace = route_key_namespace(route_key)
            route_namespace_counts[namespace] = route_namespace_counts.get(namespace, 0) + 1
        priority = skill_workflow_priority(skill, workflow_id)
        hits = skill_trigger_hits(skill, query_text)
        detail = {
            "skill_id": skill_id,
            "route_key": route_key,
            "workflow_priority": priority,
            "trigger_hits": hits,
            "trigger_hit_count": len(hits),
            "eval_status": skill.get("eval_status"),
        }
        reasons = skill_selection_filter_reasons(skill, workflow_id, query_text)
        if reasons:
            if len(filtered) < max_filtered or "deprecated" in reasons:
                filtered.append({**detail, "reasons": reasons})
            continue
        candidates.append((priority, -len(hits), skill_id, detail))
    candidates.sort()
    selected_details = [detail for _priority, _trigger_hits, _skill_id, detail in candidates[:limit]]
    return {
        "workflow_id": workflow_id,
        "query_text": query_text,
        "limit": limit,
        "selected_skill_ids": [detail["skill_id"] for detail in selected_details],
        "selected": selected_details,
        "candidate_count": len(candidates),
        "filtered_count": len(skill_registry) - len(candidates),
        "filtered": filtered,
        "deprecated_exclusions": [item for item in filtered if "deprecated" in item.get("reasons", [])],
        "route_namespace_summary": dict(sorted(route_namespace_counts.items())),
        "body_reads_during_selection": 0,
    }


def select_skills_for_workflow(
    skill_registry: dict[str, dict[str, Any]],
    workflow_id: str,
    *,
    query_text: str,
    limit: int,
) -> list[str]:
    explanation = explain_skill_selection_for_workflow(
        skill_registry,
        workflow_id,
        query_text=query_text,
        limit=limit,
    )
    return list(explanation["selected_skill_ids"])
