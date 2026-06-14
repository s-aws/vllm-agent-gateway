# Remote-Clone Priority 0 Chat-Quality Replay

This feature validates that a pushed release-candidate clone can answer representative founder prompts through the same workflow-router gateway and AnythingLLM path used for manual testing.

Use it before release-candidate review when the branch has already passed setup, clone, and PR readiness checks. The replay is blind-baseline-first: the expected answer shape comes from a contextless baseline rubric, then the local stack is scored against that rubric.

## What It Checks

- Greeting behavior does not trigger repository work.
- Coinbase code explanation returns chat-visible inputs, outputs, side effects, source refs, tests, and no-mutation status.
- Endpoint route lookup and schema lookup work against the Python service fixture.
- Coinbase related-tests lookup returns files, terms, and commands.
- Feedback capture records feedback against a prior workflow-router run.
- Unsupported broad mutation is blocked with a safe next step.
- AnythingLLM is configured to call `http://127.0.0.1:8500/v1`.
- Protected Coinbase and Python-service fixtures remain unchanged.

## Command

```bash
python3 scripts/validate_remote_clone_priority0_chat_quality_replay.py \
  --output-path runtime-state/remote-clone-priority0-chat-quality-replay/phase239/phase239-remote-clone-priority0-chat-quality-replay-report.json \
  --timeout-seconds 240
```

Set `ANYTHINGLLM_API_KEY` before running the command. The controller/gateway stack and vLLM model must already be running.

## Output

The validator writes a JSON report with:

- `decision`: `remote_clone_priority0_chat_quality_ready` or `remote_clone_priority0_chat_quality_blocked`
- `target_settings`: AnythingLLM target configuration proof
- `cases`: gateway and AnythingLLM prompt results with run IDs, findings, and run-record summaries
- `fixture_unchanged`: protected fixture mutation proof

The pass marker is:

```text
REMOTE CLONE PRIORITY0 CHAT QUALITY REPLAY PASS
```
