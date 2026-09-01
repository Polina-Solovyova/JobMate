import re
from typing import Any, Dict, List, Optional

from matching import check_vacancy_against_filter


VACANCY_INDICATORS = [
    "вакансия",
    "вакансии",
    "вакансию",
    "ищем сотрудника",
    "ищем специалиста",
    "ищем разработчика",
    "требуется",
    "требуются",
    "нужен сотрудник",
    "нужен специалист",
    "нужен разработчик",
    "на работу",
    "в команду",
    "открыта вакансия",
    "открыты вакансии",
    "позиция",
    "job opening",
    "job opportunity",
    "vacancy",
    "hiring",
    "we are hiring",
    "join our team",
    "open position",
]

JOB_ACTION_INDICATORS = [
    "обязанности",
    "требования",
    "условия",
    "что предстоит делать",
    "что нужно делать",
    "мы предлагаем",
    "мы ищем",
    "вы будете",
    "от вас требуется",
    "будет плюсом",
    "мы предлагаем",
    "responsibilities",
    "requirements",
    "qualifications",
    "we offer",
    "what you will do",
]

EMPLOYMENT_INDICATORS = [
    "зарплата",
    "зп",
    "оклад",
    "доход",
    "руб",
    "₽",
    "usd",
    "eur",
    "€",
    "$",
    "remote",
    "удалённо",
    "удаленно",
    "гибрид",
    "hybrid",
    "офис",
    "полная занятость",
    "частичная занятость",
    "full-time",
    "part-time",
    "full time",
    "part time",
]

NOT_VACANCY_INDICATORS = [
    "реклама",
    "рекламный пост",
    "новости",
    "дайджест",
    "подборка вакансий",
    "анонс",
    "мероприятие",
    "вебинар",
    "конференция",
    "митап",
    "курс",
    "обучение",
    "скидка",
    "акция",
    "промокод",
    "розыгрыш",
]

SKILL_PATTERNS = [
    "python",
    "java",
    "javascript",
    "typescript",
    "c++",
    "c#",
    "go",
    "golang",
    "php",
    "ruby",
    "kotlin",
    "swift",
    "rust",
    "react",
    "vue",
    "angular",
    "next.js",
    "node.js",
    "sql",
    "postgresql",
    "mysql",
    "mongodb",
    "redis",
    "docker",
    "kubernetes",
    "linux",
    "git",
    "figma",
    "photoshop",
    "illustrator",
    "jira",
    "confluence",
    "salesforce",
    "tableau",
    "power bi",
    "excel",
    "seo",
    "google ads",
    "facebook ads",
    "marketing",
    "scrum",
    "agile",
    "product management",
    "project management",
    "ux",
    "ui",
]

LOCATION_PATTERNS = [
    "удалённо",
    "удаленно",
    "remote",
    "дистанционно",
    "удалёнка",
    "удаленка",
    "гибрид",
    "hybrid",
    "офис",
    "office",
]

TITLE_PATTERNS = [
    "вакансия",
    "ищем",
    "требуется",
    "позиция",
    "job",
    "vacancy",
    "hiring",
]


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _contains_term(text: str, term: str) -> bool:
    escaped = re.escape(term.lower())
    return re.search(
        rf"(?<!\w){escaped}(?!\w)",
        text,
        re.IGNORECASE,
    ) is not None


def is_vacancy(text: str) -> bool:
    if not text or len(text.strip()) < 20:
        return False

    normalized = _normalize_text(text)

    negative_count = sum(
        1 for indicator in NOT_VACANCY_INDICATORS
        if _contains_term(normalized, indicator)
    )

    if negative_count >= 2:
        return False

    vacancy_count = sum(
        1 for indicator in VACANCY_INDICATORS
        if _contains_term(normalized, indicator)
    )

    job_action_count = sum(
        1 for indicator in JOB_ACTION_INDICATORS
        if _contains_term(normalized, indicator)
    )

    employment_count = sum(
        1 for indicator in EMPLOYMENT_INDICATORS
        if _contains_term(normalized, indicator)
    )

    has_salary = bool(
        re.search(
            r"(?:зп|зарплата|оклад|salary|compensation)"
            r"\s*[:\-]?\s*"
            r"(?:от|до)?\s*"
            r"\d[\d\s.,]*"
            r"\s*(?:₽|руб\.?|рублей|usd|eur|€|\$)?",
            normalized,
            re.IGNORECASE,
        )
    )

    has_contact = bool(
        re.search(
            r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
            text,
        )
        or re.search(
            r"\+?\d[\d\s().-]{7,}\d",
            text,
        )
    )

    has_vacancy_marker = vacancy_count >= 1
    has_job_structure = job_action_count >= 1
    has_employment_signal = employment_count >= 1

    if has_vacancy_marker:
        return True

    if has_job_structure and has_employment_signal:
        return True

    if has_job_structure and has_salary:
        return True

    if has_job_structure and has_contact:
        return True

    return False


