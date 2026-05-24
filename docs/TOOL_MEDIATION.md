# Tool Mediation

Tool mediation is the executable layer between a model-visible tool schema and local tool execution. Prompt text may describe policy, but enforcement happens in code.

`tool_mediator.py` provides:

- OpenAI-compatible tool schema generation from `runtime/tools.json`
- model tool-call detection from structured `message.tool_calls`
- local execution for catalog-backed tools
- tool result injection as `role: tool` messages
- final response validation

Raw tool-call-shaped assistant text is not treated as tool execution. The mediator only executes structured tool calls from the response's `tool_calls` field.

## Supported Tools

The mediator currently implements every tool in `runtime/tools.json`:

- `git_ls_files`
- `git_grep`
- `read_file`
- `scan_files`
- `run_tests`

If a role exposes a tool ID that is missing from the catalog or lacks an executable mediator, schema generation fails closed.

## Basic Use

```python
from pathlib import Path

from tool_mediator import ToolMediator, load_tool_catalog

catalog = load_tool_catalog(Path("."))
mediator = ToolMediator(
    repo_root=Path("/path/to/target/repo"),
    catalog=catalog,
    allowed_tool_ids={"git_ls_files", "read_file"},
)

tools = mediator.tool_schemas
```

`tools` is an OpenAI-compatible list suitable for a chat completion request.

## Execution Loop

`ToolMediator.run_tool_loop()` expects a callable that accepts `(messages, tools)` and returns an OpenAI-style chat completion response:

```python
result = mediator.run_tool_loop(
    messages=[{"role": "user", "content": "List tracked files."}],
    create_chat_completion=my_chat_completion_call,
)
```

The loop:

1. Sends messages plus generated tool schemas to the model caller.
2. Detects structured `message.tool_calls`.
3. Executes only allowed catalog-backed tools.
4. Appends `role: tool` result messages.
5. Calls the model again.
6. Stops only after a final assistant message passes validation.

The final assistant message is rejected if it still contains executable `tool_calls`, empty content, or raw tool-call-shaped text.

## Enforcement

The mediator validates:

- tool ID exists in `runtime/tools.json`
- tool ID has an executable local implementation
- tool ID is allowed by the active role/controller policy
- arguments match the catalog schema
- filesystem paths remain under the target repo root
- local commands are executed without a shell

`run_tests` is intentionally explicit. It runs `python -m pytest` with a list of string arguments and does not accept arbitrary shell text.

## Tests

The deterministic regression suite covers schema generation, tool call detection, local execution, result injection, raw tool-call rejection, path safety, and executable coverage:

```bash
pytest tests/regression/ -v
```
