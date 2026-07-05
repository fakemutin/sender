import logging
import re

from telethon import TelegramClient, events
from telethon.tl.functions.channels import JoinChannelRequest

from group_help import INVITE_RE, bypass_group_help, try_join_from_text

logger = logging.getLogger(__name__)

PUBLIC_RE = re.compile(r"https?://t\.me/([A-Za-z0-9_]{3,})", re.I)


async def _join_public(client: TelegramClient, username: str) -> bool:
    if username.lower() in {"addlist", "joinchat", "c", "+", "s"}:
        return False
    try:
        entity = await client.get_entity(username)
        await client(JoinChannelRequest(entity))
        return True
    except Exception as exc:
        logger.debug("join @%s: %s", username, exc)
        return False


async def join_from_message(client: TelegramClient, text: str) -> int:
    joined = 0
    if await try_join_from_text(client, text):
        joined += 1

    for match in PUBLIC_RE.finditer(text or ""):
        path = match.group(1)
        if path.startswith("+") or path.lower() == "joinchat":
            continue
        if path.lower().startswith("addlist"):
            continue
        if await _join_public(client, path):
            joined += 1
    return joined


async def handle_mention_event(client: TelegramClient, event: events.NewMessage.Event, me_id: int) -> None:
    message = event.message
    text = message.message or ""

    logger.info("Пинг в чате %s — пробую автовход", event.chat_id)
    joined = await join_from_message(client, text)

    if event.is_group or event.is_channel:
        await bypass_group_help(client, event.chat_id)

    if joined:
        logger.info("Автовход: подключено чатов %s", joined)


async def register_mention_handler(client: TelegramClient) -> None:
    me = await client.get_me()
    me_id = me.id
    username = (me.username or "").lower()

    @client.on(events.NewMessage(incoming=True))
    async def _on_new_message(event: events.NewMessage.Event) -> None:
        message = event.message
        text = (message.message or "").lower()

        mentioned = bool(getattr(message, "mentioned", False))
        if message.entities:
            for entity in message.entities:
                if getattr(entity, "user_id", None) == me_id:
                    mentioned = True
                    break
        if username and f"@{username}" in text:
            mentioned = True

        if not mentioned:
            return

        try:
            await handle_mention_event(client, event, me_id)
        except Exception as exc:
            logger.warning("mention handler: %s", exc)
