# Artifact Paging And Long Answer Usability Examples

## Validate Phase 219

```bash
python3 scripts/validate_artifact_paging_long_answer_usability.py
```

Expected summary shape:

```json
{
  "direct_case_count": 2,
  "direct_passed_count": 2,
  "format_a_case_count": 2,
  "format_a_passed_count": 2,
  "json_case_count": 2,
  "json_passed_count": 2,
  "negative_control_count": 3,
  "negative_control_passed_count": 3,
  "phase220_ready": true
}
```

## Natural Prompt

```text
In /mnt/c/agentic_agents/runtime-state/phase214/generated-large-corpus, identify the most relevant modules for the order replay pipeline. Return the top files, why they matter, and what evidence should be retrieved first.
```

Expected default chat behavior:

- starts with `Answer:`
- includes the first bounded evidence refs directly in chat
- includes `Paged evidence:` with page count, source-ref count, and first page ID
- includes artifact links after the answer and summary

## JSON Output

Ask for JSON or use `response_format={"type":"json_object"}`.

Expected JSON behavior:

- `primary_answer_contract.text` contains the answer-first summary
- `summary.retrieval_artifact_page_count` is present
- `summary.retrieval_artifact_source_ref_count` is present
- artifacts include `downstream_retrieval_backed_chat_answer`

## Page Artifact Shape

The retrieval artifact contains:

```json
{
  "artifact_pages": {
    "kind": "retrieval_evidence_pages",
    "page_count": 3,
    "total_source_ref_count": 12,
    "chat_refs_trace_to_pages": true,
    "store_source_text": false,
    "pages": [
      {
        "page_id": "retrieval-evidence-page-001",
        "source_refs": [
          {
            "source_path": "src/order_replay/module_0000.py",
            "line_start": 1,
            "line_end": 80,
            "chunk_sha256": "...",
            "source_sha256": "...",
            "freshness_status": "fresh"
          }
        ],
        "continuation_hint": "Open page 2 for the next evidence refs."
      }
    ]
  }
}
```
