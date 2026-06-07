# Workflow Router

`workflow_router.plan` is the controller-owned router for natural-language workflow selection, read-only execution, approved implementation preparation, disposable-copy apply proof, and natural client routing.

It accepts a user request, reads workflow/tool/skill registry metadata, returns a validated route decision, and writes durable artifacts. In `plan_only` mode it does not read the target repository. In `execute_read_only` mode it may delegate to approved read-only workflows only. In `implementation_prep` mode it requires explicit packet-design approval and exact packet operations, then delegates to `execution_planning.plan` in dry-run mode. In `apply_disposable_copy` mode it requires disposable-only approval, copies the target repo, applies through `implementation.workflow`, and proves the source did not change.

## When To Use It

Use this workflow when a tester wants to know which controller workflow should handle a development request, when a validated route should immediately run a read-only investigation, when approved implementation prep should create draft packet artifacts, or when an approved packet needs disposable-copy mutation proof before any real source apply is considered.

Example request:

```text
Refactor the placed_order_id stealth lookup so there is only one code path. Start from the logic beginning point, investigate first, create an implementation plan, wait for approval before implementation prep, and provide verification commands.
```

Expected route:

```text
workflow_router.plan -> refactor.single_path investigation_only
```

## Endpoint

```text
POST /v1/controller/workflow-router/plans
POST /v1/controller/workflow-router/chat/completions
```

Minimal payload:

```json
{
  "workflow": "workflow_router.plan",
  "target_root": "/path/to/repo",
  "user_request": "Investigate where placed_order_id stealth lookup begins.",
  "mode": "plan_only"
}
```

Read-only execution payload:

```json
{
  "workflow": "workflow_router.plan",
  "target_root": "/path/to/repo",
  "user_request": "Refactor the placed_order_id stealth lookup so there is only one code path. Start at the logic beginning point and investigate first.",
  "mode": "execute_read_only"
}
```

Implementation-prep payload:

```json
{
  "workflow": "workflow_router.plan",
  "target_root": "/path/to/repo",
  "user_request": "Prepare implementation packet candidates for an approved documentation clarification.",
  "mode": "implementation_prep",
  "approval": {
    "status": "approved_for_packet_design",
    "scope": "packet_design_only",
    "apply_allowed": false,
    "approval_refs": ["founder-approved packet design only"]
  },
  "packet_operations": [
    {
      "kind": "replace_text",
      "path": "docs/agents/INVARIANTS.md",
      "old": "exact old text",
      "new": "exact new text"
    }
  ]
}
```

Disposable-copy apply payload:

```json
{
  "workflow": "workflow_router.plan",
  "target_root": "/path/to/repo",
  "user_request": "Apply approved packet operations to a disposable copy for mutation proof.",
  "mode": "apply_disposable_copy",
  "approval": {
    "status": "approved_for_disposable_apply",
    "apply_allowed": true,
    "apply_scope": "disposable_copy_only",
    "approval_refs": ["founder-approved disposable copy apply only"]
  },
  "packet_operations": [
    {
      "kind": "replace_text",
      "path": "docs/agents/INVARIANTS.md",
      "old": "exact old text",
      "new": "exact new text"
    }
  ]
}
```

Optional `role_base_url` lets the router call the local model or gateway for a schema-validated advisory classification. Deterministic safety rules still win, and the selected route must pass the active fail-closed model capability policy before any downstream work runs.

Natural-language OpenAI-compatible clients should use the dedicated workflow-router gateway:

```text
http://127.0.0.1:8500/v1
```

The natural chat adapter uses the latest user message only, requires the message to name an allowed target path, and delegates to `workflow_router.plan`. The normal `8300` gateway remains for ordinary chat and explicit controller envelopes.

## Output Formats

Workflow-router chat responses use `format_a` by default. `format_a` is deterministic human-readable text: it includes a natural completion sentence, `run_id:`, a `Result:` contract block, readable summary fields, a bounded inline `Answer:` block for supported read-only artifacts, a `Draft proposal:` block for supported draft-only artifacts, and an `Artifacts:` section for audit. The structured top-level `agentic_controller_response` remains present for clients.

