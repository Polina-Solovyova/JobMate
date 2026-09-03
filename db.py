from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

from config import MONGO_DB_NAME, MONGO_URI


if not MONGO_URI:
    raise RuntimeError("MONGO_URI is not configured")


client = AsyncIOMotorClient(MONGO_URI)
db = client[MONGO_DB_NAME]

users_col = db["users"]
user_channels_col = db["user_channels"]
posts_col = db["posts"]
filters_col = db["filters"]


def utcnow() -> datetime:
    return datetime.utcnow()


def to_object_id(value: Any) -> Optional[ObjectId]:
    if isinstance(value, ObjectId):
        return value

    if value is None:
        return None

    try:
        return ObjectId(str(value))
    except Exception:
        return None


async def create_user(
    user_id: int,
    username: Optional[str] = None,
) -> bool:
    now = utcnow()

    result = await users_col.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "username": username,
                "updated_at": now,
            },
            "$setOnInsert": {
                "user_id": user_id,
                "created_at": now,
            },
        },
        upsert=True,
    )

    return (
        result.modified_count > 0
        or result.upserted_id is not None
    )


async def get_user(
    user_id: int,
) -> Optional[Dict[str, Any]]:
    return await users_col.find_one(
        {"user_id": user_id}
    )


async def get_user_ids_with_enabled_channels() -> List[int]:
    cursor = user_channels_col.find(
        {
            "enabled": True,
        },
        {
            "user_id": 1,
        },
    )

    user_ids = set()

    async for document in cursor:
        user_id = document.get("user_id")

        if user_id is not None:
            user_ids.add(int(user_id))

    return list(user_ids)

# ---------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------

async def add_user_channel(
    user_id: int,
    channel_id: int,
    channel_username: Optional[str] = None,
    channel_title: Optional[str] = None,
) -> bool:
    now = utcnow()

    result = await user_channels_col.update_one(
        {
            "user_id": user_id,
            "channel_id": channel_id,
        },
        {
            "$set": {
                "channel_username": channel_username,
                "channel_title": channel_title,
                "enabled": True,
                "updated_at": now,
            },
            "$setOnInsert": {
                "user_id": user_id,
                "channel_id": channel_id,
                "last_message_id": 0,
                "last_post_at": None,
                "added_at": now,
            },
        },
        upsert=True,
    )

    return (
        result.upserted_id is not None
        or result.modified_count > 0
    )


async def get_user_channels(
    user_id: int,
    enabled_only: bool = False,
) -> List[Dict[str, Any]]:
    query: Dict[str, Any] = {
        "user_id": user_id,
    }

    if enabled_only:
        query["enabled"] = True

    return await user_channels_col.find(
        query
    ).sort(
        "added_at",
        -1,
    ).to_list(length=None)


async def get_user_channel(
    user_id: int,
    channel_id: int,
) -> Optional[Dict[str, Any]]:
    return await user_channels_col.find_one(
        {
            "user_id": user_id,
            "channel_id": channel_id,
        }
    )


async def update_user_channel(
    user_id: int,
    channel_id: int,
    updates: Dict[str, Any],
) -> bool:
    if not updates:
        return False

    updates = dict(updates)
    updates["updated_at"] = utcnow()

    result = await user_channels_col.update_one(
        {
            "user_id": user_id,
            "channel_id": channel_id,
        },
        {
            "$set": updates,
        },
    )

    return result.matched_count > 0


async def toggle_user_channel(
    user_id: int,
    channel_id: int,
    enabled: bool,
) -> bool:
    return await update_user_channel(
        user_id=user_id,
        channel_id=channel_id,
        updates={"enabled": enabled},
    )


async def toggle_channel(
    user_id: int,
    channel_id: int,
    enabled: bool,
) -> bool:
    return await toggle_user_channel(
        user_id=user_id,
        channel_id=channel_id,
        enabled=enabled,
    )


async def delete_user_channel(
    user_id: int,
    channel_id: int,
) -> bool:
    result = await user_channels_col.delete_one(
        {
            "user_id": user_id,
            "channel_id": channel_id,
        }
    )

    return result.deleted_count > 0


async def delete_channel(
    user_id: int,
    channel_id: int,
) -> bool:
    return await delete_user_channel(
        user_id=user_id,
        channel_id=channel_id,
    )


async def update_channel_last_message(
    user_id: int,
    channel_id: int,
    last_message_id: int,
    last_post_at: Optional[datetime] = None,
) -> bool:
    updates: Dict[str, Any] = {
        "last_message_id": last_message_id,
        "updated_at": utcnow(),
    }

    if last_post_at is not None:
        updates["last_post_at"] = last_post_at

    result = await user_channels_col.update_one(
        {
            "user_id": user_id,
            "channel_id": channel_id,
        },
        {
            "$set": updates,
        },
    )

    return result.matched_count > 0


# ---------------------------------------------------------------------
# Posts
# ---------------------------------------------------------------------

async def get_post(
    user_id: int,
    channel_id: int,
    message_id: int,
) -> Optional[Dict[str, Any]]:
    return await posts_col.find_one(
        {
            "user_id": user_id,
            "channel_id": channel_id,
            "message_id": message_id,
        }
    )


