# Prompt Skill Coverage

Prompt skill coverage is the canonical map from natural-language prompt families to controller workflows, route rules, skills, tools, eval gates, expected artifacts, docs, and known gaps.

It keeps L1/L2 growth from becoming a scattered set of prompt examples and tests.

## Registry

The registry lives at:

```text
runtime/prompt_skill_coverage.json
```

It contains:

- implemented L1 prompt families
- implemented D1 draft-only prompt families
- implemented L2 prompt families
- controller-owned workflow families
- planned or deferred gaps

The broad single-path refactor prompt is recorded as deferred and must not re-enter active L1/L2 scope without a later approved advanced phase.

## Validate

```bash
python scripts/validate_prompt_skill_coverage.py \
  --output-path runtime-state/prompt-skill-coverage/phase79-current.json
```

Expected marker:

```text
PROMPT SKILL COVERAGE PASS
```

## What The Validator Checks

For implemented entries, the validator checks:

- selected workflow exists in `runtime/workflows.json`
- route rule exists in `workflow_router.plan`
- skill IDs exist and support the selected workflow
- tool IDs exist in `runtime/tools.json`
- eval case IDs exist and match the selected workflow
- controller-owned entries have regression refs when they do not have skill evals
- docs/examples links exist
- governed founder-field prompt catalog route rules are covered
- advanced single-path refactor remains in the deferred backlog

## Report

Validation reports are written under:

```text
runtime-state/prompt-skill-coverage/
```

The report kind is:

```text
prompt_skill_coverage_report
```

## Reference

See [docs/PROMPT_SKILL_COVERAGE_MAP.md](docs/PROMPT_SKILL_COVERAGE_MAP.md) for the registry shape, gap rules, and update workflow.
