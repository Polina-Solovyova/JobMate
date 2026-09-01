import asyncio
import logging

from telegram_client import TelegramUserClient


logger = logging.getLogger(__name__)

_clients: dict[int, TelegramUserClient] = {}
_polling_tasks: dict[int, asyncio.Task] = {}


async def get_telegram_client(
    user_id: int,
) -> TelegramUserClient:
    client = _clients.get(user_id)

    if client is None:
        client = TelegramUserClient(user_id=user_id)
        _clients[user_id] = client

    return client


async def start_user_polling(
    user_id: int,
) -> bool:
    client = await get_telegram_client(user_id)

    if not await client.is_authorized():
        return False

    task = _polling_tasks.get(user_id)

    if task and not task.done():
        return True

    task = asyncio.create_task(
        client.start_polling()
    )

    _polling_tasks[user_id] = task

    logger.info(
        "Telegram polling started for user %s",
        user_id,
    )

    return True


async def stop_user_client(
    user_id: int,
):
    task = _polling_tasks.pop(user_id, None)

    if task:
        task.cancel()

        await asyncio.gather(
            task,
            return_exceptions=True,
        )

    client = _clients.pop(user_id, None)

    if client:
        await client.stop()


async def stop_all_clients():
    user_ids = list(_clients.keys())

    for user_id in user_ids:
        await stop_user_client(user_id)