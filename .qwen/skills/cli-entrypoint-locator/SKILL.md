---
name: cli-entrypoint-locator
description: Locate CLI or script entrypoints such as main modules, __main__ guards, and runnable commands from bounded read-only evidence.
---

# CLI Entrypoint Locator

Use this skill for prompts asking where a repo, module, CLI, script, or service starts.

## Workflow

1. Keep the repository read-only.
2. Inspect bounded file and AST evidence for `main.py`, `def main`, and `if __name__ == "__main__"` patterns.
3. Return `cli_entrypoint_lookup` with entrypoint files, line refs, command examples, and gaps.
4. Prefer explicit user-supplied paths over broad guessing.
5. If no entrypoint evidence is found, return `unknown` with the missing evidence.

## Output Rules

- Use conservative runnable commands such as `python main.py` only when the matching path exists.
- Always include `mutation_policy: read_only_no_source_mutation`.
