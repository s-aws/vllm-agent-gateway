# AnythingLLM Founder Testing Recipes

These recipes are for hands-on founder/testing runs through AnythingLLM after the gateway and controller are running.

First-time testers should start with [Getting Started With AnythingLLM](../../README.getting-started.md). This file is the deeper recipe and validation history.

For natural workflow-router testing, AnythingLLM should point at:

```text
http://127.0.0.1:8500/v1
```

For ordinary model chat, skill-smoke prompts, and explicit `agentic_controller_request` envelope testing, use:

```text
http://127.0.0.1:8300/v1
```

Do not point the workspace at `8400`; that is the controller service, not an OpenAI-compatible gateway.

## Current Boundary

AnythingLLM can run `workflow_router.plan` from natural-language messages when configured to `8500/v1`. It can also run controller workflows through explicit `agentic_controller_request` envelopes when configured to `8300/v1`.

The product path is the natural workflow-router route. The older prompt-injected skill smoke remains here only as a support check for local-model instruction following; it is not evidence that the harness product is usable.

## Preflight

Start or restart the stack with the project repo and both frozen fixtures allowlisted:

```powershell
bash -lc "cd /mnt/c/agentic_agents && ./stop-agent-prompt-proxies.sh && CONTROLLER_ALLOWED_TARGET_ROOTS='/mnt/c/agentic_agents:/mnt/c/coinbase_testing_repo_frozen_tmp:/mnt/c/coinbase_testing_repo_frozen_tmp.github' CONTROLLER_DEFAULT_ROLE_BASE_URL='http://127.0.0.1:8300/v1' ./start-agent-prompt-proxies.sh"
```

Confirm AnythingLLM API access:

```powershell
$env:WSLENV='ANYTHINGLLM_API_KEY'
bash -lc "curl -s http://127.0.0.1:3001/api/ping && echo"
```

Point AnythingLLM at the natural workflow-router gateway:

```powershell
$headers = @{ Authorization = "Bearer $env:ANYTHINGLLM_API_KEY"; "Content-Type" = "application/json" }
$body = @{
  GenericOpenAiBasePath = "http://127.0.0.1:8500/v1"
  GenericOpenAiModelPref = "Qwen3-Coder-30B-A3B-Instruct"
} | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:3001/api/system/update-env" -Headers $headers -Method Post -Body $body
```

## Natural Workflow Router Through AnythingLLM

The broad refactor prompt below is advanced validation, not the first L1 skill test. First-time testers should use the smaller prompt in [Getting Started With AnythingLLM](../../README.getting-started.md), and L1 prompt candidates are listed in [L1 Coding Agent Prompt Backlog](../L1_CODING_AGENT_PROMPTS.md).

Default output is `format_a`, a deterministic human-readable response with `run_id:`, summary fields, bounded inline `Answer:` content for supported read-only artifacts, `Draft proposal:` content for supported draft-only artifacts, and artifact links. Users should be able to review the answer directly in the chat body; artifact files are for audit and deeper inspection. To request strict JSON from the AnythingLLM chat box, add a natural phrase such as `Return JSON`:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find where the placed_order_id stealth lookup begins. Read only. Return JSON with the entrypoint, evidence files, related tests, and confidence.
```

Expected JSON content:

- parses as a JSON object
- includes `workflow`, `status`, `run_id`, `summary`, and `artifacts`
- has `summary.selected_workflow` set to `code_investigation.plan`
- selected frozen files remain unchanged

Reusable L1 product-suite validation:

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_workflow_router_l1_suite.py \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --timeout-seconds 900
```

Reusable L2 product-suite validation:

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_workflow_router_l2_suite.py \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --timeout-seconds 900
```

Current L2 check:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, diagnose why this pytest failure is happening. Do not edit files. Return root cause, smallest safe fix plan, and verification command.
FAILED tests/unit/test_order_id_and_followup_rules.py::test_find_stealth_order_by_placed_order_id_uses_client_order_id_index - AssertionError: expected client_order_id index
E   AssertionError: expected client_order_id index
```

