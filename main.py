import asyncio
import io
import logging

import qrcode

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from config import BOT_TOKEN

from db import (
    create_indexes,
    create_user,
    get_user_filters,
    mark_post_processed,
)

from handlers.filters import (
    WAITING_FILTER_EDIT,
    add_filter_callback,
    cancel_filter_callback,
    filter_action_callback,
    filter_detail_callback,
    filter_input,
    my_filters_callback,
)

from handlers.channels import (
    WAITING_CHANNEL,
    add_channel_callback,
    add_channel_input,
    cancel_channel_callback,
    delete_channel_callback,
    my_channels_callback,
    retry_channel_callback,
    toggle_channel_callback,
)

from handlers.settings import settings_callback

from keyboards import main_menu_keyboard

from notifications import send_vacancy_notification

from telegram_client import TelegramUserClient

from telegram_clients import (
    cancel_qr_login,
    get_telegram_client,
    register_qr_task,
    set_new_post_callback,
    start_qr_login,
    start_user_polling,
    stop_all_clients,
    wait_qr_login,
)

from vacancies import process_post_with_filters


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

AUTH_QR = 1


async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user

    if not user or not update.message:
        return

    await create_user(
        user_id=user.id,
        username=user.username,
    )

    client = await get_telegram_client(
        user.id
    )

    if await client.is_authorized():
        setup_user_client_callback(
            client
        )

        await start_user_polling(
            user.id
        )

        await update.message.reply_text(
            "Telegram-аккаунт подключён.",
            reply_markup=main_menu_keyboard(),
        )

        return

    await update.message.reply_text(
        "Telegram-аккаунт не подключён.\n\n"
        "Используйте /connect для подключения."
    )


async def connect_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user

    if not user or not update.message:
        return ConversationHandler.END

    user_id = user.id

    await create_user(
        user_id=user_id,
        username=user.username,
    )

    client = await get_telegram_client(
        user_id
    )

    if await client.is_authorized():
        setup_user_client_callback(
            client
        )

        await start_user_polling(
            user_id
        )

        await update.message.reply_text(
            "Telegram-аккаунт уже подключён.",
            reply_markup=main_menu_keyboard(),
        )

        return ConversationHandler.END

    await cancel_qr_login(
        user_id
    )

    try:
        qr_login = await start_qr_login(
            user_id
        )

        if qr_login is None:
            await update.message.reply_text(
                "Telegram-аккаунт уже подключён.",
                reply_markup=main_menu_keyboard(),
            )

            return ConversationHandler.END

        qr_image = qrcode.make(
            qr_login.url
        )

        image_buffer = io.BytesIO()

        qr_image.save(
            image_buffer,
            format="PNG",
        )

        image_buffer.seek(0)

        await update.message.reply_photo(
            photo=image_buffer,
            caption=(
                "Отсканируйте этот QR-код "
                "в официальном приложении Telegram.\n\n"
                "Telegram → Настройки → Устройства → "
                "Подключить устройство.\n\n"
                "После сканирования подтвердите вход "
                "на своём устройстве.\n\n"
                "Не пересылайте этот QR-код другим людям."
            ),
        )

        task = asyncio.create_task(
            wait_for_qr_authorization(
                user_id=user_id,
                chat_id=update.effective_chat.id,
            ),
            name=f"telegram-qr-login-{user_id}",
        )

        register_qr_task(
            user_id,
            task,
        )

        return AUTH_QR

    except Exception:
        logger.exception(
            "Failed to create QR login for user %s",
            user_id,
        )

        await update.message.reply_text(
            "Не удалось создать QR-код "
            "для подключения Telegram.\n\n"
            "Попробуйте /connect ещё раз."
        )

        return ConversationHandler.END


async def wait_for_qr_authorization(
    user_id: int,
    chat_id: int,
):
    try:
        result = await wait_qr_login(
            user_id
        )

        if result == "authorized":
            client = await get_telegram_client(
                user_id
            )

            setup_user_client_callback(
                client
            )

            await start_user_polling(
                user_id
            )

            await send_bot_message(
                chat_id,
                (
                    "Telegram-аккаунт успешно "
                    "подключён."
                ),
            )

            return

        if result == "password":
            await send_bot_message(
                chat_id,
                (
                    "QR-код был подтверждён, но "
                    "Telegram запросил пароль "
                    "двухэтапной аутентификации.\n\n"
                    "Я не запрашиваю и не принимаю "
                    "пароль Telegram через этот бот. "
                    "Это сделано специально для "
                    "безопасности аккаунта.\n\n"
                    "Если Telegram не завершил вход, "
                    "запустите /connect ещё раз."
                ),
            )

            return

        await send_bot_message(
            chat_id,
            (
                "Не удалось завершить подключение "
                "Telegram. Запустите /connect ещё раз."
            ),
        )

    except asyncio.CancelledError:
        raise

    except Exception:
        logger.exception(
            "QR authorization failed for user %s",
            user_id,
        )

        await send_bot_message(
            chat_id,
            (
                "Подключение Telegram не завершилось.\n\n"
                "Запустите /connect ещё раз."
            ),
        )


async def send_bot_message(
    chat_id: int,
    text: str,
):
    from telegram import Bot

    if not BOT_TOKEN:
        logger.error(
            "BOT_TOKEN is not configured"
        )
        return

    bot = Bot(
        token=BOT_TOKEN
    )

    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
        )

    finally:
        await bot.shutdown()


