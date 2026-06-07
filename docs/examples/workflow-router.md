# Workflow Router Examples

These examples validate natural-language route planning, natural client routing, read-only execution, approved implementation prep, and disposable-copy apply proof through the controller.

## Natural Workflow Request

Use the dedicated workflow-router gateway for normal natural-language workflow requests. This is the path AnythingLLM should use when testing workflows without JSON envelopes.

```bash
curl -s http://127.0.0.1:8500/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "agentic-workflow-router",
    "messages": [
      {
        "role": "user",
        "content": "In /mnt/c/coinbase_testing_repo_frozen_tmp.github, refactor the placed_order_id stealth lookup so there is only one code path. Start from the logic beginning point, investigate first, create an implementation plan, wait for approval before implementation prep, and provide verification commands."
      }
    ]
  }'
```

Expected summary includes:

```json
{
  "route_status": "ready",
  "selected_workflow": "refactor.single_path",
  "downstream_workflow": "refactor.single_path",
  "next_action": "request_approval",
  "approval_state_status": "waiting_for_approval",
  "approval_type": "packet_design",
  "target_repo_read": true,
  "verification_command_count": 1
}
```

Expected chat-visible approval markers:

- `Approval:`
- `State: waiting_for_approval`
- `Type: packet_design`

Expected chat-visible skill-selection markers:

- `Skill Selection:`
- `Why: Selected refactor.single_path`
- `single_path_refactor_terms`
- `route_decision.evidence`

AnythingLLM natural workflow testing should use this base URL:

```text
http://127.0.0.1:8500/v1
```

## Output Format Selection

The default assistant-visible content is `format_a`: deterministic human-readable text with `run_id:`, a `Result:` block, summary fields, a bounded inline `Answer:` block for supported L1 read-only artifacts, and `Artifacts:` for audit. The top-level `agentic_controller_response` remains available in the API response.

Expected `Result:` markers:

- `Selected workflow:`
- `Selected skills:`
- `Selected tools:`
- `Next action:`
- `Verification:`

Expected `Skill Selection:` markers:

- `Why:`
- `Route rules:`
- `Skills:`
- `Tools:`
- `Grounded in: route_decision.evidence`

For example, an L1 explain-code prompt should return key inputs, outputs, side effects, related tests, and source refs directly in `choices[0].message.content`; the JSON artifact path is still listed afterward for full inspection.

Request strict JSON content with `output_format`:

```bash
curl -s http://127.0.0.1:8500/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "agentic-workflow-router",
    "output_format": "json",
    "messages": [
      {
        "role": "user",
        "content": "In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find where the placed_order_id stealth lookup begins. Read only."
      }
    ]
  }'
```

Or use OpenAI-compatible response format:

```json
{
  "response_format": {"type": "json_object"}
}
```

The same selector also accepts natural text such as `Return JSON`. JSON content includes `chat_contract`, which is the structured equivalent of the `Result:` block, plus `selection_explanation` with route rules, selected skill route keys, selected tools, and grounding markers.

## Natural L1 Simple Fix Draft

Use this as a smaller first write-adjacent route before advanced refactor prompts. It drafts through `execution_planning.plan` and `implementation.workflow`; it must not mutate the target repo.

```bash
curl -s http://127.0.0.1:8500/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "agentic-workflow-router",
    "messages": [
      {
        "role": "user",
        "content": "In /mnt/c/coinbase_testing_repo_frozen_tmp.github, inspect this failing test and propose the smallest fix. Draft only; do not apply until approved.\nFAILED tests/unit/test_order_id_and_followup_rules.py::test_find_stealth_order_by_placed_order_id_uses_client_order_id_index - AssertionError: expected find_stealth_order_by_placed_order_id docstring to mention client_order_id"
      }
    ]
  }'
```

Expected markers:

- `workflow_router.plan completed`
- `execution_planning.plan`
- `simple_test_fix_proposal`
- `downstream_implementation_workflow_report`
- `run_id: workflow-router-...`
- selected frozen files remain unchanged

