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
