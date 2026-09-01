from telegram import Update
from telegram.ext import ContextTypes
from keyboards import main_menu_keyboard

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        "Я — твой персональный помощник по поиску вакансий в Telegram.\n"
        "Я отслеживаю выбранные тобой каналы и присылаю только подходящие вакансии.\n\n"
        "Используй кнопки ниже для управления:",
        reply_markup=main_menu_keyboard()
    )