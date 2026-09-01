import logging

from telegram import Bot

from config import BOT_TOKEN


logger = logging.getLogger(__name__)


async def send_vacancy_notification(
    user_id: int,
    text: str,
    channel_title: str | None = None,
    channel_username: str | None = None,
    post_link: str | None = None,
    matched_filters: list[str] | None = None,
):
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN is not configured"
        )

    matched_filters = matched_filters or []

    channel_name = (
        channel_title
        or channel_username
        or "Неизвестный канал"
    )

    parts = [
        "Найдена подходящая вакансия.",
        "",
        f"Канал: {channel_name}",
    ]

    if matched_filters:
        parts.extend(
            [
                "",
                "Подходящие фильтры:",
                *[
                    f"• {name}"
                    for name in matched_filters
                ],
            ]
        )

    if text:
        parts.extend(
            [
                "",
                "Текст вакансии:",
                text,
            ]
        )

    if post_link:
        parts.extend(
            [
                "",
                f"Открыть пост: {post_link}",
            ]
        )

    message = "\n".join(parts)

    bot = Bot(token=BOT_TOKEN)

    try:
        await bot.send_message(
            chat_id=user_id,
            text=message,
            disable_web_page_preview=True,
        )

    except Exception:
        logger.exception(
            "Failed to send vacancy notification "
            "to user %s",
            user_id,
        )
        raise

    finally:
        await bot.shutdown()