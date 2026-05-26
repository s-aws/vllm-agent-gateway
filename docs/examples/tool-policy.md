# Tool Policy Examples

Inspect role tool assignments:

```bash
python -m json.tool runtime/roles.json
```

Inspect the tool catalog:

```bash
python -m json.tool runtime/tools.json
```

Documenter tracked discovery requires these controller tools:

```text
git_ls_files
read_file
```

Documenter all-file bootstrap discovery additionally requires:

```text
scan_files
```

Implementation verification uses controller-declared pytest commands through:

```text
run_tests
```

Run the tool mediator regression tests:

```bash
pytest tests/regression/test_tool_mediator.py -v
```

Expected mediator flow:

```text
tool schema -> model tool call -> local execution -> tool result -> final model answer
```

Raw tool-call-shaped assistant text is rejected as incomplete execution; a real local tool call must run before the final answer is accepted.
