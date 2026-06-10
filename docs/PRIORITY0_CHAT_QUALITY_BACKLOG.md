# Priority 0 Chat Quality Backlog

This document defines the default testing process and backlog for improving local-model chat quality.

Priority 0 means the product is judged by whether a user can ask a natural-language development prompt and receive a useful, evidence-backed, chat-visible response through the current local model, gateway, skills, and tools.

## Default Process

Use blind-baseline-first testing for chat-quality work.

1. Select one natural-language prompt and target root.
2. Ask a bounded contextless blind agent for the ideal response shape before showing it any local-model output.
3. Require the blind baseline to include must-have facts, evidence expectations, safety boundaries, output-format expectations, and a scoring rubric.
4. Run the same prompt through the local stack:
   - workflow-router gateway
   - AnythingLLM API or UI when applicable
   - localhost model through the current gateway path
5. Compare the local response against the blind baseline.
6. Classify each miss as routing, context gathering, skill/tool selection, deterministic formatter, model capability, safety boundary, documentation, or test coverage.
7. Repair the smallest controller, workflow, skill, tool, prompt-catalog, or formatter gap.
8. Rerun the target prompt plus holdout prompts.
9. Record the baseline, local response, comparison, accepted/rejected findings, repairs, and validation commands.

Blind structural audits are still allowed for code, roadmap, and artifact review. They do not replace the blind-baseline-first loop for chat-answer quality.

## Acceptance Threshold

A Priority 0 prompt is stable only when all are true:

- The selected workflow, skill, and tool path are correct.
- The answer is immediately useful in chat and is not just a list of artifact links.
- The answer includes required facts, evidence references, and safety boundaries from the blind baseline.
- The answer does not claim unsupported implementation or mutation.
- JSON or alternate output formats preserve the same contract when requested.
- The same prompt passes through AnythingLLM when the workflow is user-facing.
- Both frozen Coinbase fixtures are covered when the prompt is coding-repo relevant.
- Holdout prompts still pass after repairs.
- Contextless re-audit finds no unresolved critical or high findings.

Default score target: `>= 85/100`, with no critical or high unresolved findings.

## Backlog

