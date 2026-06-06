# Model Portability Gate

The model portability gate checks whether the current workflow-router harness still works when the local stack is pointed at a named model candidate.

It does not change routing, prompts, skills, or workflow behavior. It wraps the existing V1 acceptance gate, records the model candidate metadata, probes the candidate OpenAI-compatible `/models` endpoint, and classifies misses as:

- `harness`
- `classifier`
- `prompt`
- `model_quality`
- `unknown`

Use this before treating a smaller local model as supported.

## When To Use It

Use this gate when:

- the vLLM server on `localhost:8000` has been changed to a smaller model
- `start-agent-prompt-proxies.sh` was restarted with a different `VLLM_BASE_URL`
- AnythingLLM is still pointed at the workflow-router gateway
- you need evidence that the candidate works through localhost `8000`, gateway/controller ports, AnythingLLM, and both frozen Coinbase fixtures

Do not use this as automatic model selection. Phase 72 only measures and classifies. Later phases turn this evidence into capability profiles and routing policy.

Phase 78 added that next step as an advisory profile generator. After a portability report exists, use [README.model-capability-profiles.md](README.model-capability-profiles.md) to generate the model capability profile and review the routing policy.

## Runtime Setup

Start the stack from Bash after pointing it at the candidate model:

```bash
cd /mnt/c/agentic_agents
./stop-agent-prompt-proxies.sh
VLLM_BASE_URL=http://127.0.0.1:8000 \
CONTROLLER_ALLOWED_TARGET_ROOTS="/mnt/c/agentic_agents:/mnt/c/coinbase_testing_repo_frozen_tmp:/mnt/c/coinbase_testing_repo_frozen_tmp.github" \
CONTROLLER_DEFAULT_ROLE_BASE_URL=http://127.0.0.1:8300/v1 \
./start-agent-prompt-proxies.sh
```

AnythingLLM should target:

```text
http://127.0.0.1:8500/v1
```

## Run

From Bash:

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/validate_model_portability.py \
  --candidate-id smaller-local-candidate \
  --candidate-description "Smaller local model candidate behind localhost:8000" \
  --candidate-model-base-url http://127.0.0.1:8000/v1 \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --controller-base-url http://127.0.0.1:8400 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --timeout-seconds 900 \
  --command-timeout-seconds 3600
```

Expected final marker when the candidate passes:

```text
MODEL PORTABILITY PASS
```

Reports are written under:

```text
runtime-state/model-portability/
```

The portability report links the nested V1 acceptance report and includes:

- candidate ID and configured URLs
- model IDs returned by `/v1/models`
- V1 acceptance status
- classification summary
- classified failures with recommended next actions

Generate the advisory capability profile from the report:

```bash
python scripts/generate_model_capability_profile.py \
  --portability-report-path runtime-state/model-portability/phase72-live-current.json \
  --output-path runtime-state/model-capability-profiles/phase78-live-current-profile.json \
  --markdown-output-path runtime-state/model-capability-profiles/phase78-live-current-profile.md
```

## Classify An Existing V1 Report

Use this when a V1 run already exists and you only need classification:

```bash
python3 scripts/validate_model_portability.py \
  --candidate-id smaller-local-candidate \
  --skip-live-acceptance \
  --skip-model-probe \
  --acceptance-report-path runtime-state/v1-acceptance/phase71-v1-acceptance.json
```

## Interpreting Results

- `harness`: fix ports, AnythingLLM, API key, timeouts, fixture mutation, or report loading before judging the model.
- `classifier`: inspect route-decision artifacts and prompt-matrix coverage.
- `prompt`: keep the miss documented and test the refined prompt before changing router behavior.
- `model_quality`: inspect the failed output and consider smaller context, stronger artifact rendering, or a stronger model profile.
- `unknown`: inspect the referenced report and add a narrower classification rule if the same failure repeats.

## Safety

- The gate reuses the existing V1 acceptance path.
- Protected frozen fixtures are watched by the nested V1 gate.
- No source mutation is allowed except existing approved disposable-copy tests inside the V1 acceptance profile.
- The gate does not promote or reject a model automatically.
