# Documenter Run State

`run-state-*.json` is the resumable controller state for long documenter runs. It is a controller artifact, not a role prompt artifact.

## Schema

Current schema:

```json
{
  "schema_version": 1,
  "kind": "documenter_run_state",
  "status": "running",
  "run_id": "20260524T230050843985Z",
  "resume_key": {},
  "artifacts": {},
  "target_queue": [],
  "queue_index": 0,
  "completed_chunk_ids": [],
  "chunk_reports": [],
  "reviewed_file_reports": [],
  "accepted_followups": [],
  "skipped_followups": [],
  "failed_packets": [],
  "failure": null
}
```

Valid resumable statuses are:

- `running`
- `paused`
- `failed`
- `review_complete`

`completed` is terminal and is intentionally not resumable.

## Resume Contract

Resume uses the saved `resume_key` to compare controller arguments against the current command. By default, the controller refuses to resume when any compatibility key changes.

Compatibility keys include:

- mode
- config root
- target root
- output directory
- document scope
- seed document
- role ID and role base URL
- model
- dry-run and draft policy
- chunk token limit and overlap
- visible candidate limits
- max chunks per file
- follow-up policy
- criteria
- max output tokens

Use `--resume-allow-arg-changes` only when the change is deliberate. The state records that override.

## What Is Skipped

On resume, the controller reloads:

- `target_queue`
- `queue_index`
- `completed_chunk_ids`
- accepted and skipped follow-ups
- criteria remaining
- previous chunk reports
- reviewed file reports

Chunks whose IDs are already in `completed_chunk_ids` are skipped. Accepted follow-ups are not reaccepted because the saved queue and queued-file set are restored.

## Failure Metadata

When a packet call fails, the controller writes status `failed` before raising. The failed packet record includes:

- document ID
- source and follow-up depth
- chunk ID
- line range
- input token estimate
- criteria remaining
- visible follow-up candidates
- packet summary
- controller error text

The full chunk text is not duplicated in `failed_packets`; the chunk can be rebuilt from the saved document path and chunk settings.

## Commands

Pause after one newly processed chunk for a controlled resume smoke test:

```bash
python scripts/run_documenter_orchestrator.py --target-root . --seed-doc README.md \
  --mode full \
  --dry-run \
  --max-chunks 1 \
  --stop-after-chunks 1
```

Resume from a state artifact:

```bash
python scripts/run_documenter_orchestrator.py --target-root . --seed-doc README.md \
  --mode full \
  --dry-run \
  --max-chunks 1 \
  --resume .agentic_reports/run-state-agentic_agents-README.md-20260524T230050843985Z.json
```

Resume can also point at a report JSON if the report has an `artifacts.run_state` path.
