import os
import getpass
import asyncio

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from config import (
    TELEGRAM_API_ID,
    TELEGRAM_API_HASH,
    TELEGRAM_SESSION_NAME,
)

load_dotenv()


async def main():
    print("=== JobMate Telegram authorization ===")

    user_id = input("JobMate user ID: ").strip()
    phone = input("Telegram phone (+...): ").strip()

    session_dir = "sessions"
    os.makedirs(session_dir, exist_ok=True)

    session_path = os.path.join(
        session_dir,
        f"{TELEGRAM_SESSION_NAME}_{user_id}",
    )

    print(f"Session: {session_path}")

    client = TelegramClient(
        session_path,
        TELEGRAM_API_ID,
        TELEGRAM_API_HASH,
    )

    await client.connect()

    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"Already authorized: {me.id}")
        await client.disconnect()
        return

    print("Sending Telegram login code...")
    sent_code = await client.send_code_request(phone)

    code = input("Telegram login code: ").strip()

    try:
        await client.sign_in(
            phone=phone,
            code=code,
            phone_code_hash=sent_code.phone_code_hash,
        )

    except SessionPasswordNeededError:
        print("Telegram 2FA is enabled.")
        password = getpass.getpass("Telegram 2FA password: ")
        await client.sign_in(password=password)

    me = await client.get_me()

    print()
    print("=== AUTHORIZATION SUCCESSFUL ===")
    print(f"Telegram ID: {me.id}")
    print(f"Username: @{me.username}" if me.username else "Username: none")
    print(f"Session saved: {session_path}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())