# Getting Started With AnythingLLM

This is the shortest path for a first-time tester to run the natural-language workflow product through AnythingLLM.

Use this before the deeper founder-testing recipes. The goal is to prove that AnythingLLM can send a normal L1 coding-agent message, the controller can select and run the right workflow, artifacts are written, and the frozen validation repos are not mutated.

Current stable-readiness status: the Phase 170 stable release refresh still provides the release decision, and Phases 180 through 185 added the current chat-quality hardening layer. The latest proof floor includes answer-first chat contracts, natural output-format selection, evidence relevance ranking, related-test discovery reliability, Phase 184 AnythingLLM UI replay, and the Phase 185 contextless-agent audit pack. Phase 186 is the active handoff-refresh phase.

## What This Proves

- AnythingLLM is pointed at the natural workflow-router gateway.
- The local model on `localhost:8000` is reached through the gateway/router stack.
- The current Priority 0 chat-quality proof reports `readiness=ready_for_founder_testing`.
- A normal natural-language request routes to `workflow_router.plan`.
- The controller can run small read-only L1 investigations against the frozen Coinbase fixtures.
- The controller can draft an exact small documentation edit through the existing implementation workflow without mutating source files.
- The controller can draft small config-default, exact-message, and assertion-update test proposals through the existing implementation workflow without mutating source files.
- The controller can apply exact approved packet operations to a disposable copy, roll the copy back, and prove frozen source files did not change.
- Source fixture files remain unchanged.
- Current Phase 184 UI replay cases for evidence relevance and related-test discovery pass through the browser-visible AnythingLLM path.
- Future blind-baseline audits can start from the Phase 185 contextless-agent audit pack.

## Prerequisites

- vLLM OpenAI-compatible server is already running on `http://127.0.0.1:8000/v1`.
- AnythingLLM is running on `http://127.0.0.1:3001`.
- The test fixtures exist:
  - `/mnt/c/coinbase_testing_repo_frozen_tmp`
  - `/mnt/c/coinbase_testing_repo_frozen_tmp.github`
- For API validation, `ANYTHINGLLM_API_KEY` is available in your Windows user environment.
- For automated Desktop UI validation, Python Playwright, system Chrome, and Node/npm `npx` are available.

## 1. Start The Local Harness

Run from PowerShell:

```powershell
bash -lc "cd /mnt/c/agentic_agents && ./stop-agent-prompt-proxies.sh && CONTROLLER_ALLOWED_TARGET_ROOTS='/mnt/c/agentic_agents:/mnt/c/coinbase_testing_repo_frozen_tmp:/mnt/c/coinbase_testing_repo_frozen_tmp.github' CONTROLLER_DEFAULT_ROLE_BASE_URL='http://127.0.0.1:8300/v1' ./start-agent-prompt-proxies.sh"
```

Expected important lines:

```text
llm gateway: http://127.0.0.1:8300 -> http://127.0.0.1:8000
workflow router gateway: http://127.0.0.1:8500 -> http://127.0.0.1:8400/v1/controller/workflow-router/chat/completions
controller service: http://127.0.0.1:8400
```

Quick health check from PowerShell:

```powershell
bash -lc 'for u in http://127.0.0.1:8000/v1/models http://127.0.0.1:8300/v1/models http://127.0.0.1:8500/v1/models http://127.0.0.1:8400/health; do curl -fsS --max-time 20 "$u" >/dev/null && echo "$u ok"; done'
```

Run the setup doctor from Bash before opening AnythingLLM:

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/run_first_time_user_doctor.py
```

Expected markers:

```text
FIRST TIME USER DOCTOR REPORT ...
FIRST TIME USER DOCTOR SUMMARY ...
FIRST TIME USER DOCTOR PASS
```

If it fails, fix the listed `failed_check_ids` before running prompt tests. See [README.first-time-user-doctor.md](README.first-time-user-doctor.md).

After a reboot or service restart, run the Phase 163 restart gate:

```bash
python3 scripts/validate_post_restart_runtime_readiness.py
```

Expected marker:

```text
POST RESTART RUNTIME READINESS PASS
```

Validate the release-channel contract before first prompt testing:

```bash
python3 scripts/validate_release_channels.py \
  --output-path runtime-state/release-channels/getting-started.json
