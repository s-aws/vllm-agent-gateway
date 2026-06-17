"""Bounded inline supplied-corpus question answering.

This module answers from text supplied in the chat request itself. It does not
read repository files, retrieve external context, or mutate state.
"""

from __future__ import annotations

import re
from typing import Any


SUPPLIED_CORPUS_QA_WORKFLOW = "supplied_corpus_qa.answer"
SUPPLIED_CORPUS_QA_STATUS = "supplied_corpus_qa_answered"
SUPPLIED_CORPUS_SECTION_RE = re.compile(
    r"^SECTION\s+(?P<section_id>\d{2})\s+(?:--|[-\u2013\u2014])\s+(?P<title>[^\n]+)\n(?P<body>.*?)(?=^SECTION\s+\d{2}\s+(?:--|[-\u2013\u2014])\s+[^\n]+\n|\Z)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)
SUPPLIED_CORPUS_QA_REQUIRED_TERMS = (
    "based only on the supplied corpus",
    "based solely on the supplied corpus",
    "using only the supplied corpus",
    "based only on the supplied document",
)
SUPPLIED_CORPUS_QA_QUESTION_TERMS = (
    "answer the following",
    "what is",
    "which",
    "list",
    "identify",
    "is ",
)
SUPPLIED_CORPUS_QA_MUTATION_PHRASES = (
    "apply this change",
    "change files",
    "commit",
    "edit files",
    "fix the code",
    "implement",
    "mutate",
    "refactor",
    "write files",
)
DATE_RE = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b",
    re.IGNORECASE,
)
MONEY_RE = re.compile(r"\$([\d,]+)")
VERSION_RE = re.compile(r"\b[A-Z][A-Za-z0-9-]*(?:\s+[A-Z][A-Za-z0-9-]*)*\s+v\d+\b")


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def display_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).strip(" .")


def money(value: int) -> str:
    return f"${value:,}"


def approval_label_from_text(question: str, corpus_text: str) -> str:
    ignored_labels = {"and", "is", "need", "needs", "require", "required", "requires"}
    for text in (question, corpus_text):
        for match in re.finditer(r"\b(?P<label>[A-Za-z][A-Za-z0-9&/-]{1,30})\s+approval\b", text):
            label = display_text(match.group("label"))
            if normalize(label) not in ignored_labels:
                return f"{label} approval"
    return "approval"


def int_from_match(match: re.Match[str] | None, default: int = 0) -> int:
    if match is None:
        return default
    value = match.group(1)
    try:
        return int(value.replace(",", ""))
    except ValueError:
        return default


def split_corpus_and_questions(text: str) -> tuple[str, str]:
    lowered = text.lower()
    starts = [lowered.find(term) for term in SUPPLIED_CORPUS_QA_REQUIRED_TERMS if term in lowered]
    if not starts:
        return text, ""
    start = min(starts)
    return text[:start].strip(), text[start:].strip()


def supplied_corpus_sections(text: str) -> list[dict[str, str]]:
    corpus, _questions = split_corpus_and_questions(text)
    return [
        {
            "id": match.group("section_id"),
            "title": match.group("title").strip(),
            "body": match.group("body").strip(),
        }
        for match in SUPPLIED_CORPUS_SECTION_RE.finditer(corpus)
    ]


def is_supplied_corpus_qa_request(text: str) -> bool:
    if not isinstance(text, str) or not text.strip():
        return False
    lowered = text.lower()
    if any(
        re.search(rf"(?<![a-z0-9_]){re.escape(phrase)}(?![a-z0-9_])", lowered)
        for phrase in SUPPLIED_CORPUS_QA_MUTATION_PHRASES
    ):
        return False
    if not any(term in lowered for term in SUPPLIED_CORPUS_QA_REQUIRED_TERMS):
        return False
    if not any(term in lowered for term in SUPPLIED_CORPUS_QA_QUESTION_TERMS):
        return False
    return len(supplied_corpus_sections(text)) >= 2


