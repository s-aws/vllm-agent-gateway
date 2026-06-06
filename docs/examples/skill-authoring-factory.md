# Skill Authoring Factory Examples

Run a dry scaffold through the controller service:

```bash
curl -sS http://127.0.0.1:8400/v1/controller/skill-scaffolds \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow": "skill.scaffold",
    "schema_version": 1,
    "prompt_family_spec": {
      "skill_id": "example-factory-locator",
      "description": "Locate bounded source evidence for an example factory prompt family.",
      "prompt_family": "example-factory-lookup",
      "natural_prompt": "In <repo>, find the example factory evidence. Read only.",
      "workflow_id": "code_investigation.plan",
      "route_key": "code.example_factory_lookup",
      "trigger_terms": ["example factory lookup"],
      "task_types": ["example_factory_lookup"],
      "output_artifact": "investigation_plan",
      "live_suite": "skill_registry_contract",
      "coverage_id": "EXAMPLE-FACTORY-LOOKUP",
      "level": "L1",
      "route_rule": "l1_find_behavior_start_terms",
      "tool_ids": ["git_grep", "read_file"]
    }
  }'
```

Expected response markers:

```text
workflow: skill.scaffold
scaffold_status: ready
authoring_factory_status: draft_sidecars_generated
promotion_state: not_promoted_by_scaffold
```

Expected Phase 80 artifacts:

- `prompt_coverage_entry`
- `eval_skeleton`
- `docs_stub`
- `docs_example_stub`
- `regression_test_skeleton`
- `authoring_factory_report`

The generated regression skeleton intentionally fails closed:

```text
pytest.fail("Install the scaffolded route rule before enabling this test.")
pytest.fail("Install the scaffolded skill and eval case before enabling this test.")
pytest.fail("Prove the natural-language chat answer before enabling this test.")
pytest.fail("Install and validate the prompt coverage entry before enabling this test.")
```

Review order:

1. Inspect `batch_validation_report`.
2. Inspect `authoring_factory_report`.
3. Keep `prompt_coverage_entry.status` as `planned` until the skill is installed.
4. Enable the regression skeleton only after the route, artifacts, chat output, and coverage are wired.
5. Register or install through the existing approval-gated lifecycle path.

Run the live proof:

```bash
cd /mnt/c/agentic_agents
export ANYTHINGLLM_API_KEY="${ANYTHINGLLM_API_KEY:?set AnythingLLM API key first}"
python3 scripts/validate_skill_authoring_factory_live.py --timeout-seconds 900
```

Expected marker:

```text
SKILL AUTHORING FACTORY LIVE PASS
```
