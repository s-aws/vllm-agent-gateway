# Release Notes And Known Limitations

## Release Status

Current status: `ready_for_founder_testing`.

Latest proof floor: Phase 226 made M6/M8 large-context usability release-usable through retrieval-backed chat, artifact paging, context strategy routing, live gateway proof, and live AnythingLLM proof. M9 founder feedback rebaseline and repair rerun gates are in place. M12 small skill admission completed for the Python-service fixture without manual skill injection. Phase 231 proved runtime recovery reliability after restarting vLLM and the repo-managed gateway/proxy/controller stack, including post-restart small-repo and large-context prompts through gateway and AnythingLLM.

Earlier founder-field closeout: Phase 170 refreshed the stable proof floor after the Phase 163-169 chat-quality batch and kept the decision at `release_for_founder_testing`. Phases 171 through 176 closed the six Phase 169 product-gap proposals, and Phases 180 through 185 added chat-quality hardening: answer-first chat contract hardening, natural output-format selector stabilization, evidence relevance ranking, related-test discovery reliability, browser-visible AnythingLLM UI replay for repaired Priority 0 prompt families, and a reusable contextless-agent audit pack. Phase 230 admitted the first small skill-library fixture/eval coverage candidate using existing skills. Phase 231 proves the restarted runtime is ready with `decision=ready_after_recovery`.

This release is a local coding-agent harness for chat-quality testing through the workflow-router gateway. The tested user-facing path is AnythingLLM configured to use:

```text
http://127.0.0.1:8500/v1
```

AnythingLLM itself is expected at:

```text
http://127.0.0.1:3001
```

The AnythingLLM API checks use `ANYTHINGLLM_API_KEY` from the local environment.

The local model remains behind the gateway stack at:

```text
http://127.0.0.1:8000/v1
```

The ordinary model gateway is available at `http://127.0.0.1:8300`; it is not the workflow-router target for AnythingLLM. The controller service is available at `http://127.0.0.1:8400`; it is not an OpenAI-compatible chat endpoint. Role proxy ports validated for this release include `8101`, `8102`, `8201`, `8202`, `8203`, `8204`, and `8205`.

Generated proof artifacts stay under `runtime-state/` and are local-only.

The committed clean-clone proof metadata is:

```text
runtime/release_proofs/v1-1-release-candidate-stable-proof.json
```

## Supported In This Release

- Natural-language workflow routing through AnythingLLM and the workflow-router gateway.
- Read-only L1/L2 coding-agent prompts that return useful chat-visible answers with evidence and source-mutation boundaries.
- Default `format_a` chat output and requested `json` output through the same controller response path.
- Task decomposition for supported planning prompts.
- Draft-only small implementation planning.
- Approval-gated disposable-copy apply proof with rollback evidence.
- Founder feedback capture, classification, closure review, and triage dashboard.
- Setup and health checks for localhost model, gateway, controller, role ports, AnythingLLM, and both frozen fixtures.
- Post-restart readiness proof over doctor, health drift, and AnythingLLM greeting/session recovery.
- Runtime recovery reliability proof that restarts vLLM plus the repo-managed stack and then validates small-repo and large-context prompts through gateway and AnythingLLM.
- Large-context usability through retrieval-backed evidence selection, context strategy routing, and artifact paging instead of raw prompt stuffing.
- Small skill admission for Python-service endpoint and schema fixture coverage without manual skill injection.
- Founder feedback rebaseline and repair rerun gates for useful, advisory, repair-worthy, rejected, deferred, baseline, and holdout outcomes.
- Blind-baseline-first founder field round 2 with full response artifacts, route-surface proof, scoring, and prompt-advisory routing.
- Prompt-advisory closure proof with refined prompt candidates, holdouts, no silent prompt rewrites, and Phase 169 escalation routing.
- Generic chat and vague prompt guidance for greetings, ordinary help, missing target roots, target-scoped no-task prompts, approval-bypass mutation requests, and stale-session greeting isolation.
- Browser-visible AnythingLLM UI replay proof for stable Priority 0 cases and no-target generic/vague prompts.
- Browser-visible AnythingLLM UI replay proof for repaired evidence relevance and related-test discovery prompt families.
- Primary answer rendering for `summary.answer`: FormatA starts with `Answer:` before router metadata, and JSON exposes matching `chat_contract.answer` and `primary_answer_contract.text`.
- Evidence relevance ranking that labels direct, strong, and supporting evidence in chat-visible code investigations.
- Related-test discovery that labels evidence kind and confidence, and says when no bounded tests are found instead of inventing coverage.
- Contextless-agent audit pack for future blind-baseline-first chat-quality evaluations.
- Failure-to-roadmap proposal pass for unresolved Phase 165 product-gap escalations, with the resulting Phase 171-176 repair set now closed.