async def save_post(
    user_id: int,
    channel_id: int,
    message_id: int,
    text: Optional[str],
    posted_at: Optional[datetime],
    channel_username: Optional[str] = None,
    channel_title: Optional[str] = None,
    has_media: bool = False,
) -> bool:
    now = utcnow()

    result = await posts_col.update_one(
        {
            "user_id": user_id,
            "channel_id": channel_id,
            "message_id": message_id,
        },
        {
            "$set": {
                "text": text,
                "posted_at": posted_at,
                "channel_username": channel_username,
                "channel_title": channel_title,
                "has_media": has_media,
                "updated_at": now,
            },
            "$setOnInsert": {
                "user_id": user_id,
                "channel_id": channel_id,
                "message_id": message_id,
                "created_at": now,
                "processed": False,
                "processed_at": None,
                "is_vacancy": None,
                "vacancy_data": None,
                "processing_error": None,
            },
        },
        upsert=True,
    )

    return (
        result.upserted_id is not None
        or result.modified_count > 0
    )


async def mark_post_processed(
    user_id: int,
    channel_id: int,
    message_id: int,
    is_vacancy: bool,
    vacancy_data: Optional[Dict[str, Any]] = None,
) -> bool:
    result = await posts_col.update_one(
        {
            "user_id": user_id,
            "channel_id": channel_id,
            "message_id": message_id,
        },
        {
            "$set": {
                "processed": True,
                "processed_at": utcnow(),
                "is_vacancy": is_vacancy,
                "vacancy_data": vacancy_data,
                "processing_error": None,
            }
        },
    )

    return result.matched_count > 0


async def mark_post_processing_error(
    user_id: int,
    channel_id: int,
    message_id: int,
    error: str,
) -> bool:
    result = await posts_col.update_one(
        {
            "user_id": user_id,
            "channel_id": channel_id,
            "message_id": message_id,
        },
        {
            "$set": {
                "processing_error": error[:2000],
                "updated_at": utcnow(),
            }
        },
    )

    return result.matched_count > 0


async def update_post_vacancy_status(
    user_id: int,
    channel_id: int,
    message_id: int,
    is_vacancy: bool,
    vacancy_data: Optional[Dict[str, Any]] = None,
) -> bool:
    return await mark_post_processed(
        user_id=user_id,
        channel_id=channel_id,
        message_id=message_id,
        is_vacancy=is_vacancy,
        vacancy_data=vacancy_data,
    )


# ---------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------

async def add_filter(
    user_id: int,
    name: str,
    query: str,
    required: Optional[List[str]] = None,
    optional: Optional[List[str]] = None,
    excluded: Optional[List[str]] = None,
    location: Optional[str] = None,
    experience: Optional[str] = None,
    enabled: bool = True,
) -> ObjectId:
    now = utcnow()

    document = {
        "user_id": user_id,
        "name": name,
        "query": query,
        "required": required or [],
        "optional": optional or [],
        "excluded": excluded or [],
        "location": location,
        "experience": experience,
        "enabled": enabled,
        "created_at": now,
        "updated_at": now,
    }

    result = await filters_col.insert_one(document)

    return result.inserted_id


async def get_filters(
    user_id: int,
    enabled_only: bool = False,
) -> List[Dict[str, Any]]:
    query: Dict[str, Any] = {
        "user_id": user_id,
    }

    if enabled_only:
        query["enabled"] = True

    return await filters_col.find(
        query
    ).sort(
        "created_at",
        -1,
    ).to_list(length=None)


async def get_user_filters(
    user_id: int,
    enabled_only: bool = False,
) -> List[Dict[str, Any]]:
    return await get_filters(
        user_id=user_id,
        enabled_only=enabled_only,
    )


async def get_filter(
    user_id: int,
    filter_id: Any,
) -> Optional[Dict[str, Any]]:
    object_id = to_object_id(filter_id)

    if object_id is None:
        return None

    return await filters_col.find_one(
        {
            "_id": object_id,
            "user_id": user_id,
        }
    )


async def update_filter(
    user_id: int,
    filter_id: Any,
    updates: Dict[str, Any],
) -> bool:
    object_id = to_object_id(filter_id)

    if object_id is None or not updates:
        return False

    updates = dict(updates)
    updates["updated_at"] = utcnow()

    result = await filters_col.update_one(
        {
            "_id": object_id,
            "user_id": user_id,
        },
        {
            "$set": updates,
        },
    )

    return result.matched_count > 0


async def toggle_filter(
    user_id: int,
    filter_id: Any,
    enabled: bool,
) -> bool:
    return await update_filter(
        user_id=user_id,
        filter_id=filter_id,
        updates={"enabled": enabled},
    )


async def delete_filter(
    user_id: int,
    filter_id: Any,
) -> bool:
    object_id = to_object_id(filter_id)

    if object_id is None:
        return False

    result = await filters_col.delete_one(
        {
            "_id": object_id,
            "user_id": user_id,
        }
    )

    return result.deleted_count > 0


# ---------------------------------------------------------------------
# Indexes
# ---------------------------------------------------------------------

async def create_indexes() -> None:
    await users_col.create_index(
        [("user_id", 1)],
        unique=True,
        name="users_user_id_unique",
    )

    await user_channels_col.create_index(
        [
            ("user_id", 1),
            ("channel_id", 1),
        ],
        unique=True,
        name="user_channels_user_channel_unique",
    )

    await user_channels_col.create_index(
        [
            ("user_id", 1),
            ("enabled", 1),
        ],
        name="user_channels_user_enabled",
    )

    await posts_col.create_index(
        [
            ("user_id", 1),
            ("channel_id", 1),
            ("message_id", 1),
        ],
        unique=True,
        name="posts_user_channel_message_unique",
    )

    await posts_col.create_index(
        [
            ("user_id", 1),
            ("processed", 1),
            ("created_at", 1),
        ],
        name="posts_user_processing_queue",
    )

    await filters_col.create_index(
        [
            ("user_id", 1),
            ("created_at", -1),
        ],
        name="filters_user_created",
    )

    await filters_col.create_index(
        [
            ("user_id", 1),
            ("enabled", 1),
        ],
        name="filters_user_enabled",
    )