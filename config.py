import os

from dotenv import load_dotenv


load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", "0"))
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")

TELEGRAM_SESSION_NAME = os.getenv(
    "TELEGRAM_SESSION_NAME",
    "user_session",
)

MONGO_DB_NAME = os.getenv(
    "MONGO_DB_NAME",
    "jobmate",
)