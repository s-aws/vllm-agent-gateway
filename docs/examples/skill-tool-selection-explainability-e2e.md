# Skill/Tool Selection Explainability E2E Examples

Run the full Phase 151 gate from Bash:

```bash
export ANYTHINGLLM_API_KEY="${ANYTHINGLLM_API_KEY:?set AnythingLLM API key first}"

python3 scripts/validate_skill_tool_selection_explainability_e2e.py \
  --model-base-url http://127.0.0.1:8000/v1 \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --controller-base-url http://127.0.0.1:8400 \
  --anythingllm-api-base-url http://127.0.0.1:3001 \
  --workspace my-workspace \
  --output-path runtime-state/skill-tool-selection-explainability-e2e/phase151/phase151-skill-tool-selection-explainability-e2e-report.json \
  --markdown-output-path runtime-state/skill-tool-selection-explainability-e2e/phase151/phase151-skill-tool-selection-explainability-e2e-report.md
```

Run a focused single-fixture probe while debugging:

```bash
python3 scripts/validate_skill_tool_selection_explainability_e2e.py \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github \
  --output-path runtime-state/skill-tool-selection-explainability-e2e/manual/phase151-github-only.json \
  --markdown-output-path runtime-state/skill-tool-selection-explainability-e2e/manual/phase151-github-only.md
```

The report is expected to show each selected case on both surfaces:

```json
{
  "surfaces": ["anythingllm", "gateway"],
  "case_ids": ["SEL-001", "SEL-002", "SEL-003"],
  "target_roots": [
    "/mnt/c/coinbase_testing_repo_frozen_tmp",
    "/mnt/c/coinbase_testing_repo_frozen_tmp.github"
  ]
}
```

Each chat response must include:

```text
Result:
- Selected workflow:
- Selected skills:
- Selected tools:

Skill Selection:
- Why:
- Route rules:
- Confidence:
- Coverage entries:
- Skills:
- Tools:
- Rejected candidates:
- Grounded in:
```

The gate compares those visible lines to the run's `route_decision` and `registry_snapshot` artifacts. A response that only links artifacts, omits rejected candidate counts, or dumps raw selector JSON fails.
