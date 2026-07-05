import asyncio
import logging
import re

from telethon import TelegramClient
from telethon.errors import RPCError
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.types import User

logger = logging.getLogger(__name__)

GROUP_HELP_USERNAMES = frozenset(
    {
        "grouphelpbot",
        "group_help_bot",
        "grouphelp2bot",
        "grouphelp3bot",
        "guardbot",
        "grouphelp_rubot",
        "grouphelp_enbot",
    }
)

VERIFY_BUTTON_MARKERS = (
    "verify",
    "вериф",
    "подтвер",
    "human",
    "человек",
    "не бот",
    "not a bot",
    "пройти",
    "нажми",
    "click",
    "✅",
    "☑",
    "✔",
    "👤",
    "🤖",
    "start",
)

INVITE_RE = re.compile(
    r"https?://t\.me/(?:\+|joinchat/)([A-Za-z0-9_-]+)",
    re.I,
)


def _is_group_help(entity) -> bool:
    username = (getattr(entity, "username", None) or "").lower()
    if username in GROUP_HELP_USERNAMES:
        return True
    first = (getattr(entity, "first_name", None) or "").lower()
    return "group help" in first or "grouphelp" in first


async def _click_verify_buttons(client: TelegramClient, chat_id: int) -> int:
    clicked = 0
    async for message in client.iter_messages(chat_id, limit=25):
        sender = await message.get_sender()
        if not _is_group_help(sender):
            continue
        if not message.reply_markup:
            continue
        try:
            for row in message.reply_markup.rows:
                for button in row.buttons:
                    label = (getattr(button, "text", None) or "").lower()
                    if any(marker in label for marker in VERIFY_BUTTON_MARKERS):
                        await message.click(text=button.text)
                        clicked += 1
                        await asyncio.sleep(1)
                        break
                if clicked:
                    break
            if not clicked and message.reply_markup.rows:
                first = message.reply_markup.rows[0].buttons[0]
                await message.click(text=first.text)
                clicked += 1
                await asyncio.sleep(1)
        except Exception as exc:
            logger.debug("Не удалось нажать кнопку Group Help: %s", exc)
    return clicked


async def _start_group_help_pm(client: TelegramClient) -> bool:
    for username in ("GroupHelpBot", "grouphelpbot"):
        try:
            await client.send_message(username, "/start")
            await asyncio.sleep(1)
            return True
        except RPCError:
            continue
    return False


async def bypass_group_help(client: TelegramClient, chat_id: int) -> bool:
    clicked = await _click_verify_buttons(client, chat_id)
    if clicked:
        logger.info("Group Help: нажато кнопок %s в чате %s", clicked, chat_id)
        await asyncio.sleep(2)
        return True

    started = await _start_group_help_pm(client)
    if started:
        clicked = await _click_verify_buttons(client, chat_id)
        if clicked:
            logger.info("Group Help: повторно нажато %s кнопок", clicked)
            await asyncio.sleep(2)
            return True
    return clicked > 0 or started


async def message_still_exists(client: TelegramClient, chat_id: int, message_id: int) -> bool:
    try:
        msg = await client.get_messages(chat_id, ids=message_id)
        return bool(msg)
    except RPCError:
        return False


async def try_join_invite(client: TelegramClient, invite_hash: str) -> bool:
    try:
        await client(ImportChatInviteRequest(invite_hash.lstrip("+")))
        return True
    except RPCError as exc:
        logger.debug("Invite %s: %s", invite_hash[:8], exc)
        return False


async def try_join_from_text(client: TelegramClient, text: str) -> bool:
    joined = False
    for match in INVITE_RE.finditer(text or ""):
        if await try_join_invite(client, match.group(1)):
            joined = True
    return joined


async def ensure_member(client: TelegramClient, chat_id: int, me: User) -> bool:
    try:
        entity = await client.get_entity(chat_id)
        permissions = await client.get_permissions(entity, me)
        if getattr(permissions, "send_messages", None) is False:
            await bypass_group_help(client, chat_id)
        return True
    except RPCError as exc:
        text = str(exc).lower()
        if "not a participant" in text or "private" in text:
            async for message in client.iter_messages(chat_id, limit=10):
                if await try_join_from_text(client, message.message or ""):
                    return True
        return False
