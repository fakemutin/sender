import logging

from telethon import TelegramClient
from telethon.errors import (
    ChannelPrivateError,
    ChatAdminRequiredError,
    ChatWriteForbiddenError,
    PeerIdInvalidError,
    RPCError,
    UserBannedInChannelError,
    UserNotParticipantError,
)

from blocked_chats import block_chat, is_blocked
from config import AccountSettings
from permissions import ChatPermissionInfo, effective_allowed_chats, inspect_chat_permissions, iter_allowed_chats

logger = logging.getLogger(__name__)

PERMANENT_ERRORS = (
    ChatWriteForbiddenError,
    UserBannedInChannelError,
    ChannelPrivateError,
    ChatAdminRequiredError,
    UserNotParticipantError,
    PeerIdInvalidError,
)


def should_block_error(exc: Exception) -> bool:
    if isinstance(exc, PERMANENT_ERRORS):
        return True
    text = str(exc).lower()
    permanent_markers = (
        "can't write",
        "not a participant",
        "private",
        "banned",
        "forbidden",
        "invalid peer",
        "chat_restricted",
        "allow_payment_required",
    )
    return any(marker in text for marker in permanent_markers)


async def check_single_chat(
    client: TelegramClient,
    settings: AccountSettings,
    chat: ChatPermissionInfo,
) -> tuple[bool, str]:
    if is_blocked(chat.chat_id, chat.username, settings.name):
        return False, "в блок-листе"

    try:
        entity = await client.get_entity(chat.chat_id)
        permissions = await client.get_permissions(entity, "me")
        if not getattr(permissions, "send_messages", False) and not (
            getattr(permissions, "is_admin", False)
            and getattr(permissions, "post_messages", False)
        ):
            if settings.require_admin and not getattr(permissions, "is_admin", False):
                return False, "нет прав админа"
            if not getattr(permissions, "send_messages", False):
                return False, "отправка запрещена"
        return True, "ok"
    except Exception as exc:
        if should_block_error(exc):
            return False, str(exc)
        return False, f"ошибка проверки: {exc}"


async def check_allowed_list_tokens(
    client: TelegramClient,
    settings: AccountSettings,
) -> tuple[int, int, int]:
    allowed = await effective_allowed_chats(client, settings)
    if not allowed:
        return 0, 0, 0

    ok_count = 0
    bad_count = 0
    for token in allowed:
        label = token
        try:
            entity = await client.get_entity(token)
            chat_id = entity.id
            username = getattr(entity, "username", None)
            if is_blocked(chat_id, username, settings.name):
                bad_count += 1
                continue

            permissions = await client.get_permissions(entity, "me")
            can_send = getattr(permissions, "send_messages", False) or (
                getattr(permissions, "is_admin", False)
                and getattr(permissions, "post_messages", getattr(permissions, "send_messages", False))
            )
            if not can_send:
                reason = "нет прав на отправку"
                block_chat(chat_id, username, reason, account=settings.name)
                bad_count += 1
                logger.warning("[%s] ✗ %s — %s", settings.name, label, reason)
            else:
                ok_count += 1
                logger.info("[%s] ✓ %s — рабочий", settings.name, label)
        except Exception as exc:
            reason = str(exc)
            block_chat(0, token if not token.lstrip("-").isdigit() else None, reason, account=settings.name)
            bad_count += 1
            logger.warning("[%s] ✗ %s — %s", settings.name, label, reason)

    return ok_count, bad_count, ok_count + bad_count


async def filter_account_chats(client: TelegramClient, settings: AccountSettings) -> dict:
    stats = {"ok": 0, "bad": 0, "blocked_before": 0}

    list_ok, list_bad, _ = await check_allowed_list_tokens(client, settings)
    stats["ok"] += list_ok
    stats["bad"] += list_bad

    async for chat in iter_allowed_chats(client, settings):
        if is_blocked(chat.chat_id, chat.username, settings.name):
            stats["blocked_before"] += 1
            continue

        works, reason = await check_single_chat(client, settings, chat)
        label = chat.username or chat.title
        if works:
            stats["ok"] += 1
            logger.info("[%s] ✓ %s", settings.name, label)
        else:
            stats["bad"] += 1
            block_chat(chat.chat_id, chat.username, reason, account=settings.name)
            logger.warning("[%s] ✗ %s — %s", settings.name, label, reason)

    logger.info(
        "[%s] Фильтр: рабочих %s, мёртвых %s, уже в блоке %s",
        settings.name,
        stats["ok"],
        stats["bad"],
        stats["blocked_before"],
    )
    return stats
