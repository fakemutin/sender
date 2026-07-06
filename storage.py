import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ACCOUNTS_FILE = Path(os.getenv("ACCOUNTS_FILE", "accounts.json"))
STATE_FILE = Path(os.getenv("BOT_STATE_FILE", "bot_state.json"))


def get_admin_ids() -> set[int]:
    raw = os.getenv("ADMIN_IDS", "").strip()
    if not raw:
        return set()
    return {int(part.strip()) for part in raw.split(",") if part.strip()}


def load_accounts_raw() -> dict:
    if not ACCOUNTS_FILE.exists():
        return {
            "parallel_accounts": True,
            "delay_between_accounts": 300,
            "break_after_cycle": 10800,
            "defaults": {},
            "accounts": [],
        }
    with ACCOUNTS_FILE.open(encoding="utf-8") as handle:
        return json.load(handle)


def save_accounts_raw(payload: dict) -> None:
    ACCOUNTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with ACCOUNTS_FILE.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def find_account(payload: dict, name: str) -> dict | None:
    for account in payload.get("accounts", []):
        if str(account.get("name", "")).strip() == name:
            return account
    return None


def update_account(name: str, **fields) -> None:
    payload = load_accounts_raw()
    account = find_account(payload, name)
    if account is None:
        raise ValueError(f"Аккаунт '{name}' не найден")
    account.update(fields)
    save_accounts_raw(payload)


def update_defaults(**fields) -> None:
    payload = load_accounts_raw()
    defaults = payload.setdefault("defaults", {})
    defaults.update(fields)
    save_accounts_raw(payload)


def set_global_field(key: str, value) -> None:
    payload = load_accounts_raw()
    payload[key] = value
    save_accounts_raw(payload)


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    with STATE_FILE.open(encoding="utf-8") as handle:
        return json.load(handle)


def save_state(state: dict) -> None:
    with STATE_FILE.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _merge_list_field(payload: dict, name: str | None, field: str, items: list[str]) -> int:
    if name:
        account = find_account(payload, name)
        if account is None:
            raise ValueError(f"Аккаунт '{name}' не найден")
        scope = account
    else:
        scope = payload.setdefault("defaults", {})

    current = scope.get(field) or []
    if isinstance(current, str):
        current = [part.strip() for part in current.split(",") if part.strip()]
    before = len(current)
    merged = list(dict.fromkeys([*current, *items]))
    scope[field] = merged
    return len(merged) - before


def append_allowed_chats(name: str | None, chats: list[str]) -> int:
    payload = load_accounts_raw()
    added = _merge_list_field(payload, name, "allowed_chats", chats)
    save_accounts_raw(payload)
    return added


def append_addlists(name: str | None, slugs: list[str]) -> int:
    payload = load_accounts_raw()
    added = _merge_list_field(payload, name, "addlists", slugs)
    save_accounts_raw(payload)
    return added


def chat_counts(name: str | None = None) -> dict:
    payload = load_accounts_raw()
    if name:
        account = find_account(payload, name)
        scope = account or {}
    else:
        scope = payload.get("defaults", {})

    chats = scope.get("allowed_chats") or []
    addlists = scope.get("addlists") or []
    if isinstance(chats, str):
        chats = [part.strip() for part in chats.split(",") if part.strip()]
    if isinstance(addlists, str):
        addlists = [part.strip() for part in addlists.split(",") if part.strip()]
    return {"chats": len(chats), "addlists": len(addlists)}


def add_account(
    name: str,
    session_name: str,
    *,
    api_id: int | None = None,
    api_hash: str | None = None,
    proxy: str | None = None,
    source_chat: str | None = None,
    source_message_id: int | None = None,
    enabled: bool = True,
) -> None:
    payload = load_accounts_raw()
    if find_account(payload, name):
        raise ValueError(f"Аккаунт '{name}' уже существует")

    defaults = payload.setdefault("defaults", {})
    account = {
        "name": name,
        "session_name": session_name,
        "enabled": enabled,
    }
    if api_id is not None:
        account["api_id"] = api_id
    if api_hash:
        account["api_hash"] = api_hash
    if proxy:
        account["proxy"] = proxy
    if source_chat:
        account["source_chat"] = source_chat
    elif defaults.get("source_chat"):
        account["source_chat"] = defaults["source_chat"]
    if source_message_id is not None:
        account["source_message_id"] = source_message_id
    elif defaults.get("source_message_id"):
        account["source_message_id"] = defaults["source_message_id"]

    payload.setdefault("accounts", []).append(account)
    save_accounts_raw(payload)


def upsert_account(
    name: str,
    session_name: str,
    *,
    api_id: int | None = None,
    api_hash: str | None = None,
    proxy: str | None = None,
    source_chat: str | None = None,
    source_message_id: int | None = None,
    enabled: bool = True,
) -> str:
    payload = load_accounts_raw()
    account = find_account(payload, name)
    if account is None:
        add_account(
            name,
            session_name,
            api_id=api_id,
            api_hash=api_hash,
            proxy=proxy,
            source_chat=source_chat,
            source_message_id=source_message_id,
            enabled=enabled,
        )
        return "added"

    account["session_name"] = session_name
    account["enabled"] = enabled
    if api_id is not None:
        account["api_id"] = api_id
    if api_hash:
        account["api_hash"] = api_hash
    if proxy is not None:
        if proxy:
            account["proxy"] = proxy
        else:
            account.pop("proxy", None)
    if source_chat:
        account["source_chat"] = source_chat
    if source_message_id is not None:
        account["source_message_id"] = source_message_id
    save_accounts_raw(payload)
    return "updated"


def get_pending_import(user_id: int) -> dict | None:
    imports = load_state().get("pending_imports", {})
    return imports.get(str(user_id))


def set_pending_import(user_id: int, data: dict) -> None:
    state = load_state()
    imports = state.setdefault("pending_imports", {})
    imports[str(user_id)] = data
    state["pending_imports"] = imports
    save_state(state)


def clear_pending_import(user_id: int) -> None:
    state = load_state()
    imports = state.get("pending_imports", {})
    imports.pop(str(user_id), None)
    state["pending_imports"] = imports
    save_state(state)


def next_account_name() -> str:
    payload = load_accounts_raw()
    used = {a.get("name") for a in payload.get("accounts", [])}
    index = 1
    while f"acc{index}" in used:
        index += 1
    return f"acc{index}"
