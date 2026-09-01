import os

from dotenv import load_dotenv


load_dotenv()


def _required_env(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise RuntimeError(
            f"{name} is not configured"
        )

    return value


BOT_TOKEN = _required_env(
    "BOT_TOKEN"
)

MONGO_URI = _required_env(
    "MONGO_URI"
)

try:
    TELEGRAM_API_ID = int(
        _required_env(
            "TELEGRAM_API_ID"
        )
    )
except ValueError as exc:
    raise RuntimeError(
        "TELEGRAM_API_ID must be an integer"
    ) from exc


TELEGRAM_API_HASH = _required_env(
    "TELEGRAM_API_HASH"
)

TELEGRAM_SESSION_NAME = os.getenv(
    "TELEGRAM_SESSION_NAME",
    "user_session",
).strip() or "user_session"


MONGO_DB_NAME = (
    os.getenv(
        "MONGO_DB_NAME",
        "jobmate",
    ).strip()
    or "jobmate"
)
