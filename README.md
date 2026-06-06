# vLLM Agent Gateway

`vllm-agent-gateway` is a Linux-first local runtime for putting stricter controls between agent clients and a vLLM-hosted model.

It provides:

- role-specific prompt proxy ports
- a token-budget gateway that rejects oversized requests and clamps output
- an explicit local controller service for bounded workflow requests
- tiny role/subrole prompt files
- a role manifest for ports, prompts, budgets, and client policy
- controller-owned workflow routing with disposable-copy apply proof, document review, execution planning, code context lookup, code investigation, refactor orchestration, workflow feedback capture, streaming document modes, code structure indexes, and implementation workflow artifacts
- a tool catalog used by controllers and the tool mediator to authorize deterministic actions

The project is intentionally conservative. It does not silently summarize, trim, rewrite, or forward unbounded context. When a request is too large, the gateway or controller rejects it so the caller has to delegate a smaller task or explicitly choose a reduction mode.

## Quick Start

First-time AnythingLLM testers should start here:

- [README.getting-started.md](README.getting-started.md): minimal setup and validation path for natural workflow testing through AnythingLLM.
- [README.external-tester-onboarding.md](README.external-tester-onboarding.md): contextless release-candidate tester path with curated read-only prompts and feedback capture.
- [README.first-time-user-doctor.md](README.first-time-user-doctor.md): setup preflight for ports, controller roots, AnythingLLM config, and frozen fixtures.
- [README.release-channels.md](README.release-channels.md): dev, release-candidate, and stable channel metadata plus setup validation.
- [README.security-policy.md](README.security-policy.md): release-candidate security policy gate for secrets, roots, fixtures, commands, and onboarding prompts.

Tested setup:

- Ubuntu 24.04/Linux runtime
- NVIDIA RTX 6000 PRO 96 GB
- NVIDIA vLLM Docker container: `nvcr.io/nvidia/vllm:26.01-py3`
- Model: `Qwen3-Coder-30B-A3B-Instruct`
- vLLM OpenAI-compatible server on `http://127.0.0.1:8000/v1`
- Python 3 and Bash
- Claude Code as one tested client, usually with `--bare`

Start vLLM separately, then start the gateway, controller service, and role prompt proxies:

```bash
bash start-agent-prompt-proxies.sh
```

The startup script reports the LLM gateway URL, AnythingLLM workflow-router target URL, controller allowlisted roots, controller artifact root, local role endpoints, and a quick port status summary.

Stop them:

```bash
bash stop-agent-prompt-proxies.sh
```

Run regression tests:

```bash
pytest tests/regression/ -v
```

## Basic Usage

Run a one-chunk documenter dry run:

```bash
python scripts/run_documenter_orchestrator.py --target-root . --seed-doc README.md --dry-run --max-chunks 1
```

Run the same workflow through the controller service:

```bash
python scripts/run_documenter_service_example.py --target-root . --case seed --max-chunks 1
```

Run a source-presence check without vLLM:

```bash
python scripts/run_streaming_documenter.py --target-root . --doc README.md \
  --mode context_presence \
  --query "runtime ports"
```

Build a deterministic structure index:

```bash
python scripts/run_code_structure_index.py --target-root .
```

Create draft implementation artifacts from explicit packets:

```bash
python scripts/run_implementation_workflow.py --target-root . \
  --packet-file implementation-packets.json
```

## Documentation Map

Start with the ordered index: [docs/README.md](docs/README.md).

Feature docs:

