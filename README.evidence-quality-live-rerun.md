# Evidence Quality Live Rerun

Phase 208 reruns the Phase 206 evidence-quality prompts through the live workflow-router gateway and AnythingLLM, then checks the chat-visible answer against Phase 207 source-proof expectations.

This gate is for Priority 0 chat quality. It does not add a new retrieval path. It verifies that the current controller, router, formatter, gateway, AnythingLLM configuration, and local model return useful evidence-backed answers for the supported M4 evidence-quality prompt families.

## What It Checks

- The Phase 206 audit pack and Phase 207 source-hash gate are both passed and ready.
- Four holdout prompts are run against the same blind baselines so target prompt repairs do not overfit.
- Each Phase 206 prompt is mirrored across both frozen fixtures:
  - `/mnt/c/coinbase_testing_repo_frozen_tmp`
  - `/mnt/c/coinbase_testing_repo_frozen_tmp.github`
- Each prompt is run through both live surfaces:
  - workflow-router gateway
  - AnythingLLM API
- Chat output includes `Answer:`, `Skill Selection:`, `Context Sources:`, artifact traceability, source mutation status, and case-specific useful answer markers.
- Chat output exposes at least one Phase 207 source-proof path and line.
- Live artifacts prove the requested target root was used by the controller and downstream workflow.
- Phase 207 source proofs are revalidated against live fixture files. The Phase 207 source root requires whole-file and line-hash proof; mirrored roots require line-hash and query proof because equivalent frozen repositories may have different whole-file hashes.
- Blind-baseline rubric dimensions from Phase 206 are scored for each live response.
- Protected frozen fixture files remain unchanged.

## Inputs

- `runtime/evidence_quality_live_rerun_policy.json`
- `runtime-state/phase206/phase206-evidence-relevance-audit-pack-report.json`
- `runtime-state/phase207/phase207-evidence-ranking-source-hash-gate-report.json`
- live localhost model at `127.0.0.1:8000`
- workflow-router gateway at `127.0.0.1:8500`
- controller service at `127.0.0.1:8400`
- AnythingLLM API with `ANYTHINGLLM_API_KEY`

## Outputs

- Live closeout:
  - `runtime-state/phase208/phase208-evidence-quality-live-rerun-report.json`
  - `runtime-state/phase208/phase208-evidence-quality-live-rerun-report.md`
- Offline preflight:
  - `runtime-state/phase208/phase208-evidence-quality-live-rerun-preflight-report.json`
  - `runtime-state/phase208/phase208-evidence-quality-live-rerun-preflight-report.md`

Preflight and live outputs intentionally use separate default paths so a routine offline check cannot overwrite the live release proof.

## Validation

Run preflight from Bash/WSL:

```bash
python3 scripts/validate_evidence_quality_live_rerun.py
```

Run live closeout from Bash/WSL after the local model, gateway/proxies, controller, and AnythingLLM are running:

```bash
python3 scripts/validate_evidence_quality_live_rerun.py --live
```

The full gate currently runs eight live cases: four Phase 206 audit prompts plus four Phase 208 holdout prompts, across two frozen roots and two surfaces, for 32 live responses.

Focused regression:

```bash
python3 -m pytest tests/regression/test_evidence_quality_live_rerun.py tests/regression/test_chat_response_contract.py::test_format_a_behavior_start_prefers_investigation_plan_over_cli_lookup -q
```

Expected live passing marker:

```text
PHASE208 EVIDENCE QUALITY LIVE RERUN PASS
```

## Failure Review

If this gate fails, inspect the failed response entries first. A failed entry includes the surface, target root, live case id, baseline audit case id, run id, visible source-ref hits, expected source refs, baseline score, target-root proofs, errors, and a chat excerpt.

Common repair targets:

- route drift: expected Phase 206 route rule is missing from `route-decision.json`
- stale gateway process: restart `stop-agent-prompt-proxies.sh` and `start-agent-prompt-proxies.sh`
- formatter gap: source refs or required answer sections are present in artifacts but missing from chat
- evidence ranking gap: the beginning point or source proof line is not the Phase 207 direct evidence
- AnythingLLM drift: AnythingLLM is pointed at the wrong local gateway target or lacks `ANYTHINGLLM_API_KEY`
