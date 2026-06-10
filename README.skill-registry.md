# Skill Registry

The skill registry is the canonical metadata surface for project-local planning skills.

It is not a runtime tool and it does not expose arbitrary skill bodies to the model. The router selects skill IDs from metadata first, then downstream workflows may load only the selected skill bodies they already support.

## Files

- `runtime/skills.json`: canonical skill metadata.
- `runtime/skill_evals.json`: shared eval fixture and eval-case catalog.
- `runtime/skill_pack_policy.json`: executable packaging policy for layout, namespaces, dependency rules, versioning, import/export, and retirement.
- `vllm_agent_gateway/skills/registry.py`: registry validation, admission validation, and metadata-only selection.
- `vllm_agent_gateway/skills/evals.py`: executable eval-catalog validation and optional L1/L2 live-suite mapping.
- `vllm_agent_gateway/skills/batches.py`: proposed batch validation before appending new skills and eval cases to runtime registries.
- `vllm_agent_gateway/skills/packs.py`: governed skill-pack validation with namespace ownership before controlled installs.
- `vllm_agent_gateway/skills/scale.py`: scale-readiness coverage and do-not-admit reporting.
- `vllm_agent_gateway/skills/selector_scale.py`: metadata-only selector-scale and stability benchmark generation.
- `scripts/validate_skill_evals.py`: CLI that writes durable skill eval reports.
- `scripts/validate_skill_batch.py`: focused CLI for skill-batch dry-run admission reports.
- `scripts/validate_skill_pack.py`: focused CLI for skill-pack namespace and admission validation.
- `scripts/validate_skill_packaging_policy.py`: focused CLI for validating the skill-pack packaging policy against registry constants.
- `scripts/validate_skill_scale.py`: CLI that writes registry-scale coverage reports.
- `scripts/validate_skill_selector_scale.py`: CLI that writes 100, 1,000, and 10,000 skill selector-scale reports.
- `scripts/validate_skill_release_gate.py`: canonical profiled release-gate CLI that runs skill registry, eval, scale, selector-scale, prompt catalog, prompt matrix, docs, focused controller regression, mutation, and optional live/AnythingLLM guards.
- `scripts/validate_skill_mutations.py`: disposable-copy mutation and fault-injection CLI for registry, eval, selector, lifecycle, and release-gate failure proof.
- `scripts/validate_skill_promotion_live.py`: Bash-side live guard check for promotion readiness and no-mutation behavior.
- `scripts/validate_skill_lifecycle_live.py`: Bash-side live guard check for lifecycle audit through controller, gateway, and AnythingLLM.
- `scripts/validate_skill_natural_lifecycle_live.py`: Bash-side live guard for natural lifecycle chat routes, approval-required refusal, gateway, AnythingLLM, and protected-fixture no-mutation proof.
- `scripts/validate_phase40_skill_batch_live.py`: Bash-side live validator for controlled Batch B skill installation, promotion, lifecycle audit, gateway, and AnythingLLM proof.
- `scripts/validate_phase50_skill_batch_live.py`: Bash-side live validator for controlled Batch C skill routing, lifecycle audit, gateway, AnythingLLM, and protected-fixture no-mutation proof.
- `vllm_agent_gateway/controllers/skill_batch/propose.py`: controller-owned proposal workflow that creates artifact-only skill-batch drafts from natural-language requests.
- `vllm_agent_gateway/controllers/skill_batch/register.py`: approval-gated workflow that installs a passed proposal into the runtime registry with hash proof and rollback artifacts.
- `vllm_agent_gateway/controllers/skill_eval/promote.py`: approval-gated workflow that promotes registered draft skills to validated status after proof gates pass.
- `vllm_agent_gateway/controllers/skill_lifecycle/audit.py`: read-only workflow that reports skill lifecycle status and deterministic next actions.
- `vllm_agent_gateway/controllers/skill_deprecation/deprecate.py`: approval-gated workflow that deprecates one skill, validates its replacement, and writes rollback artifacts.
- `vllm_agent_gateway/controllers/skill_update/update.py`: approval-gated workflow that updates one validated skill with semantic versioning, validation, hash proof, and rollback artifacts.
- `vllm_agent_gateway/controllers/skill_selection/explain.py`: read-only workflow that explains selected, skipped, and deprecated skills without loading skill bodies.
- `vllm_agent_gateway/controllers/skill_pack/validate.py`: read-only workflow that validates governed pack manifests.
- `vllm_agent_gateway/controllers/skill_pack/install.py`: approval-gated workflow that installs passed packs into controlled registry copies with rollback proof.
- `vllm_agent_gateway/controllers/skill_scaffold/scaffold.py`: artifact-only workflow that generates draft skill bodies, metadata, eval cases, docs refs, validation checklists, and batch manifests.
- `.qwen/skills/<skill>/SKILL.md`: skill bodies with Agent Skills-style `name` and `description` frontmatter.

