import asyncio
import logging
import platform

from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from config import BOT_TOKEN

from db import (
    get_user_channel,
    get_user_filters,
    update_post_vacancy_status,
)

from handlers.start import start_command

from handlers.channels import (
    main_menu_callback,
    my_channels_callback,
    add_channel_callback,
    cancel_channel_callback,
    add_channel_input,
    retry_channel_callback,
    channel_detail_callback,
    toggle_channel_callback,
    delete_channel_callback,
    WAITING_CHANNEL,
)

from handlers.filters import (
    my_filters_callback,
    add_filter_callback,
    cancel_filter_callback,
    filter_input,
    filter_detail_callback,
    filter_action_callback,
    WAITING_FILTER_QUERY,
    WAITING_FILTER_EDIT,
)

from telegram_clients import (
    set_new_post_callback,
    start_all_user_polling,
    stop_all_clients,
)

from vacancies import process_post_with_filters

from notifications import send_vacancy_notification


# ============================================================
# CONFIG
# ============================================================

load_dotenv()

logging.basicConfig(
    format=(
        "%(asctime)s - "
        "%(name)s - "
        "%(levelname)s - "
        "%(message)s"
    ),
    level=logging.INFO,
)

logger = logging.getLogger(__name__)

application = None


# ============================================================
# TELEGRAM POST HELPERS
# ============================================================

async def _build_post_link(
    user_id: int,
    channel_id: int,
    message_id: int,
):
    """
    Формирует ссылку на исходный Telegram-пост.
    """

    channel = await get_user_channel(
        user_id,
        channel_id,
    )

    if not channel:
        return None, None

    channel_username = (
        channel.get("channel_username")
        or channel.get("username")
    )

    if channel_username:
        username_clean = channel_username.lstrip("@")

        return (
            f"https://t.me/{username_clean}/{message_id}",
            channel_username,
        )

    channel_id_str = str(channel_id)

    if channel_id_str.startswith("-100"):
        channel_id_str = channel_id_str[4:]

    return (
        f"https://t.me/c/{channel_id_str}/{message_id}",
        None,
    )


async def _send_match_notification(
    user_id: int,
    channel_id: int,
    message_id: int,
    vacancy_result: dict,
):
    """
    Отправляет уведомление по одной найденной вакансии.

    Если вакансия совпала с несколькими фильтрами,
    уведомление отправляется отдельно для каждого фильтра.
    """

    global application

    if application is None:
        logger.error("Application is not initialized")
        return

    matched_filters = vacancy_result.get(
        "matched_filters",
        [],
    )

    if not matched_filters:
        return

    vacancy_data = vacancy_result.get(
        "vacancy_data"
    )
    
    if not vacancy_data:
        return

    post_link, channel_username = (
        await _build_post_link(
            user_id=user_id,
            channel_id=channel_id,
            message_id=message_id,
        )
    )

    for match_result in matched_filters:
        score = int(
            match_result.get(
                "score",
                0,
            )
        )
        
        filter_names = [
            item.get("filter_name")
            for item in matched_filters
            if isinstance(item, dict) and item.get("filter_name")
        ]

        matched_conditions = match_result.get(
            "matched_conditions",
            [],
        )

        logger.info(
            "MATCH: user=%s channel=%s message=%s "
            "vacancy=%s filter=%s score=%s",
            user_id,
            channel_id,
            message_id,
            vacancy_data.get("title"),
            filter_names,
            score,
        )

        await send_vacancy_notification(
            user_id=user_id,
            text=vacancy_data.get("description", ""),
            channel_title=vacancy_data.get("channel_title"),
            channel_username=channel_username,
            post_link=post_link,
            matched_filters=filter_names,
        )


# ============================================================
# POST PROCESSOR
# ============================================================

