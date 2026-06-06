---
name: code-explanation-summarizer
description: Explain a named function, class, or file from bounded code evidence. Use for read-only coding-agent prompts asking what code does, including inputs, outputs, side effects, related tests, and confidence without planning edits or running tools.
---

# Code Explanation Summarizer

Use this skill after `code_investigation.plan` has gathered bounded evidence for a specific file, function, class, or symbol.

## Workflow

1. Identify the requested code target exactly.
2. Use only supplied evidence, snippets, AST metadata, and test references.
3. Separate observed behavior from inference.
4. Summarize inputs, outputs, state changes, external calls, and error/none cases.
5. List related tests and verification commands only when they are present in evidence.
6. Mark unknowns instead of filling gaps from guesses.

## Output

Return a concise explanation with:

- target
- purpose
- key inputs
- outputs or return behavior
- side effects
- related tests
- confidence and evidence gaps

Do not propose edits, invoke tools, run tests, or claim repository-wide completeness.
