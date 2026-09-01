from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Каналы",
                    callback_data="my_channels",
                ),
                InlineKeyboardButton(
                    "Фильтры",
                    callback_data="my_filters",
                ),
            ],
            [
                InlineKeyboardButton(
                    "Добавить канал",
                    callback_data="add_channel",
                ),
                InlineKeyboardButton(
                    "Добавить фильтр",
                    callback_data="add_filter",
                ),
            ],
            [
                InlineKeyboardButton(
                    "Настройки",
                    callback_data="settings",
                ),
            ],
        ]
    )


def filters_list_keyboard(filters):
    buttons = []

    for filter_data in filters:
        filter_id = str(filter_data["_id"])
        name = filter_data.get(
            "name",
            "Без названия",
        )

        enabled = filter_data.get(
            "enabled",
            True,
        )

        status = "✓" if enabled else "○"

        buttons.append(
            [
                InlineKeyboardButton(
                    f"{status} {name}",
                    callback_data=f"filter_{filter_id}",
                )
            ]
        )

    buttons.append(
        [
            InlineKeyboardButton(
                "Добавить фильтр",
                callback_data="add_filter",
            )
        ]
    )

    buttons.append(
        [
            InlineKeyboardButton(
                "Назад",
                callback_data="main_menu",
            )
        ]
    )

    return InlineKeyboardMarkup(buttons)


def filter_actions_keyboard(
    filter_id,
    enabled=True,
    confirm_delete=False,
):
    if confirm_delete:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "Да, удалить",
                        callback_data=(
                            f"confirm_delete_{filter_id}"
                        ),
                    ),
                    InlineKeyboardButton(
                        "Отмена",
                        callback_data=(
                            f"filter_{filter_id}"
                        ),
                    ),
                ]
            ]
        )

    toggle_text = (
        "Выключить"
        if enabled
        else "Включить"
    )

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Редактировать",
                    callback_data=(
                        f"edit_filter_{filter_id}"
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    toggle_text,
                    callback_data=(
                        f"toggle_filter_{filter_id}"
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    "Удалить",
                    callback_data=(
                        f"delete_filter_{filter_id}"
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    "Назад",
                    callback_data="my_filters",
                ),
            ],
        ]
    )


def channels_list_keyboard(channels):
    buttons = []

    for channel in channels:
        channel_id = channel["channel_id"]
        username = channel.get("username")
        title = channel.get("title")

        name = (
            f"@{username}"
            if username
            else title
            or str(channel_id)
        )

        enabled = channel.get(
            "enabled",
            True,
        )

        status = "✓" if enabled else "○"

        buttons.append(
            [
                InlineKeyboardButton(
                    f"{status} {name}",
                    callback_data=(
                        f"channel_{channel_id}"
                    ),
                )
            ]
        )

    buttons.append(
        [
            InlineKeyboardButton(
                "Добавить канал",
                callback_data="add_channel",
            )
        ]
    )

    buttons.append(
        [
            InlineKeyboardButton(
                "Назад",
                callback_data="main_menu",
            )
        ]
    )

    return InlineKeyboardMarkup(buttons)