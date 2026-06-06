---
name: related-test-discovery
description: Identify tests related to a named behavior from bounded investigation evidence. Use for read-only prompts asking for related tests, test files, matching terms, likely coverage, and safe commands without editing or running tests.
---

# Related Test Discovery

Use this skill when the user asks which tests are related to a behavior, symbol, file, failure, or configuration setting.

## Workflow

1. Extract the behavior terms, symbol names, and file paths from the request.
2. Prefer tests that directly mention the behavior, symbol, public API, or invariant.
3. Separate direct tests from indirect or speculative tests.
4. Include why each test is relevant using evidence references.
5. Recommend the smallest safe command before broader commands.
6. Record gaps when bounded evidence does not prove coverage.

## Output

Return:

- direct related tests
- indirect related tests
- matching terms used
- smallest safe command
- broader optional commands
- coverage gaps

Do not edit files, run tests, or invent test names.