## Natural L2 Test Selection

Use this when the tester wants validation tiers before implementation. It stays read-only and returns command rationale directly in the chat body.

```bash
curl -s http://127.0.0.1:8500/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "agentic-workflow-router",
    "messages": [
      {
        "role": "user",
        "content": "In /mnt/c/coinbase_testing_repo_frozen_tmp.github, choose the smallest, medium, and broad validation commands for placed_order_id stealth lookup. Read only. Explain why each command is relevant, what risk it covers, and what gaps remain."
      }
    ]
  }'
```

Expected markers:

- `workflow_router.plan completed`
- `code_investigation.plan`
- `downstream_test_selection_plan`
- `Smallest command:`
- `Medium command:`
- `Broad command:`
- `Rationale:`
- `Covered risks:`
- `Gaps:`
- `Source mutation: false`
- selected frozen files remain unchanged

## Natural Approval Continuation

After a natural investigation run returns a `workflow-router-...` run ID, packet-design approval can continue through the same natural gateway. Exact operations produce a completed `execution_planning.plan` dry run. If exact operations are omitted, the router asks the local model for bounded packet proposals from the approved investigation; empty or invalid proposals block with a `packet_operation_proposal` artifact instead of inventing edits.

```bash
curl -s http://127.0.0.1:8500/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "agentic-workflow-router",
    "messages": [
      {
        "role": "user",
        "content": "Approve packet design for run workflow-router-20260604T000000000000Z. Use packet operations: [{\"kind\":\"replace_text\",\"path\":\"docs/agents/INVARIANTS.md\",\"old\":\"exact old text\",\"new\":\"exact new text\"}]"
      }
    ]
  }'
```

Expected summary when exact operations are present:

```json
{
  "route_status": "ready",
  "selected_workflow": "execution_planning.plan",
  "downstream_workflow": "execution_planning.plan",
  "downstream_status": "completed",
  "approval_state_status": "finished",
  "approval_type": "packet_design"
}
```

Expected chat-visible continuation markers:

- `Approval:`
- `State: finished`
- `Type: packet_design`

Duplicate approval messages for the same source run fail closed with `approval_already_consumed`. Denied approvals fail with `approval_denied`, expired approvals fail with `approval_expired`, and approvals for runs that are not waiting for packet design fail with `approval_not_pending`.

Generated proposal continuation:

```bash
curl -s http://127.0.0.1:8500/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "agentic-workflow-router",
    "messages": [
      {
        "role": "user",
        "content": "Approve packet design for run workflow-router-20260604T000000000000Z. Proceed with implementation prep."
      }
    ]
  }'
```

Expected generated-proposal behavior:

- if a proposed operation validates, the response includes `downstream_implementation_workflow_report`
- if no safe operation validates, the response is blocked with `next_action=request_packet_objective` and includes `packet_operation_proposal`
- in both cases the source repository remains unchanged

Expected summary when exact operations are omitted and no generated operation validates:

```json
{
  "route_status": "blocked",
  "selected_workflow": "execution_planning.plan",
  "next_action": "request_packet_objective"
}
```

## Natural Packet Objective Follow-Up

When generated proposal continuation returns `next_action=request_packet_objective`, continue with a normal natural-language message. The router recovers the target root and approved investigation context from the prior run.

```bash
curl -s http://127.0.0.1:8500/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "agentic-workflow-router",
    "messages": [
      {
        "role": "user",
        "content": "For run workflow-router-20260604T000001000000Z, packet objective: make core/stealth_order_manager.py the authoritative placed_order_id lookup path. Draft only."
      }
    ]
  }'
```

Expected behavior:

- if exact generated operations validate, the response includes `downstream_implementation_workflow_report`
- if the local model explicitly claims no change is needed and bounded source snippets support that claim, the response includes `packet_objective_outcome_status=no_change_needed`
- if the local model proposes no-op or invalid exact text without enough no-change evidence, the response remains blocked with `request_narrowed_edit_objective` or `request_packet_objective`
- selected frozen source files remain unchanged

