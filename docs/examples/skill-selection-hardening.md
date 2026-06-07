# Runtime Skill Selection Hardening Examples

Run these examples from Bash when validating the live localhost stack.

## Direct Contract Check

```bash
cd /mnt/c/agentic_agents
python scripts/validate_skill_selection_hardening.py \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github
```

Expected proof:

- `runtime/skill_selection_hardening_cases.json` passes the catalog contract.
- Each case produces stable `selected_workflow`, selected skills, selected tools, route rules, coverage entry IDs, confidence reasons, and rejected candidate counts.
- Fail-closed cases do not produce selected skills/tools or request previews.

## Live Gateway And AnythingLLM Check

Start the local stack first:

```bash
cd /mnt/c/agentic_agents
CONTROLLER_ALLOWED_TARGET_ROOTS="/mnt/c/agentic_agents:/mnt/c/coinbase_testing_repo_frozen_tmp:/mnt/c/coinbase_testing_repo_frozen_tmp.github" \
CONTROLLER_DEFAULT_ROLE_BASE_URL="http://127.0.0.1:8000/v1" \
./start-agent-prompt-proxies.sh
```

Then run:

```bash
python scripts/validate_skill_selection_hardening.py \
  --live-gateway \
  --live-anythingllm \
  --model-base-url http://127.0.0.1:8000/v1 \
  --workflow-router-gateway-base-url http://127.0.0.1:8500/v1 \
  --controller-base-url http://127.0.0.1:8400 \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github
```

Expected proof:

- Gateway responses include `Skill Selection:`, `- Confidence:`, `- Rejected candidates:`, and `route_decision.selection_audit`.
- AnythingLLM responses expose the same chat-visible selector markers.
- The validator fetches the controller run record for AnythingLLM run IDs and validates the stored `route_decision`.
- Protected frozen fixture hashes and git status remain unchanged.
