# Documentation Index

This index is ordered for contextless entities: people or agents entering the project without session history. Start at the top and move down only as needed.

## 1. Project Entry

- [Project README](../README.md): what this project is, tested setup, quick start, basic usage, and repository layout.
- [Getting Started With AnythingLLM](../README.getting-started.md): minimal first-time setup and validation path for natural workflow testing through AnythingLLM.
- [Gateway Feature README](../README.gateway.md): runtime architecture, vLLM gateway behavior, role prompt proxies, ports, and client connection notes.
- [Controller Service README](../README.controller-service.md): explicit HTTP workflow service, end-to-end documenter service example, allowlisted target roots, and run lookup.
- [Workflow Router README](../README.workflow-router.md): natural-language workflow routing, natural client adapters, read-only execution, inline L1/L2 chat answers, approved implementation prep, packet-objective and narrowed-edit follow-up, and disposable-copy apply proof through controller-owned registry selection.
- [Task Decomposition README](../README.task-decomposition.md): read-only multi-step task decomposition into work packages, dependencies, approval gates, verification strategy, and uncertainty markers.
- [Controlled Apply README](../README.controlled-apply.md): approval-gated small-change dry-run, real-apply boundary, disposable-copy mutation proof, rollback metadata, and live gateway/AnythingLLM validation.
- [Execution Planning README](../README.execution-planning.md): controller-owned execution planning, packet candidates, draft compatibility checks, and non-mutation proof.
- [Code Context Lookup README](../README.code-context.md): read-only controller-owned source and curated relationship lookup with bounded artifacts.
- [Code Investigation README](../README.code-investigation.md): read-only controller-owned investigation plan with evidence and packet seed artifacts.
- [Refactor Single Path README](../README.refactor-single-path.md): approval-gated refactor orchestration through investigation and draft packet planning.
- [Workflow Feedback README](../README.workflow-feedback.md): founder/tester feedback capture linked to workflow run records and artifacts.
- [Run Inspector README](../README.run-inspector.md): compact controller run summaries for route, skills, artifacts, failures, semantic status, and mutation proof.
- [Founder Field Tests README](../README.founder-field-tests.md): natural prompt field-test runner through AnythingLLM with baseline targets, deltas, miss suggestions, and protected fixture checks.
- [AnythingLLM UI E2E README](../README.anythingllm-ui-e2e.md): browser-rendered Desktop UI validation through real AnythingLLM `/stream-chat`, workflow-router gateway, screenshots, and fixture mutation proof.
- [Prompt Catalogs README](../README.prompt-catalogs.md): governed prompt catalog fixtures, case metadata, validation, matrix expectations, and change-history rules.
- [Skill Registry README](../README.skill-registry.md): canonical metadata registry, natural lifecycle chat with approval continuations, admission validation, selection explanation, proposal, registration, skill-pack validation/install, scaffold generation, mutation gate, promotion, lifecycle audit, deprecation, update/versioning workflow, release gate, Batch B validation, selector-scale proof, capability contracts, executable eval runner, and eval fixtures for project-local planning skills.
- [L1 Coding Agent Prompt Backlog](L1_CODING_AGENT_PROMPTS.md): validated simple prompt/skill/tool targets, full L1 suite proof boundaries, and gates before advanced refactor work resumes.
- [L2 Coding Agent Prompt Backlog](L2_CODING_AGENT_PROMPTS.md): validated next-layer prompt expansion, failing-test diagnosis, multi-file investigation, dependency impact, test-selection rationale, acceptance standard, and deferred advanced boundaries.

## 2. Main Workflows

