"""Shared controller-envelope extraction helpers."""

from __future__ import annotations

import json
from typing import Any


class ControllerEnvelopeError(ValueError):
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


def require_controller_request_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ControllerEnvelopeError(f"{label} must be a JSON object.", code="invalid_controller_envelope")
    return value


def decode_json_object_text(value: str) -> dict[str, Any] | None:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return None
    return decoded if isinstance(decoded, dict) else None


def envelopes_from_message_content(content: Any) -> list[dict[str, Any]]:
    if isinstance(content, str):
        decoded = decode_json_object_text(content)
        if isinstance(decoded, dict) and "agentic_controller_request" in decoded:
            return [
                require_controller_request_object(
                    decoded["agentic_controller_request"],
                    "agentic_controller_request",
                )
            ]
        return []
    if isinstance(content, list):
        found: list[dict[str, Any]] = []
        for part in content:
            if not isinstance(part, dict) or part.get("type") != "text" or not isinstance(part.get("text"), str):
                continue
            decoded = decode_json_object_text(part["text"])
            if isinstance(decoded, dict) and "agentic_controller_request" in decoded:
                found.append(
                    require_controller_request_object(
                        decoded["agentic_controller_request"],
                        "agentic_controller_request",
                    )
                )
        return found
    return []


def find_controller_envelopes(payload: dict[str, Any], *, require_message_objects: bool = False) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if "agentic_controller_request" in payload:
        found.append(
            require_controller_request_object(
                payload["agentic_controller_request"],
                "agentic_controller_request",
            )
        )
    messages = payload.get("messages")
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                if require_message_objects:
                    raise ControllerEnvelopeError("messages entries must be objects.", code="invalid_messages")
                continue
            found.extend(envelopes_from_message_content(message.get("content")))
    return found


def require_single_controller_envelope(envelopes: list[dict[str, Any]]) -> dict[str, Any] | None:
    if len(envelopes) > 1:
        raise ControllerEnvelopeError(
            "Exactly one agentic_controller_request envelope is allowed.",
            code="multiple_controller_envelopes",
        )
    return envelopes[0] if envelopes else None


def select_latest_controller_envelope(
    payload: dict[str, Any],
    *,
    require_message_objects: bool = False,
) -> dict[str, Any] | None:
    """Select the active controller envelope from an OpenAI-style chat payload.

    Chat harnesses such as AnythingLLM may include previous user messages in
    request history. Those messages can contain older explicit controller
    envelopes. For message-based envelopes, the active request is only the
    latest chat message. Older history must not trigger controller routing when
    the current user message is ordinary model chat. Top-level envelopes remain
    exclusive because a top-level request plus an active message envelope is
    ambiguous.
    """

    top_level: dict[str, Any] | None = None
    if "agentic_controller_request" in payload:
        top_level = require_controller_request_object(
            payload["agentic_controller_request"],
            "agentic_controller_request",
        )

    active_message_envelope: dict[str, Any] | None = None
    messages = payload.get("messages")
    active_message: dict[str, Any] | None = None
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                if require_message_objects:
                    raise ControllerEnvelopeError("messages entries must be objects.", code="invalid_messages")
                continue
            active_message = message
    if active_message is not None:
        envelopes = envelopes_from_message_content(active_message.get("content"))
        if len(envelopes) > 1:
            raise ControllerEnvelopeError(
                "Exactly one agentic_controller_request envelope is allowed in the active message.",
                code="multiple_controller_envelopes",
            )
        if envelopes:
            active_message_envelope = envelopes[0]

    if top_level is not None and active_message_envelope is not None:
        raise ControllerEnvelopeError(
            "Exactly one agentic_controller_request envelope is allowed.",
            code="multiple_controller_envelopes",
        )
    return top_level if top_level is not None else active_message_envelope
