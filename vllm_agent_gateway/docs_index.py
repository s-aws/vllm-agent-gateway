"""Documentation index validation helpers."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse


DOC_GLOBS = ("README*.md", "docs/*.md", "docs/examples/*.md")
IGNORED_INDEX_DOCS = {"docs/README.md"}
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def relative_path(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def iter_project_markdown_docs(repo_root: Path) -> list[str]:
    docs: set[str] = set()
    for pattern in DOC_GLOBS:
        for path in repo_root.glob(pattern):
            if path.is_file() and path.suffix == ".md":
                docs.add(relative_path(path, repo_root))
    return sorted(docs - IGNORED_INDEX_DOCS)


def markdown_link_targets(index_path: Path) -> list[str]:
    text = index_path.read_text(encoding="utf-8")
    targets: list[str] = []
    for match in MARKDOWN_LINK_RE.finditer(text):
        target = match.group(1).strip()
        if target.startswith("<") and target.endswith(">"):
            target = target[1:-1]
        targets.append(target.split()[0])
    return targets


def linked_markdown_docs(repo_root: Path, index_path: Path) -> list[str]:
    linked: set[str] = set()
    for target in markdown_link_targets(index_path):
        parsed = urlparse(target)
        if parsed.scheme or parsed.netloc or target.startswith("#"):
            continue
        path_part = parsed.path.split("#", 1)[0]
        if not path_part.endswith(".md"):
            continue
        candidate = (index_path.parent / path_part).resolve()
        if not candidate.exists() or candidate.suffix != ".md":
            continue
        try:
            linked.add(relative_path(candidate, repo_root))
        except ValueError:
            continue
    return sorted(linked)


def docs_index_report(repo_root: Path, index_path: Path | None = None) -> dict[str, object]:
    root = repo_root.resolve()
    index = index_path or root / "docs" / "README.md"
    expected = iter_project_markdown_docs(root)
    linked = linked_markdown_docs(root, index)
    expected_set = set(expected)
    linked_set = set(linked)
    orphaned = sorted(expected_set - linked_set)
    extra = sorted(linked_set - expected_set)
    return {
        "status": "passed" if not orphaned else "failed",
        "index_path": relative_path(index, root),
        "expected_count": len(expected),
        "linked_count": len(linked),
        "orphaned_docs": orphaned,
        "extra_linked_docs": extra,
    }


def validate_docs_index(repo_root: Path, index_path: Path | None = None) -> dict[str, object]:
    report = docs_index_report(repo_root, index_path)
    if report["status"] != "passed":
        orphaned = ", ".join(report["orphaned_docs"])  # type: ignore[index]
        raise RuntimeError(f"docs index has orphaned markdown docs: {orphaned}")
    return report
