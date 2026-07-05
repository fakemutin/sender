import asyncio
import logging
from typing import Any

from telethon import TelegramClient
from telethon.errors import (
    ChatWriteForbiddenError,
    FloodWaitError,
    RPCError,
    UserBannedInChannelError,
)

from config import Settings
from permissions import ChatPermissionInfo, collect_allowed_chats

logger = logging.getLogger(__name__)


async def fetch_source_message(client: TelegramClient, settings: Settings) -> Any | None:
    if not settings.source_chat or not settings.source_message_id:
        logger.error("Укажите SOURCE_CHAT и SOURCE_MESSAGE_ID в .env")
        return None

    try:
        message = await client.get_messages(settings.source_chat, ids=settings.source_message_id)
    except RPCError as exc:
        logger.error("Не удалось получить исходное сообщение: %s", exc)
        return None

    if not message:
        logger.error(
            "Сообщение %s не найдено в %s",
            settings.source_message_id,
            settings.source_chat,
        )
        return None

    return message


async def send_to_chat(client: TelegramClient, chat_id: int, message: Any) -> tuple[bool, str]:
    try:
        await client.send_message(chat_id, message)
        return True, "отправлено"
    except FloodWaitError as exc:
        wait_seconds = exc.seconds + 2
        logger.warning("FloodWait %ss для чата %s, ждём...", exc.seconds, chat_id)
        await asyncio.sleep(wait_seconds)
        try:
            await client.send_message(chat_id, message)
            return True, "отправлено после FloodWait"
        except RPCError as retry_exc:
            return False, f"ошибка после FloodWait: {retry_exc}"
    except (ChatWriteForbiddenError, UserBannedInChannelError):
        return False, "нет прав на отправку"
    except RPCError as exc:
        return False, str(exc)


async def run_broadcast_cycle(client: TelegramClient, settings: Settings) -> None:
    source_message = await fetch_source_message(client, settings)
    if not source_message:
        return

    allowed_chats = await collect_allowed_chats(
        client,
        require_admin=settings.require_admin,
        allowed_chats=settings.allowed_chats,
    )

    if not allowed_chats:
        logger.warning("Нет чатов, куда разрешена отправка")
        return

    logger.info("Найдено %s разрешённых чатов", len(allowed_chats))

    for index, chat in enumerate(allowed_chats):
        success, detail = await send_to_chat(client, chat.chat_id, source_message)
        label = chat.username or chat.title
        if success:
            logger.info("✓ [%s] %s — %s", chat.chat_id, label, detail)
        else:
            logger.warning("✗ [%s] %s — %s", chat.chat_id, label, detail)

        if index < len(allowed_chats) - 1:
            await asyncio.sleep(settings.delay_between_chats)


async def list_allowed_chats(client: TelegramClient, settings: Settings) -> None:
    chats = await collect_allowed_chats(
        client,
        require_admin=settings.require_admin,
        allowed_chats=settings.allowed_chats,
    )

    if not chats:
        print("Разрешённых чатов не найдено.")
        return

    print(f"Разрешённых чатов: {len(chats)}\n")
    for chat in chats:
        username = f"@{chat.username}" if chat.username else "—"
        print(f"  {chat.chat_id:>14}  {username:<24}  {chat.title}  ({chat.reason})")