## Metadata

Each skill entry declares:

- `id`, `path`, `version`, and `owner`
- compatibility tags
- safety level
- allowed controller tools it may request
- supported workflows
- trigger terms and workflow priorities
- a `capability_contract` with route key, task types, input/output artifacts, approval boundary, mutation policy, and eval case IDs
- problem-solving steps
- eval status and fixture IDs
- failure-record references that justify the skill

The `capability_contract.route_key` is the scaling guardrail. It must be unique across the registry so a future skill cannot silently create a parallel implementation of the same behavior. Runtime skill selection now uses capability contracts as the deterministic shortlist before trigger-score ordering.

## Skill Admission

Phase 22 adds admission validation for one future draft skill at a time. Admission validation does not mutate `runtime/skills.json`, `runtime/skill_evals.json`, or runtime routing. It validates a proposal object with:

- `skill`: one complete draft skill metadata entry
- `eval_case`: one matching eval case
- `doc_refs`: documentation paths that already exist

The proposed skill must use `eval_status: draft`, reference the proposed eval case in `capability_contract.eval_case_ids`, match the eval case mutation policy, and avoid duplicate skill IDs or route keys.

## Skill Batch Admission

Phase 29 adds batch admission validation for future small L1/L2 skill batches. Batch admission does not mutate `runtime/skills.json`, `runtime/skill_evals.json`, runtime routing, or skill selection. It validates a manifest with:

- `schema_version: 1`
- `kind: skill_batch_manifest`
- `id` and `description`
- `doc_refs`
- `skills`: draft skill metadata entries
- `eval_cases`: matching eval cases

Batch validation rejects duplicate skill IDs, duplicate route keys, eval cases that already exist, unreferenced eval cases, missing skill bodies, missing doc refs, unsupported mutation policies, unknown workflows, unknown tools, and unknown expected artifacts. The report lists each skill, route key, eval case, workflow, expected artifacts, mutation policy, and live-suite mapping.

Use batch admission before adding a 3-5 skill batch to runtime registries:

```bash
python scripts/validate_skill_batch.py --batch-file path/to/skill-batch.json
```

The eval CLI can run the same batch mode:

```bash
python scripts/validate_skill_evals.py --batch-file path/to/skill-batch.json
```

## Skill Pack Governance

Phase 46 adds governed skill packs for scaling beyond hand-managed local batches. Phase 77 adds the executable packaging policy in `runtime/skill_pack_policy.json` and the deeper strategy in [docs/SKILL_LIBRARY_PACKAGING_STRATEGY.md](docs/SKILL_LIBRARY_PACKAGING_STRATEGY.md). A pack is a package wrapper around batch-compatible skill metadata and eval cases. It adds pack-level ownership and namespace checks, then reuses the same batch admission and canonical runtime selector path.

A skill-pack manifest uses:

- `schema_version: 1`
- `kind: skill_pack_manifest`
- `id`, `version`, `owner`, and `description`
- `namespaces`: route-key namespaces the pack is allowed to use
- `compatibility`: compatibility tags for the pack
- `docs`: documentation refs that already exist
- `skills`: draft skill metadata entries
- `eval_cases`: matching eval cases

