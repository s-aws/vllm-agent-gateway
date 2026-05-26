"""Shared workflow invocation contracts.

These contracts are intentionally small. Workflow-specific modules own their
request objects, while this module provides the common result shape a future
controller service can return without knowing CLI internals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class WorkflowStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELED = "canceled"


@dataclass(frozen=True)
class InvocationResult:
    workflow: str
    status: WorkflowStatus
    artifact_paths: dict[str, str] = field(default_factory=dict)
    summary_text: str | None = None
    failures: list[dict[str, Any]] = field(default_factory=list)
    resume_key: dict[str, Any] | None = None
    report: dict[str, Any] | None = None
    run_id: str | None = None

    def to_dict(self, include_report: bool = False) -> dict[str, Any]:
        value: dict[str, Any] = {
            "workflow": self.workflow,
            "status": self.status.value,
            "artifact_paths": self.artifact_paths,
            "summary_text": self.summary_text,
            "failures": self.failures,
            "resume_key": self.resume_key,
            "run_id": self.run_id,
        }
        if include_report:
            value["report"] = self.report
        return value


def string_artifact_paths(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items() if isinstance(key, str)}


def list_failures(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
