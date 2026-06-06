---
name: test-selection-rationale
description: Build smallest, medium, and broad validation tiers with rationale from bounded evidence. Use for L2 prompts asking which tests to run, why each command is relevant, covered risks, confidence, and remaining gaps.
---

# Test Selection Rationale

Use this skill when the user asks for tiered validation commands with rationale.

## Workflow

1. Identify the exact behavior or risk under validation.
2. Select the smallest command that directly targets the behavior.
3. Select a medium command for adjacent unit or regression coverage.
4. Select a broad command only when repository evidence supports it.
5. For each command, state covered risk, confidence, and gaps.

## Output

Return:

- smallest command
- medium command
- broad command
- rationale
- covered risks
- confidence
- gaps

Do not run tests or choose commands unrelated to the evidence.