Expected response markers:

- `Root cause hypothesis:`
- `Smallest safe fix plan:`
- `Verification:`
- `Source mutation: false`
- selected frozen files remain unchanged

Multi-file L2 check:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, investigate how placed_order_id stealth lookup flows across source files. Read only. Return the beginning point, participating files, callers/usages, related tests, risks, and the smallest verification commands.
```

Expected response markers:

- `Beginning point:`
- `Participating files:`
- `Callers/usages:`
- `Related tests:`
- `Risks:`
- `Verification:`
- `Source mutation: false`

Dependency-impact L2 check:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, summarize the dependency impact if placed_order_id stealth lookup behavior changes. Read only. Return impacted source files, callers/usages, related tests, risk level, and recommended validation commands.
```

Expected response markers:

- `Impacted files:`
- `Callers/usages:`
- `Related tests:`
- `Risk level:`
- `Verification:`
- `Source mutation: false`

Test-selection L2 check:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, choose the smallest, medium, and broad validation commands for placed_order_id stealth lookup. Read only. Explain why each command is relevant, what risk it covers, and what gaps remain.
```

Expected response markers:

- `Smallest command:`
- `Medium command:`
- `Broad command:`
- `Rationale:`
- `Covered risks:`
- `Confidence:`
- `Gaps:`
- `Source mutation: false`

Simple L1 draft-packet check:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, inspect this failing test and propose the smallest fix. Draft only; do not apply until approved.
FAILED tests/unit/test_order_id_and_followup_rules.py::test_find_stealth_order_by_placed_order_id_uses_client_order_id_index - AssertionError: expected find_stealth_order_by_placed_order_id docstring to mention client_order_id
```

Expected response markers:

- `workflow_router.plan completed`
- `execution_planning.plan`
- `simple_test_fix_proposal`
- `downstream_implementation_workflow_report`
- `run_id: workflow-router-...`
- selected frozen files remain unchanged

Advanced refactor message, only after the L1 prompt checks work. Send it as normal AnythingLLM text; do not wrap it in JSON:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, refactor the placed_order_id stealth lookup so there is only one code path. Start from the logic beginning point, investigate first, create an implementation plan, wait for approval before implementation prep, and provide verification commands.
```

Expected response markers:

- `workflow_router.plan completed`
- `run_id: workflow-router-...`
- `selected_workflow`
- `refactor.single_path`
- `verification_command_count`
- `Artifacts:`
- selected frozen files remain unchanged

## Natural Approval Continuation

After the first response returns `run_id: workflow-router-...`, you can approve packet design from a normal AnythingLLM message. Exact packet operations produce completed implementation prep. If exact operations are missing, the controller asks the local model for bounded `replace_text` proposals from the approved investigation artifacts; empty or invalid proposals block with an inspectable `packet_operation_proposal` artifact.

```text
Approve packet design for run workflow-router-20260604T000000000000Z. Use packet operations: [{"kind":"replace_text","path":"docs/agents/INVARIANTS.md","old":"exact old text","new":"exact new text"}]
```

Expected response markers when exact operations are present:

- `workflow_router.plan completed`
- `selected_workflow': 'execution_planning.plan'`
- `downstream_status': 'completed'`
- `downstream_implementation_workflow_report`
- selected frozen files remain unchanged

Generated proposal message:

```text
Approve packet design for run workflow-router-20260604T000000000000Z. Proceed with implementation prep.
```

Expected generated-proposal markers:

- `workflow_router.plan completed`
- `execution_planning.plan`
- `packet_operation_proposal`
- either `downstream_implementation_workflow_report` for validated generated operations or `request_packet_objective` when no safe exact operation is available
- selected frozen files remain unchanged

## Natural Packet Objective Follow-Up

If the generated proposal response asks for `request_packet_objective`, send a normal AnythingLLM message that names the prior continuation run and the intended packet objective. Do not paste a controller envelope.

