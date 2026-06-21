# Stable Handoff

Stable is the external-tester channel promoted from the passed V1.1 release-candidate proof.

Use this handoff only for the current product surface: natural-language L1/L2 read-only prompts, draft-only small implementation plans, approved disposable-copy apply proof, feedback capture, setup validation, security policy validation, large-context usability, runtime recovery reliability, and run observability. Advanced broad refactor orchestration remains deferred.

## What Stable Means

- `runtime/release_channels.json` marks `stable` as `active`.
- Stable activation points at the committed proof `runtime/release_proofs/v1-1-release-candidate-stable-proof.json`.
- Generated `runtime-state/` reports are local-only; committed proof metadata is the clean-clone source of truth.
- The activation report is a passed `v1_acceptance_report` with profile `v1.1-release-candidate`.
- First-time testers use AnythingLLM pointed at the workflow-router gateway. On split Windows/WSL hosts, use the WSL network workflow-router URL printed by `start-agent-prompt-proxies.sh`; Bash-side validators keep their internal workflow-router URL on `http://127.0.0.1:8500/v1`.
- The stable smoke command reruns setup, release-channel validation, security policy, one live onboarding prompt, feedback capture, and protected-fixture checks.
- Phase 273 proves the current 500k-token project usability target live through the workflow-router gateway and AnythingLLM with retrieval, artifact paging, summarization, chunked investigation, refusal routing, split-url target settings, stale-index rejection, clean-clone lineage, blind-baseline comparison, and JSON/default parity.
- Phase 276 aggregates the current 500k proof chain into decision `ship` with an explicit Phase 275 clean-clone report path, zero blockers, healthy runtime probes, and `phase277_ready=true`.
- Phase 277 refreshes stable handoff metadata and docs for 500k-token project usability through governed context strategy. The 384k-token project usability baseline remains preserved.
- Phase 296 closes the EIG-1/EIG-2 local-stub connector breadth proof for governed connector manifests, controller-owned mediation, actor/scope enforcement, approval replay, and selected natural-language connector chat.
- Phase 303 closes the EIG-3 synthetic privacy breadth proof for sensitive-data classification, output-surface handling, governed memory lifecycle, privacy EvalOps, and privacy-sensitive runtime chat.
- Phase 351 proves the full governed browser-visible AnythingLLM UI suite with `case_count=21`, `error_count=0`, `fixture_unchanged=true`, and both frozen roots covered.
- Phase 352 proves the pushed Phase 351 UI proof metadata and clone-safe UI policy tests are auditable from a clean clone with `37 passed` and no active-workspace runtime-state dependency.
- Phase 230 admits the first M12 small skill-library fixture/eval coverage candidate without manual skill injection.
- Phase 231 proves runtime recovery reliability after restarting vLLM and the repo-managed gateway/proxy/controller stack.
- Feedback still records through `workflow_feedback.record`; Phase 227 classifies feedback outcomes and Phase 228 prevents accepted repairs from closing without target and holdout rerun proof.

Stable does not mean every coding-agent task is supported. It means the current documented tester path is ready for external use under the stated boundaries.

Stable EIG proof remains local and synthetic. Real external connector execution is not shipped, arbitrary natural-language connector calls are not shipped, production OAuth token exchange is not shipped, real sensitive-data ingestion is not shipped, and persistent hidden memory is not shipped.

## Prerequisites

- vLLM model endpoint is healthy at `http://127.0.0.1:8000/v1`.
- Harness ports are healthy at `8300`, `8500`, `8400`, and role ports.
- AnythingLLM is running. Use `http://127.0.0.1:3001` only when it is actually the AnythingLLM API; if loopback is owned by another local app, use the reachable network API base such as `http://192.168.0.208:3001`.
- AnythingLLM is configured to use the workflow-router gateway. Use `http://127.0.0.1:8500/v1` only when the AnythingLLM client can reliably read response bodies from loopback; otherwise use the printed WSL network workflow-router URL.
- `ANYTHINGLLM_API_KEY` is available.
- Both frozen fixtures exist:
  - `/mnt/c/coinbase_testing_repo_frozen_tmp`
  - `/mnt/c/coinbase_testing_repo_frozen_tmp.github`

The git-enabled fixture may show many modified files when inspected from Bash because of Windows/WSL line-ending behavior. This is a warning, not a blocker, when the stable smoke report says watched hashes are unchanged and protected fixture state `changed` is `false`. Treat it as a blocker only if watched hashes change, the warning is not line-ending-only, or the smoke reports fixture mutation.

## Stable Smoke

Run from Bash:

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/validate_stable_handoff.py \
  --release-candidate-report runtime/release_proofs/v1-1-release-candidate-stable-proof.json \
  --anythingllm-api-base-url http://192.168.0.208:3001 \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --expected-anythingllm-llm-base-url http://100.100.12.45:8500/v1 \
  --controller-base-url http://127.0.0.1:8400 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --timeout-seconds 900 \
  --command-timeout-seconds 3600 \
  --output-path runtime-state/stable-handoff/stable-smoke.json
