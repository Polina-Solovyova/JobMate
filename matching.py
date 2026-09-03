"""
JobMate vacancy/filter matching.

This module provides a hybrid lexical matcher that combines:
- text normalization;
- lightweight Russian stemming;
- synonyms;
- phrase matching;
- fuzzy matching;
- token matching;
- weighted scoring;
- hard exclusions.

Semantic/ML matching is intentionally kept outside this module.
It can be added later through semantic_matching.py without changing
the public API of this module.

Public API:
    match_condition()
    match_filter()
    check_vacancy_against_filter()
"""

import logging
import re
from typing import Any, Dict, List, Set, Tuple

from rapidfuzz import fuzz


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_FUZZY_THRESHOLD = 88

# A required condition is important, but one missed lexical condition
# should no longer automatically make the whole vacancy irrelevant.
#
# These weights are intentionally conservative. Semantic matching can later
# become another signal inside calculate_condition_score().
REQUIRED_WEIGHT = 1.0
OPTIONAL_WEIGHT = 0.35

# Hard exclusion is always stronger than a positive match.
EXCLUSION_PENALTY = 100.0


# ---------------------------------------------------------------------------
# Synonyms
# ---------------------------------------------------------------------------

SYNONYMS: Dict[str, Set[str]] = {
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
        "ux/ui designer",
        "product designer",
        "продуктовый дизайнер",
    },
    "ux дизайнер": {
        "ux designer",
        "ux/ui designer",
        "user experience designer",
        "дизайнер ux",
        "дизайнер пользовательского опыта",
    },
    "ui дизайнер": {
        "ui designer",
        "ux/ui designer",
        "user interface designer",
        "дизайнер ui",
    },
    "product designer": {
        "продуктовый дизайнер",
        "дизайнер продукта",
        "дизайнер цифровых продуктов",
    },
    "backend": {
        "back end",
        "backend developer",
        "бэкенд",
        "бекенд",
        "серверная разработка",
    },
    "frontend": {
        "front end",
        "frontend developer",
        "фронтенд",
        "фронтенд разработчик",
        "клиентская разработка",
    },
    "python": {
        "python developer",
        "python разработчик",
        "питон",
    },
    "javascript": {
        "js",
        "javascript developer",
        "javascript разработчик",
    },
    "typescript": {
        "ts",
        "typescript developer",
    },
    "figma": {
        "фигма",
    },
    "photoshop": {
        "фотошоп",
    },
    "illustrator": {
        "иллюстратор",
    },
    "удалённо": {
        "удаленно",
        "удаленка",
        "удалёнка",
        "remote",
        "remote work",
        "remote job",
        "дистанционно",
        "дистанционная работа",
        "работа из дома",
        "работа на удаленке",
        "работа на удалёнке",
        "из дома",
    },
    "удаленно": {
        "удалённо",
        "удаленка",
        "удалёнка",
        "remote",
        "remote work",
        "remote job",
        "дистанционно",
        "дистанционная работа",
        "работа из дома",
        "работа на удаленке",
        "работа на удалёнке",
        "из дома",
    },
    "офис": {
        "в офисе",
        "office",
        "office work",
        "onsite",
        "on-site",
    },
    "гибрид": {
        "hybrid",
        "гибридный",
        "смешанный формат",
        "гибридный формат",
    },
    "полная занятость": {
        "full-time",
        "full time",
        "фуллтайм",
        "fulltime",
    },
    "частичная занятость": {
        "part-time",
        "part time",
        "парттайм",
        "parttime",
    },
    "стажировка": {
        "internship",
        "intern",
        "стажёр",
        "стажер",
        "стажировка",
    },
    "без опыта": {
        "junior",
        "entry-level",
        "entry level",
        "entrylevel",
        "начинающий",
        "без опыта",
        "опыт не требуется",
        "без опыта работы",
        "no experience",
    },
    "junior": {
        "джуниор",
        "junior",
        "junior developer",
        "junior designer",
        "начинающий",
        "entry-level",
        "entry level",
    },
    "middle": {
        "mid",
        "middle",
        "мидл",
        "middle developer",
        "middle designer",
    },
    "senior": {
        "сеньор",
        "senior",
        "senior developer",
        "senior designer",
    },
}


