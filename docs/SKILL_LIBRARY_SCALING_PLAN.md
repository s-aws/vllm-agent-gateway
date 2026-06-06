# Skill Library Scaling Plan

Status: approved post-V1 scope. Phase 29 through Phase 71 are complete through Batch D live proof, promotion, founder field-suite expansion, skill-library release-gate integration, non-Coinbase fixture generalization, AnythingLLM feedback-loop proof, release-gate profile splitting, latest-run inspection, prompt-catalog governance, and browser-rendered AnythingLLM Desktop UI proof.

## Problem

V1 proves that natural-language requests can route through the controller, select registered skills, use bounded tools, return chat-visible answers, and validate against localhost, gateway, AnythingLLM, and both frozen Coinbase fixtures.

The next product risk is scale. Adding skills one at a time without a strict admission path would recreate the earlier failure mode: lots of theoretical skill files that do not prove runtime usefulness.

The goal is to add more small deterministic L1/L2 skills while preserving one controller-owned runtime path:

```text
natural request
-> workflow router
-> registry metadata shortlist
-> selected skill body only when supported
-> existing workflow/tool path
-> eval artifact
-> live gateway and AnythingLLM proof
```

## Non-Goals

- Do not resume broad single-path refactor orchestration in this scope.
- Do not add a new runtime for skills.
- Do not require users to name or paste skills.
- Do not create parallel implementations of existing workflow behavior.
- Do not add skills that lack an eval case and live-suite mapping.
- Do not add apply-mode repository mutation to frozen fixtures.

## Definition Of A Small Deterministic Skill

A skill is eligible for this track only when all of these are true:

- It maps to one prompt family or one bounded artifact transformation.
- It has one unique `capability_contract.route_key`.
- It uses an existing workflow unless the roadmap explicitly approves a new workflow.
- It declares a mutation policy before implementation.
- It has at least one eval case in `runtime/skill_evals.json`.
- It can be judged from deterministic artifacts and chat-visible output.
- It blocks or asks for exact details when the request is outside its supported pattern.
- It can be validated on `/mnt/c/coinbase_testing_repo_frozen_tmp` and `/mnt/c/coinbase_testing_repo_frozen_tmp.github`.

## Admission Gates

Every new skill must pass these gates in order.

1. **Problem Definition Gate**

   Define the user prompt family, failure this skill solves, expected workflow, expected artifact, allowed tools, and unsupported boundary.

2. **Eval-First Gate**

   Add the eval case before adding the skill body. The eval case must include prompt family, natural prompt, expected workflow, expected artifacts, mutation policy, and live-suite mapping.

3. **Registry Gate**

   Add skill metadata only after the eval case exists. Registry validation must reject duplicate skill IDs, duplicate route keys, unknown eval cases, unsupported mutation policies, and missing docs links.

4. **Skill Body Gate**

   Add the `SKILL.md` body with frontmatter, deterministic procedure, output contract, stop conditions, and no tool claims outside the registry.

5. **Selector Gate**

   Prove the router selects the new skill only for matching prompt families and does not select it for unrelated workflows.

6. **Artifact Gate**

   Prove the workflow produces the expected artifact with bounded source references, confidence or gaps, and no unsupported mutation.

7. **Live Gate**

   Run Bash-side validation through localhost `8000`, gateway/router ports, AnythingLLM, and both frozen fixtures.

8. **Regression Gate**

   Run focused regression, then full regression after any code change.

9. **Mutation Gate**

   Verify watched fixture hashes, invariant text, and Windows Git status for the git-enabled frozen fixture.

10. **Documentation Gate**

   Update the relevant backlog, feature README, examples if needed, docs index, and canonical roadmap proof.

## Batch Rule

Add skills in small batches.

- Batch size: 3 to 5 prompt families.
- Stop the batch on the first failed live gate.
- Do not add another skill to compensate for a failed skill.
- A batch is complete only when every skill has eval, registry, selector, artifact, live, regression, mutation, and documentation proof.

## Proposed Phase 29: Scaling Harness Hardening

Goal: make skill-batch admission repeatable before adding more prompt families.

Implementation tasks:

- Add a skill-batch manifest shape for proposed batches.
- Extend the eval runner to validate a named skill batch.
- Add a report that lists each skill, route key, eval case, workflow, artifact, mutation policy, and live-suite mapping.
- Add a dry-run command that proves a batch is ready before runtime registration changes.
- Add regression tests for duplicate route keys across batch proposals.
- Add regression tests for missing eval cases, missing skill bodies, and unsupported mutation policies.

Acceptance proof:

- focused skill-batch regression passes
- `python scripts/validate_skill_evals.py` passes
- docs-index check passes
- no live validation required unless runtime selection changes

## Phase 30: L1 Read-Only Expansion Batch A

Status: complete. The canonical roadmap records implementation and live validation proof.

Goal: add the next common read-only coding-agent prompt families.

Candidate prompt families:

1. `L1-012: Locate Endpoint Or Route Handler`
   - Example: "Find where POST /orders is handled. Read only."
   - Expected workflow: `code_investigation.plan`
   - Expected artifact: `endpoint_route_lookup`

2. `L1-013: Locate Error Or Log Message Source`
   - Example: "Find where this error message is emitted. Read only."
   - Expected workflow: `code_investigation.plan`
   - Expected artifact: `message_source_lookup`

3. `L1-014: Summarize A Module Or File`
   - Example: "Summarize what this module is responsible for. Read only."
   - Expected workflow: `code_investigation.plan`
   - Expected artifact: `module_summary`

4. `L1-015: Find Data Model Or Schema`
   - Example: "Find the model/schema for stealth order records. Read only."
   - Expected workflow: `code_investigation.plan`
   - Expected artifact: `data_model_lookup`

5. `L1-016: Find Imports Or Dependencies`
   - Example: "Find what this file imports and what depends on it. Read only."
   - Expected workflow: `code_context.lookup`
   - Expected artifact: `dependency_lookup`

Acceptance proof:

- each skill has one eval case and unique route key
- full L1 live suite includes these cases or a new L1 expansion suite does
- gateway and AnythingLLM pass on both frozen fixtures
- chat-visible `format_a` includes useful inline answers
- JSON output selector still works for one representative new case

## Phase 31: L1 Read-Only Expansion Batch B

Status: complete. The canonical roadmap records implementation and live validation proof.

Goal: add additional read-only skills that users frequently ask before editing code.

Candidate prompt families:

1. `L1-017: Identify Test Coverage Gaps`
   - Expected artifact: `coverage_gap_summary`

2. `L1-018: Find Documentation For Behavior`
   - Expected artifact: `documentation_lookup`

3. `L1-019: Locate CLI Or Script Entrypoint`
   - Expected artifact: `cli_entrypoint_lookup`

4. `L1-020: Explain Configuration Runtime Effect`
   - Expected artifact: `configuration_effect_summary`

5. `L1-021: Find Recent Or Local Changes`
   - Expected artifact: `local_change_summary`
   - Git-enabled fixture only for the git-specific proof; non-git fixture must return a clear unsupported or limited answer.

Acceptance proof:

- same gates as Phase 30
- non-git and git-enabled fixture behavior is explicitly different where Git is required
- unsupported Git-specific requests on non-git fixtures do not hallucinate history
- gateway and AnythingLLM passed for `L1-017` through `L1-021` on both frozen fixtures
- skill registry now includes `31` validated skills and eval catalog now includes `30` cases

## Phase 32: L2 Diagnostic Expansion Batch A

Status: complete. The canonical roadmap records implementation and live validation proof.

Goal: add multi-step read-only prompt families that still avoid implementation.

Candidate prompt families:

1. `L2-006: Diagnose Runtime Error Or Stack Trace`
   - Expected artifact: `runtime_error_diagnosis`
   - Route: `workflow_router.plan` to `code_investigation.plan`
   - Output must include observed error, likely cause, evidence files, next inspection steps, risks, gaps, verification commands, and mutation policy.

2. `L2-007: Map Request Or Data Flow`
   - Expected artifact: `request_flow_map`
   - Route: `workflow_router.plan` to `code_investigation.plan`
   - Output must include target flow, ordered flow steps, participating files, related tests, risks, gaps, verification commands, and mutation policy.

3. `L2-008: Compare Two Candidate Code Paths`
   - Expected artifact: `code_path_comparison`
   - Route: `workflow_router.plan` to `code_investigation.plan`
   - Output must include candidate paths, bounded evidence, comparison summary, recommended path only when evidence supports it, risks, gaps, source refs, and mutation policy.

4. `L2-009: Identify Minimal Safe Change Surface`
   - Expected artifact: `change_surface_summary`
   - Must stop before implementation packet generation.
   - Route: `workflow_router.plan` to `code_investigation.plan`
   - Output must include files needing review, related tests, risk level, implementation status, gaps, verification commands, and mutation policy.

Implementation plan:

1. Add four skills with one unique route key each and no allowed tools.
2. Add four eval cases and map them to `workflow_router_l2_suite`.
3. Add deterministic router rules that reject apply, mutation, broad refactor, and approval-bypass language.
4. Add four `code_investigation.plan` artifact builders that consume existing bounded evidence.
5. Add default `format_a` renderers so the user sees the answer in chat without opening artifact files.
6. Extend the L2 live-suite validator with `L2-006` through `L2-009`.
7. Add focused regression for route selection, artifact content, renderer markers, and no source mutation.
8. Run batch dry-run, skill eval catalog, Bash gateway live suite, AnythingLLM live suite, full regression, docs index, and protected fixture mutation checks.