def _extract_salary(text: str) -> Optional[str]:
    patterns = [
        r"(?:зп|зарплата|оклад|salary|compensation)"
        r"\s*[:\-]?\s*"
        r"((?:от|до)?\s*\d[\d\s.,]*\s*(?:₽|руб\.?|рублей|usd|eur|€|\$)?)",

        r"(\d[\d\s.,]*)\s*(?:₽|руб\.?|рублей|usd|eur|€|\$)"
        r"(?:\s*[-–—]\s*\d[\d\s.,]*\s*(?:₽|руб\.?|рублей|usd|eur|€|\$)?)?",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            return re.sub(r"\s+", " ", match.group(0)).strip()

    return None


def _extract_contacts(text: str) -> Optional[str]:
    contacts = []

    emails = re.findall(
        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        text,
    )

    phones = re.findall(
        r"\+?\d[\d\s().-]{7,}\d",
        text,
    )

    for contact in emails + phones:
        contact = contact.strip()

        if contact not in contacts:
            contacts.append(contact)

    if not contacts:
        return None

    return ", ".join(contacts)


def _extract_title(text: str) -> Optional[str]:
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    if not lines:
        return None

    for line in lines[:8]:
        normalized = line.lower()

        if any(
            _contains_term(normalized, pattern)
            for pattern in TITLE_PATTERNS
        ):
            cleaned = re.sub(
                r"^[#*_•\-\s]+",
                "",
                line,
            ).strip()

            if 3 <= len(cleaned) <= 150:
                return cleaned

    for line in lines[:5]:
        cleaned = re.sub(
            r"^[#*_•\-\s]+",
            "",
            line,
        ).strip()

        if 3 <= len(cleaned) <= 100:
            return cleaned

    return None


def _extract_location(text: str) -> Optional[str]:
    normalized = text.lower()

    if re.search(r"\b(?:remote|удалённо|удаленно|дистанционно)\b", normalized):
        return "Удалённо"

    if re.search(r"\b(?:hybrid|гибрид)\b", normalized):
        return "Гибрид"

    office_match = re.search(
        r"(?:офис|office)\s*(?:в|:|-)?\s*([А-ЯЁA-Z][А-ЯЁA-Zа-яёa-z-]{2,})",
        text,
        re.IGNORECASE,
    )

    if office_match:
        return office_match.group(1)

    location_match = re.search(
        r"(?:в городе|локация|location|город)\s*[:\-]?\s*"
        r"([А-ЯЁA-Z][А-ЯЁA-Zа-яёa-z-]{2,})",
        text,
        re.IGNORECASE,
    )

    if location_match:
        return location_match.group(1)

    return None


def _extract_experience(text: str) -> Optional[str]:
    patterns = [
        r"(?:опыт|experience)"
        r"\s*(?:работы)?\s*"
        r"(?:от\s*)?"
        r"\d+\+?\s*(?:год(?:а|ов)?|лет|year(?:s)?)",

        r"(?:от\s*)?\d+\+?\s*(?:год(?:а|ов)?|лет|year(?:s)?)"
        r"\s*(?:опыта|experience)?",

        r"(?:без опыта|no experience|entry[- ]level|junior)",
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            text,
            re.IGNORECASE,
        )

        if match:
            return match.group(0).strip()

    return None


def _extract_skills(text: str) -> List[str]:
    normalized = text.lower()
    found = []

    for skill in SKILL_PATTERNS:
        if _contains_term(normalized, skill):
            found.append(skill)

    return sorted(set(found))


def extract_vacancy(text: str) -> Dict[str, Any]:
    raw_text = text or ""
    cleaned_text = raw_text.strip()

    return {
        "title": _extract_title(cleaned_text),
        "company": None,
        "salary": _extract_salary(cleaned_text),
        "location": _extract_location(cleaned_text),
        "experience": _extract_experience(cleaned_text),
        "description": cleaned_text,
        "contacts": _extract_contacts(cleaned_text),
        "skills": _extract_skills(cleaned_text),
        "raw_text": raw_text,
    }


def normalize_vacancy(vacancy_data: Dict[str, Any]) -> Dict[str, Any]:
    normalized = vacancy_data.copy()

    for key, value in normalized.items():
        if isinstance(value, str):
            normalized[key] = re.sub(
                r"\s+",
                " ",
                value,
            ).strip()

        elif isinstance(value, list):
            normalized[key] = sorted(
                set(
                    item.strip()
                    for item in value
                    if isinstance(item, str) and item.strip()
                )
            )

    return normalized


def process_post(post_text: str) -> Optional[Dict[str, Any]]:
    if not is_vacancy(post_text):
        return None

    return normalize_vacancy(
        extract_vacancy(post_text)
    )


def process_post_with_filters(
    post_text: str,
    filters: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    vacancy_data = process_post(post_text)

    if not vacancy_data:
        return []

    results = []

    for filter_item in filters:
        filter_data = filter_item.get("filter_data") or {}

        filter_id = str(
            filter_item.get("_id", "unknown")
        )

        filter_name = filter_data.get(
            "name",
            "Без названия",
        )

        match_result = check_vacancy_against_filter(
            vacancy_text=post_text,
            filter_data=filter_data,
        )

        results.append(
            {
                "filter_id": filter_id,
                "filter_name": filter_name,
                "matched": match_result.get("matched", False),
                "score": match_result.get("score", 0),
                "matched_conditions": match_result.get(
                    "matched_conditions",
                    [],
                ),
                "missing_conditions": match_result.get(
                    "missing_conditions",
                    [],
                ),
                "match_result": match_result,
                "vacancy_data": vacancy_data,
            }
        )

    return results