# Code Structure Indexes

Code structure indexes provide deterministic source, documentation, and config context before handing work to a role.

They are controller-side and read-only. The indexer parses files with stdlib parsers or line scanners and never imports or executes target code.

## Supported Indexes

- Python AST records:
  - modules
  - classes
  - functions
  - imports
  - decorators
  - docstrings
  - line ranges
  - syntax errors
- Markdown/AsciiDoc/reStructuredText records:
  - headings
  - anchors
  - relative links
  - unresolved links
  - inbound/outbound edges
- JSON/YAML records:
  - dotted key paths
  - scalar previews
  - line ranges where available
  - parse errors

## Artifacts

- `code-structure-index-*.json`: full deterministic index for selected supported files.
- `code-structure-slice-*.json`: bounded `structure_index_slice` records for future role packets.

## File Scope

Default scope is tracked files. `--file-scope all` performs a bootstrap scan and skips common generated directories such as `.git`, `.venv`, `node_modules`, build output, caches, and `.agentic_reports`.

## References

- Examples: [docs/examples/code-structure-indexes.md](docs/examples/code-structure-indexes.md)
- Roadmap phase: [docs/DOCUMENTER_E2E_ROADMAP.md](docs/DOCUMENTER_E2E_ROADMAP.md#phase-12-code-structure-indexes)
