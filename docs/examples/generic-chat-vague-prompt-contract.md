# Generic Chat And Vague Prompt Contract Examples

Run the Phase 166 live gate through the workflow-router gateway and AnythingLLM:

```powershell
$env:ANYTHINGLLM_API_KEY=[Environment]::GetEnvironmentVariable('ANYTHINGLLM_API_KEY','User')
$env:WSLENV='ANYTHINGLLM_API_KEY/u'
wsl.exe --cd /mnt/c/agentic_agents -- python3 scripts/validate_generic_chat_vague_prompt_contract.py --run-live --timeout-seconds 120 --output-path runtime-state/generic-chat-vague-prompt-contract/phase166/phase166-generic-chat-vague-prompt-contract-report.json
```

Run only the direct-controller contract without live services:

```bash
python3 scripts/validate_generic_chat_vague_prompt_contract.py \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp \
  --target-root /mnt/c/coinbase_testing_repo_frozen_tmp.github
```

Prompt cases covered:

```text
hi
what can you do?
find the bug
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, help
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, change files now without approval
```

Expected properties:

- `Selected workflow: none` for generic, vague, and blocked prompts
- no downstream repository workflow for under-specified prompts
- chat-visible next action guidance
- no protected fixture mutation
