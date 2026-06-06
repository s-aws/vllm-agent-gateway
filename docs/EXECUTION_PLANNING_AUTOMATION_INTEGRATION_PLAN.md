# Execution Planning Automation Integration Plan

Status: support and validation-history reference.

This is no longer the product roadmap. Use [Actionable Workflow Roadmap](ACTIONABLE_WORKFLOW_ROADMAP.md) for the current destination and implementation order. This document is useful only for the older execution-planning integration details, live-validation history, and existing gateway/controller proof.

This document records the older execution-planning integration approach across the controller service, AnythingLLM automation, and the current gateway.

The blunt gap: direct `localhost:8000` validation is necessary, but it is not enough. A product claim is not credible until the same skill loop works through the runtime path the founder/tester actually uses, against a real repository, with artifacts and non-mutation proof.

## Current Surfaces

- Direct model endpoint: `http://127.0.0.1:8000/v1`
- Gateway: `http://127.0.0.1:8300`
- Controller service: `http://127.0.0.1:8400`
- Controller harness adapter: `POST /v1/controller/harness/chat/completions`
- Existing implementation workflow: `implementation.workflow`
- Real-world validation repository: `C:\coinbase_testing_repo_frozen_tmp`
- Git-enabled real-world validation repository: `C:\coinbase_testing_repo_frozen_tmp.github`
- Current planning skills: `.qwen/skills/request-triage` through `.qwen/skills/feedback-capture`

Current local probe status recorded during this planning pass:

