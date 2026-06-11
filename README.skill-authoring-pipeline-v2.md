# Skill Authoring Pipeline V2

Phase 194 defines the repeatable draft-packet admission path for turning an observed prompt gap into a small deterministic L1/L2 skill candidate.

It does not install, prove, or promote skills. It validates that a draft authoring packet is complete enough for review before any runtime registry mutation is allowed.

## What It Checks

The V2 gate reviews one draft candidate at a time:

- `skill-batch.json`: draft skill metadata and matching eval case, validated by existing skill batch admission
- draft `SKILL.md`: skill body with frontmatter, kept under the candidate root
- `prompt-coverage-entry.json`: planned coverage entry, not implemented coverage
- `eval-skeleton.json`: required gates for routing, artifact contract, chat output, coverage, blind baseline, holdouts, live gateway, AnythingLLM, and fixture parity
- docs stub and example stub
- fail-closed regression test skeleton
- `authoring-pipeline-plan.json`: prompt examples, holdouts, objective acceptance criteria, blind-baseline-first plan, and live validation plan

The current sample candidate is:

- `tests/fixtures/skill_authoring_pipeline_v2/phase194-readme-locator`

## Promotion Boundary

The gate must keep candidate state as draft-only:

- no manual prompt injection
- no runtime registry mutation
- no direct append to `runtime/skills.json`, `runtime/skill_evals.json`, or `runtime/prompt_skill_coverage.json`
- no implemented prompt-coverage claim before live proof exists
- `packet_status=admitted` is not promotion readiness
- `proof_status=not_run` remains true until target, holdout, live, and AnythingLLM evidence is collected
- `promotion_eligible=false` remains true for every Phase 194 pass

Promotion requires the later approved lifecycle path after blind-baseline-first proof, target and holdout prompts, live gateway and AnythingLLM validation, both frozen fixture roots, and passing regression gates.

## Run

```bash
python3 scripts/validate_skill_authoring_pipeline_v2.py
```

The command writes:

- `runtime-state/phase194/phase194-skill-authoring-pipeline-v2-report.json`
- `runtime-state/phase194/phase194-skill-authoring-pipeline-v2-report.md`
- `runtime-state/phase194/phase194-skill-authoring-pipeline-v2-batch-report.json`

## Passing Standard

The report must have:

- `status=passed`
- `gate_scope=draft_packet_admission_only`
- `packet_status=admitted`
- `proof_status=not_run`
- `promotion_eligible=false`
- existing skill registry readiness from Phase 193 still passing
- batch admission passing for the draft candidate
- candidate skill, eval case, and coverage IDs absent from runtime registries
- watched runtime registry hashes unchanged before and after validation
- planned prompt coverage, not implemented coverage
- all required eval gates present and not run yet
- at least two target prompt examples and two holdout prompts
- at least three objective acceptance criteria with verification evidence
- live validation plan covering localhost `8000`, gateway `8300`, controller `8400`, workflow-router `8500`, documenter `8205`, AnythingLLM, and both frozen Coinbase fixture roots

Examples: [docs/examples/skill-authoring-pipeline-v2.md](docs/examples/skill-authoring-pipeline-v2.md).
