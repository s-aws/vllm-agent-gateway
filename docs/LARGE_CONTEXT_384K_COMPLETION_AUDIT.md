# Large-Context 384k Completion Audit

Status: Complete for the current 384k-token project usability objective.

This audit decides whether the active large-context objective is satisfied by current evidence. The objective is usable 384k-token projects through governed context strategy. It is not raw 384k-token prompt serving and it is not post-384k expansion.

## Decision

The current 384k objective is complete for the supported product path:

```text
natural-language prompt
-> workflow-router gateway
-> controller-owned context strategy selection
-> governed metadata-first index and retrieval/chunking/paging/summarization/refusal
-> chat-visible answer with evidence and limitations
-> AnythingLLM user surface proof
```

Post-384k work remains paused. Raw 384k-token prompt serving remains unsupported because the current vLLM model endpoint reports `max_model_len=262144`, and no dedicated raw-384k proof gate has validated model config, vLLM settings, hardware memory, latency, and blind-baseline answer quality.

## Requirement Matrix

| Requirement | Evidence | Result |
| --- | --- | --- |
| Active target is 384k-token project usability, not 1M+ usability. | `AGENTS.md`, `README.md`, `docs/PROJECT_MILESTONES.md`, `docs/ACTIONABLE_WORKFLOW_ROADMAP.md`, and `docs/PRIORITY0_CHAT_QUALITY_BACKLOG.md` state that work above 384k is paused until the 384k path has a stable usable tester handoff and a future milestone is approved. | Passed. |
| Raw 384k-token prompt serving is not claimed. | `README.md`, `README.getting-started.md`, `README.stable-handoff.md`, `runtime/release_channels.json`, and `runtime/release_proofs/v1-1-release-candidate-stable-proof.json` explicitly state that raw 384k prompt serving is not claimed. Current `/v1/models` proof reports `max_model_len=262144`. | Passed. |
| 384k usability uses indexing, retrieval, chunking, summarization, artifact paging, evidence selection, and model-context-aware routing. | Phase 258 acceptance contract, Phase 259 fixture/index readiness, Phase 260 stale-index rejection, Phase 261 live acceptance, Phase 264 clean-clone replay, and Phase 265 decision gate prove the governed strategy path. | Passed. |
| The accepted fixture/index state reaches the 384k target. | Phase 259 composes Phase 214, Phase 216, and Phase 217 and records a fixture/index above `384000` estimated tokens with source-hash and metadata-only proof. | Passed. |
| Unsafe or stale index content is rejected. | Phase 260 rejects stale source hashes, changed ignore policy, changed safety policy, missing source files, unapproved roots, ignored/private paths, and secret-like evidence before live acceptance. | Passed. |
| Live gateway behavior works for the current 384k target. | Phase 261 live acceptance and Phase 268 live stable smoke both passed through workflow-router gateway. Phase 268 recorded `gateway_response_count=9`, all five strategy IDs, `json_default_parity_status=passed`, `critical_or_high_finding_count=0`, `failed_small_repo_regression_count=0`, and `raw_prompt_stuffing_allowed=false`. | Passed. |
| Live AnythingLLM behavior works for the current 384k target. | Phase 261 live acceptance and Phase 268 live stable smoke both passed through AnythingLLM. Phase 268 recorded `anythingllm_response_count=9`, `target_settings_status=passed`, all five strategy IDs, and zero high/critical findings. | Passed. |
| Basic founder chat remains usable after stable handoff. | Phase 268 passed first-time user doctor, scoped AnythingLLM UI E2E for `UI167-GENCHAT-001`, and fresh-chat responsiveness with gateway and AnythingLLM API cases. | Passed. |
| Stable handoff does not rely on private active-workspace state. | Phase 267 replayed the pushed Phase 266 handoff from `/tmp/agentic_agents_phase267_remote_clone_a3f4486_r2` at commit `a3f4486539672022a9b2edb7e207c2105e96829e`; docs index, stable release-channel, ship-handoff, and 384k decision validation passed; clone status was clean before and after validation. | Passed. |
| Stable release metadata records the current boundary. | `runtime/release_channels.json` and `runtime/release_proofs/v1-1-release-candidate-stable-proof.json` include 384k release-candidate metadata, `decision=ship`, `phase266_ready=true`, `target_estimated_project_tokens=384000`, and `post_384k_expansion_status=paused`. | Passed. |
| Protected frozen fixtures are not mutated. | Phase 261, Phase 264, Phase 267, and Phase 268 report clean fixture/source state. Phase 268 fresh-chat responsiveness and UI E2E both reported `fixture_unchanged=true`; live 384k acceptance reported `failed_small_repo_regression_count=0`. | Passed. |
| Runtime-state proof remains local-only. | `.gitignore` excludes `runtime-state/`; Phase 267 confirmed generated `runtime-state/` proof remained ignored and clone source status stayed clean. | Passed. |

## Latest Proof Commands

Phase 268 used the current active stack after restarting from `/mnt/c/agentic_agents` with:

```bash
GATEWAY_BIND_HOST=0.0.0.0 \
WORKFLOW_ROUTER_GATEWAY_BIND_HOST=0.0.0.0 \
CONTROLLER_BIND_HOST=0.0.0.0 \
bash start-agent-prompt-proxies.sh
```

The latest live gates were:

```bash
python3 scripts/run_first_time_user_doctor.py \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --expected-anythingllm-llm-base-url http://100.100.12.45:8500/v1 \
  --output-path runtime-state/phase268/phase268-first-time-user-doctor.json \
  --timeout-seconds 30

python scripts/validate_anythingllm_ui_e2e.py \
  --prompt-catalog-path runtime/anythingllm_ui_prompt_cases.json \
  --case-id UI167-GENCHAT-001 \
  --output-path runtime-state/phase268/phase268-anythingllm-ui-e2e.json \
  --timeout-seconds 420

python3 scripts/validate_anythingllm_fresh_chat_responsiveness.py \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --anythingllm-workflow-router-base-url http://100.100.12.45:8500/v1 \
  --ui-report-path runtime-state/phase268/phase268-anythingllm-ui-e2e.json \
  --output-path runtime-state/phase268/phase268-anythingllm-fresh-chat-responsiveness.json \
  --timeout-seconds 180

python3 scripts/validate_large_context_384k_live_acceptance.py \
  --live \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --anythingllm-workflow-router-base-url http://100.100.12.45:8500/v1 \
  --output-path runtime-state/phase268/phase268-large-context-384k-live-acceptance-report.json \
  --markdown-output-path runtime-state/phase268/phase268-large-context-384k-live-acceptance-report.md \
  --timeout-seconds 1200
```

## Known Boundaries

- The product does not claim raw 384k-token prompt serving.
- The product does not claim 1M+ project usability.
- Post-384k expansion requires a future approved milestone.
- Advanced broad refactor orchestration remains outside this completion audit.
- The current proof depends on the configured local stack, the current AnythingLLM workspace, and the accepted frozen fixtures.

## Audit Outcome

The current evidence proves the lowered 384k large-context objective for the supported product path. No missing proof remains for the active 384k objective. Future work should continue with normal product hardening, additional prompt coverage, and skill/tool scaling without expanding beyond 384k unless a post-384k milestone is explicitly approved.