```

Expected markers:

```text
RELEASE CHANNEL REPORT ...
RELEASE CHANNEL SUMMARY ...
RELEASE CHANNEL PASS
```

Use the `stable` channel for the current external tester path after the stable smoke passes. Use `release-candidate` when validating new changes before another promotion. See [README.release-channels.md](README.release-channels.md) and [README.stable-handoff.md](README.stable-handoff.md).

Run the security policy gate before sharing tester prompts:

```bash
python3 scripts/validate_security_policy.py \
  --output-path runtime-state/security-policy/getting-started.json
```

Expected markers:

```text
SECURITY POLICY REPORT ...
SECURITY POLICY SUMMARY ...
SECURITY POLICY PASS
```

See [README.security-policy.md](README.security-policy.md).

Run the stable chat-quality release gate before first founder testing:

```bash
python3 scripts/validate_stable_release_blocker_closure.py \
  --require-artifacts \
  --output-path runtime-state/stable-release-blocker-closure/phase131/phase131-stable-release-blocker-closure-report.json

python3 scripts/validate_stable_chat_quality_release.py \
  --require-artifacts \
  --output-path runtime-state/stable-chat-quality-release/phase130/phase130-stable-chat-quality-release-report.json
```

Expected markers:

```text
STABLE RELEASE BLOCKER CLOSURE PASS
STABLE CHAT QUALITY RELEASE PASS
```

The release summary should include `readiness=ready_for_founder_testing`, `passed_gate_count=11`, and `blocker_count=0`. See [README.stable-release-blocker-closure.md](README.stable-release-blocker-closure.md) and [README.stable-chat-quality-release.md](README.stable-chat-quality-release.md).

Refresh the current founder-testing proof floor and skill/tool batch decision:

```bash
python3 scripts/validate_stable_release_refresh.py \
  --policy-path runtime/stable_release_refresh_phase170_policy.json \
  --run-refresh \
  --execute-reset-start \
  --execute-recovery \
  --output-path runtime-state/stable-release-refresh/phase170/phase170-stable-release-refresh-report.json \
  --markdown-output-path runtime-state/stable-release-refresh/phase170/phase170-stable-release-refresh-report.md

python3 scripts/validate_skill_tool_gap_batch_proposal.py \
  --output-path runtime-state/skill-tool-gap-batch-proposal/phase161/phase161-skill-tool-gap-batch-proposal-report.json \
  --markdown-output-path runtime-state/skill-tool-gap-batch-proposal/phase161/phase161-skill-tool-gap-batch-proposal-report.md
```

Expected markers:

```text
PHASE170 STABLE RELEASE REFRESH PASS
PHASE161 SKILL TOOL GAP BATCH PROPOSAL PASS
```

The current Phase 170 summary should show `source_report_count=17`, `phase169_proposal_count=6`, `phase169_release_blocker_count=0`, and `validation_error_count=0`. The current Phase 161 summary should show `decision=no_new_batch_justified`, `gap_candidate_count=0`, `missing_skill_tool_finding_count=0`, and `non_batch_finding_count=14`. The six Phase 169 proposals were closed in Phases 171-176, then refreshed through the Phase 177-185 chat-quality hardening path.

After this setup path passes, use [README.external-tester-onboarding.md](README.external-tester-onboarding.md) for the contextless first-test prompt set and feedback capture templates.

## Minimum External Tester Dry Run

For the current founder-testing release, this is the minimum external tester proof. It uses the stable channel, `ONB-001`, AnythingLLM at `http://127.0.0.1:8500/v1`, and linked feedback capture. Run from Bash/WSL:

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/validate_external_tester_dry_run.py \
  --live-runtime \
  --include-feedback \
  --output-path runtime-state/external-tester-dry-run/phase147/phase147-external-tester-dry-run.json
