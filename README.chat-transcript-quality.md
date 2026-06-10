# Chat Transcript Quality

Phase 138 classifies founder smoke chat transcripts as `pass`, `advisory`, or `blocker`.

Use this after the AnythingLLM founder smoke suite has produced `runtime-state/founder-field-tests/phase134-founder-smoke.json`.

## What It Checks

- chat-visible run ID
- expected selected workflow
- required answer sections before artifact links
- grounding or evidence markers
- HTTP success and source case status
- unsafe mutation claims in read-only founder prompts

The classifier is deterministic. It does not repair prompts or rewrite answers.

## Command

```bash
python3 scripts/validate_chat_transcript_quality.py \
  --require-artifacts \
  --output-path runtime-state/chat-transcript-quality/phase138/phase138-chat-transcript-quality-report.json
```

Expected current result:

```text
CHAT TRANSCRIPT QUALITY PASS
```

## Artifacts

- Policy: `runtime/chat_transcript_quality_policy.json`
- Report: `runtime-state/chat-transcript-quality/phase138/phase138-chat-transcript-quality-report.json`

`runtime-state` is local-only and should not be committed.
