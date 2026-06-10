# AnythingLLM Conversation State Isolation

Phase 152 proves that stale chat history does not control the current workflow-router response.

The product rule is simple: the latest user message controls routing and output format unless that latest message explicitly references prior run IDs or artifacts. Old AnythingLLM messages can exist in the session, but they must not silently change the current answer.

## What It Checks

- stale repository prompts do not override the current target root or selected workflow
- stale JSON requests do not force JSON when the current prompt asks for normal chat
- stale FormatA requests do not block JSON when the current prompt asks for JSON
- stale explicit controller envelopes do not route a current greeting as repository work
- contaminated AnythingLLM sessions match fresh-session route signatures for the same current prompt
- gateway multi-message payloads and direct controller history payloads obey the same latest-message rule
- both frozen Coinbase fixtures remain unchanged

## What It Reads

Policy:

```text
runtime/anythingllm_conversation_state_isolation_policy.json
```

## What It Produces

JSON:

```text
runtime-state/anythingllm-conversation-state-isolation/phase152/phase152-anythingllm-conversation-state-isolation-report.json
```

Markdown:

```text
runtime-state/anythingllm-conversation-state-isolation/phase152/phase152-anythingllm-conversation-state-isolation-report.md
```

## Run

From Bash with the local model, gateway, controller, and AnythingLLM running:

```bash
export ANYTHINGLLM_API_KEY="${ANYTHINGLLM_API_KEY:?set AnythingLLM API key first}"

python3 scripts/validate_anythingllm_conversation_state_isolation.py \
  --output-path runtime-state/anythingllm-conversation-state-isolation/phase152/phase152-anythingllm-conversation-state-isolation-report.json \
  --markdown-output-path runtime-state/anythingllm-conversation-state-isolation/phase152/phase152-anythingllm-conversation-state-isolation-report.md
```

Expected marker:

```text
ANYTHINGLLM CONVERSATION STATE ISOLATION PASS
```

## Failure Meaning

- Wrong selected workflow means stale history contaminated routing.
- Wrong target root means stale history contaminated the current repository scope.
- JSON returned for a normal prompt means stale output-format preference leaked forward.
- FormatA returned for a JSON prompt means current output-format intent was ignored.
- Same-session and fresh-session route signature mismatch means AnythingLLM session history is changing product behavior.

Examples: [docs/examples/anythingllm-conversation-state-isolation.md](docs/examples/anythingllm-conversation-state-isolation.md).
