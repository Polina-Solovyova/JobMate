import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Callable, Awaitable

from telethon import TelegramClient, events
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.messages import GetHistoryRequest
from telethon.tl.types import Message, Channel, User
from telethon.errors import ChannelPrivateError, ChatAdminRequiredError

from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, SESSION_NAME
from db import (
    get_user_channels,
    update_channel_last_message,
    save_post,
    get_post
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TelegramUserClient:
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.client = TelegramClient(
            f"{SESSION_NAME}_{user_id}",  # отдельная сессия на пользователя
            TELEGRAM_API_ID,
            TELEGRAM_API_HASH
        )
        self._running = False
        self._poll_task = None
        self._on_new_post_callback: Optional[Callable[[int, int, int, str, datetime], Awaitable[None]]] = None

    async def start(self):
        """Авторизация и запуск клиента."""
        await self.client.start()
        me = await self.client.get_me()
        logger.info(f"Telethon клиент авторизован как {me.first_name} (ID: {me.id})")
        return me

    async def stop(self):
        """Остановка клиента и опроса."""
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
        await self.client.disconnect()

    def set_new_post_callback(self, callback: Callable[[int, int, int, str, datetime], Awaitable[None]]):
        """Устанавливает функцию, которая будет вызвана при обнаружении нового поста."""
        self._on_new_post_callback = callback

    async def check_channel_access(self, channel_identifier: str) -> Optional[dict]:
        """
        Проверяет, имеет ли пользователь доступ к каналу (подписан).
        Возвращает информацию о канале: {id, username, title} или None, если нет доступа.
        """
        try:
            entity = await self.client.get_entity(channel_identifier)
            if not isinstance(entity, Channel):
                logger.warning(f"'{channel_identifier}' не является каналом")
                return None

            # Проверяем, подписан ли пользователь
            try:
                full_channel = await self.client(GetFullChannelRequest(channel=entity))
                # Если мы здесь, значит канал доступен
                return {
                    "id": entity.id,
                    "username": f"@{entity.username}" if entity.username else None,
                    "title": entity.title
                }
            except (ChannelPrivateError, ChatAdminRequiredError):
                logger.warning(f"Нет доступа к каналу {entity.title} (не подписан)")
                return None
        except Exception as e:
            logger.error(f"Ошибка при проверке канала {channel_identifier}: {e}")
            return None

    async def _fetch_new_messages(self, channel_id: int, last_message_id: int) -> list:
        """
        Запрашивает новые сообщения из канала, начиная с last_message_id.
        Возвращает список сообщений (от старых к новым).
        """
        try:
            entity = await self.client.get_entity(channel_id)
            history = await self.client(GetHistoryRequest(
                peer=entity,
                limit=100,  # можно увеличить, но обычно 100 хватает на один цикл
                offset_id=last_message_id,
                offset_date=None,
                add_offset=0,
                max_id=0,
                min_id=last_message_id + 1,
                hash=0
            ))
            # Сообщения возвращаются от новых к старым, переворачиваем
            messages = list(reversed(history.messages))
            return messages
        except Exception as e:
            logger.error(f"Ошибка при получении сообщений из канала {channel_id}: {e}")
            return []

    async def _poll_channels(self):
        """Периодически опрашивает все активные каналы пользователя."""
        self._running = True
        while self._running:
            try:
                # Получаем список активных каналов пользователя
                channels = await get_user_channels(self.user_id)
                active_channels = [ch for ch in channels if ch.get("enabled", True)]

                for channel in active_channels:
                    channel_id = channel["channel_id"]
                    last_msg_id = channel.get("last_message_id", 0)

                    messages = await self._fetch_new_messages(channel_id, last_msg_id)
                    if messages:
                        # Обновляем last_message_id на ID последнего полученного сообщения
                        new_last_id = messages[-1].id
                        await update_channel_last_message(
                            self.user_id,
                            channel_id,
                            new_last_id,
                            datetime.utcnow()
                        )

                        # Обрабатываем каждое новое сообщение
                        for msg in messages:
                            if msg.text and self._on_new_post_callback:
                                # Проверяем, не сохраняли ли уже этот пост
                                existing = await get_post(self.user_id, channel_id, msg.id)
                                if not existing:
                                    # Сохраняем пост в БД
                                    await save_post(
                                        self.user_id,
                                        channel_id,
                                        msg.id,
                                        msg.text,
                                        msg.date.replace(tzinfo=None)  # делаем naive для MongoDB
                                    )
                                    # Вызываем колбэк для обработки поста
                                    await self._on_new_post_callback(
                                        self.user_id,
                                        channel_id,
                                        msg.id,
                                        msg.text,
                                        msg.date.replace(tzinfo=None)
                                    )

                # Ждём перед следующим опросом
                await asyncio.sleep(30)  # интервал опроса (можно вынести в настройки)

            except asyncio.CancelledError:
                logger.info("Опрос каналов остановлен")
                break
            except Exception as e:
                logger.error(f"Ошибка в цикле опроса: {e}")
                await asyncio.sleep(60)

    async def start_polling(self):
        """Запускает фоновую задачу опроса каналов."""
        if self._poll_task is None or self._poll_task.done():
            self._poll_task = asyncio.create_task(self._poll_channels())
            logger.info("Запущен опрос каналов")

    async def stop_polling(self):
        """Останавливает опрос каналов."""
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None