```

Expected marker:

```text
EXTERNAL TESTER DRY RUN PASS
```

The first manual external-tester prompt is `ONB-001` in [README.external-tester-onboarding.md](README.external-tester-onboarding.md). The sample prompts below are useful after this minimum dry run passes.

Optional stable handoff smoke:

```bash
python3 scripts/validate_stable_handoff.py \
  --release-candidate-report runtime-state/v1-acceptance/phase90-v1-1-acceptance-final.json \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github
```

## 2. Point AnythingLLM At The Workflow Router

For natural workflow testing, AnythingLLM must use:

```text
http://127.0.0.1:8500/v1
```

Do not use `8400`; that is the controller service, not an OpenAI-compatible model endpoint. Use `8300/v1` only for ordinary model chat or explicit controller-envelope tests.

In AnythingLLM, configure the LLM provider as a Generic OpenAI-compatible provider:

- Base URL: `http://127.0.0.1:8500/v1`
- Model: `Qwen3-Coder-30B-A3B-Instruct`
- API key: any non-empty value if the UI requires one

Optional API update from PowerShell:

```powershell
$headers = @{ Authorization = "Bearer $env:ANYTHINGLLM_API_KEY"; "Content-Type" = "application/json" }
$body = @{
  GenericOpenAiBasePath = "http://127.0.0.1:8500/v1"
  GenericOpenAiModelPref = "Qwen3-Coder-30B-A3B-Instruct"
} | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:3001/api/system/update-env" -Headers $headers -Method Post -Body $body
```

## 3. Send One Natural Test Message

In a fresh AnythingLLM thread, send this as normal chat text:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find where the placed_order_id stealth lookup begins. Read only. Return the entrypoint, evidence files, related tests, and confidence.
```

Expected response markers:

- `I completed workflow_router.plan.`
- `workflow_router.plan completed`
- `run_id: workflow-router-...`
- `Result:`
- `Selected workflow:`
- `Selected skills:`
- `Selected tools:`
- `Next action:`
- `Verification:`
- `Skill Selection:`
- `Why:`
- `Route rules:`
- `Grounded in: route_decision.evidence`
- `selected_workflow`
- `code_investigation.plan`
- `verification_command_count`
- `Answer:`
- `Related tests:`
- `Recommended commands:`
- `Artifacts:`

That proves the natural-language route is working and the chat body is immediately useful without opening artifact files. It should not mutate either frozen fixture.

Optional automated Desktop UI E2E from PowerShell:

```powershell
$env:ANYTHINGLLM_API_KEY=[Environment]::GetEnvironmentVariable('ANYTHINGLLM_API_KEY','User')
python scripts\validate_anythingllm_ui_e2e.py `
  --anythingllm-api-base-url http://127.0.0.1:3001 `
  --workspace my-workspace `
  --prompt-catalog-path runtime\anythingllm_ui_prompt_cases.json `
  --timeout-seconds 900 `
  --output-path runtime-state\anythingllm-ui\getting-started-ui-replay.json `
  --case-id UI184-ERR-001 `
  --case-id UI184-RTD-001 `
  --case-id UI184-RTD-002
```

Expected marker:

```text
ANYTHINGLLM UI E2E PASS
```

This serves the extracted AnythingLLM Desktop UI bundle, drives it with Playwright and system Chrome, submits read-only Priority 0 prompts through `/stream-chat`, and writes screenshots plus fixture mutation proof under `runtime-state/anythingllm-ui/`. See [README.anythingllm-ui-e2e.md](README.anythingllm-ui-e2e.md).

The default visible response format is `format_a`: deterministic human-readable text with a natural completion sentence, a `Result:` block, summary fields, bounded inline `Answer:` content for supported L1 artifacts, and artifact links. The structured `agentic_controller_response` is still returned for API clients.

Advanced broad refactor prompts are intentionally excluded from this getting-started path. Keep first-time validation on the smaller read-only and draft-only prompts below.

Optional JSON output check:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find where the placed_order_id stealth lookup begins. Read only. Return JSON with the entrypoint, evidence files, related tests, and confidence.
```

Expected behavior:

- the assistant-visible response is valid JSON
- the JSON includes `workflow`, `status`, `run_id`, `chat_contract`, `selection_explanation`, `summary`, and `artifacts`
- `chat_contract.selected_workflow` is `code_investigation.plan`
- `selection_explanation.route_rules` is populated
- `summary.selected_workflow` is `code_investigation.plan`
- the frozen fixture remains unchanged

