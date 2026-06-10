# Priority 0 Gap Taxonomy Examples

## Validate The Stable Corpus

```bash
cd /mnt/c/agentic_agents
python3 scripts/validate_priority0_gap_taxonomy.py \
  --output-path runtime-state/priority0-gap-taxonomy/priority0-gap-taxonomy-report.json
```

Expected markers:

```text
PRIORITY0 GAP TAXONOMY REPORT ...
PRIORITY0 GAP TAXONOMY SUMMARY ...
PRIORITY0 GAP TAXONOMY PASS
```

## Review A Failed Report

Open the JSON or Markdown report under:

```text
runtime-state/priority0-gap-taxonomy/
```

Review in this order:

1. `summary.highest_severity`
2. `summary.gap_class_counts`
3. `findings[].source`
4. `findings[].evidence.case_id`
5. `findings[].evidence.route`
6. `findings[].evidence.selected_workflow`
7. `findings[].evidence.bounded_repair_action`

## Gap Class Meaning

```text
routing                 -> workflow-router or prompt-family route rule
context_gathering       -> deterministic source/test/log/evidence extraction
skill_tool_selection    -> selected skill, rejected skill, tool catalog, or allowlist
deterministic_formatter -> chat renderer, FormatA, JSON, or required visible marker
model_capability        -> local model capability/profile issue after harness proof is correct
safety_boundary         -> read-only, approval, no-mutation, or apply boundary
documentation           -> setup, tester, workflow, or AnythingLLM docs
test_coverage           -> reproduction, smallest test, broader regression, or verification strategy
```

Do not treat `model_capability` as a prompt-tuning instruction by default. First inspect the local output and model capability evidence.

For clean-clone shape inspection without local `runtime-state/` proof artifacts:

```bash
python3 scripts/validate_priority0_gap_taxonomy.py --allow-missing-artifacts
```

Do not use `--allow-missing-artifacts` for release readiness.
