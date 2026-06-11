# Skill Registry Readiness Review

Phase 193 reviews whether the current skill registry is ready for more L1/L2 skill-library scaling. It does not add or select skills. It composes existing registry, scale, and prompt-coverage validators into one readiness report with deterministic keep, split, merge, retire, and defer decisions.

## What It Checks

- `runtime/skills.json`
- `runtime/skill_evals.json`
- `runtime/prompt_skill_coverage.json`
- `runtime/workflows.json`
- `runtime/tools.json`
- source reports from skill-scale and prompt-skill coverage validators

The current result is:

- `54` skills reviewed
- `54` skills marked `keep`
- `0` split, merge, or retire decisions
- `0` semantic conflicts
- `2` planned fixture-generalization coverage entries kept outside validated readiness until implementation and eval proof are approved

Each skill record separates:

- `coverage_entry_ids`: implemented prompt-coverage evidence only
- `planned_coverage_entry_ids`: planned or deferred coverage that is not valid readiness proof yet
- `readiness_evidence`: body, route, trigger, workflow, eval, and coverage checks used to justify the decision

## Run

```bash
python3 scripts/validate_skill_registry_readiness_review.py
```

The command writes:

- `runtime-state/phase193/phase193-skill-registry-readiness-review-report.json`
- `runtime-state/phase193/phase193-skill-registry-readiness-review-report.md`
- `runtime-state/phase193/phase193-skill-scale-source.json`
- `runtime-state/phase193/phase193-prompt-skill-coverage-source.json`

## Passing Standard

The report must have:

- `status=passed`
- all validated skills classified with an explicit readiness decision
- concrete readiness evidence for each skill decision
- no planned-only coverage treated as implemented readiness evidence
- zero split, merge, or retire decisions
- zero semantic conflicts
- passing skill-scale and prompt-skill coverage source reports
- no hidden report edits after rebuild validation

Any future split, merge, or retire decision is a blocker for skill-library scaling and must become a bounded roadmap repair before more skills are added.
