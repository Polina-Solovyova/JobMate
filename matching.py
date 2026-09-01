import logging
import re
from typing import Dict, List, Set

from rapidfuzz import fuzz

logger = logging.getLogger(__name__)


SYNONYMS = {
    "разработчик": {
        "программист",
        "developer",
        "software developer",
        "software engineer",
        "инженер разработчик",
    },
    "программист": {
        "разработчик",
        "developer",
        "software developer",
        "software engineer",
    },
    "дизайнер": {
        "designer",
        "ux designer",
        "ui designer",
        "product designer",
        "продуктовый дизайнер",
    },
    "backend": {
        "back end",
        "backend developer",
        "бэкенд",
        "бекенд",
    },
    "frontend": {
        "front end",
        "frontend developer",
        "фронтенд",
    },
    "python": {
        "python developer",
        "python разработчик",
    },
    "javascript": {
        "js",
        "javascript developer",
    },
    "typescript": {
        "ts",
    },
    "figma": {
        "фигма",
    },
    "photoshop": {
        "фотошоп",
    },
    "удалённо": {
        "удаленно",
        "удаленка",
        "удалёнка",
        "remote",
        "remote work",
        "дистанционно",
    },
    "удаленно": {
        "удалённо",
        "удаленка",
        "удалёнка",
        "remote",
        "remote work",
        "дистанционно",
    },
    "офис": {
        "в офисе",
        "office",
        "office work",
    },
    "гибрид": {
        "hybrid",
        "гибридный",
        "смешанный формат",
    },
    "полная занятость": {
        "full-time",
        "full time",
        "фуллтайм",
    },
    "частичная занятость": {
        "part-time",
        "part time",
        "парттайм",
    },
    "стажировка": {
        "internship",
        "intern",
        "стажёр",
        "стажер",
    },
    "без опыта": {
        "junior",
        "entry-level",
        "entry level",
        "начинающий",
        "без опыта",
    },
}