Pack validation rejects duplicate route keys, unsupported workflows, missing docs, missing eval cases, route namespaces not declared by the pack, owner mismatches, namespace ownership collisions, and deprecated replacement gaps. It does not mutate `runtime/skills.json`, `runtime/skill_evals.json`, `.qwen/skills`, or target repositories.

Validate a pack:

```bash
python scripts/validate_skill_pack.py --pack-file path/to/skill-pack.json
```

Validate the packaging policy:

```bash
python scripts/validate_skill_packaging_policy.py
```

Direct controller validation:

```json
{
  "workflow": "skill_pack.validate",
  "schema_version": 1,
  "pack_path": "path/to/skill-pack.json"
}
```

Pack install is approval-gated and re-runs validation immediately before mutation. It writes approved skill bodies to `.qwen/skills/<skill-id>/SKILL.md`, appends metadata and eval cases to the runtime registries, runs post-install eval and scale checks, and records rollback instructions plus before/after hashes.

Approval shape:

```json
{
  "status": "approved_for_skill_pack_install",
  "scope": "skill_pack_install",
  "runtime_registry_append": true,
  "skill_body_install": true,
  "approval_refs": ["founder-review:<pack-id>"]
}
```

Uninstall is intentionally not part of Phase 46.

## Skill Authoring Scaffold

Phase 47 adds `skill.scaffold`, an artifact-only controller workflow for generating a valid draft skill package from a prompt-family spec.

Phase 80 extends the same `skill.scaffold` path into the skill authoring factory. It still does not mutate runtime registries. It now also generates planned prompt coverage, docs stubs, an eval skeleton, and a fail-closed regression test skeleton from the same prompt-family specification.

The scaffold request requires a `prompt_family_spec` with:

- `skill_id`
- `description`
- `prompt_family`
- `natural_prompt`
- `workflow_id`
- `route_key`
- `trigger_terms`
- `task_types`
- `output_artifact`
- `live_suite`

`output_artifact` is intentionally required and must already be known from workflow result artifacts, existing skill output artifacts, or manual artifacts. The scaffold will not invent a new artifact path.

Generated artifacts include:

- draft `SKILL.md` with frontmatter
- `batch.json`
- `batch-validation-report.json`
- `prompt-coverage-entry.json`
- `eval-skeleton.json`
- `docs-stubs/README.<skill_id>.md`
- `docs-stubs/examples/<skill_id>.md`
- `test-skeletons/test_<skill_id>_authoring_gate.py`
- `authoring-factory-report.json`
- `validation-checklist.json`
- `skill-scaffold.json`
- `run-state.json`

The workflow returns `ready` only when the generated batch manifest passes existing batch admission. Overlapping semantic intent, duplicate route keys, missing docs, unsupported workflows, missing eval cases, and unknown artifacts return `do_not_admit` or a structured scaffold error instead of mutating runtime files.

Scaffolded skills are not promoted by scaffolding alone. Generated sidecars carry `promotion_state: not_promoted_by_scaffold`, and the generated pytest skeleton intentionally fails closed until routing, artifact contract, natural-language chat output, and prompt coverage are installed and proved.

Direct endpoint:

```json
{
  "workflow": "skill.scaffold",
  "schema_version": 1,
  "prompt_family_spec": {
    "skill_id": "example-pack-locator",
    "description": "Locate bounded source evidence for an example scaffold prompt.",
    "prompt_family": "example-pack-lookup",
    "natural_prompt": "In <repo>, run the example pack lookup. Read only.",
    "workflow_id": "code_investigation.plan",
    "route_key": "code.example_pack_lookup",
    "trigger_terms": ["example pack lookup"],
    "task_types": ["example_pack_lookup"],
    "output_artifact": "investigation_plan",
    "live_suite": "skill_registry_contract",
    "coverage_id": "EXAMPLE-PACK-LOOKUP",
    "level": "L1",
    "route_rule": "l1_find_behavior_start_terms",
    "tool_ids": ["git_grep", "read_file"]
  }
}
```

