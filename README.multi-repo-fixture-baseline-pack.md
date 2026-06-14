# Multi-Repo Fixture Baseline Pack

Phase 209 selects the first non-Coinbase M5 generalization fixture and creates a blind-baseline prompt pack before local-model comparison or repairs.

The selected fixture is `s-aws/staterail`, cloned locally at:

```text
/mnt/c/staterail_testing_repo_frozen_tmp.github
```

The fixture is approved for scoped project work only under a no-commit/no-push boundary. The project may read source, docs, and tests, run tests, create disposable mutation copies, and use the fixture for gateway or AnythingLLM validation. It must not commit to, push to, publish branches for, or otherwise mutate the upstream `s-aws/staterail` repository.

## What It Checks

- The local `staterail` fixture exists and is a git checkout.
- The fixture is pinned to commit `d3cecac670e3dd185cd3289feecae6ec69bab0b3`.
- The fixture worktree is clean.
- File-count expectations still match the selected fixture shape.
- The prompt pack covers code explanation, behavior beginning point, related tests, change surface, and validation commands.
- Each case has source hints, test hints, safety boundaries, output-format expectations, and a 100-point blind-baseline scoring rubric.
- Phase 209 does not run local-model comparison or mutate the fixture.

## Inputs

- `runtime/multi_repo_fixture_baseline_pack_policy.json`
- `/mnt/c/staterail_testing_repo_frozen_tmp.github`

## Outputs

- `runtime-state/phase209/phase209-multi-repo-fixture-baseline-pack-report.json`
- `runtime-state/phase209/phase209-multi-repo-fixture-baseline-pack-report.md`

## Validation

Run from Bash/WSL:

```bash
python3 scripts/validate_multi_repo_fixture_baseline_pack.py
```

Focused regression:

```bash
python3 -m pytest tests/regression/test_multi_repo_fixture_baseline_pack.py -q
```

Expected passing marker:

```text
PHASE209 MULTI REPO FIXTURE BASELINE PACK PASS
```

## Next Step

Phase 210 uses this prompt pack to run the current gateway and AnythingLLM stack against `staterail`, then compares local answers against the blind baselines without making repairs.
