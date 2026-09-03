from telegram import Update
from telegram.ext import ContextTypes

from db import create_user
from telegram_clients import get_telegram_client, start_user_polling


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if user is None or update.message is None:
        return

    await create_user(
        user_id=user.id,
        username=user.username,
    )

    client = await get_telegram_client(user.id)

    if await client.is_authorized():
        started = await start_user_polling(user.id)

        if started:
            await update.message.reply_text(
                "Бот подключён и начал отслеживать вакансии."
            )
        else:
            await update.message.reply_text(
                "Бот уже отслеживает вакансии."
            )

        return

    await update.message.reply_text(
        "Для начала работы нужно подключить Telegram-аккаунт."
    )