- Direct Windows client to `http://127.0.0.1:8000/v1/models`: responded with `Qwen3-Coder-30B-A3B-Instruct`.
- Bash-side gateway client to `http://127.0.0.1:8300/v1/models`: responded with `Qwen3-Coder-30B-A3B-Instruct`.
- Bash-side gateway client to `POST http://127.0.0.1:8300/v1/chat/completions`: responded with `gateway-ok`.
- Bash-side role proxy client to `http://127.0.0.1:8205/v1/models`: responded with the model list.
- Bash-side controller client to `http://127.0.0.1:8400/health`: responded and listed `/mnt/c/agentic_agents`, `/mnt/c/coinbase_testing_repo_frozen_tmp`, and `/mnt/c/coinbase_testing_repo_frozen_tmp.github` as allowed roots.
- Windows-side gateway client to `http://<wsl-ip>:8300/v1` passed the full nine-skill validator with frozen repo proof.
- Windows-side controller harness client to `http://<wsl-ip>:8400/v1/controller/harness/chat/completions` completed a frozen-repo documenter dry run with bounded artifacts.
- Windows-side controller harness client to `http://<wsl-ip>:8400/v1/controller/harness/chat/completions` rejected natural-language chat without an explicit envelope using `missing_controller_envelope`.
- Bash-side controller harness adapter request against `/mnt/c/coinbase_testing_repo_frozen_tmp` with `document_scope: "all"` completed in dry-run mode and returned bounded artifacts.
- Bash-side controller harness adapter rejected natural-language chat without an explicit envelope with `missing_controller_envelope`.
- Direct Windows clients to Bash-hosted `127.0.0.1:8300`, `127.0.0.1:8205`, and `127.0.0.1:8400` received response headers but timed out waiting for body bytes. Using the WSL/network IP with gateway and controller bound to `0.0.0.0` returns response bodies correctly.
- AnythingLLM is running on `http://127.0.0.1:3001`; `/api/ping` responds.
- `ANYTHINGLLM_API_KEY` is available in the Windows process and user environment, and can be passed into Bash with `WSLENV=ANYTHINGLLM_API_KEY`.
- Bash-side authenticated `GET http://127.0.0.1:3001/api/v1/workspaces` returned workspace slugs including `my-workspace`, `assistant-chats`, and `codegraphcontext`.
- Bash-side authenticated chat against `my-workspace` returned `anythingllm-ok` for a minimal prompt.
- Bash-side authenticated AnythingLLM `request-triage` skill smoke returned parseable JSON for a clear read-only request and an unsafe skip-approval request. The unsafe case preserved `requires_user_approval_before_write: true`.
- Bash-side authenticated full nine-skill AnythingLLM chain against `/mnt/c/coinbase_testing_repo_frozen_tmp` completed, produced a draft packet preview, passed that preview to `implementation.workflow` in draft mode, and preserved selected frozen file hashes.
- Bash-side authenticated AnythingLLM controller-envelope probe against `my-workspace` returned normal model-generated planning text instead of controller output. It did not return `agentic_controller_response`, `run_id`, or bounded artifact paths. This proves the workspace is reachable, but it is not currently configured to route explicit controller envelopes to the controller harness endpoint.
- Bash-side live `execution_planning.plan` direct controller dry run against `/mnt/c/coinbase_testing_repo_frozen_tmp` completed, wrote bounded artifacts, produced controller-discovered verification commands after non-Git fallback lookup, and preserved selected file hashes. Run ID: `execution-planning-20260603T204052259357Z`.
- Bash-side live `execution_planning.plan` direct controller dry run against `/mnt/c/coinbase_testing_repo_frozen_tmp.github` completed through Git-backed lookup, wrote bounded artifacts, produced targeted pytest commands, and preserved selected file hashes. Run ID: `execution-planning-20260603T204845433999Z`.
- Regression mutation testing now applies an approved packet to disposable copies of both frozen fixtures through the existing `implementation.workflow` apply path, verifies the copy changed, verifies before/after hashes differ, and verifies the original private/untracked fixtures remain unchanged.
- The live AnythingLLM provider setting was corrected to `http://127.0.0.1:8300/v1` using the authenticated AnythingLLM system API. `8400` remains the controller service, not the OpenAI-compatible workspace base URL.
- Bash-side direct gateway validation through `http://127.0.0.1:8300/v1/chat/completions` and the no-`/v1` `/chat/completions` alias routed explicit `agentic_controller_request` envelopes to the controller harness for both frozen fixtures and preserved the selected file hash. Run IDs: `execution-planning-20260603T213855593613Z` for `/mnt/c/coinbase_testing_repo_frozen_tmp`; `execution-planning-20260603T213933241161Z` for `/mnt/c/coinbase_testing_repo_frozen_tmp.github`.
- Bash-side AnythingLLM workspace validation through `my-workspace` and gateway `8300` routed explicit `execution_planning.plan` envelopes to the controller harness for both frozen fixtures and returned controller markers. Run IDs: `execution-planning-20260603T213958248725Z` for `/mnt/c/coinbase_testing_repo_frozen_tmp`; `execution-planning-20260603T214035731989Z` for `/mnt/c/coinbase_testing_repo_frozen_tmp.github`.
- Repeated AnythingLLM dry-run testing exposed a real workspace-history issue: older user messages containing controller envelopes caused `multiple_controller_envelopes`. The shared envelope selector now uses the latest message-content envelope as the active request while still rejecting top-level plus message ambiguity and multiple envelopes in one active message. Covered by gateway and controller regression.
- Repeated AnythingLLM dry-run testing also exposed a local-model reliability issue: one `impact-map-builder` response returned malformed JSON. The controller now retries invalid skill JSON once with a stricter prompt, and the retry counts against `max_model_calls`. Covered by controller regression.
- Bash-side live dry-run matrix validation passed through `scripts/validate_live_execution_planning_matrix.py --mode dry_run --timeout-seconds 900`. It covered `8000`, `8300`, `8400`, role ports `8101`, `8102`, `8201`, `8202`, `8203`, `8204`, `8205`, AnythingLLM provider setting `http://127.0.0.1:8300/v1`, direct gateway dry runs, AnythingLLM dry runs, `code_context.lookup` direct-controller/direct-gateway/AnythingLLM routes, `code_investigation.plan` direct-controller/direct-gateway/AnythingLLM routes, `refactor.single_path` direct-controller/direct-gateway/AnythingLLM routes, and Bash-side mutation probes on disposable copies of both frozen fixtures. Direct gateway run IDs: `execution-planning-20260604T030702284086Z` for `/mnt/c/coinbase_testing_repo_frozen_tmp`; `execution-planning-20260604T030809564273Z` for `/mnt/c/coinbase_testing_repo_frozen_tmp.github`. AnythingLLM run IDs: `execution-planning-20260604T030848165194Z` for `/mnt/c/coinbase_testing_repo_frozen_tmp`; `execution-planning-20260604T030955310073Z` for `/mnt/c/coinbase_testing_repo_frozen_tmp.github`.
- Bash-side live `code_context.lookup` validation passed through the direct controller endpoint, direct gateway controller-envelope route, and AnythingLLM workspace route for `/mnt/c/agentic_agents`. Run IDs: direct controller `code-context-20260603T224505065415Z`; direct gateway `code-context-20260603T224505097535Z`; AnythingLLM `code-context-20260603T224530951234Z`.
- Bash-side live `code_context.lookup` validation passed through the direct controller endpoint, direct gateway controller-envelope route, and AnythingLLM workspace route for `/mnt/c/coinbase_testing_repo_frozen_tmp` and `/mnt/c/coinbase_testing_repo_frozen_tmp.github`. Selected frozen fixture hashes remained unchanged. Frozen fixture AnythingLLM run IDs from the latest matrix run: `code-context-20260604T031055806259Z` for `/mnt/c/coinbase_testing_repo_frozen_tmp`; `code-context-20260604T031100481704Z` for `/mnt/c/coinbase_testing_repo_frozen_tmp.github`.
- Bash-side live `code_investigation.plan` validation passed through the direct controller endpoint, direct gateway controller-envelope route, and AnythingLLM workspace route for `/mnt/c/coinbase_testing_repo_frozen_tmp` and `/mnt/c/coinbase_testing_repo_frozen_tmp.github`. Selected frozen fixture hashes remained unchanged. The payload resolves `core/stealth_order_manager.py`, reports possible multiple-path risk, and lists source/test packet seed files with the hinted entrypoint first. Frozen fixture AnythingLLM run IDs from the latest matrix run: `code-investigation-20260604T031144214534Z` for `/mnt/c/coinbase_testing_repo_frozen_tmp`; `code-investigation-20260604T031156516012Z` for `/mnt/c/coinbase_testing_repo_frozen_tmp.github`.
- Bash-side live `refactor.single_path` investigation-only validation passed through the direct controller endpoint, direct gateway controller-envelope route, and AnythingLLM workspace route for `/mnt/c/coinbase_testing_repo_frozen_tmp` and `/mnt/c/coinbase_testing_repo_frozen_tmp.github`. Frozen fixture AnythingLLM run IDs from the latest matrix run: `refactor-single-path-20260604T031238337959Z` for `/mnt/c/coinbase_testing_repo_frozen_tmp`; `refactor-single-path-20260604T031252572616Z` for `/mnt/c/coinbase_testing_repo_frozen_tmp.github`.
- Bash-side live `refactor.single_path` dry-run validation passed through AnythingLLM for `/mnt/c/coinbase_testing_repo_frozen_tmp`, delegated to `execution_planning.plan`, produced `execution_planning_packet_preview` and `execution_planning_implementation_workflow_report`, and preserved the selected frozen file hash. Run ID: `refactor-single-path-20260604T031630444286Z`.
- `workflow_feedback.record` is implemented as a controller-owned, no-model, no-repo-mutation feedback recorder. Regression verifies direct endpoint persistence, linkage to existing controller run records, latest-envelope harness routing, and rejection of missing or empty feedback. Bash-side live validation passed through direct controller, direct gateway, and AnythingLLM for both frozen repo fixtures. AnythingLLM feedback run IDs: `workflow-feedback-20260604T033609714600Z` for `/mnt/c/coinbase_testing_repo_frozen_tmp`; `workflow-feedback-20260604T033609784379Z` for `/mnt/c/coinbase_testing_repo_frozen_tmp.github`.
- The first curated `codegraph_context` relationship adapter is implemented behind `code_context.lookup` only. It accepts explicit `relationship_queries` for callers, callees, and imports, writes `relationship-results.json`, and keeps raw CodeGraphContext/Cypher/MCP operations rejected. Regression covers the controller endpoint and the generic tool mediator path. Bash-side live validation passed through direct controller, direct gateway, and AnythingLLM for both frozen repo fixtures. AnythingLLM relationship run IDs: `code-context-20260604T050638774145Z` for `/mnt/c/coinbase_testing_repo_frozen_tmp`; `code-context-20260604T050649650668Z` for `/mnt/c/coinbase_testing_repo_frozen_tmp.github`.

