"""Connector actor context validation and replay-safe audit helpers."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from http import HTTPStatus
from typing import Any


SCHEMA_VERSION = 1


class ConnectorIdentityError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "connector_identity_error",
        status: HTTPStatus = HTTPStatus.FORBIDDEN,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.status = status
        self.details = details or {}


def stable_json_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def required_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConnectorIdentityError(
            f"actor_context.{label} must be a non-empty string.",
            code="invalid_connector_actor_context",
            status=HTTPStatus.FORBIDDEN,
        )
    return value.strip()


def scope_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ConnectorIdentityError(
            f"actor_context.{label} must be a list of non-empty strings.",
            code="invalid_connector_actor_context",
            status=HTTPStatus.FORBIDDEN,
        )
    return sorted(set(item.strip() for item in value))


def parse_utc_datetime(value: Any, label: str) -> datetime:
    raw_value = required_string(value, label)
    try:
        normalized = raw_value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ConnectorIdentityError(
            f"actor_context.{label} must be an ISO-8601 UTC timestamp.",
            code="invalid_connector_actor_context",
            status=HTTPStatus.FORBIDDEN,
        ) from exc
    if parsed.tzinfo is None:
        raise ConnectorIdentityError(
            f"actor_context.{label} must include a timezone.",
            code="invalid_connector_actor_context",
            status=HTTPStatus.FORBIDDEN,
        )
    return parsed.astimezone(timezone.utc)


def validate_actor_context(actor_context: Any, *, now: datetime | None = None) -> dict[str, Any]:
    if not isinstance(actor_context, dict):
        raise ConnectorIdentityError(
            "connector.invoke requires actor_context.",
            code="missing_connector_actor_context",
            status=HTTPStatus.FORBIDDEN,
        )
    if actor_context.get("schema_version") != SCHEMA_VERSION:
        raise ConnectorIdentityError(
            "actor_context.schema_version must be 1.",
            code="invalid_connector_actor_context",
            status=HTTPStatus.FORBIDDEN,
        )
    actor_id = required_string(actor_context.get("actor_id"), "actor_id")
    if actor_id.lower() in {"anonymous", "unknown", "guest"}:
        raise ConnectorIdentityError(
            "anonymous actor_context.actor_id is not allowed for connector invocation.",
            code="anonymous_connector_actor_context",
            status=HTTPStatus.FORBIDDEN,
        )
    auth_subject = required_string(actor_context.get("auth_subject"), "auth_subject")
    session_id = required_string(actor_context.get("session_id"), "session_id")
    request_id = required_string(actor_context.get("request_id"), "request_id")
    granted_scopes = scope_list(actor_context.get("granted_scopes", []), "granted_scopes")
    issued_at = parse_utc_datetime(actor_context.get("issued_at_utc"), "issued_at_utc")
    expires_at = parse_utc_datetime(actor_context.get("expires_at_utc"), "expires_at_utc")
    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if expires_at <= issued_at:
        raise ConnectorIdentityError(
            "actor_context.expires_at_utc must be after issued_at_utc.",
            code="invalid_connector_actor_context",
            status=HTTPStatus.FORBIDDEN,
        )
    if expires_at <= current_time:
        raise ConnectorIdentityError(
            "actor_context is expired.",
            code="stale_connector_actor_context",
            status=HTTPStatus.FORBIDDEN,
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "actor_id": actor_id,
        "auth_subject_hash": stable_json_hash(auth_subject),
        "session_id": session_id,
        "request_id": request_id,
        "granted_scopes": granted_scopes,
        "issued_at_utc": issued_at.isoformat().replace("+00:00", "Z"),
        "expires_at_utc": expires_at.isoformat().replace("+00:00", "Z"),
        "actor_context_valid": True,
    }


def actor_context_for_artifact(actor_context: Any) -> dict[str, Any] | None:
    if not isinstance(actor_context, dict):
        return None
    artifact: dict[str, Any] = {
        "schema_version": actor_context.get("schema_version"),
        "actor_id": actor_context.get("actor_id") if isinstance(actor_context.get("actor_id"), str) else None,
        "session_id": actor_context.get("session_id") if isinstance(actor_context.get("session_id"), str) else None,
        "request_id": actor_context.get("request_id") if isinstance(actor_context.get("request_id"), str) else None,
        "granted_scopes": actor_context.get("granted_scopes") if isinstance(actor_context.get("granted_scopes"), list) else [],
        "issued_at_utc": actor_context.get("issued_at_utc") if isinstance(actor_context.get("issued_at_utc"), str) else None,
        "expires_at_utc": actor_context.get("expires_at_utc") if isinstance(actor_context.get("expires_at_utc"), str) else None,
        "raw_auth_subject_stored": False,
    }
    auth_subject = actor_context.get("auth_subject")
    if isinstance(auth_subject, str) and auth_subject:
        artifact["auth_subject_hash"] = stable_json_hash(auth_subject)
    return artifact


def replay_safe_argument_summary(arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "argument_hash": stable_json_hash(arguments),
        "argument_keys": sorted(arguments),
        "raw_arguments_stored": False,
    }