Optional contextless-audit-pack check:

```bash
python3 scripts/validate_contextless_agent_audit_pack.py \
  --output-path runtime-state/contextless-agent-audit-pack/getting-started-audit-pack.json
```

Expected marker:

```text
CONTEXTLESS AGENT AUDIT PACK PASS
```

Optional second L1 check:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find tests related to placed_order_id stealth lookup. Read only. Return test files, matching terms, and recommended test commands.
```

Expected response markers are the same, with `code_investigation.plan` selected and a non-zero `verification_command_count`.

Optional safe-command L1 check:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, recommend the smallest test command for placed_order_id stealth lookup. Read only. Explain why that command is relevant.
```

Expected response markers are the same, with `code_investigation.plan` selected and a non-zero `verification_command_count`.

Optional explanation L1 check:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, explain what find_stealth_order_by_placed_order_id does in core/stealth_order_manager.py. Read only. Include key inputs, outputs, side effects, and tests.
```

Expected response markers are the same, with `code_investigation.plan` selected and a `downstream_code_explanation` artifact listed. The artifact should identify `StealthOrderManager.find_stealth_order_by_placed_order_id`.

Optional behavior-exists L1 check:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, check whether placed_order_id stealth lookup already exists. Read only. Return evidence for yes, no, or unknown.
```

Expected response markers are the same, with `code_investigation.plan` selected and a `downstream_behavior_existence` artifact listed. The artifact should return `status=exists` and `answer=yes` for this fixture.

Optional callers/usages L1 check:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find callers/usages of find_stealth_order_by_placed_order_id. Read only. Group by file and explain each usage briefly.
```

Expected response markers are the same, with `code_context.lookup` selected and a `downstream_usage_summary` artifact listed. The artifact should group usages by file.

Optional config/env L1 check:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find where COINBASE_API_KEY environment variable is defined or used. Read only. Return files, references, and likely runtime effect.
```

Expected response markers are the same, with `code_investigation.plan` selected and a `downstream_configuration_lookup` artifact listed. The artifact should classify the `configuration.py` read as an environment read and avoid exposing any runtime secret value.

Optional pasted-failure L1 check:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, summarize this pasted test failure. Do not edit files. Return what failed, likely cause, and next bounded inspection step.
FAILED tests/unit/test_order_id_and_followup_rules.py::test_find_stealth_order_by_placed_order_id_uses_client_order_id_index - AssertionError: expected client_order_id index
E   AssertionError: expected client_order_id index
```

Expected response markers are the same, with `code_investigation.plan` selected and a `downstream_test_failure_summary` artifact listed. The artifact should identify `tests/unit/test_order_id_and_followup_rules.py` and `AssertionError`.

Optional small documentation edit L1 check:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, draft a small documentation edit to docs/agents/INVARIANTS.md. After "- Use one code path per behavior." add "- L1-010 draft proof: route small documentation edits through packet dry-run.". Do not mutate files. Return the exact file, proposed change, safety checks, and verification command.
```

Expected response markers are:

- `workflow_router.plan completed`
- `run_id: workflow-router-...`
- `selected_workflow`
- `execution_planning.plan`
- `small_text_edit_proposal`
- `downstream_implementation_workflow_report`
- `Artifacts:`

That proves the natural-language route can create a draft packet through the existing implementation workflow. It should not mutate the frozen fixture; the drafted file lives under the controller artifact directory.

Optional small unit-test draft L1 check:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, add a small unit test for sync_exchange_order_id_for_placed_order setting exchange_order_id when it is missing. Draft only. Show the proposed test file and verification command before applying.
```

Expected response markers are:

- `workflow_router.plan completed`
- `run_id: workflow-router-...`
- `selected_workflow`
- `execution_planning.plan`
- `small_unit_test_proposal`
- `downstream_implementation_workflow_report`
- `Artifacts:`

That proves the natural-language route can draft a small pytest addition through the existing implementation workflow. It should not mutate the frozen fixture; the proposed test file and draft output live under the controller artifact directory.

Optional config-default test draft check:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, draft a small unit test in tests/test_lot_tracking_integration.py proving config default DEFAULT_PROFIT_MARGIN_PCT in business/lot_config.py defaults to 0.5. Draft only. Show the proposed test file, safety checks, and verification command before applying. Do not mutate files.
```