```text
For run workflow-router-20260604T000001000000Z, packet objective: make core/stealth_order_manager.py the authoritative placed_order_id lookup path. Draft only.
```

Expected response markers:

- `workflow_router.plan completed`
- `execution_planning.plan`
- `packet_objective`
- `packet_operation_proposal`
- `downstream_implementation_workflow_report` when generated operations validate, `no_change_needed` when the desired state is already supported, or `request_narrowed_edit_objective` / `request_packet_objective` when the model proposes no-op/invalid edits without enough evidence
- selected frozen files remain unchanged

Latest observed live behavior on June 4, 2026:

- AnythingLLM accepted the natural packet-objective follow-up on both frozen fixtures.
- The local model proposed no-op replacements and claimed no change was needed on both AnythingLLM fixture runs.
- The controller recorded `packet_objective_outcome.status=no_change_needed`, kept `packet_operations=[]`, and did not create implementation work.

## Natural Narrowed Edit Follow-Up

If the packet-objective response asks for `request_narrowed_edit_objective`, send a normal AnythingLLM message that names the prior packet-objective run and the specific behavior delta. Do not paste a controller envelope.

```text
For run workflow-router-20260604T000002000000Z, narrowed edit objective: change docs/agents/INVARIANTS.md by adding the natural narrowed-edit dry-run proof line. Draft only. Use packet operations: [{"kind":"replace_text","path":"docs/agents/INVARIANTS.md","old":"exact old text","new":"exact new text"}]
```

Expected response markers:

- `workflow_router.plan completed`
- `execution_planning.plan`
- `narrowed_edit_objective_status`
- `downstream_implementation_workflow_report`
- selected frozen files remain unchanged

Generated narrowed-edit message:

```text
For run workflow-router-20260604T000002000000Z, narrowed edit objective: change core/stealth_order_manager.py by replacing the comment above self._placed_order_index[placed_order_id] = order so it explicitly says Authoritative placed_order_id lookup source for all order_engine callers. Draft only.
```

Expected generated response markers:

- `workflow_router.plan completed`
- `execution_planning.plan`
- `narrowed_edit_objective_status`
- `packet_operation_proposal`
- `downstream_implementation_workflow_report`
- selected frozen files remain unchanged

Current behavior:

- The localhost model generates a validated exact narrowed-edit operation without supplied `packet_operations`.
- The downstream `execution_planning.plan` dry-run uses compacted model-facing context and completes through `implementation.workflow` draft mode.

## Natural Feedback Capture

After the approval-continuation response returns a second `workflow-router-...` run ID, you can record feedback from a normal AnythingLLM message:

```text
Record feedback for original run workflow-router-20260604T000000000000Z and continuation run workflow-router-20260604T000001000000Z: useful: the route returned inspectable artifacts and preserved the frozen repository. missing: generate exact packet operations automatically from the approved investigation.
```

Expected response markers:

- `workflow_feedback.record completed`
- `target_run_id`
- `linked_run_found`
- `feedback_record`
- selected frozen files remain unchanged

Validate the same path through the AnythingLLM API:

```powershell
$env:WSLENV='ANYTHINGLLM_API_KEY'
bash -lc "cd /mnt/c/agentic_agents && python3 scripts/validate_workflow_router_natural_clients.py --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 --target-root /mnt/c/coinbase_testing_repo_frozen_tmp --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github --timeout-seconds 900 --include-approval-continuation --include-feedback-record"
```

Validate generated proposal attempts:

```powershell
$env:WSLENV='ANYTHINGLLM_API_KEY'
bash -lc "cd /mnt/c/agentic_agents && python3 scripts/validate_workflow_router_natural_clients.py --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 --target-root /mnt/c/coinbase_testing_repo_frozen_tmp --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github --timeout-seconds 900 --include-approval-continuation --generated-packet-continuation --allow-generated-packet-block --include-packet-objective-followup --allow-packet-objective-block --include-narrowed-edit-followup --generated-narrowed-edit-followup --include-feedback-record"
```