Therefore, gateway and controller harness validation is proven from Bash and from Windows over the WSL/network URL. AnythingLLM API access, single-skill smoke testing, full nine-skill skill-chain execution, direct gateway controller routing, AnythingLLM controller-envelope routing through `8300`, dry-run packet preview generation, disposable-copy mutation proof, the first deterministic `code_context.lookup` slice, the first deterministic `code_investigation.plan` slice, and the first `refactor.single_path` orchestration slice are proven against the frozen repo fixtures. Later Phase 71 work added a browser-rendered AnythingLLM Desktop UI validator at `scripts/validate_anythingllm_ui_e2e.py`; the remaining product gap is no longer this route, but follow-on hardening such as model portability, run diffing, fixture management, failure taxonomy, and packaging strategy in the canonical roadmap.

## Investigation Plan

1. Inventory the current runtime path.
   - Confirm which process owns `8300`, role prompt proxy ports, and `8400`.
   - Confirm the current gateway can proxy `/v1/models` and `/v1/chat/completions` to `localhost:8000`.
   - Confirm the controller service starts with `C:\agentic_agents`, `C:\coinbase_testing_repo_frozen_tmp`, and `C:\coinbase_testing_repo_frozen_tmp.github` in `CONTROLLER_ALLOWED_TARGET_ROOTS`.
   - Confirm AnythingLLM can send either top-level JSON fields or a JSON string envelope in a chat message.

