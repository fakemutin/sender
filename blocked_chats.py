import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BLOCKED_FILE = Path(os.getenv("BLOCKED_CHATS_FILE", "blocked_chats.json"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_blocked() -> dict:
    if not BLOCKED_FILE.exists():
        return {"entries": {}}
    with BLOCKED_FILE.open(encoding="utf-8") as handle:
        data = json.load(handle)
    data.setdefault("entries", {})
    return data


def save_blocked(data: dict) -> None:
    with BLOCKED_FILE.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _keys(chat_id: int | str, username: str | None) -> list[str]:
    keys = [str(chat_id)]
    if username:
        keys.append(username.lower().lstrip("@"))
    return keys


def is_blocked(chat_id: int, username: str | None, account: str | None = None) -> bool:
    entries = load_blocked().get("entries", {})
    for key in _keys(chat_id, username):
        item = entries.get(key)
        if not item:
            continue
        if account and item.get("account") not in (None, account, "all"):
            continue
        return True
    return False


def block_chat(
    chat_id: int,
    username: str | None,
    reason: str,
    *,
    account: str | None = None,
) -> None:
    data = load_blocked()
    entries = data.setdefault("entries", {})
    payload = {
        "chat_id": chat_id,
        "username": username,
        "reason": reason,
        "account": account or "all",
        "at": _now(),
    }
    for key in _keys(chat_id, username):
        entries[key] = payload
    save_blocked(data)


def unblock_chat(chat_id: int, username: str | None) -> bool:
    data = load_blocked()
    entries = data.get("entries", {})
    removed = False
    for key in _keys(chat_id, username):
        if key in entries:
            del entries[key]
            removed = True
    if removed:
        save_blocked(data)
    return removed


def blocked_count() -> int:
    entries = load_blocked().get("entries", {})
    seen: set[int] = set()
    for item in entries.values():
        cid = item.get("chat_id")
        if cid is not None:
            seen.add(int(cid))
    return len(seen)


def estimate_accounts(total_chats: int, per_account: int | None = None) -> dict:
    limit = per_account or int(os.getenv("CHATS_PER_ACCOUNT", "750"))
    if total_chats <= 0:
        return {"total": 0, "accounts": 0, "per_account": limit, "with_proxy": 0}
    accounts = (total_chats + limit - 1) // limit
    return {
        "total": total_chats,
        "accounts": accounts,
        "per_account": limit,
        "with_proxy": max(0, accounts - 1),
        "without_proxy": 1 if accounts > 0 else 0,
    }
