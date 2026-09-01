import re
from typing import Any, Dict, List


LOCATION_KEYWORDS = (
    "удалён",
    "удален",
    "remote",
    "дистанцион",
    "гибрид",
    "hybrid",
    "офис",
    "office",
)

EXPERIENCE_KEYWORDS = (
    "junior",
    "middle",
    "senior",
    "стажёр",
    "стажер",
    "intern",
    "опыт",
    "experience",
    "без опыта",
)

OPTIONAL_PREFIXES = (
    "желательно",
    "будет плюсом",
    "плюсом",
    "желателен",
)

EXCLUSION_PREFIXES = (
    "не ",
    "но не ",
    "кроме ",
)


def _clean_part(value: str) -> str:
    value = re.sub(r"\s+", " ", value)
    return value.strip(" \t\n,.;:-")


def _is_location(value: str) -> bool:
    normalized = value.lower()

    return any(
        keyword in normalized
        for keyword in LOCATION_KEYWORDS
    )


def _is_experience(value: str) -> bool:
    normalized = value.lower()

    return any(
        keyword in normalized
        for keyword in EXPERIENCE_KEYWORDS
    )


def _is_optional(value: str) -> bool:
    normalized = value.lower().strip()

    return any(
        normalized.startswith(prefix)
        for prefix in OPTIONAL_PREFIXES
    )


def _extract_exclusion(part: str) -> str | None:
    value = _clean_part(part)
    normalized = value.lower()

    for prefix in EXCLUSION_PREFIXES:
        if normalized.startswith(prefix):
            excluded = value[len(prefix):].strip()

            if excluded:
                return excluded

    return None


def _split_query(query: str) -> List[str]:
    """
    Разбивает запрос на логические части.

    Запятые и ';' считаются разделителями.
    Союз "и" внутри фразы не разделяем автоматически,
    чтобы не ломать конструкции вроде "Python и Django".
    """
    parts = re.split(r"[,;]+", query)

    return [
        _clean_part(part)
        for part in parts
        if _clean_part(part)
    ]


def parse_query_to_filter(query: str) -> Dict[str, Any]:
    """
    Преобразует запрос пользователя в плоскую модель фильтра.

    Пример:

        Python developer, удалённо, без опыта,
        но не data analyst

    ->
        {
            "name": "Python developer",
            "query": "...",
            "keywords": [...],
            "required": [
                "Python developer",
                "удалённо",
                "без опыта",
            ],
            "optional": [],
            "excluded": [
                "data analyst",
            ],
            "location": "удалённо",
            "experience": "без опыта",
        }
    """
    original_query = (query or "").strip()

    if not original_query:
        return {
            "error": "Пустой запрос",
        }

    parts = _split_query(original_query)

    if not parts:
        return {
            "error": "Не удалось разобрать запрос",
        }

    required: List[str] = []
    optional: List[str] = []
    excluded: List[str] = []

    location = None
    experience = None

    for index, part in enumerate(parts):
        exclusion = _extract_exclusion(part)

        if exclusion:
            excluded.append(exclusion)
            continue

        if _is_optional(part):
            cleaned = re.sub(
                r"^(желательно|будет плюсом|плюсом|желателен)\s*:?\s*",
                "",
                part,
                flags=re.IGNORECASE,
            )

            cleaned = _clean_part(cleaned)

            if cleaned:
                optional.append(cleaned)

            continue

        required.append(part)

        if _is_location(part):
            location = part

        if _is_experience(part):
            experience = part

    # Специально обрабатываем "без опыта":
    # это требование к вакансии, а не исключение.
    #
    # Например:
    # "Python разработчик, без опыта"
    #
    # должно означать:
    # required = ["Python разработчик", "без опыта"]
    #
    # а не:
    # excluded = ["опыта"].

    if not required and not optional:
        return {
            "error": "Не удалось определить условия фильтра",
        }

    name = (
        required[0]
        if required
        else optional[0]
    )

    name = name[:80]

    return {
        "name": name,
        "query": original_query,
        "keywords": parts,
        "required": required,
        "optional": optional,
        "excluded": excluded,
        "location": location,
        "experience": experience,
        "salary_min": None,
        "salary_max": None,
    }