import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from telethon import TelegramClient
from telethon.errors import (
    ChannelPrivateError,
    ChatAdminRequiredError,
    ChatWriteForbiddenError,
    FloodWaitError,
    PeerIdInvalidError,
    RPCError,
    UserBannedInChannelError,
    UserNotParticipantError,
)

from blocked_chats import block_chat, is_blocked
from chat_checker import should_block_error
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


def _handle_send_failure(
    chat: ChatPermissionInfo,
    account_name: str,
    detail: str,
    exc: Exception | None = None,
) -> None:
    reason = detail
    if exc and should_block_error(exc):
        reason = str(exc)
    if (exc and should_block_error(exc)) or should_block_error(Exception(detail)):
        block_chat(chat.chat_id, chat.username, reason, account=account_name)


async def send_to_chat(
    client: TelegramClient,
    chat: ChatPermissionInfo,
    message: Any,
    account_name: str,
) -> tuple[bool, str]:
    if is_blocked(chat.chat_id, chat.username, account_name):
        return False, "в блок-листе"

    try:
        await client.send_message(chat.chat_id, message)
        return True, "отправлено"
    except FloodWaitError as exc:
        wait_seconds = exc.seconds + 2
        logger.warning("FloodWait %ss для чата %s", exc.seconds, chat.chat_id)
        await asyncio.sleep(wait_seconds)
        try:
            await client.send_message(chat.chat_id, message)
            return True, "отправлено после FloodWait"
        except RPCError as retry_exc:
            _handle_send_failure(chat, account_name, str(retry_exc), retry_exc)
            return False, f"ошибка после FloodWait: {retry_exc}"
    except RPCError as exc:
        if should_block_error(exc):
            _handle_send_failure(chat, account_name, str(exc), exc)
        return False, str(exc)


async def run_broadcast_cycle(client: TelegramClient, settings: AccountSettings) -> CycleStats:
    stats = CycleStats()
    source_message = await fetch_source_message(client, settings)
    if not source_message:
        return stats

    sent_any = False
    async for chat in iter_allowed_chats(client, settings):
        if is_blocked(chat.chat_id, chat.username, settings.name):
            stats.skipped += 1
            continue

        success, detail = await send_to_chat(client, chat, source_message, settings.name)
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
        "[%s] Цикл: отправлено %s, ошибок %s, пропущено (блок) %s",
        settings.name,
        stats.sent,
        stats.failed,
        stats.skipped,
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