2. Define the controller contract before implementation.
   - Proposed workflow name: `execution_planning.plan`
   - Required envelope fields:

     ```json
     {
       "workflow": "execution_planning.plan",
       "target_root": "C:/coinbase_testing_repo_frozen_tmp",
       "user_request": "Investigate whether StealthOrderManager client_order_id lookup has one code path before refactor.",
       "mode": "dry_run",
       "skill_chain": [
         "request-triage",
         "scope-and-assumptions",
         "entrypoint-finder",
         "context-plan-builder",
         "impact-map-builder",
         "execution-plan-writer",
         "implementation-packet-designer",
         "verification-planner",
         "feedback-capture"
       ],
       "budgets": {
         "max_context_requests": 5,
         "max_files": 10,
         "max_model_calls": 12
       }
     }
     ```

   - Ordinary chat text must not trigger this workflow.
   - The controller owns context gathering, target-root checks, skill sequencing, artifact writing, and implementation workflow calls.
   - The model receives bounded skill instructions and bounded context only.

3. Decide how skills are supplied to the model.
   - Direct localhost validation can read `.qwen/skills/<name>/SKILL.md`.
   - Controller integration should load project-local skill files by name from an allowlisted skill root.
   - AnythingLLM should not need the user to say "use request-triage"; an explicit `execution_planning.plan` workflow request should select the skill chain deterministically.
   - Natural-language AnythingLLM chat without the explicit controller envelope should remain normal chat or be rejected by the controller harness adapter.

4. Map deterministic context sources.
   - Use structure indexes and bounded grep/read-file first.
   - Do not expose raw CodeGraphContext MCP operations to the model.
   - Add a curated `code_context.lookup` workflow only after the execution-planning path proves the need. The first deterministic `code_context.lookup` slice is implemented with structure index, bounded exact-text lookup, and explicit file snippets.
   - Treat unavailable CodeGraphContext state as a warning or missing evidence, not as hidden fallback behavior.

5. Define artifacts before implementation.
   - `request-triage.json`
   - `scope-and-assumptions.json`
   - `entrypoint-finder.json`
   - `context-plan.json`
   - `impact-map.json`
   - `execution-plan.json`
   - `implementation-packet-candidates.json`
   - `verification-plan.json`
   - `feedback-record.json`
   - compact harness response with artifact paths and summary only

## Implementation Plan

Phase 0: Finish and validate the final skills product.

- Create all nine endpoint skills.
- Run static validation for all nine skills.
- Run clear, ambiguous, and unsafe live smoke cases against `http://127.0.0.1:8000/v1`.
- Run the approval-to-verification-to-feedback dry chain.
- Run the frozen Coinbase repo dry chain with `--real-target-root C:\coinbase_testing_repo_frozen_tmp`.
- Run mutation testing on disposable copies of both frozen fixtures through `implementation.workflow` apply mode. Do not mutate the source fixtures.

Phase 1: Add controller workflow design.

- Create the `execution_planning.plan` request/result schema. Done in [Execution Planning Controller Workflow Schema](EXECUTION_PLANNING_CONTROLLER_WORKFLOW_SCHEMA.md).
- Define allowed modes: `investigation_only`, `implementation_prep`, and `dry_run`. Done in the schema.
- Define output artifact names and compact response shape. Done in the schema.
- Define target-root and skill-root allowlist rules. Done in the schema.
- Define explicit refusal cases for missing target root, unsupported mode, missing skill, raw CodeGraphContext, missing packet operations, and apply-mode request. Done in the schema.
- Create pasteable harness examples for founder/testing. Done in [Execution Planning Harness Examples](examples/execution-planning-harness.md).

