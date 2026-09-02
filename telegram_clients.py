import asyncio
import logging
from typing import Optional

from telegram_client import TelegramUserClient


logger = logging.getLogger(__name__)


_clients: dict[int, TelegramUserClient] = {}
_polling_tasks: dict[int, asyncio.Task] = {}
_qr_tasks: dict[int, asyncio.Task] = {}

_post_callback = None


def set_new_post_callback(callback) -> None:
    global _post_callback

    _post_callback = callback

    for client in _clients.values():
        client.set_new_post_callback(
            callback
        )


async def get_telegram_client(
    user_id: int,
) -> TelegramUserClient:
    client = _clients.get(user_id)

    if client is None:
        client = TelegramUserClient(
            user_id=user_id
        )

        if _post_callback is not None:
            client.set_new_post_callback(
                _post_callback
            )

        _clients[user_id] = client

    elif _post_callback is not None:
        client.set_new_post_callback(
            _post_callback
        )

    return client


async def start_qr_login(
    user_id: int,
):
    """
    Создаёт QR-login для пользователя.

    Возвращает:
        QRLogin | None
    """
    client = await get_telegram_client(
        user_id
    )

    if await client.is_authorized():
        return None

    return await client.create_qr_login()


async def wait_qr_login(
    user_id: int,
) -> str:
    client = await get_telegram_client(
        user_id
    )

    return await client.wait_qr_login()


async def cancel_qr_login(
    user_id: int,
) -> None:
    task = _qr_tasks.pop(
        user_id,
        None,
    )

    if task is not None:
        task.cancel()

        await asyncio.gather(
            task,
            return_exceptions=True,
        )

    client = _clients.get(
        user_id
    )

    if client is not None:
        await client.cancel_qr_login()


def register_qr_task(
    user_id: int,
    task: asyncio.Task,
) -> None:
    old_task = _qr_tasks.get(
        user_id
    )

    if (
        old_task is not None
        and not old_task.done()
    ):
        old_task.cancel()

    _qr_tasks[user_id] = task

    def _task_done(
        completed_task: asyncio.Task,
    ):
        current = _qr_tasks.get(
            user_id
        )

        if current is completed_task:
            _qr_tasks.pop(
                user_id,
                None,
            )

        try:
            exception = completed_task.exception()

            if exception:
                logger.error(
                    "QR login task failed for user %s",
                    user_id,
                    exc_info=(
                        type(exception),
                        exception,
                        exception.__traceback__,
                    ),
                )

        except asyncio.CancelledError:
            pass

        except Exception:
            logger.exception(
                "Failed to inspect QR task for user %s",
                user_id,
            )

    task.add_done_callback(
        _task_done
    )


async def start_user_polling(
    user_id: int,
    interval: int = 30,
) -> bool:
    client = await get_telegram_client(
        user_id
    )

    if not await client.is_authorized():
        return False

    existing_task = _polling_tasks.get(
        user_id
    )

    if (
        existing_task is not None
        and not existing_task.done()
    ):
        return True

    task = asyncio.create_task(
        client.start_polling(
            interval=interval
        ),
        name=f"telegram-polling-{user_id}",
    )

    _polling_tasks[user_id] = task

    def _task_done(
        completed_task: asyncio.Task,
    ):
        _polling_tasks.pop(
            user_id,
            None,
        )

        try:
            exception = completed_task.exception()

            if exception:
                logger.error(
                    "Polling task failed for user %s",
                    user_id,
                    exc_info=(
                        type(exception),
                        exception,
                        exception.__traceback__,
                    ),
                )

        except asyncio.CancelledError:
            pass

        except Exception:
            logger.exception(
                "Failed to inspect polling task for user %s",
                user_id,
            )

    task.add_done_callback(
        _task_done
    )

    logger.info(
        "Telegram polling started for user %s",
        user_id,
    )

    return True


async def stop_user_client(
    user_id: int,
) -> None:
    await cancel_qr_login(
        user_id
    )

    task: Optional[asyncio.Task] = (
        _polling_tasks.pop(
            user_id,
            None,
        )
    )

    if task is not None:
        task.cancel()

        await asyncio.gather(
            task,
            return_exceptions=True,
        )

    client = _clients.pop(
        user_id,
        None,
    )

    if client is not None:
        await client.stop()

    logger.info(
        "Telegram client stopped for user %s",
        user_id,
    )


async def stop_all_clients() -> None:
    user_ids = list(
        set(_clients.keys())
        | set(_polling_tasks.keys())
        | set(_qr_tasks.keys())
    )

    if not user_ids:
        return

    await asyncio.gather(
        *[
            stop_user_client(user_id)
            for user_id in user_ids
        ],
        return_exceptions=True,
    )