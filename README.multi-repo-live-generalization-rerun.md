# Multi-Repo Live Generalization Rerun

Phase 212 proves the repaired M5 behavior live through the workflow-router gateway and AnythingLLM across the selected non-Coinbase fixture and Coinbase holdouts.

This gate is stricter than the Phase 210 dry run. It fails closeout if any response has a route, evidence, formatter, runtime, model capability, unsupported-scope, or fixture-mutation gap.

## What It Checks

- Phase 209 Staterail target cases still pass after Phase 211 repairs.
- Holdout prompts cover `/mnt/c/staterail_testing_repo_frozen_tmp.github`, `/mnt/c/coinbase_testing_repo_frozen_tmp.github`, and `/mnt/c/coinbase_testing_repo_frozen_tmp`.
- Gateway and AnythingLLM both return chat-visible answers with run ids.
- Each controller run completes through `code_investigation.plan`.
- Chat output includes required answer and no-mutation markers.
- Chat output cites at least one expected source or test hint.
- Git-backed fixtures remain clean.
- Non-git fixtures keep bounded source/test hint hashes unchanged.

## Inputs

- `runtime/multi_repo_live_generalization_rerun_policy.json`
- `runtime/multi_repo_fixture_baseline_pack_policy.json`
- `runtime-state/phase210/phase210-multi-repo-baseline-comparison-report.json`
- `/mnt/c/staterail_testing_repo_frozen_tmp.github`
- `/mnt/c/coinbase_testing_repo_frozen_tmp.github`
- `/mnt/c/coinbase_testing_repo_frozen_tmp`

## Outputs

- `runtime-state/phase212/phase212-multi-repo-live-generalization-rerun-report.json`
- `runtime-state/phase212/phase212-multi-repo-live-generalization-rerun-report.md`
- `runtime-state/phase212/phase212-multi-repo-live-generalization-rerun-preflight-report.json`
- `runtime-state/phase212/phase212-multi-repo-live-generalization-rerun-preflight-report.md`

## Validation

Offline preflight:

```bash
python3 scripts/validate_multi_repo_live_generalization_rerun.py
```

The default preflight command writes to the `*-preflight-report.*` paths so it does not overwrite the last live closeout proof.

Focused gateway smoke:

```bash
python3 scripts/validate_multi_repo_live_generalization_rerun.py --live --allow-partial \
  --skip-anythingllm \
  --case-id P212-HO-CB-GIT-001
```

Full live closeout:

```bash
python3 scripts/validate_multi_repo_live_generalization_rerun.py --live --timeout-seconds 900
```

Focused regression:

```bash
python3 -m pytest tests/regression/test_multi_repo_live_generalization_rerun.py -q
```

## Safety Boundary

Do not commit or push to `s-aws/staterail`. Do not mutate protected frozen fixture source files. Use disposable copies for mutation tests.