Phase 2: Implement controller-owned skill orchestration after schema approval.

- Load skill text from `.qwen/skills`. Implemented.
- Call the configured role/model endpoint with one skill and one bounded input at a time. Implemented.
- Validate required JSON keys after every model call. Implemented.
- Stop on missing evidence instead of filling gaps with model guesses. Implemented through required JSON validation and controller refusal cases.
- Retry malformed skill JSON once with a stricter prompt, counting the retry against `max_model_calls`. Implemented and covered by regression after live AnythingLLM dry-run testing exposed malformed JSON from `impact-map-builder`.
- Write each skill output as an artifact. Implemented.
- Pass approved packet previews to `implementation.workflow` in `draft` mode only. Implemented.
- Use [Execution Planning Controller Workflow Schema](EXECUTION_PLANNING_CONTROLLER_WORKFLOW_SCHEMA.md) as the implementation contract. Implemented.

Phase 3: Wire the controller harness adapter.

- Accept `execution_planning.plan` inside `agentic_controller_request`. Implemented and covered by regression.
- Return an OpenAI-style assistant message plus `agentic_controller_response`. Implemented and covered by regression.
- Reject ordinary AnythingLLM chat without an explicit envelope. Implemented and covered by regression.
- Keep full artifacts on disk. Implemented.

Phase 4: Add current gateway coverage.

- Test direct gateway health and model forwarding. Done from Bash-side client.
- Test role prompt proxy forwarding to the gateway. Done from Bash-side client.
- Test Windows-side gateway model and chat forwarding through the WSL/network URL. Done.
- Test that oversized skill prompts are rejected or clamped by budget policy instead of silently truncated.
- Test that controller harness traffic is not accidentally routed through a normal role port. Natural-language harness requests are rejected by the controller adapter.
- Use the WSL/network URL for Windows-hosted clients until direct `127.0.0.1` response-body behavior is fixed.

Phase 5: Add AnythingLLM automation coverage.

- Reusable AnythingLLM API full-chain validator exists at `scripts/validate_anythingllm_execution_planning_skills.py`.
- Keep AnythingLLM pointed at the OpenAI-compatible gateway base URL, preferably `http://127.0.0.1:8300/v1`. The gateway also accepts `http://127.0.0.1:8300` clients that call `/chat/completions`.
- Add explicit-envelope controller routing to the gateway so controller requests on `/v1/chat/completions` forward to `http://127.0.0.1:8400/v1/controller/harness/chat/completions`. Implemented and covered by regression.
- Create a saved AnythingLLM request or automation recipe that sends the explicit controller envelope. Reusable validators now exist at `scripts/validate_gateway_controller_route.py` and `scripts/validate_live_execution_planning_matrix.py`; a saved AnythingLLM UI artifact remains optional hardening.
- Run the same frozen Coinbase repo request through AnythingLLM via `8300`. Done for both `/mnt/c/coinbase_testing_repo_frozen_tmp` and `/mnt/c/coinbase_testing_repo_frozen_tmp.github`.
- Confirm response contains artifact paths, status, and feedback prompt. Done through direct gateway structured response checks; the AnythingLLM route validator checks controller markers, run IDs, and artifact markers in the workspace response text.
- Confirm no target repository mutation. Done for selected validation file hashes in routed gateway/AnythingLLM validators, and done for apply behavior through the live matrix mutation probe against disposable copies of both frozen fixtures.
- Capture logs or request/response artifacts for review. Done through controller run artifacts and run-state records under the controller artifact output root.

## Test Matrix