- [Documenter README](../README.documenter.md): bounded document review, parallel chunk review, manifests, review plans, follow-ups, agent-executable change plans, drafts, and resumable state.
- [Streaming README](../README.streaming.md): streaming modes for oversized files and explicit reductions.
- [Workflow Router README](../README.workflow-router.md): route decisions from natural-language requests plus natural client adapters, read-only execution, inline L1/L2 chat answers, approved implementation prep, packet-objective and narrowed-edit follow-up, and disposable-copy apply proof.
- [Task Decomposition README](../README.task-decomposition.md): deterministic read-only decomposition for larger coding requests before implementation prep.
- [Controlled Apply README](../README.controlled-apply.md): deterministic small-change packet previews, approval-gated apply, disposable-copy mutation proof, rollback, and protected fixture boundaries.
- [Code Context Lookup README](../README.code-context.md): deterministic read-only lookup for exact matches, structure slices, explicit file snippets, and curated relationships.
- [Code Investigation README](../README.code-investigation.md): deterministic read-only investigation for beginning point, participating files, tests, and path risk.
- [Refactor Single Path README](../README.refactor-single-path.md): investigation-first refactor workflow with explicit approval before draft packet planning.
- [Workflow Feedback README](../README.workflow-feedback.md): explicit feedback records for what was useful, wrong, missing, slow, or noisy.
- [Run Inspector README](../README.run-inspector.md): latest-run and explicit-run inspection for controller artifacts.
- [Founder Field Tests README](../README.founder-field-tests.md): V1 founder field-test prompts through AnythingLLM with reviewable Markdown and JSON reports.
- [AnythingLLM UI E2E README](../README.anythingllm-ui-e2e.md): Desktop UI bundle rendering and chat submission proof through the real AnythingLLM backend.
- [Prompt Catalogs README](../README.prompt-catalogs.md): governed prompt catalog fixtures for field tests and prompt-matrix validation.
- [Skill Registry README](../README.skill-registry.md): metadata-only skill selection and explanation, natural lifecycle chat with exact approval-continuation wording, admission validation, skill-batch proposal, registration, skill-pack validation/install, scaffold generation, mutation gate, promotion, lifecycle audit, deprecation, update/versioning workflows, release gate, Batch B validation, selector-scale proof, safety levels, capability contracts, executable eval runner, and fixture references.
- [Code Structure Indexes README](../README.code-structure-indexes.md): deterministic Python AST, Markdown/reference, and JSON/YAML key-path indexes.
- [Implementation Workflow README](../README.implementation-workflow.md): bounded implementation packets, draft/apply policy, verification capture, and resume.

## 3. Tooling And Policy

- [Tool Policy README](../README.tool-policy.md): runtime tool catalog, governed tool admission/registration, role tool assignment, and synthetic tool mediation.
- [Tool Mediation Reference](TOOL_MEDIATION.md): model-visible tool schemas, tool-call detection, execution loop, and final response validation.
- [L1 Coding Agent Prompt Backlog](L1_CODING_AGENT_PROMPTS.md): validated L1 read-only and draft-only prompts built into controller-selected workflows with tool operation and live suite validation.
- [L2 Coding Agent Prompt Backlog](L2_CODING_AGENT_PROMPTS.md): L2 prompt expansion criteria, validated L2 prompt families, and future L2/scaling candidates.
- [Skill Library Scaling Plan](SKILL_LIBRARY_SCALING_PLAN.md): post-V1 plan for adding small deterministic L1/L2 skills with eval gates, selector-scale proof, and approval boundaries.
- [Skill Scaling Batch D Proposal](SKILL_SCALING_BATCH_D_PROPOSAL.md): Phase 61 field-evidence candidate list, Phase 62 draft registration proof, Phase 63 promotion proof, admission gate, and stop conditions.
- [Execution Planning Skills](EXECUTION_PLANNING_SKILLS.md): skill specs for deterministic planning by smaller models.
- [Execution Planning Skill Template](EXECUTION_PLANNING_SKILL_TEMPLATE.md): reusable 8-step template for future planning skills.
- [Execution Planning Skill Validation](EXECUTION_PLANNING_SKILL_VALIDATION.md): reusable localhost validation command, static checks, live usability proof, and dry-chain proof for project-local planning skills.
- [Execution Planning Automation Integration Plan](EXECUTION_PLANNING_AUTOMATION_INTEGRATION_PLAN.md): support reference and validation history for the older execution-planning controller/gateway integration.
- [Execution Planning Controller Workflow Schema](EXECUTION_PLANNING_CONTROLLER_WORKFLOW_SCHEMA.md): `execution_planning.plan` request/result schema, artifact contract, refusal cases, and validation matrix.
- [Gateway Controller Routing Plan](GATEWAY_CONTROLLER_ROUTING_PLAN.md): support reference for the implemented explicit-envelope gateway route; not the final natural-language workflow-router plan.