Validated fixture roots:

```text
/mnt/c/coinbase_testing_repo_frozen_tmp
/mnt/c/coinbase_testing_repo_frozen_tmp.github
```

## Known Limitations

- This is a local founder-testing release, not a production deployment.
- Validation is centered on the current local model and the two frozen Coinbase fixtures.
- Live runtime validators should be run from Bash/WSL because Windows clients can hit Bash-hosted localhost body-timeout behavior.
- AnythingLLM must point at `http://127.0.0.1:8500/v1` for natural workflow routing. `8300` is ordinary model gateway chat, and `8400` is the controller service.
- `format_a` and `json` are the only governed output formats currently released.
- Draft and apply flows are intentionally narrow. Unsupported mutation requests should block or require exact approved packet details.
- The git-enabled frozen fixture can show Windows/WSL line-ending noise; watched-hash and protected-fixture mutation proof are the release checks.
- Phase 169 converted 6 prompt-advisory product gaps into proposals: `FTR-P169-001-p08`, `FTR-P169-002-p21`, `FTR-P169-003-p29`, `FTR-P169-004-p30`, `FTR-P169-005-p33`, and `FTR-P169-006-p34`. That repair set is closed in Phases 171-176, but future broad prompt families still need their own blind-baseline and live validation before release.
- Raw 1M-token prompt serving is not claimed. Large-context usability is currently implemented through retrieval, chunking, summarization, artifact paging, evidence selection, and routing.

## Not Included

Advanced broad refactor orchestration is not released.

This release does not claim:

- every coding-agent task is supported
- every repository or language works
- source changes can be applied directly to protected frozen fixtures
- unsupported output formats such as YAML, tables, or Markdown have governed parity
- fine-tuning is required or completed

## Validation Evidence

Current proof summary:

