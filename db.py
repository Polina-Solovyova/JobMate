from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")
client = AsyncIOMotorClient(MONGO_URI)
db = client["devradar"]

# Коллекции
users_col = db["users"]                     # информация о пользователях
user_channels_col = db["user_channels"]     # каналы, добавленные пользователем
posts_col = db["posts"]                     # посты (привязаны к пользователю)
filters_col = db["filters"]                 # персональные фильтры пользователя

# ---------- Пользователи ----------
async def get_user(user_id: int):
    return await users_col.find_one({"user_id": user_id})

async def create_user(user_id: int):
    await users_col.update_one(
        {"user_id": user_id},
        {"$setOnInsert": {
            "created_at": datetime.utcnow(),
            "settings": {
                "notifications": True,
                "notification_mode": "instant"
            }
        }},
        upsert=True
    )

async def update_user_settings(user_id: int, settings: dict):
    await users_col.update_one(
        {"user_id": user_id},
        {"$set": {"settings": settings}}
    )

# ---------- Каналы пользователя ----------
async def add_user_channel(user_id: int, channel_id: int, username: str, title: str):
    await user_channels_col.update_one(
        {"user_id": user_id, "channel_id": channel_id},
        {"$set": {
            "username": username,
            "title": title,
            "enabled": True,
            "added_at": datetime.utcnow(),
            "last_message_id": 0,
            "last_post_at": None
        }},
        upsert=True
    )

async def get_user_channels(user_id: int):
    cursor = user_channels_col.find({"user_id": user_id})
    return await cursor.to_list(length=None)

async def get_user_channel(user_id: int, channel_id: int):
    return await user_channels_col.find_one({"user_id": user_id, "channel_id": channel_id})

async def remove_user_channel(user_id: int, channel_id: int):
    await user_channels_col.delete_one({"user_id": user_id, "channel_id": channel_id})

async def update_channel_last_message(user_id: int, channel_id: int, message_id: int, posted_at: datetime):
    await user_channels_col.update_one(
        {"user_id": user_id, "channel_id": channel_id},
        {"$set": {"last_message_id": message_id, "last_post_at": posted_at}}
    )

async def set_channel_enabled(user_id: int, channel_id: int, enabled: bool):
    await user_channels_col.update_one(
        {"user_id": user_id, "channel_id": channel_id},
        {"$set": {"enabled": enabled}}
    )

# ---------- Посты ----------
async def save_post(user_id: int, channel_id: int, message_id: int, text: str, posted_at: datetime):
    await posts_col.update_one(
        {"user_id": user_id, "channel_id": channel_id, "message_id": message_id},
        {"$set": {
            "text": text,
            "posted_at": posted_at,
            "processed_at": datetime.utcnow(),
            "is_vacancy": None,
            "vacancy_data": None,
            "processed": False
        }},
        upsert=True
    )

async def get_post(user_id: int, channel_id: int, message_id: int):
    return await posts_col.find_one({"user_id": user_id, "channel_id": channel_id, "message_id": message_id})

async def update_post_vacancy_status(user_id: int, channel_id: int, message_id: int, is_vacancy: bool, vacancy_data=None):
    await posts_col.update_one(
        {"user_id": user_id, "channel_id": channel_id, "message_id": message_id},
        {"$set": {
            "is_vacancy": is_vacancy,
            "vacancy_data": vacancy_data,
            "processed": True,
            "processed_at": datetime.utcnow()
        }}
    )

# ---------- Фильтры ----------
async def add_filter(user_id: int, filter_data: dict):
    # filter_data: { "name": str, "keywords": [...], "and_conditions": [...], "or_conditions": [...], "not_conditions": [...] }
    await filters_col.insert_one({
        "user_id": user_id,
        "filter_data": filter_data,
        "enabled": True,
        "created_at": datetime.utcnow()
    })

async def get_user_filters(user_id: int):
    cursor = filters_col.find({"user_id": user_id})
    return await cursor.to_list(length=None)

async def update_filter(filter_id: str, updates: dict):
    await filters_col.update_one({"_id": filter_id}, {"$set": updates})

async def delete_filter(filter_id: str):
    await filters_col.delete_one({"_id": filter_id})