---
name: multi-file-investigation-planner
description: Summarize how a behavior flows across multiple files from bounded investigation evidence. Use for L2 read-only prompts asking for beginning point, participating files, callers/usages, risks, tests, and verification.
---

# Multi File Investigation Planner

Use this skill when bounded evidence spans more than one source or test file.

## Workflow

1. Start with the logic beginning point.
2. List participating files in the observed order of behavior flow when possible.
3. Identify callers/usages and dependency edges only from evidence.
4. Tie related tests to the files or risks they cover.
5. Highlight risks, gaps, and unknown paths.
6. Recommend the smallest verification commands.

## Output

Return:

- beginning point
- participating files
- callers/usages
- related tests
- risks
- verification commands
- source mutation: false

Do not plan edits or invent missing flow edges.
