---
name: api-reference-locator
description: Find API reference documentation, sample payloads, and contract files for a named request.
---

# api-reference-locator

Use this skill only after registry metadata selects it for the active workflow.

Required behavior:

- Keep the workflow read-only.
- Cite bounded source or documentation evidence.
- Produce or support the `documentation_lookup` artifact path.
- Return gaps instead of guessing when the bounded evidence is incomplete.
- Stop when the request falls outside this prompt family.
