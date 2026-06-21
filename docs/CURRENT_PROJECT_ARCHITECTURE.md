# Current Project Architecture

Status: durable orientation reference.

This diagram shows the current product shape for contextless readers. It is not a full implementation map. Use it to understand how founder prompts, AnythingLLM, the gateway, controller workflows, local model, validation gates, and future milestone goals relate.

```mermaid
flowchart TD
    Founder["Founder / Tester"] --> AnythingLLM["AnythingLLM"]
    Founder --> DirectClient["Direct Local Validators"]

    AnythingLLM --> WorkflowGateway["Workflow Router Gateway :8500"]
    DirectClient --> WorkflowGateway

    WorkflowGateway --> Controller["Controller Service :8400"]
    WorkflowGateway --> Gateway["OpenAI-Compatible Gateway :8300"]
    Gateway --> Model["vLLM Local Model :8000"]
    Controller --> Model

    Controller --> Router["workflow_router.plan"]
    Router --> Selector["Workflow / Skill / Tool Selection"]
    Selector --> Workflows["Controller-Owned Workflows"]

    Workflows --> CodeContext["code_context.lookup"]
    Workflows --> CodeInvestigation["code_investigation.plan"]
    Workflows --> TaskDecompose["task.decompose"]
    Workflows --> SuppliedCorpusQA["supplied_corpus_qa.answer"]
    Workflows --> LargeContext["Large-Context Retrieval / Chunked Investigation"]
    Workflows --> ConnectorCatalog["connector_catalog.validate"]
    Workflows --> ConnectorRegister["connector_catalog.register"]
    Workflows --> ConnectorInvoke["connector.invoke"]
    Validation --> ConnectorReleaseGate["Connector Eval Release Gate"]

    Router --> Safety["Safety Boundaries"]
    Safety --> AllowRoots["Allowed target roots"]
    Safety --> ApprovalGates["Approval gates before mutation"]
    Safety --> DisposableCopies["Disposable-copy mutation proof"]
    Safety --> NoRawTools["No raw MCP / no direct model tool bypass"]

    Workflows --> ChatAnswer["Answer-First Chat Output"]
    Workflows --> Artifacts["Runtime Artifacts / Source Hash Proof"]
    LargeContext --> MetadataIndex["Metadata-First Corpus Index"]

    Validation["Validation Gates"] --> WorkflowGateway
    Validation --> BlindBaseline["Blind Baseline First"]
    Validation --> Regression["Focused / Full Regression"]
    Validation --> AnythingLLMProof["AnythingLLM Proof"]
    Validation --> FixtureProof["Frozen Fixture Mutation Checks"]

    Milestones["External Integration Milestone Goals"] --> Connectors["M17-M19 Governed Connectors"]
    Milestones --> Identity["M20-M22 User-Scoped Connector Authorization"]
    Milestones --> Privacy["M23-M25 PII And Memory Safety"]
```

## Current Boundaries

- The current product value is natural-language local-model work through deterministic routing, skills/tools, bounded evidence, answer-first chat output, and repeatable validation proof.
- The supported large-context path is governed 500k-token project usability through context strategy, retrieval, chunked investigation, artifact paging, and safety checks. It is not a raw 500k prompt guarantee.
- AnythingLLM is a tester-facing client surface. It should reach the workflow-router gateway when testing natural workflow behavior.
- Runtime artifacts are local proof records. They are not source of truth for product design unless summarized in tracked docs.
- Connector catalog validation, approval-gated connector registration, enabled local-stub connector mediation, connector eval release-gate validation, actor-bound connector invocation, operation-level least-privilege scopes for `oauth_user_scope` connectors, approval binding to actor/session/request/connector/operation/granted-scope state, replay-safe connector audit proof, and selected natural-language local-stub connector chat proof are available for governed manifest, registry append, dry-run/read-only proof, shippability checks, user-scoped mediation proof, and chat-visible connector result proof. Phase 304 integrates this stable handoff language with the Phase 296 local-stub connector closeout and Phase 303 synthetic privacy closeout. Real external connector execution, raw MCP access, arbitrary natural-language connector calls, enterprise-specific connectors, production OAuth token exchange, Kubernetes deployment, real sensitive-data ingestion, and persistent hidden memory are not currently shipped capabilities.

## Future Goal Position

The approved external-integration future goals are milestone goals, not implemented behavior:

- `EIG-1`: governed connector framework maps to `M17 -> M18 -> M19`, with breadth-confidence proof through `M26 -> M27 -> M28`; the approved local-stub breadth slice is complete.
- `EIG-2`: OAuth/user-scope identity propagation maps to `M20 -> M21 -> M22`, with breadth-confidence proof through `M29 -> M30 -> M31`; actor/scope breadth, approval replay breadth, selected local-stub runtime chat proof, and the Phase 296 EIG-1/EIG-2 breadth closeout are complete for the approved deterministic local-stub slice.
- `EIG-3`: PII and memory safety maps to `M23 -> M24 -> M25`, with breadth-confidence proof through `M32 -> M33 -> M34 -> M35 -> M36`; the approved synthetic privacy and memory-safety breadth slice is complete.

These goals should be implemented only through phases that preserve the existing single controller-owned path, fail-closed safety model, chat-quality validation, and contextless proof standards.

## Related References

- [Project Milestones](PROJECT_MILESTONES.md)
- [Actionable Workflow Roadmap](ACTIONABLE_WORKFLOW_ROADMAP.md)
- [Workflow Router README](../README.workflow-router.md)
- [Supplied Corpus QA README](../README.supplied-corpus-qa.md)
- [Gateway Feature README](../README.gateway.md)
- [Controller Service README](../README.controller-service.md)
- [EIG Stable Handoff Integration README](../README.eig-stable-handoff-integration.md)
