# Implementation-Prep Expansion Examples

## Direct Validator

```bash
python3 scripts/validate_implementation_prep_expansion.py \
  --output-path runtime-state/implementation-prep-expansion/phase96-implementation-prep-direct.json
```

Expected result:

```text
IMPLEMENTATION PREP EXPANSION PASS
```

## Live Gateway Validator

Start the Bash-hosted stack first:

```bash
CONTROLLER_ALLOWED_TARGET_ROOTS="/mnt/c/agentic_agents:/mnt/c/coinbase_testing_repo_frozen_tmp:/mnt/c/coinbase_testing_repo_frozen_tmp.github" \
  ./start-agent-prompt-proxies.sh
```

Then run:

```bash
python3 scripts/validate_implementation_prep_expansion.py \
  --skip-direct \
  --live-gateway \
  --output-path runtime-state/implementation-prep-expansion/phase96-implementation-prep-gateway.json \
  --timeout-seconds 900
```

This validates localhost model `8000`, workflow-router gateway `8500`, controller `8400`, both frozen Coinbase fixtures, packet proposal artifacts, downstream draft implementation artifacts, verification commands, and fixture mutation proof.

## AnythingLLM Validator

AnythingLLM should point at:

```text
http://127.0.0.1:8500/v1
```

If running from PowerShell into Bash, bridge the API key:

```powershell
$env:WSLENV='ANYTHINGLLM_API_KEY/u'
```

Then run:

```bash
python3 scripts/validate_implementation_prep_expansion.py \
  --skip-direct \
  --live-anythingllm \
  --output-path runtime-state/implementation-prep-expansion/phase96-implementation-prep-anythingllm.json \
  --timeout-seconds 900
```

## Manual Small Text Prompt

Paste into AnythingLLM:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, draft a small documentation edit to README.md that adds a note saying phase 96 implementation prep uses draft packet proposals. Draft only; do not mutate files. Show the exact proposed change, safety checks, and verification command.
```

Expected chat-visible markers:

- `Draft proposal:`
- `README.md`
- `append_text`
- `Verification: git diff -- README.md`
- `Source mutation: false`

## Manual Approved-Investigation Follow-Up

First run:

```text
In /mnt/c/coinbase_testing_repo_frozen_tmp.github, identify the minimal safe change surface for find_stealth_order_by_placed_order_id in core/stealth_order_manager.py. Read only. Return files that would need review, related tests, risks, and verification commands. Stop before implementation.
```

Then use the returned `workflow-router-...` run id:

```text
For run <workflow-router-run-id>, approved investigation. Implementation objective: add a draft-only marker beside find_stealth_order_by_placed_order_id in core/stealth_order_manager.py. Prepare exact packet operations for implementation prep. Draft only; do not mutate files.
```

Expected chat-visible markers:

- `Draft proposal:`
- `packet_operation_proposal`
- `core/stealth_order_manager.py`
- `Evidence source: downstream_investigation_plan`
- `Source mutation: false`