| ID | Area | Goal | First Proof |
| --- | --- | --- | --- |
| P0-BB-001 | Phase 116 code quality | Complete. Established blind baselines and a chat-visible code-quality review contract for code-quality and self-review prompts. | Passed live gateway and AnythingLLM comparison for 10 prompts and 20 responses with zero critical/high findings. |
| P0-BB-002 | Phase 117 defect diagnosis | Complete. Established blind baselines and a unified chat-visible defect-diagnosis contract for failing tests, pasted logs, reproduction steps, root-cause isolation, test-level selection, observability, and missing-data handling. | Passed live gateway and AnythingLLM comparison for 10 prompts and 20 responses with zero critical/high findings. |
| P0-BB-003 | Phase 118 tradeoffs and debt | Complete. Established blind baselines and a chat-visible engineering-judgment contract for technical tradeoffs, debt tracking, risk communication, review feedback, rejected alternatives, and architecture/implementation decisions. | Passed live gateway and AnythingLLM comparison for 10 prompts and 20 responses with zero critical/high findings. |
| P0-BB-004 | Phase 119 delivery and mentoring | Complete. Established blind baselines and a chat-visible delivery mentorship contract for end-to-end feature delivery, deployment readiness, and mentoring-style guidance. | Passed live gateway and AnythingLLM comparison for 10 prompts and 20 responses with zero critical/high findings and no baseline-topic gaps. |
| P0-BB-005 | Baseline corpus governance | Complete. Stores stable blind baselines, local response summaries, comparisons, repairs, holdouts, route proof, no-mutation proof, and stale-source hashes in a governed corpus. | Validator rejects missing baseline, missing local response, missing comparison, missing AnythingLLM proof, unresolved critical/high findings, fixture mutation proof gaps, missing holdouts, or stale repair status. |
| P0-BB-006 | AnythingLLM answer usefulness | Complete. Stable AnythingLLM responses must contain useful answer sections directly in chat before artifact links. | Validator rejects artifact-only, artifact-first, truncated, metadata-heavy, missing safety marker, stale hash, or family-detail-thin AnythingLLM responses. |
| P0-BB-007 | Holdout prompt bank | Complete. Keep holdouts for each prompt family so repairs do not overfit one prompt. | Holdout validator rejects missing holdouts, missing baselines, missing route captures, failed routes, low scores, unresolved findings, stale hashes, and mutation proof gaps. |
| P0-BB-008 | Gap taxonomy integration | Complete. Stable comparison misses route into the existing failure taxonomy and carry explicit gap classes plus bounded repair actions. | Priority 0 gap taxonomy validator passes the stable corpus with zero findings and rejects synthetic route, evidence, formatter, test-coverage, stale-hash, and missing-artifact failures. |
| P0-BB-009 | Output-format parity | Complete. Compares FormatA and JSON output across representative stable Priority 0 families through gateway and AnythingLLM. | JSON exposes the same inline answer contract, evidence markers, safety boundary, and run traceability as default chat output. |
| P0-BB-010 | Founder feedback loop | Complete. Converts natural founder feedback into governed baseline, holdout, repair-follow-up, or rejected-finding decisions. | Feedback records durably link prompt ID, target run ID, feedback run ID, gap classification, accepted/rejected decision, and validation result. |
| P0-BB-011 | Corpus-wide AnythingLLM UI usefulness | Complete. Extends UI E2E beyond L1-001/L1-002 to representative stable corpus prompts. | Browser-visible response segments pass answer-usefulness checks with screenshots and fixture mutation proof. |
| P0-BB-012 | Fresh local-model drift gate | Complete. Reruns a bounded stable-corpus subset against the current localhost model so stale proof does not hide model or harness drift. | Fresh local eval is compared against baseline corpus and prior accepted result with drift severity and next action. |
| P0-BB-013 | Prompt tightening recommendation gate | Complete. Generate reviewable prompt-improvement suggestions for misses or low-confidence passes without silently rewriting user prompts. | Suggestions are tied to baseline failures, classified, and blocked from rerun proof until approval. |
| P0-BB-014 | Skill/tool coverage gap gate | Complete. Identifies when a chat-quality miss requires a missing deterministic skill or tool instead of a prompt or formatter repair. | Gap report maps missing capability to a proposed skill/tool with an eval gate. |
| P0-BB-015 | Stable chat quality release gate | Complete. Consolidates baseline corpus, answer usefulness, holdouts, UI proof, drift proof, prompt-tightening recommendations, skill/tool coverage, and founder feedback into one readiness command. | Phase 130 reports `readiness=blocked` until unresolved Priority 0 items are closed. |
| P0-BB-016 | Stable release blocker closure | Complete. Resolved the Phase 130 blockers without weakening the release gate by adding governed closure proof. | Phase 130 reruns with `readiness=ready_for_founder_testing`, `status=passed`, and `blocker_count=0`. |
| P0-BB-017 | Founder testing handoff refresh | Complete. Refreshed first-time founder-testing docs around the current ready release gate and current AnythingLLM path. | Contextless founder can run one minimal smoke path with current docs and no stale blocked-release instructions. |
| P0-BB-018 | AnythingLLM founder smoke suite | Complete. Ran curated founder smoke prompts through AnythingLLM and recorded chat-visible quality. | Smoke report captures run IDs, selected workflows, answer quality, and fixture mutation proof. |
| P0-BB-019 | Founder feedback intake and classification | Complete. Converted smoke-suite feedback into governed decisions. | Current smoke produced zero actionable feedback items because all four cases passed. |
| P0-BB-020 | Release-candidate hardening batch | Complete through Phase 156. The V1 product readiness review and final stable release decision gate both pass. | Final Phase 156 report states `release_for_founder_testing` with evidence links, governed limitations, rollback path, and next-batch status. |
| P0-BB-021 | Founder field test round 1 | Complete. Ran 30 natural prompts through AnythingLLM on the current release path, with both frozen Coinbase fixtures covered. | Phase 157 report captured prompt text, target root, response evidence, run ID, quality classification, and mutation proof; 30 passed, 14 advisory prompt-risk cases, 0 blockers. |
| P0-BB-022 | Transcript quality and feedback intake | Complete. Converted Phase 157 advisory cases into governed monitoring findings and preserved transcript/run references. | Phase 158 report passed with 14 accepted prompt-issue monitoring findings, 0 rejected findings, 0 validation errors, and 0 Phase 159-eligible repair items. |
| P0-BB-023 | Priority 0 repair loop | Complete. Phase 158 produced no repair-eligible findings, so Phase 159 closed as a governed no-repair-required report. | Phase 159 report passed with `repair_mode=no_repair_required`, 14 monitoring-only findings, 0 repair items, 0 open repairs, and 0 validation errors. |
| P0-BB-024 | Stable release refresh | Complete. Reran the stable proof floor after the Phase 157-159 field-test chain. | Phase 160 report passed with `ready_for_founder_testing`, `release_for_founder_testing`, current model `Qwen3-Coder-30B-A3B-Instruct`, 5 refresh commands, 8 source reports, and 0 validation errors. |
| P0-BB-025 | Skill/tool gap batch proposal | Complete. The Phase 157-160 evidence does not currently justify a new deterministic skill/tool batch. | Phase 161 report passed with `decision=no_new_batch_justified`, `gap_candidate_count=0`, `missing_skill_tool_finding_count=0`, `non_batch_finding_count=14`, and `implementation_authorized=false`. |
| P0-BB-026 | Next founder handoff update | Complete. Founder-facing docs now include Phase 157-161 closeout state, rerun commands, proof paths, and known prompt-advisory limitations. | Contextless founder can run the current field-test path and see current limitations, prompts, proof paths, and the current `no_new_batch_justified` skill/tool decision. |
| P0-BB-027 | Post-restart runtime readiness gate | Complete. Make the post-reboot/post-restart check repeatable across localhost model, gateways, controller, role proxies, AnythingLLM API key/workspace/target URL, and greeting/session recovery. | Phase 163 report passed with `ready_after_restart`, 16/16 required surfaces covered, 0 source failures, 0 health findings, and 0 session blockers. |
| P0-BB-028 | Founder field test round 2 | Complete. Ran 16 natural prompts through blind-baseline-first comparison and the real AnythingLLM/workflow-router/local-model path. | Phase 164 report passed with 16/16 field cases, `average_score=94.0`, `min_score=91`, classifications `pass=2`, `advisory=14`, `blocker=0`, `proposal_candidate=0`, full response artifacts, route-surface proof, and unchanged fixtures. |
| P0-BB-029 | Phase 158 prompt-advisory closure | Complete. Closed the 14 prompt-risk advisories into documented guidance or product-gap escalation using refined prompt candidates and holdouts. | Phase 165 report passed with `documented_guidance=8`, `product_gap_escalation=6`, `holdout_min_score=97`, unchanged fixtures, full response artifacts, and no validation errors. Escalations `P08`, `P21`, `P29`, `P30`, `P33`, and `P34` feed Phase 169. |
| P0-BB-030 | Generic chat and vague prompt contract | Complete. Validated `hi`, ordinary help, vague asks, missing repo path, target-scoped no-task prompts, approval-bypass mutation requests, and stale-session greetings without accidental repo work. | Phase 166 report passed with `case_count=24`, `passed_case_count=24`, surfaces `direct_controller`, `workflow_router_gateway`, and `anythingllm`, both frozen fixtures covered, `fixture_state_changed=false`, and post-restart readiness still covering 16/16 required surfaces. |
| P0-BB-031 | AnythingLLM UI replay gate | Complete. Replayed selected stable prompts and no-target generic/vague prompts through the actual AnythingLLM UI, not only the API. | Phase 167 mixed UI replay passed with `case_count=11`, `fixture_unchanged=true`, `non_ignored_request_failures=0`, `page_errors=0`, 22 screenshots, stable answer-usefulness cases passed, and both frozen fixtures covered. |
| P0-BB-032 | Chat answer usefulness tightening | Complete. Promoted `summary.answer` to an answer-first FormatA section and JSON primary answer contract where Phases 164-167 exposed tool-log-shaped no-target output. | Phase 168 no-target UI replay passed with ordered `Answer:` before router metadata, JSON parity proved `summary.answer`, `chat_contract.answer`, and `primary_answer_contract.text` match, mixed UI replay passed 11 cases, and fixtures remained unchanged. |
| P0-BB-033 | Failure-to-roadmap proposal pass | Complete. Converted unresolved Phase 165 product-gap escalations from the Phase 163-168 batch into proposal-only roadmap candidates. | Phase 169 report passed with `finding_count=6`, `proposal_count=6`, `unapproved_proposal_count=6`, `approved_proposal_count=0`, `release_blocker_count=0`, no roadmap/source mutation, and no implementation. |
| P0-BB-034 | Stable refresh and handoff update | Complete. Reran the stable proof floor after the Phase 163-169 chat-quality batch and updated founder-facing handoff docs. | Phase 170 report passed with `ready_for_founder_testing`, `release_for_founder_testing`, `refresh_command_count=5`, `source_report_count=17`, `phase169_proposal_count=6`, `phase169_release_blocker_count=0`, and `validation_error_count=0`. |
| P0-BB-035 | Handler branch evidence repair | Complete. Phase 171 closed `FTR-P169-001-p08` for the refined `request_stealth_orders` handler-branch prompt. | Live AnythingLLM `P08`, `P27`, and `P28` passed with `handler-branch-tracer`, `downstream_request_flow_map`, visible handler/source/test evidence, both frozen fixtures covered, and no source mutation. |
| P0-BB-036 | Minimal change surface boundary repair | Complete. Phase 172 closed `FTR-P169-002-p21` for read-only files-to-touch/files-not-to-touch prompt ambiguity. | Live AnythingLLM `P21` and non-git `P34` passed with `downstream_change_surface_summary`, explicit touch/no-touch/unknown boundaries, risks, verification commands, both frozen fixtures covered, and no source mutation. |
| P0-BB-037 | Persisted schema evidence repair - git fixture | Complete in Phase 173 from `FTR-P169-003-p29`. Separated persisted `stealth_orders` schema fields from runtime dictionary fields for the git frozen fixture. | Git-fixture P29 refined and original prompts passed through AnythingLLM/workflow-router with persisted schema source refs, schema-only model files, and no fixture mutation. |
| P0-BB-038 | Persisted schema evidence repair - non-git fixture | Complete in Phase 174 from `FTR-P169-004-p30`. Proved the same persisted-schema behavior on the non-git frozen fixture. | Non-git P30 refined and original prompts passed with persisted schema source refs, schema-only model files, and no fixture mutation. |
| P0-BB-039 | Change boundary verification repair - git fixture | Complete in Phase 175 from `FTR-P169-005-p33`. Returned change boundaries, concrete risks, unknowns, and verification commands without drifting into implementation. | Git-fixture P33 refined and original prompts passed through AnythingLLM/workflow-router with risk-tied verification, plus P34 holdout; no fixture mutation. |
| P0-BB-040 | Change boundary verification repair - non-git fixture | Complete in Phase 176 from `FTR-P169-006-p34`. Proved the same change-boundary verification behavior on the non-git frozen fixture. | Non-git P34 refined and original prompts passed through AnythingLLM/workflow-router with risk-tied verification, a specific `non_git_text_search_fallback` gap, plus P33 git holdout; no fixture mutation. |
| P0-BB-041 | Post-repair stable proof refresh | Approved as Phase 177. Refresh the proof floor after Phases 172 through 176 complete. | Current stable, post-restart, prompt-matrix, founder-field, gateway, AnythingLLM, and fixture-mutation proof remains founder-testable. |
| P0-BB-042 | Blind-baseline delta report | Approved as Phase 178. Make the blind-baseline-first comparisons auditable across repaired prompt families. | Each evaluated prompt has baseline-before-local proof, local answer, score, gap classification, and next action. |
| P0-BB-043 | Prompt corpus governance V2 | Approved as Phase 179. Split prompt records into target, holdout, regression, promotion candidate, and retired categories. | Repairs cannot pass using only tuned target prompts, and promotion requires independent holdout proof. |
| P0-BB-044 | Chat answer contract hardening | Approved as Phase 180. Ensure supported workflows return immediately useful chat-visible answers by default. | Every supported Priority 0 workflow returns answer-first evidence, risks or gaps where applicable, and source mutation status. |
| P0-BB-045 | Output format selector stabilization | Approved as Phase 181. Stabilize default FormatA and requested JSON output without parallel behavior paths. | FormatA and JSON preserve equivalent evidence and safety boundaries through gateway and AnythingLLM validation. |
| P0-BB-046 | Evidence relevance ranking repair | Approved as Phase 182. Rank files, lines, tests, and source refs by relevance to the requested behavior. | Responses lead with strongest evidence, demote weak matches, and label unresolved gaps. |
| P0-BB-047 | Related-test discovery reliability | Approved as Phase 183. Make related-test answers reliable and honest, including bounded no-test-found cases. | Related-test responses identify evidence-backed tests, avoid unsupported claims, and provide practical verification commands. |
| P0-BB-048 | AnythingLLM UI replay expansion | Approved as Phase 184. Expand UI-level proof for representative Priority 0 prompt families. | Selected prompts produce useful chat answers in the AnythingLLM UI or actionable classified failures. |
| P0-BB-049 | Contextless agent audit pack | Approved as Phase 185. Package bounded contextless blind-agent validation as a reusable audit workflow. | A new contextless agent can run the audit process from documentation and produce comparable scoring artifacts. |
| P0-BB-050 | Founder testing handoff refresh | Approved as Phase 186. Refresh founder-facing testing guidance after Phases 172 through 185. | A first-time tester can run the current chat-quality path through AnythingLLM with minimal setup ambiguity. |
| P0-BB-051 | Multi-fixture prompt parity matrix | Approved as Phase 187. Compare supported prompt families across git, non-git, and non-Coinbase fixtures. | Each selected prompt family has pass/fail parity, fixture-specific deltas, mutation proof, and clear next action. |
| P0-BB-052 | WSL/AnythingLLM runtime environment hardening | Approved as Phase 188. Improve diagnostics for API key, port, proxy, gateway, and Bash/Windows boundary failures. | Failed live validation identifies the failing surface, likely cause, and next recovery command without session history. |
| P0-BB-053 | Evidence boundary schema gate | Approved as Phase 189. Validate structured evidence fields and semantic boundaries before accepting chat answers. | Malformed or ambiguous evidence boundaries fail validation before being presented as successful chat-quality results. |
| P0-BB-054 | Unsupported scope refusal quality | Approved as Phase 190. Make unsupported or oversized requests fail with useful guidance instead of vague fallback answers. | Unsupported requests produce actionable chat-visible guidance without mutation or workflow misrouting. |
| P0-BB-055 | Prompt family drift detection | Approved as Phase 191. Detect founder-prompt drift away from current skills, router triggers, or workflow coverage. | Drift is visible, classified, and tied to prompt governance, workflow repair, or new skill/tool proposals. |
| P0-BB-056 | Chat answer scoring automation V2 | Approved as Phase 192. Strengthen automated comparison between blind baselines and local chat answers. | Evaluations produce repeatable scores and repair guidance while preserving live local-stack proof. |
| P0-BB-057 | Skill registry readiness review | Approved as Phase 193. Audit whether current skills are small, deterministic, discoverable, testable, and scalable. | A skill-readiness report identifies keep, split, merge, retire, defer, and scaling actions. |
| P0-BB-058 | Skill authoring pipeline V2 | Approved as Phase 194. Make new L1/L2 skill creation repeatable with eval gates by default. | New skill creation follows a testable pipeline with explicit gates and no manual prompt injection requirement. |
| P0-BB-059 | Release candidate founder trial pack | Approved as Phase 195. Package validated chat-quality prompts, setup, expected behavior, limits, and feedback capture. | The founder can run the trial pack without session history and provide structured feedback tied to the roadmap. |
| P0-BB-060 | V1 product readiness reassessment | Approved as Phase 196. Reassess whether current chat quality is ready for broader V1 founder beta. | The readiness decision is evidence-backed, current, and tied to the next approved phase needs. |

