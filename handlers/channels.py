import logging

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from db import (
    add_user_channel,
    delete_channel,
    get_user_channel,
    get_user_channels,
    toggle_channel,
    update_user_channel,
)
from keyboards import (
    channels_list_keyboard,
    main_menu_keyboard,
)
from telegram_clients import get_telegram_client


logger = logging.getLogger(__name__)

WAITING_CHANNEL = 1


def normalize_channel_input(value: str) -> str:
    value = value.strip()

    prefixes = (
        "https://t.me/",
        "http://t.me/",
        "https://telegram.me/",
        "http://telegram.me/",
    )

    for prefix in prefixes:
        if value.lower().startswith(prefix):
            value = value[len(prefix):]
            break

    value = value.strip().strip("/")

    if value.startswith("t.me/"):
        value = value[5:].strip("/")

    if "/" in value:
        value = value.split("/", 1)[0]

    if value and not value.startswith("@"):
        value = f"@{value}"

    return value


async def my_channels_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id

    channels = await get_user_channels(
        user_id=user_id,
    )

    text = (
        "Ваши каналы:"
        if channels
        else "У вас пока нет добавленных каналов."
    )

    await query.edit_message_text(
        text=text,
        reply_markup=channels_list_keyboard(
            channels
        ),
    )


async def add_channel_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    context.user_data.pop(
        "editing_channel_id",
        None,
    )

    await query.edit_message_text(
        "Отправьте username или ссылку на Telegram-канал.\n\n"
        "Например:\n"
        "@vacancies_channel\n"
        "https://t.me/vacancies_channel"
    )

    return WAITING_CHANNEL


async def cancel_channel_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    context.user_data.pop(
        "editing_channel_id",
        None,
    )

    await query.edit_message_text(
        "Действие отменено.",
        reply_markup=main_menu_keyboard(),
    )

    return ConversationHandler.END


async def add_channel_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message or not update.message.text:
        return WAITING_CHANNEL

    user_id = update.effective_user.id

    channel_input = normalize_channel_input(
        update.message.text
    )

    if not channel_input:
        await update.message.reply_text(
            "Не удалось определить канал. "
            "Отправьте username или ссылку на канал."
        )
        return WAITING_CHANNEL

    client = await get_telegram_client(
        user_id
    )

    try:
        if not await client.is_authorized():
            await update.message.reply_text(
                "Сначала подключите Telegram-аккаунт "
                "командой /connect."
            )
            return ConversationHandler.END

        channel = await client.check_channel_access(
            channel_input
        )

        if channel is None:
            await update.message.reply_text(
                "Не удалось получить доступ к этому каналу.\n\n"
                "Проверьте username, ссылку и наличие подписки "
                "Telegram-аккаунта."
            )
            return WAITING_CHANNEL

        channel_id = int(channel.id)

        existing = await get_user_channel(
            user_id=user_id,
            channel_id=channel_id,
        )

        if existing:
            channels = await get_user_channels(
                user_id=user_id,
            )

            await update.message.reply_text(
                "Этот канал уже добавлен.",
                reply_markup=channels_list_keyboard(
                    channels
                ),
            )

            return ConversationHandler.END

        channel_username = getattr(
            channel,
            "username",
            None,
        )

        channel_title = getattr(
            channel,
            "title",
            None,
        )

        await add_user_channel(
            user_id=user_id,
            channel_id=channel_id,
            channel_username=channel_username,
            channel_title=channel_title,
        )

        # Не отправляем пользователю старые сообщения.
        try:
            messages = await client.client.get_messages(
                channel,
                limit=1,
            )

            if messages:
                last_message = messages[0]

                from db import update_channel_last_message

                await update_channel_last_message(
                    user_id=user_id,
                    channel_id=channel_id,
                    last_message_id=int(last_message.id),
                    last_post_at=getattr(
                        last_message,
                        "date",
                        None,
                    ),
                )

        except Exception:
            logger.exception(
                "Failed to initialize channel cursor %s",
                channel_id,
            )

        channels = await get_user_channels(
            user_id=user_id,
        )

        await update.message.reply_text(
            f"Канал «{channel_title or channel_username or channel_id}» добавлен.",
            reply_markup=channels_list_keyboard(
                channels
            ),
        )

        return ConversationHandler.END

    except Exception:
        logger.exception(
            "Failed to add channel for user %s",
            user_id,
        )

        await update.message.reply_text(
            "Не удалось добавить канал. "
            "Проверьте данные и попробуйте ещё раз."
        )

        return WAITING_CHANNEL


