import json
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from proxy import Socks5Proxy, parse_socks5_proxy, validate_proxy_required

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


def _parse_string_list(raw: str | list | None) -> frozenset[str]:
    if raw is None:
        return frozenset()
    if isinstance(raw, list):
        parts = raw
    else:
        parts = raw.split(",")
    return frozenset(
        str(part).strip().lower().lstrip("@")
        for part in parts
        if str(part).strip()
    )


def _parse_allowed_chats(raw: str | list | None) -> frozenset[str]:
    return _parse_string_list(raw)


def _parse_addlists(raw: str | list | None) -> frozenset[str]:
    return _parse_string_list(raw)


def _load_accounts_sidecar() -> dict:
    path = Path(os.getenv("ACCOUNTS_FILE", "accounts.json"))
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _merge_sidecar_defaults(sidecar: dict, env: dict) -> dict:
    merged = {**sidecar, **env}
    for field in ("allowed_chats", "addlists"):
        env_value = env.get(field)
        if env_value in (None, "", []):
            if sidecar.get(field):
                merged[field] = sidecar[field]
    return merged


@dataclass(frozen=True)
class AccountSettings:
    name: str
    api_id: int
    api_hash: str
    session_name: str
    source_chat: str
    source_message_id: int
    delay_between_chats: int
    require_admin: bool
    allowed_chats: frozenset[str]
    addlists: frozenset[str]
    proxy: Socks5Proxy | None = None
    enabled: bool = True


@dataclass(frozen=True)
class AppConfig:
    accounts: tuple[AccountSettings, ...]
    delay_between_accounts: int
    break_after_cycle: int
    parallel_accounts: bool


def _require_api_credentials() -> tuple[int, str]:
    api_id = os.getenv("API_ID")
    api_hash = os.getenv("API_HASH")
    if not api_id or not api_hash:
        raise RuntimeError("Заполните API_ID и API_HASH в .env")
    return int(api_id), api_hash


def _env_defaults() -> dict:
    return {
        "session_name": os.getenv("SESSION_NAME", "").strip(),
        "source_chat": os.getenv("SOURCE_CHAT", "").strip(),
        "source_message_id": _env_int("SOURCE_MESSAGE_ID", 0),
        "delay_between_chats": _env_int("DELAY_BETWEEN_CHATS", 120),
        "require_admin": _env_bool("REQUIRE_ADMIN", True),
        "allowed_chats": os.getenv("ALLOWED_CHATS", ""),
        "proxy": os.getenv("SOCKS5_PROXY", "").strip() or None,
    }


def _build_account(name: str, data: dict, defaults: dict, api_id: int, api_hash: str) -> AccountSettings:
    merged = {**defaults, **data}
    session_name = str(merged.get("session_name", "")).strip()
    if not session_name:
        raise RuntimeError(f"Аккаунт '{name}': укажите session_name")

    source_chat = str(merged.get("source_chat", "")).strip()
    source_message_id = int(merged.get("source_message_id", 0))
    if not source_chat or not source_message_id:
        raise RuntimeError(f"Аккаунт '{name}': укажите source_chat и source_message_id")

    account_api_id = merged.get("api_id", api_id)
    account_api_hash = merged.get("api_hash", api_hash)
    proxy = parse_socks5_proxy(merged.get("proxy"), account_name=name)

    return AccountSettings(
        name=name,
        api_id=int(account_api_id),
        api_hash=str(account_api_hash),
        session_name=session_name,
        source_chat=source_chat,
        source_message_id=source_message_id,
        delay_between_chats=int(merged.get("delay_between_chats", 120)),
        require_admin=bool(merged.get("require_admin", True)),
        allowed_chats=_parse_allowed_chats(merged.get("allowed_chats")),
        addlists=_parse_addlists(merged.get("addlists")),
        proxy=proxy,
        enabled=bool(merged.get("enabled", True)),
    )


def _load_from_accounts_file(path: Path, api_id: int, api_hash: str) -> AppConfig:
    if not path.exists():
        raise RuntimeError(f"Файл аккаунтов не найден: {path}")

    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)

    defaults = {**_env_defaults(), **payload.get("defaults", {})}
    accounts_raw = payload.get("accounts")
    if not accounts_raw:
        raise RuntimeError(f"В {path} нет секции accounts")

    accounts: list[AccountSettings] = []
    for index, item in enumerate(accounts_raw, start=1):
        name = str(item.get("name") or f"account{index}").strip()
        accounts.append(_build_account(name, item, defaults, api_id, api_hash))

    validate_proxy_required(tuple(accounts))

    return AppConfig(
        accounts=tuple(accounts),
        delay_between_accounts=int(
            payload.get("delay_between_accounts", _env_int("DELAY_BETWEEN_ACCOUNTS", 300))
        ),
        break_after_cycle=int(
            payload.get("break_after_cycle", _env_int("BREAK_AFTER_CYCLE", 10800))
        ),
        parallel_accounts=bool(
            payload.get("parallel_accounts", _env_bool("PARALLEL_ACCOUNTS", True))
        ),
    )


def load_app_config() -> AppConfig:
    api_id, api_hash = _require_api_credentials()
    env_defaults = _env_defaults()
    accounts_file = Path(os.getenv("ACCOUNTS_FILE", "accounts.json"))

    if accounts_file.exists():
        sidecar = _load_accounts_sidecar()
        if sidecar.get("accounts"):
            return _load_from_accounts_file(accounts_file, api_id, api_hash)

    # Старый режим: все переменные в .env (приоритет)
    if env_defaults["session_name"]:
        sidecar = _load_accounts_sidecar()
        sidecar_defaults = sidecar.get("defaults", {})
        merged_env = _merge_sidecar_defaults(sidecar_defaults, env_defaults)
        account = _build_account("default", merged_env, {}, api_id, api_hash)
        return AppConfig(
            accounts=(account,),
            delay_between_accounts=_env_int("DELAY_BETWEEN_ACCOUNTS", 300),
            break_after_cycle=_env_int("BREAK_AFTER_CYCLE", 10800),
            parallel_accounts=_env_bool("PARALLEL_ACCOUNTS", True),
        )

    if accounts_file.exists():
        return _load_from_accounts_file(accounts_file, api_id, api_hash)

    raise RuntimeError(
        "Заполните SESSION_NAME в .env (один аккаунт) "
        "или создайте accounts.json (см. accounts.example.json)"
    )


def filter_accounts(config: AppConfig, names: set[str] | None) -> tuple[AccountSettings, ...]:
    active = tuple(account for account in config.accounts if account.enabled)
    if not active:
        raise RuntimeError("Нет включённых аккаунтов (enabled: true)")

    if not names:
        validate_proxy_required(active)
        return active

    selected = tuple(account for account in active if account.name in names)
    missing = names - {account.name for account in selected}
    if missing:
        raise RuntimeError(f"Неизвестные аккаунты: {', '.join(sorted(missing))}")

    validate_proxy_required(selected)
    return selected
