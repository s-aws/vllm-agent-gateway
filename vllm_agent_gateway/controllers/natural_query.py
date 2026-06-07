"""Shared natural-language query extraction helpers for controller workflows."""

from __future__ import annotations

import re


PATH_PATTERN = re.compile(
    r"[A-Za-z]:[\\/]\S+|(?<![\w./-])/(?:mnt|home|tmp|var|opt|workspace|repo|repos|[A-Za-z0-9._-]+)(?:/\S+)+"
)


def strip_filesystem_paths(text: str) -> str:
    return PATH_PATTERN.sub(" ", text)


def _clean_change_subject(value: str) -> str:
    text = value.strip(" \t\r\n.,;:!?")
    text = re.sub(r"\b(read only|read-only|stop before implementation|before implementation)\b.*$", "", text, flags=re.I)
    text = re.sub(r"\b(return|include|provide)\b.*$", "", text, flags=re.I)
    text = re.sub(r"^(the|a|an|requested|changing|change to|change)\s+", "", text, flags=re.I)
    text = re.sub(r"\s+(behavior|behaviour|feature|flow|change)$", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" \t\r\n.,;:!?")
    return text


def _identifier_variant(value: str) -> str | None:
    words = re.findall(r"[A-Za-z0-9_]+", value)
    if len(words) < 2:
        return None
    return "_".join(word.lower() for word in words)


def _change_subject_query_variants(subject: str) -> list[str]:
    words = re.findall(r"[A-Za-z0-9_]+", subject)
    variants: list[str] = []
    for word in words:
        if "_" in word and word not in variants:
            variants.append(word)
    identifier = _identifier_variant(subject)
    if identifier and identifier not in variants:
        variants.append(identifier)
    if subject and subject not in variants:
        variants.append(subject)
    return variants


def change_subject_queries_from_request(user_request: str, *, limit: int = 4) -> list[str]:
    """Extract concrete behavior terms from change-boundary prompts.

    Natural change-surface prompts often contain more instruction words than
    symbols. This helper isolates the subject after "for ..." near a change
    surface/boundary phrase and emits both identifier and natural variants so
    bounded exact-text scans can match snake_case code and prose.
    """

    query_source = strip_filesystem_paths(user_request)
    candidates: list[str] = []
    patterns = (
        r"(?:change surface|change boundary|minimal safe change surface).*?\bfor\s+(.+?)(?:[.?!]|$)",
        r"\bfor\s+changing\s+(.+?)(?:[.?!]|$)",
        r"\bfor\s+(.+?\bbehavior)\b",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, query_source, flags=re.I):
            subject = _clean_change_subject(match.group(1))
            if not subject:
                continue
            lowered = subject.lower()
            if "change surface" in lowered or "change boundary" in lowered or "files to touch" in lowered:
                continue
            for value in _change_subject_query_variants(subject):
                if value and value not in candidates:
                    candidates.append(value)
                    if len(candidates) >= limit:
                        return candidates
    return candidates[:limit]


def configuration_queries_from_request(user_request: str, *, limit: int = 4) -> list[str]:
    """Extract concrete configuration identifiers from natural config wording."""

    query_source = strip_filesystem_paths(user_request)
    candidates: list[str] = []
    if re.search(r"\bcoinbase\s+api\s+key\b", query_source, flags=re.I):
        candidates.append("COINBASE_API_KEY")
    return candidates[:limit]
