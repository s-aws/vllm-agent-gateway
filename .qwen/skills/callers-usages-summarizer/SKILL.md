---
name: callers-usages-summarizer
description: Summarize callers and usages from code_context.lookup relationship evidence. Use for read-only prompts asking who calls, where used, grouped usages, relationship context, and per-file explanations.
---

# Callers Usages Summarizer

Use this skill after `code_context.lookup` returns bounded exact-match, structure, or curated relationship evidence.

## Workflow

1. Identify the requested symbol, function, class, setting, or file.
2. Group usages by file.
3. Separate direct callers/usages from related but indirect references.
4. Explain each usage briefly using evidence references.
5. Record relationship-query gaps when graph evidence is unavailable or bounded.

## Output

Return:

- target
- usage count
- usages grouped by file
- direct callers when known
- indirect references
- confidence and gaps

Do not invoke CodeGraphContext, read new files, or infer unobserved callers.