The `Result:` block is the first place a tester should look. It includes:

- workflow and status
- selected workflow
- selected skills
- selected tools
- next action
- verification command summary

The `Skill Selection:` block explains why the router selected the workflow, skills, and tools. It is grounded in `route-decision.json` evidence and registry metadata, not a separate model rewrite. It includes:

- matched route rules
- selector confidence and confidence reasons
- governed prompt-skill coverage entry IDs when a route rule maps to `runtime/prompt_skill_coverage.json`
- selected skill IDs and capability route keys when available
- selected tool IDs
- rejected workflow, skill, and tool candidate counts
- grounding markers such as `route_decision.evidence`

The `Context Sources:` block explains which source families the router selected before downstream context gathering. It includes selected and rejected source families, mapped tools, layout status, fixed budgets, evidence file samples, gaps, and grounding markers such as `route_decision.context_source_audit`. Users do not need to ask for `git_grep`, `structure_index`, or `codegraph_context` by name.

The inline `Answer:` block is rendered from controller artifacts, not from a second model rewrite. Supported artifact summaries include code explanation, behavior-existence checks, callers/usages, configuration lookup, pasted test-failure summary, related-test command discovery, L2 failing-test diagnosis with root-cause hypothesis, L2 multi-file behavior investigation, L2 dependency impact summary, L2 test selection with smallest/medium/broad command tiers, CI log failure summary, table definition/read/write lookup, runtime reproduction checklist, and user-facing message test target lookup. These summaries include the relevant rationale, evidence, gaps, verification command, and source-mutation state. Explicit multi-step decomposition prompts return a `Task Decomposition:` section with work packages, dependencies, approval gates, uncertainty, verification strategy, and mutation proof. The full artifact paths remain visible so users can inspect the durable JSON evidence when needed.

Long summary or artifact sections are bounded. When content is omitted, the response includes explicit omitted-count markers such as `omitted 30 artifact(s)`.

Use JSON when a client or user needs machine-readable assistant content. The selector uses this priority:

1. `output_format` or `agentic_output_format`
2. `metadata.output_format`
3. OpenAI-compatible `response_format`, including `{"type": "json_object"}`
4. natural-language phrases such as `Return JSON` or `respond with JSON`
5. default `format_a`

Example JSON request:

```json
{
  "model": "agentic-workflow-router",
  "output_format": "json",
  "messages": [
    {
      "role": "user",
      "content": "In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find where the placed_order_id stealth lookup begins. Read only."
    }
  ]
}
```

For JSON output, `choices[0].message.content` is a JSON object string. It includes `chat_contract` with the same selected workflow, selected skills, selected tools, next action, verification fields, and `selection_explanation` that `format_a` shows in the `Result:` and `Skill Selection:` blocks. The top-level `selection_explanation` object is also included for clients that want route rules, selected skill route keys, selected tools, and grounding markers without parsing text. The top-level `agentic_controller_response` is still returned separately.

Natural approval continuation is supported for a prior workflow-router run ID. The user can approve packet design in plain language, and the adapter recovers the target root from the prior run. Initial packet-design runs show an `Approval:` block with `State: waiting_for_approval` and `Type: packet_design`; approved continuations show `State: finished`. The router writes `approval-state.json` and links the continuation to the originating run. Duplicate, denied, expired, wrong-run, target-mismatch, and source-apply scope changes fail closed before implementation prep. Through the workflow-router gateway, these approval failures are converted to OpenAI-style chat responses so AnythingLLM can display the failure reason and next action.

When exact `packet_operations` are supplied by client metadata or embedded JSON, implementation prep runs through `execution_planning.plan` and `implementation.workflow` draft mode. When exact operations are missing, the router can ask the local model for bounded `replace_text` proposals from approved investigation artifacts; invalid, no-op, or unmatched proposals are written to `packet-operation-proposal.json` and block with a specific next action. Supported draft-only small text edits use deterministic packet generation without requiring the user to supply JSON.

