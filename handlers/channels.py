import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from db import get_user_channels
from channels import add_channel_for_user, get_channels_list, toggle_channel, delete_channel
from keyboards import (
    main_menu_keyboard,
    channels_list_keyboard,
    channel_actions_keyboard,
    confirm_add_channel_keyboard,
)
from telegram_client import TelegramUserClient

logger = logging.getLogger(__name__)

# Состояния для добавления канала
WAITING_CHANNEL_INPUT = 1

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start — показать главное меню."""
    user = update.effective_user
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        "Я — твой персональный помощник по поиску вакансий в Telegram.\n"
        "Я отслеживаю выбранные тобой каналы и присылаю только подходящие вакансии.\n\n"
        "Используй кнопки ниже для управления:",
        reply_markup=main_menu_keyboard()
    )
    return ConversationHandler.END

async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопки «Назад» или вызова главного меню."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Главное меню:",
        reply_markup=main_menu_keyboard()
    )

async def my_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список каналов пользователя."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    channels = await get_channels_list(user_id)

    if not channels:
        text = "📢 Мои каналы\n\nПока нет добавленных источников.\n\nДобавь Telegram-каналы, на которые ты подписан, и я буду отслеживать новые вакансии."
    else:
        text = "📢 Мои каналы\n\nВыбери канал для управления:"

    await query.edit_message_text(
        text,
        reply_markup=channels_list_keyboard(channels)
    )

async def add_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать процесс добавления канала — запросить ввод."""
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "Отправь ссылку или username канала.\n\n"
        "Например:\n"
        "@design_jobs\n"
        "или\n"
        "https://t.me/design_jobs",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel_add_channel")]
        ])
    )
    return WAITING_CHANNEL_INPUT

async def cancel_add_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменить добавление канала."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Добавление канала отменено.",
        reply_markup=main_menu_keyboard()
    )
    return ConversationHandler.END

async def add_channel_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка введённого пользователем идентификатора канала."""
    user_id = update.effective_user.id
    input_text = update.message.text.strip()

    # Получаем клиент из bot_data
    client: TelegramUserClient = context.bot_data.get("telegram_client")
    if not client:
        await update.message.reply_text("Ошибка: клиент Telegram не инициализирован.")
        return ConversationHandler.END

    # Проверяем доступ
    result = await add_channel_for_user(user_id, client, input_text)

    if not result["success"]:
        error_msg = result["message"]
        # Если не подписан, предлагаем проверить снова
        if result.get("error") == "not_subscribed":
            keyboard = [
                [InlineKeyboardButton("🔄 Проверить снова", callback_data=f"retry_check_{input_text}")],
                [InlineKeyboardButton("❌ Отмена", callback_data="cancel_add_channel")]
            ]
            await update.message.reply_text(
                f"📢 Канал не найден среди доступных твоему Telegram-аккаунту.\n\n"
                f"Подпишись на канал в Telegram, затем вернись сюда.\n\n"
                f"{error_msg}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        elif result.get("error") == "already_added":
            channel = result["channel"]
            await update.message.reply_text(
                f"📢 {channel['title']}\n\nЭтот канал уже добавлен.\n\n"
                f"Перейди в [настройки](tg://callback?data=channel_{channel['channel_id']}) для управления.",
                reply_markup=main_menu_keyboard(),
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                f"❌ {error_msg}",
                reply_markup=main_menu_keyboard()
            )
        return ConversationHandler.END

    # Успешно добавлен
    channel = result["channel"]
    text = (
        f"✅ Канал добавлен\n\n"
        f"📢 {channel['title']}\n"
        f"@{channel['username'] or 'без username'}\n\n"
        f"Теперь я буду отслеживать новые публикации в этом канале."
    )
    keyboard = [
        [InlineKeyboardButton("📢 Мои каналы", callback_data="my_channels")],
        [InlineKeyboardButton("➕ Добавить ещё", callback_data="add_channel")],
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

async def retry_check_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Повторная проверка канала (пользователь подписался)."""
    query = update.callback_query
    await query.answer()

    # Извлекаем identifier из callback_data (формат: retry_check_{identifier})
    identifier = query.data.replace("retry_check_", "")
    user_id = update.effective_user.id
    client: TelegramUserClient = context.bot_data.get("telegram_client")

    if not client:
        await query.edit_message_text("Ошибка: клиент не инициализирован.")
        return

    result = await add_channel_for_user(user_id, client, identifier)

    if not result["success"]:
        # Снова не подписан или другая ошибка
        await query.edit_message_text(
            "❌ Канал всё ещё недоступен. Убедись, что ты подписан на него, и попробуй позже.",
            reply_markup=main_menu_keyboard()
        )
        return

    channel = result["channel"]
    await query.edit_message_text(
        f"✅ Канал добавлен!\n\n"
        f"📢 {channel['title']}\n"
        f"@{channel['username'] or 'без username'}\n\n"
        f"Теперь я буду отслеживать новые публикации в этом канале.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Мои каналы", callback_data="my_channels")],
            [InlineKeyboardButton("➕ Добавить ещё", callback_data="add_channel")],
        ])
    )

