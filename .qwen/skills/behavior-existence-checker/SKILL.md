---
name: behavior-existence-checker
description: Determine whether a named behavior appears to already exist from bounded read-only evidence. Use for prompts asking yes, no, or unknown about existing behavior without editing files or overclaiming absence.
---

# Behavior Existence Checker

Use this skill when the user asks whether a behavior already exists.

## Workflow

1. Define the behavior in concrete searchable terms.
2. Treat direct source, test, config, or invariant evidence as stronger than naming similarity.
3. Return `yes` only when evidence shows the behavior exists.
4. Return `unknown` when bounded search is shallow or evidence is incomplete.
5. Return `no` only when the evidence scope is strong enough to support absence.
6. Include the exact evidence files and remaining gaps.

## Output

Return:

- answer: yes, no, or unknown
- evidence files
- matching symbols or terms
- confidence
- gaps and recommended next bounded check

Do not plan edits, run tests, or claim full repository coverage from partial data.
