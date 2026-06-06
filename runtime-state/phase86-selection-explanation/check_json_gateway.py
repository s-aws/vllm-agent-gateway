import json
import urllib.request
from pathlib import Path

payload = {
    "model": "agentic-workflow-router",
    "output_format": "json",
    "messages": [
        {
            "role": "user",
            "content": "In /mnt/c/coinbase_testing_repo_frozen_tmp.github, find where the placed_order_id stealth lookup begins. Read only. Return the entrypoint, evidence files, related tests, and confidence.",
        }
    ],
}
request = urllib.request.Request(
    "http://127.0.0.1:8500/v1/chat/completions",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(request, timeout=900) as response:
    body = json.loads(response.read().decode("utf-8"))
Path("runtime-state/phase86-selection-explanation/gateway-json-response.json").write_text(
    json.dumps(body, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
content = body["choices"][0]["message"]["content"]
rendered = json.loads(content)
assert rendered["selection_explanation"]["selected_workflow"] == "code_investigation.plan"
assert "l1_find_behavior_start_terms" in rendered["selection_explanation"]["route_rules"]
assert rendered["chat_contract"]["selection_explanation"]["selected_workflow"] == "code_investigation.plan"
assert rendered["summary"]["source_changed"] is False
print("PHASE86_JSON_GATEWAY_PASS", rendered["run_id"])