async def channel_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка действий с каналом (пауза, возобновление, удаление, просмотр)."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    data = query.data
    parts = data.split("_")
    action = parts[0]  # toggle, delete, vacancies, notify
    channel_id = int(parts[1])

    if action == "toggle":
        # Определяем текущий статус
        channels = await get_user_channels(user_id)
        channel = next((ch for ch in channels if ch["channel_id"] == channel_id), None)
        if not channel:
            await query.edit_message_text("Канал не найден.")
            return
        new_enabled = not channel.get("enabled", True)
        await toggle_channel(user_id, channel_id, new_enabled)
        status_text = "активен" if new_enabled else "на паузе"
        await query.answer(f"Статус изменён: {status_text}")

        # Обновляем сообщение с кнопками
        await show_channel_actions(query, user_id, channel_id)

    elif action == "delete":
        # Запрос подтверждения удаления
        keyboard = [
            [
                InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_delete_{channel_id}"),
                InlineKeyboardButton("❌ Нет", callback_data=f"channel_{channel_id}")
            ]
        ]
        await query.edit_message_text(
            "🗑 Удалить канал?\n\n"
            "Это действие удалит канал из твоего списка, но не из Telegram.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif action == "confirm_delete":
        await delete_channel(user_id, channel_id)
        await query.answer("Канал удалён")
        # Возвращаемся к списку каналов
        channels = await get_channels_list(user_id)
        await query.edit_message_text(
            "📢 Мои каналы\n\nКанал удалён.",
            reply_markup=channels_list_keyboard(channels)
        )

    elif action == "vacancies":
        # Пока заглушка — позже реализуем
        await query.edit_message_text(
            "🔎 Вакансии из этого канала (функция в разработке)",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data=f"channel_{channel_id}")]
            ])
        )

    elif action == "notify":
        # Заглушка для настроек уведомлений
        await query.edit_message_text(
            "🔔 Настройки уведомлений (функция в разработке)",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data=f"channel_{channel_id}")]
            ])
        )

async def show_channel_actions(query, user_id: int, channel_id: int):
    """Отобразить страницу управления каналом."""
    channels = await get_user_channels(user_id)
    channel = next((ch for ch in channels if ch["channel_id"] == channel_id), None)
    if not channel:
        await query.edit_message_text("Канал не найден.")
        return

    status = "🟢 Активен" if channel.get("enabled", True) else "⏸ На паузе"
    text = (
        f"📢 {channel['title']}\n"
        f"@{channel.get('username', 'без username')}\n\n"
        f"Статус: {status}\n"
        f"Добавлен: {channel.get('added_at', '').strftime('%d.%m.%Y') if channel.get('added_at') else 'неизвестно'}\n"
        # Можно добавить количество вакансий позже
    )

    await query.edit_message_text(
        text,
        reply_markup=channel_actions_keyboard(channel_id, channel.get("enabled", True))
    )

async def channel_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать детали канала при клике на него из списка."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    # callback_data: channel_{channel_id}
    channel_id = int(query.data.split("_")[1])
    await show_channel_actions(query, user_id, channel_id)

# Обработчик для кнопки "Назад" из состояния добавления
async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Главное меню:",
        reply_markup=main_menu_keyboard()
    )
    return ConversationHandler.END