- [README.getting-started.md](README.getting-started.md): first-time AnythingLLM setup and validation path
- [README.external-tester-onboarding.md](README.external-tester-onboarding.md): contextless external tester prompt pack, live validation, and linked feedback capture
- [README.first-time-user-doctor.md](README.first-time-user-doctor.md): first-time setup doctor for ports, AnythingLLM, controller roots, and fixtures
- [README.release-channels.md](README.release-channels.md): release channel manifest, setup validator, stable readiness, and rollback path
- [README.security-policy.md](README.security-policy.md): security policy validator for secret exposure, filesystem boundaries, fixture safety, command fragments, and onboarding prompt safety
- [README.gateway.md](README.gateway.md): gateway, role proxies, ports, setup, and client notes
- [README.controller-service.md](README.controller-service.md): explicit HTTP controller workflow service and run lookup
- [README.workflow-router.md](README.workflow-router.md): natural-language workflow routing, natural client adapters, read-only execution, implementation prep, and disposable-copy proof
- [README.controlled-apply.md](README.controlled-apply.md): approval-gated small-change dry-run, protected real-apply boundary, disposable-copy mutation proof, and rollback
- [README.mutation-sandbox.md](README.mutation-sandbox.md): sandbox contract, structured diff, rollback proof, and fail-closed disposable mutation artifacts
- [README.execution-planning.md](README.execution-planning.md): explicit execution-planning workflow, packet candidates, draft proof, and non-mutation checks
- [README.code-context.md](README.code-context.md): read-only controller-owned code context and curated relationship lookup
- [README.code-investigation.md](README.code-investigation.md): read-only controller-owned code investigation plan
- [README.refactor-single-path.md](README.refactor-single-path.md): approval-gated single-path refactor orchestration
- [README.workflow-feedback.md](README.workflow-feedback.md): founder/tester feedback artifacts linked to workflow runs
- [README.run-inspector.md](README.run-inspector.md): compact latest-run summaries for route, skills, artifacts, failures, and mutation proof
- [README.observability.md](README.observability.md): recent-run dashboard for workflow selection, model route status, approval state, downstream status, artifacts, failures, mutation proof, and timing
- [README.run-artifact-diff.md](README.run-artifact-diff.md): compare acceptance, founder-field, and portability run artifacts
- [README.failure-taxonomy.md](README.failure-taxonomy.md): classify validation failures into stable categories with recommended next actions
- [README.founder-field-tests.md](README.founder-field-tests.md): founder-style AnythingLLM prompt field tests with deltas and prompt suggestions
- [README.anythingllm-ui-e2e.md](README.anythingllm-ui-e2e.md): browser-rendered AnythingLLM Desktop UI proof through the real backend and workflow-router gateway
- [README.model-portability.md](README.model-portability.md): candidate-model acceptance gate with classified harness, classifier, prompt, and model-quality misses
- [README.model-capability-profiles.md](README.model-capability-profiles.md): advisory model capability profiles and routing policy from portability reports
- [README.prompt-catalogs.md](README.prompt-catalogs.md): governed prompt catalog fixtures, validation, and matrix expectations
- [README.prompt-skill-coverage.md](README.prompt-skill-coverage.md): canonical prompt family to workflow, skill, tool, eval, artifact, docs, and gap coverage map
- [README.fixture-manager.md](README.fixture-manager.md): controlled fixture manifest, disposable setup, snapshot, and cleanup
- [README.skill-registry.md](README.skill-registry.md): canonical metadata registry for project-local skills
- [README.skill-authoring-factory.md](README.skill-authoring-factory.md): dry-run scaffold factory for draft skills, coverage entries, docs stubs, eval skeletons, and fail-closed tests
- [README.skill-regression-tiers.md](README.skill-regression-tiers.md): explicit skill validation tiers and minimum proof by change type
- [README.skill-packaging.md](README.skill-packaging.md): governed skill-pack layout, namespace ownership, versioning, import/export, and retirement policy
- [README.documenter.md](README.documenter.md): documenter orchestrator, review plans, follow-ups, drafts, and state
- [README.streaming.md](README.streaming.md): streaming document modes for oversized files and explicit reductions
- [README.code-structure-indexes.md](README.code-structure-indexes.md): deterministic source/config/document structure indexes
- [README.implementation-workflow.md](README.implementation-workflow.md): implementation plans, draft/apply policy, verification, and resume
- [README.tool-policy.md](README.tool-policy.md): tool catalog, role tool assignment, and mediated tool execution

Examples live under [docs/examples/](docs/examples/).

## Repository Layout

```text
roles/                       role and subrole prompt files
runtime/roles.json            active role manifest
runtime/tools.json            controller/tool mediator catalog
runtime/workflows.json        controller workflow tool policy
runtime/skills.json           canonical project-local skill metadata
vllm_agent_gateway/gateway/    prompt proxy and token budget gateway
vllm_agent_gateway/controller_service/
                              explicit HTTP controller workflow service
vllm_agent_gateway/controllers/
                              stateful workflow controllers, including workflow routing, documenter, execution planning, code context lookup, code investigation, refactor orchestration, and feedback capture
vllm_agent_gateway/structure_index/
                              deterministic code/document/config indexer
vllm_agent_gateway/implementation/
                              controlled implementation packet workflow
vllm_agent_gateway/tools/      mediated local tool execution
scripts/                      controller and smoke-test helpers
docs/                         ordered reference docs, roadmaps, and examples
```