- Stable chat-quality release: `status=passed`, `readiness=ready_for_founder_testing`, `gate_count=11`, `blocker_count=0`.
- Chat-quality release snapshot: `status=passed`, `release_readiness=ready_for_founder_testing`, `missing_artifact_count=0`, `missing_doc_count=0`, `actionable_feedback_count=0`.
- Natural output format preference: `status=passed`, `case_count=4`, gateway and AnythingLLM passed on both frozen fixtures.
- Founder feedback triage dashboard: `status=passed`, `feedback_record_count=4`, `unresolved_feedback_count=0`, `open_next_action_count=0`, `blocker_count=0`.
- Stable release blocker closure: `status=passed`, `unresolved_blocker_count=0`.
- Gateway and AnythingLLM health drift: `status=passed`, `check_count=29`, `failed_check_count=0`, `finding_count=0`, `unclassified_finding_count=0`.
- Founder test prompt pack: `status=governed`, `case_count=14`, `smoke_case_count=4`, `expanded_read_only_case_count=10`.
- Founder smoke suite: `status=passed`, `passed=4`, `failed=0`, AnythingLLM preflight passed.
- Advanced refactor readiness boundary: `broad_refactor_runtime_enabled=false`, `stable_promotion_enabled=false`.
- Founder field round 1: `status=passed`, `case_count=30`, `pass_case_count=16`, `advisory_case_count=14`, `blocker_case_count=0`.
- Transcript quality feedback intake: `status=passed`, `accepted_finding_count=14`, `phase159_eligible_count=0`, `category_counts={"prompt_issue":14}`.
- Priority 0 repair loop: `status=passed`, `repair_mode=no_repair_required`, `open_repair_count=0`.
- Stable release refresh: `status=passed`, `readiness=ready_for_founder_testing`, `decision=release_for_founder_testing`, `refresh_command_count=5`, `source_report_count=17`, `phase169_proposal_count=6`, `phase169_release_blocker_count=0`.
- Skill/tool gap batch proposal: `status=passed`, `decision=no_new_batch_justified`, `gap_candidate_count=0`, `implementation_authorized=false`.
- Post-restart runtime readiness: `status=passed`, `decision=ready_after_restart`, `required_surface_count=16`, `covered_surface_count=16`, `missing_required_surface_count=0`.
- Founder field round 2: `status=passed`, `quality_status=advisory`, `case_count=16`, `average_score=94.0`, `min_score=91`, `classification_counts={"pass":2,"advisory":14,"blocker":0,"proposal_candidate":0}`, `validation_error_count=0`.
- Prompt advisory closure: `status=passed`, `closure_count=14`, `documented_guidance=8`, `product_gap_escalation=6`, `holdout_min_score=97`, `validation_error_count=0`.
- Generic chat and vague prompt contract: `status=passed`, `case_count=24`, `passed_case_count=24`, surfaces `direct_controller`, `workflow_router_gateway`, and `anythingllm`, `target_root_count=2`, `fixture_state_changed=false`.
- AnythingLLM UI replay gate: `status=passed`, `case_count=11`, `fixture_unchanged=true`, `non_ignored_request_failures=0`, `page_errors=0`, stable answer-usefulness cases passed, 22 screenshots captured, and both frozen fixtures covered.
- Chat answer usefulness tightening: no-target UI replay `status=passed`, `case_count=3`, ordered `Answer:` markers passed before router metadata, JSON parity proved matching `summary.answer`, `chat_contract.answer`, and `primary_answer_contract.text`, and mixed UI replay still passed 11 cases with unchanged fixtures.
- Failure-to-roadmap Phase 169: `status=passed`, `finding_count=6`, `proposal_count=6`, `unapproved_proposal_count=6`, `approved_proposal_count=0`, `release_blocker_count=0`, `roadmap_mutation_allowed=false`, and `source_mutation_allowed=false`.
- Chat answer contract hardening: `status=passed`, supported Priority 0 workflows return answer-first chat output instead of artifact-only responses.
- Evidence relevance ranking: synthetic gate passed `3/3`; live gateway and AnythingLLM gate passed `4/4` cases on both frozen Coinbase fixtures.
- Related-test discovery reliability: synthetic gate passed `3/3`; live gateway and AnythingLLM gate passed `8/8` direct/no-test cases on both frozen Coinbase fixtures.
- Phase 184 AnythingLLM UI replay: `status=passed`, `case_count=6`, `fixture_unchanged=true`, semantic status passed for every case, and no UI errors.
- Phase 185 contextless-agent audit pack: `status=passed`, `template_count=4`, `process_step_count=7`, `sample_report_count=3`, `prompt_family_count=3`, and `validation_error_count=0`.
- Large-context usability live closeout: `status=passed`, gateway and AnythingLLM proof passed, `m6_ready=true`, `m8_ready=true`, and raw prompt stuffing remained disallowed.
- Founder feedback loop rebaseline: governed feedback outcomes pass for useful, advisory, repair-worthy, rejected, deferred, baseline, and holdout cases.
- Founder feedback repair rerun gate: accepted repairs require target, holdout, blind-baseline, mutation, and artifact proof before closure.
- Small skill admission pilot: `status=passed`, `FX-001` implemented, gateway and AnythingLLM proof passed for Python-service endpoint and schema prompts.
- Runtime recovery reliability rebaseline: `status=passed`, `decision=ready_after_recovery`, `covered_surface_count=7`, `missing_required_surface_count=0`, small-repo gateway `workflow-router-20260614T110227117340Z`, small-repo AnythingLLM `workflow-router-20260614T110233546368Z`, large-context gateway `workflow-router-20260614T110240178441Z`, and large-context AnythingLLM `workflow-router-20260614T110246887855Z`.