To register scaffolded output, use the generated `batch.json` as a reviewed source for the existing `skill_batch.propose`/`skill_batch.register` path or as content for a governed skill pack. Install the generated prompt coverage entry only after the skill metadata, eval case, docs, route rule, and chat-output proof are in place. Do not hand-append scaffold output to `runtime/skills.json`.

Factory details: [README.skill-authoring-factory.md](README.skill-authoring-factory.md).

## Natural Lifecycle Chat

Phase 49 wires lifecycle operations through the workflow-router chat surface so AnythingLLM users can operate the skill system without pasting controller envelopes. The natural adapter only translates deterministic text into the same controller requests used by the direct endpoints; it does not create a second mutation path.

Read-only natural requests are supported for:

- `skill.scaffold`
- `skill.selection.explain`
- `skill_pack.validate`
- `skill_lifecycle.audit`

Approval-gated natural requests are supported for:

- `skill_pack.install`
- `skill.update`
- `skill.deprecate`

For mutating workflows, vague text such as "go ahead" or "looks good" is not approval. A mutation request without explicit approval returns `status: approval_required`, a chat-visible `required_approval` object, an `approval_requirement` artifact, and a `route_decision` artifact. Runtime registries and target repositories are not changed.

Approved continuations must use exact lifecycle wording or a structured approval object. Supported continuation phrases are:

- `Approved for skill pack install run_id <approval-required-run-id>`
- `Approved for skill update run_id <approval-required-run-id>`
- `Approved for skill deprecation run_id <approval-required-run-id>`

Successful approved continuations call the existing approval-gated workflow and add a natural `approval_proof` artifact. The underlying workflow still writes its own request, rollback, hash-proof, eval, and scale artifacts.

Natural requests can ask for JSON using `Return output as JSON`, `Respond in JSON`, or an OpenAI-style `response_format: {"type":"json_object"}`. FormatA remains the default.

## Seed V1 Skill Library

The V1 seed adds task-specific read-only skills for validated L1/L2 coding-agent prompt families. These skills do not create new runtime workflows. They sit behind the same registry selection path and use priority `1000`, which means they are selected only when their trigger terms match the request.

Seeded V1 and post-V1 Phase 30/31/32/34 families include code explanation, related-test discovery, safe test-command selection, behavior-existence checks, callers/usages summaries, configuration lookup, pasted-failure summaries, endpoint/route lookup, error/log/message source lookup, module summary, data model/schema lookup, dependency/import lookup, coverage-gap summary, documentation lookup, CLI/script entrypoint lookup, configuration runtime-effect summary, local-change summary, failing-test diagnosis, multi-file investigation, dependency-impact summaries, test-selection rationale, runtime-error diagnosis, request/data-flow mapping, code-path comparison, change-surface summary, draft config-default test proposals, draft error-message assertion test proposals, and draft test-assertion update proposals.

Post-V1 Phase 40 adds controlled Batch B families through the lifecycle workflows: background job lookup, pytest fixture lookup, API reference lookup, and agent invariant lookup.

Post-V1 Phase 50 adds controlled Batch C families through the same lifecycle workflows: auth check lookup, state mutation lookup, external integration lookup, and error-handling path lookup. The Batch C validator intentionally probes natural prompts that include competing generic terms such as `related tests` so selector scoring is proved at the live gateway budget, not only in isolated registry tests.

Post-V1 Phase 63 validates and promotes controlled Batch D families through the same lifecycle workflows: handler branch tracing, table-schema-only lookup, runtime entrypoint disambiguation, and change-boundary summarization. Phase 63 proves each family through the workflow-router gateway and AnythingLLM on both frozen Coinbase fixtures before promotion.

Current shipped catalog:

- `50` validated skill registry entries
- `49` executable eval cases
- `D1-004` through `D1-006` draft-only skills route through the existing `execution_planning.plan` to `implementation.workflow` draft path

## Scale Operations

Phase 35 adds registry-scale checks for future large libraries:

