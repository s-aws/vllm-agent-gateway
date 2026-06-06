# Skill Registry

The skill registry is the canonical metadata surface for project-local planning skills.

It is not a runtime tool and it does not expose arbitrary skill bodies to the model. The router selects skill IDs from metadata first, then downstream workflows may load only the selected skill bodies they already support.

## Files

- `runtime/skills.json`: canonical skill metadata.
- `runtime/skill_evals.json`: shared eval fixture and eval-case catalog.
- `vllm_agent_gateway/skills/registry.py`: registry validation, admission validation, and metadata-only selection.
- `vllm_agent_gateway/skills/evals.py`: executable eval-catalog validation and optional L1/L2 live-suite mapping.
- `vllm_agent_gateway/skills/batches.py`: proposed batch validation before appending new skills and eval cases to runtime registries.
- `scripts/validate_skill_evals.py`: CLI that writes durable skill eval reports.
- `scripts/validate_skill_batch.py`: focused CLI for skill-batch dry-run admission reports.
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

## Seed V1 Skill Library

The V1 seed adds task-specific read-only skills for validated L1/L2 coding-agent prompt families. These skills do not create new runtime workflows. They sit behind the same registry selection path and use priority `1000`, which means they are selected only when their trigger terms match the request.

Seeded V1 and post-V1 Phase 30/31/32 families include code explanation, related-test discovery, safe test-command selection, behavior-existence checks, callers/usages summaries, configuration lookup, pasted-failure summaries, endpoint/route lookup, error/log/message source lookup, module summary, data model/schema lookup, dependency/import lookup, coverage-gap summary, documentation lookup, CLI/script entrypoint lookup, configuration runtime-effect summary, local-change summary, failing-test diagnosis, multi-file investigation, dependency-impact summaries, test-selection rationale, runtime-error diagnosis, request/data-flow mapping, code-path comparison, and change-surface summary.

## Skill Eval Runner

The eval runner turns `runtime/skill_evals.json` into executable validation instead of passive metadata. The default mode is offline and does not require localhost services. It validates eval cases against known workflows, known artifacts, mutation-policy allowlists, and allowed live-suite names, then writes a JSON report under `runtime-state/skill-evals/` unless an output path is provided.

Mapped L1/L2 eval cases can also produce live-suite commands, or execute them when `--execute-live` is passed. Runtime live execution should be run from Bash/WSL because the gateway/controller stack is Bash-hosted.

## Safety

- Skill selection uses `runtime/skills.json`, not broad directory scanning.
- Runtime skill selection filters out skills whose mutation policy or approval boundary conflicts with the selected workflow.
- Full skill bodies are not loaded during workflow routing.
- Unknown workflows, tools, fixtures, eval cases, missing files, duplicate IDs, duplicate capability route keys, and malformed frontmatter fail validation.
- High-impact packet-design skills must use approval-gated safety metadata.
- Draft artifact mutation policy is allowed only with packet-design approval.
- Feedback-only skills may write controller artifacts but must not imply repository mutation.
- Admission proposals are isolated until a maintainer or future controller workflow explicitly appends the validated skill and eval case.

## Validation

```bash
pytest tests/regression/test_skill_registry.py -q
pytest tests/regression/test_skill_evals.py -q
python scripts/validate_skill_evals.py
python scripts/validate_skill_batch.py --batch-file path/to/skill-batch.json
```

Full regression remains required after code changes:

```bash
pytest tests/regression/ -v
```

## References

- Roadmap: [docs/ACTIONABLE_WORKFLOW_ROADMAP.md](docs/ACTIONABLE_WORKFLOW_ROADMAP.md)
- Examples: [docs/examples/skill-registry.md](docs/examples/skill-registry.md)
