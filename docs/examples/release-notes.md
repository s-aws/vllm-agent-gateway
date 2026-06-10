# Release Notes Examples

## Validate Release Notes

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_release_notes.py \
  --require-artifacts \
  --output-path runtime-state/release-notes/phase146/phase146-release-notes-report.json
```

Expected marker:

```text
RELEASE NOTES PASS
```

## Review The Notes

Open:

```text
README.release-notes.md
```

Check that it says:

- current status is `ready_for_founder_testing`
- AnythingLLM uses `http://127.0.0.1:8500/v1`
- AnythingLLM itself is reachable at `http://127.0.0.1:3001` and API checks use `ANYTHINGLLM_API_KEY`
- the ordinary model gateway `8300`, controller `8400`, local model `8000`, and role ports are distinguished correctly
- `format_a` and `json` are the only governed output formats
- advanced broad refactor orchestration is not released
- validation evidence links to the current local proof artifacts, including health drift, prompt-pack, founder-smoke, stable proof, and advanced-refactor boundary reports

The validator fails if the notes only contain the right phrases but the backing artifacts drift. Current exact proof includes:

- stable release gate: 11 of 11 gates passed, 0 blockers
- health drift: 29 checks, 0 failed checks
- founder prompt pack: 14 cases, 4 smoke, 10 expanded read-only
- founder smoke: 4 passed, 0 failed
- advanced refactor: broad runtime disabled and stable promotion disabled
