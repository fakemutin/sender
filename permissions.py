from collections.abc import AsyncIterator
from dataclasses import dataclass

from telethon import TelegramClient
from telethon.tl.types import Channel, User

from config import AccountSettings


@dataclass
class ChatPermissionInfo:
    chat_id: int
    title: str
    username: str | None
    allowed: bool
    reason: str


def _normalize_username(username: str | None) -> str | None:
    if not username:
        return None
    return username.lower().lstrip("@")


async def inspect_chat_permissions(
    client: TelegramClient,
    dialog,
    *,
    require_admin: bool,
    allowed_chats: frozenset[str],
) -> ChatPermissionInfo:
    entity = dialog.entity
    chat_id = dialog.id
    title = dialog.title or dialog.name or str(chat_id)
    username = _normalize_username(getattr(entity, "username", None))

    if isinstance(entity, User):
        return ChatPermissionInfo(chat_id, title, username, False, "личный чат пропускается")

    if allowed_chats:
        id_token = str(chat_id)
        username_token = username or ""
        if id_token not in allowed_chats and username_token not in allowed_chats:
            return ChatPermissionInfo(
                chat_id, title, username, False, "не в списке ALLOWED_CHATS"
            )

    try:
        permissions = await client.get_permissions(entity, "me")
    except Exception as exc:
        return ChatPermissionInfo(
            chat_id, title, username, False, f"не удалось проверить права: {exc}"
        )

    is_creator = bool(getattr(permissions, "is_creator", False))
    is_admin = bool(getattr(permissions, "is_admin", False))

    if isinstance(entity, Channel) and getattr(entity, "broadcast", False):
        if is_creator or (is_admin and getattr(permissions, "post_messages", False)):
            return ChatPermissionInfo(chat_id, title, username, True, "админ канала")

        if require_admin:
            return ChatPermissionInfo(
                chat_id, title, username, False, "нет прав публикации в канале"
            )

        return ChatPermissionInfo(
            chat_id, title, username, False, "в канал можно писать только будучи админом"
        )

    if is_creator:
        return ChatPermissionInfo(chat_id, title, username, True, "создатель группы")

    if is_admin and getattr(permissions, "send_messages", False):
        return ChatPermissionInfo(chat_id, title, username, True, "админ группы")

    if require_admin:
        return ChatPermissionInfo(
            chat_id, title, username, False, "нужны права админа (REQUIRE_ADMIN=true)"
        )

    if getattr(permissions, "send_messages", False):
        return ChatPermissionInfo(chat_id, title, username, True, "разрешена отправка сообщений")

    return ChatPermissionInfo(chat_id, title, username, False, "отправка сообщений запрещена")


async def iter_allowed_chats(
    client: TelegramClient,
    settings: AccountSettings,
) -> AsyncIterator[ChatPermissionInfo]:
    async for dialog in client.iter_dialogs():
        if not (dialog.is_group or dialog.is_channel):
            continue

        info = await inspect_chat_permissions(
            client,
            dialog,
            require_admin=settings.require_admin,
            allowed_chats=settings.allowed_chats,
        )
        if info.allowed:
            yield info
