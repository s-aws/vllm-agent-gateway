# Skill Authoring Factory

The skill authoring factory is the Phase 80 extension of `skill.scaffold`.

It generates reviewable draft artifacts for a small deterministic skill from one prompt-family specification. It does not install, promote, or mutate runtime skill state.

Use it when a prompt family is understood well enough to draft the first skill package, but not yet proven well enough to enter the active skill library.

## Generated Artifacts

`skill.scaffold` now emits:

- `draft_skill_body`: draft `SKILL.md` with frontmatter.
- `draft_batch_manifest`: skill registry metadata plus eval case in batch form.
- `batch_validation_report`: existing batch admission proof.
- `prompt_coverage_entry`: planned coverage entry for `runtime/prompt_skill_coverage.json`.
- `eval_skeleton`: required routing, artifact, chat-output, and coverage gates.
- `docs_stub`: feature README draft for the skill.
- `docs_example_stub`: example prompt draft.
- `regression_test_skeleton`: fail-closed pytest skeleton for the four minimum gates.
- `authoring_factory_report`: naming, namespace, version, lifecycle, docs, coverage, eval, and promotion-state checks.
- `validation_checklist`: scaffold-level review checklist.
- `skill_scaffold`: complete scaffold report.
- `run_state`: resumable run state.

## Promotion Boundary

Scaffolding is intentionally dry-run only.

Generated skills remain `draft` and carry `promotion_state: not_promoted_by_scaffold`. The generated regression skeleton intentionally calls `pytest.fail` for routing, artifact contract, natural-language chat output, and prompt coverage until the required metadata and eval proof are installed through the approved lifecycle path.

Do not copy scaffold output into runtime registries by hand. Use reviewed `skill_batch.register` or governed `skill_pack.install` with explicit approval.

## Minimum Input

The request must include:

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

Optional Phase 80 fields:

- `coverage_id`
- `level`
- `route_rule`
- `tool_ids`

`output_artifact` must already be a known workflow, skill, or manual artifact. The scaffold will not invent new artifact contracts.

## Review Order

1. Inspect `batch_validation_report`.
2. Inspect `authoring_factory_report`.
3. Review `prompt_coverage_entry` and keep it planned until the skill is installed.
4. Fill in and enable the generated regression skeleton only after the route rule, metadata, eval case, docs, and chat output are actually wired.
5. Promote only after the relevant eval gates pass.

## Live Validation

After starting the stack, run from Bash:

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="${ANYTHINGLLM_API_KEY:?set AnythingLLM API key first}"
python3 scripts/validate_skill_authoring_factory_live.py --timeout-seconds 900
```

Use `--skip-anythingllm` only when validating controller and gateway behavior without the AnythingLLM workspace API.

Examples: [docs/examples/skill-authoring-factory.md](docs/examples/skill-authoring-factory.md).