async def post_processor(
    post_data: dict,
):
    """
    Обрабатывает новый пост, полученный от Telethon.

    Поддерживает:
    - обычные вакансии;
    - подборки вакансий;
    - вакансии дня;
    - вакансии недели;
    - вакансии месяца.
    """

    user_id = post_data.get("user_id")
    channel_id = post_data.get("channel_id")
    message_id = post_data.get("message_id")
    text = post_data.get("text", "")

    logger.info(
        "PROCESSING NEW POST: user=%s channel=%s message=%s",
        user_id,
        channel_id,
        message_id,
    )

    # --------------------------------------------------------
    # Проверяем обязательные данные
    # --------------------------------------------------------

    if not user_id:
        logger.warning(
            "Post received without user_id"
        )
        return

    if not channel_id:
        logger.warning(
            "Post received without channel_id for user %s",
            user_id,
        )
        return

    if not message_id:
        logger.warning(
            "Post received without message_id "
            "for user %s channel %s",
            user_id,
            channel_id,
        )
        return

    if not text:
        logger.info(
            "Post %s:%s has no text",
            channel_id,
            message_id,
        )
        return

    # --------------------------------------------------------
    # Получаем фильтры пользователя
    # --------------------------------------------------------

    filters_data = await get_user_filters(user_id)

    if not filters_data:
        logger.info(
            "Нет фильтров у пользователя %s",
            user_id,
        )
        return

    # --------------------------------------------------------
    # Обрабатываем пост
    # --------------------------------------------------------

    try:
        results = process_post_with_filters(
            text,
            filters_data,
        )

    except Exception:
        logger.exception(
            "Ошибка обработки поста %s:%s",
            channel_id,
            message_id,
        )
        return

    if not results:
        logger.info(
            "Пустой результат обработки %s:%s",
            channel_id,
            message_id,
        )
        return

    # --------------------------------------------------------
    # Тип поста
    # --------------------------------------------------------

    post_type = results.get(
        "post_type",
        "unknown",
    )

    logger.info(
        "POST TYPE: %s "
        "(user=%s channel=%s message=%s)",
        post_type,
        user_id,
        channel_id,
        message_id,
    )

    # --------------------------------------------------------
    # Если пост не является вакансией
    # --------------------------------------------------------

    if not results.get(
        "is_vacancy",
        False,
    ):
        logger.info(
            "POST IS NOT A VACANCY: %s:%s",
            channel_id,
            message_id,
        )
        return

    # --------------------------------------------------------
    # Получаем отдельные вакансии
    # --------------------------------------------------------

    vacancies = results.get(
        "vacancies",
        [],
    )

    if not vacancies:
        logger.info(
            "В посте не найдено вакансий: %s:%s",
            channel_id,
            message_id,
        )
        return

    logger.info(
        "FOUND %s vacancy item(s) in post %s:%s",
        len(vacancies),
        channel_id,
        message_id,
    )

    sent_count = 0

    # --------------------------------------------------------
    # Обрабатываем каждую вакансию отдельно
    # --------------------------------------------------------

    for vacancy_result in vacancies:

        vacancy_data = vacancy_result.get(
            "vacancy_data",
            {},
        )

        title = (
            vacancy_data.get("title")
            or vacancy_result.get("title")
            or "Без названия"
        )

        category = vacancy_result.get(
            "category"
        )

        matched_filters = vacancy_result.get(
            "matched_filters",
            [],
        )

        logger.info(
            "VACANCY #%s: %s | category=%s | matches=%s",
            vacancy_result.get("index"),
            title,
            category,
            len(matched_filters),
        )

        if not matched_filters:
            continue

        try:
            await _send_match_notification(
                user_id=user_id,
                channel_id=channel_id,
                message_id=message_id,
                vacancy_result=vacancy_result,
            )

            sent_count += 1

        except Exception:
            logger.exception(
                "Ошибка отправки уведомления "
                "для вакансии '%s' "
                "(user=%s channel=%s message=%s)",
                title,
                user_id,
                channel_id,
                message_id,
            )

    # --------------------------------------------------------
    # Итог
    # --------------------------------------------------------

    logger.info(
        "POST PROCESSING COMPLETE: %s:%s | type=%s | "
        "vacancies=%s | sent=%s",
        channel_id,
        message_id,
        post_type,
        len(vacancies),
        sent_count,
    )

    # --------------------------------------------------------
    # Сохраняем статус поста
    # --------------------------------------------------------

    first_matched = next(
        (
            vacancy
            for vacancy in vacancies
            if vacancy.get("matched_filters")
        ),
        None,
    )

    if first_matched:
        try:
            await update_post_vacancy_status(
                user_id,
                channel_id,
                message_id,
                is_vacancy=True,
                vacancy_data=first_matched.get(
                    "vacancy_data"
                ),
            )

        except Exception:
            logger.exception(
                "Не удалось обновить статус "
                "поста %s:%s",
                channel_id,
                message_id,
            )


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):
    logger.error(
        "Ошибка Telegram bot: %s",
        context.error,
        exc_info=context.error,
    )


# ============================================================
# TELETHON INITIALIZATION
# ============================================================

