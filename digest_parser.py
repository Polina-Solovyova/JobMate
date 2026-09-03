import re
from typing import Any, Dict, List


# Заголовки категорий внутри подборок.
# Они должны передаваться в текст вакансии, потому что
# "Стажёр: Frontend Developer" и просто "Frontend Developer"
# имеют разный смысл для matching.
CATEGORY_PATTERNS = [
    (
        re.compile(
            r"^(?:стаж[её]р(?:ы)?|intern(?:ship)?s?)\s*:?\s*$",
            re.IGNORECASE,
        ),
        "Стажёр",
    ),
    (
        re.compile(
            r"^(?:junior|джуниор|младш(?:ий|ая|ие))\s*:?\s*$",
            re.IGNORECASE,
        ),
        "Junior",
    ),
    (
        re.compile(
            r"^(?:middle|мидл|средн(?:ий|яя|ие))\s*:?\s*$",
            re.IGNORECASE,
        ),
        "Middle",
    ),
    (
        re.compile(
            r"^(?:senior|сеньор|старш(?:ий|ая|ие))\s*:?\s*$",
            re.IGNORECASE,
        ),
        "Senior",
    ),
    (
        re.compile(
            r"^(?:lead|лид|руководител[ьи])\s*:?\s*$",
            re.IGNORECASE,
        ),
        "Lead",
    ),
]


# Начало отдельного элемента подборки.
ITEM_START_PATTERNS = [
    re.compile(r"^\s*(?:[-–—•▪◦●○])\s+"),
    re.compile(r"^\s*\d{1,3}\s*[\.)]\s+"),
    re.compile(r"^\s*[🔹🔸🔻🔺▪️▫️◾◽⭐🌟👉📌📍💼🧑‍💻]\s+"),
]


# Слова/фразы, которые часто встречаются в заголовках вакансий.
JOB_TITLE_HINTS = (
    "разработчик",
    "developer",
    "frontend developer",
    "backend developer",
    "fullstack developer",
    "engineer",
    "инженер",
    "дизайнер",
    "designer",
    "аналитик",
    "analyst",
    "менеджер",
    "manager",
    "маркетолог",
    "копирайтер",
    "copywriter",
    "исследователь",
    "researcher",
    "архитектор",
    "architect",
    "рекрутер",
    "recruiter",
    "тестировщик",
    "qa",
)


def _clean_line(line: str) -> str:
    """Удаляет лишние пробелы и маркеры списка."""
    line = line.strip()

    line = re.sub(
        r"^\s*(?:[-–—•▪◦●○])\s*",
        "",
        line,
    )

    line = re.sub(
        r"^\s*\d{1,3}\s*[\.)]\s*",
        "",
        line,
    )

    line = re.sub(
        r"^\s*[🔹🔸🔻🔺▪️▫️◾◽⭐🌟👉📌📍💼🧑‍💻]\s*",
        "",
        line,
    )

    return line.strip()


def _is_category(line: str) -> str | None:
    cleaned = _clean_line(line)

    for pattern, category in CATEGORY_PATTERNS:
        if pattern.match(cleaned):
            return category

    return None


def _has_item_marker(line: str) -> bool:
    return any(
        pattern.match(line)
        for pattern in ITEM_START_PATTERNS
    )


def _looks_like_job_title(line: str) -> bool:
    """
    Эвристика для строк без явного маркера списка.

    Например:
        Product Designer
        Frontend Developer (React)
        Младший UX-исследователь
    """
    cleaned = _clean_line(line).lower()

    if len(cleaned) < 4 or len(cleaned) > 180:
        return False

    return any(
        hint in cleaned
        for hint in JOB_TITLE_HINTS
    )


def _looks_like_metadata(line: str) -> bool:
    """
    Определяет строки, которые являются деталями уже найденной вакансии,
    а не началом новой вакансии.
    """
    normalized = line.lower().strip()

    metadata_prefixes = (
        "зарплата",
        "зп",
        "salary",
        "compensation",
        "локация",
        "location",
        "город",
        "формат",
        "занятость",
        "опыт",
        "experience",
        "требования",
        "обязанности",
        "условия",
        "мы предлагаем",
        "навыки",
        "skills",
        "стек",
        "контакты",
        "contact",
        "отклик",
        "ссылка",
        "link",
        "компания",
        "company",
        "работа",
        "remote",
        "удалённо",
        "удаленно",
        "гибрид",
        "hybrid",
        "офис",
        "office",
    )

    if any(
        normalized.startswith(prefix)
        for prefix in metadata_prefixes
    ):
        return True

    # Строка только с зарплатой.
    if re.search(
        r"\d[\d\s.,]*\s*(?:₽|руб\.?|рублей|usd|eur|€|\$)",
        normalized,
        re.IGNORECASE,
    ):
        return True

    return False


