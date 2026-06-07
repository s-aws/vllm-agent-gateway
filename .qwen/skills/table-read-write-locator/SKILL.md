---
name: table-read-write-locator
description: Locate where a database table is defined, read, and written from bounded source evidence without mutating repository files.
---

# table-read-write-locator

Use this skill only when registry metadata selects it for `code_investigation.plan`.

Required behavior:

- Keep the workflow read-only.
- Treat table definition, read sites, and write sites as separate buckets.
- Classify `CREATE TABLE` as definition, `SELECT ... FROM` or `JOIN` as read, and `INSERT`, `UPDATE`, or `DELETE` as write.
- Preserve gaps for any bucket that is not found in bounded evidence.
- Do not treat schema evidence alone as proof of read/write behavior.

Output contract:

- Support the `table_read_write_lookup` artifact.
- Include `target_table`, `definition_sites`, `read_sites`, `write_sites`, `access_summary`, `source_refs`, `mutation_policy`, and `gaps`.
- Preserve `mutation_policy=read_only_no_source_mutation`.

Stop conditions:

- Stop if the request does not name or imply a database table.
- Stop if the request asks to add, modify, migrate, or refactor database code.
