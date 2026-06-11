# Release Candidate Founder Trial Pack

Phase 195 packages the current validated chat-quality surface into a short founder trial path.

Use this when a founder or tester needs to verify the product through AnythingLLM without reading session history.

## What It Includes

- AnythingLLM workflow-router target: `http://127.0.0.1:8500/v1`
- AnythingLLM API target: `http://127.0.0.1:3001`
- Frozen fixture roots:
  - `/mnt/c/coinbase_testing_repo_frozen_tmp`
  - `/mnt/c/coinbase_testing_repo_frozen_tmp.github`
- Setup and readiness commands
- Four smoke prompts from the governed founder prompt catalog
- Ten expanded read-only prompts after smoke passes
- Expected answer qualities and known limits
- Feedback templates tied to workflow-router run IDs
- Proof links for Phases 191 through 194
- Exact copy/paste prompt text in the generated report
- Fixture integrity commands and recovery instructions

The pack is governed by:

- `runtime/release_candidate_founder_trial_pack.json`
- `runtime/release_candidate_founder_trial_pack_policy.json`

## Run The Pack Validator

```bash
python3 scripts/validate_release_candidate_founder_trial_pack.py --require-proof-artifacts
```

Expected marker:

```text
PHASE195 RELEASE CANDIDATE FOUNDER TRIAL PACK PASS
```

The validator writes:

- `runtime-state/phase195/phase195-release-candidate-founder-trial-pack-report.json`
- `runtime-state/phase195/phase195-release-candidate-founder-trial-pack-report.md`

## Manual Trial Order

1. Start the local harness with `start-agent-prompt-proxies.sh`.
2. Confirm AnythingLLM points to `http://127.0.0.1:8500/v1`.
3. In AnythingLLM, configure a Generic OpenAI-compatible provider:
   - Base URL: `http://127.0.0.1:8500/v1`
   - Model: `Qwen3-Coder-30B-A3B-Instruct`
   - Workspace: `my-workspace`
   - API key: any non-empty value for the provider UI
4. Verify the router gateway responds:

```bash
curl -fsS http://127.0.0.1:8500/v1/models
```

5. Verify AnythingLLM is running:

```bash
curl -fsS http://127.0.0.1:3001
```

6. Run `python3 scripts/run_first_time_user_doctor.py`.
7. Run `python3 scripts/validate_post_restart_runtime_readiness.py`.
8. Run `python3 scripts/validate_release_candidate_founder_trial_pack.py --require-proof-artifacts`.
9. Run `python3 scripts/validate_release_candidate_founder_trial_pack.py --require-proof-artifacts --validate-fixture-state`.
10. In a fresh AnythingLLM chat, run the four smoke prompts from the report.
11. If smoke prompts pass, run the expanded read-only prompts.
12. Record feedback using the included templates and the returned `workflow-router-...` run IDs.

Print copy/paste prompt text:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase195/phase195-release-candidate-founder-trial-pack-report.json").read_text())
for case in report["selected_case_summaries"]:
    print(f"\n[{case['case_id']}]")
    print(case["prompt"])
PY
```

## Fixture Safety

The release pack validator can check live fixture readiness:

```bash
python3 scripts/validate_release_candidate_founder_trial_pack.py --require-proof-artifacts --validate-fixture-state
```

If the git-enabled fixture is already dirty, this command fails before prompt testing. Treat that as fixture drift to resolve before trusting founder trial results.

Before and after prompt testing, check the frozen fixtures:

```bash
git -C /mnt/c/coinbase_testing_repo_frozen_tmp.github status --short
find /mnt/c/coinbase_testing_repo_frozen_tmp -type f -print0 | sort -z | xargs -0 sha256sum > runtime-state/phase195/non-git-fixture.before.sha256
# run trial prompts
find /mnt/c/coinbase_testing_repo_frozen_tmp -type f -print0 | sort -z | xargs -0 sha256sum > runtime-state/phase195/non-git-fixture.after.sha256
diff -u runtime-state/phase195/non-git-fixture.before.sha256 runtime-state/phase195/non-git-fixture.after.sha256
```

The git fixture should have no unexpected source changes. The non-git fixture diff should be empty. Stop testing if either fixture changes.

## Feedback Destination

Store structured founder feedback in:

```text
runtime-state/phase195/founder-feedback.jsonl
```

Each record should include `case_id`, `prompt`, `target_run_id`, `classification`, `severity`, `actual_response_excerpt`, `expected_behavior`, `fixture_root`, and `created_at`.

Allowed classifications are `answer_quality`, `confusing`, and `routing`. Allowed severities are `advisory` and `blocker`.

## Recovery

- Stale proxies: run `bash stop-agent-prompt-proxies.sh`, confirm vLLM is live, then run `bash start-agent-prompt-proxies.sh`.
- AnythingLLM down: open or restart the AnythingLLM Desktop app, wait for `http://127.0.0.1:3001` to respond, then rerun post-restart readiness.
- Wrong AnythingLLM target: set the provider base URL back to `http://127.0.0.1:8500/v1`.
- Missing API key: export `ANYTHINGLLM_API_KEY` before API validation.
- Dirty fixture: stop testing, restore the fixture, and rerun post-restart readiness.
- Failed doctor: fix `failed_check_ids` before running founder prompts.

## Boundaries

Advanced broad refactor orchestration is not released. Mutation-capable prompts are not part of this founder trial pack.

Examples: [docs/examples/release-candidate-founder-trial-pack.md](docs/examples/release-candidate-founder-trial-pack.md).