Acceptance proof:

- L2 live suite covers every new case
- each case returns root cause or flow hypothesis, evidence files, risks, gaps, and verification commands
- no repository mutation
- no approval bypass
- gateway and AnythingLLM passed for `L2-006` through `L2-009` on both frozen fixtures
- skill registry now includes `35` validated skills and eval catalog now includes `34` cases

## Phase 33: Draft-Only Expansion Readiness

Status: complete. Founder approval was received for Batch A, and Phase 34 implemented the approved scope.

Goal: decide whether to expand beyond read-only skills into more draft-only L1/L2 skills.

Readiness finding:

- The product is ready for one narrow draft-only expansion batch after founder approval.
- The product is not ready for broad refactor orchestration, automatic apply, multi-file mutation, or model-invented patches.
- Existing V1 draft-only skills prove the shared packet path, but new subfamilies must still pass eval, selector, artifact, live, regression, and mutation gates.
- All draft-only expansions must continue through `execution_planning.plan` and the existing `implementation.workflow`; do not add another edit runtime.

Recommended Batch A after approval:

1. `D1-004: Draft Small Config Default Test`
   - Expected artifact: `small_unit_test_proposal`
   - Artifact subkind: `config_default_test`
   - Required exact inputs: config key or symbol, expected value, target repo, draft-only/no-mutation intent
   - Block when: expected value, target symbol, or candidate test file cannot be bounded from evidence

2. `D1-005: Draft Small Error Message Assertion Test`
   - Expected artifact: `small_unit_test_proposal`
   - Artifact subkind: `message_assertion_test`
   - Required exact inputs: exact message text, expected emitter or behavior, target repo, draft-only/no-mutation intent
   - Block when: message source is not found or the assertion requires behavior design

3. `D1-006: Draft Small Test Assertion Update`
   - Expected artifact: `small_unit_test_proposal`
   - Artifact subkind: `test_assertion_update`
   - Required exact inputs: test file or test node, old expected value, new expected value, target repo, draft-only/no-mutation intent
   - Block when: the old assertion is not found exactly once or the request implies production-code changes

Rejected from Batch A:

- broad advanced refactor prompts
- automatic apply to source repositories
- disposable-copy apply expansion
- dependency-injection or constructor-parameter edits that require behavior design
- multi-file code edits

Acceptance proof:

- every new prompt has an eval case before a skill body
- every registry entry has a unique route key and `draft_only` mutation policy
- selector tests prove matching and non-matching behavior
- generated draft artifacts include exact file, operation, safety checks, verification command, blockers, and `Source mutation: false`
- generated draft artifacts do not alter protected fixtures
- live Bash gateway and AnythingLLM tests pass on both frozen Coinbase fixtures
- full regression passes after code changes

## Phase 34: Draft-Only Expansion Batch A

Status: complete.

Goal: implement `D1-004`, `D1-005`, and `D1-006` without adding a second edit path.

Implementation tasks:

- Add eval cases and live-suite mappings first.
- Add registry metadata after eval validation exists.
- Add skill bodies with deterministic procedures, output contracts, stop conditions, and no unlisted tool claims.
- Add router rules that require draft-only or no-mutation intent.
- Reuse the existing `small_unit_test_proposal` packet path and add only bounded subkind handling.
- Render each proposal in default `format_a`.
- Add focused regression for selection, blocking, artifact content, chat rendering, downstream draft path, and source non-mutation.
- Run batch dry-run, skill eval catalog validation, Bash gateway live validation, AnythingLLM live validation, full regression, docs index, and protected fixture mutation checks.

Acceptance proof:

- `D1-004`, `D1-005`, and `D1-006` pass the full admission gates
- unsupported variants block with exact missing-detail reasons
- gateway and AnythingLLM pass on both frozen fixtures
- `runtime/skills.json`, `runtime/skill_evals.json`, roadmap, docs index, and examples are updated
- skill registry now includes `38` validated skills and the eval catalog now includes `37` cases
- Phase 34 batch dry-run wrote `runtime-state/skill-batches/phase34-dry-run.json` with `3` skills, `3` eval cases, `3` route keys, and `0` errors
- skill eval catalog wrote `runtime-state/skill-evals/phase34-skill-evals.json` with `case_count=37` and `failed_count=0`
- Bash workflow-router gateway and AnythingLLM live validation passed for `D1-004` through `D1-006` on both frozen Coinbase fixtures
- watched-file sizes matched before and after live validation, and Windows Git status for `C:\coinbase_testing_repo_frozen_tmp.github` had no changed files
- full regression returned `231 passed, 1 skipped, 19 deselected`

## Phase 35: Scale Operations

Status: complete. The canonical roadmap records the implementation and validation proof.

Goal: prepare for hundreds or thousands of skills without losing determinism.

Implementation tasks:

- Add skill namespace conventions.
- Add route-key ownership checks.
- Add batch-level deprecation and replacement rules.
- Add eval coverage reporting by workflow, artifact, safety level, and prompt family.
- Add duplicate semantic-intent detection for route keys and trigger terms.
- Add a "do not admit" report for skills that overlap existing behavior.

Acceptance proof:

- registry can validate a large synthetic catalog without changing runtime behavior
- duplicate route-key and overlapping-intent fixtures fail
- eval coverage report is generated and linked from docs

Implementation completed:

- route-key namespace conventions and ownership checks
- deprecation and replacement validation
- deterministic semantic-intent overlap detection
- batch-level do-not-admit failures for overlapping proposals
- scale coverage report by workflow, artifact, safety level, mutation policy, prompt family, and route namespace

Validation proof:

- focused skill registry regression returned `36 passed`
- focused skill batch regression returned `10 passed`
- focused skill eval regression returned `5 passed`
- scale report wrote `runtime-state/skill-scale/phase35-skill-scale.json` and returned `skill_count=38`, `eval_case_count=37`, `route_key_count=38`, `do_not_admit_count=0`, and `status=passed`
- Phase 29 static fixture revalidation wrote `runtime-state/skill-batches/phase35-phase29-fixture-check.json` and returned `status=passed`
- focused skill registry, batch, and eval regression returned `51 passed`
- final skill eval catalog wrote `runtime-state/skill-evals/phase35-skill-evals.json` and returned `case_count=37`, `passed_count=37`, and `failed_count=0`
- final scale report wrote `runtime-state/skill-scale/phase35-final-skill-scale.json` and returned `status=passed`
- docs index returned `DOCS INDEX PASS`
- full regression returned `240 passed, 19 deselected`

## Phase 36: Skill Batch Proposal Workflow

Status: complete. The canonical roadmap records the implementation and validation proof.

Goal: add a controller-owned proposal workflow that can create draft skill-batch manifests from natural-language requests without mutating runtime registries.

Implementation tasks:

- Add `skill_batch.propose` to the workflow registry.
- Add a proposal workflow that writes draft batch manifests under controller artifacts only.
- Reuse existing batch, eval, and scale validators.
- Return chat-visible proposal and do-not-admit sections.
- Prove runtime registries and skill bodies are unchanged.

Acceptance proof:

- natural-language proposal request routes to the proposal workflow
- duplicate or overlapping requested skills return do-not-admit output
- draft manifests stay as artifacts until a separate approved implementation phase
- focused regression and full regression pass

Implementation completed:

- `skill_batch.propose` workflow registry entry
- direct controller endpoint and harness support for skill-batch proposals
- workflow-router natural-language routing for proposal-only skill-batch requests
- artifact-only draft skill body and batch manifest generation
- batch validation, scale validation, do-not-admit reporting, and chat-visible `format_a` rendering
- proposal tightening so ready draft skills reuse existing workflow artifacts instead of inventing unimplemented output artifacts

Validation proof:

- focused proposal regression returned `3 passed, 126 deselected`
- controller-service regression returned `110 passed, 19 deselected`
- focused skill registry, batch, and eval regression returned `51 passed`
- skill eval catalog wrote `runtime-state/skill-evals/phase36-skill-evals.json` with `case_count=37` and `failed_count=0`
- scale report wrote `runtime-state/skill-scale/phase36-skill-scale.json` with `skill_count=38`, `eval_case_count=37`, `route_key_count=38`, and `do_not_admit_count=0`
- Phase 29 static fixture revalidation wrote `runtime-state/skill-batches/phase36-phase29-fixture-check.json` and returned `status=passed`
- full regression returned `243 passed, 19 deselected`
- Bash workflow-router gateway and AnythingLLM proposal probes passed on both frozen Coinbase fixtures

## Phase 37: Approved Skill Batch Registration Workflow

Status: complete. The canonical roadmap records the implementation and validation proof.

Goal: add an approval-gated controller workflow that installs a passed proposal into the runtime skill registry without hand-editing JSON.

Implementation tasks:

- Accept a Phase 36 proposal artifact or run ID.
- Require explicit approval for runtime registry append and skill body install.
- Revalidate proposal, batch, eval, and scale reports before mutation.
- Copy approved draft skill bodies into `.qwen/skills`.
- Append approved skills and eval cases to `runtime/skills.json` and `runtime/skill_evals.json` using structured JSON updates.
- Produce before/after hashes, validation reports, and chat-visible installation output.
- Reject do-not-admit proposals, failed batch reports, missing draft skill bodies, duplicate IDs, duplicate route keys, and unimplemented output artifacts.

