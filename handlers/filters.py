from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from db import (
    add_filter,
    delete_filter,
    get_filter,
    get_filters,
    toggle_filter,
    update_filter,
)

from filters import parse_query_to_filter

from keyboards import (
    filter_actions_keyboard,
    filters_list_keyboard,
    main_menu_keyboard,
)


WAITING_FILTER_QUERY = 1
WAITING_FILTER_EDIT = 2


async def my_filters_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id

    filters_data = await get_filters(
        user_id
    )

    await query.edit_message_text(
        "Ваши фильтры:",
        reply_markup=filters_list_keyboard(
            filters_data
        ),
    )


async def add_filter_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    context.user_data.pop(
        "editing_filter_id",
        None,
    )

    await query.edit_message_text(
        "Введите описание вакансии для фильтра.\n\n"
        "Например:\n"
        "Python developer в Риге, удалённо, от 2000 EUR"
    )

    return WAITING_FILTER_QUERY


async def cancel_filter_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    context.user_data.pop(
        "editing_filter_id",
        None,
    )

    await query.edit_message_text(
        "Действие отменено.",
        reply_markup=main_menu_keyboard(),
    )

    return ConversationHandler.END


async def filter_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message or not update.message.text:
        return ConversationHandler.END

    user_id = update.effective_user.id
    text = update.message.text.strip()

    if not text:
        await update.message.reply_text(
            "Введите непустой запрос."
        )
        return WAITING_FILTER_QUERY

    editing_filter_id = context.user_data.get(
        "editing_filter_id"
    )

    try:
        parsed = parse_query_to_filter(
            text
        )

    except Exception:
        await update.message.reply_text(
            "Не удалось разобрать запрос. "
            "Попробуйте сформулировать его проще."
        )

        return (
            WAITING_FILTER_EDIT
            if editing_filter_id
            else WAITING_FILTER_QUERY
        )

    if not parsed:
        await update.message.reply_text(
            "Не удалось создать фильтр из этого запроса."
        )

        return (
            WAITING_FILTER_EDIT
            if editing_filter_id
            else WAITING_FILTER_QUERY
        )

    name = parsed.get("name") or text[:80]

    filter_updates = {
        "name": name,
        "query": text,
        "required": parsed.get(
            "required",
            [],
        ),
        "optional": parsed.get(
            "optional",
            [],
        ),
        "excluded": parsed.get(
            "excluded",
            [],
        ),
        "location": parsed.get(
            "location"
        ),
        "experience": parsed.get(
            "experience"
        ),
    }

    if editing_filter_id:

        existing_filter = await get_filter(
            user_id=user_id,
            filter_id=editing_filter_id,
        )

        if not existing_filter:
            context.user_data.pop(
                "editing_filter_id",
                None,
            )

            await update.message.reply_text(
                "Фильтр не найден.",
                reply_markup=main_menu_keyboard(),
            )

            return ConversationHandler.END

        updated = await update_filter(
            user_id=user_id,
            filter_id=editing_filter_id,
            updates=filter_updates,
        )

        context.user_data.pop(
            "editing_filter_id",
            None,
        )

        if not updated:
            await update.message.reply_text(
                "Не удалось обновить фильтр.",
                reply_markup=main_menu_keyboard(),
            )
            return ConversationHandler.END

        await update.message.reply_text(
            "Фильтр обновлён.",
            reply_markup=main_menu_keyboard(),
        )

        return ConversationHandler.END

    await add_filter(
        user_id=user_id,
        name=name,
        query=text,
        required=parsed.get(
            "required",
            [],
        ),
        optional=parsed.get(
            "optional",
            [],
        ),
        excluded=parsed.get(
            "excluded",
            [],
        ),
        location=parsed.get(
            "location"
        ),
        experience=parsed.get(
            "experience"
        ),
        enabled=True,
    )

    await update.message.reply_text(
        f"Фильтр «{name}» создан.",
        reply_markup=main_menu_keyboard(),
    )

    return ConversationHandler.END