def _is_separator(line: str) -> bool:
    normalized = line.strip().lower()

    if not normalized:
        return True

    if re.fullmatch(
        r"[-_=*•·.]{3,}",
        normalized,
    ):
        return True

    return False


def _extract_inline_category(
    line: str,
) -> str | None:
    normalized = line.lower().strip()

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

def split_digest_into_items(text: str) -> List[Dict[str, Any]]:
    """
    Разбивает дайджест на отдельные вакансии.

    Возвращает список:
    {
        "title": str,
        "text": str,
        "category": str | None,
    }

    Важный принцип:
    если парсер не уверен, он лучше вернёт весь пост одним элементом,
    чем потеряет часть вакансий.
    """
    if not text or not text.strip():
        return []

    lines = text.splitlines()

    items: List[Dict[str, Any]] = []

    current_lines: List[str] = []
    current_category: str | None = None

    category_context: str | None = None

    def flush_current() -> None:
        nonlocal current_lines

        if not current_lines:
            return

        cleaned_lines = [
            line.strip()
            for line in current_lines
            if line.strip()
        ]

        if not cleaned_lines:
            current_lines = []
            return

        item_text = "\n".join(cleaned_lines)

        title = _extract_item_title(
            cleaned_lines
        )

        category = category_context

        if category is None:
            category = _extract_inline_category(title)        

        if category:
            contextual_text = (
                f"{category_context}\n"
                f"{item_text}"
            )
        else:
            contextual_text = item_text

        items.append(
            {
                "title": title,
                "text": contextual_text.strip(),
                "category": category,
            }
        )

        current_lines = []

    for raw_line in lines:
        line = raw_line.strip()

        if _is_separator(line):
            continue

        category = _is_category(line)

        if category:
            flush_current()
            category_context = category
            current_category = category
            continue

        has_marker = _has_item_marker(raw_line)

        # Явный новый элемент списка.
        if has_marker:
            flush_current()

            current_lines = [
                _clean_line(line)
            ]

            current_category = category_context
            continue

        # Если текущего элемента нет, а строка выглядит как
        # название вакансии — начинаем новый элемент.
        if not current_lines:
            if _looks_like_job_title(line):
                current_lines = [line]
            else:
                # Заголовок подборки или вступительный текст.
                # Пока не считаем его вакансией.
                continue

            continue

        # Если уже есть вакансия и встретилась новая строка,
        # которая похожа на самостоятельное название вакансии,
        # начинаем новый элемент.
        if (
            _looks_like_job_title(line)
            and not _looks_like_metadata(line)
            and len(current_lines) >= 1
        ):
            # Не разделяем слишком короткие заголовки,
            # чтобы не ломать составные названия.
            if len(line) >= 5:
                flush_current()
                current_lines = [line]
                current_category = category_context
                continue

        current_lines.append(line)

    flush_current()

    # Если нашли меньше двух вакансий, это может быть обычный пост.
    if len(items) < 2:
        return [
            {
                "title": _extract_item_title(
                    [
                        line.strip()
                        for line in lines
                        if line.strip()
                    ]
                ),
                "text": text.strip(),
                "category": None,
            }
        ]

    return items


def _extract_item_title(lines: List[str]) -> str:
    """
    Выбирает наиболее вероятный заголовок вакансии.
    """
    for line in lines[:5]:
        cleaned = _clean_line(line)

        if not cleaned:
            continue

        if _is_category(cleaned):
            continue

        if _looks_like_metadata(cleaned):
            continue

        if len(cleaned) <= 180:
            return cleaned

    return _clean_line(lines[0]) if lines else "Вакансия"


def extract_digest_items(text: str) -> List[Dict[str, Any]]:
    """
    Публичная функция для использования в vacancies.py.
    """
    return split_digest_into_items(text)