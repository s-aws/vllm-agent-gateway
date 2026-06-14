"""Shared large-context strategy identifiers."""

from __future__ import annotations

from enum import Enum


class ContextStrategy(str, Enum):
    DIRECT_CONTEXT = "direct_context"
    RETRIEVAL = "retrieval"
    CHUNKED_INVESTIGATION = "chunked_investigation"
    SUMMARIZATION = "summarization"
    ARTIFACT_PAGING = "artifact_paging"
    REFUSAL = "refusal"


class ContextStrategyStatus(str, Enum):
    SELECTED = "selected"
    BLOCKED = "blocked"


class ContextStrategyExecutionPath(str, Enum):
    EXISTING_READ_ONLY_WORKFLOW = "existing_read_only_workflow"
    LARGE_CONTEXT_RETRIEVAL_ANSWER = "large_context.retrieval_answer"
    LARGE_CONTEXT_CHUNKED_INVESTIGATION = "large_context.chunked_investigation"
    NOT_EXECUTABLE_YET = "not_executable_yet"
    NONE = "none"
