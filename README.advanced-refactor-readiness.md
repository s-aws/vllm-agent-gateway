# Advanced Refactor Readiness

Phase 105 adds a fail-closed readiness gate for advanced single-path refactor prompts.

The gate is not a broad refactor implementation. It composes existing proof artifacts and decides whether limited pilots may proceed through the existing approval-gated, disposable-copy-only workflow boundary.

## When To Use It

Use this before testing natural prompts such as:

```text
In <repo>, refactor <behavior> so there is only one code path. Start from the logic beginning point.
```

The gate answers:

- whether implementation prep is proven
- whether approval continuation is robust
- whether disposable-copy apply and rollback are proven
- whether both frozen Coinbase fixtures and multi-repo layouts are covered
- whether live all-port and AnythingLLM proof exists
- whether natural advanced-refactor prompts are currently blocked or pilot-ready

## Output

The canonical runtime gate report is:

```text
runtime-state/advanced-refactor-readiness/phase105-readiness.json
```

The Markdown companion is:

```text
runtime-state/advanced-refactor-readiness/phase105-readiness.md
```

Key fields:

- `status`: report validity, `passed` or `failed`
- `readiness_status`: `blocked` or `pilot_ready`
- `prerequisites[]`: exact evidence paths and pass/fail details
- `pilot_prompt_set.status`: `blocked` or `admitted`
- `pilot_prompt_set.policy`: `approval_gated_disposable_copy_only`
- `stable_promotion.enabled`: always `false` in Phase 105

## Runtime Guard

The workflow router reads the canonical report when natural language matches `single_path_refactor_terms`.

If the report is missing, invalid, blocked, or not passed, the route is blocked with:

```text
advanced_refactor_readiness_not_met
```

If the report is `pilot_ready`, the router may run `refactor.single_path` in read-only investigation mode and request packet-design approval. Source apply is still not enabled.

## Generate The Report

```bash
python scripts/report_advanced_refactor_readiness.py
```

Expected markers:

```text
ADVANCED REFACTOR READINESS REPORT ...
ADVANCED REFACTOR READINESS SUMMARY ...
ADVANCED REFACTOR READINESS PASS
```

## Live Validation

After the controller and workflow-router gateway are running with the project root and both frozen fixtures in `CONTROLLER_ALLOWED_TARGET_ROOTS`, run:

```bash
python scripts/validate_advanced_refactor_readiness_live.py
```

This checks localhost `8000`, `8300`, `8400`, `8500`, `8101`, `8102`, and `8201` through `8205`, then sends the natural advanced-refactor prompt through the workflow-router gateway and AnythingLLM for both frozen Coinbase fixtures. It writes:

```text
runtime-state/advanced-refactor-readiness/phase105-live-natural.json
```

## Safety

Phase 105 does not promote broad refactor orchestration to stable.

Pilot prompts, if admitted, must remain:

- approval-gated
- disposable-copy-only for mutation proof
- ineligible for stable-channel promotion
- backed by explicit prerequisite evidence

## Regression

Focused regression:

```bash
python -m pytest tests/regression/test_advanced_refactor_readiness.py -q
```

All non-agent code changes still require:

```bash
python -m pytest tests/regression/ -v
```