def normalize_text(text: str) -> str:
    text = text.lower().replace("ё", "е")

    text = re.sub(
        r"[^\w+#.\-/ ]+",
        " ",
        text,
        flags=re.UNICODE,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    return text


def tokenize(text: str) -> List[str]:
    normalized = normalize_text(text)

    return [
        token
        for token in normalized.split()
        if len(token) > 1
    ]


def _stem_russian_word(word: str) -> str:
    endings = (
        "иями",
        "ами",
        "ями",
        "ого",
        "ему",
        "ому",
        "ими",
        "ыми",
        "ая",
        "яя",
        "ое",
        "ее",
        "ые",
        "ие",
        "ов",
        "ев",
        "ам",
        "ям",
        "ом",
        "ем",
        "ах",
        "ях",
        "ы",
        "и",
        "а",
        "я",
        "о",
        "е",
        "у",
        "ю",
    )

    for ending in endings:
        if len(word) > len(ending) + 2 and word.endswith(ending):
            return word[:-len(ending)]

    return word


def normalize_term(term: str) -> str:
    normalized = normalize_text(term)

    words = normalized.split()

    return " ".join(
        _stem_russian_word(word)
        for word in words
    )


def expand_with_synonyms(term: str) -> List[str]:
    normalized = normalize_text(term)

    variants: Set[str] = {normalized}

    for key, values in SYNONYMS.items():
        key_normalized = normalize_text(key)

        normalized_values = {
            normalize_text(value)
            for value in values
        }

        if normalized == key_normalized:
            variants.add(key_normalized)
            variants.update(normalized_values)

        elif normalized in normalized_values:
            variants.add(key_normalized)
            variants.update(normalized_values)

    return sorted(variants)


def _contains_phrase(
    phrase: str,
    text: str,
) -> bool:
    phrase = normalize_text(phrase)
    text = normalize_text(text)

    if not phrase or not text:
        return False

    if phrase in text:
        return True

    phrase_words = phrase.split()

    if len(phrase_words) == 1:
        return False

    text_words = text.split()
    phrase_len = len(phrase_words)

    for index in range(
        len(text_words) - phrase_len + 1
    ):
        chunk = text_words[
            index:index + phrase_len
        ]

        if all(
            normalize_term(a) == normalize_term(b)
            for a, b in zip(
                phrase_words,
                chunk,
            )
        ):
            return True

    return False


def fuzzy_match(
    needle: str,
    haystack: str,
    threshold: int = 90,
) -> bool:
    needle = normalize_text(needle)
    haystack = normalize_text(haystack)

    if not needle or not haystack:
        return False

    if _contains_phrase(needle, haystack):
        return True

    needle_words = needle.split()

    if len(needle_words) != 1:
        return False

    needle_word = needle_words[0]

    if len(needle_word) < 5:
        return False

    text_words = haystack.split()

    for word in text_words:
        if len(word) < 5:
            continue

        ratio = fuzz.ratio(
            needle_word,
            word,
        )

        if ratio >= threshold:
            return True

    return False


def match_condition(
    condition: str,
    text_lemmas: List[str],
    text_raw: str,
    threshold: int = 90,
) -> bool:
    if not condition:
        return False

    condition_variants = expand_with_synonyms(
        condition
    )

    text_normalized = normalize_text(text_raw)

    text_tokens = set(
        normalize_term(token)
        for token in text_lemmas
    )

    for variant in condition_variants:
        variant_normalized = normalize_text(
            variant
        )

        if _contains_phrase(
            variant_normalized,
            text_normalized,
        ):
            return True

        variant_tokens = [
            normalize_term(token)
            for token in variant_normalized.split()
        ]

        if variant_tokens and all(
            token in text_tokens
            for token in variant_tokens
        ):
            return True

        if len(variant_tokens) == 1:
            if fuzzy_match(
                variant_tokens[0],
                text_normalized,
                threshold,
            ):
                return True

    return False


def match_filter(
    filter_data: Dict,
    vacancy_text: str,
    threshold: int = 90,
) -> Dict:
    if not vacancy_text or not filter_data:
        return {
            "matched": False,
            "score": 0,
            "matched_conditions": [],
            "missing_conditions": [],
            "details": {},
        }

    text_normalized = normalize_text(
        vacancy_text
    )

    text_lemmas = tokenize(
        text_normalized
    )

    required = [
        item
        for item in filter_data.get("required", [])
        if isinstance(item, str) and item.strip()
    ]

    optional = [
        item
        for item in filter_data.get("optional", [])
        if isinstance(item, str) and item.strip()
    ]

    excluded = [
        item
        for item in filter_data.get("excluded", [])
        if isinstance(item, str) and item.strip()
    ]

    matched_required = []
    missing_required = []
    matched_optional = []
    missing_optional = []
    excluded_found = []

    for requirement in required:
        if match_condition(
            requirement,
            text_lemmas,
            text_normalized,
            threshold,
        ):
            matched_required.append(requirement)
        else:
            missing_required.append(requirement)

    if missing_required:
        return {
            "matched": False,
            "score": 0,
            "matched_conditions": matched_required,
            "missing_conditions": missing_required,
            "details": {
                "required": required,
                "optional": optional,
                "excluded": excluded,
                "matched_required": matched_required,
                "matched_optional": [],
                "excluded_found": [],
            },
        }

    for exclusion in excluded:
        if match_condition(
            exclusion,
            text_lemmas,
            text_normalized,
            threshold,
        ):
            excluded_found.append(exclusion)

    if excluded_found:
        return {
            "matched": False,
            "score": 0,
            "matched_conditions": matched_required,
            "missing_conditions": [
                f"Исключено: {', '.join(excluded_found)}"
            ],
            "details": {
                "required": required,
                "optional": optional,
                "excluded": excluded,
                "matched_required": matched_required,
                "matched_optional": [],
                "excluded_found": excluded_found,
            },
        }

    for optional_item in optional:
        if match_condition(
            optional_item,
            text_lemmas,
            text_normalized,
            threshold,
        ):
            matched_optional.append(optional_item)
        else:
            missing_optional.append(optional_item)

    total_conditions = len(required) + len(optional)
    matched_count = (
        len(matched_required)
        + len(matched_optional)
    )

    if total_conditions:
        score = int(
            matched_count
            / total_conditions
            * 100
        )
    else:
        score = 100

    matched_conditions = (
        matched_required
        + matched_optional
    )

    missing_conditions = missing_required + [
        f"Не совпало: {item}"
        for item in missing_optional
    ]

    return {
        "matched": True,
        "score": score,
        "matched_conditions": matched_conditions,
        "missing_conditions": missing_conditions,
        "details": {
            "required": required,
            "optional": optional,
            "excluded": excluded,
            "matched_required": matched_required,
            "matched_optional": matched_optional,
            "excluded_found": excluded_found,
        },
    }


def check_vacancy_against_filter(
    vacancy_text: str,
    filter_data: Dict,
) -> Dict:
    return match_filter(
        filter_data=filter_data,
        vacancy_text=vacancy_text,
    )