Optional exact error-message test draft check:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, draft a small unit test in tests/unit/test_orderbook_v2.py asserting exact error message "OrderBook is read-only; refusing upsert_order()" from core/orderbook.py. Draft only. Show the proposed test file, safety checks, and verification command before applying. Do not mutate files.
```

Optional test-assertion update draft check:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, draft an update to tests/unit/test_order_id_and_followup_rules.py changing assertion 'assert call_kwargs["reveal_pricing_policy"] == "top_of_book"' to 'assert call_kwargs["reveal_pricing_policy"] == "top_of_book"  # inherited from root parent'. Draft only. Show exact operation, safety checks, and verification command before applying. Do not mutate files.
```

Expected response markers for the three D1 draft checks are:

- `workflow_router.plan completed`
- `execution_planning.plan`
- `small_unit_test_proposal`
- `downstream_implementation_workflow_report`
- `Draft proposal:`
- `Source mutation: false`

These prove the natural-language route can draft exact test proposals without creating a second edit runtime. The frozen fixture should remain unchanged; the proposal lives under the controller artifact directory.

Optional disposable-copy apply boundary check:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, approved disposable copy apply only. Apply these exact packet_operations to a disposable copy and do not mutate the source repo: {"packet_operations":[{"kind":"replace_text","path":"docs/agents/INVARIANTS.md","old":"- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\n  maps, dashboard references, follow-up claims, fill ledger ownership, and DB\n  local rows.","new":"- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\n  maps, dashboard references, follow-up claims, fill ledger ownership, DB\n  local rows, and stealth manager placed-order index keys."}]}
```

Expected response markers are:

- `workflow_router.plan completed`
- `downstream_workflow: implementation.workflow`
- `source_changed: False`
- `disposable_copy_changed: True`

That proves the natural-language route can apply through the existing implementation workflow on a copied repository, record mutation proof, roll the copy back, and keep the protected frozen source unchanged.

Optional simple failing-test fix L1 check:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, inspect this failing test and propose the smallest fix. Draft only; do not apply until approved.
FAILED tests/unit/test_order_id_and_followup_rules.py::test_find_stealth_order_by_placed_order_id_uses_client_order_id_index - AssertionError: expected find_stealth_order_by_placed_order_id docstring to mention client_order_id
```

Expected response markers are:

- `workflow_router.plan completed`
- `run_id: workflow-router-...`
- `selected_workflow`
- `execution_planning.plan`
- `simple_test_fix_proposal`
- `downstream_implementation_workflow_report`
- `Artifacts:`

That proves the natural-language route can draft an exact simple-fix packet through the existing implementation workflow. It should not mutate the frozen fixture; the drafted source file lives under the controller artifact directory.

The broad refactor prompt is intentionally deferred to advanced-stage validation. First-time testing should stay on these smaller L1 prompts.

Optional Phase 31 read-only L1 checks:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, identify test coverage gaps for placed_order_id stealth lookup. Read only. Return covered tests, uncovered source files, verification commands, and gaps.
```

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find documentation for request_stealth_orders dashboard behavior. Read only. Return documentation files, source refs, and gaps.
```

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, locate the CLI/script entrypoint main.py for running the trading engine. Read only. Return entrypoint files, command, and source refs.
```

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, explain the runtime effect of COINBASE_API_KEY in configuration.py. Read only. Return references, effect, and source refs.
```

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp, find recent or local changes. Read only. Return git status, recent commits, changed files, and unsupported gaps.
```

Expected behavior:

- each prompt returns chat-visible `Answer:` content through `workflow_router.plan`
- the git-enabled fixture returns `local_change_summary.status=ready`
- the non-git fixture returns `local_change_summary.status=limited_non_git` instead of invented commit history

## 4. Run The V1 Acceptance Command

This is the shortest automated founder acceptance check for the full `v1.1-release-candidate` profile. It verifies health for `8000`, `8300`, `8500`, `8400`, and role ports; proves AnythingLLM responds through the workflow-router gateway; runs setup doctor, docs-index, release-channel, security policy, representative L1 read-only, L1 draft-only, L2 read-only, task-decomposition, controlled disposable-copy apply, chat-visible `format_a` checks, external tester onboarding, the expanded founder field suite, the profiled skill-library release gate, observability, and model-probe checks; verifies JSON output selection; records feedback; and writes a report artifact.

Run from Bash:

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/validate_v1_acceptance.py \
  --profile v1.1-release-candidate \
  --candidate-model-base-url http://127.0.0.1:8000/v1 \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --controller-base-url http://127.0.0.1:8400 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --timeout-seconds 900 \
  --command-timeout-seconds 3600
```

