import logging

from telegram import Update
from telegram.ext import ContextTypes

from db import (
    get_user_channels,
    get_user_filters,
)

from keyboards import main_menu_keyboard


logger = logging.getLogger(__name__)


async def settings_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if not query:
        return

    await query.answer()

    user_id = update.effective_user.id

    try:
        channels = await get_user_channels(
            user_id=user_id
        )

        filters_data = await get_user_filters(
            user_id=user_id,
            enabled_only=False,
        )

        enabled_channels = sum(
            1
            for channel in channels
            if channel.get(
                "enabled",
                True,
            )
        )

        enabled_filters = sum(
            1
            for filter_data in filters_data
            if filter_data.get(
                "enabled",
                True,
            )
        )

        text = (
            "Настройки\n"
            "\n"
            f"Каналы: {enabled_channels} "
            f"из {len(channels)} включено\n"
            f"Фильтры: {enabled_filters} "
            f"из {len(filters_data)} включено\n"
            "\n"
            "Сейчас настройки подключения и "
            "мониторинга управляются автоматически."
        )

        await query.edit_message_text(
            text,
            reply_markup=main_menu_keyboard(),
        )

    except Exception:
        logger.exception(
            "Failed to open settings for user %s",
            user_id,
        )

        await query.edit_message_text(
            "Не удалось открыть настройки.",
            reply_markup=main_menu_keyboard(),
        )