Acceptance proof:

- valid approved proposal installs exactly the expected skill and eval case in a controlled fixture or disposable registry copy
- rejected overlap proposal leaves runtime registries unchanged
- router selection discovers the installed skill from metadata without user skill injection
- full regression, docs index, skill eval, skill scale, and live gateway proof pass

Implementation completed:

- `skill_batch.register` workflow registry entry
- direct controller endpoint and harness support for approved skill-batch registration
- natural workflow-router approval follow-up for known proposal run IDs
- explicit approval schema requiring `approved_for_skill_registration`, `skill_batch_registration`, `runtime_registry_append=true`, `skill_body_install=true`, and approval refs
- proposal, batch, expected-artifact, registry, eval, and scale revalidation before registration is accepted
- structured copy of draft `SKILL.md` bodies into `.qwen/skills`
- structured append of skill metadata and eval cases to runtime registries
- rollback instructions, backups, before/after hash proof, chat-visible registration output, and target-repository non-mutation proof
- deterministic proposal classifier tightening so valid proposal-only phrasings execute the proposal workflow instead of stopping at plan-only mode
- Phase 37 live validator script: `scripts/validate_skill_batch_registration_live.py`

Validation proof:

- focused skill-batch controller regression returned `8 passed, 126 deselected`
- controller-service regression returned `114 passed, 19 deselected`
- focused skill registry, batch, and eval regression returned `51 passed`
- skill eval catalog wrote `runtime-state/skill-evals/phase37-skill-evals.json` with `case_count=37` and `failed_count=0`
- scale report wrote `runtime-state/skill-scale/phase37-skill-scale.json` with `skill_count=38`, `eval_case_count=37`, `route_key_count=38`, and `do_not_admit_count=0`
- docs index returned `DOCS INDEX PASS` with `48` linked docs and no orphan docs
- full regression returned `248 passed, 19 deselected`
- Bash stack restart confirmed localhost model `8000`, LLM gateway `8300`, controller `8400`, workflow-router gateway `8500`, and role ports `8101`, `8102`, and `8201` through `8205`
- Phase 37 live gateway proposal and approved registration-rejection proof passed on `/mnt/c/coinbase_testing_repo_frozen_tmp` with run IDs `workflow-router-20260605T151615492958Z` and related registration rejection proof
- Phase 37 live gateway proposal and approved registration-rejection proof passed on `/mnt/c/coinbase_testing_repo_frozen_tmp.github` with run IDs `workflow-router-20260605T151619648829Z` and related registration rejection proof
- Phase 37 AnythingLLM proposal proof passed on both frozen fixtures with `ANYTHINGLLM_API_KEY` bridged into Bash through `WSLENV`
- controlled-copy registration regression installed `feature-flag-locator` and `feature_flag_lookup`, then proved metadata-only route selection could discover the installed skill without user skill injection

## Phase 38: Registered Skill Eval Promotion Workflow

Status: complete. The canonical roadmap records the implementation and validation proof.

Goal: add a controller-owned promotion workflow that turns registered draft skills into validated skills only after focused eval, live gateway, AnythingLLM, and mutation-proof gates pass.

Reason this is the next missing scaling feature: Phase 37 can register draft skills safely, but a large skill library also needs a deterministic path from `eval_status=draft` to `eval_status=validated`. Without promotion gates, the registry can accumulate draft skills that route in production before enough live proof exists.

Required product behavior:

- add one workflow: `skill_eval.promote`
- add direct endpoint `/v1/controller/skill-evals/promotions`
- accept `skill_ids` or a Phase 37 registration run ID, then normalize to one sorted skill list
- require explicit approval: `approved_for_skill_promotion`, `skill_eval_promotion`, `eval_status_update=true`, and non-empty approval refs
- verify skill body, registry entry, eval case, route key, workflow ownership, mutation policy, expected artifact, and live-suite mapping
- update only `runtime/skills.json` in the first implementation by setting `eval_status=validated` and marking localhost, gateway, and AnythingLLM eval fields as `passed`
- refuse promotion if proof fails, approval is missing, live mappings are missing, semantic overlap appears, or target fixtures mutate
- return chat-visible promotion status, proof artifacts, run IDs, changed runtime files, and rollback instructions

Implementation plan:

1. Inspect the exact mutable skill metadata fields.
2. Add `skill_eval.promote` to the workflow registry.
3. Add a controller workflow with approval validation, proof validation, backups, atomic JSON update, rollback-on-failure, and artifacts.
4. Add controller-service direct endpoint, harness support, summary extraction, and inline `format_a` rendering.
5. Add `scripts/validate_skill_promotion_live.py` to execute proof gates before promotion.
6. Add controlled-copy regression for success, failed proof, missing approval, missing eval case, route-selection after promotion, and no target mutation.
7. Run focused regression, full regression, docs index, metadata eval, scale, Bash gateway, AnythingLLM, and protected fixture mutation checks.
8. Update feature docs, examples, this plan, and the canonical roadmap with proof.

Acceptance proof:

- draft skill promotion passes in a controlled registry copy
- failed or incomplete proof leaves runtime registries unchanged
- promoted skill remains discoverable through metadata selection
- docs and roadmap record exact proof commands and artifacts

Stop conditions:

- promotion mutates `runtime/skill_evals.json` without an approved schema phase
- missing approval can update `eval_status`
- live-suite-eligible skills can be promoted without live proof
- proof artifacts are accepted from unapproved filesystem roots
- backups or rollback instructions are missing
- target repository files change during promotion proof

Implementation completed:

- `skill_eval.promote` workflow registry entry
- direct controller endpoint and harness support for approved skill eval promotion
- explicit approval schema requiring `approved_for_skill_promotion`, `skill_eval_promotion`, `eval_status_update=true`, and approval refs
- candidate proof validation for skill bodies, registry entries, eval cases, route keys, workflow ownership, mutation policies, expected artifacts, proof artifact roots, live-suite mappings, and mapped live proof
- structured `runtime/skills.json` update that sets `eval_status=validated` and marks `localhost_8000`, `gateway_8300`, and `anythingllm` as `passed`
- rollback instructions, backups, before/after hash proof, promotion proof plan, chat-visible promotion output, and target-repository non-mutation proof
- Phase 38 live validator script: `scripts/validate_skill_promotion_live.py`

Validation proof:

- focused promotion regression returned `5 passed, 134 deselected`
- focused skill registry, batch, and eval regression returned `51 passed`
- skill eval catalog wrote `runtime-state/skill-evals/phase38-skill-evals.json` with `case_count=37` and `failed_count=0`
- scale report wrote `runtime-state/skill-scale/phase38-skill-scale.json` with `skill_count=38`, `eval_case_count=37`, `route_key_count=38`, and `do_not_admit_count=0`
- docs index returned `DOCS INDEX PASS` with `48` linked docs and no orphan docs
- full regression returned `253 passed, 19 deselected`
- Bash stack restart confirmed localhost model `8000`, LLM gateway `8300`, controller `8400`, workflow-router gateway `8500`, and role ports `8101`, `8102`, and `8201` through `8205`
- Phase 38 live validator passed gateway and AnythingLLM read-only probes on both frozen fixtures
- Phase 38 live validator passed approved invalid-promotion rejection proof with no canonical registry, skill-body, or protected fixture mutation
- controlled-copy promotion regression changed exactly `runtime/skills.json`, left `runtime/skill_evals.json` unchanged, returned rollback instructions, and proved metadata selection could discover the promoted skill

## Phase 39: Skill Lifecycle Audit And Queue

Status: Complete.

Goal: add a read-only lifecycle audit workflow so maintainers can see which skills should be promoted, revised, deprecated, or left alone.

Implementation plan:

1. Add `skill_lifecycle.audit` as a controller-owned read-only workflow.
2. Group skills by `draft`, `validated`, and `deprecated`.
3. Detect missing skill bodies, orphan eval cases, stale eval status fields, missing proof, route conflicts, semantic overlaps, and docs gaps.
4. Emit a next-action queue with one deterministic action per skill.
5. Render chat-visible counts, blockers, and next actions.
6. Add fixture coverage for each lifecycle queue status.

Acceptance proof:

- current project registry audit passes
- synthetic fixtures prove every queue status
- no runtime registry mutation occurs
- full regression and docs index pass

Implementation completed:

- Added workflow registry entry `skill_lifecycle.audit`.
- Added controller module `vllm_agent_gateway/controllers/skill_lifecycle/audit.py`.
- Added direct endpoint `/v1/controller/skill-lifecycle/audits`.
- Added harness envelope support for `workflow=skill_lifecycle.audit`.
- Added workflow-router natural-language support without requiring a target repository path.
- Added deterministic lifecycle actions: `promote`, `keep_draft`, `revise`, `deprecate`, and `no_action`.
- Added catalog findings for orphan eval cases, missing requested skills, route-key conflicts, semantic conflicts, registry validation errors, eval status, and scale status.
- Added controller-only artifacts with runtime registry hash proof.
- Added Bash-side live validator `scripts/validate_skill_lifecycle_live.py`.

Validation proof:

- focused lifecycle regression returned `7 passed, 139 deselected`
- focused lifecycle plus promotion regression returned `12 passed, 134 deselected`
- focused registry, batch, and eval regression returned `51 passed`
- skill eval catalog wrote `runtime-state/skill-evals/phase39-skill-evals.json` with `case_count=37`, `passed_count=37`, and `failed_count=0`
- scale report wrote `runtime-state/skill-scale/phase39-skill-scale.json` with `skill_count=38`, `eval_case_count=37`, `route_key_count=38`, and `do_not_admit_count=0`
- docs index returned `DOCS INDEX PASS` with `48` linked docs and no orphan docs
- full regression returned `260 passed, 19 deselected`
- Bash stack restart confirmed localhost model `8000`, LLM gateway `8300`, controller `8400`, workflow-router gateway `8500`, and role ports `8101`, `8102`, and `8201` through `8205`
- Phase 39 live validator passed direct controller audit, gateway natural chat audit, AnythingLLM audit, and before/after mutation checks on both frozen fixtures

## Phase 40: Controlled L1/L2 Skill Expansion Batch B

Status: Complete.

Goal: add the next 3-5 small deterministic L1/L2 skills by using the proposal, registration, promotion, and audit lifecycle instead of hand-editing.

Implementation plan:

1. Select 3-5 bounded prompt families from the L1/L2 backlog.
2. Generate proposal artifacts through `skill_batch.propose`.
3. Register approved proposals through `skill_batch.register`.
4. Promote registered draft skills through `skill_eval.promote`.
5. Audit final lifecycle state through `skill_lifecycle.audit`.
6. Validate through localhost `8000`, gateway/controller ports, AnythingLLM, and both frozen fixtures.

Acceptance proof:

- every new skill has eval coverage before registration
- every promoted skill has gateway and AnythingLLM proof
- lifecycle audit reports no blocked or orphan entries for the batch
- full regression and protected fixture mutation checks pass

Implemented Batch B skills:

- `background-job-locator`
- `pytest-fixture-locator`
- `api-reference-locator`
- `agent-invariant-locator`

Implementation completed:

- `skill_batch.propose` now supports a named Phase 40 multi-skill Batch B proposal.
- The approved batch was registered through `skill_batch.register` and promoted through `skill_eval.promote`.
- Lifecycle audit returns `no_action` for all four Batch B skills.
- `scripts/validate_phase40_skill_batch_live.py` validates the batch through ports, static gates, lifecycle audit, gateway, AnythingLLM, and both frozen fixtures.

Validation proof:

- focused controller lifecycle regression returned `17 passed, 130 deselected`
- Phase 40 live validator confirmed localhost model `8000`, LLM gateway `8300`, controller `8400`, workflow-router gateway `8500`, and role ports `8101`, `8102`, and `8201` through `8205`
- Phase 40 live validator passed static eval, scale, and docs-index gates
- Phase 40 live validator passed gateway and AnythingLLM probes for all four new skills on both frozen Coinbase fixtures
- Phase 40 live validator confirmed no protected fixture mutation during live probes

## Phase 41: Skill Selector Scale And Stability Gate

Goal: prove skill selection remains deterministic and performant as the registry grows.

Implementation plan:

1. Generate synthetic registries with 100, 1,000, and 10,000 skill metadata entries.
2. Measure selection runtime and stability for representative L1/L2 requests.
3. Prove route-key collision, namespace drift, trigger conflict, and semantic-overlap fixtures fail deterministically.
4. Ensure selector benchmarks never load full skill bodies.
5. Write scale reports under `runtime-state/skill-scale/`.

Acceptance proof:

- 10,000-skill benchmark completes within a documented threshold
- repeated selection returns identical skill IDs and route keys
- collision fixtures fail deterministically
- scale report is linked from docs and roadmap

Implementation completed:

- `vllm_agent_gateway/skills/selector_scale.py` generates 100, 1,000, and 10,000 skill metadata-only catalogs.
- `scripts/validate_skill_selector_scale.py` writes durable selector-scale reports under `runtime-state/skill-scale/`.
- The selector benchmark uses in-memory metadata only and reports `body_reads_during_selection=0`.
- Negative fixtures cover duplicate route keys, unsupported route namespaces, trigger collisions, semantic overlaps, and missing eval-case coverage.

Validation proof:

- focused regression returned `3 passed` for `tests/regression/test_skill_selector_scale.py`.
- `runtime-state/skill-scale/phase41-selector-scale.json` passed with `largest_skill_count=10000`.
- the 10,000-skill representative selector run completed in `0.1595441999961622` seconds against the documented `10.0` second threshold.
- Bash-side validation wrote `runtime-state/skill-scale/phase41-bash-selector-scale.json` and completed the 10,000-skill selector run in `0.11630052898544818` seconds.
- full regression returned `264 passed, 19 deselected`.
- all five negative fixtures were rejected deterministically.

## Phase 42: Skill Deprecation And Replacement Workflow

Goal: add a controller-owned deprecation workflow so obsolete skills can be replaced without breaking deterministic routing.

Implementation plan:

1. Add `skill.deprecate` as an approval-gated controller workflow.
2. Validate replacement skill existence, replacement status, route compatibility, reason, and effective date.
3. Update only deprecated skill metadata in the first implementation.
4. Ensure normal selectors exclude deprecated skills.
5. Add rollback artifacts and lifecycle-audit integration.

Acceptance proof:

- controlled-copy deprecation changes exactly one skill to deprecated
- replacement links validate and broken links fail
- selectors exclude deprecated skills in normal routing
- lifecycle audit reports deprecated skills accurately
- full regression and docs validation pass

Implementation completed:

- `runtime/workflows.json` now includes `skill.deprecate`.
- `vllm_agent_gateway/controllers/skill_deprecation/deprecate.py` performs approval-gated deprecation with replacement validation, backups, hash proof, rollback instructions, and post-validation.
- `/v1/controller/skill-deprecations` and explicit harness-envelope `workflow=skill.deprecate` return chat-visible deprecation proof.
- selector logic excludes deprecated skills in normal routing.
- semantic-overlap checks ignore deprecated skills so replacement skills can coexist with retired skills.

Validation proof:

- focused controller regression returned `17 passed, 135 deselected` for skill deprecation, lifecycle, and promotion coverage.
- skill registry and eval regression returned `43 passed`.
- controlled-copy deprecation changed only `runtime/skills.json`.
- missing approval, missing replacement, and route-incompatible replacement requests were rejected without registry mutation.
- lifecycle audit reported a deprecated controlled-copy skill as `no_action`.
- full regression returned `271 passed, 19 deselected`.
- Bash live safety probe confirmed localhost `8000`, LLM gateway `8300`, controller `8400`, workflow-router gateway `8500`, and role ports `8101`, `8102`, and `8201` through `8205`.
- Bash live safety probe rejected an approved invalid deprecation with `replacement_skill_not_registered` and confirmed runtime registry hashes were unchanged.

## Phase 43: Skill Update And Versioning Workflow

Goal: add a controller-owned workflow for changing validated skills without hand-editing metadata, bodies, or eval cases.

Implementation plan:

1. Add `skill.update` as an approval-gated controller workflow.
2. Define update modes: metadata-only, skill-body-only, eval-case-only, and combined update with explicit file list.
3. Require semantic version bump rules and reject route-key changes unless a deprecation plan exists.
4. Generate rollback artifacts for every changed file.
5. Re-run registry, eval, scale, selector-scale, and relevant live-suite gates.

Acceptance proof:

- controlled-copy metadata update changes one skill entry and bumps patch version
- controlled-copy skill-body update changes one `SKILL.md` file and preserves frontmatter validity
- eval-case update changes one intended eval case and passes eval validation
- route-key change without deprecation plan is rejected
- rollback artifacts restore all changed files
- full regression and docs validation pass

Implementation completed:

- `runtime/workflows.json` now includes `skill.update`.
- `vllm_agent_gateway/controllers/skill_update/update.py` performs approval-gated metadata-only, skill-body-only, eval-case-only, and combined updates with semantic version enforcement.
- `/v1/controller/skill-updates` and explicit harness-envelope `workflow=skill.update` return chat-visible update proof.
- route-key changes without `deprecation_plan_ref` are rejected.
- rollback artifacts include backups for every changed registry, eval, or skill-body file.

Validation proof:

- focused controller regression returned `18 passed, 140 deselected` for skill update, deprecation, and lifecycle coverage.
- skill registry, eval, and selector-scale regression returned `46 passed`.
- docs index validation passed.
- generated eval, scale, and selector-scale reports passed; selector-scale covered `10,000` synthetic skills with zero body reads.
- controlled-copy metadata-only, skill-body-only, eval-case-only, combined rollback, and route-key rejection tests passed.
- full regression returned `277 passed, 19 deselected`.
- Bash live lifecycle guard passed across localhost `8000`, gateway/controller/role ports, AnythingLLM, and both frozen fixtures.
- Bash live Phase 43 guard rejected invalid `skill.update` route-key changes through direct controller `8400` and explicit-envelope gateway `8300` without registry, skill-body, or frozen-fixture mutation.

## Phase 44: Skill Release Gate And CI Profile

Goal: create one canonical release gate for the skill system so future agents stop hand-picking partial validation commands.

Implementation completed:

