import logging

from telethon import TelegramClient
from telethon.tl.functions.chatlists import CheckChatlistInviteRequest
from telethon.tl.types import Channel, Chat, User

logger = logging.getLogger(__name__)


def _peer_token(entity) -> str | None:
    if isinstance(entity, User):
        return None
    username = getattr(entity, "username", None)
    if username:
        return username.lower()
    return str(entity.id)


async def resolve_addlist_slugs(
    client: TelegramClient,
    slugs: frozenset[str],
) -> tuple[list[str], list[str]]:
    if not slugs:
        return [], []

    resolved: list[str] = []
    failed: list[str] = []
    seen: set[str] = set()

    for slug in slugs:
        try:
            result = await client(CheckChatlistInviteRequest(slug=slug))
            entities = list(getattr(result, "chats", None) or [])
            count = 0
            for entity in entities:
                token = _peer_token(entity)
                if token and token not in seen:
                    seen.add(token)
                    resolved.append(token)
                    count += 1
            logger.info("addlist %s → %s чатов", slug, count)
        except Exception as exc:
            failed.append(slug)
            logger.warning("addlist %s — ошибка: %s", slug, exc)

    return resolved, failed