Observed blocked behavior before Phase 8:

```json
{
  "route_status": "blocked",
  "next_action": "request_packet_objective",
  "packet_operation_count": 0,
  "rejected_operation_count": 1,
  "proposal_validation_failures": {
    "noop_operation": 1
  }
}
```

Latest observed live behavior on June 4, 2026:

```json
{
  "route_status": "ready",
  "next_action": "none",
  "packet_objective_outcome_status": "no_change_needed"
}
```

## Natural Narrowed Edit Follow-Up

When packet-objective follow-up returns `request_narrowed_edit_objective`, continue with a normal natural-language message. The router recovers the target root, approved investigation run, and prior packet objective from the prior run.

```bash
curl -s http://127.0.0.1:8500/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "agentic-workflow-router",
    "messages": [
      {
        "role": "user",
        "content": "For run workflow-router-20260604T000002000000Z, narrowed edit objective: change docs/agents/INVARIANTS.md by adding the natural narrowed-edit dry-run proof line. Draft only. Use packet operations: [{\"kind\":\"replace_text\",\"path\":\"docs/agents/INVARIANTS.md\",\"old\":\"exact old text\",\"new\":\"exact new text\"}]"
      }
    ]
  }'
```

Expected behavior:

- `narrowed_edit_objective_status=accepted`
- exact operations complete `execution_planning.plan` dry run
- the route decision still records the recovered prior `packet_objective`
- selected frozen source files remain unchanged

Generated narrowed-edit behavior:

- if the user omits `packet_operations`, the local model proposes exact `replace_text` operations from bounded source snippets
- generated operations are accepted only when `old` text matches exactly once and `new` differs from `old`
- validated generated operations run through `execution_planning.plan` dry-run with compacted model-facing context, then through the existing `implementation.workflow` draft path
- if downstream execution planning fails, the response remains inspectable with `failed_skill`, `retry_guidance`, `packet_operation_proposal.status=ready`, and `downstream_status=failed`

Generated narrowed-edit example:

```bash
curl -s http://127.0.0.1:8500/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "agentic-workflow-router",
    "messages": [
      {
        "role": "user",
        "content": "For run workflow-router-20260604T000002000000Z, narrowed edit objective: change core/stealth_order_manager.py by replacing the comment above self._placed_order_index[placed_order_id] = order so it explicitly says Authoritative placed_order_id lookup source for all order_engine callers. Draft only."
      }
    ]
  }'
```

Latest generated narrowed-edit summary shape:

```json
{
  "route_status": "ready",
  "selected_workflow": "execution_planning.plan",
  "next_action": "none",
  "narrowed_edit_objective_status": "accepted",
  "downstream_workflow": "execution_planning.plan",
  "downstream_status": "completed"
}
```

## Natural Feedback Capture

After an initial run and approval-continuation run, feedback can be captured through the same natural gateway. The controller records it through `workflow_feedback.record` and links the continuation run plus any related run IDs mentioned in the message.

```bash
curl -s http://127.0.0.1:8500/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "agentic-workflow-router",
    "messages": [
      {
        "role": "user",
        "content": "Record feedback for original run workflow-router-20260604T000000000000Z and continuation run workflow-router-20260604T000001000000Z: useful: the route returned inspectable artifacts. missing: generate exact packet operations automatically from the approved investigation."
      }
    ]
  }'
```

Expected summary:

```json
{
  "target_workflow": "workflow_router.plan",
  "linked_run_found": true,
  "feedback_counts": {
    "useful": 1,
    "missing": 1
  }
}
```

## Direct Route Request

```bash
curl -s http://127.0.0.1:8400/v1/controller/workflow-router/plans \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow": "workflow_router.plan",
    "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
    "user_request": "Refactor the placed_order_id stealth lookup so there is only one code path. Start from the logic beginning point, investigate first, create an implementation plan, wait for approval before implementation prep, and provide verification commands.",
    "mode": "plan_only",
    "role_base_url": "http://127.0.0.1:8300/v1"
  }'
```