async def filter_detail_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id

    filter_id = query.data.replace(
        "filter_",
        "",
        1,
    )

    filter_data = await get_filter(
        user_id=user_id,
        filter_id=filter_id,
    )

    if not filter_data:
        await query.edit_message_text(
            "Фильтр не найден.",
            reply_markup=main_menu_keyboard(),
        )
        return

    name = filter_data.get(
        "name",
        "Без названия",
    )

    original_query = filter_data.get(
        "query",
        "",
    )

    enabled = filter_data.get(
        "enabled",
        True,
    )

    required = filter_data.get(
        "required",
        [],
    )

    optional = filter_data.get(
        "optional",
        [],
    )

    excluded = filter_data.get(
        "excluded",
        [],
    )

    location = filter_data.get(
        "location"
    )

    experience = filter_data.get(
        "experience"
    )

    lines = [
        f"Фильтр: {name}",
        "",
        f"Статус: {'включён' if enabled else 'выключен'}",
        f"Запрос: {original_query}",
    ]

    if required:
        lines.extend(
            [
                "",
                "Обязательное:",
                ", ".join(required),
            ]
        )

    if optional:
        lines.extend(
            [
                "",
                "Дополнительно:",
                ", ".join(optional),
            ]
        )

    if excluded:
        lines.extend(
            [
                "",
                "Исключить:",
                ", ".join(excluded),
            ]
        )

    if location:
        lines.extend(
            [
                "",
                f"Локация: {location}",
            ]
        )

    if experience:
        lines.extend(
            [
                "",
                f"Опыт: {experience}",
            ]
        )

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=filter_actions_keyboard(
            filter_id=str(
                filter_data["_id"]
            ),
            enabled=enabled,
        ),
    )


async def filter_action_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    data = query.data or ""

    if data.startswith("toggle_filter_"):
        action = "toggle"
        filter_id = data.replace(
            "toggle_filter_",
            "",
            1,
        )

    elif data.startswith("delete_filter_"):
        action = "delete"
        filter_id = data.replace(
            "delete_filter_",
            "",
            1,
        )

    elif data.startswith("confirm_delete_"):
        action = "confirm_delete"
        filter_id = data.replace(
            "confirm_delete_",
            "",
            1,
        )

    elif data.startswith("edit_filter_"):
        action = "edit"
        filter_id = data.replace(
            "edit_filter_",
            "",
            1,
        )

    else:
        return

    filter_data = await get_filter(
        user_id=user_id,
        filter_id=filter_id,
    )

    if not filter_data:
        await query.edit_message_text(
            "Фильтр не найден.",
            reply_markup=main_menu_keyboard(),
        )
        return

    if action == "toggle":

        enabled = not filter_data.get(
            "enabled",
            True,
        )

        updated = await toggle_filter(
            user_id=user_id,
            filter_id=filter_id,
            enabled=enabled,
        )

        if not updated:
            await query.edit_message_text(
                "Не удалось изменить статус фильтра.",
                reply_markup=main_menu_keyboard(),
            )
            return

        await query.edit_message_text(
            "Фильтр включён."
            if enabled
            else "Фильтр выключен.",
            reply_markup=filter_actions_keyboard(
                filter_id=filter_id,
                enabled=enabled,
            ),
        )

        return

    if action == "delete":

        await query.edit_message_text(
            "Удалить этот фильтр?",
            reply_markup=filter_actions_keyboard(
                filter_id=filter_id,
                enabled=filter_data.get(
                    "enabled",
                    True,
                ),
                confirm_delete=True,
            ),
        )

        return

    if action == "confirm_delete":

        deleted = await delete_filter(
            user_id=user_id,
            filter_id=filter_id,
        )

        if deleted:
            await query.edit_message_text(
                "Фильтр удалён.",
                reply_markup=main_menu_keyboard(),
            )
        else:
            await query.edit_message_text(
                "Фильтр не найден.",
                reply_markup=main_menu_keyboard(),
            )

        return

    if action == "edit":

        context.user_data[
            "editing_filter_id"
        ] = filter_id

        await query.edit_message_text(
            "Введите новый запрос для фильтра.\n\n"
            "Текущий запрос:\n"
            f"{filter_data.get('query', '')}"
        )

        return WAITING_FILTER_EDIT