async def _get_channel_by_document_id(
    user_id: int,
    document_id: str,
):
    channels = await get_user_channels(
        user_id=user_id,
    )

    for channel in channels:
        if str(channel.get("_id")) == str(document_id):
            return channel, channels

    return None, channels


async def toggle_channel_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id

    document_id = (
        query.data or ""
    ).removeprefix(
        "toggle_channel_"
    )

    try:
        channel, channels = await _get_channel_by_document_id(
            user_id,
            document_id,
        )

        if channel is None:
            await query.edit_message_text(
                "Канал не найден.",
                reply_markup=channels_list_keyboard(
                    channels
                ),
            )
            return

        enabled = not bool(
            channel.get("enabled", True)
        )

        updated = await toggle_channel(
            user_id=user_id,
            channel_id=int(channel["channel_id"]),
            enabled=enabled,
        )

        if not updated:
            await query.edit_message_text(
                "Не удалось изменить состояние канала.",
                reply_markup=channels_list_keyboard(
                    channels
                ),
            )
            return

        channels = await get_user_channels(
            user_id=user_id,
        )

        await query.edit_message_text(
            "Канал включён."
            if enabled
            else "Канал выключен.",
            reply_markup=channels_list_keyboard(
                channels
            ),
        )

    except Exception:
        logger.exception(
            "Failed to toggle channel %s for user %s",
            document_id,
            user_id,
        )

        await query.edit_message_text(
            "Не удалось изменить состояние канала."
        )


async def delete_channel_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id

    document_id = (
        query.data or ""
    ).removeprefix(
        "delete_channel_"
    )

    try:
        channel, channels = await _get_channel_by_document_id(
            user_id,
            document_id,
        )

        if channel is None:
            await query.edit_message_text(
                "Канал не найден или уже удалён.",
                reply_markup=channels_list_keyboard(
                    channels
                ),
            )
            return

        deleted = await delete_channel(
            user_id=user_id,
            channel_id=int(channel["channel_id"]),
        )

        channels = await get_user_channels(
            user_id=user_id,
        )

        await query.edit_message_text(
            "Канал удалён."
            if deleted
            else "Канал не найден или уже удалён.",
            reply_markup=channels_list_keyboard(
                channels
            ),
        )

    except Exception:
        logger.exception(
            "Failed to delete channel %s for user %s",
            document_id,
            user_id,
        )

        await query.edit_message_text(
            "Не удалось удалить канал."
        )


async def retry_channel_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id

    document_id = (
        query.data or ""
    ).removeprefix(
        "retry_channel_"
    )

    try:
        channel, channels = await _get_channel_by_document_id(
            user_id,
            document_id,
        )

        if channel is None:
            await query.edit_message_text(
                "Канал не найден.",
                reply_markup=channels_list_keyboard(
                    channels
                ),
            )
            return

        client = await get_telegram_client(
            user_id
        )

        if not await client.is_authorized():
            await query.edit_message_text(
                "Сначала подключите Telegram-аккаунт "
                "командой /connect."
            )
            return

        identifier = (
            channel.get("channel_username")
            or channel.get("channel_id")
        )

        access = await client.check_channel_access(
            str(identifier)
        )

        if access is None:
            await query.edit_message_text(
                "Доступ к каналу по-прежнему не получен.",
                reply_markup=channels_list_keyboard(
                    channels
                ),
            )
            return

        await update_user_channel(
            user_id=user_id,
            channel_id=int(channel["channel_id"]),
            updates={
                "channel_username": getattr(
                    access,
                    "username",
                    None,
                ),
                "channel_title": getattr(
                    access,
                    "title",
                    None,
                ),
            },
        )

        channels = await get_user_channels(
            user_id=user_id,
        )

        await query.edit_message_text(
            "Доступ к каналу восстановлен.",
            reply_markup=channels_list_keyboard(
                channels
            ),
        )

    except Exception:
        logger.exception(
            "Failed to retry channel %s for user %s",
            document_id,
            user_id,
        )

        await query.edit_message_text(
            "Не удалось проверить доступ к каналу."
        )