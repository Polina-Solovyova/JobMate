import logging
from typing import Any, Dict, List

from db import (
    add_user_channel,
    delete_channel as db_delete_channel,
    get_user_channel,
    get_user_channels,
    toggle_channel as db_toggle_channel,
    update_channel_last_message,
)
from telegram_client import TelegramUserClient


logger = logging.getLogger(__name__)


async def add_channel_for_user(
    user_id: int,
    client: TelegramUserClient,
    identifier: str,
) -> Dict[str, Any]:
    channel = await client.check_channel_access(
        identifier
    )

    if channel is None:
        return {
            "success": False,
            "error": "not_accessible",
            "message": (
                "Не удалось получить доступ к каналу. "
                "Проверьте ссылку и убедитесь, что "
                "Telegram-аккаунт подписан на канал."
            ),
        }

    channel_id = int(channel.id)
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

    existing = await get_user_channel(
        user_id=user_id,
        channel_id=channel_id,
    )

    if existing:
        return {
            "success": False,
            "error": "already_added",
            "message": "Этот канал уже добавлен.",
            "channel": existing,
        }

    await add_user_channel(
        user_id=user_id,
        channel_id=channel_id,
        channel_username=channel_username,
        channel_title=channel_title,
    )

    # Новые каналы начинают отслеживаться с текущего последнего
    # сообщения. Старые публикации не должны рассылаться пользователю.
    try:
        messages = await client.client.get_messages(
            channel,
            limit=1,
        )

        if messages:
            last_message = messages[0]

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
            "Failed to initialize last message for channel %s",
            channel_id,
        )

    saved_channel = await get_user_channel(
        user_id=user_id,
        channel_id=channel_id,
    )

    return {
        "success": True,
        "channel": saved_channel
        or {
            "channel_id": channel_id,
            "channel_username": channel_username,
            "channel_title": channel_title,
            "enabled": True,
        },
    }


async def get_channels_list(
    user_id: int,
) -> List[Dict[str, Any]]:
    return await get_user_channels(
        user_id=user_id,
    )


async def toggle_channel(
    user_id: int,
    channel_id: int,
    enabled: bool,
) -> bool:
    channel = await get_user_channel(
        user_id=user_id,
        channel_id=channel_id,
    )

    if not channel:
        return False

    return await db_toggle_channel(
        user_id=user_id,
        channel_id=channel_id,
        enabled=enabled,
    )


async def delete_channel(
    user_id: int,
    channel_id: int,
) -> bool:
    return await db_delete_channel(
        user_id=user_id,
        channel_id=channel_id,
    )
