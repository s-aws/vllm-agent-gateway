# Large-Context Usability Live Closeout Examples

Run the Phase 221 offline preflight:

```bash
python3 scripts/validate_large_context_usability_live_closeout.py
```

Run the live gateway plus AnythingLLM closeout:

```bash
python3 scripts/validate_large_context_usability_live_closeout.py --live --timeout-seconds 900
```

Run the live closeout when `127.0.0.1:3001` is not the AnythingLLM API:

```bash
python3 scripts/validate_large_context_usability_live_closeout.py \
  --live \
  --anythingllm-api-base-url http://192.168.0.208:3001 \
  --timeout-seconds 900
```

Inspect the generated report:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase221/phase221-large-context-usability-live-closeout-report.json").read_text())
print(json.dumps(report["summary"], indent=2, sort_keys=True))
for response in report["responses"]:
    print(response["surface"], response["case_id"], response["status"], response["selected_context_strategy"], response["run_id"])
PY
```

Representative prompt:

```text
In /mnt/c/agentic_agents/runtime-state/phase214/generated-large-corpus, find evidence for how risk gate decisions flow into audit summaries. Include source refs, limitations, and whether raw prompt stuffing was used.
```

Expected closeout markers:

- `m6_ready` is `true`
- `m8_ready` is `true`
- `failed_response_count` is `0`
- `failed_small_repo_regression_count` is `0`
- every live response has `raw_prompt_stuffing=false`
- small-repo regression prompts remain `direct_context`
