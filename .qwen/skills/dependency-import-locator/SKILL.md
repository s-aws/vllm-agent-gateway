---
name: dependency-import-locator
description: Locate imports and module dependencies for a requested file or module using code_context.lookup evidence. Use for read-only prompts asking what a file imports, depends on, or needs before change planning.
---

# Dependency Import Locator

Use after `code_context.lookup` has selected a file or module for dependency lookup.

## Workflow

1. Identify the target file or module exactly.
2. Use parsed import lines and curated import relationships only.
3. Distinguish direct imports from relationship matches.
4. Return source refs for each dependency when available.
5. Mark absence as bounded, not proven repository-wide.

## Output

Return:

- target file/module
- direct imports
- import relationships when available
- source refs
- gaps

Do not compute impact or recommend edits; dependency lookup is read-only context.
