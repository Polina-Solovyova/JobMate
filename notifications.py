import logging
from typing import Dict, Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)

def format_vacancy_card(
    vacancy_data: Dict,
    filter_name: str,
    score: int,
    matched_conditions: list,
    post_link: Optional[str] = None,
    channel_username: Optional[str] = None
) -> tuple:
    """
    Формирует текст и клавиатуру для карточки вакансии.
    Возвращает (text, keyboard).
    """
    title = vacancy_data.get("title", "Вакансия")
    company = vacancy_data.get("company", "")
    salary = vacancy_data.get("salary", "")
    location = vacancy_data.get("location", "")
    experience = vacancy_data.get("experience", "")
    contacts = vacancy_data.get("contacts", "")
    skills = vacancy_data.get("skills", [])
    description = vacancy_data.get("description", "")[:500]  # обрезаем

    # Формируем текст
    lines = []
    lines.append(f"🔔 **{title}**")
    if company:
        lines.append(f"🏢 **Компания:** {company}")
    if salary:
        lines.append(f"💰 **Зарплата:** {salary}")
    if location:
        lines.append(f"📍 **Локация:** {location}")
    if experience:
        lines.append(f"💼 **Опыт:** {experience}")
    if skills:
        lines.append(f"🛠 **Навыки:** {', '.join(skills[:5])}")
    if contacts:
        lines.append(f"📞 **Контакты:** {contacts}")
    if description:
        lines.append(f"\n{description}...")
    if matched_conditions:
        lines.append(f"\n✅ **Совпало:** {', '.join(matched_conditions[:5])}")
    lines.append(f"\n🎯 **Релевантность:** {score}%")
    lines.append(f"📢 **Источник:** {filter_name}")

    text = "\n".join(lines)

    # Клавиатура
    keyboard = []
    if post_link:
        keyboard.append(InlineKeyboardButton("📄 Открыть пост", url=post_link))
    if channel_username:
        channel_url = f"https://t.me/{channel_username.lstrip('@')}"
        keyboard.append(InlineKeyboardButton("📢 Перейти в канал", url=channel_url))
    keyboard.append(InlineKeyboardButton("👍 Полезно", callback_data="feedback_positive"))
    keyboard.append(InlineKeyboardButton("👎 Не подходит", callback_data="feedback_negative"))

    return text, InlineKeyboardMarkup([keyboard])


async def send_vacancy_notification(
    bot,
    user_id: int,
    vacancy_data: Dict,
    filter_name: str,
    score: int,
    matched_conditions: list,
    post_link: Optional[str] = None,
    channel_username: Optional[str] = None
):
    """
    Отправляет пользователю уведомление о вакансии.
    """
    text, keyboard = format_vacancy_card(
        vacancy_data,
        filter_name,
        score,
        matched_conditions,
        post_link,
        channel_username
    )
    try:
        await bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode="Markdown",
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        logger.info(f"Уведомление отправлено пользователю {user_id} по фильтру '{filter_name}' (score: {score})")
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления пользователю {user_id}: {e}")