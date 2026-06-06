# Code Investigation Plan

`code_investigation.plan` is a controller-owned read-only workflow for turning a behavior, symbol, file, or concern into bounded investigation artifacts.

It does not call the model, does not expose raw CodeGraphContext, and does not mutate the target repository.

## When To Use It

Use this workflow when a tester or agent needs to:

- resolve a likely beginning point for a behavior
- collect bounded source, documentation, and test references
- identify whether bounded evidence suggests one source path or possible multiple paths
- discover related test files from bounded request terms and produce evidence-backed pytest commands
- produce a packet seed for later `execution_planning.plan` use

Do not use it to apply edits, run broad graph queries, or claim full uniqueness of a behavior path outside the bounded evidence.

## Endpoints

Direct controller endpoint:

```text
POST /v1/controller/code-investigation/plans
```

OpenAI-style harness endpoint:

```text
POST /v1/controller/harness/chat/completions
```

The harness endpoint requires an explicit `agentic_controller_request` envelope.

## Request Shape

```json
{
  "workflow": "code_investigation.plan",
  "schema_version": 1,
  "target_root": "/mnt/c/coinbase_testing_repo_frozen_tmp",
  "user_request": "Investigate whether StealthOrderManager.find_stealth_order_by_placed_order_id has one path before planning a refactor.",
  "behavior": "placed_order_id stealth lookup",
  "entrypoint_hints": [
    {
      "path": "core/stealth_order_manager.py",
      "symbol": "StealthOrderManager.find_stealth_order_by_placed_order_id",
      "reason": "Known owner of placed-order lookup behavior."
    }
  ],
  "queries": [
    "find_stealth_order_by_placed_order_id",
    "placed_order_id"
  ],
  "paths": [
    "core/stealth_order_manager.py",
    "tests/unit/test_order_id_and_followup_rules.py",
    "tests/regression/test_order_id_regression.py"
  ],
  "max_results": 50,
  "max_files": 10
}
```

## Artifacts

Artifacts are written under:

```text
CONTROLLER_OUTPUT_ROOT/code-investigation/<run-id>/
```

Typical artifacts:

- `request.json`
- `investigation-evidence.json`
- `investigation-plan.json`
- `run-state.json`

`investigation-plan.json` includes `related_tests` and `verification_plan.verification_commands` when bounded test discovery finds matching test-file evidence. If no related tests are found, the plan records that as a gap instead of inventing commands.

The compact response includes the run ID, artifact paths, a summary, warnings, and the controller tool-policy audit record.

## Validation

Regression covers:

- direct endpoint investigation with bounded artifacts
- harness adapter investigation with prior envelope history
- raw CodeGraphContext rejection

Live Bash validation has also passed through:

- direct controller endpoint on `8400`
- gateway controller-envelope route on `8300`
- AnythingLLM workspace chat with AnythingLLM pointed at `http://127.0.0.1:8300/v1`
- both frozen validation fixtures, with selected file hashes unchanged

Examples: [docs/examples/code-investigation.md](docs/examples/code-investigation.md).
