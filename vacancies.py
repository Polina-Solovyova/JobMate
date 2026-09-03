import re
from typing import Any, Dict, List, Optional

from digest_parser import extract_digest_items
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


# Эти слова сами по себе не должны убивать дайджест.
# "дайджест" и "подборка вакансий" здесь специально НЕ находятся.
NOT_VACANCY_INDICATORS = [
    "реклама",
    "рекламный пост",
    "новости",
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


DIGEST_INDICATORS = [
    "подборка вакансий",
    "подборка вакансий дня",
    "вакансии дня",
    "вакансия дня",
    "вакансии недели",
    "вакансии месяца",
    "лучшие вакансии",
    "новые вакансии",
    "свежие вакансии",
    "горячие вакансии",
    "дайджест вакансий",
    "job digest",
    "vacancy digest",
    "daily jobs",
    "jobs of the day",
    "job of the day",
]


DAILY_DIGEST_INDICATORS = [
    "вакансии дня",
    "вакансия дня",
    "подборка вакансий дня",
    "daily jobs",
    "jobs of the day",
    "job of the day",
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
    return re.sub(
        r"\s+",
        " ",
        (text or "").lower(),
    ).strip()


def _contains_term(
    text: str,
    term: str,
) -> bool:
    escaped = re.escape(term.lower())

    return re.search(
        rf"(?<!\w){escaped}(?!\w)",
        text,
        re.IGNORECASE,
    ) is not None


def detect_post_type(text: str) -> str:
    """
    Определяет тип Telegram-поста.

    Возможные значения:
    - vacancy
    - digest
    - daily_digest
    - unknown
    """
    if not text or len(text.strip()) < 10:
        return "unknown"

    normalized = _normalize_text(text)

    # Сначала проверяем дайджесты.
    if any(
        _contains_term(normalized, indicator)
        for indicator in DAILY_DIGEST_INDICATORS
    ):
        return "daily_digest"

    if any(
        _contains_term(normalized, indicator)
        for indicator in DIGEST_INDICATORS
    ):
        return "digest"

    # После этого определяем обычную вакансию.
    if is_vacancy(text):
        return "vacancy"

    return "unknown"


def is_vacancy(text: str) -> bool:
    """
    Определяет, похож ли пост на обычную вакансию.

    Дайджесты здесь не определяются как отдельный тип:
    для них используется detect_post_type().
    """
    if not text or len(text.strip()) < 20:
        return False

    normalized = _normalize_text(text)

    negative_count = sum(
        1
        for indicator in NOT_VACANCY_INDICATORS
        if _contains_term(normalized, indicator)
    )

    if negative_count >= 2:
        return False

    vacancy_count = sum(
        1
        for indicator in VACANCY_INDICATORS
        if _contains_term(normalized, indicator)
    )

    job_action_count = sum(
        1
        for indicator in JOB_ACTION_INDICATORS
        if _contains_term(normalized, indicator)
    )

    employment_count = sum(
        1
        for indicator in EMPLOYMENT_INDICATORS
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

    if vacancy_count >= 1:
        return True

    if job_action_count >= 1 and employment_count >= 1:
        return True

    if job_action_count >= 1 and has_salary:
        return True

    if job_action_count >= 1 and has_contact:
        return True

    return False


def _extract_salary(
    text: str,
) -> Optional[str]:
    patterns = [
        (
            r"(?:зп|зарплата|оклад|salary|compensation)"
            r"\s*[:\-]?\s*"
            r"((?:от|до)?\s*\d[\d\s.,]*"
            r"\s*(?:₽|руб\.?|рублей|usd|eur|€|\$)?)"
        ),
        (
            r"(\d[\d\s.,]*)"
            r"\s*(?:₽|руб\.?|рублей|usd|eur|€|\$)"
            r"(?:\s*[-–—]\s*\d[\d\s.,]*"
            r"\s*(?:₽|руб\.?|рублей|usd|eur|€|\$)?)?"
        ),
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            text,
            re.IGNORECASE,
        )

        if match:
            return re.sub(
                r"\s+",
                " ",
                match.group(0),
            ).strip()

    return None


def _extract_contacts(
    text: str,
) -> Optional[str]:
    contacts: List[str] = []

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


def _extract_title(
    text: str,
) -> Optional[str]:
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
                r"^[#*_\-•\s]+",
                "",
                line,
            ).strip()

            if 3 <= len(cleaned) <= 150:
                return cleaned

    for line in lines[:5]:
        cleaned = re.sub(
            r"^[#*_\-•\s]+",
            "",
            line,
        ).strip()

        if 3 <= len(cleaned) <= 100:
            return cleaned

    return None


def _extract_location(
    text: str,
) -> Optional[str]:
    normalized = text.lower()

    if re.search(
        r"\b(?:remote|удалённо|удаленно|дистанционно|"
        r"удалёнка|удаленка)\b",
        normalized,
    ):
        return "Удалённо"

    if re.search(
        r"\b(?:hybrid|гибрид)\b",
        normalized,
    ):
        return "Гибрид"

    office_match = re.search(
        r"(?:офис|office)"
        r"\s*(?:в|:|-)?\s*"
        r"([А-ЯЁA-Z][А-ЯЁA-Zа-яёa-z-]{2,})",
        text,
        re.IGNORECASE,
    )

    if office_match:
        return office_match.group(1)

    location_match = re.search(
        r"(?:в городе|локация|location|город)"
        r"\s*[:\-]?\s*"
        r"([А-ЯЁA-Z][А-ЯЁA-Zа-яёa-z-]{2,})",
        text,
        re.IGNORECASE,
    )

    if location_match:
        return location_match.group(1)

    return None


def _extract_experience(
    text: str,
) -> Optional[str]:
    patterns = [
        (
            r"(?:опыт|experience)"
            r"\s*(?:работы)?\s*"
            r"(?:от\s*)?"
            r"\d+\+?\s*"
            r"(?:год(?:а|ов)?|лет|year(?:s)?)"
        ),
        (
            r"(?:от\s*)?\d+\+?\s*"
            r"(?:год(?:а|ов)?|лет|year(?:s)?)"
            r"\s*(?:опыта|experience)?"
        ),
        (
            r"(?:без опыта|no experience|entry[- ]level|junior|"
            r"стаж[её]р|intern)"
        ),
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


def _extract_skills(
    text: str,
) -> List[str]:
    normalized = text.lower()
    found: List[str] = []

    for skill in SKILL_PATTERNS:
        if _contains_term(
            normalized,
            skill,
        ):
            found.append(skill)

    return sorted(set(found))


def _extract_category(
    text: str,
) -> Optional[str]:
    normalized = _normalize_text(text)

    if re.search(
        r"\b(?:стаж[её]р|intern|internship)\b",
        normalized,
        re.IGNORECASE,
    ):
        return "Стажёр"

    if re.search(
        r"\b(?:junior|джуниор|джун)\b",
        normalized,
        re.IGNORECASE,
    ):
        return "Junior"

    if re.search(
        r"\b(?:middle|мидл)\b",
        normalized,
        re.IGNORECASE,
    ):
        return "Middle"

    if re.search(
        r"\b(?:senior|сеньор)\b",
        normalized,
        re.IGNORECASE,
    ):
        return "Senior"

    if re.search(
        r"\b(?:lead|лид)\b",
        normalized,
        re.IGNORECASE,
    ):
        return "Lead"

    return None


def extract_vacancy(
    text: str,
) -> Dict[str, Any]:
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


def normalize_vacancy(
    vacancy_data: Dict[str, Any],
) -> Dict[str, Any]:
    normalized = dict(vacancy_data)

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
                    if isinstance(item, str)
                    and item.strip()
                )
            )

    return normalized


def _process_single_vacancy(
    vacancy_text: str,
    filters: List[Dict[str, Any]],
    category: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Проверяет одну конкретную вакансию по всем фильтрам.
    """
    contextual_text = vacancy_text

    if category:
        contextual_text = (
            f"{category}\n"
            f"{vacancy_text}"
        )

    vacancy_data = normalize_vacancy(
        extract_vacancy(contextual_text)
    )

    filter_results: List[Dict[str, Any]] = []
    matched_filters: List[Dict[str, Any]] = []

    for filter_item in filters:
        if not filter_item.get(
            "enabled",
            True,
        ):
            continue

        filter_result = check_vacancy_against_filter(
            vacancy_text=contextual_text,
            filter_data=filter_item,
        )

        result = {
            "filter_id": str(
                filter_item.get(
                    "_id",
                    "",
                )
            ),
            "filter_name": filter_item.get(
                "name",
                "Без названия",
            ),
            "matched": filter_result.get(
                "matched",
                False,
            ),
            "score": filter_result.get(
                "score",
                0,
            ),
            "matched_conditions": filter_result.get(
                "matched_conditions",
                [],
            ),
            "missing_conditions": filter_result.get(
                "missing_conditions",
                [],
            ),
            "match_result": filter_result,
        }

        filter_results.append(result)

        if result["matched"]:
            matched_filters.append(result)

    return {
        "vacancy_data": vacancy_data,
        "matched_filters": matched_filters,
        "filter_results": filter_results,
    }


def process_post_with_filters(
    post_text: str,
    filters: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Обрабатывает обычную вакансию или дайджест.

    Для обычного поста:
        vacancies = [одна вакансия]

    Для дайджеста:
        vacancies = [вакансия 1, вакансия 2, ...]

    Каждая вакансия отдельно проверяется по каждому фильтру.
    """
    post_text = post_text or ""

    post_type = detect_post_type(
        post_text
    )

    if post_type == "unknown":
        return {
            "is_vacancy": False,
            "post_type": "unknown",
            "vacancy_data": None,
            "vacancies": [],
            "matched_filters": [],
            "filter_results": [],
        }

    # -------------------------
    # Обычная вакансия
    # -------------------------
    if post_type == "vacancy":
        processed = _process_single_vacancy(
            vacancy_text=post_text,
            filters=filters,
        )

        return {
            "is_vacancy": True,
            "post_type": "vacancy",
            "vacancy_data": processed[
                "vacancy_data"
            ],
            "vacancies": [
                {
                    "index": 1,
                    "title": processed[
                        "vacancy_data"
                    ].get(
                        "title"
                    ),
                    "text": post_text.strip(),
                    "category": _extract_category(post_text),
                    "vacancy_data": processed[
                        "vacancy_data"
                    ],
                    "matched_filters": processed[
                        "matched_filters"
                    ],
                    "filter_results": processed[
                        "filter_results"
                    ],
                }
            ],
            "matched_filters": processed[
                "matched_filters"
            ],
            "filter_results": processed[
                "filter_results"
            ],
        }

    # -------------------------
    # Дайджест
    # -------------------------
    items = extract_digest_items(
        post_text
    )

    if not items:
        return {
            "is_vacancy": False,
            "post_type": post_type,
            "vacancy_data": None,
            "vacancies": [],
            "matched_filters": [],
            "filter_results": [],
        }

    processed_vacancies: List[
        Dict[str, Any]
    ] = []

    all_matched_filters: List[
        Dict[str, Any]
    ] = []

    all_filter_results: List[
        Dict[str, Any]
    ] = []

    for index, item in enumerate(
        items,
        start=1,
    ):
        processed = _process_single_vacancy(
            vacancy_text=item["text"],
            filters=filters,
            category=item.get(
                "category"
            ),
        )

        vacancy_result = {
            "index": index,
            "title": item.get(
                "title"
            ),
            "text": item.get(
                "text",
                "",
            ),
            "category": item.get(
                "category"
            ),
            "vacancy_data": processed[
                "vacancy_data"
            ],
            "matched_filters": processed[
                "matched_filters"
            ],
            "filter_results": processed[
                "filter_results"
            ],
        }

        processed_vacancies.append(
            vacancy_result
        )

        all_matched_filters.extend(
            processed[
                "matched_filters"
            ]
        )

        all_filter_results.extend(
            processed[
                "filter_results"
            ]
        )

    has_matching_vacancy = any(
        vacancy["matched_filters"]
        for vacancy in processed_vacancies
    )

    return {
        "is_vacancy": True,
        "post_type": post_type,
        "vacancy_data": (
            processed_vacancies[0][
                "vacancy_data"
            ]
            if processed_vacancies
            else None
        ),
        "vacancies": processed_vacancies,
        "matched_filters": all_matched_filters,
        "filter_results": all_filter_results,
        "has_matching_vacancy": has_matching_vacancy,
    }