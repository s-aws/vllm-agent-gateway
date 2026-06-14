# Remote-Clone Non-Coinbase Generalization Replay

This feature validates that a pushed release-candidate clone still handles supported read-only prompts outside the Coinbase fixtures.

It reuses the existing multi-repo live-case runner and covers:

- the Python service generalization fixture
- the approved `s-aws/staterail` frozen fixture at `/mnt/c/staterail_testing_repo_frozen_tmp.github`
- one Coinbase holdout to catch obvious regression while focused on non-Coinbase behavior

The gate does not rely on ignored `runtime-state` reports being present in a clean clone.

## Command

```bash
python3 scripts/validate_remote_clone_non_coinbase_generalization_replay.py \
  --output-path runtime-state/remote-clone-non-coinbase-generalization-replay/phase240/phase240-remote-clone-non-coinbase-generalization-replay-report.json \
  --timeout-seconds 600
```

Set `ANYTHINGLLM_API_KEY` before running the command. vLLM, the gateway, the workflow-router gateway, the controller, and AnythingLLM must already be running.

## Pass Marker

```text
REMOTE CLONE NON-COINBASE GENERALIZATION REPLAY PASS
```

## Safety

The Staterail fixture is read-only for this project. The validator may read files, generate controller artifacts, and send prompts through gateway/AnythingLLM. It must not commit, push, or publish branches to `s-aws/staterail`.
