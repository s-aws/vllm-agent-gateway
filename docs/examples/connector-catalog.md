# Connector Catalog Examples

Validate a governed connector admission manifest without mutating runtime registries:

```bash
curl -s http://127.0.0.1:8400/v1/controller/connector-catalog/validations \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow": "connector_catalog.validate",
    "schema_version": 1,
    "connector_manifest": {
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
  }' | python -m json.tool
```

Expected success markers:

```text
"workflow": "connector_catalog.validate"
"status": "completed"
"validation_status": "passed"
"runtime_registry_changed": false
"runtime_behavior_changed": false
"target_repository_changed": false
```

Rejected raw MCP bypass example:

```json
{
  "safety": {
    "raw_mcp_allowed": true
  }
}
```

Expected rejection code:

```text
raw_mcp_bypass_not_allowed
```

Rejected write operation example:

```json
{
  "operation_class": "write",
  "approval_required": false
}
```

Expected rejection code:

```text
unsafe_connector_write_operation
```

Run the focused regression gate:

```bash
python -m pytest tests/regression/test_connector_catalog.py -v
```

Register a validated connector as a disabled draft:

```bash
curl -s http://127.0.0.1:8400/v1/controller/connector-catalog/registrations \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow": "connector_catalog.register",
    "schema_version": 1,
    "connector_manifest": {
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
    },
    "approval": {
      "status": "approved_for_connector_catalog_registration",
      "scope": "connector_catalog_registration",
      "runtime_connector_append": true,
      "enabled": false,
      "approval_refs": ["approved-registration-record"]
    }
  }' | python -m json.tool
```

Expected draft registration markers:

```text
"workflow": "connector_catalog.register"
"status": "completed"
"registration_status": "installed"
"enabled": false
"changed_runtime_files": ["runtime/connectors.json"]
"runtime_tool_registry_changed": false
"runtime_workflow_registry_changed": false
"runtime_role_registry_changed": false
"target_repository_changed": false
```

Enablement uses the same registration endpoint, but requires `approval.scope` to include `connector_enablement` and `release_gate_report_path` to point at a passed connector eval release-gate report:

```json
{
  "workflow": "connector_catalog.register",
  "schema_version": 1,
  "connector_manifest": "<full connector_admission_manifest>",
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

Expected enablement markers:

```text
"enabled": true
"release_gate_required": true
"release_gate_passed": true
```

Expected registration rejection codes:

```text
missing_connector_catalog_registration_approval
invalid_connector_catalog_registration_approval
missing_connector_release_gate_proof
connector_release_gate_not_passed
connector_release_gate_mismatch
connector_release_gate_not_ship
connector_already_registered
```

Invoke an enabled local stub connector:

```bash
curl -s http://127.0.0.1:8400/v1/controller/connectors/invocations \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow": "connector.invoke",
    "schema_version": 1,
    "connector_id": "ticketing_stub",
    "operation_id": "lookup_ticket",
    "arguments": {
      "ticket_id": "T-123"
    },
    "dry_run": true,
    "actor_context": {
      "schema_version": 1,
      "actor_id": "tester-actor",
      "auth_subject": "local-subject:tester-actor",
      "session_id": "session-001",
      "request_id": "request-001",
      "granted_scopes": ["tickets:read"],
      "issued_at_utc": "2026-01-01T00:00:00Z",
      "expires_at_utc": "2999-01-01T00:00:00Z"
    }
  }' | python -m json.tool
```

Expected success markers for an enabled `local_stub` connector:

```text
"workflow": "connector.invoke"
"status": "completed"
"invocation_status": "completed"
"actor_bound": true
"authorization_status": "allowed"
"controller_owned_path": true
"raw_mcp_used": false
"direct_model_tool_access_used": false
"external_network_called": false
"runtime_registry_changed": false
"target_repository_changed": false
```

Write-class connector dry-run approval:

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
  "actor_context": {
    "schema_version": 1,
    "actor_id": "tester-actor",
    "auth_subject": "local-subject:tester-actor",
    "session_id": "session-001",
    "request_id": "request-002",
    "granted_scopes": ["tickets:write"],
    "issued_at_utc": "2026-01-01T00:00:00Z",
    "expires_at_utc": "2999-01-01T00:00:00Z"
  },
  "approval": {
    "status": "approved_for_connector_invocation",
    "scope": "connector_invocation",
    "connector_id": "ticketing_writer_stub",
    "operation_id": "update_ticket",
    "approval_refs": ["approved-change-record"]
  }
}
```

Expected rejection codes:

```text
unknown_connector
connector_not_enabled
missing_connector_actor_context
anonymous_connector_actor_context
stale_connector_actor_context
connector_scope_denied
raw_mcp_bypass_not_allowed
direct_model_tool_bypass_not_allowed
unsupported_connector_argument
missing_connector_invocation_approval
connector_write_execution_not_supported
```

Validate a connector invocation audit artifact:

```bash
python scripts/validate_connector_user_scope_audit.py \
  --report-path runtime-state/controller-artifacts/connector-invocations/<run-id>/connector-invocation.json
```

Expected audit markers:

```text
CONNECTOR USER SCOPE AUDIT PASS
"raw_auth_subject_stored": false
"raw_arguments_stored": false
```