- `scripts/validate_skill_release_gate.py` now supports `--offline-only`, `--live`, and `--anythingllm`.
- Offline mode runs static skill eval, scale, selector-scale, docs-index, registry/eval/selector regression, and focused skill-controller regression gates.
- Live modes run the offline gate plus the Bash-hosted lifecycle guard; `--anythingllm` includes the AnythingLLM workspace API guard.
- Reports are written under `runtime-state/skill-release-gates/` with catalog counts, workflow counts, route namespace counts, proof validation, rerun commands, and watched-file hash summaries.
- Missing, stale, or catalog-inconsistent proof files fail deterministically.

Validation proof:

- offline release gate passed with `skill_count=42`, `eval_case_count=41`, `workflow_count=13`, and `changed_files=[]`.
- Bash `--live` release gate passed against localhost `8000`, controller/gateway/role ports, and both frozen fixtures.
- Bash `--anythingllm` release gate passed with AnythingLLM included.
- proof-validation regression rejects stale `case_count` and missing proof files.
- docs index validation passed.
- full regression returned `279 passed, 19 deselected`.

## Phase 45: Skill Discovery And Selection Explainability

Goal: make selected skill behavior inspectable so a tester can understand why a skill was chosen or skipped without reading registry JSON.

Implementation completed:

- `skill.selection.explain` now supports direct controller, explicit harness-envelope, and safe natural workflow-router chat.
- Selection explanations report selected skills, route keys, trigger hits, workflow priorities, filtered-out reasons, deprecated exclusions, and route namespace summary.
- The explanation path uses shared selector logic and reads `runtime/skills.json` metadata only.
- FormatA and JSON outputs are supported.
- The release gate now includes skill-selection controller regressions.

Validation proof:

- focused controller selection regression returned `5 passed, 158 deselected`.
- skill registry and selector-scale regression returned `42 passed`.
- direct endpoint, harness FormatA, harness JSON, and natural workflow-router chat selection explanations passed.
- controlled-copy missing `SKILL.md` body still selected from metadata, proving body-free explanation.
- controlled-copy deprecated skill appeared as excluded, not selected.
- 10,000-skill synthetic explanation passed within threshold with zero body reads.
- offline and AnythingLLM release gates passed with `workflow_count=14` and `changed_files=[]`.
- Bash live gateway and AnythingLLM selection prompts passed on both frozen fixtures with no runtime registry or fixture mutation.
- full regression returned `285 passed, 19 deselected`.

## Phase 46: Skill Pack Export, Import, And Namespace Governance

Goal: let the skill library grow as governed packs instead of one monolithic local registry.

Implementation completed:

- `skill_pack.validate` validates `skill_pack_manifest` files with pack id, version, owner, namespaces, compatibility tags, docs, skills, and eval cases.
- `skill_pack.install` is approval-gated with `approved_for_skill_pack_install`, `skill_pack_install`, `runtime_registry_append=true`, `skill_body_install=true`, and approval refs.
- Pack validation enforces owner and namespace governance before reusing the existing batch admission path.
- Pack install re-runs validation, reuses the existing batch install path, runs post-install eval and scale checks, writes rollback instructions, and records before/after hashes.
- `scripts/validate_skill_pack.py` provides a focused read-only pack validation command.
- The release gate focused controller subset now includes `skill_pack`.

Validation proof:

- focused controller pack regression returned `3 passed, 163 deselected`.
- focused skill-controller release subset returned `39 passed, 127 deselected`.
- valid controlled-copy pack installed two skills and two eval cases.
- invalid duplicate route-key pack failed before mutation.
- invalid namespace-not-owned pack failed before mutation.
- selector explanation after install returned the installed pack skill with zero body reads.
- docs-index validation passed.
- offline release gate passed with `workflow_count=16` and `changed_files=[]`.
- full regression returned `288 passed, 19 deselected`.
- Bash stack restart confirmed localhost model `8000`, LLM gateway `8300`, workflow-router gateway `8500`, controller `8400`, and role ports healthy.
- AnythingLLM release gate passed with `workflow_count=16` and `changed_files=[]`.
- direct controller `8400`, explicit-envelope gateway `8300`, and CLI pack validation passed for the Phase 46 live pack fixture with no watched runtime or frozen-fixture mutation.
- Natural-language AnythingLLM lifecycle operations were intentionally deferred at this point and completed later in Phase 49.

## Phase 47: Skill Authoring Scaffolder And Template Enforcement

Goal: reduce malformed skill proposals by generating validated skill bodies, metadata, eval cases, and docs from one approved scaffold path.

Implementation completed:

- `skill.scaffold` generates draft `SKILL.md`, registry metadata, eval cases, docs refs, validation checklist, and a skill-batch manifest from one prompt-family spec.
- The workflow requires explicit `output_artifact` selection from known artifacts and rejects missing or unknown output artifacts.
- Generated skill bodies include frontmatter and 8-step alignment notes.
- Generated batch manifests are immediately checked through existing skill-batch validation.
- Overlaps and duplicate route keys return `do_not_admit`; runtime registries are not mutated.
- The release gate focused controller subset now includes `skill_scaffold`.

Validation proof:

- focused controller scaffold regression returned `3 passed, 166 deselected`.
- focused skill-controller release subset returned `42 passed, 127 deselected`.
- valid scaffold produced a batch manifest accepted by skill-batch validation.
- generated skill body frontmatter validated.
- generated eval case mapped to `skill_registry_contract`.
- overlapping scaffold returned `do_not_admit` with overlapping semantic intent.
- missing explicit output artifact returned `missing_prompt_family_spec_field`.
- docs-index validation passed.
- offline release gate passed with `workflow_count=17` and `changed_files=[]`.
- full regression rerun returned `291 passed, 19 deselected`.
- AnythingLLM release gate passed with `workflow_count=17` and `changed_files=[]`.
- direct controller `8400` and explicit-envelope gateway `8300` scaffold validation passed for the Phase 47 live fixture with no watched runtime or frozen-fixture mutation.
- Natural-language AnythingLLM lifecycle/scaffold operations were intentionally deferred at this point and completed later in Phase 49.

## Phase 48: Skill Eval Mutation And Fault Injection Suite

Goal: prove registry, eval, selector, lifecycle, and release-gate checks fail when they should fail.

Implementation completed:

- `scripts/validate_skill_mutations.py` runs disposable-copy mutation fixtures and writes durable reports.
- Covered mutations are duplicate route key, missing skill body, broken frontmatter, unknown workflow, unknown tool, missing eval case, stale live proof, deprecated replacement breakage, and route namespace drift.
- Each mutation records expected and observed failure codes, errors, disposable root cleanup status, and protected fixture mutation status.
- Mutation coverage is included in the release gate.

Validation proof:

- mutation regression returned `1 passed`.
- direct mutation command returned `SKILL MUTATION PASS` with `mutation_count=9`, `passed_count=9`, `failed_count=0`, all disposable roots restored or deleted, and no protected fixture mutation.
- offline release gate passed with mutation coverage included, `workflow_count=17`, and `changed_files=[]`.
- docs-index validation passed.
- full regression returned `292 passed, 19 deselected`.
- AnythingLLM release gate passed with mutation coverage included, `workflow_count=17`, and `changed_files=[]`.

## Phase 49: Natural-Language Lifecycle Operations With Approval Continuations

Goal: let AnythingLLM users operate skill lifecycle workflows through natural language while preserving structured approval gates.

Implementation completed:

- natural workflow-router chat routes scaffold, selection explanation, pack validation, pack install, skill update, and skill deprecation requests.
- read-only natural lifecycle operations execute immediately.
- mutating natural lifecycle requests return `approval_required` with exact required approval fields unless the user supplies a structured approval object or exact approval continuation wording.
- approved continuations call the existing approval-gated controller workflow; no second mutation path was added.
- route-decision artifacts are persisted for natural lifecycle chat requests.
- approval-proof artifacts are persisted for approved natural continuations.
- JSON output is supported through the existing output-format selector.
- `scripts/validate_skill_natural_lifecycle_live.py` validates the natural lifecycle path through gateway and AnythingLLM without mutating the canonical registry.
- the live and AnythingLLM release gates include the new natural lifecycle guard.

Validation proof:

- focused natural lifecycle regression returned `5 passed, 169 deselected`.
- focused skill-controller release subset returned `47 passed, 127 deselected`.
- natural scaffold routed without manual skill injection and did not mutate runtime registries.
- natural pack validation returned parseable JSON.
- natural pack install and skill update returned `approval_required` without mutation, then approved continuations mutated only controlled-copy runtime files.
- natural deprecation returned required approval fields without mutation.
- docs-index validation passed.
- full regression returned `297 passed, 19 deselected`.
- Bash gateway natural lifecycle validation passed on both frozen fixtures with no canonical registry or fixture mutation.
- Bash AnythingLLM natural lifecycle validation passed on both frozen fixtures with no canonical registry or fixture mutation.
- offline release gate passed with `workflow_count=17` and `changed_files=[]`.
- AnythingLLM release gate passed with `workflow_count=17` and `changed_files=[]`.

## Phase 50: Controlled L1/L2 Skill Expansion Batch C

Goal: add the next small deterministic skill batch through the mature lifecycle path, with evals first and live proof on the two frozen Coinbase fixtures.

Implementation completed:

- Added Batch C proposal definitions for auth check lookup, state mutation lookup, external integration lookup, and error-handling path lookup.
- Registered and promoted `auth-check-locator`, `state-mutation-locator`, `external-integration-locator`, and `error-handling-path-locator`.
- Added eval cases `phase50_auth_check_lookup`, `phase50_state_mutation_lookup`, `phase50_external_integration_lookup`, and `phase50_error_handling_path_lookup`.
- Added deterministic workflow-router rules for the four Batch C prompt families.
- Tightened Batch C trigger metadata after live testing exposed a selector-budget tie between `state-mutation-locator` and `related-test-discovery`.
- Added `scripts/validate_phase50_skill_batch_live.py` and wired it into the live and AnythingLLM release gates.
- Updated catalog documentation and examples for the `46` skill / `45` eval-case catalog.

Validation proof:

- focused Phase 50 regression returned `2 passed, 174 deselected`.
- focused skill-controller release subset returned `49 passed, 127 deselected`.
- registry/eval/selector regression returned `47 passed`.
- docs-index validation passed.
- Phase 50 gateway live validation passed on `/mnt/c/coinbase_testing_repo_frozen_tmp` and `/mnt/c/coinbase_testing_repo_frozen_tmp.github` with no canonical registry or protected-fixture mutation during validation.
- Phase 50 AnythingLLM live validation passed on both frozen fixtures with no canonical registry or protected-fixture mutation during validation.
- offline release gate passed with `skill_count=46`, `eval_case_count=45`, `workflow_count=17`, and `changed_files=[]`.
- live release gate passed with `skill_count=46`, `eval_case_count=45`, `workflow_count=17`, and `changed_files=[]`.
- AnythingLLM release gate passed with `skill_count=46`, `eval_case_count=45`, `workflow_count=17`, and `changed_files=[]`.
- full regression returned `299 passed, 19 deselected`.

## Forward Approval Queue

The canonical phase definitions live in `docs/ACTIONABLE_WORKFLOW_ROADMAP.md`. This scaling plan mirrors the queue so future work does not revert to one-phase-at-a-time improvisation.

Approved remaining phases:

1. Phase 53: Multi-Step Task Decomposition Workflow - complete
2. Phase 54: Controlled Small-Change Apply Workflow - complete
3. Phase 55: V1 Productization, Installer, And Release Candidate Gate - complete
4. Phase 61: Skill Scaling Batch D Based On Field Evidence - proposal complete
5. Phase 62: Batch D Registration Through Existing Lifecycle - draft registration complete
6. Phase 63: Batch D Live Suite Coverage - live proof and promotion complete
7. Phase 64: Founder Field Suite Expansion With Batch D Prompts - complete
8. Phase 65: Skill Library Release Gate Upgrade - complete

Phases 51 through 55 are complete. Phase 61 produced an evidence-backed Batch D proposal and validator without mutating the skill registry. Phase 62 registered the approved Batch D candidates as draft skills through the existing `skill_batch.register` lifecycle path. Phase 63 proved Batch D through gateway and AnythingLLM on both frozen fixtures, then promoted the four skills through `skill_eval.promote`. Phase 64 added Batch D prompts to the founder field suite and proved the expanded 34-prompt suite through AnythingLLM and V1 acceptance. Phase 65 added skill-library health sections and Batch D proof to the single V1 acceptance path.

## Phase 51: Tool Catalog Expansion Governance

Goal: add a governed path for future tool capabilities so skills can request tools without bypassing policy or creating hidden behavior paths.

Implementation completed:

- Added `tool_catalog.validate` and `tool_catalog.register`.
- Added tool admission schema validation for tool identity, schemas, safety class, mutation policy, executable mediator support, workflow exposure, and role exposure.
- Added approval-gated registration that appends only `runtime/tools.json`.
- Added focused controlled-copy tests and Bash live validation.

Validation proof:

- focused tool catalog regression returned `6 passed`.
- tool catalog, tool mediator, and docs-index focused regression returned `13 passed`.
- Bash live validator returned `PHASE51 TOOL CATALOG GOVERNANCE LIVE PASS`.
- live validator recorded `runtime_changed_files=[]`, `target_changed_files={}`, and `anythingllm_applicable=false`.
- full regression returned `305 passed, 19 deselected`.

## Phase 52: AnythingLLM Chat UX And Artifact Summarization Hardening

Goal: make workflow-router and lifecycle chat responses immediately useful in AnythingLLM without forcing users to open artifact files first.

Implementation completed:

- Added `format_a` `Result:` contract fields for workflow, status, selected workflow, selected skills, selected tools, next action, and verification.
- Added JSON `chat_contract` with the same fields.
- Added bounded summary/artifact output with omitted-count markers.
- Tightened live validators to reject artifact-only responses.
- Added focused golden-marker regression fixtures and JSON contract live validation.

Validation proof:

- focused chat contract regression returned `4 passed`.
- focused controller chat regression returned `10 passed, 170 deselected`.
- docs-index validation passed.
- inline gateway and AnythingLLM validation passed on both frozen repos.
- representative L1 and L2 gateway/AnythingLLM validation passed on both frozen repos.
- JSON contract gateway/AnythingLLM validation passed on both frozen repos.
- full regression returned `309 passed, 19 deselected`.

## Phase 53: Multi-Step Task Decomposition Workflow

Goal: decompose larger coding tasks into deterministic read-only work packages before implementation starts.

Implementation completed:

- Added `task.decompose` and `/v1/controller/task-decompositions`.
- Registered `task.decompose` in `runtime/workflows.json`.
- Routed explicit natural decomposition prompts through `workflow_router.plan`.
- Added chat-visible `Task Decomposition:` output and JSON `chat_contract` support.
- Added focused regression and Bash live validation.
- Added feature README and examples.

Validation proof:

- focused task-decomposition regression returned `5 passed`.
- focused task/chat/docs regression returned `10 passed`.
- docs-index validation passed.
- Bash live validator returned `PHASE53 TASK DECOMPOSITION LIVE PASS` on both frozen repos through direct controller, workflow-router gateway, and AnythingLLM.
- live validation checked localhost `8000`, gateway/controller ports, role ports, protected fixture hashes, and git status.
- full regression returned `314 passed, 19 deselected`.

## Phase 54: Controlled Small-Change Apply Workflow

Goal: make small approved edits possible through the controller while preserving one canonical implementation path, rollback, verification, and protected fixture safety.

Implementation completed:

- Added `implementation.workflow` controller wrapper endpoint with dry-run and real-apply approval gates.
- Added patch previews and rollback operation metadata to the existing implementation workflow.
- Added protected frozen fixture real-apply refusal.
- Added natural disposable-copy apply through `workflow_router.plan` for exact approved `packet_operations` JSON.
- Added byte-exact disposable-copy rollback using backup artifacts.
- Added focused regression, live validator, feature README, examples, and Getting Started coverage.

Validation proof:

- focused controlled-apply and implementation workflow regression returned `16 passed`.
- Bash live validator returned `PHASE54 CONTROLLED SMALL-CHANGE APPLY LIVE PASS` on both frozen repos through direct controller, workflow-router gateway, and AnythingLLM.
- live validation checked localhost `8000`, gateway/controller ports, role ports, protected fixture hashes, and git status.
- live validation wrote `runtime-state/controlled-small-change-apply/phase54-live.json`.
- docs-index validation passed.
- full regression returned `321 passed, 19 deselected`.

## Phase 55: V1 Productization, Installer, And Release Candidate Gate

Goal: make the current product testable by a first-time user without session history.

Implementation completed:

- Expanded V1 acceptance to run representative L1, representative L2, task decomposition, controlled apply, inline FormatA, JSON output, and feedback checks.
- Added startup client-target diagnostics and Bash validation guidance.
- Updated Getting Started with the current release-candidate command.
- Updated the V1 release-candidate report with feature matrix, unsupported boundaries, known limitations, and proof.
- Kept the root README short and linked current feature docs through the ordered docs index.

Validation proof:

- Bash release-candidate gate returned `V1 ACCEPTANCE PASS`.
- V1 report `runtime-state/v1-acceptance/v1-acceptance-20260605T224619545592Z.json` recorded `suite_count=5`, `json_output_count=2`, `feedback_count=2`, and `error_count=0`.
- startup script output printed correct `8500/v1`, `8300/v1`, and `8400` client targets.
- docs-index validation passed.
- full regression returned `321 passed, 19 deselected`.

## Phase 61: Skill Scaling Batch D Based On Field Evidence

Goal: use founder field evidence to define the next deterministic skill batch without expanding from theory.

Implementation completed:

- Added [SKILL_SCALING_BATCH_D_PROPOSAL.md](SKILL_SCALING_BATCH_D_PROPOSAL.md) for founder review.
- Added structured proposal [skill-scaling-batch-d.json](skill-scaling-batch-d.json).
- Added `scripts/validate_skill_batch_d_proposal.py`.
- Added proposal regression for valid Batch D candidates and duplicate-route-key rejection.
- Kept `runtime/skills.json`, `runtime/skill_evals.json`, and skill bodies unchanged by this phase.

Candidate skills:

1. `handler-branch-tracer`
2. `table-schema-isolator`
3. `runtime-entrypoint-disambiguator`
4. `change-boundary-summarizer`

Validation proof:

