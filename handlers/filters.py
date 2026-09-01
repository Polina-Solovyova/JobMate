import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from db import get_user_filters
from filters import (
    create_filter_from_query,
    get_filters_for_user,
    toggle_filter,
    delete_filter_by_id
)
from keyboards import filters_list_keyboard, filter_actions_keyboard, main_menu_keyboard

logger = logging.getLogger(__name__)

# Состояния для создания фильтра
WAITING_FILTER_QUERY = 1

async def my_filters_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список фильтров пользователя."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    filters = await get_filters_for_user(user_id)

    if not filters:
        text = "🔎 Мои фильтры\n\nУ тебя пока нет сохранённых фильтров.\n\nСоздай свой первый поиск, нажав кнопку ниже."
    else:
        text = "🔎 Мои фильтры\n\nВыбери фильтр для управления:"

    await query.edit_message_text(
        text,
        reply_markup=filters_list_keyboard(filters)
    )

async def add_filter_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать создание фильтра — запросить текстовый запрос."""
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "➕ Новый поиск\n\n"
        "Напиши, какую работу ты ищешь.\n\n"
        "Например:\n"
        "UX/UI дизайнер удалённо, без опыта\n\n"
        "Или:\n"
        "Python разработчик, но не джуниор",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel_add_filter")]
        ])
    )
    return WAITING_FILTER_QUERY

async def cancel_add_filter_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменить создание фильтра."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Создание фильтра отменено.",
        reply_markup=main_menu_keyboard()
    )
    return ConversationHandler.END

async def filter_query_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстового запроса для создания фильтра."""
    user_id = update.effective_user.id
    query_text = update.message.text.strip()

    if not query_text:
        await update.message.reply_text("Пожалуйста, введите запрос.")
        return WAITING_FILTER_QUERY

    result = await create_filter_from_query(user_id, query_text)

    if not result["success"]:
        await update.message.reply_text(
            f"❌ Ошибка: {result.get('error', 'Неизвестная ошибка')}\n\n"
            "Попробуй ещё раз.",
            reply_markup=main_menu_keyboard()
        )
        return ConversationHandler.END

    filter_data = result["filter"]
    name = filter_data.get("name", "Без названия")
    required = ", ".join(filter_data.get("required", []))
    optional = ", ".join(filter_data.get("optional", []))
    excluded = ", ".join(filter_data.get("excluded", []))

    text = (
        f"✅ Фильтр создан!\n\n"
        f"📌 {name}\n"
        f"Обязательно: {required if required else '—'}\n"
        f"Желательно: {optional if optional else '—'}\n"
        f"Исключения: {excluded if excluded else '—'}\n\n"
        f"Теперь я буду искать вакансии по этому запросу."
    )

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔎 Мои фильтры", callback_data="my_filters")],
            [InlineKeyboardButton("➕ Добавить ещё", callback_data="add_filter")],
        ])
    )
    return ConversationHandler.END

async def filter_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать детали фильтра."""
    query = update.callback_query
    await query.answer()

    filter_id = query.data.replace("filter_", "")
    user_id = update.effective_user.id
    filters = await get_filters_for_user(user_id)
    filter_item = next((f for f in filters if str(f["_id"]) == filter_id), None)

    if not filter_item:
        await query.edit_message_text("Фильтр не найден.", reply_markup=main_menu_keyboard())
        return

    filter_data = filter_item.get("filter_data", {})
    name = filter_data.get("name", "Без названия")
    required = ", ".join(filter_data.get("required", []))
    optional = ", ".join(filter_data.get("optional", []))
    excluded = ", ".join(filter_data.get("excluded", []))
    is_enabled = filter_item.get("enabled", True)

    status = "🟢 Активен" if is_enabled else "⏸ На паузе"

    text = (
        f"🔎 {name}\n\n"
        f"Статус: {status}\n"
        f"Обязательно: {required if required else '—'}\n"
        f"Желательно: {optional if optional else '—'}\n"
        f"Исключения: {excluded if excluded else '—'}\n"
    )

    await query.edit_message_text(
        text,
        reply_markup=filter_actions_keyboard(filter_id, is_enabled)
    )

async def filter_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка действий с фильтром (toggle, delete)."""
    query = update.callback_query
    await query.answer()

    data = query.data
    parts = data.split("_")
    action = parts[0]
    filter_id = "_".join(parts[1:])  # на случай, если в ID есть подчёркивания

    if action == "toggle":
        # Получаем текущий статус
        user_id = update.effective_user.id
        filters = await get_filters_for_user(user_id)
        filter_item = next((f for f in filters if str(f["_id"]) == filter_id), None)
        if not filter_item:
            await query.edit_message_text("Фильтр не найден.")
            return
        new_enabled = not filter_item.get("enabled", True)
        await toggle_filter(filter_id, new_enabled)
        status_text = "активен" if new_enabled else "на паузе"
        await query.answer(f"Фильтр {status_text}")

        # Обновляем детали
        await filter_detail_callback(update, context)

    elif action == "delete":
        # Подтверждение удаления
        keyboard = [
            [
                InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_delete_{filter_id}"),
                InlineKeyboardButton("❌ Нет", callback_data=f"filter_{filter_id}")
            ]
        ]
        await query.edit_message_text(
            "🗑 Удалить фильтр?\n\n"
            "Это действие нельзя отменить.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif action == "confirm_delete":
        await delete_filter_by_id(filter_id)
        await query.answer("Фильтр удалён")
        # Возвращаемся к списку
        user_id = update.effective_user.id
        filters = await get_filters_for_user(user_id)
        await query.edit_message_text(
            "Фильтр удалён.",
            reply_markup=filters_list_keyboard(filters)
        )