import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return int(value)


@dataclass(frozen=True)
class Settings:
    api_id: int
    api_hash: str
    session_name: str
    source_chat: str
    source_message_id: int
    delay_between_chats: int
    break_after_cycle: int
    require_admin: bool
    allowed_chats: frozenset[str]


def load_settings() -> Settings:
    api_id = os.getenv("API_ID")
    api_hash = os.getenv("API_HASH")
    session_name = os.getenv("SESSION_NAME")

    if not api_id or not api_hash or not session_name:
        raise RuntimeError(
            "Заполните API_ID, API_HASH и SESSION_NAME в .env (см. .env.example)"
        )

    raw_allowed = os.getenv("ALLOWED_CHATS", "").strip()
    allowed = frozenset(
        part.strip().lower().lstrip("@")
        for part in raw_allowed.split(",")
        if part.strip()
    )

    return Settings(
        api_id=int(api_id),
        api_hash=api_hash,
        session_name=session_name,
        source_chat=os.getenv("SOURCE_CHAT", "").strip(),
        source_message_id=_env_int("SOURCE_MESSAGE_ID", 0),
        delay_between_chats=_env_int("DELAY_BETWEEN_CHATS", 120),
        break_after_cycle=_env_int("BREAK_AFTER_CYCLE", 10800),
        require_admin=_env_bool("REQUIRE_ADMIN", True),
        allowed_chats=allowed,
    )
