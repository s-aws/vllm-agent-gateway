---
name: request-flow-mapper
description: Map a request, message, or data flow across bounded source evidence without editing files, including ordered flow steps, participating files, risks, gaps, tests, and verification commands.
---

# Request Flow Mapper

Use this skill for read-only prompts asking how a request, message, event, or data item flows through code.

## Workflow

1. Identify the requested flow target and starting message, endpoint, command, or symbol.
2. Use bounded evidence to order observed source files from entrypoint to downstream behavior.
3. Include tests and docs only as supporting evidence, not as flow steps unless they define the behavior.
4. Mark missing transitions as gaps instead of inventing a full call graph.
5. Keep the result diagnostic and stop before implementation.

## Output Rules

- Return `request_flow_map`.
- Include target flow, ordered flow steps, participating files, related tests, risks, gaps, verification commands, and source refs.
- Always include `mutation_policy: read_only_no_source_mutation`.