Expected summary:

```json
{
  "route_status": "ready",
  "selected_workflow": "refactor.single_path",
  "next_action": "execute_read_only",
  "target_repo_read": false
}
```

## Ambiguous Request

```bash
curl -s http://127.0.0.1:8400/v1/controller/workflow-router/plans \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow": "workflow_router.plan",
    "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
    "user_request": "fix it"
  }'
```

Expected summary:

```json
{
  "route_status": "blocked",
  "selected_workflow": null,
  "next_action": "ask_blocking_question"
}
```

## Read-Only Execution

```bash
curl -s http://127.0.0.1:8400/v1/controller/workflow-router/plans \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow": "workflow_router.plan",
    "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
    "user_request": "Refactor the placed_order_id stealth lookup so there is only one code path. Start from the logic beginning point, investigate first, create an implementation plan, wait for approval before implementation prep, and provide verification commands.",
    "mode": "execute_read_only",
    "role_base_url": "http://127.0.0.1:8300/v1"
  }'
```

Expected summary includes:

```json
{
  "route_status": "ready",
  "selected_workflow": "refactor.single_path",
  "downstream_workflow": "refactor.single_path",
  "downstream_status": "completed",
  "target_repo_read": true,
  "verification_command_count": 1
}
```

## Implementation Prep

Use implementation prep only after packet-design approval and only with exact packet operations.

```bash
curl -s http://127.0.0.1:8400/v1/controller/workflow-router/plans \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow": "workflow_router.plan",
    "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
    "user_request": "Prepare implementation packet candidates for an approved documentation clarification that client_order_id owns internal lookup paths.",
    "mode": "implementation_prep",
    "role_base_url": "http://127.0.0.1:8300/v1",
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
  }'
```

Expected summary includes:

```json
{
  "route_status": "ready",
  "selected_workflow": "execution_planning.plan",
  "downstream_workflow": "execution_planning.plan",
  "downstream_status": "completed"
}
```

## Disposable-Copy Apply

Use disposable-copy apply only after disposable-only approval. The source repo is copied first; apply mode runs against the copy through `implementation.workflow`.

```bash
curl -s http://127.0.0.1:8400/v1/controller/workflow-router/plans \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow": "workflow_router.plan",
    "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp.github",
    "user_request": "Apply approved packet operations to a disposable copy for mutation proof that client_order_id owns internal lookup paths.",
    "mode": "apply_disposable_copy",
    "role_base_url": "http://127.0.0.1:8300/v1",
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
  }'
```

Expected summary includes:

```json
{
  "route_status": "ready",
  "selected_workflow": "execution_planning.plan",
  "downstream_workflow": "implementation.workflow",
  "downstream_status": "completed",
  "source_changed": false,
  "disposable_copy_changed": true
}
```

## Gateway And AnythingLLM Route

This validates the same workflow-router disposable-copy path through the OpenAI-compatible gateway and AnythingLLM workspace API.

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_gateway_controller_route.py \
  --mode workflow_router_apply_disposable_copy \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --timeout-seconds 900
```

## L1 Product Suite Validator

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_workflow_router_l1_suite.py \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --timeout-seconds 900
```

This is the first user-facing validator. It verifies all 11 L1 prompts through both the gateway and AnythingLLM, including inline `Answer:` content for read-only L1s and `Draft proposal:` content for draft-only L1s.

## L2 Product Suite Validator

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_workflow_router_l2_suite.py \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --timeout-seconds 900
```

The current L2 validator covers `L2-001`, `L2-002`, `L2-003`, `L2-005`, and `L2-006` through `L2-013`. It verifies the selected workflow, selected Batch E skill IDs, route rules, required downstream artifacts, chat-visible markers, artifact JSON content for Batch E, `Source mutation: false`, watched file hashes, and protected fixture cleanliness through both the gateway and AnythingLLM.

## Advanced Natural Client Validator

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_workflow_router_natural_clients.py \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --timeout-seconds 900 \
  --include-approval-continuation \
  --generated-packet-continuation \
  --allow-generated-packet-block \
  --include-packet-objective-followup \
  --allow-packet-objective-block \
  --include-narrowed-edit-followup \
  --generated-narrowed-edit-followup \
  --include-feedback-record
```

