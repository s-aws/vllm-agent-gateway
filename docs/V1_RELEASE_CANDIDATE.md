# V1 Release Candidate Report

Created from Phase 55 validation on June 5, 2026. Updated through Phase 90 V1.1 release-candidate validation on June 6, 2026.

## Candidate Scope

V1 is a natural-language workflow-router product for local coding-agent harnesses. The tested first-user path is AnythingLLM pointing at the workflow-router OpenAI-compatible gateway:

```text
http://127.0.0.1:8500/v1
```

The local model remains behind the controller/gateway stack at:

```text
http://127.0.0.1:8000/v1
```

The controller service remains an HTTP API, not an OpenAI model endpoint:

```text
http://127.0.0.1:8400
```

## Feature Matrix

| Capability | Status | Acceptance Proof |
| --- | --- | --- |
| Natural workflow routing through AnythingLLM | Supported | `validate_v1_acceptance.py` via `8500/v1` |
| Chat-visible `format_a` output | Supported | inline answer suite plus JSON output checks |
| JSON output selector | Supported | gateway and AnythingLLM JSON checks on both frozen repos |
| L1 read-only code explanation | Supported | representative `L1-002` gateway and AnythingLLM checks |
| L1 draft-only small text/doc edit | Supported | representative `L1-010` gateway and AnythingLLM checks |
| L2 read-only test-selection rationale | Supported | representative `L2-005` gateway and AnythingLLM checks |
| Multi-step task decomposition | Supported | direct controller, gateway, AnythingLLM, FormatA, and JSON validation |
| Controlled small-change dry-run | Supported | direct controller patch-preview validation |
| Controlled disposable-copy apply | Supported | gateway and AnythingLLM apply-boundary validation with rollback proof |
| Protected frozen source apply | Blocked | direct real-apply refusal with `protected_frozen_real_apply_denied` |
| Founder/tester feedback capture | Supported | gateway and AnythingLLM feedback records linked to prior run IDs |
| Founder field prompt release gate | Supported | `runtime/prompt_catalogs/founder_field_v1.json` drives `run_founder_field_prompt_eval.py`, and the suite is included in `validate_v1_acceptance.py` |
| Prompt matrix diagnostic | Supported | `validate_founder_field_prompt_matrix.py` checks original and refined prompt classifier rules offline |
| V1.1 consolidated release gate | Supported | `validate_v1_acceptance.py --profile v1.1-release-candidate` includes setup, docs, release-channel, security, observability, model, onboarding, workflow, JSON, feedback, and fixture proof |

Broader L1/L2 prompt suites exist and should be run during extended testing. The current release-candidate command includes representative suites plus the founder field prompt gate so first-user validation proves both narrow known-good cases and realistic founder wording.

The current V1.1 release-candidate profile is the preferred broad tester gate. The older `release-candidate` profile remains available for compatibility.

## Supported Prompt Families

Validated L1 prompt families include behavior start lookup, function/file explanation, related tests, configuration lookup, pasted failure summary, behavior-existence check, callers/usages, safe test command, small unit-test draft, small text/doc draft, simple failing-test draft, endpoint/route lookup, message source lookup, module summary, data model/schema lookup, and dependency/import lookup.

Validated L2 prompt families include failing-test diagnosis, multi-file behavior investigation, dependency impact summary, test-selection with rationale, runtime-error diagnosis, request/data-flow mapping, code-path comparison, and change-surface summary.

V1 also supports explicit task decomposition before implementation prep and controlled small-change apply on disposable copies.

## Unsupported Boundaries

- Broad single-path refactor orchestration is not part of V1 acceptance.
- Advanced generated packet follow-ups are not part of the first-tester flow.
- Applying changes directly to the frozen Coinbase fixtures is blocked.
- Arbitrary implementation requests outside the supported exact-packet paths should block or request exact details.
- AnythingLLM pointed at `8300/v1` is ordinary model/gateway chat, not natural workflow routing.
- AnythingLLM pointed at `8400` is unsupported because `8400` is the controller service.
- V1 is not a proof that every repository, language, or framework works. It proves the current local stack, workflow router, controller tools, skills, and two frozen Coinbase fixtures work end to end.

## Known Limitations

- Validation used the local `Qwen3-Coder-30B-A3B-Instruct` setup and two frozen Coinbase fixtures.
- AnythingLLM validation used the configured workspace API. Manual UI testing is still useful for tester feedback.
- L1 draft-only support is intentionally narrow and deterministic. Unsupported edit/test/fix requests may block until exact details are provided.
- Founder field checks are marker and semantic-concept gates. They prove useful chat-visible answer shape for the current fixture prompts; they are not a universal benchmark for every repository or language.
- WSL Git can report Windows line-ending or filemode noise for the git-enabled fixture; Windows Git status is the authoritative clean check for that fixture.
- Generated artifacts are intentionally stored under runtime state instead of being copied into target repositories.
- Windows clients can receive headers but time out waiting for body bytes against Bash-hosted localhost services. Run live validators from Bash when that happens.

## Validation Evidence

Phase 55 validation ran against:

- `/mnt/c/coinbase_testing_repo_frozen_tmp`
- `/mnt/c/coinbase_testing_repo_frozen_tmp.github`
- localhost model port `8000`
- LLM gateway `8300`
- workflow-router gateway `8500`
- controller `8400`
- role ports `8101`, `8102`, `8201`, `8202`, `8203`, `8204`, and `8205`
- AnythingLLM workspace API

