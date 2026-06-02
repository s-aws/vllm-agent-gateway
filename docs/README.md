# Documentation Index

This index is ordered for contextless entities: people or agents entering the project without session history. Start at the top and move down only as needed.

## 1. Project Entry

- [Project README](../README.md): what this project is, tested setup, quick start, basic usage, and repository layout.
- [Gateway Feature README](../README.gateway.md): runtime architecture, vLLM gateway behavior, role prompt proxies, ports, and client connection notes.
- [Controller Service README](../README.controller-service.md): explicit HTTP workflow service, end-to-end documenter service example, allowlisted target roots, and run lookup.

## 2. Main Workflows

- [Documenter README](../README.documenter.md): bounded document review, parallel chunk review, manifests, review plans, follow-ups, agent-executable change plans, drafts, and resumable state.
- [Streaming README](../README.streaming.md): streaming modes for oversized files and explicit reductions.
- [Code Structure Indexes README](../README.code-structure-indexes.md): deterministic Python AST, Markdown/reference, and JSON/YAML key-path indexes.
- [Implementation Workflow README](../README.implementation-workflow.md): bounded implementation packets, draft/apply policy, verification capture, and resume.

## 3. Tooling And Policy

- [Tool Policy README](../README.tool-policy.md): runtime tool catalog, role tool assignment, and synthetic tool mediation.
- [Tool Mediation Reference](TOOL_MEDIATION.md): model-visible tool schemas, tool-call detection, execution loop, and final response validation.
- [Execution Planning Skills](EXECUTION_PLANNING_SKILLS.md): skill specs for deterministic planning by smaller models.

## 4. Examples

- [Gateway Examples](examples/gateway.md)
- [Controller Service Examples](examples/controller-service.md)
- [Documenter Examples](examples/documenter.md)
- [Streaming Examples](examples/streaming.md)
- [Code Structure Index Examples](examples/code-structure-indexes.md)
- [Implementation Workflow Examples](examples/implementation-workflow.md)
- [Tool Policy Examples](examples/tool-policy.md)

## 5. State, Modes, And Roadmaps

- [Actionable Workflow Roadmap](ACTIONABLE_WORKFLOW_ROADMAP.md): current founder-testable workflow direction, Mermaid overview, and next shippable increments.
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
