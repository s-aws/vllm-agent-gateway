# External Integration Breadth Goals

Status: Approved.

This document defines the breadth-confidence goals for EIG-1, EIG-2, and EIG-3. It exists to prevent external-integration work from being considered complete only because one synthetic happy path passed.

## Scope Boundary

The approved breadth work does not authorize production enterprise integrations. It must not add real external API calls, real OAuth token exchange, raw MCP exposure, direct model-to-tool connector access, enterprise-specific credentials, production data-clean-room infrastructure, persistent hidden memory, or SIEM/log-sink integrations.

All breadth tests start with deterministic local fixtures. Protocols, auth modes, and schemas may be validated or rejected, but executable connector behavior remains controller-owned and local-stub based unless a later approved milestone changes that boundary.

EIG-3 breadth tests must use synthetic sensitive-data fixtures. They must not ingest real private user, employee, member, customer, credential, or business-confidential data.

## Industry-Standard Basis

The breadth goals use common engineering governance expectations:

- typed contracts before execution,
- explicit allowlists,
- deny-by-default authorization,
- least privilege,
- read/write separation,
- approval binding for mutation-class actions,
- replay-safe audit,
- negative controls,
- blind-baseline-first chat-quality evaluation,
- release gates before enablement,
- data minimization,
- purpose limitation,
- deterministic masking/refusal,
- source provenance,
- retention and deletion controls,
- cross-session isolation.

## EIG-1 And EIG-2 Common Use-Case Set

The first breadth set covers three connector archetypes:

| Archetype | Why It Matters | Required Operation Shape |
| --- | --- | --- |
| Work tracking or support ticketing | Common agent use case for triage, status lookup, and safe draft updates. | Read ticket/issue plus write-class dry-run update. |
| Knowledge or document lookup | Common read-only enterprise use case for policy, runbook, and documentation retrieval. | Search/read operation with bounded result summary. |
| Structured business-record or analytics lookup | Common enterprise pattern for customer, account, order, metric, or report lookup. | Read-only structured lookup with typed filters and numeric/string fields. |

These are fixture archetypes, not vendor-specific integrations. They should not be named after real private systems unless a later connector milestone explicitly approves that scope.

## EIG-3 Common Use-Case Set

The first EIG-3 breadth set covers three synthetic sensitive-data archetypes:

| Archetype | Why It Matters | Required Handling Shape |
| --- | --- | --- |
| Personal, employee, member, or customer-like data | Common privacy failure mode for agentic systems that summarize tickets, docs, profiles, or conversations. | Detect, classify, minimize, mask or refuse, and provide safe recovery guidance. |
| Secret-like credentials | Common high-severity leakage class for code, config, logs, support requests, and connector artifacts. | Detect, never echo raw values, block reformatting/extraction, and preserve safe audit proof. |
| Confidential business records | Common enterprise data boundary for contracts, financials, legal notes, account data, and internal operations. | Summarize only when allowed, omit or refuse when unsupported, preserve provenance and access boundaries. |

These are synthetic fixture archetypes. They are not authorization to collect, store, index, or process real sensitive data.

## EIG-1 Goals

| Goal ID | Goal | Done Means |
| --- | --- | --- |
| EIG1-B1 | Connector archetype breadth | All three archetypes have deterministic manifests, operation contracts, eval fixture references, and negative controls. |
| EIG1-B2 | Protocol, auth, and schema matrix | `local_stub`, future protocol declarations, auth requirements, nested schemas, arrays, optional fields, unknown fields, and malformed arguments are accepted, rejected, or deferred deterministically. |
| EIG1-B3 | Release and registry breadth | Draft, enabled, disabled, duplicate, stale-proof, and release-gate mismatch behavior are proven across breadth fixtures. |

## EIG-2 Goals

| Goal ID | Goal | Done Means |
| --- | --- | --- |
| EIG2-B1 | Actor and scope breadth | Read success, read denial, write dry-run success, write denial, anonymous actor, expired actor, and malformed actor scenarios are proven across relevant archetypes. |
| EIG2-B2 | Approval binding breadth | Approvals are bound to actor, session, request, connector, operation, scope state, and dry-run status, with cross-actor and stale-approval negative controls. |
| EIG2-B3 | Runtime chat proof | Any connector breadth behavior exposed to natural language returns useful, safe chat-visible output through the gateway and AnythingLLM with audit links. |

## EIG-3 Goals

| Goal ID | Goal | Done Means |
| --- | --- | --- |
| EIG3-B1 | Sensitive-data archetype breadth | Personal-data, secret-like, and confidential-business fixtures have positive, safe-negative, near-miss, holdout, and prohibited-disclosure cases. |
| EIG3-B2 | Masking/refusal output matrix | Chat, JSON, artifacts, connector audit summaries, and run-state summaries consistently allow, mask, refuse, summarize, or omit sensitive content according to policy. |
| EIG3-B3 | Memory lifecycle breadth | Memory scope, provenance, retention, deletion, inspection, stale-memory rejection, hidden-memory rejection, and cross-session isolation are proven with deterministic fixtures. |
| EIG3-B4 | Privacy EvalOps release gate | Blind-baseline and local-stack privacy tests block leakage, stale memory, cross-session contamination, unsupported reconciliation, and unsafe disclosure regressions before release. |
| EIG3-B5 | Runtime privacy chat proof | Privacy-sensitive prompts exposed to chat return useful answers or safe refusals through gateway and AnythingLLM without leaking sensitive values or relying on hidden memory. |

## Pass Criteria

A breadth goal passes only when:

- the positive path works through the single controller-owned connector path,
- required negative controls fail closed,
- raw MCP or direct model-to-tool execution is not introduced,
- runtime and target repository mutation boundaries are preserved,
- chat-visible output is useful when the behavior is exposed to natural language,
- audit artifacts are replay-safe and do not store raw auth subjects or raw arguments,
- privacy-sensitive output does not expose raw sensitive values when policy requires masking, omission, or refusal,
- persistent memory cannot influence answers unless scope, provenance, retention, and inspection rules allow it,
- focused connector tests pass when EIG-1 or EIG-2 scope is touched,
- focused privacy and memory tests pass when EIG-3 scope is touched,
- full Bash regression passes at breadth closeout.

## Roadmap Link

The active implementation phases are Phase 288 through Phase 303 in `docs/ACTIONABLE_WORKFLOW_ROADMAP.md`.

The milestone gates are M26 through M36 in `docs/PROJECT_MILESTONES.md`.
