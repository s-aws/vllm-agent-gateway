# EIG-1 Connector Archetype Breadth Matrix

Status: Phase 288 matrix.

Milestone mapping: M26 EIG-1 Connector Archetype Breadth.

This matrix defines the first breadth-confidence target for EIG-1. It prevents governed connector work from being considered proven after only the original `ticketing_stub` happy path.

## Scope Boundary

This phase defines deterministic local fixture plans only. It does not authorize real external API calls, real OAuth token exchange, enterprise-specific connectors, raw MCP exposure, direct model-to-tool connector access, production connector rollout, or runtime registry mutation.

Every executable fixture in Phase 289 must remain:

- `protocol=local_stub`,
- `mediation=controller_owned`,
- deterministic,
- local to this repository or disposable test roots,
- invoked only through `connector.invoke`,
- validated through the existing connector catalog and mediation code paths.

`https_json` and `mcp_mediated` may appear only as validation-classification cases until a later approved milestone changes the execution boundary.

## Industry Basis

The breadth target follows common enterprise integration expectations:

- typed operation contracts before execution,
- explicit connector allowlists,
- deny-by-default admission and invocation,
- read/write operation separation,
- least exposure for result summaries,
- controller-owned mediation,
- negative controls for bypass attempts,
- release-gate proof before enablement,
- replay-safe audit without raw argument storage.

## Archetype Summary

| Archetype ID | Connector ID | Purpose | Operation Classes | Current Execution State |
| --- | --- | --- | --- | --- |
| `work_tracking` | `work_tracking_stub` | Simulate issue, ticket, task, or support-work lookup plus safe dry-run update. | `read`, `write` dry-run only | Phase 289 fixture candidate |
| `knowledge_lookup` | `knowledge_lookup_stub` | Simulate policy, runbook, or document search/read retrieval. | `read` | Phase 289 fixture candidate |
| `business_record` | `business_record_stub` | Simulate structured account, order, customer, metric, or report lookup. | `read` | Phase 289 fixture candidate |

These names are generic by design. They are not vendor-specific connectors.

## Archetype A: Work Tracking

Goal: prove the connector path handles the most common coding-agent adjacent enterprise request: inspect a work item and prepare a safe change/update without applying it.

| Field | Planned Value |
| --- | --- |
| Connector ID | `work_tracking_stub` |
| Description | Deterministic local stub for work-ticket status lookup and dry-run status/comment update. |
| Protocol | `local_stub` |
| Auth mode | `oauth_user_scope` for Phase 289 breadth; `none_for_stub` may remain covered by the original sample. |
| Required scopes | `work:read` for lookup; `work:write` for dry-run update. |
| Data classification | `internal` |
| PII policy | `masked_required` if fixture records contain synthetic names or requester fragments; otherwise `not_allowed`. |
| External network | `false` |
| Raw MCP/direct model tool access | `false` |

### Planned Operations

| Operation ID | Class | Approval | Input Shape | Output Shape | Eval Fixtures |
| --- | --- | --- | --- | --- | --- |
| `lookup_work_item` | `read` | `false` | `work_item_id: string`, optional `include_history: boolean` | `status: string`, `title: string`, `priority: string`, `assignee_status: string` | `connector_eval.work_tracking.lookup_work_item.basic`, `connector_eval.work_tracking.lookup_work_item.json`, `connector_eval.work_tracking.lookup_work_item.holdout` |
| `dry_run_update_work_item` | `write` | `true` | `work_item_id: string`, `new_status: string`, `comment: string`, optional `notify_watchers: boolean` | `status: string`, `would_update: boolean`, `requires_approval: boolean` | `connector_eval.work_tracking.dry_run_update_work_item.basic`, `connector_eval.work_tracking.dry_run_update_work_item.denial`, `connector_eval.work_tracking.dry_run_update_work_item.holdout` |

### Required Cases

