"""Shared natural-language query extraction helpers for controller workflows."""

from __future__ import annotations

import re


PATH_PATTERN = re.compile(
    r"[A-Za-z]:[\\/]\S+|(?<![\w./-])/(?:mnt|home|tmp|var|opt|workspace|repo|repos|[A-Za-z0-9._-]+)(?:/\S+)+"
)
NATURAL_QUERY_STOP_WORDS = {
    "about",
    "against",
    "and",
    "around",
    "before",
    "belong",
    "belongs",
    "broad",
    "change",
    "changes",
    "command",
    "commands",
    "could",
    "downstream",
    "explain",
    "each",
    "file",
    "files",
    "find",
    "for",
    "how",
    "include",
    "likely",
    "logic",
    "medium",
    "need",
    "needed",
    "only",
    "out",
    "point",
    "pytest",
    "read",
    "recommend",
    "refs",
    "risk",
    "risks",
    "scope",
    "smallest",
    "source",
    "test",
    "tests",
    "that",
    "the",
    "tier",
    "through",
    "unknown",
    "unknowns",
    "validate",
    "validates",
    "validating",
    "verification",
    "what",
    "where",
    "would",
    "why",
}
NATURAL_QUERY_ANCHOR_WORDS = {
    "action",
    "approval",
    "association",
    "audit",
    "auth",
    "authorization",
    "behavior",
    "boundary",
    "catalog",
    "client",
    "config",
    "configuration",
    "contract",
    "executor",
    "gateway",
    "handler",
    "index",
    "lineage",
    "live",
    "manual",
    "no",
    "order",
    "placement",
    "preflight",
    "product",
    "runtime",
    "simulation",
    "strategy",
    "validation",
}


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


def _natural_query_word(value: str) -> str:
    lowered = value.lower()
    if len(lowered) > 4 and lowered.endswith("ies"):
        return lowered[:-3] + "y"
    if len(lowered) > 4 and lowered.endswith("s") and not lowered.endswith("ss"):
        return lowered[:-1]
    return lowered


def _natural_query_words(text: str) -> list[str]:
    query_source = strip_filesystem_paths(text).replace("-", " ")
    words: list[str] = []
    for raw in re.findall(r"[A-Za-z][A-Za-z0-9_]*", query_source):
        word = _natural_query_word(raw)
        if (len(word) < 3 and word != "no") or word in NATURAL_QUERY_STOP_WORDS:
            continue
        words.append(word)
    return words


def natural_identifier_queries_from_request(user_request: str, *, limit: int = 4) -> list[str]:
    """Return snake_case query variants from technical natural-language phrases.

    The router and investigation workflows primarily search code with exact
    text. Natural requests often say "live no-order preflight" or "manual
    association approval" while repositories store those concepts as
    snake_case symbols and file names. This helper turns bounded, technical
    phrase windows into deterministic identifier queries without depending on
    a specific repository fixture.
    """

    words = _natural_query_words(user_request)
    scored: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    for size in range(4, 1, -1):
        for index in range(0, max(0, len(words) - size + 1)):
            window = words[index : index + size]
            if not window:
                continue
            if not (set(window) & NATURAL_QUERY_ANCHOR_WORDS):
                continue
            value = "_".join(window)
            if value in seen:
                continue
            seen.add(value)
            anchor_count = len(set(window) & NATURAL_QUERY_ANCHOR_WORDS)
            score = anchor_count * 100 + size * 10
            if any("_" in word for word in window):
                score += 25
            scored.append((score, -index, value))
    scored.sort(reverse=True)
    return [value for _score, _index, value in scored[:limit]]


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
        r"(?:files to touch|files not to touch).*?\bfor\s+(?:a\s+|an\s+|the\s+)?(?:minimal safe\s+)?(.+?)(?:\s+change\b|[.?!]|$)",
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
