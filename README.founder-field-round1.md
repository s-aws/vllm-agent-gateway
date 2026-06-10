# Founder Field Round 1

Phase 157 runs the next founder field-test round through the current V1 release path.

This phase uses the existing founder field runner, [scripts/run_founder_field_prompt_eval.py](scripts/run_founder_field_prompt_eval.py). It does not create a second AnythingLLM harness.

## What It Tests

- AnythingLLM API at `http://127.0.0.1:3001`
- workflow-router gateway at `http://127.0.0.1:8500/v1`
- current localhost model behind `http://127.0.0.1:8000/v1`
- both frozen Coinbase fixtures:
  - `/mnt/c/coinbase_testing_repo_frozen_tmp`
  - `/mnt/c/coinbase_testing_repo_frozen_tmp.github`

The Phase 157 policy selects 30 natural-language prompts from the governed founder field catalog:

- `P01` through `P22`
- `P27` through `P34`

The first round intentionally excludes `P23` through `P26` because those are draft/apply-oriented prompts. Phase 157 focuses on current read-only, task-decomposition, and deterministic skill-backed founder testing before returning to mutation-oriented workflows.

## What It Produces

Live founder field run:

```text
runtime-state/founder-field-round1/phase157/phase157-founder-field-run.json
runtime-state/founder-field-round1/phase157/phase157-founder-field-run.md
```

Phase 157 governance report:

```text
runtime-state/founder-field-round1/phase157/phase157-founder-field-round1-report.json
runtime-state/founder-field-round1/phase157/phase157-founder-field-round1-report.md
```

The governance report includes:

- case count
- pass, advisory, and blocker counts
- target roots
- selected workflows
- per-case run IDs
- per-case response hash
- per-case quality classification
- fixture mutation proof
- release limitations
- whether Phase 158 feedback intake is required

## Quality Classifications

- `pass`: prompt passed and has no prompt-risk advisory.
- `advisory`: prompt passed but carries prompt-risk wording that should be reviewed during Phase 158.
- `blocker`: prompt failed output-contract or semantic-quality checks and must be classified in Phase 158.

Phase 157 can pass with advisory or blocker cases if the field-test evidence is complete. Missing evidence, missing run IDs, missing target-root coverage, fixture mutation, or malformed reports fail Phase 157 itself.

## Current Closeout

The latest Phase 157-161 chain is closed for founder testing:

- Phase 157: `case_count=30`, `pass_case_count=16`, `advisory_case_count=14`, `blocker_case_count=0`.
- Phase 158: all 14 accepted findings are `prompt_issue`; `phase159_eligible_count=0`.
- Phase 159: `repair_mode=no_repair_required`.
- Phase 160: `readiness=ready_for_founder_testing`, `decision=release_for_founder_testing`.
- Phase 161: `decision=no_new_batch_justified`, `gap_candidate_count=0`.

The 14 advisory cases should be treated as prompt wording risks. They do not authorize a new skill/tool implementation batch unless a later governed Phase 161-style report produces bounded candidates.

## Run

Run from Bash/WSL:

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_founder_field_round1.py \
  --run-live \
  --output-path runtime-state/founder-field-round1/phase157/phase157-founder-field-round1-report.json \
  --markdown-output-path runtime-state/founder-field-round1/phase157/phase157-founder-field-round1-report.md \
  --field-report-path runtime-state/founder-field-round1/phase157/phase157-founder-field-run.json \
  --field-markdown-output-path runtime-state/founder-field-round1/phase157/phase157-founder-field-run.md \
  --timeout-seconds 900
```

If WSL does not inherit `ANYTHINGLLM_API_KEY`, pass it explicitly from PowerShell without printing it:

```powershell
wsl.exe --cd /mnt/c/agentic_agents -- env "ANYTHINGLLM_API_KEY=$env:ANYTHINGLLM_API_KEY" python3 scripts/validate_founder_field_round1.py --run-live
```

Expected marker:

```text
PHASE157 FOUNDER FIELD ROUND PASS
```

Examples: [docs/examples/founder-field-round1.md](docs/examples/founder-field-round1.md).