| Case ID | Type | Purpose | Expected Proof |
| --- | --- | --- | --- |
| `EIG1-WORK-R1` | required | Validate manifest with one read operation and one write-class dry-run operation. | `connector_catalog.validate` passes with two operation checks. |
| `EIG1-WORK-R2` | required | Invoke read operation through `connector.invoke` with sufficient actor scope. | Controller-owned audit says allowed and no external network used. |
| `EIG1-WORK-R3` | required | Invoke write-class operation with approval and `dry_run=true`. | Result is dry-run only; audit binds actor/session/request/operation. |
| `EIG1-WORK-N1` | negative control | Attempt write-class invocation without approval. | Fail closed with `missing_connector_invocation_approval`. |
| `EIG1-WORK-N2` | negative control | Attempt write-class invocation with `dry_run=false`. | Fail closed with `connector_write_execution_not_supported`. |
| `EIG1-WORK-N3` | negative control | Attempt direct raw tool/MCP style bypass. | Fail closed through catalog/mediation checks; no connector result emitted. |
| `EIG1-WORK-H1` | holdout | Ask for a work item using alternate natural wording in a later runtime chat proof. | Phase 295 blind-baseline comparison if exposed to chat. |

## Archetype B: Knowledge Lookup

Goal: prove a read-only connector shape for policy, runbook, and document retrieval without conflating it with repository file search or web access.

| Field | Planned Value |
| --- | --- |
| Connector ID | `knowledge_lookup_stub` |
| Description | Deterministic local stub for bounded policy/runbook/document search and read-only answer support. |
| Protocol | `local_stub` |
| Auth mode | `service_read_only` or `oauth_user_scope`; Phase 289 should choose one and document the reason. |
| Required scopes | `knowledge:read` if using `oauth_user_scope`; empty for `service_read_only`. |
| Data classification | `internal` |
| PII policy | `not_allowed` |
| External network | `false` |
| Raw MCP/direct model tool access | `false` |

### Planned Operations

| Operation ID | Class | Approval | Input Shape | Output Shape | Eval Fixtures |
| --- | --- | --- | --- | --- | --- |
| `search_documents` | `read` | `false` | `query: string`, optional `limit: integer`, optional `filters: object` | `status: string`, `result_count: integer`, `top_titles: array` | `connector_eval.knowledge_lookup.search_documents.basic`, `connector_eval.knowledge_lookup.search_documents.filtered`, `connector_eval.knowledge_lookup.search_documents.holdout` |
| `read_document_summary` | `read` | `false` | `document_id: string`, optional `include_sections: array` | `status: string`, `summary: string`, `source_refs: array` | `connector_eval.knowledge_lookup.read_document_summary.basic`, `connector_eval.knowledge_lookup.read_document_summary.holdout` |

### Required Cases

| Case ID | Type | Purpose | Expected Proof |
| --- | --- | --- | --- |
| `EIG1-KNOW-R1` | required | Validate manifest with two read-only operations and bounded schema fields. | `connector_catalog.validate` passes. |
| `EIG1-KNOW-R2` | required | Invoke search through `connector.invoke` with valid typed arguments. | Result is deterministic and audit says read-only/no mutation. |
| `EIG1-KNOW-R3` | required | Invoke document summary with array input. | Schema validator accepts valid arrays and rejects malformed arrays. |
| `EIG1-KNOW-N1` | negative control | Attempt a write operation on a service-read-only connector. | Catalog rejects or fixture omits write; no ad hoc write path is added. |
| `EIG1-KNOW-N2` | negative control | Provide unsupported filter or unknown argument. | Mediation fails with `unsupported_connector_argument`. |
| `EIG1-KNOW-H1` | holdout | Ask for a policy answer using broad natural wording in a later runtime chat proof. | Phase 295 blind-baseline comparison if exposed to chat. |

## Archetype C: Structured Business Record

Goal: prove typed lookup over structured records with common scalar, boolean, array, object, and numeric fields without exposing real customer, finance, or analytics systems.

| Field | Planned Value |
| --- | --- |
| Connector ID | `business_record_stub` |
| Description | Deterministic local stub for account/order/report-style structured lookup. |
| Protocol | `local_stub` |
| Auth mode | `oauth_user_scope` |
| Required scopes | `records:read` |
| Data classification | `internal` |
| PII policy | `masked_required` if synthetic customer/member-like identifiers appear in fixture output. |
| External network | `false` |
| Raw MCP/direct model tool access | `false` |

### Planned Operations