```

Expected markers:

```text
STABLE HANDOFF REPORT ...
STABLE HANDOFF SUMMARY ...
STABLE HANDOFF PASS
```

The report lists the child setup, release-channel, security, and onboarding reports.

If AnythingLLM is configured to the WSL network URL printed by `start-agent-prompt-proxies.sh`, keep `--workflow-router-gateway-base-url` on `http://127.0.0.1:8500/v1` for Bash-side validation and pass the printed network URL to `--expected-anythingllm-llm-base-url`.

## Field-Test Closeout

Run this after stable smoke when preparing the founder handoff:

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
python3 scripts/validate_runtime_recovery_reliability_rebaseline.py \
  --restart-managed-stack \
  --restart-vllm-container vllm-qwen3 \
  --timeout-seconds 900
```

Expected current decisions:

```text
ready_for_founder_testing
release_for_founder_testing
no_new_batch_justified
```

The Phase 231 report should show `decision=ready_after_recovery`, `covered_surface_count=7`, and `missing_required_surface_count=0`.

If Phase 161 ever returns `propose_batch_for_founder_approval`, or a later failure-to-roadmap pass produces approved implementation candidates, stop founder handoff expansion and review the proposals before implementing anything.

## 500k Large-Context Acceptance

Run this when a tester needs to verify the current large-context target rather than only the first L1 prompt:

```bash
python3 scripts/validate_large_context_500k_live_acceptance.py \
  --live \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --anythingllm-workflow-router-base-url http://127.0.0.1:8500/v1 \
  --timeout-seconds 1200
```

If AnythingLLM is using the WSL network URL printed by `start-agent-prompt-proxies.sh`, first restart the managed stack with `WORKFLOW_ROUTER_GATEWAY_BIND_HOST=0.0.0.0` so the printed target is reachable from Windows. Then pass that URL to `--anythingllm-workflow-router-base-url` and keep `--workflow-router-gateway-base-url` on `http://127.0.0.1:8500/v1`.

Expected marker:

```text
PHASE273 LARGE CONTEXT 500K LIVE ACCEPTANCE PASS
```

This proves usable 500k-token project behavior through governed context strategy. It does not approve raw 500k prompt serving.

## 500k Stable Handoff Refresh

Run this after the Phase 276 decision gate when validating the accepted 500k stable handoff:

```bash
python3 scripts/validate_large_context_500k_stable_handoff_refresh.py \
  --phase276-report-path runtime-state/phase276/phase276-large-context-500k-candidate-decision-gate-report.json
```

Expected marker:

```text
PHASE277 LARGE CONTEXT 500K STABLE HANDOFF REFRESH PASS
```

Expected decision:

```text
decision=stable_500k_handoff_refreshed
phase278_ready=true
```

Raw 500k prompt serving is not claimed. Raw 1M-token prompt serving is not claimed. Advanced broad refactor orchestration remains deferred.

## EIG Stable Handoff Integration

Run this static gate before describing EIG connector, identity/scope, privacy, or memory-safety work as visible in stable handoff docs:

```bash
python3 scripts/validate_eig_stable_handoff_integration.py \
  --output-path runtime-state/eig-stable-handoff-integration/phase304-validation.json
```

Expected marker:

```text
EIG STABLE HANDOFF INTEGRATION PASS
```

This confirms that release-facing docs reference Phase 296 and Phase 303, required EIG runtime proof files are present, and the handoff preserves the local-stub connector and synthetic privacy scope boundaries.

## First Tester Prompt

Use a fresh AnythingLLM thread and send:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, explain what find_stealth_order_by_placed_order_id does in core/stealth_order_manager.py. Read only. Include key inputs, outputs, side effects, and tests.
```

Expected response markers include:

- `workflow_router.plan completed`
- `run_id: workflow-router-`
- `Selected workflow:`
- `Selected skills:`
- `Selected tools:`
- `Answer:`
- `Inputs:`
- `Outputs:`
- `Side effects:`
- `Related tests:`

## Feedback

When a tester sees a confusing answer, wrong route, setup failure, unsafe output, or missing capability, record feedback in the same AnythingLLM chat using the returned `run_id`.

Example:

```text
Record feedback for run workflow-router-REPLACE_ME: useful: the answer was visible in chat. missing: the related tests section was too vague.
```

Feedback artifacts are written through `workflow_feedback.record`. Phase 227 classifies them as useful, advisory, repair-worthy, rejected, deferred, baseline, or holdout outcomes. Phase 228 requires accepted repairs to pass target, holdout, blind-baseline, mutation, and artifact proof before any item is marked fixed.

## Rollback

If stable smoke fails, stop tester handoff and use `release-candidate` until the failing check is fixed.

Restart the harness from Bash:

```bash
cd /mnt/c/agentic_agents
./stop-agent-prompt-proxies.sh
./start-agent-prompt-proxies.sh
```

Then rerun:

```bash
python3 scripts/run_first_time_user_doctor.py
python3 scripts/validate_stable_handoff.py \
  --release-candidate-report runtime/release_proofs/v1-1-release-candidate-stable-proof.json
```

If protected fixture state changes, do not run more live tests until fixture hashes and git status are inspected.

Examples: [docs/examples/stable-handoff.md](docs/examples/stable-handoff.md).