- Route keys must use an approved namespace: `code`, `config`, `context`, `data`, `diagnostics`, `docs`, `draft`, `feedback`, `git`, `implementation`, `planning`, `test`, or `verification`.
- `draft.*`, `implementation.*`, and `feedback.*` route keys have strict workflow, safety, approval, and mutation ownership rules.
- Deprecated skills must declare `deprecation.replaced_by`, `deprecation.reason`, and `deprecation.effective_date`; replacements must exist and cannot be deprecated.
- Proposed batches fail when a new skill overlaps an existing skill's semantic intent in the same workflow and mutation boundary.
- The scale report includes coverage by workflow, output artifact, safety level, mutation policy, prompt family, and route namespace.

Phase 41 adds metadata-only selector-scale checks:

- Synthetic catalogs are generated at 100, 1,000, and 10,000 skill entries.
- Representative L1/L2 selector requests must return stable skill IDs and route keys across repeated runs.
- The 10,000-skill selector benchmark must complete within the documented threshold.
- Duplicate route-key, unsupported namespace, trigger-collision, semantic-overlap, and missing-eval-case fixtures must fail deterministically.
- Selection benchmarks must not load full skill bodies.

## Skill Release Gate

Phase 44 adds one release-gate command for the skill system. Phase 68 adds named profiles so the same command can run cheaper diagnostics without weakening the final release-candidate gate. Phase 81 adds the regression tier catalog in `runtime/skill_regression_tiers.json`, which maps common change types to the minimum expected skill-library proof.

```bash
python scripts/validate_skill_release_gate.py --profile offline
```

Profiles:

- `offline`: static registry, eval, scale, selector-scale, docs-index, skill registry/eval/selector regression, and focused skill-controller regression checks.
- `mutation`: `offline` plus disposable-copy mutation and fault-injection proof. The legacy `--offline-only` flag maps here to preserve the old gate's coverage.
- `live-smoke`: `mutation` plus the shortest Bash-hosted live lifecycle guard without AnythingLLM.
- `live-full`: `mutation` plus lifecycle, natural lifecycle, Batch C, and Batch D live guards without AnythingLLM.
- `release-candidate`: `live-full` with AnythingLLM included.

Each profile writes a durable report under `runtime-state/skill-release-gates/` with `profile`, `profile_contract`, catalog counts, workflow counts, route namespace counts, proof-file checks, rerun commands, and before/after hashes for watched runtime files and skill bodies.

Live profiles are intended to be run from Bash/WSL:

```bash
python3 scripts/validate_skill_release_gate.py --profile live-smoke
python3 scripts/validate_skill_release_gate.py --profile live-full
python3 scripts/validate_skill_release_gate.py --profile release-candidate
```

Use `release-candidate` when `ANYTHINGLLM_API_KEY` is available and AnythingLLM should be included in the proof. Legacy `--offline-only`, `--live`, and `--anythingllm` flags remain supported as aliases.

Validate the tier catalog:

```bash
python scripts/validate_skill_regression_tiers.py
```

Tier details: [README.skill-regression-tiers.md](README.skill-regression-tiers.md).

## Mutation And Fault Injection

Phase 48 adds `scripts/validate_skill_mutations.py`, a disposable-copy mutation gate for proving the skill system fails when it should fail.

The command creates one disposable registry copy per mutation, applies exactly one known-bad change, runs the relevant validator, records the expected failure code and observed failure code, and deletes the disposable copy. It also snapshots protected frozen fixture files before and after the run.

Covered mutations:

- duplicate route key
- missing skill body
- broken skill frontmatter
- unknown workflow
- unknown tool
- missing eval case
- stale live/release-gate proof
- deprecated replacement breakage
- route namespace drift

Run:

```bash
python scripts/validate_skill_mutations.py
```

Successful output means every planned mutation failed with its expected code, every disposable copy was restored or deleted, and protected frozen fixtures were not mutated. The release gate runs this command in offline, live, and AnythingLLM modes after Phase 48.

## Skill Selection Explanation Workflow

Phase 45 adds `skill.selection.explain`, a read-only controller workflow for answering: why was a skill selected, skipped, or excluded?

The workflow accepts:

- `user_request`: natural request text to evaluate
- optional `workflow_id`: skip workflow inference and explain selection for a specific workflow
- optional `target_root`: recorded for tester context only
- optional `max_candidate_count`: selected candidate limit from `1` through `20`

