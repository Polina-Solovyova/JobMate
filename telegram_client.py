import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.tl.types import Channel

from config import (
    TELEGRAM_API_HASH,
    TELEGRAM_API_ID,
    TELEGRAM_SESSION_NAME,
)

from db import (
    get_post,
    get_user_channels,
    save_post,
    update_channel_last_message,
)


logger = logging.getLogger(__name__)


PostCallback = Callable[
    [Dict[str, Any]],
    Awaitable[None],
]


class TelegramUserClient:
    def __init__(
        self,
        user_id: int,
    ):
        if not TELEGRAM_API_ID:
            raise RuntimeError(
                "TELEGRAM_API_ID is not configured"
            )

        if not TELEGRAM_API_HASH:
            raise RuntimeError(
                "TELEGRAM_API_HASH is not configured"
            )

        self.user_id = user_id

        # Сессии хранятся рядом с приложением.
        # На Wispbyte папка /home/container должна быть persistent.
        base_dir = os.path.dirname(
            os.path.abspath(__file__)
        )

        session_dir = os.path.join(
            base_dir,
            "sessions",
        )

        os.makedirs(
            session_dir,
            exist_ok=True,
        )

        session_path = os.path.join(
            session_dir,
            f"{TELEGRAM_SESSION_NAME}_{user_id}",
        )

        self.client = TelegramClient(
            session_path,
            TELEGRAM_API_ID,
            TELEGRAM_API_HASH,
        )

        self._post_callback: Optional[PostCallback] = None
        self._polling = False

        # Текущая QR-сессия авторизации.
        self._qr_login = None

    def set_new_post_callback(
        self,
        callback: PostCallback,
    ) -> None:
        self._post_callback = callback

    async def start(self) -> bool:
        if not self.client.is_connected():
            await self.client.connect()

        authorized = await self.client.is_user_authorized()

        if not authorized:
            logger.warning(
                "Telegram session is not authorized for user %s",
                self.user_id,
            )
            return False

        me = await self.client.get_me()

        logger.info(
            "Telegram client started for user %s: username=%s",
            self.user_id,
            getattr(me, "username", None),
        )

        return True

    async def stop(self) -> None:
        self._polling = False
        self._qr_login = None

        if self.client.is_connected():
            await self.client.disconnect()

    async def is_authorized(self) -> bool:
        if not self.client.is_connected():
            await self.client.connect()

        return await self.client.is_user_authorized()

    async def create_qr_login(self):
        """
        Создаёт новую QR-сессию авторизации.

        Возвращает объект QRLogin из Telethon.
        """
        if not self.client.is_connected():
            await self.client.connect()

        if await self.client.is_user_authorized():
            return None

        self._qr_login = await self.client.qr_login()

        logger.info(
            "QR login created for user %s",
            self.user_id,
        )

        return self._qr_login

    async def wait_qr_login(self) -> str:
        """
        Ожидает подтверждения QR-кода в Telegram.

        Возможные результаты:
        - authorized
        - password
        """
        if self._qr_login is None:
            raise RuntimeError(
                "QR login has not been created"
            )

        try:
            await self._qr_login.wait()

            if await self.client.is_user_authorized():
                logger.info(
                    "QR login completed for user %s",
                    self.user_id,
                )

                return "authorized"

            return "failed"

        except SessionPasswordNeededError:
            logger.warning(
                "2FA password is required for user %s",
                self.user_id,
            )

            return "password"

        finally:
            self._qr_login = None

    async def cancel_qr_login(self) -> None:
        """
        Отменяет текущую QR-сессию.

        Сам Telethon не требует отдельного revoke:
        после истечения срока действия QR токен становится недействительным.
        """
        self._qr_login = None

    async def check_channel_access(
        self,
        channel_input: str,
    ) -> Optional[Channel]:
        if not await self.is_authorized():
            return None

        try:
            entity = await self.client.get_entity(
                channel_input
            )

            if not isinstance(entity, Channel):
                return None

            return entity

        except Exception:
            logger.exception(
                "Failed to access channel %s for user %s",
                channel_input,
                self.user_id,
            )

            return None

    async def _fetch_new_messages(
        self,
        channel: Dict[str, Any],
        page_size: int = 100,
    ) -> List[Any]:
        channel_id = int(
            channel["channel_id"]
        )

        last_message_id = int(
            channel.get("last_message_id") or 0
        )

        entity = await self.client.get_entity(
            channel_id
        )

        all_messages: List[Any] = []

        offset_id = 0

        while True:
            messages = await self.client.get_messages(
                entity,
                limit=page_size,
                min_id=last_message_id,
                offset_id=offset_id,
            )

            if not messages:
                break

            page = [
                message
                for message in messages
                if int(message.id) > last_message_id
            ]

            all_messages.extend(page)

            if len(messages) < page_size:
                break

            new_offset = min(
                int(message.id)
                for message in messages
            )

            if (
                new_offset <= 0
                or new_offset == offset_id
            ):
                break

            offset_id = new_offset

        unique_messages = {
            int(message.id): message
            for message in all_messages
        }

        result = list(
            unique_messages.values()
        )

        result.sort(
            key=lambda message: int(message.id)
        )

        return result

    async def _process_message(
        self,
        channel: Dict[str, Any],
        message: Any,
    ) -> bool:
        channel_id = int(
            channel["channel_id"]
        )

        message_id = int(
            message.id
        )

        existing_post = await get_post(
            user_id=self.user_id,
            channel_id=channel_id,
            message_id=message_id,
        )

        text = getattr(
            message,
            "message",
            None,
        ) or ""

        posted_at: Optional[datetime] = getattr(
            message,
            "date",
            None,
        )

        has_media = bool(
            getattr(message, "media", None)
        )

        if existing_post is None:
            await save_post(
                user_id=self.user_id,
                channel_id=channel_id,
                message_id=message_id,
                text=text,
                posted_at=posted_at,
                channel_username=channel.get(
                    "channel_username"
                ),
                channel_title=channel.get(
                    "channel_title"
                ),
                has_media=has_media,
            )

        if (
            existing_post
            and existing_post.get("processed")
        ):
            return True

        if self._post_callback is None:
            logger.warning(
                "Post callback is not configured "
                "for user %s",
                self.user_id,
            )

            return False

        post_data = {
            "user_id": self.user_id,
            "channel_id": channel_id,
            "channel_username": channel.get(
                "channel_username"
            ),
            "channel_title": channel.get(
                "channel_title"
            ),
            "message_id": message_id,
            "text": text,
            "posted_at": posted_at,
            "has_media": has_media,
        }

        await self._post_callback(
            post_data
        )

        return True

    async def _poll_channel(
        self,
        channel: Dict[str, Any],
    ) -> None:
        channel_id = int(
            channel["channel_id"]
        )

        try:
            entity = await self.client.get_entity(
                channel_id
            )

            if not isinstance(entity, Channel):
                return

            messages = await self._fetch_new_messages(
                channel
            )

            if not messages:
                return

            for message in messages:
                success = await self._process_message(
                    channel,
                    message,
                )

                if not success:
                    logger.warning(
                        "Stopping channel processing "
                        "after failed message %s",
                        message.id,
                    )

                    break

                await update_channel_last_message(
                    user_id=self.user_id,
                    channel_id=channel_id,
                    last_message_id=int(message.id),
                    last_post_at=getattr(
                        message,
                        "date",
                        None,
                    ),
                )

        except Exception:
            logger.exception(
                "Failed to poll channel %s for user %s",
                channel_id,
                self.user_id,
            )

    async def _poll_channels(self) -> None:
        channels = await get_user_channels(
            user_id=self.user_id,
            enabled_only=True,
        )

        for channel in channels:
            if not self._polling:
                break

            await self._poll_channel(
                channel
            )

    async def start_polling(
        self,
        interval: int = 30,
    ) -> None:
        if not await self.start():
            return

        self._polling = True

        try:
            while self._polling:
                await self._poll_channels()

                if self._polling:
                    await asyncio.sleep(
                        max(1, interval)
                    )

        except asyncio.CancelledError:
            raise

        except Exception:
            logger.exception(
                "Telegram polling stopped for user %s",
                self.user_id,
            )

        finally:
            self._polling = False

    async def run(self) -> None:
        if not await self.start():
            return

        await self.start_polling()