async def post_init(
    application_instance: Application,
):
    """
    Настраивает глобальный callback Telethon
    и запускает мониторинг каналов существующих пользователей.
    """

    logger.info(
        "Настройка глобального callback Telethon..."
    )

    set_new_post_callback(
        post_processor
    )

    logger.info(
        "Telethon post callback настроен"
    )

    logger.info(
        "Запуск мониторинга существующих каналов..."
    )

    await start_all_user_polling()

    logger.info(
        "Мониторинг существующих каналов запущен"
    )

async def post_shutdown(
    application_instance: Application,
):
    logger.info(
        "Остановка Telegram-клиентов..."
    )

    await stop_all_clients()

    logger.info(
        "Telegram-клиенты остановлены"
    )

# ============================================================
# MAIN
# ============================================================

def main():
    global application

    logger.info(
        "Бот запускается..."
    )

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # ========================================================
    # ERROR HANDLER
    # ========================================================

    application.add_error_handler(
        error_handler
    )

    # ========================================================
    # START
    # ========================================================

    application.add_handler(
        CommandHandler(
            "start",
            start_command,
        )
    )

    # ========================================================
    # MAIN MENU
    # ========================================================

    application.add_handler(
        CallbackQueryHandler(
            main_menu_callback,
            pattern=r"^main_menu$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            my_channels_callback,
            pattern=r"^my_channels$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            my_filters_callback,
            pattern=r"^my_filters$",
        )
    )

    # ========================================================
    # CHANNELS
    # ========================================================

    add_channel_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                add_channel_callback,
                pattern=r"^add_channel$",
            )
        ],
        states={
            WAITING_CHANNEL: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    add_channel_input,
                )
            ],
        },
        fallbacks=[
            CallbackQueryHandler(
                cancel_channel_callback,
                pattern=r"^cancel_channel$",
            ),
            CommandHandler(
                "start",
                start_command,
            ),
        ],
        allow_reentry=True,
    )

    application.add_handler(
        add_channel_conv
    )

    # Повторная проверка доступа к каналу
    application.add_handler(
        CallbackQueryHandler(
            retry_channel_callback,
            pattern=r"^retry_channel_",
        )
    )

    # Открытие конкретного канала
    application.add_handler(
        CallbackQueryHandler(
            channel_detail_callback,
            pattern=r"^channel_",
        )
    )

    # Включение / выключение канала
    application.add_handler(
        CallbackQueryHandler(
            toggle_channel_callback,
            pattern=r"^toggle_channel_",
        )
    )

    # Удаление канала
    application.add_handler(
        CallbackQueryHandler(
            delete_channel_callback,
            pattern=r"^delete_channel_",
        )
    )

    # ========================================================
    # FILTERS
    # ========================================================

    add_filter_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                add_filter_callback,
                pattern=r"^add_filter$",
            ),

            # Редактирование существующего фильтра
            CallbackQueryHandler(
                filter_action_callback,
                pattern=r"^edit_filter_",
            ),
        ],

        states={
            # Создание нового фильтра
            WAITING_FILTER_QUERY: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    filter_input,
                )
            ],

            # Редактирование существующего фильтра
            WAITING_FILTER_EDIT: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    filter_input,
                )
            ],
        },

        fallbacks=[
            CallbackQueryHandler(
                cancel_filter_callback,
                pattern=r"^cancel_filter$",
            ),
            CommandHandler(
                "start",
                start_command,
            ),
        ],

        allow_reentry=True,
    )

    application.add_handler(
        add_filter_conv
    )

    # Открытие конкретного фильтра
    application.add_handler(
        CallbackQueryHandler(
            filter_detail_callback,
            pattern=r"^filter_",
        )
    )

    # Включение / выключение / удаление фильтра
    #
    # edit_filter_ здесь НЕ нужен:
    # он является entry point выше и переводит
    # ConversationHandler в WAITING_FILTER_EDIT.
    application.add_handler(
        CallbackQueryHandler(
            filter_action_callback,
            pattern=(
                r"^(toggle_filter_|"
                r"delete_filter_|"
                r"confirm_delete_)"
            ),
        )
    )

    # ========================================================
    # RUN
    # ========================================================

    logger.info(
        "Бот запущен. "
        "Telethon-клиенты пользователей "
        "запускаются через /start."
    )

    application.run_polling()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    if platform.system() == "Windows":
        asyncio.set_event_loop_policy(
            asyncio.WindowsSelectorEventLoopPolicy()
        )

    main()