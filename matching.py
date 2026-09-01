import re
from typing import Dict, List, Optional, Tuple
import logging
from rapidfuzz import fuzz, process
import pymorphy2

logger = logging.getLogger(__name__)

# Инициализируем морфологический анализатор для русского языка
morph = pymorphy2.MorphAnalyzer()

# Расширенный словарь синонимов (можно дополнять)
SYNONYMS = {
    # Профессии
    "разработчик": ["программист", "developer", "кодер"],
    "дизайнер": ["designer", "ux/ui", "продуктовый дизайнер"],
    
    # Технологии
    "figma": ["фигма"],
    "photoshop": ["фотошоп"],
    
    # Условия работы
    "удалённо": ["remote", "дистанционно", "удаленка", "удалёнка"],
    "офис": ["в офисе", "офисная работа"],
    "гибрид": ["hybrid", "смешанный"],
    "полная занятость": ["full-time", "фуллтайм"],
    "частичная занятость": ["part-time", "парттайм"],
    "стажировка": ["internship", "intern"],
    "без опыта": ["junior", "начинающий", "entry-level", "junior-", "стажёр"],
    "опыт от": ["от года", "опыт работы"],
}

# Кэш для лемматизированных слов
_lemmatized_cache = {}

def lemmatize_word(word: str) -> str:
    """Лемматизация одного слова."""
    if word in _lemmatized_cache:
        return _lemmatized_cache[word]
    parsed = morph.parse(word)[0]
    normal_form = parsed.normal_form
    _lemmatized_cache[word] = normal_form
    return normal_form

def tokenize_and_lemmatize(text: str) -> List[str]:
    """Разбивает текст на слова, удаляет стоп-слова, лемматизирует."""
    # Простая токенизация по словам
    words = re.findall(r'[а-яёa-z]+', text.lower())
    # Лемматизация
    lemmas = [lemmatize_word(w) for w in words if len(w) > 1]
    return lemmas

def expand_with_synonyms(term: str) -> List[str]:
    """Возвращает список синонимов для термина (включая сам термин)."""
    term_lower = term.lower()
    # Проверяем, есть ли синонимы (как ключ или как значение)
    synonyms = set()
    for key, values in SYNONYMS.items():
        if term_lower == key:
            synonyms.update(values)
        elif term_lower in values:
            synonyms.add(key)
            synonyms.update(values)
    # Добавляем сам термин
    synonyms.add(term_lower)
    return list(synonyms)

def fuzzy_match(needle: str, haystack: str, threshold: int = 85) -> bool:
    """
    Проверяет, содержится ли needle в haystack с учётом fuzzy-сравнения.
    Используется частичное отношение (если needle длиннее, сравниваем части).
    """
    if not needle or not haystack:
        return False
    # Если простое вхождение уже есть
    if needle in haystack:
        return True
    # Проверяем по отдельным словам
    needle_words = needle.split()
    haystack_words = haystack.split()
    if not needle_words or not haystack_words:
        return False
    # Для каждого слова из needle ищем лучшее совпадение в haystack
    for nw in needle_words:
        # Ищем самое похожее слово
        best = process.extractOne(nw, haystack_words, scorer=fuzz.ratio)
        if best and best[1] >= threshold:
            continue
        else:
            return False
    return True

def match_condition(condition: str, text_lemmas: List[str], text_raw: str, threshold: int = 85) -> bool:
    """
    Проверяет, выполняется ли условие (один термин) для текста.
    Учитывает синонимы и fuzzy.
    """
    synonyms = expand_with_synonyms(condition)
    for syn in synonyms:
        # Проверяем точное совпадение лемм
        syn_lemmas = tokenize_and_lemmatize(syn)
        if all(sl in text_lemmas for sl in syn_lemmas):
            return True
        # Проверяем fuzzy по сырому тексту
        if fuzzy_match(syn, text_raw, threshold):
            return True
    return False

def match_filter(
    filter_data: Dict,
    vacancy_text: str,
    threshold: int = 85
) -> Dict:
    """
    Сопоставляет фильтр с текстом вакансии.
    Возвращает:
    {
        "matched": bool,
        "score": int (0-100),
        "matched_conditions": List[str],
        "missing_conditions": List[str],
        "details": Dict  # для отладки
    }
    """
    if not vacancy_text or not filter_data:
        return {
            "matched": False,
            "score": 0,
            "matched_conditions": [],
            "missing_conditions": [],
            "details": {}
        }

    # Подготавливаем текст: леммы и сырой текст
    text_lemmas = tokenize_and_lemmatize(vacancy_text)
    text_raw = vacancy_text.lower()

    required = filter_data.get("required", [])
    optional = filter_data.get("optional", [])
    excluded = filter_data.get("excluded", [])

    matched_required = []
    missing_required = []
    matched_optional = []
    excluded_found = []

    # Проверяем обязательные (AND)
    for req in required:
        if match_condition(req, text_lemmas, text_raw, threshold):
            matched_required.append(req)
        else:
            missing_required.append(req)

    # Если не все обязательные выполнены → не подходит
    if missing_required:
        return {
            "matched": False,
            "score": 0,
            "matched_conditions": matched_required,
            "missing_conditions": missing_required,
            "details": {"required": required, "optional": optional, "excluded": excluded}
        }

    # Проверяем исключения (NOT)
    for exc in excluded:
        if match_condition(exc, text_lemmas, text_raw, threshold):
            excluded_found.append(exc)

    if excluded_found:
        return {
            "matched": False,
            "score": 0,
            "matched_conditions": matched_required,
            "missing_conditions": [f"Исключено: {', '.join(excluded_found)}"],
            "details": {"excluded_found": excluded_found}
        }

    # Проверяем желательные (OR)
    for opt in optional:
        if match_condition(opt, text_lemmas, text_raw, threshold):
            matched_optional.append(opt)

    # Вычисляем score
    total_conditions = len(required) + len(optional)
    matched_conditions = matched_required + matched_optional
    score = int((len(matched_conditions) / total_conditions) * 100) if total_conditions > 0 else 0

    return {
        "matched": True,
        "score": score,
        "matched_conditions": matched_conditions,
        "missing_conditions": [f"Не совпало: {', '.join(set(optional) - set(matched_optional))}"],
        "details": {
            "required": required,
            "optional": optional,
            "matched_required": matched_required,
            "matched_optional": matched_optional,
            "excluded": excluded,
            "excluded_found": excluded_found
        }
    }

# Упрощённая функция для интеграции с основным кодом
def check_vacancy_against_filter(vacancy_text: str, filter_data: Dict) -> Dict:
    """
    Упрощённая обёртка для проверки.
    """
    return match_filter(filter_data, vacancy_text)