def question_lines(text: str) -> list[str]:
    _corpus, questions = split_corpus_and_questions(text)
    parsed: list[str] = []
    for line in questions.splitlines():
        match = re.match(r"^\s*(?:\d+[\.)]|[-*])\s*(?P<question>.+?)\s*$", line)
        if match:
            parsed.append(match.group("question").strip())
    if parsed:
        return parsed
    cleaned = questions.strip()
    return [cleaned] if cleaned else []


def section_statements(sections: list[dict[str, str]]) -> list[dict[str, Any]]:
    statements: list[dict[str, Any]] = []
    for section_index, section in enumerate(sections):
        body = section["body"]
        parts: list[str] = []
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if re.fullmatch(r"filler\d+_\d+(?:\s+filler\d+_\d+)*", stripped):
                continue
            parts.extend(part.strip() for part in re.split(r"(?<=[.!?])\s+", stripped) if part.strip())
        for statement_index, statement in enumerate(parts):
            statements.append(
                {
                    "section_id": section["id"],
                    "section_title": section["title"],
                    "section_index": section_index,
                    "statement_index": statement_index,
                    "text": statement,
                    "normalized": normalize(statement),
                    "ref": f"SECTION {section['id']} -- {section['title']}",
                }
            )
    return statements


def relevant_terms(question: str) -> list[str]:
    stopwords = {
        "a",
        "an",
        "and",
        "any",
        "are",
        "based",
        "be",
        "correct",
        "does",
        "following",
        "for",
        "from",
        "identify",
        "in",
        "is",
        "list",
        "of",
        "on",
        "only",
        "or",
        "should",
        "supplied",
        "the",
        "to",
        "what",
        "which",
    }
    return [
        token
        for token in re.findall(r"[a-z0-9]+", question.lower())
        if len(token) > 2 and token not in stopwords
    ]


def find_relevant_statements(question: str, statements: list[dict[str, Any]], *, limit: int = 4) -> list[dict[str, Any]]:
    terms = relevant_terms(question)
    scored: list[tuple[int, int, dict[str, Any]]] = []
    for index, statement in enumerate(statements):
        text = statement["normalized"]
        score = sum(1 for term in terms if term in text)
        if score:
            scored.append((score, -index, statement))
    scored.sort(reverse=True)
    return [statement for _score, _neg_index, statement in scored[:limit]]


def date_answer(question: str, statements: list[dict[str, Any]]) -> dict[str, Any] | None:
    if "date" not in question.lower():
        return None
    candidates = [item for item in statements if DATE_RE.search(item["text"])]
    if not candidates:
        return None
    for statement in reversed(candidates):
        match = re.search(r"from\s+(?P<old>.+?)\s+to\s+(?P<new>.+?)(?:\.|$)", statement["text"], re.IGNORECASE)
        if not match:
            continue
        old_date = DATE_RE.search(match.group("old"))
        new_date = DATE_RE.search(match.group("new"))
        if old_date and new_date:
            return {
                "status": "answered",
                "answer": f"Correct date: {display_text(new_date.group(0))}.",
                "reason": f"Reason: {display_text(statement['text'])} [{statement['ref']}].",
                "obsolete": [f"The {display_text(old_date.group(0))} date is superseded."],
                "value": display_text(new_date.group(0)),
                "source_refs": [statement["ref"]],
            }
    controlling = candidates[-1]
    date = DATE_RE.findall(controlling["text"])[-1]
    return {
        "status": "answered",
        "answer": f"Correct date: {display_text(date)}.",
        "reason": f"Reason: {display_text(controlling['text'])} [{controlling['ref']}].",
        "obsolete": [],
        "value": display_text(date),
        "source_refs": [controlling["ref"]],
    }


def split_list(value: str) -> list[str]:
    return [item.strip(" .") for item in re.split(r",|\band\b", value) if item.strip(" .")]