Natural feedback capture is supported for prior run IDs through the same chat route. Messages such as `Record feedback for original run <run_id> and continuation run <run_id>: useful: ... missing: ...` are routed to the existing `workflow_feedback.record` workflow and linked to stored controller run records.

Natural L1 draft-packet prompts are supported for tightly scoped write-adjacent requests. Draft-only small documentation/text edits can produce `small_text_edit_proposal` artifacts, draft-only small unit-test additions can produce `small_unit_test_proposal` artifacts, and draft-only simple failing-test fixes can produce `simple_test_fix_proposal` artifacts. These routes delegate to `execution_planning.plan` and then to the existing `implementation.workflow` draft path; source files are hash-checked and must remain unchanged. The current deterministic unit-test auto-draft is intentionally narrow and supports the missing `exchange_order_id` sync case when an existing related pytest file can be selected. The current deterministic simple-fix auto-draft is also intentionally narrow and supports the `find_stealth_order_by_placed_order_id` docstring assertion that expects `client_order_id`.

Natural disposable-copy apply is supported only when the message explicitly says the operation is approved for disposable-copy apply and includes exact `packet_operations` JSON. The adapter sets `mode=apply_disposable_copy`, applies through the existing `implementation.workflow` path on a copied repository, records mutation proof, rolls the copy back, and proves the source repository did not change. Current disposable apply supports existing-file `replace_text` and `append_text`, including multi-operation packets across existing files. `create_file` remains blocked in apply mode with `unsupported_disposable_operation_kind`. This is the current AnythingLLM-safe apply validation path for protected frozen fixtures.

Natural L2 failing-test diagnosis is supported for read-only prompts that ask to diagnose, investigate, or identify the root cause of a pytest failure while explicitly saying not to edit or mutate files. It routes to `code_investigation.plan` and returns `downstream_test_failure_summary` with `Root cause hypothesis:`, `Smallest safe fix plan:`, `Verification:`, and `Source mutation: false` in default chat output.

Natural L2 multi-file behavior investigation is supported for read-only prompts that ask how a behavior flows across files or request participating files plus callers/usages. It routes to `code_investigation.plan` and returns `downstream_multi_file_behavior_investigation` with `Beginning point:`, `Participating files:`, `Callers/usages:`, `Related tests:`, `Risks:`, `Verification:`, and `Source mutation: false` in default chat output.

Natural L2 dependency impact summary is supported for read-only prompts that ask what would be impacted if a behavior or symbol changes. It routes to `code_investigation.plan` and returns `downstream_dependency_impact_summary` with `Impacted files:`, `Callers/usages:`, `Related tests:`, `Risk level:`, `Verification:`, and `Source mutation: false` in default chat output.

Natural L2 Batch E prompts are supported for four additional read-only coding-agent tasks:

- CI log triage routes to `ci-log-failure-summarizer` and returns `downstream_ci_failure_summary` with `First failing command:`, `Likely cause:`, and `Next local command:`.
- Table access lookup routes to `table-read-write-locator` and returns `downstream_table_read_write_lookup` with definition, read, and write sites.
- Runtime reproduction checklist prompts route to `runtime-reproduction-checklist-writer` and return `downstream_runtime_error_diagnosis` plus `downstream_reproduction_checklist`.
- User-facing message test-target prompts route to `user-facing-message-test-target-locator` and return `downstream_message_source_lookup` with source, user-facing assessment, and test-target output.

Natural L2 test selection is supported for read-only prompts that ask for smallest, medium, and broad validation commands with rationale. It routes to `code_investigation.plan` and returns `downstream_test_selection_plan` with `Smallest command:`, `Medium command:`, `Broad command:`, `Rationale:`, `Covered risks:`, `Confidence:`, `Gaps:`, and `Source mutation: false` in default chat output.