| Operation ID | Class | Approval | Input Shape | Output Shape | Eval Fixtures |
| --- | --- | --- | --- | --- | --- |
| `lookup_business_record` | `read` | `false` | `record_id: string`, `include_metrics: boolean`, optional `filters: object` | `status: string`, `record_state: string`, `metric_count: integer`, `flags: array` | `connector_eval.business_record.lookup_business_record.basic`, `connector_eval.business_record.lookup_business_record.metrics`, `connector_eval.business_record.lookup_business_record.holdout` |
| `query_business_records` | `read` | `false` | `query: string`, optional `limit: integer`, optional `tags: array` | `status: string`, `result_count: integer`, `record_ids: array` | `connector_eval.business_record.query_business_records.basic`, `connector_eval.business_record.query_business_records.holdout` |

### Required Cases

| Case ID | Type | Purpose | Expected Proof |
| --- | --- | --- | --- |
| `EIG1-REC-R1` | required | Validate manifest with structured object, boolean, integer, array, required, and optional fields. | `connector_catalog.validate` passes and Phase 290 schema matrix expands validation detail. |
| `EIG1-REC-R2` | required | Invoke structured lookup with sufficient `records:read` scope. | Audit says allowed with replay-safe argument hash. |
| `EIG1-REC-R3` | required | Invoke query with optional arrays and integer limit. | Valid arguments pass; malformed integer/array types fail closed. |
| `EIG1-REC-N1` | negative control | Missing `records:read` scope. | Fail closed with scope recovery guidance. |
| `EIG1-REC-N2` | negative control | Unknown argument or malformed nested object. | Fail closed before connector result. |
| `EIG1-REC-H1` | holdout | Natural prompt asks for a business record summary with ambiguous fields. | Phase 295 blind-baseline comparison if exposed to chat. |

## Cross-Archetype Negative Controls

Phase 289 must prove these against the breadth fixture set:

| Control ID | Requirement | Expected Result |
| --- | --- | --- |
| `EIG1-X-N1` | Unknown connector ID | `unknown_connector` or catalog validation failure; no result payload. |
| `EIG1-X-N2` | Disabled connector invocation | `connector_not_enabled`; no operation execution. |
| `EIG1-X-N3` | Unknown operation ID | `unknown_connector_operation`; no result payload. |
| `EIG1-X-N4` | Unsupported argument | `unsupported_connector_argument`. |
| `EIG1-X-N5` | Missing required argument | `missing_connector_argument`. |
| `EIG1-X-N6` | Non-`local_stub` execution attempt | `connector_protocol_not_executable` unless future approved milestone changes this. |
| `EIG1-X-N7` | `raw_mcp_allowed=true` | `raw_mcp_bypass_not_allowed`. |
| `EIG1-X-N8` | `direct_model_tool_access=true` | `direct_model_tool_bypass_not_allowed`. |

## Phase 289 Fixture Inputs

Phase 289 should create deterministic fixture manifests or generated test fixtures with the following minimum counts:

| Requirement | Minimum |
| --- | --- |
| Connector archetypes | 3 |
| Valid connector manifests | 3 |
| Read operations | at least 1 per archetype |
| Write-class dry-run operations | at least 1 across the set |
| Required positive invocation cases | at least 5 |
| Cross-archetype negative controls | at least 8 |
| Holdout references | at least 1 per archetype |

The implementation should avoid adding a second validator. The existing connector catalog, mediation, identity, release-gate, and audit modules remain the authority.

## Deferred Items

| Deferred Item | Reason |
| --- | --- |
| Real Workday, Snowflake, SAP, GitHub, Jira, ServiceNow, or other vendor connectors | Vendor scope would turn this into production integration work. |
| Real OAuth token exchange or refresh | EIG-2 currently validates actor and scope contracts with local deterministic context, not identity-provider integration. |
| Raw MCP server/tool exposure | Direct model-to-tool access violates the approved controller-owned connector path. |
| External network execution | Current proof target is local deterministic mediation. |
| Production connector registry rollout | Release-gate breadth is Phase 291-292 and remains local/proof oriented. |

## Acceptance Summary

Phase 288 is complete when this matrix is linked from the documentation index and the roadmap records that future EIG-1 fixture implementation can proceed from these concrete archetypes, operation shapes, case IDs, and deferred boundaries without guessing or expanding scope.