It returns selected skill IDs, route keys, trigger hits, workflow priorities, filtered-out reasons, deprecated exclusions, route namespace summary, and `body_reads_during_selection=0`.

The explanation path reads `runtime/skills.json` metadata only. It does not load `.qwen/skills/<skill>/SKILL.md`, does not mutate runtime registries, and does not mutate target repositories.

The workflow is available through:

- direct endpoint: `/v1/controller/skill-selection/explanations`
- harness envelope: `workflow=skill.selection.explain`
- safe natural workflow-router chat, for example: `Explain skill selection for: Explain what find_stealth_order_by_placed_order_id does.`

## Skill Batch Proposal Workflow

Phase 36 adds `skill_batch.propose`, a controller-owned proposal workflow for founder or maintainer requests such as:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, propose a skill batch for feature flag lookup. Proposal only. Do not register or append runtime skills.
```

The workflow creates draft artifacts only. It does not append to `runtime/skills.json`, `runtime/skill_evals.json`, or `.qwen/skills`.

Generated artifacts include:

- `request.json`
- draft `SKILL.md` files under the controller run output directory
- `batch.json`
- `batch-validation-report.json`
- `scale-report.json`
- `skill-batch-proposal.json`
- `run-state.json`

Ready proposals reuse existing workflow output artifacts such as `configuration_lookup` or `investigation_plan`. A proposal that needs a brand-new output artifact must wait for a separate approved workflow or artifact implementation phase. Duplicate or overlapping proposals return `do_not_admit` instead of creating a parallel skill path.

## Skill Batch Registration Workflow

Phase 37 adds `skill_batch.register`, a controller-owned registration workflow for approved Phase 36 proposal artifacts. It is the only supported structured path for turning a passed skill-batch proposal into runtime registry entries.

Registration requires an explicit approval object:

```json
{
  "status": "approved_for_skill_registration",
  "scope": "skill_batch_registration",
  "runtime_registry_append": true,
  "skill_body_install": true,
  "approval_refs": ["founder-review:<proposal-run-id>"]
}
```

The workflow accepts either `proposal_path` or `proposal_run_id`. It refuses proposals that are not `ready`, proposals with do-not-admit entries, failed batch validation, missing draft skill bodies, duplicate IDs, duplicate route keys, or expected output artifacts that are not already implemented by existing workflow/skill behavior.

Successful registration writes:

- approved `SKILL.md` bodies into `.qwen/skills/<skill-id>/SKILL.md`
- approved skill metadata into `runtime/skills.json`
- approved eval cases into `runtime/skill_evals.json`
- `skill-batch-registration.json`
- `skill-eval-report.json`
- `scale-report.json`
- `rollback-instructions.json`
- before/after hashes for runtime registry files and installed skill bodies

Natural workflow-router chat can also register a prior proposal run when the user explicitly asks to approve and register it, for example:

```text
Approve and register the skill batch proposal from run workflow-router-20260605T000000000000Z. Install it into the skill registry.
```

That natural path still produces the same `skill_batch.register` workflow request and approval object; it does not infer approval from vague wording.

## Skill Eval Promotion Workflow

Phase 38 adds `skill_eval.promote`, a controller-owned promotion workflow for registered draft skills. Promotion is the supported path from `eval_status: draft` to `eval_status: validated`; do not hand-edit that status in `runtime/skills.json`.

Promotion requires an explicit approval object:

```json
{
  "status": "approved_for_skill_promotion",
  "scope": "skill_eval_promotion",
  "eval_status_update": true,
  "approval_refs": ["founder-review:<registration-run-id>"]
}
```

The workflow accepts either `skill_ids` or a Phase 37 `registration_run_id`, normalizes to one sorted skill list, validates each skill body, registry entry, eval case, route key, workflow ownership, mutation policy, expected artifact, and live-suite mapping, then updates only `runtime/skills.json`.

Successful promotion writes:

- `skill-eval-promotion.json`
- `promotion-proof-plan.json`
- metadata eval and scale reports before and after promotion
- `rollback-instructions.json`
- before/after hashes for `runtime/skills.json` and `runtime/skill_evals.json`

The first implementation never mutates `runtime/skill_evals.json`. It changes only the promoted skill entries in `runtime/skills.json` by setting `eval_status=validated` and marking `evals.localhost_8000`, `evals.gateway_8300`, and `evals.anythingllm` as `passed`.

Promotion refuses missing approval, missing skills, deprecated skills, already validated skills unless `allow_repromotion=true`, missing eval cases, missing live-suite mappings, incomplete live proof for mapped L1/L2 cases, and proof artifacts outside approved roots.

## Skill Lifecycle Audit Workflow

Phase 39 adds `skill_lifecycle.audit`, a read-only lifecycle report for the skill registry. It answers the maintainer question: which skills should be promoted, kept as draft, revised, deprecated, or left alone?

The workflow is available through:

- direct endpoint: `/v1/controller/skill-lifecycle/audits`
- harness envelope: `workflow=skill_lifecycle.audit`
- natural workflow-router chat, for example: `Audit the skill lifecycle. Return counts, blockers, and next actions.`

The audit writes controller artifacts only. It never mutates `runtime/skills.json`, `runtime/skill_evals.json`, `.qwen/skills`, or target repositories.

Generated artifacts include:

- `request.json`
- `skill-eval-report.json`
- `scale-report.json`
- `skill-lifecycle-audit.json`
- `run-state.json`

The audit groups skills by `draft`, `validated`, `deprecated`, and `unknown`, then emits one next action per skill:

- `promote`: registered draft skill has enough proof for promotion
- `keep_draft`: draft skill is structurally valid but still lacks mapped live proof
- `revise`: skill has missing body, missing eval case, docs gap, route conflict, stale proof, or invalid lifecycle metadata
- `deprecate`: validated skill overlaps another skill's semantic intent and should not remain a parallel behavior path
- `no_action`: skill is valid for its current lifecycle state

Catalog findings also report orphan eval cases, route-key conflicts, semantic overlaps, registry validation errors, eval report status, scale report status, and runtime hash proof.

## Skill Deprecation Workflow

Phase 42 adds `skill.deprecate`, a controller-owned workflow for retiring one obsolete skill in favor of one route-compatible replacement. Deprecation is a metadata mutation only: it updates `runtime/skills.json`, does not edit `runtime/skill_evals.json`, and never deletes `.qwen/skills/<skill>/SKILL.md`.

Deprecation requires an explicit approval object:

```json
{
  "status": "approved_for_skill_deprecation",
  "scope": "skill_deprecation",
  "eval_status_update": true,
  "runtime_registry_update": true,
  "approval_refs": ["founder-review:<reason-or-run-id>"]
}
```

The workflow validates:

- deprecated skill exists and is not already deprecated
- replacement skill exists and is not deprecated
- replacement is not the same skill
- reason is descriptive and effective date uses `YYYY-MM-DD`
- replacement has compatible workflow, route namespace, safety level, mutation policy, and approval boundary
- post-deprecation registry, eval, and scale checks still pass
- normal selector output excludes the deprecated skill

Successful deprecation writes:

- `skill-deprecation.json`
- `skill-deprecation-plan.json`
- eval and scale reports before and after deprecation
- `rollback-instructions.json`
- before/after hashes proving only `runtime/skills.json` changed

The workflow is available through the direct endpoint `/v1/controller/skill-deprecations`, an explicit harness envelope with `workflow=skill.deprecate`, and Phase 49 natural workflow-router chat with exact approval-continuation wording.

## Skill Update Workflow

Phase 43 adds `skill.update`, a controller-owned workflow for changing one validated skill without hand-editing runtime registries, skill bodies, or eval cases. It supports metadata-only, skill-body-only, eval-case-only, and combined updates.

Every update requires an explicit approval object:

```json
{
  "status": "approved_for_skill_update",
  "scope": "skill_update",
  "runtime_registry_update": true,
  "skill_metadata_update": true,
  "skill_body_update": false,
  "eval_case_update": false,
  "approval_refs": ["founder-review:<reason-or-run-id>"]
}
```

Set `skill_body_update=true` when the request includes `skill_body_text`. Set `eval_case_update=true` when the request includes `eval_case_updates`. Metadata approval is always required because every update bumps the skill version in `runtime/skills.json`.

Semantic version rules are deterministic:

- `metadata_only`, `skill_body_only`, and `eval_case_only` require `version_bump=patch`.
- `combined` requires `version_bump=minor`.
- route-key changes require `version_bump=major` and a valid `deprecation_plan_ref`; route-key changes without a deprecation plan are rejected.

Successful updates write:

- `skill-update.json`
- `skill-update-plan.json`
- eval, scale, and selector-scale reports before or after the update
- `rollback-instructions.json`
- before/after hashes for every changed file

The workflow is available through `/v1/controller/skill-updates`, an explicit harness envelope with `workflow=skill.update`, and Phase 49 natural workflow-router chat with exact approval-continuation wording.

## Skill Eval Runner

The eval runner turns `runtime/skill_evals.json` into executable validation instead of passive metadata. The default mode is offline and does not require localhost services. It validates eval cases against known workflows, known artifacts, mutation-policy allowlists, and allowed live-suite names, then writes a JSON report under `runtime-state/skill-evals/` unless an output path is provided.

Mapped L1/L2 eval cases can also produce live-suite commands, or execute them when `--execute-live` is passed. Runtime live execution should be run from Bash/WSL because the gateway/controller stack is Bash-hosted.

## Safety

- Skill selection uses `runtime/skills.json`, not broad directory scanning.
- Runtime skill selection filters out skills whose mutation policy or approval boundary conflicts with the selected workflow.
- Runtime skill selection filters out skills with `eval_status: deprecated`.
- Full skill bodies are not loaded during workflow routing.
- Unknown workflows, tools, fixtures, eval cases, missing files, duplicate IDs, duplicate capability route keys, and malformed frontmatter fail validation.
- High-impact packet-design skills must use approval-gated safety metadata.
- Draft artifact mutation policy is allowed only with packet-design approval.
- Feedback-only skills may write controller artifacts but must not imply repository mutation.
- Admission proposals are isolated until `skill_batch.register` receives explicit approval and revalidates the proposal.

## Validation

```bash
pytest tests/regression/test_skill_registry.py -q
pytest tests/regression/test_skill_evals.py -q
python scripts/validate_skill_evals.py
python scripts/validate_skill_scale.py
python scripts/validate_skill_selector_scale.py
python scripts/validate_skill_release_gate.py --profile mutation
python scripts/validate_skill_batch.py --batch-file path/to/skill-batch.json
pytest tests/regression/test_controller_service.py -k skill_batch -q
pytest tests/regression/test_controller_service.py -k skill_eval_promotion -q
pytest tests/regression/test_controller_service.py -k skill_lifecycle -q
pytest tests/regression/test_controller_service.py -k skill_deprecation -q
pytest tests/regression/test_controller_service.py -k skill_update -q
pytest tests/regression/test_controller_service.py -k skill_selection -q
pytest tests/regression/test_controller_service.py -k "natural_skill_scaffold or natural_skill_pack or natural_skill_update or natural_skill_deprecation" -q
python scripts/validate_phase40_skill_batch_live.py --skip-anythingllm
python scripts/validate_phase50_skill_batch_live.py --skip-anythingllm
python scripts/validate_skill_natural_lifecycle_live.py --skip-anythingllm
```

Full regression remains required for release-candidate, cross-cutting runtime, shared controller/router/formatter, skill-library-scale, model-portability, or otherwise unbounded changes. For narrower changes, use the applicable verification tier and focused tests during iteration:

```bash
pytest tests/regression/ -v
```

## References

- Roadmap: [docs/ACTIONABLE_WORKFLOW_ROADMAP.md](docs/ACTIONABLE_WORKFLOW_ROADMAP.md)
- Examples: [docs/examples/skill-registry.md](docs/examples/skill-registry.md)
