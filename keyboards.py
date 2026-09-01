from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard():
    """Главное меню."""
    keyboard = [
        [InlineKeyboardButton("📢 Мои каналы", callback_data="my_channels")],
        [InlineKeyboardButton("🔎 Мои фильтры", callback_data="my_filters")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
    ]
    return InlineKeyboardMarkup(keyboard)


def channels_list_keyboard(channels):
    """
    Клавиатура для списка каналов.
    channels: список словарей с полями id, title, username, enabled
    """
    keyboard = []
    for ch in channels:
        status = "🟢" if ch.get("enabled", True) else "⏸"
        button_text = f"{status} {ch['title']}"
        callback_data = f"channel_{ch['channel_id']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    keyboard.append([InlineKeyboardButton("➕ Добавить канал", callback_data="add_channel")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)


def channel_actions_keyboard(channel_id: int, is_enabled: bool):
    """Клавиатура действий для конкретного канала."""
    status_text = "⏸ Пауза" if is_enabled else "▶️ Возобновить"
    status_callback = f"toggle_{channel_id}"
    keyboard = [
        [InlineKeyboardButton(status_text, callback_data=status_callback)],
        [InlineKeyboardButton("🔎 Вакансии из канала", callback_data=f"vacancies_{channel_id}")],
        [InlineKeyboardButton("🔔 Уведомления", callback_data=f"notify_{channel_id}")],
        [InlineKeyboardButton("🗑 Удалить", callback_data=f"delete_{channel_id}")],
        [InlineKeyboardButton("🔙 Назад", callback_data="my_channels")],
    ]
    return InlineKeyboardMarkup(keyboard)


def confirm_add_channel_keyboard(channel_info):
    """Клавиатура подтверждения добавления канала."""
    keyboard = [
        [InlineKeyboardButton("✅ Добавить канал", callback_data=f"confirm_add_{channel_info['id']}")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_add_channel")],
    ]
    return InlineKeyboardMarkup(keyboard)


def filters_list_keyboard(filters):
    """Клавиатура списка фильтров."""
    keyboard = []
    for f in filters:
        # f содержит _id, filter_data (name), enabled
        status = "🟢" if f.get("enabled", True) else "⏸"
        name = f.get("filter_data", {}).get("name", "Без названия")
        button_text = f"{status} {name}"
        callback_data = f"filter_{f['_id']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    keyboard.append([InlineKeyboardButton("➕ Новый поиск", callback_data="add_filter")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)


def filter_actions_keyboard(filter_id: str, is_enabled: bool):
    """Клавиатура действий для конкретного фильтра."""
    status_text = "⏸ Пауза" if is_enabled else "▶️ Возобновить"
    status_callback = f"toggle_filter_{filter_id}"
    keyboard = [
        [InlineKeyboardButton(status_text, callback_data=status_callback)],
        [InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit_filter_{filter_id}")],
        [InlineKeyboardButton("🗑 Удалить", callback_data=f"delete_filter_{filter_id}")],
        [InlineKeyboardButton("🔙 Назад", callback_data="my_filters")],
    ]
    return InlineKeyboardMarkup(keyboard)


def vacancy_card_keyboard(post_link: str, channel_username: str = None):
    """Клавиатура для карточки вакансии."""
    buttons = []
    if post_link:
        buttons.append(InlineKeyboardButton("📄 Открыть пост", url=post_link))
    if channel_username:
        buttons.append(InlineKeyboardButton("📢 Перейти в канал", url=f"https://t.me/{channel_username.lstrip('@')}"))
    buttons.append(InlineKeyboardButton("👍 Полезно", callback_data="feedback_positive"))
    buttons.append(InlineKeyboardButton("👎 Не подходит", callback_data="feedback_negative"))
    return InlineKeyboardMarkup([buttons])  # все в одной строке


# Добавить в keyboards.py

def filters_list_keyboard(filters):
    """Клавиатура списка фильтров."""
    keyboard = []
    for f in filters:
        status = "🟢" if f.get("enabled", True) else "⏸"
        name = f.get("filter_data", {}).get("name", "Без названия")
        button_text = f"{status} {name}"
        callback_data = f"filter_{f['_id']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    keyboard.append([InlineKeyboardButton("➕ Новый поиск", callback_data="add_filter")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)


def filter_actions_keyboard(filter_id: str, is_enabled: bool):
    """Клавиатура действий для конкретного фильтра."""
    status_text = "⏸ Пауза" if is_enabled else "▶️ Возобновить"
    status_callback = f"toggle_filter_{filter_id}"
    keyboard = [
        [InlineKeyboardButton(status_text, callback_data=status_callback)],
        [InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit_filter_{filter_id}")],  # пока заглушка
        [InlineKeyboardButton("🗑 Удалить", callback_data=f"delete_filter_{filter_id}")],
        [InlineKeyboardButton("🔙 Назад", callback_data="my_filters")],
    ]
    return InlineKeyboardMarkup(keyboard)