## Execution Plan

Work the backlog in the same order as the active roadmap unless the founder explicitly changes priority.

1. Current approved Phase 157-162 batch is complete.
2. Use the Phase 157-171 reports as the active field-test and chat-quality proof chain.
3. Keep using the stable release gate, founder smoke suite, Phase 156 final decision, Phase 170 refresh, and Phase 171 handler-branch repair as the active proof floor.
4. Work approved Phases 175-196 in order, using blind-baseline-first testing and live gateway/AnythingLLM validation.
5. Do not begin advanced refactor work during this batch.

## Stop Conditions

Stop and update the roadmap before continuing if:

- The repair requires a new workflow rather than extending an existing single path.
- The local model cannot meet the blind baseline because a missing tool or skill is required.
- The prompt is broader than the active phase.
- The blind baseline exposes a product expectation not represented in the current roadmap.
- Repairs would weaken safety, approval, mutation, or fixture-protection boundaries.

## Next Action

Work Phase 177 next. Do not begin advanced refactor work without an approved roadmap phase.

## Completed Work

`P0-BB-001` completed in Phase 116. Proof lives in:

- `runtime/phase116_code_quality_prompt_cases.json`
- `runtime/phase116_code_quality_blind_baselines.json`
- `runtime-state/phase116/code-quality-local-eval.json`
- `runtime-state/phase116/code-quality-comparison.json`