Primary proof artifacts:

```text
runtime-state/stable-chat-quality-release/phase130/phase130-stable-chat-quality-release-report.json
runtime-state/chat-quality-release-snapshot/phase136/phase136-chat-quality-release-snapshot.json
runtime-state/natural-output-format-preference/phase144/phase144-natural-output-format-preference-live.json
runtime-state/founder-feedback-triage-dashboard/phase145/phase145-founder-feedback-triage-dashboard.json
runtime-state/stable-release-blocker-closure/phase131/phase131-stable-release-blocker-closure-report.json
runtime-state/gateway-anythingllm-health-drift/phase141/phase141-health-drift-report.json
runtime/founder_test_prompt_pack.json
runtime/prompt_catalogs/founder_field_v1.json
runtime-state/founder-field-tests/phase134-founder-smoke.json
runtime/release_proofs/v1-1-release-candidate-stable-proof.json
runtime-state/advanced-refactor-readiness/phase105-readiness.json
runtime-state/founder-field-round1/phase157/phase157-founder-field-round1-report.json
runtime-state/transcript-quality-feedback-intake/phase158/phase158-transcript-quality-feedback-intake-report.json
runtime-state/priority0-repair-loop/phase159/phase159-priority0-repair-loop-report.json
runtime-state/stable-release-refresh/phase160/phase160-stable-release-refresh-report.json
runtime-state/skill-tool-gap-batch-proposal/phase161/phase161-skill-tool-gap-batch-proposal-report.json
runtime-state/post-restart-runtime-readiness/phase163/phase163-post-restart-runtime-readiness-report.json
runtime-state/founder-field-round2/phase164/phase164-founder-field-round2-report.json
runtime-state/prompt-advisory-closure/phase165/phase165-prompt-advisory-closure-report.json
runtime-state/generic-chat-vague-prompt-contract/phase166/phase166-generic-chat-vague-prompt-contract-report.json
runtime-state/anythingllm-ui/phase167/phase167-ui-replay-mixed.json
runtime-state/release-notes/phase167/phase167-release-notes-report.json
runtime-state/anythingllm-ui/phase168/phase168-answer-first-ui-replay.json
runtime-state/anythingllm-ui/phase168/phase168-answer-first-ui-replay-mixed.json
runtime-state/failure-to-roadmap/phase169/phase169-failure-to-roadmap-report.json
runtime-state/release-notes/phase169/phase169-release-notes-report.json
runtime-state/stable-release-refresh/phase170/phase170-stable-release-refresh-report.json
runtime-state/post-restart-runtime-readiness/phase170/phase170-post-restart-runtime-readiness-report.json
runtime-state/release-notes/phase170/phase170-release-notes-report.json
runtime-state/chat-answer-contract-hardening/phase180-live-inline-report.json
runtime-state/evidence-relevance-ranking/phase182-live-report.json
runtime-state/related-test-discovery-reliability/phase183-live-report.json
runtime-state/anythingllm-ui/phase184-ui-replay-report.json
runtime-state/contextless-agent-audit-pack/phase185/phase185-contextless-agent-audit-pack-report.json
runtime-state/large-context-live-closeout/phase221/phase221-large-context-live-report.json
runtime-state/founder-feedback-loop-rebaseline/phase227/phase227-founder-feedback-loop-rebaseline-report.json
runtime-state/founder-feedback-repair-rerun-gate/phase228/phase228-founder-feedback-repair-rerun-gate-report.json
runtime-state/skill-library-scaling/phase230/phase230-small-skill-admission-pilot-report.json
runtime-state/phase231/phase231-runtime-recovery-reliability-rebaseline-report.json
```