# ---------------------------------------------------------------------------
# Text normalization
# ---------------------------------------------------------------------------

def normalize_text(text: str) -> str:
    """
    Normalize arbitrary text for lexical matching.

    The function:
    - converts to lowercase;
    - normalizes ё -> е;
    - preserves +, #, ., / and - because they are useful in technologies
      such as C++, C#, Node.js and UX/UI;
    - collapses whitespace.
    """
    if not text:
        return ""

    text = str(text).lower().replace("ё", "е")

    text = re.sub(
        r"[^\w+#./\- ]+",
        " ",
        text,
        flags=re.UNICODE,
    )

    text = re.sub(r"\s+", " ", text).strip()

    return text


def tokenize(text: str) -> List[str]:
    """
    Split normalized text into meaningful tokens.
    """
    normalized = normalize_text(text)

    return [
        token
        for token in normalized.split()
        if len(token) > 1
    ]


def _stem_russian_word(word: str) -> str:
    """
    Lightweight Russian stemmer.

    This is intentionally conservative. It is not intended to replace
    pymorphy2/mystem. It simply helps with common forms such as:

        дизайнер -> дизайнер
        дизайнера -> дизайнер
        разработчиком -> разработчик
        вакансии -> ваканс

    A proper lemmatizer can be introduced later if necessary.
    """
    endings = (
        "иями",
        "ами",
        "ями",
        "ого",
        "ему",
        "ому",
        "ими",
        "ыми",
        "ее",
        "ие",
        "ые",
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
    """
    Normalize a single term while applying lightweight stemming.
    """
    normalized = normalize_text(term)

    words = normalized.split()

    return " ".join(
        _stem_russian_word(word)
        for word in words
    )


# ---------------------------------------------------------------------------
# Synonym handling
# ---------------------------------------------------------------------------

def _normalized_synonym_map() -> Dict[str, Set[str]]:
    """
    Build normalized synonym map.

    Kept as a function rather than a module-level mutable structure so that
    SYNONYMS remains easy to edit.
    """
    result: Dict[str, Set[str]] = {}

    for key, values in SYNONYMS.items():
        normalized_key = normalize_text(key)

        result.setdefault(normalized_key, set())

        for value in values:
            result[normalized_key].add(normalize_text(value))

    return result


def expand_with_synonyms(term: str) -> List[str]:
    """
    Return the original term and all known synonym variants.
    """
    normalized = normalize_text(term)

    if not normalized:
        return []

    variants: Set[str] = {normalized}

    synonym_map = _normalized_synonym_map()

    for key, values in synonym_map.items():
        if normalized == key:
            variants.add(key)
            variants.update(values)

        elif normalized in values:
            variants.add(key)
            variants.update(values)

    return sorted(variants)


# ---------------------------------------------------------------------------
# Phrase matching
# ---------------------------------------------------------------------------

def _contains_phrase(
    phrase: str,
    text: str,
) -> bool:
    """
    Check whether phrase occurs in text.

    First performs a direct substring check, then checks token-by-token
    with normalization/stemming.
    """
    phrase = normalize_text(phrase)
    text = normalize_text(text)

    if not phrase or not text:
        return False

    if phrase in text:
        return True

    phrase_words = phrase.split()

    if not phrase_words:
        return False

    text_words = text.split()

    phrase_len = len(phrase_words)

    if phrase_len > len(text_words):
        return False

    for index in range(len(text_words) - phrase_len + 1):
        chunk = text_words[index:index + phrase_len]

        if all(
            normalize_term(a) == normalize_term(b)
            for a, b in zip(phrase_words, chunk)
        ):
            return True

    return False


# ---------------------------------------------------------------------------
# Fuzzy matching
# ---------------------------------------------------------------------------

def fuzzy_match(
    needle: str,
    haystack: str,
    threshold: int = DEFAULT_FUZZY_THRESHOLD,
) -> bool:
    """
    Backwards-compatible boolean fuzzy matcher.

    For richer matching use calculate_match_score().
    """
    score = calculate_match_score(
        needle=needle,
        text=haystack,
        threshold=threshold,
    )

    return score > 0


def _fuzzy_word_match(
    needle: str,
    text_words: List[str],
    threshold: int,
) -> float:
    """
    Return best fuzzy similarity for a single-word needle.

    Returns a value from 0 to 1.
    """
    if not needle:
        return 0.0

    if len(needle) < 4:
        return 0.0

    best_ratio = 0.0

    for word in text_words:
        if len(word) < 4:
            continue

        ratio = fuzz.ratio(needle, word) / 100.0

        if ratio > best_ratio:
            best_ratio = ratio

    if best_ratio * 100 >= threshold:
        return best_ratio

    return 0.0


# ---------------------------------------------------------------------------
# Lexical scoring
# ---------------------------------------------------------------------------

def calculate_match_score(
    needle: str,
    text: str,
    threshold: int = DEFAULT_FUZZY_THRESHOLD,
) -> float:
    """
    Calculate lexical similarity between a condition and vacancy text.

    Returns:
        float in range [0, 1]

    Matching priority:
        1. exact phrase;
        2. normalized phrase;
        3. token overlap;
        4. synonym variants;
        5. fuzzy single-word match.

    This is intentionally independent from semantic similarity.
    """
    if not needle or not text:
        return 0.0

    needle_normalized = normalize_text(needle)
    text_normalized = normalize_text(text)

    if not needle_normalized or not text_normalized:
        return 0.0

    # Strongest possible lexical match.
    if needle_normalized in text_normalized:
        return 1.0

    # Check all synonym variants.
    variants = expand_with_synonyms(needle)

    best_score = 0.0

    text_words = text_normalized.split()
    text_stemmed = {
        normalize_term(word)
        for word in text_words
    }

    for variant in variants:
        variant_normalized = normalize_text(variant)

        if not variant_normalized:
            continue

        # Phrase match after stemming.
        if _contains_phrase(
            variant_normalized,
            text_normalized,
        ):
            best_score = max(best_score, 0.98)
            continue

        variant_tokens = [
            normalize_term(token)
            for token in variant_normalized.split()
        ]

        variant_tokens = [
            token
            for token in variant_tokens
            if token
        ]

        if not variant_tokens:
            continue

        # All tokens found.
        if all(token in text_stemmed for token in variant_tokens):
            best_score = max(best_score, 0.95)
            continue

        # Partial token overlap.
        overlap = sum(
            1
            for token in variant_tokens
            if token in text_stemmed
        )

        if overlap:
            overlap_score = overlap / len(variant_tokens)

            # Partial multi-word matches are useful but should not be
            # considered equivalent to a complete phrase.
            best_score = max(
                best_score,
                0.55 + 0.35 * overlap_score,
            )

        # Fuzzy matching is only useful for individual terms.
        if len(variant_tokens) == 1:
            fuzzy_score = _fuzzy_word_match(
                variant_tokens[0],
                text_words,
                threshold,
            )

            best_score = max(
                best_score,
                fuzzy_score,
            )

    return min(best_score, 1.0)


# ---------------------------------------------------------------------------
# Condition matching
# ---------------------------------------------------------------------------

def match_condition(
    condition: str,
    text_lemmas: List[str],
    text_raw: str,
    threshold: int = DEFAULT_FUZZY_THRESHOLD,
) -> bool:
    """
    Backwards-compatible boolean condition matcher.

    A condition is considered matched if its lexical score is high enough.

    text_lemmas is kept in the signature for compatibility with the previous
    implementation. The current matcher derives its own normalized tokens
    from text_raw because this guarantees consistent processing.
    """
    if not condition or not text_raw:
        return False

    score = calculate_match_score(
        needle=condition,
        text=text_raw,
        threshold=threshold,
    )

    return score >= 0.55


# ---------------------------------------------------------------------------
# Condition result
# ---------------------------------------------------------------------------

def _match_condition_details(
    condition: str,
    vacancy_text: str,
    threshold: int,
) -> Dict[str, Any]:
    """
    Return detailed information about one condition.
    """
    score = calculate_match_score(
        needle=condition,
        text=vacancy_text,
        threshold=threshold,
    )

    matched = score >= 0.55

    if score >= 0.98:
        match_type = "exact"

    elif score >= 0.90:
        match_type = "strong"

    elif score >= 0.70:
        match_type = "partial"

    elif score >= 0.55:
        match_type = "fuzzy"

    else:
        match_type = "none"

    return {
        "condition": condition,
        "matched": matched,
        "score": round(score, 4),
        "match_type": match_type,
    }


# ---------------------------------------------------------------------------
# Filter helpers
# ---------------------------------------------------------------------------

def _clean_conditions(
    values: Any,
) -> List[str]:
    """
    Safely normalize filter condition lists.
    """
    if not isinstance(values, list):
        return []

    result = []

    for item in values:
        if not isinstance(item, str):
            continue

        cleaned = item.strip()

        if cleaned:
            result.append(cleaned)

    return result


def _calculate_weighted_score(
    required_results: List[Dict[str, Any]],
    optional_results: List[Dict[str, Any]],
) -> int:
    """
    Calculate overall filter score.

    Required conditions have much higher weight than optional conditions,
    but missing required lexical matches no longer force score to zero.

    This is deliberate because semantic matching will later be able to
    recover cases where exact wording differs.
    """
    required_total = len(required_results)
    optional_total = len(optional_results)

    if required_total == 0 and optional_total == 0:
        return 100

    required_score = (
        sum(item["score"] for item in required_results)
        / required_total
        if required_total
        else 0.0
    )

    optional_score = (
        sum(item["score"] for item in optional_results)
        / optional_total
        if optional_total
        else 0.0
    )

    if required_total and optional_total:
        final_score = (
            required_score * 0.75
            + optional_score * 0.25
        )

    elif required_total:
        final_score = required_score

    else:
        final_score = optional_score

    return int(round(final_score * 100))


def _is_hard_exclusion(
    condition: str,
    vacancy_text: str,
    threshold: int,
) -> bool:
    """
    Check whether an excluded condition is actually present.

    Exclusions use the same lexical matcher, but a relatively conservative
    threshold is used to avoid rejecting a vacancy because of a weak fuzzy
    coincidence.
    """
    score = calculate_match_score(
        needle=condition,
        text=vacancy_text,
        threshold=threshold,
    )

    return score >= 0.70


# ---------------------------------------------------------------------------
# Main filter matching
# ---------------------------------------------------------------------------

def match_filter(
    filter_data: Dict,
    vacancy_text: str,
    threshold: int = DEFAULT_FUZZY_THRESHOLD,
) -> Dict:
    """
    Match a vacancy against a parsed JobMate filter.

    Backwards-compatible result structure:

        {
            "matched": bool,
            "score": int,
            "matched_conditions": [...],
            "missing_conditions": [...],
            "details": {...}
        }

    Additional information:

        details["required_results"]
        details["optional_results"]
        details["excluded_results"]

    Important behavioral change:

    Previous implementation:
        missing required condition -> matched=False, score=0

    New implementation:
        missing lexical condition -> lower score

    Therefore a semantically similar vacancy can later be recovered by
    semantic_matching.py without changing this API.
    """
    if not vacancy_text or not filter_data:
        return {
            "matched": False,
            "score": 0,
            "matched_conditions": [],
            "missing_conditions": [],
            "details": {},
        }

    required = _clean_conditions(
        filter_data.get("required", [])
    )

    optional = _clean_conditions(
        filter_data.get("optional", [])
    )

    excluded = _clean_conditions(
        filter_data.get("excluded", [])
    )

    # ---------------------------------------------------------------
    # Required conditions
    # ---------------------------------------------------------------

    required_results = [
        _match_condition_details(
            condition=item,
            vacancy_text=vacancy_text,
            threshold=threshold,
        )
        for item in required
    ]

    # ---------------------------------------------------------------
    # Optional conditions
    # ---------------------------------------------------------------

    optional_results = [
        _match_condition_details(
            condition=item,
            vacancy_text=vacancy_text,
            threshold=threshold,
        )
        for item in optional
    ]

    # ---------------------------------------------------------------
    # Exclusions
    # ---------------------------------------------------------------

    excluded_results = []

    for item in excluded:
        found = _is_hard_exclusion(
            condition=item,
            vacancy_text=vacancy_text,
            threshold=threshold,
        )

        excluded_results.append(
            {
                "condition": item,
                "matched": found,
                "score": (
                    round(
                        calculate_match_score(
                            needle=item,
                            text=vacancy_text,
                            threshold=threshold,
                        ),
                        4,
                    )
                    if found
                    else 0.0
                ),
            }
        )

    excluded_found = [
        item["condition"]
        for item in excluded_results
        if item["matched"]
    ]

    # ---------------------------------------------------------------
    # Score
    # ---------------------------------------------------------------

    base_score = _calculate_weighted_score(
        required_results=required_results,
        optional_results=optional_results,
    )

    # A hard exclusion always wins.
    if excluded_found:
        score = 0

    else:
        score = base_score

    # ---------------------------------------------------------------
    # Human-readable condition lists
    # ---------------------------------------------------------------

    matched_required = [
        item["condition"]
        for item in required_results
        if item["matched"]
    ]

    missing_required = [
        item["condition"]
        for item in required_results
        if not item["matched"]
    ]

    matched_optional = [
        item["condition"]
        for item in optional_results
        if item["matched"]
    ]

    missing_optional = [
        item["condition"]
        for item in optional_results
        if not item["matched"]
    ]

    matched_conditions = (
        matched_required
        + matched_optional
    )

    missing_conditions = (
        missing_required
        + [
            f"Не совпало: {item}"
            for item in missing_optional
        ]
    )

    if excluded_found:
        missing_conditions.extend(
            [
                f"Исключено: {item}"
                for item in excluded_found
            ]
        )

    # ---------------------------------------------------------------
    # Final matching decision
    # ---------------------------------------------------------------


    if excluded_found:
        matched = False
    elif not required and not optional:
        matched = True
    else:
        matched = score >= threshold


    # ---------------------------------------------------------------
    # Details
    # ---------------------------------------------------------------

    details = {
        "required": required,
        "optional": optional,
        "excluded": excluded,

        "matched_required": matched_required,
        "missing_required": missing_required,

        "matched_optional": matched_optional,
        "missing_optional": missing_optional,

        "excluded_found": excluded_found,

        "required_results": required_results,
        "optional_results": optional_results,
        "excluded_results": excluded_results,

        "required_match_ratio": (
            round(
                len(matched_required) / len(required),
                4,
            )
            if required
            else 1.0
        ),

        "optional_match_ratio": (
            round(
                len(matched_optional) / len(optional),
                4,
            )
            if optional
            else 1.0
        ),

        "base_score": base_score,
        "final_score": score,

        "threshold": threshold,
        "matching_version": "hybrid-lexical-v1",
    }

    logger.debug(
        "Filter matching: score=%s matched=%s required=%s optional=%s excluded=%s",
        score,
        matched,
        matched_required,
        matched_optional,
        excluded_found,
    )

    return {
        "matched": matched,
        "score": score,
        "matched_conditions": matched_conditions,
        "missing_conditions": missing_conditions,
        "details": details,
    }


# ---------------------------------------------------------------------------
# Public compatibility wrapper
# ---------------------------------------------------------------------------

def check_vacancy_against_filter(
    vacancy_text: str,
    filter_data: Dict,
) -> Dict:
    """
    Public compatibility wrapper used by vacancies.py.
    """
    return match_filter(
        filter_data=filter_data,
        vacancy_text=vacancy_text,
    )