Phase 116 final comparison result: `status=passed`, `response_count=20`, `passed_response_count=20`, `critical_finding_count=0`, and `high_finding_count=0`.

`P0-BB-002` completed in Phase 117. Proof lives in:

- `runtime/phase117_defect_diagnosis_prompt_cases.json`
- `runtime/phase117_defect_diagnosis_blind_baselines.json`
- `runtime-state/phase117/defect-diagnosis-prompt-cases.json`
- `runtime-state/phase117/defect-diagnosis-blind-baselines.json`
- `runtime-state/phase117/defect-diagnosis-local-eval.json`
- `runtime-state/phase117/defect-diagnosis-comparison.json`

Phase 117 final comparison result: `status=passed`, `response_count=20`, `passed_response_count=20`, `critical_finding_count=0`, `high_finding_count=0`, and `recommended_next_repairs=[]`.

`P0-BB-003` completed in Phase 118. Proof lives in:

- `runtime/phase118_engineering_judgment_prompt_cases.json`
- `runtime/phase118_engineering_judgment_blind_baselines.json`
- `runtime-state/phase118/engineering-judgment-prompt-cases.json`
- `runtime-state/phase118/engineering-judgment-blind-baselines.json`
- `runtime-state/phase118/engineering-judgment-local-eval.json`
- `runtime-state/phase118/engineering-judgment-comparison.json`

