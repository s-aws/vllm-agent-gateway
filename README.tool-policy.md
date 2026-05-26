# Tool Policy

Tool policy separates what a prompt says from what the runtime can actually execute.

`runtime/tools.json` defines available local capabilities. `runtime/roles.json` assigns tool IDs to roles. Controllers and the tool mediator enforce those assignments.

## Tool Catalog

Current tool IDs:

- `git_ls_files`: list tracked repository files.
- `git_grep`: search tracked repository content with line numbers.
- `read_file`: read a controller-selected repository file.
- `scan_files`: scan repository files for first-run/bootstrap discovery.
- `run_tests`: run an explicit test command selected by controller policy.

## Role Assignment

Roles declare `tool_ids` in `runtime/roles.json`.

For example, `documenter/default` can use controller-authorized discovery and read tools, while tester/implementer roles can also use test execution policy.

## Controller Tool Dependencies

Controller reports include tool dependency records so runs can be audited against the role's assigned tools.

Examples:

- documenter tracked discovery requires `git_ls_files`
- documenter file reading requires `read_file`
- all-file bootstrap discovery requires `scan_files`
- implementation verification requires `run_tests`

## Tool Mediation

`vllm_agent_gateway/tools/mediator.py` provides a model-mediated tool loop:

```text
tool schema -> model tool call -> local execution -> tool result -> final model answer
```

It generates OpenAI-compatible tool schemas from `runtime/tools.json`, executes only allowed catalog-backed tools, injects tool results, and rejects raw tool-call-shaped assistant text as incomplete tool execution.

Reference: [docs/TOOL_MEDIATION.md](docs/TOOL_MEDIATION.md)

Examples: [docs/examples/tool-policy.md](docs/examples/tool-policy.md)
