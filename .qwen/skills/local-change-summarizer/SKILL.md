---
name: local-change-summarizer
description: Summarize recent commits, git status, changed files, and non-git limitations from read-only local repository evidence.
---

# Local Change Summarizer

Use this skill for prompts asking what changed recently, what local changes exist, or what git status shows.

## Workflow

1. Keep the target repository read-only.
2. Use only non-mutating git commands such as status, log, and diff summary.
3. Return `local_change_summary` with git status, recent commits, changed files, source refs, and gaps.
4. If the target is not a git repository, return a limited/unsupported status instead of fabricating history.
5. Do not stage, reset, checkout, clean, commit, or modify files.

## Output Rules

- Use `status: ready` for git repositories with readable status.
- Use `status: limited_non_git` for non-git targets.
- Always include `mutation_policy: read_only_no_source_mutation`.