Natural task decomposition is supported for prompts that explicitly ask to decompose or break down a multi-step task into work packages, dependencies, approval gates, or a plan DAG. It routes to `task.decompose`, executes read-only by default, and returns `downstream_task_decomposition` with `Work packages:`, `Dependencies:`, `Approval gates:`, `Uncertainty:`, `Verification:`, and `Source mutation: false` in default chat output.

## Artifacts

Artifacts are written under `CONTROLLER_OUTPUT_ROOT/workflow-router/<run-id>/`:

- `request.json`
- `registry-snapshot.json`
- `route-decision.json`
- `downstream-result.json` when execution delegates
- `approval-state.json`
- `run-state.json`

The summary includes `route_status`, `selected_workflow`, `next_action`, `target_repo_read`, `model_router_status`, downstream fields when execution delegates, `verification_command_count` when downstream investigation found related test evidence, `approval_state_status`, `approval_type`, and `source_changed`, `source_tree_changed`, `disposable_copy_changed`, `copy_tree_restored`, `mutation_diff_file_count`, `mutation_diff_paths`, and `mutation_rollback_status` for disposable-copy apply.

`route-decision.json` records skill-selection evidence from the registry. Skill selection is now based on a `capability_contract` shortlist before trigger ordering, and the evidence includes selected skill IDs plus their capability route keys. The `selection_audit` object is the runtime selector contract: it records the selected workflow, selected skills, selected tools, confidence reasons, route rules, evidence sources, prompt-skill coverage entry IDs, selected/rejected workflow candidates, selected/rejected skill candidates, selected/rejected tool candidates, and the selection policy. The model-router observation is advisory evidence only; deterministic unsupported requests remain unsupported even if the model suggests a workflow.

`route-decision.json` also records `model_capability_routing`. This gate reads `runtime/model_capability_routing.json` and the active model capability profile. If the selected task class is not approved or conditionally approved with the required controller approval boundary, the route blocks before model-router calls, skill/tool selection, or downstream execution.

## Safety Boundary

- `plan_only` reads no target repository files.
- `execute_read_only` can run only `code_context.lookup`, `code_investigation.plan`, `refactor.single_path` in investigation mode, `skill_batch.propose`, or `task.decompose`.
- Natural chat routing requires an allowed target path in the latest user message.
- Natural approval continuation may use a prior workflow-router run ID as the target-root source only when that run is waiting for `packet_design` approval. Exact packet operations are required for completed implementation prep; generated proposals may block with an inspectable `packet_operation_proposal` artifact.
- Natural approval continuations expire after 24 hours. Duplicate approvals, denied approvals, wrong-run approvals, target mismatches, and source-apply scope changes fail closed.
- Natural packet-objective follow-up may continue after `request_packet_objective`; generated operations still must validate exactly, no-op proposals can become evidence-backed `no_change_needed`, and unsupported no-op proposals return `request_narrowed_edit_objective`.
- Natural narrowed-edit follow-up may continue after `request_narrowed_edit_objective`; exact supplied operations complete dry-run implementation prep. Live model-generated narrowed edits now produce validated exact `replace_text` operations on both frozen Coinbase fixtures, and compacted execution-planning context lets the downstream dry-run complete through the existing `implementation.workflow` draft path.
- Natural L1 small documentation edits, small unit-test additions, and simple failing-test fixes must be draft-only before the adapter creates packet-design approval. If draft-only intent is missing, the router stops at `request_approval`.
- Natural feedback capture records bounded feedback only; it does not approve implementation prep, apply packets, or mutate repositories.
- Approval-bypass requests are blocked.
- Implementation prep requires approval and exact packet operations or controller-validated generated packet operations.
- Direct source apply is blocked.
- `apply_disposable_copy` requires `approval.status=approved_for_disposable_apply`, `approval.apply_allowed=true`, and `approval.apply_scope=disposable_copy_only`.
- Raw CodeGraphContext, raw MCP, and Cypher requests are blocked.
- Unsupported non-development requests are rejected as unsupported.

## Validation

Focused regression:

```bash
pytest tests/regression/test_controller_service.py -q
```