- proposal validator returned `SKILL BATCH D PROPOSAL PASS`
- focused regression returned `12 passed` for skill batch tests
- proposal report wrote `runtime-state/skill-batches/phase61-batch-d-proposal-20260606T021705594063Z.json`
- validator reported `candidate_count=4`, `route_key_count=4`, `eval_case_count=4`, and `semantic_conflict_count=0`

## Phase 62: Batch D Registration Through Existing Lifecycle

Goal: turn the Phase 61 Batch D proposal into real draft skills and eval cases through the existing skill lifecycle without bypassing admission gates.

Implementation completed:

- Added Batch D definitions to `skill_batch.propose`.
- Registered the approved Batch D proposal through `skill_batch.register`.
- Installed draft skill bodies for `handler-branch-tracer`, `table-schema-isolator`, `runtime-entrypoint-disambiguator`, and `change-boundary-summarizer`.
- Added eval cases `phase61_handler_branch_trace`, `phase61_table_schema_only`, `phase61_runtime_entrypoint_disambiguation`, and `phase61_change_boundary_summary`.
- Kept all four skills at `eval_status=draft`; promotion is deferred until Phase 63 live proof.

Validation proof:

- registration run `skill-batch-registration-20260606T041116522680Z`
- proposal validator passed before and after registration
- registration `batch-validation-before-install.json` passed with `skill_count=4`, `eval_case_count=4`, and `route_key_count=4`
- skill eval report `runtime-state/skill-evals/phase62-skill-evals.json` passed with `case_count=49`
- skill scale report `runtime-state/skill-scale/phase62-skill-scale.json` passed with `skill_count=50`, `eval_case_count=49`, and `do_not_admit_count=0`
- focused registry/eval/batch regression returned `55 passed`
- focused lifecycle regression returned `29 passed, 149 deselected`

## Phase 63: Batch D Live Suite Coverage

Goal: prove registered Batch D skills work through live gateway and AnythingLLM paths before promotion.

Implementation completed:

- Added `scripts/validate_phase63_skill_batch_live.py`.
- Validated all four Batch D prompt families through the Bash-hosted workflow-router gateway on both frozen Coinbase fixtures.
- Validated all four Batch D prompt families through AnythingLLM on both frozen Coinbase fixtures.
- Verified expected selected skill, downstream workflow, downstream artifact, chat-visible answer markers, and no protected source mutation for every case.
- Promoted Batch D through `skill_eval.promote` only after the full live proof passed.

Validation proof:

- gateway-only dry run passed with promotion skipped: `runtime-state/skill-batches/phase63-batch-d-live-20260606T042721351141Z.json`
- full gateway and AnythingLLM proof passed: `runtime-state/skill-batches/phase63-batch-d-live-20260606T043006924969Z.json`
- promotion run `skill-eval-promotion-20260606T043425493565Z`
- lifecycle audit run `skill-lifecycle-audit-20260606T043428653989Z`
- protected source hashes for both frozen fixtures remained unchanged
- git-enabled frozen fixture status remained clean

## Phase 64: Founder Field Suite Expansion With Batch D Prompts

Goal: prove promoted Batch D skills from natural founder prompts, not only from the focused Batch D validator.

Implementation completed:

- Expanded the founder field catalog from 26 to 34 prompts.
- Added `P27` through `P34` for Batch D behavior on both frozen fixtures.
- Added expected Batch D skill IDs and downstream artifact keys to the field-test evaluator.
- Added refined prompt variants for the Batch D cases.
- Added prompt-matrix classifier expectations for the Batch D cases.
- Updated founder-facing docs and focused regressions.

Validation proof:

- prompt matrix passed with `50` prompt variants and `0` failures in `runtime-state/founder-field-tests/phase64-prompt-matrix-initial.json`
- focused Batch D AnythingLLM field run passed with `8` prompt cases and `0` failures in `runtime-state/founder-field-tests/phase64-batch-d-field-prompts.json`
- expanded founder field run passed with `34` prompt cases and `0` failures in `runtime-state/founder-field-tests/phase64-expanded-founder-field-prompts.json`
- V1 acceptance passed with the expanded suite in `runtime-state/v1-acceptance/phase64-v1-acceptance.json`
- protected source hashes for both frozen fixtures remained unchanged
- git-enabled frozen fixture status remained clean

## Phase 65: Skill Library Release Gate Upgrade

Goal: make the V1 release path prove skill-library health and Batch D live behavior, not only workflow-router behavior.

Implementation completed:

- Added prompt-matrix proof generation and validation to the skill release gate.
- Added Batch D live validation to live and AnythingLLM release-gate modes.
- Added `skill_library_release_gate` to the V1 acceptance suite list.
- Added structured `founder_field_summary` and `skill_library_health` sections to V1 acceptance reports.
- Kept one release-candidate entrypoint: `scripts/validate_v1_acceptance.py`.

Validation proof:

- offline release gate passed in `runtime-state/skill-release-gates/phase65-offline-skill-release-gate.json`
- Bash AnythingLLM release gate passed in `runtime-state/skill-release-gates/phase65-anythingllm-skill-release-gate.json`
- V1 acceptance passed in `runtime-state/v1-acceptance/phase65-v1-acceptance.json`
- V1 acceptance recorded `suite_count=7`, `skill_count=50`, `eval_case_count=49`, `route_key_count=50`, `workflow_count=21`, `field_prompt_count=34`, `prompt_matrix_case_count=50`, and `prompt_matrix_failed=0`
- V1 acceptance recorded Batch D live proof at `runtime-state/skill-batches/phase63-batch-d-live-20260606T061926847189Z.json`
- protected source hashes for both frozen fixtures remained unchanged
- git-enabled frozen fixture status remained clean

## Phase 66: Generalization Beyond Coinbase Fixture

Goal: prove the skill/workflow harness is not overfit to the Coinbase fixtures.

Implementation completed:

- Added `tests/fixtures/generalization/python_service_fixture` as a representative non-Coinbase Python service fixture.
- Added `scripts/validate_generalization_fixture_live.py` to copy the fixture into a disposable runtime directory, validate ports, run bounded gateway and AnythingLLM prompt cases, record before/after hashes, and clean up the copy.
- Covered L1 explanation, L2 test-selection, and Batch D handler-branch, table-schema, runtime-entrypoint, and change-boundary skills on the new fixture.
- Added shared natural change-subject extraction, schema-subject extraction for `schema fields for <target>` prompts, runtime-entrypoint/endpoint disambiguation, and a narrow `l2_test_selection_terms` skill override.

Validation proof:

- focused regression passed with `9` focused tests covering the new fixture, data-model extraction, and the prior schema artifact regression
- full regression passed with `344 passed, 19 deselected`
- docs index returned `DOCS INDEX PASS` with `55` linked docs and no orphan docs
- `runtime-state/generalization-fixtures/phase66-generalization-anythingllm.json` returned `status=passed`, `gateway_count=6`, `anythingllm_count=6`, `error_count=0`, and `cleanup.status=removed`
- `runtime-state/v1-acceptance/phase66-v1-acceptance.json` returned `status=passed`, `suite_count=7`, `json_output_count=2`, `feedback_count=2`, and `error_count=0`
- Phase 66 V1 acceptance included both frozen Coinbase fixtures, founder field prompts `34 passed / 0 failed`, skill release gate `status=passed`, prompt matrix `50 passed / 0 failed`, `skill_count=50`, and `eval_case_count=49`
- watched protected `core/stealth_order_manager.py` hash stayed `aa3aabd03b8d88ddfbdf61e0f849165ae4dc4cf05ec1dd8b7a4389b12729057e` in both frozen Coinbase fixtures

## Phase 67: AnythingLLM User Feedback Loop

Goal: make founder/tester feedback actionable by linking natural AnythingLLM feedback to route decisions, selected skills, artifacts, semantic status, fixture target, and a bounded next action.

Implementation completed:

- Expanded workflow feedback records with classifications, selected workflow, selected skills, artifact keys, downstream artifact keys, prompt-case status, semantic status, route decision references, target fixture, and next action.
- Added natural feedback parsing for `confusing` and `unsafe` feedback in addition to useful, wrong, missing, noisy, and slow.
- Tightened workflow-router feedback detection so filesystem paths containing feedback-related words do not trigger feedback routing.
- Tightened V1 acceptance so both gateway and AnythingLLM feedback paths prove feedback context from controller run artifacts.

Validation proof:

- focused regression passed with `15` focused tests covering feedback context, next-action selection, generalization regressions, and V1 acceptance feedback checks
- `runtime-state/v1-acceptance/phase67-v1-acceptance.json` returned `status=passed`, `suite_count=7`, `json_output_count=2`, `feedback_count=2`, and `error_count=0`
- gateway and AnythingLLM feedback records passed on both frozen Coinbase fixtures with selected workflow `code_investigation.plan`, selected skill `code-explanation-summarizer`, classifications `useful` and `missing`, downstream `code_explanation` artifacts, and next action `prompt_or_artifact_gap_review`
- full regression passed with `346 passed, 19 deselected`
- docs index returned `DOCS INDEX PASS` with `55` linked docs and no orphan docs
- watched protected `core/stealth_order_manager.py` hash stayed `aa3aabd03b8d88ddfbdf61e0f849165ae4dc4cf05ec1dd8b7a4389b12729057e` in both frozen Coinbase fixtures

## Phase 68: Release Gate Profiles

Goal: split validation into named profiles so failures are cheaper to diagnose without weakening the final release-candidate path.

