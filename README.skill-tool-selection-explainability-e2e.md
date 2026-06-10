# Skill/Tool Selection Explainability E2E

Phase 151 proves that normal chat responses explain why the router selected a workflow, skills, and tools.

This is not a separate selector. The gate reads the normal workflow-router response, fetches the same controller run artifacts, and checks that the visible chat output matches the existing `route_decision` and `registry_snapshot` evidence.

## What It Verifies

- gateway and AnythingLLM both return the explanation in normal FormatA chat
- selected workflow, selected skills, selected tools, route rules, confidence, and coverage entries are visible
- rejected workflow, skill, and tool candidate counts are visible
- grounding points back to route-decision and registry artifacts
- manual skill injection is not required
- raw selector internals are not dumped into chat as JSON
- both frozen Coinbase fixtures remain unchanged

## What It Reads

Policy:

```text
runtime/skill_tool_selection_explainability_e2e_policy.json
```

Source cases:

```text
runtime/skill_selection_hardening_cases.json
```

The default Phase 151 cases are `SEL-001`, `SEL-002`, and `SEL-003`.

## What It Produces

JSON:

```text
runtime-state/skill-tool-selection-explainability-e2e/phase151/phase151-skill-tool-selection-explainability-e2e-report.json
```

Markdown:

```text
runtime-state/skill-tool-selection-explainability-e2e/phase151/phase151-skill-tool-selection-explainability-e2e-report.md
```

## Run

From Bash with the local model, gateway, controller, and AnythingLLM running:

```bash
export ANYTHINGLLM_API_KEY="${ANYTHINGLLM_API_KEY:?set AnythingLLM API key first}"

python3 scripts/validate_skill_tool_selection_explainability_e2e.py \
  --output-path runtime-state/skill-tool-selection-explainability-e2e/phase151/phase151-skill-tool-selection-explainability-e2e-report.json \
  --markdown-output-path runtime-state/skill-tool-selection-explainability-e2e/phase151/phase151-skill-tool-selection-explainability-e2e-report.md
```

Expected marker:

```text
SKILL TOOL SELECTION EXPLAINABILITY E2E PASS
```

## Failure Meaning

- Missing `Skill Selection:` means the user cannot see why the harness chose the path.
- Missing rejected counts means the chat response does not prove competing candidates were considered.
- Missing grounding means the explanation is not traceable to controller artifacts.
- Raw internal JSON in chat means the renderer leaked implementation detail instead of producing a user-facing explanation.

Examples: [docs/examples/skill-tool-selection-explainability-e2e.md](docs/examples/skill-tool-selection-explainability-e2e.md).
