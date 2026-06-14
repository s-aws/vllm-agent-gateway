# Multi-Repo Baseline Comparison

Phase 210 runs the Phase 209 `s-aws/staterail` prompt pack through the current local stack and records comparison gaps without making repairs.

This is a dry-run comparison gate. It does not change router, controller, workflow, skill, formatter, or `s-aws/staterail` source behavior.

## What It Checks

- Phase 209 fixture and prompt-pack proof is still valid.
- The current workflow-router gateway can answer each Phase 209 prompt.
- AnythingLLM can answer each user-facing prompt when configured.
- Each response has a controller run id and completed run record.
- The selected workflow matches `code_investigation.plan`.
- Chat output includes required answer and no-mutation markers.
- Chat output exposes at least one Phase 209 source or test hint.
- The `staterail` fixture git status remains unchanged.
- Any misses are classified as route, evidence, formatter, missing skill/tool, repo-shape, model capability, unsupported scope, or runtime surface gaps.

## Inputs

- `runtime/multi_repo_baseline_comparison_policy.json`
- `runtime/multi_repo_fixture_baseline_pack_policy.json`
- `runtime-state/phase209/phase209-multi-repo-fixture-baseline-pack-report.json`
- `/mnt/c/staterail_testing_repo_frozen_tmp.github`

## Outputs

- `runtime-state/phase210/phase210-multi-repo-baseline-comparison-report.json`
- `runtime-state/phase210/phase210-multi-repo-baseline-comparison-report.md`

## Validation

Offline preflight:

```bash
python3 scripts/validate_multi_repo_baseline_comparison.py
```

Focused live smoke while iterating:

```bash
python3 scripts/validate_multi_repo_baseline_comparison.py --live --allow-partial \
  --skip-anythingllm \
  --case-id P209-SR-001
```

Full live closeout after model, gateway/proxies, controller, and AnythingLLM are running:

```bash
python3 scripts/validate_multi_repo_baseline_comparison.py --live --timeout-seconds 900
```

Focused regression:

```bash
python3 -m pytest tests/regression/test_multi_repo_baseline_comparison.py -q
```

## Safety Boundary

Do not commit or push to `s-aws/staterail`. If a later repair requires mutation testing, mutate only a disposable copy and keep this fixture clean.
