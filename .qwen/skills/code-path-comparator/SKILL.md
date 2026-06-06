---
name: code-path-comparator
description: Compare two candidate code paths from bounded read-only evidence, including candidate evidence, risks, gaps, source refs, and a recommended path only when evidence supports it.
---

# Code Path Comparator

Use this skill for read-only prompts asking to compare two candidate code paths or lookup strategies.

## Workflow

1. Identify the two named candidate paths from the request.
2. Collect bounded evidence for each candidate path.
3. Compare by ownership, source references, related tests, runtime risk, and evidence gaps.
4. Recommend a path only when the evidence supports a clear recommendation.
5. Stop before edit planning, packet design, or refactor execution.

## Output Rules

- Return `code_path_comparison`.
- Include candidate paths, evidence, comparison summary, recommended path, risks, gaps, verification commands, and source refs.
- Always include `mutation_policy: read_only_no_source_mutation`.
