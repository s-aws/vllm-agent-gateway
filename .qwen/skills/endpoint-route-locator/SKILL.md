---
name: endpoint-route-locator
description: Locate endpoint, route, WebSocket, or message-handler source lines for a named request. Use for read-only coding prompts asking where an endpoint, route handler, message type, request type, or UI/API handler is implemented.
---

# Endpoint Route Locator

Use after `code_investigation.plan` has bounded evidence for a requested endpoint, route, WebSocket message, or handler.

## Workflow

1. Identify the requested route, endpoint path, message type, or handler name exactly.
2. Prefer source evidence over docs when naming the handler.
3. Return handler file, line, role, and matched source text.
4. Include related tests only when present in evidence.
5. Mark missing handler evidence as unknown; do not infer an implementation from docs alone.

## Output

Return:

- target route/message
- handler files and line refs
- handler role
- related tests
- evidence gaps

Do not propose edits or claim all handlers were searched beyond the bounded evidence.
