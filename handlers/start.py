from telegram import Update
from telegram.ext import ContextTypes

from db import create_user
from keyboards import main_menu_keyboard
from telegram_clients import (
    get_telegram_client,
    start_user_polling,
)


async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.effective_user is None:
        return

    if update.message is None:
        return

    user = update.effective_user

    await create_user(
        user_id=user.id,
        username=user.username,
    )

    client = await get_telegram_client(
        user.id
    )

    if await client.is_authorized():
        await start_user_polling(
            user.id
        )

        await update.message.reply_text(
            "Telegram-аккаунт подключён.\n\n"
            "Выберите действие:",
            reply_markup=main_menu_keyboard(),
        )
        return

    await update.message.reply_text(
        "Добро пожаловать в JobMate.\n\n"
        "Я отслеживаю выбранные Telegram-каналы "
        "и отправляю вакансии, которые соответствуют "
        "вашим фильтрам.\n\n"
        "Для начала подключите Telegram-аккаунт "
        "командой /connect.",
        reply_markup=main_menu_keyboard(),
    )