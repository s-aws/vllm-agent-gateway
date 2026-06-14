# Multi-Repo Fixture Baseline Pack Examples

Use these commands from Bash/WSL.

## Prepare Fixture

The approved local fixture path is:

```text
/mnt/c/staterail_testing_repo_frozen_tmp.github
```

Clone it if it does not already exist:

```bash
git clone https://github.com/s-aws/staterail.git /mnt/c/staterail_testing_repo_frozen_tmp.github
```

Verify it is clean and pinned:

```bash
git -C /mnt/c/staterail_testing_repo_frozen_tmp.github status --short
git -C /mnt/c/staterail_testing_repo_frozen_tmp.github rev-parse HEAD
```

Expected commit:

```text
d3cecac670e3dd185cd3289feecae6ec69bab0b3
```

## Validate Phase 209

```bash
python3 scripts/validate_multi_repo_fixture_baseline_pack.py
```

Inspect the generated report:

```bash
python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("runtime-state/phase209/phase209-multi-repo-fixture-baseline-pack-report.json").read_text())
print(report["status"], report["summary"])
for case in report["case_summaries"]:
    print(case["case_id"], case["category"], case["rubric_total"])
PY
```

## Safety Boundary

Do not commit or push to `s-aws/staterail`:

```bash
git -C /mnt/c/staterail_testing_repo_frozen_tmp.github status --short
```

If mutation testing is needed in a later phase, create a disposable copy first and mutate only that copy.
