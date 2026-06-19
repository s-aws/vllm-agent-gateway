# Connector Catalog

The connector catalog is the governed admission surface for future external API connectors.

Current status: Phase 284 governed connector registration, enabled local-stub mediation, and release-gated enablement. The project can validate connector manifests, append connector metadata to `runtime/connectors.json` through an approval-gated workflow, require release-gate proof before `enabled=true`, and invoke enabled `local_stub` connector operations through a controller-owned path. It does not call external APIs, expose raw MCP, or route natural-language prompts to connector operations yet.

## When To Use It

Use connector catalog validation when proposing a future connector contract and you need to prove:

- the connector has a typed manifest
- operations are explicitly declared
- auth and safety policies are present
- write operations require approval
- eval fixture references exist
- no raw MCP or direct model-to-tool bypass is allowed
- validation produces artifacts without mutating runtime registries or target repositories

Do not use it for live API calls. Current invocation support is limited to enabled `local_stub` connector entries in `runtime/connectors.json`.

## Endpoint

```text
POST /v1/controller/connector-catalog/validations
POST /v1/controller/connector-catalog/registrations
POST /v1/controller/connectors/invocations
```

Default controller base URL:

```text
http://127.0.0.1:8400
```

## Manifest Shape

```json
{
  "schema_version": 1,
  "kind": "connector_admission_manifest",
  "connector": {
    "id": "ticketing_stub",
    "owner": "agentic_agents",
    "description": "Stub ticketing connector used only to validate governed connector contracts.",
    "protocol": "local_stub",
    "mediation": "controller_owned",
    "auth": {
      "type": "none_for_stub",
      "required_scopes": []
    },
    "safety": {
      "data_classification": "public",
      "pii_policy": "not_allowed",
      "external_network": false,
      "raw_mcp_allowed": false,
      "direct_model_tool_access": false
    },
    "operations": [
      {
        "id": "lookup_ticket",
        "description": "Look up one stub ticket by identifier for validation fixtures.",
        "operation_class": "read",
        "approval_required": false,
        "input_schema": {
          "type": "object",
          "properties": {
            "ticket_id": {"type": "string"}
          },
          "required": ["ticket_id"]
        },
        "output_schema": {
          "type": "object",
          "properties": {
            "status": {"type": "string"}
          },
          "required": ["status"]
        },
        "allowed_workflows": ["workflow_router.plan"],
        "eval_fixtures": ["connector_eval.ticketing_stub.lookup_ticket.basic"]
      }
    ]
  }
}
```

## Allowed Values

Protocols:

- `local_stub`
- `https_json`
- `mcp_mediated`

Mediation:

- `controller_owned`

Auth types:

- `none_for_stub`
- `service_read_only`
- `oauth_user_scope`

Operation classes:

- `read`
- `dry_run`
- `write`

Data classifications:

- `public`
- `internal`
- `sensitive`

PII policies:

- `not_allowed`
- `masked_required`
- `policy_required`

## Safety Rules

- `raw_mcp_allowed=true` is rejected.
- `direct_model_tool_access=true` is rejected.
- `none_for_stub` auth is accepted only for `local_stub`.
- `oauth_user_scope` must declare at least one required scope.
- `service_read_only` cannot expose write operations.
- write operations must set `approval_required=true`.
- each operation must declare at least one allowed workflow and one eval fixture reference.
- validation must not modify `runtime/connectors.json`, `runtime/tools.json`, `runtime/workflows.json`, `runtime/roles.json`, or any target repository.
- registration appends only to `runtime/connectors.json`.
- draft registration requires explicit approval and installs `enabled=false`.
- enabled registration requires explicit approval plus a passed connector eval release-gate report.
- registration must not modify tools, workflows, roles, target repositories, or external services.
- connector invocation is supported only for `enabled=true` `local_stub` connectors.
- connector invocation writes request, invocation, and run-state artifacts.
- connector invocation must not call external networks, mutate runtime registries, mutate target repositories, use raw MCP, or expose direct model-to-connector tool access.
- write-class connector operations are dry-run only in the current phase and require explicit connector invocation approval.

## Invocation Request

```json
{
  "workflow": "connector.invoke",
  "schema_version": 1,
  "connector_id": "ticketing_stub",
  "operation_id": "lookup_ticket",
  "arguments": {
    "ticket_id": "T-123"
  },
  "dry_run": true
}
```

## Registration Request

Draft registration:

```json
{
  "workflow": "connector_catalog.register",
  "schema_version": 1,
  "connector_manifest": {
    "schema_version": 1,
    "kind": "connector_admission_manifest",
    "connector": {
      "id": "ticketing_stub"
    }
  },
  "approval": {
    "status": "approved_for_connector_catalog_registration",
    "scope": "connector_catalog_registration",
    "runtime_connector_append": true,
    "enabled": false,
    "approval_refs": ["approved-registration-record"]
  }
}
```

Enabled registration:

```json
{
  "workflow": "connector_catalog.register",
  "schema_version": 1,
  "connector_manifest": {
    "schema_version": 1,
    "kind": "connector_admission_manifest",
    "connector": {
      "id": "ticketing_stub"
    }
  },
  "release_gate_report_path": "runtime-state/connector-eval-release-gate/ticketing-stub-report.json",
  "approval": {
    "status": "approved_for_connector_catalog_registration",
    "scope": ["connector_catalog_registration", "connector_enablement"],
    "runtime_connector_append": true,
    "enabled": true,
    "approval_refs": ["approved-enable-record"]
  }
}
```

The abbreviated manifest above is illustrative. The real request must include the full manifest shape shown earlier in this document.

Write-class dry runs require approval:

```json
{
  "workflow": "connector.invoke",
  "schema_version": 1,
  "connector_id": "ticketing_writer_stub",
  "operation_id": "update_ticket",
  "arguments": {
    "ticket_id": "T-123"
  },
  "dry_run": true,
  "approval": {
    "status": "approved_for_connector_invocation",
    "scope": "connector_invocation",
    "connector_id": "ticketing_writer_stub",
    "operation_id": "update_ticket",
    "approval_refs": ["approved-change-record"]
  }
}
```

## Artifacts

Each validation run writes:

- `request.json`
- `connector-catalog-validation.json`
- `run-state.json`

The response summary includes `validation_status`, `connector_id`, `operation_count`, `runtime_registry_changed`, `runtime_behavior_changed`, and `target_repository_changed`.

Each invocation run writes:

- `request.json`
- `connector-invocation.json`
- `run-state.json`

The response summary includes `invocation_status`, `connector_id`, `operation_id`, `operation_class`, `dry_run`, `controller_owned_path`, `raw_mcp_used`, `direct_model_tool_access_used`, `external_network_called`, `runtime_registry_changed`, and `target_repository_changed`.

Each registration run writes:

- `request.json`
- `connector-catalog-validation-before-registration.json`
- `connector-catalog-registration.json`
- `rollback-instructions.json`
- `run-state.json`

The response summary includes `registration_status`, `connector_id`, `enabled`, `changed_runtime_files`, `runtime_connector_registry_changed`, `runtime_tool_registry_changed`, `runtime_workflow_registry_changed`, `runtime_role_registry_changed`, `target_repository_changed`, `release_gate_required`, and `release_gate_passed`.

## Related Docs

- [Controller Service](README.controller-service.md)
- [Connector Eval Release Gate](README.connector-eval-release-gate.md)
- [Current Project Architecture](docs/CURRENT_PROJECT_ARCHITECTURE.md)
- [Project Milestones](docs/PROJECT_MILESTONES.md)
- [Examples](docs/examples/connector-catalog.md)
