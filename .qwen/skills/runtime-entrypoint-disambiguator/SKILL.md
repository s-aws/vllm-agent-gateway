---
name: runtime-entrypoint-disambiguator
description: Locate a subsystem runtime entrypoint and distinguish it from adjacent service or UI entrypoints.
---

# runtime-entrypoint-disambiguator

Use this skill only after registry metadata selects it for the active workflow.

Required behavior:

- Keep the workflow read-only.
- Cite bounded source or documentation evidence.
- Produce or support the `cli_entrypoint_lookup` artifact path.
- Return gaps instead of guessing when the bounded evidence is incomplete.
- Stop when the request falls outside this prompt family.
