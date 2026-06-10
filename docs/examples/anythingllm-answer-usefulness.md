# AnythingLLM Answer Usefulness Examples

Validate the committed contract only:

```bash
python scripts/validate_anythingllm_answer_usefulness.py
```

Validate against local captured AnythingLLM response artifacts:

```bash
python scripts/validate_anythingllm_answer_usefulness.py --require-artifacts --output-path runtime-state/anythingllm-answer-usefulness/anythingllm-answer-usefulness-report.json
```

Review failures by opening the report and looking at `errors`:

```bash
python -m json.tool runtime-state/anythingllm-answer-usefulness/anythingllm-answer-usefulness-report.json
```

Common failures:

- `missing accepted answer section marker`: the chat response did not include the family answer section.
- `answer section appears after artifacts`: the user must open files before seeing the answer.
- missing `primary_answer_contract`: a `summary.answer` response did not expose the same answer text in JSON.
- `Answer:` appears after router metadata: a no-target or blocked guidance response is still tool-log-shaped instead of answer-first.
- `too little answer content before artifacts`: the response is effectively metadata or artifact links.
- `useful detail marker`: the response is present but not actionable enough for the prompt family.
- `local_eval.sha256 is stale`: rerun baseline-corpus governance or update proof after a new local eval.
