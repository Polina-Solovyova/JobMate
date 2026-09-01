import logging

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
from keyboards import main_menu_keyboard
from notifications import send_vacancy_notification
from telegram_client import TelegramUserClient
from telegram_clients import (
    get_telegram_client,
    set_new_post_callback,
    start_user_polling,
    stop_all_clients,
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


AUTH_PHONE = 1
AUTH_CODE = 2
AUTH_PASSWORD = 3


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
        setup_user_client_callback(client)

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

    await create_user(
        user_id=user.id,
        username=user.username,
    )

    client = await get_telegram_client(
        user.id
    )

    if await client.is_authorized():
        setup_user_client_callback(client)

        await start_user_polling(
            user.id
        )

        await update.message.reply_text(
            "Telegram-аккаунт уже подключён.",
            reply_markup=main_menu_keyboard(),
        )

        return ConversationHandler.END

    context.user_data.pop(
        "auth_phone",
        None,
    )
    context.user_data.pop(
        "phone_code_hash",
        None,
    )

    await update.message.reply_text(
        "Введите номер телефона Telegram "
        "в международном формате.\n\n"
        "Например: +371XXXXXXXX"
    )

    return AUTH_PHONE


async def auth_phone(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if (
        not update.message
        or not update.message.text
        or not update.effective_user
    ):
        return AUTH_PHONE

    user_id = update.effective_user.id
    phone = update.message.text.strip()

    client = await get_telegram_client(
        user_id
    )

    try:
        sent_code = await client.send_code(
            phone
        )

        context.user_data["auth_phone"] = phone
        context.user_data["phone_code_hash"] = (
            sent_code.phone_code_hash
        )

        await update.message.reply_text(
            "Код отправлен в Telegram.\n\n"
            "Введите полученный код."
        )

        return AUTH_CODE

    except Exception:
        logger.exception(
            "Failed to send Telegram code "
            "for user %s",
            user_id,
        )

        await update.message.reply_text(
            "Не удалось отправить код. "
            "Проверьте номер телефона "
            "и попробуйте ещё раз."
        )

        return AUTH_PHONE


async def auth_code(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if (
        not update.message
        or not update.message.text
        or not update.effective_user
    ):
        return AUTH_CODE

    user_id = update.effective_user.id
    code = update.message.text.strip()

    phone = context.user_data.get(
        "auth_phone"
    )
    phone_code_hash = context.user_data.get(
        "phone_code_hash"
    )

    if not phone or not phone_code_hash:
        await update.message.reply_text(
            "Сессия подключения потеряна. "
            "Запустите /connect заново."
        )

        return ConversationHandler.END

    client = await get_telegram_client(
        user_id
    )

    try:
        result = await client.sign_in(
            phone=phone,
            code=code,
            phone_code_hash=phone_code_hash,
        )

        if result == "password":
            await update.message.reply_text(
                "Для аккаунта включена "
                "двухфакторная аутентификация.\n\n"
                "Введите пароль Telegram."
            )

            return AUTH_PASSWORD

        context.user_data.pop(
            "auth_phone",
            None,
        )
        context.user_data.pop(
            "phone_code_hash",
            None,
        )

        setup_user_client_callback(client)

        await start_user_polling(
            user_id
        )

        await update.message.reply_text(
            "Telegram-аккаунт успешно подключён.",
            reply_markup=main_menu_keyboard(),
        )

        return ConversationHandler.END

    except Exception:
        logger.exception(
            "Failed to sign in Telegram account "
            "for user %s",
            user_id,
        )

        await update.message.reply_text(
            "Не удалось войти в Telegram. "
            "Проверьте код и попробуйте ещё раз."
        )

        return AUTH_CODE


async def auth_password(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if (
        not update.message
        or not update.message.text
        or not update.effective_user
    ):
        return AUTH_PASSWORD

    user_id = update.effective_user.id
    password = update.message.text.strip()

    client = await get_telegram_client(
        user_id
    )

    try:
        await client.sign_in_password(
            password
        )

        context.user_data.pop(
            "auth_phone",
            None,
        )
        context.user_data.pop(
            "phone_code_hash",
            None,
        )

        setup_user_client_callback(client)

        await start_user_polling(
            user_id
        )

        await update.message.reply_text(
            "Telegram-аккаунт успешно подключён.",
            reply_markup=main_menu_keyboard(),
        )

        return ConversationHandler.END

    except Exception:
        logger.exception(
            "Failed to sign in with 2FA password "
            "for user %s",
            user_id,
        )

        await update.message.reply_text(
            "Неверный пароль или не удалось "
            "завершить авторизацию. "
            "Попробуйте ещё раз."
        )

        return AUTH_PASSWORD


async def cancel_auth(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    context.user_data.pop(
        "auth_phone",
        None,
    )
    context.user_data.pop(
        "phone_code_hash",
        None,
    )

    if update.message:
        await update.message.reply_text(
            "Подключение отменено."
        )

    return ConversationHandler.END


async def post_processor(
    post: dict,
):
    user_id = int(post["user_id"])

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

        await send_vacancy_notification(
            user_id=user_id,
            text=text,
            channel_title=channel_title,
            channel_username=channel_username,
            post_link=post_link,
            matched_filters=matched_filters,
        )

    except Exception:
        logger.exception(
            "Failed to process post %s/%s "
            "for user %s",
            channel_id,
            message_id,
            user_id,
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
            AUTH_PHONE: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    auth_phone,
                )
            ],
            AUTH_CODE: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    auth_code,
                )
            ],
            AUTH_PASSWORD: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    auth_password,
                )
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
        ],
        states={
            1: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    filter_input,
                ),
            ],
            2: [
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
            CommandHandler(
                "cancel",
                cancel_auth,
            ),
        ],
    )


async def post_init(application: Application):
    await create_indexes()

    set_new_post_callback(
        post_processor
    )

    await initialize_authorized_clients()


async def post_shutdown(
    application: Application,
):
    await stop_all_clients()


def setup_user_client_callback(
    client: TelegramUserClient,
):
    client.set_new_post_callback(
        post_processor
    )


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
    ).to_list(length=None)


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