Implementation completed:

- Added `vllm_agent_gateway.acceptance.profiles` with `ReleaseGateProfile`, `LiveGuardLevel`, and a durable `profile_contract`.
- Added `--profile offline|mutation|live-smoke|live-full|release-candidate` to `scripts/validate_skill_release_gate.py`.
- Preserved legacy `--offline-only`, `--live`, and `--anythingllm` flags as aliases, with legacy `--offline-only` still mapping to mutation coverage.
- Split the skill release gate into static, mutation, smoke-live, full-live, and AnythingLLM release-candidate command sets.
- Added `profile` and `profile_contract` fields to skill release-gate reports.
- Updated V1 acceptance to record `profile=release-candidate` and call the embedded skill gate through `--profile release-candidate`.

Validation proof:

- focused regression passed with `9` focused tests covering profile contracts, legacy flag mapping, V1 suite command shape, and V1 skill-health profile summaries
- `runtime-state/skill-release-gates/phase68-offline-profile.json` returned `status=passed`, `profile=offline`, `commands=2`, and `changed_files=[]`
- `runtime-state/skill-release-gates/phase68-mutation-profile.json` returned `status=passed`, `profile=mutation`, `commands=3`, and `changed_files=[]`
- `runtime-state/skill-release-gates/phase68-live-smoke-profile.json` returned `status=passed`, `profile=live-smoke`, `commands=4`, and `changed_files=[]`
- `runtime-state/skill-release-gates/phase68-live-full-profile.json` returned `status=passed`, `profile=live-full`, `commands=7`, and `changed_files=[]`
- `runtime-state/skill-release-gates/phase68-release-candidate-profile.json` returned `status=passed`, `profile=release-candidate`, `commands=7`, and `changed_files=[]`
- `runtime-state/v1-acceptance/phase68-v1-acceptance.json` returned `status=passed`, `profile=release-candidate`, `suite_count=7`, `json_output_count=2`, `feedback_count=2`, and `error_count=0`
- full regression passed with `348 passed, 19 deselected`
- watched protected `core/stealth_order_manager.py` hash stayed `aa3aabd03b8d88ddfbdf61e0f849165ae4dc4cf05ec1dd8b7a4389b12729057e` in both frozen Coinbase fixtures

## Phase 69: Latest Run Inspector

Goal: add a read-only CLI that summarizes latest or explicit controller runs without forcing users to open large artifact trees by hand.

Implementation completed:

- Added `vllm_agent_gateway/run_inspector.py` and `scripts/inspect_latest_run.py`.
- Supported latest run selection, explicit `--run-id`, workflow filtering, text output, JSON output, and durable report writing.
- Summarized route status, selected workflow, route rules, selected skills, selected tools, downstream workflow, artifact keys, semantic status, warnings, failures, resume key, and mutation proof.
- Added default controller artifact-root discovery and Windows-side conversion for Bash-stored `/mnt/c/...` artifact paths.
- Added `README.run-inspector.md` and `docs/examples/run-inspector.md`.

Validation proof:

- focused regression passed with `4` focused inspector/docs tests
- docs index returned `DOCS INDEX PASS` with `57` linked docs and no orphan docs
- Windows CLI inspection of `C:\private_agentic_agents\runtime-state\controller-artifacts` returned latest git-enabled workflow-router run `workflow-router-20260606T094508530797Z`
- Bash CLI inspection of `/mnt/c/private_agentic_agents/runtime-state/controller-artifacts` returned the same latest git-enabled workflow-router run and wrote `runtime-state/run-inspector/phase69-bash-latest-workflow-router.json`
- Bash explicit-run inspection for non-git fixture run `workflow-router-20260606T094432846134Z` wrote `runtime-state/run-inspector/phase69-bash-explicit-non-git-workflow-router.json`
- final full regression passed with `351 passed, 19 deselected`
- watched protected `core/stealth_order_manager.py` hash stayed `aa3aabd03b8d88ddfbdf61e0f849165ae4dc4cf05ec1dd8b7a4389b12729057e` in both frozen Coinbase fixtures

## Required Commands Per Runtime-Facing Batch

Run from Bash:

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
```

```bash
python3 scripts/validate_workflow_router_l1_suite.py \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --timeout-seconds 900
```

```bash
python3 scripts/validate_workflow_router_l2_suite.py \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --timeout-seconds 900
```

```bash
python3 scripts/validate_task_decomposition_live.py \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --controller-base-url http://127.0.0.1:8400 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --timeout-seconds 900
```

```bash
python3 scripts/validate_controlled_small_change_apply_live.py \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --controller-base-url http://127.0.0.1:8400 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --timeout-seconds 900
```

```bash
python3 scripts/validate_generalization_fixture_live.py \
  --timeout-seconds 900 \
  --output-path runtime-state/generalization-fixtures/phase66-generalization-anythingllm.json
```

```bash
python3 scripts/validate_v1_acceptance.py \
  --profile release-candidate \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --timeout-seconds 900
```

Use an explicit output path when recording feedback-loop proof:

```bash
python3 scripts/validate_v1_acceptance.py \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --timeout-seconds 900 \
  --output-path runtime-state/v1-acceptance/phase67-v1-acceptance.json
```

```bash
python3 scripts/validate_phase40_skill_batch_live.py \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --controller-base-url http://127.0.0.1:8400 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --timeout-seconds 900
```

```bash
python3 scripts/validate_skill_natural_lifecycle_live.py \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --timeout-seconds 900
```

Run from the repo shell:

```bash
python scripts/validate_skill_evals.py
python scripts/validate_skill_scale.py
python scripts/validate_skill_selector_scale.py
python scripts/validate_skill_batch_d_proposal.py
python scripts/validate_founder_field_prompt_matrix.py
python scripts/validate_skill_release_gate.py --profile offline
python scripts/check_docs_index.py
python -m pytest tests/regression/test_skill_registry.py tests/regression/test_skill_evals.py -q
python -m pytest tests/regression/ -v
git -c safe.directory=C:/coinbase_testing_repo_frozen_tmp.github -C C:\coinbase_testing_repo_frozen_tmp.github status --short
```

## Approval Decision

Approved remaining scope:

```text
Phases 51-55 complete; Phase 61 proposal complete; Phase 62 draft registration complete; Phase 63 live proof and promotion complete; Phase 64 founder field expansion complete; Phase 65 release gate integration complete; Phase 66 generalization proof complete; Phase 67 feedback-loop proof complete; Phase 68 release-gate profiles complete; Phase 69 latest-run inspector complete; Phase 70 prompt-catalog governance complete; Phase 71 AnythingLLM UI E2E complete
```

Phase 71 browser-rendered AnythingLLM UI proof is complete, so the canonical roadmap has moved to the approved Phase 72 Model Portability Gate. Batch D is allowed in the founder field suite because Phase 64 explicitly approved and validated that expansion, prompt case changes must go through the governed catalog fixture plus catalog/matrix validation, and the user-facing AnythingLLM UI path now has a repeatable `/stream-chat` proof. Broad advanced refactor orchestration remains excluded until explicitly reintroduced in the canonical roadmap.

## Phase 70 Prompt-Catalog Governance Completion

Completed:

- Moved founder field prompt case metadata to `runtime/prompt_catalogs/founder_field_v1.json`.
- Added catalog loader/validator in `vllm_agent_gateway/prompt_catalogs.py`.
- Added `scripts/validate_prompt_catalog.py`.
- Updated founder field and prompt matrix scripts to consume the catalog as the single prompt source.
- Added prompt catalog validation to the skill release gate.

Proof:

- `runtime-state/prompt-catalogs/phase70-prompt-catalog-postdocs.json`: `case_count=34`, `refined_prompt_count=16`, `problem_count=0`.
- `runtime-state/founder-field-tests/phase70-prompt-matrix-postdocs.json`: `50` passed, `0` failed.
- `runtime-state/skill-release-gates/phase70-offline-profile.json`: `status=passed`, `changed_files=[]`.
- `runtime-state/v1-acceptance/phase70-v1-acceptance.json`: `status=passed`, `profile=release-candidate`, `suite_count=7`, `json_output_count=2`, `feedback_count=2`, `errors=0`.
- Full regression: `353 passed, 19 deselected`.

## Phase 71 AnythingLLM UI E2E Completion

Completed:

- Added `vllm_agent_gateway/anythingllm_ui_e2e.py`.
- Added `scripts/validate_anythingllm_ui_e2e.py`.
- Added `README.anythingllm-ui-e2e.md` and `docs/examples/anythingllm-ui-e2e.md`.
- Added focused regression coverage for strict prompt-tag marker checks, `/stream-chat` proof, Electron shim construction, and request-failure classification.

Proof:

- `runtime-state/anythingllm-ui/phase71-ui-e2e-fixed.json`: `status=passed`, `case_count=2`, `fixture_unchanged=true`, `errors=0`.
- Both frozen Coinbase fixture cases recorded `stream_chat_seen=true` and marker hits for `workflow_router.plan completed`, `selected_workflow: code_investigation.plan`, `run_id:`, and `Answer:`.
- `runtime-state/v1-acceptance/phase71-v1-acceptance.json`: `status=passed`, `profile=release-candidate`, `suite_count=7`, `json_output_count=2`, `feedback_count=2`, `errors=0`.
- Full regression: `359 passed, 19 deselected`.