## 4. Examples

- [Examples Index](examples/README.md)
- [Gateway Examples](examples/gateway.md)
- [Getting Started With AnythingLLM](../README.getting-started.md)
- [Controller Service Examples](examples/controller-service.md)
- [Workflow Router Examples](examples/workflow-router.md)
- [Task Decomposition Examples](examples/task-decomposition.md)
- [Controlled Apply Examples](examples/controlled-apply.md)
- [Execution Planning Harness Examples](examples/execution-planning-harness.md)
- [AnythingLLM Founder Testing Examples](examples/anythingllm-founder-testing.md)
- [Code Context Lookup Examples](examples/code-context.md)
- [Code Investigation Examples](examples/code-investigation.md)
- [Refactor Single Path Examples](examples/refactor-single-path.md)
- [Workflow Feedback Examples](examples/workflow-feedback.md)
- [Run Inspector Examples](examples/run-inspector.md)
- [AnythingLLM UI E2E Examples](examples/anythingllm-ui-e2e.md)
- [Prompt Catalog Examples](examples/prompt-catalogs.md)
- [Skill Registry Examples](examples/skill-registry.md)
- [Documenter Examples](examples/documenter.md)
- [Streaming Examples](examples/streaming.md)
- [Code Structure Index Examples](examples/code-structure-indexes.md)
- [Implementation Workflow Examples](examples/implementation-workflow.md)
- [Tool Policy Examples](examples/tool-policy.md)

## 5. State, Modes, And Roadmaps

- [V1 Release Candidate Report](V1_RELEASE_CANDIDATE.md): supported V1 prompt families, unsupported boundaries, known limitations, validation evidence, and re-run commands.
- [V1 Founder Field Test Results](V1_FOUNDER_FIELD_TEST_RESULTS.md): expanded AnythingLLM field test, contextless baseline, initial differences, fixes, Batch D prompt proof, skill-library release-gate integration, final run IDs, and prompt suggestions.
- [Skill Library Scaling Plan](SKILL_LIBRARY_SCALING_PLAN.md): post-V1 scaling phases, admission gates, candidate prompt families, and validation commands.
- [Skill Scaling Batch D Proposal](SKILL_SCALING_BATCH_D_PROPOSAL.md): evidence-backed Batch D candidate skills, registration/promotion proof, and validator command.
- [Actionable Workflow Roadmap](ACTIONABLE_WORKFLOW_ROADMAP.md): canonical product roadmap for natural-language workflow routing, tool/skill selection, execution gates, verification, and final acceptance.
- [Documenter Run State](DOCUMENTER_RUN_STATE.md): `run-state-*.json` schema and resume behavior.
- [Streaming Document Modes](STREAMING_DOCUMENT_MODES.md): mode details, output labels, artifacts, and limits.
- [Documenter E2E Roadmap](DOCUMENTER_E2E_ROADMAP.md): shipped phases, remaining nice-to-have work, artifact inventory, and drift controls.
- [Controller Service Roadmap](CONTROLLER_SERVICE_ROADMAP.md): planned explicit harness-to-controller service path without adding agent-framework dependencies yet.

## Navigation Rule

Keep project documentation ordered by reader intent:

1. Entry README for summary and quick start only.
2. Feature README for each shipped capability.
3. Example docs under `docs/examples/`.
4. Reference docs under `docs/`.
5. Roadmaps only for state, decisions, and planned work.

When adding a feature, update this index first or in the same change.
