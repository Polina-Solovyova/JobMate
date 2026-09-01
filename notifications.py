import logging
from typing import Optional

from telegram import Bot

from config import BOT_TOKEN


logger = logging.getLogger(__name__)

TELEGRAM_MESSAGE_LIMIT = 4096


def _build_post_link(
    channel_username: Optional[str],
    message_id: Optional[int],
) -> Optional[str]:
    if not channel_username or not message_id:
        return None

    username = channel_username.lstrip("@").strip()

    if not username:
        return None

    return (
        f"https://t.me/{username}/{int(message_id)}"
    )


def _truncate_text(
    text: str,
    limit: int = TELEGRAM_MESSAGE_LIMIT,
) -> str:
    if len(text) <= limit:
        return text

    suffix = "\n\n…текст сокращён."

    return (
        text[: limit - len(suffix)]
        + suffix
    )


async def send_vacancy_notification(
    user_id: int,
    text: str,
    channel_title: Optional[str] = None,
    channel_username: Optional[str] = None,
    post_link: Optional[str] = None,
    matched_filters: Optional[list[str]] = None,
) -> None:
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

    if post_link is None:
        post_link = _build_post_link(
            channel_username=channel_username,
            message_id=None,
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

    message = _truncate_text(
        "\n".join(parts)
    )

    bot = Bot(
        token=BOT_TOKEN
    )

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