Latest V1.1 release-candidate report:

```text
runtime-state/v1-acceptance/phase90-v1-1-acceptance-final.json
```

Latest validation results:

- V1.1 acceptance: `status=passed`, `profile=v1.1-release-candidate`, `suite_count=13`, `json_output_count=2`, `feedback_count=2`, `error_count=0`
- health checks: `11` localhost endpoints passed
- AnythingLLM preflight: `ping_status=200`, `workspace_status=200`, workspace `my-workspace` found
- first-time user doctor: `28` passed, `1` known fixture warning for Bash/Windows git line-ending noise, `0` failed
- docs-index check: `expected_count=96`, `orphaned_docs=[]`, `status=passed`
- release-channel validation: `dev`, `release-candidate`, and `stable` metadata passed
- security policy: `5` checks passed, `0` skipped, `0` failed
- observability: recent workflow-router report loaded `30` runs
- model probe: `localhost:8000/v1/models` returned `Qwen3-Coder-30B-A3B-Instruct`; model portability summary passed with zero classified misses
- representative L1: `L1-002` and `L1-010` passed through gateway and AnythingLLM on both frozen repos
- representative L2: `L2-005` passed through gateway and AnythingLLM on both frozen repos
- task decomposition: direct controller, gateway, and AnythingLLM passed on both frozen repos
- controlled apply: direct dry-run, protected real-apply refusal, gateway disposable-copy apply, and AnythingLLM disposable-copy apply passed on both frozen repos
- inline FormatA answers: gateway and AnythingLLM passed on both frozen repos
- external tester onboarding: live onboarding prompt and linked feedback passed through AnythingLLM
- founder field prompts: `34` AnythingLLM prompts passed with output-contract and semantic-quality gates
- skill-library release gate: `50` skills, `49` eval cases, `50` route keys, Batch D live proof, prompt matrix `50` passed and `0` failed
- JSON output: gateway and AnythingLLM passed on both frozen repos
- feedback capture: gateway and AnythingLLM feedback records passed on both frozen repos
- full regression: `422 passed, 23 deselected`
- protected fixture mutation check: watched hashes were unchanged; Windows Git status for `C:\coinbase_testing_repo_frozen_tmp.github` returned clean output after validation

Representative run IDs:

- L1 gateway: `workflow-router-20260605T224621533368Z`, `workflow-router-20260605T224637153115Z`, `workflow-router-20260605T224642241422Z`, `workflow-router-20260605T224659872120Z`
- L1 AnythingLLM: `workflow-router-20260605T224705076543Z`, `workflow-router-20260605T224723214172Z`, `workflow-router-20260605T224727630951Z`, `workflow-router-20260605T224740736869Z`
- L2 gateway: `workflow-router-20260605T224745809126Z`, `workflow-router-20260605T224803433072Z`
- L2 AnythingLLM: `workflow-router-20260605T224814559545Z`, `workflow-router-20260605T224831555593Z`
- task decomposition AnythingLLM: `workflow-router-20260605T224854900083Z`, `workflow-router-20260605T224901781049Z`
- controlled apply AnythingLLM: `workflow-router-20260605T224953166198Z`, `workflow-router-20260605T225007544886Z`
- feedback records: `workflow-feedback-20260605T225258490556Z`, `workflow-feedback-20260605T225313449630Z`, `workflow-feedback-20260605T225327095103Z`, `workflow-feedback-20260605T225338568130Z`

## Re-Run Commands

Start the stack from PowerShell:

```powershell
bash -lc "cd /mnt/c/agentic_agents && ./stop-agent-prompt-proxies.sh && CONTROLLER_ALLOWED_TARGET_ROOTS='/mnt/c/agentic_agents:/mnt/c/coinbase_testing_repo_frozen_tmp:/mnt/c/coinbase_testing_repo_frozen_tmp.github' CONTROLLER_DEFAULT_ROLE_BASE_URL='http://127.0.0.1:8300/v1' ./start-agent-prompt-proxies.sh"
```

Run the release-candidate gate from Bash:

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="$(powershell.exe -NoProfile -Command '[Console]::Out.Write([Environment]::GetEnvironmentVariable("ANYTHINGLLM_API_KEY","User"))')"
python3 scripts/validate_v1_acceptance.py \
  --profile v1.1-release-candidate \
  --candidate-model-base-url http://127.0.0.1:8000/v1 \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --controller-base-url http://127.0.0.1:8400 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --timeout-seconds 900 \
  --command-timeout-seconds 1800
```

Run extended suites when needed:

```bash
python3 scripts/validate_founder_field_prompt_matrix.py
```

```bash
python3 scripts/run_founder_field_prompt_eval.py \
  --anythingllm-api-base-url http://127.0.0.1:3001 \
  --workspace my-workspace \
  --timeout-seconds 900
```

```bash
python3 scripts/validate_workflow_router_l1_suite.py \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --timeout-seconds 900
```

```bash
python3 scripts/validate_workflow_router_l2_suite.py \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --timeout-seconds 900
```

Run local project gates:

```bash
python scripts/check_docs_index.py
python -m pytest tests/regression/ -v
git -C C:\coinbase_testing_repo_frozen_tmp.github status --short
```
