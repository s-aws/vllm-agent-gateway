# Skill Library Scaling Plan

Status: approved post-V1 scope. Phase 29 through Phase 32 are complete; Phase 33 preparation is complete and awaits founder approval before any draft-only expansion is implemented.

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

## Proposed Phase 34: Draft-Only Expansion Batch A

Status: proposed; not approved for implementation until the founder approves the Phase 33 batch list and proof gates.

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

## Proposed Phase 35: Scale Operations

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
python3 scripts/validate_v1_acceptance.py \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --timeout-seconds 900
```

Run from the repo shell:

```bash
python scripts/validate_skill_evals.py
python scripts/check_docs_index.py
python -m pytest tests/regression/test_skill_registry.py tests/regression/test_skill_evals.py -q
python -m pytest tests/regression/ -v
git -C C:\coinbase_testing_repo_frozen_tmp.github status --short
```

## Approval Decision

Recommended next approved scope:

```text
Phase 34: Draft-Only Expansion Batch A
```

Do not start Phase 34 implementation until the founder approves the Phase 33 Batch A prompt list and proof gates.