Expected final markers:

```text
V1 ACCEPTANCE REPORT ...
V1 ACCEPTANCE SUMMARY ...
V1 ACCEPTANCE PASS
```

Report artifacts are written under `runtime-state/v1-acceptance/`.

The V1.1 gate also writes founder field suite reports under `runtime-state/founder-field-tests/`, skill-library release reports under `runtime-state/skill-release-gates/`, security reports under `runtime-state/security-policy/`, and observability reports under `runtime-state/run-observability/`. The V1.1 report includes `profile`, `profile_contract`, `first_time_user_doctor`, `docs_index`, `release_channels`, `security_policy`, `founder_field_summary`, `skill_library_health`, `model_portability`, `observability`, `proof_summary`, and `known_limitations`.

When you switch the local stack to a smaller model candidate, run the model portability gate instead of assuming the V1 result still applies:

```bash
python3 scripts/validate_model_portability.py \
  --candidate-id smaller-local-candidate \
  --candidate-description "Smaller local model candidate behind localhost:8000" \
  --candidate-model-base-url http://127.0.0.1:8000/v1 \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --controller-base-url http://127.0.0.1:8400 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --timeout-seconds 900 \
  --command-timeout-seconds 3600
```

The portability report classifies misses as `harness`, `classifier`, `prompt`, `model_quality`, or `unknown`. See [README.model-portability.md](README.model-portability.md).

Compare a new run to a prior run without rerunning localhost validation:

```bash
python3 scripts/diff_run_artifacts.py \
  --left-report runtime-state/v1-acceptance/phase71-v1-acceptance.json \
  --right-report runtime-state/v1-acceptance/phase72-model-portability-v1.json \
  --left-label prior \
  --right-label candidate
```

See [README.run-artifact-diff.md](README.run-artifact-diff.md).

Validate fixture setup and cleanup before adding another test repository:

```bash
python3 scripts/manage_fixtures.py setup \
  --fixture-id python-service-generalization \
  --run-id getting-started-smoke \
  --cleanup-after
```

See [README.fixture-manager.md](README.fixture-manager.md).

The founder field prompt inventory is governed by `runtime/prompt_catalogs/founder_field_v1.json`. To check the catalog without a live model run:

```bash
python3 scripts/validate_prompt_catalog.py
```

Inspect the latest workflow-router run without opening artifact folders:

```bash
python3 scripts/inspect_latest_run.py \
  --controller-output-root /mnt/c/private_agentic_agents/runtime-state/controller-artifacts \
  --workflow workflow_router.plan
```

## 5. Run The L1 Product Suite Validator

The UI message above proves one chat. The validator below runs the current L1 and D1 prompt suites through the Bash workflow-router gateway and AnythingLLM against both frozen repos. It verifies route selection, downstream status, expected artifacts, chat-visible `Answer:` or `Draft proposal:` content, no-source-mutation markers, watched file hashes, and git status.