## Re-Run Commands

Run from Bash/WSL:

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_stable_release_blocker_closure.py \
  --require-artifacts \
  --output-path runtime-state/stable-release-blocker-closure/phase131/phase131-stable-release-blocker-closure-report.json
python3 scripts/validate_stable_chat_quality_release.py \
  --require-artifacts \
  --output-path runtime-state/stable-chat-quality-release/phase130/phase130-stable-chat-quality-release-report.json
python3 scripts/validate_natural_output_format_preference_live.py \
  --output-path runtime-state/natural-output-format-preference/phase144/phase144-natural-output-format-preference-live.json \
  --timeout-seconds 900
python3 scripts/validate_founder_feedback_triage_dashboard.py \
  --require-artifacts \
  --output-path runtime-state/founder-feedback-triage-dashboard/phase145/phase145-founder-feedback-triage-dashboard.json
python3 scripts/validate_release_notes.py \
  --require-artifacts \
  --output-path runtime-state/release-notes/phase146/phase146-release-notes-report.json
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
python3 scripts/validate_founder_field_round2.py \
  --run-live \
  --timeout-seconds 900 \
  --output-path runtime-state/founder-field-round2/phase164/phase164-founder-field-round2-report.json \
  --markdown-output-path runtime-state/founder-field-round2/phase164/phase164-founder-field-round2-report.md
python3 scripts/validate_prompt_advisory_closure.py \
  --run-live \
  --timeout-seconds 900 \
  --output-path runtime-state/prompt-advisory-closure/phase165/phase165-prompt-advisory-closure-report.json \
  --markdown-output-path runtime-state/prompt-advisory-closure/phase165/phase165-prompt-advisory-closure-report.md
python3 scripts/validate_generic_chat_vague_prompt_contract.py \
  --run-live \
  --timeout-seconds 180 \
  --output-path runtime-state/generic-chat-vague-prompt-contract/phase166/phase166-generic-chat-vague-prompt-contract-report.json
python3 scripts/validate_anythingllm_ui_e2e.py \
  --anythingllm-api-base-url http://127.0.0.1:3001 \
  --workspace my-workspace \
  --ui-dist-root runtime-state/anythingllm-ui/asar-dist/dist \
  --timeout-seconds 420 \
  --output-path runtime-state/anythingllm-ui/phase167/phase167-ui-replay-mixed.json \
  --case-id UI126-CQ116-001 \
  --case-id UI126-CQ116-009 \
  --case-id UI126-DD117-001 \
  --case-id UI126-DD117-002 \
  --case-id UI126-EJ118-001 \
  --case-id UI126-EJ118-002 \
  --case-id UI126-DM119-001 \
  --case-id UI126-DM119-002 \
  --case-id UI167-GENCHAT-001 \
  --case-id UI167-GENHELP-001 \
  --case-id UI167-VAGUE-001
python3 scripts/validate_anythingllm_ui_e2e.py \
  --anythingllm-api-base-url http://127.0.0.1:3001 \
  --workspace my-workspace \
  --ui-dist-root runtime-state/anythingllm-ui/asar-dist/dist \
  --timeout-seconds 300 \
  --output-path runtime-state/anythingllm-ui/phase168/phase168-answer-first-ui-replay.json \
  --case-id UI167-GENCHAT-001 \
  --case-id UI167-GENHELP-001 \
  --case-id UI167-VAGUE-001
python3 scripts/validate_failure_to_roadmap.py \
  --require-artifacts \
  --policy-path runtime/failure_to_roadmap_phase169_policy.json \
  --output-path runtime-state/failure-to-roadmap/phase169/phase169-failure-to-roadmap-report.json
python3 scripts/validate_contextless_agent_audit_pack.py \
  --output-path runtime-state/contextless-agent-audit-pack/phase185/phase185-contextless-agent-audit-pack-report.json
```