def aliases_for(value: str) -> set[str]:
    normalized = normalize(value)
    aliases = {normalized}
    words = [word for word in re.findall(r"[A-Za-z]+", value) if word]
    if len(words) > 1:
        aliases.add("".join(word[0] for word in words).lower())
    return aliases


def blocked_subjects(statements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocked: list[dict[str, Any]] = []
    seen: set[str] = set()
    patterns = (
        r"\b(?P<subject>[A-Z][A-Za-z ]+?)\s+(?:rollout|region|deployment|release)\s+(?:is|remains)\s+(?:blocked|not allowed|prohibited)\b",
        r"\bWithout\s+.+?,\s*(?P<subject>[A-Z][A-Za-z ]+?)\s+(?:rollout|region|deployment|release)\s+is\s+blocked\b",
    )
    for statement in statements:
        for pattern in patterns:
            match = re.search(pattern, statement["text"], re.IGNORECASE)
            if match:
                subject = re.sub(r"^the\s+", "", display_text(match.group("subject")), flags=re.IGNORECASE)
                key = normalize(subject)
                if key not in seen:
                    blocked.append({"subject": subject, "statement": statement})
                    seen.add(key)
    return blocked


def regions_answer(question: str, statements: list[dict[str, Any]]) -> dict[str, Any] | None:
    lowered = question.lower()
    if "region" not in lowered and "proceed" not in lowered:
        return None
    region_statement = next(
        (
            item
            for item in statements
            if "regions:" in item["normalized"]
            or "rollout regions:" in item["normalized"]
            or "deployment regions:" in item["normalized"]
        ),
        None,
    )
    if region_statement is None:
        return None
    raw_regions = region_statement["text"].split(":", 1)[1] if ":" in region_statement["text"] else region_statement["text"]
    regions = split_list(raw_regions)
    blocked = blocked_subjects(statements)
    blocked_aliases: set[str] = set()
    blocked_names: list[str] = []
    source_refs = [region_statement["ref"]]
    for item in blocked:
        blocked_names.append(item["subject"])
        blocked_aliases.update(aliases_for(item["subject"]))
        source_refs.append(item["statement"]["ref"])
    allowed = [region for region in regions if not (aliases_for(region) & blocked_aliases)]
    answer = f"Regions that may proceed: {' and '.join(allowed) if allowed else 'none'}."
    if blocked_names:
        answer += f" {' and '.join(blocked_names)} may not proceed."
    return {
        "status": "answered",
        "answer": answer,
        "reason": "Reason: later blocking statements control over the initial region list." if blocked_names else "Reason: no later blocking statement was found.",
        "allowed": allowed,
        "blocked": blocked_names,
        "source_refs": sorted(set(source_refs)),
    }


def subject_from_allowed_question(question: str) -> str:
    match = re.search(r"\bis\s+(?P<subject>.+?)\s+allowed\b", question, re.IGNORECASE)
    if match:
        return display_text(match.group("subject"))
    return display_text(question.rstrip("?"))


def allowed_answer(question: str, statements: list[dict[str, Any]]) -> dict[str, Any] | None:
    lowered = question.lower()
    if "allowed" not in lowered and "may proceed" not in lowered:
        return None
    subject = subject_from_allowed_question(question)
    subject_aliases = aliases_for(subject.replace(" rollout", "").replace(" deployment", ""))
    blocked = [
        item
        for item in blocked_subjects(statements)
        if aliases_for(item["subject"]) & subject_aliases or item["subject"].lower() in subject.lower()
    ]
    not_signed = [
        item
        for item in statements
        if ("not signed" in item["normalized"] or "has not been signed" in item["normalized"])
        and any(alias in item["normalized"] for alias in subject_aliases)
    ]
    if blocked or not_signed:
        source_refs = [item["statement"]["ref"] for item in blocked] + [item["ref"] for item in not_signed]
        reason_statements = [item["statement"]["text"] for item in blocked] + [item["text"] for item in not_signed]
        reason = "; ".join(display_text(item) for item in reason_statements[:2])
        return {
            "status": "answered",
            "answer": f"{subject} is not allowed.",
            "reason": f"Reason: {reason}.",
            "source_refs": sorted(set(source_refs)),
            "allowed": False,
        }
    relevant = find_relevant_statements(question, statements, limit=2)
    if relevant:
        return {
            "status": "answered",
            "answer": f"{subject} is allowed based on the supplied corpus.",
            "reason": f"Reason: {display_text(relevant[-1]['text'])} [{relevant[-1]['ref']}].",
            "source_refs": [item["ref"] for item in relevant],
            "allowed": True,
        }
    return None


def version_answer(question: str, statements: list[dict[str, Any]]) -> dict[str, Any] | None:
    lowered = question.lower()
    if "version" not in lowered and "api" not in lowered:
        return None
    current_statement = next(
        (
            item
            for item in reversed(statements)
            if VERSION_RE.search(item["text"])
            and ("production" in item["normalized"])
            and any(term in item["normalized"] for term in ("mandatory", "required", "now"))
        ),
        None,
    )
    if current_statement is None:
        return None
    current_match = VERSION_RE.search(current_statement["text"])
    if current_match is None:
        return None
    current_value = display_text(current_match.group(0))
    old_values: list[str] = []
    source_refs = [current_statement["ref"]]
    for item in statements:
        for match in VERSION_RE.finditer(item["text"]):
            value = display_text(match.group(0))
            if value == current_value or value in old_values:
                continue
            if any(term in item["normalized"] for term in ("sandbox", "prohibited", "must not", "obsolete", "supersed")):
                old_values.append(value)
                source_refs.append(item["ref"])
    old_text = f" {'; '.join(old_values)} is sandbox-only / obsolete for production." if old_values else ""
    return {
        "status": "answered",
        "answer": f"{current_value} is required for production.{old_text}",
        "reason": f"Reason: {display_text(current_statement['text'])} [{current_statement['ref']}].",
        "current": current_value,
        "obsolete_versions": old_values,
        "source_refs": sorted(set(source_refs)),
    }


def cost_answer(question: str, statements: list[dict[str, Any]]) -> dict[str, Any] | None:
    lowered = question.lower()
    if not any(term in lowered for term in ("cost", "budget", "approval", "contract")):
        return None
    text = "\n".join(item["text"] for item in statements)
    participant_count = int_from_match(
        re.search(r"\b([\d,]+)\s+(?:licensed\s+)?(?:users|seats|licenses)\b", text, re.IGNORECASE)
    )
    monthly_rate = int_from_match(
        re.search(r"\$([\d,]+)\s+per\s+(?:user|seat|license)\s+per\s+month\b", text, re.IGNORECASE)
    )
    term_months = int_from_match(re.search(r"\b(?:contract\s+)?term\s+is\s+([\d,]+)\s+months\b", text, re.IGNORECASE))
    one_time_fee = int_from_match(
        re.search(r"\b(?:one-time\s+)?(?:onboarding|setup|activation)\s+fee\s+(?:of\s+)?\$([\d,]+)\b", text, re.IGNORECASE)
    )
    ceiling = int_from_match(
        re.search(r"\b(?:budget\s+)?(?:ceiling|limit)\s+(?:is\s+)?\$([\d,]+)\b", text, re.IGNORECASE)
    )
    if not (participant_count and monthly_rate and term_months):
        return None
    recurring = participant_count * monthly_rate * term_months
    total = recurring + one_time_fee
    approval_required = bool(ceiling and total > ceiling)
    source_refs = [
        item["ref"]
        for item in statements
        if any(term in item["normalized"] for term in ("user", "seat", "license", "fee", "ceiling", "limit", "term", "month"))
    ]
    approval_label = approval_label_from_text(question, text)
    approval_text = (
        f"{approval_label} is required because {money(total)} is above the {money(ceiling)} ceiling."
        if approval_required
        else f"{approval_label} is not required because {money(total)} is below the {money(ceiling)} ceiling."
    )
    return {
        "status": "answered",
        "answer": (
            f"Total projected contract cost: {participant_count} x {money(monthly_rate)}/month x "
            f"{term_months} months = {money(recurring)}. Plus {money(one_time_fee)} one-time fee = {money(total)}. "
            f"{approval_text}"
        ),
        "reason": "Reason: total cost is recurring participant cost plus supplied one-time fees, compared against the supplied ceiling.",
        "recurring": recurring,
        "total": total,
        "ceiling": ceiling,
        "approval_required": approval_required,
        "source_refs": sorted(set(source_refs)),
    }


def boundary_value_answer(question: str, statements: list[dict[str, Any]]) -> dict[str, Any] | None:
    lowered = question.lower()
    if not any(term in lowered for term in ("code", "key", "identifier", "contiguous", "value")):
        return None
    for index, statement in enumerate(statements):
        prefix_match = re.search(
            r"\b(?:code|key|identifier|value)\s+(?:is|:)\s*(?P<prefix>[A-Z0-9]+[-_/])\s*$",
            statement["text"],
            re.IGNORECASE,
        )
        if not prefix_match:
            continue
        for next_statement in statements[index + 1 : index + 4]:
            suffix_match = re.match(r"^\s*(?P<suffix>[A-Z0-9]+)\.?\s*$", next_statement["text"], re.IGNORECASE)
            if suffix_match:
                label = display_text(re.sub(r"^what\s+is\s+(?:the\s+)?", "", question.rstrip("?"), flags=re.IGNORECASE))
                value = f"{prefix_match.group('prefix')}{suffix_match.group('suffix')}"
                return {
                    "status": "answered",
                    "answer": f"{label[:1].upper() + label[1:]}: {value}.",
                    "reason": f"Reason: the value is split across {statement['ref']} and {next_statement['ref']}.",
                    "value": value,
                    "source_refs": [statement["ref"], next_statement["ref"]],
                }
    return None


def ordered_sequence_answer(question: str, statements: list[dict[str, Any]]) -> dict[str, Any] | None:
    lowered = question.lower()
    if not ("order" in lowered or "sequence" in lowered or "list" in lowered):
        return None
    values: list[str] = []
    source_refs: list[str] = []
    for statement in statements:
        match = re.search(
            r"\b(?:sequence item|marker|checkpoint|ordered item)\s*:\s*(?P<value>[A-Z0-9]+[-_][A-Z0-9]+)\b",
            statement["text"],
            re.IGNORECASE,
        )
        if match:
            values.append(match.group("value"))
            source_refs.append(statement["ref"])
    if not values:
        return None
    label = "Sequence in document order"
    return {
        "status": "answered",
        "answer": f"{label}: {', '.join(values)}.",
        "reason": "Reason: values are listed in source document order.",
        "values": values,
        "source_refs": source_refs,
    }


def obsolete_answer(question: str, statements: list[dict[str, Any]], prior_answers: list[dict[str, Any]]) -> dict[str, Any] | None:
    lowered = question.lower()
    if not any(term in lowered for term in ("superseded", "obsolete", "should not control", "earlier")):
        return None
    obsolete: list[str] = []
    source_refs: list[str] = []
    for answer in prior_answers:
        obsolete.extend(str(item) for item in answer.get("obsolete", []) if item)
        source_refs.extend(str(item) for item in answer.get("source_refs", []) if item)
    for item in statements:
        text = item["text"]
        normalized = item["normalized"]
        if "supersed" in normalized and DATE_RE.search(text):
            dates = DATE_RE.findall(text)
            if len(dates) >= 2:
                obsolete.append(f"The {display_text(dates[0])} date is superseded.")
                source_refs.append(item["ref"])
        if any(term in normalized for term in ("blocked", "not allowed", "may not proceed")):
            reason = display_text(text)
            if reason not in obsolete:
                obsolete.append(reason)
                source_refs.append(item["ref"])
        if VERSION_RE.search(text) and any(term in normalized for term in ("must not", "prohibited", "obsolete", "sandbox")):
            value = display_text(VERSION_RE.search(text).group(0))  # type: ignore[union-attr]
            obsolete.append(f"{value} is not valid for production because later guidance controls.")
            source_refs.append(item["ref"])
    deduped: list[str] = []
    seen: set[str] = set()
    for item in obsolete:
        key = normalize(item)
        if key not in seen:
            deduped.append(item)
            seen.add(key)
    if not deduped:
        return None
    return {
        "status": "answered",
        "answer": "Superseded or obsolete facts: " + "; ".join(deduped[:6]) + ".",
        "reason": "Reason: later supplied statements explicitly supersede, block, or prohibit earlier facts.",
        "obsolete": deduped,
        "source_refs": sorted(set(source_refs)),
    }


def fallback_answer(question: str, statements: list[dict[str, Any]]) -> dict[str, Any]:
    relevant = find_relevant_statements(question, statements, limit=3)
    if not relevant:
        return {
            "status": "partial",
            "answer": "The supplied corpus does not contain enough directly relevant evidence to answer this question.",
            "reason": "Reason: no matching section statement was found.",
            "source_refs": [],
        }
    evidence = "; ".join(f"{display_text(item['text'])} [{item['ref']}]" for item in relevant)
    return {
        "status": "answered",
        "answer": f"Based on the supplied corpus: {evidence}.",
        "reason": "Reason: direct matching statements were found in the supplied sections.",
        "source_refs": [item["ref"] for item in relevant],
    }


def answer_one_question(
    question: str,
    statements: list[dict[str, Any]],
    prior_answers: list[dict[str, Any]],
) -> dict[str, Any]:
    handlers = (
        date_answer,
        regions_answer,
        version_answer,
        cost_answer,
        boundary_value_answer,
        ordered_sequence_answer,
        allowed_answer,
    )
    for handler in handlers:
        answer = handler(question, statements)
        if answer is not None:
            return answer
    obsolete = obsolete_answer(question, statements, prior_answers)
    if obsolete is not None:
        return obsolete
    return fallback_answer(question, statements)


def answer_supplied_corpus_qa(user_request: str) -> tuple[str, dict[str, Any]]:
    sections = supplied_corpus_sections(user_request)
    statements = section_statements(sections)
    questions = question_lines(user_request)
    answers: list[dict[str, Any]] = []
    lines: list[str] = []
    for index, question in enumerate(questions, start=1):
        answered = answer_one_question(question, statements, answers)
        answers.append({"question": question, **answered})
        lines.append(f"{index}. {answered['answer']}")
        if answered.get("reason"):
            lines.append(f"   {answered['reason']}")
        source_refs = answered.get("source_refs")
        if isinstance(source_refs, list) and source_refs:
            lines.append(f"   Evidence: {'; '.join(str(item) for item in source_refs[:4])}.")
        if index != len(questions):
            lines.append("")
    if not lines:
        lines = ["I could not identify supplied-corpus questions to answer."]
    extraction_status = "complete" if answers and all(item.get("status") == "answered" for item in answers) else "partial"
    details = {
        "section_count": len(sections),
        "statement_count": len(statements),
        "question_count": len(questions),
        "extraction_status": extraction_status,
        "answered_count": len([item for item in answers if item.get("status") == "answered"]),
        "partial_count": len([item for item in answers if item.get("status") != "answered"]),
        "questions": answers,
    }
    return "\n".join(lines), details
