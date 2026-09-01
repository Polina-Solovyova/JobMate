import logging
from datetime import datetime
from typing import Optional, List, Dict

from db import (
    add_user_channel,
    get_user_channels,
    get_user_channel,
    remove_user_channel,
    set_channel_enabled,
    update_channel_last_message
)
from telegram_client import TelegramUserClient

logger = logging.getLogger(__name__)


async def add_channel_for_user(
    user_id: int,
    client: TelegramUserClient,
    identifier: str
) -> Dict[str, any]:
    """
    Добавляет канал пользователю.
    Проверяет доступ через Telethon, затем сохраняет в БД.
    Возвращает dict с информацией о канале или ошибкой.
    """
    # Проверяем доступ к каналу через пользовательский клиент
    channel_info = await client.check_channel_access(identifier)
    if not channel_info:
        return {
            "success": False,
            "error": "not_subscribed",
            "message": "Вы не подписаны на этот канал или он не существует."
        }

    channel_id = channel_info["id"]

    # Проверяем, не добавлен ли уже этот канал пользователем
    existing = await get_user_channel(user_id, channel_id)
    if existing:
        return {
            "success": False,
            "error": "already_added",
            "message": "Этот канал уже добавлен.",
            "channel": existing
        }

    # Сохраняем канал в БД
    await add_user_channel(
        user_id=user_id,
        channel_id=channel_id,
        username=channel_info.get("username"),
        title=channel_info["title"]
    )

    # Получаем последнее сообщение, чтобы установить last_message_id
    # (чтобы не обрабатывать старые посты)
    try:
        entity = await client.client.get_entity(channel_id)
        # Получаем последнее сообщение в канале
        from telethon.tl.functions.messages import GetHistoryRequest
        history = await client.client(GetHistoryRequest(
            peer=entity,
            limit=1,
            offset_id=0,
            offset_date=None,
            add_offset=0,
            max_id=0,
            min_id=0,
            hash=0
        ))
        if history.messages:
            last_msg = history.messages[0]
            await update_channel_last_message(
                user_id, channel_id, last_msg.id, last_msg.date.replace(tzinfo=None)
            )
    except Exception as e:
        logger.warning(f"Не удалось получить последнее сообщение для {channel_id}: {e}")

    return {
        "success": True,
        "channel": {
            "id": channel_id,
            "username": channel_info.get("username"),
            "title": channel_info["title"]
        }
    }


async def get_channels_list(user_id: int) -> List[Dict]:
    """Возвращает список всех каналов пользователя."""
    return await get_user_channels(user_id)


async def toggle_channel(user_id: int, channel_id: int, enabled: bool) -> bool:
    """Включить/выключить отслеживание канала."""
    channel = await get_user_channel(user_id, channel_id)
    if not channel:
        return False
    await set_channel_enabled(user_id, channel_id, enabled)
    return True


async def delete_channel(user_id: int, channel_id: int) -> bool:
    """Удалить канал из списка пользователя."""
    channel = await get_user_channel(user_id, channel_id)
    if not channel:
        return False
    await remove_user_channel(user_id, channel_id)
    return True