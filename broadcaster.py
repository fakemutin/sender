import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from telethon import TelegramClient
from telethon.errors import (
    ChatWriteForbiddenError,
    FloodWaitError,
    RPCError,
    UserBannedInChannelError,
)

from config import AccountSettings
from permissions import ChatPermissionInfo, iter_allowed_chats

logger = logging.getLogger(__name__)


@dataclass
class CycleStats:
    sent: int = 0
    failed: int = 0
    skipped: int = 0


async def fetch_source_message(client: TelegramClient, settings: AccountSettings) -> Any | None:
    try:
        message = await client.get_messages(settings.source_chat, ids=settings.source_message_id)
    except RPCError as exc:
        logger.error("[%s] Не удалось получить сообщение: %s", settings.name, exc)
        return None

    if not message:
        logger.error(
            "[%s] Сообщение %s не найдено в %s",
            settings.name,
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
        logger.warning("FloodWait %ss для чата %s", exc.seconds, chat_id)
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


async def run_broadcast_cycle(client: TelegramClient, settings: AccountSettings) -> CycleStats:
    stats = CycleStats()
    source_message = await fetch_source_message(client, settings)
    if not source_message:
        return stats

    sent_any = False
    async for chat in iter_allowed_chats(client, settings):
        success, detail = await send_to_chat(client, chat.chat_id, source_message)
        label = chat.username or chat.title

        if success:
            stats.sent += 1
            logger.info("[%s] ✓ %s — %s", settings.name, label, detail)
        else:
            stats.failed += 1
            logger.warning("[%s] ✗ %s — %s", settings.name, label, detail)

        if sent_any:
            await asyncio.sleep(settings.delay_between_chats)
        sent_any = True

    if not sent_any:
        logger.warning("[%s] Нет чатов, куда разрешена отправка", settings.name)

    logger.info(
        "[%s] Цикл: отправлено %s, ошибок %s",
        settings.name,
        stats.sent,
        stats.failed,
    )
    return stats


async def list_allowed_chats(client: TelegramClient, settings: AccountSettings) -> int:
    count = 0
    print(f"\n=== {settings.name} ({settings.session_name}) ===")

    async for chat in iter_allowed_chats(client, settings):
        count += 1
        username = f"@{chat.username}" if chat.username else "—"
        print(f"  {chat.chat_id:>14}  {username:<24}  {chat.title}  ({chat.reason})")

    if count == 0:
        print("  Разрешённых чатов не найдено.")

    return count
