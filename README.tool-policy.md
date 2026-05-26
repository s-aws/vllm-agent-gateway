# Tool Policy

Tool policy separates what a prompt says from what the runtime can actually execute.

`runtime/tools.json` defines available local capabilities. `runtime/roles.json` assigns tool IDs to roles. `runtime/workflows.json` defines which tools each workflow can enable. Controllers and the tool mediator enforce those assignments.

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

## Workflow Assignment

Workflows declare `controller_tool_ids`, optional conditional controller tools, allowed role IDs, model-visible tool IDs, and controller action audit records in `runtime/workflows.json`.

The controller resolves the workflow and role policy together at request time. The enabled tool set must be allowed by both:

```text
enabled tools = workflow tools constrained by role tools
```

Denied role/tool combinations fail before the workflow creates artifacts.

## Controller Tool Dependencies

Controller reports include tool dependency records so runs can be audited against the role's assigned tools.

Controller service run records also include a `tool_policy` audit record with:

- workflow and role IDs
- controller tool IDs enabled for the run
- model-visible tool IDs enabled for the run
- denied tool IDs, when a request fails policy resolution
- controller action records tying tool IDs to result artifact areas

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

The controller service uses the mediator schema generator during policy resolution to ensure every enabled controller or model-visible tool ID maps to an executable local capability.

Reference: [docs/TOOL_MEDIATION.md](docs/TOOL_MEDIATION.md)

Examples: [docs/examples/tool-policy.md](docs/examples/tool-policy.md)
