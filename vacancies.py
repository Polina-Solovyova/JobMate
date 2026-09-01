# vacancies.py
import re
from typing import Optional, Dict, List, Tuple, Any

# Импортируем функцию сопоставления из matching
from matching import check_vacancy_against_filter

# Список ключевых слов, указывающих на то, что пост — вакансия
VACANCY_INDICATORS = [
    "вакансия", "вакансии", "вакансию", "ищем", "требуется", "требуются",
    "на работу", "работа", "работаем", "сотрудник", "специалист",
    "оффер", "предложение работы", "в команду", "команда",
    "открыта вакансия", "открыты вакансии", "hire", "hiring",
    "job", "vacancy", "position", "opportunity"
]

# Стоп-слова, которые могут свидетельствовать о том, что пост не вакансия
NOT_VACANCY_INDICATORS = [
    "реклама", "новости", "дайджест", "подборка", "анонс",
    "мероприятие", "вебинар", "конференция", "скидка", "акция"
]

def is_vacancy(text: str) -> bool:
    """
    Определяет, является ли текст поста вакансией.
    Использует простой подсчёт ключевых слов.
    """
    if not text or len(text.strip()) < 10:
        return False

    text_lower = text.lower()

    # Проверяем негативные индикаторы
    negative_count = sum(1 for word in NOT_VACANCY_INDICATORS if word in text_lower)
    if negative_count >= 2:
        return False

    # Проверяем позитивные индикаторы
    positive_count = sum(1 for word in VACANCY_INDICATORS if word in text_lower)

    # Если найдено хотя бы одно позитивное слово и не слишком много негативных
    return positive_count >= 1


def extract_vacancy(text: str) -> Dict[str, any]:
    """
    Извлекает структурированные данные из текста поста.
    Возвращает словарь с полями:
        - title: должность
        - company: компания
        - salary: зарплата (строка)
        - location: локация (город, удалённо)
        - experience: требования к опыту
        - description: полный текст (очищенный)
        - contacts: контакты (если есть)
        - skills: список навыков (если удаётся выделить)
        - raw_text: исходный текст
    """
    result = {
        "title": None,
        "company": None,
        "salary": None,
        "location": None,
        "experience": None,
        "description": text.strip(),
        "contacts": None,
        "skills": [],
        "raw_text": text
    }

    # Простые паттерны для извлечения зарплаты
    salary_patterns = [
        r"зп[:\s]*([\d\s]+)[\s]*(?:руб|₽|usd|eur|€|\$)?",
        r"зарплата[:\s]*([\d\s]+)[\s]*(?:руб|₽|usd|eur|€|\$)?",
        r"salary[:\s]*([\d\s]+)",
        r"от\s*([\d\s]+)[\s]*(?:руб|₽|usd|eur|€|\$)?",
        r"до\s*([\d\s]+)[\s]*(?:руб|₽|usd|eur|€|\$)?",
        r"([\d\s]+)\s*-\s*([\d\s]+)\s*(?:руб|₽|usd|eur|€|\$)"
    ]
    for pattern in salary_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["salary"] = match.group(0).strip()
            break

    # Простой поиск контактов (email, телефон)
    email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    phone_pattern = r"\+?\d[\d\-\(\) ]{8,}\d"
    contacts = []
    emails = re.findall(email_pattern, text)
    if emails:
        contacts.extend(emails)
    phones = re.findall(phone_pattern, text)
    if phones:
        contacts.extend(phones)
    if contacts:
        result["contacts"] = ", ".join(contacts)

    # Попытка выделить навыки (технологии, инструменты)
    common_skills = ["python", "java", "javascript", "react", "vue", "angular", "sql", "mongodb",
                     "docker", "kubernetes", "linux", "git", "design", "figma", "photoshop",
                     "project management", "agile", "scrum", "marketing", "seo", "google ads"]
    skills_found = []
    for skill in common_skills:
        if skill in text.lower():
            skills_found.append(skill)
    result["skills"] = skills_found

    # Попытка извлечь локацию
    location_keywords = ["в городе", "в офисе", "remote", "удалённо", "гибрид", "hybrid"]
    for loc in location_keywords:
        if loc in text.lower():
            result["location"] = loc
            break

    # Попытка извлечь должность (обычно первая строка или строка с "вакансия", "ищем")
    lines = text.split('\n')
    for line in lines[:3]:
        line = line.strip()
        if len(line) < 60 and any(kw in line.lower() for kw in ["вакансия", "ищем", "требуется", "позиция"]):
            result["title"] = line
            break
    if not result["title"] and lines:
        result["title"] = lines[0][:100]

    return result


def normalize_vacancy(vacancy_data: Dict) -> Dict:
    """
    Нормализует данные вакансии: убирает лишние пробелы, приводит к единому формату.
    """
    normalized = vacancy_data.copy()
    for key, value in normalized.items():
        if isinstance(value, str):
            value = re.sub(r'\s+', ' ', value).strip()
            normalized[key] = value
        elif isinstance(value, list):
            normalized[key] = sorted(set(value))
    return normalized


def process_post(post_text: str) -> Optional[Dict]:
    """
    Основная функция: принимает текст поста, определяет, вакансия ли это,
    и если да, возвращает структурированные данные.
    Если не вакансия, возвращает None.
    """
    if not is_vacancy(post_text):
        return None
    raw_data = extract_vacancy(post_text)
    return normalize_vacancy(raw_data)


def process_post_with_filters(
    post_text: str,
    filters: List[Dict]
) -> List[Dict]:
    """
    Принимает текст поста и список фильтров пользователя.
    Определяет, является ли пост вакансией, извлекает данные,
    и для каждого фильтра выполняет сопоставление.
    Возвращает список результатов для каждого фильтра:
        [
            {
                "filter_id": str,
                "filter_name": str,
                "match_result": {
                    "matched": bool,
                    "score": int,
                    "matched_conditions": List[str],
                    "missing_conditions": List[str],
                    "details": Dict
                },
                "vacancy_data": Dict  # извлечённые данные вакансии (если пост — вакансия)
            },
            ...
        ]
    Если пост не является вакансией, возвращает пустой список.
    """
    # Сначала проверяем, является ли пост вакансией
    vacancy_data = process_post(post_text)
    if not vacancy_data:
        return []  # не вакансия, ничего не проверяем

    results = []
    for filter_item in filters:
        filter_data = filter_item.get("filter_data", {})
        filter_id = str(filter_item.get("_id", "unknown"))
        filter_name = filter_data.get("name", "Без названия")

        # Выполняем сопоставление
        match_result = check_vacancy_against_filter(
            vacancy_text=post_text,  # можно передавать весь текст
            filter_data=filter_data
        )
        results.append({
            "filter_id": filter_id,
            "filter_name": filter_name,
            "match_result": match_result,
            "vacancy_data": vacancy_data
        })

    return results