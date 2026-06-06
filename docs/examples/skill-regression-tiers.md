# Skill Regression Tier Examples

Validate the catalog:

```bash
python scripts/validate_skill_regression_tiers.py
```

Write a report:

```bash
python scripts/validate_skill_regression_tiers.py \
  --output-path runtime-state/skill-regression-tiers/manual.json
```

Expected marker:

```text
SKILL REGRESSION TIERS PASS
```

Run the minimum offline tier for docs, prompt coverage, or registry metadata changes:

```bash
python scripts/validate_skill_release_gate.py --profile offline
python scripts/validate_prompt_skill_coverage.py
python scripts/check_docs_index.py
python -m pytest tests/regression/test_skill_registry.py tests/regression/test_skill_evals.py tests/regression/test_skill_selector_scale.py tests/regression/test_prompt_skill_coverage.py -q
```

Run the controller tier for scaffold or lifecycle controller changes:

```bash
python -m pytest tests/regression/test_controller_service.py -k "skill_scaffold or skill_batch or skill_eval_promotion or skill_lifecycle or skill_deprecation or skill_update or skill_selection or skill_pack" -q
python -m pytest tests/regression/test_chat_response_contract.py -q
```

Run the Bash gateway tier for runtime-facing scaffold, router, or live chat-output changes:

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_skill_authoring_factory_live.py --skip-anythingllm
python3 scripts/validate_workflow_router_chat_contract_live.py --skip-anythingllm
python3 scripts/validate_skill_release_gate.py --profile live-smoke
```

Run the AnythingLLM API tier:

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="${ANYTHINGLLM_API_KEY:?set AnythingLLM API key first}"
python3 scripts/validate_skill_authoring_factory_live.py
python3 scripts/validate_workflow_router_chat_contract_live.py
python3 scripts/validate_workflow_router_l1_suite.py
python3 scripts/validate_workflow_router_l2_suite.py
```

Run the release-candidate tier:

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="${ANYTHINGLLM_API_KEY:?set AnythingLLM API key first}"
python3 scripts/validate_skill_release_gate.py --profile release-candidate \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github
python3 scripts/validate_v1_acceptance.py --profile release-candidate \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github
python -m pytest tests/regression/ -v
```
