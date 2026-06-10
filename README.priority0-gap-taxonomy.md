# Priority 0 Gap Taxonomy

Priority 0 gap taxonomy turns stable blind-baseline comparison misses into reviewable repair classes.

It reads the governed corpus at `runtime/baseline_corpus.json`, loads each stable comparison artifact, and passes route-level misses through the shared failure taxonomy. The report is read-only. It does not call the model, gateway, controller, AnythingLLM, or target repositories.

## When To Use

Run this gate when:

- a Priority 0 comparison report fails
- a stable corpus entry is updated
- a repair proposal needs a concrete owner before implementation
- preparing a chat-quality release summary
- checking whether a miss is routing, context gathering, formatting, model capability, safety, documentation, testing, or skill/tool coverage

## Gap Classes

Each comparison miss keeps the existing failure taxonomy category and adds `evidence.gap_class`:

- `routing`
- `context_gathering`
- `skill_tool_selection`
- `deterministic_formatter`
- `model_capability`
- `safety_boundary`
- `documentation`
- `test_coverage`

Each finding also includes a bounded repair action in `evidence.bounded_repair_action`.

## Validation

Validate against the local proof artifacts:

```bash
python scripts/validate_priority0_gap_taxonomy.py \
  --output-path runtime-state/priority0-gap-taxonomy/priority0-gap-taxonomy-report.json
```

Expected clean result for the current stable corpus:

```text
PRIORITY0 GAP TAXONOMY PASS
```

Clean means `finding_count=0`. If a comparison miss appears, the report fails and lists the taxonomy category, gap class, severity, source case, route, selected workflow, score, and bounded repair action.

## Fail-Closed Conditions

The validator fails if:

- a required comparison artifact is missing
- a comparison artifact hash is stale relative to the governed corpus
- any stable comparison route contains unresolved findings
- any stable route fails, scores below the accepted threshold, or has a comparison miss
- a comparison report fails without route-level findings

Use `README.failure-taxonomy.md` for classifying individual validation reports. Use this README when validating the whole Priority 0 corpus.

`--require-artifacts` is the default. Use `--allow-missing-artifacts` only for clean-clone shape inspection, not for stable proof or release readiness.
