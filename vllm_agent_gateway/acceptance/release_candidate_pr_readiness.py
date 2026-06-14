"""Phase 238 release-candidate PR/readiness packet validation."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EXPECTED_POLICY_KIND = "release_candidate_pr_readiness_policy"
EXPECTED_REPORT_KIND = "release_candidate_pr_readiness_report"
EXPECTED_PHASE = 238
EXPECTED_BACKLOG_ID = "P0-M14-238"
DEFAULT_POLICY_PATH = Path("runtime") / "release_candidate_pr_readiness_policy.json"
DEFAULT_OUTPUT_DIR = Path("runtime-state") / "release-candidate-pr-readiness" / "phase238"


class ReleaseCandidateReadinessStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class ReleaseCandidateReadinessDecision(str, Enum):
    REVIEWABLE = "release_candidate_reviewable"
    BLOCKED = "release_candidate_blocked"


@dataclass(frozen=True)
class ReleaseCandidatePrReadinessConfig:
    config_root: Path
    output_path: Path | None = None
    markdown_output_path: Path | None = None
    policy_path: Path = DEFAULT_POLICY_PATH


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def resolve_path(config_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_root / path


def default_report_path(config_root: Path) -> Path:
    return config_root / DEFAULT_OUTPUT_DIR / f"release-candidate-pr-readiness-{utc_timestamp()}.json"


def default_markdown_path(output_path: Path) -> Path:
    return output_path.with_suffix(".md")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object at {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_lines(config_root: Path, *args: str, check: bool = True) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=str(config_root),
        check=check,
        capture_output=True,
        text=True,
    )
    return result.stdout.splitlines()


def load_policy(config_root: Path, policy_path: Path) -> dict[str, Any]:
    return read_json(resolve_path(config_root, policy_path))


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def int_list(value: object) -> list[int]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, int) and not isinstance(item, bool)]


def validate_policy(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != SCHEMA_VERSION:
        errors.append("policy.schema_version must be 1")
    if policy.get("kind") != EXPECTED_POLICY_KIND:
        errors.append(f"policy.kind must be {EXPECTED_POLICY_KIND}")
    if policy.get("phase") != EXPECTED_PHASE:
        errors.append("policy.phase must be 238")
    if policy.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"policy.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    if policy.get("required_decision") != ReleaseCandidateReadinessDecision.REVIEWABLE.value:
        errors.append("policy.required_decision must be release_candidate_reviewable")
    if not isinstance(policy.get("branch_prefix"), str) or not policy.get("branch_prefix"):
        errors.append("policy.branch_prefix must be a non-empty string")
    for field in (
        "required_docs",
        "required_scripts",
        "forbidden_tracked_path_fragments",
        "allowed_tracked_path_prefixes",
        "required_known_limit_markers",
    ):
        if not string_list(policy.get(field)):
            errors.append(f"policy.{field} must be a non-empty string list")
    if not int_list(policy.get("required_prior_phases")):
        errors.append("policy.required_prior_phases must be a non-empty integer list")
    if policy.get("acceptance_marker") != "RELEASE CANDIDATE PR READINESS PASS":
        errors.append("policy.acceptance_marker must be RELEASE CANDIDATE PR READINESS PASS")
    return errors


def phase_statuses(roadmap_text: str, phases: list[int]) -> dict[str, str | None]:
    statuses: dict[str, str | None] = {}
    for phase in phases:
        pattern = re.compile(
            rf"^### Approved Phase {phase}:.*?(?:\n+)(?P<body>.*?)(?=^### Approved Phase |\Z)",
            re.MULTILINE | re.DOTALL,
        )
        match = pattern.search(roadmap_text)
        if not match:
            statuses[str(phase)] = None
            continue
        status_match = re.search(r"^Status:\s*(?P<status>.+?)\s*$", match.group("body"), flags=re.MULTILINE)
        statuses[str(phase)] = status_match.group("status") if status_match else None
    return statuses


def doc_checks(config_root: Path, docs: list[str]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for doc in docs:
        path = resolve_path(config_root, doc)
        checks.append(
            {
                "path": doc,
                "exists": path.is_file(),
                "sha256": sha256_file(path) if path.is_file() else None,
            }
        )
    return checks


def script_checks(config_root: Path, scripts: list[str]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for script in scripts:
        path = resolve_path(config_root, script)
        checks.append(
            {
                "path": script,
                "exists": path.is_file(),
                "sha256": sha256_file(path) if path.is_file() else None,
            }
        )
    return checks


def tracked_forbidden_paths(config_root: Path, fragments: list[str], allowed_prefixes: list[str] | None = None) -> list[str]:
    tracked = git_lines(config_root, "ls-files")
    allowed = tuple(allowed_prefixes or ())
    return [
        path
        for path in tracked
        if any(fragment in path for fragment in fragments)
        and not any(path.startswith(prefix) for prefix in allowed)
    ]


def known_limit_checks(config_root: Path, markers: list[str]) -> dict[str, Any]:
    search_paths = [
        "README.release-notes.md",
        "README.getting-started.md",
        "docs/ACTIONABLE_WORKFLOW_ROADMAP.md",
        "docs/PRIORITY0_CHAT_QUALITY_BACKLOG.md",
    ]
    combined = "\n".join(
        resolve_path(config_root, path).read_text(encoding="utf-8")
        for path in search_paths
        if resolve_path(config_root, path).is_file()
    )
    lower = combined.lower()
    return {
        "search_paths": search_paths,
        "markers": {
            marker: marker.lower() in lower
            for marker in markers
        },
    }


def build_report(
    *,
    policy: dict[str, Any],
    branch: str,
    commit: str,
    upstream: str | None,
    status_lines: list[str],
    docs: list[dict[str, Any]],
    scripts: list[dict[str, Any]],
    phase_status_map: dict[str, str | None],
    forbidden_tracked_paths: list[str],
    known_limits: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    missing_docs = [item["path"] for item in docs if not item.get("exists")]
    missing_scripts = [item["path"] for item in scripts if not item.get("exists")]
    incomplete_phases = [
        phase
        for phase, status in phase_status_map.items()
        if status != "Complete."
    ]
    missing_limit_markers = [
        marker
        for marker, present in known_limits.get("markers", {}).items()
        if not present
    ]
    branch_ok = branch.startswith(str(policy.get("branch_prefix") or ""))
    source_clean = len(status_lines) == 0
    reviewable = (
        not errors
        and branch_ok
        and source_clean
        and not missing_docs
        and not missing_scripts
        and not incomplete_phases
        and not forbidden_tracked_paths
        and not missing_limit_markers
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": EXPECTED_REPORT_KIND,
        "phase": EXPECTED_PHASE,
        "priority_backlog_id": EXPECTED_BACKLOG_ID,
        "status": ReleaseCandidateReadinessStatus.PASSED.value
        if reviewable
        else ReleaseCandidateReadinessStatus.FAILED.value,
        "decision": ReleaseCandidateReadinessDecision.REVIEWABLE.value
        if reviewable
        else ReleaseCandidateReadinessDecision.BLOCKED.value,
        "generated_at": utc_timestamp(),
        "source": {
            "branch": branch,
            "commit": commit,
            "upstream": upstream,
            "source_clean": source_clean,
            "status_line_count": len(status_lines),
            "status_lines": status_lines,
        },
        "docs": {
            "required": docs,
            "missing": missing_docs,
        },
        "scripts": {
            "required": scripts,
            "missing": missing_scripts,
        },
        "prior_phases": {
            "required": int_list(policy.get("required_prior_phases")),
            "statuses": phase_status_map,
            "incomplete": incomplete_phases,
        },
        "hygiene": {
            "forbidden_tracked_path_fragments": string_list(policy.get("forbidden_tracked_path_fragments")),
            "allowed_tracked_path_prefixes": string_list(policy.get("allowed_tracked_path_prefixes")),
            "forbidden_tracked_paths": forbidden_tracked_paths,
        },
        "known_limits": {
            **known_limits,
            "missing_markers": missing_limit_markers,
        },
        "review_packet": {
            "title": "M14 release-candidate handoff and chat-quality readiness",
            "branch": branch,
            "commit": commit,
            "suggested_pr_mode": "draft",
            "supported_scope": [
                "fresh AnythingLLM chat through workflow-router gateway",
                "read-only L1/L2 coding prompt routing",
                "release handoff from clean checkout",
                "large-context usability through retrieval, chunking, summarization, and artifact paging",
            ],
            "non_goals": [
                "advanced refactor",
                "real apply to protected fixtures",
                "raw 1M-token prompt support",
            ],
            "proof_commands": string_list(policy.get("required_scripts")),
            "rollback_path": "Keep the existing branch unmerged or revert the release-candidate commits from the target branch.",
        },
        "summary": {
            "branch_ok": branch_ok,
            "source_clean": source_clean,
            "missing_doc_count": len(missing_docs),
            "missing_script_count": len(missing_scripts),
            "incomplete_phase_count": len(incomplete_phases),
            "forbidden_tracked_path_count": len(forbidden_tracked_paths),
            "missing_limit_marker_count": len(missing_limit_markers),
        },
        "errors": errors,
    }


def validate_report(report: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if report.get("schema_version") != SCHEMA_VERSION:
        errors.append("report.schema_version must be 1")
    if report.get("kind") != EXPECTED_REPORT_KIND:
        errors.append(f"report.kind must be {EXPECTED_REPORT_KIND}")
    if report.get("phase") != EXPECTED_PHASE:
        errors.append("report.phase must be 238")
    if report.get("priority_backlog_id") != EXPECTED_BACKLOG_ID:
        errors.append(f"report.priority_backlog_id must be {EXPECTED_BACKLOG_ID}")
    if report.get("decision") != policy.get("required_decision"):
        errors.append("report.decision must match policy.required_decision")
    source = report.get("source") if isinstance(report.get("source"), dict) else {}
    branch = str(source.get("branch") or "")
    if not branch.startswith(str(policy.get("branch_prefix") or "")):
        errors.append("report.source.branch must use policy.branch_prefix")
    if source.get("source_clean") is not True:
        errors.append("report.source.source_clean must be true")
    for field in ("docs", "scripts"):
        section = report.get(field) if isinstance(report.get(field), dict) else {}
        if section.get("missing"):
            errors.append(f"report.{field}.missing must be empty")
    prior = report.get("prior_phases") if isinstance(report.get("prior_phases"), dict) else {}
    if prior.get("incomplete"):
        errors.append("report.prior_phases.incomplete must be empty")
    hygiene = report.get("hygiene") if isinstance(report.get("hygiene"), dict) else {}
    if hygiene.get("forbidden_tracked_paths"):
        errors.append("report.hygiene.forbidden_tracked_paths must be empty")
    known_limits = report.get("known_limits") if isinstance(report.get("known_limits"), dict) else {}
    if known_limits.get("missing_markers"):
        errors.append("report.known_limits.missing_markers must be empty")
    return errors


def render_markdown(report: dict[str, Any]) -> str:
    source = report.get("source", {})
    packet = report.get("review_packet", {})
    summary = report.get("summary", {})
    lines = [
        "# Release-Candidate PR Readiness Packet",
        "",
        f"Status: `{report.get('status')}`",
        f"Decision: `{report.get('decision')}`",
        f"Branch: `{source.get('branch')}`",
        f"Commit: `{source.get('commit')}`",
        f"Generated at: `{report.get('generated_at')}`",
        "",
        "## Summary",
        "",
        f"- Source clean: `{summary.get('source_clean')}`",
        f"- Missing docs: `{summary.get('missing_doc_count')}`",
        f"- Missing scripts: `{summary.get('missing_script_count')}`",
        f"- Incomplete prior phases: `{summary.get('incomplete_phase_count')}`",
        f"- Forbidden tracked paths: `{summary.get('forbidden_tracked_path_count')}`",
        f"- Missing known-limit markers: `{summary.get('missing_limit_marker_count')}`",
        "",
        "## Supported Scope",
        "",
    ]
    lines.extend(f"- {item}" for item in packet.get("supported_scope", []))
    lines.extend(["", "## Non-Goals", ""])
    lines.extend(f"- {item}" for item in packet.get("non_goals", []))
    lines.extend(["", "## Required Proof Commands", ""])
    lines.extend(f"- `{item}`" for item in packet.get("proof_commands", []))
    lines.extend(
        [
            "",
            "## Draft PR Body",
            "",
            "```text",
            "M14 release-candidate handoff and chat-quality readiness",
            "",
            f"Branch: {source.get('branch')}",
            f"Commit: {source.get('commit')}",
            "",
            "This branch packages the current release-candidate handoff and Priority 0 chat-quality validation path.",
            "It keeps advanced refactor, real apply, and raw 1M-token prompting out of scope.",
            "",
            "Validation to review:",
        ]
    )
    lines.extend(f"- {item}" for item in packet.get("proof_commands", []))
    lines.extend(
        [
            "",
            f"Rollback: {packet.get('rollback_path')}",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def run_release_candidate_pr_readiness(config: ReleaseCandidatePrReadinessConfig) -> dict[str, Any]:
    config_root = config.config_root.resolve()
    policy = load_policy(config_root, config.policy_path)
    errors = validate_policy(policy)
    branch = git_lines(config_root, "branch", "--show-current")[0]
    commit = git_lines(config_root, "rev-parse", "HEAD")[0]
    upstream_lines = git_lines(config_root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", check=False)
    upstream = upstream_lines[0] if upstream_lines else None
    status_lines = git_lines(config_root, "status", "--short")
    roadmap_text = resolve_path(config_root, "docs/ACTIONABLE_WORKFLOW_ROADMAP.md").read_text(encoding="utf-8")
    docs = doc_checks(config_root, string_list(policy.get("required_docs")))
    scripts = script_checks(config_root, string_list(policy.get("required_scripts")))
    phase_status_map = phase_statuses(roadmap_text, int_list(policy.get("required_prior_phases")))
    forbidden = tracked_forbidden_paths(
        config_root,
        string_list(policy.get("forbidden_tracked_path_fragments")),
        allowed_prefixes=string_list(policy.get("allowed_tracked_path_prefixes")),
    )
    known_limits = known_limit_checks(config_root, string_list(policy.get("required_known_limit_markers")))
    report = build_report(
        policy=policy,
        branch=branch,
        commit=commit,
        upstream=upstream,
        status_lines=status_lines,
        docs=docs,
        scripts=scripts,
        phase_status_map=phase_status_map,
        forbidden_tracked_paths=forbidden,
        known_limits=known_limits,
        errors=errors,
    )
    validation_errors = validate_report(report, policy)
    if validation_errors:
        report["status"] = ReleaseCandidateReadinessStatus.FAILED.value
        report["decision"] = ReleaseCandidateReadinessDecision.BLOCKED.value
        report["errors"] = report["errors"] + validation_errors
    output_path = config.output_path or default_report_path(config_root)
    if not output_path.is_absolute():
        output_path = config_root / output_path
    markdown_path = config.markdown_output_path or default_markdown_path(output_path)
    if not markdown_path.is_absolute():
        markdown_path = config_root / markdown_path
    report["markdown_output_path"] = str(markdown_path.resolve())
    write_json(output_path, report)
    write_text(markdown_path, render_markdown(report))
    return report
