#!/usr/bin/env python3
"""Validate natural skill lifecycle chat paths through gateway and AnythingLLM."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_ROOT = "/mnt/c/agentic_agents"
DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL = "http://127.0.0.1:8500/v1"
DEFAULT_ANYTHINGLLM_API_BASE_URL = "http://127.0.0.1:3001"
DEFAULT_WORKSPACE = "my-workspace"
DEFAULT_TARGET_ROOTS = [
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
]
WATCHED_TARGET_FILES = ["core/stealth_order_manager.py"]
WATCHED_REGISTRY_FILES = ["runtime/skills.json", "runtime/skill_evals.json"]
PORT_HEALTH_PROBES = [
    ("localhost-model", "http://127.0.0.1:8000/v1/models"),
    ("llm-gateway", "http://127.0.0.1:8300/v1/models"),
    ("controller", "http://127.0.0.1:8400/health"),
    ("workflow-router-gateway", "http://127.0.0.1:8500/v1/models"),
    ("documenter-role", "http://127.0.0.1:8101/v1/models"),
    ("architect-role", "http://127.0.0.1:8102/v1/models"),
    ("agent-role-8201", "http://127.0.0.1:8201/v1/models"),
    ("agent-role-8202", "http://127.0.0.1:8202/v1/models"),
    ("agent-role-8203", "http://127.0.0.1:8203/v1/models"),
    ("agent-role-8204", "http://127.0.0.1:8204/v1/models"),
    ("agent-role-8205", "http://127.0.0.1:8205/v1/models"),
]


def artifact_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def json_request(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout_seconds: int,
    method: str = "POST",
) -> tuple[int, dict[str, Any]]:
    request_headers = dict(headers or {})
    data = None
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            text = response.read().decode("utf-8")
            return response.status, json.loads(text) if text else {}
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(body_text)
        except json.JSONDecodeError:
            body = {"error": {"message": body_text, "code": "invalid_json_error_body"}}
        return exc.code, body


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def watched_hashes(root: Path, relatives: list[str]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative in relatives:
        path = root / relative
        if path.exists():
            hashes[relative] = digest_file(path)
    if not hashes:
        raise RuntimeError(f"{root} did not contain watched files: {', '.join(relatives)}")
    return hashes


def skill_body_hashes(root: Path) -> dict[str, str]:
    skill_root = root / ".qwen" / "skills"
    if not skill_root.exists():
        raise RuntimeError(f"Missing skill body root: {skill_root}")
    return {path.relative_to(root).as_posix(): digest_file(path) for path in sorted(skill_root.glob("*/SKILL.md"))}


def git_status(root: Path) -> str | None:
    if not (root / ".git").exists():
        return None
    result = subprocess.run(["git", "-C", str(root), "status", "--short"], check=True, capture_output=True, text=True)
    return result.stdout


def before_state(config_root: Path, target_roots: list[str]) -> dict[str, Any]:
    return {
        "registry": watched_hashes(config_root, WATCHED_REGISTRY_FILES),
        "skill_bodies": skill_body_hashes(config_root),
        "targets": {
            target: {
                "hashes": watched_hashes(Path(target), WATCHED_TARGET_FILES),
                "status": git_status(Path(target)),
            }
            for target in target_roots
        },
    }


def validate_state_unchanged(config_root: Path, target_roots: list[str], state: dict[str, Any], label: str) -> None:
    if watched_hashes(config_root, WATCHED_REGISTRY_FILES) != state["registry"]:
        raise RuntimeError(f"{label} changed watched runtime registry files")
    if skill_body_hashes(config_root) != state["skill_bodies"]:
        raise RuntimeError(f"{label} changed skill body files")
    for target in target_roots:
        target_root = Path(target)
        target_state = state["targets"][target]
        if watched_hashes(target_root, WATCHED_TARGET_FILES) != target_state["hashes"]:
            raise RuntimeError(f"{label} changed watched target files under {target}")
        if target_state["status"] is not None and git_status(target_root) != target_state["status"]:
            raise RuntimeError(f"{label} changed git status under {target}")


def text_response(body: dict[str, Any]) -> str:
    for key in ("textResponse", "response", "message"):
        value = body.get(key)
        if isinstance(value, str):
            return value
    choices = body.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message") if isinstance(first.get("message"), dict) else {}
        content = message.get("content")
        if isinstance(content, str):
            return content
    return json.dumps(body, ensure_ascii=True, sort_keys=True)


def require_markers(text: str, markers: tuple[str, ...], *, label: str) -> None:
    missing = [marker for marker in markers if marker not in text]
    if missing:
        raise RuntimeError(f"{label} missing marker(s): {', '.join(missing)}")


def validate_port_health(args: argparse.Namespace) -> None:
    if args.skip_port_health:
        return
    for label, url in PORT_HEALTH_PROBES:
        status, body = json_request(url, timeout_seconds=args.timeout_seconds, method="GET")
        if status != 200:
            raise RuntimeError(f"{label} health probe returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
        print(f"PHASE49 PORT PASS label={label} url={url}")


def make_pack_fixture(config_root: Path, run_id: str) -> Path:
    pack_root = config_root / "runtime-state" / "phase49-natural-lifecycle-live" / run_id / "pack-source"
    skill_id = f"phase49-live-pack-{run_id[-8:].lower()}"
    eval_case_id = skill_id.replace("-", "_")
    skill_body = pack_root / "skills" / skill_id / "SKILL.md"
    skill_body.parent.mkdir(parents=True, exist_ok=True)
    skill_body.write_text(
        "---\n"
        f"name: {skill_id}\n"
        "description: Phase 49 live pack validation fixture.\n"
        "---\n\n"
        f"# {skill_id}\n\n"
        "Use only when registry metadata selects this live validation fixture.\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 1,
        "kind": "skill_pack_manifest",
        "id": f"phase49-live-pack-{run_id[-8:].lower()}",
        "version": "0.1.0",
        "owner": "agentic_agents",
        "description": "Phase 49 live natural lifecycle pack fixture.",
        "namespaces": ["code"],
        "compatibility": ["agent-skills-frontmatter", "openai-compatible-chat", "qwen-local"],
        "docs": ["README.skill-registry.md", "docs/SKILL_LIBRARY_SCALING_PLAN.md"],
        "skills": [
            {
                "id": skill_id,
                "path": str(skill_body),
                "version": "0.1.0",
                "owner": "agentic_agents",
                "description": "Phase 49 live pack fixture skill.",
                "compatibility": ["agent-skills-frontmatter", "openai-compatible-chat", "qwen-local"],
                "safety_level": "read_only_planning",
                "allowed_tools": [],
                "workflows": ["code_investigation.plan"],
                "triggers": ["phase49 live pack lookup"],
                "workflow_priorities": {"code_investigation.plan": 1000},
                "capability_contract": {
                    "route_key": f"code.phase49_live_pack_{run_id[-8:].lower()}",
                    "task_types": ["phase49_live_pack_lookup"],
                    "input_artifacts": ["natural_user_request"],
                    "output_artifacts": ["investigation_plan"],
                    "approval_boundary": "none",
                    "mutation_policy": "no_repository_mutation",
                    "eval_case_ids": [eval_case_id],
                },
                "problem_solving_steps": [4],
                "eval_status": "draft",
                "evals": {
                    "fixtures": ["clear_request", "ambiguous_request"],
                    "localhost_8000": "not_run",
                    "gateway_8300": "not_run",
                    "anythingllm": "not_run",
                },
                "failure_record_refs": ["docs/SKILL_LIBRARY_SCALING_PLAN.md"],
            }
        ],
        "eval_cases": [
            {
                "id": eval_case_id,
                "prompt_family": "phase49-live-pack",
                "natural_prompt": "In <repo>, run the Phase 49 live pack lookup. Read only.",
                "expected_workflow": "code_investigation.plan",
                "expected_artifacts": ["investigation_plan"],
                "mutation_policy": "no_repository_mutation",
                "live_suite": "skill_registry_contract",
            }
        ],
    }
    pack_path = pack_root / "pack.json"
    pack_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return pack_path


def gateway_chat(args: argparse.Namespace, message: str) -> dict[str, Any]:
    status, body = json_request(
        f"{args.workflow_router_gateway_base_url.rstrip('/')}/chat/completions",
        payload={"model": "agentic-workflow-router", "messages": [{"role": "user", "content": message}]},
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"gateway natural lifecycle returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    return body


def anythingllm_chat(args: argparse.Namespace, message: str, api_key: str) -> dict[str, Any]:
    status, body = json_request(
        f"{args.anythingllm_api_base_url.rstrip('/')}/api/v1/workspace/{args.workspace}/chat",
        payload={"message": message, "mode": "chat", "sessionId": f"phase49-natural-lifecycle-{uuid.uuid4().hex}"},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=args.timeout_seconds,
    )
    if status != 200:
        raise RuntimeError(f"AnythingLLM natural lifecycle returned HTTP {status}: {json.dumps(body, ensure_ascii=True)}")
    return body


def selection_prompt(target_root: str) -> str:
    return (
        "Explain skill selection for: "
        f"In {target_root}, explain what find_stealth_order_by_placed_order_id does. Read only."
    )


def scaffold_prompt(run_id: str) -> str:
    suffix = run_id[-8:].lower()
    return "\n".join(
        [
            "Scaffold a skill for a deterministic Phase 49 live prompt family.",
            f"skill_id: phase49-live-scaffold-{suffix}",
            "description: Locate bounded source evidence for a Phase 49 live scaffold prompt.",
            "prompt_family: phase49-live-scaffold",
            "natural_prompt: In <repo>, run the Phase 49 live scaffold lookup. Read only.",
            "workflow_id: code_investigation.plan",
            f"route_key: code.phase49_live_scaffold_{suffix}",
            "trigger_terms: phase49 live scaffold lookup",
            "task_types: phase49_live_scaffold_lookup",
            "output_artifact: investigation_plan",
            "live_suite: skill_registry_contract",
        ]
    )


def pack_validation_prompt(pack_path: Path) -> str:
    return f"Validate this skill pack.\npack_path: {pack_path}\nReturn output as JSON."


def pack_install_prompt(pack_path: Path) -> str:
    return f"Install this skill pack.\npack_path: {pack_path}"


def skill_update_prompt() -> str:
    return "\n".join(
        [
            "Update skill metadata for live missing approval proof.",
            "skill_id: code-explanation-summarizer",
            "change_type: metadata_only",
            "version_bump: patch",
            'metadata_updates: {"description": "Phase 49 live natural missing approval proof."}',
        ]
    )


def skill_deprecation_prompt() -> str:
    return "\n".join(
        [
            "Deprecate a skill through the lifecycle gate.",
            "skill_id: code-explanation-summarizer",
            "replacement_skill_id: behavior-existence-checker",
            "reason: Phase 49 live natural deprecation request proves approval is required before mutation.",
            "effective_date: 2026-06-05",
        ]
    )


def validate_gateway_paths(args: argparse.Namespace, config_root: Path, target_roots: list[str], pack_path: Path, run_id: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for target_root in target_roots:
        body = gateway_chat(args, selection_prompt(target_root))
        compact = body.get("agentic_controller_response") if isinstance(body.get("agentic_controller_response"), dict) else {}
        if compact.get("workflow") != "skill.selection.explain":
            raise RuntimeError(f"gateway selection chose wrong workflow: {json.dumps(compact, ensure_ascii=True)}")
        if "route_decision" not in compact.get("artifacts", {}):
            raise RuntimeError("gateway selection did not persist route_decision")
        require_markers(text_response(body), ("Skill Selection:", "code-explanation-summarizer"), label=f"gateway selection {target_root}")
        results.append({"surface": "gateway", "case": "selection", "target_root": target_root, "run_id": compact.get("run_id")})

    cases = [
        ("scaffold", scaffold_prompt(run_id), "skill.scaffold", "completed", ("Skill Scaffold:", "phase49-live-scaffold")),
        ("pack_validation", pack_validation_prompt(pack_path), "skill_pack.validate", "completed", ('"workflow": "skill_pack.validate"', '"validation_status": "passed"')),
        ("pack_install_missing_approval", pack_install_prompt(pack_path), "skill_pack.install", "approval_required", ("approval_required", "approved_for_skill_pack_install")),
        ("skill_update_missing_approval", skill_update_prompt(), "skill.update", "approval_required", ("approval_required", "approved_for_skill_update")),
        ("skill_deprecation_missing_approval", skill_deprecation_prompt(), "skill.deprecate", "approval_required", ("approval_required", "approved_for_skill_deprecation")),
    ]
    for case_id, message, workflow, expected_status, markers in cases:
        body = gateway_chat(args, message)
        compact = body.get("agentic_controller_response") if isinstance(body.get("agentic_controller_response"), dict) else {}
        if compact.get("workflow") != workflow or compact.get("status") != expected_status:
            raise RuntimeError(f"gateway {case_id} mismatch: {json.dumps(compact, ensure_ascii=True)}")
        if "route_decision" not in compact.get("artifacts", {}):
            raise RuntimeError(f"gateway {case_id} did not persist route_decision")
        require_markers(text_response(body), markers, label=f"gateway {case_id}")
        results.append({"surface": "gateway", "case": case_id, "run_id": compact.get("run_id")})
    print("PHASE49 GATEWAY NATURAL LIFECYCLE PASS")
    return results


def validate_anythingllm_paths(args: argparse.Namespace, target_roots: list[str], pack_path: Path, run_id: str, api_key: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for target_root in target_roots:
        body = anythingllm_chat(args, selection_prompt(target_root), api_key)
        require_markers(text_response(body), ("Skill Selection:", "code-explanation-summarizer"), label=f"AnythingLLM selection {target_root}")
        results.append({"surface": "anythingllm", "case": "selection", "target_root": target_root})
    cases = [
        ("scaffold", scaffold_prompt(run_id), ("Skill Scaffold:", "phase49-live-scaffold")),
        ("pack_validation", pack_validation_prompt(pack_path), ('"workflow": "skill_pack.validate"', '"validation_status": "passed"')),
        ("pack_install_missing_approval", pack_install_prompt(pack_path), ("approval_required", "approved_for_skill_pack_install")),
        ("skill_update_missing_approval", skill_update_prompt(), ("approval_required", "approved_for_skill_update")),
        ("skill_deprecation_missing_approval", skill_deprecation_prompt(), ("approval_required", "approved_for_skill_deprecation")),
    ]
    for case_id, message, markers in cases:
        body = anythingllm_chat(args, message, api_key)
        require_markers(text_response(body), markers, label=f"AnythingLLM {case_id}")
        results.append({"surface": "anythingllm", "case": case_id})
    print("PHASE49 ANYTHINGLLM NATURAL LIFECYCLE PASS")
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", default=DEFAULT_CONFIG_ROOT)
    parser.add_argument("--workflow-router-gateway-base-url", default=DEFAULT_WORKFLOW_ROUTER_GATEWAY_BASE_URL)
    parser.add_argument("--anythingllm-api-base-url", default=DEFAULT_ANYTHINGLLM_API_BASE_URL)
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    parser.add_argument("--api-key-env", default="ANYTHINGLLM_API_KEY")
    parser.add_argument("--target-root", action="append", dest="target_roots")
    parser.add_argument("--skip-anythingllm", action="store_true")
    parser.add_argument("--skip-port-health", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_root = Path(args.config_root).resolve()
    target_roots = args.target_roots or DEFAULT_TARGET_ROOTS
    run_id = f"phase49-{artifact_timestamp()}"
    validate_port_health(args)
    state = before_state(config_root, target_roots)
    pack_path = make_pack_fixture(config_root, run_id)
    results = validate_gateway_paths(args, config_root, target_roots, pack_path, run_id)
    if not args.skip_anythingllm:
        api_key = os.environ.get(args.api_key_env)
        if not api_key:
            raise RuntimeError(f"{args.api_key_env} is required unless --skip-anythingllm is set")
        results.extend(validate_anythingllm_paths(args, target_roots, pack_path, run_id, api_key))
    validate_state_unchanged(config_root, target_roots, state, "phase49 natural lifecycle live validation")
    print(
        "PHASE49 LIVE SUMMARY "
        + json.dumps(
            {
                "result_count": len(results),
                "target_roots": target_roots,
                "anythingllm": not args.skip_anythingllm,
                "canonical_registry_mutated": False,
                "approved_mutation_live_mode": "skipped_to_protect_canonical_config_root",
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
