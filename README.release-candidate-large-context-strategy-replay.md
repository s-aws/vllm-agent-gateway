# Release-Candidate Large-Context Strategy Replay

This feature validates that the release-candidate path still supports large-context chat behavior after clone, setup, and prior release proof work.

It composes existing gates instead of creating another large-context implementation:

- Phase 214 large-corpus fixture and context-budget inventory
- Phase 217 metadata-first context index prototype
- Phase 221 live large-context usability closeout
- Phase 223 chunked-investigation live executor proof

The replay proves retrieval, artifact paging, summarization, safe refusal, and chunked investigation through the workflow-router gateway and AnythingLLM. It also confirms no raw 1M-token prompt support is claimed, source text remains metadata-only, and small-repo prompts still avoid large-context retrieval.

## Command

```bash
python3 scripts/validate_release_candidate_large_context_strategy_replay.py \
  --output-path runtime-state/release-candidate-large-context-strategy-replay/phase241/phase241-release-candidate-large-context-strategy-replay-report.json \
  --timeout-seconds 1200
```

Set `ANYTHINGLLM_API_KEY` before running the command. vLLM, the gateway, the workflow-router gateway, the controller, and AnythingLLM must already be running.

## Pass Marker

```text
RELEASE CANDIDATE LARGE CONTEXT STRATEGY REPLAY PASS
```

## Safety

This gate bootstraps ignored runtime artifacts needed for a clone-path replay. It regenerates the deterministic large corpus and context index locally, then snapshots the generated corpus before live prompts and verifies it is unchanged afterward.

It does not prove raw 1M-token model prompting. Large-context usability remains retrieval-first and strategy-routed unless a separate raw-context benchmark milestone is activated.
