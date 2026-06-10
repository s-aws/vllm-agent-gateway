# Chat Quality Release Snapshot

Phase 136 creates a release-candidate snapshot manifest for the current Priority 0 chat-quality proof.

The snapshot does not copy or commit `runtime-state` artifacts. It records source paths, hashes, summaries, and git status so the current release evidence can be audited locally.

## Inputs

- stable chat-quality release report
- stable release blocker closure report
- AnythingLLM founder smoke report
- founder smoke feedback classification report
- handoff and roadmap docs

## Command

From Bash/WSL:

```bash
python3 scripts/create_chat_quality_release_snapshot.py \
  --require-artifacts \
  --output-path runtime-state/chat-quality-release-snapshot/phase136/phase136-chat-quality-release-snapshot.json
```

Expected marker:

```text
CHAT QUALITY RELEASE SNAPSHOT PASS
```

## Current Result

The current snapshot has:

- `release_readiness=ready_for_founder_testing`
- `artifact_count=4`
- `doc_count=7`
- `missing_artifact_count=0`
- `missing_doc_count=0`
- `founder_smoke_failed=0`
- `actionable_feedback_count=0`

## Failure Rules

The snapshot fails if:

- the stable release gate is not ready
- founder smoke has failures
- founder feedback classification has actionable items
- a required proof artifact is missing or failed
- a required handoff document is missing