Live validation:

```bash
python scripts/validate_workflow_router.py \
  --controller-url http://127.0.0.1:8400 \
  --role-base-url http://127.0.0.1:8300/v1 \
  --require-model-router \
  --include-read-only-execution \
  --include-implementation-prep \
  --include-disposable-apply \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github
```

Phase 98 disposable-apply expansion validation:

```bash
python3 scripts/validate_disposable_apply_expansion.py \
  --port-health \
  --live-gateway \
  --live-anythingllm \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --timeout-seconds 900
```

Gateway and AnythingLLM explicit-envelope validation:

```bash
python scripts/validate_gateway_controller_route.py \
  --mode workflow_router_apply_disposable_copy \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github
```

L1 product-suite gateway and AnythingLLM validation:

```bash
python scripts/validate_workflow_router_l1_suite.py \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github
```

L2 product-suite gateway and AnythingLLM validation:

```bash
python scripts/validate_workflow_router_l2_suite.py \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github
```

Runtime skill-selection hardening validation:

```bash
python scripts/validate_skill_selection_hardening.py \
  --live-gateway \
  --live-anythingllm \
  --model-base-url http://127.0.0.1:8000/v1 \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --controller-base-url http://127.0.0.1:8400 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github
```

Task decomposition gateway and AnythingLLM validation:

```bash
python scripts/validate_task_decomposition_live.py \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --controller-base-url http://127.0.0.1:8400 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github
```

Controlled small-change apply gateway and AnythingLLM validation:

```bash
python scripts/validate_controlled_small_change_apply_live.py \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --controller-base-url http://127.0.0.1:8400 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github
```

Advanced natural-language gateway and AnythingLLM validation:

```bash
python scripts/validate_workflow_router_natural_clients.py \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --include-approval-continuation \
  --include-feedback-record
```

Generated packet-proposal validation:

```bash
python scripts/validate_workflow_router_natural_clients.py \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --include-approval-continuation \
  --generated-packet-continuation \
  --allow-generated-packet-block \
  --include-packet-objective-followup \
  --allow-packet-objective-block \
  --include-narrowed-edit-followup \
  --include-feedback-record
```

Phase 96 implementation-prep expansion validation:

```bash
python scripts/validate_implementation_prep_expansion.py \
  --skip-direct \
  --live-gateway \
  --output-path runtime-state/implementation-prep-expansion/phase96-implementation-prep-gateway.json
```

AnythingLLM Phase 96 validation:

```bash
python scripts/validate_implementation_prep_expansion.py \
  --skip-direct \
  --live-anythingllm \
  --output-path runtime-state/implementation-prep-expansion/phase96-implementation-prep-anythingllm.json
```

Phase 97 approval continuation robustness validation:

```bash
python scripts/validate_approval_continuation_robustness.py \
  --output-path runtime-state/approval-continuation-robustness/phase97-approval-direct.json
```

```bash
python scripts/validate_approval_continuation_robustness.py \
  --skip-direct \
  --live-gateway \
  --port-health \
  --output-path runtime-state/approval-continuation-robustness/phase97-approval-gateway.json
```

```bash
python scripts/validate_approval_continuation_robustness.py \
  --skip-direct \
  --live-anythingllm \
  --port-health \
  --output-path runtime-state/approval-continuation-robustness/phase97-approval-anythingllm.json
```

Generated narrowed-edit validation:

```bash
python scripts/validate_workflow_router_natural_clients.py \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --include-approval-continuation \
  --generated-packet-continuation \
  --allow-generated-packet-block \
  --include-packet-objective-followup \
  --allow-packet-objective-block \
  --include-narrowed-edit-followup \
  --generated-narrowed-edit-followup \
  --include-feedback-record
```

## References

- Roadmap: [docs/ACTIONABLE_WORKFLOW_ROADMAP.md](docs/ACTIONABLE_WORKFLOW_ROADMAP.md)
- Examples: [docs/examples/workflow-router.md](docs/examples/workflow-router.md)