Phase 118 final comparison result: `status=passed`, `response_count=20`, `passed_response_count=20`, `critical_finding_count=0`, `high_finding_count=0`, and `recommended_next_repairs=[]`.

`P0-BB-004` completed in Phase 119. Proof lives in:

- `runtime/phase119_delivery_mentorship_prompt_cases.json`
- `runtime/phase119_delivery_mentorship_blind_baselines.json`
- `runtime-state/phase119/delivery-mentorship-prompt-cases.json`
- `runtime-state/phase119/delivery-mentorship-blind-baselines.json`
- `runtime-state/phase119/delivery-mentorship-local-eval.json`
- `runtime-state/phase119/delivery-mentorship-comparison.json`

Phase 119 final comparison result: `status=passed`, `response_count=20`, `passed_response_count=20`, `critical_finding_count=0`, `high_finding_count=0`, `gap_categories={}`, and `recommended_next_repairs=[]`.

`P0-BB-005` completed in Phase 120. Proof lives in:

- `runtime/baseline_corpus.json`
- `runtime-state/baseline-corpus/phase120-baseline-corpus-report.json`
- `README.baseline-corpus.md`
- `docs/examples/baseline-corpus.md`

Phase 120 final governance result: `status=passed`, `entry_count=4`, `stable_entry_count=4`, and `error_count=0`.