Run from Bash:

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/validate_workflow_router_l1_suite.py \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --timeout-seconds 900
```

Expected final markers include:

```text
L1 SUITE GATEWAY PASS
L1 SUITE ANYTHINGLLM PASS
L1 SUITE SUMMARY
```

## 6. Run The L2 Product Suite Validator

Run this after the L1 suite passes. The current L2 suite covers failing-test diagnosis, multi-file behavior investigation, dependency impact summary, test selection with rationale, runtime-error diagnosis, request/data-flow mapping, code-path comparison, and change-surface summary: root cause or beginning point, impacted or participating files, observed runtime errors, flow steps, candidate paths, implementation stop status, verification fields, risks when applicable, gaps, and read-only mutation proof.

Optional test-selection L2 check:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, choose the smallest, medium, and broad validation commands for placed_order_id stealth lookup. Read only. Explain why each command is relevant, what risk it covers, and what gaps remain.
```

Expected response markers:

- `workflow_router.plan completed`
- `code_investigation.plan`
- `downstream_test_selection_plan`
- `Smallest command:`
- `Medium command:`
- `Broad command:`
- `Rationale:`
- `Covered risks:`
- `Source mutation: false`

Run from Bash:

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/validate_workflow_router_l2_suite.py \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --timeout-seconds 900
```

Expected final markers include:

```text
L2 SUITE GATEWAY PASS
L2 SUITE ANYTHINGLLM PASS
L2 SUITE SUMMARY
```

## 7. Inspect Results

Artifacts are written under:

```text
C:\private_agentic_agents\runtime-state\controller-artifacts
```

The chat response lists the artifact names for the current `run_id`. For first-time review, use the `run_id` shown in chat and open the matching controller artifact directory.

For a `workflow-router-...` run, start with:

```text
workflow-router/<run-id>/route-decision.json
workflow-router/<run-id>/run-state.json
```

When implementation prep runs, nested execution-planning artifacts include:

```text
context-results.json
context-results-for-model.json
implementation-workflow-report.json
```

`context-results.json` is the full evidence artifact. `context-results-for-model.json` is the compact model-facing artifact used to keep local-model skill calls reliable.

To classify failures from existing validation reports without rerunning localhost services:

```bash
cd /mnt/c/agentic_agents
python3 scripts/report_failure_taxonomy.py \
  --report runtime-state/v1-acceptance/phase72-model-portability-v1.json \
  --label phase72-v1 \
  --report runtime-state/model-portability/phase72-live-current.json \
  --label phase72-portability
```

Expected markers:

```text
FAILURE TAXONOMY REPORT ...
FAILURE TAXONOMY SUMMARY ...
FAILURE TAXONOMY PASS
```

The Markdown output is the quick review surface. Start with `summary.highest_severity`, `summary.category_counts`, and `findings[].recommended_next_action`.

## Troubleshooting

- If AnythingLLM returns normal chat instead of `workflow_router.plan completed`, it is probably pointed at `8300/v1` instead of `8500/v1`.
- If AnythingLLM reports `400 Streaming workflow-router chat responses are not supported yet`, restart the local harness; current workflow-router chat supports AnythingLLM-style `stream: true` requests on `8500/v1`.
- If the controller rejects `target_root`, restart the stack with the `CONTROLLER_ALLOWED_TARGET_ROOTS` command above.
- If Windows clients receive headers but time out waiting for the response body, run the validator from Bash.
- If `8000/v1/models` is not healthy, start or fix the vLLM server before testing the harness.
- If an old AnythingLLM thread behaves inconsistently, start a fresh thread; long chat history can consume the gateway input budget.
- If a founder prompt misses the target but Phase 161 still reports `no_new_batch_justified`, treat it as prompt wording or documentation feedback first. Do not create a new skill/tool unless a later governed report produces `decision=propose_batch_for_founder_approval`.

## Deeper Recipes

- [L1 Coding Agent Prompt Backlog](docs/L1_CODING_AGENT_PROMPTS.md)
- [Founder Field Tests](README.founder-field-tests.md)
- [Founder Field Round 1](README.founder-field-round1.md)
- [Skill/Tool Gap Batch Proposal](README.skill-tool-gap-batch-proposal.md)
- [AnythingLLM Founder Testing Examples](docs/examples/anythingllm-founder-testing.md)
- [Workflow Router README](README.workflow-router.md)
- [Actionable Workflow Roadmap](docs/ACTIONABLE_WORKFLOW_ROADMAP.md)
