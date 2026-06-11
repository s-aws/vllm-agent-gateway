# Release Candidate Founder Trial Pack Examples

Build the Phase 195 report:

```bash
python3 scripts/validate_release_candidate_founder_trial_pack.py --require-proof-artifacts
```

Write to explicit paths:

```bash
python3 scripts/validate_release_candidate_founder_trial_pack.py \
  --output-path runtime-state/phase195/phase195-release-candidate-founder-trial-pack-report.json \
  --markdown-output-path runtime-state/phase195/phase195-release-candidate-founder-trial-pack-report.md
```

Inspect prompt cases:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase195/phase195-release-candidate-founder-trial-pack-report.json").read_text())
print(report["status"])
for case in report["selected_case_summaries"]:
    print(case["case_id"], case["expected_workflow"], case["target_root"])
    print(case["prompt"])
PY
```

Require current local proof artifacts when closing a release-candidate trial:

```bash
python3 scripts/validate_release_candidate_founder_trial_pack.py \
  --require-proof-artifacts \
  --output-path runtime-state/phase195/phase195-release-candidate-founder-trial-pack-report.json \
  --markdown-output-path runtime-state/phase195/phase195-release-candidate-founder-trial-pack-report.md
```

Require proof artifacts and check live fixture state before a founder trial:

```bash
python3 scripts/validate_release_candidate_founder_trial_pack.py \
  --require-proof-artifacts \
  --validate-fixture-state
```

Verify local chat targets before running prompts:

```bash
curl -fsS http://127.0.0.1:8500/v1/models
curl -fsS http://127.0.0.1:3001
```

Capture feedback after a prompt returns a run ID:

```text
Record feedback for run workflow-router-YYYYMMDDTHHMMSSffffffZ: missing: expected the related tests section. confusing: the answer mixed setup guidance with the code answer. expected: a concise Answer section with source refs and test commands.
```

Append structured feedback locally:

```bash
mkdir -p runtime-state/phase195
cat >> runtime-state/phase195/founder-feedback.jsonl <<'JSON'
{"case_id":"P03","prompt":"<prompt text>","target_run_id":"workflow-router-YYYYMMDDTHHMMSSffffffZ","classification":"answer_quality","severity":"advisory","actual_response_excerpt":"<short excerpt>","expected_behavior":"Related tests and pytest command were visible in chat.","fixture_root":"/mnt/c/coinbase_testing_repo_frozen_tmp.github","created_at":"2026-06-11T00:00:00Z"}
JSON
```

Use only governed feedback values:

```text
classification: answer_quality | confusing | routing
severity: advisory | blocker
```

Check fixture state before and after the trial:

```bash
git -C /mnt/c/coinbase_testing_repo_frozen_tmp.github status --short
find /mnt/c/coinbase_testing_repo_frozen_tmp -type f -print0 | sort -z | xargs -0 sha256sum > runtime-state/phase195/non-git-fixture.before.sha256
# run trial prompts
find /mnt/c/coinbase_testing_repo_frozen_tmp -type f -print0 | sort -z | xargs -0 sha256sum > runtime-state/phase195/non-git-fixture.after.sha256
diff -u runtime-state/phase195/non-git-fixture.before.sha256 runtime-state/phase195/non-git-fixture.after.sha256
```
