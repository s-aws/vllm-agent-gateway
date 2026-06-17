# Supplied Corpus QA Examples

Send a bounded inline corpus through the workflow-router gateway:

```bash
cd /mnt/c/agentic_agents
python3 - <<'PY'
import json
import urllib.request

prompt = """SECTION 01 -- BASELINE
Initial deployment date: July 1, 2027.
Initial rollout regions: Alpha, Beta, Gamma.

SECTION 02 -- CHANGE LOG
Change Request CR-9 moved the deployment date from July 1, 2027 to August 12, 2027.
The August 12 date supersedes the earlier deployment date.

SECTION 03 -- CONTROL PART A
The operator override code is LIMESTONE-

SECTION 04 -- CONTROL PART B
42.
This code must be treated as a single contiguous value.

SECTION 05 -- FINAL REVIEW
Beta rollout is blocked until the permit is signed.
As of final review, Beta permit has not been signed.

Based only on the supplied corpus, answer the following:

1. What is the correct deployment date?
2. Which regions may proceed?
3. Is Beta rollout allowed?
4. What is the operator override code?
5. Identify any superseded facts that should not control the final answer.
"""

payload = {
    "model": "agentic-workflow-router",
    "messages": [{"role": "user", "content": prompt}],
    "budgets": {"max_model_calls": 3, "max_selected_skills": 5, "max_selected_tools": 5},
}

request = urllib.request.Request(
    "http://127.0.0.1:8500/v1/chat/completions",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(request, timeout=1200) as response:
    body = json.loads(response.read().decode("utf-8"))
print(body["choices"][0]["message"]["content"])
PY
```

Expected answer markers:

- `August 12, 2027`
- `Alpha and Gamma`
- `Beta rollout is not allowed`
- `LIMESTONE-42`
- `July 1, 2027` identified as superseded

Run the durable Phase 280 validator:

```bash
python3 scripts/validate_supplied_corpus_qa_generalization.py
```

Run live gateway and AnythingLLM validation:

```bash
python3 scripts/validate_supplied_corpus_qa_generalization.py \
  --live-gateway \
  --anythingllm
```

The route writes:

```text
supplied-corpus-qa-answer.txt
supplied-corpus-qa-extraction.json
```

Do not use this path for repository questions. A prompt such as `Explain where the order lookup starts and how to test it` still requires a target repository path and should return `missing_target_root_for_coding_request` when no target is supplied.