Latest proof from June 4, 2026:

- Exact packet track passed through Bash gateway for `/mnt/c/coinbase_testing_repo_frozen_tmp`: `workflow-router-20260604T111415362381Z` -> `workflow-router-20260604T111428002179Z` -> `workflow-feedback-20260604T111815486101Z`
- Exact packet track passed through Bash gateway for `/mnt/c/coinbase_testing_repo_frozen_tmp.github`: `workflow-router-20260604T111815547000Z` -> `workflow-router-20260604T111826610689Z` -> `workflow-feedback-20260604T112235367617Z`
- Exact packet track passed through AnythingLLM for `/mnt/c/coinbase_testing_repo_frozen_tmp`: `workflow-router-20260604T112235426271Z` -> `workflow-router-20260604T112249188920Z` -> `workflow-feedback-20260604T112656201064Z`
- Exact packet track passed through AnythingLLM for `/mnt/c/coinbase_testing_repo_frozen_tmp.github`: `workflow-router-20260604T112656252297Z` -> `workflow-router-20260604T112707118428Z` -> `workflow-feedback-20260604T113119852968Z`
- Generated proposal track blocked honestly with `request_packet_objective` and `packet_operation_proposal` artifacts through Bash gateway for both fixtures: `workflow-router-20260604T111037316616Z`, `workflow-router-20260604T111059462631Z`
- Generated proposal track blocked honestly with `request_packet_objective` and `packet_operation_proposal` artifacts through AnythingLLM for both fixtures: `workflow-router-20260604T111125508784Z`, `workflow-router-20260604T111146208412Z`
- Packet-objective follow-up track passed through Bash gateway for both fixtures and blocked honestly on no-op generated operations: `workflow-router-20260604T132036153515Z`, `workflow-router-20260604T132100969717Z`
- Packet-objective follow-up track passed through AnythingLLM for both fixtures and blocked honestly on no-op generated operations: `workflow-router-20260604T132126194067Z`, `workflow-router-20260604T132150922475Z`
- No-change track passed through Bash gateway for both fixtures: `workflow-router-20260604T134833016973Z` (`no_change_needed`, `verification_command_count=5`), `workflow-router-20260604T134857836765Z` (`no_change_needed`, `verification_command_count=5`)
- No-change track passed through AnythingLLM for both fixtures: `workflow-router-20260604T134924203677Z` (`no_change_needed`, `verification_command_count=5`), `workflow-router-20260604T134948062560Z` (`no_change_needed`, `verification_command_count=5`)
- Narrowed-objective branch is covered by regression with unsupported no-op claims.
- Narrowed-edit exact-operation track passed through Bash gateway for both fixtures: `workflow-router-20260604T140504669738Z`, `workflow-router-20260604T140729099692Z`
- Narrowed-edit exact-operation track passed through AnythingLLM for both fixtures: `workflow-router-20260604T141011494906Z`, `workflow-router-20260604T141227032729Z`
- Generated narrowed-edit strict track produced one validated operation and completed downstream dry-run through Bash gateway for both fixtures: `workflow-router-20260604T155720726733Z`, `workflow-router-20260604T155824959110Z`
- Generated narrowed-edit strict track produced one validated operation and completed downstream dry-run through AnythingLLM for both fixtures: `workflow-router-20260604T155931976617Z`, `workflow-router-20260604T160035235329Z`

## Live Validator

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_workflow_router.py \
  --controller-url http://127.0.0.1:8400 \
  --role-base-url http://127.0.0.1:8300/v1 \
  --require-model-router \
  --include-read-only-execution \
  --include-implementation-prep \
  --include-disposable-apply \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github
```