| Path | Target | Required proof |
| --- | --- | --- |
| Direct model | `http://127.0.0.1:8000/v1` | all nine static checks, 27 live smoke cases, synthetic chain, feedback chain |
| Frozen repo copied tree | `C:\coinbase_testing_repo_frozen_tmp` | real bounded context with non-Git fallback lookup, draft packet preview, selected-file hash unchanged |
| Frozen repo Git worktree | `C:\coinbase_testing_repo_frozen_tmp.github` | Git-backed bounded context, draft packet preview, selected-file hash unchanged |
| Implementation workflow | local Python API | model-produced packet preview accepted in `draft` mode |
| Mutation testing | disposable copies of both frozen fixtures | existing `implementation.workflow` apply path mutates only the disposable copy; original fixture text and hashes remain unchanged; covered by regression and Bash-side live matrix probe |
| Gateway | `http://127.0.0.1:8300` | health, `/v1/models`, `/v1/chat/completions`, budget behavior |
| Gateway controller route | `http://127.0.0.1:8300/v1/chat/completions` and `/chat/completions` alias | explicit `agentic_controller_request` envelope routes to the controller harness and never falls through to normal model chat; covered by regression and live Bash dry-run validation against both frozen fixtures |
| Role prompt proxy | role ports from `runtime/roles.json`: `8101`, `8102`, `8201`, `8202`, `8203`, `8204`, `8205` | prompt injection plus gateway forwarding works for bounded skill prompt |
| Controller service | `http://127.0.0.1:8400` | health, explicit envelope accepted, missing envelope rejected, execution planning endpoint completes |
| Controller harness adapter | `/v1/controller/harness/chat/completions` | OpenAI-style request with `agentic_controller_request` returns bounded artifacts |
| Code context lookup | `code_context.lookup` | direct controller, direct gateway, and AnythingLLM requests return bounded read-only lookup artifacts; curated `relationship_queries` return `relationship_results`; raw CodeGraphContext terms are rejected; live matrix covers both frozen fixtures |
| Code investigation plan | `code_investigation.plan` | direct controller, direct gateway, and AnythingLLM requests return bounded read-only investigation artifacts; raw CodeGraphContext terms are rejected |
| Refactor single path | `refactor.single_path` | investigation-only requests route through direct controller, direct gateway, and AnythingLLM; approved dry-run delegates to `execution_planning.plan` and draft `implementation.workflow` artifacts without mutation |
| Workflow feedback | `workflow_feedback.record` | direct controller, direct gateway, and AnythingLLM requests record bounded feedback artifacts linked to prior refactor run IDs without mutating either frozen fixture |
| AnythingLLM | founder/tester harness | full nine-skill chain works; explicit controller-envelope dry runs through gateway `8300` reach the controller and return controller markers for both frozen fixtures, even with prior envelope history in the workspace |
| Regression suite | `pytest tests/regression/ -v` | required for non-agent script/controller changes |

## Immediate Test Commands

Direct final skills validation:

```powershell
python scripts\validate_execution_planning_skills.py --base-url http://127.0.0.1:8000/v1
```

Direct final skills validation plus frozen Coinbase repo chain:

```powershell
python scripts\validate_execution_planning_skills.py --base-url http://127.0.0.1:8000/v1 --real-target-root C:\coinbase_testing_repo_frozen_tmp
```

Regression includes the Git-enabled frozen fixture when present:

```powershell
pytest tests\regression\test_controller_service.py::test_execution_planning_runs_against_git_enabled_frozen_coinbase_fixture -v
```

Mutation regression against disposable copies of both frozen fixtures:

```powershell
pytest tests\regression\test_implementation_workflow.py::test_frozen_coinbase_fixture_packet_mutation_on_disposable_copy -v
```

AnythingLLM full-chain frozen repo validation from Bash:

```powershell
$env:WSLENV='ANYTHINGLLM_API_KEY'
bash -lc "cd /mnt/c/agentic_agents && python3 scripts/validate_anythingllm_execution_planning_skills.py --target-root /mnt/c/coinbase_testing_repo_frozen_tmp --workspace my-workspace --timeout-seconds 420"
```

Full live runtime matrix from Bash:

```powershell
$env:WSLENV='ANYTHINGLLM_API_KEY'
bash -lc "cd /mnt/c/agentic_agents && PYTHONUNBUFFERED=1 python3 scripts/validate_live_execution_planning_matrix.py --mode dry_run --timeout-seconds 900"
```

Code context lookup through the direct controller endpoint:

```powershell
bash -lc "cd /mnt/c/agentic_agents && curl -s http://127.0.0.1:8400/v1/controller/code-context/lookups -H 'Content-Type: application/json' -d '{\"workflow\":\"code_context.lookup\",\"schema_version\":1,\"target_root\":\"/mnt/c/agentic_agents\",\"query\":\"select_latest_controller_envelope\",\"paths\":[\"vllm_agent_gateway/controller_envelope.py\"],\"max_results\":25,\"max_files\":5}'"
```

Code investigation plan through the direct controller endpoint:

```powershell
bash -lc "cd /mnt/c/agentic_agents && curl -s http://127.0.0.1:8400/v1/controller/code-investigation/plans -H 'Content-Type: application/json' -d '{\"workflow\":\"code_investigation.plan\",\"schema_version\":1,\"target_root\":\"/mnt/c/coinbase_testing_repo_frozen_tmp\",\"user_request\":\"Investigate whether StealthOrderManager.find_stealth_order_by_placed_order_id has one path before planning a refactor.\",\"behavior\":\"placed_order_id stealth lookup\",\"queries\":[\"find_stealth_order_by_placed_order_id\",\"placed_order_id\"],\"entrypoint_hints\":[{\"path\":\"core/stealth_order_manager.py\",\"symbol\":\"StealthOrderManager.find_stealth_order_by_placed_order_id\",\"reason\":\"Known owner of placed-order lookup behavior.\"}],\"paths\":[\"core/stealth_order_manager.py\",\"tests/unit/test_order_id_and_followup_rules.py\",\"tests/regression/test_order_id_regression.py\"],\"max_results\":50,\"max_files\":10}'"
```

Refactor single-path investigation through the direct controller endpoint:

```powershell
bash -lc "cd /mnt/c/agentic_agents && curl -s http://127.0.0.1:8400/v1/controller/refactor/single-path -H 'Content-Type: application/json' -d '{\"workflow\":\"refactor.single_path\",\"schema_version\":1,\"target_root\":\"/mnt/c/coinbase_testing_repo_frozen_tmp\",\"user_request\":\"Investigate whether StealthOrderManager.find_stealth_order_by_placed_order_id has one path before planning a refactor.\",\"behavior\":\"placed_order_id stealth lookup\",\"queries\":[\"find_stealth_order_by_placed_order_id\",\"placed_order_id\"],\"entrypoint_hints\":[{\"path\":\"core/stealth_order_manager.py\",\"symbol\":\"StealthOrderManager.find_stealth_order_by_placed_order_id\",\"reason\":\"Known owner of placed-order lookup behavior.\"}],\"paths\":[\"core/stealth_order_manager.py\",\"tests/unit/test_order_id_and_followup_rules.py\",\"tests/regression/test_order_id_regression.py\"],\"max_results\":50,\"max_files\":10}'"
```

Gateway probes:

```powershell
@'
import json, urllib.request
for url in ["http://127.0.0.1:8300/health", "http://127.0.0.1:8300/v1/models"]:
    with urllib.request.urlopen(url, timeout=10) as response:
        print(url, response.status, response.read(200).decode("utf-8", errors="replace"))
'@ | python -
```

Controller harness adapter dry-run example:

```powershell
python scripts\run_documenter_service_example.py --target-root . --case harness --max-chunks 1
```

Execution planning controller endpoint example:

```powershell
bash -lc "cd /mnt/c/agentic_agents && curl -s http://127.0.0.1:8400/v1/controller/execution-planning/plans -H 'Content-Type: application/json' --data-binary @<(python3 - <<'PY'
import json
old = '- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\n  maps, dashboard references, follow-up claims, fill ledger ownership, and DB\n  local rows.'
new = '- Use `client_order_id` for internal tracking, parent/child linkage, orderbook\n  maps, dashboard references, follow-up claims, fill ledger ownership, DB\n  local rows, and stealth manager placed-order index keys.'
print(json.dumps({
  'workflow': 'execution_planning.plan',
  'schema_version': 1,
  'target_root': '/mnt/c/coinbase_testing_repo_frozen_tmp',
  'user_request': 'Prepare implementation packet candidates for an approved frozen-repo documentation clarification that client_order_id owns internal lookup paths, including StealthOrderManager placed-order index keys. Use draft mode only and do not mutate the frozen repository.',
  'mode': 'dry_run',
  'approval': {'status': 'approved_for_packet_design', 'scope': 'packet_design_only', 'apply_allowed': False, 'approval_refs': ['founder:approved packet design only for frozen documentation dry run']},
  'context': {'entrypoint_hints': [{'path': 'docs/agents/INVARIANTS.md', 'symbol': None, 'reason': 'Existing validation target for client_order_id invariant clarification.'}], 'allowed_context_tools': ['structure_index', 'git_grep', 'read_file', 'manual']},
  'packet_operations': [{'kind': 'replace_text', 'path': 'docs/agents/INVARIANTS.md', 'old': old, 'new': new}],
  'budgets': {'max_context_requests': 5, 'max_files': 10, 'max_records': 50, 'max_model_calls': 12, 'max_output_tokens': 4600, 'timeout_seconds': 600}
}))
PY
)"
```

For the frozen repo, the controller must be started with both roots allowlisted:

```powershell
python -m vllm_agent_gateway.controller_service.server `
  --config-root C:\agentic_agents `
  --output-root C:\agentic_agents\.tmp\controller-artifacts `
  --host 127.0.0.1 `
  --port 8400 `
  --allowed-target-root C:\agentic_agents `
  --allowed-target-root C:\coinbase_testing_repo_frozen_tmp `
  --allowed-target-root C:\coinbase_testing_repo_frozen_tmp.github
```

The current Bash startup script expects colon-separated roots for Linux. A Windows-safe startup path or script wrapper is a prerequisite before claiming controller-service validation on Windows.

## Open Gaps

- `execution_planning.plan` controller workflow exists, has regression coverage, and has live Bash direct-controller validation against both frozen repo fixtures.
- The schema and harness catalog now reflect the implemented contract, including required `packet_operations` for `implementation_prep` and `dry_run`.
- Phase 71 added the reusable AnythingLLM Desktop UI validator `scripts/validate_anythingllm_ui_e2e.py`. The reusable API route validators remain `scripts/validate_gateway_controller_route.py` and `scripts/validate_live_execution_planning_matrix.py`.
- Bash-side probes proved `8400` serves controller requests and `8300` forwards model and chat requests.
- Windows-side probes proved `http://<wsl-ip>:8300/v1` and `http://<wsl-ip>:8400/v1/controller/harness/chat/completions` work when gateway and controller bind to `0.0.0.0`.
- Direct Windows clients to Bash-hosted `127.0.0.1:8300`, `127.0.0.1:8205`, and `127.0.0.1:8400` received headers but timed out before response bodies. Use `http://<wsl-ip>:...` for Windows-hosted clients until this is fixed.
- AnythingLLM `/api/ping`, authenticated workspace listing, minimal chat, and `request-triage` skill smoke tests work through the Bash-side API path.
- Full nine-skill AnythingLLM chain validation is captured through `scripts/validate_anythingllm_execution_planning_skills.py`.
- Controller-owned AnythingLLM dry-run route validation now passes through `8300` for both frozen fixtures, including repeated validation in a workspace that already contains older controller-envelope messages. The earlier failed controller-envelope probe remains useful history because it showed why AnythingLLM must target the gateway, not the controller service directly.
- Gateway-to-controller routing is implemented, regression-covered, and live-validated through direct gateway requests and AnythingLLM. See [Gateway Controller Routing Plan](GATEWAY_CONTROLLER_ROUTING_PLAN.md).
- Mutation testing exists as regression coverage and as a Bash-side live matrix probe. Both use the existing `implementation.workflow` apply path on disposable fixture copies and verify the source fixtures remain unchanged.
- The current startup script is Bash/Linux-oriented and uses colon-separated allowlist roots; Windows drive-letter paths require exporting `/mnt/c/...` roots inside Bash or adding a Windows-safe controller startup path.
- CodeGraphContext is running locally, but only deterministic lookup/investigation/refactor orchestration slices are exposed and live-validated. The first curated relationship adapter is implemented and live-validated behind `code_context.lookup`; do not expose the raw MCP surface to model-visible use.
- `workflow_feedback.record` is regression-covered and live-validated through direct controller, gateway, and AnythingLLM against both frozen fixtures. The latest feedback run IDs are recorded in the current status section above and in [Actionable Workflow Roadmap](ACTIONABLE_WORKFLOW_ROADMAP.md).

## Done Criteria

This integration is complete only when:

1. the final skills product passes direct `localhost:8000` validation
2. the final skills product passes frozen Coinbase repo validation
3. the controller workflow schema is implemented
4. the controller harness adapter can run the planning workflow with explicit envelope input
5. the gateway routes explicit controller envelopes to the controller harness and fails closed when routing is unavailable
6. the gateway and role prompt proxy paths pass live forwarding tests
7. AnythingLLM can run the same explicit workflow request through `8300` and return bounded artifacts
8. frozen repo non-mutation proof is recorded for the controller and AnythingLLM paths
9. mutation tests prove approved apply packets mutate only disposable copies of both frozen fixtures
10. feedback records are created from the live test results and do not imply approval to implement follow-up changes

Current status against these criteria: criteria 1 through 10 are satisfied for the current product slice, including dry-run routing through AnythingLLM, feedback capture through AnythingLLM, live mutation probes on disposable fixture copies, and the later Phase 71 browser-rendered AnythingLLM UI E2E proof. The controller/gateway route remains the product runtime path.
