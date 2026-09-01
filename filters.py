import re
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging

from db import add_filter as db_add_filter, get_user_filters, update_filter, delete_filter

logger = logging.getLogger(__name__)

# Модель фильтра:
# {
#   "_id": ObjectId,
#   "user_id": int,
#   "filter_data": {
#       "name": str,                  # название, сгенерированное из запроса
#       "query": str,                 # исходный запрос пользователя
#       "keywords": List[str],        # ключевые слова (из запроса)
#       "required": List[str],        # обязательные условия (AND)
#       "optional": List[str],        # желательные условия (OR)
#       "excluded": List[str],        # исключения (NOT)
#       "location": Optional[str],    # локация (город, удалёнка и т.п.)
#       "experience": Optional[str],  # опыт (junior, middle, senior)
#       "salary_min": Optional[int],
#       "salary_max": Optional[int],
#   },
#   "enabled": bool,
#   "created_at": datetime,
#   "updated_at": datetime
# }


def parse_query_to_filter(query: str) -> Dict[str, Any]:
    """
    Преобразует текстовый запрос пользователя в структурированный фильтр.
    Пример:
        "UX/UI дизайнер удалённо, без опыта, но не графический дизайнер"
    -> {
        "name": "UX/UI дизайнер",
        "keywords": ["ux/ui дизайнер", "удалённо", "без опыта"],
        "required": ["ux/ui дизайнер", "удалённо"],
        "optional": ["без опыта"],
        "excluded": ["графический дизайнер"]
    }
    """
    # Очищаем запрос
    query = query.strip()
    if not query:
        return {"error": "Пустой запрос"}

    # Разбиваем на части по разделителям: запятая, точка с запятой, "и", "или", "но", "не"
    # Сначала попробуем выделить исключения (после "не", "без", "но не")
    excluded = []
    main_parts = []
    
    # Ищем паттерны исключений: "не <что-то>", "без <что-то>", "но не <что-то>"
    exclusion_pattern = r'(?:не|без|но не|кроме)\s+([^,;.]+)'
    for match in re.finditer(exclusion_pattern, query, re.IGNORECASE):
        excluded.append(match.group(1).strip())
        # Удаляем найденное из основного запроса
        query = query.replace(match.group(0), '')

    # Теперь разделяем оставшийся запрос на части (по запятым, "и", "или")
    # Заменяем " и " и " или " на запятые для единообразия
    query = re.sub(r'\s+и\s+', ',', query, flags=re.IGNORECASE)
    query = re.sub(r'\s+или\s+', ',', query, flags=re.IGNORECASE)
    parts = [p.strip() for p in query.split(',') if p.strip()]

    # Определяем, что является обязательным (первая часть обычно главная)
    required = []
    optional = []
    if parts:
        # Первая часть — главная (обязательная)
        required.append(parts[0])
        # Остальные — желательные, но если они содержат ключевые слова локации/опыта, то тоже обязательные
        for part in parts[1:]:
            if any(kw in part.lower() for kw in ['удалён', 'remote', 'офис', 'гибрид', 'junior', 'middle', 'senior', 'опыт']):
                required.append(part)
            else:
                optional.append(part)

    # Извлекаем локацию и опыт
    location = None
    experience = None
    for part in required + optional:
        if any(kw in part.lower() for kw in ['удалён', 'remote', 'офис', 'гибрид']):
            location = part
        if any(kw in part.lower() for kw in ['junior', 'middle', 'senior', 'опыт', 'без опыта', 'стажёр']):
            experience = part

    # Генерируем название (берём первую часть, обрезаем до 50 символов)
    name = required[0][:50] if required else "Поиск"

    return {
        "name": name,
        "query": query.strip(),  # исходный (очищенный)
        "keywords": parts,
        "required": required,
        "optional": optional,
        "excluded": excluded,
        "location": location,
        "experience": experience,
        "salary_min": None,
        "salary_max": None,
    }


async def create_filter_from_query(user_id: int, query: str) -> Dict:
    """
    Создаёт фильтр из текстового запроса и сохраняет в БД.
    Возвращает созданный фильтр или ошибку.
    """
    filter_data = parse_query_to_filter(query)
    if "error" in filter_data:
        return {"success": False, "error": filter_data["error"]}

    # Сохраняем в БД
    await db_add_filter(user_id, filter_data)
    return {"success": True, "filter": filter_data}


async def get_filters_for_user(user_id: int) -> List[Dict]:
    """
    Возвращает все фильтры пользователя (из БД).
    """
    return await get_user_filters(user_id)


async def toggle_filter(filter_id: str, enabled: bool) -> bool:
    """
    Включает/выключает фильтр.
    """
    await update_filter(filter_id, {"enabled": enabled})
    return True


async def delete_filter_by_id(filter_id: str) -> bool:
    """
    Удаляет фильтр.
    """
    await delete_filter(filter_id)
    return True


def filter_matches_vacancy(filter_data: Dict, vacancy_data: Dict) -> Dict:
    """
    Проверяет, соответствует ли вакансия фильтру (базовая проверка).
    Возвращает:
    {
        "matched": bool,
        "score": int,  # 0-100
        "matched_conditions": List[str],
        "missing_conditions": List[str]
    }
    В будущем это будет заменено на более сложный matching из matching.py.
    Пока делаем простую проверку на наличие ключевых слов.
    """
    if not vacancy_data or not filter_data:
        return {"matched": False, "score": 0, "matched_conditions": [], "missing_conditions": []}

    text = vacancy_data.get("description", "").lower()
    title = vacancy_data.get("title", "").lower()
    full_text = (text + " " + title).lower()

    required = [kw.lower() for kw in filter_data.get("required", [])]
    optional = [kw.lower() for kw in filter_data.get("optional", [])]
    excluded = [kw.lower() for kw in filter_data.get("excluded", [])]

    matched_required = []
    missing_required = []

    # Проверяем обязательные условия (AND)
    for req in required:
        if req in full_text:
            matched_required.append(req)
        else:
            missing_required.append(req)

    # Если не все обязательные выполнены — не подходит
    if missing_required:
        return {
            "matched": False,
            "score": 0,
            "matched_conditions": matched_required,
            "missing_conditions": missing_required
        }

    # Проверяем исключения (NOT)
    for exc in excluded:
        if exc in full_text:
            return {
                "matched": False,
                "score": 0,
                "matched_conditions": matched_required,
                "missing_conditions": [f"Исключено: {exc}"]
            }

    # Проверяем желательные условия (OR) — считаем, сколько совпало
    matched_optional = []
    for opt in optional:
        if opt in full_text:
            matched_optional.append(opt)

    # Считаем score: 50% за обязательные (уже выполнены) + до 50% за желательные
    required_score = 50
    optional_score = 0
    if optional:
        optional_score = int((len(matched_optional) / len(optional)) * 50)
    total_score = required_score + optional_score

    return {
        "matched": True,
        "score": total_score,
        "matched_conditions": matched_required + matched_optional,
        "missing_conditions": missing_required + [f"Не совпало желательных: {len(optional) - len(matched_optional)}"]
    }