## Quick Skill Smoke Through AnythingLLM API

This validates that the current AnythingLLM workspace, gateway, and local model can follow `codegraph-context-lookup` without running the full nine-skill chain.

Use `http://127.0.0.1:8300/v1` for this section because it is a model skill-smoke prompt, not natural workflow-router routing.

Copied frozen repo:

```powershell
$env:WSLENV='ANYTHINGLLM_API_KEY'
bash -lc "cd /mnt/c/agentic_agents && python3 scripts/validate_anythingllm_execution_planning_skills.py --target-root /mnt/c/coinbase_testing_repo_frozen_tmp --workspace my-workspace --skip-chain --timeout-seconds 480 --verbose"
```

Git-enabled frozen repo:

```powershell
$env:WSLENV='ANYTHINGLLM_API_KEY'
bash -lc "cd /mnt/c/agentic_agents && python3 scripts/validate_anythingllm_execution_planning_skills.py --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github --workspace my-workspace --skip-chain --timeout-seconds 480 --verbose"
```

Expected markers:

- `ANYTHINGLLM SKILL PASS codegraph-context-lookup`
- `status: ready`
- `relationship_query_count: 1`
- `next_step: impact-map-builder`

The validator uses a fresh `sessionId` per prompt so prior AnythingLLM chat history does not consume the gateway input budget.

## Full Skill Chain Through AnythingLLM API

Copied frozen repo:

```powershell
$env:WSLENV='ANYTHINGLLM_API_KEY'
bash -lc "cd /mnt/c/agentic_agents && python3 scripts/validate_anythingllm_execution_planning_skills.py --target-root /mnt/c/coinbase_testing_repo_frozen_tmp --workspace my-workspace --timeout-seconds 480"
```

Git-enabled frozen repo:

```powershell
$env:WSLENV='ANYTHINGLLM_API_KEY'
bash -lc "cd /mnt/c/agentic_agents && python3 scripts/validate_anythingllm_execution_planning_skills.py --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github --workspace my-workspace --timeout-seconds 480"
```

Expected markers:

- `ANYTHINGLLM SKILL PASS codegraph-context-lookup`
- all nine endpoint skills pass
- `ANYTHINGLLM CHAIN PASS frozen-real-repo-full`
- `repo_mutated: false`

## Pasteable UI: Code Context Relationship Lookup

Paste this exact JSON object as a message in the AnythingLLM workspace:

```json
{"agentic_controller_request":{"workflow":"code_context.lookup","schema_version":1,"target_root":"/mnt/c/coinbase_testing_repo_frozen_tmp.github","query":"Find callers of reveal_order_slice before impact mapping.","paths":["core/stealth_order_manager.py"],"allowed_context_tools":["structure_index","git_grep","read_file","codegraph_context"],"relationship_queries":[{"kind":"callers","symbol":"reveal_order_slice","path":"core/stealth_order_manager.py","max_results":25}],"max_results":25,"max_files":5}}
```

Expected response markers:

- `code_context.lookup completed`
- `run_id: code-context-...`
- `Artifacts:`
- `lookup_results`
- `relationship_results`

## Pasteable UI: Single-Path Refactor Investigation

Paste this exact JSON object as a message in the AnythingLLM workspace:

```json
{"agentic_controller_request":{"workflow":"refactor.single_path","schema_version":1,"target_root":"/mnt/c/coinbase_testing_repo_frozen_tmp.github","user_request":"Investigate whether StealthOrderManager.find_stealth_order_by_placed_order_id has one path before planning a refactor.","behavior":"placed_order_id stealth lookup","entrypoint_hints":[{"path":"core/stealth_order_manager.py","symbol":"StealthOrderManager.find_stealth_order_by_placed_order_id","reason":"Known owner of placed-order lookup behavior."}],"queries":["find_stealth_order_by_placed_order_id","placed_order_id"],"paths":["core/stealth_order_manager.py","tests/unit/test_order_id_and_followup_rules.py","tests/regression/test_order_id_regression.py"],"max_results":50,"max_files":10}}
```

