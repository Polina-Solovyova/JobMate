# main.py
import os
import asyncio
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes
)

from config import BOT_TOKEN
from db import get_user_filters
from handlers.start import start_command
from handlers.channels import (
    main_menu_callback,
    my_channels_callback,
    add_channel_callback,
    cancel_add_channel_callback,
    add_channel_input,
    retry_check_callback,
    channel_detail_callback,
    channel_action_callback,
    WAITING_CHANNEL_INPUT
)
from handlers.filters import (
    my_filters_callback,
    add_filter_callback,
    cancel_add_filter_callback,
    filter_query_input,
    filter_detail_callback,
    filter_action_callback,
    WAITING_FILTER_QUERY
)
from keyboards import main_menu_keyboard
from telegram_client import TelegramUserClient
from vacancies import process_post_with_filters
from notifications import send_vacancy_notification
from db import get_user_channel, update_post_vacancy_status

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Переменная для ID владельца (если задан в .env)
OWNER_USER_ID = os.getenv("OWNER_USER_ID")
if OWNER_USER_ID:
    OWNER_USER_ID = int(OWNER_USER_ID)

async def post_processor(user_id: int, channel_id: int, message_id: int, text: str, posted_at):
    """Обработчик нового поста из Telethon."""
    logger.info(f"Новый пост в канале {channel_id}, сообщение {message_id}")

    # Получаем фильтры пользователя
    filters = await get_user_filters(user_id)
    if not filters:
        logger.info(f"Нет фильтров у пользователя {user_id}, пропускаем")
        return

    # Обрабатываем пост через vacancies + matching
    results = process_post_with_filters(text, filters)
    if not results:
        logger.info(f"Пост не является вакансией или не прошёл фильтры")
        return

    # Для каждого совпавшего фильтра отправляем уведомление
    for res in results:
        match_result = res["match_result"]
        if match_result["matched"] and match_result["score"] >= 75:
            vacancy_data = res["vacancy_data"]
            filter_name = res["filter_name"]
            score = match_result["score"]
            matched_conditions = match_result["matched_conditions"]

            # Получаем информацию о канале для ссылки
            channel = await get_user_channel(user_id, channel_id)
            if channel:
                channel_username = channel.get("username")
                # Формируем ссылку на пост
                if channel_username:
                    username_clean = channel_username.lstrip('@')
                    post_link = f"https://t.me/{username_clean}/{message_id}"
                else:
                    # Если нет username, используем ID
                    channel_id_str = str(channel_id).replace('-100', '')
                    post_link = f"https://t.me/c/{channel_id_str}/{message_id}"
            else:
                post_link = None
                channel_username = None

            # Отправляем уведомление
            await send_vacancy_notification(
                bot=application.bot,
                user_id=user_id,
                vacancy_data=vacancy_data,
                filter_name=filter_name,
                score=score,
                matched_conditions=matched_conditions,
                post_link=post_link,
                channel_username=channel_username
            )

            # Обновляем статус поста в БД
            await update_post_vacancy_status(
                user_id, channel_id, message_id,
                is_vacancy=True,
                vacancy_data=vacancy_data
            )

# Глобальная ссылка на приложение для доступа в колбэках
application = None

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")

def main():
    global application
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_error_handler(error_handler)

    # --- Добавляем хендлеры ---
    # Старт
    application.add_handler(CommandHandler("start", start_command))

    # Callback'и главного меню
    application.add_handler(CallbackQueryHandler(main_menu_callback, pattern="^main_menu$"))
    application.add_handler(CallbackQueryHandler(my_channels_callback, pattern="^my_channels$"))
    application.add_handler(CallbackQueryHandler(my_filters_callback, pattern="^my_filters$"))

    # --- Каналы ---
    # Добавление канала (ConversationHandler)
    add_channel_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_channel_callback, pattern="^add_channel$")],
        states={
            WAITING_CHANNEL_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_channel_input)
            ]
        },
        fallbacks=[
            CallbackQueryHandler(cancel_add_channel_callback, pattern="^cancel_add_channel$"),
            CommandHandler("start", start_command)
        ],
        allow_reentry=True
    )
    application.add_handler(add_channel_conv)

    # Действия с каналами
    application.add_handler(CallbackQueryHandler(retry_check_callback, pattern="^retry_check_"))
    application.add_handler(CallbackQueryHandler(channel_detail_callback, pattern="^channel_"))
    application.add_handler(CallbackQueryHandler(channel_action_callback, pattern="^(toggle|delete|confirm_delete|vacancies|notify)_"))

    # --- Фильтры ---
    # Добавление фильтра (ConversationHandler)
    add_filter_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_filter_callback, pattern="^add_filter$")],
        states={
            WAITING_FILTER_QUERY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, filter_query_input)
            ]
        },
        fallbacks=[
            CallbackQueryHandler(cancel_add_filter_callback, pattern="^cancel_add_filter$"),
            CommandHandler("start", start_command)
        ],
        allow_reentry=True
    )
    application.add_handler(add_filter_conv)

    # Действия с фильтрами
    application.add_handler(CallbackQueryHandler(filter_detail_callback, pattern="^filter_"))
    application.add_handler(CallbackQueryHandler(filter_action_callback, pattern="^(toggle|delete|confirm_delete)_filter_"))

    # --- Запуск Telethon клиента ---
    if OWNER_USER_ID:
        logger.info(f"Запуск Telethon клиента для пользователя {OWNER_USER_ID}")
        client = TelegramUserClient(OWNER_USER_ID)

        # Запускаем клиент и опрос в фоне
        async def init_client():
            await client.start()
            # Устанавливаем колбэк для новых постов
            client.set_new_post_callback(post_processor)
            await client.start_polling()
            # Сохраняем клиент в bot_data для доступа из хендлеров
            application.bot_data["telegram_client"] = client
            logger.info("Telethon клиент запущен и опрос каналов активен")

        asyncio.create_task(init_client())
    else:
        logger.warning("OWNER_USER_ID не задан. Telethon клиент не запущен. Бот будет работать только с UI.")

    # Запуск бота
    logger.info("Бот запущен...")
    application.run_polling()

if __name__ == "__main__":
    import platform
    if platform.system() == "Windows":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    main()