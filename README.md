# vLLM Agent Gateway

`vllm-agent-gateway` is a Linux-first local runtime for putting stricter controls between agent clients and a vLLM-hosted model.

The project objective is to make local-model coding-agent work reliable through natural-language requests: route the request, select deterministic skills and tools, gather bounded evidence, return useful chat-visible answers, preserve safety boundaries, and produce repeatable validation proof.

It provides:

- role-specific prompt proxy ports
- a token-budget gateway that rejects oversized requests and clamps output
- an explicit local controller service for bounded workflow requests
- tiny role/subrole prompt files
- a role manifest for ports, prompts, budgets, and client policy
- controller-owned workflow routing with disposable-copy apply proof, document review, execution planning, code context lookup, code investigation, refactor orchestration, workflow feedback capture, streaming document modes, code structure indexes, and implementation workflow artifacts
- a tool catalog used by controllers and the tool mediator to authorize deterministic actions

The project is intentionally conservative. It does not silently summarize, trim, rewrite, or forward unbounded context. When a request is too large, the gateway or controller rejects it so the caller has to delegate a smaller task or explicitly choose a reduction mode.

Large-context support currently means making large projects usable through indexing, retrieval, chunking, summarization, artifact paging, evidence selection, and model-context-aware routing. 384k-token projects remain the stable large-context baseline. A 500k-token project usability candidate is now approved for dedicated validation, but it does not mean promising that the current local model can accept raw 500k-token prompts.

Current large-context preparation and acceptance lives in [README.large-corpus-context-budget-inventory.md](README.large-corpus-context-budget-inventory.md), [README.retrieval-first-context-strategy-design.md](README.retrieval-first-context-strategy-design.md), [README.corpus-index-safety-governance.md](README.corpus-index-safety-governance.md), [README.context-index-prototype.md](README.context-index-prototype.md), [README.retrieval-backed-chat-answer-gate.md](README.retrieval-backed-chat-answer-gate.md), [README.artifact-paging-long-answer-usability.md](README.artifact-paging-long-answer-usability.md), [README.context-strategy-router.md](README.context-strategy-router.md), [README.large-context-usability-live-closeout.md](README.large-context-usability-live-closeout.md), [README.chunked-investigation-executor-contract.md](README.chunked-investigation-executor-contract.md), [README.chunked-investigation-executor-implementation.md](README.chunked-investigation-executor-implementation.md), [README.release-candidate-large-context-strategy-replay.md](README.release-candidate-large-context-strategy-replay.md), [README.release-candidate-baseline-corpus-promotion.md](README.release-candidate-baseline-corpus-promotion.md), [README.large-context-384k-usability-acceptance-contract.md](README.large-context-384k-usability-acceptance-contract.md), [README.large-context-384k-fixture-index-readiness.md](README.large-context-384k-fixture-index-readiness.md), [README.large-context-384k-stale-index-rejection.md](README.large-context-384k-stale-index-rejection.md), [README.large-context-384k-live-acceptance.md](README.large-context-384k-live-acceptance.md), [README.large-context-384k-clean-clone-replay.md](README.large-context-384k-clean-clone-replay.md), [README.large-context-384k-release-candidate-decision-gate.md](README.large-context-384k-release-candidate-decision-gate.md), [README.large-context-500k-candidate-rebaseline.md](README.large-context-500k-candidate-rebaseline.md), [README.large-context-500k-fixture-index-readiness.md](README.large-context-500k-fixture-index-readiness.md), and [README.large-context-500k-stale-index-rejection.md](README.large-context-500k-stale-index-rejection.md).

## Quick Start

First-time AnythingLLM testers should start here:

- [README.getting-started.md](README.getting-started.md): minimal setup and validation path for natural workflow testing through AnythingLLM.
- [README.productized-setup.md](README.productized-setup.md): single setup command surface for install, start, validate, reset, and rerun.
- [README.external-tester-onboarding.md](README.external-tester-onboarding.md): contextless release-candidate tester path with curated read-only prompts and feedback capture.
- [README.external-tester-dry-run.md](README.external-tester-dry-run.md): Phase 147 minimum stable external tester dry run through setup, AnythingLLM, onboarding, and feedback.
- [README.first-time-user-doctor.md](README.first-time-user-doctor.md): setup preflight for ports, controller roots, AnythingLLM config, and frozen fixtures.
- [README.release-channels.md](README.release-channels.md): dev, release-candidate, and stable channel metadata plus setup validation.
- [README.stable-handoff.md](README.stable-handoff.md): stable-channel external tester handoff, smoke validation, first prompt, feedback, and rollback.
- [README.runtime-state.md](README.runtime-state.md): local-only runtime report policy, committed proof metadata, and hygiene validation.
- [README.stable-release-reset-rehearsal.md](README.stable-release-reset-rehearsal.md): Phase 153 reset/start/recovery rehearsal that preserves source, fixtures, and real runtime-state.
- [README.release-notes.md](README.release-notes.md): current founder-testing release notes, supported scope, limitations, and proof artifacts.
- [README.release-adherence.md](README.release-adherence.md): consolidated current-local-model release gate for founder/testing readiness.
- [README.failure-to-roadmap.md](README.failure-to-roadmap.md): Phase 148 proposal gate for turning failed proof artifacts into unapproved roadmap candidates.
- [README.contextless-audit-scorecard.md](README.contextless-audit-scorecard.md): Phase 149 deterministic scorecard for contextless audit and blind-baseline evidence packages.
- [README.contextless-agent-audit-pack.md](README.contextless-agent-audit-pack.md): Phase 185 reusable blind-baseline-first audit pack for contextless agents.
- [README.multi-fixture-prompt-parity.md](README.multi-fixture-prompt-parity.md): Phase 187 parity matrix for supported prompt families across Coinbase and non-Coinbase fixtures.
- [README.evidence-boundary-schema-gate.md](README.evidence-boundary-schema-gate.md): Phase 189 gate preventing malformed schema and change-boundary evidence from rendering as successful chat answers.
- [README.unsupported-scope-refusal-quality.md](README.unsupported-scope-refusal-quality.md): Phase 190 gate proving unsupported, unsafe, and under-specified prompts return actionable recovery guidance.
- [README.prompt-family-drift-detection.md](README.prompt-family-drift-detection.md): Phase 191 gate classifying prompt-family drift before live founder field runs.
- [README.chat-answer-scoring-v2.md](README.chat-answer-scoring-v2.md): Phase 192 consolidated scoring gate for blind-baseline versus local chat answers.
- [README.skill-registry-readiness-review.md](README.skill-registry-readiness-review.md): Phase 193 readiness review for scaling the current skill registry.
- [README.release-candidate-founder-trial-pack.md](README.release-candidate-founder-trial-pack.md): Phase 195 contextless founder trial pack with setup, prompts, answer-quality expectations, limits, and feedback capture.
- [README.v1-product-readiness-reassessment.md](README.v1-product-readiness-reassessment.md): Phase 196 current readiness reassessment for broader V1 founder beta after the Phase 191-195 proof chain.
- [README.founder-trial-execution-round.md](README.founder-trial-execution-round.md): Phase 197 live founder trial execution through AnythingLLM with run IDs, response artifacts, and quality classifications.
- [README.v1-beta-release-closeout.md](README.v1-beta-release-closeout.md): Phase 199 closeout gate for the M1 V1 founder beta milestone.
- [README.chat-visible-answer-contract-inventory.md](README.chat-visible-answer-contract-inventory.md): Phase 200 inventory of chat-visible answer contracts for supported Priority 0 prompt families.
- [README.chat-visible-answer-contract-enforcement.md](README.chat-visible-answer-contract-enforcement.md): Phase 201 deterministic enforcement gate for chat-visible answer contracts.
- [README.chat-visible-output-usefulness-refresh.md](README.chat-visible-output-usefulness-refresh.md): Phase 202 live gateway and AnythingLLM refresh for M2 answer usefulness.
- [README.workflow-skill-tool-selection-matrix.md](README.workflow-skill-tool-selection-matrix.md): Phase 203 deterministic workflow/skill/tool selection matrix for M3.
- [README.no-manual-skill-injection-explainability.md](README.no-manual-skill-injection-explainability.md): Phase 204 natural prompt selection explainability without manual skill injection.
- [README.skill-library-scaling-readiness-inventory.md](README.skill-library-scaling-readiness-inventory.md): Phase 229 M12 inventory for current skill/tool coverage and the next small pilot candidate.
- [README.small-skill-admission-pilot.md](README.small-skill-admission-pilot.md): Phase 230 admission gate for the first M12 fixture/eval coverage candidate.
- [README.runtime-recovery-reliability-rebaseline.md](README.runtime-recovery-reliability-rebaseline.md): Phase 231 restart-and-resume proof for vLLM, gateway/proxies, controller, AnythingLLM, small-repo prompts, and large-context prompts.
- [README.onboarding-release-handoff-refresh.md](README.onboarding-release-handoff-refresh.md): Phase 232 docs freshness gate for the contextless tester handoff path.
- [README.contextless-handoff-dry-run.md](README.contextless-handoff-dry-run.md): Phase 233 live proof that a contextless tester can follow the refreshed handoff.
- [README.clean-clone-release-handoff.md](README.clean-clone-release-handoff.md): Phase 234 disposable clean-snapshot proof for release handoff without private workspace state.
- [README.clone-safe-model-capability-routing.md](README.clone-safe-model-capability-routing.md): Phase 235 clone-safe model capability profile path for clean checkout routing.
- [README.route-stability-holdout-replay.md](README.route-stability-holdout-replay.md): Phase 205 target and holdout route stability replay through gateway and AnythingLLM.
- [README.evidence-relevance-audit-pack.md](README.evidence-relevance-audit-pack.md): Phase 206 contextless evidence-quality audit pack for M4.
- [README.evidence-ranking-source-hash-gate.md](README.evidence-ranking-source-hash-gate.md): Phase 207 deterministic evidence ranking and source-hash proof gate for M4.
- [README.evidence-quality-live-rerun.md](README.evidence-quality-live-rerun.md): Phase 208 live gateway and AnythingLLM rerun of M4 evidence-quality prompts.
- [README.current-model-compatibility.md](README.current-model-compatibility.md): Phase 150 matrix for current localhost model support, boundaries, and monitored risks.
- [README.model-swap-smoke-probe.md](README.model-swap-smoke-probe.md): Phase 154 smoke probe that detects localhost model swaps and decides whether drift gates are required.
- [README.v1-product-readiness-review.md](README.v1-product-readiness-review.md): Phase 155 go/no-go review for V1 founder-testing readiness.
- [README.v1-stable-release-decision.md](README.v1-stable-release-decision.md): Phase 156 final release decision, scope, limitations, rollback path, and next roadmap batch.
- [README.founder-field-round1.md](README.founder-field-round1.md): Phase 157 founder field-test round through AnythingLLM with advisory/blocker routing into feedback intake.
- [README.founder-field-round2.md](README.founder-field-round2.md): Phase 164 blind-baseline-first founder field round with full response artifacts and route proof.
- [README.founder-feedback-loop-rebaseline.md](README.founder-feedback-loop-rebaseline.md): Phase 227 rebaseline for governed useful, advisory, repair, rejected, deferred, baseline, and holdout feedback outcomes.
- [README.founder-feedback-repair-rerun-gate.md](README.founder-feedback-repair-rerun-gate.md): Phase 228 proof gate for accepted feedback repairs before they can be marked fixed.
- [README.prompt-advisory-closure.md](README.prompt-advisory-closure.md): Phase 165 prompt-advisory closure using refined prompt candidates and holdout proof.
- [README.generic-chat-vague-prompt-contract.md](README.generic-chat-vague-prompt-contract.md): Phase 166 contract for greetings, vague prompts, missing targets, and approval-bypass refusal.
- [README.transcript-quality-feedback-intake.md](README.transcript-quality-feedback-intake.md): Phase 158 governed intake for Phase 157 advisory/blocker cases and founder notes.
- [README.priority0-repair-loop.md](README.priority0-repair-loop.md): Phase 159 repair-loop closure for Phase 158 findings and target-plus-holdout proof requirements.
- [README.stable-release-refresh.md](README.stable-release-refresh.md): Phase 170 stable proof-floor refresh after the Phase 163-169 chat-quality batch.
- [README.skill-tool-selection-explainability-e2e.md](README.skill-tool-selection-explainability-e2e.md): Phase 151 live gate proving normal chat explains selected and rejected skills/tools through gateway and AnythingLLM.
- [README.anythingllm-conversation-state-isolation.md](README.anythingllm-conversation-state-isolation.md): Phase 152 gate proving stale AnythingLLM history does not control the current prompt.
- [README.semi-well-defined-prompts.md](README.semi-well-defined-prompts.md): Phase 110 natural prompt generalization gate for current local-model chat quality.
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
- [README.productized-setup.md](README.productized-setup.md): productized local harness setup and recovery commands
- [README.external-tester-onboarding.md](README.external-tester-onboarding.md): contextless external tester prompt pack, live validation, and linked feedback capture
- [README.external-tester-dry-run.md](README.external-tester-dry-run.md): minimum stable external tester dry run and proof artifact
- [README.first-time-user-doctor.md](README.first-time-user-doctor.md): first-time setup doctor for ports, AnythingLLM, controller roots, and fixtures
- [README.release-channels.md](README.release-channels.md): release channel manifest, setup validator, stable readiness, and rollback path
- [README.stable-handoff.md](README.stable-handoff.md): stable-channel smoke validation, first external tester prompt, feedback capture, and rollback
- [README.runtime-state.md](README.runtime-state.md): local-only runtime reports, committed release proof metadata, and repository hygiene gate
- [README.stable-release-reset-rehearsal.md](README.stable-release-reset-rehearsal.md): stable reset/start/recovery rehearsal with source, fixture, runtime-state, and stable handoff proof
- [README.release-notes.md](README.release-notes.md): founder-testing release scope, limitations, validation evidence, and rerun commands
- [README.release-adherence.md](README.release-adherence.md): one JSON/Markdown gate for current local model release readiness
- [README.release-candidate-baseline-corpus-promotion.md](README.release-candidate-baseline-corpus-promotion.md): promoted release-candidate chat-quality cases in the governed baseline corpus
- [README.external-tester-feedback-loop-from-clone.md](README.external-tester-feedback-loop-from-clone.md): release-candidate clone feedback proof for positive and defect tester records
- [README.v1-release-candidate-decision-gate.md](README.v1-release-candidate-decision-gate.md): Phase 244 ship, hold, or repair-required decision gate for the current release candidate
- [README.release-candidate-runtime-health-restoration.md](README.release-candidate-runtime-health-restoration.md): Phase 245 post-restart runtime health proof before rerunning the release decision
- [README.release-candidate-ship-handoff.md](README.release-candidate-ship-handoff.md): Phase 247 committed ship handoff metadata and tester-doc freshness gate
- [README.failure-to-roadmap.md](README.failure-to-roadmap.md): failure-to-roadmap proposal gate for failed release proof artifacts
- [README.contextless-audit-scorecard.md](README.contextless-audit-scorecard.md): contextless audit and blind-baseline evidence scorecard
- [README.multi-fixture-prompt-parity.md](README.multi-fixture-prompt-parity.md): multi-fixture prompt parity across gateway and AnythingLLM
- [README.evidence-boundary-schema-gate.md](README.evidence-boundary-schema-gate.md): governed schema and change-boundary evidence validation before chat answers
- [README.unsupported-scope-refusal-quality.md](README.unsupported-scope-refusal-quality.md): unsupported-scope refusal and clarification quality gate
- [README.multi-repo-fixture-baseline-pack.md](README.multi-repo-fixture-baseline-pack.md): Phase 209 `s-aws/staterail` fixture selection and blind-baseline prompt pack
- [README.multi-repo-baseline-comparison.md](README.multi-repo-baseline-comparison.md): Phase 210 `s-aws/staterail` gateway and AnythingLLM baseline comparison dry run
- [README.multi-repo-live-generalization-rerun.md](README.multi-repo-live-generalization-rerun.md): Phase 212 live M5 rerun across Staterail and Coinbase holdouts
- [README.m5-generalization-closeout.md](README.m5-generalization-closeout.md): Phase 213 M5 closeout decision and next-scope boundary
- [README.large-corpus-context-budget-inventory.md](README.large-corpus-context-budget-inventory.md): Phase 214 large local corpus and context-budget inventory
- [README.prompt-family-drift-detection.md](README.prompt-family-drift-detection.md): prompt-family drift classification against catalog, skill coverage, holdouts, and founder prompt pack
- [README.chat-answer-scoring-v2.md](README.chat-answer-scoring-v2.md): repeatable chat-answer scoring, classification, and repair-target guidance
- [README.skill-registry-readiness-review.md](README.skill-registry-readiness-review.md): keep, split, merge, retire, or defer review for current skills before scaling
- [README.skill-authoring-pipeline-v2.md](README.skill-authoring-pipeline-v2.md): repeatable draft-packet admission gate for skill candidates with eval, holdout, blind-baseline, and live-validation requirements
- [README.release-candidate-founder-trial-pack.md](README.release-candidate-founder-trial-pack.md): contextless founder trial pack with setup, prompts, expected answer qualities, limits, and feedback capture
- [README.v1-product-readiness-reassessment.md](README.v1-product-readiness-reassessment.md): current V1 founder-beta readiness reassessment based on the Phase 191-195 proof chain
- [README.founder-trial-execution-round.md](README.founder-trial-execution-round.md): live founder trial execution round for the release-candidate prompt pack
- [README.founder-feedback-intake-repair.md](README.founder-feedback-intake-repair.md): deterministic intake for founder trial advisories, blockers, optional notes, and Phase 199 repair decisions
- [README.current-model-compatibility.md](README.current-model-compatibility.md): current localhost model compatibility matrix and known boundaries
- [README.model-swap-smoke-probe.md](README.model-swap-smoke-probe.md): localhost model-swap detector with next-gate decision for drift and portability
- [README.v1-product-readiness-review.md](README.v1-product-readiness-review.md): V1 product readiness review with supported scope, unsupported scope, blockers, risks, and go/no-go recommendation
- [README.v1-stable-release-decision.md](README.v1-stable-release-decision.md): final V1 founder-testing release decision with rollback and next-batch status
- [README.founder-field-round1.md](README.founder-field-round1.md): founder field-test round 1 with AnythingLLM evidence, advisory cases, and Phase 158 routing
- [README.founder-field-round2.md](README.founder-field-round2.md): founder field-test round 2 with blind baselines, full response artifacts, and route-surface proof
- [README.founder-feedback-loop-rebaseline.md](README.founder-feedback-loop-rebaseline.md): current feedback-loop rebaseline for M9 founder feedback classification
- [README.founder-feedback-repair-rerun-gate.md](README.founder-feedback-repair-rerun-gate.md): current feedback repair rerun proof gate
- [README.prompt-advisory-closure.md](README.prompt-advisory-closure.md): prompt-advisory closure decisions with refined prompt candidate and holdout proof
- [README.generic-chat-vague-prompt-contract.md](README.generic-chat-vague-prompt-contract.md): generic chat and vague prompt safety/usefulness contract
- [README.transcript-quality-feedback-intake.md](README.transcript-quality-feedback-intake.md): governed transcript and founder-feedback intake after Phase 157
- [README.priority0-repair-loop.md](README.priority0-repair-loop.md): Phase 159 no-repair-required or target-plus-holdout repair closure gate
- [README.stable-release-refresh.md](README.stable-release-refresh.md): Phase 170 refreshed release proof floor and founder-testing decision
- [README.skill-tool-gap-batch-proposal.md](README.skill-tool-gap-batch-proposal.md): Phase 161 proposal-only gate for evidence-backed deterministic skill/tool batches
- [README.skill-library-scaling-readiness-inventory.md](README.skill-library-scaling-readiness-inventory.md): current skill-library scaling inventory and Phase 230 candidate selection
- [README.small-skill-admission-pilot.md](README.small-skill-admission-pilot.md): current small skill admission pilot for `FX-001`
- [README.runtime-recovery-reliability-rebaseline.md](README.runtime-recovery-reliability-rebaseline.md): current restart-and-resume proof for local runtime recovery
- [README.onboarding-release-handoff-refresh.md](README.onboarding-release-handoff-refresh.md): current onboarding and release handoff docs freshness gate
- [README.contextless-handoff-dry-run.md](README.contextless-handoff-dry-run.md): current contextless handoff live dry-run gate
- [README.post-restart-runtime-readiness.md](README.post-restart-runtime-readiness.md): Phase 163 post-restart readiness gate over doctor, health drift, and AnythingLLM greeting/session recovery
- [README.skill-tool-selection-explainability-e2e.md](README.skill-tool-selection-explainability-e2e.md): live chat-visible selected/rejected skill and tool explanation gate
- [README.anythingllm-conversation-state-isolation.md](README.anythingllm-conversation-state-isolation.md): stale-history isolation gate for reused AnythingLLM sessions
- [README.semi-well-defined-prompts.md](README.semi-well-defined-prompts.md): semi-well-defined natural prompt suite with route, semantic, score, fixture, gateway, and AnythingLLM proof
- [README.security-policy.md](README.security-policy.md): security policy validator for secret exposure, filesystem boundaries, fixture safety, command fragments, and onboarding prompt safety
- [README.gateway.md](README.gateway.md): gateway, role proxies, ports, setup, and client notes
- [README.controller-service.md](README.controller-service.md): explicit HTTP controller workflow service and run lookup
- [README.workflow-router.md](README.workflow-router.md): natural-language workflow routing, natural client adapters, read-only execution, implementation prep, and disposable-copy proof
- [README.context-retrieval-upgrade.md](README.context-retrieval-upgrade.md): route-owned context-source selection and validation
- [README.implementation-prep-expansion.md](README.implementation-prep-expansion.md): draft-only packet proposal expansion for small text edits and approved-investigation follow-ups
- [README.approval-continuation-robustness.md](README.approval-continuation-robustness.md): approval continuation run binding, duplicate/denied/scope-change rejection, and chat-visible failure reasons
- [README.advanced-refactor-readiness.md](README.advanced-refactor-readiness.md): Phase 105 fail-closed gate for advanced refactor pilot readiness and stable-promotion blocking
- [README.controlled-apply.md](README.controlled-apply.md): approval-gated small-change dry-run, protected real-apply boundary, disposable-copy mutation proof, rollback, and Phase 98 append/multi-operation proof
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
- [README.eval-repair-loop.md](README.eval-repair-loop.md): convert failed eval artifacts into evidence-backed repair recommendations with holdout gates
- [README.founder-field-tests.md](README.founder-field-tests.md): founder-style AnythingLLM prompt field tests with deltas and prompt suggestions
- [README.bounded-recursive-testing.md](README.bounded-recursive-testing.md): no-context recursive evaluation loop with bounded rounds, deterministic adjudication, scoring, and stop conditions
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