`P0-BB-006` completed in Phase 121. Proof lives in:

- `runtime/anythingllm_answer_usefulness_contract.json`
- `runtime-state/anythingllm-answer-usefulness/phase121-answer-usefulness-report.json`
- `README.anythingllm-answer-usefulness.md`
- `docs/examples/anythingllm-answer-usefulness.md`

Phase 121 final answer-usefulness result: `status=passed`, `entry_count=4`, `checked_case_count=40`, and `error_count=0`.

`P0-BB-007` completed in Phase 122. Proof lives in:

- `runtime/holdout_prompt_bank.json`
- `runtime-state/holdout-prompt-bank/phase122-holdout-prompt-bank-report.json`
- `README.holdout-prompt-bank.md`
- `docs/examples/holdout-prompt-bank.md`

Phase 122 final holdout-bank result: `status=passed`, `entry_count=4`, `holdout_case_count=8`, `holdout_response_count=16`, and `error_count=0`.

`P0-BB-008` completed in Phase 123. Proof lives in:

- `vllm_agent_gateway/acceptance/failure_taxonomy.py`
- `vllm_agent_gateway/acceptance/priority0_gap_taxonomy.py`
- `scripts/validate_priority0_gap_taxonomy.py`
- `runtime-state/priority0-gap-taxonomy/phase123-priority0-gap-taxonomy-report.json`
- `README.priority0-gap-taxonomy.md`
- `docs/examples/priority0-gap-taxonomy.md`

Phase 123 final gap-taxonomy result: `status=passed`, `comparison_count=4`, `finding_count=0`, `highest_severity=none`, and `error_count=0`.

`P0-BB-009` completed in Phase 124. Proof lives in:

- `runtime/output_format_parity_cases.json`
- `vllm_agent_gateway/acceptance/output_format_parity.py`
- `scripts/validate_output_format_parity_live.py`
- `runtime-state/output-format-parity/phase124-output-format-parity-live.json`
- `README.output-format-parity.md`
- `docs/examples/output-format-parity.md`

Phase 124 final output-format parity result: `status=passed`, `case_count=8`, surfaces `gateway` and `anythingllm`, target roots `/mnt/c/coinbase_testing_repo_frozen_tmp` and `/mnt/c/coinbase_testing_repo_frozen_tmp.github`, `runtime_changed_files=[]`, `target_changed_files=[]`, and `target_git_changed={}`.

`P0-BB-010` completed in Phase 125. Proof lives in:

- `runtime/founder_feedback_loop_cases.json`
- `vllm_agent_gateway/acceptance/founder_feedback_loop.py`
- `scripts/validate_founder_feedback_loop_live.py`
- `runtime-state/founder-feedback-loop/phase125-founder-feedback-loop-live.json`
- `README.founder-feedback-loop.md`
- `docs/examples/founder-feedback-loop.md`

Phase 125 final founder-feedback-loop result: `status=passed`, `case_count=4`, decision kinds `baseline_prompt_candidate`, `holdout_prompt_candidate`, `repair_followup`, and `rejected_finding`, surfaces `gateway` and `anythingllm`, target roots `/mnt/c/coinbase_testing_repo_frozen_tmp` and `/mnt/c/coinbase_testing_repo_frozen_tmp.github`, `runtime_changed_files=[]`, `target_changed_files=[]`, and `target_git_changed={}`. Full Bash regression passed with `691 passed`, `4 skipped`, and `23 deselected`.

`P0-BB-011` completed in Phase 126. Proof lives in:

- `runtime/anythingllm_ui_prompt_cases.json`
- `vllm_agent_gateway/anythingllm_ui_e2e.py`
- `scripts/validate_anythingllm_ui_e2e.py`
- `runtime-state/anythingllm-ui/phase126-corpus-ui-usefulness.json`
- `README.anythingllm-ui-e2e.md`
- `docs/examples/anythingllm-ui-e2e.md`

Phase 126 final corpus-wide UI usefulness result: `status=passed`, `case_count=8`, stable families `phase116_code_quality`, `phase117_defect_diagnosis`, `phase118_engineering_judgment`, and `phase119_delivery_mentorship`, target roots `/mnt/c/coinbase_testing_repo_frozen_tmp` and `/mnt/c/coinbase_testing_repo_frozen_tmp.github`, all cases `stream_chat_seen=true`, all screenshot statuses `passed`, all stable answer-usefulness statuses `passed`, and `fixture_unchanged=true`. Full Bash regression passed with `700 passed`, `4 skipped`, and `23 deselected`.

`P0-BB-012` completed in Phase 127. Proof lives in:

- `runtime/fresh_local_model_drift_cases.json`
- `vllm_agent_gateway/acceptance/fresh_local_model_drift.py`
- `scripts/validate_fresh_local_model_drift.py`
- `runtime-state/fresh-local-model-drift/phase127/phase127-fresh-local-model-drift-report.json`
- `README.fresh-local-model-drift.md`
- `docs/examples/fresh-local-model-drift.md`

Phase 127 final fresh-drift result: `status=passed`, `family_count=4`, `selected_case_count=8`, `response_count=16`, `passed_response_count=16`, `failed_family_count=0`, `critical_finding_count=0`, `high_finding_count=0`, `gap_categories={}`, target roots `/mnt/c/coinbase_testing_repo_frozen_tmp` and `/mnt/c/coinbase_testing_repo_frozen_tmp.github`, routes `gateway` and `anythingllm`, and `drift_status=no_drift_detected`. Full Bash regression passed with `711 passed`, `4 skipped`, and `23 deselected`.

`P0-BB-013` completed in Phase 128. Proof lives in:

- `runtime/prompt_tightening_recommendation_policy.json`
- `vllm_agent_gateway/acceptance/prompt_tightening_recommendations.py`
- `scripts/validate_prompt_tightening_recommendations.py`
- `runtime-state/prompt-tightening-recommendations/phase128/phase128-prompt-tightening-recommendations-report.json`
- `README.prompt-tightening-recommendations.md`
- `docs/examples/prompt-tightening-recommendations.md`

Phase 128 final prompt-tightening result: `status=passed`, `candidate_count=1`, `decision_status_counts={"accepted":0,"pending_review":1,"rejected":0}`, `trigger_reason_counts={"low_confidence_pass":1}`, `suggestion_class_counts={"output_contract":1}`, and `applied_prompt_catalog_change_count=0`. The single pending candidate is `PTR-phase117_defect_diagnosis-DD117-009`; no prompt catalog was changed and no rerun proof was accepted before approval. Full Bash regression passed with `724 passed`, `4 skipped`, and `23 deselected`.

`P0-BB-014` completed in Phase 129. Proof lives in:

- `runtime/skill_tool_coverage_gap_policy.json`
- `vllm_agent_gateway/acceptance/skill_tool_coverage_gap.py`
- `scripts/validate_skill_tool_coverage_gap.py`
- `runtime-state/skill-tool-coverage-gap/phase129/phase129-skill-tool-coverage-gap-report.json`
- `README.skill-tool-coverage-gap.md`
- `docs/examples/skill-tool-coverage-gap.md`

Phase 129 final skill/tool coverage gap result: `status=passed`, `skill_tool_finding_count=0`, `gap_candidate_count=0`, `prompt_tightening_candidate_count=1`, `implemented_coverage_entry_count=38`, and `new_capability_required=false`. Current evidence does not require a new deterministic skill or tool before the stable chat-quality release gate. Full Bash regression passed with `733 passed`, `4 skipped`, and `23 deselected`.

`P0-BB-015` completed across Phases 130 and 132. Proof lives in:

- `runtime/stable_chat_quality_release_policy.json`
- `vllm_agent_gateway/acceptance/stable_chat_quality_release.py`
- `scripts/validate_stable_chat_quality_release.py`
- `runtime-state/stable-chat-quality-release/phase130/phase130-stable-chat-quality-release-report.json`
- `README.stable-chat-quality-release.md`
- `docs/examples/stable-chat-quality-release.md`

Final stable chat-quality release result after blocker closure and rerun: `status=passed`, `readiness=ready_for_founder_testing`, `gate_count=11`, and `blocker_count=0`.

`P0-BB-016` completed in Phase 131. Proof lives in:

- `runtime/stable_release_blocker_closure_policy.json`
- `vllm_agent_gateway/acceptance/stable_release_blocker_closure.py`
- `scripts/validate_stable_release_blocker_closure.py`
- `runtime-state/stable-release-blocker-closure/phase131/phase131-stable-release-blocker-closure-report.json`
- `README.stable-release-blocker-closure.md`
- `docs/examples/stable-release-blocker-closure.md`

Phase 131 final closure result: unresolved release blockers were closed without weakening the Phase 130 gate, and Phase 130 reran with `readiness=ready_for_founder_testing`.

`P0-BB-017` completed in Phase 133. Proof lives in:

- `README.getting-started.md`
- `README.founder-field-tests.md`
- `docs/examples/anythingllm-founder-testing.md`

Phase 133 final handoff result: first-time founder-testing docs point to the current stable release proof, remove stale blocked-release instructions, and provide a minimal AnythingLLM smoke path.

`P0-BB-018` completed in Phase 134. Proof lives in:

- `runtime-state/founder-field-tests/phase134-founder-smoke.json`
- `runtime-state/founder-field-tests/phase134-founder-smoke.md`
- `README.anythingllm-founder-smoke.md`
- `docs/examples/anythingllm-founder-smoke.md`

Phase 134 final founder-smoke result: `status=passed`, `passed=4`, `failed=0`, AnythingLLM preflight passed, and no protected fixture mutation was accepted.

`P0-BB-019` completed in Phase 135. Proof lives in:

- `runtime-state/founder-smoke-feedback/phase135/phase135-founder-smoke-feedback.json`
- `README.founder-smoke-feedback.md`
- `docs/examples/founder-smoke-feedback.md`

Phase 135 final feedback result: all four smoke cases remained useful and produced zero actionable feedback items requiring repair.

`P0-BB-020` completed across Phases 136 through 156. Final proof lives in:

- `runtime-state/chat-quality-release-snapshot/phase136/phase136-chat-quality-release-snapshot.json`
- `runtime-state/release-notes/phase146/phase146-release-notes-report.json`
- `runtime-state/external-tester-dry-run/phase147/phase147-external-tester-dry-run.json`
- `runtime-state/contextless-audit-scorecard/phase149/phase149-contextless-audit-scorecard-report.json`
- `runtime-state/current-model-compatibility-matrix/phase150/phase150-current-model-compatibility-matrix-report.json`
- `runtime-state/skill-tool-selection-explainability-e2e/phase151/phase151-skill-tool-selection-explainability-e2e-report.json`
- `runtime-state/anythingllm-conversation-state-isolation/phase152/phase152-anythingllm-conversation-state-isolation-report.json`
- `runtime-state/stable-release-reset-rehearsal/phase153/phase153-live-report.json`
- `runtime-state/model-swap-smoke-probe/phase154/phase154-model-swap-smoke-probe-report.json`
- `runtime-state/v1-product-readiness-review/phase155/phase155-v1-product-readiness-review-report.json`
- `runtime-state/v1-stable-release-decision/phase156/phase156-v1-stable-release-decision-report.json`
- `README.v1-product-readiness-review.md`
- `README.v1-stable-release-decision.md`
- `docs/examples/v1-product-readiness-review.md`
- `docs/examples/v1-stable-release-decision.md`

Phase 156 final release decision result: `status=passed`, `decision=release_for_founder_testing`, `release_blocker_count=0`, `evidence_link_count=6`, `doc_count=7`, `limitation_count=6`, `scope_count=6`, `rollback_path_present=true`, and `next_roadmap_batch_present=true`. Full Bash regression passed with `972 passed`, `4 skipped`, and `23 deselected`.

`P0-BB-021` completed in Phase 157. Proof lives in:

- `runtime/founder_field_round1_policy.json`
- `vllm_agent_gateway/acceptance/founder_field_round1.py`
- `scripts/validate_founder_field_round1.py`
- `runtime-state/founder-field-round1/phase157/phase157-founder-field-run.json`
- `runtime-state/founder-field-round1/phase157/phase157-founder-field-run.md`
- `runtime-state/founder-field-round1/phase157/phase157-founder-field-round1-report.json`
- `runtime-state/founder-field-round1/phase157/phase157-founder-field-round1-report.md`
- `README.founder-field-round1.md`
- `docs/examples/founder-field-round1.md`

Phase 157 final founder-field result: `status=passed`, `quality_status=advisory`, `case_count=30`, `pass_case_count=16`, `advisory_case_count=14`, `blocker_case_count=0`, `target_root_count=2`, `workflow_count=3`, and `phase158_required=true`. The underlying live field runner returned 30 passed prompts and 0 failed prompts through AnythingLLM.
