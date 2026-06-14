# Workflow/Skill/Tool Selection Matrix

Phase 203 refreshes the deterministic selection expectation matrix for M3.

The matrix starts from `runtime/prompt_skill_coverage.json`, then verifies that every implemented prompt-family entry references registered workflows, skills, and tools. It also records which entries already have Phase 151 explainability proof, Phase 187 multi-fixture proof, holdout proof, which entries still need Phase 204 live explainability coverage, and which entries need Phase 205 holdout replay coverage.

## Outputs

- `runtime-state/phase203/phase203-workflow-skill-tool-selection-matrix-report.json`
- `runtime-state/phase203/phase203-workflow-skill-tool-selection-matrix-report.md`

## Command

```bash
python3 scripts/validate_workflow_skill_tool_selection_matrix.py
```

Expected passing marker:

```text
PHASE203 WORKFLOW SKILL TOOL SELECTION MATRIX PASS
```

## Boundary

Phase 203 is a deterministic matrix refresh. It does not prove every natural prompt live. Phase 204 uses this matrix to run the no-manual-skill-injection and selection-explainability gate.