Expected response markers:

- `refactor.single_path completed`
- `summary.refactor_status` is approval-gated
- `Artifacts:`
- `refactor_plan`
- selected frozen files remain unchanged

## Pasteable UI: Feedback Capture

After a workflow run, replace `<run_id>` with the run ID returned by AnythingLLM:

```json
{"agentic_controller_request":{"workflow":"workflow_feedback.record","schema_version":1,"target_workflow":"refactor.single_path","target_run_id":"<run_id>","target_root":"/mnt/c/coinbase_testing_repo_frozen_tmp.github","feedback":{"useful":["The workflow returned inspectable artifacts."],"wrong":[],"missing":["Add one clearer next manual test instruction."],"too_slow":[],"too_noisy":[],"notes":"Founder UI test feedback."},"tester":{"id":"founder","surface":"AnythingLLM UI"},"request_payload":{"source":"docs/examples/anythingllm-founder-testing.md"},"artifact_refs":{}}}
```

Expected response markers:

- `workflow_feedback.record completed`
- `feedback_record`
- `linked_run_found: true` when the run ID exists

## Failure Signals

- A normal natural-language message should not trigger controller workflows.
- A normal natural-language workflow message should trigger controller workflows only when AnythingLLM is pointed at `8500/v1`.
- A controller request must be an explicit JSON object with one `agentic_controller_request`.
- If the controller health check does not include both frozen target roots, restart with the `CONTROLLER_ALLOWED_TARGET_ROOTS` command above.
- If a long AnythingLLM UI thread starts failing with context-budget errors, start a fresh thread or use the API validator, which isolates requests with `sessionId`.

## Last Validation

Latest local validation on June 4, 2026:

- quick `codegraph-context-lookup` AnythingLLM skill smoke passed for `/mnt/c/coinbase_testing_repo_frozen_tmp`
- quick `codegraph-context-lookup` AnythingLLM skill smoke passed for `/mnt/c/coinbase_testing_repo_frozen_tmp.github`
- earlier Phase 7 packet-objective follow-up passed through AnythingLLM for `/mnt/c/coinbase_testing_repo_frozen_tmp`: `workflow-router-20260604T132109277988Z` -> `workflow-router-20260604T132119283894Z` -> `workflow-router-20260604T132126194067Z` -> `workflow-feedback-20260604T132136078133Z`
- earlier Phase 7 packet-objective follow-up passed through AnythingLLM for `/mnt/c/coinbase_testing_repo_frozen_tmp.github`: `workflow-router-20260604T132136128105Z` -> `workflow-router-20260604T132143863767Z` -> `workflow-router-20260604T132150922475Z` -> `workflow-feedback-20260604T132158642873Z`
- earlier Phase 7 packet-objective runs blocked honestly on no-op generated operations; source fixture files remained unchanged
- natural no-change outcome passed through AnythingLLM for `/mnt/c/coinbase_testing_repo_frozen_tmp`: `workflow-router-20260604T134905567040Z` -> `workflow-router-20260604T134917084338Z` -> `workflow-router-20260604T134924203677Z` -> `workflow-feedback-20260604T134931581356Z`; `verification_command_count=5`
- natural no-change outcome passed through AnythingLLM for `/mnt/c/coinbase_testing_repo_frozen_tmp.github`: `workflow-router-20260604T134931637409Z` -> `workflow-router-20260604T134939226513Z` -> `workflow-router-20260604T134948062560Z` -> `workflow-feedback-20260604T134955658490Z`; `verification_command_count=5`
- natural narrowed-edit exact-operation follow-up passed through AnythingLLM for `/mnt/c/coinbase_testing_repo_frozen_tmp`: `workflow-router-20260604T140936814864Z` -> `workflow-router-20260604T140949057351Z` -> `workflow-router-20260604T140958458939Z` -> `workflow-router-20260604T141011494906Z` -> `workflow-feedback-20260604T141200392500`
- natural narrowed-edit exact-operation follow-up passed through AnythingLLM for `/mnt/c/coinbase_testing_repo_frozen_tmp.github`: `workflow-router-20260604T141200450197Z` -> `workflow-router-20260604T141211613857Z` -> `workflow-router-20260604T141218653541Z` -> `workflow-router-20260604T141227032729Z` -> `workflow-feedback-20260604T141438508491`
- exact code-context pasteable envelope passed through AnythingLLM API with run ID `code-context-20260604T060123070156Z`
- exact refactor pasteable envelope passed through AnythingLLM API with run ID `refactor-single-path-20260604T060133633371Z`
- natural workflow-router AnythingLLM route passed for `/mnt/c/coinbase_testing_repo_frozen_tmp` with run ID `workflow-router-20260604T075731753596Z`
- natural workflow-router AnythingLLM route passed for `/mnt/c/coinbase_testing_repo_frozen_tmp.github` with run ID `workflow-router-20260604T075742605162Z`
- natural workflow-router AnythingLLM initial and approval-continuation route passed for `/mnt/c/coinbase_testing_repo_frozen_tmp` with run IDs `workflow-router-20260604T094328669463Z` -> `workflow-router-20260604T094340087991Z`
- natural workflow-router AnythingLLM initial and approval-continuation route passed for `/mnt/c/coinbase_testing_repo_frozen_tmp.github` with run IDs `workflow-router-20260604T094751398516Z` -> `workflow-router-20260604T094800883455Z`
- the latest AnythingLLM initial run returned `verification_command_count=10`
- the latest AnythingLLM continuation run produced a downstream `implementation.workflow` draft report and preserved frozen source hashes
- natural workflow-router AnythingLLM initial, approval-continuation, and feedback route passed for `/mnt/c/coinbase_testing_repo_frozen_tmp` with run IDs `workflow-router-20260604T101610835736Z` -> `workflow-router-20260604T101622636557Z` -> `workflow-feedback-20260604T102025229590Z`
- natural workflow-router AnythingLLM initial, approval-continuation, and feedback route passed for `/mnt/c/coinbase_testing_repo_frozen_tmp.github` with run IDs `workflow-router-20260604T102025280005Z` -> `workflow-router-20260604T102034679429Z` -> `workflow-feedback-20260604T102354107876Z`
- exact packet AnythingLLM track passed for `/mnt/c/coinbase_testing_repo_frozen_tmp` with run IDs `workflow-router-20260604T112235426271Z` -> `workflow-router-20260604T112249188920Z` -> `workflow-feedback-20260604T112656201064Z`
- exact packet AnythingLLM track passed for `/mnt/c/coinbase_testing_repo_frozen_tmp.github` with run IDs `workflow-router-20260604T112656252297Z` -> `workflow-router-20260604T112707118428Z` -> `workflow-feedback-20260604T113119852968Z`
- generated proposal AnythingLLM track blocked honestly with `request_packet_objective` and `packet_operation_proposal` artifacts for both fixtures: `workflow-router-20260604T111125508784Z`, `workflow-router-20260604T111146208412Z`
- generated narrowed-edit strict AnythingLLM track produced one validated `replace_text` operation and completed downstream dry-run for `/mnt/c/coinbase_testing_repo_frozen_tmp`: `workflow-router-20260604T155919044661Z` -> `workflow-router-20260604T155927945123Z` -> `workflow-router-20260604T155929655471Z` -> `workflow-router-20260604T155931976617Z` -> `workflow-feedback-20260604T160024606902Z`
- generated narrowed-edit strict AnythingLLM track produced one validated `replace_text` operation and completed downstream dry-run for `/mnt/c/coinbase_testing_repo_frozen_tmp.github`: `workflow-router-20260604T160024655281Z` -> `workflow-router-20260604T160031425773Z` -> `workflow-router-20260604T160032912693Z` -> `workflow-router-20260604T160035235329Z` -> `workflow-feedback-20260604T160133143559Z`