async def cancel_auth(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user

    if user:
        await cancel_qr_login(
            user.id
        )

    if update.message:
        await update.message.reply_text(
            "Подключение отменено."
        )

    return ConversationHandler.END


async def main_menu_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if not query:
        return

    await query.answer()

    await query.edit_message_text(
        "Главное меню:",
        reply_markup=main_menu_keyboard(),
    )


async def post_processor(
    post: dict,
):
    logger.info(
        "POST PROCESSOR CALLED: user=%s channel=%s message_id=%s text=%r",
        user_id,
        channel_id,
        message_id,
        text[:300],
    )
    user_id = int(
        post["user_id"]
    )

    channel_id = int(
        post["channel_id"]
    )

    message_id = int(
        post["message_id"]
    )

    text = post.get("text") or ""

    try:
        user_filters = await get_user_filters(
            user_id=user_id,
            enabled_only=True,
        )

        result = process_post_with_filters(
            post_text=text,
            filters=user_filters,
        )

        is_vacancy = result.get(
            "is_vacancy",
            False,
        )

        vacancy_data = result.get(
            "vacancy_data"
        )


        await mark_post_processed(
            user_id=user_id,
            channel_id=channel_id,
            message_id=message_id,
            is_vacancy=is_vacancy,
            vacancy_data=vacancy_data,
        )

        if not is_vacancy:
            return

        matched_filters = result.get(
            "matched_filters",
            [],
        )

        if not matched_filters:
            return

        channel_username = post.get(
            "channel_username"
        )

        channel_title = post.get(
            "channel_title"
        )

        post_link = None

        if channel_username:
            username = channel_username.lstrip("@")

            post_link = (
                f"https://t.me/"
                f"{username}/"
                f"{message_id}"
            )

        matched_filter_names = [
            item.get(
                "filter_name",
                "Без названия",
            )
            if isinstance(item, dict)
            else str(item)
            for item in matched_filters
        ]
        
        logger.info(
            "FILTER RESULT: user=%s is_vacancy=%s matched_filters=%r",
            user_id,
            is_vacancy,
            matched_filters,
        )
        
        logger.info(
            "SENDING VACANCY NOTIFICATION: user=%s filters=%r",
            user_id,
            matched_filter_names,
        )
        await send_vacancy_notification(
            user_id=user_id,
            text=text,
            channel_title=channel_title,
            channel_username=channel_username,
            post_link=post_link,
            matched_filters=matched_filter_names,
        )

    except Exception:
        logger.exception(
            "Failed to process post %s/%s "
            "for user %s",
            channel_id,
            message_id,
            user_id,
        )


def setup_user_client_callback(
    client: TelegramUserClient,
):
    client.set_new_post_callback(
        post_processor
    )


def build_auth_conversation():
    return ConversationHandler(
        entry_points=[
            CommandHandler(
                "connect",
                connect_command,
            )
        ],
        states={
            AUTH_QR: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    lambda update, context: AUTH_QR,
                ),
            ],
        },
        fallbacks=[
            CommandHandler(
                "cancel",
                cancel_auth,
            )
        ],
    )


def build_channel_conversation():
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                add_channel_callback,
                pattern=r"^add_channel$",
            )
        ],
        states={
            WAITING_CHANNEL: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    add_channel_input,
                ),
                CallbackQueryHandler(
                    cancel_channel_callback,
                    pattern=r"^main_menu$",
                ),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(
                cancel_channel_callback,
                pattern=r"^main_menu$",
            ),
            CommandHandler(
                "cancel",
                cancel_auth,
            ),
        ],
    )


def build_filter_conversation():
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                add_filter_callback,
                pattern=r"^add_filter$",
            ),
            CallbackQueryHandler(
                filter_action_callback,
                pattern=r"^edit_filter_",
            ),
        ],
        states={
            1: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    filter_input,
                ),
            ],
            WAITING_FILTER_EDIT: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    filter_input,
                ),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(
                cancel_filter_callback,
                pattern=r"^my_filters$",
            ),
            CallbackQueryHandler(
                cancel_filter_callback,
                pattern=r"^main_menu$",
            ),
            CommandHandler(
                "cancel",
                cancel_auth,
            ),
        ],
    )


async def post_init(
    application: Application,
):
    await create_indexes()

    set_new_post_callback(
        post_processor
    )

    await initialize_authorized_clients()


async def post_shutdown(
    application: Application,
):
    await stop_all_clients()


async def initialize_authorized_clients():
    users = await _get_authorized_users()

    for user in users:
        user_id = user["user_id"]

        try:
            client = await get_telegram_client(
                user_id
            )

            if not await client.is_authorized():
                continue

            setup_user_client_callback(
                client
            )

            await start_user_polling(
                user_id
            )

        except Exception:
            logger.exception(
                "Failed to initialize Telegram "
                "client for user %s",
                user_id,
            )


async def _get_authorized_users():
    from db import users_col

    return await users_col.find(
        {}
    ).to_list(
        length=None
    )


def build_application() -> Application:
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN is not configured"
        )

    application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    application.add_handler(
        build_auth_conversation()
    )

    application.add_handler(
        CommandHandler(
            "start",
            start_command,
        )
    )

    application.add_handler(
        build_channel_conversation()
    )

    application.add_handler(
        build_filter_conversation()
    )

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
            toggle_channel_callback,
            pattern=r"^toggle_channel_",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            delete_channel_callback,
            pattern=r"^delete_channel_",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            retry_channel_callback,
            pattern=r"^retry_channel_",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            my_filters_callback,
            pattern=r"^my_filters$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            filter_detail_callback,
            pattern=r"^filter_",
        )
    )

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

    application.add_handler(
        CallbackQueryHandler(
            settings_callback,
            pattern=r"^settings$",
        )
    )

    application.bot_data[
        "post_processor"
    ] = post_processor

    return application


def main():
    application = build_application()

    application.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()